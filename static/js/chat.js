// Live chat for clients and the agent console. Polls JSON endpoints; all text is
// inserted with textContent, never innerHTML, so messages can't inject markup.
(function () {
  const csrf = document.querySelector('meta[name="csrf-token"]')?.content;
  const post = (url, data) =>
    fetch(url, { method: "POST", headers: { "X-CSRFToken": csrf }, body: new URLSearchParams(data || {}) }).then((r) => r.json());
  const el = (tag, cls, text) => { const e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; };

  // ---- one conversation (used by both sides) ----
  function Conversation(urls, role, onStatus) {
    let last = 0, timer = null, stopped = false;
    const log = document.getElementById("chat-log");
    function render(m) {
      const mine = (role === "customer" && m.kind === "customer") || (role === "agent" && m.kind === "agent");
      const row = el("div", "bubble " + (m.kind === "system" ? "system" : mine ? "mine" : "theirs"));
      if (m.kind !== "system") row.appendChild(el("span", "who", m.name + " · " + m.at));
      row.appendChild(el("span", "text", m.body));
      log.appendChild(row);
    }
    function tick() {
      if (stopped) return;
      fetch(urls.poll + "?after=" + last, { headers: { Accept: "application/json" } })
        .then((r) => r.json())
        .then((d) => {
          d.messages.forEach((m) => { render(m); last = m.id; });
          if (d.messages.length) log.scrollTop = log.scrollHeight;
          onStatus && onStatus(d);
        })
        .catch(() => {})
        .finally(() => { if (!stopped) timer = setTimeout(tick, 3000); });
    }
    return {
      start() { log.textContent = ""; last = 0; stopped = false; tick(); },
      stop() { stopped = true; clearTimeout(timer); },
      send(body) { return post(urls.send, { body }).then(() => { clearTimeout(timer); tick(); }); },
      close() { return post(urls.close).then(() => { clearTimeout(timer); tick(); }); },
    };
  }

  function wireForm(getConv) {
    const form = document.getElementById("chat-form"), input = document.getElementById("chat-body");
    form.addEventListener("submit", (e) => {
      e.preventDefault();
      const body = input.value.trim();
      if (!body || !getConv()) return;
      input.value = "";
      getConv().send(body);
    });
    input.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); form.requestSubmit(); } });
  }

  // ---- client page ----
  const client = document.getElementById("chat");
  if (client) {
    const status = document.getElementById("chat-status");
    const labels = { waiting: "Waiting for a consultant…", active: "Connected to a consultant", offline: "Message left. We'll reply by email.", closed: "Chat ended" };
    const conv = Conversation(client.dataset, "customer", (d) => {
      status.textContent = labels[d.status] || "";
      if (d.status === "closed") {
        document.getElementById("chat-form").hidden = true;
        document.getElementById("chat-end").hidden = true;
        document.getElementById("chat-new").hidden = false;
        document.getElementById("chat-rating").hidden = d.rating != null;
        conv.stop();
      }
    });
    wireForm(() => conv);
    document.getElementById("chat-end").addEventListener("click", () => conv.close());
    document.querySelectorAll("[data-rate-value]").forEach((b) =>
      b.addEventListener("click", () => post(client.dataset.rate, { rating: b.dataset.rateValue }).then(() => {
        document.getElementById("chat-rating").replaceChildren(el("p", "ok", "Thank you for your feedback."));
      })));
    conv.start();
  }

  // ---- agent console ----
  const consoleEl = document.getElementById("console");
  if (consoleEl) {
    const u = (tpl, id) => tpl.replace("/0/", "/" + id + "/");
    let current = null, currentId = null;
    const pane = document.getElementById("pane"), empty = document.getElementById("pane-empty");

    function open(id, name) {
      if (current) current.stop();
      currentId = id;
      current = Conversation({ poll: u(consoleEl.dataset.poll, id), send: u(consoleEl.dataset.send, id), close: u(consoleEl.dataset.close, id) }, "agent", (d) => {
        document.getElementById("chat-form").hidden = d.status === "closed";
      });
      document.getElementById("pane-title").textContent = name;
      pane.hidden = false; empty.hidden = true;
      current.start();
    }

    function item(c, inQueue) {
      const li = el("li", "chat-item" + (c.id === currentId ? " active" : ""));
      const head = el("div", "spread");
      head.appendChild(el("strong", null, c.name));
      if (c.unread) head.appendChild(el("span", "badge", String(c.unread)));
      li.appendChild(head);
      li.appendChild(el("span", "small muted", c.topic + (inQueue ? " · waiting " + c.waiting_min + " min" + (c.started_as !== "open" && c.started_as !== "busy" ? " · offline message" : "") : "")));
      if (c.last) li.appendChild(el("span", "small", c.last));
      if (inQueue) {
        const b = el("button", "btn btn-primary btn-sm", "Accept");
        b.addEventListener("click", () => post(u(consoleEl.dataset.accept, c.id)).then((r) => { if (r.ok) open(c.id, c.name); refresh(); }));
        li.appendChild(b);
      } else {
        li.tabIndex = 0;
        li.addEventListener("click", () => open(c.id, c.name));
        li.addEventListener("keydown", (e) => { if (e.key === "Enter") open(c.id, c.name); });
      }
      return li;
    }

    const serviceText = { open: "Service open", busy: "All agents are at capacity", closed: "Outside working hours", offline: "No agents available" };
    function refresh() {
      fetch(consoleEl.dataset.state).then((r) => r.json()).then((d) => {
        document.getElementById("queue").replaceChildren(...d.queue.map((c) => item(c, true)));
        document.getElementById("mine").replaceChildren(...d.mine.map((c) => item(c, false)));
        document.getElementById("queue-count").textContent = d.queue.length;
        document.getElementById("mine-count").textContent = d.mine.length;
        document.getElementById("service-state").textContent = serviceText[d.service] + " · " + d.agents_online + " agent(s) online";
      }).catch(() => {});
    }
    wireForm(() => current);
    document.getElementById("chat-end").addEventListener("click", () => current && current.close().then(refresh));
    const presence = document.getElementById("presence");
    presence.addEventListener("change", () => post(presence.dataset.url, { available: presence.checked ? "1" : "0" }).then(() => {
      document.getElementById("presence-label").textContent = presence.checked ? "Available" : "Away";
      refresh();
    }));
    refresh();
    setInterval(refresh, 4000);
  }
})();
