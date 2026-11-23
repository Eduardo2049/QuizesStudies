"""
Contratos pós-Fase 3 do redesign de `/app` (Missão 1):
1. Tema escuro padrão em `index.html`, `theme-boot.js` e `theme.js` (`#000000`).
2. Remoção de `smooth-scroll.js` em `/app` e preservação em `/inicio`.
3. Arquitetura em 2 camadas (`.app-nav-wrap`/`.app-nav`/`#appNavDrawer` e `.exam-panel`) sem IDs duplicados.
4. Progresso com `scaleX`, ciclo de vida WebGL (`setBackdropSuspended`), `wakeLock`, `inert`, `translate="no"` e saída de `closeResultModal()` para `'idle'`.
5. Sincronia completa de `?v=` nos 9 HTMLs e módulos JS.
6. Cobertura e integridade das 21 chaves novas/normalizadas em `public/web/modules/i18n/en.js`.
7. Tokens escuros, `#timer` fixo com `--z-timer` para compatibilidade com `.timer--custom` e alvos de toque >= 44px no mobile (`<= 768px`) em `public/web/styles.css`.
"""

import json
import re
import unittest
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "public" / "web"
MODULES = WEB / "modules"

ALL_HTMLS = (
    WEB / "index.html",
    WEB / "inicio.html",
    WEB / "login.html",
    WEB / "register.html",
    WEB / "reset-password.html",
    WEB / "produto.html",
    WEB / "termos.html",
    WEB / "privacidade.html",
    ROOT / "404.html",
)

THEME_BOOT_HTMLS = tuple(p for p in ALL_HTMLS if p.name != "inicio.html")
BACKDROP_HTMLS = (
    WEB / "index.html",
    WEB / "login.html",
    WEB / "register.html",
    WEB / "reset-password.html",
    WEB / "termos.html",
    WEB / "privacidade.html",
    ROOT / "404.html",
)
I18N_HTMLS = (
    WEB / "index.html",
    WEB / "login.html",
    WEB / "register.html",
    WEB / "reset-password.html",
)

REQUIRED_EN_KEYS = (
    "Voltar para a página inicial",
    "Início",
    "Controles do simulado",
    "Acely · Treino de raciocínio",
    "Refazer tudo",
    "Gerar novas variações",
    "Biblioteca de estudos",
    "Opções rápidas:",
    "Simulado incompleto",
    "Erro de carregamento",
    "Erro de conexão",
    "Correta",
    "Errada",
    "Explicação didática",
    "Bom rendimento",
    "Desempenho excepcional",
    "Acima da média",
    "Regular ou em evolução",
    "Atenção redobrada",
    "Ritmo médio:",
    "Desempenho por disciplina",
)


class _DomTreeParser(HTMLParser):
    """Mapeia ancestrais e filhos para validar hierarquia exata das 2 camadas."""

    VOID = frozenset({"br", "img", "meta", "link", "input", "hr", "source"})

    def __init__(self):
        super().__init__()
        self.stack: list[tuple[str, str, set[str]]] = []
        self.ids_by_element: list[tuple[str, tuple[str, ...]]] = []
        self.element_info: dict[str, tuple[str, dict[str, str], tuple[str, ...]]] = {}
        self.class_parents: dict[str, list[tuple[str, ...]]] = {}
        self.drawer_links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {k: (v or "") for k, v in attrs}
        el_id = attr_map.get("id", "")
        classes = set(attr_map.get("class", "").split())
        ancestors = tuple(item[0] for item in self.stack)
        ancestor_classes = tuple(cls for _, _, cls_set in self.stack for cls in cls_set)
        ancestor_ids = tuple(item[1] for item in self.stack if item[1])

        if el_id:
            self.ids_by_element.append((el_id, ancestor_ids))
            self.element_info[el_id] = (tag, attr_map, ancestor_classes + ancestor_ids)

        for cls in classes:
            self.class_parents.setdefault(cls, []).append(ancestors + ancestor_classes)

        if tag == "a" and "appNavDrawer" in ancestor_ids:
            self.drawer_links.append(attr_map.get("href", ""))

        if tag not in self.VOID:
            self.stack.append((tag, el_id, classes))

    def handle_endtag(self, tag: str) -> None:
        while self.stack:
            open_tag, _, _ = self.stack.pop()
            if open_tag == tag:
                break


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _extract_css_block(css: str, header_pattern: str) -> str:
    match = re.search(header_pattern, css)
    if not match:
        raise AssertionError(f"Bloco CSS não encontrado: {header_pattern}")
    brace_start = css.find("{", match.start())
    depth = 0
    for idx in range(brace_start, len(css)):
        ch = css[idx]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return css[brace_start + 1 : idx]
    raise AssertionError(f"Bloco CSS sem fechamento: {header_pattern}")


