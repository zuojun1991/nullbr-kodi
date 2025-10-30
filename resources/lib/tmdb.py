# resources/lib/tmdb.py (v1.1.2 - 修正版)
# -*- coding: utf-8 -*-
import requests
import xbmc
from simplecache import SimpleCache
import datetime # 导入 datetime 模块

class TMDbHelper:
    BASE_URL = "https://api.themoviedb.org/3"
    IMAGE_URL = "https://image.tmdb.org/t/p/"

    def __init__(self, api_key):
        self.api_key = api_key
        self.session = requests.Session()
        self.cache = SimpleCache()
        self.lang = xbmc.getLanguage(xbmc.ISO_639_1) or 'en'

    def _get(self, path, params=None):
        if not self.api_key:
            return None
        
        cache_key = f"tmdb.{self.lang}.{path}.{str(params)}"
        cached_data = self.cache.get(cache_key)
        if cached_data:
            return cached_data

        full_params = {
            'api_key': self.api_key,
            'language': self.lang,
            'append_to_response': 'images',
            'include_image_language': f'{self.lang},en,null'
        }
        if params:
            full_params.update(params)
        
        try:
            url = f"{self.BASE_URL}{path}"
            response = self.session.get(url, params=full_params, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            # --- 修正点：兼容旧版 simplecache ---
            # 使用 expiration 参数，单位是 timedelta
            expiration_delta = datetime.timedelta(days=7)
            self.cache.set(cache_key, data, expiration=expiration_delta)
            # ------------------------------------

            return data
        except Exception as e:
            xbmc.log(f"TMDbHelper Error: {e}", xbmc.LOGERROR)
            return None

    def get_art(self, tmdbid, media_type='movie'):
        art = {}
        path = f"/{media_type}/{tmdbid}"
        data = self._get(path)
        
        if not data:
            return art

        logos = data.get('images', {}).get('logos', [])
        if logos:
            cn_logo = next((l['file_path'] for l in logos if l.get('iso_639_1') == 'zh'), None)
            en_logo = next((l['file_path'] for l in logos if l.get('iso_639_1') == 'en'), None)
            logo_path = cn_logo or en_logo or (logos[0]['file_path'] if logos else None)
            if logo_path:
                art['clearlogo'] = self.IMAGE_URL + 'original' + logo_path

        if data.get('poster_path'):
            art['poster'] = self.IMAGE_URL + 'w500' + data['poster_path']
        if data.get('backdrop_path'):
            art['fanart'] = self.IMAGE_URL + 'original' + data['backdrop_path']
        
        return art

    def get_season_art(self, tmdbid, season_number):
        art = {}
        path = f"/tv/{tmdbid}/season/{season_number}"
        data = self._get(path)
        if data and data.get('poster_path'):
            art['poster'] = self.IMAGE_URL + 'w500' + data['poster_path']
            art['thumb'] = art['poster']
        return art

    def get_episode_art(self, tmdbid, season_number, episode_number):
        art = {}
        path = f"/tv/{tmdbid}/season/{season_number}/episode/{episode_number}"
        data = self._get(path)
        if data and data.get('still_path'):
            art['thumb'] = self.IMAGE_URL + 'w500' + data['still_path']
            art['icon'] = art['thumb']
        return art