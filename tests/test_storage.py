import os
import json
import glob

from backend.services.storage import load_json, save_json


def test_save_then_load_roundtrip(tmp_path):
    path = str(tmp_path / "store.json")
    save_json(path, {"a": 1, "é": "ü"})
    assert load_json(path, dict) == {"a": 1, "é": "ü"}
    assert not glob.glob(path + ".tmp-*")


def test_previous_version_kept_as_backup(tmp_path):
    path = str(tmp_path / "store.json")
    save_json(path, {"v": 1})
    save_json(path, {"v": 2})
    with open(path + ".bak", encoding="utf-8") as f:
        assert json.load(f) == {"v": 1}


def test_corrupt_file_falls_back_to_backup_and_is_kept_aside(tmp_path):
    path = str(tmp_path / "store.json")
    save_json(path, {"v": 1})
    save_json(path, {"v": 2})
    with open(path, "w", encoding="utf-8") as f:
        f.write("{truncated")

    assert load_json(path, dict) == {"v": 1}
    assert len(glob.glob(path + ".corrupt-*")) == 1, "the unreadable file must be preserved for recovery"
    # moved aside once: later reads do not pile up more copies
    load_json(path, dict)
    assert len(glob.glob(path + ".corrupt-*")) == 1


def test_missing_file_returns_default(tmp_path):
    assert load_json(str(tmp_path / "nope.json"), list) == []
    assert not os.listdir(tmp_path)
