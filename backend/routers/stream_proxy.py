import os
import hashlib
from fastapi import APIRouter, HTTPException, Query, Response
from fastapi.responses import StreamingResponse, FileResponse
import aiohttp
from urllib.parse import unquote

router = APIRouter(prefix="/api/proxy", tags=["Stream Proxy"])

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
IMAGE_CACHE_DIR = os.path.join(PROJECT_ROOT, "data", "cache", "images")
os.makedirs(IMAGE_CACHE_DIR, exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "*/*"
}

@router.get("/image")
async def proxy_image(url: str = Query(..., description="Target cover image URL")):
    target_url = unquote(url).strip()
    if not target_url:
        raise HTTPException(status_code=400, detail="Missing url parameter")

    # Local disk cache key based on MD5 of url
    url_hash = hashlib.md5(target_url.encode("utf-8")).hexdigest()
    cache_path = os.path.join(IMAGE_CACHE_DIR, f"{url_hash}.jpg")

    if os.path.exists(cache_path) and os.path.getsize(cache_path) > 0:
        return FileResponse(
            cache_path,
            media_type="image/jpeg",
            headers={
                "Cache-Control": "public, max-age=2592000",
                "Access-Control-Allow-Origin": "*"
            }
        )

    headers = HEADERS.copy()
    if "voir-anime" in target_url:
        headers["Referer"] = "https://voir-anime.to/"
    elif "anime-sama" in target_url:
        headers["Referer"] = "https://anime-sama.fr/"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(target_url, headers=headers) as resp:
                if resp.status == 200:
                    data = await resp.read()
                    try:
                        with open(cache_path, "wb") as f:
                            f.write(data)
                    except Exception as err:
                        print(f"[ProxyImage] Warning saving cache: {err}")

                    content_type = resp.headers.get("Content-Type", "image/jpeg")
                    return Response(
                        content=data,
                        media_type=content_type,
                        headers={
                            "Cache-Control": "public, max-age=2592000",
                            "Access-Control-Allow-Origin": "*"
                        }
                    )
                else:
                    raise HTTPException(status_code=resp.status, detail=f"Image fetch returned {resp.status}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Image proxy error: {str(e)}")

@router.get("/stream")
async def proxy_stream(url: str = Query(..., description="Target video or m3u8 stream URL")):
    target_url = unquote(url)
    
    headers = HEADERS.copy()
    if "vidmoly" in target_url:
        headers["Referer"] = "https://vidmoly.net/"
        headers["Origin"] = "https://vidmoly.net"
    elif "sendvid" in target_url:
        headers["Referer"] = "https://sendvid.com/"
    elif "sibnet" in target_url:
        headers["Referer"] = "https://video.sibnet.ru/"

    try:
        session = aiohttp.ClientSession()
        resp = await session.get(target_url, headers=headers)
        
        content_type = resp.headers.get("Content-Type", "application/octet-stream")
        
        async def iter_content():
            try:
                async for chunk in resp.content.iter_chunked(64 * 1024):
                    yield chunk
            finally:
                await session.close()

        return StreamingResponse(
            iter_content(),
            status_code=resp.status,
            media_type=content_type,
            headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, OPTIONS",
                "Cache-Control": "no-cache"
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Proxy error: {str(e)}")

