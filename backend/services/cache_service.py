import os
import json
import time
import random
import re
from typing import Optional, List, Dict

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data")
CACHE_DIR = os.path.join(DATA_DIR, "cache")
ANIME_CACHE_DIR = os.path.join(CACHE_DIR, "animes")
RECENT_FILE = os.path.join(CACHE_DIR, "recent.json")
CATALOG_INDEX_FILE = os.path.join(CACHE_DIR, "catalog_index.json")

# Starter recommendations for instant discovery even before scraping full catalogs
POPULAR_STARTER_ANIMES = [
    {"title": "Frieren", "source": "anime_sama", "url": "https://anime-sama.fr/catalogue/frieren/", "cover": "https://cdn.statically.io/gh/Anime-Sama/IMG/img/contenu/frieren.jpg"},
    {"title": "Jujutsu Kaisen", "source": "anime_sama", "url": "https://anime-sama.fr/catalogue/jujutsu-kaisen/", "cover": "https://cdn.statically.io/gh/Anime-Sama/IMG/img/contenu/jujutsu-kaisen.jpg"},
    {"title": "Demon Slayer", "source": "anime_sama", "url": "https://anime-sama.fr/catalogue/demon-slayer/", "cover": "https://cdn.statically.io/gh/Anime-Sama/IMG/img/contenu/demon-slayer.jpg"},
    {"title": "One Piece", "source": "anime_sama", "url": "https://anime-sama.fr/catalogue/one-piece/", "cover": "https://cdn.statically.io/gh/Anime-Sama/IMG/img/contenu/one-piece.jpg"},
    {"title": "Solo Leveling", "source": "anime_sama", "url": "https://anime-sama.fr/catalogue/solo-leveling/", "cover": "https://cdn.statically.io/gh/Anime-Sama/IMG/img/contenu/solo-leveling.jpg"},
    {"title": "L'Attaque des Titans", "source": "anime_sama", "url": "https://anime-sama.fr/catalogue/lattaque-des-titans/", "cover": "https://cdn.statically.io/gh/Anime-Sama/IMG/img/contenu/lattaque-des-titans.jpg"},
    {"title": "Chainsaw Man", "source": "anime_sama", "url": "https://anime-sama.fr/catalogue/chainsaw-man/", "cover": "https://cdn.statically.io/gh/Anime-Sama/IMG/img/contenu/chainsaw-man.jpg"},
    {"title": "Hunter x Hunter", "source": "anime_sama", "url": "https://anime-sama.fr/catalogue/hunter-x-hunter-2011/", "cover": "https://cdn.statically.io/gh/Anime-Sama/IMG/img/contenu/hunter-x-hunter-2011.jpg"},
    {"title": "Bleach", "source": "anime_sama", "url": "https://anime-sama.fr/catalogue/bleach/", "cover": "https://cdn.statically.io/gh/Anime-Sama/IMG/img/contenu/bleach.jpg"},
    {"title": "Mashle", "source": "anime_sama", "url": "https://anime-sama.fr/catalogue/mashle/", "cover": "https://cdn.statically.io/gh/Anime-Sama/IMG/img/contenu/mashle.jpg"},
    {"title": "Spy x Family", "source": "anime_sama", "url": "https://anime-sama.fr/catalogue/spy-x-family/", "cover": "https://cdn.statically.io/gh/Anime-Sama/IMG/img/contenu/spy-x-family.jpg"},
    {"title": "Oshi no Ko", "source": "anime_sama", "url": "https://anime-sama.fr/catalogue/oshi-no-ko/", "cover": "https://cdn.statically.io/gh/Anime-Sama/IMG/img/contenu/oshi-no-ko.jpg"},
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
        
        entry = {
            "title": anime.get("title"),
            "url": anime.get("url", ""),
            "source": anime.get("source", "anime_sama"),
            "cover": anime.get("cover", ""),
            "viewed_at": time.time()
        }
        filtered.insert(0, entry)
        self.recent_data[uid] = filtered[:24]  # Keep up to 24
        self._save_recent()

    def get_recent_animes(self, user_id: str) -> List[dict]:
        uid = user_id or "default"
        return self.recent_data.get(uid, [])

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

    # --- Scan Local Downloaded Media on Disk ---
    def scan_downloaded_library(self, root_folder: str) -> List[dict]:
        base_dir = os.path.join(root_folder, "nami", "anime")
        results = []
        if not os.path.exists(base_dir):
            return results

        try:
            for anime_folder in os.listdir(base_dir):
                anime_path = os.path.join(base_dir, anime_folder)
                if not os.path.isdir(anime_path):
                    continue

                display_title = anime_folder.replace("_", " ")
                seasons_found = []

                for season_folder in os.listdir(anime_path):
                    season_path = os.path.join(anime_path, season_folder)
                    if not os.path.isdir(season_path):
                        continue

                    display_season = season_folder.replace("_", " ")
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
                                "size_mb": file_size_mb
                            })

                    if episodes_found:
                        seasons_found.append({
                            "season_name": display_season,
                            "folder": season_folder,
                            "episodes": episodes_found
                        })

                if seasons_found:
                    total_eps = sum(len(s["episodes"]) for s in seasons_found)
                    results.append({
                        "anime_title": display_title,
                        "folder": anime_folder,
                        "seasons": seasons_found,
                        "total_episodes": total_eps
                    })
        except Exception as e:
            print(f"[CacheService] Error scanning downloaded library: {e}")

        return results

cache_service = CacheService()
