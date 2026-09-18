// PNS prediction card: the stimulation percent over time, full sequence and peak TR.
PulseqReport.registerCard("pns", (section, data) => {
  if (data.reason !== null) return;

  const pnsChart = PulseqReport.laneChart({
    svg: document.getElementById(`${section.id}-diagram`),
    chart: document.getElementById(`${section.id}-chart`),
    tip: document.getElementById(`${section.id}-tip`),
    lanes: data.lanes,
    xDomain: [0, data.end_ms],
    extent: [0, data.end_ms],
    minSpan: 0.1,
    // A zoom or pan leaves no preset pressed; Reset returns to the full preset.
    onViewChange: (view, isInitial) => {
      for (const b of section.querySelectorAll("[data-pns-view]")) {
        b.setAttribute("aria-pressed", String(isInitial && b.dataset.pnsView === "full"));
      }
    },
    xLabel: "Time (ms)",
    cursorText: v => `t = ${v.toFixed(3)} ms`,
  });

  for (const button of section.querySelectorAll("[data-pns-view]")) {
    button.addEventListener("click", () => {
      for (const b of section.querySelectorAll("[data-pns-view]")) {
        b.setAttribute("aria-pressed", String(b === button));
      }
      const peakTr = button.dataset.pnsView === "peak-tr";
      pnsChart.setView(peakTr ? data.peak_tr_ms : [0, data.end_ms]);
    });
  }
});
