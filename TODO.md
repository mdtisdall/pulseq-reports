# TODO

Work that is planned but not started. Delete an item when its PR merges.

## Move from the pypulseq fork to a pypulseq release

**Why.** This project needs changes of pypulseq that no release has yet. It
pins them from the fork `mdtisdall/pypulseq` in `[tool.uv.sources]` of
`pyproject.toml`: the tag `pulseq-reports-pin-1` (branch `pulseq-reports-pin`,
commit `a74ab06`). That is the release 1.5.0.post1 with four commits. Each one
is a cherry-pick (`git cherry-pick -x`) of a commit on upstream `master` or on
a fork branch from upstream `master`:

| Pin commit | From | Change | Upstream |
|---|---|---|---|
| `250791d` | `e476200` (fork branch `pns-lfilter`) | `safe_tau_lowpass` as a recursion (`scipy.signal.lfilter`), not a convolution: the PNS card of a 370 s file in 5.5 s instead of 258 s | not proposed yet (draft 06 of `github.com/mdtisdall/pypulseq-issues`) |
| `3d826dd` | `20b9e5e` (fork branch `pns-chunked`) | `calc_pns` in chunks, and the chunk function `_safe_gwf_to_pns_chunk`: the memory of `calculate_pns` near the size of its result | not proposed yet (the same draft 06) |
| `8c089a1` | `6db882b` (fork branch `fix-oversampled-get-block`) | `get_block` gives an oversampled arbitrary gradient its correct `shape_dur` (B4 of `docs/reviews/2026-09-28-code-review.md`) | issue #423, PR #424 (open on 2026-09-29) |
| `a74ab06` | `36d9fa3` (upstream `master`) | `Sequence.read` does not hang on an unsigned file whose last section is `[TRAP]`, `[ADC]` or an extension | #359, merged, not in a release |

The pin has more consequences:

- Apart from the four commits, the pin is the release 1.5.0.post1. It has
  none of the other upstream commits after the release. A project that uses
  uv gets this pin too (`docs/usage.md`, section 1), and builds its own
  sequences with it.
- `pns_levels.py` imports the private `_safe_gwf_to_pns_chunk`
  (`docs/plans/diagram-lanes.md`, decision 11). If the upstream review renames
  or changes it, `pns_levels.py` changes with it.
- `v0.2.0rc1` pins the earlier fork commit `20b9e5e` (branch `pns-chunked`,
  on upstream `master` `f2c582b`). Do not delete that branch.

To change the pin: put each change for upstream on its own fork branch from
upstream `master` (for its pull request). Cherry-pick it onto
`pulseq-reports-pin`, tag the new commit `pulseq-reports-pin-<n + 1>`, and
pin that commit. Do not move or delete a tag.

**What.** When a pypulseq release has all four changes: pin that release in
`[project] dependencies`, remove `[tool.uv.sources]`, change `pns_levels.py`
to the released name of the chunk function, and remove the fork paragraph of
`docs/usage.md`. When a release has only some of them, make a new pin branch
from that release, with the other changes.

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
use the gradients (diagram, gradient spectrum, PNS, gradient limits, RF pulse
profiles) show the logical events as they are stored, so they would be wrong
for such a sequence.
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
`"format": 3` for data with rotations (format 2 is the one-sequence form of
the data); the tables `rotation` (uint8/16/32,
length N, dense rotation index, 0 = none) and `rotations` (float64, 9 values
for each rotation: the rotation matrix, row by row). The diagram script
already raises an error for a format other than 2, and `SeqLanes.decode`
raises an error for an unknown table name. The other gradient
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

## Validate every card against external references

**Why.** The first cards moved from vb-pulseq, and `scripts/vb_parity.py` checked
that each of them gave the same data as vb-pulseq at `3a1c7dd`. That checked the
move, not the physics: vb-pulseq and this library share their authors, so an
error in both passes. On 2026-09-28 the user decided that validation uses
external references, not vb-pulseq (decision 5 of `docs/plans/rf-profiles.md`),
and retired `scripts/vb_parity.py`. Until a card has external references, its
own tests and the oracles in `tests/oracles/` (also written in this project) are
its only checks.

**What.** For each card, find external references, and add fixtures and tests
with the method of phase 2b of `docs/plans/rf-profiles.md`: a script outside CI
makes small committed fixtures that record the tool, its version and the inputs,
and a pytest compares the library with them, with the reason for each tolerance.
Candidates to check (none is verified yet):

- PNS: pypulseq's `calculate_pns` and MATLAB Pulseq's SAFE model
  (`docs/notes/slew-definitions.md` already compares their slew parts).
- Gradient limits and timing: pypulseq's and MATLAB Pulseq's own checks.
- Sequence diagram: pypulseq `Sequence.waveforms` and MATLAB Pulseq
  `waveforms_and_times`.
- Gradient spectrum: a gradient spectrum function of MATLAB Pulseq, if there
  is one, or a published forbidden-band example.
- RF exposure: an analytic pulse train, and pypulseq's SAR code if its
  quantities are the same.

Some docstrings and `TESTS.md` entries still say that a format is the same as
vb-pulseq's ("parity"). They say where a format came from; replace them with the
external reference when a card gets one.

**When.** Now: phase 2b of `docs/plans/rf-profiles.md` (#59) shows the method, and
the RF pulse profiles have their references (section 8.4 of that plan). The user
decides the order of the cards.

## Show where the gradient limits happen

**Why.** `grad_limits.gradient_limits` finds where each extreme happens: for
each axis, `peak_block` and `peak_time_s` (the largest amplitude) and
`slew_block` (the largest slew), and for |G|, `GradientLimits.vector_peak_time_s`.
The gradient limits card shows only the values. The RF exposure card already shows
the block of its peak. The user chose to show them (C14 of
`docs/reviews/2026-09-28-code-review.md`, decision 18 of
`docs/plans/review-cleanup.md`).

**What.** Show the block and the time of each peak and of each largest slew on the
card, for each file and window. Check the tie rule first (finding L3 of the review:
on an exact tie, the credited block can be the later one).

**How to check.** `scripts/check`, and a test of the new cells for a sequence whose
peaks are at known blocks and times.

**When.** After this plan. It changes the card's output, so it is a feature, not
cleanup.

## Draw the diagram of a file with very many distinct RF events

**Why.** The diagram tables keep every phase sample of each distinct RF event
(`rf_phase`), and a new `phase_offset` makes a new RF event. Thus a file that
changes the RF phase in each TR (RF spoiling) gets a table that grows with the
number of TRs. For `diagram_scale.build_worst` at 10^6 blocks (2 × 10^5 TRs),
`rf_phase` has 392,000,000 float64 values (3.1 GB): the browser cannot decode
it (`decodeTable` fails with "Failed to fetch"), so the card does not draw. In
Python, the diagram card of the same file adds 10.7 GB of RSS, about 13 KB for
each block, most of it in `diagram_data.diagram_tables` and `encode_tables`.
Section 8.4 of `docs/plans/review-cleanup.md` has the measurements.

**What.** Find a form of the RF tables that does not repeat the samples of a
pulse for each phase offset, for example the shape once and the offset for
each event, in Python and in `seq_lanes.js`. Then measure the worst case of
`scripts/diagram_scale.py` at 10^6 and 10^7 blocks, in Python and in the
browser.

**How to check.** `scripts/check`; the Python and JavaScript dumps and the
golden tests of the diagram lanes give the same lanes; the worst case at 10^6
blocks draws in the browser.

**When.** After the review cleanup. It changes the card data (a new table
format), so it needs its own plan.
