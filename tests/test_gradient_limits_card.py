import dataclasses
import math
import re
from html.parser import HTMLParser
from pathlib import Path

import pypulseq as pp
import pytest
from pulseq_analysis.grad_limits import gradient_limits
from pulseq_checks import read_profile
from synthetic import GAMMA_1H, SYSTEM

from pulseq_reports import page
from pulseq_reports.cards.gradient_limits import gradient_limits_card
from pulseq_reports.markup import fmt
from pulseq_reports.registry import build_cards
from pulseq_reports.targets import report_targets
from pulseq_reports.waveforms import TimeWindow

PROFILES = Path(__file__).parent / "profiles"


class _CardParser(HTMLParser):
    """The tables of a card body, each as its rows of cell texts (the header row first, a
    button's own text left out, white space collapsed), the attributes of each button, the
    `style` of each swatch, and for each table the `data-gamma-entry` and the `hidden`
    attribute of the element around it (None for a table with no such element)."""

    def __init__(self) -> None:
        super().__init__()
        self.tables: list[list[list[str]]] = []
        self.entries: list[tuple[str, bool] | None] = []
        self.buttons: list[dict[str, str | None]] = []
        self.swatches: list[str] = []
        self._cell: list[str] | None = None
        self._in_button = False
        self._entry: tuple[str, bool] | None = None

    def handle_starttag(self, tag, attrs):
        if tag == "div" and "data-gamma-entry" in dict(attrs):
            self._entry = (dict(attrs)["data-gamma-entry"], "hidden" in dict(attrs))
        elif tag == "span" and dict(attrs).get("class") == "swatch":
            self.swatches.append(dict(attrs)["style"])
        elif tag == "table":
            self.tables.append([])
            self.entries.append(self._entry)
        elif tag == "tr":
            self.tables[-1].append([])
        elif tag in ("th", "td"):
            self._cell = []
        elif tag == "button":
            self._in_button = True
            self.buttons.append(dict(attrs))

    def handle_endtag(self, tag):
        if tag in ("th", "td"):
            self.tables[-1][-1].append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "button":
            self._in_button = False

    def handle_data(self, data):
        if self._cell is not None and not self._in_button:
            self._cell.append(data)


def _parse(body_html: str) -> _CardParser:
    parser = _CardParser()
    parser.feed(body_html)
    return parser


def _opts(max_grad=None, max_slew=None, gamma=None) -> str:
    """The lines of the `[opts]` section of a target profile: the limits in mT/m and T/m/s,
    and the gamma (Hz/T), each when it is given."""
    lines = []
    if max_grad is not None:
        lines += [f"max_grad = {max_grad}", 'grad_unit = "mT/m"']
    if max_slew is not None:
        lines += [f"max_slew = {max_slew}", 'slew_unit = "T/m/s"']
    if gamma is not None:
        lines.append(f"gamma = {gamma!r}")
    return "\n".join(lines)


SYSTEM_OPTS = _opts(28, 150)  # the limits of the test system: SYSTEM.max_grad, SYSTEM.max_slew


def _targets(make_profile, *specs):
    """The `ReportTarget` of each `(name, opts)` of `specs`, with `opts` the lines of the
    `[opts]` section (see `_opts`)."""
    return report_targets([make_profile(name, opts) for name, opts in specs])


def _heading(name: str) -> str:
    """The text of the heading of the percent column of the target `name`."""
    return f"% of limit ({name})"


def _where(value: str, block_id: int | None, time_s: float) -> str:
    """The text of a peak or slew cell: the value, and the block and time when there is a
    block."""
    return value if block_id is None else f"{value} (block {block_id}, {time_s * 1e3:.3f} ms)"


def _trapezoid_seq(amplitude: float, rise_time: float = 200e-6, flat_time: float = 1e-3):
    """A one-block sequence with a single x trapezoid, and the trapezoid event itself."""
    gx = pp.make_trapezoid(
        channel="x", amplitude=amplitude, rise_time=rise_time, flat_time=flat_time, system=SYSTEM
    )
    seq = pp.Sequence(SYSTEM)
    seq.add_block(gx)
    return seq, gx


