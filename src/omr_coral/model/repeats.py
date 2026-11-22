"""Performance order: the measures in the order they are sung (repeats written out).

    |: A :|           -> A A
    |: A [1. B :| [2. C -> A B A C
    ... D.S. al Coda  -> back to the segno, then from "To Coda" (or the 1st coda sign) to the coda
    ... D.C. al Fine  -> back to the start, stop at "Fine"

Usual reading conventions: after a D.S./D.C. jump repeats are not taken again and the
last ending is played. A jump whose target was not found (Audiveris does not export the
segno or coda signs) is not invented: the music goes on linearly and a warning says so.
"""

from __future__ import annotations

from dataclasses import dataclass

from .score import ChoralScore


@dataclass
class Step:
    index: int  # measure index in the score
    pass_no: int  # 1 the first time through a repeated passage, 2 the second time...


def _ending_numbers(cs: ChoralScore, i: int) -> list[int]:
    """Numbers of the endings of the run of endings that measure i belongs to."""
    ms = cs.measures
    a = i
    while a > 0 and ms[a - 1].marks.volta is not None:
        a -= 1
    b = i
    while b + 1 < len(ms) and ms[b + 1].marks.volta is not None:
        b += 1
    return sorted({x for k in range(a, b + 1) for x in _passes(ms[k].marks)})


def _passes(mk) -> range:
    """The times through that take this ending: 1, or 1 to 6 for an ending printed "1.-6."."""
    return range(mk.volta, (mk.volta_to or mk.volta) + 1)


def performance_order(cs: ChoralScore) -> tuple[list[Step], list[tuple[int, str]]]:
    """(steps, warnings). warnings: (measure index, message).

    A piece may have several D.S. jumps (each with its own segno and coda). Each jump goes to
    the nearest segno before it (or the start for D.C.), leaves at the first "To Coda" after
    that point and lands on the first coda sign after the jump. Inside the coda repeats are
    played again.
    """
    ms = cs.measures
    n = len(ms)
    if not any(m.marks.repeat_end or m.marks.jump or m.marks.volta for m in ms):
        return _with_multirests(cs, [Step(i, 1) for i in range(n)]), []

    steps: list[Step] = []
    warnings: list[tuple[int, str]] = []
    i, start, pass_no = 0, 0, 1
    repeated: set[int] = set()   # repeat-end measures already taken
    used_jumps: set[int] = set()
    taken: set[tuple[int, int]] = set()
    jumped = False               # inside the passage sung again after a D.S./D.C.
    leave_at = coda_at = None    # for "al Coda": where to leave and where the coda starts
    rearmed = False              # the current "al Coda" jump was re-armed by a repeat
    fine_mode = False
    last_coda: tuple | None = None  # (leave, coda) of the last "al Coda" jump taken
    guard = 0
    # a safety stop against a loop, big enough for an ending "1.-12." over the whole piece
    most = max([m.marks.volta_to or m.marks.volta or 1 for m in ms] + [2])
    while i < n and guard < (most + 6) * (n + 2):
        guard += 1
        m = ms[i].marks
        if m.repeat_start and i != start:
            start, pass_no = i, 1
        if m.volta is not None:
            numbers = _ending_numbers(cs, i)
            wanted = numbers[-1] if jumped else pass_no
            if wanted not in _passes(m):
                i += 1
                continue
        steps.append(Step(i, pass_no))
        if jumped and fine_mode and m.fine:
            break
        if jumped and leave_at == i:
            last_coda = (leave_at, coda_at)
            # coming back here through a repeat of the coda: keep counting the passes, so
            # the coda takes its 2nd ending
            i, start, pass_no = coda_at, coda_at, (pass_no if rearmed else 1)
            jumped, leave_at, coda_at, rearmed = False, None, None, False
            continue
        # the last measure of a 1st ending with no :| (the next measure starts the 2nd): back
        # to the start all the same
        implied = (not m.repeat_end and m.volta is not None and i + 1 < n
                   and ms[i + 1].marks.volta is not None and ms[i + 1].marks.volta > max(_passes(m)))
        if (m.repeat_end or implied) and not jumped and i not in repeated and (i, pass_no) not in taken:
            numbers = _ending_numbers(cs, i) if m.volta is not None else []
            if not numbers or any(x > pass_no for x in numbers):
                taken.add((i, pass_no))  # never the same repeat twice on the same pass
                if m.volta is None:
                    repeated.add(i)
                pass_no += 1
                i = start = _repeat_start_for(cs, i)
                # A :| in the coda that goes back into the D.S. passage («Es exaltado»): that
                # passage is sung again up to the "To Coda" sign, and then the coda again.
                if last_coda and i <= last_coda[0] < n and not jumped:
                    jumped, rearmed = True, True
                    leave_at, coda_at = last_coda
                continue
        if m.jump and i not in used_jumps:
            target = _jump_target(cs, i, m.jump, warnings)
            if target is not None and m.jump.endswith("al Coda"):
                leave, coda = _coda_points(cs, target, i)
                if leave is None or coda is None:
                    missing = "la señal «a la Coda» (de dónde se salta)" if leave is None else "la coda 𝄌"
                    warnings.append((i, f"Aquí dice «{m.jump}», pero no se encontró {missing}: la parte no "
                                        f"se repite. Márcala para que se despliegue."))
                    target = None
                else:
                    leave_at, coda_at = leave, coda
            if target is not None:
                used_jumps.add(i)
                jumped, fine_mode = True, m.jump.endswith("al Fine")
                i, start, pass_no = target, target, 1
                continue
        # moving on past a finished repeat (or the last of its endings): a later :| without
        # its own |: goes back to here, and we are on the first pass again
        last_ending = m.volta is not None and (i + 1 >= n or ms[i + 1].marks.volta is None)
        if m.repeat_end or last_ending:
            start, pass_no = i + 1, 1
        i += 1
    return _with_multirests(cs, steps), list(dict.fromkeys(warnings))  # a jump inside a repeat warns once


