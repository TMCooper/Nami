import json
import os
import subprocess
import time

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.services import self_update

client = TestClient(app)


def _git(cwd, *args):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def checkout(tmp_path, monkeypatch):
    """A 'GitHub' repository and a Nami checkout of it (nothing outside tmp_path)."""
    remote, work, other = tmp_path / "remote.git", tmp_path / "nami", tmp_path / "other"
    subprocess.run(["git", "init", "--bare", "-b", "main", str(remote)], check=True, capture_output=True)
    subprocess.run(["git", "clone", str(remote), str(work)], check=True, capture_output=True)
    (work / "requirements.txt").write_text("")
    _git(work, "add", ".")
    _git(work, "commit", "-m", "first")
    _git(work, "push", "origin", "HEAD:main")
    subprocess.run(["git", "clone", str(remote), str(other)], check=True, capture_output=True)
    monkeypatch.setattr(self_update, "PROJECT_ROOT", str(work))
    ran = []
    monkeypatch.setattr(self_update, "_run", lambda cmd, cwd, timeout: ran.append(cmd) and None)
    return work, other, ran


def _push_commit(repo, name="new.txt"):
    (repo / name).write_text("x")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", f"add {name}")
    _git(repo, "push", "origin", "HEAD:main")


def test_a_checkout_updates_itself_by_fast_forward(checkout):
    work, other, ran = checkout
    assert self_update.mode() == "git" and self_update.status()["up_to_date"]
    assert self_update.apply()["status"] == "up_to_date"

    _push_commit(other)
    st = self_update.status()
    assert not st["up_to_date"] and st["name"] == "Nami (main)" and st["restarts"]
    res = self_update.apply()
    assert res["status"] == "updated" and res["restart"] and (work / "new.txt").exists()
    assert any("requirements.txt" in c for c in ran)            # dependencies installed again
    assert self_update.status()["up_to_date"]


def test_a_checkout_with_local_work_is_never_touched(checkout):
    work, other, _ = checkout
    _push_commit(other)
    (work / "requirements.txt").write_text("changed locally")
    assert self_update.apply()["status"] == "error"
    assert (work / "requirements.txt").read_text() == "changed locally" and not (work / "new.txt").exists()

    (work / "requirements.txt").write_text("")
    (work / "local.txt").write_text("mine")
    _git(work, "add", "local.txt")
    _git(work, "commit", "-m", "local commit")                  # diverged from the repository
    res = self_update.apply()
    assert res["status"] == "error" and "commits" in res["message"]


def test_docker_asks_the_host_updater(tmp_path, monkeypatch):
    monkeypatch.setattr(self_update, "PROJECT_ROOT", str(tmp_path))
    monkeypatch.setattr(self_update, "UPDATE_DIR", str(tmp_path / "data" / "nami-update"))
    monkeypatch.setattr(self_update, "STATE_FILE", str(tmp_path / "data" / "nami-update" / "state.json"))
    monkeypatch.setattr(self_update, "REQUEST_FILE", str(tmp_path / "data" / "nami-update" / "request"))
    assert self_update.mode() == "none" and "updater.sh" in self_update.status()["note"]

    os.makedirs(tmp_path / "data" / "nami-update")
    state = {"branch": "refonte-yoitsu", "local": "a" * 40, "remote": "b" * 40, "state": "idle", "alive_at": time.time() - 600}
    (tmp_path / "data" / "nami-update" / "state.json").write_text(json.dumps(state))
    assert self_update.mode() == "host"
    assert "ne tourne pas" in self_update.status()["note"] and self_update.apply()["status"] == "error"

    state["alive_at"] = time.time()
    (tmp_path / "data" / "nami-update" / "state.json").write_text(json.dumps(state))
    st = self_update.status()
    assert (st["current_version"], st["latest_version"], st["up_to_date"], st["note"]) == ("aaaaaaa", "bbbbbbb", False, "")
    res = self_update.apply()
    assert res["status"] == "requested" and res["host_rebuild"]
    assert (tmp_path / "data" / "nami-update" / "request").exists()


def test_a_restart_runs_the_same_command_again(monkeypatch):
    calls = []
    monkeypatch.setattr(self_update.os, "execv", lambda exe, argv: calls.append(argv))
    monkeypatch.setattr(self_update.sys, "argv", ["/usr/local/bin/uvicorn", "backend.main:app", "--port", "8080"])
    self_update.exec_again()
    monkeypatch.setattr(self_update.sys, "argv", [r"C:\venv\Scripts\uvicorn.exe", "backend.main:app"])
    self_update.exec_again()
    assert calls[0][1:] == ["/usr/local/bin/uvicorn", "backend.main:app", "--port", "8080"]
    assert calls[1][1:] == ["-m", "uvicorn", "backend.main:app"]


def test_updating_nami_or_the_wrapper_restarts_the_server(monkeypatch):
    from backend.routers import api as api_module
    restarts = []
    monkeypatch.setattr(api_module.self_update, "request_restart", lambda: restarts.append(1))
    monkeypatch.setattr(api_module.self_update, "apply", lambda: {"status": "updated", "restart": True, "message": "ok"})
    monkeypatch.setattr(api_module.update_service, "update_yoitsuwrap", lambda: {"status": "up_to_date", "message": ""})
    assert client.post("/api/updates/apply", params={"target": "yoitsuwrap"}).json()["restart"] is False
    assert client.post("/api/updates/apply", params={"target": "nami"}).json()["restart"] is True
    assert restarts == [1]
    assert client.post("/api/updates/apply", params={"target": "rm -rf"}).status_code == 422
    boot = client.get("/api/server/boot").json()["boot"]
    assert boot and client.get("/api/server/boot").json()["boot"] == boot
