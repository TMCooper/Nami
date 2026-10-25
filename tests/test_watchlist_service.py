import json
import os
import time
from urllib.parse import quote

import pytest

from backend.services import watchlist_service as watchlist_module
from backend.services.watchlist_service import WatchlistService

AS_URL = "https://anime-sama.to/catalogue/frieren"
VA_URL = "https://voir-anime.to/anime/sousou-no-frieren/"
VA_S2 = "https://voir-anime.to/anime/sousou-no-frieren-2/"
COVER = "https://raw.githubusercontent.com/Anime-Sama/IMG/img/contenu/frieren.jpg"
VA_COVER = "https://voir-anime.to/wp-content/uploads/f.jpg"
BANNER = "https://s4.anilist.co/file/anilistcdn/media/anime/banner/154587.jpg"
FRIEREN = {
    "id": "a-frieren", "title": "Frieren", "alt_titles": ["Sousou no Frieren", "Frieren", "A", "B", "C", "D", "E"],
    "cover": COVER, "cover_fallbacks": ["/api/img?url=" + quote(VA_COVER, safe=""), "data:image/svg+xml,x",
                                        "https://via.placeholder.com/300x450"],
    "banner": "/api/img?url=" + quote(BANNER, safe=""), "trailer": {"site": "youtube", "id": "qgQkRsJWW3I"},
    "source": "anime_sama", "url": AS_URL, "entry_title": "Frieren",
    "sources": [{"source": "anime_sama", "url": AS_URL, "title": "Frieren"},
                {"source": "voiranime", "url": VA_URL, "title": "Sousou no Frieren"}],
}
BOCCHI = {"id": "a-bocchi-the-rock", "title": "Bocchi the Rock!", "source": "voiranime",
          "url": "https://voir-anime.to/anime/bocchi-the-rock/", "cover": ""}


@pytest.fixture
def service(monkeypatch, tmp_path):
    monkeypatch.setattr(watchlist_module, "WATCHLIST_FILE", str(tmp_path / "watchlist.json"))
    return WatchlistService()


def _stored():
    with open(watchlist_module.WATCHLIST_FILE, encoding="utf-8") as f:
        return json.load(f)


def test_add_stores_raw_covers_and_returns_client_items(service):
    assert service.add("u1", FRIEREN)
    [item] = _stored()["u1"]
    assert item["cover"] == COVER and item["cover_fallbacks"] == [VA_COVER]   # raw, placeholders dropped
    assert item["banner"] == BANNER and item["trailer"] == {"site": "youtube", "id": "qgQkRsJWW3I"}
    assert item["alt_titles"] == ["Sousou no Frieren", "A", "B", "C", "D"]
    assert item["entry_title"] == "Frieren" and len(item["sources"]) == 2 and item["added_at"] > 0

    many = {**FRIEREN, "id": "a-frieren-movie", "url": "https://anime-sama.to/catalogue/frieren-movie",
            "cover_fallbacks": [f"https://example.com/c{n}.jpg" for n in range(9)],
            "sources": [{"source": "anime_sama", "url": f"https://anime-sama.to/catalogue/s{n}"} for n in range(6)]}
    assert service.add("u1", many)
    movie = next(i for i in service.items["u1"] if i["id"] == "a-frieren-movie")
    assert len(movie["cover_fallbacks"]) == 4 and len(movie["sources"]) == 4

    items = service.get_items_for_client("u1", canonical=lambda eid: {"a-frieren": "a-frieren-new"}.get(eid, eid))
    frieren = next(i for i in items if i["title"] == "Frieren" and i["url"] == AS_URL)
    assert frieren["id"] == "a-frieren-new"
    assert frieren["cover"] == COVER                                       # public CDN: loaded directly
    assert frieren["cover_fallbacks"] == ["/api/img?url=" + quote(VA_COVER, safe="")]
    assert frieren["banner"] == "/api/img?url=" + quote(BANNER, safe="")
    assert frieren["wide_images"] == [frieren["banner"], "/api/img?url=" + quote("https://i.ytimg.com/vi/qgQkRsJWW3I/hqdefault.jpg", safe="")]
    assert {"id", "title", "alt_titles", "cover", "cover_fallbacks", "source", "url", "sources"} <= set(frieren)

    assert not service.add("u1", {**FRIEREN, "id": ""})
    assert not service.add("u1", {**FRIEREN, "id": "frieren"})
    assert not service.add("u1", {**FRIEREN, "title": "  "})
    assert not service.add("u1", {**FRIEREN, "url": ""})


def test_readding_under_a_new_id_updates_in_place(service):
    service.add("u1", FRIEREN, added_at=1000.0)
    service.add("u1", {**FRIEREN, "id": "a-frieren-2", "title": "Frieren 2"})   # same primary entry
    [item] = service.items["u1"]
    assert (item["id"], item["title"], item["added_at"]) == ("a-frieren-2", "Frieren 2", 1000.0)

    canonical = lambda eid: "a-frieren" if eid in ("a-frieren-2", "a-sousou-no-frieren") else eid
    service.add("u1", {**FRIEREN, "id": "a-sousou-no-frieren", "source": "voiranime", "url": VA_URL, "sources": [],
                       "banner": None, "trailer": None}, canonical=canonical)
    [item] = service.items["u1"]
    assert (item["id"], item["url"], item["added_at"]) == ("a-sousou-no-frieren", VA_URL, 1000.0)
    assert item["banner"] == BANNER and item["trailer"], "an empty banner never erases the stored one"


