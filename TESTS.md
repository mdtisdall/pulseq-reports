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

`test_markup.py` tests the public helpers of `markup.py`, which project
cards use too (`docs/usage.md`, section 4): the zoom button group placed
above each line chart, the HTML table with escaped cell values, the number
format of the library's tables, and the JSON of a list of lanes.

#### `test_zoom_controls_markup`

**Checks:** `zoom_controls` returns the zoom button group for a chart's SVG
id, with the id HTML-escaped.

**How:** The test calls `zoom_controls("diagram")` and compares the result
with the expected markup: a controls group labeled "Zoom", with
`data-zoom-for="diagram"`, and five buttons in this order: ×10, ×2, ×0.5,
×0.1 and Reset. It calls `zoom_controls('a"b')` and checks that the result
is the same markup with the id HTML-escaped in `data-zoom-for`.

**Assumptions:** None.

#### `test_table_escapes_html`

**Checks:** `html_table` escapes HTML special characters in both the header and
the cell values.

**How:** The test calls `html_table` with one header and one row, each holding
`<`, `&`, `"` and `'` characters. It checks that the raw `<h1>` and
`<script>` tags are not in the result, and that the HTML-escaped header text
and the HTML-escaped cell text are in the result.

**Assumptions:** None.

#### `test_fmt_gives_three_significant_digits_and_a_minus_sign`

**Checks:** `fmt` shows a number with 3 significant digits, and a negative
number with the minus sign U+2212, not a hyphen.

**How:** The test compares `fmt` of 12.3456, 0.000123456 and 123456.0 with
"12.3", "0.000123" and "1.23e+05". It checks that `fmt(-2.5)` is "−2.5"
with U+2212, and that it has no hyphen.

**Assumptions:** The expected texts are Python's `.3g` format of each
value.

#### `test_lanes_json_converts_lanes_in_field_order_and_keeps_dicts`

**Checks:** `lanes_json` gives a `Lane` as a dict with its keys in field
order and its defaults filled in, and gives a dict lane (a gate lane)
unchanged.

**How:** The test makes one `Lane` with only the required fields and one
gate lane dict, and calls `lanes_json` on both. It checks that the first
result's keys are `id`, `title`, `unit`, `color`, `kind`, `segments`,
`domain`, `ticks`, `tick_labels`, `empty` and `fill`, in that order; that
`kind` is "line", `empty` is false and `fill` is None; that `segments` is
the given list; and that the second result is the same dict object.

**Assumptions:** The key order is the JSON key order on the page
(`docs/usage.md`, "Lane JSON format").

### 2.3 The report page (`test_page.py`)

`test_page.py` tests `page.py`. `render_page` builds the report page's HTML
from a list of `Card` objects, in order: each card's title is escaped, its
JSON data (if any) is placed in a `<script type="application/json">`
element, and its script (if any) is included once, even when more than one
card uses it. The tests also cover card and script id validation, the
project CSS (`extra_css`), the library CSS, the `__NAME__` placeholder
substitution, `card_asset`, and `write_page`.

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
`lane_chart.js`, `map_chart.js`, `rf_profiles.js`, `seq_lanes.js`, `pns_lanes.js`,
`g_lanes.js`, each card's library script, the extra scripts in the given order, and
`page.js`.

**How:** The test builds one card with a library script and two extra
scripts, calls `render_page`, and checks that the string indices of a
`chart_math.js` marker, a `lane_chart.js` (`PulseqReport`) marker, a
`map_chart.js` (`PulseqReport.mapChart = mapChart;`) marker, an `rf_profiles.js`
(`RfProfiles`) marker, a `seq_lanes.js` (`SeqLanes`) marker, a `pns_lanes.js` (`PnsLanes`) marker, a `g_lanes.js`
(`GLanes`) marker, the card script's marker, each extra script's marker, and a
`page.js` marker are in increasing order.

**Assumptions:** None.

---

#### `test_each_script_is_its_own_script_element`

**Checks:** Each script is in its own `<script>` element, not concatenated
with the others into one element.

**How:** The test builds one card with no script and one extra script,
calls `render_page`, and counts the occurrences of `<script>\n`. With
`chart_math.js`, `lane_chart.js`, `map_chart.js`, `rf_profiles.js`, `seq_lanes.js`,
`pns_lanes.js`, `g_lanes.js`, the extra script and `page.js`, and no card script, the
count must be 9.

**Assumptions:** None.

---

#### `test_extra_script_with_close_tag_raises`

**Checks:** `render_page` raises `ValueError` when an extra script contains
a `</script` tag, in any letter case.

**How:** The test runs once for each of three forms of the closing tag —
`</script>`, `</SCRIPT>` and `</ScRiPt ` — and checks that `render_page`
raises `ValueError` for an extra script that contains that text.

**Assumptions:** None.

#### `test_extra_css_follows_the_library_css`

**Checks:** `render_page` puts each `extra_css` text in the page's one
`<style>` element, after the whole library CSS (`report.css`), in the given
order, so a project rule wins over a library rule of the same specificity.

**How:** The test renders a page with two `extra_css` texts, each a CSS
comment with a marker. It checks that the page has one `<style>` element,
and that in it the text of `report.css` comes first, whole, and then the
first marker and then the second.

**Assumptions:** None.

#### `test_extra_css_with_close_tag_raises`

**Checks:** `render_page` raises `ValueError` when an `extra_css` text
contains a `</style` tag, in any letter case, because the tag would end the
page's `<style>` element.

**How:** The test runs once for each of three forms of the closing tag —
`</style>`, `</STYLE>` and `</StYlE ` — and checks that `render_page`
raises `ValueError` for an `extra_css` text that contains that text.

**Assumptions:** None.

#### `test_str_in_place_of_a_list_raises`

**Checks:** `render_page` raises `TypeError` when `extra_scripts` or
`extra_css` is one `str` in place of a list of texts. A `str` is a sequence
of one-character texts, so without the check each character becomes its own
`<script>` element or CSS text, with no error.

**How:** The test runs once for `extra_scripts` and once for `extra_css`. It
gives that argument the `str` `"p { color: red; }"` and checks that
`render_page` raises `TypeError` with the argument's name in the message.

**Assumptions:** None.

#### `test_library_css_selects_no_element_id`

**Checks:** The library's `report.css` has no `#id` selector. The caller of
a card builder gives the card its id (`card_id`), so an id selector in the
library CSS styles no library card, or styles one project's own card. A
project card's CSS goes in `extra_css`.

**How:** The test removes the CSS comments from `report.css`, takes the
text before each `{` (the selectors and the `@media` conditions), and
checks that no such text contains `#`.

**Assumptions:** Color values such as `#f9f9f7` are only in declarations,
after a `{`, so they are not in the text that the test checks.

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

**Checks:** `write_page` writes the same HTML that `render_page` returns,
and passes on `extra_scripts` and `extra_css`.

**How:** The test builds one card, one extra script and one `extra_css`
text, each with a marker. It calls `render_page` directly, then calls
`write_page` to a temporary path with the same arguments, and checks that
the file's contents equal the `render_page` result, and that the result has
both markers.

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
two ends of a drag into a view. `laneGroupMap` turns a `laneChart` `groups`
option into a Map from lane id to group id, and `visibleLanes` filters a
list of lanes down to those of a visible group (`lane_chart.js`'s
lane-group support, `docs/plans/diagram-lanes.md` section 4.5 item 3). `colorRamp` builds an n-color ramp linear between a list of
stops, `colorIndex` finds the index of a value in such a ramp over a domain,
and `nearestIndex` finds the nearest grid index on a uniform axis: the map
chart (`assets/map_chart.js`, `docs/plans/rf-profiles.md` section 4.4) uses
them to color its raster and to snap its cursor to the grid. The
report page (`page.py`) puts
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

#### `test_lane_group_map_maps_each_lane_id_to_its_group_id`

**Checks:** `laneGroupMap` builds a Map from each lane id named in a
group's `laneIds` to that group's own id.

**How:** The test calls `laneGroupMap` with two groups, "rf" (`laneIds:
["rf_mag", "rf_phase"]`) and "grad" (`laneIds: ["gx", "gy", "gz"]`), and
checks that the returned Map maps each of the 5 lane ids to its group's
id, and that the Map has exactly 5 entries.

**Assumptions:** None beyond the file's assumptions.

#### `test_visible_lanes_keeps_lanes_of_a_visible_group_and_drops_the_rest`

**Checks:** `visibleLanes` keeps the lanes whose group id is in
`visibleGroupIds` and drops the others.

**How:** The test builds a `groupMap` from two groups, "rf" and "grad"
(the "grad" group is marked `visible: false`, though `visibleLanes` itself
only reads the Set of visible ids it is given, not the `visible` field).
It calls `visibleLanes` with 5 lanes (2 "rf", 3 "grad") and
`visibleGroupIds = new Set(["rf"])`, and checks that only the 2 "rf" lanes
come back, in order.

**Assumptions:** None beyond the file's assumptions.

#### `test_visible_lanes_always_keeps_a_lane_that_belongs_to_no_group`

**Checks:** `visibleLanes` keeps a lane whose id is in no group's
`laneIds`, regardless of `visibleGroupIds` (`lane_chart.js`'s comment
above `laneChart`: "a lane whose id is in no group's `laneIds` is always
drawn").

**How:** The test builds a `groupMap` from one group, "grad" (`laneIds:
["gx"]`), and calls `visibleLanes` with two lanes, "gx" and "adc", and an
empty `visibleGroupIds`. "grad" is hidden, so "gx" is dropped, but "adc"
belongs to no group and stays.

**Assumptions:** None beyond the file's assumptions.

#### `test_visible_lanes_drops_a_lane_a_provider_returns_for_a_hidden_group`

**Checks:** `visibleLanes` drops a lane of a hidden group even when it is
given one anyway, the safety net of `docs/plans/diagram-lanes.md` section
4.5 item 3 for a `lanesFor` provider that does not itself honour
`visibleGroupIds`.

**How:** The test builds a `groupMap` from one group, "pns" (`laneIds:
["pns_total"]`), and calls `visibleLanes` with the single lane
"pns_total" and an empty `visibleGroupIds`. The result is empty.

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

#### `test_color_ramp_two_stops_linear_between_endpoints`

**Checks:** `colorRamp` gives the first stop, the last stop, and a linear blend at
each point in between, for a 2-stop ramp.

**How:** The test calls `colorRamp([[0, 0, 0], [100, 200, 40]], 5)`. The component
values are chosen so each of the 3 interior steps (t = 0.25, 0.5, 0.75) lands on a
whole number, so the test does not have to reason about `Uint8ClampedArray`
rounding. It checks the whole 15-value result: `[0,0,0, 25,50,10, 50,100,20,
75,150,30, 100,200,40]`.

**Assumptions:** None beyond the file's assumptions.

#### `test_color_ramp_three_stops_midpoint_is_the_middle_stop`

**Checks:** `colorRamp` places the middle stop of a 3-stop ramp exactly at the
middle color, for an odd `n`.

**How:** The test calls `colorRamp([[0, 0, 0], [10, 20, 30], [100, 200, 40]], 5)`.
With 3 stops (2 segments) and `n = 5`, the interpolation parameter `t` runs 0, 0.5,
1, 1.5, 2; index 2, the middle of the 5 colors, lands exactly on `t = 1`, the middle
stop. It checks the whole result: `[0,0,0, 5,10,15, 10,20,30, 55,110,35,
100,200,40]`.

**Assumptions:** None beyond the file's assumptions.

#### `test_color_ramp_n_equal_1_returns_only_the_first_stop`

**Checks:** `colorRamp` with `n = 1` returns a single color, the first stop.

**How:** The test calls `colorRamp([[10, 20, 30], [200, 100, 0]], 1)` and checks
that the result has length 3 and equals `[10, 20, 30]`.

**Assumptions:** None beyond the file's assumptions.

#### `test_color_index_maps_domain_endpoints_to_first_and_last_index`

**Checks:** `colorIndex` gives index 0 at the low end of the domain and `n - 1` at
the high end.

**How:** The test calls `colorIndex(0, [0, 10], 5)` and checks the result is 0. It
calls `colorIndex(10, [0, 10], 5)` and checks the result is 4.

**Assumptions:** None beyond the file's assumptions.

#### `test_color_index_maps_the_domain_midpoint_to_the_middle_index`

**Checks:** `colorIndex` gives the middle index for a value at the middle of the
domain.

**How:** The test calls `colorIndex(5, [0, 10], 5)` and checks that the result is
2, the middle of the 5 indices (0 to 4).

**Assumptions:** None beyond the file's assumptions.

#### `test_color_index_clamps_below_and_above_the_domain`

**Checks:** `colorIndex` clamps a value outside the domain to index 0 (below) or
`n - 1` (above), instead of returning an out-of-range index.

**How:** The test calls `colorIndex(-100, [0, 10], 5)` and checks the result is 0.
It calls `colorIndex(1000, [0, 10], 5)` and checks the result is 4.

**Assumptions:** None beyond the file's assumptions.

#### `test_color_index_is_minus_1_for_nan`

**Checks:** `colorIndex` returns -1 for `NaN`, so a map chart can draw that point
transparent instead of picking a color.

**How:** The test calls `colorIndex(NaN, [0, 10], 5)` and checks that the result is
-1.

**Assumptions:** None beyond the file's assumptions.

#### `test_color_index_degenerate_domain_is_always_index_0`

**Checks:** `colorIndex` returns index 0 for every value when the domain is
degenerate (`lo === hi`), since there is no range to place a value in.

**How:** The test calls `colorIndex(5, [5, 5], 8)` and `colorIndex(100, [5, 5], 8)`
(a value equal to, and a value far from, the single domain point) and checks that
both return 0.

**Assumptions:** None beyond the file's assumptions.

#### `test_nearest_index_at_the_grid_points`

**Checks:** `nearestIndex` gives the exact index of a value that sits exactly on a
grid point of `linspace(lo, hi, n)`.

**How:** The test uses the grid `linspace(0, 100, 6)` = `[0, 20, 40, 60, 80, 100]`.
It calls `nearestIndex(0, 100, 6, 0)` and checks the result is 0, `nearestIndex(0,
100, 6, 20)` and checks the result is 1, and `nearestIndex(0, 100, 6, 100)` and
checks the result is 5.

**Assumptions:** None beyond the file's assumptions.

#### `test_nearest_index_halfway_between_grid_points_rounds_up`

**Checks:** `nearestIndex` rounds a value exactly halfway between two grid points up
to the higher index, matching `Math.round`'s rounding of a 0.5 fraction towards
+Infinity.

**How:** Using the same grid `[0, 20, 40, 60, 80, 100]`, the test calls
`nearestIndex(0, 100, 6, 10)` (exactly halfway between index 0 and index 1) and
checks the result is 1. It calls `nearestIndex(0, 100, 6, 30)` (exactly halfway
between index 1 and index 2) and checks the result is 2.

**Assumptions:** None beyond the file's assumptions.

#### `test_nearest_index_clamps_outside_the_range`

**Checks:** `nearestIndex` clamps a value outside `[lo, hi]` to index 0 (below) or
`n - 1` (above).

**How:** The test calls `nearestIndex(0, 100, 6, -50)` and checks the result is 0.
It calls `nearestIndex(0, 100, 6, 500)` and checks the result is 5.

**Assumptions:** None beyond the file's assumptions.

#### `test_nearest_index_degenerate_domain_or_single_point_is_index_0`

**Checks:** `nearestIndex` returns index 0 for a degenerate axis (`lo === hi`) and
for a single-point grid (`n <= 1`).

**How:** The test calls `nearestIndex(5, 5, 4, 5)` (a degenerate domain) and checks
the result is 0. It calls `nearestIndex(0, 100, 1, 50)` (a single grid point) and
checks the result is 0.

**Assumptions:** None beyond the file's assumptions.

---

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
including "TR"), computes the same table directly with `markup.html_table` from
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
`markup.html_table(["Definition", "Value"], [])`.

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

Since phase 3 of `docs/plans/cards-at-scale.md`, `rf_exposure.py` sums the RF energy
once for each unique event (`seq_index.rf_events`) and once for each pulse in play
order, and its highest-window search (`_Search`) tries only certain candidate starts
(section 4.5 of that plan), instead of building one array of every RF sample in play
order and searching over all of them. The tests below the first group add: comparisons
with the oracle (`tests/oracles/rf_exposure.py`, the implementation from before phase 3)
on the synthetic sequences, both `periodic` values, three window-length categories and
200 random pulse trains made with pypulseq; a tie at a window boundary; and a direct
comparison of `_Search`'s candidate-only search with a brute-force search over every
sample.

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

#### `test_matches_oracle_on_synthetic_sequences`

**Checks:** `rf_exposure` matches the oracle (`tests/oracles/rf_exposure.py`, the
implementation from before phase 3 of `docs/plans/cards-at-scale.md`) on each of
`tests/synthetic.py`'s sequences (parametrized: `spin_echo_sequence`, `gre_sequence`,
`empty_sequence`), for both `periodic` values and three window lengths.

**How:** For each sequence, each `periodic` value and window lengths of 1 ms, 10 s and
100 s, the test calls both `rf_exposure` and the oracle's, and compares `num_pulses`,
`peak_block`, `window_s` and `window_used_s` exactly, and `duration_s`, `peak_b1_ut`,
`energy_ut2_s`, `b1rms_ut` and `b1rms_window_ut` within a relative 1e-12
(`_assert_matches_oracle`).

**Assumptions:**

- The new code sums the energy once for each unique RF event and once for each pulse in
  play order, not over every sample in play order like the oracle, so the summed float
  fields can differ from the oracle's by float rounding (section 3.5, item 2 of the
  plan). `num_pulses`, `peak_block`, `window_s` and `window_used_s` do not depend on a
  sum over samples, so they must match exactly.

#### `test_matches_oracle_for_window_length_categories`

**Checks:** `rf_exposure` matches the oracle for a window shorter than one pulse, a
window between one pulse and the whole sequence, and a window longer than the whole
sequence, for both `periodic` values.

**How:** The test builds two 1 ms pulses with 3 s and 17 s gaps (about 20 s total), and
calls both `rf_exposure` and the oracle's with a 0.3 ms window (shorter than one 1 ms
pulse), a 5 s window (between one pulse and the 20 s sequence) and a 50 s window (longer
than the sequence), for both `periodic` values, comparing with `_assert_matches_oracle`.

**Assumptions:** Same as `test_matches_oracle_on_synthetic_sequences`.

#### `test_matches_oracle_on_random_pulse_trains`

**Checks:** 200 seeded random pulse trains, each with several random window lengths and
both `periodic` values, match the oracle.

**How:** For each of 200 seeds, `_random_pulse_train` builds 1 to 11 blocks on the
synthetic system: about 70% of them a block or a sinc RF pulse (`make_block_pulse` or
`make_sinc_pulse`) with a random flip angle and a random duration on the 10 us raster,
each followed by a random gap (`make_delay`), also on the 10 us raster. For each of four
window lengths (well under the sequence's duration, about half of it, well over it, and
the default 10 s) and both `periodic` values, the test calls both `rf_exposure` and the
oracle's and compares them with `_assert_matches_oracle`.

**Assumptions:** Same as `test_matches_oracle_on_synthetic_sequences`.

#### `test_tie_at_window_end_matches_oracle_exactly`

