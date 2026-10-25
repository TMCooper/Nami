import re
import unicodedata
from urllib.parse import quote, unquote, urljoin, urlparse

IMAGE_ROUTE = "/api/img?url="
LEGACY_PROXY_PREFIXES = ("/api/proxy/image?url=", IMAGE_ROUTE)

# Public CDNs that serve covers without hotlink protection: loaded directly by the browser.
DIRECT_IMAGE_HOSTS = {"raw.githubusercontent.com", "cdn.statically.io", "cdn.jsdelivr.net"}

_IMG_ATTRS = ("data-src", "data-lazy-src", "data-original", "src")


def normalize_title_key(title: str) -> str:
    """Accent-folded, casefolded, punctuation-free key used for exact title lookups ('' means no key)."""
    t = unicodedata.normalize("NFKD", title or "")
    t = "".join(c for c in t if not unicodedata.combining(c)).casefold()
    return re.sub(r"[\W_]+", " ", t).strip()


def raw_cover_url(cover: str) -> str:
    """Returns the upstream URL behind a cover value (strips Nami proxy wrappers, fixes percent-encoded values)."""
    value = (cover or "").strip()
    for prefix in LEGACY_PROXY_PREFIXES:
        if value.startswith(prefix):
            value = unquote(value[len(prefix):])
            break
    if value.lower().startswith(("http%3a", "https%3a")):
        value = unquote(value)
    return value


def is_placeholder_cover(cover: str) -> bool:
    value = (cover or "").strip().lower()
    return not value or value.startswith("data:") or "placeholder" in value


def is_usable_cover(cover: str) -> bool:
    raw = raw_cover_url(cover)
    if is_placeholder_cover(raw):
        return False
    return raw.startswith(("http://", "https://", "/api/stream/local"))


def is_trusted_cover(cover: str, source: str) -> bool:
    """Older builds wrote Anime-Sama art (found by fuzzy title) as VoirAnime covers: never trust those."""
    if source != "voiranime":
        return True
    raw = raw_cover_url(cover)
    host = (urlparse(raw).hostname or "").lower()
    return "anime-sama" not in host and "/anime-sama/img/" not in raw.lower()


def client_cover_url(cover: str) -> str:
    """Cover value sent to the browser: hotlink-sensitive hosts go through the image service."""
    raw = raw_cover_url(cover)
    if not is_usable_cover(raw):
        return ""
    if raw.startswith("/api/"):
        return raw
    host = (urlparse(raw).hostname or "").lower()
    if host in DIRECT_IMAGE_HOSTS:
        return raw
    return f"{IMAGE_ROUTE}{quote(raw, safe='')}"


def extract_img_url(tag, base_url: str = "") -> str:
    """Reads the real image URL of an <img>, preferring lazy-load attributes over a placeholder src."""
    if tag is None:
        return ""
    for attr in _IMG_ATTRS:
        value = (tag.get(attr) or "").strip()
        if value and not value.startswith("data:"):
            return urljoin(base_url, value)
    srcset = (tag.get("data-srcset") or tag.get("srcset") or "").strip()
    if srcset:
        last = srcset.split(",")[-1].strip().split(" ")[0]
        if last and not last.startswith("data:"):
            return urljoin(base_url, last)
    return ""


def extract_page_cover(soup, base_url: str = "") -> str:
    """og:image first, then the Madara/Anime-Sama poster <img>."""
    og = soup.find("meta", property="og:image")
    if og and og.get("content") and not og["content"].startswith("data:"):
        return urljoin(base_url, og["content"].strip())
    return extract_img_url(soup.select_one(".summary_image img"), base_url)
