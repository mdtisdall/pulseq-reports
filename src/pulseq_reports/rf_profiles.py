"""RF pulse profiles of a Pulseq sequence: the Python reference of
`docs/plans/rf-profiles.md` (sections 4.2 and 4.3).

The RF profile card computes the same values in the browser (`assets/rf_profiles.js`,
phase 3 of the plan). This module is the reference that a golden test holds the
JavaScript to, and the Python interface for other projects and CI gates.

- `block_pulse` reads the RF pulse of one block as played (with its offsets) and the
  gradients of its block, and gives its numbers and its echo pathway.
- `period` gives the period (the TR) that contains a block, and its distinct pulses.
- `view_spec` and `simulate` give the profile of a pulse on a grid of 1 or more axes.
- `combined_profile` gives the profile of the primary echo pathway of the first echo of
  a period: the excitation |Mxy| times |beta|^2 of each refocusing pulse before the ADC.
- `pulse_list` gives the distinct pulses of a file, for navigation.

Each function needs RF use labels on every RF event (`rf_uses_labeled`). No relaxation.
"""

import math
import operator
from collections.abc import Mapping
from dataclasses import dataclass, field

import numpy as np
import pypulseq as pp
from pulseq_analysis.extensions import refuse_rotations
from pulseq_analysis.seq_index import SequenceIndex, block_cache_off, sequence_index
from pulseq_analysis.seq_utils import TIME_TOLERANCE, gradient_points, hold_samples

from pulseq_reports import profile_metrics
from pulseq_reports.rf_sim import crushed_echo, magnetization, precess, spin_domain

USES = ("excitation", "refocusing", "inversion", "saturation", "preparation", "other")
AXIS_KINDS = ("x", "y", "z", "select", "df")
MAX_POINTS = 65_536  # 256 x 256, the most points of one simulation
NUM_POSITIONS = 401  # the points of a 1D profile (as vb-pulseq did)
MAP_POINTS = 128  # the points on each axis of a 2D map
PERIOD_MAX_BLOCKS = 100_000  # the longest walk of `period` in each direction
PARALLEL_TOL = 1e-9  # relative: a gradient vector parallel to the mean direction
CONSTANT_TOL = 1e-9  # relative: a gradient vector equal to the mean vector
SPECTRUM_PADDING = 64  # zero padding of the RF spectrum (as vb-pulseq did)
PHASE_MIN_FRACTION = 0.1  # the phase is shown where |Mxy| >= this * max |Mxy|
PASSBAND_FRACTION = 0.4  # the phase fits use |u - c| <= this * W

# The reasons that the card shows. The JavaScript uses the same text.
NO_ADC = "no ADC before the next excitation"
OTHER_RF_BEFORE_ADC = (
    "an RF pulse that is not a refocusing pulse lies between this pulse and the ADC"
)
DIRECTION_CHANGES = "the gradient direction changes during the RF"
NO_FOV = "no FOV definition: give extent_m"
NO_SLICE_THICKNESS = "no SliceThickness definition"

# More reasons and notes. The JavaScript copies the same text.
_NO_GRADIENT_Z_DF = "no gradient: the profile against Δf is the 1D profile"
_NO_MAP_ONE = "the gradient has one direction: a 2d map of this pulse is only stripes"
_NO_MAP_NONE = "no gradient: a 2d map of this pulse is uniform"
_OFF_CENTRE_CHANGES = (
    "the gradient changes during the RF: an off-centre slice is not a shift of this profile"
)
_NO_EXCITATION = "no excitation before the first ADC of the period"
_NO_REFOCUSING = "no refocusing pulse between the excitation and the ADC"
_THREE_OBLIQUE = "the combined profile of three oblique directions is not supported"
_MORE_THAN_THREE = "the pulses have more than three directions"

# pypulseq keeps the first letter of the use in `rf_library.type`, and "u" for
# `undefined`. `Sequence.get_block` reads a missing or unknown letter as `undefined`.
_USE_OF_LETTER = {use[0]: use for use in USES}
_AXIS_NAMES = ("x", "y", "z")
_GRAD_ATTRS = ("gx", "gy", "gz")
# The columns of a row of `seq.block_events` (the same as in seq_index).
_RF_COLUMN = 1
_GRAD_COLUMNS = (2, 3, 4)
# The items of an `rf_library` row: (amplitude, mag_id, phase_id, time_id, center,
# delay, freq_ppm, phase_ppm, freq_offset, phase_offset).
_PHASE_ITEMS = (7, 9)  # phase_ppm, phase_offset: not in the pulse key
_NUM_OFFSET_FREE_ITEMS = 6  # items 0 to 5: the RF event without any offset
# The z x df grid of a constant gradient is one 1D simulation when the df step is |G|
# times the step of the select coordinate within this relative tolerance.
_SHEAR_RTOL = 1e-12


@dataclass(frozen=True, eq=False)
class EchoPathway:
    """The primary echo pathway from the end of an RF pulse to the centre of the first
    ADC after it (decision 8 of the plan)."""

    moment_per_m: np.ndarray  # (3,) x y z: the gradient moment from the RF end to the
    # ADC centre, with a sign change at the centre of each refocusing pulse
    sign: int  # (-1) ** (the number of refocusing pulses): -1 means Mxy is conjugated
    adc_block: int  # the play index of the block of that ADC


@dataclass(frozen=True, eq=False)
class BlockPulse:
    """The RF pulse of one block, as played, with the gradients of its block."""

    block: int  # the play index (0 is the first block)
    use: str  # one of USES
    signal_hz: np.ndarray  # (n,) complex: hold_samples, times the total offsets
    dt_s: float
    grad_hz_per_m: np.ndarray  # (n, 3): the mean gradient of each hold interval
    gradient_kind: str  # "none", "one" or "changing"
    select_kind: str | None  # "x", "y", "z" or "select" for kind "one", else None
    direction: np.ndarray | None  # (3,) the unit vector u of the mean gradient (kind "one")
    select_gradient_hz_per_m: float | None  # G: the signed amplitude on the logical
    # axis, or |mean| for "select" (kind "one")
    constant_gradient: bool  # each interval vector equals the mean (CONSTANT_TOL); False
    # for the kinds "none" and "changing"
    freq_offset_hz: float  # the total frequency offset f
    slice_centre_m: float | None  # f / G (kind "one")
    flip_deg: float  # from the RF without its offsets (the flip angle at the slice centre)
    peak_b1_ut: float
    energy_ut2_ms: float
    nominal_m: float | None  # W: the SliceThickness definition
    fov_m: tuple[float, float, float] | None  # the FOV definition
    key: tuple  # the pulse key (section 2.5 of the plan), hashable
    echo: EchoPathway | None  # excitation pulses only
    echo_reason: str | None  # why `echo` is None for an excitation pulse
    # Notes for the card: NO_SLICE_THICKNESS for kind "one" without W, and a note when
    # a gradient of kind "one" that is not constant plays with a frequency offset.
    notes: tuple[str, ...] = ()


@dataclass(frozen=True)
class PeriodPulse:
    """One distinct pulse of a period: the RF blocks of the period with one pulse key."""

    key: tuple
    use: str
    first_block: int
    last_block: int
    count: int


@dataclass(frozen=True)
class Period:
    """The blocks from one period start to the block before the next one (decision 20)."""

    first_block: int
    last_block: int
    pulses: tuple[PeriodPulse, ...]  # in the order of their first block
    first_adc_block: int | None
    truncated: bool  # a walk stopped after PERIOD_MAX_BLOCKS blocks


@dataclass(frozen=True)
class ProfileAxis:
    kind: str  # one of AXIS_KINDS
    lo: float  # m for positions, Hz for df
    hi: float
    n: int


@dataclass(frozen=True)
class ProfileSpec:
    axes: tuple[ProfileAxis, ...]
    at: Mapping[str, float] = field(default_factory=dict)  # kinds that are not axes


@dataclass(frozen=True, eq=False)
class Profile:
    spec: ProfileSpec
    grid: tuple[np.ndarray, ...]  # the values of each axis (numpy.linspace)
    a: np.ndarray  # complex, shape (n1, n2, ...)
    b: np.ndarray


@dataclass(frozen=True, eq=False)
class CombinedMap:
    """One map of the combined profile: two position axes, values (n1, n2).

    The axis kinds are logical axes ("x", "y", "z") when both directions of the map are
    logical axes. When a direction is oblique, they are "s1" (along the first direction)
    and "s2" (perpendicular to it, in the plane of the two directions). "s1" and "s2" are
    not in AXIS_KINDS: they are only for maps of the combined profile.
    """

    axes: tuple[ProfileAxis, ProfileAxis]
    values: np.ndarray


