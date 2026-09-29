/**
 * Módulo de Usabilidade e Produtividade: Atalhos de Teclado (Hotkeys)
 * Permite navegação rápida (AWSD/WASD e Setas), marcação ágil de alternativas (1–5) e finalização sem tirar as mãos do teclado.
 */

let shortcutsEnabled = true;

/** Verifica se o usuário está digitando em algum campo de formulário de texto */
function isInputActive(e) {
  const target = e.target;
  if (!target) return false;
  if (target.isContentEditable) return true;
  const tag = target.tagName ? target.tagName.toUpperCase() : '';
  if (tag === 'TEXTAREA' || tag === 'SELECT') return true;
  if (tag === 'INPUT') {
    const type = (target.type || 'text').toLowerCase();
    // Apenas campos de texto ou edição bloqueiam atalhos; radio/checkbox/button não bloqueiam
    return ['text', 'password', 'search', 'email', 'number', 'url', 'tel', ''].includes(type);
  }
  return false;
}

/**
 * Inicializa os atalhos de teclado globais.
 * @param {Object} handlers - Callbacks fornecidos pelo app principal
 */
export function initShortcuts({
  onNextQuestion,
  onPrevQuestion,
  onSelectOption,
  onSubmitQuiz,
  onCloseModals,
  getViewMode,
  getCurrentQuestionIndex,
  getQuestionsCount,
}) {
  window.addEventListener('keydown', (e) => {
    if (!shortcutsEnabled) return;

    // 1. Esc: Fecha qualquer modal aberto
    if (e.key === 'Escape') {
      if (onCloseModals) {
        onCloseModals();
      }
      return;
    }

    // 2. Ctrl+Enter ou Cmd+Enter: Finalizar simulado diretamente
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      e.preventDefault();
      if (onSubmitQuiz) onSubmitQuiz();
      return;
    }

    // Não interceptar atalhos nativos do sistema com Ctrl, Alt ou Meta (ex: Ctrl+C, Ctrl+V, Ctrl+R, Alt+Tab, etc.)
    if (e.ctrlKey || e.altKey || e.metaKey) return;

    // Se estiver digitando em um input de texto, não interceptar teclas normais
    if (isInputActive(e)) return;

    // Se houver algum modal visível aberto, não interceptar navegação de quiz
    const openModal = document.querySelector('.modal-overlay:not([hidden])');
    if (openModal) return;

    // Não executar navegação ou seleção se não houver perguntas carregadas
    const totalQuestions = getQuestionsCount ? getQuestionsCount() : 0;
    if (totalQuestions === 0) return;

    // Ignora repetição contínua se a tecla for mantida pressionada (evita saltar múltiplas questões acidentalmente)
    if (e.repeat) return;

    const currentMode = getViewMode ? getViewMode() : 'focus';
    const key = (e.key || '').toUpperCase();
    const code = e.code || '';

    // 3. Navegação entre questões com AWSD / WASD e Setas / PageUp / PageDown
    // Avançar (Próxima questão): D, S, Seta Direita, Seta Baixo, PageDown
    const isNextKey = (
      (currentMode === 'focus' && (e.key === 'ArrowRight' || e.key === 'ArrowDown' || e.key === 'PageDown')) ||
      key === 'D' ||
      key === 'S' ||
      code === 'KeyD' ||
      code === 'KeyS'
    );

    // Voltar (Questão anterior): A, W, Seta Esquerda, Seta Cima, PageUp
    const isPrevKey = (
      (currentMode === 'focus' && (e.key === 'ArrowLeft' || e.key === 'ArrowUp' || e.key === 'PageUp')) ||
      key === 'A' ||
      key === 'W' ||
      code === 'KeyA' ||
      code === 'KeyW'
    );

    if (isNextKey) {
      e.preventDefault();
      if (onNextQuestion) onNextQuestion();
      return;
    }

    if (isPrevKey) {
      e.preventDefault();
      if (onPrevQuestion) onPrevQuestion();
      return;
    }

    // 4. Marcação de alternativas rápida por tecla:
    // Suporta 1, 2, 3, 4, 5 (teclas numéricas superiores e teclado numérico Numpad)
    let optionIndex = -1;

    if (['1', '2', '3', '4', '5'].includes(e.key)) {
      optionIndex = parseInt(e.key, 10) - 1; // 1=0, 2=1, 3=2, 4=3, 5=4
    } else if (code.startsWith('Numpad')) {
      const num = code.replace('Numpad', '');
      if (['1', '2', '3', '4', '5'].includes(num)) {
        optionIndex = parseInt(num, 10) - 1;
      }
    }

    if (optionIndex >= 0) {
      e.preventDefault();
      const questionIdx = getCurrentQuestionIndex ? getCurrentQuestionIndex() : 0;
      if (onSelectOption) {
        onSelectOption(questionIdx, optionIndex);
      }
    }
  });
}

/**
 * Ativa ou desativa os atalhos temporariamente
 */
export function setShortcutsEnabled(enabled) {
  shortcutsEnabled = Boolean(enabled);
}

/**
 * Retorna o HTML de um badge visual de atalho para colocar na alternativa
 */
export function getShortcutBadgeHtml(optionIndex) {
  const number = optionIndex + 1;
  return `<kbd class="option-kbd" title="Atalho: tecle '${number}'">${number}</kbd>`;
}
