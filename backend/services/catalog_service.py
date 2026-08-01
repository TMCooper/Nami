import os
import sys
import json
import asyncio
import httpx

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

AS_API_BASE = "http://127.0.0.1:5000"
VA_API_BASE = "http://127.0.0.1:8000"

class CatalogService:
    def __init__(self):
        self.client = httpx.AsyncClient(timeout=15.0)

    async def get_update_status(self) -> dict:
        try:
            resp = await self.client.get(f"{VA_API_BASE}/catalog/status")
            if resp.status_code == 200:
                va_status = resp.json()
                if va_status.get("is_updating"):
                    return {
                        "is_updating": True,
                        "message": f"Mise à jour VoirAnime (Page {va_status.get('current_page')})...",
                        "source": "voiranime"
                    }
        except Exception:
            pass
        return {"is_updating": False, "message": "Catalogue au repos", "source": None}

    async def trigger_update(self, source: str = "all") -> dict:
        tasks = []
        if source in ["all", "anime_sama"]:
            tasks.append(self._update_anime_sama())
        if source in ["all", "voiranime"]:
            tasks.append(self._update_voiranime())

        if tasks:
            asyncio.create_task(asyncio.gather(*tasks, return_exceptions=True))
        return {"is_updating": True, "message": "Mise à jour du catalogue démarrée en arrière-plan."}

    async def _update_anime_sama(self):
        try:
            print("[CatalogService] Triggering AnimeSama catalog update via http://127.0.0.1:5000/api/getAllAnime?r=True")
            await self.client.get(f"{AS_API_BASE}/api/getAllAnime?r=True", timeout=300.0)
        except Exception as e:
            print(f"[CatalogService] AnimeSama update error: {e}")

    async def _update_voiranime(self):
        try:
            print("[CatalogService] Triggering VoirAnime catalog update via http://127.0.0.1:8000/catalog/update")
            await self.client.get(f"{VA_API_BASE}/catalog/update", timeout=10.0)
        except Exception as e:
            print(f"[CatalogService] VoirAnime update error: {e}")

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
                            if title and link:
                                results.append({
                                    "id": f"as:{link}",
                                    "title": title,
                                    "source": "anime_sama",
                                    "url": link,
                                    "cover": ""
                                })
            else:
                resp = await self.client.get(f"{AS_API_BASE}/api/loadBaseAnimeData")
                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data, list):
                        for item in data[:60]:
                            title = item.get("title", "")
                            link = item.get("link", "")
                            if title and link:
                                results.append({
                                    "id": f"as:{link}",
                                    "title": title,
                                    "source": "anime_sama",
                                    "url": link,
                                    "cover": ""
                                })
        except Exception as e:
            print(f"[CatalogService] Error querying AnimeSama API (5000): {e}")

        return results

    async def _search_voiranime(self, query: str = "") -> list:
        results = []
        q_clean = query.strip()
        try:
            if q_clean:
                resp = await self.client.get(f"{VA_API_BASE}/anime/search", params={"query": q_clean})
                if resp.status_code == 200:
                    data = resp.json()
                    matches = data.get("results", [])
                    for item in matches:
                        results.append({
                            "id": f"va:{item['url']}",
                            "title": item["name"],
                            "source": "voiranime",
                            "url": item["url"],
                            "cover": ""
                        })
            else:
                resp = await self.client.get(f"{VA_API_BASE}/catalog")
                if resp.status_code == 200:
                    data = resp.json()
                    cat_dict = data.get("catalog", {})
                    count = 0
                    for name, url in cat_dict.items():
                        results.append({
                            "id": f"va:{url}",
                            "title": name,
                            "source": "voiranime",
                            "url": url,
                            "cover": ""
                        })
                        count += 1
                        if count >= 60:
                            break
        except Exception as e:
            print(f"[CatalogService] Error querying VoirAnime API (8000): {e}")

        return results

    async def get_details(self, url: str, source: str) -> dict:
        if source == "anime_sama":
            return await self._get_details_anime_sama(url)
        elif source == "voiranime":
            return await self._get_details_voiranime(url)
        return {}

    async def _get_details_anime_sama(self, url: str) -> dict:
        try:
            # Query AnimeSama API getInfoAnime
            title = url.rstrip("/").split("/")[-1].replace("-", " ")
            resp = await self.client.get(f"{AS_API_BASE}/api/getInfoAnime", params={"q": title})
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list) and len(data) > 0:
                    anime_name = data[0].get("title", title)
                    seasons = []
                    for item in data:
                        seasons.append({
                            "name": item.get("Saison", "Saison 1"),
                            "url": item.get("url", url),
                            "raw_link": item.get("url", url)
                        })
                    return {
                        "title": anime_name,
                        "cover": "",
                        "synopsis": "",
                        "source": "anime_sama",
                        "seasons": seasons
                    }
        except Exception as e:
            print(f"[CatalogService] Error fetching AnimeSama details via 5000: {e}")

        return {"title": url.rstrip("/").split("/")[-1], "source": "anime_sama", "seasons": [{"name": "Saison 1", "url": url}]}

    async def _get_details_voiranime(self, url: str) -> dict:
        try:
            resp = await self.client.get(f"{VA_API_BASE}/episodes", params={"anime_url": url})
            if resp.status_code == 200:
                data = resp.json()
                episodes = data.get("episodes", [])
                title = url.rstrip("/").split("/")[-1].replace("-", " ").title()
                return {
                    "title": title,
                    "cover": "",
                    "synopsis": "",
                    "source": "voiranime",
                    "episodes": episodes
                }
        except Exception as e:
            print(f"[CatalogService] Error fetching VoirAnime details via 8000: {e}")

        return {"title": "Anime", "source": "voiranime", "episodes": []}

    async def fetch_anime_sama_episodes(self, season_url: str) -> list:
        episodes = []
        try:
            import cloudscraper
            from bs4 import BeautifulSoup
            scraper = cloudscraper.create_scraper()
            resp = await asyncio.to_thread(scraper.get, season_url, timeout=10)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, 'html.parser')
                scripts = soup.find_all("script")
                for script in scripts:
                    if script.string and "var eps" in script.string:
                        matches = re.findall(r'var\s+eps\d*\s*=\s*\[(.*?)\];', script.string, re.DOTALL)
                        for m in matches:
                            links = [l.strip('"\' ') for l in m.split(',') if l.strip('"\' ')]
                            for idx, link in enumerate(links, 1):
                                episodes.append({
                                    "num": idx,
                                    "title": f"Épisode {idx}",
                                    "embed_url": link
                                })
                        break
        except Exception as e:
            print(f"[CatalogService] Error fetching AS season episodes: {e}")
        return episodes

    async def resolve_stream(self, embed_url: str, source: str = "anime_sama") -> dict:
        try:
            # Try VoirAnime resolver API (port 8000)
            resp = await self.client.get(f"{VA_API_BASE}/resolve", params={"embed_url": embed_url})
            if resp.status_code == 200:
                data = resp.json()
                if data.get("status") == "success" and data.get("stream_url"):
                    return {
                        "stream_url": data["stream_url"],
                        "stream_type": data.get("stream_type", "m3u8"),
                        "iframe_url": embed_url,
                        "host": data.get("host")
                    }
        except Exception:
            pass

        return {"stream_url": None, "stream_type": None, "iframe_url": embed_url, "host": None}

catalog_service = CatalogService()
