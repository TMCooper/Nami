import asyncio

import pytest

from backend.yoitsu import gateway as gateway_module
from backend.yoitsu.gateway import YoitsuGateway
from backend.yoitsu.index import Entry

AS_URL = "https://anime-sama.to/catalogue/frieren"
VA_S1 = "https://voir-anime.to/anime/sousou-no-frieren/"
VA_S1_VF = "https://voir-anime.to/anime/sousou-no-frieren-vf/"
VA_S2 = "https://voir-anime.to/anime/sousou-no-frieren-2/"

AS_ROWS = [
    {"base_url": AS_URL, "title": "Frieren", "cover": "https://raw.githubusercontent.com/Anime-Sama/IMG/img/contenu/frieren.jpg",
     "synopsis": "Le jeune héros Himmel et ses compagnons, l'elfe Frieren, le nain Eisen et le prêtre Heiter, rentrent victorieux.",
     "Saison": "Saison 1", "url": f"{AS_URL}/saison1/vostfr"},
    {"base_url": AS_URL, "title": "Frieren", "cover": "", "synopsis": "", "Saison": "Saison 2", "url": f"{AS_URL}/saison2/vostfr"},
    {"base_url": AS_URL, "title": "Frieren", "cover": "", "synopsis": "", "Saison": "Scans", "url": f"{AS_URL}/scan/vf"},
]
VA_ROWS = [
    {"base_url": VA_S1, "title": "Sousou no Frieren", "cover": "https://voir-anime.to/wp-content/uploads/f.jpg",
     "synopsis": "Que deviennent les héros une fois le mal vaincu ?", "Saison": "Saison 1",
     "url": VA_S1, "_vostfr_url": VA_S1, "_vf_url": VA_S1_VF},
    # voiranime_API labels collapse posts: this "Saison 1" row is Boruto, found by substring search
    {"base_url": VA_S1, "title": "Sousou no Frieren", "cover": "", "synopsis": "Boruto synopsis", "Saison": "Saison 1",
     "url": "https://voir-anime.to/anime/boruto/", "_vostfr_url": "https://voir-anime.to/anime/boruto/", "_vf_url": None},
]
FRIEREN_ENTRIES = [
    Entry("anime_sama", AS_URL, "Frieren"),
    Entry("voiranime", VA_S1, "Sousou no Frieren"),
    Entry("voiranime", VA_S2, "Sousou no Frieren 2"),
    Entry("voiranime", VA_S1_VF, "Sousou no Frieren (VF)"),
]


def _make_gateway(tmp_path, monkeypatch, as_rows, va_rows, entries, catalog=None, page=None, lecteurs=None):
    store = {}
    cache = gateway_module.cache_service
    monkeypatch.setattr(cache, "get_anime_details", lambda source, key: store.get((source, key)))
    monkeypatch.setattr(cache, "save_anime_details", lambda source, key, content: store.__setitem__((source, key), content))
    monkeypatch.setattr(cache, "add_recent_anime", lambda uid, anime: store.setdefault("recents", []).append(anime))

    gateway = YoitsuGateway(meta_dir=str(tmp_path))
    gateway.anilist.enabled = False
    gateway._catalog_next = float("inf")  # no catalogue download in tests
    gateway.store = store

    async def fake_info(source, title):
        return as_rows if source == "anime_sama" else va_rows

    async def fake_page(url, refresh=False):
        return page(url) if page else None

    async def fake_lecteurs(url):
        return lecteurs(url) if lecteurs else {}

    async def no_covers(items, limit=15, wait_seconds=0):
        return None

    monkeypatch.setattr(gateway, "get_info", fake_info)
    monkeypatch.setattr(gateway_module.catalog_service, "fetch_anime_sama_page", fake_page)
    monkeypatch.setattr(gateway_module.catalog_service, "_anime_sama_lecteurs", fake_lecteurs)
    monkeypatch.setattr(gateway_module.catalog_service, "_fill_missing_voiranime_covers", no_covers)
    if catalog is not None:
        gateway.index.set_catalog(catalog)
    gateway.index.remember(entries)
    return gateway


@pytest.fixture
def gw(tmp_path, monkeypatch):
    def lecteurs(url):
        # Season 1 has a VF; season 2's VF page could not be checked (None = unknown)
        if "saison1/vf" in url:
            return {"eps1": ["https://vidmoly.net/e1"]}
        return None if "saison2/vf" in url else {}

    return _make_gateway(tmp_path, monkeypatch, AS_ROWS, VA_ROWS, FRIEREN_ENTRIES, lecteurs=lecteurs)


