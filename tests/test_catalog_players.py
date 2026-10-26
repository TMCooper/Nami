import asyncio
import json

import httpx
from bs4 import BeautifulSoup

from backend.services import catalog_service as catalog_module
from backend.services.catalog_service import CatalogService, anime_sama_player_rank, host_label


def test_voiranime_players_are_listed_best_first_without_sibnet():
    sources = {
        "LECTEUR Sibnet": '<iframe src="https://video.sibnet.ru/shell.php?videoid=1"></iframe>',
        "LECTEUR VOE": '<iframe src="https:\\/\\/voe.sx\\/e\\/abc"></iframe>',
        "LECTEUR myTV": '<iframe src="//mytv.test/embed/1"></iframe>',
    }
    html = f"<script>var thisChapterSources = {json.dumps(sources)};</script>"
    players = CatalogService.parse_voiranime_players(html)
    assert [p["host"] for p in players] == ["LECTEUR myTV", "LECTEUR VOE"]
    assert players[0]["embed_url"] == "https://mytv.test/embed/1"
    assert players[1]["embed_url"] == "https://voe.sx/e/abc"


def test_voiranime_players_fallback_to_iframes():
    html = '<iframe src="https://vidmoly.net/embed-x.html"></iframe><iframe src="https://voiranime.test/internal"></iframe>'
    assert CatalogService.parse_voiranime_players(html) == [{"host": "vidmoly", "embed_url": "https://vidmoly.net/embed-x.html"}]


def test_host_label_and_rank():
    assert host_label("https://video.sibnet.ru/shell.php") == "sibnet"
    assert host_label("https://www.sendvid.com/embed/1") == "sendvid"
    ranked = sorted(["https://uqload.vc/embed-1.html", "https://video.sibnet.ru/x", "https://ansembed.net/embed-1.html", "https://vidmoly.net/e"],
                    key=anime_sama_player_rank)
    # live check (2026-10): only ansembed resolves to a direct m3u8 among Anime-Sama's current hosts
    assert ranked == ["https://ansembed.net/embed-1.html", "https://vidmoly.net/e", "https://uqload.vc/embed-1.html", "https://video.sibnet.ru/x"]


def test_anime_sama_players_from_episodes_js(monkeypatch):
    season_page = '<html><script src="episodes.js?filever=12"></script></html>'
    episodes_js = """
    var eps1 = ['https://video.sibnet.ru/shell.php?videoid=1', 'https://video.sibnet.ru/shell.php?videoid=2'];
    var eps2 = ["https://vidmoly.net/embed-a.html", "https://vidmoly.net/embed-b.html"];
    """
    requested = []

    def handler(request):
        requested.append(str(request.url))
        if request.url.path.endswith("episodes.js"):
            return httpx.Response(200, text=episodes_js)
        return httpx.Response(200, text=season_page)

    service = CatalogService()
    service.client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(catalog_module.cache_service, "get_anime_details", lambda source, key: None)
    monkeypatch.setattr(catalog_module.cache_service, "save_anime_details", lambda source, key, content: None)

    episodes = asyncio.run(service.fetch_anime_sama_players("https://anime-sama.to/catalogue/frieren/saison1/vostfr", "vf"))
    assert requested[0] == "https://anime-sama.to/catalogue/frieren/saison1/vf"
    assert requested[1].startswith("https://anime-sama.to/catalogue/frieren/saison1/vf/episodes.js")
    assert [e["num"] for e in episodes] == [1, 2]
    assert episodes[0]["embed_url"] == "https://vidmoly.net/embed-a.html"   # resolvable host first, sibnet last
    assert [p["host"] for p in episodes[1]["players"]] == ["vidmoly", "sibnet"]


def test_anime_sama_page_metadata():
    html = """
    <h1 id="titreOeuvre">Frieren</h1>
    <h2 id="titreAlter">Soso no Furiren, Sousou no Frieren, Frieren: Beyond Journey's End</h2>
    <div class="oe-synopsis"><p id="synopsisText">Le jeune héros Himmel   et ses compagnons. <a href="#">Lire plus</a></p></div>
    <div class="oe-genres"><a class="genre-pill">Shônen</a><a class="genre-pill">Fantasy</a></div>
    """
    synopsis, alt_titles, genres = CatalogService._anime_sama_page_metadata(BeautifulSoup(html, "html.parser"))
    assert synopsis == "Le jeune héros Himmel et ses compagnons."
    assert alt_titles == ["Soso no Furiren", "Sousou no Frieren", "Frieren: Beyond Journey's End"]
    assert genres == ["Shônen", "Fantasy"]
