import os
import re
import mimetypes
from fastapi import APIRouter, HTTPException, Query, Body, Header, Request, status
from fastapi.responses import StreamingResponse, Response
from pydantic import BaseModel
from typing import Optional, List
from urllib.parse import unquote

from backend.services.catalog_service import catalog_service
from backend.services.settings_service import settings_service
from backend.services.download_service import download_service, sanitize_filename
from backend.services.history_service import history_service
from backend.services.user_service import user_service
from backend.services.cache_service import cache_service

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

class DownloadCreate(BaseModel):
    anime_title: str
    season: Optional[str] = "Saison 1"
    episode_num: str
    stream_url: str
    stream_type: Optional[str] = "m3u8"

class BulkDownloadCreate(BaseModel):
    anime_title: str
    season: Optional[str] = "Saison 1"
    episodes: List[dict]

class ProgressPayload(BaseModel):
    user_id: Optional[str] = "default"
    anime_title: str
    season: str
    ep_id: str
    position_sec: float
    duration_sec: float
    cover: Optional[str] = None
    embed_url: Optional[str] = None
    file_path: Optional[str] = None

class ToggleWatchedPayload(BaseModel):
    user_id: Optional[str] = "default"
    anime_title: str
    season: str
    ep_id: str
    watched: Optional[bool] = None

class MarkSeasonPayload(BaseModel):
    user_id: Optional[str] = "default"
    anime_title: str
    season: str
    ep_ids: List[str]
    watched: Optional[bool] = True

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

@router.get("/users/stats")
async def get_user_stats(x_user_id: Optional[str] = Header("default")):
    stats = history_service.get_user_stats(user_id=x_user_id or "default")
    # Also calculate local disk storage used
    root_folder = settings_service.get_root_folder()
    base_dir = os.path.join(root_folder, "nami", "anime")
    total_bytes = 0
    if os.path.exists(base_dir):
        for root, _, files in os.walk(base_dir):
            for f in files:
                try:
                    total_bytes += os.path.getsize(os.path.join(root, f))
                except Exception:
                    pass
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
    results = await catalog_service.search(query=q, source=source)
    return {"total": len(results), "results": results}

@router.get("/catalog/random")
async def get_random_catalog(count: int = Query(12, ge=1, le=50)):
    random_animes = cache_service.get_random_animes(count=count)
    return {"total": len(random_animes), "results": random_animes}

@router.get("/catalog/recent")
async def get_recent_animes(x_user_id: Optional[str] = Header("default")):
    recents = cache_service.get_recent_animes(user_id=x_user_id or "default")
    return {"total": len(recents), "results": recents}

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
    season_url: str = Query(..., description="URL de la saison (AnimeSama)"),
    refresh: bool = Query(False, description="Forcer l'invalidation du cache")
):
    episodes = await catalog_service.fetch_anime_sama_episodes(season_url, refresh=refresh)
    return {"total": len(episodes), "episodes": episodes}

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
    decoded_path = unquote(file_path).strip()
    
    if not os.path.exists(decoded_path) or not os.path.isfile(decoded_path):
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

# --- Episode Download Status Check & Local Library ---
@router.get("/episodes/download-status")
async def check_episodes_downloaded(
    anime_title: str = Query(...),
    season: str = Query("Saison 1")
):
    root_folder = settings_service.get_root_folder()
    safe_anime = sanitize_filename(anime_title)
    safe_season = sanitize_filename(season)
    season_dir = os.path.join(root_folder, "nami", "anime", safe_anime, safe_season)

    status_map = {}
    if os.path.exists(season_dir):
        for f in os.listdir(season_dir):
            if f.lower().endswith(('.mp4', '.mkv', '.webm')):
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
    lib = cache_service.scan_downloaded_library(root_folder)
    return {"total_animes": len(lib), "library": lib}

# --- Watch History & Progress Routes ---
@router.get("/history")
async def get_history(x_user_id: Optional[str] = Header("default")):
    return history_service.get_history(user_id=x_user_id or "default")

@router.get("/history/continue")
async def get_continue_watching(x_user_id: Optional[str] = Header("default")):
    items = history_service.get_continue_watching(user_id=x_user_id or "default")
    return {"total": len(items), "results": items}

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
        file_path=payload.file_path
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
        is_watched=payload.watched
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
        is_watched=payload.watched
    )
    return {"status": "ok"}

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
        stream_type=payload.stream_type or "m3u8"
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
            stream_type=ep.get("stream_type", "m3u8")
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

@router.get("/updates/check")
async def check_updates():
    return update_service.check_all_updates()

@router.post("/updates/apply")
async def apply_update(target: str = Query(..., description="'animesama', 'voiranime', 'yoitsuwrap', or 'all'")):
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
        results["yoitsuwrap"] = res_yw

    return {"status": "completed", "results": results}

