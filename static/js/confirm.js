// Ask before submitting forms marked data-confirm (inline handlers are blocked by the CSP).
document.addEventListener("submit", function (e) {
  var msg = e.target.getAttribute && e.target.getAttribute("data-confirm");
  if (msg && !window.confirm(msg)) e.preventDefault();
});
