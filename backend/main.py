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
from fastapi.responses import FileResponse

from backend.services.update_service import update_service, ANIME_SAMA_PATH, VOIRANIME_PATH

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_submodule_processes = {}

def _start_submodules():
    """Launch AnimeSama and VoirAnime APIs as isolated background subprocesses."""
    global _submodule_processes

    # 1. Ensure AnimeSamaApi is cloned
    if not os.path.exists(ANIME_SAMA_PATH):
        print("[Nami] AnimeSamaApi not detected. Auto-cloning from GitHub...")
        update_service.ensure_cloned("https://github.com/TMCooper/AnimeSamaApi.git", ANIME_SAMA_PATH)

    # 2. Ensure VoirAnime_API is cloned
    if not os.path.exists(VOIRANIME_PATH):
        print("[Nami] VoirAnime_API not detected. Auto-cloning from GitHub...")
        update_service.ensure_cloned("https://github.com/TMCooper/voiranime_API.git", VOIRANIME_PATH)

    # Launch AnimeSama API (Flask on 5000)
    try:
        p_as = subprocess.Popen(
            [sys.executable, "main.py"],
            cwd=ANIME_SAMA_PATH,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        _submodule_processes["animesama"] = p_as
        print("[Nami] AnimeSama API process launched on port 5000.")
    except Exception as e:
        print(f"[Nami] Error launching AnimeSama process: {e}")

    # Launch VoirAnime API (Uvicorn on 8000)
    try:
        p_va = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "src.main:app", "--host", "127.0.0.1", "--port", "8000", "--log-level", "warning"],
            cwd=VOIRANIME_PATH,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        _submodule_processes["voiranime"] = p_va
        print("[Nami] VoirAnime API process launched on port 8000.")
    except Exception as e:
        print(f"[Nami] Error launching VoirAnime process: {e}")

def restart_submodule(name: str):
    """Gracefully terminates and restarts a specific API process."""
    global _submodule_processes
    old_proc = _submodule_processes.get(name)
    if old_proc:
        try:
            old_proc.terminate()
            old_proc.wait(timeout=3)
        except Exception:
            try:
                old_proc.kill()
            except Exception:
                pass

    if name == "animesama" and os.path.exists(ANIME_SAMA_PATH):
        p_as = subprocess.Popen(
            [sys.executable, "main.py"],
            cwd=ANIME_SAMA_PATH,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        _submodule_processes["animesama"] = p_as
        print("[Nami] AnimeSama API process restarted.")

    elif name == "voiranime" and os.path.exists(VOIRANIME_PATH):
        p_va = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "src.main:app", "--host", "127.0.0.1", "--port", "8000", "--log-level", "warning"],
            cwd=VOIRANIME_PATH,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        _submodule_processes["voiranime"] = p_va
        print("[Nami] VoirAnime API process restarted.")


@asynccontextmanager
async def lifespan(app: FastAPI):
    _start_submodules()

    # Wait for APIs to be ready
    client = httpx.Client(timeout=2.0)
    
    for i in range(30):
        try:
            r1 = client.get("http://127.0.0.1:5000/status")
            if r1.status_code == 200:
                print("[Nami] AnimeSama API ready on port 5000")
                break
        except:
            pass
        time.sleep(0.5)
    
    for i in range(30):
        try:
            r2 = client.get("http://127.0.0.1:8000/status")
            if r2.status_code == 200:
                print("[Nami] VoirAnime API ready on port 8000")
                break
        except:
            pass
        time.sleep(0.5)
    
    client.close()
    print("[Nami] All submodule APIs launched and ready.")

    yield

    # Cleanup subprocesses on shutdown
    for proc in _submodule_processes.values():
        try:
            proc.terminate()
        except Exception:
            pass


app = FastAPI(
    title="Nami API & Server",
    description="Application unifiée Streaming & Téléchargement Anime (Anime Sama & VoirAnime)",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
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

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        file_path = os.path.join(FRONTEND_DIST, full_path)
        if os.path.exists(file_path) and os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(FRONTEND_DIST, "index.html"))
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
