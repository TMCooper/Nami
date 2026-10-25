import os
import re
import asyncio
from typing import Optional, List, Dict
from YoitsuWrap.Config import Config
from YoitsuWrap.Anime import Anime
from YoitsuWrap.Scan import Scan
from YoitsuWrap.Season import Season
from YoitsuWrap.Chapter import Chapter
from backend.services.settings_service import settings_service

class YoitsuService:
    def __init__(self):
        self._config = None
        self._cache_scans: Dict[str, Scan] = {}
        self._cache_animes: Dict[str, Anime] = {}

    def get_config(self) -> Config:
        root_path = settings_service.get_root_folder()
        downloads_path = os.path.join(root_path, "nami")
        os.makedirs(downloads_path, exist_ok=True)

        if not self._config:
            self._config = Config.create_config(
                urls=["http://127.0.0.1", "http://127.0.0.1"],
                ports=[5000, 8000],
                path=downloads_path,
                sources=["ANIMESAMA", "VOIRANIME"]
            )
        return self._config

    def get_anime(self, title: str, version: str = "vostfr") -> Optional[Anime]:
        """Fetches or returns cached unified Anime object from YoitsuWrap."""
        cache_key = f"{title.lower()}:{version.lower()}"
        if cache_key in self._cache_animes:
            return self._cache_animes[cache_key]

        cfg = self.get_config()
        try:
            anime_obj = Anime.search_by_name(title=title, config=cfg, version=version)
            if isinstance(anime_obj, Anime):
                self._cache_animes[cache_key] = anime_obj
                # Cache scan if present
                if anime_obj.get_scan():
                    self._cache_scans[title.lower()] = anime_obj.get_scan()
                return anime_obj
        except Exception as e:
            print(f"[YoitsuService] Error searching anime '{title}': {e}")
        return None

    def get_anime_cover(self, title: str) -> Optional[str]:
        """Resolves cover url using YoitsuWrap APIs (/getInfoAnime) directly."""
        cfg = self.get_config()
        import requests
        for conf in cfg.values():
            try:
                r = requests.get(f"{conf.API_LINK}/getInfoAnime", params={"q": title}, timeout=3.0)
                if r.status_code == 200:
                    data = r.json()
                    if isinstance(data, list) and len(data) > 0 and data[0].get("cover"):
                        return data[0]["cover"]
            except Exception:
                pass
        return None

    def get_scan(self, manga_title: str) -> Optional[Scan]:
        """Fetches manga scan object with all chapters via YoitsuWrap."""
        clean_title = manga_title.strip()
        key = clean_title.lower()
        if key in self._cache_scans:
            return self._cache_scans[key]

        cfg = self.get_config()
        try:
            scan_obj = Scan.search_by_name(manga_name=clean_title, config=cfg)
            if isinstance(scan_obj, Scan):
                self._cache_scans[key] = scan_obj
                return scan_obj
        except Exception as e:
            print(f"[YoitsuService] Error fetching scan '{manga_title}': {e}")
        return None

    def get_chapters_summary(self, manga_title: str) -> List[dict]:
        """Returns ordered list of chapters with page counts for frontend consumption."""
        scan = self.get_scan(manga_title)
        if not scan:
            return []

        chapters_dict = scan.get_chapters()
        if not chapters_dict:
            return []

        result = []
        for chap_num in sorted(chapters_dict.keys()):
            ch = chapters_dict[chap_num]
            pages = ch.get_page_link()
            result.append({
                "chapter_num": chap_num,
                "title": f"Chapitre {chap_num}",
                "pages_count": len(pages),
                "pages": pages
            })
        return result

    def get_downloaded_chapters_status(self, manga_title: str) -> dict:
        """Returns a dict {chap_num: {'downloaded': True, 'pages_count': int, 'path': str}} for downloaded chapters."""
        root_path = settings_service.get_root_folder()
        downloads_path = os.path.join(root_path, "nami")
        result = {}

        candidate_dirs = [
            os.path.join(downloads_path, "Anime", manga_title, "Scans"),
            os.path.join(downloads_path, "Anime", manga_title.title(), "Scans"),
            os.path.join(downloads_path, "Anime", manga_title.replace(" ", "_"), "Scans"),
            os.path.join(downloads_path, "Anime", manga_title.replace("-", " "), "Scans"),
        ]

        scans_dir = None
        for cd in candidate_dirs:
            if os.path.exists(cd):
                scans_dir = cd
                break

        if scans_dir and os.path.exists(scans_dir):
            try:
                for entry in os.listdir(scans_dir):
                    full_entry = os.path.join(scans_dir, entry)
                    if os.path.isdir(full_entry):
                        m = re.search(r'\d+', entry)
                        if m:
                            chap_num = str(int(m.group()))
                            img_files = [
                                f for f in os.listdir(full_entry)
                                if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp'))
                            ]
                            if img_files:
                                result[chap_num] = {
                                    "downloaded": True,
                                    "pages_count": len(img_files),
                                    "path": full_entry
                                }
            except Exception as e:
                print(f"[YoitsuService] Error reading local scans: {e}")

        return result

    async def download_chapter(self, manga_title: str, chapter_num: int, images_workers: int = 4) -> dict:
        """Downloads chapter images via YoitsuWrap Chapter.download_chapter, tracked in DownloadService."""
        from backend.services.download_service import download_service

        scan = self.get_scan(manga_title)
        if not scan:
            raise Exception("Scan introuvable pour ce manga.")

        chapters = scan.get_chapters()
        if chapter_num not in chapters:
            raise Exception(f"Chapitre {chapter_num} introuvable.")

        chapter_obj = chapters[chapter_num]

        # Register task in Nami's downloads queue for full visibility
        task = download_service.add_task(
            anime_title=f"{manga_title} [Manga]",
            season="Scans",
            episode_num=f"Chapitre {chapter_num}",
            stream_url=f"yoitsu://scan/{manga_title}/{chapter_num}",
            stream_type="scan"
        )
        task.status = "downloading"
        task.progress = 10.0
        download_service._save_tasks()

        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, chapter_obj.download_chapter, images_workers)

            task.status = "completed"
            task.progress = 100.0
            task.file_path = os.path.join(chapter_obj.path, "Anime", chapter_obj.title, "Scans", chapter_obj.chapter)
            download_service._save_tasks()

            return {
                "status": "success",
                "message": f"Chapitre {chapter_num} de {manga_title} téléchargé avec succès.",
                "file_path": task.file_path
            }
        except Exception as e:
            task.status = "error"
            task.error_message = str(e)
            download_service._save_tasks()
            raise e

    async def download_all_scans(self, manga_title: str, max_workers: int = 2) -> dict:
        """Downloads all chapters via YoitsuWrap Scan.download_scan, tracked in DownloadService."""
        from backend.services.download_service import download_service

        scan = self.get_scan(manga_title)
        if not scan:
            raise Exception("Scan introuvable pour ce manga.")

        task = download_service.add_task(
            anime_title=f"{manga_title} [Manga]",
            season="Scans",
            episode_num="Tous les chapitres",
            stream_url=f"yoitsu://scan/{manga_title}/all",
            stream_type="scan"
        )
        task.status = "downloading"
        task.progress = 10.0
        download_service._save_tasks()

        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, scan.download_scan, None, 4, max_workers)

            task.status = "completed"
            task.progress = 100.0
            task.file_path = os.path.join(scan.path, "Anime", scan.title, "Scans")
            download_service._save_tasks()

            return {
                "status": "success",
                "message": f"Tous les scans de {manga_title} ont été téléchargés avec succès.",
                "file_path": task.file_path
            }
        except Exception as e:
            task.status = "error"
            task.error_message = str(e)
            download_service._save_tasks()
            raise e

yoitsu_service = YoitsuService()

