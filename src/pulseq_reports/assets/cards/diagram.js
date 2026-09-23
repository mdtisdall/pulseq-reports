// Sequence diagram card: one lane chart with a button for each time window that
// cards/diagram.py gives. Unlike the old card, there are no lane sets and no point
// budget: cards/diagram.py sends the compressed block and event tables of each file
// that at least one window uses (diagram_data.diagram_tables), and this script
// decodes them (base64 -> gzip -> typed arrays -> SeqLanes.decode) into a model for
// each file, once, on first use. The chart's `lanesFor` hook (lane_chart.js) then
// asks SeqLanes.lanesFor for the lanes of the current view on every render: the exact
// waveform when the view has few enough points, or the minimum and the maximum of
// each lane in each of the plot's time bins otherwise. The status line under the
// chart (`{card_id}-mode`) says which of the two the current render shows.
//
// A file's tables can be large (up to 10^7 blocks), so decoding runs only for the
// file of the first window at start, and for another file the first time a button
// selects one of its windows; each decoded model is kept in `models` (by file
// index), so a file already shown is not decoded twice. While a file decodes, the
// status line shows "Loading..." and the window buttons are disabled.
PulseqReport.registerCard("diagram", async (section, data) => {
  const buttons = section.querySelectorAll("[data-window]");
  const statusEl = document.getElementById(`${section.id}-mode`);
  const files = data.files;
  const windows = data.windows;
  const models = new Array(files.length).fill(null);

  function setButtonsDisabled(disabled) {
    for (const button of buttons) button.disabled = disabled;
  }

  function showStatus(exact, bins) {
    statusEl.textContent = exact
      ? "Exact waveform."
      : `Minimum and maximum in each of ${bins} time bins. Zoom in to see the exact waveform.`;
  }

  // The typed array for one table entry {dtype, length, data}: base64 -> gzip bytes
  // -> DecompressionStream -> the typed array for its dtype. Throws for a dtype this
  // script does not know, and when the decompressed length does not match `length`
  // (a sign that the table or the decode is wrong).
  async function decodeTable(entry) {
    // A plain loop: the text can be tens of MB, and a callback for each character
    // (Uint8Array.from with a map function) is much slower.
    const text = atob(entry.data);
    const bytes = new Uint8Array(text.length);
    for (let i = 0; i < text.length; i++) bytes[i] = text.charCodeAt(i);
    const buffer = await new Response(
      new Blob([bytes]).stream().pipeThrough(new DecompressionStream("gzip"))
    ).arrayBuffer();
    const ctor = {
      uint8: Uint8Array,
      uint16: Uint16Array,
      uint32: Uint32Array,
      float64: Float64Array,
    }[entry.dtype];
    if (!ctor) throw new Error(`diagram card: unknown table dtype "${entry.dtype}"`);
    const array = new ctor(buffer);
    if (array.length !== entry.length) {
      throw new Error(
        `diagram card: table length ${array.length} does not match the given length ` +
          `${entry.length}`
      );
    }
    return array;
  }

  // The decoded SeqLanes model of file `fileIndex`, from the cache when it is
  // already there. Decodes every one of the file's tables in parallel.
  async function decodeFile(fileIndex) {
    if (models[fileIndex]) return models[fileIndex];
    const file = files[fileIndex];
    const names = Object.keys(file.tables);
    const arrays = await Promise.all(names.map(name => decodeTable(file.tables[name])));
    const tables = {};
    names.forEach((name, i) => {
      tables[name] = arrays[i];
    });
    const model = SeqLanes.decode(data.format, tables, file.lanes);
    models[fileIndex] = model;
    return model;
  }

  // The window whose view is the chart's current xDomain (what a zoom-control Reset
  // returns to). Only a button that switches to another file's model moves the
  // xDomain, so only that kind of click updates `initialWindow`; a same-file click
  // (setView) leaves it as is.
  let initialWindow = 0;
  let currentFileIndex = windows[0].file;

  statusEl.textContent = "Loading…";
  setButtonsDisabled(true);
  // The first file's decode failure is not caught here: it propagates out of this
  // async init, so page.js shows the card's usual "could not be drawn" note (there
  // is no chart to fall back to without a first model).
  let current = await decodeFile(currentFileIndex);
  setButtonsDisabled(false);

  function press(i) {
    for (const button of buttons) {
      button.setAttribute("aria-pressed", String(Number(button.dataset.window) === i));
    }
  }

  const chart = PulseqReport.laneChart({
    svg: document.getElementById(`${section.id}-diagram`),
    chart: document.getElementById(`${section.id}-chart`),
    tip: document.getElementById(`${section.id}-tip`),
    // Only its length (the number of lanes) matters here: lane_chart.js reads it for
    // the SVG height before the first render, which then replaces it with the
    // provider's own lanes. `current.lanesMeta` already has the right count, so
    // building it needs no SeqLanes.lanesFor call.
    lanes: current.lanesMeta,
    lanesFor: (view, bins) => {
      const r = SeqLanes.lanesFor(current, view, bins);
      showStatus(r.exact, bins);
      return r.lanes;
    },
    xDomain: windows[0].view_ms,
    extent: [0, current.durationS * 1000],
    minSpan: 0.01,
    xLabel: "Time (ms)",
    cursorText: v => `t = ${v.toFixed(3)} ms`,
    // A zoom or pan leaves no button pressed; a reset (isInitial) presses the button
    // of the window whose view is the current xDomain.
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
    button.addEventListener("click", async () => {
      const w = windows[i];
      if (w.file === currentFileIndex) {
        press(i);
        chart.setView(w.view_ms);
        return;
      }
      setButtonsDisabled(true);
      statusEl.textContent = "Loading…";
      let model;
      try {
        model = await decodeFile(w.file);
      } catch (error) {
        // A later file's decode failure is shown in the status line instead of
        // being rethrown: the chart already has a model and a view to keep showing,
        // so the card stays usable instead of being replaced by the "could not be
        // drawn" note.
        statusEl.textContent = `Could not load "${files[w.file].name}": ${error.message}`;
        setButtonsDisabled(false);
        return;
      }
      press(i);
      current = model;
      currentFileIndex = w.file;
      // As for the first render, only the number of lanes is read before the render
      // replaces them with the provider's lanes.
      chart.setWindow({
        lanes: current.lanesMeta,
        xDomain: w.view_ms,
        extent: [0, current.durationS * 1000],
      });
      initialWindow = i;
      setButtonsDisabled(false);
    });
  }
});
