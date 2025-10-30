# -*- coding: utf-8 -*-
# server_alist_simplified.py — 简化版 Alist 服务器
# 所有媒体都保存在“云下载”目录，不再移动。
import os, re, time, json
from urllib.parse import unquote
import requests
from flask import Flask, request, jsonify

# ===== ⚙️ 1. 基本配置 (请修改以下内容) =====
PORT = 3000

# --- NullBR API ---
NULLBR_APP_ID  = "你的 NullBR APP_ID"
NULLBR_API_KEY = "你的 NullBR API_KEY"

# --- 115 配置 ---
P115_COOKIE = "你的完整 115 Cookies"
# 目标文件夹 CID (所有磁力都会下载到这里)
TARGET_CID = "你的“云下载”文件夹的 CID"

# --- Alist 和 rclone 配置 ---
ALIST_BASE        = "http://127.0.0.1:5244"  # 你的 Alist 访问地址
ALIST_TOKEN       = "你的 Alist 管理员令牌 (Token)"
# Alist 中 115 网盘的“云下载”文件夹的完整路径
ALIST_OFFLINE_DIR = "/115/云下载"
RCLONE_RC_ADDR    = "http://127.0.0.1:5572" # rclone RC 地址, 保持默认即可

# --- Kodi 播放路径配置 ---
# 你的 rclone 挂载目录的 SMB 共享地址 (Kodi 能访问的地址)
SMB_BASE = "smb://192.168.1.3/rclone_mount"

# ===== ไม่ต้องแก้ไข下面的代码 (除非你知道你在做什么) =====
WAIT_OFFLINE_READY = 180
POLL_INTV          = 3
REFRESH_RETRY      = 3

# (正则、NullBR、Pan115、Alist、RcloneRC、工具函数等代码与原版一致，此处省略以保持简洁)
# ... (此处省略了与原版完全相同的代码块) ...
# 为了保证可运行，下面是完整的代码
requests.packages.urllib3.disable_warnings()
RE_DV      = re.compile(r'\b(dv|dovi|dolby.?vision)\b', re.I)
RE_ISO     = re.compile(r'\.iso\b', re.I)
RE_4K      = re.compile(r'\b(2160p|4k)\b', re.I)
RE_1080    = re.compile(r'\b1080p\b', re.I)
RE_SIZE    = re.compile(r'([\d.]+)\s*(TB|GB|MB)', re.I)
RE_SAMPLE  = re.compile(r'\bsample\b', re.I)
RE_EPISODE = [
    re.compile(r'[._\-\s]S(\d{1,2})E(\d{1,3})[._\-\s]', re.I), re.compile(r'[._\-\s](\d{1,2})x(\d{1,3})[._\-\s]', re.I),
    re.compile(r'[._\-\s]Season[\s._\-]?(\d{1,2})[\s._\-]?Episode[\s._\-]?(\d{1,3})', re.I), re.compile(r'\[(\d{1,2})[\s.]?(\d{2})\]', re.I),
    re.compile(r'[._\-\s]E(\d{2,3})[._\-\s]', re.I),
]
def size_to_bytes(s):
    if not s: return 0
    m = RE_SIZE.search(s)
    if not m: return 0
    v = float(m.group(1)); u = m.group(2).upper()
    return int(v*1024**4) if u=="TB" else int(v*1024**3) if u=="GB" else int(v*1024**2)
def score_tuple(name: str, sizeb: int = 0):
    return (1 if RE_DV.search(name or "") else 0, 1 if RE_ISO.search(name or "") else 0, 1 if RE_4K.search(name or "") or ("2160" in (name or "")) else (0.5 if RE_1080.search(name or "") else 0), sizeb)
class NullBR:
    BASE = "https://api.nullbr.eu.org"
    def __init__(self, app_id, key): self.s = requests.Session(); self.app_id=app_id; self.key=key
    def _get(self, path, need_key=False, **params):
        h={"X-APP-ID": self.app_id};
        if need_key: h["X-API-KEY"] = self.key
        r=self.s.get(f"{self.BASE}{path}", headers=h, params=params, timeout=20, verify=False); r.raise_for_status(); return r.json()
    def movie_meta(self, tmdb): return self._get(f"/movie/{tmdb}")
    def movie_115(self, tmdb): return self._get(f"/movie/{tmdb}/115", True, page=1)
    def movie_magnet(self, tmdb): return self._get(f"/movie/{tmdb}/magnet", True, page=1)
    def tv_meta(self, tmdb): return self._get(f"/tv/{tmdb}")
    def tv_115(self, tmdb): return self._get(f"/tv/{tmdb}/115", True, page=1)
    def tv_magnet(self, tmdb, s, e): return self._get(f"/tv/{tmdb}/season/{s}/episode/{e}/magnet", True, page=1)
