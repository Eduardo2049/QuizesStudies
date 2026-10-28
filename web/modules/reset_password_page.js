/**
 * Módulo de Recuperação de Senha (SPA)
 * Suporta solicitação de e-mail e redefinição com token em duas etapas fluidas.
 */

const pageTitle = document.getElementById('pageTitle');
const headerTitle = document.getElementById('headerTitle');
const headerSubtitle = document.getElementById('headerSubtitle');

const requestResetForm = document.getElementById('requestResetForm');
const resetIdentifier = document.getElementById('resetIdentifier');
const requestFeedback = document.getElementById('requestFeedback');
const btnRequestReset = document.getElementById('btnRequestReset');

const devHelperBox = document.getElementById('devHelperBox');
const devTokenBox = document.getElementById('devTokenBox');
const btnProceedDirectly = document.getElementById('btnProceedDirectly');

const confirmResetForm = document.getElementById('confirmResetForm');
const resetTokenInput = document.getElementById('resetToken');
const userIdentityBadge = document.getElementById('userIdentityBadge');
const identifiedUser = document.getElementById('identifiedUser');
const newPasswordInput = document.getElementById('newPassword');
const confirmPasswordInput = document.getElementById('confirmPassword');
const ruleLength = document.getElementById('ruleLength');
const ruleMatch = document.getElementById('ruleMatch');
const confirmFeedback = document.getElementById('confirmFeedback');
const btnConfirmReset = document.getElementById('btnConfirmReset');

let activeToken = '';

/**
 * Exibe feedback com classes de estilo e acessibilidade
 */
function showFeedback(element, text, type = 'error') {
  if (!element) return;
  element.hidden = false;
  element.textContent = text;
  element.className = `form-feedback feedback-${type}`;
}

/**
 * Oculta feedback
 */
function clearFeedback(element) {
  if (!element) return;
  element.hidden = true;
  element.textContent = '';
}

/**
 * Alterna visualmente para a Etapa 2 (Definição de Nova Senha)
 */
export async function switchToStep2(token) {
  activeToken = token;
  if (resetTokenInput) resetTokenInput.value = token;

  if (requestResetForm) requestResetForm.hidden = true;
  if (confirmResetForm) confirmResetForm.hidden = false;

  if (headerTitle) headerTitle.innerHTML = 'Nova<br><em>Senha</em>';
  if (headerSubtitle) headerSubtitle.textContent = 'Escolha uma nova senha forte para acessar seus simulados.';
  if (pageTitle) pageTitle.textContent = 'Definir Nova Senha — Quiz Study';

  clearFeedback(confirmFeedback);

  // Valida o token previamente via API para confirmar autenticidade
  try {
    const res = await fetch(`/api/auth/verify-reset-token?token=${encodeURIComponent(token)}`);
    const json = await res.json();

    if (!res.ok) {
      const errMsg = json.error || json.message || 'Link de recuperação expirado ou inválido.';
      showFeedback(confirmFeedback, errMsg, 'error');
      if (btnConfirmReset) btnConfirmReset.disabled = true;
      return;
    }

    const data = json.data || {};
    if (userIdentityBadge && identifiedUser) {
      identifiedUser.textContent = data.masked_email || data.username || 'usuário';
      userIdentityBadge.hidden = false;
    }
    newPasswordInput?.focus();
  } catch (err) {
    showFeedback(confirmFeedback, 'Não foi possível validar o link. Verifique sua conexão.', 'error');
  }
}

// ─── Validação em tempo real dos requisitos de senha ─────────────────────────
function updatePasswordRules() {
  const pwd = newPasswordInput?.value || '';
  const confirm = confirmPasswordInput?.value || '';

  if (ruleLength) {
    if (pwd.length >= 8) {
      ruleLength.style.color = 'var(--success, #50fa7b)';
      ruleLength.textContent = '✓ Mínimo de 8 caracteres';
    } else {
      ruleLength.style.color = 'var(--muted)';
      ruleLength.textContent = '• Mínimo de 8 caracteres';
    }
  }

  if (ruleMatch) {
    if (confirm && pwd === confirm) {
      ruleMatch.style.color = 'var(--success, #50fa7b)';
      ruleMatch.textContent = '✓ As senhas coincidem';
    } else if (confirm) {
      ruleMatch.style.color = 'var(--error, #ff5555)';
      ruleMatch.textContent = '✕ As senhas não coincidem';
    } else {
      ruleMatch.style.color = 'var(--muted)';
      ruleMatch.textContent = '• Ambas as senhas devem coincidir';
    }
  }
}

newPasswordInput?.addEventListener('input', updatePasswordRules);
confirmPasswordInput?.addEventListener('input', updatePasswordRules);

