from fastapi import APIRouter, HTTPException, Query, Response
from fastapi.responses import StreamingResponse
import aiohttp
from urllib.parse import unquote

router = APIRouter(prefix="/api/proxy", tags=["Stream Proxy"])

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "*/*"
}

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