class Pan115:
    SNAP="https://webapi.115.com/share/snap"; RECV="https://webapi.115.com/share/receive"; LIXIAN="https://115.com/web/lixian/?ct=lixian&ac=add_task_url"
    LIXIAN_TASK_LISTS = "https://lixian.115.com/lixian/?ct=lixian&ac=task_lists"; LIXIAN_TASK_DEL   = "https://lixian.115.com/lixian/?ct=lixian&ac=task_del"
    def __init__(self, cookie):
        self.s = requests.Session(); self.s.headers.update({"User-Agent":"Mozilla/5.0","Referer":"https://115.com/","Origin":"https://115.com"})
        for kv in cookie.split(";"):
            if "=" in kv: k,v=kv.strip().split("=",1); self.s.cookies.set(k.strip(), v.strip(), domain=".115.com")
    @staticmethod
    def parse_share(url):
        m=re.search(r"/s/([A-Za-z0-9]+)", url);
        if not m: raise ValueError("分享链接无法解析")
        code=m.group(1); pwd=None; m2=re.search(r"[?&]password=([^&#]+)", url)
        if m2: pwd=unquote(m2.group(1))
        return code,pwd
    def snap(self, code, pwd=None):
        r=self.s.get(self.SNAP, params={"share_code":code,"receive_code":pwd or "","offset":"0","limit":"400"}, timeout=20); j=r.json()
        if not j.get("state"): raise RuntimeError(f"snap失败:{j}")
        data=j.get("data",{}) or {}; return data.get("list") or data.get("snap_list") or []
    def receive(self, code, pwd, file_ids, cid):
        r=self.s.post(self.RECV, data={"share_code":code,"receive_code":pwd or "","file_id":",".join(file_ids),"cid":cid}, timeout=25); j=r.json()
        if not j.get("state"):
            err=j.get("error","");
            if "已接收" in err or "已存在" in err: return {"state":True,"skipped":True}
            raise RuntimeError(f"receive失败:{j}")
        return j
    def transfer_share(self, share_link, target_cid):
        code,pwd=self.parse_share(share_link); items=self.snap(code,pwd); fids=[]
        for f in items:
            fid=str(f.get("fid") or f.get("file_id") or f.get("cid") or "");
            if fid: fids.append(fid)
        if not fids: raise RuntimeError("分享里没有可转存文件")
        return self.receive(code,pwd,fids,target_cid)
    def add_magnet(self, magnet_url):
        r=self.s.post(self.LIXIAN, data={"url":magnet_url}, timeout=20);
        try: return r.json()
        except: return {"text": r.text[:200]}
    def get_completed_tasks(self):
        try: r = self.s.post(self.LIXIAN_TASK_LISTS, data={"page": 1, "flag": 0}, timeout=15); j = r.json(); return (j or {}).get("tasks", []) or []
        except Exception as e: print(f"[115] 获取任务列表失败: {e}", flush=True); return []
    def delete_task(self, hash_value):
        try: r = self.s.post(self.LIXIAN_TASK_DEL, data={"hash[0]": hash_value}, timeout=15); j = r.json(); print(f"[115] 删除任务 {hash_value}: {j}", flush=True); return bool((j or {}).get("state"))
        except Exception as e: print(f"[115] 删除任务失败: {e}", flush=True); return False
    def clear_task_by_name(self, target_name):
        try:
            tasks = self.get_completed_tasks();
            if not tasks: return False
            def norm(s): return re.sub(r'[.\-_\s]+', '', (s or '').lower())
            t = norm(target_name)
            for it in tasks:
                name = it.get("name", ""); h = it.get("info_hash") or it.get("hash");
                if not h: continue
                if t in norm(name) or norm(name) in t: return self.delete_task(h)
            return False
        except Exception as e: print(f"[115] 按名删除失败: {e}", flush=True); return False
