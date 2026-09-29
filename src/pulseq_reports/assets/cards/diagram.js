// Sequence diagram card: one lane chart with a button for each time window that
// cards/diagram.py gives, and lane-group toggle buttons (RF, ADC, Gradients, and PNS
// when the card has PNS data, docs/plans/diagram-lanes.md section 4.5, item 3). There
// are no lane sets and no point budget: cards/diagram.py sends the compressed block and
// event tables of the sequence (diagram_data.diagram_tables), and this script decodes
// them (base64 -> gzip -> typed arrays -> SeqLanes.decode) into one model, once, at
// start. A "pns" key in the card's file entry also gets its two stored-level tables
// decoded and a PnsLanes.decode model built from them, next to the SeqLanes model.
//
// The chart's `lanesFor` hook (lane_chart.js) asks SeqLanes.lanesFor for the six
// waveform lanes of the current view on every render (the exact waveform when the view
// has few enough points, or the minimum and the maximum of each lane in each of the
// plot's time bins otherwise); when the Gradients group is visible, appends the |G|
// lane (GLanes.lanesFor, docs/plans/diagram-lanes.md phase 5) after gz, building the
// GLanes model the first time a render needs it, through `buildGLane` (a hidden
// Gradients group costs no |G| computation, the same rule the PNS lane already
// follows). `buildGLane` runs `GLanes.decode` in a try/catch: a failure (for example a
// sequence with very many gradient events, or no memory) removes only the |G| lane
// instead of stopping the whole card from drawing, and is not retried on a later
// render. And, when the PNS group is visible and the card has PNS data, appends the PNS
// lane from PnsLanes.lanesFor after that. A hidden PNS group costs no PNS computation:
// `lanesFor` never calls PnsLanes.lanesFor for it. The status line under the chart
// (`{card_id}-mode`) says which data drew the waveform lanes, then, when the |G| lane
// failed to build, why it is not drawn, then, when the PNS lane is drawn,
// PnsLanes.statusText's sentence for it.
//
// The tables can be large (up to 10^7 blocks), so while they decode the status line
// shows "Loading..." and the window buttons are disabled. Table decoding
// (base64 -> gzip -> typed arrays) itself is `PulseqReport.decodeTable`
// (assets/lane_chart.js), shared with any other card that sends a table the same way.
//
// This card also publishes its state through the page-level message bus
// (docs/plans/rf-profiles.md, section 4.1) so another card can follow it without
// reading this card's own data or DOM: `sequence` once, right after the tables are
// decoded; `cursor` while the pointer hovers the chart (at most one message
// per animation frame); `anchor` when a click, the arrow keys or a `goto` message set
// or clear the zoom marker; and `view` after every change of the chart's time window.
// It also subscribes to `goto`, to move its own chart to a block that another card
// names. `docs/usage.md`, section "Messages between cards", documents all of this.
PulseqReport.registerCard("diagram", async (section, data) => {
  const buttons = section.querySelectorAll("[data-window]");
  const statusEl = document.getElementById(`${section.id}-mode`);
  const groupControls = document.getElementById(`${section.id}-groups`);
  const file = data.file;
  const windows = data.windows;
  // The version of the card's own data (cards/diagram.py `_diagram_data`). A page with
  // data of a later version (for example a rotation table) fails loudly instead of
  // drawing wrong waveforms with an old script.
  if (data.format !== 2) {
    throw new Error(
      `diagram card: unsupported data format ${data.format} (only format 2 is known)`
    );
  }
  // The version of the tables that `SeqLanes.decode` reads: not the card's data version.
  const TABLE_FORMAT = 1;

  function setButtonsDisabled(disabled) {
    for (const button of buttons) button.disabled = disabled;
  }

  // `pnsResult` is the return of `PnsLanes.lanesFor` when the PNS lane was drawn this
  // render, else null (the PNS group is hidden, or the card has no PNS data):
  // then the status line is the SeqLanes sentence alone. `gError` is `current.g.error`
  // when the Gradients group is visible and `buildGLane` (below) caught a `GLanes.decode`
  // failure, else null: then the sentence "The |G| lane is not
  // drawn: <message>" (decision 13 of docs/plans/review-bugs.md) is added, so the
  // card explains why the chart has one fewer lane instead of leaving it unsaid.
  function showStatus(exact, bins, pnsResult, gError) {
    let text = exact
      ? "Exact waveform."
      : `Minimum and maximum in each of ${bins} time bins. Zoom in to see the exact waveform.`;
    if (gError) text += ` The |G| lane is not drawn: ${gError.message || String(gError)}`;
    if (pnsResult) text += ` ${PnsLanes.statusText(pnsResult)}`;
    statusEl.textContent = text;
  }

  // The decoded model: `{seq, pns, g, view}`, `seq` the SeqLanes model, `pns` either
  // null (the file entry has no "pns" key) or `{model, laneMeta}`, the PnsLanes model
  // and its lane object without segments (PnsLanes.laneMeta(file.pns.summary), built
  // once here so a render never rebuilds it), `g` the |G| lane's own `{model, laneMeta,
  // error}` (`buildGLane`, defined near the chart below), built lazily by `lanesFor`
  // the first time a render needs it: `g` starts null here, unlike `pns`, because
  // GLanes.decode needs no data beyond the diagram tables already decoded below, so
  // there is nothing to fetch in parallel with them, and building it costs a pass
  // over the blocks that a render with the Gradients group hidden should not
  // pay for. Once built, `g` stays in the model even when `GLanes.decode` failed
  // (`model` and `laneMeta` null, `error` the caught exception), so a later render
  // does not try again: the |G| lane is left out, and the status line says why.
  // Decodes every one of the diagram tables, and, when the file entry has PNS data,
  // its two stored-level tables, all in parallel; the diagram tables are reused for
  // both SeqLanes.decode and PnsLanes.decode (a PNS model reads grad_*/duration_* out
  // of the same tables, module doc of pns_lanes.js).
  //
  // `view` is `SeqLanes.sequenceView(seqModel)` (docs/plans/rf-profiles.md, section
  // 4.1): built once here because it is exactly the payload the `sequence` message
  // needs, and reused later (the `goto` handler) for a block's start and duration
  // instead of reading the model's own tables, the same rule a subscriber follows.
  async function decodeModel() {
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
    const seqModel = SeqLanes.decode(TABLE_FORMAT, tables, file.lanes);
    let pns = null;
    if (file.pns) {
      const [levelMin, levelMax] = pnsLevels;
      const pnsData = { ...file.pns, levels: { min: levelMin, max: levelMax } };
      pns = {
        model: PnsLanes.decode(tables, pnsData),
        laneMeta: PnsLanes.laneMeta(file.pns.summary),
      };
    }
    return { seq: seqModel, pns, g: null, view: SeqLanes.sequenceView(seqModel) };
  }

  statusEl.textContent = "Loading…";
  setButtonsDisabled(true);
  // The decode failure is not caught here: it propagates out of this async init, so
  // page.js shows the card's usual "could not be drawn" note (there is no chart to
  // fall back to without a model).
  const current = await decodeModel();
  PulseqReport.publish("sequence", { source: section.id, view: current.view });
  setButtonsDisabled(false);

  function press(i) {
    for (const button of buttons) {
      button.setAttribute("aria-pressed", String(Number(button.dataset.window) === i));
    }
  }

  // Lane groups (plan section 4.5, item 3): RF, ADC and Gradients always, PNS only
  // when the file entry has PNS data. All visible at start, so the PNS group (when
  // present) is on by default. `groups` never changes after `laneChart` is called
  // (lane_chart.js), matching that the PNS data is fixed once the card is built.
  const hasPns = Boolean(file.pns);
  const groups = [
    { id: "rf", label: "RF", laneIds: ["rf_mag", "rf_phase"], visible: true },
    { id: "adc", label: "ADC", laneIds: ["adc"], visible: true },
    { id: "gradients", label: "Gradients", laneIds: ["gx", "gy", "gz", "gmag"], visible: true },
  ];
  if (hasPns) groups.push({ id: "pns", label: "PNS", laneIds: ["pns"], visible: true });

  // Publishes `view` (plan section 4.1) for the chart's current time window.
  // `laneChart`'s own `setView` does not call `onViewChange` (lane_chart.js), so every
  // place below that calls it also calls this explicitly; `onViewChange` itself (a
  // zoom, pan, reset or zoom-control click) calls it too.
  function publishView(viewMs) {
    PulseqReport.publish("view", {
      source: section.id,
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
      PulseqReport.publish("cursor", { source: section.id, tS: null });
      return;
    }
    const tS = x / 1000; // the chart's x axis is milliseconds; the message is seconds
    PulseqReport.publish("cursor", {
      source: section.id,
      tS,
      block: SeqLanes.blockAt(current.seq, tS),
      pxS: pxX / 1000,
    });
  }

  // `anchor` (plan section 4.1): published directly, with no throttle -- a click or
  // the arrow keys change the anchor far less often than the cursor moves.
  function publishAnchor(x) {
    if (x === null) {
      PulseqReport.publish("anchor", { source: section.id, tS: null });
      return;
    }
    const tS = x / 1000;
    PulseqReport.publish("anchor", {
      source: section.id,
      tS,
      block: SeqLanes.blockAt(current.seq, tS),
    });
  }

  // The |G| lane's `{model, laneMeta, error}` (plan section 4.3 of
  // docs/plans/review-bugs.md, B3). `GLanes.decode` can throw (for example a sequence
  // with very many gradient events, or no memory); this is the one place that calls it,
  // so catching it here covers every path that can reach a `GLanes` failure: the
  // initial render inside `laneChart` below, a window button (`showWindow`), and a
  // window shown through the `goto` message (`gotoBlock`, which calls `showWindow`
  // too) -- all three run through `lanesFor` below. On success, `error` is null. On
  // failure, `model` and `laneMeta` are null (so the caller below appends no |G| lane)
  // and `error` is the caught exception (so the status line can say why); logged once
  // here with `console.error`, not on every render, because the caller keeps the
  // returned object in `current.g` and never calls this again.
  function buildGLane(seqModel) {
    try {
      const model = GLanes.decode(seqModel);
      return { model, laneMeta: GLanes.laneMeta(model), error: null };
    } catch (error) {
      console.error(`diagram card "${section.id}": the |G| lane is not drawn:`, error);
      return { model: null, laneMeta: null, error };
    }
  }

  const chart = PulseqReport.laneChart({
    svg: document.getElementById(`${section.id}-diagram`),
    chart: document.getElementById(`${section.id}-chart`),
    tip: document.getElementById(`${section.id}-tip`),
    // `lanesFor` and `groups` are given, so `laneChart` never draws `lanes` (lane_chart.js).
    lanes: [],
    groups,
    groupControls,
    lanesFor: (view, bins, visibleGroupIds) => {
      const r = SeqLanes.lanesFor(current.seq, view, bins);
      let lanes = r.lanes;
      let gError = null;
      if (visibleGroupIds.has("gradients")) {
        if (!current.g) current.g = buildGLane(current.seq);
        gError = current.g.error;
        if (current.g.model) {
          lanes = lanes.concat(
            [GLanes.lanesFor(current.g.model, current.g.laneMeta, view, bins)]
          );
        }
      }
      let pnsResult = null;
      if (current.pns && visibleGroupIds.has("pns")) {
        pnsResult = PnsLanes.lanesFor(current.pns.model, current.pns.laneMeta, view, bins);
        lanes = lanes.concat([pnsResult.lane]);
      }
      showStatus(r.exact, bins, pnsResult, gError);
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
    // of the first window, whose view is the xDomain. Every change also publishes
    // `view` (plan section 4.1).
    onViewChange: (view, isInitial) => {
      if (isInitial) {
        press(0);
      } else {
        for (const button of buttons) button.setAttribute("aria-pressed", "false");
      }
      publishView(view);
    },
  });

  // `setView` does not call `onViewChange` (lane_chart.js), and the chart's very first
  // window is itself a `view` a later subscriber should learn (plan section 4.1), so it
  // is published explicitly here.
  publishView(windows[0].view_ms);

  // Shows window `i`: the same steps a window button always ran inline, before `goto`
  // (plan section 4.1) needed them too.
  function showWindow(i) {
    const w = windows[i];
    press(i);
    chart.setView(w.view_ms);
    publishView(w.view_ms);
  }

  for (const button of buttons) {
    const i = Number(button.dataset.window);
    button.addEventListener("click", () => { showWindow(i); });
  }

  // `goto` (plan section 4.1): another card asks this diagram to show one block. It
  // shows the first window (exactly as a click on that window's button does, through
  // the shared `showWindow`), then sets the view to that block with half its own
  // duration as padding on each side (so the window is twice the block's duration),
  // widened to at least 1 ms and moved inside the sequence if the padding would reach
  // past an end (`ChartMath.clampView` does both: widen about the same centre, then
  // shift to fit), then sets the anchor to the middle of the block (the `anchor`
  // message itself comes from `onAnchor`, above), then publishes `view`.
  // A `goto` for a block that the sequence does not have is ignored with a warning.
  function gotoBlock(message) {
    const seqView = current.view;
    if (!Number.isInteger(message.block) || message.block < 0 ||
        message.block >= seqView.numBlocks) {
      console.warn(`diagram card "${section.id}": goto ignored, no block ${message.block}`);
      return;
    }
    showWindow(0);
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
  PulseqReport.subscribe("goto", gotoBlock, { replay: false });
});
