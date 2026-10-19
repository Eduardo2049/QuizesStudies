import { icon } from './icons.js?v=6';
/**
 * Fundo animado em tela cheia: porte em WebGL puro da cena "Frosty Gradient"
 * do Unicorn Studio (sem SDK nem CDN, porque a CSP só permite 'self'). As
 * camadas da cena, de baixo para cima, com os mesmos parâmetros do original:
 *   1. Noise Fill: Perlin com threshold, que acende manchas sobre a base; o
 *      ponteiro "estufa" o ruído ao redor dele (bulge).
 *   2. Flow Field: 8 passos ao longo de um campo de Perlin, que arrastam o
 *      líquido em correntes.
 *   3. Liquify: ondas suaves que deformam o plano inteiro.
 *   4. Glyph Dither "horizontal lines": nas manchas mais claras, barras
 *      horizontais com espessura proporcional ao brilho.
 * As camadas 2 e 3 só deslocam coordenadas, então 1–3 viram uma única passada
 * procedural numa textura de resolução reduzida (a imagem é macia). A
 * passada de exibição amplia com filtro bilinear, aplica as cores e desenha as
 * barras na resolução da tela.
 *
 * Cores vêm dos tokens --backdrop-* (temas claro e escuro). Pausa com a aba
 * oculta. O botão [data-backdrop-toggle] liga/pausa a animação e a escolha
 * fica salva; sem escolha salva, prefers-reduced-motion (no Windows, "Efeitos
 * de animação" desligado) mostra um único quadro parado. Sem WebGL, o canvas
 * não é criado, o botão fica oculto e fica o gradiente de --bg-gradient.
 */

const MAX_FPS = 30;
const MAX_PIXEL_RATIO = 1.5;
const FIELD_SCALE = 0.5;             // campo em px CSS × isto
const CELL_CSS = 10;                 // célula do glyph dither em px CSS
const COLUMN_HALF_CSS = 480;         // meia-largura do corredor do conteúdo em px CSS
const STILL_FRAME_S = 6;             // quadro parado com boa composição
const MOTION_STORAGE_KEY = 'quiz_backdrop_motion';  // 'on' | 'off'; sem valor, segue o sistema
// Velocidade de cada camada na cena original: uTime avança speed × 60 por segundo.
const SPEED = { noise: 0.16, flow: 0.13, liquify: 0.15 };

const VERTEX_SHADER = `
attribute vec2 a_pos;
void main() { gl_Position = vec4(a_pos, 0.0, 1.0); }
`;

const PRECISION = `
#ifdef GL_FRAGMENT_PRECISION_HIGH
precision highp float;
#else
precision mediump float;
#endif
`;

