"""Who is calling: passwords, sessions, brute-force protection and the security log.

- passwords: PBKDF2-SHA256 (hashlib, no extra dependency); the old salted SHA-256 hashes are still
  accepted and upgraded at the next successful login;
- sessions: a random token in an HttpOnly cookie, only its SHA-256 stored (data/sessions.json), so a
  copy of the data folder gives no usable session;
- brute force: failed logins are counted per IP and per account; past the limit, both are locked for a
  delay that doubles at each new lock (1 min up to 1 h). The answer never tells whether the account exists;
- the security log keeps the last events (logins, locks, account changes) for the super administrator;
- the super administrator: the first account created is it. An install that already has accounts but no
  administrator gets a one-time setup code (data/admin-setup.txt, also printed in the logs).
"""
import hashlib
import hmac
import os
import secrets
import threading
import time
from typing import Dict, List, Optional, Tuple

from backend.services.storage import load_json, save_json

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data")
SESSIONS_FILE = os.path.join(DATA_DIR, "sessions.json")
SECURITY_LOG_FILE = os.path.join(DATA_DIR, "security-log.json")
SETUP_CODE_FILE = os.path.join(DATA_DIR, "admin-setup.txt")

PBKDF2_ITERATIONS = 240_000
SESSION_COOKIE = "nami_session"
SESSION_DAYS = 30                # "Se souvenir de moi"
SESSION_IDLE = 12 * 3600         # otherwise: ends after this much inactivity (and with the browser)
SESSION_TOUCH_EVERY = 60         # last_seen is saved at most this often

FAIL_WINDOW = 15 * 60            # failures counted over this window
FAIL_LIMIT = 5                   # failures before a lock
LOCK_BASE = 60                   # first lock (seconds), doubled at each new lock
LOCK_MAX = 3600
REGISTER_WINDOW = 3600
REGISTER_LIMIT = 5               # accounts one IP may create per hour
LOG_SIZE = 300


# --- passwords ---
def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("ascii"), PBKDF2_ITERATIONS).hex()
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    if not isinstance(stored, str) or not stored:
        return False
    if stored.startswith("pbkdf2_sha256$"):
        try:
            _, iterations, salt, digest = stored.split("$", 3)
            candidate = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("ascii"), int(iterations)).hex()
        except (ValueError, UnicodeEncodeError):
            return False
        return hmac.compare_digest(candidate, digest)
    if ":" in stored:   # older Nami: sha256(password + salt)
        salt, digest = stored.split(":", 1)
        return hmac.compare_digest(hashlib.sha256((password + salt).encode("utf-8")).hexdigest(), digest)
    return False


def needs_rehash(stored: str) -> bool:
    return not (isinstance(stored, str) and stored.startswith(f"pbkdf2_sha256${PBKDF2_ITERATIONS}$"))


_DUMMY_HASH = hash_password(secrets.token_hex(8))


def burn_time(password: str):
    """Same work as a real check, for unknown accounts (their answer takes as long)."""
    verify_password(password, _DUMMY_HASH)


def password_problem(password: str) -> Optional[str]:
    if len(password) < 8:
        return "Le mot de passe doit contenir au moins 8 caractères."
    if len(password) > 200:
        return "Le mot de passe est trop long."
    if password.isdigit() or password.lower() == password and password.isalpha() and len(set(password)) < 4:
        return "Ce mot de passe est trop simple."
    return None


