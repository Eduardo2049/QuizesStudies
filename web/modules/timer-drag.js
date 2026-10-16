// ─── Cronômetro arrastável e redimensionável ─────────────────────────────────
// Posição e escala valem só para a sessão atual (sessionStorage).
// Arrastar move; clique simples continua abrindo a configuração de tempo;
// a alça no canto redimensiona e, com duplo clique, restaura o padrão.

const STORAGE_KEY = 'quiz_timer_layout';
const MIN_SCALE = 0.75;
const MAX_SCALE = 3;
const DRAG_THRESHOLD = 4;   // px antes de considerar arrasto (preserva o clique)
const EDGE = 8;             // margem mínima até a borda da janela
const KEY_STEP = 16;        // px por seta (Shift = 4x)
const SCALE_STEP = 0.1;

const clamp = (value, min, max) => Math.min(Math.max(value, min), max);

function readLayout() {
  try {
    const data = JSON.parse(sessionStorage.getItem(STORAGE_KEY) || 'null');
    if (data && Number.isFinite(data.scale)) return data;
  } catch { /* storage indisponível */ }
  return null;
}

function writeLayout(layout) {
  try {
    if (layout) sessionStorage.setItem(STORAGE_KEY, JSON.stringify(layout));
    else sessionStorage.removeItem(STORAGE_KEY);
  } catch { /* storage indisponível */ }
}

