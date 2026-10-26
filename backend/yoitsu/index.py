"""Groups source entries (Anime-Sama franchises, VoirAnime season/version posts) into one entity per anime.

Rules:
- an Anime-Sama page is a work: only strong season suffixes are stripped from its title, and
  two pages with the same title stay apart (the second one gets its slug in its key);
- a VoirAnime post joins the Anime-Sama page that has exactly its name, else its franchise
  root (weak suffixes and ": subtitle" stripped with sibling evidence, see normalize.py);
- learned aliases always win (AliasIndex).
"""
import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Tuple
from urllib.parse import quote, unquote

from backend.services.cover_utils import is_usable_cover, is_trusted_cover
from backend.services.storage import load_json, save_json
from backend.yoitsu.aliases import AliasIndex
from backend.yoitsu.normalize import franchise_of, slug_of, split_version, strong_root, title_key, is_valid_key

SOURCE_ORDER = ("anime_sama", "voiranime")   # display title, cover and default source preference
MAX_REMEMBERED = 20000
ENTITY_PREFIX = "a-"


@dataclass(frozen=True)
class Entry:
    source: str
    url: str
    title: str
    cover: str = ""
    slug: str = field(init=False, compare=False, repr=False)

    def __post_init__(self):
        object.__setattr__(self, "slug", slug_of(self.url))

    @property
    def ident(self) -> Tuple[str, str]:
        return (self.source, self.slug)

    @property
    def is_vf(self) -> bool:
        return split_version(self.title)[1] == "vf" or self.slug.endswith("-vf")

    def to_dict(self) -> dict:
        return {"source": self.source, "url": self.url, "title": self.title, "cover": self.cover}


def entry_rank(e: Entry) -> tuple:
    """Root post first: shortest title, VOSTFR before VF."""
    return (len(split_version(e.title)[0]), e.is_vf)


def entity_id(key: str) -> str:
    return ENTITY_PREFIX + quote(key.replace(" ", "-"), safe="-")


def key_from_entity_id(eid: str) -> str:
    raw = eid[len(ENTITY_PREFIX):] if eid.startswith(ENTITY_PREFIX) else eid
    return unquote(raw).replace("-", " ")


def _exact_key(title: str) -> str:
    return strong_root(title_key(split_version(title)[0]))[0]


def _richer(old: str, new: str) -> str:
    """Keeps the raw title when the other one is the same name with ':' / ' - ' stripped (VoirAnime catalogue)."""
    if title_key(old) == title_key(new):
        punct = lambda t: t.count(":") + t.count(" - ")
        return old if punct(old) > punct(new) else new
    return new


