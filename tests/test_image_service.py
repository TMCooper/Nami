import asyncio

import pytest

from backend.services import image_service as image_module
from backend.services.image_service import ImageService, ImageFetchError, sniff_image_type

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 2048
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 2048


def test_sniff_image_type_accepts_images_rejects_html_and_svg():
    assert sniff_image_type(PNG[:32]) == "image/png"
    assert sniff_image_type(JPEG[:32]) == "image/jpeg"
    assert sniff_image_type(b"RIFF\x00\x00\x00\x00WEBPVP8 ") == "image/webp"
    assert sniff_image_type(b"<!DOCTYPE html><html>") is None
    assert sniff_image_type(b"<svg xmlns='http://www.w3.org/2000/svg'>") is None


@pytest.fixture
def service(tmp_path, monkeypatch):
    monkeypatch.setattr(image_module, "IMAGE_CACHE_DIR", str(tmp_path))
    return ImageService()


def test_valid_image_is_cached_on_disk(service, monkeypatch):
    calls = []

    async def fake_download(url):
        calls.append(url)
        return PNG

    monkeypatch.setattr(service, "_download", fake_download)

    async def scenario():
        path, media = await service.get_image("https://cdn.test/a.png")
        again = await service.get_image("https://cdn.test/a.png")
        return path, media, again

    path, media, again = asyncio.run(scenario())
    assert media == "image/png"
    assert again == (path, media)
    assert calls == ["https://cdn.test/a.png"]


def test_html_body_is_rejected_and_negatively_cached(service, monkeypatch):
    calls = []

    async def fake_download(url):
        calls.append(url)
        return b"<html><body>blocked</body></html>" * 100

    monkeypatch.setattr(service, "_download", fake_download)

    async def scenario():
        for _ in range(2):
            with pytest.raises(ImageFetchError):
                await service.get_image("https://cdn.test/blocked.jpg")

    asyncio.run(scenario())
    assert len(calls) == 1, "a failed URL must not be fetched again before its negative TTL expires"


def test_concurrent_requests_share_one_download(service, monkeypatch):
    calls = []

    async def fake_download(url):
        calls.append(url)
        await asyncio.sleep(0.05)
        return JPEG

    monkeypatch.setattr(service, "_download", fake_download)

    async def scenario():
        return await asyncio.gather(*(service.get_image("https://cdn.test/b.jpg") for _ in range(5)))

    results = asyncio.run(scenario())
    assert len(calls) == 1
    assert all(r[1] == "image/jpeg" for r in results)


def test_ssrf_target_is_refused_without_network(service):
    with pytest.raises(ImageFetchError):
        asyncio.run(service._download("http://127.0.0.1:8000/catalog"))
