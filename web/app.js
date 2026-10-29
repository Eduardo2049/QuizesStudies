import { icon } from './modules/icons.js?v=6';
import { initTheme, toggleTheme } from './modules/theme.js?v=9';
import { initShortcuts, getShortcutBadgeHtml } from './modules/shortcuts.js?v=5';
import { calculateQuizStats, renderStatsHtml } from './modules/stats.js?v=7';
import { initTimerDrag } from './modules/timer-drag.js?v=1';
import { getLanguage } from './modules/i18n.js?v=3';

// ─── Estado global ────────────────────────────────────────────────────────────
const quiz = document.querySelector('#quiz');
const progress = document.querySelector('#progress');
const percent = document.querySelector('#percent');
const progressBar = document.querySelector('#progressBar');
const quizSelector = document.querySelector('#quizSelector');
const customQuizSelectorWrap = document.querySelector('#customQuizSelectorWrap');
const customQuizTrigger = document.querySelector('#customQuizTrigger');
const customQuizValue = document.querySelector('#customQuizValue');
const customQuizDropdown = document.querySelector('#customQuizDropdown');
const timer = document.querySelector('#timer');
const startBtn = document.querySelector('#startBtn');

// ─── Toolbar & Modos de Visualização ──────────────────────────────────────────
const examToolbar = document.querySelector('#examToolbar');
const btnToggleFocus = document.querySelector('#btnToggleFocus');
const btnToggleList = document.querySelector('#btnToggleList');
const btnQuickSubmit = document.querySelector('#btnQuickSubmit');
const questionPalette = document.querySelector('#questionPalette');

// ─── Navegação do Modo Foco ───────────────────────────────────────────────────
const focusNavigation = document.querySelector('#focusNavigation');
const btnPrevQuestion = document.querySelector('#btnPrevQuestion');
const btnNextQuestion = document.querySelector('#btnNextQuestion');
const focusIndicator = document.querySelector('#focusIndicator');

// ─── Modal Catálogo de Simulados ──────────────────────────────────────────────
const catalogModal = document.querySelector('#catalogModal');
const btnOpenCatalog = document.querySelector('#btnOpenCatalog');
const closeCatalogModalBtn = document.querySelector('#closeCatalogModal');
const catalogSearchInput = document.querySelector('#catalogSearchInput');
const catalogList = document.querySelector('#catalogList');
const catalogTabBtns = document.querySelectorAll('.catalog-tab-btn');

// ─── Modal de Confirmação: Finalizar Simulado ──────────────────────────────────
const confirmSubmitModal = document.querySelector('#confirmSubmitModal');
const confirmSubmitCancel = document.querySelector('#confirmSubmitCancel');
const confirmSubmitConfirm = document.querySelector('#confirmSubmitConfirm');
const confirmSubmitAnsweredEl = document.querySelector('#confirmSubmitAnswered');
const confirmSubmitTotalEl = document.querySelector('#confirmSubmitTotal');
const confirmSubmitMissingEl = document.querySelector('#confirmSubmitMissing');
const confirmSubmitWarning = document.querySelector('#confirmSubmitWarning');

/** Abre o modal de confirmação de finalização e retorna uma Promise<boolean> */
// ─── Acessibilidade: Confinamento e Gerenciamento de Foco em Modais (WAI-ARIA) ──
function trapFocus(modalElement, initialFocusElement = null) {
  if (!modalElement) return () => {};

  const previousActive = document.activeElement;
  const focusableSelector = 'button:not([disabled]), [href], input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

  function getFocusableElements() {
    return Array.from(modalElement.querySelectorAll(focusableSelector))
      .filter(el => el.offsetParent !== null && !el.hidden && window.getComputedStyle(el).visibility !== 'hidden');
  }

  const timer = setTimeout(() => {
    if (initialFocusElement && typeof initialFocusElement.focus === 'function' && !initialFocusElement.disabled) {
      initialFocusElement.focus();
    } else {
      const focusables = getFocusableElements();
      if (focusables.length) {
        focusables[0].focus();
      } else {
        modalElement.focus();
      }
    }
  }, 40);

  function handleKeyDown(e) {
    if (e.key !== 'Tab') return;

    const focusables = getFocusableElements();
    if (!focusables.length) {
      e.preventDefault();
      return;
    }

    const first = focusables[0];
    const last = focusables[focusables.length - 1];

    if (e.shiftKey) {
      if (document.activeElement === first || !modalElement.contains(document.activeElement)) {
        e.preventDefault();
        last.focus();
      }
    } else {
      if (document.activeElement === last || !modalElement.contains(document.activeElement)) {
        e.preventDefault();
        first.focus();
      }
    }
  }

  modalElement.addEventListener('keydown', handleKeyDown);

  return function releaseFocus() {
    clearTimeout(timer);
    modalElement.removeEventListener('keydown', handleKeyDown);
    if (previousActive && typeof previousActive.focus === 'function' && document.body.contains(previousActive)) {
      try {
        previousActive.focus();
      } catch (_) {}
    }
  };
}

function openConfirmSubmitModal(answeredCount, totalCount) {
  return new Promise((resolve) => {
    if (confirmSubmitAnsweredEl) confirmSubmitAnsweredEl.textContent = answeredCount;
    if (confirmSubmitTotalEl) confirmSubmitTotalEl.textContent = totalCount;
    const missing = totalCount - answeredCount;
    if (confirmSubmitWarning) {
      if (missing > 0) {
        if (confirmSubmitMissingEl) confirmSubmitMissingEl.textContent = missing;
        confirmSubmitWarning.hidden = false;
      } else {
        confirmSubmitWarning.hidden = true;
      }
    }
    if (confirmSubmitModal) {
      confirmSubmitModal.hidden = false;
      document.body.style.overflow = 'hidden';
    }

    // Gerenciador acessível de foco: foca inicialmente o botão principal de confirmação
    const releaseFocus = trapFocus(confirmSubmitModal, confirmSubmitConfirm);

    function onConfirm() {
      cleanup();
      resolve(true);
    }
    function onCancel() {
      cleanup();
      resolve(false);
    }
    function cleanup() {
      if (confirmSubmitModal) {
        confirmSubmitModal.hidden = true;
        document.body.style.overflow = '';
      }
      confirmSubmitConfirm?.removeEventListener('click', onConfirm);
      confirmSubmitCancel?.removeEventListener('click', onCancel);
      confirmSubmitModal?.removeEventListener('click', onOverlayClick);
      document.removeEventListener('keydown', onKeyDown);
      releaseFocus();
    }
    function onOverlayClick(e) {
      if (e.target === confirmSubmitModal) onCancel();
    }

    function onKeyDown(e) {
      if (confirmSubmitModal && confirmSubmitModal.hidden) return;

      // Navegação por setas: ← ou ↑ foca Cancelar; → ou ↓ foca Confirmar
      if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
        e.preventDefault();
        confirmSubmitCancel?.focus();
        return;
      }
      if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
        e.preventDefault();
        confirmSubmitConfirm?.focus();
        return;
      }

      // Enter aciona a ação do botão selecionado ou confirma diretamente
      if (e.key === 'Enter') {
        e.preventDefault();
        if (document.activeElement === confirmSubmitCancel) {
          onCancel();
        } else {
          onConfirm();
        }
        return;
      }

      // Escape fecha o modal cancelando
      if (e.key === 'Escape') {
        e.preventDefault();
        onCancel();
        return;
      }
    }

    confirmSubmitConfirm?.addEventListener('click', onConfirm);
    confirmSubmitCancel?.addEventListener('click', onCancel);
    confirmSubmitModal?.addEventListener('click', onOverlayClick);
    document.addEventListener('keydown', onKeyDown);
  });
}

// ─── Modal Genérico de Notificação (substitui alert() nativo) ───────────────
export function showNotice(message, title = 'Aviso', iconName = 'info') {
  return new Promise((resolve) => {
    const modal = document.getElementById('noticeModal');
    const titleEl = document.getElementById('noticeModalTitle');
    const msgEl = document.getElementById('noticeModalMessage');
    const iconEl = document.getElementById('noticeIcon');
    const closeBtn = document.getElementById('btnNoticeClose');

    if (!modal) {
      alert(message);
      resolve();
      return;
    }

    if (titleEl) titleEl.textContent = title;
    if (msgEl) msgEl.textContent = message;
    if (iconEl) iconEl.innerHTML = icon(iconName, 36);

    modal.hidden = false;
    document.body.style.overflow = 'hidden';

    const releaseFocus = trapFocus(modal, closeBtn);

    function onClose() {
      cleanup();
      resolve();
    }
    function onOverlayClick(e) {
      if (e.target === modal) onClose();
    }
    function onKeyDown(e) {
      if (e.key === 'Escape' || e.key === 'Enter') onClose();
    }
    function cleanup() {
      modal.hidden = true;
      document.body.style.overflow = '';
      closeBtn?.removeEventListener('click', onClose);
      modal.removeEventListener('click', onOverlayClick);
      document.removeEventListener('keydown', onKeyDown);
      releaseFocus();
    }

    closeBtn?.addEventListener('click', onClose);
    modal.addEventListener('click', onOverlayClick);
    document.addEventListener('keydown', onKeyDown);
  });
}

// ─── Modal de Configuração de Tempo (substitui prompt() nativo) ─────────────
export function openCustomTimerModal() {
  const modal = document.getElementById('customTimerModal');
  const closeBtn = document.getElementById('closeCustomTimerModal');
  const cancelBtn = document.getElementById('cancelCustomTimer');
  const form = document.getElementById('customTimerForm');
  const input = document.getElementById('customTimerMinutesInput');
  const feedback = document.getElementById('customTimerFeedback');
  const presetsGrid = document.getElementById('timerPresetsGrid');

  if (!modal) return;

  hideTimerConfig(0);
  if (feedback) {
    feedback.hidden = true;
    feedback.textContent = '';
  }

  // Preencher input com o valor atual ou vazio
  const currentMins = customTimerSeconds ? Math.round(customTimerSeconds / 60) : '';
  if (input) input.value = currentMins;

  // Destacar chip ativo se coincidir
  const currentVal = customTimerSeconds ? String(Math.round(customTimerSeconds / 60)) : 'auto';
  presetsGrid?.querySelectorAll('.timer-chip').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.mins === currentVal);
  });

  modal.hidden = false;
  document.body.style.overflow = 'hidden';

  const releaseFocus = trapFocus(modal, input);

  function applyPreset(mins) {
    if (mins === 'auto') {
      customTimerSeconds = null;
      if (timerPreset) {
        const existingCustom = timerPreset.querySelector('[value="custom-set"]');
        if (existingCustom) existingCustom.remove();
        timerPreset.value = 'auto';
      }
    } else {
      const num = parseInt(mins, 10);
      if (!isNaN(num) && num > 0) {
        customTimerSeconds = num * 60;
        setPresetOption(num);
      }
    }
    if (!timerInterval) resetTimer();
    closeModal();
  }

  function setPresetOption(num) {
    if (!timerPreset) return;
    const existing = timerPreset.querySelector(`[value="${num * 60}"]`);
    if (existing) {
      timerPreset.value = String(num * 60);
    } else {
      const existingCustom = timerPreset.querySelector('[value="custom-set"]');
      if (existingCustom) existingCustom.remove();
      const opt = document.createElement('option');
      opt.value = 'custom-set';
      opt.textContent = `${num} min ✎`;
      timerPreset.insertBefore(opt, timerPreset.querySelector('[value="custom"]'));
      timerPreset.value = 'custom-set';
    }
  }

  function onChipClick(e) {
    const chip = e.target.closest('.timer-chip');
    if (!chip) return;
    applyPreset(chip.dataset.mins);
  }

  function onSubmit(e) {
    e.preventDefault();
    const raw = input?.value?.trim();
    const mins = parseInt(raw, 10);
    if (isNaN(mins) || mins < 1 || mins > 300) {
      if (feedback) {
        feedback.hidden = false;
        feedback.textContent = 'Por favor, informe um número entre 1 e 300 minutos.';
      }
      input?.focus();
      return;
    }
    applyPreset(String(mins));
  }

  function closeModal() {
    modal.hidden = true;
    document.body.style.overflow = '';
    if (timerPreset && timerPreset.value === 'custom') {
      timerPreset.value = customTimerSeconds !== null ? 'custom-set' : 'auto';
    }
    cleanup();
  }

  function onOverlayClick(e) {
    if (e.target === modal) closeModal();
  }

  function onKeyDown(e) {
    if (e.key === 'Escape') closeModal();
  }

  function cleanup() {
    closeBtn?.removeEventListener('click', closeModal);
    cancelBtn?.removeEventListener('click', closeModal);
    modal.removeEventListener('click', onOverlayClick);
    form?.removeEventListener('submit', onSubmit);
    presetsGrid?.removeEventListener('click', onChipClick);
    document.removeEventListener('keydown', onKeyDown);
    releaseFocus();
  }

  closeBtn?.addEventListener('click', closeModal);
  cancelBtn?.addEventListener('click', closeModal);
  modal.addEventListener('click', onOverlayClick);
  form?.addEventListener('submit', onSubmit);
  presetsGrid?.addEventListener('click', onChipClick);
  document.addEventListener('keydown', onKeyDown);
}