def _variants(season):
    return {(v["source"], v["version"]): v for v in season["variants"]}


def test_details_merge_sources_seasons_versions_and_synopsis(gw):
    details = asyncio.run(gw.details("a-frieren", user_id="u1"))

    assert details["title"] == "Frieren"
    assert details["synopsis"]["origin"] == "anime_sama" and details["synopsis"]["lang"] == "fr"
    assert [s["source"] for s in details["sources"]] == ["anime_sama", "voiranime"]
    assert [s["key"] for s in details["seasons"]] == ["saison-1", "saison-2", "scans"]
    assert not any(k.startswith("_") for k in details)

    s1, s2, scans = details["seasons"]
    variants = _variants(s1)
    assert set(variants) == {("anime_sama", "vostfr"), ("anime_sama", "vf"), ("voiranime", "vostfr"), ("voiranime", "vf")}
    assert variants[("anime_sama", "vf")]["available"] is True           # probed: episodes.js present
    assert variants[("voiranime", "vf")]["url"] == VA_S1_VF
    assert variants[("voiranime", "vostfr")]["url"] == VA_S1             # the Boruto row never becomes a season
    assert variants[("anime_sama", "vostfr")]["history_title"] == "Frieren"
    assert variants[("voiranime", "vostfr")]["history_title"] == "Sousou No Frieren"   # legacy VoirAnime key

    s2_variants = _variants(s2)
    assert s2_variants[("voiranime", "vostfr")]["url"] == VA_S2
    assert "Sousou No Frieren 2" in s2_variants[("voiranime", "vostfr")]["history_titles"]
    assert all("boruto" not in v["url"] for s in details["seasons"] for v in s["variants"])
    assert scans["is_scans"] and scans["variants"][0]["version"] == "scans"

    assert details["cover"].startswith("https://raw.githubusercontent.com/")
    assert gw.store["recents"][0]["title"] == "Frieren"


def test_vf_variants_have_their_own_season_name_and_legacy_keys(gw):
    s1 = asyncio.run(gw.details("a-frieren"))["seasons"][0]
    variants = _variants(s1)
    assert variants[("anime_sama", "vostfr")]["season_name"] == "Saison 1"
    assert variants[("anime_sama", "vf")]["season_name"] == "Saison 1 VF"
    va_vf = variants[("voiranime", "vf")]
    assert va_vf["season_name"] == "Saison 1 VF"
    # Before the merge the VF post was its own card, saved under its slug title and "Saison 1"
    assert {"title": "Sousou No Frieren Vf", "season": "Saison 1"} in va_vf["history_keys"]
    assert {"title": "Sousou No Frieren", "season": "Saison 1 VF"} in va_vf["history_keys"]


def test_unknown_vf_availability_is_neither_assumed_nor_cached(gw):
    details = asyncio.run(gw.details("a-frieren"))
    s2_vf = _variants(details["seasons"][1])[("anime_sama", "vf")]
    assert s2_vf["available"] is None
    assert s2_vf["url"] not in gw._vf_probe
    assert f"{AS_URL}/saison1/vf" in gw._vf_probe


def test_details_are_cached_and_unknown_ids_are_none(gw):
    first = asyncio.run(gw.details("a-frieren"))
    gw.get_info = None  # a second build would crash: must come from cache
    assert asyncio.run(gw.details("a-frieren")) == first
    assert asyncio.run(gw.details("a-does-not-exist")) is None


def test_details_cache_is_rebuilt_when_the_entity_gains_a_post(gw):
    asyncio.run(gw.details("a-frieren"))
    gw.index.remember([Entry("voiranime", "https://voir-anime.to/anime/sousou-no-frieren-3/", "Sousou no Frieren 3")])
    keys = [s["key"] for s in asyncio.run(gw.details("a-frieren"))["seasons"]]
    assert "saison-3" in keys


def test_voiranime_down_falls_back_to_known_posts(gw, monkeypatch):
    async def info(source, title):
        return AS_ROWS if source == "anime_sama" else []

    monkeypatch.setattr(gw, "get_info", info)
    details = asyncio.run(gw.details("a-frieren", refresh=True))
    s1 = next(s for s in details["seasons"] if s["key"] == "saison-1")
    s2 = next(s for s in details["seasons"] if s["key"] == "saison-2")
    assert {v["url"] for v in s1["variants"] if v["source"] == "voiranime"} == {VA_S1, VA_S1_VF}
    assert {v["url"] for v in s2["variants"] if v["source"] == "voiranime"} == {VA_S2}


