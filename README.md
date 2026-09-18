# pulseq-reports

`pulseq-reports` is a Python library that writes one self-contained HTML review
report for one or more [Pulseq](https://pulseq.github.io/) sequences. It takes
`pypulseq` `Sequence` objects and knows nothing about a specific sequence. Each
project that uses it supplies its own sequences, selects the cards it wants
(timing check, sequence diagram, gradient spectrum, RF exposure, PNS, gradient
limits), and can add its own cards.

The first release is v0.1.0. For how to add the dependency, build a report and
add your own card, see [docs/usage.md](docs/usage.md). The design is in
[docs/plans/pulseq-reports.md](docs/plans/pulseq-reports.md), and the planned
work is in [TODO.md](TODO.md).

Python 3.12, uv, Node.js and the other tools come from the Nix devShell. To run
all the checks that CI runs:

```
nix develop --command scripts/check
```
