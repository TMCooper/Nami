"""YoitsuWrap builds, done once per anime and version, kept on disk.

YoitsuWrap's Anime.search_by_name is the reference way to get an anime: every season, every
episode link resolved by the API, each one checked with yt-dlp, the second API filling the
episodes the first one lacks. It is also slow (about 50 s for Frieren), so it runs here in
background workers, never in a request, and its result is kept as a snapshot, the fiche of the anime:

- the first view of an anime page starts the build and the page waits for it (no duplicate
  seasons or episodes guessed from the APIs meanwhile);
- the episode links are signed and expire (Anime-Sama: 12 h). An expired snapshot is rebuilt
  on the next view, and « Actualiser » on the anime page rebuilds it at once.
"""
import os
import time
import hashlib
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

import requests

from backend.services.storage import load_json, save_json
from backend.yoitsu.normalize import season_key, slug_of

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data")
WRAPPER_DIR = os.path.join(DATA_DIR, "cache", "yoitsu")
DEFAULT_LIFETIME = 6 * 3600     # links without an expiry in their query are trusted this long
EXPIRY_MARGIN = 600             # a link this close to its expiry is treated as expired
RETRY_FAILED = 900              # a failed build is retried after this delay
BUILD_WORKERS = 2               # a long build (One Piece) must not hold every other anime back
SOURCE_NAMES = {"ANIMESAMA": "anime_sama", "VOIRANIME": "voiranime"}
WRAPPER_HOST = "YoitsuWrap"

_original_request = requests.sessions.Session.request
_tracking = threading.local()   # .job: progress dict of the build running in this thread


def _request_with_timeout(self, method, url, **kwargs):
    # YoitsuWrap calls requests without a timeout: one hung API call would block the build worker forever
    kwargs.setdefault("timeout", (10, 180))
    response = _original_request(self, method, url, **kwargs)
    job = getattr(_tracking, "job", None)
    if job is not None:
        _observe(job, url, response)
    return response


requests.sessions.Session.request = _request_with_timeout


def _observe(job: dict, url: str, response):
    """Progress of a build, read from the API calls YoitsuWrap makes (it reports nothing itself)."""
    try:
        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        if parsed.path.endswith("/getInfoAnime"):
            rows = response.json()
            labels = {r.get("Saison") for r in rows if isinstance(r, dict) and r.get("Saison") not in (None, "Scans")} \
                if isinstance(rows, list) else set()
            job["season_labels"] = job.get("season_labels", set()) | labels
        elif parsed.path.endswith("/getSpecificAnime"):
            label = (query.get("s") or [""])[0]
            if label and label != job.get("season"):
                if job.get("season"):
                    job["seasons_done"] = job.get("seasons_done", 0) + 1
                job.update(season=label, checked=0, episodes=0)
        elif parsed.path.endswith("/getAnimeLink"):
            links = response.json()
            if isinstance(links, list) and not job.get("episodes"):
                job["episodes"] = len(links)
    except (ValueError, AttributeError):
        pass


def _count_check(check):
    def wrapper(*args, **kwargs):
        try:
            return check(*args, **kwargs)
        finally:
            job = getattr(_tracking, "job", None)
            if job is not None:
                job["checked"] = job.get("checked", 0) + 1
    return wrapper


def progress_of(job: dict) -> Optional[dict]:
    """{'value': 0..1, 'step': 'Saison 2 · épisode 4/12'} of a running build."""
    seasons = max(len(job.get("season_labels") or ()), 1)
    done = min(job.get("seasons_done", 0), seasons)
    episodes, checked = job.get("episodes", 0), job.get("checked", 0)
    current = min(checked / episodes, 1.0) if episodes else 0.0
    season = job.get("season")
    if not season:
        return {"value": 0.02, "step": "Recherche des saisons"}
    step = f"{season} · épisode {min(checked + 1, episodes)}/{episodes}" if episodes else f"{season} · liens"
    return {"value": round(min((done + current) / seasons, 0.99), 3), "step": step}


def link_expiry(url: str, built_at: float) -> float:
    """Expiry of a signed link: 's' (signing time) + 'e' (lifetime) in its query, else a default lifetime."""
    try:
        query = parse_qs(urlparse(url).query)
        start, lifetime = int(query["s"][0]), int(query["e"][0])
        if start > 0 and lifetime > 0:
            return float(start + lifetime)
    except (KeyError, ValueError, IndexError):
        pass
    return built_at + DEFAULT_LIFETIME