class AList:
    def __init__(self, base, token): self.base=base.rstrip("/"); self.s=requests.Session(); self.s.headers.update({"Authorization":token,"Content-Type":"application/json"})
    def refresh(self, path, recursive=True):
        payload = {"path": path, "page": 1, "per_page": 1, "refresh": True, "password": ""}
        for i in range(REFRESH_RETRY):
              try:
                  r = self.s.post(f"{self.base}/api/fs/list", data=json.dumps(payload), timeout=15); j = r.json()
                  if j.get("code") == 200: return True
              except Exception as e: print(f"[alist_refresh] 提交错误: {e}", flush=True); time.sleep(1)
        return False
    def listdir(self, path):
        r=self.s.post(f"{self.base}/api/fs/list", data=json.dumps({"path":path,"page":1,"per_page":1000,"password":""}), timeout=15); j=r.json()
        return j.get("data",{}).get("content",[]) if j.get("code")==200 else []
class RcloneRC:
    def __init__(self, addr): self.addr=addr.rstrip("/")
    def vfs_refresh(self, path="", recursive=True):
        try:
            if path == "/": path = ""; path = path.lstrip("/")
            print(f"[rclone] 刷新: '{path}'", flush=True)
            requests.post(f"{self.addr}/vfs/refresh", data={"dir":path,"recursive":"true" if recursive else "false"}, timeout=6)
        except Exception as e: print(f"[rclone] 刷新错误: {e}", flush=True)
def pick_candidates(tmdb, nb: 'NullBR', media_type='movie', season=None, episode=None):
    cands=[];
    try:
        if media_type == 'tv':
            if season and episode:
                for m in (nb.tv_magnet(tmdb, season, episode).get("magnet") or []): cands.append({"src":"magnet","title":m.get("name") or "","magnet":m.get("link") or m.get("magnet") or "","sizeb":size_to_bytes(m.get("size")),"score":score_tuple(m.get("name") or "",size_to_bytes(m.get("size")))})
            for x in (nb.tv_115(tmdb).get("115") or []): cands.append({"src":"115","title":x.get("title") or "","share_link":x.get("share_link"),"sizeb":size_to_bytes(x.get("size")),"score":score_tuple(x.get("title") or "",size_to_bytes(x.get("size")))})
        else:
            for x in (nb.movie_115(tmdb).get("115") or []): cands.append({"src":"115","title":x.get("title") or "","share_link":x.get("share_link"),"sizeb":size_to_bytes(x.get("size")),"score":score_tuple(x.get("title") or "",size_to_bytes(x.get("size")))})
            for m in (nb.movie_magnet(tmdb).get("magnet") or []): cands.append({"src":"magnet","title":m.get("name") or "","magnet":m.get("link") or m.get("magnet") or "","sizeb":size_to_bytes(m.get("size")),"score":score_tuple(m.get("name") or "",size_to_bytes(m.get("size")))})
    except Exception as e: print(f"[pick_candidates] 获取资源出错: {e}", flush=True)
    def boost(c): b=0;
        if re.search(RE_DV, c["title"]): b+=3
        if re.search(RE_ISO, c["title"]): b+=2
        if re.search(RE_4K, c["title"]): b+=1
        return (*c["score"], b)
    cands.sort(key=lambda c: boost(c), reverse=True); return cands
def fuzzy_match(target, candidate):
    def normalize(s): return re.sub(r'[.\-_\s]+', '', s.lower())
    t = normalize(target); c = normalize(candidate); min_len = min(15, len(t), len(c))
    if min_len < 8: return t in c or c in t
    return t[:min_len] in c or c[:min_len] in t
def check_file_exists(item_name, alist: AList):
    print(f"\n[check_exists] 检查: {item_name}", flush=True)
    print(f"[check_exists] 检查云下载...", flush=True)
    alist.refresh(ALIST_OFFLINE_DIR, False); time.sleep(1)
    items = alist.listdir(ALIST_OFFLINE_DIR) or []
    for it in items:
        name = it.get("name", "")
        if fuzzy_match(item_name, name):
            print(f"[check_exists] ✓ 在云下载找到: {name}", flush=True)
            return (name, it)
    print(f"[check_exists] ✗ 未找到", flush=True); return (None, None)
