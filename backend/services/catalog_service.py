import json
import re
import time
import asyncio
import httpx
from urllib.parse import urljoin, urlparse
from typing import Optional, List, Dict
from bs4 import BeautifulSoup
from backend.services import api_state
from backend.services.cache_service import cache_service
from backend.services.cover_registry import cover_registry
from backend.services.cover_utils import (
    client_cover_url, raw_cover_url, is_usable_cover, is_trusted_cover, extract_page_cover
)

AS_API_BASE = "http://127.0.0.1:5000"
VA_API_BASE = "http://127.0.0.1:8000"

COVER_MISS_TTL = 1800          # seconds before retrying a page whose cover could not be found
COVER_SCRAPE_CONCURRENCY = 6
BACKGROUND_COVER_CONCURRENCY = 2
SEARCH_COVER_WAIT = 5.0        # seconds a search waits for missing covers; the rest finish in background

# voiranime_API /resolve returns the kind under "type"; the player and downloads expect these values
RESOLVER_TYPES = {"hls": "m3u8", "m3u8": "m3u8", "mp4": "mp4"}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
}

CANONICAL_ALIASES = {
    "spice and wolf": "ookami to koushinryou",
    "spice & wolf": "ookami to koushinryou",
    "ookami to koushinryou": "spice and wolf",
    "ookami to koushinryu": "spice and wolf",
    "attack on titan": "shingeki no kyojin",
    "lattaque des titans": "shingeki no kyojin",
    "l'attaque des titans": "shingeki no kyojin",
    "shingeki no kyojin": "attack on titan",
    "frieren": "sousou no frieren",
    "frieren: beyond journey's end": "sousou no frieren",
    "sousou no frieren": "frieren",
    "redo of healer": "kaifuku jutsushi no yarinaoshi",
    "kaifuku jutsushi no yarinaoshi": "redo of healer",
    "high school dxd": "high school dxd",
    "high school dxd new": "high school dxd",
    "high school dxd born": "high school dxd",
    "high school dxd hero": "high school dxd",
}

def get_canonical_search_queries(q: str) -> List[str]:
    q_clean = q.strip().lower()
    queries = [q.strip()]
    if q_clean in CANONICAL_ALIASES:
        queries.append(CANONICAL_ALIASES[q_clean])
    simple = re.sub(r'[^a-zA-Z0-9\s]', '', q_clean).strip()
    if simple in CANONICAL_ALIASES and CANONICAL_ALIASES[simple] not in queries:
        queries.append(CANONICAL_ALIASES[simple])
    return queries

def get_base_anime_title(title: str) -> str:
    """Extracts base anime title by stripping season numbers, year reboots, and VF/VOSTFR tags."""
    t = re.sub(r'\s*\((?:VF|VOSTFR|\d{4})\)\s*', '', title, flags=re.IGNORECASE)
    t = re.sub(r'\s+(?:VF|VOSTFR)$', '', t, flags=re.IGNORECASE)
    t = re.sub(r'\s+(?:II|III|IV|V|\d+(?:st|nd|rd|th)?\s*Season|Season\s*\d+|The Final Season|Specials?|OAV|OVA)\s*$', '', t, flags=re.IGNORECASE)
    t = re.sub(r'\s+\d{4}$', '', t)
    return t.strip()


def host_label(url: str) -> str:
    """'https://vidmoly.net/embed-x.html' -> 'vidmoly'."""
    host = (urlparse(url).hostname or "").lower()
    parts = [p for p in host.split(".") if p and p != "www"]
    return parts[-2] if len(parts) >= 2 else (parts[0] if parts else "lecteur")


# Hosts that resolve to a direct stream first (ansembed first, as in AnimeSamaApi); hosts that
# only give an embed page (uqload, ...) after; sibnet last (often unavailable)
_ANIME_SAMA_HOST_ORDER = (
    ("ansembed", "movembed"), ("vidmoly",), ("smoothpre", "vidhide", "streamwish"), ("sendvid",),
    ("voe",), ("mytv", "voembed"), ("embed4me", "lpayer"),
)


def anime_sama_player_rank(url: str) -> int:
    u = url.lower()
    for rank, hosts in enumerate(_ANIME_SAMA_HOST_ORDER):
        if any(h in u for h in hosts):
            return rank
    return 99 if "sibnet" in u else 50


