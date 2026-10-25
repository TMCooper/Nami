import os
import json
import time
import threading
from typing import Any, Callable

_locks: dict = {}
_locks_guard = threading.Lock()


def _lock_for(path: str) -> threading.RLock:
    key = os.path.normcase(os.path.abspath(path))
    with _locks_guard:
        lock = _locks.get(key)
        if lock is None:
            lock = threading.RLock()
            _locks[key] = lock
        return lock


def load_json(path: str, default: Callable[[], Any]) -> Any:
    """Loads a JSON store, falling back to its .bak copy.

    An unreadable main file is moved aside once (.corrupt-<ts>) instead of being silently
    replaced by an empty store on the next save.
    """
    with _lock_for(path):
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"[Storage] Unreadable JSON {path}: {e}")
                try:
                    os.replace(path, f"{path}.corrupt-{int(time.time())}")
                except OSError:
                    pass

        backup = f"{path}.bak"
        if os.path.exists(backup):
            try:
                with open(backup, "r", encoding="utf-8") as f:
                    print(f"[Storage] Restored {path} from backup")
                    return json.load(f)
            except Exception as e:
                print(f"[Storage] Unreadable backup {backup}: {e}")

        return default()


def save_json(path: str, data: Any, indent: int = 2):
    """Writes a JSON store atomically (temp file + os.replace), keeping the previous version as .bak."""
    with _lock_for(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp_path = f"{path}.tmp-{os.getpid()}-{threading.get_ident()}"
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=indent, ensure_ascii=False)
                f.flush()
                os.fsync(f.fileno())
            if os.path.exists(path):
                _replace_with_retry(path, f"{path}.bak")
            _replace_with_retry(tmp_path, path)
        finally:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass


def _replace_with_retry(src: str, dst: str, attempts: int = 5):
    # Windows can briefly lock a file (antivirus, indexer): retry a few times before giving up.
    for attempt in range(attempts):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if attempt == attempts - 1:
                raise
            time.sleep(0.05)
