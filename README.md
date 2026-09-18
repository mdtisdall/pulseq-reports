# pulseq-reports

`pulseq-reports` is a Python library that writes one self-contained HTML review
report for one or more [Pulseq](https://pulseq.github.io/) sequences. It takes
`pypulseq` `Sequence` objects and knows nothing about a specific sequence. Each
project that uses it supplies its own sequences, selects the cards it wants
(timing check, sequence diagram, gradient spectrum, RF exposure, PNS, gradient
limits), and can add its own cards.

The library is under development and has no release yet. The design and the
work that remains are in [docs/plans/pulseq-reports.md](docs/plans/pulseq-reports.md).

Python 3.12, uv, Node.js and the other tools come from the Nix devShell. To run
all the checks that CI runs:

```
nix develop --command scripts/check
```
