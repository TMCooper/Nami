import asyncio
import json
import threading
import time
from types import SimpleNamespace
from urllib.parse import quote

import pytest

from backend.services import history_service as history_module
from backend.services.history_service import HistoryService
from backend.yoitsu.gateway import YoitsuGateway

AS_URL = "https://anime-sama.to/catalogue/frieren"
VA_S1 = "https://voir-anime.to/anime/sousou-no-frieren/"
VA_S2 = "https://voir-anime.to/anime/sousou-no-frieren-2/"
BANNER = "https://s4.anilist.co/file/anilistcdn/media/anime/banner/154587.jpg"
FRIEREN = {"id": "a-frieren", "title": "Frieren", "source": "anime_sama", "url": AS_URL, "entry_title": "Frieren",
           "banner": BANNER, "trailer": {"site": "youtube", "id": "qgQkRsJWW3I"}}
SOUSOU = {"id": "a-sousou-no-frieren", "title": "Sousou no Frieren", "source": "voiranime", "url": VA_S2}
S1 = {"season_key": "saison-1", "source": "anime_sama", "version": "vostfr"}
CANONICAL = {"a-sousou-no-frieren": "a-frieren"}


def canon(eid):
    return CANONICAL.get(eid, eid)


def _proxied(url):
    return "/api/img?url=" + quote(url, safe="")


# What history_claims reads of client details (built by hand: no scraping)
FRIEREN_DETAILS = {
    "id": "a-frieren", "title": "Frieren", "source": "anime_sama", "url": AS_URL,
    "banner": _proxied("https://s4.anilist.co/b.jpg"), "trailer": None,
    "sources": [{"source": "anime_sama", "url": AS_URL, "title": "Frieren"},
                {"source": "voiranime", "url": VA_S1, "title": "Sousou no Frieren"}],
    "seasons": [
        {"key": "saison-1", "label": "Saison 1", "is_scans": False, "variants": [
            {"source": "anime_sama", "version": "vostfr", "history_keys": [{"title": "Frieren", "season": "Saison 1"}]},
            {"source": "anime_sama", "version": "vf", "history_keys": [{"title": "Frieren", "season": "Saison 1 VF"}]},
            {"source": "voiranime", "version": "vostfr", "history_keys": [{"title": "Sousou No Frieren", "season": "Saison 1"}]},
            {"source": "voiranime", "version": "vf", "history_keys": [{"title": "Sousou No Frieren", "season": "Saison 1 VF"},
                                                                      {"title": "Sousou No Frieren Vf", "season": "Saison 1"}]},
        ]},
        {"key": "saison-2", "label": "Saison 2", "is_scans": False, "variants": [
            {"source": "voiranime", "version": "vostfr", "history_keys": [{"title": "Sousou No Frieren", "season": "Saison 2"},
                                                                          {"title": "Sousou No Frieren 2", "season": "Saison 1"}]},
        ]},
        {"key": "scans", "label": "Scans", "is_scans": True, "variants": [
            {"source": "anime_sama", "version": "scans", "history_keys": [{"title": "Frieren", "season": "Scans"}]},
        ]},
    ],
}


@pytest.fixture
def clock(monkeypatch):
    """Strictly increasing time for history_service: a play and a mark never share a timestamp."""
    now = [1761420000.0]

    def tick():
        now[0] += 1.0
        return now[0]

    monkeypatch.setattr(history_module, "time", SimpleNamespace(time=tick))
    return now


@pytest.fixture
def service(monkeypatch, tmp_path, clock):
    monkeypatch.setattr(history_module, "HISTORY_FILE", str(tmp_path / "history.json"))
    return HistoryService()


def _cards(service, uid="u1", **kwargs):
    return service.get_continue_watching(uid, **kwargs)


