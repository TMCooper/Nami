"""Episodes downloaded to the viewer's own device (phone, PC), not to the server.

The server only relays: it finds a playable stream for the episode and remuxes it to MP4 on the
fly with ffmpeg (no re-encoding, nothing stored). ffmpeg reads through Nami's own stream proxy
on the loopback interface, so every remote hop goes through the proxy's SSRF checks.
The output is fragmented MP4: it can be written while it is produced and plays everywhere.
"""
import asyncio
import shutil
import subprocess
from functools import lru_cache
from typing import List, Optional
from urllib.parse import quote, urlparse

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse

from backend.services.catalog_service import catalog_service

router = APIRouter(prefix="/api", tags=["Device downloads"])

MAX_PARALLEL = 2          # remuxes running at once (each one is an ffmpeg process)
CHUNK = 64 * 1024
_slots = asyncio.Semaphore(MAX_PARALLEL)


def _is_stream(url: str) -> Optional[str]:
    """'m3u8' / 'mp4' for a direct stream URL, else None."""
    try:
        path = urlparse(url).path.lower()
    except ValueError:
        return None
    if url.startswith(("http://", "https://")):
        if path.endswith(".m3u8"):
            return "m3u8"
        if path.endswith(".mp4"):
            return "mp4"
    return None


async def _playable(candidates: List[str]) -> Optional[tuple]:
    """First (stream_url, kind) among the episode's players: direct links first, then resolved embeds."""
    for url in candidates:
        kind = _is_stream(url)
        if kind:
            return url, kind
        try:
            res = await catalog_service.resolve_stream(url)
        except Exception:
            continue
        stream = res.get("stream_url")
        if stream:
            return stream, res.get("stream_type") or _is_stream(stream) or "m3u8"
    return None


@lru_cache(maxsize=1)
def _hls_input_options(ffmpeg: str) -> tuple:
    """Proxied HLS segments have no '.ts' in their URL: recent ffmpeg refuses them unless told not to be picky.

    The options exist only in recent builds: an older ffmpeg (Raspberry Pi, Docker) does not need them.
    """
    try:
        help_text = subprocess.run([ffmpeg, "-hide_banner", "-h", "demuxer=hls"], capture_output=True,
                                   text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError):
        return ()
    options = []
    if "allowed_extensions" in help_text:
        options += ["-allowed_extensions", "ALL"]
    if "extension_picky" in help_text:
        options += ["-extension_picky", "0"]
    return tuple(options)


def _content_disposition(name: str) -> str:
    safe = "".join(c for c in name if c.isprintable() and c not in '"\\/:*?<>|').strip() or "episode.mp4"
    if not safe.lower().endswith(".mp4"):
        safe += ".mp4"
    ascii_name = safe.encode("ascii", "ignore").decode() or "episode.mp4"
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(safe)}"


@router.get("/device-download")
async def device_download(
    request: Request,
    url: List[str] = Query(..., description="Lecteurs de l'épisode, du meilleur au moins bon"),
    name: str = Query("episode.mp4", max_length=200, description="Nom du fichier proposé au navigateur")
):
    candidates = [u for u in url[:8] if isinstance(u, str) and u.startswith(("http://", "https://"))]
    if not candidates:
        raise HTTPException(status_code=400, detail="Aucun lecteur fourni.")
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise HTTPException(status_code=503, detail="ffmpeg est introuvable sur le serveur.")
    found = await _playable(candidates)
    if not found:
        raise HTTPException(status_code=422, detail="Aucun flux téléchargeable pour cet épisode.")
    stream_url, kind = found

    port = (request.scope.get("server") or ("127.0.0.1", 8080))[1]
    local_input = f"http://127.0.0.1:{port}/api/proxy/stream?url={quote(stream_url, safe='')}"
    hls_options = list(await asyncio.to_thread(_hls_input_options, ffmpeg)) if kind == "m3u8" else []
    cmd = [ffmpeg, "-loglevel", "error", "-nostdin", *hls_options, "-i", local_input,
           "-map", "0:v:0?", "-map", "0:a:0?", "-c", "copy"]
    if kind == "m3u8":
        cmd += ["-bsf:a", "aac_adtstoasc"]   # HLS audio is ADTS AAC: MP4 needs it raw
    cmd += ["-movflags", "frag_keyframe+empty_moov+default_base_moof", "-f", "mp4", "pipe:1"]

    await _slots.acquire()
    try:
        proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE,
                                                    stderr=asyncio.subprocess.DEVNULL, stdin=asyncio.subprocess.DEVNULL)
        first = await proc.stdout.read(CHUNK)
    except Exception:
        _slots.release()
        raise HTTPException(status_code=502, detail="Impossible de lancer la conversion.")
    if not first:
        await proc.wait()
        _slots.release()
        raise HTTPException(status_code=502, detail="Le flux de cet épisode ne répond pas.")

    async def body():
        try:
            yield first
            while True:
                chunk = await proc.stdout.read(CHUNK)
                if not chunk:
                    break
                yield chunk
        finally:
            # Finished, or the viewer cancelled / closed the page: never leave ffmpeg running
            if proc.returncode is None:
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass
            await proc.wait()
            _slots.release()

    return StreamingResponse(body(), media_type="video/mp4", headers={
        "Content-Disposition": _content_disposition(name),
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
    })
