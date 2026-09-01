// AJAX-переключение дат: фетч партиала, подмена таймлайна, pushState.
(function () {
  const wrap = document.getElementById("schedule-body");
  if (!wrap) return;

  let seq = 0;

  function load(url, push) {
    const my = ++seq;
    wrap.classList.add("is-loading");
    const sep = url.includes("?") ? "&" : "?";
    fetch(url + sep + "ajax=1", { headers: { "X-Requested-With": "fetch" } })
      .then(r => {
        if (!r.ok) throw new Error(r.status);
        return r.text();
      })
      .then(html => {
        if (my !== seq) return;
        wrap.innerHTML = html;
        if (push) history.pushState({}, "", url);
        if (window.initScheduleLive) window.initScheduleLive();
      })
      .catch(() => { location.href = url; })
      .finally(() => { if (my === seq) wrap.classList.remove("is-loading"); });
  }

  document.addEventListener("click", function (e) {
    const chip = e.target.closest("#schedule-body .chip");
    if (!chip) return;
    e.preventDefault();
    load(chip.getAttribute("href"), true);
  });

  window.addEventListener("popstate", function () {
    load(location.pathname + location.search, false);
  });
})();
