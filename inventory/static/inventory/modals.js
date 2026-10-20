(() => {
  let activeModal = null;
  let opening = false;
  let opener = null;
  let previousOverflow = "";

  function closeModal() {
    if (!activeModal) return;
    activeModal.remove();
    activeModal = null;
    document.body.style.overflow = previousOverflow;
    opener?.focus();
    opener = null;
  }

  document.addEventListener("click", async (event) => {
    const close = event.target.closest("[data-modal-close]");
    if (close && activeModal?.contains(close)) {
      event.preventDefault();
      closeModal();
      return;
    }

    const link = event.target.closest("a[data-modal-open]");
    if (!link || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    if (activeModal || opening) return;
    opening = true;
    opener = link;
    try {
      const response = await fetch(link.href, { credentials: "same-origin" });
      if (!response.ok || response.redirected) throw new Error("Formulario no disponible");
      const page = new DOMParser().parseFromString(await response.text(), "text/html");
      const modal = page.querySelector(".modal-backdrop");
      if (!modal) throw new Error("Ventana no disponible");
      activeModal = document.importNode(modal, true);
      const form = activeModal.querySelector("form");
      if (form) form.action = link.href;
      previousOverflow = document.body.style.overflow;
      document.body.style.overflow = "hidden";
      document.body.appendChild(activeModal);
      activeModal.querySelector("input, select, textarea, .modal-close")?.focus();
    } catch (_) {
      window.location.assign(link.href);
    } finally {
      opening = false;
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && activeModal) closeModal();
  });
})();
