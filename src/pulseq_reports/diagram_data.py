"""The compact block and event tables that the diagram card sends to the browser.

`diagram_tables` reads `seq.block_events` and `seq.block_durations` through
`seq_index.sequence_index`, in play order, without calling `get_block`. Each unique
RF, gradient and ADC event is expanded one time only, by `seq_index.rf_events`,
`grad_events` and `adc_events`, on the first block that uses it, with the block cache
off (never once for each block). The offsets and values it stores are exactly those of
`waveforms._block_events`. `encode_tables` and `decode_tables` are the gzip+base64 wire
form of the tables and its inverse. `lane_meta` gives the lane titles, colors, domains,
ticks and tick labels of `file_lanes`, computed from the tables instead of the expanded
points, so it costs O(N) and O(unique events), not O(the file's points).
"""

import base64
import gzip
import math

import numpy as np
import pypulseq as pp

from .seq_index import _index_dtype, adc_events, grad_events, rf_events, sequence_index
from .seq_utils import GAMMA, gradient_offsets
from .waveforms import _AXES, _rf_offsets, _value_domain

CHECKPOINT_BLOCKS = 1024


class _Pool:
    """Distinct float64 arrays, each kept one time, matched by their exact bytes. `add`
    returns the start position of an array in the pool, reusing the position of an
    equal array already there."""

    def __init__(self) -> None:
        self._position: dict[bytes, int] = {}
        self._chunks: list[np.ndarray] = []
        self._length = 0

    def add(self, values) -> int:
        arr = np.asarray(values, dtype=np.float64)
        key = arr.tobytes()
        pos = self._position.get(key)
        if pos is not None:
            return pos
        pos = self._length
        self._position[key] = pos
        self._chunks.append(arr)
        self._length += arr.size
        return pos

    def array(self) -> np.ndarray:
        if not self._chunks:
            return np.empty(0, dtype=np.float64)
        return np.concatenate(self._chunks)