@dataclass(frozen=True, eq=False)
class CombinedProfile:
    """The profile of the primary echo pathway of the first echo of a period (decision
    21): the excitation |Mxy| times |beta|^2 of each refocusing pulse between that
    excitation and the first ADC of the period, with ideal crushers."""

    reason: str | None  # None when there is a combined profile
    excitation_block: int | None
    refocusing_blocks: tuple[int, ...]
    factor: float  # the product of |beta|^2 at df = 0 of the refocusing pulses of kind "none"
    # (and the |Mxy| at r = 0, df = 0 of an excitation of kind "none"); NaN with a reason
    directions: tuple[str, ...]  # the select kind of each distinct direction
    line: tuple[np.ndarray, np.ndarray] | None  # (u, values): one direction only
    # (block, values) of each pulse of the line's direction, in play order: the arrays
    # whose product (times `factor`) is the line's values. Empty without a line.
    line_pulses: tuple[tuple[int, np.ndarray], ...]
    maps: tuple[CombinedMap, ...]  # view "2d" only: 1 map for 2 directions, 3 for 3
    numbers: dict[str, float]


@dataclass(frozen=True)
class PulseSummary:
    """One distinct pulse of a file, for the pulse list: the RF event without all its
    offsets, and the gradient events during the RF."""

    first_block: int
    num_blocks: int
    use: str
    gradient_kind: str
    flip_deg: float
    peak_b1_ut: float
    energy_ut2_ms: float


def rf_uses_labeled(seq: pp.Sequence) -> bool:
    """False when an RF event of `seq` has no use label (`undefined`).

    Reads only `seq.rf_library.type`, so the cost does not grow with the number of
    blocks. A sequence without RF events is labeled (True). pypulseq stores the letter
    "u" for `undefined`; an RF event without a letter, or with a letter that is not the
    first letter of one of USES, also counts as `undefined` (`Sequence.get_block` reads
    it so).
    """
    library = seq.rf_library
    return all(library.type.get(rf_id) in _USE_OF_LETTER for rf_id in library.data)


def block_pulse(
    seq: pp.Sequence, block: int, *, max_blocks: int = PERIOD_MAX_BLOCKS
) -> BlockPulse | None:
    """The RF pulse of the block at play index `block`, or None when it has no RF.

    Section 4.2 of the plan, items 1 to 7:

    1. `extensions.refuse_rotations(seq)` first. `ValueError` when
       `rf_uses_labeled(seq)` is False.
    2. The RF as played: `seq_utils.hold_samples(rf, seq.rf_raster_time)` times
       `exp(1j * (phase + 2*pi*f*t))`, with t = (k + 0.5) * dt from the start of the
       shape, f = freq_offset + freq_ppm * 1e-6 * |gamma| * B0 and the same form for the
       phase (`seq.system.gamma`, `seq.system.B0`).
    3. The gradient of each hold interval: for each axis, the exact integral over
       [rf.delay + k*dt, rf.delay + (k+1)*dt] of the piecewise-linear gradient of the
       block (`seq_utils.gradient_points(g, 0.0)`, zero outside the event), divided by dt.
    4. The gradient kind, the select kind, the direction, G and `constant_gradient`.
    5. The numbers, with |gamma| of the sequence for µT.
    6. The pulse key: the rf_library row without phase_offset and phase_ppm, the use,
       and the pypulseq ids of the gradient events whose time in the block overlaps
       [rf.delay, rf.delay + shape_dur] (0 for no such event on an axis).
    7. The echo pathway of an excitation pulse. Walk forward in play order from the RF
       end: add the gradient moment (x y z); at the centre of each refocusing RF
       (block start + rf.delay + pp.calc_rf_center(rf)[0]), change the sign of the
       moment and count it. Stop at the centre of the first ADC (adc.delay +
       num_samples * dwell / 2 in its block): the pathway. Stop at the start of an
       excitation RF, or at the end of the file: None, reason NO_ADC. An RF labeled
       inversion, saturation, preparation or other before the ADC: None, reason
       OTHER_RF_BEFORE_ADC.

    Choices that the plan leaves open:

    - A gradient event "plays during the RF" (items 3 and 6) when its time
      [g.delay, pp.calc_duration(g)] overlaps [rf.delay, rf.delay + shape_dur] by more
      than `seq_utils.TIME_TOLERANCE`. Only those events give interval gradients and
      key ids. A `.seq` file keeps times in µs, so after a file round trip a spoiler that
      ends where the RF starts can end 1e-19 s after the RF start; without the tolerance
      it would count as a gradient of the pulse.
    - The flip angle, the peak B1 and the energy use the RF without its offsets: a
      frequency offset moves the slice, and the flip angle at the slice centre does not
      change. So blocks that differ only in their offsets have the same numbers.
    - The echo walk (item 7) looks at most `max_blocks` blocks after this block; then it
      stops with NO_ADC. An ADC in this block counts when its centre is not before the
      RF end. When an ADC centre and an RF event of one block have the same time, the ADC
      comes first.

    `IndexError` when `block` is not a play index of `seq`.
    """
    refuse_rotations(seq)
    _require_labels(seq, "block_pulse")
    _check_max_blocks(max_blocks)
    index = sequence_index(seq)
    i = _play_index(index, block)
    return _block_pulse(seq, index, i, with_echo=True, max_blocks=max_blocks)


def period(seq: pp.Sequence, block: int, *, max_blocks: int = PERIOD_MAX_BLOCKS) -> Period:
    """The period that contains the block at play index `block` (decision 20).

    A block is a period start when it has an RF that is not a refocusing pulse, and the
    last block before it with an RF or an ADC has an ADC; the first block with an RF is
    always a start. A block with both an RF and an ADC counts its ADC after its RF.
    Before the first period start, the first period. So an echo train (a TSE) is one
    period: its refocusing pulses never start one. The walk in each direction stops after PERIOD_MAX_BLOCKS blocks, and then
    `truncated` is True. `ValueError` when `rf_uses_labeled(seq)` is False; a sequence
    without RF: `ValueError`.

    `refuse_rotations(seq)` first. `max_blocks` replaces PERIOD_MAX_BLOCKS (for tests):
    the backward walk looks at the `max_blocks` blocks before `block`, and the forward
    walk at the `max_blocks` blocks after `block` (or after the first period start, for
    a block before it). A truncated period starts or ends at that limit. The distinct
    pulses group the RF blocks of the period by the pulse key (`BlockPulse.key`).
    `IndexError` when `block` is not a play index of `seq`.

    The rule uses the ADCs and one use label, "refocusing" (decision 20 of the plan, as
    revised on 2026-09-28: the card needs the labels anyway, decision 22).
    """
    refuse_rotations(seq)
    _require_labels(seq, "period")
    _check_max_blocks(max_blocks)
    index = sequence_index(seq)
    i = _play_index(index, block)
    if index.rf_first.size == 0:
        raise ValueError("period: the sequence has no RF pulse, so it has no period")

    truncated = False
    first_rf = int(index.rf_first[0])  # the first block with an RF: always a start
    refocusing = _refocusing_rf(seq, index)
    if i < first_rf:
        first = first_rf
    else:
        lo = max(0, i - max_blocks)
        events = _events_in(index, lo, i + 1)
        starts = _starts_among(
            index, events, _last_event_before(index, lo, max_blocks), refocusing, first_rf
        )
        if starts.size:
            first = int(starts[-1])
        else:
            # The first RF block is a start before `lo`, so the period starts before the
            # limit of the walk.
            first, truncated = lo, True

    anchor = max(first, i)
    hi = min(index.num_blocks, anchor + max_blocks + 1)
    events = _events_in(index, first, hi)
    starts = _starts_among(
        index, events, _last_event_before(index, first, max_blocks), refocusing, first_rf
    )
    later = starts[starts > anchor]
    if later.size:
        last = int(later[0]) - 1
    elif hi == index.num_blocks:
        last = hi - 1
    else:
        last, truncated = hi - 1, True

    adc_blocks = first + np.flatnonzero(index.adc[first : last + 1] > 0)
    rf_blocks = first + np.flatnonzero(index.rf[first : last + 1] > 0)
    return Period(
        first_block=first,
        last_block=last,
        pulses=_period_pulses(seq, index, rf_blocks),
        first_adc_block=int(adc_blocks[0]) if adc_blocks.size else None,
        truncated=truncated,
    )


