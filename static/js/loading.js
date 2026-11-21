// Page loading feedback: a thin bar across the top while the next page loads,
// and a busy state on the button that sent a form (which also stops double taps).
(function () {
  const bar = document.createElement("div");
  bar.id = "page-loader";
  bar.setAttribute("role", "progressbar");
  bar.setAttribute("aria-label", "Loading");
  bar.hidden = true;
  let showTimer = null, trickle = null, giveUp = null, width = 0;

  function set(w) { width = w; bar.style.transform = "scaleX(" + w + ")"; }
  function start() {
    if (showTimer || !bar.hidden) return;
    // Wait a moment, so quick pages don't flash a bar.
    showTimer = setTimeout(() => {
      bar.hidden = false;
      bar.classList.remove("done");
      set(0.08);
      trickle = setInterval(() => set(width + (0.9 - width) * 0.08), 250);
    }, 120);
    // A link that turned out to be a download never leaves the page: stop after a while.
    giveUp = setTimeout(stop, 12000);
  }
  function stop() {
    clearTimeout(showTimer); clearTimeout(giveUp); clearInterval(trickle);
    showTimer = trickle = giveUp = null;
    if (!bar.hidden) {
      bar.classList.add("done");
      set(1);
      setTimeout(() => { bar.hidden = true; set(0); }, 300);
    }
    document.querySelectorAll("[data-loading]").forEach((b) => {
      b.removeAttribute("data-loading");
      b.removeAttribute("aria-busy");
      b.disabled = false;
    });
  }

  function isDownload(a) {
    return a.hasAttribute("download") || a.hasAttribute("data-no-loader") ||
      /\/(download|export|document)\b|\.(pdf|csv|xlsx?|docx?|zip|png|jpe?g)(\?|$)/i.test(a.pathname + a.search);
  }

  document.addEventListener("click", (e) => {
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    const a = e.target.closest("a[href]");
    if (!a || a.target === "_blank" || isDownload(a)) return;
    if (a.origin !== location.origin) return;
    if (a.pathname === location.pathname && a.search === location.search && a.hash) return; // same-page jump
    start();
  });

  document.addEventListener("submit", (e) => {
    if (e.defaultPrevented) return;
    const form = e.target;
    if (form.hasAttribute("data-no-loader") || form.target === "_blank") return;
    const button = e.submitter || form.querySelector("button[type=submit], button:not([type])");
    if (button && button.hasAttribute("data-loading")) { e.preventDefault(); return; } // already sending
    start();
    if (button) {
      button.setAttribute("data-loading", "");
      button.setAttribute("aria-busy", "true");
      // Disable after the browser has read the button's name and value.
      setTimeout(() => { button.disabled = true; }, 0);
    }
  });

  // Coming back with the Back button restores the old page from memory: reset it.
  window.addEventListener("pageshow", stop);
  document.addEventListener("DOMContentLoaded", () => document.body.prepend(bar));
})();
