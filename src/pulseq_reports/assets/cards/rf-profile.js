// RF profile card (docs/plans/rf-profiles.md, section 4.5, items 3 to 6): the RF pulses
// of the period at the cursor of the sequence diagram card, simulated in the browser
// with RfProfiles (assets/rf_profiles.js).
//
// The card follows the diagram only through the page's messages (section 4.1):
// `sequence` gives the sequence view, and `cursor` and `anchor` give a block. A page has
// one publisher of each of these topics (decision 21 of docs/plans/public-api.md), so
// the card takes every message of them. The card subscribes to no `view` message:
// nothing here depends on the diagram's view (decision 13).
//
// Which period: the period that contains the block of the anchor, or of the cursor when
// there is no anchor (decision 14). When the cursor leaves the plot, or a reset clears
// the anchor, the card keeps the period that it shows until the cursor moves again. A
// move inside the shown period changes nothing, and costs no RfProfiles call (every
// block of a period that is not truncated has that same period, section 2.5 of the
// plan); a new period is drawn in the next animation frame, so a cursor message itself
// does only the period walk.
//
// The work: each distinct pulse of the period gets its 1D "profile" view at once, in the
// order of the table (section 4.5, item 5); then the combined profile of the first echo
// and the maps of the views that the caller switched on ("z_df", "2d") run in slices
// (STEP_MS of simulation, then the drawing of what ended in it) with a setTimeout
// between them. The elements of a pulse
// stay on the page while the next period has the same pulse key, so a move to the next
// TR draws no chart again. A new period replaces the work list: the work of a pulse
// that the new period does not have stops, and its progress stays in the cache, so it
// goes on when the pulse comes back. The cache keeps the profiles and maps of the last
// MAX_KEYS pulse keys (the key leaves out the phase offsets of the RF, so an RF-spoiled
// GRE has one key). The card also has a line cache (RfProfiles, decision 25) that the
// combined profile shares with the 1D profiles; the entries of a pulse key leave it with
// that key. Combined profiles are kept by the layout of the RF blocks of their period
// (MAX_COMBINED of them), so a move to the next TR of the same kind draws at once.
//
// The echo pathway belongs to the block, not to the key: the phase at the echo and the
// phase numbers of an excitation come from its last block in the period (the one
// nearest to the ADC), with the profile of its key.
//
// The groups (docs/plans/pulseq-checks.md, section 4.8). The data has the groups of the
// targets with the same gamma and B0 (`file.groups`). A `ppm` offset changes into Hz with
// the signed gamma and the B0 of a group, and |B1| uses |gamma| (RfProfiles). With more
// than one group, each lane of a 1D profile has one series for each group, in the color of
// the group, and the table of the pulses has one row for each pulse and group. The
// Bloch simulation depends only on the offsets in Hz, so the groups that give a pulse the
// same offsets share its profiles (a "variant" of the pulse key). The maps and the maps of
// the combined profile are for the first group that has the pulse. A pulse with a `ppm`
// offset in a group without B0 has a note for that group, and is not drawn for it.
//
// The "Show" buttons of the pulse list publish `goto` with the block, and are shown only
// while a card subscribes to `goto` (decision 22 of docs/plans/public-api.md).
PulseqReport.registerCard("rf-profile", (section, data) => {
  const {fmt} = ChartMath;
  const id = section.id;
  const byId = suffix => document.getElementById(`${id}-${suffix}`);
  const statusEl = byId("status");
  const pulsesEl = byId("pulses");
  const combinedEl = byId("combined");
  const combinedBody = byId("combined-body");
  // The note of section 4.3, item 7 (PRIMARY_ECHO_NOTE of cards/rf_profile.py): the
  // paragraph after the heading of the combined element. It shows only above a combined
  // profile, not above the line that says why a period has none.
  const combinedNote = combinedEl.querySelector(":scope > p");
  const mapViews = data.views.filter(v => v !== "profile");
  const viewOptions = {plane: data.plane, extentM: data.extent_m};
  const combinedView = data.views.includes("2d") ? "2d" : "profile";

  // A slice of work steps the simulations for STEP_MS. A job that ends in the first
  // FINISH_MS of a slice draws its result (a few ms: 7 ms for a 201 × 201 map) in that
  // slice; a job that ends later draws it at the start of the next slice. So a slice
  // stays within the 20 ms of section 2.4.
  const STEP_MS = 14;
  const FINISH_MS = 6;
  const MAX_KEYS = 64; // the pulse keys whose profiles and maps the cache keeps
  const MAX_COMBINED = 16; // the combined profiles that the cache keeps

  // ---- The file ----

  // The state of the card data's file. `fd` is the RfProfiles file data once the RF table
  // is decoded; `blockKeys` maps the event ids of an RF block ("rf,gx,gy,gz") to its
  // pulse key, so that the key of a block needs one blockPulse call for each distinct
  // combination.
  const file = {
    entry: data.file, fd: null, decoding: null, error: null,
    lineCache: new Map(), blockKeys: new Map(),
  };
  // The sequence view of the diagram's last `sequence` message, or null before it.
  let diagramView = null;

  function decodeFile() {
    if (file.decoding === null) {
      const rf = file.entry.rf;
      const names = Object.keys(rf);
      file.decoding = Promise.all(names.map(name => PulseqReport.decodeTable(rf[name])))
        .then(arrays => {
          const tables = {};
          names.forEach((name, i) => { tables[name] = arrays[i]; });
          file.fd = RfProfiles.fileData(file.entry, tables);
        })
        .catch(error => {
          file.error = error;
          console.error(`RF profile card "${id}": the RF table:`, error);
        })
        .then(select);
    }
    return file.decoding;
  }

  // The pulse key of the RF block `b`: it does not depend on the group.
  function blockKey(seqView, b) {
    const ev = seqView.events(b);
    const combo = `${ev.rf},${ev.gx},${ev.gy},${ev.gz}`;
    let key = file.blockKeys.get(combo);
    if (key === undefined) {
      key = RfProfiles.pulseKey(seqView, file.fd, b);
      file.blockKeys.set(combo, key);
    }
    return key;
  }

  // The groups of the targets with the same gamma and B0 (the file data).
  const manyGroups = () => file.fd.groups.length > 1;
  // The names of the targets of a group.
  const groupNames = group => group.names.join(", ");

  // ---- The caches ----

  // pulse key -> {key, variants: Map}, in the order of use (the first entry is the least
  // recently used). A variant is {pulse, profile, maps: {view}} for one offset of the pulse
  // in Hz (the groups with that offset share it; only a `ppm` offset differs between
  // groups); `profile` and each map are a record of one view of the pulse (newRecord).
  const keyCache = new Map();

  // The record of one view of a pulse: its spec (undefined until the work makes it,
  // null with a reason when the view does not apply), its RfProfiles work, its result,
  // and values made from the result for the page (quantities, widths, map values).
  const newRecord = () => ({spec: undefined, reason: null, work: null, result: null});

  // The work of one view of a pulse, in two parts: the spec (one step: for a pulse
  // without W, it needs the RF spectrum), then the simulation. The record keeps both,
  // so the work goes on where it stopped when the pulse comes back.
  function viewWork(rec, pulse, view, cache) {
    return {
      step(budgetMs) {
        if (rec.spec === undefined) {
          ({spec: rec.spec, reason: rec.reason} = RfProfiles.viewSpec(pulse, view, viewOptions));
          return 0;
        }
        if (rec.work === null) rec.work = RfProfiles.simulation(pulse, rec.spec, {cache});
        return rec.work.step(budgetMs);
      },
      get done() {
        return rec.spec === null || (rec.work !== null && rec.work.done);
      },
    };
  }
  const recordDone = rec => rec.spec === null || rec.result !== null ||
    (rec.work !== null && rec.work.done);
  // The result of a record whose work is done.
  function takeResult(rec) {
    if (rec.result === null) {
      rec.result = rec.work.result();
      rec.work = null;
    }
    return rec.result;
  }

  // The cache entry of `key`.
  function keyEntry(key) {
    let entry = keyCache.get(key);
    if (entry !== undefined) {
      keyCache.delete(key);
      keyCache.set(key, entry);
      return entry;
    }
    entry = {key, variants: new Map()};
    keyCache.set(key, entry);
    while (keyCache.size > MAX_KEYS) {
      const [oldKey] = keyCache.entries().next().value;
      keyCache.delete(oldKey);
      const prefix = `${oldKey}|`;
      for (const lineKey of Array.from(file.lineCache.keys())) {
        if (lineKey.startsWith(prefix)) file.lineCache.delete(lineKey);
      }
    }
    return entry;
  }

  // The variant of `entry` for the offset in Hz `freqHz`, made with the pulse that
  // `makePulse()` gives when the entry does not have it.
  function variantOf(entry, freqHz, makePulse) {
    const id = String(freqHz);
    let variant = entry.variants.get(id);
    if (variant === undefined) {
      variant = {pulse: makePulse(), profile: newRecord(), maps: {}};
      entry.variants.set(id, variant);
    }
    return variant;
  }

  // `${layout}/${view}` -> {firstBlock, result}: the combined profiles,
  // by the layout of the RF blocks of their period up to its first ADC (each block's
  // offset from the period start, its pulse key and its offset in Hz in the group), which
  // decides the result; its blocks are those of the period `firstBlock`.
  const combinedCache = new Map();

  function combinedName(seqView, per, gi) {
    const parts = [];
    if (per.firstAdcBlock !== null) {
      for (let b = per.firstBlock; b <= per.firstAdcBlock; b++) {
        if (seqView.events(b).rf === 0) continue;
        const offsets = RfProfiles.pulseOffset(seqView, file.fd, b, gi);
        parts.push(`${b - per.firstBlock}:${blockKey(seqView, b)}:${offsets && offsets.freqHz}`);
      }
    }
    return `${parts.join(",")}/${combinedView}`;
  }

  // ---- Which period ----

  let anchor = null; // {block} of the diagram's anchor, or null
  let cursor = null; // {block} of the last cursor in the plot, or null
  // What the card shows: null (nothing yet), {note} (a line of text only), or {seqView,
  // per, pinned}.
  let shown = null;
  let frame = null;

  function onMessage(topic, message) {
    if (topic === "sequence") {
      diagramView = message.view;
      if (file.entry.labeled) decodeFile();
      return;
    }
    const at = message.tS === null ? null : {block: message.block};
    if (topic === "anchor") {
      anchor = at;
      // A cleared anchor keeps the shown period, and ends the "pinned" text.
      if (at === null) {
        if (shown !== null && shown.per && shown.pinned) {
          shown.pinned = false;
          statusEl.textContent = statusText();
        }
        return;
      }
    } else if (topic === "cursor") {
      if (at === null) return;
      cursor = at;
      if (anchor !== null) return;
    }
    select();
  }

  function showNote(text) {
    if (shown !== null && shown.note === text) return;
    shown = {note: text};
    stopWork();
    clearAll();
    statusEl.textContent = text;
  }

  function select() {
    const target = anchor ?? cursor;
    if (target === null) return;
    if (diagramView === null) return;
    if (!file.entry.labeled) {
      showNote("This file has RF pulses without a use label, so the card shows " +
        "no profiles for it (see the note above).");
      return;
    }
    if (file.error !== null) {
      showNote(`The card could not read its RF table: ${file.error.message}`);
      return;
    }
    if (file.fd === null) {
      decodeFile();
      statusEl.textContent = "Loading the RF pulses…";
      return;
    }
    if (file.fd.firstRfBlock === null) {
      showNote("This file has no RF pulses.");
      return;
    }
    const seqView = diagramView;
    const block = Math.min(Math.max(target.block, 0), seqView.numBlocks - 1);
    const pinned = target === anchor;
    const same = shown !== null && shown.per !== undefined;
    if (same && !shown.per.truncated && block >= shown.per.firstBlock &&
        block <= shown.per.lastBlock) {
      if (shown.pinned !== pinned) {
        shown.pinned = pinned;
        statusEl.textContent = statusText();
      }
      return;
    }
    const per = RfProfiles.period(seqView, file.fd, block);
    if (same && per.firstBlock === shown.per.firstBlock && per.lastBlock === shown.per.lastBlock) {
      shown.pinned = pinned;
      statusEl.textContent = statusText();
      return;
    }
    shown = {seqView, per, pinned};
    stopWork();
    if (frame === null) frame = requestAnimationFrame(render);
  }

  function statusText() {
    const {seqView, per, pinned} = shown;
    const t0 = seqView.blockStart(per.firstBlock) * 1e3;
    const t1 = (seqView.blockStart(per.lastBlock) + seqView.blockDuration(per.lastBlock)) * 1e3;
    const n = per.pulses.length;
    let text = `Blocks ${per.firstBlock}–${per.lastBlock} ` +
      `(${t0.toFixed(3)}–${t1.toFixed(3)} ms), ${n} distinct RF pulse${n === 1 ? "" : "s"}.`;
    if (per.truncated) {
      text += ` The period goes on for more than ${RfProfiles.PERIOD_MAX_BLOCKS} blocks ` +
        "from the cursor: the card shows only the blocks within that distance.";
    }
    if (pinned) text += " Pinned by the marker of the diagram (Escape or Reset there to follow the cursor).";
    return text;
  }

  // ---- Elements ----

  function el(tag, attrs = {}, ...children) {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
    node.append(...children);
    return node;
  }

  // A chart made after page.js ran gets the same focus rule as the others: no outline
  // after a click, an outline after the keyboard.
  function pointerFocus(svg) {
    svg.addEventListener("pointerdown", () => svg.setAttribute("data-pointer-focus", ""));
    svg.addEventListener("blur", () => svg.removeAttribute("data-pointer-focus"));
  }

  const SVG_NS = "http://www.w3.org/2000/svg";
  function chartBox(svgId, label, withCanvas) {
    const box = el("div", {class: withCanvas ? "chart map-chart" : "chart"});
    const svg = document.createElementNS(SVG_NS, "svg");
    if (svgId !== null) svg.setAttribute("id", svgId);
    svg.setAttribute("tabindex", "0");
    svg.setAttribute("role", "img");
    svg.setAttribute("aria-label", label);
    pointerFocus(svg);
    const tip = el("div", {class: "tip"});
    tip.hidden = true;
    const canvas = withCanvas ? document.createElement("canvas") : null;
    if (canvas) box.append(canvas);
    box.append(svg, tip);
    return {box, svg, tip, canvas};
  }

  // The unit and the scale of an axis kind: positions in mm, df in Hz.
  function axisOf(kind) {
    if (kind === "df") return {scale: 1, unit: "Hz", label: "Δf (Hz)", name: "Δf"};
    return {scale: 1e3, unit: "mm", label: `${kind} (mm)`, name: kind};
  }

  function gradientText(pulse) {
    if (pulse.gradientKind === "none") return "no gradient";
    if (pulse.gradientKind === "changing") return "changing direction";
    return pulse.selectKind === "select" ? "oblique" : `G${pulse.selectKind}`;
  }

  // The lanes of the 1D profile of each use (section 4.3, item 2), and the main
  // quantity of its maps.
  const LANES = {
    excitation: ["mxy", "mz", "phase"],
    refocusing: ["beta"],
    inversion: ["mz"],
    saturation: ["mz"],
    preparation: ["mxy", "mz"],
    other: ["mxy", "mz"],
  };
  const MAIN = {
    excitation: "mxy_abs", refocusing: "beta_sq", inversion: "mz", saturation: "mz",
    preparation: "mxy_abs", other: "mxy_abs",
  };
  const QUANTITY_LABEL = {mxy_abs: "|Mxy|", mz: "Mz", beta_sq: "|β|²"};
  // The top of the axis of a quantity from 0 to at most 1 (|Mxy|, |β|², a combined
  // profile): the first of these at or above the largest value, so that a small flip
  // angle does not draw a flat line near 0.
  const TOPS = [0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1];
  function niceTop(...arrays) {
    let max = 0;
    for (const values of arrays) for (const v of values) if (v > max) max = v;
    return TOPS.find(t => max <= t * (1 + 1e-9)) ?? max;
  }
  const unitTicks = (...arrays) => {
    const top = niceTop(...arrays);
    return {domain: [0, top], ticks: [0, top / 2, top], tick_labels: ["0", fmt(top / 2), fmt(top)]};
  };
  const SIGNED_TICKS = {domain: [-1, 1], ticks: [-1, 0, 1], tick_labels: ["−1", "0", "1"]};
  const PHASE_TICKS = {domain: [-Math.PI, Math.PI], ticks: [-Math.PI, 0, Math.PI],
    tick_labels: ["−π", "0", "π"]};

  // The segments of the values at the points x (scaled for the axis), cut where a value is
  // not finite (the echo phase is NaN where |Mxy| is small).
  function segmentsOf(x, scale, values) {
    const segments = [];
    let seg = [];
    for (let i = 0; i < x.length; i++) {
      if (Number.isFinite(values[i])) {
        seg.push([x[i] * scale, values[i]]);
      } else if (seg.length) {
        segments.push(seg);
        seg = [];
      }
    }
    if (seg.length) segments.push(seg);
    return segments;
  }

  // One line lane. `items` are {x, values, label, color}, one for each group (or each set
  // of groups) that has the lane: with several groups in the file, each is a series of the
  // lane in its color, else the one item is the lane.
  function lane(laneId, title, unit, color, items, scale, ticks) {
    const out = {id: laneId, title, unit, color, kind: "line", segments: [], fill: null, ...ticks};
    if (manyGroups()) {
      out.series = items.map(it => ({label: `${title}: ${it.label}`, color: it.color,
        segments: segmentsOf(it.x, scale, it.values)}));
    } else {
      out.segments = segmentsOf(items[0].x, scale, items[0].values);
    }
    return out;
  }

  // The bands of a slice, in the unit of the axis: [lo, hi], or {lo, hi, color} in the color
  // of a group when the card has several.
  const scaledBand = (band, scale) => (Array.isArray(band)
    ? [band[0] * scale, band[1] * scale]
    : {lo: band.lo * scale, hi: band.hi * scale, color: band.color});

  function drawLanes(container, svgId, label, axis, lo, hi, lanes, bands) {
    const {box, svg, tip} = chartBox(svgId, label, false);
    container.replaceChildren(box);
    const xDomain = [lo * axis.scale, hi * axis.scale];
    PulseqReport.laneChart({
      svg, chart: box, tip, lanes, xDomain, minSpan: (xDomain[1] - xDomain[0]) / 1000,
      xLabel: axis.label,
      cursorText: v => `${axis.name} = ${fmt(v)} ${axis.unit}`,
      bands: bands.map(band => scaledBand(band, axis.scale)),
    });
  }

  // Values of a C-order grid (first axis slowest, as RfProfiles gives them) in the
  // row-major order of mapChart: one row for each point of the second axis.
  function mapOrder(values, nx, ny) {
    const out = new Float64Array(nx * ny);
    for (let i = 0; i < nx; i++) {
      for (let j = 0; j < ny; j++) out[j * nx + i] = values[i * ny + j];
    }
    return out;
  }

  // Draws a map chart into `container` and returns it; whoever removes it from the page
  // calls its destroy() first. `values` are in the C order of RfProfiles.
  function drawMap(container, label, axes, values, quantity, outlines) {
    const [ax, ay] = axes;
    const xa = axisOf(ax.kind), ya = axisOf(ay.kind);
    const {box, svg, tip, canvas} = chartBox(null, label, true);
    container.replaceChildren(box);
    const signed = quantity === "mz";
    const top = signed ? 1 : niceTop(values);
    const valueLabel = quantity === "combined" ? "Combined" : QUANTITY_LABEL[quantity];
    return PulseqReport.mapChart({
      canvas, svg, chart: box, tip,
      x: {lo: ax.lo * xa.scale, hi: ax.hi * xa.scale, n: ax.n, label: xa.label},
      y: {lo: ay.lo * ya.scale, hi: ay.hi * ya.scale, n: ay.n, label: ya.label},
      values: mapOrder(values, ax.n, ay.n),
      domain: signed ? [-1, 1] : [0, top],
      scale: signed ? "diverging" : "sequential",
      valueLabel,
      cursorText: (x, y, v) => `${xa.name} = ${fmt(x)} ${xa.unit}, ${ya.name} = ${fmt(y)} ` +
        `${ya.unit}, ${valueLabel} = ${fmt(v)}`,
      outlines: outlines.map(([x0, x1, y0, y1]) =>
        [x0 * xa.scale, x1 * xa.scale, y0 * ya.scale, y1 * ya.scale]),
    });
  }

  const muted = text => el("p", {class: "muted"}, text);

  // ---- The work ----

  let jobs = [];
  let timer = null;
  let pendingFinish = null; // the finish of a job that ended late in the last slice

  function stopWork() {
    jobs = [];
    pendingFinish = null;
    if (timer !== null) {
      clearTimeout(timer);
      timer = null;
    }
  }

  function startWork(list) {
    stopWork();
    jobs = list;
    if (jobs.length) timer = setTimeout(slice, 0);
  }

  // One slice (STEP_MS and FINISH_MS above): first the finish of a job that ended late
  // in the last slice, then steps of the first job until STEP_MS of the slice have
  // passed, then of the next one. A job is {work (an RfProfiles work object, or an
  // object with the same step and done), progress(fraction), finish()}.
  function slice() {
    timer = null;
    const start = performance.now();
    const end = start + STEP_MS;
    try {
      if (pendingFinish !== null) {
        const finish = pendingFinish;
        pendingFinish = null;
        finish();
      }
      while (jobs.length && performance.now() < end) {
        const job = jobs[0];
        const fraction = job.work.step(Math.max(0, end - performance.now()));
        if (job.work.done) {
          jobs.shift();
          if (performance.now() - start < FINISH_MS) {
            job.finish();
          } else {
            pendingFinish = job.finish;
            break;
          }
        } else {
          job.progress(fraction);
        }
      }
    } catch (error) {
      jobs = [];
      pendingFinish = null;
      console.error(`RF profile card "${id}":`, error);
      statusEl.textContent = `The card could not compute a profile: ${error.message}`;
      return;
    }
    if (jobs.length || pendingFinish !== null) timer = setTimeout(slice, 0);
  }

  const percent = f => `${Math.floor(100 * f)} %`;

  // ---- The elements of the distinct pulses ----

  // The elements of each distinct pulse of the shown period, by pulse key: {el, heading,
  // profileBox, drawn (what the 1D chart shows: null, or {groups, phases}), mapBoxes: {view},
  // mapTitles: {view}, maps: {view: map chart}}. A pulse of the
  // next period with the same key keeps its elements, so a move to the next TR of a
  // sequence draws no chart again, except a 1D chart whose echo phase changes.
  let pulseViews = new Map();
  let nextViewId = 0;

  function dropView(v) {
    for (const chart of Object.values(v.maps)) chart.destroy();
  }

  function makeView(use) {
    const v = {heading: el("h4"), profileBox: el("div"), drawn: null, mapBoxes: {}, mapTitles: {},
      maps: {}, svgId: `${id}-lanes-${nextViewId++}`};
    v.el = el("div", {}, v.heading, v.profileBox);
    for (const view of mapViews) {
      v.mapBoxes[view] = el("div");
      v.mapTitles[view] = el("strong", {}, `${view === "z_df" ? "Select coordinate × Δf" : "Two spatial axes"} ` +
        `(${QUANTITY_LABEL[MAIN[use]]})`);
      v.el.append(el("p", {}, v.mapTitles[view]), v.mapBoxes[view]);
    }
    return v;
  }

  // The combined profile that the card shows: {name (of combinedCache), summary (the
  // paragraph with the block numbers), maps}, or null.
  let combinedShown = null;

  function dropCombined() {
    if (combinedShown !== null) for (const chart of combinedShown.maps) chart.destroy();
    combinedShown = null;
  }

  function clearAll() {
    for (const v of pulseViews.values()) dropView(v);
    pulseViews = new Map();
    dropCombined();
    pulsesEl.replaceChildren();
    combinedBody.replaceChildren();
    combinedEl.hidden = true;
  }

  // ---- Drawing a period ----

  const TABLE_HEADERS = ["Pulse", "Use", "Count", "Gradient", "Flip angle (°)",
    "Peak B1 (µT)", "Energy (µT²·ms)", "W (mm)", "Slice centre (mm)", "FWHM",
    "Edge 10–90 %", "Passband ripple", "Stopband level", "Rephasing error (rad)",
    "Non-linear residual (rad)", "Centre phase (rad)", "Notes"];
  // The columns that the 1D profile fills, in the order of TABLE_HEADERS from "FWHM".
  const WIDTH_KEYS = ["fwhm", "edge_width", "passband_ripple", "stopband_level",
    "rephasing_error_rad", "nonlinear_residual_rad", "centre_phase_rad"];
  // The note of a pulse with a `ppm` offset in a group without B0.
  const NO_B0 = "the offset is in ppm and no target gives B0, so it cannot be changed into Hz";

  const mm = v => (v === null || v === undefined ? "—" : fmt(v * 1e3));

  function render() {
    frame = null;
    if (shown === null || shown.per === undefined) return;
    const {seqView, per} = shown;
    stopWork();
    statusEl.textContent = statusText();
    const groups = file.fd.groups;
    const many = manyGroups();

    // One slot for each distinct pulse: its key's cache entry, its elements, and a "sub"
    // for each group: the pulse in that group (for an excitation, the pulse of its last
    // block, for the echo pathway of that block; else the pulse of the key's variant) and
    // that variant, both null for a `ppm` offset in a group without B0.
    const views = new Map();
    const slots = per.pulses.map((g, i) => {
      const name = g.key;
      const entry = keyEntry(g.key);
      const subs = groups.map((group, gi) => {
        const offsets = RfProfiles.pulseOffset(seqView, file.fd, g.lastBlock, gi);
        if (offsets === null) return {gi, group, pulse: null, variant: null};
        const own = g.use === "excitation"
          ? RfProfiles.blockPulse(seqView, file.fd, g.lastBlock, {group: gi}) : null;
        const variant = variantOf(entry, offsets.freqHz,
          () => own ?? RfProfiles.blockPulse(seqView, file.fd, g.lastBlock, {group: gi}));
        // The variant is shared by the groups with this offset in Hz, but its pulse has the
        // |B1| of the group that made it: each group reads the pulse with its own |gamma|.
        return {gi, group, pulse: own ?? RfProfiles.pulseInGroup(seqView, file.fd, variant.pulse, gi),
          variant};
      });
      const first = subs.find(sub => sub.pulse !== null);
      const view = pulseViews.get(name) ?? makeView(g.use);
      views.set(name, view);
      view.heading.textContent = `Pulse ${i + 1}: ${g.use}, ` +
        `${first ? `${gradientText(first.pulse)}, ` : ""}×${g.count}`;
      return {k: i + 1, g, name, entry, view, subs, first};
    });
    for (const [name, v] of pulseViews) if (!views.has(name)) dropView(v);
    pulseViews = views;

    const tbody = el("tbody");
    for (const slot of slots) {
      const {k, g} = slot;
      for (const sub of slot.subs) {
        const {pulse, variant} = sub;
        const notes = pulse === null ? [NO_B0] : pulse.notes.slice();
        if (pulse !== null) {
          if (pulse.use === "excitation" && pulse.echo === null && pulse.echoReason !== null) {
            notes.push(`phase at the echo: ${pulse.echoReason}`);
          }
          if (variant.profile.reason !== null) notes.push(variant.profile.reason);
        }
        sub.widthCells = WIDTH_KEYS.map(() => el("td", {}, pulse === null ? "—" : "…"));
        sub.notes = notes;
        sub.notesCell = el("td", {}, notes.join("; "));
        const target = many ? [el("td", {}, groupNames(sub.group))] : [];
        const numbers = pulse === null ? ["—", "—", "—", "—", "—", "—"]
          : [gradientText(pulse), fmt(pulse.flipDeg), fmt(pulse.peakB1Ut), fmt(pulse.energyUt2Ms),
            mm(pulse.nominalM), mm(pulse.sliceCentreM)];
        tbody.append(el("tr", {},
          el("td", {}, String(k)), ...target, el("td", {}, g.use), el("td", {}, String(g.count)),
          ...numbers.map(text => el("td", {}, text)), ...sub.widthCells, sub.notesCell));
      }
    }
    const headers = many ? [TABLE_HEADERS[0], "Target", ...TABLE_HEADERS.slice(1)] : TABLE_HEADERS;
    const table = el("div", {class: "scroll"}, el("table", {},
      el("thead", {}, el("tr", {}, ...headers.map(h => el("th", {}, h)))), tbody));
    pulsesEl.replaceChildren(table, ...slots.map(s => s.view.el));

    // The 1D profiles at once, in the order of the table (section 4.5, item 5); then the
    // combined profile and the maps, in slices.
    for (const slot of slots) profileNow(slot);
    const list = [];
    combinedWork(seqView, per, slots, list);
    for (const view of mapViews) for (const slot of slots) mapWork(slot, view, list);
    startWork(list);
  }

  // The view of `slot` is still on the page (a job can end after its period has gone).
  const alive = slot => pulseViews.get(slot.name) === slot.view;

  // The 1D profile of a slot, at once: its reason, or its chart (from the cache, or
  // computed here). The work of a variant is done one time for all its groups.
  function profileNow(slot) {
    for (const sub of slot.subs) {
      if (sub.variant === null) continue;
      const p = sub.variant.profile;
      if (!recordDone(p)) {
        const work = viewWork(p, sub.variant.pulse, "profile", file.lineCache);
        while (!work.done) work.step(Infinity);
      }
      if (p.spec === null) {
        if (!sub.notes.includes(p.reason)) {
          sub.notesCell.textContent = [...sub.notes, p.reason].join("; ");
        }
        for (const cell of sub.widthCells) cell.textContent = "—";
      } else {
        takeResult(p);
      }
    }
    showProfile(slot);
  }

  const samePhase = (a, b) => a === b || (a !== null && b !== null && a.length === b.length &&
    a.every((v, i) => v === b[i] || (Number.isNaN(v) && Number.isNaN(b[i]))));

  // Draws the 1D chart of a slot, unless the same chart is on the page, and fills the
  // width cells of its rows. A group whose pulse has no profile is not in the chart.
  function showProfile(slot) {
    const {view} = slot;
    const drawable = slot.subs.filter(sub => sub.variant !== null && sub.variant.profile.spec !== null);
    if (drawable.length === 0) {
      // The same reason for each group (it comes from the pulse), or the note.
      const sub = slot.subs.find(s => s.variant !== null);
      const reason = sub ? sub.variant.profile.reason : NO_B0;
      if (view.drawn === null || view.drawn.reason !== reason) {
        view.profileBox.replaceChildren(muted(`No 1D profile: ${reason}.`));
        view.drawn = {reason};
      }
      return;
    }
    const axis = axisOf(drawable[0].variant.profile.result.spec.axes[0].kind);
    const phases = drawable.map(sub => (sub.pulse.use === "excitation" && sub.pulse.gradientKind === "one"
      ? RfProfiles.echoPhase(sub.pulse, sub.variant.profile.result) : null));
    const groupsKey = drawable.map(sub => `${sub.gi}:${sub.variant.profile.result.spec.axes[0].lo}`).join(",");
    const same = view.drawn !== null && view.drawn.groups === groupsKey &&
      view.drawn.phases.every((phase, i) => samePhase(phase, phases[i]));
    if (!same) {
      const items = drawable.map((sub, i) => {
        const p = sub.variant.profile;
        if (p.quantities === undefined) {
          p.quantities = {};
          for (const q of ["mxy_abs", "mz", "beta_sq"]) p.quantities[q] = RfProfiles.quantity(p.result, q);
        }
        return {x: p.result.grid[0], q: p.quantities, phase: phases[i], label: groupNames(sub.group),
          color: sub.group.color};
      });
      const lanes = [];
      const of = values => items.map(it => ({x: it.x, values: values(it), label: it.label, color: it.color}));
      for (const name of LANES[slot.g.use]) {
        if (name === "mxy") {
          lanes.push(lane("mxy", "|Mxy|", "", "rf", of(it => it.q.mxy_abs), axis.scale,
            unitTicks(...items.map(it => it.q.mxy_abs))));
        } else if (name === "mz") {
          lanes.push(lane("mz", "Mz", "", "gx", of(it => it.q.mz), axis.scale, SIGNED_TICKS));
        } else if (name === "beta") {
          lanes.push(lane("beta", "|β|²", "", "rf", of(it => it.q.beta_sq), axis.scale,
            unitTicks(...items.map(it => it.q.beta_sq))));
        } else if (phases.some(phase => phase !== null)) {
          const withPhase = items.filter(it => it.phase !== null);
          lanes.push(lane("phase", "Phase at the echo", "rad", "gy",
            withPhase.map(it => ({x: it.x, values: it.phase, label: it.label, color: it.color})),
            axis.scale, PHASE_TICKS));
        }
      }
      const bands = [];
      for (const sub of drawable) {
        const {pulse} = sub;
        if (pulse.gradientKind !== "one" || pulse.nominalM === null) continue;
        const lo = pulse.sliceCentreM - pulse.nominalM / 2, hi = pulse.sliceCentreM + pulse.nominalM / 2;
        bands.push(manyGroups() ? {lo, hi, color: sub.group.color} : [lo, hi]);
      }
      const lo = Math.min(...items.map(it => it.x[0]));
      const hi = Math.max(...items.map(it => it.x[it.x.length - 1]));
      drawLanes(view.profileBox, view.svgId, `1D profile of pulse ${slot.k}`, axis, lo, hi, lanes,
        bands);
      view.drawn = {groups: groupsKey, phases};
    }

    // The widths of an excitation depend on its block (the echo pathway); the others
    // are kept with the profile.
    const width = v => (v === undefined ? "—"
      : axis.unit === "mm" ? `${fmt(v * 1e3)} mm` : `${fmt(v)} Hz`);
    const plain = v => (v === undefined ? "—" : fmt(v));
    for (const sub of drawable) {
      const {pulse} = sub;
      const p = sub.variant.profile;
      let w;
      if (pulse.use === "excitation") {
        w = RfProfiles.widths(pulse, p.result);
      } else {
        if (p.widths === undefined) p.widths = RfProfiles.widths(pulse, p.result);
        w = p.widths;
      }
      WIDTH_KEYS.forEach((key, i) => {
        sub.widthCells[i].textContent = i < 2 ? width(w[key]) : plain(w[key]);
      });
    }
  }

  // The map of `view` of a slot, for the first group that has the pulse: nothing when it
  // is on the page, its reason, drawn at once from the cache, or a job.
  function mapWork(slot, view, list) {
    const sub = slot.subs.find(s => s.variant !== null);
    const v = slot.view;
    if (v.maps[view] !== undefined || v.mapBoxes[view].dataset.reason !== undefined) return;
    const box = v.mapBoxes[view];
    if (sub === undefined) {
      box.replaceChildren(muted(`No map: ${NO_B0}.`));
      box.dataset.reason = "";
      return;
    }
    const {pulse, variant} = sub;
    if (manyGroups()) {
      v.mapTitles[view].textContent = `${v.mapTitles[view].textContent.replace(/ — .*$/, "")} — ` +
        groupNames(sub.group);
    }
    let m = variant.maps[view];
    if (m === undefined) {
      m = newRecord();
      variant.maps[view] = m;
    }
    const finish = () => {
      if (m.spec === null) {
        if (alive(slot)) {
          box.replaceChildren(muted(`No map: ${m.reason}.`));
          box.dataset.reason = "";
        }
        return;
      }
      takeResult(m);
      if (!alive(slot) || v.maps[view] !== undefined) return;
      const q = MAIN[pulse.use];
      if (m.values === undefined) m.values = RfProfiles.quantity(m.result, q);
      const outlines = view === "z_df" && pulse.nominalM !== null
        ? [[pulse.sliceCentreM - pulse.nominalM / 2, pulse.sliceCentreM + pulse.nominalM / 2,
          m.spec.axes[1].lo, m.spec.axes[1].hi]]
        : [];
      v.maps[view] = drawMap(box, `${view} map of pulse ${slot.k}`, m.spec.axes, m.values, q,
        outlines);
    };
    if (recordDone(m)) {
      finish();
      return;
    }
    box.replaceChildren(muted("Computing the map… 0 %"));
    list.push({work: viewWork(m, variant.pulse, view, null), finish, progress: fr => {
      box.firstChild.textContent = `Computing the map… ${percent(fr)}`;
    }});
  }

  // ---- The combined profile ----

  // The combined profile of the period for each group: the groups that give the pulses the
  // same offsets in Hz share a result (an "entry" with the indexes `gis` of its groups). A
  // group whose pulses cannot change a `ppm` offset into Hz (no B0) has no entry.
  function combinedWork(seqView, per, slots, list) {
    const entries = [];
    const byName = new Map();
    file.fd.groups.forEach((group, gi) => {
      const name = combinedName(seqView, per, gi);
      let entry = byName.get(name);
      if (entry === undefined) {
        entry = {name, gis: [], result: null, shift: 0, work: null};
        byName.set(name, entry);
        entries.push(entry);
      }
      entry.gis.push(gi);
    });

    const usable = [];
    const later = [];
    for (const entry of entries) {
      const kept = combinedCache.get(entry.name);
      if (kept !== undefined) {
        combinedCache.delete(entry.name);
        combinedCache.set(entry.name, kept);
        entry.result = kept.result;
        entry.shift = per.firstBlock - kept.firstBlock;
      } else {
        try {
          entry.work = RfProfiles.combinedProfile(seqView, file.fd, per,
            {view: combinedView, cache: file.lineCache, group: entry.gis[0]});
        } catch (error) {
          // A pulse of the combined profile has a `ppm` offset and the group has no B0.
          entry.noB0 = true;
          continue;
        }
        if (entry.work.done) {
          finishEntry(entry, per);
        } else {
          later.push(entry);
        }
      }
      usable.push(entry);
    }
    if (usable.length === 0) {
      showNoB0Combined();
      return;
    }
    const left = entries.filter(e => e.noB0).flatMap(e => e.gis);
    if (later.length === 0) {
      showCombined(seqView, slots, usable, left);
      return;
    }
    dropCombined();
    combinedEl.hidden = false;
    combinedNote.hidden = false;
    combinedBody.replaceChildren(muted("Computing the combined profile… 0 %"));
    for (const entry of later) {
      list.push({work: entry.work, finish: () => {
        finishEntry(entry, per);
        if (later.every(e => e.result !== null)) showCombined(seqView, slots, usable, left);
      }, progress: fr => {
        combinedBody.firstChild.textContent = `Computing the combined profile… ${percent(fr)}`;
      }});
    }
  }

  // Keeps the result of the finished work of `entry` in the cache.
  function finishEntry(entry, per) {
    entry.result = entry.work.result();
    entry.shift = 0;
    combinedCache.set(entry.name, {firstBlock: per.firstBlock, result: entry.result});
    while (combinedCache.size > MAX_COMBINED) {
      combinedCache.delete(combinedCache.keys().next().value);
    }
  }

  // No group has the pulses of the combined profile (a `ppm` offset, no B0).
  function showNoB0Combined() {
    dropCombined();
    combinedShown = {name: "no B0", summary: null, maps: []};
    combinedEl.hidden = false;
    combinedNote.hidden = true;
    combinedBody.replaceChildren(muted(`No combined profile for this period: ${NO_B0}.`));
  }

  const COMBINED_NUMBERS = [
    ["fwhm_m", "FWHM (mm)", v => fmt(v * 1e3)],
    ["edge_width_m", "Edge 10–90 % (mm)", v => fmt(v * 1e3)],
    ["signal_kept", "Signal kept", fmt],
    ["fraction_inside", "Fraction inside W", fmt],
    ["centre_signal", "Signal at the slice centre", fmt],
  ];

  // Shows the combined profile of the entries `usable` of combinedWork (each with the
  // result of the entry `name` of combinedCache). `shift` of an entry moves its blocks to
  // this period, when it comes from another period with the same layout of RF blocks.
  // `left` are the indexes of the groups that have no entry. The first entry sets the
  // structure (the blocks, the directions, the reason: they do not depend on the group) and
  // the maps. When the card shows these entries already, only the block numbers change.
  function showCombined(seqView, slots, usable, left) {
    const groups = file.fd.groups;
    const [{result, shift}] = usable;
    const name = usable.map(e => e.name).join("+");
    // The distinct pulse (its number in the table) of a block of the result.
    const slotOf = b => slots.find(s => s.g.key === blockKey(seqView, b + shift));
    const blocks = result.reason === null ? [result.excitationBlock, ...result.refocusingBlocks] : [];
    // The pulses of the blocks of an entry, in its first group.
    const pulsesOf = entry => [entry.result.excitationBlock, ...entry.result.refocusingBlocks]
      .map(b => RfProfiles.blockPulse(seqView, file.fd, b + entry.shift,
        {maxBlocks: 1, group: entry.gis[0]}));
    const label = entry => entry.gis.map(gi => groupNames(groups[gi])).join(", ");
    const summaryText = () => {
      const names = blocks.map(b => {
        const s = slotOf(b);
        return `pulse ${s ? s.k : "?"} (block ${b + shift})`;
      });
      let text = `Excitation: ${names[0]}; refocusing: ${names.slice(1).join(", ")}. ` +
        `Directions: ${result.directions.length ? result.directions.join(", ") : "none"}.`;
      if (pulsesOf(usable[0]).some(p => p.gradientKind === "none")) {
        text += ` The pulses without a gradient give a factor of ${fmt(result.factor)}.`;
      }
      if (left.length) {
        text += ` Not drawn for ${left.map(gi => groupNames(groups[gi])).join(", ")}: ${NO_B0}.`;
      }
      if (usable.length > 1 && result.maps.length) {
        text += ` The maps are for ${label(usable[0])}.`;
      }
      return text;
    };
    if (combinedShown !== null && combinedShown.name === name) {
      if (combinedShown.summary !== null) combinedShown.summary.textContent = summaryText();
      return;
    }
    dropCombined();
    combinedShown = {name, summary: null, maps: []};
    if (result.reason === RfProfiles.REASONS.NO_REFOCUSING) {
      combinedEl.hidden = true;
      combinedBody.replaceChildren();
      return;
    }
    combinedEl.hidden = false;
    if (result.reason !== null) {
      combinedNote.hidden = true;
      combinedBody.replaceChildren(muted(`No combined profile for this period: ${result.reason}.`));
      return;
    }
    combinedNote.hidden = false;
    const shownNumbers = COMBINED_NUMBERS.filter(([key]) => result.numbers[key] !== undefined);
    const many = manyGroups();
    const summary = el("p", {}, summaryText());
    combinedShown.summary = summary;
    const headers = [...(many ? ["Target"] : []), ...shownNumbers.map(([, label]) => label)];
    const rows = usable.map(entry => el("tr", {},
      ...(many ? [el("td", {}, label(entry))] : []),
      ...shownNumbers.map(([key, , text]) => el("td", {}, text(entry.result.numbers[key])))));
    const parts = [summary, el("div", {class: "scroll"}, el("table", {},
      el("thead", {}, el("tr", {}, ...headers.map(h => el("th", {}, h)))),
      el("tbody", {}, ...rows))),
    ];

    const pulsesByEntry = usable.map(pulsesOf);
    const centreOf = (pulses, kind) => {
      const p = pulses.find(q => q.gradientKind === "one" && q.selectKind === kind);
      return p ? p.sliceCentreM : null;
    };
    const nominal = file.fd.sliceThicknessM;
    if (result.line !== null) {
      const axis = axisOf(result.directions[0]);
      const colors = ["rf", "gy", "gz", "gx"];
      const ticks = unitTicks(...usable.flatMap(e =>
        [e.result.line.values, ...e.result.linePulses.map(lp => lp.values)]));
      const item = (entry, values) => ({x: entry.result.line.u, values, label: label(entry),
        color: groups[entry.gis[0]].color});
      const lanes = result.linePulses.map((lp, i) => {
        const s = slotOf(lp.block);
        const use = s ? s.g.use : "";
        const title = `Pulse ${s ? s.k : "?"} ${use === "excitation" ? "|Mxy|" : "|β|²"}`;
        return lane(`line-${i}`, title, "", colors[i % colors.length],
          usable.map(e => item(e, e.result.linePulses[i].values)), axis.scale, ticks);
      });
      lanes.push(lane("combined", "Combined", "", "adc",
        usable.map(e => item(e, e.result.line.values)), axis.scale, ticks));
      const bands = [];
      usable.forEach((entry, k) => {
        const c = centreOf(pulsesByEntry[k], result.directions[0]);
        if (nominal === null || c === null) return;
        const band = [c - nominal / 2, c + nominal / 2];
        bands.push(many ? {lo: band[0], hi: band[1], color: groups[entry.gis[0]].color} : band);
      });
      const lo = Math.min(...usable.map(e => e.result.line.u[0]));
      const hi = Math.max(...usable.map(e => e.result.line.u[e.result.line.u.length - 1]));
      const box = el("div");
      parts.push(box);
      combinedBody.replaceChildren(...parts);
      drawLanes(box, `${id}-combined-line`, "Combined profile of the first echo", axis,
        lo, hi, lanes, bands);
      return;
    }
    if (result.maps.length === 0 && result.directions.length > 1) {
      parts.push(muted(`The combined profile of ${result.directions.length} directions is a ` +
        'map, and the "2d" view of this card is off.'));
    }
    const boxes = result.maps.map(() => el("div"));
    result.maps.forEach((m, i) => {
      const [a, b] = m.axes;
      let title = `${a.kind} × ${b.kind}`;
      if (result.maps.length === 3) {
        const third = ["x", "y", "z"].find(k => k !== a.kind && k !== b.kind);
        title += `, through the slice centre on ${third}`;
      }
      parts.push(el("p", {}, el("strong", {}, title)), boxes[i]);
    });
    combinedBody.replaceChildren(...parts);
    result.maps.forEach((m, i) => {
      const [a, b] = m.axes;
      const ca = centreOf(pulsesByEntry[0], a.kind), cb = centreOf(pulsesByEntry[0], b.kind);
      const outlines = nominal !== null && ca !== null && cb !== null
        ? [[ca - nominal / 2, ca + nominal / 2, cb - nominal / 2, cb + nominal / 2]] : [];
      combinedShown.maps.push(drawMap(boxes[i], `Combined profile, ${a.kind} × ${b.kind}`,
        m.axes, m.values, "combined", outlines));
    });
  }

  // ---- Start ----

  for (const topic of ["sequence", "cursor", "anchor"]) {
    PulseqReport.subscribe(topic, message => onMessage(topic, message));
  }

  // The gamma control of the "Distinct pulses" table (one table for each |gamma|).
  PulseqReport.gammaSelect(section);
  for (const button of section.querySelectorAll("button[data-block]")) {
    PulseqReport.requestButton(button, "goto");
    button.addEventListener("click", () => {
      PulseqReport.publish("goto", {source: id, block: Number(button.dataset.block)});
    });
  }
});
