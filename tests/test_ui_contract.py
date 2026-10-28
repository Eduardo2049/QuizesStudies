"""
Contrato entre o HTML e o JavaScript da interface.

Antes e depois de qualquer redesenho, os IDs que o JS procura precisam continuar
existindo, e as referências de acessibilidade (for, aria-labelledby,
aria-describedby, aria-controls) precisam apontar para elementos reais. Se um
redesenho remover ou renomear um desses IDs, este teste falha e diz qual.
"""
import re
import unittest
from html.parser import HTMLParser
from pathlib import Path

WEB_DIR = Path(__file__).resolve().parent.parent / "web"

# Script principal de cada página -> páginas onde ele roda
PAGE_SCRIPTS = {
    "app.js": ["index.html"],
    "modules/auth_page.js": ["login.html", "register.html"],
    "modules/reset_password_page.js": ["reset-password.html"],
}
# Módulos compartilhados: o ID precisa existir em pelo menos uma página
SHARED_SCRIPTS = [
    "modules/theme.js",
    "modules/backdrop.js",
    "modules/shortcuts.js",
    "modules/stats.js",
    "modules/timer-drag.js",
    "modules/i18n.js",
]
PAGES = ["index.html", "login.html", "register.html", "reset-password.html"]

ID_LOOKUP = re.compile(
    r"""getElementById\(\s*['"]([A-Za-z][\w-]*)['"]\s*\)"""
    r"""|querySelector\(\s*['"]#([A-Za-z][\w-]*)['"]\s*\)"""
)
# IDs criados pelo próprio JS (templates e atribuições), que não estão no HTML estático
ID_CREATED = re.compile(r"""\bid=["']([A-Za-z][\w-]*)["']|\.id\s*=\s*['"]([A-Za-z][\w-]*)['"]""")
ID_REFERENCE_ATTRS = ("for", "aria-labelledby", "aria-describedby", "aria-controls")


class _PageParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = set()
        self.references = []  # (atributo, id)

    def handle_starttag(self, tag, attrs):
        for name, value in attrs:
            if not value:
                continue
            if name == "id":
                self.ids.add(value)
            elif name in ID_REFERENCE_ATTRS:
                for ref in value.split():
                    self.references.append((name, ref))


def _parse(page):
    parser = _PageParser()
    parser.feed((WEB_DIR / page).read_text(encoding="utf-8"))
    return parser


def _read(script):
    return (WEB_DIR / script).read_text(encoding="utf-8")


def _looked_up_ids(source):
    return {a or b for a, b in ID_LOOKUP.findall(source)}


def _created_ids(source):
    return {a or b for a, b in ID_CREATED.findall(source)}


class TestUIContract(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.pages = {page: _parse(page) for page in PAGES}
        all_scripts = list(PAGE_SCRIPTS) + SHARED_SCRIPTS
        cls.dynamic_ids = set().union(*(_created_ids(_read(s)) for s in all_scripts))

    def test_page_scripts_find_their_ids(self):
        for script, pages in PAGE_SCRIPTS.items():
            for element_id in sorted(_looked_up_ids(_read(script))):
                if element_id in self.dynamic_ids:
                    continue
                for page in pages:
                    with self.subTest(script=script, page=page, id=element_id):
                        self.assertIn(element_id, self.pages[page].ids,
                                      f"{script} procura #{element_id}, que não existe em {page}")

    def test_shared_modules_find_their_ids(self):
        every_id = set().union(*(p.ids for p in self.pages.values())) | self.dynamic_ids
        for script in SHARED_SCRIPTS:
            for element_id in sorted(_looked_up_ids(_read(script))):
                with self.subTest(script=script, id=element_id):
                    self.assertIn(element_id, every_id, f"{script} procura #{element_id}, que não existe em nenhuma página")

    def test_accessibility_references_point_to_real_elements(self):
        for page, parsed in self.pages.items():
            for attr, ref in parsed.references:
                if ref in self.dynamic_ids:
                    continue
                with self.subTest(page=page, attr=attr, id=ref):
                    self.assertIn(ref, parsed.ids, f'{page}: {attr}="{ref}" aponta para um ID inexistente')

    def test_ids_are_unique_per_page(self):
        for page in PAGES:
            ids = re.findall(r'\sid="([^"]+)"', (WEB_DIR / page).read_text(encoding="utf-8"))
            duplicated = sorted({i for i in ids if ids.count(i) > 1})
            with self.subTest(page=page):
                self.assertEqual(duplicated, [], f"{page} tem IDs repetidos: {duplicated}")


if __name__ == "__main__":
    unittest.main()
