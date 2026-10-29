"""
Integração da marca Acely com o domínio acely.com.br.
Valida:
1. robots.txt, sitemap.xml e site.webmanifest servidos na raiz com o Content-Type certo
   (servidor local) e com rewrite equivalente no vercel.json.
2. www.acely.com.br redireciona para o domínio sem www.
3. Todas as páginas apontam para o manifesto; as públicas têm canonical no domínio.
4. O manifesto e o sitemap só citam ícones e rotas que existem.
5. O e-mail de recuperação sai com o nome "Acely" e a logo do mesmo domínio do link.
"""

import json
import re
import threading
import unittest
import urllib.request
from email import message_from_string
from email.header import decode_header, make_header
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import MagicMock, patch

from api.handlers import quiz_handler
from api.handlers.quiz_handler import QuizHandler
from api.services.email_service import EmailService

ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = ROOT / "web"
DOMAIN = "https://acely.com.br"
ROOT_FILES = {
    "/robots.txt": "text/plain",
    "/sitemap.xml": "application/xml",
    "/site.webmanifest": "application/manifest+json",
}
PAGES = [
    "web/index.html",
    "web/login.html",
    "web/register.html",
    "web/reset-password.html",
    "web/termos.html",
    "web/privacidade.html",
    "404.html",
]
CANONICAL = {
    "web/index.html": f"{DOMAIN}/",
    "web/login.html": f"{DOMAIN}/login",
    "web/register.html": f"{DOMAIN}/register",
    "web/termos.html": f"{DOMAIN}/termos",
    "web/privacidade.html": f"{DOMAIN}/privacidade",
}


def _vercel():
    return json.loads((ROOT / "vercel.json").read_text(encoding="utf-8"))


class TestRootFilesServed(unittest.TestCase):
    def setUp(self):
        p = patch.object(quiz_handler, "_ensure_migrations", lambda: None)
        p.start()
        self.addCleanup(p.stop)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), QuizHandler)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def test_root_files_have_right_content_type(self):
        for path, mime in ROOT_FILES.items():
            with (
                self.subTest(path=path),
                urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}", timeout=5) as resp,
            ):
                self.assertEqual(resp.status, 200)
                self.assertTrue(resp.headers["Content-Type"].startswith(mime), resp.headers["Content-Type"])
                self.assertTrue(resp.read())


class TestVercelDomain(unittest.TestCase):
    def test_root_files_have_vercel_rewrites(self):
        rewrites = {r["source"]: r["destination"] for r in _vercel()["rewrites"]}
        for path in ROOT_FILES:
            with self.subTest(path=path):
                self.assertIn(path, rewrites)
                self.assertTrue((ROOT / rewrites[path].lstrip("/")).is_file(), rewrites[path])

    def test_www_redirects_to_apex(self):
        redirect = next(
            r for r in _vercel()["redirects"] if {"type": "host", "value": "www.acely.com.br"} in r.get("has", [])
        )
        self.assertEqual(redirect["destination"], f"{DOMAIN}/$1")
        self.assertTrue(redirect["permanent"])


class TestPagesPointToDomain(unittest.TestCase):
    def test_every_page_links_the_manifest(self):
        for page in PAGES:
            with self.subTest(page=page):
                self.assertIn(
                    '<link rel="manifest" href="/site.webmanifest">', (ROOT / page).read_text(encoding="utf-8")
                )

    def test_public_pages_have_canonical_and_og_url_on_domain(self):
        for page, url in CANONICAL.items():
            html = (ROOT / page).read_text(encoding="utf-8")
            with self.subTest(page=page):
                self.assertIn(f'<link rel="canonical" href="{url}">', html)
                self.assertIn(f'<meta property="og:url" content="{url}">', html)
                self.assertIn(f'<meta property="og:image" content="{DOMAIN}/web/icons/og-image.png">', html)

    def test_private_pages_are_not_indexed(self):
        for page in ("web/reset-password.html", "404.html"):
            with self.subTest(page=page):
                self.assertIn('<meta name="robots" content="noindex">', (ROOT / page).read_text(encoding="utf-8"))

    def test_structured_data_is_valid_json(self):
        html = (WEB_DIR / "index.html").read_text(encoding="utf-8")
        block = re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
        data = json.loads(block.group(1))
        names = {item["name"] for item in data["@graph"]}
        self.assertEqual(names, {"Acely"})


class TestManifestAndSitemap(unittest.TestCase):
    def test_manifest_icons_exist(self):
        manifest = json.loads((WEB_DIR / "site.webmanifest").read_text(encoding="utf-8"))
        self.assertEqual(manifest["name"], "Acely")
        sizes = set()
        for icon in manifest["icons"]:
            path = ROOT / icon["src"].split("?", 1)[0].lstrip("/")
            with self.subTest(icon=icon["src"]):
                self.assertTrue(path.is_file())
            sizes.add(icon["sizes"])
        self.assertTrue({"192x192", "512x512"} <= sizes)

    def test_sitemap_lists_only_routes_on_domain(self):
        # Sem parser XML: o Semgrep do CI bloqueia xml.etree, e um regex basta para o <loc>
        sitemap = (WEB_DIR / "sitemap.xml").read_text(encoding="utf-8")
        self.assertIn('xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"', sitemap)
        locs = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", sitemap)
        self.assertEqual(len(locs), sitemap.count("<url>"))
        routes = {r["source"] for r in _vercel()["rewrites"]}
        for loc in locs:
            with self.subTest(loc=loc):
                self.assertTrue(loc.startswith(f"{DOMAIN}/"))
                self.assertIn(loc.removeprefix(DOMAIN) or "/", routes)

    def test_robots_points_to_sitemap(self):
        self.assertIn(f"Sitemap: {DOMAIN}/sitemap.xml", (WEB_DIR / "robots.txt").read_text(encoding="utf-8"))


class TestResetEmailBranding(unittest.TestCase):
    def _send(self, from_email, reset_url):
        service = EmailService(
            host="smtp.test", port=587, user="", password="", from_email=from_email, use_tls=False, use_ssl=False
        )
        smtp = MagicMock()
        with patch("api.services.email_service.smtplib.SMTP") as smtp_cls:
            smtp_cls.return_value.__enter__.return_value = smtp
            ok, _ = service.send_password_reset_email("ana@exemplo.com", "ana", reset_url, "tok")
        self.assertTrue(ok)
        return message_from_string(smtp.sendmail.call_args[0][2])

    def test_sender_without_name_shows_acely(self):
        msg = self._send("conta@gmail.com", f"{DOMAIN}/reset-password?token=tok")
        self.assertEqual(str(make_header(decode_header(msg["From"]))), "Acely <conta@gmail.com>")

    def test_sender_with_name_is_kept(self):
        msg = self._send("Equipe <noreply@acely.com.br>", f"{DOMAIN}/reset-password?token=tok")
        self.assertEqual(msg["From"], "Equipe <noreply@acely.com.br>")

    def test_logo_comes_from_link_domain(self):
        msg = self._send("conta@gmail.com", f"{DOMAIN}/reset-password?token=tok")
        html = next(p for p in msg.walk() if p.get_content_type() == "text/html")
        body = html.get_payload(decode=True).decode("utf-8")
        self.assertIn(f'src="{DOMAIN}/web/icons/favicon-192.png"', body)
        self.assertIn(f'href="{DOMAIN}"', body)


if __name__ == "__main__":
    unittest.main()
