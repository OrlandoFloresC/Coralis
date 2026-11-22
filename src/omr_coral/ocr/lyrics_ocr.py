"""The stanzas of a hymn read from the page images by Coralis itself (not by Audiveris).

Audiveris' text reading loses lyrics: it erases what follows an elision printed with «_»
(«que_en» → «que»), misreads small type («gri-no ig-no-to» → «gn g no to») and sometimes gives no
lyrics at all. The operating system's recognizer (see system_ocr) reads the whole page; here the
lines that lie between the staves of each system (where the words are printed) are taken, top to
bottom (line 1 = stanza 1…), joined system after system, and cleaned into plain stanza text — like
a lyrics .txt the user would write. Placing them on the notes is apply_lyrics_text's job.
"""

from __future__ import annotations

import re
from pathlib import Path

from ..model.layout import LayoutSystem, read_audiveris_layout
from ..model.lyrics_text import _norm
from ..model.score import PARTNER
from . import system_ocr

FILE = "letra_ocr.json"   # the lines read, cached in the run folder


def _layout(run_dir: Path) -> tuple[list[LayoutSystem], Path] | None:
    """The systems Audiveris found, and the folder of the page images they refer to. The original
    pages first; when Audiveris only managed another image version (rescaled, straightened…), that
    one, with its own images, since its coordinates are not those of the original pages."""
    for name in ("original", "limpia", "binaria", "contraste", "enderezada", "escala"):
        omr = run_dir / "engines" / "audiveris" / name / "book.omr"
        if not omr.exists():
            continue
        try:
            lay = read_audiveris_layout(omr)
        except Exception:  # noqa: BLE001
            continue
        images = run_dir / "variants" / name
        if lay and (name == "original" or images.is_dir()):
            return lay, (images if images.is_dir() else run_dir / "pages")
    return None


def _bands(s: LayoutSystem, next_top: float | None = None) -> list[tuple[float, float, float, float, bool]]:
    """Where the words of a system are printed: (x0, y0, x1, y1, below). Between the first and the
    second staff (a hymnal's two staves; the soprano's own staff in an open score), or under a lone
    staff; and, marked below=True, under the last staff (the men's words when they sing alone)."""
    if not s.staves:
        return []
    il = s.interline or 20
    first, last = s.staves[0], s.staves[-1]
    x0, x1 = min(st.left for st in s.staves) - 2 * il, max(st.right for st in s.staves) + il
    if len(s.staves) >= 2:
        y1 = last.bottom + 5 * il
        if next_top is not None:
            y1 = min(y1, next_top - 0.5 * il)
        return [(x0, first.bottom + 0.6 * il, x1, s.staves[1].top - 0.3 * il, False),
                (x0, last.bottom + 0.6 * il, x1, y1, True)]
    return [(x0, first.bottom + 0.6 * il, x1, first.bottom + 9 * il, False)]


def _rows(fragments: list[dict], il: float) -> list[list[dict]]:
    """Fragments at the same height are one printed line (the recognizer splits it at wide gaps).
    A line printed half-way between two others, to the right of where they end, is words every
    stanza sings (a refrain's first words between the stanza lines: «Je-sús me guí-a,»): it goes
    at the end of line 1, the line every stanza takes in a refrain."""
    rows: list[list[dict]] = []
    for f in sorted(fragments, key=lambda f: (f["y0"] + f["y1"]) / 2):
        cy = (f["y0"] + f["y1"]) / 2
        if rows and abs(cy - sum(x["cy"] for x in rows[-1]) / len(rows[-1])) < 0.5 * il:
            rows[-1].append(f | {"cy": cy})
        else:
            rows.append([f | {"cy": cy}])
    rows = [_no_overlaps(sorted(r, key=lambda f: f["x0"])) for r in rows]
    if len(rows) >= 3:
        mid = [k for k in range(1, len(rows) - 1)
               if min(f["x0"] for f in rows[k]) > max(f["x1"] for j, r in enumerate(rows) if j != k for f in r) - il]
        for k in reversed(mid):
            rows[0] += rows.pop(k)
    return rows