def _hand_computed(amplitude: float, gx) -> dict:
    """Peak (mT/m), max slew (T/m/s) and RMS (mT/m) of `gx`, computed from its own
    parameters."""
    duration = gx.delay + gx.rise_time + gx.flat_time + gx.fall_time
    energy = (
        gx.rise_time * amplitude**2 / 3
        + gx.flat_time * amplitude**2
        + gx.fall_time * amplitude**2 / 3
    )
    return {
        "peak_mt": amplitude / GAMMA_1H * 1e3,
        "slew_t": amplitude / gx.rise_time / GAMMA_1H,
        "rms_mt": math.sqrt(energy / duration) / GAMMA_1H * 1e3,
    }


def test_table_has_axis_rows_and_percents(make_profile):
    """One x trapezoid and one target with limits: the Gx, Gy, Gz and |G| rows hold the
    peak, the percent of the limit, the max slew, its percent, and the RMS, each computed
    by hand from the trapezoid's own parameters. The Gx and |G| peaks are reached at the end of the rise
    (0.2 ms) and the Gx max slew at its start (0 ms), all in block 1; the zero values of Gy
    and Gz have no block."""
    amplitude = 0.4 * SYSTEM.max_grad
    seq, gx = _trapezoid_seq(amplitude)
    values = _hand_computed(amplitude, gx)
    max_grad_mt = SYSTEM.max_grad / GAMMA_1H * 1e3
    max_slew_t = SYSTEM.max_slew / GAMMA_1H
    peak_pct = values["peak_mt"] / max_grad_mt * 100
    slew_pct = values["slew_t"] / max_slew_t * 100
    zero_row = ["", fmt(0.0), fmt(0.0), fmt(0.0), fmt(0.0), fmt(0.0)]
    block_id = next(iter(seq.block_events))
    peak_cell = _where(fmt(values["peak_mt"]), block_id, gx.rise_time)

    card = gradient_limits_card(seq, targets=_targets(make_profile, ("system", SYSTEM_OPTS)))

    expected_table = [
        [
            "Axis",
            "Peak (mT/m)",
            _heading("system"),
            "Max slew (T/m/s)",
            _heading("system"),
            "RMS (mT/m)",
        ],
        [
            "Gx",
            peak_cell,
            fmt(peak_pct),
            _where(fmt(values["slew_t"]), block_id, 0.0),
            fmt(slew_pct),
            fmt(values["rms_mt"]),
        ],
        ["Gy", *zero_row[1:]],
        ["Gz", *zero_row[1:]],
        # There is no gradient on y or z, so the |G| peak and RMS equal Gx's. There is
        # no vector slew, so those cells are the "no value" mark.
        ["|G|", peak_cell, fmt(peak_pct), "—", "—", fmt(values["rms_mt"])],
    ]

    assert card.id == "gradient-limits"
    assert card.title == "Gradient limits"
    assert card.data is None
    assert _parse(card.body_html).tables == [expected_table]


