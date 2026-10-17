#!/usr/bin/env python3
"""
Generates every custom SVG used by the profile README into ../assets/.

    pip install fonttools brotli
    python3 scripts/build_assets.py

Each asset is written twice (`*-dark.svg`, `*-light.svg`) so the README can
swap them with <picture> + prefers-color-scheme, which follows GitHub's theme.

Fonts (SIL OFL 1.1, see scripts/fonts/LICENSE-*): JetBrains Mono and
Space Grotesk. Each SVG embeds a subset containing only the glyphs it uses,
with system font fallbacks if a renderer refuses embedded fonts.

To change copy, colours or tech lists, edit the constants below and re-run.
"""
from __future__ import annotations

import base64
import io
import math
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parent.parent
FONT_DIR = ROOT / "scripts" / "fonts"
OUT = ROOT / "assets"

# --------------------------------------------------------------------------
# Theme
# --------------------------------------------------------------------------
THEMES = {
    "dark": dict(
        bg="#07070D", panel="#0D0D17", head="#12121F", grid="#FFFFFF", grid_a=0.035,
        line="#22223A", line2="#33334F", text="#EDEDF5", muted="#9A9AB4", dim="#5F5F7E",
        violet="#8B5CFF", violet2="#B69BFF", cyan="#5CE1FF", shadow="#000000", shadow_a=0.55,
        glow=0.30,
    ),
    "light": dict(
        bg="#F7F6FC", panel="#FFFFFF", head="#F3F1FB", grid="#1A1440", grid_a=0.05,
        line="#E3E0F0", line2="#CDC8E4", text="#0E0B1F", muted="#55536E", dim="#8E8BA8",
        violet="#6A3DF0", violet2="#8F6CFF", cyan="#0A8BAF", shadow="#2A1A80", shadow_a=0.10,
        glow=0.12,
    ),
}

FONTS = {
    ("mono", 400): "jetbrains-mono-latin-400-normal.woff2",
    ("mono", 500): "jetbrains-mono-latin-500-normal.woff2",
    ("mono", 700): "jetbrains-mono-latin-700-normal.woff2",
    ("sans", 500): "space-grotesk-latin-500-normal.woff2",
    ("sans", 600): "space-grotesk-latin-600-normal.woff2",
    ("sans", 700): "space-grotesk-latin-700-normal.woff2",
}
FAMILY = {
    "mono": "JBM, 'JetBrains Mono', ui-monospace, 'SF Mono', Menlo, Consolas, monospace",
    "sans": "SG, 'Space Grotesk', Inter, 'Segoe UI', system-ui, sans-serif",
}
FACE = {"mono": "JBM", "sans": "SG"}

_metrics: dict = {}


def _font(key):
    if key not in _metrics:
        f = TTFont(FONT_DIR / FONTS[key])
        _metrics[key] = (f.getBestCmap(), f["hmtx"].metrics, f["head"].unitsPerEm)
    return _metrics[key]


def text_width(s: str, fam: str, w: int, size: float, ls: float = 0) -> float:
    cmap, hmtx, upm = _font((fam, w))
    total = 0
    for ch in s:
        g = cmap.get(ord(ch))
        if g is None:
            raise ValueError(f"glyph {ch!r} (U+{ord(ch):04X}) missing from {fam} {w}")
        total += hmtx[g][0]
    return total * size / upm + ls * len(s)


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


# --------------------------------------------------------------------------
# SVG builder
# --------------------------------------------------------------------------
class Svg:
    def __init__(self, w, h, T, title, desc=""):
        self.w, self.h, self.T = w, h, T
        self.title, self.desc = title, desc
        self.defs: list[str] = []
        self.css: list[str] = []
        self.body: list[str] = []
        self.used: dict = {}

    def add(self, s):
        self.body.append(s)

    def text(self, x, y, s, fam="mono", w=400, size=12, fill=None, anchor="start",
             ls=0, cls="", extra=""):
        self.used.setdefault((fam, w), set()).update(s)
        fill = fill or self.T["text"]
        a = f' text-anchor="{anchor}"' if anchor != "start" else ""
        l = f' letter-spacing="{ls}"' if ls else ""
        c = f' class="{cls}"' if cls else ""
        self.add(f'<text x="{x:.1f}" y="{y:.1f}" font-family="{FACE[fam]}" font-weight="{w}" '
                 f'font-size="{size}" fill="{fill}" xml:space="preserve"{a}{l}{c}{extra}>{esc(s)}</text>')

    def rich(self, x, y, parts, fam="sans", w=500, size=20, ls=0, cls=""):
        """parts: list of (string, fill)."""
        spans = []
        for s, fill in parts:
            self.used.setdefault((fam, w), set()).update(s)
            spans.append(f'<tspan fill="{fill}">{esc(s)}</tspan>')
        l = f' letter-spacing="{ls}"' if ls else ""
        c = f' class="{cls}"' if cls else ""
        self.add(f'<text x="{x}" y="{y}" font-family="{FACE[fam]}" font-weight="{w}" '
                 f'font-size="{size}" xml:space="preserve"{l}{c}>{"".join(spans)}</text>')

    def _fontface(self):
        out = []
        for (fam, w), chars in sorted(self.used.items()):
            opts = subset.Options()
            opts.flavor = "woff2"
            opts.layout_features = ["kern", "liga", "calt"]
            opts.name_IDs = []
            opts.notdef_outline = False
            font = TTFont(FONT_DIR / FONTS[(fam, w)])
            sub = subset.Subsetter(opts)
            sub.populate(text="".join(sorted(chars)) + " ")
            sub.subset(font)
            buf = io.BytesIO()
            font.flavor = "woff2"
            font.save(buf)
            b64 = base64.b64encode(buf.getvalue()).decode()
            out.append(f"@font-face{{font-family:{FACE[fam]};font-weight:{w};"
                       f"src:url(data:font/woff2;base64,{b64}) format('woff2')}}")
        for fam in ("mono", "sans"):
            out.append(f"text[font-family='{FACE[fam]}']{{font-family:{FAMILY[fam]}}}")
        return "\n".join(out)

    def render(self) -> str:
        css = self._fontface() + "\n" + "\n".join(self.css) + (
            "\n@media (prefers-reduced-motion: reduce){*{animation:none!important}}")
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" height="{self.h}" '
            f'viewBox="0 0 {self.w} {self.h}" role="img" aria-labelledby="t d">\n'
            f'<title id="t">{esc(self.title)}</title><desc id="d">{esc(self.desc)}</desc>\n'
            f"<style>\n{css}\n</style>\n<defs>{''.join(self.defs)}</defs>\n"
            + "\n".join(self.body) + "\n</svg>\n"
        )


def chevron(x, y, size, color, sw=1.4, direction=1):
    """A drawn arrow head '>' (glyph-free so every font renders it)."""
    d = size * direction
    return (f'<path d="M{x - d:.1f} {y - size:.1f} L{x:.1f} {y:.1f} L{x - d:.1f} {y + size:.1f}" '
            f'fill="none" stroke="{color}" stroke-width="{sw}" stroke-linecap="round" '
            f'stroke-linejoin="round"/>')


