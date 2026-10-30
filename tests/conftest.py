import copy
import os

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


TEST_ADMIN = "test_admin"


@pytest.fixture(autouse=True)
def signed_in(tmp_path, monkeypatch, request):
    """Accounts, sessions and the security log live in tmp_path; requests come from a signed-in administrator
    (or the user named by an X-User-ID header). Tests marked real_sessions use real session cookies."""
    from backend import security
    from backend.services import auth_service as auth_module
    from backend.services import user_service as user_module

    from backend.services import cache_service as cache_module, download_service as download_module
    from backend.services import history_service as history_module, settings_service as settings_module
    from backend.services import watchlist_service as watchlist_module

    for name in ("SESSIONS_FILE", "SECURITY_LOG_FILE", "SETUP_CODE_FILE"):
        monkeypatch.setattr(auth_module, name, str(tmp_path / f"{name.lower()}.json"))
    monkeypatch.setattr(user_module, "USERS_FILE", str(tmp_path / "users.json"))
    # No route a test calls may write the repository's own data/ (a real install's stores)
    for module, name in ((history_module, "HISTORY_FILE"), (watchlist_module, "WATCHLIST_FILE"),
                         (cache_module, "RECENT_FILE"), (download_module, "DOWNLOADS_DB"),
                         (settings_module, "SETTINGS_FILE")):
        monkeypatch.setattr(module, name, str(tmp_path / f"store-{name.lower()}.json"))
    monkeypatch.setattr(settings_module.settings_service, "settings", copy.deepcopy(settings_module.DEFAULT_SETTINGS))
    auth = auth_module.auth_service
    for attr, value in (("_sessions", {}), ("_log", []), ("_failures", {}), ("_locks", {}), ("_registrations", {})):
        monkeypatch.setattr(auth, attr, value)
    users = {TEST_ADMIN: {"id": TEST_ADMIN, "username": "Zzz Admin", "avatar": "x", "password_hash": "", "role": "admin",
                          "disabled": False, "created_at": 0}}
    monkeypatch.setattr(user_module.user_service, "users", users)
    if request.node.get_closest_marker("real_sessions"):
        return users
    monkeypatch.setattr(security, "session_identity", lambda req: req.headers.get("x-user-id") or TEST_ADMIN)
    return users


REPO_DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")


def _data_files():
    found = {}
    for root, _, files in os.walk(REPO_DATA):
        for name in files:
            path = os.path.join(root, name)
            found[path] = os.path.getmtime(path)
    return found


@pytest.fixture(autouse=True, scope="session")
def repository_data_untouched():
    """The whole run must leave the repository's data/ (a real install's stores) exactly as it was."""
    before = _data_files()
    yield
    after = _data_files()
    changed = sorted(p for p in set(before) | set(after) if before.get(p) != after.get(p))
    assert not changed, f"tests wrote into data/: {changed}"
