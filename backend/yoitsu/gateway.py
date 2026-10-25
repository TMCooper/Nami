"""YoitsuGateway: single entry point of the UI for anime data.

It speaks the YoitsuWrap contract — each source API's /getInfoAnime (title, cover, synopsis,
Saison, url) at the API_LINK of the YoitsuWrap Config — but asynchronously and lazily:
YoitsuWrap's own Anime.search_by_name builds every season and health-checks every episode
with yt-dlp, which takes minutes per anime. YoitsuWrap objects keep handling scans.

On top of the contract it merges the sources: one entity per anime (EntityIndex), seasons
merged across sources, VOSTFR/VF versions, every player of an episode, and optional AniList
data (aliases, banner, trailer, English synopsis).
"""
import os
import re
import time
import asyncio
from typing import List, Optional
from urllib.parse import urlparse

import httpx

from backend.services.cache_service import cache_service
from backend.services.catalog_service import catalog_service, get_canonical_search_queries, CatalogService, SEARCH_COVER_WAIT
from backend.services.cover_utils import client_cover_url, is_usable_cover, is_trusted_cover, raw_cover_url
from backend.services.yoitsu_service import yoitsu_service
from backend.yoitsu.aliases import AliasIndex
from backend.yoitsu.anilist import AniListClient, media_titles
from backend.yoitsu.index import Entry, EntityIndex, build_entity, entity_id, entry_rank, key_from_entity_id
from backend.yoitsu.normalize import (
    franchise_of, is_valid_key, legacy_title_from_url, season_key, slug_of, split_version, strong_root, title_key
)

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data")
META_DIR = os.path.join(DATA_DIR, "meta")

SOURCES = {"anime_sama": "ANIMESAMA", "voiranime": "VOIRANIME"}
SOURCE_HOSTS = {"anime_sama": "anime-sama", "voiranime": "voir-anime"}
CATALOG_REFRESH = 1800          # seconds between catalogue snapshots (sibling evidence for grouping)
CATALOG_RETRY = 60
DETAILS_ANILIST_WAIT = 3.0
VF_PROBE_WAIT = 4.0
VF_PROBE_TTL = 86400
ENRICH_PER_SEARCH = 4
MAX_AS_PAGES = 3
FLUSH_DELAY = 10.0
SYNOPSIS_STUB = re.compile(r"^saison\s+\d+\s+de\b", re.IGNORECASE)


def learnable_keys(titles) -> set:
    """Alias keys learned from a name list: exact and season-stripped only.

    Subtitle roots are not learned ("Naruto: Shippuuden" must not alias "Naruto").
    """
    keys = set()
    for t in titles or []:
        if not isinstance(t, str):
            continue
        key = title_key(split_version(t)[0])
        for k in (key, strong_root(key)[0]):
            if (is_valid_key(k) and len(k) >= 4) or (len(k) >= 2 and k.replace(" ", "").isdigit()):
                keys.add(k)
    return keys


def _as_list(value) -> list:
    if isinstance(value, list):
        return [v.strip() for v in value if isinstance(v, str) and v.strip()]
    if isinstance(value, str):
        return [v.strip() for v in value.split(",") if v.strip()]
    return []


def _vf_url(url: str) -> str:
    base = re.sub(r"/(?:vostfr|vf)/?$", "", url.rstrip("/"))
    return f"{base}/vf"


def _dedup(items) -> list:
    return list(dict.fromkeys(i for i in items if i))


