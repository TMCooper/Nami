from fastapi import APIRouter, HTTPException, Query, Body
from pydantic import BaseModel
from typing import Optional, List
from backend.services.catalog_service import catalog_service
from backend.services.settings_service import settings_service
from backend.services.download_service import download_service

router = APIRouter(prefix="/api", tags=["Nami API"])

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
    episodes: List[dict]  # list of {episode_num, stream_url, stream_type}

@router.get("/search")
async def search_anime(
    q: str = Query(..., description="Recherche d'anime"),
    source: str = Query("all", description="Source: 'all', 'anime_sama', 'voiranime'")
):
    results = await catalog_service.search(query=q, source=source)
    return {"total": len(results), "results": results}

@router.get("/details")
async def get_details(
    url: str = Query(..., description="URL d'un anime"),
    source: str = Query(..., description="Source ('anime_sama' ou 'voiranime')")
):
    details = await catalog_service.get_details(url=url, source=source)
    if not details:
        raise HTTPException(status_code=404, detail="Impossible de récupérer les détails de cet anime.")
    return details

@router.get("/episodes")
async def get_season_episodes(
    season_url: str = Query(..., description="URL de la saison (AnimeSama)")
):
    episodes = await catalog_service.fetch_anime_sama_episodes(season_url)
    return {"total": len(episodes), "episodes": episodes}

@router.get("/resolve")
async def resolve_stream(
    embed_url: str = Query(..., description="URL iframe/embed du lecteur vidéo"),
    source: str = Query("anime_sama", description="Source ('anime_sama' ou 'voiranime')")
):
    res = await catalog_service.resolve_stream(embed_url=embed_url, source=source)
    return res

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
