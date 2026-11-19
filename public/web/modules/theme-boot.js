/**
 * Script de prevenção de FOUC (Flash of Unstyled Content) de tema.
 * Precisa executar de forma síncrona e bloqueante, antes do primeiro paint,
 * por isso é carregado como <script src="..."> comum (sem defer/module) no <head>.
 */
(function () {
  try {
    var fallback = document.documentElement.getAttribute('data-default-theme') || 'system';
    var saved = null;
    try {
      saved = localStorage.getItem('quiz_theme_preference');
    } catch (_) {}
    var t = (saved === 'system' || saved === 'dark' || saved === 'light') ? saved : fallback;
    var r = t === 'system'
      ? (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')
      : t;
    document.documentElement.setAttribute('data-theme', r);
    document.documentElement.setAttribute('data-theme-mode', t);
    var meta = document.querySelector('meta[name="theme-color"]');
    if (meta) {
      meta.content = r === 'dark' ? '#000000' : '#f4f0e8';
    }
  } catch (_) {}
})();
