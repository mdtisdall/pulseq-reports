"""Tests for `pulseq_reports.cards.rf_profile` (`docs/plans/rf-profiles.md`, section 4.5,
items 1 and 2; task 5.3, items 1 to 7).

Each test builds its sequences with pypulseq, with the same helpers as
`tests/test_rf_profiles.py`, which both import from `tests/rf_sequences.py`. This card
copies values from `rf_profiles` and `diagram_data`, so most checks compare with `==` or
`np.array_equal` (exact); a comparison that is not exact says why.
"""

import dataclasses
import html
import math
import re
from pathlib import Path

import numpy as np
import pypulseq as pp
import pytest
from pypulseq.event_lib import EventLibrary
from rf_sequences import (
    CRUSHER_AREA,
    SYSTEM,
    W,
    _gre,
    _hard,
    _new,
    _readout,
    _sinc,
    _trap,
    _turning_gradients,
)

from pulseq_reports import page
from pulseq_reports import rf_profiles as rp
from pulseq_reports.cards.diagram import diagram_card
from pulseq_reports.cards.rf_profile import (
    PRIMARY_ECHO_NOTE,
    PRIMARY_ECHO_TITLE,
    rf_profile_card,
    rf_profile_data,
    rf_table,
)
from pulseq_reports.diagram_data import decode_tables, encode_tables
from pulseq_reports.seq_utils import hold_samples
from pulseq_reports.waveforms import full_window

# ---- Sequence helpers ----


def _rotation_library_sequence():
    """A sequence with a rotation stored the way pypulseq draft PR #372 stores one in
    memory (as `tests/test_extensions.py` does): a non-empty `rotation_library`."""
    quaternion = (0.9238795325112867, 0.0, 0.0, 0.3826834323650898)  # 45 deg about z
    seq = _gre(1)
    seq.rotation_library = EventLibrary()
    seq.rotation_library.insert(1, quaternion)
    return seq


# ---- 1. The RF table ----


def test_rf_table_matches_hold_samples_and_definitions():
    """rf_table (task 5.3, item 1): a sinc excitation with a slice-select gradient and
    all four RF offsets, a sinc refocusing pulse, and a block pulse (its shape has few
    enough points that hold_samples interpolates it). Encoding and decoding round-trips
    the pools exactly, and each column matches its definition."""
    system = pp.Opts(
        max_grad=30,
        grad_unit="mT/m",
        max_slew=150,
        slew_unit="T/m/s",
        rf_dead_time=100e-6,
        rf_ringdown_time=30e-6,
        rf_raster_time=5e-6,
        B0=2.89,
    )
    rf_ex, gz_ex, _ = _sinc("excitation", system=system)
    rf_ex.freq_offset = 100.0
    rf_ex.phase_offset = 0.3
    rf_ex.freq_ppm = -3.45
    rf_ex.phase_ppm = 0.7
    rf_ref, gz_ref, _ = _sinc("refocusing", math.pi, phase_offset=math.pi / 2, system=system)
    block = _hard("saturation", duration=0.5e-3, system=system)
    seq = _new(system=system)
    seq.add_block(rf_ex, gz_ex)
    seq.add_block(rf_ref, gz_ref)
    seq.add_block(block)

    table = rf_table(seq)
    expected_dtypes = {
        "key": np.uint32,
        "use": np.uint8,
        "delay": np.float64,
        "shape_dur": np.float64,
        "center": np.float64,
        "dt": np.float64,
        "shape_at": np.uint32,
        "shape_n": np.uint32,
        "freq_hz": np.float64,
        "phase_rad": np.float64,
        "shape_re": np.float64,
        "shape_im": np.float64,
    }
    for name, dtype in expected_dtypes.items():
        assert table[name].dtype == dtype, name

    decoded = decode_tables(encode_tables(table))
    ppm_hz = 1e-6 * abs(system.gamma) * system.B0
    for k, use in enumerate(["excitation", "refocusing", "saturation"]):
        # The RF as pypulseq stores and rebuilds it (`seq.get_block`), not the object
        # given to `add_block`: the rebuilt samples can differ from the given ones by
        # float rounding. This is the same "rf" that `rf_table` itself reads.
        rf = seq.get_block(k + 1).rf
        baseband, dt = hold_samples(rf, system.rf_raster_time)
        at, n = int(decoded["shape_at"][k]), int(decoded["shape_n"][k])
        np.testing.assert_array_equal(decoded["shape_re"][at : at + n], baseband.real)
        np.testing.assert_array_equal(decoded["shape_im"][at : at + n], baseband.imag)
        assert decoded["dt"][k] == dt
        assert decoded["delay"][k] == float(rf.delay)
        assert decoded["shape_dur"][k] == float(rf.shape_dur)
        assert decoded["center"][k] == float(pp.calc_rf_center(rf)[0])
        assert decoded["use"][k] == rp.USES.index(use)
        expected_freq = float(rf.freq_offset) + float(getattr(rf, "freq_ppm", 0.0)) * ppm_hz
        expected_phase = float(rf.phase_offset) + float(getattr(rf, "phase_ppm", 0.0)) * ppm_hz
        assert decoded["freq_hz"][k] == expected_freq
        assert decoded["phase_rad"][k] == expected_phase
        # "at the first block of that RF event": each RF event here has only one block,
        # at play index k.
        assert decoded["freq_hz"][k] == rp.block_pulse(seq, k).freq_offset_hz


