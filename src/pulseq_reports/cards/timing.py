"""Timing check card: pypulseq's own timing check for one or more sequences."""

import html
from collections.abc import Sequence

import pypulseq as pp

from pulseq_reports.markup import html_table
from pulseq_reports.page import Card
from pulseq_reports.seq_utils import NamedSequence


def timing_errors(seq: pp.Sequence) -> list[dict]:
    """Errors from `Sequence.check_timing`, one dict for each."""
    ok, report = seq.check_timing()
    errors = [dict(vars(r)) if hasattr(r, "__dict__") else {"message": str(r)} for r in report]
    if not ok and not errors:
        errors = [{"error_type": "TIMING_CHECK_FAILED"}]
    return errors


_HEADERS = ["Block", "Event", "Field", "Error", "Value (s)", "Limits (s)"]
_MAIN_KEYS = ("block", "event", "field", "error_type", "value", "message")


def _error_row(e: dict) -> list:
    limits = ", ".join(
        f"{k} = {v:g}" if isinstance(v, float) else f"{k} = {v}"
        for k, v in e.items()
        if k not in _MAIN_KEYS
    )
    value = e.get("value", "")
    return [
        e.get("block", ""),
        e.get("event", ""),
        e.get("field", ""),
        e.get("error_type", e.get("message", "")),
        f"{value:g}" if isinstance(value, float) else value,
        limits,
    ]


def _timing_html(errors: list[dict], name: str | None = None) -> str:
    """The timing check body of one sequence: a status paragraph, and an error table
    when there are errors. With `name`, the status line starts with the file name
    (HTML-escaped)."""
    prefix = "" if name is None else f"{html.escape(name)}: "
    if not errors:
        return (
            f'<p class="status good"><span aria-hidden="true">✓</span> {prefix}'
            "Timing check passed: pypulseq reported no errors.</p>"
        )
    head = (
        f'<p class="status bad"><span aria-hidden="true">✕</span> {prefix}'
        f"Timing check failed: {len(errors)} error{'s' if len(errors) != 1 else ''}.</p>"
    )
    return head + html_table(_HEADERS, [_error_row(e) for e in errors])


def timing_card(seqs: Sequence[NamedSequence], card_id: str = "timing") -> Card:
    """The timing check card: pypulseq's `check_timing` result for each sequence.

    For one sequence, `body_html` is exactly the vb-pulseq timing check HTML: a status
    paragraph, and an error table when there are errors (parity).

    For more than one sequence, the body has one status line for each file, naming the
    file (HTML-escaped), with the error table placed under each file that has errors.
    """
    if len(seqs) == 1:
        body = _timing_html(timing_errors(seqs[0].seq))
    else:
        body = "\n".join(_timing_html(timing_errors(named.seq), named.name) for named in seqs)
    return Card(id=card_id, title="Timing check", body_html=body, data=None, script=None)
