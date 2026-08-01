import os
import json
import time

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
                    return json.load(f)
            except Exception as e:
                print(f"[HistoryService] Error loading history DB: {e}")
        return {}

    def _save(self):
        try:
            with open(HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump(self.history, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[HistoryService] Error saving history DB: {e}")

    def get_history(self) -> dict:
        return self.history

    def get_anime_history(self, anime_title: str) -> dict:
        return self.history.get(anime_title, {"episodes": {}})

    def save_progress(self, anime_title: str, season: str, ep_id: str, position_sec: float, duration_sec: float):
        if not anime_title or not ep_id:
            return

        if anime_title not in self.history:
            self.history[anime_title] = {
                "anime_title": anime_title,
                "last_season": season,
                "last_ep_id": ep_id,
                "last_updated": time.time(),
                "episodes": {}
            }

        anime_record = self.history[anime_title]
        anime_record["last_season"] = season
        anime_record["last_ep_id"] = ep_id
        anime_record["last_updated"] = time.time()

        ep_key = f"{season}:{ep_id}"
        ep_record = anime_record["episodes"].get(ep_key, {})
        
        ep_record["position_sec"] = position_sec
        ep_record["duration_sec"] = duration_sec
        ep_record["last_watched_at"] = time.time()

        # Mark as watched if position >= 85% of duration
        if duration_sec > 0 and (position_sec / duration_sec) >= 0.85:
            ep_record["watched"] = True

        anime_record["episodes"][ep_key] = ep_record
        self._save()
        return ep_record

    def toggle_watched(self, anime_title: str, season: str, ep_id: str, is_watched: bool = None) -> bool:
        if not anime_title or not ep_id:
            return False

        if anime_title not in self.history:
            self.history[anime_title] = {
                "anime_title": anime_title,
                "last_season": season,
                "last_ep_id": ep_id,
                "last_updated": time.time(),
                "episodes": {}
            }

        anime_record = self.history[anime_title]
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

    def mark_season(self, anime_title: str, season: str, ep_ids: list, is_watched: bool = True):
        if not anime_title or not ep_ids:
            return

        if anime_title not in self.history:
            self.history[anime_title] = {
                "anime_title": anime_title,
                "last_season": season,
                "last_ep_id": ep_ids[0] if ep_ids else "1",
                "last_updated": time.time(),
                "episodes": {}
            }

        anime_record = self.history[anime_title]
        for ep_id in ep_ids:
            ep_key = f"{season}:{ep_id}"
            ep_record = anime_record["episodes"].get(ep_key, {})
            ep_record["watched"] = is_watched
            ep_record["last_watched_at"] = time.time()
            anime_record["episodes"][ep_key] = ep_record

        self._save()

history_service = HistoryService()
