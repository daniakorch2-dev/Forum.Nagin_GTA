#!/usr/bin/env python3
"""NAGIN GTA forum | KDE Studio - HTTP-сервер (без сторонніх залежностей)."""
import mimetypes
import os
import re
import sys
import time
import traceback
from email import policy
from email.parser import BytesParser
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit, unquote

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import config as C  # noqa: E402
from app import db as DB  # noqa: E402
from app import web  # noqa: E402
from app.security import hash_token  # noqa: E402

# Підключення модулів з маршрутами
from app.views import auth, forum, profile, apps, orgs, admin, misc  # noqa: E402,F401

MAX_BODY = 1024 * 1024
MAX_UPLOAD = int(C.CONFIG["max_avatar_mb"]) * 1024 * 1024 + 64 * 1024

CSP = ("default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; "
       "form-action 'self'; frame-ancestors 'none'; base-uri 'self'")


def parse_multipart(ctype, body):
    raw = b"Content-Type: " + ctype.encode("latin-1", "replace") + b"\r\nMIME-Version: 1.0\r\n\r\n" + body
    msg = BytesParser(policy=policy.HTTP).parsebytes(raw)
    form, files = {}, {}
    if not msg.is_multipart():
        return form, files
    for part in msg.iter_parts():
        name = part.get_param("name", header="content-disposition")
        if not name:
            continue
        filename = part.get_filename()
        data = part.get_payload(decode=True) or b""
        if filename is not None:
            files[name] = (filename, data, part.get_content_type())
        else:
            form[name] = data.decode("utf-8", "replace")
    return form, files