def grid_and_glow(s: Svg, w, h, glows=(), rx=18, pid="g", grid=True, **_):
    """Near-black base, soft radial violet/cyan glows and a faint centred grid."""
    T = s.T
    s.defs.append(
        f'<clipPath id="{pid}c"><rect width="{w}" height="{h}" rx="{rx}"/></clipPath>'
        f'<pattern id="{pid}p" width="24" height="24" patternUnits="userSpaceOnUse">'
        f'<path d="M24 0H0V24" fill="none" stroke="{T["grid"]}" stroke-opacity="{T["grid_a"]}"/></pattern>'
        f'<radialGradient id="{pid}f" cx="50%" cy="50%" r="60%"><stop offset="0" stop-color="#fff"/>'
        f'<stop offset="1" stop-color="#fff" stop-opacity="0"/></radialGradient>'
        f'<mask id="{pid}m"><rect width="{w}" height="{h}" fill="url(#{pid}f)"/></mask>'
        f'<filter id="soft" x="-20%" y="-20%" width="140%" height="160%"><feGaussianBlur stdDeviation="10"/></filter>'
        f'<linearGradient id="brand" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="{T["violet"]}"/>'
        f'<stop offset="1" stop-color="{T["cyan"]}"/></linearGradient>'
    )
    for i, (cx, cy, r, color) in enumerate(glows):
        s.defs.append(
            f'<radialGradient id="{pid}r{i}" cx="{cx}" cy="{cy}" r="{r}" gradientUnits="userSpaceOnUse">'
            f'<stop offset="0" stop-color="{color}" stop-opacity="{T["glow"]}"/>'
            f'<stop offset="1" stop-color="{color}" stop-opacity="0"/></radialGradient>')
    s.add(f'<g clip-path="url(#{pid}c)"><rect width="{w}" height="{h}" fill="{T["bg"]}"/>')
    for i in range(len(glows)):
        s.add(f'<rect width="{w}" height="{h}" fill="url(#{pid}r{i})"/>')
    if grid:
        s.add(f'<rect width="{w}" height="{h}" fill="url(#{pid}p)" mask="url(#{pid}m)"/>')
    s.add('</g>')
    s.add(f'<rect x=".5" y=".5" width="{w - 1}" height="{h - 1}" rx="{rx}" fill="none" stroke="{T["line"]}"/>')


def glass_panel(s: Svg, x, y, w, h, rx=12, shadow=True):
    """Solid card with a soft neutral drop shadow and a crisp border."""
    T = s.T
    if shadow:
        s.add(f'<rect x="{x + 6}" y="{y + 10}" width="{w - 12}" height="{h - 6}" rx="{rx}" fill="{T["shadow"]}" '
              f'opacity="{T["shadow_a"]}" filter="url(#soft)"/>')
    s.add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{T["panel"]}"/>')
    s.add(f'<rect x="{x + .5}" y="{y + .5}" width="{w - 1}" height="{h - 1}" rx="{rx}" fill="none" stroke="{T["line2"]}"/>')


def perspective_floor(s: Svg, w, h, horizon, vpx=None, pid="fl"):
    """Synthwave-style grid floor; horizontal lines glide toward the viewer."""
    T = s.T
    vpx = vpx if vpx is not None else w / 2
    s.defs.append(
        f'<linearGradient id="{pid}v" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="#fff" stop-opacity="0"/><stop offset=".55" stop-color="#fff" stop-opacity=".9"/>'
        f'<stop offset="1" stop-color="#fff"/></linearGradient>'
        f'<linearGradient id="{pid}h" x1="0" y1="0" x2="1" y2="0">'
        f'<stop offset="0" stop-color="#000"/><stop offset=".2" stop-color="#fff"/>'
        f'<stop offset=".8" stop-color="#fff"/><stop offset="1" stop-color="#000"/></linearGradient>'
        f'<mask id="{pid}mh"><rect width="{w}" height="{h}" fill="url(#{pid}h)"/></mask>'
        f'<mask id="{pid}m"><rect y="{horizon}" width="{w}" height="{h - horizon}" fill="url(#{pid}v)"/></mask>')
    col = T["violet"]
    op = 0.42 if T is THEMES["dark"] else 0.28
    lines = []
    for k in range(-16, 17):
        lines.append(f'<path d="M{vpx + k * 9:.1f} {horizon}L{vpx + k * 120:.1f} {h + 60}"/>')
    ys = [horizon + 4 * (1.42 ** k) for k in range(11)]
    for k in range(len(ys) - 1):
        lines.append(f'<line x1="0" x2="{w}" y1="{ys[k]:.1f}" y2="{ys[k]:.1f}">'
                     f'<animate attributeName="y1" values="{ys[k]:.1f};{ys[k + 1]:.1f}" dur="2.2s" repeatCount="indefinite"/>'
                     f'<animate attributeName="y2" values="{ys[k]:.1f};{ys[k + 1]:.1f}" dur="2.2s" repeatCount="indefinite"/>'
                     f'</line>')
    s.add(f'<g clip-path="url(#gc)"><g mask="url(#{pid}mh)"><g mask="url(#{pid}m)" stroke="{col}" '
          f'stroke-opacity="{op}" stroke-width="1" fill="none">{"".join(lines)}</g></g>'
          f'<path d="M0 {horizon + .5}H{w}" stroke="{T["line2"]}"/></g>')


def corner_marks(s: Svg, x0, y0, x1, y1, n=10, color=None):
    c = color or s.T["line2"]
    p = (f"M{x0} {y0 + n}V{y0}H{x0 + n} M{x1 - n} {y0}H{x1}V{y0 + n} "
         f"M{x1} {y1 - n}V{y1}H{x1 - n} M{x0 + n} {y1}H{x0}V{y1 - n}")
    s.add(f'<path d="{p}" fill="none" stroke="{c}" stroke-width="1.2"/>')


# --------------------------------------------------------------------------
# 1. Hero
# --------------------------------------------------------------------------
NAME = "Salman Shaikh"
TAGLINE = [("Building products from ", "text"), ("interface", "violet"),
           (" to ", "text"), ("infrastructure", "cyan"), (".", "text")]
HERO_DESC = [
    "I build web apps end to end and deploy them myself.",
    "Right now I'm learning AI agents, RAG and system design.",
]
CHAIN = ["FRONTEND", "BACKEND", "DATA", "DEVOPS", "GENAI"]


