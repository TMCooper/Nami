"""Single title/season normalizer shared by grouping, alias lookups and season merging.

Titles are compared through keys (accent-folded, casefolded, punctuation-free, see
normalize_title_key). Season suffixes are split in two families:
- strong ("Saison 2", "2nd Season", "Final Season", "Part 2"): always stripped;
- weak (bare trailing number, roman numeral, year, ": subtitle"): stripped only when the
  remaining root is a known franchise ("sibling evidence"), so "Mob Psycho 100" or
  "Kaiju No. 8" keep their number while "Sousou no Frieren 2" joins "Sousou no Frieren".
"""
import re
from typing import Callable, Optional, Tuple
from urllib.parse import urlparse

from backend.services.cover_utils import normalize_title_key as title_key

_VERSION_TAG = re.compile(r"\(\s*(vf|vostfr)\s*\)|\s(vf|vostfr)\s*$", re.IGNORECASE)
# 'X' and 'V' are left out: a trailing X / V is almost always part of the name ("Beyblade X", "Arc-V")
_ROMAN = {"ii": 2, "iii": 3, "iv": 4, "vi": 6, "vii": 7, "viii": 8, "ix": 9}

_STRONG = [
    (re.compile(r"^(?P<root>.+?)\s+(?:the\s+)?final\s+season(?:\s+part\s+(?P<part>\d+))?$"), "final"),
    (re.compile(r"^(?P<root>.+?)\s+saison\s+finale(?:\s+partie\s+(?P<part>\d+))?$"), "final"),
    (re.compile(r"^(?P<root>.+?)\s+(?P<n>\d{1,2})(?:st|nd|rd|th)\s+season(?:\s+part\s+(?P<part>\d+))?$"), "season"),
    (re.compile(r"^(?P<root>.+?)\s+(?:season|saison|s)\s*(?P<n>\d{1,2})(?:\s+(?:part|partie|cour)\s+(?P<part>\d+))?$"), "season"),
    (re.compile(r"^(?P<root>.+?)\s+(?:part|partie|cour)\s+(?P<part>\d+)$"), "part"),
]
_WEAK = [
    (re.compile(r"^(?P<root>.+?)\s+(?P<roman>ii|iii|iv|vi|vii|viii|ix)$"), "roman"),
    (re.compile(r"^(?P<root>.+?)\s+(?P<year>(?:19|20)\d{2})$"), "year"),
    (re.compile(r"^(?P<root>.+?)\s+(?P<n>[1-9]\d?)$"), "number"),
]
_SUBTITLE_SPLIT = re.compile(r"\s*:\s+|\s+-\s+")
MIN_KEY_LENGTH = 3


def split_version(title: str) -> Tuple[str, Optional[str]]:
    """'Frieren (VF)' -> ('Frieren', 'vf'); version is None when the title carries no tag."""
    text = title or ""
    version = None
    match = _VERSION_TAG.search(text)
    if match:
        version = (match.group(1) or match.group(2)).lower()
        text = _VERSION_TAG.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip(), version


def slug_of(url: str) -> str:
    if not isinstance(url, str):
        return ""
    try:
        path = urlparse(url).path.rstrip("/")
    except ValueError:
        return ""  # unbalanced IPv6 brackets ('https://[bad'): names no page
    return path.split("/")[-1].lower() if path else ""


def legacy_title_from_url(url: str) -> str:
    """Display title the old VoirAnime details built from the page slug (history keys use it)."""
    return slug_of(url).replace("-", " ").title()


def is_valid_key(key: str) -> bool:
    return len(key) >= MIN_KEY_LENGTH and not key.replace(" ", "").isdigit()


def _season_hint(kind: str, match) -> str:
    groups = match.groupdict()
    if kind == "final":
        return "Saison finale" + (f" Partie {groups['part']}" if groups.get("part") else "")
    if kind in ("season", "number") and groups.get("n"):
        return f"Saison {int(groups['n'])}" + (f" Partie {groups['part']}" if groups.get("part") else "")
    if kind == "part":
        return f"Partie {groups['part']}"
    if kind == "roman":
        return f"Saison {_ROMAN[groups['roman']]}"
    if kind == "year":
        return f"Remake {groups['year']}"
    return ""


