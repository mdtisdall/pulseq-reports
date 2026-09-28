# Plan: RF pulse profiles in the library

Mode: Strict STE100. Structural rules are enforced. Lexical rules are a
direction of travel, not a verified dictionary match.

Status: proposed. The plan was written on 2026-09-28. The user answers the
questions of section 7 before phase 1 starts.

## 1. Goal

Add a card that shows the simulated profile of each RF pulse of a sequence,
for any Pulseq sequence:

1. Each group of RF pulses (section 2.5) gets its numbers: the flip angle, the
   peak B1, the RF energy and the widths of its profile.
2. With no input from the caller, a pulse with a gradient in one direction
   gets a 1D profile along that direction. A pulse with no gradient gets a 1D
   profile against the frequency offset.
3. A caller can ask for a profile over other axes: the positions x, y and z,
   the frequency offset, and a B1 scale factor. The simulation takes any
   number of axes. The card shows one axis as lanes, or two axes as a map.
4. vb-pulseq can replace its RF pulse profiles card with this card. It can
   build its column cross-section card from the profiles and the map chart of
   the library.

These items are not in this plan:

- Relaxation during the pulse (decision 7 of section 2.2).
- The rotation extension. The card refuses rotations, as the other gradient
  cards do (`extensions.refuse_rotations`).
- A 3D view. A profile with three or more axes is a Python result only.
- The column cross-section card and the coherence pathways card. They stay in
  vb-pulseq (decision 1).
- Pulse design.

## 2. Read this first (context for the executing agent)

### 2.1 The state of the repository

- Read `docs/plans/pulseq-reports.md`, `docs/plans/cards-at-scale.md` and
  `docs/plans/diagram-lanes.md`. Their workflow rules apply to this plan too.
  This plan changes decision 7 of section 2.2 of `docs/plans/pulseq-reports.md`
  (decision 1 below).
- `main` is at `b2200f4` (2026-09-28). The tag `v0.2.0rc1` is on `c7a284b`.
  The user tests the release candidate now. The card is new behavior for a
  version after 0.2.0 (question 8 of section 7).
- The branch `feature/public-card-helpers` (commit `5a2ae35`, not pushed, no
  PR on 2026-09-28) gives public names to helpers of `markup.py`
  (`html_table`, `fmt`, `zoom_controls`, `lanes_json`, `Lane`), and adds
  `extra_css` to `render_page` and `write_page`. If it merges before phase 4,
  the card of phase 4 uses the public names.
- The vb-pulseq code that this plan starts from is at the parity commit
  `3a1c7dd` in `~/dev/vb_pulseq`. Read each file with
  `git -C ~/dev/vb_pulseq show 3a1c7dd:<path>`. These files did not change
  from `3a1c7dd` to the vb-pulseq `HEAD` of 2026-09-28 (`2d81816`):
  - `src/vb_pulseq/rf_sim.py` (41 lines): the spin-domain simulator.
  - `src/vb_pulseq/rf_profiles.py` (186 lines): the pulses of a sequence,
    their numbers and their profiles.
  - `src/vb_pulseq/profile_metrics.py` (54 lines): the widths of a 1D
    profile.
  - `src/vb_pulseq/report/pulses_card.py` (175 lines): the RF pulse profiles
    card.
  - `src/vb_pulseq/report/assets/report.js`: the pulse lanes (lines 423 to 438)
    and the column map, `columnChart` (lines 520 to 727).
  - Tests: `tests/tools/test_rf_sim.py`, `test_rf_profiles.py`,
    `test_profile_metrics.py`.
- vb-pulseq has a plan, `docs/plans/review-fixes.md`, not committed, in
  `~/dev/vb_pulseq/.worktrees/review-fixes-plan`. Its Phase 8.2 moves the vb
  pulse profiles card and the column card onto `pulseq_reports.page.Card` as
  project cards. This plan does not edit vb-pulseq (question 7).

### 2.2 Decisions that are already made

Do not open these decisions again. The user made them or approved them.

1. **RF pulse profiles move to the library** (the user, 2026-09-28). This
   changes decision 7 of section 2.2 of `docs/plans/pulseq-reports.md` for
   `rf_sim.py`, `rf_profiles.py`, `profile_metrics.py` and the RF pulse
   profiles card. They move to the library in the general form of section
   4. The column cross-section, the coherence pathways, `moments.py`,
   `column.py` and `spin_echo.py` stay in vb-pulseq, because they know a
   spin echo (the project rule in `CLAUDE.md`).
2. **The library has its own simulator. No new dependency.** Recommended on
   2026-09-28 (section 2.3). The user asked for this plan after the
   recommendation. Decision 11 of section 2.2 of `docs/plans/pulseq-reports.md`
   stays: the dependencies are `pypulseq`, `numpy` and `scipy`.
3. **The model has N dimensions. The display has one or two.** Recommended
   on 2026-09-28. The user asked for this plan after the recommendation. The
   simulator takes a list of points, so a grid of any number of axes costs
   nothing extra in the design. The card shows 1D profiles as lanes of
   `laneChart` and 2D profiles as a map.
4. **The earlier rules stay.** No plotting library, no JavaScript dependency,
   no build step (decision 9 of `docs/plans/pulseq-reports.md`). No DOM tests:
   Node tests cover pure functions, and a browser check covers each chart
   (decision 10). Lean on pypulseq: do not test pypulseq in this project
   (decision 6 of `docs/plans/diagram-lanes.md`).
5. **Parity with vb-pulseq.** For the two vb-pulseq sequences of
   `scripts/vb_parity.py`, the library gives the same pulse numbers and
   profiles as vb-pulseq at `3a1c7dd` (section 3.5).
6. **The gyromagnetic ratio of the sequence.** The new code converts Hz to µT
   with `abs(seq.system.gamma)`, as the `TODO.md` item "Use the gyromagnetic
   ratio of the sequence" asks. The simulation itself needs no gyromagnetic
   ratio: pypulseq keeps the RF in Hz and the gradients in Hz/m.
