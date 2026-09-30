"""RF profile card: the RF pulses of the period at the cursor of the sequence diagram
card, simulated in the browser (`docs/plans/rf-profiles.md`, section 4.5).

This module builds the Python half of the card: the RF table, the pulse list of the
sequence, and the card's options. The card script (`assets/cards/rf-profile.js`) reads
this data with `RfProfiles` (`assets/rf_profiles.js`) and the sequence view of the
diagram card (`SeqLanes.sequenceView`), which it gets from the diagram's `sequence`
messages.

The card needs an RF use label on every RF event of the sequence (decision 22 of the
plan): `rf_profiles.rf_uses_labeled` tells the caller so before it adds the card. A
sequence without labels gets a note instead of profiles.
"""

import dataclasses
import html
import math
from collections.abc import Sequence

import numpy as np
import pypulseq as pp

from pulseq_reports import diagram_data, options
from pulseq_reports.extensions import refuse_rotations
from pulseq_reports.markup import fmt
from pulseq_reports.page import Card, card_asset
from pulseq_reports.registry import CardSpec, ReportContext
from pulseq_reports.rf_profiles import (
    _PHASE_ITEMS,
    _RF_COLUMN,
    _USE_OF_LETTER,
    USES,
    _definition,
    _require_labels,
    pulse_list,
    rf_uses_labeled,
)
from pulseq_reports.seq_index import rf_events, sequence_index
from pulseq_reports.seq_utils import hold_samples

VIEWS = ("profile", "z_df", "2d")
PUBLISHES = ("goto",)
SUBSCRIBES = ("sequence", "cursor", "anchor")
PRIMARY_ECHO_TITLE = "Primary echo pathway only."
PRIMARY_ECHO_NOTE = (
    "This is the excitation |Mxy| times |β|² of each refocusing pulse before the first "
    "ADC of this period, with ideal crushers. It does not include the FID or "
    "stimulated-echo pathways, the later echoes of an echo train, the effect of "
    "preparation pulses, or relaxation."
)

# The gradient kind, as the pulse list table shows it.
_GRADIENT_KIND_LABEL = {"none": "none", "one": "one direction", "changing": "changing"}
_PULSE_TABLE_HEADERS = (
    "Use",
    "Gradient",
    "First block",
    "Blocks",
    "Flip angle (°)",
    "Peak B1 (µT)",
    "Energy (µT²·ms)",
    "",
)
_PLANE_AXES = ("x", "y", "z")


class _ShapePool:
    """Distinct baseband RF shapes, each kept one time, matched by their exact complex128
    bytes: two events with the same baseband array share a position. In the spirit of
    `diagram_data._Pool`, which pools one real array at a time; this one keeps the real
    and imaginary parts of a complex array at the same position, for `shape_re` and
    `shape_im`."""

    def __init__(self) -> None:
        self._position: dict[bytes, int] = {}
        self._chunks: list[np.ndarray] = []
        self._length = 0

    def add(self, values: np.ndarray) -> int:
        arr = np.asarray(values, dtype=np.complex128)
        key = arr.tobytes()
        pos = self._position.get(key)
        if pos is not None:
            return pos
        pos = self._length
        self._position[key] = pos
        self._chunks.append(arr)
        self._length += arr.size
        return pos

    def arrays(self) -> tuple[np.ndarray, np.ndarray]:
        if not self._chunks:
            return np.empty(0, dtype=np.float64), np.empty(0, dtype=np.float64)
        combined = np.concatenate(self._chunks)
        return combined.real.copy(), combined.imag.copy()


