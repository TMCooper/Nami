"""Downloads of episodes of a YoitsuWrap fiche: to the server's library, or to the viewer's device.

Both are done by YoitsuWrap (Season.download_season: episodes in parallel, with yt-dlp), from the
links of the fiche it verified, with progress and speed.

- server: into the library (<root>/nami/Anime/<anime>/<season>/<version>/<n>.mp4), followed in
  the downloads drawer like the other server downloads;
- device: a browser cannot fetch the video hosts itself (no CORS), so YoitsuWrap downloads the
  episode into a temporary folder of the server, then the page fetches the finished file and
  writes it on the device (the folder the viewer picked, else the browser's downloads). The
  temporary file is removed once sent, or after a few hours.
"""
import os
import time
import uuid
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from backend.security import ensure_free_space, is_admin, require_server_downloads, session_user_id
from backend.services import wrapper_download
from backend.services.download_service import download_service
from backend.services.settings_service import settings_service
from backend.yoitsu.gateway import yoitsu_gateway

router = APIRouter(prefix="/api", tags=["Fiche downloads"])

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data")
DEVICE_DIR = os.path.join(DATA_DIR, "cache", "device")
DEVICE_KEEP = 6 * 3600          # a file the page never fetched is removed after this
SENT_KEEP = 3600                # a file handed to the browser's download manager (no « done » comes back)
DEVICE_BATCHES = 2
VERSION_LABELS = {"vostfr": "VOSTFR", "vf": "VF"}


class FicheDownload(BaseModel):
    """Episodes of a season of a YoitsuWrap fiche (empty list: the whole season)."""
    anime_id: str = Field(..., min_length=3, max_length=300)
    season: str = Field(..., min_length=1, max_length=200)
    version: str = Field("vostfr", pattern="^(vostfr|vf)$")
    episodes: List[int] = Field(default_factory=list, max_length=3000)


FICHE_DOWNLOAD_ERRORS = {
    "not_found": (404, "Saison introuvable dans la fiche."),
    "building": (409, "YoitsuWrap prépare encore la fiche de cet anime : réessayez quand elle est prête."),
    "expired": (409, "YoitsuWrap renouvelle les liens de cet anime : réessayez dans un instant."),
}


async def fiche_download_items(payload: FicheDownload) -> dict:
    if not payload.anime_id.startswith("a-"):
        raise HTTPException(status_code=404, detail="Anime introuvable.")
    found = await yoitsu_gateway.download_items(payload.anime_id, payload.season, payload.version, payload.episodes)
    if found.get("error"):
        code, detail = FICHE_DOWNLOAD_ERRORS[found["error"]]
        raise HTTPException(status_code=code, detail=detail)
    if not found["episodes"]:
        raise HTTPException(status_code=404, detail="Aucun de ces épisodes n'est dans la fiche.")
    return found


def _workers() -> int:
    return int(settings_service.get_settings().get("max_concurrent_downloads") or 3)


@router.post("/downloads/fiche")
async def add_fiche_download(payload: FicheDownload, user_id: str = Depends(require_server_downloads)):
    found = await fiche_download_items(payload)
    tasks = download_service.add_wrapper_season(found["title"], found["label"], payload.version,
                                                found["episodes"], cover=found["cover"], owner=user_id)
    return {"total_added": len(tasks), "tasks": [t.to_dict() for t in tasks]}