class EntityIndex:
    def __init__(self, aliases: AliasIndex, store_path: str):
        self.aliases = aliases
        self._store_path = store_path
        self._lock = threading.RLock()
        self._remembered: "OrderedDict[Tuple[str, str], Entry]" = OrderedDict()
        self._catalog: Dict[Tuple[str, str], Entry] = {}
        self._catalog_keys: set = set()
        self._as_slugs: Dict[str, set] = {}         # Anime-Sama exact key -> page slugs
        self._canon_cache: Dict[Tuple[str, str], str] = {}
        self._canon_version = -1
        self._dirty = False
        self.catalog_loaded = False
        stored = load_json(store_path, list)
        for item in stored if isinstance(stored, list) else []:
            if isinstance(item, dict) and item.get("url") and item.get("title"):
                e = Entry(item.get("source", "anime_sama"), item["url"], item["title"], item.get("cover", ""))
                self._remembered[e.ident] = e
                self._note_as(e)

    # --- known entries ---
    def _note_as(self, e: Entry):
        if e.source == "anime_sama" and e.slug:
            slugs = self._as_slugs.setdefault(_exact_key(e.title), set())
            if e.slug not in slugs:
                # A new page can take VoirAnime posts with its exact name, or split a title in two works
                slugs.add(e.slug)
                self._canon_cache.clear()

    def set_catalog(self, entries: Iterable[Entry]):
        catalog = {e.ident: e for e in entries if e.slug}
        keys = {title_key(split_version(e.title)[0]) for e in catalog.values()}
        with self._lock:
            self._catalog = catalog
            self._catalog_keys = keys
            for e in catalog.values():
                self._note_as(e)
            self._canon_cache.clear()
            self.catalog_loaded = True

    def knows(self, ident: Tuple[str, str]) -> bool:
        with self._lock:
            return ident in self._remembered or ident in self._catalog

    def remember(self, entries: Iterable[Entry]):
        with self._lock:
            for e in entries:
                if not e.slug or not e.title:
                    continue
                prev = self._remembered.get(e.ident)
                if prev is not None:
                    self._remembered.move_to_end(e.ident)
                    e = Entry(e.source, e.url, _richer(prev.title, e.title), e.cover or prev.cover)
                    if e == prev:
                        continue
                    self._canon_cache.pop(e.ident, None)
                self._remembered[e.ident] = e
                self._note_as(e)
                self._dirty = True
            while len(self._remembered) > MAX_REMEMBERED:
                self._remembered.popitem(last=False)
                self._dirty = True

    def flush(self):
        """Persists remembered entries (called from a debounced background task)."""
        with self._lock:
            if not self._dirty:
                return
            items = list(self._remembered.values())
            self._dirty = False
        try:
            save_json(self._store_path, [e.to_dict() for e in items], indent=None)
        except OSError as e:
            self._dirty = True
            print(f"[EntityIndex] Save failed: {e}")

    @property
    def dirty(self) -> bool:
        return self._dirty

    def all_entries(self) -> List[Entry]:
        with self._lock:
            merged = dict(self._remembered)
            for ident, cat in self._catalog.items():
                mem = merged.get(ident)
                if mem is None:
                    merged[ident] = cat
                else:
                    # The catalogue title is the source's own name for the page (stable history key);
                    # a remembered raw VoirAnime title only wins when it is the same name with ':' kept
                    merged[ident] = Entry(cat.source, cat.url, _richer(mem.title, cat.title), cat.cover or mem.cover)
            return list(merged.values())

    def entry(self, ident: Tuple[str, str]) -> Optional[Entry]:
        with self._lock:
            return self._catalog.get(ident) or self._remembered.get(ident)

    # --- franchise keys ---
    def _known(self, root: str, siblings: set) -> bool:
        return root in siblings or root in self._catalog_keys or self.aliases.known(root)

    def canonical_key(self, entry: Entry, siblings: Optional[set] = None) -> str:
        exact = _exact_key(entry.title)
        if entry.source == "anime_sama":
            slugs = self._as_slugs.get(exact, set())
            # Two Anime-Sama pages with the same title are two works: the extra one keys on its slug
            if len(slugs) > 1 and entry.slug != min(slugs, key=lambda s: (len(s), s)):
                return f"{exact} {entry.slug.replace('-', ' ')}"
            return self.aliases.find(exact)
        if self.aliases.known(exact) or exact in self._as_slugs:
            return self.aliases.find(exact)
        key, _ = franchise_of(entry.title, lambda r: self._known(r, siblings or set()))
        return self.aliases.find(key)

    def _cached_canonical(self, entry: Entry) -> str:
        with self._lock:
            if self._canon_version != self.aliases.version:
                self._canon_cache.clear()
                self._canon_version = self.aliases.version
            cached = self._canon_cache.get(entry.ident)
            if cached is None:
                cached = self.canonical_key(entry)
                self._canon_cache[entry.ident] = cached
            return cached

    def entries_for(self, eid: str) -> List[Entry]:
        """Every known entry (catalogue snapshot + remembered search results) of an entity. CPU-bound: run off the loop."""
        wanted = self.aliases.find(key_from_entity_id(eid))
        return [e for e in self.all_entries() if self._cached_canonical(e) == wanted]

    def members_of(self, keys: set) -> Dict[str, List[Entry]]:
        """Entries of several entities in one pass (same canonical as entries_for). CPU-bound: run off the loop."""
        out = {k: [] for k in keys}
        if keys:
            for e in self.all_entries():
                k = self._cached_canonical(e)
                if k in out:
                    out[k].append(e)
        return out

    def foreign_as_keys(self, canonical: str) -> set:
        """Anime-Sama page names that belong to other entities (never learned as aliases of this one)."""
        with self._lock:
            keys = list(self._as_slugs)
        return {k for k in keys if self.aliases.find(k) != canonical}

    def entry_keys(self) -> set:
        """Names of every known entry (alias learning is restricted to names that link existing entries)."""
        return {title_key(split_version(e.title)[0]) for e in self.all_entries()}

    # --- grouping ---
    def group(self, entries: List[Entry]) -> List[dict]:
        """One entity per franchise, in first-seen order (search relevance is kept)."""
        siblings = {title_key(split_version(e.title)[0]) for e in entries}
        with self._lock:
            for e in entries:
                self._note_as(e)  # pages listed together must be told apart even when not remembered
        groups: "OrderedDict[str, List[Entry]]" = OrderedDict()
        seen = set()
        for e in entries:
            if not e.slug or e.ident in seen:
                continue
            seen.add(e.ident)
            groups.setdefault(self.canonical_key(e, siblings), []).append(e)
        return [build_entity(key, members) for key, members in groups.items()]


def _display_title(members: List[Entry]) -> str:
    for source in SOURCE_ORDER:
        same_source = [m for m in members if m.source == source]
        if same_source:
            # The root post is usually the franchise name ("Sousou no Frieren" before "... 2 (VF)")
            return split_version(min(same_source, key=entry_rank).title)[0]
    return split_version(members[0].title)[0]


def build_entity(key: str, members: List[Entry]) -> dict:
    ordered = sorted(members, key=lambda m: SOURCE_ORDER.index(m.source) if m.source in SOURCE_ORDER else 9)
    title = _display_title(ordered)
    alt_titles = []
    for m in ordered:
        t = split_version(m.title)[0]
        if t != title and t not in alt_titles:
            alt_titles.append(t)

    covers = [m.cover for m in ordered if is_usable_cover(m.cover) and is_trusted_cover(m.cover, m.source)]
    primary_by_source: Dict[str, Entry] = {}
    for m in ordered:
        current = primary_by_source.get(m.source)
        # The root post (shortest title, VOSTFR first) is the best entry point of a source
        if current is None or entry_rank(m) < entry_rank(current):
            primary_by_source[m.source] = m
    sources = [
        {"source": s, "url": e.url, "title": split_version(e.title)[0]}
        for s, e in sorted(primary_by_source.items(), key=lambda kv: SOURCE_ORDER.index(kv[0]) if kv[0] in SOURCE_ORDER else 9)
    ]
    primary = sources[0] if sources else {"source": ordered[0].source, "url": ordered[0].url}
    return {
        "id": entity_id(key),
        "key": key,
        "title": title,
        "alt_titles": alt_titles,
        "cover": covers[0] if covers else "",
        "cover_fallbacks": list(dict.fromkeys(covers[1:])),
        "source": primary["source"],
        "url": primary["url"],
        "sources": sources,
        "entries": len(members),
    }
