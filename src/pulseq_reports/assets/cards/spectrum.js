// Gradient spectrum card: Gx, Gy, Gz and RSS against frequency, with a linear/dB
// toggle and the acoustic resonance bands shaded.
PulseqReport.registerCard("spectrum", (section, data) => {
  if (data.reason !== null) return;

  const bands = data.resonances.map(
    r => [r.frequency_hz - r.bandwidth_hz / 2, r.frequency_hz + r.bandwidth_hz / 2]);
  // The dB scale: 20 log10 of each value relative to the largest RSS value, with a floor.
  const DB_FLOOR = data.db_floor;
  const linearLanes = data.lanes;
  const rssPoints = linearLanes[linearLanes.length - 1].segments[0];
  const peak = Math.max(...rssPoints.map(([, v]) => v));
  const toDb = v => (peak > 0 && v > 0
    ? Math.max(DB_FLOOR, 20 * Math.log10(v / peak)) : DB_FLOOR);
  const dbTicks = [DB_FLOOR, DB_FLOOR / 2, 0];
  const dbLanes = linearLanes.map(lane => ({
    ...lane,
    unit: "dB",
    segments: lane.segments.map(seg => seg.map(([f, v]) => [f, toDb(v)])),
    domain: [DB_FLOOR, 0.05 * -DB_FLOOR],
    ticks: dbTicks,
    tick_labels: dbTicks.map(ChartMath.fmt),
  }));

  const svg = document.getElementById(`${section.id}-diagram`);
  const ariaLabel = svg.getAttribute("aria-label");
  const spectrumChart = PulseqReport.laneChart({
    svg,
    chart: document.getElementById(`${section.id}-chart`),
    tip: document.getElementById(`${section.id}-tip`),
    lanes: linearLanes,
    xDomain: [0, data.max_frequency_hz],
    minSpan: 50,
    xLabel: "Frequency (Hz)",
    cursorText: f => {
      const band = bands.find(([lo, hi]) => f >= lo && f <= hi);
      return `f = ${f.toFixed(0)} Hz` + (band ? ` · forbidden ${band[0]}–${band[1]} Hz` : "");
    },
    bands,
    bandStyle: "fill:var(--critical);fill-opacity:0.14",
  });

  for (const button of section.querySelectorAll("[data-scale]")) {
    button.addEventListener("click", () => {
      for (const b of section.querySelectorAll("[data-scale]")) {
        b.setAttribute("aria-pressed", String(b === button));
      }
      const db = button.dataset.scale === "db";
      spectrumChart.setLanes(db ? dbLanes : linearLanes);
      svg.setAttribute("aria-label", db ? `${ariaLabel}, in dB relative to the RSS peak` : ariaLabel);
    });
  }
});
