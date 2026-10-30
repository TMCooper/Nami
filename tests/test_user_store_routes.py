import asyncio
import copy
import json
import os

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.routers import api as api_module
from backend.services import cache_service as cache_module
from backend.services import history_service as history_module
from backend.services import user_service as user_module
from backend.services import watchlist_service as watchlist_module
from backend.services.cache_service import cache_service
from backend.services.history_service import history_service
from backend.services.user_service import user_service
from backend.services.watchlist_service import watchlist_service
from backend.yoitsu import gateway as gateway_module
from backend.yoitsu.index import Entry
from backend.yoitsu.normalize import slug_of

# No "with TestClient(...)": the lifespan (which launches the scraper APIs) is not started
client = TestClient(app)

# Real store paths, read before any test patches them
REAL_FILES = (history_module.HISTORY_FILE, watchlist_module.WATCHLIST_FILE, user_module.USERS_FILE, cache_module.RECENT_FILE)

SHOW_URL = "https://anime-sama.to/catalogue/zzz-test-show"
SHOW = {"id": "a-zzz-test-show", "title": "Zzz Test Show", "source": "anime_sama", "url": SHOW_URL, "entry_title": "Zzz Test Show"}
DETAILS = {
    "id": "a-zzz-test-show", "title": "Zzz Test Show", "alt_titles": [], "synopsis": None,
    "cover": "/api/img?url=https%3A%2F%2Fanime-sama.to%2Fc.jpg", "cover_fallbacks": [], "banner": None, "trailer": None,
    "color": None, "genres": [], "anilist_id": None, "source": "anime_sama", "url": SHOW_URL,
    "sources": [{"source": "anime_sama", "url": SHOW_URL, "title": "Zzz Test Show"}],
    "seasons": [{"key": "saison-1", "label": "Saison 1", "order": [0, 1, 0], "is_scans": False, "variants": [
        {"source": "anime_sama", "version": "vostfr", "url": f"{SHOW_URL}/saison1/vostfr", "available": True,
         "season_name": "Saison 1", "season_label": "Saison 1", "history_title": "Zzz Test Show",
         "history_titles": ["Zzz Test Show"], "history_keys": [{"title": "Zzz Test Show", "season": "Saison 1"}]},
        {"source": "anime_sama", "version": "vf", "url": f"{SHOW_URL}/saison1/vf", "available": True,
         "season_name": "Saison 1 VF", "season_label": "Saison 1", "history_title": "Zzz Test Show",
         "history_titles": ["Zzz Test Show"], "history_keys": [{"title": "Zzz Test Show", "season": "Saison 1 VF"}]},
    ]}],
}
EPISODES = [{"num": 1, "title": "Épisode 1", "embed_url": "https://vidmoly.net/e1"},
            {"num": 2, "title": "Épisode 2", "embed_url": "https://vidmoly.net/e2"}]


@pytest.fixture
def stores(monkeypatch, tmp_path):
    monkeypatch.setattr(history_module, "HISTORY_FILE", str(tmp_path / "history.json"))
    monkeypatch.setattr(watchlist_module, "WATCHLIST_FILE", str(tmp_path / "watchlist.json"))
    monkeypatch.setattr(history_service, "history", {})
    monkeypatch.setattr(history_service, "_link_tried", {})
    monkeypatch.setattr(history_service, "_dirty", False)
    monkeypatch.setattr(watchlist_service, "items", {})
    # The watchlist only keeps buckets of known profiles (in memory only: users.json is never saved here)
    for uid in ("u1", "u2", "u3", "u4", "u5", "u6"):
        monkeypatch.setitem(user_service.users, uid, {"id": uid, "username": f"Zzz {uid.upper()}", "avatar": "x",
                                                      "password_hash": "", "created_at": 0})
    # TestClient serves each request in a short-lived loop: write at once instead of debouncing
    monkeypatch.setattr(history_service, "_schedule_flush", lambda delay=None: history_service.flush())
    gw = gateway_module.yoitsu_gateway
    monkeypatch.setattr(gw, "_catalog_next", float("inf"))
    monkeypatch.setattr(gw.index, "flush", lambda: None)
    monkeypatch.setattr(gw.index, "catalog_loaded", False)   # no background linking task
    return tmp_path


