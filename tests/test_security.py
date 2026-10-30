import time

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.services import auth_service as auth_module
from backend.services.auth_service import auth_service, hash_password
from backend.services.settings_service import settings_service
from backend.services.user_service import user_service

pytestmark = pytest.mark.real_sessions


@pytest.fixture
def no_accounts(signed_in, monkeypatch):
    """A fresh install: no account at all (settings kept in memory)."""
    signed_in.clear()
    store = dict(settings_service.get_settings())
    monkeypatch.setattr(settings_service, "settings", store)
    monkeypatch.setattr(settings_service, "update_settings", lambda new: store.update(new) or store)
    return store


def browser() -> TestClient:
    return TestClient(app)


def register(client, name, password="motdepasse-solide"):
    return client.post("/api/auth/register", json={"username": name, "password": password})


def login(client, name, password="motdepasse-solide", remember=False):
    return client.post("/api/auth/login", json={"username": name, "password": password, "remember": remember})


def test_the_first_account_is_the_super_administrator(no_accounts):
    owner = browser()
    assert owner.get("/api/auth/status").json() == {"user": None, "has_users": False, "registration_open": True,
                                                   "setup_needed": False}
    me = register(owner, "Proprio").json()
    assert me["role"] == "admin" and owner.get("/api/auth/me").json()["username"] == "Proprio"

    friend = browser()
    assert register(friend, "Ami").json()["role"] == "user"
    assert friend.get("/api/admin/users").status_code == 403

    # Closed registration: only the administrator adds accounts
    assert owner.post("/api/admin/policy", json={"registration_open": False}).status_code == 200
    stranger = browser()
    assert stranger.get("/api/auth/status").json()["registration_open"] is False
    assert register(stranger, "Inconnu").status_code == 403
    assert owner.post("/api/admin/users", json={"username": "Invite", "password": "un-autre-mot-2"}).status_code == 200
    assert login(stranger, "Invite", "un-autre-mot-2").status_code == 200


def test_signing_in_needs_the_pseudo_and_the_password(no_accounts):
    register(browser(), "Proprio")
    client = browser()
    assert client.get("/api/history").status_code == 401             # nothing without a session
    assert client.get("/api/proxy/stream", params={"url": "https://x.test/a.m3u8"}).status_code == 401
    wrong = login(client, "Proprio", "pas-le-bon")
    unknown = login(client, "Personne", "pas-le-bon")
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json() == {"detail": "Pseudo ou mot de passe incorrect."}   # says nothing more

    resp = login(client, "proprio", remember=True)                   # the pseudo's case does not matter
    assert resp.status_code == 200 and "httponly" in resp.headers["set-cookie"].lower()
    assert "max-age" in resp.headers["set-cookie"].lower()           # « Se souvenir de moi »
    assert client.get("/api/history").status_code == 200
    assert "password_hash" not in str(client.get("/api/auth/me").json())
    client.post("/api/auth/logout")
    assert client.get("/api/history").status_code == 401


def test_repeated_failures_lock_the_ip_and_the_account(no_accounts):
    owner = browser()
    register(owner, "Proprio")
    attacker = browser()
    for _ in range(auth_module.FAIL_LIMIT):
        assert login(attacker, "Proprio", "devine").status_code == 401
    locked = login(attacker, "Proprio")                              # even the right password waits
    assert locked.status_code == 429 and int(locked.headers["retry-after"]) > 0
    assert login(browser(), "Proprio").status_code == 429            # the account itself is locked too

    security = owner.get("/api/admin/security").json()
    assert {l["kind"] for l in security["lockouts"]} == {"ip", "user"}
    assert any(e["event"] == "locked" for e in security["events"])
    for lock in security["lockouts"]:
        assert owner.delete(f"/api/admin/lockouts/{lock['key']}").status_code == 200
    assert login(attacker, "Proprio").status_code == 200


