# Plan: the pulseq-reports library

Mode: Strict STE100. Structural rules are enforced. Lexical rules are a
direction of travel, not a verified dictionary match.

Status: not started. The plan was written on 2026-09-18.

## 1. Goal

Make a new Python library, `pulseq-reports`. The library writes one
self-contained HTML review report for one or more Pulseq sequences. Each
project that uses it supplies its own sequences and can add its own cards.

This plan makes the library only. It does not change `vb-pulseq` or
`ex-vivo-gre-pulseq`. Each of those projects moves to the library in a later,
separate plan.

## 2. Read this first (context for the executing agent)

### 2.1 Source projects

| Project | Path | GitHub | Commit to copy from |
|---|---|---|---|
| vb-pulseq | `~/dev/vb_pulseq` | `mdtisdall/vb-pulseq` (private) | `3a1c7dd` |
| ex-vivo-gre-pulseq | `~/dev/ex-vivo-gre-pulseq` | `mdtisdall/ex-vivo-gre-pulseq` (private) | `2409949` |
| pulseq-reports (new) | `~/dev/pulseq-reports` | `mdtisdall/pulseq-reports` (public, not created yet) | none |

Copy code from vb-pulseq at commit `3a1c7dd`. Use `git -C ~/dev/vb_pulseq
show 3a1c7dd:<path>` to read a file at that commit. Do not copy from the vb
working tree, because it can have newer changes.

At the start of this plan, `~/dev/pulseq-reports` holds only this file. It is
not a git repository.

### 2.2 Decisions that are already made

Do not open these decisions again. The user made them or approved them.

1. **Public repository.** `mdtisdall/pulseq-reports` is public on GitHub.
   Consumers pin it by git URL and tag, for example
   `pulseq-reports @ git+https://github.com/mdtisdall/pulseq-reports@v0.1.0`.
   CI of a consumer needs no credentials to fetch it.
2. **License: MIT.** Before the repository becomes public, ask the user to
   confirm two items (see task 0.1). The user was told that Penn's copyright
   policy (Faculty Handbook III.D) lets the author choose the license. The
   exceptions are sponsored-research agreements, works made for hire, and
   substantial use of university resources.
3. **Scope: the library only.** Do not edit `vb-pulseq` or
   `ex-vivo-gre-pulseq` in this plan. Read them only.
4. **The gradient limits card is new and is part of this plan** (phase 6).
5. **The library is sequence-agnostic.** It takes `pp.Sequence` objects. It
   knows nothing about spin echo, GRE, labels such as LIN or ECO, or TR types.
6. **What moves from vb-pulseq into the library:**
   - `seq_utils.py` (only `GAMMA`, `TIME_TOLERANCE`, `iter_blocks`,
     `BlockTiming`, `hold_samples`)
   - `grad_spectrum.py`, `rf_exposure.py`, `pns.py`
   - `report/markup.py`, `report/diagram.py`, `report/spectrum_card.py`,
     `report/exposure_card.py`, `report/pns_card.py`
   - the timing check, the definitions table and the block table (now in
     `report/__init__.py` and `report/diagram.py`)
   - `report/assets/report.css`, `report/assets/chart_math.js`, and the
     generic part of `report/assets/report.js` (the `laneChart` function)
   - `tests/js/test_chart_math.js`
7. **What stays in vb-pulseq:** the column cross-section, RF pulse profile and
   coherence pathway cards, `moments.py`, `column.py`, `rf_profiles.py`,
   `rf_sim.py`, `spin_echo.py` and all phantom and twix code.
8. **What stays in ex-vivo-gre-pulseq:** `seq_analysis.py`, and the
   acquisition summary, echo and polarity map, spoiling and transient cards.
9. **Charts are drawn in the browser** by the existing `laneChart` JavaScript
   in vb-pulseq. Do not add a plotting library. Do not add a JavaScript
   dependency or a build step.
10. **No DOM tests.** Node tests cover only pure JavaScript functions
    (`chart_math.js`). Check each chart in a real browser with the
    `dev-workflow:browser-check-localhost` skill before you open its PR.
11. **Dependencies are fixed in phase 0:** `pypulseq>=1.5.0.post1`, `numpy`,
    `scipy`. Dev: `pytest`, `ruff`. Do not add a dependency in a later phase.
    If a phase needs one, stop and ask the user.
12. **Python 3.12, uv, Nix devShell, hatchling, ruff line length 100.** These
    are the same as in vb-pulseq.

### 2.3 Why the design is not a plain copy of vb-pulseq

The vb-pulseq report has four limits. `ex-vivo-gre-pulseq` needs each of them
removed. The library must remove them.

1. **Fixed page.** vb-pulseq has one `template.html` with one placeholder for
   each card, one global `DATA` object with fixed keys, and DOM ids that are
   hard-coded in Python and in JavaScript. A new card needs edits in three
   files. The library uses a list of `Card` objects instead (phase 1).
2. **One card reads the data of another card.** The "peak TR" view of the
   vb-pulseq diagram reads `DATA.pns.peak_tr_ms`. In the library, the caller
   gives the diagram a list of named time windows (phase 7). The PNS module
   gives a public function that returns the peak-TR window (phase 5).
3. **Size.** vb-pulseq sends every waveform point of the whole sequence to the
   page. ex-vivo has about 4 files, about 39,000 blocks in each file, about
   4,500 TRs in each file, and a TR of 80 ms (about 24 min in total). All the
   points of all the files are more than one million points, or tens of MB of
   JSON. The library sends exact points only for the windows that the caller
   selects. For a whole file that is too large, it sends a min/max envelope
   (phase 7).
4. **One sequence.** vb-pulseq takes one `pp.Sequence`. ex-vivo writes one
   acquisition as several `.seq` files. The library takes a list of named
   sequences (phase 1, `NamedSequence`).

Other facts about ex-vivo that the library must work with:

- The RF pulse is a non-selective hard pulse, 100 µs, 20°. Its peak B1 is
  about 13 µT.
- The system limits are 28 mT/m and 10 T/m/s.
- A full file at the 10 µs gradient raster is about 3.6 × 10⁷ samples for
  each axis. This is too large to hold as one float64 array for each axis in
  the spectrum code. Phase 4 processes the samples in chunks.

