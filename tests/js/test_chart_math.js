const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

const {fmt, niceTicks, valueAt, minMaxAt, visiblePoints, clampView, zoomView, panView,
  dragView, laneGroupMap, visibleLanes, valueDomain, rescaleLane} = require(
  path.join(__dirname, "..", "..", "src", "pulseq_reports", "assets", "chart_math.js")
);

test("test_nice_ticks_step_is_1_2_or_5_times_power_of_ten", () => {
  // step 1 * 10^0
  assert.deepEqual(niceTicks(0, 8, 8), [0, 1, 2, 3, 4, 5, 6, 7, 8]);
  // step 2 * 10^1
  assert.deepEqual(niceTicks(0, 100, 8), [0, 20, 40, 60, 80, 100]);
  // step 5 * 10^0
  assert.deepEqual(niceTicks(0, 24, 8), [0, 5, 10, 15, 20]);
});

test("test_nice_ticks_starts_at_first_multiple_at_or_above_lo", () => {
  // step is 5 here; the first multiple of 5 at or above lo=3 is 5, and ticks stop at hi=24.
  assert.deepEqual(niceTicks(3, 24, 8), [5, 10, 15, 20]);
});

test("test_value_at_interpolates_linearly_within_a_segment", () => {
  const lane = {segments: [[[0, 0], [10, 100]]], fill: null};
  assert.equal(valueAt(lane, 5), 50);
});

test("test_value_at_gate_lane_is_on_inside_window_and_off_outside", () => {
  const lane = {kind: "gate", windows: [[2, 5]]};
  assert.equal(valueAt(lane, 3), "on");
  assert.equal(valueAt(lane, 7), "off");
});

test("test_value_at_returns_lane_fill_outside_all_segments", () => {
  const nullFillLane = {segments: [[[0, 0], [10, 100]]], fill: null};
  assert.equal(valueAt(nullFillLane, 20), null);

  const numericFillLane = {segments: [[[0, 0], [10, 100]]], fill: 42};
  assert.equal(valueAt(numericFillLane, -5), 42);
});

test("test_min_max_at_reads_the_bin_that_holds_the_cursor", () => {
  // Two bins: [0, 10) has min -1, max 2; the second bin starts at t = 10.
  const lane = {segments: [[[0, -1], [5, 2], [10, -3], [15, 4]]]};
  assert.deepEqual(minMaxAt(lane, 3), {min: -1, max: 2});
  assert.deepEqual(minMaxAt(lane, 12), {min: -3, max: 4});
});

test("test_min_max_at_bin_start_belongs_to_the_later_bin", () => {
  // The first bin's own end (t = 10) is exclusive, so t = 10 falls in the
  // second bin, whose start it is.
  const lane = {segments: [[[0, -1], [5, 2], [10, -3], [15, 4]]]};
  assert.deepEqual(minMaxAt(lane, 10), {min: -3, max: 4});
});

test("test_min_max_at_last_bin_of_a_segment_is_inclusive_at_its_own_end", () => {
  // The last pair of a segment has no following pair, so its own end is
  // derived as 2 * centre - start = 2 * 15 - 10 = 20, and t = 20 (the very
  // end) is still in the bin.
  const lane = {segments: [[[0, -1], [5, 2], [10, -3], [15, 4]]]};
  assert.deepEqual(minMaxAt(lane, 20), {min: -3, max: 4});
});

test("test_min_max_at_returns_null_in_a_gap_between_segments", () => {
  // Segment 1 covers only the bin [0, 10); segment 2 covers only the bin
  // [20, 30). There is no bin for [10, 20), as for a gap between RF pulses.
  const lane = {segments: [
    [[0, -1], [5, 2]],
    [[20, -3], [25, 4]],
  ]};
  assert.deepEqual(minMaxAt(lane, 3), {min: -1, max: 2});
  assert.equal(minMaxAt(lane, 15), null);
  assert.deepEqual(minMaxAt(lane, 22), {min: -3, max: 4});
});

test("test_min_max_at_returns_null_past_the_last_bin", () => {
  const lane = {segments: [[[0, -1], [5, 2]]]};
  assert.equal(minMaxAt(lane, 11), null);
});

test("test_fmt_rounds_to_three_significant_figures", () => {
  assert.equal(fmt(1234.5), "1230");
  assert.equal(fmt(0.012345), "0.0123");
});

test("test_fmt_gives_zero_for_magnitudes_below_5e_minus_4", () => {
  assert.equal(fmt(0.0001), "0");
  assert.equal(fmt(-0.0001), "0");
});

test("test_fmt_uses_unicode_minus_sign_for_negative_numbers", () => {
  assert.equal(fmt(-12.345), "−12.3");
});

test("test_fmt_uses_em_dash_for_null_or_undefined", () => {
  assert.equal(fmt(null), "—");
  assert.equal(fmt(undefined), "—");
});

test("test_fmt_returns_strings_unchanged", () => {
  assert.equal(fmt("abc"), "abc");
});

