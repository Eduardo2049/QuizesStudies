"""
Os <link rel="modulepreload"> da home precisam ter o mesmo ?v= dos imports reais:
com versão diferente o navegador baixa o arquivo duas vezes e o ganho vira perda.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "web"


def _imports_of(path: Path, seen: set[str]) -> None:
    for spec in re.findall(r"""^\s*import\s[^'"]*['"](\.[^'"]+)['"]""", path.read_text(encoding="utf-8"), re.M):
        target = (path.parent / spec.split("?")[0]).resolve()
        url = "/" + target.relative_to(ROOT).as_posix() + ("?" + spec.split("?", 1)[1] if "?" in spec else "")
        if url not in seen:
            seen.add(url)
            _imports_of(target, seen)


class ModulePreloadTests(unittest.TestCase):
    def test_preloads_match_real_imports(self):
        html = (WEB / "index.html").read_text(encoding="utf-8")
        preloads = set(re.findall(r'<link rel="modulepreload" href="([^"]+)"', html))
        app_src = re.search(r'<script type="module" src="(/web/app\.js[^"]*)"', html).group(1)
        expected = {app_src}
        _imports_of(WEB / "app.js", expected)
        self.assertEqual(preloads, expected)

    def test_preloaded_font_exists_in_css(self):
        html = (WEB / "index.html").read_text(encoding="utf-8")
        css = (WEB / "styles.css").read_text(encoding="utf-8")
        for href in re.findall(r'<link rel="preload" href="([^"]+\.woff2)"', html):
            self.assertIn(f"url('{href}')", css)
            self.assertTrue((ROOT / href.lstrip("/")).exists())


if __name__ == "__main__":
    unittest.main()
