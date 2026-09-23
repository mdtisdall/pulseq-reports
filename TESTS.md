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

#### `test_gradient_offsets_trapezoid`

**Checks:** `gradient_offsets` gives the delay and the four corner offsets and
amplitudes of a trapezoid gradient, with the offsets relative to the delay
(not including it).

**How:** The test makes an x trapezoid and calls `gradient_offsets`. It
compares the returned delay with the gradient's own `delay`, the returned
offsets with the running sum of the rise time, the flat time and the fall
time (starting at zero), and the returned amplitudes with zero, the plateau
amplitude twice, and zero.

**Assumptions:** None.

#### `test_gradient_offsets_arbitrary`

**Checks:** `gradient_offsets` gives the delay and the sample offsets and
amplitudes of an arbitrary gradient, with one added point at each end, at
offset 0.0 and at the shape duration, for the shape's `first` and `last`
values.

**How:** The test makes an x arbitrary gradient from a 10-point waveform,
checks that pypulseq gave it both a `first` and a `shape_dur` attribute (the
branch this test means to exercise), and calls `gradient_offsets`. It checks
that the first and last returned amplitudes are the gradient's `first` and
`last` values, and that the first and last returned offsets are 0.0 and the
shape duration. It checks that the interior offsets and amplitudes are the
gradient's own sample times (`g.tt`) and waveform, unchanged.

**Assumptions:**

- pypulseq's `make_arbitrary_grad` gives the shape both `first` and
  `shape_dur` by default. The test checks that before it tests the helper,
  so the case without them (used only for a shape that already has points at
  its own ends) is not covered here.

#### `test_gradient_points_matches_gradient_offsets_exactly`

**Checks:** `gradient_points(g, t0)` gives exactly `(t0 + delay) + offsets`
for the `delay` and `offsets` that `gradient_offsets(g)` returns, for both a
trapezoid and an arbitrary gradient. This is the relationship a later phase
depends on to rebuild point times from the stored offset tables.

**How:** The test is parametrized over a trapezoid and an arbitrary
gradient. For each, it calls `gradient_points` with a non-zero `t0` and
`gradient_offsets` on the same event, then compares the two with
`numpy.testing.assert_array_equal` — exact equality, not a tolerance.

**Assumptions:**

- Bit-for-bit equality is the right check here, not an approximation: the
  point in this test is that `gradient_points` is defined in terms of
  `gradient_offsets` with no room for a rounding difference to creep in.

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
an axis, `valueAt` reads a lane's value at a given time, `minMaxAt` reads the
minimum and the maximum of a minmax lane's bin at a given time, `visiblePoints`
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
can show. Its tooltip (`setCursor`) calls `valueAt` for a lane without the
key `minmax: true`, and `minMaxAt` for a lane with that key (except a gate
lane, which is always read with `valueAt`).

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
- `minMaxAt` is new to this library; it has no vb-pulseq history. Its tests
  check properties from the comment above it in `chart_math.js` and from
  section 4.4 item 2 of `docs/plans/diagram-event-table.md`, which defines
  the point pairs `(bin start, minimum), (bin centre, maximum)` that a
  minmax lane's segments hold.

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

#### `test_min_max_at_reads_the_bin_that_holds_the_cursor`

**Checks:** `minMaxAt` returns the minimum and the maximum of the bin whose
span holds a given time.

**How:** The test makes a lane with one segment of two bins: the first bin's
points are (0, -1) and (5, 2), and the second bin's points are (10, -3) and
(15, 4). At t = 3, inside the first bin, `minMaxAt` must return {min: -1,
max: 2}. At t = 12, inside the second bin, it must return {min: -3, max: 4}.

**Assumptions:** None beyond the file's assumptions.

#### `test_min_max_at_bin_start_belongs_to_the_later_bin`

**Checks:** A time exactly at the start of a bin belongs to that bin, not to
the bin before it: a bin's own right edge is exclusive.

**How:** Using the same two-bin lane as the previous test, the test calls
`minMaxAt` at t = 10, the start of the second bin, which is also the first
bin's own right edge. The result must be the second bin's {min: -3, max: 4}.

**Assumptions:** None beyond the file's assumptions.

#### `test_min_max_at_last_bin_of_a_segment_is_inclusive_at_its_own_end`

**Checks:** The last bin of a segment has no following pair to read its
right edge from; `minMaxAt` derives it from the bin's own two points
instead, as `2 * centre - start`, and a time exactly at that computed end is
still in the bin.

**How:** Using the same two-bin lane, the second bin's own end is
`2 * 15 - 10 = 20`. The test calls `minMaxAt` at t = 20 and checks that the
result is still the second bin's {min: -3, max: 4}.

**Assumptions:** None beyond the file's assumptions.

#### `test_min_max_at_returns_null_in_a_gap_between_segments`

**Checks:** `minMaxAt` returns null for a time that falls between two
segments, where no bin has a value (for example, a gap between two RF
pulses on the phase lane).

**How:** The test makes a lane with two segments: one bin, (0, -1) and
(5, 2), covering [0, 10), and one bin, (20, -3) and (25, 4), covering
[20, 30), with no bin for [10, 20). `minMaxAt` at t = 3 and t = 22 must
return the first and the second bin; at t = 15, in the gap, it must return
null.

**Assumptions:** None beyond the file's assumptions.

#### `test_min_max_at_returns_null_past_the_last_bin`

**Checks:** `minMaxAt` returns null for a time after the last bin's own end.

**How:** The test makes a lane with one segment of one bin, (0, -1) and
(5, 2), whose own end is `2 * 5 - 0 = 10`. The test calls `minMaxAt` at
t = 11, past that end, and checks that the result is null.

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

`test_timing_card.py` tests `cards/timing.py`. `timing_card` builds the
timing check card from pypulseq's `check_timing` result for one or more
sequences. For one sequence, the body is the same HTML as vb-pulseq's timing
check. For more than one sequence, a status line names each file and an
error table is placed under each file that fails.

#### `test_timing_card_for_one_sequence_matches_timing_html`

**Checks:** For one sequence, `timing_card`'s `body_html` equals the same
HTML as vb-pulseq's timing check (parity), and the card's `id`, `title`,
`data` and `script` fields are correct.

**How:** The test builds a synthetic spin echo sequence (it passes the
timing check), calls `timing_card` with one `NamedSequence`, and compares
`body_html` to `timing._timing_html(timing.timing_errors(seq))` called
directly. It also checks `id == "timing"`, `title == "Timing check"`,
"Timing check passed" is in the body, and `data` and `script` are both None.

**Assumptions:** The synthetic spin echo sequence passes pypulseq's timing
check.

#### `test_timing_card_lists_timing_errors_for_one_sequence`

**Checks:** `timing_card` shows the failure text and the error type for a
sequence with a timing violation.

**How:** The test builds a sequence with one RF block whose delay is set to
0 after construction, below the RF dead time (as in vb-pulseq's own
bad-sequence test), confirms that `timing_errors` reports an `RF_DEAD_TIME`
error, then checks that `timing_card`'s body has "Timing check failed" and
"RF_DEAD_TIME".

**Assumptions:** pypulseq's `check_timing` reports an `RF_DEAD_TIME` error
for an RF block whose delay is below the system's RF dead time.

#### `test_timing_card_for_two_sequences_names_each_file_and_only_the_failing_one_has_a_table`

**Checks:** With two sequences, `timing_card` names each file in a status
line, in the given order, and places the error table only under the file
that fails.

**How:** The test builds one `NamedSequence` with a valid sequence and one
with the bad sequence from the previous test, calls `timing_card` with both,
and checks that both file names appear (the good one first), that both a
"passed" and a "failed" status line are present, that exactly one error
table appears in the body, and that splitting the body on the second file's
name puts "RF_DEAD_TIME" only in the part after it.

**Assumptions:** None beyond the previous test's.

#### `test_timing_card_escapes_file_names`

**Checks:** A file name with HTML special characters is escaped in the
body.

**How:** The test calls `timing_card` with a `NamedSequence` named `"a<b>"`
and checks that the raw text is absent from the body and the HTML-escaped
form is present.

**Assumptions:** None.

#### `test_render_page_accepts_timing_card`

**Checks:** `page.render_page` accepts a `Card` from `timing_card` and
renders its title.

**How:** The test builds a timing card for one sequence, renders it with
`page.render_page`, and checks that `<h2>Timing check</h2>` is in the
result.

**Assumptions:** None beyond `test_page.py`'s coverage of `render_page`.

### 2.6 Definitions card (`test_definitions_card.py`)

`test_definitions_card.py` tests `cards/definitions.py`. `definitions_card`
builds the two-column definitions table from a sequence's `Definitions`,
the same as vb-pulseq, for one sequence. For more than one sequence, it
builds one row for each definition key found in any file (in first-seen
order), with one column for each file; a file that lacks a key gets an
empty cell. When no file has any definitions, the body is a muted "No
definitions." paragraph instead of an empty table — a choice this phase
makes, since vb-pulseq has no multi-file case to match.

#### `test_definitions_card_for_one_sequence_matches_the_vb_table`

**Checks:** For one sequence, `definitions_card`'s `body_html` equals
vb-pulseq's two-column definitions table for the same sequence (parity),
and the card's `id`, `title`, `data` and `script` fields are correct.

**How:** The test builds a synthetic GRE sequence (it has definitions,
including "TR"), computes the same table directly with `markup._table` from
`seq.definitions.items()`, and compares it to `definitions_card`'s
`body_html`. It also checks `id == "definitions"`, `title == "Definitions"`,
and `data` and `script` are both None.

**Assumptions:** None.

#### `test_definitions_card_for_one_sequence_with_no_definitions_is_an_empty_table`

**Checks:** A single sequence with no definitions gets the two-column table
with an empty body, not the "No definitions." message (that message is
only for the multi-file case).

**How:** The test clears `seq.definitions` on a synthetic spin echo
sequence and checks that the body equals
`markup._table(["Definition", "Value"], [])`.

**Assumptions:** pypulseq's `Sequence.definitions` is a plain dict that a
test can clear directly.

#### `test_definitions_card_for_two_sequences_unions_keys_in_first_seen_order`

**Checks:** With two sequences, the table has one column for each file and
one row for each definition key found in any file, in first-seen order,
with an empty cell where a file lacks the key.

