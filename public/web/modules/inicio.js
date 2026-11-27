/**
 * Página inicial protótipo (/inicio).
 *
 * Rolagem suave própria (smooth-scroll.js), cartão-resposta animado no topo (mural.js),
 * mural Você / IA, tagline palavra por palavra, trilho horizontal preso na tela em
 * "Como funciona", números que contam ao aparecer e uma faixa de temas que acelera com a
 * rolagem. Tudo para em prefers-reduced-motion. Sem dependências externas.
 *
 * i18n.js vem primeiro: ele traduz a página ao ser importado, antes de a tagline ser
 * quebrada em palavras (a tradução casa frases inteiras do dicionário).
 */
import './i18n.js?v=15';
import { initTheme, toggleTheme } from './theme.js?v=10';
import { createSmoothScroll } from './smooth-scroll.js?v=1';
import { initMural } from './mural.js?v=2';

const root = document.documentElement;
const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
root.classList.add('in-js');

const scroller = createSmoothScroll({ lerp: 0.1, anchorOffset: 96 });

// ── Menu do celular (painel de altura total, links em sequência) ─────────────
function initMenu() {
  const toggle = document.getElementById('inMenuToggle');
  const menu = document.getElementById('inMenu');
  if (!toggle || !menu) return;
  const links = Array.from(menu.querySelectorAll('[data-menu-link]'));
  const STEP = 60;
  const MAX_TOTAL = 400;

  function open() {
    menu.hidden = false;
    document.body.classList.add('in-menu-open');
    toggle.setAttribute('aria-expanded', 'true');
    toggle.setAttribute('aria-label', 'Fechar menu');
    const step = Math.min(STEP, MAX_TOTAL / Math.max(links.length, 1));
    links.forEach((link, i) => { link.style.transitionDelay = `${Math.round(i * step)}ms`; });
    requestAnimationFrame(() => requestAnimationFrame(() => menu.classList.add('is-open')));
    links[0]?.focus({ preventScroll: true });
  }

  function close({ returnFocus = true } = {}) {
    menu.classList.remove('is-open');
    document.body.classList.remove('in-menu-open');
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

// ── Vídeo de apresentação: botão sobre a capa e pausa ao sair da tela ────────
function initVideo() {
  const frame = document.querySelector('[data-video]');
  const video = frame?.querySelector('video');
  const play = frame?.querySelector('[data-video-play]');
  if (!video || !play) return;
  // Antes do play só o botão grande; os controles nativos voltam ao tocar (sem JS, ficam sempre)
  frame.classList.add('has-overlay');
  video.controls = false;
  play.addEventListener('click', () => {
    video.play().catch(() => { video.controls = true; });
  });
  video.addEventListener('play', () => {
    frame.classList.add('is-playing');
    video.controls = true;
    video.focus({ preventScroll: true });
  });
  video.addEventListener('ended', () => {
    frame.classList.remove('is-playing');
    video.controls = false;
    play.focus({ preventScroll: true });
  });
  if (!('IntersectionObserver' in window)) return;
  const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry) => { if (!entry.isIntersecting && !video.paused) video.pause(); });
  }, { threshold: 0.2 });
  observer.observe(video);
}

