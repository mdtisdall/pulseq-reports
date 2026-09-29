"""Block table card: one row for each block of a sequence, in a collapsed table."""

import html
from collections.abc import Sequence

import pypulseq as pp

from ..markup import html_table
from ..page import Card
from ..waveforms import TimeWindow, _check_windows, block_rows


def _note(total: int, max_rows: int) -> str:
    """The vb-pulseq "First N of M blocks." note, or "" when nothing was cut."""
    return f'<p class="muted">First {max_rows} of {total} blocks.</p>' if total > max_rows else ""


def _rows_table(rows: list[dict]) -> str:
    return html_table(
        ["Block", "Start (ms)", "Duration (ms)", "Events"],
        [[r["block"], f"{r['start_ms']:g}", f"{r['duration_ms']:g}", r["events"]] for r in rows],
    )


def _table(seq, max_rows: int, start_s: float | None = None, end_s: float | None = None) -> str:
    """The note and the table for the blocks of `seq` in [start_s, end_s] (the whole
    sequence by default), at most `max_rows` of them. This is vb-pulseq's own
    `__BLOCK_NOTE__` + "\\n" + `__BLOCKS__` text (parity, no range)."""
    rows, total = block_rows(seq, start_s=start_s, end_s=end_s, max_rows=max_rows)
    return f"{_note(total, max_rows)}\n{_rows_table(rows)}"


def blocks_card(
    seq: pp.Sequence,
    *,
    windows: Sequence[TimeWindow] | None = None,
    max_rows: int = 500,
    card_id: str = "blocks",
) -> Card:
    """The "Blocks (table view)" card: a collapsed `<details>` card (as in vb-pulseq)
    with a table of block rows (block id, start (ms), duration (ms), events).

    With `windows=None` (the default), the card has the first `max_rows` blocks, with
    the vb-pulseq "First N of M blocks." note when the sequence has more blocks than
    that. `body_html` is exactly vb-pulseq's own block table HTML (parity).

    With `windows` given, the card has one table for each window, with the blocks that
    overlap it (`waveforms.block_rows` with the window's `start_s` and `end_s`), headed by
    an `<h3>` with the window's label.

    No chart: `data=None` and `script=None`.

    Raises `ValueError` for a window that is not inside the sequence or that does not
    end after its start.
    """
    if windows is None:
        body = _table(seq, max_rows)
    else:
        _check_windows(seq, windows)
        body = "\n\n".join(
            f"<h3>{html.escape(w.label)}</h3>\n{_table(seq, max_rows, w.start_s, w.end_s)}"
            for w in windows
        )
    return Card(
        id=card_id,
        title="Blocks (table view)",
        body_html=body,
        data=None,
        script=None,
        collapsed=True,
    )