**How:** The test builds two plain pypulseq sequences with different
definitions set ("Name" and "TR" on the first, "TR" and "FOV" on the
second, with "TR" set to a different value in each), calls
`definitions_card` with both, and checks that the header row names both
files, that the "Name" row is empty for the second file, the "FOV" row is
empty for the first, the "TR" row shows each file's own value, and that
"Name" and "TR" (first seen in the first file) appear before "FOV" (first
seen in the second).

**Assumptions:** None.

#### `test_definitions_card_for_two_sequences_with_no_definitions_shows_a_muted_message`

**Checks:** When no file has any definitions, `definitions_card` shows a
muted "No definitions." message instead of an empty table.

**How:** The test clears the definitions of two plain pypulseq sequences
and checks that the body equals `<p class="muted">No definitions.</p>`
exactly.

**Assumptions:** This is a design decision the plan leaves to this phase
(section 5, Phase 2, task 2.2); there is no vb-pulseq behavior to match.

#### `test_render_page_accepts_definitions_card`

**Checks:** `page.render_page` accepts a `Card` from `definitions_card` and
renders its title.

**How:** The test builds a definitions card for one sequence, renders it
with `page.render_page`, and checks that `<h2>Definitions</h2>` is in the
result.

**Assumptions:** None beyond `test_page.py`'s coverage of `render_page`.

### 2.7 RF exposure (`test_rf_exposure.py`)

`test_rf_exposure.py` tests `rf_exposure.py`: the RF exposure of a sequence,
calculated from the RF amplitudes only — the number of pulses, the peak B1,
∫B1² dt, B1+rms over the sequence, and the highest B1+rms in a window. With
`periodic=True` (the default), the sequence is taken as one period that
repeats. With `periodic=False`, the sequence plays once: the highest-window
search does not wrap past the end, and a sequence shorter than the window
uses the whole sequence as the window, recorded as the window's real length.