def _rf_table(seq: pp.Sequence) -> dict[str, np.ndarray]:
    """The RF table of `seq` (section 4.5, item 2 of the plan): one row for each dense RF
    index `k` of `seq_index.sequence_index(seq)` (k = 1 .. K), at position k - 1, in
    dense order, plus two pools of baseband samples.

    Columns (dtype, value):

    - `key` (uint32): the id of the RF event without its phase offsets: the
      `seq.rf_library.data` row without `rf_profiles._PHASE_ITEMS` (phase_ppm,
      phase_offset), as a tuple of floats, with the use letter. Ids 0, 1, 2, ... in the
      order of first appearance. Two rows have the same id exactly when these tuples are
      equal (the RF part of `rf_profiles._pulse_key`, built the same way).
    - `use` (uint8): the index of the use in `rf_profiles.USES`.
    - `delay` (float64): `rf.delay`.
    - `shape_dur` (float64): `rf.shape_dur`.
    - `center` (float64): `pp.calc_rf_center(rf)[0]`, seconds from the start of the shape.
    - `dt` (float64): the hold interval of `seq_utils.hold_samples`.
    - `shape_at`, `shape_n` (uint32): the start and the length of this event's baseband
      samples in the pools.
    - `freq_hz`, `phase_rad` (float64): the total frequency and phase offsets, computed
      as `rf_profiles._pulse_core` computes them.
    - `shape_re`, `shape_im` (float64): the pools, the real and imaginary parts of the
      baseband samples (`hold_samples`, before any offset). A baseband array is stored
      one time: two events whose arrays have the same exact complex128 bytes share
      `shape_at`.

    A sequence without RF gives every column and both pools with length 0, with these
    dtypes. The card sends this table encoded by `diagram_data.encode_tables`.
    `RfProfiles` (the browser, `assets/rf_profiles.js`) reads it together with the
    sequence view of the diagram card (`SeqLanes.sequenceView`), whose dense RF index is
    the same as this table's.

    Raises `ValueError` when `rf_profiles.rf_uses_labeled(seq)` is False (the reference's
    own check, `rf_profiles._require_labels`): `use` has no index for `undefined`.
    """
    _require_labels(seq, "_rf_table")
    index = sequence_index(seq)
    n = index.rf_first.size

    key = np.zeros(n, dtype=np.uint32)
    use = np.zeros(n, dtype=np.uint8)
    delay = np.zeros(n, dtype=np.float64)
    shape_dur = np.zeros(n, dtype=np.float64)
    center = np.zeros(n, dtype=np.float64)
    dt = np.zeros(n, dtype=np.float64)
    shape_at = np.zeros(n, dtype=np.uint32)
    shape_n = np.zeros(n, dtype=np.uint32)
    freq_hz = np.zeros(n, dtype=np.float64)
    phase_rad = np.zeros(n, dtype=np.float64)

    gamma = abs(float(seq.system.gamma))
    ppm_hz = 1e-6 * gamma * float(seq.system.B0)
    use_index = {name: i for i, name in enumerate(USES)}
    keys: dict[tuple, int] = {}
    pool = _ShapePool()

    for k, rf in rf_events(seq, index):
        rf_id = int(seq.block_events[int(index.block_id[int(index.rf_first[k - 1])])][_RF_COLUMN])
        row = seq.rf_library.data[rf_id]
        letter = seq.rf_library.type.get(rf_id, "u")
        pulse_key = (
            tuple(float(v) for i, v in enumerate(row) if i not in _PHASE_ITEMS),
            letter,
        )
        if pulse_key not in keys:
            keys[pulse_key] = len(keys)

        i = k - 1
        key[i] = keys[pulse_key]
        use[i] = use_index[_USE_OF_LETTER[letter]]
        delay[i] = float(rf.delay)
        shape_dur[i] = float(rf.shape_dur)
        center[i] = float(pp.calc_rf_center(rf)[0])
        baseband, sample_dt = hold_samples(rf, seq.system.rf_raster_time)
        dt[i] = float(sample_dt)
        shape_at[i] = pool.add(baseband)
        shape_n[i] = baseband.size
        freq_hz[i] = float(rf.freq_offset) + float(getattr(rf, "freq_ppm", 0.0)) * ppm_hz
        phase_rad[i] = float(rf.phase_offset) + float(getattr(rf, "phase_ppm", 0.0)) * ppm_hz

    shape_re, shape_im = pool.arrays()
    return {
        "key": key,
        "use": use,
        "delay": delay,
        "shape_dur": shape_dur,
        "center": center,
        "dt": dt,
        "shape_at": shape_at,
        "shape_n": shape_n,
        "freq_hz": freq_hz,
        "phase_rad": phase_rad,
        "shape_re": shape_re,
        "shape_im": shape_im,
    }


