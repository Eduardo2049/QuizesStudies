/**
 * Página de produto e planos (/produto, /planos).
 * Menu do celular, abas de público, revelação ao rolar, tagline palavra por palavra
 * e link ativo na navegação. Sem dependências além dos módulos do próprio app.
 *
 * i18n.js vem primeiro: ele traduz a página ao ser importado, antes de a tagline
 * ser quebrada em palavras (a tradução casa frases inteiras do dicionário).
 */
import './i18n.js?v=7';
import { initTheme } from './theme.js?v=9';

const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
document.documentElement.classList.add('lp-js');

initTheme();

// ── Menu do celular ──────────────────────────────────────────────────────────
function initMenu() {
  const toggle = document.getElementById('lpMenuToggle');
  const menu = document.getElementById('lpMenu');
  if (!toggle || !menu) return;
  const links = Array.from(menu.querySelectorAll('[data-menu-link]'));
  const STEP = 60;      // ms entre um link e o próximo
  const MAX_TOTAL = 400; // a sequência inteira nunca passa disso

  function open() {
    menu.hidden = false;
    document.body.classList.add('lp-menu-open');
    toggle.setAttribute('aria-expanded', 'true');
    toggle.setAttribute('aria-label', 'Fechar menu');
    const step = Math.min(STEP, MAX_TOTAL / Math.max(links.length, 1));
    links.forEach((link, i) => { link.style.transitionDelay = `${Math.round(i * step)}ms`; });
    requestAnimationFrame(() => requestAnimationFrame(() => menu.classList.add('is-open')));
    links[0]?.focus({ preventScroll: true });
  }

  function close({ returnFocus = true } = {}) {
    menu.classList.remove('is-open');
    document.body.classList.remove('lp-menu-open');
    toggle.setAttribute('aria-expanded', 'false');
    toggle.setAttribute('aria-label', 'Abrir menu');
    links.forEach((link) => { link.style.transitionDelay = '0ms'; });
    window.setTimeout(() => { if (!menu.classList.contains('is-open')) menu.hidden = true; }, 300);
    if (returnFocus) toggle.focus({ preventScroll: true });
  }

  toggle.addEventListener('click', () => {
    if (toggle.getAttribute('aria-expanded') === 'true') close();
    else open();
  });
  links.forEach((link) => link.addEventListener('click', () => close({ returnFocus: false })));
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && toggle.getAttribute('aria-expanded') === 'true') close();
  });
  window.matchMedia('(min-width: 641px)').addEventListener('change', (event) => {
    if (event.matches && toggle.getAttribute('aria-expanded') === 'true') close({ returnFocus: false });
  });
}

// ── Abas de público (padrão WAI-ARIA: setas, Home e End) ─────────────────────
function initTabs() {
  const tabs = Array.from(document.querySelectorAll('.lp-tab'));
  if (!tabs.length) return;

  function select(tab, { focus = false } = {}) {
    tabs.forEach((other) => {
      const selected = other === tab;
      other.setAttribute('aria-selected', String(selected));
      other.tabIndex = selected ? 0 : -1;
      const panel = document.getElementById(other.getAttribute('aria-controls'));
      if (panel) panel.hidden = !selected;
    });
    if (focus) tab.focus();
  }

  tabs.forEach((tab, index) => {
    tab.addEventListener('click', () => select(tab));
    tab.addEventListener('keydown', (event) => {
      const keys = { ArrowRight: index + 1, ArrowLeft: index - 1, Home: 0, End: tabs.length - 1 };
      if (!(event.key in keys)) return;
      event.preventDefault();
      select(tabs[(keys[event.key] + tabs.length) % tabs.length], { focus: true });
    });
  });
}

// ── Revelação das seções ao entrar na tela (uma vez só) ──────────────────────
function initReveal() {
  const items = document.querySelectorAll('.lp-reveal');
  if (!('IntersectionObserver' in window)) {
    items.forEach((el) => el.classList.add('is-visible'));
    return;
  }
  const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (!entry.isIntersecting) return;
      entry.target.classList.add('is-visible');
      observer.unobserve(entry.target);
    });
  }, { rootMargin: '0px 0px -10% 0px' });
  items.forEach((el, i) => {
    el.style.transitionDelay = `${(i % 4) * 60}ms`;
    observer.observe(el);
  });
}

// ── Tagline: cada palavra acende ao cruzar a linha de disparo ────────────────
function initWordReveal() {
  document.querySelectorAll('[data-word-reveal]').forEach((block) => {
    const words = block.textContent.trim().split(/\s+/);
    block.setAttribute('aria-label', block.textContent.trim());
    block.textContent = '';
    // Já traduzido: as palavras soltas não devem passar pelo dicionário de novo
    block.setAttribute('translate', 'no');
    const spans = words.map((word, i) => {
      const span = document.createElement('span');
      span.className = 'lp-word';
      span.setAttribute('aria-hidden', 'true');
      span.textContent = word;
      block.appendChild(span);
      if (i < words.length - 1) block.appendChild(document.createTextNode(' '));
      return span;
    });

    if (reduceMotion || !('IntersectionObserver' in window)) {
      spans.forEach((span) => span.classList.add('is-on'));
      return;
    }
    // A linha de disparo fica a 40% do fim da tela: a palavra acende quando passa dela,
    // em ordem de leitura, e apaga de novo só se voltar para baixo da linha.
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        entry.target.classList.toggle('is-on', entry.isIntersecting || entry.boundingClientRect.top < 0);
      });
    }, { rootMargin: '0px 0px -40% 0px', threshold: 1 });
    // Palavras na mesma linha cruzam juntas; um atraso curto mantém a ordem de leitura
    spans.forEach((span, i) => {
      span.style.transitionDelay = `${(i % 6) * 70}ms`;
      observer.observe(span);
    });
  });
}

// ── Link ativo na navegação conforme a seção visível ─────────────────────────
function initActiveNav() {
  const links = Array.from(document.querySelectorAll('[data-nav-link]'));
  const sections = links
    .map((link) => document.querySelector(link.getAttribute('href')))
    .filter(Boolean);
  if (!sections.length || !('IntersectionObserver' in window)) return;
  const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (!entry.isIntersecting) return;
      links.forEach((link) => {
        if (link.getAttribute('href') === `#${entry.target.id}`) link.setAttribute('aria-current', 'true');
        else link.removeAttribute('aria-current');
      });
    });
  }, { rootMargin: '-45% 0px -50% 0px' });
  sections.forEach((section) => observer.observe(section));
}

// /planos abre direto na seção de planos
function initPlansRoute() {
  if (window.location.pathname.replace(/\/$/, '') === '/planos' && !window.location.hash) {
    document.getElementById('planos')?.scrollIntoView({ behavior: 'auto', block: 'start' });
  }
}

initMenu();
initTabs();
initReveal();
initWordReveal();
initActiveNav();
initPlansRoute();
