from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.routers import stream_proxy
from backend.routers.stream_proxy import rewrite_playlist

VIDEO = bytes(range(256)) * 4


def _upstream(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path == "/redirect":
        return httpx.Response(302, headers={"location": "https://cdn.test/hls/index.m3u8"})
    if path == "/hls/index.m3u8":
        assert request.headers.get("referer") == "https://vidmoly.net/"
        return httpx.Response(200, headers={"content-type": "application/vnd.apple.mpegurl"},
                              content=b"#EXTM3U\n#EXTINF:4,\nseg-1.ts\n")
    if path == "/evil.html":
        return httpx.Response(200, headers={"content-type": "text/html"}, content=b"<script>alert(1)</script>")
    if path == "/video.mp4":
        range_header = request.headers.get("range")
        if range_header == "bytes=10-19":
            return httpx.Response(206, headers={"content-type": "video/mp4", "content-range": f"bytes 10-19/{len(VIDEO)}",
                                                "content-length": "10", "accept-ranges": "bytes"}, content=VIDEO[10:20])
        return httpx.Response(200, headers={"content-type": "video/mp4", "content-length": str(len(VIDEO))}, content=VIDEO)
    return httpx.Response(404)


@pytest.fixture
def proxy_client(monkeypatch):
    async def allow_all(url):
        return None

    monkeypatch.setattr(stream_proxy, "assert_public_http_url", allow_all)
    monkeypatch.setattr(stream_proxy, "peer_is_public", lambda resp: True)
    monkeypatch.setattr(stream_proxy, "get_stream_client",
                        lambda: httpx.AsyncClient(transport=httpx.MockTransport(_upstream)))
    return TestClient(app)


def test_route_follows_redirect_and_rewrites_playlist(proxy_client):
    resp = proxy_client.get("/api/proxy/stream", params={"url": "https://vidmoly.net/redirect"})
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/vnd.apple.mpegurl")
    segment = resp.text.splitlines()[2]
    assert _target(segment) == ("https://cdn.test/hls/seg-1.ts", "https://vidmoly.net/")


def test_route_forwards_range_requests_for_mp4_seeking(proxy_client):
    resp = proxy_client.get("/api/proxy/stream", params={"url": "https://cdn.test/video.mp4"}, headers={"Range": "bytes=10-19"})
    assert resp.status_code == 206
    assert resp.content == VIDEO[10:20]
    assert resp.headers["content-range"] == f"bytes 10-19/{len(VIDEO)}"

    full = proxy_client.get("/api/proxy/stream", params={"url": "https://cdn.test/video.mp4"})
    assert full.status_code == 200
    assert full.content == VIDEO


def _target(proxied: str):
    query = parse_qs(urlparse(proxied).query)
    return query["url"][0], query.get("ref", [None])[0]


def test_playlist_segments_and_keys_go_through_the_proxy():
    playlist = "\n".join([
        "#EXTM3U",
        "#EXT-X-VERSION:3",
        '#EXT-X-KEY:METHOD=AES-128,URI="key.bin"',
        "#EXTINF:10.0,",
        "seg-001.ts",
        "#EXTINF:10.0,",
        "https://cdn2.test/abs/seg-002.ts",
        "",
    ])
    out = rewrite_playlist(playlist, "https://cdn.test/hls/index.m3u8", "https://vidmoly.net/").splitlines()

    assert out[0] == "#EXTM3U"
    key_uri = out[2].split('URI="')[1].rstrip('"')
    assert _target(key_uri) == ("https://cdn.test/hls/key.bin", "https://vidmoly.net/")
    assert _target(out[4]) == ("https://cdn.test/hls/seg-001.ts", "https://vidmoly.net/")
    assert _target(out[6]) == ("https://cdn2.test/abs/seg-002.ts", "https://vidmoly.net/")
    assert all(line.startswith(("#", "/api/proxy/stream?url=")) for line in out if line)


def test_master_playlist_variants_are_rewritten_without_referer():
    out = rewrite_playlist("#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=1\n720p/index.m3u8\n", "https://cdn.test/master.m3u8", None)
    variant = out.splitlines()[2]
    assert _target(variant) == ("https://cdn.test/720p/index.m3u8", None)


def test_route_never_serves_html_on_nami_origin(proxy_client):
    resp = proxy_client.get("/api/proxy/stream", params={"url": "https://evil.test/evil.html"})
    assert resp.headers["content-type"] == "application/octet-stream"
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert "sandbox" in resp.headers["content-security-policy"]


def test_route_refuses_a_connection_without_a_verified_public_peer(monkeypatch):
    async def allow_all(url):
        return None

    monkeypatch.setattr(stream_proxy, "assert_public_http_url", allow_all)
    monkeypatch.setattr(stream_proxy, "get_stream_client",
                        lambda: httpx.AsyncClient(transport=httpx.MockTransport(_upstream)))
    # MockTransport responses carry no peer address: treated like a non-public peer
    resp = TestClient(app).get("/api/proxy/stream", params={"url": "https://cdn.test/video.mp4"})
    assert resp.status_code == 400
