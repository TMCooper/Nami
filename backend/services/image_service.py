import os
import time
import asyncio
import hashlib
import httpx
from typing import Optional, Tuple
from urllib.parse import urljoin

from backend.services.http_headers import USER_AGENT, image_referer
from backend.services.net_safety import assert_public_http_url, peer_is_public, UnsafeUrlError

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# New directory on purpose: data/cache/images may hold unvalidated bodies cached by older builds.
IMAGE_CACHE_DIR = os.path.join(PROJECT_ROOT, "data", "cache", "img")

MIN_IMAGE_BYTES = 512                       # rejects 1x1 lazy-load placeholders
MAX_IMAGE_BYTES = 15 * 1024 * 1024
CACHE_MAX_BYTES = 500 * 1024 * 1024
CACHE_TARGET_BYTES = 400 * 1024 * 1024
NEGATIVE_TTL_MISSING = 6 * 3600
NEGATIVE_TTL_TRANSIENT = 600
NEGATIVE_CACHE_MAX = 5000
PRUNE_EVERY_WRITES = 100

def sniff_image_type(head: bytes) -> Optional[str]:
    """Media type from magic bytes. SVG and HTML are deliberately not accepted."""
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    if head[4:8] == b"ftyp" and head[8:12] in (b"avif", b"avis"):
        return "image/avif"
    if head[:2] == b"BM":
        return "image/bmp"
    return None


class ImageFetchError(Exception):
    def __init__(self, transient: bool):
        super().__init__("transient" if transient else "missing")
        self.transient = transient


class ImageService:
    def __init__(self):
        os.makedirs(IMAGE_CACHE_DIR, exist_ok=True)
        self._client: Optional[httpx.AsyncClient] = None
        self._inflight: dict = {}
        self._negative: dict = {}
        self._writes_since_prune = 0

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(15.0, connect=5.0),
                limits=httpx.Limits(max_connections=16, max_keepalive_connections=8),
                follow_redirects=False,
                trust_env=False,  # the peer address check needs direct connections
            )
        return self._client

    async def close(self):
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    @staticmethod
    def cache_key(url: str) -> str:
        return hashlib.sha256(url.encode("utf-8")).hexdigest()[:40]

    def cached_file(self, url: str) -> Optional[Tuple[str, str]]:
        path = os.path.join(IMAGE_CACHE_DIR, self.cache_key(url))
        if not os.path.isfile(path):
            return None
        try:
            with open(path, "rb") as f:
                media = sniff_image_type(f.read(32))
            if media:
                os.utime(path, None)  # LRU: keep recently served images
                return path, media
            os.remove(path)
        except OSError:
            pass
        return None

    async def get_image(self, url: str) -> Tuple[str, str]:
        """Returns (file_path, media_type) of a validated, disk-cached image. Raises ImageFetchError."""
        hit = self.cached_file(url)
        if hit:
            return hit

        key = self.cache_key(url)
        expiry = self._negative.get(key)
        if expiry and expiry > time.monotonic():
            raise ImageFetchError(transient=False)

        task = self._inflight.get(key)
        if task is None:
            task = asyncio.create_task(self._fetch_and_store(url, key))
            self._inflight[key] = task
            task.add_done_callback(lambda t, k=key: self._on_fetch_done(k, t))
        # shield: a client disconnecting must not cancel the fetch other requests are waiting on
        return await asyncio.shield(task)

    def _on_fetch_done(self, key: str, task: asyncio.Task):
        self._inflight.pop(key, None)
        if not task.cancelled():
            task.exception()  # mark as retrieved when every waiter went away
        if len(self._negative) > NEGATIVE_CACHE_MAX:
            now = time.monotonic()
            alive = sorted(((v, k) for k, v in self._negative.items() if v > now), reverse=True)
            self._negative = {k: v for v, k in alive[:NEGATIVE_CACHE_MAX // 2]}

    async def _fetch_and_store(self, url: str, key: str) -> Tuple[str, str]:
        try:
            data = await self._download(url)
            media = sniff_image_type(data[:32])
            if not media or len(data) < MIN_IMAGE_BYTES:
                raise ImageFetchError(transient=False)
        except ImageFetchError as e:
            ttl = NEGATIVE_TTL_TRANSIENT if e.transient else NEGATIVE_TTL_MISSING
            self._negative[key] = time.monotonic() + ttl
            raise

        path = os.path.join(IMAGE_CACHE_DIR, key)
        await asyncio.to_thread(self._write_atomic, path, data)
        self._writes_since_prune += 1
        if self._writes_since_prune >= PRUNE_EVERY_WRITES:
            self._writes_since_prune = 0
            asyncio.get_running_loop().run_in_executor(None, self._prune_cache)
        return path, media

    async def _download(self, url: str) -> bytes:
        client = self._get_client()
        current = url
        # Redirects are followed by hand so every hop goes through the SSRF check
        for _ in range(4):
            try:
                await assert_public_http_url(current)
            except UnsafeUrlError:
                raise ImageFetchError(transient=False)

            headers = {"User-Agent": USER_AGENT, "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8"}
            referer = image_referer(current)
            if referer:
                headers["Referer"] = referer

            try:
                async with client.stream("GET", current, headers=headers) as resp:
                    if not peer_is_public(resp):
                        raise ImageFetchError(transient=False)
                    if resp.is_redirect and resp.headers.get("location"):
                        current = urljoin(current, resp.headers["location"])
                        continue
                    if resp.status_code != 200:
                        raise ImageFetchError(transient=resp.status_code >= 500 or resp.status_code == 429)
                    if int(resp.headers.get("content-length") or 0) > MAX_IMAGE_BYTES:
                        raise ImageFetchError(transient=False)
                    chunks, total = [], 0
                    async for chunk in resp.aiter_bytes():
                        total += len(chunk)
                        if total > MAX_IMAGE_BYTES:
                            raise ImageFetchError(transient=False)
                        chunks.append(chunk)
                    return b"".join(chunks)
            except httpx.InvalidURL:
                raise ImageFetchError(transient=False)
            except httpx.HTTPError:
                raise ImageFetchError(transient=True)
        raise ImageFetchError(transient=False)

    @staticmethod
    def _write_atomic(path: str, data: bytes):
        tmp_path = f"{path}.tmp"
        with open(tmp_path, "wb") as f:
            f.write(data)
        os.replace(tmp_path, path)

    @staticmethod
    def _prune_cache():
        try:
            entries = []
            total = 0
            for name in os.listdir(IMAGE_CACHE_DIR):
                full = os.path.join(IMAGE_CACHE_DIR, name)
                st = os.stat(full)
                entries.append((st.st_mtime, st.st_size, full))
                total += st.st_size
            if total <= CACHE_MAX_BYTES:
                return
            for _mtime, size, full in sorted(entries):
                os.remove(full)
                total -= size
                if total <= CACHE_TARGET_BYTES:
                    break
        except OSError as e:
            print(f"[ImageService] Cache prune error: {e}")


image_service = ImageService()
