import pytest

from backend.yoitsu.normalize import (
    franchise_of, legacy_title_from_url, season_key, split_version, strong_root, subtitle_root, title_variants
)

KNOWN = {"sousou no frieren", "ookami to koushinryou", "steins gate", "hunter x hunter", "naruto"}


def known(root):
    return root in KNOWN


@pytest.mark.parametrize("title,expected_key,season", [
    ("Sousou no Frieren 2", "sousou no frieren", "Saison 2"),
    ("Sousou no Frieren 2nd Season", "sousou no frieren", "Saison 2"),
    ("Shingeki no Kyojin: The Final Season Part 2", "shingeki no kyojin", "Saison finale Partie 2"),
    ("Shingeki no Kyojin Season 3 Part 2", "shingeki no kyojin", "Saison 3 Partie 2"),
    ("L'Attaque des Titans Saison Finale", "l attaque des titans", "Saison finale"),
    ("Ookami to Koushinryou: Merchant Meets the Wise Wolf", "ookami to koushinryou", ""),
    ("Hunter x Hunter (2011)", "hunter x hunter", "Remake 2011"),
])
def test_season_and_subtitle_suffixes_are_stripped(title, expected_key, season):
    key, info = franchise_of(title, known)
    assert key == expected_key
    assert info["season"] == season


@pytest.mark.parametrize("title,expected_key", [
    ("Mob Psycho 100", "mob psycho 100"),          # 3 digits: part of the name
    ("Kaiju No. 8", "kaiju no 8"),                  # root "kaiju no" is not a known franchise
    ("86", "86"),
    ("Naruto Shippuden", "naruto shippuden"),       # no suffix: stays its own franchise
    ("To Be Hero X", "to be hero x"),               # a trailing X is part of the name
    ("Beyblade X", "beyblade x"),
    ("Re:Zero kara Hajimeru Isekai Seikatsu", "re zero kara hajimeru isekai seikatsu"),
])
def test_names_ending_with_numbers_or_colons_are_kept(title, expected_key):
    assert franchise_of(title, known)[0] == expected_key


def test_a_suffix_after_the_subtitle_belongs_to_the_subtitle():
    key, info = franchise_of("Bleach: Thousand-Year Blood War Part 2", lambda root: root == "bleach")
    assert key == "bleach"
    assert info["season"] == "" and info["subtitle"] == "Thousand-Year Blood War Part 2"
    key, info = franchise_of("Mushoku Tensei II: Isekai Ittara Honki Dasu", lambda root: root == "mushoku tensei")
    assert key == "mushoku tensei" and info["season"] == "Saison 2"


def test_weak_suffix_needs_sibling_evidence():
    assert franchise_of("Sousou no Frieren 2")[0] == "sousou no frieren 2"
    assert franchise_of("Sousou no Frieren 2", known)[0] == "sousou no frieren"


def test_version_tags():
    assert split_version("Sousou no Frieren (VF)") == ("Sousou no Frieren", "vf")
    assert split_version("One Piece VOSTFR") == ("One Piece", "vostfr")
    assert split_version("Frieren") == ("Frieren", None)
    assert franchise_of("Sousou no Frieren 2 (VF)", known) == ("sousou no frieren", {"version": "vf", "season": "Saison 2"})


def test_variants_and_roots():
    assert strong_root("frieren beyond journey s end season 2")[0] == "frieren beyond journey s end"
    assert subtitle_root("Frieren: Beyond Journey's End") == "frieren"
    assert subtitle_root("Re:Zero kara Hajimeru") == ""
    assert "frieren" in title_variants("Frieren: Beyond Journey's End")


def test_legacy_title_matches_the_old_voiranime_details_title():
    assert legacy_title_from_url("https://voir-anime.to/anime/sousou-no-frieren-2/") == "Sousou No Frieren 2"


@pytest.mark.parametrize("label,key", [
    ("Saison 1", "saison-1"), ("Season 1", "saison-1"), ("Saison 1 Partie 2", "saison-1-partie-2"),
    ("Film", "film"), ("Movie 2", "film-2"), ("OVA", "oav"), ("Scans", "scans"), ("Remake 2024", "remake-2024"),
])
def test_season_keys_merge_labels_across_sources(label, key):
    assert season_key(label)[0] == key


def test_season_order():
    labels = ["Scans", "Film", "Saison 2", "OAV", "Saison 1", "Saison 1 Partie 2"]
    assert sorted(labels, key=lambda l: season_key(l)[1]) == ["Saison 1", "Saison 1 Partie 2", "Saison 2", "Film", "OAV", "Scans"]
