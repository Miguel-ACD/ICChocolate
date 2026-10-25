(() => {
  const card = document.querySelector("[data-sensor-url]");
  if (!card) return;
  const fields = {
    status: document.getElementById("sensor-status"),
    temperature: document.getElementById("sensor-temperature"),
    humidity: document.getElementById("sensor-humidity"),
    updated: document.getElementById("sensor-updated"),
    communication: document.getElementById("sensor-communication"),
  };
  let lastReading = null;
  let staleAfter = 180;
  let serverOffset = 0;
  let connectionFailed = false;

  function display() {
    if (lastReading) {
      fields.temperature.textContent = Number(lastReading.temperature_c).toFixed(2).replace(/\.00$/, "");
      fields.humidity.textContent = `${Number(lastReading.humidity_percent).toFixed(2).replace(/\.00$/, "")} %`;
      fields.updated.textContent = `Última actualización: ${new Date(lastReading.received_at).toLocaleString("es-PE")}`;
    }
    const age = lastReading ? (Date.now() + serverOffset - Date.parse(lastReading.received_at)) / 1000 : 0;
    const state = connectionFailed ? "error" : !lastReading ? "waiting" : age > staleAfter ? "stale" : "online";
    card.dataset.state = state;
    fields.status.textContent = {error: "Sin comunicación", waiting: "Esperando sensor", stale: "Lectura antigua", online: "En línea"}[state];
    fields.communication.textContent = {error: "No se pudo consultar el servidor. Reintentando…", waiting: "Esperando sensor", stale: "El sensor no envía datos recientes.", online: "Comunicación activa"}[state];
  }

  async function refresh() {
    try {
      const response = await fetch(card.dataset.sensorUrl, {credentials: "same-origin", cache: "no-store"});
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      lastReading = data.reading;
      staleAfter = data.stale_after_seconds;
      serverOffset = Date.parse(data.server_time) - Date.now();
      connectionFailed = false;
    } catch (_) {
      connectionFailed = true;
    }
    display();
  }

  display();
  refresh();
  setInterval(refresh, 15000);
  setInterval(display, 1000);
})();
