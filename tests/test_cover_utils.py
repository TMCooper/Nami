from urllib.parse import quote

from bs4 import BeautifulSoup

from backend.services.cover_utils import (
    raw_cover_url, client_cover_url, is_usable_cover, extract_img_url, extract_page_cover, normalize_title_key
)

VA_COVER = "https://voir-anime.to/wp-content/uploads/2023/09/thumb_650d6d2a0493b.jpg"


def test_raw_cover_url_unwraps_legacy_proxy_and_percent_encoding():
    assert raw_cover_url(f"/api/proxy/image?url={quote(VA_COVER, safe='')}") == VA_COVER
    assert raw_cover_url(f"/api/img?url={quote(VA_COVER, safe='')}") == VA_COVER
    # value stored by the old code: proxy prefix stripped without unquoting
    assert raw_cover_url(quote(VA_COVER, safe="")) == VA_COVER
    assert raw_cover_url(VA_COVER) == VA_COVER


def test_client_cover_url_routes_hotlink_hosts_through_image_service():
    assert client_cover_url(VA_COVER) == f"/api/img?url={quote(VA_COVER, safe='')}"
    # legacy stored value is rewritten to the new route (bypasses the old 30-day browser cache)
    assert client_cover_url(f"/api/proxy/image?url={quote(VA_COVER, safe='')}") == f"/api/img?url={quote(VA_COVER, safe='')}"
    github = "https://raw.githubusercontent.com/Anime-Sama/IMG/img/contenu/frieren.jpg"
    assert client_cover_url(github) == github
    local = "/api/stream/local?file_path=%2Fdownloads%2Fnami%2Fanime%2FX%2Fcover.jpg"
    assert client_cover_url(local) == local


def test_placeholders_are_never_usable():
    for value in ["", "data:image/svg+xml;charset=utf-8,%3Csvg", "https://via.placeholder.com/180x260", "relative/path.jpg"]:
        assert not is_usable_cover(value)
        assert client_cover_url(value) == ""


def test_extract_img_url_prefers_lazy_attributes_and_absolutizes():
    tag = BeautifulSoup('<img src="data:image/gif;base64,R0lGOD" data-src="/wp-content/a.jpg">', "html.parser").img
    assert extract_img_url(tag, "https://voir-anime.to/anime/x/") == "https://voir-anime.to/wp-content/a.jpg"
    tag = BeautifulSoup('<img srcset="/s.jpg 100w, /l.jpg 600w">', "html.parser").img
    assert extract_img_url(tag, "https://voir-anime.to/") == "https://voir-anime.to/l.jpg"
    assert extract_img_url(None) == ""


def test_extract_page_cover_og_image_then_summary_image():
    soup = BeautifulSoup('<meta property="og:image" content="https://x.test/og.jpg">', "html.parser")
    assert extract_page_cover(soup) == "https://x.test/og.jpg"
    soup = BeautifulSoup('<div class="summary_image"><img data-src="/p.jpg" src="data:x"></div>', "html.parser")
    assert extract_page_cover(soup, "https://voir-anime.to/anime/y/") == "https://voir-anime.to/p.jpg"


def test_normalize_title_key_is_case_and_accent_insensitive():
    assert normalize_title_key("Sousou No Frieren") == normalize_title_key("sousou no frieren")
    assert normalize_title_key("Frièren: Beyond") == "frieren beyond"