### 2.4 Parity with vb-pulseq

When the library gets the same single sequence as vb-pulseq, each moved card
must give the same data as vb-pulseq at commit `3a1c7dd`. This is "parity".
Parity lets vb-pulseq move to the library later without a change in its
report. Phase 8 adds a script that checks parity. Each phase that moves a card
also checks parity for that card before its PR.

### 2.5 Terms

- **Card.** One `<section>` of the report page, with a title, HTML, optional
  JSON data and an optional JavaScript setup function.
- **Window.** A named time range in one file, for example one TR.
- **Envelope.** The minimum and maximum of a waveform in each of N equal time
  bins. It replaces the exact points when there are too many.
- **Consumer.** A project that imports `pulseq-reports`, for example
  vb-pulseq.
- **Worker.** A sub-agent that the executing agent starts with the Agent
  tool.

## 3. How to execute this plan

### 3.1 Workflow

Use the dev-workflow Claude Code plugin skills. Phase 0 installs the same
branch-and-PR workflow that vb-pulseq uses (read `~/dev/vb_pulseq/CLAUDE.md`).

1. Each phase is one branch, one worktree and one pull request.
2. Start each phase with the `dev-workflow:start-task` skill, from the latest
   `origin/main`.
3. Run `nix develop --command scripts/check` before each PR.
4. Open each PR with the `dev-workflow:ship` skill.
5. Show the commit message to the user and wait for approval before
   `git commit`.
6. Merge only when the user tells you to. Use `dev-workflow:finish-task`.
7. To give work to workers, use the `dev-workflow:parallel-agents` skill.
   Workers do not run git write commands. You review each diff.

### 3.2 Worker model tiers

Each task and sub-task has a tier. The tier is the cheapest model that can do
the task safely.

| Tier | Model | Use it when |
|---|---|---|
| H | `haiku` | The task is a mechanical copy or rename with an exact file list. The task needs no design decision. |
| S | `sonnet` | The task writes new code or tests from a full specification in this plan. The task needs local decisions only. |
| O | the executing Opus agent, not a worker | The task sets an interface that other phases use, needs judgment about parity, or reviews other work. |

Rules for workers:

1. Give each worker the full paths of the files it owns. Give it the files it
   may read. Tell it the files it must not edit.
2. Give each worker the parity rule (section 2.4) when its task moves vb code.
3. The executing agent reviews every worker diff before the commit.
4. A tier H or S worker that finds a design problem stops and reports it. It
   does not change an interface from phase 1.

### 3.3 Order and parallel work

```
Phase 0 (setup) ──► Phase 1 (core) ──┬─► Phase 2 (timing, definitions)
                                     ├─► Phase 3 (RF exposure)
                                     ├─► Phase 4 (gradient spectrum)
                                     ├─► Phase 5 (PNS)
                                     ├─► Phase 6 (gradient limits)
                                     └─► Phase 7 (diagram, block table)
                                              │
                    all of phases 2–7 merged ─┴─► Phase 8 (parity, docs, v0.1.0)
```

- Phase 0 and phase 1 are sequential. Phase 1 sets the interfaces that all
  later phases use.
- Phases 2 to 7 can run in parallel after phase 1 is merged. Each phase has
  its own files (section 3.4). Start each one from `origin/main` after
  phase 1 is merged.
- Phase 8 starts after phases 2 to 7 are all merged.
- If you run more than three of phases 2 to 7 at the same time, the review
  work for the user increases. Ask the user how many PRs they want open at
  one time.

### 3.4 File ownership

Each file has one owner phase. A phase edits only the files that it owns.
The one exception is `TESTS.md` (see rule 3 below).

Package root: `src/pulseq_reports/`. Tests: `tests/`.

| Phase | Files that the phase creates and owns |
|---|---|
| 0 | `flake.nix`, `flake.lock`, `.envrc`, `.gitignore`, `pyproject.toml`, `uv.lock`, `LICENSE`, `README.md`, `CLAUDE.md`, `.claude/**`, `.github/workflows/check.yml`, `scripts/check`, `scripts/check_tests_md.py`, `src/pulseq_reports/__init__.py`, `docs/plans/pulseq-reports.md` (this file) |
| 1 | `src/pulseq_reports/seq_utils.py`, `markup.py`, `page.py`, `cards/__init__.py`, `assets/report.css`, `assets/chart_math.js`, `assets/lane_chart.js`, `assets/page.js`, `assets/template.html`, `tests/conftest.py`, `tests/synthetic.py`, `tests/test_seq_utils.py`, `tests/test_markup.py`, `tests/test_page.py`, `tests/js/test_chart_math.js`, `TESTS.md` (the skeleton) |
| 2 | `cards/timing.py`, `cards/definitions.py`, `tests/test_timing_card.py`, `tests/test_definitions_card.py` |
| 3 | `rf_exposure.py`, `cards/rf_exposure.py`, `tests/test_rf_exposure.py`, `tests/test_rf_exposure_card.py` |
| 4 | `grad_spectrum.py`, `cards/spectrum.py`, `assets/cards/spectrum.js`, `tests/test_grad_spectrum.py`, `tests/test_spectrum_card.py` |
| 5 | `pns.py`, `cards/pns.py`, `assets/cards/pns.js`, `tests/test_pns.py`, `tests/test_pns_card.py` |
| 6 | `grad_limits.py`, `cards/gradient_limits.py`, `tests/test_grad_limits.py`, `tests/test_gradient_limits_card.py` |
| 7 | `waveforms.py`, `cards/diagram.py`, `cards/blocks.py`, `assets/cards/diagram.js`, `tests/test_waveforms.py`, `tests/test_diagram_card.py`, `tests/test_blocks_card.py` |
| 8 | `scripts/vb_parity.py`, `docs/usage.md`, and edits to `README.md` and this plan file |

Rules:

1. Phases 2 to 7 do not edit any file of phase 0 or phase 1. This includes
   `pyproject.toml`, `uv.lock`, `page.py`, `markup.py`, `seq_utils.py`,
   `report.css`, `lane_chart.js`, `page.js`, `conftest.py` and
   `synthetic.py`.
