import os
import re
import json
import time
import asyncio
import threading
from typing import Optional, List, Dict, Tuple
from urllib.parse import quote
from backend.services.storage import load_json, save_json_text
from backend.services.cover_utils import raw_cover_url, is_usable_cover, client_cover_url, normalize_title_key, url_host
from backend.services.anime_refs import identity_keys, same_anime, same_entity, clean_trailer, trailer_thumb

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data")
HISTORY_FILE = os.path.join(DATA_DIR, "history.json")

HISTORY_FLUSH_DELAY = 5.0    # the player heartbeat: at most one write per window
FINISHED_RATIO = 0.85
LINK_RANK = {"index": 0, "details": 1, "write": 2}
LINK_RETRY = 1800            # seconds before an unlinked title is offered to the index pass again
MAX_NEXT_HOPS = 50
SOURCES = ("anime_sama", "voiranime")
VERSIONS = ("vostfr", "vf")
_VERSION_WORD = re.compile(r"\b(?:vostfr|vf)\b", re.IGNORECASE)
_RAW_EP_NUMBER = re.compile(r"-\s*(\d+)\s*(?:vostfr|vf)\b", re.IGNORECASE)


def _text(value, limit: int) -> str:
    return value.strip()[:limit] if isinstance(value, str) else ""


def _dedup(items) -> list:
    return list(dict.fromkeys(i for i in items if i))


def _split_ep_key(ep_key: str, record: dict) -> Tuple[str, str]:
    # Season names can contain ':' ("Original · Saison 1: X"), episode ids cannot
    season, sep, ep_id = ep_key.rpartition(":")
    return (season, ep_id) if sep else (record.get("last_season", "Saison 1"), ep_key)


def _played(ep: dict) -> bool:
    return float(ep.get("position_sec") or 0) > 0


def _finished(ep: dict) -> bool:
    pos, dur = float(ep.get("position_sec") or 0), float(ep.get("duration_sec") or 0)
    by_position = dur > 0 and pos / dur >= FINISHED_RATIO
    played_at, watched_at = ep.get("played_at"), ep.get("watched_at")
    if watched_at is not None and watched_at >= (played_at or 0):
        return bool(ep.get("watched"))     # an explicit mark after the last play wins
    if played_at is not None:
        return by_position                 # played since Phase 2: a rewatch is in progress again
    return bool(ep.get("watched")) or by_position   # legacy episode: today's flag


def _last_played(episodes: dict) -> Optional[Tuple[str, dict]]:
    played = [(k, e) for k, e in episodes.items() if isinstance(e, dict) and _played(e)]
    if not played:
        return None
    return max(played, key=lambda ke: float(ke[1].get("played_at") or ke[1].get("last_watched_at") or 0))


def _pointer(record: dict) -> Optional[Tuple[str, str, dict]]:
    """Last PLAYED episode: the save_progress pointer, else (dangling pointer) the most recently played one."""
    episodes = record.get("episodes") or {}
    season, ep_id = record.get("last_season", "Saison 1"), str(record.get("last_ep_id", "1"))
    ep = episodes.get(f"{season}:{ep_id}")
    if isinstance(ep, dict) and _played(ep):
        return season, ep_id, ep
    last = _last_played(episodes)
    if not last:
        return None  # records only created by toggles / mark-season never count
    season, ep_id = _split_ep_key(last[0], record)
    return season, ep_id, last[1]


def _season_host(record: dict, season: str) -> Optional[str]:
    """'voiranime' / 'anime_sama' when every http(s) embed_url of that season agrees, else None."""
    hosts = set()
    for ep_key, ep in (record.get("episodes") or {}).items():
        url = ep.get("embed_url") if isinstance(ep, dict) else None
        if isinstance(url, str) and url.startswith(("http://", "https://")) and _split_ep_key(ep_key, record)[0] == season:
            hosts.add("voiranime" if "voir-anime" in url else "anime_sama")
    return hosts.pop() if len(hosts) == 1 else None


def _link_of(record: dict) -> Optional[dict]:
    ref = record.get("anime")
    return ref if isinstance(ref, dict) and ref.get("id") else None


def _record_keys(title: str, record: dict, canonical=None) -> set:
    ref = _link_of(record)
    return identity_keys(ref, canonical) if ref else {"t:" + (normalize_title_key(title) or title)}


