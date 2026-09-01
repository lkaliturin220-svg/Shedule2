// «Моя группа» / «Мой преподаватель» — избранное в localStorage.
// Для залогиненного студента дефолт — группа из профиля (data-default-group на <body>).
(function () {
  const KEY_G = 'fav_group';
  const KEY_T = 'fav_teacher';

  const defaultGroup = (document.body.dataset.defaultGroup || '').trim();
  const getG = () => localStorage.getItem(KEY_G) || defaultGroup;
  const getT = () => localStorage.getItem(KEY_T) || '';
  const setG = v => (v ? localStorage.setItem(KEY_G, v) : localStorage.removeItem(KEY_G));
  const setT = v => (v ? localStorage.setItem(KEY_T, v) : localStorage.removeItem(KEY_T));

  /* ── Чип в шапке: быстрая ссылка на мою группу ── */
  function navChip() {
    const chip = document.getElementById('fav-group-link');
    if (!chip) return;
    const g = getG();
    if (!g || !window.scheduleUrls || !window.scheduleUrls.group) { chip.hidden = true; return; }
    chip.hidden = false;
    chip.href = window.scheduleUrls.group.replace('__NAME__', encodeURIComponent(g));
    chip.title = 'Перейти к расписанию группы ' + g;
    const label = chip.querySelector('span');
    if (label) label.textContent = g.length > 16 ? g.slice(0, 15) + '…' : g;
  }

  /* ── Главная: пометить и закрепить избранное ── */
  function decorateIndex() {
    for (const [gridId, key, fav] of [['gg', KEY_G, getG()], ['tg', KEY_T, getT()]]) {
      const grid = document.getElementById(gridId);
      if (!grid || !fav) continue;
      const tiles = [...grid.children];
      let favTile = null;
      for (const tile of tiles) {
        const isFav = (tile.dataset.name || tile.dataset.id || '') === fav;
        tile.classList.toggle('fav', isFav);
        let star = tile.querySelector('.tile-star');
        if (isFav) {
          favTile = tile;
          if (!star) {
            star = document.createElement('span');
            star.className = 'tile-star';
            star.textContent = '★';
            tile.prepend(star);
          }
        } else if (star) {
          star.remove();
        }
      }
      if (favTile) grid.prepend(favTile);
    }
  }

  /* ── Кнопки на страницах расписания ── */
  function decorateFavButtons() {
    for (const btn of document.querySelectorAll('.js-fav-group')) {
      const name = btn.dataset.name;
      const sync = () => {
        const on = getG() === name;
        btn.classList.toggle('is-fav', on);
        btn.textContent = on ? '★ Моя группа (нажми, чтобы убрать)' : '⭐ Сделать моей группой';
      };
      sync();
      btn.addEventListener('click', () => { setG(getG() === name ? '' : name); sync(); navChip(); decorateIndex(); });
    }
    for (const btn of document.querySelectorAll('.js-fav-teacher')) {
      const id = btn.dataset.id;
      const sync = () => {
        const on = getT() === id;
        btn.classList.toggle('is-fav', on);
        btn.textContent = on ? '★ Мой преподаватель (убрать)' : '⭐ Сделать моим преподавателем';
      };
      sync();
      btn.addEventListener('click', () => { setT(getT() === id ? '' : id); sync(); decorateIndex(); });
    }
  }

  navChip();
  decorateIndex();
  decorateFavButtons();
})();
