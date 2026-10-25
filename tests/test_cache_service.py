from backend.services import cache_service as cache_module
from backend.services.cache_service import CacheService, anime_identity
from backend.services.storage import save_json


def _service(tmp_path, monkeypatch):
    anime_dir = tmp_path / "animes"
    anime_dir.mkdir()
    monkeypatch.setattr(cache_module, "ANIME_CACHE_DIR", str(anime_dir))
    monkeypatch.setattr(cache_module, "RECENT_FILE", str(tmp_path / "recent.json"))
    return CacheService(), anime_dir


def test_random_pool_survives_episode_list_files_and_dedups_by_slug(tmp_path, monkeypatch):
    service, anime_dir = _service(tmp_path, monkeypatch)
    # Episode caches hold a list: the old loop stopped at the first one
    save_json(str(anime_dir / "anime_sama_eps_as_eps_x.json"), {"_cached_at": 0, "content": [{"num": 1}]})
    save_json(str(anime_dir / "anime_sama_anime_sama_snk.json"), {"_cached_at": 0, "content": {
        "title": "Shingeki no Kyojin", "url": "https://anime-sama.si/catalogue/shingeki-no-kyojin", "source": "anime_sama", "cover": ""
    }})
    save_json(str(anime_dir / "voiranime_voiranime_bocchi.json"), {"_cached_at": 0, "content": {
        "title": "Bocchi the Rock!", "url": "https://voir-anime.to/anime/bocchi-the-rock/", "source": "voiranime", "cover": ""
    }})
    (anime_dir / "broken.json").write_text("{not json", encoding="utf-8")

    titles = [a["title"] for a in service.get_random_animes(count=50)]
    assert "Bocchi the Rock!" in titles
    # Same AS slug as the starter "L'Attaque des Titans": only one of them is kept
    assert ("Shingeki no Kyojin" in titles) != ("L'Attaque des Titans" in titles)


def test_recents_store_raw_cover_and_never_placeholders(tmp_path, monkeypatch):
    service, _ = _service(tmp_path, monkeypatch)
    service.add_recent_anime("u1", {"title": "A", "url": "https://voir-anime.to/anime/a/", "source": "voiranime",
                                    "cover": "/api/proxy/image?url=https%3A%2F%2Fvoir-anime.to%2Fa.jpg"})
    service.add_recent_anime("u1", {"title": "B", "url": "https://voir-anime.to/anime/b/", "source": "voiranime",
                                    "cover": "data:image/svg+xml;charset=utf-8,x"})

    stored = {a["title"]: a["cover"] for a in service.recent_data["u1"]}
    assert stored == {"A": "https://voir-anime.to/a.jpg", "B": ""}
    client = {a["title"]: a["cover"] for a in service.get_recent_animes("u1")}
    assert client["A"].startswith("/api/img?url=")
    assert [a["title"] for a in service.recents_missing_cover("u1")] == ["B"]

    service.set_recent_cover("u1", "voiranime", "https://voir-anime.to/anime/b/", "B", "https://voir-anime.to/b.jpg")
    assert service.recents_missing_cover("u1") == []


def test_recents_dedup_same_entry_with_another_title(tmp_path, monkeypatch):
    service, _ = _service(tmp_path, monkeypatch)
    service.add_recent_anime("u1", {"title": "Sousou No Frieren 2", "url": "https://voir-anime.to/anime/sousou-no-frieren-2/", "source": "voiranime"})
    service.add_recent_anime("u1", {"title": "Sousou no Frieren 2", "url": "https://voir-anime.to/anime/sousou-no-frieren-2", "source": "voiranime"})
    assert len(service.recent_data["u1"]) == 1


def test_anime_identity_ignores_domain_and_trailing_slash():
    assert anime_identity("anime_sama", "https://anime-sama.to/catalogue/frieren/") == anime_identity("anime_sama", "https://anime-sama.si/catalogue/frieren")


def test_discover_still_works_when_the_cache_folder_disappears(tmp_path, monkeypatch):
    service, anime_dir = _service(tmp_path, monkeypatch)
    anime_dir.rmdir()
    assert service.get_random_animes(count=5)


def test_voiranime_recent_with_legacy_anime_sama_art_is_repaired(tmp_path, monkeypatch):
    service, _ = _service(tmp_path, monkeypatch)
    service.add_recent_anime("u1", {"title": "One Piece Film Red", "url": "https://voir-anime.to/anime/one-piece-film-red/",
                                    "source": "voiranime", "cover": "https://raw.githubusercontent.com/Anime-Sama/IMG/img/contenu/one-piece.jpg"})
    assert [a["title"] for a in service.recents_missing_cover("u1")] == ["One Piece Film Red"]
    assert service.get_recent_animes("u1")[0]["cover"] == ""