2. If a phase 2 to 7 needs a change to a phase 1 file, stop that phase.
   Make the change in its own small PR from `main`. Merge it. Then rebase the
   phase branch.
3. **`TESTS.md`.** Phase 1 writes a skeleton. The skeleton has one `###`
   section for each test file in the table above, in the order of the table.
   Each section holds one placeholder line: `Phase N adds the entries.`
   Each later phase replaces only the placeholder line of its own sections.
   Git merges these edits without a conflict, because an unchanged heading
   line separates each pair of sections. If a rebase gives a conflict in
   `TESTS.md`, keep both sides.
4. Phases 2 to 7 do not edit this plan file. Phase 8 updates its status.
5. A test helper that only one phase needs goes in that phase's test file,
   not in `conftest.py` or `synthetic.py`.

## 4. Public interface (set in phase 1)

Phases 2 to 7 build on these types and functions. Phase 1 writes them. Later
phases do not change them (see rule 2 in section 3.4).

### 4.1 `seq_utils.py`

```python
GAMMA = 42.576e6        # Hz/T
TIME_TOLERANCE = 1e-9   # s

class BlockTiming(NamedTuple): block_id, start_s, duration_s, block
def iter_blocks(seq) -> Iterator[BlockTiming]
def hold_samples(rf, raster) -> tuple[np.ndarray, float]
def gradient_points(g, t0: float) -> tuple[np.ndarray, np.ndarray]
    # corner or sample times (s) and amplitudes (Hz/m) of one gradient event.
    # From vb `report/diagram.py::_gradient_points`, but in Hz/m, not mT/m.

@dataclass(frozen=True)
class NamedSequence:
    name: str            # shown in the report, for example the file name
    seq: pp.Sequence
```

`iter_blocks` and `hold_samples` are copies of vb-pulseq `seq_utils.py`.
Phase 6 and phase 7 both use `gradient_points`. It is in phase 1 so that
the two phases do not both edit one file.

### 4.2 `page.py`

```python
@dataclass(frozen=True)
class Card:
    id: str                       # unique on the page, matches [a-z][a-z0-9-]*
    title: str
    body_html: str                # the HTML inside the section, after the title
    data: object | None = None    # JSON-ready. Written to <script type="application/json" id="{id}-data">
    script: str | None = None     # the name that a card script registered, or None
    collapsed: bool = False       # True: the body is in <details><summary>{title}</summary>

def render_page(title: str, subtitle: str, cards: Sequence[Card],
                extra_scripts: Sequence[str] = ()) -> str
def write_page(path, title, subtitle, cards, extra_scripts=()) -> None
def card_asset(name: str) -> str   # the text of assets/cards/<name>.js
```

Behavior of `render_page`:

1. It raises `ValueError` when two cards have the same `id`, or when an `id`
   does not match the pattern.
2. Each card becomes `<section class="card" id="{id}"
   data-card-script="{script}">`, with the `<h2>` title (or the `<details>`
   form), the body, and the data script element when `data` is not None.
3. It escapes `</` in the JSON as `<\/`, as vb-pulseq does.
4. Script order on the page: `chart_math.js`, `lane_chart.js`, the card
   scripts, `extra_scripts` in the given order, `page.js`.
5. Card scripts: for each distinct `script` name in the cards, it includes
   `assets/cards/<script>.js` one time. A consumer that has its own card
   script passes it in `extra_scripts` and gives the card that name.

### 4.3 JavaScript interface

- `lane_chart.js` defines one global object `PulseqReport` with:
  - `PulseqReport.laneChart(options)`: the vb-pulseq `laneChart`, unchanged
    in behavior, plus a new method `setWindow({lanes, xDomain, extent})`.
    `setWindow` replaces the lanes (any number of lanes), the initial view
    and the extent, and then renders. It recomputes the SVG height from the
    new number of lanes.
  - `PulseqReport.registerCard(name, init)`: stores `init` under `name`.
  - `PulseqReport.el`, `PulseqReport.text`: the SVG element helpers.
- `page.js` runs last. For each `section[data-card-script]`, it reads the
  JSON from `#{id}-data` (or `null`) and calls `init(section, data)`. It
  then adds the focus-outline handler that is at the end of vb `report.js`.
- A card script finds its elements by ids that start with its card id, for
  example `{id}-svg`, `{id}-chart`, `{id}-tip`. Then two cards of the same
  type can be on one page.

### 4.4 Card builder functions (made in phases 2 to 7)

Each card module has one public function that returns a `Card`. All take
`card_id` with a default, so a page can hold two cards of the same type.

| Phase | Function |
|---|---|
| 2 | `cards.timing.timing_card(seqs: Sequence[NamedSequence], card_id="timing")` |
| 2 | `cards.definitions.definitions_card(seqs, card_id="definitions")` |
| 3 | `cards.rf_exposure.rf_exposure_card(seqs, periodic=True, window_s=10.0, card_id="rf-exposure")` |
| 4 | `cards.spectrum.spectrum_card(seqs, resonances=PRISMA_AS82_RESONANCES, scanner_label="MAGNETOM Prisma (AS82)", card_id="gradient-spectrum")` |
| 5 | `cards.pns.pns_card(seq: NamedSequence, gradient_asc=None, card_id="pns")` |
| 6 | `cards.gradient_limits.gradient_limits_card(seqs, window=None, limits=None, card_id="gradient-limits")` |
| 7 | `cards.diagram.diagram_card(seqs, windows, card_id="diagram", point_budget=DIAGRAM_POINT_BUDGET)` |
| 7 | `cards.blocks.blocks_card(seqs, windows=None, max_rows=500, card_id="blocks")` |

## 5. Phases

Each phase lists its tasks and sub-tasks. Each item has a tier (section 3.2).
"Parity" means the rule in section 2.4.

---

### Phase 0: repository setup

Branch: none for the first commit (see task 0.2). Then `chore/project-setup`
if the `project-setup` skill needs a PR. Parallel: no. Tier of the phase: O.

The user must be present for this phase. Several steps are outward-facing.

**Task 0.1: Get the user's approval before you publish anything.** Tier O.

