// ─── Estado global ────────────────────────────────────────────────────────────
const quiz = document.querySelector('#quiz');
const result = document.querySelector('#result');
const progress = document.querySelector('#progress');
const percent = document.querySelector('#percent');
const progressBar = document.querySelector('#progressBar');
const quizSelector = document.querySelector('#quizSelector');
const timer = document.querySelector('#timer');
const startBtn = document.querySelector('#startBtn');
const timerDuration = 24 * 60;

// ─── Modal de Resultado do Simulado ───────────────────────────────────────────
const resultModal = document.querySelector('#resultModal');
const closeResultModalBtn = document.querySelector('#closeResultModal');
const btnCloseResultModal = document.querySelector('#btnCloseResultModal');
const btnRedoQuiz = document.querySelector('#btnRedoQuiz');
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

let questions = [];
let selectedSource = '';
let loadRequestId = 0;
let loadController;
let remainingSeconds = timerDuration;
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

// ─── Timer ────────────────────────────────────────────────────────────────────
function resetTimer() {
  clearInterval(timerInterval);
  timerInterval = undefined;
  remainingSeconds = timerDuration;
  timer.textContent = '24:00';
  timer.classList.remove('expired', 'running');
  if (startBtn) startBtn.classList.remove('hidden');
}

function startTimer() {
  if (timerInterval || remainingSeconds === 0) return;
  timer.classList.add('running');
  if (startBtn) startBtn.classList.add('hidden');
  timerInterval = setInterval(() => {
    remainingSeconds -= 1;
    const minutes = Math.floor(remainingSeconds / 60);
    const seconds = remainingSeconds % 60;
    timer.textContent = `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
    if (remainingSeconds === 0) {
      clearInterval(timerInterval);
      timerInterval = undefined;
      timer.classList.remove('running');
      timer.classList.add('expired');
    }
  }, 1000);
}

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
  quiz.innerHTML = questions.map((item, index) => `
    <article class="question">
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
  updateProgress();
}

async function loadQuizList() {
  let serverQuizzes = [];
  try {
    const response = await fetch('/api/quizzes', { cache: 'no-store' });
    if (response.ok) {
      const rawData = await response.json();
      const data = rawData.data || rawData;
      serverQuizzes = data.quizzes || [];
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

  if (answeredCount < questions.length) {
    const confirmSubmit = confirm(
      `Você respondeu ${answeredCount} de ${questions.length} questões. As questões não respondidas serão consideradas erradas.\n\nDeseja conferir o resultado agora?`
    );
    if (!confirmSubmit) return;
  }

  const submitBtn = document.querySelector('#submit');
  if (submitBtn) {
    submitBtn.disabled = true;
    submitBtn.textContent = 'Conferindo respostas…';
  }

  try {
    let data;
    const localQuiz = isGuestMode() ? findGuestQuizByName(selectedSource) : null;
    const isLocalQuiz = Boolean(localQuiz && questions.length > 0 && questions[0]?.answer !== undefined);

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
      data = {
        score,
        total: results.length,
        percentage: results.length ? Math.round(score / results.length * 100) : 0,
        results,
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

// Fechar com Escape
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    if (uploadModal && !uploadModal.hidden) closeModal();
    if (resultModal && !resultModal.hidden) closeResultModal();
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

