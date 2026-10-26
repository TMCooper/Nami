import sys
import socket
import asyncio
import textwrap

import httpx
import pytest

pytest.importorskip("flask")

from backend import main as main_module


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _fake_animesama(root):
    """Same module layout as AnimeSamaApi (src.api.Yui.app, src/utils/config.py without __init__)."""
    (root / "src" / "utils").mkdir(parents=True)
    (root / "src" / "__init__.py").write_text("")
    (root / "src" / "utils" / "config.py").write_text("class Config:\n    IP = '127.0.0.1'\n    PORT = 5000\n")
    (root / "src" / "api.py").write_text(textwrap.dedent("""
        from flask import Flask, jsonify
        from .utils.config import Config

        class Yui:
            app = Flask(__name__)

            @app.route('/api/status')
            def status():
                return jsonify({'API Status': 'Online', 'port': Config.PORT, 'debug': Yui.app.debug})
    """))


def test_animesama_launcher_starts_ready_without_debug(tmp_path, monkeypatch):
    api_dir = tmp_path / "AnimeSamaApi"
    _fake_animesama(api_dir)
    port = _free_port()
    spec = {
        **main_module.SUBMODULES["animesama"],
        "path": str(api_dir),
        "port": port,
        "cmd": [sys.executable, main_module.ANIME_SAMA_LAUNCHER, "--host", "127.0.0.1", "--port", str(port)],
    }
    monkeypatch.setitem(main_module.SUBMODULES, "animesama", spec)
    monkeypatch.setattr(main_module, "LOG_DIR", str(tmp_path / "logs"))

    main_module._launch_submodule("animesama")
    try:
        assert asyncio.run(main_module._wait_until_ready("animesama", timeout=30))
        status = httpx.get(f"http://127.0.0.1:{port}/api/status").json()
        assert status["port"] == port      # Config.PORT set for AnimeSamaApi's self-calls
        assert status["debug"] is False
    finally:
        main_module._stop_submodule("animesama")
    assert (tmp_path / "logs" / "animesama.log").exists()


def test_wait_until_ready_reports_a_crashed_process(tmp_path, monkeypatch):
    spec = {
        **main_module.SUBMODULES["animesama"],
        "path": str(tmp_path),
        "port": _free_port(),
        "cmd": [sys.executable, "-c", "raise SystemExit(3)"],
    }
    monkeypatch.setitem(main_module.SUBMODULES, "animesama", spec)
    monkeypatch.setattr(main_module, "LOG_DIR", str(tmp_path / "logs"))

    main_module._launch_submodule("animesama")
    try:
        assert asyncio.run(main_module._wait_until_ready("animesama", timeout=10)) is False
    finally:
        main_module._stop_submodule("animesama")