def _no_overlaps(row: list[dict]) -> list[dict]:
    """The recognizer sometimes gives a stretch of a line twice («…a-que-lla dul-ce» and «dul-ce
    paz»): two fragments that overlap on the line are joined where their words repeat; one that
    lies inside the other is dropped."""
    def words(t: str) -> list[str]:
        return re.sub(r"\s*-\s*", "-", t).split()   # «de - ber» and «de -ber» are the same word

    out: list[dict] = []
    for f in sorted(row, key=lambda f: f["x0"]):
        if out and f["x0"] < out[-1]["x1"] - 2:
            a, b = out[-1], f
            wa, wb = words(a["text"]), words(b["text"])
            if b["x1"] <= a["x1"] + 8:      # inside the one before
                continue
            k = next((k for k in range(min(len(wa), len(wb)), 0, -1) if wa[-k:] == wb[:k]), 0)
            out[-1] = a | {"text": " ".join(wa + wb[k:]), "x1": b["x1"]}
            continue
        out.append(dict(f))
    return out


_NUMBER = re.compile(r"^\s*(\d{1,2})\s*[.)]\s*")
_NOT_SUNG = re.compile(r"©|copyright|rights|reserv|derechos|www\.|http", re.IGNORECASE)


# the recognizer sometimes answers with Cyrillic look-alikes («У» for «y», «тр» for «mp»)
_CYRILLIC = str.maketrans("АВЕКМНОРСТХУаеорсхут", "ABEKMHOPCTXyaeopcxym")
_SPECK = re.compile(r"^[^\w¡¿]*[b-df-hj-np-tv-xzB-DF-HJ-NP-TV-XZ][^\w]*$")


def clean(text: str) -> str:
    """Printed lyrics → plain words: «Cris - to» → «Cris-to», «que_en» → «que en», extender lines
    («____», «———») out."""
    t = text.translate(_CYRILLIC).replace("‿", " ").replace("—", " ").replace("–", "-")
    t = re.sub(r"_{2,}", " ", t)
    t = t.replace("_", " ")
    t = re.sub(r"\s*-\s*", "-", t)          # syllables of one word
    t = re.sub(r"-{2,}", "-", t)
    t = re.sub(r"(^|\s)-+|-+(\s|$)", r"\1\2", t)   # a hyphen at a word's edge (continued from the line before)
    t = re.sub(r"\s+", " ", t).strip()
    # «cO ra zon», «SO»: a capital the recognizer put inside lowercase lyrics
    def inner_capital(w: str) -> bool:
        letters = [c for c in w if c.isalpha()]   # «¡E-xal-ta-do»: the ¡ does not count
        return any(c.isupper() for c in letters[1:])

    words = [w.lower() if inner_capital(w) and any(c.islower() for c in t) else w for w in t.split()]
    # a lone letter that is not a Spanish word («d», «x»): a speck read as text; letters the
    # recognizer confuses (digits inside words «na-c10», odd marks «tẹ»…), as for Audiveris
    from ..model.lyrics_fix import fix_ocr_letters

    return " ".join(fix_ocr_letters(w) for w in words if not _SPECK.match(w))


_DYNAMIC = re.compile(r"^(?:p{1,3}|m[pf]|f{1,3}|sfz?|fp|cresc\.?|decresc\.?|dim\.?|rit\.?|rall\.?|"
                      r"accel\.?|unis\.?|a tempo|\d+|[+†*].*)$", re.IGNORECASE)
_DIRECTION = re.compile(r"\b(?:hombres|mujeres|varones|damas|tenor(?:es)?|bajos?|sopranos?|contraltos?|"
                        r"unísono|tutti|solo|coro|coda|fine|d\.\s?[sc]\.|segno)\b", re.IGNORECASE)


def _strip_marks(text: str) -> str:
    """Dynamics and performance words the recognizer read on the lyrics line («mp», «cresc.», «+tenores»)."""
    return " ".join(w for w in text.translate(_CYRILLIC).split() if not _DYNAMIC.match(w.strip(",;:")))


def _lyric_fragment(text: str) -> bool:
    """«hombres en unísono», «D. S. al Coda»: an indication, not words to sing (sung words get hyphens)."""
    return "-" in text or not _DIRECTION.search(text)


