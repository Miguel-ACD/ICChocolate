(() => {
  const launcher = document.getElementById("chat-launcher");
  const windowPanel = document.getElementById("chat-window");
  const close = document.getElementById("chat-close");
  const form = document.getElementById("chat-form");
  const input = document.getElementById("chat-question");
  const messages = document.getElementById("chat-messages");
  if (!launcher || !windowPanel || !form) return;
  let lastTopic = null;
  function show(open) {
    windowPanel.hidden = !open;
    launcher.setAttribute("aria-expanded", String(open));
    launcher.setAttribute("aria-label", open ? "Cerrar chat" : "Abrir chat");
    if (open) input.focus(); else launcher.focus();
  }
  launcher.addEventListener("click", () => show(windowPanel.hidden));
  close.addEventListener("click", () => show(false));
  document.addEventListener("keydown", event => {
    if (event.key === "Escape" && !windowPanel.hidden) show(false);
  });
  const bubble = (content, className) => {
    const paragraph = document.createElement("p");
    paragraph.className = `chat-bubble ${className}`;
    paragraph.textContent = content;
    messages.appendChild(paragraph);
    messages.scrollTop = messages.scrollHeight;
    return paragraph;
  };
  form.addEventListener("submit", async event => {
    event.preventDefault();
    const question = input.value.trim();
    if (!question) return;
    bubble(question, "chat-question");
    input.value = "";
    const button = form.querySelector("button");
    button.disabled = true;
    const pending = bubble("Consultando…", "chat-answer");
    try {
      const csrf = form.querySelector("input[name='csrfmiddlewaretoken']")?.value || "";
      const response = await fetch("/api/v1/chat", {
        method: "POST", credentials: "same-origin",
        headers: {"Content-Type": "application/json", "X-CSRFToken": csrf},
        body: JSON.stringify({question, context: lastTopic}),
      });
      const data = await response.json();
      pending.textContent = response.ok ? data.answer : (data.error || "No pude responder. Inténtalo de nuevo.");
      lastTopic = response.ok ? (data.topic || null) : null;
      if (response.ok && data.sources?.length) {
        const sources = document.createElement("span");
        sources.className = "chat-sources";
        sources.append("Abrir: ");
        let count = 0;
        data.sources.forEach(source => {
          if (!source.url?.startsWith("/")) return;
          if (count++) sources.append(" · ");
          const link = document.createElement("a");
          link.href = source.url;
          link.textContent = source.label;
          sources.appendChild(link);
        });
        pending.appendChild(sources);
      }
    } catch (_) {
      pending.textContent = "No hay conexión con el chat. Inténtalo de nuevo.";
    } finally {
      button.disabled = false;
      input.focus();
      messages.scrollTop = messages.scrollHeight;
    }
  });
})();
