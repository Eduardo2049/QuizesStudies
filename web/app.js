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

let questions = [];
let selectedSource = '';
let loadRequestId = 0;
let loadController;
let remainingSeconds = timerDuration;
let timerInterval;

function isGuestMode() {
  return localStorage.getItem('quiz_guest_mode') === 'true';
}

function getGuestQuiz() {
  try {
    return JSON.parse(localStorage.getItem('quiz_guest_data') || 'null');
  } catch (_) {
    return null;
  }
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
  if (isGuestMode()) {
    const localQuiz = getGuestQuiz();
    if (!localQuiz) {
      quiz.innerHTML = '<p class="empty-state">Envie um quiz para começar.</p>';
      return;
    }
    selectedSource = localQuiz.name;
    questions = localQuiz.questions || [];
    renderQuestions();
    return;
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
  if (isGuestMode()) {
    const localQuiz = getGuestQuiz();
    quizSelector.innerHTML = localQuiz
      ? `<option value="${escapeHtml(localQuiz.name)}">${escapeHtml(localQuiz.label)} (local)</option>`
      : '<option value="">— Nenhum quiz local —</option>';
    return;
  }

  const response = await fetch('/api/quizzes', { cache: 'no-store' });
  const rawData = await response.json();
  const data = rawData.data || rawData;
  const quizzes = data.quizzes || [];

  if (!quizzes.length) {
    quizSelector.innerHTML = '<option value="">— Nenhum quiz cadastrado —</option>';
    return;
  }

  quizSelector.innerHTML = quizzes.map((item) =>
    `<option value="${item.name}">
      ${escapeHtml(item.label)}${item.ai_generated ? ' 🤖' : ''}
    </option>`
  ).join('');
  quizSelector.value = selectedSource;
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
    if (isGuestMode()) {
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
      const token = getAuthToken();
      const headers = { 'Content-Type': 'application/json' };
      if (token) headers['Authorization'] = `Bearer ${token}`;

      const response = await fetch('/api/quiz/submit', {
        method: 'POST',
        headers,
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
    result.hidden = false;
    result.innerHTML = `
      <h2>${escapeHtml(data.score)}/${escapeHtml(data.total)} acertos · ${escapeHtml(data.percentage)}%</h2>
      <p>Revise suas respostas abaixo. Use "Resetar quiz" para tentar novamente.</p>
      ${data.results.map((item) => `
        <div class="review">
          <strong class="${item.isCorrect ? 'right' : 'wrong'}">
            ${item.isCorrect ? '✓ Correta' : '✗ Errada'} · Questão ${escapeHtml(item.id)}
          </strong>
          <span>${item.isCorrect
            ? 'Você marcou a alternativa certa.'
            : (item.selected !== null && item.selected !== undefined
                ? `Você marcou a alternativa ${escapeHtml(String.fromCharCode(65 + item.selected))}; a correta era ${escapeHtml(String.fromCharCode(65 + item.correct))}.`
                : `Não respondida; a alternativa correta era ${String.fromCharCode(65 + item.correct)}.`)
          }</span>
          ${item.explanation ? `<br><small>${escapeHtml(item.explanation)}</small>` : ''}
        </div>
      `).join('')}`;
    result.scrollIntoView({ behavior: 'smooth' });
  } catch (err) {
    alert('Erro ao conferir respostas. Verifique a conexão com o servidor.');
  } finally {
    if (submitBtn) {
      submitBtn.disabled = false;
      submitBtn.innerHTML = 'Conferir respostas <span>→</span>';
    }
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
  result.hidden = true;
  result.innerHTML = '';
  updateProgress();
  window.scrollTo({ top: 0, behavior: 'smooth' });
});

quiz.addEventListener('change', () => {
  startTimer();
  updateProgress();
});

quizSelector.addEventListener('change', async () => {
  resetTimer();
  result.hidden = true;
  result.innerHTML = '';
  quiz.innerHTML = '';
  try {
    await loadQuiz(quizSelector.value);
  } catch (error) {
    if (error.name !== 'AbortError')
      result.innerHTML = `<p>Não foi possível carregar este questionário.</p>`;
  }
});

// ─── Modal de Upload ──────────────────────────────────────────────────────────
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

let selectedFile = null;

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
  dropZone.classList.remove('drop-zone--active', 'drop-zone--error');
  fileInput.value = '';
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
  uploadError.textContent = msg;
  uploadError.hidden = false;
  dropZone.classList.add('drop-zone--error');
  confirmUploadBtn.disabled = true;
}

// ─── Autenticação & Sessão ──────────────────────────────────────────────────
let currentUser = null;

function clearAuthToken() {
  currentUser = null;
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
  if (isGuestMode()) {
    currentUser = { id: null, username: 'Convidado', role: 'guest' };
    updateAuthUI();
    return true;
  }

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
  if (isGuestMode()) {
    localStorage.removeItem('quiz_guest_mode');
    localStorage.removeItem('quiz_guest_data');
    window.location.replace('/login');
    return;
  }
  const token = getAuthToken();
  try { await fetch('/api/auth/logout', { method: 'POST' }); } catch (_) {}
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
      localStorage.setItem('quiz_guest_data', JSON.stringify(data));
    }

    uploadStatus.hidden = true;
    uploadSuccess.textContent = `✓ ${data.message}`;
    uploadSuccess.hidden = false;

    // Recarregar lista e selecionar novo quiz
    await loadQuizList();
    quizSelector.value = data.name;
    resetTimer();
    result.hidden = true;
    result.innerHTML = '';
    quiz.innerHTML = '';
    try { await loadQuiz(data.name); } catch (_) {}

    setTimeout(closeModal, 1800);
  } catch (err) {
    showUploadError('Falha na conexão. Verifique o servidor e tente novamente.');
    uploadStatus.hidden = true;
    confirmUploadBtn.disabled = false;
  }
}

// Eventos do modal de upload
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

// Fechar clicando fora
uploadModal.addEventListener('click', (e) => { if (e.target === uploadModal) closeModal(); });

// Fechar com Escape
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    if (!uploadModal.hidden) closeModal();
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
    await loadQuiz();
    await loadQuizList();
  } catch (error) {
    if (error.name !== 'AbortError') {
      quiz.innerHTML = '<p class="empty-state">Adicione um quiz usando o botão acima para começar.</p>';
      await loadQuizList().catch(() => {});
    }
  }
}

init();