def read_rows(run_dir: Path) -> list[list[list]] | None:
    """For each system (in reading order), its printed lyrics lines top to bottom, cleaned, as
    [text, x where the line starts, under the last staff]. A line starting with a stanza number «2.» keeps it («2. Mi co-ra-zón…»)."""
    if not system_ocr.available():
        return None
    found = _layout(run_dir)
    if not found:
        return None
    layout, image_dir = found
    from PIL import Image

    images: dict[int, Image.Image] = {}
    out: list[list[list]] = []
    for i, s in enumerate(layout):
        if s.page not in images:
            img = image_dir / f"page_{s.page:03d}.png"
            if not img.exists():
                continue
            images[s.page] = Image.open(img).convert("L")
        page = images[s.page]
        il = s.interline or 20
        rows: list[list] = []
        nxt = layout[i + 1] if i + 1 < len(layout) else None
        next_top = nxt.staves[0].top if nxt and nxt.page == s.page and nxt.staves else None
        for bx0, by0, bx1, by1, below in _bands(s, next_top):
            box = (max(0, int(bx0)), max(0, int(by0)), min(page.width, int(bx1)), min(page.height, int(by1)))
            if box[2] - box[0] < 50 or box[3] - box[1] < 10:
                continue
            # the band alone, read on its own: small type on a whole page gets skipped
            frags = [f for f in system_ocr.read_lines(page.crop(box))
                     if not _NOT_SUNG.search(f["text"]) and _lyric_fragment(f["text"])]
            for row in _rows(frags, il):
                text = " ".join(f["text"] for f in row)
                m = _NUMBER.match(text)
                num = f"{int(m.group(1))}. " if m and 1 <= int(m.group(1)) <= 12 else ""
                text = clean(_strip_marks(_NUMBER.sub("", text)))
                if sum(c.isalpha() for c in text) >= 2:   # a line of dynamics only is not a line
                    rows.append([num + text, round(row[0]["x0"] + box[0]), below])
        out.append(rows)
    return out if any(r for rows in out for r in rows) else None


def rows_for(run_dir: Path) -> list[list[list]] | None:
    """read_rows, cached in the run folder (FILE, JSON)."""
    import json

    cache = run_dir / FILE
    if cache.exists():
        try:
            rows = json.loads(cache.read_text(encoding="utf-8")) or None
        except ValueError:
            rows = None
        if rows:
            # cleaned again: a better clean() applies to runs read before it (it is idempotent)
            def again(t: str) -> str:
                m = _NUMBER.match(t)
                return (m.group(0) if m else "") + clean(_NUMBER.sub("", t))
            return [[[again(r[0]), *r[1:]] for r in sys_rows] for sys_rows in rows]
    found = read_rows(run_dir)
    if found:
        cache.write_text(json.dumps(found, ensure_ascii=False, indent=1), encoding="utf-8")
    return found


# --------------------------------------------------------------------------- matching with Audiveris


def _syls(text: str) -> list[str]:
    from ..model.lyrics_text import verse_syllables

    return [x for x in (_norm(s.text) for s in verse_syllables(text)) if x]


def _overlap(row: list[str], verse: list[str]) -> float:
    """Share of the row's syllables found in runs of ≥2 in a row in the verse: lone common
    syllables («de», «la») match anything, runs do not."""
    from difflib import SequenceMatcher

    if not row or not verse:
        return 0.0
    blocks = SequenceMatcher(None, row, verse, autojunk=False).get_matching_blocks()
    return sum(b.size for b in blocks if b.size >= 2) / len(row)


def stanzas(rows: list[list[list]], audiveris: list[list[str]]) -> list[str] | None:
    """The stanza texts built from the OCR lines, as many stanzas as the vote found (audiveris[n-1]
    = stanza n as Audiveris read it, see audiveris_stanzas). Each line goes to the stanza it
    shares runs of syllables with; a line like no stanza (Audiveris lost it) goes by its place,
    line k = stanza k, only where the system's other lines keep that order. Lines that belong to
    no stanza (another voice's words, indications) are left out. None: not enough agreement."""
    n_verses = len(audiveris)
    if not n_verses:
        return None
    parts: dict[int, list[str]] = {n: [] for n in range(1, n_verses + 1)}
    matched_rows = 0
    for sys_rows in rows:
        found: dict[int, int] = {}       # row → stanza
        loose: list[int] = []
        upper = [r for r in sys_rows if not (len(r) > 2 and r[2])]
        below = [r for r in sys_rows if len(r) > 2 and r[2]]
        texts = [r[0] for r in upper]
        for k, text in enumerate(texts, start=1):
            m = _NUMBER.match(text)
            if m and 1 <= int(m.group(1)) <= n_verses:
                found[k] = int(m.group(1))
                continue
            row = _syls(text)
            scores = [_overlap(row, [_norm(t[0]) for t in v]) for v in audiveris]
            best = max(scores)
            if best >= 0.4:
                # a refrain line matches several stanzas: its place decides
                close = [n for n, sc in enumerate(scores, start=1) if sc >= best - 0.05]
                found[k] = k if k in close else close[0]
            else:
                loose.append(k)
        in_order = all(n == k for k, n in found.items())
        for k in loose:
            if in_order and k <= n_verses and k not in found.values() and (
                    "-" in texts[k - 1] or len(texts[k - 1].split()) >= 4):
                found[k] = k
        chosen = [(found[k], upper[k - 1]) for k in found]
        # under the last staff: only words of a stanza that the lines above do not already say
        # (many scores print the words again for the men)
        above = [_syls(t) for t in texts]
        for r in below:
            row = _syls(r[0])
            if not row or any(_overlap(row, a) >= 0.5 for a in above):
                continue
            scores = [_overlap(row, [_norm(t[0]) for t in v]) for v in audiveris]
            if max(scores) >= 0.5:
                chosen.append((scores.index(max(scores)) + 1, r))
        # two lines of one stanza in a system: voices taking turns, left to right
        for n, r in sorted(chosen, key=lambda c: (c[0], c[1][1])):
            parts[n].append(_NUMBER.sub("", r[0]))
        matched_rows += len(chosen)
    # a «stanza» of Audiveris with next to nothing («i», a speck under the staff, a few syllables of
    # another line read apart) that no printed line matches is noise: None in its place (dropped)
    longest = max(len(v) for v in audiveris)
    noise = {n for n, p in parts.items() if not p and len(audiveris[n - 1]) < max(4, 0.15 * longest)}
    if not matched_rows or any(not p for n, p in parts.items() if n not in noise) or len(noise) == n_verses:
        return None
    return [None if n in noise else " ".join(parts[n]) for n in sorted(parts)]