def hero(T):
    W, H = 960, 460
    s = Svg(W, H, T, "Salman Shaikh, Full Stack Engineer",
            "Building products from interface to infrastructure. End-to-end product engineering "
            "across interfaces, APIs, data, containers and cloud, now building with AI agents.")
    grid_and_glow(s, W, H, [(780, 170, 400, T["violet"]), (80, 480, 340, T["cyan"])])
    perspective_floor(s, W, H, horizon=318)
    s.css.append("""
.glitch{opacity:0;animation:glitch 7s steps(1) infinite}
.glitch.b{animation-delay:.06s}
@keyframes glitch{0%,88%,100%{opacity:0;transform:none;clip-path:inset(0 0 100% 0)}
89%{opacity:.9;transform:translate(-4px,0);clip-path:inset(18% 0 58% 0)}
90.5%{opacity:.9;transform:translate(4px,0);clip-path:inset(62% 0 12% 0)}
92%{opacity:.9;transform:translate(-2px,0);clip-path:inset(38% 0 40% 0)}
93%{opacity:0}}
.scan{animation:scan 9s ease-in-out infinite}
@keyframes scan{0%{transform:translateY(-120px)}60%,100%{transform:translateY(520px)}}
.rise{animation:rise 1s cubic-bezier(.2,.7,.2,1) both}
.d1{animation-delay:.1s}.d2{animation-delay:.25s}.d3{animation-delay:.4s}.d4{animation-delay:.55s}
@keyframes rise{from{transform:translateY(6px)}}
""")
    # top bar
    s.add(f'<path d="M0 44.5H{W}" stroke="{T["line"]}"/>')
    s.add('<rect x="28" y="43.5" width="292" height="2" rx="1" fill="url(#brand)"/>')
    s.add(f'<rect x="28" y="19" width="8" height="8" fill="{T["violet"]}"/>')
    s.text(46, 27.5, "SALMAN SHAIKH  /  ENGINEERING PROFILE", "mono", 500, 11, T["muted"], ls=1.6)
    s.text(W - 28, 27.5, "MUMBAI, IN  /  SALMANSHAIKH.DEV", "mono", 400, 11, T["dim"],
           anchor="end", ls=1.4)
    corner_marks(s, 20, 58, W - 20, H - 16)

    # left column
    x = 52
    s.add(f'<g class="rise">')
    s.add(f'<rect x="{x}" y="101" width="3" height="14" fill="{T["violet"]}"/>')
    s.text(x + 13, 112.5, "FULL STACK DEVELOPER", "mono", 700, 12, T["violet"], ls=3)
    s.text(x + 13 + text_width("FULL STACK DEVELOPER", "mono", 700, 12, 3) + 14, 112.5,
           "2+ YRS IN PRODUCTION", "mono", 400, 12, T["dim"], ls=2)
    s.add("</g>")
    name_w = text_width(NAME, "sans", 700, 74, -2.5)
    assert x + name_w < 600, name_w
    s.add('<g class="rise d1">')
    s.text(x - 3, 192, NAME, "sans", 700, 74, T["text"], ls=-2.5)
    s.text(x - 3, 192, NAME, "sans", 700, 74, T["violet"], ls=-2.5, cls="glitch")
    s.text(x - 3, 192, NAME, "sans", 700, 74, T["cyan"], ls=-2.5, cls="glitch b")
    s.add("</g>")
    s.add('<g class="rise d2">')
    s.rich(x, 238, [(t, T[c]) for t, c in TAGLINE], "sans", 500, 22, ls=-0.3)
    assert x + sum(text_width(t, "sans", 500, 22, -0.3) for t, _ in TAGLINE) < 590
    for i, line in enumerate(HERO_DESC):
        s.text(x, 280 + i * 22, line, "mono", 400, 13, T["muted"])
    s.add("</g>")

    # chain of layers -> previews the system map
    s.add('<g class="rise d3">')
    cx = x
    y = 372
    for i, label in enumerate(CHAIN):
        tw = text_width(label, "mono", 500, 11, 1.4)
        w = tw + 18
        dashed = label == "GENAI"
        dash = ' stroke-dasharray="3 3"' if dashed else ""
        col = T["cyan"] if dashed else T["line2"]
        s.add(f'<rect x="{cx}" y="{y}" width="{w:.1f}" height="24" rx="5" fill="{T["panel"]}" '
              f'stroke="{col}"{dash}/>')
        s.text(cx + 9, y + 16, label, "mono", 500, 11, T["cyan"] if dashed else T["text"], ls=1.4)
        cx += w
        if i < len(CHAIN) - 1:
            s.add(f'<path d="M{cx + 4} {y + 12}H{cx + 16}" stroke="{T["violet"]}" stroke-width="1.2"/>')
            s.add(chevron(cx + 17, y + 12, 3, T["violet"], 1.2))
            cx += 22
    s.add("</g>")

    # right: code editor + terminal (the stack, written as config)
    SYN = dict(
        kw=T["violet2"] if T is THEMES["dark"] else T["violet"],
        fn="#FFB547" if T is THEMES["dark"] else "#A85F00",
        str=T["cyan"], key=T["text"], p=T["muted"], c=T["dim"],
    )
    code = [
        [("// salman.config.ts", "c")],
        [("export default ", "kw"), ("defineStack", "fn"), ("({", "p")],
        [("  frontend", "key"), (": [", "p"), ('"react"', "str"), (", ", "p"), ('"next"', "str"), (", ", "p"), ('"redux"', "str"), ("],", "p")],
        [("  backend", "key"), (":  [", "p"), ('"node"', "str"), (", ", "p"), ('"express"', "str"), (", ", "p"), ('"fastapi"', "str"), ("],", "p")],
        [("  data", "key"), (":     [", "p"), ('"postgres"', "str"), (", ", "p"), ('"mongo"', "str"), (", ", "p"), ('"redis"', "str"), ("],", "p")],
        [("  devops", "key"), (":   [", "p"), ('"docker"', "str"), (", ", "p"), ('"aws"', "str"), (", ", "p"), ('"actions"', "str"), ("],", "p")],
        [("  genai", "key"), (":    [", "p"), ('"langgraph"', "str"), (", ", "p"), ('"rag"', "str"), (", ", "p"), ('"mcp"', "str"), ("],", "p")],
        [("});", "p")],
    ]
    ex, ey, ew = 608, 74, 328
    lh, fs = 19, 10.3
    eh = 34 + 14 + len(code) * lh + 12
    s.defs.append('<filter id="shadow" x="-20%" y="-20%" width="140%" height="160%">'
                  '<feGaussianBlur stdDeviation="14"/></filter>')
    s.css.append("""
.hl{animation:hl 9.6s steps(1) infinite}
@keyframes hl{0%{transform:translateY(0)}12.5%{transform:translateY(19px)}25%{transform:translateY(38px)}
37.5%{transform:translateY(57px)}50%{transform:translateY(76px)}62.5%{transform:translateY(95px)}
75%{transform:translateY(114px)}87.5%{transform:translateY(133px)}}
.blink{animation:blink 1.1s steps(1) infinite}@keyframes blink{50%{opacity:0}}
""")

    def window(x, y, w, h, title, badge=None):
        glass_panel(s, x, y, w, h, 10)
        s.add(f'<path d="M{x} {y + 10}a10 10 0 0 1 10 -10h{w - 20}a10 10 0 0 1 10 10v20h-{w}z" fill="{T["head"]}"/>')
        s.add(f'<path d="M{x} {y + 30.5}H{x + w}" stroke="{T["line"]}"/>')
        s.add(f'<rect x="{x + .5}" y="{y + .5}" width="{w - 1}" height="{h - 1}" rx="10" fill="none" stroke="{T["line2"]}"/>')
        for k, c in enumerate(("#FF5F57", "#FEBC2E", "#28C840")):
            s.add(f'<circle cx="{x + 16 + k * 14}" cy="{y + 15}" r="4.5" fill="{c}" opacity=".9"/>')
        s.text(x + 66, y + 19.5, title, "mono", 500, 10.5, T["muted"])
        if badge:
            bw = text_width(badge, "mono", 700, 9, 1) + 12
            s.add(f'<rect x="{x + w - 12 - bw:.1f}" y="{y + 8}" width="{bw:.1f}" height="15" rx="4" fill="{SYN["kw"]}" '
                  f'fill-opacity=".14" stroke="{SYN["kw"]}" stroke-opacity=".5"/>')
            s.text(x + w - 12 - bw / 2, y + 19, badge, "mono", 700, 9, SYN["kw"], anchor="middle", ls=1)

    # editor
    window(ex, ey, ew, eh, "salman.config.ts", "TS")
    cy0 = ey + 34 + 14
    s.defs.append(f'<clipPath id="edc"><rect x="{ex}" y="{ey + 31}" width="{ew}" height="{eh - 31}"/></clipPath>')
    s.add(f'<g clip-path="url(#edc)"><rect x="{ex}" y="{cy0 - 13}" width="{ew}" height="{lh}" fill="{T["violet"]}" '
          f'fill-opacity=".10" class="hl"/></g>')
    s.add(f'<path d="M{ex + 34.5} {ey + 31}V{ey + eh - 8}" stroke="{T["line"]}"/>')
    for i, toks in enumerate(code):
        yy = cy0 + i * lh
        s.text(ex + 26, yy, str(i + 1), "mono", 400, fs, T["dim"], anchor="end")
        s.rich(ex + 46, yy, [(t, SYN[k]) for t, k in toks], "mono", 400, fs)
        line_w = sum(text_width(t, "mono", 400, fs) for t, _ in toks)
        assert 46 + line_w < ew - 10, (i, line_w)
    last_w = text_width("});", "mono", 400, fs)
    s.add(f'<rect x="{ex + 46 + last_w + 3:.1f}" y="{cy0 + (len(code) - 1) * lh - 10}" width="6.5" height="13" '
          f'fill="{T["cyan"]}" class="blink"/>')

    # terminal, layered over the editor's corner
    tx, ty, tw_ = 636, ey + eh - 12, 300
    GREEN = "#28C840" if T is THEMES["dark"] else "#13852B"
    term = [
        [("~/salman", T["cyan"]), (" $ ", T["dim"]), ("docker compose up -d", T["text"])],
        [("[+] Running 3/3", T["muted"])],
        [(" web    ", T["text"]), ("next.js   ", T["dim"]), ("Started", GREEN)],
        [(" api    ", T["text"]), ("node/py   ", T["dim"]), ("Started", GREEN)],
        [(" agent  ", T["text"]), ("langgraph ", T["dim"]), ("Started", GREEN)],
    ]
    th = 31 + 10 + len(term) * 16 + 6
    window(tx, ty, tw_, th, "zsh  ~/salman")
    for i, parts in enumerate(term):
        s.rich(tx + 14, ty + 31 + 20 + i * 16, parts, "mono", 400, 10)
    assert ty + th < H - 8, (ty + th, H)
    return s