let releaseCatalogFocus = null;
function openCatalogModal() {
  if (catalogModal) {
    catalogModal.hidden = false;
    document.body.style.overflow = 'hidden';
    renderCatalogList();
    releaseCatalogFocus = trapFocus(catalogModal, catalogSearchInput);
  }
}

function closeCatalogModal() {
  if (catalogModal) {
    catalogModal.hidden = true;
    document.body.style.overflow = '';
    releaseCatalogFocus?.();
    releaseCatalogFocus = null;
  }
}

let currentQuestionIndex = 0;
let viewMode = 'focus'; // 'focus' | 'list'
let allPlatformQuizzes = [];
let currentCatalogFilter = 'all';

// ─── Modal de Resultado do Simulado ───────────────────────────────────────────
const resultModal = document.querySelector('#resultModal');
const closeResultModalBtn = document.querySelector('#closeResultModal');
const btnCloseResultModal = document.querySelector('#btnCloseResultModal');
const btnRedoQuiz = document.querySelector('#btnRedoQuiz');
const btnTrainMistakes = document.querySelector('#btnTrainMistakes');
const btnRemixMistakes = document.querySelector('#btnRemixMistakes');
const mistakesCount = document.querySelector('#mistakesCount');
const resultScoreBadge = document.querySelector('#resultScoreBadge');
const resultScoreNumber = document.querySelector('#resultScoreNumber');
const resultScorePercent = document.querySelector('#resultScorePercent');
const resultSummaryText = document.querySelector('#resultSummaryText');
const resultQuestionsList = document.querySelector('#resultQuestionsList');

let releaseResultFocus = null;
function openResultModal() {
  if (resultModal) {
    resultModal.hidden = false;
    document.body.style.overflow = 'hidden';
    releaseResultFocus = trapFocus(resultModal, btnRedoQuiz || btnCloseResultModal);
  }
}

function closeResultModal() {
  if (resultModal) {
    resultModal.hidden = true;
    document.body.style.overflow = '';
    releaseResultFocus?.();
    releaseResultFocus = null;
  }
}

// ─── Modal Explicativo: Por que o Acely? ──────────────────────────────────
const aboutModal = document.querySelector('#aboutModal');
const btnOpenAboutModal = document.querySelector('#btnOpenAboutModal');
const closeAboutModalBtn = document.querySelector('#closeAboutModal');
const btnCloseAbout = document.querySelector('#btnCloseAbout');

let releaseAboutFocus = null;
function openAboutModal() {
  if (aboutModal) {
    aboutModal.hidden = false;
    document.body.style.overflow = 'hidden';
    // Foco inicial no fechar do topo: focar o botão do rodapé rolava o modal até o fim
    releaseAboutFocus = trapFocus(aboutModal, closeAboutModalBtn || btnCloseAbout);
  }
}

function closeAboutModal() {
  if (aboutModal) {
    aboutModal.hidden = true;
    document.body.style.overflow = '';
    releaseAboutFocus?.();
    releaseAboutFocus = null;
  }
}

let currentWrongQuestions = [];

let questions = [];
let selectedSource = '';
let loadRequestId = 0;
let loadController;
let remainingSeconds = 24 * 60; // valor padrão; recalculado em resetTimer()
let timerInterval;

// ─── Sessão: visitante, convidado ou conta ────────────────────────────────────
// Visitante (currentUser === null): navega e resolve simulados prontos sem cadastro.
// Convidado (role 'guest'): escolheu "continuar como convidado"; usa a IA dentro da
//   cota gratuita contada no servidor e guarda os simulados só nesta aba.
// Conta (student/admin): simulados e histórico salvos no banco.
let currentUser = null;
let guestAI = null;          // { limit, used, remaining, window_hours } do servidor
let sessionResolved = false; // vira true quando checkAuth() termina

function isGuestMode() {
  if (currentUser) return currentUser.role === 'guest';
  // Antes da checagem de sessão terminar, a marca da aba permite já ler os simulados locais
  return !sessionResolved && sessionStorage.getItem('quiz_guest_mode') === 'true';
}

function clearGuestData() {
  sessionStorage.removeItem('quiz_guest_mode');
  sessionStorage.removeItem('quiz_guest_data');
  sessionStorage.removeItem('quiz_guest_quizzes');
  localStorage.removeItem('quiz_guest_mode');
  localStorage.removeItem('quiz_guest_data');
  localStorage.removeItem('quiz_guest_quizzes');
}

function getGuestQuiz() {
  try {
    return JSON.parse(sessionStorage.getItem('quiz_guest_data') || localStorage.getItem('quiz_guest_data') || 'null');
  } catch (_) {
    return null;
  }
}

function getGuestQuizzes() {
  try {
    const list = JSON.parse(sessionStorage.getItem('quiz_guest_quizzes') || localStorage.getItem('quiz_guest_quizzes') || '[]');
    if (Array.isArray(list) && list.length > 0) return list;
  } catch (_) {}
  const single = getGuestQuiz();
  return single ? [single] : [];
}

function saveGuestQuiz(quizData) {
  const quizzes = getGuestQuizzes().filter((q) => q.name !== quizData.name);
  quizzes.unshift(quizData);
  sessionStorage.setItem('quiz_guest_quizzes', JSON.stringify(quizzes));
  sessionStorage.setItem('quiz_guest_data', JSON.stringify(quizData));
}

function findGuestQuizByName(name) {
  const quizzes = getGuestQuizzes();
  return quizzes.find((q) => q.name === name) || null;
}

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, (character) => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;',
  }[character]));
}

// ─── Timer Adaptativo + Customizável ─────────────────────────────────────────
const timerPreset = document.querySelector('#timerPreset');
const timerConfig = document.querySelector('#timerConfig');
// (referência ao #timer já existe na const 'timer' declarada no início)

/** Tempo customizado pelo usuário (null = usar automático) */
let customTimerSeconds = null;

function calculateTimerDuration(questionCount) {
  // Se há um preset fixo, usa ele; senão calcula adaptive
  if (customTimerSeconds !== null) return customTimerSeconds;
  const count = Math.max(1, questionCount || 1);
  return Math.max(5 * 60, count * 150); // ~2m30s por questão, mínimo de 5 minutos
}

function formatTime(seconds) {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

function resetTimer() {
  clearInterval(timerInterval);
  timerInterval = undefined;
  const count = questions.length || 5;
  const duration = calculateTimerDuration(count);
  remainingSeconds = duration;
  timer.textContent = formatTime(duration);
  timer.classList.remove('expired', 'running');
  if (startBtn) startBtn.classList.remove('hidden');
}

function startTimer() {
  if (timerInterval || remainingSeconds === 0) return;
  timer.classList.add('running');
  if (startBtn) startBtn.classList.add('hidden');
  timerInterval = setInterval(() => {
    remainingSeconds -= 1;
    timer.textContent = formatTime(remainingSeconds);
    if (remainingSeconds === 0) {
      clearInterval(timerInterval);
      timerInterval = undefined;
      timer.classList.remove('running');
      timer.classList.add('expired');
    }
  }, 1000);
}

// ─── Lógica do painel de configuração do timer ────────────────────────────────
let timerConfigTimeout;

function showTimerConfig() {
  clearTimeout(timerConfigTimeout);
  timerConfig?.classList.add('timer-config--visible');
}

function hideTimerConfig(delay = 900) {
  clearTimeout(timerConfigTimeout);
  timerConfigTimeout = setTimeout(() => {
    timerConfig?.classList.remove('timer-config--visible');
  }, delay);
}

timer?.addEventListener('mouseenter', showTimerConfig);
timer?.addEventListener('mouseleave', () => hideTimerConfig());
timerConfig?.addEventListener('mouseenter', showTimerConfig);
timerConfig?.addEventListener('mouseleave', () => hideTimerConfig());
timer?.addEventListener('focus', showTimerConfig);
timer?.addEventListener('blur', () => hideTimerConfig());
timer?.addEventListener('click', () => openCustomTimerModal());
document.querySelector('.timer-config-label')?.addEventListener('click', () => openCustomTimerModal());
document.querySelector('#btnSetTimer')?.addEventListener('click', () => openCustomTimerModal());

timerPreset?.addEventListener('change', () => {
  const val = timerPreset.value;

  if (val === 'auto') {
    customTimerSeconds = null;
    const existingCustom = timerPreset.querySelector('[value="custom-set"]');
    if (existingCustom) existingCustom.remove();
  } else if (val === 'custom') {
    openCustomTimerModal();
    return;
  } else {
    customTimerSeconds = parseInt(val, 10);
    const existingCustom = timerPreset.querySelector('[value="custom-set"]');
    if (existingCustom) existingCustom.remove();
  }

  // Aplicar imediatamente se o timer não estiver rodando
  if (!timerInterval) {
    resetTimer();
  }
  hideTimerConfig(200);
});


// ─── Carregamento de Quiz ─────────────────────────────────────────────────────
async function loadQuiz(source = selectedSource) {
  // Se for convidado e o quiz for local, carrega diretamente do storage
  if (isGuestMode()) {
    const localQuiz = source ? findGuestQuizByName(source) : (getGuestQuizzes()[0] || null);
    if (localQuiz && (!source || localQuiz.name === source)) {
      selectedSource = localQuiz.name;
      questions = localQuiz.questions || [];
      if (!questions.length) {
        quiz.innerHTML = '<p class="empty-state">Nenhuma questão encontrada neste quiz.</p>';
        updateProgress();
        return;
      }
      renderQuestions();
      return;
    }
  }

  const requestId = ++loadRequestId;
  loadController?.abort();
  loadController = new AbortController();
  const response = await fetch(`/api/quiz${source ? `?source=${encodeURIComponent(source)}` : ''}`, {
    cache: 'no-cache', // revalida via ETag: 304 sem corpo quando nada mudou
    signal: loadController.signal,
  });
  if (!response.ok) throw new Error(`Falha ao carregar o questionário (${response.status})`);
  const rawData = await response.json();
  const data = rawData.data || rawData;
  if (requestId !== loadRequestId) return;
  selectedSource = data.source;
  questions = data.questions;

  if (!questions.length) {
    quiz.innerHTML = '<p class="empty-state">Nenhuma questão encontrada. Adicione um quiz usando o botão acima.</p>';
    updateProgress();
    return;
  }

  renderQuestions();
}

function renderQuestions() {
  if (currentQuestionIndex >= questions.length) {
    currentQuestionIndex = Math.max(0, questions.length - 1);
  }

  quiz.classList.toggle('quiz--focus', viewMode === 'focus');

  quiz.innerHTML = questions.map((item, index) => `
    <article class="question ${viewMode === 'focus' && index === currentQuestionIndex ? 'question--active' : ''}" data-index="${index}" id="question-card-${index}">
      <p class="section">${escapeHtml(item.section)}</p>
      ${item.context && (index === 0 || questions[index - 1].context !== item.context)
        ? `<p class="context">${escapeHtml(item.context)}</p>` : ''}
      <div class="question-head">
        <span class="number">${escapeHtml(String(item.id).padStart(2, '0'))}</span>
        <h2>${escapeHtml(item.question)}</h2>
      </div>
      <div class="options">
        ${item.options.map((option, i) => `
          <label class="option" id="option-${index}-${i}">
            <input type="radio" name="q-${escapeHtml(item.id)}" value="${i}">
            <span>${String.fromCharCode(65 + i)}) ${escapeHtml(option)}</span>
            ${getShortcutBadgeHtml(i)}
          </label>
        `).join('')}
      </div>
    </article>`).join('');

  updateFocusNavigation();
  renderQuestionPalette();
  updateProgress();
}

