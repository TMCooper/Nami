import os
import time
from typing import Optional, List
from backend.services.storage import load_json, save_json
from backend.services.cover_utils import raw_cover_url, is_usable_cover, client_cover_url
from backend.services.anime_refs import identity_keys, primary_ident, same_anime, same_entity, clean_trailer, trailer_thumb

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data")
WATCHLIST_FILE = os.path.join(DATA_DIR, "watchlist.json")
MAX_ITEMS = 500
MAX_FALLBACKS = 4
MAX_SOURCES = 4
MAX_ALT_TITLES = 5
MAX_INPUT_ITEMS = 20        # list inputs are cut before any processing (no-auth app: any client can post)
MAX_IMAGE_URL = 500         # like history banners: a longer cover is dropped, never truncated
# What a details view heals on a saved item (covers, banner and trailer only when the new value is known)
REFRESHED_FIELDS = ("id", "title", "alt_titles", "source", "url", "entry_title", "sources")


def _text(value, limit: int) -> str:
    return value.strip()[:limit] if isinstance(value, str) else ""


def _dedup(items) -> list:
    return list(dict.fromkeys(i for i in items if i))


def _list(value) -> list:
    return value[:MAX_INPUT_ITEMS] if isinstance(value, list) else []


def _image(value) -> str:
    """Raw form of a usable cover / banner value, '' otherwise (checked raw: a proxied value is longer)."""
    if not isinstance(value, str) or len(value) > 3 * MAX_IMAGE_URL or not is_usable_cover(value):
        return ""
    raw = raw_cover_url(value)
    return raw if len(raw) <= MAX_IMAGE_URL else ""


