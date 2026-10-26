import asyncio
import os

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.routers import fiche_download as fiche_module
from backend.services import download_service as download_module
from backend.services import wrapper_download
from backend.services.cache_service import cache_service
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


FOUND = {"title": "Frieren", "label": "Saison 1", "cover": "",
         "episodes": [{"num": 1, "link": "https://cdn.test/1/master.m3u8", "source": "anime_sama"},
                      {"num": 2, "link": "https://cdn.test/2/master.m3u8", "source": "voiranime"}]}


def _fake_season(items, workers):
    """What YoitsuWrap's download does to the items, without the network: progress, then the file."""
    for item in items:
        item.hook({"status": "downloading", "downloaded_bytes": 50, "fragment_index": 1, "fragment_count": 4, "speed": 2e6, "eta": 3})
        assert item.progress == 25.0
        if item.cancelled:
            item.status = "cancelled"
            continue
        os.makedirs(os.path.dirname(item.target), exist_ok=True)
        with open(item.target, "wb") as f:
            f.write(b"\0" * 200)
        item.hook({"status": "finished", "total_bytes": 200})
        item.status, item.file_path = "completed", item.target
        item._changed()
    return items


def test_fiche_downloads_explain_why_they_cannot_start(monkeypatch):
    async def answer(error):
        async def download_items(eid, season, version, nums):
            return {"error": error} if error else {**FOUND, "episodes": []}
        return download_items

    for error, code in (("not_found", 404), ("building", 409), ("expired", 409), (None, 404)):
        monkeypatch.setattr(fiche_module.yoitsu_gateway, "download_items", asyncio.run(answer(error)))
        res = client.post("/api/device-download/jobs", json={"anime_id": "a-frieren", "season": "saison-1"})
        assert res.status_code == code, error
    assert client.post("/api/downloads/fiche", json={"anime_id": "abc", "season": "s"}).status_code == 404
    assert client.post("/api/downloads/fiche", json={"anime_id": "a-x", "season": "s", "version": "jp"}).status_code == 422


def test_episodes_for_a_device_are_prepared_then_sent_and_removed(tmp_path, monkeypatch):
    jobs = fiche_module.DeviceJobs(folder=str(tmp_path))
    monkeypatch.setattr(fiche_module, "device_jobs", jobs)
    monkeypatch.setattr(fiche_module.wrapper_download, "download_season", _fake_season)

    async def download_items(eid, season, version, nums):
        return {**FOUND, "episodes": [e for e in FOUND["episodes"] if not nums or e["num"] in nums]}
    monkeypatch.setattr(fiche_module.yoitsu_gateway, "download_items", download_items)

    started = client.post("/api/device-download/jobs", json={"anime_id": "a-frieren", "season": "saison-1", "episodes": [2]}).json()["jobs"]
    assert [(j["num"], j["source"]) for j in started] == [(2, "voiranime")]
    job_id = started[0]["id"]
    jobs._executor.shutdown(wait=True)
    status = client.get("/api/device-download/jobs", params={"id": job_id}).json()["jobs"][0]
    assert status["status"] == "completed" and status["progress"] == 100.0

    res = client.get(f"/api/device-download/jobs/{job_id}/file")
    assert res.status_code == 200 and len(res.content) == 200
    assert res.headers["content-disposition"] == ('attachment; filename="Frieren - Saison 1 - VOSTFR - ep_2.mp4"; '
                                                  "filename*=UTF-8''Frieren%20-%20Saison%201%20-%20VOSTFR%20-%20ep_2.mp4")
    path = jobs.get(job_id)["item"].target
    assert client.delete(f"/api/device-download/jobs/{job_id}").status_code == 200
    assert not os.path.exists(path) and os.listdir(tmp_path) == []
    assert client.get(f"/api/device-download/jobs/{job_id}/file").status_code == 404


