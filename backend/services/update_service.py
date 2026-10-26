import os
import sys
import subprocess
import httpx
import importlib.metadata
from typing import Dict, Optional

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ANIME_SAMA_PATH = os.path.join(PROJECT_ROOT, "AnimeSamaApi")
if not os.path.exists(ANIME_SAMA_PATH):
    sibling_as = os.path.join(os.path.dirname(PROJECT_ROOT), "AnimeSamaApi")
    if os.path.exists(sibling_as):
        ANIME_SAMA_PATH = sibling_as

VOIRANIME_PATH = os.path.join(PROJECT_ROOT, "voiranime_API")
if not os.path.exists(VOIRANIME_PATH):
    sibling_va = os.path.join(os.path.dirname(PROJECT_ROOT), "voiranime_API")
    if os.path.exists(sibling_va):
        VOIRANIME_PATH = sibling_va

class UpdateService:
    def __init__(self):
        self.client = httpx.Client(timeout=8.0)

    def _get_local_commit(self, repo_path: str) -> str:
        if not os.path.exists(repo_path) or not os.path.exists(os.path.join(repo_path, ".git")):
            return "Non cloné"
        try:
            res = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=4
            )
            return res.stdout.strip() if res.returncode == 0 else "Inconnu"
        except Exception:
            return "Inconnu"

    def _get_remote_commit(self, repo_url: str) -> str:
        try:
            res = subprocess.run(
                ["git", "ls-remote", repo_url, "HEAD"],
                capture_output=True,
                text=True,
                timeout=6
            )
            if res.returncode == 0 and res.stdout:
                full_hash = res.stdout.split()[0]
                return full_hash[:7]
        except Exception:
            pass
        return "Inconnu"

    def _get_yoitsu_versions(self) -> tuple[str, str]:
        local_ver = "0.1.8"
        try:
            local_ver = importlib.metadata.version("YoitsuWrap")
        except Exception:
            pass

        latest_ver = local_ver
        try:
            resp = self.client.get("https://pypi.org/pypi/YoitsuWrap/json")
            if resp.status_code == 200:
                data = resp.json()
                latest_ver = data.get("info", {}).get("version", local_ver)
        except Exception:
            pass

        return local_ver, latest_ver

    def check_all_updates(self) -> Dict[str, dict]:
        # AnimeSamaApi
        as_local = self._get_local_commit(ANIME_SAMA_PATH)
        as_remote = self._get_remote_commit("https://github.com/TMCooper/AnimeSamaApi.git")
        as_up_to_date = (as_local == as_remote) if (as_local != "Inconnu" and as_remote != "Inconnu") else True

        # VoirAnime_API
        va_local = self._get_local_commit(VOIRANIME_PATH)
        va_remote = self._get_remote_commit("https://github.com/TMCooper/voiranime_API.git")
        va_up_to_date = (va_local == va_remote) if (va_local != "Inconnu" and va_remote != "Inconnu") else True

        # YoitsuWrap
        yw_local, yw_remote = self._get_yoitsu_versions()
        yw_up_to_date = (yw_local == yw_remote)

        return {
            "animesama": {
                "name": "AnimeSamaApi",
                "repo_url": "https://github.com/TMCooper/AnimeSamaApi",
                "current_version": as_local,
                "latest_version": as_remote,
                "up_to_date": as_up_to_date,
                "cloned": os.path.exists(ANIME_SAMA_PATH)
            },
            "voiranime": {
                "name": "VoirAnime_API",
                "repo_url": "https://github.com/TMCooper/voiranime_API",
                "current_version": va_local,
                "latest_version": va_remote,
                "up_to_date": va_up_to_date,
                "cloned": os.path.exists(VOIRANIME_PATH)
            },
            "yoitsuwrap": {
                "name": "YoitsuWrap (Wrapper Python)",
                "repo_url": "https://pypi.org/project/YoitsuWrap/",
                "current_version": yw_local,
                "latest_version": yw_remote,
                "up_to_date": yw_up_to_date,
                "cloned": True
            }
        }

    def ensure_cloned(self, repo_url: str, target_path: str) -> bool:
        """Clones the repository if it doesn't already exist."""
        if not os.path.exists(target_path):
            print(f"[UpdateService] Cloning {repo_url} into {target_path}...")
            try:
                res = subprocess.run(
                    ["git", "clone", "--depth", "1", repo_url, target_path],
                    check=True,
                    capture_output=True,
                    text=True
                )
                req_path = os.path.join(target_path, "requirements.txt")
                if os.path.exists(req_path):
                    subprocess.run([sys.executable, "-m", "pip", "install", "--no-cache-dir", "-r", req_path], check=False)
                return True
            except Exception as e:
                print(f"[UpdateService] Clone error for {repo_url}: {e}")
                return False
        return True

    def update_repo(self, repo_url: str, target_path: str) -> dict:
        """Updates repository via git pull or clones if missing."""
        if not os.path.exists(target_path):
            success = self.ensure_cloned(repo_url, target_path)
            return {"status": "cloned" if success else "error", "message": "Dépôt cloné avec succès"}

        try:
            # Git pull
            pull_res = subprocess.run(
                ["git", "pull", "origin", "main"],
                cwd=target_path,
                capture_output=True,
                text=True,
                timeout=30
            )
            # Reinstall requirements if changed
            req_path = os.path.join(target_path, "requirements.txt")
            if os.path.exists(req_path):
                subprocess.run([sys.executable, "-m", "pip", "install", "--no-cache-dir", "-r", req_path], check=False)
                # Safeguard FastAPI typing_extensions consistency
                subprocess.run([sys.executable, "-m", "pip", "install", "--no-cache-dir", "--upgrade", "typing-extensions>=4.14.0", "anyio>=4.8.0"], check=False)


            new_commit = self._get_local_commit(target_path)
            return {
                "status": "updated",
                "message": pull_res.stdout.strip() or "Mise à jour effectuée",
                "new_commit": new_commit
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def update_yoitsuwrap(self) -> dict:
        """Upgrades YoitsuWrap pip package to the latest release."""
        try:
            res = subprocess.run(
                [sys.executable, "-m", "pip", "install", "--no-cache-dir", "--upgrade", "YoitsuWrap"],
                capture_output=True,
                text=True,
                timeout=45
            )
            new_ver, _ = self._get_yoitsu_versions()
            return {
                "status": "updated",
                "message": res.stdout.strip()[-200:] or "Mis à jour",
                "new_version": new_ver
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

update_service = UpdateService()
