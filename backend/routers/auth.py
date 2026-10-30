"""Accounts: signing in and up, one's own profile, and the super administrator's management.

Signing in takes the pseudo and the password (no list of profiles to pick from). Only the super
administrator touches other people's accounts, the server settings, the download policy and the
security tools (sessions, locks, log).
"""
import base64
import time
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile
from pydantic import BaseModel, Field

from backend.security import client_ip, free_bytes, require_admin, session_user_id
from backend.services.auth_service import SESSION_COOKIE, SESSION_DAYS, auth_service
from backend.services.settings_service import settings_service
from backend.services.user_service import AccountError, user_service

router = APIRouter(prefix="/api", tags=["Accounts"])

AVATAR_MAX = 2 * 1024 * 1024
AVATAR_TYPES = {"image/png", "image/jpeg", "image/webp", "image/gif"}


class Credentials(BaseModel):
    username: str = Field(..., max_length=64)
    password: str = Field(..., max_length=200)
    remember: bool = False


class Registration(BaseModel):
    username: str = Field(..., max_length=64)
    password: str = Field(..., max_length=200)
    avatar: Optional[str] = Field("👤", max_length=16)


class PasswordChange(BaseModel):
    current_password: str = Field(..., max_length=200)
    new_password: str = Field(..., max_length=200)


class ProfileChange(BaseModel):
    username: Optional[str] = Field(None, max_length=64)
    avatar: Optional[str] = Field(None, max_length=16)   # an emoji (pictures go through /auth/avatar)


class PasswordConfirm(BaseModel):
    password: str = Field(..., max_length=200)


class SetupCode(BaseModel):
    code: str = Field(..., max_length=64)


def _account_error(e: AccountError):
    raise HTTPException(status_code=400, detail=str(e))


def _set_session_cookie(request: Request, response: Response, token: str, remember: bool):
    response.set_cookie(
        SESSION_COOKIE, token, httponly=True, samesite="lax", path="/",
        secure=request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https",
        max_age=SESSION_DAYS * 86400 if remember else None,
    )


def _username(user_id: str) -> str:
    user = user_service.users.get(user_id)
    return user["username"] if user else user_id


# --- signing in ---
@router.get("/auth/status")
async def auth_status(request: Request):
    """Public: what the sign-in screen offers (and who is signed in on this browser)."""
    user_id = getattr(request.state, "user_id", None)
    settings = settings_service.get_settings()
    has_users = user_service.count() > 0
    setup_needed = has_users and not user_service.has_admin()
    if setup_needed:
        auth_service.setup_code()   # written for the owner of the server (data/admin-setup.txt)
    return {
        "user": user_service.get_user(user_id) if user_id else None,
        "has_users": has_users,
        "registration_open": not has_users or bool(settings.get("registration_open", True)),
        "setup_needed": setup_needed,
    }


@router.post("/auth/login")
async def login(payload: Credentials, request: Request, response: Response):
    ip = client_ip(request)
    wait = auth_service.locked_for(ip, payload.username)
    if wait:
        raise HTTPException(status_code=429, headers={"Retry-After": str(wait)},
                            detail=f"Trop d'essais : réessayez dans {max(1, round(wait / 60))} min.")
    user = user_service.authenticate(payload.username, payload.password)
    if not user:
        auth_service.login_failed(ip, payload.username)
        raise HTTPException(status_code=401, detail="Pseudo ou mot de passe incorrect.")
    auth_service.login_succeeded(ip, payload.username)
    if user.get("disabled"):
        auth_service.log("login_refused", ip=ip, username=user["username"], detail="compte désactivé")
        raise HTTPException(status_code=403, detail="Ce compte a été désactivé par l'administrateur.")
    token = auth_service.create_session(user["id"], payload.remember, ip, request.headers.get("user-agent", ""))
    _set_session_cookie(request, response, token, payload.remember)
    user_service.note_login(user["id"], ip)
    auth_service.log("login", ip=ip, username=user["username"])
    return user_service.public(user)


@router.post("/auth/register")
async def register(payload: Registration, request: Request, response: Response):
    ip = client_ip(request)
    first = user_service.count() == 0
    if not first and not settings_service.get_settings().get("registration_open", True):
        raise HTTPException(status_code=403, detail="La création de compte est fermée par l'administrateur.")
    if not auth_service.may_register(ip):
        raise HTTPException(status_code=429, detail="Trop de comptes créés depuis cette adresse : réessayez plus tard.")
    try:
        user = user_service.register_user(payload.username, payload.password, payload.avatar or "👤")
    except AccountError as e:
        _account_error(e)
    if first:
        auth_service.drop_setup_code()
    auth_service.log("account_created", ip=ip, username=user["username"],
                     detail="super administrateur" if user["role"] == "admin" else "")
    token = auth_service.create_session(user["id"], False, ip, request.headers.get("user-agent", ""))
    _set_session_cookie(request, response, token, False)
    user_service.note_login(user["id"], ip)
    return user


@router.post("/auth/logout")
async def logout(request: Request, response: Response):
    auth_service.end_session(request.cookies.get(SESSION_COOKIE))
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"status": "ok"}


