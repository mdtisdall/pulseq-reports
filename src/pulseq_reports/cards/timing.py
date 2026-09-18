"""Timing check card: pypulseq's own timing check for one or more sequences."""

import html
from collections.abc import Sequence

import pypulseq as pp

from pulseq_reports.page import Card
from pulseq_reports.seq_utils import NamedSequence


def timing_errors(seq: pp.Sequence) -> list[dict]:
    """Errors from `Sequence.check_timing`, one dict for each."""
    ok, report = seq.check_timing()
    errors = [dict(vars(r)) if hasattr(r, "__dict__") else {"message": str(r)} for r in report]
    if not ok and not errors:
        errors = [{"error_type": "TIMING_CHECK_FAILED"}]
    return errors


def _error_table_html(errors: list[dict]) -> str:
    main_keys = ("block", "event", "field", "error_type", "value", "message")
    rows = []
    for e in errors:
        limits = ", ".join(
            f"{k} = {v:g}" if isinstance(v, float) else f"{k} = {v}"
            for k, v in e.items()
            if k not in main_keys
        )
        value = e.get("value", "")
        cells = [
            e.get("block", ""),
            e.get("event", ""),
            e.get("field", ""),
            e.get("error_type", e.get("message", "")),
            f"{value:g}" if isinstance(value, float) else value,
            limits,
        ]
        rows.append("<tr>" + "".join(f"<td>{html.escape(str(c))}</td>" for c in cells) + "</tr>")
    return (
        '<div class="scroll"><table><thead><tr><th>Block</th><th>Event</th><th>Field</th>'
        "<th>Error</th><th>Value (s)</th><th>Limits (s)</th></tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table></div>"
    )


def _timing_html(errors: list[dict]) -> str:
    """The timing check body for one sequence: a status paragraph, and an error table
    when there are errors. The output is the same as vb-pulseq `_timing_html`."""
    if not errors:
        return (
            '<p class="status good"><span aria-hidden="true">✓</span> '
            "Timing check passed: pypulseq reported no errors.</p>"
        )
    head = (
        f'<p class="status bad"><span aria-hidden="true">✕</span> '
        f"Timing check failed: {len(errors)} error{'s' if len(errors) != 1 else ''}.</p>"
    )
    return head + _error_table_html(errors)


def _status_line(name: str, errors: list[dict]) -> str:
    """One status paragraph naming `name` (HTML-escaped), followed by the error table
    when `errors` is not empty."""
    name = html.escape(name)
    if not errors:
        return (
            f'<p class="status good"><span aria-hidden="true">✓</span> {name}: '
            "Timing check passed: pypulseq reported no errors.</p>"
        )
    head = (
        f'<p class="status bad"><span aria-hidden="true">✕</span> {name}: '
        f"Timing check failed: {len(errors)} error{'s' if len(errors) != 1 else ''}.</p>"
    )
    return head + _error_table_html(errors)


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
        body = "\n".join(_status_line(named.name, timing_errors(named.seq)) for named in seqs)
    return Card(id=card_id, title="Timing check", body_html=body, data=None, script=None)