# --------------------------------------------------------------------------
# 2. Section headers
# --------------------------------------------------------------------------
SECTIONS = [
    ("01", "ABOUT", "who I am"),
    ("02", "ROLES", "what I work on"),
    ("03", "SYSTEM MAP", "how it fits together"),
    ("04", "GITHUB", "recent activity"),
    ("05", "CONTACT", "say hi"),
]


def section(T, num, title, sub):
    W, H = 960, 56
    s = Svg(W, H, T, f"{num} {title.title()}", sub)
    s.css.append(".run{stroke-dasharray:36 2000;animation:run 7s cubic-bezier(.6,0,.4,1) infinite}"
                 "@keyframes run{from{stroke-dashoffset:40}to{stroke-dashoffset:-1000}}")
    s.text(2, 36, num, "sans", 600, 26, T["violet"], ls=-0.5)
    tx = 2 + text_width(num, "sans", 600, 26, -0.5) + 16
    s.add(f'<path d="M{tx - 8} 15V39" stroke="{T["line2"]}"/>')
    s.text(tx + 4, 34, title, "sans", 600, 17, T["text"], ls=3.5)
    sx = tx + 4 + text_width(title, "sans", 600, 17, 3.5) + 14
    s.text(sx, 33.5, f"// {sub}", "mono", 400, 12, T["dim"])
    lx = sx + text_width(f"// {sub}", "mono", 400, 12) + 20
    end = W - 14
    s.add(f'<path d="M{lx:.1f} 28.5H{end}" stroke="{T["line2"]}"/>')
    ticks = " ".join(f"M{xx:.1f} 25V28" for xx in range(int(lx) + 12, end - 6, 16))
    s.add(f'<path d="{ticks}" stroke="{T["line"]}"/>')
    s.add(f'<path d="M{lx:.1f} 28.5H{end}" stroke="{T["violet"]}" stroke-width="2" class="run"/>')
    s.add(f'<rect x="{end - 1}" y="24.5" width="8" height="8" transform="rotate(45 {end + 3} 28.5)" '
          f'fill="{T["bg"]}" stroke="{T["cyan"]}" stroke-width="1.4"/>')
    return s


# --------------------------------------------------------------------------
# 3. Signature: system map blueprint
# --------------------------------------------------------------------------
M1 = ("M1", "PRODUCT ENGINEERING", "CORE", [
    ("TypeScript, JavaScript", "lang"), ("HTML, CSS", "markup"), ("React, Redux", "ui, state"),
    ("Next.js", "ssr, routing"), ("Tailwind CSS", "styling"), ("React Native, Expo", "mobile")])
M2 = ("M2", "BACKEND SYSTEMS", "CORE", [
    ("Node.js, Express", "services"), ("FastAPI, Python", "python apis"),
    ("REST APIs", "contracts"), ("WebSockets", "realtime"), ("Socket.IO", "events")])
M3 = ("M3", "DATA LAYER", "CORE", [
    ("MongoDB", "documents"), ("PostgreSQL", "relational"), ("Redis", "cache"),
    ("Prisma", "orm")])
M4_STACK = ["AWS", "Docker", "Linux", "Nginx", "GitHub Actions"]
M4_PIPE = ["commit", "build", "test", "scan", "image", "deploy"]
M5 = ("M5", "OBSERVABILITY & QUALITY", "OPS", [
    ("Prometheus", "metrics"), ("Grafana", "dashboards"), ("Loki", "logs"),
    ("SonarQube", "code quality")])
