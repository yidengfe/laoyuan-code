import html
import json
import os
import secrets
import sqlite3
import time
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, "admin.db")
SESSION_TTL_SECONDS = 60 * 60 * 8
SESSIONS: dict[str, dict[str, float | str]] = {}


def db_conn():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with sqlite3.connect(DATABASE) as db:
        with open(os.path.join(BASE_DIR, "schema.sql"), encoding="utf-8") as f:
            db.executescript(f.read())

        admin_exists = db.execute(
            "SELECT id FROM users WHERE username = ?", ("admin",)
        ).fetchone()
        if not admin_exists:
            db.execute(
                "INSERT INTO users (username, role, status) VALUES (?, ?, ?)",
                ("admin", "超级管理员", "启用"),
            )

        products = db.execute("SELECT id FROM products LIMIT 1").fetchall()
        if not products:
            db.executemany(
                "INSERT INTO products (name, category, stock, price) VALUES (?, ?, ?, ?)",
                [
                    ("企业会员", "订阅", 200, 199.0),
                    ("短信包", "增值服务", 5000, 0.08),
                    ("数据看板", "插件", 120, 99.0),
                ],
            )


def read_file(*parts):
    with open(os.path.join(BASE_DIR, *parts), encoding="utf-8") as f:
        return f.read()


def render_login(error=""):
    safe_error = html.escape(error)
    html_content = read_file("templates", "login.html")
    return html_content.replace("{{error}}", safe_error)


def render_dashboard():
    return read_file("templates", "dashboard.html")


class AdminHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlparse(self.path).path

        if path == "/init-db":
            init_db()
            return self.text("数据库初始化完成")

        if path.startswith("/static/"):
            return self.serve_static(path)

        if path == "/login":
            return self.html(render_login())

        if path == "/logout":
            token = self.session_token()
            if token:
                SESSIONS.pop(token, None)
            self.redirect("/login", clear_cookie=True)
            return

        if path == "/":
            if not self.is_auth():
                self.redirect("/login")
                return
            return self.html(render_dashboard())

        if not self.is_auth():
            return self.json_response({"error": "未登录"}, HTTPStatus.UNAUTHORIZED)

        if path == "/api/stats":
            with db_conn() as db:
                users_count = db.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"]
                product_count = db.execute("SELECT COUNT(*) AS c FROM products").fetchone()["c"]
                active_count = db.execute(
                    "SELECT COUNT(*) AS c FROM users WHERE status = ?", ("启用",)
                ).fetchone()["c"]
                total_stock = db.execute(
                    "SELECT COALESCE(SUM(stock),0) AS c FROM products"
                ).fetchone()["c"]
            return self.json_response(
                {
                    "users": users_count,
                    "products": product_count,
                    "active_users": active_count,
                    "total_stock": total_stock,
                }
            )

        if path == "/api/users":
            with db_conn() as db:
                rows = db.execute(
                    "SELECT id, username, role, status, created_at FROM users ORDER BY id DESC"
                ).fetchall()
            return self.json_response([dict(r) for r in rows])

        if path == "/api/products":
            with db_conn() as db:
                rows = db.execute(
                    "SELECT id, name, category, stock, price, created_at FROM products ORDER BY id DESC"
                ).fetchall()
            return self.json_response([dict(r) for r in rows])

        return self.text("Not found", HTTPStatus.NOT_FOUND)

    def do_POST(self):
        path = urlparse(self.path).path

        if path == "/login":
            data = self.form_data()
            username = data.get("username", "").strip()
            password = data.get("password", "").strip()
            if username == "admin" and password == "123456":
                token = secrets.token_hex(16)
                SESSIONS[token] = {
                    "username": username,
                    "expires_at": time.time() + SESSION_TTL_SECONDS,
                }
                self.redirect("/", cookie=token)
                return
            return self.html(render_login("账号或密码错误（默认：admin / 123456）"))

        if not self.is_auth():
            return self.json_response({"error": "未登录"}, HTTPStatus.UNAUTHORIZED)

        if path == "/api/users":
            return self.create_user()

        if path == "/api/products":
            return self.create_product()

        return self.text("Not found", HTTPStatus.NOT_FOUND)

    def do_DELETE(self):
        path = urlparse(self.path).path
        if not self.is_auth():
            return self.json_response({"error": "未登录"}, HTTPStatus.UNAUTHORIZED)

        if path.startswith("/api/users/"):
            user_id = self.extract_id(path)
            if user_id is None:
                return self.json_response({"error": "无效用户ID"}, HTTPStatus.BAD_REQUEST)
            with db_conn() as db:
                db.execute("DELETE FROM users WHERE id = ?", (user_id,))
            return self.json_response({"ok": True})

        if path.startswith("/api/products/"):
            product_id = self.extract_id(path)
            if product_id is None:
                return self.json_response({"error": "无效商品ID"}, HTTPStatus.BAD_REQUEST)
            with db_conn() as db:
                db.execute("DELETE FROM products WHERE id = ?", (product_id,))
            return self.json_response({"ok": True})

        return self.text("Not found", HTTPStatus.NOT_FOUND)

    def create_user(self):
        data, error = self.safe_json_data()
        if error:
            return self.json_response({"error": error}, HTTPStatus.BAD_REQUEST)

        username = data.get("username", "").strip()
        role = data.get("role", "普通管理员").strip() or "普通管理员"
        status = data.get("status", "启用").strip() or "启用"

        if not username:
            return self.json_response({"error": "用户名不能为空"}, HTTPStatus.BAD_REQUEST)
        if status not in {"启用", "禁用"}:
            return self.json_response({"error": "状态必须是 启用/禁用"}, HTTPStatus.BAD_REQUEST)

        try:
            with db_conn() as db:
                db.execute(
                    "INSERT INTO users (username, role, status) VALUES (?, ?, ?)",
                    (username, role, status),
                )
        except sqlite3.IntegrityError:
            return self.json_response({"error": "用户名已存在"}, HTTPStatus.CONFLICT)

        return self.do_GET()

    def create_product(self):
        data, error = self.safe_json_data()
        if error:
            return self.json_response({"error": error}, HTTPStatus.BAD_REQUEST)

        name = data.get("name", "").strip()
        category = data.get("category", "未分类").strip() or "未分类"

        try:
            stock = int(data.get("stock", 0))
            price = float(data.get("price", 0))
        except (TypeError, ValueError):
            return self.json_response({"error": "库存或价格格式不正确"}, HTTPStatus.BAD_REQUEST)

        if not name:
            return self.json_response({"error": "商品名不能为空"}, HTTPStatus.BAD_REQUEST)
        if stock < 0 or price < 0:
            return self.json_response({"error": "库存和价格必须大于等于0"}, HTTPStatus.BAD_REQUEST)

        with db_conn() as db:
            db.execute(
                "INSERT INTO products (name, category, stock, price) VALUES (?, ?, ?, ?)",
                (name, category, stock, price),
            )
        return self.do_GET()

    def form_data(self):
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length).decode("utf-8")
        parsed = parse_qs(raw)
        return {k: v[0] for k, v in parsed.items()}

    def safe_json_data(self):
        length = int(self.headers.get("Content-Length", 0))
        if length <= 0:
            return {}, None

        raw = self.rfile.read(length).decode("utf-8")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return None, "请求体不是合法 JSON"

        if not isinstance(payload, dict):
            return None, "请求体必须是 JSON 对象"
        return payload, None

    @staticmethod
    def extract_id(path):
        try:
            return int(path.rsplit("/", 1)[-1])
        except ValueError:
            return None

    def session_token(self):
        cookie = SimpleCookie(self.headers.get("Cookie"))
        cookie_val = cookie.get("session")
        return cookie_val.value if cookie_val else ""

    def is_auth(self):
        token = self.session_token()
        if not token:
            return False

        session = SESSIONS.get(token)
        if not session:
            return False

        if time.time() > float(session["expires_at"]):
            SESSIONS.pop(token, None)
            return False

        return True

    def html(self, content, status=HTTPStatus.OK):
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(content.encode("utf-8"))

    def text(self, content, status=HTTPStatus.OK):
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(content.encode("utf-8"))

    def json_response(self, payload, status=HTTPStatus.OK):
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps(payload, ensure_ascii=False).encode("utf-8"))

    def redirect(self, location, cookie=None, clear_cookie=False):
        self.send_response(HTTPStatus.FOUND)
        self.send_header("Location", location)
        if cookie:
            self.send_header(
                "Set-Cookie",
                f"session={cookie}; HttpOnly; Path=/; Max-Age={SESSION_TTL_SECONDS}; SameSite=Lax",
            )
        if clear_cookie:
            self.send_header("Set-Cookie", "session=; Max-Age=0; Path=/; SameSite=Lax")
        self.end_headers()

    def serve_static(self, path):
        static_map = {
            "/static/style.css": ("text/css; charset=utf-8", os.path.join(BASE_DIR, "static", "style.css")),
            "/static/app.js": (
                "application/javascript; charset=utf-8",
                os.path.join(BASE_DIR, "static", "app.js"),
            ),
        }

        target = static_map.get(path)
        if not target:
            return self.text("Not found", HTTPStatus.NOT_FOUND)

        content_type, file_path = target
        with open(file_path, "rb") as f:
            content = f.read()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.end_headers()
        self.wfile.write(content)


def run_server(port=8000):
    init_db()
    server = ThreadingHTTPServer(("0.0.0.0", port), AdminHandler)
    print(f"Admin server running on http://127.0.0.1:{port}")
    server.serve_forever()


if __name__ == "__main__":
    run_server()
