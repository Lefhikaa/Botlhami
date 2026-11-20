// Light/dark theme. Loaded in <head> (not deferred) so the page never flashes
// the wrong colours. Follows the device setting until the person picks one.
(function () {
  const root = document.documentElement;
  const media = window.matchMedia ? window.matchMedia("(prefers-color-scheme: dark)") : null;
  let saved = null;
  try { saved = localStorage.getItem("botlhami-theme"); } catch (e) { /* storage blocked */ }
  const system = () => (media && media.matches ? "dark" : "light");
  const apply = (t) => { root.dataset.theme = t; };
  apply(saved === "dark" || saved === "light" ? saved : system());
  // Restore a collapsed sidebar before the first paint, too.
  try { if (localStorage.getItem("botlhami-sidebar") === "collapsed") root.dataset.sidebar = "collapsed"; } catch (e) { /* storage blocked */ }
  if (media && media.addEventListener) {
    media.addEventListener("change", () => { if (!saved) { apply(system()); label(); } });
  }
  function label() {
    const b = document.getElementById("theme-toggle");
    if (!b) return;
    const dark = root.dataset.theme === "dark";
    b.setAttribute("aria-pressed", String(dark));
    b.setAttribute("aria-label", dark ? "Switch to light mode" : "Switch to dark mode");
    if (b.querySelector(".lbl")) return; // the sidebar switch shows its state with aria-pressed
    b.title = dark ? "Light mode" : "Dark mode";
    b.querySelector("span").textContent = dark ? "☀" : "☾";
  }
  document.addEventListener("DOMContentLoaded", () => {
    const b = document.getElementById("theme-toggle");
    if (!b) return;
    b.hidden = false;
    label();
    b.addEventListener("click", () => {
      saved = root.dataset.theme === "dark" ? "light" : "dark";
      try { localStorage.setItem("botlhami-theme", saved); } catch (e) { /* storage blocked */ }
      apply(saved);
      label();
    });
  });
})();