def view_spec(
    pulse: BlockPulse,
    view: str = "profile",
    *,
    plane: tuple[str, str] | None = None,
    extent_m: float | None = None,
    n: int | None = None,
) -> tuple[ProfileSpec | None, str | None]:
    """The spec of a view of `pulse` and None, or None and the reason (section 4.3).

    - "profile": kind "one": the select coordinate from c - 2W to c + 2W (c the slice
      centre), n = NUM_POSITIONS; without W, the half range is 2 times the thickness
      from the RF spectrum (the FWHM of the zero-padded spectrum / |G|). Kind "none":
      df from f - 2B to f + 2B, B the FWHM of the RF spectrum. Kind "changing": None,
      DIRECTION_CHANGES.
    - "z_df": kind "one" only: the select coordinate of "profile" with
      (NUM_POSITIONS + 1) // 2 points, and df with the same number of points, centred on
      0 Hz, with the step |G| times the step of the select coordinate.
    - "2d": kind "changing" only: two logical axes (`plane`, else the two with the
      largest RMS gradient during the RF), each from -e/2 to +e/2 with MAP_POINTS
      points, e = `extent_m`, else the FOV definition of that axis; with neither: None,
      NO_FOV.

    `n` replaces the number of points of each axis.

    The RF spectrum is that of `pulse.signal_hz` (the RF as played): an offset moves the
    spectrum and does not change its FWHM. Without `plane`, the two axes are in the
    order x, y, z. `ValueError` for an unknown view, a bad `plane`, `extent_m` <= 0, or
    `n` < 2.
    """
    if view not in ("profile", "z_df", "2d"):
        raise ValueError(f"view must be 'profile', 'z_df' or '2d': {view!r}")
    _check_n(n)
    kind = pulse.gradient_kind
    if view == "profile":
        if kind == "changing":
            return None, DIRECTION_CHANGES
        points = n or NUM_POSITIONS
        if kind == "none":
            half = 2 * _spectrum_fwhm_hz(pulse.signal_hz, pulse.dt_s)
            f = pulse.freq_offset_hz
            return ProfileSpec((ProfileAxis("df", f - half, f + half, points),)), None
        lo, hi = _select_range(pulse)
        return ProfileSpec((ProfileAxis(pulse.select_kind, lo, hi, points),)), None

    if view == "z_df":
        if kind == "none":
            return None, _NO_GRADIENT_Z_DF
        if kind == "changing":
            return None, DIRECTION_CHANGES
        points = n or (NUM_POSITIONS + 1) // 2
        lo, hi = _select_range(pulse)
        step = abs(pulse.select_gradient_hz_per_m) * (hi - lo) / (points - 1)
        half = (points - 1) / 2 * step
        axes = (
            ProfileAxis(pulse.select_kind, lo, hi, points),
            ProfileAxis("df", -half, half, points),
        )
        return ProfileSpec(axes), None

    if kind == "one":
        return None, _NO_MAP_ONE
    if kind == "none":
        return None, _NO_MAP_NONE
    if plane is None:
        rms = np.sqrt(np.mean(pulse.grad_hz_per_m**2, axis=0))
        top = sorted(np.argsort(-rms, kind="stable")[:2].tolist())
        plane = (_AXIS_NAMES[top[0]], _AXIS_NAMES[top[1]])
    elif len(plane) != 2 or plane[0] == plane[1] or any(name not in _AXIS_NAMES for name in plane):
        raise ValueError(f"plane must be two different axes of 'x', 'y', 'z': {plane!r}")
    if extent_m is not None:
        if not (math.isfinite(extent_m) and extent_m > 0):
            raise ValueError(f"extent_m must be a positive length (m): {extent_m!r}")
        extents = (float(extent_m), float(extent_m))
    elif pulse.fov_m is not None:
        extents = tuple(pulse.fov_m[_AXIS_NAMES.index(name)] for name in plane)
    else:
        return None, NO_FOV
    points = n or MAP_POINTS
    axes = tuple(ProfileAxis(name, -e / 2, e / 2, points) for name, e in zip(plane, extents))
    return ProfileSpec(axes), None


def simulate(pulse: BlockPulse, spec: ProfileSpec) -> Profile:
    """The profile of `pulse` on the grid of `spec` (`rf_sim.spin_domain`).

    `ValueError` for a spec that breaks a rule of section 4.2 of the plan ("Specs").
    A "z_df" spec of a pulse with a constant gradient, whose df step is |G| times the
    step of the select coordinate, is computed as one 1D simulation of the distinct
    values u + df / G (the same values as the whole grid, within float rounding).

    The grid: numpy.linspace(lo, hi, n) for each axis, numpy.meshgrid with
    indexing="ij", flattened in C order. A position that is not an axis is its `at`
    value, else 0 m; df is its axis or its `at` value, else 0 Hz. A "select" value s is
    the position s * `pulse.direction`. A spec without axes is one point.
    """
    _check_spec(pulse, spec)
    grid, shape, count, values = _grid_values(spec)
    sheared = _shear_simulation(pulse, spec)
    if sheared is not None:
        a, b = sheared
    else:
        positions = _positions(pulse, values, count)
        a, b = spin_domain(
            pulse.signal_hz, pulse.dt_s, pulse.grad_hz_per_m, positions, values.get("df")
        )
    return Profile(spec=spec, grid=grid, a=a.reshape(shape), b=b.reshape(shape))


def quantity(profile: Profile, name: str) -> np.ndarray:
    """ "mxy_abs", "mz" or "beta_sq" of `profile`, with the shape of its grid."""
    if name == "mxy_abs":
        return np.abs(magnetization(profile.a, profile.b)[0])
    if name == "mz":
        return magnetization(profile.a, profile.b)[1]
    if name == "beta_sq":
        return crushed_echo(profile.b)
    raise ValueError(f"quantity must be 'mxy_abs', 'mz' or 'beta_sq': {name!r}")


def echo_phase(
    pulse: BlockPulse, profile: Profile, *, echo_moment_per_m: np.ndarray | None = None
) -> np.ndarray | None:
    """The phase (rad) of the primary echo of an excitation `pulse` along its "profile"
    view, relative to its value at the slice centre (the grid point nearest to it), NaN
    where |Mxy| < PHASE_MIN_FRACTION * max |Mxy|. The echo Mxy is
    `precess(mxy, moment, r)`, or `precess(conj(mxy), moment, r)` when the pathway sign
    is -1. `echo_moment_per_m` replaces the pathway: that moment and the sign +1.
    None when the pulse is not an excitation, not of kind "one", or has no pathway and
    no replacement. `ValueError` when `profile` is not a 1D profile along the select
    coordinate of `pulse`, or `echo_moment_per_m` is not 3 values.
    """
    echo = _echo_mxy(pulse, profile, echo_moment_per_m)
    if echo is None:
        return None
    u = profile.grid[0]
    centre = int(np.argmin(np.abs(u - pulse.slice_centre_m)))
    phase = np.angle(echo * np.exp(-1j * np.angle(echo[centre])))
    magnitude = np.abs(echo)
    phase[magnitude < PHASE_MIN_FRACTION * magnitude.max()] = np.nan
    return phase


def widths(
    pulse: BlockPulse, profile: Profile, *, echo_moment_per_m: np.ndarray | None = None
) -> dict[str, float]:
    """The numbers of a 1D "profile" view (section 4.3, item 6), in the units of its
    axis: "fwhm" and "edge_width" of the profile for the widths; "passband_ripple" and
    "stopband_level" on the select coordinate with W; for an excitation with a pathway
    (or `echo_moment_per_m`) and W: "rephasing_error_rad", "nonlinear_residual_rad" and
    "centre_phase_rad". A key is missing when its number does not apply.

    The profile for the widths, by use: excitation |Mxy|, refocusing |beta|^2, inversion
    (1 - Mz) / 2, saturation 1 - Mz, preparation and other |Mxy|. The position numbers
    use u - c (c the slice centre), because `profile_metrics` puts the slice at 0.

    - "rephasing_error_rad": the slope of the weighted least-squares line (minimum of
      sum(w * residual**2), w = |Mxy|) through the unwrapped echo phase over
      |u - c| <= PASSBAND_FRACTION * W, times W.
    - "nonlinear_residual_rad": the peak-to-peak of the unwrapped echo phase minus that
      line, over the same points.
    - "centre_phase_rad": the angle of the echo Mxy at the grid point nearest to c.

    "passband_ripple" and "stopband_level" are missing when the grid has no point in
    their region; the fit numbers need at least 2 points in |u - c| <= 0.4 W.
    `ValueError` when `profile` has more than one axis, or a position axis that is not
    the select coordinate of `pulse`.
    """
    axes = profile.spec.axes
    if len(axes) != 1:
        raise ValueError("widths needs a 1D profile (the 'profile' view)")
    kind = axes[0].kind
    if kind != "df" and kind != pulse.select_kind:
        raise ValueError(f"widths needs a profile along the select coordinate or df, not {kind!r}")
    x = profile.grid[0]
    main = _width_profile(pulse.use, profile)
    out = {
        "fwhm": float(profile_metrics.fwhm(x, main)),
        "edge_width": float(profile_metrics.edge_width(x, main)),
    }
    nominal = pulse.nominal_m
    if kind == "df" or nominal is None:
        return out
    rel = x - pulse.slice_centre_m
    if np.any(np.abs(rel) <= 0.4 * nominal):
        out["passband_ripple"] = float(profile_metrics.passband_ripple(rel, main, nominal))
    if np.any(np.abs(rel) >= nominal):
        out["stopband_level"] = float(profile_metrics.stopband_level(rel, main, nominal))
    echo = _echo_mxy(pulse, profile, echo_moment_per_m)
    if echo is not None:
        out.update(_phase_numbers(rel, echo, nominal))
    return out


