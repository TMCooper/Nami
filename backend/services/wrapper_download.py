"""Episode downloads done by YoitsuWrap itself, with their progress.

YoitsuWrap downloads a season with Season.download_season(max_workers): its episodes in parallel,
each one with yt-dlp (Episode.download_episode) into <path>/Anime/<title>/<season>/<version>/<n>.mp4.
It reports nothing while it works, so the yt-dlp it uses is given progress hooks here: each
episode's output file is registered with a callback that receives bytes, total, speed and ETA,
and can stop that episode (cancel).
"""
import os
import glob
import time
import types
import threading
import importlib
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

import yt_dlp
from yt_dlp.utils import DownloadCancelled

_hooks: Dict[str, Callable[[dict], None]] = {}
_hooks_lock = threading.Lock()
_install_lock = threading.Lock()


def _target_key(path: str) -> str:
    return os.path.normcase(os.path.abspath(path))


class _TrackedYoutubeDL(yt_dlp.YoutubeDL):
    """yt-dlp as YoitsuWrap creates it, plus the progress hook registered for its output file."""

    def __init__(self, params=None, *args, **kwargs):
        params = dict(params or {})
        target = params.get("outtmpl")
        if isinstance(target, dict):
            target = target.get("default")
        hook = None
        if isinstance(target, str):
            with _hooks_lock:
                hook = _hooks.get(_target_key(target))
        if hook is not None:
            params["progress_hooks"] = [*(params.get("progress_hooks") or []), hook]
            params.update(quiet=True, noprogress=True, no_warnings=True)
        super().__init__(params, *args, **kwargs)


def install():
    """Points YoitsuWrap's Episode module at the tracked yt-dlp (its health checks are unchanged)."""
    module = importlib.import_module("YoitsuWrap.Episode")
    with _install_lock:
        if not getattr(module.yt_dlp, "_nami_tracked", False):
            module.yt_dlp = types.SimpleNamespace(YoutubeDL=_TrackedYoutubeDL, utils=yt_dlp.utils, _nami_tracked=True)


def safe_part(name: str) -> str:
    """A folder or file name every system accepts (Windows forbids : ? * and friends)."""
    cleaned = "".join("_" if c in '\\/:*?"<>|' or ord(c) < 32 else c for c in str(name))
    return cleaned.strip(" .") or "_"


@dataclass
class Item:
    """One episode to download: what YoitsuWrap's Episode is built from, and its progress."""
    title: str
    season: str
    version: str
    num: int
    link: str
    source: str
    root: str
    status: str = "queued"          # queued, downloading, completed, error, cancelled
    downloaded: int = 0
    total: int = 0
    speed: float = 0.0              # bytes per second
    eta: Optional[int] = None
    error: str = ""
    file_path: str = ""
    cancelled: bool = False
    on_change: Optional[Callable[["Item"], None]] = field(default=None, repr=False)

    @property
    def target(self) -> str:
        # Episode.download_episode's own output path
        return os.path.join(self.root, "Anime", self.title, self.season, self.version, f"{self.num}.mp4")

    @property
    def progress(self) -> float:
        if self.status == "completed":
            return 100.0
        return round(min(self.downloaded / self.total * 100.0, 99.9), 1) if self.total else 0.0

    def _changed(self):
        if self.on_change:
            self.on_change(self)

    def hook(self, d: dict):
        if self.cancelled:
            raise DownloadCancelled("annulé")
        status = d.get("status")
        if status == "downloading":
            self.status = "downloading"
            self.downloaded = int(d.get("downloaded_bytes") or 0)
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            if not total and d.get("fragment_count") and d.get("fragment_index"):
                # HLS without sizes: estimated from the fragments done so far
                total = self.downloaded * d["fragment_count"] / max(d["fragment_index"], 1)
            self.total = int(total or 0)
            self.speed = float(d.get("speed") or 0.0)
            self.eta = int(d["eta"]) if d.get("eta") is not None else None
        elif status == "finished":
            self.downloaded = int(d.get("total_bytes") or d.get("downloaded_bytes") or self.downloaded)
            self.total = max(self.total, self.downloaded)
        elif status == "error":
            self.error = "yt-dlp a refusé ce lien"
        self._changed()


def _remove_partial(item: Item, attempts: int = 10):
    # A cancelled yt-dlp can hold its .part file open a moment longer (Windows refuses the removal)
    for attempt in range(attempts):
        left = []
        for path in glob.glob(glob.escape(item.target) + "*"):
            try:
                os.remove(path)
            except OSError:
                left.append(path)
        if not left:
            return
        time.sleep(0.5)


def download_season(items: List[Item], workers: int) -> List[Item]:
    """Runs YoitsuWrap's Season.download_season on these episodes (blocking: worker thread only).

    All items share title, season and version. Each ends completed, error or cancelled.
    """
    from YoitsuWrap.Episode import Episode
    from YoitsuWrap.Season import Season

    install()
    if not items:
        return items
    first = items[0]
    episodes = []
    for item in items:
        os.makedirs(os.path.dirname(item.target), exist_ok=True)
        with _hooks_lock:
            _hooks[_target_key(item.target)] = item.hook
        episodes.append(Episode(title=item.title, link=item.link, path=item.root, api_link="",
                                season=item.season, version=item.version, episode_number=item.num, source=item.source))
    season = Season(saison=first.season, title=first.title, episodes=episodes, episodes_numbers=len(episodes),
                    path=first.root, api_link="", version=first.version)
    try:
        season.download_season(max_workers=max(1, workers))
    finally:
        with _hooks_lock:
            for item in items:
                _hooks.pop(_target_key(item.target), None)

    for item in items:
        done = os.path.isfile(item.target) and os.path.getsize(item.target) > 0
        if item.cancelled:
            item.status = "cancelled"
            _remove_partial(item)
        elif done:
            item.status, item.file_path = "completed", item.target
            item.downloaded = item.total = os.path.getsize(item.target)
        else:
            item.status = "error"
            item.error = item.error or "Téléchargement impossible avec ce lien"
            _remove_partial(item)
        item.speed, item.eta = 0.0, None
        item._changed()
    return items


def format_speed(bps: float) -> str:
    if bps <= 0:
        return ""
    if bps >= 1024 * 1024:
        return f"{bps / (1024 * 1024):.1f} Mo/s"
    return f"{bps / 1024:.0f} Ko/s"

