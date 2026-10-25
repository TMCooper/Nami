import os
import sys
import json
import re
import asyncio
import httpx
from urllib.parse import quote
from typing import Optional, List, Dict
from bs4 import BeautifulSoup
from backend.services.cache_service import cache_service
from backend.services.update_service import VOIRANIME_PATH

AS_API_BASE = "http://127.0.0.1:5000"
VA_API_BASE = "http://127.0.0.1:8000"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
}


class CatalogService:
    def __init__(self):
        self.client = httpx.AsyncClient(timeout=30.0, headers=HEADERS, follow_redirects=True)
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

    def _format_cover_url(self, cover: str) -> str:
        if not cover:
            return ""
        if "voir-anime" in cover:
            return f"/api/proxy/image?url={quote(cover, safe='')}"
        return cover

    def _save_voiranime_cached_cover(self, title: str, cover_url: str):
        if not title or not cover_url:
            return
        covers_path = os.path.join(VOIRANIME_PATH, "data", "covers.json")
        try:
            cov_data = {}
            if os.path.exists(covers_path):
                with open(covers_path, "r", encoding="utf-8") as f:
                    cov_data = json.load(f)
            cov_data[title] = cover_url
            clean_title = re.sub(r'\s*\((?:VF|VOSTFR)\)\s*', '', title, flags=re.IGNORECASE).strip()
            cov_data[clean_title] = cover_url
            with open(covers_path, "w", encoding="utf-8") as f:
                json.dump(cov_data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[CatalogService] Error saving cover to covers.json: {e}")

    def _get_voiranime_cached_cover(self, title: str) -> str:
        if not title:
            return ""
        covers_path = os.path.join(VOIRANIME_PATH, "data", "covers.json")
        if os.path.exists(covers_path):
            try:
                with open(covers_path, "r", encoding="utf-8") as f:
                    cov_data = json.load(f)
                    if title in cov_data and cov_data[title]:
                        return cov_data[title]
                    clean_title = re.sub(r'\s*\((?:VF|VOSTFR)\)\s*', '', title, flags=re.IGNORECASE).strip()
                    if clean_title in cov_data and cov_data[clean_title]:
                        return cov_data[clean_title]
                    # Also try case-insensitive lookup
                    lower_clean = clean_title.lower()
                    for k, v in cov_data.items():
                        if k.lower().strip() == lower_clean and v:
                            return v
            except Exception:
                pass
        return ""

    async def _resolve_voiranime_cover(self, name: str, url: str) -> str:
        # 1. Fast cache lookup
        cov = self._get_voiranime_cached_cover(name)
        if cov:
            return cov

        # 2. Check if detail cache has it
        cached_detail = cache_service.get_anime_details("voiranime", f"voiranime:{url}")
        if cached_detail and cached_detail.get("cover"):
            raw_c = cached_detail["cover"]
            if "/api/proxy/image?url=" in raw_c:
                raw_c = raw_c.split("/api/proxy/image?url=")[-1]
            self._save_voiranime_cached_cover(name, raw_c)
            return raw_c

        # 3. Direct HTML scrape of og:image / summary image
        try:
            r = await self.client.get(url, timeout=3.5, headers={"Referer": "https://voir-anime.to/"})
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, 'html.parser')
                og = soup.find('meta', property='og:image')
                if og and og.get('content'):
                    c_url = og['content']
                    self._save_voiranime_cached_cover(name, c_url)
                    return c_url
                sum_img = soup.select_one('.summary_image img')
                if sum_img:
                    c_url = sum_img.get('src') or sum_img.get('data-src') or ""
                    if c_url:
                        self._save_voiranime_cached_cover(name, c_url)
                        return c_url
        except Exception:
            pass

        return ""

    @staticmethod
    def _calc_relevance(title: str, query: str) -> float:
        if not query.strip():
            return 100.0
        t_lower = title.lower()
        q_lower = query.lower().strip()
        if q_lower == t_lower:
            return 100.0
        if q_lower in t_lower:
            return 90.0 + (len(q_lower) / len(t_lower)) * 5.0
        q_tokens = [w for w in q_lower.split() if len(w) > 1]
        if not q_tokens:
            return 0.0
        matched_tokens = [w for w in q_tokens if w in t_lower]
        return (len(matched_tokens) / len(q_tokens)) * 70.0

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

        # Relevance scoring & filtering
        q_clean = query.strip()
        if q_clean and results:
            has_strong_match = False
            for item in results:
                score = self._calc_relevance(item.get("title", ""), q_clean)
                item["_score"] = score
                if score >= 85.0:
                    has_strong_match = True

            # If strong match exists (e.g. "High School DxD"), filter out irrelevant clutter (< 60 score)
            if has_strong_match:
                results = [item for item in results if item.get("_score", 0) >= 60.0]

            # Rank best matches first
            results.sort(key=lambda x: x.get("_score", 0), reverse=True)

        # Fallback to starter/popular recommendations if search is empty and no results found
        if not results and not query.strip():
            if source in ["all", "anime_sama"]:
                return cache_service.get_random_animes(count=24)
            return []

        return results

    async def _search_anime_sama(self, query: str = "") -> list:
        results = []
        q_clean = query.strip()
        try:
            if q_clean:
                resp = await self.client.get(f"{AS_API_BASE}/api/getSerchAnime", params={"q": q_clean, "l": 20})
                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data, list):
                        for item in data:
                            title = item.get("title", "")
                            link = item.get("lien", item.get("link", ""))
                            cover = item.get("cover", "")
                            if not cover and link:
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
                            link = item.get("link", item.get("lien", ""))
                            slug = link.rstrip("/").split("/")[-1] if link else ""
                            cover = item.get("cover") or (f"https://cdn.statically.io/gh/Anime-Sama/IMG/img/contenu/{slug}.jpg" if slug else "")
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
                # Try compatible route first
                resp = await self.client.get(f"{VA_API_BASE}/api/getSerchAnime", params={"q": q_clean, "l": 20})
                if resp.status_code != 200:
                    resp = await self.client.get(f"{VA_API_BASE}/anime/search", params={"query": q_clean})

                if resp.status_code == 200:
                    data = resp.json()
                    matches = data.get("results", data) if isinstance(data, dict) else data
                    if isinstance(matches, list):
                        # 1. Resolve missing covers concurrently
                        missing_items = [
                            m for m in matches
                            if not m.get("cover") and not self._get_voiranime_cached_cover(m.get("title", m.get("name", "")))
                        ]
                        if missing_items:
                            tasks = [
                                self._resolve_voiranime_cover(
                                    item.get("title", item.get("name", "")),
                                    item.get("link", item.get("lien", item.get("url", "")))
                                )
                                for item in missing_items[:12]
                            ]
                            resolved_covers = await asyncio.gather(*tasks, return_exceptions=True)
                            for idx, cov in enumerate(resolved_covers):
                                if isinstance(cov, str) and cov:
                                    missing_items[idx]["cover"] = cov

                        for item in matches:
                            name = item.get("title", item.get("name", ""))
                            url = item.get("link", item.get("lien", item.get("url", "")))
                            cover = item.get("cover", "")
                            if not cover:
                                cover = self._get_voiranime_cached_cover(name)
                            cover = self._format_cover_url(cover)
                            if name and url:
                                results.append({
                                    "id": f"va:{url}",
                                    "title": name,
                                    "source": "voiranime",
                                    "url": url,
                                    "cover": cover
                                })
            else:
                resp = await self.client.get(f"{VA_API_BASE}/api/loadBaseAnimeData")
                if resp.status_code != 200:
                    resp = await self.client.get(f"{VA_API_BASE}/catalog")

                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data, list):
                        for item in data[:300]:
                            name = item.get("title", "")
                            url = item.get("link", "")
                            cover = item.get("cover", "")
                            if not cover:
                                cover = self._get_voiranime_cached_cover(name)
                            cover = self._format_cover_url(cover)
                            if name and url:
                                results.append({
                                    "id": f"va:{url}",
                                    "title": name,
                                    "source": "voiranime",
                                    "url": url,
                                    "cover": cover
                                })
                    elif isinstance(data, dict):
                        cat_dict = data.get("catalog", data)
                        count = 0
                        if isinstance(cat_dict, dict):
                            for name, url in cat_dict.items():
                                cover = self._get_voiranime_cached_cover(name)
                                cover = self._format_cover_url(cover)
                                results.append({
                                    "id": f"va:{url}",
                                    "title": name,
                                    "source": "voiranime",
                                    "url": url,
                                    "cover": cover
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
                if source == "voiranime":
                    eps = cached.get("episodes", [])
                    needs_refresh = False
                    if not eps or "num" not in eps[0] or not isinstance(eps[0].get("num"), int):
                        needs_refresh = True
                    cover_val = cached.get("cover", "")
                    if "voir-anime" in cover_val and not cover_val.startswith("/api/proxy/image"):
                        cached["cover"] = self._format_cover_url(cover_val)
                    if needs_refresh:
                        cached = None
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
        ALIASES = {
            "lattaque-des-titans": "shingeki-no-kyojin",
            "attaque-des-titans": "shingeki-no-kyojin",
            "attack-on-titan": "shingeki-no-kyojin",
            "hunter-x-hunter-2011": "hunter-x-hunter"
        }
        raw_slug = url.rstrip("/").split("/")[-1]
        slug = ALIASES.get(raw_slug, raw_slug)
        target_url = url if slug == raw_slug else f"https://anime-sama.to/catalogue/{slug}/"
        default_cover = f"https://raw.githubusercontent.com/Anime-Sama/IMG/img/contenu/{slug}.jpg"

        # 1. Try scraping the catalogue page directly on Anime-Sama
        try:
            fetch_url = target_url.replace("anime-sama.fr", "anime-sama.to")
            resp = await self.client.get(fetch_url, timeout=8.0, headers={"User-Agent": "Mozilla/5.0"})
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, 'html.parser')
                h1 = soup.find('h1', id='titreOeuvre') or soup.find('h1')
                anime_name = h1.text.strip() if h1 and h1.text.strip() else slug.replace("-", " ").title()

                og_img = soup.find('meta', property='og:image')
                cover = og_img.get('content') if og_img and og_img.get('content') else default_cover

                pattern = re.compile(r'panneau(?:Anime|Film|Scan|Visual)\s*\(\s*["\']([^"\']+)["\']\s*,\s*["\']([^"\']+)["\']\s*\)')
                matches = pattern.findall(resp.text)
                seasons = []
                seen_seasons = set()
                base_clean = fetch_url.rstrip("/")
                for nom, lien in matches:
                    if nom.lower() not in ["nom", "scans"] and lien.lower() != "url":
                        if nom not in seen_seasons:
                            seen_seasons.add(nom)
                            seasons.append({
                                "name": nom,
                                "url": f"{base_clean}/{lien.lstrip('/')}",
                                "raw_link": f"{base_clean}/{lien.lstrip('/')}"
                            })

                if seasons:
                    return {
                        "title": anime_name,
                        "url": target_url,
                        "cover": cover,
                        "synopsis": "",
                        "source": "anime_sama",
                        "seasons": seasons
                    }
        except Exception as e:
            print(f"[CatalogService] Direct Anime-Sama scrape error: {e}")

        # 2. Fallback to AnimeSamaApi /api/getInfoAnime
        try:
            title = slug.replace("-", " ")
            resp = await self.client.get(f"{AS_API_BASE}/api/getInfoAnime", params={"q": title})
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list) and len(data) > 0:
                    anime_name = data[0].get("title", title.title())
                    cover = data[0].get("cover", default_cover)
                    seasons = []
                    for item in data:
                        s_name = item.get("Saison", "Saison 1")
                        seasons.append({
                            "name": s_name,
                            "url": item.get("url", target_url),
                            "raw_link": item.get("url", target_url)
                        })
                    return {
                        "title": anime_name,
                        "url": target_url,
                        "cover": cover,
                        "synopsis": "",
                        "source": "anime_sama",
                        "seasons": seasons
                    }
        except Exception as e:
            print(f"[CatalogService] Error fetching AnimeSama details: {e}")

        return {
            "title": slug.replace("-", " ").title(),
            "url": target_url,
            "cover": default_cover,
            "source": "anime_sama",
            "seasons": [{"name": "Saison 1", "url": target_url}]
        }

    async def _get_details_voiranime(self, url: str) -> dict:
        title = url.rstrip("/").split("/")[-1].replace("-", " ").title()
        cover = self._get_voiranime_cached_cover(title)
        synopsis = ""

        # Scrape anime page on VoirAnime to get cover and synopsis directly
        try:
            page_resp = await self.client.get(url, timeout=8.0, headers={"Referer": "https://voir-anime.to/"})
            if page_resp.status_code == 200:
                soup = BeautifulSoup(page_resp.text, 'html.parser')
                og_img = soup.find('meta', property='og:image')
                if og_img and og_img.get('content'):
                    cover = og_img['content']
                if not cover:
                    sum_img = soup.select_one('.summary_image img')
                    if sum_img:
                        cover = sum_img.get('src') or sum_img.get('data-src') or ""

                desc_p = soup.select_one('.description-summary p')
                if desc_p:
                    synopsis = desc_p.text.strip()
        except Exception as e:
            print(f"[CatalogService] VoirAnime page scraping warning: {e}")

        seasons = []
        try:
            info_resp = await self.client.get(f"{VA_API_BASE}/api/getInfoAnime", params={"q": title})
            if info_resp.status_code == 200:
                info_data = info_resp.json()
                if isinstance(info_data, list) and len(info_data) > 0:
                    if not cover and info_data[0].get("cover"):
                        cover = info_data[0].get("cover", "")
                    if len(info_data) > 1:
                        for s in info_data:
                            s_nom = s.get("Saison", "Saison 1")
                            s_url = s.get("url", url)
                            s_cov = s.get("cover", cover)
                            seasons.append({
                                "name": s_nom,
                                "url": s_url,
                                "raw_link": s_url,
                                "cover": self._format_cover_url(s_cov)
                            })
        except Exception:
            pass

        if cover:
            raw_c = cover.split("/api/proxy/image?url=")[-1] if "/api/proxy/image?url=" in cover else cover
            self._save_voiranime_cached_cover(title, raw_c)

        cover = self._format_cover_url(cover)

        try:
            resp = await self.client.get(f"{VA_API_BASE}/episodes", params={"anime_url": url})
            if resp.status_code == 200:
                data = resp.json()
                raw_episodes = data.get("episodes", [])
                episodes = []
                for idx, ep in enumerate(raw_episodes):
                    title_str = ep.get("title", "")
                    num_match = re.search(r'-\s*(\d+)\s*(?:VOSTFR|VF)', title_str, re.IGNORECASE) or re.search(r'(\d+)', title_str)
                    ep_num = int(num_match.group(1)) if num_match else idx + 1
                    ep_url = ep.get("url", "")
                    episodes.append({
                        "num": ep_num,
                        "title": title_str or f"Épisode {ep_num}",
                        "url": ep_url,
                        "embed_url": ep_url
                    })
                # Sort ascending by episode number (1, 2, 3...)
                episodes.sort(key=lambda x: x["num"])
                res_dict = {
                    "title": title,
                    "url": url,
                    "cover": cover,
                    "synopsis": synopsis,
                    "source": "voiranime",
                    "episodes": episodes
                }
                if seasons:
                    res_dict["seasons"] = seasons
                return res_dict
        except Exception as e:
            print(f"[CatalogService] Error fetching VoirAnime episodes: {e}")

        res_dict = {"title": title, "url": url, "cover": cover, "synopsis": synopsis, "source": "voiranime", "episodes": []}
        if seasons:
            res_dict["seasons"] = seasons
        return res_dict

    async def fetch_anime_sama_episodes(
        self,
        season_url: str,
        anime_title: str = "",
        season_name: str = "Saison 1",
        version: str = "vostfr",
        refresh: bool = False
    ) -> list:
        cache_key = f"as_eps:{season_url}:{season_name}:{version}"
        if not refresh:
            cached = cache_service.get_anime_details("anime_sama_eps", cache_key)
            if cached and isinstance(cached, list) and len(cached) > 0:
                return cached

        episodes = []

        # 1. Determine title and season to call AnimeSamaApi /api/getAnimeLink?n=...&s=...&v=...
        derived_title = anime_title.strip()
        if not derived_title and "/catalogue/" in season_url:
            slug_match = re.search(r'/catalogue/([^/]+)', season_url)
            if slug_match:
                derived_title = slug_match.group(1).replace("-", " ")

        s_norm = season_name.lower().replace(" ", "")
        if not s_norm or s_norm == "saison":
            s_norm = "saison1"

        # Try API getAnimeLink
        if derived_title:
            try:
                resp = await self.client.get(
                    f"{AS_API_BASE}/api/getAnimeLink",
                    params={"n": derived_title, "s": s_norm, "v": version},
                    timeout=20.0
                )
                if resp.status_code == 200:
                    data = resp.json()
                    if isinstance(data, list) and len(data) > 0:
                        for item in data:
                            ep_num = item.get("episode", len(episodes) + 1)
                            raw_url = item.get("url", "")
                            if raw_url:
                                is_direct = ".m3u8" in raw_url or ".mp4" in raw_url
                                episodes.append({
                                    "num": ep_num,
                                    "title": f"Épisode {ep_num}",
                                    "embed_url": raw_url,
                                    "stream_url": raw_url if is_direct else None,
                                    "stream_type": "m3u8" if ".m3u8" in raw_url else ("mp4" if ".mp4" in raw_url else None)
                                })
            except Exception as e:
                print(f"[CatalogService] getAnimeLink query error: {e}")

        # 2. Direct episodes.js fallback scraping if API returned 0 episodes
        if not episodes and season_url:
            try:
                target_url = season_url.rstrip("/")
                if not target_url.endswith("/vostfr") and not target_url.endswith("/vf"):
                    target_url = f"{target_url}/{version}"

                resp = await self.client.get(target_url, timeout=10.0)
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, 'html.parser')
                    script_tag = soup.find("script", src=lambda s: s and "episodes.js" in s)
                    if script_tag:
                        js_src = script_tag.get("src", "").strip("\"'")
                        js_url = f"{target_url.rstrip('/')}/{js_src.lstrip('/')}"
                        js_resp = await self.client.get(js_url, headers={"Referer": target_url}, timeout=10.0)
                        if js_resp.status_code == 200:
                            js_text = js_resp.text
                            # Find all var eps1 = [...]; or epsAS = [...]
                            matches = re.findall(r"var\s+(eps\w+)\s*=\s*\[(.*?)\];", js_text, re.DOTALL)
                            lecteurs = {}
                            for l_name, content in matches:
                                urls = re.findall(r"'(https?://[^']+)'", content)
                                if urls:
                                    lecteurs[l_name] = urls

                            if lecteurs:
                                # Pick best lecteur
                                best_key = list(lecteurs.keys())[0]
                                for k in lecteurs:
                                    if "eps1" in k:
                                        best_key = k
                                        break
                                url_list = lecteurs[best_key]
                                for idx, u in enumerate(url_list, 1):
                                    episodes.append({
                                        "num": idx,
                                        "title": f"Épisode {idx}",
                                        "embed_url": u,
                                        "stream_url": u if (".m3u8" in u or ".mp4" in u) else None
                                    })
            except Exception as e:
                print(f"[CatalogService] Direct episodes.js scrape error: {e}")

        if episodes:
            cache_service.save_anime_details("anime_sama_eps", cache_key, episodes)

        return episodes

    async def resolve_stream(self, embed_url: str, source: str = "anime_sama") -> dict:
        result = {"stream_url": None, "stream_type": None, "iframe_url": embed_url, "host": None}

        if embed_url.startswith("//"):
            embed_url = "https:" + embed_url

        target_embed = embed_url

        # Special handling for VoirAnime: episode URL is a webpage, extract the real video player iframe!
        if "voir-anime.to" in target_embed or source == "voiranime":
            try:
                page_resp = await self.client.get(target_embed, headers={**HEADERS, "Referer": "https://voir-anime.to/"}, timeout=8.0)
                if page_resp.status_code == 200:
                    page_html = page_resp.text
                    sources_match = re.search(r'var\s+thisChapterSources\s*=\s*(\{.*?\});', page_html, re.DOTALL)
                    if sources_match:
                        src_dict = json.loads(sources_match.group(1))
                        # Preferred video player order: voembed/mytv, vidmoly, sendvid, voe, streamtape
                        def player_rank(k):
                            kl = k.lower()
                            if "sibnet" in kl: return 999
                            if "mytv" in kl or "voembed" in kl: return 1
                            if "vidmoly" in kl: return 2
                            if "sendvid" in kl: return 3
                            if "voe" in kl: return 4
                            if "streamtape" in kl or "stape" in kl: return 5
                            return 10

                        sorted_keys = sorted(src_dict.keys(), key=player_rank)
                        for k in sorted_keys:
                            if "sibnet" in k.lower():
                                continue
                            ifr_code = src_dict[k]
                            src_match = re.search(r'src=["\']([^"\']+)["\']', ifr_code)
                            if src_match:
                                extracted = src_match.group(1).replace(r"\/", "/")
                                if "voiranime" not in extracted:
                                    target_embed = extracted
                                    result["iframe_url"] = extracted
                                    result["host"] = k
                                    break
                    else:
                        soup = BeautifulSoup(page_html, 'html.parser')
                        for ifr in soup.find_all('iframe'):
                            src = ifr.get('src')
                            if src and "voiranime" not in src and "sibnet" not in src.lower():
                                target_embed = src
                                result["iframe_url"] = src
                                break
            except Exception as e:
                print(f"[CatalogService] VoirAnime iframe extraction error: {e}")

        # Now resolve the clean target embed via VoirAnime resolver to obtain direct m3u8 or mp4
        try:
            resp = await self.client.get(f"{VA_API_BASE}/resolve", params={"embed_url": target_embed}, timeout=10.0)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("status") == "success" and data.get("stream_url"):
                    result["stream_url"] = data["stream_url"]
                    result["stream_type"] = data.get("stream_type", "m3u8")
                    result["host"] = data.get("host") or result["host"]
                    result["iframe_url"] = target_embed
                    return result
        except Exception:
            pass

        return result

catalog_service = CatalogService()