def get_best_video(dir_path, dir_name, alist: AList, s_e_tuple=None):
    print(f"\n[get_video] 扫描目录: {dir_name}", flush=True)
    if s_e_tuple: print(f"[get_video] 目标剧集: S{s_e_tuple[0]:02d}E{s_e_tuple[1]:02d}", flush=True)
    alist.refresh(dir_path, True); time.sleep(1)
    files = alist.listdir(dir_path) or []; print(f"[get_video] 目录内有 {len(files)} 项", flush=True)
    video_exts = {'.mp4', '.mkv', '.avi', '.mov', '.m2ts', '.iso', '.m4v', '.wmv', '.flv', '.ts'}; videos = []
    for f in files:
        if f.get("is_dir"): continue
        fname = f.get("name", ""); ext = os.path.splitext(fname.lower())[1]
        if ext not in video_exts: continue
        if RE_SAMPLE.search(fname): print(f"[get_video]   跳过sample: {fname}", flush=True); continue
        videos.append(f)
    if not videos: print(f"[get_video] ✗ 无有效视频", flush=True); return None
    if s_e_tuple:
        target_s, target_e = s_e_tuple; matched_episodes = []
        for video in videos:
            fname = video.get("name", ""); found_s, found_e = None, None
            for pattern in RE_EPISODE:
                match = pattern.search(fname)
                if match:
                    groups = match.groups()
                    if len(groups) == 2: found_s, found_e = int(groups[0]), int(groups[1])
                    elif len(groups) == 1: found_e = int(groups[0])
                    break
            if found_e == target_e and (found_s is None or found_s == target_s):
                print(f"[get_video]   ✓ 精准匹配: {fname}", flush=True); matched_episodes.append(video)
        if matched_episodes:
            matched_episodes.sort(key=lambda x: score_tuple(x.get("name", ""), x.get("size", 0)), reverse=True)
            best_video = matched_episodes[0]["name"]; print(f"[get_video] ✓✓ 最佳剧集文件: {best_video}", flush=True)
            return f"/{dir_name}/{best_video}"
        else: print(f"[get_video] ✗ 未能精准匹配到 S{target_s:02d}E{target_e:02d}", flush=True); print(f"[get_video]   ! 降级为最大文件匹配", flush=True)
    videos.sort(key=lambda x: (1 if RE_ISO.search(x.get("name","")) else 0, x.get("size", 0)), reverse=True)
    best_video = videos[0]["name"]; print(f"[get_video] ✓ 最佳视频(兜底): {best_video}", flush=True)
    return f"/{dir_name}/{best_video}"
def wait_in_offline(keywords, timeout=WAIT_OFFLINE_READY, interval=POLL_INTV, alist:AList=None):
    print(f"\n[wait_offline] 关键词: {keywords[:2]}", flush=True); deadline=time.time()+timeout; attempt = 0; last_found = None
    while time.time()<deadline:
        attempt += 1; print(f"\n[wait_offline] === 尝试 #{attempt} ===", flush=True)
        alist.refresh(ALIST_OFFLINE_DIR, True); time.sleep(2)
        items = alist.listdir(ALIST_OFFLINE_DIR) or []; print(f"[wait_offline] 云下载中有 {len(items)} 项", flush=True)
        if not items: time.sleep(interval); continue
        best = None
        for it in items:
            name = it.get("name", ""); print(f"[wait_offline] 检查: {name}", flush=True); matched = False
            for kw in keywords:
                if fuzzy_match(kw, name): matched = True; print(f"[wait_offline]   ✓ 匹配关键词: {kw}", flush=True); break
            if not matched: continue
            score = (1 if it.get("is_dir") else 0, it.get("modified", 0), it.get("size", 0))
            if best is None or score > best[0]: best = (score, name, it)
        if best:
            result_name = best[1]
            if last_found == result_name: print(f"[wait_offline] ✓✓✓ 验证通过: {result_name}", flush=True); return result_name
            else: last_found = result_name; print(f"[wait_offline] ✓ 找到候选: {result_name}, 下次验证", flush=True)
        else: last_found = None
        time.sleep(interval)
    print(f"[wait_offline] ✗ 超时", flush=True); return None
