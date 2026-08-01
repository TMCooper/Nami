import os
import sys
import subprocess
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ANIME_SAMA_PATH = os.path.join(PROJECT_ROOT, "AnimeSamaApi")
VOIRANIME_PATH = os.path.join(PROJECT_ROOT, "voiranime_API")

procs = []


def _launch_subprocess(name, cwd, cmd):
    """Launch a subprocess and return the process handle."""
    main_file = os.path.join(cwd, cmd[-1])
    if not os.path.exists(main_file):
        print(f"[Nami] WARNING: {main_file} not found. Skipping {name}.")
        return None
    try:
        print(f"[Nami] Launching {name} (cwd={cwd})...")
        p = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        return p
    except Exception as e:
        print(f"[Nami] Error launching {name}: {e}")
        return None


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Launch AnimeSama API (Flask on http://127.0.0.1:5000)
    p_as = _launch_subprocess(
        "AnimeSama API (port 5000)",
        ANIME_SAMA_PATH,
        [sys.executable, "main.py"]
    )
    if p_as:
        procs.append(p_as)

    # Launch VoirAnime API (FastAPI on http://127.0.0.1:8000)
    p_va = _launch_subprocess(
        "VoirAnime API (port 8000)",
        VOIRANIME_PATH,
        [sys.executable, "main.py"]
    )
    if p_va:
        procs.append(p_va)

    # Give submodule APIs time to bind to ports
    await asyncio.sleep(3)
    print(f"[Nami] Submodule APIs launched. AnimeSama=5000, VoirAnime=8000")
    yield

    # Clean up subprocesses on shutdown
    for p in procs:
        try:
            p.terminate()
            p.wait(timeout=5)
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
