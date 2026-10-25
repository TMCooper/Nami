import os
import json
import hashlib
import secrets
import time
from typing import Optional, List, Dict

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data")
USERS_FILE = os.path.join(DATA_DIR, "users.json")

def hash_password(password: str, salt: str = "") -> str:
    if not salt:
        salt = secrets.token_hex(8)
    hashed = hashlib.sha256((password + salt).encode('utf-8')).hexdigest()
    return f"{salt}:{hashed}"

def verify_password(password: str, stored_hash: str) -> bool:
    if ":" not in stored_hash:
        return False
    salt, original_hash = stored_hash.split(":", 1)
    new_hash = hashlib.sha256((password + salt).encode('utf-8')).hexdigest()
    return new_hash == original_hash

class UserService:
    def __init__(self):
        os.makedirs(DATA_DIR, exist_ok=True)
        self.users: Dict[str, dict] = self._load()
        self._ensure_default_user()

    def _load(self) -> dict:
        if os.path.exists(USERS_FILE):
            try:
                with open(USERS_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"[UserService] Error loading users DB: {e}")
        return {}

    def _save(self):
        try:
            with open(USERS_FILE, "w", encoding="utf-8") as f:
                json.dump(self.users, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[UserService] Error saving users DB: {e}")

    def _ensure_default_user(self):
        if not self.users:
            # Create a default guest profile if no user exists
            default_user = {
                "id": "default",
                "username": "Utilisateur",
                "avatar": "👤",
                "password_hash": hash_password("nami123"),
                "created_at": time.time()
            }
            self.users["default"] = default_user
            self._save()

    def list_users(self) -> List[dict]:
        res = []
        for user in self.users.values():
            res.append({
                "id": user["id"],
                "username": user["username"],
                "avatar": user.get("avatar", "👤"),
                "created_at": user.get("created_at")
            })
        return res

    def register_user(self, username: str, password: str = "", avatar: str = "👤") -> dict:
        username_clean = username.strip()
        if not username_clean:
            raise ValueError("Le nom d'utilisateur ne peut pas être vide.")

        # Check duplicate
        for u in self.users.values():
            if u["username"].lower() == username_clean.lower():
                raise ValueError("Ce nom d'utilisateur existe déjà.")

        user_id = f"user_{secrets.token_hex(4)}"
        p_hash = hash_password(password or "123456")

        user_data = {
            "id": user_id,
            "username": username_clean,
            "avatar": avatar,
            "password_hash": p_hash,
            "created_at": time.time()
        }
        self.users[user_id] = user_data
        self._save()

        return {
            "id": user_id,
            "username": username_clean,
            "avatar": avatar,
            "created_at": user_data["created_at"]
        }

    def login_user(self, username: str, password: str = "") -> dict:
        username_clean = username.strip().lower()
        target_user = None
        for u in self.users.values():
            if u["username"].lower() == username_clean:
                target_user = u
                break

        if not target_user:
            raise ValueError("Utilisateur non trouvé.")

        # If user has password set and entered password fails
        if target_user.get("password_hash") and password:
            if not verify_password(password, target_user["password_hash"]):
                raise ValueError("Mot de passe incorrect.")

        return {
            "id": target_user["id"],
            "username": target_user["username"],
            "avatar": target_user.get("avatar", "👤")
        }

    def get_user(self, user_id: str) -> Optional[dict]:
        user = self.users.get(user_id)
        if not user:
            # Fallback to default user if user_id unknown
            user = self.users.get("default")
        if user:
            return {
                "id": user["id"],
                "username": user["username"],
                "avatar": user.get("avatar", "👤")
            }
        return None

user_service = UserService()