def _parse_en_entries() -> list[tuple[str, str]]:
    source = _read(MODULES / "i18n" / "en.js")
    entries: list[tuple[str, str]] = []
    # Captura pares chave: valor de uma linha ou multilinha em export default { ... }
    pattern = re.compile(
        r"""^\s*(?:'((?:[^'\\]|\\.)*)'|"((?:[^"\\]|\\.)*)")\s*:\s*(?:\n\s*)?(?:'((?:[^'\\]|\\.)*)'|"((?:[^"\\]|\\.)*)")""",
        re.M,
    )
    for k_single, k_double, v_single, v_double in pattern.findall(source):
        key = (k_single or json.loads(f'"{k_double}"')).replace("\\'", "'")
        val = (v_single or json.loads(f'"{v_double}"')).replace("\\'", "'")
        entries.append((key, val))
    return entries


class TestThemeDefaultDarkContract(unittest.TestCase):
    def test_index_html_declares_dark_default_and_black_theme_color(self):
        html = _read(WEB / "index.html")
        self.assertIn('<html lang="pt-BR" data-default-theme="dark">', html)
        self.assertIn('<meta name="theme-color" content="#000000">', html)

    def test_theme_boot_and_theme_js_honor_default_theme_and_dark_order(self):
        boot = _read(MODULES / "theme-boot.js")
        theme_js = _read(MODULES / "theme.js")

        self.assertIn("getAttribute('data-default-theme') || 'system'", boot)
        self.assertIn("r === 'dark' ? '#000000' : '#f4f0e8'", boot)

        self.assertIn("const THEMES = ['dark', 'light', 'system'];", theme_js)
        self.assertIn("getAttribute('data-default-theme')", theme_js)
        self.assertIn("resolved === 'dark' ? '#000000' : '#f4f0e8'", theme_js)


class TestSmoothScrollRemovalContract(unittest.TestCase):
    def test_app_has_no_smooth_scroll_while_inicio_preserves_it(self):
        index_html = _read(WEB / "index.html")
        app_js = _read(WEB / "app.js")
        inicio_html = _read(WEB / "inicio.html")
        inicio_js = _read(MODULES / "inicio.js")

        self.assertNotIn("smooth-scroll.js", index_html)
        self.assertNotIn("smooth-scroll.js", app_js)
        self.assertIn("smooth-scroll.js", inicio_js)
        self.assertIn('<html lang="pt-BR" data-theme="dark" data-default-theme="dark" class="in-html">', inicio_html)


class TestTwoLayerArchitectureContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        html = _read(WEB / "index.html")
        cls.html = re.sub(r"<!--.*?-->", "", html, flags=re.S)
        cls.parser = _DomTreeParser()
        cls.parser.feed(cls.html)

    def test_layer1_nav_and_drawer_structure_without_duplicate_ids(self):
        ids = [el_id for el_id, _ in self.parser.ids_by_element]
        self.assertEqual(sorted({i for i in ids if ids.count(i) > 1}), [])

        self.assertIn("app-nav-wrap", self.parser.class_parents)
        self.assertTrue(any("app-nav-wrap" in p for p in self.parser.class_parents["app-nav"]))

        toggle_tag, toggle_attrs, toggle_ancestors = self.parser.element_info["appMenuToggle"]
        self.assertEqual(toggle_tag, "button")
        self.assertEqual(toggle_attrs.get("aria-controls"), "appNavDrawer")
        self.assertIn("app-nav", toggle_ancestors)

        for child_id in ("plansLink", "btnOpenAboutModal", "backdropMotionToggle", "authControls"):
            with self.subTest(child_id=child_id):
                _, _, ancestors = self.parser.element_info[child_id]
                self.assertIn("appNavDrawer", ancestors)

        self.assertIn("/", self.parser.drawer_links)
        for quick_id in ("langToggle", "themeToggle"):
            with self.subTest(quick_id=quick_id):
                _, _, ancestors = self.parser.element_info[quick_id]
                self.assertIn("app-nav", ancestors)

    def test_layer2_exam_panel_and_timer_outside_exam_panel(self):
        exam_panel_parents = self.parser.class_parents.get("exam-panel", [])
        self.assertTrue(exam_panel_parents)
        self.assertTrue(any("hero" in p for p in exam_panel_parents))

        _, _, timer_ancestors = self.parser.element_info["timer"]
        self.assertIn("timer-wrap", timer_ancestors)
        self.assertNotIn("timer-dock", timer_ancestors)