7. **No relaxation.** The spin-domain simulation (Cayley-Klein parameters)
   cannot include T1 or T2. This is normal for pulse profiles. It matters for
   long adiabatic pulses or for a very short T2. If the user needs it later,
   it is a separate simulator and a `TODO.md` item.

### 2.3 Facts (2026-09-28)

**Python Bloch simulators.** None fits as a dependency:

| Package | License | What fits | What stops it |
|---|---|---|---|
| sigpy 0.1.27 (last release 2025-01-11, last push 2024-12-27) | BSD-3 | `abrm_nd`: the same spin-domain rotation, any number of spatial dimensions | No frequency offset (only `abrm_ptx` has one, and it assumes a square 2D grid). It needs numba, pywavelets and tqdm. |
| PulPy 1.8.8 | `pyproject.toml` says MIT, the `LICENSE` file is GPL-3.0 | `sim.py` is a copy of the sigpy functions | `numpy < 2.0` and `numba 0.59`. This project locks numpy 2.5.3. |
| blochsimulator 2.7.0 (the C solver of B. Hargreaves) | GPL-3.0 | Fast, relaxation, positions and frequencies, a Pulseq mode | The license. It needs matplotlib, h5py, xarray and Cython. |
| MRzeroCore 1.1.1 | AGPL-3.0 | Reads `.seq` files | The license, and torch. It simulates the signal of a whole sequence, not pulse profiles. |
| KomaMRI, BlochSim.jl | | Good simulators | Julia |

pypulseq has no Bloch simulator. `calc_rf_bandwidth` gives only the spectrum
of the RF (correct only at small flip angles).

**The vb-pulseq simulator is the sigpy algorithm.** A random complex RF of
1000 samples at 401 positions: vb-pulseq `cayley_klein` and sigpy `abrm_nd`
agree within 4e-14. A 2D grid of 201 × 201 points and 1000 RF samples took
0.85 s with sigpy and 1.06 s with a plain numpy N-D loop (vb-pulseq
environment, Mac with 10 cores and 64 GB). A dependency makes it no faster.

**What in vb-pulseq knows its own sequences** (`rf_profiles.py` at
`3a1c7dd`):

1. A profile only for a trapezoid on one axis, with the RF inside its flat
   top. Other pulses get the reason "select gradient on more than one axis",
   "select gradient is not a trapezoid" or "RF is not inside the flat top".
2. A pulse with no gradient gets no profile ("no select gradient").
3. A pulse is one combination of RF and gradient event ids. pypulseq makes a
   new RF event for each new frequency or phase offset. The example GRE of
   this library (`examples/gre_report.py`, pypulseq `write_gre.py` with RF
   spoiling) has 64 blocks with RF and 24 such combinations. Without the
   offsets, it has 1 group. It has no `SliceThickness` definition.
4. The rephaser is the rest of the select gradient after the RF, plus the
   whole next block on the same axis.
5. The simulation ignores the frequency and phase offsets.

**pypulseq facts** (the pinned fork, `20b9e5e`):

1. `seq.rf_library.data[id]` is `(amplitude, mag_id, phase_id, time_id,
   center, delay, freq_ppm, phase_ppm, freq_offset, phase_offset)`.
   `seq.rf_library.type[id]` is the first letter of the use (for example
   `"e"` for excitation).
2. The uses: `excitation`, `refocusing`, `inversion`, `saturation`,
   `preparation`, `other`, `undefined` (`get_supported_rf_uses`).
3. `Sequence.waveforms` plays an RF as `signal * exp(1j * (phase + 2π * f *
   rf.t))`, with `f = freq_offset + freq_ppm * 1e-6 * gamma * B0`, the same
   form for the phase, and `rf.t` from the start of the shape.
4. pypulseq examples place a slice with `freq_offset = G * position`
   (`write_tse.py`), where `G` is the signed select amplitude (Hz/m).

### 2.4 Budgets (proposed: the user approves them with this plan)

For one file. "Card" is `rf_profiles_card` with its defaults.

| Quantity | vb-pulseq sequences, example GRE | 10^7 repeating blocks |
|---|---|---|
| Python time of the card, with `SequenceIndex` | at most 2 s | at most 20 s |
| Python peak RSS added | at most 0.2 GB | at most 1 GB |
| Page size of the card | at most 0.2 MB | at most 0.2 MB |

One 2D map of 256 × 256 points for a pulse of 1000 RF samples: at most 5 s
in Python, at most 0.3 MB of page, at most 200 ms in the browser for the first
draw, and at most 16 ms for one cursor move.

If a budget fails, stop and tell the user. Do not change a budget yourself.

### 2.5 Terms

- **Offsets.** The four offsets of an RF event: `freq_offset`, `freq_ppm`,
  `phase_offset` and `phase_ppm`. The **total frequency offset** is `f =
  freq_offset + freq_ppm * 1e-6 * abs(gamma) * B0` (Hz).
- **Pulse group (group).** The blocks whose RF events are equal except for
  the offsets, and whose gradient events are the same.
- **Hold interval.** The time of one RF sample from `hold_samples`: the
  interval `[k * dt, (k + 1) * dt]` from the start of the RF shape.
- **Gradient kind.** For the gradients during the RF of a group: `none` (all
  zero), `one` (one direction, see section 4.2), or `changing`.
- **Select coordinate.** The position along the gradient of a group of kind
  `one`: a logical axis (`x`, `y` or `z`) when the gradient is on one axis,
  else `select` (along the unit vector of the mean gradient).
- **Slice centre.** The position of the select coordinate where the total
  frequency offset puts the profile: `f / G`.
- **Axis kind.** One of `x`, `y`, `z`, `select` (positions, m), `df` (the
  frequency offset of the spins, Hz) and `b1` (a factor on the RF amplitude).
- **Profile spec (spec).** The axes of a profile, and the values of the
  kinds that are not axes.