// Perlin clássico 3D (Stefan Gustavson, MIT). Amplitude reduzida (1.32 em vez
// de 2.2) para bater com a distribuição de brilho das capturas da cena original.
const PERLIN = `
vec3 mod289(vec3 x) { return x - floor(x * (1.0 / 289.0)) * 289.0; }
vec4 mod289(vec4 x) { return x - floor(x * (1.0 / 289.0)) * 289.0; }
vec4 permute(vec4 x) { return mod289(((x * 34.0) + 1.0) * x); }
vec4 taylorInvSqrt(vec4 r) { return 1.79284291400159 - 0.85373472095314 * r; }
vec3 fade(vec3 t) { return t * t * t * (t * (t * 6.0 - 15.0) + 10.0); }

float perlin(vec3 P) {
  vec3 Pi0 = mod289(floor(P));
  vec3 Pi1 = mod289(floor(P) + vec3(1.0));
  vec3 Pf0 = fract(P);
  vec3 Pf1 = Pf0 - vec3(1.0);
  vec4 ix = vec4(Pi0.x, Pi1.x, Pi0.x, Pi1.x);
  vec4 iy = vec4(Pi0.yy, Pi1.yy);
  vec4 ixy = permute(permute(ix) + iy);
  vec4 ixy0 = permute(ixy + Pi0.zzzz);
  vec4 ixy1 = permute(ixy + Pi1.zzzz);

  vec4 gx0 = ixy0 * (1.0 / 7.0);
  vec4 gy0 = fract(floor(gx0) * (1.0 / 7.0)) - 0.5;
  gx0 = fract(gx0);
  vec4 gz0 = vec4(0.5) - abs(gx0) - abs(gy0);
  vec4 sz0 = step(gz0, vec4(0.0));
  gx0 -= sz0 * (step(0.0, gx0) - 0.5);
  gy0 -= sz0 * (step(0.0, gy0) - 0.5);

  vec4 gx1 = ixy1 * (1.0 / 7.0);
  vec4 gy1 = fract(floor(gx1) * (1.0 / 7.0)) - 0.5;
  gx1 = fract(gx1);
  vec4 gz1 = vec4(0.5) - abs(gx1) - abs(gy1);
  vec4 sz1 = step(gz1, vec4(0.0));
  gx1 -= sz1 * (step(0.0, gx1) - 0.5);
  gy1 -= sz1 * (step(0.0, gy1) - 0.5);

  vec3 g000 = vec3(gx0.x, gy0.x, gz0.x);
  vec3 g100 = vec3(gx0.y, gy0.y, gz0.y);
  vec3 g010 = vec3(gx0.z, gy0.z, gz0.z);
  vec3 g110 = vec3(gx0.w, gy0.w, gz0.w);
  vec3 g001 = vec3(gx1.x, gy1.x, gz1.x);
  vec3 g101 = vec3(gx1.y, gy1.y, gz1.y);
  vec3 g011 = vec3(gx1.z, gy1.z, gz1.z);
  vec3 g111 = vec3(gx1.w, gy1.w, gz1.w);

  vec4 norm0 = taylorInvSqrt(vec4(dot(g000, g000), dot(g010, g010), dot(g100, g100), dot(g110, g110)));
  g000 *= norm0.x; g010 *= norm0.y; g100 *= norm0.z; g110 *= norm0.w;
  vec4 norm1 = taylorInvSqrt(vec4(dot(g001, g001), dot(g011, g011), dot(g101, g101), dot(g111, g111)));
  g001 *= norm1.x; g011 *= norm1.y; g101 *= norm1.z; g111 *= norm1.w;

  float n000 = dot(g000, Pf0);
  float n100 = dot(g100, vec3(Pf1.x, Pf0.yz));
  float n010 = dot(g010, vec3(Pf0.x, Pf1.y, Pf0.z));
  float n110 = dot(g110, vec3(Pf1.xy, Pf0.z));
  float n001 = dot(g001, vec3(Pf0.xy, Pf1.z));
  float n101 = dot(g101, vec3(Pf1.x, Pf0.y, Pf1.z));
  float n011 = dot(g011, vec3(Pf0.x, Pf1.yz));
  float n111 = dot(g111, Pf1);

  vec3 f = fade(Pf0);
  vec4 nz = mix(vec4(n000, n100, n010, n110), vec4(n001, n101, n011, n111), f.z);
  vec2 nyz = mix(nz.xy, nz.zw, f.y);
  return 1.32 * mix(nyz.x, nyz.y, f.x);
}
`;

