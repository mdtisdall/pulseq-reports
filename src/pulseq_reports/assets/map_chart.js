// The 2D map chart: a canvas raster (one canvas pixel per grid point) with an SVG
// overlay for axes, a color legend, a crosshair and a tooltip. Loaded after
// lane_chart.js; adds PulseqReport.mapChart without changing lane_chart.js itself.
// Generalizes vb-pulseq's columnChart (report.js at 3a1c7dd, lines 520-727) from one
// fixed n x n signal grid to any x/y axes and any values array (docs/plans/
// rf-profiles.md section 4.4).
(() => {
  const {el, text} = PulseqReport;
  const {niceTicks, fmt, colorRamp, colorIndex, nearestIndex} = ChartMath;

  // The viewBox geometry, close to vb's #column-chart (570 x 580, CLEFT/CRIGHT/CTOP/
  // CAXIS_H the same). A map chart is not drawn at the data's physical aspect ratio:
  // the plot area is always CPLOT x CPLOT, whatever the axes' own lo/hi ranges are.
  const CW = 570, CH = 580, CLEFT = 70, CRIGHT = 20, CTOP = 16, CAXIS_H = 34;
  const CPLOT = CW - CLEFT - CRIGHT;
  // The resolution of the canvas color lookup table built from the CSS ramp stops.
  const LUT_STEPS = 256;

  // A counter for the per-chart id of the legend's <linearGradient>, so that several
  // map charts on one page do not share (or clash over) the same gradient id. This is
  // the only id mapChart makes for itself; the caller's own elements need none.
  let nextChartId = 0;

  function hexToRgb(hex) {
    const h = hex.trim().replace("#", "");
    return [0, 2, 4].map(k => parseInt(h.slice(k, k + 2), 16));
  }

  function themeKey() {
    const attr = document.documentElement.getAttribute("data-theme");
    if (attr === "light" || attr === "dark") return attr;
    return matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }

  // The CSS custom property names of a scale's stops, low to high (report.css).
  function stopNames(scale) {
    return scale === "diverging"
      ? ["--map-div-0", "--map-div-1", "--map-div-2", "--map-div-3", "--map-div-4"]
      : ["--map-seq-0", "--map-seq-1", "--map-seq-2", "--map-seq-3"];
  }

  // Reads the current theme's colors for `scale` from the page's CSS custom
  // properties and builds a LUT_STEPS-color lookup table with colorRamp.
  function buildLut(scale) {
    const style = getComputedStyle(document.documentElement);
    const stops = stopNames(scale).map(name => hexToRgb(style.getPropertyValue(name)));
    return colorRamp(stops, LUT_STEPS);
  }

  // One map chart. `canvas`, `svg`, `chart` and `tip` are existing DOM elements (the
  // caller's container has class="chart map-chart", and the svg has tabindex="0",
  // role="img" and an aria-label, as a laneChart's svg does). `x` and `y` are axis
  // objects {lo, hi, n, label}. `values` is a Float32Array or Float64Array of length
  // x.n * y.n, row-major (n_y rows, n_x columns): values[iy * x.n + ix] is at
  // (x at index ix, y at index iy). `domain` is [lo, hi] for the color scale. `scale`
  // is "sequential" or "diverging" (report.css --map-seq-* / --map-div-*). `valueLabel`
  // is the legend's label. `cursorText(x, y, v)` formats the tooltip text; without it,
  // the default shows the axis labels and the value, each formatted with fmt.
  // `outlines` is a list of [x0, x1, y0, y1] axis-unit rectangles, drawn dashed.
  // Returns {setData({x, y, values, domain})}, which replaces the axes and the values
  // and redraws, without making a new chart. No zoom.
  function mapChart({canvas, svg, chart, tip, x, y, values, domain, scale = "sequential",
                     valueLabel = "Value", cursorText, outlines = []}) {
    const chartId = nextChartId++;
    svg.setAttribute("viewBox", `0 0 ${CW} ${CH}`);

    let X = x, Y = y, V = values, DOMAIN = domain.slice();
    const defaultCursorText = (xv, yv, v) =>
      `${X.label} = ${fmt(xv)}, ${Y.label} = ${fmt(yv)}, ${valueLabel} = ${fmt(v)}`;
    const cursorTextFor = cursorText ?? defaultCursorText;

    // The pixel position, in viewBox units, of an axis value; the inverse of these
    // (used by the pointer handler) is the plain linear interpolation below.
    const xPx = v => CLEFT + (v - X.lo) / (X.hi - X.lo) * CPLOT;
    const yPx = v => CTOP + (Y.hi - v) / (Y.hi - Y.lo) * CPLOT;
    // The axis value of grid index i (0 to n - 1).
    const xAt = i => X.n === 1 ? X.lo : X.lo + (X.hi - X.lo) * i / (X.n - 1);
    const yAt = j => Y.n === 1 ? Y.lo : Y.lo + (Y.hi - Y.lo) * j / (Y.n - 1);

    let cross = null;
    // The grid index of the cursor, or null when it is hidden. The crosshair and the
    // tooltip always sit exactly on a grid point (nearestIndex), never at the raw
    // pointer position, so the position they show and the value they read always
    // agree with each other and with the arrow keys.
    let cursorIx = null, cursorIy = null;
    // One cached ImageData for each theme key ("light"/"dark"), rebuilt by setData.
    let imageCache = {};

    function positionCanvas() {
      canvas.width = X.n;
      canvas.height = Y.n;
      canvas.style.left = `${(CLEFT / CW * 100).toFixed(4)}%`;
      canvas.style.top = `${(CTOP / CH * 100).toFixed(4)}%`;
      canvas.style.width = `${(CPLOT / CW * 100).toFixed(4)}%`;
      canvas.style.height = `${(CPLOT / CH * 100).toFixed(4)}%`;
    }

    function imageDataForTheme() {
      const key = themeKey();
      if (!imageCache[key]) {
        const lut = buildLut(scale);
        const pixels = new Uint8ClampedArray(X.n * Y.n * 4);
        for (let row = 0; row < Y.n; row++) {
          // Image row 0 is the top of the canvas, the highest y value. V is row-major
          // with row 0 at the lowest y (the values contract), so the source row is
          // read back to front, as vb's columnChart does for its own square grid.
          const srcRow = Y.n - 1 - row;
          for (let col = 0; col < X.n; col++) {
            const v = V[srcRow * X.n + col];
            const p = (row * X.n + col) * 4;
            const idx = colorIndex(v, DOMAIN, LUT_STEPS);
            if (idx < 0) continue; // NaN: leave alpha at 0, transparent.
            pixels[p] = lut[idx * 3];
            pixels[p + 1] = lut[idx * 3 + 1];
            pixels[p + 2] = lut[idx * 3 + 2];
            pixels[p + 3] = 255;
          }
        }
        imageCache[key] = new ImageData(pixels, X.n, Y.n);
      }
      return imageCache[key];
    }

    function drawCanvas() {
      canvas.getContext("2d").putImageData(imageDataForTheme(), 0, 0);
    }

    function setCursor(xv, yv) {
      if (xv === null) {
        cursorIx = cursorIy = null;
        cross.v.setAttribute("visibility", "hidden");
        cross.h.setAttribute("visibility", "hidden");
        tip.hidden = true;
        return;
      }
      const cx = Math.min(X.hi, Math.max(X.lo, xv));
      const cy = Math.min(Y.hi, Math.max(Y.lo, yv));
      cursorIx = nearestIndex(X.lo, X.hi, X.n, cx);
      cursorIy = nearestIndex(Y.lo, Y.hi, Y.n, cy);
      const gx = xAt(cursorIx), gy = yAt(cursorIy);
      const v = V[cursorIy * X.n + cursorIx];

      cross.v.setAttribute("x1", xPx(gx));
      cross.v.setAttribute("x2", xPx(gx));
      cross.v.setAttribute("visibility", "visible");
      cross.h.setAttribute("y1", yPx(gy));
      cross.h.setAttribute("y2", yPx(gy));
      cross.h.setAttribute("visibility", "visible");

      tip.replaceChildren();
      const row = document.createElement("div");
      row.className = "row";
      row.textContent = cursorTextFor(gx, gy, v);
      tip.appendChild(row);
      tip.hidden = false;
      const r = svg.getBoundingClientRect(), wrap = chart.getBoundingClientRect();
      const left = xPx(gx) * r.width / CW + (r.left - wrap.left);
      const width = tip.offsetWidth;
      tip.style.left = `${left + 12 + width > wrap.width ? left - 12 - width : left + 12}px`;
    }

    function renderAxes() {
      svg.replaceChildren();

      for (const t of niceTicks(X.lo, X.hi, 6)) {
        el("line", {x1: xPx(t), x2: xPx(t), y1: CTOP, y2: CTOP + CPLOT, class: "grid"}, svg);
        text({x: xPx(t), y: CTOP + CPLOT + 16, class: "tick", "text-anchor": "middle"},
          String(t), svg);
      }
      for (const t of niceTicks(Y.lo, Y.hi, 6)) {
        el("line", {x1: CLEFT, x2: CLEFT + CPLOT, y1: yPx(t), y2: yPx(t), class: "grid"}, svg);
        text({x: CLEFT - 8, y: yPx(t) + 4, class: "tick", "text-anchor": "end"}, String(t), svg);
      }
      el("rect", {x: CLEFT, y: CTOP, width: CPLOT, height: CPLOT, fill: "none", class: "base"},
        svg);
      text({x: CLEFT + CPLOT / 2, y: CTOP + CPLOT + CAXIS_H - 2, class: "lbl",
        "text-anchor": "middle"}, X.label, svg);
      const vLabel = el("text", {x: 14, y: CTOP + CPLOT / 2, class: "lbl",
        "text-anchor": "middle", transform: `rotate(-90 14 ${CTOP + CPLOT / 2})`}, svg);
      vLabel.textContent = Y.label;

      for (const [x0, x1, y0, y1] of outlines) {
        const px0 = xPx(x0), px1 = xPx(x1), py0 = yPx(y0), py1 = yPx(y1);
        el("rect", {x: Math.min(px0, px1), y: Math.min(py0, py1), width: Math.abs(px1 - px0),
          height: Math.abs(py1 - py0), class: "outline"}, svg);
      }

      // The color legend: a gradient bar of the scale's own CSS stops (so it follows
      // a theme change on its own, unlike the canvas raster, which is baked pixels
      // and needs drawCanvas again) and its own ticks, from niceTicks over the domain.
      const gradId = `map-chart-${chartId}-legend`;
      const ly = CTOP + CPLOT + CAXIS_H + 8, lx = CLEFT, lw = CPLOT, lh = 10;
      const names = stopNames(scale);
      const grad = el("linearGradient", {id: gradId, x1: "0%", x2: "100%", y1: "0%", y2: "0%"},
        el("defs", {}, svg));
      names.forEach((name, k) => {
        el("stop", {offset: `${k / (names.length - 1) * 100}%`, style: `stop-color:var(${name})`},
          grad);
      });
      el("rect", {x: lx, y: ly, width: lw, height: lh, fill: `url(#${gradId})`}, svg);
      el("rect", {x: lx, y: ly, width: lw, height: lh, fill: "none", class: "base"}, svg);
      text({x: lx - 8, y: ly + lh / 2 + 4, class: "tick", "text-anchor": "end"}, valueLabel, svg);
      const [dlo, dhi] = DOMAIN;
      if (dhi > dlo) {
        for (const t of niceTicks(dlo, dhi, 4)) {
          const tx = lx + (t - dlo) / (dhi - dlo) * lw;
          el("line", {x1: tx, x2: tx, y1: ly + lh, y2: ly + lh + 4, class: "base"}, svg);
          text({x: tx, y: ly + lh + 15, class: "tick", "text-anchor": "middle"}, fmt(t), svg);
        }
      }

      cross = {
        v: el("line", {y1: CTOP, y2: CTOP + CPLOT, class: "cross", visibility: "hidden"}, svg),
        h: el("line", {x1: CLEFT, x2: CLEFT + CPLOT, class: "cross", visibility: "hidden"}, svg),
      };
      const hit = el("rect", {x: CLEFT, y: CTOP, width: CPLOT, height: CPLOT,
        fill: "transparent"}, svg);
      hit.addEventListener("pointermove", ev => {
        const r = svg.getBoundingClientRect();
        const px = (ev.clientX - r.left) * CW / r.width;
        const py = (ev.clientY - r.top) * CH / r.height;
        setCursor(X.lo + (px - CLEFT) / CPLOT * (X.hi - X.lo),
          Y.hi - (py - CTOP) / CPLOT * (Y.hi - Y.lo));
      });
      hit.addEventListener("pointerleave", () => setCursor(null, null));
      setCursor(null, null);
    }

    svg.addEventListener("keydown", ev => {
      let ix = cursorIx ?? Math.floor((X.n - 1) / 2);
      let iy = cursorIy ?? Math.floor((Y.n - 1) / 2);
      if (ev.key === "ArrowRight") ix = Math.min(X.n - 1, ix + 1);
      else if (ev.key === "ArrowLeft") ix = Math.max(0, ix - 1);
      else if (ev.key === "ArrowUp") iy = Math.min(Y.n - 1, iy + 1);
      else if (ev.key === "ArrowDown") iy = Math.max(0, iy - 1);
      else if (ev.key === "Escape") { setCursor(null, null); return; }
      else return;
      ev.preventDefault();
      setCursor(xAt(ix), yAt(iy));
    });
    svg.addEventListener("blur", () => setCursor(null, null));

    function redraw() {
      positionCanvas();
      renderAxes();
      drawCanvas();
    }
    redraw();

    // A theme change re-reads the CSS stops and rebuilds the canvas (the legend
    // gradient is plain CSS and updates itself). vb's columnChart does the same, with
    // both a media-query listener (the OS/browser theme) and a MutationObserver on
    // the root element's data-theme attribute (the page's own theme switch, if any).
    matchMedia("(prefers-color-scheme: dark)").addEventListener("change", drawCanvas);
    new MutationObserver(drawCanvas).observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-theme"],
    });

    return {
      // Replaces the axes, the values and the domain, and redraws, without making a
      // new chart: for another pulse, another view, or a slice of a larger map that
      // was computed since the last render.
      setData({x: newX, y: newY, values: newValues, domain: newDomain}) {
        X = newX;
        Y = newY;
        V = newValues;
        DOMAIN = newDomain.slice();
        imageCache = {};
        redraw();
      },
    };
  }

  PulseqReport.mapChart = mapChart;
})();
