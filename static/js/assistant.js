// Botlhami Assistant: asks the server for an answer from the help content.
// Everything is inserted with textContent, never innerHTML.
(function () {
  const box = document.getElementById("assistant");
  if (!box) return;
  const csrf = document.querySelector('meta[name="csrf-token"]')?.content;
  const log = document.getElementById("assistant-log");
  const form = document.getElementById("assistant-form");
  const input = document.getElementById("assistant-q");
  const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };
  const post = (url, data) => fetch(url, { method: "POST", headers: { "X-CSRFToken": csrf }, body: new URLSearchParams(data) }).then((r) => r.json());

  function bubble(cls, text) {
    const b = el("div", "bubble " + cls);
    b.appendChild(el("span", "text", text));
    log.appendChild(b);
    log.scrollTop = log.scrollHeight;
    return b;
  }

  function ask(q) {
    bubble("mine", q);
    const thinking = bubble("theirs typing", "…");
    post(box.dataset.ask, { q }).then((d) => {
      thinking.remove();
      const b = bubble("theirs", d.text);
      if (d.answered && d.url) {
        const more = el("a", "small", "Read more: " + d.title);
        more.href = d.url;
        b.appendChild(el("br"));
        b.appendChild(more);
        b.appendChild(el("span", "who", "From: " + d.source));
      }
      if (d.suggestions && d.suggestions.length) {
        const row = el("div", "chips");
        row.appendChild(el("span", "small muted", d.answered ? "Related:" : "Did you mean:"));
        d.suggestions.forEach((s) => { const c = el("button", "chip", s); c.type = "button"; c.addEventListener("click", () => ask(s)); row.appendChild(c); });
        b.appendChild(row);
      }
      if (d.id && d.answered) {
        const fb = el("div", "assistant-feedback small");
        fb.appendChild(el("span", "muted", "Did this help? "));
        [["yes", "Yes"], ["no", "No, talk to a person"]].forEach(([v, label]) => {
          const btn = el("button", "linklike", label);
          btn.type = "button";
          btn.addEventListener("click", () => {
            post(box.dataset.feedback.replace("/0/", "/" + d.id + "/"), { helpful: v });
            fb.textContent = v === "yes" ? "Thanks!" : "No problem: a consultant can help below.";
            if (v === "no") document.getElementById("human").scrollIntoView({ behavior: "smooth" });
          });
          fb.appendChild(btn);
          fb.appendChild(document.createTextNode("  ·  "));
        });
        fb.lastChild.remove();
        b.appendChild(fb);
      }
      if (!d.answered) {
        const go = el("button", "btn btn-sm mt-s", "Talk to a consultant");
        go.type = "button";
        go.addEventListener("click", () => document.getElementById("human").scrollIntoView({ behavior: "smooth" }));
        b.appendChild(go);
      }
      log.scrollTop = log.scrollHeight;
    }).catch(() => { thinking.remove(); bubble("theirs", "Sorry, I couldn't answer just now. Please try again, or chat with a consultant below."); });
  }

  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const q = input.value.trim();
    if (!q) return;
    input.value = "";
    ask(q);
  });
  document.querySelectorAll("#assistant-chips .chip").forEach((c) => c.addEventListener("click", () => ask(c.textContent)));
})();