test("test_visible_points_keeps_the_largest_and_smallest_value_in_the_view", () => {
  const n = 100000;
  const spikeUpIndex = 40000;
  const spikeDownIndex = 70000;
  const points = [];
  for (let i = 0; i < n; i++) {
    let v = Math.sin(i / 500);
    if (i === spikeUpIndex) v = 1000;
    if (i === spikeDownIndex) v = -1000;
    points.push([i, v]);
  }
  const result = visiblePoints(points, 0, n - 1, 100);
  const values = result.map(([, v]) => v);
  assert.ok(values.includes(1000), "spike up must be in the result");
  assert.ok(values.includes(-1000), "spike down must be in the result");
});

test("test_visible_points_keeps_index_order", () => {
  const n = 50000;
  const points = [];
  for (let i = 0; i < n; i++) {
    points.push([i, Math.sin(i / 137) + Math.cos(i / 29)]);
  }
  const indexOf = new Map(points.map((p, i) => [p, i]));
  const result = visiblePoints(points, 0, n - 1, 33);

  let prevIndex = -1;
  let prevX = -Infinity;
  for (const p of result) {
    const idx = indexOf.get(p);
    assert.ok(idx !== undefined, "every returned point must be one of the input points");
    assert.ok(idx > prevIndex, "returned points must be a subsequence in index order");
    assert.ok(p[0] >= prevX, "x values must be non-decreasing");
    prevIndex = idx;
    prevX = p[0];
  }
});

test("test_visible_points_returns_a_short_slice_unchanged", () => {
  const points = [];
  for (let i = 0; i < 10; i++) points.push([i, i]);
  const buckets = 3; // 4 * buckets = 12, at least as large as the slice below
  const lo = 2.5, hi = 6.5;
  // i0 = 2 (largest index with x <= 2.5), i1 = 7 (smallest index with x >= 6.5)
  const result = visiblePoints(points, lo, hi, buckets);
  assert.deepEqual(result, points.slice(2, 8));
});

test("test_visible_points_is_empty_for_a_segment_outside_the_view", () => {
  const points = [];
  for (let i = 0; i < 10; i++) points.push([i, i]);

  assert.deepEqual(visiblePoints(points, 20, 30, 10), []); // fully left of the view
  assert.deepEqual(visiblePoints(points, -30, -20, 10), []); // fully right of the view
  assert.deepEqual(visiblePoints([], 0, 1, 10), []); // empty input
});

test("test_visible_points_keeps_the_points_just_outside_the_view", () => {
  const points = [];
  for (let i = 0; i < 100; i++) points.push([i, i]);

  // view [10.5, 20.5]: no point sits exactly on the edge, so the result must
  // reach one point past each edge (x = 10 and x = 21) so the edge-to-point
  // line still draws.
  let result = visiblePoints(points, 10.5, 20.5, 10);
  assert.equal(result[0][0], 10);
  assert.equal(result[result.length - 1][0], 21);

  // view ends exactly on points: x = 10 and x = 20 start and end the result.
  result = visiblePoints(points, 10, 20, 10);
  assert.equal(result[0][0], 10);
  assert.equal(result[result.length - 1][0], 20);

  // no point inside the view: both surrounding points come back.
  const sparse = [[0, 0], [100, 1]];
  result = visiblePoints(sparse, 40, 60, 10);
  assert.deepEqual(result, sparse);
});

test("test_visible_points_has_at_most_4_buckets_plus_2_points", () => {
  const n = 120000;
  const points = [];
  for (let i = 0; i < n; i++) points.push([i, Math.sin(i / 331)]);
  const buckets = 1624;
  const result = visiblePoints(points, 0, n - 1, buckets);
  assert.ok(result.length <= 4 * buckets + 2, `got ${result.length} points`);
});

test("test_visible_points_keeps_vertical_edges", () => {
  const buckets = 50;
  const blocksPerBin = 500;
  const numBlocks = buckets * blocksPerBin;
  const points = [];
  for (let j = 0; j < numBlocks; j++) {
    const x0 = 10 * j;
    // a square pulse: low, rising edge, high, falling edge, all inside one bin
    points.push([x0, 0], [x0, 1], [x0 + 1, 1], [x0 + 1, 0]);
  }
  const lo = 0, hi = 10 * numBlocks;
  const result = visiblePoints(points, lo, hi, buckets);

  const hasZero = new Array(buckets).fill(false);
  const hasOne = new Array(buckets).fill(false);
  for (const [x, v] of result) {
    const b = Math.min(buckets - 1, Math.max(0, Math.floor((x - lo) / (hi - lo) * buckets)));
    if (v === 0) hasZero[b] = true;
    if (v === 1) hasOne[b] = true;
  }
  for (let b = 0; b < buckets; b++) {
    assert.ok(hasZero[b], `bin ${b} is missing a value-0 point`);
    assert.ok(hasOne[b], `bin ${b} is missing a value-1 point`);
  }
});

test("test_clamp_view_keeps_a_view_that_is_inside_the_extent", () => {
  assert.deepEqual(clampView([10, 20], [0, 100], 5), [10, 20]);
});

