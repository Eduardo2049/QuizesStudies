/**
 * Script de prevenção de FOUC (Flash of Unstyled Content) de tema.
 * Precisa executar de forma síncrona e bloqueante, antes do primeiro paint,
 * por isso é carregado como <script src="..."> comum (sem defer/module) no <head>.
 */
(function () {
  try {
    var t = localStorage.getItem('quiz_theme_preference') || 'system';
    var r = t === 'system'
      ? (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')
      : t;
    document.documentElement.setAttribute('data-theme', r);
    document.documentElement.setAttribute('data-theme-mode', t);
  } catch (_) {}
})();