def test_rf_table_shares_one_shape_for_an_rf_spoiled_gre():
    """An RF-spoiled GRE (task 5.3, item 1): more than one dense RF index, one shape in
    the pools (every event shares the same baseband bytes), and one key (the phase
    offset is not part of the key). The same GRE with two slices (two frequency offsets)
    gives two keys and still one shape."""
    table = rf_table(_gre(24, rf_spoiling=True))
    assert table["key"].size > 1
    assert len(set(table["key"].tolist())) == 1
    assert table["shape_re"].size == int(table["shape_n"][0])
    assert table["shape_im"].size == int(table["shape_n"][0])
    np.testing.assert_array_equal(table["shape_at"], 0)

    two_slices = rf_table(_gre(1, slices=(-5e-3, 5e-3)))
    assert set(two_slices["key"].tolist()) == {0, 1}
    assert two_slices["shape_re"].size == int(two_slices["shape_n"][0])
    np.testing.assert_array_equal(two_slices["shape_at"], 0)


def test_rf_table_of_a_sequence_without_rf_is_empty():
    """A sequence without RF: every column and both pools of rf_table have length 0."""
    seq = _new()
    seq.add_block(_trap("x", 100.0))
    seq.add_block(pp.make_delay(1e-3))
    table = rf_table(seq)
    for name, arr in table.items():
        assert arr.size == 0, name


# ---- 2. The label check ----


def test_rf_table_raises_without_labels():
    """rf_table raises ValueError (rf_profiles._require_labels) when an RF event has no
    use label, because `use` has no index for "undefined"."""
    seq = _new()
    seq.add_block(
        pp.make_block_pulse(
            flip_angle=0.1, duration=0.2e-3, delay=SYSTEM.rf_dead_time, system=SYSTEM
        )
    )
    with pytest.raises(ValueError, match="rf_uses_labeled"):
        rf_table(seq)


# ---- 3. The pulse list and the other file-entry keys ----


def test_pulse_list_and_file_entry_keys():
    """The pulse list (task 5.3, item 2): an excitation and a refocusing pulse (sincs
    with gradients), a block pulse, and a pulse with a turning gradient. `pulses` equals
    `dataclasses.asdict` of `rf_profiles.pulse_list`, and the other keys of the file
    entry match their definitions. The body has one "Show" button for each pulse, with
    its `data-block`."""
    rf_ex, gz_ex, _ = _sinc("excitation")
    rf_ref, gz_ref, _ = _sinc("refocusing", math.pi, phase_offset=math.pi / 2)
    block = _hard("saturation", duration=0.4e-3)
    turn_x, turn_y = _turning_gradients()
    seq = _new()
    seq.set_definition("FOV", [0.2, 0.2, 0.2])
    seq.add_block(rf_ex, gz_ex)
    seq.add_block(rf_ref, gz_ref)
    seq.add_block(block)
    seq.add_block(_hard("inversion", duration=0.8e-3), turn_x, turn_y)

    entry = rf_profile_data(seq)
    assert entry["labeled"] is True
    assert entry["pulses"] == [dataclasses.asdict(p) for p in rp.pulse_list(seq)]
    assert len(entry["pulses"]) == 4
    assert entry["slice_thickness_m"] == W
    assert entry["fov_m"] == [0.2, 0.2, 0.2]
    assert entry["b0_t"] == float(SYSTEM.B0)
    assert entry["gamma_hz_per_t"] == abs(float(SYSTEM.gamma))
    assert entry["first_rf_block"] == 0

    without_fov = _new()
    without_fov.add_block(_hard("excitation", duration=0.4e-3))
    assert rf_profile_data(without_fov)["fov_m"] is None

    card = rf_profile_card(seq)
    assert card.body_html.count("<button") == len(entry["pulses"])
    for pulse in entry["pulses"]:
        assert f'data-block="{pulse["first_block"]}"' in card.body_html


# ---- 4. The options ----