- **Profile.** The spin-domain parameters `a` and `b` on the grid of a spec.
- **Main quantity.** The quantity of a profile that a map shows (section
  4.4).
- **Baseband.** The RF without its offsets.

## 3. How to execute this plan

### 3.1 Workflow

As in `docs/plans/cards-at-scale.md`, section 3.1, items 1 to 9. At most three
PRs open at one time. Each phase that changes `scripts/vb_parity.py` puts its
output in the PR.

### 3.2 Worker model tiers

As in `docs/plans/cards-at-scale.md`, section 3.2: H (`haiku`), S (`sonnet`),
O (the executing agent). Give each worker the exactness and parity rule
(section 3.5).

### 3.3 Order and parallel work

```
Phase 1 (simulator, metrics) ──► Phase 2 (pulse groups, profiles) ──┐
                                                                    ├─► Phase 4 (card) ─► Phase 5 (scale, documents)
Phase 3 (map chart in JavaScript) ──────────────────────────────────┘
```

- Phases 1 and 3 start at the same time. They edit different files.
- Phase 2 after phase 1. Phase 4 after phases 2 and 3. Phase 5 last.
- No phase 0: phases 1, 2 and 4 each add their `TESTS.md` sections at the
  end, one after another. Phase 3 edits only section 2.4. So no two open
  phases edit the same part of `TESTS.md`.

### 3.4 File ownership

Package root: `src/pulseq_reports/`. Tests: `tests/`.

| Phase | Files that the phase creates or edits |
|---|---|
| 1 | `rf_sim.py` (new), `profile_metrics.py` (new), `tests/oracles/rf_sim.py` (new), `tests/test_rf_sim.py` (new), `tests/test_profile_metrics.py` (new), `TESTS.md` (new sections 2.28 and 2.29 at the end) |
| 2 | `rf_profiles.py` (new), `tests/test_rf_profiles.py` (new), `scripts/vb_parity.py` (a new `pulses` check, `VB_REPORT_PATHS`, and `ACCEPTED["pulses"]` only after the user accepts a difference), `TESTS.md` (new section 2.30 at the end) |
| 3 | `assets/chart_math.js` (new pure functions only), `assets/lane_chart.js` (new `PulseqReport.mapChart` and `PulseqReport.decodeTable` only), `assets/cards/diagram.js` (only: use `PulseqReport.decodeTable`), `assets/report.css` (new map chart rules only), `tests/js/test_chart_math.js` (new tests only), `docs/usage.md` (new subsections of section 4 only), `TESTS.md` (section 2.4, new entries only) |
| 4 | `cards/rf_profiles.py` (new), `assets/cards/rf-profiles.js` (new), `tests/test_rf_profiles_card.py` (new), `examples/gre_report.py`, `docs/examples/gre.html` (rebuilt), `docs/usage.md` (sections 2 and 5, and a new subsection), `README.md` (the card table of "The cards" only), `TESTS.md` (new section 2.31 at the end) |
| 5 | `scripts/cards_scale.py` (only a new card name), `TODO.md`, `docs/usage.md` (the scale table only), `docs/plans/pulseq-reports.md` (one note on decision 7 only), this plan file (status and results only) |

Rules: as in `docs/plans/cards-at-scale.md`, section 3.3, items 1 to 3.
`tests/oracles/` is a namespace package: add no `__init__.py`.

### 3.5 The exactness and parity rule

1. **The simulator against the oracle.** `rf_sim.spin_domain` and the oracle
   `tests/oracles/rf_sim.py` must agree within 1e-10 on each component of the
   magnetization (a unit vector). The oracle uses a different method (3 × 3
   rotations of the magnetization, section 5, task 1.3), so a shared error is
   unlikely.
2. **Analytic cases.** Each analytic test writes its tolerance and the reason
   for it in the test.
3. **Parity.** `scripts/vb_parity.py` compares the pulse numbers and the
   profiles of the library with those of vb-pulseq at `3a1c7dd`, within a
   relative 1e-9 (its `RTOL`). The position grids must be equal. Each
   difference is an accepted difference that the user approves
   (`ACCEPTED["pulses"]`).
4. **The map values in the page.** A map sends each value as a uint16 over
   the domain of its quantity (section 4.5). The decoded value must be within
   half a step (`(hi - lo) / 65535 / 2`) of the Python value. A Node test of
   the pure decode function checks this.

## 4. Design

### 4.1 The simulator (`rf_sim.py`, phase 1)

```python
def spin_domain(
    signal_hz: np.ndarray,       # (n,) complex: the RF samples, each held for dt_s
    dt_s: float,
    grad_hz_per_m: np.ndarray,   # (n, 3): the mean gradient of each hold interval, x y z
    positions_m: np.ndarray,     # (m, 3)
    df_hz: np.ndarray | None = None,     # (m,): the frequency offset of each point, default 0
    b1_scale: np.ndarray | None = None,  # (m,): a factor on the RF of each point, default 1
) -> tuple[np.ndarray, np.ndarray]      # a, b: (m,) complex
def magnetization(a, b) -> tuple[np.ndarray, np.ndarray]  # mxy (complex), mz; from M0 = (0, 0, 1)
def crushed_echo(b) -> np.ndarray                          # |b|^2
def precess(mxy, moment_per_m, positions_m) -> np.ndarray  # mxy * exp(2j*pi * (moment . r))
```

1. For each hold interval `k` and point `j`: the RF angle is `2π * dt *
   b1_scale[j] * signal[k]` (complex), and the off-resonance angle is `2π *
   dt * (grad[k] · r[j] + df[j])`. The rotation of the interval is the
   rotation of vb-pulseq `cayley_klein` with these two angles. With
   `grad[k] = (0, 0, G)`, `r[j] = (0, 0, x[j])`, `df = 0` and `b1_scale = 1`,
   it is `cayley_klein(signal, dt, G, x)`.
