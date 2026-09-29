import math

import pypulseq as pp
import pytest
from synthetic import SYSTEM

from pulseq_reports import grad_limits, page
from pulseq_reports.cards.gradient_limits import gradient_limits_card
from pulseq_reports.markup import fmt, html_table
from pulseq_reports.seq_utils import GAMMA
from pulseq_reports.waveforms import TimeWindow


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
    parameters, the same formulas as `test_grad_limits.py`."""
    duration = gx.delay + gx.rise_time + gx.flat_time + gx.fall_time
    energy = (
        gx.rise_time * amplitude**2 / 3
        + gx.flat_time * amplitude**2
        + gx.fall_time * amplitude**2 / 3
    )
    return {
        "peak_mt": amplitude / GAMMA * 1e3,
        "slew_t": amplitude / gx.rise_time / GAMMA,
        "rms_mt": math.sqrt(energy / duration) / GAMMA * 1e3,
    }


def test_table_has_axis_rows_and_percents():
    """One x trapezoid: the Gx, Gy, Gz and |G| rows hold the peak, the percent of the
    limit, the max slew, its percent, and the RMS, each computed by hand from the
    trapezoid's own parameters."""
    amplitude = 0.4 * SYSTEM.max_grad
    seq, gx = _trapezoid_seq(amplitude)
    values = _hand_computed(amplitude, gx)
    max_grad_mt = SYSTEM.max_grad / GAMMA * 1e3
    max_slew_t = SYSTEM.max_slew / GAMMA
    peak_pct = values["peak_mt"] / max_grad_mt * 100
    slew_pct = values["slew_t"] / max_slew_t * 100
    zero_row = ["", fmt(0.0), fmt(0.0), fmt(0.0), fmt(0.0), fmt(0.0)]

    card = gradient_limits_card(seq)

    expected_table = html_table(
        ["Axis", "Peak (mT/m)", "% of limit", "Max slew (T/m/s)", "% of limit", "RMS (mT/m)"],
        [
            [
                "Gx",
                fmt(values["peak_mt"]),
                fmt(peak_pct),
                fmt(values["slew_t"]),
                fmt(slew_pct),
                fmt(values["rms_mt"]),
            ],
            ["Gy", *zero_row[1:]],
            ["Gz", *zero_row[1:]],
            # There is no gradient on y or z, so the |G| peak and RMS equal Gx's. There is
            # no vector slew, so those cells are the "no value" mark.
            ["|G|", fmt(values["peak_mt"]), fmt(peak_pct), "—", "—", fmt(values["rms_mt"])],
        ],
    )

    assert card.id == "gradient-limits"
    assert card.title == "Gradient limits"
    assert card.data is None
    assert card.script is None
    assert card.body_html.startswith(expected_table)
    assert "pypulseq system limits" in card.body_html


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
    window_rms_mt = math.sqrt(amplitude**2 / 3) / GAMMA * 1e3
    max_grad_mt = SYSTEM.max_grad / GAMMA * 1e3
    max_slew_t = SYSTEM.max_slew / GAMMA
    window_peak_mt = amplitude / GAMMA * 1e3  # the ramp reaches amplitude at the window edge
    window_slew_t = amplitude / gx.rise_time / GAMMA

    card = gradient_limits_card(seq, windows=[TimeWindow("ramp", *window)])

    expected_table = html_table(
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
            [
                "Gx",
                fmt(window_peak_mt),
                fmt(window_peak_mt / max_grad_mt * 100),
                fmt(window_slew_t),
                fmt(window_slew_t / max_slew_t * 100),
                fmt(window_rms_mt),
                fmt(whole["rms_mt"]),
            ],
            ["Gy", fmt(0.0), fmt(0.0), fmt(0.0), fmt(0.0), fmt(0.0), fmt(0.0)],
            ["Gz", fmt(0.0), fmt(0.0), fmt(0.0), fmt(0.0), fmt(0.0), fmt(0.0)],
            [
                "|G|",
                fmt(window_peak_mt),
                fmt(window_peak_mt / max_grad_mt * 100),
                "—",
                "—",
                fmt(window_rms_mt),
                fmt(whole["rms_mt"]),
            ],
        ],
    )

    assert card.body_html.startswith(f"<h3>ramp</h3>\n{expected_table}")


def test_no_gradients_adds_a_reason_note():
    """A file with no gradient events: the table still has the four rows, all zero,
    and the muted note gives the reason."""
    seq = pp.Sequence(SYSTEM)
    seq.add_block(pp.make_delay(2e-3))

    card = gradient_limits_card(seq)

    assert '<p class="muted">no gradient events in the sequence.</p>' in card.body_html