nb = NullBR(NULLBR_APP_ID, NULLBR_API_KEY); pan = Pan115(P115_COOKIE); alist = AList(ALIST_BASE, ALIST_TOKEN); rcrc = RcloneRC(RCLONE_RC_ADDR)
app = Flask(__name__)
@app.route("/")
def index(): return "OK"
@app.route("/play")
def play():
    try:
        tmdb = request.args.get("tmdb") or ""; title = request.args.get("title") or ""; media_type = request.args.get("media_type", "movie")
        season_str = request.args.get("season"); episode_str = request.args.get("episode"); s_e_tuple = None
        if not tmdb: return jsonify({"ok":False,"error":"缺少 tmdb"}), 400
        if media_type == 'tv' and season_str and episode_str:
            try: s_e_tuple = (int(season_str), int(episode_str)); print(f"\n{'='*60}\n[play] TV请求: tmdb={tmdb}, S{s_e_tuple[0]:02d}E{s_e_tuple[1]:02d}, title={title}\n{'='*60}\n", flush=True)
            except (ValueError, TypeError): media_type = 'movie'
        if media_type == 'movie': print(f"\n{'='*60}\n[play] 电影请求: tmdb={tmdb}, title={title}\n{'='*60}\n", flush=True)
        try:
            if media_type == 'tv': meta = nb.tv_meta(tmdb)
            else: meta = nb.movie_meta(tmdb)
            if not title: title = meta.get("title") or ""
        except Exception as e: print(f"[meta] 失败: {e}", flush=True)
        cands = pick_candidates(tmdb, nb, media_type, s_e_tuple[0] if s_e_tuple else None, s_e_tuple[1] if s_e_tuple else None)
        if not cands: return jsonify({"ok":False,"error":"无资源"}), 404
        best = cands[0]; print(f"[pick] src={best['src']}, title={best['title']}", flush=True)
        item_name = best["title"]; magnet_hash = None
        found_name, found_item = check_file_exists(item_name, alist)
        if found_name:
            item_name = found_name
            print(f"[exists] 文件已在云下载,直接使用", flush=True)
        else:
            if best["src"] == "115":
                print(f"[115] 转存分享链接到云下载...", flush=True)
                try: res = pan.transfer_share(best["share_link"], TARGET_CID); print(f"[115] 结果: {res}", flush=True)
                except Exception as e: return jsonify({"ok":False,"error":f"115转存失败: {e}"}), 502
            else:
                print(f"[magnet] 添加磁链...", flush=True)
                try:
                    res = pan.add_magnet(best["magnet"]); print(f"[magnet] 结果: {res}", flush=True)
                    if isinstance(res, dict): magnet_hash = res.get("info_hash")
                    if not res.get("state") and "已存在" not in res.get("error_msg", "") and "重复" not in res.get("error_msg", ""): raise RuntimeError(f"磁链失败: {res}")
                except Exception as e: return jsonify({"ok":False,"error":f"磁链失败: {e}"}), 502
            print(f"[wait] 等待文件出现在云下载...", flush=True); time.sleep(3)
            keywords = [best["title"], title, tmdb]
            item_name = wait_in_offline(keywords, alist=alist)
            if not item_name: return jsonify({"ok":False,"error":"云下载超时"}), 504
        print(f"\n[final] 获取最终路径: {item_name}", flush=True)
        alist.refresh(ALIST_OFFLINE_DIR, True); time.sleep(1)
        items = alist.listdir(ALIST_OFFLINE_DIR) or []; matched_item = None
        for it in items:
            name = it.get("name", "")
            if fuzzy_match(item_name, name): matched_item = it; item_name = name; print(f"[final] ✓ 找到项: {name}", flush=True); break
        if not matched_item: return jsonify({"ok":False,"error":"文件在云下载中消失"}), 500
        rel_path = None
        if not matched_item.get("is_dir"): rel_path = f"/{item_name}"; print(f"[final] ✓✓✓ 直接文件: {rel_path}", flush=True)
        else: dir_path = f"{ALIST_OFFLINE_DIR}/{item_name}"; rel_path = get_best_video(dir_path, item_name, alist, s_e_tuple)
        if not rel_path: return jsonify({"ok":False,"error":"目录中无有效视频"}), 404
        # 路径拼接在 Alist 内部，所以需要加上父目录
        final_rel_path = f"{ALIST_OFFLINE_DIR}{rel_path}"
        rcrc.vfs_refresh(ALIST_OFFLINE_DIR.lstrip('/'), True); time.sleep(1)
        try:
            if magnet_hash: pan.delete_task(magnet_hash)
            else: pan.clear_task_by_name(item_name)
        except Exception as e: print(f"[offline] 删除离线任务记录失败: {e}", flush=True)
        smb_full = f"{SMB_BASE}{final_rel_path}"
        print(f"\n{'='*60}\n[SUCCESS] 最终SMB路径: {smb_full}\n{'='*60}\n", flush=True)
        return jsonify({"ok": True, "smb_path": smb_full, "path": final_rel_path})
    except Exception as e:
        print(f"\n[ERROR] {e}", flush=True); import traceback; traceback.print_exc(); return jsonify({"ok":False,"error":str(e)}), 500
if __name__ == "__main__":
    print(f"Server @ http://0.0.0.0:{PORT}", flush=True)
    from werkzeug.serving import WSGIRequestHandler
    WSGIRequestHandler.protocol_version="HTTP/1.1"
    app.run(host="0.0.0.0", port=PORT, debug=False, threaded=True, use_reloader=False)