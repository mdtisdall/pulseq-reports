import pypulseq as pp
import pytest
from pypulseq.event_lib import EventLibrary
from synthetic import gre_sequence

from pulseq_reports.cards.diagram import diagram_card
from pulseq_reports.cards.gradient_limits import gradient_limits_card
from pulseq_reports.cards.pns import pns_card
from pulseq_reports.cards.spectrum import spectrum_card
from pulseq_reports.waveforms import full_window

# A scalar-first unit quaternion (angle 45 deg about z): q0=cos(22.5deg), qz=sin(22.5deg).
_QUATERNION = (0.9238795325112867, 0.0, 0.0, 0.3826834323650898)


def _with_rotation_library() -> pp.Sequence:
    """A `gre_sequence` with one rotation stored the way pypulseq draft PR #372 stores
    it: a `rotation_library` (an `EventLibrary` of scalar-first unit quaternions)."""
    seq = gre_sequence(num_trs=2)
    seq.rotation_library = EventLibrary()
    seq.rotation_library.insert(1, _QUATERNION)
    return seq


@pytest.mark.parametrize(
    "call_card",
    [
        pytest.param(spectrum_card, id="spectrum_card"),
        pytest.param(pns_card, id="pns_card"),
        pytest.param(gradient_limits_card, id="gradient_limits_card"),
        pytest.param(lambda seq: diagram_card(seq, [full_window(seq)]), id="diagram_card"),
    ],
)
def test_gradient_cards_refuse_rotations(call_card):
    """`spectrum_card`, `pns_card`, `gradient_limits_card` and `diagram_card` each
    raise `NotImplementedError` for a sequence with a rotation library."""
    seq = _with_rotation_library()
    with pytest.raises(NotImplementedError):
        call_card(seq)
