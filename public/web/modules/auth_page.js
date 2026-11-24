/**
 * Página de login e cadastro (/login e /register).
 *
 * Fluxo principal: código de 6 dígitos por e-mail. A pessoa digita o e-mail, recebe o código
 * (vale LOGIN_CODE_TTL_MINUTES no servidor, 10 por padrão) e entra. Sem conta com o e-mail, a
 * conta é criada no código certo, então /login e /register usam o mesmo fluxo e só mudam o texto.
 *
 * Também ficam aqui: Entrar com Google, modo convidado e o formulário de usuário e senha, que só
 * aparece em /login?senha=1 para a conta de administrador. O cadastro por senha e as abas
 * Entrar/Cadastrar estão comentados no bloco "DESATIVADO" no fim do arquivo.
 *
 * A sessão fica num cookie HttpOnly definido pelo servidor; nada de token no JavaScript.
 */
import { getLanguage } from './i18n.js?v=13';

// Limpeza de resquícios antigos (versões anteriores guardavam o convidado no localStorage).
// Os simulados do convidado da aba atual (sessionStorage) são mantidos até o login dar certo:
// quem abre esta tela e volta sem entrar não perde o que criou.
localStorage.removeItem('quiz_guest_mode');
localStorage.removeItem('quiz_guest_data');
localStorage.removeItem('quiz_guest_quizzes');

// Ao entrar, só a marca de convidado sai. Os simulados que ele criou ficam na aba
// para a home (app.js) enviá-los à conta recém-aberta e depois limpá-los.
function clearGuestSession() {
  sessionStorage.removeItem('quiz_guest_mode');
}

/**
 * Destino depois de entrar (?next=). Só aceita caminhos internos para não virar
 * um redirecionamento aberto (ex.: ?next=https://site-falso.com ou //site-falso.com).
 */
// Sem ?next=, quem entra vai para os simulados (/app); a raiz é a página inicial.
const DEFAULT_NEXT = '/app';
function safeNext() {
  const raw = new URLSearchParams(window.location.search).get('next') || DEFAULT_NEXT;
  if (!raw.startsWith('/') || raw.startsWith('//') || raw.startsWith('/\\')) return DEFAULT_NEXT;
  try {
    const url = new URL(raw, window.location.origin);
    if (url.origin !== window.location.origin) return DEFAULT_NEXT;
    if (['/login', '/register', '/reset-password'].includes(url.pathname)) return DEFAULT_NEXT;
    return url.pathname + url.search + url.hash;
  } catch (_) {
    return DEFAULT_NEXT;
  }
}

async function readJson(res) {
  try {
    const raw = await res.json();
    return { ...raw, data: raw.data || raw };
  } catch (_) {
    return { data: {} };
  }
}

function showFeedback(el, message, kind = 'error') {
  if (!el) return;
  el.textContent = message;
  el.className = `form-feedback ${kind === 'success' ? 'feedback-success' : 'feedback-error'}`;
  el.hidden = false;
}

function hideFeedback(el) {
  if (!el) return;
  el.hidden = true;
  el.textContent = '';
}

function setBusy(button, busy, busyLabel) {
  if (!button) return;
  const span = button.querySelector('span');
  if (busy) {
    button.dataset.label = span?.textContent || '';
    if (span && busyLabel) span.textContent = busyLabel;
  } else if (span && button.dataset.label) {
    span.textContent = button.dataset.label;
  }
  button.disabled = busy;
  button.classList.toggle('btn-loading', busy);
}

