import os
import json
import time
import random
import re
import threading
import httpx
from typing import Optional, List, Dict
from urllib.parse import quote

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data")
CACHE_DIR = os.path.join(DATA_DIR, "cache")
ANIME_CACHE_DIR = os.path.join(CACHE_DIR, "animes")
RECENT_FILE = os.path.join(CACHE_DIR, "recent.json")
CATALOG_INDEX_FILE = os.path.join(CACHE_DIR, "catalog_index.json")

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

class CacheService:
    def __init__(self):
        os.makedirs(ANIME_CACHE_DIR, exist_ok=True)
        self.recent_data: Dict[str, List[dict]] = self._load_recent()

    def _load_recent(self) -> dict:
        if os.path.exists(RECENT_FILE):
            try:
                with open(RECENT_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"[CacheService] Error reading recent file: {e}")
        return {}

    def _save_recent(self):
        try:
            with open(RECENT_FILE, "w", encoding="utf-8") as f:
                json.dump(self.recent_data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[CacheService] Error saving recent file: {e}")

    # --- Anime Details Caching ---
    def get_anime_details(self, source: str, key: str) -> Optional[dict]:
        safe_key = f"{source}_{sanitize_cache_key(key)}.json"
        path = os.path.join(ANIME_CACHE_DIR, safe_key)
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    # Cache valid for 3 days or perpetual
                    if time.time() - data.get("_cached_at", 0) < 86400 * 3:
                        return data.get("content")
            except Exception as e:
                print(f"[CacheService] Error reading cache {safe_key}: {e}")
        return None

    def save_anime_details(self, source: str, key: str, content: dict):
        safe_key = f"{source}_{sanitize_cache_key(key)}.json"
        path = os.path.join(ANIME_CACHE_DIR, safe_key)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"_cached_at": time.time(), "content": content}, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[CacheService] Error saving cache {safe_key}: {e}")

    # --- Recent Viewed & Searched Animes ---
    def add_recent_anime(self, user_id: str, anime: dict):
        if not anime or not anime.get("title"):
            return
        uid = user_id or "default"
        if uid not in self.recent_data:
            self.recent_data[uid] = []

        user_recents = self.recent_data[uid]
        # Remove existing if duplicate
        filtered = [a for a in user_recents if a.get("title", "").lower() != anime.get("title", "").lower()]
        
        cover_val = anime.get("cover", "")
        if not cover_val or "placeholder" in cover_val:
            title = anime.get("title", "")
            try:
                from backend.services.yoitsu_service import yoitsu_service
                cov = yoitsu_service.get_anime_cover(title)
                if cov:
                    if "voir-anime" in cov or "voiranime" in cov:
                        from urllib.parse import quote
                        cover_val = f"/api/proxy/image?url={quote(cov, safe='')}"
                    else:
                        cover_val = cov
            except Exception:
                pass

        entry = {
            "title": anime.get("title"),
            "url": anime.get("url", ""),
            "source": anime.get("source", "anime_sama"),
            "cover": cover_val,
            "viewed_at": time.time()
        }
        filtered.insert(0, entry)
        self.recent_data[uid] = filtered[:24]  # Keep up to 24
        self._save_recent()

    def get_recent_animes(self, user_id: str) -> List[dict]:
        uid = user_id or "default"
        recents = self.recent_data.get(uid, [])
        updated = False
        for a in recents:
            cov = a.get("cover", "")
            if not cov or "placeholder" in cov:
                title = a.get("title", "")
                try:
                    from backend.services.yoitsu_service import yoitsu_service
                    new_cov = yoitsu_service.get_anime_cover(title)
                    if new_cov:
                        if "voir-anime" in new_cov or "voiranime" in new_cov:
                            from urllib.parse import quote
                            a["cover"] = f"/api/proxy/image?url={quote(new_cov, safe='')}"
                        else:
                            a["cover"] = new_cov
                        updated = True
                except Exception:
                    pass
        if updated:
            self._save_recent()
        return recents

    # --- Random / Starter Animes ---
    def get_random_animes(self, count: int = 12) -> List[dict]:
        pool = list(POPULAR_STARTER_ANIMES)
        
        # Also include any cached animes
        try:
            for fname in os.listdir(ANIME_CACHE_DIR):
                if fname.endswith(".json"):
                    fpath = os.path.join(ANIME_CACHE_DIR, fname)
                    with open(fpath, "r", encoding="utf-8") as f:
                        item = json.load(f).get("content", {})
                        if item.get("title"):
                            pool.append({
                                "title": item["title"],
                                "url": item.get("url", ""),
                                "source": item.get("source", "anime_sama"),
                                "cover": item.get("cover", "")
                            })
        except Exception:
            pass

        # Deduplicate by title
        seen = set()
        deduped = []
        for a in pool:
            t = a["title"].lower()
            if t not in seen:
                seen.add(t)
                deduped.append(a)

        random.shuffle(deduped)
        return deduped[:count]

    def _save_local_cover_async(self, cover_url: str, anime_path: str):
        """Asynchronously fetches and saves the cover image to cover.jpg inside anime folder."""
        def _fetch_and_save():
            try:
                dest = os.path.join(anime_path, "cover.jpg")
                if os.path.exists(dest) and os.path.getsize(dest) > 1000:
                    return
                target = cover_url
                if "/api/proxy/image?url=" in target:
                    target = target.split("/api/proxy/image?url=")[-1]
                headers = {"User-Agent": "Mozilla/5.0"}
                if "voir-anime" in target:
                    headers["Referer"] = "https://voir-anime.to/"
                elif "anime-sama" in target:
                    headers["Referer"] = "https://anime-sama.fr/"
                with httpx.Client(timeout=10.0, follow_redirects=True) as client:
                    resp = client.get(target, headers=headers)
                    if resp.status_code == 200 and len(resp.content) > 1000:
                        with open(dest, "wb") as f:
                            f.write(resp.content)
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
        hist_file = os.path.join(DATA_DIR, "history.json")
        if os.path.exists(hist_file):
            try:
                with open(hist_file, "r", encoding="utf-8") as f:
                    hdata = json.load(f)
                    for user_records in hdata.values():
                        if isinstance(user_records, dict):
                            for atitle, rec in user_records.items():
                                if atitle.lower().strip() == clean_name and rec.get("cover"):
                                    cov_url = rec["cover"]
                                    self._save_local_cover_async(cov_url, anime_path)
                                    return cov_url
            except Exception:
                pass

        # 3. VoirAnime covers.json
        va_covers = os.path.join(DATA_DIR, "submodules", "voiranime_API", "data", "covers.json")
        if not os.path.exists(va_covers):
            va_covers = os.path.join(os.path.dirname(DATA_DIR), "voiranime_API", "data", "covers.json")
        if os.path.exists(va_covers):
            try:
                with open(va_covers, "r", encoding="utf-8") as f:
                    vdata = json.load(f)
                    for t, c in vdata.items():
                        if c and (t.lower().strip() == clean_name or clean_name in t.lower() or t.lower() in clean_name):
                            self._save_local_cover_async(c, anime_path)
                            return f"/api/proxy/image?url={quote(c, safe='')}"
            except Exception:
                pass

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
