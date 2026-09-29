const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

const {fmt, niceTicks, valueAt, minMaxAt, visiblePoints, clampView, zoomView, panView,
  dragView, laneGroupMap, visibleLanes} = require(
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
