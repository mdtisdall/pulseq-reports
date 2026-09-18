// Sequence diagram card: one lane chart with a button for each time window that
// cards/diagram.py gives. Moved from vb-pulseq report.js (seqChart and the
// data-view button code), generalized from one fixed set of views (first ADC, full,
// peak-TR) to any list of windows, some of which can share one set of lanes (a small
// file) and some of which each carry their own lane set (a file over the point
// budget). Unlike vb, this card never reads a PNS view: a caller that wants a PNS
// window builds it as an ordinary window (see waveforms.TimeWindow).
PulseqReport.registerCard("diagram", (section, data) => {
  const buttons = section.querySelectorAll("[data-window]");
  const laneSets = data.lane_sets;
  const windows = data.windows;

  // The lane set that the chart currently shows, and the window whose view is the
  // chart's current xDomain (what a zoom-control Reset returns to). Only a button that
  // changes the lane set (a call to setWindow) moves the xDomain, so only that kind of
  // click updates `initialWindow`; a same-lane-set click (setView) leaves it as is.
  let currentSet = windows[0].lane_set;
  let initialWindow = 0;

  function press(i) {
    for (const button of buttons) {
      button.setAttribute("aria-pressed", String(Number(button.dataset.window) === i));
    }
  }

  const chart = PulseqReport.laneChart({
    svg: document.getElementById(`${section.id}-diagram`),
    chart: document.getElementById(`${section.id}-chart`),
    tip: document.getElementById(`${section.id}-tip`),
    lanes: laneSets[currentSet].lanes,
    xDomain: windows[0].view_ms,
    extent: laneSets[currentSet].extent_ms,
    minSpan: 0.01,
    xLabel: "Time (ms)",
    cursorText: v => `t = ${v.toFixed(3)} ms`,
    // A zoom or pan leaves no button pressed; a reset (isInitial) presses the button of
    // the window whose view is the current xDomain.
    onViewChange: (view, isInitial) => {
      if (isInitial) {
        press(initialWindow);
      } else {
        for (const button of buttons) button.setAttribute("aria-pressed", "false");
      }
    },
  });

  for (const button of buttons) {
    const i = Number(button.dataset.window);
    button.addEventListener("click", () => {
      const w = windows[i];
      press(i);
      if (w.lane_set === currentSet) {
        chart.setView(w.view_ms);
      } else {
        currentSet = w.lane_set;
        chart.setWindow({
          lanes: laneSets[currentSet].lanes,
          xDomain: w.view_ms,
          extent: laneSets[currentSet].extent_ms,
        });
        initialWindow = i;
      }
    });
  }
});
