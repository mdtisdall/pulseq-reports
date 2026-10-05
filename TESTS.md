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
2. [Tests](#2-tests): the sequence extensions; the HTML and lane markup, the
   report page, the chart math and the messages between cards; the analyses
   (RF exposure, the gradient spectrum, the RF simulation, the profile
   metrics and the RF profiles); the
   waveform data, the diagram tables and the lane modules in JavaScript (the
   sequence lanes, the PNS lane and the |G| lane), with their golden tests
   against Python; the report cards; the card registry, the command line,
   the package exports, the rasters of the file and the report targets

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
the pattern matches no file, the step fails.

**Assumptions:**

- The tests run the modules that do not use the DOM: `chart_math.js`,
  `seq_lanes.js`, `pns_lanes.js`, `g_lanes.js`, `rf_profiles.js`, and the
  message bus of `lane_chart.js`. The drawing code of `lane_chart.js` and
  `map_chart.js`, `page.js`, and the card scripts in `assets/cards/` are not
  run by any test: there are no DOM tests. The charts are checked by hand in
  a browser before a pull request.
- The Node.js version is the one from the Nix devShell. No other version is
  tested.

---

## 2. Tests

### 2.2 HTML and lane markup (`test_markup.py`)

`test_markup.py` tests the public helpers of `markup.py`, which project
cards use too (`docs/usage.md`, section 4): the zoom button group placed
above each line chart, the HTML table with escaped cell values, the number
format of the library's tables, the JSON of a list of lanes, and the hidden
"Show" button of a block.

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

#### `test_show_button_has_the_play_index_of_the_block_hidden_and_an_escaped_label`

**Checks:** `show_button_html` gives a `<button>` whose `data-block` is the play index of
the block (its position in `index.block_id`, from 0), not the block id; the button has the
attribute `hidden`; and the label is HTML-escaped.

**How:** The test makes the `sequence_index` of the synthetic spin echo sequence and checks
that its block ids are 1 to 6, so that no block id equals its play index. For each block, it
calls `show_button_html` with the block id and the label `Show <b>`. It checks that the result
starts with `<button`, has `data-block` with the play index, has `hidden`, ends with the
escaped label and the closing tag, and has no raw `<b>`.

**Assumptions:** pypulseq numbers the blocks from 1; the test checks this.

#### `test_show_button_raises_for_a_block_that_the_sequence_does_not_have`

**Checks:** `show_button_html` raises `ValueError` for a block id that is not in the
sequence.

**How:** The same index as above. The test calls `show_button_html` with the id 0 and with
the id after the last block, and checks that each call raises `ValueError` with the id in the
message.

**Assumptions:** None.

#### `test_target_legend_is_empty_for_no_targets`

**Checks:** `target_legend_html` gives `""` for no targets.

**How:** One call with an empty list and one with an empty tuple.

**Assumptions:** None.

#### `test_target_legend_lists_the_targets_in_order_with_their_colors`

**Checks:** The legend is a `<ul>` with one `<li>` for each target, in the order of the
targets; the name of each target and its color `var(--target-k)` are in its item, and no
other color is in the legend.

**How:** Three profiles from the `make_profile` fixture, through `report_targets`. The test
checks the `<li>` count, that the names and the `var(--target-k)` texts for k from 1 to 3 are
in increasing positions, and that each item has its own name and color.

**Assumptions:** None.

#### `test_target_legend_escapes_the_name`

**Checks:** The name of a target is HTML-escaped in the legend.

**How:** A profile renamed with `dataclasses.replace` to a name with `<b>`, `&`, `"` and `'`.
The escaped name is in the legend, and `<b>` is not.

**Assumptions:** None.

#### `test_target_legend_lists_a_target_with_another_gamma_like_any_other`

**Checks:** A target with a gamma that is not the proton gamma is in the legend as the others
are: its item has its color and its name, and nothing else.

**How:** Two profiles, the second with the sodium gamma. The test splits the legend at `<li>`
and checks the color token and the text after the swatch of each item.

**Assumptions:** None.

#### `test_gamma_select_is_empty_for_fewer_than_two_entries`

**Checks:** `gamma_select_html` gives `""` for no entry and for one entry.

**How:** A list of zero and a list of one `GammaEntry`.

**Assumptions:** None.

#### `test_gamma_select_has_a_button_for_each_entry_in_order`

**Checks:** For two entries, the control has two buttons in the order of the entries, with
`data-gamma-choice` "0" and "1", `data-gamma` equal to the gamma of each entry (also a negative
one), and `aria-pressed` "true" for the first and "false" for the second. The label of a
button has the names of its entry.

**How:** Two entries (`42.576e6` with two names, `-11.777e6` with the name `<x>`), parsed with
`html.parser`.

**Assumptions:** None.

#### `test_gamma_select_escapes_the_names_and_the_card_id`

**Checks:** The names of the entries and the card id are HTML-escaped.

**How:** An entry with the name `<b>&` and the card id `a"<i>`; `<b>` and `<i>` are not in the
output, and the escaped name is.

**Assumptions:** None.

### 2.3 The report page (`test_page.py`)

`test_page.py` tests `page.py`. `render_page` builds the report page's HTML
from a list of `Card` objects, in order: each card's title is escaped, its
JSON data (if any) is placed in a `<script type="application/json">`
element, and the scripts and CSS texts of the cards (`Card.scripts`,
`Card.css`) are included once each, even when more than one card has the
same text. The tests also cover card and script id validation, the topic
check (`TOPIC_KINDS`), the project CSS
(`extra_css`), the library CSS, the `__NAME__` placeholder substitution,
`card_asset`, and `write_page`.

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

#### `test_card_scripts_and_css_are_on_the_page_once_in_order_of_first_use`

**Checks:** `render_page` includes each distinct text of the cards'
`scripts` and `css` one time, in the order of first use. The scripts come
after the library scripts and before `extra_scripts`; the CSS comes before
`extra_css`.

**How:** The test builds two cards. The second repeats one script and one CSS
text of the first, and adds one new script and one new CSS text. Each text is a
comment with a marker. The test renders the page with one extra script and one
`extra_css` text. It checks that each card marker appears exactly once, that
the script markers are in the order of first use and then the extra script's
marker, after the last library script (`g_lanes.js`) and before `page.js`, and
that the CSS markers are in the order of first use and then the `extra_css`
marker.

**Assumptions:** None.

#### `test_card_css_with_close_tag_raises`

**Checks:** `render_page` raises `ValueError` when the `css` of a card
contains `</style`, because the tag would end the page's `<style>` element.

**How:** The test builds a card whose `css` text contains `</style>` and
checks that `render_page` raises `ValueError`.

**Assumptions:** None.

#### `test_script_order`

**Checks:** The page's scripts appear in this order: `chart_math.js`,
`lane_chart.js`, `map_chart.js`, `rf_profiles.js`, `seq_lanes.js`, `pns_lanes.js`,
`g_lanes.js`, each card's `scripts`, the extra scripts in the given order, and
`page.js`.

**How:** The test builds one card with one script text and two extra
scripts, calls `render_page`, and checks that the string indices of a
`chart_math.js` marker, a `lane_chart.js` (`PulseqReport`) marker, a
`map_chart.js` (`PulseqReport.mapChart = mapChart;`) marker, an `rf_profiles.js`
(`RfProfiles`) marker, a `seq_lanes.js` (`SeqLanes`) marker, a `pns_lanes.js` (`PnsLanes`) marker, a `g_lanes.js`
(`GLanes`) marker, the card script's marker, each extra script's marker, and a
`page.js` marker are in increasing order.

**Assumptions:** None.

---

#### `test_two_publishers_of_a_state_topic_raise`

**Checks:** `render_page` raises `ValueError`, with the topic and the two
card ids in the message, when two cards publish one state topic (`sequence`).

**How:** The test builds two cards that both publish `sequence` and checks
that `render_page` raises `ValueError` and that the message has `sequence`
and both card ids.

**Assumptions:** None.

#### `test_two_subscribers_of_a_request_topic_raise`

**Checks:** `render_page` raises `ValueError`, with the topic and the two
card ids in the message, when two cards subscribe to one request topic
(`goto`).

**How:** The test builds two cards that both subscribe to `goto` and checks
that `render_page` raises `ValueError` and that the message has `goto` and
both card ids.

**Assumptions:** None.

#### `test_topics_that_pass_the_check`

**Checks:** `render_page` does not raise for one publisher of a state topic
with many subscribers, one subscriber of a request topic with many
publishers, and any number of publishers and subscribers of a topic that is
not in `TOPIC_KINDS`.

**How:** The test builds three cards with those topics and checks that
`render_page` does not raise.

**Assumptions:** None.

#### `test_the_error_of_a_card_is_not_on_the_page`

**Checks:** `render_page` does not show `Card.error`.

**How:** The test renders a card with `error` set to a marker text. It checks that the marker is
not in the page, and that the page equals the page of the same card without `error`.

**Assumptions:** None.

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
two ends of a drag into a view. `valueDomain` gives the domain, ticks and tick labels of a value
lane of the diagram for a peak, and `rescaleLane` changes such a lane from the units of the file
(Hz/m, Hz) into the units of the chart (mT/m, µT) for the gamma of the selected target
(`docs/plans/pulseq-checks-implementation.md`, section 4.7b). `laneGroupMap` turns a `laneChart` `groups`
option into a Map from lane id to group id, and `visibleLanes` filters a
list of lanes down to those of a visible group (`lane_chart.js`'s
lane-group support, `docs/plans/diagram-lanes.md` section 4.5 item 3). `colorRamp` builds an n-color ramp linear between a list of
stops, `colorIndex` finds the index of a value in such a ramp over a domain,
and `nearestIndex` finds the nearest grid index on a uniform axis: the map
chart (`assets/map_chart.js`, `docs/plans/rf-profiles.md` section 4.4) uses
them to color its raster and to snap its cursor to the grid.
`tooltipRows` gives the rows of a lane's tooltip at a time (one row for a
lane, or one for each of its `series`), `normalizeBand` turns an entry of the
`bands` option (`[lo, hi]` or `{lo, hi, color}`) into one form, and
`markSpans` turns a lane's `marks` into the few rectangles to draw for a view
(`docs/plans/pulseq-checks-implementation.md` section 4.4). The
report page (`page.py`) puts
`chart_math.js` and `lane_chart.js` first among its scripts, each in its own
`<script>` element, before any card scripts, the extra scripts and
`page.js`. `lane_chart.js` has `PulseqReport.laneChart`, which calls these
functions to draw the charts, and calls `clampView`, `zoomView`, `panView`
and `dragView` for the zoom and pan controls on a chart. Its `render`
function calls `visiblePoints` once for each line segment, with the current
view and a bucket count of 2 times the plot width in viewBox units (812), so
a zoomed-out chart with many points does not draw more points than the chart
can show. Its tooltip (`setCursor`) builds one row for each row of
`tooltipRows`, which calls `valueAt` for a lane without the key
`minmax: true`, and `minMaxAt` for a lane with that key (except a gate lane,
which is always read with `valueAt`). Its
`render` function calls `markSpans` (with a minimum width of 1 viewBox unit)
for the `marks` of a lane, and `normalizeBand` for each entry of `bands`.

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

#### `test_tooltip_rows_plain_line_lane_has_one_row_with_title_color_and_unit`

**Checks:** `tooltipRows` gives one row for a lane without `series`, with the title of the lane as its label, the color of the lane, and the value at the time with the unit of the lane.

**How:** The test makes a line lane (title "Gx", color "gx", unit "mT/m", fill 0) with one segment from (0, 0) to (10, 100). At t = 5 the result must be the one row `{label: "Gx", color: "gx", text: "50 mT/m"}`. At t = 20, outside the segment, the text must be the fill, "0 mT/m".

**Assumptions:** None beyond the file's assumptions.

#### `test_tooltip_rows_null_fill_has_no_unit`

**Checks:** `tooltipRows` gives an em dash with no unit for a value that is null (a lane with a null fill, outside its segments).

**How:** The test makes a lane with a unit and a null fill, and reads it outside its only segment. The text must be "—" alone.

**Assumptions:** None beyond the file's assumptions.

#### `test_tooltip_rows_minmax_lane_reads_the_bin_and_falls_back_to_fill_in_a_gap`

**Checks:** `tooltipRows` gives the minimum and the maximum of the bin at the time for a lane with `minmax: true`, with the unit, and the fill in a gap between bins.

**How:** The test makes a minmax lane (unit "mT/m", fill 0) with two segments of one bin each: (0, -1) and (5, 2), and (20, -3) and (25, 4). At t = 3 and t = 22 the texts must be "−1 – 2 mT/m" and "−3 – 4 mT/m". At t = 15, in the gap, the text must be "0 mT/m".

**Assumptions:** None beyond the file's assumptions.

#### `test_tooltip_rows_minmax_lane_without_unit_has_no_unit_text`

**Checks:** `tooltipRows` leaves the unit out of the text of a minmax lane that has none, and gives an em dash for a null fill in a gap.

**How:** The test makes a minmax lane with no unit and a null fill, and one bin: (0, -1) and (5, 2). At t = 3 the text must be "−1 – 2". At t = 50 it must be "—".

**Assumptions:** None beyond the file's assumptions.

#### `test_tooltip_rows_gate_lane_is_on_or_off_even_with_minmax`

**Checks:** `tooltipRows` reads a gate lane with `valueAt` ("on" or "off"), even when the lane also has `minmax: true` and a unit.

**How:** The test makes a gate lane with one window, [2, 5], the key `minmax: true` and a unit. At t = 3 the text must be "on" and at t = 7 it must be "off". The label and the color are those of the lane.

**Assumptions:** None beyond the file's assumptions.

#### `test_tooltip_rows_series_has_one_row_per_series_read_from_its_own_segments`

**Checks:** `tooltipRows` gives one row for each series, in order, with the label and color of the series, and the value read from the segments of that series, with the unit and the fill of the lane.

**How:** The test makes a lane (unit "%", fill 0) with two series: the first has one segment from (0, 0) to (10, 100), the second has the segments (0, 10) to (10, 20) and (20, 5) to (30, 7). At t = 5 the texts must be "50 %" and "15 %". At t = 25 they must be "0 %" (outside the first series) and "6 %". At t = 15, outside both, both must be the fill, "0 %".

**Assumptions:** None beyond the file's assumptions.

#### `test_tooltip_rows_series_of_a_minmax_lane_read_the_bin_of_each_series`

**Checks:** `tooltipRows` reads the minimum and the maximum of the bin from the segments of each series for a lane with `minmax: true` and series, and gives the fill of the lane where a series has no bin.

**How:** The test makes a minmax lane (unit "mT/m", fill 0) with two series, each with one bin: (0, -1) and (5, 2), and (0, -4) and (5, 6). At t = 3 the texts must be "−1 – 2 mT/m" and "−4 – 6 mT/m". At t = 50 both must be "0 mT/m".

**Assumptions:** None beyond the file's assumptions.

#### `test_tooltip_rows_empty_series_array_has_no_rows`

**Checks:** `tooltipRows` gives no rows for a lane whose `series` is an empty array, even when the lane has segments of its own.

**How:** The test makes a lane with `series: []` and a segment, and checks that the result is an empty array.

**Assumptions:** None beyond the file's assumptions.

#### `test_normalize_band_pair_has_no_color_and_object_keeps_its_color`

**Checks:** `normalizeBand` turns a pair `[lo, hi]` into `{lo, hi, color: null}`, and an object into the same fields with its own color (null when it has none).

**How:** The test calls `normalizeBand` with `[1, 2]`, with `{lo: 3, hi: 4, color: "target-2"}` and with `{lo: 3, hi: 4}`, and compares each result with the expected object.

**Assumptions:** None beyond the file's assumptions.

#### `test_mark_spans_maps_to_plot_coordinates`

**Checks:** `markSpans` maps a mark in chart units to plot coordinates (0 at the start of the view, `width` at its end).

**How:** The test calls `markSpans` for the view [100, 200] and a plot width of 1000 (10 plot units for each chart unit) with the mark [120, 150]. The result must be one span from 200 to 500 with the color of the mark.

**Assumptions:** None beyond the file's assumptions.

#### `test_mark_spans_drops_marks_fully_outside_the_view`

**Checks:** `markSpans` drops a mark that lies fully before or fully after the view.

**How:** The test gives three marks for the view [100, 200]: [0, 50], [250, 300] and [120, 130]. Only the third must be in the result, as the span 200 to 300.

**Assumptions:** None beyond the file's assumptions.

#### `test_mark_spans_cuts_a_mark_partly_in_view_at_the_edge`

**Checks:** `markSpans` cuts a mark that is partly in the view at the edge of the plot.

**How:** The test gives the marks [50, 120] and [180, 400] for the view [100, 200] and a plot width of 1000. The spans must be 0 to 200 and 800 to 1000.

**Assumptions:** None beyond the file's assumptions.

#### `test_mark_spans_widens_a_narrow_mark_about_its_centre`

**Checks:** `markSpans` widens a mark that is narrower than `minWidth` to `minWidth` about its centre, and leaves a wider mark as it is.

**How:** The test gives the mark [150, 150.01] (0.1 plot units wide) with a minimum width of 2. The span must be 2 wide about the centre of the mark, 499.05 to 501.05 (with a tolerance of 1e-9). A mark [150, 150.2] (2 plot units wide) must stay 500 to 502.

**Assumptions:** None beyond the file's assumptions.

#### `test_mark_spans_widened_mark_at_the_edge_is_cut_at_the_edge`

**Checks:** `markSpans` cuts a widened mark at the edge of the plot, so it does not go outside [0, width].

**How:** The test gives a mark of zero width at the start of the view (100) and one at the end (200), for the view [100, 200], a plot width of 1000 and a minimum width of 2. The spans must be 0 to 1 and 999 to 1000.

**Assumptions:** None beyond the file's assumptions.

#### `test_mark_spans_merges_overlapping_and_touching_marks_of_the_same_color`

**Checks:** `markSpans` merges marks of one color that overlap or touch into one span, and keeps the gaps between them.

**How:** The test gives five marks of one color for the view [100, 200] and a plot width of 1000: [110, 120], [115, 130], [130, 135] (it touches the second), [150, 160] and [112, 113] (it lies inside the first). The spans must be 100 to 350 and 500 to 600.

**Assumptions:** None beyond the file's assumptions.

#### `test_mark_spans_merges_marks_that_overlap_only_after_widening`

**Checks:** `markSpans` merges two marks that do not overlap as they are, but overlap after the widening to `minWidth`.

