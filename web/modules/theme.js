/**
 * Módulo de Personalização e Temas (Dark / Light / Sistema)
 * Suporta preferência do sistema operacional e alternância manual salva em localStorage.
 */

const THEME_STORAGE_KEY = 'quiz_theme_preference';
const THEMES = ['system', 'dark', 'light'];

let currentTheme = 'system';
let systemMediaQuery = null;

/** Retorna o tema resolvido ('dark' ou 'light') com base no sistema ou preferência */
export function getResolvedTheme(theme = currentTheme) {
  if (theme === 'system') {
    return window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches
      ? 'dark'
      : 'light';
  }
  return theme;
}

/** Aplica o tema na tag <html> e atualiza o estado visual do botão */
export function applyTheme(theme = currentTheme) {
  currentTheme = theme;
  const resolved = getResolvedTheme(theme);
  
  document.documentElement.setAttribute('data-theme', resolved);
  document.documentElement.setAttribute('data-theme-mode', theme);
  
  // Atualiza cores de meta theme-color se existir
  let metaTheme = document.querySelector('meta[name="theme-color"]');
  if (!metaTheme) {
    metaTheme = document.createElement('meta');
    metaTheme.name = 'theme-color';
    document.head.appendChild(metaTheme);
  }
  metaTheme.content = resolved === 'dark' ? '#0d1315' : '#f4f0e8';

  updateThemeButtonUI();
}

/** Salva o tema escolhido no localStorage e o aplica */
export function setTheme(theme) {
  if (!THEMES.includes(theme)) theme = 'system';
  currentTheme = theme;
  try {
    localStorage.setItem(THEME_STORAGE_KEY, theme);
  } catch (_) {}
  applyTheme(theme);
}

/** Alterna ciclicamente entre: Sistema -> Escuro -> Claro */
export function toggleTheme() {
  const currentIndex = THEMES.indexOf(currentTheme);
  const nextTheme = THEMES[(currentIndex + 1) % THEMES.length];
  setTheme(nextTheme);
  return nextTheme;
}

/** Obtém a preferência atual ('system' | 'dark' | 'light') */
export function getCurrentTheme() {
  return currentTheme;
}

/** Atualiza a aparência do botão de alternância de tema no header */
function updateThemeButtonUI() {
  const btn = document.querySelector('#themeToggle');
  if (!btn) return;

  const iconEl = btn.querySelector('.theme-icon');
  const labelEl = btn.querySelector('.theme-label');

  let icon = '💻';
  let label = 'Tema: Sistema';
  let title = 'Tema: Sistema (clique para alternar)';

  if (currentTheme === 'dark') {
    icon = '🌙';
    label = 'Tema: Escuro';
    title = 'Tema: Escuro (clique para alternar para Claro)';
  } else if (currentTheme === 'light') {
    icon = '☀️';
    label = 'Tema: Claro';
    title = 'Tema: Claro (clique para alternar para Sistema)';
  }

  if (iconEl) iconEl.textContent = icon;
  if (labelEl) labelEl.textContent = label;
  btn.title = title;
  btn.setAttribute('aria-label', title);
}

/** Inicializa o observador do sistema operacional e carrega preferência salva */
export function initTheme() {
  try {
    const saved = localStorage.getItem(THEME_STORAGE_KEY);
    if (saved && THEMES.includes(saved)) {
      currentTheme = saved;
    } else {
      currentTheme = 'system';
    }
  } catch (_) {
    currentTheme = 'system';
  }

  // Listener para quando o usuário alterar o tema do Windows/Mac/Linux em tempo real
  if (window.matchMedia) {
    systemMediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
    const onChange = () => {
      if (currentTheme === 'system') {
        applyTheme('system');
      }
    };
    if (systemMediaQuery.addEventListener) {
      systemMediaQuery.addEventListener('change', onChange);
    } else if (systemMediaQuery.addListener) {
      systemMediaQuery.addListener(onChange);
    }
  }

  applyTheme(currentTheme);

  // Conectar botão na DOM
  const btn = document.querySelector('#themeToggle');
  if (btn) {
    btn.addEventListener('click', () => {
      toggleTheme();
    });
  }
}