class TestRuntimeMotionBackdropWakeLockAndInertContract(unittest.TestCase):
    def test_progress_bars_use_scalex_and_not_width(self):
        css = _read(WEB / "styles.css")
        app_js = _read(WEB / "app.js")

        progress_css = _extract_css_block(css, r"#progressBar\s*\{")
        section_css = _extract_css_block(css, r"\.section-progress-fill\s*\{")
        self.assertIn("transform: scaleX(0);", progress_css)
        self.assertIn("transform-origin: left center;", progress_css)
        self.assertIn("transform: scaleX(0);", section_css)
        self.assertIn("transform-origin: left center;", section_css)

        self.assertNotIn("progressBar.style.width", app_js)
        self.assertIn("progressBar.style.transform = `scaleX(${ratio})`", app_js)
        self.assertIn("el.style.transform = `scaleX(${pct / 100})`", app_js)

    def test_backdrop_lifecycle_wakelock_inert_and_translate_no(self):
        backdrop_js = _read(MODULES / "backdrop.js")
        app_js = _read(WEB / "app.js")

        self.assertIn("export function setBackdropSuspended", backdrop_js)
        for gl_cleanup in ("deleteTexture", "deleteFramebuffer", "deleteBuffer", "deleteProgram"):
            self.assertIn(gl_cleanup, backdrop_js)

        self.assertIn("setBackdropSuspended", app_js)
        self.assertIn("let examState = 'idle';", app_js)
        self.assertIn("navigator.wakeLock?.request", app_js)
        self.assertIn("visibilitychange", app_js)
        wake_lock_fn = app_js.split("async function acquireWakeLock()", 1)[1].split("function releaseWakeLock()", 1)[0]
        self.assertIn("try {", wake_lock_fn)
        self.assertIn("navigator.wakeLock.request('screen')", wake_lock_fn)
        self.assertIn("} catch", wake_lock_fn)

        self.assertIn("el.inert =", app_js)
        self.assertIn("card.inert = isHiddenInFocus;", app_js)

        # Perguntas, opções, seletor, catálogo e revisão mantêm translate="no"
        self.assertIn('<p class="section" translate="no">', app_js)
        self.assertIn('<h2 translate="no">', app_js)
        self.assertIn('<span translate="no">${String.fromCharCode(65 + i)})', app_js)
        self.assertIn('<h3 class="catalog-card-title" translate="no">', app_js)
        result_modal_fn = app_js.split("function renderResultModal", 1)[1].split("quiz.addEventListener('submit'", 1)[0]
        self.assertIn('translate="no"', result_modal_fn)

    def test_close_result_modal_returns_to_idle_when_timer_stopped(self):
        app_js = _read(WEB / "app.js")
        close_result_fn = _extract_css_block(app_js, r"function closeResultModal\(\)\s*\{")

        self.assertIn("if (examState === 'results')", close_result_fn)
        self.assertNotIn("isTimerActiveOrExpired", close_result_fn)
        self.assertNotIn("expired", close_result_fn)
        self.assertIn("timerInterval", close_result_fn)
        self.assertIn("classList.contains('running')", close_result_fn)
        self.assertRegex(close_result_fn, r"setExamState\([^;]*\?\s*'active'\s*:\s*'idle'\s*\)")


