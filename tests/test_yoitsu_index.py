from backend.yoitsu.aliases import AliasIndex, SEED_GROUPS
from backend.yoitsu.index import Entry, EntityIndex, build_entity, entity_id, key_from_entity_id

AS = "anime_sama"
VA = "voiranime"


def _index(tmp_path, seeds=None):
    aliases = AliasIndex(str(tmp_path / "aliases.json"), SEED_GROUPS if seeds is None else seeds)
    return EntityIndex(aliases, str(tmp_path / "entries.json"))


def test_one_entity_per_anime_across_sources_and_seasons(tmp_path):
    index = _index(tmp_path)
    entities = index.group([
        Entry(AS, "https://anime-sama.to/catalogue/frieren", "Frieren", "https://raw.githubusercontent.com/Anime-Sama/IMG/img/contenu/frieren.jpg"),
        Entry(VA, "https://voir-anime.to/anime/sousou-no-frieren/", "Sousou no Frieren", "https://voir-anime.to/wp-content/uploads/f.jpg"),
        Entry(VA, "https://voir-anime.to/anime/sousou-no-frieren-2/", "Sousou no Frieren 2"),
        Entry(VA, "https://voir-anime.to/anime/sousou-no-frieren-vf/", "Sousou no Frieren (VF)"),
        Entry(VA, "https://voir-anime.to/anime/mob-psycho-100/", "Mob Psycho 100"),
        Entry(VA, "https://voir-anime.to/anime/naruto/", "Naruto"),
        Entry(VA, "https://voir-anime.to/anime/naruto-shippuden/", "Naruto Shippuden"),
    ])
    by_title = {e["title"]: e for e in entities}
    assert set(by_title) == {"Frieren", "Mob Psycho 100", "Naruto", "Naruto Shippuden"}

    frieren = by_title["Frieren"]
    assert [s["source"] for s in frieren["sources"]] == [AS, VA]
    assert frieren["sources"][1]["url"] == "https://voir-anime.to/anime/sousou-no-frieren/"  # VA root post
    assert "Sousou no Frieren" in frieren["alt_titles"]
    assert frieren["cover"].startswith("https://raw.githubusercontent.com/")  # Anime-Sama preferred
    assert frieren["cover_fallbacks"] == ["https://voir-anime.to/wp-content/uploads/f.jpg"]


def test_french_and_japanese_names_merge_through_aliases(tmp_path):
    index = _index(tmp_path)
    entities = index.group([
        Entry(AS, "https://anime-sama.to/catalogue/spice-and-wolf", "Spice and Wolf"),
        Entry(VA, "https://voir-anime.to/anime/ookami-to-koushinryou/", "Ookami to Koushinryou"),
        Entry(VA, "https://voir-anime.to/anime/ookami-to-koushinryou-merchant/", "Ookami to Koushinryou: Merchant Meets the Wise Wolf"),
    ])
    assert len(entities) == 1 and entities[0]["title"] == "Spice and Wolf"


def test_same_source_entry_under_two_titles_is_one_card(tmp_path):
    index = _index(tmp_path)
    entities = index.group([
        Entry(AS, "https://anime-sama.to/catalogue/shingeki-no-kyojin/", "L'Attaque des Titans"),
        Entry(AS, "https://anime-sama.si/catalogue/shingeki-no-kyojin", "Shingeki no Kyojin"),
    ])
    assert len(entities) == 1


def test_learned_aliases_persist_and_old_ids_keep_resolving(tmp_path):
    index = _index(tmp_path, seeds=[])
    assert len(index.group([Entry(AS, "https://a.test/catalogue/x", "Kimetsu no Yaiba"), Entry(VA, "https://v.test/anime/y/", "Demon Slayer")])) == 2
    old_id = entity_id("kimetsu no yaiba")

    index.aliases.union({"kimetsu no yaiba", "demon slayer"})
    index.aliases.flush()
    assert len(index.group([Entry(AS, "https://a.test/catalogue/x", "Kimetsu no Yaiba"), Entry(VA, "https://v.test/anime/y/", "Demon Slayer")])) == 1

    reloaded = AliasIndex(str(tmp_path / "aliases.json"), [])
    assert reloaded.same("kimetsu no yaiba", "demon slayer")
    assert index.aliases.find(key_from_entity_id(old_id)) == "demon slayer"


def test_entries_for_collects_catalogue_and_remembered_entries(tmp_path):
    index = _index(tmp_path)
    index.set_catalog([
        Entry(VA, "https://voir-anime.to/anime/sousou-no-frieren/", "Sousou no Frieren"),
        Entry(VA, "https://voir-anime.to/anime/sousou-no-frieren-2/", "Sousou no Frieren 2"),
        Entry(VA, "https://voir-anime.to/anime/bocchi/", "Bocchi the Rock!"),
    ])
    index.remember([Entry(AS, "https://anime-sama.to/catalogue/frieren", "Frieren")])
    index.flush()
    urls = sorted(e.url for e in index.entries_for("a-frieren"))
    assert urls == ["https://anime-sama.to/catalogue/frieren", "https://voir-anime.to/anime/sousou-no-frieren-2/",
                    "https://voir-anime.to/anime/sousou-no-frieren/"]

    reloaded = EntityIndex(index.aliases, str(tmp_path / "entries.json"))
    assert [e.title for e in reloaded.all_entries()] == ["Frieren"]


def test_two_anime_sama_pages_with_one_title_stay_two_works(tmp_path):
    index = _index(tmp_path, seeds=[])
    entities = index.group([
        Entry(AS, "https://anime-sama.to/catalogue/hunter-x-hunter", "Hunter x Hunter"),
        Entry(AS, "https://anime-sama.to/catalogue/hunter-x-hunter-1999", "Hunter x Hunter"),
        Entry(VA, "https://voir-anime.to/anime/hunter-x-hunter/", "Hunter x Hunter"),
    ])
    assert len(entities) == 2
    main = next(e for e in entities if e["key"] == "hunter x hunter")
    assert {s["url"] for s in main["sources"]} == {"https://anime-sama.to/catalogue/hunter-x-hunter",
                                                   "https://voir-anime.to/anime/hunter-x-hunter/"}


def test_vostfr_post_is_the_entry_point_of_a_source(tmp_path):
    vf = Entry(VA, "https://voir-anime.to/anime/dandadan-vf/", "Dandadan (VF)")
    vostfr = Entry(VA, "https://voir-anime.to/anime/dandadan/", "Dandadan")
    assert build_entity("dandadan", [vf, vostfr])["url"] == vostfr.url


def test_catalogue_title_is_kept_over_a_stripped_search_title(tmp_path):
    index = _index(tmp_path, seeds=[])
    index.set_catalog([Entry(VA, "https://voir-anime.to/anime/re-zero/", "Re:Zero kara Hajimeru Isekai Seikatsu")])
    index.remember([Entry(VA, "https://voir-anime.to/anime/re-zero/", "ReZero kara Hajimeru Isekai Seikatsu")])
    assert [e.title for e in index.all_entries()] == ["Re:Zero kara Hajimeru Isekai Seikatsu"]


def test_entity_id_roundtrip():
    assert key_from_entity_id(entity_id("sousou no frieren")) == "sousou no frieren"
    assert key_from_entity_id(entity_id("進撃の巨人")) == "進撃の巨人"