/** Segundos para m:ss (números em DM Mono na tela). */
function formatClock(totalSeconds) {
  const seconds = Math.max(0, Math.ceil(totalSeconds));
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`;
}

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

// ─── Entrar com Google (só aparece se o servidor estiver configurado) ────────
const googleBtn = document.getElementById('btnGoogleLogin');
const googleDivider = document.getElementById('googleDivider');
fetch('/api/auth/providers', { cache: 'no-store' })
  .then((res) => (res.ok ? res.json() : {}))
  .then((raw) => {
    const enabled = Boolean((raw.data || raw).google);
    if (googleBtn) googleBtn.hidden = !enabled;
    if (googleDivider) googleDivider.hidden = !enabled;
  })
  .catch(() => {});
googleBtn?.addEventListener('click', () => {
  window.location.assign(`/api/auth/google/start?next=${encodeURIComponent(safeNext())}`);
});

// Erros devolvidos pelo retorno do Google (?erro=)
const LOGIN_ERRORS = {
  google_indisponivel: 'O login com Google não está disponível agora. Entre com o código por e-mail.',
  google_sessao: 'O login com Google expirou ou foi interrompido. Tente de novo.',
  google_email: 'Use uma conta Google com e-mail verificado.',
  google_falhou: 'O Google não confirmou o login. Tente de novo ou entre com o código por e-mail.',
  google_admin: 'A conta de administrador entra só com usuário e senha.',
  muitas_tentativas: 'Muitas tentativas seguidas. Aguarde alguns minutos.',
};

// ─── Verificação da sessão HttpOnly ──────────────────────────────────────────
fetch('/api/auth/me', { cache: 'no-store', credentials: 'same-origin' })
  .then(res => { if (res.ok) window.location.replace(safeNext()); })
  .catch(() => { });

// ─── Elementos da Interface ──────────────────────────────────────────────────
const headerSubtitle = document.getElementById('headerSubtitle');
const codeEmailForm = document.getElementById('codeEmailForm');
const codeEmailInput = document.getElementById('codeEmail');
const codeEmailFeedback = document.getElementById('codeEmailFeedback');
const btnSendCode = document.getElementById('btnSendCode');
const codeVerifyForm = document.getElementById('codeVerifyForm');
const codeSentEmail = document.getElementById('codeSentEmail');
const codeInputs = document.getElementById('codeInputs');
const digits = Array.from(codeInputs?.querySelectorAll('.code-digit') || []);
const codeTimerLabel = document.getElementById('codeTimerLabel');
const codeCountdown = document.getElementById('codeCountdown');
const codeVerifyFeedback = document.getElementById('codeVerifyFeedback');
const btnVerifyCode = document.getElementById('btnVerifyCode');
const btnResendCode = document.getElementById('btnResendCode');
const codeResendIn = document.getElementById('codeResendIn');
const btnChangeEmail = document.getElementById('btnChangeEmail');
const codeFooterHint = document.getElementById('codeFooterHint');
const loginFooter = codeFooterHint?.closest('.login-footer');
const pageLoginForm = document.getElementById('pageLoginForm');
const loginFeedback = document.getElementById('loginFeedback');
const submitLoginBtn = document.getElementById('btnLoginSubmit');

const passwordMode = new URLSearchParams(window.location.search).has('senha');

// ─── Código por e-mail: estado ───────────────────────────────────────────────
// O pedido pendente fica na aba (sessionStorage): recarregar a página ou voltar do
// aplicativo de e-mail mantém a tela do código, sem pedir outro.
const PENDING_KEY = 'acely_code_pending';
let pending = null;   // { email, expiresAt, resendAt } em milissegundos
let ticker = null;
let verifying = false;

function loadPending() {
  try {
    const saved = JSON.parse(sessionStorage.getItem(PENDING_KEY) || 'null');
    if (saved && typeof saved.email === 'string' && saved.expiresAt > Date.now()) return saved;
  } catch (_) { }
  sessionStorage.removeItem(PENDING_KEY);
  return null;
}

function savePending() {
  if (pending) sessionStorage.setItem(PENDING_KEY, JSON.stringify(pending));
  else sessionStorage.removeItem(PENDING_KEY);
}

function codeValue() {
  return digits.map((input) => input.value).join('');
}

function paintDigits() {
  digits.forEach((input) => input.classList.toggle('is-filled', input.value !== ''));
}

function clearDigits() {
  digits.forEach((input) => { input.value = ''; });
  paintDigits();
}

/** Espalha os números a partir de uma casa (colar, preencher automático do celular). */
function fillDigits(text, start = 0) {
  const numbers = String(text).replace(/\D/g, '').slice(0, digits.length - start);
  numbers.split('').forEach((char, offset) => { digits[start + offset].value = char; });
  paintDigits();
  const next = Math.min(start + numbers.length, digits.length - 1);
  digits[next]?.focus();
  if (codeValue().length === digits.length) submitCode();
}

function tick() {
  if (!pending) return;
  const now = Date.now();
  const left = (pending.expiresAt - now) / 1000;
  if (codeCountdown) codeCountdown.textContent = formatClock(left);
  const expired = left <= 0;
  if (codeTimerLabel) codeTimerLabel.textContent = expired ? 'O código venceu. Peça um novo.' : 'O código vence em';
  if (codeCountdown) codeCountdown.hidden = expired;
  if (btnVerifyCode && !verifying) btnVerifyCode.disabled = expired;

  const wait = (pending.resendAt - now) / 1000;
  if (btnResendCode && !btnResendCode.classList.contains('btn-loading')) btnResendCode.disabled = wait > 0;
  if (codeResendIn) codeResendIn.textContent = wait > 0 ? formatClock(wait) : '';
}

function startTicker() {
  window.clearInterval(ticker);
  tick();
  ticker = window.setInterval(tick, 1000);
}

function showEmailStep() {
  window.clearInterval(ticker);
  if (codeVerifyForm) codeVerifyForm.hidden = true;
  if (pageLoginForm) pageLoginForm.hidden = true;
  if (codeEmailForm) codeEmailForm.hidden = false;
  if (loginFooter) loginFooter.hidden = false;
  hideFeedback(codeVerifyFeedback);
  codeEmailInput?.focus();
}

function showCodeStep() {
  if (!pending) return;
  if (codeEmailForm) codeEmailForm.hidden = true;
  if (pageLoginForm) pageLoginForm.hidden = true;
  if (codeVerifyForm) codeVerifyForm.hidden = false;
  if (loginFooter) loginFooter.hidden = true;
  if (codeSentEmail) codeSentEmail.textContent = pending.email;
  codeInputs?.classList.remove('is-error');
  clearDigits();
  startTicker();
  digits[0]?.focus();
}

/** Pede um código ao servidor. Devolve true se saiu. */
async function requestCode(email, { feedback, button, busyLabel }) {
  hideFeedback(feedback);
  setBusy(button, true, busyLabel);
  try {
    const res = await fetch('/api/auth/email-code', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'same-origin',
      body: JSON.stringify({ email, language: getLanguage() }),
    });
    const raw = await readJson(res);
    if (!res.ok) {
      // 429 do reenvio traz quantos segundos faltam: a contagem do botão passa a valer
      if (res.status === 429 && raw.retry_after && pending && pending.email === email) {
        pending.resendAt = Date.now() + raw.retry_after * 1000;
        savePending();
        tick();
      }
      showFeedback(feedback, raw.message || 'Não foi possível enviar o código. Tente novamente.');
      return false;
    }
    const data = raw.data;
    const now = Date.now();
    pending = {
      email,
      expiresAt: now + (Number(data.expires_in) || 600) * 1000,
      resendAt: now + (Number(data.resend_in) || 60) * 1000,
    };
    savePending();
    showCodeStep();
    if (data.dev_code) {
      // Só em desenvolvimento sem SMTP (o servidor não manda isso em produção)
      showFeedback(codeVerifyFeedback, `Modo de desenvolvimento: o código é ${data.dev_code}`, 'success');
    }
    return true;
  } catch (_) {
    showFeedback(feedback, 'Não foi possível conectar ao servidor. Verifique a conexão.');
    return false;
  } finally {
    setBusy(button, false);
  }
}

async function submitCode() {
  if (!pending || verifying) return;
  const code = codeValue();
  hideFeedback(codeVerifyFeedback);
  codeInputs?.classList.remove('is-error');
  if (code.length !== digits.length) {
    showFeedback(codeVerifyFeedback, 'Digite os 6 números do código.');
    digits[code.length]?.focus();
    return;
  }

  verifying = true;
  setBusy(btnVerifyCode, true, 'Conferindo o código…');
  try {
    const res = await fetch('/api/auth/email-code/verify', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'same-origin',
      body: JSON.stringify({ email: pending.email, code }),
    });
    const raw = await readJson(res);
    if (!res.ok) {
      showFeedback(codeVerifyFeedback, raw.message || 'Código incorreto. Confira o e-mail e tente de novo.');
      // Sem animação de tremor para quem pede menos movimento: a cor da borda basta
      codeInputs?.classList.remove('is-error');
      void codeInputs?.offsetWidth;
      codeInputs?.classList.add('is-error');
      clearDigits();
      digits[0]?.focus();
      return;
    }

    window.clearInterval(ticker);
    pending = null;
    savePending();
    clearGuestSession();
    showFeedback(
      codeVerifyFeedback,
      raw.data.created ? 'Conta criada. Abrindo seus simulados…' : 'Acesso liberado. Abrindo seus simulados…',
      'success',
    );
    setTimeout(() => window.location.replace(safeNext()), 500);
  } catch (_) {
    showFeedback(codeVerifyFeedback, 'Não foi possível conectar ao servidor. Verifique a conexão.');
  } finally {
    verifying = false;
    setBusy(btnVerifyCode, false);
    tick();
  }
}

// ─── Código por e-mail: eventos ──────────────────────────────────────────────
codeEmailForm?.addEventListener('submit', (e) => {
  e.preventDefault();
  const email = (codeEmailInput?.value || '').trim().toLowerCase();
  if (!EMAIL_PATTERN.test(email)) {
    showFeedback(codeEmailFeedback, 'Informe um e-mail válido, como nome@exemplo.com.');
    codeEmailInput?.focus();
    return;
  }
  requestCode(email, { feedback: codeEmailFeedback, button: btnSendCode, busyLabel: 'Enviando código…' });
});

codeVerifyForm?.addEventListener('submit', (e) => {
  e.preventDefault();
  submitCode();
});

btnResendCode?.addEventListener('click', () => {
  if (!pending) return;
  requestCode(pending.email, { feedback: codeVerifyFeedback, button: btnResendCode }).then((sent) => {
    if (sent) showFeedback(codeVerifyFeedback, 'Enviamos um novo código. O anterior deixou de valer.', 'success');
  });
});

btnChangeEmail?.addEventListener('click', () => {
  if (codeEmailInput && pending) codeEmailInput.value = pending.email;
  pending = null;
  savePending();
  showEmailStep();
});

digits.forEach((input, index) => {
  input.addEventListener('input', () => {
    const numbers = input.value.replace(/\D/g, '');
    if (numbers.length > 1) {
      // Preenchimento automático (one-time-code) ou digitação rápida: espalha pelas casas
      input.value = '';
      fillDigits(numbers, index);
      return;
    }
    input.value = numbers;
    paintDigits();
    codeInputs?.classList.remove('is-error');
    if (numbers && index < digits.length - 1) digits[index + 1].focus();
    if (codeValue().length === digits.length) submitCode();
  });

  input.addEventListener('keydown', (e) => {
    if (e.key === 'Backspace' && !input.value && index > 0) {
      e.preventDefault();
      digits[index - 1].value = '';
      paintDigits();
      digits[index - 1].focus();
    } else if (e.key === 'ArrowLeft' && index > 0) {
      e.preventDefault();
      digits[index - 1].focus();
    } else if (e.key === 'ArrowRight' && index < digits.length - 1) {
      e.preventDefault();
      digits[index + 1].focus();
    }
  });

  input.addEventListener('paste', (e) => {
    const text = e.clipboardData?.getData('text') || '';
    if (!/\d/.test(text)) return;
    e.preventDefault();
    clearDigits();
    fillDigits(text, 0);
  });

  input.addEventListener('focus', () => input.select());
});

// ─── Acesso com usuário e senha (só o administrador, em /login?senha=1) ──────
pageLoginForm?.addEventListener('submit', async (e) => {
  e.preventDefault();
  hideFeedback(loginFeedback);

  const username = document.getElementById('loginUsername')?.value.trim();
  const password = document.getElementById('loginPassword')?.value;

  if (!username || !password) {
    showFeedback(loginFeedback, 'Por favor, preencha o usuário e a senha.');
    return;
  }

  setBusy(submitLoginBtn, true, 'Validando credenciais…');
  try {
    const response = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'same-origin',
      body: JSON.stringify({ username, password })
    });
    const raw = await readJson(response);
    if (!response.ok) {
      showFeedback(loginFeedback, raw.message || raw.error || 'Usuário ou senha incorretos.');
      return;
    }
    clearGuestSession();
    showFeedback(loginFeedback, 'Acesso liberado. Abrindo seus simulados…', 'success');
    setTimeout(() => window.location.replace(safeNext()), 500);
  } catch (_) {
    showFeedback(loginFeedback, 'Não foi possível conectar ao servidor. Verifique a conexão.');
  } finally {
    setBusy(submitLoginBtn, false);
  }
});

// Acesso como convidado: o servidor cria a sessão (cookie HttpOnly) e a cota de IA
const btnGuestAccess = document.getElementById('btnGuestAccess');
btnGuestAccess?.addEventListener('click', async () => {
  btnGuestAccess.disabled = true;
  try {
    const res = await fetch('/api/guest/start', { method: 'POST', credentials: 'same-origin' });
    if (!res.ok) {
      const raw = await res.json().catch(() => ({}));
      if (res.status === 409) {
        window.location.replace(safeNext());
        return;
      }
      throw new Error(raw.message || 'Não foi possível abrir o modo convidado.');
    }
    sessionStorage.setItem('quiz_guest_mode', 'true');
    window.location.replace(safeNext());
  } catch (err) {
    const visible = [codeEmailFeedback, codeVerifyFeedback, loginFeedback]
      .find((el) => el && !el.closest('form')?.hidden);
    showFeedback(visible || codeEmailFeedback, `${err.message} Tente novamente em alguns minutos.`);
    btnGuestAccess.disabled = false;
  }
});

// ─── Inicialização ───────────────────────────────────────────────────────────
if (passwordMode) {
  if (codeEmailForm) codeEmailForm.hidden = true;
  if (codeVerifyForm) codeVerifyForm.hidden = true;
  if (loginFooter) loginFooter.hidden = true;
  if (pageLoginForm) pageLoginForm.hidden = false;
  if (headerSubtitle) headerSubtitle.textContent = 'Acesso com usuário e senha, usado pela conta de administrador.';
  document.getElementById('loginUsername')?.focus();
} else {
  pending = loadPending();
  if (pending) {
    if (codeEmailInput) codeEmailInput.value = pending.email;
    showCodeStep();
  }
}

const loginError = LOGIN_ERRORS[new URLSearchParams(window.location.search).get('erro')];
if (loginError) {
  showFeedback(passwordMode ? loginFeedback : (pending ? codeVerifyFeedback : codeEmailFeedback), loginError);
}

/* ═══ DESATIVADO: abas Entrar/Cadastrar e cadastro com usuário e senha ═══════════
   Substituídos pelo código por e-mail, que entra e cria a conta no mesmo fluxo.
   Para reativar: descomente este bloco, o bloco "DESATIVADO" de login.html e register.html,
   e troque os textos de cabeçalho de volta (o setMode abaixo cuida das duas telas).

const pageTitle = document.getElementById('pageTitle');
const headerEyebrow = document.getElementById('headerEyebrow');
const headerTitle = document.getElementById('headerTitle');
const tabLogin = document.getElementById('tabLogin');
const tabRegister = document.getElementById('tabRegister');
const pageRegisterForm = document.getElementById('pageRegisterForm');
const footerHint = document.getElementById('footerHint');
const registerFeedback = document.getElementById('registerFeedback');
const submitRegisterBtn = document.getElementById('btnRegisterSubmit');

export function setMode(mode, pushState = true) {
  if (loginFeedback) {
    loginFeedback.hidden = true;
    loginFeedback.textContent = '';
  }
  if (registerFeedback) {
    registerFeedback.hidden = true;
    registerFeedback.textContent = '';
  }

  if (mode === 'register') {
    if (pageTitle) pageTitle.textContent = 'Cadastrar — Acely';
    if (headerEyebrow) headerEyebrow.textContent = 'Acely · crie sua conta';
    if (headerTitle) headerTitle.innerHTML = 'Crie sua<br><em>conta grátis</em>';
    if (headerSubtitle) headerSubtitle.textContent = 'Seus simulados e seu histórico ficam salvos e acessíveis em qualquer dispositivo. Sem cartão de crédito.';
    tabRegister?.classList.add('active');
    tabRegister?.setAttribute('aria-current', 'page');
    tabLogin?.classList.remove('active');
    tabLogin?.removeAttribute('aria-current');
    if (pageLoginForm) pageLoginForm.hidden = true;
    if (pageRegisterForm) pageRegisterForm.hidden = false;
    if (footerHint) footerHint.innerHTML = 'Já possui uma conta? <a href="/login" id="linkToggle" class="auth-link">Entre aqui</a>';
    if (pushState && window.location.pathname !== '/register') {
      history.pushState({ mode: 'register' }, '', '/register' + window.location.search);
    }
    document.getElementById('regUsername')?.focus();
  } else {
    if (pageTitle) pageTitle.textContent = 'Entrar — Acely';
    if (headerEyebrow) headerEyebrow.textContent = 'Acely · acesso à plataforma';
    if (headerTitle) headerTitle.innerHTML = 'Boas-vindas ao<br><em>Acely</em>';
    if (headerSubtitle) headerSubtitle.textContent = 'Entre para salvar seus simulados e acompanhar seu desempenho.';
    tabLogin?.classList.add('active');
    tabLogin?.setAttribute('aria-current', 'page');
    tabRegister?.classList.remove('active');
    tabRegister?.removeAttribute('aria-current');
    if (pageRegisterForm) pageRegisterForm.hidden = true;
    if (pageLoginForm) pageLoginForm.hidden = false;
    if (footerHint) footerHint.innerHTML = 'Não possui uma conta? <a href="/register" id="linkToggle" class="auth-link">Cadastre-se aqui</a>';
    if (pushState && window.location.pathname !== '/login') {
      history.pushState({ mode: 'login' }, '', '/login' + window.location.search);
    }
    document.getElementById('loginUsername')?.focus();
  }
}

// Navegação pelas abas sem recarregar a página (0ms de atraso, sem reload)
tabLogin?.addEventListener('click', (e) => {
  e.preventDefault();
  setMode('login');
});

tabRegister?.addEventListener('click', (e) => {
  e.preventDefault();
  setMode('register');
});

// Delegação de evento no rodapé para alternar modo
footerHint?.addEventListener('click', (e) => {
  const link = e.target.closest('a');
  if (link) {
    e.preventDefault();
    const currentMode = pageRegisterForm?.hidden ? 'login' : 'register';
    setMode(currentMode === 'login' ? 'register' : 'login');
  }
});

// Suporte aos botões voltar/avançar do navegador
window.addEventListener('popstate', () => {
  const isRegister = window.location.pathname === '/register';
  setMode(isRegister ? 'register' : 'login', false);
});

// ─── Submissão do Formulário de Cadastro ──────────────────────────────────────
pageRegisterForm?.addEventListener('submit', async (e) => {
  e.preventDefault();
  if (registerFeedback) {
    registerFeedback.hidden = true;
    registerFeedback.textContent = '';
  }

  const username = document.getElementById('regUsername')?.value.trim();
  const email = document.getElementById('regEmail')?.value.trim();
  const password = document.getElementById('regPassword')?.value;

  if (!username || !email || !password) {
    if (registerFeedback) {
      registerFeedback.textContent = 'Por favor, preencha todos os campos.';
      registerFeedback.className = 'form-feedback feedback-error';
      registerFeedback.hidden = false;
    }
    return;
  }

  // Mesma regra do servidor (auth_service): 3 a 30 caracteres, letras, números, . _ -
  if (!/^[A-Za-z0-9_.-]{3,30}$/.test(username)) {
    if (registerFeedback) {
      registerFeedback.textContent = 'O nome de usuário deve ter de 3 a 30 caracteres: letras, números, ponto, hífen ou sublinhado.';
      registerFeedback.className = 'form-feedback feedback-error';
      registerFeedback.hidden = false;
    }
    return;
  }

  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    if (registerFeedback) {
      registerFeedback.textContent = 'Informe um e-mail válido, como nome@exemplo.com.';
      registerFeedback.className = 'form-feedback feedback-error';
      registerFeedback.hidden = false;
    }
    return;
  }

  // Mesmo mínimo exigido pelo servidor (auth_service): 8 caracteres
  if (password.length < 8) {
    if (registerFeedback) {
      registerFeedback.textContent = 'A senha deve ter no mínimo 8 caracteres.';
      registerFeedback.className = 'form-feedback feedback-error';
      registerFeedback.hidden = false;
    }
    return;
  }

  if (submitRegisterBtn) {
    submitRegisterBtn.disabled = true;
    submitRegisterBtn.classList.add('btn-loading');
    const span = submitRegisterBtn.querySelector('span');
    if (span) span.textContent = 'Criando cadastro…';
  }

  try {
    const response = await fetch('/api/auth/register', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, email, password })
    });

    const rawData = await response.json();
    const data = rawData.data || rawData;

    if (!response.ok) {
      if (registerFeedback) {
        registerFeedback.textContent = data.message || data.error || 'Erro ao criar conta.';
        registerFeedback.className = 'form-feedback feedback-error';
        registerFeedback.hidden = false;
      }
      return;
    }

    if (registerFeedback) {
      registerFeedback.textContent = 'Conta criada. Enviamos um link para confirmar seu e-mail. Conectando…';
      registerFeedback.className = 'form-feedback feedback-success';
      registerFeedback.hidden = false;
    }

    try {
      const loginRes = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        body: JSON.stringify({ username, password })
      });

      if (loginRes.ok) {
        clearGuestSession();
        setTimeout(() => {
          window.location.replace(safeNext());
        }, 500);
        return;
      }
    } catch (_) { }

    setMode('login');
    if (loginFeedback) {
      loginFeedback.textContent = 'Conta criada. Entre com seu usuário e senha para continuar.';
      loginFeedback.className = 'form-feedback feedback-success';
      loginFeedback.hidden = false;
    }

  } catch (err) {
    if (registerFeedback) {
      registerFeedback.textContent = 'Não foi possível conectar ao servidor. Verifique a conexão.';
      registerFeedback.className = 'form-feedback feedback-error';
      registerFeedback.hidden = false;
    }
  } finally {
    if (submitRegisterBtn) {
      submitRegisterBtn.disabled = false;
      submitRegisterBtn.classList.remove('btn-loading');
      const span = submitRegisterBtn.querySelector('span');
      if (span) span.textContent = 'Criar conta grátis';
    }
  }
});

// Inicialização de acordo com a rota atual
if (window.location.pathname === '/register') {
  setMode('register', false);
} else {
  setMode('login', false);
}
═══ fim do bloco DESATIVADO ═══ */