class WatchlistService:
    """« À regarder plus tard »: per-profile snapshots, so shelves render without any details call."""

    def __init__(self):
        os.makedirs(DATA_DIR, exist_ok=True)
        self.items = self._load()

    def _load(self) -> dict:
        data = load_json(WATCHLIST_FILE, dict)
        if not isinstance(data, dict):
            return {}
        # A hand-edited or foreign file never breaks the shelves: keep only well-formed items
        return {
            uid: [i for i in items if isinstance(i, dict) and i.get("title") and i.get("url")]
            for uid, items in data.items() if isinstance(items, list)
        }

    def _save(self):
        try:
            save_json(WATCHLIST_FILE, self.items)
        except Exception as e:
            print(f"[WatchlistService] Error saving watchlist DB: {e}")

    @staticmethod
    def _snapshot(anime: dict) -> Optional[dict]:
        """Stored form of an anime card / details payload (raw covers, capped lists); None without title/source/url."""
        if not isinstance(anime, dict):
            return None
        title, source, url = _text(anime.get("title"), 300), _text(anime.get("source"), 32), _text(anime.get("url"), 500)
        if not (title and source and url):
            return None
        covers = _dedup(_image(c) for c in [anime.get("cover"), *_list(anime.get("cover_fallbacks"))])
        sources = [
            {"source": _text(s.get("source"), 32), "url": _text(s.get("url"), 500), "title": _text(s.get("title"), 300)}
            for s in _list(anime.get("sources")) if isinstance(s, dict)
        ]
        sources = [s for s in sources if s["source"] and s["url"]][:MAX_SOURCES]
        alt_titles = [t for t in _dedup(_text(t, 300) for t in _list(anime.get("alt_titles"))) if t != title]
        return {
            "id": _text(anime.get("id"), 500),
            "title": title,
            "alt_titles": alt_titles[:MAX_ALT_TITLES],
            "cover": covers[0] if covers else "",
            "cover_fallbacks": covers[1:1 + MAX_FALLBACKS],
            "banner": _image(anime.get("banner")) or None,
            "trailer": clean_trailer(anime.get("trailer")),
            "source": source,
            "url": url,
            "entry_title": _text(anime.get("entry_title"), 300) or (sources[0]["title"] if sources else "") or title,
            "sources": sources,
        }

    @staticmethod
    def _client_item(item: dict, canonical=None) -> dict:
        eid = item.get("id") or ""
        fallbacks = [client_cover_url(c) for c in item.get("cover_fallbacks") or []]
        banner = client_cover_url(item.get("banner") or "")
        return {
            **item,
            "id": (canonical(eid) if canonical and eid else eid) or eid,
            "cover": client_cover_url(item.get("cover") or ""),
            "cover_fallbacks": [c for c in fallbacks if c],
            "banner": banner or None,
            "wide_images": _dedup([banner, trailer_thumb(item.get("trailer"))]),
        }

    def get_items_for_client(self, user_id: str, canonical=None) -> List[dict]:
        """Newest first. Duplicates (same anime under an old id) are skipped in the response only, never saved."""
        seen = set()
        out = []
        for item in sorted(self.items.get(user_id or "default", []), key=lambda i: i.get("added_at") or 0, reverse=True):
            keys = identity_keys(item, canonical)
            if keys & seen:
                continue
            seen |= keys
            out.append(self._client_item(item, canonical))
        return out

    def add(self, user_id: str, anime: dict, added_at: Optional[float] = None, canonical=None) -> bool:
        snap = self._snapshot(anime)
        if not snap or not snap["id"].startswith("a-"):
            return False
        uid = user_id or "default"
        items = self.items.setdefault(uid, [])
        now = time.time()
        restored = min(added_at, now) if added_at and added_at > 0 else None
        match = next((i for i in items if same_anime(i, snap, canonical)), None)
        if match:
            # Re-added under a new id or from another card: one item, updated in place (an empty banner keeps the old one)
            match.update({k: v for k, v in snap.items() if v})
            if restored:
                match["added_at"] = restored
        else:
            items.append({**snap, "added_at": restored or now})
        items.sort(key=lambda i: i.get("added_at") or 0, reverse=True)
        del items[MAX_ITEMS:]
        self._save()
        return True

    def remove(self, user_id: str, anime_id: str = "", source: str = "", url: str = "", canonical=None) -> bool:
        uid = user_id or "default"
        items = self.items.get(uid)
        if not items:
            return False
        probe = {"id": anime_id, "source": source, "url": url}
        kept = [i for i in items if not same_anime(i, probe, canonical)]
        if len(kept) == len(items):
            return False
        self.items[uid] = kept
        self._save()
        return True

    def refresh(self, user_id: str, details: dict, canonical=None, idents: Optional[set] = None) -> bool:
        """Heals the saved items of one anime from its details (id, title, covers, sources); saves only on change.

        idents (gateway.entry_idents): an item whose primary entry is not among them is another work that
        shares the id (homonymous page) and is left untouched. Default: the details' own sources.
        """
        items = self.items.get(user_id or "default")
        if not items or not isinstance(details, dict):
            return False
        sources = details.get("sources") or [{}]
        snap = self._snapshot({**details, "entry_title": sources[0].get("title") if isinstance(sources[0], dict) else ""})
        if not snap or not snap["id"].startswith("a-"):
            return False
        if idents is None:
            idents = {primary_ident(s) for s in [snap, *snap["sources"]]} - {""}
        changed = False
        for index, item in enumerate(items):
            if not same_entity(item, snap, canonical, idents):
                continue
            updated = {**item, **{k: snap[k] for k in REFRESHED_FIELDS}}
            if snap["cover"]:
                # A details build without cover (VoirAnime API down) never erases the saved one
                updated["cover"], updated["cover_fallbacks"] = snap["cover"], snap["cover_fallbacks"]
            for k in ("banner", "trailer"):
                if snap[k]:
                    updated[k] = snap[k]
            if updated != item:
                items[index] = updated
                changed = True
        if changed:
            self._save()
        return changed

    def delete_user_data(self, user_id: str):
        if self.items.pop(user_id or "default", None) is not None:
            self._save()

watchlist_service = WatchlistService()