2. The loop runs over the `n` intervals and uses numpy over the `m` points.
   A caller gives at most `MAX_POINTS` points (section 4.3), so there is no
   chunking.
3. The signs are the signs of vb-pulseq (`test_precess_sign_matches_free_precession_in_cayley_klein`).
4. `magnetization`, `crushed_echo` and `precess` are the vb-pulseq functions.
   `precess` takes a moment vector (1/m, x y z) and positions (m, 3) instead of
   a scalar area and a scalar position.

`profile_metrics.py` is a copy of vb-pulseq `profile_metrics.py`
(`fwhm`, `edge_width`, `passband_ripple`, `stopband_level`,
`phase_peak_to_peak`), without changes.

### 4.2 From a sequence to pulse groups (`rf_profiles.py`, phase 2)

1. **Guard.** `rf_pulse_groups` calls `extensions.refuse_rotations(seq)`
   first.
2. **Index.** Use `seq_index.sequence_index(seq)` (the cached index of the
   other cards). No loop in Python over the blocks.
3. **Groups.** For each dense RF index `k`, find its pypulseq id from the
   first block that uses it (`rf_first`, `block_id` and `seq.block_events`).
   Its key without offsets is `rf_library.data[id][:6]` (amplitude, shapes,
   center, delay) and `rf_library.type[id]` (the use). Give each distinct key
   a number. The group of a block with RF is the row (key number, `gx`, `gy`,
   `gz`) of the index: `numpy.unique` over the blocks with RF, with
   `return_inverse`. Order the groups by their first block.
4. **Members.** For each group: the block ids of its members (uint32, play
   order), and the distinct total frequency offsets of its RF events.
5. **The representative block** is the first member. The card reads only
   this block with `seq.get_block`, and the next block in play order for the
   rephaser.
6. **The RF samples.** `seq_utils.hold_samples(rf, seq.system.rf_raster_time)`
   at baseband: without the offsets.
7. **The gradient of each hold interval.** For each axis, the points of the
   block's gradient event from `seq_utils.gradient_points(g, 0.0)`
   (block-local times). The gradient is linear between the points and zero
   outside the event. The value for interval `k` is the exact integral of
   this function over `[rf.delay + k * dt, rf.delay + (k + 1) * dt]`,
   divided by `dt`. On the flat top of a trapezoid it is the flat-top
   amplitude, as in vb-pulseq. A gradient on the ramps, a VERSE gradient or
   an arbitrary gradient needs no special case.
8. **The gradient kind.** `none` when every interval value is exactly zero.
   `one` when the mean vector `m` is not zero and every interval vector `g`
   is parallel to it: `|g - (g · u) u| <= 1e-9 * max |g|` with `u = m / |m|`.
   `changing` for all other cases. The select coordinate of kind `one` is
   the logical axis when only one axis has a gradient, else `select` along
   `u`. The gradient is **constant** when every interval vector equals the
   mean within a relative 1e-9.
9. **Numbers** (as vb-pulseq, with the gyromagnetic ratio of decision 6):
   - flip angle (degrees): `degrees(2π * |sum(signal) * dt|)`.
   - peak B1 (µT): `max |signal| / |gamma| * 1e6`.
   - RF energy (µT²·ms): `sum((|signal| / |gamma| * 1e6)^2) * dt * 1e3`.
   - W (m): the `SliceThickness` definition, or None.
10. **Offsets and the axis.** The simulation is at baseband. The card moves
    the axis by the offset when all members of a group have one total
    frequency offset `f`:
    - kind `one`: the select coordinate moves by the slice centre `f / G`.
      `G` is the signed amplitude on the logical axis, or `|m|` for `select`.
    - kind `none`: the `df` axis moves by `f`.

    This move is exact when the gradient is constant during the RF: the
    offset then equals a shift of the profile, plus a phase. When the
    gradient is not constant, the profile of an off-centre member is not a
    shift. The notes of the group then say so. With more than one total
    frequency offset, the axis stays relative to the slice centre of each
    member, and the table lists the centres. The phase offsets rotate the
    whole profile. They change no quantity of the card.

### 4.3 Specs and default specs (`rf_profiles.py`, phase 2)

```python
AXIS_KINDS = ("x", "y", "z", "select", "df", "b1")
MAX_POINTS = 65_536  # 256 x 256
NUM_POSITIONS = 401  # the default number of points of a 1D profile (vb-pulseq)


@dataclass(frozen=True)
class ProfileAxis:
    kind: str  # one of AXIS_KINDS
    lo: float  # m for positions, Hz for df, a factor for b1
    hi: float
    n: int


@dataclass(frozen=True)
class ProfileSpec:
    axes: tuple[ProfileAxis, ...]
    at: Mapping[str, float] = field(default_factory=dict)  # kinds that are not axes
    rephaser_moment_per_m: float | None = None  # replaces the rule of 4.4
```

1. **Rules** (`ValueError` for each one):
   - each kind at most once, in the axes and in `at` together.
   - `select` not together with `x`, `y` or `z`.
   - `select` only for a group of kind `one` whose select coordinate is
     `select`.
   - `n >= 2` and `lo < hi` for each axis.
   - the product of the `n` values at most `MAX_POINTS`.
2. **Values that are not axes.** Positions 0 m, `df` 0 Hz, `b1` 1.
3. **The grid.** `numpy.linspace(lo, hi, n)` for each axis, `numpy.meshgrid`
   with `indexing="ij"`, flattened in C order. `a` and `b` have the shape
   `(n1, n2, ...)`.
4. **Default spec** (`default_spec(group)`):
   - kind `one`: one axis, the select coordinate, from `-2W` to `+2W` with
     `NUM_POSITIONS` points (vb-pulseq). Without W, the half range is 2 times
     the thickness from the RF spectrum (vb-pulseq `_spectrum_thickness`: the
     FWHM of the zero-padded spectrum divided by `|G|`), and a note says "no
     SliceThickness definition".
   - kind `none`: one axis `df`, from `-2B` to `+2B` with `NUM_POSITIONS`
     points, where `B` is the FWHM of the RF spectrum (Hz).
   - kind `changing`: no default. The group has the reason "the gradient
     direction changes during the RF: give a profile spec" (question 4).
