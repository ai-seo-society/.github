"""The profile's artwork as SVG: the header (dark + light), one cover per repository,
and the link buttons.

One design system, one module. Themes swap hues only; layout, spacing, sharp corners
and the semantic colours (SPARK for the mark, ALERT for "something moved") stay fixed.
Everything is a pure function of its arguments: same input, same bytes.
"""
from __future__ import annotations

import hashlib
import math
import random
from html import escape

from .text import Type, fit, measure, num, path

THEMES = {
    "dark": {
        "bg": "#05070F", "panel": "#0A0E1C", "sunken": "#0D1224", "line": "#1A2238",
        "dot": "#1F2848", "ink": "#F5F1EA", "muted": "#98A1B7", "dim": "#46506C",
        "ghost": "#2A3456", "accent": "#F7B538", "glow": "#E8650A", "band": "#16223F",
    },
    "light": {
        "bg": "#FBF8F2", "panel": "#F3EEE4", "sunken": "#ECE5D8", "line": "#E2DACB",
        "dot": "#E0D7C6", "ink": "#0B1020", "muted": "#4B5468", "dim": "#9AA0AE",
        "ghost": "#D8CFBF", "accent": "#C96F00", "glow": "#F59E0B", "band": "#EFE3CC",
    },
}
SPARK = ("#FFC15C", "#FF8A1F", "#E0620A")  # the avatar's pixel star: lit, body, shade
ALERT = "#FF6B3D"


class DoesNotFit(ValueError):
    """A name or kicker is too long to be drawn inside its box."""

HEADER_ALT = "The AI SEO Society: SEO systems, Claude Code skills and self-hosted apps"

DISPLAY = Type("display", 800, 112)
BODY = Type("display", 400, 30)
LABEL = Type("mono", 600, 22, 0.16)

# Motifs a catalog entry may ask for, with the words its cover's alt text uses.
MOTIFS = {
    "dashboard": "a dashboard with KPI tiles, a bar chart and an alert",
    "anomaly": "a search performance line dropping out of its expected band, flagged",
    "rank": "a search result climbing from position five to position one",
    "grid": "a local ranking grid, strongest in the centre",
    "terminal": "a terminal running commands",
    "sparkle": "the pixel star of the AI SEO Society",
}


# ── primitives ───────────────────────────────────────────────────────────────

def el(tag: str, body: str | None = None, **attrs: object) -> str:
    a = "".join(f' {k.rstrip("_").replace("_", "-")}="{_attr(v)}"' for k, v in attrs.items() if v is not None)
    return f"<{tag}{a}/>" if body is None else f"<{tag}{a}>{body}</{tag}>"


def _attr(v: object) -> str:
    if isinstance(v, float):  # coordinates to 0.1 px; opacities and offsets keep two decimals
        s = num(v) if abs(v) >= 1 else f"{v:.2f}".rstrip("0").rstrip(".")
        return "0" if s in ("", "-0") else s
    return escape(str(v), quote=True)


def svg(w: int, h: int, title: str, parts: list[str]) -> str:
    head = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" '
            f'role="img" aria-labelledby="title">')
    return head + el("title", escape(title), id="title") + "".join(parts) + "</svg>\n"


def words(text: str, t: Type, x: float, y: float, fill: str, anchor: str = "start", **attrs: object) -> str:
    return el("path", d=path(text, t, x, y, anchor), fill=fill, **attrs)


def cells_path(cells: list[tuple[float, float]], size: float) -> str:
    return "".join(f"M{num(x)} {num(y)}h{num(size)}v{num(size)}h-{num(size)}z" for x, y in cells)


def seeded(key: str) -> random.Random:
    return random.Random(int.from_bytes(hashlib.sha256(key.encode()).digest()[:8], "big"))