def test_options_appear_in_the_data_as_given_and_the_defaults():
    """The options (task 5.3, item 3): views, plane and extent_m are in the data as
    given; the defaults give ["profile"], None and None."""
    seq = _new()
    seq.add_block(_hard("excitation", duration=0.4e-3))

    card = rf_profile_card(seq, views=("profile", "z_df", "2d"), plane=("x", "y"), extent_m=0.2)
    assert card.data["views"] == ["profile", "z_df", "2d"]
    assert card.data["plane"] == ["x", "y"]
    assert card.data["extent_m"] == 0.2

    default_card = rf_profile_card(seq)
    assert default_card.data["views"] == ["profile"]
    assert default_card.data["plane"] is None
    assert default_card.data["extent_m"] is None


def _one_sequence():
    seq = _new()
    seq.add_block(_hard("excitation", duration=0.4e-3))
    return seq


@pytest.mark.parametrize(
    "kwargs",
    [
        {"views": ("z_df",)},
        {"views": ("profile", "bogus")},
        {"views": ("profile", "profile")},
        {"plane": ("x",)},
        {"plane": ("x", "x")},
        {"plane": ("x", "w")},
        {"extent_m": 0},
        {"extent_m": -1},
        {"extent_m": math.nan},
        {"extent_m": math.inf},
    ],
    ids=[
        "views_without_profile",
        "unknown_view",
        "view_twice",
        "plane_one_name",
        "plane_same_name_twice",
        "plane_unknown_name",
        "extent_zero",
        "extent_negative",
        "extent_nan",
        "extent_inf",
    ],
)
def test_value_error_cases(kwargs):
    """The ValueError cases (task 5.3, item 3): views without "profile", an unknown view,
    a view twice, a bad plane and a bad extent_m."""
    with pytest.raises(ValueError):
        rf_profile_card(_one_sequence(), **kwargs)


# ---- 5. Rotations ----


def test_rf_profile_card_refuses_rotations():
    """Rotations (task 5.3, item 4): a sequence with a rotation library raises
    NotImplementedError, as the other gradient cards do (built as
    tests/test_extensions.py builds one)."""
    seq = _rotation_library_sequence()
    with pytest.raises(NotImplementedError, match="rotation extension"):
        rf_profile_card(seq)


# ---- 6. Two cards on one page ----


def test_two_cards_on_one_page_have_unique_ids():
    """Two cards on one page (task 5.3, item 5): different card_id, the same sequence: no
    id="..." value occurs twice in the page."""
    seq = _new()
    seq.add_block(_hard("excitation", duration=0.4e-3))

    card_a = rf_profile_card(seq, card_id="rf-a")
    card_b = rf_profile_card(seq, card_id="rf-b")
    result = page.render_page("Title", "Subtitle", [card_a, card_b])

    ids = re.findall(r'id="([^"]+)"', result)
    assert len(ids) == len(set(ids))


# ---- 7. Labels ----


def test_unlabeled_sequence_gets_a_note_and_no_profiles():
    """Labels (task 5.3, item 6): a sequence with one undefined pulse (and one labeled
    pulse, so the counts are "1 of 2"). No exception: the data has only the counts. The
    body has the note with the counts and no "Show" button. A labeled sequence has its
    full entry and no note."""
    labeled = _new()
    labeled.add_block(_hard("excitation", duration=0.4e-3))

    mixed = _new()
    mixed.add_block(_hard("excitation", duration=0.4e-3))
    mixed.add_block(
        pp.make_block_pulse(
            flip_angle=0.1, duration=0.2e-3, delay=SYSTEM.rf_dead_time, system=SYSTEM
        )
    )

    good = rf_profile_card(labeled)
    assert good.data["file"]["labeled"] is True and "rf" in good.data["file"]
    assert 'class="status bad"' not in good.body_html

    card = rf_profile_card(mixed)
    assert card.data["file"] == {"labeled": False, "unlabeled_rf_events": 1, "rf_events": 2}
    assert 'class="status bad"' in card.body_html
    assert "(1 of 2 RF events)" in card.body_html
    assert "<button" not in card.body_html


# ---- 8. The primary echo note ----


def test_primary_echo_note_matches_the_plan_text():
    """The primary echo pathway note (task 5.3, item 7): the element the card script
    fills with the combined profile holds the title and the note word for word, and the
    constant equals the text of section 4.3, item 7, of the plan (without its title),
    written here as a literal so that a change of the constant fails this test."""
    expected_note = (
        "This is the excitation |Mxy| times |β|² of each refocusing pulse before the "
        "first ADC of this period, with ideal crushers. It does not include the FID or "
        "stimulated-echo pathways, the later echoes of an echo train, the effect of "
        "preparation pulses, or relaxation."
    )
    assert PRIMARY_ECHO_NOTE == expected_note

    seq = _new()
    seq.add_block(_hard("excitation", duration=0.4e-3))
    card = rf_profile_card(seq, card_id="rf-profile")
    # The part of the body from the start of the combined element to the element that
    # the card script fills: the note must be there, not elsewhere in the body.
    combined = re.search(
        r'<div id="rf-profile-combined" hidden>(.*?)<div id="rf-profile-combined-body">',
        card.body_html,
        re.DOTALL,
    )
    assert combined is not None
    assert (
        f"<strong>{PRIMARY_ECHO_TITLE}</strong> {html.escape(PRIMARY_ECHO_NOTE)}"
        in combined.group(1)
    )


