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
    return sorted({ms[k].marks.volta for k in range(a, b + 1)})


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
    while i < n and guard < 8 * n + 16:
        guard += 1
        m = ms[i].marks
        if m.repeat_start and i != start:
            start, pass_no = i, 1
        if m.volta is not None:
            numbers = _ending_numbers(cs, i)
            wanted = numbers[-1] if jumped else pass_no
            if m.volta != wanted:
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
        if m.repeat_end and not jumped and i not in repeated and (i, pass_no) not in taken:
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


def lyric_line(cs: ChoralScore, steps: list[Step]) -> dict:
    """How lyric lines map to (stanza, pass): a repeated passage may print the words of
    each pass on its own line ("1." and "2." under the same notes).

    Returns {"stanzas": n, "shift": k}: on pass p of stanza v the line is v + (p - 1) * k.
    """
    repeated = {s.index for s in steps if s.pass_no > 1}

    def lines(indices) -> int:
        return max((n for i in indices for evs in cs.measures[i].voices.values()
                    for e in evs for n in e.lyrics), default=0)

    once = lines(i for i in range(len(cs.measures)) if i not in repeated)
    twice = lines(repeated)
    if repeated and twice > once >= 1:
        return {"stanzas": once, "shift": once}
    return {"stanzas": max(once, twice, 1), "shift": 0}
