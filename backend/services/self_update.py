"""Nami's own update, next to the APIs' and YoitsuWrap's (Paramètres > Mises à jour).

Nami's repository is private: only the machine that cloned it, with its credentials, can fetch it.
- git checkout (development, bare metal): Nami fetches its branch and fast-forwards it (refused when
  tracked files were changed locally or the branch diverged), installs the requirements, rebuilds the
  interface (npm), then restarts itself;
- Docker: the container holds no checkout. The host runs updater.sh / updater.ps1 next to
  docker-compose.yml: it writes what it knows into data/nami-update/state.json and rebuilds Nami
  (git pull + new image) when the interface drops data/nami-update/request.

A restart is a clean stop (the APIs are stopped, the history saved), then the same command again.
"""
import json
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from typing import Optional

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
UPDATE_DIR = os.path.join(PROJECT_ROOT, "data", "nami-update")
STATE_FILE = os.path.join(UPDATE_DIR, "state.json")
REQUEST_FILE = os.path.join(UPDATE_DIR, "request")
HOST_ALIVE = 60          # seconds: a host updater that wrote nothing for longer is not running
RESTART_DELAY = 1.5      # seconds left to the HTTP answer before the restart

_restart_requested = False


def _git(*args: str, timeout: float = 60) -> subprocess.CompletedProcess:
    # Never wait for a password prompt: the update runs in the background
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0",
           "GIT_SSH_COMMAND": os.environ.get("GIT_SSH_COMMAND", "ssh -o BatchMode=yes -o ConnectTimeout=10")}
    return subprocess.run(["git", *args], cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=timeout, env=env)


def mode() -> str:
    """'git' (checkout), 'host' (Docker, host updater) or 'none'."""
    if os.path.isdir(os.path.join(PROJECT_ROOT, ".git")) and shutil.which("git"):
        return "git"
    if os.path.exists(STATE_FILE):
        return "host"
    return "none"


def _read_state() -> dict:
    try:
        with open(STATE_FILE, encoding="utf-8-sig") as f:   # updater.ps1 (Windows PowerShell) writes a BOM
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _host_alive(state: dict) -> bool:
    return time.time() - float(state.get("alive_at") or 0) < HOST_ALIVE


def _git_status() -> dict:
    branch = _git("rev-parse", "--abbrev-ref", "HEAD", timeout=10).stdout.strip() or "main"
    local = _git("rev-parse", "HEAD", timeout=10).stdout.strip()
    remote = ""
    try:
        res = _git("ls-remote", "origin", f"refs/heads/{branch}", timeout=25)
        remote = res.stdout.split()[0] if res.returncode == 0 and res.stdout.strip() else ""
    except subprocess.TimeoutExpired:
        pass
    note = "" if remote else "Dépôt distant injoignable (identifiants git de cette machine ?)"
    return {"branch": branch, "local": local, "remote": remote, "note": note}


def status() -> dict:
    """The 'nami' entry of /api/updates/check."""
    current = mode()
    if current == "git":
        info = _git_status()
    elif current == "host":
        state = _read_state()
        info = {"branch": state.get("branch") or "", "local": state.get("local") or "", "remote": state.get("remote") or "",
                "note": ""}
        if not _host_alive(state):
            info["note"] = "L'outil de mise à jour de la machine hôte (updater.sh) ne tourne pas."
        elif state.get("state") == "updating":
            info["note"] = "Mise à jour en cours sur la machine hôte…"
        elif state.get("state") == "error":
            info["note"] = state.get("message") or "La dernière mise à jour a échoué."
    else:
        info = {"branch": "", "local": "", "remote": "",
                "note": "Installation Docker : lancez updater.sh (ou updater.ps1) à côté de docker-compose.yml sur la machine hôte."}
    local, remote = info["local"], info["remote"]
    return {
        "name": "Nami" + (f" ({info['branch']})" if info["branch"] else ""),
        "repo_url": "https://github.com/TMCooper/Nami",
        "current_version": local[:7] or "Inconnu",
        "latest_version": remote[:7] or "Inconnu",
        "up_to_date": not (local and remote and local != remote),
        "mode": current,
        "note": info["note"],
        "restarts": True,
        "cloned": True,
    }


