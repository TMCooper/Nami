import os
import re
import time
import shutil
import base64
import asyncio
import threading
import mimetypes
import hashlib
import subprocess
import httpx
from fastapi import APIRouter, HTTPException, Query, Body, Header, Request, status, UploadFile, File, Form
from fastapi.responses import StreamingResponse, Response, FileResponse
from pydantic import BaseModel, Field
from typing import Optional, List
from urllib.parse import unquote

from backend.services.catalog_service import catalog_service
from backend.services.settings_service import settings_service
from backend.services.download_service import download_service, sanitize_filename, resolve_anime_folder
from backend.services.history_service import history_service, client_ref, SOURCES as HISTORY_SOURCES, VERSIONS as HISTORY_VERSIONS
from backend.services.watchlist_service import watchlist_service, MAX_INPUT_ITEMS
from backend.services.user_service import user_service
from backend.services.cache_service import cache_service
from backend.services.source_health import source_health
from backend.services.yoitsu_service import yoitsu_service
from backend.yoitsu.gateway import yoitsu_gateway
from backend.services.net_safety import resolve_media_path, media_root

SCANS_TIMEOUT = 120.0


def _media_path_or_404(file_path: str, kind: str = "Fichier") -> str:
    """Only files under {root_folder}/nami can be streamed, thumbnailed or deleted."""
    decoded_path = unquote(file_path).strip()
    real_path = resolve_media_path(decoded_path, settings_service.get_root_folder())
    if not real_path or not os.path.exists(real_path):
        raise HTTPException(status_code=404, detail=f"{kind} introuvable sur le disque.")
    return real_path

router = APIRouter(prefix="/api", tags=["Nami API"])

class UserRegister(BaseModel):
    username: str
    password: Optional[str] = ""
    avatar: Optional[str] = "👤"

class UserLogin(BaseModel):
    username: str
    password: Optional[str] = ""

class SettingsUpdate(BaseModel):
    root_folder: Optional[str] = None
    default_provider: Optional[str] = None
    download_quality: Optional[str] = None
    max_concurrent_downloads: Optional[int] = Field(None, ge=1, le=6)

class DownloadCreate(BaseModel):
    anime_title: str
    season: Optional[str] = "Saison 1"
    episode_num: str
    stream_url: str
    stream_type: Optional[str] = "m3u8"
    fallback_urls: Optional[List[str]] = None

class BulkDownloadCreate(BaseModel):
    anime_title: str
    season: Optional[str] = "Saison 1"
    episodes: List[dict]

class AnimeRefPayload(BaseModel):
    id: Optional[str] = ""
    title: Optional[str] = ""
    source: Optional[str] = ""
    url: Optional[str] = ""
    entry_title: Optional[str] = ""
    banner: Optional[str] = None
    trailer: Optional[dict] = None

class NextEpisodePayload(BaseModel):
    ep_id: str
    title: Optional[str] = ""

class ProgressPayload(BaseModel):
    user_id: Optional[str] = "default"
    anime_title: str
    season: str
    ep_id: str
    # null when the player reports Infinity / NaN (live streams): treated as 0, never a 422
    position_sec: Optional[float] = 0
    duration_sec: Optional[float] = 0
    cover: Optional[str] = None
    embed_url: Optional[str] = None
    file_path: Optional[str] = None
    anime: Optional[AnimeRefPayload] = None
    season_key: Optional[str] = None
    source: Optional[str] = None
    version: Optional[str] = None
    ep_title: Optional[str] = None
    next_ep: Optional[NextEpisodePayload] = None
    link_via: Optional[str] = None

class ToggleWatchedPayload(BaseModel):
    user_id: Optional[str] = "default"
    anime_title: str
    season: str
    ep_id: str
    watched: Optional[bool] = None
    anime: Optional[AnimeRefPayload] = None
    season_key: Optional[str] = None
    source: Optional[str] = None
    version: Optional[str] = None
    ep_title: Optional[str] = None
    next_ep: Optional[NextEpisodePayload] = None
    cover: Optional[str] = None
    link_via: Optional[str] = None

class MarkSeasonPayload(BaseModel):
    user_id: Optional[str] = "default"
    anime_title: str
    season: str
    ep_ids: List[str]
    watched: Optional[bool] = True
    anime: Optional[AnimeRefPayload] = None
    season_key: Optional[str] = None
    source: Optional[str] = None
    version: Optional[str] = None
    cover: Optional[str] = None
    link_via: Optional[str] = None

class WatchlistAnimePayload(BaseModel):
    id: Optional[str] = ""
    title: str
    source: str
    url: str
    entry_title: Optional[str] = ""
    alt_titles: Optional[List[str]] = None
    cover: Optional[str] = ""
    cover_fallbacks: Optional[List[str]] = None
    banner: Optional[str] = None
    trailer: Optional[dict] = None
    sources: Optional[List[dict]] = None

class WatchlistPayload(BaseModel):
    user_id: Optional[str] = "default"
    anime: WatchlistAnimePayload
    added_at: Optional[float] = None

def _anime_ref(model: Optional[AnimeRefPayload]) -> Optional[dict]:
    """Entity link sent with a history write; its lookup fallback is kept only for a real source entry."""
    if not model or not (model.id or "").startswith("a-"):
        return None
    ref = model.model_dump()
    if not yoitsu_gateway.valid_entry(ref["source"] or "", ref["url"] or ""):
        ref.update(source="", url="", entry_title="")
    return ref

