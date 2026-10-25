import re
import httpx
from typing import Optional
from urllib.parse import quote, urljoin, urlparse
from fastapi import APIRouter, Query, Request
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse

from backend.services.cover_utils import raw_cover_url
from backend.services.http_headers import USER_AGENT, stream_referer
from backend.services.image_service import image_service, ImageFetchError
from backend.services.net_safety import assert_public_http_url, peer_is_public, UnsafeUrlError

router = APIRouter(prefix="/api", tags=["Proxy"])

# Proxied bodies are served on Nami's own origin: never let the browser render them as a page
SECURITY_HEADERS = {"X-Content-Type-Options": "nosniff", "Content-Security-Policy": "default-src 'none'; sandbox"}
IMAGE_OK_HEADERS = {"Cache-Control": "public, max-age=604800", **SECURITY_HEADERS}
IMAGE_MISS_HEADERS = {"Cache-Control": "no-store", "X-Nami-Fallback": "1", **SECURITY_HEADERS}
STREAM_MEDIA_TYPES = {
    "application/octet-stream", "binary/octet-stream", "video/mp2t",
    "application/vnd.apple.mpegurl", "application/x-mpegurl",
    # some hosts disguise HLS segments as images
    "image/jpeg", "image/png", "image/webp", "image/gif",
}

PLAYLIST_MAX_BYTES = 5 * 1024 * 1024
PASSTHROUGH_HEADERS = ("content-type", "content-length", "content-range", "accept-ranges", "last-modified", "etag")
_URI_ATTR = re.compile(r'URI="([^"]+)"')

_stream_client: Optional[httpx.AsyncClient] = None


def get_stream_client() -> httpx.AsyncClient:
    global _stream_client
    if _stream_client is None:
        _stream_client = httpx.AsyncClient(
            timeout=httpx.Timeout(connect=10.0, read=30.0, write=30.0, pool=10.0),
            limits=httpx.Limits(max_connections=32, max_keepalive_connections=16),
            follow_redirects=False,
            trust_env=False,  # the peer address check needs direct connections
        )
    return _stream_client


async def close_stream_client():
    global _stream_client
    if _stream_client is not None:
        await _stream_client.aclose()
        _stream_client = None


# --- Images ---
async def _serve_image(url: str):
    target = raw_cover_url(url)
    if not target.startswith(("http://", "https://")):
        return Response(status_code=404, headers=IMAGE_MISS_HEADERS)
    try:
        path, media_type = await image_service.get_image(target)
    except ImageFetchError:
        # 404 lets the browser fire onError and show the local placeholder
        return Response(status_code=404, headers=IMAGE_MISS_HEADERS)
    return FileResponse(path, media_type=media_type, headers=IMAGE_OK_HEADERS)


@router.get("/img")
async def proxy_image(url: str = Query(..., description="URL de l'image distante")):
    return await _serve_image(url)


@router.get("/proxy/image")
async def proxy_image_legacy(url: str = Query(..., description="Ancien chemin, encore présent dans l'historique")):
    return await _serve_image(url)


# --- Video streams (HLS playlists are rewritten so every segment goes through this proxy) ---
def proxied_stream_url(url: str, referer: Optional[str]) -> str:
    out = f"/api/proxy/stream?url={quote(url, safe='')}"
    if referer:
        out += f"&ref={quote(referer, safe='')}"
    return out


def rewrite_playlist(text: str, base_url: str, referer: Optional[str]) -> str:
    def wrap(uri: str) -> str:
        uri = uri.strip()
        if not uri or uri.startswith("data:"):
            return uri
        return proxied_stream_url(urljoin(base_url, uri), referer)

    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            lines.append(line)
        elif stripped.startswith("#"):
            lines.append(_URI_ATTR.sub(lambda m: f'URI="{wrap(m.group(1))}"', line) if 'URI="' in line else line)
        else:
            lines.append(wrap(stripped))
    return "\n".join(lines) + "\n"