export function initTimerDrag(timer, timerConfig) {
  if (!timer) return;

  // x/y = canto superior esquerdo em px; null = posição padrão do CSS
  let state = { x: null, y: null, scale: 1 };
  let suppressClick = false;

  const handle = document.createElement('button');
  handle.type = 'button';
  handle.className = 'timer-resize-handle';
  handle.setAttribute('aria-label', 'Redimensionar cronômetro (duplo clique restaura o padrão)');
  handle.title = 'Arraste para redimensionar · duplo clique restaura';
  timer.after(handle);

  if (!timer.hasAttribute('tabindex')) timer.tabIndex = 0;
  timer.title = 'Arraste para mover · clique para definir o tempo';
  timer.setAttribute('aria-keyshortcuts', 'ArrowUp ArrowDown ArrowLeft ArrowRight + - 0');

  function isMoved() {
    return state.x !== null && state.y !== null;
  }

  function placeHandleAndConfig() {
    const rect = timer.getBoundingClientRect();
    if (!rect.width) return; // cronômetro oculto
    const size = handle.offsetWidth || 24;
    // Alça um pouco para fora do canto inferior direito. Sem espaço à direita,
    // desce para baixo do cronômetro (no celular a alça de 44px cobriria o número);
    // sem espaço embaixo, sobe para cima dele.
    let left = rect.right - size * 0.45;
    let top = rect.bottom - size * 0.45;
    if (left + size > window.innerWidth) {
      left = window.innerWidth - size;
      top = rect.bottom;
    }
    if (top + size > window.innerHeight) top = rect.top - size;
    left = clamp(left, 0, window.innerWidth - size);
    top = clamp(top, 0, window.innerHeight - size);
    handle.style.left = `${Math.round(left)}px`;
    handle.style.top = `${Math.round(top)}px`;

    if (!timerConfig) return;
    if (isMoved()) {
      const cfgWidth = timerConfig.offsetWidth;
      const left = clamp(rect.right - cfgWidth, EDGE, window.innerWidth - cfgWidth - EDGE);
      const below = rect.bottom + timerConfig.offsetHeight + EDGE <= window.innerHeight;
      timerConfig.style.left = `${Math.round(left)}px`;
      timerConfig.style.right = 'auto';
      timerConfig.style.top = below
        ? `${Math.round(rect.bottom)}px`
        : `${Math.round(rect.top - timerConfig.offsetHeight)}px`;
    } else {
      timerConfig.style.left = '';
      timerConfig.style.right = '';
      timerConfig.style.top = '';
    }
  }

  function keepInViewport() {
    if (!isMoved()) return;
    const rect = timer.getBoundingClientRect();
    if (!rect.width) return;
    state.x = clamp(state.x, EDGE, Math.max(EDGE, window.innerWidth - rect.width - EDGE));
    state.y = clamp(state.y, EDGE, Math.max(EDGE, window.innerHeight - rect.height - EDGE));
    timer.style.left = `${state.x}px`;
    timer.style.top = `${state.y}px`;
  }

  function apply({ persist = true } = {}) {
    timer.style.setProperty('--timer-scale', String(state.scale));
    if (isMoved()) {
      timer.style.left = `${state.x}px`;
      timer.style.top = `${state.y}px`;
      timer.style.right = 'auto';
      keepInViewport();
    } else {
      timer.style.left = '';
      timer.style.top = '';
      timer.style.right = '';
    }
    timer.classList.toggle('timer--custom', isMoved() || state.scale !== 1);
    placeHandleAndConfig();
    if (persist) {
      writeLayout(isMoved() || state.scale !== 1 ? state : null);
    }
  }

  // Fixa a posição atual em px antes de mover ou escalar (deixa de usar right/top do CSS)
  function detach() {
    if (isMoved()) return;
    const rect = timer.getBoundingClientRect();
    state.x = rect.left;
    state.y = rect.top;
  }

  function reset() {
    state = { x: null, y: null, scale: 1 };
    apply();
  }

  // ── Arrastar o cronômetro ──
  timer.addEventListener('pointerdown', (event) => {
    if (event.button !== 0) return;
    const rect = timer.getBoundingClientRect();
    const offsetX = event.clientX - rect.left;
    const offsetY = event.clientY - rect.top;
    const startX = event.clientX;
    const startY = event.clientY;
    let dragging = false;

    const onMove = (moveEvent) => {
      if (!dragging) {
        if (Math.hypot(moveEvent.clientX - startX, moveEvent.clientY - startY) < DRAG_THRESHOLD) return;
        dragging = true;
        detach();
        timer.classList.add('is-dragging');
        timerConfig?.classList.remove('timer-config--visible');
        // Continua recebendo o movimento fora da janela (os eventos sobem até o window)
        try { timer.setPointerCapture(event.pointerId); } catch { /* ponteiro já liberado */ }
      }
      state.x = moveEvent.clientX - offsetX;
      state.y = moveEvent.clientY - offsetY;
      apply({ persist: false });
    };

    const onUp = () => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
      window.removeEventListener('pointercancel', onUp);
      if (dragging) {
        timer.classList.remove('is-dragging');
        suppressClick = true;
        setTimeout(() => { suppressClick = false; }, 0); // sem click após soltar fora
        apply();
      }
    };

    // Na janela: um movimento rápido sai do cronômetro antes do primeiro pointermove
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
    window.addEventListener('pointercancel', onUp);
  });

  // Um arrasto não deve abrir o modal de tempo (captura roda antes do handler do app.js)
  timer.addEventListener('click', (event) => {
    if (suppressClick) {
      suppressClick = false;
      event.stopImmediatePropagation();
      event.preventDefault();
    }
  }, true);

  // ── Redimensionar pela alça ──
  handle.addEventListener('pointerdown', (event) => {
    if (event.button !== 0) return;
    event.preventDefault();
    detach();
    const startScale = state.scale;
    const startWidth = timer.getBoundingClientRect().width || 1;
    const startX = event.clientX;
    const startY = event.clientY;
    handle.setPointerCapture?.(event.pointerId);
    timer.classList.add('is-resizing');

    const onMove = (moveEvent) => {
      const delta = ((moveEvent.clientX - startX) + (moveEvent.clientY - startY)) / 2;
      state.scale = clamp(startScale * (startWidth + delta) / startWidth, MIN_SCALE, MAX_SCALE);
      apply({ persist: false });
    };

    const onUp = () => {
      handle.removeEventListener('pointermove', onMove);
      handle.removeEventListener('pointerup', onUp);
      handle.removeEventListener('pointercancel', onUp);
      timer.classList.remove('is-resizing');
      apply();
    };

    handle.addEventListener('pointermove', onMove);
    handle.addEventListener('pointerup', onUp);
    handle.addEventListener('pointercancel', onUp);
  });

  handle.addEventListener('dblclick', reset);

  // ── Teclado: setas movem, +/- escalam, 0 restaura, Enter/Espaço abre o tempo ──
  function onKey(event) {
    const step = event.shiftKey ? KEY_STEP * 4 : KEY_STEP;
    const moves = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] };
    let handled = true;

    if (moves[event.key]) {
      detach();
      state.x += moves[event.key][0];
      state.y += moves[event.key][1];
      apply();
    } else if (event.key === '+' || event.key === '=') {
      detach();
      state.scale = clamp(state.scale + SCALE_STEP, MIN_SCALE, MAX_SCALE);
      apply();
    } else if (event.key === '-' || event.key === '_') {
      detach();
      state.scale = clamp(state.scale - SCALE_STEP, MIN_SCALE, MAX_SCALE);
      apply();
    } else if (event.key === '0') {
      reset();
    } else if (event.target === timer && (event.key === 'Enter' || event.key === ' ')) {
      timer.click();
    } else {
      handled = false;
    }

    if (handled) {
      event.preventDefault();
      event.stopPropagation(); // não dispara os atalhos globais de navegação
    }
  }

  timer.addEventListener('keydown', onKey);
  handle.addEventListener('keydown', onKey);

  // ── Mantém tudo dentro da tela e alinhado ──
  window.addEventListener('resize', () => {
    keepInViewport();
    placeHandleAndConfig();
  });
  if ('ResizeObserver' in window) {
    // Dispara quando o cronômetro aparece/some ou muda de largura
    new ResizeObserver(() => {
      keepInViewport();
      placeHandleAndConfig();
    }).observe(timer);
  }

  const saved = readLayout();
  if (saved) {
    state = {
      x: Number.isFinite(saved.x) ? saved.x : null,
      y: Number.isFinite(saved.y) ? saved.y : null,
      scale: clamp(saved.scale, MIN_SCALE, MAX_SCALE),
    };
  }
  apply({ persist: false });
}
