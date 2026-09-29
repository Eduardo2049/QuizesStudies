/**
 * Módulo de Autenticação e Navegação SPA (Login e Cadastro)
 * Gerencia a alternância instantânea entre as abas sem recarregamento da página,
 * validação de formulários com feedback acessível e controle de sessão HttpOnly.
 */

// Limpeza proativa de qualquer resquício de cache ou usuário anterior ao abrir a tela de autenticação
localStorage.removeItem('quiz_guest_mode');
localStorage.removeItem('quiz_guest_data');
localStorage.removeItem('quiz_guest_quizzes');
sessionStorage.clear();

// ─── Verificação da sessão HttpOnly ──────────────────────────────────────────
fetch('/api/auth/me', { cache: 'no-store', credentials: 'same-origin' })
  .then(res => { if (res.ok) window.location.replace('/'); })
  .catch(() => {});

// ─── Elementos da Interface ──────────────────────────────────────────────────
const pageTitle = document.getElementById('pageTitle');
const headerEyebrow = document.getElementById('headerEyebrow');
const headerTitle = document.getElementById('headerTitle');
const headerSubtitle = document.getElementById('headerSubtitle');
const tabLogin = document.getElementById('tabLogin');
const tabRegister = document.getElementById('tabRegister');
const pageLoginForm = document.getElementById('pageLoginForm');
const pageRegisterForm = document.getElementById('pageRegisterForm');
const footerHint = document.getElementById('footerHint');
const loginFeedback = document.getElementById('loginFeedback');
const submitLoginBtn = document.getElementById('btnLoginSubmit');
const registerFeedback = document.getElementById('registerFeedback');
const submitRegisterBtn = document.getElementById('btnRegisterSubmit');

/**
 * Alterna entre a visualização de Login e de Cadastro
 * @param {'login'|'register'} mode
 * @param {boolean} pushState
 */
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
    if (pageTitle) pageTitle.textContent = 'Cadastrar — Quiz Study';
    if (headerEyebrow) headerEyebrow.textContent = 'Quiz Study · crie sua conta';
    if (headerTitle) headerTitle.innerHTML = 'Cadastro de<br><em>Estudante</em>';
    if (headerSubtitle) headerSubtitle.textContent = 'Crie seu perfil gratuitamente para responder simulados e acompanhar seu progresso.';
    tabRegister?.classList.add('active');
    tabRegister?.setAttribute('aria-current', 'page');
    tabLogin?.classList.remove('active');
    tabLogin?.removeAttribute('aria-current');
    if (pageLoginForm) pageLoginForm.hidden = true;
    if (pageRegisterForm) pageRegisterForm.hidden = false;
    if (footerHint) footerHint.innerHTML = 'Já possui uma conta? <a href="/login" id="linkToggle" class="auth-link">Entre aqui</a>';
    if (pushState && window.location.pathname !== '/register') {
      history.pushState({ mode: 'register' }, '', '/register');
    }
    document.getElementById('regUsername')?.focus();
  } else {
    if (pageTitle) pageTitle.textContent = 'Entrar — Quiz Study';
    if (headerEyebrow) headerEyebrow.textContent = 'Quiz Study · acesso à plataforma';
    if (headerTitle) headerTitle.innerHTML = 'Boas-vindas ao<br><em>Quiz Study</em>';
    if (headerSubtitle) headerSubtitle.textContent = 'Entre com sua conta para acessar os simulados e acompanhar seu desempenho.';
    tabLogin?.classList.add('active');
    tabLogin?.setAttribute('aria-current', 'page');
    tabRegister?.classList.remove('active');
    tabRegister?.removeAttribute('aria-current');
    if (pageRegisterForm) pageRegisterForm.hidden = true;
    if (pageLoginForm) pageLoginForm.hidden = false;
    if (footerHint) footerHint.innerHTML = 'Não possui uma conta? <a href="/register" id="linkToggle" class="auth-link">Cadastre-se aqui</a>';
    if (pushState && window.location.pathname !== '/login') {
      history.pushState({ mode: 'login' }, '', '/login');
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

// Acesso como Visitante
document.getElementById('btnGuestAccess')?.addEventListener('click', () => {
  localStorage.removeItem('quiz_guest_mode');
  localStorage.removeItem('quiz_guest_data');
  localStorage.removeItem('quiz_guest_quizzes');
  sessionStorage.setItem('quiz_guest_mode', 'true');
  window.location.replace('/guest');
});

// ─── Submissão do Formulário de Login ─────────────────────────────────────────
pageLoginForm?.addEventListener('submit', async (e) => {
  e.preventDefault();
  localStorage.removeItem('quiz_guest_mode');
  localStorage.removeItem('quiz_guest_data');
  localStorage.removeItem('quiz_guest_quizzes');
  sessionStorage.clear();
  if (loginFeedback) {
    loginFeedback.hidden = true;
    loginFeedback.textContent = '';
  }

  const username = document.getElementById('loginUsername')?.value.trim();
  const password = document.getElementById('loginPassword')?.value;

  if (!username || !password) {
    if (loginFeedback) {
      loginFeedback.textContent = 'Por favor, preencha o usuário e a senha.';
      loginFeedback.className = 'form-feedback feedback-error';
      loginFeedback.hidden = false;
    }
    return;
  }

  if (submitLoginBtn) {
    submitLoginBtn.disabled = true;
    submitLoginBtn.classList.add('btn-loading');
    const span = submitLoginBtn.querySelector('span');
    if (span) span.textContent = 'Validando credenciais…';
  }

  try {
    const response = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'same-origin',
      body: JSON.stringify({ username, password })
    });

    const rawData = await response.json();
    const data = rawData.data || rawData;

    if (!response.ok) {
      if (loginFeedback) {
        loginFeedback.textContent = data.message || data.error || 'Usuário ou senha incorretos.';
        loginFeedback.className = 'form-feedback feedback-error';
        loginFeedback.hidden = false;
      }
      return;
    }

    if (loginFeedback) {
      loginFeedback.textContent = '✓ Acesso liberado! Redirecionando…';
      loginFeedback.className = 'form-feedback feedback-success';
      loginFeedback.hidden = false;
    }

    setTimeout(() => {
      window.location.replace('/');
    }, 500);

  } catch (err) {
    if (loginFeedback) {
      loginFeedback.textContent = 'Não foi possível conectar ao servidor. Verifique a conexão.';
      loginFeedback.className = 'form-feedback feedback-error';
      loginFeedback.hidden = false;
    }
  } finally {
    if (submitLoginBtn) {
      submitLoginBtn.disabled = false;
      submitLoginBtn.classList.remove('btn-loading');
      const span = submitLoginBtn.querySelector('span');
      if (span) span.textContent = 'Acessar Simulados';
    }
  }
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

  if (password.length < 6) {
    if (registerFeedback) {
      registerFeedback.textContent = 'A senha deve ter no mínimo 6 caracteres.';
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
      registerFeedback.textContent = '✓ Conta criada! Conectando…';
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
        setTimeout(() => {
          window.location.replace('/');
        }, 500);
        return;
      }
    } catch (_) {}

    setMode('login');
    if (loginFeedback) {
      loginFeedback.textContent = '✓ Conta criada com sucesso! Faça login para continuar.';
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
      if (span) span.textContent = 'Criar Conta';
    }
  }
});

// Inicialização de acordo com a rota atual
if (window.location.pathname === '/register') {
  setMode('register', false);
} else {
  setMode('login', false);
}
