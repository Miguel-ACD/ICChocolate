(() => {
  let activeModal = null;
  let opening = false;
  let opener = null;
  let previousOverflow = "";

  function initializeMovementFields(root) {
    const operation = root.querySelector("#id_type");
    const destination = root.querySelector("#id_destination");
    const field = destination?.closest(".field");
    if (!operation || !destination || !field) return;
    function syncDestination() {
      const transfer = operation.value === "TRASLADO";
      field.hidden = !transfer;
      destination.disabled = !transfer;
      destination.required = transfer;
      if (!transfer) destination.value = "";
    }
    operation.addEventListener("change", syncDestination);
    syncDestination();
  }

  function closeModal() {
    if (!activeModal) return;
    activeModal.remove();
    activeModal = null;
    document.body.style.overflow = previousOverflow;
    opener?.focus();
    opener = null;
  }

  document.addEventListener("click", async (event) => {
    if (!event.target.closest(".header-menu")) {
      document.querySelectorAll(".header-menu[open]").forEach(menu => menu.open = false);
    }
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
    document.querySelectorAll(".header-menu[open]").forEach(menu => menu.open = false);
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
      initializeMovementFields(activeModal);
      activeModal.querySelector("input, select, textarea, .modal-close")?.focus();
    } catch (_) {
      window.location.assign(link.href);
    } finally {
      opening = false;
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && activeModal) closeModal();
    if (event.key === "Escape") document.querySelectorAll(".header-menu[open]").forEach(menu => menu.open = false);
  });
  document.querySelectorAll(".header-menu").forEach(menu => menu.addEventListener("toggle", () => {
    if (menu.open) document.querySelectorAll(".header-menu[open]").forEach(other => { if (other !== menu) other.open = false; });
  }));
  initializeMovementFields(document);
})();
