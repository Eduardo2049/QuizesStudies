/**
 * Evita mostrar o português por um instante antes da tradução.
 * Carregado como <script src="..."> comum no <head>, como o theme-boot.js.
 * A regra de idioma é a mesma de getLanguage() em i18n.js.
 */
(function () {
  try {
    var saved = localStorage.getItem('quiz_lang');
    var nav = String(navigator.language || 'pt-BR').toLowerCase();
    var lang = saved === 'pt-BR' || saved === 'en' ? saved : (nav.indexOf('pt') === 0 ? 'pt-BR' : 'en');
    var root = document.documentElement;
    root.lang = lang;
    if (lang !== 'pt-BR') {
      root.classList.add('i18n-pending');
      // Se o módulo de tradução falhar, a página aparece mesmo assim
      setTimeout(function () { root.classList.remove('i18n-pending'); }, 1500);
    }
  } catch (_) {}
})();