test("test_clamp_view_moves_a_view_past_an_end_inside_without_a_change_in_width", () => {
  // past the left end: shift right, width stays 20
  assert.deepEqual(clampView([-10, 10], [0, 100], 5), [0, 20]);
  // past the right end: shift left, width stays 20
  assert.deepEqual(clampView([90, 110], [0, 100], 5), [80, 100]);
});

test("test_clamp_view_gives_the_extent_for_a_view_wider_than_the_extent", () => {
  assert.deepEqual(clampView([-50, 200], [0, 100], 5), [0, 100]);
});

test("test_clamp_view_widens_a_view_narrower_than_min_span_about_its_centre", () => {
  // centred in the extent: widen about the same centre, no further move.
  assert.deepEqual(clampView([40, 42], [0, 100], 5), [38.5, 43.5]);
  // near the left end: widening about the centre first goes past 0, so the
  // widened view then also moves inside.
  assert.deepEqual(clampView([0, 1], [0, 100], 5), [0, 5]);
});

test("test_clamp_view_gives_the_extent_when_min_span_is_wider_than_the_extent", () => {
  assert.deepEqual(clampView([10, 20], [0, 100], 200), [0, 100]);
});

test("test_zoom_view_by_2_halves_the_width_about_the_anchor", () => {
  assert.deepEqual(zoomView([0, 100], 2, 30, [-1000, 1000], 1), [5, 55]);
});

test("test_zoom_view_uses_the_view_centre_without_an_anchor_in_the_view", () => {
  // no anchor
  assert.deepEqual(zoomView([0, 100], 2, null, [-1000, 1000], 1), [25, 75]);
  // anchor outside the view
  assert.deepEqual(zoomView([0, 100], 2, 200, [-1000, 1000], 1), [25, 75]);
});

test("test_zoom_view_by_0_1_near_an_end_moves_the_view_inside_the_extent", () => {
  // width 20 / 0.1 = 200 about anchor 10, giving [-90, 110], which is
  // narrower than the extent (width 1000) but must move right to fit.
  assert.deepEqual(zoomView([0, 20], 0.1, 10, [0, 1000], 1), [0, 200]);
});

test("test_zoom_view_by_10_stops_at_min_span", () => {
  // width 20 / 10 = 2, which is narrower than minSpan 5, so the result is
  // widened to minSpan about the same centre (50).
  assert.deepEqual(zoomView([40, 60], 10, 50, [0, 1000], 5), [47.5, 52.5]);
});

test("test_zoom_view_by_0_1_from_a_wide_view_gives_the_extent", () => {
  // width 200 / 0.1 = 2000, wider than the extent (width 1000).
  assert.deepEqual(zoomView([400, 600], 0.1, null, [0, 1000], 1), [0, 1000]);
});

test("test_pan_view_moves_both_ends_by_delta", () => {
  assert.deepEqual(panView([10, 20], 5, [0, 1000]), [15, 25]);
});

test("test_pan_view_stops_at_each_end_and_keeps_the_width", () => {
  // past the left end
  assert.deepEqual(panView([5, 15], -10, [0, 1000]), [0, 10]);
  // past the right end
  assert.deepEqual(panView([985, 995], 20, [0, 1000]), [990, 1000]);
});

test("test_drag_view_gives_the_same_view_in_both_directions", () => {
  assert.deepEqual(dragView(20, 50, [0, 1000], 1), [20, 50]);
  assert.deepEqual(dragView(50, 20, [0, 1000], 1), [20, 50]);
});

test("test_drag_view_is_null_for_a_zero_width_drag", () => {
  assert.equal(dragView(30, 30, [0, 1000], 1), null);
});

test("test_drag_view_widens_a_narrow_drag_to_min_span", () => {
  // drag width 2, widened about its centre (51) to minSpan 10.
  assert.deepEqual(dragView(50, 52, [0, 1000], 10), [46, 56]);
});

test("test_lane_group_map_maps_each_lane_id_to_its_group_id", () => {
  const groups = [
    {id: "rf", label: "RF", laneIds: ["rf_mag", "rf_phase"], visible: true},
    {id: "grad", label: "Gradients", laneIds: ["gx", "gy", "gz"], visible: true},
  ];
  const map = laneGroupMap(groups);
  assert.equal(map.get("rf_mag"), "rf");
  assert.equal(map.get("rf_phase"), "rf");
  assert.equal(map.get("gx"), "grad");
  assert.equal(map.get("gy"), "grad");
  assert.equal(map.get("gz"), "grad");
  assert.equal(map.size, 5);
});

test("test_visible_lanes_keeps_lanes_of_a_visible_group_and_drops_the_rest", () => {
  const groups = [
    {id: "rf", label: "RF", laneIds: ["rf_mag", "rf_phase"], visible: true},
    {id: "grad", label: "Gradients", laneIds: ["gx", "gy", "gz"], visible: false},
  ];
  const map = laneGroupMap(groups);
  const lanes = [{id: "rf_mag"}, {id: "rf_phase"}, {id: "gx"}, {id: "gy"}, {id: "gz"}];
  const result = visibleLanes(lanes, map, new Set(["rf"]));
  assert.deepEqual(result.map(l => l.id), ["rf_mag", "rf_phase"]);
});

