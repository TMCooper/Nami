import asyncio

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.routers import device_download as device_module
from backend.services import source_health as health_module
from backend.services.source_health import SourceHealth
from backend.yoitsu.index import Entry
from backend.yoitsu.wrapper_store import _observe, progress_of

from tests.test_yoitsu_gateway import _make_gateway

client = TestClient(app)


@pytest.fixture
def settings(monkeypatch):
    """Settings kept in memory: the switches never write the repo's data/settings.json."""
    store = {"disabled_sources": []}
    monkeypatch.setattr(health_module.settings_service, "get_settings", lambda: store)
    monkeypatch.setattr(health_module.settings_service, "update_settings", lambda new: store.update(new) or store)
    return store


def _health_with(handler):
    health = SourceHealth()

    async def check(source):
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as c:
            return await health._check_one(c, source)
    return health, check


def test_a_source_is_usable_until_known_down_or_switched_off(settings):
    health = SourceHealth()
    assert health.usable("voiranime")                      # not checked yet: tried
    health._state["voiranime"] = {"status": "site_unreachable", "message": "x"}
    assert not health.usable("voiranime")
    health._state["voiranime"] = {"status": "ok", "message": ""}
    health.set_enabled("voiranime", False)
    assert settings["disabled_sources"] == ["voiranime"] and not health.usable("voiranime")
    snap = health.snapshot()
    assert snap["voiranime"]["enabled"] is False and snap["anime_sama"]["status"] == "unknown"
    health.set_enabled("voiranime", True)
    assert health.usable("voiranime")


def test_checks_tell_a_stopped_api_from_a_blocked_site():
    def api_down(request):
        raise httpx.ConnectError("refused")
    _, check = _health_with(api_down)
    assert asyncio.run(check("voiranime"))["status"] == "api_down"

    def site_down(request):
        if request.url.path.endswith("/status"):
            return httpx.Response(200, json={"API Status": "Online"})   # the API says online...
        raise httpx.ConnectError("getaddrinfo failed")                  # ...but its site is unreachable
    _, check = _health_with(site_down)
    assert asyncio.run(check("voiranime"))["status"] == "site_unreachable"

    def challenge(request):
        if request.url.path.endswith("/status"):
            return httpx.Response(200)
        return httpx.Response(403, headers={"cf-mitigated": "challenge", "server": "cloudflare"})
    _, check = _health_with(challenge)
    assert asyncio.run(check("voiranime"))["status"] == "cloudflare"

    _, check = _health_with(lambda request: httpx.Response(200))
    assert asyncio.run(check("anime_sama"))["status"] == "ok"


def test_down_sources_are_skipped_without_waiting(tmp_path, monkeypatch, settings):
    from backend.yoitsu import gateway as gateway_module
    gw = _make_gateway(tmp_path, monkeypatch, [], [], [])
    gw.get_info = gateway_module.YoitsuGateway.get_info.__get__(gw)   # the real one, not the fixture's fake
    monkeypatch.setattr(gateway_module.source_health, "_state", {"voiranime": {"status": "api_down", "message": ""}})
    assert asyncio.run(gw.get_info("voiranime", "Frieren")) == []


def test_device_download_validates_and_explains_failures(monkeypatch):
    assert client.get("/api/device-download").status_code == 422          # no url at all
    assert client.get("/api/device-download", params={"url": "ftp://x"}).status_code == 400

    monkeypatch.setattr(device_module.shutil, "which", lambda name: None)
    res = client.get("/api/device-download", params={"url": "https://cdn.test/a/master.m3u8"})
    assert res.status_code == 503 and "ffmpeg" in res.json()["detail"]

    monkeypatch.setattr(device_module.shutil, "which", lambda name: "ffmpeg")

    async def nothing(url, source="anime_sama"):
        return {"stream_url": None}
    monkeypatch.setattr(device_module.catalog_service, "resolve_stream", nothing)
    res = client.get("/api/device-download", params={"url": "https://vidmoly.net/embed-x.html"})
    assert res.status_code == 422 and "téléchargeable" in res.json()["detail"]


def test_first_playable_player_wins():
    async def resolve(url, source="anime_sama"):
        return {"stream_url": "https://cdn.test/v/master.m3u8", "stream_type": "m3u8"} if "good" in url else {"stream_url": None}

    original = device_module.catalog_service.resolve_stream
    device_module.catalog_service.resolve_stream = resolve
    try:
        found = asyncio.run(device_module._playable(["https://dead.test/embed", "https://good.test/embed"]))
        assert found == ("https://cdn.test/v/master.m3u8", "m3u8")
        assert asyncio.run(device_module._playable(["https://cdn.test/v.mp4"])) == ("https://cdn.test/v.mp4", "mp4")
    finally:
        device_module.catalog_service.resolve_stream = original


def test_download_names_are_safe_everywhere():
    header = device_module._content_disposition('Frieren : Saison 1/ép "1"')
    assert header == ('attachment; filename="Frieren  Saison 1p 1.mp4"; '
                      "filename*=UTF-8''Frieren%20%20Saison%201%C3%A9p%201.mp4")


