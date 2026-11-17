/**
 * Mural do topo da página /inicio: um cartão-resposta (aquele das provas, com as
 * bolinhas A a E) que se marca sozinho numa onda diagonal e reage ao cursor.
 *
 * Desenho em duas camadas: a base (números, círculos e letras) é desenhada uma vez numa
 * tela fora da página; a cada quadro só entram as bolinhas marcadas e o brilho do cursor.
 * Para quando sai da tela ou a aba fica escondida. Com prefers-reduced-motion, desenha um
 * quadro parado com algumas marcas e não anima.
 */

const LETTERS = ['A', 'B', 'C', 'D', 'E'];
const ROW_H = 30;
const BUBBLE_R = 8;
const BUBBLE_GAP = 24;
const NUM_W = 36;
const COL_GAP = 40;
const COL_W = NUM_W + LETTERS.length * BUBBLE_GAP + COL_GAP;
const WAVE_SPEED = 0.16;   // px por ms
const WAVE_BAND = 720;     // largura da faixa marcada atrás da frente da onda
const POINTER_RADIUS = 140;

const COLORS = {
  bg: '#000000',
  line: '#272727',
  letter: '#4d4d4d',
  num: '#3b3b3b',
  near: '#9B9B9B',
  mark: '#FF7A5C',
  markInk: '#000000',
  touched: '#EDEDED',
};

// Número "aleatório" fixo por linha: o desenho é o mesmo a cada visita
function seeded(n) {
  const x = Math.sin(n * 12.9898) * 43758.5453;
  return x - Math.floor(x);
}