1. Ask the user to confirm the MIT license.
2. Ask the user which copyright holder goes in `LICENSE`: "Dylan Tisdall" or
   "The Trustees of the University of Pennsylvania". The answer depends on
   the Penn policy exceptions in section 2.2, item 2.
3. Ask the user if they checked with PCI (Penn Center for Innovation) about
   sponsored-research terms. Do not make the repository public until the user
   says yes.
4. Ask the user for approval to create the public GitHub repository
   `mdtisdall/pulseq-reports`.

**Task 0.2: Set up the repository with the `dev-workflow:project-setup`
skill.** Tier O. Follow that skill. It covers the first commit on `main`,
before the hook exists. It also covers the GitHub token
(`dev-workflow:github-token`), `.envrc`, `.gitignore`, the hook
`.claude/hooks/block-main-writes.sh`, `.claude/gh-token-permissions`, and the
workflow section of `CLAUDE.md`.

Sub-tasks for the files that the skill does not make:

1. **`flake.nix`.** Tier H. Copy vb-pulseq `flake.nix` at `3a1c7dd`. Change
   the description to `pulseq-reports: development shell`. Keep `nodejs` in
   both shells.
2. **`pyproject.toml`.** Tier H. Name `pulseq-reports`, version `0.1.0`,
   `requires-python = ">=3.12"`. Dependencies: `pypulseq>=1.5.0.post1`,
   `numpy`, `scipy`. Dev group: `pytest`, `ruff`. Hatchling build. Ruff line
   length 100. No `[project.scripts]`. Make sure that the hatchling build
   includes `src/pulseq_reports/assets/**` as package data.
3. **`src/pulseq_reports/__init__.py`.** Tier H. One docstring line and
   `__version__ = "0.1.0"`.
4. **`scripts/check`.** Tier H. Copy vb-pulseq `scripts/check`. Make two
   changes:
   - In the node step, print `skip  node: no JavaScript tests` and continue
     when `tests/js/test_*.js` matches no file. (Phase 0 has no JS tests.)
   - In the shellcheck step, list only `scripts/check` and
     `.claude/hooks/block-main-writes.sh`.
5. **`scripts/check_tests_md.py`.** Tier H. Copy it from vb-pulseq
   unchanged.
6. **`.github/workflows/check.yml`.** Tier H. Copy it from vb-pulseq
   unchanged.
7. **`LICENSE`.** Tier H. The MIT text with the year 2026 and the holder from
   task 0.1.
8. **`README.md`.** Tier H. Three short paragraphs: what the library does, that
   it is under development, and how to run the checks.
9. **`CLAUDE.md`.** Tier O. Use the vb-pulseq `CLAUDE.md` as the model. Add
   two project rules:
   - "The library is sequence-agnostic. Do not add code that knows one
     sequence."
   - "Read `docs/plans/pulseq-reports.md` before you change the design."
10. **Plan file.** Commit this file as `docs/plans/pulseq-reports.md`.

**Task 0.3: Check the setup.** Tier O.

1. Run `nix develop --command uv lock`, then
   `nix develop --command scripts/check`. It must pass with no tests.
2. Confirm that CI runs and passes on the first PR (Actions API, not
   `gh pr checks`).

Acceptance: `main` has the files above. CI passes. The repository is public
only after task 0.1 gets a yes.

---

### Phase 1: core page, shared helpers and JavaScript

Branch: `feat/core`. Parallel: no. It must be merged before phases 2 to 7
start.

**Task 1.1: Shared Python helpers.** Tier S.

1. Write `seq_utils.py` as in section 4.1. Copy `GAMMA`, `TIME_TOLERANCE`,
   `BlockTiming`, `iter_blocks` and `hold_samples` from vb-pulseq
   `seq_utils.py`. Copy `_gradient_points` from vb `report/diagram.py` as
   `gradient_points`, and return Hz/m (remove the `/ GAMMA * 1e3`). Add
   `NamedSequence`. Tier S.
2. Write `markup.py`. Copy vb `report/markup.py` in full: `_points`, `_fmt`,
   `Lane`, `_lanes_json`, `_table`, `_AXIS_COLOR`, `_blocks_cell`, `_sig`,
   `_zoom_controls`. Change `_zoom_controls` to take the card's svg id (it
   already does). Keep the names. They are private by name, but library
   modules use them. Tier H.
3. Write `tests/test_seq_utils.py`. Copy the vb tests for the functions that
   moved (`test_gamma_and_time_tolerance`, `test_iter_blocks_*`,
   `test_hold_samples_*`). Add one test for `gradient_points` with a trapezoid
   and one with an arbitrary gradient. Tier S.
4. Write `tests/test_markup.py`. Copy `test_zoom_controls_markup` from vb
   `tests/tools/test_report.py`. Add a test that `_table` escapes HTML.
   Tier S.

**Task 1.2: Test sequences.** Tier S.

1. Write `tests/synthetic.py`. It makes small test sequences with pypulseq
   only. It must not import vb-pulseq. vb `tests/tools/synthetic.py` uses
   `spin_echo.design_system()`. Replace that with a local `pp.Opts` with
   `max_grad=28 mT/m`, `max_slew=150 T/m/s`, the default rasters, and
   `rf_ringdown_time=20e-6`, `rf_dead_time=100e-6`, `adc_dead_time=10e-6`.
2. Include these builders. Phases 2 to 7 use them:
   - `block_pulse(use, flip)` and `readout()` (from vb).
   - `spin_echo_sequence(...)` (from vb, with the local system).
   - `gre_sequence(num_trs=4, tr=20e-3)`: a hard pulse, a readout trapezoid
     with an ADC, a phase-encode trapezoid, and a spoiler, with the `TR`
     definition set.
   - `empty_sequence()`: one delay block, no RF, no gradients, no ADC.
   - `arbitrary_gradient_sequence()`: one block with an arbitrary gradient
     (`pp.make_arbitrary_grad`).
3. Write `tests/conftest.py`. Copy only the `--collected-tests-file` hook
   from vb `tests/conftest.py`. Do not copy the SLR cache fixture or the
   `write_gradient_asc` fixture. Phase 5 puts `write_gradient_asc` in its own
   test file.

