# pulseq-reports

`pulseq-reports` is a Python library that writes one self-contained HTML
review report for one or more [Pulseq](https://pulseq.github.io/) sequences.
You give it `pypulseq` `Sequence` objects. It gives you one `.html` file that
shows the timing check, the hardware limits, the predicted peripheral nerve
stimulation (PNS), the RF exposure, the gradient spectrum and an interactive
sequence diagram.

**[Open the example report](https://mdtisdall.github.io/pulseq-reports/examples/gre.html)**:
a simple 2D gradient echo (GRE) sequence, with every card of the library.

## What it is for

You write a Pulseq sequence, in pypulseq or in MATLAB Pulseq. Before you take
it to the scanner, you want to know:

- Does the timing pass the raster and dead-time checks?
- How near are the gradients to the amplitude and slew-rate limits?
- What PNS does the SAFE model predict, and where in the sequence is the peak?
- How much RF does it transmit (peak B1, B1+rms)?
- Does the gradient spectrum put energy on the acoustic resonances of the
  gradient coil?
- What do the waveforms look like, at the start, at the PNS peak, and across
  the whole sequence?

pypulseq can answer most of these questions one at a time: `check_timing`,
`test_report`, `calculate_pns`, `calculate_gradient_spectrum` and `plot` give
text or a matplotlib figure in your own Python session. `pulseq-reports` puts
the answers together on one page that other people can open:

- **One file.** The CSS, the JavaScript and the data are all in the `.html`
  file. It needs no server and no Python to view: open it in a browser, send
  it to a colleague, attach it to a pull request, or keep it next to the
  `.seq` file.
- **Interactive.** Zoom and pan the sequence diagram from one gradient ramp
  out to the whole sequence, and hover to read the values. This works for
  sequences of up to 10^7 blocks.
- **Scripted.** You build the report in the same code that builds the
  sequence, so each change to the sequence can give a new report, for example
  in CI.
- **Your choice of cards.** Each project selects the cards that it wants, and
  can write its own cards.

Some ways to use it:

- Review your own sequence before a scan session.
- Review a sequence from someone else, from the report alone.
- Show all the files of a multi-file acquisition on one page.
- Keep a record of what was scanned: commit the report with the code that
  made the sequence.

The library knows nothing about a specific sequence type. It reads any
`pypulseq` `Sequence`, including one that `Sequence.read` loads from a `.seq`
file written by MATLAB Pulseq.

## The example report

[`docs/examples/gre.html`](docs/examples/gre.html) is the report for a 64 × 64
GRE with a sinc slice-selective excitation, RF spoiling and gradient
spoiling (TR 12 ms, TE 5 ms). The sequence is the same as pypulseq's own
`write_gre.py` example. GitHub Pages serves it at
<https://mdtisdall.github.io/pulseq-reports/examples/gre.html>. You can also
download the file and open it in a browser.

Things to try in the example:

- In the sequence diagram, click **Full sequence**, then drag across the chart
  to zoom in on one TR. Hover to read the RF, ADC, gradient, |G| and PNS
  values.
- Click **Peak-PNS TR** to go to the TR with the highest predicted PNS.
- Click **RF**, **ADC**, **Gradients** or **PNS** to hide or show a group of
  lanes.
- Open **Blocks (table view)** at the end of the page for the block-by-block
  table.

The example also shows the kind of issue that a report finds. The timing
check passes and no logical gradient axis is over its limit. But the x and z
spoiler gradients both play at the full 28 mT/m at the same time, so the
gradient limits card shows |G|, the magnitude of the gradient vector, at
39.7 mT/m: 142 % of the limit of one axis. On an oblique slice, the scanner
rotates the logical axes onto the physical ones, and one physical axis can
then need more than the hardware has. The gradient spectrum card gives the
largest value in each of the two acoustic resonance bands of a Prisma
gradient coil: here, about a quarter of the peak of the spectrum.

[`examples/gre_report.py`](examples/gre_report.py) builds the sequence and the
report. To build the report again, for example after a change to the library:

```bash
nix develop --command uv run python examples/gre_report.py
```

The page's subtitle gives the `pulseq-reports` version that built it.

## The cards

| Card | Shows |
|---|---|
| Timing check | pypulseq's own timing check, and a table of errors when there are errors. |
| RF exposure | Peak B1, the B1² integral and B1+rms of each file, and of all the files together when there are several. |
| Sequence diagram | RF magnitude and phase, the ADC, Gx, Gy, Gz, \|G\| and (optional) PNS against time, with zoom, pan and buttons for named time windows. |
| Gradient spectrum | The spectrum of each gradient axis, against the acoustic resonance bands of a gradient coil. |
| PNS prediction | The SAFE-model PNS peak of each axis and of all axes, with pypulseq's example hardware or the gradient `.asc` file of your scanner. |
| Gradient limits | Peak amplitude, peak slew rate and RMS of each axis and of \|G\|, as a percent of the hardware limits. |
| Definitions | The `[DEFINITIONS]` of each sequence. |
| Blocks | A block-by-block table: start, duration and events. |

A project can add its own card: a Python function that returns a `page.Card`,
and a JavaScript file that draws it. See [docs/usage.md](docs/usage.md),
section 4.

## Quick start

Add the dependency by git URL and tag, for example in `pyproject.toml`:

```toml
[project]
dependencies = [
    "pulseq-reports @ git+https://github.com/mdtisdall/pulseq-reports@v0.2.0rc1",
]
```

Then build a page:

```python
import pypulseq as pp

from pulseq_reports.cards.diagram import diagram_card
from pulseq_reports.cards.gradient_limits import gradient_limits_card
from pulseq_reports.cards.rf_exposure import rf_exposure_card
from pulseq_reports.cards.timing import timing_card
from pulseq_reports.page import write_page
from pulseq_reports.seq_utils import NamedSequence
from pulseq_reports.waveforms import first_adc_window, full_window

seq = pp.Sequence()
seq.read("my_scan.seq")  # or use the Sequence that your code builds
seqs = [NamedSequence(name="my_scan.seq", seq=seq)]

cards = [
    timing_card(seqs),
    rf_exposure_card(seqs),
    diagram_card(seqs, [first_adc_window(seqs), full_window(seqs)]),
    gradient_limits_card(seqs),
]
write_page("my_scan.html", title="my_scan.seq", subtitle="Before the scan session", cards=cards)
```

Open `my_scan.html` in a browser. For every card, several files on one
page, time windows and your own cards, see [docs/usage.md](docs/usage.md).
The PNS card and the diagram's PNS lane need a pypulseq fork until a pypulseq
release has the changes that they use; docs/usage.md, section 1, tells you
how to pin it.

## What a report does not do

- **It is not a safety check.** Every value comes from the sequence as
  written. The scanner's own checks decide: its SAR model, its PNS monitor,
  and its gradient limits after the rotation to the slice orientation.
- **PNS needs your hardware.** Without the gradient `.asc` file of your
  scanner, the PNS prediction uses pypulseq's example hardware, which is not a
  real scanner. The resonance bands of the gradient spectrum card are
  published values for one coil (MAGNETOM Prisma, AS82) unless you give
  others.
- **No rotation extension yet.** The gradient cards refuse a sequence that
  uses the Pulseq rotation extension. See [TODO.md](TODO.md).

To view a report, you need a browser with `DecompressionStream` for gzip:
Chrome or Edge 80, Firefox 113, Safari 16.4, or later.

## Status

The first release is v0.1.0. v0.2.0rc1 is a release candidate for 0.2.0:
every card for files of up to 10^7 blocks, and the PNS and |G| lanes of the
sequence diagram. The design is in
[docs/plans/pulseq-reports.md](docs/plans/pulseq-reports.md), the planned work
is in [TODO.md](TODO.md), and each test that CI runs is in
[TESTS.md](TESTS.md).

## Development

Python 3.12, uv, Node.js and the other tools come from the Nix devShell. To
run all the checks that CI runs:

```bash
nix develop --command scripts/check
```

## License

MIT. See [LICENSE](LICENSE).
