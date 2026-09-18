"""Definitions card: the Pulseq `Definitions` of one or more sequences."""

from collections.abc import Sequence

from pulseq_reports.markup import _table
from pulseq_reports.page import Card
from pulseq_reports.seq_utils import NamedSequence


def _value_cell(value: object) -> object:
    return " ".join(map(str, value)) if isinstance(value, (list, tuple)) else value


def definitions_card(seqs: Sequence[NamedSequence], card_id: str = "definitions") -> Card:
    """The definitions card: the `Definitions` of one or more Pulseq sequences.

    For one sequence, `body_html` is exactly the vb-pulseq two-column definitions table
    (parity): one row for each definition, with list or tuple values joined by spaces.

    For more than one sequence, the table has one row for each definition key (the union
    of the keys of all sequences, in first-seen order) and one column for each sequence,
    headed with the sequence's name. A sequence that does not have a key gets an empty
    cell. When no sequence has any definitions, the body is a muted "No definitions."
    paragraph instead of an empty table.
    """
    if len(seqs) == 1:
        rows = [[k, _value_cell(v)] for k, v in seqs[0].seq.definitions.items()]
        body = _table(["Definition", "Value"], rows)
    else:
        keys: list[str] = []
        seen: set[str] = set()
        for named in seqs:
            for key in named.seq.definitions:
                if key not in seen:
                    seen.add(key)
                    keys.append(key)
        if not keys:
            body = '<p class="muted">No definitions.</p>'
        else:
            headers = ["Definition", *(named.name for named in seqs)]
            rows = [
                [
                    key,
                    *(
                        _value_cell(named.seq.definitions[key])
                        if key in named.seq.definitions
                        else ""
                        for named in seqs
                    ),
                ]
                for key in keys
            ]
            body = _table(headers, rows)
    return Card(id=card_id, title="Definitions", body_html=body, data=None, script=None)