def test_anime_sama_contract_mismatch_uses_the_page(tmp_path, monkeypatch):
    rows = [{**AS_ROWS[0], "base_url": "https://anime-sama.to/catalogue/other-show"}]

    def page(url):
        return {"slug": "frieren", "title": "Frieren", "url": url, "cover": "", "synopsis": "Synopsis de la page.",
                "alt_titles": ["Sousou no Frieren"], "genres": ["Shônen"], "seasons": [{"label": "Saison 1", "url": f"{url}/saison1/vostfr"}]}

    gw = _make_gateway(tmp_path, monkeypatch, rows, VA_ROWS, FRIEREN_ENTRIES, page=page)
    details = asyncio.run(gw.details("a-frieren", refresh=True))
    assert details["synopsis"]["text"] == "Synopsis de la page."
    assert details["genres"] == ["Shônen"]
    assert _variants(details["seasons"][0])[("anime_sama", "vostfr")]["url"] == f"{AS_URL}/saison1/vostfr"


def test_page_h1_is_the_anime_sama_history_title(tmp_path, monkeypatch):
    def page(url):
        return {"slug": "frieren", "title": "Frieren : Beyond Journey's End", "url": url, "cover": "", "synopsis": "",
                "alt_titles": [], "genres": [], "seasons": []}

    gw = _make_gateway(tmp_path, monkeypatch, AS_ROWS, VA_ROWS, FRIEREN_ENTRIES, page=page)
    as_vostfr = _variants(asyncio.run(gw.details("a-frieren"))["seasons"][0])[("anime_sama", "vostfr")]
    assert as_vostfr["history_title"] == "Frieren : Beyond Journey's End"
    assert as_vostfr["history_titles"] == ["Frieren : Beyond Journey's End", "Frieren"]


def test_anime_sama_alt_titles_only_link_known_entries(tmp_path, monkeypatch):
    boruto = "https://anime-sama.to/catalogue/boruto"

    def page(url):
        return {"slug": "frieren", "title": "Frieren", "url": url, "cover": "", "synopsis": "", "genres": [], "seasons": [],
                "alt_titles": ["Frieren at the Funeral", "Journey's End", "Boruto Naruto Next Generations", "Bocchi"]}

    entries = FRIEREN_ENTRIES + [
        Entry("anime_sama", boruto, "Boruto Naruto Next Generations"),
        Entry("voiranime", "https://voir-anime.to/anime/bocchi/", "Bocchi"),
    ]
    gw = _make_gateway(tmp_path, monkeypatch, AS_ROWS, VA_ROWS, entries, page=page)
    asyncio.run(gw.details("a-frieren"))
    assert gw.aliases.find("boruto naruto next generations") != "frieren"   # another entity's page
    assert gw.aliases.find("bocchi") != "frieren"                           # one-word fragment
    assert not gw.aliases.known("journey s end")                            # names no known entry


def test_original_and_remake_lineages_do_not_merge_seasons(tmp_path, monkeypatch):
    as_url = "https://anime-sama.to/catalogue/hunter-x-hunter"
    va_1999 = "https://voir-anime.to/anime/hunter-x-hunter/"
    va_2011 = "https://voir-anime.to/anime/hunter-x-hunter-2011/"
    rows = [{"base_url": as_url, "title": "Hunter x Hunter", "cover": "", "synopsis": "Gon.", "Saison": "Saison 1",
             "url": f"{as_url}/saison1/vostfr"}]
    entries = [Entry("anime_sama", as_url, "Hunter x Hunter"), Entry("voiranime", va_1999, "Hunter x Hunter"),
               Entry("voiranime", va_2011, "Hunter x Hunter (2011)")]
    gw = _make_gateway(tmp_path, monkeypatch, rows, [], entries, catalog=entries)

    seasons = {s["key"]: s for s in asyncio.run(gw.details("a-hunter-x-hunter"))["seasons"]}
    assert {v["source"] for v in seasons["saison-1"]["variants"]} == {"anime_sama"}
    assert _variants(seasons["remake-2011"])[("voiranime", "vostfr")]["url"] == va_2011
    original = next(s for s in seasons.values() if s["label"] == "Original · Saison 1")
    va_1999_variant = _variants(original)[("voiranime", "vostfr")]
    assert va_1999_variant["url"] == va_1999
    assert {"title": "Hunter X Hunter", "season": "Saison 1"} in va_1999_variant["history_keys"]


