# -*- coding: utf-8 -*-
import json
import traceback
import sys
from urllib.parse import urlencode

import xbmc
import xbmcgui
import xbmcplugin
import xbmcaddon

try:
    import requests
except Exception:
    requests = None

ADDON = xbmcaddon.Addon()
ADDON_NAME = ADDON.getAddonInfo('name')


class NullBRPlayer:
    """
    仅做“桥接”，不改你插件结构：
      1) 把 default.py 传来的参数原样转给本地服务 /play
      2) 兼容服务返回的多种字段，播放地址优先级：
         (1) path + rclone_mount
         (2) smb_path
         (3) direct_url
         (4) smb（兜底）
         (5) file_path/relative + rclone_mount（兜底）
      3) setResolvedUrl 交给 Kodi 播放
    """

    def __init__(self, server_url, rclone_mount, cookie_uid=None, cookie_cid=None, cookie_seid=None, target_cid=None):
        self.server_url = (server_url or "").rstrip("/")
        self.rclone_mount = (rclone_mount or "").rstrip("/\\")
        self.cookie_uid = cookie_uid or ""
        self.cookie_cid = cookie_cid or ""
        self.cookie_seid = cookie_seid or ""
        self.target_cid = target_cid or ""
        xbmc.log(f"{ADDON_NAME}: Player initialized server={self.server_url}, mount={self.rclone_mount}", xbmc.LOGINFO)

    def _notify(self, msg, time=4000):
        try:
            xbmcgui.Dialog().notification(ADDON_NAME, msg, xbmcgui.NOTIFICATION_INFO, time)
        except Exception:
            xbmc.log(f"{ADDON_NAME}: notify fail: {msg}", xbmc.LOGWARNING)

    def _error(self, msg, time=6000):
        try:
            xbmcgui.Dialog().notification(ADDON_NAME, msg, xbmcgui.NOTIFICATION_ERROR, time)
        except Exception:
            xbmc.log(f"{ADDON_NAME}: error notify fail: {msg}", xbmc.LOGERROR)

    def _resolve_handle(self, explicit_handle=None):
        """尽量稳妥地拿到 handle；支持 default.py 显式传入，也支持从 sys.argv[1] 获取。"""
        if isinstance(explicit_handle, int) and explicit_handle > 0:
            return explicit_handle
        try:
            if len(sys.argv) > 1:
                s = str(sys.argv[1]).strip()
                if s.lstrip("-").isdigit():
                    return int(s)
        except Exception:
            pass
        return 0  # 兜底

    def _fetch_play_info(self, query):
        """
        向本地服务 /play 请求，期望返回 JSON。
        允许返回的字段（至少包含 path/smb_path/smb/file_path/relative/直连之一）：
          - path:       相对路径（不编码），例如：/目录/文件.ext
          - smb_path:   完整 smb:// 路径
          - smb:        完整 smb:// 路径（兼容老字段）
          - file_path:  相对路径（不编码）
          - relative:   相对路径（兼容别名）
          - direct_url: 直连 http(s)
        """
        if not requests:
            self._error("缺少 requests 库")
            return None

        if not self.server_url:
            self._error("未设置服务器地址（Settings 里的 server_url）")
            return None

        url = f"{self.server_url}/play"
        try:
            xbmc.log(f"{ADDON_NAME}: request -> {url}?{urlencode(query)}", xbmc.LOGINFO)
            # 按你的要求，把超时从 30 提到 60 秒
            r = requests.get(url, params=query, timeout=60)
            if r.status_code != 200:
                self._error(f"服务器返回状态码 {r.status_code}")
                return None
            data = r.json()
            xbmc.log(f"{ADDON_NAME}: response <- {json.dumps(data, ensure_ascii=False)[:1024]}", xbmc.LOGINFO)
            return data
        except Exception as e:
            xbmc.log(f"{ADDON_NAME}: HTTP error: {repr(e)}\n{traceback.format_exc()}", xbmc.LOGERROR)
            self._error("本地服务不可达或返回异常")
            return None

    @staticmethod
    def _join_path(base, relative):
        base = (base or "").rstrip("/\\")
        rel = (relative or "").replace("\\", "/")
        if rel and not rel.startswith("/"):
            rel = "/" + rel
        if not base:
            return None
        return f"{base}{rel}"

    def play(self, tmdbid=None, title=None, source=None, handle=None, **kwargs):
        """
        兼容 default.py 传来的所有参数（不要求 default.py 变更）；
        同时也支持未来 default.py 显式传入 handle=... 的写法。
        """
        h = self._resolve_handle(handle)
        try:
            if not tmdbid:
                self._error("缺少 tmdbid，无法播放")
                if h:
                    xbmcplugin.setResolvedUrl(h, False, xbmcgui.ListItem())
                return

            # 组装查询参数：把 default.py 传来的字段原样丢给服务
            query = {"tmdb": tmdbid}
            if title:
                query["title"] = title
            if source:
                query["source"] = source
            for k, v in (kwargs or {}).items():
                if v is None:
                    continue
                query[str(k)] = v

            data = self._fetch_play_info(query)
            if not data or not data.get("ok"):
                self._error("服务未返回可用播放信息")
                if h:
                    xbmcplugin.setResolvedUrl(h, False, xbmcgui.ListItem())
                return

            # 播放地址优先级：
            # 1) path + rclone_mount
            play_path = None
            if data.get("path") and self.rclone_mount:
                play_path = self._join_path(self.rclone_mount, data["path"])

            # 2) smb_path（完整路径）
            if not play_path and data.get("smb_path"):
                play_path = data.get("smb_path")

            # 3) direct_url（直连）
            if not play_path and data.get("direct_url"):
                play_path = data.get("direct_url")

            # 4) smb（兼容老字段）
            if not play_path and data.get("smb"):
                play_path = data.get("smb")

            # 5) file_path/relative + rclone_mount（兜底）
            if not play_path and self.rclone_mount:
                rel = data.get("file_path") or data.get("relative")
                if rel:
                    play_path = self._join_path(self.rclone_mount, rel)

            if not play_path:
                self._error("返回数据中缺少可播放地址")
                if h:
                    xbmcplugin.setResolvedUrl(h, False, xbmcgui.ListItem())
                return

            liz = xbmcgui.ListItem(path=play_path)
            liz.setProperty("IsPlayable", "true")
            if title:
                liz.setLabel(title)

            # 续播点（如果服务返回 resume_offset 单位秒）
            resume_sec = data.get("resume_offset")
            if isinstance(resume_sec, (int, float)) and resume_sec > 0:
                liz.setProperty("ResumeTime", str(float(resume_sec)))
                liz.setProperty("TotalTime", "0")

            if h:
                xbmcplugin.setResolvedUrl(h, True, listitem=liz)
            else:
                # 没拿到句柄也尽量播一下（部分环境仍然会成功）
                xbmc.Player().play(play_path, liz)

        except Exception as e:
            xbmc.log(f"{ADDON_NAME}: player error: {repr(e)}\n{traceback.format_exc()}", xbmc.LOGERROR)
            self._error("播放出错，查看日志以获取详情")
            if h:
                try:
                    xbmcplugin.setResolvedUrl(h, False, xbmcgui.ListItem())
                except Exception:
                    pass