**Task 1.3: The page builder.** Tier O. This task sets the interface in
section 4.2.

1. Write `page.py` with `Card`, `render_page`, `write_page`, `card_asset`.
2. Write `assets/template.html`. Placeholders: `__TITLE__`, `__SUBTITLE__`,
   `__CARDS__`, `__CSS__`, `__JS__`. Copy `_substitute` and its leftover
   placeholder check from vb `report/__init__.py`.
3. Write `tests/test_page.py`. Tier S worker, after the interface is written.
   Test these cases:
   - Cards appear in the given order with their titles.
   - A duplicate id and a bad id raise `ValueError`.
   - The data element holds the JSON, and `</` is escaped.
   - A collapsed card uses `<details>`.
   - Each card script is included one time, even when two cards use it.
   - Script order is as in section 4.2, item 4.
   - `_substitute` replaces every placeholder and raises on a leftover one
     (copy the two vb tests).

**Task 1.4: CSS and JavaScript.** Tier S for sub-tasks 1 to 3. Tier O for
sub-task 4.

1. Copy vb `report/assets/report.css` to `assets/report.css` unchanged.
   Tier H.
2. Copy vb `report/assets/chart_math.js` unchanged, and
   `tests/js/test_chart_math.js` with its `require` path changed to the new
   location. Tier H.
3. Write `assets/lane_chart.js`. Take lines 1 to about 390 of vb
   `report/assets/report.js` (the constants, `el`, `text` and `laneChart`).
   Do not take the code after `laneChart` that sets up the vb cards. Put the
   code in the `PulseqReport` global object (section 4.3). Add `setWindow`.
   Add `registerCard`. Tier S.
4. Write `assets/page.js` (section 4.3). Review the worker's
   `lane_chart.js` diff line by line against vb `report.js`. The only
   changes must be the wrapper, `setWindow` and `registerCard`. Tier O.

**Task 1.5: `TESTS.md` skeleton.** Tier S.

1. Copy the introduction of vb `TESTS.md` (the text before its first test
   section). Remove the vb terms (W, TBW, N, cycles across the column width).
2. Copy the "TESTS.md coverage" section of vb `TESTS.md`.
3. Add entries for the phase 1 tests.
4. Add the `###` sections for phases 2 to 7 with placeholder lines
   (section 3.4, rule 3). Use the heading form that
   `scripts/check_tests_md.py` reads: `### <n>. <title> (`<test file>`)`.

**Task 1.6: Browser check.** Tier O.

1. Write a scratch script (do not commit it) that makes a page with one test
   card. The card's script draws one `laneChart` with two lanes. It calls
   `setWindow` from a button to change to three lanes.
2. Check it with the `dev-workflow:browser-check-localhost` skill: hover,
   drag to zoom, Shift+drag to pan, the zoom buttons, the arrow keys, and the
   light and dark themes.

Acceptance: `scripts/check` passes. The browser check passes. The interfaces
in section 4 exist as written.

---

### Phase 2: timing check and definitions cards

Branch: `feat/timing-definitions-cards`. Parallel: yes, with phases 3 to 7.
Tier of the phase: S (one worker for the whole phase). Review: O.

**Task 2.1: Timing card.** Tier S.

1. Copy `timing_errors` from vb `report/diagram.py` and `_timing_html`. Put
   them in `cards/timing.py`.
2. `timing_card(seqs)`: for one sequence, the body is the same HTML as vb
   (parity). For more than one sequence, show one status line for each file,
   with the file name. Show the error table under each file that has errors.
3. `data=None`, `script=None`. No JavaScript.

**Task 2.2: Definitions card.** Tier S.

1. `definitions_card(seqs)`: for one sequence, the same two-column table as
   vb `report/__init__.py` (parity). For more than one sequence, one row for
   each definition key (the union of the keys in all files, in first-seen
   order), and one column for each file. Show an empty cell where a file does
   not have the key.

**Task 2.3: Tests.** Tier S.

1. `tests/test_timing_card.py`: copy the timing parts of
   `test_report_for_valid_sequence` and `test_report_lists_timing_errors`
   from vb. Add a test with two sequences where only the second one has an
   error.
2. `tests/test_definitions_card.py`: one sequence, and two sequences with
   different keys.
3. Fill the phase 2 sections of `TESTS.md`.

Acceptance: `scripts/check` passes. Parity for one sequence: the body HTML
is equal to the vb HTML for the same sequence.

---

### Phase 3: RF exposure

Branch: `feat/rf-exposure-card`. Parallel: yes. Tier of the phase: S.
Review: O.

**Task 3.1: Physics.** Tier S.

1. Copy vb `rf_exposure.py` to `rf_exposure.py`. Import from
   `pulseq_reports.seq_utils`.
2. Add the argument `periodic: bool = True`. With `True`, the behavior is
   the same as vb (parity). With `False`, the sequence plays one time:
   - B1+rms is the energy divided by the duration, as before.
   - The highest-window search does not wrap around the end.
   - When the duration is shorter than `window_s`, the window is the whole
     sequence. The result records the real window length.

**Task 3.2: Card.** Tier S.

1. Copy `rf_exposure_data` and `_rf_exposure_html` from vb
   `report/exposure_card.py` into `cards/rf_exposure.py`.
2. `rf_exposure_card(seqs, periodic, window_s)`: for one sequence, the same
   body as vb (parity). For more than one sequence, one table row group for
   each file, then an "All files" row. For "All files", peak B1 is the
   maximum over the files. B1+rms uses the files played one after the other
   with no gap. The note must state this assumption.
3. The note text must say "sequence repeated" only when `periodic=True`.

**Task 3.3: Tests.** Tier S.

1. `tests/test_rf_exposure.py`: copy the vb tests. Change the imports and
   replace the vb sequence builders with `tests/synthetic.py`. Add tests for
   `periodic=False`: no wrap, and a sequence shorter than the window.
2. `tests/test_rf_exposure_card.py`: copy `test_rf_exposure_data_for_spin_echo`,
   `test_report_has_rf_exposure_card` and `test_rf_exposure_card_without_rf`
   from vb, changed to the new builder. Add a two-file test.
3. Fill the phase 3 sections of `TESTS.md`.

