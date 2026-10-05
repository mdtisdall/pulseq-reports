import math
from html.parser import HTMLParser

import pypulseq as pp
import pytest
from pulseq_analysis.grad_limits import gradient_limits
from pulseq_checks import HardwareLimits
from synthetic import GAMMA_1H, SYSTEM

from pulseq_reports import page
from pulseq_reports.cards.gradient_limits import gradient_limits_card
from pulseq_reports.markup import fmt
from pulseq_reports.waveforms import TimeWindow


class _CardParser(HTMLParser):
    """The tables of a card body, each as its rows of cell texts (the header row first, a
    button's own text left out, white space collapsed), and the attributes of each button."""

    def __init__(self) -> None:
        super().__init__()
        self.tables: list[list[list[str]]] = []
        self.buttons: list[dict[str, str | None]] = []
        self._cell: list[str] | None = None
        self._in_button = False

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.tables.append([])
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


LIMITS = HardwareLimits(
    max_grad_mt_per_m=SYSTEM.max_grad / GAMMA_1H * 1e3,
    max_slew_t_per_m_per_s=SYSTEM.max_slew / GAMMA_1H,
    label="system limits",
)


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


def test_table_has_axis_rows_and_percents():
    """One x trapezoid: the Gx, Gy, Gz and |G| rows hold the peak, the percent of the
    limit, the max slew, its percent, and the RMS, each computed by hand from the
    trapezoid's own parameters. The Gx and |G| peaks are reached at the end of the rise
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

    card = gradient_limits_card(seq, limits=LIMITS)

    expected_table = [
        ["Axis", "Peak (mT/m)", "% of limit", "Max slew (T/m/s)", "% of limit", "RMS (mT/m)"],
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


def test_window_gives_rms_over_window_and_over_whole_file():
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

    card = gradient_limits_card(seq, windows=[TimeWindow("ramp", *window)], limits=LIMITS)

    expected_table = [
        [
            "Axis",
            "Peak (mT/m)",
            "% of limit",
            "Max slew (T/m/s)",
            "% of limit",
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


def test_without_limits_the_table_has_no_percent_columns():
    """Without `limits`, the tables have no "% of limit" header and no percent cell: the
    whole-file table has four columns (axis, peak, max slew, RMS), and the table of a window
    has five (RMS over the window and over the whole file). With `limits`, each table has
    the two percent columns more. The cells of each row are as many as the headers."""
    seq = _two_trapezoid_seq()
    end = gradient_limits(seq).range_s[1]
    windows = [TimeWindow("first half", 0.0, end / 2), TimeWindow("second half", end / 2, end)]

    for kwargs, columns in (({}, 4), ({"windows": windows}, 5)):
        for limits, percent_columns in ((None, 0), (LIMITS, 2)):
            card = gradient_limits_card(seq, limits=limits, **kwargs)

            tables = _parse(card.body_html).tables
            assert len(tables) == len(kwargs.get("windows", [None]))
            for table in tables:
                assert table[0].count("% of limit") == percent_columns
                assert [len(row) for row in table] == [columns + percent_columns] * 5


def test_without_limits_the_values_are_those_with_limits():
    """The cells that the percent columns do not hold are the same with and without
    `limits`: the table without limits is the table with limits, less its percent columns."""
    seq = _two_trapezoid_seq()

    without = _parse(gradient_limits_card(seq).body_html).tables[0]
    with_limits = _parse(gradient_limits_card(seq, limits=LIMITS).body_html).tables[0]

    percent = [i for i, header in enumerate(with_limits[0]) if header == "% of limit"]
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
    """The cell texts of the table of one window, from `gradient_limits` for that range."""
    result = gradient_limits(seq, window=window)
    lim = LIMITS

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
                fmt(mt(a.peak_hz_per_m) / lim.max_grad_mt_per_m * 100),
                _where(fmt(t_per_s(a.max_slew_hz_per_m_per_s)), a.slew_block, a.slew_time_s),
                fmt(t_per_s(a.max_slew_hz_per_m_per_s) / lim.max_slew_t_per_m_per_s * 100),
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
            fmt(mt(result.vector_peak_hz_per_m) / lim.max_grad_mt_per_m * 100),
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
            "% of limit",
            "Max slew (T/m/s)",
            "% of limit",
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


def test_two_windows_give_two_tables_with_the_values_of_each_range():
    """Two windows, one over each trapezoid: the card has one table for each, under an
    `<h3>` of its label, with the values that `gradient_limits` gives for that range."""
    seq = _two_trapezoid_seq()
    end = gradient_limits(seq).range_s[1]
    first = (0.0, end / 2)
    second = (end / 2, end)

    card = gradient_limits_card(
        seq,
        windows=[TimeWindow("first half", *first), TimeWindow("second half", *second)],
        limits=LIMITS,
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


def test_note_gives_the_values_of_the_given_limits():
    """The note's limits are the values of the `limits` argument, with its label."""
    seq, _gx = _trapezoid_seq(0.4 * SYSTEM.max_grad)
    limits = HardwareLimits(
        max_grad_mt_per_m=22.5, max_slew_t_per_m_per_s=77.0, label="test limits"
    )

    card = gradient_limits_card(seq, limits=limits)

    assert f"Limits: test limits ({fmt(22.5)} mT/m, {fmt(77.0)} T/m/s)." in card.body_html


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
