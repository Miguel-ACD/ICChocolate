(() => {
  const card = document.querySelector("[data-sensor-url]");
  if (!card) return;
  const fields = {
    status: document.getElementById("sensor-status"),
    temperature: document.getElementById("sensor-temperature"),
    humidity: document.getElementById("sensor-humidity"),
    updated: document.getElementById("sensor-updated"),
    communication: document.getElementById("sensor-communication"),
    zone: document.getElementById("sensor-zone"),
  };
  let lastReading = null;
  let lastCycle = null;
  let currentZone = null;
  let staleAfter = 180;
  let serverOffset = 0;
  let connectionFailed = false;

  function display() {
    if (lastReading) {
      fields.temperature.textContent = Number(lastReading.temperature_c).toFixed(2).replace(/\.00$/, "");
      fields.humidity.textContent = `${Number(lastReading.humidity_percent).toFixed(2).replace(/\.00$/, "")} %`;
      fields.updated.textContent = `Última actualización: ${new Date(lastReading.measured_at || lastReading.received_at).toLocaleString("es-PE")}`;
    }
    if (fields.zone) fields.zone.textContent = `Zona actual: ${currentZone || "sin asignar"}${lastReading?.location ? ` · Última lectura de ${lastReading.location}` : ""}`;
    const age = lastReading ? (Date.now() + serverOffset - Date.parse(lastReading.measured_at || lastReading.received_at)) / 1000 : 0;
    const state = connectionFailed ? "error" : !lastReading ? "waiting" : age > staleAfter ? "stale" : "online";
    card.dataset.state = state;
    fields.status.textContent = {error: "Sin comunicación", waiting: "Esperando sensor", stale: "Lectura antigua", online: "En línea"}[state];
    const cycleAge = lastCycle ? (Date.now() + serverOffset - Date.parse(lastCycle.received_at)) / 1000 : Infinity;
    fields.communication.textContent = connectionFailed
      ? "No se pudo consultar el servidor. Reintentando…"
      : !lastCycle ? "Esperando sensor"
      : lastCycle && cycleAge <= staleAfter && lastCycle.status === "INVALIDO"
        ? `Comunicación activa; último ciclo inválido (${lastCycle.sample_count}/4 muestras).`
        : lastCycle && cycleAge <= staleAfter ? "Comunicación activa" : "El sensor no envía datos recientes.";
  }

  async function refresh() {
    try {
      const response = await fetch(card.dataset.sensorUrl, {credentials: "same-origin", cache: "no-store"});
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const data = await response.json();
      lastReading = data.reading;
      lastCycle = data.last_cycle;
      currentZone = data.current_location;
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