M6 = ("M6", "AI ENGINEERING", "R&D", [
    ("Python", "language"), ("LangChain, LangGraph", "orchestration"),
    ("RAG", "retrieval"), ("MCP, AI agents", "tool use"), ("Ollama", "local llms"),
    ("Qdrant, Pinecone", "vectors"), ("Neo4j", "graph"), ("Langfuse", "llm tracing")])


def module(s: Svg, x, y, w, h, spec, rows=True, dashed=False, accent=None):
    T = s.T
    idx, title, tag, items = spec
    dash = ' stroke-dasharray="5 4"' if dashed else ""
    border = accent or (T["cyan"] if dashed else T["line2"])
    cid = f"c{idx}"
    s.defs.append(f'<clipPath id="{cid}"><rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10"/></clipPath>')
    glass_panel(s, x, y, w, h, 10)
    s.add(f'<rect x="{x}" y="{y}" width="{w}" height="34" fill="{T["head"]}" clip-path="url(#{cid})"/>')
    s.add(f'<path d="M{x} {y + 34.5}H{x + w}" stroke="{T["line"]}"/>')
    s.add(f'<rect x="{x + .5}" y="{y + .5}" width="{w - 1}" height="{h - 1}" rx="10" fill="none" '
          f'stroke="{border}"{dash}{' stroke-width="1.5"' if accent else ""}/>')
    s.text(x + 16, y + 22, idx, "mono", 700, 12, T["violet"])
    s.text(x + 44, y + 22, title, "mono", 500, 11, T["text"], ls=1.6)
    tw = text_width(tag, "mono", 500, 9.5, 1.4) + 14
    tcol = accent or (T["cyan"] if dashed else T["dim"])
    s.add(f'<rect x="{x + w - 14 - tw:.1f}" y="{y + 10}" width="{tw:.1f}" height="16" rx="8" fill="none" '
          f'stroke="{tcol}" stroke-opacity=".7"{" stroke-dasharray=\"2 2\"" if dashed else ""}/>')
    s.text(x + w - 14 - tw / 2, y + 21.5, tag, "mono", 500, 9.5, tcol, anchor="middle", ls=1.4)
    if not rows:
        return
    for i, (name, note) in enumerate(items):
        ry = y + 62 + i * 27
        s.add(chevron(x + 22, ry - 4.5, 3.2, T["violet"], 1.3))
        s.text(x + 32, ry, name, "mono", 400, 13, T["text"])
        nw = text_width(name, "mono", 400, 13)
        ow = text_width(note, "mono", 400, 10.5)
        x0, x1 = x + 32 + nw + 8, x + w - 16 - ow - 8
        assert x1 - x0 > 8, (name, note, x1 - x0)
        s.add(f'<path d="M{x0:.1f} {ry - 3.5}H{x1:.1f}" stroke="{T["line2"]}" stroke-dasharray="1 4" '
              f'stroke-linecap="round"/>')
        s.text(x + w - 16, ry, note, "mono", 400, 10.5, T["dim"], anchor="end")


