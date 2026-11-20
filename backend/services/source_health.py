"""Health of each source: its local API, the site behind it, and the user's on/off switch.

The APIs are configured once and can stop, be forgotten, or lose the site they scrape (DNS
blocking, Cloudflare). A source that is not usable is skipped at once everywhere (search, anime
pages, YoitsuWrap builds) instead of making every request wait for its timeouts.
"""
import time
import asyncio
from typing import Dict, Optional
from urllib.parse import urlparse

import httpx

from backend.services.settings_service import settings_service

CHECK_EVERY = 60.0
STALE_AFTER = 20.0
# Fallback defaults used only before an API answers its active domain (or if it doesn't expose one)
SITES = {"anime_sama": "https://anime-sama.to/", "voiranime": "https://voiranime.cx/"}
API_NAMES = {"anime_sama": "ANIMESAMA", "voiranime": "VOIRANIME"}
URL_ENDPOINTS = {"anime_sama": "/getAnimeSamaURL", "voiranime": "/getVoirAnimeURL"}
LABELS = {"anime_sama": "Anime-Sama", "voiranime": "VoirAnime"}
HOST_TOKENS = {"anime_sama": ("anime-sama",), "voiranime": ("voir-anime", "voiranime")}


def _normalize_origin(raw: str) -> Optional[str]:
    """Returns 'https://host/' for a valid http(s) URL, else None."""
    if not isinstance(raw, str):
        return None
    raw = raw.strip()
    if not raw.startswith(("http://", "https://")):
        return None
    try:
        parsed = urlparse(raw)
    except ValueError:
        return None
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return None
    return f"{parsed.scheme}://{parsed.netloc}/"


class SourceHealth:
    def __init__(self):
        self._state: Dict[str, dict] = {}
        self._sites: Dict[str, str] = {}
        self._checked_at = 0.0
        self._lock = asyncio.Lock()
        self._task: Optional[asyncio.Task] = None

    # --- resolved site URLs ---
    def site_url(self, source: str) -> str:
        """Active base URL of a source, learned from its local API (fallback: SITES default)."""
        return self._sites.get(source) or SITES[source]

    def site_host(self, source: str) -> str:
        return (urlparse(self.site_url(source)).hostname or "").lower()

    def matches_source_host(self, source: str, host: Optional[str]) -> bool:
        """True when host belongs to this source (known tokens or the live domain reported by its API)."""
        if not host or source not in SITES:
            return False
        h = host.lower()
        if any(token in h for token in HOST_TOKENS[source]):
            return True
        live_host = self.site_host(source)
        return bool(live_host) and (h == live_host or h.endswith(f".{live_host}"))

    def is_source_url(self, source: str, url: str) -> bool:
        if not isinstance(url, str) or not url.startswith(("http://", "https://")):
            return False
        try:
            host = urlparse(url).hostname
        except ValueError:
            return False
        return self.matches_source_host(source, host)

    # --- switches ---
    @staticmethod
    def disabled() -> set:
        return set(settings_service.get_settings().get("disabled_sources") or [])

    def set_enabled(self, source: str, enabled: bool):
        off = self.disabled()
        if enabled:
            off.discard(source)
        else:
            off.add(source)
        settings_service.update_settings({"disabled_sources": sorted(off)})

    def usable(self, source: str) -> bool:
        """False only when switched off or known to be down: an unchecked source is tried."""
        if source in self.disabled():
            return False
        state = self._state.get(source)
        return state is None or state["status"] == "ok"

    # --- checks ---
    async def _resolve_site_url(self, client: httpx.AsyncClient, api: str, source: str) -> str:
        """Asks the local API for the current site domain so domain rotations require zero config."""
        endpoint = URL_ENDPOINTS.get(source)
        if endpoint:
            try:
                resp = await client.get(f"{api}{endpoint}", timeout=3.0)
                if resp.status_code == 200:
                    data = resp.json()
                    origin = _normalize_origin(data.get("url") if isinstance(data, dict) else None)
                    if origin:
                        if self._sites.get(source) and self._sites[source] != origin:
                            print(f"[Sources] {LABELS[source]} domain updated: {self._sites[source]} -> {origin}")
                        self._sites[source] = origin
                        return origin
            except (httpx.HTTPError, ValueError, TypeError):
                pass
        return self.site_url(source)

    async def _check_one(self, client: httpx.AsyncClient, source: str) -> dict:
        from backend.services.yoitsu_service import yoitsu_service
        api = yoitsu_service.api_link(API_NAMES[source])
        try:
            api_up = (await client.get(f"{api}/status", timeout=3.0)).status_code == 200
        except httpx.HTTPError:
            api_up = False
        if not api_up:
            return {"status": "api_down", "message": f"L'API {LABELS[source]} ne répond pas (est-elle démarrée ?)"}
        site_url = await self._resolve_site_url(client, api, source)
        try:
            # Any HTTP answer means the site is reachable; Cloudflare's challenge answers 403/503
            resp = await client.get(site_url, timeout=8.0, follow_redirects=True)
        except httpx.HTTPError:
            host = (urlparse(site_url).hostname or site_url).lower()
            return {"status": "site_unreachable",
                    "message": f"{LABELS[source]} ({host}) est injoignable depuis ce serveur (bloqué par le DNS du fournisseur ?)"}
        if resp.status_code in (403, 503) and ("cf-mitigated" in resp.headers or "cloudflare" in resp.headers.get("server", "").lower()):
            return {"status": "cloudflare", "message": f"{LABELS[source]} demande une vérification Cloudflare"}
        return {"status": "ok", "message": ""}

    async def refresh(self, force: bool = False) -> Dict[str, dict]:
        async with self._lock:
            if not force and time.monotonic() - self._checked_at < STALE_AFTER and self._state:
                return self._state
            async with httpx.AsyncClient(headers={"User-Agent": "Mozilla/5.0"}) as client:
                results = await asyncio.gather(*(self._check_one(client, s) for s in SITES))
            now = time.time()
            for source, result in zip(SITES, results):
                previous = self._state.get(source, {}).get("status")
                if previous and previous != result["status"]:
                    print(f"[Sources] {LABELS[source]}: {previous} -> {result['status']}")
                self._state[source] = {**result, "checked_at": now}
            self._checked_at = time.monotonic()
            return self._state

    def snapshot(self) -> Dict[str, dict]:
        off = self.disabled()
        return {
            source: {
                "label": LABELS[source],
                "url": self.site_url(source),
                "enabled": source not in off,
                "usable": self.usable(source),
                **self._state.get(source, {"status": "unknown", "message": "", "checked_at": None}),
            }
            for source in SITES
        }

    def start(self):
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._loop())

    async def _loop(self):
        while True:
            try:
                await self.refresh(force=True)
            except Exception as e:
                print(f"[Sources] Health check failed: {e}")
            await asyncio.sleep(CHECK_EVERY)

    async def close(self):
        if self._task is not None:
            self._task.cancel()


source_health = SourceHealth()