@pytest.fixture
def real_gateway(stores, monkeypatch):
    """A real YoitsuGateway (temp meta dir, no network, no recents) behind the routes."""
    store = {}
    monkeypatch.setattr(cache_service, "get_anime_details", lambda source, key: store.get((source, key)))
    monkeypatch.setattr(cache_service, "save_anime_details", lambda source, key, content: store.__setitem__((source, key), content))
    monkeypatch.setattr(cache_service, "add_recent_anime", lambda uid, anime: None)
    gw = gateway_module.YoitsuGateway(meta_dir=str(stores / "meta"))
    gw.anilist.enabled = False
    gw._catalog_next = float("inf")
    monkeypatch.setattr(gw, "_schedule_flush", lambda: None)

    async def no_info(source, title):
        return []

    async def page(url, refresh=False):
        return {"slug": slug_of(url), "title": "Shaman King", "url": url, "cover": "", "synopsis": "", "alt_titles": [],
                "genres": [], "seasons": [{"label": "Saison 1", "url": f"{url}/saison1/vostfr"}]}

    async def lecteurs(url):
        return None

    async def as_players(url, version, refresh=False):
        return [{"num": n, "title": f"Épisode {n}", "embed_url": f"https://vidmoly.net/{slug_of(url.split('/saison')[0])}/{n}",
                 "players": []} for n in (1, 2, 3)]

    async def va_details(url, source, refresh=False, track_recent=True):
        return {"episodes": [{"num": n, "title": f"{slug_of(url)} {n}", "url": f"{url}ep-{n}/", "embed_url": f"{url}ep-{n}/"}
                             for n in (1, 2, 3)]}

    async def no_covers(items, limit=15, wait_seconds=0):
        return None

    catalog = gateway_module.catalog_service
    monkeypatch.setattr(gw, "get_info", no_info)
    monkeypatch.setattr(catalog, "fetch_anime_sama_page", page)
    monkeypatch.setattr(catalog, "_anime_sama_lecteurs", lecteurs)
    monkeypatch.setattr(catalog, "fetch_anime_sama_players", as_players)
    monkeypatch.setattr(catalog, "get_details", va_details)
    monkeypatch.setattr(catalog, "_fill_missing_voiranime_covers", no_covers)
    monkeypatch.setattr(api_module, "yoitsu_gateway", gw)
    return gw


def _progress(uid, season="Saison 1", **extra):
    body = {"anime_title": "Zzz Test Show", "season": season, "ep_id": "2", "position_sec": 300, "duration_sec": 1400,
            "embed_url": "https://vidmoly.net/e2", **extra}
    resp = client.post("/api/history/progress", json=body, headers={"X-User-ID": uid})
    assert resp.status_code == 200
    return resp


def test_progress_accepts_null_duration_and_position(stores):
    resp = client.post("/api/history/progress", json={"anime_title": "Zzz Test Show", "season": "Saison 1",
                                                       "ep_id": "1", "position_sec": None, "duration_sec": None},
                       headers={"X-User-ID": "u1"})
    assert resp.status_code == 200
    assert (resp.json()["position_sec"], resp.json()["duration_sec"]) == (0, 0)
    assert "u1" in json.loads((stores / "history.json").read_text(encoding="utf-8"))