**How:** The test gives two marks of zero width, at 150 and 150.05 (500 and 500.5 in plot units), for a minimum width of 2. After the widening they are 499 to 501 and 499.5 to 501.5, so the result must be one span from 499 to 501.5 (with a tolerance of 1e-9).

**Assumptions:** None beyond the file's assumptions.

#### `test_mark_spans_does_not_merge_marks_of_different_colors`

**Checks:** `markSpans` does not merge marks of different colors, even when they overlap.

**How:** The test gives the marks [110, 130] and [125, 135] of color "a" and [120, 140] of color "b" for the view [100, 200] and a plot width of 1000. The result must be the color "a" span 100 to 350 and then the color "b" span 200 to 400 (the colors in the order of their first mark).

**Assumptions:** None beyond the file's assumptions.

#### `test_mark_spans_does_not_need_sorted_input`

**Checks:** `markSpans` gives the same spans for marks in any order, and each color's spans in increasing x0.

**How:** The test gives four marks of one color, in order and in a shuffled order. The two results must be equal, and equal to the spans 100 to 300, 500 to 600 and 700 to 800.

**Assumptions:** None beyond the file's assumptions.

#### `test_mark_spans_empty_input_gives_no_spans`

**Checks:** `markSpans` gives an empty list for an empty list of marks.

**How:** The test calls `markSpans` with `[]` and checks that the result is an empty array.

**Assumptions:** None beyond the file's assumptions.

#### `test_value_domain_is_the_rule_of_the_python_value_lane`

**Checks:** `valueDomain(peak, symmetric)` gives the domain, the ticks and the tick labels that
`waveforms._value_domain(peak, symmetric)` gave when Python calculated them (before the diagram
data kept the units of the file): a peak of 0 gives `[-1, 1]` with one tick; a symmetric lane
gives `±1.1 * peak` with the ticks `-peak`, 0 and `peak`; another lane gives `[0, 1.1 * peak]`
with the ticks 0 and `peak`. A label has 3 significant digits as Python's `f"{v:.3g}"` writes
them: a tie goes to the even digit (12.25 gives "12.2", 1.125 gives "1.12"), an exponent
("1.23e+03", "1e+03") appears from 1e3 and below 1e-4, and every hyphen, also the one of an
exponent, is U+2212.

**How:** A table of 16 rows (peaks from 1.234e-5 to 1234.5, both values of `symmetric`), each
row the printed result of the Python function of the version before this change, compared with
`assert.deepEqual`.

**Assumptions:** The rows are copied from a run of that Python function, not derived again; they
cover the cases where `toPrecision` of JavaScript differs from `.3g` of Python.

#### `test_rescale_lane_gives_the_values_and_the_axis_of_the_gamma`

**Checks:** `rescaleLane(lane, gamma)` of a gradient lane in Hz/m (unit "mT/m", `symmetric`)
gives each value as `v / gamma * 1e3`, and the `domain`, `ticks` and `tick_labels` of
`valueDomain` for its `peak` in mT/m: 1064400 Hz/m is 25 mT/m for the proton gamma, and a gamma
of half the size doubles the values and the axis. The lane that was given is not changed.

**How:** A hand-made lane with four points and `peak` 1064400. The segments are compared with
the same arithmetic, the axis with `valueDomain(25, true)` and `valueDomain(50, true)`.

**Assumptions:** None beyond the file's assumptions.

#### `test_rescale_lane_with_a_negative_gamma_changes_the_sign_of_a_signed_lane_only`

**Checks:** For a negative gamma, the values of a signed (`symmetric`) gradient lane are the
negatives of those for its magnitude, with the same domain, ticks and labels (the peak is a
magnitude). The RF magnitude lane (unit "µT", values in Hz) and a magnitude of the gradient
(`symmetric: false`, unit "mT/m", with an axis of its own and no `peak`) are equal for a gamma
and its negative, and the second keeps its own axis.

**How:** `rescaleLane` of a gradient lane, an RF lane and a magnitude lane with `GAMMA_1H` and
`-GAMMA_1H`. The zero values are compared after `+ 0`, which turns -0 into 0.

**Assumptions:** None beyond the file's assumptions.

#### `test_rescale_lane_keeps_the_minimum_before_the_maximum_of_a_minmax_lane`

**Checks:** In a `minmax` lane, a pair is (bin start, minimum) and (bin centre, maximum). For a
negative gamma the minimum becomes the maximum, so `rescaleLane` sorts each pair again: the
result of the negative gamma has the negative of the maximum first.

**How:** A lane with two pairs; the result for `-GAMMA_1H` is compared with the result for
`GAMMA_1H` (swapped and negated), and each pair is checked to be in order.

**Assumptions:** None beyond the file's assumptions.

#### `test_rescale_lane_returns_a_lane_without_symmetric_as_it_is`

**Checks:** A lane without a boolean `symmetric` (the RF phase, the ADC gate) is returned as
the same object, for any gamma.

**How:** `rescaleLane` of a phase lane and a gate lane, compared with `assert.equal`.

**Assumptions:** None beyond the file's assumptions.

#### `test_rescale_lane_refuses_a_gamma_that_is_0_or_not_finite_and_an_unknown_unit`

**Checks:** `rescaleLane` throws for a gamma of 0, NaN, Infinity or undefined (with "gamma" in
the message), and for a unit that is not "mT/m" or "µT".

**How:** `assert.throws` with a pattern for each bad value.

**Assumptions:** None beyond the file's assumptions.

#### `test_rescale_lane_rounds_the_peak_to_4_decimals_with_the_tie_to_the_even_digit`

**Checks:** The peak in the unit of the chart is rounded to 4 decimals as Python's `round`
rounds (as the peak of a lane was rounded when Python calculated the domain): 0.03125 mT/m gives
the ticks ±0.0312, where `toFixed(4)` would give 0.0313.

**How:** A lane with a peak of 1 Hz/m and a gamma of 32000 Hz/T, which is exactly 0.03125 mT/m;
the segment value is checked to be exactly 0.03125, and the ticks and the domain to be those of
0.0312.

**Assumptions:** The division and the multiplication of this peak are exact in floating point
(the test checks the value of the segment).

---

### 2.5 Timing card (`test_timing_card.py`)

`test_timing_card.py` tests `cards/timing.py`. `timing_card` builds the
timing check card from pypulseq's `check_timing` result for one sequence.
The body is the same HTML as vb-pulseq's timing check.

#### `test_timing_card_for_one_sequence_matches_timing_html`

**Checks:** `timing_card`'s `body_html` equals the same
HTML as vb-pulseq's timing check (parity), and the card's `id`, `title`,
`data` and `script` fields are correct.

**How:** The test builds a synthetic spin echo sequence (it passes the
timing check), calls `timing_card` with it, and compares
`body_html` to `timing._timing_html(timing._timing_errors(seq))` called
directly. It also checks `id == "timing"`, `title == "Timing check"`,
and that `data` and `script` are both None.

**Assumptions:** The synthetic spin echo sequence passes pypulseq's timing
check.

#### `test_timing_card_of_a_sequence_without_timing_errors_has_no_error_table`

**Checks:** For a sequence without timing errors, the number of errors in the body is 0
and the body has no error table.

**How:** The test builds the card for the synthetic spin echo sequence, reads the number
in the sentence "pypulseq's timing check gave N errors" with a regular expression, and
checks that it is 0 and that the body has no `<table`.

**Assumptions:** The synthetic spin echo sequence passes pypulseq's timing check.

#### `test_timing_card_lists_timing_errors_for_one_sequence`

**Checks:** For a sequence with a timing violation, the number of errors in the body is
the number of errors that `_timing_errors` gives (at least 1), the error table has one
row for each error, and the body names the error type.

**How:** The test builds a sequence with one RF block whose delay is set to
0 after construction, below the RF dead time (as in vb-pulseq's own
bad-sequence test), confirms that `_timing_errors` reports an `RF_DEAD_TIME`
error, then reads the number of errors in the body's sentence and compares it
with the length of `_timing_errors`. It counts the `<tr>` elements of the body, which must be
the header row and one row for each error, and checks that "RF_DEAD_TIME" is in the body.

**Assumptions:** pypulseq's `check_timing` reports an `RF_DEAD_TIME` error
for an RF block whose delay is below the system's RF dead time.

#### `test_timing_card_has_no_verdict`

**Checks:** The card gives no verdict: its body has no `status good` and no `status bad`
class, for a sequence without timing errors and for a sequence with one.

**How:** The test builds the card for the synthetic spin echo sequence and for the
RF dead time sequence of the test above, and checks that neither body has the text
`status good` or `status bad`.

**Assumptions:** `status good` and `status bad` are the classes (`assets/report.css`) that the
timing card used for its verdict before it had none.

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
the same as vb-pulseq.

#### `test_definitions_card_for_one_sequence_matches_the_vb_table`

**Checks:** `definitions_card`'s `body_html` equals
vb-pulseq's two-column definitions table for the same sequence (parity),
and the card's `id`, `title`, `data` and `script` fields are correct.

**How:** The test builds a synthetic GRE sequence (it has definitions,
including "TR"), computes the same table directly with `markup.html_table` from
`seq.definitions.items()`, and compares it to `definitions_card`'s
`body_html`. It also checks `id == "definitions"`, `title == "Definitions"`,
and `data` and `script` are both None.

**Assumptions:** None.

#### `test_definitions_card_for_one_sequence_with_no_definitions_is_an_empty_table`

**Checks:** A sequence with no definitions gets the two-column table with
an empty body.

**How:** The test clears `seq.definitions` on a synthetic spin echo
sequence and checks that the body equals
`markup.html_table(["Definition", "Value"], [])`.

**Assumptions:** pypulseq's `Sequence.definitions` is a plain dict that a
test can clear directly.

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

#### `test_a_negative_gamma_gives_the_values_of_its_magnitude`

**Checks:** `rf_exposure(seq, -gamma)` equals `rf_exposure(seq, gamma)`, field by field: the
peak B1, the energy and the B1+rms use the magnitude of the gamma.

**How:** A two-pulse train; the two `RfExposure` objects are compared with `==`.

**Assumptions:** None.

#### `test_the_values_follow_the_magnitude_of_the_gamma`

**Checks:** B1 is the amplitude in Hz divided by the magnitude of the gamma: a gamma of half the
size (and negative) doubles the peak B1, the B1+rms and the highest-window B1+rms, and gives 4
times the energy.

**How:** A two-pulse train; `rf_exposure` with `GAMMA_1H` and with `-GAMMA_1H / 2`, compared with
`pytest.approx` at a relative 1e-12.

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
`peak_block`, `b1rms_window_s` (the oracle's `window_s`) and `b1rms_window_used_s` (the
oracle's `window_used_s`) exactly, and `duration_s`, `peak_b1_ut`,
`energy_ut2_s`, `b1rms_ut` and `b1rms_window_ut` within a relative 1e-12
(`_assert_matches_oracle`).

**Assumptions:**

- The new code sums the energy once for each unique RF event and once for each pulse in
  play order, not over every sample in play order like the oracle, so the summed float
  fields can differ from the oracle's by float rounding (section 3.5, item 2 of the
  plan). `num_pulses`, `peak_block`, `b1rms_window_s` and `b1rms_window_used_s` do not depend on a
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
`b1rms_window_used_s` and `b1rms_window_ut` equal the oracle's exactly (`==`).

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

`test_rf_exposure_card.py` tests `cards/rf_exposure.py`. `_rf_exposure_data`
gives `rf_exposure.rf_exposure` as a JSON-ready dict, in ms and µT, plus the
highest window's real length and whether the sequence is periodic.
`rf_exposure_card` builds the "RF exposure" `Card`: for one sequence, the
body is a six-row table and its note, for the magnitude of each gamma of
`units.gamma_entries(targets, seq, signed=False)` (one table for each entry, and the control of
the gamma with the card script `gamma-select` when there are two or more entries). The card
takes one sequence.

The tests use `tests/synthetic.py`'s `spin_echo_sequence` and
`empty_sequence`.

**Assumptions for the whole file:**

- The card has no chart: its `data` is `None`, and its `script` is `None` unless the card has
  the gamma control.

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

**How:** The test builds the card for the spin echo sequence, checks that its
`data` and `script` are `None`, renders the page, cuts out the text from the
card's id to the end of the result, and checks for the title "RF exposure"
and the rows "RF pulses", "Peak B1 (µT)", "∫B1² dt over the sequence
(µT²·ms)", "Sequence duration (ms)", "B1+rms, sequence repeated (µT)" and
"B1+rms, highest 10 s window (µT)". This also checks that `render_page`
accepts the card.

**Assumptions:** None.

#### `test_a_negative_gamma_gives_the_table_of_its_magnitude`

**Checks:** Two targets with the gamma of the sequence and its negative are one entry (the
magnitude), so the card is the card without targets: the same body, no control, no card script.

**How:** `rf_exposure_card` with `report_targets` of two profiles (`gamma = GAMMA_1H` and
`-GAMMA_1H`), compared with the card of the same sequence without targets.

**Assumptions:** None.

#### `test_targets_with_other_magnitudes_of_gamma_give_one_table_for_each`

**Checks:** Targets with two magnitudes of gamma (the default, a negative 11.777 MHz/T and the
default again) give two tables, in the order of the first target of each magnitude, in
`data-gamma-entry` blocks (the second `hidden`), two control buttons and the card script
`gamma-select`; each table has the peak B1 of the refocusing pulse for its magnitude.

**How:** The card for three profiles; the position of the two blocks in `body_html` is read, and
the cell of the peak B1 of each block is compared with the value that the test calculates from
the flip angle, the duration and the gamma.

**Assumptions:** The peak B1 shows in the table as `f"{peak:.2f} (block ...)"`.

#### `test_rf_exposure_card_without_rf`

**Checks:** For a sequence without RF, the card's body is the "No RF
pulses." note, on its own and inside a rendered page.

**How:** The test builds the card for the synthetic sequence with only a
delay block, checks that the body equals the note exactly, and that the note
is in a rendered page.

**Assumptions:** None.

### 2.10 Gradient spectrum card (`test_spectrum_card.py`)

`test_spectrum_card.py` tests `cards/spectrum.py`. `spectrum_card(seq, *, targets,
check_results, card_id)` builds the "Gradient spectrum" `Card` from the analysis
`gradient.spectrum` of the result matrix: it calls no spectrum function (`pulseq-analysis`
tests the calculation). The card reads the series `gradient_spectrum` of each target whose
result is done (the arrays `value`, `x`, `y` and `z` in Hz/m/√Hz, and the frequency
`coord_start + k * coord_step`), and draws it in mT/m/√Hz with the \|γ\| of the target. The
targets with the same \|γ\| and equal arrays are one group, and each group is one line in
each lane (several groups: the `series` of the lanes). `data` is the JSON-ready dict
(`reason`, `max_frequency_hz`, `db_floor`, `lanes`, `resonances`) and `script` is always
`"spectrum"`.

The tests use `tests/synthetic.py`'s `spin_echo_sequence` and `empty_sequence`, the target
profiles of `tests/profiles` and of the `make_profile` fixture, and `ResultMatrix` objects
that the file makes by hand, with a `gradient_spectrum` series of five frequencies (0 to
2000 Hz) in which `x` is 1 to 5 mT/m/√Hz for the proton gamma. Two tests run
`pulseq_checks.run_checks` for one target.

#### `test_without_a_chart_the_data_has_a_reason_and_no_lanes`

**Checks:** With no target, with no matrix, with a matrix that has no `gradient.spectrum`
result, with a result "not evaluated", with a result "error" and with a result "done" with
no series (no gradient event), `data["reason"]` is set and the card has no lanes, no maximum
frequency, no chart element and no scale button, and its `script` is still `"spectrum"`.

**How:** Six parametrized cases, each with the card for the spin echo sequence and one
target of the `make_profile` fixture.

**Assumptions:** None.

#### `test_a_result_that_is_not_done_gives_its_reason_in_the_body_escaped`

**Checks:** The note of the body has the reason of each analysis result that is not "done",
and the markup of a reason is escaped.

**How:** Two targets with an "error" result whose reason has `<b>` and `&`, and a "not
evaluated" result. The test checks the escaped reason and the other reason in the text of the
muted paragraphs, and that `<b>` is not in the body.

**Assumptions:** None.

#### `test_a_not_done_target_is_named_next_to_a_target_that_is_drawn`

**Checks:** When one target has a spectrum and another has an "error" result, the card
draws the four lanes of the first and its notes name the second with its reason.

**How:** Two targets, one "done" with a series and one "error". The test checks that `reason`
is None, the lane IDs, and a muted paragraph with the name and the reason of the second.

**Assumptions:** None.

#### `test_one_target_gives_four_lanes_of_the_series_in_mt_per_m`

**Checks:** One target gives the lanes Gx, Gy, Gz and RSS with their axis colors (RSS
"ink-2"), the unit mT/m/√Hz, no `series` key, the frequencies of the series, the values of
the series times 1e3 / \|γ\|, and a domain of 0 to 1.1 times the largest RSS value, with the
ticks 0 and that value. `max_frequency_hz` is the one of the series.

**How:** One target with the proton gamma and a hand-made series. The values are compared
within a relative 1e-3 (the card keeps four significant digits).

**Assumptions:** None.

#### `test_the_frequency_of_a_sample_follows_coord_start_and_coord_step`

**Checks:** The frequency of sample `k` is `coord_start + k * coord_step`.

**How:** A series with `coord_start` 10 Hz and `coord_step` 25 Hz; the test compares the
frequencies of the first lane with 10, 35, 60, 85 and 110 Hz.

**Assumptions:** None.

#### `test_targets_with_the_same_spectrum_and_gamma_are_one_group`

**Checks:** Two targets with the same \|γ\| and equal series give the same lanes as one target,
with no `series` key.

**How:** The test compares the `lanes` of the card of two targets with those of the card of
one target.

**Assumptions:** None.

#### `test_a_negative_gamma_is_in_the_group_of_its_magnitude`

**Checks:** Targets with γ and −γ are one group: no lane has `series`, and the last RSS value
is the series value times 1e3 / \|γ\|.

**How:** Two targets with the gamma 42.576e6 and −42.576e6 Hz/T and equal series.

**Assumptions:** None.

#### `test_targets_with_different_magnitudes_give_a_series_each_in_their_colors`

**Checks:** Two targets with different \|γ\| and equal arrays give each lane two `series`
(and no segments in the lane itself), in the colors `target-1` and `target-2`, labeled with
the names of their targets. The values of series `k` are the array times 1e3 / \|γ\| of group
`k`, and every lane has the domain and ticks of 1.1 times the largest RSS value of both.

