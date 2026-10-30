import os
import re
import secrets
import threading
import time
from typing import Optional, List, Dict
from backend.services.storage import load_json, save_json
from backend.services.auth_service import hash_password, verify_password, needs_rehash, password_problem, burn_time

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data")
USERS_FILE = os.path.join(DATA_DIR, "users.json")
USERNAME = re.compile(r"^[\w .'-]{2,32}$", re.UNICODE)
ROLES = ("admin", "user")


class AccountError(ValueError):
    """A refused account operation (its message is shown as is)."""


class UserService:
    """Accounts: one super administrator (role 'admin', the first account created), the others 'user'."""

    def __init__(self):
        os.makedirs(DATA_DIR, exist_ok=True)
        self._lock = threading.RLock()
        self.users: Dict[str, dict] = self._load()

    def _load(self) -> dict:
        data = load_json(USERS_FILE, dict)
        if isinstance(data, dict):
            # Ensure default is never kept
            data.pop("default", None)
            for user in data.values():
                user.setdefault("role", "user")
                user.setdefault("disabled", False)
            return data
        return {}

    def _save(self):
        try:
            save_json(USERS_FILE, self.users)
        except Exception as e:
            print(f"[UserService] Error saving users DB: {e}")

    # --- views ---
    @staticmethod
    def public(user: dict) -> dict:
        """What the account's own session and the interface see."""
        return {
            "id": user["id"],
            "username": user["username"],
            "avatar": user.get("avatar", "👤"),
            "role": user.get("role", "user"),
            "created_at": user.get("created_at"),
        }

    def admin_view(self, user: dict) -> dict:
        return {**self.public(user), "disabled": bool(user.get("disabled")), "last_login": user.get("last_login"),
                "last_ip": user.get("last_ip", "")}

    def list_users(self) -> List[dict]:
        with self._lock:
            return sorted((self.admin_view(u) for u in self.users.values()), key=lambda u: u.get("created_at") or 0)

    def count(self) -> int:
        return len(self.users)

    def has_admin(self) -> bool:
        return any(u.get("role") == "admin" for u in self.users.values())

    def get_user(self, user_id: str) -> Optional[dict]:
        user = self.users.get(user_id)
        return self.public(user) if user else None

    def is_admin(self, user_id: str) -> bool:
        user = self.users.get(user_id)
        return bool(user and user.get("role") == "admin" and not user.get("disabled"))

    def usable(self, user_id: str) -> bool:
        user = self.users.get(user_id)
        return bool(user and not user.get("disabled"))

    def _find(self, username: str) -> Optional[dict]:
        wanted = username.strip().lower()
        return next((u for u in self.users.values() if u["username"].lower() == wanted), None)

    @staticmethod
    def _clean_name(username: str) -> str:
        name = re.sub(r"\s+", " ", (username or "").strip())
        if not USERNAME.match(name):
            raise AccountError("Pseudo invalide : 2 à 32 caractères (lettres, chiffres, espace, . ' - _).")
        return name

    # --- accounts ---
    def register_user(self, username: str, password: str = "", avatar: str = "👤") -> dict:
        name = self._clean_name(username)
        problem = password_problem(password or "")
        if problem:
            raise AccountError(problem)
        with self._lock:
            if self._find(name):
                raise AccountError("Ce pseudo est déjà pris.")
            user_id = f"user_{secrets.token_hex(6)}"
            user = {
                "id": user_id,
                "username": name,
                "avatar": avatar if isinstance(avatar, str) and len(avatar) <= 3 * 1024 * 1024 else "👤",
                "password_hash": hash_password(password),
                # The very first account is the super administrator
                "role": "admin" if not self.users else "user",
                "disabled": False,
                "created_at": time.time(),
            }
            self.users[user_id] = user
            self._save()
            return self.public(user)

    def authenticate(self, username: str, password: str) -> Optional[dict]:
        """The account these credentials open, or None (never says which part was wrong)."""
        user = self._find(username or "")
        if not user or not user.get("password_hash"):
            burn_time(password or "")
            return None
        if not verify_password(password or "", user["password_hash"]):
            return None
        if needs_rehash(user["password_hash"]):
            with self._lock:
                user["password_hash"] = hash_password(password)
                self._save()
        return user

    def note_login(self, user_id: str, ip: str):
        with self._lock:
            user = self.users.get(user_id)
            if user:
                user["last_login"], user["last_ip"] = time.time(), ip
                self._save()

    def set_password(self, user_id: str, new_password: str, current_password: Optional[str] = None):
        problem = password_problem(new_password or "")
        if problem:
            raise AccountError(problem)
        with self._lock:
            user = self.users.get(user_id)
            if not user:
                raise AccountError("Compte introuvable.")
            if current_password is not None and not verify_password(current_password, user.get("password_hash", "")):
                raise AccountError("Mot de passe actuel incorrect.")
            user["password_hash"] = hash_password(new_password)
            self._save()

    def rename(self, user_id: str, username: str) -> dict:
        name = self._clean_name(username)
        with self._lock:
            user = self.users.get(user_id)
            if not user:
                raise AccountError("Compte introuvable.")
            other = self._find(name)
            if other and other["id"] != user_id:
                raise AccountError("Ce pseudo est déjà pris.")
            user["username"] = name
            self._save()
            return self.public(user)

    def set_avatar(self, user_id: str, avatar: str) -> dict:
        with self._lock:
            user = self.users.get(user_id)
            if not user:
                raise AccountError("Compte introuvable.")
            user["avatar"] = avatar
            self._save()
            return self.public(user)

    def set_disabled(self, user_id: str, disabled: bool) -> dict:
        with self._lock:
            user = self.users.get(user_id)
            if not user:
                raise AccountError("Compte introuvable.")
            if disabled and user.get("role") == "admin":
                raise AccountError("Le super administrateur ne peut pas être désactivé.")
            user["disabled"] = bool(disabled)
            self._save()
            return self.admin_view(user)

    def make_admin(self, user_id: str) -> dict:
        """The super administrator role goes to this account (the previous one becomes a user)."""
        with self._lock:
            user = self.users.get(user_id)
            if not user:
                raise AccountError("Compte introuvable.")
            if user.get("disabled"):
                raise AccountError("Ce compte est désactivé.")
            for other in self.users.values():
                if other.get("role") == "admin":
                    other["role"] = "user"
            user["role"] = "admin"
            self._save()
            return self.admin_view(user)

    def delete_user(self, user_id: str) -> bool:
        """Deletes user and completely wipes their watch history and recent entries."""
        with self._lock:
            user = self.users.get(user_id)
            if not user:
                return False
            if user.get("role") == "admin":
                raise AccountError("Le super administrateur ne peut pas être supprimé : transférez d'abord son rôle.")
            del self.users[user_id]
            self._save()

        # Clean user history
        try:
            from backend.services.history_service import history_service
            history_service.delete_user_data(user_id)
        except Exception as e:
            print(f"[UserService] Error deleting user history: {e}")

        # Clean user watchlist
        try:
            from backend.services.watchlist_service import watchlist_service
            watchlist_service.delete_user_data(user_id)
        except Exception as e:
            print(f"[UserService] Error deleting user watchlist: {e}")

        # Clean user recent items
        try:
            from backend.services.cache_service import cache_service
            with cache_service._recent_lock:
                removed = cache_service.recent_data.pop(user_id, None)
            if removed is not None:
                cache_service._save_recent()
        except Exception as e:
            print(f"[UserService] Error deleting user recents: {e}")

        # And every session it had
        from backend.services.auth_service import auth_service
        auth_service.end_user_sessions(user_id)
        return True


user_service = UserService()
