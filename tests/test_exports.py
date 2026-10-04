import importlib

import pulseq_checks
import pytest

import pulseq_reports

# (package, exported name, module that defines it)
EXPORTS = [
    ("pulseq_reports", "build_cards", "registry"),
    ("pulseq_reports", "Card", "page"),
    ("pulseq_reports", "render_page", "page"),
    ("pulseq_reports", "write_page", "page"),
    ("pulseq_reports", "TimeWindow", "waveforms"),
    ("pulseq_reports", "first_adc_window", "waveforms"),
    ("pulseq_reports", "full_window", "waveforms"),
    ("pulseq_reports.cards", "timing_card", "timing"),
    ("pulseq_reports.cards", "rf_exposure_card", "rf_exposure"),
    ("pulseq_reports.cards", "diagram_card", "diagram"),
    ("pulseq_reports.cards", "rf_profile_card", "rf_profile"),
    ("pulseq_reports.cards", "spectrum_card", "spectrum"),
    ("pulseq_reports.cards", "pns_card", "pns"),
    ("pulseq_reports.cards", "gradient_limits_card", "gradient_limits"),
    ("pulseq_reports.cards", "definitions_card", "definitions"),
    ("pulseq_reports.cards", "blocks_card", "blocks"),
]


@pytest.mark.parametrize(("package", "name", "module"), EXPORTS)
def test_an_exported_name_is_the_object_of_its_module(package, name, module):
    defining = importlib.import_module(f"{package}.{module}")
    assert getattr(importlib.import_module(package), name) is getattr(defining, name)


def test_hardware_limits_is_the_class_of_pulseq_checks():
    assert pulseq_reports.HardwareLimits is pulseq_checks.HardwareLimits
