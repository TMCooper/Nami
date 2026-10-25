import asyncio
import time

import httpx
import pytest

from backend.services import catalog_service as catalog_module
from backend.services.catalog_service import CatalogService


@pytest.mark.parametrize("kind,url,expected", [
    ("hls", "https://cdn.test/v/master", "m3u8"),
    ("mp4", "https://cdn.test/v.mp4", "mp4"),
    ("embed", "https://player.test/e/1", None),
    ("", "https://cdn.test/v.mp4?token=1", "mp4"),
    ("", "https://cdn.test/v/master", "m3u8"),
])
def test_resolver_type_mapping(kind, url, expected):
    assert CatalogService._stream_type(kind, url) == expected


def _service_with_resolver(payload: dict, status: int = 200) -> CatalogService:
    service = CatalogService()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/resolve"
        return httpx.Response(status, json=payload)

    service.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return service


def test_mp4_host_is_no_longer_labelled_m3u8():
    service = _service_with_resolver({"status": "success", "host": "sendvid", "stream_url": "https://s.test/v.mp4", "type": "mp4"})
    result = asyncio.run(service.resolve_stream("https://sendvid.com/embed/abc"))
    assert result["stream_url"] == "https://s.test/v.mp4"
    assert result["stream_type"] == "mp4"
    assert result["host"] == "sendvid"


def test_embed_fallback_keeps_only_the_iframe():
    service = _service_with_resolver({
        "status": "fallback", "host": "voe", "stream_url": "https://voe.test/e/1", "type": "embed",
        "embed_url": "https://voe.test/e/1"
    })
    result = asyncio.run(service.resolve_stream("https://voe.test/e/1"))
    assert result["stream_url"] is None
    assert result["iframe_url"] == "https://voe.test/e/1"


class _NoCovers:
    """Registry stub: nothing known yet, records registrations."""
    def __init__(self):
        self.saved = {}

    def lookup(self, title, source="voiranime"):
        return self.saved.get(title, "")

    def register(self, title, cover, source="voiranime"):
        self.saved[title] = cover


@pytest.fixture
def isolated(monkeypatch):
    registry = _NoCovers()
    monkeypatch.setattr(catalog_module, "cover_registry", registry)
    monkeypatch.setattr(catalog_module.cache_service, "get_anime_details", lambda source, key: None)
    return registry


def _page_service(handler) -> CatalogService:
    service = CatalogService()
    service.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return service


def test_concurrent_resolutions_of_one_page_share_a_single_scrape(isolated):
    hits = []

    async def handler(request):
        hits.append(str(request.url))
        await asyncio.sleep(0.05)
        return httpx.Response(200, text='<meta property="og:image" content="https://voir-anime.to/c.jpg">')

    service = _page_service(handler)

    async def scenario():
        return await asyncio.gather(*(service._resolve_voiranime_cover("X", "https://voir-anime.to/anime/x/") for _ in range(4)))

    assert asyncio.run(scenario()) == ["https://voir-anime.to/c.jpg"] * 4
    assert len(hits) == 1


def test_recently_failed_pages_give_their_slot_to_the_next_entries(isolated):
    hits = []

    async def handler(request):
        hits.append(request.url.path)
        return httpx.Response(404)

    service = _page_service(handler)
    items = [{"title": f"T{i}", "url": f"https://voir-anime.to/anime/p{i}/", "cover": ""} for i in range(4)]

    async def scenario():
        await service._fill_missing_voiranime_covers(items, limit=2, wait_seconds=1.0)
        await service._fill_missing_voiranime_covers(items, limit=2, wait_seconds=1.0)

    asyncio.run(scenario())
    assert sorted(hits) == ["/anime/p0/", "/anime/p1/", "/anime/p2/", "/anime/p3/"]


def test_cached_details_without_cover_are_returned_without_waiting(monkeypatch):
    service = CatalogService()
    cached = {"title": "Slow", "url": "https://voir-anime.to/anime/slow/", "cover": "", "source": "voiranime",
              "episodes": [{"num": 1, "title": "Ep 1", "url": "u", "embed_url": "u"}]}
    monkeypatch.setattr(catalog_module.cache_service, "get_anime_details", lambda source, key: dict(cached))
    monkeypatch.setattr(catalog_module.cache_service, "add_recent_anime", lambda uid, anime: None)

    async def slow_repair(cache_key, details, url):
        await asyncio.sleep(10)

    monkeypatch.setattr(service, "_repair_details_cover", slow_repair)

    async def scenario():
        start = time.monotonic()
        res = await service.get_details(cached["url"], "voiranime")
        elapsed = time.monotonic() - start
        for task in list(service._background_tasks):
            task.cancel()
        return res, elapsed

    res, elapsed = asyncio.run(scenario())
    assert res["title"] == "Slow"
    assert elapsed < 1.0


def test_legacy_anime_sama_art_is_not_trusted_for_voiranime_entries():
    service = CatalogService()
    grouped = service._group_voiranime_entries([
        {"title": "One Piece Film Red", "link": "https://voir-anime.to/anime/one-piece-film-red/",
         "cover": "https://raw.githubusercontent.com/Anime-Sama/IMG/img/contenu/one-piece.jpg"},
        {"title": "Bocchi", "link": "https://voir-anime.to/anime/bocchi/", "cover": "data:image/gif;base64,R0lG"},
    ])
    assert all(g["cover"] == "" for g in grouped)