def _looks_like_playlist(url: str, content_type: str) -> bool:
    return "mpegurl" in (content_type or "").lower() or urlparse(url).path.lower().endswith(".m3u8")


def _safe_media_type(content_type: str) -> str:
    media = (content_type or "").split(";")[0].strip().lower()
    if media.startswith(("video/", "audio/")) or media in STREAM_MEDIA_TYPES:
        return content_type
    return "application/octet-stream"


@router.get("/proxy/stream")
async def proxy_stream(
    request: Request,
    url: str = Query(..., description="URL du flux vidéo ou de la playlist m3u8"),
    ref: Optional[str] = Query(None, description="Referer à transmettre (propagé aux segments HLS)")
):
    target = url.strip()
    # Header-safe value only (printable ASCII: no CR/LF injection)
    valid_ref = bool(ref) and ref.isascii() and ref.isprintable() and ref.startswith(("http://", "https://"))
    referer = ref if valid_ref else stream_referer(target)

    headers = {"User-Agent": USER_AGENT, "Accept": "*/*", "Accept-Encoding": "identity"}
    if referer:
        headers["Referer"] = referer
        if "vidmoly" in referer:
            headers["Origin"] = "https://vidmoly.net"
    if request.headers.get("range"):
        headers["Range"] = request.headers["range"]

    client = get_stream_client()
    current = target
    resp = None
    try:
        # Redirects are followed by hand so every hop goes through the SSRF check
        for _ in range(5):
            await assert_public_http_url(current)
            resp = await client.send(client.build_request("GET", current, headers=headers), stream=True)
            if not peer_is_public(resp):
                await resp.aclose()
                return JSONResponse({"detail": "Hôte non autorisé"}, status_code=400, headers=SECURITY_HEADERS)
            if resp.is_redirect and resp.headers.get("location"):
                await resp.aclose()
                current = urljoin(current, resp.headers["location"])
                resp = None
                continue
            break
    except (UnsafeUrlError, httpx.InvalidURL) as e:
        return JSONResponse({"detail": str(e)}, status_code=400)
    except httpx.HTTPError as e:
        return JSONResponse({"detail": f"Erreur proxy: {e}"}, status_code=502)
    if resp is None:
        return JSONResponse({"detail": "Trop de redirections"}, status_code=502)

    iterator = resp.aiter_bytes()
    try:
        try:
            first = await iterator.__anext__()
        except StopAsyncIteration:
            first = b""

        content_type = resp.headers.get("content-type", "")
        if resp.status_code < 400 and (_looks_like_playlist(current, content_type) or first.lstrip().startswith(b"#EXTM3U")):
            body = bytearray(first)
            async for chunk in iterator:
                body.extend(chunk)
                if len(body) > PLAYLIST_MAX_BYTES:
                    await resp.aclose()
                    return JSONResponse({"detail": "Playlist trop volumineuse"}, status_code=502)
            await resp.aclose()
            rewritten = rewrite_playlist(body.decode("utf-8", errors="replace"), current, referer)
            return Response(rewritten, media_type="application/vnd.apple.mpegurl", headers={"Cache-Control": "no-cache", **SECURITY_HEADERS})
    except httpx.HTTPError as e:
        await resp.aclose()
        return JSONResponse({"detail": f"Erreur proxy: {e}"}, status_code=502)

    out_headers = {name: resp.headers[name] for name in PASSTHROUGH_HEADERS if name in resp.headers}
    out_headers["content-type"] = _safe_media_type(resp.headers.get("content-type", ""))
    out_headers["Cache-Control"] = "no-cache"
    out_headers.update(SECURITY_HEADERS)

    async def body_iter():
        try:
            if first:
                yield first
            async for chunk in iterator:
                yield chunk
        except httpx.HTTPError:
            pass
        finally:
            await resp.aclose()

    return StreamingResponse(body_iter(), status_code=resp.status_code, headers=out_headers)