class YoitsuGateway:
    def __init__(self, meta_dir: str = META_DIR):
        self.aliases = AliasIndex(os.path.join(meta_dir, "aliases.json"))
        self.index = EntityIndex(self.aliases, os.path.join(meta_dir, "entries.json"))
        self.anilist = AniListClient(os.path.join(meta_dir, "anilist.json"))
        self._client: Optional[httpx.AsyncClient] = None
        self._tasks: set = set()
        self._catalog_next = 0.0
        self._catalog_task: Optional[asyncio.Task] = None
        self._flush_task: Optional[asyncio.Task] = None
        self._vf_probe: dict = {}
        self._probe_semaphore = asyncio.Semaphore(3)

    # --- plumbing ---
    def _spawn(self, coro) -> asyncio.Task:
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=5.0))
        return self._client

    def _flush_all(self):
        self.index.flush()
        self.aliases.flush()
        self.anilist.flush()

    def _schedule_flush(self):
        """Debounced persistence of entries, aliases and the AniList cache (off the event loop)."""
        if self._flush_task is None or self._flush_task.done():
            self._flush_task = self._spawn(self._flush_later())

    async def _flush_later(self):
        await asyncio.sleep(FLUSH_DELAY)
        await asyncio.to_thread(self._flush_all)

    async def close(self):
        try:
            await asyncio.to_thread(self._flush_all)
        except Exception as e:
            print(f"[Yoitsu] Final flush failed: {e}")
        if self._client is not None:
            await self._client.aclose()
            self._client = None
        await self.anilist.close()

    # --- YoitsuWrap contract ---
    async def get_info(self, source: str, title: str) -> list:
        """/getInfoAnime of one source: [] when the source is down or has no match (VoirAnime answers 404)."""
        api = yoitsu_service.api_link(SOURCES[source])
        try:
            resp = await self._http().get(f"{api}/getInfoAnime", params={"q": title})
        except httpx.HTTPError:
            return []
        if resp.status_code != 200:
            return []
        try:
            data = resp.json()
        except ValueError:
            return []
        return [row for row in data if isinstance(row, dict)] if isinstance(data, list) else []

    def ensure_catalog(self, force: bool = False):
        """Refreshes the catalogue snapshot in background (used as sibling evidence and entity lookup)."""
        if self._catalog_task and not self._catalog_task.done():
            return
        if force or time.monotonic() >= self._catalog_next:
            self._catalog_task = self._spawn(self._load_catalog())

    async def _load_catalog(self):
        entries = []
        as_api = yoitsu_service.api_link("ANIMESAMA")
        va_api = yoitsu_service.api_link("VOIRANIME")
        try:
            resp = await self._http().get(f"{as_api}/loadBaseAnimeData", timeout=300.0)
            data = resp.json() if resp.status_code == 200 else []
        except (httpx.HTTPError, ValueError):
            data = []
        for item in data if isinstance(data, list) else []:
            link = (item.get("link") or item.get("lien")) if isinstance(item, dict) else None
            if link and item.get("title"):
                entries.append(Entry("anime_sama", link, item["title"], item.get("cover") or ""))
        try:
            # /catalog keeps VoirAnime's raw names (loadBaseAnimeData strips ':' and accents)
            resp = await self._http().get(f"{va_api.rsplit('/api', 1)[0]}/catalog", timeout=60.0)
            catalog = resp.json().get("catalog", {}) if resp.status_code == 200 else {}
        except (httpx.HTTPError, ValueError, AttributeError):
            catalog = {}
        for name, link in catalog.items() if isinstance(catalog, dict) else []:
            if name and isinstance(link, str):
                entries.append(Entry("voiranime", link, name))
        if entries:
            await asyncio.to_thread(self.index.set_catalog, entries)
            self._catalog_next = time.monotonic() + CATALOG_REFRESH
        else:
            self._catalog_next = time.monotonic() + CATALOG_RETRY

    # --- lists ---
    @staticmethod
    def client_entity(entity: dict) -> dict:
        fallbacks = [client_cover_url(c) for c in entity.get("cover_fallbacks", [])]
        return {
            "id": entity["id"],
            "title": entity["title"],
            "alt_titles": entity.get("alt_titles", []),
            "cover": client_cover_url(entity.get("cover", "")),
            "cover_fallbacks": [c for c in fallbacks if c],
            "source": entity["source"],
            "url": entity["url"],
            "sources": entity.get("sources", []),
        }

    @staticmethod
    def _entries(items) -> List[Entry]:
        out = []
        for item in items or []:
            if isinstance(item, dict) and item.get("url") and item.get("title"):
                out.append(Entry(item.get("source", "anime_sama"), item["url"], item["title"], item.get("cover") or ""))
        return out

    def group(self, entries: List[Entry], remember: str = "all") -> List[dict]:
        """remember: 'all' (search results), 'new' (only unknown entries: shelves) or 'none'."""
        if remember != "none":
            to_remember = entries if remember == "all" else [e for e in entries if not self.index.knows(e.ident)]
            if to_remember:
                self.index.remember(to_remember)
                self._schedule_flush()
        return self.index.group(entries)

    async def search(self, query: str = "", source: str = "all") -> list:
        self.ensure_catalog()
        q = query.strip()
        if not q:
            return await self.catalogue(source)

        tasks = []
        for term in get_canonical_search_queries(q):
            if source in ("all", "anime_sama"):
                tasks.append(catalog_service._search_anime_sama(term))
            if source in ("all", "voiranime"):
                tasks.append(catalog_service._search_voiranime(term, group=False, cover_wait=0))
        results = await asyncio.gather(*tasks, return_exceptions=True)
        entries = [e for res in results if isinstance(res, list) for e in self._entries(res)]
        entities = self.group(entries)

        scored = []
        for e in entities:
            score = max(CatalogService._calc_relevance(t, q) for t in [e["title"], *e["alt_titles"]])
            scored.append((score, e))
        if any(score >= 85.0 for score, _ in scored):
            scored = [(s, e) for s, e in scored if s >= 60.0]
        scored.sort(key=lambda se: se[0], reverse=True)

        await self._fill_entity_covers([e for _, e in scored], entries)
        self._enrich_in_background([e for _, e in scored])
        return [{**self.client_entity(e), "_score": s} for s, e in scored]

    async def _fill_entity_covers(self, entities: list, entries: List[Entry]):
        """Covers are scraped only for cards that have none (one VoirAnime post per card)."""
        missing = [e for e in entities if not e.get("cover") and e["source"] == "voiranime"][:15]
        if not missing:
            return
        items = [{"title": next((x.title for x in entries if x.url == e["url"]), e["title"]), "url": e["url"], "cover": ""} for e in missing]
        await catalog_service._fill_missing_voiranime_covers(items, limit=15, wait_seconds=SEARCH_COVER_WAIT)
        for entity, item in zip(missing, items):
            if item.get("cover"):
                entity["cover"] = item["cover"]

    async def catalogue(self, source: str = "all") -> list:
        tasks = []
        if source in ("all", "anime_sama"):
            tasks.append(catalog_service._search_anime_sama(""))
        if source in ("all", "voiranime"):
            tasks.append(catalog_service._search_voiranime("", group=False))
        results = await asyncio.gather(*tasks, return_exceptions=True)
        entities = self.group([e for res in results if isinstance(res, list) for e in self._entries(res)], remember="new")
        if not entities and source in ("all", "anime_sama"):
            return await self.random(24)
        return [self.client_entity(e) for e in entities]

    async def random(self, count: int = 12) -> list:
        raw = cache_service.get_random_animes(count=count * 3)
        entities = self.group(self._entries(raw), remember="new")
        return [self.client_entity(e) for e in entities[:count]]

    def recents(self, user_id: str) -> list:
        raw = cache_service.get_recent_animes(user_id)
        viewed = {(a.get("source", "anime_sama"), slug_of(a.get("url", ""))): a.get("viewed_at") for a in raw}
        entities = self.group(self._entries(raw), remember="new")
        out = []
        for e in entities:
            item = self.client_entity(e)
            item["viewed_at"] = viewed.get((e["source"], slug_of(e["url"])))
            out.append(item)
        return out

    @staticmethod
    def valid_entry(source: str, url: str) -> bool:
        host = (urlparse(url or "").hostname or "").lower()
        return source in SOURCES and url.startswith(("http://", "https://")) and SOURCE_HOSTS[source] in host

    async def lookup(self, source: str, url: str, title: str) -> Optional[dict]:
        """Entity of one source entry (history / legacy links only know source + url + title)."""
        if not title or not self.valid_entry(source, url):
            return None
        entry = Entry(source, url, title)
        if not self.index.knows(entry.ident):
            self.index.remember([entry])
            self._schedule_flush()
        key = self.index.canonical_key(entry)
        members = await asyncio.to_thread(self.index.entries_for, entity_id(key))
        return self.client_entity(build_entity(key, members or [entry]))

    def _enrich_in_background(self, entities: list):
        if not self.anilist.enabled or self.anilist.busy():
            return
        started = 0
        for e in entities:
            if started >= ENRICH_PER_SEARCH:
                break
            if len(e["sources"]) > 1 or self.anilist.has(e["title"]):
                continue
            self._spawn(self._learn_from_anilist(e["key"], e["title"]))
            started += 1

    def _learn(self, canonical: str, keys: set) -> str:
        """Unions names into an entity, never pulling in another entity's Anime-Sama page."""
        keys = set(keys) - self.index.foreign_as_keys(canonical)
        result = self.aliases.union({canonical} | keys, anchor=canonical)
        self._schedule_flush()
        return result

    async def _learn_from_anilist(self, key: str, title: str, priority: bool = False) -> Optional[dict]:
        media = await self.anilist.lookup(title, priority=priority)
        if media:
            self._learn(key, learnable_keys(media_titles(media)))
        self._schedule_flush()
        return media

    # --- details ---
    async def details(self, eid: str, refresh: bool = False, user_id: str = "default", track_recent: bool = True) -> Optional[dict]:
        self.ensure_catalog()
        canonical = self.aliases.find(key_from_entity_id(eid))
        cache_key = f"entity:{canonical}"
        details = None if refresh else cache_service.get_anime_details("entity", cache_key)
        if details:
            members = await asyncio.to_thread(self.index.entries_for, eid)
            stale = sorted(f"{m.source}:{m.slug}" for m in members) != details.get("_members") or (
                not details.get("_complete") and self.index.catalog_loaded
            )
            if stale and members:
                details = None
        if not details:
            details = await self._build_details(eid, canonical, refresh)
            if not details:
                return None
            final_key = f"entity:{key_from_entity_id(details['id'])}"
            for key in _dedup([cache_key, final_key]):
                cache_service.save_anime_details("entity", key, details)
        if track_recent:
            cache_service.add_recent_anime(user_id, {
                "title": details["title"], "url": details["url"], "source": details["source"], "cover": details.get("cover", "")
            })
        return self.client_details(details)

    async def _build_details(self, eid: str, canonical: str, refresh: bool = False) -> Optional[dict]:
        members = await asyncio.to_thread(self.index.entries_for, eid)
        if not members and self._catalog_task and not self._catalog_task.done():
            await asyncio.wait({self._catalog_task}, timeout=10.0)
            members = await asyncio.to_thread(self.index.entries_for, eid)
        if not members:
            return None
        entity = build_entity(canonical, members)

        as_entries = sorted((m for m in members if m.source == "anime_sama"), key=entry_rank)[:MAX_AS_PAGES]
        va_entries = [m for m in members if m.source == "voiranime"]
        anilist_task = self._spawn(self._learn_from_anilist(canonical, entity["title"], priority=True)) if self.anilist.enabled else None

        as_infos = await asyncio.gather(*(self._anime_sama_info(e, refresh) for e in as_entries)) if as_entries else []
        va_info = await self._voiranime_info(va_entries) if va_entries else None
        as_infos = [i for i in as_infos if i]

        media = None
        if anilist_task:
            done, _ = await asyncio.wait({anilist_task}, timeout=DETAILS_ANILIST_WAIT)
            if anilist_task in done and not anilist_task.cancelled() and anilist_task.exception() is None:
                media = anilist_task.result()

        # Anime-Sama alternative titles: learned only when they name an entry Nami knows
        alt_from_as = [t for info in as_infos for t in info.get("alt_titles", [])]
        if alt_from_as:
            known_names = await asyncio.to_thread(self.index.entry_keys)
            linking = {k for k in learnable_keys(alt_from_as) if k in known_names and len(k.split()) >= 2}
            if linking:
                self._learn(canonical, linking)

        seasons = self._merge_seasons(as_infos, va_info)
        await self._probe_vf(seasons, refresh)

        primary_as = as_infos[0] if as_infos else None
        alt_titles = []
        for t in [*entity["alt_titles"], *alt_from_as, *(media_titles(media)[:3] if media else [])]:
            if t and t != entity["title"] and t not in alt_titles:
                alt_titles.append(t)

        covers = [c for c in [
            primary_as.get("cover") if primary_as else "",
            entity.get("cover", ""),
            va_info.get("cover") if va_info else "",
            *entity.get("cover_fallbacks", []),
            media.get("cover") if media else "",
        ] if c and is_usable_cover(c)]
        covers = _dedup(raw_cover_url(c) for c in covers)

        details = {
            "id": entity_id(self.aliases.find(canonical)),
            "title": entity["title"],
            "alt_titles": alt_titles[:10],
            "synopsis": self._pick_synopsis(primary_as, va_info, media),
            "cover": covers[0] if covers else "",
            "cover_fallbacks": covers[1:],
            "banner": media.get("banner") if media else None,
            "trailer": media.get("trailer") if media else None,
            "color": media.get("color") if media else None,
            "genres": primary_as.get("genres", []) if primary_as else [],
            "anilist_id": media.get("id") if media else None,
            "source": entity["source"],
            "url": entity["url"],
            "sources": entity["sources"],
            "seasons": seasons,
            "_members": sorted(f"{m.source}:{m.slug}" for m in members),
            "_complete": self.index.catalog_loaded,
        }
        if anilist_task and media is None and not anilist_task.done():
            # AniList answered late (rate limit queue): patch the cached details when it does
            cache_keys = _dedup([f"entity:{canonical}", f"entity:{key_from_entity_id(details['id'])}"])
            anilist_task.add_done_callback(lambda t, keys=cache_keys: self._spawn(self._patch_with_media(keys, t)))
        return details

    async def _patch_with_media(self, cache_keys: list, task: asyncio.Task):
        if task.cancelled() or task.exception() is not None or not task.result():
            return
        media = task.result()
        for key in cache_keys:
            cached = cache_service.get_anime_details("entity", key)
            if not cached:
                continue
            cached.update({
                "banner": cached.get("banner") or media.get("banner"),
                "trailer": cached.get("trailer") or media.get("trailer"),
                "color": cached.get("color") or media.get("color"),
                "anilist_id": cached.get("anilist_id") or media.get("id"),
            })
            if not cached.get("synopsis") and media.get("description"):
                cached["synopsis"] = {"text": media["description"], "lang": "en", "origin": "anilist"}
            cache_service.save_anime_details("entity", key, cached)

    async def _anime_sama_info(self, entry: Entry, refresh: bool = False) -> Optional[dict]:
        rows_task = self.get_info("anime_sama", split_version(entry.title)[0])
        page_task = catalog_service.fetch_anime_sama_page(entry.url, refresh=refresh)
        rows, page = await asyncio.gather(rows_task, page_task)
        rows = [r for r in rows if slug_of(r.get("base_url", "")) == entry.slug]
        if not rows and not page:
            return None

        seasons, seen = [], set()
        for r in rows:
            label = (r.get("Saison") or "").strip()
            if label and label.lower() != "nom" and label not in seen and r.get("url"):
                seen.add(label)
                seasons.append({"label": label, "url": r["url"]})
        if not seasons and page:
            seasons = page["seasons"]

        first = rows[0] if rows else {}
        # The page h1 is the key the old flow used for history and download folders
        history_title = (page or {}).get("title") or first.get("title") or entry.title
        return {
            "slug": entry.slug,
            "title": history_title,
            "cover": first.get("cover") or (page or {}).get("cover") or "",
            "synopsis": first.get("synopsis") or (page or {}).get("synopsis") or "",
            "alt_titles": _as_list(first.get("alt_titles")) or (page or {}).get("alt_titles", []),
            "genres": _as_list(first.get("genres")) or (page or {}).get("genres", []),
            "seasons": seasons,
            "history_title": history_title,
            "history_titles": _dedup([history_title, first.get("title"), entry.title]),
        }

    async def _voiranime_info(self, entries: List[Entry]) -> dict:
        """VoirAnime seasons are built from the posts Nami knows (one post = one season x version).

        voiranime_API's own season labels collapse posts ("2nd Season", "Final Season" and
        spin-offs all become "Saison 1"), so its rows only provide the synopsis and cover.
        """
        posts = sorted(entries, key=entry_rank)
        primary = posts[0]
        history_title = legacy_title_from_url(primary.url)
        member_keys = {title_key(split_version(e.title)[0]) for e in posts}
        member_slugs = {e.slug for e in posts}

        labelled = []
        for e in posts:
            # Only the entity's own posts are evidence: "Fullmetal Alchemist: Brotherhood" stays "Saison 1"
            _, info = franchise_of(e.title, lambda root: root in member_keys)
            labelled.append((e, info.get("season") or info.get("subtitle") or "Saison 1"))
        # With a "Hunter x Hunter (2011)" post, the un-yeared posts are the original series: they must
        # not merge into the other source's "Saison 1" (which may be the remake)
        lineage = any(label.startswith("Remake ") for _, label in labelled)

        by_label: dict = {}
        for e, label in labelled:
            display = f"Original · {label}" if lineage and not label.startswith("Remake ") else label
            version = "vf" if e.is_vf else "vostfr"
            slot = by_label.setdefault(display, {"label": label, "display": display, "vostfr": None, "vf": None})
            if slot[version] and slot[version] != e.url:
                # Two different posts for one label: keep both instead of overwriting
                alt = f"{display} · {split_version(e.title)[0]}"
                slot = by_label.setdefault(alt, {"label": label, "display": alt, "vostfr": None, "vf": None})
            slot[version] = slot[version] or e.url

        rows = await self.get_info("voiranime", split_version(primary.title)[0])
        own_rows = [r for r in rows if any(slug_of(u) in member_slugs for u in (r.get("_vostfr_url"), r.get("_vf_url"), r.get("url")) if u)]
        synopsis = next((r.get("synopsis") for r in own_rows if r.get("synopsis")), "")
        cover = next((r.get("cover") for r in own_rows if is_usable_cover(r.get("cover") or "") and is_trusted_cover(r["cover"], "voiranime")), "")
        cover = cover or next((e.cover for e in posts if is_usable_cover(e.cover) and is_trusted_cover(e.cover, "voiranime")), "")
        return {"seasons": list(by_label.values()), "synopsis": synopsis or "", "cover": cover, "history_title": history_title}

    @staticmethod
    def _merge_seasons(as_infos: list, va_info: Optional[dict]) -> list:
        merged = {}

        def add(label: str, variant: dict, key_prefix: str = "", display: str = ""):
            key, order = season_key(label)
            key = f"{key_prefix}{key}"
            season = merged.setdefault(key, {"key": key, "label": display or label, "order": list(order),
                                             "variants": [], "is_scans": False})
            if variant["source"] == "anime_sama":
                season["label"] = display or label
            if variant["version"] == "scans":
                season["is_scans"] = True
            season["variants"].append(variant)

        for page_index, info in enumerate(as_infos):
            # A second Anime-Sama page keeps its own tabs; its history keys stay those of its own title
            prefix = f"{info['slug']}:" if page_index else ""
            for s in info["seasons"]:
                label = s["label"]
                display = f"{info['title']} · {label}" if page_index else label
                titles = info["history_titles"]
                base = {"source": "anime_sama", "history_title": info["history_title"], "history_titles": titles,
                        "season_label": label}
                if season_key(label)[0] == "scans":
                    add(label, {**base, "version": "scans", "url": s["url"], "available": True, "season_name": label,
                                "history_keys": [{"title": t, "season": label} for t in titles]}, prefix, display)
                    continue
                add(label, {**base, "version": "vostfr", "url": s["url"], "available": True, "season_name": label,
                            "history_keys": [{"title": t, "season": label} for t in titles]}, prefix, display)
                vf_name = f"{label} VF"
                add(label, {**base, "version": "vf", "url": _vf_url(s["url"]), "available": None, "season_name": vf_name,
                            "history_keys": [{"title": t, "season": vf_name} for t in titles]}, prefix, display)

        if va_info:
            main = va_info["history_title"]
            for s in va_info["seasons"]:
                label, display = s["label"], s.get("display", s["label"])
                for version in ("vostfr", "vf"):
                    url = s.get(version)
                    if not url:
                        continue
                    name = display if version == "vostfr" else f"{display} VF"
                    post_title = legacy_title_from_url(url)
                    # Before the merge every VoirAnime post was its own card stored under "Saison 1"
                    keys = [{"title": main, "season": name}]
                    if post_title != main:
                        keys.append({"title": post_title, "season": "Saison 1"})
                    elif name != label:
                        keys.append({"title": main, "season": label})
                    add(display, {
                        "source": "voiranime", "version": version, "url": url, "available": True,
                        "season_name": name, "season_label": label, "history_title": main,
                        "history_titles": _dedup([main, post_title]), "history_keys": keys,
                    })

        return sorted(merged.values(), key=lambda s: s["order"])

    async def _probe_vf(self, seasons: list, refresh: bool = False):
        """Anime-Sama does not list VF availability: check the VF season pages (bounded wait, cached a day)."""
        pending = {}
        now = time.time()
        for season in seasons:
            for v in season["variants"]:
                if v["source"] == "anime_sama" and v["version"] == "vf" and v["available"] is None:
                    known = None if refresh else self._vf_probe.get(v["url"])
                    if known and now - known[1] < VF_PROBE_TTL:
                        v["available"] = known[0]
                    else:
                        pending.setdefault(v["url"], []).append(v)
        if not pending:
            return
        tasks = {self._spawn(self._probe_one(url)): url for url in pending}
        done, _ = await asyncio.wait(list(tasks), timeout=VF_PROBE_WAIT)
        for task in done:
            if not task.cancelled() and task.exception() is None and task.result() is not None:
                for v in pending[tasks[task]]:
                    v["available"] = task.result()

    async def _probe_one(self, url: str) -> Optional[bool]:
        async with self._probe_semaphore:
            lecteurs = await catalog_service._anime_sama_lecteurs(url)
        if lecteurs is None:
            return None  # could not check: stays "unknown", never cached
        available = bool(lecteurs)
        self._vf_probe[url] = (available, time.time())
        return available

    @staticmethod
    def _pick_synopsis(as_info: Optional[dict], va_info: Optional[dict], media: Optional[dict]) -> Optional[dict]:
        candidates = [
            (as_info.get("synopsis") if as_info else "", "fr", "anime_sama"),
            (va_info.get("synopsis") if va_info else "", "fr", "voiranime"),
            (media.get("description") if media else "", "en", "anilist"),
        ]
        for text, lang, origin in candidates:
            text = (text or "").strip()
            # VoirAnime sequel pages often only say "Saison 2 de « X »"
            if text and not (len(text) < 80 and SYNOPSIS_STUB.match(text)):
                return {"text": text, "lang": lang, "origin": origin}
        return None

    @staticmethod
    def client_details(details: dict) -> dict:
        fallbacks = [client_cover_url(c) for c in details.get("cover_fallbacks", [])]
        out = {k: v for k, v in details.items() if not k.startswith("_")}
        out.update({
            "cover": client_cover_url(details.get("cover", "")),
            "cover_fallbacks": [c for c in fallbacks if c],
            "banner": client_cover_url(details.get("banner") or "") or None,
        })
        return out

    # --- episodes & players ---
    async def episodes(self, eid: str, season: str, source: str = "", version: str = "vostfr", refresh: bool = False) -> Optional[dict]:
        details = await self.details(eid, track_recent=False)
        if not details:
            return None
        season_obj = next((s for s in details["seasons"] if s["key"] == season), None)
        if not season_obj:
            return None
        variants = season_obj["variants"]
        usable = [v for v in variants if v["available"] is not False]
        variant = (
            next((v for v in usable if v["source"] == source and v["version"] == version), None)
            or next((v for v in usable if v["version"] == version), None)
            or next((v for v in usable if v["source"] == source), None)
            or (usable or variants)[0]
        )
        result = {"season": {"key": season_obj["key"], "label": season_obj["label"]}, "variant": variant,
                  "is_scans": variant["version"] == "scans", "episodes": []}
        if result["is_scans"]:
            return result  # scans keep using /api/episodes (YoitsuWrap Scan objects)

        if variant["source"] == "anime_sama":
            episodes = await catalog_service.fetch_anime_sama_players(variant["url"], variant["version"], refresh=refresh)
            if not episodes:
                episodes = await catalog_service.fetch_anime_sama_episodes(
                    season_url=variant["url"], anime_title=variant["history_title"],
                    season_name=variant.get("season_label", variant["season_name"]), version=variant["version"], refresh=refresh
                )
        else:
            va = await catalog_service.get_details(url=variant["url"], source="voiranime", refresh=refresh, track_recent=False)
            episodes = va.get("episodes", []) if va else []
        result["episodes"] = episodes
        return result

    async def players(self, url: str) -> list:
        if not self.valid_entry("voiranime", url):
            return []
        return await catalog_service.extract_voiranime_players(url)


yoitsu_gateway = YoitsuGateway()
