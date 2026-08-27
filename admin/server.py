#!/usr/bin/env python3
"""FANS1 Admin — локальный сервер админки блога.

Запуск:  python3 admin/server.py [--port 8765]
Откроется на http://127.0.0.1:8765

Позволяет: писать посты, загружать фото/видео в бесплатное облако
(imgbb для картинок, Cloudinary unsigned для всего), публиковать их
в статический сайт (_site/) и управлять уже опубликованным.
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import mimetypes
import os
import re
import subprocess
import sys
import time
import uuid
import webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib import request as urlreq
from urllib.error import HTTPError, URLError
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
STATIC = Path(__file__).resolve().parent / "static"
CONFIG_PATH = ROOT / "fans1.config.json"
DATA = ROOT / "content" / "posts.json"
SITE_DIR = ROOT / "_site"
UPLOADS_FALLBACK = ROOT / "public" / "uploads"
MAX_UPLOAD = 64 * 1024 * 1024  # 64 МБ на один файл

MONTHS_RU = ["января", "февраля", "марта", "апреля", "мая", "июня",
             "июля", "августа", "сентября", "октября", "ноября", "декабря"]


# ---------------------------------------------------------------- config/data
def load_config() -> dict:
    cfg = {
        "site_title": "FANS1",
        "tagline": "фанатский блог о Формуле-1",
        "cloud": {"provider": "", "imgbb_key": "",
                  "cloudinary_cloud": "", "cloudinary_preset": ""},
    }
    if CONFIG_PATH.exists():
        try:
            saved = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            cfg.update({k: v for k, v in saved.items() if k != "cloud"})
            cfg["cloud"].update(saved.get("cloud") or {})
        except Exception as e:
            print("[config] не удалось прочитать конфиг:", e)
    return cfg


def save_config(cfg: dict) -> None:
    CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2),
                           encoding="utf-8")
    try:
        os.chmod(CONFIG_PATH, 0o600)  # там ключи — только владелец
    except OSError:
        pass


def load_posts() -> list:
    try:
        return json.loads(DATA.read_text(encoding="utf-8"))
    except Exception:
        return []


def save_posts(posts: list) -> None:
    DATA.parent.mkdir(parents=True, exist_ok=True)
    DATA.write_text(json.dumps(posts, ensure_ascii=False, indent=2),
                    encoding="utf-8")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def run_build() -> tuple[bool, str]:
    p = subprocess.run([sys.executable, str(ROOT / "scripts" / "build.py")],
                       capture_output=True, text=True, timeout=120)
    out = (p.stdout + p.stderr).strip()
    return p.returncode == 0, out


# ------------------------------------------------------------------- upload
def _http_json(url: str, obj: dict, timeout: int = 180) -> dict:
    req = urlreq.Request(url,
                         data=json.dumps(obj).encode("utf-8"),
                         headers={"Content-Type": "application/json",
                                  "User-Agent": "fans1-admin/1.0"},
                         method="POST")
    try:
        with urlreq.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except HTTPError as e:
        raise RuntimeError("HTTP %s: %s" % (e.code, e.read().decode("utf-8", "replace")[:300]))
    except URLError as e:
        raise RuntimeError("нет связи с %s: %s" % (url.split("/")[2], e.reason))


def _http_multipart(url: str, fields: dict, files: list, timeout: int = 180) -> dict:
    """files: [(field_name, filename, bytes, mime)]"""
    bnd = "----fans1" + uuid.uuid4().hex
    buf = io.BytesIO()
    for k, v in fields.items():
        buf.write("--%s\r\nContent-Disposition: form-data; name=\"%s\"\r\n\r\n%s\r\n"
                  % (bnd, k, v))
    for name, fname, data, ctype in files:
        buf.write("--%s\r\nContent-Disposition: form-data; name=\"%s\"; filename=\"%s\"\r\n"
                  "Content-Type: %s\r\n\r\n" % (bnd, name, fname, ctype))
        buf.write(data)
        buf.write(b"\r\n")
    buf.write("--%s--\r\n" % bnd)
    req = urlreq.Request(url, data=buf.getvalue(),
                         headers={"Content-Type": "multipart/form-data; boundary=%s" % bnd,
                                  "User-Agent": "fans1-admin/1.0"},
                         method="POST")
    try:
        with urlreq.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except HTTPError as e:
        raise RuntimeError("HTTP %s: %s" % (e.code, e.read().decode("utf-8", "replace")[:300]))
    except URLError as e:
        raise RuntimeError("нет связи с %s: %s" % (url.split("/")[2], e.reason))


def sniff_kind(fname: str, data: bytes, ctype: str) -> str:
    """Видео или картинка — по Content-Type, расширению и магическим байтам."""
    ct = (ctype or "").split(";")[0].strip().lower()
    if ct.startswith("video/"):
        return "video"
    if ct.startswith("image/"):
        return "image"
    ext = Path(fname).suffix.lower()
    if ext in {".mp4", ".m4v", ".webm", ".mov", ".mkv", ".avi", ".ogv"}:
        return "video"
    if ext in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".avif", ".bmp"}:
        return "image"
    head = (data or b"")[:16]
    if head[:4] == b"\x89PNG" or head[:4] == b"GIF8" or head[:3] == b"\xff\xd8\xff":
        return "image"
    if len(head) >= 8 and head[4:8] == b"ftyp":      # mp4 / mov
        return "video"
    if head[:4] == b"\x1a\x45\xdf\xa3":              # webm / mkv
        return "video"
    if head[:4] == b"RIFF" and (data or b"")[8:12] == b"WEBP":
        return "image"
    return "image"


def upload_local(fname: str, data: bytes, ctype: str) -> tuple[str, str]:
    d = UPLOADS_FALLBACK / datetime.now().strftime("%Y-%m")
    d.mkdir(parents=True, exist_ok=True)
    safe = "%s-%s%s" % (datetime.now().strftime("%H%M%S"),
                        re.sub(r"[^A-Za-z0-9_-]", "_", Path(fname).stem)[:40],
                        Path(fname).suffix.lower())
    (d / safe).write_bytes(data)
    rel = "/uploads/%s/%s" % (d.name, safe)
    kind = sniff_kind(fname, data, ctype)
    return kind, rel


def upload_to_cloud(fname: str, data: bytes, ctype: str, cfg: dict) -> tuple[str, str]:
    kind = sniff_kind(fname, data, ctype)
    cl = cfg.get("cloud") or {}
    prov = cl.get("provider")

    if prov == "imgbb":
        if kind == "video":
            raise RuntimeError("imgbb не принимает видео — включите Cloudinary или оставьте локально")
        if len(data) > 32 * 1024 * 1024:
            raise RuntimeError("imgbb: файл больше 32 МБ")
        j = _http_multipart(
            "https://api.imgbb.com/1/upload",
            {"key": cl.get("imgbb_key", ""), "name": Path(fname).stem[:50]},
            [("image", Path(fname).name, data, ctype)])
        if int(j.get("status_code", 400)) != 200:
            raise RuntimeError("imgbb отказал: %s" % json.dumps(j.get("error"))[:200])
        d = j["data"]
        return "image", d.get("display_url") or d["url"]

    if prov == "cloudinary":
        cloud = cl.get("cloudinary_cloud", "")
        preset = cl.get("cloudinary_preset", "")
        rt = "video" if kind == "video" else "image"
        url = "https://api.cloudinary.com/v1_1/%s/%s/upload" % (cloud, rt)
        b64 = "data:%s;base64,%s" % (ctype, base64.b64encode(data).decode())
        j = _http_json(url, {"upload_preset": preset, "file": b64},
                       timeout=300)
        if not j.get("secure_url"):
            raise RuntimeError("Cloudinary отказал: %s" % json.dumps(j)[:200])
        return kind, j["secure_url"]

    raise RuntimeError("не настроено")


# --------------------------------------------------------------- inbound mp
def parse_multipart(body: bytes, header_ctype: str) -> list:
    m = re.search(r'boundary=(?:"([^"]+)"|([^;,\s]+))', header_ctype or "")
    if not m:
        return []
    delim = b"--" + (m.group(1) or m.group(2)).strip().encode()
    parts = []
    for seg in body.split(delim):
        seg = seg.strip(b"\r\n ")
        if not seg or seg == b"--":
            continue
        if b"\r\n\r\n" not in seg:
            continue
        head, _, payload = seg.partition(b"\r\n\r\n")
        info = {"filename": "", "ctype": "application/octet-stream", "name": ""}
        disp = ""
        for line in head.decode("latin-1").split("\r\n"):
            low = line.lower()
            if low.startswith("content-disposition"):
                disp = line
            elif low.startswith("content-type"):
                info["ctype"] = line.split(":", 1)[1].strip()
        fn = re.search(r'filename\*="?([^";]+)"?', disp)
        fn2 = re.search(r'filename="([^"]*)"', disp)
        nm = re.search(r'name="([^"]*)"', disp)
        if fn:
            info["filename"] = fn.group(1).split("''")[-1]
        elif fn2:
            info["filename"] = fn2.group(1)
        if nm:
            info["name"] = nm.group(1)
        info["data"] = payload
        parts.append(info)
    return parts


# ------------------------------------------------------------------ server
class Handler(BaseHTTPRequestHandler):
    server_version = "Fans1Admin/1.0"

    # helpers ---------------------------------------------------------------
    def _send(self, code: int, body: bytes, ctype: str, extra=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code: int = 200):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _read_body(self) -> bytes:
        n = int(self.headers.get("Content-Length") or 0)
        if n > MAX_UPLOAD * 2:
            raise ValueError("слишком большой запрос")
        return self.rfile.read(n)

    def log_message(self, fmt, *args):
        sys.stdout.write("[admin] %s\n" % (fmt % args))

    # GET -------------------------------------------------------------------
    def do_GET(self):
        path = self.path.rstrip("/") or "/"
        if path.startswith("/api/"):
            if path == "/api/config":
                cfg = load_config()
                mask = lambda s: (("••••" + s[-4:]) if s else "")
                return self._json({
                    "configured": cfg["cloud"]["provider"] != "",
                    "provider": cfg["cloud"]["provider"],
                    "cloudinary_cloud": cfg["cloud"].get("cloudinary_cloud", ""),
                    "imgbb_key_masked": mask(cfg["cloud"].get("imgbb_key", "")),
                    "cloudinary_preset_masked": mask(cfg["cloud"].get("cloudinary_preset", "")),
                })
            if path == "/api/posts":
                slim = []
                for p in sorted(load_posts(),
                                key=lambda x: x.get("date", ""), reverse=True):
                    media = p.get("media") or []
                    thumb = ""
                    for m in media:
                        u = m.get("url", "")
                        if m.get("type") == "image":
                            if "res.cloudinary.com" in u:
                                u = u.replace("/upload/", "/upload/c_fill,w_200,h_113,q_auto/")
                            thumb = u
                            break
                    slim.append({"id": p.get("id"), "title": p.get("title"),
                                 "slug": p.get("slug"), "date": p.get("date"),
                                 "updated": p.get("updated"),
                                 "tags": p.get("tags") or [],
                                 "media_n": len(media),
                                 "media": [{"type": m.get("type"), "url": m.get("url")}
                                           for m in media],
                                 "thumb": thumb,
                                 "body": p.get("body") or ""})
                return self._json({"posts": slim})
            return self._json({"ok": False, "error": "unknown api"}, 404)

        # статика админки
        if path == "/" or path.endswith("/admin"):
            f = STATIC / "admin.html"
            return self._send(200, f.read_bytes(), "text/html; charset=utf-8")
        if path.startswith("/static/"):
            base = STATIC.resolve()
            f = (base / path[len("/static/"):]).resolve()
            if f.is_file() and f.is_relative_to(base):
                ct = mimetypes.guess_type(str(f))[0] or "application/octet-stream"
                return self._send(200, f.read_bytes(), ct)
            return self._send(404, b"not found", "text/plain")
        if path.startswith("/assets/"):
            base = (ROOT / "assets").resolve()
            f = (base / path[len("/assets/"):]).resolve()
            if f.is_file() and f.is_relative_to(base):
                ct = mimetypes.guess_type(str(f))[0] or "application/octet-stream"
                return self._send(200, f.read_bytes(), ct)
            return self._send(404, b"not found", "text/plain")

        # предпросмотр собранного сайта
        if path == "/site":
            f = SITE_DIR / "index.html"
            if f.is_file():
                return self._send(200, f.read_bytes(), "text/html; charset=utf-8")
            return self._send(404, "сайт ещё не собран — опубликуй первый пост".encode("utf-8"),
                              "text/plain; charset=utf-8")
        if path.startswith("/site/"):
            f = SITE_DIR / path[len("/site/"):]
            if f.is_dir():
                f = f / "index.html"
            if f.is_file() and f.resolve().is_relative_to(SITE_DIR.resolve()):
                if f.suffix == ".html":
                    ct = "text/html; charset=utf-8"
                else:
                    ct = mimetypes.guess_type(str(f))[0] or "application/octet-stream"
                return self._send(200, f.read_bytes(), ct)
            return self._send(404, "нет такой страницы сайта".encode("utf-8"),
                              "text/plain; charset=utf-8")

        # локальные загрузки (превью медиа из public/uploads)
        if path.startswith("/uploads/"):
            f = UPLOADS_FALLBACK / path[len("/uploads/"):]
            if f.is_file() and f.resolve().is_relative_to(UPLOADS_FALLBACK.resolve()):
                ct = mimetypes.guess_type(str(f))[0] or "application/octet-stream"
                return self._send(200, f.read_bytes(), ct)
            return self._send(404, b"not found", "text/plain")

        self._send(404, b"not found", "text/plain")

    # POST ------------------------------------------------------------------
    def do_POST(self):
        path = self.path.rstrip("/")
        try:
            if path == "/api/upload":
                body = self._read_body()
                parts = [p for p in parse_multipart(body, self.headers.get("Content-Type"))
                         if p["filename"]]
                if not parts:
                    return self._json({"ok": False, "error": "нет файлов"}, 400)
                cfg = load_config()
                results = []
                for p in parts:
                    if len(p["data"]) > MAX_UPLOAD:
                        results.append({"file": p["filename"], "ok": False,
                                        "error": "> 64 МБ"})
                        continue
                    try:
                        kind, url = upload_to_cloud(p["filename"], p["data"],
                                                    p["ctype"], cfg)
                    except Exception as e:
                        kind, url = upload_local(p["filename"], p["data"], p["ctype"])
                        results.append({"file": p["filename"], "ok": True,
                                        "kind": kind, "url": url,
                                        "warning": "облако недоступно (%s) — сохранено локально в public/" % e})
                        continue
                    results.append({"file": p["filename"], "ok": True,
                                    "kind": kind, "url": url})
                return self._json({"ok": True, "files": results})

            if path == "/api/post/save":
                payload = json.loads(self._read_body().decode("utf-8"))
                resp = self._save_post(payload)
                return self._json(resp)

            if path == "/api/post/delete":
                pid = json.loads(self._read_body().decode("utf-8")).get("id")
                posts = load_posts()
                left = [p for p in posts if p.get("id") != pid]
                if len(left) == len(posts):
                    return self._json({"ok": False, "error": "пост не найден"}, 404)
                save_posts(left)
                ok, out = run_build()
                return self._json({"ok": True, "deleted": pid, "build": out})

            if path == "/api/config/save":
                inc = json.loads(self._read_body().decode("utf-8"))
                cfg = load_config()
                cfg["site_title"] = (inc.get("site_title") or cfg["site_title"]).strip()
                cfg["tagline"] = inc.get("tagline", cfg["tagline"]).strip()
                c = cfg["cloud"]
                if inc.get("provider") in ("", "imgbb", "cloudinary"):
                    c["provider"] = inc["provider"]
                for k in ("imgbb_key", "cloudinary_cloud", "cloudinary_preset"):
                    if inc.get(k):          # пустое = не менять
                        c[k] = inc[k].strip()
                save_config(cfg)
                return self._json({"ok": True, "saved": True})

            if path == "/api/deploy":
                d = subprocess.run(
                    ["vercel", "--prod", "--yes"],
                    cwd=str(SITE_DIR), capture_output=True, text=True, timeout=300,
                    env={**os.environ, "CI": "1"})
                out = (d.stdout + d.stderr).strip()
                ok = d.returncode == 0
                return self._json({"ok": ok, "log": out[-1200:] if ok else out,
                                   "error": None if ok else "vercel вернул ошибку"})

            return self._json({"ok": False, "error": "unknown api"}, 404)
        except Exception as e:
            import traceback
            traceback.print_exc()
            return self._json({"ok": False, "error": str(e)}, 500)

    # логика сохранения поста -------------------------------------------------
    def _save_post(self, payload: dict) -> dict:
        title = (payload.get("title") or "").strip()
        body = (payload.get("body") or "").strip()
        if not title and not body:
            raise ValueError("пустой пост")
        if not title:
            title = (body[:60] + ("…" if len(body) > 60 else "")).strip()

        slug = re.sub(r"\s+", "-", (payload.get("slug") or "").strip()).strip("-.").lower()
        if not slug:
            from admin_md_lite import translit_ru
            slug = translit_ru(title)
        slug = slug[:70]

        media = []
        for m in payload.get("media") or []:
            u = (m.get("url") or "").strip()
            t = m.get("type") or ("video" if m.get("mime", "").startswith("video") else "image")
            if u:
                media.append({"type": t, "url": u,
                              **({"poster": m["poster"]} if m.get("poster") else {})})

        posts = load_posts()
        ts = now_iso()
        edit_id = payload.get("editing_id")
        existing = next((p for p in posts if p.get("id") == edit_id), None)

        if existing:
            changed = (title != existing.get("title") or body != existing.get("body")
                       or slug != existing.get("slug")
                       or media != existing.get("media")
                       or sorted(payload.get("tags") or []) != sorted(existing.get("tags") or []))
            pid = existing["id"]
            created = existing.get("created") or existing.get("date") or ts
            upd = ts if changed else existing.get("updated")
        else:
            pid = "p-%s-%s" % (ts[:10], uuid.uuid4().hex[:6])
            created = ts
            upd = None

        # уникальный slug среди других постов
        others = [p for p in posts if p.get("id") != pid]
        taken = {p.get("slug") for p in others}
        base = slug
        i = 2
        while slug in taken:
            slug = "%s-%d" % (base, i)
            i += 1

        post = {"id": pid, "slug": slug, "title": title, "body": body,
                "tags": [t.strip("# ") for t in (payload.get("tags") or []) if t.strip()],
                "media": media,
                "date": existing.get("date") if existing else created,
                "created": created}
        if upd:
            post["updated"] = upd

        if existing:
            posts[posts.index(existing)] = post
        else:
            posts.append(post)
        save_posts(posts)

        ok, out = run_build()
        if not ok:
            return {"ok": False, "error": "сборка не удалась:\n" + out}
        return {"ok": True, "post": {"id": pid, "slug": slug, "title": title,
                                     "new": not bool(existing)},
                "build": out}


# --------------------------------------------------------- translit helper
def translit_ru(s: str) -> str:
    TR = {"а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e",
          "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
          "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
          "ф": "f", "х": "h", "ц": "c", "ч": "ch", "ш": "sh", "щ": "sch",
          "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya"}
    t = "".join(TR.get(ch, ch) for ch in s.lower())
    t = re.sub(r"[^a-z0-9]+", "-", t).strip("-")[:60]
    return t or "post-%d" % int(time.time())


sys.modules.setdefault("admin_md_lite", type(sys)("admin_md_lite"))
sys.modules["admin_md_lite"].translit_ru = translit_ru


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args()

    for d in (ROOT / "content", ROOT / "public" / "uploads", SITE_DIR):
        d.mkdir(parents=True, exist_ok=True)
    if not DATA.exists():
        save_posts([])

    # пробуем порт и соседние
    srv = None
    for port in range(a.port, a.port + 15):
        try:
            srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
            url = "http://127.0.0.1:%d" % port
            break
        except OSError:
            continue
    if srv is None:
        print("Не удалось занять порт %d…%d" % (a.port, a.port + 14))
        return

    print("=" * 46)
    print(" FANS1 админка запущена:", url)
    print(" Открыть сайт-предпросмотр:", url + "/site/")
    print(" Логи публикаций появятся здесь. Ctrl+C — останов.")
    print("=" * 46)
    if not a.no_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nПока!")


if __name__ == "__main__":
    main()
