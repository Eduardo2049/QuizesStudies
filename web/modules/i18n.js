/**
 * Tradução da interface sem marcar tela por tela.
 *
 * O português continua sendo o texto-fonte escrito no HTML e no JS. Quando o idioma
 * escolhido é outro, este módulo percorre o DOM, troca os textos e os atributos
 * (title, placeholder, aria-label, alt, label, data-topic) que existem no dicionário e
 * observa as mudanças seguintes com MutationObserver, então o conteúdo que o
 * app.js gera depois também sai traduzido.
 *
 * Elementos com translate="no" (e o que estiver dentro deles) não são tocados.
 * Para acrescentar um idioma: crie web/modules/i18n/<código>.js e registre em
 * LANGUAGES e DICTIONARIES. O i18n-boot.js precisa da mesma regra de getLanguage().
 */
import en from './i18n/en.js?v=2';

const STORAGE_KEY = 'quiz_lang';
export const LANGUAGES = { 'pt-BR': 'Português', en: 'English' };
const DICTIONARIES = { en };
const ATTRIBUTES = ['title', 'placeholder', 'aria-label', 'alt', 'label', 'data-topic'];
const SKIP_TAGS = new Set(['SCRIPT', 'STYLE', 'TEXTAREA', 'CODE', 'PRE', 'SVG']);

export function getLanguage() {
  let saved = null;
  try { saved = localStorage.getItem(STORAGE_KEY); } catch (_) {}
  if (saved && saved in LANGUAGES) return saved;
  const nav = String(navigator.language || 'pt-BR').toLowerCase();
  return nav.startsWith('pt') ? 'pt-BR' : 'en';
}

const currentLang = getLanguage();
const dict = DICTIONARIES[currentLang] || null;
const exact = new Map();
const patterns = [];

function normalize(text) {
  return text.replace(/\s+/g, ' ').trim();
}

function compilePattern(key, value) {
  const order = [];
  const source = key.split(/(\{\d+\})/).map((part) => {
    const slot = part.match(/^\{(\d+)\}$/);
    if (slot) {
      order.push(Number(slot[1]));
      return '(.+?)';
    }
    return part.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  }).join('');
  return {
    regex: new RegExp(`^${source}$`),
    order,
    value,
    literalLength: key.replace(/\{\d+\}/g, '').length,
  };
}

if (dict) {
  for (const [key, value] of Object.entries(dict)) {
    const norm = normalize(key);
    if (/\{\d+\}/.test(norm)) patterns.push(compilePattern(norm, value));
    else exact.set(norm, value);
  }
  // Padrões mais específicos (mais texto fixo) primeiro
  patterns.sort((a, b) => b.literalLength - a.literalLength);
}

/** Traduz um texto da interface; devolve o próprio texto quando não há tradução. */
export function t(text) {
  if (!dict || typeof text !== 'string') return text;
  const norm = normalize(text);
  if (!norm) return text;
  const hit = exact.get(norm);
  if (hit !== undefined) return hit;
  for (const pattern of patterns) {
    const match = norm.match(pattern.regex);
    if (!match) continue;
    const values = [];
    pattern.order.forEach((slot, i) => { values[slot] = match[i + 1]; });
    return pattern.value.replace(/\{(\d+)\}/g, (_, slot) => t(values[slot] ?? ''));
  }
  return text;
}

function isSkipped(el) {
  for (let node = el; node; node = node.parentElement) {
    if (SKIP_TAGS.has(node.tagName.toUpperCase()) || node.getAttribute('translate') === 'no') return true;
  }
  return false;
}

function translateTextNode(node) {
  const original = node.nodeValue;
  const next = t(original);
  // Comparar normalizado evita laço quando a tradução é igual ao original
  if (next === original || normalize(next) === normalize(original)) return;
  const lead = original.match(/^\s*/)[0];
  const trail = original.match(/\s*$/)[0];
  node.nodeValue = lead + next + trail;
}

function translateAttribute(el, name) {
  const value = el.getAttribute(name);
  if (!value) return;
  const next = t(value);
  if (next !== value && normalize(next) !== normalize(value)) el.setAttribute(name, next);
}

function translateAttributes(el) {
  for (const name of ATTRIBUTES) {
    if (el.hasAttribute(name)) translateAttribute(el, name);
  }
}

function translateTree(root) {
  if (root.nodeType === Node.TEXT_NODE) {
    if (root.parentElement && !isSkipped(root.parentElement)) translateTextNode(root);
    return;
  }
  if (root.nodeType !== Node.ELEMENT_NODE || isSkipped(root)) return;
  translateAttributes(root);
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT, {
    acceptNode(node) {
      if (node.nodeType === Node.ELEMENT_NODE
        && (SKIP_TAGS.has(node.tagName.toUpperCase()) || node.getAttribute('translate') === 'no')) {
        return NodeFilter.FILTER_REJECT;
      }
      return NodeFilter.FILTER_ACCEPT;
    },
  });
  while (walker.nextNode()) {
    const node = walker.currentNode;
    if (node.nodeType === Node.TEXT_NODE) translateTextNode(node);
    else translateAttributes(node);
  }
}

function onMutations(mutations) {
  for (const m of mutations) {
    if (m.type === 'childList') {
      m.addedNodes.forEach(translateTree);
    } else if (m.type === 'characterData') {
      if (m.target.parentElement && !isSkipped(m.target.parentElement)) translateTextNode(m.target);
    } else if (m.type === 'attributes') {
      if (!isSkipped(m.target)) translateAttribute(m.target, m.attributeName);
    }
  }
}

export function setLanguage(lang) {
  if (!(lang in LANGUAGES) || lang === currentLang) return;
  try { localStorage.setItem(STORAGE_KEY, lang); } catch (_) {}
  // Recarregar devolve os textos originais antes de traduzir para o novo idioma
  window.location.reload();
}

function initLanguageToggles() {
  const codes = Object.keys(LANGUAGES);
  const next = codes[(codes.indexOf(currentLang) + 1) % codes.length];
  const title = currentLang === 'en'
    ? `Language: English (switch to ${LANGUAGES[next]})`
    : `Idioma: Português (mudar para ${LANGUAGES[next]})`;
  document.querySelectorAll('[data-lang-toggle]').forEach((btn) => {
    const label = btn.querySelector('.lang-code');
    if (label) label.textContent = currentLang === 'en' ? 'EN' : 'PT';
    btn.title = title;
    btn.setAttribute('aria-label', title);
    btn.addEventListener('click', () => setLanguage(next));
  });
}

function init() {
  document.documentElement.lang = currentLang;
  initLanguageToggles();
  if (dict) {
    translateTree(document.documentElement);
    new MutationObserver(onMutations).observe(document.documentElement, {
      childList: true,
      subtree: true,
      characterData: true,
      attributes: true,
      attributeFilter: ATTRIBUTES,
    });
  }
  document.documentElement.classList.remove('i18n-pending');
}

init();