class Handler(BaseHTTPRequestHandler):
    server_version = "NaginForum"
    sys_version = ""
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        if os.environ.get("NAGIN_QUIET"):
            return
        sys.stderr.write("%s %s\n" % (time.strftime("%H:%M:%S"), fmt % args))

    # ------------------------------------------------------------ утиліти
    def client_ip(self):
        if C.CONFIG["trust_proxy"]:
            xff = self.headers.get("X-Forwarded-For")
            if xff:
                return xff.split(",")[0].strip()[:64]
        return self.client_address[0]

    def send_response_obj(self, resp, head_only=False):
        self.send_response(resp.status)
        has_cache = False
        for k, v in resp.headers:
            self.send_header(k, v)
            if k.lower() == "cache-control":
                has_cache = True
        if not has_cache:
            self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "same-origin")
        self.send_header("Content-Security-Policy", CSP)
        self.send_header("Content-Length", str(len(resp.body)))
        self.end_headers()
        if not head_only:
            self.wfile.write(resp.body)

    def serve_file(self, path, head_only):
        try:
            with open(path, "rb") as f:
                data = f.read()
        except OSError:
            return Response404()
        ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
        if ctype.startswith("text/"):
            ctype += "; charset=utf-8"
        return web.Response(data, ctype=ctype, headers=[("Cache-Control", "public, max-age=300")])

    # ------------------------------------------------------------ головна обробка
    def handle_any(self, method):
        head_only = method == "HEAD"
        if head_only:
            method = "GET"
        parts = urlsplit(self.path)
        path = unquote(parts.path)

        # статика та аватарки без БД
        if method == "GET" and path.startswith("/static/"):
            rel = path[len("/static/"):]
            full = os.path.normpath(os.path.join(C.STATIC, rel))
            if not full.startswith(os.path.normpath(C.STATIC) + os.sep) or not os.path.isfile(full):
                return self.send_response_obj(web.Response(b"Not found", 404, "text/plain; charset=utf-8"), head_only)
            return self.send_response_obj(self.serve_file(full, head_only), head_only)
        if method == "GET" and path.startswith("/avatar/"):
            name = path[len("/avatar/"):]
            if not re.match(r"^[a-f0-9]{32}\.(png|jpg|gif|webp)$", name):
                return self.send_response_obj(web.Response(b"Not found", 404, "text/plain; charset=utf-8"), head_only)
            full = os.path.join(C.UPLOADS, "avatars", name)
            if not os.path.isfile(full):
                return self.send_response_obj(web.Response(b"Not found", 404, "text/plain; charset=utf-8"), head_only)
            return self.send_response_obj(self.serve_file(full, head_only), head_only)

        # тіло запиту
        body = b""
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = 0
        ctype = self.headers.get("Content-Type") or ""
        limit = MAX_UPLOAD if ctype.startswith("multipart/form-data") else MAX_BODY
        if length > limit:
            self.close_connection = True
            resp = web.Response("Занадто великий запит.", 413, "text/plain; charset=utf-8")
            return self.send_response_obj(resp, head_only)
        if length:
            body = self.rfile.read(length)

        form, files = {}, {}
        if method == "POST":
            if ctype.startswith("application/x-www-form-urlencoded"):
                form = {k: v[0] for k, v in parse_qs(body.decode("utf-8", "replace"), keep_blank_values=True).items()}
            elif ctype.startswith("multipart/form-data"):
                try:
                    form, files = parse_multipart(ctype, body)
                except Exception:
                    form, files = {}, {}

        query = {k: v[0] for k, v in parse_qs(parts.query, keep_blank_values=True).items()}
        cookies = {}
        try:
            sc = SimpleCookie()
            sc.load(self.headers.get("Cookie") or "")
            cookies = {k: m.value for k, m in sc.items()}
        except Exception:
            cookies = {}

        conn = DB.connect()
        req = web.Request(method, path, query, self.headers, cookies, form, files, self.client_ip(), conn)
        try:
            self.load_session(req)
            if method == "POST":
                origin = self.headers.get("Origin")
                is_api = path.startswith("/api/")  # ігровий сервер, захист ключем X-Api-Key
                if not is_api and origin and urlsplit(origin).netloc != (self.headers.get("Host") or ""):
                    raise web.HttpError(403, "Запит відхилено: чужий Origin.")
                if not is_api and not req.csrf_ok():
                    raise web.HttpError(403, "Недійсний токен форми. Оновіть сторінку й спробуйте ще раз.")
            resp = web.dispatch(req)
            conn.commit()
        except web.Redirect as r:
            conn.commit()
            resp = web.Response(b"", r.status, "text/plain; charset=utf-8", [("Location", r.url)])
        except web.HttpError as e:
            conn.rollback()
            resp = web.error_page(req, e.status, e.message)
        except Exception:
            conn.rollback()
            traceback.print_exc()
            try:
                resp = web.error_page(req, 500)
            except Exception:
                resp = web.Response("Помилка сервера", 500, "text/plain; charset=utf-8")
        finally:
            conn.close()

        for c in req._set_cookies:
            resp.headers.append(("Set-Cookie", c))
        self.send_response_obj(resp, head_only)

    def load_session(self, req):
        sid = req.cookies.get("sid")
        if not sid:
            return
        sh = hash_token(sid)
        row = req.db.execute("SELECT * FROM sessions WHERE id = ?", (sh,)).fetchone()
        if not row or row["expires_at"] < req.now:
            req.clear_cookie("sid")
            if row:
                req.db.execute("DELETE FROM sessions WHERE id = ?", (sh,))
            return
        user = web.load_user(req.db, row["user_id"])
        if not user:
            req.clear_cookie("sid")
            return
        req.user = user
        req.session_id = sh
        if req.now - user.row["last_seen"] > 60:
            req.db.execute("UPDATE users SET last_seen = ? WHERE id = ?", (req.now, user.id))

    def do_GET(self):
        self.handle_any("GET")

    def do_HEAD(self):
        self.handle_any("HEAD")

    def do_POST(self):
        self.handle_any("POST")


def Response404():
    return web.Response(b"Not found", 404, "text/plain; charset=utf-8")


def cleanup():
    conn = DB.connect()
    now = int(time.time())
    conn.execute("DELETE FROM sessions WHERE expires_at < ?", (now,))
    conn.execute("DELETE FROM email_tokens WHERE expires_at < ?", (now - 86400,))
    conn.commit()
    conn.close()


def main():
    DB.init_db()
    cleanup()
    host, port = C.CONFIG["host"], int(C.CONFIG["port"])
    srv = ThreadingHTTPServer((host, port), Handler)
    srv.daemon_threads = True
    print("=" * 60)
    print(" NAGIN GTA | Форум запущено")
    print(" Адреса:  http://%s:%d/" % ("127.0.0.1" if host in ("0.0.0.0", "") else host, port))
    print(" Пошта:   %s" % ("SMTP %s" % C.CONFIG["smtp"]["host"] if C.CONFIG["smtp"]["host"]
                            else "SMTP не налаштовано: листи з посиланнями будуть у цьому вікні та в data/outbox"))
    print(" Зупинити: Ctrl+C")
    print("=" * 60)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nЗупинено.")


if __name__ == "__main__":
    main()
