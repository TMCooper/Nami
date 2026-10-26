import os
from backend.services.storage import load_json, save_json

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")
SETTINGS_FILE = os.path.join(DATA_DIR, "settings.json")

DEFAULT_SETTINGS = {
    "root_folder": "/downloads",
    "default_provider": "all",  # "all", "anime_sama", "voiranime"
    "download_quality": "1080p",
    "max_concurrent_downloads": 3,
    "disabled_sources": []      # sources switched off by the user ("anime_sama", "voiranime")
}

class SettingsService:
    def __init__(self):
        os.makedirs(DATA_DIR, exist_ok=True)
        self.settings = self._load()

    def _load(self):
        data = load_json(SETTINGS_FILE, dict)
        # Merge with default settings
        return {**DEFAULT_SETTINGS, **(data if isinstance(data, dict) else {})}

    def get_settings(self):
        return self.settings

    def update_settings(self, new_settings: dict):
        self.settings.update(new_settings)
        if "root_folder" in new_settings:
            path = new_settings["root_folder"].strip()
            if not path:
                path = "/downloads"
            self.settings["root_folder"] = path
            
        save_json(SETTINGS_FILE, self.settings, indent=4)
        return self.settings

    def get_root_folder(self) -> str:
        return self.settings.get("root_folder", "/downloads")

settings_service = SettingsService()
