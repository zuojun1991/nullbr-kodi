# default.py (v1.1.7 - 最终修复版)

#!/usr/bin/python
# -*- coding: utf-8 -*-

import sys
import os
from urllib.parse import parse_qsl, urlencode

import xbmc
import xbmcgui
import xbmcplugin
import xbmcaddon
import xbmcvfs

# ===== Addon 基本信息 (已恢复完整) =====
ADDON = xbmcaddon.Addon()
ADDON_ID = ADDON.getAddonInfo('id')
ADDON_NAME = ADDON.getAddonInfo('name')
ADDON_PATH = xbmcvfs.translatePath(ADDON.getAddonInfo('path'))
ADDON_PROFILE = xbmcvfs.translatePath(ADDON.getAddonInfo('profile'))
ADDON_ICON = xbmcvfs.translatePath(ADDON.getAddonInfo('icon'))
ADDON_FANART = xbmcvfs.translatePath(ADDON.getAddonInfo('fanart'))

# ===== 导入自定义库 =====
sys.path.insert(0, os.path.join(ADDON_PATH, 'resources', 'lib'))
try:
    from resources.lib.nullbr import NullBRAPI
    from resources.lib.player import NullBRPlayer
    from resources.lib.cache import Cache
    from resources.lib.tmdb import TMDbHelper
except Exception as e:
    xbmc.log(f'{ADDON_NAME}: Import libs error: {e}', xbmc.LOGERROR)
    xbmcgui.Dialog().notification(ADDON_NAME, 'Load libraries failed', ADDON_ICON, 4000)
    raise

def _get_params():
    if len(sys.argv) >= 3 and sys.argv[2]:
        return dict(parse_qsl(sys.argv[2][1:]))
    return {}

def _build_url(base, q):
    return base + '?' + urlencode(q)