def test_progress_context_then_continue(stores):
    _progress("u1", "Saison 1", position_sec=600, anime=SHOW, season_key="saison-1", source="anime_sama", version="vostfr",
              ep_title="Épisode 2", next_ep={"ep_id": "3", "title": "Épisode 3"})
    data = client.get("/api/history/continue", headers={"X-User-ID": "u1"}).json()
    assert data["total"] == 1
    [item] = data["results"]
    assert item["key"] == "a-zzz-test-show" and item["anime"]["id"] == "a-zzz-test-show"
    assert (item["season_key"], item["source"], item["version"]) == ("saison-1", "anime_sama", "vostfr")
    assert item["remaining_sec"] == 800 and item["episode_title"] == "Épisode 2"
    assert item["anime_title"] == "Zzz Test Show" and item["embed_url"] == "https://vidmoly.net/e2"

    # An entry url that is not a source page is blanked; the id is kept
    _progress("u2", anime={**SHOW, "url": "https://evil.test/catalogue/zzz-test-show"})
    ref = history_service.history["u2"]["Zzz Test Show"]["anime"]
    assert (ref["id"], ref["source"], ref["url"], ref["entry_title"]) == ("a-zzz-test-show", "", "", "")
    assert client.get("/api/history", headers={"X-User-ID": "u2"}).json()["Zzz Test Show"]["anime"]["url"] == ""

    assert client.get("/api/history/continue", params={"limit": 0}).status_code == 422
    assert client.get("/api/history/continue", params={"limit": 1}, headers={"X-User-ID": "u1"}).json()["total"] == 1


def test_resume_route(stores, monkeypatch):
    gw = gateway_module.yoitsu_gateway
    details_calls = []

    async def live_id(ref):
        return {"a-zzz-old-show": "a-zzz-test-show"}.get(ref["id"], ref["id"])

    async def episodes(eid, season, source="", version="vostfr", refresh=False):
        if season != "saison-1":
            return None
        # Only Anime-Sama serves this season: a VoirAnime mapping falls back to it
        variant = {"source": "anime_sama", "version": version, "url": f"{SHOW_URL}/saison1/{version}", "available": True,
                   "season_name": "Saison 1", "history_keys": [{"title": "Zzz Test Show", "season": "Saison 1"}]}
        return {"season": {"key": "saison-1", "label": "Saison 1"}, "variant": variant, "is_scans": False,
                "episodes": EPISODES, "anime_id": eid}

    async def details(eid, refresh=False, user_id="default", track_recent=True):
        details_calls.append((eid, user_id, track_recent))
        return copy.deepcopy(DETAILS)

    monkeypatch.setattr(gw, "live_id", live_id)
    monkeypatch.setattr(gw, "episodes", episodes)
    monkeypatch.setattr(gw, "details", details)
    recents = copy.deepcopy(cache_service.recent_data)

    def resume(uid, season, title="Zzz Test Show"):
        return client.get("/api/history/resume", params={"anime_title": title, "season": season}, headers={"X-User-ID": uid})

    _progress("u1", anime=SHOW, season_key="saison-1", source="anime_sama", version="vostfr")
    data = resume("u1", "Saison 1").json()
    assert data["exact"] is True and data["total"] == 2 and data["episodes"] == EPISODES
    assert data["anime_id"] == "a-zzz-test-show" and data["anime"]["id"] == "a-zzz-test-show"
    assert data["season"] == {"key": "saison-1", "label": "Saison 1"}
    assert details_calls == []

    _progress("u2", anime=SHOW, season_key="saison-1", source="voiranime", version="vostfr")
    data = resume("u2", "Saison 1").json()
    assert data["exact"] is False and data["variant"]["source"] == "anime_sama"

    _progress("u3")   # unlinked
    for uid, title in (("u1", "Zzz Unknown Show"), ("u3", "Zzz Test Show")):
        resp = resume(uid, "Saison 1", title)
        assert resp.status_code == 404 and resp.json() == {"detail": "Reprise introuvable."}

    # No mapping for that season: one details call, without recents
    _progress("u4", "Saison 1 VF", anime=SHOW)
    data = resume("u4", "Saison 1 VF").json()
    assert data["exact"] is True and data["variant"]["version"] == "vf"
    assert details_calls == [("a-zzz-test-show", "u4", False)]
    assert history_service.history["u4"]["Zzz Test Show"]["seasons"]["Saison 1 VF"]["by"] == "details"

    # The stored season key vanished: the mapping is refreshed once
    _progress("u5", anime=SHOW, season_key="saison-9", source="anime_sama", version="vostfr")
    data = resume("u5", "Saison 1").json()
    assert data["exact"] is True and data["season"]["key"] == "saison-1"
    assert details_calls[-1] == ("a-zzz-test-show", "u5", False) and len(details_calls) == 2

    # A dead id resolved through its source entry is healed on the record
    _progress("u6", anime={**SHOW, "id": "a-zzz-old-show"}, season_key="saison-1", source="anime_sama", version="vostfr")
    data = resume("u6", "Saison 1").json()
    assert data["anime"]["id"] == "a-zzz-test-show"
    assert history_service.history["u6"]["Zzz Test Show"]["anime"]["id"] == "a-zzz-test-show"
    assert cache_service.recent_data == recents