class TestCacheBustingVersionSyncContract(unittest.TestCase):
    def test_all_htmls_and_modules_have_exact_expected_versions(self):
        for html_path in ALL_HTMLS:
            html = _read(html_path)
            with self.subTest(file=html_path.name):
                self.assertIn("/web/styles.css?v=33", html)
                self.assertNotIn("styles.css?v=30", html)

        for html_path in THEME_BOOT_HTMLS:
            html = _read(html_path)
            with self.subTest(file=html_path.name):
                self.assertIn("/web/modules/theme-boot.js?v=2", html)

        for html_path in BACKDROP_HTMLS:
            html = _read(html_path)
            with self.subTest(file=html_path.name):
                self.assertIn("/web/modules/backdrop.js?v=9", html)

        for html_path in I18N_HTMLS:
            html = _read(html_path)
            with self.subTest(file=html_path.name):
                self.assertIn("/web/modules/i18n.js?v=11", html)

        index_html = _read(WEB / "index.html")
        self.assertEqual(index_html.count("/web/app.js?v=28"), 2)
        self.assertIn("/web/modules/theme.js?v=10", index_html)
        self.assertIn("/web/modules/stats.js?v=8", index_html)
        self.assertIn("/web/modules/i18n/en.js?v=11", index_html)

        app_js = _read(WEB / "app.js")
        self.assertIn("./modules/theme.js?v=10", app_js)
        self.assertIn("./modules/stats.js?v=8", app_js)
        self.assertIn("./modules/i18n.js?v=11", app_js)
        self.assertIn("./modules/backdrop.js?v=9", app_js)

        self.assertIn("./i18n.js?v=11", _read(MODULES / "auth_page.js"))
        self.assertIn("./i18n.js?v=11", _read(MODULES / "inicio.js"))
        produto_js = _read(MODULES / "produto.js")
        self.assertIn("./i18n.js?v=11", produto_js)
        self.assertIn("./theme.js?v=10", produto_js)
        self.assertIn("./i18n/en.js?v=11", _read(MODULES / "i18n.js"))


class TestI18nDictionaryContract(unittest.TestCase):
    def test_en_js_covers_21_keys_without_duplicates_or_exclamation(self):
        entries = _parse_en_entries()
        keys = [k for k, _ in entries]
        duplicated = sorted({k for k in keys if keys.count(k) > 1})
        self.assertEqual(duplicated, [], f"Chaves duplicadas em en.js: {duplicated}")

        entry_map = dict(entries)
        for required_key in REQUIRED_EN_KEYS:
            with self.subTest(key=required_key):
                self.assertIn(required_key, entry_map)
                self.assertNotIn("!", required_key)
                self.assertNotIn("!", entry_map[required_key])


class TestCssDarkTokensAndMobileTouchTargetsContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.css = _read(WEB / "styles.css")

    def test_dark_theme_tokens_match_studio_coral_aa_spec(self):
        dark_block = _extract_css_block(self.css, r'\[data-theme="dark"\]\s*\{')
        for token_line in (
            "--paper: #000000;",
            "--surface: #181818;",
            "--surface-2: #1F1F1F;",
            "--coral: #FF7A5C;",
            "--btn-primary-text: #000000;",
            "--accent-text: #FF8F75;",
            "--teal: #FF7A5C;",
            "--line: #272727;",
            "--line-strong: #313131;",
        ):
            with self.subTest(token=token_line):
                self.assertIn(token_line, dark_block)

    def test_mobile_touch_targets_block_covers_44px_minimum(self):
        # Extrai o bloco consolidado final de alvos >= 44px em @media (max-width: 768px)
        marker = "/* ═══ Alvos de toque >= 44\u00d744px no mobile"
        self.assertIn(marker, self.css)
        touch_section = _extract_css_block(self.css[self.css.index(marker) :], r"@media \(max-width: 768px\)\s*\{")

        for selector in (
            ".catalog-tab-btn",
            ".footer-link",
            ".visitor-actions .guest-action-link",
            "#timer",
            ".topic-chip",
            ".palette-btn",
            ".app-brand",
            ".app-menu-toggle",
            "#langToggle",
            "#themeToggle",
            ".app-nav-link",
            ".modal-close",
            ".file-preview-remove",
            ".btn-auth-logout",
        ):
            with self.subTest(selector=selector):
                self.assertIn(selector, touch_section)

        self.assertIn("min-height: 44px;", touch_section)
        self.assertIn("min-width: 44px;", touch_section)

    def test_timer_base_block_keeps_fixed_positioning_and_z_index(self):
        timer_base = _extract_css_block(self.css, r"#timer\s*\{")
        self.assertIn("position: fixed;", timer_base)
        self.assertIn("z-index: var(--z-timer);", timer_base)

        timer_not_custom = _extract_css_block(self.css, r"#timer:not\(\.timer--custom\)\s*\{")
        self.assertNotIn("position:", timer_not_custom)
        self.assertNotIn("z-index:", timer_not_custom)


if __name__ == "__main__":
    unittest.main()