def blueprint(T):
    W, H = 960, 852
    s = Svg(W, H, T, "System map: interface to infrastructure",
            "Six engineering modules. M1 Product engineering: TypeScript, JavaScript, HTML, CSS, React, "
            "Redux, Next.js, Tailwind CSS, React Native, Expo. M2 Backend systems: Node.js, Express, "
            "FastAPI, REST APIs, WebSockets, Socket.IO. M3 Data layer: MongoDB, PostgreSQL, Redis, Prisma. "
            "M4 Cloud and DevOps: AWS, Docker, Linux, Nginx and a GitHub Actions CI/CD pipeline from "
            "commit to deploy. M5 Observability and quality: Prometheus, Grafana, Loki, SonarQube. "
            "M6 AI engineering, marked as active exploration: Python, LangChain, LangGraph, RAG, MCP, "
            "AI agents, Ollama, Qdrant, Pinecone, Neo4j, Langfuse.")
    grid_and_glow(s, W, H, [(480, 380, 520, T["violet"])], rx=18, pid="b")
    s.defs.append('<filter id="mglow" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="12"/></filter>')
    s.css.append("""
.flow{stroke-dasharray:3 6;animation:flow 1.4s linear infinite}
.back{stroke-dasharray:3 6;animation:flow 1.4s linear infinite reverse}
@keyframes flow{to{stroke-dashoffset:-18}}
.stage{animation:stage 6s ease-in-out infinite;opacity:0}
@keyframes stage{0%{opacity:0}6%,16%{opacity:1}26%,100%{opacity:0}}
""")
    # header
    s.text(28, 34, "~/architecture", "mono", 700, 11, T["violet"], ls=1.6)
    s.text(28 + text_width("~/architecture", "mono", 700, 11, 1.6) + 14, 34, "INTERFACE TO INFRASTRUCTURE  /  HOW THE PIECES I WORK WITH CONNECT", "mono", 400, 11,
           T["muted"], ls=1.2)
    s.add(f'<path d="M0 54.5H{W}" stroke="{T["line"]}"/>')

    # row 1
    y1, h1 = 82, 224
    cw, gap = 272, 48
    xs = [24, 24 + cw + gap, 24 + 2 * (cw + gap)]
    for x, spec in zip(xs, (M1, M2, M3)):
        module(s, x, y1, cw, h1, spec)
    for i, label in enumerate(["HTTP/WS", "QUERIES"]):
        gx0 = xs[i] + cw
        gx1 = xs[i + 1]
        my = y1 + 110
        s.text((gx0 + gx1) / 2, my - 18, label, "mono", 500, 8.5, T["dim"], anchor="middle", ls=0.6)
        s.add(f'<path d="M{gx0 + 4} {my - 4}H{gx1 - 6}" stroke="{T["violet"]}" stroke-width="1.4" class="flow"/>')
        s.add(chevron(gx1 - 4, my - 4, 3.5, T["violet"], 1.4))
        s.add(f'<path d="M{gx0 + 6} {my + 6}H{gx1 - 4}" stroke="{T["cyan"]}" stroke-width="1.4" class="back"/>')
        s.add(chevron(gx0 + 4, my + 6, 3.5, T["cyan"], 1.4, direction=-1))
        for gx in (gx0, gx1):
            s.add(f'<circle cx="{gx}" cy="{my + 1}" r="2.5" fill="{T["bg"]}" stroke="{T["line2"]}"/>')

    # row 2: platform
    y2, h2 = y1 + h1 + 50, 150
    for x in xs:
        cx = x + cw / 2
        s.add(f'<path d="M{cx} {y1 + h1 + 3}V{y2 - 3}" stroke="{T["line2"]}" stroke-width="1.2" class="flow"/>')
        s.add(f'<circle cx="{cx}" cy="{y2}" r="3" fill="{T["violet"]}"/>')
    s.text(xs[1] + cw / 2 + 10, y1 + h1 + 29, "ships onto", "mono", 400, 10, T["dim"])
    module(s, 24, y2, W - 48, h2, ("M4", "CLOUD & DEVOPS", "OPS", []), rows=False)
    s.text(44, y2 + 70, "STACK", "mono", 500, 10, T["dim"], ls=1.6)
    cx = 128
    for tech in M4_STACK:
        w = text_width(tech, "mono", 500, 12) + 22
        s.add(f'<rect x="{cx}" y="{y2 + 52}" width="{w:.1f}" height="28" rx="6" fill="{T["panel"]}" stroke="{T["line2"]}"/>')
        s.text(cx + 11, y2 + 70.5, tech, "mono", 500, 12, T["text"])
        cx += w + 10
    s.text(44, y2 + 118, "PIPELINE", "mono", 500, 10, T["dim"], ls=1.6)
    px = 128
    stage_w = 82
    for i, st in enumerate(M4_PIPE):
        s.add(f'<rect x="{px}" y="{y2 + 100}" width="{stage_w}" height="28" rx="6" fill="{T["panel"]}" stroke="{T["line2"]}"/>')
        s.add(f'<rect x="{px}" y="{y2 + 100}" width="{stage_w}" height="28" rx="6" fill="{T["violet"]}" '
              f'fill-opacity=".14" stroke="{T["violet"]}" class="stage" style="animation-delay:{i * .9:.1f}s"/>')
        s.text(px + 12, y2 + 118.5, f"{i + 1:02d}", "mono", 700, 10, T["violet"])
        s.text(px + 31, y2 + 118.5, st, "mono", 500, 12, T["text"])
        px += stage_w
        if i < len(M4_PIPE) - 1:
            s.add(f'<path d="M{px + 5} {y2 + 114}H{px + 20}" stroke="{T["violet"]}" stroke-width="1.3"/>')
            s.add(chevron(px + 21, y2 + 114, 3, T["violet"], 1.3))
            px += 28
    s.text(px + 16, y2 + 118.5, "CI/CD via GitHub Actions", "mono", 400, 10.5, T["dim"])

    # row 3
    y3, h3 = y2 + h2 + 50, 272
    w3 = (W - 48 - 32) / 2
    x5, x6 = 24, 24 + w3 + 32
    s.add(f'<path d="M{x5 + w3 / 2} {y2 + h2 + 3}V{y3 - 3}" stroke="{T["cyan"]}" stroke-width="1.4" stroke-dasharray="4 4"/>')
    s.add(f'<circle cx="{x5 + w3 / 2}" cy="{y3}" r="3" fill="{T["bg"]}" stroke="{T["cyan"]}" stroke-width="1.4"/>')
    s.text(x5 + w3 / 2 + 10, y2 + h2 + 29, "metrics + logs", "mono", 400, 10, T["dim"])
    s.add(f'<path d="M{x6 + w3 / 2} {y2 + h2 + 3}V{y3 - 3}" stroke="{T["cyan"]}" stroke-width="1.4" stroke-dasharray="4 4"/>')
    s.add(f'<circle cx="{x6 + w3 / 2}" cy="{y3}" r="3" fill="{T["bg"]}" stroke="{T["cyan"]}" stroke-width="1.4"/>')
    s.text(x6 + w3 / 2 - 10, y2 + h2 + 29, "agents call services via APIs and MCP", "mono", 400, 10, T["dim"],
           anchor="end")
    module(s, x5, y3, w3, h3, M5, dashed=True, accent=T["cyan"])
    # M5 signal paths
    fy = y3 + 62 + len(M5[3]) * 27 + 18
    s.add(f'<path d="M{x5 + 16} {fy - 12}H{x5 + w3 - 16}" stroke="{T["line"]}"/>')
    for k, chain in enumerate([["service", "/metrics", "Prometheus", "Grafana"],
                               ["containers", "stdout", "Loki", "Grafana"]]):
        yy = fy + 14 + k * 30
        cx = x5 + 18
        for j, node in enumerate(chain):
            w = text_width(node, "mono", 400, 10.5) + 14
            last = j == len(chain) - 1
            s.add(f'<rect x="{cx:.1f}" y="{yy - 13}" width="{w:.1f}" height="20" rx="4" fill="{T["panel"]}" '
                  f'stroke="{T["violet"] if last else T["line2"]}"/>')
            s.text(cx + 7, yy + 1, node, "mono", 400, 10.5, T["text"] if last else T["muted"])
            cx += w
            if not last:
                s.add(f'<path d="M{cx + 3:.1f} {yy - 3}H{cx + 13:.1f}" stroke="{T["dim"]}"/>')
                s.add(chevron(cx + 14, yy - 3, 2.6, T["dim"], 1.1))
                cx += 18
    module(s, x6, y3, w3, h3, M6, dashed=True, accent=T["cyan"])
    return s


# --------------------------------------------------------------------------
# 3b. Signature: roles, laid out like a monorepo
# --------------------------------------------------------------------------
ROLE_COLORS = {
    "dark": dict(fs="#B69BFF", fe="#5CE1FF", be="#9B7BFF", ops="#7FA6FF", ai="#C9B3FF"),
    "light": dict(fs="#6A3DF0", fe="#0A7FA3", be="#6A3DF0", ops="#2F5BD3", ai="#7A4DF0"),
}
FULLSTACK = dict(
    path="~/salman", title="Full Stack Developer",
    desc="I work on every part of an app, from the UI down to the server it runs on.",
    groups=[("languages", ["TypeScript", "JavaScript", "Python"]),
            ("practice", ["System Design", "End-to-end apps"])],
)
ROLES = [
    dict(key="fe", path="apps/web", title="Frontend", tag="CORE",
         desc="Web and mobile UIs with React, Next.js and React Native.",
         groups=[("ui", ["React", "Next.js", "Redux", "Tailwind CSS"]),
                 ("web", ["HTML", "CSS"]),
                 ("mobile", ["React Native", "Expo"])]),
    dict(key="be", path="services/api", title="Backend", tag="CORE",
         desc="REST and realtime APIs, plus the databases behind them.",
         groups=[("runtime", ["Node.js", "Express", "FastAPI"]),
                 ("protocols", ["REST APIs", "WebSockets", "Socket.IO"]),
                 ("data", ["MongoDB", "PostgreSQL", "Redis", "Prisma"])]),
    dict(key="ops", path="infra/", title="DevOps", tag="CORE",
         desc="Servers on AWS, Docker, CI/CD pipelines and monitoring.",
         groups=[("cloud", ["AWS", "Linux", "Nginx"]),
                 ("ship", ["Docker", "GitHub Actions", "CI/CD"]),
                 ("observe", ["Prometheus", "Grafana", "Loki", "SonarQube"])]),
    dict(key="ai", path="agents/", title="GenAI", tag="EXPLORING",
         desc="Agents and RAG apps. Still learning, building as I go.",
         groups=[("orchestrate", ["LangChain", "LangGraph", "MCP", "AI Agents"]),
                 ("retrieve", ["RAG", "Qdrant", "Pinecone", "Neo4j"]),
                 ("run + trace", ["Ollama", "Langfuse"])]),
]


