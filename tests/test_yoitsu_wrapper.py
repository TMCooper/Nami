import asyncio
import time
from types import SimpleNamespace

from backend.services.catalog_service import catalog_service
from backend.yoitsu import gateway as gateway_module
from backend.yoitsu import wrapper_store as wrapper_module
from backend.yoitsu.wrapper_store import WrapperStore, link_expiry, snapshot_from_anime, with_wrapper_links

from tests.test_yoitsu_gateway import AS_ROWS, FRIEREN_ENTRIES, VA_ROWS, _make_gateway

LINK = "https://prx-1.vmpx.online/hls2/01/x/master.m3u8?t=abc&s={s}&e=43200"


def _snapshot(valid_for=3600, built_at=None):
    built_at = built_at or time.time()
    return {
        "query": "Frieren", "version": "vostfr", "sources": ["anime_sama"], "built_at": built_at,
        "valid_until": built_at + valid_for, "anime": {"title": "Frieren"},
        "seasons": [{"label": "Saison 1", "key": "saison-1", "episodes": [
            {"num": 1, "link": "https://cdn.test/1/master.m3u8", "source": "anime_sama"},
            {"num": 2, "link": "https://cdn.test/2/master.m3u8", "source": "voiranime"},
            {"num": 3, "link": "https://cdn.test/3/master.m3u8", "source": "anime_sama"},
        ]}],
    }


def _wait(store, key, version="vostfr", timeout=5.0):
    end = time.time() + timeout
    while time.time() < end and store.status(key, version)["state"] in ("queued", "running"):
        time.sleep(0.02)
    return store.status(key, version)


def test_signed_links_expire_with_their_query():
    assert link_expiry(LINK.format(s=1_000_000), built_at=5.0) == 1_000_000 + 43200
    assert link_expiry("https://cdn.test/v.mp4", built_at=100.0) == 100.0 + wrapper_module.DEFAULT_LIFETIME


def test_snapshot_keeps_seasons_episodes_and_the_earliest_expiry():
    def ep(n, s):
        return SimpleNamespace(episode_number=n, link=LINK.format(s=s), source="ANIMESAMA")

    season = SimpleNamespace(get_saison=lambda: "Saison 2", get_episodes=lambda: [ep(2, 2000), ep(1, 1000)])
    anime = SimpleNamespace(get_seasons=lambda: {"2": season}, get_title=lambda: "Frieren", get_cover=lambda: "c",
                            get_link=lambda: "l", get_synopsis=lambda: "s", get_scan=lambda: object())
    snap = snapshot_from_anime(anime, "Frieren", "vostfr", ["anime_sama"], built_at=10.0)
    assert snap["seasons"][0]["key"] == "saison-2"
    assert [e["num"] for e in snap["seasons"][0]["episodes"]] == [1, 2]
    assert snap["seasons"][0]["episodes"][0]["source"] == "anime_sama"
    assert snap["valid_until"] == 1000 + 43200 and snap["anime"]["has_scan"] is True


def test_a_build_runs_once_is_kept_on_disk_and_reused():
    calls = []

    def builder(query, version, allowed, order):
        calls.append((query, version, order))
        time.sleep(0.05)
        return _snapshot()

    store = WrapperStore(builder=builder)
    first = store.ensure("frieren", "vostfr", "Frieren", {"ANIMESAMA": {"frieren"}}, ["ANIMESAMA", "VOIRANIME"])
    store.ensure("frieren", "vostfr", "Frieren", {"ANIMESAMA": {"frieren"}}, ["ANIMESAMA", "VOIRANIME"])
    assert first["state"] in ("queued", "running")
    assert _wait(store, "frieren")["state"] == "ready"
    assert calls == [("Frieren", "vostfr", ["ANIMESAMA", "VOIRANIME"])]

    # Ready: no rebuild; a new process reads the snapshot from disk
    store.ensure("frieren", "vostfr", "Frieren", {}, [])
    assert len(calls) == 1
    reloaded = WrapperStore(builder=builder)
    assert reloaded.status("frieren", "vostfr")["state"] == "ready"
    assert reloaded.get("frieren", "vostfr")["seasons"][0]["episodes"][0]["num"] == 1

    # « Actualiser » rebuilds at once
    store.ensure("frieren", "vostfr", "Frieren", {}, [], force=True)
    _wait(store, "frieren")
    assert len(calls) == 2


def test_expired_links_are_rebuilt_and_failures_wait_before_a_retry():
    calls = []
    store = WrapperStore(builder=lambda *a: calls.append(a) or None)
    store._snapshots[store._id("frieren", "vostfr")] = _snapshot(valid_for=-1)
    assert store.status("frieren", "vostfr")["state"] == "expired"
    store.ensure("frieren", "vostfr", "Frieren", {}, [])
    assert _wait(store, "frieren")["state"] == "expired"   # the failed rebuild keeps the old (expired) snapshot
    assert store._jobs[store._id("frieren", "vostfr")]["state"] == "failed"
    store.ensure("frieren", "vostfr", "Frieren", {}, [])
    assert len(calls) == 1                                   # no retry storm