def test_resume_after_an_id_change_never_reuses_the_old_season_key(real_gateway):
    gw = real_gateway
    mp, mp2 = "https://voir-anime.to/anime/mob-psycho-100/", "https://voir-anime.to/anime/mob-psycho-100-ii/"
    entries = [Entry("voiranime", mp, "Mob Psycho 100"), Entry("voiranime", mp2, "Mob Psycho 100 II")]
    gw.index.remember(entries)
    # Before the catalogue loads, the II post is its own entity with a single season
    details = asyncio.run(gw.details("a-mob-psycho-100-ii", track_recent=False))
    assert details["id"] == "a-mob-psycho-100-ii" and [s["key"] for s in details["seasons"]] == ["saison-1"]
    _progress("u1", anime_title="Mob Psycho 100 Ii", ep_id="3", embed_url=f"{mp2}ep-3/", anime=gw.anime_ref(details),
              season_key="saison-1", source="voiranime", version="vostfr")

    # Sibling evidence: the II post joins 'Mob Psycho 100' as its season 2, where 'saison-1' is season 1
    gw.index.set_catalog(entries)
    resp = client.get("/api/history/resume", params={"anime_title": "Mob Psycho 100 Ii", "season": "Saison 1"},
                      headers={"X-User-ID": "u1"})
    assert resp.status_code == 200
    data = resp.json()
    assert (data["anime_id"], data["season"]["key"], data["exact"]) == ("a-mob-psycho-100", "saison-2", True)
    assert [ep["title"] for ep in data["episodes"]] == ["mob-psycho-100-ii 1", "mob-psycho-100-ii 2", "mob-psycho-100-ii 3"]
    record = history_service.history["u1"]["Mob Psycho 100 Ii"]
    assert record["anime"]["id"] == "a-mob-psycho-100"
    assert record["seasons"]["Saison 1"] == {"key": "saison-2", "source": "voiranime", "version": "vostfr", "by": "details"}


def test_resume_from_another_entity_is_never_exact_with_a_stale_key(stores, monkeypatch):
    gw = gateway_module.yoitsu_gateway
    asked = []

    async def live_id(ref):
        return ref["id"]

    async def episodes(eid, season, source="", version="vostfr", refresh=False):
        asked.append((eid, season))
        variant = {"source": "anime_sama", "version": version, "url": f"{SHOW_URL}/saison1/{version}", "available": True,
                   "season_name": "Saison 1", "history_keys": []}
        # An alias renamed the entity while its details were built: the answer names another id
        return {"season": {"key": season, "label": "Saison 1"}, "variant": variant, "is_scans": False,
                "episodes": EPISODES, "anime_id": "a-zzz-renamed"}

    async def details(eid, refresh=False, user_id="default", track_recent=True):
        return None   # the mapping cannot be rebuilt

    monkeypatch.setattr(gw, "live_id", live_id)
    monkeypatch.setattr(gw, "episodes", episodes)
    monkeypatch.setattr(gw, "details", details)
    _progress("u1", anime=SHOW, season_key="saison-1", source="anime_sama", version="vostfr")
    data = client.get("/api/history/resume", params={"anime_title": "Zzz Test Show", "season": "Saison 1"},
                      headers={"X-User-ID": "u1"}).json()
    assert data["exact"] is False and asked == [("a-zzz-test-show", "saison-1")]
    record = history_service.history["u1"]["Zzz Test Show"]
    assert record["anime"]["id"] == "a-zzz-renamed" and record["seasons"] == {}