def _rf_profile_data(seq: pp.Sequence) -> dict:
    """The file entry of the RF profile card data. `refuse_rotations(seq)` first.

    For a sequence where `rf_profiles.rf_uses_labeled(seq)` is True: `labeled`
    True; `slice_thickness_m` (the `SliceThickness` definition, or None);
    `fov_m` (the `FOV` definition as [x, y, z], or None); `b0_t`; `gamma_hz_per_t`
    (`abs(seq.system.gamma)`); `first_rf_block` (the play index of the first RF block,
    or None without RF); `rf` (`_rf_table(seq)`, encoded with `diagram_data.encode_tables`);
    `pulses` (`rf_profiles.pulse_list(seq)`, each pulse as `dataclasses.asdict`).

    For a sequence where it is False: `labeled` False; `unlabeled_rf_events` (the
    number of RF events whose use letter is not a key of `rf_profiles._USE_OF_LETTER`);
    `rf_events` (the number of RF events of the sequence). No other key, and no
    exception: the card shows a note instead of raising.
    """
    refuse_rotations(seq)
    if not rf_uses_labeled(seq):
        library = seq.rf_library
        unlabeled = sum(
            1 for rf_id in library.data if library.type.get(rf_id) not in _USE_OF_LETTER
        )
        return {
            "labeled": False,
            "unlabeled_rf_events": unlabeled,
            "rf_events": len(library.data),
        }

    index = sequence_index(seq)
    thickness = _definition(seq, "SliceThickness", 1)
    fov = _definition(seq, "FOV", 3)
    return {
        "labeled": True,
        "slice_thickness_m": None if thickness is None else float(thickness[0]),
        "fov_m": None if fov is None else [float(v) for v in fov],
        "b0_t": float(seq.system.B0),
        "gamma_hz_per_t": abs(float(seq.system.gamma)),
        "first_rf_block": int(index.rf_first[0]) if index.rf_first.size else None,
        "rf": diagram_data.encode_tables(_rf_table(seq)),
        "pulses": [dataclasses.asdict(p) for p in pulse_list(seq)],
    }


def _check_views(views: Sequence[str]) -> None:
    seen: set[str] = set()
    for v in views:
        if v not in VIEWS:
            raise ValueError(f"views must be one of {VIEWS}: {v!r}")
        if v in seen:
            raise ValueError(f"views has {v!r} twice")
        seen.add(v)
    if "profile" not in seen:
        raise ValueError('views must include "profile"')


def _check_plane(plane: tuple[str, str] | None) -> None:
    if plane is None:
        return
    if len(plane) != 2 or plane[0] == plane[1] or any(name not in _PLANE_AXES for name in plane):
        raise ValueError(f"plane must be two different axes of 'x', 'y', 'z': {plane!r}")


def _check_extent(extent_m: float | None) -> None:
    if extent_m is not None and not (math.isfinite(extent_m) and extent_m > 0):
        raise ValueError(f"extent_m must be a finite number above 0: {extent_m!r}")


def _unlabeled_note(entry: dict) -> str:
    """The note of section 4.5, item 1, for a sequence with RF pulses that have no use
    label, with its counts."""
    n, m = entry["unlabeled_rf_events"], entry["rf_events"]
    return (
        f'<p class="status bad">This file has RF pulses without a use label '
        f"({n} of {m} RF events). The RF profile card needs a use label on each RF pulse: "
        "set <code>use=</code> in the pypulseq <code>make_*_pulse</code> functions. A "
        "<code>.seq</code> file older than format 1.5 has no labels: read it with "
        "<code>detect_rf_use=True</code> for labels that pypulseq guesses from the flip "
        "angle, or set them by hand; see <code>docs/usage.md</code>.</p>"
    )


def _pulse_table(rows: list[list]) -> str:
    """The pulse list table: the markup of `markup.html_table`, written locally
    because the last cell holds a "Show" button, and `html_table` escapes every cell."""
    head = "".join(f"<th>{html.escape(h)}</th>" for h in _PULSE_TABLE_HEADERS)
    body = "".join(
        "<tr>"
        + "".join(f"<td>{html.escape(str(c))}</td>" for c in row[:-1])
        + f"<td>{row[-1]}</td></tr>"
        for row in rows
    )
    return f'<div class="scroll"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def _body_html(card_id: str, entry: dict) -> str:
    parts = [] if entry["labeled"] else [_unlabeled_note(entry)]
    parts.append(
        f'<p class="muted" id="{card_id}-status" aria-live="polite">Move the cursor over '
        "the sequence diagram to show the RF pulses of that period.</p>"
    )
    parts.append(f'<div id="{card_id}-pulses"></div>')
    parts.append(
        f'<div id="{card_id}-combined" hidden><h3>First echo: combined profile</h3>\n'
        f"<p><strong>{PRIMARY_ECHO_TITLE}</strong> {html.escape(PRIMARY_ECHO_NOTE)}</p>\n"
        f'<div id="{card_id}-combined-body"></div></div>'
    )
    parts.append("<h3>Distinct pulses</h3>")
    if entry["labeled"]:
        pulses = entry["pulses"]
        if not pulses:
            parts.append('<p class="muted">No RF pulses.</p>')
        else:
            rows = [
                [
                    p["use"],
                    _GRADIENT_KIND_LABEL[p["gradient_kind"]],
                    p["first_block"],
                    p["num_blocks"],
                    fmt(p["flip_deg"]),
                    fmt(p["peak_b1_ut"]),
                    fmt(p["energy_ut2_ms"]),
                    f'<button type="button" data-block="{p["first_block"]}">Show</button>',
                ]
                for p in pulses
            ]
            parts.append(_pulse_table(rows))
    return "\n".join(parts)