def _episode_context(payload) -> dict:
    source, version = payload.source, payload.version
    return {
        "season_key": payload.season_key or None,
        "source": source if source in HISTORY_SOURCES else None,
        "version": version if version in HISTORY_VERSIONS else None,
        "ep_title": getattr(payload, "ep_title", None),
    }

def _link_by(payload) -> str:
    # A context handed out by /history/resume is the server's own guess: it never ranks as a user write
    return "details" if payload.link_via == "resume" else "write"

_link_tasks: set = set()
_linking_users: set = set()

async def _link_legacy_history(uid: str, pending: list):
    try:
        links = await asyncio.to_thread(yoitsu_gateway.infer_links, pending)
        history_service.apply_links(uid, links)
    except Exception as e:
        print(f"[History] Legacy linking failed: {e}")
    finally:
        _linking_users.discard(uid)

def _spawn_legacy_linking(uid: str, pending: list):
    _linking_users.add(uid)
    task = asyncio.create_task(_link_legacy_history(uid, pending))
    _link_tasks.add(task)
    task.add_done_callback(_link_tasks.discard)

# --- User Auth & Accounts Routes ---
@router.get("/users")
async def list_users():
    return user_service.list_users()

@router.post("/auth/register")
async def register(payload: UserRegister):
    try:
        user = user_service.register_user(
            username=payload.username,
            password=payload.password or "",
            avatar=payload.avatar or "👤"
        )
        return user
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/auth/login")
async def login(payload: UserLogin):
    try:
        user = user_service.login_user(
            username=payload.username,
            password=payload.password or ""
        )
        return user
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))

@router.get("/auth/me")
async def get_current_user(x_user_id: Optional[str] = Header("default")):
    user = user_service.get_user(x_user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    return user

@router.post("/auth/avatar")
async def upload_avatar(x_user_id: Optional[str] = Header("default"), file: UploadFile = File(...)):
    """Upload a custom profile picture. Stored as base64 data URI in user data."""
    uid = x_user_id or "default"
    if uid not in user_service.users:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")

    content = await file.read()
    if len(content) > 2 * 1024 * 1024:  # 2MB max
        raise HTTPException(status_code=400, detail="L'image ne doit pas dépasser 2 Mo.")

    mime = file.content_type or "image/png"
    b64 = base64.b64encode(content).decode("utf-8")
    data_uri = f"data:{mime};base64,{b64}"

    user_service.users[uid]["avatar"] = data_uri
    user_service._save()

    return {
        "id": uid,
        "username": user_service.users[uid]["username"],
        "avatar": data_uri
    }

@router.patch("/auth/profile")
async def update_profile(x_user_id: Optional[str] = Header("default"), avatar: Optional[str] = Body(None, embed=True)):
    """Update user profile fields (e.g. emoji avatar)."""
    uid = x_user_id or "default"
    if uid not in user_service.users:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")

    if avatar is not None:
        user_service.users[uid]["avatar"] = avatar
        user_service._save()

    return user_service.get_user(uid)

@router.delete("/users/{user_id}")
async def delete_user(user_id: str):
    success = user_service.delete_user(user_id)
    if not success:
        raise HTTPException(status_code=404, detail="Utilisateur non trouvé.")
    return {"status": "ok", "message": f"Utilisateur {user_id} et toutes ses données supprimés."}

def _folder_size(base_dir: str) -> int:
    total_bytes = 0
    if os.path.exists(base_dir):
        for root, _, files in os.walk(base_dir):
            for f in files:
                try:
                    total_bytes += os.path.getsize(os.path.join(root, f))
                except Exception:
                    pass
    return total_bytes

@router.get("/users/stats")
async def get_user_stats(x_user_id: Optional[str] = Header("default")):
    stats = history_service.get_user_stats(user_id=x_user_id or "default", canonical=yoitsu_gateway.canonical_id)
    # Also calculate local disk storage used
    root_folder = settings_service.get_root_folder()
    total_bytes = await asyncio.to_thread(_folder_size, os.path.join(root_folder, "nami", "anime"))
    total_mb = round(total_bytes / (1024 * 1024), 1)
    total_gb = round(total_mb / 1024, 2)
    stats["storage_used"] = f"{total_gb} Go" if total_gb >= 1.0 else f"{total_mb} Mo"
    return stats

# --- Catalog Search & Details Routes ---
@router.get("/search")
async def search_anime(
    q: str = Query("", description="Recherche d'anime"),
    source: str = Query("all", description="Source: 'all', 'anime_sama', 'voiranime'")
):
    # One entity per anime (sources merged), see backend/yoitsu
    results = await yoitsu_gateway.search(query=q, source=source)
    return {"total": len(results), "results": results}

@router.get("/catalog/random")
async def get_random_catalog(count: int = Query(12, ge=1, le=50)):
    random_animes = await yoitsu_gateway.random(count=count)
    return {"total": len(random_animes), "results": random_animes}

@router.get("/catalog/recent")
async def get_recent_animes(x_user_id: Optional[str] = Header("default")):
    uid = x_user_id or "default"
    recents = yoitsu_gateway.recents(user_id=uid)
    if cache_service.recents_missing_cover(uid):
        # Never resolve covers inside the request: they appear on the next load
        catalog_service._spawn(catalog_service.repair_recent_covers(uid))
    return {"total": len(recents), "results": recents}

@router.get("/catalog/status")
async def get_catalog_status():
    return await catalog_service.get_update_status()

@router.post("/catalog/update")
async def trigger_catalog_update(source: str = Query("all", description="'all', 'anime_sama' ou 'voiranime'")):
    return await catalog_service.trigger_update(source=source)

# --- Merged anime entities (Yoitsu layer) ---
@router.get("/anime/lookup")
async def lookup_anime(
    source: str = Query(..., description="Source ('anime_sama' ou 'voiranime')"),
    url: str = Query(..., description="URL de l'entrée sur la source"),
    title: str = Query(..., description="Titre de l'entrée")
):
    if not yoitsu_gateway.valid_entry(source, url):
        raise HTTPException(status_code=400, detail="Source ou URL invalide.")
    entity = await yoitsu_gateway.lookup(source=source, url=url, title=title)
    if not entity:
        raise HTTPException(status_code=404, detail="Anime introuvable.")
    return entity

@router.get("/anime/{entity_id}")
async def get_anime_entity(
    entity_id: str,
    refresh: bool = Query(False, description="Forcer l'invalidation du cache"),
    x_user_id: Optional[str] = Header("default")
):
    uid = x_user_id or "default"
    details = await yoitsu_gateway.details(entity_id, refresh=refresh, user_id=uid)
    if not details:
        raise HTTPException(status_code=404, detail="Anime introuvable.")
    try:
        # Viewing an anime labels this profile's legacy records and heals its watchlist snapshot (never another profile's)
        idents = await yoitsu_gateway.entry_idents(details)   # an equal id under another page is another work
        history_service.link_titles(uid, yoitsu_gateway.anime_ref(details), yoitsu_gateway.history_claims(details),
                                    canonical=yoitsu_gateway.canonical_id, idents=idents)
        watchlist_service.refresh(uid, details, canonical=yoitsu_gateway.canonical_id, idents=idents)
    except Exception as e:
        print(f"[History] Linking from details failed: {e}")
    return details

@router.get("/sources")
async def get_sources(refresh: bool = Query(False)):
    # State of each source (API, site behind it, user switch): drives the settings panel and the home banner
    await source_health.refresh(force=refresh)
    return source_health.snapshot()

class SourceSwitchPayload(BaseModel):
    enabled: bool

@router.post("/sources/{source}")
async def set_source_enabled(source: str, payload: SourceSwitchPayload):
    if source not in ("anime_sama", "voiranime"):
        raise HTTPException(status_code=404, detail="Source inconnue.")
    source_health.set_enabled(source, payload.enabled)
    return source_health.snapshot()

class CookiePayload(BaseModel):
    cookie: str = Field(..., min_length=10, max_length=4000)

@router.post("/sources/voiranime/cookie")
async def set_voiranime_cookie(payload: CookiePayload):
    # voiranime_API can pass Cloudflare with the browser's cf_clearance cookie (its /api/setCookie route)
    api = yoitsu_service.api_link("VOIRANIME")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(f"{api}/setCookie", params={"cookie": payload.cookie.strip()})
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="L'API VoirAnime ne répond pas.")
    if resp.status_code != 200:
        raise HTTPException(status_code=400, detail="Cookie refusé par l'API VoirAnime.")
    await source_health.refresh(force=True)
    return source_health.snapshot()