// Passada 1: a cena procedural. Saída: r = intensidade (0 = base, 1 = mancha
// plena), g = posição entre as cores A e B, que acompanha as correntes do flow field.
const FIELD_SHADER = `${PRECISION}
uniform vec2 u_res;        // campo em px
uniform vec3 u_time;       // uTime de cada camada: noise, flow, liquify
uniform vec2 u_mouse;      // ponteiro em 0..1 (origem embaixo), suavizado
${PERLIN}
const float TAU = 6.28318530718;

mat2 rot(float a) { return mat2(cos(a), -sin(a), sin(a), cos(a)); }

// Liquify: frequency 0.5, amplitude 0.3, angle 0.7857, drift 0.5, mix 0.3.
vec2 liquify(vec2 uv, float ar, float time) {
  const float ANGLE = 0.7857 * TAU;
  const float FREQ = 3.0;              // 5 × (frequency + 0.1)
  const float AMP = 0.0723;            // amplitude × mix(0.2, 0.2 / (frequency + 0.05), 0.25)
  vec2 pos = vec2(0.5) + vec2(0.0, 0.5 * time * 0.0125) * rot(-ANGLE);
  vec2 st = uv - pos;
  st.x *= ar;
  st = st * rot(ANGLE);
  float t = time * 0.025;
  for (int k = 1; k <= 5; k++) {
    float i = float(k);
    st = st * rot(i / 5.0 * TAU);
    st.x += AMP * cos(i * FREQ * st.y + t);
    st.y += AMP * sin(i * FREQ * st.x + t);
  }
  st = st * rot(-ANGLE);
  st.x /= ar;
  return mix(uv, st + pos, 0.3);
}

// Flow Field: amount 1, scale 0.2, angle 0.621, phase 0.9, mix radius 0.75.
// tint recebe o último ruído do campo, que separa as correntes da cor A e da cor B.
vec2 flow(vec2 uv, float ar, float time, out float tint) {
  const vec2 POS = vec2(0.5786, 0.7192);
  const float RAD = 0.621 * 6.0 * TAU;  // 360° × angle × 6
  vec2 aspect = vec2(ar, 1.0);
  float amt = 0.02 * max(0.0, 1.0 - length((uv - POS) * aspect));
  float freq = 5.0 * 0.21 / ((ar + 1.0) * 0.5);
  float t = 4.5 + time * 0.0166;
  vec2 st = uv;
  float n = 0.0;
  for (int i = 0; i < 8; i++) {
    vec2 scaled = (clamp(st, -1.0, 2.0) - 0.5) * aspect + (1.0 - POS);
    n = perlin(vec3((scaled - 0.5) * freq, t)) - 0.5;
    st += vec2(cos(n * RAD), sin(n * RAD)) * amt;
  }
  tint = n;
  return clamp(st, 0.0, 1.0);
}

// Noise Fill: Perlin, scale 0.25, amplitude 0.4, skew 0.5, phase 0.8.
float noiseAt(vec2 st, float time) {
  float n = perlin(vec3(st * 0.5, 0.8 + time * 0.03));
  return mix(0.5, n * 0.5 + 0.5, 1.28);
}

// Bulge 0.57 / 0.5 em volta do ponteiro, threshold 0.79 e a rampa de cor
// do original (cosseno entre as duas cores): 0 = base, 1 = mancha plena.
float fill(vec2 uv, float ar, float time) {
  const float SCALE = 4.25;            // mix(1, 14, scale)
  vec2 aspect = vec2(ar, 1.0);
  vec2 st = (uv - 0.5) * aspect * SCALE;
  vec2 toMouse = (uv - u_mouse) * aspect;
  float r = length(toMouse);
  float falloff = 1.0 - smoothstep(0.0, 0.55, r);
  float noise;
  if (falloff > 0.0) {
    // 0.3135 = bulge amount × raio (mix(0.1, 1, bulge scale) = 0.55)
    vec2 offset = -(toMouse / max(r, 1e-5)) * 0.3135 * falloff * falloff / aspect * r * 5.0;
    noise = noiseAt((uv - 0.5 + offset * noiseAt(st, time)) * aspect * SCALE, time);
  } else {
    noise = noiseAt(st, time);
  }
  float t = smoothstep(noise - 0.5, noise + 0.5, 0.79);
  return 0.5 - 0.5 * cos(TAU * t);
}

void main() {
  float ar = u_res.x / u_res.y;
  float tint;
  vec2 uv = flow(liquify(gl_FragCoord.xy / u_res, ar, u_time.z), ar, u_time.y, tint);
  gl_FragColor = vec4(fill(uv, ar, u_time.x), smoothstep(-0.9, 0.3, tint), 0.0, 1.0);
}
`;

// Passada 2: cores + glyph dither + deband. No corredor central, onde o texto
// fica direto sobre o fundo, as manchas perdem força (u_calm, uma por cor,
// porque cada cor tem seu limite de contraste AA); nas laterais a cena
// aparece inteira.
const DISPLAY_SHADER = `${PRECISION}
uniform sampler2D u_field;
uniform vec2 u_res;        // canvas em px de render
uniform float u_cell;      // célula do glyph dither em px de render
uniform vec2 u_column;     // corredor do conteúdo: centro x e meia-largura, em px de render
uniform vec2 u_calm;       // intensidade das manchas dentro do corredor: cor A, cor B
uniform float u_mix;       // ponto de virada da cor A para a B (0.5 = meio a meio)
uniform vec3 u_base;
uniform vec3 u_colorA;
uniform vec3 u_colorB;
uniform vec3 u_line;

float hash(vec2 p) {
  p = fract(p * vec2(123.34, 456.21));
  p += dot(p, p + 45.32);
  return fract(p.x * p.y);
}

float hueMix(float g) {
  return smoothstep(u_mix - 0.25, u_mix + 0.25, g);
}

float calm(float x, float h) {
  return mix(mix(u_calm.x, u_calm.y, h), 1.0, smoothstep(u_column.y, u_column.y * 1.5, abs(x - u_column.x)));
}

void main() {
  vec2 frag = gl_FragCoord.xy;
  vec4 F = texture2D(u_field, frag / u_res);
  float h = hueMix(F.g);

  // Rampa do Noise Fill original (sigmoide por canal), aproximada.
  float w = F.r * calm(frag.x, h);
  float ramp = w * (0.83 + 0.17 * w);
  vec3 color = mix(u_base, mix(u_colorA, u_colorB, h), ramp);

  // Sprite "horizontal lines": 9 glyphs, barra centrada de 0 a 80% da célula,
  // escolhida pelo brilho no centro da célula (só as manchas claras ganham barra).
  vec2 cell = floor(frag / u_cell);
  vec2 center = (cell + 0.5) * u_cell;
  vec2 C = texture2D(u_field, center / u_res).rg;
  float wc = C.r * calm(center.x, hueMix(C.g));
  float level = min(floor(max(0.0, (wc - 0.52) * 6.0)), 8.0);
  float y = (fract(frag.y / u_cell) - 0.5) * u_cell;
  float halfBar = level * 0.05 * u_cell;
  float bar = clamp(min(y + 0.5, halfBar) - max(y - 0.5, -halfBar), 0.0, 1.0);
  color = mix(color, u_line, bar * 0.5);

  color += (hash(frag) - 0.5) / 255.0;
  gl_FragColor = vec4(color, 1.0);
}
`;

