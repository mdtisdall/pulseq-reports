// Sequence diagram card: one lane chart with a button for each time window that
// cards/diagram.py gives, and lane-group toggle buttons (RF, ADC, Gradients, and PNS
// when at least one file has PNS data, docs/plans/diagram-lanes.md section 4.5, item
// 3). Unlike the old card, there are no lane sets and no point budget: cards/diagram.py
// sends the compressed block and event tables of each file that at least one window
// uses (diagram_data.diagram_tables), and this script decodes them (base64 -> gzip ->
// typed arrays -> SeqLanes.decode) into a model for each file, once, on first use. A
// file entry with a "pns" key also gets its two stored-level tables decoded and a
// PnsLanes.decode model built from them, next to the SeqLanes model.
//
// The chart's `lanesFor` hook (lane_chart.js) asks SeqLanes.lanesFor for the six
// waveform lanes of the current view on every render (the exact waveform when the view
// has few enough points, or the minimum and the maximum of each lane in each of the
// plot's time bins otherwise); when the Gradients group is visible, appends the |G|
// lane (GLanes.lanesFor, docs/plans/diagram-lanes.md phase 5) after gz, building the
// file's GLanes model the first time a render needs it (a hidden Gradients group costs
// no |G| computation, the same rule the PNS lane already follows); and, when the PNS
// group is visible and the current file has PNS data, appends the PNS lane from
// PnsLanes.lanesFor after that. A hidden PNS group costs no PNS computation: `lanesFor`
// never calls PnsLanes.lanesFor for it. The status line under the chart
// (`{card_id}-mode`) says which data drew the waveform lanes, then, when the PNS lane
// is drawn, PnsLanes.statusText's sentence for it.
//
// A file's tables can be large (up to 10^7 blocks), so decoding runs only for the
// file of the first window at start, and for another file the first time a button
// selects one of its windows; each decoded model is kept in `models` (by file
// index), so a file already shown is not decoded twice. While a file decodes, the
// status line shows "Loading..." and the window buttons are disabled.
PulseqReport.registerCard("diagram", async (section, data) => {
  const buttons = section.querySelectorAll("[data-window]");
  const statusEl = document.getElementById(`${section.id}-mode`);
  const groupControls = document.getElementById(`${section.id}-groups`);
  const files = data.files;
  const windows = data.windows;
  const models = new Array(files.length).fill(null);

  function setButtonsDisabled(disabled) {
    for (const button of buttons) button.disabled = disabled;
  }

  // `pnsResult` is the return of `PnsLanes.lanesFor` when the PNS lane was drawn this
  // render, else null (the PNS group is hidden, or the current file has no PNS data):
  // then the status line is the SeqLanes sentence alone, as it was before this lane
  // existed. `onRaster` is `current.pns.model.onRaster`, read by the caller so this
  // function itself never reads `current`.
  function showStatus(exact, bins, pnsResult, onRaster) {
    let text = exact
      ? "Exact waveform."
      : `Minimum and maximum in each of ${bins} time bins. Zoom in to see the exact waveform.`;
    if (pnsResult) text += ` ${PnsLanes.statusText(pnsResult, onRaster)}`;
    statusEl.textContent = text;
  }

  // The typed array for one table entry {dtype, length, data}: base64 -> gzip bytes
  // -> DecompressionStream -> the typed array for its dtype. Throws for a dtype this
  // script does not know, and when the decompressed length does not match `length`
  // (a sign that the table or the decode is wrong). "float32" is the PNS stored
  // level's dtype (plan section 4.4); the six diagram tables never use it.
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
      float32: Float32Array,
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

  // The decoded model of file `fileIndex`, from the cache when it is already there:
  // `{seq, pns, g}`, `seq` the SeqLanes model (as before), `pns` either null (the file
  // has no "pns" key) or `{model, laneMeta}`, the PnsLanes model and its lane object
  // without segments (PnsLanes.laneMeta(file.pns.summary), built once here so a render
  // never rebuilds it), and `g` the |G| lane's own `{model, laneMeta}` pair, built
  // lazily by `lanesFor` (below) the first time a render needs it: `g` starts null
  // here, unlike `pns`, because GLanes.decode needs no data beyond the diagram tables
  // already decoded below, so there is nothing to fetch in parallel with them, and
  // building it costs a pass over the file's blocks that a render with the Gradients
  // group hidden should not pay for. Decodes every one of the file's diagram tables,
  // and, when the file has PNS data, its two stored-level tables, all in parallel; the
  // diagram tables are reused for both SeqLanes.decode and PnsLanes.decode (a PNS
  // model reads grad_*/duration_* out of the same tables, module doc of
  // pns_lanes.js).
  async function decodeFile(fileIndex) {
    if (models[fileIndex]) return models[fileIndex];
    const file = files[fileIndex];
    const names = Object.keys(file.tables);
    const tablesPromise = Promise.all(names.map(name => decodeTable(file.tables[name])));
    const pnsLevelsPromise = file.pns
      ? Promise.all([decodeTable(file.pns.levels.min), decodeTable(file.pns.levels.max)])
      : null;
    const [arrays, pnsLevels] = await Promise.all([tablesPromise, pnsLevelsPromise]);
    const tables = {};
    names.forEach((name, i) => {
      tables[name] = arrays[i];
    });
    const seqModel = SeqLanes.decode(data.format, tables, file.lanes);
    let pns = null;
    if (file.pns) {
      const [levelMin, levelMax] = pnsLevels;
      const pnsData = { ...file.pns, levels: { min: levelMin, max: levelMax } };
      pns = {
        model: PnsLanes.decode(tables, pnsData),
        laneMeta: PnsLanes.laneMeta(file.pns.summary),
      };
    }
    const model = { seq: seqModel, pns, g: null };
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

  // Lane groups (plan section 4.5, item 3): RF, ADC and Gradients always, PNS only
  // when at least one file has PNS data (whether or not the file shown first is one
  // of them: switching to such a file later still finds the PNS group and its
  // button). All visible at start, so the PNS group (when present) is on by default.
  // `groups` never changes after `laneChart` is called (lane_chart.js), matching that
  // "at least one file" is fixed once the card is built.
  const hasPns = files.some(f => f.pns);
  const groups = [
    { id: "rf", label: "RF", laneIds: ["rf_mag", "rf_phase"], visible: true },
    { id: "adc", label: "ADC", laneIds: ["adc"], visible: true },
    { id: "gradients", label: "Gradients", laneIds: ["gx", "gy", "gz", "gmag"], visible: true },
  ];
  if (hasPns) groups.push({ id: "pns", label: "PNS", laneIds: ["pns"], visible: true });

  // Only its length (the number of lanes) matters here: lane_chart.js reads it for
  // the SVG height before the first render, which then replaces it with the
  // provider's own lanes. But `laneChart` also reads each lane's own `id` for this
  // very first count, through `groups`/`visibleLanes` (chart_math.js), before that
  // first render ever runs -- so the |G| placeholder needs a real `id`, "gmag", not
  // an empty object or null. `current.seq.lanesMeta`, plus that placeholder (always
  // drawn on the first render: the Gradients group is visible by default, and
  // `lanesFor` below builds `current.g` the moment that render asks for it) and the
  // PNS lane meta when the first file has one, already has the right count, so
  // building it needs no GLanes.decode, SeqLanes.lanesFor or PnsLanes.lanesFor call.
  const initialLanes = current.seq.lanesMeta.concat(
    [{ id: "gmag" }],
    current.pns ? [current.pns.laneMeta] : []
  );

  const chart = PulseqReport.laneChart({
    svg: document.getElementById(`${section.id}-diagram`),
    chart: document.getElementById(`${section.id}-chart`),
    tip: document.getElementById(`${section.id}-tip`),
    lanes: initialLanes,
    groups,
    groupControls,
    lanesFor: (view, bins, visibleGroupIds) => {
      const r = SeqLanes.lanesFor(current.seq, view, bins);
      let lanes = r.lanes;
      if (visibleGroupIds.has("gradients")) {
        if (!current.g) {
          const gModel = GLanes.decode(current.seq);
          current.g = { model: gModel, laneMeta: GLanes.laneMeta(gModel) };
        }
        lanes = lanes.concat([GLanes.lanesFor(current.g.model, current.g.laneMeta, view, bins)]);
      }
      let pnsResult = null;
      if (current.pns && visibleGroupIds.has("pns")) {
        pnsResult = PnsLanes.lanesFor(current.pns.model, current.pns.laneMeta, view, bins);
        lanes = lanes.concat([pnsResult.lane]);
      }
      showStatus(r.exact, bins, pnsResult, current.pns ? current.pns.model.onRaster : null);
      return lanes;
    },
    xDomain: windows[0].view_ms,
    extent: [0, current.seq.durationS * 1000],
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
      // replaces them with the provider's lanes (a `{id: "gmag"}` placeholder for the
      // |G| lane, as `initialLanes` above has, for the same reason). A file without
      // PNS data draws no PNS lane even with the PNS group on (`current.pns` is
      // null, so `lanesFor` above never appends one), whatever file was shown before
      // it.
      chart.setWindow({
        lanes: current.seq.lanesMeta.concat(
          [{ id: "gmag" }],
          current.pns ? [current.pns.laneMeta] : []
        ),
        xDomain: w.view_ms,
        extent: [0, current.seq.durationS * 1000],
      });
      initialWindow = i;
      setButtonsDisabled(false);
    });
  }
});
