import pytest
from synthetic import empty_sequence, gre_sequence, spin_echo_sequence

from pulseq_reports import page
from pulseq_reports.cards.spectrum import _spectrum_data, spectrum_card, spectrum_data
from pulseq_reports.grad_spectrum import AcousticResonance, combine, gradient_spectrum
from pulseq_reports.seq_utils import NamedSequence


@pytest.fixture(scope="module")
def default_seq():
    return spin_echo_sequence()


def test_spectrum_data_for_spin_echo(default_seq):
    data = spectrum_data(default_seq)

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
    card = spectrum_card([NamedSequence("vb-spin-echo", default_seq)])
    result = page.render_page("Title", "Subtitle", [card])
    body = result[result.index('id="gradient-spectrum"') :]

    assert "<h2>Gradient spectrum</h2>" in body
    assert "<td>540–640</td>" in body
    assert "<td>1030–1250</td>" in body
    assert 'id="gradient-spectrum-diagram"' in body
    assert '<button type="button" data-scale="linear" aria-pressed="true">Linear</button>' in body
    assert '<button type="button" data-scale="db" aria-pressed="false">dB</button>' in body
    assert "drawn at −80 dB" in body


def test_report_without_gradients_has_no_spectrum_chart():
    card = spectrum_card([NamedSequence("no-gradients", empty_sequence())])
    assert card.body_html == '<p class="muted">No gradient spectrum: no gradients.</p>'

    result = page.render_page("Title", "Subtitle", [card])
    assert '<p class="muted">No gradient spectrum: no gradients.</p>' in result
    assert 'id="gradient-spectrum-diagram"' not in result


def test_custom_scanner_label_and_resonances_appear(default_seq):
    custom_resonances = (AcousticResonance(frequency_hz=700.0, bandwidth_hz=40.0),)

    card = spectrum_card(
        [NamedSequence("a.seq", default_seq)],
        resonances=custom_resonances,
        scanner_label="Acme Scanner",
    )

    assert "Acme Scanner forbidden band (Hz)" in card.body_html
    assert "the Acme Scanner forbidden bands" in card.body_html
    assert "the acoustic resonances of the Acme Scanner gradient coil" in card.body_html
    assert "700 ± 20 Hz" in card.body_html
    assert card.data["resonances"] == [{"frequency_hz": 700.0, "bandwidth_hz": 40.0}]
    assert [(b["low_hz"], b["high_hz"]) for b in card.data["bands"]] == [(680.0, 720.0)]
    expected_bands = spectrum_data(default_seq, resonances=custom_resonances)["bands"]
    assert card.data["bands"] == expected_bands


def test_two_file_card_uses_combined_spectrum():
    seqs = [
        NamedSequence("spin-echo.seq", spin_echo_sequence()),
        NamedSequence("gre.seq", gre_sequence()),
    ]

    card = spectrum_card(seqs)

    expected = _spectrum_data(combine([gradient_spectrum(named.seq) for named in seqs]))
    assert card.data == expected
    assert "maximum, at each frequency, over the files" in card.body_html
    assert "windows that would cross from one file to the next are not included" in card.body_html

    # render_page accepts a card built for more than one file too.
    page.render_page("Title", "Subtitle", [card])


def test_custom_card_id_changes_element_ids(default_seq):
    card = spectrum_card([NamedSequence("a.seq", default_seq)], card_id="spectrum-b")

    assert card.id == "spectrum-b"
    assert 'id="spectrum-b-chart"' in card.body_html
    assert 'id="spectrum-b-diagram"' in card.body_html
    assert 'id="spectrum-b-tip"' in card.body_html
    assert 'data-zoom-for="spectrum-b-diagram"' in card.body_html


def test_render_page_includes_spectrum_script_once(default_seq):
    cards = [
        spectrum_card([NamedSequence("a.seq", default_seq)], card_id="spectrum-a"),
        spectrum_card([NamedSequence("a.seq", default_seq)], card_id="spectrum-b"),
    ]

    result = page.render_page("Title", "Subtitle", cards)

    assert result.count('PulseqReport.registerCard("spectrum"') == 1
