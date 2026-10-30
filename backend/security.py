"""Access rules of the API.

Every /api route needs a valid session cookie, except signing in and up and the public status. The user
of the session is the only identity a route ever sees (request.state.user_id): a header or a body field
naming another user is ignored. Writes coming from another site's page are refused (same-origin check).
"""
import os
import shutil
from typing import Optional
from urllib.parse import urlparse

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from backend.services.auth_service import SESSION_COOKIE, auth_service
from backend.services.settings_service import settings_service
from backend.services.user_service import user_service

PUBLIC_PATHS = {"/api/auth/status", "/api/auth/login", "/api/auth/register", "/api/auth/logout", "/api/server/boot"}
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
_EXTRA_ORIGINS = {o.strip().rstrip("/") for o in os.environ.get("NAMI_CORS_ORIGINS", "").split(",") if o.strip()}
_DEV_ORIGINS = {"http://localhost:3000", "http://127.0.0.1:3000"}


def client_ip(request: Request) -> str:
    # Behind a reverse proxy, NAMI_TRUST_PROXY=1 makes its X-Forwarded-For the client address
    if os.environ.get("NAMI_TRUST_PROXY") == "1":
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else ""


def _same_origin(request: Request) -> bool:
    origin = request.headers.get("origin")
    if not origin:
        return True   # same-origin requests without Origin (old browsers, server tools)
    origin = origin.rstrip("/")
    if origin in _EXTRA_ORIGINS or origin in _DEV_ORIGINS:
        return True
    return urlparse(origin).netloc == request.headers.get("host", "")


def session_identity(request: Request) -> Optional[str]:
    """User id of the request's session cookie (the tests replace this one function)."""
    return auth_service.session_user(request.cookies.get(SESSION_COOKIE))


async def guard(request: Request, call_next):
    path = request.url.path
    if path == "/api" or path.startswith("/api/"):
        if request.method not in SAFE_METHODS and not _same_origin(request):
            return JSONResponse({"detail": "Requête refusée (autre origine)."}, status_code=403)
        user_id = session_identity(request)   # looked up at each call: the tests replace it
        if user_id and not user_service.usable(user_id):
            user_id = None   # deleted or disabled since: the session no longer opens anything
        request.state.user_id = user_id
        if not user_id and path not in PUBLIC_PATHS:
            return JSONResponse({"detail": "Connexion requise."}, status_code=401)
    return await call_next(request)


def session_user_id(request: Request) -> str:
    """The signed-in user (routes declare it instead of trusting a header)."""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="Connexion requise.")
    return user_id


def require_admin(request: Request) -> str:
    user_id = session_user_id(request)
    if not user_service.is_admin(user_id):
        raise HTTPException(status_code=403, detail="Réservé au super administrateur.")
    return user_id


def is_admin(request: Request) -> bool:
    user_id = getattr(request.state, "user_id", None)
    return bool(user_id and user_service.is_admin(user_id))


# --- download policy ---
def free_bytes(path: str) -> Optional[int]:
    """Free space of the disk holding path (its nearest existing parent), None when unknown."""
    probe = os.path.abspath(path or ".")
    while probe and not os.path.exists(probe):
        parent = os.path.dirname(probe)
        if parent == probe:
            break
        probe = parent
    try:
        return shutil.disk_usage(probe).free
    except OSError:
        return None


def ensure_free_space(path: str):
    minimum = float(settings_service.get_settings().get("min_free_gb") or 0) * 1024 ** 3
    free = free_bytes(path)
    if minimum and free is not None and free < minimum:
        raise HTTPException(status_code=507, detail=(
            f"Espace disque insuffisant sur le serveur ({free / 1024 ** 3:.1f} Go libres, "
            f"{minimum / 1024 ** 3:.0f} Go à garder libres)."))


def require_server_downloads(request: Request) -> str:
    """Downloads into the server's library: allowed by the administrator, and room left on its disk."""
    user_id = session_user_id(request)
    if not settings_service.get_settings().get("server_downloads", True) and not user_service.is_admin(user_id):
        raise HTTPException(status_code=403, detail=(
            "Le téléchargement sur le serveur est désactivé par l'administrateur : "
            "utilisez « Sur cet appareil »."))
    ensure_free_space(settings_service.get_root_folder())
    return user_id