class NullBRPlugin:
    def __init__(self):
        self.handle = int(sys.argv[1])
        self.base_url = sys.argv[0]

        self.app_id     = ADDON.getSetting('nullbr_app_id').strip()
        self.api_key    = ADDON.getSetting('nullbr_api_key').strip()
        self.list_ids   = [x.strip() for x in ADDON.getSetting('nullbr_lists').strip().split(',') if x.strip()]
        self.tmdb_api_key = ADDON.getSetting('tmdb_api_key').strip()

        self.cookie_uid = ADDON.getSetting('cookie_uid')
        self.cookie_cid = ADDON.getSetting('cookie_cid')
        self.cookie_seid= ADDON.getSetting('cookie_seid')
        self.target_cid = ADDON.getSetting('target_cid')
        self.server_url = ADDON.getSetting('server_url').strip().rstrip('/')
        self.rclone_mount = ADDON.getSetting('rclone_mount').strip().rstrip('/\\')

        self.auto_select = ADDON.getSetting('auto_select_quality') == 'true'
        self.prefer_dv   = ADDON.getSetting('prefer_dolby_vision') == 'true'
        self.prefer_iso  = ADDON.getSetting('prefer_iso') == 'true'
        self.prefer_4k   = ADDON.getSetting('prefer_4k') == 'true'

        self.api    = NullBRAPI(self.app_id, self.api_key)
        self.player = NullBRPlayer(self.server_url, self.rclone_mount,
                                   self.cookie_uid, self.cookie_cid, self.cookie_seid, self.target_cid)
        self.cache  = Cache(ADDON_PROFILE)
        self.tmdb   = TMDbHelper(self.tmdb_api_key)

        xbmc.log(f'{ADDON_NAME}: init ok; router exists={hasattr(self, "router")}', xbmc.LOGINFO)

    def build_url(self, q):
        return _build_url(self.base_url, q)

    def add_item(self, title, url, is_folder=True, info=None, art=None, context_menu=None):
        li = xbmcgui.ListItem(label=title)
        info = info or {}
        art = art or {}
        
        mediatype = info.get('mediatype', 'movie')
        tag = li.getVideoInfoTag()
        tag.setMediaType(mediatype)
        tag.setTitle(info.get('title', title))
        if 'plot' in info: tag.setPlot(info['plot'])
        if 'rating' in info: tag.setRating(float(info['rating']))
        if 'year' in info and info['year']:
            try: tag.setYear(int(info['year']))
            except: pass
        if 'premiered' in info: tag.setPremiered(info['premiered'])
        
        if mediatype == 'tvshow':
            if 'tvshowtitle' in info: tag.setTvShowTitle(info['tvshowtitle'])
        elif mediatype == 'season':
            if 'tvshowtitle' in info: tag.setTvShowTitle(info['tvshowtitle'])
            if 'season' in info: tag.setSeason(int(info['season']))
        elif mediatype == 'episode':
            if 'tvshowtitle' in info: tag.setTvShowTitle(info['tvshowtitle'])
            if 'season' in info: tag.setSeason(int(info['season']))
            if 'episode' in info: tag.setEpisode(int(info['episode']))

        final_art = {'icon': ADDON_ICON, 'fanart': ADDON_FANART}
        final_art.update(art)
        li.setArt(final_art)

        if context_menu:
            li.addContextMenuItems(context_menu)

        if not is_folder:
            li.setProperty('IsPlayable', 'true')

        xbmcplugin.addDirectoryItem(self.handle, url, li, is_folder)

    def show_lists(self):
        xbmcplugin.setContent(self.handle, 'tvshows')
        
        self.add_item(
            '[B]刷新列表 (Refresh Lists)[/B]', 
            self.build_url({'action': 'refresh_container'}), 
            is_folder=False,
            info={'title': '刷新列表', 'plot': '当您修改了设置或列表内容更新后，请点击此处刷新主菜单。'},
            art={'icon': 'DefaultAddons.png'}
        )

        if not self.list_ids:
            xbmcgui.Dialog().notification(ADDON_NAME, '请先到设置里填写 NullBR 列表 ID', ADDON_ICON, 4000)
            ADDON.openSettings()
            xbmcplugin.endOfDirectory(self.handle, succeeded=True)
            return

        for list_id in self.list_ids:
            try:
                data = self.api.get_list(list_id, page=1)
                name = data.get('name', f'List {list_id}')
                total = data.get('total_items', 0)
                url = self.build_url({'action':'show_list_contents', 'list_id': list_id, 'page':'1'})
                self.add_item(
                    f'{name} ({total})', url,
                    is_folder=True, info={'title': name}
                )
            except Exception as e:
                xbmc.log(f'{ADDON_NAME}: load list {list_id} error: {e}', xbmc.LOGERROR)

        self.add_item('Clear cache', self.build_url({'action':'clear_cache'}), is_folder=False)
        
        xbmcplugin.endOfDirectory(self.handle, succeeded=True)

    def refresh_container(self):
        xbmc.executebuiltin('Container.Refresh')

    def show_list_contents(self, list_id, page=1):
        xbmcplugin.setContent(self.handle, 'videos')
        try:
            data = self.api.get_list(list_id, page=int(page))
        except Exception as e:
            xbmcgui.Dialog().notification(ADDON_NAME, f'加载列表失败: {e}', ADDON_ICON, 4000)
            xbmcplugin.endOfDirectory(self.handle, succeeded=False)
            return
        for it in data.get('items', []):
            if not (it.get('115-flg') == 1 or it.get('magnet-flg') == 1):
                continue
            tmdbid = it.get('tmdbid')
            if not tmdbid: continue
            title = it.get('title', 'Unknown')
            plot = it.get('overview', '')
            vote = it.get('vote_average', 0) or 0
            rdate = it.get('release_date', '') or ''
            year = rdate[:4] if rdate else ''
            poster_path = it.get('poster') or ''
            poster = f'https://image.tmdb.org/t/p/w500{poster_path}' if poster_path.startswith('/') else ADDON_ICON
            fanart = f'https://image.tmdb.org/t/p/original{poster_path}' if poster_path.startswith('/') else ADDON_FANART
            art = {'poster': poster, 'thumb': poster, 'fanart': fanart, 'icon': poster}
            media_type = it.get('media_type', 'movie')
            tmdb_art = self.tmdb.get_art(tmdbid, media_type)
            art.update(tmdb_art)
            info = {'title': title, 'plot': plot, 'rating': float(vote), 'year': year, 'premiered': rdate}
            if media_type == 'movie':
                info['mediatype'] = 'movie'
                play_url = self.build_url({'action':'play', 'tmdbid': str(tmdbid), 'title': title})
                cm = [('选择源', f'RunPlugin({ self.build_url({"action":"select_quality","tmdbid":str(tmdbid),"title":title}) })')]
                self.add_item(title, play_url, is_folder=False, info=info, art=art, context_menu=cm)
            elif media_type == 'tv':
                info['mediatype'] = 'tvshow'
                info['tvshowtitle'] = title
                seasons_url = self.build_url({'action':'show_seasons', 'tmdbid': str(tmdbid), 'title': title})
                self.add_item(f"{title} [TV]", seasons_url, is_folder=True, info=info, art=art)
        cur, total = int(data.get('page', 1)), int(data.get('total_page', 1))
        if cur < total:
            self.add_item(f'下一页 ({cur + 1}/{total})',
                          self.build_url({'action':'show_list_contents', 'list_id': list_id, 'page': str(cur + 1)}),
                          is_folder=True)
        xbmcplugin.endOfDirectory(self.handle, succeeded=True)

    def show_seasons(self, tmdbid, tvshow_title):
        xbmcplugin.setContent(self.handle, 'seasons')
        try:
            data = self.api.get_tv_show(tmdbid)
            num_seasons = data.get('number_of_seasons', 0)
            tv_art = self.tmdb.get_art(tmdbid, 'tv')
            fanart = tv_art.get('fanart', ADDON_FANART)
            for s_num in range(1, num_seasons + 1):
                season_data = self.api.get_season_details(tmdbid, s_num)
                title = season_data.get('name', f'Season {s_num}')
                plot = season_data.get('overview', '')
                art = {'fanart': fanart}
                art.update(self.tmdb.get_season_art(tmdbid, s_num))
                info = {'mediatype': 'season', 'title': title, 'plot': plot, 'tvshowtitle': tvshow_title, 'season': s_num}
                url = self.build_url({'action': 'show_episodes', 'tmdbid': tmdbid, 'season': s_num, 'tvshowtitle': tvshow_title})
                self.add_item(title, url, is_folder=True, info=info, art=art)
            xbmcplugin.endOfDirectory(self.handle, succeeded=True)
        except Exception as e:
            xbmcplugin.endOfDirectory(self.handle, succeeded=False)

    def show_episodes(self, tmdbid, season_number, tvshow_title):
        xbmcplugin.setContent(self.handle, 'episodes')
        try:
            season_data = self.api.get_season_details(tmdbid, season_number)
            episode_count = season_data.get('episode_count', 0)
            tv_art = self.tmdb.get_art(tmdbid, 'tv')
            season_art = self.tmdb.get_season_art(tmdbid, season_number)
            base_art = {'fanart': tv_art.get('fanart', ADDON_FANART), 'poster': season_art.get('poster')}
            for e_num in range(1, episode_count + 1):
                ep_data = self.api.get_episode_details(tmdbid, season_number, e_num)
                title = f"{e_num}. {ep_data.get('name', f'Episode {e_num}')}"
                plot = ep_data.get('overview', '')
                art = base_art.copy()
                art.update(self.tmdb.get_episode_art(tmdbid, season_number, e_num))
                info = {
                    'mediatype': 'episode', 'title': title, 'plot': plot,
                    'tvshowtitle': tvshow_title, 'season': int(season_number), 'episode': e_num,
                    'premiered': ep_data.get('air_date', ''), 'rating': float(ep_data.get('vote_average', 0))
                }
                url = self.build_url({'action': 'select_episode_quality', 'tmdbid': tmdbid, 'season': season_number, 'episode': e_num, 'title': title})
                self.add_item(title, url, is_folder=False, info=info, art=art)
            xbmcplugin.endOfDirectory(self.handle, succeeded=True)
        except Exception as e:
            xbmcplugin.endOfDirectory(self.handle, succeeded=False)

    def play(self, tmdbid, title, source='115', choice_index=None):
        try:
            self.player.play(tmdbid, title, source=source, choice_index=choice_index,
                             prefer_dv=self.prefer_dv, prefer_iso=self.prefer_iso, prefer_4k=self.prefer_4k)
        except Exception as e:
            xbmcgui.Dialog().notification(ADDON_NAME, f'无法播放: {e}', ADDON_ICON, 4000)

    def play_episode(self, tmdbid, season, episode, title, source='115', choice_index=None):
        try:
            self.player.play(tmdbid, title, source=source, media_type='tv',
                             season=season, episode=episode, choice_index=choice_index,
                             prefer_dv=self.prefer_dv, prefer_4k=self.prefer_4k)
        except Exception as e:
            xbmcgui.Dialog().notification(ADDON_NAME, f'无法播放: {e}', ADDON_ICON, 4000)

    def select_episode_quality(self, tmdbid, season, episode, title):
        dialog = xbmcgui.Dialog()
        if self.auto_select:
            self.play_episode(tmdbid, season, episode, title, source='115', choice_index=0)
            return
        options = ["[115 资源包播放 (依赖服务器匹配)]", "[选择磁力链接播放]"]
        choice = dialog.select(f'选择播放方式 - {title}', options)
        if choice == 0:
            self.play_episode(tmdbid, season, episode, title, source='115', choice_index=0)
        elif choice == 1:
            try:
                data = self.api.get_episode_magnet_links(tmdbid, season, episode)
                magnets = data.get('magnet', [])
                if not magnets:
                    dialog.notification(ADDON_NAME, '未找到该集的磁力链接', ADDON_ICON, 3000)
                    return
                labels = [f"磁力 | {m.get('size','?')} | {m.get('name','')}" for m in magnets]
                idx = dialog.select(f'选择磁力源 - {title}', labels)
                if idx >= 0:
                    self.play_episode(tmdbid, season, episode, title, source='magnet', choice_index=idx)
            except Exception as e:
                dialog.notification(ADDON_NAME, f'获取磁力失败: {e}', ADDON_ICON, 4000)

    def clear_cache(self):
        try:
            self.cache.clear()
            import shutil
            import xbmcvfs
            simplecache_addon_id = 'script.module.simplecache'
            simplecache_profile_path = xbmcvfs.translatePath(f'special://profile/addon_data/{simplecache_addon_id}')
            if os.path.exists(simplecache_profile_path):
                try:
                    shutil.rmtree(simplecache_profile_path)
                    xbmc.log(f"[{ADDON_NAME}] Successfully cleared simplecache directory.", xbmc.LOGINFO)
                except Exception as e:
                    xbmc.log(f"[{ADDON_NAME}] Failed to clear simplecache directory: {e}", xbmc.LOGERROR)
            xbmcgui.Dialog().notification(ADDON_NAME, '所有缓存已清理', ADDON_ICON, 3000)
        except Exception as e:
            xbmc.log(f"[{ADDON_NAME}] Clear cache error: {e}", xbmc.LOGERROR)
            xbmcgui.Dialog().notification(ADDON_NAME, f'清理失败: {e}', ADDON_ICON, 4000)

    def router(self):
        q = _get_params()
        action = q.get('action', '').strip()

        if not action:
            self.show_lists()
        elif action == 'refresh_container':
            self.refresh_container()
        elif action == 'show_list_contents':
            self.show_list_contents(q.get('list_id'), q.get('page', '1'))
        elif action == 'show_seasons':
            self.show_seasons(q.get('tmdbid'), q.get('title'))
        elif action == 'show_episodes':
            self.show_episodes(q.get('tmdbid'), q.get('season'), q.get('tvshowtitle'))
        elif action == 'play':
            self.play(q.get('tmdbid'), q.get('title'))
        elif action == 'select_episode_quality':
            self.select_episode_quality(q.get('tmdbid'), q.get('season'), q.get('episode'), q.get('title'))
        elif action == 'clear_cache':
            self.clear_cache()
        else:
            self.show_lists()

if __name__ == '__main__':
    try:
        plugin = NullBRPlugin()
        plugin.router()
    except Exception as e:
        xbmc.log(f'{ADDON_NAME}: fatal error: {e}', xbmc.LOGERROR)
        xbmcgui.Dialog().notification(ADDON_NAME, f'Fatal: {e}', ADDON_ICON, 6000)