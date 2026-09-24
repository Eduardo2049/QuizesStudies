/**
 * Módulo de Feedback e Estatísticas Pedagógicas
 * Calcula métricas de aproveitamento, ritmo por questão e divisão por disciplinas/seções.
 */

/**
 * Calcula estatísticas pedagógicas completas para uma tentativa de simulado.
 * 
 * @param {Array} questions - Lista de questões do quiz [{id, section, ...}]
 * @param {Array} results - Lista de resultados retornados pela API [{question_id, correct, user_answer, answer, explanation}]
 * @param {number} totalSeconds - Tempo total decorrido no simulado (em segundos)
 * @returns {Object} Estatísticas calculadas
 */
export function calculateQuizStats(questions, results, totalSeconds = 0) {
  const total = questions.length;
  if (!total) return null;

  // Mapa de resultados por question_id
  const resultMap = new Map();
  for (const r of (results || [])) {
    resultMap.set(r.question_id, r);
  }

  let correctCount = 0;
  let wrongCount = 0;
  let blankCount = 0;

  // Agrupamento por seção/matéria
  const sectionMap = new Map();

  for (const q of questions) {
    const sectionName = (q.section || 'Geral').trim();
    if (!sectionMap.has(sectionName)) {
      sectionMap.set(sectionName, { section: sectionName, total: 0, correct: 0, wrong: 0, blank: 0 });
    }
    const sec = sectionMap.get(sectionName);
    sec.total += 1;

    const res = resultMap.get(q.id);
    if (!res || res.user_answer === null || res.user_answer === undefined) {
      blankCount += 1;
      sec.blank += 1;
    } else if (res.correct) {
      correctCount += 1;
      sec.correct += 1;
    } else {
      wrongCount += 1;
      sec.wrong += 1;
    }
  }

  const percentage = Math.round((correctCount / total) * 100);

  // Lista de seções com percentuais calculados
  const sections = Array.from(sectionMap.values()).map((sec) => ({
    ...sec,
    percentage: Math.round((sec.correct / sec.total) * 100),
  })).sort((a, b) => b.total - a.total); // Ordena pelas matérias com mais questões

  // Ritmo de prova
  const avgSecondsPerQuestion = total > 0 ? Math.round(totalSeconds / total) : 0;

  // Classificação geral
  let tierBadge = '🎯 Bom Rendimento';
  let tierColor = 'tier-good';
  let encouragement = 'Você teve um bom aproveitamento! Revise os erros pontuais para consolidar o conteúdo.';

  if (percentage >= 85) {
    tierBadge = '🏆 Desempenho Excepcional';
    tierColor = 'tier-excellent';
    encouragement = 'Excelente domínio! Você está pronto para os níveis mais desafiadores desta matéria.';
  } else if (percentage >= 70) {
    tierBadge = '🎯 Acima da Média';
    tierColor = 'tier-good';
    encouragement = 'Muito bom! Você superou o ponto de corte padrão. Foco nas justificativas das erradas.';
  } else if (percentage >= 50) {
    tierBadge = '⚖️ Regular / Em Evolução';
    tierColor = 'tier-average';
    encouragement = 'Bom esforço! Recomendamos retreinar o Caderno de Erros ou gerar variações com IA para fixar.';
  } else {
    tierBadge = '⚠️ Atenção Redobrada';
    tierColor = 'tier-attention';
    encouragement = 'Revise a teoria e as explicações didáticas antes de tentar o próximo simulado.';
  }

  return {
    total,
    correctCount,
    wrongCount,
    blankCount,
    percentage,
    sections,
    totalSeconds,
    avgSecondsPerQuestion,
    tierBadge,
    tierColor,
    encouragement,
  };
}

/** Formata segundos em texto amigável (ex: 2m 15s) */
function formatDuration(seconds) {
  if (!seconds || seconds <= 0) return '0s';
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  if (mins === 0) return `${secs}s`;
  if (secs === 0) return `${mins}m`;
  return `${mins}m ${secs}s`;
}

/**
 * Gera o bloco HTML dos painéis estatísticos e do breakdown por matérias
 * para ser injetado no modal de resultados.
 */
export function renderStatsHtml(stats) {
  if (!stats) return '';

  const {
    sections,
    totalSeconds,
    avgSecondsPerQuestion,
    correctCount,
    wrongCount,
    blankCount,
    tierBadge,
    tierColor,
    encouragement,
  } = stats;

  return `
    <div class="stats-overview-card ${tierColor}">
      <div class="stats-tier-header">
        <span class="stats-tier-tag">${tierBadge}</span>
        <span class="stats-rhythm-badge">⏱️ Ritmo Médio: <strong>${formatDuration(avgSecondsPerQuestion)}</strong> / questão</span>
      </div>
      <p class="stats-encouragement">${encouragement}</p>

      <div class="stats-pills-row">
        <div class="stats-pill pill-correct">
          <span class="pill-number">${correctCount}</span>
          <span class="pill-label">Acertos</span>
        </div>
        <div class="stats-pill pill-wrong">
          <span class="pill-number">${wrongCount}</span>
          <span class="pill-label">Erros</span>
        </div>
        ${blankCount > 0 ? `
          <div class="stats-pill pill-blank">
            <span class="pill-number">${blankCount}</span>
            <span class="pill-label">Em branco</span>
          </div>
        ` : ''}
        <div class="stats-pill pill-time">
          <span class="pill-number">${formatDuration(totalSeconds)}</span>
          <span class="pill-label">Tempo total</span>
        </div>
      </div>
    </div>

    ${sections.length > 0 ? `
      <div class="sections-breakdown-card">
        <h3 class="sections-breakdown-title">
          <span>📊 Desempenho por Disciplina / Matéria</span>
        </h3>
        <div class="sections-list">
          ${sections.map((sec) => {
            const barColorClass = sec.percentage >= 70 ? 'bar-high' : (sec.percentage >= 50 ? 'bar-mid' : 'bar-low');
            return `
              <div class="section-item">
                <div class="section-item-head">
                  <span class="section-name" title="${sec.section}">${sec.section}</span>
                  <span class="section-score">
                    <strong>${sec.correct}/${sec.total}</strong> (${sec.percentage}%)
                  </span>
                </div>
                <div class="section-progress-track">
                  <div class="section-progress-fill ${barColorClass}" style="width: ${sec.percentage}%"></div>
                </div>
              </div>
            `;
          }).join('')}
        </div>
      </div>
    ` : ''}
  `;
}
