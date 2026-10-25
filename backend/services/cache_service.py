import os
import time
import random
import re
import threading
import httpx
from typing import Optional, List, Dict
from urllib.parse import quote, urlparse

from backend.services.storage import load_json, save_json
from backend.services.cover_utils import raw_cover_url, is_usable_cover, is_trusted_cover, client_cover_url
from backend.services.http_headers import USER_AGENT, image_referer
from backend.services.image_service import sniff_image_type, MIN_IMAGE_BYTES

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data")
CACHE_DIR = os.path.join(DATA_DIR, "cache")
ANIME_CACHE_DIR = os.path.join(CACHE_DIR, "animes")
RECENT_FILE = os.path.join(CACHE_DIR, "recent.json")
DETAILS_TTL = 86400 * 3
EPISODES_CACHE_PREFIX = "anime_sama_eps_"

# Starter recommendations for instant discovery even before scraping full catalogs
POPULAR_STARTER_ANIMES = [
    {"title": "Frieren", "source": "anime_sama", "url": "https://anime-sama.to/catalogue/frieren/", "cover": "https://raw.githubusercontent.com/Anime-Sama/IMG/img/contenu/frieren.jpg"},
    {"title": "Jujutsu Kaisen", "source": "anime_sama", "url": "https://anime-sama.to/catalogue/jujutsu-kaisen/", "cover": "https://raw.githubusercontent.com/Anime-Sama/IMG/img/contenu/jujutsu-kaisen.jpg"},
    {"title": "Demon Slayer", "source": "anime_sama", "url": "https://anime-sama.to/catalogue/demon-slayer/", "cover": "https://raw.githubusercontent.com/Anime-Sama/IMG/img/contenu/demon-slayer.jpg"},
    {"title": "One Piece", "source": "anime_sama", "url": "https://anime-sama.to/catalogue/one-piece/", "cover": "https://raw.githubusercontent.com/Anime-Sama/IMG/img/contenu/one-piece.jpg"},
    {"title": "Solo Leveling", "source": "anime_sama", "url": "https://anime-sama.to/catalogue/solo-leveling/", "cover": "https://raw.githubusercontent.com/Anime-Sama/IMG/img/contenu/solo-leveling.jpg"},
    {"title": "L'Attaque des Titans", "source": "anime_sama", "url": "https://anime-sama.to/catalogue/shingeki-no-kyojin/", "cover": "https://raw.githubusercontent.com/Anime-Sama/IMG/img/contenu/shingeki-no-kyojin.jpg"},
    {"title": "Chainsaw Man", "source": "anime_sama", "url": "https://anime-sama.to/catalogue/chainsaw-man/", "cover": "https://raw.githubusercontent.com/Anime-Sama/IMG/img/contenu/chainsaw-man.jpg"},
    {"title": "Hunter x Hunter", "source": "anime_sama", "url": "https://anime-sama.to/catalogue/hunter-x-hunter/", "cover": "https://raw.githubusercontent.com/Anime-Sama/IMG/img/contenu/hunter-x-hunter.jpg"},
    {"title": "Bleach", "source": "anime_sama", "url": "https://anime-sama.to/catalogue/bleach/", "cover": "https://raw.githubusercontent.com/Anime-Sama/IMG/img/contenu/bleach.jpg"},
    {"title": "Mashle", "source": "anime_sama", "url": "https://anime-sama.to/catalogue/mashle/", "cover": "https://raw.githubusercontent.com/Anime-Sama/IMG/img/contenu/mashle.jpg"},
    {"title": "Spy x Family", "source": "anime_sama", "url": "https://anime-sama.to/catalogue/spy-x-family/", "cover": "https://raw.githubusercontent.com/Anime-Sama/IMG/img/contenu/spy-x-family.jpg"},
    {"title": "Oshi no Ko", "source": "anime_sama", "url": "https://anime-sama.to/catalogue/oshi-no-ko/", "cover": "https://raw.githubusercontent.com/Anime-Sama/IMG/img/contenu/oshi-no-ko.jpg"},
]

def sanitize_cache_key(key: str) -> str:
    return re.sub(r'[^a-zA-Z0-9_\-]', '_', key.strip().lower())

def anime_identity(source: str, url: str, title: str = "") -> str:
    """Stable key for one source entry: the URL slug survives domain changes and trailing slashes."""
    slug = urlparse(url or "").path.rstrip("/").split("/")[-1].lower()
    if slug:
        return f"{source or 'anime_sama'}:{slug}"
    return f"title:{(title or '').strip().lower()}"

