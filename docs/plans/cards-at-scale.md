# Plan: the PNS, RF exposure, gradient limits and gradient spectrum cards at 10^7 blocks

Mode: Strict STE100. Structural rules are enforced. Lexical rules are a
direction of travel, not a verified dictionary match.

Status: not started. The plan was written on 2026-09-23.

## 1. Goal

Make four cards work for each `.seq` file of up to 10^7 blocks:

1. PNS prediction (`cards/pns.py`, `pns.py`).
2. RF exposure (`cards/rf_exposure.py`, `rf_exposure.py`).
3. Gradient limits (`cards/gradient_limits.py`, `grad_limits.py`).
4. Gradient spectrum (`cards/spectrum.py`, `grad_spectrum.py`).

"Work" means that each card meets the budgets of section 2.6. The values that
each card shows do not change, except by float rounding inside the tolerance
of section 3.5.

The PNS card is the most urgent part. It is too slow for real files now,
at 4 × 10^4 blocks (section 2.2). Phase 1 fixes this first, before the other
work.

The slow PNS code is in pypulseq, not in this library. This plan changes it in
a fork of pypulseq, `mdtisdall/pypulseq`, and measures the benefit. It does not
copy the pypulseq code into this library. After the measurements, the user
decides whether to offer each fork change to the pypulseq maintainers.

The PNS chart moves into the sequence diagram as lanes, and PNS at 10^7
blocks is solved there: see `docs/plans/diagram-lanes.md`. This plan keeps
only phase 1 of the PNS work: the fast filter, which makes the current PNS
card usable for real files now.

After this plan, the user can tag `v0.2.0` (phase 7).

## 2. Read this first (context for the executing agent)

### 2.1 The state of the repository

- Repository: `~/dev/pulseq-reports`, GitHub `mdtisdall/pulseq-reports`
  (public). The default branch is `main`. `v0.1.0` is tagged on `9499351`.
- Read `docs/plans/pulseq-reports.md` (the first plan) and
  `docs/plans/diagram-event-table.md` (the second plan). Their workflow rules
  apply to this plan too, except where this plan changes them.
- The diagram card already works at 10^7 blocks. It uses the block and event
  tables of `diagram_data.py`: each unique event is expanded one time.
- `TODO.md` has the item "Make the other cards work at 10^7 blocks". This plan
  is that item. Phase 7 deletes the item.
- `scripts/diagram_scale.py` builds large synthetic sequences:
  `build_repeating(n_trs)` and `build_worst(n_trs)`, with 5 blocks in each TR.
  At 10^7 blocks, the repeating case is 11,980 s (3.3 h) long.
- The dependency is pypulseq 1.5.0.post1 from PyPI. The upstream repository is
  `pulseq/pypulseq` on GitHub. On 2026-09-23, upstream `master` had the same
  `safe_tau_lowpass` as 1.5.0.post1. A search of the upstream issues found none
  about the speed of PNS. That search was not complete.
- The fork `mdtisdall/pypulseq` does not exist yet. The user makes it with the
  GitHub Fork button, because the token of this project can see only
  `pulseq-reports` (task 1.1).

### 2.2 Measurements (2026-09-23, a Mac with 10 cores and 64 GB)

A separate agent used the library on a real protocol file (39,304 blocks,
370 s). It is file 0 of the ex-vivo GRE protocol (question 3 of
section 7). The PNS calculation ran for more than 3 minutes. It used 5.3 GB of
memory, and it did not finish.

The research for this plan measured each card in a fresh process. "Repeating"
and "worst" are the builders of `scripts/diagram_scale.py`. Peak RSS includes
the sequence itself.

PNS (`pns_card`, repeating case, 10 µs gradient raster):

| Sequence duration | Blocks | Time | Peak RSS |
|---|---|---|---|
| 12 s | 10,000 | 9.2 s | 0.51 GB |
| 60 s | 50,085 | 42.7 s | 1.53 GB |
| 120 s | 100,000 | 85.1 s | 2.72 GB |
| 370 s (extrapolated) | | about 263 s | about 7.5 GB |
| 11,980 s = 10^7 blocks (extrapolated) | | about 2.3 h | about 240 GB |

RF exposure (`rf_exposure_card`):

| Case | Blocks | Time | Peak RSS |
|---|---|---|---|
| repeating | 10^5 | 2.2 s | 2.20 GB |
| worst | 10^5 | 3.8 s | 4.80 GB |
| repeating | 10^7 (extrapolated) | about 220 s | about 207 GB |

Gradient limits (`gradient_limits_card`, no window):

| Case | Blocks | Time | Peak RSS |
|---|---|---|---|
| repeating | 10^6 | 22.4 s | 1.38 GB |
| worst | 10^5 | 3.3 s | 1.26 GB |
| repeating | 10^7 (extrapolated) | about 4 to 7 min | more than 8.6 GB |

Gradient spectrum (`spectrum_card`):

| Case | Blocks | Duration | Time | Peak RSS |
|---|---|---|---|---|
| repeating | 10^6 | 1,198 s | 22.3 s | 1.69 GB |
| worst | 10^5 | 140 s | 3.2 s | 1.45 GB |
| repeating | 10^7 (extrapolated) | 11,980 s | about 223 s | not known |

The spectrum takes about 67 s for each hour of sequence. Section 2.8 of the
second plan said "about 50 s". That value was not correct.

### 2.3 Where the time and the memory go

1. **PNS: the SAFE filters.** `pns_prediction` calls pypulseq
   `Sequence.calculate_pns`. That samples the three gradient axes over the
   whole file on the 10 µs raster, into one array. Then
   `safe_pns_prediction.safe_tau_lowpass` runs 9 low-pass filters (3 axes ×
   3 time constants). Each filter is a direct `np.convolve` with an
   exponential kernel of up to about 11,000 taps. In a profile of a 60 s
   file, `np.convolve` used 97% of the time. The large arrays (about 210 B
   for each sample) exist at the same time. The time and the memory grow
   with the duration, not with the number of blocks.
2. **RF exposure: samples of every pulse.** `_rf_samples` calls
   `seq.get_block` for every block. It expands every RF pulse to samples on
   the RF raster each time the pulse plays, also when it is the same event.
   A 1 ms block pulse gives 1000 samples. The 10 s window search tries every
   RF sample as a window start. The card for several files reads each file
   two times.
3. **Gradient limits: every block.** `grad_limits.py` calls `seq.get_block`
   for every block. With a `window`, the card makes two full passes.