The tests use a train of 1 ms, 90° block pulses on the synthetic system
(`tests/synthetic.py`'s `SYSTEM`), each followed by a delay. One pulse has
B1 = (1/4 cycle) / 1 ms, converted to µT, and ∫B1² dt = B1² × 1 ms.

**Assumptions for the whole file:**

- The values do not depend on the scanner, the transmit coil or the patient.
  They are not SAR, and no test compares them with a SAR or B1+rms limit.
- Each RF sample counts at its start time for the window calculation.

#### `test_block_pulse_train`

**Checks:** For two pulses in 20 s, the number of pulses, duration, peak B1,
peak block, RF energy and B1+rms are correct.

**How:** The test makes two pulses, followed by delays of 3 s and 17 s. It
checks that there are 2 pulses, the duration is 20 s within 10 ms, the peak B1
is the B1 of one pulse, the peak is in block 1, the energy is twice the energy
of one pulse, B1+rms is √(energy / duration), and the window's real length is
the full 10 s window.

**Assumptions:**

- The duration also includes the pulses and their dead times, so it is a
  little more than 20 s. The 10 ms tolerance allows that.

#### `test_highest_window`

**Checks:** The highest 10 s window holds the right number of pulses, also
when the window wraps into the next repetition.

**How:** The test runs three cases with two pulses. For each, the B1+rms of
the highest window must be √(pulses in the window × energy of one pulse /
10 s):

- delays 3 s and 17 s: both pulses are in one window;
- delays 15 s and 5 s: the window from the second pulse wraps into the next
  repetition and holds the first pulse again, so 2 pulses;
- delays 11 s and 11 s: the pulses are more than 10 s apart both ways, so
  1 pulse.

**Assumptions:**

- The sequence repeats with no gap between repetitions.

#### `test_short_sequence_window`

**Checks:** For a sequence shorter than the window, the highest window holds
all the whole repetitions that fit, plus the pulse in the remaining part.

**How:** The test makes one pulse followed by a 0.3 s delay. 33 whole
repetitions fit in 10 s, and the remaining part (about 60 ms) can hold one
more pulse. The window B1+rms must be √(34 × energy of one pulse / 10 s), and
more than the B1+rms over the sequence.

**Assumptions:** None.

#### `test_no_rf`

**Checks:** A sequence without RF has zero pulses, no peak block, zero energy
and B1+rms, and a window whose real length is the full 10 s window.

**How:** The test makes a sequence with only a delay block
(`tests/synthetic.py`'s `empty_sequence`) and checks each value.

**Assumptions:** None.

#### `test_periodic_false_does_not_wrap`

**Checks:** With `periodic=False`, the highest-window search does not wrap
past the end of the sequence, so it finds fewer pulses than the periodic
search does for the same sequence.

**How:** The test makes two pulses with delays of 15 s and 5 s, the same
pattern `test_highest_window` uses for its wrap case. With `periodic=True`,
the highest 10 s window wraps into the next repetition and holds 2 pulses, as
in `test_highest_window`. With `periodic=False`, the sequence plays once: the
two pulses are 15 s apart in both directions within that one play, more than
the 10 s window, so the highest window holds only 1 pulse. The test checks
the B1+rms of the highest window against √(pulses in the window × energy of
one pulse / 10 s) for both cases, and that the window's real length is the
full 10 s in the `periodic=False` case.

**Assumptions:**

- The sequence's duration (about 20 s) is longer than the 10 s window, so the
  window is not the whole sequence.

#### `test_periodic_false_window_is_whole_sequence_when_shorter_than_window`

**Checks:** With `periodic=False` and a sequence shorter than the window, the
highest window is the whole sequence: its real length is the sequence
duration, and its B1+rms equals the plain (non-windowed) B1+rms.

**How:** The test makes one pulse followed by a 0.3 s delay, well under the
10 s window. It checks that the duration is less than the window, that the
window's real length equals the duration, that B1+rms equals √(energy of one
pulse / duration), and that the highest-window B1+rms equals the plain
B1+rms.

**Assumptions:** None.

#### `test_periodic_false_no_rf`

**Checks:** With `periodic=False`, a sequence without RF has zero pulses,
zero B1+rms in the highest window, and a window real length equal to the
sequence's own (zero-RF) duration.

**How:** The test makes a sequence with only a delay block
(`tests/synthetic.py`'s `empty_sequence`), calls `rf_exposure` with
`periodic=False`, and checks each value.

**Assumptions:** None.

### 2.8 RF exposure card (`test_rf_exposure_card.py`)

`test_rf_exposure_card.py` tests `cards/rf_exposure.py`. `rf_exposure_data`
gives `rf_exposure.rf_exposure` as a JSON-ready dict, in ms and µT, plus the
highest window's real length and whether the sequence is periodic.
`rf_exposure_card` builds the "RF exposure" `Card`: for one sequence, the
body is `_rf_exposure_html(rf_exposure_data(seq))`, a six-row table and its
note. For more than one sequence, the body has one table for each file,
named by its file name, then an "All files" table and note: peak B1 is the
maximum over the files, and B1+rms and the highest-window value treat the
files as played one after another with no gap, and, when `periodic=True`,
that concatenation repeated.

The tests use `tests/synthetic.py`'s `spin_echo_sequence`, `gre_sequence` and
`empty_sequence`.

**Assumptions for the whole file:**

- The card has no chart: its `data` and `script` are both `None`.

#### `test_rf_exposure_data_for_spin_echo`

**Checks:** For the synthetic spin echo sequence, the RF exposure data has 2
pulses, the peak B1 of the refocusing pulse in its own block, the sum of the
two pulses' energies, the B1+rms from that energy and duration, a 10 s
window (the default), and a highest-window B1+rms at least as large as the
plain B1+rms.

**How:** The test computes the excitation and refocusing pulses' B1 directly
from their flip angle and 1 ms duration (µT = (flip / 2π) / duration / γ),
independent of the library. It checks that the data has 2 pulses, the
duration matches pypulseq's own `Sequence.duration()`, the peak B1 is the
refocusing pulse's B1, the peak block is the block that pypulseq itself
reports as carrying the refocusing pulse, the energy is the sum of the two
pulses' ∫B1² dt, B1+rms is √(energy / duration), the window is 10 s and its
real length is 10 s (the sequence is much shorter), and the highest-window
B1+rms is at least the plain B1+rms (a window can include more than one
repetition of the short sequence).

**Assumptions:**

- The refocusing pulse (180°) has a higher peak B1 than the excitation pulse
  (90°), because both are 1 ms block pulses and B1 is proportional to the
  flip angle.

#### `test_report_has_rf_exposure_card`

**Checks:** The rendered page has the RF exposure card, with its title and
its six table rows, and the card itself has no chart data or script.

**How:** The test builds the card for one named sequence, checks that its
`data` and `script` are `None`, renders the page, cuts out the text from the
card's id to the end of the result, and checks for the title "RF exposure"
and the rows "RF pulses", "Peak B1 (µT)", "∫B1² dt over the sequence
(µT²·ms)", "Sequence duration (ms)", "B1+rms, sequence repeated (µT)" and
"B1+rms, highest 10 s window (µT)". This also checks that `render_page`
accepts the card.

**Assumptions:** None.

#### `test_rf_exposure_card_without_rf`

**Checks:** For a sequence without RF, the card's body is the "No RF
pulses." note, on its own and inside a rendered page.

**How:** The test builds the card for the synthetic sequence with only a
delay block, checks that the body equals the note exactly, and that the note
is in a rendered page.

**Assumptions:** None.

#### `test_rf_exposure_card_two_files`

**Checks:** For two named sequences, the card has one table for each file,
named by its file name, in file order, then an "All files" table whose peak
B1 is the maximum of the two files' peak B1, and whose note says the
sequence is repeated (because `periodic` defaults to `True`).

**How:** The test builds the card for a spin echo and a GRE sequence, checks
that both file names appear as headings before "All files", in that order,
computes each file's own peak B1 with `rf_exposure_data`, checks that the
"All files" table has the larger of the two as its peak B1, checks that
"sequence repeated" is in the "All files" section, and renders the page to
check that `render_page` accepts a multi-file card.

**Assumptions:** None.

#### `test_rf_exposure_card_two_files_not_periodic_omits_repeated_wording`

**Checks:** With `periodic=False`, the "All files" section does not say the
sequence is repeated, and says instead that the files play once.

**How:** The test builds the two-file card with `periodic=False` and checks
that "sequence repeated" is not in the "All files" section and that "files
played once" is.

**Assumptions:** None.

### 2.9 Gradient spectrum (`test_grad_spectrum.py`)

The spectrum is calculated as in pypulseq: 50 ms Hann windows with 50 %
overlap, the magnitude spectrum of each window, and the maximum over windows.
Here the gradients are sampled to the end of the sequence, with half a window
of zeros added at each end. The RSS spectrum is the root-sum-of-squares of the
three axes in each window, then the maximum over windows. The default
resonance bands, of the MAGNETOM Prisma AS82 gradient coil, are 590 ± 50 Hz
and 1140 ± 110 Hz. The gradients are sampled in chunks of `CHUNK_WINDOWS`
windows, so the memory does not grow with the sequence length. `combine` gives
the spectrum of several files.

Several tests use a 1 mT/m sine on x, on the synthetic system. On a frequency
bin, a Hann window gives an amplitude spectral density of
(A/2) × Σw / √(fs × Σw²). With 5000 samples at 100 kHz, that is the expected
peak for A = 1 mT/m.

**Assumptions for the whole file:**

- The resonance bands are published values for one Prisma gradient coil, not
  read from a scanner's `.asc` file.
- The test sine frequencies (300 Hz and 600 Hz) are exactly on frequency bins,
  and each window holds a whole number of cycles. So there is no scalloping
  loss, and the peak is the full value.
- The tests do not compare the result with vb-pulseq. Parity with vb-pulseq
  (rtol 1e-12, several chunk sizes) was checked outside CI when this module
  moved from vb-pulseq.

#### `test_prisma_as82_resonances`

**Checks:** The default resonance bands are 540–640 Hz and 1030–1250 Hz.

**How:** The test compares the low and high edge of each band in
`PRISMA_AS82_RESONANCES` with these values.

**Assumptions:** None.

#### `test_spin_echo_spectrum`

**Checks:** For the synthetic spin echo, the spectrum runs from 0 to 2 kHz,
the x and y axes have a non-zero spectrum, the RSS is at least each axis at
every frequency, and the largest RSS value in each band is inside that band.

**How:** The test calculates the spectrum of the synthetic spin echo. It
checks that there is no reason, that the frequencies start at 0 and end at
2 kHz, and that there are x, y and z spectra. The x and y spectra must have a
maximum above 0 (the synthetic spin echo has no z gradient). Each axis
spectrum must have the same length as the frequencies, and the RSS must be at
least that axis at every frequency. There must be a band peak for each
resonance, at a frequency inside the band, with a value relative to the
overall peak from 0 to 1.

**Assumptions:**

- The relative value can be 1 when the largest RSS value is inside a band.
  The test does not check the size of the value in a band.

#### `test_sine_in_the_first_band`

**Checks:** A 600 Hz sine gives an RSS peak at 600 Hz with the expected
amplitude, the first band holds the overall peak, and less than 5 % leaks into
the second band.

**How:** The test makes a 0.5 s, 1 mT/m, 600 Hz sine on x. The RSS peak must
be at 600 Hz, with a value within 1 % of the expected peak. The first band's
relative value must be 1. The second band's must be less than 0.05.

**Assumptions:**

- The windows that hold the abrupt start and end of the sine leak about 1 %
  into the second band.

#### `test_sine_outside_the_bands`

**Checks:** A 300 Hz sine puts less than 5 % of the peak in each band.

**How:** The test makes a 300 Hz sine and checks that both band values
relative to the peak are less than 0.05.

**Assumptions:**

- The abrupt start and end of the sine leak about 2 % into the bands.

#### `test_short_sequence_is_padded_to_one_window`

**Checks:** A sequence shorter than one window still has a spectrum, with its
peak at the sine frequency.

**How:** The test makes a 20 ms, 600 Hz sine. There must be no reason, and the
RSS peak must be within 20 Hz of 600 Hz.

**Assumptions:**

- A 20 ms sine has a wide spectral peak, so the tolerance is wider than one
  frequency bin.

#### `test_gradients_at_the_end_are_not_attenuated`

**Checks:** A sine at the end of the sequence has its full amplitude in the
spectrum.

**How:** The test makes a sequence with 440 ms of no gradient and then 60 ms
of a 600 Hz sine, so the last sample is at the end of the sequence. The RSS
peak must be within 2 % of the expected peak.

**Assumptions:**

- The sine is 60 ms long, so at least one 50 ms window is fully inside it and
  the full amplitude is expected. The test fails if the gradient samples near
  the end of the sequence are lost, or are only at the edge of a window.

#### `test_no_gradients`

**Checks:** A sequence without gradients has no spectrum, with the reason
"no gradients", and no band values.

**How:** The test makes a sequence with only a block pulse and checks the
reason and the band values.

**Assumptions:** None.

#### `test_chunks_give_the_same_spectrum_as_one_chunk`

**Checks:** The spectrum does not depend on the chunk size.

**How:** The test makes a synthetic GRE sequence of 30 TRs of 20 ms (600 ms,
25 windows). It calculates the spectrum with `CHUNK_WINDOWS` set to 1,000,000
(one chunk) and to 4 (7 chunks, the last one shorter). The frequencies must be
equal, and each axis spectrum and the RSS must agree with a relative tolerance
of 1e-12. The band peaks must be at the same frequencies.

**Assumptions:**

- The results are not always bit-for-bit equal, because scipy computes the
  FFTs of a different number of windows in each call. The tolerance allows for
  that rounding.

#### `test_combine_is_the_maximum_over_the_files`

**Checks:** The combined spectrum of two files is the element-wise maximum of
each axis and of the RSS, with the band peaks recomputed from the combined
RSS.

**How:** The test calculates the spectra of a 200 ms, 600 Hz sine and a
200 ms, 300 Hz sine and combines them. The frequencies must be those of the
files, and each axis and the RSS must be equal to the element-wise maximum.
The first band's peak must be at 600 Hz with the value of the 600 Hz file,
and its relative value must be that value divided by the combined RSS
maximum.

**Assumptions:**

- The windows that would cross from one file to the next are not in the
  combined spectrum. The test does not check them.

#### `test_combine_skips_files_without_gradients`

**Checks:** `combine` skips a file without gradients, gives "no gradients"
when no file has gradients, and raises for an empty list.

**How:** The test combines a file with only a delay block and a 100 ms sine:
the result must be the same as the sine's spectrum. It combines the file
without gradients alone: the reason must be "no gradients". Combining an empty
list must raise ValueError.

**Assumptions:** None.

### 2.10 Gradient spectrum card (`test_spectrum_card.py`)

`test_spectrum_card.py` tests `cards/spectrum.py`. `spectrum_data` gives the
gradient spectrum of one sequence (`grad_spectrum.gradient_spectrum`) as
JSON-ready data, in Hz and mT/m/√Hz; for the default resonances this is
exactly the vb-pulseq `spectrum_data(seq)` data. `spectrum_card` builds the
"Gradient spectrum" `Card`: for one sequence, the body is
`_spectrum_html(spectrum_data(seq, resonances), scanner_label, card_id)` — the
band table, the Linear/dB chart controls and the chart itself, or a note that
there is no spectrum. For more than one sequence, the data is the combined
spectrum (`grad_spectrum.combine`) of the files' own spectra, and the body
has an added note that the chart is the maximum over the files. `data` is
always the JSON-ready spectrum dict and `script` is always `"spectrum"`.

The tests use `tests/synthetic.py`'s `spin_echo_sequence`, `gre_sequence` and
`empty_sequence`.

#### `test_spectrum_data_for_spin_echo`

**Checks:** For the synthetic spin echo sequence, the spectrum data has the
two default resonances, lanes for Gx, Gy, Gz and RSS with one shared value
range from 0 Hz to the maximum frequency, and the two bands.

**How:** The test makes the spectrum data. It checks that there is no reason,
and that the resonances are 590 Hz (100 Hz wide) and 1140 Hz (220 Hz wide).
The lanes must be Gx, Gy, Gz and RSS. Each lane must have the unit mT/m/√Hz,
the same value range as the RSS lane, and one segment from 0 Hz to the
maximum frequency. The bands must be 540–640 Hz and 1030–1250 Hz.

**Assumptions:**

- One value range for all lanes makes the axes comparable. The RSS is the
  largest, so its range holds the others.

#### `test_report_has_gradient_spectrum_card`

**Checks:** The rendered page has the gradient spectrum card with the two
band rows, the chart, the Linear and dB buttons with Linear selected, and
the −80 dB note.

**How:** The test builds the card for one named sequence, renders the page,
cuts out the text from the card's id to the end of the result, and checks
for the title, the cells "540–640" and "1030–1250", the diagram element, the
two scale buttons with their pressed states, and "drawn at −80 dB".

**Assumptions:** None.

#### `test_report_without_gradients_has_no_spectrum_chart`

**Checks:** For a sequence without gradients, the card's body is the "No
gradient spectrum" note, on its own and inside a rendered page, and the page
has no spectrum diagram element.

**How:** The test builds the card for the synthetic sequence with only a
delay block, checks that the body equals the note "No gradient spectrum: no
gradients." exactly, and that the note is in a rendered page with no
`gradient-spectrum-diagram` id.

**Assumptions:** None.

#### `test_custom_scanner_label_and_resonances_appear`

**Checks:** A custom `scanner_label` and custom `resonances` change the
table header, the aria-label wording, the note's band text and gradient
coil wording, and the data's resonances and bands, in place of the default
Prisma wording and values.

**How:** The test builds the card with one custom resonance (700 Hz, 40 Hz
wide) and the label "Acme Scanner". It checks that the table header, the
aria-label phrase and the note's gradient-coil phrase all use "Acme
Scanner", that the note states "700 ± 20 Hz", that the data's `resonances`
list holds only the custom resonance, that the data's `bands` low/high
values are 680–720 Hz, and that they equal `spectrum_data`'s own bands for
the same sequence and resonances.

**Assumptions:** None.

#### `test_two_file_card_uses_combined_spectrum`

**Checks:** For two named sequences, the card's data equals
`_spectrum_data(combine(...))` of the two files' own spectra, and the body
states that the chart is the maximum over the files and that windows
crossing between files are not included.

**How:** The test builds the card for a spin echo and a GRE sequence,
computes the expected data directly from `gradient_spectrum` and `combine`,
and checks that the card's `data` equals it exactly and that the two note
phrases are in the body. It renders the page to check that `render_page`
accepts a multi-file card.

**Assumptions:** None.

#### `test_custom_card_id_changes_element_ids`

**Checks:** A non-default `card_id` changes the card id and every chart
element id, which all start with `card_id`.

**How:** The test builds the card with `card_id="spectrum-b"` and checks
that `card.id` is `"spectrum-b"` and that the body has the ids
`spectrum-b-chart`, `spectrum-b-diagram` and `spectrum-b-tip`, and the zoom
button group's `data-zoom-for="spectrum-b-diagram"`.

**Assumptions:** None.

#### `test_render_page_includes_spectrum_script_once`

**Checks:** `render_page` includes the `spectrum` card script once, even
when two spectrum cards (with different `card_id`s) are on the page.

**How:** The test builds two spectrum cards with different `card_id`s,
renders the page, and checks that the literal registration call
`PulseqReport.registerCard("spectrum"` appears exactly once in the result.

**Assumptions:**

- The literal `registerCard` call text is unique to
  `assets/cards/spectrum.js` and does not appear elsewhere in the rendered
  page.

### 2.11 PNS prediction (`test_pns.py`)

`test_pns.py` tests `pns.py`: the PNS prediction, which runs pypulseq's SAFE
model, and `peak_tr_window`, the start and end of the TR that holds the
prediction's peak, counted from the sequence start in steps of the TR
definition. Without a gradient `.asc` file, the prediction uses pypulseq's
example hardware, which is not a real scanner.

The real `.asc` files are confidential, so the tests write a test `.asc` file
with the PNS parameters of pypulseq's example hardware, with the
`write_gradient_asc` fixture at the top of this file. The stimulation limits
and thresholds in it can be multiplied by a scale factor. The test file can
also have the layout of a scanner file: a main file with an `ASCCONV` block,
CRLF line ends and the name in `asCOMP[0].tName`, which includes a
`_GSWD_SAFETY.asc` file with the PNS parameters under `GradPatSup.Phys.PNS`.

Most of the tests use the synthetic spin echo sequence
(`tests/synthetic.py`'s `spin_echo_sequence`). The `peak_tr_window` tests use
a three-TR sequence built in this file (`_three_trs`): three 50 ms TRs, each a
y trapezoid on the synthetic system and a delay, with a TR definition of
50 ms. One of the three TRs (the "peak TR") has a 0.1 ms rise and fall time,
against 0.4 ms for the others, so its faster slew rate gives it the highest
PNS.

**Assumptions for the whole file:**

- pypulseq's SAFE model is correct. No test compares it with a published
  result or with a scanner.
- No test uses the parameters of a real scanner. A PNS value for the
  synthetic sequences on the scanner is not tested.
- A faster slew rate gives a higher PNS prediction. The SAFE model is driven
  by the slew rate, so this is expected but not calculated in the tests.

#### `test_example_hardware_for_spin_echo`

**Checks:** For the synthetic spin echo sequence on the example hardware, the
prediction is below the stimulation limit, is highest on y, has one curve for
each axis, and has a peak time inside the sequence.

**How:** The test runs the prediction without an `.asc` file. It checks that
there is no reason, that the hardware is the example hardware, and that there
is no `.asc` file name. It checks that the axes are x, y and z, and that the
peak is more than 0 and less than 1 (100 % of the limit). The axis with the
highest peak must be y, where the crushers are. Each axis curve must have the
same length as the all-axes curve, and the all-axes curve must be at least
each axis curve at every time. The peak time must be inside the time range.

**Assumptions:**

- The all-axes value is the root-sum-of-squares of the axes, so it is at least
  each axis.
- "Below the limit" is for the example hardware only.
- The crushers (on y) give the synthetic sequence's highest per-axis PNS.
  This was checked against a direct run of the prediction, not derived by
  hand.

#### `test_asc_file_with_the_example_parameters`

**Checks:** An `.asc` file with the example hardware's parameters gives the
same prediction as the example hardware, and the file's hardware name and
file name.

**How:** The test writes a test `.asc` file with scale factor 1 and runs the
prediction with it. There must be no reason, the hardware name must be the
name in the file, and the file name must be the name of the file. The
all-axes curve must be equal to the example hardware curve within a relative
10⁻⁹.

**Assumptions:**

- The test file has only the fields that pypulseq's `.asc` reader needs for
  PNS. A real file has many more fields, in the same format.

#### `test_asc_file_that_includes_the_pns_parameters`

**Checks:** A main `.asc` file that includes the PNS parameters from a second
file with `$INCLUDE` gives the same prediction as the example hardware, and
the hardware name in `asCOMP[0].tName`.

**How:** The test writes a test `.asc` file with the scanner layout and scale
factor 1, and runs the prediction with the main file. There must be no reason,
the hardware name must be the name in the main file, and the file name must be
the name of the main file. The all-axes curve must be equal to the example
hardware curve within a relative 10⁻⁹.

**Assumptions:**

- The layout is the layout of the `MP_GradSys_K2309_2250V_951A_XR_AS82.asc`
  files from the XA60 IDEA installation: the `$INCLUDE` line names a file in
  the same directory, without quotes. Other software versions are not tested.

#### `test_asc_file_with_a_missing_include`

**Checks:** When a file that `$INCLUDE` names is not there, reading the `.asc`
file stops with an error that names both files.

**How:** The test writes a test `.asc` file with the scanner layout, deletes
the `_GSWD_SAFETY.asc` file, and reads the main file. It must raise
`FileNotFoundError` with a message that has the main file name and the
included file name.

**Assumptions:** None.

#### `test_included_fields_replace_fields_with_the_same_name`

**Checks:** The fields of an included file are merged into the fields of the
main file, and a field in both files gets the value of the included file.

**How:** The test writes a main file with `a.b[0] = 1`, `a.b[1] = 2`,
`c = "old"` and a `$INCLUDE` line, and an included file with `a.b[1] = 3` and
`c = "new"`. The fields read must be `a.b[0] = 1`, `a.b[1] = 3` and
`c = "new"`.

**Assumptions:**

- In the real files, the `$INCLUDE` line is the last field of the main file,
  so the included values are the last values, as in the file order. A field
  after a `$INCLUDE` line that is also in the included file is not tested.

#### `test_hardware_name`

**Checks:** The hardware name comes from `asCOMP[0].tName` (a scanner file) or
`asCOMP.tName`, and is "unknown" without either.

**How:** The test gives the name function the fields for each of the three
cases and checks the name.

**Assumptions:** None.

#### `test_prediction_scales_with_the_stimulation_limit`

**Checks:** A stimulation limit 10 times lower gives a prediction 10 times
higher, above the limit.

**How:** The test writes a test `.asc` file with scale factor 0.1 and runs the
prediction. The peak must be 10 times the example hardware peak within a
relative 10⁻⁹, and more than 1.

**Assumptions:**

- In the SAFE model, the prediction is inversely proportional to the
  stimulation limit.

#### `test_peak_time_is_the_first_sample_at_the_peak_within_rounding`

**Checks:** The peak time is the first sample within a relative 10⁻⁶ of the
peak, and a real, larger increase moves it.

**How:** The test makes a prediction by hand with five samples. Sample 1 is
0.5 × (1 − 10⁻¹²) and sample 3 is 0.5. The peak must be 0.5 and the peak time
must be sample 1. The test then sets sample 3 to 0.5 × (1 + 10⁻³). The peak
time must be sample 3.

**Assumptions:**

- Identical TRs give PNS values that differ only by rounding. The tolerance
  puts the peak in the first of them.

#### `test_no_gradients`

**Checks:** A sequence without gradients has no prediction, with the reason
"no gradients", a peak of 0 and no peak time.

**How:** The test makes the synthetic sequence with only a delay block
(`tests/synthetic.py`'s `empty_sequence`) and checks the reason, the hardware
name, the peak and the peak time.

**Assumptions:** None.

#### `test_peak_tr_window_finds_the_tr_with_the_peak`

**Checks:** For each position of the peak TR (first, second or third) in the
three-TR sequence, `peak_tr_window` returns that whole TR, and the
prediction's peak time is inside it.

**How:** For peak TR k = 0, 1 and 2, the test builds `_three_trs(k)`, runs the
prediction, and calls `peak_tr_window` with the peak time. The window must be
50k s to 50(k + 1) ms (converted to seconds), and the peak time must be
inside it.

**Assumptions:**

- TRs are counted from the start of the sequence, in steps of the TR
  definition.

#### `test_peak_tr_window_without_a_tr_definition_is_none`

**Checks:** Without a TR definition, `peak_tr_window` returns None.

**How:** The test builds the three-TR sequence, removes its TR definition,
runs the prediction, and calls `peak_tr_window` with the peak time. The
result must be None.

**Assumptions:** None.

#### `test_peak_tr_window_with_one_tr_is_none`

**Checks:** When the sequence is not longer than one TR, `peak_tr_window`
returns None.

**How:** The test takes the synthetic spin echo sequence, whose duration is
much less than a TR, and sets its TR definition to its own duration exactly.
`peak_tr_window` with any peak time must return None.

**Assumptions:** None.

#### `test_peak_tr_window_without_a_peak_time_is_none`

**Checks:** With no peak time (`None`), `peak_tr_window` returns None.

**How:** The test builds the three-TR sequence and calls `peak_tr_window`
with `peak_time_s=None`. The result must be None.

**Assumptions:** None.

### 2.12 PNS card (`test_pns_card.py`)

`test_pns_card.py` tests `cards/pns.py`. `pns_data` gives
`pns.pns_prediction` as a JSON-ready dict, in ms and percent of the
stimulation limit, with one lane for all axes and one for each of Gx, Gy and
Gz, and the start and end (ms) of the TR that holds the peak
(`pns.peak_tr_window`) when the sequence has a TR definition and more than
one TR. `pns_card` builds the "PNS prediction" `Card`, with that data, the
`_pns_html` body (the result, the table, the chart and its explanation, or a
note that there is no prediction, with "full sequence" and "peak TR" view
buttons when there is a TR to zoom to), and the `"pns"` script.

Most of the tests use the synthetic spin echo sequence
(`tests/synthetic.py`'s `spin_echo_sequence`) or the three-TR sequence built
in this file (`_three_trs`, the same sequence as in `test_pns.py`: three
50 ms TRs, one with a faster slew rate that gives it the highest PNS).

**Assumptions for the whole file:**

- The physics (the prediction itself and `peak_tr_window`) is `pns.py`'s,
  tested in `test_pns.py`. These tests check only that the card wires that
  physics into JSON data and HTML correctly.

#### `test_pns_data_for_spin_echo`

**Checks:** For the synthetic spin echo sequence, the PNS data uses the
example hardware, has a peak between 0 % and 100 % that is at least each axis
peak, has lanes for all axes, Gx, Gy and Gz in percent with a range of 0 % to
110 % and not too many points, draws the peak, ends at the last sample, and
has no TR zoom.

**How:** The test makes the PNS data. It checks that there is no reason, that
the example hardware is used with no `.asc` file, that the peak is more than
0 % and less than 100 %, and that it is at least each axis peak. The lanes
must be all axes, Gx, Gy and Gz. Each lane must be in percent, with a range of
0 % to 110 %, and have more than 0 and at most 100000 points. The highest
point of the all-axes lane must be the peak within 0.01 %, and its last point
must be at the end time. There must be no TR zoom range.

**Assumptions:**

- The range is 110 % of the larger of 100 % and the peak. For a peak below
  100 %, that is 0 % to 110 %.
- With one TR and no TR definition, there is nothing to zoom to.

#### `test_max_envelope_keeps_the_maximum_of_each_run`

**Checks:** Reducing a curve to at most 4000 points keeps its maximum and its
start time.

**How:** The test makes a curve of 10001 zeros with one value of 3 at sample
7777, and reduces it to at most 4000 points. The result must have at most
4000 points, the same number of times and values, a maximum of 3, and a first
time of 0.

**Assumptions:**

- Each point of the result is the maximum of a run of samples, at the time of
  the run's first sample. So a short peak is kept, but its time can move by up
  to one run.

#### `test_pns_data_zooms_to_the_tr_with_the_highest_pns`

**Checks:** For each position of the peak TR (first, second or third), the
PNS data's TR zoom range is that whole TR, and the peak time is inside it.

**How:** For peak TR k = 0, 1 and 2, the test makes the PNS data for
`_three_trs(k)`. The zoom range must be 50k ms to 50(k + 1) ms, and the peak
time must be inside it.

**Assumptions:**

- TRs are counted from the start of the sequence, in steps of the TR
  definition.

#### `test_pns_data_without_a_tr_definition_has_no_zoom`

**Checks:** Without a TR definition, the PNS data has no TR zoom.

**How:** The test makes the three-TR sequence, removes its TR definition, and
makes the PNS data. There must be no zoom range.

**Assumptions:** None.

#### `test_pns_lanes_keep_every_sample_above_the_floor`

**Checks:** A PNS lane keeps every raw sample whose value is above the zero
floor, and still has fewer points than the raw sequence has samples.

**How:** The test uses the three-TR sequence with the peak in the second TR.
It runs the PNS prediction directly and makes the PNS data. For each lane, it
takes the raw samples whose value is above the zero floor, rounded the same
way as the lane's own points. Every one of those rounded samples must be
among the lane's points, and the lane must have fewer points than the raw
sequence has samples.

**Assumptions:**

- The test checks only that the above-floor samples survive and that the lane
  has fewer points than the raw sequence. It does not check that the lane
  keeps exactly the points that the reduction is meant to keep, such as the
  neighbors of each above-floor sample or the ends of each zero run.
  `test_active_samples_keep_the_ends_of_zero_runs` checks that for the
  reduction function alone, with a short made-up curve.

#### `test_active_samples_keep_the_ends_of_zero_runs`

**Checks:** Reducing a PNS lane keeps the samples above the floor, their
neighbors, and the first and last sample, and drops the inside of each run at
or below the floor.

**How:** The test uses 10 samples with values 0, 0, 0, 1, 2, 0, 0, 0, 0, 0
and a floor of 0.01. The kept samples must be 0, 2, 3, 4, 5 and 9, with
values 0, 0, 1, 2, 0 and 0.

**Assumptions:**

- A run at or below the floor is drawn as a straight line between its ends,
  so dropping its inside does not change the chart.

#### `test_report_has_peak_tr_buttons`

**Checks:** For the three-TR sequence with the peak in the second TR, the
card has a "Full sequence" button that is selected and a "TR with the highest
PNS (50–100 ms)" button that is not, and the note on how TRs are counted.

**How:** The test builds the card and checks its body for the full-sequence
button, selected, the zoom button, not selected, and the text "counted from
the sequence start in steps of the TR definition".

**Assumptions:** None beyond the file's assumptions.

#### `test_report_has_pns_card`

**Checks:** For the synthetic spin echo sequence, the card has the id
`"pns"`, the title "PNS prediction" and the script name `"pns"`; its body has
the below-limit result, the example hardware warning, the hardware and peak
rows, and the chart, and no zoom buttons (one TR, no TR definition); and
`render_page` accepts it, with the title and the id that the script and the
data element key on.

**How:** The test builds the card and checks its `id`, `title` and `script`.
It checks the body for the title, "is below the 100 % limit", "Example
hardware, not a real scanner.", a cell with the example hardware name, the
rows for the peak of all axes, Gx, Gy and Gz, and the chart element, and that
the body has no PNS zoom buttons. It renders the page and checks for the
section element with the card's id and script, and the title.

**Assumptions:**

- "Below the limit" is for the example hardware only.

#### `test_report_without_gradients_has_no_pns_chart`

**Checks:** For a sequence without gradients, the card says that there is no
PNS prediction and has no PNS chart, on its own and inside a rendered page.

**How:** The test builds the card for the synthetic sequence with only a
delay block and renders the page. It checks for the note "No PNS prediction:
no gradients." and that there is no PNS chart element.

**Assumptions:** None.

#### `test_card_ids_start_with_card_id`

**Checks:** With a non-default `card_id`, every id in the card's body (the
chart, the SVG, the tip and the zoom button group's `data-zoom-for`) starts
with that `card_id`, so two PNS cards can be on one page.

**How:** The test builds the card with `card_id="pns-b"` and checks that the
card's own id is `"pns-b"`, its script is still `"pns"`, and that
`"pns-b-diagram"`, `"pns-b-chart"` and `"pns-b-tip"` each appear as an
element id, and `"pns-b-diagram"` appears as `data-zoom-for`. It then removes
every occurrence of `"pns-b-diagram"` from the body and checks that
`"pns-diagram"` (the default card id's chart id) does not appear, so no id
from the default `card_id` leaked in.

**Assumptions:** None.

#### `test_render_page_includes_pns_script_once`

**Checks:** `render_page` includes the `pns` card script exactly one time.

**How:** The test builds the card, renders a page with it, and checks that
the page's text has exactly one copy of `page.card_asset("pns")`.

**Assumptions:** None.

### 2.13 Gradient limits (`test_grad_limits.py`)

`test_grad_limits.py` tests `grad_limits.py`: the peak amplitude, the peak slew
rate and the RMS amplitude of a sequence's gradients, on each logical axis and
as a three-axis vector, over the whole sequence or over a window. Every
expected value is computed by hand from the parameters of the trapezoid or
arbitrary gradient that the test builds, not by calling `gradient_limits`
itself for the expected value.

#### `test_trapezoid_peak_slew_and_rms_match_hand_computed_values`

**Checks:** For a single x trapezoid, `gradient_limits` gives the peak
amplitude, the peak slew rate and the RMS amplitude that hand computation from
the trapezoid's own rise time, flat time and amplitude predicts.

**How:** The test builds one block with an x trapezoid of a given amplitude,
rise time and flat time, and calls `gradient_limits` on it. It computes the
expected peak as the amplitude in mT/m, the expected slew as the amplitude
divided by the rise time in T/m/s, and the expected RMS from the energy of the
two ramps (each `amplitude^2 * rise_time / 3`) plus the flat top
(`amplitude^2 * flat_time`), divided by the block's duration and square
rooted. It checks that the x axis result matches each expected value, that
`reason` is None, and that the peak and the slew are attributed to the
trapezoid's own block ID.

**Assumptions:**

- The trapezoid's `fall_time` equals its `rise_time`, which is
  `pp.make_trapezoid`'s default when only `rise_time` is given.

#### `test_same_trapezoid_on_x_and_y_gives_vector_peak_root_2_times_axis_peak`

**Checks:** The same trapezoid, played on x and on y at the same time, gives a
vector peak that is the axis peak times the square root of 2.

**How:** The test builds one block with the same trapezoid on x and on y, and
calls `gradient_limits`. Because Gx equals Gy at every point, `|G|` is
`sqrt(2)` times `|Gx|` at every point, and so at the peak. It checks that the
vector peak equals the x axis peak times `sqrt(2)`, and that the x and y axis
peaks are equal.

**Assumptions:** None.

#### `test_window_that_cuts_a_ramp_gives_hand_computed_rms`

**Checks:** A window that ends partway up a trapezoid's rising ramp gives an
RMS amplitude equal to the value hand-computed from the piece that the window
keeps, cut at the window edge.

**How:** The test builds one block with an x trapezoid and a window from 0 to
half the rise time. It computes the expected RMS from the one linear piece the
window keeps, from `(0, 0)` to `(rise_time / 2, amplitude / 2)`, with
`Delta t * (a^2 + a*b + b^2) / 3` divided by the window length. It checks that
`range_s` equals the window and that the x axis RMS matches.

**Assumptions:** None.

#### `test_arbitrary_gradient_peak_is_the_largest_of_first_last_and_waveform`

**Checks:** For an arbitrary gradient, the peak amplitude is the largest
absolute value among the shape's `first`, `last` and interior waveform
samples.

**How:** The test builds an x arbitrary gradient from an asymmetric sine-lobe
waveform, whose largest magnitude is not at the shape's first or last sample,
and calls `gradient_limits`. It computes the expected peak as the largest of
`abs(first)`, `abs(last)` and the largest absolute waveform sample, taken from
the block's own gradient event, converted to mT/m. It checks that the x axis
peak matches.

**Assumptions:**

- `seq_utils.gradient_points` adds `first` and `last` as extra points at the
  ends of an arbitrary gradient's shape (checked by `test_gradient_points_arbitrary`
  in `test_seq_utils.py`), so they can hold the largest magnitude even when
  every interior waveform sample is smaller.

#### `test_no_gradients_sets_reason`

**Checks:** A sequence with no gradient events at all gives a set `reason`,
and every numeric field is its zero value: 0.0 for an amplitude, slew or RMS
field, and None for a block field.

**How:** The test builds a sequence with one delay block and no gradients, and
calls `gradient_limits`. It checks that `reason` is
"no gradient events in the sequence", that the vector peak and its time are
0.0, and that every axis's peak, slew and RMS are 0.0 with `peak_block` and
`slew_block` both None.

**Assumptions:** None.

#### `test_default_limits_come_from_seq_system`

**Checks:** With `limits=None`, the limits are `seq.system.max_grad` and
`seq.system.max_slew`, converted to mT/m and T/m/s, with the label
"pypulseq system limits".

**How:** The test builds a sequence with one x trapezoid and calls
`gradient_limits` with no `limits` argument. It checks that the result's
`limits.label` is "pypulseq system limits", and that `max_grad_mt_per_m` and
`max_slew_t_per_m_per_s` equal `seq.system.max_grad` and `seq.system.max_slew`
converted with the gyromagnetic ratio, the same conversion the function itself
documents.

**Assumptions:**

- `seq.system.max_grad` and `seq.system.max_slew` are always in Hz/m and
  Hz/m/s, whatever unit was given to `pp.Opts`, because `pp.Opts` converts to
  Hz/m (respectively Hz/m/s) before it stores the value. This is a fact about
  pypulseq, not about the function under test, and is not itself checked here.

### 2.14 Gradient limits card (`test_gradient_limits_card.py`)

`test_gradient_limits_card.py` tests `cards/gradient_limits.py`: the "Gradient
limits" table (Gx, Gy, Gz and |G| rows, with the peak, its percent of the
limit, the max slew, its percent, and the RMS), one row group for each file
when there is more than one, and the extra RMS column when a window is given.
Every expected numeric cell is computed by hand from the trapezoid the test
builds, using the same formulas as `test_grad_limits.py`, and compared through
`markup._table`, so a test also fixes the exact table that `_table` would
render from those rows.

#### `test_single_file_table_has_axis_rows_and_percents`

**Checks:** For one file with a single x trapezoid, the card's table has no
"File" column, and its Gx, Gy, Gz and |G| rows hold the hand-computed peak,
percent of the limit, max slew, its percent, and RMS, with "—" for the
max slew of |G| and its percent. The |G| RMS equals the Gx RMS, because only x
has a gradient.

**How:** The test builds one file with an x trapezoid, computes the expected
peak, slew and RMS from the trapezoid's parameters (as in
`test_trapezoid_peak_slew_and_rms_match_hand_computed_values`) and their
percents of `SYSTEM.max_grad` and `SYSTEM.max_slew`, and builds the expected
table HTML with `markup._table` from the hand-computed rows. It calls
`gradient_limits_card` and checks that the card's `id`, `title`, `data` and
`script`, and that its body starts with the expected table HTML.

**Assumptions:** None.

#### `test_two_files_have_one_row_group_each_with_file_names`

**Checks:** With two files, the table has a leading "File" column, each
file's name on the first of its four rows and blank on the other three, and a
file name with an HTML special character is escaped.

**How:** The test builds two files, each with a single x trapezoid of a
different amplitude, computes the hand-computed rows for each as in the
single-file test, and builds the expected table HTML with `markup._table`,
with the first file's name (which contains `&`) on the first row of its group
and the second file's name on the first row of its group. It checks that the
card's body starts with the expected table HTML, and that the escaped form of
the first file's name is in the body.

**Assumptions:** None.

#### `test_window_gives_rms_over_window_and_over_whole_file`

**Checks:** With a window, the table has two RMS columns, "RMS over window"
and "RMS over whole file", and the peak and the slew columns are over the
window.

**How:** The test builds one file with an x trapezoid and a window equal to
the rising ramp. It computes the expected peak, slew and window RMS from the
ramp alone (RMS from `amplitude^2 * rise_time / 3` divided by the window
length), and the expected whole-file RMS as in the single-file test. It builds
the expected table HTML with `markup._table` from these hand-computed rows,
with both RMS columns, and checks that the card's body starts with it.

**Assumptions:** None.

#### `test_no_gradients_adds_a_reason_note`

**Checks:** A file with no gradient events gets a muted note in the card that
names the file and the reason.

**How:** The test builds a file with a delay block only, calls
`gradient_limits_card`, and checks that the body contains
"empty.seq: no gradient events in the sequence.".

**Assumptions:** None.

#### `test_render_page_accepts_gradient_limits_card`

**Checks:** `render_page` accepts the card that `gradient_limits_card`
returns.

**How:** The test builds a card from one file with a trapezoid, calls
`render_page` with it, and checks that the card's section and its `<h2>`
title are in the result.

**Assumptions:** None.

### 2.15 Waveform data (`test_waveforms.py`)

`test_waveforms.py` tests `waveforms.py`: the exact chart lanes
(`file_lanes`), the minimum/maximum envelope (`file_envelope`), the point
count without building the lanes (`point_count`), the block table rows
(`block_rows`), and the two named views `first_adc_window` and
`full_window`. The lane and block-table tests are adapted from vb-pulseq's
`test_spin_echo_lanes`, `test_block_table`,
`test_zero_phase_rf_and_zero_gradient_are_events` and its `report_at_tr`
tests, moved to `tests/synthetic.py` sequences and to the module's own
functions in place of vb's `sequence_data` dict; the PNS, page and
timing-check parts of those vb tests belong to other cards and are dropped.
The rest of the file is new coverage for a range that cuts a block, the
envelope, `point_count`, and the two named views.

#### `test_spin_echo_lanes`

**Checks:** For a synthetic spin echo sequence, `file_lanes` gives Gx and Gy
events within the system's gradient limit, an empty Gz lane (the sequence
uses block pulses, so there is no slice-select gradient), one ADC window as
long as the readout's own sample count times its dwell time, two RF phase
segments (one for each pulse), and a first-ADC window that ends after that
ADC window.

**How:** The test builds `synthetic.spin_echo_sequence()` once (a module
fixture, `spin_echo`) and calls `file_lanes` on it. For Gx and Gy, it checks
that the lane is not empty and that no value is above the system's
`max_grad` converted to mT/m. It checks that there is one ADC window whose
length matches `NUM_SAMPLES * DWELL` in ms, that the RF phase lane has two
segments, and that `first_adc_window`'s end is after the ADC window's end.

**Assumptions:**

- The synthetic spin echo sequence's block pulses have no slice-select
  gradient, so Gz has no events (unlike vb-pulseq's own spin echo, which
  used slice-selective pulses and so had Gz events too).

#### `test_block_table`

**Checks:** The block table lists the excitation first, has a refocusing
pulse of its own with no gradient in the same block, two crusher blocks with
a Gy trapezoid, and a readout block with a Gx trapezoid and the ADC's sample
count.

**How:** The test calls `block_rows` on the `spin_echo` fixture's sequence
and reads the `events` text of each row. The first must be exactly
"RF (excitation)". One row must be exactly "RF (refocusing)". Exactly two
rows must be "Gy trap" (the two crushers). One row must have "Gx trap" and
`f"ADC {NUM_SAMPLES} × "`.

**Assumptions:**

- Unlike vb-pulseq's spin echo, the synthetic sequence's refocusing pulse
  and its crusher gradients are in separate blocks, so the refocusing row
  has no gradient text and there is no trailing delay block to check.

#### `test_zero_phase_rf_and_zero_gradient_are_events`

**Checks:** An RF pulse with zero phase and a gradient with zero amplitude
count as events in their lanes, and an axis with no gradient does not.

**How:** The test plays a block pulse with a zero-amplitude trapezoid on x
and calls `file_lanes`. The RF phase lane and the Gx lane must not be empty.
The Gy lane must be empty.

**Assumptions:**

- A lane is empty when there is no event, not when the values are zero.

#### `test_multi_tr_lanes_span_the_whole_sequence`

**Checks:** For a synthetic multi-TR gradient echo sequence, the RF
magnitude and gradient lanes each cover the whole file in one segment from 0
to the end, and each of the ADC windows (one for each TR) falls inside its
own TR.

**How:** The test builds `synthetic.gre_sequence(num_trs=10, tr=20e-3)` and
calls `file_lanes`. For RF magnitude, Gx, Gy and Gz, the one segment must
start at 0 and end at the file's duration in ms. There must be one ADC
window for each TR, and window k must start after `k * tr_ms` and end
before `(k + 1) * tr_ms`, where `tr_ms` is the file duration divided by the
number of TRs.

**Assumptions:**

- Every TR of `gre_sequence` has the same real duration, so dividing the
  file's total duration by the TR count gives the true TR period even when
  it differs from the nominal `tr` argument (for example when the blocks
  do not leave room for a padding delay).
- Adapted from vb-pulseq's `test_report_at_tr_plots_the_whole_sequence`,
  with a synthetic gradient echo sequence in place of vb's spin echo, and
  keeping only the parts about lanes and durations; the PNS, page and
  timing-check parts belong to other cards.

#### `test_multi_tr_excitations_start_every_tr`

**Checks:** In the block table of a multi-TR file, the excitation blocks
start at exact multiples of the real TR period.

**How:** The test builds the same `gre_sequence(num_trs=10, tr=20e-3)` and
calls `block_rows`. It takes the start time of each row whose `events` text
starts with "RF (excitation)" and checks that the list equals
`[0, tr_ms, 2 * tr_ms, ...]` within 1 µs, where `tr_ms` is the file
duration divided by the number of TRs.

**Assumptions:**

- Adapted from vb-pulseq's `test_report_at_tr_excitations_start_every_tr`.

#### `test_range_that_cuts_a_block_includes_it_whole_and_pads_at_its_own_edges`

**Checks:** A range whose edges fall inside blocks still includes each such
block whole, and the zero pad point at each end of a joined line lane is at
the included block's own start or end, not at the range's requested edge.

**How:** The test builds a synthetic spin echo sequence and, from
`seq_utils.iter_blocks`, takes the RF refocusing block and the Gy crusher
block right after it. It calls `file_lanes` with a range that starts inside
the RF block and ends inside the crusher block. It checks that the RF
magnitude lane's first point is at the RF block's own start (earlier than
the range's requested start) with value 0, and that the Gy lane's last point
is at the crusher block's own end (later than the range's requested end)
with value 0.

**Assumptions:** None.

#### `test_point_count_matches_file_lanes_point_count`

**Checks:** `point_count`, computed without building the lanes, equals the
total number of points that `file_lanes` gives over all its lanes, both for
the whole file and for a range: each line lane's segment points, plus 2 for
each ADC window.

**How:** The test builds a synthetic gradient echo sequence and, for
`(start_s, end_s)` equal to `(None, None)` and to a quarter-to-60%-of-file
range, computes the expected count directly from `file_lanes`'s own output
(summing segment lengths of the line lanes and adding 2 for each ADC
window) and compares it with `point_count`'s result.

**Assumptions:** None.

#### `test_envelope_bin_min_and_max_match_dense_interpolation`

**Checks:** Each envelope bin's minimum and maximum match the true minimum
and maximum of the exact waveform in that bin.

**How:** The test builds a synthetic gradient echo sequence, computes
`file_lanes` and `file_envelope` for the same 40 bins, and for each line
lane and each bin, builds a dense `numpy.interp` of the exact lane's
segment: 2000 evenly spaced samples across the bin, plus the segment's own
vertex times that fall inside the bin (added explicitly, because a narrow
spike such as a trapezoid with no flat top reaches its peak at a single
instant that an evenly spaced grid alone can miss). It checks that the
envelope's minimum and maximum for that bin match the dense sample's
minimum and maximum within 2e-4.

**Assumptions:**

- Outside a segment's own time range, `numpy.interp`'s zero fill matches
  `file_envelope`'s treatment of time that no event covers.

#### `test_envelope_merges_adc_windows_closer_than_one_bin`

**Checks:** ADC windows closer together than one bin's width merge into
one envelope window that spans from the first window's start to the last
window's end, and the ADC lane's `note` says so.

**How:** The test builds a synthetic gradient echo sequence with three TRs
and a short TR (8 ms), so that the gap between any two of its three ADC
windows is smaller than the width of a single bin covering the whole file.
It calls `file_envelope` with `bins=1` and checks that the ADC lane has one
window, from the first exact window's start to the last exact window's end,
and that its `note` mentions "merged".

**Assumptions:** None.

#### `test_envelope_drops_rf_phase_and_has_note_fields`

**Checks:** `file_envelope` has no RF phase lane, its RF magnitude lane's
note says that RF phase is not shown, its other line lanes' notes describe
the bins without mentioning RF phase, and the ADC lane's note mentions that
windows are merged.

**How:** The test builds a synthetic gradient echo sequence and calls
`file_envelope`. It checks that the lane ids are exactly `rf_mag`, `adc`,
`gx`, `gy` and `gz` (no `rf_phase`), that the `rf_mag` lane's `note` mentions
that RF phase is not shown, that each of `gx`, `gy` and `gz`'s `note`
mentions "Minimum and maximum" but not RF phase, and that the `adc` lane's
`note` mentions "merged".

**Assumptions:** None.

#### `test_first_adc_window_label_and_times`

**Checks:** `first_adc_window` gives a window from 0 to 1.1 times the end of
the first ADC window (or the file's own end, if that is shorter), with a
label that names that end time.

**How:** The test builds a synthetic gradient echo sequence with a short TR,
reads the first exact ADC window's end from `file_lanes`, computes the
expected end as `min(duration_ms, 1.1 * first_window_end_ms)` rounded the
same way the function documents, and checks `first_adc_window`'s `file_index`,
`start_s`, `end_s` and `label` against it.

**Assumptions:** None.

#### `test_first_adc_window_with_no_adc_is_the_whole_file`

**Checks:** For a sequence with no ADC event, `first_adc_window` gives the
whole file.

**How:** The test builds a sequence with one delay block only and checks
that `first_adc_window`'s end and label both use the file's own duration.

**Assumptions:** None.

#### `test_full_window_label_and_times`

**Checks:** `full_window` gives a window from 0 to the end of the file, with
a label that names the duration.

**How:** The test builds a synthetic gradient echo sequence and checks
`full_window`'s `file_index`, `start_s`, `end_s` and `label` against the
file's own duration.

**Assumptions:** None.

#### `test_block_rows_with_max_rows_and_range`

**Checks:** `max_rows` caps the number of rows that `block_rows` returns
while `total` still counts every block, both over the whole file and over a
range, and a range keeps only the blocks that overlap it.

**How:** The test builds a synthetic gradient echo sequence with five TRs.
It checks that `max_rows=3` returns the first three of the unlimited rows
with the same `total`. It then picks a range equal to one TR (a fifth of
the file) and checks that its `total` is less than the whole file's, and
that `max_rows=2` over that range returns the first two of the range's own
unlimited rows with the same `total`.

**Assumptions:** None.

### 2.16 Sequence diagram card (`test_diagram_card.py`)

`test_diagram_card.py` tests `cards/diagram.py`. `diagram_card` builds one
button for each caller-given time window, sharing one lane set across the
windows of a small file (parity with vb-pulseq) and giving a file over the
point budget its own lane set (exact or an envelope) for each window. The
last test is adapted from vb-pulseq's
`test_report_has_zoom_controls_on_each_line_chart`, checking only the
diagram card because phases 4 (gradient spectrum) and 5 (PNS) are not
merged into this branch.

#### `test_small_file_has_one_lane_set_with_the_file_extent`

**Checks:** For a file within the point budget, `diagram_card`'s data has
one lane set, not an envelope, with the extent of the whole file, and every
window points to it with the given view.

**How:** The test builds a synthetic spin echo sequence and calls
`diagram_card` with its `first_adc_window` and `full_window`. It checks that
`data["lane_sets"]` has one entry, that its `envelope` is `False` and its
`extent_ms` is `[0.0, duration_ms]`, that every window's `lane_set` is 0, and
that each window's `view_ms` matches the given `TimeWindow`'s start and end
in ms.

**Assumptions:** None.

#### `test_over_budget_file_gets_one_lane_set_per_window`

**Checks:** A file over `point_budget` gets an envelope lane set for a
window equal to the whole file (extent the whole file), and an exact lane
set for a short window within the budget (extent equal to that window).

**How:** The test builds a synthetic multi-TR gradient echo sequence, picks
a `point_budget` below the whole file's `point_count` but above one TR's
`point_count`, and calls `diagram_card` with `full_window` and a one-TR
`TimeWindow`. It checks that there are two lane sets, that the full window's
lane set has `envelope=True` and the whole file's extent, and that the short
window's lane set has `envelope=False` and the window's own extent.

**Assumptions:** None.

#### `test_two_files_prefix_button_text_with_the_file_name`

**Checks:** With two files, each button's text starts with its file's name.

**How:** The test builds two named sequences and one `full_window` for
each, calls `diagram_card`, and checks that `"a.seq: Full sequence"` and
`"b.seq: Full sequence"` both appear in `body_html`.

**Assumptions:** None.

#### `test_ids_start_with_the_given_card_id`

**Checks:** With a non-default `card_id`, the card's own id and the ids of
its SVG, chart and tooltip elements all start with it.

**How:** The test calls `diagram_card` with `card_id="my-diagram"` and
checks that `card.id` is `"my-diagram"` and that `body_html` has
`id="my-diagram-diagram"`, `id="my-diagram-chart"` and
`id="my-diagram-tip"`.

**Assumptions:** None.

#### `test_no_windows_raises`

**Checks:** `diagram_card` raises `ValueError` when `windows` is empty.

**How:** The test calls `diagram_card` with an empty list of windows and
expects `ValueError`.

**Assumptions:** None.

#### `test_bad_file_index_raises`

**Checks:** `diagram_card` raises `ValueError` when a window names a file
index outside the given sequences.

**How:** The test calls `diagram_card` with one sequence and a `TimeWindow`
whose `file_index` is 1 and expects `ValueError`.

**Assumptions:** None.

#### `test_end_before_start_raises`

**Checks:** `diagram_card` raises `ValueError` when a window's end is not
after its start.

**How:** The test calls `diagram_card` with a `TimeWindow` whose `end_s` is
before its `start_s` and expects `ValueError`.

**Assumptions:** None.

#### `test_render_page_includes_diagram_script_once`

**Checks:** `render_page` includes the diagram card script exactly once.

**How:** The test builds a diagram card, renders it with `render_page`, and
checks that the page has exactly one
`PulseqReport.registerCard("diagram"` call.

**Assumptions:** None.

#### `test_diagram_card_has_zoom_controls_before_its_chart_and_the_help_sentence_once`

**Checks:** The rendered page has the zoom button group directly before the
diagram's `<div class="chart">`, and the zoom and pan help text exactly
once.

**How:** Adapted from vb-pulseq's
`test_report_has_zoom_controls_on_each_line_chart`, checking only the
diagram card because phases 4 and 5 are not merged into this branch. The
test builds a diagram card and renders it. It checks that
`markup._zoom_controls("diagram-diagram")` appears exactly once, that the
text right after it (skipping one newline) starts with
`<div class="chart"` and has `id="diagram-diagram"` within its first 400
characters, and that the zoom and pan help sentence ("Click the chart to
mark the centre for the zoom buttons. Drag across the chart to zoom to that
range. Hold Shift and drag, or scroll sideways, to pan.") appears exactly
once.

**Assumptions:** None beyond the file's assumptions.

### 2.17 Block table card (`test_blocks_card.py`)

`test_blocks_card.py` tests `cards/blocks.py`. `blocks_card` builds a
collapsed "Blocks (table view)" card from `waveforms.block_rows`: the first
`max_rows` blocks of each file when there are no windows (vb-pulseq's own
note and table for one file, parity), or one table for each window when
`windows` is given. Every expected table in this file is built with
`markup._table`, the same helper the card itself uses, from the rows that
`block_rows` gives directly, so a test also fixes the exact table that
`_table` would render from those rows.

#### `test_one_file_note_and_table_match_vb_parity_when_rows_are_cut`

**Checks:** For one file with more blocks than `max_rows`, `body_html`
equals vb-pulseq's own `__BLOCK_NOTE__` + "\n" + `__BLOCKS__` text (the "First
N of M blocks." note followed directly by the table), and the card's other
fields are correct.

**How:** The test builds a synthetic gradient echo sequence with more
blocks than a small `max_rows`, calls `blocks_card`, and separately calls
`block_rows` with the same `max_rows` to get the expected rows and total. It
builds the expected note text and the expected table with `markup._table`,
and checks that `body_html` equals the note, a newline, and the table,
exactly. It also checks `id`, `title`, `collapsed`, `data` and `script`.

**Assumptions:** None.

#### `test_no_note_when_all_rows_fit`

**Checks:** When every block fits under `max_rows`, the card has no "First N
of M blocks." note.

**How:** The test builds a small sequence, calls `blocks_card` with the
default `max_rows`, and checks that `body_html` equals a newline followed by
the expected table (built with `markup._table`), and that the text "muted"
(the note's CSS class) is absent.

**Assumptions:** None.

#### `test_two_files_have_an_h3_with_each_escaped_file_name`

**Checks:** With more than one file and no windows, each file's table is
headed by an `<h3>` with the file's own name, HTML-escaped, in the given
order.

**How:** The test builds two named sequences, one with a name that has an
HTML special character, calls `blocks_card` with both, and checks that the
escaped and the plain `<h3>` headings are both present and in the given
order.

**Assumptions:** None.

#### `test_windows_give_one_table_each_headed_by_the_window_label`

**Checks:** With `windows` given, the card has exactly one table for each
window, headed by an `<h3>` with the window's label, holding the blocks that
overlap it.

**How:** The test builds a synthetic multi-TR sequence and one `TimeWindow`
for each TR, calls `blocks_card` with them, and checks that `body_html` has
exactly as many `<h3>` elements as windows, that each window's label
appears in its own heading, and that the expected table for that window's
own range (from `block_rows` and `markup._table`) appears in the body.

**Assumptions:** None.

#### `test_windows_with_two_files_prefix_the_heading_with_the_file_name`

**Checks:** With `windows` and more than one file, each heading has the
file's name before the window's label, in the same "name: label" format as
`cards.diagram.diagram_card`'s buttons.

**How:** The test builds two named sequences, one `TimeWindow` for each
(naming its own `file_index`), calls `blocks_card` with both, and checks
that both `"<h3>a.seq: TR 0</h3>"` and `"<h3>b.seq: TR 0</h3>"` are present.

**Assumptions:** None.

#### `test_windows_note_when_a_window_has_more_blocks_than_max_rows`

**Checks:** A window whose own block count is over `max_rows` gets the
"First N of M blocks." note, with that window's own total.

**How:** The test builds a sequence and a window equal to the whole file, a
small `max_rows`, and checks that `block_rows` for that window already has a
total over `max_rows` before calling `blocks_card`. It then calls
`blocks_card` with that window and `max_rows`, and checks that the note
names the window's own total.

**Assumptions:** None.

#### `test_render_page_accepts_blocks_card`

**Checks:** `render_page` accepts the card that `blocks_card` returns.

**How:** The test builds a blocks card, renders it with `render_page`, and
checks that `<summary>Blocks (table view)</summary>` is in the result.

**Assumptions:** None.

### 2.18 Diagram tables (`test_diagram_data.py`)

`test_diagram_data.py` tests `diagram_data.py`: the compact per-file tables
(`diagram_tables`), their gzip+base64 wire form (`encode_tables`,
`decode_tables`), and the lane metadata built from the tables instead of the
expanded points (`lane_meta`). `waveforms.file_lanes` and
`waveforms._events_in_range` are the reference (section 3.5 of
`docs/plans/diagram-event-table.md`): the module must give the same numbers,
because a later phase rebuilds these same numbers in JavaScript and a golden
test there compares them with `==` and no tolerance. Most of these tests
therefore compare with `numpy.array_equal` rather than `pytest.approx`.

#### `test_rebuilt_polylines_exactly_match_events_in_range`

**Checks:** For a synthetic spin echo, gradient echo, arbitrary-gradient and
empty sequence, rebuilding each lane's whole-file polyline from the decoded
tables with the section 4.3 time formulas gives exactly the same points,
bit for bit, as `waveforms._events_in_range(seq, None, None)`'s own unrounded
per-block arrays.

**How:** A module helper, `_rebuild_lane_polylines`, walks the decoded
tables block by block: it rebuilds each block's start time from the
checkpoints and durations (`_block_starts`, section 4.3: `checkpoints[c]`
plus one duration at a time up to the block), then each event's points as
`(block start + event delay) + the event's own offset`, reading the event's
slice out of its pool with its `*_at` and `*_n` entries. This is independent
of `waveforms.py`, so it is a real check of the tables' content, not a
tautology. A second helper, `_reference_lane_polylines`, concatenates the
same six lanes' points directly from `_events_in_range`'s per-block
`_BlockEvents`. The test builds `diagram_tables`, round-trips it through
`encode_tables`/`decode_tables` (so the check also exercises the wire form),
and compares the two helpers' output per lane with `numpy.array_equal`.

**Assumptions:** None.

#### `test_encode_then_decode_gives_the_same_arrays_and_dtypes`

**Checks:** `decode_tables(encode_tables(tables))` gives back the same table
names, the same dtype for each array, and the same values.

**How:** The test builds the tables of a synthetic gradient echo sequence,
round-trips them through `encode_tables` and `decode_tables`, and checks
that the decoded dict has the same keys and that each array's dtype and
values (`numpy.array_equal`) match the original.

**Assumptions:** None.

#### `test_index_dtype_widths`

**Checks:** `_index_dtype` gives `uint8` for a maximum index up to 255,
`uint16` up to 65535, and `uint32` above that, matching section 4.2's rule
for the width of an index column.

**How:** For each boundary value (0, 255, 256, 65535, 65536), the test
builds a small made-up `uint32` array that contains it, takes its maximum,
calls `_index_dtype` and checks the returned dtype against the expected one,
and checks that casting the array to that dtype keeps the same dtype (no
silent widening).

**Assumptions:** None.

#### `test_checkpoints_match_the_sequential_sum_at_blocks_0_1024_2048`

**Checks:** `diagram_tables`'s `checkpoints` table holds the start time of
blocks 0, 1024 and 2048, equal to the sequential sum that
`waveforms._timed_blocks` gives at those same blocks.

**How:** The test builds `synthetic.gre_sequence(num_trs=600)` (3000
blocks, more than `2 * CHECKPOINT_BLOCKS`, so all three checkpoints this
plan lists exist), builds its tables, and checks `checkpoints` has exactly 3
entries equal to the start time that a plain list of `_timed_blocks` gives
at indexes 0, 1024 and 2048.

**Assumptions:**

- Building the tables for this 3000-block sequence is fast enough to belong
  in the suite: measured at about 30 ms total for the test (sequence
  construction and `diagram_tables` together, on the machine this was
  written on), well under pytest's per-test budget.

#### `test_lane_meta_matches_file_lanes_without_segments_and_windows`

**Checks:** `lane_meta(seq)` equals `waveforms.file_lanes(seq)` with the
`segments` and `windows` keys removed from each lane, both when `lane_meta`
builds its own tables and when it is given prebuilt tables.

**How:** The test builds a synthetic spin echo sequence, computes the
expected lane list by stripping `segments` and `windows` from
`file_lanes`'s output, and checks it against `lane_meta(seq)` and against
`lane_meta(seq, tables=diagram_tables(seq))`.

**Assumptions:** None.

#### `test_read_back_sequence_rebuilds_exactly_and_matches_the_original_within_tolerance`

**Checks:** For a synthetic spin echo sequence written with `seq.write` and
read back with `pp.Sequence.read`, the read sequence's own tables still
rebuild its own `_events_in_range` polylines exactly; and the read
sequence's polylines agree with the original sequence's own polylines
closely, though not exactly.

**How:** The test writes the spin echo sequence to a `tmp_path` file and
reads it back into a fresh `pp.Sequence`. It checks the read sequence's
rebuilt polylines against its own `_events_in_range` reference with
`numpy.array_equal`, the same as
`test_rebuilt_polylines_exactly_match_events_in_range`. It then compares the
read sequence's reference polylines against the original sequence's, with a
tolerance rather than exactly.

**Assumptions:**

- This is the one test in the file, and the only one the plan allows, that
  uses a tolerance rather than an exact comparison.
- The plan (`docs/plans/diagram-event-table.md`, task 1.3) states this
  tolerance as 1e-9 s absolute and 1e-9 relative on values, reasoning that
  the `.seq` file stores durations as raster counts and other values as
  decimal text, so floats "can differ in the last bits". Measured directly
  (`Sequence/write_seq.py` in the installed pypulseq, and the round-tripped
  synthetic sequences here), block times do round-trip that closely, to a
  few ULP, well inside 1e-9. Event **values** do not: pypulseq's own `.seq`
  writer formats a `[TRAP]` gradient's amplitude, and other event values,
  with Python's default `%g` text precision (6 significant digits;
  `'{:12g}'` for `[TRAP]`), which measured as up to about 1e-6 relative
  error on these synthetic sequences (for example about 3.6e-6 on a Gx
  trapezoid amplitude) — far more than "the last bits", and about three
  orders of magnitude looser than the plan's stated 1e-9. This is a property
  of pypulseq's own file writer, not of `diagram_data.py`: the read
  sequence's tables reproduce that same (already-rounded) sequence exactly,
  which the test's first half checks. The test therefore keeps the plan's
  1e-9 tolerance for times, where it holds, and uses a wider, measured
  tolerance for values (1e-6 absolute, 1e-5 relative) instead of the plan's
  1e-9. This gap between the plan's stated value tolerance and the measured
  one has not been resolved with the plan's author; a future change to
  pypulseq's write precision could require revisiting this tolerance.

#### `test_two_rf_events_that_differ_only_in_phase_offset_share_their_offset_pools`

**Checks:** Two RF events built with the same flip angle, duration and
delay but a different `phase_offset` have their magnitude points, and their
kept-phase-point offsets, stored once and shared in the pools, while their
phase values are stored separately.

**How:** The test builds a two-block sequence, one block pulse with
`phase_offset=0` and one with `phase_offset=math.pi / 3`, otherwise
identical, and computes its tables. It checks that the two RF events are
dense indexes 1 and 2, that `rf_mag_offset_at`, `rf_mag_at` and
`rf_phase_offset_at` are equal between them (the shared pool positions), and
that `rf_phase_at` differs (the phase values are not equal, so the test is
a genuine check of both sharing and non-sharing, not one where every pool
happens to collapse).

**Assumptions:**

- `phase_offset` changes the phase samples (`_rf_offsets`'s `phase`) but not
  the magnitude samples or which of them are kept (`mag = |signal|` and
  `keep = mag > 1% of its peak` do not depend on `phase_offset`), so this
  pair of events is expected to share exactly the offset arrays and not the
  phase value array.

### 2.19 Sequence lanes (`test_seq_lanes.js`)

Phase 2 of `docs/plans/diagram-event-table.md` adds the entries.

### 2.20 Sequence lanes against Python (`test_seq_lanes_golden.py`)

Phase 4 of `docs/plans/diagram-event-table.md` adds the entries.

### 2.21 Sequence extensions (`test_extensions.py`)

Phase 6 of `docs/plans/diagram-event-table.md` adds the entries.
