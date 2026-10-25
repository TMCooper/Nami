import pytest

from backend.yoitsu import wrapper_store as wrapper_module


@pytest.fixture(autouse=True)
def no_wrapper_builds(tmp_path, monkeypatch):
    """No test may run a real YoitsuWrap build (network, yt-dlp) nor write snapshots into the repo's data/."""
    monkeypatch.setattr(wrapper_module, "WRAPPER_DIR", str(tmp_path / "yoitsu"))
    builds = []

    def fake_builder(query, version, allowed, order):
        builds.append((query, version))
        return None

    monkeypatch.setattr(wrapper_module.wrapper_store, "_builder", fake_builder)
    monkeypatch.setattr(wrapper_module.wrapper_store, "_snapshots", {})
    monkeypatch.setattr(wrapper_module.wrapper_store, "_jobs", {})
    return builds