test("test_visible_lanes_always_keeps_a_lane_that_belongs_to_no_group", () => {
  const groups = [{id: "grad", label: "Gradients", laneIds: ["gx"], visible: true}];
  const map = laneGroupMap(groups);
  const lanes = [{id: "gx"}, {id: "adc"}];
  // The "grad" group is hidden (not in visibleGroupIds), but "adc" belongs to
  // no group, so it stays.
  const result = visibleLanes(lanes, map, new Set());
  assert.deepEqual(result.map(l => l.id), ["adc"]);
});

test("test_visible_lanes_drops_a_lane_a_provider_returns_for_a_hidden_group", () => {
  // Even if a lanesFor provider ignores visibleGroupIds and returns a lane of
  // a hidden group anyway, visibleLanes still drops it (lane_chart.js's
  // safety net, docs/plans/diagram-lanes.md section 4.5 item 3).
  const groups = [{id: "pns", label: "PNS", laneIds: ["pns_total"], visible: false}];
  const map = laneGroupMap(groups);
  const result = visibleLanes([{id: "pns_total"}], map, new Set());
  assert.deepEqual(result, []);
});

test("test_view_functions_do_not_change_their_arguments", () => {
  const view = [10, 20];
  const extent = [0, 100];
  const viewCopy = [...view];
  const extentCopy = [...extent];

  const r1 = clampView(view, extent, 5);
  assert.deepEqual(view, viewCopy);
  assert.deepEqual(extent, extentCopy);
  assert.notEqual(r1, view);

  zoomView(view, 2, 15, extent, 5);
  assert.deepEqual(view, viewCopy);
  assert.deepEqual(extent, extentCopy);

  panView(view, 5, extent);
  assert.deepEqual(view, viewCopy);
  assert.deepEqual(extent, extentCopy);

  dragView(30, 10, extent, 5);
  assert.deepEqual(extent, extentCopy);
});

// colorRamp, colorIndex and nearestIndex (docs/plans/rf-profiles.md section 4.4, item 1)
// are the pure functions the map chart uses to color its raster and to snap the hover
// cursor and the arrow keys to the nearest grid point.
const {colorRamp, colorIndex, nearestIndex} = require(
  path.join(__dirname, "..", "..", "src", "pulseq_reports", "assets", "chart_math.js")
);

test("test_color_ramp_two_stops_linear_between_endpoints", () => {
  // Component values are chosen so every interior step (0.25, 0.5, 0.75) lands on a
  // whole number, so the test does not have to reason about Uint8ClampedArray rounding.
  const stops = [[0, 0, 0], [100, 200, 40]];
  const ramp = colorRamp(stops, 5);
  assert.deepEqual(Array.from(ramp), [
    0, 0, 0,
    25, 50, 10,
    50, 100, 20,
    75, 150, 30,
    100, 200, 40,
  ]);
});

test("test_color_ramp_three_stops_midpoint_is_the_middle_stop", () => {
  // With 3 stops (2 segments) and n = 5, t runs 0, 0.5, 1, 1.5, 2: index 2 (the
  // middle of the 5 colors) lands exactly on t = 1, the middle stop.
  const stops = [[0, 0, 0], [10, 20, 30], [100, 200, 40]];
  const ramp = colorRamp(stops, 5);
  assert.deepEqual(Array.from(ramp), [
    0, 0, 0,
    5, 10, 15,
    10, 20, 30,
    55, 110, 35,
    100, 200, 40,
  ]);
});

test("test_color_ramp_n_equal_1_returns_only_the_first_stop", () => {
  const stops = [[10, 20, 30], [200, 100, 0]];
  const ramp = colorRamp(stops, 1);
  assert.equal(ramp.length, 3);
  assert.deepEqual(Array.from(ramp), [10, 20, 30]);
});

test("test_color_index_maps_domain_endpoints_to_first_and_last_index", () => {
  assert.equal(colorIndex(0, [0, 10], 5), 0);
  assert.equal(colorIndex(10, [0, 10], 5), 4);
});

test("test_color_index_maps_the_domain_midpoint_to_the_middle_index", () => {
  assert.equal(colorIndex(5, [0, 10], 5), 2);
});

test("test_color_index_clamps_below_and_above_the_domain", () => {
  assert.equal(colorIndex(-100, [0, 10], 5), 0);
  assert.equal(colorIndex(1000, [0, 10], 5), 4);
});

test("test_color_index_is_minus_1_for_nan", () => {
  assert.equal(colorIndex(NaN, [0, 10], 5), -1);
});

test("test_color_index_degenerate_domain_is_always_index_0", () => {
  // lo === hi: there is no range to place a value in, so every value, even one
  // outside the single point, maps to index 0.
  assert.equal(colorIndex(5, [5, 5], 8), 0);
  assert.equal(colorIndex(100, [5, 5], 8), 0);
});

test("test_nearest_index_at_the_grid_points", () => {
  // linspace(0, 100, 6) = [0, 20, 40, 60, 80, 100].
  assert.equal(nearestIndex(0, 100, 6, 0), 0);
  assert.equal(nearestIndex(0, 100, 6, 20), 1);
  assert.equal(nearestIndex(0, 100, 6, 100), 5);
});

