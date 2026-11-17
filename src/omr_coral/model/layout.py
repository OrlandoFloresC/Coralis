"""Page geometry of a recognized score: where each system, staff and measure is in the page image.

Only Audiveris provides this (inside its .omr book file). Other engines yield no layout,
and the pipeline then works without image crops.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass
from pathlib import Path


@dataclass
class StaffBox:
    top: float     # y of the top staff line
    bottom: float  # y of the bottom staff line
    left: float
    right: float
    header_stop: float = 0.0  # x where the clef/key/time header ends
    top_line: list = None     # [(x, y), ...] points of the top staff line (lines may bend or tilt)
    bottom_line: list = None  # same for the bottom line

    def top_at(self, x: float) -> float:
        return _interp(self.top_line, x, self.top)

    def bottom_at(self, x: float) -> float:
        return _interp(self.bottom_line, x, self.bottom)


def _interp(points, x: float, default: float) -> float:
    if not points:
        return default
    xs, ys = zip(*sorted(points))
    if len(xs) == 1:
        return ys[0]
    import numpy as np

    return float(np.interp(x, xs, ys))


@dataclass
class LayoutSystem:
    page: int                          # 1-based page number (= page_00N.png)
    stacks: list[tuple[float, float]]  # (left, right) x-range of each measure, in order
    staves: list[StaffBox]             # top to bottom
    interline: float                   # distance between staff lines, in pixels


def _line_y(line: ET.Element) -> float:
    ys = [float(p.get("y")) for p in line.iter("point")]
    return sum(ys) / len(ys) if ys else 0.0


def read_audiveris_layout(omr: Path) -> list[LayoutSystem]:
    systems: list[LayoutSystem] = []
    with zipfile.ZipFile(omr) as z:
        sheets = sorted(
            (n for n in z.namelist() if re.fullmatch(r"sheet#\d+/sheet#\d+\.xml", n)),
            key=lambda n: int(re.search(r"#(\d+)", n).group(1)),
        )
        for name in sheets:
            page = int(re.search(r"#(\d+)", name).group(1))
            root = ET.fromstring(z.read(name))
            il = root.find("./scale/interline")
            interline = float(il.get("main")) if il is not None else 20.0
            for sys_el in root.iter("system"):
                stacks = [(float(s.get("left")), float(s.get("right"))) for s in sys_el.findall("stack")]
                staves = []
                for st in sys_el.iter("staff"):
                    lines = st.find("lines")
                    line_els = lines.findall("line") if lines is not None else []
                    ys = [_line_y(l) for l in line_els]
                    if ys:
                        hdr = st.find("header")
                        stop = float(hdr.get("stop")) if hdr is not None and hdr.get("stop") else 0.0
                        pts = [[(float(q.get("x")), float(q.get("y"))) for q in l.iter("point")] for l in line_els]
                        order = sorted(range(len(ys)), key=lambda i: ys[i])
                        staves.append(StaffBox(min(ys), max(ys), float(st.get("left")), float(st.get("right")),
                                               stop, pts[order[0]], pts[order[-1]]))
                staves.sort(key=lambda s: s.top)
                systems.append(LayoutSystem(page, stacks, staves, interline))
    return systems