def backdrop(w: int, h: int, c: dict, glow: tuple[float, float, float], fade: str = "right") -> list[str]:
    """Night sky: flat ground, a pixel grid that fades in, one warm glow."""
    gx, gy, gr = glow
    x1, x2 = ("0", "1") if fade == "right" else ("1", "0")
    defs = el("defs", "".join([
        el("pattern", el("rect", x=18, y=18, width=4, height=4, fill=c["dot"]),
           id="dots", width=40, height=40, patternUnits="userSpaceOnUse"),
        el("linearGradient", el("stop", offset=0, stop_color="#fff", stop_opacity=0.15)
           + el("stop", offset=1, stop_color="#fff", stop_opacity=1), id="fade", x1=x1, x2=x2, y1=0, y2=0),
        el("mask", el("rect", width=w, height=h, fill="url(#fade)"), id="fademask"),
        el("radialGradient", el("stop", offset=0, stop_color=c["glow"], stop_opacity=0.42)
           + el("stop", offset=0.45, stop_color=c["glow"], stop_opacity=0.12)
           + el("stop", offset=1, stop_color=c["glow"], stop_opacity=0), id="glow"),
    ]))
    return [
        defs,
        el("rect", width=w, height=h, fill=c["bg"]),
        el("rect", width=w, height=h, fill="url(#dots)", mask="url(#fademask)"),
        el("circle", cx=gx, cy=gy, r=gr, fill="url(#glow)"),
    ]


# ── the mark ─────────────────────────────────────────────────────────────────

def sparkle(cx: float, cy: float, cell: float, arm: int = 7, body: tuple[int, ...] = (7, 3, 2, 1),
            fill: str | None = None) -> str:
    """The pixel star: a cross `arm` cells long with a stepped body, lit from the top left.
    `fill` draws it in one flat colour instead."""
    tones: dict[str, list[tuple[float, float]]] = {tone: [] for tone in ((fill,) if fill else SPARK)}
    for dy in range(-arm, arm + 1):
        half = body[abs(dy)] if abs(dy) < len(body) else 0
        for dx in range(-half, half + 1):
            tone = fill or (SPARK[0] if dx + dy < -1 else SPARK[2] if dx + dy > 1 else SPARK[1])
            tones[tone].append((cx + (dx - 0.5) * cell, cy + (dy - 0.5) * cell))
    return "".join(el("path", d=cells_path(cells, cell), fill=tone) for tone, cells in tones.items() if cells)


def plus(cx: float, cy: float, cell: float, fill: str = SPARK[0]) -> str:
    cells = [(cx + (dx - 0.5) * cell, cy + (dy - 0.5) * cell) for dx, dy in ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1))]
    return el("path", d=cells_path(cells, cell), fill=fill)


# ── header ───────────────────────────────────────────────────────────────────

def header(theme: str) -> str:
    c = THEMES[theme]
    w, h = 1600, 520
    x = 96
    parts = backdrop(w, h, c, (1296, 250, 560))
    rng = seeded("header")
    stars = [(rng.uniform(1010, 1560), rng.uniform(40, 480)) for _ in range(22)]
    parts += [el("rect", x=sx, y=sy, width=6, height=6, fill=c["ink"], opacity=round(rng.uniform(0.15, 0.55), 2))
              for sx, sy in stars if math.dist((sx, sy), (1296, 250)) > 190]
    parts += [
        sparkle(1296, 250, 19),
        plus(1478, 108, 12),
        plus(1118, 404, 8, SPARK[1]),
        el("rect", x=x, y=133, width=44, height=4, fill=c["accent"]),
        words("GITHUB.COM/AI-SEO-SOCIETY", LABEL, x + 62, 143, c["accent"]),
        words("THE AI SEO", DISPLAY, x - 6, 262, c["ink"]),
        words("SOCIETY", DISPLAY, x - 6, 372, c["accent"]),
        el("rect", x=x, y=404, width=312, height=8, fill=c["accent"]),
        words("SEO systems, Claude Code skills and self-hosted apps.", BODY, x, 470, c["muted"]),
    ]
    return svg(w, h, HEADER_ALT, parts)


# ── covers ───────────────────────────────────────────────────────────────────

COVER_W, COVER_H = 1200, 630
PANEL = (620, 64, 1136, 566)  # x0, y0, x1, y1 of the motif window


