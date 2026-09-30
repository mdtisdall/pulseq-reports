"""Self-contained HTML review reports for Pulseq sequences."""

from .grad_limits import HardwareLimits
from .grad_spectrum import PRISMA_AS82, GradientCoil
from .page import Card, Check, render_page, write_page
from .registry import build_cards
from .waveforms import TimeWindow, first_adc_window, full_window

__version__ = "0.2.0rc2"

__all__ = [
    "PRISMA_AS82",
    "Card",
    "Check",
    "GradientCoil",
    "HardwareLimits",
    "TimeWindow",
    "__version__",
    "build_cards",
    "first_adc_window",
    "full_window",
    "render_page",
    "write_page",
]
