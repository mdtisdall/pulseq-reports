import math

import numpy as np
import pytest
from oracles import rf_exposure as oracle
from synthetic import empty_sequence, gre_sequence, spin_echo_sequence

from pulseq_reports import page
from pulseq_reports import rf_exposure as rf_exposure_module
from pulseq_reports.cards import rf_exposure as rf_exposure_card_module
from pulseq_reports.cards.rf_exposure import rf_exposure_card, rf_exposure_data
from pulseq_reports.seq_utils import GAMMA, NamedSequence


def _b1_ut(flip_rad: float, duration_s: float) -> float:
    """The constant B1 (µT) of a block pulse with this flip angle and duration."""
    return (flip_rad / (2 * math.pi)) / duration_s / GAMMA * 1e6


@pytest.fixture(scope="module")
def default_seq():
    return spin_echo_sequence()


def _refocusing_block_id(seq) -> int:
    for block_id in seq.block_events:
        rf = getattr(seq.get_block(block_id), "rf", None)
        if rf is not None and rf.use == "refocusing":
            return int(block_id)
    raise AssertionError("no refocusing pulse in sequence")


def test_rf_exposure_data_for_spin_echo(default_seq):
    data = rf_exposure_data(default_seq)
    b1_ex = _b1_ut(math.pi / 2, 1e-3)
    b1_ref = _b1_ut(math.pi, 1e-3)

    assert data["num_pulses"] == 2
    assert data["duration_ms"] == pytest.approx(default_seq.duration()[0] * 1e3)
    # The refocusing pulse (180°) has twice the flip of the excitation pulse (90°) in the
    # same duration, so it has the higher B1 and is the peak.
    assert data["peak_b1_ut"] == pytest.approx(b1_ref, rel=1e-6)
    assert data["peak_block"] == _refocusing_block_id(default_seq)
    assert data["energy_ut2_ms"] == pytest.approx(b1_ex**2 + b1_ref**2, rel=1e-6)
    assert data["b1rms_ut"] == pytest.approx(
        math.sqrt(data["energy_ut2_ms"] / data["duration_ms"]), rel=1e-4
    )
    assert data["window_s"] == 10.0
    assert data["window_used_s"] == 10.0
    # The window is at least as energetic as one period, since it can include more than one
    # repetition of the (much shorter than 10 s) sequence.
    assert data["b1rms_window_ut"] >= data["b1rms_ut"]
    assert data["periodic"] is True


def test_report_has_rf_exposure_card(default_seq):
    card = rf_exposure_card([NamedSequence("vb-spin-echo", default_seq)])
    assert card.id == "rf-exposure"
    assert card.title == "RF exposure"
    assert card.data is None
    assert card.script is None

    result = page.render_page("Title", "Subtitle", [card])
    body = result[result.index('id="rf-exposure"') :]
    assert "<h2>RF exposure</h2>" in body
    for label in (
        "RF pulses",
        "Peak B1 (µT)",
        "∫B1² dt over the sequence (µT²·ms)",
        "Sequence duration (ms)",
        "B1+rms, sequence repeated (µT)",
        "B1+rms, highest 10 s window (µT)",
    ):
        assert f"<td>{label}</td>" in body


def test_rf_exposure_card_without_rf():
    card = rf_exposure_card([NamedSequence("no-rf", empty_sequence())])
    assert card.body_html == '<p class="muted">No RF pulses.</p>'
    result = page.render_page("Title", "Subtitle", [card])
    assert '<p class="muted">No RF pulses.</p>' in result