function renderQuestionPalette() {
  if (!questionPalette) return;
  if (!questions.length) {
    questionPalette.innerHTML = '';
    questionPalette.hidden = true;
    return;
  }

  questionPalette.hidden = false;
  const answered = new FormData(quiz);
  const answeredKeys = new Set([...answered.keys()].map((k) => k.replace('q-', '')));

  questionPalette.innerHTML = questions.map((item, index) => {
    const isAnswered = answeredKeys.has(String(item.id));
    const isCurrent = viewMode === 'focus' && index === currentQuestionIndex;
    const classes = ['palette-btn'];
    if (isAnswered) classes.push('answered');
    if (isCurrent) classes.push('active');

    return `
      <button type="button" 
              class="${classes.join(' ')}" 
              data-index="${index}" 
              title="Questão ${index + 1}${isAnswered ? ' (Respondida)' : ''}">
        ${index + 1}
      </button>
    `;
  }).join('');
}

function goToQuestion(index) {
  if (index < 0 || index >= questions.length) return;
  currentQuestionIndex = index;

  if (viewMode === 'focus') {
    const cards = quiz.querySelectorAll('.question');
    cards.forEach((card, idx) => {
      card.classList.toggle('question--active', idx === currentQuestionIndex);
    });
    updateFocusNavigation();
    renderQuestionPalette();
    const activeCard = quiz.querySelector('.question.question--active');
    if (activeCard) {
      activeCard.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  } else {
    renderQuestionPalette();
    const targetCard = document.querySelector(`#question-card-${index}`);
    if (targetCard) {
      targetCard.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }
}

function updateFocusNavigation() {
  if (!focusNavigation) return;
  if (viewMode !== 'focus' || !questions.length) {
    focusNavigation.hidden = true;
    return;
  }

  focusNavigation.hidden = false;
  if (focusIndicator) {
    focusIndicator.textContent = `Questão ${currentQuestionIndex + 1} de ${questions.length}`;
  }

  if (btnPrevQuestion) {
    btnPrevQuestion.disabled = currentQuestionIndex === 0;
  }

  if (btnNextQuestion) {
    const isLast = currentQuestionIndex === questions.length - 1;
    if (isLast) {
      btnNextQuestion.innerHTML = `${icon('flag')} Finalizar simulado`;
      btnNextQuestion.classList.add('is-final');
    } else {
      btnNextQuestion.innerHTML = 'Próxima →';
      btnNextQuestion.classList.remove('is-final');
    }
  }
}

async function loadQuizList() {
  let serverQuizzes = [];
  try {
    const response = await fetch('/api/quizzes', { cache: 'no-cache' });
    if (response.ok) {
      const rawData = await response.json();
      const data = rawData.data || rawData;
      serverQuizzes = data.quizzes || [];
      allPlatformQuizzes = serverQuizzes;
    }
  } catch (e) {
    console.warn('Não foi possível carregar quizzes da plataforma:', e);
  }

  const localQuizzes = isGuestMode() ? getGuestQuizzes() : [];

  if (!serverQuizzes.length && !localQuizzes.length) {
    quizSelector.innerHTML = '<option value="">— Nenhum quiz disponível —</option>';
    renderCustomQuizOptions([], []);
    syncCustomQuizSelector();
    return;
  }

  let html = '';
  if (serverQuizzes.length > 0) {
    html += '<optgroup label="Quizzes da Plataforma">';
    html += serverQuizzes.map((item) =>
      `<option value="${escapeHtml(item.name)}">
        ${escapeHtml(item.label)}${item.ai_generated ? ' (IA)' : ''}
      </option>`
    ).join('');
    html += '</optgroup>';
  }

  if (localQuizzes.length > 0) {
    html += '<optgroup label="Seus Quizzes Gerados (Convidado)">';
    html += localQuizzes.map((item) =>
      `<option value="${escapeHtml(item.name)}">
        ${escapeHtml(item.label)} (IA)
      </option>`
    ).join('');
    html += '</optgroup>';
  }

  quizSelector.innerHTML = html;

  // Restaurar seleção se válida
  const optionExists = selectedSource && quizSelector.querySelector(`option[value="${CSS.escape(selectedSource)}"]`);
  if (optionExists) {
    quizSelector.value = selectedSource;
  } else if (quizSelector.options.length > 0) {
    selectedSource = quizSelector.options[0].value;
    quizSelector.value = selectedSource;
  }

  renderCustomQuizOptions(serverQuizzes, localQuizzes);
  syncCustomQuizSelector();
}

// ─── Custom Quiz Selector Component ──────────────────────────────────────────
function renderCustomQuizOptions(serverQuizzes = [], localQuizzes = []) {
  if (!customQuizDropdown) return;

  if (!serverQuizzes.length && !localQuizzes.length) {
    customQuizDropdown.innerHTML = '<div class="custom-select-option custom-select-empty">Nenhum quiz disponível</div>';
    return;
  }

  let html = '';
  if (serverQuizzes.length > 0) {
    html += '<div class="custom-select-group">';
    html += '<div class="custom-select-group-header">Quizzes da Plataforma</div>';
    html += serverQuizzes.map((item) => `
      <div class="custom-select-option" role="option" data-value="${escapeHtml(item.name)}" tabindex="0">
        <span class="custom-select-option-label">${escapeHtml(item.label)}${item.ai_generated ? ` <span class="inline-ai">${icon('bot', 14)}</span>` : ''}</span>
        <span class="custom-select-option-check" aria-hidden="true"></span>
      </div>
    `).join('');
    html += '</div>';
  }

  if (localQuizzes.length > 0) {
    html += '<div class="custom-select-group">';
    html += '<div class="custom-select-group-header">Seus Quizzes Gerados (Convidado)</div>';
    html += localQuizzes.map((item) => `
      <div class="custom-select-option" role="option" data-value="${escapeHtml(item.name)}" tabindex="0">
        <span class="custom-select-option-label">${escapeHtml(item.label)} <span class="inline-ai">${icon('sparkle', 14)}</span></span>
        <span class="custom-select-option-check" aria-hidden="true"></span>
      </div>
    `).join('');
    html += '</div>';
  }

  customQuizDropdown.innerHTML = html;
}

function syncCustomQuizSelector() {
  if (!quizSelector || !customQuizValue) return;

  const currentVal = quizSelector.value;
  const selectedOpt = quizSelector.selectedOptions?.[0] || quizSelector.querySelector(`option[value="${CSS.escape(currentVal)}"]`);
  if (selectedOpt) {
    customQuizValue.textContent = selectedOpt.textContent.trim();
  } else if (selectedSource) {
    customQuizValue.textContent = selectedSource;
  } else {
    customQuizValue.textContent = 'Selecione um simulado…';
  }

  if (customQuizDropdown) {
    customQuizDropdown.querySelectorAll('.custom-select-option').forEach(opt => {
      const isSel = opt.getAttribute('data-value') === currentVal;
      opt.classList.toggle('is-selected', isSel);
      opt.setAttribute('aria-selected', isSel ? 'true' : 'false');
      const checkSpan = opt.querySelector('.custom-select-option-check');
      if (checkSpan) checkSpan.textContent = isSel ? '✓' : '';
    });
  }
}

function openCustomQuizDropdown() {
  if (!customQuizDropdown || !customQuizTrigger) return;
  customQuizDropdown.removeAttribute('hidden');
  customQuizTrigger.setAttribute('aria-expanded', 'true');
  const selectedItem = customQuizDropdown.querySelector('.custom-select-option.is-selected');
  if (selectedItem) {
    selectedItem.scrollIntoView({ block: 'nearest' });
  }
}

function closeCustomQuizDropdown() {
  if (!customQuizDropdown || !customQuizTrigger) return;
  customQuizDropdown.setAttribute('hidden', '');
  customQuizTrigger.setAttribute('aria-expanded', 'false');
}

customQuizTrigger?.addEventListener('click', (e) => {
  e.stopPropagation();
  const isExpanded = customQuizTrigger.getAttribute('aria-expanded') === 'true';
  if (isExpanded) {
    closeCustomQuizDropdown();
  } else {
    openCustomQuizDropdown();
  }
});

customQuizDropdown?.addEventListener('click', (e) => {
  const option = e.target.closest('.custom-select-option');
  if (!option || option.classList.contains('custom-select-empty')) return;
  const val = option.getAttribute('data-value');
  if (!val) return;

  closeCustomQuizDropdown();
  if (quizSelector && quizSelector.value !== val) {
    selectedSource = val;
    quizSelector.value = val;
    syncCustomQuizSelector();
    quizSelector.dispatchEvent(new Event('change', { bubbles: true }));
  }
});

document.addEventListener('click', (e) => {
  if (!customQuizSelectorWrap?.contains(e.target)) {
    closeCustomQuizDropdown();
  }
});

document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && customQuizTrigger?.getAttribute('aria-expanded') === 'true') {
    closeCustomQuizDropdown();
    customQuizTrigger?.focus();
  }
});

