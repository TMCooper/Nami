import os
import json
import threading
from typing import Optional

from backend.services.cover_utils import normalize_title_key, raw_cover_url, is_usable_cover, is_trusted_cover
from backend.services.storage import load_json, save_json
from backend.services.update_service import VOIRANIME_PATH

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data")
REGISTRY_FILE = os.path.join(DATA_DIR, "cache", "covers.json")


class CoverRegistry:
    """Nami-owned cover store keyed by source + normalized title.

    voiranime_API's own covers.json is read as an extra, read-only input: Nami no longer
    writes into it (both processes overwrote each other's entries).
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._covers: dict = load_json(REGISTRY_FILE, dict)
        self._va_index: dict = {}
        self._va_mtime: Optional[float] = None

    @staticmethod
    def _key(source: str, title: str) -> str:
        return f"{source or 'any'}|{normalize_title_key(title)}"

    def lookup(self, title: str, source: str = "voiranime") -> str:
        if not normalize_title_key(title):
            return ""
        with self._lock:
            cover = self._covers.get(self._key(source, title), "")
        if cover:
            return cover
        if source == "voiranime":
            return self._lookup_voiranime_file(title)
        return ""

    def register(self, title: str, cover: str, source: str = "voiranime"):
        raw = raw_cover_url(cover)
        if not normalize_title_key(title) or not is_usable_cover(raw) or raw.startswith("/api/"):
            return
        key = self._key(source, title)
        with self._lock:
            if self._covers.get(key) == raw:
                return
            self._covers[key] = raw
            snapshot = dict(self._covers)
        try:
            save_json(REGISTRY_FILE, snapshot)
        except OSError as e:
            # The in-memory entry still serves lookups; it is persisted with the next successful save
            print(f"[CoverRegistry] Save failed: {e}")

    def _lookup_voiranime_file(self, title: str) -> str:
        path = os.path.join(VOIRANIME_PATH, "data", "covers.json")
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            return ""
        with self._lock:
            if mtime != self._va_mtime:
                # Foreign file, rewritten in place by voiranime_API: plain read, never quarantined;
                # a read that hits a rewrite keeps the previous index and is retried next time
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                except (OSError, ValueError):
                    return self._va_index.get(normalize_title_key(title), "")
                index = {}
                if isinstance(data, dict):
                    for name, cover in data.items():
                        raw = raw_cover_url(cover) if isinstance(cover, str) else ""
                        key = normalize_title_key(name)
                        if key and is_usable_cover(raw) and is_trusted_cover(raw, "voiranime"):
                            index.setdefault(key, raw)
                self._va_index = index
                self._va_mtime = mtime
            return self._va_index.get(normalize_title_key(title), "")


cover_registry = CoverRegistry()
