// Живая подсветка пар на расписании: «идёт сейчас», «скоро», пройденные.
// Работает только если выбран сегодняшний день (data-today="1").
(function () {
  const card = document.querySelector('[data-today]');
  if (!card || card.dataset.today !== '1') return;
  const rows = [...card.querySelectorAll('.tl-row')];
  if (!rows.length) return;

  function toMin(hhmm) {
    const [h, m] = hhmm.split(':').map(Number);
    return h * 60 + m;
  }

  function note(text) {
    const n = document.createElement('span');
    n.className = 'tl-note';
    n.textContent = text;
    return n;
  }

  function update() {
    const now = new Date();
    const cur = now.getHours() * 60 + now.getMinutes();
    let nextMarked = false;

    for (const row of rows) {
      row.classList.remove('tl-now', 'tl-next', 'tl-done');
      row.querySelectorAll('.tl-note, .tl-progress').forEach(el => el.remove());
      if (!row.dataset.start) continue;

      const s = toMin(row.dataset.start);
      const e = toMin(row.dataset.end);
      const body = row.querySelector('.tl-body');

      if (cur >= s && cur < e) {
        row.classList.add('tl-now');
        body.prepend(note('идёт сейчас · осталось ' + (e - cur) + ' мин'));
        const p = document.createElement('div');
        p.className = 'tl-progress';
        const bar = document.createElement('i');
        bar.style.width = Math.min(100, Math.round(((cur - s) / (e - s)) * 100)) + '%';
        p.appendChild(bar);
        body.appendChild(p);
      } else if (cur < s && !nextMarked) {
        row.classList.add('tl-next');
        body.prepend(note(cur === s - 1 ? 'скоро' : 'скоро · через ' + (s - cur) + ' мин'));
        nextMarked = true;
      } else if (cur >= e) {
        row.classList.add('tl-done');
      }
    }
  }

  update();
  setInterval(update, 30000);
})();