// ─── Progresso ────────────────────────────────────────────────────────────────
function updateProgress() {
  const answered = new FormData(quiz);
  const count = [...answered.keys()].length;
  const value = Math.round(count / (questions.length || 1) * 100);
  progress.textContent = `${count} de ${questions.length} respondidas`;
  percent.textContent = `${value}%`;
  progressBar.style.width = `${value}%`;

  renderQuestionPalette();

  if (btnQuickSubmit) {
    btnQuickSubmit.hidden = questions.length === 0;
    if (count > 0) {
      btnQuickSubmit.innerHTML = `${icon('flag')} Finalizar (${count}/${questions.length})`;
    } else {
      btnQuickSubmit.innerHTML = `${icon('flag')} Finalizar simulado`;
    }
  }
}

// ─── Eventos do Quiz ──────────────────────────────────────────────────────────
async function handleSubmitQuiz(event) {
  if (event) event.preventDefault();
  if (!questions.length) return;

  const answers = Object.fromEntries(
    [...new FormData(quiz)].map(([key, value]) => [key.replace('q-', ''), Number(value)])
  );
  const answeredCount = Object.keys(answers).length;

  if (answeredCount === 0) {
    showNotice('Por favor, marque pelo menos uma resposta antes de conferir.', 'Simulado Incompleto', 'warning');
    return;
  }

  // Modal de confirmação customizado (substitui o confirm() nativo)
  const confirmed = await openConfirmSubmitModal(answeredCount, questions.length);
  if (!confirmed) return;

  const submitBtn = document.querySelector('#submit');
  if (submitBtn) {
    submitBtn.disabled = true;
    submitBtn.textContent = 'Conferindo respostas…';
  }

  try {
    let data;
    const localQuiz = isGuestMode() ? findGuestQuizByName(selectedSource) : null;
    const hasLocalAnswers = questions.length > 0 && questions[0]?.answer !== undefined;
    const isLocalQuiz = Boolean(localQuiz && hasLocalAnswers) || Boolean(questions[0]?.is_remix) || (Boolean(!selectedSource) && hasLocalAnswers);

    if (isLocalQuiz) {
      const results = questions.map((item) => {
        const selected = answers[String(item.id)];
        return {
          id: item.id,
          selected: Number.isFinite(selected) ? selected : null,
          correct: item.answer,
          isCorrect: selected === item.answer,
          explanation: item.explanation || '',
        };
      });
      const score = results.filter((item) => item.isCorrect).length;
      const wrongIds = results.filter((item) => !item.isCorrect).map((item) => item.id);
      data = {
        score,
        total: results.length,
        percentage: results.length ? Math.round(score / results.length * 100) : 0,
        results,
        wrong_ids: wrongIds,
      };
    } else {
      const headers = { 'Content-Type': 'application/json' };

      const response = await fetch('/api/quiz/submit', {
        method: 'POST',
        headers,
        credentials: 'same-origin',
        body: JSON.stringify({ source: selectedSource, answers }),
      });

      if (!response.ok) {
        throw new Error(`Servidor retornou status ${response.status}`);
      }

      const rawData = await response.json();
      data = rawData.data || rawData;
    }

    clearInterval(timerInterval);
    timerInterval = undefined;
    timer.classList.remove('running');
    renderResultModal(data);
    openResultModal();
  } catch (err) {
    showNotice('Erro ao conferir respostas. Verifique a conexão com o servidor.', 'Erro de Conexão', 'error');
  } finally {
    if (submitBtn) {
      submitBtn.disabled = false;
      submitBtn.innerHTML = 'Conferir respostas <span>→</span>';
    }
  }
}

function renderResultModal(data) {
  const { score, total, percentage, results } = data;

  // Filtrar questões erradas para o Caderno de Erros e Variações IA
  const wrongIds = data.wrong_ids || results.filter((item) => !item.isCorrect).map((item) => item.id);
  currentWrongQuestions = questions.filter((q) => wrongIds.includes(q.id));

  if (btnTrainMistakes && btnRemixMistakes) {
    if (currentWrongQuestions.length > 0) {
      if (mistakesCount) mistakesCount.textContent = currentWrongQuestions.length;
      btnTrainMistakes.hidden = false;
      btnRemixMistakes.hidden = false;
    } else {
      btnTrainMistakes.hidden = true;
      btnRemixMistakes.hidden = true;
    }
  }

  if (resultScoreNumber) resultScoreNumber.textContent = `${score}/${total}`;
  if (resultScorePercent) resultScorePercent.textContent = `${percentage}%`;

  if (resultScoreBadge) {
    resultScoreBadge.className = 'results-badge';
    if (percentage >= 80) {
      resultScoreBadge.classList.add('excellent');
      resultScoreBadge.innerHTML = `${icon('target')} Excelente`;
    } else if (percentage >= 60) {
      resultScoreBadge.classList.add('good');
      resultScoreBadge.innerHTML = `${icon('thumb')} Bom trabalho`;
    } else {
      resultScoreBadge.classList.add('practice');
      resultScoreBadge.innerHTML = `${icon('bulb')} Continue praticando`;
    }
  }

  if (resultSummaryText) {
    if (percentage >= 80) {
      resultSummaryText.textContent = 'Parabéns. Você domina bem este conteúdo.';
    } else if (percentage >= 60) {
      resultSummaryText.textContent = 'Muito bom. Você acertou a maior parte das questões.';
    } else {
      resultSummaryText.textContent = 'Revise detalhadamente cada questão abaixo e tente novamente.';
    }
  }

  // ─── Feedback Pedagógico & Estatísticas Avançadas ───
  try {
    const totalExamSeconds = calculateTimerDuration(questions.length);
    const timeSpent = Math.max(1, totalExamSeconds - (remainingSeconds || 0));
    const normalizedResults = (results || []).map((r) => ({
      question_id: r.id,
      correct: Boolean(r.isCorrect),
      user_answer: r.selected,
      answer: r.correct,
      explanation: r.explanation,
    }));
    const stats = calculateQuizStats(questions, normalizedResults, timeSpent);
    const statsContainer = document.querySelector('#resultStatsContainer');
    if (statsContainer && stats) {
      statsContainer.innerHTML = renderStatsHtml(stats);
      // Aplica a largura das barras via CSSOM (não via atributo style inline),
      // compatível com CSP style-src sem 'unsafe-inline'.
      statsContainer.querySelectorAll('.section-progress-fill[data-percentage]').forEach((el) => {
        const pct = Math.max(0, Math.min(100, Number(el.dataset.percentage) || 0));
        el.style.width = `${pct}%`;
      });
    }
  } catch (err) {
    console.error('Erro ao renderizar estatísticas:', err);
  }

  if (resultQuestionsList) {
    resultQuestionsList.innerHTML = results.map((item) => {
      const qData = questions.find((q) => q.id === item.id);
      const questionText = qData?.question || `Questão ${item.id}`;
      const options = qData?.options || [];

      const hasUserSelected = item.selected !== null && item.selected !== undefined;
      const userSelectedLabel = hasUserSelected
        ? `${String.fromCharCode(65 + item.selected)}) ${escapeHtml(options[item.selected] ?? '')}`
        : 'Não respondida';

      const hasCorrect = item.correct !== null && item.correct !== undefined;
      const correctLabel = hasCorrect
        ? `${String.fromCharCode(65 + item.correct)}) ${escapeHtml(options[item.correct] ?? '')}`
        : '';

      return `
        <article class="result-card ${item.isCorrect ? 'is-correct' : 'is-wrong'}">
          <div class="result-card-header">
            <span class="result-card-qnumber">Questão ${escapeHtml(String(item.id).padStart(2, '0'))}</span>
            <span class="result-card-tag">${item.isCorrect ? '✓ Correta' : '✗ Errada'}</span>
          </div>
          <p class="result-card-question">${escapeHtml(questionText)}</p>
          <div class="result-card-answers">
            <div class="result-user-answer">
              Sua resposta: <strong>${userSelectedLabel}</strong>
            </div>
            ${!item.isCorrect && correctLabel ? `
            <div class="result-correct-answer">
              Gabarito correto: <strong>${correctLabel}</strong>
            </div>` : ''}
          </div>
          ${item.explanation ? `
          <div class="result-card-explanation">
            <strong>${icon('bulb')} Explicação Didática</strong>
            ${escapeHtml(item.explanation)}
          </div>` : ''}
        </article>
      `;
    }).join('');
  }
}

quiz.addEventListener('submit', handleSubmitQuiz);
document.querySelector('#submit')?.addEventListener('click', (e) => {
  e.preventDefault();
  handleSubmitQuiz(e);
});

startBtn?.addEventListener('click', () => {
  startTimer();
  const firstQuestion = quiz.querySelector('.question');
  if (firstQuestion) firstQuestion.scrollIntoView({ behavior: 'smooth', block: 'start' });
});

document.querySelector('#reset').addEventListener('click', () => {
  quiz.reset();
  resetTimer();
  closeResultModal();
  updateProgress();
  window.scrollTo({ top: 0, behavior: 'smooth' });
});

// Ações do Modal de Resultados
closeResultModalBtn?.addEventListener('click', closeResultModal);
btnCloseResultModal?.addEventListener('click', closeResultModal);
btnRedoQuiz?.addEventListener('click', () => {
  closeResultModal();
  quiz.reset();
  resetTimer();
  updateProgress();
  const firstQuestion = quiz.querySelector('.question');
  if (firstQuestion) {
    firstQuestion.scrollIntoView({ behavior: 'smooth', block: 'start' });
  } else {
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }
});

// Caderno de Erros: Refazer apenas as questões erradas
btnTrainMistakes?.addEventListener('click', () => {
  if (!currentWrongQuestions.length) return;
  closeResultModal();
  questions = [...currentWrongQuestions];
  renderQuestions();
  quiz.reset();
  resetTimer();
  updateProgress();
  const firstQuestion = quiz.querySelector('.question');
  if (firstQuestion) {
    firstQuestion.scrollIntoView({ behavior: 'smooth', block: 'start' });
  } else {
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }
});

// Gerar Variações Inéditas com IA (exige conta ou convidado com cota)
btnRemixMistakes?.addEventListener('click', () => {
  if (!currentWrongQuestions.length) return;
  requireAiAccess(runRemixMistakes, 'remix');
});

async function runRemixMistakes() {
  if (!currentWrongQuestions.length) return;

  const originalContent = btnRemixMistakes.innerHTML;
  btnRemixMistakes.disabled = true;
  btnRemixMistakes.innerHTML = `${icon('hourglass')} Criando variações com IA…`;

  try {
    const response = await fetch('/api/quiz/remix-mistakes', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'same-origin',
      body: JSON.stringify({ questions: currentWrongQuestions, language: getLanguage() }),
    });

    const raw = await readJson(response);
    if (!response.ok) {
      if (raw?.error === 'GUEST_AI_LIMIT_REACHED' || raw?.error === 'AUTH_REQUIRED') {
        closeResultModal();
        handleAccessError(raw, 'remix');
        return;
      }
      throw new Error(raw?.data?.message || raw?.message || 'Erro ao comunicar com a IA');
    }

    if (raw.data?.guest_ai) applyGuestStatus(raw.data.guest_ai);
    const remixedQuestions = raw.data?.questions || [];
    if (!remixedQuestions.length) {
      throw new Error('Nenhuma questão gerada.');
    }

    closeResultModal();
    questions = remixedQuestions;
    renderQuestions();
    quiz.reset();
    resetTimer();
    updateProgress();
    const firstQuestion = quiz.querySelector('.question');
    if (firstQuestion) {
      firstQuestion.scrollIntoView({ behavior: 'smooth', block: 'start' });
    } else {
      window.scrollTo({ top: 0, behavior: 'smooth' });
    }
  } catch (err) {
    showNotice(`Não foi possível gerar as variações: ${err.message}. Tente novamente em instantes.`, 'Falha na IA', 'error');
  } finally {
    btnRemixMistakes.disabled = false;
    btnRemixMistakes.innerHTML = originalContent;
  }
}