5. **Simulate.** `simulate(group, spec) -> Profile` maps each grid point to
   a position vector (a `select` value `s` is `s * u`), a `df` value and a
   `b1` value, and calls `spin_domain` with the RF and gradient samples of the
   group.

```python
@dataclass(frozen=True)
class Profile:
    spec: ProfileSpec
    grid: tuple[np.ndarray, ...]  # the values of each axis
    a: np.ndarray  # complex, shape (n1, n2, ...)
    b: np.ndarray
```

### 4.4 Quantities, the rephaser and the numbers (`rf_profiles.py`, phase 2)

| Use | Lanes of a 1D profile | Main quantity (maps) | Profile for the widths |
|---|---|---|---|
| excitation | \|Mxy\|, Mz, phase after the rephaser | \|Mxy\| | \|Mxy\| |
| refocusing | \|β\|² | \|β\|² | \|β\|² |
| inversion | Mz | Mz | (1 - Mz) / 2 |
| saturation | Mz | Mz | 1 - Mz |
| preparation, other, undefined | \|Mxy\|, Mz | \|Mxy\| | \|Mxy\| |

The excitation and refocusing rows are those of vb-pulseq. vb-pulseq shows
\|Mxy\| and Mz for inversion and saturation. The new rows show Mz, because an
inversion or saturation pulse is judged by Mz.

1. **The rephaser** (question 1). The moment vector (1/m, x y z) from the RF
   end to the end of its block, plus the whole next block in play order. On
   the select coordinate, the rephaser moment is the component on its logical
   axis, or `moment · u` for `select`. For one axis and a trapezoid, this is
   vb-pulseq `rephaser_area`. `ProfileSpec.rephaser_moment_per_m` replaces it
   when the caller gives it.
2. **The phase lane.** Only for an excitation group of kind `one` with a 1D
   profile along its select coordinate. The phase of
   `precess(mxy, rephaser)`, relative to its value at the slice centre, where
   \|Mxy\| is at least 10 % of its maximum (vb-pulseq).
3. **The widths of a 1D profile.** On the profile for the widths, in the
   units of the axis: `fwhm` and `edge_width`. `passband_ripple` and
   `stopband_level` only on the select coordinate with W. For excitation:
   `phase_peak_to_peak` (with W) and the centre phase (vb-pulseq
   `center_phase_rad` and `residual_phase_rad`).
4. **The widths of a 2D profile** (question 9). `fwhm` and `edge_width` along
   each axis, on the grid line through index `n // 2` of the other axis.
5. **Three or more axes.** `simulate` accepts them. The card gives an error
   for such a spec (section 4.5).

### 4.5 The card (`cards/rf_profiles.py`, phase 4)

```python
def rf_profiles_card(
    seqs: Sequence[NamedSequence],
    specs: Callable[[NamedSequence, RfPulseGroup], ProfileSpec | None] | None = None,
    card_id: str = "rf-profiles",
) -> Card
```

`specs` gives the spec of a group, or None for its default spec. A spec with
three or more axes raises `ValueError`.

1. **Body.** One part for each file (a heading with the file name when there
   is more than one file, question 5):
   - A table with one row for each group: Blocks (`_blocks_cell`: the first
     four and the count), Use, Gradient (`none`, `Gx`, `oblique (x 0.71,
     z 0.71)` or `changing`), Flip (°), Peak B1 (µT), RF energy (µT²·ms),
     W (mm), Centres (the slice centres in mm or the offsets in Hz, at most
     8, then the count), FWHM, Edge 10–90 %, Passband ripple, Stopband level,
     Residual phase (rad), Centre phase (rad), Notes. The width cells have
     their unit (mm, Hz, or none for `b1`), because the kind of axis can be
     different in each row.
   - For each group with a profile: a heading "Pulse N: use, gradient" and a
     chart. A 1D profile is a lane chart, as the vb-pulseq pulse lanes. A 2D
     profile is a map.
   - A note under the tables: each profile is a spin-domain simulation of the
     held RF samples with the gradients of the block, without relaxation. A
     group is simulated one time, at baseband (section 4.2, item 10).
2. **Data.**

   ```
   {"files": [{"name": ..., "groups": [{
       "blocks": [first four block ids], "num_blocks": N,
       "use", "gradient", "flip_deg", "peak_b1_ut", "energy_ut2_ms",
       "nominal_mm", "centres", "reason", "notes", "metrics",
       "view": null
             | {"kind": "lanes", "x_label", "lanes": [...], "bands": [[lo, hi]]}
             | {"kind": "map", "x": {...}, "y": {...}, "quantity", "domain": [lo, hi],
                "values": {"dtype": "uint16", "length": ..., "data": ...}}
   }]}]}
   ```

   - Lanes: the lane JSON of `markup` (`Lane`), with points `[x, value]`
     rounded to 4 digits, x in mm, Hz or the factor. Bands: `±W / 2` around
     the displayed slice centre on the select coordinate with W (vb-pulseq).
   - Map axes: `{"kind", "lo", "hi", "n", "label"}` in display units.
   - Map values: the main quantity, row-major `(n_y, n_x)`, as uint16:
     `round((v - lo) / (hi - lo) * 65535)`, with the domain `[0, 1]` for
     \|Mxy\| and \|β\|², and `[-1, 1]` for Mz. `diagram_data.encode_tables`
     makes the entry.
3. **The card script** (`assets/cards/rf-profiles.js`). For each group with a
   view: `PulseqReport.laneChart` for lanes (as vb-pulseq `report.js` lines
   423 to 438), or `PulseqReport.decodeTable` and `PulseqReport.mapChart` for
   a map. The element ids start with the card id.

