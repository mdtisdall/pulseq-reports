"""Gradient spectrum card: the axis and RSS spectra of a sequence."""

import html

import pypulseq as pp

from pulseq_reports.extensions import refuse_rotations
from pulseq_reports.grad_spectrum import (
    FFT_WINDOW_S,
    MAX_FREQUENCY_HZ,
    GradientSpectrum,
    gradient_spectrum,
)
from pulseq_reports.markup import (
    _AXIS_COLOR,
    Lane,
    _sig,
    fmt,
    lanes_json,
    zoom_controls,
)
from pulseq_reports.page import Card, card_asset
from pulseq_reports.registry import CardSpec, ReportContext

_SPECTRUM_UNIT = "mT/m/√Hz"
_SPECTRUM_DB_FLOOR = -80  # the lowest value drawn on the spectrum's dB scale


def _spectrum_data(s: GradientSpectrum) -> dict:
    """`GradientSpectrum` as JSON-ready data, in Hz and mT/m/√Hz. All lanes share the RSS
    lane's value range."""
    out = {
        "reason": s.reason,
        "max_frequency_hz": MAX_FREQUENCY_HZ,
        "db_floor": _SPECTRUM_DB_FLOOR,
        "resonances": [
            {"frequency_hz": frequency_hz, "bandwidth_hz": bandwidth_hz}
            for frequency_hz, bandwidth_hz in s.resonances
        ],
        "lanes": [],
        "bands": [],
    }
    if s.reason is not None:
        return out

    peak = float(s.rss.max())
    if peak > 0:
        domain, ticks, labels = [0.0, 1.1 * peak], [0.0, peak], ["0", fmt(peak)]
    else:
        domain, ticks, labels = [0.0, 1.0], [0.0], ["0"]
    series = [(f"g{a}", f"G{a}", _AXIS_COLOR[a], s.axes[a]) for a in "xyz"]
    series.append(("rss", "RSS", "ink-2", s.rss))
    out["lanes"] = lanes_json(
        [
            Lane(
                id=lane_id,
                title=title,
                unit=_SPECTRUM_UNIT,
                color=color,
                segments=[
                    [[round(float(f), 3), _sig(float(v))] for f, v in zip(s.frequency_hz, values)]
                ],
                domain=domain,
                ticks=ticks,
                tick_labels=labels,
            )
            for lane_id, title, color, values in series
        ]
    )
    out["bands"] = [
        {
            "low_hz": b.resonance[0] - b.resonance[1] / 2,
            "high_hz": b.resonance[0] + b.resonance[1] / 2,
            "peak": _sig(b.peak),
            "peak_frequency_hz": round(b.frequency_hz, 3),
            "relative": round(b.relative, 4),
        }
        for b in s.band_peaks
    ]
    return out


def _spectrum_html(spectrum: dict, card_id: str) -> str:
    """The body of the "Gradient spectrum" card: the chart and its explanation, or a note
    that there is no spectrum. `card_id` is used to build the chart element ids
    (`{card_id}-chart`, `{card_id}-diagram`, `{card_id}-tip`)."""
    if spectrum["reason"] is not None:
        return f'<p class="muted">No gradient spectrum: {html.escape(spectrum["reason"])}.</p>'

    controls = (
        '<div class="controls" role="group" aria-label="Spectrum scale">'
        '<button type="button" data-scale="linear" aria-pressed="true">Linear</button>'
        '<button type="button" data-scale="db" aria-pressed="false">dB</button>'
        "</div>"
    )
    diagram_id = f"{card_id}-diagram"
    chart = (
        f'<div class="chart" id="{card_id}-chart">'
        f'<svg id="{diagram_id}" tabindex="0" role="img" aria-label="'
        + html.escape(
            f"Gradient spectrum: Gx, Gy, Gz and RSS against frequency, 0 to "
            f"{spectrum['max_frequency_hz']:g} Hz"
        )
        + f'"></svg><div class="tip" id="{card_id}-tip" hidden></div></div>'
    )
    window_ms = FFT_WINDOW_S * 1e3
    note = (
        '<p class="muted">The spectra use the method of pypulseq '
        f"<code>calculate_gradient_spectrum</code> over the whole sequence: {window_ms:g} ms "
        "Hann windows with 50% overlap, the magnitude spectrum (amplitude spectral density) of "
        "each window, and the maximum over windows. The gradients are padded with half a window "
        "of zeros at each end. RSS is the root-sum-of-squares of the three axes in each window. "
        "On the dB scale, each value is 20 log10 of its ratio to the largest RSS value, and "
        "values below "
        f"{fmt(_SPECTRUM_DB_FLOOR)} dB are drawn at {fmt(_SPECTRUM_DB_FLOOR)} dB. "
        "Click the chart to mark the centre for the zoom buttons. "
        "Drag across the chart to zoom to that range. Hold Shift and drag, or scroll "
        "sideways, to pan.</p>"
    )
    return controls + zoom_controls(diagram_id) + chart + note


def spectrum_card(seq: pp.Sequence, *, card_id: str = "gradient-spectrum") -> Card:
    """The "Gradient spectrum" card of one sequence: the body is
    `_spectrum_html(data, card_id)`, with `data` from `_spectrum_data` of
    `grad_spectrum.gradient_spectrum(seq)`. The card gives no resonance bands, so `data` has
    empty `resonances` and `bands` (the card script reads `data.resonances`).

    `data` is always the JSON-ready spectrum dict and `script` is always `"spectrum"`,
    even when there are no gradients, so the card script can still read `data.reason`. The
    card's `scripts` has `assets/cards/spectrum.js`.

    Raises `NotImplementedError` for a sequence with the rotation extension
    (`extensions.refuse_rotations`).
    """
    refuse_rotations(seq)
    data = _spectrum_data(gradient_spectrum(seq))
    body = _spectrum_html(data, card_id)
    return Card(
        id=card_id,
        title="Gradient spectrum",
        body_html=body,
        data=data,
        script="spectrum",
        scripts=(card_asset("spectrum"),),
    )


def _build(ctx: ReportContext) -> Card:
    return spectrum_card(ctx.seq, card_id=SPEC.name)


SPEC = CardSpec("gradient-spectrum", 50, _build)