// Ações do Modal Explicativo (Sobre / Benchmarking)
btnOpenAboutModal?.addEventListener('click', openAboutModal);
closeAboutModalBtn?.addEventListener('click', closeAboutModal);
btnCloseAbout?.addEventListener('click', closeAboutModal);

// ─── Ações de Navegação e Alternância de Modo ─────────────────────────────
btnPrevQuestion?.addEventListener('click', () => {
  if (currentQuestionIndex > 0) {
    goToQuestion(currentQuestionIndex - 1);
  }
});

btnNextQuestion?.addEventListener('click', () => {
  if (currentQuestionIndex === questions.length - 1) {
    handleSubmitQuiz();
  } else if (currentQuestionIndex < questions.length - 1) {
    goToQuestion(currentQuestionIndex + 1);
  }
});

btnToggleFocus?.addEventListener('click', () => {
  viewMode = 'focus';
  btnToggleFocus.classList.add('active');
  btnToggleList.classList.remove('active');
  renderQuestions();
  goToQuestion(currentQuestionIndex);
});

btnToggleList?.addEventListener('click', () => {
  viewMode = 'list';
  btnToggleList.classList.add('active');
  btnToggleFocus.classList.remove('active');
  renderQuestions();
});

btnQuickSubmit?.addEventListener('click', (e) => {
  e.preventDefault();
  handleSubmitQuiz();
});

questionPalette?.addEventListener('click', (e) => {
  const btn = e.target.closest('.palette-btn');
  if (!btn) return;
  const targetIndex = Number(btn.getAttribute('data-index'));
  if (Number.isFinite(targetIndex)) {
    goToQuestion(targetIndex);
  }
});



// ─── Catálogo de Simulados ────────────────────────────────────────────────
function renderCatalogList() {
  if (!catalogList) return;

  const localQuizzes = isGuestMode() ? getGuestQuizzes() : [];
  const localItems = localQuizzes.map((q) => ({
    ...q,
    is_guest: true,
    question_count: q.questions ? q.questions.length : (q.question_count || 5),
  }));

  const combined = [...allPlatformQuizzes, ...localItems];
  const searchTerm = (catalogSearchInput?.value || '').trim().toLowerCase();

  const filtered = combined.filter((item) => {
    // Filtro por tab
    if (currentCatalogFilter === 'platform' && (item.is_guest || item.ai_generated)) return false;
    if (currentCatalogFilter === 'ai' && !item.ai_generated) return false;
    if (currentCatalogFilter === 'custom' && !item.is_guest && (!item.file_type || item.file_type === 'txt' || item.ai_generated)) return false;

    // Filtro por busca textual
    if (searchTerm) {
      const titleMatch = (item.label || '').toLowerCase().includes(searchTerm);
      const nameMatch = (item.name || '').toLowerCase().includes(searchTerm);
      return titleMatch || nameMatch;
    }
    return true;
  });

  if (!filtered.length) {
    catalogList.innerHTML = '<div class="catalog-empty">Nenhum simulado encontrado para os filtros selecionados.</div>';
    return;
  }

  catalogList.innerHTML = filtered.map((item) => {
    const count = item.question_count || 5;
    const estMinutes = Math.round(count * 2.5);
    const badgeLabel = item.ai_generated
      ? 'IA'
      : (item.file_type ? item.file_type.toUpperCase() : (item.is_guest ? 'LOCAL' : 'OFICIAL'));

    return `
      <div class="catalog-card" data-source="${escapeHtml(item.name)}">
        <div class="catalog-card-header">
          <h3 class="catalog-card-title">${escapeHtml(item.label)}</h3>
          <span class="catalog-card-badge ${item.ai_generated ? 'ai' : ''}">${escapeHtml(badgeLabel)}</span>
        </div>
        <div class="catalog-card-meta">
          <span>${icon('note', 14)} ${count} questões</span>
          <span>${icon('clock', 14)} ~${estMinutes} min</span>
        </div>
        <button type="button" class="primary catalog-card-btn">Iniciar Simulado ▶</button>
      </div>
    `;
  }).join('');
}

btnOpenCatalog?.addEventListener('click', openCatalogModal);
closeCatalogModalBtn?.addEventListener('click', closeCatalogModal);

catalogSearchInput?.addEventListener('input', () => {
  renderCatalogList();
});

catalogTabBtns.forEach((btn) => {
  btn.addEventListener('click', () => {
    catalogTabBtns.forEach((b) => b.classList.remove('active'));
    btn.classList.add('active');
    currentCatalogFilter = btn.getAttribute('data-filter') || 'all';
    renderCatalogList();
  });
});