def test_secondary_source_overlap_never_merges_two_animes(service):
    service.add("u1", FRIEREN)
    movie_url = "https://anime-sama.to/catalogue/frieren-movie"
    service.add("u1", {"id": "a-frieren-movie", "title": "Frieren Movie", "source": "anime_sama", "url": movie_url,
                       "sources": [{"source": "anime_sama", "url": movie_url, "title": "Frieren Movie"},
                                   {"source": "voiranime", "url": VA_URL, "title": "Sousou no Frieren"}]})
    assert len(service.items["u1"]) == 2
    assert len(service.get_items_for_client("u1")) == 2
    assert service.remove("u1", source="voiranime", url=VA_URL) is False


def test_remove_by_stale_id_or_by_primary_entry(service):
    kimetsu = "https://anime-sama.to/catalogue/kimetsu-no-yaiba"
    service.add("u1", {"id": "a-kimetsu-no-yaiba", "title": "Kimetsu no Yaiba", "source": "anime_sama", "url": kimetsu})
    canonical = lambda eid: {"a-kimetsu-no-yaiba": "a-demon-slayer"}.get(eid, eid)
    assert service.remove("u1", anime_id="a-demon-slayer", canonical=canonical)
    assert service.items["u1"] == []

    service.add("u1", FRIEREN)
    assert not service.remove("u1", anime_id="a-unknown")
    assert service.remove("u1", source="anime_sama", url=AS_URL + "/")   # same slug
    assert service.items["u1"] == [] and _stored()["u1"] == []
    assert not service.remove("nobody", anime_id="a-frieren")


def test_reads_never_write_and_collapse_duplicates_in_the_response_only(service):
    path = watchlist_module.WATCHLIST_FILE
    service.add("u1", FRIEREN, added_at=100.0)
    service.add("u1", {**FRIEREN, "id": "a-sousou-no-frieren", "source": "voiranime", "url": VA_URL}, added_at=200.0)
    assert len(service.items["u1"]) == 2   # saved before the alias was learned
    with open(path, encoding="utf-8") as f:
        before = (os.path.getmtime(path), f.read())

    canonical = lambda eid: "a-frieren" if eid == "a-sousou-no-frieren" else eid
    items = service.get_items_for_client("u1", canonical=canonical)
    assert len(items) == 1 and items[0]["url"] == VA_URL and items[0]["id"] == "a-frieren"   # newest kept
    assert len(service.get_items_for_client("u1")) == 2
    assert service.get_items_for_client("nobody") == []

    assert len(service.items["u1"]) == 2
    with open(path, encoding="utf-8") as f:
        assert (os.path.getmtime(path), f.read()) == before
    assert len(WatchlistService().items["u1"]) == 2


def test_refresh_heals_only_the_matching_item_and_skips_unchanged_saves(service, monkeypatch):
    service.add("u1", {**FRIEREN, "id": "a-sousou-no-frieren", "title": "Sousou no Frieren", "banner": None, "trailer": None},
                added_at=100.0)
    service.add("u1", BOCCHI, added_at=50.0)
    bocchi = dict(service.items["u1"][1])
    details = {
        "id": "a-frieren", "title": "Frieren", "alt_titles": ["Sousou no Frieren"], "synopsis": None,
        "cover": "/api/img?url=" + quote(VA_COVER, safe=""), "cover_fallbacks": [], "banner": "/api/img?url=" + quote(BANNER, safe=""),
        "trailer": None, "source": "anime_sama", "url": AS_URL, "seasons": [],
        "sources": [{"source": "anime_sama", "url": AS_URL, "title": "Frieren"}],
    }
    saves = []
    monkeypatch.setattr(service, "_save", lambda: saves.append(1))

    assert service.refresh("u1", details)
    frieren, other = service.items["u1"]
    assert (frieren["id"], frieren["title"], frieren["cover"], frieren["banner"]) == ("a-frieren", "Frieren", VA_COVER, BANNER)
    assert frieren["added_at"] == 100.0 and frieren["entry_title"] == "Frieren" and len(frieren["sources"]) == 1
    assert other == bocchi
    assert saves == [1]

    assert not service.refresh("u1", details)
    assert not service.refresh("u1", {**details, "banner": None}), "a details view without banner keeps the stored one"
    assert not service.refresh("u2", details)
    assert saves == [1]