def strong_root(key: str) -> Tuple[str, str]:
    """Strips strong season suffixes (repeatedly). Returns (root_key, season_hint)."""
    hint = ""
    for _ in range(2):
        for pattern, kind in _STRONG:
            match = pattern.match(key)
            if match and len(match.group("root").strip()) >= 2:
                key = match.group("root").strip()
                hint = hint or _season_hint(kind, match)
                break
        else:
            break
    return key, hint


def _weak_root(key: str, known: Callable[[str], bool]) -> Tuple[str, str]:
    for pattern, kind in _WEAK:
        match = pattern.match(key)
        if match:
            root = match.group("root").strip()
            if is_valid_key(root) and known(root):
                return root, _season_hint(kind, match)
            break
    return key, ""


def _split_subtitle(title: str) -> Tuple[str, str]:
    base, _ = split_version(title)
    parts = _SUBTITLE_SPLIT.split(base, maxsplit=1)
    return (parts[0], parts[1].strip()) if len(parts) > 1 else ("", "")


def subtitle_root(title: str) -> str:
    """'Ookami to Koushinryou: Merchant Meets the Wise Wolf' -> 'ookami to koushinryou' (never 'Re:Zero')."""
    head, _ = _split_subtitle(title)
    return title_key(head) if head else ""


def franchise_of(title: str, known: Callable[[str], bool] = lambda _k: False) -> Tuple[str, dict]:
    """Franchise key of one catalogue entry and what was stripped.

    known(root) tells whether a root is attested elsewhere (catalogue sibling or alias),
    which is required before stripping a weak suffix or a subtitle.
    info: version ('vf'/'vostfr'/None), season (hint label or ''), subtitle (text when the
    entry joined its franchise through ': subtitle').
    """
    base, version = split_version(title)
    key = title_key(base)
    info = {"version": version, "season": ""}

    key, info["season"] = strong_root(key)
    key, weak_hint = _weak_root(key, known)
    info["season"] = info["season"] or weak_hint

    head, subtitle = _split_subtitle(base)
    if head:
        # "Mushoku Tensei II: ..." -> "mushoku tensei ii" -> "mushoku tensei"
        sub, sub_hint = strong_root(title_key(head))
        sub, weak_sub_hint = _weak_root(sub, known)
        if sub != key and is_valid_key(sub) and known(sub):
            key = sub
            # A suffix after the subtitle belongs to it ("Bleach: Thousand-Year Blood War Part 2")
            info["season"] = sub_hint or weak_sub_hint
            info["subtitle"] = subtitle

    return key, info


def title_variants(title: str) -> set:
    """Keys a title can be matched under without any evidence (exact, strong-stripped, subtitle root)."""
    base, _ = split_version(title)
    key = title_key(base)
    variants = {key, strong_root(key)[0]}
    sub = subtitle_root(base)
    if sub:
        variants.add(sub)
        variants.add(strong_root(sub)[0])
    return {v for v in variants if is_valid_key(v)}


_SEASON_LABEL = re.compile(r"^(?:saison|season|s)\s*(?P<n>\d+)(?:\s+(?:partie|part)\s*(?P<part>\d+))?")


def season_key(label: str) -> Tuple[str, tuple]:
    """Stable key + sort order for a season label, so 'Saison 1' (Anime-Sama) and 'Season 1' (VoirAnime) merge."""
    key = title_key(label)
    if key in ("scans", "scan"):
        return "scans", (9, 0, 0)
    match = _SEASON_LABEL.match(key)
    if match:
        n, part = int(match.group("n")), int(match.group("part") or 0)
        return f"saison-{n}" + (f"-partie-{part}" if part else ""), (0, n, part)
    if key.startswith(("saison finale", "final season")):
        part = re.search(r"(?:partie|part)\s*(\d+)", key)
        return "saison-finale" + (f"-partie-{part.group(1)}" if part else ""), (0, 98, int(part.group(1)) if part else 0)
    for prefix, rank in (("film", 1), ("movie", 1), ("oav", 2), ("ova", 2), ("oad", 2), ("special", 3), ("remake", 4)):
        if key.startswith(prefix):
            num = re.search(r"(\d+)", key)
            canonical = {"movie": "film", "ova": "oav", "oad": "oav"}.get(prefix, prefix)
            return canonical + (f"-{num.group(1)}" if num else ""), (rank, int(num.group(1)) if num else 0, 0)
    return key.replace(" ", "-") or "saison-1", (5, 0, 0)
