const quiz = document.querySelector('#quiz');
const result = document.querySelector('#result');
const progress = document.querySelector('#progress');
const percent = document.querySelector('#percent');
const progressBar = document.querySelector('#progressBar');
const quizSelector = document.querySelector('#quizSelector');
const timer = document.querySelector('#timer');
const timerDuration = 24 * 60;
let questions = [];
let selectedSource = '';
let loadRequestId = 0;
let loadController;
let remainingSeconds = timerDuration;
let timerInterval;

function resetTimer() {
  clearInterval(timerInterval);
  timerInterval = undefined;
  remainingSeconds = timerDuration;
  timer.textContent = '24:00';
  timer.classList.remove('expired', 'running');
}

function startTimer() {
  if (timerInterval || remainingSeconds === 0) return;
  timer.classList.add('running');
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

async function loadQuiz(source = selectedSource) {
  const requestId = ++loadRequestId;
  loadController?.abort();
  loadController = new AbortController();
  const response = await fetch(`/api/quiz${source ? `?source=${encodeURIComponent(source)}` : ''}`, {
    cache: 'no-store',
    signal: loadController.signal,
  });
  if (!response.ok) throw new Error(`Falha ao carregar o questionario (${response.status})`);
  const data = await response.json();
  if (requestId !== loadRequestId) return;
  selectedSource = data.source;
  questions = data.questions;
  quiz.innerHTML = questions.map((item, index) => `
    <article class="question">
      <p class="section">${item.section}</p>
      ${item.context && (index === 0 || questions[index - 1].context !== item.context) ? `<p class="context">${item.context}</p>` : ''}
      <div class="question-head"><span class="number">${String(item.id).padStart(2, '0')}</span><h2>${item.question}</h2></div>
      <div class="options">${item.options.map((option, index) => `<label class="option"><input type="radio" name="q-${item.id}" value="${index}"><span>${String.fromCharCode(65 + index)}) ${option}</span></label>`).join('')}</div>
    </article>`).join('');
  updateProgress();
}

async function loadQuizList() {
  const response = await fetch('/api/quizzes', {cache: 'no-store'});
  const data = await response.json();
  quizSelector.innerHTML = data.quizzes.map((item) => `<option value="${item.name}">${item.label}</option>`).join('');
  quizSelector.value = selectedSource;
}

function updateProgress() {
  const answered = new FormData(quiz);
  const count = [...answered.keys()].length;
  const value = Math.round(count / questions.length * 100);
  progress.textContent = `${count} de ${questions.length} respondidas`;
  percent.textContent = `${value}%`;
  progressBar.style.width = `${value}%`;
}

quiz.addEventListener('submit', async (event) => {
  event.preventDefault();
  const answers = Object.fromEntries([...new FormData(quiz)].map(([key, value]) => [key.replace('q-', ''), Number(value)]));
  if (Object.keys(answers).length < questions.length) { alert('Responda todas as questoes antes de conferir.'); return; }
  const response = await fetch('/api/quiz/submit', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({source:selectedSource, answers}) });
  const data = await response.json();
  clearInterval(timerInterval);
  timerInterval = undefined;
  timer.classList.remove('running');
  result.hidden = false;
  result.innerHTML = `<h2>${data.score}/${data.total} acertos · ${data.percentage}%</h2><p>Agora voce pode revisar cada resposta. Use "Resetar quiz" para tentar novamente.</p>${data.results.map((item) => `<div class="review"><strong class="${item.isCorrect ? 'right' : 'wrong'}">${item.isCorrect ? 'Correta' : 'Errada'} · Questao ${item.id}</strong><span>${item.isCorrect ? 'Voce marcou a alternativa certa.' : `Voce marcou a alternativa ${String.fromCharCode(65 + item.selected)}; a correta era ${String.fromCharCode(65 + item.correct)}.`}</span><br><small>${item.explanation}</small></div>`).join('')}`;
  result.scrollIntoView({behavior:'smooth'});
});

document.querySelector('#reset').addEventListener('click', () => { quiz.reset(); resetTimer(); result.hidden = true; result.innerHTML = ''; updateProgress(); window.scrollTo({top:0, behavior:'smooth'}); });
quiz.addEventListener('change', startTimer);
quizSelector.addEventListener('change', async () => {
  resetTimer();
  result.hidden = true;
  result.innerHTML = '';
  quiz.innerHTML = '';
  try {
    await loadQuiz(quizSelector.value);
  } catch (error) {
    if (error.name !== 'AbortError') result.innerHTML = `<p> nao foi possivel carregar este questionario.</p>`;
  }
});
document.addEventListener('click', (event) => {
  if (event.target.closest('button, select, label')) startTimer();
});
resetTimer();
loadQuiz().then(loadQuizList);
