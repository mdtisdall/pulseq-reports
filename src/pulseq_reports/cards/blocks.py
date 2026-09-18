"""Block table card: one row for each block of a sequence, in a collapsed table."""

import html
from collections.abc import Sequence

from ..markup import _table
from ..page import Card
from ..seq_utils import NamedSequence
from ..waveforms import TimeWindow, block_rows


def _note(total: int, max_rows: int) -> str:
    """The vb-pulseq "First N of M blocks." note, or "" when nothing was cut."""
    return f'<p class="muted">First {max_rows} of {total} blocks.</p>' if total > max_rows else ""


def _rows_table(rows: list[dict]) -> str:
    return _table(
        ["Block", "Start (ms)", "Duration (ms)", "Events"],
        [[r["block"], f"{r['start_ms']:g}", f"{r['duration_ms']:g}", r["events"]] for r in rows],
    )


def _file_table(
    seq, max_rows: int, start_s: float | None = None, end_s: float | None = None
) -> str:
    """The note and the table for the blocks of `seq` in [start_s, end_s] (the whole
    sequence by default), at most `max_rows` of them. This is vb-pulseq's own
    `__BLOCK_NOTE__` + "\\n" + `__BLOCKS__` text (parity for one file, no range)."""
    rows, total = block_rows(seq, start_s, end_s, max_rows)
    return f"{_note(total, max_rows)}\n{_rows_table(rows)}"


def blocks_card(
    seqs: Sequence[NamedSequence],
    windows: Sequence[TimeWindow] | None = None,
    max_rows: int = 500,
    card_id: str = "blocks",
) -> Card:
    """The "Blocks (table view)" card: a collapsed `<details>` card (as in vb-pulseq)
    with a table of block rows (block id, start (ms), duration (ms), events).

    With `windows=None` (the default), the card has the first `max_rows` blocks of each
    file, with the vb-pulseq "First N of M blocks." note when a file has more blocks
    than that. For one file, `body_html` is exactly vb-pulseq's own block table HTML
    (parity). With more than one file, each file's table is headed by an `<h3>` with
    the file's escaped name.

    With `windows` given, the card has one table for each window, with the blocks that
    overlap it (`waveforms.block_rows(seq, w.start_s, w.end_s, max_rows)`), headed by
    an `<h3>` with the window's label, and the file name too when there is more than
    one file in `seqs` (the same "name: label" format as `cards.diagram.diagram_card`).

    No chart: `data=None` and `script=None`.
    """
    multi = len(seqs) > 1
    parts: list[str] = []
    if windows is None:
        for named in seqs:
            table = _file_table(named.seq, max_rows)
            parts.append(f"<h3>{html.escape(named.name)}</h3>\n{table}" if multi else table)
    else:
        for w in windows:
            named = seqs[w.file_index]
            label = w.label if not multi else f"{named.name}: {w.label}"
            table = _file_table(named.seq, max_rows, w.start_s, w.end_s)
            parts.append(f"<h3>{html.escape(label)}</h3>\n{table}")
    body = "\n\n".join(parts)
    return Card(
        id=card_id,
        title="Blocks (table view)",
        body_html=body,
        data=None,
        script=None,
        collapsed=True,
    )