def test_a_subtitle_that_names_the_work_is_not_a_season(tmp_path, monkeypatch):
    as_url = "https://anime-sama.to/catalogue/fullmetal-alchemist-brotherhood"
    va_url = "https://voir-anime.to/anime/fullmetal-alchemist-brotherhood/"
    rows = [{"base_url": as_url, "title": "Fullmetal Alchemist: Brotherhood", "cover": "", "synopsis": "", "Saison": "Saison 1",
             "url": f"{as_url}/saison1/vostfr"}]
    entries = [Entry("anime_sama", as_url, "Fullmetal Alchemist: Brotherhood"),
               Entry("voiranime", va_url, "Fullmetal Alchemist: Brotherhood")]
    catalog = entries + [Entry("voiranime", "https://voir-anime.to/anime/fullmetal-alchemist/", "Fullmetal Alchemist")]
    gw = _make_gateway(tmp_path, monkeypatch, rows, [], entries, catalog=catalog)

    details = asyncio.run(gw.details("a-fullmetal-alchemist-brotherhood"))
    assert [s["key"] for s in details["seasons"]] == ["saison-1"]
    assert _variants(details["seasons"][0])[("voiranime", "vostfr")]["url"] == va_url


def test_episodes_are_routed_to_the_chosen_source(gw, monkeypatch):
    async def as_players(url, version, refresh=False):
        return [{"num": 1, "title": "Épisode 1", "embed_url": "https://vidmoly.net/e1",
                 "players": [{"host": "vidmoly", "embed_url": "https://vidmoly.net/e1"}]}]

    async def va_details(url, source, refresh=False, track_recent=True):
        assert track_recent is False
        return {"episodes": [{"num": 1, "title": "Sousou no Frieren - 01 VOSTFR", "url": url, "embed_url": url}]}

    monkeypatch.setattr(gateway_module.catalog_service, "fetch_anime_sama_players", as_players)
    monkeypatch.setattr(gateway_module.catalog_service, "get_details", va_details)

    as_result = asyncio.run(gw.episodes("a-frieren", "saison-1", "anime_sama", "vostfr"))
    assert as_result["variant"]["source"] == "anime_sama" and as_result["episodes"][0]["players"]

    va_result = asyncio.run(gw.episodes("a-frieren", "saison-1", "voiranime", "vf"))
    assert va_result["variant"]["url"] == VA_S1_VF
    assert va_result["episodes"][0]["embed_url"] == VA_S1_VF

    scans = asyncio.run(gw.episodes("a-frieren", "scans", "anime_sama", "vostfr"))
    assert scans["is_scans"] is True and scans["episodes"] == []


def test_search_returns_one_ranked_entity_per_anime(gw, monkeypatch):
    async def as_search(q):
        return [{"id": f"as:{AS_URL}", "title": "Frieren", "source": "anime_sama", "url": AS_URL, "cover": ""}]

    async def va_search(q, group=True, cover_wait=None):
        assert group is False and cover_wait == 0   # covers are filled per card afterwards
        return [
            {"title": "Sousou no Frieren", "source": "voiranime", "url": VA_S1, "cover": ""},
            {"title": "Sousou no Frieren 2", "source": "voiranime", "url": VA_S2, "cover": ""},
            {"title": "Bocchi the Rock!", "source": "voiranime", "url": "https://voir-anime.to/anime/bocchi/", "cover": ""},
        ]

    monkeypatch.setattr(gateway_module.catalog_service, "_search_anime_sama", as_search)
    monkeypatch.setattr(gateway_module.catalog_service, "_search_voiranime", va_search)
    results = asyncio.run(gw.search("Frieren"))
    assert [r["title"] for r in results] == ["Frieren"]   # Bocchi filtered out by relevance
    assert results[0]["id"] == "a-frieren" and len(results[0]["sources"]) == 2


def test_lookup_only_accepts_source_urls(gw):
    assert asyncio.run(gw.lookup("voiranime", "https://evil.test/anime/x/", "X")) is None
    assert asyncio.run(gw.lookup("anime_sama", VA_S1, "Sousou no Frieren")) is None
    assert asyncio.run(gw.lookup("voiranime", VA_S1, "Sousou no Frieren"))["id"] == "a-frieren"