4. **Gradient spectrum: every block, then every sample.**
   `seq.get_gradients()` calls `get_block` for every block (49% of the time
   at 10^5 blocks). The chunked spectrogram (38%) grows with the duration. It
   never keeps the whole sampled waveform.
5. **pypulseq keeps every block that `get_block` reads.** `pp.Sequence` has
   `use_block_cache=True` by default. `get_block` puts each block in
   `seq.block_cache`, and nothing removes it. A card that reads every block
   thus keeps all of them in memory. With the cache off, one gradient limits
   call added 33 KB instead of 86 MB of RSS (10^5 blocks).

### 2.4 Facts that the design uses

1. **The SAFE filter is a first-order recursive filter.**
   `safe_tau_lowpass` computes `alpha * convolve(x, (1 - alpha)^k)` with a
   kernel that it cuts where `(1 - alpha)^k` is below 1e-16. This is the
   recursion `y[i] = alpha * x[i] + (1 - alpha) * y[i - 1]`, with `y = 0`
   before the first sample. A recursion costs O(1) for each sample, and its
   state (one number) goes from one chunk to the next. The result differs
   from the convolution only by float rounding and the cut kernel.
2. **The SAFE model is causal.** Each output sample depends only on earlier
   samples. The padding that `safe_gwf_to_pns` adds at the end of the file
   does not change an earlier output. The padding at the start sets the
   filter state to zero.
3. **The three PNS axes combine only at the end**, as the root-sum-of-squares
   of each sample. Each axis can go through its filters on its own.
4. **RF exposure totals are sums over events.** The energy is the sum of
   `|B1|^2 × dt` over all samples. The peak is a maximum. The number of pulses
   is a count. Each of them comes from the unique events and the number of
   times that each event plays.
5. **The RF window maximum.** Each sample is a mass of energy at its start
   time. A window `[s, s + W)` holds the masses in it. The search tries each
   sample time as `s`. While `s` moves over the samples of one pulse, masses
   leave the window at its start. Masses come into the window only when
   `s + W` passes a sample time. Thus the window energy does not increase in a
   run of starts where no mass comes in. Only the first start of such a run
   can be the maximum.
6. **Gradient limits values are per event**, except the peak of |G|. The
   peak, the slew and the integral of g^2 of each axis come from each unique
   event. The RMS of the three-axis vector is `sqrt` of the sum of the axis
   mean squares, so it needs only the axis values. The peak of |G| needs the
   three events that play together in one block (a "triple").
7. **The spectrum windows are independent.** Each window uses only its own
   samples. The card combines windows by a maximum.
8. **The gradient waveform is a polyline.** pypulseq `get_gradients` makes a
   piecewise-linear `PPoly` from the corner points of each block. The tables
   of `diagram_data.py` hold the same corner points (`grad_offset`,
   `grad_value`), for each unique event one time.
9. **Parity with vb-pulseq.** `scripts/vb_parity.py` compares the data of the
   RF exposure, gradient spectrum and PNS cards with vb-pulseq. It also
   compares the HTML text of the RF exposure and PNS cards. The tolerance is
   a relative 1e-9 on each number. Many values in the data are rounded (for
   example to 2 decimals). A value that is very near a rounding boundary can
   round to a different number after a change of 1e-13. The gradient limits
   card has no vb-pulseq parity. It was new in the first plan.

### 2.5 Decisions that are already made

Do not open these decisions again. The user made them or approved them.

1. **Target: 10^7 blocks in each file**, as in the second plan. The budgets of
   section 2.6 are for one file.
2. **PNS first.** Phase 1 makes the PNS card fast enough for real files. It
   does not wait for the shared work of phase 2.
3. **Lean on pypulseq.** Do not test what pypulseq already asserts. Examples:
   the slew of an event, the gradient value at a block junction (`add_block`
   checks it), the decoding of events, and the SAFE model itself. Tests of
   pypulseq belong in pypulseq's own test suite, in the fork. The tests in
   this library compare its output with pypulseq output, or with the output
   of the current implementation.
4. **Change pypulseq in the fork, not in a copy.** When the slow or large part
   is pypulseq code, change it in the fork `mdtisdall/pypulseq`. Do not copy
   pypulseq code into this library. This library uses the fork through
   `[tool.uv.sources]` in `pyproject.toml` (section 3.6).
5. **Upstream later.** Measure each fork change first. With the measurements,
   the user decides whether to offer the change to upstream. The agent does
   not open an upstream issue or pull request.
6. **Slew as pypulseq defines it for its limit checks** (the user,
   2026-09-24). The gradient limits card reports the largest of:
   - The slope of each segment of each gradient event, as `make_trapezoid`,
     `make_extended_trapezoid` and `make_arbitrary_grad` compute it.
   - The step at each block junction divided by `grad_raster_time`, as
     `add_block` checks it. The step is `|last value of the block before −
     first value of the block after|`. Use 0 where a block has no event on
     the axis, and 0 before the first block.
   The junction steps are new. The current card does not report them.
   pypulseq checks a step only against `seq.system`. It checks every axis
   at every junction, with 0 for a block that has no event on the axis
   (`docs/notes/slew-definitions.md`, section 4). The card computes every
   junction and gives the percent of the caller's limits. The SAFE model uses
   a different slew (the raster difference `dgdt`). `TODO.md` has an item to
   study this difference. Until then, do not change either definition.
7. **No new dependency.** Use numpy and scipy. Both are already dependencies.
   The fork is the same dependency (pypulseq) from a different source.
8. **Keep the values.** Each card must give the same values as now, inside the
   tolerance of section 3.5. The card HTML and the JSON data keep their form.
9. **Do not read every block with `get_block`.** New code reads blocks through
   the tables (section 4.1). When code must call `get_block` for more than a
   few blocks, it turns the block cache off (section 4.2).
10. **The old implementations become test oracles.** Before a phase replaces a
    module of this library, it copies the module unchanged into
    `tests/oracles/`. The tests compare the new code with the oracle on small
    sequences.

### 2.6 Budgets (proposed: the user approves them with this plan)

"Added RSS" is the peak RSS during the card, minus the RSS after the sequence
is built. The pypulseq sequence of 10^7 repeating blocks uses about 3.8 GB by
itself (second plan, phase 5). "370 s file" is a synthetic repeating sequence
of 370 s with about 4 × 10^4 blocks, like the real file of section 2.2.

| Card | 370 s file: time | 370 s file: added RSS | 10^7 blocks: time | 10^7 blocks: added RSS |
|---|---|---|---|---|
| PNS | at most 30 s | at most 1 GB | see `docs/plans/diagram-lanes.md` | see `docs/plans/diagram-lanes.md` |
| RF exposure | at most 5 s | at most 0.5 GB | at most 120 s | at most 2 GB |
| Gradient limits | at most 5 s | at most 0.5 GB | at most 120 s | at most 2 GB |
| Gradient spectrum | at most 30 s | at most 1 GB | at most 300 s | at most 2 GB |