class CatalogService:
    def __init__(self):
        self.client = httpx.AsyncClient(timeout=30.0, headers=HEADERS, follow_redirects=True)
        self._is_updating = False
        self._update_message = "Catalogue au repos"
        self._cover_misses: Dict[str, float] = {}
        self._cover_inflight: Dict[str, asyncio.Task] = {}
        self._cover_semaphore = asyncio.Semaphore(COVER_SCRAPE_CONCURRENCY)
        self._background_cover_semaphore = asyncio.Semaphore(BACKGROUND_COVER_CONCURRENCY)
        self._background_tasks: set = set()
        self._repairing_recents: set = set()

    def _spawn(self, coro):
        """Fire-and-forget task that is kept referenced until it finishes."""
        task = asyncio.create_task(coro)
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        return task

    async def get_update_status(self) -> dict:
        status = await self._update_status()
        # Lets the UI reload the catalogue once the scraper APIs finished starting
        status["apis_ready"] = api_state.all_ready()
        return status

    async def _update_status(self) -> dict:
        if self._is_updating:
            return {"is_updating": True, "message": self._update_message, "source": "all"}

        try:
            resp = await self.client.get(f"{VA_API_BASE}/catalog/status", timeout=3.0)
            if resp.status_code == 200:
                va_status = resp.json()
                if va_status.get("is_updating"):
                    return {
                        "is_updating": True,
                        "message": f"Mise à jour VoirAnime (Page {va_status.get('current_page', '?')})...",
                        "source": "voiranime"
                    }
        except Exception:
            pass
        return {"is_updating": False, "message": "Catalogue au repos", "source": None}

    async def trigger_update(self, source: str = "all") -> dict:
        if self._is_updating:
            return {"is_updating": True, "message": self._update_message}

        self._is_updating = True
        self._update_message = "Mise à jour démarrée..."
        asyncio.create_task(self._run_update(source))
        return {"is_updating": True, "message": "Mise à jour du catalogue démarrée en arrière-plan."}

    async def _run_update(self, source: str):
        try:
            if source in ["all", "anime_sama"]:
                self._update_message = "Mise à jour Anime-Sama en cours..."
                try:
                    await self.client.get(f"{AS_API_BASE}/api/getAllAnime?r=True", timeout=300.0)
                except Exception as e:
                    print(f"[CatalogService] AnimeSama update error: {e}")

            if source in ["all", "voiranime"]:
                self._update_message = "Mise à jour VoirAnime en cours..."
                try:
                    await self.client.get(f"{VA_API_BASE}/catalog/update", timeout=300.0)
                except Exception as e:
                    print(f"[CatalogService] VoirAnime update error: {e}")

            self._update_message = "Catalogue à jour !"
        except Exception as e:
            self._update_message = f"Erreur: {e}"
        finally:
            self._is_updating = False

    def _format_cover_url(self, cover: str) -> str:
        return client_cover_url(cover)

    def _save_voiranime_cached_cover(self, title: str, cover_url: str):
        if not title or not cover_url:
            return
        cover_registry.register(title, cover_url, "voiranime")
        clean_title = re.sub(r'\s*\((?:VF|VOSTFR)\)\s*', '', title, flags=re.IGNORECASE).strip()
        if clean_title != title:
            cover_registry.register(clean_title, cover_url, "voiranime")

    def _get_voiranime_cached_cover(self, title: str) -> str:
        if not title:
            return ""
        cover = cover_registry.lookup(title, "voiranime")
        if cover:
            return cover
        clean_title = re.sub(r'\s*\((?:VF|VOSTFR)\)\s*', '', title, flags=re.IGNORECASE).strip()
        return cover_registry.lookup(clean_title, "voiranime") if clean_title != title else ""

    def _known_voiranime_cover(self, name: str) -> str:
        cov = self._get_voiranime_cached_cover(name)
        if cov:
            return cov
        base_name = get_base_anime_title(name)
        if base_name and base_name != name:
            return self._get_voiranime_cached_cover(base_name)
        return ""

    def _cover_missed_recently(self, url: str) -> bool:
        return self._cover_misses.get(url, 0) > time.monotonic()

    async def _resolve_voiranime_cover(self, name: str, url: str, background: bool = False) -> str:
        """Cover of one VoirAnime entry, looked up by its exact page URL (never by fuzzy title).

        Concurrent callers for the same URL share one scrape; background scrapes (home catalogue,
        repairs) use their own smaller semaphore so they never delay interactive requests.
        """
        # 1. Fast cache lookup
        cov = self._known_voiranime_cover(name)
        if cov or not url:
            return cov

        # 2. Check if detail cache has it
        cached_detail = cache_service.get_anime_details("voiranime", f"voiranime:{url}")
        if cached_detail and is_usable_cover(cached_detail.get("cover", "")) and is_trusted_cover(cached_detail["cover"], "voiranime"):
            raw_c = raw_cover_url(cached_detail["cover"])
            self._save_voiranime_cached_cover(name, raw_c)
            return raw_c

        # 3. Direct HTML scrape of og:image / summary image, with a negative cache for pages without one
        if self._cover_missed_recently(url):
            return ""
        task = self._cover_inflight.get(url)
        if task is None:
            task = self._spawn(self._scrape_voiranime_cover(name, url, background))
            self._cover_inflight[url] = task
            task.add_done_callback(lambda _t, u=url: self._cover_inflight.pop(u, None))
        # shield: a cancelled request must not cancel the scrape other callers wait on
        return await asyncio.shield(task)

    async def _scrape_voiranime_cover(self, name: str, url: str, background: bool) -> str:
        semaphore = self._background_cover_semaphore if background else self._cover_semaphore
        async with semaphore:
            # Another task may have found it (or given up) while this one was queued
            cov = self._known_voiranime_cover(name)
            if cov or self._cover_missed_recently(url):
                return cov
            try:
                r = await self.client.get(url, timeout=4.0, headers={"Referer": "https://voir-anime.to/"})
                if r.status_code == 200:
                    c_url = extract_page_cover(BeautifulSoup(r.text, 'html.parser'), str(r.url))
                    if c_url:
                        self._save_voiranime_cached_cover(name, c_url)
                        return c_url
            except Exception:
                pass
        self._cover_misses[url] = time.monotonic() + COVER_MISS_TTL
        return ""

    async def _fill_missing_voiranime_covers(self, items: list, limit: int, wait_seconds: float):
        """Resolves missing covers concurrently; whatever is not done after wait_seconds finishes in background."""
        # Recently failed URLs give their slot to the next entries
        missing = [
            m for m in items
            if not is_usable_cover(m.get("cover", ""))
            and not self._get_voiranime_cached_cover(m.get("title", ""))
            and not self._cover_missed_recently(m.get("url", ""))
        ][:limit]
        if not missing:
            return
        background = wait_seconds <= 0
        tasks = {
            self._spawn(self._resolve_voiranime_cover(m.get("title", ""), m.get("url", ""), background=background)): m
            for m in missing
        }
        if background:
            return
        done, _pending = await asyncio.wait(list(tasks), timeout=wait_seconds)
        for task in done:
            if not task.cancelled() and task.exception() is None and task.result():
                tasks[task]["cover"] = task.result()

    async def resolve_cover(self, source: str, url: str, title: str = "", background: bool = False) -> str:
        if source == "voiranime":
            return await self._resolve_voiranime_cover(title, url, background=background)
        slug = url.rstrip("/").split("/")[-1] if url else ""
        return f"https://raw.githubusercontent.com/Anime-Sama/IMG/img/contenu/{slug}.jpg" if slug else ""

    async def _repair_details_cover(self, cache_key: str, details: dict, url: str):
        cover = await self._resolve_voiranime_cover(details.get("title", ""), url, background=True)
        if cover:
            cache_service.save_anime_details("voiranime", cache_key, {**details, "cover": cover})

    async def repair_recent_covers(self, user_id: str):
        """Background repair of recents without a usable cover (was done synchronously in GET /api/catalog/recent)."""
        uid = user_id or "default"
        if uid in self._repairing_recents:
            return
        self._repairing_recents.add(uid)
        try:
            for entry in cache_service.recents_missing_cover(uid)[:12]:
                source = entry.get("source", "anime_sama")
                cover = await self.resolve_cover(source, entry.get("url", ""), entry.get("title", ""), background=True)
                if cover:
                    cache_service.set_recent_cover(uid, source, entry.get("url", ""), entry.get("title", ""), cover)
        except Exception as e:
            print(f"[CatalogService] Recent covers repair error: {e}")
        finally:
            self._repairing_recents.discard(uid)

    @staticmethod
    def _calc_relevance(title: str, query: str) -> float:
        if not query.strip():
            return 100.0
        t_lower = title.lower()
        q_lower = query.lower().strip()
        if q_lower == t_lower:
            return 100.0
        if q_lower in t_lower:
            return 90.0 + (len(q_lower) / len(t_lower)) * 5.0
        # Check canonical aliases match as strong match
        if q_lower in CANONICAL_ALIASES and CANONICAL_ALIASES[q_lower] in t_lower:
            return 95.0
        q_tokens = [w for w in q_lower.split() if len(w) > 1]
        if not q_tokens:
            return 0.0
        matched_tokens = [w for w in q_tokens if w in t_lower]
        return (len(matched_tokens) / len(q_tokens)) * 70.0

    @staticmethod
    def _raw_voiranime_entries(items: list) -> list:
        """One item per VoirAnime post (season / VF variant kept apart): grouping is done by the Yoitsu index."""
        out, seen = [], set()
        for it in items:
            name = it.get("title", it.get("name", ""))
            url = it.get("link", it.get("lien", it.get("url", "")))
            if not name or not url or url in seen:
                continue
            seen.add(url)
            cover = it.get("cover", "")
            if not (is_usable_cover(cover) and is_trusted_cover(cover, "voiranime")):
                cover = ""
            out.append({"title": name, "url": url, "cover": cover})
        return out

    def _group_voiranime_entries(self, items: list) -> list:
        """Unifies individual season/variant entries (e.g. S2, VF, Specials) into their parent Anime object."""
        grouped = {}
        for it in items:
            name = it.get("title", it.get("name", ""))
            url = it.get("link", it.get("lien", it.get("url", "")))
            cover = it.get("cover", "")
            # Junk (data:, relative) or legacy Anime-Sama art counts as missing so it gets re-resolved
            if not (is_usable_cover(cover) and is_trusted_cover(cover, "voiranime")):
                cover = ""
            if not name or not url:
                continue
            base_title = get_base_anime_title(name)
            base_key = base_title.lower()

            if base_key not in grouped:
                grouped[base_key] = {
                    "id": f"va:{url}",
                    "title": base_title,
                    "source": "voiranime",
                    "url": url,
                    "cover": cover,
                    "_score": it.get("_score", 0)
                }
            else:
                if cover and not grouped[base_key].get("cover"):
                    grouped[base_key]["cover"] = cover
                # If exact title match with base, use its URL as primary
                if name.lower().strip() == base_key:
                    grouped[base_key]["url"] = url
                    grouped[base_key]["id"] = f"va:{url}"
                    if cover:
                        grouped[base_key]["cover"] = cover
        return list(grouped.values())

    async def search(self, query: str = "", source: str = "all") -> list:
        results = []
        tasks = []
        q_clean = query.strip()
        search_queries = get_canonical_search_queries(q_clean) if q_clean else [""]

        for q_term in search_queries:
            if source in ["all", "anime_sama"]:
                tasks.append(self._search_anime_sama(q_term))
            if source in ["all", "voiranime"]:
                tasks.append(self._search_voiranime(q_term))

        if tasks:
            res_list = await asyncio.gather(*tasks, return_exceptions=True)
            seen_ids = set()
            for res in res_list:
                if isinstance(res, list):
                    for item in res:
                        item_id = item.get("id") or f"{item.get('source')}:{item.get('title')}"
                        if item_id not in seen_ids:
                            seen_ids.add(item_id)
                            results.append(item)

        # Relevance scoring & filtering
        if q_clean and results:
            has_strong_match = False
            for item in results:
                score = self._calc_relevance(item.get("title", ""), q_clean)
                item["_score"] = score
                if score >= 85.0:
                    has_strong_match = True

            # If strong match exists (e.g. "High School DxD"), filter out irrelevant clutter (< 60 score)
            if has_strong_match:
                results = [item for item in results if item.get("_score", 0) >= 60.0]

            # Rank best matches first
            results.sort(key=lambda x: x.get("_score", 0), reverse=True)

        # Fallback to starter/popular recommendations if search is empty and no results found
        if not results and not query.strip():
            if source in ["all", "anime_sama"]:
                return cache_service.get_random_animes(count=24)
            return []

        return results

    async def _search_anime_sama(self, query: str = "") -> list:
        results = []
        q_clean = query.strip()
        try:
            if q_clean:
                resp = await self.client.get(f"{AS_API_BASE}/api/getSerchAnime", params={"q": q_clean, "l": 20})
                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data, list):
                        for item in data:
                            title = item.get("title", "")
                            link = item.get("lien", item.get("link", ""))
                            cover = item.get("cover", "")
                            if not is_usable_cover(cover) and link:
                                slug = link.rstrip("/").split("/")[-1]
                                cover = f"https://cdn.statically.io/gh/Anime-Sama/IMG/img/contenu/{slug}.jpg"
                            if title and link:
                                results.append({
                                    "id": f"as:{link}",
                                    "title": title,
                                    "source": "anime_sama",
                                    "url": link,
                                    "cover": client_cover_url(cover),
                                    # AnimeSamaApi scores with the alternative titles and Anime-Sama's own search
                                    "score": item.get("score")
                                })
            else:
                resp = await self.client.get(f"{AS_API_BASE}/api/loadBaseAnimeData")
                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data, list):
                        for item in data[:300]:
                            title = item.get("title", "")
                            link = item.get("link", item.get("lien", ""))
                            slug = link.rstrip("/").split("/")[-1] if link else ""
                            cover = item.get("cover") if is_usable_cover(item.get("cover") or "") else ""
                            cover = cover or (f"https://cdn.statically.io/gh/Anime-Sama/IMG/img/contenu/{slug}.jpg" if slug else "")
                            if title and link:
                                results.append({
                                    "id": f"as:{link}",
                                    "title": title,
                                    "source": "anime_sama",
                                    "url": link,
                                    "cover": client_cover_url(cover)
                                })
        except Exception as e:
            print(f"[CatalogService] Error querying AnimeSama API: {e}")

        return results

    async def _search_voiranime(self, query: str = "", group: bool = True, cover_wait: float = SEARCH_COVER_WAIT) -> list:
        results = []
        q_clean = query.strip()
        try:
            if q_clean:
                # Try compatible route first
                resp = await self.client.get(f"{VA_API_BASE}/api/getSerchAnime", params={"q": q_clean, "l": 20})
                if resp.status_code != 200:
                    resp = await self.client.get(f"{VA_API_BASE}/anime/search", params={"query": q_clean})

                if resp.status_code == 200:
                    data = resp.json()
                    matches = data.get("results", data) if isinstance(data, dict) else data
                    if isinstance(matches, list):
                        # Unify sub-seasons (e.g. Season II, Specials, VF) under parent Anime
                        grouped_matches = self._group_voiranime_entries(matches) if group else self._raw_voiranime_entries(matches)

                        # Resolve missing covers concurrently (bounded wait, the rest completes in background)
                        await self._fill_missing_voiranime_covers(grouped_matches, limit=15, wait_seconds=cover_wait)

                        for item in grouped_matches:
                            name = item.get("title", item.get("name", ""))
                            url = item.get("link", item.get("lien", item.get("url", "")))
                            cover = item.get("cover", "")
                            if not cover:
                                cover = self._get_voiranime_cached_cover(name)
                            cover = self._format_cover_url(cover)
                            if name and url:
                                results.append({
                                    "id": f"va:{url}",
                                    "title": name,
                                    "source": "voiranime",
                                    "url": url,
                                    "cover": cover
                                })
            else:
                resp = await self.client.get(f"{VA_API_BASE}/api/loadBaseAnimeData")
                if resp.status_code != 200:
                    resp = await self.client.get(f"{VA_API_BASE}/catalog")

                if resp.status_code == 200:
                    data = resp.json()
                    raw_items = []
                    if isinstance(data, list):
                        raw_items = data[:300]
                    elif isinstance(data, dict):
                        cat_dict = data.get("catalog", data)
                        if isinstance(cat_dict, dict):
                            raw_items = [{"title": k, "link": v} for k, v in list(cat_dict.items())[:300]]

                    # Unify sub-seasons (e.g. S2, VF, Specials) under parent Anime
                    grouped_items = self._group_voiranime_entries(raw_items) if group else self._raw_voiranime_entries(raw_items)

                    # Home catalogue: never wait on cover scraping, covers show up on the next load
                    await self._fill_missing_voiranime_covers(grouped_items, limit=20, wait_seconds=0)

                    for item in grouped_items:
                        name = item.get("title", item.get("name", ""))
                        url = item.get("link", item.get("lien", item.get("url", "")))
                        cover = item.get("cover", "")
                        if not cover:
                            cover = self._get_voiranime_cached_cover(name)
                        cover = self._format_cover_url(cover)
                        if name and url:
                            results.append({
                                "id": f"va:{url}",
                                "title": name,
                                "source": "voiranime",
                                "url": url,
                                "cover": cover
                            })
        except Exception as e:
            print(f"[CatalogService] Error querying VoirAnime API: {e}")

        return results

    async def get_details(self, url: str, source: str, refresh: bool = False, user_id: str = "default", track_recent: bool = True) -> dict:
        cache_key = f"{source}:{url}"
        res = None
        if not refresh:
            cached = cache_service.get_anime_details(source, cache_key)
            if cached:
                if source == "voiranime":
                    eps = cached.get("episodes", [])
                    if not eps or "num" not in eps[0] or not isinstance(eps[0].get("num"), int):
                        cached = None
                    elif track_recent and not (is_usable_cover(cached.get("cover", "")) and is_trusted_cover(cached["cover"], "voiranime")):
                        # An empty cover used to stay frozen for the whole cache lifetime: repair it in
                        # background (never make the modal wait), it shows up on the next opening
                        self._spawn(self._repair_details_cover(cache_key, cached, url))
                res = cached

        if not res:
            if source == "anime_sama":
                res = await self._get_details_anime_sama(url)
            elif source == "voiranime":
                res = await self._get_details_voiranime(url)
            if res and res.get("title"):
                cache_service.save_anime_details(source, cache_key, res)

        if not res:
            return {}
        if res.get("title") and track_recent:
            cache_service.add_recent_anime(user_id, res)
        return self._client_details(res)

    @staticmethod
    def _client_details(details: dict) -> dict:
        """Details payload for the browser: covers are stored raw and rewritten here."""
        out = {**details, "cover": client_cover_url(details.get("cover", ""))}
        if isinstance(details.get("seasons"), list):
            out["seasons"] = [
                {**s, "cover": client_cover_url(s["cover"])} if isinstance(s, dict) and "cover" in s else s
                for s in details["seasons"]
            ]
        return out

    @staticmethod
    def _anime_sama_page_metadata(soup) -> tuple:
        """Synopsis, alternative titles and genres of an Anime-Sama catalogue page."""
        synopsis = ""
        node = soup.find(id="synopsisText") or soup.select_one(".oe-synopsis p") or soup.select_one(".oe-synopsis")
        if node:
            for extra in node.find_all(["button", "a"]):
                extra.decompose()
            synopsis = re.sub(r'\s+', ' ', node.get_text(" ", strip=True)).strip()
        alt_node = soup.find(id="titreAlter")
        alt_titles = [t.strip() for t in alt_node.get_text(" ", strip=True).split(",") if t.strip()] if alt_node else []
        genres = [g.get_text(" ", strip=True) for g in soup.select(".oe-genres .genre-pill") if g.get_text(strip=True)]
        return synopsis, alt_titles, genres

    async def _get_details_anime_sama(self, url: str) -> dict:
        ALIASES = {
            "lattaque-des-titans": "shingeki-no-kyojin",
            "attaque-des-titans": "shingeki-no-kyojin",
            "attack-on-titan": "shingeki-no-kyojin",
            "hunter-x-hunter-2011": "hunter-x-hunter"
        }
        raw_slug = url.rstrip("/").split("/")[-1]
        slug = ALIASES.get(raw_slug, raw_slug)
        target_url = url if slug == raw_slug else f"https://anime-sama.to/catalogue/{slug}/"
        default_cover = f"https://raw.githubusercontent.com/Anime-Sama/IMG/img/contenu/{slug}.jpg"

        # 1. Try scraping the catalogue page directly on Anime-Sama
        try:
            fetch_url = target_url.replace("anime-sama.fr", "anime-sama.to")
            resp = await self.client.get(fetch_url, timeout=8.0, headers={"User-Agent": "Mozilla/5.0"})
            if resp.status_code == 200 and "/catalogue/" not in str(resp.url):
                # Stale mirror domains redirect to the home page: retry on the main domain
                fetch_url = f"https://anime-sama.to/catalogue/{slug}/"
                resp = await self.client.get(fetch_url, timeout=8.0, headers={"User-Agent": "Mozilla/5.0"})
            if resp.status_code == 200 and "/catalogue/" in str(resp.url):
                soup = BeautifulSoup(resp.text, 'html.parser')
                h1 = soup.find('h1', id='titreOeuvre') or soup.find('h1')
                anime_name = h1.text.strip() if h1 and h1.text.strip() else slug.replace("-", " ").title()

                cover = extract_page_cover(soup, str(resp.url)) or default_cover
                synopsis, alt_titles, genres = self._anime_sama_page_metadata(soup)

                pattern = re.compile(r'panneau(?:Anime|Film|Scan|Visual)\s*\(\s*["\']([^"\']+)["\']\s*,\s*["\']([^"\']+)["\']\s*\)')
                matches = pattern.findall(resp.text)
                seasons = []
                seen_seasons = set()
                base_clean = fetch_url.rstrip("/")
                for nom, lien in matches:
                    if nom.lower() not in ["nom", "scans"] and lien.lower() != "url":
                        if nom not in seen_seasons:
                            seen_seasons.add(nom)
                            seasons.append({
                                "name": nom,
                                "url": f"{base_clean}/{lien.lstrip('/')}",
                                "raw_link": f"{base_clean}/{lien.lstrip('/')}"
                            })

                if seasons:
                    return {
                        "title": anime_name,
                        "url": target_url,
                        "cover": cover,
                        "synopsis": synopsis,
                        "alt_titles": alt_titles,
                        "genres": genres,
                        "source": "anime_sama",
                        "seasons": seasons
                    }
        except Exception as e:
            print(f"[CatalogService] Direct Anime-Sama scrape error: {e}")

        # 2. Fallback to AnimeSamaApi /api/getInfoAnime
        try:
            title = slug.replace("-", " ")
            resp = await self.client.get(f"{AS_API_BASE}/api/getInfoAnime", params={"q": title})
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list) and len(data) > 0:
                    anime_name = data[0].get("title", title.title())
                    cover = data[0].get("cover") if is_usable_cover(data[0].get("cover") or "") else default_cover
                    seasons = []
                    for item in data:
                        s_name = item.get("Saison", "Saison 1")
                        seasons.append({
                            "name": s_name,
                            "url": item.get("url", target_url),
                            "raw_link": item.get("url", target_url)
                        })
                    return {
                        "title": anime_name,
                        "url": target_url,
                        "cover": cover,
                        "synopsis": "",
                        "source": "anime_sama",
                        "seasons": seasons
                    }
        except Exception as e:
            print(f"[CatalogService] Error fetching AnimeSama details: {e}")

        return {
            "title": slug.replace("-", " ").title(),
            "url": target_url,
            "cover": default_cover,
            "source": "anime_sama",
            "seasons": [{"name": "Saison 1", "url": target_url}]
        }

    async def _get_details_voiranime(self, url: str) -> dict:
        title = url.rstrip("/").split("/")[-1].replace("-", " ").title()
        cover = self._get_voiranime_cached_cover(title)
        synopsis = ""
        page_scraped = False

        # Scrape anime page on VoirAnime to get cover and synopsis directly
        try:
            page_resp = await self.client.get(url, timeout=8.0, headers={"Referer": "https://voir-anime.to/"})
            if page_resp.status_code == 200:
                page_scraped = True
                soup = BeautifulSoup(page_resp.text, 'html.parser')
                cover = extract_page_cover(soup, str(page_resp.url)) or cover

                # Every paragraph: on sequel pages the first one is often just "Saison 2 de ..."
                summary = soup.select_one('.description-summary')
                if summary:
                    paragraphs = [p.get_text(" ", strip=True) for p in summary.find_all('p')]
                    synopsis = "\n\n".join(p for p in paragraphs if p)
        except Exception as e:
            print(f"[CatalogService] VoirAnime page scraping warning: {e}")

        seasons = []
        try:
            info_resp = await self.client.get(f"{VA_API_BASE}/api/getInfoAnime", params={"q": title})
            if info_resp.status_code == 200:
                info_data = info_resp.json()
                if isinstance(info_data, list) and len(info_data) > 0:
                    if not is_usable_cover(cover) and is_usable_cover(info_data[0].get("cover") or ""):
                        cover = info_data[0]["cover"]
                    if len(info_data) > 1:
                        for s in info_data:
                            s_nom = s.get("Saison", "Saison 1")
                            s_url = s.get("url", url)
                            s_cov = s.get("cover") or cover
                            seasons.append({
                                "name": s_nom,
                                "url": s_url,
                                "raw_link": s_url,
                                "cover": raw_cover_url(s_cov)
                            })
        except Exception:
            pass

        cover = raw_cover_url(cover) if is_usable_cover(cover) and is_trusted_cover(cover, "voiranime") else ""
        if cover:
            self._save_voiranime_cached_cover(title, cover)
        elif page_scraped:
            # The page itself has no cover: do not scrape it again for every follow-up request
            self._cover_misses[url] = time.monotonic() + COVER_MISS_TTL

        try:
            resp = await self.client.get(f"{VA_API_BASE}/episodes", params={"anime_url": url})
            if resp.status_code == 200:
                data = resp.json()
                raw_episodes = data.get("episodes", [])
                episodes = []
                for idx, ep in enumerate(raw_episodes):
                    title_str = ep.get("title", "")
                    num_match = re.search(r'-\s*(\d+)\s*(?:VOSTFR|VF)', title_str, re.IGNORECASE) or re.search(r'(\d+)', title_str)
                    ep_num = int(num_match.group(1)) if num_match else idx + 1
                    ep_url = ep.get("url", "")
                    episodes.append({
                        "num": ep_num,
                        "title": title_str or f"Épisode {ep_num}",
                        "url": ep_url,
                        "embed_url": ep_url
                    })
                # Sort ascending by episode number (1, 2, 3...)
                episodes.sort(key=lambda x: x["num"])
                res_dict = {
                    "title": title,
                    "url": url,
                    "cover": cover,
                    "synopsis": synopsis,
                    "source": "voiranime",
                    "episodes": episodes
                }
                if seasons:
                    res_dict["seasons"] = seasons
                return res_dict
        except Exception as e:
            print(f"[CatalogService] Error fetching VoirAnime episodes: {e}")

        res_dict = {"title": title, "url": url, "cover": cover, "synopsis": synopsis, "source": "voiranime", "episodes": []}
        if seasons:
            res_dict["seasons"] = seasons
        return res_dict

    async def fetch_anime_sama_episodes(
        self,
        season_url: str,
        anime_title: str = "",
        season_name: str = "Saison 1",
        version: str = "vostfr",
        refresh: bool = False
    ) -> list:
        cache_key = f"as_eps:{season_url}:{season_name}:{version}"
        if not refresh:
            cached = cache_service.get_anime_details("anime_sama_eps", cache_key)
            if cached and isinstance(cached, list) and len(cached) > 0:
                return cached

        episodes = []

        # 1. Determine title and season to call AnimeSamaApi /api/getAnimeLink?n=...&s=...&v=...
        derived_title = anime_title.strip()
        if not derived_title and "/catalogue/" in season_url:
            slug_match = re.search(r'/catalogue/([^/]+)', season_url)
            if slug_match:
                derived_title = slug_match.group(1).replace("-", " ")

        s_norm = season_name.lower().replace(" ", "")
        if not s_norm or s_norm == "saison":
            s_norm = "saison1"

        # Try API getAnimeLink
        if derived_title:
            try:
                resp = await self.client.get(
                    f"{AS_API_BASE}/api/getAnimeLink",
                    params={"n": derived_title, "s": s_norm, "v": version},
                    timeout=20.0
                )
                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data, list) and len(data) > 0:
                        for item in data:
                            ep_num = item.get("episode", len(episodes) + 1)
                            raw_url = item.get("url", "")
                            if raw_url:
                                is_direct = ".m3u8" in raw_url or ".mp4" in raw_url
                                episodes.append({
                                    "num": ep_num,
                                    "title": f"Épisode {ep_num}",
                                    "embed_url": raw_url,
                                    "stream_url": raw_url if is_direct else None,
                                    "stream_type": "m3u8" if ".m3u8" in raw_url else ("mp4" if ".mp4" in raw_url else None)
                                })
            except Exception as e:
                print(f"[CatalogService] getAnimeLink query error: {e}")

        # 2. Direct episodes.js fallback scraping if API returned 0 episodes
        if not episodes and season_url:
            try:
                target_url = season_url.rstrip("/")
                if not target_url.endswith("/vostfr") and not target_url.endswith("/vf"):
                    target_url = f"{target_url}/{version}"

                resp = await self.client.get(target_url, timeout=10.0)
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, 'html.parser')
                    script_tag = soup.find("script", src=lambda s: s and "episodes.js" in s)
                    if script_tag:
                        js_src = script_tag.get("src", "").strip("\"'")
                        js_url = f"{target_url.rstrip('/')}/{js_src.lstrip('/')}"
                        js_resp = await self.client.get(js_url, headers={"Referer": target_url}, timeout=10.0)
                        if js_resp.status_code == 200:
                            js_text = js_resp.text
                            # Find all var eps1 = [...]; or epsAS = [...]
                            matches = re.findall(r"var\s+(eps\w+)\s*=\s*\[(.*?)\];", js_text, re.DOTALL)
                            lecteurs = {}
                            for l_name, content in matches:
                                urls = re.findall(r"'(https?://[^']+)'", content)
                                if urls:
                                    lecteurs[l_name] = urls

                            if lecteurs:
                                # Pick best lecteur
                                best_key = list(lecteurs.keys())[0]
                                for k in lecteurs:
                                    if "eps1" in k:
                                        best_key = k
                                        break
                                url_list = lecteurs[best_key]
                                for idx, u in enumerate(url_list, 1):
                                    episodes.append({
                                        "num": idx,
                                        "title": f"Épisode {idx}",
                                        "embed_url": u,
                                        "stream_url": u if (".m3u8" in u or ".mp4" in u) else None
                                    })
            except Exception as e:
                print(f"[CatalogService] Direct episodes.js scrape error: {e}")

        if episodes:
            cache_service.save_anime_details("anime_sama_eps", cache_key, episodes)

        return episodes

    @staticmethod
    def _voiranime_player_rank(label: str) -> int:
        kl = label.lower()
        if "sibnet" in kl: return 999
        if "mytv" in kl or "voembed" in kl: return 1
        if "vidmoly" in kl: return 2
        if "sendvid" in kl: return 3
        if "voe" in kl: return 4
        if "streamtape" in kl or "stape" in kl: return 5
        return 10

    @classmethod
    def parse_voiranime_players(cls, page_html: str) -> list:
        """Every usable player of a VoirAnime episode page, best first (sibnet and internal players skipped)."""
        players = []
        sources_match = re.search(r'var\s+thisChapterSources\s*=\s*(\{.*?\});', page_html, re.DOTALL)
        if sources_match:
            try:
                src_dict = json.loads(sources_match.group(1))
            except ValueError:
                src_dict = {}
            for label in sorted(src_dict.keys(), key=cls._voiranime_player_rank):
                src_match = re.search(r'src=["\']([^"\']+)["\']', str(src_dict[label]))
                if not src_match or "sibnet" in label.lower():
                    continue
                embed = src_match.group(1).replace("\\/", "/")
                if embed.startswith("//"):
                    embed = "https:" + embed
                if "voiranime" not in embed and "sibnet" not in embed.lower():
                    players.append({"host": label, "embed_url": embed})
        else:
            soup = BeautifulSoup(page_html, 'html.parser')
            for ifr in soup.find_all('iframe'):
                src = ifr.get('src') or ""
                if src.startswith("//"):
                    src = "https:" + src
                if src and "voiranime" not in src and "sibnet" not in src.lower():
                    players.append({"host": host_label(src), "embed_url": src})
        return players

    async def extract_voiranime_players(self, episode_url: str) -> list:
        try:
            page_resp = await self.client.get(episode_url, headers={**HEADERS, "Referer": "https://voir-anime.to/"}, timeout=8.0)
            if page_resp.status_code == 200:
                return self.parse_voiranime_players(page_resp.text)
        except Exception as e:
            print(f"[CatalogService] VoirAnime iframe extraction error: {e}")
        return []

    async def fetch_anime_sama_players(self, season_url: str, version: str = "vostfr", refresh: bool = False) -> list:
        """Episodes of an Anime-Sama season with every player (lecteur) of episodes.js, best first.

        Players are resolved only when played, so the list loads fast and the UI can switch host.
        """
        base = re.sub(r"/(?:vostfr|vf)/?$", "", season_url.rstrip("/"))
        target_url = f"{base}/{version}"
        cache_key = f"as_players:{target_url}"
        if not refresh:
            cached = cache_service.get_anime_details("anime_sama_eps", cache_key)
            if isinstance(cached, list) and cached:
                return cached

        lecteurs = await self._anime_sama_lecteurs(target_url) or {}
        episodes = []
        count = max((len(urls) for urls in lecteurs.values()), default=0)
        for idx in range(count):
            players = [
                {"host": host_label(urls[idx]), "embed_url": urls[idx], "lecteur": name}
                for name, urls in lecteurs.items() if idx < len(urls) and urls[idx]
            ]
            players.sort(key=lambda p: anime_sama_player_rank(p["embed_url"]))
            if players:
                episodes.append({
                    "num": idx + 1,
                    "title": f"Épisode {idx + 1}",
                    "embed_url": players[0]["embed_url"],
                    "stream_url": None,
                    "players": players,
                })
        if episodes:
            cache_service.save_anime_details("anime_sama_eps", cache_key, episodes)
        return episodes

    async def _anime_sama_lecteurs(self, target_url: str) -> Optional[dict]:
        """{lecteur name: [embed url per episode]} from the season's episodes.js.

        {} means the season page has no episodes (e.g. no VF); None means it could not be checked.
        """
        try:
            resp = await self.client.get(target_url, timeout=10.0)
            if resp.status_code == 404:
                return {}
            if resp.status_code != 200 or "/catalogue/" not in str(resp.url):
                return None
            soup = BeautifulSoup(resp.text, 'html.parser')
            script_tag = soup.find("script", src=lambda s: s and "episodes.js" in s)
            if not script_tag:
                return {}
            js_src = script_tag.get("src", "").strip("\"'")
            js_url = urljoin(f"{str(resp.url).rstrip('/')}/", js_src)
            js_resp = await self.client.get(js_url, headers={"Referer": target_url}, timeout=10.0)
            if js_resp.status_code != 200:
                return None
            lecteurs = {}
            for name, content in re.findall(r"var\s+(eps\w+)\s*=\s*\[(.*?)\];", js_resp.text, re.DOTALL):
                urls = re.findall(r"""['"](https?://[^'"]+)['"]""", content)
                if urls:
                    lecteurs[name] = urls
            return lecteurs
        except Exception as e:
            print(f"[CatalogService] episodes.js scrape error: {e}")
            return None

    async def fetch_anime_sama_page(self, url: str, refresh: bool = False) -> Optional[dict]:
        """Metadata of an Anime-Sama catalogue page (h1, synopsis, alternative titles, genres, seasons).

        The getInfoAnime contract has no alternative titles / genres, and its titles are
        ASCII-normalized: the page h1 is the legacy history / download key. Cached per slug.
        """
        slug = url.rstrip("/").split("/")[-1].lower()
        cache_key = f"as_page:{slug}"
        if not refresh:
            cached = cache_service.get_anime_details("anime_sama_page", cache_key)
            if isinstance(cached, dict) and cached.get("title"):
                return cached
        try:
            resp = await self.client.get(url, timeout=8.0, headers={"User-Agent": "Mozilla/5.0"})
            if resp.status_code == 200 and "/catalogue/" not in str(resp.url):
                resp = await self.client.get(f"https://anime-sama.to/catalogue/{slug}/", timeout=8.0, headers={"User-Agent": "Mozilla/5.0"})
            if resp.status_code != 200 or f"/catalogue/{slug}" not in str(resp.url).lower():
                return None
        except Exception as e:
            print(f"[CatalogService] Anime-Sama page fetch error: {e}")
            return None
        soup = BeautifulSoup(resp.text, 'html.parser')
        h1 = soup.find('h1', id='titreOeuvre')
        if not h1 or not h1.get_text(strip=True):
            return None
        synopsis, alt_titles, genres = self._anime_sama_page_metadata(soup)
        base_clean = str(resp.url).rstrip("/")
        seasons, seen = [], set()
        pattern = re.compile(r'panneau(?:Anime|Film|Scan|Visual)\s*\(\s*["\']([^"\']+)["\']\s*,\s*["\']([^"\']+)["\']\s*\)')
        for nom, lien in pattern.findall(re.sub(r"/\*.*?\*/", "", resp.text, flags=re.DOTALL)):
            if nom.lower() != "nom" and lien.lower() != "url" and nom not in seen:
                seen.add(nom)
                seasons.append({"label": nom, "url": f"{base_clean}/{lien.lstrip('/')}"})
        page = {
            "slug": slug,
            "title": h1.get_text(" ", strip=True),
            "url": base_clean,
            "cover": extract_page_cover(soup, str(resp.url)),
            "synopsis": synopsis,
            "alt_titles": alt_titles,
            "genres": genres,
            "seasons": seasons,
        }
        cache_service.save_anime_details("anime_sama_page", cache_key, page)
        return page

    async def resolve_stream(self, embed_url: str, source: str = "anime_sama") -> dict:
        result = {"stream_url": None, "stream_type": None, "iframe_url": embed_url, "host": None}

        if embed_url.startswith("//"):
            embed_url = "https:" + embed_url

        target_embed = embed_url

        # Already a stream (YoitsuWrap gives resolved, yt-dlp checked hls/mp4 links): nothing to resolve
        try:
            parsed = urlparse(embed_url)
            direct = parsed.path.lower()
            host = parsed.hostname
        except ValueError:
            return result
        if embed_url.startswith(("http://", "https://")) and direct.endswith((".m3u8", ".mp4")):
            result.update(stream_url=embed_url, stream_type="m3u8" if direct.endswith(".m3u8") else "mp4", host=host)
            return result

        # Special handling for VoirAnime: episode URL is a webpage, extract the real video player iframe!
        if "voir-anime.to" in target_embed or source == "voiranime":
            players = await self.extract_voiranime_players(target_embed)
            if players:
                target_embed = players[0]["embed_url"]
                result["iframe_url"] = target_embed
                result["host"] = players[0]["host"]

        # Now resolve the clean target embed via VoirAnime resolver to obtain direct m3u8 or mp4
        try:
            resp = await self.client.get(f"{VA_API_BASE}/resolve", params={"embed_url": target_embed}, timeout=10.0)
            if resp.status_code == 200:
                data = resp.json()
                result["host"] = data.get("host") or result["host"]
                result["iframe_url"] = data.get("embed_url") or target_embed
                stream_url = data.get("stream_url")
                kind = (data.get("type") or data.get("stream_type") or "").lower()
                # A "fallback" answer is only playable when it still carries a direct hls/mp4 link;
                # type "embed" means only the player page works: the UI then shows it in an iframe
                playable = data.get("status") == "success" or (data.get("status") == "fallback" and kind in RESOLVER_TYPES)
                stream_type = self._stream_type(kind, stream_url)
                if playable and stream_url and stream_type:
                    result["stream_url"] = stream_url
                    result["stream_type"] = stream_type
                return result
        except Exception:
            pass

        return result

    @staticmethod
    def _stream_type(kind: str, stream_url: Optional[str]) -> Optional[str]:
        if kind in RESOLVER_TYPES:
            return RESOLVER_TYPES[kind]
        if kind in ("embed", "iframe", "raw"):
            return None
        if (stream_url or "").lower().split("?")[0].endswith(".mp4"):
            return "mp4"
        return "m3u8"

catalog_service = CatalogService()