test("test_nearest_index_halfway_between_grid_points_rounds_up", () => {
  // 10 is exactly halfway between grid index 0 (0) and index 1 (20); Math.round
  // rounds a 0.5 fraction up (towards +Infinity), so it goes to index 1. 30 is
  // exactly halfway between index 1 (20) and index 2 (40), and rounds to index 2.
  assert.equal(nearestIndex(0, 100, 6, 10), 1);
  assert.equal(nearestIndex(0, 100, 6, 30), 2);
});

test("test_nearest_index_clamps_outside_the_range", () => {
  assert.equal(nearestIndex(0, 100, 6, -50), 0);
  assert.equal(nearestIndex(0, 100, 6, 500), 5);
});

test("test_nearest_index_degenerate_domain_or_single_point_is_index_0", () => {
  assert.equal(nearestIndex(5, 5, 4, 5), 0);
  assert.equal(nearestIndex(0, 100, 1, 50), 0);
});

// tooltipRows, normalizeBand and markSpans (docs/plans/pulseq-checks-implementation.md section
// 4.4, decision D9) are the pure parts of the series, the marks and the colored bands of
// `laneChart`.
const {tooltipRows, normalizeBand, markSpans} = require(
  path.join(__dirname, "..", "..", "src", "pulseq_reports", "assets", "chart_math.js")
);

test("test_tooltip_rows_plain_line_lane_has_one_row_with_title_color_and_unit", () => {
  const lane = {title: "Gx", color: "gx", unit: "mT/m", fill: 0,
    segments: [[[0, 0], [10, 100]]]};
  assert.deepEqual(tooltipRows(lane, 5), [{label: "Gx", color: "gx", text: "50 mT/m"}]);
  // Outside the segments the value is the fill.
  assert.deepEqual(tooltipRows(lane, 20), [{label: "Gx", color: "gx", text: "0 mT/m"}]);
});

test("test_tooltip_rows_null_fill_has_no_unit", () => {
  const lane = {title: "RF", color: "rf", unit: "uT", fill: null, segments: [[[0, 1], [10, 1]]]};
  assert.equal(tooltipRows(lane, 50)[0].text, "—");
});

test("test_tooltip_rows_minmax_lane_reads_the_bin_and_falls_back_to_fill_in_a_gap", () => {
  const lane = {title: "G", color: "g", unit: "mT/m", minmax: true, fill: 0,
    segments: [[[0, -1], [5, 2]], [[20, -3], [25, 4]]]};
  assert.deepEqual(tooltipRows(lane, 3),
    [{label: "G", color: "g", text: "−1 – 2 mT/m"}]);
  assert.deepEqual(tooltipRows(lane, 22),
    [{label: "G", color: "g", text: "−3 – 4 mT/m"}]);
  // t = 15 is in the gap between the two bins.
  assert.deepEqual(tooltipRows(lane, 15), [{label: "G", color: "g", text: "0 mT/m"}]);
});

test("test_tooltip_rows_minmax_lane_without_unit_has_no_unit_text", () => {
  const lane = {title: "G", color: "g", minmax: true, fill: null,
    segments: [[[0, -1], [5, 2]]]};
  assert.equal(tooltipRows(lane, 3)[0].text, "−1 – 2");
  assert.equal(tooltipRows(lane, 50)[0].text, "—");
});

test("test_tooltip_rows_gate_lane_is_on_or_off_even_with_minmax", () => {
  const lane = {kind: "gate", title: "ADC", color: "adc", unit: "x", minmax: true,
    windows: [[2, 5]]};
  assert.deepEqual(tooltipRows(lane, 3), [{label: "ADC", color: "adc", text: "on"}]);
  assert.deepEqual(tooltipRows(lane, 7), [{label: "ADC", color: "adc", text: "off"}]);
});

test("test_tooltip_rows_series_has_one_row_per_series_read_from_its_own_segments", () => {
  const lane = {title: "Lane", color: "lane", unit: "%", fill: 0,
    series: [
      {label: "Target 1", color: "target-1", segments: [[[0, 0], [10, 100]]]},
      {label: "Target 2", color: "target-2", segments: [[[0, 10], [10, 20]], [[20, 5], [30, 7]]]},
    ]};
  assert.deepEqual(tooltipRows(lane, 5), [
    {label: "Target 1", color: "target-1", text: "50 %"},
    {label: "Target 2", color: "target-2", text: "15 %"},
  ]);
  // Past the first series' segments: its row is the fill, the other series still has a value.
  assert.deepEqual(tooltipRows(lane, 25), [
    {label: "Target 1", color: "target-1", text: "0 %"},
    {label: "Target 2", color: "target-2", text: "6 %"},
  ]);
  // In the gap of the second series, and past the first: both are the fill.
  assert.deepEqual(tooltipRows(lane, 15), [
    {label: "Target 1", color: "target-1", text: "0 %"},
    {label: "Target 2", color: "target-2", text: "0 %"},
  ]);
});

