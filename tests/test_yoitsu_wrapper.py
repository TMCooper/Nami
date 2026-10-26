import asyncio
import requests
import time
from types import SimpleNamespace

from backend.services.catalog_service import catalog_service
from backend.yoitsu import gateway as gateway_module
from backend.yoitsu import wrapper_store as wrapper_module
from backend.yoitsu.wrapper_store import WrapperStore, link_expiry, snapshot_from_anime, wrapper_episodes

from tests.test_yoitsu_gateway import AS_ROWS, FRIEREN_ENTRIES, VA_ROWS, _make_gateway

LINK = "https://prx-1.vmpx.online/hls2/01/x/master.m3u8?t=abc&s={s}&e=43200"


def _snapshot(valid_for=3600, built_at=None):
    built_at = built_at or time.time()
    return {
        "format": wrapper_module.SNAPSHOT_FORMAT, "query": "Frieren", "version": "vostfr", "sources": ["anime_sama"], "built_at": built_at,
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


def test_the_fiche_lists_its_episodes_with_their_source_and_api_players_behind():
    episodes = [
        {"num": 1, "title": "Épisode 1", "embed_url": "https://vidmoly.net/e1",
         "players": [{"host": "vidmoly", "embed_url": "https://vidmoly.net/e1"}]},
        {"num": 2, "title": "Sousou no Frieren - 02", "embed_url": "https://voir-anime.to/anime/x/x-02-vostfr/"},
        {"num": 4, "title": "Épisode 4", "embed_url": "https://vidmoly.net/e4"},
    ]
    season = _snapshot()["seasons"][0]
    out = wrapper_episodes(season, episodes, fresh=True, api_source="anime_sama")
    assert [e["num"] for e in out] == [1, 2, 3, 4]
    assert out[0]["players"][0] == {"host": "YoitsuWrap", "embed_url": "https://cdn.test/1/master.m3u8",
                                    "verified": True, "source": "anime_sama"}
    assert out[0]["players"][1]["host"] == "vidmoly" and out[0]["embed_url"] == "https://cdn.test/1/master.m3u8"
    assert out[1]["source"] == "voiranime"
    assert out[1]["players"][1] == {"host": "VoirAnime", "embed_url": "https://voir-anime.to/anime/x/x-02-vostfr/"}
    assert out[2]["verified"] and out[2]["title"] == "Épisode 3"           # only YoitsuWrap had it
    assert out[3]["verified"] is False and out[3]["source"] == "anime_sama"  # YoitsuWrap could not check it

    # Expired links: the API players are tried first, the old link last
    stale = wrapper_episodes(season, episodes, fresh=False, api_source="anime_sama")
    assert stale[0]["players"][0]["host"] == "vidmoly" and stale[0]["players"][-1]["host"] == "YoitsuWrap"
    assert stale[2]["players"][0]["host"] == "YoitsuWrap"                    # nothing else to try


def test_the_page_shows_the_fiche_built_by_yoitsuwrap(tmp_path, monkeypatch):
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

    # First view: the build starts with this entity's own pages only, the page has no fiche to show yet
    first = asyncio.run(gw.fiche("a-frieren"))
    assert first["state"] in ("queued", "running", "failed") and first["fiche"] is None
    _wait(gw.wrapper, "frieren")
    query, version, allowed, order = builds[0]
    assert (query, version, order) == ("Frieren", "vostfr", ["ANIMESAMA", "VOIRANIME"])
    assert allowed["ANIMESAMA"] == {"frieren"}
    assert allowed["VOIRANIME"] == {"sousou-no-frieren", "sousou-no-frieren-2", "sousou-no-frieren-vf"}

    # Ready: one list of seasons, the one YoitsuWrap made (a season only it found included)
    snap = _snapshot()
    snap["anime"].update(cover="", synopsis="Synopsis de YoitsuWrap")
    snap["seasons"].append({"label": "OAV", "key": "oav", "episodes": [{"num": 1, "link": "https://cdn.test/oav.mp4", "source": "voiranime"}]})
    gw.wrapper._snapshots[gw.wrapper._id("frieren", "vostfr")] = snap
    gw.wrapper._jobs.clear()
    ready = asyncio.run(gw.fiche("a-frieren"))
    assert ready["state"] == "ready"
    assert [(s["key"], s["episodes"], s["sources"]) for s in ready["fiche"]["seasons"] if not s.get("is_scans")] == [
        ("saison-1", 3, ["anime_sama", "voiranime"]), ("oav", 1, ["voiranime"])]
    assert any(s.get("is_scans") for s in ready["fiche"]["seasons"])
    assert ready["fiche"]["synopsis"]["text"] == "Synopsis de YoitsuWrap"

    # Its episodes, whatever source the page asked for: each says where it comes from
    eps = asyncio.run(gw.episodes("a-frieren", "saison-1", "voiranime", "vostfr"))
    assert eps["from_wrapper"] and eps["variant"]["source"] == "anime_sama"
    assert [(e["num"], e["source"]) for e in eps["episodes"]] == [(1, "anime_sama"), (2, "voiranime"), (3, "anime_sama")]
    assert eps["episodes"][0]["players"][1]["host"] == "vidmoly"   # the API player behind the verified link

    # A season only YoitsuWrap knows gets history keys of its own
    oav = asyncio.run(gw.episodes("a-frieren", "oav", "", "vostfr"))
    assert oav["variant"]["source"] == "voiranime" and oav["variant"]["history_keys"] == [{"title": "Frieren", "season": "OAV"}]
    assert gw.wrapper_status("a-frieren")["state"] == "ready"


def test_direct_streams_need_no_resolver():
    res = asyncio.run(catalog_service.resolve_stream("https://cdn.test/hls2/master.m3u8?t=1&s=2&e=3"))
    assert res["stream_url"] == "https://cdn.test/hls2/master.m3u8?t=1&s=2&e=3"
    assert res["stream_type"] == "m3u8" and res["host"] == "cdn.test"
    assert asyncio.run(catalog_service.resolve_stream("https://[bad/x.m3u8"))["stream_url"] is None


class _FakeApis:
    """Anime-Sama and VoirAnime APIs as YoitsuWrap sees them, without the network.

    VoirAnime knows High School DxD as six posts; like the real voiranime_API, its getSpecificAnime
    matches labels by substring (« BorN: Yomigaeranai Fushichou » answers the « BorN » post) and its
    getAnimeLink resolves every stream before answering (« Hero » takes too long). Anime-Sama answers
    {"title": None, ...} for a season it does not have.
    """
    VA = "http://va.test/api"
    AS = "http://as.test/api"
    HXD = ["Saison 1", "OAV", "New", "BorN", "BorN: Yomigaeranai Fushichou", "Hero"]

    def __init__(self, as_seasons=(), va_seasons=HXD, slow=("Hero",)):
        self.as_seasons, self.va_seasons, self.slow = list(as_seasons), list(va_seasons), set(slow)

    @staticmethod
    def _slug(label):
        return label.lower().replace(":", "").replace(" ", "-")

    def _va_match(self, label):
        wanted = label.lower().replace(" ", "")
        return next((s for s in self.va_seasons if wanted == s.lower().replace(" ", "")
                     or wanted in s.lower().replace(" ", "") or s.lower().replace(" ", "") in wanted), None)

    def answer(self, url, params):
        api, _, route = url.rpartition("/")
        q, s = params.get("q") or params.get("n"), params.get("s")
        if api == self.VA:
            if q != "High School DxD":
                return []
            if route == "getInfoAnime":
                return [{"base_url": "https://voir-anime.to/anime/high-school-dxd/", "title": "High School DxD", "Saison": label,
                         "url": f"https://voir-anime.to/anime/{self._slug(label)}/", "cover": "", "synopsis": "Issei..."}
                        for label in self.va_seasons]
            match = self._va_match(s)
            if route == "getSpecificAnime":
                return {"title": "High School DxD", "Saison": match, "url": f"https://voir-anime.to/anime/{self._slug(match)}/"}
            if route == "getAnimeLink":
                if match in self.slow:
                    raise requests.ReadTimeout("read timed out")
                return [{"episode": n, "url": f"https://cdn.test/{self._slug(match)}/{n}.mp4"} for n in (1, 2, 3)]
        if api == self.AS:
            if route == "getInfoAnime":
                return [{"base_url": "https://anime-sama.to/catalogue/hxd", "title": "High School DxD", "Saison": label,
                         "url": f"https://anime-sama.to/catalogue/hxd/{self._slug(label)}/vostfr"} for label in self.as_seasons]
            if route == "getSpecificAnime":
                if s in self.as_seasons:
                    return {"title": "High School DxD", "Saison": s, "url": "https://anime-sama.to/catalogue/hxd"}
                return {"title": None, "Saison": None, "url": None}
            if route == "getAnimeLink":
                return [{"episode": n, "url": f"https://as.test/{self._slug(s)}/{n}.m3u8"} for n in (1, 2)] if s in self.as_seasons else []
        return []

    def install(self, monkeypatch, names):
        from urllib.parse import parse_qs, urlsplit
        from YoitsuWrap.Config import Config
        from YoitsuWrap.Episode import Episode

        def fake_request(session, method, url, **kwargs):
            params = dict(kwargs.get("params") or {})
            params.update({k: v[0] for k, v in parse_qs(urlsplit(url).query).items()})
            data = self.answer(url.split("?")[0], params)
            return SimpleNamespace(json=lambda: data, status_code=200)

        monkeypatch.setattr(wrapper_module, "_original_request", fake_request)
        monkeypatch.setattr(Episode, "check_vid_health", staticmethod(lambda link: True))
        links = {"ANIMESAMA": self.AS, "VOIRANIME": self.VA}
        config = {n: Config(BASE_URL="", PORT=0, PATH=".", API_LINK=links[n], SOURCE=n) for n in names}
        monkeypatch.setattr("backend.services.yoitsu_service.yoitsu_service.get_config", lambda: config)


def test_every_season_yoitsuwrap_returns_is_in_the_fiche(tmp_path, monkeypatch):
    _FakeApis().install(monkeypatch, ["ANIMESAMA", "VOIRANIME"])
    store = WrapperStore(builder=wrapper_module.build_with_wrapper)
    allowed = {"ANIMESAMA": set(), "VOIRANIME": {"high-school-dxd"}}
    store.ensure("high school dxd", "vostfr", "High School DxD", allowed, ["VOIRANIME", "ANIMESAMA"])
    assert _wait(store, "high school dxd")["state"] == "ready"
    seasons = store.get("high school dxd", "vostfr")["seasons"]

    assert [(s["label"], len(s["episodes"])) for s in seasons] == [
        ("Saison 1", 3), ("OAV", 3), ("New", 3), ("BorN", 3), ("BorN: Yomigaeranai Fushichou", 3), ("Hero", 0)]
    assert len({s["key"] for s in seasons}) == 6
    assert seasons[4]["same_as"] == "BorN"                     # the API answered the « BorN » post for it
    assert seasons[5]["error"] == "l'API n'a pas répondu à temps" and seasons[5]["api_links"] is None
    assert seasons[2]["api_links"] == 3 and {e["source"] for e in seasons[2]["episodes"]} == {"voiranime"}


def test_a_season_the_first_api_lacks_keeps_its_own_name(tmp_path, monkeypatch):
    # Anime-Sama has « Saison 1 » only: its {"title": None} answer for « New » is taken by YoitsuWrap
    _FakeApis(as_seasons=["Saison 1"], va_seasons=["Saison 1", "New"], slow=()).install(monkeypatch, ["ANIMESAMA", "VOIRANIME"])
    store = WrapperStore(builder=wrapper_module.build_with_wrapper)
    allowed = {"ANIMESAMA": {"hxd"}, "VOIRANIME": {"high-school-dxd"}}
    store.ensure("hxd", "vostfr", "High School DxD", allowed, ["ANIMESAMA", "VOIRANIME"])
    assert _wait(store, "hxd")["state"] == "ready"
    seasons = store.get("hxd", "vostfr")["seasons"]
    assert [s["label"] for s in seasons] == ["Saison 1", "New"]
    assert {e["source"] for e in seasons[0]["episodes"]} == {"anime_sama"}


def test_a_fiche_of_an_older_format_is_shown_then_rebuilt():
    store = WrapperStore(builder=lambda *a: None)
    old = _snapshot()
    del old["format"]
    store._snapshots[store._id("frieren", "vostfr")] = old
    assert store.status("frieren", "vostfr")["state"] == "expired"
    assert store.get("frieren", "vostfr") is old