catalogList?.addEventListener('click', async (e) => {
  const card = e.target.closest('.catalog-card');
  if (!card) return;
  const source = card.getAttribute('data-source');
  if (!source) return;

  closeCatalogModal();
  selectedSource = source;
  if (quizSelector) quizSelector.value = source;
  syncCustomQuizSelector();
  resetTimer();
  closeResultModal();
  quiz.innerHTML = '';

  try {
    await loadQuiz(source);
    startTimer();
    const firstQuestion = quiz.querySelector('.question');
    if (firstQuestion) {
      firstQuestion.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  } catch (err) {
    showNotice('Erro ao carregar o simulado selecionado.', 'Erro de Carregamento', 'error');
  }
});

quiz.addEventListener('change', (e) => {
  startTimer();
  updateProgress();
  const card = e.target?.closest?.('.question');
  if (card && card.dataset.index !== undefined) {
    const idx = parseInt(card.dataset.index, 10);
    if (!Number.isNaN(idx)) {
      currentQuestionIndex = idx;
    }
  }
});

quizSelector.addEventListener('change', async () => {
  resetTimer();
  closeResultModal();
  quiz.innerHTML = '';
  try {
    await loadQuiz(quizSelector.value);
  } catch (error) {
    if (error.name !== 'AbortError')
      quiz.innerHTML = `<p class="empty-state">Não foi possível carregar este questionário.</p>`;
  }
});

// ─── Modal de Upload / Gerar Quiz ─────────────────────────────────────────
const uploadModal = document.querySelector('#uploadModal');
const dropZone = document.querySelector('#dropZone');
const fileInput = document.querySelector('#fileInput');
const filePreview = document.querySelector('#filePreview');
const filePreviewName = document.querySelector('#filePreviewName');
const uploadStatus = document.querySelector('#uploadStatus');
const uploadStatusText = document.querySelector('#uploadStatusText');
const uploadError = document.querySelector('#uploadError');
const uploadSuccess = document.querySelector('#uploadSuccess');
const confirmUploadBtn = document.querySelector('#confirmUpload');
const confirmGenerateTopicBtn = document.querySelector('#confirmGenerateTopic');

// Abas e Painéis do Modal
const tabUploadFile = document.querySelector('#tabUploadFile');
const tabGenerateTopic = document.querySelector('#tabGenerateTopic');
const panelUpload = document.querySelector('#panelUpload');
const panelTopic = document.querySelector('#panelTopic');
const topicInput = document.querySelector('#topicInput');
const topicNumQuestions = document.querySelector('#topicNumQuestions');
const topicCustomQtyWrap = document.querySelector('#topicCustomQtyWrap');
const topicCustomQty = document.querySelector('#topicCustomQty');
const topicDifficulty = document.querySelector('#topicDifficulty');
const topicContext = document.querySelector('#topicContext');
const uploadNumQuestions = document.querySelector('#uploadNumQuestions');
const uploadCustomQtyWrap = document.querySelector('#uploadCustomQtyWrap');
const uploadCustomQty = document.querySelector('#uploadCustomQty');
const uploadContext = document.querySelector('#uploadContext');

uploadNumQuestions?.addEventListener('change', () => {
  if (uploadNumQuestions.value === 'custom') {
    uploadCustomQtyWrap?.removeAttribute('hidden');
    uploadCustomQty?.focus();
  } else {
    uploadCustomQtyWrap?.setAttribute('hidden', '');
  }
});

topicNumQuestions?.addEventListener('change', () => {
  if (topicNumQuestions.value === 'custom') {
    topicCustomQtyWrap?.removeAttribute('hidden');
    topicCustomQty?.focus();
  } else {
    topicCustomQtyWrap?.setAttribute('hidden', '');
  }
});

let selectedFile = null;

function switchModalTab(tabName) {
  uploadError.hidden = true;
  uploadError.textContent = '';
  uploadSuccess.hidden = true;
  uploadSuccess.textContent = '';

  if (tabName === 'topic') {
    tabGenerateTopic?.classList.add('active');
    tabUploadFile?.classList.remove('active');
    panelTopic?.removeAttribute('hidden');
    panelUpload?.setAttribute('hidden', '');
    confirmGenerateTopicBtn?.removeAttribute('hidden');
    confirmUploadBtn?.setAttribute('hidden', '');
    setTimeout(() => topicInput?.focus(), 50);
  } else {
    tabUploadFile?.classList.add('active');
    tabGenerateTopic?.classList.remove('active');
    panelUpload?.removeAttribute('hidden');
    panelTopic?.setAttribute('hidden', '');
    confirmUploadBtn?.removeAttribute('hidden');
    confirmGenerateTopicBtn?.setAttribute('hidden', '');
  }
}

let releaseUploadFocus = null;

function openModal() {
  resetModalState();
  uploadModal.hidden = false;
  document.body.style.overflow = 'hidden';
  releaseUploadFocus = trapFocus(uploadModal, tabUploadFile || fileInput);
}

function closeModal() {
  uploadModal.hidden = true;
  document.body.style.overflow = '';
  selectedFile = null;
  releaseUploadFocus?.();
  releaseUploadFocus = null;
}

function resetModalState() {
  selectedFile = null;
  filePreview.hidden = true;
  filePreviewName.textContent = '';
  uploadStatus.hidden = true;
  uploadError.hidden = true;
  uploadError.textContent = '';
  uploadSuccess.hidden = true;
  uploadSuccess.textContent = '';
  confirmUploadBtn.disabled = true;
  if (confirmGenerateTopicBtn) confirmGenerateTopicBtn.disabled = false;
  dropZone.classList.remove('drop-zone--active', 'drop-zone--error');
  fileInput.value = '';
  if (uploadNumQuestions) uploadNumQuestions.value = 'auto';
  if (uploadCustomQtyWrap) uploadCustomQtyWrap.setAttribute('hidden', '');
  if (uploadCustomQty) uploadCustomQty.value = '5';
  if (uploadContext) uploadContext.value = '';
  if (topicInput) topicInput.value = '';
  if (topicContext) topicContext.value = '';
  if (topicNumQuestions) topicNumQuestions.value = '5';
  if (topicCustomQtyWrap) topicCustomQtyWrap.setAttribute('hidden', '');
  if (topicCustomQty) topicCustomQty.value = '5';
  if (topicDifficulty) topicDifficulty.value = 'Médio';
  switchModalTab('upload');
}

function setFile(file) {
  const allowed = ['text/plain', 'application/pdf',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document'];
  const ext = file.name.split('.').pop().toLowerCase();
  if (!['txt', 'pdf', 'docx'].includes(ext)) {
    showUploadError(`Tipo de arquivo não suportado: .${ext}. Use TXT, PDF ou DOCX.`);
    return;
  }
  if (file.size > 20 * 1024 * 1024) {
    showUploadError('Arquivo muito grande. Máximo: 20 MB.');
    return;
  }
  selectedFile = file;
  filePreviewName.textContent = file.name;
  filePreview.hidden = false;
  dropZone.classList.remove('drop-zone--error');
  uploadError.hidden = true;
  confirmUploadBtn.disabled = false;
}

function showUploadError(msg) {
  let cleanMsg = String(msg || 'Ocorreu um erro ao processar a requisição.').trim();
  if (cleanMsg.includes('{"error"') || cleanMsg.includes('"user_id"') || cleanMsg.includes('OpenRouter')) {
    cleanMsg = 'O serviço de inteligência artificial está indisponível no momento. Por favor, tente novamente em instantes.';
  }
  uploadError.textContent = cleanMsg;
  uploadError.hidden = false;
  dropZone?.classList.add('drop-zone--error');
  if (confirmUploadBtn) confirmUploadBtn.disabled = true;
  if (confirmGenerateTopicBtn) confirmGenerateTopicBtn.disabled = false;
}

// ─── Autenticação & Sessão ──────────────────────────────────────────────────
function clearAuthToken() {
  currentUser = null;
  guestAI = null;
  clearGuestData();
  updateAuthUI();
}

/** Link para login/cadastro que traz a pessoa de volta para onde estava. */
function authHref(path, next = '/') {
  return `${path}?next=${encodeURIComponent(next)}`;
}

function sessionKind() {
  if (!currentUser) return 'visitor';
  return currentUser.role === 'guest' ? 'guest' : 'user';
}

function guestAiLabel() {
  if (!guestAI) return '';
  return `IA ${guestAI.remaining}/${guestAI.limit}`;
}

function guestAiDescription() {
  if (!guestAI) return '';
  const hours = guestAI.window_hours || 24;
  if (guestAI.remaining <= 0) {
    return `Você usou os ${guestAI.limit} usos de IA do modo convidado. A cota renova em até ${hours} horas.`;
  }
  const usos = guestAI.remaining === 1 ? 'uso' : 'usos';
  return `Modo convidado: ${guestAI.remaining} de ${guestAI.limit} ${usos} de IA restantes nas próximas ${hours} horas. Os simulados ficam só neste navegador.`;
}

function updateAuthUI() {
  const kind = sessionKind();
  const isGuest = kind === 'guest';
  document.body.dataset.session = kind;

  const userProfile = document.querySelector('#userProfile');
  const userName = document.querySelector('#userName');
  const userRoleBadge = document.querySelector('#userRoleBadge');
  const uploadVisibilityOption = document.querySelector('#uploadVisibilityOption');
  const visitorActions = document.querySelector('#visitorActions');
  const logoutBtn = document.querySelector('#logoutBtn');
  const guestActions = document.querySelector('#guestActions');
  const guestAiChip = document.querySelector('#guestAiChip');
  const guestAiNotice = document.querySelector('#guestAiNotice');
  const guestAiNoticeText = document.querySelector('#guestAiNoticeText');
  const uploadSizeLimit = document.querySelector('#uploadSizeLimit');

  if (visitorActions) visitorActions.hidden = kind !== 'visitor';

  if (currentUser) {
    if (userProfile) userProfile.hidden = false;
    if (userName) userName.textContent = currentUser.username;
    if (userRoleBadge) {
      userRoleBadge.textContent = currentUser.role;
      userRoleBadge.className = `user-role-badge role-${currentUser.role}`;
      // "Convidado" já aparece no nome; o selo só repetiria a informação
      userRoleBadge.hidden = isGuest;
    }
    // Convidado não tem conta para encerrar: oferece entrar ou cadastrar
    if (logoutBtn) logoutBtn.hidden = isGuest;
    const accountBtn = document.querySelector('#accountBtn');
    if (accountBtn) accountBtn.hidden = isGuest;
    if (guestActions) guestActions.hidden = !isGuest;
    if (uploadVisibilityOption) {
      uploadVisibilityOption.hidden = currentUser.role !== 'admin';
    }
  } else {
    if (userProfile) userProfile.hidden = true;
    if (uploadVisibilityOption) uploadVisibilityOption.hidden = true;
  }

  if (guestAiChip) {
    guestAiChip.hidden = !isGuest || !guestAI;
    guestAiChip.textContent = guestAiLabel();
    guestAiChip.title = guestAiDescription();
    guestAiChip.setAttribute('aria-label', guestAiDescription());
    guestAiChip.classList.toggle('guest-ai-chip--empty', Boolean(guestAI && guestAI.remaining <= 0));
  }
  if (guestAiNotice) {
    guestAiNotice.hidden = !isGuest;
    guestAiNotice.classList.toggle('guest-ai-notice--empty', Boolean(guestAI && guestAI.remaining <= 0));
  }
  if (guestAiNoticeText) guestAiNoticeText.textContent = guestAiDescription() || 'Modo convidado. Os simulados ficam só neste navegador.';
  if (uploadSizeLimit) uploadSizeLimit.textContent = kind === 'user' ? '20 MB' : '5 MB';

  // Convidado vê o custo antes de gastar
  if (confirmGenerateTopicBtn) {
    confirmGenerateTopicBtn.textContent = isGuest && guestAI
      ? `Gerar simulado · usa 1 de ${guestAI.remaining}`
      : 'Gerar simulado';
    if (isGuest && guestAI && guestAI.remaining <= 0) confirmGenerateTopicBtn.textContent = 'Gerar simulado';
  }

  const introLimit = document.querySelector('#introGuestAiLimit');
  if (introLimit && guestAI) introLimit.textContent = String(guestAI.limit);

  // Textos e blocos por tipo de sessão (data-show-for="visitor guest user")
  document.querySelectorAll('[data-show-for]').forEach((el) => {
    el.hidden = !el.dataset.showFor.split(/\s+/).includes(kind);
  });

  // Links de login/cadastro voltam para a home depois de entrar
  document.querySelectorAll('[data-auth-link]').forEach((link) => {
    link.setAttribute('href', authHref(link.dataset.authLink, link.dataset.next || '/'));
  });
}

function setGuestSession(ai) {
  currentUser = { id: null, username: 'Convidado', role: 'guest' };
  guestAI = ai || guestAI;
  sessionStorage.setItem('quiz_guest_mode', 'true');
}

function applyGuestStatus(ai) {
  if (!ai) return;
  guestAI = ai;
  updateAuthUI();
}

async function readJson(response) {
  try {
    return await response.json();
  } catch (_) {
    return {};
  }
}

/** Abre a sessão de convidado no servidor (cookie HttpOnly) e atualiza a interface. */
async function startGuestSession() {
  const res = await fetch('/api/guest/start', { method: 'POST', credentials: 'same-origin' });
  const raw = await readJson(res);
  if (res.status === 409) {
    // Já existe uma conta conectada nesta aba (ex.: login em outra aba)
    await checkAuth();
    return;
  }
  if (!res.ok) {
    throw new Error(raw.message || 'Não foi possível abrir o modo convidado.');
  }
  const data = raw.data || raw;
  setGuestSession(data.ai);
  updateAuthUI();
}

/**
 * Depois do login/cadastro, os simulados criados como convidado (ainda na aba)
 * vão para a conta. Falhou? Ficam na aba para uma nova tentativa no próximo carregamento.
 */
let importedGuestQuizzes = 0;
async function importGuestQuizzesIntoAccount() {
  const pending = getGuestQuizzes().filter((q) => Array.isArray(q?.questions) && q.questions.length);
  if (!pending.length) return;
  try {
    const res = await fetch('/api/quizzes/import', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'same-origin',
      body: JSON.stringify({ quizzes: pending.slice(0, 20) }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const raw = await readJson(res);
    importedGuestQuizzes = (raw.data || raw).imported || 0;
  } catch (err) {
    console.warn('Não foi possível salvar os simulados do convidado na conta:', err);
    throw err;
  }
}

async function checkAuth() {
  const wantsGuest = window.location.pathname === '/guest';
  const [meResult, guestResult] = await Promise.allSettled([
    fetch('/api/auth/me', { cache: 'no-store', credentials: 'same-origin' }),
    fetch('/api/guest/status', { cache: 'no-store', credentials: 'same-origin' }),
  ]);

  try {
    const meRes = meResult.status === 'fulfilled' ? meResult.value : null;
    if (meRes && meRes.ok) {
      const raw = await readJson(meRes);
      currentUser = raw.data?.user || raw.user || null;
      if (currentUser) {
        guestAI = null;
        try {
          await importGuestQuizzesIntoAccount();
          clearGuestData();
        } catch (_) {
          sessionStorage.removeItem('quiz_guest_mode');
        }
        return true;
      }
    }

    const guestRes = guestResult.status === 'fulfilled' ? guestResult.value : null;
    const guestRaw = guestRes && guestRes.ok ? await readJson(guestRes) : {};
    const guestData = guestRaw.data || guestRaw;
    guestAI = guestData.ai || null;

    if (guestData.active) {
      setGuestSession(guestData.ai);
    } else if (wantsGuest) {
      // Link antigo /guest: abre o modo convidado direto
      try {
        await startGuestSession();
      } catch (err) {
        console.warn('Não foi possível iniciar o modo convidado:', err);
        currentUser = null;
        clearGuestData();
      }
    } else {
      currentUser = null;
      clearGuestData();
    }
    return true;
  } catch (err) {
    console.warn('Erro ao validar sessão:', err);
    currentUser = null;
    return true;
  } finally {
    sessionResolved = true;
    if (wantsGuest) {
      history.replaceState(history.state, '', `/${window.location.search}${window.location.hash}`);
    }
    updateAuthUI();
  }
}

// ─── Modal de acesso: conta grátis ou convidado ─────────────────────────────
// Só aparece quando a pessoa tenta uma ação que precisa de identidade (criar
// simulado, usar a IA). Navegar e resolver simulados prontos é livre.
const accessModal = document.querySelector('#accessModal');
const accessModalBadge = document.querySelector('#accessModalBadge');
const accessModalTitle = document.querySelector('#accessModalTitle');
const accessModalText = document.querySelector('#accessModalText');
const accessGuestOption = document.querySelector('#accessGuestOption');
const accessGuestBtn = document.querySelector('#accessGuestBtn');
const accessFeedback = document.querySelector('#accessFeedback');
const accessOptions = document.querySelector('#accessOptions');
let pendingAccessAction = null;
let releaseAccessFocus = null;

const ACCESS_COPY = {
  create: {
    badge: 'Grátis',
    title: 'Crie simulados com IA',
    text: 'Escolha como continuar. A conta grátis guarda seus simulados e seu histórico em qualquer dispositivo. No modo convidado você testa agora, sem cadastro.',
    next: '/?abrir=criar',
  },
  remix: {
    badge: 'Grátis',
    title: 'Gere novas questões a partir dos seus erros',
    text: 'A IA cria variações inéditas das questões que você errou. Entre na sua conta ou continue como convidado para usar agora.',
    next: '/',
  },
  limit: {
    badge: 'Limite do convidado',
    title: 'Você usou as gerações grátis',
    text: '',
    next: '/?abrir=criar',
  },
};

function openAccessModal(reason = 'create', onGranted = null) {
  if (!accessModal) return;
  const copy = ACCESS_COPY[reason] || ACCESS_COPY.create;
  const isLimit = reason === 'limit';
  pendingAccessAction = isLimit ? null : onGranted;

  if (accessModalBadge) accessModalBadge.textContent = copy.badge;
  if (accessModalTitle) {
    accessModalTitle.textContent = isLimit && guestAI
      ? `Você usou as ${guestAI.limit} gerações grátis`
      : copy.title;
  }
  if (accessModalText) {
    accessModalText.textContent = isLimit
      ? `Crie uma conta grátis para continuar agora. Os simulados que você já criou continuam neste navegador, e a cota do convidado renova em até ${guestAI?.window_hours || 24} horas.`
      : copy.text;
  }
  if (accessGuestOption) accessGuestOption.hidden = isLimit;
  accessOptions?.classList.toggle('access-options--single', isLimit);
  accessModal.querySelector('.modal--access')?.classList.toggle('modal--access-compact', isLimit);
  accessModalBadge?.classList.toggle('access-badge--warning', isLimit);
  const limit = guestAI?.limit ?? 3;
  const windowHours = guestAI?.window_hours ?? 24;
  const limitEl = document.querySelector('#accessGuestLimit');
  const windowEl = document.querySelector('#accessGuestWindow');
  if (limitEl) limitEl.textContent = String(limit);
  if (windowEl) windowEl.textContent = String(windowHours);
  if (accessFeedback) {
    accessFeedback.hidden = true;
    accessFeedback.textContent = '';
  }
  accessModal.querySelectorAll('[data-auth-link]').forEach((link) => {
    link.dataset.next = copy.next;
    link.setAttribute('href', authHref(link.dataset.authLink, copy.next));
  });
  if (accessGuestBtn) accessGuestBtn.disabled = false;

  accessModal.hidden = false;
  document.body.style.overflow = 'hidden';
  releaseAccessFocus = trapFocus(accessModal, document.querySelector('#accessRegisterLink'));
}

function closeAccessModal() {
  if (!accessModal || accessModal.hidden) return;
  accessModal.hidden = true;
  // Pode ter sido aberto por cima do resultado: só libera a rolagem se nada mais estiver aberto
  const otherOpen = [...document.querySelectorAll('.modal-overlay')].some((m) => !m.hidden);
  if (!otherOpen) document.body.style.overflow = '';
  pendingAccessAction = null;
  releaseAccessFocus?.();
  releaseAccessFocus = null;
}

/**
 * Executa `action` se a sessão permite usar a IA; senão abre o modal de acesso.
 * Conta: sempre. Convidado: enquanto houver cota. Visitante: escolhe primeiro.
 */
function requireAiAccess(action, reason = 'create') {
  const kind = sessionKind();
  if (kind === 'user') return action();
  if (kind === 'guest') {
    if (guestAI && guestAI.remaining <= 0) {
      openAccessModal('limit');
      return undefined;
    }
    return action();
  }
  openAccessModal(reason, action);
  return undefined;
}

/** Trata respostas de erro dos endpoints de IA. Retorna true se já cuidou da situação. */
function handleAccessError(raw, reason = 'create') {
  const code = raw?.error;
  if (code === 'GUEST_AI_LIMIT_REACHED') {
    if (guestAI) guestAI = { ...guestAI, remaining: 0, used: guestAI.limit };
    updateAuthUI();
    closeModal();
    openAccessModal('limit');
    return true;
  }
  if (code === 'AUTH_REQUIRED') {
    // A sessão expirou ou o convidado apagou os cookies: volta a ser visitante
    currentUser = null;
    clearGuestData();
    updateAuthUI();
    closeModal();
    openAccessModal(reason);
    return true;
  }
  return false;
}

accessGuestBtn?.addEventListener('click', async () => {
  const action = pendingAccessAction;
  accessGuestBtn.disabled = true;
  try {
    await startGuestSession();
    closeAccessModal();
    await loadQuizList().catch(() => {});
    if (typeof action === 'function') {
      if (guestAI && guestAI.remaining <= 0) {
        openAccessModal('limit');
      } else {
        action();
      }
    }
  } catch (err) {
    if (accessFeedback) {
      accessFeedback.textContent = `${err.message} Tente novamente em alguns minutos ou crie uma conta grátis.`;
      accessFeedback.hidden = false;
    }
    accessGuestBtn.disabled = false;
  }
});
document.querySelector('#closeAccessModal')?.addEventListener('click', closeAccessModal);
accessModal?.addEventListener('click', (e) => { if (e.target === accessModal) closeAccessModal(); });

// ─── Minha conta: cópia dos dados e exclusão (LGPD) ─────────────────────────
const accountModal = document.querySelector('#accountModal');
const deleteAccountForm = document.querySelector('#deleteAccountForm');
const deleteAccountPassword = document.querySelector('#deleteAccountPassword');
const deleteAccountFeedback = document.querySelector('#deleteAccountFeedback');
const deleteAccountBtn = document.querySelector('#deleteAccountBtn');
let releaseAccountFocus = null;

const accountEmailStatus = document.querySelector('#accountEmailStatus');
const accountEmailFeedback = document.querySelector('#accountEmailFeedback');
const accountResendBtn = document.querySelector('#accountResendVerification');

function renderAccountEmail() {
  const addressEl = document.querySelector('#accountEmailAddress');
  if (addressEl) addressEl.textContent = currentUser?.email || '';
  const verified = Boolean(currentUser?.email_verified);
  if (accountEmailStatus) {
    accountEmailStatus.textContent = verified
      ? 'Seu e-mail está confirmado.'
      : 'Seu e-mail ainda não foi confirmado. Confirme pelo link que enviamos para proteger sua conta e receber a recuperação de senha.';
  }
  if (accountResendBtn) accountResendBtn.hidden = verified;
  if (accountEmailFeedback) accountEmailFeedback.hidden = true;
}

accountResendBtn?.addEventListener('click', async () => {
  accountResendBtn.disabled = true;
  const showFeedback = (msg, ok) => {
    if (!accountEmailFeedback) return;
    accountEmailFeedback.textContent = msg;
    accountEmailFeedback.className = `form-feedback ${ok ? 'feedback-success' : 'feedback-error'}`;
    accountEmailFeedback.hidden = false;
  };
  try {
    const res = await fetch('/api/auth/resend-verification', { method: 'POST', credentials: 'same-origin' });
    const raw = await readJson(res);
    if (res.status === 429) {
      showFeedback('Muitas tentativas seguidas. Aguarde alguns minutos.', false);
    } else if (!res.ok) {
      showFeedback(raw.message || 'Não foi possível enviar o link agora. Tente novamente mais tarde.', false);
    } else {
      if (raw.data?.already_verified && currentUser) {
        currentUser.email_verified = true;
        renderAccountEmail();
      }
      showFeedback(raw.message || 'Enviamos um novo link de confirmação para o seu e-mail.', true);
    }
  } catch (_) {
    showFeedback('Falha na conexão. Tente novamente.', false);
  } finally {
    accountResendBtn.disabled = false;
  }
});

function openAccountModal() {
  if (!accountModal || sessionKind() !== 'user') return;
  const nameEl = document.querySelector('#accountUsername');
  if (nameEl) nameEl.textContent = currentUser.username;
  renderAccountEmail();
  if (deleteAccountPassword) deleteAccountPassword.value = '';
  if (deleteAccountFeedback) deleteAccountFeedback.hidden = true;
  accountModal.hidden = false;
  document.body.style.overflow = 'hidden';
  releaseAccountFocus = trapFocus(accountModal, document.querySelector('#accountExportLink'));
}

function closeAccountModal() {
  if (!accountModal || accountModal.hidden) return;
  accountModal.hidden = true;
  document.body.style.overflow = '';
  releaseAccountFocus?.();
  releaseAccountFocus = null;
}

document.querySelector('#accountBtn')?.addEventListener('click', openAccountModal);
document.querySelector('#footerAccountBtn')?.addEventListener('click', openAccountModal);
document.querySelector('#closeAccountModal')?.addEventListener('click', closeAccountModal);
accountModal?.addEventListener('click', (e) => { if (e.target === accountModal) closeAccountModal(); });
accountModal?.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeAccountModal(); });

deleteAccountForm?.addEventListener('submit', async (e) => {
  e.preventDefault();
  const password = deleteAccountPassword?.value || '';
  const showError = (msg) => {
    if (!deleteAccountFeedback) return;
    deleteAccountFeedback.textContent = msg;
    deleteAccountFeedback.hidden = false;
  };
  if (!password) {
    showError('Digite sua senha para confirmar.');
    deleteAccountPassword?.focus();
    return;
  }
  deleteAccountBtn.disabled = true;
  try {
    const res = await fetch('/api/account/delete', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'same-origin',
      body: JSON.stringify({ password }),
    });
    const raw = await readJson(res);
    if (!res.ok) {
      showError(raw.message || 'Não foi possível excluir a conta. Tente novamente.');
      return;
    }
    clearAuthToken();
    closeAccountModal();
    await showNotice('Sua conta e seus dados foram excluídos.', 'Conta excluída', 'info');
    window.location.replace('/');
  } catch (_) {
    showError('Falha na conexão. Tente novamente.');
  } finally {
    deleteAccountBtn.disabled = false;
  }
});

// ─── Logout ─────────────────────────────────────────────────────────────────
// Sair da conta volta para a home como visitante (sem muro de login).
document.querySelector('#logoutBtn')?.addEventListener('click', async () => {
  try {
    await fetch('/api/auth/logout', {
      method: 'POST',
      credentials: 'same-origin'
    });
  } catch (_) {}
  clearAuthToken();
  window.location.replace('/');
});

// ─── Upload de Arquivos (Protegido para usuários autenticados) ─────────────
async function doUpload() {
  if (!selectedFile) return;

  uploadStatus.hidden = false;
  uploadStatusText.textContent = 'Enviando arquivo…';
  uploadError.hidden = true;
  uploadSuccess.hidden = true;
  confirmUploadBtn.disabled = true;

  const formData = new FormData();
  formData.append('file', selectedFile, selectedFile.name);
  formData.append('is_public', document.querySelector('#isPublicQuiz')?.checked ? 'true' : 'false');

  let uploadQty = uploadNumQuestions?.value || 'auto';
  if (uploadQty === 'custom') {
    uploadQty = String(Math.max(1, Math.min(Number(uploadCustomQty?.value) || 5, 30)));
  }
  formData.append('num_questions', uploadQty);
  formData.append('language', getLanguage());

  const userContext = uploadContext?.value?.trim() || '';
  if (userContext) {
    formData.append('context', userContext);
  }

  try {
    uploadStatusText.textContent = 'Processando… (pode levar alguns segundos se usar IA)';
    const response = await fetch('/api/upload', {
      method: 'POST',
      credentials: 'same-origin',
      body: formData
    });
    const raw = await readJson(response);
    const data = raw.data || raw;

    if (!response.ok) {
      uploadStatus.hidden = true;
      confirmUploadBtn.disabled = false;
      if (handleAccessError(raw, 'create')) return;
      showUploadError(data.message || 'Não foi possível processar o arquivo. Tente novamente.');
      return;
    }

    if (data.guest_ai) applyGuestStatus(data.guest_ai);
    if (data.local_only || isGuestMode()) {
      saveGuestQuiz(data);
    }

    uploadStatus.hidden = true;
    uploadSuccess.textContent = `✓ ${data.message}`;
    uploadSuccess.hidden = false;

    // Recarregar lista e selecionar novo quiz
    await loadQuizList();
    selectedSource = data.name;
    quizSelector.value = data.name;
    syncCustomQuizSelector();
    resetTimer();
    closeResultModal();
    quiz.innerHTML = '';
    try { await loadQuiz(data.name); } catch (_) {}

    setTimeout(closeModal, 1800);
  } catch (err) {
    showUploadError('Falha na conexão. Verifique o servidor e tente novamente.');
    uploadStatus.hidden = true;
    confirmUploadBtn.disabled = false;
  }
}

// ─── Geração por Tema com IA ───────────────────────────────────────────────
async function doGenerateTopic() {
  const topic = topicInput?.value.trim();
  if (!topic) {
    showUploadError('Por favor, informe o tema ou assunto do quiz.');
    topicInput?.focus();
    return;
  }

  if (sessionKind() === 'guest' && guestAI && guestAI.remaining <= 0) {
    closeModal();
    openAccessModal('limit');
    return;
  }

  uploadStatus.hidden = false;
  uploadStatusText.textContent = 'A IA está elaborando as questões e o gabarito…';
  uploadError.hidden = true;
  uploadSuccess.hidden = true;
  confirmGenerateTopicBtn.disabled = true;

  let topicQty = Number(topicNumQuestions?.value) || 5;
  if (topicNumQuestions?.value === 'custom') {
    topicQty = Math.max(1, Math.min(Number(topicCustomQty?.value) || 5, 30));
  }

  const payload = {
    topic,
    num_questions: topicQty,
    difficulty: topicDifficulty?.value || 'Médio',
    context: topicContext?.value.trim() || '',
    is_public: document.querySelector('#isPublicQuiz')?.checked || false,
    language: getLanguage(),
  };

  try {
    const response = await fetch('/api/quiz/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'same-origin',
      body: JSON.stringify(payload),
    });

    const raw = await readJson(response);
    const data = raw.data || raw;

    if (!response.ok) {
      uploadStatus.hidden = true;
      confirmGenerateTopicBtn.disabled = false;
      if (handleAccessError(raw, 'create')) return;
      showUploadError(data.message || 'Não foi possível gerar o simulado. Tente novamente.');
      return;
    }

    if (data.guest_ai) applyGuestStatus(data.guest_ai);
    if (data.local_only || isGuestMode()) {
      saveGuestQuiz(data);
    }

    uploadStatus.hidden = true;
    uploadSuccess.textContent = `✓ ${data.message || 'Simulado gerado.'}`;
    uploadSuccess.hidden = false;

    // Recarregar lista e selecionar novo quiz
    await loadQuizList();
    selectedSource = data.name;
    quizSelector.value = data.name;
    syncCustomQuizSelector();
    resetTimer();
    closeResultModal();
    quiz.innerHTML = '';
    try { await loadQuiz(data.name); } catch (_) {}

    setTimeout(closeModal, 1400);
  } catch (err) {
    showUploadError('Falha na conexão. Verifique o servidor ou a chave de IA.');
    uploadStatus.hidden = true;
    confirmGenerateTopicBtn.disabled = false;
  }
}