let instance = null;

function parseHex(value, fallback) {
  let hex = (value || '').trim().replace('#', '');
  if (hex.length === 3) hex = hex.split('').map((ch) => ch + ch).join('');
  if (!/^[0-9a-f]{6}$/i.test(hex)) return fallback;
  return [0, 2, 4].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
}

function readPalette() {
  const styles = getComputedStyle(document.documentElement);
  const read = (name, fallback) => parseHex(styles.getPropertyValue(name), fallback);
  const unit = (name, fallback) => {
    const value = parseFloat(styles.getPropertyValue(name));
    return Number.isFinite(value) ? Math.min(1, Math.max(0, value)) : fallback;
  };
  const calm = unit('--backdrop-calm', 0.45);
  return {
    calm,
    calmB: unit('--backdrop-calm-b', calm),
    mix: unit('--backdrop-mix', 0.7),
    base: read('--backdrop-base', [23 / 255, 23 / 255, 23 / 255]),
    a: read('--backdrop-a', [58 / 255, 75 / 255, 217 / 255]),
    b: read('--backdrop-b', [124 / 255, 92 / 255, 240 / 255]),
    line: read('--backdrop-line', [143 / 255, 155 / 255, 255 / 255]),
  };
}

function compile(gl, type, source) {
  const shader = gl.createShader(type);
  gl.shaderSource(shader, source);
  gl.compileShader(shader);
  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
    const log = gl.getShaderInfoLog(shader);
    gl.deleteShader(shader);
    throw new Error(`Shader: ${log}`);
  }
  return shader;
}

function createProgram(gl, fragmentSource, uniformNames) {
  const program = gl.createProgram();
  gl.attachShader(program, compile(gl, gl.VERTEX_SHADER, VERTEX_SHADER));
  gl.attachShader(program, compile(gl, gl.FRAGMENT_SHADER, fragmentSource));
  gl.bindAttribLocation(program, 0, 'a_pos');
  gl.linkProgram(program);
  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
    throw new Error(`Programa: ${gl.getProgramInfoLog(program)}`);
  }
  const uniforms = {};
  uniformNames.forEach((name) => { uniforms[name] = gl.getUniformLocation(program, name); });
  return { program, uniforms };
}