**How:** Targets with the gamma 42.576e6 and 21.288e6 Hz/T, and the same series.

**Assumptions:** None.

#### `test_targets_with_one_gamma_and_different_spectra_give_a_series_each`

**Checks:** Three targets with one \|γ\|, of which the first and the third have equal series and
the second has twice the values, give two series: the first labeled with the names of the
first and the third target, the second with the name of the second, and the values of the
second are twice those of the first.

**How:** The test compares the labels, the colors and the ratio of the values.

**Assumptions:** None.

#### `test_the_window_and_the_frequency_come_from_the_series`

**Checks:** `max_frequency_hz` of the data is `meta["max_frequency_hz"]` of the series, and
the explanation has the window `meta["window_s"]` in ms and that frequency, not the constants
of the method.

**How:** A series with a window of 20 ms and a maximum frequency of 1000 Hz. The test checks
that the explanation paragraph has "20 ms" and "1000 Hz", and not "50 ms" or "2000 Hz".

**Assumptions:** None.

#### `test_each_target_with_resonances_has_its_bands_in_its_color`

**Checks:** `data["resonances"]` has, for each resonance of each target in the order of the
targets, `lo` and `hi` (frequency minus and plus half the bandwidth), the color of the target
and its name. A target without resonances gives none. The data has no `bands` key.

**How:** Targets example A, a profile without resonances, and example B.

**Assumptions:** The resonances of the example profiles are those of the files (700 Hz and
1300 Hz, 120 Hz and 200 Hz wide, for A; 800 Hz and 1500 Hz, 80 Hz and 250 Hz wide, for B).

#### `test_the_bands_are_in_the_data_without_a_chart`

**Checks:** A card with a target and no matrix has no chart, and its data still has the
bands of the target.

**How:** Example A with no matrix.

**Assumptions:** None.

#### `test_a_target_without_resonances_is_named_in_a_note`

**Checks:** A target without resonances is named in a muted paragraph, and a target with
resonances is not.

**How:** Example A and a profile named "Plain target" without `[acoustic]`; the test searches
the text of the `<p class="muted">` elements.

**Assumptions:** None.

#### `test_each_target_has_a_check_line_with_its_state_and_value`

**Checks:** The body has a line for each target, with the swatch of its color, its name, and
the result of the check `acoustic.resonance-energy` of that target: the state, the value and
the limit with the unit for "pass" and "fail", the reason (escaped) for "not evaluated". A
target that has no result of that check (only the result of another check) has its line with
no state and no value. The body has no table.

**How:** Four targets with a "pass" result (12.3 %, limit 30 %), a "fail" result (45.6 %), a
"not evaluated" result whose reason has `<band>`, and no result of the check.

**Assumptions:** None.

#### `test_the_check_line_does_not_depend_on_the_chart`

**Checks:** A card with no chart (an analysis "error" and a result with no gradient) still has
the check line of each target.

**How:** Two targets, one with a "pass" result of the check, one with none.

**Assumptions:** None.

#### `test_a_card_from_a_real_run_has_the_spectrum_and_the_check_result`

**Checks:** For the matrix of a real `run_checks` of example A, with the check and the
analysis, the card made by `build_cards` has the RSS lane equal to the series times
1e3 / \|γ\|, the frequency step of the series, `max_frequency_hz` of the series, and the state
and value of the result of the check in the line of the target.

**How:** `run_checks(spin_echo_sequence(), [A], select=["acoustic.resonance-energy"],
analyses=["gradient.spectrum"])`, then `build_cards(cards=["gradient-spectrum"], targets=...,
check_results=...)`.

**Assumptions:** None.

#### `test_a_real_run_for_a_sequence_without_gradients_has_no_chart`

**Checks:** For a sequence with only a delay block, the result of the analysis is "done" with
no series, and the card has the reason "no gradients", no lanes and no chart element.

**How:** `run_checks(empty_sequence(), [A], select=[], analyses=["gradient.spectrum"])`.

**Assumptions:** None.

#### `test_report_has_gradient_spectrum_card`

**Checks:** The rendered page has the gradient spectrum card with the chart, the Linear and dB
buttons with Linear selected, and the −80 dB note.

**How:** The test builds the card for one target with a hand-made series, renders the page,
cuts out the text from the card's id to the end of the result, and checks for the title, the
diagram element, the two scale buttons with their pressed states, and "drawn at −80 dB".

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

### 2.12 PNS card (`test_pns_card.py`)

`test_pns_card.py` tests `cards/pns.py`. `pns_card(seq, *, targets, check_results, card_id)`
shows the PNS of each target from its analysis result `pns.safe.levels` in the result matrix
(principle 9 of `docs/plans/pulseq-checks.md`): the card runs no SAFE model. For each target,
in order, it has a swatch of the target's color and its name, and then: with the state "done",
a table of the hardware and the peak percent for all axes, Gx, Gy and Gz, and a button that
shows the peak in the diagram; with another state, the reason of the result; without a result
in the matrix, a sentence that says so. The percent of a value `v` is `100 * v /
meta["threshold"]` of the series `pns_above_0` (decision P38). `_pns_data` (private) is the
summary of the series `pns_total` in percent and ms, from which the body is written. Without
targets, or without a matrix, the card has one muted note and no button, no script and no
data. The card gives no verdict and has no chart: the stimulation over time is the PNS lane of
the sequence diagram. The card's own data is what its script `assets/cards/pns.js` reads:
`{"format": 2, "goto": [...]}`, with one entry for each target: the message of its button (the
TR that holds the peak, or the block that holds it when the sequence has no `TR` definition),
or `None` for a target with no button. The browser checks the buttons.

The tests make the matrix with `pulseq_checks.run_checks(..., select=[],
analyses=["pns.safe.levels"])` for the example targets of `tests/profiles/` (A has the proton
gamma, C a negative gamma, and both have the SAFE parameters of pypulseq's example hardware,
which are invented), or, for a target without SAFE parameters, with the `make_profile` fixture.
One target runs on the sequence object, and several run on a file in `tmp_path`.

Most of the tests use the synthetic spin echo sequence
(`tests/synthetic.py`'s `spin_echo_sequence`) or the three-TR sequence built
in this file (`_three_trs`: three
50 ms TRs, one with a faster slew rate that gives it the highest PNS).

**Assumptions for the whole file:**

- The physics (the prediction itself and `peak_tr_window`) is
  `pulseq_analysis.pns`'s, and the matrix is `pulseq-checks`', which have their own tests.
  These tests check only that the card wires the series into JSON data and HTML correctly.
- The tests check names, reasons, numbers and which elements exist. They do not check the
  text of a note.

#### `test_pns_data_is_the_percent_of_the_threshold_of_the_result`

**Checks:** `_pns_data` gives the peak, each axis peak and the time of the peak of
`pns_total` as `100 * v / meta["threshold"]` of `pns_above_0` (percent) and ms, with the
hardware name of the result, and the threshold is the magnitude of the gamma of the target.

**How:** The test makes the matrix for target A and the spin echo sequence, reads the two
series with `pns_series`, and compares each value of `_pns_data` with the formula, within a
relative 1e-12. It checks that the threshold is `abs(gamma)` of the target, that the peak is
between 0 % and 100 % and at least each axis peak, and that `asc_file` is None.

**Assumptions:** None.

#### `test_the_percent_of_a_negative_gamma_target_uses_its_magnitude`

**Checks:** The PNS values of `pulseq-analysis` are in Hz/T of samples in Hz/m, so the same
SAFE parameters give the same peak for a target with the proton gamma (A) and for one with a
negative gamma (C), and the percent of C is the percent of A times the ratio of the
magnitudes of the gammas (the threshold of C is a positive number).

**How:** The test makes the matrix for A and C on a file, checks that the two gammas have
opposite signs, that the threshold of C is `abs(gamma)`, that the two peaks (Hz/T) are equal
within a relative 1e-12, and that the percent of C is above 0 and equals the percent of A times
`abs(gamma_A / gamma_C)`.

**Assumptions:** The SAFE parameters of examples A and C are the same (the files differ in the
name and the gamma only).

#### `test_the_card_shows_the_percent_of_each_target`

**Checks:** The table of each target shows its own numbers: the peak and its time, the three
axis peaks (each to one decimal), and the hardware name.

**How:** The test builds the card for A and C, and for each target takes `_pns_data` from the
same matrix and checks the body for the "peak at time" text, the three axis cells and the
hardware cell, with the formats `.1f` and `.3f`. The two targets have different thresholds,
so a card that used one threshold for both would fail.

**Assumptions:** None.

#### `test_report_has_pns_card`

**Checks:** For the synthetic spin echo sequence and target A, the card has the id `"pns"`,
the title "PNS prediction" and the script `"pns"`; its body has the peak rows, the name of
the target and the swatch of its color, no chart, no SVG and no verdict class; and
`render_page` accepts it, with the title.

**How:** The test builds the card and checks its `id`, `title` and `script`. It checks the
body for the rows for the peak of all axes, Gx, Gy and Gz, for the name of the target and
`var(--target-1)`, and that the body has no `<div class="chart">`, no `<svg`, no `status good` and
no `status bad`. It renders the page and checks for the section element with the card's id and
the `data-card-script="pns"` attribute, and the title.

**Assumptions:** None.

#### `test_two_targets_have_one_part_each_in_order`

**Checks:** With two targets, the body has one part for each, in the order of the targets,
each with its own color swatch, table and button.

**How:** The test builds the card for the targets C and A (in that order) and checks that the
name of C comes before the name of A, that the swatch `var(--target-1)` comes before the name
of C and `var(--target-2)` before the name of A, that the body has two tables and two buttons,
and that the buttons have the ids `pns-goto-0` and `pns-goto-1`, the first before the name of A.

**Assumptions:** None.

#### `test_the_goto_list_has_one_entry_for_each_target`

**Checks:** The `goto` list of the card data has one entry for each target, in order: the
payload of its button for a target with a result, and `None`, with no button, for a target
without SAFE parameters.

**How:** The test builds the card for A, a target without SAFE parameters, and C, in that
order. It checks that the format is 2, that the list has 3 entries, that the first and the
third are not None and are equal (the same sequence and the same Hz/T peak), that the second is
None, and that the body has the buttons `pns-goto-0` and `pns-goto-2` and not `pns-goto-1`.

**Assumptions:** None.

#### `test_a_target_that_is_not_evaluated_has_its_reason_and_no_table`

**Checks:** A target that gives no SAFE parameters has the reason of its result in the
card, and no table, no button, no data and no script.

**How:** The test makes the matrix for a target without SAFE parameters, checks that the
result has a reason, builds the card and checks that the body has the name of the target and a
part of the reason of `pulseq-checks` ("model pns.safe"), that it has no `<table` and no
`<button`, that `data` and `script` are None and that `scripts` is empty.

**Assumptions:** The reason of `pulseq-checks` names the missing model "pns.safe".

#### `test_a_target_name_and_a_reason_are_escaped`

**Checks:** The name of a target and the reason of its result are HTML-escaped.

**How:** The test builds the card for a target named `a<b>&` without SAFE parameters, and
checks that the body has the escaped name and not the raw `a<b>`.

**Assumptions:** None.

#### `test_a_target_without_a_result_in_the_matrix_says_so`

**Checks:** A target for which the matrix has no `pns.safe.levels` result has its name and
the analysis name in the card, and no table, no data and no script.

**How:** The test gives the card a matrix with the target and no result (the `make_matrix`
fixture) and checks the body for the target name and `pns.safe.levels`, for no `<table`, and
that `data` and `script` are None.

**Assumptions:** None.

#### `test_without_targets_the_card_has_a_note_and_no_pns`

**Checks:** With a matrix and no targets, the card has one muted note, no table, no button,
no data, no script, no scripts and no `error`, the SAFE model does not run, and `render_page`
accepts the card.

**How:** The test makes the matrix, replaces the SAFE model with a function that raises (the
chunk function of `pulseq_analysis.pns_levels`), builds the card with `targets=()` and checks
`data`, `script`, `scripts`, that the body starts with `<p class="muted">` and has no `<table`
and no `<button`, and that `error` is None. It renders the page.

**Assumptions:** The chunk function is the one way into the SAFE model of `pulseq-analysis`
(`pns_levels` calls it, and the other PNS functions call `pns_levels`).

#### `test_without_a_matrix_the_card_has_a_note_and_no_pns`

**Checks:** With a target and no matrix, the card has one muted note, no table, no button, no
data and no script, and does not name the target, and the SAFE model does not run.

**How:** The test replaces the SAFE model with a function that raises, builds the card with
the target A and no matrix and checks `data`, `script`, `scripts`, the note, no `<table`, no
`<button`, and that the name of the target is not in the body.

**Assumptions:** The same as for the test without targets.

#### `test_the_card_runs_no_safe_model`

**Checks:** With a matrix that has the result, the card does not call the SAFE model.

**How:** The test makes the matrix, replaces the SAFE model with a function that raises,
builds the card and checks that it has data.

**Assumptions:** The same as for the test without targets.

#### `test_card_without_gradients_has_no_data_and_no_script`

**Checks:** A sequence with no gradients gives a result that is "done" with no series, so the
card names the target, and has no table, no button, no data and no script.

**How:** The test builds the card for the empty synthetic sequence and target A, and checks
that the body has the name of the target and no `<table` and no `<button`, and that `data` and
`script` are None.

**Assumptions:** None.

#### `test_card_id_is_used_for_the_section_the_buttons_and_the_data_element`

**Checks:** With a non-default `card_id`, the card's own id follows it, and so do the id of its
button and its JSON data element key, which holds the card's data, so two PNS cards can be on
one page without an id clash.

**How:** The test builds the card with `card_id="pns-b"` and checks the id, the script
(`"pns"`) and the button id `pns-b-goto-0`. It renders the page, checks the section
`id="pns-b"`, reads the data element `id="pns-b-data"` and checks that its JSON is the card's
`data`.

**Assumptions:** None.

#### `test_data_with_a_tr_definition_has_the_peak_tr_and_the_peak_time`

**Checks:** For a sequence with a `TR` definition, the card's data is
`{"format": 2, "goto": [{"t0S", "t1S", "anchorS"}]}`: the range is the TR that
`pns.peak_tr_window` gives, and the anchor is the peak time of the result.

**How:** The test builds the three-TR sequence with the peak in the second TR, makes the
matrix and takes the peak time from `pns_total`. It computes the window with
`pns.peak_tr_window`, and checks that the card's data equals the format, the window and the
peak time exactly, and that the window is 50 ms to 100 ms.

**Assumptions:** None.

#### `test_the_peak_is_in_the_tr_with_the_fastest_slew`

**Checks:** For each position of the peak TR (first, second or third) in the three-TR
sequence, the card's `goto` is that TR, with the anchor inside it.

**How:** For peak TR k = 0, 1 and 2, the test builds `_three_trs(k)` and the card for target A,
and checks that `t0S` and `t1S` of the one `goto` entry are `0.05 k` and `0.05 (k + 1)` s and
that the anchor is between them.

**Assumptions:**

- TRs are counted from the start of the sequence, in steps of the TR definition.

#### `test_data_without_a_tr_definition_has_the_block_of_the_peak`

**Checks:** For a sequence without a `TR` definition, the card's data is
`{"format": 2, "goto": [{"block": k}]}`, with `k` the play index of a block that holds
the peak time.

**How:** The test takes the synthetic spin echo sequence, checks that
`pns.peak_tr_window` gives None for its peak time, and checks the key sets of the data.
It reads the start and duration of block `k` from `seq_index.sequence_index` and checks
that the block has a duration above zero and that the peak time is inside it.

**Assumptions:** None.

### 2.14 Gradient limits card (`test_gradient_limits_card.py`)

`test_gradient_limits_card.py` tests `cards/gradient_limits.py`: the "Gradient
limits" table (Gx, Gy, Gz and |G| rows, with the peak, the max slew, and the RMS, and, for
each target that has hardware limits, the percent of its limit of the peak and of the max
slew, in the gamma of that target), one table for each `TimeWindow`
(with the extra RMS column), the block and the time of each peak and max slew with
its "Show" button, one table for each distinct |gamma| of the targets with the gamma control,
and the names of the targets without limits.
Every expected numeric cell is computed by hand from the trapezoid the test
builds; the tests that read `gradient_limits` convert its Hz/m, Hz/m/s values with `GAMMA_1H`
as the card does. The tests read the card's
tables with Python's `html.parser` (`_CardParser`): the text of each cell, without a
button's own text, the attributes of each button, the `style` of each swatch, and the
`data-gamma-entry` of the element around each table. A target comes from a profile that the
`make_profile` fixture reads (`_targets`, with the `[opts]` lines of `_opts`); `SYSTEM_OPTS`
gives it the limits of the test system (`SYSTEM.max_grad` and `SYSTEM.max_slew`). The card
does not take limits from the sequence's system, so the tests that look at the percent columns
give a target.

Since phase 4 of `docs/plans/cards-at-scale.md`, a window's "RMS over whole file" column comes
from the one `gradient_limits` call's own `whole_rms_hz_per_m`, not a second call with
`window=None`.

#### `test_table_has_axis_rows_and_percents`

**Checks:** For a sequence with a single x trapezoid, the card's Gx, Gy, Gz and
|G| rows hold the hand-computed peak,
percent of the limit, max slew, its percent, and RMS, with "—" for the
max slew of |G| and its percent. The |G| RMS equals the Gx RMS, because only x
has a gradient. The Gx and |G| peak cells give block 1 and the end of the rise
(0.200 ms), the Gx max slew cell gives block 1 and the start of the rise (0.000
ms), and the zero values of Gy and Gz give no block.

**How:** The test builds a sequence with an x trapezoid, computes the expected
peak, slew and RMS from the trapezoid's parameters (as in
`test_trapezoid_peak_slew_and_rms_match_hand_computed_values`) and their
percents of `SYSTEM.max_grad` and `SYSTEM.max_slew`, and the expected cell texts,
with "(block N, t ms)" after a value that has a block. It calls
`gradient_limits_card` with one target that has the limits of `SYSTEM` and checks the card's `id`, `title` and `data`, and that
its one table has exactly the expected cell texts.

**Assumptions:** None.

#### `test_window_gives_rms_over_window_and_over_whole_file`

**Checks:** With a window, the table has two RMS columns, "RMS over window"
and "RMS over whole file", and the peak and the slew columns are over the
window.

