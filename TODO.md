# TODO

Work that is planned but not started. Delete an item when its PR merges.

## Move from the pypulseq fork to a pypulseq release

**Why.** PNS at 10^7 blocks needs two changes of pypulseq that no release has
yet. This project pins them from the fork `mdtisdall/pypulseq` in
`[tool.uv.sources]` of `pyproject.toml` (`docs/plans/cards-at-scale.md`,
section 3.6):

| Fork branch | Commit | Change | Upstream |
|---|---|---|---|
| `pns-lfilter` | `e476200` | `safe_tau_lowpass` as a recursion (`scipy.signal.lfilter`), not a convolution: the PNS card of a 370 s file in 5.5 s instead of 258 s | not proposed yet (draft 06 of `github.com/mdtisdall/pypulseq-issues`) |
| `pns-chunked` | `20b9e5e` | `calc_pns` in chunks, and the chunk function `_safe_gwf_to_pns_chunk`: the memory of `calculate_pns` near the size of its result | not proposed yet (the same draft 06) |

The pin has two more consequences:

- The fork branches are on upstream `master` (`f2c582b`), so the pin also has
  28 upstream commits that are not in a release
  (`docs/plans/diagram-lanes.md`, section 2.6, item 5).
- `pns_levels.py` imports the private `_safe_gwf_to_pns_chunk`
  (`docs/plans/diagram-lanes.md`, decision 11). If the upstream review renames
  or changes it, `pns_levels.py` changes with it.

A project that depends on pulseq-reports gets stock pypulseq from PyPI unless
it adds the same source line (`docs/usage.md`).

**What.** When a pypulseq release has both changes: pin that release in
`[project] dependencies`, remove `[tool.uv.sources]`, change `pns_levels.py`
to the released name of the chunk function, and remove the fork paragraph of
`docs/usage.md`.

**How to check.** `scripts/check`, and `scripts/cards_scale.py --card pns` for
the 370 s file.

**When.** After the upstream pull requests are merged and released (the user
proposes them).

## Support the rotation extension

**Why.** The Pulseq rotation extension (MATLAB Pulseq 1.5.1, `mr.makeRotation`)
keeps a library of unit quaternions, with at most one rotation in each block.
The gradient events in the library are logical: the scanner rotates the
gradients of a block with its rotation. A radial or PROPELLER sequence can use
a few gradient events and a different rotation in each block. The cards that
use the gradients (diagram, gradient spectrum, PNS, gradient limits) show the
logical events as they are stored, so they would be wrong for such a sequence.
Until rotations are supported, these cards refuse a sequence with rotations:
`extensions.refuse_rotations` raises `NotImplementedError` (phase 6 of
`docs/plans/diagram-event-table.md`, PR #16).

pypulseq 1.5.0.post1 has no rotation extension (`pp.rotate` makes new, rotated
gradient events; it is not the extension). Its `Sequence.read` raises
`ValueError` for a `.seq` file with a rotation section. pypulseq draft PR #372
("[v1.5.1] Add rotation extension") adds `make_rotation` and a
`seq.rotation_library` of scalar-first quaternions; the guard already detects
that form. Related pypulseq PRs: #302 and #378 (`rotate3D`), #341 (a refactor
of `get_block`).

**What.** These decisions are already made (decisions 8 and 9 of section 2.3
of `docs/plans/diagram-event-table.md`):

- The diagram shows the rotated gradient axes first, with a button for the
  logical events as they are stored.
- Rotations come from pypulseq, not from a `.seq` reader of this library.
- Until then, the gradient cards refuse rotations. They do not draw unrotated
  gradients as if they were correct.

The diagram data format reserves these names (section 4.6 of that plan):
`"format": 2` for data with rotations; the tables `rotation` (uint8/16/32,
length N, dense rotation index, 0 = none) and `rotations` (float64, 9 values
for each rotation: the rotation matrix, row by row). `SeqLanes.decode` already
raises an error for format 2 and for an unknown table name. The other gradient
cards need the rotated waveforms too, and `refuse_rotations` is then removed
from each card that supports them.

**When.** After a pypulseq release has rotation support. Write a plan in
`docs/plans/` first.

## Use the gyromagnetic ratio of the sequence