def snapshot_from_anime(anime, query: str, version: str, sources: List[str], built_at: float) -> dict:
    """Plain data of a YoitsuWrap Anime: what Nami keeps of it."""
    seasons, expiries = [], []
    for season in anime.get_seasons().values():
        label = season.get_saison()
        episodes = []
        for ep in season.get_episodes():
            if not ep.link:
                continue
            episodes.append({
                "num": int(ep.episode_number),
                "link": ep.link,
                "source": SOURCE_NAMES.get(str(ep.source).upper(), str(ep.source).lower()),
            })
            expiries.append(link_expiry(ep.link, built_at))
        episodes.sort(key=lambda e: e["num"])
        seasons.append({"label": label, "key": season_key(label)[0], "episodes": episodes})
    return {
        "query": query,
        "version": version,
        "sources": sources,
        "built_at": built_at,
        "valid_until": min(expiries) if expiries else built_at + DEFAULT_LIFETIME,
        "anime": {
            "title": anime.get_title(),
            "cover": anime.get_cover(),
            "link": anime.get_link(),
            "synopsis": anime.get_synopsis() or "",
            "has_scan": bool(anime.get_scan()),
        },
        "seasons": seasons,
    }


def build_with_wrapper(query: str, version: str, allowed: Dict[str, set], order: List[str]) -> Optional[dict]:
    """Runs YoitsuWrap for one anime (blocking: worker thread only)."""
    from YoitsuWrap.Anime import Anime
    from YoitsuWrap.Episode import Episode
    from backend.services.yoitsu_service import yoitsu_service

    if not getattr(Episode.check_vid_health, "_counted", False):
        counted = _count_check(Episode.check_vid_health)
        counted._counted = True
        Episode.check_vid_health = staticmethod(counted)

    config = yoitsu_service.get_config()
    if not config:
        raise RuntimeError("API indisponible")
    # Only the APIs that know this very anime: YoitsuWrap stops on an API answering « not found »,
    # and a fuzzy match on another title must never fill its episodes
    picked = {}
    for name in order:
        conf = config.get(name)
        slugs = allowed.get(name) or set()
        if conf is None or not slugs:
            continue
        try:
            rows = requests.get(f"{conf.API_LINK}/getInfoAnime", params={"q": query}, timeout=20).json()
        except (requests.RequestException, ValueError):
            continue
        if isinstance(rows, list) and rows and isinstance(rows[0], dict) \
                and slug_of(rows[0].get("base_url") or rows[0].get("url") or "") in slugs:
            picked[name] = conf
    if not picked:
        return None
    job = getattr(_tracking, "job", None)
    if job is not None:
        job["season_labels"] = set()   # the checks above were not YoitsuWrap's own calls
    anime = Anime.search_by_name(title=query, config=picked, version=version)
    if not isinstance(anime, Anime):
        return None
    return snapshot_from_anime(anime, query, version, [SOURCE_NAMES[n] for n in picked], time.time())