test("test_tooltip_rows_series_of_a_minmax_lane_read_the_bin_of_each_series", () => {
  const lane = {title: "Lane", color: "lane", unit: "mT/m", minmax: true, fill: 0,
    series: [
      {label: "A", color: "target-1", segments: [[[0, -1], [5, 2]]]},
      {label: "B", color: "target-2", segments: [[[0, -4], [5, 6]]]},
    ]};
  assert.deepEqual(tooltipRows(lane, 3), [
    {label: "A", color: "target-1", text: "−1 – 2 mT/m"},
    {label: "B", color: "target-2", text: "−4 – 6 mT/m"},
  ]);
  assert.deepEqual(tooltipRows(lane, 50), [
    {label: "A", color: "target-1", text: "0 mT/m"},
    {label: "B", color: "target-2", text: "0 mT/m"},
  ]);
});

test("test_tooltip_rows_empty_series_array_has_no_rows", () => {
  const lane = {title: "Lane", color: "lane", fill: 0, segments: [[[0, 0], [10, 100]]],
    series: []};
  assert.deepEqual(tooltipRows(lane, 5), []);
});

test("test_normalize_band_pair_has_no_color_and_object_keeps_its_color", () => {
  assert.deepEqual(normalizeBand([1, 2]), {lo: 1, hi: 2, color: null});
  assert.deepEqual(normalizeBand({lo: 3, hi: 4, color: "target-2"}),
    {lo: 3, hi: 4, color: "target-2"});
  assert.deepEqual(normalizeBand({lo: 3, hi: 4}), {lo: 3, hi: 4, color: null});
});

test("test_mark_spans_maps_to_plot_coordinates", () => {
  // View [100, 200] over a plot of width 1000: 10 plot units for each chart unit.
  const spans = markSpans([{lo: 120, hi: 150, color: "a"}], 100, 200, 1000, 1);
  assert.deepEqual(spans, [{x0: 200, x1: 500, color: "a"}]);
});

test("test_mark_spans_drops_marks_fully_outside_the_view", () => {
  const marks = [
    {lo: 0, hi: 50, color: "a"},
    {lo: 250, hi: 300, color: "a"},
    {lo: 120, hi: 130, color: "a"},
  ];
  assert.deepEqual(markSpans(marks, 100, 200, 1000, 1), [{x0: 200, x1: 300, color: "a"}]);
});

test("test_mark_spans_cuts_a_mark_partly_in_view_at_the_edge", () => {
  const marks = [{lo: 50, hi: 120, color: "a"}, {lo: 180, hi: 400, color: "b"}];
  assert.deepEqual(markSpans(marks, 100, 200, 1000, 1), [
    {x0: 0, x1: 200, color: "a"},
    {x0: 800, x1: 1000, color: "b"},
  ]);
});

test("test_mark_spans_widens_a_narrow_mark_about_its_centre", () => {
  // A mark of 0.01 chart units is 0.1 plot units wide; it becomes 2 wide about 500.05.
  const [span] = markSpans([{lo: 150, hi: 150.01, color: "a"}], 100, 200, 1000, 2);
  assert.ok(Math.abs(span.x0 - 499.05) < 1e-9);
  assert.ok(Math.abs(span.x1 - 501.05) < 1e-9);
  // A mark at least minWidth wide is not changed.
  const [wide] = markSpans([{lo: 150, hi: 150.2, color: "a"}], 100, 200, 1000, 2);
  assert.ok(Math.abs(wide.x0 - 500) < 1e-9);
  assert.ok(Math.abs(wide.x1 - 502) < 1e-9);
});

test("test_mark_spans_widened_mark_at_the_edge_is_cut_at_the_edge", () => {
  assert.deepEqual(markSpans([{lo: 100, hi: 100, color: "a"}], 100, 200, 1000, 2),
    [{x0: 0, x1: 1, color: "a"}]);
  assert.deepEqual(markSpans([{lo: 200, hi: 200, color: "a"}], 100, 200, 1000, 2),
    [{x0: 999, x1: 1000, color: "a"}]);
});

test("test_mark_spans_merges_overlapping_and_touching_marks_of_the_same_color", () => {
  const marks = [
    {lo: 110, hi: 120, color: "a"},
    {lo: 115, hi: 130, color: "a"},
    {lo: 130, hi: 135, color: "a"},
    {lo: 150, hi: 160, color: "a"},
    // Inside the first mark: no change to the merged span.
    {lo: 112, hi: 113, color: "a"},
  ];
  assert.deepEqual(markSpans(marks, 100, 200, 1000, 1), [
    {x0: 100, x1: 350, color: "a"},
    {x0: 500, x1: 600, color: "a"},
  ]);
});

test("test_mark_spans_merges_marks_that_overlap_only_after_widening", () => {
  // Two marks 0.5 plot units apart, each widened to 2: they overlap and merge.
  const marks = [{lo: 150, hi: 150, color: "a"}, {lo: 150.05, hi: 150.05, color: "a"}];
  const spans = markSpans(marks, 100, 200, 1000, 2);
  assert.equal(spans.length, 1);
  assert.ok(Math.abs(spans[0].x0 - 499) < 1e-9);
  assert.ok(Math.abs(spans[0].x1 - 501.5) < 1e-9);
});

