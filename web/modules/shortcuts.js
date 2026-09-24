/**
 * Módulo de Usabilidade e Produtividade: Atalhos de Teclado (Hotkeys)
 * Permite navegação rápida, marcação ágil de alternativas e finalização sem tirar as mãos do teclado.
 */

let shortcutsEnabled = true;

/** Verifica se o usuário está digitando em algum campo de formulário */
function isInputActive(e) {
  const tag = (e.target && e.target.tagName) ? e.target.tagName.toUpperCase() : '';
  if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') {
    return true;
  }
  return e.target && e.target.isContentEditable;
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

    // Se estiver digitando em um input de texto ou formulário de modal, não interceptar teclas normais
    if (isInputActive(e)) return;

    // Se houver algum modal visível aberto, não interceptar navegação de quiz
    const openModal = document.querySelector('.modal-overlay:not([hidden])');
    if (openModal) return;

    const currentMode = getViewMode ? getViewMode() : 'focus';

    // 3. Navegação entre questões com setas (no Modo Foco)
    if (currentMode === 'focus') {
      if (e.key === 'ArrowRight' || e.key === 'PageDown') {
        e.preventDefault();
        if (onNextQuestion) onNextQuestion();
        return;
      }
      if (e.key === 'ArrowLeft' || e.key === 'PageUp') {
        e.preventDefault();
        if (onPrevQuestion) onPrevQuestion();
        return;
      }
    }

    // 4. Marcação de alternativas rápida por tecla:
    // Suporta A, B, C, D, E ou 1, 2, 3, 4, 5
    const key = e.key.toUpperCase();
    let optionIndex = -1;

    if (['A', 'B', 'C', 'D', 'E'].includes(key)) {
      optionIndex = key.charCodeAt(0) - 65; // A=0, B=1, C=2, D=3, E=4
    } else if (['1', '2', '3', '4', '5'].includes(key)) {
      optionIndex = parseInt(key, 10) - 1; // 1=0, 2=1...
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
  const letter = String.fromCharCode(65 + optionIndex);
  const number = optionIndex + 1;
  return `<kbd class="option-kbd" title="Atalho: tecle '${letter}' ou '${number}'">${letter}</kbd>`;
}
