// ─── Estado global ────────────────────────────────────────────────────────────
const quiz = document.querySelector('#quiz');
const result = document.querySelector('#result');
const progress = document.querySelector('#progress');
const percent = document.querySelector('#percent');
const progressBar = document.querySelector('#progressBar');
const quizSelector = document.querySelector('#quizSelector');
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
    }
    function onOverlayClick(e) {
      if (e.target === confirmSubmitModal) onCancel();
    }

    confirmSubmitConfirm?.addEventListener('click', onConfirm);
    confirmSubmitCancel?.addEventListener('click', onCancel);
    confirmSubmitModal?.addEventListener('click', onOverlayClick);
  });
}

function openCatalogModal() {
  if (catalogModal) {
    catalogModal.hidden = false;
    document.body.style.overflow = 'hidden';
    renderCatalogList();
    if (catalogSearchInput) {
      setTimeout(() => catalogSearchInput.focus(), 100);
    }
  }
}

function closeCatalogModal() {
  if (catalogModal) {
    catalogModal.hidden = true;
    document.body.style.overflow = '';
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
function openResultModal() {
  if (resultModal) {
    resultModal.hidden = false;
    document.body.style.overflow = 'hidden';
  }
}

function closeResultModal() {
  if (resultModal) {
    resultModal.hidden = true;
    document.body.style.overflow = '';
  }
}

// ─── Modal Explicativo: Por que o Quiz Study? ──────────────────────────────────
const aboutModal = document.querySelector('#aboutModal');
const btnOpenAboutModal = document.querySelector('#btnOpenAboutModal');
const closeAboutModalBtn = document.querySelector('#closeAboutModal');
const btnCloseAbout = document.querySelector('#btnCloseAbout');

function openAboutModal() {
  if (aboutModal) {
    aboutModal.hidden = false;
    document.body.style.overflow = 'hidden';
  }
}

function closeAboutModal() {
  if (aboutModal) {
    aboutModal.hidden = true;
    document.body.style.overflow = '';
  }
}

let currentWrongQuestions = [];

let questions = [];
let selectedSource = '';
let loadRequestId = 0;
let loadController;
let remainingSeconds = 24 * 60; // valor padrão; recalculado em resetTimer()
let timerInterval;

function isGuestMode() {
  return window.location.pathname === '/guest' || sessionStorage.getItem('quiz_guest_mode') === 'true';
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

timerPreset?.addEventListener('change', () => {
  const val = timerPreset.value;

  if (val === 'auto') {
    customTimerSeconds = null;
  } else if (val === 'custom') {
    const raw = prompt('Informe o tempo desejado em minutos (ex: 35):');
    const mins = parseInt(raw, 10);
    if (!isNaN(mins) && mins > 0 && mins <= 300) {
      customTimerSeconds = mins * 60;
      // Adiciona opção temporária para mostrar o valor escolhido
      const existingCustom = timerPreset.querySelector('[value="custom-set"]');
      if (existingCustom) existingCustom.remove();
      const opt = document.createElement('option');
      opt.value = 'custom-set';
      opt.textContent = `${mins} min ✎`;
      timerPreset.insertBefore(opt, timerPreset.querySelector('[value="custom"]'));
      timerPreset.value = 'custom-set';
    } else {
      if (raw !== null) alert('Por favor, informe um número entre 1 e 300 minutos.');
      // Reverter para a seleção anterior
      timerPreset.value = customTimerSeconds !== null ? 'custom-set' : 'auto';
      return;
    }
  } else {
    customTimerSeconds = parseInt(val, 10);
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
    cache: 'no-store',
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
          <label class="option">
            <input type="radio" name="q-${item.id}" value="${i}">
            <span>${String.fromCharCode(65 + i)}) ${escapeHtml(option)}</span>
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
      btnNextQuestion.innerHTML = '🏁 Finalizar Simulado';
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
    const response = await fetch('/api/quizzes', { cache: 'no-store' });
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
    return;
  }

  let html = '';
  if (serverQuizzes.length > 0) {
    html += '<optgroup label="Quizzes da Plataforma">';
    html += serverQuizzes.map((item) =>
      `<option value="${escapeHtml(item.name)}">
        ${escapeHtml(item.label)}${item.ai_generated ? ' 🤖' : ''}
      </option>`
    ).join('');
    html += '</optgroup>';
  }

  if (localQuizzes.length > 0) {
    html += '<optgroup label="Seus Quizzes Gerados (Convidado)">';
    html += localQuizzes.map((item) =>
      `<option value="${escapeHtml(item.name)}">
        ${escapeHtml(item.label)} ✨
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
}

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
      btnQuickSubmit.textContent = `🏁 Finalizar (${count}/${questions.length})`;
    } else {
      btnQuickSubmit.textContent = '🏁 Finalizar Simulado';
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
    alert('Por favor, marque pelo menos uma resposta antes de conferir.');
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
    if (result) {
      result.hidden = true;
      result.innerHTML = '';
    }
    renderResultModal(data);
    openResultModal();
  } catch (err) {
    alert('Erro ao conferir respostas. Verifique a conexão com o servidor.');
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
      resultScoreBadge.textContent = '🎯 Excelente!';
    } else if (percentage >= 60) {
      resultScoreBadge.classList.add('good');
      resultScoreBadge.textContent = '👍 Bom trabalho!';
    } else {
      resultScoreBadge.classList.add('practice');
      resultScoreBadge.textContent = '💡 Continue praticando!';
    }
  }

  if (resultSummaryText) {
    if (percentage >= 80) {
      resultSummaryText.textContent = 'Parabéns! Excelente domínio do conteúdo abordado.';
    } else if (percentage >= 60) {
      resultSummaryText.textContent = 'Muito bom! Você acertou a maior parte das questões.';
    } else {
      resultSummaryText.textContent = 'Revise detalhadamente cada questão abaixo e tente novamente.';
    }
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
            <strong>💡 Explicação Didática</strong>
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
  if (result) {
    result.hidden = true;
    result.innerHTML = '';
  }
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

// Gerar Variações Inéditas com IA
btnRemixMistakes?.addEventListener('click', async () => {
  if (!currentWrongQuestions.length) return;

  const originalContent = btnRemixMistakes.innerHTML;
  btnRemixMistakes.disabled = true;
  btnRemixMistakes.innerHTML = '<span>⏳</span> Criando variações com IA…';

  try {
    const response = await fetch('/api/quiz/remix-mistakes', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'same-origin',
      body: JSON.stringify({ questions: currentWrongQuestions }),
    });

    const raw = await response.json();
    if (!response.ok) {
      throw new Error(raw?.data?.message || raw?.message || 'Erro ao comunicar com a IA');
    }

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
    alert(`Erro ao gerar variações com IA: ${err.message}`);
  } finally {
    btnRemixMistakes.disabled = false;
    btnRemixMistakes.innerHTML = originalContent;
  }
});

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

// Navegação rápida por teclado (Setas Esquerda / Direita no Modo Foco)
document.addEventListener('keydown', (e) => {
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.isContentEditable) return;
  if (viewMode !== 'focus' || !questions.length) return;
  if (uploadModal && !uploadModal.hidden) return;
  if (resultModal && !resultModal.hidden) return;
  if (aboutModal && !aboutModal.hidden) return;
  if (catalogModal && !catalogModal.hidden) return;

  if (e.key === 'ArrowRight') {
    if (currentQuestionIndex < questions.length - 1) {
      goToQuestion(currentQuestionIndex + 1);
    }
  } else if (e.key === 'ArrowLeft') {
    if (currentQuestionIndex > 0) {
      goToQuestion(currentQuestionIndex - 1);
    }
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
      ? '✨ IA'
      : (item.file_type ? item.file_type.toUpperCase() : (item.is_guest ? 'LOCAL' : 'OFICIAL'));

    return `
      <div class="catalog-card" data-source="${escapeHtml(item.name)}">
        <div class="catalog-card-header">
          <h3 class="catalog-card-title">${escapeHtml(item.label)}</h3>
          <span class="catalog-card-badge ${item.ai_generated ? 'ai' : ''}">${badgeLabel}</span>
        </div>
        <div class="catalog-card-meta">
          <span>📝 ${count} questões</span>
          <span>⏱️ ~${estMinutes} min</span>
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
  resetTimer();
  closeResultModal();
  if (result) {
    result.hidden = true;
    result.innerHTML = '';
  }
  quiz.innerHTML = '';

  try {
    await loadQuiz(source);
    startTimer();
    const firstQuestion = quiz.querySelector('.question');
    if (firstQuestion) {
      firstQuestion.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  } catch (err) {
    alert('Erro ao carregar o simulado selecionado.');
  }
});

quiz.addEventListener('change', () => {
  startTimer();
  updateProgress();
});

quizSelector.addEventListener('change', async () => {
  resetTimer();
  closeResultModal();
  if (result) {
    result.hidden = true;
    result.innerHTML = '';
  }
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
const topicDifficulty = document.querySelector('#topicDifficulty');
const topicContext = document.querySelector('#topicContext');

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

function openModal() {
  resetModalState();
  uploadModal.hidden = false;
  document.body.style.overflow = 'hidden';
  uploadModal.querySelector('.modal').focus?.();
}

function closeModal() {
  uploadModal.hidden = true;
  document.body.style.overflow = '';
  selectedFile = null;
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
  if (topicInput) topicInput.value = '';
  if (topicContext) topicContext.value = '';
  if (topicNumQuestions) topicNumQuestions.value = '5';
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
let currentUser = null;

function clearAuthToken() {
  currentUser = null;
  clearGuestData();
  updateAuthUI();
}

function updateAuthUI() {
  const userProfile = document.querySelector('#userProfile');
  const userName = document.querySelector('#userName');
  const userRoleBadge = document.querySelector('#userRoleBadge');
  const uploadVisibilityOption = document.querySelector('#uploadVisibilityOption');

  if (currentUser) {
    if (userProfile) userProfile.hidden = false;
    if (userName) userName.textContent = currentUser.username;
    if (userRoleBadge) {
      userRoleBadge.textContent = currentUser.role;
      userRoleBadge.className = `user-role-badge role-${currentUser.role}`;
    }
    if (uploadVisibilityOption) {
      uploadVisibilityOption.hidden = currentUser.role !== 'admin';
    }
  } else {
    if (userProfile) userProfile.hidden = true;
    if (uploadVisibilityOption) uploadVisibilityOption.hidden = true;
  }
}

async function checkAuth() {
  if (window.location.pathname === '/guest') {
    currentUser = { id: null, username: 'Convidado', role: 'guest' };
    updateAuthUI();
    return true;
  }

  clearGuestData();

  try {
    const res = await fetch('/api/auth/me', {
      cache: 'no-store',
      credentials: 'same-origin'
    });
    if (res.ok) {
      const raw = await res.json();
      currentUser = raw.data?.user || raw.user;
      updateAuthUI();
      return true;
    } else {
      clearAuthToken();
      window.location.replace('/login');
      return false;
    }
  } catch (err) {
    console.warn('Erro ao validar sessão:', err);
    clearAuthToken();
    window.location.replace('/login');
    return false;
  }
}

// ─── Logout ─────────────────────────────────────────────────────────────────
document.querySelector('#logoutBtn')?.addEventListener('click', async () => {
  clearGuestData();
  if (isGuestMode()) {
    clearAuthToken();
    window.location.replace('/login');
    return;
  }
  try {
    await fetch('/api/auth/logout', {
      method: 'POST',
      credentials: 'same-origin'
    });
  } catch (_) {}
  clearAuthToken();
  window.location.replace('/login');
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

  try {
    uploadStatusText.textContent = 'Processando… (pode levar alguns segundos se usar IA)';
    const response = await fetch(`/api/upload${isGuestMode() ? '?guest=1' : ''}`, {
      method: 'POST',
      body: formData
    });
    const raw = await response.json();
    const data = raw.data || raw;

    if (!response.ok) {
      if (response.status === 401 || response.status === 403) {
        showUploadError(data.message || 'Faça login para enviar um quiz.');
      } else {
        showUploadError(data.message || data.error || 'Erro ao processar o arquivo.');
      }
      uploadStatus.hidden = true;
      confirmUploadBtn.disabled = false;
      return;
    }

    if (isGuestMode()) {
      saveGuestQuiz(data);
    }

    uploadStatus.hidden = true;
    uploadSuccess.textContent = `✓ ${data.message}`;
    uploadSuccess.hidden = false;

    // Recarregar lista e selecionar novo quiz
    await loadQuizList();
    selectedSource = data.name;
    quizSelector.value = data.name;
    resetTimer();
    closeResultModal();
    if (result) {
      result.hidden = true;
      result.innerHTML = '';
    }
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

  uploadStatus.hidden = false;
  uploadStatusText.textContent = 'A IA está elaborando as questões e o gabarito…';
  uploadError.hidden = true;
  uploadSuccess.hidden = true;
  confirmGenerateTopicBtn.disabled = true;

  const payload = {
    topic,
    num_questions: Number(topicNumQuestions?.value) || 5,
    difficulty: topicDifficulty?.value || 'Médio',
    context: topicContext?.value.trim() || '',
    is_public: document.querySelector('#isPublicQuiz')?.checked || false,
  };

  try {
    const response = await fetch(`/api/quiz/generate${isGuestMode() ? '?guest=1' : ''}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'same-origin',
      body: JSON.stringify(payload),
    });

    const raw = await response.json();
    const data = raw.data || raw;

    if (!response.ok) {
      showUploadError(data.message || data.error || 'Erro ao gerar quiz por tema.');
      uploadStatus.hidden = true;
      confirmGenerateTopicBtn.disabled = false;
      return;
    }

    if (isGuestMode()) {
      saveGuestQuiz(data);
    }

    uploadStatus.hidden = true;
    uploadSuccess.textContent = `✓ ${data.message || 'Quiz gerado com sucesso!'}`;
    uploadSuccess.hidden = false;

    // Recarregar lista e selecionar novo quiz
    await loadQuizList();
    selectedSource = data.name;
    quizSelector.value = data.name;
    resetTimer();
    closeResultModal();
    if (result) {
      result.hidden = true;
      result.innerHTML = '';
    }
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
  if (!currentUser) {
    window.location.replace('/login');
  } else {
    openModal();
  }
});
document.querySelector('#closeModal').addEventListener('click', closeModal);
document.querySelector('#cancelUpload').addEventListener('click', closeModal);
confirmUploadBtn.addEventListener('click', doUpload);
confirmGenerateTopicBtn?.addEventListener('click', doGenerateTopic);

tabUploadFile?.addEventListener('click', () => switchModalTab('upload'));
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
    // Fechar modal de confirmação (= cancelar a finalização)
    if (confirmSubmitModal && !confirmSubmitModal.hidden) {
      confirmSubmitModal.hidden = true;
      document.body.style.overflow = '';
    }
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
  const isAuthed = await checkAuth();
  if (!isAuthed) return;
  try {
    await Promise.all([loadQuiz(), loadQuizList()]);
  } catch (error) {
    if (error.name !== 'AbortError') {
      quiz.innerHTML = '<p class="empty-state">Adicione um quiz usando o botão acima para começar.</p>';
      await loadQuizList().catch(() => {});
    }
  }
}

init();