**How:** The test builds a sequence with an x trapezoid and a window equal to
the rising ramp, given as a `TimeWindow`. It computes the expected peak, slew and window RMS from the
ramp alone (RMS from `amplitude^2 * rise_time / 3` divided by the window
length), with a target that has the limits of `SYSTEM`, and the expected whole-file RMS as in the first test. It builds
the expected cell texts from these hand-computed values, with both RMS columns
(the peak is at the window end, 0.200 ms, and the slew segment starts at the
window start, 0.000 ms), and checks that the card's body starts with the `<h3>`
of the window's label and that its one table has these cell texts.

**Assumptions:** None.

#### `test_two_windows_give_two_tables_with_the_values_of_each_range`

**Checks:** Two windows give two tables, each under an `<h3>` of its window's
label, with the values that `gradient_limits` gives for that window's range.

**How:** The test builds a sequence with an x trapezoid and a y trapezoid of
different amplitudes, and two windows, one half of the sequence each, and calls the card with a target that has the limits of `SYSTEM`. For each
window it builds the expected cell texts from the fields of
`gradient_limits(seq, window=...)`, with the block and time of each value, checks
that the two tables differ, and checks that the card's body starts with the first
`<h3>`, has the second, and that its two tables have these cell texts in order.

**Assumptions:** None.

#### `test_without_a_target_with_limits_the_tables_have_no_percent_columns`

**Checks:** With no target, and with a target that has no limits, the card has no "% of limit"
header and no percent cell: the whole-file table has 4 cells in each row, and the table of each
window has 5. With a target that has limits, each row has the two percent cells more, and each
table has two "% of limit" headers.

**How:** The test builds the two-trapezoid sequence and two windows. For the card without
windows and with the two windows, each with no target, with a target that has only a max
amplitude, and with a target that has the limits of `SYSTEM`, it reads the tables
and checks the number of tables (1, or 2 for the windows), the number of "% of limit" headers in
each header row (0, or 2), and that each of the 5 rows (the header, Gx, Gy, Gz and |G|) has as many cells as 4
(or 5 with windows) plus the number of percent columns.

**Assumptions:** None.

#### `test_without_a_target_with_limits_the_values_are_those_with_one`

**Checks:** The table without a target is the table with a target that has limits less its two
percent columns: the other cells are the same.

**How:** The test builds the two-trapezoid sequence, reads the table of the card without
targets and the table of the card with a target that has the limits of `SYSTEM`, checks that the
percent columns of the second are columns 2 and 4, and that the first equals the second with
those columns removed from each row.

**Assumptions:** None.

#### `test_window_outside_the_sequence_raises`

**Checks:** A window outside the sequence raises `ValueError` with the window's
label.

**How:** The test calls `gradient_limits_card` with a window after the end of the
sequence, and checks the error.

**Assumptions:** None.

#### `test_no_gradients_adds_a_reason_note`

**Checks:** A sequence with no gradient events gets a muted note in the card
that gives the reason, with no file name in front of it. The card has no "Show"
button, and so no script.

**How:** The test builds a sequence with a delay block only, calls
`gradient_limits_card`, and checks that the body contains
`<p class="muted">no gradient events in the sequence.</p>`, that the body has no
button, and that `script` is None and `scripts` is empty.

**Assumptions:** None.

#### `test_render_page_accepts_gradient_limits_card`

**Checks:** `render_page` accepts the card that `gradient_limits_card`
returns, and the page has the card's script, registered under the name in
`Card.script`.

**How:** The test builds a card from a sequence with a trapezoid, calls
`render_page` with it, and checks that the card's section (with
`data-card-script="gradient-limits"`), its `<h2>` title and the script's
`registerCard("gradient-limits"` call are in the result.

**Assumptions:** None.

#### `test_show_buttons_send_the_block_of_each_value_with_its_time`

**Checks:** The card has one "Show" button for each peak and max slew that has a
block. A button's `goto` range is the block with half its duration on each side,
and its anchor is the time of the value. The buttons start hidden, and the card
has the script that sends their messages and publishes `goto`.

**How:** The test builds an x trapezoid block (0.2 of the limit) and a y
trapezoid block (0.5), each 1.4 ms. It checks that the buttons' `aria-label`s name
exactly the Gx and Gy peaks and max slews and the |G| peak; that the Gy peak and
|G| peak buttons have `data-t0` 0.7 ms, `data-t1` 3.5 ms and `data-anchor` 1.6 ms
(block 2 from 1.4 ms to 2.8 ms, the end of its rise at 1.6 ms) and the `hidden`
attribute; and that the card's `script` is `gradient-limits`, it has one script
text, and `publishes` is `("goto",)`.

**Assumptions:** The script itself runs only in a browser: no test runs it (there
are no DOM tests). It is checked by hand in a browser.

#### `test_show_button_view_of_a_short_block_is_1_ms_wide`

**Checks:** For a block shorter than 0.5 ms, a button's view is 1 ms wide, centred
on the block, as the diagram's own `goto` of a block.

**How:** The test builds one x trapezoid block of 0.3 ms and checks that every
button's `data-t0` and `data-t1` are 0.5 ms before and after the block's middle
(0.15 ms).

**Assumptions:** None.

#### `test_each_target_has_its_percent_columns_with_its_own_gamma_in_target_order`

**Checks:** With two targets that have limits and two gammas, the table has the percent of
the peak of the first target, then of the second, after the peak, and the same for the max
slew. Each percent is the value of `gradient_limits` (Hz/m, Hz/m/s) in mT/m (T/m/s) with the
gamma of that target, over its limit, times 100, for the Gx, Gy, Gz and |G| rows (the |G| row
has no slew percent). The heading of each percent column names its target, after a swatch
with the color token of the target. The two gammas give two tables, and both have the same
percent columns.

**How:** The two-trapezoid sequence and two profiles with different limits and gammas (the
second 20 MHz/T). The expected percents are computed from `gradient_limits(seq)` and the
`hardware_limits` of the profiles; the swatch colors are read from the `style` of the swatches.

**Assumptions:** None.

#### `test_a_target_without_limits_has_no_percent_column_and_is_named`

**Checks:** With a target that has limits and a target that has none (a max amplitude and no max
slew), the table has the percent columns of the first only. The name of the second, escaped, is
in the card, and it is not in a heading.

**How:** The two-trapezoid sequence; the name of the second target has `<`, `>` and `&`. The test
checks the headings of the table and that the escaped name is in the body and the raw one is not.
It does not test the sentence of the note.

**Assumptions:** None.

#### `test_a_negative_gamma_gives_the_percent_of_its_magnitude`

**Checks:** Two targets with the same limits and the gammas 11.777 MHz/T and -11.777 MHz/T
give one table (one |gamma|), and the two percent columns of the peak are equal, and so are
the two of the max slew. They equal the value in Hz/m (Hz/m/s) in mT/m (T/m/s) with the
magnitude of the gamma, over the limit. The Gy percent is above 100, so it is not 0.

**How:** The two-trapezoid sequence and two profiles; the expected percents come from
`gradient_limits(seq)`.

**Assumptions:** None.

#### `test_two_gamma_magnitudes_give_a_table_for_each_and_the_control`

**Checks:** With the targets `example_a` (42.576 MHz/T) and `example_c` (-11.777 MHz/T), each
window has two tables, in elements with `data-gamma-entry` 0 and 1, the second `hidden`; the Gy
peak cell of table k is the peak in mT/m with the |gamma| of entry k. The card has one control
with two buttons (`data-gamma-choice` 0 and 1, the first pressed, with the gammas as
`data-gamma`) before the first table. Its script is `gradient-limits` and it has one script text,
the `gradient-limits` one.

**How:** The two-trapezoid sequence, two windows, and the two profiles of `tests/profiles`.

**Assumptions:** The script runs only in a browser: no test runs it. It is checked by hand in a
browser.

#### `test_one_gamma_magnitude_gives_one_table_and_no_control`

**Checks:** Targets with the gammas 42.576 MHz/T and -42.576 MHz/T give one table, in no
element with `data-gamma-entry`, and the card has no control.

**How:** The two-trapezoid sequence and two profiles.

**Assumptions:** None.

#### `test_a_control_without_a_show_button_has_the_gamma_select_script`

**Checks:** A sequence with no gradient event has no "Show" button. With two |gamma| entries,
the card has two tables, its `script` is `gamma-select`, its `scripts` is the text of
`assets/cards/gamma-select.js`, and the page has the `registerCard("gamma-select"` call.

**How:** A delay-only sequence, the two profiles of `tests/profiles`, and `render_page`.

**Assumptions:** None.

#### `test_without_targets_the_values_are_in_the_gamma_of_the_sequence`

**Checks:** Without targets, the peak is in mT/m with `seq.system.gamma`, in one table, in no
element with `data-gamma-entry`, with no control.

**How:** A sequence whose system has the gamma 20 MHz/T, with an x trapezoid of 0.4 of the system's
max amplitude; the Gx peak cell is `amplitude / gamma * 1e3` mT/m (11.2 mT/m) with its block and time.

**Assumptions:** None.

#### `test_the_registry_gives_the_targets_to_the_card`

**Checks:** `build_cards` with `targets` builds the gradient limits card that
`gradient_limits_card` builds with the `ReportTarget` of each profile, and the table has the
four percent columns of two targets.

**How:** The two-trapezoid sequence and two profiles; `build_cards(..., cards=["gradient-limits"])`
compared with a direct call.

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
`max_grad` in Hz/m (the lanes are in the units of the file, with a tolerance of 1 Hz/m). It checks that there is one ADC window whose
length matches `NUM_SAMPLES * DWELL` in ms, that the RF phase lane has two
segments, and that `first_adc_window`'s end is after the ADC window's end.

**Assumptions:**

- The synthetic spin echo sequence's block pulses have no slice-select
  gradient, so Gz has no events (unlike vb-pulseq's own spin echo, which
  used slice-selective pulses and so had Gz events too).

#### `test_value_lanes_are_in_the_units_of_the_file_with_a_peak_and_no_axis`

