// Gradient spectrum card: Gx, Gy, Gz and RSS against frequency, with a linear/dB
// toggle and the acoustic resonance band of each target shaded in its color. A lane has
// `series` (one line for each group of targets) or its own `segments` (one group).
PulseqReport.registerCard("spectrum", (section, data) => {
  if (data.reason !== null) return;

  // The bands {lo, hi, color, target}: laneChart reads lo, hi and color.
  const bands = data.resonances;
  const hz = v => String(Number(v.toFixed(1)));
  // The dB scale: 20 log10 of each value relative to the largest RSS value of all the lines,
  // with a floor.
  const DB_FLOOR = data.db_floor;
  const linearLanes = data.lanes;
  const linesOf = lane => (Array.isArray(lane.series) ? lane.series : [lane]);
  let peak = 0;
  for (const line of linesOf(linearLanes[linearLanes.length - 1])) {
    for (const seg of line.segments) {
      for (const [, v] of seg) if (v > peak) peak = v;
    }
  }
  const toDb = v => (peak > 0 && v > 0
    ? Math.max(DB_FLOOR, 20 * Math.log10(v / peak)) : DB_FLOOR);
  const dbSegments = segments => segments.map(seg => seg.map(([f, v]) => [f, toDb(v)]));
  const dbTicks = [DB_FLOOR, DB_FLOOR / 2, 0];
  const dbLanes = linearLanes.map(lane => {
    const dbLane = {
      ...lane,
      unit: "dB",
      segments: dbSegments(lane.segments),
      domain: [DB_FLOOR, 0.05 * -DB_FLOOR],
      ticks: dbTicks,
      tick_labels: dbTicks.map(ChartMath.fmt),
    };
    if (Array.isArray(lane.series)) {
      dbLane.series = lane.series.map(s => ({...s, segments: dbSegments(s.segments)}));
    }
    return dbLane;
  });

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
    cursorText: f => `f = ${f.toFixed(0)} Hz` + bands
      .filter(b => f >= b.lo && f <= b.hi)
      .map(b => ` · resonance of ${b.target} ${hz(b.lo)}–${hz(b.hi)} Hz`)
      .join(""),
    bands,
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
