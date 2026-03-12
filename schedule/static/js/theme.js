// Тема: dark | light | auto
(function () {
  const ICONS = { dark: '🌙', light: '☀️', auto: '🖥️' };
  const LABELS = { dark: 'Тёмная', light: 'Светлая', auto: 'Авто' };
  const order = ['auto', 'dark', 'light'];
  let current = localStorage.getItem('theme') || 'auto';

  function apply(theme) {
    const root = document.documentElement;
    if (theme === 'auto') {
      root.removeAttribute('data-theme');
    } else {
      root.setAttribute('data-theme', theme);
    }
    const btn = document.getElementById('theme-btn');
    if (btn) {
      btn.textContent = ICONS[theme];
      btn.title = LABELS[theme];
    }
  }

  function cycle() {
    const idx = order.indexOf(current);
    current = order[(idx + 1) % order.length];
    localStorage.setItem('theme', current);
    apply(current);
  }

  document.addEventListener('DOMContentLoaded', function () {
    apply(current);
    const btn = document.getElementById('theme-btn');
    if (btn) btn.addEventListener('click', cycle);
  });
})();
