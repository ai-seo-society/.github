"""Words as SVG outlines, shaped with HarfBuzz from the fonts vendored in fonts/.

An SVG shown through an <img> tag loads no fonts, and GitHub serves README images
through a proxy that would block them anyway. So every word in the artwork is drawn
as a path: it looks the same in every browser, in the mobile app and offline.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import uharfbuzz as hb
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen

FONT_DIR = Path(__file__).resolve().parent.parent / "fonts"
FAMILIES = {"display": "Outfit.ttf", "mono": "JetBrainsMono.ttf"}
# Code ligatures would turn "->" into an arrow glyph in the mono face; labels stay literal.
FEATURES = {"display": {"kern": True}, "mono": {"kern": True, "calt": False, "liga": False}}


@dataclass(frozen=True)
class Type:
    family: str  # "display" (Outfit) or "mono" (JetBrains Mono)
    weight: int
    size: float  # px in the SVG's own coordinates
    tracking: float = 0.0  # extra space between letters, in em

    def at(self, size: float) -> "Type":
        return Type(self.family, self.weight, size, self.tracking)


def num(v: float) -> str:
    """One decimal, no trailing zero, never "-0": keeps the SVGs small and byte-stable."""
    s = f"{v:.1f}"
    if s.endswith(".0"):
        s = s[:-2]
    return "0" if s == "-0" else s


@lru_cache(maxsize=None)
def _font(family: str, weight: int) -> tuple[hb.Font, int]:
    face = hb.Face(hb.Blob.from_file_path(str(FONT_DIR / FAMILIES[family])))
    font = hb.Font(face)
    font.set_variations({"wght": float(weight)})
    return font, face.upem


def _shape(text: str, t: Type) -> tuple[list[tuple[int, float, float]], float, float]:
    font, upem = _font(t.family, t.weight)
    buf = hb.Buffer()
    buf.add_str(text)
    buf.guess_segment_properties()
    hb.shape(font, buf, FEATURES[t.family])
    scale = t.size / upem
    track = t.tracking * t.size
    glyphs, x = [], 0.0
    for info, pos in zip(buf.glyph_infos, buf.glyph_positions):
        glyphs.append((info.codepoint, x + pos.x_offset * scale, pos.y_offset * scale))
        x += pos.x_advance * scale + track
    width = x - track if glyphs else 0.0
    return glyphs, width, scale


def measure(text: str, t: Type) -> float:
    return _shape(text, t)[1]


def path(text: str, t: Type, x: float, y: float, anchor: str = "start") -> str:
    """The `d` attribute that draws `text` with its baseline at y."""
    glyphs, width, scale = _shape(text, t)
    x0 = x - {"start": 0.0, "middle": width / 2, "end": width}[anchor]
    font, _ = _font(t.family, t.weight)
    pen = SVGPathPen(None, ntos=num)
    for gid, gx, gy in glyphs:
        font.draw_glyph_with_pen(gid, TransformPen(pen, (scale, 0, 0, -scale, x0 + gx, y - gy)))
    return pen.getCommands()


def wrap(text: str, t: Type, width: float) -> list[str]:
    """Greedy word wrap by measured width. A single word wider than `width` gets its own line."""
    lines: list[str] = []
    for word in text.split():
        if lines and measure(f"{lines[-1]} {word}", t) <= width:
            lines[-1] = f"{lines[-1]} {word}"
        else:
            lines.append(word)
    return lines


def fit(text: str, t: Type, width: float, max_lines: int, min_size: float) -> tuple[Type, list[str]]:
    """The largest size (down to min_size) at which `text` wraps into max_lines within width."""
    size = t.size
    while True:
        cur = t.at(size)
        lines = wrap(text, cur, width)
        fits = len(lines) <= max_lines and all(measure(line, cur) <= width for line in lines)
        if fits or size <= min_size:
            return cur, lines
        size -= 2