def combined_profile(
    seq: pp.Sequence, per: Period, *, view: str = "profile", n: int | None = None
) -> CombinedProfile:
    """The combined profile of the first echo of `per` (section 4.3, item 7).

    `reason` is set, and the other fields are empty, when there is none: no ADC in the
    period, no excitation before the first ADC, no refocusing pulse between them, a
    pulse of kind "changing", or an RF of another use between them. `view="2d"` also
    gives the maps. `n` replaces the number of points of each axis.

    The pulses: the excitation is the last excitation block of the period at or before
    the first ADC block (a block with both counts its ADC after its RF); the refocusing
    pulses are the RF blocks after it up to that ADC block. A pulse of kind "none" is a
    factor: its value at r = 0, df = 0 (|beta|^2, or |Mxy| for the excitation).

    The directions: the select directions of the pulses of kind "one", in the order of
    the pulses. Two directions are the same when |u1 x u2| <= PARALLEL_TOL (parallel or
    antiparallel). A direction is named by the select kind of its first pulse. Each
    pulse is simulated at the 3D points of the grid (`rf_sim.spin_domain`), at df = 0.

    - No direction (all pulses of kind "none"): only numbers["centre_signal"] = factor.
    - One direction: `line` = (u, values) on the grid of the "profile" view of the first
      pulse of the direction, and `line_pulses` = (block, values) of each pulse of the
      direction at those points (|Mxy| of the excitation, |beta|^2 of a refocusing
      pulse), in play order; `line`'s values are their product times `factor`, in that
      order. numbers: "fwhm_m" and "edge_width_m" of the line,
      "signal_kept" = trapezoid(values) / trapezoid(excitation |Mxy|) over the grid,
      "fraction_inside" (with W) = the sum of values over |u - c| <= W / 2 divided by
      the sum over the grid (sums, as vb-pulseq did), "centre_signal" = values
      interpolated at c; c is the slice centre of the first pulse of the direction.
    - Two or three directions: `line` None and `line_pulses` empty. For each
      direction, the product of its
      pulses on the union of their "profile" ranges (n or NUM_POSITIONS points).
      numbers: "fraction_inside" (with W) = the product over directions of each
      direction's fraction inside |u - c| <= W / 2, "centre_signal" = the product over
      directions of each line interpolated at its c, times `factor`.
    - Three directions must all be logical axes; more than three: a reason.

    The maps (view "2d", MAP_POINTS or n points on each axis, the ranges of the lines):
    two logical directions: axes in the order x, y, z, values = the outer product of the
    products of each direction on its map axis, times `factor`. A pair with an oblique
    direction: axes "s1" (the first direction) and "s2" (perpendicular to it, in the plane
    of both); the "s2" range puts the range of the second direction at s1 = c1; each pulse
    is simulated at each 3D grid point. Three directions: the maps x-y, x-z and y-z, each
    through the slice centre of the third direction (the product of the third direction
    at exactly its c is a factor).
    """
    if view not in ("profile", "2d"):
        raise ValueError(f"view must be 'profile' or '2d': {view!r}")
    _check_n(n)
    refuse_rotations(seq)
    _require_labels(seq, "combined_profile")
    index = sequence_index(seq)

    adc_block = per.first_adc_block
    if adc_block is None:
        return _no_combined(NO_ADC)
    rf_blocks = per.first_block + np.flatnonzero(index.rf[per.first_block : adc_block + 1] > 0)
    uses = [_block_use(seq, index, int(p)) for p in rf_blocks]
    excitations = [k for k, use in enumerate(uses) if use == "excitation"]
    if not excitations:
        return _no_combined(_NO_EXCITATION)
    k0 = excitations[-1]
    if any(use != "refocusing" for use in uses[k0 + 1 :]):
        return _no_combined(OTHER_RF_BEFORE_ADC)
    refocusing_blocks = tuple(int(p) for p in rf_blocks[k0 + 1 :])
    if not refocusing_blocks:
        return _no_combined(_NO_REFOCUSING)

    excitation_block = int(rf_blocks[k0])
    pulses = [
        _block_pulse(seq, index, p, with_echo=False, max_blocks=0)
        for p in (excitation_block, *refocusing_blocks)
    ]
    if any(p.gradient_kind == "changing" for p in pulses):
        return _no_combined(DIRECTION_CHANGES)

    factor = 1.0
    for p in pulses:
        if p.gradient_kind == "none":
            factor *= float(_pulse_values(p, np.zeros((1, 3)))[0])
    directions = _directions(pulses)
    if len(directions) > 3:
        return _no_combined(_MORE_THAN_THREE)
    if len(directions) == 3 and any(d.kind not in _AXIS_NAMES for d in directions):
        return _no_combined(_THREE_OBLIQUE)

    nominal = pulses[0].nominal_m
    line = None
    line_pulses: tuple[tuple[int, np.ndarray], ...] = ()
    maps: tuple[CombinedMap, ...] = ()
    if not directions:
        numbers = {"centre_signal": factor}
    elif len(directions) == 1:
        line, line_pulses, numbers = _one_direction(pulses[0], directions[0], factor, nominal, n)
    else:
        numbers = _several_directions(directions, factor, nominal, n)
        if view == "2d":
            maps = _combined_maps(directions, factor, n)
    return CombinedProfile(
        reason=None,
        excitation_block=excitation_block,
        refocusing_blocks=refocusing_blocks,
        factor=factor,
        directions=tuple(d.kind for d in directions),
        line=line,
        line_pulses=line_pulses,
        maps=maps,
        numbers=numbers,
    )


def pulse_list(seq: pp.Sequence) -> list[PulseSummary]:
    """The distinct pulses of `seq`, in the order of their first block: the blocks with
    RF grouped by the RF event without all its offsets (the rf_library row without
    freq_ppm, phase_ppm, freq_offset and phase_offset, and the use) and the gradient
    events that play during the RF. Uses `seq_index.sequence_index`, and reads each
    distinct pulse one time, so the cost grows with the number of distinct events, not
    blocks, apart from numpy work on the index columns.

    "Play during the RF" is the rule of `block_pulse` (an overlap longer than
    `seq_utils.TIME_TOLERANCE`). The numbers and the gradient kind of a distinct pulse
    are those of its first block. `refuse_rotations(seq)` first; `ValueError` when
    `rf_uses_labeled(seq)` is False.
    """
    refuse_rotations(seq)
    _require_labels(seq, "pulse_list")
    index = sequence_index(seq)
    rf_blocks = np.flatnonzero(index.rf > 0)
    if rf_blocks.size == 0:
        return []

    # The offset-free key of each dense RF event (a lookup of its first block's row).
    # Its time span depends only on items of that key (the shapes and the delay), so one
    # event of each key is read.
    num_rf = index.rf_first.size
    key_of_rf = np.zeros(num_rf + 1, dtype=np.int64)
    keys: dict[tuple, int] = {}
    first_rf_of_key: list[int] = []
    for k in range(1, num_rf + 1):
        block_id = int(index.block_id[index.rf_first[k - 1]])
        rf_id = int(seq.block_events[block_id][_RF_COLUMN])
        row = seq.rf_library.data[rf_id]
        key = (
            tuple(float(v) for v in row[:_NUM_OFFSET_FREE_ITEMS]),
            seq.rf_library.type.get(rf_id, "u"),
        )
        if key not in keys:
            keys[key] = len(keys)
            first_rf_of_key.append(k)
        key_of_rf[k] = keys[key]
    rf_start = np.zeros(len(keys))
    rf_end = np.zeros(len(keys))
    for key_id, k in enumerate(first_rf_of_key):
        rf = _read_block(seq, index, int(index.rf_first[k - 1])).rf
        rf_start[key_id] = float(rf.delay)
        rf_end[key_id] = float(rf.delay) + float(rf.shape_dur)

    # The time span of each dense gradient event that is in a block with RF.
    grad_cols = [getattr(index, attr)[rf_blocks].astype(np.int64) for attr in _GRAD_ATTRS]
    num_grad = index.grad_first.size
    g_start = np.zeros(num_grad + 1)
    g_end = np.zeros(num_grad + 1)
    _grad_spans(seq, index, rf_blocks, grad_cols, g_start, g_end)

    rf_key = key_of_rf[index.rf[rf_blocks].astype(np.int64)]
    start, end = rf_start[rf_key], rf_end[rf_key]
    masked = [
        np.where(
            (ids > 0)
            & (g_start[ids] < end - TIME_TOLERANCE)
            & (g_end[ids] > start + TIME_TOLERANCE),
            ids,
            0,
        )
        for ids in grad_cols
    ]
    rows = np.stack([rf_key, *masked], axis=1)
    _, first_index, counts = _unique_rows(rows)
    order = np.argsort(first_index, kind="stable")

    summaries = []
    for g in order.tolist():
        i = int(rf_blocks[first_index[g]])
        core = _pulse_core(seq, _read_block(seq, index, i))
        summaries.append(
            PulseSummary(
                first_block=i,
                num_blocks=int(counts[g]),
                use=core.use,
                gradient_kind=core.kind,
                flip_deg=core.flip_deg,
                peak_b1_ut=core.peak_b1_ut,
                energy_ut2_ms=core.energy_ut2_ms,
            )
        )
    return summaries


