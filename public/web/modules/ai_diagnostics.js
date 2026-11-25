/**
 * Diagnóstico da IA (só admin), dentro de "Minha conta".
 *
 * Mostra a ordem dos provedores, quais têm chave, avisos de configuração, as chamadas do dia e
 * as últimas gerações por tema, com tempo, questões entregues e o que deu errado
 * (GET /api/admin/ia), e testa cada provedor com um pedido mínimo (POST /api/admin/ia/teste).
 * Os avisos, os ids de modelo e as linhas de log vêm do servidor e ficam sem tradução
 * (translate="no"). Tudo entra com textContent: nada do servidor vira HTML.
 */

const $ = (selector) => document.querySelector(selector);
let probeBound = false;

function node(tag, text = '', { cls = '', noTranslate = false } = {}) {
  const el = document.createElement(tag);
  if (text) el.textContent = text;
  if (cls) el.className = cls;
  if (noTranslate) el.setAttribute('translate', 'no');
  return el;
}

function fillList(list, items) {
  if (!list) return;
  list.replaceChildren(...items);
  list.hidden = items.length === 0;
}

function providerStatus(provider) {
  if (!provider.has_key) return 'sem chave';
  if (!provider.position) return 'fora de AI_PROVIDERS';
  if (provider.paused_seconds > 0) return `pausado por mais ${Math.ceil(provider.paused_seconds / 60)} min`;
  return 'ativo';
}

function modelsText(models) {
  return (models || []).map((m) => {
    if (m.state !== 'ativo') return `${m.id} (${m.state})`;
    if (m.streaming === false) return `${m.id} (sem streaming)`;
    if (m.shutdown) return `${m.id} (sai do ar em ${m.shutdown})`;
    return m.id;
  }).join(', ');
}

/** Uma linha por geração recente: tempo, entregues/pedidas e, se houve, o que atrapalhou. */
function recentGenerationText(g) {
  const head = `${g.seconds} s · ${g.delivered} de ${g.requested} questões · ${g.parts || 1} parte(s)`;
  const notes = [];
  if (g.failed_parts) notes.push(`${g.failed_parts} falha(s)`);
  if (g.duplicates_removed) notes.push(`${g.duplicates_removed} repetida(s)`);
  if (g.discarded) notes.push(`${g.discarded} reprovada(s)`);
  if (g.hedged_parts) notes.push(`${g.hedged_parts} pedido(s) em dobro`);
  if (g.topup) notes.push('pedido extra');
  const via = [g.provider, g.model].filter(Boolean).join(' ');
  return [head, ...notes, via].filter(Boolean).join(' · ');
}

