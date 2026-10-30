import os
import sys
import time
import uuid
import re
import asyncio
import threading
import subprocess
import aiohttp
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional
from backend.services.settings_service import settings_service
from backend.services.storage import load_json, save_json
from backend.services.http_headers import USER_AGENT, stream_referer
from backend.services import wrapper_download

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data")
DOWNLOADS_DB = os.path.join(DATA_DIR, "downloads.json")
WRAPPER_BATCHES = 2     # seasons downloaded at the same time; their episodes run in parallel inside YoitsuWrap

def sanitize_filename(name: str) -> str:
    """Sanitize folder and file names for cross-platform compatibility"""
    name = re.sub(r'[\\/*?:"<>|]', "", name)
    return name.strip().replace(" ", "_")


def resolve_anime_folder(base_dir: str, anime_title: str) -> str:
    """Folder name of an anime under base_dir: an existing folder of the same title variant
    ("Re:Zero" vs "Re Zero") is reused so downloads of one anime stay together."""
    candidate = sanitize_filename(anime_title)
    if os.path.isdir(os.path.join(base_dir, candidate)):
        return candidate
    from backend.services.cover_utils import normalize_title_key
    # Compared without spaces: sanitize_filename drops ':' without a space ("Re:Zero" -> "ReZero")
    wanted = normalize_title_key(anime_title).replace(" ", "")
    try:
        for folder in os.listdir(base_dir):
            if normalize_title_key(folder).replace(" ", "") == wanted and os.path.isdir(os.path.join(base_dir, folder)):
                return folder
    except OSError:
        pass
    return candidate

def _needs_resolution(url: str) -> bool:
    return "voir-anime.to" in url or ("http" in url and not any(ext in url for ext in [".m3u8", ".mp4", ".ts"]))


class DownloadTask:
    def __init__(self, anime_title: str, season: str, episode_num: str, stream_url: str, stream_type: str = "m3u8", custom_filename: str = None,
                 fallback_urls: Optional[List[str]] = None, owner: str = ""):
        self.id = str(uuid.uuid4())
        self.owner = owner   # the account that asked for it
        self.anime_title = anime_title
        self.season = season or "Saison_1"
        self.episode_num = str(episode_num)
        self.stream_url = stream_url
        # Other players of the episode, tried in order when stream_url does not resolve
        self.fallback_urls = [u for u in (fallback_urls or []) if isinstance(u, str) and u and u != stream_url]
        self.stream_type = stream_type.lower()
        self.custom_filename = custom_filename
        self.status = "queued"  # queued, downloading, completed, error, cancelled
        self.progress = 0.0     # 0.0 to 100.0
        self.speed = "0 MB/s"
        self.error_message = ""
        self.file_path = ""
        self.created_at = time.time()
        # YoitsuWrap downloads (mode "wrapper"): the verified link of the fiche, downloaded by YoitsuWrap
        self.mode = "legacy"
        self.version = ""
        self.source = ""
        self.downloaded_bytes = 0
        self.total_bytes = 0
        self.eta = None

    def to_dict(self):
        return {
            "id": self.id,
            "anime_title": self.anime_title,
            "season": self.season,
            "episode_num": self.episode_num,
            "stream_url": self.stream_url,
            "stream_type": self.stream_type,
            "fallback_urls": self.fallback_urls,
            "status": self.status,
            "progress": round(self.progress, 1),
            "speed": self.speed,
            "error_message": self.error_message,
            "file_path": self.file_path,
            "mode": self.mode,
            "owner": self.owner,
            "version": self.version,
            "source": self.source,
            "downloaded_bytes": self.downloaded_bytes,
            "total_bytes": self.total_bytes,
            "eta": self.eta
        }

