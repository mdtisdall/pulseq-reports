# Plan: RF pulse profiles at the diagram cursor

Mode: Strict STE100. Structural rules are enforced. Lexical rules are a
direction of travel, not a verified dictionary match.

Status: in progress. The plan was written on 2026-09-28 (PR #51) and revised on
the same day with the user's answers (decisions 8 to 22 of section 2.2). On the
same day the user replaced parity with vb-pulseq by external references
(decision 5, phase 2b). No question is open (section 7).

## 1. Goal

The report shows the simulated profiles of the RF pulses at the cursor of the
sequence diagram, for any Pulseq sequence with RF use labels:

1. **The diagram publishes.** The diagram card publishes its cursor, its
   marker (the anchor that a click sets), its view and its decoded sequences
   as messages, through a publish/subscribe interface of the page. Any card
   can subscribe. Later visualizations can use the same messages.
2. **A new card, the RF profile card, subscribes.** For the period (the TR,
   section 2.5) at the diagram cursor, it simulates each distinct RF pulse as
   played (the RF with its offsets, and the gradients of its block) in the
   browser. It shows the 1D profile and the numbers of each pulse. It keeps
   each result in a cache.
3. **The combined profile of the first echo.** For a period with an
   excitation and refocusing pulses, the card also shows their combined
   effect on the first echo: the primary echo pathway only, and the card
   says so (decision 21). Pulses on one direction give a combined 1D
   profile. Pulses on different directions give a combined map (vb-pulseq's
   column cross-section, generalized).
4. **Two map views, switched on by the caller.** The caller that makes the
   report (the Python code, or a command line later) can switch on a z × Δf
   map (the select coordinate against the frequency offset) and 2D maps (two
   spatial axes: a pulse whose gradient direction changes during the RF, and
   the combined profile on different directions). The page has no control
   that switches them.
5. **A Python reference.** Python computes the same values for one period.
   Tests hold the JavaScript to it. vb-pulseq and CI gates can use it.
6. **A pulse list.** The card lists the distinct pulses of each file, with a
   button that moves the diagram to each one.
7. **RF use labels are necessary.** A file with an RF pulse without a use
   label gets a note in the card, not profiles. A public helper tells the
   caller before it adds the card (decision 22).

These items are not in this plan:

- Relaxation during the pulse (decision 7 of section 2.2).
- The rotation extension. The card refuses rotations, as the other gradient
  cards do (`extensions.refuse_rotations`).
- A 3D view, and a B1 axis in the card.
- The echoes after the first echo of a train (they also have stimulated-echo
  pathways; an extended phase graph model over the slice profile is a later
  item), and the effect of a preparation pulse on a later excitation (it
  needs T1 recovery).
- The coherence pathways card. It stays in vb-pulseq (decision 1).
- A command line. The code review of 2026-09-28 (item F1, branch
  `docs/code-review`, not merged) proposes one. When it exists, it passes the
  options of the card (section 4.5).
- Pulse design.

## 2. Read this first (context for the executing agent)

### 2.1 The state of the repository

- Read `docs/plans/pulseq-reports.md`, `docs/plans/cards-at-scale.md` and
  `docs/plans/diagram-lanes.md`. Their workflow rules apply to this plan too.
  This plan changes decision 7 of section 2.2 and item 2 of section 2.3 of
  `docs/plans/pulseq-reports.md` (decisions 1 and 11 below).
- `main` is at `b2200f4` (2026-09-28). The tag `v0.2.0rc1` is on `c7a284b`.
  The user tests the release candidate now. This plan is part of 0.2.0
  (decision 19): the tag `v0.2.0` waits for phase 6.
- The branch `feature/public-card-helpers` (commit `5a2ae35`, not pushed, no
  PR on 2026-09-28) gives public names to helpers of `markup.py`
  (`html_table`, `fmt`, `zoom_controls`, `lanes_json`, `Lane`), and adds
  `extra_css` to `render_page` and `write_page`. If it merges before phase 5,
  the card of phase 5 uses the public names.
- The vb-pulseq code that this plan starts from is at commit `3a1c7dd` (the
  commit that the library copied its first cards from) in `~/dev/vb_pulseq`. Read each file with
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
  project cards. This plan does not edit vb-pulseq (decision 18).
- The scripts of the studies of section 2.3 are in the session scratchpad of
  2026-09-28 (`q14/survey.py`, `q3/bench.js`). They are not part of this plan.

### 2.2 Decisions that are already made

Do not open these decisions again. The user made them or approved them.

1. **RF pulse profiles move to the library** (the user, 2026-09-28). This
   changes decision 7 of section 2.2 of `docs/plans/pulseq-reports.md` for
   `rf_sim.py`, `rf_profiles.py`, `profile_metrics.py` and the RF pulse
   profiles card. They move to the library in the general form of section
   4. The coherence pathways card, `moments.py` and `spin_echo.py` stay in
   vb-pulseq, because they know a spin echo (the project rule in
   `CLAUDE.md`). vb-pulseq's column cross-section becomes the combined map of
   this card (decision 21): the primary echo pathway is defined from the RF
   use labels and the ADCs, not from a spin echo.
2. **The library has its own simulator. No new dependency** (recommended on
   2026-09-28, section 2.3; the user asked for this plan after the
   recommendation). Decision 11 of section 2.2 of
   `docs/plans/pulseq-reports.md` stays: the dependencies are `pypulseq`,
   `numpy` and `scipy`.
3. **The model has N dimensions** (recommended on 2026-09-28). The simulator
   takes a list of points, so a grid of any number of axes costs nothing extra
   in the design. The card shows a 1D profile as lanes and the map views as
   maps.
4. **The earlier rules stay.** No plotting library, no JavaScript dependency,
   no build step (decision 9 of `docs/plans/pulseq-reports.md`). No DOM tests:
   Node tests cover pure functions, and a browser check covers each chart
   (decision 10). Lean on pypulseq: do not test pypulseq in this project
   (decision 6 of `docs/plans/diagram-lanes.md`).
5. **External references, not vb-pulseq** (the user, 2026-09-28; this
   replaces "parity with vb-pulseq" of the first version). vb-pulseq shares
   its authors with this library, so agreement with it does not validate the
   physics. The Python reference is checked against analytic results, an
   independent oracle (task 2.3), and external references (phase 2b): MATLAB
   Pulseq's `mr.simRf`, sigpy's `abrm_nd`, and pulse design theory (the
   specifications of an SLR design, the inversion band of an adiabatic
   pulse). No phase compares with vb-pulseq. The user also retired
   `scripts/vb_parity.py` on 2026-09-28 (its own chore PR). The `TODO.md`
   item "Validate every card against external references" finds references
   for the other cards.
6. **The gyromagnetic ratio of the sequence.** The new code converts Hz to µT
   with `abs(seq.system.gamma)`, as the `TODO.md` item "Use the gyromagnetic
   ratio of the sequence" asks. The simulation itself needs no gyromagnetic
   ratio: pypulseq keeps the RF in Hz and the gradients in Hz/m.
7. **No relaxation.** The spin-domain simulation (Cayley-Klein parameters)
   cannot include T1 or T2. This is normal for pulse profiles. It matters for
   long adiabatic pulses or for a very short T2. If the user needs it later,
   it is a separate simulator and a `TODO.md` item.
8. **The rephasing: the echo rule** (the user, 2026-09-28, question 1 of the
   first version). The card follows the primary echo pathway from the end of
   the RF to the centre of the next ADC, with a sign change at each
   refocusing pulse (section 4.2, item 7). It gives two numbers in place of
   the vb-pulseq "residual phase": the rephasing error (the linear phase
   across W that the sequence leaves) and the non-linear residual (the phase
   of the pulse itself after the best linear rephasing). The override of the
   caller is the keyword `echo_moment_per_m` of the reference functions
   `echo_phase` and `widths` (section 4.2). The card has no override: it
   applies the rule to the block at the cursor, so a dummy block or a
   partition-encode step shows its own pathway (decision 10).
9. **1D by default. The map views are options of the caller** (the user,
   2026-09-28, question 2 of the first version). The z × Δf map and the 2D
   map are arguments of the card builder (section 4.5), and later options of
   a command line. The page has no control that switches them.
10. **On demand, in the browser, at the cursor** (the user, 2026-09-28,
    question 3 of the first version). The page simulates the pulses at the
    diagram cursor when they are needed (decision 20 makes this the pulses of
    the period), and keeps the results in a cache. Each block is simulated as
    played, with its offsets. No grouping of blocks is necessary for a
    correct profile. The pulse list (item 6 of section 1) is only for
    navigation.
11. **The diagram publishes messages** (the user, 2026-09-28). A page-level
    publish/subscribe interface (section 4.1). This changes item 2 of section
    2.3 of `docs/plans/pulseq-reports.md` ("one card reads the data of another
    card"). The rule is now: a card never reads the data or the DOM of
    another card. Cards communicate only through published messages. The
    topics and the messages are public API: `docs/usage.md` documents them.
12. **A pulse whose gradient direction changes during the RF** (the user,
    2026-09-28, question 4 of the first version). It gets no 1D profile. The
    numbers and the reason show in the card. When the caller switches on the
    2D view, the 2D map shows it (section 4.3, item 4).
13. **All five topics now** (the user, 2026-09-28, question 1 of section 7):
    `sequence`, `cursor`, `anchor`, `view` and `goto` (section 4.1). No card
    of this plan subscribes to `view`. It is there for later visualizations.
14. **The cursor selects, the anchor pins** (the user, 2026-09-28, question
    2). The profile follows the hover cursor. A click or the arrow keys set
    the anchor, and the card then keeps the pulse of the anchor until a
    reset (section 4.5, item 3). Unfinished map work stops when the pulse
    changes.
15. **The pulse list, with "Show" buttons** (the user, 2026-09-28, question
    3). Section 4.5, item 4.
16. **The Python reference and the golden test** (the user, 2026-09-28,
    question 4). Python has the whole block pipeline (section 4.2). The
    JavaScript copy (section 4.6) must give the same values (section 3.5,
    item 2).
17. **The limits and the budgets** (the user, 2026-09-28, question 5):
    `MAX_POINTS = 65_536`, 2D maps of 128 × 128, and the budgets of section
    2.4, as written.
18. **vb-pulseq decides later** (the user, 2026-09-28, question 6). This plan
    does not tell vb-pulseq what to do with Phase 8.2 of its `review-fixes`
    plan. Section 4.7 lists what vb-pulseq can do when this plan is done.
19. **Part of 0.2.0** (the user, 2026-09-28, question 7). The tag `v0.2.0`
    waits for this plan. The phases merge to `main` when they are ready.
    After phase 6, the next release candidate (`0.2.0rc2`) is a separate
    chore PR, and its tag needs the user's approval, as for `0.2.0rc1`.
20. **The cursor selects a period, not a block** (the user, 2026-09-28,
    question 8). The hover cursor and the anchor select the period that
    contains their time (section 2.5), and the card shows each distinct pulse
    of that period. The user does not have to point at a pulse: a click
    anywhere in a TR pins that TR. Revised by the user on 2026-09-28 (phase 2
    found it): refocusing pulses never start a period. With the ADCs alone, a
    TSE was one period for each echo, because a refocusing pulse follows an
    ADC. The card needs the use labels anyway (decision 22).
21. **The combined profile of the first echo, primary echo pathway only**
    (the user, 2026-09-28, question 9). The excitation \|Mxy\| times \|β\|²
    of each refocusing pulse between that excitation and the first ADC of
    the period, with ideal crushers (vb-pulseq's `crushed_echo`). Preparation
    pulses do not take part. The card shows a clear note, in the words of
    section 4.3, item 7, directly above the combined profile: it is only the
    primary echo pathway (the user asked for this note).
22. **RF use labels are necessary: a note, and a helper** (the user,
    2026-09-28, question 10). The echo rule and the combined profile must
    know which pulses excite and which refocus, and the quantities of a
    profile depend on the use. A file with an RF event whose use is
    `undefined` gets a note in the card and no profiles (section 4.5, item
    1). The public function `rf_uses_labeled(seq)` returns False for such a
    file, so that a caller (or a command line) can leave the card out. The
    card does not raise an error: the other files of the report still get
    their cards.

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
of the RF (correct only at small flip angles). vb-pulseq `cayley_klein` and
sigpy `abrm_nd` agree within 4e-14 (a random complex RF of 1000 samples at 401
positions).

**The time of one simulation** (Mac with 10 cores and 64 GB; Python numpy
2.5.3; Node 24, which has the V8 engine of Chrome). All pulses are on the 1 µs
RF raster:

| Pulse | RF samples | numpy, 1D, 401 points | JavaScript, 1D, 401 points | JavaScript, z × Δf, 201 × 201, full | JavaScript, 128 × 128 |
|---|---|---|---|---|---|
| Example GRE sinc | 3000 | 52 ms | 14 ms | 1.3 s | 0.54 s |
| TSE excitation | 2500 | 42 ms | 11 ms | 1.1 s | 0.55 s |
| TSE refocusing | 2000 | 34 ms | 11 ms | 0.9 s | 0.36 s |
| EPI-SE fat saturation | 8000 | 138 ms | 36 ms | 3.6 s | 1.5 s |
| Hard pulse, 100 µs | 100 | 1.7 ms | 0.4 ms | 46 ms | 18 ms |

JavaScript takes about 11 ns for each point and each RF sample, with the exact
rotation of vb-pulseq (section 4.2, item 1).

**z × Δf with a constant gradient is a 1D simulation.** With a constant
gradient `G` during the RF, a spin at `u` with the frequency offset `Δf` has
the same rotation as a spin at `u + Δf / G` without an offset. With the Δf
step equal to `G` times the step of `u`, an `n × m` grid needs only `n + m - 1`
simulations (section 4.3, item 3).

**A survey of 13 pypulseq example sequences** (`write_gre`, `write_gre_label`,
`write_epi`, `write_epi_label`, `write_epi_se`, `write_epi_se_rs`,
`write_haste`, `write_tse`, `write_2Dt1_mprage`, `write_3Dt1_mprage`,
`write_mprage`, `write_radial_gre`, `write_ute`, at the pinned fork):

1. **Rephasing.** The residual select moment after the rephasing, divided by
   the moment that the rephasing must cancel (0 is correct):

   | Example | vb-pulseq rule (the rest of the block and the next block) | Echo rule (decision 8) |
   |---|---|---|
   | GRE, GRE label, EPI, EPI label, EPI-SE, 2D MPRAGE, radial GRE | 0.000 | 0.000 |
   | TSE | +1.870 | 0.000 |
   | HASTE | +1.870 | 0.000 |
   | EPI-SE with refocusing slice shifts | +1.065 | 0.000 |

   In TSE and HASTE, the next block has the slice rephaser and the crusher of
   the first refocusing pulse in one gradient. The echo rule needs an ADC
   before the next excitation: in TSE (the first excitation) and in the
   radial GRE (20 dummy scans), the first blocks have none.
2. **Distinct pulses.** pypulseq makes a new RF event for each new frequency
   or phase offset:

   | Example | Blocks with RF | RF and gradient event ids (vb-pulseq pulses) | Without offsets, block gradient ids | Without offsets, gradients during the RF |
   |---|---|---|---|---|
   | GRE (RF spoiling) | 64 | 24 | 1 | 1 |
   | EPI label (7 slices) | 28 | 7 | 1 | 1 |
   | radial GRE | 81 | 24 | 1 | 1 |
   | MPRAGE | 2,940 | 2,822 | 2,822 | 2 |

   The MPRAGE RF blocks also hold the rewinder and phase-encode gradients of
   the previous readout. They do not play during the RF.
3. **Gradient kinds.** Every pulse of the 13 examples has a gradient in one
   direction, constant during the RF, or no gradient. None has a gradient
   whose direction changes.

**What in vb-pulseq knows its own sequences** (`rf_profiles.py` at
`3a1c7dd`): a profile only for a trapezoid on one axis with the RF inside its
flat top; no profile without a gradient; one pulse for each combination of RF
and gradient event ids (item 2 above); the rephaser rule of item 1 above; the
frequency and phase offsets are ignored.

**The diagram card now.**

1. `assets/lane_chart.js`: `laneChart` has a hover cursor (`setCursor`,
   `cursorText`) and a marker that a click or the arrow keys set (`anchor`,
   `setAnchor`, the zoom centre). Neither is visible outside the chart.
2. `assets/seq_lanes.js`: `SeqLanes.blockAt(model, t)` and
   `SeqLanes.blockStart(model, i)` find a block and its start in a decoded
   file (`t` in seconds).
3. The diagram tables (`diagram_data.diagram_tables`) have the gradients of
   each event exactly, in mT/m: the Hz/m of pypulseq divided by
   `seq_utils.GAMMA` and multiplied by 1e3. Their RF columns are for display
   only: the magnitude in µT, the phase only where the magnitude is above 1 %
   of its peak, and the offsets inside the phase. A simulation cannot use
   them. The event columns `rf`, `gx`, `gy`, `gz` and `adc` are the dense
   indexes of `seq_index.SequenceIndex` (0 is no event).
4. `assets/cards/diagram.js` has its own `decodeTable` (base64, gzip,
   typed array).

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
5. **The use label is `undefined` unless the author sets it.** Each
   `make_*_pulse` function has `use: str = 'undefined'`. The pypulseq
   examples, vb-pulseq and the ex-vivo file (format 1.5, `e` on each RF event)
   set it.
6. **A file older than format 1.5 has no use field.** The method
   `Sequence.read` has `detect_rf_use=False` by default, so each use of such a
   file is `undefined`. With `detect_rf_use=True`, pypulseq guesses the use
   (`read_seq.py`): a flip angle below 90.01° is `excitation`; any other pulse
   is `refocusing`, or `saturation` when it is longer than 6 ms and between
   −3.5 and −3.4 ppm off resonance. So an inversion pulse is then read as
   `refocusing`. (The function `read_seq.read` itself guesses by default for
   such a file; `Sequence.read` passes False.) The `Sequence` object does not
   keep the format version of the file, so this library cannot tell a guessed
   label from a label of the author. (Corrected on 2026-09-28: the first text
   said that `Sequence.read` guesses by default.)
7. **pypulseq stores `use="other"` as undefined.** `register_rf_event`
   (`Sequence/block.py`) keeps the letter of only five uses; `other` becomes
   `u`, so `get_block` and a written file give `undefined` for such a pulse,
   and the card refuses its file. MATLAB Pulseq keeps `o`. A draft upstream
   issue with a fix is in `github.com/mdtisdall/pypulseq-issues` (08).

### 2.4 Budgets (approved by the user on 2026-09-28, decision 17)

**Python, for one file.** "Card" is `rf_profile_card` with its defaults.

| Quantity | vb-pulseq sequences, example GRE | 10^7 repeating blocks |
|---|---|---|
| Python time of the card, with `SequenceIndex` | at most 2 s | at most 20 s |
| Python peak RSS added | at most 0.2 GB | at most 1 GB |
| Page size of the card | at most 0.5 MB | at most 0.5 MB |

**Browser.**

| Quantity | Budget |
|---|---|
| All handlers of one cursor message, without a new simulation | at most 1 ms |
| A 1D profile of a pulse of 3000 RF samples, first time | at most 50 ms |
| A z × Δf map, constant gradient, first time | at most 50 ms |
| A full map (128 × 128 or 201 × 201) of a pulse of 3000 RF samples | at most 3 s, in slices of at most 20 ms each |
| A result from the cache | at most 16 ms (one frame) |
| The combined profile, after the profiles of its pulses (1D, or a map of logical axes) | at most 16 ms |

The budgets of a pulse apply to each distinct pulse of a period.

If a budget fails, stop and tell the user. Do not change a budget yourself.

### 2.5 Terms

- **Topic, message, publisher, subscriber.** A topic is a name. A publisher
  sends a message (a plain object) on a topic. Each subscriber of the topic
  gets it (section 4.1).
- **Anchor.** The marker of the diagram chart that a click or the arrow keys
  set. It pins the period of the RF profile card.
- **Period.** The blocks from one period start to the block before the next
  period start. A block is a **period start** when it has an RF that is not a
  refocusing pulse, and the last block before it that has an RF or an ADC has
  an ADC; the first block with an RF is always a start. (A block with both
  counts its ADC after its RF.)
  In a GRE a period is one TR; in a TSE it is one echo train; dummy scans
  without an ADC join the period of the first ADC after them.
- **The period at the cursor.** The period that contains the block at the
  anchor, or at the cursor when there is no anchor. Before the first period
  start: the first period (section 4.5, item 3).
- **Distinct pulses of a period.** The RF blocks of the period, grouped by
  pulse key, in the order of their first block, each with its count.
- **Primary echo pathway.** For the first ADC of a period: the magnetization
  that the last excitation before that ADC makes, refocused one time by each
  refocusing pulse between them, with ideal crushers. The FID and the
  stimulated-echo pathways are not in it.
- **Combined profile.** The profile of the primary echo pathway: the
  excitation \|Mxy\| times \|β\|² of each of those refocusing pulses (section
  4.3, item 7).
- **Offsets.** The four offsets of an RF event: `freq_offset`, `freq_ppm`,
  `phase_offset` and `phase_ppm`. The **total frequency offset** is `f =
  freq_offset + freq_ppm * 1e-6 * abs(gamma) * B0` (Hz), and the total phase
  offset has the same form.
- **As played.** The RF samples with the total offsets:
  `signal * exp(1j * (phase + 2π * f * t))`, `t` at the centre of each hold
  interval.
- **Hold interval.** The time of one RF sample from `hold_samples`: the
  interval `[k * dt, (k + 1) * dt]` from the start of the RF shape.
- **Gradient kind.** For the gradients during the RF: `none` (all zero),
  `one` (one direction, section 4.2, item 4), or `changing`.
- **Select coordinate.** The position along the gradient of a pulse of kind
  `one`: a logical axis (`x`, `y` or `z`) when the gradient is on one axis,
  else `select` (along the unit vector of the mean gradient).
- **Slice centre.** The position of the select coordinate where the total
  frequency offset puts the profile: `f / G`.
- **Views.** `profile` (the 1D profiles and the combined 1D profile,
  always), `z_df` (the select coordinate × Δf) and `2d` (two spatial axes:
  a pulse of kind `changing`, and the combined profile on different
  directions). The caller switches on `z_df` and `2d`.
- **RF table.** The data of the RF profile card: the RF events of a file at
  baseband, with their offsets and uses (section 4.5, item 2).
- **Pulse key.** The file, the RF event without its phase offsets
  (`phase_offset` and `phase_ppm`), and the gradient events that play during
  the RF. A constant phase only turns the whole profile, and the card shows
  \|Mxy\|, Mz, \|β\|² and phases relative to the slice centre, so two blocks
  with the same key have the same profiles. RF spoiling then gives one key,
  not one key for each phase.
- **Reference.** The Python functions of `rf_profiles.py`. The JavaScript of
  `assets/rf_profiles.js` must give the same values (section 3.5).

## 3. How to execute this plan

### 3.1 Workflow

As in `docs/plans/cards-at-scale.md`, section 3.1, items 1 to 8. At most three
PRs open at one time. There is no vb-pulseq parity check (decision 5).

### 3.2 Worker model tiers

As in `docs/plans/cards-at-scale.md`, section 3.2: H (`haiku`), S (`sonnet`),
O (the executing agent). Give each worker the exactness and reference rule
(section 3.5).

### 3.3 Order and parallel work

```
Phase 0 (TESTS.md) ─┬─► Phase 1 (messages) ──────────────────────────────────┐
                    ├─► Phase 2 (Python reference) ─┬► Phase 3 (JavaScript) ──┼─► Phase 5 (card) ─► Phase 6
                    │                               └► Phase 2b (external references) ─► Phase 6
                    └─► Phase 4 (map chart) ─────────────────────────────────┘
```

- Phase 0 first. Then phases 1, 2 and 4 at the same time: they edit
  different files (section 3.4).
- Phase 3 after phases 2 and 4: its golden test needs the reference of phase
  2, and it adds a line to the script order of `page.py` after the line of
  phase 4.
- Phase 2b after phase 2, at the same time as phases 3 and 5: it adds only
  its own files.
- Phase 5 after phases 1, 3 and 4. Phase 6 last.

### 3.4 File ownership

Package root: `src/pulseq_reports/`. Tests: `tests/`.

| Phase | Files that the phase creates or edits |
|---|---|
| 0 | `TESTS.md` (only: placeholder sections 2.28 to 2.34, task 0.1) |
| 1 | `assets/lane_chart.js` (the message functions, `decodeTable`, and the `laneChart` options `onCursor` and `onAnchor` and the method `setAnchor` only), `assets/seq_lanes.js` (only the new function `sequenceView`), `assets/cards/diagram.js`, `tests/js/test_messages.js` (new), `tests/js/test_seq_lanes.js` (new tests only), `docs/usage.md` (a new section "Messages between cards"), `TESTS.md` sections 2.19 (new entries only) and 2.28 |
| 2 | `rf_sim.py` (new), `profile_metrics.py` (new), `rf_profiles.py` (new), `tests/oracles/rf_sim.py` (new), `tests/test_rf_sim.py` (new), `tests/test_profile_metrics.py` (new), `tests/test_rf_profiles.py` (new), `TESTS.md` sections 2.29, 2.30 and 2.31 |
| 2b | `scripts/rf_references.py` (new), `tests/fixtures/rf_references/` (new), `tests/test_rf_references.py` (new), `TESTS.md` (a new section 2.35 at the end) |
| 3 | `assets/rf_profiles.js` (new), `page.py` (only the script order), `tests/js/test_rf_profiles.js` (new), `tests/test_rf_profiles_golden.py` (new), `tests/js/golden_rf_profiles.js` (new), `tests/test_page.py` (only `test_script_order`), `TESTS.md` sections 2.3 (that entry only), 2.32 and 2.33 |
| 4 | `assets/map_chart.js` (new), `assets/chart_math.js` (new pure functions only), `assets/report.css` (new map chart rules only), `page.py` (only the script order), `tests/js/test_chart_math.js` (new tests only), `tests/test_page.py` (only `test_script_order`), `docs/usage.md` (a new subsection of section 4 only), `TESTS.md` sections 2.3 (that entry only) and 2.4 (new entries only) |
| 5 | `cards/rf_profile.py` (new), `assets/cards/rf-profile.js` (new), `tests/test_rf_profile_card.py` (new), `examples/gre_report.py`, `docs/examples/gre.html` (rebuilt), `docs/usage.md` (sections 2 and 5, and a new subsection), `README.md` (the card table of "The cards" only), `TESTS.md` section 2.34 |
| 6 | `scripts/cards_scale.py` (only a new card name), `TODO.md`, `docs/usage.md` (the scale table, and the references paragraph of the card's subsection), `docs/plans/pulseq-reports.md` (one note on decision 7 of section 2.2 and one on item 2 of section 2.3 only), this plan file (status and results only) |

Rules: as in `docs/plans/cards-at-scale.md`, section 3.3, items 1 to 3.
`tests/oracles/` is a namespace package: add no `__init__.py`. Phases 3 and 4
both change the script order of `page.py` and `test_script_order`. Phase 3
starts after phase 4 is merged, so they do not conflict.

### 3.5 The exactness and reference rule

1. **The Python simulator against the oracle.** `rf_sim.spin_domain` and the
   oracle `tests/oracles/rf_sim.py` must agree within 1e-10 on each component
   of the magnetization (a unit vector). The oracle uses a different method
   (3 × 3 rotations of the magnetization, task 2.3), so a shared error is
   unlikely.
2. **JavaScript against the reference.** For the same block and the same
   spec, `a` and `b` of `assets/rf_profiles.js` must agree with the reference
   within 1e-12 (their size is at most 1). Each width must be equal, or differ
   by one grid step only where a profile value is within 1e-9 of a threshold
   (write the reason in the test). The golden test of phase 3 checks this.
3. **Analytic cases.** Each analytic test writes its tolerance and the reason
   for it in the test.
4. **External references** (phase 2b). Each comparison with an external
   reference has a tolerance, and the test writes the reason for it: the
   same rotation computed by another program (sigpy) agrees to float
   rounding; a program that resamples the RF (MATLAB Pulseq's `mr.simRf`)
   agrees within the error of its resampling, which task 2b.3 measures; a
   design specification (SLR) or an analytic band (adiabatic inversion) is a
   bound, not a value. A difference larger than its reason explains is a
   finding: stop and tell the user. Do not widen a tolerance to make a test
   pass.
5. **The map values in the page.** The card sends no map values: the browser
   computes them. The legend and the tooltip show the computed values.

## 4. Design

### 4.1 Messages between cards (phase 1)

**The interface** (in `assets/lane_chart.js`, on `PulseqReport`):

```js
PulseqReport.publish(topic, message)  // message: a plain object with `source` (a card id)
PulseqReport.subscribe(topic, handler, {replay = true} = {})  // returns an unsubscribe function
```

1. The page keeps the last message of each pair (topic, source). With
   `replay`, `subscribe` calls the handler at once with each kept message of
   the topic, in the order of publication. So the order in which `page.js`
   starts the cards does not matter.
2. The handlers of a topic run in the order of subscription. A handler that
   throws does not stop the other handlers or the publisher: the page writes
   the error to the console with the topic and the source.
3. A `publish` inside a handler is delivered after the current delivery ends
   (a queue), not inside it.
4. `publish` freezes the message object (`Object.freeze`, one level).
5. A handler must be fast: a cursor message can come once in each animation
   frame. A subscriber does long work later, in slices (section 4.5, item 5).

**The messages of a diagram card** (card id `D`). Times are file times in
seconds. `block` is the play index (0 is the first block). `file` is the index
of the file in the card's list.

| Topic | Message | When |
|---|---|---|
| `sequence` | `{source: D, file, name, view}` | One time for each file, when the diagram has decoded it. `view` is the sequence view (below). |
| `cursor` | `{source: D, file, tS, block, pxS}`, or `{source: D, file: null}` | The hover cursor moves (at most one message in each animation frame), or leaves the plot. `pxS` is the time of one pixel of the current view. |
| `anchor` | `{source: D, file, tS, block}`, or `{source: D, file: null}` | A click or the arrow keys set the anchor, or a reset clears it. |
| `view` | `{source: D, file, t0S, t1S}` | After each view change and each change of file. |

**The message that a diagram card receives.**

| Topic | Message | What the diagram does |
|---|---|---|
| `goto` | `{target: D, file, block}` | It shows the first window of that file (if the file is not shown), sets the view to the block with half its duration on each side (at least 1 ms in all), and sets the anchor at the middle of the block. Then it publishes `view` and `anchor`. A file with no window: it writes a warning to the console and does nothing. |

**The sequence view** (`SeqLanes.sequenceView(model)`, pure, Node tests). A
read-only object over the decoded tables of one file. A subscriber uses it,
and never the tables or the model:

```js
view.numBlocks, view.durationS
view.blockAt(tS)            // SeqLanes.blockAt
view.blockStart(i)          // SeqLanes.blockStart
view.blockDuration(i)
view.events(i)              // {rf, gx, gy, gz, adc}: dense event indexes, 0 = none
view.gradEvent(k)           // {delayS, offsetsS, values}: typed arrays, do not change them
view.gradHzPerValue         // the factor from `values` to Hz/m (GAMMA * 1e-3 now)
view.adcEvent(k)            // {delayS, lengthS}
view.rfDelayS(k)
```

The dense event indexes are those of `seq_index.SequenceIndex`. A card that
has its own data for the same `NamedSequence` list (for example the RF table
of section 4.5) can use them as keys.

**Changes in the charts.**

1. `laneChart` gets two options, `onCursor(x, pxX)` (x is null when the cursor
   leaves) and `onAnchor(x)` (null when a reset clears it), and a method
   `setAnchor(x)`. Without the options, `laneChart` works as now.
2. `PulseqReport.decodeTable(entry)`: the `decodeTable` of
   `assets/cards/diagram.js`, moved without a change of behavior.
   `diagram.js` then calls it.
3. `diagram.js` publishes the messages of the table above, and subscribes to
   `goto`.

### 4.2 The Python reference (phase 2)

**The simulator** (`rf_sim.py`):

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
2. The signs are the signs of vb-pulseq. `magnetization`, `crushed_echo` and
   `precess` are the vb-pulseq functions; `precess` takes a moment vector and
   positions `(m, 3)`.
3. `profile_metrics.py` is a copy of vb-pulseq `profile_metrics.py`.

**One block** (`rf_profiles.py`):

```python
def block_pulse(seq: pp.Sequence, block: int) -> BlockPulse | None  # block: the play index
```

`None` when the block has no RF. `BlockPulse` (a frozen dataclass) holds the
values below.

1. **Guard.** `refuse_rotations(seq)` first.
2. **The RF as played.** `hold_samples(rf, seq.system.rf_raster_time)`, times
   the total offsets at the centre of each hold interval. Also the use, and
   the total frequency offset `f`.
3. **The gradient of each hold interval.** For each axis, the points of the
   block's gradient event from `seq_utils.gradient_points(g, 0.0)`. The
   gradient is linear between the points and zero outside the event. The
   value for interval `k` is the exact integral of this function over
   `[rf.delay + k * dt, rf.delay + (k + 1) * dt]`, divided by `dt`. On the
   flat top of a trapezoid it is the flat-top amplitude, as in vb-pulseq. A
   gradient on the ramps, a VERSE gradient or an arbitrary gradient needs no
   special case.
4. **The gradient kind.** `none` when every interval value is exactly zero.
   `one` when the mean vector `m` is not zero and every interval vector `g` is
   parallel to it: `|g - (g · u) u| <= 1e-9 * max |g|` with `u = m / |m|`.
   `changing` for all other cases. The select coordinate of kind `one` is the
   logical axis when only one axis has a gradient, else `select` along `u`.
   The gradient is **constant** when every interval vector equals the mean
   within a relative 1e-9. The signed select amplitude `G` is the amplitude
   on the logical axis, or `|m|` for `select`.
5. **The numbers** (as vb-pulseq, with the gyromagnetic ratio of decision 6):
   - flip angle (degrees): `degrees(2π * |sum(signal) * dt|)`.
   - peak B1 (µT): `max |signal| / |gamma| * 1e6`.
   - RF energy (µT²·ms): `sum((|signal| / |gamma| * 1e6)^2) * dt * 1e3`.
   - W (m): the `SliceThickness` definition, or None.
   - the slice centre `f / G` (kind `one`).
6. **The pulse key** (section 2.5): the RF event without its phase offsets,
   and the gradient events whose time in the block overlaps
   `[rf.delay, rf.delay + shape_dur]`.
7. **The echo pathway** (decision 8). Start with the moment vector `m = 0` at
   the end of the RF. Walk forward in play order: add the gradient moment of
   each interval (x y z), and at the centre of each refocusing RF, change the
   sign of `m` and count it. Stop at the centre of the first ADC:
   `echo_moment_per_m = m` and `echo_sign = (-1)^(the count)`. Stop at the
   start of the next excitation RF, or at the end of the file, with no ADC:
   the pathway is None, with the reason "no ADC before the next excitation".
   An RF labeled `inversion`, `saturation`, `preparation` or `other` before
   the ADC: the pathway is None, with the reason "an RF pulse that is not a
   refocusing pulse lies between this pulse and the ADC" (its effect on the
   pathway is not known from its label). The Mxy of the primary echo, before
   its constant phase, is `precess(mxy, m, r)` for `echo_sign = +1`, and
   `precess(conj(mxy), m, r)` for `-1`.
8. **The period** (decision 20, section 2.5).
   `period(seq, block) -> Period`: the first and the last block of the
   period that contains `block`, its distinct pulses (pulse key, use, first
   block, last block, count, in the order of their first block), and the
   first ADC block of the period (or None). The walk in each direction stops
   after `PERIOD_MAX_BLOCKS = 100_000` blocks; the period then has the flag
   `truncated` and the card says so. The echo pathway of a distinct
   excitation is that of its last block in the period, the one nearest to
   the ADC.
9. **The labels** (decision 22). `rf_uses_labeled(seq) -> bool`: False when
   an RF event of `seq` has the use `undefined`. It reads only
   `seq.rf_library.type`, so its cost does not grow with the number of
   blocks. `block_pulse` and `period` raise `ValueError` for such a
   sequence.

**Specs.**

```python
AXIS_KINDS = ("x", "y", "z", "select", "df")
MAX_POINTS = 65_536  # 256 x 256
NUM_POSITIONS = 401  # the points of a 1D profile (vb-pulseq)


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
```

1. **Rules** (`ValueError` for each one): each kind at most once, in the axes
   and in `at` together; `select` not together with `x`, `y` or `z`; `select`
   only for a pulse whose select coordinate is `select`; `n >= 2` and
   `lo < hi` for each axis; the product of the `n` values at most
   `MAX_POINTS`.
2. **Values that are not axes.** Positions 0 m and `df` 0 Hz.
3. **The grid.** `numpy.linspace(lo, hi, n)` for each axis, `numpy.meshgrid`
   with `indexing="ij"`, flattened in C order. `a` and `b` have the shape
   `(n1, n2, ...)`.

```python
def rf_uses_labeled(seq: pp.Sequence) -> bool
def period(seq: pp.Sequence, block: int) -> Period
def view_spec(pulse, view="profile", *, plane=None, extent_m=None, n=None) -> ProfileSpec | None
def simulate(pulse: BlockPulse, spec: ProfileSpec) -> Profile
def quantity(profile: Profile, name: str) -> np.ndarray  # "mxy_abs", "mz", "beta_sq"
def echo_phase(pulse: BlockPulse, profile: Profile, *, echo_moment_per_m=None) -> np.ndarray | None
def widths(pulse: BlockPulse, profile: Profile, *, echo_moment_per_m=None) -> dict[str, float]
def combined_profile(seq: pp.Sequence, per: Period, *, view="profile", n=None) -> CombinedProfile | None
def pulse_list(seq: pp.Sequence) -> list[PulseSummary]
```

`Profile` holds the spec, the grid values of each axis, and `a` and `b`.
`CombinedProfile` holds the pulses that take part, the directions, the grids,
the combined values (1D for each direction, and the maps for `view="2d"`),
the numbers of section 4.3, item 7, or the reason when there is none. The
signatures are proposals. Task 2.1 (tier O) fixes them before a worker
starts.

### 4.3 The views (phase 2, the same in phase 3)

`view_spec` gives the spec of each view, or None when the view does not apply
to the pulse (the card then shows the reason).

1. **`profile`** (always):
   - kind `one`: one axis, the select coordinate, from `c - 2W` to `c + 2W`
     with `NUM_POSITIONS` points, where `c` is the slice centre. Without W,
     the half range is 2 times the thickness from the RF spectrum (vb-pulseq
     `_spectrum_thickness`: the FWHM of the zero-padded spectrum divided by
     `|G|`), and a note says "no SliceThickness definition".
   - kind `none`: one axis `df`, from `f - 2B` to `f + 2B` with
     `NUM_POSITIONS` points, where `B` is the FWHM of the RF spectrum (Hz)
     and `f` the total frequency offset.
   - kind `changing`: None, with the reason "the gradient direction changes
     during the RF" (decision 12).
2. **The quantities by use:**

   | Use | Lanes of the 1D profile | Main quantity (maps) | Profile for the widths |
   |---|---|---|---|
   | excitation | \|Mxy\|, Mz, phase at the echo | \|Mxy\| | \|Mxy\| |
   | refocusing | \|β\|² | \|β\|² | \|β\|² |
   | inversion | Mz | Mz | (1 - Mz) / 2 |
   | saturation | Mz | Mz | 1 - Mz |
   | preparation, other | \|Mxy\|, Mz | \|Mxy\| | \|Mxy\| |

   The excitation and refocusing rows are those of vb-pulseq. vb-pulseq shows
   \|Mxy\| and Mz for inversion and saturation. The new rows show Mz, because
   an inversion or saturation pulse is judged by Mz. There is no row for
   `undefined`: the card needs a label on each pulse (decision 22).
3. **`z_df`** (a caller option, kind `one` only). The axes: the select
   coordinate of the `profile` view, but with `(NUM_POSITIONS + 1) / 2`
   points (201), and `df` with the same number of points, centred on 0 Hz,
   with the step `|G|` times the step of the select coordinate (the range is
   then 2 times the bandwidth of the slab on each side). With a constant
   gradient, `simulate` computes the `n + m - 1` distinct values of `u + Δf /
   G` as a 1D simulation (section 2.3). Without a constant gradient, it
   computes the whole grid. Kind `none`: None, with the reason "no gradient:
   the profile against Δf is the 1D profile".
4. **`2d`** (a caller option). For one pulse of kind `changing`: two logical
   axes (`plane`, given by the caller, else the two axes with the largest RMS
   gradient during the RF), each from `-e/2` to `+e/2` with 128 points, where
   `e` is `extent_m` of the caller, else the `FOV` definition of that axis.
   With neither: None, with the reason "no FOV definition: give extent_m".
   Kinds `one` and `none`: no map of the single pulse, because a spatial map
   of such a pulse is only stripes. The `2d` option also switches on the
   combined maps (item 7).
5. **The phase at the echo** (excitation, the `profile` view of kind `one`):
   the phase of the primary echo (section 4.2, item 7), relative to its value
   at the slice centre, where \|Mxy\| is at least 10 % of its maximum
   (vb-pulseq). None without an echo pathway, and the card says "no ADC
   before the next excitation".
6. **The widths** (the `profile` view only, on the profile for the widths, in
   the units of the axis): `fwhm` and `edge_width`; `passband_ripple` and
   `stopband_level` only on the select coordinate with W. For excitation with
   an echo pathway and W:
   - **rephasing error** (rad): the slope of the linear fit of the echo
     phase over `|u - c| <= 0.4 W` (weights \|Mxy\|), times W.
   - **non-linear residual** (rad): the peak-to-peak of the echo phase minus
     that linear fit, over the same range.
   - **centre phase** (rad): the phase of the echo Mxy at the slice centre
     (as vb-pulseq `center_phase_rad`).
7. **The combined profile** (decision 21, `combined_profile`).
   - **The pulses.** The period must have an ADC. The excitation is the last
     excitation block before the first ADC of the period. The refocusing
     pulses are the refocusing blocks between that excitation and that ADC.
     No combined profile (None, with the reason in the card) when there is
     no such excitation, no refocusing pulse (a GRE: the combined profile
     would be the excitation profile), a pulse of kind `changing`, or an RF
     of another use between the excitation and the ADC (item 7 of section
     4.2 has the same guard). Preparation pulses before the excitation do
     not take part.
   - **The values.** The excitation \|Mxy\| times \|β\|² of each refocusing
     pulse, at the same points. A refocusing pulse of kind `none` has the
     same \|β\|² at each position: it is a factor, its value at Δf = 0 (the
     card shows it as a number).
   - **The directions.** The distinct select directions of the pulses of
     kind `one` (two directions are the same when their unit vectors are
     parallel within 1e-9).
     - One direction: the combined 1D profile on the grid of the excitation's
       `profile` view. Each refocusing pulse is simulated at the same points
       (no interpolation).
     - Two directions: no combined 1D profile. With the `2d` option, a map
       over the plane of the two directions: two logical axes when both
       directions are logical axes (else the plane of the two unit vectors,
       with in-plane axes `s1` along the first direction and `s2`
       perpendicular to it), each with 128 points over the union of the
       `profile` ranges of its pulses. For logical axes, the map is the
       outer product of the 1D products of each axis (no new simulation).
       Otherwise each pulse is simulated at the projection of each grid
       point on its direction.
     - Three directions (for example PRESS): with the `2d` option, the three
       central sections: the map of each pair of directions through the
       slice centre of the third.
     - More than three directions: no combined maps, with the reason.
   - **The numbers.** For each direction: the FWHM and the 10–90 % edge of
     the combined 1D profile (one direction only); the signal kept, the
     integral of the combined profile divided by the integral of the
     excitation \|Mxy\| over the same grid; with W: the fraction of the
     combined signal inside `|u - c| <= W / 2` (vb-pulseq `_fraction_inside`),
     multiplied over the directions (inside W × W for two directions, as
     vb-pulseq `signal_fraction`); the combined value at the slice centres
     (vb-pulseq `center_signal`).
   - **The note** (the user asked for it). The card shows this text directly
     above the combined profile, as a visible paragraph, not a tooltip:

     > **Primary echo pathway only.** This is the excitation |Mxy| times
     > |β|² of each refocusing pulse before the first ADC of this period,
     > with ideal crushers. It does not include the FID or stimulated-echo
     > pathways, the later echoes of an echo train, the effect of
     > preparation pulses, or relaxation.

     `docs/usage.md` has the same text in its section for the card.

### 4.4 The map chart (phase 4)

1. **Pure functions in `chart_math.js`** (Node tests):
   - `colorRamp(stops, n)`: `n` RGB colors, linear between the stops.
   - `colorIndex(value, domain, n)`: the index of a value in the ramp,
     clamped.
   - `nearestIndex(lo, hi, n, value)`: the nearest grid index on a uniform
     axis, clamped.
2. **`PulseqReport.mapChart(options)`** in the new `assets/map_chart.js`
   (loaded after `lane_chart.js`), from vb-pulseq `columnChart` (`report.js`
   lines 520 to 727 at `3a1c7dd`). Options: `canvas`, `svg`, `chart`, `tip`
   (existing elements), `x`, `y` (axes `{lo, hi, n, label}`), `values`
   (`Float32Array` or `Float64Array`, row-major `(n_y, n_x)`), `domain`,
   `scale` (`"sequential"` or `"diverging"`), `valueLabel`,
   `cursorText(x, y, v)`, and `outlines` (a list of `[x0, x1, y0, y1]`,
   drawn dashed). It draws the raster on the canvas, the axes with
   `niceTicks`, a color legend, a crosshair with a tooltip, arrow keys that
   move the cursor by one grid step, and the colors of the current theme
   (again after a theme change, as vb-pulseq does). It returns `{setData}`,
   which replaces the axes and values without a new chart. No zoom.
3. **CSS** in `report.css`: class selectors only (`.map-chart` and its
   children). No id selectors.
4. **`page.py`**: `map_chart.js` after `lane_chart.js`.
5. **`docs/usage.md`**: the `PulseqReport.mapChart` options.

### 4.5 The RF profile card (phase 5)

```python
def rf_profile_card(
    seqs: Sequence[NamedSequence],
    *,
    diagram_card_id: str = "diagram",
    views: Sequence[str] = ("profile",),    # add "z_df" and "2d"
    plane: tuple[str, str] | None = None,   # the 2d view
    extent_m: float | None = None,          # the 2d view
    card_id: str = "rf-profile",
) -> Card
```

1. **The builder.** It calls `refuse_rotations` for each file. `seqs` must be
   the list of the diagram card `diagram_card_id`, in the same order: the
   card data has the file names, and the card script shows a note when a
   message names a file that the card does not have. `views` without
   `"profile"`, or with an unknown name: `ValueError`. For a file where
   `rf_uses_labeled` is False, the data of that file is only its name and
   the count of RF events without a label, and the card shows, for that
   file (decision 22):

   > This file has RF pulses without a use label (N of M RF events). The RF
   > profile card needs a use label on each RF pulse: set `use=` in the
   > pypulseq `make_*_pulse` functions. A `.seq` file older than format 1.5
   > has no labels: read it with `detect_rf_use=True` for labels that pypulseq
   > guesses from the flip angle, or set them by hand; see `docs/usage.md`.
2. **The data.** For each file:
   - `name`, W (`SliceThickness`, m, or null), FOV (the `FOV` definition, m,
     or null), `B0` and `abs(gamma)`.
   - The RF table (`diagram_data.encode_tables`), one row for each dense RF
     index of `SequenceIndex`: `delay`, `dt`, `shape_at` and `shape_n` (in
     the shape pool), `use` (an index into the list of uses), `freq_hz` and
     `phase_rad` (the totals), and the pool `shape_re`, `shape_im` (the
     baseband samples of `hold_samples`, each shape stored one time). The
     GRE example has 24 RF events and one shape: about 48 KB before
     compression.
   - The pulse list (`pulse_list`): for each distinct pulse (the RF event
     without its offsets, and the gradient events during the RF, section
     2.3, item 2): the first block, the number of blocks, the use, the
     gradient kind, the flip angle, the peak B1 and the energy.
   - The options: `views`, `plane`, `extent_m`, `diagram_card_id`.
3. **Which period** (decision 20). The card subscribes to `sequence`,
   `cursor`, `anchor` and `view` of the diagram `diagram_card_id`.
   - With an anchor, the card shows the period at the anchor. Without one,
     it follows the cursor. When the cursor leaves the plot, it keeps the
     last period.
   - The card changes its content only when the period changes. A move of
     the cursor inside a TR changes nothing.
4. **The body.**
   - A status line (`aria-live="polite"`): the file, the blocks and the time
     of the period, and the number of distinct pulses; or what to do ("move
     the cursor over the sequence diagram").
   - A table with one row for each distinct pulse of the period: use,
     count, gradient, flip angle, peak B1, energy, W, slice centre, FWHM,
     edge 10–90 %, passband ripple, stopband level, rephasing error,
     non-linear residual, centre phase and notes.
   - For each distinct pulse, in the order of the table: a heading ("Pulse
     2: refocusing, Gz, ×16"), the lane chart of its 1D profile (with bands
     at `c ± W / 2`), and a map for each view that the caller switched on,
     or its reason.
   - The combined profile (section 4.3, item 7), when the period has one: a
     heading ("First echo: combined profile"), the note of section 4.3, item
     7, its numbers, its 1D lane chart (one lane for each pulse that takes
     part, and one lane for the product, on one axis), and its maps when the
     caller switched on `2d`. When the period has none, one line with the
     reason, except for a period without a refocusing pulse (no line).
   - The pulse list, one table for each file, with a "Show" button in each
     row that publishes `goto`.
5. **The work.** `RfProfiles` (phase 3) computes the period, the pulses, the
   specs and the profiles. The 1D profiles are computed at once, in the order
   of the table. Maps are computed after them, in slices of at most 20 ms,
   with `setTimeout` between them, and a progress text. A new period stops
   the work for the previous one. The cache keeps the profiles of the last
   64 pulse keys. The echo pathway belongs to the block, not to the key: the
   card computes it for the last block of each distinct excitation of the
   period (a walk of a few blocks).
6. **The card script** (`assets/cards/rf-profile.js`) uses `laneChart`,
   `PulseqReport.mapChart` and `PulseqReport.decodeTable`. Its element ids
   start with the card id.

### 4.6 The JavaScript of the reference (phase 3)

`assets/rf_profiles.js`: the global `RfProfiles` (and `module.exports` in
Node), pure functions only:

1. `spinDomain(...)`: the rotation of section 4.2, item 1, on typed arrays,
   one point at a time over all samples (section 2.3: about 11 ns for each
   point and sample).
2. `blockPulse(view, rfTable, block)` and `period(view, rfTable, block)`:
   section 4.2, items 2 to 8, from the sequence view of section 4.1 and the
   RF table of section 4.5.
3. `viewSpec`, `quantity`, `echoPhase`, `widths`, `combinedProfile`:
   sections 4.2 and 4.3.
4. `simulation(pulse, spec)`: an object with `step(budgetMs)` (it computes
   points until the budget ends; it returns the fraction done) and `result()`.
   The card calls `step` in its slices. A z × Δf spec with a constant
   gradient is one 1D simulation.

### 4.7 What vb-pulseq can do after this plan (not in this plan)

1. Use the diagram card and `rf_profile_card` (with `views=("profile",
   "2d")`) instead of its pulse profiles card and its column cross-section
   card: the combined map of a vb-pulseq period is the column cross-section.
2. Delete its `rf_sim.py`, `rf_profiles.py`, `profile_metrics.py` and
   `column.py`, or keep its column card and draw it with
   `PulseqReport.mapChart` and a W × W outline.

## 5. Phases

---

### Phase 0: TESTS.md skeleton

Branch: `docs/rf-profiles-tests-skeleton`. Tier: H. Review: O.

**Task 0.1.** At the end of `TESTS.md`, add these placeholder sections. Each
has its heading and the line "Phase N of `docs/plans/rf-profiles.md` adds the
entries.":

```
### 2.28 Messages between cards (`test_messages.js`)
### 2.29 RF simulation (`test_rf_sim.py`)
### 2.30 Profile metrics (`test_profile_metrics.py`)
### 2.31 RF pulse of a block (`test_rf_profiles.py`)
### 2.32 RF profiles in JavaScript (`test_rf_profiles.js`)
### 2.33 RF profiles against Python (`test_rf_profiles_golden.py`)
### 2.34 RF profile card (`test_rf_profile_card.py`)
```

---

### Phase 1: messages between cards

Branch: `feature/card-messages`. Tier: S. Review: O. After phase 0.

**Task 1.1: The interface.** Tier S. Section 4.1, items 1 to 5, in
`lane_chart.js`. Node tests in `tests/js/test_messages.js`: replay, the order
of the handlers, a handler that throws, a publish inside a handler, the
frozen message, and unsubscribe. The functions must work in Node without a
DOM: put them in a part of `lane_chart.js` that Node can load, or test them
through a small pure factory that `lane_chart.js` calls. Task 1.1 decides
which (tier O) and writes it in the PR.

**Task 1.2: The sequence view.** Tier S. `SeqLanes.sequenceView` (section
4.1). Node tests in `tests/js/test_seq_lanes.js` on hand-made tables:
`blockAt`, `blockStart`, `events`, `gradEvent`, `adcEvent` and
`gradHzPerValue` against the tables.

**Task 1.3: The charts and the diagram.** Tier S. Section 4.1, "Changes in the
charts". Review O line by line: without the new options, `laneChart` must
work as now for the other cards.

**Task 1.4: Documents.** Tier S. `docs/usage.md`: a new section "Messages
between cards": the interface, the topics, the messages, the sequence view,
and the rule of decision 11.

**Task 1.5: Browser check.** Tier O. Use the
`dev-workflow:browser-check-localhost` skill. A scratch page with the
diagram card and a project card (`Card` and `extra_scripts`) that subscribes
to all four topics and shows each message. Check the cursor, the anchor
(click, arrow keys, reset), the view, a change of file, `goto` from a button
of the project card, both themes, and that there is no console error. The
diagram must look and work as before.

Acceptance: `scripts/check` passes. The browser check passes.

---

### Phase 2: the Python reference

Branch: `feature/rf-profiles-python`. Tier: O for the interface, S for the
code. After phase 0.

**Task 2.1: The interface.** Tier O. Write the dataclasses (`BlockPulse`,
`Period`, `ProfileAxis`, `ProfileSpec`, `Profile`, `CombinedProfile`,
`PulseSummary`) and the signatures of sections 4.2 and 4.3 with their
docstrings, and fix them.

**Task 2.2: `rf_sim.py` and `profile_metrics.py`.** Tier S (the simulator from
vb-pulseq `rf_sim.py`), H (`profile_metrics.py` and
`tests/test_profile_metrics.py`: copies of the vb-pulseq files, with new
imports only).

**Task 2.3: The oracle.** Tier S. `tests/oracles/rf_sim.py`: the
magnetization vector of each point, rotated in each hold interval by the 3 × 3
matrix (Rodrigues' formula) about the field `(Re b1, Im b1, off-resonance)`.
No spin-domain parameters. It returns `mxy` and `mz`, to compare with
`magnetization(*spin_domain(...))`. Read the vb-pulseq test
`test_hard_pulse_with_gradient_matches_rodrigues_rotation` for the sign of
each component.

**Task 2.4: `rf_profiles.py`.** Tier S. Sections 4.2 and 4.3.

**Task 2.5: Tests.** Tier S.

`tests/test_rf_sim.py`:

1. The six vb-pulseq tests of `tests/tools/test_rf_sim.py`, with the new
   signatures.
2. The oracle (section 3.5, item 1): random complex RF (at least 200
   samples), a gradient on 3 axes that changes in each interval, random
   points with random `df` and `b1_scale`.
3. Rotation: a gradient `(Gx, Gy, 0)` and points along it give the 1D result
   of the gradient magnitude and the distance along it (1e-12).
4. `df` is a shift: with a constant gradient `G`, the point at `u` with `df`
   equals the point at `u + df / G` with `df = 0` (1e-12).
5. `b1_scale`: a hard pulse with `b1_scale = s` gives `s` times the flip
   angle (1e-12).

`tests/test_rf_profiles.py` (build each sequence in the test with pypulseq):

1. The gradient kinds: a block pulse (`none`); a trapezoid on z (`one`,
   select coordinate `z`, as vb-pulseq); the same trapezoid on x and y with
   one timing (`one`, `select`, `u` = the unit vector); an arbitrary gradient
   on x and y that turns (`changing`, no `profile` view, the reason).
2. Interval values: for a trapezoid, the values of a ramp interval, an
   interval with a corner, and a flat interval equal the means computed by
   hand (1e-12). A pulse longer than the flat top: not constant.
3. As played: a block with the total frequency offset `f` and a constant
   gradient `G`. Its profile is the profile of the same block without the
   offset, moved by `f / G`, within the error of the hold model: the
   modulation is sampled at the interval centres, so the difference is of
   second order in `dt` (measured in phase 2: 1.4e-4 at a 5 µs raster and
   800 Hz). The test checks a bound of 1e-3, and that the difference falls
   when `dt` halves. (Corrected on 2026-09-28: the first text had 1e-9.) The
   `freq_ppm` of an RF event adds `freq_ppm * 1e-6 * abs(gamma) * B0`.
4. The pulse key: an MPRAGE-like block with a phase-encode gradient after the
   RF has the key of a block with the RF alone; blocks of an RF-spoiled GRE
   (a new phase offset in each TR) have one key; blocks with different
   frequency offsets have different keys.
5. The echo pathway: a GRE (the rephaser in the next block); a spin echo with
   crushers around the refocusing pulse (the pathway moment of a correct
   sequence is 0 within 1e-9 of the moment it cancels); a dummy block with
   no ADC before the next excitation (None, and the reason); a TSE-like
   block where the rephaser and the crusher are one gradient (the echo rule
   gives 0, the vb-pulseq rule does not); a saturation pulse between an
   excitation and its ADC (None, and the reason).
6. The period: a GRE (one TR); a spin echo (the excitation and the
   refocusing pulse); a TSE-like train (one period, the refocusing pulse with
   its count); a fat saturation before an excitation (in the period of that
   excitation); dummy scans without an ADC (in the period of the first ADC,
   with their count); a block before the first RF (the first period); the
   period of each block of a period is the same period; a walk longer than
   `PERIOD_MAX_BLOCKS` (the flag `truncated`; set the constant low for this
   test only).
7. The labels: `rf_uses_labeled` is True for the test sequences and False
   for a sequence with one `undefined` pulse; `block_pulse` and `period`
   raise `ValueError` for it.
8. The combined profile:
   - one direction: a spin echo with the refocusing pulse 1.5 times as wide
     as the excitation on the same axis; the combined profile equals the
     product of the two `profile` views at the same points (exact), and the
     signal kept is below 1;
   - two logical directions (excitation on z, refocusing on y): the map
     equals the outer product (exact), and the numbers equal the definitions
     of section 4.3, item 7, computed by hand in the test on the same grids
     (1e-12);
   - three directions (PRESS-like: excitation on x, refocusing on y and z):
     the three central sections;
   - an oblique direction: each pulse at the projection of each grid point
     (1e-12 against a direct `simulate` at those points);
   - a non-selective refocusing pulse (kind `none`): a constant factor;
   - no combined profile, with the reason, for: a GRE, no ADC in the period,
     a pulse of kind `changing`, an `inversion` pulse between the excitation
     and the ADC; a fat saturation before the excitation does not take part.
9. The views: `profile` for each kind (with W, without W, `none`,
   `changing`); `z_df` equals, on each grid line, the 1D profile with the
   other value in `at` (exact); `z_df` with a constant gradient equals the
   full grid (1e-12); `2d` with `plane` and `extent_m`, with the `FOV`
   definition, and with neither (None and the reason); `2d` for kind `one`
   (None).
10. The quantities and the widths for each use of the table in section 4.3,
    item 2. The rephasing error with a rephaser of 1.5 times the correct
    moment, minus the error with the correct moment, equals
    `0.5 * 2π * (the moment) * W` within 1e-6 (the linear fit). (The
    difference, because a 90° sinc has its own phase error of about 1 rad
    with the correct rephaser.)
11. Spec errors: one test for each rule of the specs.
12. `pulse_list`: RF spoiling and slices give one entry; the MPRAGE-like case
    gives one entry.
13. Rotations: `NotImplementedError`, as `tests/test_extensions.py` makes a
    sequence with rotations.
14. Another nucleus: the peak B1 of a block pulse made with
    `pp.Opts(gamma=11.262e6)` equals its B1 in µT (1e-9).

`TESTS.md` sections 2.29, 2.30 and 2.31.

**Task 2.6: Measure.** Tier S. The time of `block_pulse` and of each view for
the example GRE and a vb-pulseq-like spin echo, and the time and the added RSS
of `pulse_list` at 10^6 repeating blocks (`scripts/diagram_scale.py`).

Acceptance: `scripts/check` passes.

---

### Phase 2b: external references

Branch: `feature/rf-references`. Tier: O for the cases and the tolerances, S
for the script and the tests. After phase 2. Decision 5 and section 3.5,
item 4.

**Task 2b.1: The reference script.** Tier S, with O review.
`scripts/rf_references.py` writes the fixtures of task 2b.2. It is not part
of `scripts/check` or CI (as `scripts/cards_scale.py`), and it records, in
each fixture, the tool, its version or commit, the command and the inputs.
It needs these tools only when it runs; none of them is a dependency of
this project:

1. **MATLAB Pulseq's `mr.simRf`** in GNU Octave (`nix shell --inputs-from .
   nixpkgs#octave`), with MATLAB Pulseq (`github.com/pulseq/pulseq`) cloned
   at a pinned commit into the session scratchpad; the script takes its
   path. For each case, pypulseq writes the sequence to a `.seq` file,
   MATLAB Pulseq reads it (`mr.Sequence`, `read`, `getBlock`), and
   `mr.simRf(rf)` gives the frequency axis `F`, `Mz_z` and `Mz_xy` of the
   pulse as played. `mr.simRf` has no gradient: a slice-selective pulse is
   compared on its frequency axis (section 2.3, "z × Δf with a constant
   gradient is a 1D simulation"). \|β\|² is `(1 - Mz_z) / 2` for a
   rotation.
2. **sigpy's `abrm_nd`** (sigpy 0.1.27, BSD-3, in a scratch environment:
   `uv run --no-project --with sigpy==0.1.27`, never in the project
   environment), for the cases with a gradient that changes during the RF,
   an oblique gradient, and positions in 2D: `a` and `b` on the spatial grid
   from the same hold samples and interval gradients.
3. **sigpy's SLR design** (`sigpy.mri.rf.slr.dzrf`) for the SLR case: the
   pulse and its design parameters (time-bandwidth product, passband and
   stopband ripples, pulse type).

**Task 2b.2: The fixtures.** Tier S. `tests/fixtures/rf_references/`, one
small JSON file for each case (at most 200 KB each), with the provenance,
the inputs (RF samples, `dt`, gradients, grid) and the reference outputs.
The cases:

1. A pypulseq sinc excitation, 90°, time-bandwidth product 4, 3 ms, with a
   slice-select gradient (MATLAB Pulseq and sigpy).
2. A pypulseq sinc refocusing pulse, 180° (MATLAB Pulseq: \|β\|²).
3. A block pulse, 20°, 100 µs (MATLAB Pulseq: the spectral profile).
4. A sinc excitation with a frequency offset and a phase offset (MATLAB
   Pulseq: the pulse as played).
5. A Gaussian fat saturation pulse at −3.45 ppm (MATLAB Pulseq).
6. A hyperbolic secant adiabatic inversion (`pp.make_adiabatic_pulse`,
   "hypsec") (MATLAB Pulseq; the analytic band of task 2b.3).
7. An SLR 90° excitation (sigpy design; MATLAB Pulseq profile).
8. A sinc excitation on the ramps of its gradient, and one on an oblique
   gradient (sigpy).
9. A pulse with a gradient that turns on x and y (a short spiral) on an x-y
   grid (sigpy).

**Task 2b.3: The tests.** Tier S, O for the tolerances.
`tests/test_rf_references.py` computes each case with the reference
functions of phase 2 and compares:

1. With MATLAB Pulseq: \|Mxy\| and Mz on its frequency axis. First measure
   the difference; it comes from the resampling of `mr.simRf` (it
   interpolates the RF linearly to a step of 1 to 10 µs). Set each tolerance
   from that measurement and write the reason in the test (section 3.5,
   item 4).
2. With sigpy `abrm_nd`: `a` and `b` within 1e-10 (the same rotation, with
   another order of float operations).
3. SLR: the passband ripple and the stopband level of the simulated profile
   are within the design ripples.
4. Hyperbolic secant: Mz is at most −0.9 across the inversion band of the
   analytic formula of this pulse type (write the formula and its source in
   the test), for the pulse's B1 above its adiabatic threshold.

`TESTS.md`: a new section at the end, "2.35 RF profiles against external
references (`test_rf_references.py`)".

**Task 2b.4: Results.** Tier O. The measured differences and the chosen
tolerances go into section 8 of this plan (phase 6). A difference that the
resampling does not explain is a finding: stop and tell the user.

Acceptance: `scripts/check` passes with the fixtures. CI needs neither
Octave nor sigpy.

---

### Phase 3: the reference in JavaScript

Branch: `feature/rf-profiles-js`. Tier: S. Review: O (the inner loop line by
line). After phases 2 and 4.

**Task 3.1: `assets/rf_profiles.js`.** Tier S. Section 4.6.

**Task 3.2: Page order.** Tier H. `page.py`: `rf_profiles.js` after
`map_chart.js`. Update `test_script_order` and its `TESTS.md` entry.

**Task 3.3: Node tests.** Tier S. `tests/js/test_rf_profiles.js` on hand-made
tables: the spin-domain rotation for a hard pulse (the flip angle), the
interval values of a trapezoid, the gradient kinds, the views, the echo
pathway, the period rule (the cases of task 2.5, item 6), the combined
profile of one and two logical directions, `step` with small budgets gives
the same result as one large budget (exact), and the constant-gradient
z × Δf. `TESTS.md` section 2.32.

**Task 3.4: The golden test.** Tier O for the design, S for the code.
`tests/test_rf_profiles_golden.py` with `tests/js/golden_rf_profiles.js`, as
the golden tests of the diagram and the PNS lane do. For each period of the
phase 2 test sequences and the two vb-pulseq-like sequences, and each view:
Python writes the diagram tables, the RF table and the reference values (the
period, each pulse, each profile, the widths and the combined profile); Node
computes the same with `RfProfiles`. Section 3.5, item 2. `TESTS.md` section
2.33.

**Task 3.5: Measure.** Tier S. The times of section 2.4 (browser part) in
Node for the pulses of section 2.3.

Acceptance: `scripts/check` passes, with the golden test.

---

### Phase 4: the map chart

Branch: `feature/map-chart`. Tier: S. Review: O. After phase 0.

**Task 4.1: Pure functions.** Tier S. Section 4.4, item 1. Node tests in
`tests/js/test_chart_math.js`. `TESTS.md` section 2.4: an entry for each new
test.

**Task 4.2: `assets/map_chart.js`.** Tier S. Section 4.4, items 2 and 4.
Update `test_script_order` and its `TESTS.md` entry.

**Task 4.3: CSS and documents.** Tier S. Section 4.4, items 3 and 5.

**Task 4.4: Browser check.** Tier O. A scratch page with a project card that
draws a known map: a Gaussian on one axis times a ramp on the other, on a
non-square grid (for example 180 × 120), sequential and diverging, with an
outline, and `setData`. Check the axes, the legend, the tooltip values, the
arrow keys, both themes, a theme change, and that there is no console error.

Acceptance: `scripts/check` passes. The browser check passes.

---

### Phase 5: the RF profile card

Branch: `feature/rf-profile-card`. Tier: S. Review and browser check: O.
After phases 1, 3 and 4.

**Task 5.1: `cards/rf_profile.py`.** Tier S. Section 4.5, items 1 and 2.

**Task 5.2: `assets/cards/rf-profile.js`.** Tier S. Section 4.5, items 3 to 6.

**Task 5.3: Tests.** Tier S. `tests/test_rf_profile_card.py`:

1. The data of section 4.5, item 2: the RF table decodes
   (`diagram_data.decode_tables`) to the baseband samples and the totals of
   each RF event; one shape for the 24 RF events of an RF-spoiled GRE.
2. The pulse list of a sequence with an excitation and a refocusing pulse, a
   block pulse, and a turning gradient.
3. The options: `views` with `z_df` and `2d`, `plane`, `extent_m`; the
   `ValueError` cases.
4. Rotations: `NotImplementedError`.
5. Two cards on one page (different `card_id` and `diagram_card_id`): no id
   is used twice.
6. Labels (decision 22): a report with a labeled file and a file with
   `undefined` pulses. The labeled file has its data. The other file has only
   its name and the counts, and the card HTML has the note of section 4.5,
   item 1, with those counts. No exception.
7. The card HTML has the note of section 4.3, item 7 (the primary echo
   pathway) in the element that the card script fills with the combined
   profile, word for word. Compare with one constant, which the card script
   and `docs/usage.md` also use, so that the three stay the same.

`TESTS.md` section 2.34.

**Task 5.4: Documents and the example.** Tier S.

1. `docs/usage.md`: the card in the builder table of section 5, in the
   example of section 2, and a new subsection with the options (`views`,
   `plane`, `extent_m`), the rule that the card follows one diagram card, the
   period rule, the combined profile with the note of section 4.3, item 7,
   and the labels: `rf_uses_labeled`, `Sequence.read(...,
   detect_rf_use=True)` for guessed labels of a file older than format 1.5
   (section 2.3, pypulseq fact 6), and the pypulseq `use="other"` problem
   (fact 7).
2. `examples/gre_report.py`: add the card, with `views=("profile", "z_df")`.
   Rebuild `docs/examples/gre.html`.
3. `README.md`: a row for the card in the table of "The cards".

**Task 5.5: Browser check.** Tier O. Pages: the example GRE; a vb-pulseq
sequence with `views=("profile", "2d")` (scratch page); the TSE, EPI-SE with
fat saturation and MPRAGE examples of pypulseq (scratch pages); a PRESS-like
sequence (excitation and two refocusing pulses on three axes, built in a
scratch script) with `2d`; a sequence with a turning gradient and
`views=("profile", "2d")`; a report with one unlabeled file; the ex-vivo file
`data/exvivo_gre_seg_0.seq` (a hard pulse: a `df` profile). The scratch pages
stay in the scratchpad. Never commit them. Check:

1. The card follows the period of the cursor, and a move inside a TR
   changes nothing. A click anywhere in a TR pins it, and a reset releases
   it.
2. Each distinct pulse of the period, with its count (TSE: the refocusing
   pulse ×16; the fat saturation in its excitation's period).
3. A period of dummy scans says "no ADC before the next excitation" where it
   applies.
4. The combined profile: the vb-pulseq map looks like the vb-pulseq column
   cross-section; the PRESS-like sections; the note of section 4.3, item 7,
   is visible above each combined profile; a GRE has no combined profile and
   no line.
5. The z × Δf map of the GRE comes at once. A full map shows its progress,
   and a move to another period stops it.
6. "Show" in the pulse list moves the diagram and the card.
7. The unlabeled file shows its note, and the labeled file of the same
   report works.
8. The tooltips, both themes, and that there is no console error.

**Task 5.6: Measure.** Tier S. The budgets of section 2.4 for a
vb-pulseq-like spin echo, the example GRE and the ex-vivo file, in the
browser (the performance panel or `performance.now` in a scratch page).

Acceptance: `scripts/check` passes. The budgets pass. The browser check
passes.

---

### Phase 6: scale check and documents

Branch: `chore/rf-profile-scale`. Tier: O, with H for the documents.

**Task 6.1.** Add the card name `rf-profile` to `scripts/cards_scale.py`.
Measure 10^6 and 10^7 repeating blocks and 10^5 worst-case blocks: the Python
budgets of section 2.4. The repeating TR of `scripts/diagram_scale.py` has an
RF block pulse (kind `none`). A browser check of the 10^7-block page with the
diagram and this card: the cursor and the anchor work, and the budgets of the
browser pass.

**Task 6.2.** `docs/usage.md`: the card in the scale table, and the external
references of phase 2b in the card's subsection. This plan: status
"complete", the PR numbers, the decisions made during the work, and the
results in section 8 (with the measured differences and tolerances of task
2b.4). `docs/plans/pulseq-reports.md`: the two notes of phase
6 in section 3.4. `TODO.md`: an item for relaxation during the pulse only if
the user asks for it.

**Task 6.3.** Tell the user that the plan is complete, and ask when to make
the release candidate `0.2.0rc2` (decision 19). Do not bump the version or
make a tag without the user's approval.

## 6. Summary of parallel work

| Wave | Phases | Condition to start |
|---|---|---|
| 1 | 0 | This plan is merged. |
| 2 | 1, 2, 4 | Phase 0 merged. |
| 3 | 3, 2b | Phase 3: phases 2 and 4 merged. Phase 2b: phase 2 merged. |
| 4 | 5 | Phases 1, 3 and 4 merged. |
| 5 | 6 | Phases 5 and 2b merged. |

Workers inside a phase:

| Phase | Parallel workers |
|---|---|
| 1 | The executing agent decides the form of task 1.1. Then one S worker for tasks 1.1 and 1.2, and one S worker for task 1.3, at the same time. Task 1.4 after both. |
| 2 | The executing agent does task 2.1. Then one S worker for task 2.2 (simulator) and task 2.3, one H worker for task 2.2 (metrics), and one S worker for task 2.4, at the same time. Task 2.5 after them. One S worker for task 2.6. |
| 2b | The executing agent chooses the pinned MATLAB Pulseq commit and runs task 2b.1's tools. One S worker for tasks 2b.1 and 2b.2, then one S worker for task 2b.3; the executing agent sets the tolerances and does task 2b.4. |
| 3 | One S worker for tasks 3.1 and 3.3, and one H worker for task 3.2, at the same time. The executing agent designs task 3.4 and gives the code to an S worker. |
| 4 | One S worker for tasks 4.1 and 4.2, and one S worker for task 4.3, at the same time. |
| 5 | One S worker for tasks 5.1 and 5.3, and one S worker for task 5.2, at the same time. Task 5.4 after both. |
| 6 | The executing agent. One H worker for the documents with the exact text. |

## 7. Questions still open

No question is open. The questions of the first version (PR #51) became
decisions 8 to 12. The questions of this version were answered on 2026-09-28:

1. **The topics and the messages** (section 4.1). Answered: all five now
   (decision 13).
2. **Hover and anchor** (section 4.5, item 3). Answered: the cursor selects,
   the anchor pins (decision 14).
3. **The pulse list** (section 4.5, item 4). Answered: yes, with "Show"
   buttons (decision 15).
4. **The Python reference and the golden test** (sections 4.2 and 4.6).
   Answered: yes (decision 16).
5. **`MAX_POINTS`, the 2D grid and the budgets.** Answered: as proposed
   (decision 17).
6. **vb-pulseq.** Answered: vb-pulseq decides later, in its own plan
   (decision 18).
7. **The release.** Answered: part of 0.2.0 (decision 19).
8. **What the cursor selects in a TR, off a pulse.** Answered: the period
   (decision 20).
9. **The combined effect of the pulses of a TR.** Answered: yes, the primary
   echo pathway of the first echo, with a clear note (decision 21).
10. **Files without RF use labels.** Answered: a note in the card, and the
    helper `rf_uses_labeled` (decision 22).
11. **Parity with vb-pulseq.** Answered: dropped; external references
    instead (decision 5, phase 2b).

## 8. Results

Phase 6 writes this section.
