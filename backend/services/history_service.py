import os
import json
import time
from typing import Optional, List, Dict

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data")
HISTORY_FILE = os.path.join(DATA_DIR, "history.json")

class HistoryService:
    def __init__(self):
        os.makedirs(DATA_DIR, exist_ok=True)
        self.history = self._load()

    def _load(self) -> dict:
        if os.path.exists(HISTORY_FILE):
            try:
                with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    # Backward compatibility migration:
                    if data and not any(isinstance(v, dict) and "episodes" not in v for k, v in data.items()):
                        first_val = next(iter(data.values()), {})
                        if "episodes" in first_val or "last_season" in first_val:
                            return {"default": data}
                    return data
            except Exception as e:
                print(f"[HistoryService] Error loading history DB: {e}")
        return {}

    def _save(self):
        try:
            with open(HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump(self.history, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[HistoryService] Error saving history DB: {e}")

    def get_history(self, user_id: str = "default") -> dict:
        uid = user_id or "default"
        return self.history.get(uid, {})

    def get_anime_history(self, user_id: str, anime_title: str) -> dict:
        user_hist = self.get_history(user_id)
        return user_hist.get(anime_title, {"episodes": {}})

    def save_progress(
        self,
        user_id: str,
        anime_title: str,
        season: str,
        ep_id: str,
        position_sec: float,
        duration_sec: float,
        cover: Optional[str] = None,
        embed_url: Optional[str] = None,
        file_path: Optional[str] = None
    ):
        if not anime_title or not ep_id:
            return

        uid = user_id or "default"
        if uid not in self.history:
            self.history[uid] = {}

        user_hist = self.history[uid]

        if anime_title not in user_hist:
            user_hist[anime_title] = {
                "anime_title": anime_title,
                "cover": cover or "",
                "last_season": season,
                "last_ep_id": ep_id,
                "last_updated": time.time(),
                "episodes": {}
            }

        anime_record = user_hist[anime_title]
        if cover and not anime_record.get("cover"):
            anime_record["cover"] = cover
        anime_record["last_season"] = season
        anime_record["last_ep_id"] = ep_id
        anime_record["last_updated"] = time.time()

        ep_key = f"{season}:{ep_id}"
        ep_record = anime_record["episodes"].get(ep_key, {})
        
        ep_record["position_sec"] = position_sec
        ep_record["duration_sec"] = duration_sec
        ep_record["last_watched_at"] = time.time()
        if embed_url:
            ep_record["embed_url"] = embed_url
        if file_path:
            ep_record["file_path"] = file_path

        # Mark as watched if position >= 85% of duration
        if duration_sec > 0 and (position_sec / duration_sec) >= 0.85:
            ep_record["watched"] = True

        anime_record["episodes"][ep_key] = ep_record
        self._save()
        return ep_record

    def toggle_watched(self, user_id: str, anime_title: str, season: str, ep_id: str, is_watched: bool = None) -> bool:
        if not anime_title or not ep_id:
            return False

        uid = user_id or "default"
        if uid not in self.history:
            self.history[uid] = {}

        user_hist = self.history[uid]

        if anime_title not in user_hist:
            user_hist[anime_title] = {
                "anime_title": anime_title,
                "last_season": season,
                "last_ep_id": ep_id,
                "last_updated": time.time(),
                "episodes": {}
            }

        anime_record = user_hist[anime_title]
        ep_key = f"{season}:{ep_id}"
        ep_record = anime_record["episodes"].get(ep_key, {})

        if is_watched is not None:
            ep_record["watched"] = is_watched
        else:
            ep_record["watched"] = not ep_record.get("watched", False)

        ep_record["last_watched_at"] = time.time()
        anime_record["episodes"][ep_key] = ep_record
        self._save()
        return ep_record["watched"]

    def mark_season(self, user_id: str, anime_title: str, season: str, ep_ids: list, is_watched: bool = True):
        if not anime_title or not ep_ids:
            return

        uid = user_id or "default"
        if uid not in self.history:
            self.history[uid] = {}

        user_hist = self.history[uid]

        if anime_title not in user_hist:
            user_hist[anime_title] = {
                "anime_title": anime_title,
                "last_season": season,
                "last_ep_id": ep_ids[0] if ep_ids else "1",
                "last_updated": time.time(),
                "episodes": {}
            }

        anime_record = user_hist[anime_title]
        for ep_id in ep_ids:
            ep_key = f"{season}:{ep_id}"
            ep_record = anime_record["episodes"].get(ep_key, {})
            ep_record["watched"] = is_watched
            ep_record["last_watched_at"] = time.time()
            anime_record["episodes"][ep_key] = ep_record

        self._save()

    def get_continue_watching(self, user_id: str) -> List[dict]:
        """Returns in-progress or recently watched episodes sorted by last activity."""
        user_hist = self.get_history(user_id)
        continue_list = []

        for anime_title, record in user_hist.items():
            episodes = record.get("episodes", {})
            last_season = record.get("last_season", "Saison 1")
            last_ep_id = record.get("last_ep_id", "1")
            last_key = f"{last_season}:{last_ep_id}"

            ep_data = episodes.get(last_key, {})
            pos = ep_data.get("position_sec", 0)
            dur = ep_data.get("duration_sec", 0)
            watched = ep_data.get("watched", False)
            last_time = ep_data.get("last_watched_at", record.get("last_updated", 0))

            percent = round((pos / dur) * 100, 1) if dur > 0 else 0

            # If unfinished (> 10s and not watched), or recently watched
            continue_list.append({
                "anime_title": anime_title,
                "cover": record.get("cover", ""),
                "season": last_season,
                "episode_num": last_ep_id,
                "position_sec": pos,
                "duration_sec": dur,
                "progress_percent": percent,
                "watched": watched,
                "last_watched_at": last_time,
                "embed_url": ep_data.get("embed_url"),
                "file_path": ep_data.get("file_path")
            })

        continue_list.sort(key=lambda x: x["last_watched_at"], reverse=True)
        return continue_list

    def get_user_stats(self, user_id: str) -> dict:
        """Calculates viewing statistics for the user."""
        user_hist = self.get_history(user_id)
        total_seconds_watched = 0
        total_episodes_watched = 0
        total_animes_started = len(user_hist)
        animes_completed = 0

        for anime_title, record in user_hist.items():
            episodes = record.get("episodes", {})
            anime_watched_count = 0
            for ep_key, ep in episodes.items():
                if ep.get("watched"):
                    total_episodes_watched += 1
                    anime_watched_count += 1
                    dur = ep.get("duration_sec", 1440)  # default 24 min if unknown
                    total_seconds_watched += dur
                else:
                    pos = ep.get("position_sec", 0)
                    total_seconds_watched += pos

            # If at least 12 episodes watched or marked completed
            if anime_watched_count >= 12:
                animes_completed += 1

        hours = int(total_seconds_watched // 3600)
        minutes = int((total_seconds_watched % 3600) // 60)

        return {
            "total_seconds_watched": round(total_seconds_watched),
            "watch_time_formatted": f"{hours}h {minutes}m" if hours > 0 else f"{minutes}m",
            "total_episodes_watched": total_episodes_watched,
            "total_animes_started": total_animes_started,
            "animes_completed": animes_completed,
            "animes_in_progress": max(0, total_animes_started - animes_completed)
        }

    def delete_item(self, user_id: str, anime_title: str, ep_key: Optional[str] = None):
        """Removes a specific episode or an entire anime from the user's watch history."""
        uid = user_id or "default"
        if uid in self.history and anime_title in self.history[uid]:
            if ep_key:
                eps = self.history[uid][anime_title].get("episodes", {})
                if ep_key in eps:
                    del eps[ep_key]
                if not eps:
                    del self.history[uid][anime_title]
            else:
                del self.history[uid][anime_title]
            self._save()

    def clear_user_history(self, user_id: str):
        """Clears all watch history records for a given user."""
        uid = user_id or "default"
        if uid in self.history:
            self.history[uid] = {}
            self._save()

history_service = HistoryService()

