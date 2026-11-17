/**
 * Rolagem suave no estilo do Lenis (lenis.dev), sem dependência externa.
 *
 * Como funciona: a roda do mouse e o trackpad não rolam a página direto. Cada evento soma
 * ao "alvo" e, a cada quadro, a posição real anda uma fração (lerp) do caminho até ele,
 * desacelerando até parar. Teclado, barra de rolagem, busca da página e toque continuam
 * nativos: o módulo só acompanha a posição para avisar quem depende dela.
 *
 * Fica desligado (rolagem nativa) em telas de toque, com prefers-reduced-motion e dentro
 * de elementos que rolam por conta própria (menus, modais, caixas com overflow).
 *
 * Uso:
 *   const scroller = createSmoothScroll();
 *   scroller.on(({ scroll, velocity, limit }) => { ... });   // um aviso por quadro
 *   scroller.scrollTo(document.querySelector('#secao'));
 */

const clamp = (value, min, max) => Math.min(max, Math.max(min, value));

function canScrollInside(start, deltaY) {
  for (let el = start; el && el !== document.body && el !== document.documentElement; el = el.parentElement) {
    if (!(el instanceof HTMLElement)) continue;
    const style = getComputedStyle(el);
    const scrollable = /(auto|scroll)/.test(style.overflowY) && el.scrollHeight > el.clientHeight + 1;
    if (!scrollable) continue;
    if (deltaY > 0 && el.scrollTop + el.clientHeight < el.scrollHeight - 1) return true;
    if (deltaY < 0 && el.scrollTop > 0) return true;
  }
  return false;
}

export function createSmoothScroll({ lerp = 0.1, wheelMultiplier = 1, anchorOffset = 80 } = {}) {
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  const finePointer = window.matchMedia('(hover: hover) and (pointer: fine)');
  const listeners = new Set();

  let enabled = !reduceMotion.matches && finePointer.matches;
  let current = window.scrollY;
  let target = current;
  let velocity = 0;
  let frame = null;      // animação da rolagem suave em andamento
  let notify = null;     // aviso pendente vindo da rolagem nativa
  let lastNative = current;

  const limit = () => Math.max(0, document.documentElement.scrollHeight - window.innerHeight);

  function emit() {
    const state = { scroll: current, velocity, limit: limit() };
    listeners.forEach((fn) => fn(state));
  }

  function step() {
    frame = null;
    const distance = target - current;
    if (Math.abs(distance) < 0.5) {
      current = target;
      velocity = 0;
    } else {
      velocity = distance * lerp;
      current += velocity;
      frame = requestAnimationFrame(step);
    }
    window.scrollTo(0, current);
    emit();
  }

  function animateTo(y) {
    target = clamp(y, 0, limit());
    if (!frame) {
      current = window.scrollY;
      frame = requestAnimationFrame(step);
    }
  }

  function onWheel(event) {
    if (!enabled || event.ctrlKey || event.defaultPrevented) return; // ctrl + roda = zoom
    if (document.body.classList.contains('in-menu-open')) return;
    if (canScrollInside(event.target, event.deltaY)) return;
    event.preventDefault();
    const unit = event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? window.innerHeight : 1;
    // Sem animação em curso, parte da posição real (pode ter mudado pelo teclado)
    const base = frame ? target : window.scrollY;
    target = clamp(base + event.deltaY * unit * wheelMultiplier, 0, limit());
    if (!frame) {
      current = window.scrollY;
      frame = requestAnimationFrame(step);
    }
  }

  // Rolagem nativa (teclado, barra, toque, busca): acompanha e avisa uma vez por quadro
  function onNativeScroll() {
    if (frame || notify) return;
    notify = requestAnimationFrame(() => {
      notify = null;
      const y = window.scrollY;
      velocity = y - lastNative;
      lastNative = y;
      current = y;
      target = y;
      emit();
    });
  }

  function scrollTo(destination, { immediate = false } = {}) {
    let y = destination;
    if (destination instanceof Element) {
      y = destination.getBoundingClientRect().top + window.scrollY - anchorOffset;
    }
    if (typeof y !== 'number' || Number.isNaN(y)) return;
    if (immediate || !enabled) {
      window.scrollTo({ top: clamp(y, 0, limit()), behavior: 'auto' });
      return;
    }
    animateTo(y);
  }

  // Links internos (#secao) usam a mesma desaceleração
  function onClick(event) {
    if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey) return;
    const link = event.target.closest('a[href^="#"]');
    if (!link) return;
    const id = decodeURIComponent(link.getAttribute('href').slice(1));
    const section = id ? document.getElementById(id) : null;
    if (!section) return;
    event.preventDefault();
    scrollTo(section);
    history.pushState(null, '', `#${id}`);
    // Leva o foco junto para quem navega pelo teclado, sem pular a tela
    if (!section.hasAttribute('tabindex')) section.setAttribute('tabindex', '-1');
    section.focus({ preventScroll: true });
  }

  function refreshEnabled() {
    enabled = !reduceMotion.matches && finePointer.matches;
    if (!enabled && frame) {
      cancelAnimationFrame(frame);
      frame = null;
    }
  }

  window.addEventListener('wheel', onWheel, { passive: false });
  window.addEventListener('scroll', onNativeScroll, { passive: true });
  window.addEventListener('resize', () => { target = clamp(target, 0, limit()); emit(); }, { passive: true });
  document.addEventListener('click', onClick);
  reduceMotion.addEventListener?.('change', refreshEnabled);
  finePointer.addEventListener?.('change', refreshEnabled);

  return {
    on(fn) { listeners.add(fn); fn({ scroll: window.scrollY, velocity: 0, limit: limit() }); },
    off(fn) { listeners.delete(fn); },
    scrollTo,
    get enabled() { return enabled; },
  };
}