// ── Link ativo na navegação conforme a seção visível ─────────────────────────
function initActiveNav() {
  const links = Array.from(document.querySelectorAll('[data-nav-link]'));
  const sections = links.map((link) => document.querySelector(link.getAttribute('href'))).filter(Boolean);
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

// ── Hero: cartão-resposta e parallax leve ────────────────────────────────────
function initHero() {
  const canvas = document.getElementById('inMuralCanvas');
  initMural(canvas, { reduceMotion });
  // Duas trocas de quadro garantem que o estado inicial foi pintado antes da entrada
  requestAnimationFrame(() => requestAnimationFrame(() => root.classList.add('is-ready')));
  if (reduceMotion || !canvas) return;
  const stage = canvas.parentElement;
  scroller.on(({ scroll }) => {
    const h = stage.offsetHeight;
    if (scroll > h * 1.2) return;
    // A ilustração anda mais devagar que a página: sensação de profundidade
    canvas.style.transform = `translate3d(0, ${(scroll * 0.35).toFixed(1)}px, 0)`;
  });
}

// ── Mural Você / IA ──────────────────────────────────────────────────────────
function initMuralSwitch() {
  const buttons = [document.getElementById('inSwitchYou'), document.getElementById('inSwitchAi')].filter(Boolean);
  if (buttons.length !== 2) return;
  let busy = false;

  function show(button) {
    if (busy || button.getAttribute('aria-pressed') === 'true') return;
    const nextList = document.getElementById(button.getAttribute('aria-controls'));
    const other = buttons.find((b) => b !== button);
    const currentList = document.getElementById(other.getAttribute('aria-controls'));
    if (!nextList || !currentList) return;
    buttons.forEach((b) => b.setAttribute('aria-pressed', String(b === button)));

    if (reduceMotion) {
      currentList.hidden = true;
      nextList.hidden = false;
      return;
    }
    busy = true;
    currentList.classList.add('is-leaving');
    window.setTimeout(() => {
      currentList.hidden = true;
      currentList.classList.remove('is-leaving', 'is-shown');
      nextList.classList.add('is-entering');
      nextList.hidden = false;
      const items = Array.from(nextList.children);
      items.forEach((item, i) => { item.style.transitionDelay = `${i * 60}ms`; });
      requestAnimationFrame(() => requestAnimationFrame(() => {
        nextList.classList.remove('is-entering');
        nextList.classList.add('is-shown');
        busy = false;
      }));
    }, 300);
  }

  buttons.forEach((button) => button.addEventListener('click', () => show(button)));
}

// ── Revelação das seções ao entrar na tela (uma vez só) ──────────────────────
function initReveal() {
  const items = document.querySelectorAll('.in-reveal');
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
    const text = block.textContent.trim();
    const words = text.split(/\s+/);
    block.setAttribute('aria-label', text);
    block.textContent = '';
    block.setAttribute('translate', 'no'); // já traduzido: as palavras soltas não voltam ao dicionário
    const spans = words.map((word, i) => {
      const span = document.createElement('span');
      span.className = 'in-word';
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
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        entry.target.classList.toggle('is-on', entry.isIntersecting || entry.boundingClientRect.top < 0);
      });
    }, { rootMargin: '0px 0px -40% 0px', threshold: 1 });
    spans.forEach((span, i) => {
      span.style.transitionDelay = `${(i % 6) * 70}ms`;
      observer.observe(span);
    });
  });
}

// ── Como funciona: a rolagem vertical move o trilho na horizontal ────────────
function initSteps() {
  const section = document.getElementById('como-funciona');
  const track = document.getElementById('inStepsTrack');
  const counter = document.getElementById('inStepsCurrent');
  if (!section || !track) return;
  const steps = Array.from(track.children);
  const pinned = window.matchMedia('(min-width: 901px)');
  let lastActive = -1;

  function setActive(index) {
    if (index === lastActive) return;
    lastActive = index;
    steps.forEach((step, i) => step.classList.toggle('is-active', i === index));
    if (counter) counter.textContent = String(index + 1).padStart(2, '0');
  }

  scroller.on(() => {
    if (reduceMotion || !pinned.matches) {
      track.style.transform = '';
      return;
    }
    const rect = section.getBoundingClientRect();
    const travel = section.offsetHeight - window.innerHeight;
    if (travel <= 0) return;
    const progress = Math.min(1, Math.max(0, -rect.top / travel));
    const distance = Math.max(0, track.scrollWidth - window.innerWidth);
    track.style.transform = `translate3d(${(-progress * distance).toFixed(1)}px, 0, 0)`;
    setActive(Math.min(steps.length - 1, Math.round(progress * (steps.length - 1))));
  });

  if (reduceMotion || !pinned.matches) steps.forEach((step) => step.classList.add('is-active'));
  pinned.addEventListener?.('change', () => {
    if (!pinned.matches) steps.forEach((step) => step.classList.add('is-active'));
    else lastActive = -1;
  });
}