def test_rf_exposure_card_two_files():
    seqs = [
        NamedSequence("spin-echo.seq", spin_echo_sequence()),
        NamedSequence("gre.seq", gre_sequence()),
    ]
    card = rf_exposure_card(seqs)
    body = card.body_html

    assert "<h3>spin-echo.seq</h3>" in body
    assert "<h3>gre.seq</h3>" in body
    assert "<h3>All files</h3>" in body
    assert (
        body.index("<h3>spin-echo.seq</h3>")
        < body.index("<h3>gre.seq</h3>")
        < body.index("<h3>All files</h3>")
    )

    spin_echo_data = rf_exposure_data(seqs[0].seq)
    gre_data = rf_exposure_data(seqs[1].seq)
    all_files_peak_b1 = max(spin_echo_data["peak_b1_ut"], gre_data["peak_b1_ut"])
    assert f"<td>{all_files_peak_b1:.2f}</td>" in body[body.index("<h3>All files</h3>") :]
    assert "sequence repeated" in body[body.index("<h3>All files</h3>") :]

    # render_page accepts a card built for more than one file too.
    page.render_page("Title", "Subtitle", [card])


def test_rf_exposure_card_two_files_not_periodic_omits_repeated_wording():
    seqs = [
        NamedSequence("spin-echo.seq", spin_echo_sequence()),
        NamedSequence("gre.seq", gre_sequence()),
    ]
    card = rf_exposure_card(seqs, periodic=False)
    all_files_html = card.body_html[card.body_html.index("<h3>All files</h3>") :]
    assert "sequence repeated" not in all_files_html
    assert "files played once" in all_files_html


# ---- Comparisons with the oracle (task 3.5) ----
#
# The "All files" table combines the files' pulse trains into one, with the file offsets
# (`cards/rf_exposure.py`'s `_combined_data`, from the pulse trains that `rf_exposure_card`
# already built for each file's own table, section 4.5 item 7 of
# docs/plans/cards-at-scale.md: no file is read twice). Before phase 3, the card instead
# read each file's samples again with `oracle._rf_samples`, offset them by hand and called
# `oracle._windowed_energy` on the concatenation (`cards/rf_exposure.py`'s own
# `_combined_data`, before this task's changes; see `tests/oracles/rf_exposure.py`'s own
# docstring). `_oracle_combined_data` rebuilds that approach directly from the oracle
# module, so the tests below compare the new card's dict with it, independently of
# `_combined_data`'s own implementation.


def _oracle_combined_data(seqs: list[NamedSequence], periodic: bool, window_s: float) -> dict:
    """The "All files" data as the card computed it before phase 3: each file's samples
    from `oracle._rf_samples`, offset by the durations before it, concatenated, then
    `oracle._windowed_energy` on the concatenation."""
    times_parts: list[np.ndarray] = []
    energy_parts: list[np.ndarray] = []
    durations, num_pulses_list, peak_b1_list, energy_totals = [], [], [], []
    offset = 0.0
    for named in seqs:
        raster = named.seq.system.rf_raster_time
        times, energies, duration, peak_b1, _peak_block, num_pulses = oracle._rf_samples(
            named.seq, raster
        )
        durations.append(duration)
        num_pulses_list.append(num_pulses)
        peak_b1_list.append(peak_b1)
        energy_totals.append(float(np.concatenate(energies).sum()) if energies else 0.0)
        if times:
            times_parts.append(np.concatenate(times) + offset)
            energy_parts.append(np.concatenate(energies))
        offset += duration

    total_duration = sum(durations)
    total_pulses = sum(num_pulses_list)
    peak_b1 = max(peak_b1_list, default=0.0)
    total_energy = sum(energy_totals)

    if total_pulses == 0 or total_duration <= 0:
        window_used = window_s if periodic else total_duration
        window_energy = 0.0
    else:
        combined_times = np.concatenate(times_parts)
        combined_energy = np.concatenate(energy_parts)
        window_used, window_energy = oracle._windowed_energy(
            combined_times, combined_energy, total_duration, window_s, periodic
        )
    b1rms = math.sqrt(total_energy / total_duration) if total_duration > 0 else 0.0
    b1rms_window = math.sqrt(window_energy / window_used) if window_used > 0 else 0.0

    return {
        "duration_ms": round(total_duration * 1e3, 4),
        "num_pulses": total_pulses,
        "peak_b1_ut": round(peak_b1, 4),
        "peak_block": None,
        "energy_ut2_ms": round(total_energy * 1e3, 4),
        "b1rms_ut": round(b1rms, 4),
        "window_s": window_s,
        "b1rms_window_ut": round(b1rms_window, 4),
        "window_used_s": window_used,
        "periodic": periodic,
    }


