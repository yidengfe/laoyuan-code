import http.cookiejar
import json
import os
import subprocess
import tempfile
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


class AdminSystemTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.TemporaryDirectory()
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"

        repo_root = Path(__file__).resolve().parents[1]
        app_src = repo_root / "app.py"
        schema_src = repo_root / "schema.sql"
        templates_src = repo_root / "templates"
        static_src = repo_root / "static"

        workdir = Path(cls.tmpdir.name)
        (workdir / "app.py").write_text(app_src.read_text(encoding="utf-8"), encoding="utf-8")
        (workdir / "schema.sql").write_text(schema_src.read_text(encoding="utf-8"), encoding="utf-8")
        (workdir / "templates").mkdir()
        (workdir / "static").mkdir()

        for name in ["login.html", "dashboard.html"]:
            (workdir / "templates" / name).write_text(
                (templates_src / name).read_text(encoding="utf-8"), encoding="utf-8"
            )
        for name in ["style.css", "app.js"]:
            (workdir / "static" / name).write_text(
                (static_src / name).read_text(encoding="utf-8"), encoding="utf-8"
            )

        cls.proc = subprocess.Popen(
            ["python3", "app.py"], cwd=workdir, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        time.sleep(1.2)

        cls.base = "http://127.0.0.1:8000"
        cj = http.cookiejar.CookieJar()
        cls.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

    @classmethod
    def tearDownClass(cls):
        cls.proc.terminate()
        cls.proc.wait(timeout=5)
        cls.tmpdir.cleanup()

    def login(self):
        data = urllib.parse.urlencode({"username": "admin", "password": "123456"}).encode()
        req = urllib.request.Request(f"{self.base}/login", data=data, method="POST")
        self.opener.open(req)

    def test_login_and_dashboard(self):
        self.login()
        html = self.opener.open(f"{self.base}/").read().decode("utf-8")
        self.assertIn("企业后台管理系统", html)

    def test_unauthorized_api_blocked(self):
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(f"{self.base}/api/stats")
        self.assertEqual(ctx.exception.code, 401)
        data = json.loads(ctx.exception.read().decode("utf-8"))
        self.assertEqual(data["error"], "未登录")

    def test_user_create_and_duplicate_rejected(self):
        self.login()
        payload = json.dumps({"username": "ops", "role": "运营", "status": "启用"}).encode()
        req = urllib.request.Request(
            f"{self.base}/api/users",
            data=payload,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        data = json.loads(self.opener.open(req).read().decode("utf-8"))
        self.assertTrue(any(u["username"] == "ops" for u in data))

        dup_req = urllib.request.Request(
            f"{self.base}/api/users",
            data=payload,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.opener.open(dup_req)
        self.assertEqual(ctx.exception.code, 409)

    def test_product_negative_values_rejected(self):
        self.login()
        payload = json.dumps(
            {"name": "错误商品", "category": "知识", "stock": -1, "price": -2}
        ).encode()
        req = urllib.request.Request(
            f"{self.base}/api/products",
            data=payload,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.opener.open(req)
        self.assertEqual(ctx.exception.code, 400)


if __name__ == "__main__":
    unittest.main()
