import asyncio

import httpx

from backend.yoitsu import anilist as anilist_module
from backend.yoitsu.anilist import AniListClient, accepts, pick_media
from backend.yoitsu.gateway import learnable_keys

FRIEREN = {"romaji": "Sousou no Frieren", "english": "Frieren: Beyond Journey’s End",
           "synonyms": ["Frieren at the Funeral", "장송의 프리렌"]}
SNK_FINAL = {"romaji": "Shingeki no Kyojin: The Final Season", "english": "Attack on Titan Final Season",
             "synonyms": ["SnK 4", "L'Attaque des Titans Saison Finale"]}
SHIPPUDEN = {"romaji": "Naruto: Shippuuden", "english": "Naruto Shippuden", "synonyms": []}


def test_accept_rule_matches_names_not_just_search_rank():
    assert accepts("Frieren", FRIEREN)                      # English title minus subtitle
    assert accepts("Sousou no Frieren", FRIEREN)
    assert accepts("L'Attaque des Titans", SNK_FINAL)       # French synonym minus "Saison Finale"
    assert not accepts("Bocchi the Rock!", FRIEREN)


def test_learned_aliases_never_use_subtitle_roots():
    assert "naruto" not in learnable_keys([SHIPPUDEN["romaji"], SHIPPUDEN["english"]])
    keys = learnable_keys([SNK_FINAL["romaji"], SNK_FINAL["english"], *SNK_FINAL["synonyms"]])
    assert {"shingeki no kyojin", "attack on titan", "l attaque des titans"} <= keys


def test_exact_name_beats_a_subtitle_match():
    picked = pick_media("Naruto", [_raw("Naruto: Shippuuden", "Naruto Shippuden", [], 1735), _raw("Naruto", "Naruto", [], 20)])
    assert picked["id"] == 20


def _raw(romaji, english, synonyms, media_id=1):
    return {"id": media_id, "title": {"romaji": romaji, "english": english, "native": None}, "synonyms": synonyms,
            "description": "Story.<br>More", "coverImage": {"extraLarge": "https://s4.anilist.co/c.jpg", "color": "#123"},
            "bannerImage": "https://s4.anilist.co/b.jpg", "trailer": {"id": "abc", "site": "youtube"}}


def _client(tmp_path, monkeypatch, handler):
    monkeypatch.setattr(anilist_module, "MIN_INTERVAL", 0.0)
    client = AniListClient(str(tmp_path / "anilist.json"), enabled=True)
    client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return client


def test_lookup_caches_hits_and_misses(tmp_path, monkeypatch):
    calls = []

    def handler(request):
        calls.append(request)
        media = [_raw("Bocchi the Rock!", None, []), _raw("Sousou no Frieren", "Frieren: Beyond Journey’s End", [], 154587)]
        return httpx.Response(200, json={"data": {"Page": {"media": media}}})

    client = _client(tmp_path, monkeypatch, handler)

    async def scenario():
        hit = await client.lookup("Frieren")
        again = await client.lookup("Frieren")
        miss = await client.lookup("Unknown show")
        miss_again = await client.lookup("Unknown show")
        return hit, again, miss, miss_again

    hit, again, miss, miss_again = asyncio.run(scenario())
    assert hit["id"] == 154587 and hit is not None and again["id"] == 154587
    assert hit["description"] == "Story.\nMore"
    assert miss is None and miss_again is None
    assert len(calls) == 2
    client.flush()
    assert AniListClient(str(tmp_path / "anilist.json"), enabled=True).cached("Frieren")["banner"].endswith("b.jpg")


def test_rate_limited_answers_are_not_cached(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch, lambda request: httpx.Response(429, headers={"retry-after": "0"}))
    assert asyncio.run(client.lookup("Frieren")) is None
    assert not client.has("Frieren")


def test_disabled_client_never_calls_out(tmp_path):
    client = AniListClient(str(tmp_path / "anilist.json"), enabled=False)
    assert asyncio.run(client.lookup("Frieren")) is None