Acceptance: `scripts/check` passes. Parity for one periodic sequence.

---

### Phase 4: gradient spectrum

Branch: `feat/spectrum-card`. Parallel: yes. Tier of the phase: S for the
card, O for the chunked physics. Review: O.

**Task 4.1: Physics with chunks.** Tier O. The parity condition is strict.

1. Copy vb `grad_spectrum.py`. Rename `PRISMA_ACOUSTIC_RESONANCES` to
   `PRISMA_AS82_RESONANCES`. Keep the comment about where the values come
   from.
2. Change the sampling so that memory does not grow with the sequence length:
   - Keep the padding of half a window at each end, and the window and hop
     of vb (50 ms Hann, 50% overlap).
   - Evaluate the gradient on chunks of `CHUNK_WINDOWS` windows (start with
     256). Each chunk starts at a multiple of the hop and overlaps the next
     chunk by `nwin - hop` samples. Then each chunk gives the same windows
     as one call on the whole array.
   - Call `scipy.signal.spectrogram` with the vb arguments on each chunk.
     Keep the running maximum over windows for each axis and for RSS.
3. Parity: for the synthetic spin echo and GRE sequences, the result must
   equal the vb result with `numpy.testing.assert_allclose(rtol=1e-12)`.
   Check this with a scratch script that imports vb at `3a1c7dd` (see phase 8
   for the method). Put the check that does not need vb into the tests: a
   sequence long enough for three or more chunks gives the same result with
   `CHUNK_WINDOWS=1000000` and with `CHUNK_WINDOWS=4`.
4. Add `combine(spectra) -> GradientSpectrum`: the element-wise maximum of
   each axis and of RSS over several files, with the band peaks recomputed.
   This is correct because the result is a maximum over windows. The windows
   that cross from one file to the next are not included. The card note must
   state this.

**Task 4.2: Card.** Tier S.

1. Copy `spectrum_data` and `_spectrum_html` from vb
   `report/spectrum_card.py` to `cards/spectrum.py`.
2. Replace each fixed "Prisma" text with `scanner_label`. Build the band
   text from `resonances`. With the default arguments, the HTML must equal
   the vb HTML (parity).
3. Use ids that start with `card_id` (section 4.3). The vb ids were
   `spectrum-chart`, `spectrum-diagram` and `spectrum-tip`. With the default
   `card_id="gradient-spectrum"`, the ids change. This is the only accepted
   difference from vb. Record it in the parity script (phase 8).
4. Write `assets/cards/spectrum.js`. Move the spectrum part of vb
   `report.js` (the block that starts with `if (DATA.spectrum.reason ===
   null)`), including the linear/dB buttons. Register it as `"spectrum"`.
   Scope the button queries to the card section.

**Task 4.3: Tests.** Tier S.

1. `tests/test_grad_spectrum.py`: copy the vb tests. Rename the Prisma test.
   Add the chunk test from task 4.1, item 3, and a test for `combine`.
2. `tests/test_spectrum_card.py`: copy `test_spectrum_data_for_spin_echo`,
   `test_report_has_gradient_spectrum_card` and
   `test_report_without_gradients_has_no_spectrum_chart` from vb. Add a
   test for a custom `scanner_label` and custom resonances.
3. Fill the phase 4 sections of `TESTS.md`.

**Task 4.4: Browser check and scale check.** Tier O.

1. Check the chart in the browser: the bands, the dB button, zoom.
2. Scale check (not in CI): build the ex-vivo default protocol with
   `uv run --with-editable ~/dev/ex-vivo-gre-pulseq` in a scratch script. Use
   `ex_vivo_gre_pulseq.sequence.build_segments()`. Run the spectrum of one
   file. Record the time and the peak memory in the PR description.

Acceptance: `scripts/check` passes. Parity. The scale check finishes on one
ex-vivo file.

---

### Phase 5: PNS prediction

Branch: `feat/pns-card`. Parallel: yes. Tier of the phase: S. Review: O.

**Task 5.1: Physics.** Tier S.

1. Copy vb `pns.py` unchanged, except for the imports.
2. Move `_peak_tr_window` from vb `report/pns_card.py` into `pns.py` as the
   public function `peak_tr_window(seq, peak_time_s) -> tuple[float, float] |
   None`. Consumers use it to make a diagram window (phase 7) without a
   dependency between the two cards.

**Task 5.2: Card.** Tier S.

1. Copy `pns_data`, `_pns_html`, `_max_envelope`, `_active_samples` and
   `_pns_lane` from vb `report/pns_card.py` to `cards/pns.py`.
2. `pns_card(seq: NamedSequence, gradient_asc=None)` takes one sequence
   only. The docstring must say that the SAFE model runs over the whole
   waveform, so it is slow for long sequences.
3. Use ids that start with `card_id`. Record the id change as in task 4.2,
   item 3.
4. Write `assets/cards/pns.js`. Move the PNS part of vb `report.js` (the
   block that starts with `if (DATA.pns.reason === null)`), with its view
   buttons. Register it as `"pns"`. Scope the queries to the card section.

**Task 5.3: Tests.** Tier S.

1. `tests/test_pns.py`: copy the vb tests. Put the `write_gradient_asc`
   fixture from vb `tests/conftest.py` at the top of this file.
2. `tests/test_pns_card.py`: copy the vb PNS card tests (`test_pns_data_*`,
   `test_max_envelope_*`, `test_active_samples_*`, `test_report_has_pns_card`,
   `test_report_has_peak_tr_buttons`, `test_report_without_gradients_has_no_pns_chart`).
   Leave out `test_main_with_gradient_asc_over_the_limit`. It tests the vb
   command line. Add a test for `peak_tr_window`.
3. Fill the phase 5 sections of `TESTS.md`.

**Task 5.4: Browser check.** Tier O. The chart, the full and peak-TR
buttons, zoom.

Acceptance: `scripts/check` passes. Parity (except the ids).

---

### Phase 6: gradient limits (new)

Branch: `feat/gradient-limits-card`. Parallel: yes. Tier of the phase: S for
code and tests, O for the specification review. Review: O.

This card is new. It answers: "How near is the sequence to the gradient
limits, on each axis?"