// ── Números contam até o valor ao aparecer ───────────────────────────────────
function initCounters() {
  const items = document.querySelectorAll('[data-count-to]');
  if (reduceMotion || !('IntersectionObserver' in window)) return;
  const observer = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (!entry.isIntersecting) return;
      observer.unobserve(entry.target);
      const el = entry.target;
      const end = Number(el.dataset.countTo) || 0;
      const duration = 900;
      const started = performance.now();
      const tick = (now) => {
        const t = Math.min(1, (now - started) / duration);
        const eased = 1 - Math.pow(1 - t, 3); // desacelera como a curva base
        el.textContent = String(Math.round(end * eased));
        if (t < 1) requestAnimationFrame(tick);
      };
      el.textContent = '0';
      requestAnimationFrame(tick);
    });
  }, { threshold: 0.6 });
  items.forEach((el) => observer.observe(el));
}

// ── Faixa de temas: anda sozinha e acelera com a rolagem ─────────────────────
function initMarquee() {
  const viewport = document.getElementById('inMarquee');
  const track = document.getElementById('inMarqueeTrack');
  if (!viewport || !track) return;
  if (reduceMotion) {
    viewport.parentElement?.classList.add('is-static');
    return;
  }
  // Uma cópia da lista emenda o fim no começo; a cópia fica fora da leitura e do Tab
  const originals = Array.from(track.children);
  originals.forEach((item) => {
    const clone = item.cloneNode(true);
    clone.setAttribute('aria-hidden', 'true');
    clone.querySelectorAll('a').forEach((a) => a.setAttribute('tabindex', '-1'));
    track.appendChild(clone);
  });

  let offset = 0;
  let boost = 0;
  let paused = false;
  let visible = false;
  let last = performance.now();
  let frame = null;

  function loop(now) {
    frame = null;
    const dt = Math.min(64, now - last);
    last = now;
    const half = track.scrollWidth / 2;
    boost *= 0.92;
    const speed = paused ? 0 : 0.04 + Math.min(1.2, Math.abs(boost)) * 0.6; // px por ms
    offset = (offset + speed * dt) % half;
    track.style.transform = `translate3d(${(-offset).toFixed(1)}px, 0, 0)`;
    if (visible) frame = requestAnimationFrame(loop);
  }

  function start() {
    if (frame) return;
    last = performance.now();
    frame = requestAnimationFrame(loop);
  }

  scroller.on(({ velocity }) => { boost += velocity * 0.02; });
  viewport.addEventListener('pointerenter', () => { paused = true; });
  viewport.addEventListener('pointerleave', () => { paused = false; });
  viewport.addEventListener('focusin', () => { paused = true; });
  viewport.addEventListener('focusout', () => { paused = false; });

  if ('IntersectionObserver' in window) {
    new IntersectionObserver(([entry]) => {
      visible = entry.isIntersecting;
      if (visible) start();
    }).observe(viewport);
  } else {
    visible = true;
    start();
  }
}

// ── Quem já entrou vê "Meus simulados" no lugar de "Entrar" ──────────────────
function initAccountLinks() {
  fetch('/api/auth/me', { cache: 'no-store', credentials: 'same-origin' })
    .then((res) => {
      if (!res.ok) return;
      ['inNavAccount', 'inMenuAccount'].forEach((id) => {
        const link = document.getElementById(id);
        if (!link) return;
        link.textContent = 'Meus simulados';
        link.setAttribute('href', '/app');
      });
    })
    .catch(() => {});
}

initTheme();
document.getElementById('themeToggle')?.addEventListener('click', () => {
  toggleTheme();
});

initMenu();
initAccountLinks();
initActiveNav();
initHero();
initMuralSwitch();
initVideo();
initReveal();
initWordReveal();
initSteps();
initCounters();
initMarquee();
