import os
import sys
import threading
import time
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# Ensure root dir & submodule dirs are in python path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ANIME_SAMA_PATH = os.path.join(PROJECT_ROOT, "AnimeSamaApi")
VOIRANIME_PATH = os.path.join(PROJECT_ROOT, "voiranime_API")

for p in [PROJECT_ROOT, ANIME_SAMA_PATH, VOIRANIME_PATH]:
    if p not in sys.path:
        sys.path.insert(0, p)

def start_anime_sama_api():
    """Runs AnimeSama Flask API on http://127.0.0.1:5000"""
    try:
        from AnimeSamaApi.main import Api
        print("[Nami] Starting AnimeSama API on http://127.0.0.1:5000 ...")
        Api.launch(port=5000, ip="127.0.0.1", debug_state=False, reload_status=False)
    except Exception as e:
        print(f"[Nami] Error starting AnimeSama API: {e}")

def start_voiranime_api():
    """Runs VoirAnime FastAPI on http://127.0.0.1:8000"""
    try:
        import uvicorn
        print("[Nami] Starting VoirAnime API on http://127.0.0.1:8000 ...")
        uvicorn.run("voiranime_API.src.main:app", host="127.0.0.1", port=8000, reload=False, log_level="warning")
    except Exception as e:
        print(f"[Nami] Error starting VoirAnime API: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Launch submodule APIs in background daemon threads
    t_as = threading.Thread(target=start_anime_sama_api, daemon=True)
    t_va = threading.Thread(target=start_voiranime_api, daemon=True)
    
    t_as.start()
    t_va.start()
    
    # Allow 2 seconds for submodule APIs to bind to ports
    await asyncio.sleep(2)
    yield

app = FastAPI(
    title="Nami API & Server",
    description="Application unifiée Streaming & Téléchargement Anime (Anime Sama & VoirAnime)",
    version="1.0.0",
    lifespan=lifespan
)

# Enable CORS for local network and dev servers
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