**Task 6.1: Physics.** Tier S.

Write `grad_limits.py` with:

```python
@dataclass(frozen=True)
class HardwareLimits:
    max_grad_mt_per_m: float
    max_slew_t_per_m_per_s: float
    label: str                    # for example "pypulseq system limits"

@dataclass(frozen=True)
class AxisResult:
    peak_mt_per_m: float
    peak_time_s: float
    peak_block: int | None
    max_slew_t_per_m_per_s: float
    slew_block: int | None
    rms_mt_per_m: float           # over the range that was used

@dataclass(frozen=True)
class GradientLimits:
    reason: str | None            # why there is no result, or None
    range_s: tuple[float, float]  # the time range that was used
    axes: dict[str, AxisResult]   # "x", "y", "z"
    vector_peak_mt_per_m: float   # the largest |G| over the three axes together
    vector_peak_time_s: float
    limits: HardwareLimits

def gradient_limits(seq, window: tuple[float, float] | None = None,
                    limits: HardwareLimits | None = None) -> GradientLimits
```

Rules for the computation:

1. Use `seq_utils.iter_blocks` and `seq_utils.gradient_points`. Treat each
   gradient as piecewise linear between its points, as the Pulseq
   specification does.
2. Peak: the largest |amplitude| at a point.
3. Slew: the largest |ΔG/Δt| between neighbouring points of one event.
   Ignore pairs with Δt below `TIME_TOLERANCE`.
4. RMS: the exact integral of G² over each linear piece,
   `Δt · (a² + a·b + b²) / 3`. Divide the sum by the length of the range and
   take the square root. The gradient is zero where there is no event.
5. Vector peak: |G| is convex on a piece where all three axes are linear.
   Its maximum is at a breakpoint. Evaluate |G| at the union of the
   breakpoints of the three axes, with linear interpolation.
6. `window` limits the range. A piece that crosses the window edge is cut at
   the edge.
7. With `limits=None`, use `seq.system.max_grad` and `seq.system.max_slew`,
   converted to mT/m and T/m/s, with the label "pypulseq system limits".
8. Axes are the logical axes of the sequence. The note must say that the
   scanner rotates them. On an oblique slice, one physical axis can get up to
   the vector peak.
9. Memory must not grow with the number of blocks by more than a small
   constant for each block. Process one block at a time.

**Task 6.2: Card.** Tier S.

1. `gradient_limits_card(seqs, window=None, limits=None)`: one table. The
   rows are Gx, Gy, Gz and |G|. The columns are peak (mT/m), percent of the
   limit, max slew (T/m/s), percent of the limit, and RMS (mT/m). With more
   than one file, show one row group for each file.
2. When `window` is given, the card shows RMS over the window and over the
   whole file. For example, the window is one TR.
3. A short note explains the rules in task 6.1 (items 2 to 5 and 8).
4. No chart. `data=None`, `script=None`.

**Task 6.3: Tests.** Tier S.

1. `tests/test_grad_limits.py`, with sequences built in the test file:
   - One trapezoid with known amplitude, rise and flat time: the peak, the
     slew and the RMS equal the hand-computed values.
   - The same trapezoid on x and on y at the same time: the vector peak is
     √2 times the axis peak.
   - A window that cuts a ramp: the RMS equals the hand-computed value.
   - An arbitrary gradient.
   - No gradients: `reason` is set.
   - `limits=None` uses `seq.system`.
2. `tests/test_gradient_limits_card.py`: the rows and percents for one file,
   and the row groups for two files.
3. Fill the phase 6 sections of `TESTS.md`.

**Task 6.4: Review of the formulas.** Tier O. Check the RMS and slew
formulas against a dense numeric sampling of the waveform in a scratch
script. Record the result in the PR description.

Acceptance: `scripts/check` passes. The formulas agree with dense sampling.

---

### Phase 7: sequence diagram and block table

Branch: `feat/diagram-card`. Parallel: yes. This is the largest phase. Tier
of the phase: O for the data design, S for the JavaScript and the tests.
Review: O.

**Task 7.1: Waveform data.** Tier O.

Write `waveforms.py`:

```python
DIAGRAM_POINT_BUDGET = 200_000     # points for all lanes of one file

@dataclass(frozen=True)
class TimeWindow:
    label: str          # the button text
    file_index: int     # the index in the list of sequences
    start_s: float
    end_s: float

def first_adc_window(seqs, file_index=0) -> TimeWindow   # vb "First ADC"
def full_window(seqs, file_index=0) -> TimeWindow        # vb "Full sequence"
def file_lanes(seq, start_s=None, end_s=None) -> list[dict]   # exact lanes
def file_envelope(seq, bins: int) -> list[dict]           # min/max lanes
```

1. `file_lanes` with no range must give the same lanes as vb
   `report/diagram.py::sequence_data` (parity). Move that code here. Keep the
   lane ids, titles, units, colours, domains and ticks. Use
   `seq_utils.gradient_points` and convert to mT/m.
2. With a range, `file_lanes` includes only the blocks that overlap the
   range. It pads each joined lane with zero at the range start and end.
3. `file_envelope` gives, for each line lane, the minimum and the maximum in
   each of `bins` equal time bins, as a line through (bin start, min),
   (bin centre, max) and so on, so that `visiblePoints` draws it correctly.
   For the ADC gate lane, it merges windows closer than one bin. It drops the
   RF phase lane and records that in a lane field `"note"`.
4. `first_adc_window` and `full_window` give the same times as vb
   `first_adc_window_ms` and `duration_ms`.
5. Process one block at a time. Do not build the full point list of a file
   when the file is over the budget. Count the points first.

**Task 7.2: Diagram card.** Tier O for the data layout, S for the HTML.

`diagram_card(seqs, windows, point_budget)`:

1. For each file that has a window: if the file's point count is within
   `point_budget`, send the exact lanes of the whole file one time. The
   windows of that file are views into those lanes, with the extent of the
   whole file. This is the vb behavior (parity for one small file).
2. If the file is over the budget: send exact lanes for each window of that
   file, with the extent equal to the window. A window equal to the whole
   file uses `file_envelope` with `bins = point_budget // (6 * 3)`. The note
   under the chart says that the full-file view shows the minimum and the
   maximum in each of N time bins.