def _repeat_start_for(cs: ChoralScore, i: int) -> int:
    """Where a :| at measure i goes back to: the nearest |: before it, or the measure after
    the previous repeat's end, or the beginning."""
    ms = cs.measures
    for k in range(i, -1, -1):
        mk = ms[k].marks
        if mk.repeat_start:
            return k
        ends_ending_run = mk.volta is not None and k + 1 < len(ms) and ms[k + 1].marks.volta is None
        if k < i and ((mk.repeat_end and mk.volta is None) or ends_ending_run):
            return k + 1
    return 0


def _jump_target(cs: ChoralScore, i: int, jump: str, warnings: list) -> int | None:
    if jump.startswith("D.C."):
        return 0
    segnos = [k for k in range(i + 1) if cs.measures[k].marks.segno]
    if not segnos:
        warnings.append((i, f"Aquí dice «{jump}», pero no se encontró el segno 𝄋: la parte no se repite. "
                            f"Márcalo para que se despliegue."))
        return None
    return segnos[-1]


def _coda_points(cs: ChoralScore, target: int, jump_at: int) -> tuple[int | None, int | None]:
    """Where to leave ("To Coda" between the target and the jump) and where the coda starts
    (the first coda sign after the jump). Two coda signs and no "To Coda" text: the first,
    inside the passage, marks where to leave. Engravers print that sign above the barline at
    the END of the measure to finish first, so that measure is sung, then the jump
    («Es exaltado»: ⊕ over the end of "rá" — "rá" is sung on the D.S. pass)."""
    ms = cs.measures
    coda = next((k for k in range(jump_at + 1, len(ms)) if ms[k].marks.coda), None)
    leave = next((k for k in range(target, jump_at + 1) if ms[k].marks.to_coda), None)
    if leave is None:
        inner = next((k for k in range(target + 1, jump_at + 1) if ms[k].marks.coda), None)
        if inner is not None:
            leave = inner
    return leave, coda