// ─── Submissão da Etapa 1: Solicitar link ─────────────────────────────────────
requestResetForm?.addEventListener('submit', async (e) => {
  e.preventDefault();
  clearFeedback(requestFeedback);
  if (devHelperBox) devHelperBox.hidden = true;

  const identifier = resetIdentifier?.value.trim();
  if (!identifier) {
    showFeedback(requestFeedback, 'Por favor, informe seu e-mail ou nome de usuário.', 'error');
    resetIdentifier?.focus();
    return;
  }

  if (btnRequestReset) {
    btnRequestReset.disabled = true;
    btnRequestReset.classList.add('btn-loading');
    const span = btnRequestReset.querySelector('span');
    if (span) span.textContent = 'Verificando…';
  }

  try {
    const res = await fetch('/api/auth/forgot-password', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: identifier })
    });

    const json = await res.json();
    const data = json.data || {};

    if (!res.ok) {
      showFeedback(requestFeedback, json.error || json.message || 'Erro ao processar solicitação.', 'error');
      return;
    }

    showFeedback(
      requestFeedback,
      json.message || 'Se os dados informados estiverem cadastrados, você receberá o link para redefinir sua senha.',
      'success'
    );

    // Modo desenvolvimento ou simulado: exibe token diretamente para teste instantâneo
    if (data.dev_token) {
      if (devHelperBox && devTokenBox) {
        devTokenBox.textContent = data.dev_reset_url || data.dev_token;
        devHelperBox.hidden = false;

        btnProceedDirectly?.addEventListener('click', () => {
          switchToStep2(data.dev_token);
        }, { once: true });
      }
    }

  } catch (err) {
    showFeedback(requestFeedback, 'Não foi possível conectar ao servidor. Verifique sua conexão.', 'error');
  } finally {
    if (btnRequestReset) {
      btnRequestReset.disabled = false;
      btnRequestReset.classList.remove('btn-loading');
      const span = btnRequestReset.querySelector('span');
      if (span) span.textContent = 'Enviar Link de Recuperação';
    }
  }
});

// ─── Submissão da Etapa 2: Redefinir senha ────────────────────────────────────
confirmResetForm?.addEventListener('submit', async (e) => {
  e.preventDefault();
  clearFeedback(confirmFeedback);

  const token = resetTokenInput?.value.trim() || activeToken;
  const newPassword = newPasswordInput?.value || '';
  const confirmPassword = confirmPasswordInput?.value || '';

  if (!token) {
    showFeedback(confirmFeedback, 'Token de recuperação não identificado. Solicite um novo link.', 'error');
    return;
  }

  if (newPassword.length < 8) {
    showFeedback(confirmFeedback, 'A senha deve conter no mínimo 8 caracteres.', 'error');
    newPasswordInput?.focus();
    return;
  }

  if (newPassword !== confirmPassword) {
    showFeedback(confirmFeedback, 'As senhas digitadas não coincidem.', 'error');
    confirmPasswordInput?.focus();
    return;
  }

  if (btnConfirmReset) {
    btnConfirmReset.disabled = true;
    btnConfirmReset.classList.add('btn-loading');
    const span = btnConfirmReset.querySelector('span');
    if (span) span.textContent = 'Salvando nova senha…';
  }

  try {
    const res = await fetch('/api/auth/reset-password', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token, new_password: newPassword })
    });

    const json = await res.json();

    if (!res.ok) {
      showFeedback(confirmFeedback, json.error || json.message || 'Falha ao redefinir senha.', 'error');
      return;
    }

    showFeedback(confirmFeedback, '✓ Senha alterada. Redirecionando para o login…', 'success');

    // Desabilita formulário e redireciona para login
    newPasswordInput.disabled = true;
    confirmPasswordInput.disabled = true;

    setTimeout(() => {
      window.location.replace('/login');
    }, 1400);

  } catch (err) {
    showFeedback(confirmFeedback, 'Não foi possível conectar ao servidor. Verifique sua conexão.', 'error');
  } finally {
    if (btnConfirmReset && !confirmFeedback.classList.contains('feedback-success')) {
      btnConfirmReset.disabled = false;
      btnConfirmReset.classList.remove('btn-loading');
      const span = btnConfirmReset.querySelector('span');
      if (span) span.textContent = 'Salvar Nova Senha';
    }
  }
});

// ─── Inicialização: verifica se há token na URL ──────────────────────────────
const urlParams = new URLSearchParams(window.location.search);
const tokenFromUrl = urlParams.get('token');

if (tokenFromUrl) {
  switchToStep2(tokenFromUrl);
}
