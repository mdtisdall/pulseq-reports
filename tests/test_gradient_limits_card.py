import math

import pypulseq as pp
from synthetic import SYSTEM

from pulseq_reports import grad_limits, page
from pulseq_reports.cards.gradient_limits import gradient_limits_card
from pulseq_reports.markup import fmt, html_table
from pulseq_reports.seq_utils import GAMMA


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

    card = gradient_limits_card(seq, window=window)

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

    assert card.body_html.startswith(expected_table)


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

    gradient_limits_card(seq, window=(0.0, 1e-3))

    assert len(calls) == 1


def test_render_page_accepts_gradient_limits_card():
    """`render_page` accepts the card that `gradient_limits_card` returns."""
    seq, _gx = _trapezoid_seq(0.4 * SYSTEM.max_grad)
    card = gradient_limits_card(seq)

    result = page.render_page("Title", "Subtitle", [card])

    assert '<section class="card" id="gradient-limits">' in result
    assert "<h2>Gradient limits</h2>" in result