### 4.6 The map chart (phase 3)

1. **Pure functions in `chart_math.js`** (Node tests):
   - `colorRamp(stops, n)`: `n` RGB colors, linear between the stops.
   - `colorIndex(value, domain, n)`: the index of a value in the ramp,
     clamped.
   - `nearestIndex(lo, hi, n, value)`: the nearest grid index on a uniform
     axis, clamped.
   - `uint16Values(array, domain)`: the values of a decoded uint16 array
     (`Float32Array`).
2. **`PulseqReport.mapChart(options)`** in `lane_chart.js`, from vb-pulseq
   `columnChart` (`report.js` lines 520 to 727 at `3a1c7dd`). Options:
   `canvas`, `svg`, `chart`, `tip` (existing elements), `x`, `y` (axis objects
   of section 4.5), `values` (`Float32Array`, row-major), `domain`,
   `scale` (`"sequential"` or `"diverging"`), `xLabel`, `yLabel`,
   `valueLabel`, `cursorText(x, y, v)`, and `outlines` (a list of
   `[x0, x1, y0, y1]`, drawn dashed). It draws the raster on the canvas, the
   axes with `niceTicks`, a color legend, a crosshair with a tooltip, arrow
   keys that move the cursor by one grid step, and the colors of the current
   theme (again after a theme change, as vb-pulseq does). No zoom. The card
   of this plan passes no outlines. vb-pulseq's column card can pass its
   W × W square.
3. **`PulseqReport.decodeTable(entry)`** in `lane_chart.js`: the function
   `decodeTable` of `assets/cards/diagram.js`, moved without a change of
   behavior. `diagram.js` then calls it.
4. **CSS** in `report.css`: class selectors only, for example `.map-chart`,
   `.map-chart canvas`, `.map-chart svg`. No id selectors.
5. **`docs/usage.md`**: `PulseqReport.mapChart` options and
   `PulseqReport.decodeTable`, next to the `laneChart` options.

### 4.7 The API

```python
# pulseq_reports.rf_sim
spin_domain, magnetization, crushed_echo, precess

# pulseq_reports.profile_metrics
fwhm, edge_width, passband_ripple, stopband_level, phase_peak_to_peak

# pulseq_reports.rf_profiles
AXIS_KINDS, MAX_POINTS, NUM_POSITIONS, ProfileAxis, ProfileSpec, Profile, RfPulseGroup
def rf_pulse_groups(seq: pp.Sequence) -> list[RfPulseGroup]
def default_spec(group: RfPulseGroup) -> ProfileSpec | None
def simulate(group: RfPulseGroup, spec: ProfileSpec) -> Profile
def quantity(profile: Profile, name: str) -> np.ndarray  # "mxy_abs", "mz", "beta_sq"
def phase_after_rephaser(group: RfPulseGroup, profile: Profile) -> np.ndarray
def widths(group: RfPulseGroup, profile: Profile) -> dict[str, float]

# pulseq_reports.cards.rf_profiles
def rf_profiles_card(seqs, specs=None, card_id="rf-profiles") -> Card
```

`RfPulseGroup` (frozen dataclass) holds: `block_ids` (uint32 array), `use`,
`gradient_kind`, `select_kind` (None, `x`, `y`, `z` or `select`),
`direction` (the unit vector `u`, or None), `gradient_hz_per_m` (the signed
amplitude on the select coordinate, or None), `constant_gradient`,
`frequency_offsets_hz` (distinct values), `flip_deg`, `peak_b1_ut`,
`energy_ut2_ms`, `nominal_m`, `rephaser_moment_per_m`, `signal_hz`, `dt_s`,
`grad_hz_per_m` (the interval values), `reason` and `notes`.

The signatures are proposals. Phase 2 (tier O) fixes them before a worker
starts.

### 4.8 What vb-pulseq can do after this plan (not in this plan)

1. Use `rf_profiles_card` instead of its pulse profiles card.
2. Build its column cross-section card from two library profiles: the
   excitation \|Mxy\| times the refocusing \|β\|², drawn with
   `PulseqReport.mapChart` and a W × W outline.
3. Delete its `rf_sim.py`, `rf_profiles.py` and `profile_metrics.py`.

## 5. Phases

---

### Phase 1: the simulator and the metrics

Branch: `feature/rf-sim`. Tier: S. Review: O. Starts at once.

**Task 1.1: `rf_sim.py`.** Tier O for the signatures and the docstrings, S
for the code. Section 4.1. Start from vb-pulseq `rf_sim.py` at `3a1c7dd`.

**Task 1.2: `profile_metrics.py`.** Tier H. A copy of vb-pulseq
`profile_metrics.py` at `3a1c7dd`, and a copy of
`tests/tools/test_profile_metrics.py` as `tests/test_profile_metrics.py`.
Change only the imports.