# ---- Private helpers ----


@dataclass(frozen=True, eq=False)
class _PulseCore:
    """What `block_pulse` and `pulse_list` read from one block with RF."""

    use: str
    signal: np.ndarray  # as played
    dt: float
    grad: np.ndarray  # (n, 3)
    kind: str
    select_kind: str | None
    direction: np.ndarray | None
    select_gradient: float | None
    constant: bool
    freq_offset: float
    flip_deg: float
    peak_b1_ut: float
    energy_ut2_ms: float


@dataclass(eq=False)
class _Direction:
    """One distinct select direction of the pulses of a combined profile."""

    kind: str  # the select kind of its first pulse: "x", "y", "z" or "select"
    unit: np.ndarray  # the direction of its first pulse
    pulses: list[BlockPulse]
    signs: list[float]  # +1 or -1: the direction of each pulse relative to `unit`


def _require_labels(seq: pp.Sequence, name: str) -> None:
    if not rf_uses_labeled(seq):
        raise ValueError(
            f"{name} needs a use label on each RF event, and this sequence has an RF "
            "event with the use 'undefined' (rf_uses_labeled is False): set use= in "
            "the pypulseq make_*_pulse functions"
        )


def _check_max_blocks(max_blocks: int) -> None:
    if operator.index(max_blocks) < 1:
        raise ValueError(f"max_blocks must be at least 1: {max_blocks!r}")


def _check_n(n: int | None) -> None:
    if n is not None and operator.index(n) < 2:
        raise ValueError(f"n must be at least 2: {n!r}")


def _play_index(index: SequenceIndex, block: int) -> int:
    i = operator.index(block)
    if not 0 <= i < index.num_blocks:
        raise IndexError(
            f"block {block} is not a play index: the sequence has {index.num_blocks} blocks"
        )
    return i


def _read_block(seq: pp.Sequence, index: SequenceIndex, i: int):
    """The pypulseq block at play index `i`, without filling pypulseq's block cache."""
    with block_cache_off(seq):
        return seq.get_block(int(index.block_id[i]))


def _block_use(seq: pp.Sequence, index: SequenceIndex, i: int) -> str:
    """The use of the RF event of the block at play index `i`, from the library only."""
    rf_id = int(seq.block_events[int(index.block_id[i])][_RF_COLUMN])
    return _USE_OF_LETTER.get(seq.rf_library.type.get(rf_id), "undefined")


def _definition(seq: pp.Sequence, name: str, size: int) -> np.ndarray | None:
    """The definition `name` as `size` positive floats, or None when it is missing or is
    not such a value."""
    value = seq.definitions.get(name)
    if value is None:
        return None
    try:
        values = np.asarray(value, dtype=float).reshape(-1)
    except (TypeError, ValueError):
        return None
    if values.size != size or not np.all(np.isfinite(values)) or np.any(values <= 0):
        return None
    return values


def _plays_during(g, rf_start: float, rf_end: float) -> bool:
    """True when the gradient event `g` plays during the RF (block times): its time
    [g.delay, calc_duration(g)] overlaps [rf_start, rf_end] by more than TIME_TOLERANCE
    (see `block_pulse`)."""
    return (
        float(g.delay) < rf_end - TIME_TOLERANCE
        and float(pp.calc_duration(g)) > rf_start + TIME_TOLERANCE
    )


