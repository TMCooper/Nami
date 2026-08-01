import os
import sys
import json
import uuid
import re
import asyncio
import subprocess
import aiohttp
from typing import Dict, List, Optional
from backend.services.settings_service import settings_service

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data")
DOWNLOADS_DB = os.path.join(DATA_DIR, "downloads.json")

def sanitize_filename(name: str) -> str:
    """Sanitize folder and file names for cross-platform compatibility"""
    name = re.sub(r'[\\/*?:"<>|]', "", name)
    return name.strip().replace(" ", "_")

class DownloadTask:
    def __init__(self, anime_title: str, season: str, episode_num: str, stream_url: str, stream_type: str = "m3u8", custom_filename: str = None):
        self.id = str(uuid.uuid4())
        self.anime_title = anime_title
        self.season = season or "Saison_1"
        self.episode_num = str(episode_num)
        self.stream_url = stream_url
        self.stream_type = stream_type.lower()
        self.custom_filename = custom_filename
        self.status = "queued"  # queued, downloading, completed, error, cancelled
        self.progress = 0.0     # 0.0 to 100.0
        self.speed = "0 MB/s"
        self.error_message = ""
        self.file_path = ""
        self.created_at = asyncio.get_event_loop().time()

    def to_dict(self):
        return {
            "id": self.id,
            "anime_title": self.anime_title,
            "season": self.season,
            "episode_num": self.episode_num,
            "stream_url": self.stream_url,
            "stream_type": self.stream_type,
            "status": self.status,
            "progress": round(self.progress, 1),
            "speed": self.speed,
            "error_message": self.error_message,
            "file_path": self.file_path
        }

class DownloadService:
    def __init__(self):
        os.makedirs(DATA_DIR, exist_ok=True)
        self.tasks: Dict[str, DownloadTask] = {}
        self.active_downloads = 0
        self.max_concurrent = 3
        self.worker_task = None
        self._load_tasks()

    def _load_tasks(self):
        if os.path.exists(DOWNLOADS_DB):
            try:
                with open(DOWNLOADS_DB, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for item in data:
                        t = DownloadTask(
                            anime_title=item["anime_title"],
                            season=item["season"],
                            episode_num=item["episode_num"],
                            stream_url=item["stream_url"],
                            stream_type=item.get("stream_type", "m3u8")
                        )
                        t.id = item["id"]
                        t.status = item["status"] if item["status"] != "downloading" else "error"
                        t.progress = item.get("progress", 0.0)
                        t.file_path = item.get("file_path", "")
                        self.tasks[t.id] = t
            except Exception as e:
                print(f"[DownloadService] Error loading tasks DB: {e}")

    def _save_tasks(self):
        try:
            with open(DOWNLOADS_DB, "w", encoding="utf-8") as f:
                json.dump([t.to_dict() for t in self.tasks.values()], f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[DownloadService] Error saving tasks DB: {e}")

    def add_task(self, anime_title: str, season: str, episode_num: str, stream_url: str, stream_type: str = "m3u8") -> DownloadTask:
        task = DownloadTask(
            anime_title=anime_title,
            season=season,
            episode_num=episode_num,
            stream_url=stream_url,
            stream_type=stream_type
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
            self._save_tasks()
            return True
        return False

    def clear_completed(self):
        self.tasks = {k: v for k, v in self.tasks.items() if v.status not in ["completed", "cancelled", "error"]}
        self._save_tasks()

    async def _process_queue(self):
        queued_tasks = [t for t in self.tasks.values() if t.status == "queued"]
        for task in queued_tasks:
            if self.active_downloads >= self.max_concurrent:
                break
            task.status = "downloading"
            self.active_downloads += 1
            asyncio.create_task(self._download_task(task))

    async def _download_task(self, task: DownloadTask):
        try:
            root_folder = settings_service.get_root_folder()
            safe_anime = sanitize_filename(task.anime_title)
            safe_season = sanitize_filename(task.season)
            ep_name = f"Episode_{task.episode_num}.mp4"

            # Create output directory structure: root/nami/anime/{anime_title}/{season}/{ep_name}
            output_dir = os.path.join(root_folder, "nami", "anime", safe_anime, safe_season)
            os.makedirs(output_dir, exist_ok=True)
            output_file = os.path.join(output_dir, ep_name)
            task.file_path = output_file

            print(f"[DownloadService] Starting download for {task.anime_title} Ep {task.episode_num} -> {output_file}")

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
        # Use ffmpeg command line to download m3u8 stream
        cmd = [
            "ffmpeg", "-y",
            "-headers", "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64)\r\n",
            "-i", task.stream_url,
            "-c", "copy",
            "-bsf:a", "aac_adtstoasc",
            output_file
        ]
        
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        while proc.returncode is None:
            if task.status == "cancelled":
                try:
                    proc.kill()
                except Exception:
                    pass
                return
            await asyncio.sleep(1)
            # Simulating steady progress update for ffmpeg task
            if task.progress < 95.0:
                task.progress += 2.5
            self._save_tasks()

        await proc.wait()
        if proc.returncode != 0:
            stderr_bytes = await proc.stderr.read()
            stderr_msg = stderr_bytes.decode("utf-8", errors="ignore")
            # If ffmpeg failed, fallback to direct download or report error
            raise Exception(f"FFmpeg error: {stderr_msg[-200:]}")

    async def _download_http_file(self, task: DownloadTask, output_file: str):
        async with aiohttp.ClientSession() as session:
            async with session.get(task.stream_url) as resp:
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
                        self._save_tasks()

download_service = DownloadService()
