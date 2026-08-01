import os
import sys
import json
import re
import asyncio
import cloudscraper
from bs4 import BeautifulSoup

# Add submodules to sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ANIME_SAMA_PATH = os.path.join(PROJECT_ROOT, "AnimeSamaApi")
VOIRANIME_PATH = os.path.join(PROJECT_ROOT, "voiranime_API")

if ANIME_SAMA_PATH not in sys.path:
    sys.path.insert(0, ANIME_SAMA_PATH)
if VOIRANIME_PATH not in sys.path:
    sys.path.insert(0, VOIRANIME_PATH)

# Import submodule resolvers and scrapers
try:
    from AnimeSamaApi.src.utils.resolvers import resolve_video_url as as_resolve_url
    from AnimeSamaApi.src.utils.utils import Utils as ASUtils
except ImportError:
    try:
        from src.utils.resolvers import resolve_video_url as as_resolve_url
        from src.utils.utils import Utils as ASUtils
    except ImportError:
        as_resolve_url = None
        ASUtils = None

try:
    from voiranime_API.src.core.scraper import VoirAnimeScraper
except ImportError:
    try:
        from src.core.scraper import VoirAnimeScraper
    except ImportError:
        VoirAnimeScraper = None


class CatalogService:
    def __init__(self):
        self.data_dir = os.path.join(PROJECT_ROOT, "data")
        os.makedirs(self.data_dir, exist_ok=True)
        self.as_scraper = cloudscraper.create_scraper()
        self.va_scraper = VoirAnimeScraper(data_dir=os.path.join(self.data_dir, "voiranime")) if VoirAnimeScraper else None
        self._as_base_url = None

    @property
    def as_base_url(self):
        if not self._as_base_url:
            if ASUtils:
                try:
                    self._as_base_url = ASUtils.findLink()
                except Exception:
                    self._as_base_url = "https://anime-sama.fr"
            else:
                self._as_base_url = "https://anime-sama.fr"
        return self._as_base_url or "https://anime-sama.fr"

    async def search(self, query: str, source: str = "all") -> list:
        results = []
        tasks = []

        if source in ["all", "anime_sama"]:
            tasks.append(self._search_anime_sama(query))
        if source in ["all", "voiranime"] and self.va_scraper:
            tasks.append(self._search_voiranime(query))

        if tasks:
            res_list = await asyncio.gather(*tasks, return_exceptions=True)
            for res in res_list:
                if isinstance(res, list):
                    results.extend(res)

        return results

    async def _search_anime_sama(self, query: str) -> list:
        results = []
        try:
            url = f"{self.as_base_url}/catalogue/"
            resp = self.as_scraper.get(url, timeout=10)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, 'lxml')
                cards = soup.find_all('div', class_="shrink-0 catalog-card card-base")
                q_lower = query.lower().strip()
                for card in cards:
                    h2 = card.find('h2', class_="card-title")
                    title = h2.get_text(strip=True) if h2 else ""
                    a_tag = card.find('a')
                    link = a_tag.get('href') if a_tag else ""
                    img_tag = card.find('img')
                    cover = img_tag.get('src') if img_tag else ""
                    if cover and not cover.startswith("http"):
                        cover = f"{self.as_base_url}/{cover.lstrip('/')}"

                    if not title or not link:
                        continue

                    if q_lower in title.lower():
                        results.append({
                            "id": f"as:{link}",
                            "title": title,
                            "source": "anime_sama",
                            "url": link,
                            "cover": cover,
                        })
        except Exception as e:
            print(f"[CatalogService] Error AnimeSama search: {e}")
        return results

    async def _search_voiranime(self, query: str) -> list:
        results = []
        try:
            if not self.va_scraper:
                return results
            matches = self.va_scraper.resolve_anime(query)
            for item in matches:
                results.append({
                    "id": f"va:{item['url']}",
                    "title": item["name"],
                    "source": "voiranime",
                    "url": item["url"],
                    "cover": "", # Cover will be fetched when loading anime details
                })
        except Exception as e:
            print(f"[CatalogService] Error VoirAnime search: {e}")
        return results

    async def get_details(self, url: str, source: str) -> dict:
        if source == "anime_sama":
            return await self._get_details_anime_sama(url)
        elif source == "voiranime":
            return await self._get_details_voiranime(url)
        return {}

    async def _get_details_anime_sama(self, url: str) -> dict:
        try:
            resp = self.as_scraper.get(url, timeout=10)
            if resp.status_code != 200:
                return {}
            
            soup = BeautifulSoup(resp.text, 'html.parser')
            title_tag = soup.find('h1') or soup.find('h2', class_="card-title")
            title = title_tag.get_text(strip=True) if title_tag else "Anime"

            img_tag = soup.find('img', id="cover") or soup.find('img', class_="w-full")
            cover = img_tag.get('src') if img_tag else ""
            if cover and not cover.startswith("http"):
                cover = f"{self.as_base_url}/{cover.lstrip('/')}"

            desc_tag = soup.find('p', class_="text-sm text-gray-400") or soup.find('div', id="synopsis")
            synopsis = desc_tag.get_text(strip=True) if desc_tag else ""

            # Extract seasons & versions from scripts
            scripts = soup.find_all("script")
            pattern = re.compile(r'panneau(?:Anime|Film|Scan|Visual)\s*\(\s*(["\'])(.*?)\1\s*,\s*(["\'])(.*?)\3\s*\)')

            seasons = []
            for script in scripts:
                if script.text:
                    text = re.sub(r'/\*.*?\*/', '', script.text, flags=re.DOTALL)
                    matches = pattern.findall(text)
                    for quote1, nom, quote2, lien in matches:
                        if nom.lower() not in ["nom", "scan", "visual"] and lien.lower() != "url":
                            saison_url = url.rstrip("/") + "/" + lien.lstrip("/")
                            seasons.append({
                                "name": nom,
                                "url": saison_url,
                                "raw_link": lien
                            })

            return {
                "title": title,
                "cover": cover,
                "synopsis": synopsis,
                "source": "anime_sama",
                "seasons": seasons
            }
        except Exception as e:
            print(f"[CatalogService] Error AnimeSama details: {e}")
            return {}

    async def _get_details_voiranime(self, url: str) -> dict:
        try:
            if not self.va_scraper:
                return {}
            episodes = await self.va_scraper.fetch_episodes(url)
            
            # Fetch cover & synopsis from page
            cover = ""
            synopsis = ""
            title = "Anime"
            
            self.va_scraper.init_client()
            resp = await self.va_scraper.client.get(url)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, 'lxml')
                t_tag = soup.find('h1') or soup.find('div', class_="post-title")
                if t_tag:
                    title = t_tag.get_text(strip=True)
                img = soup.find('div', class_="summary_image")
                if img and img.find('img'):
                    cover = img.find('img').get('src', '')
                desc = soup.find('div', class_="description-summary") or soup.find('div', class_="summary__content")
                if desc:
                    synopsis = desc.get_text(strip=True)

            return {
                "title": title,
                "cover": cover,
                "synopsis": synopsis,
                "source": "voiranime",
                "episodes": episodes
            }
        except Exception as e:
            print(f"[CatalogService] Error VoirAnime details: {e}")
            return {}

    async def fetch_anime_sama_episodes(self, season_url: str) -> list:
        """Fetches episode links for an AnimeSama season page"""
        episodes = []
        try:
            resp = self.as_scraper.get(season_url, timeout=10)
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, 'html.parser')
                scripts = soup.find_all("script")
                
                # Find eps.js or episode arrays in script
                for script in scripts:
                    if script.string and "var eps" in script.string:
                        # Extract episode JS arrays
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
                
                # If script approach didn't yield links, look for iframe tags or select elements
                if not episodes:
                    iframes = soup.find_all('iframe')
                    for idx, iframe in enumerate(iframes, 1):
                        src = iframe.get('src')
                        if src:
                            episodes.append({
                                "num": idx,
                                "title": f"Épisode {idx}",
                                "embed_url": src
                            })
        except Exception as e:
            print(f"[CatalogService] Error fetching AS season episodes: {e}")
        return episodes

    async def resolve_stream(self, embed_url: str, source: str = "anime_sama") -> dict:
        """Resolves embed player URL to direct video stream URL (.m3u8 or .mp4)"""
        result = {"stream_url": None, "stream_type": None, "iframe_url": embed_url, "host": None}
        
        # Standardize embed URL
        if embed_url.startswith("//"):
            embed_url = "https:" + embed_url

        try:
            # First try AnimeSama resolver if available
            if as_resolve_url:
                as_res = as_resolve_url(embed_url)
                if as_res and as_res.get("url") and as_res.get("type") in ["m3u8", "mp4"]:
                    result["stream_url"] = as_res["url"]
                    result["stream_type"] = as_res["type"]
                    return result

            # Second try VoirAnime resolver if available
            if self.va_scraper and hasattr(self.va_scraper, 'resolver'):
                va_res = await self.va_scraper.resolver.resolve(embed_url)
                if va_res and va_res.get("status") == "success" and va_res.get("stream_url"):
                    result["stream_url"] = va_res["stream_url"]
                    result["stream_type"] = va_res.get("stream_type", "m3u8")
                    result["host"] = va_res.get("host")
                    return result

        except Exception as e:
            print(f"[CatalogService] Error resolving stream URL ({embed_url}): {e}")

        return result

catalog_service = CatalogService()