def _group_titles(user_hist: dict, canonical=None) -> List[List[str]]:
    """Titles of one anime (union over _record_keys). Display only: nothing is merged on disk."""
    parent: Dict[str, str] = {}
    owner: Dict[str, str] = {}

    def find(t: str) -> str:
        while parent[t] != t:
            parent[t] = parent[parent[t]]
            t = parent[t]
        return t

    for title, record in user_hist.items():
        if not isinstance(record, dict):
            continue
        parent[title] = title
        for key in _record_keys(title, record, canonical):
            if key not in owner:
                owner[key] = title
                continue
            a, b = find(owner[key]), find(title)
            if a != b:
                parent[b] = a
    groups: Dict[str, List[str]] = {}
    for title in parent:
        groups.setdefault(find(title), []).append(title)
    return list(groups.values())


def _group_key(title: str, record: dict, canonical=None) -> str:
    ref = _link_of(record)
    if ref:
        return (canonical(ref["id"]) if canonical else ref["id"]) or ref["id"]
    return "title:" + (normalize_title_key(title) or title)


def client_ref(ref: Optional[dict], canonical=None, media=None) -> Optional[dict]:
    """A stored link as sent to the browser: current id, lookup fallback and 16:9 images (no network)."""
    if not isinstance(ref, dict) or not ref.get("id"):
        return None
    banner, trailer = ref.get("banner"), ref.get("trailer")
    if media and not (banner and trailer) and ref.get("title"):
        # AniList cache: links made before AniList answered get their art at read time
        cached = media(ref["title"]) or {}
        banner, trailer = banner or cached.get("banner"), trailer or cached.get("trailer")
    eid = ref["id"]
    return {
        "id": (canonical(eid) if canonical else eid) or eid,
        "title": ref.get("title") or "",
        "source": ref.get("source") or "",
        "url": ref.get("url") or "",
        "entry_title": ref.get("entry_title") or "",
        "wide_images": _dedup([client_cover_url(banner or ""), trailer_thumb(trailer)]),
    }


def _episode_title(ep_title: str, ep_id: str, names: set) -> str:
    """Raw source titles ('Sousou no Frieren - 04 VOSTFR') read as 'Épisode N'; real names pass through."""
    title = (ep_title or "").strip()
    key = normalize_title_key(title)
    if not title or _VERSION_WORD.search(title) or any(key == n or key.startswith(n + " ") for n in names):
        if ep_id.isdecimal():
            return f"Épisode {ep_id}"
        # Episode 0 has num 0, so clients fall back to the raw title as its id ('Frieren - 00 VOSTFR')
        match = _RAW_EP_NUMBER.search(ep_id) or _RAW_EP_NUMBER.search(title)
        return f"Épisode {int(match.group(1))}" if match else "Épisode spécial"
    return title


def _pick_claim(cands: List[dict], record: dict, season: str) -> Optional[dict]:
    """The one season variant a legacy (title, season) names; None while the claims stay ambiguous."""
    host = _season_host(record, season) if len({c["source"] for c in cands}) > 1 else None
    distinct = {(c["key"], c["version"]) for c in cands}
    if len(distinct) > 1:
        # Hunter x Hunter "Saison 1": the Anime-Sama remake or the VoirAnime original, told by the hosts played
        cands = [c for c in cands if c["source"] == host]
        distinct = {(c["key"], c["version"]) for c in cands}
    if len(distinct) != 1:
        return None
    return next((c for c in cands if c["source"] == host), cands[0])


def _next_target(record: dict, season: str, ep_id: str, ep: dict) -> Optional[Tuple[str, Optional[dict], bool, str]]:
    """(shown ep_id, shown episode, is_next, next title) of a candidate, or None when nothing is left to watch."""
    if not _finished(ep):
        return ep_id, ep, False, ""
    episodes = record.get("episodes") or {}
    cur_id, cur, seen = ep_id, ep, {ep_id}
    # A rewatch of episode 2 of a long legacy series (no `next` links) must still reach episode 80
    for _ in range(max(MAX_NEXT_HOPS, len(episodes) + 1)):
        nxt = cur.get("next")
        if not isinstance(nxt, dict) or not nxt.get("ep_id"):
            # No recorded successor: walk the stored N+1 (played or marked), never invent an unseen episode
            if not cur_id.isdecimal():
                return None
            succ_id = str(int(cur_id) + 1)
            succ = episodes.get(f"{season}:{succ_id}")
            if succ_id in seen or not isinstance(succ, dict) or not (_played(succ) or succ.get("watched")):
                return None
            seen.add(succ_id)
            if not _finished(succ):
                return (succ_id, succ, False, "") if _played(succ) else None
            cur_id, cur = succ_id, succ
            continue
        nid = str(nxt["ep_id"])
        if nid in seen:
            return None
        seen.add(nid)
        n = episodes.get(f"{season}:{nid}")
        if not isinstance(n, dict) or not (_played(n) or n.get("watched")):
            return nid, n, True, nxt.get("title") or ""
        if not _finished(n):
            return (nid, n, False, "") if _played(n) else (nid, n, True, nxt.get("title") or "")
        cur_id, cur = nid, n
    return None