@router.post("/auth/setup")
async def claim_admin(payload: SetupCode, request: Request, user_id: str = Depends(session_user_id)):
    """An install with accounts but no administrator: the server's setup code makes this account it."""
    if user_service.has_admin():
        raise HTTPException(status_code=409, detail="Il y a déjà un super administrateur.")
    if not auth_service.check_setup_code(payload.code):
        auth_service.login_failed(client_ip(request), f"setup:{user_id}")
        raise HTTPException(status_code=403, detail="Code d'installation incorrect.")
    user = user_service.make_admin(user_id)
    auth_service.drop_setup_code()
    auth_service.log("admin_claimed", ip=client_ip(request), username=user["username"])
    return user_service.get_user(user_id)


# --- one's own account ---
@router.get("/auth/me")
async def me(user_id: str = Depends(session_user_id)):
    return user_service.get_user(user_id)


@router.patch("/auth/profile")
async def update_profile(payload: ProfileChange, request: Request, user_id: str = Depends(session_user_id)):
    try:
        if payload.username is not None:
            before = _username(user_id)
            user_service.rename(user_id, payload.username)
            auth_service.log("renamed", ip=client_ip(request), username=_username(user_id), detail=f"ancien pseudo : {before}")
        if payload.avatar is not None:
            user_service.set_avatar(user_id, payload.avatar)
    except AccountError as e:
        _account_error(e)
    return user_service.get_user(user_id)


@router.post("/auth/avatar")
async def upload_avatar(user_id: str = Depends(session_user_id), file: UploadFile = File(...)):
    """Custom profile picture, kept as a data URI in the account."""
    content = await file.read(AVATAR_MAX + 1)
    if len(content) > AVATAR_MAX:
        raise HTTPException(status_code=400, detail="L'image ne doit pas dépasser 2 Mo.")
    mime = file.content_type or ""
    if mime not in AVATAR_TYPES:
        raise HTTPException(status_code=400, detail="Format d'image non pris en charge (PNG, JPEG, WebP, GIF).")
    return user_service.set_avatar(user_id, f"data:{mime};base64,{base64.b64encode(content).decode('ascii')}")


@router.post("/auth/password")
async def change_password(payload: PasswordChange, request: Request, user_id: str = Depends(session_user_id)):
    try:
        user_service.set_password(user_id, payload.new_password, current_password=payload.current_password)
    except AccountError as e:
        _account_error(e)
    # The other devices must sign in again with the new password
    ended = auth_service.end_user_sessions(user_id, keep_token=request.cookies.get(SESSION_COOKIE))
    auth_service.log("password_changed", ip=client_ip(request), username=_username(user_id))
    return {"status": "ok", "sessions_ended": ended}


@router.get("/auth/sessions")
async def my_sessions(request: Request, user_id: str = Depends(session_user_id)):
    return [s for s in auth_service.list_sessions(request.cookies.get(SESSION_COOKIE)) if s["user_id"] == user_id]


@router.delete("/auth/sessions/{session_id}")
async def end_my_session(session_id: str, user_id: str = Depends(session_user_id)):
    if not any(s["id"] == session_id and s["user_id"] == user_id for s in auth_service.list_sessions()):
        raise HTTPException(status_code=404, detail="Session introuvable.")
    auth_service.end_session_by_id(session_id)
    return {"status": "ok"}


@router.post("/auth/delete")
async def delete_my_account(payload: PasswordConfirm, request: Request, response: Response,
                            user_id: str = Depends(session_user_id)):
    user = user_service.users.get(user_id) or {}
    if not user_service.authenticate(user.get("username", ""), payload.password):
        raise HTTPException(status_code=403, detail="Mot de passe incorrect.")
    try:
        user_service.delete_user(user_id)
    except AccountError as e:
        _account_error(e)
    auth_service.log("account_deleted", ip=client_ip(request), username=user.get("username", ""), detail="par lui-même")
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"status": "ok"}


# --- the super administrator ---
class AdminAccount(BaseModel):
    username: str = Field(..., max_length=64)
    password: str = Field(..., max_length=200)


class AdminAccountChange(BaseModel):
    username: Optional[str] = Field(None, max_length=64)
    disabled: Optional[bool] = None


class AdminPassword(BaseModel):
    password: str = Field(..., max_length=200)


class AdminTransfer(BaseModel):
    password: str = Field(..., max_length=200)   # the current administrator confirms with his own


class Policy(BaseModel):
    registration_open: Optional[bool] = None
    server_downloads: Optional[bool] = None
    min_free_gb: Optional[float] = Field(None, ge=0, le=10000)
    device_max_episodes: Optional[int] = Field(None, ge=1, le=500)
    device_max_active: Optional[int] = Field(None, ge=1, le=200)


@router.get("/admin/users")
async def admin_users(_: str = Depends(require_admin)):
    return user_service.list_users()


@router.post("/admin/users")
async def admin_create_user(payload: AdminAccount, request: Request, admin_id: str = Depends(require_admin)):
    try:
        user = user_service.register_user(payload.username, payload.password)
    except AccountError as e:
        _account_error(e)
    auth_service.log("account_created", ip=client_ip(request), username=user["username"], by=_username(admin_id))
    return user_service.admin_view(user_service.users[user["id"]])