The worst case of `scripts/diagram_scale.py`: record the values at 10^5
blocks. Do not run it at 10^6 or 10^7 blocks. (The second plan used 10^5
blocks for the worst case, with the user's approval.)

The PNS time at 10^7 blocks has a larger budget, because the SAFE model must
filter every sample: 1.2 × 10^9 samples for each axis at 3.3 h.

If a budget fails, stop and tell the user. Do not change a budget yourself.

### 2.7 Terms

- **Index.** The `SequenceIndex` of phase 2: the block table of one sequence,
  in play order, with dense event indexes (section 4.1).
- **Unique event.** One row of a pypulseq event library that at least one
  block uses. The index numbers them from 1, for each kind (RF, gradient,
  ADC).
- **Oracle.** A copy of the current implementation of a module, kept in
  `tests/oracles/`, that the tests use as the reference.
- **Sampler.** The raster sampler of phase 2 (section 4.3).
- **Chunk.** A contiguous run of raster samples that the code processes at one
  time. Chunks keep the memory bounded.
- **Stock pypulseq.** pypulseq 1.5.0.post1 from PyPI, without a change.
- **Fork.** The repository `mdtisdall/pypulseq`, cloned to `~/dev/pypulseq`
  (question 5 of section 7).
- **Upstream.** The repository `pulseq/pypulseq`.
- **Worker.** A sub-agent that the executing agent starts with the Agent tool.

## 3. How to execute this plan

### 3.1 Workflow

Use the dev-workflow Claude Code plugin skills, as in the earlier plans.

1. Each phase is one branch, one worktree and one pull request in this
   project. Phase 1 also has work in the fork (section 3.6).
2. Start each phase with the `dev-workflow:start-task` skill, from the latest
   `origin/main`. The branch prefix is `feature/`, `fix/`, `docs/` or
   `chore/`.
3. Run `nix develop --command scripts/check` before each PR.
4. Open each PR with the `dev-workflow:ship` skill. Show the commit message to
   the user and wait for approval before `git commit`.
5. Merge only when the user tells you to. Use `dev-workflow:finish-task`.
6. Give work to workers with the `dev-workflow:parallel-agents` skill.
   Workers do not run git write commands. You review each diff.
7. The user wants at most three PRs open at one time.
8. `TESTS.md` must have one entry for each test. A PR that adds, removes or
   changes a test changes `TESTS.md`.
9. Each phase that changes a card runs `scripts/vb_parity.py` (see its
   docstring and the vb-pulseq notes of the earlier plans) and puts the
   output in the PR.

### 3.2 Worker model tiers

| Tier | Model | Use it when |
|---|---|---|
| H | `haiku` | The task is a mechanical copy, rename or removal with an exact file list. It needs no design decision. |
| S | `sonnet` | The task writes code or tests from a full specification in this plan. It needs local decisions only. |
| O | the executing Opus agent, not a worker | The task sets an interface, needs judgment about exactness or performance, or reviews other work. |

Rules for workers:

1. Give each worker the full paths of the files that it owns, the files that
   it may read, and the files that it must not edit.
2. Give each worker the exactness rule (section 3.5) and the pypulseq rule
   (decision 3 of section 2.5).
3. A tier H or S worker that finds a design problem stops and reports it.
4. Workers put scratch files in the session scratchpad directory, not in the
   worktree.
5. A worker that measures time or memory runs each size in a fresh process.
   It stops a run at 5 minutes or at 8 GB of RSS.

### 3.3 Order and parallel work

```
Phase 1 (fork: lfilter, then pin and measure) ─────────────────────────────┐
Phase 0 (TESTS.md) ─► Phase 2 (index, cache, sampler, script) ─┬─► Phase 3 (RF exposure) ─────┤
                                                               ├─► Phase 4 (gradient limits) ─┼─► Phase 7
                                                               └─► Phase 5 (spectrum) ────────┘
```

Phases 3, 4 and 5 need phase 2 only. The former phase 6 (PNS in chunks)
moved to `docs/plans/diagram-lanes.md`, which starts after phases 1 and 2 are
merged.

- Phase 1 starts at once. It does not need phase 0 or phase 2. Its
  pulseq-reports part edits only the PNS files, `pyproject.toml`, `uv.lock`,
  `ACCEPTED["pns"]` of `scripts/vb_parity.py` and the PNS sections of
  `TESTS.md`.
- Phase 0 and phase 2 can run at the same time as phase 1.
- Phase 2 needs phase 0 (its `TESTS.md` placeholder sections).
- Phases 3, 4 and 5 start after phase 2 is merged. They edit different files
  and can run at the same time (three PRs).
- Phase 7 starts after phases 1, 3, 4 and 5 are merged.
- At most three PRs open at one time, together with the PRs of
  `docs/plans/diagram-lanes.md`: do phases 0, 1 and 2 first, then 3, 4 and 5,
  then 7. Work in the fork is not a PR of this project.

### 3.4 File ownership

Each file has one owner phase at a time. Package root: `src/pulseq_reports/`.
Tests: `tests/`.

| Phase | Files that the phase creates or edits |
|---|---|
| 0 | `TESTS.md` (only: add two placeholder sections, task 0.1) |
| 1 | In the fork: `src/pypulseq/utils/safe_pns_prediction.py` (only `safe_tau_lowpass`) and one test file in pypulseq's suite. In this project: `pyproject.toml` (only `[tool.uv.sources]`), `uv.lock`, `pns.py`, `tests/test_pns.py`, `scripts/vb_parity.py` (only `ACCEPTED["pns"]`), `TESTS.md` section 2.11 |
| 2 | `seq_index.py` (new), `sampling.py` (new), `diagram_data.py`, `tests/test_seq_index.py` (new), `tests/test_sampling.py` (new), `tests/test_diagram_data.py` (only if a test must change), `scripts/cards_scale.py` (new), `TESTS.md` sections 2.18, 2.22 and 2.23 |
| 3 | `rf_exposure.py`, `cards/rf_exposure.py`, `tests/oracles/rf_exposure.py` (new), `tests/test_rf_exposure.py`, `tests/test_rf_exposure_card.py`, `scripts/vb_parity.py` (only `ACCEPTED["rf exposure"]`), `TESTS.md` sections 2.7 and 2.8 |
| 4 | `grad_limits.py`, `cards/gradient_limits.py`, `tests/oracles/grad_limits.py` (new), `tests/test_grad_limits.py`, `tests/test_gradient_limits_card.py`, `TESTS.md` sections 2.13 and 2.14 |
| 5 | `grad_spectrum.py`, `cards/spectrum.py`, `tests/oracles/grad_spectrum.py` (new), `tests/test_grad_spectrum.py`, `tests/test_spectrum_card.py`, `scripts/vb_parity.py` (only `ACCEPTED["gradient spectrum"]`), `TESTS.md` sections 2.9 and 2.10 |
| 7 | `scripts/cards_scale.py`, `TODO.md`, `docs/usage.md`, this plan file (status and results only), `README.md` (only if a sentence is wrong) |

Rules:

1. A phase edits only its own files.
2. If a phase needs a change to a file of another open phase, stop. Tell the
   user.
3. `TESTS.md`: each phase edits only its own sections. An unchanged heading
   line separates each pair of sections, so git merges the edits without a
   conflict. If a rebase gives a conflict in `TESTS.md`, keep both sides.
4. `scripts/vb_parity.py` is in phases 1, 3 and 5, and in phase 4 of
   `docs/plans/diagram-lanes.md`. Each phase edits only its own keys of
   `ACCEPTED`, and only when the user accepts a difference (section 3.5).
   These phases can conflict there. Rebase each one that merges later.
   Phase 1 and phase 4 of `docs/plans/diagram-lanes.md` both own the key
   `"pns"`. They do not overlap, because that plan starts after phase 1 is
   merged.
5. `tests/oracles/` is new in phase 3, 4 or 5, whichever is first. Each of
   them adds only its own file. Add an empty `tests/oracles/__init__.py` only
   if the imports need it. The first phase adds it, and the others rebase.
6. `pyproject.toml`, `uv.lock`, `pns.py` and `tests/test_pns.py` are in phase
   1, and later in `docs/plans/diagram-lanes.md`, which starts after phase 1
   is merged. No other phase of this plan changes the dependencies.

### 3.5 The exactness and parity rule

1. Where the new code does the same float operations in the same order as the
   old code, the tests require exact equality (`==`, `numpy.array_equal`).
2. The order of the float operations can change, for example a sum over
   events instead of over samples, or a recursion instead of a convolution.
   Then the tests allow a relative difference of at most 1e-12. They also
   allow an absolute difference of at most 1e-12 × the largest value of the
   same array. Write the reason in the test docstring.
3. `scripts/vb_parity.py` must print `ok` for each card. If a rounded value
   changes (section 2.4, item 9), stop. Tell the user the value, the old and
   the new number, and the unrounded value. The user decides whether to add
   an accepted difference. Do not change the rounding.
4. The fork changes the PNS values a little: the old filter cuts its kernel at
   1e-16, and the recursion does not. Phase 1 measures the largest difference
   between the fork and stock pypulseq, and records it in the PR. If it is
   more than the tolerance of item 2, stop and tell the user.
5. Do not test pypulseq in this library (decision 3 of section 2.5).

### 3.6 Work in the fork

1. **Clone.** `git clone git@github.com:mdtisdall/pypulseq.git ~/dev/pypulseq`.
   Add the upstream repository as the remote `upstream`. The worktree rules of
   this project do not apply to the fork.
2. **Base.** Start each fork branch from the release tag that this project
   uses (1.5.0.post1: find the exact tag name). Do not start from upstream
   `master`: it has changes that are not released. Before the first change,
   compare the tag's `src/pypulseq` with the installed package
   (`.venv/lib/python3.12/site-packages/pypulseq`). They must be the same.
3. **One change, one commit, one branch.** Phase 1 uses the branch
   `pns-lfilter`. `docs/plans/diagram-lanes.md` uses `pns-chunks`, which
   starts from `pns-lfilter`.
   Each change can then move to upstream `master` with a rebase, if the user
   decides so.
4. **Tests of the change** go in pypulseq's own test suite, in the fork. Run
   the whole suite of the fork before each commit. Use the Python of this
   project's devShell (`nix develop ~/dev/pulseq-reports --command ...`) and
   a separate uv environment in `~/dev/pypulseq`. Find the test command in the
   fork's own documents or CI configuration.
5. **Approval.** Show each fork commit message to the user and wait for
   approval before `git commit`. Push to the fork only after approval. Never
   push to upstream. Never open an upstream issue or pull request (decision 5
   of section 2.5).
6. **The pin.** This project pins one fork commit:
   ```toml
   [tool.uv.sources]
   pypulseq = { git = "https://github.com/mdtisdall/pypulseq", rev = "<commit>" }
   ```
   The requirement in `[project] dependencies` stays `pypulseq`. `uv.lock`
   records the commit. CI fetches the public fork. Pin a full commit hash, not
   a branch name.
7. **Consumers.** uv uses `[tool.uv.sources]` only for this project's own
   environment. A project that depends on pulseq-reports gets stock pypulseq
   from PyPI, unless it adds the same source line (question 6 of section 7).
   `docs/usage.md` states this while the pin exists.

## 4. Shared design

### 4.1 The sequence index (phase 2)

`seq_index.py` makes one `SequenceIndex` for a sequence:

```python
@dataclass(frozen=True)
class SequenceIndex:
    num_blocks: int
    block_id: np.ndarray        # uint32, length N: the pypulseq block id, in play order
    start_s: np.ndarray         # float64, length N: block start (s), the sequential sum
    duration_s: np.ndarray      # float64, length N
    end_s: float                # the end of the last block
    rf: np.ndarray              # uint8/16/32, length N: dense RF index, 0 = none
    gx: np.ndarray              # the same, one gradient index space for the three axes
    gy: np.ndarray
    gz: np.ndarray
    adc: np.ndarray
    rf_first: np.ndarray        # int64, one for each unique RF event: its first block (play index)
    grad_first: np.ndarray      # the same for gradients (with the axis, see below)
    grad_first_axis: np.ndarray # uint8: 0, 1, 2 for gx, gy, gz
    adc_first: np.ndarray

def sequence_index(seq: pp.Sequence) -> SequenceIndex
def rf_events(seq, index) -> Iterator[tuple[int, SimpleNamespace]]    # (dense k, event)
def grad_events(seq, index) -> Iterator[tuple[int, SimpleNamespace]]
def adc_events(seq, index) -> Iterator[tuple[int, SimpleNamespace]]
```

1. `sequence_index` reads `seq.block_events` and `seq.block_durations` in play
   order. It does not call `get_block`. It builds one column at a time
   (as `diagram_data.diagram_tables` does now). `start_s` is the sequential
   sum `start += duration`, the same float operations as
   `waveforms._timed_blocks`.
2. A start array of length N is allowed here (80 MB at 10^7 blocks). The
   browser rules of the second plan do not apply to Python.
3. `*_events` call `get_block` only on the first block of each unique event,
   with the block cache off (section 4.2).
4. `sequence_index` keeps the result for each sequence object, so that four
   cards on one page build it one time. Use a `weakref.WeakKeyDictionary`.
   Keep with it the number of blocks and the last block id. Build the index
   again when they changed.
5. `diagram_data.diagram_tables` uses `sequence_index` and `*_events` instead
   of its own loop. Its output must not change (`tests/test_diagram_data.py`
   and the golden test pass without a change).

### 4.2 The block cache (phase 2)

`seq_index.py` has a context manager:

```python
@contextmanager
def block_cache_off(seq: pp.Sequence) -> Iterator[None]
```

It sets `seq.use_block_cache = False` and gives back the old value at the
end, also after an error. It does not remove blocks that are already in the
cache. Check the attribute name in the installed pypulseq before you use it.

### 4.3 The raster sampler (phase 2)

`sampling.py` gives the gradient waveform of one axis at given times, from
the index and the unique gradient events:

```python
class GradientSampler:
    def __init__(self, seq: pp.Sequence, index: SequenceIndex) -> None
    def sample(self, axis: str, t: np.ndarray) -> np.ndarray   # Hz/m, t sorted (s)
```

1. The waveform is the same polyline as pypulseq `get_gradients()`:
   - The corner points of each block's event, at the times
     `(block start + delay) + offset`, with the offsets of
     `seq_utils.gradient_offsets`.
   - Straight lines between the points.
   - 0 where no event plays.
2. `sample` finds the blocks that overlap `[t[0], t[-1]]` with
   `numpy.searchsorted` on `index.start_s`. It uses `numpy.interp` inside each
   block. Its cost is O(samples + blocks in the range), not O(all blocks).
3. The values must agree with `seq.get_gradients()` evaluated at the same
   times, inside the tolerance of section 3.5, item 2. Test this on the
   synthetic sequences of `tests/synthetic.py`, including the arbitrary
   gradient and a gradient that ends non-zero at a block boundary.
4. Phase 5 and `docs/plans/diagram-lanes.md` use the sampler. Phase 1 does
   not: `calc_pns` in the fork still samples through `seq.get_gradients()`
   (section 4.4).

### 4.4 PNS (phase 1)

**Step 1 (phase 1): the recursive filter in the fork.**

1. In the fork, `safe_tau_lowpass` computes the same first-order filter with
   `scipy.signal.lfilter([alpha], [1.0, alpha - 1.0], dgdt)`. This is
   `y[i] = alpha * x[i] + (1 - alpha) * y[i - 1]` with `y = 0` before the
   first sample (section 2.4, item 1). Keep the function name, the arguments
   and the result shape. The argument `eps` then has no effect. Keep it, so
   that callers do not break, and say so in the docstring.
2. The fork test compares the new function with the old convolution, which
   it keeps as a copy. It uses random input and the time constants of
   `safe_example_hw()`, with the tolerance of section 3.5, item 2.
3. In this project, `pns.py` makes two changes of its own:
   - It decides "no gradients" from the gradient columns of
     `seq.block_events`, not from `seq.get_gradients()`. The current code
     builds the gradients of the whole file two times.
   - It turns the block cache off around `seq.calculate_pns`
     (`seq.use_block_cache = False` in a `try`/`finally` block, and gives back
     the old value).
4. `calc_pns` still keeps whole-file arrays, so the memory still grows with
   the duration. Phase 1 measures how much. `docs/plans/diagram-lanes.md`
   removes this.

**Step 2: chunks, for 10^7 blocks.** This moved to
`docs/plans/diagram-lanes.md` (its phases 1 and 2), together with the PNS
chart, which becomes lanes of the sequence diagram.

### 4.5 RF exposure on the index (phase 3)

1. For each unique RF event, compute these values one time:
   `hold_samples(rf, raster)`, the `|B1|` values (µT), the peak, the energy
   `sum(b1^2 × dt)`, and the sample times from the pulse start. Keep the
   per-sample energies and their cumulative sum for the window search.
2. The number of pulses, the energy and the peak come from the events and
   the index.
3. The first block with the peak is the first block, in play order, whose
   event has the largest peak. The current code gives the same block, because
   it keeps a peak only when a later one is strictly larger.
4. The window search keeps the current meaning (section 2.4, item 5, and
   `rf_exposure._max_window_energy`). It tries only these starts:
   - The first sample of each pulse.
   - For each sample time `u` that comes into the window while the start moves
     over one pulse: the first sample start `s` with `s > u − W`.
5. For each start, the window energy is the sum of three parts:
   - The energy of the whole pulses in the window, from one cumulative array
     over the pulses in play order.
   - The part of the pulse that holds the start, from its event's cumulative
     sum.
   - The part of the pulse that holds the window end, from its event's
     cumulative sum.
6. `periodic=True` lets a window wrap into the next repetition of the
   sequence, as now. Use the index of the pulse modulo the number of pulses,
   and add the period to the time. Do not copy the arrays.
7. The card for several files puts the pulses of all files in one play order,
   with the file offsets. It does not read a file two times.
8. The oracle (`tests/oracles/rf_exposure.py`) is the current module. The
   tests compare every output with the oracle, with the tolerance of section
   3.5, item 2. They use the synthetic sequences and random pulse trains, with
   random pulse shapes, gaps and window lengths.

### 4.6 Gradient limits on the index (phase 4)

1. For each unique gradient event, compute these values one time from its
   corner points (`gradient_offsets`):
   - The peak `|g|`.
   - The largest slew between two neighbouring points.
   - The first and the last value (for the junction steps of item 6).
   - The integral of `g^2`, with the current formula
     `dt × (a^2 + a·b + b^2) / 3`.
2. For each axis: count how many times each event plays on that axis (for
   example `numpy.bincount` of the axis column). The RMS comes from the sum of
   count × integral. The peak and the slew are the largest event values. The
   "block" of a peak or a slew is the smallest play index among the blocks
   whose event has that value.
3. **Peak of |G|.** Find the distinct triples `(gx, gy, gz)` of the index
   columns (for example `numpy.unique` on the three columns). Compute the
   current `_vector_peak_in_block` one time for each triple. A triple fully
   decides the |G| waveform of its block, because all events start at the
   block start plus their own delay.
4. **Window.** Blocks fully inside the window use the per-event values over
   that range of play indexes. The blocks that a window edge cuts (at most
   two, and blocks of zero duration at an edge) use the current clipping code.
   The card computes the whole-file RMS and the window values in one pass over
   the index, not two.
5. The current results are the reference. Task 4.1 first adds tests of the
   current code for the cases that no test covers now (section 5, phase 4).
   These tests must pass before and after the change.
6. **Junction steps** (decision 6 of section 2.5). For each axis and each pair
   of neighbouring blocks, the step is `|last(i) − first(i + 1)|` divided by
   `grad_raster_time`. Use 0 for a block that has no event on the axis, and
   `first(0) − 0` before the first block. Compute it with numpy from the index
   columns and the per-event first and last values. The slew of an axis is
   the largest of the segment slopes and the junction steps. Its "block" is
   the block after the junction. The oracle does not compute junction steps,
   so the tests compare the segment part with the oracle and the junction
   part with hand-computed values.

### 4.7 Gradient spectrum on the sampler (phase 5)

1. Replace `seq.get_gradients()` in `grad_spectrum.gradient_spectrum` with the
   sampler. Sample each chunk at the same times as now.
2. Keep the spectrogram, the window, the chunk size, the combination by a
   maximum, the band peaks and `combine` as they are.
3. The oracle is the current module. The tests compare the spectra with the
   tolerance of section 3.5, item 2.
4. A process pool for the chunks is not part of this plan. If the time budget
   at 10^7 blocks fails, stop and tell the user (section 2.6).

## 5. Phases

Each phase lists its tasks and sub-tasks. Each item has a tier (section 3.2).

---

### Phase 0: TESTS.md skeleton

Branch: `docs/cards-scale-tests-skeleton`. Parallel: yes, with phase 1. Tier
of the phase: H. Review: O.

**Task 0.1: Add two placeholder sections.** Tier H.

1. At the end of `TESTS.md`, after section 2.21, add these sections in this
   order. Each has only its heading and one placeholder line:
   ```
   ### 2.22 Sequence index (`test_seq_index.py`)

   Phase 2 of `docs/plans/cards-at-scale.md` adds the entries.

   ### 2.23 Raster sampler (`test_sampling.py`)

   Phase 2 of `docs/plans/cards-at-scale.md` adds the entries.
   ```

Acceptance: `scripts/check` passes.

---

### Phase 1: PNS with the recursive filter in the fork

Two parts: work in the fork (branch `pns-lfilter`), then one PR in this
project (branch `chore/pypulseq-fork-pns`). Parallel: yes, with phases 0 and
2. Tier of the phase: O for the fork setup and review, S for the rest.

**Task 1.1: Make the fork.** The user.

1. The user makes `mdtisdall/pypulseq` with the GitHub Fork button of
   `pulseq/pypulseq`.
2. The user tells the agent the clone path (question 5 of section 7).

**Task 1.2: Set up the fork.** Tier O.

1. Clone the fork. Add the `upstream` remote. Make the branch `pns-lfilter`
   from the release tag (section 3.6, items 1 and 2).
2. Find how to run pypulseq's test suite. Run it one time without a change,
   and record the result.

**Task 1.3: The recursive filter.** Tier S. Review O.

1. Section 4.4, step 1, items 1 and 2, in the fork.
2. Run the whole test suite of the fork.

**Task 1.4: Commit and push the fork.** Tier O.

1. Show the commit message to the user and wait for approval. Commit. Push
   the branch to the fork after approval.

**Task 1.5: Pin the fork in this project.** Tier S. Review O.

1. `[tool.uv.sources]` with the commit of task 1.4 (section 3.6, item 6).
   Update `uv.lock` with `uv lock`. Check that `uv sync --frozen` installs the
   fork commit.
2. Section 4.4, step 1, item 3, in `pns.py`.
3. `tests/test_pns.py`: keep every current test. Add a test that `pns_prediction`
   gives back the old `use_block_cache` value, also after an error. Add a test
   for the "no gradients" check from `seq.block_events` if no current test
   covers it.
4. `docs/usage.md` is not in this phase. Phase 7 describes the pin.
5. `TESTS.md` section 2.11.

**Task 1.6: Measure stock pypulseq against the fork.** Tier S.

1. Use a baseline worktree of `origin/main` (stock pypulseq) and the branch of
   task 1.5 (the fork), as the `parallel-agents` skill says. Run each size in a
   fresh process.
2. Sizes: repeating sequences of 12 s, 60 s, 120 s and 370 s, made with the
   builders of `scripts/diagram_scale.py`. For the 370 s file with about
   4 × 10^4 blocks, give the builder a longer TR. Also the ex-vivo file
   `data/exvivo_gre_seg_0.seq` (question 3 of section 7).
3. Record, for each size and each side: the time and the added RSS of
   `pns_card`.
4. On the synthetic sequences of `tests/synthetic.py`, record the largest
   difference of the PNS values between the two sides, relative to the peak.
   The PNS values are the root-sum-of-squares and the three axes. Apply
   section 3.5, item 4.
5. Run `scripts/vb_parity.py` on the branch. Apply section 3.5, item 3.

**Task 1.7: Report to the user.** Tier O.

1. Show a table of the measurements of task 1.6.
2. The user decides:
   - Whether to merge the PR of this phase (the pin).
   - Whether to prepare an upstream proposal later (decision 5 of section
     2.5).
3. If the user wants an upstream proposal, prepare it only: a branch rebased
   onto upstream `master`, and a draft text with the measurements. The user
   opens it.

Acceptance: `scripts/check` passes. The PR records the measurements. The 370 s
time budget of section 2.6 passes. If the 370 s memory budget fails because
`calc_pns` keeps whole-file arrays, tell the user:
`docs/plans/diagram-lanes.md` removes this. The
user decides whether to merge phase 1 first. The parity script prints `ok` for
PNS, or the user accepts each difference.

---

### Phase 2: the index, the block cache, the sampler and the scale script

Branch: `feature/sequence-index`. Parallel: yes, with phase 1, after phase 0 is
merged. Tier of the phase: O for the interfaces, S for the rest.

**Task 2.1: `seq_index.py`.** Tier O for the interface, S for the code.

1. Write `SequenceIndex`, `sequence_index`, `rf_events`, `grad_events`,
   `adc_events` and `block_cache_off` (sections 4.1 and 4.2).
2. The executing agent writes the dataclass and the function signatures with
   their docstrings first. Then an S worker writes the bodies.

**Task 2.2: `diagram_data.py` on the index.** Tier S. Review O.

1. `diagram_tables` uses `sequence_index` and `*_events`. It uses
   `block_cache_off` when it calls `get_block`.
2. Exactness check (a scratch script, not committed): `diagram_tables` gives
   identical arrays (`numpy.array_equal`, same dtypes) on this branch and on
   `origin/main`. Check the synthetic sequences and the builders of
   `scripts/diagram_scale.py` at 10^4 blocks. Use a baseline worktree as the
   `parallel-agents` skill says. Record the result in the PR.

**Task 2.3: `sampling.py`.** Tier S. Review O.

1. Write `GradientSampler` (section 4.3).
2. Performance target: at least 2 × 10^7 samples each second for each axis on
   the 10^6-block repeating sequence. Record the measured value in the PR.

**Task 2.4: Tests.** Tier S.

1. `tests/test_seq_index.py`:
   - The dense index columns and the first blocks equal those that
     `diagram_data.diagram_tables` gave on `origin/main`.
   - `start_s` equals the sequential sum exactly.
   - The index is kept for one sequence object, and built again after
     `add_block`.
   - `block_cache_off` gives back the old setting, also after an error.
   - `*_events` call `get_block` one time for each unique event. Count the
     calls with a wrapper.
2. `tests/test_sampling.py`:
   - The sampler equals `seq.get_gradients()` at the same times (section 4.3,
     item 3), on the whole file and on sub-ranges that cut blocks.
   - The value is 0 before the first event and after the last event.
   - An empty sequence gives zeros.
3. `TESTS.md` sections 2.22 and 2.23 (and 2.18 if a test there changes).

**Task 2.5: `scripts/cards_scale.py`.** Tier S.

1. A script like `scripts/diagram_scale.py`, not part of `scripts/check` or
   CI. Arguments: `--card pns|rf|limits|spectrum|diagram|all`, `--blocks N`,
   `--case repeating|worst`, `--tr-s T` (optional: a longer TR, for a file
   like the 370 s file), `--out DIR`.
2. It imports the builders of `scripts/diagram_scale.py` by path. It does not
   copy them.
3. It records, for each card: the time, the peak RSS before and after, the
   added RSS, the sequence duration and the number of blocks. It writes JSON.
4. It runs each card in a fresh process when `--card all` is given, so that
   the peak RSS of one card does not hide another.

Acceptance: `scripts/check` passes. The exactness check of task 2.2 passes.
The golden test of the diagram passes without a change.

---

### Phase 3: RF exposure on the index

Branch: `feature/rf-exposure-scale`. Parallel: yes, with phases 4 and 5.
Tier of the phase: O for the window search, S for the rest.

**Task 3.1: The oracle.** Tier H.

1. Copy `src/pulseq_reports/rf_exposure.py` without a change to
   `tests/oracles/rf_exposure.py`. Change only the imports, so that it runs
   from `tests/`. Add a docstring line: "Oracle: the implementation before
   phase 3 of docs/plans/cards-at-scale.md. Do not change it."

**Task 3.2: Per-event values and totals.** Tier S.

1. Section 4.5, items 1 and 2, with `seq_index.rf_events`.

**Task 3.3: The window search.** Tier O.

1. Section 4.5, items 4, 5 and 6. Write the proof of item 5 of section 2.4 in
   the docstring of the search, in a few sentences.

**Task 3.4: The card.** Tier S.

1. Section 4.5, item 7: the "All files" table without a second read.

**Task 3.5: Tests.** Tier S.

1. `tests/test_rf_exposure.py`: keep every current test. Add comparisons with
   the oracle (section 4.5, item 8) for these cases:
   - The synthetic sequences.
   - `periodic=True` and `periodic=False`.
   - Window lengths shorter than one pulse, between one pulse and the
     sequence, and longer than the sequence.
   - 200 random pulse trains made with pypulseq (`make_block_pulse`,
     `make_sinc_pulse`, random gaps).
2. `tests/test_rf_exposure_card.py`: two and three files give the same "All
   files" table as the oracle.
3. `TESTS.md` sections 2.7 and 2.8.

**Task 3.6: Measure and parity.** Tier S.

1. `scripts/cards_scale.py --card rf` for the 370 s file, 10^6 and 10^7
   repeating blocks, and 10^5 worst-case blocks.
2. `scripts/vb_parity.py`. Apply section 3.5, item 3.

Acceptance: `scripts/check` passes. The RF exposure budgets of section 2.6
pass. The parity script prints `ok` for RF exposure, or the user accepts
each difference.

---

### Phase 4: gradient limits on the index

Branch: `feature/gradient-limits-scale`. Parallel: yes, with phases 3 and 5.
Tier of the phase: S, with O review.

**Task 4.1: Reference tests of the current code.** Tier S.

Add these tests to `tests/test_grad_limits.py` first. Each uses sequences made
with pypulseq `make_*` functions. Each must pass with the current code before
the other tasks start. They test only the computations of this library, not
pypulseq (decision 3 of section 2.5).

1. The largest slew of an arbitrary gradient is the largest
   `|Δg / Δt|` between its neighbouring points.
2. The largest slew of an extended trapezoid.
3. With several blocks and several axes, the peak and the slew are the
   largest over all of them. The block is the first block that has that value.
4. A window that cuts a ramp: the slew over the window is the slew of the part
   of the ramp inside the window.
5. The peak of |G| for two blocks with different triples of events.

Task 4.3 adds the junction steps (section 4.6, item 6). Add their tests with
it, not in task 4.1:

1. A tolerated step between two extended trapezoids. pypulseq accepts a step
   up to `max_slew × grad_raster_time`.
2. A gradient that ends non-zero before a block with no gradient on that
   axis.
3. A first block that does not start at 0, within the tolerance.

**Task 4.2: The oracle.** Tier H.

1. Copy `src/pulseq_reports/grad_limits.py` to `tests/oracles/grad_limits.py`,
   as task 3.1 does.

**Task 4.3: Per-event values, triples and windows.** Tier S. Review O.

1. Section 4.6, items 1 to 4, with `seq_index.grad_events`.

**Task 4.4: Tests.** Tier S.

1. Compare every output of `gradient_limits` with the oracle, with and
   without a window. Use the tolerance of section 3.5, item 2. Use the
   synthetic sequences and 200 random sequences made with pypulseq. The random
   sequences have trapezoids, extended trapezoids and arbitrary gradients on
   random axes, and random windows.
2. `tests/test_gradient_limits_card.py`: the card with a window makes one pass
   (count the calls to `sequence_index`, or to the per-event function).
3. `TESTS.md` sections 2.13 and 2.14.

**Task 4.5: Measure.** Tier S.

1. `scripts/cards_scale.py --card limits` for the 370 s file, 10^6 and 10^7
   repeating blocks, and 10^5 worst-case blocks.

Acceptance: `scripts/check` passes. The gradient limits budgets of section
2.6 pass.

---

### Phase 5: gradient spectrum on the sampler

Branch: `feature/spectrum-scale`. Parallel: yes, with phases 3 and 4. Tier
of the phase: S, with O review.

**Task 5.1: The oracle.** Tier H.

1. Copy `src/pulseq_reports/grad_spectrum.py` to
   `tests/oracles/grad_spectrum.py`, as task 3.1 does.

**Task 5.2: The sampler in the spectrum.** Tier S. Review O.

1. Section 4.7, items 1 and 2.

**Task 5.3: Tests.** Tier S.

1. `tests/test_grad_spectrum.py`: keep every current test. Compare the axis
   spectra, the RSS spectrum and the band peaks with the oracle. Use the
   tolerance of section 3.5, item 2. Use the synthetic sequences and the
   builders of `scripts/diagram_scale.py` at 10^4 blocks.
2. `TESTS.md` sections 2.9 and 2.10.

**Task 5.4: Measure and parity.** Tier S.

1. `scripts/cards_scale.py --card spectrum` for the 370 s file, 10^6 and 10^7
   repeating blocks, and 10^5 worst-case blocks.
2. `scripts/vb_parity.py`. Apply section 3.5, item 3.

Acceptance: `scripts/check` passes. The spectrum budgets of section 2.6
pass, or the user accepts the measured values. The parity script prints `ok`
for the spectrum, or the user accepts each difference.

---

### Phase 6: moved

The former phase 6 (PNS in chunks, and the PNS card at 10^7 blocks) is now
part of `docs/plans/diagram-lanes.md`. The phase number stays free, so that
the other numbers do not change.

---

### Phase 7: scale check, documents and release

Branch: `chore/cards-scale`. Parallel: no. It starts after phases 1, 3, 4
and 5 are merged. Tier of the phase: O, with H for the documents.

**Task 7.1: Measure all cards.** Tier O.

1. `scripts/cards_scale.py --card all` for the 370 s file, 10^7 repeating
   blocks and 10^5 worst-case blocks.
2. A page with all cards for the 370 s file: open it in the browser (the
   `dev-workflow:browser-check-localhost` skill). Check each card, both
   themes, and no console errors.
3. Compare with section 2.6. Put a table of the results in the PR.

**Task 7.2: Documents.** Tier H, with the text from the executing agent.

1. `TODO.md`: delete the item "Make the other cards work at 10^7 blocks".
2. If the pin to the fork stays, add the `TODO.md` item "Move from the
   pypulseq fork to a pypulseq release". Give the fork commits and the state
   of each upstream proposal.
3. `docs/usage.md`: state that all cards work for a file of up to 10^7 blocks,
   with the measured times, except PNS (`docs/plans/diagram-lanes.md`).
   While the pin exists, state that a project that depends on pulseq-reports
   needs the same `[tool.uv.sources]` line to get the fast PNS (section 3.6,
   item 7).
4. This plan: set the status to "complete", list the PR numbers and the fork
   commits, record the decisions made during the work and the results.

**Task 7.3: Tag `v0.2.0`.** Tier O.

1. After the PR is merged and CI passes on `main`, ask the user to approve the
   tag. Show the commit. Tell the user whether the release still pins the
   fork (question 7 of section 7).
2. Only after approval: `git tag -a v0.2.0 -m "pulseq-reports 0.2.0"` and
   `git push origin v0.2.0`.

Acceptance: the budgets of section 2.6 pass, or the user accepts the measured
values. `TODO.md`, `docs/usage.md` and this plan are updated.

## 6. Summary of parallel work

| Wave | Phases | Condition to start |
|---|---|---|
| 1 | 0, 1, 2 | The user approves this plan. Phase 1 also needs the fork (task 1.1). Phase 2 starts after phase 0 is merged. |
| 2 | 3, 4, 5 | Phase 2 merged. At most three PRs open. |
| 3 | 7 | Phases 1, 3, 4 and 5 merged. |

Tasks inside a phase that can run as parallel workers:

| Phase | Parallel workers |
|---|---|
| 0 | One H worker. |
| 1 | The executing agent does tasks 1.2, 1.4 and 1.7. One S worker for task 1.3 (the fork). After task 1.4, one S worker for task 1.5 and one S worker for the scratch scripts of task 1.6 (different files). |
| 2 | The executing agent writes the interfaces of task 2.1. Then S workers at the same time: task 2.1 bodies with task 2.2 (one worker, `seq_index.py` and `diagram_data.py`), task 2.3 (one worker, `sampling.py`), task 2.5 (one worker, `scripts/cards_scale.py`). Task 2.4 follows 2.1 and 2.3. |
| 3 | Task 3.1 (H) and task 3.2 (S) at the same time. The executing agent does task 3.3. Task 3.4 (S) after 3.2. Task 3.5 (S) after 3.3 and 3.4. |
| 4 | Task 4.1 (S) and task 4.2 (H) at the same time. Task 4.3 (S) after 4.1. Task 4.4 (S) after 4.3. |
| 5 | Task 5.1 (H) and task 5.2 (S) at the same time. Task 5.3 (S) after 5.2. |
| 7 | The executing agent does tasks 7.1 and 7.3. One H worker for task 7.2 with the exact text. |

## 7. Questions still open

1. **The budgets.** The user approves or changes the budgets of section 2.6
   before phase 1 starts.
2. **The PNS arrays.** Moved to `docs/plans/diagram-lanes.md` (question 1).
3. **The real file.** Answered on 2026-09-24: the file of section 2.2 is
   file 0 of the ex-vivo GRE protocol of another project. The user gave a
   copy. It is `data/exvivo_gre_seg_0.seq`, git-ignored and linked into each
   worktree. Never commit it. Phases 1 and 7 measure it, together with the
   synthetic 370 s sequence.
4. **Accepted differences.** If a rounded value changes (section 3.5, item 3),
   the user decides whether to accept it.
5. **The fork.** The user makes `mdtisdall/pypulseq` (task 1.1) and confirms
   the clone path. The proposal is `~/dev/pypulseq`.
6. **Consumers of the pin.** A project that depends on pulseq-reports gets the
   fast PNS only if it adds the same `[tool.uv.sources]` line. The user
   decides whether to tell such projects (for example the one of section 2.2).
7. **The release and the pin.** The fork changes can be missing from the
   pypulseq releases at phase 7. Then the user decides whether to tag
   `v0.2.0` with the pin, or to wait.