def test_a_homonymous_page_taking_the_id_never_rewrites_the_saved_work(real_gateway):
    gw = real_gateway
    sk21, sk = "https://anime-sama.to/catalogue/shaman-king-2021", "https://anime-sama.to/catalogue/shaman-king"
    cover21 = "https://raw.githubusercontent.com/Anime-Sama/IMG/img/contenu/shaman-king-2021.jpg"
    gw.index.remember([Entry("anime_sama", sk21, "Shaman King")])
    assert asyncio.run(gw.lookup("anime_sama", sk21, "Shaman King"))["id"] == "a-shaman-king"
    ref = {"id": "a-shaman-king", "title": "Shaman King", "source": "anime_sama", "url": sk21, "entry_title": "Shaman King"}
    _progress("u1", anime_title="Shaman King", anime=ref, season_key="saison-1", source="anime_sama", version="vostfr",
              embed_url="https://vidmoly.net/shaman-king-2021/2")
    assert client.post("/api/watchlist", json={"anime": {**ref, "cover": cover21}}, headers={"X-User-ID": "u1"}).status_code == 200
    saved = dict(watchlist_service.items["u1"][0])

    # The 2001 page (shorter slug) becomes known and takes the plain key: the saved id opens its details
    gw.index.remember([Entry("anime_sama", sk, "Shaman King")])
    resp = client.get("/api/anime/a-shaman-king", headers={"X-User-ID": "u1"})
    assert resp.status_code == 200 and resp.json()["url"] == sk
    record = history_service.history["u1"]["Shaman King"]
    assert (record["anime"]["url"], record["seasons"]["Saison 1"]["by"]) == (sk21, "write")
    assert watchlist_service.items["u1"][0] == saved

    # Resume follows the stored page, not the id
    data = client.get("/api/history/resume", params={"anime_title": "Shaman King", "season": "Saison 1"},
                      headers={"X-User-ID": "u1"}).json()
    assert (data["anime_id"], data["exact"]) == ("a-shaman-king-shaman-king-2021", True)
    assert all("/shaman-king-2021/" in ep["embed_url"] for ep in data["episodes"])
    assert (record["anime"]["id"], record["anime"]["url"]) == ("a-shaman-king-shaman-king-2021", sk21)


def test_details_route_links_only_the_requesting_profile(stores, monkeypatch):
    gw = gateway_module.yoitsu_gateway

    async def details(eid, refresh=False, user_id="default", track_recent=True):
        return copy.deepcopy(DETAILS) if eid == "a-zzz-test-show" else None

    monkeypatch.setattr(gw, "details", details)
    for uid in ("u1", "u2"):
        history_service.save_progress(uid, "Zzz Test Show", "Saison 1 VF", "1", 300, 1400)
    watchlist_service.add("u1", {**SHOW, "title": "Zzz Old Name"})

    resp = client.get("/api/anime/a-zzz-test-show", headers={"X-User-ID": "u1"})
    assert resp.status_code == 200 and resp.json() == DETAILS
    record = history_service.history["u1"]["Zzz Test Show"]
    assert record["anime"]["id"] == "a-zzz-test-show" and record["anime"]["by"] == "details"
    assert record["seasons"]["Saison 1 VF"] == {"key": "saison-1", "source": "anime_sama", "version": "vf", "by": "details"}
    assert "anime" not in history_service.history["u2"]["Zzz Test Show"]
    assert watchlist_service.items["u1"][0]["title"] == "Zzz Test Show"

    resp = client.get("/api/anime/a-zzz-missing", headers={"X-User-ID": "u1"})
    assert resp.status_code == 404 and resp.json() == {"detail": "Anime introuvable."}