def cover(repo: str, name: str, kicker: str, motif: str, tag: str | None, tag_style: str) -> str:
    """One repository's card. tag_style: "solid" (premium), "outline", "soon", or "none"
    with tag=None for no corner tag."""
    c = THEMES["dark"]
    rng = seeded(repo)
    glow = rng.choice([(1080, 90, 520), (1100, 560, 520), (900, 40, 480)])
    parts = backdrop(COVER_W, COVER_H, c, glow, fade="left")
    parts.append(el("rect", x=1, y=1, width=COVER_W - 2, height=COVER_H - 2, fill="none", stroke=c["line"], stroke_width=2))

    kick = Type("mono", 600, 34, 0.12)
    parts.append(el("rect", x=64, y=88, width=28, height=4, fill=c["accent"]))
    kick, kick_lines = fit(kicker.upper(), kick, 456, 1, 22)
    if len(kick_lines) > 1 or measure(kicker.upper(), kick) > 456:
        raise DoesNotFit(f"kicker `{kicker}` is too long for the cover; keep it to about 20 characters")
    parts.append(words(kicker.upper(), kick, 108, 102, c["accent"]))
    title, lines = fit(name.upper(), Type("display", 800, 96, -0.005), 500, 3, 56)
    if len(lines) > 3 or any(measure(line, title) > 500 for line in lines):
        raise DoesNotFit(f"name `{name}` does not fit the cover in three lines; shorten it")
    lead = title.size * 1.02
    for i, line in enumerate(lines):
        parts.append(words(line, title, 60, 196 + title.size * 0.72 + i * lead, c["ink"]))
    if tag:
        parts.append(_tag(tag, tag_style, 64, 506, c))

    x0, y0, x1, y1 = PANEL
    window = [el("rect", x=x0, y=y0, width=x1 - x0, height=y1 - y0, fill=c["panel"], stroke=c["line"], stroke_width=2),
              el("rect", x=x0, y=y0, width=x1 - x0, height=44, fill=c["sunken"]),
              el("path", d=cells_path([(x0 + 20 + i * 20, y0 + 17) for i in range(3)], 10), fill=c["dim"])]
    art = MOTIF_DRAW[motif](x0 + 24, y0 + 68, x1 - 24, y1 - 24, rng, c)
    group = "".join(window) + art
    parts.append(el("g", group, opacity=0.42) if tag_style == "soon" else group)
    return svg(COVER_W, COVER_H, f"{name}: {MOTIFS[motif]}", parts)


def _tag(text: str, style: str, x: float, y: float, c: dict) -> str:
    t = Type("mono", 700, 28, 0.1)
    w = measure(text, t) + 48
    h = 58
    if style == "solid":
        box = el("rect", x=x, y=y, width=w, height=h, fill=c["accent"])
        ink = c["bg"]
    else:
        box = el("rect", x=x + 1, y=y + 1, width=w - 2, height=h - 2, fill="none",
                 stroke=c["accent"] if style == "soon" else c["dim"], stroke_width=2,
                 stroke_dasharray="8 6" if style == "soon" else None)
        ink = c["accent"] if style == "soon" else c["muted"]
    return box + words(text, t, x + 24, y + 39, ink)


# Each motif draws inside (x0, y0)-(x1, y1) of the cover's window.

def _anomaly(x0, y0, x1, y1, rng, c):
    w, h = x1 - x0, y1 - y0
    n, k = 30, 21
    mid = y0 + h * 0.42
    base = [mid + math.sin(i * 2 * math.pi / 7) * h * 0.07 - i * h * 0.004 for i in range(n)]
    xs = [x0 + w * i / (n - 1) for i in range(n)]
    ys = [b + rng.uniform(-1, 1) * h * 0.035 + (h * (0.26 + (i - k) * 0.012) if i >= k else 0) for i, b in enumerate(base)]
    band = [(x, b - h * 0.11) for x, b in zip(xs, base)] + [(x, b + h * 0.11) for x, b in reversed(list(zip(xs, base)))]
    grid = "".join(el("rect", x=x0, y=y0 + h * f, width=w, height=2, fill=c["line"]) for f in (0.1, 0.4, 0.7, 1.0))
    pts = lambda seq: " ".join(f"{num(x)},{num(y)}" for x, y in seq)  # noqa: E731
    xk, yk = xs[k], ys[k]
    return "".join([
        grid,
        el("polygon", points=pts(band), fill=c["band"]),
        el("polyline", points=pts(zip(xs[:k], ys[:k])), fill="none", stroke=c["muted"], stroke_width=5, stroke_linejoin="round"),
        el("polyline", points=pts(zip(xs[k - 1:], ys[k - 1:])), fill="none", stroke=ALERT, stroke_width=6, stroke_linejoin="round"),
        el("rect", x=xk - 1, y=y0 + h * 0.1, width=2, height=h * 0.9, fill=ALERT, opacity=0.55),
        el("circle", cx=xk, cy=yk, r=34, fill=ALERT, opacity=0.18),
        el("rect", x=xk - 11, y=yk - 11, width=22, height=22, fill=ALERT),
        el("rect", x=xk - 58, y=y0 - 6, width=116, height=40, fill=ALERT),
        words("ALERT", Type("mono", 800, 22, 0.1), xk, y0 + 22, c["bg"], anchor="middle"),
    ])