def test_window_gives_rms_over_window_and_over_whole_file(make_profile):
    """With a window, the table has two RMS columns: over the window, and over the
    whole file. The window here is the whole first ramp, so the window RMS differs
    from the whole-file RMS, and both are computed by hand from the trapezoid."""
    amplitude = 0.4 * SYSTEM.max_grad
    seq, gx = _trapezoid_seq(amplitude)
    window = (0.0, gx.rise_time)
    whole = _hand_computed(amplitude, gx)
    # Over the window (just the rising ramp, 0 to amplitude): energy = rise_time *
    # amplitude^2 / 3, divided by the window length (rise_time).
    window_rms_mt = math.sqrt(amplitude**2 / 3) / GAMMA_1H * 1e3
    max_grad_mt = SYSTEM.max_grad / GAMMA_1H * 1e3
    max_slew_t = SYSTEM.max_slew / GAMMA_1H
    window_peak_mt = amplitude / GAMMA_1H * 1e3  # the ramp reaches amplitude at the window edge
    window_slew_t = amplitude / gx.rise_time / GAMMA_1H
    block_id = next(iter(seq.block_events))
    # The peak is at the window end, and the slew segment starts at the window start.
    peak_cell = _where(fmt(window_peak_mt), block_id, gx.rise_time)

    card = gradient_limits_card(
        seq,
        windows=[TimeWindow("ramp", *window)],
        targets=_targets(make_profile, ("system", SYSTEM_OPTS)),
    )

    expected_table = [
        [
            "Axis",
            "Peak (mT/m)",
            _heading("system"),
            "Max slew (T/m/s)",
            _heading("system"),
            "RMS over window (mT/m)",
            "RMS over whole file (mT/m)",
        ],
        [
            "Gx",
            peak_cell,
            fmt(window_peak_mt / max_grad_mt * 100),
            _where(fmt(window_slew_t), block_id, 0.0),
            fmt(window_slew_t / max_slew_t * 100),
            fmt(window_rms_mt),
            fmt(whole["rms_mt"]),
        ],
        ["Gy", fmt(0.0), fmt(0.0), fmt(0.0), fmt(0.0), fmt(0.0), fmt(0.0)],
        ["Gz", fmt(0.0), fmt(0.0), fmt(0.0), fmt(0.0), fmt(0.0), fmt(0.0)],
        [
            "|G|",
            peak_cell,
            fmt(window_peak_mt / max_grad_mt * 100),
            "—",
            "—",
            fmt(window_rms_mt),
            fmt(whole["rms_mt"]),
        ],
    ]

    assert card.body_html.startswith("<h3>ramp</h3>\n")
    assert _parse(card.body_html).tables == [expected_table]


def test_without_a_target_with_limits_the_tables_have_no_percent_columns(make_profile):
    """With no target, and with a target that has no limits, the tables have no "% of limit"
    header and no percent cell: the whole-file table has four columns (axis, peak, max slew,
    RMS), and the table of a window has five (RMS over the window and over the whole file).
    With a target that has limits, each table has the two percent columns more. The cells of
    each row are as many as the headers."""
    seq = _two_trapezoid_seq()
    end = gradient_limits(seq).range_s[1]
    windows = [TimeWindow("first half", 0.0, end / 2), TimeWindow("second half", end / 2, end)]
    no_limits = _targets(make_profile, ("no-limits", "max_grad = 30"))
    limits = _targets(make_profile, ("system", SYSTEM_OPTS))

    for kwargs, columns in (({}, 4), ({"windows": windows}, 5)):
        for targets, percent_columns in (((), 0), (no_limits, 0), (limits, 2)):
            card = gradient_limits_card(seq, targets=targets, **kwargs)

            tables = _parse(card.body_html).tables
            assert len(tables) == len(kwargs.get("windows", [None]))
            for table in tables:
                assert sum(h.startswith("% of limit") for h in table[0]) == percent_columns
                assert [len(row) for row in table] == [columns + percent_columns] * 5


def test_without_a_target_with_limits_the_values_are_those_with_one(make_profile):
    """The cells that the percent columns do not hold are the same with and without a target
    that has limits: the table without it is the table with it, less its percent columns."""
    seq = _two_trapezoid_seq()

    without = _parse(gradient_limits_card(seq).body_html).tables[0]
    targets = _targets(make_profile, ("system", SYSTEM_OPTS))
    with_limits = _parse(gradient_limits_card(seq, targets=targets).body_html).tables[0]

    percent = [i for i, header in enumerate(with_limits[0]) if header.startswith("% of limit")]
    assert percent == [2, 4]
    assert without == [
        [cell for i, cell in enumerate(row) if i not in percent] for row in with_limits
    ]


def test_no_gradients_adds_a_reason_note():
    """A file with no gradient events: the table still has the four rows, all zero,
    and the muted note gives the reason."""
    seq = pp.Sequence(SYSTEM)
    seq.add_block(pp.make_delay(2e-3))

    card = gradient_limits_card(seq)

    assert '<p class="muted">no gradient events in the sequence.</p>' in card.body_html
    assert _parse(card.body_html).buttons == []
    assert card.script is None
    assert card.scripts == ()


