"""Coralis' own reading of the lyrics (ocr/lyrics_ocr): the parts that do not need an image."""

from fractions import Fraction as Fr

from omr_coral.model.lyrics_text import verse_syllables
from omr_coral.model.score import Event
from omr_coral.ocr.lyrics_ocr import clean, complete, correct, stanzas


def _aud(text: str) -> list[tuple]:
    """A stanza as Audiveris read it: (text, syllabic, event)."""
    out = []
    for k, s in enumerate(verse_syllables(text)):
        e = Event(Fr(k), Fr(1), "C4", 60)
        e.lyrics = {1: (s.text, s.syllabic)}
        out.append((s.text, s.syllabic, e))
    return out


def test_clean_printed_lyrics():
    assert clean("Cris - to que_en mí ____") == "Cris-to que en mí"
    assert clean("¡E-xal-ta-do se-a") == "¡E-xal-ta-do se-a"      # the ¡ is not a capital inside a word
    assert clean("mi cO-ra-zón") == "mi co-ra-zón"
    assert clean("Dios У d a-mor") == "Dios y a-mor"                # Cyrillic look-alike, a speck


def test_lines_go_to_the_stanza_they_look_like():
    theirs = [_aud("Su-bli-me gra-cia del Se-ñor"), _aud("Su gra-cia me en-se-ñó a te-mer")]
    rows = [[["Su gra-cia me en-se-ñó a te-mer", 10, False],      # printed 2nd but read 1st
             ["Su-bli-me gra-cia del Se-ñor", 10, False],
             ["mp cresc. hombres", 10, False]]]                    # not lyrics: left out
    assert stanzas(rows, theirs) == ["Su-bli-me gra-cia del Se-ñor", "Su gra-cia me en-se-ñó a te-mer"]


def test_a_lost_line_goes_by_its_place():
    theirs = [_aud("Su-bli-me gra-cia del Se-ñor que a un in-fe-liz"), _aud("Su gra-cia me en-se-ñó")]
    rows = [[["Su-bli-me gra-cia del Se-ñor", 10, False], ["Su gra-cia me en-se-ñó", 10, False]],
            [["que a un in-fe-liz", 10, False], ["a te-mer mis du-das a-hu-yen-tó", 10, False]]]
    # Audiveris lost «a temer mis dudas ahuyentó»: line 2 of system 2 = stanza 2
    assert stanzas(rows, theirs)[1] == "Su gra-cia me en-se-ñó a te-mer mis du-das a-hu-yen-tó"


def test_words_repeated_under_the_lower_staff_are_not_added_twice():
    theirs = [_aud("Mi Dios ma-jes-tuo-so es y san-to es")]
    rows = [[["Mi Dios ma-jes-tuo-so es", 10, False], ["Mi Dios ma-jes-tuo-so es", 10, True],
             ["y san-to es", 900, True]]]                            # men alone, further right
    assert stanzas(rows, theirs) == ["Mi Dios ma-jes-tuo-so es y san-to es"]


def test_a_stretch_read_twice_goes_out():
    own = verse_syllables("A-gra-de-ci A-gra-de-ci-dos hoy")
    out = complete(own, _aud("A-gra-de-ci-dos hoy"))
    assert [s.text for s in out] == ["A", "gra", "de", "ci", "dos", "hoy"]


def test_misread_syllables_are_mended_on_their_notes():
    theirs = _aud("un mun-do rne-jor que")              # «rne» for «me»; «que_en» lost its «en»
    n = correct(verse_syllables("un mun-do me-jor que en"), theirs, 1)
    texts = [t[2].lyrics[1][0] for t in theirs]
    assert texts == ["un", "mun", "do", "me", "jor", "que‿en"]   # same notes, mended words
    assert n == 2