function renderDiagnostics(diag) {
  const summary = $('#accountAiSummary');
  const daily = $('#accountAiDaily');
  const active = (diag.providers || []).filter((p) => p.active);
  if (summary) {
    summary.textContent = active.length
      ? `Ordem: ${active.map((p) => p.name).join(' → ')}.`
      : 'Nenhum provedor de IA com chave.';
  }
  if (daily) {
    const calls = diag.daily_calls || {};
    daily.textContent = calls.limit
      ? `Chamadas hoje: ${calls.used_24h ?? 0} de ${calls.limit}.`
      : `Chamadas hoje: ${calls.used_24h ?? 0}.`;
    daily.hidden = false;
  }
  const speed = $('#accountAiSpeed');
  if (speed) {
    const t = diag.generation_time;
    if (!t || !t.count) {
      speed.textContent = 'Nenhuma geração com IA nas últimas 24 h.';
    } else {
      speed.textContent = `Tempo de geração (24 h): média de ${t.avg} s, p90 de ${t.p90} s, ${t.within_target_pct}% em até ${t.target_seconds} s (${t.count} simulados).`;
    }
    speed.hidden = false;
    const detail = $('#accountAiSpeedDetail');
    if (detail) {
      const parts = (t?.by_size || []).map((b) => `${b.label}: ${b.avg} s (${b.count})`);
      detail.textContent = parts.join(' · ');
      detail.hidden = parts.length === 0;
    }
  }
  fillList($('#accountAiRecent'), (diag.generation_time?.recent || []).map((g) => {
    const li = node('li', recentGenerationText(g), {
      cls: g.delivered < g.requested ? 'ai-diag-item ai-diag-fail' : 'ai-diag-item',
      noTranslate: true,
    });
    if (g.errors?.length) {
      const sub = node('ul', '', { cls: 'ai-diag-list ai-diag-list--log' });
      sub.append(...g.errors.map((e) => node('li', e, { cls: 'ai-diag-log', noTranslate: true })));
      li.append(sub);
    }
    return li;
  }));
  fillList($('#accountAiWarnings'), (diag.warnings || []).map((w) => node('li', w, { cls: 'ai-diag-warning', noTranslate: true })));
  fillList($('#accountAiProviders'), (diag.providers || []).map((p) => {
    const li = node('li', '', { cls: 'ai-diag-item' });
    li.append(node('strong', p.name, { noTranslate: true }), node('span', providerStatus(p), { cls: 'ai-diag-status' }));
    const models = modelsText(p.models);
    if (models) li.append(node('span', models, { cls: 'ai-diag-models', noTranslate: true }));
    return li;
  }));
}

function renderProbe(results) {
  fillList($('#accountAiResults'), (results || []).map((r) => {
    const li = node('li', '', { cls: 'ai-diag-item ai-diag-item--block' });
    const head = r.ok
      ? `${r.provider}: respondeu com ${r.model} em ${r.seconds} s`
      : `${r.provider}: falhou em ${r.seconds} s`;
    li.append(node('span', head, { cls: r.ok ? 'ai-diag-ok' : 'ai-diag-fail' }));
    const lines = (r.log || []).map((line) => node('li', line, { cls: 'ai-diag-log', noTranslate: true }));
    if (lines.length) {
      const sub = node('ul', '', { cls: 'ai-diag-list ai-diag-list--log' });
      sub.append(...lines);
      li.append(sub);
    }
    return li;
  }));
}

async function loadDiagnostics() {
  const summary = $('#accountAiSummary');
  try {
    const res = await fetch('/api/admin/ia', { cache: 'no-store', credentials: 'same-origin' });
    if (!res.ok) throw new Error(String(res.status));
    const body = await res.json();
    renderDiagnostics(body.data || {});
  } catch (_) {
    if (summary) summary.textContent = 'Não foi possível carregar o diagnóstico.';
  }
}

async function runProbe() {
  const button = $('#accountAiProbe');
  const hint = $('#accountAiProbeHint');
  if (!button || button.disabled) return;
  button.disabled = true;
  button.textContent = 'Testando…';
  try {
    const res = await fetch('/api/admin/ia/teste', {
      method: 'POST',
      cache: 'no-store',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: '{}',
    });
    if (res.status === 429) {
      if (hint) hint.textContent = 'Aguarde alguns minutos para testar de novo.';
      return;
    }
    if (!res.ok) throw new Error(String(res.status));
    const body = await res.json();
    renderProbe(body.data?.results);
    if (body.data?.diagnostics) renderDiagnostics(body.data.diagnostics);
    if (hint) hint.textContent = 'Faz um pedido mínimo a cada provedor com chave e mostra a resposta.';
  } catch (_) {
    if (hint) hint.textContent = 'Não foi possível testar agora.';
  } finally {
    button.disabled = false;
    button.textContent = 'Testar provedores agora';
  }
}

/** Mostra a seção (só chamada para o admin) e carrega a situação atual. */
export function openAiDiagnostics() {
  const section = $('#accountAiSection');
  if (!section) return;
  section.hidden = false;
  if (!probeBound) {
    $('#accountAiProbe')?.addEventListener('click', runProbe);
    probeBound = true;
  }
  loadDiagnostics();
}