def test_refresh_never_turns_a_saved_item_into_another_work_or_erases_its_cover(service):
    sk21, sk = "https://anime-sama.to/catalogue/shaman-king-2021", "https://anime-sama.to/catalogue/shaman-king"
    cover21 = "https://raw.githubusercontent.com/Anime-Sama/IMG/img/contenu/shaman-king-2021.jpg"
    service.add("u1", {"id": "a-shaman-king", "title": "Shaman King", "source": "anime_sama", "url": sk21, "cover": cover21})
    saved = dict(service.items["u1"][0])
    # The 2001 page took the plain key: the saved id now opens its details
    details = {"id": "a-shaman-king", "title": "Shaman King", "source": "anime_sama", "url": sk,
               "cover": "https://raw.githubusercontent.com/Anime-Sama/IMG/img/contenu/shaman-king.jpg",
               "banner": "/api/img?url=" + quote(BANNER, safe=""), "trailer": {"site": "youtube", "id": "qgQkRsJWW3I"},
               "sources": [{"source": "anime_sama", "url": sk, "title": "Shaman King"}]}
    assert not service.refresh("u1", details)
    assert not service.refresh("u1", details, idents={"anime_sama:shaman-king"})
    assert service.items["u1"][0] == saved

    # Its own entity's details heal it; a details build without cover keeps the saved one
    own = {**details, "id": "a-shaman-king-shaman-king-2021", "url": sk21, "cover": "",
           "sources": [{"source": "anime_sama", "url": sk21, "title": "Shaman King"}]}
    assert service.refresh("u1", own)
    item = service.items["u1"][0]
    assert (item["id"], item["url"], item["banner"], item["cover"]) == ("a-shaman-king-shaman-king-2021", sk21, BANNER, cover21)

    # A sequel post is a member of the entity, not a listed source: the route's idents carry every member
    service.add("u2", {"id": "a-frieren", "title": "Sousou no Frieren 2", "source": "voiranime", "url": VA_S2})
    frieren = {**FRIEREN, "cover": COVER}
    assert not service.refresh("u2", frieren)
    assert service.refresh("u2", frieren, idents={"anime_sama:frieren", "voiranime:sousou-no-frieren",
                                                   "voiranime:sousou-no-frieren-2"})
    assert service.items["u2"][0]["url"] == AS_URL and service.items["u2"][0]["cover"] == COVER


def test_snapshot_drops_oversized_images_and_cuts_list_inputs(service):
    long_cover = "https://example.com/" + "c" * 600 + ".jpg"
    assert service.add("u1", {**FRIEREN, "cover": long_cover, "banner": long_cover,
                              "cover_fallbacks": [long_cover, "/api/img?url=" + quote(VA_COVER, safe="")],
                              "alt_titles": ["Frieren"] * 30 + ["Late Alias"],
                              "sources": [{"source": "", "url": ""}] * 30 + [{"source": "anime_sama", "url": AS_URL}]})
    [item] = service.items["u1"]
    assert item["cover"] == VA_COVER and item["cover_fallbacks"] == [] and item["banner"] is None
    assert item["alt_titles"] == [] and item["sources"] == []
    assert service.add("u2", {**FRIEREN, "cover": "https://[bad", "cover_fallbacks": ["https://[bad"], "banner": "https://[bad"})
    [item] = service.items["u2"]
    assert (item["cover"], item["cover_fallbacks"], item["banner"]) == ("", [], None)


def test_added_at_restore_cap_and_profiles(service, monkeypatch):
    service.add("default", FRIEREN, added_at=time.time() + 3600)   # a client clock ahead: clamped
    assert service.items["default"][0]["added_at"] <= time.time()
    service.add("default", BOCCHI, added_at=50.0)                  # restored place after an undo
    assert [i["title"] for i in service.get_items_for_client("")] == ["Frieren", "Bocchi the Rock!"]
    assert "default" in _stored()

    monkeypatch.setattr(watchlist_module, "MAX_ITEMS", 3)
    for n in range(5):
        service.add("u2", {"id": f"a-show-{n}", "title": f"Show {n}", "source": "anime_sama",
                           "url": f"https://anime-sama.to/catalogue/show-{n}"}, added_at=1000.0 + n)
    assert [i["id"] for i in service.items["u2"]] == ["a-show-4", "a-show-3", "a-show-2"]


def test_delete_user_data(service):
    service.add("u1", FRIEREN)
    service.add("u2", FRIEREN)
    service.delete_user_data("u1")
    assert "u1" not in service.items and "u1" not in _stored() and "u2" in _stored()
    service.delete_user_data("u1")


def test_malformed_file_keeps_only_valid_items(monkeypatch, tmp_path):
    path = tmp_path / "watchlist.json"
    monkeypatch.setattr(watchlist_module, "WATCHLIST_FILE", str(path))
    path.write_text(json.dumps({"u1": [{"title": "Frieren", "url": AS_URL, "id": "a-frieren"}, {"title": "No url"}, "x"],
                                "u2": {"not": "a list"}}), encoding="utf-8")
    service = WatchlistService()
    assert list(service.items) == ["u1"] and len(service.items["u1"]) == 1
    assert service.get_items_for_client("u1")[0]["cover_fallbacks"] == []