def _expected_window_table(seq, window) -> list[list[str]]:
    """The cell texts of the table of one window, from `gradient_limits` for that range, with
    the percent columns of the target "system" (the limits of `SYSTEM`)."""
    result = gradient_limits(seq, window=window)
    max_grad_mt = SYSTEM.max_grad / GAMMA_1H * 1e3
    max_slew_t = SYSTEM.max_slew / GAMMA_1H

    def mt(v):  # Hz/m to mT/m, as the card converts
        return v / GAMMA_1H * 1e3

    def t_per_s(v):  # Hz/m/s to T/m/s
        return v / GAMMA_1H

    rows = []
    for axis, label in (("x", "Gx"), ("y", "Gy"), ("z", "Gz")):
        a = result.axes[axis]
        rows.append(
            [
                label,
                _where(fmt(mt(a.peak_hz_per_m)), a.peak_block, a.peak_time_s),
                fmt(mt(a.peak_hz_per_m) / max_grad_mt * 100),
                _where(fmt(t_per_s(a.max_slew_hz_per_m_per_s)), a.slew_block, a.slew_time_s),
                fmt(t_per_s(a.max_slew_hz_per_m_per_s) / max_slew_t * 100),
                fmt(mt(a.rms_hz_per_m)),
                fmt(mt(result.whole_rms_hz_per_m[axis])),
            ]
        )
    vector_rms = math.sqrt(sum(mt(result.axes[x].rms_hz_per_m) ** 2 for x in "xyz"))
    whole_vector_rms = math.sqrt(sum(mt(result.whole_rms_hz_per_m[x]) ** 2 for x in "xyz"))
    rows.append(
        [
            "|G|",
            _where(
                fmt(mt(result.vector_peak_hz_per_m)),
                result.vector_peak_block,
                result.vector_peak_time_s,
            ),
            fmt(mt(result.vector_peak_hz_per_m) / max_grad_mt * 100),
            "—",
            "—",
            fmt(vector_rms),
            fmt(whole_vector_rms),
        ]
    )
    return [
        [
            "Axis",
            "Peak (mT/m)",
            _heading("system"),
            "Max slew (T/m/s)",
            _heading("system"),
            "RMS over window (mT/m)",
            "RMS over whole file (mT/m)",
        ],
        *rows,
    ]


def _two_trapezoid_seq():
    """Two blocks, an x trapezoid of amplitude 0.2 of the limit and a y trapezoid of 0.5."""
    seq = pp.Sequence(SYSTEM)
    for channel, fraction in (("x", 0.2), ("y", 0.5)):
        seq.add_block(
            pp.make_trapezoid(
                channel=channel,
                amplitude=fraction * SYSTEM.max_grad,
                rise_time=200e-6,
                flat_time=1e-3,
                system=SYSTEM,
            )
        )
    return seq


def test_two_windows_give_two_tables_with_the_values_of_each_range(make_profile):
    """Two windows, one over each trapezoid: the card has one table for each, under an
    `<h3>` of its label, with the values that `gradient_limits` gives for that range."""
    seq = _two_trapezoid_seq()
    end = gradient_limits(seq).range_s[1]
    first = (0.0, end / 2)
    second = (end / 2, end)

    card = gradient_limits_card(
        seq,
        windows=[TimeWindow("first half", *first), TimeWindow("second half", *second)],
        targets=_targets(make_profile, ("system", SYSTEM_OPTS)),
    )

    first_table = _expected_window_table(seq, first)
    second_table = _expected_window_table(seq, second)
    assert first_table != second_table
    assert card.body_html.startswith("<h3>first half</h3>\n")
    assert "\n\n<h3>second half</h3>\n" in card.body_html
    assert _parse(card.body_html).tables == [first_table, second_table]


def test_window_outside_the_sequence_raises():
    """A window that is not inside the sequence raises `ValueError`."""
    seq, _gx = _trapezoid_seq(0.4 * SYSTEM.max_grad)

    with pytest.raises(ValueError, match="late"):
        gradient_limits_card(seq, windows=[TimeWindow("late", 1.0, 2.0)])


