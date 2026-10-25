import os
import sys
import time
import asyncio
import subprocess
import httpx
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

from backend.services.update_service import update_service, ANIME_SAMA_PATH, VOIRANIME_PATH
from backend.services import api_state

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_DIR = os.path.join(PROJECT_ROOT, "data", "logs")
ANIME_SAMA_LAUNCHER = os.path.join(PROJECT_ROOT, "backend", "launchers", "animesama_launcher.py")

SUBMODULES = {
    "animesama": {
        "repo": "https://github.com/TMCooper/AnimeSamaApi.git",
        "path": ANIME_SAMA_PATH,
        "port": 5000,
        "cmd": [sys.executable, ANIME_SAMA_LAUNCHER, "--host", "127.0.0.1", "--port", "5000"],
    },
    "voiranime": {
        "repo": "https://github.com/TMCooper/voiranime_API.git",
        "path": VOIRANIME_PATH,
        "port": 8000,
        "cmd": [sys.executable, "-m", "uvicorn", "src.main:app", "--host", "127.0.0.1", "--port", "8000", "--log-level", "warning"],
    },
}

_submodule_processes = {}

def _launch_submodule(name: str):
    """Starts one API as a background process, logging to data/logs/<name>.log."""
    spec = SUBMODULES[name]
    if not os.path.exists(spec["path"]):
        print(f"[Nami] {name} introuvable ({spec['path']}), lancement ignoré.")
        return
    os.makedirs(LOG_DIR, exist_ok=True)
    env = {**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8"}
    log_path = os.path.join(LOG_DIR, f"{name}.log")
    try:
        # Keep the previous run's log (it holds the traceback when a restart was caused by a crash)
        if os.path.exists(log_path):
            os.replace(log_path, f"{log_path}.1")
    except OSError:
        pass
    try:
        with open(log_path, "w", encoding="utf-8") as log_file:
            _submodule_processes[name] = subprocess.Popen(
                spec["cmd"],
                cwd=spec["path"],
                stdin=subprocess.DEVNULL,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                env=env
            )
        print(f"[Nami] {name} API process launched on port {spec['port']}.")
    except Exception as e:
        print(f"[Nami] Error launching {name} process: {e}")

def _stop_submodule(name: str):
    proc = _submodule_processes.pop(name, None)
    if not proc:
        return
    try:
        proc.terminate()
        proc.wait(timeout=5)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass

def _start_submodules():
    """Clone (if needed) and launch AnimeSama and VoirAnime APIs as isolated background subprocesses."""
    for name, spec in SUBMODULES.items():
        if not os.path.exists(spec["path"]):
            print(f"[Nami] {name} not detected. Auto-cloning from GitHub...")
            update_service.ensure_cloned(spec["repo"], spec["path"])
        _launch_submodule(name)

def restart_submodule(name: str):
    """Gracefully terminates and restarts a specific API process, then waits until it answers.

    Blocking: called from a worker thread by the in-app updater.
    """
    api_state.api_ready[name] = False
    _stop_submodule(name)
    _launch_submodule(name)
    ready = _wait_until_ready_sync(name)
    api_state.api_ready[name] = ready
    if ready:
        # The cached YoitsuWrap Config only holds static URLs: keep it, just allow an immediate retry
        from backend.services.yoitsu_service import yoitsu_service
        yoitsu_service.allow_retry()
    print(f"[Nami] {name} API process restarted (ready={ready}).")

def _probe(name: str) -> str:
    proc = _submodule_processes.get(name)
    if proc is None:
        return "missing"
    if proc.poll() is not None:
        print(f"[Nami] {name} API exited (code {proc.returncode}), voir data/logs/{name}.log")
        return "exited"
    return "running"

def _status_url(name: str) -> str:
    return f"http://127.0.0.1:{SUBMODULES[name]['port']}/api/status"

def _wait_until_ready_sync(name: str, timeout: float = 60.0) -> bool:
    deadline = time.monotonic() + timeout
    with httpx.Client(timeout=2.0) as client:
        while time.monotonic() < deadline:
            if _probe(name) != "running":
                return False
            try:
                if client.get(_status_url(name)).status_code == 200:
                    return True
            except httpx.HTTPError:
                pass
            time.sleep(0.5)
    return False

async def _wait_until_ready(name: str, timeout: float = 60.0) -> bool:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    async with httpx.AsyncClient(timeout=2.0) as client:
        while loop.time() < deadline:
            if _probe(name) != "running":
                return False
            try:
                if (await client.get(_status_url(name))).status_code == 200:
                    print(f"[Nami] {name} API ready on port {SUBMODULES[name]['port']}")
                    return True
            except httpx.HTTPError:
                pass
            await asyncio.sleep(0.5)
    print(f"[Nami] {name} API not ready after {int(timeout)}s, voir data/logs/{name}.log")
    return False

async def _warm_up():
    names = list(SUBMODULES)
    results = await asyncio.gather(*(_wait_until_ready(name) for name in names))
    for name, ready in zip(names, results):
        api_state.api_ready[name] = ready
    from backend.services.yoitsu_service import yoitsu_service
    await asyncio.to_thread(yoitsu_service.get_config)


@asynccontextmanager
async def lifespan(app: FastAPI):
    _start_submodules()
    # Readiness is awaited in the background: the web UI is served immediately
    warm_up_task = asyncio.create_task(_warm_up())

    yield

    warm_up_task.cancel()
    from backend.services.image_service import image_service
    from backend.routers.stream_proxy import close_stream_client
    await image_service.close()
    await close_stream_client()
    for name in list(_submodule_processes):
        _stop_submodule(name)


app = FastAPI(
    title="Nami API & Server",
    description="Application unifiée Streaming & Téléchargement Anime (Anime Sama & VoirAnime)",
    version="1.0.0",
    lifespan=lifespan
)

# The UI is served by this same server (and proxied by Vite in dev), so only explicit
# extra origins are allowed: NAMI_CORS_ORIGINS="http://host:port,..."
_extra_origins = [o.strip() for o in os.environ.get("NAMI_CORS_ORIGINS", "").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", *_extra_origins],
    allow_methods=["*"],
    allow_headers=["*"],
)

from backend.routers.api import router as api_router
from backend.routers.stream_proxy import router as proxy_router

app.include_router(api_router)
app.include_router(proxy_router)

# Mount static frontend build if it exists
FRONTEND_DIST = os.path.join(PROJECT_ROOT, "frontend", "dist")
if os.path.exists(FRONTEND_DIST):
    app.mount("/assets", StaticFiles(directory=os.path.join(FRONTEND_DIST, "assets")), name="assets")

    _dist_root = os.path.realpath(FRONTEND_DIST)

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        # Unknown API routes must not fall back to index.html (the UI would try to parse HTML as JSON)
        if full_path == "api" or full_path.startswith("api/"):
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        file_path = os.path.realpath(os.path.join(_dist_root, full_path))
        if file_path.startswith(_dist_root + os.sep) and os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(_dist_root, "index.html"))
else:
    @app.get("/")
    async def root():
        return {
            "name": "Nami Server API",
            "status": "Online",
            "documentation": "/docs"
        }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8080, reload=True)