@router.get("/anime/{entity_id}/wrapper")
async def get_anime_wrapper_status(entity_id: str, version: str = Query("vostfr", pattern="^(vostfr|vf)$")):
    # State of the YoitsuWrap build of this anime (started by its episodes): none, queued, running, ready, expired, failed
    if not entity_id.startswith("a-"):
        raise HTTPException(status_code=404, detail="Anime introuvable.")
    return yoitsu_gateway.wrapper_status(entity_id, version)

@router.get("/anime/{entity_id}/fiche")
async def get_anime_fiche(
    entity_id: str,
    version: str = Query("vostfr", pattern="^(vostfr|vf)$"),
    refresh: bool = Query(False, description="Reconstruire la fiche avec YoitsuWrap")
):
    # The anime as YoitsuWrap builds it (seasons, episodes and their source); starts the build when needed
    if not entity_id.startswith("a-"):
        raise HTTPException(status_code=404, detail="Anime introuvable.")
    fiche = await yoitsu_gateway.fiche(entity_id, version, refresh)
    if fiche is None:
        raise HTTPException(status_code=404, detail="Anime introuvable.")
    return fiche

@router.get("/anime/{entity_id}/preview")
async def get_anime_preview(entity_id: str, title: str = Query("", max_length=300, description="Titre de la carte")):
    # Hover previews: caches only, so hovering a grid never scrapes nor fills the recents
    preview = yoitsu_gateway.preview(entity_id, title)
    if preview is None:
        raise HTTPException(status_code=404, detail="Anime introuvable.")
    return preview

@router.get("/anime/{entity_id}/episodes")
async def get_anime_entity_episodes(
    entity_id: str,
    season: str = Query(..., description="Clé de saison (ex: saison-1)"),
    source: str = Query("", description="Source préférée"),
    version: str = Query("vostfr", description="Version (vostfr ou vf)"),
    refresh: bool = Query(False, description="Forcer l'invalidation du cache")
):
    result = await yoitsu_gateway.episodes(entity_id, season=season, source=source, version=version, refresh=refresh)
    if result is None:
        raise HTTPException(status_code=404, detail="Saison introuvable.")
    return {**result, "total": len(result["episodes"])}