def rf_profile_card(
    seq: pp.Sequence,
    *,
    views: Sequence[str] = ("profile",),
    plane: tuple[str, str] | None = None,
    extent_m: float | None = None,
    card_id: str = "rf-profile",
) -> Card:
    """The "RF pulse profiles" card (`docs/plans/rf-profiles.md`, section 4.5): the RF
    pulses of the period at the cursor of the sequence diagram card of the page,
    simulated in the browser by the card script (`assets/cards/rf-profile.js`).

    The card follows the diagram only through the page's messages (`sequence`, `cursor`
    and `anchor`), so `seq` must be the sequence of the page's diagram card.

    `views` switches on the map views in addition to the always-shown 1D profile:
    `"z_df"` (the select coordinate against the frequency offset) and `"2d"` (two
    spatial axes). `plane` picks the two logical axes of the "2d" view of a pulse whose
    gradient direction changes during the RF (else the two axes with the largest RMS
    gradient); `extent_m` picks the extent of that view (else the `FOV` definition).

    The card's `scripts` has `assets/cards/rf-profile.js`. It publishes `PUBLISHES` (`goto`)
    and subscribes to `SUBSCRIBES` (`sequence`, `cursor` and `anchor`).

    Checks, before any other work:

    1. `views` has a name that is not in `VIEWS`, has a name twice, or does not have
       `"profile"`: `ValueError`.
    2. `plane` is not None and is not two different names of `("x", "y", "z")`:
       `ValueError` (the rule of `rf_profiles.view_spec`).
    3. `extent_m` is not None and is not a finite number above 0: `ValueError`.
    4. `refuse_rotations`: `NotImplementedError`.

    A sequence where `rf_profiles.rf_uses_labeled` is False gets a note in the body
    instead of profiles (section 4.5, item 1), and its data is only the count of RF
    events without a use label (`_rf_profile_data`); this does not raise. `card_id` is
    checked by `render_page`, as for the other cards.

    The body: a note for an unlabeled sequence, a status line that the card script
    fills, the elements for the pulses of the period at the cursor and the combined
    profile of the first echo (both empty here, and the combined one hidden, until the
    card script fills them), the note of section 4.3, item 7 (`PRIMARY_ECHO_TITLE`,
    `PRIMARY_ECHO_NOTE`: the first paragraph of the combined element, which the card
    script hides above a period without a combined profile), and a table of the
    distinct pulses of a labeled sequence, with a "Show" button in each row that the
    card script uses to move the diagram (`data-block` is the pulse's first block; the
    script sends `goto` with it).
    """
    _check_views(views)
    _check_plane(plane)
    _check_extent(extent_m)
    refuse_rotations(seq)

    file = _rf_profile_data(seq)
    data = {
        "format": 2,
        "views": list(views),
        "plane": None if plane is None else list(plane),
        "extent_m": None if extent_m is None else float(extent_m),
        "file": file,
    }
    body = _body_html(card_id, file)
    return Card(
        id=card_id,
        title="RF pulse profiles",
        body_html=body,
        data=data,
        script="rf-profile",
        scripts=(card_asset("rf-profile"),),
        publishes=PUBLISHES,
        subscribes=SUBSCRIBES,
    )


def _applies(ctx: ReportContext) -> bool:
    """The card needs RF use labels, and a selected card that publishes `anchor` (the
    diagram) to follow."""
    return rf_uses_labeled(ctx.seq) and ctx.publishes("anchor")


def _build(ctx: ReportContext) -> Card:
    return rf_profile_card(
        ctx.seq,
        views=ctx.option(options.views),
        plane=ctx.option(options.plane),
        extent_m=ctx.option(options.extent_m),
        card_id=SPEC.name,
    )


SPEC = CardSpec(
    "rf-profile",
    40,
    _build,
    (options.views, options.plane, options.extent_m),
    publishes=PUBLISHES,
    subscribes=SUBSCRIBES,
    when=_applies,
)