def test_watchlist_routes(stores, monkeypatch):
    gw = gateway_module.yoitsu_gateway
    lookups = []

    async def lookup(source, url, title):
        lookups.append((source, url, title))
        return {"id": "a-zzz-test-show", "title": title, "source": source, "url": url}

    monkeypatch.setattr(gw, "lookup", lookup)
    anime = {"title": "Zzz Test Show", "source": "anime_sama", "url": SHOW_URL,
             "cover": "/api/img?url=https%3A%2F%2Fanime-sama.to%2Fc.jpg",
             "sources": [{"source": "anime_sama", "url": SHOW_URL, "title": "Zzz Test Show"},
                         {"source": "voiranime", "url": "https://evil.test/anime/x/", "title": "X"}]}

    for bad in ({**anime, "url": "https://evil.test/catalogue/x"}, {**anime, "title": "  "}, {**anime, "source": "other"}):
        resp = client.post("/api/watchlist", json={"anime": bad}, headers={"X-User-ID": "u1"})
        assert resp.status_code == 400 and resp.json() == {"detail": "Anime invalide."}

    resp = client.post("/api/watchlist", json={"anime": anime}, headers={"X-User-ID": "u1"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1 and data["results"][0]["id"] == "a-zzz-test-show"
    assert lookups == [("anime_sama", SHOW_URL, "Zzz Test Show")]
    assert data["results"][0]["cover"] == "/api/img?url=https%3A%2F%2Fanime-sama.to%2Fc.jpg"
    assert len(data["results"][0]["sources"]) == 1   # the invalid secondary entry is dropped
    assert watchlist_service.items["u1"][0]["cover"] == "https://anime-sama.to/c.jpg"

    assert client.get("/api/watchlist", headers={"X-User-ID": "u1"}).json()["total"] == 1
    assert client.get("/api/watchlist").json() == {"total": 0, "results": []}
    assert client.post("/api/watchlist", json={"anime": {**anime, "id": "a-zzz-test-show"}}).json()["total"] == 1
    assert len(lookups) == 1
    assert client.get("/api/watchlist").json()["total"] == 1   # the signed-in administrator's

    assert client.delete("/api/watchlist", headers={"X-User-ID": "u1"}).status_code == 400
    resp = client.delete("/api/watchlist", params={"source": "anime_sama", "url": SHOW_URL}, headers={"X-User-ID": "u1"})
    assert resp.status_code == 200 and resp.json() == {"total": 0, "results": []}
    assert client.get("/api/watchlist").json()["total"] == 1
    assert client.delete("/api/watchlist", params={"id": "a-zzz-test-show"}).json()["total"] == 0
    assert json.loads((stores / "watchlist.json").read_text(encoding="utf-8")) == {"u1": [], "test_admin": []}


def test_watchlist_only_writes_buckets_of_signed_in_accounts(stores):
    # An unknown account has no session: nothing is written
    resp = client.post("/api/watchlist", json={"anime": SHOW}, headers={"X-User-ID": "user_zzz_unknown"})
    assert resp.status_code == 401
    assert watchlist_service.items == {} and not (stores / "watchlist.json").exists()
    # A body naming another account is ignored: the item goes to the signed-in one
    assert client.post("/api/watchlist", json={"anime": SHOW, "user_id": "u2"}, headers={"X-User-ID": "u1"}).status_code == 200
    assert client.post("/api/watchlist", json={"anime": SHOW}).status_code == 200   # the test administrator
    assert set(watchlist_service.items) == {"test_admin", "u1"}


def test_malformed_urls_never_make_a_route_fail(stores):
    bad = "https://[bad"
    h = {"X-User-ID": "u1"}
    _progress("u1", anime={"id": "a-zzz-test-show", "title": "Zzz Test Show", "source": "anime_sama", "url": "https://[x",
                           "banner": bad}, cover=bad, embed_url=bad)
    record = history_service.history["u1"]["Zzz Test Show"]
    assert record["cover"] == "" and record["anime"]["banner"] is None and record["anime"]["url"] == ""
    assert client.get("/api/history", headers=h).status_code == 200
    assert client.get("/api/history/continue", headers=h).status_code == 200

    anime = {**SHOW, "cover": bad, "banner": bad, "cover_fallbacks": [bad],
             "sources": [{"source": "anime_sama", "url": 7}, {"source": 7, "url": SHOW_URL}, {"source": "anime_sama", "url": bad}]}
    assert client.post("/api/watchlist", json={"anime": anime}, headers=h).status_code == 200
    [item] = watchlist_service.items["u1"]
    assert (item["cover"], item["cover_fallbacks"], item["banner"], item["sources"]) == ("", [], None, [])
    assert client.get("/api/watchlist", headers=h).status_code == 200
    resp = client.post("/api/watchlist", json={"anime": {**SHOW, "url": "https://[x"}}, headers=h)
    assert resp.status_code == 400 and resp.json() == {"detail": "Anime invalide."}
    assert client.delete("/api/watchlist", params={"source": "anime_sama", "url": "https://[x"}, headers=h).status_code == 200
    assert client.get("/api/anime/lookup", params={"source": "anime_sama", "url": bad, "title": "X"}).status_code == 400
    assert client.get("/api/episode/players", params={"url": bad}).status_code == 400

    # Values an older build stored are read as missing
    item["cover"], item["banner"] = bad, bad
    record["cover"] = bad
    assert client.get("/api/watchlist", headers=h).json()["results"][0]["cover"] == ""
    assert client.get("/api/history", headers=h).json()["Zzz Test Show"]["cover"] == ""


def test_delete_user_purges_history_watchlist_and_recents(stores, monkeypatch):
    monkeypatch.setattr(user_module, "USERS_FILE", str(stores / "users.json"))
    monkeypatch.setattr(cache_module, "RECENT_FILE", str(stores / "recent.json"))
    uid = "user_0000test"
    monkeypatch.setitem(user_service.users, uid, {"id": uid, "username": "Zzz", "avatar": "x", "password_hash": "",
                                                  "created_at": 0})
    recent = {"title": "Zzz Test Show", "url": SHOW_URL, "source": "anime_sama", "cover": "", "viewed_at": 1.0}
    monkeypatch.setattr(cache_service, "recent_data", {uid: [recent], "default": [recent]})
    for owner in (uid, "default"):
        history_service.save_progress(owner, "Zzz Test Show", "Saison 1", "1", 300, 1400)
        watchlist_service.add(owner, SHOW)

    resp = client.delete(f"/api/admin/users/{uid}")
    assert resp.status_code == 200
    assert uid not in history_service.history and uid not in watchlist_service.items and uid not in cache_service.recent_data
    for name in ("history.json", "watchlist.json", "recent.json"):
        stored = json.loads((stores / name).read_text(encoding="utf-8"))
        assert uid not in stored and "default" in stored
    assert uid not in json.loads((stores / "users.json").read_text(encoding="utf-8"))
    assert client.delete(f"/api/admin/users/{uid}").status_code == 404


def test_nothing_is_written_outside_tmp(stores):
    def snapshot():
        return {p: os.path.getmtime(p) if os.path.exists(p) else None for p in REAL_FILES}

    before = snapshot()
    _progress("u1", anime=SHOW, season_key="saison-1", source="anime_sama", version="vostfr")
    client.post("/api/watchlist", json={"anime": SHOW}, headers={"X-User-ID": "u1"})
    client.delete("/api/history/item", params={"anime_title": "Zzz Test Show", "ep_key": "Saison 1:2"}, headers={"X-User-ID": "u1"})

    assert history_module.HISTORY_FILE == str(stores / "history.json")
    assert watchlist_module.WATCHLIST_FILE == str(stores / "watchlist.json")
    assert (stores / "history.json").exists() and (stores / "watchlist.json").exists()
    assert all(not p.startswith(str(stores)) for p in REAL_FILES)
    assert snapshot() == before