// Eventos do modal de upload / geração
document.querySelector('#addQuizBtn').addEventListener('click', () => {
  // Visitante escolhe entre conta grátis e convidado; convidado sem cota ainda
  // pode enviar arquivos com gabarito (não usam IA), então o modal abre normalmente.
  if (sessionKind() === 'visitor') {
    openAccessModal('create', openModal);
  } else {
    openModal();
  }
});
document.querySelector('#closeModal').addEventListener('click', closeModal);
document.querySelector('#cancelUpload').addEventListener('click', closeModal);
confirmUploadBtn.addEventListener('click', doUpload);
confirmGenerateTopicBtn?.addEventListener('click', doGenerateTopic);

tabUploadFile?.addEventListener('click', () => switchModalTab('upload'));

// Temas de exemplo: preenchem o campo para o primeiro simulado sair em um clique
document.querySelectorAll('.topic-chip').forEach((chip) => {
  chip.addEventListener('click', () => {
    if (!topicInput) return;
    topicInput.value = chip.dataset.topic || chip.textContent.trim();
    topicInput.focus();
  });
});
tabGenerateTopic?.addEventListener('click', () => switchModalTab('topic'));

topicInput?.addEventListener('keydown', (e) => {
  if (e.key === 'Enter') {
    e.preventDefault();
    doGenerateTopic();
  }
});