def test_server_downloads_follow_yoitsuwrap_progress(tmp_path, monkeypatch):
    saved = []
    monkeypatch.setattr(download_module, "save_json", lambda path, data, **kw: saved.append(data))
    monkeypatch.setattr(download_module.settings_service, "get_root_folder", lambda: str(tmp_path))
    monkeypatch.setattr(download_module.wrapper_download, "download_season", _fake_season)
    service = download_module.DownloadService.__new__(download_module.DownloadService)
    service.__init__()
    service.tasks = {}

    tasks = service.add_wrapper_season("Re:Zero", "Saison 1", "vf", FOUND["episodes"])
    cancelled = tasks[1]
    service.cancel_task(cancelled.id)
    service._batches.shutdown(wait=True)
    done = tasks[0]
    assert done.status == "completed" and done.progress == 100.0 and done.mode == "wrapper"
    assert done.season == "Saison 1 VF" and done.source == "anime_sama"
    assert done.file_path.replace("\\", "/").endswith("nami/Anime/ReZero/Saison_1/vf/1.mp4")
    assert cancelled.status == "cancelled" and not os.path.exists(cancelled.file_path)
    assert saved and saved[-1][0]["mode"] == "wrapper"

    # The library and the episode list find these files
    lib = cache_service.scan_downloaded_library(str(tmp_path))
    assert [(s["season_name"], [e["num"] for e in s["episodes"]]) for s in lib[0]["seasons"]] == [("Saison 1 VF", ["1"])]
    status = client.get("/api/episodes/download-status", params={"anime_title": "Re:Zero", "season": "Saison 1 VF",
                                                                 "label": "Saison 1", "version": "vf"})
    assert list(status.json()["downloaded_episodes"]) == ["1"]


def test_progress_hooks_reach_the_yt_dlp_yoitsuwrap_creates(tmp_path):
    wrapper_download.install()
    from YoitsuWrap import Episode as episode_module
    item = wrapper_download.Item(title="T", season="S", version="vostfr", num=3, link="", source="", root=str(tmp_path))
    with wrapper_download._hooks_lock:
        wrapper_download._hooks[wrapper_download._target_key(item.target)] = item.hook
    try:
        ydl = episode_module.yt_dlp.YoutubeDL({"outtmpl": item.target})
        assert item.hook in ydl.params["progress_hooks"] and ydl.params["quiet"]
        other = episode_module.yt_dlp.YoutubeDL({"quiet": True})          # the health checks are untouched
        assert not other.params.get("progress_hooks")
    finally:
        wrapper_download._hooks.clear()
    item.cancelled = True
    with pytest.raises(wrapper_download.DownloadCancelled):
        item.hook({"status": "downloading"})


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


def test_search_shows_one_card_per_franchise_like_yoitsuwrap(tmp_path, monkeypatch):
    from backend.yoitsu import gateway as gateway_module
    gw = _make_gateway(tmp_path, monkeypatch, [], HXD_ROWS, [])

    async def as_search(q):
        return []

    async def va_search(q, group=True, cover_wait=None):
        return [{"title": t, "source": "voiranime", "url": u, "cover": ""} for t, u in (
            ("High School DxD", HXD), ("High School DxD New", HXD_NEW), ("High School DxD BorN", HXD_BORN))]

    monkeypatch.setattr(gateway_module.catalog_service, "_search_anime_sama", as_search)
    monkeypatch.setattr(gateway_module.catalog_service, "_search_voiranime", va_search)
    results = asyncio.run(gw.search("high school dxd"))
    assert [r["title"] for r in results] == ["High School DxD"]
    assert set(results[0]["alt_titles"]) == {"High School DxD New", "High School DxD BorN"}

    # The API naming another work (its best match is not among these posts) groups nothing
    other = _make_gateway(tmp_path / "other", monkeypatch, [], [{**HXD_ROWS[0], "base_url": "https://voir-anime.to/anime/x/"}], [])
    other.aliases.union = lambda *a, **k: pytest.fail("nothing to learn")
    asyncio.run(other.group_like_wrapper([Entry("voiranime", HXD, "High School DxD"), Entry("voiranime", HXD_BORN, "Z BorN")]))