HXD = "https://voir-anime.to/anime/high-school-dxd/"
HXD_NEW = "https://voir-anime.to/anime/high-school-dxd-new/"
HXD_BORN = "https://voir-anime.to/anime/high-school-dxd-born/"
HXD_ROWS = [
    {"base_url": HXD, "title": "High School DxD", "cover": "", "synopsis": "Issei Hyoudou...", "Saison": "Saison 1",
     "url": HXD, "_vostfr_url": HXD, "_vf_url": None},
    {"base_url": HXD, "title": "High School DxD", "cover": "", "synopsis": "", "Saison": "New",
     "url": HXD_NEW, "_vostfr_url": HXD_NEW, "_vf_url": None},
    {"base_url": HXD, "title": "High School DxD", "cover": "", "synopsis": "", "Saison": "BorN",
     "url": HXD_BORN, "_vostfr_url": HXD_BORN, "_vf_url": None},
]


def test_voiranime_seasons_follow_the_api_labels(tmp_path, monkeypatch):
    entries = [Entry("voiranime", HXD, "High School DxD"), Entry("voiranime", HXD_NEW, "High School DxD New")]
    gw = _make_gateway(tmp_path, monkeypatch, [], HXD_ROWS, entries)
    details = asyncio.run(gw.details("a-high-school-dxd"))
    seasons = {s["label"]: s for s in details["seasons"]}
    assert set(seasons) == {"Saison 1", "New", "BorN"}           # BorN: a post only the API knew
    assert seasons["New"]["variants"][0]["url"] == HXD_NEW
    assert seasons["BorN"]["variants"][0]["url"] == HXD_BORN
    assert details["synopsis"]["text"].startswith("Issei")


def test_catalogue_alternative_titles_merge_cards(tmp_path, monkeypatch):
    as_page = Entry("anime_sama", "https://anime-sama.to/catalogue/kimetsu", "Demon Slayer")
    va_post = Entry("voiranime", "https://voir-anime.to/anime/kimetsu-no-yaiba/", "Kimetsu no Yaiba")
    other_page = Entry("anime_sama", "https://anime-sama.to/catalogue/kny-other", "Kimetsu Gakuen")
    gw = _make_gateway(tmp_path, monkeypatch, [], [], [], catalog=[as_page, va_post, other_page])
    assert len(gw.index.group([as_page, va_post])) == 2
    learned = gw.learn_catalogue_names([(as_page, ["Kimetsu no Yaiba", "Kimetsu Gakuen", "Yaiba"])])
    assert learned == 1
    assert len(gw.index.group([as_page, va_post])) == 1           # one card now
    assert gw.aliases.find("kimetsu gakuen") != gw.aliases.find("demon slayer")   # another page never joins


def test_build_progress_is_read_from_the_wrapper_calls():
    job = {}

    class Resp:
        def __init__(self, data):
            self.data = data

        def json(self):
            return self.data

    assert progress_of(job)["step"] == "Recherche des saisons"
    _observe(job, "http://127.0.0.1:5000/api/getInfoAnime?q=Frieren",
             Resp([{"Saison": "Saison 1"}, {"Saison": "Saison 2"}, {"Saison": "Scans"}]))
    _observe(job, "http://127.0.0.1:5000/api/getSpecificAnime?q=Frieren&s=Saison 1&v=vostfr", Resp({}))
    _observe(job, "http://127.0.0.1:5000/api/getAnimeLink?n=Frieren&s=Saison 1&v=vostfr", Resp([{}] * 28))
    job["checked"] = 14
    p = progress_of(job)
    assert p["value"] == 0.25 and p["step"] == "Saison 1 · épisode 15/28"
    _observe(job, "http://127.0.0.1:5000/api/getSpecificAnime?q=Frieren&s=Saison 2&v=vostfr", Resp({}))
    assert progress_of(job)["value"] == 0.5


def test_search_keeps_what_the_source_matched_through_other_names(tmp_path, monkeypatch):
    from backend.yoitsu import gateway as gateway_module
    gw = _make_gateway(tmp_path, monkeypatch, [], [], [])

    async def as_search(q):
        return [
            {"title": "Shingeki no Kyojin", "source": "anime_sama", "url": "https://anime-sama.to/catalogue/shingeki-no-kyojin", "cover": "", "score": 95.0},
            {"title": "Attaque des Titans Junior High-school", "source": "anime_sama", "url": "https://anime-sama.to/catalogue/shingeki-kyojin-chuugakkou", "cover": "", "score": 93.0},
        ]

    async def va_search(q, group=True, cover_wait=None):
        return []

    monkeypatch.setattr(gateway_module.catalog_service, "_search_anime_sama", as_search)
    monkeypatch.setattr(gateway_module.catalog_service, "_search_voiranime", va_search)
    titles = [r["title"] for r in asyncio.run(gw.search("attaque des titans"))]
    assert titles[0] == "Shingeki no Kyojin" and "Attaque des Titans Junior High-school" in titles
