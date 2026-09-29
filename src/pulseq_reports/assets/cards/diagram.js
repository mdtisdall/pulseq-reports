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
// status line shows "Loading..." and the window buttons are disabled. Table decoding
// (base64 -> gzip -> typed arrays) itself is `PulseqReport.decodeTable`
// (assets/lane_chart.js), shared with any other card that sends a table the same way.
//
// This card also publishes its state through the page-level message bus
// (docs/plans/rf-profiles.md, section 4.1) so another card can follow it without
// reading this card's own data or DOM: `sequence` once for each file, right after it
// is first decoded; `cursor` while the pointer hovers the chart (at most one message
// per animation frame); `anchor` when a click, the arrow keys or a `goto` message set
// or clear the zoom marker; and `view` after every change of the chart's time window.
// It also subscribes to `goto`, to move its own chart to a block that another card
// names, in a file that the card names by this card's file index or by its file name.
// `docs/usage.md`, section "Messages between cards", documents all of this.
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

  // The decoded model of file `fileIndex`, from the cache when it is already there:
  // `{seq, pns, g, view}`, `seq` the SeqLanes model (as before), `pns` either null
  // (the file has no "pns" key) or `{model, laneMeta}`, the PnsLanes model and its
  // lane object without segments (PnsLanes.laneMeta(file.pns.summary), built once
  // here so a render never rebuilds it), `g` the |G| lane's own `{model, laneMeta}`
  // pair, built lazily by `lanesFor` (below) the first time a render needs it: `g`
  // starts null here, unlike `pns`, because GLanes.decode needs no data beyond the
  // diagram tables already decoded below, so there is nothing to fetch in parallel
  // with them, and building it costs a pass over the file's blocks that a render
  // with the Gradients group hidden should not pay for. Decodes every one of the
  // file's diagram tables, and, when the file has PNS data, its two stored-level
  // tables, all in parallel; the diagram tables are reused for both SeqLanes.decode
  // and PnsLanes.decode (a PNS model reads grad_*/duration_* out of the same tables,
  // module doc of pns_lanes.js).
  //
  // `view` is `SeqLanes.sequenceView(seqModel)` (docs/plans/rf-profiles.md, section
  // 4.1): built once here because it is exactly the payload the `sequence` message
  // needs, and reused later (the `goto` handler) for a block's start and duration
  // instead of reading the model's own tables, the same rule a subscriber follows.
  // The `sequence` message publishes only the first time a file is decoded, which
  // this function already guarantees by returning the cached model on a later call.
  async function decodeFile(fileIndex) {
    if (models[fileIndex]) return models[fileIndex];
    const file = files[fileIndex];
    const names = Object.keys(file.tables);
    const tablesPromise = Promise.all(
      names.map(name => PulseqReport.decodeTable(file.tables[name]))
    );
    const pnsLevelsPromise = file.pns
      ? Promise.all([
        PulseqReport.decodeTable(file.pns.levels.min),
        PulseqReport.decodeTable(file.pns.levels.max),
      ])
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
    const view = SeqLanes.sequenceView(seqModel);
    const model = { seq: seqModel, pns, g: null, view };
    models[fileIndex] = model;
    PulseqReport.publish(
      "sequence", { source: section.id, file: fileIndex, name: file.name, view }
    );
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

  // Publishes `view` (plan section 4.1) for the chart's current time window.
  // `laneChart`'s own `setView`/`setWindow` do not call `onViewChange` (lane_chart.js),
  // so every place below that calls them also calls this explicitly; `onViewChange`
  // itself (a zoom, pan, reset or zoom-control click) calls it too.
  function publishView(viewMs) {
    PulseqReport.publish("view", {
      source: section.id,
      file: currentFileIndex,
      t0S: viewMs[0] / 1000,
      t1S: viewMs[1] / 1000,
    });
  }

  // `cursor` (plan section 4.1): at most one message per animation frame, publishing
  // only the latest hover position even when it moved several times within one frame.
  let cursorFrame = null;
  let pendingCursor = null;
  function scheduleCursorPublish(x, pxX) {
    pendingCursor = { x, pxX };
    if (cursorFrame !== null) return;
    cursorFrame = requestAnimationFrame(() => {
      cursorFrame = null;
      publishCursor(pendingCursor.x, pendingCursor.pxX);
    });
  }
  function publishCursor(x, pxX) {
    if (x === null) {
      PulseqReport.publish("cursor", { source: section.id, file: null });
      return;
    }
    const tS = x / 1000; // the chart's x axis is milliseconds; the message is seconds
    PulseqReport.publish("cursor", {
      source: section.id,
      file: currentFileIndex,
      tS,
      block: SeqLanes.blockAt(current.seq, tS),
      pxS: pxX / 1000,
    });
  }

  // `anchor` (plan section 4.1): published directly, with no throttle -- a click or
  // the arrow keys change the anchor far less often than the cursor moves.
  function publishAnchor(x) {
    if (x === null) {
      PulseqReport.publish("anchor", { source: section.id, file: null });
      return;
    }
    const tS = x / 1000;
    PulseqReport.publish("anchor", {
      source: section.id,
      file: currentFileIndex,
      tS,
      block: SeqLanes.blockAt(current.seq, tS),
    });
  }

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
    onCursor: scheduleCursorPublish,
    onAnchor: publishAnchor,
    // A zoom or pan leaves no button pressed; a reset (isInitial) presses the button
    // of the window whose view is the current xDomain. Every change also publishes
    // `view` (plan section 4.1).
    onViewChange: (view, isInitial) => {
      if (isInitial) {
        press(initialWindow);
      } else {
        for (const button of buttons) button.setAttribute("aria-pressed", "false");
      }
      publishView(view);
    },
  });

  // `setView`/`setWindow` do not call `onViewChange` (lane_chart.js), and the chart's
  // very first window is itself a `view` a later subscriber should learn (plan
  // section 4.1), so it is published explicitly here.
  publishView(windows[0].view_ms);

  // Shows window `i`: switches to its file first if needed (decoding it, the first
  // time), then sets the chart's view -- the same steps a window button always ran
  // inline, before `goto` (plan section 4.1) needed them too. Returns true once the
  // window is shown, false when the file failed to decode (the status line already
  // explains why, and the chart keeps showing whatever it had before).
  async function showWindow(i) {
    const w = windows[i];
    if (w.file === currentFileIndex) {
      press(i);
      chart.setView(w.view_ms);
      publishView(w.view_ms);
      return true;
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
      return false;
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
    publishView(w.view_ms);
    initialWindow = i;
    setButtonsDisabled(false);
    return true;
  }

  for (const button of buttons) {
    const i = Number(button.dataset.window);
    button.addEventListener("click", () => { showWindow(i); });
  }

  // `goto` (plan section 4.1): another card asks this diagram to show one block of
  // one of its files, named by `name` (a string: the first file of this card with that
  // name) when the message has one, else by `file` (this card's file index). A card
  // that learns this card's file indexes only from `sequence` messages cannot know the
  // index of a file that this card has not decoded yet, but it can know the file's
  // name. It shows the first window of that file (switching files first,
  // exactly as a click on that window's button does, through the shared
  // `showWindow`), then sets the view to that block with half its own duration as
  // padding on each side (so the window is twice the block's duration), widened to
  // at least 1 ms and moved inside the file if the padding would reach past an end
  // (`ChartMath.clampView` does both: widen about the same centre, then shift to
  // fit), then sets the anchor to the middle of the block (the `anchor` message
  // itself comes from `onAnchor`, above), then publishes `view`.
  // A `goto` for a block that the file does not have is ignored with a warning; any
  // other failure is written to the console, because the bus cannot catch an error
  // that an async handler throws after its first `await`.
  async function handleGoto(message) {
    if (message.target !== section.id) return;
    try {
      await gotoBlock(message);
    } catch (error) {
      console.error(`diagram card "${section.id}": goto failed:`, error);
    }
  }
  async function gotoBlock(message) {
    const byName = typeof message.name === "string";
    const fileIndex = byName ? files.findIndex(f => f.name === message.name) : message.file;
    const fileText = byName ? `"${message.name}"` : String(message.file);
    if (byName && fileIndex === -1) {
      console.warn(`diagram card "${section.id}": goto ignored, no file named ${fileText}`);
      return;
    }
    // A block that the file cannot have is refused before any file switch. The upper
    // bound needs the file's decoded model: checked here when the file is already
    // decoded, else after `showWindow` decodes it.
    const cached = models[fileIndex];
    if (!Number.isInteger(message.block) || message.block < 0 ||
        (cached && message.block >= cached.view.numBlocks)) {
      console.warn(
        `diagram card "${section.id}": goto ignored, file ${fileText} has no block ` +
          `${message.block}`
      );
      return;
    }
    const i = windows.findIndex(w => w.file === fileIndex);
    if (i === -1) {
      console.warn(
        `diagram card "${section.id}": goto ignored, file ${fileText} has no window`
      );
      return;
    }
    if (!(await showWindow(i))) return;
    const seqView = current.view;
    if (message.block >= seqView.numBlocks) {
      console.warn(
        `diagram card "${section.id}": goto ignored, file ${fileText} has no block ` +
          `${message.block}`
      );
      return;
    }
    const startS = seqView.blockStart(message.block);
    const durS = seqView.blockDuration(message.block);
    const padS = durS / 2;
    const [loS, hiS] = ChartMath.clampView(
      [startS - padS, startS + durS + padS], [0, seqView.durationS], 0.001
    );
    const newView = [loS * 1000, hiS * 1000];
    chart.setView(newView);
    // A view that is not a window's view: no window button is pressed, as after a zoom.
    for (const button of buttons) button.setAttribute("aria-pressed", "false");
    chart.setAnchor((startS + durS / 2) * 1000);
    publishView(newView);
  }

  // `replay: false`: a goto is a one-time action, not state a later subscriber
  // should be replayed into.
  PulseqReport.subscribe("goto", handleGoto, { replay: false });
});