**Checks:** With pulses at a regular spacing and a window length equal to that spacing
(a window end that lands exactly on the next pulse's first sample, a tie), the window
value equals the oracle's exactly, not just within the general tolerance.

**How:** The test builds a train of 5 pulses 2 ms apart plus a 2 ms delay: the first
pulse has a 180° flip angle and the other four (equal to each other) have a 45° flip
angle, so the first pulse alone has the highest one-pulse energy and the search picks it
without a further tie among equal candidates. The window length is set to the exact
spacing between two pulse starts (read from the built sequence's own block durations), a
whole number (1) of that spacing. For both `periodic` values, it checks that
`window_used_s` and `b1rms_window_ut` equal the oracle's exactly (`==`).

**Assumptions:**

- The module docstring says the highest-window search uses the same float sample times
  and the same float comparisons as a search over every sample, so a tie at a window end
  excludes the tied sample the same way as the oracle's `<` comparison, and each window
  here can then hold only the one pulse it starts on.
- The peak pulse's own window energy is an isolated sum of its own per-sample energies,
  in the same order, in both implementations (the oracle's cumulative sum over every
  sample starts at this first pulse, and the new code's `energy_before` for its own
  first pulse is exactly 0), so it is not subject to the general tolerance's rounding.

#### `test_search_candidates_match_brute_force_over_every_sample`

**Checks:** `_Search(train, period).max_energy(length)`, which tries only the candidate
starts of section 4.5 item 4 of `docs/plans/cards-at-scale.md`, equals a brute-force
search over every sample start, written independently in the test.

**How:** For each of 30 seeds, `_small_random_pulse_train` builds a smaller random pulse
train (1 to 4 blocks, shorter pulses) than `_random_pulse_train`, small enough for a
brute-force search. `_brute_force_max_energy` collects every sample's time (from
`_Search._time`) and energy (from the per-event cumulative energies) across the search
(both copies, when periodic), sorts them, and for every sample of the first copy as a
candidate start, sums the energy between that start and the start plus the window length
with `np.searchsorted` on the sorted times. The test compares this against
`_Search.max_energy` for both a wrapping (`period=duration`) and a non-wrapping
(`period=None`) search, and three window lengths (well under, about half of, and well
over the train's duration), within a relative 1e-12.

**Assumptions:**

- A seed whose random train has no RF pulses is skipped: `_Search.max_energy` and the
  brute-force search both give 0.0 for a train with no pulses, so there is nothing to
  compare.

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

Since phase 3 of `docs/plans/cards-at-scale.md`, the "All files" table comes from the
pulse trains that `rf_exposure_card` already built for each file's own table
(`rf_exposure._pulse_train`, `cards/rf_exposure.py`'s `_combined_data`), so the card
does not read a file a second time to build it (section 4.5 item 7 of that plan). The
tests below the first group add: a comparison of the "All files" table with the
oracle's own way of combining files, for two and for three files, and a check that each
file is read only once.

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

#### `test_all_files_table_matches_oracle`

**Checks:** The "All files" table (`_combined_data`'s dict) for two files (spin echo and
GRE) and for three (those two plus a spin echo variant with the readout prephaser after
the second crusher instead of before it) matches the oracle's own way of combining
files, for both `periodic` values.

**How:** `_oracle_combined_data` rebuilds the "All files" data the way the card computed
it before phase 3: each file's samples from `oracle._rf_samples`, offset by the
durations before it, concatenated, then `oracle._windowed_energy` on the concatenation
(`cards/rf_exposure.py`'s own `_combined_data`, before this task's changes). The test
compares this with `_combined_data_from_new_module`'s dict (one `_pulse_train` per file,
then the new `_combined_data`): `num_pulses`, `peak_block`, `window_s`, `window_used_s`
and `periodic` exactly, and `duration_ms`, `peak_b1_ut`, `energy_ut2_ms`, `b1rms_ut` and
`b1rms_window_ut` exactly too, because these are already rounded to 4 decimals and a
relative 1e-12 difference before rounding is far too small to change the rounded value.

**Assumptions:** None.

#### `test_all_files_reads_each_file_once`

**Checks:** `rf_exposure_card` calls `rf_exposure._pulse_train` exactly once for each
file, for two and for three files.

**How:** The test wraps `rf_exposure._pulse_train` with a counting wrapper
(`monkeypatch`), calls `rf_exposure_card` with the two-file and the three-file cases,
and checks that the wrapper was called exactly once for each file.

**Assumptions:** None.

### 2.9 Gradient spectrum (`test_grad_spectrum.py`)

The spectrum is calculated as in pypulseq: 50 ms Hann windows with 50 %
overlap, the magnitude spectrum of each window, and the maximum over windows.
Here the gradients are sampled to the end of the sequence, with half a window
of zeros added at each end. The RSS spectrum is the root-sum-of-squares of the
three axes in each window, then the maximum over windows. The default
resonance bands, of the MAGNETOM Prisma AS82 gradient coil, are 590 ± 50 Hz
and 1140 ± 110 Hz. The gradients are sampled through the raster sampler
(`sampling.GradientSampler`, phase 2 of `docs/plans/cards-at-scale.md`),
in chunks of `CHUNK_WINDOWS` windows, so the memory does not grow with the
sequence length. `combine` gives the spectrum of several files.
`tests/oracles/grad_spectrum.py` is the module before that phase, sampling
through `Sequence.get_gradients()` instead; the tests compare this module's
spectra with it.

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

#### `test_matches_oracle_on_synthetic_sequences`

**Checks:** Phase 5 of `docs/plans/cards-at-scale.md` moved
`gradient_spectrum` from `Sequence.get_gradients()` to the raster sampler
(`sampling.GradientSampler`). This test checks that the axis spectra, the RSS
spectrum and the band peaks still agree with the oracle
(`tests/oracles/grad_spectrum.py`, the module before that change), on the
synthetic spin echo, GRE, arbitrary-gradient, empty and 600 Hz sine
sequences.

**How:** For each sequence, the test calculates the spectrum with this
module and with the oracle. The reasons must be equal. When there is a
spectrum, the frequencies must be equal, the axis spectra and the RSS must
agree within a relative 1e-12 or an absolute 1e-12 times the array's own
peak, and the band peaks must agree on their resonance, their peak value,
their frequency and their relative value within the same tolerance.

**Assumptions:**

- The sampler builds the waveform from each block's own corner points and
  `numpy.interp`, a different order of float operations than
  `Sequence.get_gradients()`'s one whole-axis `PPoly`, so the values are not
  always bit-for-bit equal (section 3.5, item 2 of
  `docs/plans/cards-at-scale.md`).
- The long sequences of task 5.3 are in
  `test_matches_oracle_on_long_sequences`, with a tolerance that grows with
  the duration.

#### `test_matches_oracle_on_long_sequences`

**Checks:** The same comparison with the oracle as
`test_matches_oracle_on_synthetic_sequences`, on the builders of
`scripts/diagram_scale.py` (`build_repeating` and `build_worst`) at 10^4
blocks (task 5.3 of `docs/plans/cards-at-scale.md`).

**How:** The test imports `scripts/diagram_scale.py` by path, builds each
sequence with `10^4 / TR_BLOCKS` TRs, and compares this module's spectrum with
the oracle's, as the test above does, with the tolerance
`1e-12 * max(1, duration in s)` instead of 1e-12.

**Assumptions:**

- The user chose this tolerance on 2026-09-28. Both implementations place each
  gradient corner at an absolute time with float rounding, in a different
  order of additions: the sampler adds `(block start + delay) + offset`, and
  `Sequence.get_gradients()` adds the segment durations one at a time. The
  rounding of an absolute time grows with the time, and a gradient ramp turns
  it into a value difference. Measured: 2.5e-12 of the peak at 10^4 repeating
  blocks (12 s), 3.6e-12 at 10^5 blocks. Neither value is more correct.

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

#### `test_scanner_label_is_escaped_in_the_note`

**Checks:** The card escapes `scanner_label` in its note, as it already does
in the table header and the `aria-label`. A label with `<`, `>` or `&` does
not appear unescaped anywhere in the card's HTML (review finding B5).

**How:** The test builds the card with `scanner_label="Coil <A&B>"` and the
setup of `test_custom_scanner_label_and_resonances_appear`. It checks that
`body_html` does not contain "Coil <A&B>", and that it contains the note's
phrase "the acoustic resonances of the Coil &lt;A&amp;B&gt; gradient coil".

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

`test_pns.py` tests `pns.py`. `PnsPrediction` is now summary-only (`reason`,
`hardware`, `asc_file`, `peak`, `peak_time_s`, `axis_peaks`; no `t_s`,
`norm` or `axes`), built by `pns_prediction` from `pns_levels_for(seq,
asc_path)` — the SAFE model itself (`pns_levels.pns_levels`, the pinned
pypulseq fork's chunked SAFE recursion) has moved there. `pns_levels_for`
keeps one `PnsLevels` for each (sequence object, asc path), the rule of
`seq_index.sequence_index` for staleness (rebuilt when the number of
blocks or the last block id changes, or when the given asc path differs
from the kept one), so that a page with both the PNS summary card and the
diagram's PNS lane for one sequence runs the SAFE model once.
`peak_tr_window` is the start and end of the TR that holds the
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

**Checks:** For the synthetic spin echo sequence on the example hardware, the summary
equals `pns_levels.pns_levels` of the same sequence and hardware, is below the
stimulation limit, and is highest on y.

**How:** The test runs the prediction without an `.asc` file (the module-scoped
`example` fixture) and, separately, `pns_levels.pns_levels` on the same sequence
object. It checks that there is no reason, that the hardware is the example hardware,
and that there is no `.asc` file name. It checks that the axis peaks are keyed x, y and
z, and that the peak is more than 0 and less than 1 (100 % of the limit). The axis with
the highest peak must be y, where the crushers are. `peak`, `peak_time_s` and
`axis_peaks` must equal `pns_levels`'s own fields exactly.

**Assumptions:**

- "Below the limit" is for the example hardware only.
- The crushers (on y) give the synthetic sequence's highest per-axis PNS. This was
  checked against a direct run of the prediction, not derived by hand.
- `pns_prediction` and a fresh `pns_levels.pns_levels` call on the same sequence and
  hardware give bit-identical numbers (no randomness in the pipeline), so the
  comparison is exact equality, not a tolerance.

#### `test_asc_file_with_the_example_parameters`

**Checks:** An `.asc` file with the example hardware's parameters gives the same
prediction as the example hardware, and the file's hardware name and file name.

**How:** The test writes a test `.asc` file with scale factor 1 and runs the
prediction with it. There must be no reason, the hardware name must be the name in the
file, and the file name must be the name of the file. `peak`, `peak_time_s` and each
axis of `axis_peaks` must equal the example hardware's own summary within a relative
10⁻⁹.

**Assumptions:**

- The test file has only the fields that pypulseq's `.asc` reader needs for PNS. A
  real file has many more fields, in the same format.

#### `test_asc_file_that_includes_the_pns_parameters`

**Checks:** A main `.asc` file that includes the PNS parameters from a second file
with `$INCLUDE` gives the same prediction as the example hardware, and the hardware
name in `asCOMP[0].tName`.

**How:** The test writes a test `.asc` file with the scanner layout and scale factor
1, and runs the prediction with the main file. There must be no reason, the hardware
name must be the name in the main file, and the file name must be the name of the main
file. `peak`, `peak_time_s` and each axis of `axis_peaks` must equal the example
hardware's own summary within a relative 10⁻⁹.

**Assumptions:**

- The layout is the layout of the `MP_GradSys_K2309_2250V_951A_XR_AS82.asc` files from
  the XA60 IDEA installation: the `$INCLUDE` line names a file in the same directory,
  without quotes. Other software versions are not tested.

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

#### `test_no_gradients`

**Checks:** A sequence without gradients has no prediction, with the reason
"no gradients", a peak of 0 and no peak time.

**How:** The test makes the synthetic sequence with only a delay block
(`tests/synthetic.py`'s `empty_sequence`) and checks the reason, the hardware
name, the peak and the peak time.

**Assumptions:** None.

#### `test_no_gradients_with_rf_and_adc`

**Checks:** A sequence with RF and ADC events but no gradient events has no
prediction, with the reason "no gradients".

**How:** The test makes a sequence with a block pulse block and an ADC block,
and checks the reason.

**Assumptions:**

- `pns.py` finds "no gradients" from the gradient columns of
  `seq.block_events`. This test and `test_no_gradients` check that other
  events do not count as gradients.

#### `test_a_gradient_on_one_axis_has_a_prediction`

**Checks:** A sequence with a gradient on one axis only, x, y or z, has a
prediction.

**How:** For each axis, the test makes a sequence with a delay block and a
trapezoid block on that axis. There must be no reason, and the peak must be
more than 0.

**Assumptions:**

- A gradient in a block after the first block counts. The delay block comes
  first, so a check of the first block only would fail.

#### `test_prediction_does_not_build_the_gradients_for_an_on_raster_sequence`

**Checks:** The prediction never calls `seq.get_gradients()` for an on-raster sequence.

**How:** The test replaces `get_gradients` of a synthetic spin echo sequence with a
wrapper that counts the calls, and runs the prediction. There must be no calls.

**Assumptions:**

- `pns_levels.pns_levels` samples an on-raster sequence with
  `GradientSampler.block_samples`, not `seq.get_gradients()`/`seq.calculate_pns` (that
  was the old, now-removed, implementation, which is why the old test expected exactly
  one call). `test_pns_levels.py` and `test_sampling.py` test `block_samples` and its
  agreement with `sample`/`get_gradients()` directly; this test only checks that the
  fast path is actually taken from `pns_prediction`.

#### `test_prediction_keeps_no_blocks_and_gives_back_the_cache_setting`

**Checks:** The prediction does not fill pypulseq's block cache, and the
cache setting of the sequence is the same after the prediction.

**How:** For `use_block_cache` True and False, the test sets it on a
synthetic spin echo sequence, empties `seq.block_cache`, and runs the
prediction. After it, `use_block_cache` must have the same value and
`seq.block_cache` must be empty.

**Assumptions:**

- `calculate_pns` reads every block with `get_block`, which keeps each block
  in `seq.block_cache` when `use_block_cache` is True. An empty cache after
  the prediction shows that the cache was off while it ran.

#### `test_prediction_propagates_an_error_and_keeps_the_cache_setting`

**Checks:** An error deep inside the SAFE model propagates out of `pns_prediction`, and
the sequence's block-cache setting and contents are unaffected.

**How:** The test sets `use_block_cache` to True on a synthetic spin echo sequence and
replaces `pns_levels._safe_gwf_to_pns_chunk` (the pinned fork's chunk function) with a
function that raises `RuntimeError`. The prediction must raise the error,
`use_block_cache` must be True and `seq.block_cache` must be empty afterward.

**Assumptions:**

- The block cache is touched only inside `seq_index.block_cache_off`'s own
  `try`/`finally`, which has already restored `use_block_cache` by the time the chunk
  function runs (`GradientSampler` is built, with the block cache off, before the
  chunk loop starts). So this test checks that the error propagates and that nothing
  else in `pns_levels_for`/`pns_prediction` touches the cache setting outside that
  narrower guarantee, not that the guarantee itself is new.

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

#### `test_pns_levels_for_shares_one_computation_with_the_pns_card_and_the_diagram`

**Checks:** For one sequence, the PNS summary card (`cards.pns.pns_data`) and the
diagram's PNS lane (`cards.diagram.diagram_card(..., pns=True)`) together run the SAFE
model once, not twice; adding a block makes the next call recompute
(`docs/plans/diagram-lanes.md`, section 4.6).

**How:** The test patches `pns_levels.pns_levels` with a wrapper that records one entry
for each call (patching the module attribute reaches `pns.pns_levels_for`, which
imports it inside the function body on every call, to avoid a circular import with
`pns_levels.py`). It calls `cards.pns.pns_data(seq)` and then
`cards.diagram.diagram_card([named], [full_window([named])], pns=True)` for the same
sequence object and checks there was 1 call. It adds a delay block to the sequence and
calls `pns_data` again, and checks there are then 2 calls.

**Assumptions:**

- `seq_index.sequence_index`'s staleness rule (block count and last block id) is
  already tested elsewhere (`docs/plans/cards-at-scale.md`'s suite); this test only
  checks that `pns_levels_for` uses the same rule for its own cache.

#### `test_pns_levels_for_recomputes_for_a_different_asc_path`

**Checks:** `pns_levels_for` keeps one result for each (sequence, asc path): a
different `.asc` file for the same sequence recomputes, and going back to an earlier
path recomputes again (a 1-entry cache, not a cache of every path seen).

**How:** The test patches `pns_levels.pns_levels` the same way as the test above, and
calls `pns.pns_levels_for(seq, path)` for two different `.asc` files (`path_a`,
`path_b`) built by the file's `write_gradient_asc` fixture, in the order a, a, b, a. It
checks the call count is 1, 1 (cached), 2 (a different path), 3 (back to `path_a`, but
recomputed, not restored from a 2-entry cache).

**Assumptions:** None.

### 2.12 PNS card (`test_pns_card.py`)

`test_pns_card.py` tests `cards/pns.py`. `pns_data` is now `pns.pns_prediction`'s
summary as a JSON-ready dict only (`reason`, `hardware`, `asc_file`, `example`,
`peak_percent`, `peak_time_ms`, `axis_peaks_percent`); it no longer has `lanes`,
`end_ms` or `peak_tr_ms`. `pns_card` keeps the status line, the table of peaks and
the hardware note; it has no chart and no script (`Card.script` is `None`): the
stimulation over time is now the PNS lane of the sequence diagram
(`cards.diagram.diagram_card(..., pns=...)`), which shares its `PnsLevels`
computation with this card through `pns.pns_levels_for`. A caller that wants the
old "TR with the highest PNS" zoomed view adds `pns.peak_tr_window(seq, ...)` to
the diagram card's own windows instead.

Most of the tests use the synthetic spin echo sequence
(`tests/synthetic.py`'s `spin_echo_sequence`) or the three-TR sequence built
in this file (`_three_trs`, the same sequence as in `test_pns.py`: three
50 ms TRs, one with a faster slew rate that gives it the highest PNS).

**Assumptions for the whole file:**

- The physics (the prediction itself and `peak_tr_window`) is `pns.py`'s,
  tested in `test_pns.py`. These tests check only that the card wires that
  physics into JSON data and HTML correctly.

#### `test_pns_data_for_spin_echo`

**Checks:** For the synthetic spin echo sequence, the PNS data has exactly the
summary-only keys, uses the example hardware, has a peak between 0 % and 100 % that is
at least each axis peak, and has axis peaks keyed x, y and z.

**How:** The test makes the PNS data and checks its key set against the 7 summary
keys. It checks that there is no reason, that the example hardware is used with no
`.asc` file, that the peak is more than 0 % and less than 100 % and is at least each
axis peak, and that the axis peaks are keyed x, y and z.

**Assumptions:** None.

#### `test_pns_data_matches_pns_prediction`

**Checks:** `pns_data`'s numbers are `pns.pns_prediction`'s own fields, converted to
percent and ms.

**How:** The test computes `pns.pns_prediction(seq)` and `pns_data(seq)` for the
synthetic spin echo sequence and checks `peak_percent`, `peak_time_ms` and each axis of
`axis_peaks_percent` against the prediction's `peak`, `peak_time_s` and `axis_peaks`
(scaled and converted), within the rounding the card applies.

**Assumptions:** None.

#### `test_pns_data_for_each_tr_position`

**Checks:** For each position of the peak TR (first, second or third) in the
three-TR sequence, the card still reports the right peak time.

**How:** For peak TR k = 0, 1 and 2, the test makes `_three_trs(k)`, computes
`pns.pns_prediction` and `pns_data`, and checks that `peak_time_ms` matches the
prediction's own `peak_time_s` (converted) and falls inside the TR `[50k, 50(k + 1)]`
ms.

**Assumptions:**

- TRs are counted from the start of the sequence, in steps of the TR definition (as in
  `test_pns.py`'s `peak_tr_window` tests).

#### `test_report_has_pns_card`

**Checks:** For the synthetic spin echo sequence, the card has the id `"pns"`, the
title "PNS prediction" and no script (`script is None`); its body has the below-limit
result, the example hardware warning, the hardware and peak rows, and no chart, no SVG
and no PNS view buttons; and `render_page` accepts it, with the title.

**How:** The test builds the card and checks its `id`, `title` and `script`. It checks
the body for the status text, "Example hardware, not a real scanner.", a cell with the
example hardware name, the rows for the peak of all axes, Gx, Gy and Gz, and that the
body has no `<div class="chart">`, no `<svg` and no `data-pns-view`. It renders the
page and checks for the section element with the card's id (with no
`data-card-script` attribute, since `Card.script` is `None`) and the title.

**Assumptions:**

- "Below the limit" is for the example hardware only.

#### `test_report_without_gradients_has_no_pns_table`

**Checks:** For a sequence without gradients, the card says that there is no PNS
prediction and has no table, inside a rendered page.

**How:** The test builds the card for the synthetic sequence with only a delay block
and renders the page. It checks for the note "No PNS prediction: no gradients." and
that there is no `<table>` element.

**Assumptions:** None.

#### `test_card_id_is_used_for_the_section_and_data_element`

**Checks:** With a non-default `card_id`, the card's own id follows it, and its JSON
data element key is that id too, so two PNS cards can be on one page without an id
clash.

**How:** The test builds the card with `card_id="pns-b"` and checks that the card's own
id and script (`None`) are as given, and that the rendered page has the section
`id="pns-b"` and the data element `id="pns-b-data"`.

**Assumptions:** None.

### 2.13 Gradient limits (`test_grad_limits.py`)

`test_grad_limits.py` tests `grad_limits.py`: the peak amplitude, the peak slew
rate and the RMS amplitude of a sequence's gradients, on each logical axis and
as a three-axis vector, over the whole sequence or over a window. Every
expected value is computed by hand from the parameters of the trapezoid or
arbitrary gradient that the test builds, not by calling `gradient_limits`
itself for the expected value.

Since phase 4 of `docs/plans/cards-at-scale.md`, `grad_limits.py` computes its values from
the per-event values of `seq_index.grad_events` and the columns of `seq_index.sequence_index`,
instead of reading every block with `get_block`, and its slew also includes the step at each
block junction (decision 6 of section 2.5 of that plan). The tests below the first group add:
the largest slew of an arbitrary gradient and of an extended trapezoid (computed from the
event's own corner points, the same way as the peak amplitude tests above), the credited block
for a value that several blocks and axes share, a window that keeps only part of a ramp's
slew, the vector peak of two blocks with different triples of active gradients, the three
junction-step cases of section 4.6 item 6, a window that starts inside a block after a
junction step, and comparisons with the oracle
(`tests/oracles/grad_limits.py`, the implementation from before phase 4).

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

#### `test_arbitrary_gradient_max_slew_is_the_largest_neighbouring_slope`

**Checks:** The largest slew of an arbitrary gradient is the largest
`|delta g / delta t|` between its neighbouring corner points (the shape's
`first`, its waveform samples, and its `last`).

**How:** The test builds an x arbitrary gradient from an asymmetric sine-lobe
waveform and calls `gradient_limits`. It computes the expected slew from
`block.gx.first`, `block.gx.waveform`, `block.gx.last` and their own offset
and shape-duration fields (the same corner points `gradient_offsets` builds),
as the largest `|diff(amplitude) / diff(time)|`, not by calling
`gradient_limits` for the expected value. It checks that the x axis slew
matches.

**Assumptions:** None.

#### `test_extended_trapezoid_max_slew_is_the_largest_segment_slope`

**Checks:** The largest slew of an extended trapezoid is the largest
`|delta g / delta t|` between its neighbouring control points.

**How:** The test builds an x extended trapezoid from five explicit times and
amplitudes and calls `gradient_limits`. It computes the expected slew as the
largest `|diff(amplitudes) / diff(times)|` of the same arrays given to
`make_extended_trapezoid`. It checks that the x axis slew matches.

**Assumptions:** None.

#### `test_largest_over_several_blocks_and_axes_credits_the_first_block_with_that_value`

**Checks:** With several blocks on several axes, the peak amplitude and the
peak slew of each axis are the largest over every block with an event on that
axis, credited to the first block, in play order, whose event reaches that
value; a later block that repeats the very same event does not move the
credit.

**How:** The test builds four blocks: a small x trapezoid, a y trapezoid, a
larger x trapezoid, and the same larger x trapezoid again. It checks that the
x axis peak and slew equal the larger trapezoid's own amplitude and slew
(divided by its rise time), each credited to the third block (the first
block with that event, not the fourth), and that the y axis peak equals the y
trapezoid's amplitude.

**Assumptions:** None.

#### `test_window_that_cuts_a_ramp_gives_the_slew_of_the_part_inside_the_window`

**Checks:** A window that includes only part of an extended trapezoid, over a
segment with a smaller slope than another segment outside the window: the
slew over the window is the slope of the part inside the window, not the
largest slope of the whole event.

**How:** The test builds an x extended trapezoid with four segments of
different slopes and a window that lies inside the two segments with the
smallest slopes, excluding the segment with the largest. It computes the
expected slew by hand from the times and amplitudes of the segment the window
keeps. It checks that the x axis slew matches, not the whole event's own
largest segment slope.

**Assumptions:** None.

#### `test_vector_peak_of_g_compares_different_triples_across_blocks`

**Checks:** Two blocks with different triples of active gradients: the
vector peak of `|G|` is the largest magnitude found across the two different
triples, not just the largest single-axis peak.

**How:** The test builds one block with a large x trapezoid alone, and a
second block with a smaller, equal-amplitude trapezoid on both x and y (whose
combined vector magnitude, `sqrt(2)` times the smaller amplitude, is larger
than the first block's lone peak). It checks that the vector peak equals the
hand-computed combined magnitude of the second block's triple.

**Assumptions:** None.

#### `test_junction_step_between_extended_trapezoids_is_reported_as_the_slew`

**Checks:** A step at the junction between two extended trapezoids, within
the tolerance that `add_block` accepts (`max_slew * grad_raster_time`) and
larger than any segment's own slope: the reported slew is the step divided
by `grad_raster_time`, credited to the block after the junction.

**How:** The test builds two x extended trapezoids whose junction step is 90%
of the largest step `add_block` accepts, and whose own segment slopes are
smaller than that step. It computes the expected slew by hand as the step
divided by `grad_raster_time`. It checks that the x axis slew matches and is
credited to the second block.

**Assumptions:** None.

#### `test_gradient_ending_non_zero_before_a_block_with_no_gradient_is_a_junction_step`

**Checks:** A gradient that ends at a non-zero value (within the tolerance
`add_block` accepts) right before a block with no gradient on that axis: the
junction step uses 0 for the block with no event, and is credited to that
block (the block after the junction).

**How:** The test builds an x extended trapezoid ending at 90% of the largest
step `add_block` accepts, followed by a delay block with no gradient. It
computes the expected slew by hand as that ending value divided by
`grad_raster_time`. It checks that the x axis slew matches and is credited to
the delay block.

**Assumptions:** None.

#### `test_first_block_not_starting_at_zero_is_a_junction_step_before_the_first_block`

**Checks:** A first block whose gradient starts at a non-zero value within
the tolerance `add_block` accepts: the junction before the first block uses 0
for "the block before" (there is none), and is credited to the first block.

**How:** The test builds a single x extended trapezoid starting at 90% of the
largest step `add_block` accepts. It computes the expected slew by hand as
that starting value divided by `grad_raster_time`. It checks that the x axis
slew matches and is credited to the first (only) block.

**Assumptions:** None.

#### `test_window_inside_a_block_with_no_gradient_ignores_the_junction_before_it`

**Checks:** A window entirely inside a block with no gradient, right after a gradient
event that ends at a non-zero value (within the tolerance `add_block` accepts) in the
block before: the window does not use the junction between the two blocks, because
that block starts before the window (`docs/plans/review-bugs.md`, B1, decision 14), so
the window has no gradient event and 0 slew. A window that starts exactly at that
junction still uses it.

**How:** The test builds an x extended trapezoid ending at 90% of the largest step
`add_block` accepts, followed by a delay block with no gradient. It calls
`gradient_limits` with a window from partway into the delay block to its end, and
checks that `reason` is "no gradient events in the window", the x slew is 0.0, and
`slew_block` is None. It then calls `gradient_limits` with a window that starts
exactly at the junction (the end of the trapezoid block) and checks that the x slew
equals the ending value divided by `grad_raster_time` and is credited to the delay
block.

**Assumptions:** None.

#### `test_matches_oracle_on_synthetic_sequences`

**Checks:** `gradient_limits` matches the oracle (`tests/oracles/grad_limits.py`, the
implementation from before phase 4 of `docs/plans/cards-at-scale.md`) on the whole file, and
on a window covering the first half of the sequence, for each of `tests/synthetic.py`'s
sequences (parametrized: `spin_echo_sequence`, `gre_sequence`, `empty_sequence`,
`arbitrary_gradient_sequence`).

**How:** For each sequence, the test calls both `gradient_limits` and the oracle's, with no
window and with a window from 0 to half the total duration, and compares every field (`reason`,
`range_s`, each axis's peak, slew and RMS, and the vector peak), within a tolerance derived
from the sequence (`_rounding_tol`): `1e-12 + 4 * eps * duration / shortest segment`, relative
to the value or to the limit of the same kind. It checks only whether a block is credited, not
which one, because `gre_sequence` repeats its readout, phase-encode and spoiler events every TR,
and the oracle's own choice among such a tie can depend on the same rounding.

**Assumptions:**

- The user chose this tolerance on 2026-09-28. The oracle adds each block's absolute start
  time to an event's corner points before it takes a slope, so each corner time is rounded to
  about eps times the start time, and a slope divides the difference of two such times by the
  segment's duration. The new code computes each event one time from its own offsets. On the
  synthetic and random sequences the differences are at most about 2% of this bound.

#### `test_matches_oracle_on_random_gradient_sequences`

**Checks:** 200 random sequences of trapezoids, extended trapezoids and arbitrary gradients on
random axes, each event built so that it starts and ends at 0 (so every block junction step is
0, and the result is only the per-event, non-junction part that the tests above cover on their
own): `gradient_limits` matches the oracle, on the whole file and on a random window, and the
window's `whole_rms_mt_per_m` (computed in the same call, for the card's "RMS over whole file"
column) matches the oracle's own whole-file RMS.

**How:** For each of 200 seeds, the test builds a sequence of 2 to 6 blocks, each with 0 to 3
random axes, each a trapezoid, an extended trapezoid or an arbitrary gradient built with
pypulseq's `make_*` functions (so pypulseq's own limit checks apply) and an explicit `first` and
`last` of 0 where the function does not default to that. It compares the whole-file result and
a random window's result with the oracle's, field by field, with the same derived tolerance and
the same block-attribution exception as `test_matches_oracle_on_synthetic_sequences`, and separately
compares `whole_rms_mt_per_m` against a fresh whole-file oracle call.

**Assumptions:**

- `make_arbitrary_grad`'s `first` and `last` default to a linear extrapolation of the
  waveform's own edge samples, not to 0 (`docs/notes/slew-definitions.md`'s pypulseq source
  reading confirms this), so the random arbitrary-gradient builder passes `first=0.0, last=0.0`
  explicitly to keep every event zero-ended. This is a fact about pypulseq, not about the
  function under test, and is not itself checked here.

### 2.14 Gradient limits card (`test_gradient_limits_card.py`)

`test_gradient_limits_card.py` tests `cards/gradient_limits.py`: the "Gradient
limits" table (Gx, Gy, Gz and |G| rows, with the peak, its percent of the
limit, the max slew, its percent, and the RMS), one row group for each file
when there is more than one, and the extra RMS column when a window is given.
Every expected numeric cell is computed by hand from the trapezoid the test
builds, using the same formulas as `test_grad_limits.py`, and compared through
`markup.html_table`, so a test also fixes the exact table that `html_table` would
render from those rows.

Since phase 4 of `docs/plans/cards-at-scale.md`, a window's "RMS over whole file" column comes
from the one `gradient_limits` call's own `whole_rms_mt_per_m`, not a second call with
`window=None`, so that the card makes one pass over the per-event values for each file.

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
table HTML with `markup.html_table` from the hand-computed rows. It calls
`gradient_limits_card` and checks that the card's `id`, `title`, `data` and
`script`, and that its body starts with the expected table HTML.

**Assumptions:** None.

#### `test_two_files_have_one_row_group_each_with_file_names`

**Checks:** With two files, the table has a leading "File" column, each
file's name on the first of its four rows and blank on the other three, and a
file name with an HTML special character is escaped.

**How:** The test builds two files, each with a single x trapezoid of a
different amplitude, computes the hand-computed rows for each as in the
single-file test, and builds the expected table HTML with `markup.html_table`,
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
the expected table HTML with `markup.html_table` from these hand-computed rows,
with both RMS columns, and checks that the card's body starts with it.

**Assumptions:** None.

#### `test_no_gradients_adds_a_reason_note`

**Checks:** A file with no gradient events gets a muted note in the card that
names the file and the reason.

**How:** The test builds a file with a delay block only, calls
`gradient_limits_card`, and checks that the body contains
"empty.seq: no gradient events in the sequence.".

**Assumptions:** None.

#### `test_note_says_max_slew_includes_block_junction_steps`

**Checks:** The card's note says that Max slew is the largest slope inside one
gradient event, or the step at a block junction divided by the gradient raster
time, as the slew column computes it since phase 4 of
`docs/plans/cards-at-scale.md` (review finding B6).

**How:** The test builds one trapezoid file, calls `gradient_limits_card`, and
checks that the body contains "or the step at a block junction divided by the
gradient raster time".

**Assumptions:** None.

#### `test_card_with_a_window_makes_one_pass_over_the_per_event_values`

**Checks:** With a window, `gradient_limits_card` calls the per-event
function (`seq_index.grad_events`, which reads each unique gradient event's
block with `get_block`) exactly one time for the one file, instead of once
for the window and again for the whole-file RMS.

**How:** The test wraps `grad_limits.grad_events` with a counting wrapper
(`monkeypatch`), calls `gradient_limits_card` with one file and a window, and
checks that the wrapper was called exactly once.

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
(`file_lanes`), the block table rows (`block_rows`), and the two named views
`first_adc_window` and `full_window`. The lane and block-table tests are adapted from vb-pulseq's
`test_spin_echo_lanes`, `test_block_table`,
`test_zero_phase_rf_and_zero_gradient_are_events` and its `report_at_tr`
tests, moved to `tests/synthetic.py` sequences and to the module's own
functions in place of vb's `sequence_data` dict; the PNS, page and
timing-check parts of those vb tests belong to other cards and are dropped.
The rest of the file is new coverage for a range that cuts a block and the
two named views.

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

`test_diagram_card.py` tests `cards/diagram.py`. `diagram_card` sends one
entry in `data["files"]` for each file that at least one caller-given time
window uses (its compressed block and event tables, `diagram_data`, plus
`lane_meta`), and one entry in `data["windows"]` for each window, with one
button for each window in the given order (section 4.1 of
`docs/plans/diagram-event-table.md`). There is no lane set and no point
budget any more: every view is drawn in the browser from the tables (phase
4's job is done there, not in Python). The last test is adapted from
vb-pulseq's `test_report_has_zoom_controls_on_each_line_chart`, checking
only the diagram card because phases 4 (gradient spectrum) and 5 (PNS) are
not merged into this branch.

#### `test_data_has_format_1_with_file_and_window_keys`

**Checks:** `diagram_card`'s data has `format == 1`, one file entry with
the keys of section 4.1 (`name`, `duration_s`, `num_blocks`, `lanes`,
`tables`), a `lanes` equal to `lane_meta(seq)`, a `duration_s` and
`num_blocks` equal to `waveforms.duration_s(seq)` and
`len(seq.block_events)`, each table entry with the keys `dtype`, `length`
and `data`, and each window entry with the keys `label`, `file` and
`view_ms`.

**How:** The test builds a synthetic spin echo sequence and calls
`diagram_card` with its `first_adc_window` and `full_window`, then checks
the key sets and values of `card.data` and of its one file and its windows
directly against `diagram_data.lane_meta`, `waveforms.duration_s` and
`seq.block_events`.

**Assumptions:** None.

#### `test_tables_decode_to_diagram_tables`

**Checks:** A file entry's `tables`, decoded with `diagram_data.decode_tables`,
equal `diagram_data.diagram_tables(seq)`: the same table names, the same
dtype and the same values for each.

**How:** The test builds a synthetic gradient echo sequence, calls
`diagram_card` with its `full_window`, decodes the one file entry's
`tables`, and compares each decoded array's dtype and values
(`numpy.array_equal`) against `diagram_tables(seq)`'s own arrays.

**Assumptions:** None.

#### `test_two_files_give_two_file_entries_and_names_in_button_texts`

**Checks:** With two files, each used by one window, `data["files"]` has
two entries in the order in which the windows first use them (here the
`seqs` order), and each button's text starts with its file's name.

**How:** The test builds two named sequences and one `full_window` for
each, calls `diagram_card`, and checks `data["files"]`'s names and that
`"a.seq: Full sequence"` and `"b.seq: Full sequence"` both appear in
`body_html`.

**Assumptions:** None.

#### `test_a_window_of_a_file_with_no_other_window_adds_that_file`

**Checks:** A window of a file that no other window uses still adds that
file to `data["files"]`; a file in `seqs` with no window at all is not in
`data["files"]`; and each window's `file` index points at the right entry.

**How:** The test builds three named sequences, `a.seq`, `b.seq` and
`c.seq`, and calls `diagram_card` with one window each for `c.seq` and
`a.seq` only (`b.seq` gets none). It checks `data["files"]` has exactly two
entries, with the names `{"a.seq", "c.seq"}`, and that each window's `file`
index, looked up by the window's label prefix (`"c.seq:"`, `"a.seq:"`),
names the file with the matching file name (so a file's position in
`data["files"]` — its order of first use — is checked against the window
that should point at it, not assumed).

**Assumptions:** None.

#### `test_ids_start_with_the_given_card_id`

**Checks:** With a non-default `card_id`, the card's own id and the ids of
its SVG, chart, tooltip and status-line elements all start with it.

**How:** The test calls `diagram_card` with `card_id="my-diagram"` and
checks that `card.id` is `"my-diagram"` and that `body_html` has
`id="my-diagram-diagram"`, `id="my-diagram-chart"`, `id="my-diagram-tip"`
and `id="my-diagram-mode"`.

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

#### `test_render_page_includes_diagram_and_seq_lanes_scripts_once`

**Checks:** `render_page` includes the diagram card script and
`assets/seq_lanes.js` exactly once each.

**How:** The test builds a diagram card, renders it with `render_page`, and
checks that the page has exactly one
`PulseqReport.registerCard("diagram"` call and exactly one `const SeqLanes`
(the top of `seq_lanes.js`).

**Assumptions:** None.

#### `test_no_envelope_note_and_status_line_is_present`

**Checks:** The card's body has no envelope note (removed with the lane
sets and the point budget) and has the status-line element
`{card_id}-mode` that `assets/cards/diagram.js` writes the "Exact
waveform."/"Minimum and maximum..." text into.

**How:** The test builds a diagram card and checks that `"too many"` and
`"envelope"` do not appear in `body_html`, and that `id="diagram-mode"` and
`aria-live="polite"` do.

**Assumptions:** None.

#### `test_diagram_card_has_zoom_controls_before_its_chart_and_the_help_sentence_once`

**Checks:** The rendered page has the zoom button group directly before the
diagram's `<div class="chart">`, and the zoom and pan help text exactly
once.

**How:** Adapted from vb-pulseq's
`test_report_has_zoom_controls_on_each_line_chart`, checking only the
diagram card because phases 4 and 5 are not merged into this branch. The
test builds a diagram card and renders it. It checks that
`markup.zoom_controls("diagram-diagram")` appears exactly once, that the
text right after it (skipping one newline) starts with
`<div class="chart"` and has `id="diagram-diagram"` within its first 400
characters, and that the zoom and pan help sentence ("Click the chart to
mark the centre for the zoom buttons. Drag across the chart to zoom to that
range. Hold Shift and drag, or scroll sideways, to pan.") appears exactly
once.

**Assumptions:** None beyond the file's assumptions.

#### `test_pns_false_by_default_adds_no_pns_key`

**Checks:** Without `pns` (the default, `False`), a file entry has no `"pns"` key.

**How:** The test builds a diagram card for the synthetic spin echo sequence with no
`pns` argument and checks that `"pns"` is not a key of the one file entry.

**Assumptions:** None.

#### `test_pns_true_adds_the_pns_key_with_the_example_hardware`

**Checks:** With `pns=True`, the file entry gets a `"pns"` key with the example
hardware, the SAFE parameters, the gradient raster, `gradScale`, `binSamples`, the
summary and the stored level, all with the keys the plan's data section lists.

**How:** The test builds a diagram card with `pns=True` for the synthetic spin echo
sequence, and checks the `"pns"` entry's key set, that `hardware` is
`pns.EXAMPLE_HARDWARE`, `example` is True and `asc_file` is None, that `hw` has x, y, z
each with the 8 SAFE fields, that `dtS` equals the sequence's own gradient raster time,
that `gradScale` is exactly 1.0 (a proton sequence), that `binSamples` is positive,
that the summary has `peak`, `peak_time_s` and `axis_peaks` with a peak between 0 and 1
and a peak time, and that `levels` has `min` and `max` tables of dtype `float32`.

**Assumptions:** None.

#### `test_pns_asc_path_uses_the_gradient_asc_hardware`

**Checks:** With `pns` set to a gradient `.asc` path, the `"pns"` entry uses that
file's hardware, not the example hardware.

**How:** The test writes a minimal gradient `.asc` file with pypulseq's example
hardware's own PNS parameters (a local helper, the same technique as `test_pns.py`'s
`write_gradient_asc` fixture: the real files are confidential), builds a diagram card
with `pns` set to that path, and checks that the `"pns"` entry's `hardware` is the
file's name, `example` is False and `asc_file` is the file's name.

**Assumptions:** None.

#### `test_pns_grad_scale_for_a_sequence_with_another_gyromagnetic_ratio`

**Checks:** `gradScale = seq_utils.GAMMA / seq.system.gamma` (decision 14): not 1.0 for
a sequence built with a non-proton gyromagnetic ratio.

**How:** The test builds a one-block x-trapezoid sequence on a system with
`gamma=11.262e6` (sodium, the same value the golden test of task 4.5 uses), builds a
diagram card with `pns=True`, and checks the `"pns"` entry's `gradScale` equals
`seq_utils.GAMMA / seq.system.gamma` and is not 1.0.

**Assumptions:** None.

#### `test_pns_without_gradients_adds_no_pns_key`

**Checks:** A file with no gradient event gets no `"pns"` key even when `pns` is not
False.

**How:** The test builds a diagram card with `pns=True` for the synthetic sequence
with only a delay block (`tests/synthetic.py`'s `empty_sequence`) and checks that
`"pns"` is not a key of the one file entry.

**Assumptions:** None.

#### `test_pns_levels_decode_back_to_pns_levels_for_exactly`

**Checks:** The `"levels"` key of the `"pns"` entry, decoded, equals
`pns.pns_levels_for(seq)`'s own `level_min`/`level_max` exactly.

**How:** The test builds a diagram card with `pns=True` for the synthetic spin echo
sequence, decodes the `"pns"` entry's `"levels"` with `diagram_data.decode_tables`, and
compares the two arrays' dtype (`float32`) and values (`numpy.array_equal`) against
`pns.pns_levels_for(seq).level_min`/`level_max`.

**Assumptions:**

- `diagram_card` and the direct `pns_levels_for` call read the same cached `PnsLevels`
  for this sequence object (`pns.pns_levels_for`'s own cache, `test_pns.py`), so the
  comparison is exact, not merely close.

#### `test_group_controls_container_is_between_the_window_buttons_and_the_zoom_controls`

**Checks:** The lane-group toggle buttons (RF/ADC/Gradients/PNS, `docs/plans/
diagram-lanes.md` section 4.5 item 3) go above the chart, after the time-window
buttons and before `zoom_controls`, so the existing "zoom controls directly
before the chart" test still holds.

**How:** The test builds a diagram card for the synthetic spin echo sequence and
checks that the group-controls container (`<div class="controls" role="group"
aria-label="Lanes" id="diagram-groups"></div>`) appears exactly once in the
body, and that its position is after the time-window buttons' container and
before `markup.zoom_controls("diagram-diagram")`.

**Assumptions:** None.

#### `test_group_controls_container_id_starts_with_the_given_card_id`

**Checks:** With a non-default `card_id`, the group-controls container's id
starts with it.

**How:** The test builds a diagram card with `card_id="my-diagram"` and checks
that `id="my-diagram-groups"` appears on the group-controls container.

**Assumptions:** None.

#### `test_group_controls_container_present_even_without_pns_data`

**Checks:** The group-controls container is present even when the card has no
PNS lane: it is not conditional on `pns`, since the RF, ADC and gradient groups
can be toggled regardless, and the card script fills it in the browser with one
button for each group that applies to the file's own data.

**How:** The test builds a diagram card with no `pns` argument (`pns=False`, the
default) and checks that the empty group-controls container is present in the
body.

**Assumptions:** None.

#### `test_g_lane_explanation_sentence_always_present`

**Checks:** The card's body always has the |G| lane's explanation sentence (naming
the |G| lane and that it shows the magnitude of the gradient vector), whether or not
`pns` is given: the |G| lane needs no extra data from `diagram_card` (`docs/plans/
diagram-lanes.md`, phase 5; it is computed in the browser from the tables already
sent), unlike the PNS sentence.

**How:** The test builds a diagram card with no `pns` argument (`pns=False`, the
default) for the synthetic spin echo sequence and checks that each of the two phrases
("|G| lane", "magnitude of the gradient vector") appears in the body.

**Assumptions:** None.

#### `test_g_lane_explanation_sentence_present_even_without_gradients`

**Checks:** The |G| lane's explanation sentence is present even for a file with no
gradient event, unlike the PNS sentence, which such a file never gets: the |G| lane
itself is always in the Gradients group (empty, with an "0 to 1" domain, when the file
has no gradient), so its sentence is not keyed on the file's own data either.

**How:** The test builds a diagram card for `tests/synthetic.py`'s `empty_sequence`
(only a delay block) and checks that each of the two phrases appears in the body.

**Assumptions:** None.

#### `test_pns_explanation_sentence_present_when_the_card_has_pns_data`

**Checks:** With `pns=True` and a sequence with gradients, the card's body has
the PNS lane's explanation sentence (naming the PNS lane, that it is a percent
of the SAFE stimulation limit, and the "10 s or less" exact-view span).

**How:** The test builds a diagram card with `pns=True` for the synthetic spin
echo sequence and checks that each of the three phrases ("PNS lane", "percent
of the SAFE stimulation limit", "10 s or less") appears in the body.

**Assumptions:** None.

#### `test_pns_explanation_sentence_absent_by_default`

**Checks:** Without `pns` (the default, `False`), the explanation sentence is
absent.

**How:** The test builds a diagram card with no `pns` argument and checks that
none of the three explanation phrases appears in the body.

**Assumptions:** None.

#### `test_pns_explanation_sentence_absent_without_gradients_even_with_pns_true`

**Checks:** A file with no gradient event gets no `"pns"` key even when `pns` is
not False, so it gets no explanation sentence either: the sentence is keyed on
the data (`has_pns`), not on the `pns` argument alone.

**How:** The test builds a diagram card with `pns=True` for the synthetic
sequence with only a delay block (`tests/synthetic.py`'s `empty_sequence`) and
checks that none of the three explanation phrases appears in the body.

**Assumptions:** None.

### 2.17 Block table card (`test_blocks_card.py`)

`test_blocks_card.py` tests `cards/blocks.py`. `blocks_card` builds a
collapsed "Blocks (table view)" card from `waveforms.block_rows`: the first
`max_rows` blocks of each file when there are no windows (vb-pulseq's own
note and table for one file, parity), or one table for each window when
`windows` is given. Every expected table in this file is built with
`markup.html_table`, the same helper the card itself uses, from the rows that
`block_rows` gives directly, so a test also fixes the exact table that
`html_table` would render from those rows.

#### `test_one_file_note_and_table_when_rows_are_cut`

**Checks:** For one file with more blocks than `max_rows`, `body_html` is the
"First N of M blocks." note, a newline, and the table, and the card's other
fields are correct.

**How:** The test builds a synthetic gradient echo sequence with more
blocks than a small `max_rows`, calls `blocks_card`, and separately calls
`block_rows` with the same `max_rows` to get the expected rows and total. It
builds the expected note text and the expected table with `markup.html_table`,
and checks that `body_html` equals the note, a newline, and the table,
exactly. It also checks `id`, `title`, `collapsed`, `data` and `script`.

**Assumptions:** None.

#### `test_no_note_when_all_rows_fit`

**Checks:** When every block fits under `max_rows`, the card has no "First N
of M blocks." note.

**How:** The test builds a small sequence, calls `blocks_card` with the
default `max_rows`, and checks that `body_html` equals a newline followed by
the expected table (built with `markup.html_table`), and that the text "muted"
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
own range (from `block_rows` and `markup.html_table`) appears in the body.

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

#### `test_encode_then_decode_accepts_float32`

**Checks:** `decode_tables(encode_tables(tables))` keeps a `float32` array's dtype and
(for values representable exactly in `float32`) its values.

**How:** The test builds a small `float32` array (0.0, 1.5, −2.25 and the largest
finite `float32`), round-trips it through `encode_tables`/`decode_tables` as the
`"level_min"` table, and checks the decoded array's dtype is `float32` and its values
equal the original (`numpy.array_equal`).

**Assumptions:**

- The chosen values are exactly representable in `float32`, so the round trip is exact
  equality, not a tolerance; `pns_levels.py`'s own `_cast_outward` (tested in
  `test_pns_levels.py`) is what turns an arbitrary float64 minimum/maximum into a
  float32 that still bounds it — this test only checks the wire form's round trip.

#### `test_encode_tables_gives_the_same_bytes_at_different_times`

**Checks:** `encode_tables` gives byte-identical output for the same tables at two
different clock times, so a report built again from the same sequence is the same
file. In the gzip header of each table, the time stamp (bytes 4-7) is 0 and the OS
byte (byte 9) is 255.

**How:** The test builds the tables of a synthetic gradient echo sequence once. It
encodes them with `time.time` monkeypatched to return 1,000,000,000 s, then again with
2,000,000,000 s, and checks that the two results are equal. It then base64-decodes each
table's `data` and checks bytes 4-7 and byte 9 of the header.

**Assumptions:**

- `gzip.compress` reads the clock through `time.time`, so the monkeypatch changes the
  time stamp that a call without `mtime=0` would write. Without the fix, the two results
  differ.
- The OS byte check is for the case the first check cannot see on one machine. With
  `mtime=0`, Python 3.12 lets zlib write the header, and zlib's OS byte is 3 on Linux
  and 19 on macOS. So a report built on macOS and one built on Linux would differ.

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
  orders of magnitude looser than 1e-9. This is a property of pypulseq's own
  file writer, not of `diagram_data.py`: the read sequence's tables
  reproduce that same (already-rounded) sequence exactly, which the test's
  first half checks. The test therefore uses 1e-9 for times and a measured
  tolerance for values (1e-6 absolute, 1e-5 relative). The plan first asked
  for 1e-9 on the values too; phase 5 corrected the plan (task 1.3) to these
  tolerances. A change to pypulseq's write precision can change the
  tolerance that the values need.

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

`seq_lanes.js` turns the compressed block and event tables of one `.seq`
file (section 4.2 of `docs/plans/diagram-event-table.md`) into chart lanes,
with no DOM and no network: `SeqLanes.decode` builds a model from typed
arrays and lane metadata; `blockStart` and `blockAt` give block times
without a start-time array of length N; `exactLanes` and `pointsIn` give the
exact view and its point count; `minMaxLanes` gives the minimum and the
maximum of each bin of a zoomed-out view; `lanesFor` picks between the two
by `pointsIn` against `EXACT_POINT_LIMIT`.

The tests load `seq_lanes.js` directly, with Node's `require`, from
`src/pulseq_reports/assets/seq_lanes.js`, the same way `test_chart_math.js`
loads `chart_math.js`. They use `node:test` and `node:assert/strict`, and no
browser or DOM. Two kinds of model back the tests:

- `buildHandModel`: 5 blocks built by hand (an RF pulse with a magnitude and
  a phase point, a trapezoid gradient, an arbitrary gradient, an ADC window,
  and an empty block), with every block start and every event point worked
  out on paper. `buildPhaseGapModel` (3 blocks) and `buildAdcCloseModel` (4
  blocks) are further hand-built models for two `minMaxLanes` edge cases
  that the 5-block model does not have: an RF phase gap and two ADC windows
  closer together than one bin. `buildSparseAdcModel(nBlocks, adcBlocks)`
  builds a model of any block count, no RF and no gradient, with a 0.5 ms
  ADC window at the start of each block in `adcBlocks`: used for a
  `minMaxLanes` ADC edge case (B2 of `docs/plans/review-bugs.md`, whose
  section 2.3 reports that `buildRandomModel`'s ADC density never reaches
  this placement). `buildPointBudgetModel` gives every block the same,
  known number of points, so a view can be built that holds exactly
  `EXACT_POINT_LIMIT` points.
- `buildRandomModel`: a pseudo-random model of any block count (so it can be
  built larger than 1024 or 2048 blocks, to cross a checkpoint boundary),
  seeded for a deterministic sequence, used where the exact points are too
  many to check by hand. It is the model builder of the scratchpad scripts
  `validate_minmax.js` and `validate_phase_adc.js`, which the task that
  wrote this file used to work out `minMaxLanes`'s behavior before writing
  the tests, copied here so the test file reads nothing from the scratchpad
  at run time.

For `minMaxLanes`, most tests compare its output against a brute-force
computation over `exactLanes`'s whole-file points, written out in the test
file itself (`bruteForceLineWant`, and the per-bin loops in
`phaseLaneProblems` and `adcLaneProblems`): for each bin, the minimum and
the maximum of every whole-file point in the bin, and of the polyline's
value at each of the bin's two edges, by direct linear interpolation
(`numpyInterp`, `numpy.interp`'s formula, section 4.4 item 2, the same
formula the Python reference of the golden test of section 2.20 uses).

**Assumptions for the whole file:**

- The functions take only plain values (numbers, arrays, typed arrays) and
  return only plain values. Nothing in a test depends on the page or a
  browser.
- Interpolated edge values need about 1e-12 relative tolerance
  (`relClose`): `minMaxLanes` and the brute-force check in the test reach
  the same mathematical value by different sequences of floating-point
  operations (a segment tree of group extremes and `_edgeValue`'s neighbour
  search, against a linear scan of every whole-file point), so the two need
  not always land on the exact same bit pattern. Every other numeric
  comparison in this file (`blockStart`, `blockAt`, `exactLanes`, the
  windows of `minMaxLanes`'s ADC lane, and the point counts and segment
  counts used to pin down the edge cases) is an exact comparison, with no
  tolerance, because those values are sums of the same operations in the
  same order, or bin-edge times computed by the same formula the test
  itself uses, or plain integer counts.
- `test_min_max_lanes_matches_brute_force_for_line_lanes_over_several_views`,
  `test_min_max_lanes_matches_brute_force_for_the_rf_phase_lane` and
  `test_min_max_lanes_matches_brute_force_for_adc_windows` reuse the model
  sizes, seeds and views of the scratchpad's `validate_minmax.js` and
  `validate_phase_adc.js`, which already ran them against `seq_lanes.js`
  with 0 mismatches. This file's tests do not depend on that scratchpad run
  for their own result: each one recomputes the brute-force comparison
  itself.

#### `test_decode_throws_for_an_unsupported_format`

**Checks:** `decode` throws for a `format` other than 1 (section 4.6: a page
with data for a later format must fail loudly, not draw wrong waveforms).

**How:** The test calls `SeqLanes.decode(2, tables, HAND_LANES_META)` with
the hand model's tables, and checks that it throws.

**Assumptions:** None beyond the file's assumptions.

#### `test_decode_throws_for_an_unknown_table_name`

**Checks:** `decode` throws when `tables` has a table name it does not
know, for example `rotation` (section 4.6, the name reserved for the
rotation extension).

**How:** The test calls `decode` with the hand model's tables plus an extra
`rotation` table, and checks that it throws.

**Assumptions:** None beyond the file's assumptions.

#### `test_decode_throws_for_offsets_out_of_time_order`

**Checks:** `decode` throws when the offsets of an event go down. The
minimum/maximum view finds the points of an event by binary search on
their times, which is correct only for offsets in time order.

**How:** The test takes the hand model's tables, changes one offset of
gradient event 2 so that its offsets are `[0, 0.0004, 0.0001, 0.002]`, and
checks that `decode` throws with "not in time order" in the message.

**Assumptions:** None beyond the file's assumptions.

#### `test_decode_throws_for_a_checkpoint_that_is_not_the_sum_of_durations`

**Checks:** `decode` throws when a checkpoint is not the sequential sum of
the durations before it (section 4.3). `decode` keeps its own start for
each group of 64 blocks, from that same sum, and `blockStart` starts from
those, so the two must agree exactly.

**How:** The test builds a 2048-block random model, adds 1e-9 s to
checkpoint 1, and checks that `decode` throws with "checkpoint 1" in the
message.

**Assumptions:** None beyond the file's assumptions.

#### `test_decode_throws_for_a_missing_table`

**Checks:** `decode` throws when `tables` is missing one of the known
tables. This is not one of the six required checks, but it is the other
half of the same "requires exactly the known tables" behavior, and the test
was already available to add cheaply.

**How:** The test calls `decode` with the hand model's tables minus
`checkpoints`, and checks that it throws.

**Assumptions:** None beyond the file's assumptions.

#### `test_block_start_is_a_sequential_sum_from_zero_exactly`

**Checks:** `blockStart` gives the sequential sum of the block durations
from 0.0, for every block of a small model, with no tolerance.

**How:** The test calls `blockStart` on the hand model's 5 blocks (block
durations 0.002, 0.003, 0.0025, 0.001, 0.0015 s) and checks the exact
result for each: 0, 0.002, 0.005, 0.0075, 0.0085.

**Assumptions:** None beyond the file's assumptions.

#### `test_block_start_is_exact_across_a_checkpoint_boundary`

**Checks:** `blockStart` agrees exactly, with no tolerance, with a plain
sequential sum from 0.0, across more than one 1024-block checkpoint
boundary.

**How:** The test builds a 2500-block random model (`buildRandomModel(2500,
11)`), which section 4.2 gives 3 checkpoints (blocks 0, 1024, 2048). It
then walks every block, keeping its own running total `want` (starting at
0.0 and adding one block's duration at a time, the same forward order
`decode` itself uses to build `durationS`), and checks that
`blockStart(model, i)` equals `want` exactly before adding block `i`'s
duration, for every `i` from 0 to 2499.

**Assumptions:** Floating-point addition of the same two operands always
gives the same bit pattern. Since `blockStart` restarts from
`checkpoints[c]`, itself an exact partial sum captured mid-loop when
`buildRandomModel` computed `want`, and then adds the same remaining
durations in the same order, its result and the test's independently-kept
`want` must be bit-for-bit equal; this is not a coincidence of this
particular model, but a property of the two computations. This differs from
the whole file's general "no tolerance" assumption only in giving the
reason a checkpoint-based partial sum still matches an unbroken one.

#### `test_block_at_before_the_file_returns_block_zero`

**Checks:** `blockAt` returns block 0 for a time before the start of the
file (section 4.4, item 4).

**How:** The test calls `blockAt(model, -0.001)` on the hand model and
checks that the result is 0.

**Assumptions:** None beyond the file's assumptions.

#### `test_block_at_at_a_block_start_returns_that_block`

**Checks:** `blockAt` returns block `i` for `t` exactly at that block's
start, at every block edge of a small model.

**How:** The test calls `blockAt` at each of the hand model's 5 block
starts (0, 0.002, 0.005, 0.0075, 0.0085) and checks that each call returns
that block's index (0 through 4).

**Assumptions:** None beyond the file's assumptions.

#### `test_block_at_inside_a_block_returns_that_block`

**Checks:** `blockAt` returns the right block for a time strictly inside it,
not just at its edges.

**How:** The test calls `blockAt(model, 0.0019)`, inside block 0 (which
spans [0, 0.002)), and checks the result is 0. It calls `blockAt(model,
0.0086)`, inside block 4 (which spans [0.0085, 0.01)), and checks the
result is 4.

**Assumptions:** None beyond the file's assumptions.

#### `test_block_at_at_the_end_of_the_file_returns_the_last_nonzero_block`

**Checks:** `blockAt` returns the last block with a duration above zero for
`t` exactly at the end of the file (section 4.4, item 4).

**How:** The test calls `blockAt(model, 0.01)` (the hand model's
`durationS`) and checks that the result is 4, the last block.

**Assumptions:** None beyond the file's assumptions.

#### `test_block_at_past_the_end_of_the_file_returns_the_last_nonzero_block`

**Checks:** `blockAt` also returns the last block with a duration above
zero for `t` past the end of the file (section 4.4, item 4).

**How:** The test calls `blockAt(model, 0.02)`, past the hand model's
`durationS` of 0.01, and checks that the result is 4.

**Assumptions:** None beyond the file's assumptions.

#### `test_exact_lanes_rf_pulse_with_phase`

**Checks:** `exactLanes` gives the right whole-file points for an RF
pulse's magnitude lane and its phase lane, in ms, with the zero pad points
at each end of the magnitude lane's polyline.

**How:** The test calls `exactLanes(model, 0, 0.01)` on the hand model and
checks the `rf_mag` lane's one segment: the zero pad at time 0, the pulse's
3 magnitude points (from block 0's start of 0, delay 0.0002 and offsets [0,
0.0005, 0.001], values [0, 10, 0]), and the zero pad at the end of the file
(10 ms). It checks the `rf_phase` lane's one segment: the pulse's single
phase point, at (0 + 0.0002 + 0.0005) s = 0.7 ms, value π/2.

**Assumptions:** None beyond the file's assumptions.

#### `test_exact_lanes_trapezoid_gradient_block`

**Checks:** `exactLanes` gives the right whole-file points for a trapezoid
gradient event.

**How:** The test calls `exactLanes(model, 0, 0.01)` and checks the `gx`
lane's one segment: the zero pad at time 0, the trapezoid's 4 points (from
block 1's start of 0.002, delay 0.0001 and offsets [0, 0.0005, 0.0015,
0.002], values [0, 10, 10, 0]), and the zero pad at the end of the file.

**Assumptions:** None beyond the file's assumptions.

#### `test_exact_lanes_arbitrary_gradient_block`

**Checks:** `exactLanes` gives the right whole-file points for an arbitrary
(non-trapezoid) gradient event.

**How:** The test calls `exactLanes(model, 0, 0.01)` and checks the `gy`
lane's one segment: the zero pad at time 0, the event's 4 points (from
block 2's start of 0.005, delay 0.00005 and offsets [0, 0.0004, 0.0012,
0.002], values [0, -3, -6, 0]), and the zero pad at the end of the file.

**Assumptions:** None beyond the file's assumptions.

#### `test_exact_lanes_adc_window`

**Checks:** `exactLanes` gives the right ADC window.

**How:** The test calls `exactLanes(model, 0, 0.01)` and checks the `adc`
lane's one window: from block 3's start of 0.0075 plus the ADC's delay of
0.00002, to that plus its length of 0.0006, in ms.

**Assumptions:** None beyond the file's assumptions.

#### `test_exact_lanes_zero_pads_when_a_lane_has_no_event`

**Checks:** `exactLanes` gives just the two zero pad points, at time 0 and
at the end of the file, for a lane with no event anywhere in the file.

**How:** The test calls `exactLanes(model, 0, 0.01)` on the hand model,
whose `gz` lane has no event in any of its 5 blocks, and checks that the
`gz` lane's one segment is exactly `[[0, 0], [10, 0]]`.

**Assumptions:** None beyond the file's assumptions.

#### `test_exact_lanes_range_that_cuts_a_block`

**Checks:** `exactLanes` gives every point of a block whose whole extent is
inside the requested range, plus the pad-point neighbours, when the range
itself is narrower than the whole file.

**How:** The test calls `exactLanes(model, 0.0021, 0.0049)`, a range
strictly inside block 1 (the gx trapezoid). It checks that the `gx` lane's
one segment holds all 4 of the trapezoid's points (none of the block's
points fall outside this range), with the zero pad at time 0 before them
(nothing on the gx lane before the trapezoid) and the zero pad at the end of
the file after them (nothing on the gx lane after it).

**Assumptions:** None beyond the file's assumptions.

#### `test_exact_lanes_range_with_no_event_still_returns_neighbour_points`

**Checks:** `exactLanes` still returns the nearest point before and after a
range that has no event of its own on a lane.

**How:** The test calls `exactLanes(model, 0.009, 0.0095)`, a range inside
block 4 (the empty delay block, which has no gx event). It checks that the
`gx` lane's one segment is exactly two points: the last gx point before the
range (the end of block 1's trapezoid, at 0.0041 s) and the first after it
(the zero pad at the end of the file, since nothing on gx follows the
trapezoid).

**Assumptions:** None beyond the file's assumptions.

#### `test_min_max_lanes_matches_brute_force_for_line_lanes_over_several_views`

**Checks:** `minMaxLanes`'s minimum and maximum in each bin, for the
`rf_mag`, `gx`, `gy` and `gz` lanes, match a brute-force computation over
the exact whole-file points, across several model sizes, seeds, views and
bin counts.

**How:** The test builds 5 random models (300, 300, 3000, 3000 and 2500
blocks, with seeds 7, 7, 99, 99 and 11) and, for each, calls `minMaxLanes`
with a view and a bin count (a whole-ish view and a zoomed-in view of the
300- and 3000-block models, and an odd bin count of 137 for the 2500-block
model). For each of the 4 line lanes, it calls `lineLaneProblems`, which
computes each bin's want value with `bruteForceLineWant` (every whole-file
point in the bin, plus `numpyInterp` at the bin's two edges) and compares it
against `minMaxLanes`'s bin, within `relClose`'s tolerance. It checks that
the list of problems is empty for every lane, model and view.

**Assumptions:** None beyond the file's assumptions.

#### `test_min_max_lanes_matches_brute_force_for_the_rf_phase_lane`

**Checks:** `minMaxLanes`'s minimum and maximum in each bin of the RF phase
lane match a brute-force computation over the exact whole-file phase
points, across several model sizes, seeds, views and bin counts.

**How:** The test builds 4 random models (300, 300, 3000 and 2500 blocks)
and calls `phaseLaneProblems` for each, with the same views as the line-lane
test above (minus the 3000-block zoomed-in view). `phaseLaneProblems` works
like `lineLaneProblems`, except that an edge value only counts when the
edge falls between two points of the same RF pulse (section 4.4, item 2), so
each pulse's points are searched on their own rather than as one
whole-file polyline. It checks that the list of problems is empty for every
model and view.

**Assumptions:** None beyond the file's assumptions.

#### `test_min_max_lanes_matches_brute_force_for_adc_windows`

**Checks:** `minMaxLanes`'s ADC windows (the runs of "on" bins) match a
brute-force computation over the exact whole-file ADC windows, across
several model sizes, seeds, views and bin counts.

**How:** The test builds the same 4 random models as the RF phase test and
calls `adcLaneProblems` for each, with the same views. `adcLaneProblems`
marks each bin "on" when a whole-file ADC window overlaps it, merges runs of
"on" bins into windows at the bin edges, and compares that list, by exact
equality (bin-edge times, not interpolated values), against `minMaxLanes`'s
`windows`. It checks that the list of problems is empty for every model and
view.

**Assumptions:** None beyond the file's assumptions.

#### `test_min_max_lanes_adc_off_after_a_window_in_the_first_block_of_a_group`

**Checks:** B2 of `docs/plans/review-bugs.md`: a bin is not wrongly marked
"ADC on" when its first block is the first block of a 64-block group and
that block's own ADC window ends before the bin starts.

**How:** The test builds `buildSparseAdcModel(400, [64])` (400 blocks of 1
ms, an ADC window of 0.5 ms at the start of block 64, the first block of
group 1) and calls `adcLaneProblems` for the views `[0.0647, 0.2647, 1]`,
`[0.0647, 0.2647, 3]` and `[0, 0.4, 40]`. In the first two views, the
first bin starts at 64.7 ms, inside block 64 but after its ADC window
ends, and reaches at least two groups past group 0 with no other ADC
block; both views failed before the fix. The third view (40 bins of 10 ms
over the whole file) also checks the bin that holds the window. The test
checks that the list of problems is empty for every view.

**Assumptions:** None beyond the file's assumptions.

#### `test_min_max_lanes_matches_brute_force_across_a_checkpoint_boundary`

**Checks:** `minMaxLanes` (line lanes, RF phase and ADC) matches the
brute-force computation for a whole-file view of a model whose block count
crosses more than one 1024-block checkpoint boundary.

**How:** The test builds a 2500-block random model (checkpoints at blocks 0,
1024 and 2048) and calls `lineLaneProblems`, `phaseLaneProblems` and
`adcLaneProblems` with the whole file as the view and 200 bins, so several
bin edges fall inside the second and third checkpoint segments. It checks
that every problem list is empty.

**Assumptions:** None beyond the file's assumptions.

#### `test_min_max_lanes_bin_with_no_point_uses_only_edge_values`

**Checks:** A bin that holds no point of a lane, only interpolated values at
its two edges, gets the right minimum and maximum.

**How:** The test calls `minMaxLanes` on the hand model's `gx` lane with 10
bins over the whole file (bin width 0.001 s). It first checks, with
`bruteForceLineWant`, that bin 5 ([0.005, 0.006) s, inside block 2) has no
gx point of its own (`hadPoint` is false: the trapezoid's points are all
inside [0.0021, 0.0041] s, and the zero pad points sit at time 0 and 0.01
s, both outside this bin) and that its want value is exactly `[0, 0]` (both
of bin 5's edges interpolate, between the trapezoid's zero-valued last point
and the zero-valued pad at the end of the file, to exactly 0, with no
rounding, since the interpolation's numerator is 0). It then checks, with
`lineLaneProblems`, that every bin of this view matches the brute force,
which covers bin 5 along with the rest.

**Assumptions:** None beyond the file's assumptions.

#### `test_min_max_lanes_edge_values_follow_the_last_of_repeated_point_times`

**Checks:** When two points of a lane have the same time, an edge value
after them interpolates from the last of them, and an edge value before
them interpolates to the first of them, as the polyline does. A pypulseq RF
magnitude event always ends with two such points (the last sample, then the
zero pad at `rt[-1]`), so without this rule, each bin in the gap after a
pulse gets a value near the pulse's last sample instead of 0.

**How:** `buildRepeatedTimeModel` has two RF pulses with an empty 4 ms
block between them. The first pulse ends with (0.9 ms, 3) then (0.9 ms, 0).
The second, a block pulse, starts with (5.0 ms, 0) then (5.0 ms, 4). The
test calls `minMaxLanes` on the `rf_mag` lane with 5 bins over the whole
file (edges at 1.2, 2.4, 3.6 and 4.8 ms, all in the gap and none on a
repeated time). It checks that bins 1 to 3, which hold no point, are
exactly `[0, 0]`, that bin 0 is `[0, 5]`, and that every bin matches
`bruteForceLineWant` (`lineLaneProblems`).

**Assumptions:** None beyond the file's assumptions.

#### `test_min_max_lanes_matches_brute_force_inside_long_events`

**Checks:** `minMaxLanes` gives the right minimum and maximum when a bin
holds a long run of one event's points. For such a run it takes the
extremes from the min/max pyramid of the event's value pool, and it finds
the run by binary search on the point times, also when a bin edge cuts
inside the event.

**How:** `buildLongEventModel` has an RF event of 20,000 samples (in two
blocks) and a gradient event of 30,000 points, at a 1 µs raster, with
pseudo-random values and narrow spikes. In the gradient event, the sample
at each 64-value chunk start is a spike that grows to the right, and the
sample at each chunk end is a negative spike that grows to the left, so
the extremes of any range are chunk-edge samples: a scan that misses one
value at a chunk edge gives a wrong bin. For 12 views (the whole file, and
ranges inside the RF event and the gradient event, with 1 to 333 bins),
the test compares the `rf_mag`, `gx` and `gy` lanes with
`bruteForceLineWant` (`lineLaneProblems`) and the RF phase lane with
`phaseLaneProblems`.

**Assumptions:** None beyond the file's assumptions.

#### `test_min_max_lanes_edge_on_a_repeated_point_time`

**Checks:** A bin edge exactly on a time with two points takes the value
of the first of them, the value that the polyline reaches from the left,
and the bin that starts at that edge holds both points.

**How:** A one-block model has a gx event with the points (0, 0),
(2.5 ms, 1), (2.5 ms, 9), (5 ms, 0). The test checks that the edge of a
2-bin view over [0, 5 ms] is exactly 2.5 ms, that bin 0 is `[0, 1]` (the
last point, 9, would give `[0, 9]`), and that bin 1 is `[0, 9]` (its
maximum comes only from the point (2.5 ms, 9): a search that misses points
at the bin's start edge gives `[0, 1]`).

**Assumptions:** None beyond the file's assumptions.

#### `test_min_max_lanes_rf_phase_gap_splits_into_two_segments`

**Checks:** A gap between two RF pulses (a stretch of bins with no phase
value) splits `minMaxLanes`'s phase lane into two segments, one for each
pulse.

**How:** The test builds `buildPhaseGapModel` (an RF pulse at 0.4 ms, an
empty block, then a second RF pulse at 3.4 ms) and calls `minMaxLanes` with
4 bins over the whole file (bin width 1 ms). It checks that the `rf_phase`
lane's `segments` array has exactly 2 entries (the two middle bins have no
phase value: no point of either pulse falls in them, and neither pulse has
a second point to interpolate an edge value from, section 4.4 item 2). It
then checks, with `phaseLaneProblems`, that every bin of this view matches
the brute force.

**Assumptions:** None beyond the file's assumptions.

#### `test_min_max_lanes_adc_windows_closer_than_one_bin_merge_into_one_window`

**Checks:** Two ADC windows that land in adjacent bins, with no "off" bin
between them, are reported as a single merged window, wider than either
physical window.

**How:** The test builds `buildAdcCloseModel` (two ADC windows 0.7 ms apart,
[0.0011, 0.0014] s and [0.0021, 0.0024] s) and calls `minMaxLanes` with 4
bins over the whole file (bin width 1 ms), which puts the first window in
bin 1 and the second in bin 2. It checks that the `adc` lane's `windows`
array has exactly 1 entry. It then checks, with `adcLaneProblems`, that this
merged window (and the rest of the bins) matches the brute force.

**Assumptions:** None beyond the file's assumptions.

#### `test_lanes_for_switches_from_exact_to_min_max_at_the_point_limit`

**Checks:** `lanesFor` returns `exactLanes`'s lanes with `exact: true` for a
view whose point count is at `EXACT_POINT_LIMIT`, and `minMaxLanes`'s lanes
with `exact: false` for a view just over the limit.

**How:** The test builds `buildPointBudgetModel(2600)`, where every block
has exactly 8 points (an RF pulse's 3 magnitude and 1 phase point, plus a gx
event's 4 points), so 2500 blocks give exactly `EXACT_POINT_LIMIT` (20000)
points. It finds `tAtLimit`, the midpoint of block 2499 (so the view [0,
tAtLimit] holds blocks 0 through 2499, 2500 blocks), and `tOverLimit`, the
midpoint of block 2500 (2501 blocks). It checks with `pointsIn` that these
views hold exactly 20000 and 20008 points. It then checks that
`lanesFor(model, [0, tAtLimit * 1000], 100)` has `exact: true` and `lanes`
deep-equal to `exactLanes(model, 0, tAtLimit)`, and that `lanesFor(model, [0,
tOverLimit * 1000], 100)` has `exact: false` and `lanes` deep-equal to
`minMaxLanes(model, 0, tOverLimit, 100)`.

**Assumptions:** `pointsIn`, which this test uses to confirm the view's
point count, is not itself one of the six behaviors this file was asked to
cover, but its own correctness is a straightforward reading of `_blockPoints`
(section 4.4, item 3): for every block in the view, the RF magnitude and
phase point counts when the block has an RF event, each gradient axis's
point count when it has a gradient event, and 2 for an ADC event. The test
does not re-derive this by a separate brute force; it relies on the
function under test elsewhere in `seq_lanes.js` doing the addition section
4.4 describes.

#### `test_sequence_view_num_blocks_and_duration_s`

**Checks:** `sequenceView(model).numBlocks` and `.durationS` are the same
values the model already has (`model.numBlocks`, `model.durationS`), not
recomputed.

**How:** The test builds the hand model (`buildHandModel`, 5 blocks, end of
file 0.01 s) and checks `view.numBlocks` equals both `model.numBlocks` and
the literal `5`, and `view.durationS` equals both `model.durationS` and the
literal `0.01`.

**Assumptions:** None beyond the file's assumptions (section 2.19 preamble).

#### `test_sequence_view_block_at_and_block_start_match_seq_lanes`

**Checks:** `view.blockAt(tS)` and `view.blockStart(i)` return exactly what
`SeqLanes.blockAt(model, tS)` and `SeqLanes.blockStart(model, i)` return, for
several times (before the file, at each block start, inside a block, at and
past the end of file) and for every block of the hand model.

**How:** The test builds the hand model and compares `view.blockAt(t)`
against `SeqLanes.blockAt(model, t)` for `t` in
`[-0.001, 0, 0.0019, 0.002, 0.005, 0.0075, 0.0086, 0.01, 0.02]`, and
`view.blockStart(i)` against `SeqLanes.blockStart(model, i)` for `i` in `[0,
5)`, with `assert.equal` (exact, no tolerance).

**Assumptions:** None beyond the file's assumptions. This test does not
re-derive the expected block times (that is
`test_block_start_is_a_sequential_sum_from_zero_exactly` and the `blockAt`
tests above); it only checks that `sequenceView` forwards to the same
functions, byte for byte.

#### `test_sequence_view_block_duration`

**Checks:** `view.blockDuration(i)` equals
`tables.durations[tables.duration_index[i]]`, for every block.

**How:** The test builds the hand model and, for each block `i` in `[0, 5)`,
compares `view.blockDuration(i)` against `tables.durations[tables.duration_index[i]]`
read directly from the hand-built tables.

**Assumptions:** None beyond the file's assumptions.

#### `test_sequence_view_events_for_blocks_with_and_without_each_event`

**Checks:** `view.events(i)` returns `{rf, gx, gy, gz, adc}`, the dense event
index of each lane at block `i` (0 = none), for a block with an event on
each lane and for a block with none.

**How:** The test builds the hand model, whose 5 blocks each carry exactly
one kind of event (block0 RF, block1 gx, block2 gy, block3 ADC) except
block4, which is empty, and checks `view.events(i)` against the literal
object for each of the 5 blocks (`assert.deepEqual`). Every call also
exercises the lanes that are absent from that block (gz is absent from every
block; each lane other than the block's own event is 0 at least once).

**Assumptions:** None beyond the file's assumptions.

#### `test_sequence_view_grad_event_delay_and_exact_slices`

**Checks:** `view.gradEvent(k)` returns `{delayS, offsetsS, values}` with
`delayS` equal to `grad_delay[k - 1]`, and `offsetsS`/`values` equal
(element for element) to the pool slice of length `grad_n[k - 1]` starting
at `grad_offset_at[k - 1]`/`grad_at[k - 1]`.

**How:** The test builds the hand model and reads `view.gradEvent(1)` (the
trapezoid used as gx in block1: delay 0.0001, offsets
`[0, 0.0005, 0.0015, 0.002]`, values `[0, 10, 10, 0]` mT/m, the same event
`test_exact_lanes_trapezoid_gradient_block` uses) and `view.gradEvent(2)`
(the arbitrary gradient used as gy in block2: delay 0.00005, offsets
`[0, 0.0004, 0.0012, 0.002]`, values `[0, -3, -6, 0]` mT/m, the same event
`test_exact_lanes_arbitrary_gradient_block` uses), and compares each field
with `assert.equal`/`assert.deepEqual` (`Array.from` the typed-array fields
first, so `deepEqual` compares plain values).

**Assumptions:** None beyond the file's assumptions.

#### `test_sequence_view_grad_event_offsets_are_subarray_views_not_copies`

**Checks:** `offsetsS` and `values` are views over the model's own pool
arrays (`TypedArray.prototype.subarray`), not copies: they share the
underlying `ArrayBuffer`, and a write through one is visible in the table
the model was decoded from.

**How:** The test builds the hand model, reads `view.gradEvent(1)`, checks
`g1.offsetsS.buffer === tables.grad_offset.buffer` and
`g1.values.buffer === tables.grad_value.buffer`, then writes a new value
into `g1.values[1]` and checks that `tables.grad_value[1]` changed to match,
before restoring the original value (so later tests of the same model
object, if any ran after this one, would see the pool unchanged; in this
file each test builds its own model, so this is a defensive habit, not a
requirement of another test).

**Assumptions:** None beyond the file's assumptions. This test documents
behavior that the spec of `docs/plans/rf-profiles.md` section 4.1 calls out
explicitly ("do not change them"): it exists to show that the views are live
slices, which is exactly why a caller must not change them, not to encourage
mutation.

#### `test_sequence_view_grad_event_offsets_shared_across_events`

**Checks:** Two different gradient events whose `grad_offset_at`/`grad_n`
are equal (the pool position that `diagram_data._Pool.add` gives two
byte-equal offset arrays) give `offsetsS` views with the same contents, one
for each event, while their `delayS` and `values` differ normally.

**How:** The test builds `buildRandomModel(5, 1)`, whose fixed grad event
tables (independent of `nBlocks` and the seed) give all three gradient
events `grad_offset_at = 0` and `grad_n = 4`, i.e. the same slice of the
offset pool. It checks `tables.grad_offset_at` is `[0, 0, 0]`, then reads
`view.gradEvent(1)`, `view.gradEvent(2)` and `view.gradEvent(3)` and checks
that all three `offsetsS` deep-equal `[0, 1e-4, 6e-4, 7e-4]` (the offset
pool's only slice), while `delayS` is `0`, `5e-5` and `1e-4` and `values` is
`[0, 15, 15, 0]`, `[0, -22, -22, 0]` and `[0, 9, 9, 0]` respectively (each
event's own slice of the value pool, at `grad_at` 0, 4 and 8).

**Assumptions:** `buildRandomModel`'s event tables (`grad_delay`, `grad_n`,
`grad_offset_at`, `grad_at`, `grad_offset`, `grad_value`, and similarly the
RF tables) are fixed literals in the helper, not derived from its `nBlocks`
or `seed` parameters; only the per-block columns (`duration_index`, `rf`,
`gx`, `gy`, `gz`, `adc`) and the checkpoints depend on them. This is read
directly from `buildRandomModel`'s source in this file, not documented
elsewhere.

#### `test_sequence_view_grad_hz_per_value`

**Checks:** `view.gradHzPerValue` and the exported constant
`SeqLanes.GRAD_HZ_PER_VALUE` both equal `42.576e6 * 1e-3`, the inverse of the
factor `diagram_data.diagram_tables` uses to store gradient values in mT/m
(`Hz/m / seq_utils.GAMMA * 1e3`, with `GAMMA = 42.576e6` Hz/T).

**How:** The test builds the hand model and checks
`view.gradHzPerValue === 42.576e6 * 1e-3` and
`SeqLanes.GRAD_HZ_PER_VALUE === 42.576e6 * 1e-3` with `assert.equal`.

**Assumptions:** The factor `42.576e6 * 1e-3` is taken from `seq_utils.GAMMA`
and from `diagram_data.diagram_tables`'s `amp / GAMMA * 1e3` (read in this
task's context, not re-derived from a Python run); the test pins
`GRAD_HZ_PER_VALUE` to that same arithmetic expression, so a future change to
either side that breaks the relationship fails this test rather than only
showing up as a scale error in a chart.

#### `test_sequence_view_adc_event_and_rf_delay`

**Checks:** `view.adcEvent(k)` returns
`{delayS: adc_delay[k - 1], lengthS: adc_length[k - 1]}`, and
`view.rfDelayS(k)` returns `rf_delay[k - 1]`.

**How:** The test builds the hand model (one ADC event: delay 0.00002,
length 0.0006, the same event `test_exact_lanes_adc_window` uses; one RF
event: delay 0.0002, the same event `test_exact_lanes_rf_pulse_with_phase`
uses) and checks `view.adcEvent(1)` deep-equals
`{delayS: 0.00002, lengthS: 0.0006}` and `view.rfDelayS(1)` equals `0.0002`.

**Assumptions:** None beyond the file's assumptions.

#### `test_sequence_view_block_index_out_of_range_throws`

**Checks:** `blockStart`, `blockDuration` and `events` each throw a
`RangeError` for a block index `i` outside `[0, numBlocks)`.

**How:** The test builds the hand model (`numBlocks = 5`) and, for `i` in
`[-1, 5, 100]`, checks with `assert.throws(..., RangeError)` that
`view.blockStart(i)`, `view.blockDuration(i)` and `view.events(i)` each
throw.

**Assumptions:** None beyond the file's assumptions.

#### `test_sequence_view_event_index_out_of_range_throws`

**Checks:** `gradEvent`, `adcEvent` and `rfDelayS` each throw a `RangeError`
for an event index `k` outside `[1, count]`, where `count` is the length of
that event's own table (`grad_n.length`, `adc_delay.length`,
`rf_delay.length`).

**How:** The test builds the hand model, whose event counts are 2 gradient
events, 1 ADC event and 1 RF event. For `k` in `[0, -1, 3]` it checks
`view.gradEvent(k)` throws `RangeError` (3 is one past the 2 gradient
events); for `k` in `[0, -1, 2]` it checks that both `view.adcEvent(k)` and
`view.rfDelayS(k)` throw `RangeError` (2 is one past the single ADC and RF
event of this model).

**Assumptions:** None beyond the file's assumptions.

#### `test_sequence_view_is_frozen`

**Checks:** `sequenceView`'s return value is frozen (`Object.isFrozen`), and
assigning a new value to one of its properties, in strict mode, throws a
`TypeError` and leaves the property unchanged.

**How:** The test builds the hand model, checks
`Object.isFrozen(view) === true`, then checks that an arrow function whose
body opens with a `"use strict"` directive and assigns `view.numBlocks = 999`
throws `TypeError` (`assert.throws`), and finally checks `view.numBlocks`
still equals `model.numBlocks`.

**Assumptions:** An arrow function with an empty parameter list may open its
body with a `"use strict"` directive (the restriction on directive
prologues applies only to a non-simple parameter list, which an empty list
is not), so the assignment inside it runs in strict mode and a write to a
frozen object's own property throws, per the JavaScript specification, not
per any behavior specific to this file.

### 2.20 Sequence lanes against Python (`test_seq_lanes_golden.py`)

`test_seq_lanes_golden.py` is the golden test of task 4.4 of
`docs/plans/diagram-event-table.md`: it checks that `SeqLanes`
(`assets/seq_lanes.js`), run through Node on one sequence's real
`diagram_tables`, gives exactly the same lanes as a Python reference built
straight from `waveforms._events_in_range`'s unrounded per-block arrays —
not from `diagram_data.py` or `seq_lanes.js` itself, so a bug shared between
the tables and the JavaScript would not pass this test by accident.
`tests/js/golden_seq_lanes.js` is the Node half: given a JSON file with one
file's encoded tables, its lane metadata, and a list of `exact` or `minmax`
queries, it decodes the tables, calls `SeqLanes.decode` once, answers each
query with `SeqLanes.exactLanes` or `SeqLanes.minMaxLanes`, and writes the
results as JSON. It is not named `test_*.js`, so `node --test` does not try
to run it on its own; `test_seq_lanes_golden.py` runs it with
`subprocess.run`.

For the exact view, every point must be equal to the reference, with `==`
and no tolerance: the plan's design (section 2.7, item 3) makes the browser
and Python compute each point time with the same float64 operations in the
same order, precisely so this comparison can require bit-for-bit equality.
For the min/max view, a bin's minimum or maximum that a raw point already
reaches must also match exactly; one that only a bin-edge interpolation
reaches (`numpy.interp`, called directly, through `_edge_interp`) is compared
with `math.isclose` at a relative tolerance of 1e-12, as the plan allows
(task 4.4, item 2), because `SeqLanes` and the Python reference reach that
value by different sequences of floating-point operations.

#### `test_seq_lanes_exact_and_minmax_views_match_the_python_reference`

**Checks:** For the synthetic spin echo, gradient echo (the default 4 TRs,
600 TRs so the tables cross two 1024-block checkpoints, and 10 TRs, which
carries a "TR" definition), arbitrary-gradient and empty sequences,
`SeqLanes.exactLanes` and `SeqLanes.minMaxLanes` give the same lanes as the
Python reference, for several queries of each kind. It also checks that
`SeqLanes.decode`'s `durationS` equals `waveforms.duration_s(seq)` exactly,
and, for every sequence with at least one RF, gradient or ADC event, that
the whole-file exact lanes, rounded the way `markup._points` rounds them,
equal `waveforms.file_lanes(seq)` (with the RF phase lane's empty segments,
one for each zero-amplitude pulse, removed, since `exactLanes` never emits
one for such a pulse) — the link between this golden test and the
vb-pulseq parity that `file_lanes` itself keeps.

**How:** For each sequence, the test builds its own Python reference (the
whole-file polyline of each line lane, as `[(0, 0), *event points,
(duration, 0)]`; the phase points of each RF pulse that has at least one;
each ADC window), all as unrounded floats from `_events_in_range`. It then
builds a set of `exact` queries — the whole file; one block with an event;
a range that cuts from partway through one event block into partway
through another; a range inside a block with no event, or, when the
sequence has none (for example `spin_echo_sequence`, whose blocks all carry
an event), the widest gap between two consecutive points of some line
lane's polyline; a range near the end; and one past the end — and a set of
`minmax` queries (the whole file at 1, 7 and 800 bins; the cutting range at
50 bins; and one RF pulse's span, or the first event block's span for a
sequence with no RF, at 2000 bins, fine enough to leave most bins with no
point of their own). The empty sequence gets the two ranges the plan lists
for it instead (`[0, 0]` and `[0, min(1e-3, duration)]`), and only the
second as a `minmax` query, at 3 bins; because that set has no whole-file
query, the file_lanes link is not checked for it. All the queries of one
sequence go to `golden_seq_lanes.js` in a single Node process. For each
`exact` result, the test rebuilds the expected segment or window with the
same restriction rule as `SeqLanes.exactLanes` (task 4.4, item 1) and
compares it to the JSON result field by field, `==` throughout. For each
`minmax` result, it rebuilds each bin's expected minimum and maximum
(task 4.4, item 2): the points of the reference polyline (or, for the RF
phase lane, of the pulses' own points) that fall in the bin, by
`numpy.searchsorted` over the same array `numpy.interp` reads, plus
`_edge_interp` at the bin's two edges (`numpy.interp`, except that an edge
exactly on a point time takes the first point at that time); a value is
compared exactly when a
point in the bin already reaches it (it is `<=`, or `>=`, both edge
values), and with `math.isclose` (`rel_tol=1e-12`,
`abs_tol=1e-12 * lane_peak`) otherwise.

**Assumptions:**

- Two points of a lane can have the same time: each pypulseq RF
  magnitude event ends with the last sample and then the zero pad at the
  same offset. For an edge after such points, both `numpy.interp` and
  `SeqLanes` interpolate from the last of them. This test found that
  `SeqLanes` first took the first of them; phase 4 fixed that, and
  `test_min_max_lanes_edge_values_follow_the_last_of_repeated_point_times`
  (section 2.19) checks it. For an edge exactly on such a time, the
  reference (`_edge_interp`) and `SeqLanes` take the first of the points,
  the value that the polyline reaches from the left, where `numpy.interp`
  takes the last (phase 5; section 2.19,
  `test_min_max_lanes_edge_on_a_repeated_point_time`).
- `node` must be on `PATH` (both devShells have it); if it is not, the test
  fails with a message naming the missing dependency, rather than skipping.
- The reference and `SeqLanes.minMaxLanes` are not required to reach an
  edge value by the same floating-point operations, so an interpolated
  value gets `math.isclose` rather than `==`; every other numeric
  comparison in this file — the exact view's points and windows, a
  min/max bin's point-sourced extreme, bin-edge times, and the point and
  segment counts used to align the two sides — is exact, because both
  sides compute those from the same inputs by the same formula, or because
  they are plain counts.
- The "range inside a block with no event" and "one RF pulse's span" query
  builders read `seq.block_events` directly (as `diagram_data.py` does) to
  find an event or a pure delay block, rather than reusing `_reference_data`
  for that purpose, so the choice of query does not depend on the same
  code path the assertions then check.

### 2.21 Sequence extensions (`test_extensions.py`)

`test_extensions.py` tests `extensions.refuse_rotations`, the guard that
`cards/spectrum.py`, `cards/pns.py` and `cards/gradient_limits.py` call
before they read any gradient. Task 6.1 of
`docs/plans/diagram-event-table.md` found that pypulseq 1.5.0.post1 cannot
make a rotation and that its `Sequence.read` raises `ValueError` for a
`.seq` file with a rotation section. This file therefore makes its own
rotation sequences by hand, the way pypulseq draft PR #372 stores a
rotation: a `rotation_library` event library on the `pp.Sequence`, a
`"ROTATIONS"` entry in `seq.extension_string_idx`, or, for the one test that
checks a `.seq` file directly, an `[EXTENSIONS]` section and an `extension
ROTATIONS` section written into the file text after `pp.Sequence.write`.

#### `test_refuse_rotations_accepts_synthetic_sequences`

**Checks:** `refuse_rotations` raises nothing for each synthetic sequence
builder in `tests/synthetic.py`: none of them uses the rotation extension.

**How:** The test is parametrized over `spin_echo_sequence`, `gre_sequence`,
`arbitrary_gradient_sequence` and `empty_sequence`. For each, it builds the
sequence and calls `refuse_rotations` on it.

**Assumptions:** None.

#### `test_refuse_rotations_raises_for_a_rotation_library`

**Checks:** `refuse_rotations` raises `NotImplementedError`, with "rotation
extension" in the message, for a sequence with a non-empty
`rotation_library`.

**How:** The test builds a `gre_sequence`, sets its `rotation_library` to a
new `EventLibrary` holding one scalar-first unit quaternion (the format PR
#372 uses), and calls `refuse_rotations` inside `pytest.raises`.

**Assumptions:** None.

#### `test_refuse_rotations_raises_for_a_rotations_extension_type`

**Checks:** `refuse_rotations` raises `NotImplementedError`, with "rotation
extension" in the message, for a sequence that has registered the
`"ROTATIONS"` extension type.

**How:** The test builds a `gre_sequence`, calls
`seq.set_extension_string_ID("ROTATIONS", 1)` (as PR #372's `Sequence.read`
does while reading a file with a rotation section), and calls
`refuse_rotations` inside `pytest.raises`.

**Assumptions:** None.

#### `test_refuse_rotations_ignores_an_empty_rotation_library`

**Checks:** A `rotation_library` attribute that exists but holds no data is
not a rotation: `refuse_rotations` raises nothing.

**How:** The test builds a `gre_sequence`, sets its `rotation_library` to a
new, empty `EventLibrary`, and calls `refuse_rotations` on it.

**Assumptions:** None.

#### `test_a_rotation_file_never_reaches_a_card_unrotated`

**Checks:** A `.seq` file with a rotation section never reaches a card with
its rotation silently dropped.

**How:** The test writes a `gre_sequence` to a file, then edits the file
text to add a rotation: an `[EXTENSIONS]` section, an `extension ROTATIONS`
section with one quaternion, and the second block's extension list id set
to point at it. It reads the file with a fresh `pp.Sequence`. With pypulseq
1.5.0.post1, `Sequence.read` raises `ValueError`, and the test checks that
"ROTATIONS" is in the error message. If `Sequence.read` raises nothing (a
future pypulseq with rotation support), the test instead calls
`refuse_rotations` on the sequence `read` returned, inside `pytest.raises`
for `NotImplementedError`.

**Assumptions:**

- With pypulseq 1.5.0.post1, only the `Sequence.read` branch of this test
  runs. The `refuse_rotations` branch is unexercised until a pypulseq
  version can read the file, but it protects against a version that reads
  the rotation and drops it silently.

#### `test_gradient_cards_refuse_rotations`

**Checks:** `spectrum_card`, `pns_card`, `gradient_limits_card` and
`diagram_card` each raise `NotImplementedError` for a sequence with a
rotation library.

**How:** The test is parametrized over the four cards, each called through
a small lambda or helper function that wraps the sequence in the
`NamedSequence` (and list) form that card expects; `diagram_card` also
needs a window, so its helper gives it `waveforms.full_window`. For each,
it builds a `gre_sequence` with a non-empty `rotation_library` and calls
the card inside `pytest.raises`.

**Assumptions:** None.

#### `test_multi_file_cards_refuse_a_rotation_in_any_file`

**Checks:** `spectrum_card`, `gradient_limits_card` and `diagram_card`
raise `NotImplementedError` when any one of several files has a rotation,
not only when the first one does.

**How:** The test is parametrized over the three cards (`diagram_card`
through a helper that gives it one window, `waveforms.full_window`, on the
first file only, so the file with the rotation is checked with no window
of its own). For each, it calls the card with two named sequences, a plain
`gre_sequence` first and a `gre_sequence` with a rotation library second,
inside `pytest.raises`.

**Assumptions:** None.

### 2.22 Sequence index (`test_seq_index.py`)

`test_seq_index.py` tests `seq_index.py` (section 4.1 of
`docs/plans/cards-at-scale.md`): the dense RF, gradient and ADC event numbering of
`sequence_index`, its block times, its dtypes and its cache; `block_cache_off`; and
`rf_events`, `grad_events` and `adc_events`, which read each unique event one time with
the block cache off. The
reference numbering, `_reference_index`, is a plain loop over the blocks with one dict
for each event kind: the loop that `diagram_data.diagram_tables` had before it used the
index. Its `*_first` arrays hold play indexes, as `SequenceIndex` does (the old loop
kept block ids). The tests load `build_repeating` and `build_worst` from
`scripts/diagram_scale.py` by path, because that script is not part of the package.

#### `test_dense_columns_and_first_arrays_match_the_reference_numbering`

**Checks:** `sequence_index`'s `rf`, `gx`, `gy`, `gz` and `adc` columns, `rf_first`,
`grad_first`, `grad_first_axis`, `adc_first` and `block_id` equal `_reference_index`'s,
for a synthetic spin echo, gradient echo, empty and arbitrary-gradient sequence, and
for `build_repeating`/`build_worst` at 50 TRs (250 blocks).

**How:** The test is parametrized over the four synthetic builders and two lambdas
wrapping `build_repeating(50)`/`build_worst(50)`. For each, it builds the sequence,
computes `sequence_index(seq)` and `_reference_index(seq)`, and compares every one of
those nine arrays with `numpy.array_equal` (the dense columns cast to `int64` first,
since `sequence_index` narrows their dtype while the reference always uses `int64`).

**Assumptions:** None.

#### `test_grad_dense_numbering_follows_gx_then_gy_then_gz_within_a_block`

**Checks:** The dense numbering of gradient events follows gx before gy before gz
within one block, and reusing an already-numbered event on a different axis of a later
block does not add a new dense index, with the expected numbers worked out by hand.

**How:** The test builds a 3-block sequence by hand: block 0 has only a gz trapezoid;
block 1 has a gx and a gy trapezoid, each a different amplitude; block 2 reuses block
0's gz trapezoid object (a shallow copy with its `channel` changed to `"x"`) on gx. It
checks `index.gx`, `gy`, `gz`, `grad_first` and `grad_first_axis` against the
hand-worked values, then checks that `grad_events` yields the three events in dense
order 1, 2, 3 with the expected amplitudes (1e5, 2e5, 3e5).

**Assumptions:**

- pypulseq's gradient library keys an event by its shape and amplitude data, not by
  the channel it is later read from, so the same trapezoid object can be reused on a
  different axis and keep the same library id. This was checked directly against
  `seq.block_events` and `seq.grad_library` while writing this test; the test itself
  then relies on it to make the hand-worked expected numbers correct.

#### `test_start_s_is_the_sequential_sum_and_end_s_is_its_final_value`

**Checks:** `index.start_s` is the sequential sum of the block durations from 0.0,
`index.end_s` is that sum's final value, and `index.duration_s` is
`seq.block_durations` in play order.

**How:** The test builds `build_repeating(50)`, computes `sequence_index(seq)`, and
independently walks `seq.block_events.keys()` with a running total `t` (starting at
0.0, recording `t` before adding each block's own duration from
`seq.block_durations`). It compares `index.start_s` to that running list with
`numpy.array_equal`, `index.end_s` to the final `t` with `==`, and `index.duration_s`
to a plain array of the `seq.block_durations` values in play order with
`numpy.array_equal`.

**Assumptions:** None.

#### `test_dtype_is_uint8_for_a_sequence_with_few_unique_events`

**Checks:** For a sequence with 255 or fewer unique events of each kind, every one of
`sequence_index`'s dense columns (`rf`, `gx`, `gy`, `gz`, `adc`) has dtype `uint8`.

**How:** The test builds `gre_sequence()` (the default 4 TRs), checks that
`rf_first`, `grad_first` and `adc_first` each have at most 255 entries, and checks the
dtype of each of the five dense columns.

**Assumptions:** None.

#### `test_dtype_widens_to_uint16_past_255_unique_gradient_events`

**Checks:** Once a sequence has more than 255 unique gradient events, `gx`, `gy` and
`gz` widen to `uint16`.

**How:** The test builds `build_repeating(260)`. `build_repeating`'s phase-encode
table has 256 amplitudes (`PE_STEPS`), so 260 TRs give more than 255 unique gradient
events overall (the phase-encode events, plus the readout and the spoiler, each reused
every TR). It checks that `grad_first` has more than 255 entries and that `gx`, `gy`
and `gz` have dtype `uint16`.

**Assumptions:**

- `build_repeating`'s phase-encode table size (`PE_STEPS = 256` in
  `scripts/diagram_scale.py`) is large enough, on its own, to push the total past 255
  once combined with the readout and spoiler events; this is read from that script,
  not re-derived here.

#### `test_sequence_index_of_a_sequence_with_no_blocks`

**Checks:** `sequence_index` of a `pp.Sequence` with no blocks added has `num_blocks`
0, `end_s` 0.0, and every array (`block_id`, `start_s`, `duration_s`, `rf`, `gx`,
`gy`, `gz`, `adc`, `rf_first`, `grad_first`, `grad_first_axis`, `adc_first`) empty.

**How:** The test builds `pp.Sequence(SYSTEM)` with no `add_block` call, computes
`sequence_index(seq)`, and checks `num_blocks`, `end_s`, and the size of each of the
twelve arrays.

**Assumptions:** None.

#### `test_sequence_index_is_kept_for_one_sequence_object_and_rebuilt_after_add_block`

**Checks:** `sequence_index(seq)` returns the same object on a second call for the
same sequence, and a new, longer index after `add_block`.

**How:** The test builds `gre_sequence()`, calls `sequence_index(seq)` twice and
checks the two results are the same object (`is`), then calls
`seq.add_block(pp.make_delay(1e-3))` and checks that a third call returns a different
object whose `num_blocks` is one more than the first.

**Assumptions:** None.

#### `test_block_cache_off_restores_use_block_cache_true`

**Checks:** `block_cache_off` sets `use_block_cache` to `False` inside the block, and
restores it to `True` afterward when that was the value beforehand.

**How:** The test sets `seq.use_block_cache = True`, checks it is `False` inside
`block_cache_off`, and checks it is `True` again afterward.

**Assumptions:** None.

#### `test_block_cache_off_restores_use_block_cache_false`

**Checks:** `block_cache_off` sets `use_block_cache` to `False` inside the block, and
restores it to `False` afterward when that was already the value beforehand.

**How:** The test sets `seq.use_block_cache = False`, checks it is still `False`
inside `block_cache_off`, and checks it is `False` again afterward.

**Assumptions:** None.

#### `test_block_cache_off_restores_the_old_value_after_an_exception`

**Checks:** `block_cache_off` restores the old `use_block_cache` value even when an
exception is raised inside the block.

**How:** The test sets `seq.use_block_cache = True`, raises a `ValueError` inside
`block_cache_off` (after checking it reads `False` there), catches it with
`pytest.raises`, and checks `use_block_cache` is `True` again afterward.

**Assumptions:** None.

#### `test_block_cache_off_does_not_remove_blocks_already_in_the_cache`

**Checks:** `block_cache_off` does not remove a block that was already in
`seq.block_cache` before it ran.

**How:** The test builds `gre_sequence()`, calls `seq.get_block` on the first block id
to populate the cache, checks it is in `seq.block_cache`, runs an empty
`block_cache_off` block, and checks the block is still in `seq.block_cache` afterward.

**Assumptions:** None.

#### `test_rf_events_reads_each_unique_event_once_with_the_cache_off`

**Checks:** `rf_events` calls `seq.get_block` exactly once for each unique RF event,
with the block cache off during every call and restored afterward; it yields dense
indexes 1 to K in order; and each yielded event equals the same block's `rf` event
read separately.

**How:** The test builds `spin_echo_sequence()` (two distinct RF events), wraps
`seq.get_block` with a counting wrapper (monkeypatched onto the instance) that also
records `seq.use_block_cache` at each call, sets `seq.use_block_cache = True`, and
calls `rf_events(seq, index)`, collecting its results. It checks the call count
against the number of unique first-use blocks (`numpy.unique(index.rf_first).size`),
that every recorded cache flag is `False`, and that `use_block_cache` is `True` again
afterward. It checks the yielded dense indexes are 1 to K in order, and, for each
result, that its `delay`, `type` and `signal` equal the `rf` attribute of
`seq.get_block(block_id)` read again through the saved, unwrapped `get_block`.

**Assumptions:** None.

#### `test_grad_events_reads_each_unique_first_use_block_once_with_the_cache_off`

**Checks:** `grad_events` calls `seq.get_block` exactly once for each distinct
first-use block, not once for each unique gradient event, when two axes of one block
are both first uses; the block cache is off during every call and restored afterward;
the yielded dense indexes are 1 to K in order; and each yielded event equals the
corresponding axis attribute of that block, read separately.

**How:** The test builds a 3-block sequence where block 1 introduces both a gx and a
gy event (so it is the first-use block of two dense indexes at once), wraps
`seq.get_block` as in the RF test, and calls `grad_events(seq, index)`. It checks the
call count is 2 (the two distinct first-use blocks, not the three dense events), that
every recorded cache flag is `False`, and that `use_block_cache` is restored to
`True`. It checks the yielded dense indexes are 1, 2, 3 in order, and, for each, that
its `delay`, `type` and `amplitude` equal the `gx`/`gy`/`gz` attribute (picked by
`grad_first_axis`) of that block, read separately with the saved, unwrapped
`get_block`.

**Assumptions:** None.

#### `test_adc_events_reads_each_unique_event_once_with_the_cache_off`

**Checks:** `adc_events` calls `seq.get_block` exactly once for the sequence's one
unique ADC event (reused every TR), with the block cache off during the call and
restored afterward, and the yielded event equals that block's `adc` attribute read
separately.

**How:** The test builds `gre_sequence(num_trs=5)`, whose ADC event is the same
object reused every TR, and repeats the wrapper technique of the RF and gradient
tests. It checks the call count is 1, that the recorded cache flag is `False`, that
`use_block_cache` is restored to `True`, and that the yielded event's `delay`,
`num_samples` and `dwell` equal the `adc` attribute of that block read separately.

**Assumptions:** None.

### 2.23 Raster sampler (`test_sampling.py`)

`test_sampling.py` tests `sampling.py` (section 4.3 of
`docs/plans/cards-at-scale.md`): `GradientSampler`, which gives the gradient waveform of one axis at sorted times, from
the sequence index and the unique gradient events. The reference is pypulseq's
`seq.get_gradients()`: `_assert_matches_pypulseq` compares `sample(axis, t)` with the
`PPoly` of each axis at the same times, within a relative 1e-12 and an absolute 1e-12
times the largest |value| of the reference (section 3.5, item 2, of the plan). They are
not bit-exact: `seq_utils.gradient_offsets` adds a trapezoid's corner times in a
different order than pypulseq's `waveforms()`, and `PPoly` evaluates a line segment with
a different formula than `numpy.interp`. The comparison checks `GradientSampler`, not
pypulseq.

#### `test_whole_file_matches_pypulseq_for_synthetic_sequences`

**Checks:** For each of the four synthetic sequence builders (a spin echo, a gradient
echo, the arbitrary gradient, and the empty sequence), `GradientSampler.sample` gives
the same three-axis waveform as `seq.get_gradients()`, sampled at the raster centres
of the whole file.

**How:** Parametrized over `spin_echo_sequence()`, `gre_sequence()`,
`arbitrary_gradient_sequence()` and `empty_sequence()`. For each, `t` is
`(k + 0.5) * grad_raster_time` for `k` in `range(ceil(duration / raster))`, with
`duration` the sequence index's `end_s`; the test compares all three axes against
`seq.get_gradients()` with `_assert_matches_pypulseq`.

**Assumptions:**

- None of these raster-centre times falls within `get_gradients()`'s excluded 1e-12 s
  band around the first or last point of an axis (the `teps` zero points it adds); this
  was not arranged, only observed to hold for these four sequences.

#### `test_subrange_that_cuts_blocks_matches_pypulseq`

**Checks:** A sample range that starts in the middle of one block and ends in the
middle of another gives the same waveform as `seq.get_gradients()` on all three axes,
including an axis whose only event in the file is entirely before the range.

**How:** Builds `gre_sequence(num_trs=1)` (5 blocks: RF, phase-encode on y, readout on
x with an ADC, spoiler on z, delay). `t` is 500 evenly spaced points from the middle of
block 2 (the readout, which the range cuts) to the middle of block 4 (the delay, after
the spoiler); the phase-encode event of block 1 is entirely before this range, so it
also checks that gy is 0 for the rest of the file after its one event. Compares with
`_assert_matches_pypulseq`.

**Assumptions:** None.

#### `test_subrange_inside_a_gap_matches_pypulseq`

**Checks:** A sample range entirely inside a gap between two gradient events on the
same axis (a block with no event of its own) still gives the pypulseq value: a
straight line between the earlier event's last point and the later event's first
point.

**How:** Builds a trapezoid on x, a 2 ms delay block, and a second trapezoid on x. `t`
is 200 evenly spaced points strictly inside the delay block, 50 µs in from each edge.
Compares with `_assert_matches_pypulseq`.

**Assumptions:** None.

#### `test_single_sample_matches_pypulseq`

**Checks:** `sample` gives the pypulseq value for a `t` array of length 1.

**How:** Builds `gre_sequence(num_trs=1)`, samples at one time (the middle of the
readout block), and compares with `_assert_matches_pypulseq`.

**Assumptions:** None.

#### `test_amplitude_continues_across_a_block_junction`

**Checks:** Two extended trapezoids that together make one trapezoid, split into two
blocks at the middle of the flat top so the amplitude continues unchanged from one
block into the next, give the same waveform as `seq.get_gradients()` around the
junction: the join rule's dropped point does not create a spurious step.

**How:** `_junction_sequence(step_hz_per_m=0.0)` builds the two extended trapezoids
from the rise, flat and fall of one area-1000 trapezoid, split at the middle of the
flat top, and returns the junction time. `t` is 41 points evenly spaced over 40
gradient-raster periods centred on the junction. Compares with
`_assert_matches_pypulseq`.

**Assumptions:** None.

#### `test_tolerated_step_at_a_block_junction_matches_pypulseq`

**Checks:** A step at a block junction that is inside what pypulseq's `add_block`
accepts (up to `max_slew * grad_raster_time`) still gives the same waveform as
`seq.get_gradients()`: the join rule keeps the value of the earlier event at the
junction time even when the two events do not meet exactly.

**How:** Same construction as `test_amplitude_continues_across_a_block_junction`, with
`_junction_sequence`'s `step_hz_per_m` set to half of `max_slew * grad_raster_time`
instead of 0. The test does not check that `add_block` accepts the step; that is
pypulseq's own check, exercised here only because building the sequence requires it to
pass.

**Assumptions:** None.

#### `test_triangle_trapezoid_matches_pypulseq`

**Checks:** A trapezoid with no flat time (`make_trapezoid` gives `flat_time == 0.0`),
whose `gradient_offsets` therefore has two points at the same time with the same
value, gives the same waveform as `seq.get_gradients()`: the join rule's
duplicate-point removal does not change the value.

**How:** Builds a single-block sequence with one small-area trapezoid on x, asserts
`flat_time == 0.0` to confirm the construction is the intended triangle, samples the
whole file at the raster centres, and compares with `_assert_matches_pypulseq`.

**Assumptions:** None.

#### `test_sample_matches_the_added_events_for_an_oversampled_arbitrary_gradient`

**Checks:** `sample` gives the correct waveform for a file with an oversampled
arbitrary gradient (`make_arbitrary_grad(oversampling=True)`): B4 of
`docs/reviews/2026-09-28-code-review.md` (pypulseq issue #423), fixed by the project's
pypulseq pin (`pulseq-reports-pin-1`, the fix of pypulseq PR #424). The reference is not
`seq.get_gradients()`: pypulseq's `waveforms()` leaves out the first and the last point
of an oversampled gradient (a separate pypulseq bug, draft 03 of
`github.com/mdtisdall/pypulseq-issues`), so `_assert_matches_pypulseq`'s own reference
would be wrong for this event by construction, not only by the bug under test. The
reference is instead the polyline of the added events (the objects `make_*` returns,
before `add_block`), which does not depend on either pypulseq bug.

**How:** Builds three blocks with `SYSTEM` of `synthetic.py`: an oversampled ramp
(`make_arbitrary_grad("x", ..., oversampling=True)`, 21 samples at 50 % of `max_slew`
over half a raster, ending at a value that is not 0), an extended trapezoid back down to
0, and an ordinary trapezoid. The waveform is kept within the real `max_slew` by the
test itself, because `make_arbitrary_grad(oversampling=True)` checks the slew rate 4
times too leniently (pypulseq issue #421). The reference polyline is built from each
added event's own corner or sample points (`[0, *g.tt, g.shape_dur]` and `[g.first,
*g.waveform, g.last]` for the arbitrary and extended-trapezoid events, the rise/flat/fall
corners for the trapezoid), offset by each block's start (`numpy.cumsum` of
`seq.block_durations`) and the event's own delay, with a point dropped when it is not
more than 1e-9 s after the point before it (the same join rule as `GradientSampler`).
`GradientSampler.sample("gx", t)` is compared with `numpy.interp` on that polyline at
3999 points evenly spaced over the file, within an absolute 1e-12 times the peak of the
reference (`rtol=0`). Before the pin's fix, this test's own error is about 40 % of the
peak (checked against a pypulseq checkout at the old pin, `20b9e5e`).

**Assumptions:**

- The pin (`pulseq-reports-pin-1`) has the fix of pypulseq PR #424. A pypulseq without
  it fails this test: checked against a checkout of the old pin (`20b9e5e`).

#### `test_axis_without_events_is_zero`

**Checks:** An axis with no gradient event anywhere in the file (`get_gradients()`
gives `None` for it) samples to exactly 0 at every time.

**How:** Builds `spin_echo_sequence()` (gx and gy only), asserts
`seq.get_gradients()[2] is None` to document that gz has no event, samples gz at the
raster centres of the whole file, and checks the result against `numpy.zeros` with
`numpy.testing.assert_array_equal` (an exact check, not a tolerance).

**Assumptions:** None.

#### `test_zero_before_the_first_event_and_after_the_last`

**Checks:** The waveform is exactly 0 before the first gradient event of the file and
after the last one.

**How:** Builds a delay block, one trapezoid on x, and a second delay block. Samples
50 points inside the first delay block (before the event) and 50 points inside the
second delay block (after the event), and checks both against `numpy.zeros` exactly.

**Assumptions:** None.

#### `test_empty_sequence_is_zero_for_any_t`

**Checks:** A sequence with no gradient event on any axis gives exactly 0 for any `t`,
including a time past the sequence's own duration.

**How:** Builds `empty_sequence()` (one delay block; no RF, gradients or ADC). Samples
all three axes at `t = [0.0, 1e-3, 5.0]` (5.0 s is far past the sequence's 2 ms), and
checks each result against `numpy.zeros` exactly, with `dtype == float64`.

**Assumptions:** None.

#### `test_empty_times_gives_empty_output`

**Checks:** `sample` with an empty `t` returns an empty `float64` array, not an error.

**How:** Builds `gre_sequence(num_trs=1)`, calls `sample("gx", numpy.array([]))`, and
checks the result's dtype and shape.

**Assumptions:** None.

#### `test_invalid_axis_name_raises_value_error`

**Checks:** `sample` raises `ValueError` for an axis name other than "gx", "gy" or
"gz".

**How:** Builds `gre_sequence(num_trs=1)`, calls `sample("gw", ...)` inside
`pytest.raises(ValueError)`.

**Assumptions:** None.

The remaining tests of this section are for `GradientSampler.block_samples` and
`raster_block_lengths` (`docs/plans/diagram-lanes.md`, phase 2, task 2.0, section 4.1,
item 3): the PNS lane's per-block samples at the local times `(j + 0.5) * dt`, 0 before
a block's first gradient point and after its last, with no line across a gap and no
time drift from the block start sums. This is the rule of `PnsLanes` (`_eventSamples`
in `assets/pns_lanes.js`), not the rule of `sample`.

#### `test_block_samples_matches_sample_at_file_raster_times`

**Checks:** `block_samples` over all the blocks of a file agrees with `sample` at the
file times `(k + 0.5) * dt`, within 1e-9 of the largest |g| of the axis, for the
spin-echo, gradient-echo and arbitrary-gradient synthetic sequences.

**How:** Parametrized over `spin_echo_sequence()`, `gre_sequence()` and
`arbitrary_gradient_sequence()`. `raster_block_lengths(index, dt)` gives each block's
sample count and confirms the file is on the raster; `t_file` is `(k + 0.5) * dt` for
`k` in `range(total_samples)`. For each axis, `block_samples(axis, 0, num_blocks, dt)`
is compared with `sample(axis, t_file)` with `numpy.testing.assert_allclose`, `atol =
1e-9 * peak` and `rtol = 0`, `peak` the largest `|value|` of `sample`'s result. The two
are not exactly equal: `block_samples` computes each block's samples from its own local
raster grid, with no accumulated float error, while `sample` reads the waveform at the
block's actual start time (the sequential sum of the durations before it), which drifts
off the ideal raster grid by float rounding (`docs/plans/diagram-lanes.md`, section 2.3,
item 1). The difference is that drift only.

**Assumptions:** None.

#### `test_hand_made_ramp_and_no_event_block`

**Checks:** `block_samples` gives the exact values of a hand-made sequence: a gradient
that ramps to a nonzero value and stops there (unlike an ordinary trapezoid, whose
event is 0 at both ends), inside a block longer than the ramp, and a later block with
no gradient event on any axis.

**How:** Builds a two-block sequence: block 0 has `pp.make_extended_trapezoid` on x,
ramping from 0 to `amp = 1000.0` Hz/m over `n_ramp = 4` raster steps, and
`pp.make_trapezoid` on z with an explicit `duration` of `n_block = 7` raster steps (so
the block is longer than the x ramp); block 1 is `pp.make_delay(n_block * dt)`, with no
gradient event at all. The expected x samples of block 0 are computed by hand from the
linear-interpolation rule (`amp * t / rise` while `t` is before the ramp's own last
point, 0 after it) and compared with `numpy.testing.assert_allclose` (`rtol = atol =
1e-12`): a division (the same rule, computed by a different sequence of floating-point
operations) makes exact equality unlikely. gy, which has no event anywhere in the file,
and block 1's gx and gz, which have no event in that block, are checked against exact
zero with `numpy.testing.assert_array_equal`.

**Assumptions:** None.

#### `test_range_inside_the_file_equals_the_same_slice_of_the_whole_file`

**Checks:** `block_samples` for a range that starts and ends inside the file gives
exactly the same values as the matching slice of `block_samples` for the whole file.

**How:** Builds `gre_sequence(num_trs=3)`. `raster_block_lengths` gives each block's
sample count, used to find the sample offset and length of a block range `[2, num_blocks
- 1)`. For each axis, `block_samples(axis, 0, num_blocks, dt)` and `block_samples(axis,
2, num_blocks - 1, dt)` are compared with `numpy.array_equal` after slicing the whole-file
result to the same sample offset and length.

**Assumptions:** None.

#### `test_block_samples_invalid_axis_name_raises_value_error`

**Checks:** `block_samples` raises `ValueError` for an axis name other than "gx", "gy"
or "gz".

**How:** Builds `gre_sequence(num_trs=1)`, calls `block_samples("gw", 0, 1, dt)` inside
`pytest.raises(ValueError)`.

**Assumptions:** None.

#### `test_block_samples_bad_range_raises_value_error`

**Checks:** `block_samples` raises `ValueError` when `first`/`stop` are outside `0 <=
first <= stop <= num_blocks`: a negative `first`, a `first` greater than `stop`, and a
`stop` past the number of blocks.

**How:** Parametrized over `(first, stop) = (-1, 1)`, `(3, 1)` and `(0, 100)` on
`gre_sequence(num_trs=1)` (5 blocks), each inside `pytest.raises(ValueError)`.

**Assumptions:** None.

#### `test_block_samples_off_raster_block_raises_value_error`

**Checks:** `block_samples` raises `ValueError` for a block whose duration is not a
whole number of raster steps.

**How:** `pp.make_delay(1.5 * dt)` (pypulseq accepts this duration), the block's own
sequence, and `block_samples("gx", 0, 1, dt)` inside `pytest.raises(ValueError)`.

**Assumptions:** None.

#### `test_raster_block_lengths_with_different_block_lengths`

**Checks:** `raster_block_lengths` gives `round(duration / dt)` for each block of a
file whose blocks do not all have the same duration, and reports the file as on the
raster.

**How:** Builds `gre_sequence(num_trs=2)` (RF, phase-encode, readout, spoiler and delay
blocks, of different durations; confirmed with `len(set(index.duration_s.tolist())) >
1`). Compares `raster_block_lengths(index, dt)`'s `n` with `numpy.rint(index.duration_s
/ dt)` cast to `int64`, with `numpy.testing.assert_array_equal`, and checks `on_raster`
is `True`.

**Assumptions:** None.

#### `test_raster_block_lengths_detects_a_block_off_the_raster`

**Checks:** `raster_block_lengths` reports a file as not on the raster when one block's
duration is not within `ON_RASTER_TOLERANCE` samples of a whole number, while still
giving a sample count (the nearest whole number) for every block.

**How:** A two-block sequence: `pp.make_delay(2 * dt)`, then `pp.make_delay(1.5 *
dt)`. `raster_block_lengths(index, dt)` must give `on_raster = False` and `n =
[2, 2]` (`numpy.rint` rounds 1.5 to 2, ties-to-even).

**Assumptions:** None.

### 2.24 PNS levels (`test_pns_levels.py`)

`test_pns_levels.py` tests `pns_levels.py` (`docs/plans/diagram-lanes.md`, section
4.1, item 2, and section 4.2): `pns_levels`, which samples the gradients block by
block (`GradientSampler.block_samples`), runs the SAFE model of the pinned pypulseq
fork (`_safe_gwf_to_pns_chunk`) over them in chunks, and keeps only the stored level
(the minimum and the maximum of the total in fixed time bins) and the summary (the
peak, the peak time and the axis peaks); and `bin_samples_for`, which picks the bin
size. The reference for most tests is `seq.calculate_pns` of the pinned fork
(decision 6 of section 2.2 of the plan: this project does not test pypulseq itself,
only compares this library's output with pypulseq's or with its own other output).
`calc_pns` samples `seq.get_gradients()` at the file times `(k + 0.5) * dt`, which
drift off the ideal raster grid by float rounding of the block start time sums
(section 2.3, item 1, of the plan); `pns_levels` samples each block at its own local
raster times, with no such drift. Both then run the same chunk function, so a
relative 1e-6-of-peak tolerance (section 3.5, item 2, of the plan) covers the whole
difference, except for a file with a block off the gradient raster, where both
sample at file times and a relative 1e-9 suffices.

#### `test_summary_matches_calculate_pns_within_the_fork_tolerance`

**Checks:** For a spin echo, a gradient echo, an arbitrary gradient, and a
hand-made "border" sequence (two extended-trapezoid blocks whose gradient is not
zero at the block border between them), `pns_levels`'s peak, peak time and axis
peaks equal `seq.calculate_pns`'s (example hardware) within a relative 1e-6 of the
peak. Also checks `reason`, `hardware`, `asc_file`, `dt_s` and `on_raster` for the
example-hardware, on-raster case.

**How:** Parametrized over `spin_echo_sequence()`, `gre_sequence()`,
`arbitrary_gradient_sequence()` and a module-level `_border_sequence()` (two
`pp.make_extended_trapezoid` blocks on x, the second continuing the first's
amplitude with no step, so `add_block` accepts the junction). The reference peak,
peak time (the first sample at or above `peak * (1 - pns.PEAK_TOLERANCE)`, as
`PnsPrediction.peak_time_s`) and axis peaks come from
`seq.calculate_pns(safe_example_hw(), do_plots=False)`. `pns_levels(seq)`'s fields
are compared with `pytest.approx`: the
peak and axis peaks with `abs = 1e-6 * ref_peak`, the peak time with `abs = 1e-9`
(both use the same `(k + 0.5) * dt` formula, so the same sample index gives the same
float).

**Assumptions:** None of these sequences has two samples close enough together, in
value, to flip which one the tolerance-based peak-time search finds first.

#### `test_stored_bins_match_calculate_pns_totals`

**Checks:** Each stored bin's minimum and maximum equal the minimum and the maximum
of `seq.calculate_pns`'s totals over the same samples, within the same 1e-6-of-peak
tolerance, for the same four sequences.

**How:** Same parametrization and reference call as
`test_summary_matches_calculate_pns_within_the_fork_tolerance`. For each bin `i` of
`pns_levels(seq)`, `s0 = i * bin_samples`, `s1 = min(s0 + bin_samples,
levels.num_samples)` (the last bin can be shorter); the loop stops before a bin
whose `s1` is past the end of `calc_pns`'s own array (shorter than `pns_levels`'s
when a trailing block has no gradient event, for example `gre_sequence`'s TR
padding: `pns_levels` keeps sampling into the filters' own decay past where
`calc_pns` stopped, so a bin that straddles that point is not comparable). Each
compared bin's `level_min[i]`/`level_max[i]` are checked against
`norm[s0:s1].min()`/`.max()` with `pytest.approx(abs = 1e-6 * levels.peak)`. Asserts
at least one bin was compared.

**Assumptions:** None.

#### `test_cast_outward_bounds_every_input_value`

**Checks:** `_cast_outward` (the float32 rounding that keeps every bin's minimum and
maximum outside the float64 samples it was built from) never lands on the wrong
side of its input: the downward cast is at most the input, the upward cast is at
least the input.

**How:** 2000 uniform random float64 values in `[-1000, 1000)`
(`numpy.random.default_rng(0)`). Checks `_cast_outward(values,
down=True).astype(float64) <= values` and `_cast_outward(values,
down=False).astype(float64) >= values` elementwise, and that both results are
`float32`.

**Assumptions:** None of the 2000 values happens to already be exactly representable
in float32 for every one of them (which would make the nudging branch untested);
not arranged, only overwhelmingly likely for uniform random values.

#### `test_bin_samples_for_matches_the_formula`

**Checks:** `bin_samples_for` follows `max(floor(EXACT_MAX_S / (2 * DISPLAY_BINS) /
dt), ceil(num_samples / MAX_BINS), 1)`: 615 samples at the 10 us raster for any file
of up to 1,230,000,000 samples, and a coarser bin above that size or at a coarser
`dt`. A `pns_levels` call on a real sequence follows the same formula and gives that
many bins.

**How:** Direct calls: `bin_samples_for(0, 1e-5) == 615`,
`bin_samples_for(1_230_000_000, 1e-5) == 615`, `bin_samples_for(1_230_000_001, 1e-5)
== 616`, `bin_samples_for(2_000_000_000, 1e-5) == 1000`, `bin_samples_for(0, 2e-5) ==
307`. Then `pns_levels(gre_sequence(num_trs=6))`'s `bin_samples` is compared with
`bin_samples_for(levels.num_samples, levels.dt_s)`, and `len(levels.level_min) ==
len(levels.level_max)` equals the ceiling division of `num_samples` by
`bin_samples`.

**Assumptions:** None.

#### `test_result_does_not_depend_on_chunk_samples`

**Checks:** The stored level and the summary do not depend on `chunk_samples`: exact
equality for chunks of 1, 2 and 7 bins and one chunk larger than the whole file.

**How:** `gre_sequence(num_trs=20)`, long enough that the smallest case (1 bin per
chunk) still has more than one chunk. `reference = pns_levels(seq)` (the default
chunk size); then `pns_levels(seq, chunk_samples=...)` for `bin_samples * (1, 2, 7)`
and `bin_samples * (num_samples // bin_samples + 10)` (bigger than the file).
`level_min`/`level_max` are compared with `numpy.array_equal`; `peak`, `peak_time_s`,
`axis_peaks`, `num_samples` and `bin_samples` with `==`.

**Assumptions:** None.

#### `test_no_gradients`

**Checks:** A sequence with no gradient event gives `reason=pns.NO_GRADIENTS`, no
stored bins, a peak of 0, `peak_time_s` of `None`, zero axis peaks, and still the
example hardware and its `hw` fields.

**How:** `pns_levels(empty_sequence())`. Checks `reason`, `hardware`, `asc_file`,
the `(0,)` shape of `level_min`/`level_max`, `peak == 0.0`, `peak_time_s is None`,
`axis_peaks == {"x": 0.0, "y": 0.0, "z": 0.0}`, and `hw` against the 8 kept fields
of `safe_example_hw()`.

**Assumptions:** None.

#### `test_off_raster_block_falls_back_to_sampling`

**Checks:** A file with a block that is not on the gradient raster is reported as
`on_raster=False`, and its peak, peak time and axis peaks equal `seq.calculate_pns`
within a relative 1e-9 of the peak (tighter than the drift-based 1e-6 elsewhere in
this section, because both now sample with `GradientSampler.sample`/
`seq.get_gradients()` at the same file times; `test_sampling.py` established that
those two agree to about float rounding).

**How:** A trapezoid on x followed by `pp.make_delay(1.5 * dt)` (pypulseq's
`add_block` accepts this duration, though it is not a whole number of raster
steps). Compares `pns_levels(seq)`'s `on_raster`, `peak`, `peak_time_s` and
`axis_peaks` with the same-named values from `seq.calculate_pns(safe_example_hw(),
do_plots=False)`, as in `test_summary_matches_calculate_pns_within_the_fork_tolerance`
but with `abs = 1e-9 * ref_peak` (and `abs = 1e-9` for the peak time). It also checks
that `num_samples` is at least the length of `calculate_pns`'s result: `pns_levels`
covers the whole sequence, and `calc_pns` stops at the last gradient point.

**Assumptions:** None.

#### `test_asc_hardware_file_is_used_for_the_levels`

**Checks:** `pns_levels` reads the hardware name and the 8 kept fields of each axis
from a given gradient .asc file, instead of the example hardware, and its stored
level and summary then equal the default (example-hardware) call exactly, because
this .asc file encodes the example hardware's own numbers.

**How:** A local `write_gradient_asc` fixture (the technique of `test_pns.py`'s
fixture of the same name, not its confidential data: real .asc files are
confidential, so this one is built from pypulseq's own public
`safe_example_hw()`) writes an `asCOMP.tName` line and the `flGSWDTau*`,
`flGSWDA*`, `flGSWDStimulationLimit*`/`Threshold*` and `flGScaleFactor*` fields for
each axis. `pns_levels(spin_echo_sequence(), path)`'s `hardware`, `asc_file` and
`hw` are checked, then its `level_min`, `level_max`, `peak` and `peak_time_s` are
compared with a plain `pns_levels(seq)` call (`numpy.array_equal` for the arrays,
`==` for the scalars).

**Assumptions:** None.

#### `test_pns_levels_refuses_rotations`

**Checks:** `pns_levels` raises `NotImplementedError` for a sequence with a
rotation library, as the other gradient cards do.

**How:** `gre_sequence(num_trs=2)` with a non-empty `rotation_library` (the
technique of `test_extensions.py`'s `_with_rotation_library`), inside
`pytest.raises(NotImplementedError, match="rotation extension")`.

**Assumptions:** None.

#### `test_pns_levels_is_a_frozen_dataclass`

**Checks:** `pns_levels` returns a `PnsLevels` instance.

**How:** `isinstance(pns_levels(spin_echo_sequence()), PnsLevels)`. A smoke test of
the interface; the other tests of this section check individual fields.

**Assumptions:** None.

#### `test_chunk_samples_must_be_a_whole_number_of_bins`

**Checks:** `pns_levels` raises `ValueError` for a `chunk_samples` that is not a
positive whole number of bins.

**How:** `pns_levels(spin_echo_sequence(), chunk_samples=...)` with `bin_samples //
2` (not a multiple of `bin_samples`) and with `0`, each inside
`pytest.raises(ValueError)`.

**Assumptions:** None.

#### `test_default_chunk_samples_is_the_nearest_whole_number_of_bins_at_or_above_the_fork_size`

**Checks:** The default `chunk_samples` (no keyword given) is the smallest multiple
of `bin_samples` that is at least `CHUNK_SAMPLES`.

**How:** `gre_sequence(num_trs=20)`; `expected` is `bin_samples` times the ceiling
division of `CHUNK_SAMPLES` by `bin_samples`, computed independently of
`pns_levels`'s own formula. `pns_levels(seq, chunk_samples=expected)` and
`pns_levels(seq)` (the default) are compared with `numpy.array_equal` on
`level_min` and `level_max`.

**Assumptions:** None.

### 2.25 PNS lane in JavaScript (`test_pns_lanes.js`)

`pns_lanes.js` computes the PNS lane of the sequence diagram in the browser, with
no DOM and no network (`docs/plans/diagram-lanes.md`, phase 3): `PnsLanes.decode`
builds a model from the diagram tables and a file's `pns` hardware/raster data;
`exactView` gives the exact PNS of a short time range with the block maps of
the prototype (`prototypes/pns_lanes/pns_lanes.js` in the tag
`archive/pns-lanes-prototype`) (a scan with a checkpoint every `GROUP_BLOCKS`
blocks), not a per-sample recursion over the whole file; `levels` builds the coarser
pyramid levels of a stored level; `lanesFor` picks between the exact view and the
pyramid for one render, as `SeqLanes.lanesFor` picks between the exact and the
minimum/maximum view; `laneMeta` and `statusText` are the two pure helpers the
diagram card script (`assets/cards/diagram.js`) uses to build the PNS lane's
metadata and its status-line text (task 4.3).

The tests load `pns_lanes.js` directly, with Node's `require`, from
`src/pulseq_reports/assets/pns_lanes.js`, the same way `test_seq_lanes.js` loads
`seq_lanes.js`. They use `node:test` and `node:assert/strict`, and no browser or
DOM. There is no pypulseq in this file (rule: lean on pypulseq, but there is no
pypulseq reference for a pure JavaScript module): every model is hand-made typed
arrays, built by `buildPnsTables` (a seeded pseudo-random block table, as
`test_seq_lanes.js`'s `buildRandomModel` is, reused by most tests) or by a fully
explicit small table (`buildBorderTables`, `buildOffRasterTables`, and the two
empty/no-gradient tables of the last two tests). The hardware numbers
(`hwSet`/`HW`) are pypulseq's own `safe_example_hw()` values, copied from
`prototypes/pns_lanes/README.md`'s table, not read from pypulseq.

Two independent references stand in for a Python or pypulseq comparison:
`bruteForceTotals` re-derives the whole model (the gradient of each axis, the
three filters, the axis fractions and the total) directly from the tables, in a
single pass over the whole file, never calling any function of `pns_lanes.js`.
`collectPlainRecursion` calls the module's own `_internal._plainRecursion` (the
whole-file, zero-initial-state recursion), which is not used by `exactView`
itself (the block maps are). Comparing `exactView`'s output (the block maps) to
`_plainRecursion`'s output over the same range is the worker spec's rule 2: the
two are the same model, so they must agree to 1e-12 of the peak, not bit for bit
(`assertWithinPeakTol`). A value that comes from the same call (for example the
sample times `exactView` returns) is compared with no tolerance.

**Assumptions for the whole file:**

- The functions take only plain values (numbers, arrays, typed arrays) and return
  only plain values. Nothing in a test depends on the page or a browser.
- `assertWithinPeakTol(got, want, tol)` checks
  `max(|got[i] - want[i]|) <= tol * max(peak(got), peak(want))`, the same
  "relative to the peak, not to each value" rule the golden test of section 2.26
  will use against Python. `tol` is 1e-12 everywhere in this file (plan section
  3.5, item 1); the prototype measured 3.5e-15 for the same comparison.
- `buildPnsTables` always places a 0-duration block at index 5 and a block with
  no event on any axis at index 10 (when the model has more than 10 blocks), so
  both edge cases are in every randomized model regardless of the seed.
- A model built only for one test (`buildBorderTables`, `buildOffRasterTables`,
  and the two models of the last two tests) is documented at its own
  definition, not here.

#### `test_brute_force_matches_plain_recursion_on_a_hand_model`

**Checks:** The model's own per-sample recursion (`_internal._plainRecursion`)
agrees with an independent, from-scratch implementation of the SAFE model's
formulas (`bruteForceTotals`), to 1e-12 of the peak. This is rule 1 of the tests
the worker spec asks for.

**How:** Builds an 80-block pseudo-random model (`buildPnsTables(80, 7)`, which
includes a 0-duration block and a no-gradient block by construction), decodes it,
computes `bruteForceTotals` directly from the tables and `collectPlainRecursion`
from the model, and compares the two whole-file total arrays with
`assertWithinPeakTol`.

**Assumptions:** None beyond the file's assumptions.

#### `test_exact_view_matches_plain_recursion_across_many_views`

**Checks:** `exactView` (the block maps, with the checkpoint skip) agrees with
`_plainRecursion` (the plain per-sample recursion) to 1e-12 of the peak, for views
that start inside many different blocks and checkpoint groups of a model larger
than `3 * GROUP_BLOCKS`. This is rule 2 of the tests the worker spec asks for.

**How:** Builds a 500-block pseudo-random model (more than `3 * 64` blocks, so
`GROUP_BLOCKS` is confirmed to be 64 and the model crosses more than 3 checkpoint
groups), computes each block's start time independently (a running sum of the
durations, not calling the module), and for each of 12 starting blocks (block 0,
1, the blocks around the first and second checkpoint boundaries, and others up to
the last block) and 4 span lengths, calls `exactView` with a large enough `bins`
that the "samples" kind is always chosen, and compares its `total` array against
the matching slice of the whole-file `_plainRecursion` array (found by the
module's own `sampleRangeFor`) with `assertWithinPeakTol`. The sample times
themselves (`view.t`), which come from the exact formula `(k + 0.5) * dt` with no
filter arithmetic, are checked with no tolerance.

**Assumptions:** None beyond the file's assumptions.

#### `test_gradient_not_zero_at_a_block_border`

**Checks:** The block map's boundary term (`x[0] = (g[0] - g_prev_last) / dt`)
is correct when the gradient does not return to 0 at a block border: the same
1e-12-of-the-peak checks as the previous two tests, on a 2-block model built so
that block 0's last sample and block 1's first sample are both exactly 8 (mT/m),
a continuous, non-zero gradient across the junction (unlike the "ends at 0" case
the prototype's own README already checked).

**How:** `buildBorderTables` gives block 0 (10 samples) a gx event whose last two
points both hold the value 8 through the block's end, and block 1 (8 samples) a
gx event that starts at offset 0 already at 8 before ramping to 0. The test
checks `bruteForceTotals` against `collectPlainRecursion` for the whole file, then
checks `exactView` against the same `_plainRecursion` reference for 4 ranges:
inside block 0, spanning most of the file, starting exactly at the border, and
straddling the border.

**Assumptions:** None beyond the file's assumptions.

#### `test_exact_view_bins_match_brute_force_binning_of_the_samples`

**Checks:** `exactView`'s "bins" kind (the minimum and the maximum of the total in
each of `bins` bins) equals a brute-force binning of the same range's "samples"
kind values, by the exact formula of the interface doc
(`floor((t - t0) / span * bins)`, clamped), for several bin counts; and the
"samples"/"bins" switch happens exactly at more than `2 * bins` samples, not at
`2 * bins` itself.

**How:** Builds a 60-block model of uniform 20-sample blocks (`buildPnsTables(60,
23, {durationOptionsDt: [20]})`), so a view's sample count starting at sample 0 is
exactly controllable (`t1 = (count - 1 + 0.5) * dt` selects exactly `count`
samples, by `sampleRangeFor`'s own rule). For `bins` in `{3, 7, 16}` and `count` in
`{2 * bins, 2 * bins + 1, 5 * bins + 3}`, it checks that `count = 2 * bins` still
gives kind "samples" (the switch has not happened) and that the two larger counts
give kind "bins"; for those, it re-fetches the same range in "samples" kind (with
`bins` large enough that the switch cannot trigger), bins those samples by hand
with the interface formula, and compares the resulting minimum and maximum arrays
to `exactView`'s own "bins" output, and the bin edges to the documented formula
`edges[k] = t0 + span * k / bins`, all with exact equality (both come from the
same underlying sample values, only reduced by `min`/`max`, which introduces no
rounding).

**Assumptions:** None beyond the file's assumptions.

#### `test_exact_view_bins_empty_bin_is_plus_minus_infinity`

**Checks:** A bin with no sample in it gets `min = +Infinity`, `max = -Infinity`
(interface doc), not 0 or `NaN`.

**How:** Builds a 40-block, 200-sample model, then asks `exactView` for a view
`[0, 5 * numSamples * dt]` (5 times the file's own duration) with 20 bins: the
bins spread evenly over the whole requested range, but real samples exist only in
the file's own, much shorter span, so only the first few bins can ever hold a
sample. The test checks that kind is "bins" and that at least one bin has
`max === -Infinity` and, for every such bin, `min === Infinity`.

**Assumptions:** None beyond the file's assumptions.

#### `test_exact_view_sample_range_edge_cases`

**Checks:** The sample range `[t0, t1]` behaves correctly at its edges (plan
interface doc): a view that starts before the file and ends after it returns
every sample; a view with `t0 = t1` exactly on one sample's centre time returns
that one sample; a view strictly between two samples' centre times returns none.

**How:** Builds a 30-block model with two block-duration options, computes the
whole-file `_plainRecursion` reference, and checks three `exactView` calls: `(-5,
numSamples * dt + 5)` gives all `numSamples` samples, with the first and last
`t` values matching `(k + 0.5) * dt` exactly and the totals matching the
reference within 1e-12 of the peak; `(t, t)` at sample 12's centre time gives
exactly one sample, matching the reference at index 12; and a `[t0, t1]` strictly
inside the gap between sample 12 and sample 13 gives an empty result.

**Assumptions:** None beyond the file's assumptions.

#### `test_levels_pyramid_matches_brute_force_min_max`

**Checks:** `PnsLanes.levels` builds the pyramid of plan section 4.5 correctly:
each level is the minimum/maximum of up to 4 bins of the level below it, the
pyramid stops after the first level of length 1, and level 0 is the same
Float32Array objects passed in, not copies.

**How:** For hand-made stored levels of length 1, 4, 5 and 17 (pseudo-random
values, seeded), compares `PnsLanes.levels` against `bruteForcePyramid`, an
independent implementation in the test file (using `Math.min`/`Math.max` over
each chunk of 4, rather than the module's own loop), level by level, with exact
equality (a min/max reduction introduces no floating-point rounding, so the two
must agree bit for bit regardless of the order of operations). It also checks
that the last level always has length 1, and that `result[0].min`/`max` are the
identical objects (`assert.strictEqual`) passed in as the stored level.

**Assumptions:** None beyond the file's assumptions.

#### `test_lanes_for_exact_branch_is_percent_and_matches_the_plain_recursion`

**Checks:** `lanesFor`'s item 1 (the exact view): a short, sample-poor view gives
one segment of `[t_ms, percent]` points equal to the exact per-sample recursion
(scaled to percent and milliseconds), with `exact: true`, `binMs: null`,
`gap: false`; a short but sample-rich view gives the same zigzag shape as
`exactView`'s own "bins" kind, with `minmax: true`.

**How:** `buildPyramidModel(8)` builds a model whose stored level comes from its
own `_plainRecursion` (the worker spec's "so that the numbers are realistic"):
it decodes a 1100-block model once with a placeholder level to get the exact
per-sample totals, bins those totals into a real stored level of `binSamples = 8`
by hand, and decodes the same tables again with that level. For a 100-sample view
(`[0, 1] ms`), it checks `lanesFor`'s single segment against the
`sampleRangeFor`-selected slice of the exact totals (`assertWithinPeakTol`, since
`lanesFor`'s exact branch is `exactView`, not `_plainRecursion`) and each point's
time against `(k + 0.5) * dt * 1000`. For a 500-sample view with 10 bins (forcing
the "bins" kind), it calls `exactView` directly for the same range and bins, and
checks that `lanesFor`'s zigzag segments (read back into a `{edge_ms: [min,
max]}` map by `zigzagBins`, as `test_seq_lanes.js`'s `gotLineBins` reads
`minMaxLanes`'s segments) hold exactly `[view.min[k] * 100, view.max[k] * 100]`
at each non-empty bin's edge, and that an empty bin is absent from the map.

**Assumptions:** None beyond the file's assumptions.

#### `test_lanes_for_pyramid_branch_matches_brute_force_of_overlapping_level_bins`

**Checks:** `lanesFor`'s item 2 (the pyramid, for a view longer than
`EXACT_MAX_S`): the level chosen is the largest with `binSamples * dt <= (span /
bins) / 2`; each display bin equals the minimum/maximum of the chosen level's
bins that overlap it (the `floor`/`ceil` index range of the interface doc);
`binMs` is that level's bin width in ms; `gap` is `false` when a level fits.

**How:** Uses the same `buildPyramidModel(8)` model as the previous test, with a
view `[0, 20]` s (longer than `EXACT_MAX_S`) and 100 bins. It finds the expected
level independently, by reading the model's own public `levels` array (not a
private helper) and applying the documented formula, then computes each display
bin's expected minimum/maximum by hand from that level's `min`/`max` arrays, and
compares against `lanesFor`'s zigzag output (`zigzagBins`) bin by bin, with exact
equality (both reduce the same stored `Float32Array` values by `min`/`max`, so
there is no rounding to tolerate). It also checks `binMs` and that `gap` is
`false`.

**Assumptions:** A level exists that fits this test's span and bin count
(`assert.notEqual(chosen, -1)`); the test's own span/bins were chosen so that
this always holds, but the assertion documents the requirement rather than
letting a wrong result pass silently if it ever did not.

#### `test_lanes_for_gap_true_when_even_the_stored_level_is_too_coarse`

**Checks:** `gap` is `true` when even the stored level (level 0, the finest) has
bins longer than half the display bin (plan section 4.2's "gap": zooming in
further would not show anything the stored data does not already show at this
resolution), and `binMs` then reports level 0's own bin width.

**How:** Uses `buildPyramidModel(8)` again, with a view `[0, 20]` s (longer than
`EXACT_MAX_S`) and a bin count chosen so that `(span / bins) / 2` is smaller than
level 0's own bin width (`bins = ceil(span / (2 * B0)) + 1000`, comfortably past
the threshold). Checks `exact: false`, `gap: true`, and `binMs === B0 * 1000`.

**Assumptions:** None beyond the file's assumptions.

#### `test_on_raster_false_never_uses_the_exact_view`

**Checks:** `model.onRaster` is `false` when a block's duration is not within
1e-6 samples of a whole number; `exactView` then throws rather than returning a
wrong answer; `lanesFor` never calls it (no throw), and draws a short view from the
stored level. `gap` stays `false` when a level fits: it says only that the stored
level is too coarse, and the card script reads `model.onRaster` for a file without
an exact view.

**How:** `buildOffRasterTables` gives one block a duration of `1.5 * dt` among
otherwise whole-sample blocks. After decoding, the test checks `model.onRaster
=== false` and that `PnsLanes.exactView` throws. It then calls `lanesFor` with a
20-sample span and 2 bins, chosen so that level 0 still satisfies `(span / bins)
/ 2 >= B0` (so this is not the separate "even the stored level is too coarse"
case of the pyramid tests above). It checks `exact: false`, `gap: false` and
`minmax: true`. A second call with a
span already longer than `EXACT_MAX_S` is checked only for not throwing and
`exact: false`, since that path does not depend on `onRaster` at all.

**Assumptions:** None beyond the file's assumptions.

#### `test_grad_scale_multiplies_every_gradient_sample`

**Checks:** `PnsLanes.decode` reads `pns.gradScale` and multiplies every
gradient sample by it before the SAFE model (`grad_value / 1000 * gradScale`
in T/m): a model decoded with `gradScale: 2` agrees, within 1e-12 of the
peak, with a model of the same tables with every `grad_value` doubled and no
`gradScale` key. A missing `gradScale` defaults to exactly `1.0`: a model
decoded with no `gradScale` key gives bit-identical totals to one decoded
with an explicit `gradScale: 1.0`.

**How:** Builds a 60-block pseudo-random model (`buildPnsTables(60, 29,
{durationOptionsDt: [15, 25], noEventProb: 0.3})`), decodes it once with
`gradScale: 2` and once, from a copy of the tables with every `grad_value`
doubled, with no `gradScale` key, and compares the two whole-file totals
(`collectPlainRecursion`) with `assertWithinPeakTol` at `1e-12` (the two take
different code paths to the same number: one scale multiply per sample
against a pre-doubled input table, so this is rule 2 of the worker spec, not
bit-exactness). It then decodes the original tables twice more, once with no
`gradScale` key and once with `gradScale: 1.0`, and checks the two totals
arrays with `assert.deepEqual` (exact equality: multiplying a T/m value by
`1.0` rounds to itself in IEEE 754 arithmetic, so this is the same code path
both times).

**Assumptions:** None beyond the file's assumptions.

#### `test_empty_file_has_no_samples_and_no_exact_view_crash`

**Checks:** A file with 0 blocks decodes to `numBlocks = 0`, `numSamples = 0`,
`onRaster = true` (no block ever contradicts it); `exactView` returns an empty
"samples" result rather than throwing or indexing out of bounds; `lanesFor`
returns `{lane: {...meta, segments: []}, exact: true, binMs: null, gap: false}`
(the interface doc's "an empty file" case).

**How:** Decodes a model from tables where every array (`duration_index`,
`gx`/`gy`/`gz`, all the `grad_*` tables) has length 0, then checks `exactView(0,
1, 10)` gives empty `t`/`total` arrays and `lanesFor` gives exactly the
documented empty-file result (`assert.deepEqual` against the literal expected
object).

**Assumptions:** None beyond the file's assumptions.

#### `test_file_with_no_gradient_event_is_all_zero`

**Checks:** A file with blocks but no gradient event on any axis anywhere gives
an exact total of 0 for every sample (the zero-input, zero-initial-state
recursion has nothing to filter).

**How:** Decodes a 20-block model of uniform 15-sample blocks with `gx`, `gy` and
`gz` all 0 and empty gradient-event tables, asks `exactView` for the whole file,
and checks that every one of the `numSamples` total values is exactly `0`, with
no tolerance (every intermediate value of the recursion is an exact `0` times a
finite coefficient, which stays exactly `0` in IEEE 754 arithmetic).

**Assumptions:** None beyond the file's assumptions.

#### `test_lane_meta_has_the_fixed_lane_fields_and_the_peak_dependent_domain`

**Checks:** `PnsLanes.laneMeta` gives the PNS lane's fixed fields (`id: "pns"`,
`title: "PNS"`, `unit: "%"`, `color: "ink-2"`, `kind: "line"`, `ticks: [0, 100]`,
`tick_labels: ["0", "100"]`, `empty: false`, `fill: 0.0`), and a `domain` whose low
end is always 0 and whose high end is `1.1 * max(100, 100 * peak)` (plan section
4.5, item 4): the same `[0, 110]` the old PNS card's chart used for a peak at or
below the limit, widened to show a peak above it.

**How:** Calls `PnsLanes.laneMeta` with a summary object and checks each fixed
field. For `domain`, it calls `laneMeta` with peak 0.5, 0.86, 1.0 and 1.5 and
checks the low end is exactly 0 and the high end is within 1e-9 of 110, 110, 110
and 165 (a tolerance, since `1.1 * 100` is not exact in float64).

**Assumptions:** None beyond the file's assumptions.

#### `test_status_text_exact`

**Checks:** `PnsLanes.statusText` gives "PNS: exact." whenever `result.exact` is
true.

**How:** Calls `PnsLanes.statusText({exact: true, binMs: null, gap: false}, true)`
and checks the result.

**Assumptions:**

- A file that is not on the gradient raster never reaches `lanesFor`'s exact
  branch, so passing `onRaster: false` alongside `exact: true` is not a case
  `lanesFor` itself produces; the test only checks that `statusText` reads
  `exact` first.

#### `test_status_text_bins_with_a_sensible_digit_count`

**Checks:** For the minimum/maximum branch, `statusText` formats the bin width to
3 significant figures, not with the module's own float64 precision.

**How:** Calls `PnsLanes.statusText` with `binMs` of 6.15, 393.6 and 1574.4 (`gap:
false`, `onRaster: true`) and checks the result is "PNS: minimum and maximum in
bins of 6.15 ms.", "...394 ms." and "...1570 ms." respectively.

**Assumptions:** None beyond the file's assumptions.

#### `test_status_text_gap_adds_the_zoom_in_sentence`

**Checks:** `gap: true` adds a sentence naming `PnsLanes.EXACT_MAX_S` as the span
to zoom in to for exact values; `gap: false` adds nothing.

**How:** Calls `PnsLanes.statusText({exact: false, binMs: 24.6, gap: true}, true)`
and checks the result is the bins sentence followed by "Zoom in to
`${PnsLanes.EXACT_MAX_S}` s or less for the exact values.". It then calls the same
with `gap: false` and checks the result is only the bins sentence.

**Assumptions:** None beyond the file's assumptions.

#### `test_status_text_off_raster_replaces_the_gap_sentence`

**Checks:** `onRaster: false` gives the "not on the gradient raster" sentence
instead of the "zoom in" sentence, even when `gap` is also true (plan section
4.5, item 2): zooming in would not reach an exact view for such a file, so
telling the reader to do it would be wrong.

**How:** Calls `PnsLanes.statusText({exact: false, binMs: 24.6, gap: true},
false)` and `PnsLanes.statusText({exact: false, binMs: 24.6, gap: false}, false)`
and checks both give the bins sentence followed by "The file is not on the
gradient raster, so there is no exact view." with no "zoom in" sentence in either
case.

**Assumptions:** None beyond the file's assumptions.

### 2.26 PNS lane against Python (`test_pns_lanes_golden.py`)

The golden test of task 4.5 of `docs/plans/diagram-lanes.md`: the browser module
`PnsLanes` (`src/pulseq_reports/assets/pns_lanes.js`) against the Python
`pns_levels.pns_levels` pipeline, as `test_seq_lanes_golden.py` checks `SeqLanes`
against a Python reference. `_run_golden` writes one sequence's diagram tables and its
`pns` object (plan section 4.4, including `gradScale`, decision 14) to a JSON file,
runs `tests/js/golden_pns_lanes.js` with Node on it, and reads back the JSON result:
`PnsLanes.decode`, one `exactView` call for the whole file (forced to the "samples"
kind by a bin count far larger than the sample count, so every sample comes back,
never a minimum/maximum reduction), and the decoded pyramid (`model.levels`).

The Python reference (`_python_reference_totals`) is the same pipeline `pns_levels`
itself runs (its own docstring, items 1 to 3), built again independently in this
file, in a single call instead of `pns_levels`'s chunks: `GradientSampler.block_samples`
of gx, gy and gz for the whole file, divided by `seq.system.gamma`, through pypulseq's
`_safe_gwf_to_pns_chunk` (one chunk, `state=None`, example hardware), scaled by 0.01
and combined as `sqrt(x^2 + y^2 + z^2)`. The pinned fork's chunk function is exact for
any chunk size (`test_pns_levels.py`'s `test_result_does_not_depend_on_chunk_samples`;
lean on pypulseq, decision 6: not re-tested here), so the test also asserts
`pns_levels(seq).peak == totals.max()` exactly, as a check that this file's one-call
reference really is `pns_levels`'s own computation, not a second implementation of
PNS.

#### `test_pns_lanes_exact_view_and_levels_match_the_python_pipeline`

**Checks:** `PnsLanes.decode` and `exactView`, run through Node on one sequence's real
diagram tables and `pns` object, give the same whole-file PNS total, at the same
sample times, as the Python `pns_levels` pipeline, within a relative 1e-12 of the peak
(plan section 3.5, item 1); the stored level (`pns_levels`'s `level_min`/`level_max`)
bounds every one of those JS exact samples in its own bin (plan section 4.2), within
the same relative 1e-12 slack (the stored level comes from Python's chunked SAFE
filter, the JS samples from the block maps -- different code paths over the same
model); and each level of the decoded pyramid (`PnsLanes.levels`) is exactly the
minimum/maximum of the 4 bins of the level below it (no rounding: a min/max reduction
of already-float32 values).

**How:** Parametrized over six sequences: the three synthetic builders of
`tests/synthetic.py` that have a gradient event (`spin_echo_sequence`,
`gre_sequence`, `arbitrary_gradient_sequence`; the empty sequence has no PNS bins to
compare); a "border" sequence of two extended trapezoids whose gradient is not zero
at the block junction, built again in this file (not imported from
`test_pns_levels.py`'s `_border_sequence`, so the two files need no cross-import); a
repeating sequence of 225 blocks (45 TRs of `gre_sequence`'s 5 blocks each), more
than `3 * PnsLanes.GROUP_BLOCKS` (192), so the test crosses more than 3 of the
JavaScript block map's checkpoint groups; and a sequence built with
`pp.Opts(gamma=11.262e6)` (sodium), with a small trapezoid on every axis (areas
scaled down from the proton sequences', since sodium's smaller gamma gives a smaller
max-gradient area in 1/m for the same mT/m hardware limit), so a wrong `gradScale`
would show on all three axes.

For each sequence: `_run_golden` builds the diagram tables, `pns_levels(seq)`, and
`gradScale = seq_utils.GAMMA / seq.system.gamma`, writes them as the `pns` object of
plan section 4.4 (`levels` encoded with `diagram_data.encode_tables`, as float32),
and runs `golden_pns_lanes.js`. The JS sample times are checked against
`(k + 0.5) * dt` with exact array equality; the JS totals against the Python
reference with `max(|diff|) <= 1e-12 * peak`; each stored bin's `level_min`/`max`
against the min/max of the JS samples in that bin, with the same tolerance; and the
pyramid level by level, with exact equality, against the level below it.

**Assumptions:**

- `golden_pns_lanes.js`'s `t0`/`t1`/`bins` (`-1.0`, `numSamples * dt + 1.0`,
  `numSamples * 2 + 16`) force `exactView`'s "samples" kind for the whole file: the
  range covers every sample regardless of the file's own duration (`sampleRangeFor`
  clamps to `[0, numSamples - 1]`), and the bin count is always more than half the
  sample count.
- All six sequences are on the gradient raster (`PnsLanes.exactView` refuses a file
  that is not, and `GradientSampler.block_samples` raises for it); the test asserts
  `onRaster` is `true` as a guard, not as its own coverage goal (off-raster PNS is
  `test_pns_levels.py`'s concern, per `docs/plans/diagram-lanes.md` section 4.1, item
  3).
- The `sodium_gamma` case needs `PnsLanes.decode` to read `pns.gradScale`
  (decision 14 of `docs/plans/diagram-lanes.md`).

### 2.27 |G| lane (`test_g_lanes.js`)

`g_lanes.js` computes the |G| lane of the sequence diagram in the browser, with no
DOM and no network (`docs/plans/diagram-lanes.md`, phase 5): |G| =
sqrt(gx^2 + gy^2 + gz^2) (mT/m, the table units), the magnitude of the gradient
vector, 0 wherever none of its three axes has an event, or outside the span an
axis's own event covers (before its own delay, or after its own last point),
whatever the block's own duration -- so a block can be longer than its events (a
short trapezoid with a longer delay, ADC or RF ringdown in the same block, or a
gradient that starts only after a delay) and the padding still reads as the real
value 0, never "no value". It is the prototype's `gMagMinMax`
(`prototypes/pns_lanes/slew_g.js` in the tag
`archive/pns-lanes-prototype`, its "|G|" section only) made into library code, with
that padding added: `GLanes.decode` builds, once, the per-(triple, block duration)
piecewise-quadratic geometry (keyed by duration as well as by the triple of dense
gradient event ids, because the padding depends on the block's own duration, which
one triple can play at more than one length) and the group tree over a
`SeqLanes.decode` model's blocks; `minMax` gives the exact minimum and maximum of
|G| in each of a view's time bins; `lanesFor` turns that into the chart's
minimum/maximum zigzag form, the only form the |G| lane ever uses (unlike a value
lane, |G| is not linear between two axes' corner points, so a polyline through the
corner values would be wrong at any zoom); `laneMeta` builds the lane object
without "segments".

The tests load `seq_lanes.js` and `g_lanes.js` directly, with Node's `require`,
the same way `test_pns_lanes.js` loads `pns_lanes.js`. Every model is hand-made:
`buildGModel` (a seeded pseudo-random block table, reused by most tests, in the
style of `test_seq_lanes.js`'s `buildRandomModel` and `test_pns_lanes.js`'s
`buildPnsTables`), `buildManyEventsTables` (a seeded pseudo-random block table with
many thousands of distinct gradient events, for the cache-key test below), or a
fully explicit small table (`buildBorderTables`, `buildTailPaddingTables`,
`buildHeadPaddingTables`, and the empty/no-gradient tables of
`test_empty_file_has_zero_peak_and_no_lane_segments` and
`test_file_without_gradients_is_all_zero_not_empty`).
Unlike `test_pns_lanes.js`, `GLanes.decode` takes a
full `SeqLanes.decode` model (not the raw tables directly), so `buildGModel`
builds every table `SeqLanes.decode` requires (empty RF and ADC tables:
`g_lanes.js` reads none of them). `buildGModel`'s events keep a nonzero delay, and
a block that has an event draws its own duration independently of which events it
plays and of their own delay or span, so it commonly has real padding before its
first event and after its last: real `diagram_tables` output never has the
opposite (a block shorter than an event it carries: `add_block` sets a block's
duration to the longest of its own events), so a block with an event never draws
the 0 duration option either, and the forced 0-duration block (below) is given no
event.

An independent brute force (`bruteMinMax`/`bruteBlockGRange`, never calling any
function of `g_lanes.js`) applies the same piecewise-quadratic rule the module's
doc describes, padded to the whole block the same way, to every block of a bin,
clip by clip, instead of the module's group tree, the same relationship
`prototypes/pns_lanes/run_slew_g.js`'s own brute force has to `slew_g.js`. A bin
with no block overlapping it at all keeps `[Infinity, -Infinity]` ("no value"),
the convention `GLanes.minMax` itself uses for such a bin (only reachable when a
view reaches outside the file, since blocks otherwise tile the file with no
gaps); a bin, or part of one, that lies in a block's own padding gets the real
value 0.

**Assumptions for the whole file:**

- The functions take only plain values (numbers, typed arrays, a `SeqLanes.decode`
  model) and return only plain values. Nothing in a test depends on the page or a
  browser.
- `assertMinMaxMatches(got, want, tol)` checks that `got` and `want` agree exactly
  on which bins are empty, and that every other bin's minimum and maximum agree
  within `tol` of the overall peak (the fast path and the brute force both use the
  closed-form quadratic extrema, but a clipped sub-piece computes its own `ta`/`tb`
  from a division a whole, unclipped piece does not, so the two can differ in the
  last bit). `tol` is 1e-12 everywhere in this file, the same bound the prototype's
  own brute-force comparison and `test_pns_lanes.js` use.
- `buildGModel` always places a 0-duration block with no event at index 5, a block
  with no event on any axis at index 10, and a block with an event on only the gx
  axis at index 11 (`opts.forceSpecialBlocks: false` turns this off, for the "file
  without gradients" tests, which need every block to have no event).

#### `test_min_max_matches_brute_force_across_many_views`

**Checks:** `GLanes.minMax` equals the independent brute force, exactly on which
bins are empty and within 1e-12 of the peak otherwise, for the whole file, a view
with more bins than there are blocks in many groups, a zoomed view that cuts
blocks at both ends, a view inside a single block, a view that crosses more than
`GLanes.GROUP_BLOCKS` (64) blocks between its two edges' own blocks (so the group
tree's own range query is exercised, not just the two edge blocks), and a view
that starts at the forced 0-duration block and covers the forced no-event and
single-axis blocks. `buildGModel`'s own durations, drawn independently of the
events a block plays, give many of these blocks real padding, so this also covers
the padding case at scale, across many blocks and views, not just the two
dedicated tests below.

**How:** The test builds a 300-block pseudo-random model (`buildGModel`, more
than 4 `GROUP_BLOCKS`, so it crosses more than one checkpoint group), computes
block start times independently by a running sum, and for each of the six views
above compares `GLanes.minMax` against `bruteMinMax` with `assertMinMaxMatches`.

**Assumptions:** None beyond the file's own.

#### `test_gradient_not_zero_at_a_block_border_and_single_axis_blocks`

**Checks:** `GLanes.minMax` equals the brute force across a gradient event that is
not zero at a block border (the gx event of block 0 ends, and block 1's gx event
starts, at the same nonzero value 8 mT/m, a continuous gradient) and three blocks
that each have an event on only one axis (gx, then gy, then gz), for views inside
one block, a view that starts exactly at the border, and a view that straddles it.

**How:** The test builds a 4-block hand-made table (`buildBorderTables`), checks
with the brute force itself that the fixture's gx value really does reach 8 at
the border (so the fixture tests what it claims to), then compares
`GLanes.minMax` against `bruteMinMax` for six views, including one bin per block,
one bin covering the whole file, and views confined to or straddling the border.

**Assumptions:** None beyond the file's own.

#### `test_bins_in_the_tail_padding_after_a_shorter_gradient_are_zero_not_empty`

**Checks:** A block whose gradient event ends well before the block's own end (a
short trapezoid in a block padded out by, for example, a longer delay, ADC or RF
ringdown) reads as exactly `[0, 0]`, not "no value", for a bin entirely inside
that padding; a bin that straddles the transition from the event's own peak into
the padding has minimum 0 and keeps the event's own peak as its maximum.

**How:** The test builds a one-block table (`buildTailPaddingTables`: a gx event
that ends at 10 raster units into a 20-unit block, gy and gz with no event at
all), checks a bin entirely inside `[10, 20]` raster units is exactly `[0, 0]`,
checks a bin straddling the fall from the event's peak (8 mT/m) into the padding
has minimum 0 and maximum 8, then cross-checks both of those views and the whole
block (6 bins) against `bruteMinMax`.

**Assumptions:** None.

#### `test_a_gradient_ending_non_zero_a_hair_before_the_block_end_has_no_false_zero`

**Checks:** A gradient that ends at a value that is not 0 at the block end (it continues
into the next block), with its last point a rounding error (1e-17 s) before the block
duration, gives no false minimum of 0 in the last bin: `_tripleTimes` adds the block end as
a breakpoint only when no event point is within 1e-9 s of it.

**How:** One block of 20 raster steps with one gx event at offsets 0, 4 and 20 − 1e-12
raster steps and values 0, 8 and 8 (mT/m). `GLanes.minMax` of the bin from 15 to 20 raster
steps must be exactly `[8, 8]`. With the block end added as its own breakpoint, a piece of
almost no width would fall from 8 to 0 there, and the minimum would be 0.

**Assumptions:** None.

#### `test_bins_in_the_head_padding_before_every_delayed_gradient_are_zero_not_empty`

**Checks:** A block whose every active axis starts only after its own delay reads
as exactly `[0, 0]`, not "no value", for a bin entirely before the earliest of
those delays; a bin that straddles the start of the earliest event has minimum 0.

**How:** The test builds a one-block table (`buildHeadPaddingTables`: a gx event
starting at 8 raster units' delay, a gy event starting at 5 raster units' delay,
gz with no event, in a 20-unit block), checks a bin entirely inside `[0, 5]`
raster units is exactly `[0, 0]`, checks a bin straddling gy's own start (5 raster
units) has minimum 0, then cross-checks both of those views and the whole block
(6 bins) against `bruteMinMax`.

**Assumptions:** None.

#### `test_lane_meta_domain_ticks_and_the_other_fixed_fields`

**Checks:** `GLanes.laneMeta`'s fixed fields (`id`, `title`, `unit`, `kind`,
`empty`, `fill`, and a `color` that is not one of gx/gy/gz's own report.css
tokens), and its peak-dependent domain, ticks and tick label: `[0, 1.1 * peak]`,
`[0, peak]` and `["0", <peak to 3 significant figures>]`, `diagram_data.lane_meta`'s
own style for a lane whose value is never negative.

**How:** The test builds a 60-block pseudo-random model with a nonzero peak |G|,
calls `GLanes.laneMeta`, and checks each fixed field and the domain/ticks/label
against `model.wholeFileMax` and the same 3-significant-figure formula
(`Number(peak.toPrecision(3)).toString()`) `assets/chart_math.js`'s `fmt` and
`pns_lanes.js`'s `_fmtBinMs` use.

**Assumptions:** None.

#### `test_lane_meta_domain_is_zero_to_one_with_no_gradient`

**Checks:** A file with blocks but no gradient event on any axis gets the domain
`[0, 1]`, ticks `[0]` and tick label `["0"]` -- never `[-1, 1]`, unlike
`diagram_data.lane_meta`'s own gx/gy/gz lanes for a 0 peak, because |G| can never
be negative -- and `empty: true`.

**How:** The test builds a 20-block model with `noEventProb: 1.0` (and
`forceSpecialBlocks: false`, so no block is forced to have an event), checks
`wholeFileMax` is 0, and checks `GLanes.laneMeta`'s domain, ticks, tick label and
`empty`.

**Assumptions:** None.

#### `test_lanes_for_zigzag_form_matches_min_max_exactly`

**Checks:** `GLanes.lanesFor` returns the lane object with `id: "gmag"`,
`minmax: true`, and segments that are exactly `GLanes.minMax`'s own bins
reformatted as a zigzag (`[edge ms, min]`, `[centre ms, max]` for each bin that
has a value; an empty bin is absent from every segment): the same layout
`SeqLanes.minMaxLanes` and `PnsLanes.lanesFor` use.

**How:** The test builds a 120-block pseudo-random model, calls `GLanes.minMax`
and `GLanes.lanesFor` for the whole file with the same `[t0, t1]` (both divide the
same `viewMs` by 1000, in the same order, so the two calls use bit-for-bit the
same range), reads the lane's segments back into a map keyed by each point's
edge time (`zigzagBins`), and checks, for every bin, that an empty bin
(`max[k] === -Infinity`) is absent from the map and every other bin's map entry
is exactly `[min[k], max[k]]`.

**Assumptions:** None.

#### `test_lanes_for_empty_bins_end_a_segment`

**Checks:** A view that reaches far past the end of the file gets bins with no
value there (`SeqLanes.blockAt` clamps every edge past the file's end to the last
block, so a bin whose own range does not reach that block's own tail overlaps
nothing), and those empty bins are absent from the lane's segments rather than
drawn as a value, ending the current segment.

**How:** The test builds a 40-block model, asks for a view 5 times the file's own
duration (so only about the first fifth of the bins can ever hold a value),
checks with `GLanes.minMax` that at least one bin is empty, then checks that
`GLanes.lanesFor`'s zigzag has no point at an empty bin's edge and a point at
every non-empty bin's edge, and that not every bin is present.

**Assumptions:** None.

#### `test_empty_file_has_zero_peak_and_no_lane_segments`

**Checks:** An empty file (`SeqLanes.decode` with no blocks) gives
`GLanes.decode` a model with `numBlocks: 0` and `wholeFileMax: 0`;
`GLanes.minMax` gives every bin `[Infinity, -Infinity]` ("no value"); `laneMeta`
gives the `[0, 1]`/`empty: true` domain; and `lanesFor` gives `segments: []`
(never a segment of one point).

**How:** The test builds a table with every array empty, decodes it with
`SeqLanes.decode` and `GLanes.decode`, checks `wholeFileMax` and `numBlocks`,
calls `GLanes.minMax` over 10 bins and checks every one is empty, and checks
`laneMeta` and `lanesFor`'s output.

**Assumptions:** None.

#### `test_file_without_gradients_is_all_zero_not_empty`

**Checks:** A file whose blocks tile the whole duration but have no event on any
axis gives every bin exactly `[0, 0]` (a real value, the model's own "a block
with no event on an axis reads as the constant 0"), not "no value": one
unbroken segment of zeros, not an empty lane.

**How:** The test builds a 30-block model with `noEventProb: 1.0` (and
`forceSpecialBlocks: false`), checks `wholeFileMax` is 0 but the file has blocks
and a nonzero duration, calls `GLanes.minMax` over the whole file and checks
every bin is exactly `[0, 0]`, and checks `GLanes.lanesFor` gives one segment
whose every point's value is 0.

**Assumptions:** None.

#### `test_decode_accepts_more_gradient_events_than_one_numeric_key_allows`

**Checks:** `GLanes.decode` does not throw for a file with far more gradient events
than the single flat numeric cache key `((kx * M + ky) * M + kz) * D + durIdx`
(`M = numGradEvents + 1`) can hold as an exact integer below 2^53 (about 1.2 * 10^5
events), once that key is split into the two-level `outerKey`/`innerKey` form
(`kx * M + ky` on the outer `Map`, `kz * D + durIdx` on the inner `Map`), which
stays exact up to about 9.5 * 10^7 events; and `GLanes.minMax` still matches the
brute force within 1e-12 of the peak there.

**How:** The test builds a 300-block table with 150,000 distinct gradient events
(`buildManyEventsTables`, most blocks reference event indexes within 50 of the top
end on each axis), calls `GLanes.decode` (must not throw), and compares
`GLanes.minMax` against `bruteMinMax` with `assertMinMaxMatches` for the whole file
at two different bin counts and a range that crosses many checkpoint groups. Before
the fix, `GLanes.decode` throws "the per-(triple, duration) cache key of this file
would exceed 2^53" (checked).

**Assumptions:** None beyond the file's own.

### 2.28 Messages between cards (`test_messages.js`)

`lane_chart.js`'s `createMessageBus` builds the page-level publish/subscribe bus of
`docs/plans/rf-profiles.md`, section 4.1: `publish(topic, message)` keeps the last
message of each `(topic, source)` pair and fans it out to every handler of that topic
in subscription order; `subscribe(topic, handler, {replay})` returns an unsubscribe
function and, by default, replays the kept messages of a topic to a new handler, in
the order those pairs were first published. `PulseqReport.publish` and
`PulseqReport.subscribe` are the one bus the page itself uses; `PulseqReport.createMessageBus`
is also exported, so a test builds its own private bus instead of sharing state with
any other test.

The tests load `lane_chart.js` directly with Node's `require`, after setting
`global.ChartMath` (the same way a browser page loads `chart_math.js` before
`lane_chart.js`), and use `node:test` and `node:assert/strict`, with no browser or
DOM. Every test but one builds a private bus with `createMessageBus`, passing its own
`onError` collector instead of relying on `console.error`, so a test never depends on
console output. The one exception, `test_pulseq_report_publish_and_subscribe_share_one_page_level_bus`,
uses `PulseqReport.publish`/`PulseqReport.subscribe` themselves, on a topic name no
other test in the file uses, because that singleton bus, unlike one from
`createMessageBus`, is shared by every test in the same Node process.

#### `test_subscribe_replays_kept_messages_in_publication_order`

**Checks:** A new subscriber with the default `replay: true` is called at once with
each kept message of a topic, in the order those `(topic, source)` pairs were first
published.

**How:** Publishes `{source: "a", v: 1}` then `{source: "b", v: 2}` on one topic of a
fresh bus, before any subscriber exists, then subscribes and checks the handler's
calls, in order, against `[["a", 1], ["b", 2]]`.

**Assumptions:** None beyond the file's assumptions.

#### `test_replacing_a_source_keeps_its_original_position_in_replay_order`

**Checks:** Publishing again from a source that already published to a topic
replaces its kept message with the new value, but does not move its position in
replay order: the position comes from the pair's first publication, not its last.

**How:** Publishes `{source: "a", v: 1}`, then `{source: "b", v: 1}`, then
`{source: "a", v: 2}` on one topic, subscribes, and checks the replay order is
`[["a", 2], ["b", 1]]`: "a" first, since it published first, but with its updated
value.

**Assumptions:** None beyond the file's assumptions.

#### `test_subscribe_with_replay_false_does_not_replay`

**Checks:** `{replay: false}` skips the replay of kept messages, but the handler
still receives a message published after it subscribes.

**How:** Publishes one message, subscribes with `{replay: false}` and checks nothing
was delivered yet, then publishes a second message and checks the handler received
exactly that one.

**Assumptions:** None beyond the file's assumptions.

#### `test_handlers_run_in_subscription_order`

**Checks:** The handlers of one topic run in the order in which they subscribed.

**How:** Subscribes three handlers, each pushing its own label onto a shared array,
to one topic in a fixed order, publishes one message, and checks the array equals
that same order.

**Assumptions:** None beyond the file's assumptions.

#### `test_a_throwing_handler_does_not_stop_the_others_or_the_publisher`

**Checks:** A handler that throws is reported to `onError` (with the error, the
topic and the message) and does not stop the other handlers of the same delivery,
and does not make `publish` itself throw.

**How:** Subscribes a handler that records its call and then throws, and a second
handler that only records its call, to a bus built with an `onError` collector;
publishes one message inside `assert.doesNotThrow`, then checks both handlers ran,
in order, and that `onError` was called exactly once, with the thrown error, the
topic and the message's source.

**Assumptions:** None beyond the file's assumptions.

#### `test_publish_inside_a_handler_is_delivered_after_the_current_delivery_ends`

**Checks:** A `publish` made from inside a handler is queued and delivered only
after every handler of the topic has finished running for the message that
triggered it, never nested inside that delivery.

**How:** Subscribes two handlers to one topic; the first, on the message with
`v: 1`, publishes a second message (`v: 2`) to the same topic before returning.
Publishes the first message and checks the recorded call order is
`["first:1", "second:1", "first:2", "second:2"]`: both handlers see `v: 1` before
either sees `v: 2`.

**Assumptions:** None beyond the file's assumptions.

#### `test_unsubscribe_stops_future_deliveries`

**Checks:** The function `subscribe` returns stops that handler from being called by
any later `publish`.

**How:** Subscribes a handler with `{replay: false}`, publishes one message, calls
the returned unsubscribe function, publishes a second message, and checks the
handler's recorded values are only `[1]`.

**Assumptions:** None beyond the file's assumptions.

#### `test_unsubscribe_during_a_delivery_stops_the_rest_of_that_delivery`

**Checks:** A handler unsubscribed by an earlier handler of the same delivery is not
called for the rest of that delivery, while a handler subscribed before the delivery
started, and not unsubscribed, still runs.

**How:** Subscribes three handlers to one topic in order: the first unsubscribes the
second (using its own unsubscribe function) before returning; the second and third
each record their call. Publishes one message and checks the recorded order is
`["first", "third"]`.

**Assumptions:** None beyond the file's assumptions.

#### `test_unsubscribe_twice_does_nothing`

**Checks:** Calling an unsubscribe function a second time is a no-op: it neither
throws nor removes a different, still-subscribed handler.

**How:** Subscribes two handlers with `{replay: false}`; unsubscribes the first,
then calls its unsubscribe function again inside `assert.doesNotThrow`; publishes
one message and checks the first handler received nothing while the second still
received it.

**Assumptions:** None beyond the file's assumptions.

#### `test_publish_freezes_the_message`

**Checks:** `publish` freezes the message object (`Object.isFrozen`), both for the
object the publisher passed in and for the same object as a subscriber receives it,
and an assignment to one of its fields is silently ignored, not applied.

**How:** Publishes a plain object, checks `Object.isFrozen` on it directly and on
the object a new subscriber then receives (`replay: true`), then assigns to one of
its fields and checks the value is unchanged.

**Assumptions:** An assignment to a frozen object's field is a silent no-op rather
than a thrown error outside strict mode, so the test checks the value, not a thrown
error (a `node:test` file is not implicitly in strict mode).

#### `test_publish_throws_type_error_for_a_non_string_or_empty_topic`

**Checks:** `publish` throws `TypeError` for a topic that is not a non-empty string:
an empty string, `null`, and a number.

**How:** Calls `publish` with each of `""`, `null` and `42` as the topic (a valid
message otherwise) and checks each call throws `TypeError`.

**Assumptions:** None beyond the file's assumptions.

#### `test_publish_throws_type_error_for_a_message_without_a_string_source`

**Checks:** `publish` throws `TypeError` for a message that is not an object with a
string `source`: an object with no `source`, an object whose `source` is not a
string, `null`, and a string.

**How:** Calls `publish` with a valid topic and each of `{}`, `{source: 42}`, `null`
and `"not an object"` as the message, and checks each call throws `TypeError`.

**Assumptions:** None beyond the file's assumptions.

#### `test_create_message_bus_returns_independent_buses`

**Checks:** `createMessageBus` is a pure factory: two buses it returns do not share
kept messages or subscribers.

**How:** Builds two buses, subscribes a handler on one of them, publishes a message
on the other, and checks the handler was not called.

**Assumptions:** None beyond the file's assumptions.

#### `test_pulseq_report_publish_and_subscribe_share_one_page_level_bus`

**Checks:** `PulseqReport.publish` and `PulseqReport.subscribe` are the functions of
one shared bus (not, for example, two unconnected pairs).

**How:** Subscribes on `PulseqReport` itself with `{replay: false}`, on a topic name
used nowhere else in this file (so it cannot see a kept message left by another test
that shares the same singleton bus within the process), publishes one message
through `PulseqReport.publish`, and checks the handler received it.

**Assumptions:** This is the only test in the file that uses
`PulseqReport.publish`/`PulseqReport.subscribe` directly, because that bus, unlike
one from `createMessageBus`, is a module-level singleton shared by every test in
this file's process; every other test uses its own private bus instead.

#### `test_bus_still_delivers_after_on_error_throws`

**Checks:** When the `onError` callback itself throws, the error leaves `publish` (or
`subscribe`, for a replay), but the bus is not left in its "delivering" state: a
later `publish` is still delivered to its subscribers at once, not only queued.

**How:** A bus whose `onError` throws, and a subscriber of topic `t` that throws. The
`publish` on `t` must throw the `onError` error. Then a new subscriber of topic `u`
and a `publish` on `u`: the subscriber must receive the message. A second bus checks
the same after a replay: a kept message on `t`, and a `subscribe` to `t` with a
throwing handler must throw the `onError` error; then a `publish` on another topic
must be delivered.

**Assumptions:** None.

### 2.29 RF simulation (`test_rf_sim.py`)

`test_rf_sim.py` tests `rf_sim.py` (`docs/plans/rf-profiles.md`, section 4.2): the
spin-domain (Cayley-Klein) simulator `spin_domain`, generalized from vb-pulseq
`rf_sim.cayley_klein` to a gradient vector per hold interval and a frequency offset and
a B1 factor per point, and `magnetization`, `crushed_echo` and `precess`. Most tests
come from vb-pulseq's own `tests/tools/test_rf_sim.py` (commit 3a1c7dd), adapted to the
new signatures. Oracle: `tests/oracles/rf_sim.py`, an independent simulation that
rotates the magnetization vector directly (a 3x3 Rodrigues rotation about the effective
field) in each hold interval, without Cayley-Klein parameters (section 3.5, item 1).

#### `test_hard_pulse_zero_gradient_flip_angle`

**Checks:** For a constant-amplitude ("hard") pulse with no gradient, Mz and |Mxy| of
the simulated point match the closed-form flip angle: `cos(flip)` and `|sin(flip)|`.

**How:** Parametrized over `flip_deg` in `[30, 90, 180]`. A 1 ms, 1000-interval hard
pulse (`_hard_pulse_signal`) with a zero gradient, one point at z = 0, `spin_domain` +
`magnetization`, compared with `pytest.approx(..., abs=1e-9)`.

**Assumptions:** None.

#### `test_hard_pulse_with_gradient_matches_rodrigues_rotation`

**Checks:** A hard pulse under a constant gradient rotates M by the same result as a
direct Rodrigues rotation of M0 = (0, 0, 1) by the angle `|field| * duration` about the
unit vector along `field = (Re(b1), Im(b1), off-resonance)`, confirming the sign
convention: `spin_domain` rotates M by `+angle` (right-handed) about that field, the
same convention as vb-pulseq `cayley_klein`.

**How:** A 1000-interval, 1 ms hard pulse with a nonzero phase (so the rotation axis
tilts off the x-axis) and a constant z gradient, at 5 points including 0, compared with
a hand-written `_rodrigues` helper (the same one vb-pulseq's test uses) applied to each
point's own field and angle, `atol=1e-9` (vb-pulseq's own tolerance: the float error of
composing 1000 Cayley-Klein rotations, not an approximation).

**Assumptions:** None.

#### `test_small_flip_angle_matches_fourier_prediction`

**Checks:** For a small-flip-angle (5°) sinc pulse under a constant gradient, the
simulated |Mxy| profile matches the small-tip-angle Fourier approximation (the
magnitude of the Fourier transform of the RF shape, evaluated at the frequency each
position sees).

**How:** A 400-sample sinc pulse (time-bandwidth product 4, Hann-windowed) scaled to a
5° flip, a gradient giving a 5 mm nominal slice, 201 points from -1 to 1 cm. Compared
with a direct discrete Fourier sum computed independently in the test, `atol = 0.02 *
mxy_sim.max()` (vb-pulseq's own tolerance: an empirical bound on the small-tip-angle
approximation error, not a rounding-error bound — the two sides use genuinely different
formulas).

**Assumptions:** None.

#### `test_magnetization_and_crushed_echo_definitions`

**Checks:** `magnetization(a, b)` returns exactly `(2 * conj(a) * b, |a|^2 - |b|^2)`,
and `crushed_echo(b)` returns exactly `|b|^2`.

**How:** Hand-picked complex `a`, `b` arrays (not from a simulation), compared with
`numpy.testing.assert_allclose` at its default tolerance against the formulas computed
directly in the test.

**Assumptions:** None.

#### `test_precess_sign_matches_free_precession_in_spin_domain`

**Checks:** Continuing a pulse simulation with zero-RF intervals under the same
gradient (free precession) gives the same Mxy as calling `precess` with the matching
gradient moment on the pulse's own result; the opposite-signed moment does not.

**How:** A 200-interval hard pulse (70°, nonzero phase) under a constant z gradient, at
13 points, then 500 more zero-signal intervals under the same gradient (`spin_domain`
again, on the concatenated signal and a matching extended gradient array). `precess`
with the moment vector `(0, 0, gradient * n_free * dt)` applied to the pulse-only
result is compared with the extended-simulation result, `rtol=0, atol=1e-9`
(vb-pulseq's own tolerance: the float error of composing 700 Cayley-Klein rotations).
A second assertion confirms `precess` with the negated moment does *not* match, within
a much looser `atol=1e-3`, so the test would fail if the sign of `precess` were
reversed.

**Assumptions:** None.

#### `test_magnetization_has_unit_length_for_random_pulses`

**Checks:** `|Mxy|^2 + Mz^2 == 1` for random pulses, at every point.

**How:** `numpy.random.default_rng(7)`, 5 repetitions of a random-length (20 to 100
samples) complex Gaussian RF under a random constant z gradient, at 21 points from -1
to 1 cm, `atol=1e-9` (vb-pulseq's own tolerance: `|M| = 1` is exact only in exact
arithmetic; this bounds the float error of composing up to 100 Cayley-Klein rotations).

**Assumptions:** None.

#### `test_matches_oracle_for_random_rf_gradient_and_points`

**Checks:** `spin_domain` + `magnetization` agrees with the independent oracle
(`tests/oracles/rf_sim.py`) on Re(Mxy), Im(Mxy) and Mz, for a gradient that changes in
every interval and random points with random frequency offsets and B1 scales.

**How:** `numpy.random.default_rng(1234)`, 250 complex Gaussian RF samples (at least
the 200 the plan asks for), a `(250, 3)` gradient array drawn uniformly on each axis in
every interval (so its direction changes throughout the pulse), 30 random 3D points in
a 4 cm cube with random `df` (±200 Hz) and `b1_scale` (0.5 to 1.5), compared with
`atol=1e-10` on each of the three components (docs/plans/rf-profiles.md, section 3.5,
item 1: the oracle uses a different method — direct 3x3 Rodrigues rotation of M, no
Cayley-Klein parameters — so a shared error is unlikely). The measured agreement for
this seed is under 5e-15 on Mxy and under 5e-15 on Mz, far inside the 1e-10 bound.

**Assumptions:** None.

#### `test_rotation_invariance_matches_1d_simulation_along_the_gradient_direction`

**Checks:** A constant gradient `(Gx, Gy, 0)` with points along its own direction gives
the same `a`, `b` as the equivalent 1D-along-z simulation, with the gradient magnitude
on z and the signed distance along `(Gx, Gy, 0)` as the z coordinate.

**How:** `numpy.random.default_rng(5)`, 60 complex Gaussian RF samples, a fixed `(Gx,
Gy, 0)` direction, 11 points at signed distances from -1 to 1 cm along the unit vector
of that direction, compared with `_grad_z`/`_positions_z` (the gradient magnitude and
the same distances on z), `atol=1e-12` (both sides compute the same rotation, only
reindexed onto different axes; the difference is float reassociation in a handful of
extra multiply-adds with the zero x, y components, not an approximation).

**Assumptions:** None.

#### `test_df_is_a_shift_along_the_gradient`

**Checks:** With a constant gradient `G` on z, the point at `z` with `df` gives the
same `a`, `b` as the point at `z + df / G` with `df = 0`.

**How:** `numpy.random.default_rng(9)`, 80 complex Gaussian RF samples, `G = 5e4` Hz/m,
`z = 0.004` m, `df = 137` Hz, compared with `atol=1e-12` (both points see the same
total off-resonance angle in every interval, `G*(z + df/G) + 0 == G*z + df` up to
reassociation of the same multiply-add; the difference is float rounding in one extra
division and addition, not an approximation).

**Assumptions:** None.

#### `test_b1_scale_gives_s_times_the_flip_angle_of_a_hard_pulse`

**Checks:** A hard pulse (constant RF, zero gradient) with `b1_scale = s` gives `s`
times the flip angle: Mz = `cos(s * flip)`, |Mxy| = `sin(s * flip)`.

**How:** A 300-interval, 40°-flip hard pulse with zero gradient, one point at z = 0,
`b1_scale = 1.7`, compared with `pytest.approx(..., abs=1e-12)` against the closed-form
values. The bound is much tighter than the 1e-9 bound of the 1000-interval hard-pulse
tests above because here every interval rotates about the same fixed axis (zero
gradient), so composing `n` identical small rotations is exactly one rotation by `n`
times the per-interval angle in exact arithmetic; with a changing rotation axis (a
nonzero gradient) the tighter bound would not hold.

**Assumptions:** None.

#### `test_precess_matches_scalar_form_along_one_axis`

**Checks:** `precess` with a moment vector `(0, 0, area)` and points on z exactly
equals the scalar form `mxy * exp(2j * pi * area * x)`.

**How:** `numpy.random.default_rng(3)`, 25 random `x` and random complex `mxy`, `area =
137`. Compared with `numpy.testing.assert_array_equal` (exact): `positions_m @
moment_per_m` reduces to `x * area` plus two products with an exactly-zero component
(`0*0 + 0*0 + x*area`), which does not change the float value (verified for this seed:
the dot product equals `area * x` exactly). The expected value in the test keeps the
same `2j*pi * (the dot product)` grouping as the `precess` docstring and implementation,
rather than a left-to-right `2j*pi*area*x`, which associates differently in floating
point and is not bit-identical to the dot-product form.

**Assumptions:** None.

#### `test_spin_domain_raises_value_error_for_mismatched_shapes`

**Checks:** `spin_domain` raises `ValueError`, not a silent broadcast or a cryptic
numpy error, when `grad_hz_per_m`'s interval count does not match `signal_hz`, when
`grad_hz_per_m` or `positions_m` does not have 3 columns, or when `df_hz` or
`b1_scale`'s length does not match `positions_m`.

**How:** Five separate `spin_domain` calls, each inside its own `pytest.raises
(ValueError)`: a `grad_hz_per_m` with `n - 1` rows, a `grad_hz_per_m` with 2 columns, a
`positions_m` with 2 columns, a `df_hz` of length `m - 1`, and a `b1_scale` of length
`m + 1`.

**Assumptions:** None.

### 2.30 Profile metrics (`test_profile_metrics.py`)

These tests use synthetic 1-D profiles on a symmetric grid of positions, with known shapes: a rectangle, a trapezoid, a triangle, a cosine ripple, a spike and a linear phase. This module and tests are a copy of vb-pulseq at commit 3a1c7dd. The expected values come from the shapes, not from the functions under test.

The profile numbers are defined as follows:

- **FWHM**: the distance between the outermost positions where the profile is at or above half its maximum.
- **Edge width**: the mean of the left and right distances from the 10 % point to the 90 % point.
- **Passband ripple**: (maximum − minimum) / maximum, over |x| ≤ 0.4 × the nominal thickness.
- **Stopband level**: the maximum over |x| ≥ the nominal thickness, divided by the maximum of the whole profile.
- **Residual phase**: the peak-to-peak unwrapped phase over |x| ≤ 0.4 × the nominal thickness.

**Assumptions for the whole file:**

- All numbers are measured on the sample grid, with no interpolation. So they are accurate only to about one sample step.
- The passband is |x| ≤ 0.4 × nominal and the stopband is |x| ≥ nominal. These regions are fixed choices, not derived from the pulse.

#### `test_rectangle_edge_width_is_zero`

**Checks:** A rectangular profile has an edge width of 0.

**How:** The test makes a rectangle of value 1 for |x| ≤ 6 mm and 0 outside. The 10 % and 90 % points are at the same positions, so the edge width must be 0.

**Assumptions:** None.

#### `test_rectangle_passband_ripple_is_zero`

**Checks:** A rectangular profile that is wider than the passband has a passband ripple of 0.

**How:** The test makes the same 12 mm rectangle and a nominal thickness of 10 mm. The passband (|x| ≤ 4 mm) is all 1, so the ripple must be 0.

**Assumptions:** None.

#### `test_rectangle_stopband_level_is_zero`

**Checks:** A rectangular profile that is narrower than the nominal thickness on each side has a stopband level of 0.

**How:** The test makes the same rectangle (|x| ≤ 6 mm) and a nominal thickness of 10 mm. The stopband (|x| ≥ 10 mm) is all 0, so the level must be 0.

**Assumptions:** None.

#### `test_rectangle_fwhm_equals_width`

**Checks:** The FWHM of a rectangle is its width.

**How:** The test makes a rectangle for |x| ≤ 5 mm, with 5 mm an exact multiple of the grid step. The FWHM must be 10 mm.

**Assumptions:**

- The edges of the rectangle are on grid points. Otherwise the FWHM is off by up to one step.

#### `test_trapezoid_edge_width_matches_ramp`

**Checks:** The edge width of a trapezoid profile is 80 % of its ramp width.

**How:** The test makes a profile with a flat top for |x| ≤ 3 mm and linear edges 4 mm wide. On a linear edge, the distance from 10 % to 90 % is 0.8 × the ramp width. The edge width must be 3.2 mm within one grid step.

**Assumptions:** None.

#### `test_passband_ripple_known_cosine`

**Checks:** The passband ripple of a cosine ripple is (maximum − minimum) / maximum.

**How:** The test makes the profile 1 + 0.1 cos(kx), with k chosen so that the cosine is +1 at x = 0 and −1 exactly at the passband edges. The maximum in the passband is 1.1 and the minimum is 0.9. The ripple must be 0.2 / 1.1 within 10⁻⁶.

**Assumptions:**

- The passband edges are on grid points, so the minimum is sampled.

#### `test_stopband_level_known_spike`

**Checks:** The stopband level is the height of a spike in the stopband, relative to the profile maximum.

**How:** The test makes a rectangle of value 1 inside the nominal thickness, and a spike of 0.2 at x = 7 mm, which is in the stopband for a 5 mm nominal thickness. The stopband level must be 0.2.

**Assumptions:** None.

#### `test_phase_peak_to_peak_linear_phase`

**Checks:** The residual phase of a linear phase that wraps several times is the full unwrapped range.

**How:** The test makes Mxy = e^(i s x), with s = 2000 rad/m, over the passband of a 10 mm nominal thickness. The phase range is s × 8 mm = 16 rad, which wraps more than twice. The result must be 16 rad within a relative 10⁻⁶.

**Assumptions:**

- The phase changes by less than π between samples (0.2 rad here), so unwrapping is correct.

#### `test_phase_peak_to_peak_constant_phase_is_zero`

**Checks:** A constant phase has a residual phase of 0.

**How:** The test makes Mxy with a constant phase of 0.7 rad. The result must be 0.

**Assumptions:** None.

#### `test_passband_ripple_empty_region_raises`

**Checks:** The passband ripple raises an error when no sample is in the passband.

**How:** The test uses positions 1, 2 and 3 m and a nominal thickness of 1 mm, so no position is within 0.4 mm of 0. The calculation must raise an error.

**Assumptions:** None.

#### `test_stopband_level_empty_region_raises`

**Checks:** The stopband level raises an error when no sample is in the stopband.

**How:** The test uses positions within 1 mm of 0 and a nominal thickness of 10 m, so no position is in the stopband. The calculation must raise an error.

**Assumptions:** None.

#### `test_phase_peak_to_peak_empty_region_raises`

**Checks:** The residual phase raises an error when no sample is in the passband.

**How:** The same as for the passband ripple, with Mxy values. The calculation must raise an error.

**Assumptions:** None.

#### `test_fwhm_triangle_known_width`

**Checks:** The FWHM of a triangle is half its base width.

**How:** The test makes a triangle with a 20 mm base. The FWHM must be 10 mm within two grid steps.

**Assumptions:** None.

### 2.31 RF pulse of a block (`test_rf_profiles.py`)

`test_rf_profiles.py` tests `rf_profiles.py` (`docs/plans/rf-profiles.md`, sections 4.2
and 4.3; task 2.5, items 1 to 14): `block_pulse` (the RF of a block as played, the
interval gradients, the gradient kind, the numbers, the pulse key and the echo pathway),
`period`, `rf_uses_labeled`, `view_spec`, `simulate`, `quantity`, `echo_phase`,
`widths`, `combined_profile` and `pulse_list`. Each test builds its sequences with
pypulseq in the test file. The RF raster is 5 µs (3 µs in the interval test, 2.5 µs in
one part of the as-played test), so a 1.5 ms sinc has 300 samples and the whole file
runs in about 2 s. The expected values come from closed forms (trapezoid areas and
means, the amplitude of a block pulse), from `rf_sim.spin_domain` called directly on
points made in the test, or from the definitions of the plan written out with numpy.

**Assumptions for the whole file:**

- `rf_sim.spin_domain` and `profile_metrics` are correct: section 2.29 and 2.30 test
  them. These tests check how `rf_profiles` reads the sequence, builds the grids and
  combines the results.
- "Exact" means bit-for-bit equal: the test builds the same points and calls the same
  simulation, so no float difference is possible.
- pypulseq 1.5 (the pinned fork) stores `use="other"` as `undefined` (its
  `register_rf_event` knows only the first five uses). The test of the uses sets the
  letter "o" in `rf_library.type` by hand, as a file with that label is read.

#### `test_gradient_kind_none_for_a_block_pulse`

**Checks:** A block pulse without a gradient has the gradient kind "none": no select
coordinate, no direction, no G, no slice centre, not constant, all interval gradients 0.
Its "profile" view is one `df` axis with `NUM_POSITIONS` points, centred on the
frequency offset.

**How:** A 0.5 ms block pulse with `freq_offset` 150 Hz. The middle of the `df` axis is
compared with 150 Hz within a relative 1e-12 (the range is f ± 2B, so only rounding).

**Assumptions:** None.

#### `test_gradient_kind_one_on_a_logical_axis`

**Checks:** A sinc with its trapezoid on z, the RF inside the flat top, has the kind
"one", the select coordinate "z", the direction (0, 0, 1), a constant gradient, the
flat-top amplitude as G, and the slice centre 0.

**How:** `pp.make_sinc_pulse(..., return_gz=True)` in one block. Each interval value but
the last must equal the amplitude exactly (the value at the middle of a flat interval).
The last interval and G are compared within a relative 1e-14: the RF end and the
flat-top end are one time from two float sums, so the last interval can cross that
corner by 1e-19 s.

**Assumptions:** None.

#### `test_gradient_kind_one_oblique_on_two_axes`

**Checks:** The same trapezoid on x and y with one timing gives the kind "one" with the
select coordinate "select", the unit vector of the two amplitudes as the direction, and
the trapezoid amplitude as G.

**How:** The select gradient of a sinc, scaled by cos 30° on x and sin 30° on y
(`pp.scale_grad`). The direction and G are compared within 1e-12 (rounding of the two
scaled amplitudes).

**Assumptions:** None.

#### `test_gradient_kind_changing_for_a_turning_gradient`

**Checks:** Arbitrary gradients on x and y whose direction turns one time during the RF
give the kind "changing", with no select coordinate and no direction. The "profile" and
"z_df" views give None and the reason `DIRECTION_CHANGES` (decision 12).

**How:** `_turning_gradients`: a sine envelope times cos and sin of a turning angle, as
two `pp.make_arbitrary_grad` events, with a 0.8 ms block pulse.

**Assumptions:** None.

#### `test_oversampled_gradient_that_ends_before_the_rf_is_not_a_gradient_of_the_pulse`

**Checks:** B4 of `docs/reviews/2026-09-28-code-review.md` (pypulseq issue #423), fixed
by the project's pypulseq pin (`pulseq-reports-pin-1`, the fix of pypulseq PR #424): an
oversampled arbitrary gradient (`make_arbitrary_grad(oversampling=True)`) that ends well
before an RF is not a gradient of that RF's pulse. The gradient kind is "none", every
interval gradient is 0, and the gradient's id is 0 in each place of the pulse key.
`_plays_during` reads the gradient's end from `pp.calc_duration(g)`, and `_pulse_key`
uses `_plays_during`. The old pin gave that end twice as late as the real `shape_dur`,
so the gradient looked like it was still playing when the RF started.

**How:** Builds the block of section 9.6 of `docs/plans/review-bugs.md`: an oversampled
triangle on z (`synthetic.SYSTEM`, not this file's own `SYSTEM`; 21 samples that start
and end at 0, at 50 % of `max_slew` over half a raster, kept within the real `max_slew`
by the test itself because `make_arbitrary_grad(oversampling=True)` checks the slew rate
4 times too leniently, pypulseq issue #421), and a block pulse with `use="excitation"`
whose delay is 50 µs after the added gradient event's own end (its delay plus its
`shape_dur`), then an ADC block. `block_pulse(seq, 0).gradient_kind` must be "none",
`grad_hz_per_m` all 0, and the third item of `key` (the gradient ids) `(0, 0, 0)`.
Checked against a pypulseq checkout at the old pin (`20b9e5e`): there the kind is "one",
with a z direction, and the gz event's id is in the key.

**Assumptions:**

- The pin (`pulseq-reports-pin-1`) has the fix of pypulseq PR #424. A pypulseq without
  it fails this test: checked against a checkout of the old pin (`20b9e5e`).

#### `test_interval_values_of_a_trapezoid_equal_the_hand_means`

**Checks:** The gradient of each hold interval is the exact mean of the trapezoid over
that interval: on the ramp up, across the corner at the start of the flat top, on the
flat top, on the fall, across the end of the trapezoid, and 0 after it. An RF that is
longer than the flat top gives the kind "one", not constant.

**How:** A system with a 3 µs RF raster, so that gradient corners (on the 10 µs raster)
fall inside hold intervals. A trapezoid of 200 kHz/m with 100 µs ramps and a 500 µs flat
top, and a 900 µs block pulse that starts at 60 µs. The expected means are written out:
the value of a line at the middle of the interval, or the sum of the two parts across a
corner, divided by dt. Relative 1e-12 (rounding of the interval ends); the flat
interval must be the amplitude exactly.

**Assumptions:** None.

#### `test_as_played_profile_is_the_profile_moved_by_f_over_g`

**Checks:** A block with the frequency offset f = G × c and a constant gradient G has
the profile of the same block without the offset, moved by c = f / G (|Mxy|, Mz and
|β|²), up to the error of the hold model; and that error is a discretization error.

**How:** `_moved_and_plain_difference` builds the sinc with and without f (c = 1.5 mm,
f = 800 Hz), simulates the first on its "profile" view and the second on the same axis
minus c, and returns the largest difference of the three quantities, and the difference
of |Mxy| when the plain profile is not moved. At a 5 µs raster the difference must be
below 1e-3, while the profile that is not moved differs by about 1. At a 2.5 µs raster
the difference must be 3 to 5 times smaller.

**Assumptions:**

- The hold model keeps the offset phase of each sample constant over its hold interval
  (its value at the centre), a midpoint rule. Its error is second order in dt and first
  order in f: measured 1.4e-4 at 5 µs and 3.5e-5 at 2.5 µs. The plan's 1e-9 is not
  reached for any useful shift (2.6e-7 for f = 2 Hz at 5 µs), so the test checks the
  convergence instead.

#### `test_freq_ppm_adds_to_the_total_frequency_offset`

**Checks:** The total frequency offset is `freq_offset + freq_ppm * 1e-6 * |gamma| *
B0`, the total phase has the same form, and the RF as played is the baseband times
`exp(1j * (phase + 2π f t))` with `t` at the centre of each hold interval.

**How:** A 0.5 ms saturation block pulse with all four offsets, on a system with
B0 = 2.89 T. The expected offset and samples are written out in the test (the block
pulse amplitude is flip / (2π × duration)). Relative 1e-12 (the same formula, only
rounding).

**Assumptions:** None.

#### `test_pulse_key_ignores_gradients_outside_the_rf`

**Checks:** MPRAGE-like blocks, each with a different phase-encode gradient before the
RF (ending where the RF starts, as pypulseq's `write_mprage`) or after it, have the key
of the block with the RF alone, and the gradient kind "none". The same holds after a
write and a read of the file.

**How:** Parametrized over "before" and "after". `_mprage_like` makes four RF blocks with
different phase-encode areas and one RF block alone, each followed by a readout. The
file is written to `tmp_path` and read again; for both sequences, the keys of the five
RF blocks must be one key.

**Assumptions:**

- A `.seq` file keeps times in µs. After the read, the spoiler that ends at the RF start
  ends 1e-19 s after it. `block_pulse` counts a gradient as playing during the RF only
  when the overlap is longer than `seq_utils.TIME_TOLERANCE` (1 ns), so this case must
  still give one key and the kind "none".

#### `test_pulse_key_ignores_the_phase_offset`

**Checks:** The blocks of an RF-spoiled GRE, with a new phase offset (so a new RF
event) in each TR, have one key.

**How:** `_gre(4, rf_spoiling=True)`: the test first checks that the four RF blocks have
four different RF event ids, then that `block_pulse` gives one key for them.

**Assumptions:** None.

#### `test_pulse_key_differs_for_different_frequency_offsets`

**Checks:** Blocks with different frequency offsets have different keys.

**How:** `_gre(1, slices=(-5 mm, 0, 5 mm))`: the three RF blocks must give three keys.

**Assumptions:** None.

#### `test_echo_pathway_of_a_gre`

**Checks:** In a GRE (the slice rephaser in the next block), the pathway of an
excitation ends at the ADC of the same TR with the sign +1. Its moment cancels the
dephasing of the pulse on z (−G × T / 2) and the readout moment to the ADC centre on
x, and is 0 on y.

**How:** `_gre(2)`, the excitation of the second TR (block 4). z and x within 1e-9 of
the moment that each cancels (`REPHASING_TOL`, the plan's tolerance: the moments are
sums of a few trapezoid areas).

**Assumptions:**

- The sinc's flat top holds the whole RF, so the dephasing to cancel is G × T / 2 from
  the RF centre to the RF end.

#### `test_echo_pathway_of_a_spin_echo_with_crushers`

**Checks:** In a spin echo with crushers on y around a refocusing pulse on y, the
pathway has the sign −1 and a residual moment of 0 on each axis: on z the moment is
+G × T / 2 (the conjugation turns the dephasing of the pulse), and the crushers and the
readout prephaser cancel.

**How:** `_spin_echo("y")`: excitation, rephaser with the readout prephaser, crusher,
refocusing pulse, crusher, readout. Each axis within `REPHASING_TOL` of the moment it
cancels (z: G × T / 2, y: the crusher area, x: the readout area to the ADC centre).

**Assumptions:** None.

#### `test_echo_pathway_without_an_adc`

**Checks:** An excitation with no ADC before the next excitation (a dummy TR), an
excitation with no ADC before the end of the file, and a walk longer than `max_blocks`
have no pathway and the reason `NO_ADC`. The excitation of the next TR finds its ADC.
A refocusing pulse gets no pathway and no reason.

**How:** `_gre(1, dummies=1)` (block 0 is the dummy, block 4 the excitation with an ADC
in block 6); `block_pulse(seq, 4, max_blocks=1)`; a sequence of an excitation and its
rephaser only; block 3 of `_spin_echo("y")`.

**Assumptions:** None.

#### `test_echo_pathway_of_a_tse_like_merged_rephaser_and_crusher`

**Checks:** When the slice rephaser and the first crusher are one gradient in the block
after the excitation (as in pypulseq's `write_tse`), the echo rule gives a residual
moment of 0, and a next-block rule (the select area from the RF end to the end of the
next block, sign +1; item 1 of the survey in section 2.3 of the plan) leaves the
crusher area.

**How:** Excitation, a merged trapezoid of area rephaser + crusher (with the readout
prephaser), refocusing pulse on z, crusher on z, readout. The pathway must have the sign
−1 and z within `REPHASING_TOL` of G × T / 2. The next-block residual is computed by
hand (the ramp area after the RF, plus the merged area, plus G × T / 2) and must equal
the crusher area (relative 1e-9) and be larger than G × T / 2.

**Assumptions:** None.

#### `test_echo_pathway_stops_at_a_saturation_pulse`

**Checks:** A saturation pulse between an excitation and its ADC stops the walk: no
pathway, the reason `OTHER_RF_BEFORE_ADC`.

**How:** Excitation, rephaser, a saturation block pulse, readout.

**Assumptions:** None.

#### `test_period_of_a_gre_is_one_tr`

**Checks:** The period of a block of a GRE is its TR: blocks 4 to 7 for a block of the
second TR, with its ADC block and one distinct excitation (count 1, key of
`block_pulse`). The last TR ends at the end of the file.

**How:** `_gre(3)`, `period(seq, 5)` and `period(seq, 11)`.

**Assumptions:** None.

#### `test_period_of_a_spin_echo`

**Checks:** A spin echo is one period with two distinct pulses in the order of their
first block: the excitation and the refocusing pulse, each with count 1.

**How:** `_spin_echo("y")`, `period(seq, 3)`: blocks 0 to 5, ADC in block 5.

**Assumptions:** None.

#### `test_period_counts_repeated_refocusing_pulses`

**Checks:** Two refocusing pulses with the same key before one ADC (a double spin echo)
are one distinct pulse with count 2, first block 3 and last block 6.

**How:** `_spin_echo("y", num_ref=2)`, `period(seq, 0)`.

**Assumptions:** None.

#### `test_period_of_a_tse_like_train_is_one_echo_train`

**Checks:** Refocusing pulses never start a period (decision 20 of
`docs/plans/rf-profiles.md`, as revised on 2026-09-28): a TSE-like echo train is one
period, with one distinct refocusing pulse counted once for each echo, and the next
excitation, after an ADC, starts the next period.

**How:** Two trains of an excitation, a rephaser with a crusher, and three times a
refocusing pulse, a crusher and a readout with an ADC (11 blocks each). `period` of
blocks 0, 1, 6 and 10 gives blocks 0 to 10, the first ADC in block 4, and the distinct
pulses (excitation, 1) and (refocusing, 3). `period` of block 13 gives blocks 11 to 21
with the first ADC in block 15.

**Assumptions:** None.
#### `test_period_with_fat_saturation_before_the_excitation`

**Checks:** A fat saturation and its spoiler before each excitation are in the period
of that excitation: the saturation block is the period start, and the excitation after
it is not.

**How:** Two TRs of [saturation block pulse with `freq_ppm` −3.45, spoiler, excitation,
rephaser, readout]. `period(seq, 7)`: blocks 5 to 9, pulses saturation (block 5) and
excitation (block 7).

**Assumptions:** None.

#### `test_period_joins_dummy_scans_to_the_first_adc`

**Checks:** Dummy TRs without an ADC join the period of the first ADC after them: one
distinct excitation with the count of all its blocks.

**How:** `_gre(2, dummies=3)`, `period(seq, 2)`: blocks 0 to 15, ADC in block 14, the
excitation with first block 0, last block 12 and count 4.

**Assumptions:** None.

#### `test_period_before_the_first_rf_is_the_first_period`

**Checks:** A block before the first RF block is in no period, and `period` gives the
first period for it.

**How:** A delay block and a gradient block, then two TRs. `period` of blocks 0 and 1
must both be blocks 2 to 4.

**Assumptions:** None.

#### `test_period_is_the_same_for_each_of_its_blocks`

**Checks:** Each block of a period gives the same period (the dataclasses are equal:
blocks, pulses with their keys, ADC block and flag).

**How:** `_gre(3, dummies=1)`: the period of block 6, then `period` of each of its
blocks.

**Assumptions:** None.

#### `test_period_truncated_after_max_blocks`

**Checks:** A walk longer than the limit stops at the limit and sets `truncated`; with
the default limit the whole period is found.

**How:** An excitation, 30 gradient-only blocks, and the readout. `period(seq, 15,
max_blocks=10)` must be blocks 5 to 25, `truncated`, with no pulse and no ADC block;
`period(seq, 15)` must be blocks 0 to 31, not truncated. The keyword `max_blocks`
replaces `PERIOD_MAX_BLOCKS` for this test.

**Assumptions:** None.

#### `test_rf_uses_labeled_and_unlabeled_sequences`

**Checks:** `rf_uses_labeled` is True for the test sequences and for a sequence without
RF, and False when one RF event has the use `undefined`. Then `block_pulse`, `period`,
`combined_profile` and `pulse_list` raise `ValueError` that names `rf_uses_labeled`.

**How:** A GRE, a spin echo, the MPRAGE-like sequence and an empty sequence; then a GRE
with one more block pulse made without `use=`.

**Assumptions:** None.

#### `test_combined_profile_one_direction`

**Checks:** A spin echo with the refocusing pulse on z, 1.5 times as wide as the
excitation: one direction ("z"), and the combined line equals the excitation |Mxy| times
the refocusing |β|² of the two "profile" views at the same points (exact). `line_pulses`
holds the blocks 0 and 3 with those two arrays (exact). The numbers
follow the definitions of section 4.3, item 7: the signal kept (below 1), the FWHM and
the edge width of the line, the fraction inside |u| ≤ W / 2 (sums), and the value at the
slice centre.

**How:** `_spin_echo("z", 1.5 * W)`. The numbers are computed by hand from the product
(`numpy.trapezoid`, `profile_metrics`, sums, `numpy.interp`); relative 1e-15 or exact
(the same formulas on the same arrays).

**Assumptions:** None.

#### `test_combined_profile_two_logical_directions`

**Checks:** A column spin echo (excitation on z, refocusing on y, each over ±2W with 401
points): `fraction_inside` is the product over the two directions of the sum of the
profile inside |u| ≤ W / 2 over its sum on the grid, and `centre_signal` the product of
the two profiles interpolated at 0 (section 4.3, item 7). There is no line, and
`line_pulses` is empty. With the "2d" view, the map
has the axes (y, z) with `MAP_POINTS` points, and its values are the outer product of
the refocusing |β|² and the excitation |Mxy| on those axes (exact).

**How:** The two profiles come from `simulate` on the "profile" views of the two pulses;
the numbers are computed by hand, relative 1e-12 (only the order of float sums). The map
lines come from `simulate` on the map axes.

**Assumptions:** None.

#### `test_combined_profile_three_directions`

**Checks:** A PRESS-like sequence (excitation on x, refocusing on y and on z) has three
directions. The numbers are the products over the three directions. With the "2d" view,
there are three maps (x-y, x-z, y-z), each the outer product of two direction lines times
the third direction at its slice centre.

**How:** `n` = 41. The lines come from `simulate` on the "profile" views of the pulses;
the value at a slice centre from `simulate` with a spec without axes (one point at 0).
Relative 1e-12.

**Assumptions:** None.

#### `test_combined_profile_oblique_direction`

**Checks:** Excitation on x and refocusing oblique in the x-y plane (60° from x) give
two directions ("x", "select"). The "2d" map has the in-plane axes "s1" (x) and "s2"
(perpendicular to x in that plane), and each value equals the excitation |Mxy| times the
refocusing |β|² from `rf_sim.spin_domain` at the 3D grid point. The "s2" range puts the
range of the refocusing pulse on the line s1 = 0.

**How:** `n` = 21. The test builds the 3D points from the map axes (s1 along x, s2 along
y) and calls `spin_domain` for each pulse. Absolute 1e-12 (the oblique gradient is
parallel to its direction only within rounding). The ends of the "s2" axis times sin 60°
must equal the ends of the refocusing pulse's "profile" range (relative 1e-12).

**Assumptions:** None.

#### `test_combined_profile_non_selective_refocusing_is_a_factor`

**Checks:** A hard refocusing pulse (kind "none") is a factor: its |β|² at r = 0,
df = 0, which is 1 for a 180° pulse on resonance. The line is the excitation |Mxy| times
that factor (exact), and `line_pulses` has only the excitation (block 0, its |Mxy|,
exact): a pulse of kind "none" is the factor, not a pulse on the line.

**How:** `_spin_echo("y", hard_ref=True)`. The factor from `simulate` with a spec
without axes, compared with 1 within 1e-12 (sin²(90°), only rounding).

**Assumptions:** None.

#### `test_no_combined_profile_reasons`

**Checks:** There is no combined profile, with the reason and empty fields (factor NaN,
no line, empty `line_pulses`), for: a GRE (no refocusing pulse), a period without an ADC (`NO_ADC`), a refocusing pulse
of kind "changing" (`DIRECTION_CHANGES`), an inversion pulse between the excitation and
the ADC (`OTHER_RF_BEFORE_ADC`), and a refocusing pulse without an excitation before the
ADC.

**How:** Parametrized over five builders; `combined_profile(seq, period(seq, 0))`.

**Assumptions:** None.

#### `test_fat_saturation_before_the_excitation_does_not_take_part`

**Checks:** A fat saturation before the excitation is in the period but not in the
combined profile, which has the excitation and the refocusing pulse only.

**How:** `_spin_echo("y")` with a saturation block and a spoiler before it: the period
starts at block 0, and the combined profile has the excitation block 2 and the
refocusing block 5.

**Assumptions:** None.

#### `test_profile_view_for_each_kind`

**Checks:** The "profile" view of kind "one" with W is c ± 2W with `NUM_POSITIONS`
points (c = f / G), and the pulse has no note. Without W, it is c ± 2 times the spectrum
thickness (the FWHM of the zero-padded spectrum over |G|), `n` replaces the number of
points, and the pulse has the note `NO_SLICE_THICKNESS`. Kind "none" is f ± 2B on `df`,
and has no "z_df" view (with its reason).

**How:** A sinc with a 1 mm offset, with and without the `SliceThickness` definition,
and a block pulse at −200 Hz. The spectrum FWHM is computed in the test with numpy
(`SPECTRUM_PADDING` zero padding); relative 1e-12. Kind "changing" is in
`test_gradient_kind_changing_for_a_turning_gradient`.

**Assumptions:** None.

#### `test_z_df_grid_lines_equal_1d_profiles`

**Checks:** For a pulse whose gradient is not constant (the RF is longer than the flat
top, so the whole grid is simulated), each row of the "z_df" view equals the 1D `df`
profile with that z in `at`, and each column the 1D z profile with that `df` in `at`
(exact). The `df` step is |G| times the z step (G the mean during the RF), and the `df`
axis is centred on 0.

**How:** `view_spec(pulse, "z_df", n=15)`; rows 0, 7, 14 and columns 0, 5, 14 are
compared with `simulate` on 1D specs.

**Assumptions:** None.

#### `test_z_df_shear_equals_the_full_grid`

**Checks:** With a constant gradient, `simulate` computes the "z_df" view as one 1D
simulation of the distinct values z + df / G. It equals the whole grid from
`rf_sim.spin_domain` at each (z, df) point, for either sign of G.

**How:** Parametrized over the sign of G. A sinc with a 300 Hz offset and `n` = 25; the
reference grid calls `spin_domain` on the meshgrid of the two axes. Absolute 1e-12 on
`a` and `b` (rounding of z + df / G against G × z + df).

**Assumptions:** None.

#### `test_2d_view`

**Checks:** The "2d" view of a pulse of kind "changing": with `plane` and `extent_m`
(those axes, ±e/2, `MAP_POINTS` points); with the `FOV` definition (the two axes with the
largest RMS gradient, x and y, each ± half its FOV, `n` points); with neither (None and
`NO_FOV`). A pulse of kind "one" has no "2d" view.

**How:** The turning gradient of `_turning_gradients` with a block pulse; the FOV
definition (0.2, 0.25, 0.005) m; a `simulate` of the 9 × 9 spec has the shape (9, 9).

**Assumptions:** None.

#### `test_quantities_and_widths_for_each_use`

**Checks:** For each use of section 4.3, item 2: `quantity` gives |2 conj(a) b|,
|a|² − |b|² and |b|² (exact), and raises `ValueError` for another name. `widths` measures
the profile of the use (excitation, preparation and other |Mxy|; refocusing |β|²;
inversion (1 − Mz) / 2; saturation 1 − Mz) at u − c (exact). Only the excitation, which
has a pathway, gets the phase numbers; its echo phase is 0 at the slice centre (within
1e-15, the rounding of z × exp(−i angle(z))) and NaN exactly where |Mxy| < 10 % of its
maximum. The other uses have no echo phase.

**How:** Parametrized over the six uses with their flip angles. A sinc with a 0.5 mm
offset, its rephaser and a readout; `n` = 201. For "other", the letter "o" is set in
`rf_library.type` (see the assumptions of the whole file).

**Assumptions:** None.

#### `test_rephasing_error_of_a_1_5x_rephaser`

**Checks:** A rephaser of 1.5 times the correct moment m leaves 0.5 × m, a linear echo
phase 2π × 0.5 × m × u, so the rephasing error grows by 0.5 × 2π × m × W against the
correct rephaser. `echo_moment_per_m` with the pathway moment gives the same numbers as
the pathway.

**How:** Two sequences: the sinc, its rephaser times 1.0 or 1.5 (`pp.scale_grad`), and a
readout. The difference of the two errors is compared with 0.5 × 2π × m × W within 1e-6
(the plan's tolerance; the difference is exact up to rounding, because the added phase
is linear and the weights are the same).

**Assumptions:**

- The rephasing error of the correct rephaser is not 0 for a 90° sinc: the pulse's own
  non-linear phase has a linear part (1.04 rad for this pulse; it grows about as the
  flip angle squared). So the test compares the two sequences, not the 1.5 case alone.

#### `test_spec_errors`

**Checks:** `simulate` raises `ValueError` for each rule of the specs (section 4.2 of the
plan): an unknown kind, a kind two times in the axes, a kind in the axes and in `at`,
"select" with z, "select" for a pulse whose select coordinate is a logical axis, an axis
with 1 point, an axis with lo = hi, and more than `MAX_POINTS` points.

**How:** Parametrized over the eight specs, with a pulse on z or an oblique pulse.

**Assumptions:** None.

#### `test_argument_errors`

**Checks:** The other argument checks: a number of points that is not an int
(`TypeError`); an unknown view, a plane that is not two different logical axes, a
negative `extent_m`, and `n` < 2 in `view_spec`; an unknown view in
`combined_profile` (`ValueError`); a play index outside the file in `block_pulse` and
`period` (`IndexError`).

**How:** A pulse on z, a pulse with a turning gradient, and `_spin_echo("y")` (6 blocks,
so −1 and 6 are outside).

**Assumptions:** None.

#### `test_pulse_list_rf_spoiling_and_slices_give_one_entry`

**Checks:** An RF-spoiled GRE with three slices (a new phase offset in each block and
three frequency offsets) gives one entry with all 12 RF blocks. Its use, gradient kind
and numbers are those of `block_pulse` for its first block (exact).

**How:** `_gre(4, rf_spoiling=True, slices=(-5 mm, 0, 5 mm))`. The flip angle is also
checked against 90° within 0.5°.

**Assumptions:** None.

#### `test_pulse_list_mprage_like_blocks_give_one_entry`

**Checks:** The MPRAGE-like blocks (a different phase-encode gradient before or after
the RF, and one block with the RF alone) give one entry of kind "none" with all 5 RF
blocks, also after a write and a read of the file. A spin echo gives two entries in
block order, and a sequence without RF none.

**How:** Parametrized over "before" and "after", as
`test_pulse_key_ignores_gradients_outside_the_rf`.

**Assumptions:** None.

#### `test_rotations_are_refused`

**Checks:** A sequence with a rotation library makes `block_pulse`, `period`,
`combined_profile` and `pulse_list` raise `NotImplementedError`.

**How:** A GRE with a `rotation_library` that holds one quaternion, as
`tests/test_extensions.py` stores it (pypulseq draft PR #372).

**Assumptions:** None.

#### `test_peak_b1_of_another_nucleus`

**Checks:** With the gyromagnetic ratio of sodium (`pp.Opts(gamma=11.262e6)`), the peak
B1 of a block pulse is its amplitude divided by that gamma, in µT, and the energy and
the flip angle follow.

**How:** A 90°, 0.5 ms block pulse: amplitude flip / (2π × duration) = 500 Hz, so
B1 = 500 / 11.262e6 × 1e6 µT. Relative 1e-9 (only rounding).

**Assumptions:** None.

### 2.32 RF profiles in JavaScript (`test_rf_profiles.js`)

`rf_profiles.js` is the JavaScript copy of the Python reference of RF pulse profiles
(`rf_profiles.py`, `rf_sim.py` and `profile_metrics.py`; `docs/plans/rf-profiles.md`,
sections 4.2, 4.3 and 4.6; task 3.3): `spinDomain` and its sliced form
`spinDomainRange`, `magnetization`, `crushedEcho`, `precess`, the profile metrics,
`linspace`, `unwrap`, `fft` and the RF spectrum (`spectrumMagnitudes`,
`spectrumFwhmHz`), `fileData`, `blockPulse` (the RF as played, the interval gradients,
the gradient kind, the pulse key and the echo pathway), `period`, `viewSpec`,
`simulation` and `simulate`, `quantity`, `echoPhase`, `widths` and `combinedProfile`.
The golden test (section 2.33) holds its values to the Python reference; these tests
check each rule on small hand-made cases, without Python.

The tests load `rf_profiles.js` directly with Node's `require`, and use `node:test` and
`node:assert/strict`, with no browser or DOM. Each test builds its sequence with the
helper `newSeq`: RF rows (the columns of `cards.rf_profile.rf_table`, made by
`rfTables`), gradient events in mT/m (as the diagram tables keep them, read back with
`gradHzPerValue` 42576), ADC events and blocks. `build` returns a fake sequence view
(`fakeView`: the methods of `SeqLanes.sequenceView` over those arrays) and the file
data of `RfProfiles.fileData`. Equal events share one dense index, as pypulseq's
libraries share one id. The pulses follow `tests/test_rf_profiles.py`: a 1 ms
Hann-windowed sinc (time-bandwidth product 4, 200 samples at 5 µs, from 100 µs) on a
trapezoid whose flat top holds the whole RF, rephasers, crushers of four cycles across
W = 5 mm, and a readout trapezoid with its ADC; `gre`, `spinEcho` and `turning` build
the common sequences. The whole file runs in about 0.2 s.

**Assumptions for the whole file:**

- The functions take only plain values (numbers, typed arrays, the fake view, the file
  data) and return only plain values. Nothing in a test depends on the page or a
  browser.
- "Exact" means bit-for-bit equal (`Object.is` for each value, or `deepEqual`): the test
  makes the same points and calls the same simulation or the same float operations,
  so no float difference is possible.
- The fake view has the methods and the units of `SeqLanes.sequenceView` (section 2.19
  tests the real one); the fake RF table has the columns of `rf_table` (section 2.34
  tests the real one).
- Numbers written in a test from numpy (`linspace`, `unwrap`, the spectrum FWHM) come
  from numpy 2.5.3, with the numpy command in a comment next to them.

#### `test_spin_domain_hard_pulse_flip_angle_and_precess_sign`

**Checks:** A 70° hard pulse without a gradient gives |Mxy| = sin(70°) and Mz =
cos(70°) at r = 0 and 0 Hz. `precess` has the sign of free precession in `spinDomain`,
as `test_precess_sign_matches_free_precession_in_spin_domain` in `test_rf_sim.py`.

**How:** A pulse of 200 samples at 1 µs with the phase 0.4 rad; |Mxy| and Mz within
1e-12 (the float rounding of 200 rotations). Then the same pulse under a z gradient of
1e5 Hz/m at 13 points from -3 mm to 3 mm, and the same pulse followed by 500 samples of
zero RF: `precess` of the first Mxy with the moment of those 500 samples equals the
second Mxy within 1e-9 (the Python test's tolerance, the rounding of 700 rotations),
and with the opposite moment it differs by more than 1e-3.

**Assumptions:** None beyond the file's own.

#### `test_linspace_gives_the_numpy_values`

**Checks:** `linspace` gives the values of `numpy.linspace` exactly, including the last
value, which numpy sets to the end itself.

**How:** Three ranges, compared with the numpy values written in the test. For 0.1 to
1.7 with 6 points, 5 × step + 0.1 is 1.6999999999999997, and the last value must be 1.7.

**Assumptions:** None beyond the file's own.

#### `test_fft_matches_a_direct_dft_and_the_spectrum_fwhm_matches_numpy`

**Checks:** `fft` equals a direct DFT for lengths with each kind of factor (4, 2, 3, 5,
the small prime 7, and the primes 97 and 131, which use Bluestein's method), within
1e-12 of the largest magnitude. `spectrumMagnitudes` (64 DFTs of length n of the
pre-twiddled signal) equals the magnitudes of a direct DFT of the signal zero padded to
64 n, the same tolerance. `spectrumFwhmHz` of a block pulse equals numpy's FWHM
exactly.

**How:** Seeded pseudo-random complex signals of lengths 1, 2, 3, 5, 7, 12, 30, 97, 128,
131 and 3000, and of 7, 12 and 97 samples for the padded spectrum. The direct DFT
reduces each index product modulo N before its twiddle, so its own error is about one
rounding of `Math.cos`; both results are exact up to float rounding (about 1e-15 here).
Then a block pulse of 100 samples of 250 Hz at 1 µs, as played by `blockPulse` with
1000 Hz and 0.4 rad, and the same pulse without offsets: 12031.25 Hz and 11875.0 Hz, the
values of `rf_profiles._spectrum_fwhm_hz` (the numpy command is in the test). The FWHM
is exact because it is the difference of two frequencies k / (N dt) of the same bins.

**Assumptions:** None beyond the file's own.

#### `test_unwrap_matches_numpy`

**Checks:** `unwrap` gives the values of `numpy.unwrap` exactly, including a step of
exactly π and of exactly -π, which numpy keeps.

**How:** Eleven phases whose steps are 3, -6, π, 0.858, -π, 4.64, -5, 2.7, 6.8 and -14
rad; the test first checks that two steps are exactly ±π, then compares with the numpy
values written in the test.

**Assumptions:** None beyond the file's own.

#### `test_interval_values_of_a_trapezoid_equal_the_hand_means`

**Checks:** The gradient of each hold interval is the mean of the trapezoid over it:
on the ramp, across the corner, on the flat top, on the fall, across the end and after
the end, as `test_interval_values_of_a_trapezoid_equal_the_hand_means` of
`test_rf_profiles.py`. The kind is "one" on z and not constant.

**How:** A 900 µs RF of 300 samples at 3 µs from 60 µs (so the corners on the 10 µs
raster fall inside hold intervals), on a trapezoid of 2e5 Hz/m with 100 µs ramps and a
500 µs flat top. The intervals 0, 13, 180 and 213 are compared with the hand means
within a relative 1e-12 (the rounding of the interval ends); interval 80 (flat top)
exactly, and all intervals after the end and all x and y values are 0.

**Assumptions:** The amplitude the module reads is the table value in mT/m times 42576;
the test uses that value for the hand means.

#### `test_gradient_kinds_none_one_oblique_and_changing`

**Checks:** The gradient kinds of `gradientKind`: "none" without a gradient (no select
coordinate, direction, G or slice centre, not constant); "one" on z for a trapezoid on
z (direction (0, 0, 1), each interval the flat-top amplitude, G the mean, constant);
"one" with the select kind "select" for the same trapezoid times 0.6 on x and 0.8 on y
(direction (0.6, 0.8, 0), G = |mean|, constant); "changing" for a gradient that turns,
and for a bipolar gradient on one axis (a mean of zero has no direction).

**How:** Three pulses in one sequence and the turning gradients of `turning`
(arbitrary gradients on x and y, as `_turning_gradients` of `test_rf_profiles.py`).
Each flat-top interval value exactly; G within a relative 1e-12 (the sum of the 200
interval values rounds); the oblique direction within 1e-12 (the scaled table values
round).

**Assumptions:** None beyond the file's own.

#### `test_views_for_each_kind`

**Checks:** `viewSpec`: "profile" of kind "one" with W (c ± 2W, 401 points, c = f / G);
without W (c ± 2 × the spectrum FWHM / |G|, and the note NO_SLICE_THICKNESS); of kind
"none" (df from f - 2B to f + 2B); of kind "changing" (the reason); "z_df" (201 points
on each axis, the df step |G| times the z step, centred on 0 Hz) and its reason for
kind "none"; "2d" with `plane` and `extentM`, with the FOV definition (the two axes
with the largest RMS gradient, x and y), with neither (NO_FOV), and its reasons for the
kinds "one" and "none".

**How:** Pulses with a frequency offset of 800 Hz (sinc) and -200 Hz (hard), a file
without W, and the turning gradients with and without an FOV. The axes are compared
exactly with the same operations as the reference; c against f / G within a relative
1e-12 (G is a mean). A spec of the FOV view is simulated to check its shape (9 × 9).

**Assumptions:** None beyond the file's own.

#### `test_echo_pathway_of_a_gre_rephases_the_select_and_readout_moments`

**Checks:** The echo pathway of a GRE: the rephaser in the next block cancels the
dephasing of the pulse and the prephaser the readout moment; the pathway ends at the
ADC of the same TR with the sign +1.

**How:** `gre(2)`, the excitation of the second TR (block 4): the ADC block is 6, the z
moment is -half (the moment from the RF centre to the RF end) and the x moment 0,
within 1e-9 of the moment each cancels (the rephasing tolerance of the plan); the y
moment is exactly 0.

**Assumptions:** None beyond the file's own.

#### `test_echo_pathway_of_a_spin_echo_has_sign_minus_one`

**Checks:** A spin echo with crushers around the refocusing pulse on y: the sign is -1,
the z moment is +half (the conjugation turns the dephasing), and the crusher and
readout moments cancel. A refocusing pulse has no pathway and no reason.

**How:** `spinEcho("gy")`: the ADC block is 5; the moments within 1e-9 of the moment
each cancels.

**Assumptions:** None beyond the file's own.

#### `test_echo_pathway_without_an_adc_before_the_next_excitation`

**Checks:** No pathway, with the reason NO_ADC, for an excitation followed by another
excitation before any ADC (a dummy TR), for one at the end of the file, and for a walk
longer than `maxBlocks`. The last excitation before the ADC has its pathway.

**How:** `gre(1, 1)` (one dummy TR, then one TR), block 0 and block 4 (and block 4 with
`maxBlocks` 1); a file with only an excitation and its rephaser.

**Assumptions:** None beyond the file's own.

#### `test_echo_pathway_stops_at_a_saturation_pulse`

**Checks:** A saturation pulse between an excitation and its ADC: no pathway, with the
reason OTHER_RF_BEFORE_ADC.

**How:** An excitation, its rephaser, a hard saturation pulse, then the readout.

**Assumptions:** None beyond the file's own.

#### `test_period_of_a_gre_spin_echo_and_tse_like_train`

**Checks:** `period` for a GRE (the period of a block of the second TR is that TR, with
one distinct excitation, and RF spoiling gives one pulse key; the last TR ends at the
end of the file), a spin echo (the excitation and the refocusing pulse in one period),
and a TSE-like train (refocusing pulses never start a period: one period for each
train, with one distinct refocusing pulse counted three times).

**How:** `gre(3)`, whose TRs each have their own RF row with a new phase and the same
`key`; `spinEcho("gy")`; two trains of an excitation and three [refocusing, crusher,
readout] groups. The first block, the last block, the first ADC block, `truncated` and
the pulses (use, first block, last block, count) are compared exactly, from several
blocks of each period.

**Assumptions:** None beyond the file's own.

#### `test_period_with_fat_saturation_dummies_and_blocks_before_the_first_rf`

**Checks:** A fat saturation before each excitation is the period start, and the
excitation after it is not; dummy TRs without an ADC join the period of the first ADC
(one distinct excitation with the count of all its blocks); a block before the first
RF block gives the first period; each block of a period gives the same period.

**How:** Two TRs of [saturation, spoiler, excitation, rephaser, readout] (period of
block 7: blocks 5 to 9); `gre(2, 3)` (period of block 2: blocks 0 to 15, first ADC 14,
count 4); a delay block and a gradient block before two TRs (the period of blocks 0 and
1 is blocks 2 to 4); `gre(3, 1)` (the period of each block of the period of block 6,
with `deepEqual`).

**Assumptions:** None beyond the file's own.

#### `test_period_truncated_after_max_blocks`

**Checks:** A walk longer than `maxBlocks` sets `truncated`, and the period starts and
ends at the limits of the walks; with the default limit, the whole period.

**How:** An excitation, 30 gradient blocks, then the readout: the period of block 15
with `maxBlocks` 10 is blocks 5 to 25, truncated, with no pulses and no ADC; with the
default, blocks 0 to 31 with the ADC block 31.

**Assumptions:** None beyond the file's own.

#### `test_combined_profile_of_one_direction_is_the_product_of_the_profiles`

**Checks:** The combined profile of a spin echo with the refocusing pulse on z (1.5 W
wide): one direction; its line is the excitation |Mxy| times the refocusing |β|² of
their "profile" views at the same points, exactly; `linePulses` has the blocks 0 and 3
with those two arrays, exactly; less signal is kept than the excitation alone makes;
the numbers have the keys of the reference, in its order.

**How:** `combinedProfile` of the period of block 0 (done only after `step`), against
`simulate` of the two "profile" views and `quantity`. Exact: the same grid (both views
use c ± 2W) and the same simulations.

**Assumptions:** None beyond the file's own.

#### `test_combined_profile_of_two_logical_directions_is_the_outer_product`

**Checks:** The combined profile of an excitation on z and a refocusing pulse on y,
view "2d": no line and no `linePulses`, the numbers `centre_signal` and
`fraction_inside`, and one map on
the axes y and z (in the order x, y, z) whose values are the outer product of the
refocusing |β|² on its y axis and the excitation |Mxy| on its z axis, exactly.

**How:** `combinedProfile` with `n` 21, then `simulate` of each pulse on the map axis of
its direction and `quantity`; the outer product is made in the test. Exact: the same
points and simulations, times the factor 1.

**Assumptions:** None beyond the file's own.

#### `test_line_cache_gives_the_same_results_and_reuses_the_profiles`

**Checks:** The line cache of `rf_profiles.js` (its module comment): a combined profile
with a cache that already holds the "profile" view of each distinct pulse of the period
gives the same reason, blocks, factor, directions, numbers, line, `linePulses` and maps
as one without a cache, for both views ("profile" and "2d"), for five periods: a column
spin echo (two logical directions), a spin echo with a 1.5 times thicker refocusing
slice on the same axis, the same without the `SliceThickness` definition W, a train of
two refocusing pulses with the same key before the first ADC, and an excitation and a
refocusing pulse on one oblique direction ("select"). With the "profile" view, the work
adds no line with W (every line of the combined profile is then the grid of a pulse's
own view, c ± 2W), and it is done before its first `step`; without W it adds one line
(the refocusing pulse on the excitation's grid) and needs a `step`.

**How:** For each case, `simulate` with a new `Map` on the "profile" view of the first
block of each distinct pulse of the period (one entry each), then `combinedProfile`
with that cache, against `combinedProfile` without one. The arrays are compared value by
value with `===` (or both NaN), not `Object.is`: along "select", a point of the cache
and a point of the combined profile can differ in the sign of a zero (0 + x against
x), which does not change a value. The oblique case checks only the results: whether
the two pulses' directions are equal to the last bit (and so whether the refocusing
pulse's own view is a line of the combined profile) depends on rounding.

**Assumptions:** None beyond the file's own.

#### `test_simulation_with_the_line_cache`

**Checks:** A `simulation` with a cache adds its 1D line to the cache when its work is
done; a second `simulation` of the same pulse and spec with that cache is done at once
(`done` true, `step(0)` returns 1), with the same typed arrays and an equal grid. A
"df" axis, a z × Δf spec and a spec with an `at` value are not lines of the cache: they
leave it unchanged.

**How:** The excitation of `spinEcho("gy")`, its "profile" view, and the three other
specs with 11 points.

**Assumptions:** None beyond the file's own.

#### `test_step_with_small_budgets_gives_the_same_arrays`

**Checks:** Sliced work does not change a value: `step(0)` until done gives exactly the
arrays of one `step(Infinity)`, for a 1D profile, a z × Δf shear, a 2D grid and a
combined profile with a map. The fraction that `step` returns grows to 1, and each case
takes several slices. `result()` throws before the work is done.

**How:** The excitation of `spinEcho("gy")`: its "profile" view (401 points), its
"z_df" view with 41 points (81 points of work), and a 17 × 13 grid on z and x; the
combined profile of the period with view "2d" and `n` 21. Each value is compared with
`Object.is`.

**Assumptions:** `step(0)` computes one chunk of points (about 4096 point-samples), so a
200-sample pulse takes 20 points for each call and each case needs several calls.

#### `test_z_df_shear_equals_the_full_grid`

**Checks:** With a constant gradient, the "z_df" view is one 1D simulation of the
distinct values z + Δf / G; it equals `spinDomain` at each (z, Δf) grid point, for both
signs of G.

**How:** An excitation with 300 Hz on a trapezoid of each sign; the "z_df" view with 25
points on each axis, against `spinDomain` called at the 625 grid points (z on the z
axis, Δf as `df`), within 1e-12 (the float rounding of z + Δf / G against G z + Δf).

**Assumptions:** None beyond the file's own.

#### `test_spec_and_argument_errors`

**Checks:** Each rule of the specs throws with the message of `rf_profiles._check_spec`
(an unknown kind, a kind twice in the axes, a kind in the axes and in `at`, "select"
with z, "select" for a pulse on a logical axis, a number of points that is not an
integer (TypeError), one point, lo not below hi, an `at` value that is not finite, more
than `MAX_POINTS` points), and the other argument checks: an unknown view, a bad
`plane`, `extentM` <= 0, `n` < 2, an unknown quantity, an unknown combined view, a block
that is not a play index and `maxBlocks` < 1 (RangeError, for `blockPulse` and
`period`), a file without RF for `period`, and `result()` before the work is done.

**How:** Each call inside `assert.throws`, with the error type and a pattern of the
Python message.

**Assumptions:** None beyond the file's own.

#### `test_file_data_checks_the_rf_table`

**Checks:** `fileData` returns a frozen object with the entry's values (null for no W),
and refuses a file without use labels, a missing column, and a column of another
length.

**How:** The RF table of `spinEcho("gy")` with a hand-made entry; a copy without the
`center` column; a copy whose `dt` column has one value.

**Assumptions:** None beyond the file's own.

#### `test_widths_keys_follow_the_reference`

**Checks:** The keys of `widths`, in the reference's order, are missing when the Python
leaves them out: an excitation with W and a pathway has all seven, also with a moment
of the caller; a refocusing pulse has no phase numbers; a Δf profile has only the two
widths. The echo phase is 0 at the grid point of the slice centre and NaN below 10 % of
the maximum |Mxy|, and a moment that is not 3 values throws.

**How:** The pulses of `spinEcho("gy")` and their "profile" views, and a Δf axis for the
excitation. The centre phase within 1e-15 (the angle of z exp(-i angle(z)) rounds, as
the Python test).

**Assumptions:** None beyond the file's own.

### 2.33 RF profiles against Python (`test_rf_profiles_golden.py`)

`test_rf_profiles_golden.py` is the golden test of task 3.4 of
`docs/plans/rf-profiles.md`: it checks that `RfProfiles`
(`assets/rf_profiles.js`), run through Node on real diagram tables and RF
profile card file data, gives the same values as the Python reference
(`rf_profiles.py`) for the period, every RF block, the first block of every
distinct pulse and period (each view: `profile`, `z_df` and `2d`, with its
widths and echo phase for `profile`), and the combined profile of the first
echo. `tests/js/golden_rf_profiles.js` is the Node half: given a JSON file
with one sequence's encoded diagram tables, its lane metadata, its RF
profile card file entry (`cards.rf_profile.rf_profile_data`, with the RF
table) and a list of `period`, `pulse`, `view` or `combined` queries, it
decodes the tables, builds `SeqLanes.sequenceView` and `RfProfiles.fileData`,
answers each query with `RfProfiles`, and writes the results as JSON. It is
not named `test_*.js`, so `node --test` does not try to run it on its own;
`test_rf_profiles_golden.py` runs it with `subprocess.run`.

The comparison uses a different tolerance for each kind of value, matching
section 3.5, item 2 of the plan and the reason each value can differ at all:

- **Exact** (`==`): the period fields, a period's pulses in order (`use`,
  `first_block`, `last_block`, `count`), a block pulse's `use`,
  `gradient_kind`, `select_kind`, `constant_gradient`, `dt_s`,
  `freq_offset_hz`, `nominal_m`, `fov_m`, `notes`, `echo_reason`, the echo
  `sign` and `adc_block`, every reason text, the kinds and `n` of each spec
  axis, and a combined profile's `reason`, blocks and `directions`. `dt_s`
  and `freq_offset_hz` are exact because both languages read them straight
  from the RF table's `dt` and `freq_hz` columns, which `rf_profiles.py`
  itself computes with the same formula in the same order as
  `cards.rf_profile.rf_table`, so the two Python computations already agree
  bit for bit before either reaches JavaScript.
- **The pulse key partition**: a Python key is a tuple and a JavaScript key
  is a string, so the test never compares them by value. Instead, every
  block it asks about builds a bijection between the two representations
  and asserts that the bijection is never many-to-one on either side --
  "the partition of the RF blocks by key must be the same".
- **Float rounding of the same arithmetic** (relative 1e-12 of the largest
  value of the array, or of the scalar itself): the signal (`sigRe`,
  `sigIm` against `signal_hz`), the interval gradients (JavaScript
  multiplies the diagram table's mT/m by 42576 Hz/m per mT/m where Python
  divides pypulseq's Hz/m by `seq_utils.GAMMA` and multiplies by 1e3),
  `direction`, `select_gradient_hz_per_m`, `slice_centre_m`, `flip_deg`,
  `peak_b1_ut`, `energy_ut2_ms`, a spec's `lo`/`hi` away from the
  spectrum-FWHM cases below, the grids, the combined `factor`, the line's
  `u`, and the maps' axes.
- **The spectrum FWHM**: the first axis of a "profile" or "z_df" spec of
  kind "none", and of kind "one" without a nominal thickness, comes from the
  FWHM of the zero-padded RF spectrum, which two independent FFTs compute
  (numpy's in Python, a mixed-radix FFT in JavaScript). The FWHM is the
  distance between two discrete frequency bins, so it is equal unless a
  magnitude next to the edge of "at or above half the maximum" is within a
  relative 1e-9 of that half, where float rounding alone could pick another
  bin. The test asserts that each such pulse is outside that margin (with
  numpy's FFT of the pulse's own signal; a pulse inside it fails with a
  message to use another test pulse), and then holds `lo` and `hi` to the
  relative 1e-12 rule: a bin of difference would move them by about 1e-3.
- **`a` and `b`** (absolute 1e-12, the plan's own rule): both are bounded
  (`|a|^2 + |b|^2 = 1`), so an absolute tolerance is the natural one;
  `mxy_abs`, `mz` and `beta_sq` are plain algebra on `a` and `b`, so they get
  the same absolute 1e-12.
- **The echo moment** (absolute 1e-9 /m): moments add terms of order 1e2 /m,
  so rounding is many orders below 1e-9; 1e-9 /m is a phase of about
  6e-11 rad over 1 cm.
- **The echo phase** (absolute 1e-9 rad where both are finite): the NaN
  masks (`|Mxy| < 10%` of its maximum) must be equal except where `|Mxy|` is
  within an absolute 1e-9 of that threshold.
- **Widths**: `fwhm` and `edge_width` (and the combined `fwhm_m`,
  `edge_width_m`) are equal within a relative 1e-12 of the axis (or line)
  range, or -- only where a profile value is within an absolute 1e-9 of that
  width's own threshold (half the maximum for `fwhm`; 10% or 90% for
  `edge_width`) -- exactly one grid step apart, because these numbers are
  read straight off the sample grid with no interpolation, so a threshold
  crossing that float rounding alone could move to the neighboring grid
  point in one implementation and not the other is expected there and
  nowhere else. `passband_ripple`, `stopband_level`, `signal_kept`,
  `fraction_inside` and `centre_signal` get the relative-1e-12 rule; the
  phase numbers (`rephasing_error_rad`, `nonlinear_residual_rad`,
  `centre_phase_rad`) get the absolute 1e-9 rad rule.
- **Maps and lines of the combined profile** (absolute 1e-12): a combined
  value is a product of `mxy_abs`/`beta_sq` values, the same reasoning as
  `a` and `b`; the values of each pulse on the line (`line_pulses`, whose blocks
  must be equal) are `mxy_abs`/`beta_sq` values themselves.

#### `test_rf_profiles_js_matches_python_reference`

**Checks:** For each of 16 sequences (one test each) -- the phase 2 test sequences and the two
vb-pulseq-like spin echoes named in the task (a column spin echo:
excitation on z, refocusing on y; and excitation and a 1.5&times; wider
refocusing pulse, both on z), a TSE-like train, a non-selective refocusing
pulse, a fat saturation before the excitation, an inversion between the
excitation and the ADC, a PRESS-like sequence and an oblique direction, a
turning gradient with a `FOV` definition, a block pulse and a sinc without
`SliceThickness`, an MPRAGE-like block, a sequence of another nucleus, a
sequence with `freq_ppm` on a system with `B0` set, and the example GRE of
`examples/gre_report.py` -- `RfProfiles` gives the same period (for every
block, plus a few with `maxBlocks: 1` for `truncated`), the same pulse (for
every block with RF), the same view spec/profile/quantities/widths/echo
phase (for the first block of every distinct pulse of every period, all
three views, with one `echoMomentPerM` override), and the same combined
profile (`profile` and `2d`, for the first block of every distinct period)
as `rf_profiles.py`, within the tolerances above. 1055 queries in total; the
16 tests run in about 13 s.

**How:** Parametrized over the 16 sequences. For its sequence, the test builds a `period` query for every
block, a few `period` queries with `maxBlocks: 1`, a `pulse` query for
every RF block, a `view` query (all three views) for the first block of
every distinct pulse of every period, and a `combined` query (both views)
for the first block of every distinct period, then writes the sequence's
encoded diagram tables, lane metadata and RF profile card file entry
alongside the queries to a JSON file and runs
`tests/js/golden_rf_profiles.js` with Node on it. It then recomputes each
query's answer with `rf_profiles.py` (`period`, `block_pulse`,
`view_spec`, `simulate`, `quantity`, `widths`, `echo_phase`,
`combined_profile`) and compares field by field with the rule above that
applies to it. Most view and combined queries use a small grid (101 points
for `profile`, 31 for `z_df` and `2d`, 21 for a combined profile) to keep
the whole file inside its time budget; three sequences whose pulses are
short and never need a full spatial map (the RF-spoiled GRE, the column
spin echo, and the MPRAGE-like block) use the library's default sizes (401,
201, 128) instead, for a few queries at full size.

**Assumptions:**

- `node` must be on `PATH` (both devShells have it); if it is not, the test
  fails with a message naming the missing dependency, rather than skipping.
- `rf_sim.spin_domain`, `profile_metrics` and the rest of `rf_profiles.py`
  are correct: sections 2.29, 2.30 and 2.31 test them against an
  independent oracle and closed forms. This file only checks that
  `RfProfiles` agrees with them, not that either is physically correct.
- A block's echo pathway, its widths and its echo phase are read from the
  `BlockPulse`/`Profile` this file itself builds with `rf_profiles.py`, not
  from a second, independent computation, so a bug shared between
  `rf_profiles.py` and this file's expectations would not be caught here;
  task 2.5's own tests (section 2.31) are the independent check on the
  Python side, and phase 2b's external references (section 2.35) check the
  physics.

Measured largest differences (2026-09-28; the inputs are fixed, so a rerun
gives the same numbers):

| Comparison | Largest measured difference | Tolerance |
|---|---|---|
| `a`, `b` | 1.08e-14 (abs) | 1e-12 abs |
| combined line/map values | 7.88e-15 (abs) | 1e-12 abs |
| combined `line_pulses` values | 2.89e-15 (abs) | 1e-12 abs |
| `signal_hz` | 2.14e-16 (rel) | 1e-12 rel |
| `grad_hz_per_m` | 2.91e-16 (rel) | 1e-12 rel |
| `direction`, `select_gradient_hz_per_m`, `slice_centre_m` | 0 (exact this run) | 1e-12 rel |
| `flip_deg`, `peak_b1_ut`, `energy_ut2_ms` | 1.89e-15, 0, 2.60e-15 (rel) | 1e-12 rel |
| quantities (`mxy_abs`, `mz`, `beta_sq`) | 2.12e-14 (abs) | 1e-12 abs |
| echo moment | 1.14e-13 /m (abs) | 1e-9 /m abs |
| echo phase | 1.80e-14 rad (abs) | 1e-9 rad abs |
| `fwhm`, `edge_width` (and combined) | 0 (exact this run; the one-grid-step branch was never used) | 1e-12 rel of range, or one grid step near a threshold |
| `passband_ripple`, `stopband_level` | 3.90e-14, 8.18e-15 (rel) | 1e-12 rel |
| `rephasing_error_rad`, `nonlinear_residual_rad`, `centre_phase_rad` | 2.66e-15, 2.66e-15, 8.88e-16 rad (abs) | 1e-9 rad abs |
| combined `factor`, `signal_kept`, `fraction_inside`, `centre_signal` | 0, 8.80e-16, 8.69e-16, 8.88e-16 (rel) | 1e-12 rel |
| spectrum-FWHM spec axes | 0 (no pulse inside the 1e-9 margin) | the margin asserted, then 1e-12 rel |

Every measured difference is at least two orders of magnitude inside its
tolerance; no comparison came close to its limit.

### 2.34 RF profile card (`test_rf_profile_card.py`)

`test_rf_profile_card.py` tests `cards/rf_profile.py` (`docs/plans/rf-profiles.md`,
section 4.5, items 1 and 2; task 5.3, items 1 to 7): `rf_table` (the RF table of a file,
its pools and its label check), `rf_profile_data` (one file entry, labeled or not) and
`rf_profile_card` (the options, the checks and the body). Each test builds its own
sequences with pypulseq, with the same helpers as `test_rf_profiles.py` (copied, not
imported). This card copies values from `rf_profiles` and `diagram_data`, so most checks
compare with `==` or `np.array_equal` (exact); a comparison that is not exact says why.

#### `test_rf_table_matches_hold_samples_and_definitions`

**Checks:** `rf_table`'s dtypes are those of its column table; after encoding and
decoding (`diagram_data.encode_tables`/`decode_tables`), each dense RF index's pool
slice equals `hold_samples` of the RF event as pypulseq rebuilds it, and `dt`, `delay`,
`shape_dur`, `center`, `use`, `freq_hz` and `phase_rad` equal their definitions;
`freq_hz` also equals `rf_profiles.block_pulse(seq, block).freq_offset_hz` at the first
block of the event.

**How:** A sinc excitation with a slice-select gradient and all four RF offsets
(`freq_offset`, `phase_offset`, `freq_ppm`, `phase_ppm`, on a system with `B0` set), a
sinc refocusing pulse, and a block pulse (`hold_samples` interpolates its shape). The
expected values are computed from `seq.get_block(...).rf`, the RF event as pypulseq
stores and rebuilds it, not the object given to `add_block`: the rebuilt samples can
differ from the given ones by float rounding. The rebuilt event is the same "rf" that
`rf_table` itself reads, so the comparison is exact.

**Assumptions:**

- `hold_samples` and `pp.calc_rf_center` are correct: `test_seq_utils.py` and pypulseq
  itself test them. This test checks how `rf_table` reads and encodes their results.

#### `test_rf_table_shares_one_shape_for_an_rf_spoiled_gre`

**Checks:** An RF-spoiled GRE gives more than one dense RF index, one shape in the pools
(every `shape_at` is 0, and `shape_re`/`shape_im` hold exactly one shape's samples), and
one `key` value, because the pulse key excludes the phase offset. The same GRE with two
slices (two frequency offsets) gives two `key` values and still one shape.

**How:** `_gre(24, rf_spoiling=True)` (a new phase offset each TR) and
`_gre(1, slices=(-5e-3, 5e-3))` (two frequency offsets, no spoiling).

**Assumptions:** None.

#### `test_rf_table_of_a_sequence_without_rf_is_empty`

**Checks:** A sequence without RF gives every `rf_table` column length 0.

**How:** A sequence with one trapezoid and one delay block, no RF.

**Assumptions:** None.

#### `test_rf_table_raises_without_labels`

**Checks:** `rf_table` raises `ValueError` (matching "rf_uses_labeled") when an RF event
has no use label, because `use` has no index for "undefined".

**How:** A block pulse added without a `use` argument (the pypulseq default,
"undefined").

**Assumptions:** None.

#### `test_pulse_list_and_file_entry_keys`

**Checks:** `rf_profile_data`'s `pulses` equals `dataclasses.asdict` of
`rf_profiles.pulse_list(seq)`, and its other keys (`slice_thickness_m`, `fov_m`, `b0_t`,
`gamma_hz_per_t`, `first_rf_block`) match their definitions, with and without an `FOV`
definition. The card body has one "Show" button for each pulse, with its `data-block`.

**How:** A sequence with an excitation and a refocusing pulse (sincs with gradients), a
block pulse, and a pulse with a turning gradient (`_turning_gradients`), and an `FOV`
definition; a second sequence without one.

**Assumptions:** None.

#### `test_options_appear_in_the_data_as_given_and_the_defaults`

**Checks:** `views`, `plane` and `extent_m` appear in the card data exactly as given;
without them, the data has `["profile"]`, `None` and `None`.

**How:** One card built with `views=("profile", "z_df", "2d")`, `plane=("x", "y")`,
`extent_m=0.2`, and one built with the defaults.

**Assumptions:** None.

#### `test_value_error_cases`

**Checks:** `rf_profile_card` raises `ValueError` for: empty `seqs`; two files with the
same name; `views` without `"profile"`; an unknown view; a view given twice; `plane`
with one name, with the same name twice, or with an axis that is not `x`, `y` or `z`;
`extent_m` of 0, −1, NaN or infinity; and a `diagram_card_id` that does not match
`[a-z][a-z0-9-]*` ("Diagram").

**How:** A parametrized test over the 13 cases, each with one sequence (or none, for the
empty case) and the one bad keyword argument.

**Assumptions:** None.

#### `test_rf_profile_card_refuses_rotations`

**Checks:** A sequence with the Pulseq rotation extension makes `rf_profile_card` raise
`NotImplementedError`, as the other gradient cards do.

**How:** A GRE sequence with a `rotation_library` attached by hand, the way pypulseq
draft PR #372 stores a rotation in memory (as `test_extensions.py` does).

**Assumptions:** None.

#### `test_two_cards_on_one_page_have_unique_ids`

**Checks:** Two RF profile cards on one page, with different `card_id`s and
`diagram_card_id`s but the same two files, give a page with no `id="..."` value used
twice.

**How:** `page.render_page` with two cards (`card_id` "rf-a"/"rf-b",
`diagram_card_id` "diag-a"/"diag-b"); every `id="..."` value in the result is found with
a regular expression and checked for duplicates.

**Assumptions:** None.

#### `test_unlabeled_file_gets_a_note_and_the_labeled_file_still_works`

**Checks:** A report with a labeled file and a file with one unlabeled RF event (and one
labeled event, so the counts are "1 of 2") raises nothing: the labeled file's data is its
full entry, and the other file's data is only its name and the counts. The body has the
note with the counts and the escaped file name; the raw (unescaped) name is not in the
body.

**How:** A file name with a character that `html.escape` changes (`"a<b"`).

**Assumptions:** None.

#### `test_primary_echo_note_matches_the_plan_text`

**Checks:** `PRIMARY_ECHO_NOTE` equals the text of section 4.3, item 7, of the plan
(without its title), written in the test as a literal so that a change of the constant
fails the test; and the card body's combined-profile element holds the title and the
note word for word.

**How:** The literal expected text is compared with the constant. In a one-file card's
body, the part from the start of the element `{card_id}-combined` to the element
`{card_id}-combined-body` (which the card script fills) must hold the `<strong>` title
and the escaped note.

**Assumptions:** None.

#### `test_sequence_without_rf_has_an_empty_entry_and_no_pulses_note`

**Checks:** A sequence without RF gives a file entry with `first_rf_block` None, an RF
table with length 0 in every column (after decoding), and an empty `pulses` list; the
card body says "No RF pulses." for that file.

**How:** A sequence with one trapezoid and one delay block, no RF.

**Assumptions:** None.

#### `test_page_has_the_card_script_and_the_elements_it_reads`

**Checks:** The card script (`assets/cards/rf-profile.js`) is DOM code, which the
library tests only in a browser check (decision 10 of `docs/plans/pulseq-reports.md`);
this test holds the Python half to what the script reads. On a page with a diagram card
and this card, for an RF-spoiled GRE, a file without use labels and a spin echo: the page
has the card script one time (`PulseqReport.registerCard("rf-profile"` and the text of
`page.card_asset("rf-profile")`); the card data names the diagram card; the body has the
status line with `aria-live="polite"`, the empty pulses element, and the combined
element, hidden, whose first paragraph is the primary echo note (the script hides that
paragraph above a period without a combined profile) and which holds the empty combined
body. The "Show" buttons are exactly one for each distinct pulse of each labeled file,
in order: `data-file` the file's index in the card's list (the unlabeled file, index 1,
has none) and `data-block` the pulse's first block.

**How:** `page.render_page` with `diagram_card` (a full window for each file) and
`rf_profile_card`; regular expressions on the body for the elements and the buttons,
compared with the card data's `pulses`.

**Assumptions:** None.

#### `test_usage_md_has_the_primary_echo_note_word_for_word`

**Checks:** `docs/usage.md` has `**{PRIMARY_ECHO_TITLE}** {PRIMARY_ECHO_NOTE}` word for
word (task 5.3, item 7: the card HTML, the card script and the documents use the one
text of the constants).

**How:** The test reads `docs/usage.md`, drops the `>` quote mark at the start of each
line, joins the lines with spaces and makes each run of white space one space, so that
the line breaks of the Markdown quote do not matter, then looks for the text.

**Assumptions:** `docs/usage.md` is in the repository at `docs/usage.md` from the tests
directory's parent.

### 2.35 RF profiles against external references (`test_rf_references.py`)

`test_rf_references.py` holds the Python reference of RF pulse profiles (`rf_profiles`,
`rf_sim`) to external references: phase 2b of `docs/plans/rf-profiles.md` (decision 5,
section 3.5, item 4). The fixtures in `tests/fixtures/rf_references/` (one JSON file
for each case, at most 200 KB) come from `scripts/rf_references.py`, which runs MATLAB
Pulseq's `mr.simRf` in GNU Octave (MATLAB Pulseq pinned to one commit in the
`rf-references` shell of `flake.nix`) and sigpy 0.1.27 (in its own locked environment,
`scripts/rf_references_sigpy.py`). Each fixture holds its provenance, the `.seq` file of
its case (gzip and base64) with the system values that a `.seq` file does not store
(B0, gamma, the rasters), a fingerprint of the pulse as `block_pulse` reads it, and the
reference outputs. The test needs neither Octave nor sigpy: it reads each `.seq` file
with pypulseq and computes the profiles with the reference functions. Each tolerance
is measured (2026-09-28), with its reason in the test.

#### `test_fixtures_have_provenance_and_are_small`

**Checks:** The fixture directory has exactly one JSON file for each case; each is at
most 200 KB (the plan's limit) and records its generator, the pypulseq version, the
MATLAB Pulseq commit and the Octave version (MATLAB cases), and the sigpy version
(sigpy cases).

**How:** Reads each fixture.

**Assumptions:** None.

#### `test_pulse_matches_the_fixture_fingerprint`

**Checks:** For each case, the pulse that `rf_profiles.block_pulse` reads from the
fixture's `.seq` file matches the fingerprint that the fixture recorded when the
references were computed: the number of samples, the gradient kind, `dt`, the sums of
the real and imaginary parts of the RF, its peak, and the sum and peak of each gradient
axis. So a failure of the other tests is a difference of the simulation, not of the
input; a failure here means that the reader, the hold rule or the interval gradients
changed, and the fixtures must be written again.

**How:** Parametrized over the 10 cases. `dt` with a relative 1e-12; each sum and peak
within 1e-12 times the sum of the magnitudes of its terms (the terms of a sinc or a
bipolar gradient cancel), which allows only float rounding of another numpy or pypulseq
version.

**Assumptions:** pypulseq reads the `.seq` file the same way as when the fixture was
written (the fingerprint checks it).

#### `test_simrf_of_its_resampled_rf`

**Checks:** `rf_sim.spin_domain`, on the RF that MATLAB Pulseq's `mr.simRf` simulates
(after its own resampling), gives `mr.simRf`'s Mz, |Mxy| and |refocusing efficiency|
(which equals |β|²) at its frequencies, within 1e-12. This checks the rotation itself
(quaternions in `mr.simRf`, Cayley-Klein parameters here), and that the frequency of
`mr.simRf` is the frequency offset `df` of this project, with the same sign.

**How:** Parametrized over the 7 MATLAB cases (sinc excitation, sinc refocusing, block
pulse, sinc with frequency and phase offsets, Gaussian fat saturation at −3.45 ppm,
hyperbolic secant, SLR). The fixture has the resampled RF (rad/s, one value for each
step of `mr.simRf`) and at most 601 points of its frequency axis. Measured: at most
1.2e-14.

**Assumptions:** The fixture's resampled RF is what `mr.simRf` simulates:
`scripts/rf_references_simrf.m` computes it with a copy of the lines of `simRf.m`
(the agreement to 1e-14 confirms the copy).

#### `test_simrf_of_the_pulse_as_played`

**Checks:** `rf_profiles.simulate` of the pulse as played (`block_pulse` of the same
`.seq` file: the hold samples with the offsets, and B0 of the fixture for a ppm offset),
on the frequency axis of `mr.simRf` at r = 0 (`mr.simRf` has no gradient), gives
`mr.simRf`'s Mz, |Mxy| and |β|² within the tolerance of the case.

**How:** Parametrized over the 7 MATLAB cases. The spec is a `df` axis over the
fixture's frequencies (the grid must match them within 1e-9 Hz; numpy's and MATLAB's
`linspace` differ by 7e-12 Hz at most). `mr.simRf` resamples the RF linearly to steps of
10 µs (5, 2 or 1 µs for a wide bandwidth), and the reference holds each 1 µs sample; the
test of the resampled RF shows that the rest agrees to float rounding, so the difference
here is the resampling. Tolerances (the measured maximum of the three quantities, times
3, rounded up): sinc excitation 2e-4 (6.3e-5), sinc refocusing 3e-4 (7.5e-5), sinc with
offsets 8e-4 (2.4e-4), fat saturation 3e-4 (7.0e-5), hyperbolic secant 2e-4 (5.2e-5);
1e-12 for the block pulse (1.8e-14: linear resampling does not change a constant pulse)
and for the SLR pulse (4.2e-14: each design sample is held 10 µs, and `mr.simRf` takes
one 10 µs step at the centre of each). A wrong frequency sign gave 0.99, and a ppm
offset with the wrong B0 gave 0.76.

**Assumptions:** None.

#### `test_abrm_nd`

**Checks:** `rf_profiles.simulate` of the pulse (its hold samples and interval
gradients) at the points of the fixture's grid gives the `a` and `b` of sigpy's
`abrm_nd`, within 1e-12: a sinc with its slice-select gradient (201 points on z), a sinc
across the ramps of its gradient (201 points on z), a sinc with an oblique gradient
(31 × 31 points on x-y), and a pulse whose gradient direction turns twice (31 × 31 points
on x-y, kind "changing").

**How:** Parametrized over the 4 sigpy cases. sigpy gets the reference's own hold
samples and interval gradients (times 2π dt) and the points that `simulate` builds, so
this checks the rotation in 1D and 2D, not the interval gradients (the analytic tests of
`test_rf_profiles.py` check those). `abrm_nd` uses the same Cayley-Klein formulas with
the operations in another order. Measured: at most 1.6e-13 (3000 samples).

**Assumptions:** None.

#### `test_slr_profile_equals_sigpy_abrm_of_the_design`

**Checks:** An SLR 90° excitation designed by sigpy (`dzrf`: 256 samples,
time-bandwidth product 4, ptype "ex", ftype "ls", d1 = d2 = 0.01), each design sample
held 10 µs on the 1 µs RF raster: `rf_profiles.simulate` on 601 frequencies (±3 kHz)
gives the `a` and `b` of sigpy's own 1D simulator of SLR design (`abrm`) at x = f ×
duration (cycles per pulse), within 1e-12. First, one sample of each held group of the
pulse read from the `.seq` file equals the stored design of the fixture, within 1e-12.

**How:** `abrm` gets the design as the `.seq` file stores it: pypulseq writes RF shapes
with about 7 significant digits, which moves the design by 7.5e-7 of its peak (the
fixture records it), and moves `a` and `b` by 4.6e-7. Measured: at most 1.8e-14. The
design ripples are not a check: they are not a bound for a 90° "ls" design, and sigpy's
own simulation of its design exceeds them (passband 1.5e-2, stopband 5.2e-2, against
0.01; decision 24 of the plan).

**Assumptions:** None.

#### `test_hyperbolic_secant_inverts_its_analytic_band`

**Checks:** pypulseq's default hyperbolic secant inversion (`make_adiabatic_pulse`
"hypsec": beta 800 rad/s, mu 4.9, 10 ms, adiabaticity 4, so w1_max = 2 sqrt(mu) beta)
gives Mz ≤ −0.9 (the plan's bound) at each frequency where the analytic Mz of the
untruncated pulse is at most −0.99 (|f| ≤ 405 Hz of the ±624 Hz sweep).

**How:** 601 frequencies over ±1.5 kHz. The analytic Mz is the Silver, Joseph and Hoult
solution (Phys. Rev. A 31, 2753, 1985), as Eq. [23] of Zhang, Garwood and Park (Magn.
Reson. Med. 77, 1630, 2017), written out in the test. Measured: Mz ≤ −0.9926 in the
band. The pulse is truncated at beta t = ±4, which moves its profile from the analytic
one by up to 0.12 near the band edges, so the band is where the analytic inversion is
deep.

**Assumptions:** None.

#### `test_hyperbolic_secant_approaches_the_analytic_profile`

**Checks:** The same hyperbolic secant, longer (20 and 30 ms, so that sech(beta t) is
truncated at 6.7e-4 and 1.2e-5), gives the analytic Mz at every frequency within 1e-2
and 2e-4.

**How:** Measured max |Mz − analytic|: 0.125 at 10 ms, 3.0e-3 at 20 ms, 5.9e-5 at
30 ms. The difference is the truncation (the analytic solution is for an untruncated
pulse), and it falls with it; the tolerances are the measured values times 3, rounded
up. The two simulations take about 1.3 s.

**Assumptions:** None.
