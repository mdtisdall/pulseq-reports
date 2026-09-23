# TODO

Work that is planned but not started. Delete an item when its PR merges.

## Make the other cards work at 10^7 blocks

**Why.** The sequence diagram works for a file of up to 10^7 blocks
(`docs/plans/diagram-event-table.md`). The other cards were not made for that
size, and a long file can make them too slow or too large:

- **PNS:** pypulseq `calculate_pns` uses the whole sampled waveform. A 1 h file
  is about 3.6 × 10^8 samples for each axis, so several GB.
- **RF exposure and gradient limits:** they call `seq.get_block` for each
  block (about 18 µs for each block, so minutes at 10^7 blocks).
- **Gradient spectrum:** it is chunked. Its time grows with the duration of
  the file, not with the number of blocks (about 50 s for 1 h).
- **Block table:** it reads only the rows that it shows. No change is needed.

For scale: a synthetic GRE-like sequence of 10^7 blocks (5 blocks for each
TR, about 3.3 h) takes 87 s and 3.8 GB peak RSS to build in pypulseq
(phase 5 of `docs/plans/diagram-event-table.md`). The diagram card adds 13 s
and 0.2 GB to that.

**What.** Give each card a method whose time and memory do not grow with the
expanded waveform:

- RF exposure and gradient limits can use the block and event tables of
  `diagram_data.diagram_tables` (each unique event is expanded one time).
- PNS needs a chunked or windowed method.

**How to check.** A scale run, as `scripts/diagram_scale.py` does for the
diagram, for each card.

**When.** Write a plan in `docs/plans/` first. Each card can be its own phase.

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