def diagram_tables(seq: pp.Sequence) -> dict[str, np.ndarray]:
    """The block table and the RF, gradient and ADC event tables of `seq` (section 4.2
    of `docs/plans/diagram-event-table.md`), as numpy arrays with the dtypes it lists.

    Builds `seq_index.sequence_index(seq)` and reads its columns: the index itself
    reads `seq.block_events` and `seq.block_durations` in play order, without calling
    `get_block`. `gx`, `gy` and `gz` share one dense gradient index space in the index
    (as `seq.grad_library` does), but each is cast here to its own narrowest dtype.
    Each unique RF, gradient and ADC event is read one time, by
    `seq_index.rf_events`/`grad_events`/`adc_events`, with the block cache off. The
    checkpoints are the index's own block-start times (`start_s`, the sequential sum
    of the durations), sampled every `CHECKPOINT_BLOCKS` blocks.
    """
    index = sequence_index(seq)
    n = index.num_blocks

    # The unique block durations, in the order of their first appearance in play
    # order, matched by float equality (as the per-block dict of the former loop
    # matched them): np.unique's sorted unique values, reordered by each value's
    # first position, with the same reordering applied to the per-block index.
    unique_durations, first_pos, inverse = np.unique(
        index.duration_s, return_index=True, return_inverse=True
    )
    order = np.argsort(first_pos, kind="stable")
    durations = unique_durations[order]
    rank = np.empty(order.size, dtype=np.int64)
    rank[order] = np.arange(order.size)
    duration_index = rank[inverse].astype(_index_dtype(durations.size - 1 if durations.size else 0))

    # A copy, not a view: the index is kept for the sequence (sequence_index).
    checkpoints = index.start_s[::CHECKPOINT_BLOCKS].copy()

    rf_delay: list[float] = []
    rf_mag_n: list[int] = []
    rf_mag_offset_at: list[int] = []
    rf_mag_at: list[int] = []
    rf_phase_n: list[int] = []
    rf_phase_offset_at: list[int] = []
    rf_phase_at: list[int] = []
    rf_mag_offset_pool = _Pool()
    rf_mag_pool = _Pool()
    rf_phase_offset_pool = _Pool()
    rf_phase_pool = _Pool()
    for _, rf in rf_events(seq, index):
        delay, mag_offsets, mag, phase_offsets, phase = _rf_offsets(rf)
        rf_delay.append(float(delay))
        rf_mag_n.append(mag_offsets.size)
        rf_mag_offset_at.append(rf_mag_offset_pool.add(mag_offsets))
        rf_mag_at.append(rf_mag_pool.add(mag))
        rf_phase_n.append(phase_offsets.size)
        rf_phase_offset_at.append(rf_phase_offset_pool.add(phase_offsets))
        rf_phase_at.append(rf_phase_pool.add(phase))

    grad_delay: list[float] = []
    grad_n: list[int] = []
    grad_offset_at: list[int] = []
    grad_at: list[int] = []
    grad_offset_pool = _Pool()
    grad_value_pool = _Pool()
    for _, g in grad_events(seq, index):
        delay, offsets, amp = gradient_offsets(g)
        grad_delay.append(float(delay))
        grad_n.append(offsets.size)
        grad_offset_at.append(grad_offset_pool.add(offsets))
        grad_at.append(grad_value_pool.add(amp / GAMMA * 1e3))

    adc_delay: list[float] = []
    adc_length: list[float] = []
    for _, adc in adc_events(seq, index):
        adc_delay.append(float(adc.delay))
        adc_length.append(float(adc.num_samples * adc.dwell))

    return {
        "duration_index": duration_index,
        "durations": durations,
        "checkpoints": checkpoints,
        "rf": index.rf.astype(_index_dtype(index.rf_first.size)),
        "gx": index.gx.astype(_index_dtype(int(index.gx.max()) if n else 0)),
        "gy": index.gy.astype(_index_dtype(int(index.gy.max()) if n else 0)),
        "gz": index.gz.astype(_index_dtype(int(index.gz.max()) if n else 0)),
        "adc": index.adc.astype(_index_dtype(index.adc_first.size)),
        "rf_delay": np.asarray(rf_delay, dtype=np.float64),
        "rf_mag_n": np.asarray(rf_mag_n, dtype=np.uint32),
        "rf_mag_offset_at": np.asarray(rf_mag_offset_at, dtype=np.uint32),
        "rf_mag_at": np.asarray(rf_mag_at, dtype=np.uint32),
        "rf_mag_offset": rf_mag_offset_pool.array(),
        "rf_mag": rf_mag_pool.array(),
        "rf_phase_n": np.asarray(rf_phase_n, dtype=np.uint32),
        "rf_phase_offset_at": np.asarray(rf_phase_offset_at, dtype=np.uint32),
        "rf_phase_at": np.asarray(rf_phase_at, dtype=np.uint32),
        "rf_phase_offset": rf_phase_offset_pool.array(),
        "rf_phase": rf_phase_pool.array(),
        "grad_delay": np.asarray(grad_delay, dtype=np.float64),
        "grad_n": np.asarray(grad_n, dtype=np.uint32),
        "grad_offset_at": np.asarray(grad_offset_at, dtype=np.uint32),
        "grad_at": np.asarray(grad_at, dtype=np.uint32),
        "grad_offset": grad_offset_pool.array(),
        "grad_value": grad_value_pool.array(),
        "adc_delay": np.asarray(adc_delay, dtype=np.float64),
        "adc_length": np.asarray(adc_length, dtype=np.float64),
    }


def encode_tables(tables: dict[str, np.ndarray]) -> dict[str, dict]:
    """Each table as `{"dtype", "length", "data"}`, where `data` is the little-endian
    bytes of the array, gzipped (level 6) and base64-encoded. Each table is compressed
    separately, so each decompressed buffer is aligned for its typed array."""
    encoded: dict[str, dict] = {}
    for name, arr in tables.items():
        arr = np.asarray(arr)
        little = arr.astype(arr.dtype.newbyteorder("<"), copy=False)
        compressed = gzip.compress(little.tobytes(), compresslevel=6)
        encoded[name] = {
            "dtype": arr.dtype.name,
            "length": int(arr.size),
            "data": base64.b64encode(compressed).decode("ascii"),
        }
    return encoded