def normalize_anime_and_season(anime_title: str, season: str):
    t_clean = anime_title.strip()
    s_clean = season.strip()
    
    # Specific handling for High School DxD franchise
    if re.search(r'high school dxd new', t_clean, re.IGNORECASE):
        return "High School DxD", "Saison 2"
    if re.search(r'high school dxd born', t_clean, re.IGNORECASE):
        return "High School DxD", "Saison 3"
    if re.search(r'high school dxd hero', t_clean, re.IGNORECASE):
        return "High School DxD", "Saison 4"
    if re.search(r'high school dxd (?:ova|oav)', t_clean, re.IGNORECASE):
        return "High School DxD", "OAV"

    # General sequel patterns
    m_sec = re.search(r'^(.*?)\s+(?:2nd|second)\s*season$', t_clean, re.IGNORECASE)
    if m_sec:
        return m_sec.group(1), "Saison 2"
    m_3rd = re.search(r'^(.*?)\s+(?:3rd|third)\s*season$', t_clean, re.IGNORECASE)
    if m_3rd:
        return m_3rd.group(1), "Saison 3"
    m_4th = re.search(r'^(.*?)\s+(?:4th|fourth)\s*season$', t_clean, re.IGNORECASE)
    if m_4th:
        return m_4th.group(1), "Saison 4"

    return t_clean, s_clean

