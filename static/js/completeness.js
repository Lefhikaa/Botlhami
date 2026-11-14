// Live completeness meter for the idea form. Mirrors Idea.missing_items() on the server.
(function () {
  const form = document.querySelector("form[data-completeness]");
  if (!form) return;
  const val = (name) => (form.elements[name] ? form.elements[name].value.trim() : "");
  const checks = [
    () => val("title"), () => val("sector"), () => val("maturity"), () => val("location"),
    () => val("problem").length >= 50, () => val("solution").length >= 50,
    () => val("beneficiaries"), () => val("impact"), () => val("jobs") !== "", () => val("budget") !== "",
    () => form.querySelectorAll('input[name="sdgs"]:checked').length > 0,
    () => val("team"), () => form.elements["ip_declared"] && form.elements["ip_declared"].checked,
  ];
  const bar = document.getElementById("meter-bar");
  const label = document.getElementById("meter-label");
  function update() {
    const ok = checks.filter((c) => c()).length;
    bar.style.width = Math.round((ok / checks.length) * 100) + "%";
    label.textContent = ok + " of " + checks.length + " required items complete";
  }
  form.addEventListener("input", update);
  form.addEventListener("change", update);
  update();
})();