# ---- 9. A sequence without RF ----


def test_sequence_without_rf_has_an_empty_entry_and_no_pulses_note():
    """A sequence without RF: `first_rf_block` is None, the RF table has length 0 in
    every column, `pulses` is empty, and the body says "No RF pulses." for it."""
    seq = _new()
    seq.add_block(_trap("x", 100.0))
    seq.add_block(pp.make_delay(1e-3))

    entry = rf_profile_data(seq)
    assert entry["labeled"] is True
    assert entry["first_rf_block"] is None
    assert entry["pulses"] == []
    decoded = decode_tables(entry["rf"])
    for name, arr in decoded.items():
        assert arr.size == 0, name

    card = rf_profile_card(seq)
    assert '<p class="muted">No RF pulses.</p>' in card.body_html


# ---- 10. What the card script reads ----


def _spin_echo():
    """Excitation (sinc on z), a crusher, a refocusing pulse (sinc on y), a crusher and
    the readout."""
    rf_ex, gz_ex, _ = _sinc("excitation")
    rf_ref, gz_ref, _ = _sinc("refocusing", math.pi, phase_offset=math.pi / 2)
    gz_ref.channel = "y"
    gx, adc, _ = _readout()
    seq = _new()
    seq.add_block(rf_ex, gz_ex)
    seq.add_block(_trap("y", CRUSHER_AREA))
    seq.add_block(rf_ref, gz_ref)
    seq.add_block(_trap("y", CRUSHER_AREA))
    seq.add_block(gx, adc)
    return seq


def test_page_has_the_card_script_and_the_elements_it_reads():
    """A page with a diagram card and this card, for a spin echo
    (`assets/cards/rf-profile.js` is DOM code, with no Node test: decision 10 of
    `docs/plans/pulseq-reports.md`): the page has the card script once; the data has
    the keys of format 2 (no `diagram_card_id`); the body has the elements that the
    script reads by id (the status line with `aria-live`, the pulses element, the
    combined element, hidden, with the combined body inside it), and the primary echo
    note is the first paragraph of the combined element (the script hides that paragraph
    above a period without a combined profile). The "Show" buttons are exactly one for
    each distinct pulse, with `data-block` its first block and no `data-file`."""
    seq = _spin_echo()
    card = rf_profile_card(seq)
    result = page.render_page("Title", "Subtitle", [diagram_card(seq, [full_window(seq)]), card])

    assert result.count('PulseqReport.registerCard("rf-profile"') == 1
    assert page.card_asset("rf-profile") in result
    assert card.data["format"] == 2
    assert set(card.data) == {"format", "views", "plane", "extent_m", "file"}

    body = card.body_html
    assert '<p class="muted" id="rf-profile-status" aria-live="polite">' in body
    assert '<div id="rf-profile-pulses"></div>' in body
    combined = re.search(
        r'<div id="rf-profile-combined" hidden><h3>[^<]*</h3>\s*<p>(.*?)</p>\s*'
        r'<div id="rf-profile-combined-body"></div></div>',
        body,
        re.DOTALL,
    )
    assert combined is not None
    assert combined.group(1).startswith(f"<strong>{PRIMARY_ECHO_TITLE}</strong>")

    buttons = re.findall(r'<button type="button" data-block="(\d+)">', body)
    assert buttons == [str(p["first_block"]) for p in card.data["file"]["pulses"]]
    assert len(buttons) == body.count("<button")


def test_usage_md_has_the_primary_echo_note_word_for_word():
    """`docs/usage.md` has the primary echo note (task 5.3, item 7: the card HTML, the
    card script and the documents use one text): `PRIMARY_ECHO_TITLE` in bold, then
    `PRIMARY_ECHO_NOTE`, word for word, in a Markdown quote. The comparison drops the
    quote marks at the start of each line and joins the lines with one space, so the
    line breaks of the Markdown source do not matter."""
    usage = (Path(__file__).parent.parent / "docs" / "usage.md").read_text(encoding="utf-8")
    text = " ".join(line.removeprefix(">").strip() for line in usage.splitlines())
    text = re.sub(r"\s+", " ", text)
    assert f"**{PRIMARY_ECHO_TITLE}** {PRIMARY_ECHO_NOTE}" in text
