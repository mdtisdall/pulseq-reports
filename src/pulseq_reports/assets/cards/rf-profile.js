// RF profile card (docs/plans/rf-profiles.md, section 4.5, items 3 to 6): the RF pulses
// of the period at the cursor of one sequence diagram card, simulated in the browser
// with RfProfiles (assets/rf_profiles.js).
//
// The card follows the diagram only through its messages (section 4.1): `sequence`
// gives the sequence view of each file that the diagram has decoded, with the file's
// name; `cursor` and `anchor` give a block of the file that the diagram shows. The card
// data (cards/rf_profile.py) has the files in the order of the card's own list, so the
// card matches a diagram file to its own by name (the names are unique, decision 23).
// The card subscribes to no `view` message: nothing here depends on the diagram's view
// (decision 13).
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
// GRE has one key). Each file also has a line cache (RfProfiles, decision 25) that the
// combined profile shares with the 1D profiles; the entries of a pulse key leave it with
// that key. Combined profiles are kept by the layout of the RF blocks of their period
// (MAX_COMBINED of them), so a move to the next TR of the same kind draws at once.
//
// The echo pathway belongs to the block, not to the key: the phase at the echo and the
// phase numbers of an excitation come from its last block in the period (the one
// nearest to the ADC), with the profile of its key.
//
// The "Show" buttons of the pulse lists publish `goto` with the file's name (decision
// 25), so they also work for a file that the diagram has not shown yet.
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
  const diagramId = data.diagram_card_id;
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

  // ---- Files ----

  // One state for each file of the card data, in its order. `fd` is the RfProfiles file
  // data once the RF table is decoded; `blockKeys` maps the event ids of an RF block
  // ("rf,gx,gy,gz") to its pulse key, so that the key of a block needs one blockPulse
  // call for each distinct combination.
  const files = data.files.map((entry, index) => ({
    index, entry, fd: null, decoding: null, error: null,
    lineCache: new Map(), blockKeys: new Map(),
  }));
  const fileByName = new Map(files.map(f => [f.entry.name, f]));
  // The files of the diagram, by the diagram's own file index: {name, file (a state
  // above, or null when the card does not have that name), seqView}.
  const diagramFiles = new Map();

  function decodeFile(f) {
    if (f.decoding === null) {
      const rf = f.entry.rf;
      const names = Object.keys(rf);
      f.decoding = Promise.all(names.map(name => PulseqReport.decodeTable(rf[name])))
        .then(arrays => {
          const tables = {};
          names.forEach((name, i) => { tables[name] = arrays[i]; });
          f.fd = RfProfiles.fileData(f.entry, tables);
        })
        .catch(error => {
          f.error = error;
          console.error(`RF profile card "${id}": the RF table of "${f.entry.name}":`, error);
        })
        .then(select);
    }
    return f.decoding;
  }

  // The pulse key of the RF block `b`.
  function blockKey(f, seqView, b) {
    const ev = seqView.events(b);
    const combo = `${ev.rf},${ev.gx},${ev.gy},${ev.gz}`;
    let key = f.blockKeys.get(combo);
    if (key === undefined) {
      key = RfProfiles.blockPulse(seqView, f.fd, b, {maxBlocks: 1}).key;
      f.blockKeys.set(combo, key);
    }
    return key;
  }

  // ---- The caches ----

  // `${file index}/${pulse key}` -> {file, key, pulse, profile, maps: {view}}, in the
  // order of use (the first entry is the least recently used). `profile` and each map
  // are a record of one view of the pulse (newRecord).
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

  // The cache entry of `key`, made with the pulse that `makePulse()` gives (a pulse of
  // a block with that key) when the cache does not have it.
  function keyEntry(f, key, makePulse) {
    const name = `${f.index}/${key}`;
    let entry = keyCache.get(name);
    if (entry !== undefined) {
      keyCache.delete(name);
      keyCache.set(name, entry);
      return entry;
    }
    const pulse = makePulse();
    entry = {file: f, key, pulse, profile: newRecord(), maps: {}};
    keyCache.set(name, entry);
    while (keyCache.size > MAX_KEYS) {
      const [oldName, old] = keyCache.entries().next().value;
      keyCache.delete(oldName);
      const prefix = `${old.key}|`;
      for (const lineKey of Array.from(old.file.lineCache.keys())) {
        if (lineKey.startsWith(prefix)) old.file.lineCache.delete(lineKey);
      }
    }
    return entry;
  }

  // `${file index}/${layout}/${view}` -> {firstBlock, result}: the combined profiles,
  // by the layout of the RF blocks of their period up to its first ADC (each block's
  // offset from the period start and its pulse key), which decides the result; its
  // blocks are those of the period `firstBlock`.
  const combinedCache = new Map();

  function combinedName(f, seqView, per) {
    const parts = [];
    if (per.firstAdcBlock !== null) {
      for (let b = per.firstBlock; b <= per.firstAdcBlock; b++) {
        if (seqView.events(b).rf !== 0) parts.push(`${b - per.firstBlock}:${blockKey(f, seqView, b)}`);
      }
    }
    return `${f.index}/${parts.join(",")}/${combinedView}`;
  }

  // ---- Which period ----

  let anchor = null; // {diagram file, block} of the diagram's anchor, or null
  let cursor = null; // {diagram file, block} of the last cursor in the plot, or null
  // What the card shows: null (nothing yet), {note} (a line of text only), or {file,
  // diagramFile, seqView, per, pinned}.
  let shown = null;
  let frame = null;

  function onMessage(topic, message) {
    if (message.source !== diagramId) return;
    if (topic === "sequence") {
      const f = fileByName.get(message.name) ?? null;
      diagramFiles.set(message.file, {name: message.name, file: f, seqView: message.view});
      if (f !== null && f.entry.labeled) decodeFile(f);
      return;
    }
    const at = message.file === null ? null : {diagramFile: message.file, block: message.block};
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
    const d = diagramFiles.get(target.diagramFile);
    if (d === undefined) return;
    const f = d.file;
    if (f === null) {
      showNote(`The diagram shows "${d.name}", which this card does not have.`);
      return;
    }
    const name = f.entry.name;
    if (!f.entry.labeled) {
      showNote(`${name}: this file has RF pulses without a use label, so the card shows ` +
        "no profiles for it (see the note above).");
      return;
    }
    if (f.error !== null) {
      showNote(`${name}: the card could not read its RF table: ${f.error.message}`);
      return;
    }
    if (f.fd === null) {
      decodeFile(f);
      statusEl.textContent = `Loading the RF pulses of ${name}…`;
      return;
    }
    if (f.fd.firstRfBlock === null) {
      showNote(`${name}: this file has no RF pulses.`);
      return;
    }
    const seqView = d.seqView;
    const block = Math.min(Math.max(target.block, 0), seqView.numBlocks - 1);
    const pinned = target === anchor;
    const same = shown !== null && shown.per !== undefined && shown.file === f &&
      shown.diagramFile === target.diagramFile;
    if (same && !shown.per.truncated && block >= shown.per.firstBlock &&
        block <= shown.per.lastBlock) {
      if (shown.pinned !== pinned) {
        shown.pinned = pinned;
        statusEl.textContent = statusText();
      }
      return;
    }
    const per = RfProfiles.period(seqView, f.fd, block);
    if (same && per.firstBlock === shown.per.firstBlock && per.lastBlock === shown.per.lastBlock) {
      shown.pinned = pinned;
      statusEl.textContent = statusText();
      return;
    }
    shown = {file: f, diagramFile: target.diagramFile, seqView, per, pinned};
    stopWork();
    if (frame === null) frame = requestAnimationFrame(render);
  }

  function statusText() {
    const {file: f, seqView, per, pinned} = shown;
    const t0 = seqView.blockStart(per.firstBlock) * 1e3;
    const t1 = (seqView.blockStart(per.lastBlock) + seqView.blockDuration(per.lastBlock)) * 1e3;
    const n = per.pulses.length;
    let text = `${f.entry.name}: blocks ${per.firstBlock}–${per.lastBlock} ` +
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

  // One line lane of values at the points x (scaled for the axis), cut where a value is
  // not finite (the echo phase is NaN where |Mxy| is small).
  function lane(laneId, title, unit, color, x, scale, values, ticks) {
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
    return {id: laneId, title, unit, color, kind: "line", segments, fill: null, ...ticks};
  }

  function drawLanes(container, svgId, label, axis, lo, hi, lanes, bands) {
    const {box, svg, tip} = chartBox(svgId, label, false);
    container.replaceChildren(box);
    const xDomain = [lo * axis.scale, hi * axis.scale];
    PulseqReport.laneChart({
      svg, chart: box, tip, lanes, xDomain, minSpan: (xDomain[1] - xDomain[0]) / 1000,
      xLabel: axis.label,
      cursorText: v => `${axis.name} = ${fmt(v)} ${axis.unit}`,
      bands: bands.map(([a, b]) => [a * axis.scale, b * axis.scale]),
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

  // The elements of each distinct pulse of the shown period, by `${file index}/${pulse
  // key}`: {el, heading, profileBox, drawn (the 1D chart is drawn), phase (the echo
  // phase it shows, or null), mapBoxes: {view}, maps: {view: map chart}}. A pulse of the
  // next period with the same key keeps its elements, so a move to the next TR of a
  // sequence draws no chart again, except a 1D chart whose echo phase changes.
  let pulseViews = new Map();
  let nextViewId = 0;

  function dropView(v) {
    for (const chart of Object.values(v.maps)) chart.destroy();
  }

  function makeView(pulse) {
    const v = {heading: el("h4"), profileBox: el("div"), drawn: false, phase: null,
      mapBoxes: {}, maps: {}, svgId: `${id}-lanes-${nextViewId++}`};
    v.el = el("div", {}, v.heading, v.profileBox);
    for (const view of mapViews) {
      const title = view === "z_df" ? "Select coordinate × Δf" : "Two spatial axes";
      v.mapBoxes[view] = el("div");
      v.el.append(el("p", {}, el("strong", {}, `${title} (${QUANTITY_LABEL[MAIN[pulse.use]]})`)),
        v.mapBoxes[view]);
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

  const mm = v => (v === null || v === undefined ? "—" : fmt(v * 1e3));

  function render() {
    frame = null;
    if (shown === null || shown.per === undefined) return;
    const {file: f, seqView, per} = shown;
    stopWork();
    statusEl.textContent = statusText();

    // One slot for each distinct pulse: its key's cache entry, its pulse (for an
    // excitation, the pulse of its last block, for the echo pathway of that block; else
    // the key's pulse), and its elements.
    const views = new Map();
    const slots = per.pulses.map((g, i) => {
      const name = `${f.index}/${g.key}`;
      let pulse = g.use === "excitation" ? RfProfiles.blockPulse(seqView, f.fd, g.lastBlock) : null;
      const entry = keyEntry(f, g.key,
        () => pulse ?? RfProfiles.blockPulse(seqView, f.fd, g.lastBlock));
      if (pulse === null) pulse = entry.pulse;
      const view = pulseViews.get(name) ?? makeView(pulse);
      views.set(name, view);
      view.heading.textContent =
        `Pulse ${i + 1}: ${pulse.use}, ${gradientText(pulse)}, ×${g.count}`;
      return {k: i + 1, g, name, pulse, entry, view};
    });
    for (const [name, v] of pulseViews) if (!views.has(name)) dropView(v);
    pulseViews = views;

    const tbody = el("tbody");
    for (const slot of slots) {
      const {k, g, pulse} = slot;
      const notes = pulse.notes.slice();
      if (pulse.use === "excitation" && pulse.echo === null && pulse.echoReason !== null) {
        notes.push(`phase at the echo: ${pulse.echoReason}`);
      }
      if (slot.entry.profile.reason !== null) notes.push(slot.entry.profile.reason);
      slot.widthCells = WIDTH_KEYS.map(() => el("td", {}, "…"));
      slot.notes = notes;
      slot.notesCell = el("td", {}, notes.join("; "));
      tbody.append(el("tr", {},
        el("td", {}, String(k)), el("td", {}, pulse.use), el("td", {}, String(g.count)),
        el("td", {}, gradientText(pulse)), el("td", {}, fmt(pulse.flipDeg)),
        el("td", {}, fmt(pulse.peakB1Ut)), el("td", {}, fmt(pulse.energyUt2Ms)),
        el("td", {}, mm(pulse.nominalM)), el("td", {}, mm(pulse.sliceCentreM)),
        ...slot.widthCells, slot.notesCell));
    }
    const table = el("div", {class: "scroll"}, el("table", {},
      el("thead", {}, el("tr", {}, ...TABLE_HEADERS.map(h => el("th", {}, h)))), tbody));
    pulsesEl.replaceChildren(table, ...slots.map(s => s.view.el));

    // The 1D profiles at once, in the order of the table (section 4.5, item 5); then the
    // combined profile and the maps, in slices.
    for (const slot of slots) profileNow(slot);
    const list = [];
    combinedWork(f, seqView, per, slots, list);
    for (const view of mapViews) for (const slot of slots) mapWork(slot, view, list);
    startWork(list);
  }

  // The view of `slot` is still on the page (a job can end after its period has gone).
  const alive = slot => pulseViews.get(slot.name) === slot.view;

  // The 1D profile of a slot, at once: its reason, or its chart (from the cache, or
  // computed here).
  function profileNow(slot) {
    const {entry, view} = slot;
    const p = entry.profile;
    if (!recordDone(p)) {
      const work = viewWork(p, entry.pulse, "profile", entry.file.lineCache);
      while (!work.done) work.step(Infinity);
    }
    if (p.spec === null) {
      if (!view.drawn) {
        view.profileBox.replaceChildren(muted(`No 1D profile: ${p.reason}.`));
        view.drawn = true;
      }
      if (!slot.notes.includes(p.reason)) {
        slot.notesCell.textContent = [...slot.notes, p.reason].join("; ");
      }
      for (const cell of slot.widthCells) cell.textContent = "—";
      return;
    }
    takeResult(p);
    showProfile(slot);
  }

  const samePhase = (a, b) => a === b || (a !== null && b !== null && a.length === b.length &&
    a.every((v, i) => v === b[i] || (Number.isNaN(v) && Number.isNaN(b[i]))));

  // Draws the 1D chart of a slot, unless the same chart is on the page, and fills the
  // width cells of its row.
  function showProfile(slot) {
    const {pulse, entry, view} = slot;
    const p = entry.profile;
    const profile = p.result;
    const axis = axisOf(profile.spec.axes[0].kind);
    const phase = pulse.use === "excitation" && pulse.gradientKind === "one"
      ? RfProfiles.echoPhase(pulse, profile) : null;
    if (!view.drawn || !samePhase(view.phase, phase)) {
      if (p.quantities === undefined) {
        p.quantities = {};
        for (const q of ["mxy_abs", "mz", "beta_sq"]) p.quantities[q] = RfProfiles.quantity(profile, q);
      }
      const q = p.quantities;
      const x = profile.grid[0];
      const lanes = [];
      for (const name of LANES[pulse.use]) {
        if (name === "mxy") {
          lanes.push(lane("mxy", "|Mxy|", "", "rf", x, axis.scale, q.mxy_abs, unitTicks(q.mxy_abs)));
        } else if (name === "mz") {
          lanes.push(lane("mz", "Mz", "", "gx", x, axis.scale, q.mz, SIGNED_TICKS));
        } else if (name === "beta") {
          lanes.push(lane("beta", "|β|²", "", "rf", x, axis.scale, q.beta_sq, unitTicks(q.beta_sq)));
        } else if (phase !== null) {
          lanes.push(lane("phase", "Phase at the echo", "rad", "gy", x, axis.scale, phase,
            PHASE_TICKS));
        }
      }
      const bands = pulse.gradientKind === "one" && pulse.nominalM !== null
        ? [[pulse.sliceCentreM - pulse.nominalM / 2, pulse.sliceCentreM + pulse.nominalM / 2]]
        : [];
      drawLanes(view.profileBox, view.svgId, `1D profile of pulse ${slot.k}`, axis,
        x[0], x[x.length - 1], lanes, bands);
      view.drawn = true;
      view.phase = phase;
    }

    // The widths of an excitation depend on its block (the echo pathway); the others
    // are kept with the profile.
    let w;
    if (pulse.use === "excitation") {
      w = RfProfiles.widths(pulse, profile);
    } else {
      if (p.widths === undefined) p.widths = RfProfiles.widths(pulse, profile);
      w = p.widths;
    }
    const width = v => (v === undefined ? "—"
      : axis.unit === "mm" ? `${fmt(v * 1e3)} mm` : `${fmt(v)} Hz`);
    const plain = v => (v === undefined ? "—" : fmt(v));
    WIDTH_KEYS.forEach((key, i) => {
      slot.widthCells[i].textContent = i < 2 ? width(w[key]) : plain(w[key]);
    });
  }

  // The map of `view` of a slot: nothing when it is on the page, its reason, drawn at
  // once from the cache, or a job.
  function mapWork(slot, view, list) {
    const {entry, pulse} = slot;
    const v = slot.view;
    if (v.maps[view] !== undefined || v.mapBoxes[view].dataset.reason !== undefined) return;
    const box = v.mapBoxes[view];
    let m = entry.maps[view];
    if (m === undefined) {
      m = newRecord();
      entry.maps[view] = m;
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
    list.push({work: viewWork(m, entry.pulse, view, null), finish, progress: fr => {
      box.firstChild.textContent = `Computing the map… ${percent(fr)}`;
    }});
  }

  // ---- The combined profile ----

  function combinedWork(f, seqView, per, slots, list) {
    const name = combinedName(f, seqView, per);
    const kept = combinedCache.get(name);
    if (kept !== undefined) {
      combinedCache.delete(name);
      combinedCache.set(name, kept);
      showCombined(f, seqView, slots, name, kept.result, per.firstBlock - kept.firstBlock);
      return;
    }
    const work = RfProfiles.combinedProfile(seqView, f.fd, per,
      {view: combinedView, cache: f.lineCache});
    const finish = () => {
      const result = work.result();
      combinedCache.set(name, {firstBlock: per.firstBlock, result});
      while (combinedCache.size > MAX_COMBINED) {
        combinedCache.delete(combinedCache.keys().next().value);
      }
      showCombined(f, seqView, slots, name, result, 0);
    };
    if (work.done) {
      finish();
      return;
    }
    dropCombined();
    combinedEl.hidden = false;
    combinedNote.hidden = false;
    combinedBody.replaceChildren(muted("Computing the combined profile… 0 %"));
    list.push({work, finish, progress: fr => {
      combinedBody.firstChild.textContent = `Computing the combined profile… ${percent(fr)}`;
    }});
  }

  const COMBINED_NUMBERS = [
    ["fwhm_m", "FWHM (mm)", v => fmt(v * 1e3)],
    ["edge_width_m", "Edge 10–90 % (mm)", v => fmt(v * 1e3)],
    ["signal_kept", "Signal kept", fmt],
    ["fraction_inside", "Fraction inside W", fmt],
    ["centre_signal", "Signal at the slice centre", fmt],
  ];

  // Shows the combined profile `result` (the entry `name` of combinedCache). `shift`
  // moves its blocks to this period, when it comes from another period with the same
  // layout of RF blocks. When the card shows that entry already, only the block numbers
  // change.
  function showCombined(f, seqView, slots, name, result, shift) {
    // The distinct pulse (its number in the table) of a block of the result.
    const slotOf = b => slots.find(s => s.g.key === blockKey(f, seqView, b + shift));
    const blocks = result.reason === null ? [result.excitationBlock, ...result.refocusingBlocks] : [];
    const pulses = blocks.map(b => RfProfiles.blockPulse(seqView, f.fd, b + shift, {maxBlocks: 1}));
    const summaryText = () => {
      const names = blocks.map(b => {
        const s = slotOf(b);
        return `pulse ${s ? s.k : "?"} (block ${b + shift})`;
      });
      let text = `Excitation: ${names[0]}; refocusing: ${names.slice(1).join(", ")}. ` +
        `Directions: ${result.directions.length ? result.directions.join(", ") : "none"}.`;
      if (pulses.some(p => p.gradientKind === "none")) {
        text += ` The pulses without a gradient give a factor of ${fmt(result.factor)}.`;
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
    const numbers = result.numbers;
    const shownNumbers = COMBINED_NUMBERS.filter(([key]) => numbers[key] !== undefined);
    const summary = el("p", {}, summaryText());
    combinedShown.summary = summary;
    const parts = [summary, el("div", {class: "scroll"}, el("table", {},
      el("thead", {}, el("tr", {}, ...shownNumbers.map(([, label]) => el("th", {}, label)))),
      el("tbody", {}, el("tr", {},
        ...shownNumbers.map(([key, , text]) => el("td", {}, text(numbers[key]))))))),
    ];

    const centreOf = kind => {
      const p = pulses.find(q => q.gradientKind === "one" && q.selectKind === kind);
      return p ? p.sliceCentreM : null;
    };
    const nominal = f.fd.sliceThicknessM;
    if (result.line !== null) {
      const u = result.line.u;
      const axis = axisOf(result.directions[0]);
      const colors = ["rf", "gy", "gz", "gx"];
      const ticks = unitTicks(result.line.values, ...result.linePulses.map(lp => lp.values));
      const lanes = result.linePulses.map((lp, i) => {
        const s = slotOf(lp.block);
        const use = s ? s.pulse.use : "";
        const title = `Pulse ${s ? s.k : "?"} ${use === "excitation" ? "|Mxy|" : "|β|²"}`;
        return lane(`line-${i}`, title, "", colors[i % colors.length], u, axis.scale, lp.values,
          ticks);
      });
      lanes.push(lane("combined", "Combined", "", "adc", u, axis.scale, result.line.values,
        ticks));
      const c = centreOf(result.directions[0]);
      const bands = nominal !== null && c !== null ? [[c - nominal / 2, c + nominal / 2]] : [];
      const box = el("div");
      parts.push(box);
      combinedBody.replaceChildren(...parts);
      drawLanes(box, `${id}-combined-line`, "Combined profile of the first echo", axis,
        u[0], u[u.length - 1], lanes, bands);
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
      const ca = centreOf(a.kind), cb = centreOf(b.kind);
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

  for (const button of section.querySelectorAll("button[data-file][data-block]")) {
    button.addEventListener("click", () => {
      const f = files[Number(button.dataset.file)];
      PulseqReport.publish("goto", {source: id, target: diagramId, name: f.entry.name,
        block: Number(button.dataset.block)});
    });
  }
});