def _dashboard(x0, y0, x1, y1, rng, c):
    side = 76
    parts = [el("rect", x=x0, y=y0, width=side, height=y1 - y0, fill=c["sunken"])]
    parts += [el("rect", x=x0 + 18, y=y0 + 22 + i * 38, width=40, height=10, fill=c["accent"] if i == 1 else c["ghost"]) for i in range(6)]
    gx0, gap = x0 + side + 22, 18
    tile_w = (x1 - gx0 - 2 * gap) / 3
    for i in range(3):
        tx = gx0 + i * (tile_w + gap)
        spark = [(tx + 16 + j * (tile_w - 32) / 7, y0 + 96 - rng.uniform(0, 26) - j * 2.5) for j in range(8)]
        parts += [
            el("rect", x=tx, y=y0, width=tile_w, height=118, fill=c["sunken"]),
            el("rect", x=tx + 16, y=y0 + 18, width=tile_w * 0.42, height=8, fill=c["dim"]),
            el("rect", x=tx + 16, y=y0 + 38, width=tile_w * (0.5 + 0.1 * i), height=20, fill=c["ink"]),
            el("polyline", points=" ".join(f"{num(a)},{num(b)}" for a, b in spark), fill="none",
               stroke=c["accent"], stroke_width=4),
        ]
    cy0, cols = y0 + 146, 12
    col_w = (x1 - gx0) / cols
    for i in range(cols):
        hgt = (y1 - cy0 - 64) * min(1.0, 0.22 + i * 0.062 + rng.uniform(0, 0.12))
        parts.append(el("rect", x=gx0 + i * col_w + 5, y=y1 - hgt, width=col_w - 10, height=hgt,
                        fill=c["accent"] if i == cols - 1 else c["ghost"]))
    parts += [el("rect", x=x1 - 132, y=cy0 + 4, width=132, height=40, fill=c["sunken"], stroke=c["line"], stroke_width=2),
              el("rect", x=x1 - 118, y=cy0 + 17, width=14, height=14, fill=ALERT),
              el("rect", x=x1 - 94, y=cy0 + 20, width=78, height=8, fill=c["muted"])]
    return "".join(parts)


