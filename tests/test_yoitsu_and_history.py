from backend.services import yoitsu_service as yoitsu_module
from backend.services import history_service as history_module
from backend.services.yoitsu_service import YoitsuService
from backend.services.history_service import HistoryService


def test_config_exit_is_contained_and_retried_later(monkeypatch, tmp_path):
    monkeypatch.setattr(yoitsu_module.settings_service, "get_root_folder", lambda: str(tmp_path))
    attempts = []

    def failing_create_config(**kwargs):
        attempts.append(1)
        raise SystemExit()  # YoitsuWrap calls exit() when an API is down

    monkeypatch.setattr(yoitsu_module.Config, "create_config", staticmethod(failing_create_config))
    service = YoitsuService()
    assert service.get_config() is None
    assert service.get_config() is None  # inside the retry delay: no new ping
    assert len(attempts) == 1

    # One API down: the other one keeps being used during the retry delay
    partial = {"ANIMESAMA": object()}
    monkeypatch.setattr(yoitsu_module.Config, "create_config", staticmethod(lambda **kwargs: partial))
    service.allow_retry()
    assert service.get_config() is partial
    assert service.get_config() is partial  # inside the retry delay: no new ping, still usable
    assert service._config is None          # never cached: the missing API is retried later

    complete = {"ANIMESAMA": object(), "VOIRANIME": object()}
    monkeypatch.setattr(yoitsu_module.Config, "create_config", staticmethod(lambda **kwargs: complete))
    service.allow_retry()  # what an API restart does once the API answers again
    assert service.get_config() is complete
    assert service.get_config() is complete
    service.allow_retry()
    assert service.get_config() is complete, "a valid cached config survives API restarts"


def test_history_never_stores_placeholder_and_upgrades_it(monkeypatch, tmp_path):
    monkeypatch.setattr(history_module, "HISTORY_FILE", str(tmp_path / "history.json"))
    service = HistoryService()
    service.save_progress("u1", "Frieren", "Saison 1", "1", 30, 1400, cover="data:image/svg+xml;charset=utf-8,x")
    assert service.history["u1"]["Frieren"]["cover"] == ""

    service.save_progress("u1", "Frieren", "Saison 1", "1", 60, 1400, cover="/api/img?url=https%3A%2F%2Fvoir-anime.to%2Ff.jpg")
    assert service.history["u1"]["Frieren"]["cover"] == "https://voir-anime.to/f.jpg"

    item = service.get_continue_watching("u1")[0]
    assert item["cover"].startswith("/api/img?url=")
    assert service.get_history_for_client("u1")["Frieren"]["cover"].startswith("/api/img?url=")