def _token_key(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class AuthService:
    def __init__(self):
        os.makedirs(DATA_DIR, exist_ok=True)
        self._lock = threading.RLock()
        data = load_json(SESSIONS_FILE, dict)
        self._sessions: Dict[str, dict] = data if isinstance(data, dict) else {}
        log = load_json(SECURITY_LOG_FILE, list)
        self._log: List[dict] = log if isinstance(log, list) else []
        self._failures: Dict[str, List[float]] = {}     # 'ip:<ip>' / 'user:<name>' -> failure times
        self._locks: Dict[str, Tuple[float, int]] = {}  # same keys -> (locked until, locks so far)
        self._registrations: Dict[str, List[float]] = {}
        self._last_save = 0.0

    # --- sessions ---
    def _save_sessions(self):
        save_json(SESSIONS_FILE, self._sessions, indent=None)
        self._last_save = time.time()

    def create_session(self, user_id: str, remember: bool, ip: str, user_agent: str) -> str:
        token = secrets.token_urlsafe(32)
        now = time.time()
        with self._lock:
            self._purge(now)
            self._sessions[_token_key(token)] = {
                "user_id": user_id, "created": now, "last_seen": now, "remember": bool(remember),
                "expires": now + SESSION_DAYS * 86400 if remember else now + SESSION_IDLE,
                "ip": ip, "agent": (user_agent or "")[:160],
            }
            self._save_sessions()
        return token

    def session_user(self, token: Optional[str]) -> Optional[str]:
        """User id of a valid session (its idle expiry is pushed back)."""
        if not token:
            return None
        key = _token_key(token)
        now = time.time()
        with self._lock:
            session = self._sessions.get(key)
            if not session:
                return None
            if session["expires"] < now:
                del self._sessions[key]
                self._save_sessions()
                return None
            session["last_seen"] = now
            if not session.get("remember"):
                session["expires"] = now + SESSION_IDLE
            if now - self._last_save > SESSION_TOUCH_EVERY:
                self._save_sessions()
            return session["user_id"]

    def end_session(self, token: Optional[str]):
        if not token:
            return
        with self._lock:
            if self._sessions.pop(_token_key(token), None) is not None:
                self._save_sessions()

    def end_user_sessions(self, user_id: str, keep_token: Optional[str] = None) -> int:
        keep = _token_key(keep_token) if keep_token else None
        with self._lock:
            gone = [k for k, s in self._sessions.items() if s["user_id"] == user_id and k != keep]
            for k in gone:
                del self._sessions[k]
            if gone:
                self._save_sessions()
        return len(gone)

    def list_sessions(self, current_token: Optional[str] = None) -> List[dict]:
        current = _token_key(current_token) if current_token else None
        with self._lock:
            self._purge(time.time())
            return [{"id": k[:16], "user_id": s["user_id"], "created": s["created"], "last_seen": s["last_seen"],
                     "ip": s.get("ip", ""), "agent": s.get("agent", ""), "remember": s.get("remember", False),
                     "current": k == current} for k, s in sorted(self._sessions.items(), key=lambda kv: -kv[1]["last_seen"])]

    def end_session_by_id(self, short_id: str) -> Optional[str]:
        with self._lock:
            key = next((k for k in self._sessions if k[:16] == short_id), None)
            if not key:
                return None
            user_id = self._sessions.pop(key)["user_id"]
            self._save_sessions()
            return user_id

    def _purge(self, now: float):
        expired = [k for k, s in self._sessions.items() if s["expires"] < now]
        for k in expired:
            del self._sessions[k]

    # --- brute force ---
    def _recent(self, key: str, now: float) -> List[float]:
        times = [t for t in self._failures.get(key, []) if now - t < FAIL_WINDOW]
        self._failures[key] = times
        return times

    def locked_for(self, ip: str, username: str) -> int:
        """Seconds left before this IP / account may try again (0: free)."""
        now = time.time()
        with self._lock:
            waits = [until - now for key in (f"ip:{ip}", f"user:{username.lower()}")
                     for until, _ in [self._locks.get(key, (0, 0))] if until > now]
        return int(max(waits)) + 1 if waits else 0

    def login_failed(self, ip: str, username: str):
        now = time.time()
        locked = []
        with self._lock:
            for key in (f"ip:{ip}", f"user:{username.lower()}"):
                times = self._recent(key, now)
                times.append(now)
                if len(times) >= FAIL_LIMIT:
                    _, count = self._locks.get(key, (0, 0))
                    delay = min(LOCK_BASE * (2 ** count), LOCK_MAX)
                    self._locks[key] = (now + delay, count + 1)
                    self._failures[key] = []
                    locked.append((key, delay))
        self.log("login_failed", ip=ip, username=username)
        for key, delay in locked:
            self.log("locked", ip=ip, username=username, detail=f"{key.split(':', 1)[0]} bloqué {delay // 60 or 1} min")

    def login_succeeded(self, ip: str, username: str):
        with self._lock:
            for key in (f"ip:{ip}", f"user:{username.lower()}"):
                self._failures.pop(key, None)
                if key in self._locks and self._locks[key][0] <= time.time():
                    self._locks.pop(key, None)

    def lockouts(self) -> List[dict]:
        now = time.time()
        with self._lock:
            return [{"key": k, "kind": k.split(":", 1)[0], "value": k.split(":", 1)[1], "until": until, "count": count}
                    for k, (until, count) in self._locks.items() if until > now]

    def unlock(self, key: str) -> bool:
        with self._lock:
            self._failures.pop(key, None)
            return self._locks.pop(key, None) is not None

    def may_register(self, ip: str) -> bool:
        now = time.time()
        with self._lock:
            times = [t for t in self._registrations.get(ip, []) if now - t < REGISTER_WINDOW]
            self._registrations[ip] = times
            if len(times) >= REGISTER_LIMIT:
                return False
            times.append(now)
            return True

    # --- security log ---
    def log(self, event: str, ip: str = "", username: str = "", detail: str = "", by: str = ""):
        with self._lock:
            self._log.append({"at": time.time(), "event": event, "ip": ip, "username": username, "detail": detail, "by": by})
            del self._log[:-LOG_SIZE]
            try:
                save_json(SECURITY_LOG_FILE, self._log, indent=None)
            except Exception as e:
                print(f"[Auth] Security log not saved: {e}")

    def recent_events(self, limit: int = 100) -> List[dict]:
        with self._lock:
            return list(reversed(self._log[-limit:]))

    # --- super administrator setup code ---
    @staticmethod
    def setup_code(create: bool = True) -> Optional[str]:
        """The one-time code that makes an existing account the super administrator (no administrator yet)."""
        try:
            with open(SETUP_CODE_FILE, encoding="utf-8") as f:
                code = f.read().strip()
            if code:
                return code
        except OSError:
            pass
        if not create:
            return None
        code = "-".join(secrets.token_hex(3).upper() for _ in range(3))
        with open(SETUP_CODE_FILE, "w", encoding="utf-8") as f:
            f.write(code + "\n")
        print(f"[Nami] Aucun super administrateur : code d'installation {code} (aussi dans data/admin-setup.txt)")
        return code

    @staticmethod
    def check_setup_code(code: str) -> bool:
        expected = AuthService.setup_code(create=False)
        return bool(expected) and hmac.compare_digest(expected.replace("-", "").upper(), (code or "").replace("-", "").strip().upper())

    @staticmethod
    def drop_setup_code():
        try:
            os.remove(SETUP_CODE_FILE)
        except OSError:
            pass


auth_service = AuthService()