def drop_verses(cs, gone: set[int]) -> None:
    """Remove those lyrics lines and renumber the rest (1, 2, 3…). A dropped line's syllables in a
    measure where the stanza above it has no words were that stanza, numbered one too far by the
    engine («pues a-con-go-re» read as line 3 under line 1 when line 2 is empty there): they move
    up instead of going."""
    if not gone:
        return
    keep = [n for n in range(1, cs.verses + 1) if n not in gone]
    for m in cs.measures:
        evs = [e for v in m.voices.values() for e in v]
        for n in sorted(gone):
            up = max((k for k in keep if k < n), default=None)
            if up is not None and not any(up in e.lyrics for e in evs):
                for e in evs:
                    if n in e.lyrics:
                        e.lyrics[up] = e.lyrics[n]
    new = {old: k for k, old in enumerate(keep, start=1)}
    for m in cs.measures:
        for evs in m.voices.values():
            for e in evs:
                if e.lyrics:
                    e.lyrics = {new[v]: t for v, t in e.lyrics.items() if v in new}


def lyric_slots(cs) -> list:
    """Every sung note that can carry the words, in order (see lyric_slot_voices); correct() places
    syllables only on those that take one, the others can still mark where a stretch starts or ends."""
    from ..model.lyrics_text import lyric_slot_voices
    from ..model.score import lyric_voice

    held = {id(e) for e, _, _ in lyric_slot_voices(cs)}
    out = []
    for m in cs.measures:
        lead = lyric_voice(m)
        evs = [e for v in (lead, PARTNER[lead]) for e in m.voices.get(v, [])
               if e.is_attack and (v == lead or id(e) in held)]
        out += sorted(evs, key=lambda e: e.offset)
    return out


def audiveris_stanzas(cs) -> list[list[tuple]]:
    """Each stanza of the voted score as Audiveris read it: (text, syllabic, event) on the notes
    that carry the words (lyric_slots), in order."""
    n = cs.verses
    out: list[list[tuple]] = [[] for _ in range(n)]
    for e in lyric_slots(cs):
        for v, (t, syl) in e.lyrics.items():
            if 1 <= v <= n and _norm(t):
                out[v - 1].append((t, syl or "single", e))
    return out


def complete(own: list, theirs: list[tuple]) -> list:
    """The stanza read by Coralis (Syl list), mended with Audiveris' reading where it is safe:
    - a run it read twice in a row («A-gra-de-ci A-gra-de-ci-dos», two voices at one height) that
      Audiveris has once goes out;
    - a short word it skipped (a lone «a» in a wide gap: «¡Lo-or a Ti!», «Je-» at the start) that
      Audiveris read, next to stretches where both readings agree, goes in. Longer runs do not
      (6 syllables tried: «Nuestro temor» 47 → 34 %): where Audiveris lost much, its order is no
      guide (it put phrases twice)."""
    from difflib import SequenceMatcher

    from ..model.lyrics_text import Syl

    a = [_norm(x.text) for x in own]
    b = [_norm(t[0]) for t in theirs]
    ops = SequenceMatcher(None, a, b, autojunk=False).get_opcodes()
    out: list = []
    for k, (tag, i1, i2, j1, j2) in enumerate(ops):
        if tag == "delete" and i2 - i1 >= 2 and a[i2:i2 + (i2 - i1)] == a[i1:i2]:
            continue
        if tag == "insert" and j2 - j1 <= 2 and (k == 0 or ops[k - 1][0] == "equal") \
                and (k == len(ops) - 1 or ops[k + 1][0] == "equal") and len(ops) > 1:
            for t, syl, _ in theirs[j1:j2]:
                out.append(Syl(t, syl, syl in ("single", "begin"), syl in ("single", "end")))
            continue
        out.extend(own[i1:i2])
    return out