def test_verified_links_come_first_and_api_players_stay_as_fallbacks():
    episodes = [
        {"num": 1, "title": "Épisode 1", "embed_url": "https://vidmoly.net/e1",
         "players": [{"host": "vidmoly", "embed_url": "https://vidmoly.net/e1"}]},
        {"num": 2, "title": "Sousou no Frieren - 02", "embed_url": "https://voir-anime.to/anime/x/x-02-vostfr/"},
        {"num": 4, "title": "Épisode 4", "embed_url": "https://vidmoly.net/e4"},
    ]
    out = with_wrapper_links(episodes, _snapshot()["seasons"][0])
    assert [e["num"] for e in out] == [1, 2, 3, 4]
    assert out[0]["players"][0] == {"host": "YoitsuWrap", "embed_url": "https://cdn.test/1/master.m3u8", "verified": True}
    assert out[0]["players"][1]["host"] == "vidmoly" and out[0]["embed_url"] == "https://vidmoly.net/e1"
    assert out[1]["players"][1] == {"host": "VoirAnime", "embed_url": "https://voir-anime.to/anime/x/x-02-vostfr/"}
    assert out[2]["verified"] and out[2]["embed_url"] == "https://cdn.test/3/master.m3u8"   # only YoitsuWrap had it
    assert "verified" not in out[3]                                                         # the API's alone
    assert with_wrapper_links(episodes, None) is episodes


def test_episodes_use_a_fresh_build_of_their_own_source(tmp_path, monkeypatch):
    gw = _make_gateway(tmp_path, monkeypatch, AS_ROWS, VA_ROWS, FRIEREN_ENTRIES)
    builds = []
    gw.wrapper = WrapperStore(builder=lambda q, v, allowed, order: builds.append((q, v, allowed, order)) or None)

    async def as_players(url, version, refresh=False):
        return [{"num": 1, "title": "Épisode 1", "embed_url": "https://vidmoly.net/e1",
                 "players": [{"host": "vidmoly", "embed_url": "https://vidmoly.net/e1"}]}]

    async def va_details(url, source, refresh=False, track_recent=True):
        return {"episodes": [{"num": 1, "title": "Sousou no Frieren - 01 VOSTFR", "url": url, "embed_url": url}]}

    monkeypatch.setattr(gateway_module.catalog_service, "fetch_anime_sama_players", as_players)
    monkeypatch.setattr(gateway_module.catalog_service, "get_details", va_details)

    # No build yet: the API players, and the build is started with this entity's own pages only
    first = asyncio.run(gw.episodes("a-frieren", "saison-1", "anime_sama", "vostfr"))
    assert first["episodes"][0]["players"][0]["host"] == "vidmoly"
    assert first["wrapper"]["state"] in ("queued", "running", "failed")
    _wait(gw.wrapper, "frieren")
    query, version, allowed, order = builds[0]
    assert (query, version, order) == ("Frieren", "vostfr", ["ANIMESAMA", "VOIRANIME"])
    assert allowed["ANIMESAMA"] == {"frieren"}
    assert allowed["VOIRANIME"] == {"sousou-no-frieren", "sousou-no-frieren-2", "sousou-no-frieren-vf"}

    # Ready: verified links first on the Anime-Sama variant, never mixed into the VoirAnime one
    gw.wrapper._snapshots[gw.wrapper._id("frieren", "vostfr")] = _snapshot()
    gw.wrapper._jobs.clear()
    ready = asyncio.run(gw.episodes("a-frieren", "saison-1", "anime_sama", "vostfr"))
    assert ready["wrapper"]["state"] == "ready"
    assert ready["episodes"][0]["players"][0]["host"] == "YoitsuWrap"
    va = asyncio.run(gw.episodes("a-frieren", "saison-1", "voiranime", "vostfr"))
    assert all(not e.get("verified") for e in va["episodes"])
    assert gw.wrapper_status("a-frieren")["state"] == "ready"


def test_direct_streams_need_no_resolver():
    res = asyncio.run(catalog_service.resolve_stream("https://cdn.test/hls2/master.m3u8?t=1&s=2&e=3"))
    assert res["stream_url"] == "https://cdn.test/hls2/master.m3u8?t=1&s=2&e=3"
    assert res["stream_type"] == "m3u8" and res["host"] == "cdn.test"
    assert asyncio.run(catalog_service.resolve_stream("https://[bad/x.m3u8"))["stream_url"] is None
