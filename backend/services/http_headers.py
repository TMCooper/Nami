from typing import Optional
from urllib.parse import urlparse

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


def image_referer(url: str) -> Optional[str]:
    """Referer expected by hotlink-protected cover hosts."""
    host = (urlparse(url).hostname or "").lower()
    if "voir-anime" in host or "voiranime" in host:
        return "https://voir-anime.to/"
    if "anime-sama" in host:
        return f"https://{host}/"
    return None


def stream_referer(url: str) -> Optional[str]:
    """Referer expected by the video hosts whose direct links Nami plays or downloads."""
    if "vidmoly" in url:
        return "https://vidmoly.net/"
    if "sendvid" in url:
        return "https://sendvid.com/"
    if "sibnet" in url:
        return "https://video.sibnet.ru/"
    return None