**Why.** pypulseq keeps RF and gradient amplitudes in Hz and Hz/m. It converts
them from T and T/m with `seq.system.gamma`, which a caller sets for another
nucleus (`pp.Opts(gamma=...)`, for example 11.262e6 Hz/T for sodium).
`pp.Opts` uses `abs(gamma)`. This library converts back with the fixed
proton value `seq_utils.GAMMA` (42.576e6 Hz/T) in these places:

- `diagram_data.diagram_tables`: the gradient values of the diagram (mT/m).
- `waveforms.py`: the RF magnitude (µT) and the gradient lanes (mT/m) of the
  diagram.
- `grad_limits.py`: the peak, slew and RMS values, the |G| peak, and the
  pypulseq system limits (`seq.system.max_grad` and `max_slew`) of the
  gradient limits card.
- `rf_exposure.py`: |B1| (µT), and so the energy and the window values of
  the RF exposure card.

For a proton sequence nothing is wrong. For a sequence of another nucleus,
these values are wrong by the factor `seq.system.gamma / GAMMA`, and a
percent of a limit that the caller gives in physical units is wrong too.
`grad_spectrum.py` already uses `seq.system.gamma`. The PNS lane gets its own
fix (`gradScale`, decision 14 of `docs/plans/diagram-lanes.md`).

**What.** Use `abs(seq.system.gamma)` for each conversion, as pypulseq does.
Keep `GAMMA` only where no sequence is known. The diagram data format then
needs the gamma of each file (or values that are already converted), and
`gradScale` of the PNS data can become 1.0 or go away.

**How to check.** A test for each card with `pp.Opts(gamma=...)` of another
nucleus: the physical values (mT/m, µT) of an event made with physical units
equal those units. The existing tests (`scripts/check`) for proton sequences.

**When.** After phases 3 and 4 of `docs/plans/cards-at-scale.md` are merged
(they change `rf_exposure.py` and `grad_limits.py`), and after phase 4 of
`docs/plans/diagram-lanes.md` (the diagram data).

## Study the two definitions of the gradient slew rate

**Why.** This library uses two slew rates that are not the same:

- **The gradient limits check** uses the definition of pypulseq's own limit
  checks. In an event, the slew is the slope of each segment of the gradient
  polyline:
  - `make_trapezoid`: amplitude / rise time, and amplitude / fall time.
  - `make_extended_trapezoid`: `diff(waveform) / diff(tt)`.
  - `make_arbitrary_grad`: the difference of its raster samples /
    `grad_raster_time`, with half-raster edge segments.

  At a block junction, it is the step / `grad_raster_time`, as `add_block`
  checks it. (Decided on 2026-09-24. The card gets the junction steps in phase 4 of
  `docs/plans/cards-at-scale.md`.)
- **The SAFE PNS model** (pypulseq `safe_gwf_to_pns`) uses
  `dgdt = diff(g) / dt` of the gradient sampled at the half-raster times
  `(k + 0.5) * dt`.

`docs/notes/slew-definitions.md` (2026-09-24) compares the two definitions,
and the pypulseq and MATLAB Pulseq implementations of each, with figures. In
short:

- At a corner on the raster, `dgdt` is the average of the two slopes.
- For a ramp of exactly one raster interval, the largest `dgdt` is half the
  segment slope.
- At the edge of an arbitrary gradient, `dgdt` is half the slope of the
  half-raster edge segment.
- At a step at a block junction, the merged waveform puts the step into the
  first segment of the next event. `dgdt` can then reach about 2 ×
  `max_slew`. The limit check sees the step alone.

Without a step, `|dgdt|` is never larger than the largest segment slope (it
is a weighted average of the slopes).

**What.** Find out which definition each of these should use, and change
this library to match:

- The slew limit that the scanner applies (what the Siemens gradient system
  checks, and on which raster).
- The gradient limits card.
- A slew lane in the sequence diagram, next to the PNS lanes (planned). If
  it shows `dgdt`, it also needs one of the two time conventions: pypulseq
  and MATLAB Pulseq report the same `dgdt` value 10 µs apart.

Record the answer, and the sources for it. If pypulseq's own limit checks and
its SAFE model disagree in a way that matters, tell the pypulseq maintainers
(the user decides).

**When.** Before the slew lane of the sequence diagram is built. Until then,
keep both definitions as they are.
