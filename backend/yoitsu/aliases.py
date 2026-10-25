import threading
from typing import Iterable, List, Optional, Set

from backend.services.storage import load_json, save_json
from backend.yoitsu.normalize import is_valid_key, title_key

# Known cross-source / cross-language names (seeded from the former CANONICAL_ALIASES table)
SEED_GROUPS: List[List[str]] = [
    ["spice and wolf", "spice wolf", "ookami to koushinryou", "ookami to koushinryu"],
    ["attack on titan", "l attaque des titans", "lattaque des titans", "shingeki no kyojin"],
    ["frieren", "sousou no frieren", "frieren beyond journey s end", "frieren beyond journeys end", "frieren at the funeral"],
    ["redo of healer", "kaifuku jutsushi no yarinaoshi"],
    ["high school dxd", "high school dxd new", "high school dxd born", "high school dxd hero"],
]


def _digit_key(key: str) -> bool:
    return len(key.replace(" ", "")) >= 2 and key.replace(" ", "").isdigit()


class AliasIndex:
    """Union-find over title keys that name the same franchise.

    A merge keeps the anchor's root when one is given (the entity being enriched keeps its
    id), otherwise the lexicographically smallest root. Entity ids built from any member keep
    resolving after merges (find() follows the union). Learned groups are persisted by flush().
    """

    def __init__(self, path: str, seed_groups: Iterable[Iterable[str]] = SEED_GROUPS):
        self._path = path
        self._lock = threading.RLock()
        self._parent: dict = {}
        self.version = 0
        self._dirty = False
        for group in seed_groups:
            self._union([title_key(k) for k in group])
        stored = load_json(path, list)
        for group in stored if isinstance(stored, list) else []:
            if isinstance(group, list) and group:
                keys = [k for k in group if isinstance(k, str)]
                self._union(keys, anchor=keys[0])  # groups are stored root first

    def _find(self, key: str) -> str:
        root = key
        while self._parent.get(root, root) != root:
            root = self._parent[root]
        while self._parent.get(key, key) != root:  # path compression
            self._parent[key], key = root, self._parent[key]
        return root

    def _union(self, keys: Iterable[str], anchor: Optional[str] = None) -> bool:
        keys = list(keys)
        named = any(is_valid_key(k) for k in keys)
        # Digit-only names ("86") only join a group that also has a real name
        valid = [k for k in keys if is_valid_key(k) or (named and _digit_key(k))]
        if len(valid) < 2:
            for k in valid:
                self._parent.setdefault(k, k)
            return False
        changed = False
        for k in valid:
            if k not in self._parent:
                self._parent[k] = k
                changed = True
        roots = {self._find(k) for k in valid}
        if len(roots) > 1:
            target = self._find(anchor) if anchor in self._parent else min(roots)
            for r in roots:
                if r != target:
                    self._parent[r] = target
            changed = True
        return changed

    def find(self, key: str) -> str:
        with self._lock:
            return self._find(key) if key in self._parent else key

    def known(self, key: str) -> bool:
        with self._lock:
            return key in self._parent

    def same(self, a: str, b: str) -> bool:
        return self.find(a) == self.find(b)

    def members(self, key: str) -> Set[str]:
        with self._lock:
            root = self.find(key)
            return {k for k in self._parent if self._find(k) == root} or {key}

    def union(self, keys: Iterable[str], anchor: Optional[str] = None) -> str:
        """Declares that keys name one franchise; returns the canonical key. No I/O (see flush)."""
        keys = list(keys)
        with self._lock:
            if self._union(keys, anchor=anchor):
                self.version += 1
                self._dirty = True
            first = anchor if anchor else next((k for k in keys if is_valid_key(k)), keys[0] if keys else "")
            return self.find(first)

    def flush(self):
        with self._lock:
            if not self._dirty:
                return
            snapshot = self._groups()
            self._dirty = False
        try:
            save_json(self._path, snapshot, indent=None)
        except OSError as e:
            self._dirty = True
            print(f"[AliasIndex] Save failed: {e}")

    def _groups(self) -> list:
        groups: dict = {}
        for k in self._parent:
            groups.setdefault(self._find(k), []).append(k)
        # Root first so the canonical (entity id) survives a reload
        return sorted([root] + sorted(k for k in g if k != root) for root, g in groups.items() if len(g) > 1)
