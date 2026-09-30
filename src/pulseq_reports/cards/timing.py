"""Timing check card: pypulseq's own timing check for a sequence."""

import pypulseq as pp

from pulseq_reports.markup import html_table
from pulseq_reports.page import Card, Check
from pulseq_reports.registry import CardSpec, ReportContext


def _timing_errors(seq: pp.Sequence) -> list[dict]:
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


def _timing_html(errors: list[dict]) -> str:
    """The timing check body: a status paragraph, and an error table when there are
    errors."""
    if not errors:
        return (
            '<p class="status good"><span aria-hidden="true">✓</span> '
            "Timing check passed: pypulseq reported no errors.</p>"
        )
    head = (
        '<p class="status bad"><span aria-hidden="true">✕</span> '
        f"Timing check failed: {len(errors)} error{'s' if len(errors) != 1 else ''}.</p>"
    )
    return head + html_table(_HEADERS, [_error_row(e) for e in errors])


def timing_card(seq: pp.Sequence, *, card_id: str = "timing") -> Card:
    """The timing check card: pypulseq's `check_timing` result for the sequence.

    `body_html` is exactly the vb-pulseq timing check HTML: a status paragraph, and an
    error table when there are errors (parity).

    The card has one check, `timing`, which fails when pypulseq's timing check gives errors.
    """
    errors = _timing_errors(seq)
    body = _timing_html(errors)
    check = Check(
        name="timing",
        passed=not errors,
        message=(
            "pypulseq's timing check gave no errors."
            if not errors
            else f"pypulseq's timing check gave {len(errors)} "
            f"error{'s' if len(errors) != 1 else ''}."
        ),
    )
    return Card(
        id=card_id, title="Timing check", body_html=body, data=None, script=None, checks=(check,)
    )


def _build(ctx: ReportContext) -> Card:
    return timing_card(ctx.seq, card_id=SPEC.name)


SPEC = CardSpec("timing", 10, _build)