test("test_mark_spans_does_not_merge_marks_of_different_colors", () => {
  const marks = [
    {lo: 110, hi: 130, color: "a"},
    {lo: 120, hi: 140, color: "b"},
    {lo: 125, hi: 135, color: "a"},
  ];
  assert.deepEqual(markSpans(marks, 100, 200, 1000, 1), [
    {x0: 100, x1: 350, color: "a"},
    {x0: 200, x1: 400, color: "b"},
  ]);
});

test("test_mark_spans_does_not_need_sorted_input", () => {
  const sorted = [
    {lo: 110, hi: 120, color: "a"}, {lo: 115, hi: 130, color: "a"},
    {lo: 150, hi: 160, color: "a"}, {lo: 170, hi: 180, color: "a"},
  ];
  const shuffled = [sorted[3], sorted[1], sorted[2], sorted[0]];
  assert.deepEqual(markSpans(shuffled, 100, 200, 1000, 1), markSpans(sorted, 100, 200, 1000, 1));
  assert.deepEqual(markSpans(shuffled, 100, 200, 1000, 1), [
    {x0: 100, x1: 300, color: "a"},
    {x0: 500, x1: 600, color: "a"},
    {x0: 700, x1: 800, color: "a"},
  ]);
});

test("test_mark_spans_empty_input_gives_no_spans", () => {
  assert.deepEqual(markSpans([], 100, 200, 1000, 1), []);
});

// ---- The value lanes of the diagram: valueDomain and rescaleLane ----

const GAMMA_1H = 42576000; // Hz/T, the proton

test("test_value_domain_is_the_rule_of_the_python_value_lane", () => {
  // Each row is the result of `waveforms._value_domain(peak, symmetric)` of the version that
  // calculated the domain in Python (the 3 significant digits of `f"{v:.3g}"`: a tie goes to
  // the even digit, an exponent appears below 1e-4 and from 1e3, and a hyphen is U+2212).
  const minus = "\u2212";
  const rows = [
    [0, true, [-1, 1], [0], ["0"]],
    [0, false, [-1, 1], [0], ["0"]],
    [25, true, [-27.500000000000004, 27.500000000000004], [-25, 0, 25], [minus + "25", "0", "25"]],
    [25, false, [0, 27.500000000000004], [0, 25], ["0", "25"]],
    [12.25, true, [-13.475000000000001, 13.475000000000001], [-12.25, 0, 12.25],
      [minus + "12.2", "0", "12.2"]],
    [22.25, false, [0, 24.475], [0, 22.25], ["0", "22.2"]],
    [0.03125, true, [-0.034375, 0.034375], [-0.03125, 0, 0.03125],
      [minus + "0.0312", "0", "0.0312"]],
    [1234.5, true, [-1357.95, 1357.95], [-1234.5, 0, 1234.5],
      [minus + "1.23e+03", "0", "1.23e+03"]],
    [99.99999, false, [0, 109.999989], [0, 99.99999], ["0", "100"]],
    [7, false, [0, 7.700000000000001], [0, 7], ["0", "7"]],
    [1.125, false, [0, 1.2375], [0, 1.125], ["0", "1.12"]],
    [0.0001, false, [0, 0.00011000000000000002], [0, 0.0001], ["0", "0.0001"]],
    [1.234e-5, true, [-1.3574e-5, 1.3574e-5], [-1.234e-5, 0, 1.234e-5],
      [minus + "1.23e" + minus + "05", "0", "1.23e" + minus + "05"]],
    [999.5, false, [0, 1099.45], [0, 999.5], ["0", "1e+03"]],
    [0.1235, false, [0, 0.13585], [0, 0.1235], ["0", "0.123"]],
    [5.2, true, [-5.720000000000001, 5.720000000000001], [-5.2, 0, 5.2],
      [minus + "5.2", "0", "5.2"]],
  ];
  for (const [peak, symmetric, domain, ticks, labels] of rows) {
    assert.deepEqual(
      valueDomain(peak, symmetric), {domain, ticks, tick_labels: labels}, `${peak} ${symmetric}`
    );
  }
});

// A gradient lane in Hz/m (the unit of the chart is mT/m), as `SeqLanes` gives it.
function gradLane(overrides = {}) {
  return {
    id: "gx", title: "Gx", unit: "mT/m", color: "gx", kind: "line", peak: 1064400,
    symmetric: true, empty: false, fill: 0,
    segments: [[[0, 0], [1, 1064400], [2, -532200], [3, 0]]], ...overrides,
  };
}