def decode_tables(encoded: dict[str, dict]) -> dict[str, np.ndarray]:
    """The inverse of `encode_tables`: the tables as numpy arrays with their original
    dtypes."""
    tables: dict[str, np.ndarray] = {}
    for name, meta in encoded.items():
        raw = gzip.decompress(base64.b64decode(meta["data"]))
        dtype = np.dtype(meta["dtype"]).newbyteorder("<")
        tables[name] = np.frombuffer(raw, dtype=dtype, count=meta["length"]).copy()
    return tables


def _rounded_peak(values: np.ndarray, digits: int = 4) -> float:
    """The largest absolute value of `values`, each rounded as `markup._points` rounds a
    lane value (`round(float(v), digits)`)."""
    if values.size == 0:
        return 0.0
    return max(abs(round(float(v), digits)) for v in values)


def _grad_event_peaks(tables: dict[str, np.ndarray]) -> np.ndarray:
    """The rounded peak (`_rounded_peak`) of each unique gradient event's own value
    array, in dense-index order."""
    n_events = tables["grad_n"].size
    peaks = np.empty(n_events, dtype=np.float64)
    pool = tables["grad_value"]
    at = tables["grad_at"]
    lengths = tables["grad_n"]
    for k in range(n_events):
        start = int(at[k])
        length = int(lengths[k])
        peaks[k] = _rounded_peak(pool[start : start + length])
    return peaks


def lane_meta(seq: pp.Sequence, tables: dict[str, np.ndarray] | None = None) -> list[dict]:
    """`waveforms.file_lanes(seq)` without the `segments` and `windows` keys: the six
    lane titles, colors, domains, ticks and tick labels, in `file_lanes` order.

    Does not call `file_lanes`: that builds every point of the file, which costs too
    much memory at 10^7 blocks. Each lane's peak comes from the per-event values of
    `diagram_tables`, rounded as `markup._points` rounds them, because `_value_lane`
    takes its peak from the rounded points. `empty` comes from the event counts.

    Pass `tables` (the result of `diagram_tables(seq)`) when the caller already has
    them, so that a caller that wants both the tables and the lanes of one file builds
    the tables one time. `diagram_tables` is the dominant cost of a large file.
    """
    if tables is None:
        tables = diagram_tables(seq)
    has_rf = tables["rf_delay"].size > 0
    has_adc = tables["adc_delay"].size > 0

    rf_mag_peak = _rounded_peak(tables["rf_mag"])
    rf_mag_domain, rf_mag_ticks, rf_mag_labels = _value_domain(rf_mag_peak, symmetric=False)

    lanes = [
        {
            "id": "rf_mag",
            "title": "RF |B1|",
            "unit": "µT",
            "color": "rf",
            "kind": "line",
            "domain": rf_mag_domain,
            "ticks": rf_mag_ticks,
            "tick_labels": rf_mag_labels,
            "empty": not has_rf,
            "fill": 0.0,
        },
        {
            "id": "rf_phase",
            "title": "RF phase",
            "unit": "rad",
            "color": "rf",
            "kind": "line",
            "domain": [-1.1 * math.pi, 1.1 * math.pi],
            "ticks": [-math.pi, 0.0, math.pi],
            "tick_labels": ["−π", "0", "π"],
            "empty": not has_rf,
            "fill": None,
        },
        {
            "id": "adc",
            "title": "ADC",
            "unit": "",
            "color": "adc",
            "kind": "gate",
            "domain": [0.0, 1.25],
            "ticks": [0.0, 1.0],
            "tick_labels": ["off", "on"],
            "empty": not has_adc,
        },
    ]

    event_peaks = _grad_event_peaks(tables)
    for axis in _AXES:
        used = np.unique(tables[axis])
        used = used[used > 0]
        if used.size:
            peak = float(np.max(event_peaks[used.astype(np.int64) - 1]))
        else:
            peak = 0.0
        domain, ticks, labels = _value_domain(peak, symmetric=True)
        lanes.append(
            {
                "id": axis,
                "title": f"G{axis[1]}",
                "unit": "mT/m",
                "color": axis,
                "kind": "line",
                "domain": domain,
                "ticks": ticks,
                "tick_labels": labels,
                "empty": used.size == 0,
                "fill": 0.0,
            }
        )
    return lanes