def _season_id(title: str, record: dict, season: str) -> tuple:
    """(mapped key or None, season name, record title, host), names without their version word: VF and VOSTFR are one season."""
    mapping = (record.get("seasons") or {}).get(season)
    key = mapping.get("key") if isinstance(mapping, dict) else None
    return (key or None, normalize_title_key(_VERSION_WORD.sub(" ", season)),
            normalize_title_key(_VERSION_WORD.sub(" ", title)), _season_host(record, season))


def _is_covered(covered: set, sid: tuple) -> bool:
    key, name, base, host = sid
    for c_key, c_name, c_base, c_host in covered:
        if key and c_key:
            if key == c_key:  # 'Sousou No Frieren 2'/'Saison 1' is saison-2
                return True
        elif name == c_name and (base == c_base or (host and c_host and host != c_host)):
            # Unmapped legacy posts all say 'Saison 1': same name only counts for the same post in another
            # version, or for the same season played on the other source (VoirAnime -> Anime-Sama switch)
            return True
    return False


def _continue_item(title: str, record: dict, season: str, ep_id: str, ep: Optional[dict], is_next: bool,
                   next_title: str, activity: float, canonical=None, media=None) -> dict:
    ref = _link_of(record) or {}
    anime = client_ref(ref, canonical, media)
    mapping = (record.get("seasons") or {}).get(season)
    mapping = mapping if isinstance(mapping, dict) else {}
    ep = ep or {}
    file_path = ep.get("file_path") or ""
    wide = [f"/api/stream/thumbnail?file_path={quote(file_path, safe='')}"] if file_path else []
    names = {normalize_title_key(t) for t in (title, ref.get("title"), ref.get("entry_title")) if t} - {""}
    pos, dur = (0.0, 0.0) if is_next else (float(ep.get("position_sec") or 0), float(ep.get("duration_sec") or 0))
    return {
        "key": _group_key(title, record, canonical),
        "anime": anime,
        "anime_title": title,
        "display_title": (anime or {}).get("title") or title,
        "cover": client_cover_url(record.get("cover", "")),
        "wide_images": _dedup(wide + (anime["wide_images"] if anime else [])),
        "season": season,
        "season_key": mapping.get("key"),
        "source": mapping.get("source"),
        "version": mapping.get("version"),
        "episode_num": ep_id,
        "episode_title": _episode_title(ep.get("ep_title") or next_title, ep_id, names),
        "is_next": is_next,
        "position_sec": pos,
        "duration_sec": dur,
        "progress_percent": round((pos / dur) * 100, 1) if dur > 0 else 0,
        "remaining_sec": max(0.0, dur - pos) if dur > 0 else None,
        "watched": False if is_next else bool(ep.get("watched", False)),
        "last_watched_at": activity,
        "embed_url": ep.get("embed_url"),
        "file_path": ep.get("file_path"),
    }


