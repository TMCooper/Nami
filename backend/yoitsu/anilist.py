"""Optional AniList lookups: aliases for cross-source merging, plus banner / trailer / English synopsis.

Results are cached on disk (positive and negative) and requests are spaced so Nami stays far
below AniList's rate limit. Interactive lookups (opening an anime) go before background ones.
Set NAMI_ANILIST=0 to disable all outbound calls.
"""
import os
import re
import time
import asyncio
from typing import Optional

import httpx

from backend.services.storage import load_json, save_json
from backend.yoitsu.normalize import title_key, title_variants, strong_root, is_valid_key, split_version

ANILIST_URL = "https://graphql.anilist.co"
MIN_INTERVAL = 3.0              # <= 20 requests/min (AniList allows 30/min)
POSITIVE_TTL = 30 * 86400
NEGATIVE_TTL = 7 * 86400
QUERY = """query ($q: String) { Page(perPage: 5) { media(search: $q, type: ANIME) {
  id idMal format seasonYear episodes title { romaji english native } synonyms
  description(asHtml: false) coverImage { extraLarge color } bannerImage trailer { id site } } } }"""

_HTML_TAG = re.compile(r"<[^>]+>")


def _latin(text: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return text.strip().replace(" ", "").isdigit()  # "86"
    return sum(c.isascii() for c in letters) / len(letters) >= 0.6


def _query_key_ok(key: str) -> bool:
    return is_valid_key(key) or (len(key) >= 2 and key.replace(" ", "").isdigit())


def media_titles(media: dict) -> list:
    titles = [media.get("romaji"), media.get("english")] + list(media.get("synonyms") or [])
    return [t for t in titles if t and _latin(t)]


def _exact_keys(media: dict) -> set:
    keys = set()
    for t in media_titles(media):
        key = title_key(split_version(t)[0])
        keys |= {key, strong_root(key)[0]}
    return keys


def media_keys(media: dict) -> set:
    keys = set()
    for t in media_titles(media):
        keys |= title_variants(t)
    return {k for k in keys if is_valid_key(k) and len(k) >= 4} | _exact_keys(media)


def match_rank(query_title: str, media: dict) -> Optional[int]:
    """0: the queried title is one of the media names; 1: only after dropping a subtitle; None: no match."""
    wanted = title_variants(query_title) | {strong_root(title_key(query_title))[0]}
    if wanted & _exact_keys(media):
        return 0
    if wanted & media_keys(media):
        return 1
    return None


def accepts(query_title: str, media: dict) -> bool:
    return match_rank(query_title, media) is not None


def _summarize(raw: dict) -> dict:
    title = raw.get("title") or {}
    trailer = raw.get("trailer") or {}
    description = _HTML_TAG.sub("", (raw.get("description") or "").replace("<br>", "\n")).strip()
    return {
        "id": raw.get("id"),
        "idMal": raw.get("idMal"),
        "romaji": title.get("romaji"),
        "english": title.get("english"),
        "native": title.get("native"),
        "synonyms": raw.get("synonyms") or [],
        "format": raw.get("format"),
        "year": raw.get("seasonYear"),
        "episodes": raw.get("episodes"),
        "description": description,
        "cover": (raw.get("coverImage") or {}).get("extraLarge"),
        "color": (raw.get("coverImage") or {}).get("color"),
        "banner": raw.get("bannerImage"),
        "trailer": {"site": trailer.get("site"), "id": trailer.get("id")} if trailer.get("id") else None,
    }


def pick_media(query_title: str, raw_media: list) -> Optional[dict]:
    """Exact-name hits beat subtitle-only hits ("Naruto" never picks "Naruto: Shippuuden" over "Naruto")."""
    ranked = []
    for order, media in enumerate(map(_summarize, raw_media)):
        rank = match_rank(query_title, media)
        if rank is not None:
            ranked.append((rank, order, media))
    return min(ranked, key=lambda r: (r[0], r[1]))[2] if ranked else None


class AniListClient:
    def __init__(self, path: str, enabled: Optional[bool] = None):
        self._path = path
        self.enabled = os.environ.get("NAMI_ANILIST", "1") != "0" if enabled is None else enabled
        cache = load_json(path, dict)
        self._cache: dict = cache if isinstance(cache, dict) else {}
        self._inflight: dict = {}
        self._rate_lock = asyncio.Lock()
        self._next_call = 0.0
        self._priority_waiting = 0
        self._dirty = False
        self._client: Optional[httpx.AsyncClient] = None

    def cached(self, title: str) -> Optional[dict]:
        entry = self._cache.get(title_key(title))
        return entry.get("media") if isinstance(entry, dict) else None

    def has(self, title: str) -> bool:
        """Already looked up (found or not) or being looked up."""
        key = title_key(title)
        return key in self._cache or key in self._inflight

    def busy(self) -> bool:
        return bool(self._inflight)

    async def lookup(self, title: str, priority: bool = False) -> Optional[dict]:
        key = title_key(title)
        if not self.enabled or not _query_key_ok(key):
            return None
        entry = self._cache.get(key)
        if isinstance(entry, dict):
            ttl = POSITIVE_TTL if entry.get("media") else NEGATIVE_TTL
            if time.time() - entry.get("at", 0) < ttl:
                return entry.get("media")
        task = self._inflight.get(key)
        if task is None:
            task = asyncio.create_task(self._fetch(title, key, priority))
            self._inflight[key] = task
            task.add_done_callback(lambda _t, k=key: self._inflight.pop(k, None))
        return await asyncio.shield(task)

    async def _fetch(self, title: str, key: str, priority: bool) -> Optional[dict]:
        if priority:
            self._priority_waiting += 1
        else:
            # Background lookups yield to the anime the user is opening
            while self._priority_waiting:
                await asyncio.sleep(0.2)
        try:
            async with self._rate_lock:
                wait = self._next_call - time.monotonic()
                if wait > 0:
                    await asyncio.sleep(wait)
                self._next_call = time.monotonic() + MIN_INTERVAL
                try:
                    if self._client is None:
                        self._client = httpx.AsyncClient(timeout=10.0)
                    resp = await self._client.post(ANILIST_URL, json={"query": QUERY, "variables": {"q": title}})
                except httpx.HTTPError:
                    return None  # transient: not cached
                if resp.status_code == 429:
                    self._next_call = time.monotonic() + min(float(resp.headers.get("retry-after") or 60), 120.0)
                    return None
                if resp.status_code != 200:
                    return None
        finally:
            if priority:
                self._priority_waiting -= 1

        try:
            raw_media = resp.json()["data"]["Page"]["media"] or []
        except (ValueError, KeyError, TypeError):
            raw_media = []
        media = pick_media(title, raw_media)
        self._cache[key] = {"at": time.time(), "media": media}
        self._dirty = True
        return media

    def flush(self):
        if not self._dirty:
            return
        self._dirty = False
        try:
            save_json(self._path, dict(self._cache), indent=None)
        except OSError as e:
            self._dirty = True
            print(f"[AniList] Cache save failed: {e}")

    async def close(self):
        if self._client is not None:
            await self._client.aclose()
            self._client = None