def skipped_words(own: list[list], theirs: list[list[tuple]]) -> set[int]:
    """The stanzas where Coralis' reader skipped words: Audiveris has a run of ≥3 syllables there that
    Coralis read nowhere («Sublime gracia»: «per-di-do fui, me ha-lló» missing from stanzas 1 and 2).
    A run Coralis has in another stanza is not skipped: Audiveris repeated the refrain under
    stanza 2 («Todas las promesas», «Grato es contar la historia»)."""
    from difflib import SequenceMatcher

    texts = [[_norm(x.text) for x in o] for o in own]

    def anywhere(run: list[str]) -> bool:   # (half of it, in runs: Audiveris glues junk on: «sasqu»)
        return any(_overlap(run, t) >= 0.5 for t in texts)

    out = set()
    for v, (a, th) in enumerate(zip(texts, theirs), start=1):
        b = [_norm(t[0]) for t in th]
        for tag, i1, i2, j1, j2 in SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
            if tag == "insert" and j2 - j1 >= 3 and not anywhere(b[j1:j2]):
                out.add(v)
                break
    return out


def coverage(own: list, theirs: list[tuple]) -> float:
    """How much of the stanza Audiveris read, against Coralis' own reading (syllables)."""
    return len(theirs) / max(1, len(own))


def correct(own: list, theirs: list[tuple], verse: int, slots: list | None = None) -> int:
    """Audiveris' words stay on their notes; only the stretches it misread or lost are redone with
    what Coralis read. Where the two readings differ, Coralis' syllables are placed (place_verse)
    on the notes between the last note before and the first note after on which both agree —
    the notes Audiveris used there and the empty ones between them (slots: every note that can
    take a syllable, in order) — so «rne jor» → «me jor», «que» → «que‿en», and «Hi- men-sa» gets
    back «zo un ar-ca in-». The words cannot drift past those two notes. Returns notes changed."""
    from difflib import SequenceMatcher

    from ..model.lyrics_text import ELISION, _can_merge, place_verse

    a = [_norm(x.text) for x in own]
    b = [_norm(t[0]) for t in theirs]
    where = {id(e): k for k, e in enumerate(slots or [])}
    changed = 0
    for tag, i1, i2, j1, j2 in SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag == "equal" or i2 == i1:
            continue
        if tag == "delete" and i2 - i1 == 1 and i1 and j1 and a[i1 - 1] == b[j1 - 1] \
                and _can_merge(own[i1 - 1], own[i1]):
            # a syllable Audiveris lost after an elision mark («que_en» read «que»): same note
            e = theirs[j1 - 1][2]
            text, syl = e.lyrics[verse]
            if ELISION not in text:
                last = own[i1].syllabic in ("single", "end")
                start = syl in ("single", "begin")
                e.lyrics[verse] = (text + ELISION + own[i1].text,
                                   "single" if start and last else "begin" if start else "end" if last else "middle")
                changed += 1
            continue
        # the notes of this stretch: between the agreeing neighbours (all of them when slots are known)
        lo = where.get(id(theirs[j1 - 1][2])) if j1 else -1
        hi = where.get(id(theirs[j2][2])) if j2 < len(theirs) else len(slots or [])
        if slots and lo is not None and hi is not None and hi - lo - 1 >= 1:
            events = [e for e in slots[lo + 1:hi] if e.takes_syllable or verse in e.lyrics]
        elif j2 > j1:
            events = [t[2] for t in theirs[j1:j2]]
        else:
            continue
        if len(events) > 3 * (i2 - i1) + 4:   # a long gap: no guide to where the words go
            continue
        placed = place_verse(events, [e.lyrics.get(verse, (None,))[0] for e in events], own[i1:i2])
        if not placed:
            continue
        new = {j: (text, syl) for j, text, syl in placed}
        for j, e in enumerate(events):
            old = e.lyrics.get(verse)
            if j in new:
                if old != new[j]:
                    e.lyrics[verse] = new[j]
                    changed += 1
            elif old is not None:
                del e.lyrics[verse]
                changed += 1
    return changed