def _combined_data_from_new_module(
    seqs: list[NamedSequence], periodic: bool, window_s: float
) -> dict:
    """The new card's "All files" dict, built the same way `rf_exposure_card` builds it:
    one `_pulse_train` per file, then `_combined_data` on the trains and exposures."""
    trains, exposures = [], []
    for named in seqs:
        train, duration = rf_exposure_module._pulse_train(named.seq)
        trains.append(train)
        exposures.append(rf_exposure_module._exposure(train, duration, window_s, periodic))
    return rf_exposure_card_module._combined_data(exposures, trains, periodic, window_s)


def _assert_combined_data_matches_oracle(ours: dict, theirs: dict) -> None:
    assert ours["num_pulses"] == theirs["num_pulses"]
    assert ours["peak_block"] == theirs["peak_block"]
    assert ours["window_s"] == theirs["window_s"]
    assert ours["window_used_s"] == theirs["window_used_s"]
    assert ours["periodic"] == theirs["periodic"]
    # duration_ms, peak_b1_ut, energy_ut2_ms, b1rms_ut and b1rms_window_ut are already
    # rounded to 4 decimals (`round(x, 4)`): a relative 1e-12 difference before rounding
    # (section 3.5, item 2 of the plan) is far too small to change the rounded value, so
    # these must match exactly too.
    for field in ("duration_ms", "peak_b1_ut", "energy_ut2_ms", "b1rms_ut", "b1rms_window_ut"):
        assert ours[field] == theirs[field], f"{field}: {ours[field]!r} != {theirs[field]!r}"


def _two_and_three_file_cases() -> list[list[NamedSequence]]:
    """Two files (spin echo and GRE), and three (those two plus a spin echo variant with
    the readout prephaser after the second crusher instead of before it)."""
    two = [
        NamedSequence("spin-echo.seq", spin_echo_sequence()),
        NamedSequence("gre.seq", gre_sequence()),
    ]
    three = [
        *two,
        NamedSequence("spin-echo-2.seq", spin_echo_sequence(prephaser_position="after")),
    ]
    return [two, three]


@pytest.mark.parametrize("seqs", _two_and_three_file_cases(), ids=["two_files", "three_files"])
@pytest.mark.parametrize("periodic", [True, False])
def test_all_files_table_matches_oracle(seqs, periodic):
    """The "All files" table (`_combined_data`'s dict) for two and for three files
    matches the oracle's own way of combining files (`_oracle_combined_data`), for both
    `periodic` values, within the tolerance above."""
    ours = _combined_data_from_new_module(seqs, periodic, rf_exposure_module.WINDOW_S)
    theirs = _oracle_combined_data(seqs, periodic, rf_exposure_module.WINDOW_S)
    _assert_combined_data_matches_oracle(ours, theirs)


@pytest.mark.parametrize("seqs", _two_and_three_file_cases(), ids=["two_files", "three_files"])
def test_all_files_reads_each_file_once(seqs, monkeypatch):
    """`rf_exposure_card` calls `rf_exposure._pulse_train` exactly once for each file, for
    two and for three files: it does not read a file again to build the "All files" table
    (section 4.5 item 7 of the plan)."""
    calls = []
    real_pulse_train = rf_exposure_module._pulse_train

    def counting_pulse_train(seq):
        calls.append(seq)
        return real_pulse_train(seq)

    monkeypatch.setattr(rf_exposure_module, "_pulse_train", counting_pulse_train)

    rf_exposure_card(seqs)

    assert len(calls) == len(seqs)
