// Тема: light | dark | auto (следует за системной).
// Выбор хранится в localStorage и не зависит от логина.
(function () {
  const LABELS = { light: 'Светлая', dark: 'Тёмная', auto: 'Системная' };
  const ICONS = { light: '☀️', dark: '🌙', auto: '🖥️' };
  const mq = window.matchMedia('(prefers-color-scheme: dark)');

  function current() { return localStorage.getItem('theme') || 'auto'; }
  function resolved() {
    const t = current();
    return t === 'auto' ? (mq.matches ? 'dark' : 'light') : t;
  }

  function apply() {
    const t = current();
    const root = document.documentElement;
    root.removeAttribute('data-theme');
    if (resolved() === 'dark') root.setAttribute('data-theme', 'dark');
    const btn = document.getElementById('theme-btn');
    if (btn) {
      btn.textContent = ICONS[t];
      btn.title = 'Тема: ' + LABELS[t];
      btn.setAttribute('aria-label', btn.title);
    }
    syncMenu();
  }

  function menu() { return document.getElementById('theme-menu'); }

  function syncMenu() {
    const m = menu();
    if (!m) return;
    const t = current();
    for (const item of m.querySelectorAll('[data-theme-choice]')) {
      const on = item.dataset.themeChoice === t;
      item.classList.toggle('on', on);
      item.setAttribute('aria-checked', on ? 'true' : 'false');
    }
  }

  function closeMenu() {
    const m = menu();
    if (m) m.hidden = true;
    const btn = document.getElementById('theme-btn');
    if (btn) btn.setAttribute('aria-expanded', 'false');
  }

  function init() {
    apply();

    const btn = document.getElementById('theme-btn');
    const m = menu();
    if (!btn || !m) return;

    btn.addEventListener('click', function (e) {
      e.stopPropagation();
      m.hidden = !m.hidden;
      btn.setAttribute('aria-expanded', m.hidden ? 'false' : 'true');
    });

    m.addEventListener('click', function (e) {
      const item = e.target.closest('[data-theme-choice]');
      if (!item) return;
      localStorage.setItem('theme', item.dataset.themeChoice);
      apply();
      closeMenu();
    });

    document.addEventListener('click', function (e) {
      if (!e.target.closest('.theme-switch')) closeMenu();
    });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') closeMenu();
    });

    // Системная тема сменилась — обновляем, если режим «Системная»
    mq.addEventListener('change', function () {
      if (current() === 'auto') apply();
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