export function initMural(canvas, { reduceMotion = false } = {}) {
  if (!canvas?.getContext) return { destroy() {} };
  const ctx = canvas.getContext('2d');
  const base = document.createElement('canvas');
  const baseCtx = base.getContext('2d');

  let rows = [];
  let width = 0;
  let height = 0;
  let dpr = 1;
  let frame = null;
  let visible = true;
  let startedAt = performance.now();
  const pointer = { x: -9999, y: -9999, inside: false };
  const touched = new Map(); // linha -> { letter, at }

  function bubbleX(row, i) {
    return row.x + NUM_W + i * BUBBLE_GAP + BUBBLE_R;
  }

  function layout() {
    const rect = canvas.getBoundingClientRect();
    width = Math.max(1, rect.width);
    height = Math.max(1, rect.height);
    dpr = Math.min(window.devicePixelRatio || 1, 2);
    for (const c of [canvas, base]) {
      c.width = Math.round(width * dpr);
      c.height = Math.round(height * dpr);
    }
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    baseCtx.setTransform(dpr, 0, 0, dpr, 0, 0);

    const cols = Math.ceil(width / COL_W) + 1;
    const perCol = Math.ceil(height / ROW_H) + 1;
    const offsetX = (width - cols * COL_W) / 2 + COL_GAP / 2;
    rows = [];
    let n = 1;
    for (let c = 0; c < cols; c++) {
      for (let r = 0; r < perCol; r++) {
        const x = offsetX + c * COL_W;
        const y = 16 + r * ROW_H;
        rows.push({ x, y, n, answer: Math.floor(seeded(n) * LETTERS.length), lag: seeded(n + 999) * 160, d: x * 0.8 + y });
        n++;
      }
    }
    drawBase();
  }

  function drawBubble(target, cx, cy, letter, { stroke, fill, ink }) {
    target.beginPath();
    target.arc(cx, cy, BUBBLE_R, 0, Math.PI * 2);
    if (fill) {
      target.fillStyle = fill;
      target.fill();
    }
    target.lineWidth = 1;
    target.strokeStyle = stroke;
    target.stroke();
    target.fillStyle = ink;
    target.fillText(letter, cx, cy + 0.5);
  }

  function setFont(target) {
    target.font = '500 9px "DM Mono", ui-monospace, monospace';
    target.textAlign = 'center';
    target.textBaseline = 'middle';
  }

  function drawBase() {
    baseCtx.fillStyle = COLORS.bg;
    baseCtx.fillRect(0, 0, width, height);
    setFont(baseCtx);
    for (const row of rows) {
      baseCtx.fillStyle = COLORS.num;
      baseCtx.textAlign = 'right';
      baseCtx.fillText(String(row.n).padStart(2, '0'), row.x + NUM_W - 10, row.y + 0.5);
      baseCtx.textAlign = 'center';
      LETTERS.forEach((letter, i) => {
        drawBubble(baseCtx, bubbleX(row, i), row.y, letter, { stroke: COLORS.line, ink: COLORS.letter });
      });
    }
  }

  function draw(now) {
    ctx.globalAlpha = 1;
    ctx.drawImage(base, 0, 0, width, height);
    setFont(ctx);

    const span = width * 0.8 + height + WAVE_BAND * 2;
    // A onda começa no meio do caminho: a primeira tela já mostra marcas
    const front = reduceMotion ? span * 0.62 : ((now - startedAt) * WAVE_SPEED + span * 0.45) % span;

    for (let index = 0; index < rows.length; index++) {
      const row = rows[index];

      // Onda: marca a resposta da linha quando a frente passa e apaga no fim da faixa
      const behind = front - row.d - row.lag;
      if (behind > 0 && behind < WAVE_BAND) {
        const fadeIn = Math.min(1, behind / 80);
        const fadeOut = Math.min(1, (WAVE_BAND - behind) / 240);
        ctx.globalAlpha = Math.min(fadeIn, fadeOut);
        drawBubble(ctx, bubbleX(row, row.answer), row.y, LETTERS[row.answer], {
          stroke: COLORS.mark, fill: COLORS.mark, ink: COLORS.markInk,
        });
      }

      // Cursor: as linhas perto acendem e a bolinha embaixo dele é marcada
      if (pointer.inside) {
        const dy = Math.abs(row.y - pointer.y);
        if (dy < POINTER_RADIUS) {
          for (let i = 0; i < LETTERS.length; i++) {
            const cx = bubbleX(row, i);
            const dist = Math.hypot(cx - pointer.x, row.y - pointer.y);
            if (dist > POINTER_RADIUS) continue;
            ctx.globalAlpha = 1 - dist / POINTER_RADIUS;
            drawBubble(ctx, cx, row.y, LETTERS[i], { stroke: COLORS.near, ink: COLORS.near });
            if (dist < BUBBLE_R + 3) touched.set(index, { letter: i, at: now });
          }
        }
      }

      const mark = touched.get(index);
      if (mark) {
        const age = now - mark.at;
        if (age > 1600) {
          touched.delete(index);
        } else {
          ctx.globalAlpha = 1 - age / 1600;
          drawBubble(ctx, bubbleX(row, mark.letter), row.y, LETTERS[mark.letter], {
            stroke: COLORS.touched, fill: COLORS.touched, ink: COLORS.markInk,
          });
        }
      }
    }
    ctx.globalAlpha = 1;
  }

  function loop(now) {
    frame = null;
    draw(now);
    if (!reduceMotion && visible && !document.hidden) frame = requestAnimationFrame(loop);
  }

  function start() {
    if (!frame && !reduceMotion) frame = requestAnimationFrame(loop);
  }

  function stop() {
    if (frame) cancelAnimationFrame(frame);
    frame = null;
  }

  layout();
  draw(performance.now());

  // A fonte DM Mono pode chegar depois do primeiro desenho
  document.fonts?.ready.then(() => { drawBase(); draw(performance.now()); });

  let resizeTimer = null;
  const onResize = () => {
    window.clearTimeout(resizeTimer);
    resizeTimer = window.setTimeout(() => { layout(); draw(performance.now()); }, 120);
  };
  window.addEventListener('resize', onResize, { passive: true });

  if (!reduceMotion) {
    const host = canvas.parentElement || canvas;
    host.addEventListener('pointermove', (event) => {
      const rect = canvas.getBoundingClientRect();
      pointer.x = event.clientX - rect.left;
      pointer.y = event.clientY - rect.top;
      pointer.inside = true;
    }, { passive: true });
    host.addEventListener('pointerleave', () => { pointer.inside = false; }, { passive: true });

    if ('IntersectionObserver' in window) {
      new IntersectionObserver(([entry]) => {
        visible = entry.isIntersecting;
        if (visible) start(); else stop();
      }).observe(canvas);
    }
    document.addEventListener('visibilitychange', () => { if (document.hidden) stop(); else if (visible) start(); });
    start();
  }

  return {
    destroy() {
      stop();
      window.removeEventListener('resize', onResize);
    },
  };
}
