"""Identity of a stored reference to an anime entity (history links, watchlist items).

Entity ids can change (alias unions, new homonymous pages), source entries do not: two
references name the same anime when their ids agree (raw or canonical) or when their
primary source entry is the same. A secondary source never counts (two works could merge).
"""
import re
from typing import Optional

from backend.services.cover_utils import client_cover_url
from backend.yoitsu.normalize import slug_of

TRAILER_ID = re.compile(r"^[\w-]{6,20}$")


def primary_ident(ref: Optional[dict]) -> str:
    """'source:slug' of a ref's primary entry ('' when either part is missing: never a match)."""
    if not isinstance(ref, dict):
        return ""
    source, slug = ref.get("source") or "", slug_of(ref.get("url") or "")
    return f"{source}:{slug}" if source and slug else ""


def identity_keys(ref: Optional[dict], canonical=None) -> set:
    """Keys two refs of one anime share: 'k:<canonical id>' and 'e:<primary entry>'."""
    if not isinstance(ref, dict):
        return set()
    keys = set()
    eid = ref.get("id") or ""
    if eid:
        keys.add("k:" + ((canonical(eid) if canonical else eid) or eid))
    ident = primary_ident(ref)
    if ident:
        keys.add("e:" + ident)
    return keys


def same_anime(a: Optional[dict], b: Optional[dict], canonical=None) -> bool:
    """Same entity: equal ids (raw or canonical, both non-empty), or the same primary source entry."""
    if not isinstance(a, dict) or not isinstance(b, dict):
        return False
    if a.get("id") and a.get("id") == b.get("id"):
        return True
    return bool(identity_keys(a, canonical) & identity_keys(b, canonical))


def same_entity(stored: Optional[dict], ref: Optional[dict], canonical=None, idents: Optional[set] = None) -> bool:
    """same_anime, before a details payload overwrites a stored ref (idents: gateway.entry_idents of it).

    An equal id is not proof once the stored primary entry left that entity: a homonymous Anime-Sama
    page with a shorter slug takes over the plain key, and its details would rewrite the ref.
    """
    if not same_anime(stored, ref, canonical):
        return False
    ident = primary_ident(stored)
    return idents is None or not ident or ident in idents


def clean_trailer(trailer) -> Optional[dict]:
    if not isinstance(trailer, dict):
        return None
    site, tid = trailer.get("site"), trailer.get("id")
    if isinstance(site, str) and site.strip() and isinstance(tid, str) and TRAILER_ID.match(tid):
        return {"site": site.strip()[:32], "id": tid}
    return None


def trailer_thumb(trailer) -> str:
    """16:9 frame of a YouTube trailer (hqdefault: always exists, letterbox bars are cropped by object-fit)."""
    t = clean_trailer(trailer)
    if not t or t["site"].lower() != "youtube":
        return ""
    return client_cover_url(f"https://i.ytimg.com/vi/{t['id']}/hqdefault.jpg")
