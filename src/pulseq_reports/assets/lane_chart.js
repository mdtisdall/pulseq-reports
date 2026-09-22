// The lane chart of the report cards and the card registry, in one global object,
// PulseqReport. Loaded after chart_math.js and before the card scripts and page.js.
const PulseqReport = (() => {
  const NS = "http://www.w3.org/2000/svg";
  const W = 960, LEFT = 128, RIGHT = 20, TOP = 10, LANE_H = 64, LANE_GAP = 18, AXIS_H = 38;
  const PLOT_W = W - LEFT - RIGHT;

  const el = (name, attrs, parent) => {
    const node = document.createElementNS(NS, name);
    for (const k in attrs) node.setAttribute(k, attrs[k]);
    parent.appendChild(node);
    return node;
  };
  const text = (attrs, content, parent) => { el("text", attrs, parent).textContent = content; };
  const {fmt, niceTicks, valueAt, minMaxAt, visiblePoints, zoomView, panView, dragView} = ChartMath;
  // A line segment draws at most 4 * BUCKETS + 2 of its points in the view (see visiblePoints).
  const BUCKETS = 2 * PLOT_W;
  // A drag shorter than this, in CSS px, is a click and does not zoom.
  const DRAG_PX = 4;

  // One lane chart: the grid, the x axis, the lanes, the crosshair and tooltip,
  // arrow-key/Escape navigation, and x-axis zoom and pan. `svg`, `chart` and `tip` are
  // existing DOM elements; `svg` needs a unique id (used to make its clip path id unique
  // on a page with several charts, and to find its `[data-zoom-for]` button group, if
  // any). `bands` is a list of [lo, hi] x ranges, shaded with `bandStyle`.
  // `xDomain` is the initial view, `extent` the widest view (default `xDomain`) and
  // `minSpan` the narrowest view width. `onViewChange(view, isInitial)` is called when a
  // zoom, pan or reset changes the view; `isInitial` is true for a reset to `xDomain`.
  // Zoom: drag in the plot, the zoom buttons, or the + = - keys; 0 resets. Pan: Shift+drag
  // or horizontal scroll.
  // `lanesFor(view, bins)`, when given, is called at the start of each render, with the
  // current view and `bins = PLOT_W`, and its result is drawn instead of `lanes`; it must
  // always return the same number of lanes. `lanes` is then only the initial lanes, shown
  // by the first render before a view change. Without `lanesFor`, `lanes` is drawn as
  // given to `laneChart` or to `setLanes`/`setWindow`, as before.
  // Returns {setView, setLanes, setWindow}: setView changes the view without calling
  // onViewChange. setWindow replaces the lanes, `xDomain` and `extent` together, and keeps
  // `lanesFor` if one was given.
  function laneChart({svg, chart, tip, lanes, lanesFor, xDomain, extent = xDomain,
                      minSpan: minSpanOption, onViewChange = () => {},
                      xLabel, cursorText, bands = [],
                      bandStyle = "fill:var(--ink);fill-opacity:0.05"}) {
    // `minSpan` when it is given, else a millionth of the extent.
    const spanOf = ext => minSpanOption ?? (ext[1] - ext[0]) / 1e6;
    let minSpan = spanOf(extent);
    // The SVG height depends on the number of lanes. setWindow changes it.
    let H, PLOT_BOTTOM;
    function setHeight() {
      H = TOP + lanes.length * (LANE_H + LANE_GAP) - LANE_GAP + AXIS_H;
      PLOT_BOTTOM = H - AXIS_H;
      svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
    }
    setHeight();
    const clipId = `${svg.id}-clip`;
    svg.setAttribute("data-zoomable", "");

    let view = xDomain.slice();
    let cursor = null;
    let cross = null;
    // The x value of the zoom marker, set by a click in the plot or the arrow keys, or null.
    // The zoom buttons and keys centre on it.
    let anchor = null;
    // The dashed line that shows the zoom marker.
    let anchorLine = null;
    // The selection rectangle of a zoom drag.
    let select = null;
    // The active zoom drag {pointerId, startT, startClientX, moved}, or null.
    let drag = null;
    // The active pan {pointerId, startClientX, startView}, or null.
    let pan = null;
    // The id of a pending requestAnimationFrame render, or null.
    let frame = null;

    const x = t => LEFT + (t - view[0]) / (view[1] - view[0]) * PLOT_W;

    function render() {
      if (lanesFor) lanes = lanesFor(view, PLOT_W);
      if (frame !== null) {
        cancelAnimationFrame(frame);
        frame = null;
      }
      svg.replaceChildren();
      const clip = el("clipPath", {id: clipId}, el("defs", {}, svg));
      el("rect", {x: LEFT, y: 0, width: PLOT_W, height: H}, clip);

      for (const t of niceTicks(view[0], view[1], 8)) {
        el("line", {x1: x(t), x2: x(t), y1: TOP, y2: PLOT_BOTTOM, class: "grid"}, svg);
        text({x: x(t), y: PLOT_BOTTOM + 16, class: "tick", "text-anchor": "middle"}, String(t), svg);
      }
      text({x: LEFT + PLOT_W / 2, y: H - 4, class: "lbl", "text-anchor": "middle"}, xLabel, svg);

      const bg = el("g", {"clip-path": `url(#${clipId})`}, svg);
      for (const [lo, hi] of bands) {
        const x0 = x(lo), x1 = x(hi);
        el("rect", {x: Math.min(x0, x1), y: TOP, width: Math.abs(x1 - x0),
          height: PLOT_BOTTOM - TOP, style: bandStyle}, bg);
      }

      lanes.forEach((lane, i) => {
        const top = TOP + i * (LANE_H + LANE_GAP);
        const [lo, hi] = lane.domain;
        const y = v => top + LANE_H - (v - lo) / (hi - lo) * LANE_H;
        text({x: 0, y: top + LANE_H / 2 - 2, class: "lbl"}, lane.title, svg);
        if (lane.unit) text({x: 0, y: top + LANE_H / 2 + 14, class: "tick"}, lane.unit, svg);
        lane.ticks.forEach((v, k) => {
          el("line", {x1: LEFT, x2: LEFT + PLOT_W, y1: y(v), y2: y(v),
            class: v === 0 ? "base" : "grid"}, svg);
          text({x: LEFT - 8, y: y(v) + 4, class: "tick", "text-anchor": "end"},
            lane.tick_labels[k], svg);
        });
        const g = el("g", {"clip-path": `url(#${clipId})`}, svg);
        const stroke = `stroke:var(--${lane.color})`;
        if (lane.kind === "gate") {
          for (const [a, b] of lane.windows) {
            el("rect", {x: x(a), y: y(1), width: Math.max(x(b) - x(a), 0), height: y(0) - y(1),
              style: `fill:var(--${lane.color});fill-opacity:0.1`}, g);
            el("path", {d: `M${x(a)},${y(0)}V${y(1)}H${x(b)}V${y(0)}`, class: "trace",
              style: stroke}, g);
          }
        } else {
          for (const segment of lane.segments) {
            const seg = visiblePoints(segment, view[0], view[1], BUCKETS);
            if (seg.length < 2) continue;
            const d = "M" + seg.map(([t, v]) => `${x(t).toFixed(2)},${y(v).toFixed(2)}`).join("L");
            el("path", {d, class: "trace", style: stroke}, g);
          }
        }
        if (lane.empty) {
          text({x: LEFT + PLOT_W / 2, y: top + LANE_H / 2 - 8, class: "tick",
            "text-anchor": "middle"}, "no events", svg);
        }
      });

      // A transparent hit area over the plot. The pointer listeners are on `svg`, which
      // render does not replace, so a pointer capture lasts through a render.
      el("rect", {x: LEFT, y: TOP, width: PLOT_W, height: PLOT_BOTTOM - TOP,
        fill: "transparent"}, svg);
      select = el("rect", {x: LEFT, y: TOP, width: 0, height: PLOT_BOTTOM - TOP, class: "select",
        visibility: "hidden"}, svg);
      anchorLine = el("line", {y1: TOP, y2: PLOT_BOTTOM, class: "anchor", visibility: "hidden"},
        svg);
      cross = el("line", {y1: TOP, y2: PLOT_BOTTOM, class: "cross", visibility: "hidden"}, svg);
      drawAnchor();
      setCursor(cursor);
    }

    // Shows the zoom marker when it is in the view.
    function drawAnchor() {
      if (anchor === null || anchor < view[0] || anchor > view[1]) {
        anchorLine.setAttribute("visibility", "hidden");
        return;
      }
      anchorLine.setAttribute("x1", x(anchor));
      anchorLine.setAttribute("x2", x(anchor));
      anchorLine.setAttribute("visibility", "visible");
    }

    function setAnchor(t) {
      anchor = t;
      drawAnchor();
    }

    function scheduleRender() {
      if (frame === null) {
        frame = requestAnimationFrame(() => {
          frame = null;
          render();
        });
      }
    }

    // Formats a lane's value for the tooltip, as before.
    const valueText = (lane, v) => lane.unit && typeof v !== "string" && v !== null
      ? `${fmt(v)} ${lane.unit}` : fmt(v);

    // Formats the minimum and the maximum of a minmax lane's bin at t for the tooltip, for
    // example "−12.3 – 4.56 mT/m". Falls back to the lane's fill value, formatted
    // as valueText does, when t is in a gap between bins (see ChartMath.minMaxAt).
    const minMaxText = (lane, t) => {
      const mm = minMaxAt(lane, t);
      if (mm === null) return valueText(lane, lane.fill);
      const range = `${fmt(mm.min)} – ${fmt(mm.max)}`;
      return lane.unit ? `${range} ${lane.unit}` : range;
    };

    function setCursor(t) {
      cursor = t === null ? null : Math.min(view[1], Math.max(view[0], t));
      if (cursor === null) {
        cross.setAttribute("visibility", "hidden");
        tip.hidden = true;
        return;
      }
      const cx = x(cursor);
      cross.setAttribute("x1", cx);
      cross.setAttribute("x2", cx);
      cross.setAttribute("visibility", "visible");

      tip.replaceChildren();
      const head = document.createElement("div");
      head.className = "t";
      head.textContent = cursorText(cursor);
      tip.appendChild(head);
      for (const lane of lanes) {
        const row = document.createElement("div");
        row.className = "row";
        const name = document.createElement("span");
        const key = document.createElement("span");
        key.className = "key";
        key.style.background = `var(--${lane.color})`;
        name.append(key, lane.title);
        const value = document.createElement("span");
        value.textContent = lane.kind !== "gate" && lane.minmax
          ? minMaxText(lane, cursor) : valueText(lane, valueAt(lane, cursor));
        row.append(name, value);
        tip.appendChild(row);
      }
      tip.hidden = false;
      const r = svg.getBoundingClientRect(), wrap = chart.getBoundingClientRect();
      const left = cx * r.width / W + (r.left - wrap.left);
      const width = tip.offsetWidth;
      tip.style.left = `${left + 12 + width > wrap.width ? left - 12 - width : left + 12}px`;
    }

    // The pointer position in viewBox units.
    function viewBoxPoint(ev) {
      const r = svg.getBoundingClientRect();
      return [(ev.clientX - r.left) * W / r.width, (ev.clientY - r.top) * H / r.height];
    }
    const inPlot = (px, py) => px >= LEFT && px <= LEFT + PLOT_W && py >= TOP && py <= PLOT_BOTTOM;
    const clampPx = px => Math.min(LEFT + PLOT_W, Math.max(LEFT, px));
    const valueAtPx = px => view[0] + (clampPx(px) - LEFT) / PLOT_W * (view[1] - view[0]);
    // The plot width in CSS px.
    const plotCssWidth = () => svg.getBoundingClientRect().width * PLOT_W / W;
    const sameView = (a, b) => a[0] === b[0] && a[1] === b[1];

    // Ends a zoom drag or a pan without changing the view.
    function stopGesture() {
      const gesture = drag || pan;
      if (!gesture) return;
      drag = pan = null;
      svg.classList.remove("panning");
      select.setAttribute("visibility", "hidden");
      if (svg.hasPointerCapture(gesture.pointerId)) svg.releasePointerCapture(gesture.pointerId);
    }

    // Ends a pan and keeps the view it reached.
    function finishPan() {
      const startView = pan.startView;
      stopGesture();
      if (frame !== null) render();
      if (!sameView(view, startView)) onViewChange(view, false);
    }

    function zoomBy(factor) {
      if (pan) stopGesture();
      view = zoomView(view, factor, anchor, extent, minSpan);
      render();
      onViewChange(view, false);
    }

    function resetView() {
      if (pan) stopGesture();
      view = xDomain.slice();
      anchor = null;
      render();
      onViewChange(view, true);
    }

    svg.addEventListener("pointerdown", ev => {
      if (ev.button !== 0 || drag || pan) return;
      const [px, py] = viewBoxPoint(ev);
      if (!inPlot(px, py)) return;
      if (ev.shiftKey) {
        pan = {pointerId: ev.pointerId, startClientX: ev.clientX, startView: view.slice()};
        setCursor(null);
        svg.classList.add("panning");
      } else {
        drag = {pointerId: ev.pointerId, startT: valueAtPx(px), startClientX: ev.clientX,
          moved: false};
      }
      svg.setPointerCapture(ev.pointerId);
    });

    svg.addEventListener("pointermove", ev => {
      if (pan) {
        if (ev.pointerId !== pan.pointerId) return;
        const [lo, hi] = pan.startView;
        const delta = -(ev.clientX - pan.startClientX) * (hi - lo) / plotCssWidth();
        view = panView(pan.startView, delta, extent);
        scheduleRender();
        return;
      }
      const [px, py] = viewBoxPoint(ev);
      if (drag && ev.pointerId === drag.pointerId) {
        if (Math.abs(ev.clientX - drag.startClientX) >= DRAG_PX) drag.moved = true;
        if (drag.moved) {
          const a = clampPx(x(drag.startT)), b = clampPx(px);
          select.setAttribute("x", Math.min(a, b));
          select.setAttribute("width", Math.abs(b - a));
          select.setAttribute("visibility", "visible");
        }
        setCursor(valueAtPx(px));
        return;
      }
      setCursor(inPlot(px, py) ? valueAtPx(px) : null);
    });

    svg.addEventListener("pointerup", ev => {
      if (pan && ev.pointerId === pan.pointerId) {
        finishPan();
      } else if (drag && ev.pointerId === drag.pointerId) {
        const {startT, startClientX, moved} = drag;
        stopGesture();
        // A click puts the zoom marker there.
        if (!moved) {
          setAnchor(valueAtPx(viewBoxPoint(ev)[0]));
          return;
        }
        // A drag that ends back within DRAG_PX of its start does not zoom.
        if (Math.abs(ev.clientX - startClientX) < DRAG_PX) return;
        const newView = dragView(startT, valueAtPx(viewBoxPoint(ev)[0]), extent, minSpan);
        if (newView === null) return;
        view = newView;
        anchor = null;
        render();
        onViewChange(view, false);
      }
    });

    // A cancelled pointer (for example a touch that becomes a page scroll) ends a pan
    // where it is and cancels a zoom drag.
    const cancelPointer = ev => {
      if (pan && ev.pointerId === pan.pointerId) finishPan();
      else if (drag && ev.pointerId === drag.pointerId) stopGesture();
    };
    svg.addEventListener("pointercancel", cancelPointer);
    svg.addEventListener("lostpointercapture", cancelPointer);

    svg.addEventListener("pointerleave", () => {
      if (!drag && !pan) setCursor(null);
    });

    // Horizontal scroll pans; vertical scroll is left to the page.
    svg.addEventListener("wheel", ev => {
      if (Math.abs(ev.deltaX) <= Math.abs(ev.deltaY)) return;
      ev.preventDefault();
      if (pan) return;
      const plotPx = plotCssWidth();
      const dx = ev.deltaX * (ev.deltaMode === 1 ? 16 : ev.deltaMode === 2 ? plotPx : 1);
      const newView = panView(view, dx * (view[1] - view[0]) / plotPx, extent);
      if (sameView(newView, view)) return;
      view = newView;
      scheduleRender();
      onViewChange(view, false);
    }, {passive: false});

    const zoomGroup = document.querySelector(`[data-zoom-for="${svg.id}"]`);
    if (zoomGroup) {
      for (const button of zoomGroup.querySelectorAll("[data-zoom]")) {
        button.addEventListener("click", () => {
          if (button.dataset.zoom === "reset") resetView();
          else zoomBy(Number(button.dataset.zoom));
        });
      }
    }

    svg.addEventListener("keydown", ev => {
      const step = (view[1] - view[0]) / 100;
      const modified = ev.ctrlKey || ev.metaKey || ev.altKey;
      if (ev.key === "ArrowRight" || ev.key === "ArrowLeft") {
        // The arrow keys move the zoom marker, and the crosshair with it.
        const start = anchor ?? cursor ?? (view[0] + view[1]) / 2;
        setCursor(start + (ev.key === "ArrowRight" ? step : -step));
        setAnchor(cursor);
        ev.preventDefault();
      } else if (!modified && (ev.key === "+" || ev.key === "=")) {
        zoomBy(2);
        ev.preventDefault();
      } else if (!modified && ev.key === "-") {
        zoomBy(0.5);
        ev.preventDefault();
      } else if (!modified && ev.key === "0") {
        resetView();
        ev.preventDefault();
      } else if (ev.key === "Escape") {
        if (pan) {
          // Cancel the pan: go back to the view it started from.
          const startView = pan.startView;
          stopGesture();
          view = startView;
          render();
        } else if (drag) {
          stopGesture();
        } else {
          setCursor(null);
          setAnchor(null);
        }
      }
    });
    svg.addEventListener("blur", () => setCursor(null));

    render();

    return {
      setView(newView) {
        stopGesture();
        view = newView;
        cursor = null;
        anchor = null;
        render();
      },
      // Replace the lanes with the same number of lanes, for example on another scale.
      setLanes(newLanes) {
        lanes = newLanes;
        render();
      },
      // Replace the lanes (any number), the initial view and the widest view, for example
      // to show another time window of the data. The view goes to the new `xDomain`.
      setWindow({lanes: newLanes, xDomain: newDomain, extent: newExtent = newDomain}) {
        stopGesture();
        lanes = newLanes;
        xDomain = newDomain.slice();
        extent = newExtent.slice();
        minSpan = spanOf(extent);
        view = xDomain.slice();
        cursor = null;
        anchor = null;
        setHeight();
        render();
      },
    };
  }

  // The init function of each card script, by name. page.js calls
  // init(section, data) for each <section data-card-script="name">.
  const cards = new Map();

  function registerCard(name, init) {
    if (cards.has(name)) throw new Error(`card script "${name}" is already registered`);
    cards.set(name, init);
  }

  return {laneChart, registerCard, cards, el, text};
})();
