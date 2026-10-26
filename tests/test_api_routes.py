import os

import pytest
from fastapi.testclient import TestClient

from backend.main import app, FRONTEND_DIST
from backend.routers import api as api_module

# No "with TestClient(...)": the lifespan (which launches the scraper APIs) is not started
client = TestClient(app)


def test_local_stream_refuses_files_outside_the_media_root(tmp_path, monkeypatch):
    secret = tmp_path / "secret.txt"
    secret.write_text("nope")
    monkeypatch.setattr(api_module.settings_service, "get_root_folder", lambda: str(tmp_path / "downloads"))

    for route in ("/api/stream/local", "/api/stream/thumbnail"):
        assert client.get(route, params={"file_path": str(secret)}).status_code == 404
    assert client.delete("/api/library/episode", params={"file_path": str(secret)}).status_code == 404
    assert secret.exists()


def test_local_stream_serves_files_inside_the_media_root(tmp_path, monkeypatch):
    episode = tmp_path / "downloads" / "nami" / "anime" / "X" / "Saison_1" / "Episode_01.mp4"
    episode.parent.mkdir(parents=True)
    episode.write_bytes(b"0123456789")
    monkeypatch.setattr(api_module.settings_service, "get_root_folder", lambda: str(tmp_path / "downloads"))

    resp = client.get("/api/stream/local", params={"file_path": str(episode)}, headers={"Range": "bytes=2-5"})
    assert resp.status_code == 206
    assert resp.content == b"2345"


def test_image_proxy_refuses_internal_targets():
    resp = client.get("/api/img", params={"url": "http://127.0.0.1:8000/catalog"})
    assert resp.status_code == 404
    assert resp.headers["x-nami-fallback"] == "1"


def test_stream_proxy_refuses_internal_targets():
    assert client.get("/api/proxy/stream", params={"url": "http://127.0.0.1:5000/api/status"}).status_code == 400


def test_catalog_status_route_exists():
    resp = client.get("/api/catalog/status")
    assert resp.status_code == 200
    assert "is_updating" in resp.json()


@pytest.mark.skipif(not os.path.isdir(FRONTEND_DIST), reason="frontend not built")
def test_unknown_api_route_is_a_json_404_not_the_spa():
    resp = client.get("/api/does-not-exist")
    assert resp.status_code == 404
    assert resp.headers["content-type"].startswith("application/json")


def test_library_deletes_cannot_wipe_the_whole_library(tmp_path, monkeypatch):
    root = tmp_path / "downloads"
    episode = root / "nami" / "anime" / "X" / "Saison_1" / "Episode_01.mp4"
    episode.parent.mkdir(parents=True)
    episode.write_bytes(b"x")
    monkeypatch.setattr(api_module.settings_service, "get_root_folder", lambda: str(root))

    assert client.delete("/api/library/anime", params={"anime_title": ".."}).status_code == 400
    assert client.delete("/api/library/anime", params={"anime_title": ""}).status_code == 400
    for folder in (root / "nami", root / "nami" / "anime", root / "nami" / "anime" / "X"):
        assert client.delete("/api/library/episode", params={"file_path": str(folder)}).status_code == 400
    assert episode.exists()

    assert client.delete("/api/library/episode", params={"file_path": str(episode)}).status_code == 200
    assert not episode.exists()
