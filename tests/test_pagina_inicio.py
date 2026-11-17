"""
Página inicial protótipo (/inicio) e links diretos para o app.

Valida:
1. O servidor local e o vercel.json servem a página em /inicio.
2. A página fica fora dos buscadores enquanto é protótipo (noindex, fora do sitemap).
3. Todo texto visível tem tradução exata em en.js (padrões genéricos como "{0} de {1}"
   trocariam "Caderno de erros" por "Caderno of erros"; por isso a chave tem de ser exata).
4. Respeita a CSP 'self': sem atributo style e sem script executável inline.
5. Âncoras internas apontam para seções existentes e o rodapé leva a produto, termos e privacidade.
6. Todo link /?abrir=... da página é tratado pelo app.js, e o app aceita ?simulado=.
7. Todas as páginas e módulos importam o i18n.js na mesma versão (versões diferentes criam
   duas instâncias do módulo, cada uma traduzindo a página).
"""
import json
import re
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from api.handlers import quiz_handler
from api.handlers.quiz_handler import QuizHandler
from tests.test_pagina_produto import _TextCollector, _dictionary_keys

ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = ROOT / "public" / "web"
PAGE = WEB_DIR / "inicio.html"


def _collect():
    parser = _TextCollector()
    parser.feed(PAGE.read_text(encoding="utf-8"))
    return parser


class TestInicioRoutes(unittest.TestCase):
    def setUp(self):
        p = patch.object(quiz_handler, "_ensure_migrations", lambda: None)
        p.start()
        self.addCleanup(p.stop)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), QuizHandler)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def test_local_server_serves_page(self):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/inicio", timeout=5) as resp:
            self.assertEqual(resp.status, 200)
            self.assertTrue(resp.headers["Content-Type"].startswith("text/html"))
            self.assertIn('id="inMuralCanvas"', resp.read().decode("utf-8"))

    def test_static_assets_are_served(self):
        for path, kind in (("/web/inicio.css", "text/css"), ("/web/modules/inicio.js", "javascript"),
                           ("/web/modules/smooth-scroll.js", "javascript"), ("/web/modules/mural.js", "javascript")):
            with self.subTest(path=path), urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}", timeout=5) as resp:
                self.assertEqual(resp.status, 200)
                self.assertIn(kind, resp.headers["Content-Type"])

    def test_vercel_rewrite(self):
        rewrites = {r["source"]: r["destination"] for r in json.loads((ROOT / "vercel.json").read_text())["rewrites"]}
        self.assertEqual(rewrites.get("/inicio"), "/web/inicio.html")


class TestInicioContent(unittest.TestCase):
    def test_prototype_is_not_indexed(self):
        html = PAGE.read_text(encoding="utf-8")
        self.assertIn('<meta name="robots" content="noindex">', html)
        self.assertNotIn("/inicio", (WEB_DIR / "sitemap.xml").read_text(encoding="utf-8"))

    def test_every_visible_text_has_exact_translation(self):
        keys = _dictionary_keys()
        untranslatable = re.compile(r"^(\d+(:\d+)?|[A-D]|/ \d+|[·.])$")
        missing = [
            text for text in dict.fromkeys(_collect().texts)
            if not untranslatable.match(text) and text not in keys
        ]
        self.assertEqual(missing, [], "Textos sem tradução exata em en.js")

    def test_respects_csp_self(self):
        html = PAGE.read_text(encoding="utf-8")
        self.assertEqual(_collect().style_attrs, 0, "atributo style é bloqueado pela CSP")
        for block in re.findall(r"<script(?![^>]*\bsrc=)([^>]*)>", html):
            self.assertIn('type="application/ld+json"', block, "script inline executável é bloqueado pela CSP")
        self.assertNotRegex(html, r"https?://(?!acely\.com\.br|schema\.org)[^\"'\s]+\.(js|css|woff2?)")

    def test_faq_structured_data_matches_page(self):
        html = PAGE.read_text(encoding="utf-8")
        data = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S).group(1))
        summaries = set(re.findall(r"<summary>(.*?)</summary>", html))
        self.assertEqual({q["name"] for q in data["mainEntity"]}, summaries)

    def test_anchors_and_footer(self):
        parser = _collect()
        for href in parser.hrefs:
            if href.startswith("#"):
                with self.subTest(href=href):
                    self.assertIn(href[1:], parser.ids)
        for target in ("/produto", "/termos", "/privacidade", "/login"):
            self.assertIn(target, parser.hrefs)
        self.assertIn('<a href="/produto">Produto e planos</a>', PAGE.read_text(encoding="utf-8"))

    def test_single_primary_cta_in_hero(self):
        hero = re.search(r'<section class="in-hero".*?</section>', PAGE.read_text(encoding="utf-8"), re.S).group(0)
        self.assertEqual(len(re.findall(r'class="in-btn in-btn--primary"', hero)), 1)


class TestDeepLinks(unittest.TestCase):
    def test_every_open_action_is_handled_by_app(self):
        app = (WEB_DIR / "app.js").read_text(encoding="utf-8")
        handled = set(re.findall(r"'(\w+)'", re.search(r"\[('criar'[^\]]*)\]\.includes\(openAction\)", app).group(1)))
        used = set()
        for href in _collect().hrefs:
            parsed = urlparse(href)
            if parsed.path == "/" and "abrir" in parse_qs(parsed.query):
                used.update(parse_qs(parsed.query)["abrir"])
        self.assertTrue(used, "a página deveria ter atalhos para o app")
        self.assertLessEqual(used, handled, f"ações sem tratamento no app.js: {used - handled}")

    def test_app_accepts_quiz_link(self):
        app = (WEB_DIR / "app.js").read_text(encoding="utf-8")
        self.assertIn("params.get('simulado')", app)
        self.assertIn("loadInitialQuiz()", app)


class TestI18nModuleVersion(unittest.TestCase):
    def test_single_i18n_version_everywhere(self):
        versions = {}
        files = list(WEB_DIR.glob("*.html")) + list(WEB_DIR.glob("*.js")) + list((WEB_DIR / "modules").glob("*.js"))
        files.append(ROOT / "404.html")
        for path in files:
            for version in re.findall(r"i18n\.js\?v=(\d+)", path.read_text(encoding="utf-8")):
                versions.setdefault(version, []).append(path.name)
        self.assertEqual(len(versions), 1, f"i18n.js com versões diferentes: {versions}")


if __name__ == "__main__":
    unittest.main()