def _with_multirests(cs: ChoralScore, steps: list[Step]) -> list[Step]:
    """A measure marked as a silence of N measures is sung (counted) N times."""
    out = []
    for s in steps:
        out += [s] * (cs.measures[s.index].marks.multirest or 1)
    return out


def _real_lines(cs: ChoralScore) -> set[int]:
    """Lyric line numbers that are sung text. A stray mark the OCR read under one note
    («A ^» in «Nuestro temor es de Dios») must not make a whole 2nd stanza."""
    from collections import Counter

    count: Counter = Counter()
    for m in cs.measures:
        seen = {}
        for evs in m.voices.values():  # the same syllable on several voices counts once
            for e in evs:
                for n, (text, _) in e.lyrics.items():
                    if any(c.isalpha() for c in text):
                        seen[(n, e.offset)] = 1
        for (n, _off) in seen:
            count[n] += 1
    if not count:
        return set()
    biggest = max(count.values())
    real = {n for n, k in count.items() if k >= max(2, 0.15 * biggest) or n == 1}
    return {n for n in real if n == 1 or not _echoes_line_1(cs, n)}


def _echoes_line_1(cs: ChoralScore, n: int) -> bool:
    """Line n repeats line 1's words wherever it appears: the words of other voices in a
    chorus («¿Cómo podré estar triste?»: the men's «Feliz cantando alegre» under their own
    notes), not another stanza."""
    same = total = syl_same = syl_total = 0
    for m in cs.measures:
        words = {}
        for evs in m.voices.values():
            for e in evs:
                for k, (text, _) in e.lyrics.items():
                    if k in (1, n) and any(c.isalpha() for c in text):
                        words.setdefault(k, {})[e.offset] = text.strip(",.;:!?¡¿ ").lower()
        if words.get(n):
            total += 1
            line, first = words[n], words.get(1, {})
            equal = sum(first.get(off) == t for off, t in line.items())
            same += equal >= len(line) / 2
            syl_same += equal
            syl_total += len(line)
    # and most of its syllables too: two stanzas that share a refrain line («Bus-car a los per-di-dos»
    # in both, «es nuestro gran deber» / «no importa dónde estén» in between) are not an echo
    return total > 0 and same >= 0.6 * total and syl_same >= 0.75 * syl_total


def lyric_line(cs: ChoralScore, steps: list[Step]) -> dict:
    """How lyric lines map to (stanza, pass): a repeated passage may print the words of
    each pass on its own line ("1." and "2." under the same notes).

    Returns {"stanzas": n, "shift": k}: on pass p of stanza v the line is v + (p - 1) * k.
    """
    repeated = {s.index for s in steps if s.pass_no > 1}
    real = _real_lines(cs)

    def lines(indices) -> int:
        return max((n for i in indices for evs in cs.measures[i].voices.values()
                    for e in evs for n in e.lyrics if n in real), default=0)

    # the measure right before a «|:» holds the upbeat into the repeated passage: its words on every
    # line belong to the passes («Buscar a los perdidos»: «Bus-» printed on both lines in c.32)
    upbeat = {i for i in range(len(cs.measures) - 1) if cs.measures[i + 1].marks.repeat_start}
    once = (lines(i for i in range(len(cs.measures)) if i not in repeated and i not in upbeat)
            or min(1, lines(i for i in range(len(cs.measures)) if i not in repeated)))
    twice = lines(repeated)
    if repeated and twice > once >= 1:
        return {"stanzas": once, "shift": once}
    return {"stanzas": max(once, twice, 1), "shift": 0}