3. One button for each window, in the given order. The first window is the
   initial view. When a button selects a window with other lanes or another
   extent, the card script calls `setWindow`. Otherwise, it calls `setView`.
4. The button text includes the file name when there is more than one file.
5. Copy the diagram HTML from vb `template.html` (the time-window buttons,
   `_zoom_controls`, the chart div and the help text). Use ids that start
   with `card_id`.
6. Write `assets/cards/diagram.js`. Move the diagram part of vb `report.js`
   (`seqChart` and the `data-view` button code). Remove the read of
   `DATA.pns`. Register it as `"diagram"`. Tier S.

**Task 7.3: Block table card.** Tier S.

1. `blocks_card(seqs, windows=None, max_rows=500)`: with no windows, the
   first `max_rows` blocks of each file, with the vb note "First N of M
   blocks" (parity for one file). With windows, one table for each window
   with the blocks that overlap it.
2. Collapsed card (`collapsed=True`), as in vb.
3. The rows come from a helper in `waveforms.py` that is shared with
   `file_lanes`, so that the block list is computed one time.

**Task 7.4: Tests.** Tier S.

1. `tests/test_waveforms.py`: copy `test_spin_echo_lanes`, `test_block_table`,
   `test_zero_phase_rf_and_zero_gradient_are_events` and the
   `report_at_tr` tests from vb. Change them to `tests/synthetic.py`. Add
   tests for a range that cuts a block, for the envelope (min and max of
   each bin are kept, and the ADC windows are merged), and for the point
   count.
2. `tests/test_diagram_card.py`: a small file gives one lane set with the
   extent of the file. A file over the budget (use a small `point_budget`)
   gives one lane set for each window. Two files give the file names in the
   buttons. `test_report_has_zoom_controls_on_each_line_chart` from vb,
   changed to a page with the diagram, spectrum and PNS cards. Do this test
   only if phases 4 and 5 are merged. Otherwise, test the diagram card only.
3. `tests/test_blocks_card.py`: the vb note, and tables for windows.
4. Fill the phase 7 sections of `TESTS.md`.

**Task 7.5: Browser check and scale check.** Tier O.

1. Browser: all window buttons, zoom and pan in each window, the envelope
   view, and the change between files.
2. Scale (not in CI): build the ex-vivo default protocol as in task 4.4.
   Make a diagram card with windows for one TR in each file and a full-file
   window for each file. Record the page size and the time in the PR
   description. The page must be less than 10 MB.

Acceptance: `scripts/check` passes. Parity for one small file. The ex-vivo
page is less than 10 MB.

---

### Phase 8: parity script, usage document, first release

Branch: `docs/usage-and-parity`. Parallel: no. It starts after phases 2 to 7
are merged. Tier of the phase: O, with S workers for the documents.

**Task 8.1: Parity script.** Tier O.

1. Write `scripts/vb_parity.py`. It is not part of `scripts/check` or CI,
   because it needs a vb-pulseq checkout. Run it with:
   `nix develop --command uv run --with-editable <vb checkout> python
   scripts/vb_parity.py`
2. For the vb sequences `vb-spin-echo-5mm-bw260` and
   `vb-spin-echo-3mm-bw100`, it computes the vb data (`sequence_data`,
   `spectrum_data`, `rf_exposure_data`, `pns_data`) and the library data. It
   compares them with a numeric tolerance of `1e-9` relative. It prints one
   line for each card: `ok` or the first difference.
3. It knows the accepted differences: the new DOM ids (tasks 4.2 and 5.2),
   and the `peak_tr_ms` key, which is now a diagram window.
4. The vb checkout must be at commit `3a1c7dd`, or at a later commit where
   the vb report is not changed. The script prints the vb commit.
5. Run it. Record the output in the PR description.

**Task 8.2: Usage document.** Tier S.

1. Write `docs/usage.md`. Include:
   - How a consumer adds the dependency with a git tag.
   - One complete example that makes a page with every library card for one
     sequence.
   - One example for several files with windows.
   - How a consumer adds its own card: a Python function that returns a
     `Card`, and a script passed in `extra_scripts` that calls
     `PulseqReport.registerCard`.
2. Link it from `README.md`.

**Task 8.3: Plan status.** Tier H. Set the status line of this file to
"complete" and list the PR numbers.

**Task 8.4: Tag `v0.1.0`.** Tier O. Ask the user before you push the tag.
The tag is public.

Acceptance: the parity script reports `ok` for each card, with only the
accepted differences. `docs/usage.md` exists. The tag exists after the user
approves it.

## 6. Summary of parallel work

| Wave | Phases | Condition to start |
|---|---|---|
| 1 | 0 | The user approves task 0.1 |
| 2 | 1 | Phase 0 merged |
| 3 | 2, 3, 4, 5, 6, 7 | Phase 1 merged. Each phase is a separate branch from `origin/main` |
| 4 | 8 | Phases 2 to 7 merged |

Tasks inside a phase that can run as parallel workers:

| Phase | Parallel workers |
|---|---|
| 1 | Task 1.1 items 2 and 4, task 1.2, and task 1.4 items 1 and 2 can run at the same time. Task 1.3 is done by the executing agent first. Its test (1.3 item 3) and task 1.4 item 3 follow it. |
| 4 | Task 4.2 (card and JS) can start while the executing agent does task 4.1. The card calls `gradient_spectrum` through its interface only. |
| 7 | Task 7.3 and the JS part of task 7.2 can start after task 7.1 sets the data layout. |
| Others | One worker for the phase is enough. |

## 7. Questions still open

These do not block phases 1 to 7.

1. **The copyright holder in `LICENSE`** (task 0.1). The executing agent asks
   in phase 0.
2. **Scanner and gradient coil for ex-vivo.** This sets `resonances`,
   `scanner_label` and `HardwareLimits` when ex-vivo uses the library. The
   library does not need the answer. Its defaults are the Prisma AS82 bands
   and the pypulseq system limits.
3. **The ex-vivo echo and polarity chart.** It is SVG made in Python. Moving
   it to `laneChart` is part of the later ex-vivo plan, not this plan.