class CacheService:
    def __init__(self):
        os.makedirs(ANIME_CACHE_DIR, exist_ok=True)
        self._recent_lock = threading.Lock()
        self.recent_data: Dict[str, List[dict]] = self._load_recent()

    def _load_recent(self) -> dict:
        data = load_json(RECENT_FILE, dict)
        return data if isinstance(data, dict) else {}

    def _save_recent(self):
        try:
            save_json(RECENT_FILE, self.recent_data)
        except Exception as e:
            print(f"[CacheService] Error saving recent file: {e}")

    # --- Anime Details Caching ---
    def _details_path(self, source: str, key: str) -> str:
        return os.path.join(ANIME_CACHE_DIR, f"{source}_{sanitize_cache_key(key)}.json")

    def get_anime_details(self, source: str, key: str) -> Optional[dict]:
        data = load_json(self._details_path(source, key), dict)
        # Cache valid for 3 days
        if isinstance(data, dict) and time.time() - data.get("_cached_at", 0) < DETAILS_TTL:
            return data.get("content")
        return None

    def save_anime_details(self, source: str, key: str, content):
        try:
            save_json(self._details_path(source, key), {"_cached_at": time.time(), "content": content})
        except Exception as e:
            print(f"[CacheService] Error saving cache {source}:{key}: {e}")

    # --- Recent Viewed & Searched Animes ---
    def add_recent_anime(self, user_id: str, anime: dict):
        if not anime or not anime.get("title"):
            return
        uid = user_id or "default"
        source = anime.get("source", "anime_sama")
        identity = anime_identity(source, anime.get("url", ""), anime.get("title", ""))
        title_lower = anime.get("title", "").lower()
        cover = anime.get("cover", "")

        entry = {
            "title": anime.get("title"),
            "url": anime.get("url", ""),
            "source": source,
            # Raw upstream URL; placeholders are never stored
            "cover": raw_cover_url(cover) if is_usable_cover(cover) else "",
            "viewed_at": time.time()
        }
        with self._recent_lock:
            user_recents = self.recent_data.get(uid, [])
            # Remove existing if duplicate (same entry or same title)
            filtered = [
                a for a in user_recents
                if a.get("title", "").lower() != title_lower
                and anime_identity(a.get("source", "anime_sama"), a.get("url", ""), a.get("title", "")) != identity
            ]
            filtered.insert(0, entry)
            self.recent_data[uid] = filtered[:24]  # Keep up to 24
        self._save_recent()

    @staticmethod
    def _has_good_cover(entry: dict) -> bool:
        cover = entry.get("cover", "")
        return is_usable_cover(cover) and is_trusted_cover(cover, entry.get("source", "anime_sama"))

    def get_recent_animes(self, user_id: str) -> List[dict]:
        """Recent entries with browser-loadable covers. Missing covers are repaired in the background (see catalog_service)."""
        uid = user_id or "default"
        return [
            {**a, "cover": client_cover_url(a.get("cover", "")) if self._has_good_cover(a) else ""}
            for a in list(self.recent_data.get(uid, []))
        ]

    def recents_missing_cover(self, user_id: str) -> List[dict]:
        return [a for a in list(self.recent_data.get(user_id or "default", [])) if not self._has_good_cover(a)]

    def set_recent_cover(self, user_id: str, source: str, url: str, title: str, cover: str):
        if not is_usable_cover(cover):
            return
        identity = anime_identity(source, url, title)
        changed = False
        with self._recent_lock:
            for a in self.recent_data.get(user_id or "default", []):
                if anime_identity(a.get("source", "anime_sama"), a.get("url", ""), a.get("title", "")) == identity:
                    a["cover"] = raw_cover_url(cover)
                    changed = True
        if changed:
            self._save_recent()

    # --- Random / Starter Animes ---
    def get_random_animes(self, count: int = 12) -> List[dict]:
        pool = list(POPULAR_STARTER_ANIMES)

        # Also include cached anime details (one bad file must not stop the scan)
        try:
            names = os.listdir(ANIME_CACHE_DIR)
        except OSError:
            names = []
        for fname in names:
            if not fname.endswith(".json") or fname.startswith(EPISODES_CACHE_PREFIX):
                continue
            data = load_json(os.path.join(ANIME_CACHE_DIR, fname), dict)
            item = data.get("content") if isinstance(data, dict) else None
            if isinstance(item, dict) and item.get("title"):
                pool.append({
                    "title": item["title"],
                    "url": item.get("url", ""),
                    "source": item.get("source", "anime_sama"),
                    "cover": item.get("cover", "")
                })

        # Deduplicate by title and by source entry (e.g. "L'Attaque des Titans" and "Shingeki no Kyojin" share one URL)
        seen = set()
        deduped = []
        for a in pool:
            keys = {f"title:{a['title'].lower()}", anime_identity(a.get("source"), a.get("url", ""), a["title"])}
            if not keys & seen:
                seen |= keys
                good = is_trusted_cover(a.get("cover", ""), a.get("source", "anime_sama"))
                deduped.append({**a, "cover": client_cover_url(a.get("cover", "")) if good else ""})

        random.shuffle(deduped)
        return deduped[:count]

    def _save_local_cover_async(self, cover_url: str, anime_path: str):
        """Asynchronously fetches and saves the cover image to cover.jpg inside anime folder."""
        target = raw_cover_url(cover_url)
        if not target.startswith(("http://", "https://")):
            return

        def _fetch_and_save():
            try:
                dest = os.path.join(anime_path, "cover.jpg")
                if os.path.exists(dest) and os.path.getsize(dest) > 1000:
                    return
                headers = {"User-Agent": USER_AGENT}
                referer = image_referer(target)
                if referer:
                    headers["Referer"] = referer
                with httpx.Client(timeout=10.0, follow_redirects=True) as client:
                    resp = client.get(target, headers=headers)
                    # Only real images: an HTML error page must not become cover.jpg
                    if resp.status_code == 200 and len(resp.content) >= MIN_IMAGE_BYTES and sniff_image_type(resp.content[:32]):
                        tmp_dest = f"{dest}.tmp"
                        with open(tmp_dest, "wb") as f:
                            f.write(resp.content)
                        os.replace(tmp_dest, dest)
            except Exception:
                pass

        t = threading.Thread(target=_fetch_and_save, daemon=True)
        t.start()

    def _find_anime_cover(self, display_title: str, anime_path: str) -> str:
        # 1. Local cover on disk
        for ext in [".jpg", ".jpeg", ".png", ".webp"]:
            local_cov = os.path.join(anime_path, f"cover{ext}")
            if os.path.exists(local_cov) and os.path.getsize(local_cov) > 1000:
                return f"/api/stream/local?file_path={quote(local_cov)}"
            poster_cov = os.path.join(anime_path, f"poster{ext}")
            if os.path.exists(poster_cov) and os.path.getsize(poster_cov) > 1000:
                return f"/api/stream/local?file_path={quote(poster_cov)}"

        clean_name = display_title.lower().strip()

        # 2. History database
        from backend.services.history_service import history_service
        # Snapshots: this runs in a worker thread while requests may add titles to the live dicts
        for user_records in list(history_service.history.values()):
            if isinstance(user_records, dict):
                for atitle, rec in list(user_records.items()):
                    cov_url = rec.get("cover", "") if isinstance(rec, dict) else ""
                    if atitle.lower().strip() == clean_name and is_usable_cover(cov_url):
                        self._save_local_cover_async(cov_url, anime_path)
                        return client_cover_url(cov_url)

        # 3. Cover registry (exact normalized title, never a substring match)
        from backend.services.cover_registry import cover_registry
        reg_cover = cover_registry.lookup(display_title)
        if reg_cover:
            self._save_local_cover_async(reg_cover, anime_path)
            return client_cover_url(reg_cover)

        # 4. Popular starter list
        for starter in POPULAR_STARTER_ANIMES:
            if starter.get("title", "").lower().strip() == clean_name:
                c = starter.get("cover", "")
                if c:
                    self._save_local_cover_async(c, anime_path)
                    return c

        # 5. Fallback to Anime-Sama Statically CDN by slug
        clean_slug = re.sub(r'[^a-z0-9]+', '-', clean_name).strip('-')
        if clean_slug:
            as_cdn = f"https://cdn.statically.io/gh/Anime-Sama/IMG/img/contenu/{clean_slug}.jpg"
            self._save_local_cover_async(as_cdn, anime_path)
            return as_cdn

        return ""

    # --- Scan Local Downloaded Media on Disk ---
    def scan_downloaded_library(self, root_folder: str) -> List[dict]:
        candidate_bases = [
            os.path.join(root_folder, "nami", "anime"),
            os.path.join(root_folder, "nami", "Anime"),
        ]

        results = []
        seen_titles = set()

        for base_dir in candidate_bases:
            if not os.path.exists(base_dir):
                continue

            try:
                for anime_folder in os.listdir(base_dir):
                    anime_path = os.path.join(base_dir, anime_folder)
                    if not os.path.isdir(anime_path):
                        continue

                    display_title = anime_folder.replace("_", " ")
                    if display_title.lower() in seen_titles:
                        continue

                    cover = self._find_anime_cover(display_title, anime_path)
                    seasons_found = []

                    for season_folder in os.listdir(anime_path):
                        season_path = os.path.join(anime_path, season_folder)
                        if not os.path.isdir(season_path):
                            continue

                        display_season = season_folder.replace("_", " ")

                        # Check if this is a Manga Scans folder
                        if season_folder.lower() == "scans":
                            chapters_found = []
                            for chap_entry in sorted(os.listdir(season_path)):
                                chap_path = os.path.join(season_path, chap_entry)
                                if os.path.isdir(chap_path):
                                    m = re.search(r'\d+', chap_entry)
                                    chap_num = int(m.group()) if m else 1
                                    img_files = sorted(
                                        [f for f in os.listdir(chap_path) if f.lower().endswith(('.jpg', '.jpeg', '.png', '.webp'))],
                                        key=lambda x: [int(c) if c.isdigit() else c for c in re.split(r'(\d+)', x)]
                                    )
                                    if img_files:
                                        chap_size_mb = round(sum(os.path.getsize(os.path.join(chap_path, f)) for f in img_files) / (1024 * 1024), 1)
                                        full_pages = [os.path.join(chap_path, f).replace("\\", "/") for f in img_files]
                                        chapters_found.append({
                                            "num": chap_num,
                                            "title": chap_entry if "chap" in chap_entry.lower() else f"Chapitre {chap_num}",
                                            "filename": chap_entry,
                                            "file_path": chap_path,
                                            "pages_count": len(img_files),
                                            "pages": full_pages,
                                            "size_mb": chap_size_mb,
                                            "is_scan": True,
                                            "is_downloaded": True
                                        })
                            if chapters_found:
                                chapters_found.sort(key=lambda x: x["num"])
                                seasons_found.append({
                                    "season_name": "Scans",
                                    "folder": season_folder,
                                    "is_scans": True,
                                    "episodes": chapters_found
                                })
                        else:
                            # Standard video season folder
                            episodes_found = []
                            for ep_file in sorted(os.listdir(season_path)):
                                if ep_file.lower().endswith(('.mp4', '.mkv', '.webm')):
                                    full_ep_path = os.path.join(season_path, ep_file)
                                    file_size_mb = round(os.path.getsize(full_ep_path) / (1024 * 1024), 1)
                                    
                                    # Extract episode number
                                    ep_num = "1"
                                    m = re.search(r'\d+', ep_file)
                                    if m:
                                        ep_num = str(int(m.group()))

                                    episodes_found.append({
                                        "num": ep_num,
                                        "filename": ep_file,
                                        "file_path": full_ep_path,
                                        "thumbnail": f"/api/stream/thumbnail?file_path={quote(full_ep_path)}",
                                        "size_mb": file_size_mb,
                                        "is_scan": False,
                                        "is_downloaded": True
                                    })

                            if episodes_found:
                                seasons_found.append({
                                    "season_name": display_season,
                                    "folder": season_folder,
                                    "is_scans": False,
                                    "episodes": episodes_found
                                })

                    if seasons_found:
                        seen_titles.add(display_title.lower())
                        total_eps = sum(len(s["episodes"]) for s in seasons_found if not s.get("is_scans"))
                        total_chaps = sum(len(s["episodes"]) for s in seasons_found if s.get("is_scans"))
                        total_size = sum(ep.get("size_mb", 0) for s in seasons_found for ep in s["episodes"])
                        results.append({
                            "anime_title": display_title,
                            "folder": anime_folder,
                            "cover": cover,
                            "seasons": seasons_found,
                            "total_episodes": total_eps,
                            "total_chapters": total_chaps,
                            "total_size_mb": round(total_size, 1),
                            "has_videos": total_eps > 0,
                            "has_scans": total_chaps > 0
                        })
            except Exception as e:
                print(f"[CacheService] Error scanning downloaded library: {e}")

        return results

cache_service = CacheService()