def _piecewise_integral(
    t: np.ndarray, g: np.ndarray, a: np.ndarray, b: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """The integral over each interval [a, b] (a <= b) of the piecewise-linear function
    through the points (t, g), which is 0 outside [t[0], t[-1]]; and its mean where the
    whole interval is inside one segment of that function, else NaN.

    Repeated times (a step) are segments of zero length, with integral 0. The mean over
    one segment is the value at the middle of the interval (the mean of a linear
    function), so on a flat top it is exactly the flat-top amplitude.
    Across a corner, the integral is the part in the first segment, the whole segments
    between (a cumulative trapezoid), and the part in the last segment.
    """
    t = np.asarray(t, dtype=float)
    g = np.asarray(g, dtype=float)
    a = np.atleast_1d(np.asarray(a, dtype=float))
    b = np.atleast_1d(np.asarray(b, dtype=float))
    if t.size < 2:
        return np.zeros(a.shape), np.full(a.shape, np.nan)
    lo = np.clip(a, t[0], t[-1])
    hi = np.clip(b, t[0], t[-1])
    last = t.size - 2
    # The segment that holds lo (t[i0] <= lo < t[i0 + 1]) and the one that holds hi
    # (t[i1] < hi <= t[i1 + 1]); at a step, lo is after it and hi is before it.
    i0 = np.clip(np.searchsorted(t, lo, side="right") - 1, 0, last)
    i1 = np.clip(np.searchsorted(t, hi, side="left") - 1, 0, last)

    def value(x: np.ndarray, i: np.ndarray) -> np.ndarray:
        span = t[i + 1] - t[i]
        slope = np.where(span > 0, (g[i + 1] - g[i]) / np.where(span > 0, span, 1.0), 0.0)
        return g[i] + (x - t[i]) * slope

    cumulative = np.concatenate(([0.0], np.cumsum(np.diff(t) * (g[1:] + g[:-1]) / 2)))
    same = i0 == i1
    mid = value((lo + hi) / 2, i0)
    head = (t[i0 + 1] - lo) * (value(lo, i0) + g[i0 + 1]) / 2
    tail = (hi - t[i1]) * (g[i1] + value(hi, i1)) / 2
    several = head + (cumulative[i1] - cumulative[i0 + 1]) + tail
    total = np.where(hi > lo, np.where(same, (hi - lo) * mid, several), 0.0)
    inside = same & (hi > lo) & (a >= t[0]) & (b <= t[-1])
    return total, np.where(inside, mid, np.nan)


def _gradient_kind(grad: np.ndarray):
    """(kind, select kind, direction, G, constant) of the interval gradients (n, 3)."""
    if not np.any(grad):
        return "none", None, None, None, False
    mean = grad.mean(axis=0)
    norm = float(np.linalg.norm(mean))
    if norm > 0:
        unit = mean / norm
        peak = float(np.max(np.linalg.norm(grad, axis=1)))
        across = grad - np.outer(grad @ unit, unit)
        if np.all(np.linalg.norm(across, axis=1) <= PARALLEL_TOL * peak):
            constant = bool(np.max(np.abs(grad - mean)) <= CONSTANT_TOL * norm)
            on = [j for j in range(3) if np.any(grad[:, j] != 0)]
            if len(on) == 1:
                j = on[0]
                direction = np.zeros(3)
                direction[j] = 1.0
                return "one", _AXIS_NAMES[j], direction, float(mean[j]), constant
            return "one", "select", unit, norm, constant
    # A mean of zero (for example a bipolar gradient on one axis) has no direction.
    return "changing", None, None, None, False


def _pulse_core(seq: pp.Sequence, blk) -> _PulseCore:
    rf = blk.rf
    gamma = abs(float(seq.system.gamma))
    ppm_hz = 1e-6 * gamma * float(seq.system.B0)
    # The file's raster ([DEFINITIONS]): `Sequence.read` does not change `seq.system`.
    baseband, dt = hold_samples(rf, seq.rf_raster_time)
    dt = float(dt)
    n = baseband.size
    f = float(rf.freq_offset) + float(getattr(rf, "freq_ppm", 0.0)) * ppm_hz
    phase = float(rf.phase_offset) + float(getattr(rf, "phase_ppm", 0.0)) * ppm_hz
    t = (np.arange(n) + 0.5) * dt
    signal = baseband * np.exp(1j * (phase + 2 * np.pi * f * t))

    rf_start = float(rf.delay)
    rf_end = rf_start + float(rf.shape_dur)
    edges = rf_start + np.arange(n + 1) * dt
    grad = np.zeros((n, 3))
    for j, attr in enumerate(_GRAD_ATTRS):
        g = getattr(blk, attr)
        if g is not None and _plays_during(g, rf_start, rf_end):
            times, amp = gradient_points(g, 0.0)
            total, mid = _piecewise_integral(times, amp, edges[:-1], edges[1:])
            grad[:, j] = np.where(np.isnan(mid), total / dt, mid)
    kind, select_kind, direction, select_gradient, constant = _gradient_kind(grad)

    b1_ut = np.abs(baseband) / gamma * 1e6
    return _PulseCore(
        use=rf.use,
        signal=signal,
        dt=dt,
        grad=grad,
        kind=kind,
        select_kind=select_kind,
        direction=direction,
        select_gradient=select_gradient,
        constant=constant,
        freq_offset=f,
        flip_deg=float(np.degrees(2 * np.pi * abs(baseband.sum() * dt))),
        peak_b1_ut=float(b1_ut.max()),
        energy_ut2_ms=float(np.sum(b1_ut**2) * dt * 1e3),
    )


def _pulse_key(seq: pp.Sequence, block_id: int, blk) -> tuple:
    """The pulse key (section 2.5 of the plan) of the block `block_id`."""
    events = seq.block_events[block_id]
    rf_id = int(events[_RF_COLUMN])
    row = seq.rf_library.data[rf_id]
    rf_items = tuple(float(v) for k, v in enumerate(row) if k not in _PHASE_ITEMS)
    rf_start = float(blk.rf.delay)
    rf_end = rf_start + float(blk.rf.shape_dur)
    grads = []
    for column, attr in zip(_GRAD_COLUMNS, _GRAD_ATTRS, strict=True):
        g = getattr(blk, attr)
        playing = g is not None and _plays_during(g, rf_start, rf_end)
        grads.append(int(events[column]) if playing else 0)
    return (rf_items, seq.rf_library.type.get(rf_id, "u"), tuple(grads))


def _block_pulse(
    seq: pp.Sequence, index: SequenceIndex, i: int, *, with_echo: bool, max_blocks: int
) -> BlockPulse | None:
    if index.rf[i] == 0:
        return None
    blk = _read_block(seq, index, i)
    core = _pulse_core(seq, blk)
    thickness = _definition(seq, "SliceThickness", 1)
    nominal = None if thickness is None else float(thickness[0])
    fov = _definition(seq, "FOV", 3)

    notes = []
    centre = None
    if core.kind == "one":
        centre = core.freq_offset / core.select_gradient
        if nominal is None:
            notes.append(NO_SLICE_THICKNESS)
        if not core.constant and core.freq_offset != 0:
            notes.append(_OFF_CENTRE_CHANGES)
    echo, reason = None, None
    if with_echo and core.use == "excitation":
        echo, reason = _echo_pathway(seq, index, i, blk, max_blocks)
    return BlockPulse(
        block=i,
        use=core.use,
        signal_hz=core.signal,
        dt_s=core.dt,
        grad_hz_per_m=core.grad,
        gradient_kind=core.kind,
        select_kind=core.select_kind,
        direction=core.direction,
        select_gradient_hz_per_m=core.select_gradient,
        constant_gradient=core.constant,
        freq_offset_hz=core.freq_offset,
        slice_centre_m=centre,
        flip_deg=core.flip_deg,
        peak_b1_ut=core.peak_b1_ut,
        energy_ut2_ms=core.energy_ut2_ms,
        nominal_m=nominal,
        fov_m=None if fov is None else tuple(float(v) for v in fov),
        key=_pulse_key(seq, int(index.block_id[i]), blk),
        echo=echo,
        echo_reason=reason,
        notes=tuple(notes),
    )


def _echo_pathway(
    seq: pp.Sequence, index: SequenceIndex, i: int, blk, max_blocks: int
) -> tuple[EchoPathway | None, str | None]:
    """The echo pathway of the excitation in the block at play index `i` (`block_pulse`,
    item 7). Block by block in play order, in block times: the moments add in the same
    order as a walk in file time. A block without RF and ADC adds the whole integral of
    each of its gradient events, which is kept for each dense event, so such a block is
    read only for a gradient event that the walk has not seen."""
    moment = np.zeros(3)
    count = 0
    whole: dict[int, float] = {}

    def add(block, a: float, b: float) -> None:
        for j, attr in enumerate(_GRAD_ATTRS):
            g = getattr(block, attr)
            if g is not None:
                times, amp = gradient_points(g, 0.0)
                moment[j] += float(_piecewise_integral(times, amp, a, b)[0][0])

    def walk(block, start: float, duration: float, own: bool) -> str | None:
        """Adds the moments of `block` after `start`; returns "adc", a reason, or None
        to go on."""
        nonlocal count
        events = []
        rf = block.rf
        if rf is not None and not own:
            if rf.use == "refocusing":
                events.append((rf.delay + pp.calc_rf_center(rf)[0], 1, "refocusing"))
            elif rf.use == "excitation":
                events.append((rf.delay, 1, NO_ADC))
            else:
                events.append((rf.delay, 1, OTHER_RF_BEFORE_ADC))
        adc = block.adc
        if adc is not None:
            centre = adc.delay + adc.num_samples * adc.dwell / 2
            if centre >= start:
                events.append((centre, 0, "adc"))
        at = start
        for time, _, what in sorted(events):
            add(block, at, float(time))
            at = float(time)
            if what != "refocusing":
                return what
            moment[:] = -moment
            count += 1
        add(block, at, duration)
        return None

    def result(stop: str, j: int):
        if stop == "adc":
            return EchoPathway(moment_per_m=moment.copy(), sign=(-1) ** count, adc_block=j), None
        return None, stop

    rf = blk.rf
    stop = walk(blk, float(rf.delay) + float(rf.shape_dur), float(index.duration_s[i]), True)
    if stop is not None:
        return result(stop, i)
    last = min(index.num_blocks - 1, i + max_blocks)
    for j in range(i + 1, last + 1):
        if index.rf[j] == 0 and index.adc[j] == 0:
            ids = (int(index.gx[j]), int(index.gy[j]), int(index.gz[j]))
            if any(k and k not in whole for k in ids):
                block = _read_block(seq, index, j)
                for k, attr in zip(ids, _GRAD_ATTRS, strict=True):
                    if k and k not in whole:
                        times, amp = gradient_points(getattr(block, attr), 0.0)
                        whole[k] = float(_piecewise_integral(times, amp, times[0], times[-1])[0][0])
            for axis, k in enumerate(ids):
                if k:
                    moment[axis] += whole[k]
            continue
        stop = walk(_read_block(seq, index, j), 0.0, float(index.duration_s[j]), False)
        if stop is not None:
            return result(stop, j)
    return None, NO_ADC


def _events_in(index: SequenceIndex, lo: int, hi: int) -> np.ndarray:
    """The play indexes in [lo, hi) of the blocks with an RF or an ADC."""
    return lo + np.flatnonzero((index.rf[lo:hi] > 0) | (index.adc[lo:hi] > 0))


def _last_event_before(index: SequenceIndex, pos: int, chunk: int) -> int:
    """The play index of the last block before `pos` with an RF or an ADC, or -1. It
    looks back `chunk` blocks at a time."""
    hi = pos
    while hi > 0:
        lo = max(0, hi - chunk)
        found = _events_in(index, lo, hi)
        if found.size:
            return int(found[-1])
        hi = lo
    return -1


def _refocusing_rf(seq: pp.Sequence, index: SequenceIndex) -> np.ndarray:
    """A bool for each dense RF index (index 0 is "no RF"): True for a refocusing pulse.
    Reads the use letter of each RF event from `seq.rf_library.type`, through the first
    block that uses it, so no block is read."""
    refocusing = np.zeros(index.rf_first.size + 1, dtype=bool)
    for k, p in enumerate(index.rf_first.tolist(), start=1):
        rf_id = int(seq.block_events[int(index.block_id[p])][_RF_COLUMN])
        refocusing[k] = seq.rf_library.type.get(rf_id, "u") == "r"
    return refocusing


def _starts_among(
    index: SequenceIndex, events: np.ndarray, before: int, refocusing: np.ndarray, first_rf: int
) -> np.ndarray:
    """The period starts among `events`: all the blocks with an RF or an ADC in a range,
    in play order; `before` is the last such block before them, or -1. `refocusing`
    marks the dense RF indexes of refocusing pulses (`_refocusing_rf`), which never
    start a period; `first_rf`, the first block with an RF, always does."""
    if events.size == 0:
        return events
    has_adc = index.adc[events] > 0
    last_was_adc = np.empty(events.size, dtype=bool)
    last_was_adc[0] = before < 0 or bool(index.adc[before] > 0)
    # A block with both counts its ADC after its RF: its own ADC does not matter for
    # itself, and it makes the next RF block a start.
    last_was_adc[1:] = has_adc[:-1]
    rf = index.rf[events]
    starts = (rf > 0) & ~refocusing[rf] & last_was_adc
    return events[starts | (events == first_rf)]


def _period_pulses(
    seq: pp.Sequence, index: SequenceIndex, rf_blocks: np.ndarray
) -> tuple[PeriodPulse, ...]:
    """The RF blocks `rf_blocks` grouped by pulse key, in the order of their first block.
    The key is computed once for each distinct (RF, gx, gy, gz) dense combination."""
    if rf_blocks.size == 0:
        return ()
    rows = np.stack(
        [getattr(index, name)[rf_blocks].astype(np.int64) for name in ("rf", *_GRAD_ATTRS)],
        axis=1,
    )
    inverse, first_index, _ = _unique_rows(rows)
    groups: dict[tuple, list[int]] = {}
    for c in np.argsort(first_index, kind="stable").tolist():
        i = int(rf_blocks[first_index[c]])
        key = _pulse_key(seq, int(index.block_id[i]), _read_block(seq, index, i))
        groups.setdefault(key, []).append(c)
    pulses = []
    for key, combos in groups.items():
        blocks = rf_blocks[np.isin(inverse, combos)]
        pulses.append(
            PeriodPulse(
                key=key,
                use=_USE_OF_LETTER.get(key[1], "undefined"),
                first_block=int(blocks[0]),
                last_block=int(blocks[-1]),
                count=int(blocks.size),
            )
        )
    pulses.sort(key=lambda p: p.first_block)
    return tuple(pulses)


def _unique_rows(rows: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(inverse, first index, count) of the distinct rows of a non-negative int64 array.
    The rows are one int64 code when their values fit, which is faster than
    numpy.unique(axis=0)."""
    top = rows.max(axis=0).astype(object) + 1
    size = 1
    for v in top:
        size *= int(v)
    if size < 2**62:
        code = np.zeros(rows.shape[0], dtype=np.int64)
        for col, base in zip(rows.T, top, strict=True):
            code = code * int(base) + col
        _, first, inverse, counts = np.unique(
            code, return_index=True, return_inverse=True, return_counts=True
        )
    else:
        _, first, inverse, counts = np.unique(
            rows, axis=0, return_index=True, return_inverse=True, return_counts=True
        )
    return inverse.reshape(-1), first, counts


def _grad_spans(
    seq: pp.Sequence,
    index: SequenceIndex,
    rf_blocks: np.ndarray,
    grad_cols: list[np.ndarray],
    g_start: np.ndarray,
    g_end: np.ndarray,
) -> None:
    """Fills the block time span [delay, calc_duration] of each dense gradient event
    that is in a block with RF. Reads one block for each such event (or fewer, when
    events share a block)."""
    ids = np.concatenate(grad_cols)
    axes = np.repeat(np.arange(3), rf_blocks.size)
    positions = np.tile(rf_blocks, 3)
    used = ids > 0
    unique_ids, first = np.unique(ids[used], return_index=True)
    if unique_ids.size == 0:
        return
    at_block = positions[used][first]
    at_axis = axes[used][first]
    order = np.argsort(at_block, kind="stable")
    block, current = None, -1
    for k in order.tolist():
        i = int(at_block[k])
        if i != current:
            block, current = _read_block(seq, index, i), i
        g = getattr(block, _GRAD_ATTRS[int(at_axis[k])])
        g_start[unique_ids[k]] = float(g.delay)
        g_end[unique_ids[k]] = float(pp.calc_duration(g))


def _spectrum_fwhm_hz(signal: np.ndarray, dt: float) -> float:
    """The FWHM (Hz) of the zero-padded RF spectrum (plan section 4.3, item 1; the
    thickness from it is FWHM / |G|, as vb-pulseq did)."""
    n = SPECTRUM_PADDING * signal.size
    spectrum = np.abs(np.fft.fftshift(np.fft.fft(signal, n)))
    freqs = np.fft.fftshift(np.fft.fftfreq(n, dt))
    return float(profile_metrics.fwhm(freqs, spectrum))


def _select_range(pulse: BlockPulse) -> tuple[float, float]:
    """The select-coordinate range of the "profile" view of a pulse of kind "one"."""
    if pulse.nominal_m is not None:
        half = 2 * pulse.nominal_m
    else:
        thickness = _spectrum_fwhm_hz(pulse.signal_hz, pulse.dt_s) / abs(
            pulse.select_gradient_hz_per_m
        )
        half = 2 * thickness
    c = pulse.slice_centre_m
    return c - half, c + half


def _check_spec(pulse: BlockPulse, spec: ProfileSpec) -> None:
    kinds = [axis.kind for axis in spec.axes] + list(spec.at)
    for kind in kinds:
        if kind not in AXIS_KINDS:
            raise ValueError(f"a spec kind must be one of {AXIS_KINDS}: {kind!r}")
    if len(set(kinds)) != len(kinds):
        raise ValueError(f"each kind at most once in the axes and `at` together: {kinds}")
    if "select" in kinds:
        if any(name in kinds for name in _AXIS_NAMES):
            raise ValueError("'select' cannot be in a spec together with 'x', 'y' or 'z'")
        if pulse.select_kind != "select":
            raise ValueError(
                "'select' needs a pulse whose select coordinate is 'select' (a gradient "
                f"of kind 'one' on more than one axis); this pulse has {pulse.select_kind!r}"
            )
    total = 1
    for axis in spec.axes:
        if isinstance(axis.n, bool) or not isinstance(axis.n, (int, np.integer)):
            raise TypeError(f"the number of points must be an int: {axis.n!r}")
        if axis.n < 2:
            raise ValueError(f"an axis needs at least 2 points: {axis}")
        if not (math.isfinite(axis.lo) and math.isfinite(axis.hi) and axis.lo < axis.hi):
            raise ValueError(f"an axis needs finite lo < hi: {axis}")
        total *= int(axis.n)
    for kind, value in spec.at.items():
        if not math.isfinite(float(value)):
            raise ValueError(f"the `at` value of {kind!r} must be finite: {value!r}")
    if total > MAX_POINTS:
        raise ValueError(f"the grid has {total} points, more than MAX_POINTS = {MAX_POINTS}")


def _grid_values(spec: ProfileSpec):
    """(grid, shape, count, values): the values of each kind at each point, C order."""
    grid = tuple(np.linspace(axis.lo, axis.hi, axis.n) for axis in spec.axes)
    shape = tuple(int(axis.n) for axis in spec.axes)
    count = math.prod(shape)
    values: dict[str, np.ndarray] = {}
    if grid:
        meshes = np.meshgrid(*grid, indexing="ij")
        for axis, mesh in zip(spec.axes, meshes, strict=True):
            values[axis.kind] = mesh.ravel()
    for kind, value in spec.at.items():
        values[kind] = np.full(count, float(value))
    return grid, shape, count, values


def _positions(pulse: BlockPulse, values: dict[str, np.ndarray], count: int) -> np.ndarray:
    """The (count, 3) positions of the points: x, y, z from their values (else 0), or the
    "select" value times the pulse direction."""
    positions = np.zeros((count, 3))
    for j, name in enumerate(_AXIS_NAMES):
        if name in values:
            positions[:, j] = values[name]
    if "select" in values:
        positions += np.outer(values["select"], pulse.direction)
    return positions


def _shear_simulation(pulse: BlockPulse, spec: ProfileSpec):
    """(a, b) of a z x df spec as one 1D simulation (section 2.3 of the plan), or None
    when the spec is not such a grid. With a constant gradient G, the point (u, df) has
    the rotation of the point v = u + df / G at df = 0. With the df step equal to |G|
    times the u step, v(i, j) = (u_lo + df_lo / G) + (i + sign(G) * j) * du: only
    n_u + n_df - 1 distinct values."""
    axes = spec.axes
    if (
        pulse.gradient_kind != "one"
        or not pulse.constant_gradient
        or len(axes) != 2
        or axes[0].kind != pulse.select_kind
        or axes[1].kind != "df"
    ):
        return None
    u_axis, f_axis = axes
    g = pulse.select_gradient_hz_per_m
    du = (u_axis.hi - u_axis.lo) / (u_axis.n - 1)
    step = (f_axis.hi - f_axis.lo) / (f_axis.n - 1)
    if abs(step - abs(g) * du) > _SHEAR_RTOL * abs(g) * du:
        return None
    sign = 1 if g > 0 else -1
    m = np.arange(u_axis.n)[:, None] + sign * np.arange(f_axis.n)[None, :]
    m_min = int(m.min())
    count = u_axis.n + f_axis.n - 1
    v = (u_axis.lo + f_axis.lo / g) + np.arange(m_min, m_min + count) * du
    values = {pulse.select_kind: v}
    for kind, value in spec.at.items():
        values[kind] = np.full(count, float(value))
    positions = _positions(pulse, values, count)
    a, b = spin_domain(pulse.signal_hz, pulse.dt_s, pulse.grad_hz_per_m, positions)
    return a[m - m_min], b[m - m_min]


def _echo_mxy(
    pulse: BlockPulse, profile: Profile, echo_moment_per_m: np.ndarray | None
) -> np.ndarray | None:
    """The Mxy of the primary echo at each point of a 1D select-coordinate profile."""
    if pulse.use != "excitation" or pulse.gradient_kind != "one":
        return None
    axes = profile.spec.axes
    if len(axes) != 1 or axes[0].kind != pulse.select_kind:
        raise ValueError("the echo phase needs the 1D 'profile' view of the pulse")
    if echo_moment_per_m is not None:
        moment = np.asarray(echo_moment_per_m, dtype=float)
        if moment.shape != (3,):
            raise ValueError(f"echo_moment_per_m must be 3 values (x y z): {moment.shape}")
        sign = 1
    elif pulse.echo is not None:
        moment, sign = pulse.echo.moment_per_m, pulse.echo.sign
    else:
        return None
    _, _, count, values = _grid_values(profile.spec)
    positions = _positions(pulse, values, count)
    mxy = magnetization(profile.a, profile.b)[0].reshape(-1)
    return precess(mxy if sign > 0 else np.conj(mxy), moment, positions)


def _width_profile(use: str, profile: Profile) -> np.ndarray:
    """The profile for the widths, by use (section 4.3, item 2, of the plan)."""
    if use == "refocusing":
        return crushed_echo(profile.b)
    mxy, mz = magnetization(profile.a, profile.b)
    if use == "inversion":
        return (1 - mz) / 2
    if use == "saturation":
        return 1 - mz
    return np.abs(mxy)


def _phase_numbers(rel: np.ndarray, echo: np.ndarray, nominal: float) -> dict[str, float]:
    out = {"centre_phase_rad": float(np.angle(echo[int(np.argmin(np.abs(rel)))]))}
    region = np.abs(rel) <= PASSBAND_FRACTION * nominal
    if np.count_nonzero(region) < 2:
        return out
    x = rel[region]
    y = np.unwrap(np.angle(echo[region]))
    w = np.abs(echo[region])
    total = w.sum()
    if total > 0:
        x_mean = (w * x).sum() / total
        y_mean = (w * y).sum() / total
        dx = x - x_mean
        spread = (w * dx * dx).sum()
        if spread > 0:
            slope = (w * dx * (y - y_mean)).sum() / spread
            line = y_mean + slope * dx
            out["rephasing_error_rad"] = float(slope * nominal)
            out["nonlinear_residual_rad"] = float(np.ptp(y - line))
    return out


def _no_combined(reason: str) -> CombinedProfile:
    return CombinedProfile(
        reason=reason,
        excitation_block=None,
        refocusing_blocks=(),
        factor=math.nan,
        directions=(),
        line=None,
        line_pulses=(),
        maps=(),
        numbers={},
    )


def _pulse_values(pulse: BlockPulse, positions: np.ndarray) -> np.ndarray:
    """|Mxy| of an excitation, or |beta|^2 of a refocusing pulse, at `positions` (m, 3)
    and df = 0."""
    a, b = spin_domain(pulse.signal_hz, pulse.dt_s, pulse.grad_hz_per_m, positions)
    if pulse.use == "excitation":
        return np.abs(magnetization(a, b)[0])
    return crushed_echo(b)


def _directions(pulses: list[BlockPulse]) -> list[_Direction]:
    directions: list[_Direction] = []
    for p in pulses:
        if p.gradient_kind != "one":
            continue
        for d in directions:
            if np.linalg.norm(np.cross(d.unit, p.direction)) <= PARALLEL_TOL:
                d.pulses.append(p)
                d.signs.append(1.0 if float(d.unit @ p.direction) > 0 else -1.0)
                break
        else:
            directions.append(_Direction(p.select_kind, p.direction, [p], [1.0]))
    return directions


def _direction_points(d: _Direction, u: np.ndarray) -> np.ndarray:
    """The 3D points at the coordinates `u` along the direction `d`. For a logical axis,
    the same arrays as `simulate` makes for a "profile" view, so the values are equal."""
    if d.kind in _AXIS_NAMES:
        positions = np.zeros((u.size, 3))
        positions[:, _AXIS_NAMES.index(d.kind)] = u
        return positions
    return np.outer(u, d.unit)


def _direction_product(d: _Direction, positions: np.ndarray) -> np.ndarray:
    values = np.ones(positions.shape[0])
    for p in d.pulses:
        values = values * _pulse_values(p, positions)
    return values


def _direction_range(d: _Direction, n: int | None) -> tuple[float, float]:
    """The union of the "profile" ranges of the pulses of `d`, in its coordinate."""
    lows, highs = [], []
    for p, s in zip(d.pulses, d.signs, strict=True):
        spec, _ = view_spec(p, "profile", n=n)
        lo, hi = spec.axes[0].lo, spec.axes[0].hi
        lows.append(lo if s > 0 else -hi)
        highs.append(hi if s > 0 else -lo)
    return min(lows), max(highs)


def _fraction_inside(u: np.ndarray, values: np.ndarray, centre: float, nominal: float) -> float:
    inside = np.abs(u - centre) <= nominal / 2
    return float(values[inside].sum() / values.sum())


def _one_direction(
    excitation: BlockPulse, d: _Direction, factor: float, nominal: float | None, n: int | None
):
    first = d.pulses[0]
    spec, _ = view_spec(first, "profile", n=n)
    axis = spec.axes[0]
    u = np.linspace(axis.lo, axis.hi, axis.n)
    positions = _direction_points(d, u)
    combined = np.ones(u.size)
    reference = None
    line_pulses = []
    for p in d.pulses:
        values = _pulse_values(p, positions)
        line_pulses.append((p.block, values))
        if p is excitation:
            reference = values
        combined = combined * values
    combined = combined * factor
    if reference is None:
        # An excitation of kind "none": its |Mxy| is the same at each point.
        reference = np.full(u.size, float(_pulse_values(excitation, np.zeros((1, 3)))[0]))
    centre = first.slice_centre_m
    numbers = {
        "fwhm_m": float(profile_metrics.fwhm(u, combined)),
        "edge_width_m": float(profile_metrics.edge_width(u, combined)),
        "signal_kept": float(np.trapezoid(combined, u) / np.trapezoid(reference, u)),
    }
    if nominal is not None:
        numbers["fraction_inside"] = _fraction_inside(u, combined, centre, nominal)
    numbers["centre_signal"] = float(np.interp(centre, u, combined))
    return (u, combined), tuple(line_pulses), numbers


def _several_directions(
    directions: list[_Direction], factor: float, nominal: float | None, n: int | None
) -> dict[str, float]:
    fraction = 1.0
    centre_signal = 1.0
    for d in directions:
        lo, hi = _direction_range(d, n)
        u = np.linspace(lo, hi, n or NUM_POSITIONS)
        values = _direction_product(d, _direction_points(d, u))
        centre = d.pulses[0].slice_centre_m
        if nominal is not None:
            fraction *= _fraction_inside(u, values, centre, nominal)
        centre_signal *= float(np.interp(centre, u, values))
    numbers = {"centre_signal": centre_signal * factor}
    if nominal is not None:
        numbers["fraction_inside"] = fraction
    return numbers


def _combined_maps(
    directions: list[_Direction], factor: float, n: int | None
) -> tuple[CombinedMap, ...]:
    points = n or MAP_POINTS
    if all(d.kind in _AXIS_NAMES for d in directions):
        ordered = sorted(directions, key=lambda d: _AXIS_NAMES.index(d.kind))
        axes, lines = [], []
        for d in ordered:
            lo, hi = _direction_range(d, n)
            axis = ProfileAxis(d.kind, lo, hi, points)
            u = np.linspace(lo, hi, points)
            axes.append(axis)
            lines.append(_direction_product(d, _direction_points(d, u)))
        if len(ordered) == 2:
            return (CombinedMap((axes[0], axes[1]), np.outer(lines[0], lines[1]) * factor),)
        maps = []
        for first, second, third in ((0, 1, 2), (0, 2, 1), (1, 2, 0)):
            d = ordered[third]
            centre = np.array([d.pulses[0].slice_centre_m])
            through = float(_direction_product(d, _direction_points(d, centre))[0])
            values = np.outer(lines[first], lines[second]) * through * factor
            maps.append(CombinedMap((axes[first], axes[second]), values))
        return tuple(maps)

    # Two directions, at least one oblique: in-plane axes s1 (along the first direction)
    # and s2 (perpendicular to it, in the plane of both).
    d1, d2 = directions
    e1 = d1.unit
    across = d2.unit - (d2.unit @ e1) * e1
    e2 = across / np.linalg.norm(across)
    cos, sin = float(d2.unit @ e1), float(d2.unit @ e2)
    lo1, hi1 = _direction_range(d1, n)
    lo2, hi2 = _direction_range(d2, n)
    c1 = d1.pulses[0].slice_centre_m
    # The s2 range that puts the whole range of d2 on the line s1 = c1.
    s2_lo, s2_hi = (lo2 - c1 * cos) / sin, (hi2 - c1 * cos) / sin
    s1 = np.linspace(lo1, hi1, points)
    s2 = np.linspace(s2_lo, s2_hi, points)
    g1, g2 = np.meshgrid(s1, s2, indexing="ij")
    positions = np.outer(g1.ravel(), e1) + np.outer(g2.ravel(), e2)
    values = np.ones(positions.shape[0])
    for d in directions:
        values = values * _direction_product(d, positions)
    axes = (ProfileAxis("s1", lo1, hi1, points), ProfileAxis("s2", s2_lo, s2_hi, points))
    return (CombinedMap(axes, values.reshape(points, points) * factor),)
