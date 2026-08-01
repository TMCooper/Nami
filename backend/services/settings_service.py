import os
import json

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")

DEFAULT_SETTINGS = {
    "root_folder": "/downloads",
    "default_provider": "all",  # "all", "anime_sama", "voiranime"
    "download_quality": "1080p",
    "max_concurrent_downloads": 3
}

class SettingsService:
    def __init__(self):
        os.makedirs(DATA_DIR, exist_ok=True)
        self.settings = self._load()

    def _load(self):
        if os.path.exists(SETTINGS_FILE):
            try:
                with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    # Merge with default settings
                    merged = {**DEFAULT_SETTINGS, **data}
                    return merged
            except Exception as e:
                print(f"[Settings] Error loading settings: {e}")
        return DEFAULT_SETTINGS.copy()

    def get_settings(self):
        return self.settings

    def update_settings(self, new_settings: dict):
        self.settings.update(new_settings)
        if "root_folder" in new_settings:
            path = new_settings["root_folder"].strip()
            if not path:
                path = "/downloads"
            self.settings["root_folder"] = path
            
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(self.settings, f, indent=4, ensure_ascii=False)
        return self.settings

    def get_root_folder(self) -> str:
        return self.settings.get("root_folder", "/downloads")

settings_service = SettingsService()
