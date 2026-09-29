"""Definitions card: the Pulseq `Definitions` of a sequence."""

import pypulseq as pp

from pulseq_reports.markup import html_table
from pulseq_reports.page import Card


def _value_cell(value: object) -> object:
    return " ".join(map(str, value)) if isinstance(value, (list, tuple)) else value


def definitions_card(seq: pp.Sequence, *, card_id: str = "definitions") -> Card:
    """The definitions card: the `Definitions` of a Pulseq sequence.

    `body_html` is exactly the vb-pulseq two-column definitions table (parity): one row
    for each definition, with list or tuple values joined by spaces.
    """
    rows = [[k, _value_cell(v)] for k, v in seq.definitions.items()]
    body = html_table(["Definition", "Value"], rows)
    return Card(id=card_id, title="Definitions", body_html=body, data=None, script=None)
