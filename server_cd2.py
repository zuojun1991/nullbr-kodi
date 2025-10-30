# -*- coding: utf-8 -*-
# server_cd2_direct_mount.py — CD2/直接挂载版服务器
# 无需 Alist 和 rclone，直接操作本地挂载路径。
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

# --- 挂载路径配置 (最关键！) ---
# 你的 115 网盘被挂载到本机的绝对路径
# Windows 示例: "G:\\115"
# Linux / CoreELEC 示例: "/mnt/115"
LOCAL_MOUNT_PATH = "你的 115 网盘的本地挂载根目录"

# Kodi 访问这个挂载目录的路径 (例如 SMB 共享地址)
# Windows 示例: "smb://192.168.1.3/115_share"
# Linux / CoreELEC 示例: "/mnt/115" (如果 Kodi 和服务器在同一台机器)
KODI_ACCESS_PATH = "Kodi 能访问到的挂载根目录路径"

# 115 网盘内的“云下载”文件夹名称 (通常不需要修改)
OFFLINE_SUBDIR_NAME = "云下载"

# ===== ไม่ต้องแก้ไข下面的代码 (除非你知道你在做什么) =====
WAIT_OFFLINE_READY = 180
POLL_INTV          = 3

# (正则、NullBR、Pan115、工具函数等代码与原版一致，此处省略以保持简洁)
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
# --- 本地文件操作函数 ---
def check_file_exists_local(item_name, offline_dir_path):
    print(f"\n[check_exists] 检查本地目录: {offline_dir_path}", flush=True)
    if not os.path.isdir(offline_dir_path): print(f"[check_exists] ✗ 目录不存在", flush=True); return None, None
    for name in os.listdir(offline_dir_path):
        if fuzzy_match(item_name, name):
            print(f"[check_exists] ✓ 在本地找到: {name}", flush=True)
            full_path = os.path.join(offline_dir_path, name)
            return name, {"name": name, "is_dir": os.path.isdir(full_path)}
    print(f"[check_exists] ✗ 未找到", flush=True); return None, None
def get_best_video_local(dir_path, s_e_tuple=None):
    print(f"\n[get_video] 扫描本地目录: {dir_path}", flush=True)
    if s_e_tuple: print(f"[get_video] 目标剧集: S{s_e_tuple[0]:02d}E{s_e_tuple[1]:02d}", flush=True)
    video_exts = {'.mp4', '.mkv', '.avi', '.mov', '.m2ts', '.iso', '.m4v', '.wmv', '.flv', '.ts'}; videos = []
    for fname in os.listdir(dir_path):
        full_path = os.path.join(dir_path, fname)
        if os.path.isdir(full_path): continue
        ext = os.path.splitext(fname.lower())[1]
        if ext not in video_exts: continue
        if RE_SAMPLE.search(fname): print(f"[get_video]   跳过sample: {fname}", flush=True); continue
        videos.append({"name": fname, "size": os.path.getsize(full_path)})
    if not videos: print(f"[get_video] ✗ 无有效视频", flush=True); return None
    if s_e_tuple:
        target_s, target_e = s_e_tuple; matched_episodes = []
        for video in videos:
            fname = video["name"]; found_s, found_e = None, None
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
            matched_episodes.sort(key=lambda x: score_tuple(x["name"], x["size"]), reverse=True)
            best_video = matched_episodes[0]["name"]; print(f"[get_video] ✓✓ 最佳剧集文件: {best_video}", flush=True)
            return best_video
    videos.sort(key=lambda x: (1 if RE_ISO.search(x["name"]) else 0, x["size"]), reverse=True)
    best_video = videos[0]["name"]; print(f"[get_video] ✓ 最佳视频(兜底): {best_video}", flush=True)
    return best_video
def wait_in_offline_local(keywords, offline_dir_path, timeout=WAIT_OFFLINE_READY, interval=POLL_INTV):
    print(f"\n[wait_offline] 轮询本地目录: {offline_dir_path}", flush=True); deadline=time.time()+timeout
    while time.time()<deadline:
        if os.path.isdir(offline_dir_path):
            for name in os.listdir(offline_dir_path):
                for kw in keywords:
                    if fuzzy_match(kw, name):
                        print(f"[wait_offline] ✓ 找到: {name}", flush=True); return name
        time.sleep(interval)
    print(f"[wait_offline] ✗ 超时", flush=True); return None
nb = NullBR(NULLBR_APP_ID, NULLBR_API_KEY); pan = Pan115(P115_COOKIE)
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
        offline_dir_path = os.path.join(LOCAL_MOUNT_PATH, OFFLINE_SUBDIR_NAME)
        found_name, found_item = check_file_exists_local(item_name, offline_dir_path)
        if found_name:
            item_name = found_name
            print(f"[exists] 文件已在本地,直接使用", flush=True)
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
            print(f"[wait] 等待文件出现在本地挂载...", flush=True); time.sleep(5) # 等待CD2同步
            keywords = [best["title"], title, tmdb]
            item_name = wait_in_offline_local(keywords, offline_dir_path)
            if not item_name: return jsonify({"ok":False,"error":"云下载超时"}), 504
            found_name, found_item = check_file_exists_local(item_name, offline_dir_path)
        print(f"\n[final] 获取最终路径: {item_name}", flush=True)
        if not found_item: return jsonify({"ok":False,"error":"文件在本地消失"}), 500
        rel_path = None
        if not found_item["is_dir"]:
            rel_path = f"/{OFFLINE_SUBDIR_NAME}/{item_name}"
            print(f"[final] ✓✓✓ 直接文件: {rel_path}", flush=True)
        else:
            local_dir_path = os.path.join(offline_dir_path, item_name)
            best_video_file = get_best_video_local(local_dir_path, s_e_tuple)
            if not best_video_file: return jsonify({"ok":False,"error":"目录中无有效视频"}), 404
            rel_path = f"/{OFFLINE_SUBDIR_NAME}/{item_name}/{best_video_file}"
        try:
            if magnet_hash: pan.delete_task(magnet_hash)
            else: pan.clear_task_by_name(item_name)
        except Exception as e: print(f"[offline] 删除离线任务记录失败: {e}", flush=True)
        # 路径拼接，需要处理 Windows 和 Linux 的斜杠问题
        final_access_path = os.path.join(KODI_ACCESS_PATH, rel_path.lstrip('/')).replace('\\', '/')
        print(f"\n{'='*60}\n[SUCCESS] 最终播放路径: {final_access_path}\n{'='*60}\n", flush=True)
        return jsonify({"ok": True, "smb_path": final_access_path, "path": final_access_path})
    except Exception as e:
        print(f"\n[ERROR] {e}", flush=True); import traceback; traceback.print_exc(); return jsonify({"ok":False,"error":str(e)}), 500
if __name__ == "__main__":
    print(f"Server @ http://0.0.0.0:{PORT}", flush=True)
    from werkzeug.serving import WSGIRequestHandler
    WSGIRequestHandler.protocol_version="HTTP/1.1"
    app.run(host="0.0.0.0", port=PORT, debug=False, threaded=True, use_reloader=False)