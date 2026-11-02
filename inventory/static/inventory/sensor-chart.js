(() => {
  const host = document.getElementById("sensor-chart");
  const data = document.getElementById("sensor-chart-data");
  if (!host || !data) return;
  const points = JSON.parse(data.textContent);
  if (!points.length) {
    host.textContent = "Todavía no hay mediciones válidas en los últimos 7 días.";
    return;
  }
  const svgNS = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(svgNS, "svg");
  svg.setAttribute("viewBox", "0 0 720 280");
  svg.setAttribute("aria-hidden", "true");
  const times = points.map(p => Date.parse(p.time));
  const minTime = Math.min(...times), maxTime = Math.max(...times);
  const x = t => 48 + 640 * (maxTime === minTime ? .5 : (t - minTime) / (maxTime - minTime));
  const add = (name, attrs, text) => {
    const el = document.createElementNS(svgNS, name);
    for (const [key, value] of Object.entries(attrs)) el.setAttribute(key, value);
    if (text) el.textContent = text;
    svg.appendChild(el);
    return el;
  };
  const series = [
    {key: "temperature", color: "#704332", label: "Temperatura °C", top: 20, bottom: 115},
    {key: "humidity", color: "#377466", label: "Humedad %", top: 150, bottom: 245},
  ];
  for (const s of series) {
    const values = points.map(p => p[s.key]);
    const low = Math.floor(Math.min(...values) - 1), high = Math.ceil(Math.max(...values) + 1);
    add("text", {x: 48, y: s.top + 12, fill: s.color, "font-size": 14, "font-weight": 700}, s.label);
    add("line", {x1: 48, x2: 688, y1: s.bottom, y2: s.bottom, stroke: "#d9cabe"});
    add("text", {x: 4, y: s.bottom, fill: "#6d5b51", "font-size": 11}, String(low));
    add("text", {x: 4, y: s.top + 28, fill: "#6d5b51", "font-size": 11}, String(high));
    points.forEach((p, i) => {
      const cy = s.bottom - ((p[s.key] - low) / (high - low)) * (s.bottom - s.top - 25);
      const dot = add("circle", {cx: x(times[i]), cy, r: 3.6, fill: s.color});
      const title = document.createElementNS(svgNS, "title");
      title.textContent = `${new Date(p.time).toLocaleString("es-PE")}: ${p[s.key]} ${s.key === "temperature" ? "°C" : "%"}`;
      dot.appendChild(title);
    });
  }
  host.appendChild(svg);
})();
