"""
Página de produto e planos (/produto e /planos).
Valida:
1. O servidor local e o vercel.json servem a página nas duas rotas.
2. Todo texto visível da página tem tradução em public/web/modules/i18n/en.js.
3. A página respeita a CSP 'self' (sem atributo style, sem script executável inline).
4. Os planos pagos aparecem como "em breve" (sem botão de compra ativo enquanto não há cobrança).
5. Todas as páginas com rodapé levam à página de produto, e a home tem o link "Planos".
6. Os links internos com âncora apontam para seções que existem.
"""

import json
import re
import threading
import unittest
import urllib.request
from html.parser import HTMLParser
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from api.handlers import quiz_handler
from api.handlers.quiz_handler import QuizHandler

ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = ROOT / "public" / "web"
PAGE = WEB_DIR / "produto.html"
EN_JS = WEB_DIR / "modules" / "i18n" / "en.js"
TRANSLATED_ATTRS = ("title", "aria-label", "alt", "placeholder")


class _TextCollector(HTMLParser):
    """Junta textos e atributos traduzíveis, pulando o que i18n.js também pula."""

    SKIP = frozenset({"script", "style", "svg", "code", "pre", "textarea"})
    VOID = frozenset({"br", "img", "meta", "link", "input", "hr", "source"})

    def __init__(self):
        super().__init__()
        self.stack = []
        self.texts = []
        self.ids = set()
        self.hrefs = []
        self.style_attrs = 0
        self.disabled_buttons = []

    def _skipping(self):
        return any(skip for _, skip in self.stack)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "id" in attrs:
            self.ids.add(attrs["id"])
        if "href" in attrs:
            self.hrefs.append(attrs["href"])
        if "style" in attrs:
            self.style_attrs += 1
        skip = tag in self.SKIP or attrs.get("translate") == "no"
        if not skip and not self._skipping():
            self.texts.extend(attrs[a] for a in TRANSLATED_ATTRS if attrs.get(a))
        if tag == "button" and "disabled" in attrs:
            self.disabled_buttons.append(tag)
        if tag not in self.VOID:
            self.stack.append((tag, skip))

    def handle_endtag(self, tag):
        while self.stack:
            open_tag, _ = self.stack.pop()
            if open_tag == tag:
                break

    def handle_data(self, data):
        text = " ".join(data.split())
        if text and not self._skipping():
            self.texts.append(text)


def _collect():
    parser = _TextCollector()
    parser.feed(PAGE.read_text(encoding="utf-8"))
    return parser


def _dictionary_keys():
    source = EN_JS.read_text(encoding="utf-8")
    keys = set()
    for single, double in re.findall(r"""^\s*(?:'((?:[^'\\]|\\.)*)'|"((?:[^"\\]|\\.)*)")\s*:""", source, re.M):
        keys.add(" ".join((single or json.loads(f'"{double}"')).replace("\\'", "'").split()))
    return keys


def _pattern_matches(text, keys):
    for key in keys:
        if "{0}" not in key:
            continue
        regex = "^" + re.sub(r"\\\{\d\\\}", "(.+?)", re.escape(key)) + "$"
        if re.match(regex, text):
            return True
    return False


class TestProdutoRoutes(unittest.TestCase):
    def setUp(self):
        p = patch.object(quiz_handler, "_ensure_migrations", lambda: None)
        p.start()
        self.addCleanup(p.stop)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), QuizHandler)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def test_local_server_serves_both_routes(self):
        for path in ("/produto", "/planos"):
            with (
                self.subTest(path=path),
                urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}", timeout=5) as resp,
            ):
                self.assertEqual(resp.status, 200)
                self.assertTrue(resp.headers["Content-Type"].startswith("text/html"))
                self.assertIn('id="planos"', resp.read().decode("utf-8"))

    def test_vercel_rewrites_both_routes(self):
        rewrites = {r["source"]: r["destination"] for r in json.loads((ROOT / "vercel.json").read_text())["rewrites"]}
        for path in ("/produto", "/planos"):
            with self.subTest(path=path):
                self.assertEqual(rewrites.get(path), "/web/produto.html")


class TestProdutoContent(unittest.TestCase):
    def test_every_visible_text_has_english_translation(self):
        keys = _dictionary_keys()
        # Números, preços e letras de alternativa ficam iguais nos dois idiomas
        untranslatable = re.compile(r"^(R\$ [\d.,]+|[A-D]|\d+[:\d]*|Pro|[·.])$")
        missing = [
            text
            for text in dict.fromkeys(_collect().texts)
            if not untranslatable.match(text) and text not in keys and not _pattern_matches(text, keys)
        ]
        self.assertEqual(missing, [], "Textos sem tradução em en.js")

    def test_respects_csp_self(self):
        html = PAGE.read_text(encoding="utf-8")
        self.assertEqual(_collect().style_attrs, 0, "atributo style é bloqueado pela CSP")
        for block in re.findall(r"<script(?![^>]*\bsrc=)([^>]*)>", html):
            self.assertIn('type="application/ld+json"', block, "script inline executável é bloqueado pela CSP")

    def test_faq_structured_data_matches_page(self):
        html = PAGE.read_text(encoding="utf-8")
        data = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S).group(1))
        self.assertEqual(data["@type"], "FAQPage")
        summaries = set(re.findall(r"<summary>(.*?)</summary>", html))
        for question in data["mainEntity"]:
            with self.subTest(question=question["name"]):
                self.assertIn(question["name"], summaries)

    def test_paid_plans_have_no_active_checkout(self):
        html = PAGE.read_text(encoding="utf-8")
        for plan_id in ("planPro", "planTeam"):
            card = re.search(rf'aria-labelledby="{plan_id}">(.*?)</article>', html, re.S).group(1)
            with self.subTest(plan=plan_id):
                self.assertIn("Em breve", card)
                self.assertRegex(card, r"<button[^>]*disabled")

    def test_internal_anchors_exist(self):
        parser = _collect()
        for href in parser.hrefs:
            if href.startswith("#"):
                with self.subTest(href=href):
                    self.assertIn(href[1:], parser.ids)


class TestLinksToProduto(unittest.TestCase):
    def test_footers_link_to_produto(self):
        for page in ("index.html", "login.html", "register.html", "termos.html", "privacidade.html", "produto.html"):
            with self.subTest(page=page):
                self.assertIn('<a href="/produto">Produto e planos</a>', (WEB_DIR / page).read_text(encoding="utf-8"))
        self.assertIn('<a href="/produto">Produto e planos</a>', (ROOT / "404.html").read_text(encoding="utf-8"))

    def test_home_header_links_to_plans(self):
        self.assertRegex((WEB_DIR / "index.html").read_text(encoding="utf-8"), r'<a href="/planos" id="plansLink"')


if __name__ == "__main__":
    unittest.main()