**Checks:** The value lanes (`rf_mag`, `gx`, `gy`, `gz`) of `file_lanes` have the `peak` (the
largest absolute value of the lane in Hz for the RF magnitude and Hz/m for a gradient, from
pypulseq's events) and `symmetric` (False for the RF magnitude, True for a gradient), and none of
`domain`, `ticks` and `tick_labels`: the browser calculates them for the selected gamma.

**How:** On the synthetic spin echo sequence, the peaks are calculated from the amplitudes of
`seq.get_block` (the RF signal and the gradient amplitude) and compared with `pytest.approx` at
a relative 1e-12; the keys of each lane are checked.

**Assumptions:** The gradients of the sequence are trapezoids, so the peak is the amplitude.

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
`iter_blocks` of `tests/oracles/blocks.py`, takes the RF refocusing block
and the Gy crusher block right after it. It calls `file_lanes` with a range
that starts inside the RF block and ends inside the crusher block. It checks
that the RF magnitude lane's first point is at the RF block's own start
(earlier than the range's requested start) with value 0, and that the Gy
lane's last point is at the crusher block's own end (later than the range's
requested end) with value 0.

**Assumptions:** None.

#### `test_first_adc_window_label_and_times`

**Checks:** `first_adc_window` gives a window from 0 to 1.1 times the end of
the first ADC window (or the file's own end, if that is shorter), with a
label that names that end time.

**How:** The test builds a synthetic gradient echo sequence with a short TR,
reads the first exact ADC window's end from `file_lanes`, computes the
expected end as `min(duration_ms, 1.1 * first_window_end_ms)` rounded the
same way the function documents, and checks `first_adc_window`'s
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
`full_window`'s `start_s`, `end_s` and `label` against the
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

`test_diagram_card.py` tests `cards/diagram.py`. `diagram_card` sends the
sequence as `data["file"]` (its compressed block and event tables,
`diagram_data`, plus `lane_meta`), and one entry in `data["windows"]` for each
caller-given time window, with one button for each window in the given order
(section 4.1 of `docs/plans/diagram-event-table.md`; the data format is 4 since
phase 7b of `docs/plans/pulseq-checks-implementation.md`: the tables keep the units of the file
(Hz/m and Hz), `file.lanes` give the `peak` of a value lane and no axis, and `file.gamma` lists
the signed gammas of the targets; phase 7 made `file.pns` a list). There is no lane set and no point
budget any more: every view is drawn in the browser from the tables (phase
4's job is done there, not in Python). The last test is adapted from
vb-pulseq's `test_report_has_zoom_controls_on_each_line_chart`.

#### `test_data_has_format_4_with_file_and_window_keys`

**Checks:** `diagram_card`'s data has the keys `format`, `file` and `windows`,
with `format == 4`; the `file` entry has the keys `duration_s`, `num_blocks`,
`lanes`, `gamma` and `tables` (no `name`, and no `pns` without PNS data), a `lanes` equal to
`lane_meta(seq)`, a
`duration_s` and `num_blocks` equal to `waveforms.duration_s(seq)` and
`len(seq.block_events)`, and each table entry has the keys `dtype`, `length`
and `data`; there is one window entry for each given window, with the keys
`label` and `view_ms` (no `file`).

**How:** The test builds a synthetic spin echo sequence and calls
`diagram_card` with its `first_adc_window` and `full_window`, then checks
the key sets and values of `card.data`, of its `file` and of its windows
directly against `diagram_data.lane_meta`, `waveforms.duration_s` and
`seq.block_events`.

**Assumptions:** None.

#### `test_the_tables_and_the_lane_peaks_are_in_the_units_of_the_file`

**Checks:** The largest RF magnitude in the tables is the peak of the RF signal in Hz, the
largest gradient value is the largest gradient amplitude in Hz/m (pypulseq's events, no
division by a gamma), and the `peak` of each value lane of `file.lanes` is that peak.

**How:** On the synthetic spin echo sequence, the peaks come from the events of
`seq.get_block`; the decoded `rf_mag` and `grad_value` tables and the `peak` of each lane are
compared with `pytest.approx` at a relative 1e-12.

**Assumptions:** None.

#### `test_without_targets_the_gamma_is_the_gamma_of_the_sequence`

**Checks:** Without targets, `file.gamma` is one entry with `seq.system.gamma` and no names
(also for a negative gamma of the sequence), and the card has no gamma control.

**How:** The card for a synthetic spin echo sequence and for a sequence with `Opts(gamma=-11.777e6)`.

**Assumptions:** None.

#### `test_the_gamma_entries_are_the_signed_gammas_of_the_targets_and_the_tables_do_not_change`

**Checks:** Two targets with one gamma are one entry in `file.gamma` with both names and no
control. Targets with a negative gamma and the default gamma are two signed entries in the order
of the first target of each, with two control buttons; the card script stays `diagram`, and the
tables and the lanes are the same as the card without targets (the units of the file do not
depend on the gamma).

**How:** `diagram_card` with `report_targets` of the example profiles (`example_c` has the
gamma -11.777 MHz/T); the entries are compared with the gammas of `make_opts()`.

**Assumptions:** None.

#### `test_tables_decode_to_diagram_tables`

**Checks:** The `file` entry's `tables`, decoded with
`pulseq_analysis.series.decode_array` for each array, equal `diagram_data.diagram_tables(seq)`: the
same table names, the same dtype and the same values for each.

**How:** The test builds a synthetic gradient echo sequence, calls
`diagram_card` with its `full_window`, decodes the `file` entry's
`tables`, and compares each decoded array's dtype and values
(`numpy.array_equal`) against `diagram_tables(seq)`'s own arrays.

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

#### `test_a_window_outside_the_sequence_raises`

**Checks:** `diagram_card` raises `ValueError`, with the window's label in the
message, for a window that is not inside the sequence: one that ends after the
end of the sequence, and one that starts before 0.

**How:** The test is parametrized over two `TimeWindow` objects (`"past the
end"`, from 0 to 10^6 s, and `"before the start"`, from -0.5 s), calls
`diagram_card` with a synthetic spin echo sequence and that one window, and
expects `ValueError` with a message that matches the label.

**Assumptions:** None.

#### `test_end_before_start_raises`

**Checks:** `diagram_card` raises `ValueError`, with the window's label in the
message, when a window's end is not after its start.

**How:** The test calls `diagram_card` with a `TimeWindow` whose `end_s` is
before its `start_s` and expects `ValueError` with a message that matches the
label.

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

#### `test_diagram_card_has_zoom_controls_directly_before_its_chart`

**Checks:** The rendered page has the zoom button group directly before the
diagram's `<div class="chart">`.

**How:** Adapted from vb-pulseq's
`test_report_has_zoom_controls_on_each_line_chart`. The test builds a
diagram card and renders it. It checks that
`markup.zoom_controls("diagram-diagram")` appears exactly once, that the
text right after it (skipping one newline) starts with
`<div class="chart"` and has `id="diagram-diagram"` within its first 400
characters.

**Assumptions:** None beyond the file's assumptions.

#### `test_pns_false_by_default_adds_no_pns_key`

**Checks:** Without `pns_lane` (the default, `False`), the `file` entry has no `"pns"` key.

**How:** The test builds a diagram card for the synthetic spin echo sequence with no
`pns_lane` argument and checks that `"pns"` is not a key of the `file` entry.

**Assumptions:** None.

#### `test_targets_and_a_matrix_without_pns_lane_add_no_pns_key`

**Checks:** With targets and a matrix that has the PNS result, but with `pns_lane=False`
(the default), the data has no `pns` key.

**How:** The test makes the matrix for target A and the spin echo sequence, builds the card with
the target and the matrix and no `pns_lane`, and checks that `file` has no `"pns"` key.

**Assumptions:** None.

#### `test_one_target_gives_one_pns_entry_from_its_series`

**Checks:** With `pns_lane=True`, one target and its matrix, `file.pns` is a list with one
entry that has exactly the keys `target`, `color`, `hardware`, `asc_file`, `hw`, `dtS`,
`binSamples`, `threshold`, `summary`, `levels` and `runs`. The values are those of the series
of the result, with no division: the target name and the color `target-1`, the hardware name
of `pns_total`, no `.asc` file, the SAFE parameters of the profile (the eight keys that
`pns_lanes.js` reads, for each axis), the gradient raster, the bin size, the threshold
(`abs(gamma)` of the target, Hz/T), the summary of `pns_total` (the peak, its time and the axis
peaks, Hz/T, between 0 and the threshold), and `levels` and `runs` that decode to the arrays
of the series exactly (float32 `min` and `max`, float64 `start` and `end`).

**How:** The test makes the matrix, builds the card, and compares each field with the series
and the profile. It decodes the tables with `pulseq_analysis.series.decode_array` and
compares the arrays with `numpy.array_equal` and the dtypes.

**Assumptions:** None.

#### `test_two_targets_give_two_entries_in_order_with_their_own_thresholds`

**Checks:** With two targets, `file.pns` has two entries in the order of the targets, with the
colors `target-1` and `target-2` and their own thresholds, which are the magnitudes of their
gammas also for a negative gamma. The levels and the summary, in Hz/T, are the same for two
targets with the same SAFE parameters.

**How:** The test makes the matrix for the targets C (a negative gamma) and A on a gradient
echo sequence file, builds the card, and checks the order, the colors, the thresholds
(`11.777e6` and `abs(gamma)` of A), that the gamma of C is negative, and that the
encoded levels and the summaries of the two entries are equal.

**Assumptions:** The SAFE parameters of examples A and C are the same.

#### `test_a_target_that_is_not_evaluated_has_no_entry_and_is_named_with_its_reason`

**Checks:** A target without SAFE parameters has no entry in `file.pns`, and the explanation
under the chart names it, escaped, with the reason of its result; the other target has its
entry, with the color of its place in the report (`target-2`), and is not named in the
explanation.

**How:** The test makes the matrix for a target named `no <safe>` and for A, builds the card
and checks the entry, the escaped name and a part of the reason of `pulseq-checks`
("model pns.safe") in the body, and that the name of A is not in the part of the body after the
status line.

**Assumptions:** The reason of `pulseq-checks` names the missing model "pns.safe".

#### `test_without_a_pns_result_the_lane_has_no_entry`

**Checks:** With `pns_lane=True`, no key `pns` is in `file` when there are no targets, when
there is no matrix, when the matrix has no result for the target, and when the target is not
evaluated. The card still builds, and in the last two cases its explanation names the target.

**How:** The test builds the four cards for the spin echo sequence and checks `file`, `error`
and, for the last two, that the body has the name of the target.

**Assumptions:** None.

#### `test_a_sequence_without_gradients_has_no_pns_entry`

**Checks:** A sequence with no gradient event gives a result that is "done" with no series, so
there is no `pns` key, and the card builds.

**How:** The test builds the card for the empty sequence and target A and checks `file` and
`error`.

**Assumptions:** None.

#### `test_the_lane_runs_no_safe_model`

**Checks:** The card reads the matrix and does not call the SAFE model.

**How:** The test makes the matrix, replaces the chunk function of the SAFE model of
`pulseq_analysis.pns_levels` with a function that raises, builds the card, and checks that it
has one entry.

**Assumptions:** The chunk function is the one way into the SAFE model of `pulseq-analysis`.

#### `test_pns_lane_that_is_not_a_bool_raises_type_error`

**Checks:** `diagram_card` raises `TypeError`, with `pns_lane` in the message, for a
`pns_lane` that is not a `bool`: 1, 0, "yes", None and `numpy.True_`.

**How:** The test is parametrized over the five values and expects `TypeError`.

**Assumptions:** None.

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
PNS lane: it is not conditional on `pns_lane`, since the RF, ADC and gradient groups
can be toggled regardless, and the card script fills it in the browser with one
button for each group that applies to the file's own data.

**How:** The test builds a diagram card with no `pns_lane` argument (`pns_lane=False`, the
default) and checks that the empty group-controls container is present in the
body.

**Assumptions:** None.

#### `test_g_lane_explanation_sentence_always_present`

**Checks:** The card's body always has the |G| lane's explanation sentence (naming
the |G| lane and that it shows the magnitude of the gradient vector), whether or not
`pns_lane` is given: the |G| lane needs no extra data from `diagram_card` (`docs/plans/
diagram-lanes.md`, phase 5; it is computed in the browser from the tables already
sent), unlike the PNS sentence.

**How:** The test builds a diagram card with no `pns_lane` argument (`pns_lane=False`, the
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

### 2.17 Block table card (`test_blocks_card.py`)

`test_blocks_card.py` tests `cards/blocks.py`. `blocks_card` builds a
collapsed "Blocks (table view)" card from `waveforms.block_rows`: the first
`max_rows` blocks when there are no windows (vb-pulseq's own note and table,
parity), or one table for each window when `windows` is given; a window that is
not inside the sequence raises `ValueError`. Every expected table in this file is built with
`markup.html_table`, the same helper the card itself uses, from the rows that
`block_rows` gives directly, so a test also fixes the exact table that
`html_table` would render from those rows.

#### `test_note_and_table_when_rows_are_cut`

**Checks:** For a sequence with more blocks than `max_rows`, `body_html` is the
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

#### `test_a_window_outside_the_sequence_or_without_length_raises_value_error`

**Checks:** `blocks_card` raises `ValueError` that names the label of a window
that ends after the sequence, starts before 0, or does not end after its start.

**How:** The test builds a synthetic gradient echo sequence and, for each of
the three bad `TimeWindow`s, calls `blocks_card` with a good window followed by
the bad one, and checks that `pytest.raises(ValueError, match=label)` holds.

**Assumptions:** None.

### 2.18 Diagram tables (`test_diagram_data.py`)

`test_diagram_data.py` tests `diagram_data.py`: the compact per-file tables
(`diagram_tables`), their gzip+base64 wire form (`pulseq_analysis.series.encode_array`,
`decode_array`, which `pulseq-analysis` tests), and the lane metadata built from the tables instead of the
expanded points (`lane_meta`). `waveforms.file_lanes` and
`waveforms._events_in_range` are the reference (section 3.5 of
`docs/plans/diagram-event-table.md`): the module must give the same numbers,
because `test_seq_lanes_golden.py` rebuilds these same numbers in JavaScript
and a golden test there compares them with `==` and no tolerance. Most of
these tests therefore compare with `numpy.array_equal` rather than
`pytest.approx`.

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
`encode_array`/`decode_array` for each array (so the check also exercises the wire form),
and compares the two helpers' output per lane with `numpy.array_equal`.

**Assumptions:** None.

#### `test_encode_then_decode_gives_the_same_arrays_and_dtypes`

**Checks:** `decode_array(encode_array(a))` for each array of `diagram_tables` gives back the same table
names, the same dtype for each array, and the same values.

**How:** The test builds the tables of a synthetic gradient echo sequence,
round-trips each array through `encode_array` and `decode_array`, and checks
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
  this placement). `buildEightPointModel` gives every block the same,
  known number of points, so a view can be built that holds exactly
  `EXACT_POINT_LIMIT` points.
- `buildRandomModel`: a pseudo-random model of any block count (so it can be
  built larger than 1024 or 2048 blocks, to cross a checkpoint boundary),
  seeded for a deterministic sequence, used where the exact points are too
  many to check by hand.

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
  `test_min_max_lanes_matches_brute_force_for_adc_windows` compute the
  expected bins by brute force from the exact whole-file points, and compare
  `minMaxLanes`'s output with them.

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

**How:** The test builds `buildEightPointModel(2600)`, where every block
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

`test_extensions.py` tests that `cards/spectrum.py`, `cards/pns.py`,
`cards/gradient_limits.py` and `cards/diagram.py` refuse a sequence with a rotation,
through `pulseq_analysis.extensions.refuse_rotations` (`pulseq-analysis` has its own
tests of that guard). The test makes its own rotation sequence by hand, the way pypulseq
draft PR #372 stores a rotation: a `rotation_library` event library on the `pp.Sequence`,
because pypulseq 1.5.0.post1 cannot make a rotation.

#### `test_gradient_cards_refuse_rotations`

**Checks:** `spectrum_card`, `pns_card`, `gradient_limits_card` and
`diagram_card` each raise `NotImplementedError` for a sequence with a
rotation library. The test checks the type, not the message.

**How:** The test is parametrized over the four cards; `diagram_card` also
needs a window, so it is called through a lambda that gives it
`waveforms.full_window`. For each, it builds a `gre_sequence` with a
non-empty `rotation_library` and calls the card inside `pytest.raises`.

**Assumptions:** None.

### 2.25 PNS lane in JavaScript (`test_pns_lanes.js`)

`pns_lanes.js` computes the PNS lane of the sequence diagram in the browser, with
no DOM and no network (`docs/plans/diagram-lanes.md`, phase 3): `PnsLanes.decode`
builds a model from the diagram tables, one entry of the `file.pns` list of the diagram data
(the SAFE parameters, the raster, the stored level in Hz/T and the `threshold` of a target); the
gradient values of the tables are in Hz/m;
`exactView` gives the exact PNS of a short time range with the block maps of
the prototype (`prototypes/pns_lanes/pns_lanes.js` in the tag
`archive/pns-lanes-prototype`) (a scan with a checkpoint every `GROUP_BLOCKS`
blocks), not a per-sample recursion over the whole file; `levels` builds the coarser
pyramid levels of a stored level; `lanesFor` picks between the exact view and the
pyramid for one render, as `SeqLanes.lanesFor` picks between the exact and the
minimum/maximum view; `percent`, `laneMeta`, `runMarks`, `overlay`, `peaksText` and
`statusText` are the pure helpers the diagram card script (`assets/cards/diagram.js`) uses to
build the PNS lane of all the targets (one line for each, the runs as marks) and its
status-line text (task 4.3 of the diagram lanes plan, and phase 7 of
`docs/plans/pulseq-checks-implementation.md`). The model runs on the gradient samples in Hz/m
(`grad_value`), so its totals are in Hz/T, and the lane values are
`percent(v, threshold)`.

The tests load `pns_lanes.js` directly, with Node's `require`, from
`src/pulseq_reports/assets/pns_lanes.js`, the same way `test_seq_lanes.js` loads
`seq_lanes.js`. They use `node:test` and `node:assert/strict`, and no browser or
DOM. There is no pypulseq in this file (rule: lean on pypulseq, but there is no
pypulseq reference for a pure JavaScript module): every model is hand-made typed
arrays, built by `buildPnsTables` (a seeded pseudo-random block table, as
`test_seq_lanes.js`'s `buildRandomModel` is, reused by most tests) or by a fully
explicit small table (`buildBorderTables`, `buildOffRasterTables`, and the two
empty/no-gradient tables of the last two tests). The hardware numbers
(`hwSet`/`HW`) are pypulseq's own `safe_example_hw()` values, copied from the
table of the README in the tag `archive/pns-lanes-prototype`
(`prototypes/pns_lanes/README.md`), not read from pypulseq. The test file has its own
`HZ_PER_MT` (42576 Hz/m for 1 mT/m of the proton gamma: the hand-made events are written in
mT/m and put in the tables in Hz/m) and a `THRESHOLD` of 42576000 Hz/T for its models.

Two independent references stand in for a Python or pypulseq comparison:
`bruteForceTotals` re-derives the whole model (the gradient of each axis, the
three filters, the axis fractions and the total) directly from the tables, in a
single pass over the whole file, never calling any function of `pns_lanes.js`.
`collectPlainRecursion` calls the test file's own `plainRecursion` (the
whole-file, zero-initial-state recursion over the model's per-event samples,
which it reads through `PnsLanes._internal.eventEntry`), which is not used by
`exactView` itself (the block maps are). Comparing `exactView`'s output (the
block maps) to `plainRecursion`'s output over the same range is item 1 of task
3.4 in phase 3 of `docs/plans/diagram-lanes.md`: the two are the same model, so
they must agree to 1e-12 of the peak, not bit for bit (`assertWithinPeakTol`).
A value that comes from the same call (for example the sample times `exactView`
returns) is compared with no tolerance.

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

**Checks:** The per-sample recursion of the test file (`plainRecursion`)
agrees with an independent, from-scratch implementation of the SAFE model's
formulas (`bruteForceTotals`), to 1e-12 of the peak.

**How:** Builds an 80-block pseudo-random model (`buildPnsTables(80, 7)`, which
includes a 0-duration block and a no-gradient block by construction), decodes it,
computes `bruteForceTotals` directly from the tables and `collectPlainRecursion`
from the model, and compares the two whole-file total arrays with
`assertWithinPeakTol`.

**Assumptions:** None beyond the file's assumptions.

#### `test_exact_view_matches_plain_recursion_across_many_views`

**Checks:** `exactView` (the block maps, with the checkpoint skip) agrees with
`plainRecursion` (the plain per-sample recursion) to 1e-12 of the peak, for views
that start inside many different blocks and checkpoint groups of a model larger
than `3 * GROUP_BLOCKS`. This is item 1 of task 3.4 in phase 3 of
`docs/plans/diagram-lanes.md`.

**How:** Builds a 500-block pseudo-random model (more than `3 * 64` blocks, so
`GROUP_BLOCKS` is confirmed to be 64 and the model crosses more than 3 checkpoint
groups), computes each block's start time independently (a running sum of the
durations, not calling the module), and for each of 12 starting blocks (block 0,
1, the blocks around the first and second checkpoint boundaries, and others up to
the last block) and 4 span lengths, calls `exactView` with a large enough `bins`
that the "samples" kind is always chosen, and compares its `total` array against
the matching slice of the whole-file `plainRecursion` array (found by the
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
that the README in the tag `archive/pns-lanes-prototype` already checked).

**How:** `buildBorderTables` gives block 0 (10 samples) a gx event whose last two
points both hold the value 8 through the block's end, and block 1 (8 samples) a
gx event that starts at offset 0 already at 8 before ramping to 0. The test
checks `bruteForceTotals` against `collectPlainRecursion` for the whole file, then
checks `exactView` against the same `plainRecursion` reference for 4 ranges:
inside block 0, spanning most of the file, starting exactly at the border, and
straddling the border.

**Assumptions:** None beyond the file's assumptions.

#### `test_exact_view_bins_match_brute_force_binning_of_the_samples`

**Checks:** `exactView`'s "bins" kind (the minimum and the maximum of the total in
each of `bins` bins) equals a brute-force binning of the same range's "samples"
kind values, with the formula that `exactView` uses
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
with the same formula, and compares the resulting minimum and maximum arrays
to `exactView`'s own "bins" output, and the bin edges to the formula
`edges[k] = t0 + span * k / bins`, all with exact equality (both come from the
same underlying sample values, only reduced by `min`/`max`, which introduces no
rounding).

**Assumptions:** None beyond the file's assumptions.

#### `test_exact_view_bins_empty_bin_is_plus_minus_infinity`

**Checks:** A bin with no sample in it gets `min = +Infinity`, `max = -Infinity`,
not 0 or `NaN`.

**How:** Builds a 40-block, 200-sample model, then asks `exactView` for a view
`[0, 5 * numSamples * dt]` (5 times the file's own duration) with 20 bins: the
bins spread evenly over the whole requested range, but real samples exist only in
the file's own, much shorter span, so only the first few bins can ever hold a
sample. The test checks that kind is "bins" and that at least one bin has
`max === -Infinity` and, for every such bin, `min === Infinity`.

**Assumptions:** None beyond the file's assumptions.

#### `test_exact_view_sample_range_edge_cases`

**Checks:** The sample range `[t0, t1]` behaves correctly at its edges (the
samples k with `t0 <= (k + 0.5) * dt <= t1`, as the README's section "Interface
of `pns_lanes.js`" in the tag `archive/pns-lanes-prototype` has it): a view that
starts before the file and ends after it returns every sample; a view with
`t0 = t1` exactly on one sample's centre time returns that one sample; a view
strictly between two samples' centre times returns none.

**How:** Builds a 30-block model with two block-duration options, computes the
whole-file `plainRecursion` reference, and checks three `exactView` calls: `(-5,
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
(in percent of the model's threshold, and milliseconds), with `exact: true`, `binMs: null`,
`gap: false`; a short but sample-rich view gives the same zigzag shape as
`exactView`'s own "bins" kind, with `minmax: true`.

**How:** `buildPyramidModel(8)` builds a model whose stored level comes from the
test file's `plainRecursion` (so that the numbers are realistic):
it decodes a 1100-block model once with a placeholder level to get the exact
per-sample totals, bins those totals into a real stored level of `binSamples = 8`
by hand, and decodes the same tables again with that level. For a 100-sample view
(`[0, 1] ms`), it checks `lanesFor`'s single segment against the
`sampleRangeFor`-selected slice of the exact totals (`assertWithinPeakTol`, since
`lanesFor`'s exact branch is `exactView`, not `plainRecursion`) and each point's
time against `(k + 0.5) * dt * 1000`. For a 500-sample view with 10 bins (forcing
the "bins" kind), it calls `exactView` directly for the same range and bins, and
checks that `lanesFor`'s zigzag segments (read back into a `{edge_ms: [min,
max]}` map by `zigzagBins`, as `test_seq_lanes.js`'s `gotLineBins` reads
`minMaxLanes`'s segments) hold exactly `[100 * view.min[k] / THRESHOLD, 100 *
view.max[k] / THRESHOLD]` at each non-empty bin's edge, and that an empty bin is absent from the map.

**Assumptions:** None beyond the file's assumptions.

#### `test_lanes_for_pyramid_branch_matches_brute_force_of_overlapping_level_bins`

**Checks:** `lanesFor`'s item 2 (the pyramid, for a view longer than
`EXACT_MAX_S`): the level chosen is the largest with `binSamples * dt <= (span /
bins) / 2`; each display bin equals the minimum/maximum of the chosen level's
bins that overlap it (the `floor`/`ceil` index range of `lanesFor`'s pyramid
branch); `binMs` is that level's bin width in ms; `gap` is `false` when a level
fits.

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
level is too coarse, and `statusText` reads `result.onRaster` for a file without
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

#### `test_totals_double_with_the_gradient_values`

**Checks:** The model is linear in the gradient: the whole-file totals of the tables with every
`grad_value` doubled agree, within 1e-12 of the peak, with twice the totals of the tables.

**How:** Builds a 60-block pseudo-random model (`buildPnsTables(60, 29,
{durationOptionsDt: [15, 25], noEventProb: 0.3})`), decodes it and a copy with every
`grad_value` doubled, collects the whole-file totals (`collectPlainRecursion`) of both, and
compares the second with twice the first with `assertWithinPeakTol` at `1e-12`. It also checks
that the peak is above 0.

**Assumptions:** None beyond the file's assumptions.

#### `test_totals_are_in_hz_per_t_of_the_samples_in_hz_per_m`

**Checks:** The totals of the model are in Hz/T: they equal the brute force of the test file,
which reads the tables as they are (Hz/m) and divides by no gamma, and they
are far above 1 (the size of a fraction of the limit) for these gradients.

**How:** Builds a 40-block model, collects the plain recursion and the brute force, compares
them with `assertWithinPeakTol` at `1e-12`, and checks that the peak of the brute force is
above 1000.

**Assumptions:** None beyond the file's assumptions.

#### `test_decode_refuses_a_threshold_that_is_not_a_number_above_zero`

**Checks:** `PnsLanes.decode` throws, with the name of the argument in the message, for a
`threshold` of 0, -1, NaN, Infinity or undefined.

**How:** Decodes a 5-block model with each bad value and expects the error with
`assert.throws` and a pattern.

**Assumptions:** None beyond the file's assumptions.

#### `test_lanes_for_percent_is_100_times_the_total_over_the_threshold_of_the_model`

**Checks:** The lane values of `lanesFor` are percent of the threshold of the model: a model
with twice the threshold (same tables, same stored level) gives half the values, for the exact
samples, the exact bins and the stored level of the pyramid.

**How:** Takes the `buildPyramidModel(8)` model and a shallow copy with `threshold` doubled,
calls `lanesFor` on both for a 1 ms view with 812 bins, a 5 ms view with 10 bins and a 20 s
view with 100 bins, flattens the values of the segments and compares the second with the
half of the first with `assertWithinPeakTol` at `1e-14`. It checks that each view has values.

**Assumptions:** None beyond the file's assumptions.

#### `test_percent_is_100_times_the_value_over_the_threshold`

**Checks:** `PnsLanes.percent(v, threshold)` is `100 * v / threshold` (0, 100, 25 and 200 for
exact inputs), and it keeps the order of two values, so a stored float32 bound of the totals is
still a bound of the percents.

**How:** Calls `percent` with exact inputs and checks the results, and with two different
float32 values and one threshold and checks that the percent of the smaller is not above the
percent of the larger.

**Assumptions:** None beyond the file's assumptions.

#### `test_empty_file_has_no_samples_and_no_exact_view_crash`

**Checks:** A file with 0 blocks decodes to `numBlocks = 0`, `numSamples = 0`,
`onRaster = true` (no block ever contradicts it); `exactView` returns an empty
"samples" result rather than throwing or indexing out of bounds; `lanesFor`
returns `{lane: {...meta, segments: []}, exact: true, binMs: null, gap: false,
onRaster: true}` (the "an empty file" case of `lanesFor`).

**How:** Decodes a model from tables where every array (`duration_index`,
`gx`/`gy`/`gz`, all the `grad_*` tables) has length 0, then checks `exactView(0,
1, 10)` gives empty `t`/`total` arrays and `lanesFor` gives exactly the
empty-file result above (`assert.deepEqual` against the literal expected
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
end is always 0 and whose high end is `1.1 * max(100, the largest peak percent)`: the
same `[0, 110]` the old PNS card's chart used for a peak at or below the limit, widened
to show a peak above it. With several entries (targets) there is one domain: the peak of
each entry is a percent of its own threshold, and the largest wins.

**How:** Calls `PnsLanes.laneMeta` with a list of entries (`target`, `color`, `threshold`
and `summary.peak`) and checks each fixed field. For `domain`, it calls `laneMeta` with one
entry of peak 0.5, 1.0 and 1.5 times the threshold and checks the low end is exactly 0 and the
high end is within 1e-9 of 110, 110 and 165 (a tolerance, since `1.1 * 100` is not exact in
float64). It calls it with two entries, 3 MHz/T of a 12 MHz/T threshold (25 %) and 3 MHz/T of
a 1 MHz/T threshold (300 %), in both orders, and checks the domain is 330.

**Assumptions:** None beyond the file's assumptions.

#### `test_run_marks_are_the_runs_in_ms_in_the_color_of_the_target`

**Checks:** `PnsLanes.runMarks(runs, color)` gives one `{lo, hi, color}` for each run, with
`lo` and `hi` the start and end of the run in ms and the color token of the target, and an
empty list for no run (a run of one sample has `lo == hi`).

**How:** Calls it with two runs in seconds (one of one sample) and with empty arrays, and
compares with `assert.deepEqual`.

**Assumptions:** None beyond the file's assumptions.

#### `test_overlay_has_one_series_for_each_entry_and_the_marks`

**Checks:** `PnsLanes.overlay(meta, entries, results, marks)` gives the lane of `meta` with a
`series` of `{label, color, segments}` for each entry in order (the target name and its color
token, and the segments of its `lanesFor` result), the given `marks` (the same array), no
`segments` of its own and `minmax` only when a result has `minmax`; one entry still gives
`series`, so the tooltip names the target.

**How:** Builds two entries and two hand-made results, calls `overlay` and compares the lane
with `assert.deepEqual` and `assert.strictEqual` (for the marks). It repeats it with results
that have `minmax: true`, and with one entry.

**Assumptions:** None beyond the file's assumptions.

#### `test_peaks_text_gives_the_peak_percent_of_each_target`

**Checks:** `PnsLanes.peaksText(entries)` gives the peak of each target, in percent of its
own threshold to one decimal, with its name, in the order of the entries.

**How:** Calls it with two entries (86.6 % of 42.576 MHz/T, and 3 MHz/T of 12 MHz/T) and
compares the text.

**Assumptions:** None beyond the file's assumptions.

#### `test_status_text_exact`

**Checks:** `PnsLanes.statusText` gives "PNS: exact." whenever `result.exact` is
true.

**How:** Calls `PnsLanes.statusText({exact: true, binMs: null, gap: false,
onRaster: true})` and checks the result.

**Assumptions:**

- A file that is not on the gradient raster never reaches `lanesFor`'s exact
  branch, so passing `onRaster: false` alongside `exact: true` is not a case
  `lanesFor` itself produces; the test only checks that `statusText` reads
  `exact` first.

#### `test_status_text_bins_with_a_sensible_digit_count`

**Checks:** For the minimum/maximum branch, `statusText` formats the bin width to
3 significant figures, not with the module's own float64 precision.

**How:** Calls `PnsLanes.statusText` with `binMs` of 6.15, 393.6 and 1574.4 in
the result object (`gap: false`, `onRaster: true`) and checks the result is
"PNS: minimum and maximum in bins of 6.15 ms.", "...394 ms." and "...1570 ms."
respectively.

**Assumptions:** None beyond the file's assumptions.

#### `test_status_text_gap_adds_the_zoom_in_sentence`

**Checks:** `gap: true` adds a sentence naming `PnsLanes.EXACT_MAX_S` as the span
to zoom in to for exact values; `gap: false` adds nothing.

**How:** Calls `PnsLanes.statusText({exact: false, binMs: 24.6, gap: true,
onRaster: true})` and checks the result is the bins sentence followed by "Zoom
in to `${PnsLanes.EXACT_MAX_S}` s or less for the exact values.". It then calls
the same with `gap: false` and checks the result is only the bins sentence.

**Assumptions:** None beyond the file's assumptions.

#### `test_status_text_off_raster_replaces_the_gap_sentence`

**Checks:** `onRaster: false` in the result gives the "not on the gradient raster"
sentence instead of the "zoom in" sentence (plan section 4.5, item 2), even when
`gap` is also true: zooming in would not reach an exact view for such a file, so
telling the reader to do it would be wrong.

**How:** Calls `PnsLanes.statusText({exact: false, binMs: 24.6, gap: true,
onRaster: false})` and `PnsLanes.statusText({exact: false, binMs: 24.6, gap:
false, onRaster: false})` and checks both give the bins sentence followed by
"The file is not on the gradient raster, so there is no exact view." with no
"zoom in" sentence in either case.

**Assumptions:** None beyond the file's assumptions.

### 2.26 PNS lane against Python (`test_pns_lanes_golden.py`)

The golden test of task 4.5 of `docs/plans/diagram-lanes.md`, for the PNS entries of the
targets (phase 7 of `docs/plans/pulseq-checks-implementation.md`): the browser module
`PnsLanes` (`src/pulseq_reports/assets/pns_lanes.js`) against the Python
`pns_levels.pns_levels` pipeline, as `test_seq_lanes_golden.py` checks `SeqLanes`
against a Python reference. `_run_golden` runs the checks of one target on one sequence
(`run_checks`, the analysis `pns.safe.levels`), builds the real diagram card with the target
and the matrix, writes its tables and the first entry of `file.pns` to a JSON file, runs
`tests/js/golden_pns_lanes.js` with Node on it, and reads back the JSON result:
`PnsLanes.decode`, one `exactView` call for the whole file
(forced to the "samples" kind by a bin count far larger than the sample count, so every
sample comes back, never a minimum/maximum reduction), its totals as percent
(`PnsLanes.percent` with the threshold of the entry), and the decoded pyramid
(`model.levels`).

The Python reference (`_python_reference_totals`) is the same pipeline `pns_levels`
itself runs (its own docstring, items 1 to 3), built again independently in this
file, in a single call instead of `pns_levels`'s chunks: `GradientSampler.block_samples`
of gx, gy and gz for the whole file, in Hz/m (no gamma), through pypulseq's
`_safe_gwf_to_pns_chunk` (one chunk, `state=None`, the SAFE parameters of the target via
`pulseq_checks.safe_model.hw_from_dict`), scaled by 0.01 and combined as `sqrt(x^2 + y^2 +
z^2)`: totals in Hz/T. The pinned fork's chunk function does not depend on the chunk size (lean
on pypulseq, decision 6: not tested here). Both pipelines divide by no gamma, so the test
also asserts that `pns_levels(seq).peak_hz_per_t` equals `totals.max()` exactly, as a check
that this file's one-call reference really is `pns_levels`'s own computation, not a second
implementation of PNS. The reference in percent is `100 * totals / threshold`, where the
threshold is `abs(gamma)` of the profile, written in the test and not read from the entry.

#### `test_pns_lanes_exact_view_and_levels_match_the_python_pipeline`

**Checks:** `PnsLanes.decode` and `exactView`, run through Node on one sequence's real
diagram tables and `pns` entry, give the same whole-file PNS in percent of the threshold of
the target, at the same sample times, as the Python `pns_levels` pipeline, within a relative
1e-12 of the peak (plan section 3.5, item 1); the stored level (`pns_levels`'s float32
`level_min_hz_per_t`/`level_max_hz_per_t`, as it reaches the browser, in percent) bounds every
one of those JS exact samples in its own bin (plan section 4.2), within the same relative
1e-12 slack (the stored level comes from Python's chunked SAFE filter, the JS samples from the
block maps -- different code paths over the same model), with no float32 spacing, because the
level is not divided in Python; and each level of the decoded pyramid (`PnsLanes.levels`) is
exactly the minimum/maximum of the 4 bins of the level below it (no rounding: a min/max
reduction of already-float32 values).

**How:** Parametrized over seven cases. Five are for target A (the proton gamma): the three
synthetic builders of `tests/synthetic.py` that have a gradient event (`spin_echo_sequence`,
`gre_sequence`, `arbitrary_gradient_sequence`; the empty sequence has no PNS bins to compare); a
"border" sequence of two extended trapezoids whose gradient is not zero at the block
junction (`synthetic.border_sequence()`, in `tests/synthetic.py`); and a repeating sequence of
225 blocks (45 TRs of `gre_sequence`'s 5 blocks each), more than `3 * PnsLanes.GROUP_BLOCKS`
(192), so the test crosses more than 3 of the JavaScript block map's checkpoint groups. Two are
for target C, whose gamma is negative (`spin_echo_sequence` and `gre_sequence`), so the
threshold is the magnitude of its gamma. The sodium case of the earlier version is gone: the
model runs on samples in Hz/m, so the gamma of the sequence does not enter, and the case would be
the proton case.

For each case: `_run_golden` makes the matrix and the card data and runs
`golden_pns_lanes.js`. The test checks that the threshold of the entry is `abs(gamma)` of the
profile; that the chunked peak of `pns_levels` equals the maximum of the reference exactly and
the peak of the entry; that the JS sample times equal `(k + 0.5) * dt` with exact array
equality; the JS percent against the reference percent with `max(|diff|) <= 1e-12 * peak`; the
stored level that reached JS against the one of `pns_levels` with exact equality; each
stored bin's level, as percent, against the min/max of the JS samples in that bin, with the
same tolerance; and the pyramid level by level, with exact equality, against the level below
it.

**Assumptions:**

- `golden_pns_lanes.js`'s `t0`/`t1`/`bins` (`-1.0`, `numSamples * dt + 1.0`,
  `numSamples * 2 + 16`) force `exactView`'s "samples" kind for the whole file: the
  range covers every sample regardless of the file's own duration (`sampleRangeFor`
  clamps to `[0, numSamples - 1]`), and the bin count is always more than half the
  sample count.
- All the sequences are on the gradient raster (`PnsLanes.exactView` refuses a file
  that is not, and `GradientSampler.block_samples` raises for it); the test asserts
  `onRaster` is `true` as a guard, not as its own coverage goal (off-raster PNS is
  `pulseq-analysis`'s concern, per `docs/plans/diagram-lanes.md` section 4.1, item
  3).
- The diagram tables have the gradient values in Hz/m, as the Python pipeline reads them, so the
  model needs no factor.

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
(`Number(peak.toPrecision(3)).toString()`) that `ChartMath.sig3` computes, which
`ChartMath.fmt`, `GLanes.laneMeta` and `PnsLanes.statusText` share.

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
the order those pairs were first published. `watchSubscribers(topic, fn)` calls
`fn(count)` at once with the number of subscribers of a topic, then each time that
number changes, and returns a function that stops the watch (a card shows a request
button only while a card subscribes to the request). `PulseqReport.publish`,
`PulseqReport.subscribe` and `PulseqReport.watchSubscribers` are the one bus the page
itself uses; `PulseqReport.createMessageBus`
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

#### `test_watch_subscribers_calls_at_once_with_the_current_count`

**Checks:** `watchSubscribers(topic, fn)` calls `fn` at once with the number of
subscribers that the topic has now (0 for a topic that no one subscribed to), and
counts only the subscribers of the watched topic.

**How:** Watches a topic of a fresh bus with no subscriber and checks the calls are
`[0]`. Subscribes two handlers to the topic and makes a second watch, which is called
with `[2]`. Subscribes a handler to another topic and checks the first watch did not
get a call for it (its calls are `[0, 1, 2]`).

**Assumptions:** None beyond the file's assumptions.

#### `test_watch_subscribers_calls_after_a_subscribe_and_after_an_unsubscribe`

**Checks:** A watch is called with the new count each time a subscriber is added
or removed, and a second call of the same unsubscribe function is not a change.

**How:** Watches a topic, subscribes two handlers, unsubscribes the first (twice),
then the second, and checks the watch's calls are `[0, 1, 2, 1, 0]`.

**Assumptions:** None beyond the file's assumptions.

#### `test_a_stopped_watch_is_not_called_again`

**Checks:** The function that `watchSubscribers` returns stops that watch (a second
call of it does nothing), and does not stop another watch of the same topic.

**How:** Makes two watches of one topic, stops the first (twice), subscribes a
handler, and checks the stopped watch has only its call at once (`[0]`) and the
other has `[0, 1]`.

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
pypulseq, with the builders of `tests/rf_sequences.py` (shared with
`test_rf_profile_card.py`) or the ones in the test file. The RF raster is 5 µs (3 µs in
the interval test, 2.5 µs in one part of the as-played test), so a 1.5 ms sinc has 300
samples and the whole file runs in about 2 s. The expected values come from closed forms
(trapezoid areas and means, the amplitude of a block pulse), from `rf_sim.spin_domain`
called directly on points made in the test, or from the definitions of the plan written
out with numpy.

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
helper `newSeq`: RF rows (the columns of `cards.rf_profile._rf_table`, made by
`rfTables`), gradient events in Hz/m (as the diagram tables keep them), ADC events and blocks. `build` returns a fake sequence view
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
  tests the real one); the fake RF table has the columns of `_rf_table` (section 2.34
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

**Assumptions:** The amplitude the module reads is the table value in Hz/m; the test uses
that value for the hand means.

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

**How:** The RF table of `spinEcho("gy")` with a hand-made entry (it has no `name`,
as the entry of `_rf_profile_data` has none); a copy without the `center` column; a copy
whose `dt` column has one value.

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
profile card file entry (`cards.rf_profile._rf_profile_data`, with the RF
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
  `cards.rf_profile._rf_table`, so the two Python computations already agree
  bit for bit before either reaches JavaScript.
- **The pulse key partition**: a Python key is a tuple and a JavaScript key
  is a string, so the test never compares them by value. Instead, every
  block it asks about builds a bijection between the two representations
  and asserts that the bijection is never many-to-one on either side --
  "the partition of the RF blocks by key must be the same".
- **Float rounding of the same arithmetic** (relative 1e-12 of the largest
  value of the array, or of the scalar itself): the signal (`sigRe`,
  `sigIm` against `signal_hz`), the interval gradients (JavaScript
  reads the diagram table's Hz/m as it is, as Python reads pypulseq's Hz/m),
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
section 4.5, items 1 and 2; task 5.3, items 1 to 7): `_rf_table` (the RF table of the
sequence, its pools and its label check), `_rf_profile_data` (the file entry, labeled or
not) and `rf_profile_card` (the options, the checks and the body). Each test builds its own
sequences with pypulseq, with the same helpers as `test_rf_profiles.py`, from
`tests/rf_sequences.py`. This card copies values from `rf_profiles` and `diagram_data`,
so most checks compare with `==` or `np.array_equal` (exact); a comparison that is not
exact says why.

#### `test_rf_table_matches_hold_samples_and_definitions`

**Checks:** `_rf_table`'s dtypes are those of its column table; after encoding and
decoding (`pulseq_analysis.series.encode_array`/`decode_array`), each dense RF index's pool
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
`_rf_table` itself reads, so the comparison is exact.

**Assumptions:**

- `hold_samples` and `pp.calc_rf_center` are correct: `pulseq-analysis` and pypulseq
  test them. This test checks how `_rf_table` reads and encodes their results.

#### `test_rf_table_shares_one_shape_for_an_rf_spoiled_gre`

**Checks:** An RF-spoiled GRE gives more than one dense RF index, one shape in the pools
(every `shape_at` is 0, and `shape_re`/`shape_im` hold exactly one shape's samples), and
one `key` value, because the pulse key excludes the phase offset. The same GRE with two
slices (two frequency offsets) gives two `key` values and still one shape.

**How:** `_gre(24, rf_spoiling=True)` (a new phase offset each TR) and
`_gre(1, slices=(-5e-3, 5e-3))` (two frequency offsets, no spoiling).

**Assumptions:** None.

#### `test_rf_table_of_a_sequence_without_rf_is_empty`

**Checks:** A sequence without RF gives every `_rf_table` column length 0.

**How:** A sequence with one trapezoid and one delay block, no RF.

**Assumptions:** None.

#### `test_rf_table_raises_without_labels`

**Checks:** `_rf_table` raises `ValueError` (matching "rf_uses_labeled") when an RF event
has no use label, because `use` has no index for "undefined".

**How:** A block pulse added without a `use` argument (the pypulseq default,
"undefined").

**Assumptions:** None.

#### `test_pulse_list_and_file_entry_keys`

**Checks:** `_rf_profile_data`'s `pulses` equals `dataclasses.asdict` of
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

**Checks:** `rf_profile_card` raises `ValueError` for: `views` without `"profile"`; an
unknown view; a view given twice; `plane` with one name, with the same name twice, or
with an axis that is not `x`, `y` or `z`; and `extent_m` of 0, −1, NaN or infinity.

**How:** A parametrized test over the 10 cases, each with one sequence and the one bad
keyword argument.

**Assumptions:** None.

#### `test_rf_profile_card_refuses_rotations`

**Checks:** A sequence with the Pulseq rotation extension makes `rf_profile_card` raise
`NotImplementedError`, as the other gradient cards do.

**How:** A GRE sequence with a `rotation_library` attached by hand, the way pypulseq
draft PR #372 stores a rotation in memory (as `test_extensions.py` does).

**Assumptions:** None.

#### `test_two_cards_on_one_page_have_unique_ids`

**Checks:** Two RF profile cards on one page, with different `card_id`s but the same
sequence, give a page with no `id="..."` value used twice.

**How:** `page.render_page` with two cards (`card_id` "rf-a"/"rf-b"); every `id="..."`
value in the result is found with a regular expression and checked for duplicates.

**Assumptions:** None.

#### `test_unlabeled_sequence_gets_a_note_and_no_profiles`

**Checks:** A sequence with one unlabeled RF event (and one labeled event, so the counts
are "1 of 2") raises nothing: its data is only `labeled` False and the counts, and the
body has the note (the `status bad` paragraph) with the counts and no "Show" button. A
labeled sequence has its full entry and no note.

**How:** One card for a sequence of one labeled pulse, and one for a sequence of one
labeled and one unlabeled pulse (`make_block_pulse` with no `use`).

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
card body says "No RF pulses.".

**How:** A sequence with one trapezoid and one delay block, no RF.

**Assumptions:** None.

#### `test_page_has_the_card_script_and_the_elements_it_reads`

**Checks:** The card script (`assets/cards/rf-profile.js`) is DOM code, which the
library tests only in a browser check (decision 10 of `docs/plans/pulseq-reports.md`);
this test holds the Python half to what the script reads. On a page with a diagram card
and this card, for a spin echo: the page has the card script one time
(`PulseqReport.registerCard("rf-profile"` and the text of
`page.card_asset("rf-profile")`); the card data has `format` 2 and exactly the keys
`format`, `views`, `plane`, `extent_m` and `file` (no `diagram_card_id`); the body has
the status line with `aria-live="polite"`, the empty pulses element, and the combined
element, hidden, whose first paragraph is the primary echo note (the script hides that
paragraph above a period without a combined profile) and which holds the empty combined
body. The "Show" buttons are exactly one for each distinct pulse, in order, with
`data-block` the pulse's first block and no `data-file`.

**How:** `page.render_page` with `diagram_card` (a full window) and `rf_profile_card`;
regular expressions on the body for the elements and the buttons, compared with the card
data's `pulses`.

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

### 2.36 Card registry (`test_registry.py`)

`test_registry.py` tests `registry.py` (`docs/plans/public-api.md`, section 4.4, items 3 to
6 and 10): `discover` and `build_cards`. The tests use the test plugin in
`tests/plugin_card.py`, which is not a test file. Its spec makes a card that reads the
options that it declares and shows their values in `data-` attributes of its body. The
`add_specs` fixture adds specs to the ones that `discover` finds, by replacing
`registry._load_entry_points`, so every spec goes through the same checks as an entry
point. The first tests select the cards of the test plugin with `cards=`, so they do not
depend on the library's own cards. The tests from `test_discovery_finds_the_nine_library_cards_in_their_order`
on use the library's nine cards, which are the entry points of `pyproject.toml`: the
installed project must have them (`uv sync`).

#### `test_plugin_card_is_in_the_report_in_its_order_with_its_assets_once`

**Checks:** The plugin's card is in the cards that `build_cards` makes, between a card with
a lower `order` and a card with a higher `order` that were added after it; the card shows
the value of the shared option `max_rows` that the caller gave, and its default when the
caller gives none. On the page of the three cards, the cards' one script and one CSS text
each appear one time.

**How:** Two more specs of the plugin (`order` 1 and 99999) are added in the opposite
order, and all three read `options.max_rows`. `render_page` gets the three cards.

**Assumptions:**

- `render_page` includes each distinct text of `Card.scripts` and `Card.css` one time:
  `test_page.py` tests it. This test checks that the assets of a card reach the page
  through `build_cards`.

#### `test_two_specs_with_one_name_raise_and_no_card_is_built`

**Checks:** Two specs with one name make `build_cards` raise `ValueError` with the names of
both entry points, before any card is built.

**How:** A second spec with the name of the plugin, and a spec whose `build` records that it
ran.

**Assumptions:** None.

#### `test_two_options_with_one_name_raise`

**Checks:** Two cards that declare options with one name, where the options are not the
same object, make `discover` raise `ValueError` with the names of both cards and of the
option.

**How:** The second option is `dataclasses.replace` of `options.max_rows`: a different
object with the same fields.

**Assumptions:** None.

#### `test_a_spec_reads_only_the_options_it_declares`

**Checks:** `ReportContext.option` raises `ValueError` for an option that no selected spec
declares. In a report, a card whose spec does not declare an option that another selected
card declares is an error card that names the option, in its `error` and in its body, and the
other card is built, with no `error`.

**How:** A spec that declares no option and reads `options.max_rows`, with the plugin's
card, which declares it.

**Assumptions:** None.

#### `test_a_card_that_raises_is_an_error_card_and_the_others_are_built`

**Checks:** When the `build` or the `when` of a spec raises (here `NotImplementedError`,
the error of a card that refuses a sequence), `build_cards` makes an error card in its
place: the spec's name as `id`, the title "<name>: error", the message with the error's
type name in the body with its HTML characters escaped, and the unescaped message with the
error's type name in `error`. The error with its traceback goes to the logger
`pulseq_reports`, one time. The other card is built, with no `error`, and a page of the two
cards renders.

**How:** The message of the error has `<b>`, so the test can see the escape. The test reads
the logger's records with `caplog`, and checks that the record holds the error object.

**Assumptions:** None.

#### `test_cards_and_skip_select_cards`

**Checks:** `cards` keeps the named cards, in the order of their specs and not in the order
of the names; `skip` leaves out the named cards, with `cards` and without it.

**How:** Three cards of the test plugin with different `order` values, and the cards of the
installed entry points, if any: the last two checks look only at the test card.

**Assumptions:** None.

#### `test_an_unknown_card_name_raises`

**Checks:** A name in `cards`, and a name in `skip`, that no spec has raises `ValueError`
with the name.

**How:** One known and one unknown name, for each argument.

**Assumptions:** None.

#### `test_an_option_of_no_selected_card_raises`

**Checks:** An option that no selected card declares raises `TypeError`, when no card
declares it, and when the card that declares it is not selected (by `cards` or `skip`).
When the card is selected, the option reaches it.

**How:** `periodic`, declared by one added spec.

**Assumptions:** None.

#### `test_when_can_depend_on_the_topics_of_the_selected_cards`

**Checks:** A card whose `when` is `ctx.publishes("anchor")` (and, in the second case,
`ctx.subscribes("goto")`) is built when a selected card declares the topic, and is not
built when none does.

**How:** Two specs: one with the `when`, and one that declares the topic. The test selects
both, and then the first with a card that does not declare the topic.

**Assumptions:** None.

#### `test_discovery_finds_the_nine_library_cards_in_their_order`

**Checks:** `discover` finds the nine library cards, `timing`, `rf-exposure`, `diagram`,
`rf-profile`, `gradient-spectrum`, `pns`, `gradient-limits`, `definitions` and `blocks`, in
this order, and no other card; their `order` values do not decrease.

**How:** The entry points of the installed project, with no added spec.

**Assumptions:** None.

#### `test_a_card_that_builds_has_no_error`

**Checks:** A card that builds has `error` None.

**How:** `build_cards` for the synthetic spin echo sequence with all the library cards
(the PNS card has no targets, and no card raises for this sequence). The test checks
that the list is not empty and that each card's `error` is None.

**Assumptions:** No library card raises for the synthetic spin echo sequence.

#### `test_without_the_diagram_the_rf_profile_card_is_not_built`

**Checks:** The RF profile card, for a sequence with RF use labels, is not built when it is
the only selected card, and when the diagram is skipped (no selected card publishes `anchor`);
with the diagram selected, both cards are built.

**How:** `build_cards` with `cards=["rf-profile"]`, with `skip=["diagram"]`, and with
`cards=["diagram", "rf-profile"]`, on the spin echo sequence.

**Assumptions:** None.

#### `test_render_page_raises_for_two_diagram_cards`

**Checks:** `render_page` raises `ValueError`, with the topic `sequence`, for two diagram cards:
they are two publishers of a state topic.

**How:** Two `diagram_card` calls for one sequence with different `card_id`s.

**Assumptions:** None.

#### `test_render_page_raises_for_two_cards_that_subscribe_to_goto`

**Checks:** `render_page` raises `ValueError`, with the topic `goto`, for the diagram card and
a second card that subscribes to `goto`: a request topic has at most one card that acts on it.

**How:** A `diagram_card`, and a `Card` with `subscribes=("goto",)`.

**Assumptions:** None.

#### `test_render_page_does_not_check_a_plugin_topic`

**Checks:** `render_page` accepts two cards that publish and subscribe to a topic that
`page.TOPIC_KINDS` does not list.

**How:** Two `Card` objects with the topic `plugin-topic`.

**Assumptions:** None.

#### `test_the_options_of_each_spec_are_the_keywords_of_its_builder`

**Checks:** For each of the nine library cards, each keyword-only parameter of its builder is
an option that its spec declares, except `card_id`, `targets` and `check_results` (the targets
and the matrix of the report) and (for the blocks and gradient limits
cards) `windows`; each option that the spec declares is a keyword-only parameter of the
builder, with the same default as the option (decision 17 of the plan); and the default
`card_id` is the spec's name.

**How:** `inspect.signature` of the nine builders, against the specs from `discover`.

**Assumptions:**

- The `windows` of the diagram card is a positional parameter, so it is not in the keywords.


#### `test_a_report_without_targets_has_no_targets_and_no_check_results`

**Checks:** For a report without `targets` and `check_results`, the context that a card's
`build` gets has `targets == ()` and `check_results` None.

**How:** A spec whose `build` records its `ReportContext` is added with `add_specs`, and
`build_cards` builds it for the spin echo sequence.

**Assumptions:** None.

#### `test_targets_do_not_change_the_cards_that_are_built`

**Checks:** `build_cards` with targets makes the same cards (equal `Card` objects, not only
the same ids) as `build_cards` without targets, but for the cards that use the targets
(`_USE_TARGETS`: `diagram`, `gradient-limits`, `gradient-spectrum`, `pns` and
`rf-exposure`), which are built in both
cases.

**How:** `build_cards` for the spin echo sequence with all the cards, twice without targets
and once with two target profiles. The test checks that the second build without targets
equals the first (so that `Card` equality works for the built cards), and that the build with
targets equals them too, in the cards that do not use the targets.

**Assumptions:** When another card uses the targets, its name goes in `_USE_TARGETS`.

#### `test_the_context_has_the_report_targets_in_order_with_their_colors`

**Checks:** The context of a card has `targets` as a tuple of `ReportTarget`, in the order of
the profiles that the caller gave, with the colors `target-1` and `target-2` and the
`gamma` of each; `check_results` is None when the caller gives none.

**How:** The recording spec; two profiles read from TOML files, the second with the sodium
gamma (the first has no gamma, so the default of pypulseq).

**Assumptions:** None.

#### `test_the_context_has_the_result_matrix_that_the_caller_gave`

**Checks:** `ctx.check_results` is the same object as the `ResultMatrix` that the caller
gave.

**How:** The recording spec; a matrix made directly from the classes of pulseq-checks, with
the names of two profiles, in the same order.

**Assumptions:** None.

#### `test_a_sequence_with_another_gamma_is_accepted`

**Checks:** `build_cards` accepts a `Sequence` built with the sodium gamma (11.262e6) and with a
negative gamma (-11.777e6), and builds the card.

**How:** `pp.Sequence(pp.Opts(gamma=...))`, without blocks, with the plugin card only.

**Assumptions:** None.

#### `test_a_sequence_with_a_gamma_that_is_0_or_nan_raises`

**Checks:** `build_cards` raises `ValueError` when `seq.system.gamma` is 0 or NaN.

**How:** `pp.Sequence(pp.Opts(gamma=...))` for 0 and for `nan`; pypulseq builds both.

**Assumptions:** The check of the gamma happens before any card is built, so the empty
sequence does not matter.

#### `test_more_than_the_most_targets_raise`

**Checks:** `build_cards` raises `ValueError` for more than `MAX_TARGETS` targets.

**How:** `MAX_TARGETS + 1` profiles with different names.

**Assumptions:** None.

#### `test_two_targets_with_one_name_raise`

**Checks:** `build_cards` raises `ValueError`, with the name in the message, for two targets
with one name.

**How:** Two profiles read from TOML files with the name `a`.

**Assumptions:** None.

#### `test_a_target_that_is_not_a_target_profile_raises`

**Checks:** `build_cards` raises `TypeError` for a target that is not a `TargetProfile`.

**How:** `targets=["a.toml"]`.

**Assumptions:** None.

#### `test_check_results_with_other_target_names_raise`

**Checks:** `build_cards` raises `ValueError` when the target names of `check_results` are not
the names of `targets` in the same order: a different name, a different order, a missing
target, an extra target, a matrix with targets and no targets given, and targets given with a
matrix that has none.

**How:** One parametrized case for each; the matrix is made directly from the classes of
pulseq-checks, with no results.

**Assumptions:** None.

#### `test_check_results_that_are_not_a_result_matrix_raise`

**Checks:** `build_cards` raises `TypeError` for a `check_results` that is not a
`pulseq_checks.ResultMatrix`.

**How:** `check_results` is a dict, with one valid target.

**Assumptions:** None.

#### `test_no_card_is_built_when_the_inputs_raise`

**Checks:** When the targets and `check_results` do not agree, `build_cards` raises before it
builds any card.

**How:** The recording spec, a profile `a` and a matrix with the target `b`. After the
`ValueError`, the list of contexts that the build recorded is empty.

**Assumptions:** None.

#### `test_check_result_units_accepts_a_matrix_with_hz_per_t_and_a_matrix_without_pns`

**Checks:** `registry.check_result_units` returns without an error for a matrix whose PNS
series have the unit `"Hz/T"`, and for a matrix with no analysis result.

**How:** The test makes the matrix of the analysis `pns.safe.levels` for the example target A
with `run_checks`, and a matrix with no results (the `make_matrix` fixture), and calls the function
for each.

**Assumptions:** None.

#### `test_check_result_units_raises_for_a_pns_series_in_the_unit_1`

**Checks:** `registry.check_result_units` raises `ValueError`, with "Hz/T" in the message, for
a matrix whose `pns.safe.levels` series have the unit `"1"`: the form of pulseq-checks
`v0.1.0rc4` (decision P39 of the design).

**How:** The test makes the matrix with `run_checks`, writes it as JSON, changes the unit of each series
of each analysis result to `"1"`, reads it with `ResultMatrix.from_json` (the older form
reads), checks that the result has series, and expects the error.

**Assumptions:** None.

#### `test_build_cards_raises_for_a_pns_series_in_the_unit_1_and_builds_no_card`

**Checks:** `build_cards` raises `ValueError` with "Hz/T" in the message for the matrix of the
previous test, before it builds any card.

**How:** The recording spec, the target A and the matrix with the unit `"1"`. After the
`ValueError`, the list of contexts that the build recorded is empty.

**Assumptions:** None.

#### `test_build_cards_accepts_a_matrix_with_hz_per_t`

**Checks:** `build_cards` builds the cards for a matrix whose PNS series have the unit
`"Hz/T"`.

**How:** The recording spec, the target A and the matrix of `run_checks`. The recorder has seen
one context.

**Assumptions:** None.

### 2.37 Command line (`test_cli.py`)

These tests call `cli.main(argv)` in the test process, with a `.seq` file that `seq.write` wrote from a synthetic sequence. `FAST` is the cards `gradient-limits,blocks,gradient-spectrum`.

#### `test_the_page_of_the_command_line_equals_the_page_of_build_cards`

**Checks:** The page that `main` writes equals `render_page` of `build_cards` for the same file read back, with the file name as title, "pulseq-reports <version>" as subtitle, and the same option value; the status is 0.

**How:** `main` with `--max-rows`; the expected page from `Sequence.read`, `build_cards` and `render_page`, compared as text.

**Assumptions:** None.

#### `test_the_default_output_is_the_stem_in_the_current_directory`

**Checks:** Without `-o`, the page of `se.seq` is `se.html` in the current directory.

**How:** `monkeypatch.chdir` into an empty directory.

**Assumptions:** None.

#### `test_two_files_give_two_pages_in_the_output_directory`

**Checks:** Two files and `-o DIR` give `<stem>.html` for each in `DIR`, and `DIR` is made when it does not exist.

**How:** A spin-echo and a GRE file; a nested output directory.

**Assumptions:** None.

#### `test_two_files_with_one_stem_exit_1_and_write_no_page`

**Checks:** Two files in different directories with one stem exit 1, stderr names the stem, and the output directory is not made.

**How:** Two `same.seq` files.

**Assumptions:** None.

#### `test_cards_and_skip_select_the_cards`

**Checks:** `--cards` gives the page of `build_cards` with those cards, and `--skip` removes a card from them.

**How:** Page equality with `build_cards(cards=...)`.

**Assumptions:** None.

#### `test_an_unknown_card_name_exits_1`

**Checks:** An unknown name in `--cards` or `--skip` exits 1, stderr names it, and no page is written.

**How:** Parametrized over the two flags.

**Assumptions:** None.

#### `test_a_file_with_no_error_card_exits_0`

**Checks:** A file whose cards build without an error card exits 0.

**How:** `--cards` with `FAST`, for the spin-echo sequence.

**Assumptions:** None.

#### `test_a_page_with_an_error_card_exits_1_and_the_page_is_written`

**Checks:** A page with an error card (a card whose build raises) gives status 1, and the page is still written, with the timing card and the error card, and the error's type name.

**How:** `--card-module plugin_card:BROKEN` (the spec in `tests/plugin_card.py` whose build raises `NotImplementedError`) with `--cards timing,plugin-broken`. The test reads the page back and looks for the two card ids and `NotImplementedError`.

**Assumptions:** None.

#### `test_an_unreadable_file_exits_1_and_the_good_file_has_its_page`

**Checks:** A text file that is not a sequence and a missing file give status 1 and are named on stderr, and the page of the good file in the same call is written.

**How:** Three files in one call.

**Assumptions:** None.

#### `test_card_module_adds_the_card_and_its_option`

**Checks:** `--card-module plugin_card:SPEC` adds the test plugin's card and the flag `--max-rows`: the page has the card with the value, and `discover` does not find the spec after `main` returns.

**How:** `tests/` is on `sys.path`, as for the other tests that import `plugin_card`.

**Assumptions:** The plugin module imports from `tests/`, which pytest puts on `sys.path`.

#### `test_card_module_with_a_bad_spec_exits_1_and_writes_no_page`

**Checks:** A spec given twice (two cards with one name), an attribute that does not exist, a module that does not exist, a label with no attribute, and an attribute that is not a `CardSpec` each exit 1 and name the label or the card on stderr; no page is written.

**How:** `main` for each case.

**Assumptions:** None.

#### `test_each_option_of_the_discovered_specs_has_its_flag_in_the_parser`

**Checks:** The `--help` text has the flag of each option of the discovered specs (with the test plugin added), and the `--no-` form of each `bool` flag.

**How:** `main(["--help"])` returns 0; the flags come from `Option.flags()`.

**Assumptions:** None.

#### `test_a_toml_and_a_json_config_file_give_the_page_of_the_same_flags`

**Checks:** A `.toml` and a `.json` config file with the same values (max_rows, cards) give the page that the same values as flags give.

**How:** Page equality.

**Assumptions:** None.

#### `test_a_flag_overrides_the_config_file`

**Checks:** `--max-rows` overrides `max_rows` of the config file: the page equals the page of flags with the flag's value.

**How:** Page equality.

**Assumptions:** None.

#### `test_a_config_file_with_an_unknown_key_exits_1`

**Checks:** A key that no option has exits 1, stderr names the key, and no page is written.

**How:** A misspelled `max_rowz`.

**Assumptions:** None.

#### `test_a_config_file_with_another_suffix_or_a_bad_value_exits_1`

**Checks:** A `.yaml` file, a value of the wrong type, and a missing file each exit 1 with the file named on stderr.

**How:** `main` for each file.

**Assumptions:** None.

#### `test_a_config_key_of_a_skipped_card_is_ignored`

**Checks:** `max_rows` in the config file, with `--cards timing`, exits 0 and gives the page of `build_cards` for the timing card.

**How:** Page equality.

**Assumptions:** None.

#### `test_a_flag_of_a_skipped_card_exits_1_and_names_the_flag_and_the_card`

**Checks:** `--max-rows 5` with `--cards timing` exits 1, stderr names `--max-rows` and the card `blocks`, and no page is written.

**How:** None.

**Assumptions:** None.

#### Helpers for the target tests

The tests of the targets use the profiles `tests/profiles/example_a.toml` (limits above the
peaks of the synthetic spin echo) and `example_b.toml` (limits below them). The fixture `spy`
replaces `cli.build_cards` and `cli.run_checks` with functions that record their arguments and
call the real ones. `fake_checks` records the same, but `run_checks` gives a matrix with no
results and the names of the targets (or raises `RunError` for the file names in
`fake_checks.raises`). `no_checks` makes `cli.run_checks` fail the test when it is called.
The error tests check status 1, that no page is written, and that stderr has the prefix
`pulseq-report:`; they do not check the text of a message, except that a message names a file.

#### `test_targets_reach_build_cards_with_their_matrix_and_the_checks_run_once`

**Checks:** `--target A --target B` gives `build_cards` the two profiles in order and a
`ResultMatrix` with the two target names; `run_checks` runs once, for the file, with the two
profiles, `select=None`, `required=None` and `fast_only=False`; the status is 0 and the page is
written.

**How:** The `spy` fixture, with the real `run_checks` (all checks), the card `timing`.

**Assumptions:** The cards do not use the targets yet, so the page does not show them; the
test reads the arguments of `build_cards`.

#### `test_two_files_run_the_checks_once_for_each_file`

**Checks:** With two files, `run_checks` is called one time for each file, in order, and each
`build_cards` call gets a matrix with one target.

**How:** `fake_checks`, the synthetic spin echo and gradient echo files, one `--target`.

**Assumptions:** None.

#### `test_the_analyses_of_the_run_follow_the_selected_cards`

**Checks:** `run_checks` gets `analyses=("pns.safe.levels",)` when the `pns` card is selected
and when the `diagram` card is selected with `--pns-lane`, `("gradient.spectrum",)` when the
`gradient-spectrum` card is selected, both (in that order) when the `gradient-spectrum` and
`pns` cards are selected, and `()` with only `timing` and with `diagram` without `--pns-lane`.

**How:** Six parametrized runs with `fake_checks` and `--target A`.

**Assumptions:** The status of each run is 0 with the fake matrix.

#### `test_a_check_config_gives_the_targets_in_its_order_and_the_checks`

**Checks:** `--check-config` gives the targets of the configuration, in its order (B, then a
profile in a sub-directory, relative to the file), and its `select`, `required` and
`fast_only` to `run_checks`; `build_cards` gets the same targets.

**How:** `fake_checks`, a config in `tmp_path` and copies of the profiles. The expected values
are those of `read_check_config` of the same file, and `select` and `fast_only` are also
compared with the literal values.

**Assumptions:** None.

#### `test_check_results_give_build_cards_the_matrix_and_run_no_check`

**Checks:** `--check-results FILE.json` gives `build_cards` a matrix equal to the matrix in
the file (same JSON text, same number of results, same target names), calls `run_checks` not
at all, and the page is written.

**How:** A real matrix from `run_checks` for the synthetic file and the two profiles, with
the check `gradient.amplitude.axis`, written with `to_json`. `no_checks` and `spy`.

**Assumptions:** The matrix has results (the test checks it).

#### `test_a_target_and_a_check_config_together_exit_1`

**Checks:** `--target` with `--check-config` exits 1 and writes no page.

**How:** `_fails` with a valid config and a valid profile.

**Assumptions:** None.

#### `test_check_results_without_targets_exit_1`

**Checks:** `--check-results` with no target exits 1 and writes no page.

**How:** `_fails`, with a valid result file.

**Assumptions:** None.

#### `test_check_results_with_two_files_exit_1`

**Checks:** `--check-results` with two `.seq` files exits 1 and writes no page.

**How:** Two files, a valid result file and a target; the output directory is not made.

**Assumptions:** None.

#### `test_a_missing_result_file_exits_1_and_names_it`

**Checks:** A result file that does not exist exits 1, writes no page, and the message has
the file name.

**How:** `_fails` with a path that does not exist.

**Assumptions:** None.

#### `test_a_result_file_that_is_not_a_matrix_exits_1`

**Checks:** A result file that `ResultMatrix.from_json` refuses exits 1, writes no page, and
the message has the file name.

**How:** The file holds `{"a": 1}`.

**Assumptions:** None.

#### `test_a_result_file_with_a_pns_series_in_the_unit_1_exits_1_and_writes_no_page`

**Checks:** A result file of the form of pulseq-checks `v0.1.0rc4` (a `pns.safe.levels` series
with the unit `"1"`), which `ResultMatrix.from_json` reads, exits 1, runs no check, writes no
page, and the message has the file name and "Hz/T" (decision P39 of the design).

**How:** The test makes the matrix for target A with `run_checks`, changes the unit of each
series in its JSON to `"1"`, writes the file and runs the command with `--target` and
`--check-results`. The `no_checks` fixture makes the test fail if `run_checks` is called.

**Assumptions:** None.

#### `test_a_missing_profile_exits_1`

**Checks:** A profile that does not exist exits 1, writes no page, and the message has the
file name.

**How:** `_fails` with a path that does not exist.

**Assumptions:** None.

#### `test_a_missing_check_config_exits_1`

**Checks:** A check configuration that does not exist exits 1 and writes no page.

**How:** `_fails` with a path that does not exist.

**Assumptions:** None.

#### `test_the_same_profile_twice_exits_1`

**Checks:** Two targets with one name (the same profile twice) exit 1 and write no page.

**How:** `_fails` with `--target A --target A`.

**Assumptions:** None.

#### `test_seven_targets_exit_1`

**Checks:** Seven targets exit 1 and write no page.

**How:** Seven copies of profile A with the names `target 0` to `target 6`, written to
`tmp_path`.

**Assumptions:** None.

#### `test_check_results_for_other_targets_exit_1`

**Checks:** A result file whose targets are not the targets that were given exits 1 and
writes no page.

**How:** A matrix with the target A only, and `--target A --target B`.

**Assumptions:** None.

#### `test_the_targets_key_of_a_config_file_gives_the_targets_of_the_flags`

**Checks:** The key `targets` of a `--config` file (relative paths) gives `run_checks` the
same targets (names and `opts`) as the flags `--target`.

**How:** `fake_checks`; two runs, one with the config file and one with the flags.

**Assumptions:** None.

#### `test_a_config_key_of_the_wrong_type_exits_1`

**Checks:** `targets = "x"`, `check_config = 3` and `check_results = ["x"]` in the config file
each exit 1 and write no page.

**How:** Three parametrized configs in `tmp_path`.

**Assumptions:** None.

#### `test_a_target_flag_replaces_the_targets_key`

**Checks:** `--target` replaces the key `targets` of the config file: only the flag's target
is run.

**How:** `fake_checks`, a config with A and B and `--target B`.

**Assumptions:** None.

#### `test_a_run_error_for_one_file_gives_no_page_for_it_and_the_other_page_is_written`

**Checks:** When `run_checks` raises `RunError` for the first of two files, the status is 1,
that file has no page, the other file's page is written, and the message names the file.

**How:** `fake_checks` with `raises` set to the first file's name.

**Assumptions:** None.

For "without targets the page is the same as before", the existing test
`test_the_page_of_the_command_line_equals_the_page_of_build_cards` (no target flag; the page
equals the page of `build_cards` without targets) covers it.

### 2.38 Package exports (`test_exports.py`)

#### `test_an_exported_name_is_the_object_of_its_module`

**Checks:** Each name that `pulseq_reports` or `pulseq_reports.cards` exports is the same object as the name in the module that defines it, for example `pulseq_reports.build_cards is pulseq_reports.registry.build_cards`.

**How:** Parametrized over the 16 (package, name, module) triples.

**Assumptions:** None.

#### `test_hardware_limits_is_the_class_of_pulseq_checks`

**Checks:** `pulseq_reports.HardwareLimits` is the class `pulseq_checks.HardwareLimits`.

**How:** The test compares the two names with `is`. `HardwareLimits` is not defined in a module of `pulseq_reports`, so it has no row in the parametrized test.

**Assumptions:** None.

### 2.39 Rasters of the file (`test_file_rasters.py`)

`test_file_rasters.py` tests that the analyses use the rasters a `.seq` file
declares in `[DEFINITIONS]`. pypulseq's `Sequence.read` sets
`seq.grad_raster_time` and `seq.rf_raster_time` from the file, but it keeps
`seq.system` at the `Opts` given to `pp.Sequence`: the pypulseq defaults
(10 µs gradient, 1 µs RF) when `pulseq-report` reads a file. The tests write
one file with a 4 µs gradient raster and a 2 µs RF raster (a block pulse, a
trapezoid and a delay, three times) and read it back with `pp.Sequence()`.

**Assumptions for the whole file:**

- A block pulse has two shape points, so `seq_utils.hold_samples` samples it
  at the raster it is given. A pulse with uniform samples that fill its shape
  does not use the raster, and the tests do not use one.
- The shared modules (`grad_limits` and the others that pulseq-checks also
  has) are not tested here.

#### `test_rf_samples_use_the_file_rf_raster`

**Checks:** The RF profile card's RF table (`cards/rf_profile._rf_table`) and
`rf_profiles.block_pulse` sample the 500 µs block pulse at the file's 2 µs RF
raster: a sample duration of 2 µs and 250 samples.

**How:** The test first checks that `seq.system.rf_raster_time` of the read
sequence is not 2 µs, so that the case under test is present. It then checks
the `dt` and `shape_n` columns of the first RF table row, and the `dt_s` and
the sample count of `block_pulse(seq, 0)`. The durations are compared within
1e-12 s.

**Assumptions:** None.

#### `test_rf_exposure_does_not_depend_on_the_reader_opts`

**Checks:** `rf_exposure.rf_exposure` of the file read with `pp.Sequence()` is
exactly equal to that of the same file read with `pp.Sequence(<the file's Opts>)`.

**How:** The test checks that the two reads have different
`seq.system` rasters, then compares the two `RfExposure` results with `==`.

**Assumptions:**

- Before the fix, the differences were small (RF energy at float rounding), so
  only an exact comparison finds them. An exact comparison holds because both
  reads give the same `seq.grad_raster_time`, `seq.rf_raster_time` and events,
  and the analysis reads no other value from `seq.system` that the two `Opts`
  give differently, except `gamma` and `B0`, which are the same in both.

### 2.40 Report targets (`test_targets.py`)

`test_targets.py` tests `targets.py`: `report_targets` makes the `ReportTarget` of each target
profile that the caller gives. The profiles are read with `pulseq_checks.read_profile` from
small TOML files that the `make_profile` fixture of `tests/conftest.py` writes to `tmp_path`.

#### `test_colors_are_target_1_to_target_k_in_order`

**Checks:** The targets keep the order and the profile objects of the input, and their colors
are `target-1` to `target-k` in that order.

**How:** Three profiles named `c`, `a` and `b`; the test compares the `profile` and `color` of
each result.

**Assumptions:** None.

#### `test_no_profiles_give_no_targets`

**Checks:** `report_targets([])` is the empty tuple.

**How:** One call.

**Assumptions:** None.

#### `test_the_most_targets_are_accepted_and_one_more_raises`

**Checks:** `MAX_TARGETS` profiles are accepted, with the colors `target-1` to `target-6`,
and one more raises `ValueError`.

**How:** `MAX_TARGETS + 1` profiles with different names; the first `MAX_TARGETS` and then all.

**Assumptions:** `MAX_TARGETS` is 6; the test builds the expected colors for 1 to 6.

#### `test_two_profiles_with_one_name_raise`

**Checks:** Two profiles with one name raise `ValueError` with the name in the message, also
when other profiles are between them.

**How:** Profiles `scanner`, `third` and a copy of another profile renamed to `scanner` with
`dataclasses.replace`.

**Assumptions:** None.

#### `test_an_item_that_is_not_a_target_profile_raises`

**Checks:** An item that is not a `TargetProfile` raises `TypeError`.

**How:** One profile and one string.

**Assumptions:** None.

#### `test_a_negative_gamma_is_valid_and_kept_signed`

**Checks:** A profile with a negative gamma gives a target whose `gamma` is that negative value.

**How:** A profile with `gamma = -11.777e6` in `[opts]`.

**Assumptions:** None.

#### `test_a_profile_with_no_gamma_gets_the_default_gamma_of_pypulseq`

**Checks:** A profile with `opts` that give no gamma, and a profile with no `opts`, have the
`gamma` of `pp.Opts()`.

**How:** Two profiles; the test compares with `pp.Opts().gamma`.

**Assumptions:** None.

#### `test_a_gamma_that_is_0_or_not_finite_raises`

**Checks:** A profile with a gamma of 0, `inf` or `nan` makes `report_targets` raise
`ValueError` with the name of the profile, also when another profile is valid.

**How:** One profile with `gamma = 0`, `inf` or `nan` (parametrized), and a valid one.

**Assumptions:** None.

#### `test_the_example_profile_with_a_negative_gamma_is_read`

**Checks:** `tests/profiles/example_c.toml` is read, and its target has the gamma `-11.777e6`
(129Xe) and the other `opts` of the example profile (B0 3.0).

**How:** `read_profile` of the file, then `report_targets`.

**Assumptions:** None.

### 2.41 Units (`test_units.py`)

`test_units.py` tests `units.py`: the proton gamma and the conversions from the units of a `.seq`
file (Hz/m, Hz/m/s, Hz) to tesla units.

#### `test_the_proton_gamma_is_the_default_gamma_of_pypulseq`

**Checks:** `GAMMA_1H` of `tests/synthetic.py` equals `pp.Opts().gamma`.

**How:** One equality.

**Assumptions:** The tests use `GAMMA_1H` (decision D17) and the library has no proton constant
since phase 7b, so this test is the one link between the tests and pypulseq.

#### `test_a_negative_gamma_gives_the_value_of_its_magnitude_for_a_number`

**Checks:** For each conversion function, a negative gamma gives exactly the value of the positive
gamma, for a float.

**How:** Each of `hz_per_m_to_mt_per_m`, `hz_per_m_per_s_to_t_per_m_per_s` and `hz_to_ut` is called
with 1234.5 and `-GAMMA_1H`, and with `GAMMA_1H`.

**Assumptions:** None.

#### `test_a_negative_gamma_gives_the_value_of_its_magnitude_for_an_array`

**Checks:** The same as the test for a number, for a numpy array.

**How:** The three functions with an array of three values; `numpy.array_equal` of the two results.

**Assumptions:** None.

#### `test_gamma_entries_with_signed_gammas_give_one_entry_for_each_sign`

**Checks:** For two targets with gamma and -gamma, `gamma_entries` with `signed=True` gives two
entries, each with its own signed gamma and name; with `signed=False` it gives one entry with the
magnitude and both names, in order.

**How:** Two profiles with `GAMMA_1H` and `-GAMMA_1H`, and an empty `Sequence`.

**Assumptions:** None.

#### `test_gamma_entries_share_an_entry_for_targets_with_one_gamma`

**Checks:** Targets with one gamma share an entry, with their names in order; the entries are in
the order of the first target of each gamma.

**How:** Three profiles: sodium, the default gamma, sodium.

**Assumptions:** None.

#### `test_gamma_entries_without_targets_give_the_gamma_of_the_sequence`

**Checks:** Without targets, `gamma_entries` gives one entry with `seq.system.gamma` (signed, or
its magnitude for `signed=False`) and no names.

**How:** A `Sequence` with `gamma=-11.777e6`.

**Assumptions:** None.
