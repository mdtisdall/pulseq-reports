import pytest
from synthetic import empty_sequence, spin_echo_sequence

from pulseq_reports import page
from pulseq_reports.cards.spectrum import _spectrum_data, spectrum_card
from pulseq_reports.grad_spectrum import gradient_spectrum

RESONANCES = ((590.0, 100.0), (1140.0, 220.0))  # (frequency_hz, bandwidth_hz)


@pytest.fixture(scope="module")
def default_seq():
    return spin_echo_sequence()


def test_spectrum_data_for_spin_echo(default_seq):
    data = _spectrum_data(gradient_spectrum(default_seq, resonances=RESONANCES))

    assert data["reason"] is None
    assert data["resonances"] == [
        {"frequency_hz": 590.0, "bandwidth_hz": 100.0},
        {"frequency_hz": 1140.0, "bandwidth_hz": 220.0},
    ]
    assert [lane["id"] for lane in data["lanes"]] == ["gx", "gy", "gz", "rss"]
    for lane in data["lanes"]:
        assert lane["unit"] == "mT/m/√Hz"
        assert lane["domain"] == data["lanes"][-1]["domain"]  # one shared value range
        (points,) = lane["segments"]
        assert points[0][0] == 0
        assert points[-1][0] == pytest.approx(data["max_frequency_hz"])
    assert [(b["low_hz"], b["high_hz"]) for b in data["bands"]] == [(540, 640), (1030, 1250)]


def test_report_has_gradient_spectrum_card(default_seq):
    card = spectrum_card(default_seq)
    result = page.render_page("Title", "Subtitle", [card])
    body = result[result.index('id="gradient-spectrum"') :]

    assert "<h2>Gradient spectrum</h2>" in body
    assert 'id="gradient-spectrum-diagram"' in body
    assert '<button type="button" data-scale="linear" aria-pressed="true">Linear</button>' in body
    assert '<button type="button" data-scale="db" aria-pressed="false">dB</button>' in body
    assert "drawn at −80 dB" in body


def test_report_without_gradients_has_no_spectrum_chart():
    card = spectrum_card(empty_sequence())
    assert card.body_html == '<p class="muted">No gradient spectrum: no gradients.</p>'

    result = page.render_page("Title", "Subtitle", [card])
    assert '<p class="muted">No gradient spectrum: no gradients.</p>' in result
    assert 'id="gradient-spectrum-diagram"' not in result


def test_the_card_has_no_bands(default_seq):
    card = spectrum_card(default_seq)

    assert card.data["reason"] is None
    assert card.data["resonances"] == []
    assert card.data["bands"] == []
    assert "<table" not in card.body_html


def test_custom_card_id_changes_element_ids(default_seq):
    card = spectrum_card(default_seq, card_id="spectrum-b")

    assert card.id == "spectrum-b"
    assert 'id="spectrum-b-chart"' in card.body_html
    assert 'id="spectrum-b-diagram"' in card.body_html
    assert 'id="spectrum-b-tip"' in card.body_html
    assert 'data-zoom-for="spectrum-b-diagram"' in card.body_html


def test_render_page_includes_spectrum_script_once(default_seq):
    cards = [
        spectrum_card(default_seq, card_id="spectrum-a"),
        spectrum_card(default_seq, card_id="spectrum-b"),
    ]

    result = page.render_page("Title", "Subtitle", cards)

    assert result.count('PulseqReport.registerCard("spectrum"') == 1