def test_render_page_accepts_gradient_limits_card():
    """`render_page` accepts the card that `gradient_limits_card` returns, and the page has
    the card's script, registered under the name in `Card.script`."""
    seq, _gx = _trapezoid_seq(0.4 * SYSTEM.max_grad)
    card = gradient_limits_card(seq)

    result = page.render_page("Title", "Subtitle", [card])

    assert (
        '<section class="card" id="gradient-limits" data-card-script="gradient-limits">' in result
    )
    assert "<h2>Gradient limits</h2>" in result
    assert 'PulseqReport.registerCard("gradient-limits"' in result


def test_show_buttons_send_the_block_of_each_value_with_its_time():
    """Two blocks, an x trapezoid (0.2 of the limit) then a y trapezoid (0.5), each 1.4 ms:
    there is one "Show" button for each value with a block (the Gx and Gy peaks and max
    slews, and the |G| peak). The Gy peak's button shows block 2 with half its duration on
    each side (0.7 ms to 3.5 ms), anchored at the end of its rise (1.6 ms); the |G| peak is the
    same place. The card has the script that sends the buttons' `goto` messages."""
    seq = _two_trapezoid_seq()

    card = gradient_limits_card(seq)

    buttons = {b["aria-label"]: b for b in _parse(card.body_html).buttons}
    assert set(buttons) == {
        f"Show the {what} in the diagram"
        for what in ("Gx peak", "Gx max slew", "Gy peak", "Gy max slew", "|G| peak")
    }
    for label in ("Show the Gy peak in the diagram", "Show the |G| peak in the diagram"):
        button = buttons[label]
        assert float(button["data-t0"]) == pytest.approx(0.7e-3)
        assert float(button["data-t1"]) == pytest.approx(3.5e-3)
        assert float(button["data-anchor"]) == pytest.approx(1.6e-3)
        assert "hidden" in button
    assert card.script == "gradient-limits"
    assert len(card.scripts) == 1
    assert card.publishes == ("goto",)


def test_show_button_view_of_a_short_block_is_1_ms_wide():
    """A block of 0.3 ms: twice its duration is less than 1 ms, so the button's view is 1 ms
    wide, centred on the block, as the diagram's own `goto` of a block."""
    gx = pp.make_trapezoid(
        channel="x",
        amplitude=0.1 * SYSTEM.max_grad,
        rise_time=100e-6,
        flat_time=100e-6,
        system=SYSTEM,
    )
    seq = pp.Sequence(SYSTEM)
    seq.add_block(gx)

    card = gradient_limits_card(seq)

    for button in _parse(card.body_html).buttons:
        assert float(button["data-t0"]) == pytest.approx(0.15e-3 - 0.5e-3)
        assert float(button["data-t1"]) == pytest.approx(0.15e-3 + 0.5e-3)


def _percent_cells(result, gamma: float, limits) -> list[list[str]]:
    """The percent cells of the Gx, Gy, Gz and |G| rows of one target, as `[peak, slew]`:
    the Hz/m (Hz/m/s) value of `result` (a `GradientLimits`) in mT/m (T/m/s) with `gamma`,
    over the limit of `limits`, times 100. The |G| row has no slew."""
    cells = []
    for axis in "xyz":
        a = result.axes[axis]
        cells.append(
            [
                fmt(a.peak_hz_per_m / abs(gamma) * 1e3 / limits.max_grad_mt_per_m * 100),
                fmt(a.max_slew_hz_per_m_per_s / abs(gamma) / limits.max_slew_t_per_m_per_s * 100),
            ]
        )
    vector = fmt(result.vector_peak_hz_per_m / abs(gamma) * 1e3 / limits.max_grad_mt_per_m * 100)
    return [*cells, [vector, "—"]]


