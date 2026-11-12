(() => {
  const host = document.getElementById("sensor-chart");
  const data = document.getElementById("sensor-chart-data");
  if (!host || !data) return;
  const points = JSON.parse(data.textContent);
  if (!points.length) {
    host.textContent = "Todavía no hay mediciones válidas.";
    return;
  }
  const svgNS = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(svgNS, "svg");
  svg.setAttribute("viewBox", "0 0 760 430");
  svg.setAttribute("aria-hidden", "true");
  const times = points.map(p => Date.parse(p.time));
  const minTime = Math.min(...times), maxTime = Math.max(...times);
  const startTime = minTime === maxTime ? minTime - 30 * 60 * 1000 : minTime;
  const endTime = minTime === maxTime ? maxTime + 30 * 60 * 1000 : maxTime;
  const x = t => 68 + 650 * (t - startTime) / (endTime - startTime);
  const timeLabel = new Intl.DateTimeFormat("es-PE", {day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit"});
  const add = (name, attrs, text) => {
    const el = document.createElementNS(svgNS, name);
    for (const [key, value] of Object.entries(attrs)) el.setAttribute(key, value);
    if (text) el.textContent = text;
    svg.appendChild(el);
    return el;
  };
  const series = [
    {key: "temperature", color: "#704332", label: "Temperatura °C", top: 42, bottom: 170},
    {key: "humidity", color: "#377466", label: "Humedad %", top: 245, bottom: 373},
  ];
  for (const s of series) {
    const values = points.map(p => p[s.key]);
    const padding = Math.max((Math.max(...values) - Math.min(...values)) * .18, s.key === "temperature" ? .3 : 1);
    const low = Math.floor((Math.min(...values) - padding) * 2) / 2;
    const high = Math.ceil((Math.max(...values) + padding) * 2) / 2;
    const y = value => s.bottom - ((value - low) / (high - low)) * (s.bottom - s.top);
    add("text", {x: 68, y: s.top - 15, fill: s.color, "font-size": 15, "font-weight": 700}, s.label);
    for (let step = 0; step <= 4; step++) {
      const value = low + (high - low) * step / 4;
      const ordinate = y(value);
      add("line", {x1: 68, x2: 718, y1: ordinate, y2: ordinate, stroke: "#d9cabe", "stroke-dasharray": step ? "4 5" : ""});
      add("text", {x: 58, y: ordinate + 4, fill: "#6d5b51", "font-size": 11, "text-anchor": "end"}, value.toFixed(1));
      const time = startTime + (endTime - startTime) * step / 4;
      const abscissa = x(time);
      add("line", {x1: abscissa, x2: abscissa, y1: s.top, y2: s.bottom, stroke: "#e9ded3", "stroke-dasharray": "4 5"});
      add("text", {x: abscissa, y: s.bottom + 18, fill: "#6d5b51", "font-size": 10, "text-anchor": step === 0 ? "start" : step === 4 ? "end" : "middle"}, timeLabel.format(new Date(time)));
    }
    const coordinates = points.map((p, i) => `${x(times[i]).toFixed(1)},${y(p[s.key]).toFixed(1)}`).join(" ");
    if (points.length > 1) add("polyline", {points: coordinates, fill: "none", stroke: s.color, "stroke-width": 2.5, "stroke-linecap": "round", "stroke-linejoin": "round"});
    points.forEach((p, i) => {
      const dot = add("circle", {cx: x(times[i]), cy: y(p[s.key]), r: 4, fill: s.color, stroke: "#fffdf8", "stroke-width": 1.5});
      const title = document.createElementNS(svgNS, "title");
      title.textContent = `${new Date(p.time).toLocaleString("es-PE")}: ${p[s.key]} ${s.key === "temperature" ? "°C" : "%"}`;
      dot.appendChild(title);
    });
  }
  host.appendChild(svg);
})();