@router.patch("/admin/users/{user_id}")
async def admin_change_user(user_id: str, payload: AdminAccountChange, request: Request, admin_id: str = Depends(require_admin)):
    try:
        if payload.username is not None:
            before = _username(user_id)
            user_service.rename(user_id, payload.username)
            auth_service.log("renamed", ip=client_ip(request), username=_username(user_id),
                             detail=f"ancien pseudo : {before}", by=_username(admin_id))
        if payload.disabled is not None:
            user_service.set_disabled(user_id, payload.disabled)
            if payload.disabled:
                auth_service.end_user_sessions(user_id)
            auth_service.log("disabled" if payload.disabled else "enabled", ip=client_ip(request),
                             username=_username(user_id), by=_username(admin_id))
    except AccountError as e:
        _account_error(e)
    user = user_service.users.get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Compte introuvable.")
    return user_service.admin_view(user)


@router.post("/admin/users/{user_id}/password")
async def admin_reset_password(user_id: str, payload: AdminPassword, request: Request, admin_id: str = Depends(require_admin)):
    try:
        user_service.set_password(user_id, payload.password)
    except AccountError as e:
        _account_error(e)
    keep = request.cookies.get(SESSION_COOKIE) if user_id == admin_id else None
    auth_service.end_user_sessions(user_id, keep_token=keep)
    auth_service.log("password_reset", ip=client_ip(request), username=_username(user_id), by=_username(admin_id))
    return {"status": "ok"}


@router.post("/admin/users/{user_id}/make-admin")
async def admin_transfer(user_id: str, payload: AdminTransfer, request: Request, admin_id: str = Depends(require_admin)):
    if not user_service.authenticate(_username(admin_id), payload.password):
        raise HTTPException(status_code=403, detail="Mot de passe incorrect.")
    try:
        user = user_service.make_admin(user_id)
    except AccountError as e:
        _account_error(e)
    auth_service.log("admin_transferred", ip=client_ip(request), username=user["username"], by=_username(admin_id))
    return user


@router.delete("/admin/users/{user_id}")
async def admin_delete_user(user_id: str, request: Request, admin_id: str = Depends(require_admin)):
    name = _username(user_id)
    try:
        deleted = user_service.delete_user(user_id)
    except AccountError as e:
        _account_error(e)
    if not deleted:
        raise HTTPException(status_code=404, detail="Compte introuvable.")
    auth_service.log("account_deleted", ip=client_ip(request), username=name, by=_username(admin_id))
    return {"status": "ok"}


@router.get("/admin/security")
async def admin_security(request: Request, _: str = Depends(require_admin)):
    sessions = auth_service.list_sessions(request.cookies.get(SESSION_COOKIE))
    for s in sessions:
        s["username"] = _username(s.pop("user_id"))
    return {"sessions": sessions, "lockouts": auth_service.lockouts(), "events": auth_service.recent_events(150)}


@router.delete("/admin/sessions/{session_id}")
async def admin_end_session(session_id: str, request: Request, admin_id: str = Depends(require_admin)):
    user_id = auth_service.end_session_by_id(session_id)
    if not user_id:
        raise HTTPException(status_code=404, detail="Session introuvable.")
    auth_service.log("session_ended", ip=client_ip(request), username=_username(user_id), by=_username(admin_id))
    return {"status": "ok"}


@router.delete("/admin/lockouts/{key}")
async def admin_unlock(key: str, request: Request, admin_id: str = Depends(require_admin)):
    if not auth_service.unlock(key):
        raise HTTPException(status_code=404, detail="Blocage introuvable.")
    auth_service.log("unlocked", ip=client_ip(request), detail=key, by=_username(admin_id))
    return {"status": "ok"}


@router.get("/admin/policy")
async def admin_policy(_: str = Depends(require_admin)):
    settings = settings_service.get_settings()
    free = free_bytes(settings_service.get_root_folder())
    return {key: settings.get(key) for key in Policy.model_fields} | {
        "disk_free_gb": round(free / 1024 ** 3, 1) if free is not None else None, "checked_at": time.time()}


@router.post("/admin/policy")
async def admin_set_policy(payload: Policy, request: Request, admin_id: str = Depends(require_admin)):
    changes = payload.model_dump(exclude_none=True)
    settings_service.update_settings(changes)
    auth_service.log("policy_changed", ip=client_ip(request), by=_username(admin_id),
                     detail=", ".join(f"{k}={v}" for k, v in changes.items()))
    return await admin_policy(admin_id)


@router.get("/policy")
async def public_policy(user_id: str = Depends(session_user_id)):
    """What the interface offers this user (server downloads or this device only)."""
    settings = settings_service.get_settings()
    admin = user_service.is_admin(user_id)
    return {
        "server_downloads": admin or bool(settings.get("server_downloads", True)),
        "device_max_episodes": int(settings.get("device_max_episodes") or 50),
        "is_admin": admin,
    }