def _run(cmd: list, cwd: str, timeout: float) -> Optional[str]:
    """None when it worked, else the end of its output."""
    try:
        res = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as e:
        return str(e)
    return None if res.returncode == 0 else (res.stderr or res.stdout).strip()[-300:]


def _apply_git() -> dict:
    if _git("status", "--porcelain", "--untracked-files=no", timeout=20).stdout.strip():
        return {"status": "error", "message": "Des fichiers de Nami ont été modifiés sur cette machine : mise à jour annulée."}
    branch = _git("rev-parse", "--abbrev-ref", "HEAD", timeout=10).stdout.strip()
    before = _git("rev-parse", "HEAD", timeout=10).stdout.strip()
    fetch = _git("fetch", "origin", branch, timeout=180)
    if fetch.returncode != 0:
        return {"status": "error", "message": f"Récupération impossible : {(fetch.stderr or fetch.stdout).strip()[-200:]}"}
    merge = _git("merge", "--ff-only", "FETCH_HEAD", timeout=60)
    if merge.returncode != 0:
        return {"status": "error", "message": "La branche locale a des commits que le dépôt n'a pas : mise à jour annulée."}
    after = _git("rev-parse", "HEAD", timeout=10).stdout.strip()
    if after == before:
        return {"status": "up_to_date", "message": "Nami est déjà à jour."}

    notes = []
    error = _run([sys.executable, "-m", "pip", "install", "--no-cache-dir", "-r", "requirements.txt"], PROJECT_ROOT, 900)
    if error:
        notes.append(f"dépendances Python : {error}")
    frontend = os.path.join(PROJECT_ROOT, "frontend")
    npm = shutil.which("npm")
    if npm and os.path.exists(os.path.join(frontend, "package.json")):
        error = _run([npm, "install", "--no-audit", "--no-fund"], frontend, 900) or _run([npm, "run", "build"], frontend, 900)
        if error:
            notes.append(f"interface non reconstruite : {error}")
    elif os.path.exists(os.path.join(frontend, "package.json")):
        notes.append("interface non reconstruite (npm absent)")
    message = f"Nami mis à jour ({before[:7]} → {after[:7]}), redémarrage…"
    return {"status": "updated", "restart": True, "message": message + (f" ({'; '.join(notes)})" if notes else ""),
            "new_commit": after[:7]}


def _apply_host() -> dict:
    state = _read_state()
    if not _host_alive(state):
        return {"status": "error", "message": "L'outil de mise à jour de la machine hôte (updater.sh) ne tourne pas."}
    if state.get("state") == "updating":
        return {"status": "requested", "message": "Une mise à jour est déjà en cours sur la machine hôte."}
    os.makedirs(UPDATE_DIR, exist_ok=True)
    with open(REQUEST_FILE, "w", encoding="utf-8") as f:
        json.dump({"requested_at": time.time()}, f)
    return {"status": "requested", "host_rebuild": True,
            "message": "La machine hôte reconstruit Nami : il redémarre dans quelques minutes."}


def apply() -> dict:
    current = mode()
    if current == "git":
        return _apply_git()
    if current == "host":
        return _apply_host()
    return {"status": "error", "message": status()["note"]}


def request_restart():
    """Clean stop then the same command again (main.py's lifespan does the exec once everything is closed)."""
    global _restart_requested
    _restart_requested = True

    def stop():
        time.sleep(RESTART_DELAY)
        signal.raise_signal(signal.SIGTERM)

    threading.Thread(target=stop, daemon=True).start()


def restart_requested() -> bool:
    return _restart_requested


def exec_again():
    """Replaces this process by the same command (same PID in Docker): the new code and wrapper are loaded."""
    argv = list(sys.argv)
    if argv and argv[0].lower().endswith(".exe"):
        argv = ["-m", "uvicorn", *argv[1:]]   # Windows console script: not a Python file
    print("[Nami] Redémarrage…", flush=True)
    os.execv(sys.executable, [sys.executable, *argv])