function createBackdrop(canvas, gl) {
  const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
  const coarsePointer = window.matchMedia('(pointer: coarse)');

  let field = null;
  let display = null;
  let fieldTexture = null;
  let framebuffer = null;
  let palette = readPalette();
  let rafId = 0;
  let lastFrame = 0;
  let elapsed = 0;
  let renderScale = 1;
  let quality = 1;
  let slowFrames = 0;
  let contextLost = false;
  const size = { fieldW: 1, fieldH: 1, cell: CELL_CSS };
  // Ponteiro em 0..1 com origem embaixo; começa (e fica, no toque) no centro.
  const pointer = { x: 0.5, y: 0.5, tx: 0.5, ty: 0.5 };
  const toggle = document.querySelector('[data-backdrop-toggle]');
  let choice = null;                 // escolha feita no botão nesta página

  // A escolha do botão vence a do sistema; sem escolha, segue prefers-reduced-motion.
  function motionEnabled() {
    let saved = choice;
    if (!saved) {
      try { saved = localStorage.getItem(MOTION_STORAGE_KEY); } catch (_) {}
    }
    if (saved === 'on') return true;
    if (saved === 'off') return false;
    return !reducedMotion.matches;
  }

  function syncToggle() {
    if (!toggle) return;
    const on = motionEnabled();
    toggle.setAttribute('aria-pressed', String(on));
    toggle.title = on
      ? 'Animação do fundo: ligada (clique para pausar)'
      : 'Animação do fundo: pausada (clique para animar)';
    const iconEl = toggle.querySelector('.theme-icon');
    if (iconEl) iconEl.innerHTML = icon(on ? 'pause' : 'play');
  }

  function onToggleClick() {
    choice = motionEnabled() ? 'off' : 'on';
    try { localStorage.setItem(MOTION_STORAGE_KEY, choice); } catch (_) {}
    update();
  }

  function setup() {
    field = createProgram(gl, FIELD_SHADER, ['u_res', 'u_time', 'u_mouse']);
    display = createProgram(gl, DISPLAY_SHADER, [
      'u_field', 'u_res', 'u_cell', 'u_column', 'u_calm', 'u_mix', 'u_base', 'u_colorA', 'u_colorB', 'u_line',
    ]);
    const buffer = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
    // Um triângulo que cobre a tela inteira.
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 3, -1, -1, 3]), gl.STATIC_DRAW);
    gl.enableVertexAttribArray(0);
    gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0);

    fieldTexture = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_2D, fieldTexture);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    framebuffer = gl.createFramebuffer();
  }

  function resize() {
    const cssW = window.innerWidth;
    const cssH = window.innerHeight;
    const maxRatio = coarsePointer.matches ? 1 : MAX_PIXEL_RATIO;
    renderScale = Math.max(0.5, Math.min(window.devicePixelRatio || 1, maxRatio) * quality);
    canvas.width = Math.max(1, Math.round(cssW * renderScale));
    canvas.height = Math.max(1, Math.round(cssH * renderScale));
    // Célula com tamanho inteiro em px de render: barras nítidas.
    size.cell = Math.max(4, Math.round(CELL_CSS * renderScale));
    size.fieldW = Math.max(1, Math.round(cssW * FIELD_SCALE * quality));
    size.fieldH = Math.max(1, Math.round(cssH * FIELD_SCALE * quality));

    gl.bindTexture(gl.TEXTURE_2D, fieldTexture);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, size.fieldW, size.fieldH, 0, gl.RGBA, gl.UNSIGNED_BYTE, null);
    gl.bindFramebuffer(gl.FRAMEBUFFER, framebuffer);
    gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, fieldTexture, 0);
    const complete = gl.checkFramebufferStatus(gl.FRAMEBUFFER) === gl.FRAMEBUFFER_COMPLETE;
    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
    if (!complete) throw new Error('Framebuffer incompleto');
  }

  function render() {
    if (contextLost || !field) return;
    const t = elapsed * 60;

    // 1. Cena procedural, na textura do campo.
    gl.bindFramebuffer(gl.FRAMEBUFFER, framebuffer);
    gl.viewport(0, 0, size.fieldW, size.fieldH);
    gl.useProgram(field.program);
    const fu = field.uniforms;
    gl.uniform2f(fu.u_res, size.fieldW, size.fieldH);
    gl.uniform3f(fu.u_time, t * SPEED.noise, t * SPEED.flow, t * SPEED.liquify);
    gl.uniform2f(fu.u_mouse, pointer.x, pointer.y);
    gl.drawArrays(gl.TRIANGLES, 0, 3);

    // 2. Exibição na tela.
    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
    gl.viewport(0, 0, canvas.width, canvas.height);
    gl.useProgram(display.program);
    const du = display.uniforms;
    gl.activeTexture(gl.TEXTURE0);
    gl.bindTexture(gl.TEXTURE_2D, fieldTexture);
    gl.uniform1i(du.u_field, 0);
    gl.uniform2f(du.u_res, canvas.width, canvas.height);
    gl.uniform1f(du.u_cell, size.cell);
    gl.uniform2f(du.u_column, canvas.width / 2, COLUMN_HALF_CSS * renderScale);
    gl.uniform2f(du.u_calm, palette.calm, palette.calmB);
    gl.uniform1f(du.u_mix, palette.mix);
    gl.uniform3fv(du.u_base, palette.base);
    gl.uniform3fv(du.u_colorA, palette.a);
    gl.uniform3fv(du.u_colorB, palette.b);
    gl.uniform3fv(du.u_line, palette.line);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
  }

  function ease(dt) {
    // Momentum alto, como no original: o bulge segue o ponteiro devagar.
    const follow = 1 - Math.exp(-dt * 1.5);
    pointer.x += (pointer.tx - pointer.x) * follow;
    pointer.y += (pointer.ty - pointer.y) * follow;
  }

  function adaptQuality(frameMs) {
    slowFrames = frameMs > 50 ? slowFrames + 1 : Math.max(0, slowFrames - 1);
    if (slowFrames > 20 && quality > 0.6) {
      quality = Math.max(0.5, quality - 0.25);
      slowFrames = 0;
      resize();
    }
  }

  function frame(now) {
    rafId = requestAnimationFrame(frame);
    if (lastFrame && now - lastFrame < 1000 / MAX_FPS - 1) return;
    const dt = lastFrame ? Math.min(0.1, (now - lastFrame) / 1000) : 1 / MAX_FPS;
    if (lastFrame) adaptQuality(now - lastFrame);
    lastFrame = now;
    elapsed += dt;
    ease(dt);
    render();
  }

  function stopLoop() {
    if (rafId) cancelAnimationFrame(rafId);
    rafId = 0;
    lastFrame = 0;
  }

  function update() {
    stopLoop();
    syncToggle();
    if (contextLost) {
      canvas.classList.remove('is-running');
      return;
    }
    palette = readPalette();
    canvas.classList.add('is-running');
    if (!motionEnabled()) {
      // Pausado no botão congela o quadro atual; parado desde o início usa um com boa composição.
      if (!elapsed) elapsed = STILL_FRAME_S;
      render();
    } else if (!document.hidden) {
      rafId = requestAnimationFrame(frame);
    }
  }

  let resizeQueued = false;
  function onResize() {
    if (resizeQueued) return;
    resizeQueued = true;
    requestAnimationFrame(() => {
      resizeQueued = false;
      resize();
      render();
    });
  }

  function onPointerMove(event) {
    if (event.pointerType === 'touch') return;
    pointer.tx = event.clientX / Math.max(1, window.innerWidth);
    pointer.ty = 1 - event.clientY / Math.max(1, window.innerHeight);
  }

  function onContextLost(event) {
    event.preventDefault();
    contextLost = true;
    stopLoop();
    canvas.classList.remove('is-running');
  }

  function onContextRestored() {
    contextLost = false;
    try {
      setup();
      resize();
      update();
    } catch (_) {
      canvas.classList.remove('is-running');
    }
  }

  setup();
  resize();

  // O tema troca as cores (tokens --backdrop-*): relê a paleta e redesenha.
  const themeObserver = new MutationObserver(update);
  themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
  document.addEventListener('visibilitychange', update);
  window.addEventListener('resize', onResize, { passive: true });
  window.addEventListener('pointermove', onPointerMove, { passive: true });
  reducedMotion.addEventListener?.('change', update);
  canvas.addEventListener('webglcontextlost', onContextLost);
  canvas.addEventListener('webglcontextrestored', onContextRestored);
  if (toggle) {
    toggle.hidden = false;
    toggle.addEventListener('click', onToggleClick);
  }

  update();

  return {
    destroy() {
      stopLoop();
      if (toggle) {
        toggle.removeEventListener('click', onToggleClick);
        toggle.hidden = true;
      }
      themeObserver.disconnect();
      document.removeEventListener('visibilitychange', update);
      window.removeEventListener('resize', onResize);
      window.removeEventListener('pointermove', onPointerMove);
      reducedMotion.removeEventListener?.('change', update);
      canvas.remove();
      instance = null;
    },
  };
}

/** Cria o canvas de fundo (uma vez por página) e liga a animação ao tema. */
export function initBackdrop() {
  if (instance) return instance;
  const canvas = document.createElement('canvas');
  canvas.className = 'backdrop';
  canvas.setAttribute('aria-hidden', 'true');
  const gl = canvas.getContext('webgl', {
    alpha: false,
    antialias: false,
    depth: false,
    stencil: false,
    powerPreference: 'low-power',
    preserveDrawingBuffer: false,
  });
  if (!gl) return null;
  try {
    document.body.prepend(canvas);
    instance = createBackdrop(canvas, gl);
  } catch (err) {
    canvas.remove();
    console.warn('Fundo animado desativado:', err);
    return null;
  }
  return instance;
}

initBackdrop();