def wrap(text, fam, w, size, maxw):
    lines, cur = [], ""
    for word in text.split():
        t = f"{cur} {word}".strip()
        if text_width(t, fam, w, size) <= maxw:
            cur = t
        else:
            lines.append(cur)
            cur = word
    return lines + [cur]


def chips(s: Svg, x, y, maxw, items, color, dashed_items=(), size=11):
    """Lays out tech chips with wrapping. Returns the y below the last row."""
    T = s.T
    cx, cy, ch = x, y, 24
    for it in items:
        w = text_width(it, "mono", 500, size) + 18
        if cx + w > x + maxw and cx > x:
            cx, cy = x, cy + ch + 6
        dash = ' stroke-dasharray="3 3"' if it in dashed_items else ""
        s.add(f'<rect x="{cx:.1f}" y="{cy}" width="{w:.1f}" height="{ch}" rx="6" fill="{color}" '
              f'fill-opacity=".08" stroke="{color}" stroke-opacity=".45"{dash}/>')
        s.text(cx + 9, cy + 16, it, "mono", 500, size, T["text"])
        cx += w + 6
    return cy + ch


def role_panel(s: Svg, x, y, w, role, C, height=None, measure=False):
    """Draws (or measures) one role panel. Returns its natural height."""
    T = s.T
    col = C[role["key"]]
    out = s if not measure else Svg(10, 10, T, "")
    pad = 16
    dashed = role["tag"] == "EXPLORING"
    if not measure:
        dash = ' stroke-dasharray="5 4"' if dashed else ""
        cid = f"rp{role['key']}"
        s.defs.append(f'<clipPath id="{cid}"><rect x="{x}" y="{y}" width="{w}" height="{height}" rx="12"/></clipPath>')
        glass_panel(s, x, y, w, height, 12)
        s.add(f'<rect x="{x}" y="{y}" width="{w}" height="40" fill="{T["head"]}" clip-path="url(#{cid})"/>')
        s.add(f'<path d="M{x} {y + 40.5}H{x + w}" stroke="{T["line"]}"/>')
        s.add(f'<rect x="{x + .5}" y="{y + .5}" width="{w - 1}" height="{height - 1}" rx="12" fill="none" '
              f'stroke="{col if dashed else T["line2"]}" stroke-opacity="{.8 if dashed else 1}"{dash}/>')
        s.add(f'<path d="M{x + 14} {y + 1}H{x + w - 14}" stroke="{col}" stroke-width="2" stroke-linecap="round"/>')
        # folder icon + path
        fx, fy = x + pad, y + 15
        s.add(f'<path d="M{fx} {fy + 1}h4l2 2h6v8h-12z" fill="none" stroke="{col}" stroke-width="1.3" '
              f'stroke-linejoin="round"/>')
        s.text(fx + 19, y + 25, role["path"], "mono", 500, 11, T["muted"])
        tw = text_width(role["tag"], "mono", 500, 9, 1.2) + 14
        s.add(f'<rect x="{x + w - pad - tw:.1f}" y="{y + 12}" width="{tw:.1f}" height="17" rx="8.5" fill="none" '
              f'stroke="{col}" stroke-opacity=".75"{" stroke-dasharray=\"2 2\"" if dashed else ""}/>')
        s.text(x + w - pad - tw / 2, y + 24, role["tag"], "mono", 500, 9, col, anchor="middle", ls=1.2)
        s.text(x + pad, y + 72, role["title"], "sans", 700, 24, T["text"], ls=-0.6)
    yy = y + 92
    for line in wrap(role["desc"], "mono", 400, 10.5, w - 2 * pad):
        if not measure:
            s.text(x + pad, yy, line, "mono", 400, 10.5, T["muted"])
        yy += 16
    yy += 10
    for label, items in role["groups"]:
        if not measure:
            s.text(x + pad, yy + 4, f"// {label}", "mono", 500, 9.5, T["dim"], ls=0.6)
        yy = chips(out, x + pad, yy + 12, w - 2 * pad, items, col) + 16
    return yy - y + 4


def roles(T):
    C = ROLE_COLORS["dark" if T is THEMES["dark"] else "light"]
    W = 960
    M, GAP = 24, 14
    cw = (W - 2 * M - 3 * GAP) / 4
    BY, BH = 72, 132
    RY = BY + BH + 46
    ph = max(role_panel(Svg(10, 10, T, ""), 0, 0, cw, r, C, measure=True) for r in ROLES)
    H = RY + ph + 58
    desc = ["Full Stack Developer: " + "; ".join(f"{g}: {', '.join(i)}" for g, i in FULLSTACK["groups"])]
    for r in ROLES:
        desc.append(f"{r['title']} ({r['tag'].lower()}): " +
                    "; ".join(f"{g}: {', '.join(i)}" for g, i in r["groups"]))
    s = Svg(W, H, T, "Roles: full stack, frontend, backend, DevOps and GenAI", ". ".join(desc) + ".")
    grid_and_glow(s, W, H, [(220, 80, 420, C["fs"]), (760, H, 460, T["violet"])], pid="ro")
    s.css.append("""
.flow{stroke-dasharray:3 6;animation:flow 1.4s linear infinite}
@keyframes flow{to{stroke-dashoffset:-18}}
.blink{animation:blink 1.1s steps(1) infinite}@keyframes blink{50%{opacity:0}}
""")
    # header strip
    s.text(28, 34, "$ tree ~/salman -L 2", "mono", 500, 11, T["violet"], ls=0.4)
    s.add(f'<rect x="{28 + text_width("$ tree ~/salman -L 2", "mono", 500, 11, 0.4) + 6:.1f}" y="24" '
          f'width="7" height="13" fill="{T["cyan"]}" class="blink"/>')
    s.text(W - 28, 34, "frontend  /  backend  /  devops  /  genai", "mono", 400, 10.5, T["dim"], anchor="end", ls=1)
    s.add(f'<path d="M0 54.5H{W}" stroke="{T["line"]}"/>')

    # full stack banner
    bx, bw = M, W - 2 * M
    col = C["fs"]
    s.defs.append(f'<clipPath id="bnr"><rect x="{bx}" y="{BY}" width="{bw}" height="{BH}" rx="12"/></clipPath>')
    glass_panel(s, bx, BY, bw, BH, 12)
    s.add(f'<rect x="{bx}" y="{BY}" width="5" height="{BH}" fill="{col}" clip-path="url(#bnr)"/>')
    s.add(f'<rect x="{bx + .5}" y="{BY + .5}" width="{bw - 1}" height="{BH - 1}" rx="12" fill="none" stroke="{T["line2"]}"/>')
    lx = bx + 28
    s.add(f'<path d="M{lx} {BY + 21}h4l2 2h6v8h-12z" fill="none" stroke="{col}" stroke-width="1.3" stroke-linejoin="round"/>')
    s.text(lx + 19, BY + 31, FULLSTACK["path"], "mono", 500, 11, T["muted"])
    s.text(lx + 19 + text_width(FULLSTACK["path"], "mono", 500, 11) + 10, BY + 31, "root", "mono", 400, 10, T["dim"])
    s.text(lx - 2, BY + 72, FULLSTACK["title"], "sans", 700, 32, T["text"], ls=-0.9)
    for i, line in enumerate(wrap(FULLSTACK["desc"], "mono", 400, 11, 380)):
        s.text(lx, BY + 98 + i * 17, line, "mono", 400, 11, T["muted"])
    gx = bx + 470
    gy = BY + 30
    for label, items in FULLSTACK["groups"]:
        s.text(gx, gy, f"// {label}", "mono", 500, 9.5, T["dim"], ls=0.6)
        gy = chips(s, gx, gy + 9, bw - (gx - bx) - 24, items, col,
                   dashed_items=("System Design",)) + 22

    # connectors banner -> roles
    trunk = BY + BH + 22
    s.add(f'<path d="M{W / 2} {BY + BH}V{trunk}" stroke="{T["line2"]}"/>')
    xs = [M + i * (cw + GAP) for i in range(4)]
    s.add(f'<path d="M{xs[0] + cw / 2:.1f} {trunk}H{xs[3] + cw / 2:.1f}" stroke="{T["line2"]}"/>')
    for x, r in zip(xs, ROLES):
        cxm = x + cw / 2
        c = C[r["key"]]
        s.add(f'<path d="M{cxm:.1f} {trunk}V{RY - 3}" stroke="{c}" stroke-width="1.4" class="flow"/>')
        s.add(f'<circle cx="{cxm:.1f}" cy="{trunk}" r="3" fill="{T["bg"]}" stroke="{c}" stroke-width="1.4"/>')
        role_panel(s, x, RY, cw, r, C, height=ph)
    s.add(f'<circle cx="{W / 2}" cy="{trunk}" r="3.5" fill="{col}"/>')

    s.text(W - 28, H - 20, "solid = what I build and ship   dashed = what I am actively exploring",
           "mono", 400, 9.5, T["dim"], anchor="end")
    return s