def test_locks_grow_with_each_new_lock(no_accounts):
    for _ in range(2 * auth_module.FAIL_LIMIT):
        auth_service.login_failed("10.0.0.9", "x")
        auth_service._locks = {k: (0, n) for k, (_, n) in auth_service._locks.items()}   # the first lock is over
    assert auth_service._locks["ip:10.0.0.9"][1] == 2 and auth_service.locked_for("10.0.0.9", "x") == 0
    for _ in range(auth_module.FAIL_LIMIT):
        auth_service.login_failed("10.0.0.9", "x")
    assert auth_service.locked_for("10.0.0.9", "x") > 3 * auth_module.LOCK_BASE      # 4 min the third time


def test_an_identity_header_or_body_opens_nothing(no_accounts):
    owner = browser()
    owner_id = register(owner, "Proprio").json()["id"]
    owner.post("/api/watchlist", json={"anime": {"id": "a-zzz", "title": "Zzz", "source": "anime_sama",
                                                 "url": "https://anime-sama.to/catalogue/zzz"}})
    intruder = browser()
    register(intruder, "Intrus")
    seen = intruder.get("/api/watchlist", headers={"X-User-ID": owner_id}).json()
    assert seen["total"] == 0                                        # his own (empty) list, not the owner's
    assert browser().get("/api/watchlist", headers={"X-User-ID": owner_id}).status_code == 401


def test_only_the_administrator_manages_the_server_and_the_accounts(no_accounts):
    owner = browser()
    register(owner, "Proprio")
    user = browser()
    user_id = register(user, "Ami").json()["id"]
    for method, path, kwargs in (("post", "/api/settings", {"json": {"root_folder": "/tmp"}}),
                                 ("post", "/api/updates/apply", {"params": {"target": "nami"}}),
                                 ("post", "/api/catalog/update", {}),
                                 ("post", "/api/sources/voiranime", {"json": {"enabled": False}}),
                                 ("delete", "/api/library/anime", {"params": {"anime_title": "Zzz"}}),
                                 ("get", "/api/admin/security", {}),
                                 ("delete", f"/api/admin/users/{user_id}", {})):
        assert getattr(user, method)(path, **kwargs).status_code == 403, path
    assert "root_folder" not in user.get("/api/settings").json()

    # Disabling ends the account's sessions and its next sign-in
    assert owner.patch(f"/api/admin/users/{user_id}", json={"disabled": True}).json()["disabled"] is True
    assert user.get("/api/history").status_code == 401
    assert login(browser(), "Ami").status_code == 403
    owner.patch(f"/api/admin/users/{user_id}", json={"disabled": False})
    # A reset password is the only one that works
    assert owner.post(f"/api/admin/users/{user_id}/password", json={"password": "remis-a-zero-1"}).status_code == 200
    assert login(browser(), "Ami").status_code == 401 and login(browser(), "Ami", "remis-a-zero-1").status_code == 200
    # The super administrator can neither be deleted nor disabled: his role is transferred first
    owner_id = owner.get("/api/auth/me").json()["id"]
    assert owner.delete(f"/api/admin/users/{owner_id}").status_code == 400
    assert owner.post(f"/api/admin/users/{user_id}/make-admin", json={"password": "faux"}).status_code == 403
    assert owner.post(f"/api/admin/users/{user_id}/make-admin", json={"password": "motdepasse-solide"}).status_code == 200
    assert owner.get("/api/admin/users").status_code == 403
    assert owner.delete(f"/api/admin/users/{user_id}").status_code == 403


