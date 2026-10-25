from fastapi.testclient import TestClient

from backend.main import app
from backend.services import history_service as history_module
from backend.services.download_service import resolve_anime_folder
from backend.services.history_service import HistoryService

client = TestClient(app)


def test_progress_under_a_title_variant_updates_the_existing_record(monkeypatch, tmp_path):
    monkeypatch.setattr(history_module, "HISTORY_FILE", str(tmp_path / "history.json"))
    service = HistoryService()
    service.save_progress("u1", "Re:Zero", "Saison 1", "1", 100, 1400)
    service.save_progress("u1", "Re Zero", "Saison 1", "2", 200, 1400)
    service.toggle_watched("u1", "re zero", "Saison 1", "3", True)

    assert list(service.history["u1"]) == ["Re:Zero"]
    episodes = service.history["u1"]["Re:Zero"]["episodes"]
    assert set(episodes) == {"Saison 1:1", "Saison 1:2", "Saison 1:3"}
    assert len(service.get_continue_watching("u1")) == 1


def test_downloads_reuse_the_folder_of_a_title_variant(tmp_path):
    base = tmp_path / "nami" / "anime"
    (base / "ReZero").mkdir(parents=True)
    assert resolve_anime_folder(str(base), "Re:Zero") == "ReZero"
    assert resolve_anime_folder(str(base), "Re Zero") == "ReZero"
    assert resolve_anime_folder(str(base), "Frieren") == "Frieren"
    assert resolve_anime_folder(str(tmp_path / "missing"), "Frieren") == "Frieren"


def test_anime_routes(monkeypatch):
    from backend.yoitsu import gateway as gateway_module
    gw = gateway_module.yoitsu_gateway
    monkeypatch.setattr(gw, "_catalog_next", float("inf"))
    monkeypatch.setattr(gw.index, "flush", lambda: None)

    assert client.get("/api/anime/a-zzz-unknown-show").status_code == 404
    found = client.get("/api/anime/lookup", params={"source": "voiranime", "url": "https://voir-anime.to/anime/zzz-test-show-2/",
                                                   "title": "Zzz Test Show 2"})
    assert found.status_code == 200
    assert found.json()["id"].startswith("a-")
    assert client.get("/api/anime/lookup", params={"source": "voiranime", "url": "", "title": ""}).status_code == 400