def test_a_speck_read_as_a_stanza_is_noise():
    theirs = [_aud("Nues-tro sol se po-ne ya"), _aud("Oh Se-ñor tu pro-tec-ción"), _aud("i")]
    rows = [[["1. Nues-tro sol se po-ne ya", 10, False], ["2. Oh, Se-ñor, tu pro-tec-ción", 10, False]]]
    assert stanzas(rows, theirs) == ["Nues-tro sol se po-ne ya", "Oh, Se-ñor, tu pro-tec-ción", None]


def test_a_stretch_given_twice_by_the_recognizer_is_joined():
    from omr_coral.ocr.lyrics_ocr import _rows

    frags = [{"text": "Da-le a-que-lla dul-ce", "x0": 0, "y0": 0, "x1": 200, "y1": 10},
             {"text": "dul-ce paz", "x0": 150, "y0": 0, "x1": 260, "y1": 10},
             {"text": "Que a los tu-yos", "x0": 300, "y0": 0, "x1": 400, "y1": 10}]
    assert [" ".join(f["text"] for f in r) for r in _rows(frags, 20)] == ["Da-le a-que-lla dul-ce paz Que a los tu-yos"]


def test_a_lone_word_the_recognizer_skipped_comes_from_audiveris():
    own = verse_syllables("Se-ñor; ¡Lo-or Ti!")
    out = complete(own, _aud("Se-ñor; ¡Lo-or a Ti!"))
    assert [s.text for s in out] == ["Se", "ñor;", "¡Lo", "or", "a", "Ti!"]


def test_words_audiveris_lost_go_on_the_empty_notes_between():
    # notes: Hi | (empty) | (empty) | men | sa ; Coralis read «Hi-zo un in-men-sa»
    evs = [Event(Fr(k), Fr(1), "C4", 60) for k in range(5)]
    for e, t in zip(evs, ["Hi", None, None, "men", "sa"]):
        if t:
            e.lyrics = {1: (t, "middle")}
    theirs = [(e.lyrics[1][0], "middle", e) for e in evs if e.lyrics]
    correct(verse_syllables("Hi-zo un in-men-sa"), theirs, 1, evs)
    # three syllables for the two empty notes: one sinalefa
    assert [e.lyrics.get(1, ("",))[0] for e in evs] == ["Hi", "zo‿un", "in", "men", "sa"]


def test_the_first_syllable_the_recognizer_skipped_comes_from_audiveris():
    out = complete(verse_syllables("sús me guí-a"), _aud("Je-sús me guí-a"))
    assert [s.text for s in out][:2] == ["Je", "sús"]


def test_words_printed_between_the_lines_after_them_go_with_line_1():
    from omr_coral.ocr.lyrics_ocr import _rows

    def fr(t, x0, x1, cy):
        return {"text": t, "x0": x0, "x1": x1, "y0": cy - 8, "y1": cy + 8}

    frags = [fr("pues Dios me guar-da su-yo soy.", 170, 1400, 55), fr("pues aun a-llí con-ti-go i-ré.", 170, 1390, 105),
             fr("Je-sús me guí-a,", 1480, 2070, 84)]
    rows = [" ".join(f["text"] for f in r) for r in _rows(frags, 21)]
    assert rows == ["pues Dios me guar-da su-yo soy. Je-sús me guí-a,", "pues aun a-llí con-ti-go i-ré."]


def test_words_the_reader_skipped_versus_a_refrain_audiveris_repeated():
    from omr_coral.ocr.lyrics_ocr import skipped_words

    own = [verse_syllables("Su-bli-me gra-cia del Se-ñor de muer-te me li-bró gran-des fie-les su a-mor"),
           verse_syllables("Mi co-ra-zón en-ter-ne-ció")]
    theirs = [_aud("Su-bli-me gra-cia del Se-ñor de muer-te me li-bró per-di-do fui gran-des fie-les su a-mor"),
              _aud("Mi co-ra-zón en-ter-ne-ció gran-des fie-les su a-mor")]   # the refrain, read under stanza 2
    assert skipped_words(own, theirs) == {1}