def _stored(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


async def _until(condition, timeout=5.0):
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while not condition():
        assert loop.time() < deadline, "condition not met in time"
        await asyncio.sleep(0.01)


def test_progress_with_context_links_the_record_and_keeps_legacy_shape(service):
    service.save_progress("u1", "Frieren", "Saison 1", "4", 610.2, 1420.0, cover="https://voir-anime.to/f.jpg",
                          embed_url="https://vidmoly.net/e4", anime=FRIEREN, context={**S1, "ep_title": "Épisode 4"},
                          next_ep={"ep_id": "5", "title": "Épisode 5"})

    assert list(service.history["u1"]) == ["Frieren"]
    record = service.history["u1"]["Frieren"]
    assert {"anime_title", "cover", "last_season", "last_ep_id", "last_updated", "episodes"} <= set(record)
    assert (record["anime_title"], record["last_season"], record["last_ep_id"]) == ("Frieren", "Saison 1", "4")
    assert record["anime"]["id"] == "a-frieren" and record["anime"]["by"] == "write"
    assert record["seasons"]["Saison 1"] == {"key": "saison-1", "source": "anime_sama", "version": "vostfr", "by": "write"}
    ep = record["episodes"]["Saison 1:4"]
    assert ep["position_sec"] == 610.2 and ep["embed_url"] == "https://vidmoly.net/e4"
    assert ep["played_at"] and ep["ep_title"] == "Épisode 4" and ep["next"] == {"ep_id": "5", "title": "Épisode 5"}

    client = service.get_history_for_client("u1")["Frieren"]
    assert client["anime"]["wide_images"][0].startswith("/api/img?url=")
    assert "by" not in client["anime"] and client["cover"].startswith("/api/img?url=")
    assert list(_stored(history_module.HISTORY_FILE)) == ["u1"]


def test_continue_card_comes_from_playback_not_from_toggles(service):
    service.save_progress("u1", "Frieren", "Saison 1", "5", 560, 1400, anime=FRIEREN, context=S1)
    service.toggle_watched("u1", "Frieren", "Saison 1", "3", True, anime=FRIEREN, context=S1, next_ep={"ep_id": "4"})
    [card] = _cards(service)
    assert (card["season"], card["episode_num"], card["is_next"], card["progress_percent"]) == ("Saison 1", "5", False, 40.0)

    service.save_progress("u2", "Frieren", "Saison 2", "3", 560, 1400, anime=FRIEREN)
    service.mark_season("u2", "Frieren", "Saison 1", [str(n) for n in range(1, 13)], anime=FRIEREN, context=S1)
    [card] = _cards(service, "u2")
    assert (card["season"], card["episode_num"], card["progress_percent"]) == ("Saison 2", "3", 40.0)

    service.save_progress("u3", "Frieren", "Saison 1", "2", 1372, 1400)   # 98 %
    service.save_progress("u3", "Frieren", "Saison 1", "5", 560, 1400)
    service.toggle_watched("u3", "Frieren", "Saison 1", "2", False)
    [card] = _cards(service, "u3")
    assert (card["episode_num"], card["position_sec"], card["is_next"]) == ("5", 560.0, False)


def test_finished_pointer_becomes_next_or_drops(service, clock):
    local = "D:/nami/anime/Frieren/Saison_1/Episode_03.mp4"
    service.save_progress("u1", "Frieren", "Saison 1", "3", 1330, 1400, file_path=local, anime=FRIEREN, context=S1,
                          next_ep={"ep_id": "4", "title": "Épisode 4"})
    [card] = _cards(service)
    assert card["is_next"] and card["episode_num"] == "4" and card["episode_title"] == "Épisode 4"
    assert card["position_sec"] == 0 and card["progress_percent"] == 0 and card["remaining_sec"] is None
    assert card["watched"] is False and card["embed_url"] is None and card["file_path"] is None
    assert not any("/api/stream/thumbnail" in url for url in card["wide_images"])

    # E4 marked watched from the detail modal, with its own successor: the chain goes on
    service.toggle_watched("u1", "Frieren", "Saison 1", "4", True, next_ep={"ep_id": "5", "title": "Épisode 5"})
    [card] = _cards(service)
    assert card["is_next"] and card["episode_num"] == "5"

    # Without a recorded successor nothing is invented
    del service.history["u1"]["Frieren"]["episodes"]["Saison 1:4"]["next"]
    assert _cards(service) == []

    # A started successor is resumed
    service.save_progress("u2", "Frieren", "Saison 1", "3", 1330, 1400, anime=FRIEREN, context=S1, next_ep={"ep_id": "4"})
    service.history["u2"]["Frieren"]["episodes"]["Saison 1:4"] = {
        "position_sec": 420.0, "duration_sec": 1400.0, "last_watched_at": clock[0], "played_at": clock[0]}
    [card] = _cards(service, "u2")
    assert (card["episode_num"], card["is_next"], card["progress_percent"]) == ("4", False, 30.0)

    # A next card cannot be played without an entity link
    service.save_progress("u3", "Bocchi", "Saison 1", "3", 1330, 1400, next_ep={"ep_id": "4"})
    assert _cards(service, "u3") == []


def test_rewatch_in_progress_is_resumed(service):
    service.save_progress("u1", "Frieren", "Saison 1", "3", 1390, 1400, anime=FRIEREN, context=S1)
    service.toggle_watched("u1", "Frieren", "Saison 1", "3", True)   # the player's 'ended'
    assert _cards(service) == []

    service.save_progress("u1", "Frieren", "Saison 1", "3", 420, 1400)
    [card] = _cards(service)
    assert (card["episode_num"], card["is_next"], card["progress_percent"], card["watched"]) == ("3", False, 30.0, True)


def test_explicit_mark_after_play_wins(service):
    service.save_progress("u1", "Frieren", "Saison 1", "3", 560, 1400, anime=FRIEREN, context=S1, next_ep={"ep_id": "4"})
    service.toggle_watched("u1", "Frieren", "Saison 1", "3", True)
    [card] = _cards(service)
    assert card["is_next"] and card["episode_num"] == "4"

    service.toggle_watched("u1", "Frieren", "Saison 1", "3", False)
    [card] = _cards(service)
    assert (card["episode_num"], card["is_next"], card["position_sec"]) == ("3", False, 560.0)
    assert service.history["u1"]["Frieren"]["episodes"]["Saison 1:3"]["position_sec"] == 560.0


def test_legacy_finished_pointer_drops_unless_successor_was_started(service):
    service.history["u1"] = {"Frieren": {
        "anime_title": "Frieren", "cover": "", "last_season": "Saison 1", "last_ep_id": "3", "last_updated": 100.0,
        "episodes": {"Saison 1:3": {"position_sec": 1390.0, "duration_sec": 1400.0, "last_watched_at": 100.0, "watched": True}},
    }}
    assert _cards(service) == []

    service.history["u1"]["Frieren"]["episodes"]["Saison 1:4"] = {"position_sec": 700.0, "duration_sec": 1400.0, "last_watched_at": 90.0}
    [card] = _cards(service)
    assert (card["episode_num"], card["progress_percent"], card["is_next"]) == ("4", 50.0, False)


def test_toggle_only_records_never_make_a_card(service):
    service.toggle_watched("u1", "Frieren", "Saison 1", "3", True, anime=FRIEREN, context=S1, next_ep={"ep_id": "4"})
    service.toggle_watched("u1", "Frieren", "Saison 1", "4", False)
    service.mark_season("u1", "Bocchi", "Saison 1", ["1", "2"])
    assert _cards(service) == []


def test_continue_one_card_per_anime_across_records(service):
    service.save_progress("u1", "Frieren", "Saison 1", "2", 300, 1400, anime=FRIEREN, context=S1)
    service.save_progress("u1", "Sousou No Frieren 2", "Saison 1", "3", 300, 1400, anime=SOUSOU)
    [card] = _cards(service, canonical=canon)
    assert card["key"] == "a-frieren" and card["anime_title"] == "Sousou No Frieren 2"
    assert card["anime"]["id"] == "a-frieren"
    assert len(_cards(service)) == 2, "without the alias the records are two animes"

    # Two ids the resolver does not unite, one primary source entry
    service.save_progress("u2", "Frieren", "Saison 1", "2", 300, 1400, anime=FRIEREN)
    service.save_progress("u2", "Frieren Beyond", "Saison 1", "3", 300, 1400, anime={**FRIEREN, "id": "a-frieren-beyond"})
    [card] = _cards(service, "u2")
    assert card["anime_title"] == "Frieren Beyond"

    # The newest record ended another season (mapped keys tell 'Sousou No Frieren 2'/'Saison 1' is saison-2):
    # the older unfinished record of the same anime gives the card
    service.save_progress("u3", "Frieren", "Saison 1", "2", 300, 1400, anime=FRIEREN, context=S1)
    service.save_progress("u3", "Sousou No Frieren 2", "Saison 1", "12", 1390, 1400, anime=SOUSOU,
                          context={"season_key": "saison-2", "source": "voiranime", "version": "vostfr"})
    [card] = _cards(service, "u3", canonical=canon)
    assert (card["anime_title"], card["episode_num"]) == ("Frieren", "2")

    # Unmapped legacy posts all say 'Saison 1': a finished sequel post never hides the first season
    service.save_progress("u4", "Frieren", "Saison 1", "2", 300, 1400, anime=FRIEREN)
    service.save_progress("u4", "Sousou No Frieren 2", "Saison 1", "12", 1390, 1400, anime=SOUSOU)
    [card] = _cards(service, "u4", canonical=canon)
    assert (card["anime_title"], card["episode_num"]) == ("Frieren", "2")

    # ...but the VF post of the same season does
    service.save_progress("u5", "Sousou No Frieren", "Saison 1", "3", 300, 1400, anime={**SOUSOU, "url": VA_S1})
    service.save_progress("u5", "Sousou No Frieren Vf", "Saison 1", "12", 1390, 1400, anime={**SOUSOU, "url": VA_S1})
    assert _cards(service, "u5", canonical=canon) == []


def test_older_record_never_resumes_a_season_a_newer_record_settled(service):
    sousou_s1 = {**SOUSOU, "url": VA_S1}

    def va(n):
        return f"https://voir-anime.to/anime/sousou-no-frieren/sousou-no-frieren-{n:02d}-vostfr/"

    def as_host(n):
        return f"https://vidmoly.net/embed-frieren{n}.html"

    # VoirAnime: ep 1-2 finished, ep 3 started; then the switch to Anime-Sama, watched from 3 to the last episode
    for n, pos in ((1, 1400), (2, 1400), (3, 560)):
        service.save_progress("u1", "Sousou No Frieren", "Saison 1", str(n), pos, 1420, embed_url=va(n), anime=sousou_s1)
    for n in range(3, 13):
        service.save_progress("u1", "Frieren", "Saison 1", str(n), 1400, 1420, embed_url=as_host(n), anime=FRIEREN,
                              context=S1, next_ep={"ep_id": str(n + 1)} if n < 12 else None)
    assert _cards(service, canonical=canon) == []

    # VF and VOSTFR of one season are the same content (both mapped: the keys decide)
    service.save_progress("u2", "Sousou No Frieren", "Saison 1 VF", "3", 560, 1420, anime=sousou_s1,
                          context={"season_key": "saison-1", "source": "voiranime", "version": "vf"})
    service.save_progress("u2", "Frieren", "Saison 1", "12", 1400, 1420, anime=FRIEREN, context=S1)
    assert _cards(service, "u2", canonical=canon) == []

    # « Tout marquer vu » on the current record takes the anime off the shelf, no older card in its place
    service.save_progress("u3", "Sousou No Frieren", "Saison 1", "3", 560, 1420, embed_url=va(3), anime=sousou_s1)
    for n in range(1, 6):
        service.save_progress("u3", "Frieren", "Saison 1", str(n), 1400 if n < 5 else 700, 1420, embed_url=as_host(n),
                              anime=FRIEREN, context=S1, next_ep={"ep_id": str(n + 1)})
    [card] = _cards(service, "u3", canonical=canon)
    assert (card["anime_title"], card["episode_num"]) == ("Frieren", "5")
    service.mark_season("u3", "Frieren", "Saison 1", [str(n) for n in range(1, 7)], anime=FRIEREN, context=S1)
    assert _cards(service, "u3", canonical=canon) == []


def test_no_next_walk_goes_through_stored_finished_successors(service):
    def legacy(last):
        eps = {f"Saison 1:{n}": {"position_sec": 1400.0, "duration_sec": 1420.0, "last_watched_at": 100.0 + n,
                                 "watched": True} for n in range(1, last)}
        eps[f"Saison 1:{last}"] = {"position_sec": 710.0, "duration_sec": 1420.0, "last_watched_at": 100.0 + last}
        return {"X": {"anime_title": "X", "cover": "", "last_season": "Saison 1", "last_ep_id": str(last),
                      "last_updated": 100.0 + last, "episodes": eps}}

    # Phase 1 episodes have no `next`: a rewatch of ep 2 (closed at the credits) still leads to the half-watched ep 8
    service.history["u1"] = legacy(8)
    assert _cards(service)[0]["episode_num"] == "8"
    service.save_progress("u1", "X", "Saison 1", "2", 1400, 1420, next_ep={"ep_id": "3"})
    [card] = _cards(service)
    assert (card["episode_num"], card["is_next"], card["progress_percent"]) == ("8", False, 50.0)

    # Longer than MAX_NEXT_HOPS
    service.history["u2"] = legacy(80)
    service.save_progress("u2", "X", "Saison 1", "2", 1400, 1420)
    assert _cards(service, "u2")[0]["episode_num"] == "80"

    # Marked successors are walked through; an unseen episode is never invented
    service.history["u3"] = legacy(8)
    episodes = service.history["u3"]["X"]["episodes"]
    episodes["Saison 1:4"] = {"watched": True, "last_watched_at": 104.0, "watched_at": 104.0}
    service.save_progress("u3", "X", "Saison 1", "2", 1400, 1420)
    assert _cards(service, "u3")[0]["episode_num"] == "8"
    episodes["Saison 1:8"]["position_sec"] = 1400.0
    assert _cards(service, "u3") == []


def test_unlinked_record_keeps_every_legacy_item_field(service):
    service.save_progress("u1", "Bocchi the Rock!", "Saison 1", "2", 300, 1400, embed_url="https://vidmoly.net/b2")
    [card] = _cards(service)
    assert {"anime_title", "cover", "season", "episode_num", "position_sec", "duration_sec", "progress_percent", "watched",
            "last_watched_at", "embed_url", "file_path"} <= set(card)
    assert card["key"].startswith("title:") and card["anime"] is None and card["source"] is None
    assert card["display_title"] == "Bocchi the Rock!" and card["embed_url"] == "https://vidmoly.net/b2"
    assert card["last_watched_at"] == service.history["u1"]["Bocchi the Rock!"]["last_updated"]


def test_remaining_time_titles_and_images(service):
    local = "D:/nami/anime/Frieren/Saison_1/Episode_04.mp4"
    service.save_progress("u1", "Sousou No Frieren", "Saison 1", "4", 610.2, 1420.0, file_path=local,
                          anime={**FRIEREN, "banner": None}, context={**S1, "ep_title": "Sousou no Frieren - 04 VOSTFR"})
    [card] = _cards(service)
    assert card["remaining_sec"] == pytest.approx(1420.0 - 610.2)
    assert card["episode_title"] == "Épisode 4"
    assert service.history["u1"]["Sousou No Frieren"]["episodes"]["Saison 1:4"]["ep_title"] == "Sousou no Frieren - 04 VOSTFR"
    hqdefault = _proxied("https://i.ytimg.com/vi/qgQkRsJWW3I/hqdefault.jpg")
    assert card["wide_images"] == [f"/api/stream/thumbnail?file_path={quote(local, safe='')}", hqdefault]

    # The AniList cache fills a banner the link does not have (no network)
    [card] = _cards(service, media=lambda title: {"banner": BANNER} if title == "Frieren" else None)
    assert card["wide_images"][1:] == [_proxied(BANNER), hqdefault]

    service.save_progress("u2", "Frieren", "Saison 1", "1", 300, None)
    [card] = _cards(service, "u2")
    assert card["remaining_sec"] is None and card["progress_percent"] == 0

    names = {"frieren", "sousou no frieren"}
    assert history_module._episode_title("Le départ", "1", names) == "Le départ"
    assert history_module._episode_title("Épisode 7", "7", names) == "Épisode 7"
    assert history_module._episode_title("Épisode 7 VF", "7", names) == "Épisode 7"
    assert history_module._episode_title("", "8", names) == "Épisode 8"
    # Episode 0 (num 0): clients use the raw title as its id
    raw = "Sousou no Frieren - 00 VOSTFR"
    assert history_module._episode_title(raw, raw, names) == "Épisode 0"
    assert history_module._episode_title("", "Sousou no Frieren - 12 vf", names) == "Épisode 12"
    assert history_module._episode_title("Sousou no Frieren Special", "Sousou no Frieren Special", names) == "Épisode spécial"
    assert history_module._episode_title("Le départ", "Le départ", names) == "Le départ"

    service.save_progress("u3", "Sousou No Frieren", "Saison 1", raw, 300, 1400, context={"ep_title": raw})
    [card] = _cards(service, "u3")
    assert card["episode_title"] == "Épisode 0" and card["episode_num"] == raw


def test_season_names_with_colons_use_rpartition(service):
    season = "Original · Saison 1: X"
    service.save_progress("u1", "Hunter X Hunter", season, "3", 300, 1400)
    record = service.history["u1"]["Hunter X Hunter"]
    assert history_module._split_ep_key(f"{season}:3", record) == (season, "3")
    assert history_module._split_ep_key("3", record) == (season, "3")

    record["last_ep_id"] = "99"   # dangling pointer: the last played episode is split back correctly
    [card] = _cards(service)
    assert (card["season"], card["episode_num"]) == (season, "3")


def test_deleting_the_pointer_episode_repoints_it(service):
    service.save_progress("u1", "Frieren", "Saison 1", "1", 300, 1400)
    service.save_progress("u1", "Frieren", "Saison 1", "2", 300, 1400)
    service.toggle_watched("u1", "Frieren", "Saison 1", "5", True)
    updated = service.history["u1"]["Frieren"]["last_updated"]

    service.delete_item("u1", "Frieren", "Saison 1:2")
    record = service.history["u1"]["Frieren"]
    assert (record["last_season"], record["last_ep_id"], record["last_updated"]) == ("Saison 1", "1", updated)
    assert _cards(service)[0]["episode_num"] == "1"

    # Nothing played is left: the pointer stays, no card
    service.delete_item("u1", "Frieren", "Saison 1:1")
    assert (record["last_season"], record["last_ep_id"]) == ("Saison 1", "1")
    assert _cards(service) == []


def test_link_titles_needs_title_and_season_evidence_and_maps_seasons(service):
    va_ep = "https://voir-anime.to/anime/sousou-no-frieren-2/sousou-no-frieren-2-02-vostfr/"
    service.save_progress("u1", "Sousou No Frieren 2", "Saison 1", "2", 300, 1400, embed_url=va_ep)
    service.save_progress("u1", "Frieren", "Film", "1", 300, 1400)
    ref, claims = YoitsuGateway.anime_ref(FRIEREN_DETAILS), YoitsuGateway.history_claims(FRIEREN_DETAILS)

    assert service.link_titles("u1", ref, claims) == 1
    record = service.history["u1"]["Sousou No Frieren 2"]
    assert record["anime"]["id"] == "a-frieren" and record["anime"]["by"] == "details"
    assert record["anime"]["banner"] == "https://s4.anilist.co/b.jpg"
    assert record["seasons"]["Saison 1"] == {"key": "saison-2", "source": "voiranime", "version": "vostfr", "by": "details"}
    assert "anime" not in service.history["u1"]["Frieren"], "a title without season evidence is never linked"
    assert service.link_titles("u1", ref, claims) == 0

    hxh_as, hxh_va = "https://anime-sama.to/catalogue/hunter-x-hunter", "https://voir-anime.to/anime/hunter-x-hunter/"
    hxh = {"id": "a-hunter-x-hunter", "title": "Hunter x Hunter", "source": "anime_sama", "url": hxh_as,
           "sources": [{"source": "anime_sama", "url": hxh_as, "title": "Hunter x Hunter"}], "seasons": [
               {"key": "saison-1", "is_scans": False, "variants": [
                   {"source": "anime_sama", "version": "vostfr", "history_keys": [{"title": "Hunter x Hunter", "season": "Saison 1"}]}]},
               {"key": "original-saison-1", "is_scans": False, "variants": [
                   {"source": "voiranime", "version": "vostfr", "history_keys": [
                       {"title": "Hunter X Hunter", "season": "Original · Saison 1"}, {"title": "Hunter X Hunter", "season": "Saison 1"}]}]},
           ]}
    hxh_ref, hxh_claims = YoitsuGateway.anime_ref(hxh), YoitsuGateway.history_claims(hxh)
    va_episode = f"{hxh_va}hunter-x-hunter-02-vostfr/"

    # Mixed hosts in one season: the anime is linked, the season stays unmapped
    service.save_progress("u2", "Hunter X Hunter", "Saison 1", "1", 300, 1400, embed_url="https://vidmoly.net/e1")
    service.save_progress("u2", "Hunter X Hunter", "Saison 1", "2", 300, 1400, embed_url=va_episode)
    service.link_titles("u2", hxh_ref, hxh_claims)
    record = service.history["u2"]["Hunter X Hunter"]
    assert record["anime"]["id"] == "a-hunter-x-hunter" and not record.get("seasons")

    # VoirAnime hosts only: the VoirAnime original
    service.save_progress("u3", "Hunter X Hunter", "Saison 1", "2", 300, 1400, embed_url=va_episode)
    service.link_titles("u3", hxh_ref, hxh_claims)
    assert service.history["u3"]["Hunter X Hunter"]["seasons"]["Saison 1"]["key"] == "original-saison-1"


def test_link_precedence(service):
    clean = service._clean_ref
    bocchi = {"id": "a-bocchi", "title": "Bocchi", "source": "voiranime", "url": "https://voir-anime.to/anime/bocchi/"}
    record = {"episodes": {}}

    assert service._link(record, clean(bocchi), "index")
    assert service._link(record, clean(FRIEREN), "details")
    assert record["anime"]["id"] == "a-frieren" and record["anime"]["by"] == "details"
    assert not service._link(record, clean(bocchi), "details")
    record["anime"]["by"] = "write"
    assert not service._link(record, clean(bocchi), "details")
    record["seasons"] = {"Saison 1": {"key": "saison-1", "source": "anime_sama", "version": "vostfr", "by": "write"}}
    assert service._link(record, clean(bocchi), "write")
    assert record["anime"]["id"] == "a-bocchi" and record["seasons"] == {}

    # Same entity through the canonical id: merged, id healed, old banner and higher provenance kept
    record = {"episodes": {}}
    service._link(record, clean({**SOUSOU, "banner": BANNER}), "write")
    plain = {"id": "a-frieren", "title": "Frieren", "source": "anime_sama", "url": AS_URL}
    assert not service._link(record, clean(plain), "details"), "another entity without the alias"
    assert service._link(record, clean(plain), "details", canon)
    assert (record["anime"]["id"], record["anime"]["by"], record["anime"]["banner"]) == ("a-frieren", "write", BANNER)
    assert not service._link(record, clean(plain), "details", canon), "unchanged: nothing to save"
    # Same primary source entry under an id the resolver does not know
    assert service._link(record, clean({**plain, "id": "a-frieren-2"}), "details")
    assert record["anime"]["id"] == "a-frieren-2" and record["anime"]["by"] == "write"

    service.save_progress("u1", "Frieren", "Saison 1", "1", 300, 1400, anime=FRIEREN, context=S1)
    service.save_progress("u1", "Bocchi", "Saison 1", "1", 300, 1400)
    assert service.apply_links("u1", {"Frieren": bocchi, "Bocchi": bocchi, "Missing": bocchi}) == 1
    assert service.history["u1"]["Frieren"]["anime"]["id"] == "a-frieren"
    assert service.history["u1"]["Bocchi"]["anime"]["by"] == "index"
    assert service.apply_links("u1", {"Bocchi": bocchi}) == 0

    # A context handed out by /history/resume ranks as details, not as a user write
    service.save_progress("u2", "Frieren", "Saison 1", "1", 300, 1400, anime=FRIEREN, context=S1, link_by="details")
    record = service.history["u2"]["Frieren"]
    assert record["anime"]["by"] == "details" and record["seasons"]["Saison 1"]["by"] == "details"
    service.save_progress("u3", "Frieren", "Saison 1", "1", 300, 1400, anime=FRIEREN, context=S1)
    service.save_progress("u3", "Frieren", "Saison 1", "2", 300, 1400, anime=FRIEREN, context={**S1, "source": "voiranime"},
                          link_by="details")
    record = service.history["u3"]["Frieren"]
    assert record["seasons"]["Saison 1"]["source"] == "anime_sama"

    # A details mapping never overrides a write mapping whose season still exists, and does once it vanished
    target = {"key": "saison-1", "source": "voiranime", "version": "vostfr"}
    assert not service._map_season(record, "Saison 1", target, "details", live_keys={"saison-1"})
    record["seasons"]["Saison 1"]["key"] = "saison-1-old"
    assert service._map_season(record, "Saison 1", target, "details", live_keys={"saison-1"})
    assert record["seasons"]["Saison 1"] == {**target, "by": "details"}


def test_details_of_a_homonymous_page_never_rewrite_a_link_under_the_same_id(service):
    sk21, sk = "https://anime-sama.to/catalogue/shaman-king-2021", "https://anime-sama.to/catalogue/shaman-king"
    stored = {"id": "a-shaman-king", "title": "Shaman King", "source": "anime_sama", "url": sk21, "entry_title": "Shaman King"}
    service.save_progress("u1", "Shaman King", "Saison 1", "2", 300, 1400, anime=stored, context=S1)
    # The 2001 page (shorter slug) took the plain key: its details carry the same id
    details = {"id": "a-shaman-king", "title": "Shaman King", "source": "anime_sama", "url": sk,
               "sources": [{"source": "anime_sama", "url": sk, "title": "Shaman King"}],
               "seasons": [{"key": "saison-1", "is_scans": False, "variants": [
                   {"source": "anime_sama", "version": "vostfr", "history_keys": [{"title": "Shaman King", "season": "Saison 1"}]},
                   {"source": "anime_sama", "version": "vf", "history_keys": [{"title": "Shaman King", "season": "Saison 1 VF"}]}]}]}
    ref, claims = YoitsuGateway.anime_ref(details), YoitsuGateway.history_claims(details)
    record = service.history["u1"]["Shaman King"]
    before = json.loads(json.dumps(record))

    assert service.link_titles("u1", ref, claims, idents={"anime_sama:shaman-king"}) == 0
    assert record == before
    record["anime"]["by"] = "index"
    assert service.link_titles("u1", ref, claims, idents={"anime_sama:shaman-king"}) == 1, "an index link is replaced"
    assert record["anime"]["url"] == sk and record["seasons"] == {"Saison 1": {**before["seasons"]["Saison 1"], "by": "details"}}

    # Its own entity's details (the stored page among its entries) still heal the link
    service.save_progress("u2", "Shaman King", "Saison 1", "2", 300, 1400, anime=stored)
    own = {**details, "url": sk21, "sources": [{"source": "anime_sama", "url": sk21, "title": "Shaman King"}]}
    assert service.link_titles("u2", YoitsuGateway.anime_ref(own), YoitsuGateway.history_claims(own),
                               idents={"anime_sama:shaman-king-2021"}) == 1
    healed = service.history["u2"]["Shaman King"]
    assert healed["anime"]["by"] == "write" and healed["seasons"]["Saison 1"]["key"] == "saison-1"
    # No idents (write paths): an equal id is still the same anime
    assert service._link({"anime": {**stored, "by": "write"}}, service._clean_ref({**stored, "url": sk}), "details")


def test_relabel_drops_the_season_mapping(service):
    service.save_progress("u1", "Mob Psycho 100 Ii", "Saison 1", "3", 300, 1400,
                          anime={"id": "a-mob-psycho-100-ii", "title": "Mob Psycho 100 II", "source": "voiranime",
                                 "url": "https://voir-anime.to/anime/mob-psycho-100-ii/"},
                          context={"season_key": "saison-1", "source": "voiranime", "version": "vostfr"})
    record = service.history["u1"]["Mob Psycho 100 Ii"]
    assert not service.relabel("u1", "Mob Psycho 100 Ii", "a-mob-psycho-100-ii")
    assert record["seasons"]["Saison 1"]["key"] == "saison-1"
    assert service.relabel("u1", "Mob Psycho 100 Ii", "a-mob-psycho-100")
    assert record["anime"]["id"] == "a-mob-psycho-100" and record["anime"]["by"] == "write" and record["seasons"] == {}


def test_unlinked_titles_retry_after_link_retry_and_carry_voiranime_urls(service, clock):
    for n in range(1, 8):
        service.save_progress("u1", "Sousou No Frieren", "Saison 1", str(n), 300, 1400,
                              embed_url=f"{VA_S1}sousou-no-frieren-0{n}-vostfr/", cover="https://voir-anime.to/f.jpg")
    service.save_progress("u1", "Sousou No Frieren", "Saison 2", "1", 300, 1400, embed_url="https://vidmoly.net/e1")
    service.save_progress("u1", "Frieren", "Saison 1", "1", 300, 1400, anime=FRIEREN)

    [(title, cover, urls)] = service.unlinked_titles("u1")
    assert (title, cover) == ("Sousou No Frieren", "https://voir-anime.to/f.jpg")
    assert len(urls) == 5 and all(u.startswith(VA_S1) for u in urls)
    assert service.unlinked_titles("u1") == [], "tried titles wait LINK_RETRY"

    clock[0] += history_module.LINK_RETRY + 1
    assert [t for t, _, _ in service.unlinked_titles("u1")] == ["Sousou No Frieren"]


def test_unparsable_urls_are_never_stored_nor_crash_a_read(service):
    bad = "https://[bad"
    service.save_progress("u1", "Bocchi", "Saison 1", "1", 300, 1400, cover=bad, embed_url=bad,
                          anime={"id": "a-bocchi", "title": "Bocchi", "banner": bad})
    record = service.history["u1"]["Bocchi"]
    assert record["cover"] == "" and record["anime"]["banner"] is None
    [card] = _cards(service)
    assert card["cover"] == "" and card["anime"]["wide_images"] == []

    # Values stored by an older build are read as missing
    record["cover"] = bad
    record["anime"]["banner"] = bad
    assert service.get_history_for_client("u1")["Bocchi"]["cover"] == "" and _cards(service)[0]["cover"] == ""
    service.save_progress("u2", "Bocchi", "Saison 1", "1", 300, 1400, embed_url=bad)
    assert service.unlinked_titles("u2") == [("Bocchi", "", [])]


def test_stats_count_anime_groups_not_title_records(service):
    for n in range(1, 8):
        service.toggle_watched("u1", "Frieren", "Saison 1", str(n), True, anime=FRIEREN)
    for n in range(1, 7):
        service.toggle_watched("u1", "Sousou No Frieren", "Saison 1", str(n), True, anime={**SOUSOU, "url": VA_S1})
    service.save_progress("u1", "Bocchi", "Saison 1", "1", 300, 1400)

    stats = service.get_user_stats("u1", canonical=canon)
    assert (stats["total_animes_started"], stats["animes_completed"], stats["animes_in_progress"]) == (2, 1, 1)
    assert stats["total_episodes_watched"] == 13
    assert stats["total_seconds_watched"] == 13 * 1440 + 300
    legacy = service.get_user_stats("u1")
    assert (legacy["total_animes_started"], legacy["animes_completed"]) == (3, 0)


def test_flush_is_debounced_ordered_and_written_on_close(monkeypatch, tmp_path):
    path = tmp_path / "history.json"
    monkeypatch.setattr(history_module, "HISTORY_FILE", str(path))
    monkeypatch.setattr(history_module, "HISTORY_FLUSH_DELAY", 0.05)

    async def scenario():
        service = HistoryService()
        service.save_progress("u1", "Frieren", "Saison 1", "1", 100, 1400)
        service.save_progress("u1", "Frieren", "Saison 1", "2", 200, 1400)
        assert not path.exists(), "writes wait for the debounce window"
        await asyncio.sleep(0.2)
        await _until(lambda: path.exists())
        assert set(_stored(path)["u1"]["Frieren"]["episodes"]) == {"Saison 1:1", "Saison 1:2"}

        # A change during the write opens a new window
        monkeypatch.setattr(history_module, "HISTORY_FLUSH_DELAY", 60.0)
        real_write = service._write
        changed = []

        def write_then_change(text, seq):
            real_write(text, seq)
            if not changed:
                changed.append(seq)
                service._dirty = True

        monkeypatch.setattr(service, "_write", write_then_change)
        written = service._written_seq
        service.save_progress("u1", "Frieren", "Saison 1", "3", 300, 1400)
        service._save(immediate=True)
        await _until(lambda: service._written_seq > written and service._flush_pending)
        assert service._flush_task is not None and not service._flush_task.done()

        # A pending change is written at shutdown
        service.save_progress("u1", "Frieren", "Saison 1", "4", 400, 1400)
        await service.close()
        assert "Saison 1:4" in _stored(path)["u1"]["Frieren"]["episodes"]
        assert not service._flush_pending

    asyncio.run(scenario())

    # An older snapshot never replaces a newer one
    service = HistoryService()
    service._write(json.dumps({"new": True}), 2)
    service._write(json.dumps({"old": True}), 1)
    assert _stored(path) == {"new": True}

    # Outside a loop (scripts, unit tests), a save writes immediately
    other = tmp_path / "other.json"
    monkeypatch.setattr(history_module, "HISTORY_FILE", str(other))
    HistoryService().save_progress("u1", "Bocchi", "Saison 1", "1", 30, 1400)
    assert "Bocchi" in _stored(other)["u1"]


def test_close_writes_only_a_pending_change_and_waits_for_a_running_write(monkeypatch, tmp_path):
    path = tmp_path / "history.json"
    monkeypatch.setattr(history_module, "HISTORY_FILE", str(path))
    path.write_text(json.dumps({"u1": {}}), encoding="utf-8")

    # Nothing changed (or a file that could not be read and was loaded as {}): the file and its .bak stay as they are
    asyncio.run(HistoryService().close())
    assert _stored(path) == {"u1": {}} and not (tmp_path / "history.json.bak").exists()

    # A write already running in a worker thread (another loop's task) lands before close() returns
    service = HistoryService()
    landed = []
    service._write_lock.acquire()

    def finish_write():
        time.sleep(0.2)
        landed.append(True)
        service._write_lock.release()

    worker = threading.Thread(target=finish_write)
    worker.start()
    asyncio.run(service.close())
    assert landed == [True]
    worker.join()


def test_a_flush_left_in_a_closed_loop_is_rescheduled(monkeypatch, tmp_path):
    path = tmp_path / "history.json"
    monkeypatch.setattr(history_module, "HISTORY_FILE", str(path))
    monkeypatch.setattr(history_module, "HISTORY_FLUSH_DELAY", 60.0)
    service = HistoryService()

    async def save(ep_id):
        service.save_progress("u1", "Frieren", "Saison 1", ep_id, 100, 1400)

    # TestClient: the request loop closes before the window ends and cancels the sleeping task
    asyncio.run(save("1"))
    assert service._flush_pending and not path.exists()

    async def save_and_wait():
        monkeypatch.setattr(history_module, "HISTORY_FLUSH_DELAY", 0.01)
        await save("2")
        await asyncio.wait_for(service._flush_task, timeout=5)

    asyncio.run(save_and_wait())
    assert set(_stored(path)["u1"]["Frieren"]["episodes"]) == {"Saison 1:1", "Saison 1:2"}


def test_delete_user_data_and_clear_flush_promptly(monkeypatch, tmp_path):
    path = tmp_path / "history.json"
    monkeypatch.setattr(history_module, "HISTORY_FILE", str(path))
    service = HistoryService()
    service.save_progress("u1", "Frieren", "Saison 1", "1", 100, 1400)   # no loop: written now
    service.save_progress("u2", "Frieren", "Saison 1", "1", 100, 1400)
    service._link_tried[("u1", "Frieren")] = 1.0
    monkeypatch.setattr(history_module, "HISTORY_FLUSH_DELAY", 60.0)

    async def scenario():
        service.save_progress("u1", "Frieren", "Saison 1", "2", 200, 1400)   # a 60 s window is pending
        debounced = service._flush_task
        service.delete_user_data("u1")
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert debounced.cancelled() or debounced.cancelling()
        await asyncio.wait_for(service._flush_task, timeout=5)
        assert "u1" not in _stored(path) and "u2" in _stored(path)
        assert ("u1", "Frieren") not in service._link_tried

        service.save_progress("u2", "Frieren", "Saison 1", "2", 200, 1400)
        service.clear_user_history("u2")
        await asyncio.wait_for(service._flush_task, timeout=5)
        assert _stored(path)["u2"] == {}

    asyncio.run(scenario())


def test_augmented_file_loads_unchanged_and_flat_legacy_still_wraps(monkeypatch, tmp_path):
    path = tmp_path / "history.json"
    monkeypatch.setattr(history_module, "HISTORY_FILE", str(path))
    augmented = {"user_1a2b3c4d": {"Sousou No Frieren": {
        "anime_title": "Sousou No Frieren", "cover": "https://voir-anime.to/wp-content/uploads/f.jpg",
        "last_season": "Saison 1", "last_ep_id": "4", "last_updated": 1761420000.5,
        "anime": {**FRIEREN, "by": "write", "at": 1761420000.5},
        "seasons": {"Saison 1": {"key": "saison-1", "source": "voiranime", "version": "vostfr", "by": "details"}},
        "episodes": {
            "Saison 1:3": {"position_sec": 1398.0, "duration_sec": 1420.0, "last_watched_at": 1761419000.0, "watched": True,
                           "played_at": 1761419000.0, "watched_at": 1761419010.0, "ep_title": "Sousou no Frieren - 03 VOSTFR",
                           "next": {"ep_id": "4", "title": "Sousou no Frieren - 04 VOSTFR"}},
            "Saison 1:4": {"position_sec": 610.2, "duration_sec": 1420.0, "last_watched_at": 1761420000.5, "played_at": 1761420000.5},
        },
    }}}
    path.write_text(json.dumps(augmented), encoding="utf-8")
    service = HistoryService()
    assert service.history == augmented
    [card] = service.get_continue_watching("user_1a2b3c4d")
    assert (card["episode_num"], card["season_key"], card["source"]) == ("4", "saison-1", "voiranime")

    flat = {"Frieren": {"anime_title": "Frieren", "last_season": "Saison 1", "last_ep_id": "1", "last_updated": 1.0,
                        "episodes": {"Saison 1:1": {"position_sec": 10.0, "duration_sec": 1400.0, "last_watched_at": 1.0}}}}
    path.write_text(json.dumps(flat), encoding="utf-8")
    assert HistoryService().history == {"default": flat}