def test_each_target_has_its_percent_columns_with_its_own_gamma_in_target_order(make_profile):
    """Two targets with limits and two gammas: the table has the peak percent of the first
    target, then of the second, after the peak, and the same for the max slew. Each percent
    is the Hz/m (Hz/m/s) value in mT/m (T/m/s) with the gamma of that target, over its
    limit. The heading of a column names its target after a swatch of the color of the
    target, and both tables (the gammas give two entries) have the same percent columns."""
    seq = _two_trapezoid_seq()
    targets = _targets(
        make_profile, ("first", _opts(40, 200)), ("second", _opts(30, 120, gamma=20e6))
    )
    result = gradient_limits(seq)
    by_target = [
        _percent_cells(result, t.gamma, t.profile.hardware_limits) for t in targets
    ]  # [target][row][peak or slew]

    card = gradient_limits_card(seq, targets=targets)

    parser = _parse(card.body_html)
    assert len(parser.tables) == 2
    for table in parser.tables:
        assert table[0] == [
            "Axis",
            "Peak (mT/m)",
            _heading("first"),
            _heading("second"),
            "Max slew (T/m/s)",
            _heading("first"),
            _heading("second"),
            "RMS (mT/m)",
        ]
        for r, row in enumerate(table[1:]):
            assert row[2:4] == [by_target[0][r][0], by_target[1][r][0]]
            assert row[5:7] == [by_target[0][r][1], by_target[1][r][1]]
        assert by_target[0] != by_target[1]
    colors = [re.search(r"var\(--(target-\d)\)", style).group(1) for style in parser.swatches]
    assert colors == ["target-1", "target-2"] * 4


def test_a_target_without_limits_has_no_percent_column_and_is_named(make_profile):
    """A target with limits and a target without (it has a max amplitude and no max slew): the
    table has the percent columns of the first only, and the name of the second, escaped, is
    in the card but not in a heading of a table."""
    seq = _two_trapezoid_seq()
    (with_limits,) = _targets(make_profile, ("system", SYSTEM_OPTS))
    bare = dataclasses.replace(make_profile("bare", "max_grad = 30"), name="bare <i> & co")
    targets = report_targets([with_limits.profile, bare])

    card = gradient_limits_card(seq, targets=targets)

    (table,) = _parse(card.body_html).tables
    assert table[0] == [
        "Axis",
        "Peak (mT/m)",
        _heading("system"),
        "Max slew (T/m/s)",
        _heading("system"),
        "RMS (mT/m)",
    ]
    assert "bare &lt;i&gt; &amp; co" in card.body_html
    assert "bare <i>" not in card.body_html


def test_a_negative_gamma_gives_the_percent_of_its_magnitude(make_profile):
    """Two targets with the same limits and the gamma 11.777 MHz/T and its negative: the
    gammas have one magnitude, so there is one table (and no control), the two percent
    columns of the peak are equal, and so are the two of the max slew. They equal the Hz/m
    (Hz/m/s) value in mT/m (T/m/s) with the magnitude of the gamma, over the limit."""
    seq = _two_trapezoid_seq()
    targets = _targets(
        make_profile,
        ("positive", _opts(40, 200, gamma=11.777e6)),
        ("negative", _opts(40, 200, gamma=-11.777e6)),
    )
    expected = _percent_cells(gradient_limits(seq), 11.777e6, targets[0].profile.hardware_limits)

    card = gradient_limits_card(seq, targets=targets)

    (table,) = _parse(card.body_html).tables
    for r, row in enumerate(table[1:]):
        assert row[2] == row[3] == expected[r][0]
        if r < 3:
            assert row[5] == row[6] == expected[r][1]
    # The Gy peak is 14 mT/m at 42.576 MHz/T, so 51 mT/m at 11.777 MHz/T, above the 40 mT/m
    # limit: the percent is not a trivial 0.
    assert float(table[2][2].replace("−", "-")) > 100