// Fechar clicando fora
uploadModal.addEventListener('click', (e) => { if (e.target === uploadModal) closeModal(); });
resultModal?.addEventListener('click', (e) => { if (e.target === resultModal) closeResultModal(); });
aboutModal?.addEventListener('click', (e) => { if (e.target === aboutModal) closeAboutModal(); });
catalogModal?.addEventListener('click', (e) => { if (e.target === catalogModal) closeCatalogModal(); });

// Fechar com Escape
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    if (uploadModal && !uploadModal.hidden) closeModal();
    if (resultModal && !resultModal.hidden) closeResultModal();
    if (aboutModal && !aboutModal.hidden) closeAboutModal();
    if (catalogModal && !catalogModal.hidden) closeCatalogModal();
    if (accessModal && !accessModal.hidden) closeAccessModal();
  }
});

// Remover arquivo selecionado
document.querySelector('#removeFile').addEventListener('click', () => {
  selectedFile = null;
  filePreview.hidden = true;
  filePreviewName.textContent = '';
  confirmUploadBtn.disabled = true;
  fileInput.value = '';
});

// Drag & Drop
dropZone.addEventListener('click', () => fileInput.click());
dropZone.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') fileInput.click(); });

dropZone.addEventListener('dragover', (e) => { e.preventDefault(); dropZone.classList.add('drop-zone--active'); });
dropZone.addEventListener('dragleave', () => dropZone.classList.remove('drop-zone--active'));
dropZone.addEventListener('drop', (e) => {
  e.preventDefault();
  dropZone.classList.remove('drop-zone--active');
  const file = e.dataTransfer.files[0];
  if (file) setFile(file);
});

fileInput.addEventListener('change', () => {
  const file = fileInput.files[0];
  if (file) setFile(file);
});

// ─── Inicialização ────────────────────────────────────────────────────────────
resetTimer();

async function init() {
  initTheme();
  initTimerDrag(timer, timerConfig);

  initShortcuts({
    onNextQuestion: () => {
      if (currentQuestionIndex < questions.length - 1) {
        goToQuestion(currentQuestionIndex + 1);
      }
    },
    onPrevQuestion: () => {
      if (currentQuestionIndex > 0) {
        goToQuestion(currentQuestionIndex - 1);
      }
    },
    onSelectOption: (qIndex, optIndex) => {
      const card = document.querySelector(`#question-card-${qIndex}`);
      if (!card) return;
      const radio = card.querySelectorAll('input[type="radio"]')[optIndex];
      if (radio) {
        radio.checked = true;
        radio.dispatchEvent(new Event('change', { bubbles: true }));
        const optionLabel = radio.closest('.option');
        if (optionLabel) {
          optionLabel.classList.remove('option--hotkey-pulse');
          void optionLabel.offsetWidth;
          optionLabel.classList.add('option--hotkey-pulse');
        }
      }
    },
    onSubmitQuiz: () => {
      btnQuickSubmit?.click();
    },
    onCloseModals: () => {
      closeAccessModal();
      closeCatalogModal();
      closeResultModal();
      closeAboutModal();
      const uploadModalEl = document.querySelector('#uploadModal');
      if (uploadModalEl) uploadModalEl.hidden = true;
      if (confirmSubmitModal) confirmSubmitModal.hidden = true;
      document.body.style.overflow = '';
    },
    getViewMode: () => viewMode,
    getCurrentQuestionIndex: () => currentQuestionIndex,
    getQuestionsCount: () => questions.length,
  });

  // Sessão, quiz e lista em paralelo: a home é aberta a todos e o cookie vai em
  // todas as requisições, então não é preciso esperar a sessão para buscar os dados.
  const assumedGuest = isGuestMode();
  const authPromise = checkAuth();
  const dataPromise = Promise.all([loadQuiz(), loadQuizList()]);
  await authPromise;

  // Volta do login/cadastro com intenção de criar simulado (?abrir=criar):
  // abre assim que a sessão é conhecida, sem esperar a lista de simulados
  const params = new URLSearchParams(window.location.search);
  if (params.get('abrir') === 'criar') {
    params.delete('abrir');
    const query = params.toString();
    history.replaceState(history.state, '', `${window.location.pathname}${query ? `?${query}` : ''}${window.location.hash}`);
    if (sessionKind() === 'visitor') {
      openAccessModal('create', openModal);
    } else {
      openModal();
    }
  }

  // Volta do link de confirmação de e-mail (/api/auth/verify-email redireciona com ?email=)
  const emailResult = params.get('email');
  if (emailResult) {
    params.delete('email');
    const query = params.toString();
    history.replaceState(history.state, '', `${window.location.pathname}${query ? `?${query}` : ''}${window.location.hash}`);
    if (emailResult === 'confirmado') {
      if (currentUser && sessionKind() === 'user') currentUser.email_verified = true;
      showNotice('Seu e-mail foi confirmado.', 'E-mail confirmado', 'info');
    } else if (emailResult === 'link_invalido') {
      showNotice('Este link de confirmação é inválido, já foi usado ou venceu. Entre na sua conta e peça um novo em Minha conta.', 'Confirmação de e-mail', 'info');
    } else if (emailResult === 'muitas_tentativas') {
      showNotice('Muitas tentativas seguidas. Aguarde alguns minutos.', 'Confirmação de e-mail', 'info');
    }
  }

  if (importedGuestQuizzes > 0) {
    const plural = importedGuestQuizzes === 1 ? 'simulado do modo convidado foi salvo' : 'simulados do modo convidado foram salvos';
    showNotice(`${importedGuestQuizzes} ${plural} na sua conta.`, 'Simulados salvos', 'info');
  }

  try {
    await dataPromise;
    // A sessão real difere do que a aba supunha (ex.: cookie de convidado expirou)
    if (isGuestMode() !== assumedGuest || importedGuestQuizzes > 0) await loadQuizList();
  } catch (error) {
    if (error.name !== 'AbortError') {
      quiz.innerHTML = '<p class="empty-state">Escolha um simulado em "Explorar simulados" ou crie o seu em "Criar simulado".</p>';
      await loadQuizList().catch(() => {});
    }
  }

}

init();