# --------------------------------------------------------------------------
# 4. Link buttons
# --------------------------------------------------------------------------
BUTTONS = [
    ("portfolio", "PORTFOLIO", "salmanshaikh.dev"),
    ("linkedin", "LINKEDIN", "in/salmandev18"),
    ("email", "EMAIL", "dev.salmanshaikh@gmail.com"),
]


def button(T, key, label, value):
    W, H = 300, 58
    s = Svg(W, H, T, f"{label.title()}: {value}")
    grid_and_glow(s, W, H, [(30, 60, 160, T["violet"]), (W - 20, 0, 160, T["cyan"])], rx=12, pid="bt",
                  grid=False, extra_blob=False)
    glass_panel(s, 0, 0, W, H, 12)
    s.add(f'<rect x="14" y="14" width="30" height="30" rx="7" fill="{T["violet"]}" fill-opacity=".12" '
          f'stroke="{T["violet"]}" stroke-opacity=".5"/>')
    c = T["violet"]
    if key == "portfolio":
        icon = (f'<circle cx="29" cy="29" r="8" fill="none" stroke="{c}" stroke-width="1.4"/>'
                f'<ellipse cx="29" cy="29" rx="3.6" ry="8" fill="none" stroke="{c}" stroke-width="1.2"/>'
                f'<path d="M21 29H37" stroke="{c}" stroke-width="1.2"/>')
    elif key == "linkedin":
        icon = (f'<rect x="21.5" y="21.5" width="15" height="15" rx="3" fill="none" stroke="{c}" stroke-width="1.4"/>'
                f'<path d="M25.5 28V33M29 33V28M29 30C29 28 33 27.3 33 30V33" fill="none" stroke="{c}" '
                f'stroke-width="1.4" stroke-linecap="round"/><circle cx="25.5" cy="25.2" r=".9" fill="{c}"/>')
    else:
        icon = (f'<rect x="21" y="23" width="16" height="12" rx="2" fill="none" stroke="{c}" stroke-width="1.4"/>'
                f'<path d="M21.5 24L29 30L36.5 24" fill="none" stroke="{c}" stroke-width="1.4" stroke-linejoin="round"/>')
    s.add(icon)
    s.text(56, 25, label, "mono", 500, 9.5, T["dim"], ls=1.8)
    s.text(56, 42, value, "mono", 500, 13, T["text"])
    assert 56 + text_width(value, "mono", 500, 13) < W - 34
    s.add(f'<path d="M{W - 26} 33L{W - 18} 25M{W - 24} 25H{W - 18}V31" fill="none" stroke="{T["cyan"]}" '
          f'stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>')
    return s


# --------------------------------------------------------------------------
# 5. Footer
# --------------------------------------------------------------------------
def footer(T):
    W, H = 960, 190
    s = Svg(W, H, T, "Got something to build? Let's talk.",
            "Email dev.salmanshaikh@gmail.com or visit salmanshaikh.dev.")
    grid_and_glow(s, W, H, [(480, 260, 360, T["violet"])], pid="f")
    s.css.append(".blink{animation:blink 1.1s steps(1) infinite}@keyframes blink{50%{opacity:0}}")
    parts = [("Got something to build? ", T["text"]), ("Let's talk.", "url(#brand)")]
    full = "".join(p for p, _ in parts)
    tw = text_width(full, "sans", 600, 30, -0.6)
    x0 = (W - tw) / 2
    s.rich(round(x0, 1), 88, parts, "sans", 600, 30, ls=-0.6)
    s.add(f'<rect x="{x0 + tw + 6:.1f}" y="64" width="12" height="28" fill="{T["cyan"]}" class="blink"/>')
    s.text(W / 2, 122, "dev.salmanshaikh@gmail.com  /  salmanshaikh.dev", "mono", 400, 12.5,
           T["muted"], anchor="middle", ls=0.4)
    s.add(f'<path d="M40 150.5H{W - 40}" stroke="{T["line"]}"/>')
    s.text(40, 172, "EOF", "mono", 700, 10, T["violet"], ls=1.8)
    s.text(W / 2, 172, "SALMAN SHAIKH  /  SALMANSHAIKH18", "mono", 400, 10, T["dim"], anchor="middle", ls=1.8)
    s.text(W - 40, 172, "MUMBAI, IN", "mono", 400, 10, T["dim"], anchor="end", ls=1.8)
    return s


# --------------------------------------------------------------------------
def main():
    OUT.mkdir(exist_ok=True)
    jobs = [("hero", hero), ("roles", roles), ("system-map", blueprint), ("footer", footer)]
    for num, title, sub in SECTIONS:
        jobs.append((f"section-{num}", lambda T, n=num, t=title, u=sub: section(T, n, t, u)))
    for key, label, value in BUTTONS:
        jobs.append((f"link-{key}", lambda T, k=key, l=label, v=value: button(T, k, l, v)))
    for name, fn in jobs:
        for theme, T in THEMES.items():
            path = OUT / f"{name}-{theme}.svg"
            path.write_text(fn(T).render(), encoding="utf-8")
            print(f"{path.relative_to(ROOT)}  {path.stat().st_size / 1024:.1f} KB")


if __name__ == "__main__":
    main()