class DownloadService:
    def __init__(self):
        os.makedirs(DATA_DIR, exist_ok=True)
        self.tasks: Dict[str, DownloadTask] = {}
        self.active_downloads = 0
        self.max_concurrent = 3
        self.worker_task = None
        self._last_save = 0.0
        self._save_lock = threading.Lock()
        self._wrapper_items: Dict[str, wrapper_download.Item] = {}
        self._batches = ThreadPoolExecutor(max_workers=WRAPPER_BATCHES, thread_name_prefix="yoitsu-download")
        self._load_tasks()

    def _load_tasks(self):
        if os.path.exists(DOWNLOADS_DB):
            try:
                data = load_json(DOWNLOADS_DB, list)
                if isinstance(data, list):
                    for item in data:
                        t = DownloadTask(
                            anime_title=item["anime_title"],
                            season=item["season"],
                            episode_num=item["episode_num"],
                            stream_url=item["stream_url"],
                            stream_type=item.get("stream_type", "m3u8"),
                            fallback_urls=item.get("fallback_urls")
                        )
                        t.id = item["id"]
                        t.owner = item.get("owner", "")
                        t.mode = item.get("mode", "legacy")
                        t.version = item.get("version", "")
                        t.source = item.get("source", "")
                        t.status = item["status"] if item["status"] != "downloading" else "error"
                        if t.mode == "wrapper" and t.status == "queued":
                            t.status = "error"   # its YoitsuWrap batch ended with the previous run
                        if t.status == "error" and not item.get("error_message") and item["status"] != "error":
                            t.error_message = "Interrompu par l'arrêt du serveur"
                        else:
                            t.error_message = item.get("error_message", "")
                        t.progress = item.get("progress", 0.0)
                        t.file_path = item.get("file_path", "")
                        self.tasks[t.id] = t
            except Exception as e:
                print(f"[DownloadService] Error loading tasks DB: {e}")

    def _save_tasks(self, force: bool = True):
        # Progress updates (force=False) are written at most once per second
        now = time.monotonic()
        if not force and now - self._last_save < 1.0:
            return
        self._last_save = now
        try:
            with self._save_lock:   # YoitsuWrap batches report from their own threads
                save_json(DOWNLOADS_DB, [t.to_dict() for t in list(self.tasks.values())])
        except Exception as e:
            print(f"[DownloadService] Error saving tasks DB: {e}")

    def add_task(self, anime_title: str, season: str, episode_num: str, stream_url: str, stream_type: str = "m3u8",
                 fallback_urls: Optional[List[str]] = None, owner: str = "") -> DownloadTask:
        task = DownloadTask(
            anime_title=anime_title,
            season=season,
            episode_num=episode_num,
            stream_url=stream_url,
            stream_type=stream_type,
            fallback_urls=fallback_urls,
            owner=owner
        )
        self.tasks[task.id] = task
        self._save_tasks()
        
        # Trigger background queue processor
        asyncio.create_task(self._process_queue())
        return task

    def get_all_tasks(self) -> List[dict]:
        return [t.to_dict() for t in self.tasks.values()]

    def cancel_task(self, task_id: str) -> bool:
        if task_id in self.tasks:
            self.tasks[task_id].status = "cancelled"
            item = self._wrapper_items.get(task_id)
            if item is not None:
                item.cancelled = True   # its yt-dlp stops at the next progress report
            self._save_tasks()
            return True
        return False

    def clear_completed(self, owner: Optional[str] = None):
        """Finished downloads leave the list: everyone's, or only those of one account."""
        self.tasks = {k: v for k, v in self.tasks.items()
                      if v.status not in ["completed", "cancelled", "error"] or (owner is not None and v.owner != owner)}
        self._save_tasks()

    # --- YoitsuWrap downloads ---
    def add_wrapper_season(self, anime_title: str, season_label: str, version: str, episodes: List[dict],
                           cover: str = "", owner: str = "") -> List[DownloadTask]:
        """Episodes of one season of a fiche, downloaded by YoitsuWrap (Season.download_season) in parallel.

        episodes: [{num, link, source}] (links verified by YoitsuWrap). Files land where YoitsuWrap puts
        them: <root>/nami/Anime/<anime>/<season>/<version>/<n>.mp4.
        """
        root = os.path.join(settings_service.get_root_folder(), "nami")
        folder = resolve_anime_folder(os.path.join(root, "Anime"), anime_title)
        season_folder = wrapper_download.safe_part(sanitize_filename(season_label) or "Saison_1")
        season_name = season_label if version == "vostfr" else f"{season_label} VF"
        tasks, items = [], []
        for ep in episodes:
            task = DownloadTask(anime_title=anime_title, season=season_name, episode_num=str(ep["num"]),
                                stream_url=ep["link"], stream_type="wrapper", owner=owner)
            task.mode, task.version, task.source = "wrapper", version, ep.get("source") or ""
            item = wrapper_download.Item(title=folder, season=season_folder, version=version, num=int(ep["num"]),
                                         link=ep["link"], source=(ep.get("source") or "").upper(), root=root)
            item.on_change = lambda it, t=task: self._follow(t, it)
            task.file_path = item.target
            self.tasks[task.id] = task
            self._wrapper_items[task.id] = item
            tasks.append(task)
            items.append(item)
        self._save_tasks()
        if cover:
            self._save_cover(os.path.join(root, "Anime", folder), cover)
        workers = int(settings_service.get_settings().get("max_concurrent_downloads") or 3)
        self._batches.submit(self._run_batch, items, workers, [t.id for t in tasks])
        return tasks

    def _follow(self, task: DownloadTask, item: wrapper_download.Item):
        if task.status == "cancelled" and item.status not in ("cancelled",):
            item.cancelled = True
            return
        task.status = item.status
        task.progress = item.progress
        task.downloaded_bytes, task.total_bytes, task.eta = item.downloaded, item.total, item.eta
        task.speed = wrapper_download.format_speed(item.speed) if item.status == "downloading" else (
            "Terminé" if item.status == "completed" else "")
        task.error_message = item.error if item.status == "error" else ""
        if item.status == "completed":
            task.file_path = item.file_path
        self._save_tasks(force=item.status != "downloading")

    def _run_batch(self, items: List[wrapper_download.Item], workers: int, task_ids: List[str]):
        try:
            # Episodes cancelled while queued never start
            pending = [i for i, tid in zip(items, task_ids) if self.tasks.get(tid) and self.tasks[tid].status != "cancelled"]
            wrapper_download.download_season(pending, workers)
        except Exception as e:
            print(f"[DownloadService] YoitsuWrap batch failed: {e}")
            for item, tid in zip(items, task_ids):
                task = self.tasks.get(tid)
                if task and task.status in ("queued", "downloading"):
                    task.status, task.error_message = "error", str(e)[:200]
        finally:
            for tid in task_ids:
                self._wrapper_items.pop(tid, None)
            self._save_tasks()

    @staticmethod
    def _save_cover(anime_dir: str, cover: str):
        """cover.jpg of the anime folder (the offline library shows it)."""
        try:
            os.makedirs(anime_dir, exist_ok=True)
            dest = os.path.join(anime_dir, "cover.jpg")
            if not os.path.exists(dest) or os.path.getsize(dest) < 1000:
                from backend.services.cache_service import cache_service
                cache_service._save_local_cover_async(cover, anime_dir)
        except Exception as e:
            print(f"[DownloadService] Warning saving cover.jpg: {e}")

    async def _process_queue(self):
        queued_tasks = [t for t in self.tasks.values() if t.status == "queued" and t.mode != "wrapper"]
        for task in queued_tasks:
            if self.active_downloads >= self.max_concurrent:
                break
            task.status = "downloading"
            self.active_downloads += 1
            asyncio.create_task(self._download_task(task))

    async def _download_task(self, task: DownloadTask):
        try:
            root_folder = settings_service.get_root_folder()
            norm_anime, norm_season = normalize_anime_and_season(task.anime_title, task.season)
            safe_anime = resolve_anime_folder(os.path.join(root_folder, "nami", "anime"), norm_anime)
            safe_season = sanitize_filename(norm_season)

            # Auto-save anime cover.jpg if missing
            anime_dir = os.path.join(root_folder, "nami", "anime", safe_anime)
            os.makedirs(anime_dir, exist_ok=True)
            cover_dest = os.path.join(anime_dir, "cover.jpg")
            if not os.path.exists(cover_dest) or os.path.getsize(cover_dest) < 1000:
                try:
                    from backend.services.cache_service import cache_service
                    cov_url = cache_service._find_anime_cover(norm_anime, anime_dir)
                    if not cov_url:
                        from backend.services.cover_registry import cover_registry
                        cov_url = cover_registry.lookup(task.anime_title) or cover_registry.lookup(norm_anime)
                    if cov_url:
                        cache_service._save_local_cover_async(cov_url, anime_dir)
                except Exception as cov_err:
                    print(f"[DownloadService] Warning saving cover.jpg: {cov_err}")

            # Sanitize episode number: extract the actual number to avoid long dirty names
            nums = re.findall(r'\d+', str(task.episode_num))
            if nums:
                clean_ep_num = str(int(nums[-1])).zfill(2)
            else:
                clean_ep_num = "01"
            ep_name = f"Episode_{clean_ep_num}.mp4"

            # Auto-resolve stream if it's a page or embed link (then the episode's other players)
            if _needs_resolution(task.stream_url):
                from backend.services.catalog_service import catalog_service
                for candidate in [task.stream_url, *task.fallback_urls]:
                    if not _needs_resolution(candidate):
                        task.stream_url = candidate
                        break
                    try:
                        resolved = await catalog_service.resolve_stream(candidate)
                    except Exception as e:
                        print(f"[DownloadService] Stream pre-resolution error ({candidate}): {e}")
                        continue
                    if resolved and resolved.get("stream_url"):
                        task.stream_url = resolved["stream_url"]
                        task.stream_type = resolved.get("stream_type", "m3u8")
                        break

            # Create output directory structure: root/nami/anime/{anime_title}/{season}/{ep_name}
            output_dir = os.path.join(anime_dir, safe_season)
            os.makedirs(output_dir, exist_ok=True)
            output_file = os.path.join(output_dir, ep_name)
            task.file_path = output_file

            print(f"[DownloadService] Starting download for {norm_anime} ({norm_season}) Ep {clean_ep_num} -> {output_file}")

            if task.stream_type == "m3u8" or ".m3u8" in task.stream_url:
                await self._download_hls_ffmpeg(task, output_file)
            else:
                await self._download_http_file(task, output_file)

            if task.status != "cancelled":
                task.status = "completed"
                task.progress = 100.0
                task.speed = "Terminé"
        except Exception as e:
            print(f"[DownloadService] Error downloading task {task.id}: {e}")
            task.status = "error"
            task.error_message = str(e)
        finally:
            self.active_downloads = max(0, self.active_downloads - 1)
            self._save_tasks()
            asyncio.create_task(self._process_queue())

    async def _download_hls_ffmpeg(self, task: DownloadTask, output_file: str):
        # 1. Try ffmpeg command line to download m3u8 stream
        header_lines = f"User-Agent: {USER_AGENT}\r\n"
        referer = stream_referer(task.stream_url)
        if referer:
            header_lines += f"Referer: {referer}\r\n"
        cmd = [
            "ffmpeg", "-y",
            "-loglevel", "error", "-nostats",
            "-headers", header_lines,
            "-i", task.stream_url,
            "-c", "copy",
            "-bsf:a", "aac_adtstoasc",
            output_file
        ]
        
        proc = None
        try:
            # Output is discarded: an unread PIPE fills up and stalls ffmpeg on long downloads
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL
            )

            while proc.returncode is None:
                if task.status == "cancelled":
                    try:
                        proc.kill()
                    except Exception:
                        pass
                    return
                await asyncio.sleep(1)
                if task.progress < 95.0:
                    task.progress += 2.5
                self._save_tasks(force=False)

            await proc.wait()
            if proc.returncode == 0 and os.path.exists(output_file) and os.path.getsize(output_file) > 1000:
                return
        except Exception as e:
            print(f"[DownloadService] ffmpeg execution error: {e}")

        # 2. Fallback to yt-dlp if ffmpeg failed or exited with error
        print(f"[DownloadService] FFmpeg failed, running yt-dlp fallback for {task.anime_title}...")
        yt_cmd = [
            sys.executable, "-m", "yt_dlp",
            "--no-check-certificates",
            "--no-progress",
            "--user-agent", USER_AGENT,
            "-o", output_file,
        ]
        if referer:
            yt_cmd += ["--referer", referer]
        yt_cmd.append(task.stream_url)
        yt_proc = await asyncio.create_subprocess_exec(
            *yt_cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE
        )
        _, stderr_b = await yt_proc.communicate()
        if yt_proc.returncode != 0:
            raise Exception(f"Download failed: {stderr_b.decode('utf-8', errors='ignore')[-200:]}")

    async def _download_http_file(self, task: DownloadTask, output_file: str):
        headers = {"User-Agent": USER_AGENT}
        referer = stream_referer(task.stream_url)
        if referer:
            headers["Referer"] = referer
        async with aiohttp.ClientSession() as session:
            async with session.get(task.stream_url, headers=headers) as resp:
                if resp.status != 200:
                    raise Exception(f"HTTP Error {resp.status}")

                total_size = int(resp.headers.get("content-length", 0))
                downloaded = 0
                start_time = asyncio.get_event_loop().time()

                with open(output_file, "wb") as f:
                    async for chunk in resp.content.iter_chunked(1024 * 64):
                        if task.status == "cancelled":
                            return
                        f.write(chunk)
                        downloaded += len(chunk)

                        if total_size > 0:
                            task.progress = (downloaded / total_size) * 100.0

                        elapsed = max(0.1, asyncio.get_event_loop().time() - start_time)
                        speed_mb = (downloaded / (1024 * 1024)) / elapsed
                        task.speed = f"{round(speed_mb, 2)} MB/s"
                        self._save_tasks(force=False)

download_service = DownloadService()