test("test_rescale_lane_gives_the_values_and_the_axis_of_the_gamma", () => {
  const lane = rescaleLane(gradLane(), GAMMA_1H);
  assert.deepEqual(lane.segments, [[
    [0, 0 / GAMMA_1H * 1e3], [1, 1064400 / GAMMA_1H * 1e3], [2, -532200 / GAMMA_1H * 1e3],
    [3, 0 / GAMMA_1H * 1e3],
  ]]);
  // 1064400 Hz/m is 25 mT/m for the proton gamma.
  assert.ok(Math.abs(lane.segments[0][1][1] - 25) < 1e-12);
  assert.deepEqual(
    {domain: lane.domain, ticks: lane.ticks, tick_labels: lane.tick_labels},
    valueDomain(25, true)
  );
  // A gamma of half the size doubles the values and the axis.
  const half = rescaleLane(gradLane(), GAMMA_1H / 2);
  assert.ok(Math.abs(half.segments[0][1][1] - 50) < 1e-12);
  assert.deepEqual(half.ticks, valueDomain(50, true).ticks);
  // The lane that was given is not changed.
  assert.equal(gradLane().segments[0][1][1], 1064400);
});

test("test_rescale_lane_with_a_negative_gamma_changes_the_sign_of_a_signed_lane_only", () => {
  const positive = rescaleLane(gradLane(), GAMMA_1H);
  const negative = rescaleLane(gradLane(), -GAMMA_1H);
  // (`+ 0` turns the -0 of a zero value into 0.)
  assert.deepEqual(
    negative.segments[0].map(p => p[1] + 0), positive.segments[0].map(p => -p[1] + 0)
  );
  // The peak is a magnitude: the axis, the ticks and the labels are those of |gamma|.
  assert.deepEqual(negative.domain, positive.domain);
  assert.deepEqual(negative.ticks, positive.ticks);
  assert.deepEqual(negative.tick_labels, positive.tick_labels);

  // The RF magnitude (a magnitude, in Hz) and a magnitude of the gradient (|G|, no peak: the
  // axis is the lane's own) use |gamma|.
  const rf = {
    id: "rf_mag", unit: "\u00b5T", peak: 333.5, symmetric: false, segments: [[[0, 0], [1, 333.5]]],
  };
  assert.deepEqual(rescaleLane(rf, -GAMMA_1H), rescaleLane(rf, GAMMA_1H));
  assert.ok(Math.abs(rescaleLane(rf, GAMMA_1H).segments[0][1][1] - 333.5 / GAMMA_1H * 1e6) < 1e-15);
  const magnitude = {
    id: "gmag", unit: "mT/m", symmetric: false, domain: [0, 3], ticks: [0, 2], tick_labels: ["0", "2"],
    segments: [[[0, 0], [1, 85152]]],
  };
  const same = rescaleLane(magnitude, -GAMMA_1H);
  assert.deepEqual(same, rescaleLane(magnitude, GAMMA_1H));
  assert.deepEqual(same.domain, [0, 3]);
  assert.ok(same.segments[0][1][1] > 0);
});

test("test_rescale_lane_keeps_the_minimum_before_the_maximum_of_a_minmax_lane", () => {
  // The pairs are (bin start, minimum) and (bin centre, maximum). A negative gamma turns the
  // minimum into the maximum, so the pair is sorted again (the tooltip reads min then max).
  const lane = gradLane({
    minmax: true, segments: [[[0, -1000], [0.5, 3000], [1, 0], [1.5, 2000]]],
  });
  const negative = rescaleLane(lane, -GAMMA_1H).segments[0];
  const positive = rescaleLane(lane, GAMMA_1H).segments[0];
  assert.deepEqual(negative.map(p => p[0]), [0, 0.5, 1, 1.5]);
  assert.equal(negative[0][1], -positive[1][1]);
  assert.equal(negative[1][1], -positive[0][1]);
  assert.equal(negative[2][1], -positive[3][1]);
  assert.equal(negative[3][1] + 0, -positive[2][1] + 0);
  for (const i of [0, 2]) assert.ok(negative[i][1] <= negative[i + 1][1]);
});

test("test_rescale_lane_returns_a_lane_without_symmetric_as_it_is", () => {
  const phase = {id: "rf_phase", unit: "rad", domain: [-1, 1], segments: [[[0, 1]]]};
  const gate = {id: "adc", kind: "gate", windows: [[0, 1]]};
  assert.equal(rescaleLane(phase, GAMMA_1H), phase);
  assert.equal(rescaleLane(gate, -GAMMA_1H), gate);
});

test("test_rescale_lane_refuses_a_gamma_that_is_0_or_not_finite_and_an_unknown_unit", () => {
  for (const gamma of [0, NaN, Infinity, undefined]) {
    assert.throws(() => rescaleLane(gradLane(), gamma), /gamma/, `gamma ${gamma}`);
  }
  assert.throws(() => rescaleLane(gradLane({unit: "T/m"}), GAMMA_1H), /unit/);
});

test("test_rescale_lane_rounds_the_peak_to_4_decimals_with_the_tie_to_the_even_digit", () => {
  // 1 Hz/m with a gamma of 32000 Hz/T is exactly 0.03125 mT/m. Python's round(0.03125, 4) is
  // 0.0312 (an exact tie goes to the even digit), where toFixed(4) gives 0.0313.
  const lane = rescaleLane(gradLane({peak: 1, segments: [[[0, 1]]]}), 32000);
  assert.equal(lane.segments[0][0][1], 0.03125);
  assert.deepEqual(lane.ticks, [-0.0312, 0, 0.0312]);
  assert.deepEqual(lane.domain, valueDomain(0.0312, true).domain);
});