class WrapperStore:
    def __init__(self, builder: Callable[..., Optional[dict]] = build_with_wrapper):
        self._builder = builder
        self._lock = threading.RLock()
        self._snapshots: Dict[str, dict] = {}
        self._jobs: Dict[str, dict] = {}
        self._executor = ThreadPoolExecutor(max_workers=BUILD_WORKERS, thread_name_prefix="yoitsu-build")

    @staticmethod
    def _id(key: str, version: str) -> str:
        return hashlib.sha1(f"{key}|{version}".encode("utf-8")).hexdigest()[:24]

    def _path(self, key: str, version: str) -> str:
        return os.path.join(WRAPPER_DIR, f"{self._id(key, version)}.json")

    def get(self, key: str, version: str) -> Optional[dict]:
        sid = self._id(key, version)
        with self._lock:
            snap = self._snapshots.get(sid)
        if snap is None:
            stored = load_json(self._path(key, version), dict)
            if isinstance(stored, dict) and isinstance(stored.get("seasons"), list):
                snap = stored
                with self._lock:
                    self._snapshots[sid] = snap
        return snap

    @staticmethod
    def is_fresh(snap: Optional[dict]) -> bool:
        return bool(snap) and time.time() < float(snap.get("valid_until") or 0) - EXPIRY_MARGIN

    def status(self, key: str, version: str) -> dict:
        snap = self.get(key, version)
        with self._lock:
            job = dict(self._jobs.get(self._id(key, version)) or {})
        state = job.get("state")
        if state not in ("queued", "running"):
            if self.is_fresh(snap):
                state = "ready"
            elif snap:
                state = "expired"
            else:
                state = state or "none"   # 'failed' or 'none'
        return {
            "state": state,
            "built_at": (snap or {}).get("built_at"),
            "valid_until": (snap or {}).get("valid_until"),
            "episodes": sum(len(s.get("episodes") or []) for s in (snap or {}).get("seasons") or []),
            "error": job.get("error") if state == "failed" else None,
            "progress": progress_of(job.get("tracking") or {}) if state == "running" else None,
        }

    def ensure(self, key: str, version: str, query: str, allowed: Dict[str, set], order: List[str],
               force: bool = False) -> dict:
        """Starts a build when there is no fresh snapshot (or when forced); never waits for it."""
        sid = self._id(key, version)
        snap = self.get(key, version)
        with self._lock:
            job = self._jobs.get(sid)
            if job and job["state"] in ("queued", "running"):
                return self.status(key, version)
            if not force and self.is_fresh(snap):
                return self.status(key, version)
            if not force and job and job["state"] == "failed" and time.time() - job["at"] < RETRY_FAILED:
                return self.status(key, version)
            self._jobs[sid] = {"state": "queued", "at": time.time(), "error": None}
        self._executor.submit(self._run, key, version, query, allowed, order)
        return self.status(key, version)

    def _run(self, key: str, version: str, query: str, allowed: Dict[str, set], order: List[str]):
        sid = self._id(key, version)
        tracking: dict = {}
        with self._lock:
            self._jobs[sid] = {"state": "running", "at": time.time(), "error": None, "tracking": tracking}
        _tracking.job = tracking
        try:
            snap = self._builder(query, version, allowed, order)
            if not snap:
                raise LookupError("anime introuvable via YoitsuWrap")
            snap["key"] = key
            save_json(self._path(key, version), snap, indent=None)
            with self._lock:
                self._snapshots[sid] = snap
                self._jobs[sid] = {"state": "done", "at": time.time(), "error": None}
        except Exception as e:
            print(f"[YoitsuWrap] Build failed for '{query}' ({version}): {e}")
            with self._lock:
                self._jobs[sid] = {"state": "failed", "at": time.time(), "error": str(e)[:200]}
        finally:
            _tracking.job = None

    def close(self):
        self._executor.shutdown(wait=False, cancel_futures=True)


def wrapper_episodes(season: dict, api_episodes: List[dict], fresh: bool, api_source: str = "") -> List[dict]:
    """Episodes of a season of the YoitsuWrap fiche: its list is the reference.

    Each episode says which source YoitsuWrap took it from. Its verified link comes first while it is
    valid (after the API players once expired); the players of the source API stay behind it as
    fallbacks. An episode only the API lists (YoitsuWrap could not check it) is kept, marked unverified.
    """
    api_by_num = {}
    for ep in api_episodes or []:
        try:
            api_by_num.setdefault(int(ep.get("num")), ep)
        except (TypeError, ValueError):
            continue
    out = []
    for w in season.get("episodes") or []:
        api = api_by_num.pop(w["num"], None) or {}
        fallbacks = api.get("players") or ([{"host": "VoirAnime" if "voir-anime" in api["embed_url"] else "Source",
                                             "embed_url": api["embed_url"]}] if api.get("embed_url") else [])
        fallbacks = [p for p in fallbacks if p.get("embed_url") and p["embed_url"] != w["link"]]
        verified = {"host": WRAPPER_HOST, "embed_url": w["link"], "verified": fresh, "source": w.get("source")}
        players = [verified, *fallbacks] if fresh or not fallbacks else [*fallbacks, verified]
        out.append({**api, "num": w["num"], "title": api.get("title") or f"Épisode {w['num']}",
                    "embed_url": players[0]["embed_url"], "players": players,
                    "source": w.get("source") or api_source, "verified": fresh})
    for num, api in sorted(api_by_num.items()):
        out.append({**api, "num": num, "source": api.get("source") or api_source, "verified": False})
    out.sort(key=lambda e: int(e["num"]))
    return out


wrapper_store = WrapperStore()