class HistoryService:
    def __init__(self):
        os.makedirs(DATA_DIR, exist_ok=True)
        self.history = self._load()
        self._dirty = False
        self._flush_pending = False   # a flush task is sleeping (it has not started writing)
        self._flush_task: Optional[asyncio.Task] = None
        self._flush_loop = None
        self._closed = False
        self._seq = 0
        self._written_seq = 0
        self._write_lock = threading.Lock()
        self._link_tried: Dict[Tuple[str, str], float] = {}

    def _load(self) -> dict:
        data = load_json(HISTORY_FILE, dict)
        if not isinstance(data, dict):
            return {}
        # Backward compatibility migration:
        if data and not any(isinstance(v, dict) and "episodes" not in v for k, v in data.items()):
            first_val = next(iter(data.values()), {})
            if "episodes" in first_val or "last_season" in first_val:
                return {"default": data}
        return data

    # --- persistence ---
    def _save(self, immediate: bool = False):
        # Name kept: every mutation path calls it. Persistence is debounced (see _schedule_flush).
        self._dirty = True
        self._schedule_flush(0.0 if immediate else HISTORY_FLUSH_DELAY)

    def _schedule_flush(self, delay: Optional[float] = None):
        if self._closed:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            self.flush()  # no loop (unit tests, scripts): write now
            return
        delay = HISTORY_FLUSH_DELAY if delay is None else delay
        task = self._flush_task
        # A task of another loop never runs (TestClient serves each request in a short-lived loop)
        alive = task is not None and not task.done() and self._flush_loop is loop
        if self._flush_pending and alive:
            if delay > 0:
                return  # the sleeping task writes this change too
            task.cancel()  # an immediate save must not wait for the debounce window
        self._flush_pending = True
        self._flush_loop = loop
        self._flush_task = loop.create_task(self._flush_later(delay))

    async def _flush_later(self, delay: float):
        await asyncio.sleep(delay)
        self._flush_pending = False  # cleared before the write: a change during the write opens a new window
        await self._flush_async()

    def _snapshot(self) -> Tuple[str, int]:
        # On the loop thread, the only writer of self.history: the worker only receives a string
        text = json.dumps(self.history, ensure_ascii=False)
        self._seq += 1
        self._dirty = False
        return text, self._seq

    async def _flush_async(self):
        if not self._dirty:
            return
        try:
            text, seq = self._snapshot()
            await asyncio.to_thread(self._write, text, seq)
        except Exception as e:
            self._dirty = True
            print(f"[HistoryService] Error saving history DB: {e}")
        if self._dirty:
            self._schedule_flush()  # changed during the write, or the write failed

    def _write(self, text: str, seq: int):
        with self._write_lock:
            if seq <= self._written_seq:
                return  # an older snapshot never replaces a newer one
            save_json_text(HISTORY_FILE, text)
            self._written_seq = seq

    def _wait_for_writes(self):
        with self._write_lock:
            pass  # a write already in a worker thread holds the lock until its file is in place

    def flush(self):
        """Synchronous flush (no running loop)."""
        if not self._dirty:
            return
        try:
            text, seq = self._snapshot()
            self._write(text, seq)
        except Exception as e:
            self._dirty = True
            print(f"[HistoryService] Error saving history DB: {e}")

    async def close(self):
        """Final flush at shutdown (lifespan): only a pending change is written."""
        self._closed = True
        task = self._flush_task
        if task and not task.done() and self._flush_loop is asyncio.get_running_loop():
            if self._flush_pending:
                task.cancel()  # still sleeping: the write below replaces it
            else:
                await asyncio.gather(task, return_exceptions=True)  # writing: let it land
        self._flush_pending = False
        if self._dirty:
            # Never a forced write: an untouched state (maybe an unreadable file loaded as {}) must not
            # replace the file and rotate the good copy into .bak
            await self._flush_async()
        # A write started from another loop, or by a superseded task, may still run in a worker thread
        await asyncio.to_thread(self._wait_for_writes)

    # --- reads ---
    def get_history(self, user_id: str = "default") -> dict:
        uid = user_id or "default"
        return self.history.get(uid, {})

    def get_history_for_client(self, user_id: str = "default", canonical=None, media=None) -> dict:
        """Same as get_history, with covers rewritten to browser-loadable URLs and links in client form."""
        return {
            title: {**record, "cover": client_cover_url(record.get("cover", "")),
                    "anime": client_ref(record.get("anime"), canonical, media)}
            for title, record in self.get_history(user_id).items()
        }

    @staticmethod
    def _resolve_title(user_hist: dict, anime_title: str) -> str:
        """Existing record key for a title variant (accents, case, punctuation): keeps one record per anime."""
        if anime_title in user_hist:
            return anime_title
        wanted = normalize_title_key(anime_title)
        if wanted:
            for existing in user_hist:
                if normalize_title_key(existing) == wanted:
                    return existing
        return anime_title

    def get_anime_history(self, user_id: str, anime_title: str) -> dict:
        user_hist = self.get_history(user_id)
        return user_hist.get(self._resolve_title(user_hist, anime_title), {"episodes": {}})

    def find_record(self, user_id: str, title: str) -> Tuple[str, Optional[dict]]:
        user_hist = self.get_history(user_id)
        key = self._resolve_title(user_hist, title)
        record = user_hist.get(key)
        return key, record if isinstance(record, dict) else None

    # --- entity links ---
    @staticmethod
    def _clean_ref(anime: Optional[dict]) -> Optional[dict]:
        if not isinstance(anime, dict):
            return None
        eid = anime.get("id")
        if not isinstance(eid, str) or not eid.startswith("a-") or len(eid) > 500:
            return None  # a truncated id would name another entity
        url = anime.get("url").strip() if isinstance(anime.get("url"), str) else ""
        if len(url) > 500:
            url = ""  # a truncated url would name another page
        title = _text(anime.get("title"), 300)
        banner = anime.get("banner") if isinstance(anime.get("banner"), str) else ""
        return {
            "id": eid,
            "title": title,
            "source": _text(anime.get("source"), 32) if url else "",
            "url": url,
            # The title that drives /api/anime/lookup's key: only meaningful next to its url
            "entry_title": (_text(anime.get("entry_title"), 300) or title) if url else "",
            "banner": raw_cover_url(banner) if is_usable_cover(banner) and len(banner) <= 500 else None,
            "trailer": clean_trailer(anime.get("trailer")),
        }

    def _link(self, record: dict, ref: Optional[dict], by: str, canonical=None, idents: Optional[set] = None) -> bool:
        """Applies one link with the precedence index < details < write. Returns whether the record changed.

        idents: 'source:slug' of every entry the details describe (details passes only, see same_entity).
        """
        if not ref:
            return False
        old = _link_of(record)
        if old and same_entity(old, ref, canonical, idents):
            # Same entity: heal the id and refresh the snapshot, never lose a field or a stronger provenance
            merged = {**old, **{k: v for k, v in ref.items() if v}}
            merged["by"] = old.get("by") if LINK_RANK.get(old.get("by"), 0) > LINK_RANK[by] else by
        elif old:
            if not (by == "write" or (by == "details" and LINK_RANK.get(old.get("by"), 0) == LINK_RANK["index"])):
                return False
            merged = {**ref, "by": by}
            record["seasons"] = {}  # season keys belong to the old entity
        else:
            merged = {**ref, "by": by}
        if old and {k: v for k, v in old.items() if k != "at"} == {k: v for k, v in merged.items() if k != "at"}:
            return False
        merged["at"] = time.time()
        record["anime"] = merged
        return True

    def _map_season(self, record: dict, season: str, target: Optional[dict], by: str, live_keys: Optional[set] = None) -> bool:
        if not isinstance(target, dict):
            return False
        key, source, version = target.get("key"), target.get("source"), target.get("version")
        if not (isinstance(key, str) and 0 < len(key) <= 120 and source in SOURCES and version in VERSIONS):
            return False
        seasons = record.get("seasons") if isinstance(record.get("seasons"), dict) else {}
        current = seasons.get(season)
        if isinstance(current, dict) and current.get("by") == "write" and by == "details":
            # What the user played wins, unless the season it names no longer exists
            if live_keys is None or current.get("key") in live_keys:
                return False
        entry = {"key": key, "source": source, "version": version, "by": by}
        if current == entry:
            return False
        seasons[season] = entry
        record["seasons"] = seasons
        return True

    @staticmethod
    def _set_episode_meta(ep_record: dict, context: Optional[dict], next_ep: Optional[dict]):
        # Absent values never erase stored ones
        ep_title = _text((context or {}).get("ep_title"), 200)
        if ep_title:
            ep_record["ep_title"] = ep_title
        if isinstance(next_ep, dict):
            next_id = _text(next_ep.get("ep_id"), 32)
            if next_id:
                ep_record["next"] = {"ep_id": next_id, "title": _text(next_ep.get("title"), 200)}

    def _apply_context(self, record: dict, season: str, anime: Optional[dict], context: Optional[dict],
                       link_by: str, canonical=None) -> bool:
        ref = self._clean_ref(anime)
        if not ref:
            return False
        changed = self._link(record, ref, link_by, canonical)
        if same_anime(record.get("anime"), ref, canonical) and context and context.get("season_key"):
            changed |= self._map_season(record, season, {"key": context["season_key"], "source": context.get("source"),
                                                         "version": context.get("version")}, link_by)
        return changed

    @staticmethod
    def _upgrade_cover(record: dict, cover: str):
        if cover and not is_usable_cover(record.get("cover", "")):
            record["cover"] = cover

    # --- mutations ---
    def save_progress(
        self,
        user_id: str,
        anime_title: str,
        season: str,
        ep_id: str,
        position_sec: float,
        duration_sec: float,
        cover: Optional[str] = None,
        embed_url: Optional[str] = None,
        file_path: Optional[str] = None,
        anime: Optional[dict] = None,
        context: Optional[dict] = None,
        next_ep: Optional[dict] = None,
        link_by: str = "write",
        canonical=None
    ):
        if not anime_title or not ep_id:
            return

        # JS Infinity / NaN (live streams) arrive as null
        position_sec = float(position_sec or 0)
        duration_sec = float(duration_sec or 0)

        uid = user_id or "default"
        if uid not in self.history:
            self.history[uid] = {}

        user_hist = self.history[uid]
        anime_title = self._resolve_title(user_hist, anime_title)

        # Placeholders (data: URIs, via.placeholder) must never be stored as a cover
        cover = raw_cover_url(cover) if is_usable_cover(cover) else ""

        if anime_title not in user_hist:
            user_hist[anime_title] = {
                "anime_title": anime_title,
                "cover": cover,
                "last_season": season,
                "last_ep_id": ep_id,
                "last_updated": time.time(),
                "episodes": {}
            }

        anime_record = user_hist[anime_title]
        if cover and not is_usable_cover(anime_record.get("cover", "")):
            anime_record["cover"] = cover
        anime_record["last_season"] = season
        anime_record["last_ep_id"] = ep_id
        anime_record["last_updated"] = time.time()

        ep_key = f"{season}:{ep_id}"
        ep_record = anime_record["episodes"].get(ep_key, {})

        ep_record["position_sec"] = position_sec
        ep_record["duration_sec"] = duration_sec
        ep_record["last_watched_at"] = time.time()
        ep_record["played_at"] = ep_record["last_watched_at"]  # playback only (see _finished)
        if embed_url:
            ep_record["embed_url"] = embed_url
        if file_path:
            ep_record["file_path"] = file_path

        # Mark as watched if position >= 85% of duration
        if duration_sec > 0 and (position_sec / duration_sec) >= FINISHED_RATIO:
            ep_record["watched"] = True

        self._set_episode_meta(ep_record, context, next_ep)
        anime_record["episodes"][ep_key] = ep_record
        self._apply_context(anime_record, season, anime, context, link_by, canonical)
        self._save()
        return ep_record

    def toggle_watched(self, user_id: str, anime_title: str, season: str, ep_id: str, is_watched: bool = None,
                       anime: Optional[dict] = None, context: Optional[dict] = None, next_ep: Optional[dict] = None,
                       cover: Optional[str] = None, link_by: str = "write", canonical=None) -> bool:
        if not anime_title or not ep_id:
            return False

        uid = user_id or "default"
        if uid not in self.history:
            self.history[uid] = {}

        user_hist = self.history[uid]
        anime_title = self._resolve_title(user_hist, anime_title)
        cover = raw_cover_url(cover) if is_usable_cover(cover) else ""

        if anime_title not in user_hist:
            user_hist[anime_title] = {
                "anime_title": anime_title,
                "cover": cover,
                "last_season": season,
                "last_ep_id": ep_id,
                "last_updated": time.time(),
                "episodes": {}
            }

        anime_record = user_hist[anime_title]
        self._upgrade_cover(anime_record, cover)
        ep_key = f"{season}:{ep_id}"
        ep_record = anime_record["episodes"].get(ep_key, {})

        if is_watched is not None:
            ep_record["watched"] = is_watched
        else:
            ep_record["watched"] = not ep_record.get("watched", False)

        ep_record["last_watched_at"] = time.time()
        ep_record["watched_at"] = ep_record["last_watched_at"]  # marks only (see _finished)
        self._set_episode_meta(ep_record, context, next_ep)
        anime_record["episodes"][ep_key] = ep_record
        self._apply_context(anime_record, season, anime, context, link_by, canonical)
        self._save()
        return ep_record["watched"]

    def mark_season(self, user_id: str, anime_title: str, season: str, ep_ids: list, is_watched: bool = True,
                    anime: Optional[dict] = None, context: Optional[dict] = None, cover: Optional[str] = None,
                    link_by: str = "write", canonical=None):
        if not anime_title or not ep_ids:
            return

        uid = user_id or "default"
        if uid not in self.history:
            self.history[uid] = {}

        user_hist = self.history[uid]
        anime_title = self._resolve_title(user_hist, anime_title)
        cover = raw_cover_url(cover) if is_usable_cover(cover) else ""

        if anime_title not in user_hist:
            user_hist[anime_title] = {
                "anime_title": anime_title,
                "cover": cover,
                "last_season": season,
                "last_ep_id": ep_ids[0] if ep_ids else "1",
                "last_updated": time.time(),
                "episodes": {}
            }

        anime_record = user_hist[anime_title]
        self._upgrade_cover(anime_record, cover)
        for ep_id in ep_ids:
            ep_key = f"{season}:{ep_id}"
            ep_record = anime_record["episodes"].get(ep_key, {})
            ep_record["watched"] = is_watched
            ep_record["last_watched_at"] = time.time()
            ep_record["watched_at"] = ep_record["last_watched_at"]
            anime_record["episodes"][ep_key] = ep_record

        self._apply_context(anime_record, season, anime, context, link_by, canonical)
        self._save()

    # --- legacy linking (labels only: nothing is moved, merged or renamed) ---
    def link_titles(self, user_id: str, ref: dict, claims: Dict[Tuple[str, str], List[dict]], canonical=None,
                    idents: Optional[set] = None) -> int:
        """Links this profile's records named by a details payload (title AND season evidence).

        idents (gateway.entry_idents): a record whose primary entry is not among them is another work.
        """
        ref = self._clean_ref(ref)
        if not ref or not claims:
            return 0
        titles = {tk for tk, _ in claims}
        live_keys = {t["key"] for ts in claims.values() for t in ts}
        changed_records = 0
        for stored_title, record in self.get_history(user_id).items():
            if not isinstance(record, dict):
                continue
            tk = normalize_title_key(stored_title)
            if tk not in titles:
                continue
            seasons_present = {_split_ep_key(k, record)[0] for k in record.get("episodes") or {}}
            matched = {s: claims[(tk, s)] for s in seasons_present if (tk, s) in claims}
            if not matched:
                continue  # title evidence without season evidence never links
            changed = self._link(record, ref, "details", canonical, idents)
            if same_entity(record.get("anime"), ref, canonical, idents):
                for season, cands in matched.items():
                    target = _pick_claim(cands, record, season)
                    if target:
                        changed |= self._map_season(record, season, target, "details", live_keys)
            changed_records += changed
        if changed_records:
            self._save()
        return changed_records

    def unlinked_titles(self, user_id: str) -> List[Tuple[str, str, List[str]]]:
        """(title, raw cover, VoirAnime episode urls) of the records the index pass may try now."""
        uid = user_id or "default"
        now = time.time()
        pending = []
        for title, record in self.get_history(uid).items():
            if not isinstance(record, dict) or _link_of(record):
                continue
            tried = self._link_tried.get((uid, title))
            if tried is not None and now - tried < LINK_RETRY:
                continue
            self._link_tried[(uid, title)] = now
            urls = []
            for ep in (record.get("episodes") or {}).values():
                url = ep.get("embed_url") if isinstance(ep, dict) else None
                if isinstance(url, str) and "voir-anime" in (url_host(url) or "") and url not in urls:
                    urls.append(url)
                    if len(urls) >= 5:
                        break
            cover = record.get("cover")
            pending.append((title, cover if isinstance(cover, str) else "", urls))
        return pending

    def apply_links(self, user_id: str, links: Dict[str, dict]) -> int:
        """Index links (background pass): only records that are still unlinked."""
        user_hist = self.get_history(user_id)
        changed = 0
        for title, ref in (links or {}).items():
            record = user_hist.get(title)
            if isinstance(record, dict) and not _link_of(record):
                changed += self._link(record, self._clean_ref(ref), "index")
        if changed:
            self._save()
        return changed

    def relabel(self, user_id: str, title: str, anime_id: str) -> bool:
        """Heals a link whose id stopped resolving (provenance kept). Its season mapping is dropped."""
        record = self.get_history(user_id).get(title)
        ref = _link_of(record) if isinstance(record, dict) else None
        if not ref or not isinstance(anime_id, str) or not anime_id.startswith("a-") or len(anime_id) > 500 or ref["id"] == anime_id:
            return False
        ref["id"] = anime_id
        ref["at"] = time.time()
        # Season keys belong to the entity that issued them: 'saison-1' of the new one can be another season
        record["seasons"] = {}
        self._save()
        return True

    # --- shelves & stats ---
    def get_continue_watching(self, user_id: str, canonical=None, media=None) -> List[dict]:
        """One card per anime, from playback only: the last played episode, or the recorded next one."""
        user_hist = self.get_history(user_id)
        cards = []
        for titles in _group_titles(user_hist, canonical):
            candidates = []
            for title in titles:
                pointer = _pointer(user_hist[title])
                if pointer:
                    candidates.append((float(user_hist[title].get("last_updated") or 0), title, pointer))
            # Most recent record first; an older record of the same anime still counts when the newer one is done,
            # unless its pointer is in a season a newer record already played or marked (watched there: VA -> AS switch)
            candidates.sort(key=lambda c: c[0], reverse=True)
            covered: set = set()
            for activity, title, (season, ep_id, ep) in candidates:
                record = user_hist[title]
                if _is_covered(covered, _season_id(title, record, season)):
                    continue
                target = _next_target(record, season, ep_id, ep)
                if not target or (target[2] and not _link_of(record)):
                    # Nothing left here (a next card cannot be played without its anime): its seasons are settled
                    covered |= {_season_id(title, record, _split_ep_key(k, record)[0])
                                for k, e in (record.get("episodes") or {}).items()
                                if isinstance(e, dict) and (_played(e) or e.get("watched"))}
                    continue
                shown_id, shown, is_next, next_title = target
                cards.append(_continue_item(title, record, season, shown_id, shown, is_next, next_title, activity,
                                            canonical, media))
                break

        cards.sort(key=lambda x: x["last_watched_at"], reverse=True)
        return cards

    def get_user_stats(self, user_id: str, canonical=None) -> dict:
        """Calculates viewing statistics for the user."""
        user_hist = self.get_history(user_id)
        total_seconds_watched = 0
        total_episodes_watched = 0
        watched_by_title = {}

        for anime_title, record in user_hist.items():
            episodes = record.get("episodes", {})
            anime_watched_count = 0
            for ep_key, ep in episodes.items():
                if ep.get("watched"):
                    total_episodes_watched += 1
                    anime_watched_count += 1
                    dur = ep.get("duration_sec", 1440)  # default 24 min if unknown
                    total_seconds_watched += dur
                else:
                    pos = ep.get("position_sec", 0)
                    total_seconds_watched += pos
            watched_by_title[anime_title] = anime_watched_count

        # One anime saved under several legacy titles counts once
        groups = _group_titles(user_hist, canonical)
        total_animes_started = len(groups)
        # If at least 12 episodes watched or marked completed
        animes_completed = sum(1 for titles in groups if sum(watched_by_title.get(t, 0) for t in titles) >= 12)

        hours = int(total_seconds_watched // 3600)
        minutes = int((total_seconds_watched % 3600) // 60)

        return {
            "total_seconds_watched": round(total_seconds_watched),
            "watch_time_formatted": f"{hours}h {minutes}m" if hours > 0 else f"{minutes}m",
            "total_episodes_watched": total_episodes_watched,
            "total_animes_started": total_animes_started,
            "animes_completed": animes_completed,
            "animes_in_progress": max(0, total_animes_started - animes_completed)
        }

    # --- deletes ---
    def delete_item(self, user_id: str, anime_title: str, ep_key: Optional[str] = None):
        """Removes a specific episode or an entire anime from the user's watch history."""
        uid = user_id or "default"
        if uid in self.history:
            anime_title = self._resolve_title(self.history[uid], anime_title)
        if uid in self.history and anime_title in self.history[uid]:
            if ep_key:
                record = self.history[uid][anime_title]
                eps = record.get("episodes", {})
                if ep_key in eps:
                    del eps[ep_key]
                    if eps and ep_key == f"{record.get('last_season', 'Saison 1')}:{record.get('last_ep_id', '1')}":
                        # The continue card follows the pointer: move it to the last played episode left
                        last = _last_played(eps)
                        if last:
                            record["last_season"], record["last_ep_id"] = _split_ep_key(last[0], record)
                if not eps:
                    del self.history[uid][anime_title]
            else:
                del self.history[uid][anime_title]
            self._save()

    def clear_user_history(self, user_id: str):
        """Clears all watch history records for a given user."""
        uid = user_id or "default"
        if uid in self.history:
            self.history[uid] = {}
            self._save(immediate=True)

    def delete_user_data(self, user_id: str):
        """Removes a deleted profile's whole history (written at once, not after the debounce window)."""
        uid = user_id or "default"
        removed = self.history.pop(uid, None)
        for key in [k for k in self._link_tried if k[0] == uid]:
            del self._link_tried[key]
        if removed is not None:
            self._save(immediate=True)

history_service = HistoryService()