def _rank(x0, y0, x1, y1, rng, c):
    """A results page: the result that sat at position five (dashed) now ranks first."""
    rows, parts = 6, []
    step = (y1 - y0) / rows
    lane = x1 - 64  # the climb runs up this column, right of the results
    for i in range(rows):
        ry = y0 + i * step + 10
        hot = i == 0
        tw = (lane - x0 - 96) * (0.92 if hot else rng.uniform(0.55, 0.9))
        if i == 4:
            parts.append(el("rect", x=x0 - 8, y=ry - 12, width=lane - x0 - 16, height=step - 14, fill="none",
                            stroke=c["accent"], stroke_width=2, stroke_dasharray="8 6", opacity=0.7))
        if hot:
            parts += [el("rect", x=x0, y=ry - 4, width=34, height=34, fill=c["accent"]),
                      words("1", Type("mono", 800, 26), x0 + 17, ry + 22, c["bg"], anchor="middle")]
        else:
            parts.append(el("rect", x=x0 + 5, y=ry + 1, width=24, height=24, fill=c["dim"]))
        parts += [
            el("rect", x=x0 + 50, y=ry + 2, width=tw, height=14, fill=c["accent"] if hot else c["ghost"]),
            el("rect", x=x0 + 50, y=ry + 30, width=tw * 0.45, height=8, fill=c["dim"]),
        ]
    # the climb: a pixel trail from row five up to row one, brightening as it rises, and a pixel arrowhead
    top, bottom = y0 + 10 + 60, y0 + 4 * step + 22
    trail = int((bottom - top) // 26)
    for j in range(trail + 1):
        parts.append(el("rect", x=lane + 18, y=bottom - j * 26, width=14, height=14, fill=ALERT,
                        opacity=round(0.25 + 0.75 * j / trail, 2)))
    head = [(lane + 18 + dx * 14, top - 14 * (3 - r)) for r, half in enumerate((0, 1, 2)) for dx in range(-half, half + 1)]
    parts.append(el("path", d=cells_path(head, 14), fill=ALERT))
    return "".join(parts)


def _grid(x0, y0, x1, y1, rng, c):
    parts = [el("rect", x=x0 + i * 96, y=y0, width=78, height=10, fill=c["accent"] if i == 0 else c["ghost"]) for i in range(4)]
    cols, rows, gap = 7, 5, 10
    size = min((x1 - x0 - (cols - 1) * gap) / cols, (y1 - y0 - 40 - (rows - 1) * gap) / rows)
    gx = x0 + (x1 - x0 - cols * size - (cols - 1) * gap) / 2
    gy = y0 + 40
    for r in range(rows):
        for col in range(cols):
            d = math.dist((col, r), ((cols - 1) / 2, (rows - 1) / 2))
            rank = d * 3.2 + rng.uniform(0, 3)
            fill = c["accent"] if rank < 3.5 else "#B9770E" if rank < 7 else c["ghost"] if rank < 10.5 else c["sunken"]
            parts.append(el("rect", x=gx + col * (size + gap), y=gy + r * (size + gap), width=size, height=size, fill=fill))
    cx, cy = gx + 3 * (size + gap) + size / 2, gy + 2 * (size + gap) + size / 2
    parts.append(el("rect", x=cx - 9, y=cy - 9, width=18, height=18, fill=c["bg"]))
    return "".join(parts)


def _terminal(x0, y0, x1, y1, rng, c):
    parts, y = [], y0 + 10
    for i in range(7):
        if i % 3 == 0:
            parts += [words("$", Type("mono", 700, 30), x0, y + 24, c["accent"]),
                      el("rect", x=x0 + 34, y=y + 8, width=(x1 - x0 - 60) * rng.uniform(0.4, 0.8), height=14, fill=c["ink"])]
        else:
            parts.append(el("rect", x=x0 + 34, y=y + 10, width=(x1 - x0 - 60) * rng.uniform(0.3, 0.9), height=10, fill=c["dim"]))
        y += 52
    parts.append(el("rect", x=x0 + 34, y=y + 2, width=18, height=30, fill=c["accent"]))
    return "".join(parts)


def _sparkle(x0, y0, x1, y1, rng, c):
    return sparkle((x0 + x1) / 2, (y0 + y1) / 2, 17) + plus(x1 - 40, y0 + 40, 10)


MOTIF_DRAW = {"dashboard": _dashboard, "anomaly": _anomaly, "rank": _rank, "grid": _grid,
              "terminal": _terminal, "sparkle": _sparkle}
assert MOTIF_DRAW.keys() == MOTIFS.keys()


# ── buttons ──────────────────────────────────────────────────────────────────

BUTTON_H = 72  # shown at half size: 36 px tall, crisp on high-density screens


def button(label: str, style: str) -> str:
    """style: "primary" (amber, carries the mark) or "secondary" (dark, outlined)."""
    c = THEMES["dark"]
    t = Type("display", 600, 30)
    icon = 40 if style == "primary" else 0
    w = round(measure(label, t) + 64 + icon)
    if style == "primary":
        box = el("rect", width=w, height=BUTTON_H, rx=16, fill=c["accent"])
        mark = sparkle(48, 36, 5, arm=3, body=(3, 1), fill=c["bg"])
        ink = c["bg"]
    else:
        box = el("rect", x=1, y=1, width=w - 2, height=BUTTON_H - 2, rx=15, fill=c["panel"], stroke="#2A3352", stroke_width=2)
        mark, ink = "", c["ink"]
    return svg(w, BUTTON_H, label, [box, mark, words(label, t, 32 + icon, 46, ink)])
