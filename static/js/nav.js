// Sidebar: collapse on desktop, slide-in drawer on phones, Ctrl/⌘+K to search.
(function () {
  const root = document.documentElement;
  const bar = document.getElementById("sidebar");
  if (!bar) return;
  const collapse = document.getElementById("sb-collapse");
  const open = document.getElementById("sb-open");
  const scrim = document.getElementById("sb-scrim");
  const search = document.getElementById("sb-q");
  const phone = window.matchMedia("(max-width: 900px)");

  function setCollapsed(on) {
    if (on) root.dataset.sidebar = "collapsed"; else delete root.dataset.sidebar;
    collapse.setAttribute("aria-expanded", String(!on));
    collapse.setAttribute("aria-label", on ? "Expand the menu" : "Collapse the menu");
    try { localStorage.setItem("botlhami-sidebar", on ? "collapsed" : "open"); } catch (e) { /* storage blocked */ }
  }
  function setDrawer(on) {
    bar.classList.toggle("open", on);
    scrim.hidden = !on;
    open.setAttribute("aria-expanded", String(on));
    if (on) bar.querySelector(".sb-item")?.focus();
  }

  collapse.setAttribute("aria-expanded", String(root.dataset.sidebar !== "collapsed"));
  collapse.addEventListener("click", () => {
    if (phone.matches) { setDrawer(false); return; }
    setCollapsed(root.dataset.sidebar !== "collapsed");
  });
  open.addEventListener("click", () => setDrawer(true));
  scrim.addEventListener("click", () => setDrawer(false));
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && bar.classList.contains("open")) { setDrawer(false); open.focus(); }
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
      e.preventDefault();
      if (phone.matches) setDrawer(true);
      if (root.dataset.sidebar === "collapsed") setCollapsed(false);
      search.focus();
      search.select();
    }
  });
  search.closest("form").addEventListener("click", () => {
    if (!phone.matches && root.dataset.sidebar === "collapsed") { setCollapsed(false); search.focus(); }
  });
  if (/Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent)) {
    const k = document.getElementById("kbd-mod");
    if (k) k.textContent = "⌘";
  }
})();