def drop_echo_lines(cs: ChoralScore) -> list[int]:
    """Remove lyric lines that only repeat line 1 (other voices' words in a chorus), so they
    are not counted as stanzas; higher lines move down. Returns the removed line numbers."""
    top = cs.verses
    gone = [n for n in range(2, top + 1) if _echoes_line_1(cs, n)]
    if not gone:
        return []
    new_no = {}
    for n in range(1, top + 1):
        if n not in gone:
            new_no[n] = len(new_no) + 1
    for m in cs.measures:
        for evs in m.voices.values():
            for e in evs:
                if e.lyrics:
                    e.lyrics = {new_no[k]: v for k, v in e.lyrics.items() if k in new_no}
    return gone


def _lines_in(m) -> dict[int, dict]:
    """{line: {offset: (text, syllabic)}} of a measure, over all voices."""
    out: dict[int, dict] = {}
    for evs in m.voices.values():
        for e in evs:
            for n, syl in e.lyrics.items():
                if any(c.isalpha() for c in syl[0]):
                    out.setdefault(n, {}).setdefault(e.offset, syl)
    return out


def split_part_lines(cs: ChoralScore, alone: int = 8) -> list[int]:
    """Lines that are other voices' words, not stanzas, moved onto those voices.

    One stanza where, from some point on, the men answer the melody with their own words
    («Cuando la pena»: the tenors sing «No te a-co-bar-des», the basses «No te a-co-bar-des
    fren-te a la pe-na»), printed as extra lines. A line that first appears after at least
    `alone` measures where line 1 was alone is such a line (stanzas start together).
    In a measure with line 1 and another line, the upper staff sings line 1 and the lower
    staff the last other line; with no line 1, everybody sings the other line.
    Returns the line numbers moved (empty: nothing done)."""
    alone_before: dict[int, int] = {}
    seen: set[int] = set()
    count = 0
    for m in cs.measures:
        lines = _lines_in(m)
        for n in lines:
            if n not in seen:
                seen.add(n)
                alone_before[n] = count
        if set(lines) == {1}:
            count += 1
    late = sorted(n for n in seen if n >= 2 and alone_before.get(n, 0) >= alone)
    # stanzas printed after a chorus («Bálsamo existe») start late too, but they lie under
    # the same notes as line 1; the men's own words keep another rhythm, or go alone
    parts = late if late and _own_rhythm(cs, late) else []
    if not parts or len(parts) != len(seen - {1}):
        return []
    for m in cs.measures:
        lines = _lines_in(m)
        others = [n for n in parts if n in lines]
        if not others:
            continue
        upper = lines.get(1) or lines[others[0]]
        lower = lines[others[-1]]
        m.own_words = True
        for v, evs in m.voices.items():
            words = upper if v in ("soprano", "alto") else lower
            for e in evs:
                e.lyrics = {}
            attacks = [e for e in evs if e.takes_syllable]
            if len(attacks) < len(words):  # a slur misread over the notes that carry the words
                attacks = [e for e in evs if e.is_attack]
            _place(words, attacks)
    return parts


def _own_rhythm(cs: ChoralScore, lines_: list[int]) -> bool:
    """These lines go without line 1, or on other notes, in at least half the measures they
    are in (taken together: a line seen in two measures says little on its own)."""
    apart = total = 0
    for m in cs.measures:
        lines = _lines_in(m)
        for n in lines_:
            if n not in lines:
                continue
            total += 1
            first = set(lines.get(1, {}))
            apart += not first or len(first & set(lines[n])) < 0.5 * len(lines[n])
    return total > 0 and apart >= 0.5 * total


def _place(words: dict, attacks: list) -> None:
    """Syllables (by offset) onto a voice's attacks, in order: each on the attack at or just
    before its offset (the words were read under another staff's notes)."""
    j = 0
    for off in sorted(words):
        if j >= len(attacks):
            break
        while j + 1 < len(attacks) and attacks[j + 1].offset <= off:
            j += 1
        attacks[j].lyrics = {1: words[off]}
        j += 1