class DeviceJobs:
    """Episodes YoitsuWrap downloads for a device: kept in memory, their files in DEVICE_DIR."""

    def __init__(self, folder: str = DEVICE_DIR):
        self.folder = folder
        self._jobs: Dict[str, dict] = {}
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=DEVICE_BATCHES, thread_name_prefix="yoitsu-device")

    def active(self, owner: str) -> int:
        """Episodes this account has being prepared."""
        with self._lock:
            return sum(1 for j in self._jobs.values() if j["owner"] == owner and j["item"].status in ("queued", "downloading"))

    def start(self, found: dict, version: str, workers: int, owner: str = "") -> List[dict]:
        self.purge()
        root = os.path.join(self.folder, uuid.uuid4().hex)
        title, label = found["title"], found["label"]
        items, created = [], []
        for ep in found["episodes"]:
            item = wrapper_download.Item(title=wrapper_download.safe_part(title), season=wrapper_download.safe_part(label),
                                         version=version, num=int(ep["num"]), link=ep["link"],
                                         source=(ep.get("source") or "").upper(), root=root)
            job_id = uuid.uuid4().hex
            job = {"id": job_id, "owner": owner, "item": item, "root": root, "created": time.time(), "anime": title,
                   "season": label, "version": version, "num": int(ep["num"]), "source": ep.get("source") or ""}
            with self._lock:
                self._jobs[job_id] = job
            items.append(item)
            created.append(self.describe(job))
        self._executor.submit(wrapper_download.download_season, items, workers)
        return created

    @staticmethod
    def describe(job: dict) -> dict:
        item = job["item"]
        return {
            "id": job["id"], "anime": job["anime"], "season": job["season"], "version": job["version"],
            "num": job["num"], "source": job["source"], "status": item.status, "progress": item.progress,
            "downloaded": item.downloaded, "total": item.total, "speed": item.speed, "eta": item.eta,
            "error": item.error,
        }

    def get(self, job_id: str, owner: str = None):
        """The job, when it belongs to owner (None: any owner)."""
        with self._lock:
            job = self._jobs.get(job_id)
        return job if job and (owner is None or job["owner"] == owner) else None

    def statuses(self, ids: List[str], owner: str = None) -> List[dict]:
        return [self.describe(job) for job in (self.get(i, owner) for i in ids) if job]

    def remove(self, job_id: str, owner: str = None) -> bool:
        """Cancels the download, or deletes the file once the page has it."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job and (owner is None or job["owner"] == owner):
                self._jobs.pop(job_id)
            else:
                job = None
        if not job:
            return False
        item = job["item"]
        item.cancelled = True
        if item.status in ("completed", "error", "cancelled"):
            try:
                os.remove(item.target)
            except OSError:
                pass
            self._remove_empty(job["root"])
        return True

    def _remove_empty(self, root: str):
        with self._lock:
            if any(j["root"] == root for j in self._jobs.values()):
                return
        shutil.rmtree(root, ignore_errors=True)

    def purge(self):
        """Files nobody fetched (closed page) after DEVICE_KEEP, files sent to a browser after SENT_KEEP."""
        now = time.time()
        limit = now - DEVICE_KEEP
        with self._lock:
            old = [i for i, j in self._jobs.items() if j["item"].status not in ("queued", "downloading")
                   and (j["created"] < limit or j.get("sent_at", now) < now - SENT_KEEP)]
        for job_id in old:
            self.remove(job_id)   # no owner: the purge removes anyone's
        with self._lock:
            live = {j["root"] for j in self._jobs.values()}
        try:
            for name in os.listdir(self.folder):
                path = os.path.join(self.folder, name)
                if path not in live and os.path.getmtime(path) < limit:
                    shutil.rmtree(path, ignore_errors=True)
        except OSError:
            pass


device_jobs = DeviceJobs()


def _content_disposition(name: str) -> str:
    """attachment; ASCII filename for old browsers, filename* (UTF-8) for the others."""
    ascii_name = "".join(c for c in name if 32 <= ord(c) < 127 and c not in '"\\/:*?<>|;') or "episode"
    return f"attachment; filename=\"{ascii_name}.mp4\"; filename*=UTF-8''{quote(name + '.mp4')}"


def _owner_filter(request: Request, user_id: str):
    """The administrator may follow anyone's jobs; the others only their own."""
    return None if is_admin(request) else user_id


@router.post("/device-download/jobs")
async def start_device_download(payload: FicheDownload, request: Request, user_id: str = Depends(session_user_id)):
    settings = settings_service.get_settings()
    limit = int(settings.get("device_max_episodes") or 50)
    if len(payload.episodes) > limit:
        raise HTTPException(status_code=413, detail=f"Au plus {limit} épisodes par demande.")
    ensure_free_space(DEVICE_DIR)   # the episodes go through the server's disk first
    found = await fiche_download_items(payload)
    if len(found["episodes"]) > limit:
        raise HTTPException(status_code=413, detail=f"Au plus {limit} épisodes par demande : choisissez-en moins.")
    active_limit = int(settings.get("device_max_active") or 10)
    active = device_jobs.active(user_id)
    if not is_admin(request) and active + len(found["episodes"]) > active_limit:
        raise HTTPException(status_code=429, detail=(
            f"Vous avez déjà {active} épisode(s) en préparation (au plus {active_limit} à la fois) : "
            "attendez qu'ils soient copiés."))
    return {"jobs": device_jobs.start(found, payload.version, _workers(), owner=user_id)}


@router.get("/device-download/jobs")
async def device_download_status(request: Request, job_id: List[str] = Query(..., alias="id", max_length=200),
                                 user_id: str = Depends(session_user_id)):
    return {"jobs": device_jobs.statuses(job_id, _owner_filter(request, user_id))}


@router.get("/device-download/jobs/{job_id}/file")
async def device_download_file(job_id: str, request: Request, user_id: str = Depends(session_user_id)):
    job = device_jobs.get(job_id, _owner_filter(request, user_id))
    if not job:
        raise HTTPException(status_code=404, detail="Téléchargement introuvable.")
    item = job["item"]
    if item.status != "completed" or not os.path.isfile(item.target):
        raise HTTPException(status_code=409, detail="L'épisode n'est pas encore prêt.")
    job["sent_at"] = time.time()
    name = wrapper_download.safe_part(
        f"{job['anime']} - {job['season']} - {VERSION_LABELS[job['version']]} - ep_{job['num']}")
    return FileResponse(item.target, media_type="video/mp4",
                        headers={"Content-Disposition": _content_disposition(name), "Cache-Control": "no-store"})


@router.delete("/device-download/jobs/{job_id}")
async def remove_device_download(job_id: str, request: Request, user_id: str = Depends(session_user_id)):
    if not device_jobs.remove(job_id, _owner_filter(request, user_id)):
        raise HTTPException(status_code=404, detail="Téléchargement introuvable.")
    return {"status": "removed"}
