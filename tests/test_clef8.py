"""The small «8» under a treble clef, found in the image (synthesis/clef8.py)."""

import cv2
import numpy as np

from omr_coral.synthesis.clef8 import _figures_with_two_holes


def _crop_with(text: str) -> np.ndarray:
    img = np.full((120, 100), 255, np.uint8)
    cv2.putText(img, text, (25, 85), cv2.FONT_HERSHEY_SIMPLEX, 1.6, 0, 4)
    return img


def test_an_eight_has_two_holes():
    assert _figures_with_two_holes(_crop_with("8"), 30) == 1


def test_a_verse_number_or_a_letter_is_not_an_eight():
    assert _figures_with_two_holes(_crop_with("1."), 30) == 0
    assert _figures_with_two_holes(_crop_with("a"), 30) == 0


def test_an_upper_staff_read_in_the_f_clef_is_read_again_as_octave_treble():
    from fractions import Fraction as Fr

    from omr_coral.model.score import Event, Measure
    from omr_coral.pipeline import _reread_as_octave_treble

    m = Measure(index=0, system=1, page=None, staves=[], key_fifths=-2)
    m.voices = {"soprano": [Event(Fr(0), Fr(1), "D3", 50)], "alto": [Event(Fr(0), Fr(1), "A2", 45)]}

    class Staff:
        clef = "F"

    st = Staff()
    _reread_as_octave_treble(m, st)
    assert [m.voices["soprano"][0].pitch, m.voices["alto"][0].pitch] == ["B-3", "F3"] and st.clef == "G8vb"