def test_two_gamma_magnitudes_give_a_table_for_each_and_the_control():
    """Targets with the gammas 42.576 MHz/T and -11.777 MHz/T (two magnitudes): each window
    has two tables, in elements with `data-gamma-entry` 0 and 1 (the second hidden), and the
    peak cells of table k are those of entry k, the peak in mT/m with its |gamma|. The card
    has one control, with a button for each entry, before the first table, and the script
    of the "Show" buttons, which also runs the control."""
    seq = _two_trapezoid_seq()
    targets = report_targets(
        [read_profile(PROFILES / "example_a.toml"), read_profile(PROFILES / "example_c.toml")]
    )
    end = gradient_limits(seq).range_s[1]
    windows = [(0.0, end / 2), (end / 2, end)]

    card = gradient_limits_card(
        seq,
        windows=[TimeWindow("first half", *windows[0]), TimeWindow("second half", *windows[1])],
        targets=targets,
    )

    parser = _parse(card.body_html)
    assert parser.entries == [("0", False), ("1", True)] * 2
    gammas = [GAMMA_1H, 11.777e6]
    for w, window in enumerate(windows):
        result = gradient_limits(seq, window=window)
        a = result.axes["y"]
        for k, gamma in enumerate(gammas):
            gy_row = parser.tables[2 * w + k][2]
            assert gy_row[1] == _where(
                fmt(a.peak_hz_per_m / gamma * 1e3), a.peak_block, a.peak_time_s
            )
    controls = [b for b in parser.buttons if "data-gamma-choice" in b]
    assert [(b["data-gamma-choice"], b["aria-pressed"]) for b in controls] == [
        ("0", "true"),
        ("1", "false"),
    ]
    assert [float(b["data-gamma"]) for b in controls] == gammas
    assert card.body_html.index("data-gamma-choice") < card.body_html.index("<table")
    assert card.script == "gradient-limits"
    assert card.scripts == (page.card_asset("gradient-limits"),)


def test_one_gamma_magnitude_gives_one_table_and_no_control(make_profile):
    """Targets with the gammas 42.576 MHz/T and -42.576 MHz/T (one magnitude): one table, in
    no element with `data-gamma-entry`, and no control."""
    seq = _two_trapezoid_seq()
    targets = _targets(
        make_profile, ("positive", _opts(40, 200)), ("negative", _opts(40, 200, gamma=-42.576e6))
    )

    card = gradient_limits_card(seq, targets=targets)

    parser = _parse(card.body_html)
    assert len(parser.tables) == 1
    assert parser.entries == [None]
    assert "data-gamma" not in card.body_html


def test_a_control_without_a_show_button_has_the_gamma_select_script():
    """A file with no gradient event has no "Show" button, so the card with two |gamma|
    entries has the library script `gamma-select` for its control, and the page has it."""
    seq = pp.Sequence(SYSTEM)
    seq.add_block(pp.make_delay(2e-3))
    targets = report_targets(
        [read_profile(PROFILES / "example_a.toml"), read_profile(PROFILES / "example_c.toml")]
    )

    card = gradient_limits_card(seq, targets=targets)

    assert len(_parse(card.body_html).tables) == 2
    assert card.script == "gamma-select"
    assert card.scripts == (page.card_asset("gamma-select"),)
    assert 'PulseqReport.registerCard("gamma-select"' in page.render_page("T", "S", [card])


def test_without_targets_the_values_are_in_the_gamma_of_the_sequence():
    """Without targets, the peak is in mT/m with `seq.system.gamma`, in one table with no
    control and no percent column."""
    gamma = 20e6
    system = pp.Opts(max_grad=28, grad_unit="mT/m", max_slew=150, slew_unit="T/m/s", gamma=gamma)
    amplitude = 0.4 * system.max_grad
    gx = pp.make_trapezoid(
        channel="x", amplitude=amplitude, rise_time=200e-6, flat_time=1e-3, system=system
    )
    seq = pp.Sequence(system)
    seq.add_block(gx)

    card = gradient_limits_card(seq)

    parser = _parse(card.body_html)
    (table,) = parser.tables
    block_id = next(iter(seq.block_events))
    assert table[1][1] == _where(fmt(amplitude / gamma * 1e3), block_id, gx.rise_time)
    assert table[1][1].startswith(fmt(0.4 * 28))
    assert parser.entries == [None]
    assert "data-gamma" not in card.body_html


def test_the_registry_gives_the_targets_to_the_card(make_profile):
    """`build_cards` builds the card with the targets of the report: the card is that of
    `gradient_limits_card` with the `ReportTarget` of each profile."""
    seq = _two_trapezoid_seq()
    profiles = [
        make_profile("first", _opts(40, 200)),
        make_profile("second", _opts(30, 120, gamma=20e6)),
    ]

    (built,) = build_cards(seq, cards=["gradient-limits"], targets=profiles)

    assert built == gradient_limits_card(seq, targets=report_targets(profiles))
    assert [len(row) for row in _parse(built.body_html).tables[0]] == [8] * 5
