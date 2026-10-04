"""Self-contained HTML review reports for Pulseq sequences."""

from .grad_limits import HardwareLimits
from .page import Card, render_page, write_page
from .registry import build_cards
from .waveforms import TimeWindow, first_adc_window, full_window

__version__ = "0.2.0rc3.dev0"

__all__ = [
    "Card",
    "HardwareLimits",
    "TimeWindow",
    "__version__",
    "build_cards",
    "first_adc_window",
    "full_window",
    "render_page",
    "write_page",
]
