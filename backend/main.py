import os
import sys
import subprocess
import time
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

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Launch AnimeSama API (Flask on http://127.0.0.1:5000)
    try:
        print("[Nami] Launching AnimeSama API (port 5000)...")
        p_as = subprocess.Popen([sys.executable, "main.py"], cwd=ANIME_SAMA_PATH)
        procs.append(p_as)
    except Exception as e:
        print(f"[Nami] Error launching AnimeSama API: {e}")

    # Launch VoirAnime API (FastAPI on http://127.0.0.1:8000)
    try:
        print("[Nami] Launching VoirAnime API (port 8000)...")
        p_va = subprocess.Popen([sys.executable, "main.py"], cwd=VOIRANIME_PATH)
        procs.append(p_va)
    except Exception as e:
        print(f"[Nami] Error launching VoirAnime API: {e}")

    # Give submodules 2 seconds to bind to ports
    await asyncio.sleep(2)
    yield

    # Clean up subprocesses on shutdown
    for p in procs:
        try:
            p.terminate()
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
