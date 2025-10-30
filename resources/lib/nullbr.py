# resources/lib/nullbr.py
# -*- coding: utf-8 -*-
import requests

BASE_URL = "https://api.nullbr.eu.org"

class NullBRAPI:
    def __init__(self, app_id: str, api_key: str = ""):
        self.app_id = (app_id or "").strip()
        self.api_key = (api_key or "").strip()
        self.session = requests.Session()
        self.session.headers.update({
            "X-APP-ID": self.app_id,
        })

    def _get(self, path: str, params=None, need_key=False):
        headers = {}
        if need_key and self.api_key:
            headers["X-API-KEY"] = self.api_key
        url = f"{BASE_URL}{path}"
        r = self.session.get(url, params=params or {}, headers=headers, timeout=15)
        r.raise_for_status()
        return r.json()

    # ===== 电影 =====
    def get_list(self, list_id: str, page: int = 1):
        return self._get(f"/list/{list_id}", params={"page": page})

    def get_movie(self, tmdbid: str):
        return self._get(f"/movie/{tmdbid}")

    def get_movie_115_links(self, tmdbid: str, page: int = 1):
        return self._get(f"/movie/{tmdbid}/115", params={"page": page}, need_key=True)

    def get_movie_magnet_links(self, tmdbid: str, page: int = 1):
        return self._get(f"/movie/{tmdbid}/magnet", params={"page": page}, need_key=True)

    # ===== 电视剧 (新增) =====
    def get_tv_show(self, tmdbid: str):
        return self._get(f"/tv/{tmdbid}")

    def get_tv_show_115_links(self, tmdbid: str, page: int = 1):
        return self._get(f"/tv/{tmdbid}/115", params={"page": page}, need_key=True)

    def get_season_details(self, tmdbid: str, season_number: int):
        return self._get(f"/tv/{tmdbid}/season/{season_number}")

    def get_season_magnet_links(self, tmdbid: str, season_number: int, page: int = 1):
        return self._get(f"/tv/{tmdbid}/season/{season_number}/magnet", params={"page": page}, need_key=True)

    def get_episode_details(self, tmdbid: str, season_number: int, episode_number: int):
        return self._get(f"/tv/{tmdbid}/season/{season_number}/episode/{episode_number}")

    def get_episode_magnet_links(self, tmdbid: str, season_number: int, episode_number: int, page: int = 1):
        return self._get(f"/tv/{tmdbid}/season/{season_number}/episode/{episode_number}/magnet", params={"page": page}, need_key=True)