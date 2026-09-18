# Tests

This file describes each check that CI runs. CI runs `scripts/check` in the
`ci` Nix devShell on every pull request and on every push to `main`. The `ci`
devShell has only the tools that `scripts/check` uses. Run the same checks
locally with:

```bash
nix develop --command scripts/check
```

Each check below has:

- **Checks:** one statement of what the check makes sure of.
- **How:** the logic of the check, in words.
- **Assumptions:** what the check takes as true without testing it, and what
  it does not cover. A check can pass while one of its assumptions is false.

When you add, remove or change a test, update this file in the same pull
request. CI fails when a test has no entry here (see
[TESTS.md coverage](#testsmd-coverage)).

Terms used below:

- **Synthetic sequences** are the small sequences in `tests/synthetic.py`,
  built with pypulseq only. They use the system limits 28 mT/m and
  150 T/m/s, RF dead time 100 µs, RF ringdown 20 µs and ADC dead time 10 µs.

Contents:

1. [Static checks](#1-static-checks)
2. [Tests](#2-tests): the shared sequence helpers, the HTML and lane markup,
   the report page, the report page's chart math, and the report cards

---

## 1. Static checks

### Dependency install

**Checks:** The locked dependencies install.

**How:** uv installs the project and its dependencies at the exact versions in
`uv.lock`, into the project environment. Every later step uses this
environment.

**Assumptions:**

- The install uses `--frozen`, which reads `uv.lock` and does not compare it to
  `pyproject.toml`. CI does not fail when `pyproject.toml` has a dependency
  change that is not in `uv.lock`.
- The Python version is the one from the Nix devShell (3.12). No other version
  is tested.

### Lint

**Checks:** The Python code has no findings from the rules that ruff turns on
by default.

**How:** ruff checks every Python file in the repository. The project sets
only the line length (100), so ruff uses its default rule set. `uv.lock` has
ruff 0.16.8.

**Assumptions:**

- The rule set is ruff's default, not a choice that the project makes. The
  project does not pin ruff in `pyproject.toml`, so an update of ruff in
  `uv.lock` can add or remove rules.
- Some common rules are not in the default set, so ruff does not report them:
  line length (E501), function complexity (C901), `print` calls (T201),
  `assert` statements (S101), too many arguments (PLR0913) and magic numbers
  (PLR2004). The format check wraps most long lines of code, but it does not
  split long strings or comments, so a line can still be longer than 100.
- ruff does not check types. No type checker runs in CI.

### Format

**Checks:** The Python code is formatted as ruff format would format it.

**How:** ruff format runs in check mode. It fails when any file would change.
The line length is 100.

**Assumptions:** None.

### Shell scripts

**Checks:** The shell scripts have no shellcheck warnings or errors.

**How:** shellcheck runs on `scripts/check` and the hook
`.claude/hooks/block-main-writes.sh`, at severity warning and above.

**Assumptions:**

- Only these two files are checked. A new shell script is not checked until
  it is added to the list in `scripts/check`.
- Info and style findings do not fail the check.

### TESTS.md coverage

**Checks:** TESTS.md has exactly one entry for each test that pytest collects
and for each JavaScript test in `tests/js/`, in the section of that test's
file, and no entry for a test that does not exist.

**How:** In `scripts/check`, the pytest run writes the ID of each test that
it collects to a temporary file (option `--collected-tests-file`, from
`tests/conftest.py`), and the check reads that file (option `--collected`).
When the check runs alone, without `--collected`, it runs
`pytest --collect-only`, which lists the tests without running them. Each
pytest test is identified by its file name and its function name. A
parametrized test is one test. For each file that matches
`tests/js/test_*.js`, the check reads the file's text and takes each line
that starts with `test("test_` followed by word characters and a closing
quote as one JavaScript test, identified by its file name and its test name.
It does this by reading the file's text, without running Node.js. The check
reads TESTS.md and takes each level-4 heading that is a test name in
backticks as an entry. The entry belongs to the test file named in the
nearest level-3 heading above it. The check then reports:

- each pytest test or JavaScript test with no entry in its file's section;
- each entry for a test that does not exist in that file;
- each test with more than one entry;
- each entry that is not under a test file's heading;
- each line in a JavaScript test file that starts with `test(` but is not in
  that form, for example a test name with a hyphen, or a template string;
- each JavaScript test name that is in one file more than once.

It fails if it reports anything, if pytest cannot collect the tests, if it
cannot read the file of test IDs, or if a JavaScript test file and a pytest
test file have the same name.

**Assumptions:**

- In `scripts/check`, the check runs after pytest, although this file lists
  it before the tests. When a test fails, `scripts/check` stops, and the
  check does not run.
- In `scripts/check`, pytest runs on the `tests` directory without other
  test selection (no `-k`), so the file of test IDs lists every test.
- `scripts/check` skips both the pytest run and this check, with a skip
  line, when there is no `tests/` directory. This no longer applies once
  `tests/` exists, as it does from phase 1 onward.
- Test files are identified by file name only, without the directory. The
  check fails if two test files have the same name, in pytest, in the
  JavaScript tests, or between the two.
- The check looks only at the headings. It does not check that an entry has
  its Checks, How and Assumptions parts, or that the text is still correct
  after a test changes.
- A level-4 heading that is not a test name in backticks (for example a
  description of shared test sequences) is not an entry and is ignored.
- A JavaScript test written in another form, for example inside `describe`,
  or indented, is not found by the check. It has no entry, and the check
  does not report it as missing.

### JavaScript unit tests

**Checks:** The JavaScript unit tests in `tests/js/` pass.

**How:** `scripts/check` runs `node --test` on every file that matches
`tests/js/test_*.js`, with the Node.js version from the Nix devShell. When
the pattern matches no file, it prints a skip line and continues, instead of
failing.

**Assumptions:**

- Only the pure functions in `chart_math.js` are tested. `lane_chart.js` and
  `page.js`, and the card scripts, are not run by any test: there are no DOM
  tests. The charts are checked by hand in a browser before a pull request.
- The Node.js version is the one from the Nix devShell. No other version is
  tested.

---

## 2. Tests

### 2.1 Shared sequence helpers (`test_seq_utils.py`)

`test_seq_utils.py` tests the shared helpers in `seq_utils.py` that the
report cards use to read a pypulseq sequence: the block iterator, the RF
resampling helper, and the gradient corner/sample helper. It also checks
that the synthetic sequences in `tests/synthetic.py` are legal Pulseq.

#### `test_gamma_and_time_tolerance`

**Checks:** The gyromagnetic ratio is 42.576 MHz/T and the time tolerance is
1 ns.

**How:** The test compares the two shared constants with these values.

**Assumptions:** None.

#### `test_iter_blocks_start_times_and_events`

**Checks:** The block iteration gives every block in play order, with its ID,
its duration, a start time that is the sum of the durations before it, and its
events.

**How:** The test makes a sequence with three blocks: a block pulse, an x
trapezoid, and a delay. It iterates over the blocks and checks that the IDs
are in the sequence's block order. For each block it checks that the duration
is the sequence's block duration, and that the start time is exactly the sum
of the earlier durations, added one at a time. It checks that the first block
has the RF and the second has the x gradient, and that the last start time
plus the last duration is the end of the sequence.

**Assumptions:**

- The start times are compared for exact equality, not with a tolerance. This
  is correct because the test adds the durations in the same order.

#### `test_iter_blocks_empty_sequence`

**Checks:** The block iteration of an empty sequence gives no blocks.

**How:** The test iterates over a new sequence with no blocks and checks that
the result is empty.

**Assumptions:** None.

#### `test_hold_samples_keeps_uniform_shapes_unchanged`

**Checks:** An RF shape with uniform samples that fill the pulse duration is
used as it is.

**How:** The test makes a 3 ms sinc pulse. It checks that the sample times
are uniform and that the number of samples times the step is the pulse
duration. It then gets the held samples, and checks that the sample time and
the sample values are the same as the pulse's own.

**Assumptions:**

- pypulseq's sinc pulse has uniform samples that fill its duration. The test
  checks that before it tests the helper.

#### `test_hold_samples_interpolates_a_block_pulse`

**Checks:** A block pulse, which has samples only at its start and end, is
resampled on the RF raster with the correct number of samples, the correct
duration, and the correct flip angle.

**How:** The test makes a 2 ms, 60° block pulse. It checks that the pulse has
only two samples, which do not fill the duration. It gets the held samples on
the RF raster, and checks that the number of samples is the duration divided
by the raster, that the samples fill the duration, and that the sum of the
samples times the sample time is 60° as a fraction of a cycle (1/6).

**Assumptions:**

- The flip angle in cycles is the sum of B1 (Hz) × dt, which is correct for a
  pulse with constant phase.

#### `test_gradient_points_trapezoid`

**Checks:** `gradient_points` gives the four corner times and amplitudes of a
trapezoid gradient.

**How:** The test makes an x trapezoid and calls `gradient_points` with a
start time `t0`. It compares the returned times with `t0` plus the
gradient's delay plus the running sum of the rise time, the flat time and
the fall time, and compares the returned amplitudes with zero, the plateau
amplitude twice, and zero.

**Assumptions:** None.

#### `test_gradient_points_arbitrary`

**Checks:** `gradient_points` gives the sample times and amplitudes of an
arbitrary gradient, with one added point at each end for the shape's first
and last values.

**How:** The test makes an x arbitrary gradient from a 10-point waveform and
calls `gradient_points` with a start time `t0`. It checks that the first and
last returned amplitudes are the gradient's `first` and `last` values, and
that the first and last returned times are `t0` plus the delay, and `t0`
plus the delay plus the shape duration. It checks that the interior points
are the waveform samples unchanged, at `t0` plus the delay plus the
gradient's own sample times (`g.tt`).

**Assumptions:** None.

#### `test_synthetic_sequences_pass_the_timing_check`

**Checks:** Each synthetic sequence builder in `tests/synthetic.py` passes
pypulseq's timing check.

**How:** The test runs once for each of four builders — `spin_echo_sequence`,
`gre_sequence`, `empty_sequence` and `arbitrary_gradient_sequence` — builds
the sequence, calls its `check_timing` method, and asserts that the check
passes, showing the report if it does not.

**Assumptions:**

- pypulseq's timing check is trusted to cover raster alignment, RF dead time
  and ringdown, and ADC dead time before and after the ADC. This test does
  not check the report cards' own reading of the sequence, only that the
  synthetic sequences are legal Pulseq.

### 2.2 HTML and lane markup (`test_markup.py`)

`test_markup.py` tests the HTML helpers in `markup.py`: the zoom button
group placed above each line chart, and the HTML table with escaped cell
values.

#### `test_zoom_controls_markup`

**Checks:** `_zoom_controls` returns the zoom button group for a chart's SVG
id, with the id HTML-escaped.

**How:** The test calls `_zoom_controls("diagram")` and compares the result
with the expected markup: a controls group labeled "Zoom", with
`data-zoom-for="diagram"`, and five buttons in this order: ×10, ×2, ×0.5,
×0.1 and Reset. It calls `_zoom_controls('a"b')` and checks that the result
is the same markup with the id HTML-escaped in `data-zoom-for`.

**Assumptions:** None.

#### `test_table_escapes_html`

**Checks:** `_table` escapes HTML special characters in both the header and
the cell values.

**How:** The test calls `_table` with one header and one row, each holding
`<`, `&`, `"` and `'` characters. It checks that the raw `<h1>` and
`<script>` tags are not in the result, and that the HTML-escaped header text
and the HTML-escaped cell text are in the result.

**Assumptions:** None.

### 2.3 The report page (`test_page.py`)

`test_page.py` tests `page.py`. `render_page` builds the report page's HTML
from a list of `Card` objects, in order: each card's title is escaped, its
JSON data (if any) is placed in a `<script type="application/json">`
element, and its script (if any) is included once, even when more than one
card uses it. The tests also cover card and script id validation, the
`__NAME__` placeholder substitution, `card_asset`, and `write_page`.

#### `test_cards_appear_in_order_with_escaped_titles`

**Checks:** `render_page` includes each card's title, HTML-escaped, as an
`<h2>`, in the order the cards are given.

**How:** The test builds three cards with titles that include `<`, `>` and
`&`, calls `render_page`, and checks that each escaped title appears as
`<h2>...</h2>`, and that the three headings appear, by string index, in the
cards' order.

**Assumptions:** None.

#### `test_duplicate_card_id_raises`

**Checks:** `render_page` raises `ValueError` when two cards have the same
id.

**How:** The test builds two cards with the id "dup" and checks that
`render_page` raises `ValueError`.

**Assumptions:** None.

#### `test_bad_card_id_raises`

**Checks:** `render_page` raises `ValueError` for a card id that does not
match `[a-z][a-z0-9-]*`.

**How:** The test runs once for each of three bad ids — "Bad_id"
(uppercase), "1x" (starts with a digit) and "" (empty) — and checks that
`render_page` raises `ValueError`.

**Assumptions:** None.

#### `test_bad_card_script_name_raises`

**Checks:** `render_page` raises `ValueError` when a card's script name does
not match `[a-z][a-z0-9-]*`.

**How:** The test builds a card with `script="Bad_Script"` and checks that
`render_page` raises `ValueError`.

**Assumptions:** None.

#### `test_card_data_element_holds_json`

**Checks:** A card's JSON data appears in a `<script type="application/json"
id="{id}-data">` element in the page.

**How:** The test builds a card with a dict of data, calls `render_page`,
finds the JSON script element with a regular expression, unescapes its
`</`-escaping, and checks that it parses back to the same data.

**Assumptions:** None.

#### `test_card_data_element_escapes_close_script`

**Checks:** A `</script>` in a card's JSON data does not end the JSON script
element early.

**How:** The test builds a card whose data contains the literal text
`</script><script>alert(1)</script>`, calls `render_page`, and finds the
JSON script element with the same regular expression, which matches only up
to the first real `</script>` close tag. It checks that `</script>` is not
in the matched payload, and that the payload parses back, after unescaping,
to the original data.

**Assumptions:** None.

#### `test_card_without_data_has_no_data_element`

**Checks:** A card with `data=None` has no JSON data element.

**How:** The test builds a card with `data=None`, calls `render_page`, and
checks that "a-data" is not in the result.

**Assumptions:** None.

#### `test_collapsed_card_uses_details`

**Checks:** A card with `collapsed=True` is rendered as a closed `<details>`
element with the title in a `<summary>`, not as an `<h2>`.

**How:** The test builds a card with `collapsed=True`, calls `render_page`,
and checks that the result has `<details>` and `<summary>A title</summary>`,
and has no `<h2>`.

**Assumptions:** None.

#### `test_card_script_included_once_for_two_cards`

**Checks:** A library card script is included in the page once, even when
two cards use it.

**How:** The test copies the real assets directory into a temporary
directory, adds a card script file with a marker comment, points
`page._ASSETS` at the copy, builds two cards that both use that script,
calls `render_page`, and checks that the marker text appears exactly once in
the result.

**Assumptions:**

- The test uses `monkeypatch` to point `page._ASSETS` at a temporary copy of
  the real assets directory, so it can add a card script without changing
  the real assets directory.

#### `test_card_script_without_library_file_uses_extra_scripts`

**Checks:** A card whose script name has no library file under
`assets/cards/` gets its script from `extra_scripts`, and library card
scripts that are unrelated to it are not included.

**How:** The test builds a card with `script="consumer"`, for which no
`assets/cards/consumer.js` file exists, and passes an extra script that
registers "consumer" with `PulseqReport.registerCard`. It checks that the
extra script's marker is in the result and that the unrelated demo card
script's marker is not.

**Assumptions:** None.

#### `test_script_order`

**Checks:** The page's scripts appear in this order: `chart_math.js`,
`lane_chart.js`, each card's library script, the extra scripts in the given
order, and `page.js`.

**How:** The test builds one card with a library script and two extra
scripts, calls `render_page`, and checks that the string indices of a
`chart_math.js` marker, a `lane_chart.js` (`PulseqReport`) marker, the card
script's marker, each extra script's marker, and a `page.js` marker are
in increasing order.

**Assumptions:** None.

#### `test_each_script_is_its_own_script_element`

**Checks:** Each script is in its own `<script>` element, not concatenated
with the others into one element.

**How:** The test builds one card with no script and one extra script,
calls `render_page`, and counts the occurrences of `<script>\n`. With
`chart_math.js`, `lane_chart.js`, the extra script and `page.js`, and no
card script, the count must be 4.

**Assumptions:** None.

#### `test_extra_script_with_close_tag_raises`

**Checks:** `render_page` raises `ValueError` when an extra script contains
a `</script` tag, in any letter case.

**How:** The test runs once for each of three forms of the closing tag —
`</script>`, `</SCRIPT>` and `</ScRiPt ` — and checks that `render_page`
raises `ValueError` for an extra script that contains that text.

**Assumptions:** None.

#### `test_substitute_replaces_every_placeholder`

**Checks:** `_substitute` replaces each `__NAME__` placeholder in a template
with its value.

**How:** The test calls `_substitute("__A__-__B__", {"__A__": "1", "__B__":
"2"})` and checks that the result is "1-2".

**Assumptions:** None.

#### `test_substitute_raises_on_unresolved_placeholder`

**Checks:** `_substitute` raises `ValueError`, naming the placeholder, when
the template has a `__NAME__`-shaped placeholder that is not in the
replacements.

**How:** The test calls `_substitute` with a template that has
"__MISSING__" and a replacements dict without that key, and checks that it
raises `ValueError` matching "__MISSING__".

**Assumptions:** None.

#### `test_substitute_keeps_placeholder_shaped_value_as_is`

**Checks:** A replacement value that is itself shaped like a placeholder is
not substituted a second time.

**How:** The test calls `_substitute("__A__", {"__A__": "__MISSING__"})` and
checks that the result is "__MISSING__", unchanged, because the substitution
makes one pass over the template.

**Assumptions:** None.

#### `test_render_page_with_placeholder_shaped_card_body_does_not_raise`

**Checks:** A card body that contains `__NAME__`-shaped text does not raise,
because it is not itself a placeholder in the page template.

**How:** The test builds a card whose `body_html` contains "__FOO__" and
checks that `render_page` does not raise, and that "__FOO__" is still in the
result.

**Assumptions:** None.

#### `test_write_page_matches_render_page`

**Checks:** `write_page` writes the same HTML that `render_page` returns.

**How:** The test builds one card, calls `render_page` directly, then calls
`write_page` to a temporary path with the same arguments, and checks that
the file's contents equal the `render_page` result.

**Assumptions:** None.

#### `test_card_asset_bad_name_raises`

**Checks:** `card_asset` raises `ValueError` for a name that does not match
`[a-z][a-z0-9-]*`.

**How:** The test calls `card_asset("../x")` and checks that it raises
`ValueError`.

**Assumptions:** None.

#### `test_card_asset_missing_name_raises`

**Checks:** `card_asset` raises an error for a name with no matching file
under `assets/cards/`.

**How:** The test calls `card_asset("does-not-exist")` and checks that it
raises `FileNotFoundError` or `OSError`.

**Assumptions:** None.

#### `test_rendered_page_has_no_leftover_placeholder`

**Checks:** The rendered page has no `__NAME__`-shaped text left over from an
unresolved template placeholder.

**How:** The test builds one plain card, calls `render_page`, and checks
that no substring matching `__[A-Z_]+__` is in the result.

**Assumptions:**

- A card's own title, body or data could coincidentally contain such text.
  This test's one card does not, so it does not rule that out in general.

### 2.4 Chart math (`test_chart_math.js`)

`chart_math.js` has the pure functions that the report page's charts use:
`fmt` formats a number for display, `niceTicks` chooses the tick values for
an axis, `valueAt` reads a lane's value at a given time, `visiblePoints`
picks the points of one line segment that the chart must actually draw for
the current view, `clampView` moves and, if needed, widens a view so it fits
inside a chart's extent, `zoomView` zooms a view by a factor about an
anchor, `panView` shifts a view by a fixed amount, and `dragView` turns the
two ends of a drag into a view. The report page (`page.py`) puts
`chart_math.js` and `lane_chart.js` first among its scripts, each in its own
`<script>` element, before any card scripts, the extra scripts and
`page.js`. `lane_chart.js` has `PulseqReport.laneChart`, which calls these
functions to draw the charts, and calls `clampView`, `zoomView`, `panView`
and `dragView` for the zoom and pan controls on a chart. Its `render`
function calls `visiblePoints` once for each line segment, with the current
view and a bucket count of 2 times the plot width in viewBox units (812), so
a zoomed-out chart with many points does not draw more points than the chart
can show.

The tests load `chart_math.js` directly, with Node's `require`, from
`src/pulseq_reports/assets/chart_math.js`. They use `node:test` and
`node:assert/strict`. They do not load `lane_chart.js`, `page.js` or the
page, and they do not use a browser or a DOM.

**Assumptions for the whole file:**

- The functions take only plain values as arguments and return only plain
  values. Nothing in a test depends on the page or the DOM.
- For the first 10 tests, of `fmt`, `niceTicks` and `valueAt`, the expected
  values are the results of the functions as they were in vb-pulseq's
  `report.js`, before vb-pulseq moved them into `chart_math.js`. The tests
  keep that behavior. They do not show that the behavior is correct for the
  charts.
- `visiblePoints`, `clampView`, `zoomView`, `panView` and `dragView` were new
  in vb-pulseq's `chart_math.js`: they were not in vb-pulseq's `report.js`
  before that move. Their tests check properties from each function's
  specification, the comment above it in `chart_math.js`, not expected
  values from an earlier version of the function.

#### `test_nice_ticks_step_is_1_2_or_5_times_power_of_ten`

**Checks:** `niceTicks` chooses a step that is 1, 2 or 5 times a power of
ten, and lists the tick values at that step.

**How:** The test calls `niceTicks` three times, each with 8 as the target
number of ticks. For the range 0 to 8, the step is 1 and the result is 0, 1,
2, 3, 4, 5, 6, 7, 8. For the range 0 to 100, the step is 20 and the result is
0, 20, 40, 60, 80, 100. For the range 0 to 24, the step is 5 and the result
is 0, 5, 10, 15, 20.

**Assumptions:** None beyond the file's assumptions.

#### `test_nice_ticks_starts_at_first_multiple_at_or_above_lo`

**Checks:** `niceTicks` starts its list at the first multiple of the step at
or above the low end of the range, and stops at or below the high end.

**How:** The test calls `niceTicks(3, 24, 8)`. The step is 5. The first
multiple of 5 at or above 3 is 5, and the last multiple of 5 at or below 24
is 20. The result must be 5, 10, 15, 20.

**Assumptions:** None beyond the file's assumptions.

#### `test_value_at_interpolates_linearly_within_a_segment`

**Checks:** `valueAt` interpolates linearly between the two points of a
segment.

**How:** The test makes a lane with one segment from the point (0, 0) to the
point (10, 100). At t = 5, halfway between the two points, `valueAt` must
return 50.

**Assumptions:** None beyond the file's assumptions.

#### `test_value_at_gate_lane_is_on_inside_window_and_off_outside`

**Checks:** For a gate lane, `valueAt` gives "on" inside one of its windows
and "off" outside every window.

**How:** The test makes a gate lane with one window from t = 2 to t = 5. At
t = 3, inside the window, `valueAt` must return "on". At t = 7, outside the
window, it must return "off".

**Assumptions:** None beyond the file's assumptions.

#### `test_value_at_returns_lane_fill_outside_all_segments`

**Checks:** Outside every segment, `valueAt` returns the lane's fill value,
whether the fill is null or a number.

**How:** The test makes two lanes with the same one segment, from the point
(0, 0) to the point (10, 100): one with a fill of null and one with a fill
of 42. At t = 20, after the end of the segment, `valueAt` on the first lane
must return null. At t = -5, before the start of the segment, `valueAt` on
the second lane must return 42.

**Assumptions:** None beyond the file's assumptions.

#### `test_fmt_rounds_to_three_significant_figures`

**Checks:** `fmt` rounds a number to three significant figures.

**How:** The test calls `fmt(1234.5)` and checks that the result is "1230".
It calls `fmt(0.012345)` and checks that the result is "0.0123".

**Assumptions:** None beyond the file's assumptions.

#### `test_fmt_gives_zero_for_magnitudes_below_5e_minus_4`

**Checks:** `fmt` gives "0" for a value whose magnitude is below 5 × 10⁻⁴,
whether the value is positive or negative.

**How:** The test calls `fmt(0.0001)` and `fmt(-0.0001)`, and checks that
each result is "0".

**Assumptions:** None beyond the file's assumptions.

#### `test_fmt_uses_unicode_minus_sign_for_negative_numbers`

**Checks:** `fmt` writes a negative number with the Unicode minus sign, not a
hyphen.

**How:** The test calls `fmt(-12.345)` and checks that the result is
"−12.3", with the Unicode minus sign (U+2212).

**Assumptions:** None beyond the file's assumptions.

#### `test_fmt_uses_em_dash_for_null_or_undefined`

**Checks:** `fmt` gives an em dash for both null and undefined.

**How:** The test calls `fmt(null)` and `fmt(undefined)`, and checks that
each result is the em dash character "—" (U+2014).

**Assumptions:** None beyond the file's assumptions.

#### `test_fmt_returns_strings_unchanged`

**Checks:** `fmt` returns a string value unchanged.

**How:** The test calls `fmt("abc")` and checks that the result is "abc".

**Assumptions:** None beyond the file's assumptions.

#### `test_visible_points_keeps_the_largest_and_smallest_value_in_the_view`

**Checks:** `visiblePoints` keeps a single spike up and a single spike down
that lie inside the view, even after decimation.

**How:** The test builds 100000 points, indexed 0 to 99999, with x equal to
the index. Each point's value is sin(index / 500), except point 40000, whose
value is 1000, and point 70000, whose value is -1000. The test calls
`visiblePoints(points, 0, 99999, 100)`, so the view covers every point. The
result must contain the value 1000 and the value -1000.

**Assumptions:** None beyond the file's assumptions.

#### `test_visible_points_keeps_index_order`

**Checks:** `visiblePoints` returns a subsequence of the input points, in
the same order as the input, with non-decreasing x values.

**How:** The test builds 50000 points, indexed 0 to 49999, with x equal to
the index and value sin(index / 137) + cos(index / 29). It calls
`visiblePoints(points, 0, 49999, 33)`. For each point in the result, the
test looks up the point's index in the input array by identity, and checks
that this index is larger than the previous result point's index, and that
the point's x value is not smaller than the previous result point's x
value.

**Assumptions:** None beyond the file's assumptions.

#### `test_visible_points_returns_a_short_slice_unchanged`

**Checks:** When the number of points between the view edges is small
enough, `visiblePoints` returns them unchanged, with no decimation.

**How:** The test builds 10 points, with x and value both equal to the
index, 0 to 9. It calls `visiblePoints(points, 2.5, 6.5, 3)`. With 3
buckets, a range of up to 4 times 3, or 12, points comes back unchanged. The
largest index with x at or below 2.5 is 2, and the smallest index with x at
or above 6.5 is 7, so the range from index 2 to index 7 has 6 points, at or
below that limit. The result must equal the input points from index 2 to
index 7.

**Assumptions:** None beyond the file's assumptions.

#### `test_visible_points_is_empty_for_a_segment_outside_the_view`

**Checks:** `visiblePoints` returns an empty array when no point of the
segment lies inside the view, and for an empty segment.

**How:** The test builds 10 points, with x and value both equal to the
index, 0 to 9. It makes three calls, each with 10 buckets. In
`visiblePoints(points, 20, 30, 10)`, the view is to the right of every point.
In `visiblePoints(points, -30, -20, 10)`, the view is to the left of every
point. `visiblePoints([], 0, 1, 10)` has no points. Each call must return an
empty array.

**Assumptions:** None beyond the file's assumptions.

#### `test_visible_points_keeps_the_points_just_outside_the_view`

**Checks:** `visiblePoints` keeps one point just outside each edge of the
view, so the line from the edge to the first visible point still draws.

**How:** The test builds 100 points, with x and value both equal to the
index, 0 to 99, and calls `visiblePoints` three times, each with 10 buckets.
For the view 10.5 to 20.5, no point sits exactly on an edge, and the result
must start at x = 10 and end at x = 21, one point past each edge. For the
view 10 to 20, both edges sit exactly on a point, and the result must start
at x = 10 and end at x = 20. For the two-point segment [[0, 0], [100, 1]]
with the view 40 to 60, no point lies inside the view, and the result must
equal the two input points unchanged.

**Assumptions:** None beyond the file's assumptions.

#### `test_visible_points_has_at_most_4_buckets_plus_2_points`

**Checks:** `visiblePoints` never returns more than 4 times the bucket
count, plus 2, points.

**How:** The test builds 120000 points, with x equal to the index, 0 to
119999, and value sin(index / 331). It calls
`visiblePoints(points, 0, 119999, 1624)`. The length of the result must be
at most 4 times 1624, plus 2.

**Assumptions:** None beyond the file's assumptions.

#### `test_visible_points_keeps_vertical_edges`

**Checks:** `visiblePoints` keeps both the low value and the high value of
the square pulses in each bin.

**How:** The test builds 50 buckets, with 500 square pulses ("blocks") in
each bucket, 25000 blocks in all. Each block is 4 points, 10 x units apart
from the next block: value 0, then value 1 at the same x, then value 1 one x
unit later, then value 0 at that same later x. This puts the block's rising
edge and falling edge inside one bin. The test calls `visiblePoints` with
the view from x = 0 to x = 10 times the number of blocks, and 50 buckets.
For every bin, the result must contain at least one point with value 0 and
at least one point with value 1 in that bin.

**Assumptions:** None beyond the file's assumptions.

#### `test_clamp_view_keeps_a_view_that_is_inside_the_extent`

**Checks:** `clampView` returns a view unchanged when it already fits inside
the extent at or above the minimum span.

**How:** The test calls `clampView([10, 20], [0, 100], 5)` and checks that
the result is `[10, 20]`.

**Assumptions:** None beyond the file's assumptions.

#### `test_clamp_view_moves_a_view_past_an_end_inside_without_a_change_in_width`

**Checks:** `clampView` shifts a view that reaches past one end of the
extent so it lies inside, without changing its width.

**How:** The test calls `clampView([-10, 10], [0, 100], 5)`, a 20-wide view
past the left end, and checks that the result is `[0, 20]`, the same width
shifted right. It calls `clampView([90, 110], [0, 100], 5)`, a 20-wide view
past the right end, and checks that the result is `[80, 100]`, the same
width shifted left.

**Assumptions:** None beyond the file's assumptions.

#### `test_clamp_view_gives_the_extent_for_a_view_wider_than_the_extent`

**Checks:** `clampView` returns the whole extent when the view is wider than
the extent.

**How:** The test calls `clampView([-50, 200], [0, 100], 5)` and checks that
the result is `[0, 100]`.

**Assumptions:** None beyond the file's assumptions.

#### `test_clamp_view_widens_a_view_narrower_than_min_span_about_its_centre`

**Checks:** `clampView` widens a view narrower than the minimum span, about
the view's own centre, then moves the widened view inside the extent if it
still reaches past an end.

**How:** The test calls `clampView([40, 42], [0, 100], 5)`. Widening the
2-wide view about its centre (41) to the minimum span 5 gives `[38.5, 43.5]`,
which is already inside the extent, so that is the result. It calls
`clampView([0, 1], [0, 100], 5)`. Widening the 1-wide view about its centre
(0.5) to width 5 gives `[-2, 3]`, which reaches past the left end, so the
result is that view shifted right, `[0, 5]`.

**Assumptions:** None beyond the file's assumptions.

#### `test_clamp_view_gives_the_extent_when_min_span_is_wider_than_the_extent`

**Checks:** `clampView` returns the whole extent when the minimum span
itself is wider than the extent.

**How:** The test calls `clampView([10, 20], [0, 100], 200)` and checks that
the result is `[0, 100]`.

**Assumptions:** None beyond the file's assumptions.

#### `test_zoom_view_by_2_halves_the_width_about_the_anchor`

**Checks:** `zoomView` with factor 2 halves the view's width, centred on the
anchor, when the anchor lies inside the view.

**How:** The test calls `zoomView([0, 100], 2, 30, [-1000, 1000], 1)`. The
100-wide view zoomed by factor 2 is 50 wide, centred on the anchor 30, which
gives `[5, 55]`; this is inside the extent, so it is not moved further. The
result must be `[5, 55]`.

**Assumptions:** None beyond the file's assumptions.

#### `test_zoom_view_uses_the_view_centre_without_an_anchor_in_the_view`

**Checks:** `zoomView` zooms about the view's own centre when there is no
anchor, and when the anchor lies outside the view.

**How:** The test calls `zoomView([0, 100], 2, null, [-1000, 1000], 1)` with
no anchor, and checks that the result is `[25, 75]`, the halved width
centred on the view's own centre, 50. It calls
`zoomView([0, 100], 2, 200, [-1000, 1000], 1)` with the anchor 200, outside
the view, and checks that the result is the same, `[25, 75]`.

**Assumptions:** None beyond the file's assumptions.

#### `test_zoom_view_by_0_1_near_an_end_moves_the_view_inside_the_extent`

**Checks:** A zoom out that would put the view past an end of the extent
instead shifts the zoomed view inside, keeping its new, wider width.

**How:** The test calls `zoomView([0, 20], 0.1, 10, [0, 1000], 1)`. The
20-wide view zoomed by factor 0.1 is 200 wide, centred on the anchor 10,
which gives `[-90, 110]`. That is narrower than the extent (width 1000) but
reaches past the left end, so the result is shifted right, `[0, 200]`.

**Assumptions:** None beyond the file's assumptions.

#### `test_zoom_view_by_10_stops_at_min_span`

**Checks:** A zoom in that would make the view narrower than the minimum
span instead widens it back to the minimum span, about the same centre.

**How:** The test calls `zoomView([40, 60], 10, 50, [0, 1000], 5)`. The
20-wide view zoomed by factor 10 is 2 wide, narrower than the minimum span
5, so the result is widened to width 5 about the centre 50, `[47.5, 52.5]`.

**Assumptions:** None beyond the file's assumptions.

#### `test_zoom_view_by_0_1_from_a_wide_view_gives_the_extent`

**Checks:** A zoom out that would make the view wider than the extent
instead gives the whole extent.

**How:** The test calls `zoomView([400, 600], 0.1, null, [0, 1000], 1)`. The
200-wide view zoomed by factor 0.1 is 2000 wide, wider than the extent
(width 1000), so the result is the whole extent, `[0, 1000]`.

**Assumptions:** None beyond the file's assumptions.

#### `test_pan_view_moves_both_ends_by_delta`

**Checks:** `panView` shifts both ends of the view by the same amount,
without changing its width.

**How:** The test calls `panView([10, 20], 5, [0, 1000])` and checks that
the result is `[15, 25]`.

**Assumptions:** None beyond the file's assumptions.

#### `test_pan_view_stops_at_each_end_and_keeps_the_width`

**Checks:** `panView` stops a pan at each end of the extent, keeping the
view's width.

**How:** The test calls `panView([5, 15], -10, [0, 1000])`, a pan past the
left end, and checks that the result is `[0, 10]`, the same 10-wide view
shifted right to the end. It calls `panView([985, 995], 20, [0, 1000])`, a
pan past the right end, and checks that the result is `[990, 1000]`.

**Assumptions:** None beyond the file's assumptions.

#### `test_drag_view_gives_the_same_view_in_both_directions`

**Checks:** `dragView` gives the same view whichever end of the drag comes
first.

**How:** The test calls `dragView(20, 50, [0, 1000], 1)` and
`dragView(50, 20, [0, 1000], 1)`, and checks that both give `[20, 50]`.

**Assumptions:** None beyond the file's assumptions.

#### `test_drag_view_is_null_for_a_zero_width_drag`

**Checks:** `dragView` gives null for a drag whose two ends are equal.

**How:** The test calls `dragView(30, 30, [0, 1000], 1)` and checks that the
result is null.

**Assumptions:** None beyond the file's assumptions.

#### `test_drag_view_widens_a_narrow_drag_to_min_span`

**Checks:** `dragView` widens a drag narrower than the minimum span, about
the drag's own centre.

**How:** The test calls `dragView(50, 52, [0, 1000], 10)`. The 2-wide drag
is widened about its centre, 51, to the minimum span 10, which gives the
result `[46, 56]`.

**Assumptions:** None beyond the file's assumptions.

#### `test_view_functions_do_not_change_their_arguments`

**Checks:** `clampView`, `zoomView`, `panView` and `dragView` do not change
the view or extent arrays passed to them, and `clampView` returns a new
array rather than the view it was given.

**How:** The test makes a view `[10, 20]` and an extent `[0, 100]`, and a
copy of each. It calls `clampView(view, extent, 5)` and checks that `view`
and `extent` still equal their copies, and that the result is not the same
array as `view`. It calls `zoomView(view, 2, 15, extent, 5)` and checks that
`view` and `extent` still equal their copies. It calls
`panView(view, 5, extent)` and checks the same. It calls
`dragView(30, 10, extent, 5)` and checks that `extent` still equals its
copy.

**Assumptions:** None beyond the file's assumptions.

### 2.5 Timing card (`test_timing_card.py`)

Phase 2 adds the entries.

### 2.6 Definitions card (`test_definitions_card.py`)

Phase 2 adds the entries.

### 2.7 RF exposure (`test_rf_exposure.py`)

Phase 3 adds the entries.

### 2.8 RF exposure card (`test_rf_exposure_card.py`)

Phase 3 adds the entries.

### 2.9 Gradient spectrum (`test_grad_spectrum.py`)

Phase 4 adds the entries.

### 2.10 Gradient spectrum card (`test_spectrum_card.py`)

Phase 4 adds the entries.

### 2.11 PNS prediction (`test_pns.py`)

Phase 5 adds the entries.

### 2.12 PNS card (`test_pns_card.py`)

Phase 5 adds the entries.

### 2.13 Gradient limits (`test_grad_limits.py`)

Phase 6 adds the entries.

### 2.14 Gradient limits card (`test_gradient_limits_card.py`)

Phase 6 adds the entries.

### 2.15 Waveform data (`test_waveforms.py`)

Phase 7 adds the entries.

### 2.16 Sequence diagram card (`test_diagram_card.py`)

Phase 7 adds the entries.

### 2.17 Block table card (`test_blocks_card.py`)

Phase 7 adds the entries.
