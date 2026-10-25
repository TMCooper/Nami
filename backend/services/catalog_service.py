import os
import sys
import json
import re
import asyncio
import httpx
from typing import Optional, List, Dict
from backend.services.cache_service import cache_service

AS_API_BASE = "http://127.0.0.1:5000"
VA_API_BASE = "http://127.0.0.1:8000"

class CatalogService:
    def __init__(self):
        self.client = httpx.AsyncClient(timeout=30.0)
        self._is_updating = False
        self._update_message = "Catalogue au repos"

    async def get_update_status(self) -> dict:
        if self._is_updating:
            return {"is_updating": True, "message": self._update_message, "source": "all"}

        try:
            resp = await self.client.get(f"{VA_API_BASE}/catalog/status", timeout=3.0)
            if resp.status_code == 200:
                va_status = resp.json()
                if va_status.get("is_updating"):
                    return {
                        "is_updating": True,
                        "message": f"Mise à jour VoirAnime (Page {va_status.get('current_page', '?')})...",
                        "source": "voiranime"
                    }
        except Exception:
            pass
        return {"is_updating": False, "message": "Catalogue au repos", "source": None}

    async def trigger_update(self, source: str = "all") -> dict:
        if self._is_updating:
            return {"is_updating": True, "message": self._update_message}

        self._is_updating = True
        self._update_message = "Mise à jour démarrée..."
        asyncio.create_task(self._run_update(source))
        return {"is_updating": True, "message": "Mise à jour du catalogue démarrée en arrière-plan."}

    async def _run_update(self, source: str):
        try:
            if source in ["all", "anime_sama"]:
                self._update_message = "Mise à jour Anime-Sama en cours..."
                try:
                    await self.client.get(f"{AS_API_BASE}/api/getAllAnime?r=True", timeout=300.0)
                except Exception as e:
                    print(f"[CatalogService] AnimeSama update error: {e}")

            if source in ["all", "voiranime"]:
                self._update_message = "Mise à jour VoirAnime en cours..."
                try:
                    await self.client.get(f"{VA_API_BASE}/catalog/update", timeout=300.0)
                except Exception as e:
                    print(f"[CatalogService] VoirAnime update error: {e}")

            self._update_message = "Catalogue à jour !"
        except Exception as e:
            self._update_message = f"Erreur: {e}"
        finally:
            self._is_updating = False

    async def search(self, query: str = "", source: str = "all") -> list:
        results = []
        tasks = []

        if source in ["all", "anime_sama"]:
            tasks.append(self._search_anime_sama(query))
        if source in ["all", "voiranime"]:
            tasks.append(self._search_voiranime(query))

        if tasks:
            res_list = await asyncio.gather(*tasks, return_exceptions=True)
            for res in res_list:
                if isinstance(res, list):
                    results.extend(res)

        # Fallback to starter/popular recommendations if search is empty and no results found
        if not results and not query.strip():
            return cache_service.get_random_animes(count=24)

        return results

    async def _search_anime_sama(self, query: str = "") -> list:
        results = []
        q_clean = query.strip()
        try:
            if q_clean:
                resp = await self.client.get(f"{AS_API_BASE}/api/getSerchAnime", params={"q": q_clean})
                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data, list):
                        for item in data:
                            title = item.get("title", "")
                            link = item.get("lien", item.get("link", ""))
                            cover = item.get("cover", "")
                            if not cover:
                                slug = link.rstrip("/").split("/")[-1]
                                cover = f"https://cdn.statically.io/gh/Anime-Sama/IMG/img/contenu/{slug}.jpg"
                            if title and link:
                                results.append({
                                    "id": f"as:{link}",
                                    "title": title,
                                    "source": "anime_sama",
                                    "url": link,
                                    "cover": cover
                                })
            else:
                resp = await self.client.get(f"{AS_API_BASE}/api/loadBaseAnimeData")
                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data, list):
                        for item in data[:300]:
                            title = item.get("title", "")
                            link = item.get("link", "")
                            slug = link.rstrip("/").split("/")[-1]
                            cover = f"https://cdn.statically.io/gh/Anime-Sama/IMG/img/contenu/{slug}.jpg"
                            if title and link:
                                results.append({
                                    "id": f"as:{link}",
                                    "title": title,
                                    "source": "anime_sama",
                                    "url": link,
                                    "cover": cover
                                })
        except Exception as e:
            print(f"[CatalogService] Error querying AnimeSama API: {e}")

        return results

    async def _search_voiranime(self, query: str = "") -> list:
        results = []
        q_clean = query.strip()
        try:
            if q_clean:
                resp = await self.client.get(f"{VA_API_BASE}/anime/search", params={"query": q_clean})
                if resp.status_code == 200:
                    data = resp.json()
                    matches = data.get("results", data) if isinstance(data, dict) else data
                    if isinstance(matches, list):
                        for item in matches:
                            name = item.get("name", item.get("title", ""))
                            url = item.get("url", "")
                            if name and url:
                                results.append({
                                    "id": f"va:{url}",
                                    "title": name,
                                    "source": "voiranime",
                                    "url": url,
                                    "cover": ""
                                })
            else:
                resp = await self.client.get(f"{VA_API_BASE}/catalog")
                if resp.status_code == 200:
                    data = resp.json()
                    cat_dict = data.get("catalog", data) if isinstance(data, dict) else {}
                    count = 0
                    if isinstance(cat_dict, dict):
                        for name, url in cat_dict.items():
                            results.append({
                                "id": f"va:{url}",
                                "title": name,
                                "source": "voiranime",
                                "url": url,
                                "cover": ""
                            })
                            count += 1
                            if count >= 300:
                                break
        except Exception as e:
            print(f"[CatalogService] Error querying VoirAnime API: {e}")

        return results

    async def get_details(self, url: str, source: str, refresh: bool = False, user_id: str = "default") -> dict:
        cache_key = f"{source}:{url}"
        if not refresh:
            cached = cache_service.get_anime_details(source, cache_key)
            if cached:
                cache_service.add_recent_anime(user_id, cached)
                return cached

        res = {}
        if source == "anime_sama":
            res = await self._get_details_anime_sama(url)
        elif source == "voiranime":
            res = await self._get_details_voiranime(url)

        if res and res.get("title"):
            cache_service.save_anime_details(source, cache_key, res)
            cache_service.add_recent_anime(user_id, res)

        return res

    async def _get_details_anime_sama(self, url: str) -> dict:
        slug = url.rstrip("/").split("/")[-1]
        default_cover = f"https://cdn.statically.io/gh/Anime-Sama/IMG/img/contenu/{slug}.jpg"
        try:
            title = slug.replace("-", " ")
            resp = await self.client.get(f"{AS_API_BASE}/api/getInfoAnime", params={"q": title})
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list) and len(data) > 0:
                    anime_name = data[0].get("title", title)
                    cover = data[0].get("cover", default_cover)
                    seasons = []
                    for item in data:
                        s_name = item.get("Saison", "Saison 1")
                        seasons.append({
                            "name": s_name,
                            "url": item.get("url", url),
                            "raw_link": item.get("url", url)
                        })
                    return {
                        "title": anime_name,
                        "url": url,
                        "cover": cover,
                        "synopsis": "",
                        "source": "anime_sama",
                        "seasons": seasons
                    }
        except Exception as e:
            print(f"[CatalogService] Error fetching AnimeSama details: {e}")

        return {
            "title": slug.title(),
            "url": url,
            "cover": default_cover,
            "source": "anime_sama",
            "seasons": [{"name": "Saison 1", "url": url}]
        }

    async def _get_details_voiranime(self, url: str) -> dict:
        try:
            resp = await self.client.get(f"{VA_API_BASE}/episodes", params={"anime_url": url})
            if resp.status_code == 200:
                data = resp.json()
                episodes = data.get("episodes", [])
                title = url.rstrip("/").split("/")[-1].replace("-", " ").title()
                return {
                    "title": title,
                    "url": url,
                    "cover": "",
                    "synopsis": "",
                    "source": "voiranime",
                    "episodes": episodes
                }
        except Exception as e:
            print(f"[CatalogService] Error fetching VoirAnime details: {e}")

        return {"title": "Anime", "url": url, "source": "voiranime", "episodes": []}

    async def fetch_anime_sama_episodes(self, season_url: str, refresh: bool = False) -> list:
        cache_key = f"as_eps:{season_url}"
        if not refresh:
            cached = cache_service.get_anime_details("anime_sama_eps", cache_key)
            if cached and isinstance(cached, list) and len(cached) > 0:
                return cached

        episodes = []
        try:
            resp = await self.client.get(f"{AS_API_BASE}/api/getAnimeLink", params={"q": season_url}, timeout=30.0)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list):
                    for idx, item in enumerate(data, 1):
                        embed_url = item.get("url", item.get("link", ""))
                        if embed_url:
                            episodes.append({
                                "num": idx,
                                "title": f"Épisode {idx}",
                                "embed_url": embed_url
                            })
                    if episodes:
                        cache_service.save_anime_details("anime_sama_eps", cache_key, episodes)
        except Exception as e:
            print(f"[CatalogService] Error fetching AS season episodes: {e}")
        return episodes

    async def resolve_stream(self, embed_url: str, source: str = "anime_sama") -> dict:
        result = {"stream_url": None, "stream_type": None, "iframe_url": embed_url, "host": None}

        if embed_url.startswith("//"):
            embed_url = "https:" + embed_url

        try:
            resp = await self.client.get(f"{VA_API_BASE}/resolve", params={"embed_url": embed_url})
            if resp.status_code == 200:
                data = resp.json()
                if data.get("status") == "success" and data.get("stream_url"):
                    result["stream_url"] = data["stream_url"]
                    result["stream_type"] = data.get("stream_type", "m3u8")
                    result["host"] = data.get("host")
                    return result
        except Exception:
            pass

        return result

catalog_service = CatalogService()