def test_everyone_manages_his_own_account(no_accounts):
    register(browser(), "Proprio")
    phone, laptop = browser(), browser()
    register(phone, "Ami")
    login(laptop, "Ami")
    assert phone.patch("/api/auth/profile", json={"username": "Proprio"}).status_code == 400   # taken
    assert phone.patch("/api/auth/profile", json={"username": "Ami Renommé", "avatar": "🦊"}).json()["avatar"] == "🦊"
    assert phone.post("/api/auth/password", json={"current_password": "faux", "new_password": "nouveau-mot-2"}).status_code == 400
    resp = phone.post("/api/auth/password", json={"current_password": "motdepasse-solide", "new_password": "nouveau-mot-2"})
    assert resp.json()["sessions_ended"] == 1
    assert laptop.get("/api/history").status_code == 401 and phone.get("/api/history").status_code == 200
    assert phone.post("/api/auth/delete", json={"password": "motdepasse-solide"}).status_code == 403
    assert phone.post("/api/auth/delete", json={"password": "nouveau-mot-2"}).status_code == 200
    assert login(browser(), "Ami Renommé", "nouveau-mot-2").status_code == 401


def test_passwords_are_slow_hashes_and_old_ones_are_upgraded(no_accounts):
    register(browser(), "Proprio")
    user = next(iter(user_service.users.values()))
    assert user["password_hash"].startswith("pbkdf2_sha256$")
    user["password_hash"] = "abcd:" + __import__("hashlib").sha256(b"ancien-mot-de-passe" + b"abcd").hexdigest()
    assert login(browser(), "Proprio", "ancien-mot-de-passe").status_code == 200
    assert user["password_hash"].startswith("pbkdf2_sha256$")
    assert register(browser(), "Court", "1234").status_code == 400


def test_an_install_with_accounts_but_no_administrator_needs_the_setup_code(no_accounts):
    user_service.users["old"] = {"id": "old", "username": "Ancien", "role": "user", "disabled": False, "created_at": 1,
                                 "password_hash": hash_password("ancien-mot-2")}
    client = browser()
    assert client.get("/api/auth/status").json()["setup_needed"] is True
    code = auth_service.setup_code(create=False)
    assert code and login(client, "Ancien", "ancien-mot-2").status_code == 200
    assert client.post("/api/auth/setup", json={"code": "AAAAAA-BBBBBB-CCCCCC"}).status_code == 403
    assert client.post("/api/auth/setup", json={"code": code.lower()}).json()["role"] == "admin"
    assert auth_service.setup_code(create=False) is None and client.get("/api/admin/users").status_code == 200


def test_writes_from_another_site_are_refused(no_accounts):
    client = browser()
    register(client, "Proprio")
    assert client.post("/api/auth/logout", headers={"Origin": "https://evil.test"}).status_code == 403
    assert client.get("/api/history", headers={"Origin": "https://evil.test"}).status_code == 200   # reads are not writes
    assert client.post("/api/history/clear", headers={"Origin": "http://testserver"}).status_code in (200, 405)


def test_the_administrator_decides_where_episodes_are_downloaded(no_accounts, monkeypatch):
    owner = browser()
    register(owner, "Proprio")
    user = browser()
    register(user, "Ami")
    owner.post("/api/admin/policy", json={"server_downloads": False, "device_max_episodes": 2})
    assert user.get("/api/policy").json()["server_downloads"] is False
    body = {"anime_id": "a-zzz", "season": "saison-1", "episodes": [1]}
    refused = user.post("/api/downloads/fiche", json=body)
    assert refused.status_code == 403 and "Sur cet appareil" in refused.json()["detail"]
    assert user.post("/api/downloads", json={"anime_title": "Zzz", "episode_num": "1", "stream_url": "https://x.test/a.m3u8"}).status_code == 403
    assert owner.post("/api/downloads/fiche", json=body).status_code != 403          # the administrator still may
    too_many = user.post("/api/device-download/jobs", json={**body, "episodes": [1, 2, 3]})
    assert too_many.status_code == 413

    # A nearly full disk stops downloads for everyone
    from backend import security
    monkeypatch.setattr(security, "free_bytes", lambda path: 1024 ** 3)
    owner.post("/api/admin/policy", json={"server_downloads": True, "min_free_gb": 5})
    full = user.post("/api/downloads/fiche", json=body)
    assert full.status_code == 507 and "Espace disque insuffisant" in full.json()["detail"]