@router.get("/episode/players")
async def get_episode_players(url: str = Query(..., description="Page d'épisode VoirAnime")):
    if not yoitsu_gateway.valid_entry("voiranime", url):
        raise HTTPException(status_code=400, detail="URL VoirAnime invalide.")
    players = await yoitsu_gateway.players(url)
    return {"total": len(players), "players": players}

@router.get("/details")
async def get_details(
    url: str = Query(..., description="URL d'un anime"),
    source: str = Query(..., description="Source ('anime_sama' ou 'voiranime')"),
    refresh: bool = Query(False, description="Forcer l'invalidation du cache"),
    x_user_id: Optional[str] = Header("default")
):
    details = await catalog_service.get_details(url=url, source=source, refresh=refresh, user_id=x_user_id or "default")
    if not details:
        raise HTTPException(status_code=404, detail="Impossible de récupérer les détails de cet anime.")
    return details

@router.get("/episodes")
async def get_season_episodes(
    season_url: str = Query(..., description="URL de la saison (AnimeSama ou VoirAnime)"),
    anime_title: Optional[str] = Query("", description="Titre de l'anime"),
    season_name: Optional[str] = Query("Saison 1", description="Nom de la saison"),
    version: Optional[str] = Query("vostfr", description="Version (vostfr ou vf)"),
    refresh: bool = Query(False, description="Forcer l'invalidation du cache")
):
    # Check if this is a manga scans request via YoitsuWrap
    if (season_name and season_name.lower() == "scans") or ("scans" in season_url.lower()):
        manga_name = anime_title or season_url.rstrip("/").split("/")[-1].replace("-", " ")
        chapters = await _scans_summary(manga_name)
        local_status = await asyncio.to_thread(yoitsu_service.get_downloaded_chapters_status, manga_name)

        episodes = []
        for ch in chapters:
            c_num_str = str(ch["chapter_num"])
            is_local = c_num_str in local_status
            pages = ch["pages"]

            if is_local:
                local_dir = local_status[c_num_str]["path"]
                try:
                    img_files = sorted(
                        [f for f in os.listdir(local_dir) if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp'))],
                        key=lambda x: [int(c) if c.isdigit() else c for c in re.split(r'(\d+)', x)]
                    )
                    if img_files:
                        pages = [os.path.join(local_dir, f).replace("\\", "/") for f in img_files]
                except Exception:
                    pass

            episodes.append({
                "num": ch["chapter_num"],
                "title": ch["title"],
                "pages_count": len(pages),
                "pages": pages,
                "is_scan": True,
                "is_downloaded": is_local
            })
        return {"total": len(episodes), "episodes": episodes, "is_scans": True}

    if "voir-anime" in season_url:
        # Loading a season tab is not "viewing an anime": keep it out of the recents shelf
        va_details = await catalog_service.get_details(url=season_url, source="voiranime", refresh=refresh, track_recent=False)
        episodes = va_details.get("episodes", [])
    else:
        episodes = await catalog_service.fetch_anime_sama_episodes(
            season_url=season_url,
            anime_title=anime_title or "",
            season_name=season_name or "Saison 1",
            version=version or "vostfr",
            refresh=refresh
        )
    return {"total": len(episodes), "episodes": episodes, "is_scans": False}

class DownloadScanPayload(BaseModel):
    anime_title: str
    chapter_num: Optional[int] = None

async def _scans_summary(manga_name: str) -> list:
    """YoitsuWrap scans use blocking requests without timeouts: run them off the event loop, bounded."""
    try:
        return await asyncio.wait_for(asyncio.to_thread(yoitsu_service.get_chapters_summary, manga_name), timeout=SCANS_TIMEOUT)
    except asyncio.TimeoutError:
        print(f"[API] Scans lookup timed out for '{manga_name}'")
        return []

@router.get("/scans")
async def get_scans_list(anime_title: str = Query(...)):
    chapters = await _scans_summary(anime_title)
    return {"title": anime_title, "total": len(chapters), "chapters": chapters}

@router.post("/scans/download")
async def download_scan_endpoint(payload: DownloadScanPayload):
    try:
        if payload.chapter_num is not None:
            res = await yoitsu_service.download_chapter(payload.anime_title, payload.chapter_num)
        else:
            res = await yoitsu_service.download_all_scans(payload.anime_title)
        return res
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/scans/status")
async def get_scans_status(anime_title: str = Query(...)):
    """Checks disk for downloaded chapters of a manga."""
    status_dict = await asyncio.to_thread(yoitsu_service.get_downloaded_chapters_status, anime_title)
    return {"anime_title": anime_title, "downloaded_chapters": status_dict}

# Image proxy: see backend/routers/stream_proxy.py (/api/img, legacy /api/proxy/image)

@router.get("/resolve")
async def resolve_stream(
    embed_url: str = Query(..., description="URL iframe/embed du lecteur vidéo"),
    source: str = Query("anime_sama", description="Source ('anime_sama' ou 'voiranime')")
):
    res = await catalog_service.resolve_stream(embed_url=embed_url, source=source)
    return res

# --- Local File Video Streaming with HTTP 206 Partial Content (Range) ---
@router.get("/stream/local")
async def stream_local_video(file_path: str = Query(..., description="Chemin du fichier vidéo local"), request: Request = None):
    decoded_path = _media_path_or_404(file_path, "Fichier vidéo local")
    if not os.path.isfile(decoded_path):
        raise HTTPException(status_code=404, detail="Fichier vidéo local introuvable sur le disque.")

    file_size = os.path.getsize(decoded_path)
    mime_type, _ = mimetypes.guess_type(decoded_path)
    if not mime_type:
        mime_type = "video/mp4"

    range_header = request.headers.get("range") if request else None

    if range_header:
        # Parse range header e.g. "bytes=0-1024" or "bytes=1024-"
        range_match = re.match(r"bytes=(\d+)-(\d*)", range_header)
        if range_match:
            start = int(range_match.group(1))
            end = int(range_match.group(2)) if range_match.group(2) else file_size - 1
            if start >= file_size:
                raise HTTPException(status_code=416, detail="Requested Range Not Satisfiable")
            end = min(end, file_size - 1)
            chunk_size = (end - start) + 1

            def iter_chunk():
                with open(decoded_path, "rb") as f:
                    f.seek(start)
                    bytes_remaining = chunk_size
                    while bytes_remaining > 0:
                        read_len = min(64 * 1024, bytes_remaining)
                        data = f.read(read_len)
                        if not data:
                            break
                        bytes_remaining -= len(data)
                        yield data

            headers = {
                "Content-Range": f"bytes {start}-{end}/{file_size}",
                "Accept-Ranges": "bytes",
                "Content-Length": str(chunk_size),
                "Content-Type": mime_type,
            }
            return StreamingResponse(iter_chunk(), status_code=status.HTTP_206_PARTIAL_CONTENT, headers=headers)

    # Standard full file stream
    def iter_full():
        with open(decoded_path, "rb") as f:
            while chunk := f.read(64 * 1024):
                yield chunk

    headers = {
        "Accept-Ranges": "bytes",
        "Content-Length": str(file_size),
        "Content-Type": mime_type,
    }
    return StreamingResponse(iter_full(), headers=headers)

@router.get("/stream/thumbnail")
async def get_video_thumbnail(file_path: str = Query(..., description="Chemin absolu du fichier vidéo local")):
    """Generates and caches a video thumbnail at 00:00:30 using ffmpeg."""
    decoded_path = _media_path_or_404(file_path, "Fichier vidéo")
    if not os.path.isfile(decoded_path):
        raise HTTPException(status_code=404, detail="Fichier vidéo introuvable")

    data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data")
    thumb_cache_dir = os.path.join(data_dir, "cache", "thumbnails")
    os.makedirs(thumb_cache_dir, exist_ok=True)
    h = hashlib.md5(decoded_path.encode("utf-8")).hexdigest()
    thumb_path = os.path.join(thumb_cache_dir, f"{h}.jpg")

    if os.path.exists(thumb_path) and os.path.getsize(thumb_path) > 1000:
        return FileResponse(thumb_path, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=2592000"})

    def _extract_frame(seek: str) -> bool:
        cmd = ["ffmpeg", "-y", "-ss", seek, "-i", decoded_path, "-vframes", "1", "-q:v", "3", thumb_path]
        proc = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
        return proc.returncode == 0 and os.path.exists(thumb_path) and os.path.getsize(thumb_path) > 1000

    try:
        # 1 frame at 30 seconds, or at 5 seconds if 30s is past the end (off the event loop)
        if await asyncio.to_thread(_extract_frame, "00:00:30") or await asyncio.to_thread(_extract_frame, "00:00:05"):
            return FileResponse(thumb_path, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=2592000"})
    except Exception as e:
        print(f"[Thumbnail] Error generating thumbnail for {decoded_path}: {e}")

    raise HTTPException(status_code=500, detail="Impossible de générer la miniature")

# --- Episode Download Status Check & Local Library ---
@router.get("/episodes/download-status")
async def check_episodes_downloaded(
    anime_title: List[str] = Query(..., max_length=4),
    season: str = Query("Saison 1"),
    label: str = Query("", description="Saison de la fiche YoitsuWrap"),
    version: str = Query("", pattern="^(|vostfr|vf)$")
):
    root_folder = settings_service.get_root_folder()
    season_dirs = []
    for title in anime_title:
        # Old downloads: <root>/nami/anime/<anime>/<season name>/
        anime_base = os.path.join(root_folder, "nami", "anime")
        season_dirs.append(os.path.join(anime_base, resolve_anime_folder(anime_base, title), sanitize_filename(season)))
        if label and version:
            # YoitsuWrap downloads: <root>/nami/Anime/<anime>/<season>/<version>/
            wrapper_base = os.path.join(root_folder, "nami", "Anime")
            season_dirs.append(os.path.join(wrapper_base, resolve_anime_folder(wrapper_base, title),
                                            sanitize_filename(label), version))

    status_map = {}
    for season_dir in dict.fromkeys(season_dirs):
        if not os.path.isdir(season_dir):
            continue
        for f in os.listdir(season_dir):
            if f.lower().endswith(('.mp4', '.mkv', '.webm')) and ".temp." not in f.lower():
                full_path = os.path.join(season_dir, f)
                m = re.search(r'\d+', f)
                if m:
                    ep_num = str(int(m.group()))
                    status_map[ep_num] = {
                        "downloaded": True,
                        "file_path": full_path,
                        "filename": f,
                        "size_mb": round(os.path.getsize(full_path) / (1024 * 1024), 1)
                    }

    return {"downloaded_episodes": status_map}

@router.get("/library/downloaded")
async def get_downloaded_library():
    root_folder = settings_service.get_root_folder()
    lib = await asyncio.to_thread(cache_service.scan_downloaded_library, root_folder)
    return {"total_animes": len(lib), "library": lib}

@router.delete("/library/episode")
async def delete_downloaded_episode(file_path: str = Query(..., description="Chemin absolu du fichier épisode ou dossier de chapitre")):
    """Delete a single downloaded episode file or chapter scan folder from disk."""
    decoded_path = _media_path_or_404(file_path, "Fichier ou dossier")
    # Only an episode file or a chapter folder (category/anime/season/item): never the root,
    # a category ("anime", "Anime") or a whole anime folder (that is /library/anime)
    rel_parts = os.path.relpath(decoded_path, media_root(settings_service.get_root_folder())).split(os.sep)
    if len(rel_parts) < 3 or ".." in rel_parts:
        raise HTTPException(status_code=400, detail="Suppression de ce dossier refusée.")
    try:
        if os.path.isdir(decoded_path):
            shutil.rmtree(decoded_path)
        else:
            os.remove(decoded_path)
        # Clean up empty parent directories
        parent = os.path.dirname(decoded_path)
        if os.path.isdir(parent) and not os.listdir(parent):
            os.rmdir(parent)
            grandparent = os.path.dirname(parent)
            if os.path.isdir(grandparent) and not os.listdir(grandparent):
                os.rmdir(grandparent)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors de la suppression: {str(e)}")
    return {"status": "deleted", "file_path": decoded_path}

@router.delete("/library/anime")
async def delete_downloaded_anime(
    anime_title: str = Query(..., description="Titre de l'anime (nom du dossier sanitizé)")
):
    """Delete an entire anime folder from disk. Stats/history are preserved."""
    root_folder = settings_service.get_root_folder()
    safe_title = sanitize_filename(anime_title)
    if not safe_title.strip("."):
        # ".." or "" would resolve to the whole library
        raise HTTPException(status_code=400, detail="Titre invalide.")

    deleted = False
    for sub in ["anime", "Anime"]:
        anime_dir = os.path.join(root_folder, "nami", sub, safe_title)
        category_dir = os.path.realpath(os.path.join(root_folder, "nami", sub))
        if os.path.normcase(os.path.dirname(os.path.realpath(anime_dir))) != os.path.normcase(category_dir):
            continue
        if os.path.exists(anime_dir) and os.path.isdir(anime_dir):
            try:
                shutil.rmtree(anime_dir)
                deleted = True
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Erreur lors de la suppression: {str(e)}")

    if not deleted:
        raise HTTPException(status_code=404, detail="Dossier anime introuvable sur le disque.")
    return {"status": "deleted", "anime_title": anime_title}

# --- Watch History & Progress Routes ---
@router.get("/history")
async def get_history(x_user_id: Optional[str] = Header("default")):
    return history_service.get_history_for_client(user_id=x_user_id or "default", canonical=yoitsu_gateway.canonical_id,
                                                  media=yoitsu_gateway.anilist.cached)

@router.get("/history/continue")
async def get_continue_watching(limit: int = Query(20, ge=1, le=100), x_user_id: Optional[str] = Header("default")):
    uid = x_user_id or "default"
    if yoitsu_gateway.index.catalog_loaded and uid not in _linking_users:
        pending = history_service.unlinked_titles(uid)
        if pending:
            _spawn_legacy_linking(uid, pending)  # links show up on the next load, never awaited here
    items = history_service.get_continue_watching(uid, canonical=yoitsu_gateway.canonical_id, media=yoitsu_gateway.anilist.cached)
    return {"total": len(items), "results": items[:limit]}

@router.get("/history/resume")
async def resume_history(
    anime_title: str = Query(..., description="Titre de l'enregistrement d'historique"),
    season: str = Query(..., description="Nom de saison de l'historique (ex: Saison 1 VF)"),
    x_user_id: Optional[str] = Header("default")
):
    """Strict resume target of a history record: its linked entity, season variant and episode list."""
    uid = x_user_id or "default"
    key, record = history_service.find_record(uid, anime_title)
    ref = (record or {}).get("anime") or {}
    if not ref.get("id"):
        raise HTTPException(status_code=404, detail="Reprise introuvable.")
    eid = await yoitsu_gateway.live_id(ref)
    if not eid:
        raise HTTPException(status_code=404, detail="Reprise introuvable.")
    if eid != ref["id"]:
        # Before reading the mapping: relabel drops the old entity's season keys, so it goes through relink()
        history_service.relabel(uid, key, eid)

    async def relink(anime_id: str):
        # Season mapping from details claims (explicit tap only: no recents)
        details = await yoitsu_gateway.details(anime_id, user_id=uid, track_recent=False)
        if details:
            history_service.link_titles(uid, yoitsu_gateway.anime_ref(details), yoitsu_gateway.history_claims(details),
                                        canonical=yoitsu_gateway.canonical_id,
                                        idents=await yoitsu_gateway.entry_idents(details))

    async def season_episodes(anime_id: str):
        target = (record.get("seasons") or {}).get(season)
        if not isinstance(target, dict):
            return None, None
        result = await yoitsu_gateway.episodes(anime_id, season=target.get("key") or "", source=target.get("source") or "",
                                               version=target.get("version") or "vostfr")
        return target, result

    relinked = False
    if not isinstance((record.get("seasons") or {}).get(season), dict):
        await relink(eid)
        relinked = True
    target, result = await season_episodes(eid)
    if result is None and not relinked:
        # The stored season key vanished (relabelled entity): refresh the mapping once
        await relink(eid)
        target, result = await season_episodes(eid)
    if result is None:
        raise HTTPException(status_code=404, detail="Reprise introuvable.")
    trusted = True
    if result["anime_id"] != eid:
        # Another entity answered: the list was fetched with a season key the old one issued. Relabel (which drops
        # the mapping), relink and retry once; a list that still comes from a stale key is never reported exact
        stale = target, result
        eid = result["anime_id"]
        history_service.relabel(uid, key, eid)
        await relink(eid)
        target, result = await season_episodes(eid)
        trusted = result is not None and result["anime_id"] == eid
        if result is None:
            target, result = stale
    variant = result["variant"]
    return {
        **result,
        "anime": client_ref(record["anime"], yoitsu_gateway.canonical_id, yoitsu_gateway.anilist.cached),
        "total": len(result["episodes"]),
        "exact": trusted and variant["source"] == target["source"] and variant["version"] == target["version"],
    }

@router.post("/history/progress")
async def save_progress(payload: ProgressPayload, x_user_id: Optional[str] = Header(None)):
    uid = x_user_id or payload.user_id or "default"
    res = history_service.save_progress(
        user_id=uid,
        anime_title=payload.anime_title,
        season=payload.season,
        ep_id=payload.ep_id,
        position_sec=payload.position_sec,
        duration_sec=payload.duration_sec,
        cover=payload.cover,
        embed_url=payload.embed_url,
        file_path=payload.file_path,
        anime=_anime_ref(payload.anime),
        context=_episode_context(payload),
        next_ep=payload.next_ep.model_dump() if payload.next_ep else None,
        link_by=_link_by(payload),
        canonical=yoitsu_gateway.canonical_id
    )
    return res

@router.post("/history/toggle-watched")
async def toggle_watched(payload: ToggleWatchedPayload, x_user_id: Optional[str] = Header(None)):
    uid = x_user_id or payload.user_id or "default"
    is_watched = history_service.toggle_watched(
        user_id=uid,
        anime_title=payload.anime_title,
        season=payload.season,
        ep_id=payload.ep_id,
        is_watched=payload.watched,
        anime=_anime_ref(payload.anime),
        context=_episode_context(payload),
        next_ep=payload.next_ep.model_dump() if payload.next_ep else None,
        cover=payload.cover,
        link_by=_link_by(payload),
        canonical=yoitsu_gateway.canonical_id
    )
    return {"watched": is_watched}

@router.post("/history/mark-season")
async def mark_season(payload: MarkSeasonPayload, x_user_id: Optional[str] = Header(None)):
    uid = x_user_id or payload.user_id or "default"
    history_service.mark_season(
        user_id=uid,
        anime_title=payload.anime_title,
        season=payload.season,
        ep_ids=payload.ep_ids,
        is_watched=payload.watched,
        anime=_anime_ref(payload.anime),
        context=_episode_context(payload),
        cover=payload.cover,
        link_by=_link_by(payload),
        canonical=yoitsu_gateway.canonical_id
    )
    return {"status": "ok"}

@router.delete("/history/item")
async def delete_history_item(
    anime_title: str = Query(...),
    ep_key: Optional[str] = Query(None),
    x_user_id: Optional[str] = Header("default")
):
    history_service.delete_item(x_user_id or "default", anime_title, ep_key)
    return {"status": "ok"}

@router.delete("/history/clear")
async def clear_history(x_user_id: Optional[str] = Header("default")):
    history_service.clear_user_history(x_user_id or "default")
    return {"status": "ok"}

# --- Watchlist (« À regarder plus tard ») ---
def _watchlist_response(uid: str) -> dict:
    # Every route returns the server list: the client sets it as the truth without a second GET
    items = watchlist_service.get_items_for_client(uid, canonical=yoitsu_gateway.canonical_id)
    return {"total": len(items), "results": items}

@router.get("/watchlist")
async def get_watchlist(x_user_id: Optional[str] = Header("default")):
    return _watchlist_response(x_user_id or "default")

@router.post("/watchlist")
async def add_to_watchlist(payload: WatchlistPayload, x_user_id: Optional[str] = Header(None)):
    uid = x_user_id or payload.user_id or "default"
    if uid != "default" and uid not in user_service.users:
        # Never a bucket for an id no profile owns (the store would grow with any header value)
        raise HTTPException(status_code=404, detail="Profil introuvable.")
    anime = payload.anime.model_dump()
    if not anime["title"].strip() or not yoitsu_gateway.valid_entry(anime["source"], anime["url"]):
        raise HTTPException(status_code=400, detail="Anime invalide.")
    anime["sources"] = [s for s in (anime.get("sources") or [])[:MAX_INPUT_ITEMS] if isinstance(s, dict)
                        and isinstance(s.get("source"), str) and isinstance(s.get("url"), str)
                        and yoitsu_gateway.valid_entry(s["source"], s["url"])]
    if not (anime["id"] or "").startswith("a-"):
        entity = await yoitsu_gateway.lookup(anime["source"], anime["url"], anime["entry_title"] or anime["title"])
        anime["id"] = entity["id"] if entity else ""
    if not watchlist_service.add(uid, anime, payload.added_at, canonical=yoitsu_gateway.canonical_id):
        raise HTTPException(status_code=400, detail="Anime invalide.")
    return _watchlist_response(uid)

@router.delete("/watchlist")
async def remove_from_watchlist(
    anime_id: str = Query("", alias="id", description="Identifiant de l'anime"),
    source: str = Query("", description="Source de l'entrée principale"),
    url: str = Query("", description="URL de l'entrée principale"),
    x_user_id: Optional[str] = Header("default")
):
    # Query parameters, not a path: ids are percent-encoded
    if not anime_id and not (source and url):
        raise HTTPException(status_code=400, detail="Anime invalide.")
    uid = x_user_id or "default"
    watchlist_service.remove(uid, anime_id=anime_id, source=source, url=url, canonical=yoitsu_gateway.canonical_id)
    return _watchlist_response(uid)


# --- Settings & Download Routes ---
@router.get("/settings")
async def get_settings():
    return settings_service.get_settings()

@router.post("/settings")
async def update_settings(payload: SettingsUpdate):
    updated = settings_service.update_settings(payload.model_dump(exclude_unset=True))
    return updated

@router.get("/downloads")
async def get_downloads():
    return download_service.get_all_tasks()

@router.post("/downloads")
async def add_download(payload: DownloadCreate):
    task = download_service.add_task(
        anime_title=payload.anime_title,
        season=payload.season,
        episode_num=payload.episode_num,
        stream_url=payload.stream_url,
        stream_type=payload.stream_type or "m3u8",
        fallback_urls=(payload.fallback_urls or [])[:10]
    )
    return task.to_dict()

@router.post("/downloads/bulk")
async def add_bulk_download(payload: BulkDownloadCreate):
    added_tasks = []
    for ep in payload.episodes:
        t = download_service.add_task(
            anime_title=payload.anime_title,
            season=payload.season,
            episode_num=ep.get("episode_num", "1"),
            stream_url=ep.get("stream_url", ""),
            stream_type=ep.get("stream_type", "m3u8"),
            fallback_urls=[u for u in ep.get("fallback_urls") or [] if isinstance(u, str)][:10]
        )
        added_tasks.append(t.to_dict())
    return {"total_added": len(added_tasks), "tasks": added_tasks}

@router.post("/downloads/cancel/{task_id}")
async def cancel_download(task_id: str):
    success = download_service.cancel_task(task_id)
    if not success:
        raise HTTPException(status_code=404, detail="Tâche non trouvée")
    return {"status": "cancelled", "task_id": task_id}

@router.post("/downloads/clear")
async def clear_downloads():
    download_service.clear_completed()
    return {"status": "cleared"}

# --- In-App Updates & Component Management ---
from backend.services.update_service import update_service, ANIME_SAMA_PATH, VOIRANIME_PATH
from backend.services import self_update

_BOOT_ID = f"{os.getpid()}-{time.time():.0f}"

@router.get("/server/boot")
async def server_boot():
    # Changes on every start: the interface reloads once Nami has restarted after an update
    return {"boot": _BOOT_ID}

@router.get("/updates/check")
async def check_updates():
    # Nami itself first, then its APIs and YoitsuWrap
    # git ls-remote + PyPI lookups: several seconds of blocking I/O
    nami, others = await asyncio.gather(asyncio.to_thread(self_update.status), asyncio.to_thread(update_service.check_all_updates))
    return {"nami": nami, **others}

@router.post("/updates/apply")
async def apply_update(target: str = Query(..., pattern="^(nami|animesama|voiranime|yoitsuwrap|all)$",
                                           description="'nami', 'animesama', 'voiranime', 'yoitsuwrap', or 'all' (the APIs and YoitsuWrap)")):
    # git pull, pip install and process restarts must not freeze the server
    return await asyncio.to_thread(_apply_update, target)

_update_lock = threading.Lock()

def _apply_update(target: str) -> dict:
    # One update at a time: concurrent git pull / pip install / restarts would race
    with _update_lock:
        return _apply_update_locked(target)

def _apply_update_locked(target: str) -> dict:
    from backend.main import restart_submodule
    results = {}

    if target in ["all", "animesama"]:
        res_as = update_service.update_repo("https://github.com/TMCooper/AnimeSamaApi.git", ANIME_SAMA_PATH)
        results["animesama"] = res_as
        restart_submodule("animesama")

    if target in ["all", "voiranime"]:
        res_va = update_service.update_repo("https://github.com/TMCooper/voiranime_API.git", VOIRANIME_PATH)
        results["voiranime"] = res_va
        restart_submodule("voiranime")

    if target in ["all", "yoitsuwrap"]:
        res_yw = update_service.update_yoitsuwrap()
        # The running process keeps the old wrapper imported: Nami restarts to load the new one
        res_yw["restart"] = res_yw.get("status") == "updated"
        results["yoitsuwrap"] = res_yw

    if target == "nami":
        results["nami"] = self_update.apply()

    restart = any(r.get("restart") for r in results.values())
    if restart:
        self_update.request_restart()
    return {"status": "completed", "results": results, "restart": restart,
            "host_rebuild": any(r.get("host_rebuild") for r in results.values())}