**Task 1.3: The oracle.** Tier S. `tests/oracles/rf_sim.py`: the
magnetization vector of each point, rotated in each hold interval by the 3 × 3
matrix (Rodrigues' formula) about the field `(Re b1, Im b1, off-resonance)`.
No spin-domain parameters. It returns `mxy` and `mz`, to compare with
`magnetization(*spin_domain(...))`. Read the vb-pulseq test
`test_hard_pulse_with_gradient_matches_rodrigues_rotation` for the sign of
each component.

**Task 1.4: Tests.** Tier S. `tests/test_rf_sim.py`:

1. The six vb-pulseq tests of `tests/tools/test_rf_sim.py`, with the new
   signatures.
2. The oracle (section 3.5, item 1): random complex RF (at least 200
   samples), a gradient on 3 axes that changes in each interval, random
   points with random `df` and `b1_scale`.
3. Rotation: a gradient `(Gx, Gy, 0)` and points along it give the 1D result
   of the gradient magnitude and the distance along it (1e-12).
4. `df` is a shift: with a constant gradient `G`, the point at `x` with
   `df` equals the point at `x + df / G` with `df = 0` (1e-12).
5. `b1_scale`: a hard pulse with `b1_scale = s` gives `s` times the flip
   angle (1e-12).
6. `precess` with a moment vector equals the vb-pulseq scalar form along one
   axis (exact).

`TESTS.md`: new sections at the end, "2.28 RF simulation
(`test_rf_sim.py`)" and "2.29 Profile metrics (`test_profile_metrics.py`)".

Acceptance: `scripts/check` passes.

---

### Phase 2: pulse groups and profiles

Branch: `feature/rf-profiles`. Tier: O for the interface, S for the code.
After phase 1.

**Task 2.1: The interface.** Tier O. Write the dataclasses and the
signatures of section 4.7 with their docstrings, and fix them. Give the
bodies to the worker.

**Task 2.2: `rf_profiles.py`.** Tier S. Sections 4.2, 4.3 and 4.4.

**Task 2.3: Tests.** Tier S. `tests/test_rf_profiles.py`. Build each
sequence in the test with pypulseq.

1. Groups: a sequence with RF spoiling (a new phase offset in each TR) is one
   group. Slices with different frequency offsets are one group, with each
   total frequency offset. Two select gradients give two groups. The groups
   are in the order of their first block. The block ids of each group are in
   play order.
2. The gradient kinds: a block pulse (`none`); a trapezoid on z (`one`,
   select coordinate `z`, as vb-pulseq); the same trapezoid on x and y with
   one timing (`one`, `select`, `u` = the unit vector); an arbitrary
   gradient on x and y that turns (`changing`, no default spec, the reason).
3. Interval values: for a trapezoid, the values of a ramp interval, an
   interval with a corner, and a flat interval equal the means computed by
   hand (1e-12).
4. RF on the ramps: a pulse longer than the flat top gets a profile. It is
   not constant. The notes say that an off-centre member is not a shift.
5. Offsets: a member with the total frequency offset `f` and a constant
   gradient `G`. The simulation of the RF as played (the samples times
   `exp(2j * pi * f * t)`, `t` at the interval centres) equals the baseband
   profile moved by `f / G` (\|Mxy\|, Mz and \|β\|² within 1e-9). The
   `freq_ppm` of an RF event adds `freq_ppm * 1e-6 * abs(gamma) * B0`.
6. The rephaser: the vb-pulseq test
   `test_rephaser_area_is_half_the_flat_top_area`, and a moment in the next
   block on the select axis.
7. The quantities and the widths for each use of the table in section 4.4.
8. Default specs: with W (`-2W` to `+2W`, 401 points); without W (the
   spectrum rule and the note); `none` (`df` axis).
9. Spec errors: one test for each rule of section 4.3, item 1.
10. N-D: a spec with the axes `z` and `df` equals, on each grid line, the 1D
    profile with the other value in `at` (exact equality).
11. Rotations: `NotImplementedError`, as `tests/test_extensions.py` makes a
    sequence with rotations.
12. Another nucleus: the peak B1 of a block pulse made with
    `pp.Opts(gamma=11.262e6)` equals its B1 in µT (1e-9).

`TESTS.md`: a new section at the end, "2.30 RF pulse groups and profiles
(`test_rf_profiles.py`)".

**Task 2.4: Parity.** Tier O. In `scripts/vb_parity.py`:

1. Add `src/vb_pulseq/rf_profiles.py`, `src/vb_pulseq/rf_sim.py` and
   `src/vb_pulseq/profile_metrics.py` to `VB_REPORT_PATHS`.
2. Add the check `pulses`. For each vb-pulseq sequence: vb-pulseq
   `rf_profiles.pulse_profiles(seq)` against the library groups with their
   default profiles. Compare, for each pulse: the blocks, the use, the axis,
   the flip angle, the peak B1, the energy, W, the rephaser area, the
   position grid, each vb-pulseq profile (`mxy_abs`, `mz`, `phase`,
   `beta_sq`) and each vb-pulseq metric.
3. Run it (section 3.5, item 3). Show each difference to the user. Record
   each difference that the user accepts in `ACCEPTED["pulses"]`.

**Task 2.5: Measure.** Tier S. The time and the added RSS of
`rf_pulse_groups` and the default profiles for the two vb-pulseq sequences
and the example GRE, and one 256 × 256 spec (section 2.4).

Acceptance: `scripts/check` passes. `scripts/vb_parity.py` prints `ok` for
`pulses` and for the other cards.

---

### Phase 3: the map chart in JavaScript

Branch: `feature/map-chart`. Tier: S. Review: O. Starts at once.

**Task 3.1: Pure functions.** Tier S. Section 4.6, item 1, in
`chart_math.js`. Node tests in `tests/js/test_chart_math.js`: each function
on hand-made input, the clamps, and the half-step rule of section 3.5,
item 4. `TESTS.md` section 2.4: an entry for each new test.

**Task 3.2: `PulseqReport.mapChart`.** Tier S. Section 4.6, item 2. Review O
line by line: `laneChart` must not change.

**Task 3.3: `PulseqReport.decodeTable`.** Tier S. Section 4.6, item 3.

**Task 3.4: CSS and documents.** Tier S. Section 4.6, items 4 and 5.

**Task 3.5: Browser check.** Tier O. Use the
`dev-workflow:browser-check-localhost` skill.

1. A scratch page with a project card (`Card` and `extra_scripts`) that
   draws a known map: a Gaussian on one axis times a ramp on the other, on a
   non-square grid (for example 180 × 120), sequential and diverging.
2. Check the axes, the legend, the tooltip values, the arrow keys, both
   themes, a theme change, and that there is no console error.
3. The diagram card of the example GRE still works (task 3.3).

Acceptance: `scripts/check` passes. The browser check passes.

---

### Phase 4: the card

Branch: `feature/rf-profiles-card`. Tier: S. Review and browser check: O.
After phases 2 and 3.

**Task 4.1: `cards/rf_profiles.py`.** Tier S. Section 4.5.

**Task 4.2: `assets/cards/rf-profiles.js`.** Tier S. Section 4.5, item 3.

**Task 4.3: Tests.** Tier S. `tests/test_rf_profiles_card.py`:

1. The data of section 4.5, item 2, for a sequence with an excitation and a
   refocusing pulse (vb-pulseq-like), a block pulse, and a turning gradient
   (no view, the reason in the table).
2. A 2D spec from `specs`: the map entry, its axes, and its values decoded
   with `diagram_data.decode_tables` within half a step of `quantity`.
3. A spec with three axes: `ValueError`.
4. Several files: one part for each file.
5. A group with many members: the blocks cell and `num_blocks`.
6. Two cards on one page (different `card_id`): no id is used twice.

`TESTS.md`: a new section at the end, "2.31 RF profiles card
(`test_rf_profiles_card.py`)".

**Task 4.4: Documents and the example.** Tier S.

1. `docs/usage.md`: the card in the builder table of section 5, the card in
   the example of section 2, and a new subsection with a `specs` example (a
   `z` × `df` map for the slice-selective pulse).
2. `examples/gre_report.py`: add the card. Rebuild `docs/examples/gre.html`
   with it.
3. `README.md`: a row for the card in the table of "The cards".

**Task 4.5: Browser check.** Tier O. Pages: the example GRE; a vb-pulseq
sequence (scratch page); a page with a 2D spec; the ex-vivo file
`data/exvivo_gre_seg_0.seq` (a hard pulse: a `df` profile). The ex-vivo page
stays in the scratchpad. Never commit it. Check the lanes, the bands, the
map, the tooltips, both themes, and that there is no console error.

**Task 4.6: Measure.** Tier S. The budgets of section 2.4 for the vb-pulseq
sequences, the example GRE and the ex-vivo file.

Acceptance: `scripts/check` passes. `scripts/vb_parity.py` prints `ok` for
each card. The budgets pass. The browser check passes.

---

### Phase 5: scale check and documents

Branch: `chore/rf-profiles-scale`. Tier: O, with H for the documents.

**Task 5.1.** Add the card name `rf-profiles` to `scripts/cards_scale.py`.
Measure 10^6 and 10^7 repeating blocks and 10^5 worst-case blocks: the budgets
of section 2.4. The repeating TR of `scripts/diagram_scale.py` has an RF block
pulse (kind `none`), so the card simulates one `df` profile.

**Task 5.2.** `docs/usage.md`: the card in the scale table. This plan: status
"complete", the PR numbers, the decisions made during the work, and the
results in section 8. `docs/plans/pulseq-reports.md`: under decision 7 of
section 2.2, one note that `docs/plans/rf-profiles.md` moved the RF pulse
profiles to the library. `TODO.md`: an item for relaxation during the pulse
only if the user asks for it.

## 6. Summary of parallel work

| Wave | Phases | Condition to start |
|---|---|---|
| 1 | 1, 3 | The user answered section 7 (questions 1 to 4 at least). |
| 2 | 2 | Phase 1 merged. |
| 3 | 4 | Phases 2 and 3 merged. |
| 4 | 5 | Phase 4 merged. |

Workers inside a phase:

| Phase | Parallel workers |
|---|---|
| 1 | The executing agent writes the signatures of task 1.1. Then one S worker for tasks 1.1 and 1.4, one H worker for task 1.2, and one S worker for task 1.3, at the same time (different files). Test item 2 of task 1.4 waits for task 1.3. |
| 2 | The executing agent does task 2.1. Then one S worker for tasks 2.2 and 2.3. The executing agent does task 2.4. One S worker for task 2.5. |
| 3 | One S worker for tasks 3.1 and 3.2, and one S worker for tasks 3.3 and 3.4, at the same time. |
| 4 | One S worker for tasks 4.1 and 4.3, and one S worker for task 4.2, at the same time. Task 4.4 after both. |
| 5 | The executing agent. One H worker for the documents with the exact text. |

## 7. Questions still open

1. **The rephaser.** Proposal: the rule of section 4.4, item 1 (vb-pulseq's
   rule on the select coordinate), and `ProfileSpec.rephaser_moment_per_m`
   for a caller that knows better. Another choice: the moment up to the next
   ADC. That choice is wrong for a spin echo unless the card also models the
   refocusing pulse.
2. **The 2D map in the first version.** Proposal: yes (phases 3 and 4).
   Without it, phase 3 goes away, the card refuses a spec with two axes, and
   vb-pulseq keeps its own map for the column card.
3. **Groups without the offsets, a baseband simulation, and the move of the
   axis** (section 4.2, items 3 and 10). Proposal: yes. Another choice: the
   vb-pulseq groups (one RF event id is one pulse). The example GRE then
   shows 24 profiles of one pulse (section 2.3).
4. **A pulse whose gradient direction changes during the RF.** Proposal: no
   default profile, and the reason in the table. Another choice: a default
   map on the two axes with the largest gradient.
5. **Several files.** Proposal: one table for each file. Another choice: one
   table with a "Files" column, and groups across the files. The ex-vivo
   acquisition has 4 files with the same pulse.
6. **`MAX_POINTS`** (65,536) and the budgets of section 2.4.
7. **vb-pulseq.** Its `review-fixes` plan (Phase 8.2) moves its pulse
   profiles card onto `Card` as a project card. Proposal: vb-pulseq does 8.2
   as planned. A later vb-pulseq change uses this card and deletes its copies
   (section 4.8). Another choice: vb-pulseq waits for this card and does not
   move its pulse profiles card. The user decides in vb-pulseq.
8. **The release.** Proposal: the card is in 0.3.0. The PRs open at any
   time, and merge after the tag `v0.2.0` exists. Then a fix for 0.2.0 does
   not bring the card with it.
9. **The widths of a 2D profile.** Proposal: section 4.4, item 4. Another
   choice: no widths for a map.

## 8. Results

Phase 5 writes this section.