def test_card_with_a_window_makes_one_pass_over_the_per_event_values(monkeypatch):
    """With a window, `gradient_limits_card` calls the per-event function
    (`seq_index.grad_events`, which reads each unique gradient event's block with
    `get_block`) exactly one time for the one file, instead of once for the window and
    again for the whole-file RMS (`GradientLimits.whole_rms_mt_per_m` gives that from
    the same call, section 4.6 item 4 of `docs/plans/cards-at-scale.md`)."""
    seq, _gx = _trapezoid_seq(0.4 * SYSTEM.max_grad)
    calls = []
    real_grad_events = grad_limits.grad_events

    def counting_grad_events(seq, index):
        calls.append(1)
        return real_grad_events(seq, index)

    monkeypatch.setattr(grad_limits, "grad_events", counting_grad_events)

    gradient_limits_card(seq, windows=[TimeWindow("first", 0.0, 1e-3)])

    assert len(calls) == 1


def _expected_window_table(seq, window, limits=None) -> str:
    """The table of one window, from `gradient_limits` for that range."""
    result = grad_limits.gradient_limits(seq, window=window, limits=limits)
    lim = result.limits
    rows = []
    for axis, label in (("x", "Gx"), ("y", "Gy"), ("z", "Gz")):
        a = result.axes[axis]
        rows.append(
            [
                label,
                fmt(a.peak_mt_per_m),
                fmt(a.peak_mt_per_m / lim.max_grad_mt_per_m * 100),
                fmt(a.max_slew_t_per_m_per_s),
                fmt(a.max_slew_t_per_m_per_s / lim.max_slew_t_per_m_per_s * 100),
                fmt(a.rms_mt_per_m),
                fmt(result.whole_rms_mt_per_m[axis]),
            ]
        )
    vector_rms = math.sqrt(sum(result.axes[x].rms_mt_per_m ** 2 for x in "xyz"))
    whole_vector_rms = math.sqrt(sum(result.whole_rms_mt_per_m[x] ** 2 for x in "xyz"))
    rows.append(
        [
            "|G|",
            fmt(result.vector_peak_mt_per_m),
            fmt(result.vector_peak_mt_per_m / lim.max_grad_mt_per_m * 100),
            "—",
            "—",
            fmt(vector_rms),
            fmt(whole_vector_rms),
        ]
    )
    return html_table(
        [
            "Axis",
            "Peak (mT/m)",
            "% of limit",
            "Max slew (T/m/s)",
            "% of limit",
            "RMS over window (mT/m)",
            "RMS over whole file (mT/m)",
        ],
        rows,
    )


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
    end = grad_limits.gradient_limits(seq).range_s[1]
    first = (0.0, end / 2)
    second = (end / 2, end)

    card = gradient_limits_card(
        seq, windows=[TimeWindow("first half", *first), TimeWindow("second half", *second)]
    )

    first_table = _expected_window_table(seq, first)
    second_table = _expected_window_table(seq, second)
    assert first_table != second_table
    assert card.body_html.startswith(
        f"<h3>first half</h3>\n{first_table}\n\n<h3>second half</h3>\n{second_table}"
    )


def test_window_outside_the_sequence_raises_before_any_computation(monkeypatch):
    """A window that is not inside the sequence raises `ValueError`, and no analysis
    ran."""
    seq, _gx = _trapezoid_seq(0.4 * SYSTEM.max_grad)
    calls = []
    monkeypatch.setattr(grad_limits, "sequence_index", lambda seq: calls.append(1))

    with pytest.raises(ValueError, match="late"):
        gradient_limits_card(seq, windows=[TimeWindow("late", 1.0, 2.0)])

    assert calls == []


def test_note_gives_the_values_of_the_given_limits():
    """The note's limits are the values of the `limits` argument, with its label."""
    seq, _gx = _trapezoid_seq(0.4 * SYSTEM.max_grad)
    limits = grad_limits.HardwareLimits(
        max_grad_mt_per_m=22.5, max_slew_t_per_m_per_s=77.0, label="test coil"
    )

    card = gradient_limits_card(seq, limits=limits)

    assert f"Limits: test coil ({fmt(22.5)} mT/m, {fmt(77.0)} T/m/s)." in card.body_html


def test_render_page_accepts_gradient_limits_card():
    """`render_page` accepts the card that `gradient_limits_card` returns."""
    seq, _gx = _trapezoid_seq(0.4 * SYSTEM.max_grad)
    card = gradient_limits_card(seq)

    result = page.render_page("Title", "Subtitle", [card])

    assert '<section class="card" id="gradient-limits">' in result
    assert "<h2>Gradient limits</h2>" in result
