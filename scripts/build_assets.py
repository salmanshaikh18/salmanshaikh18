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
        line="#22223A", line2="#33334F", text="#EDEDF5", muted="#9A9AB4",
        dim="#5F5F7E", violet="#8B5CFF", violet2="#B69BFF", cyan="#5CE1FF",
        glow=0.30,
    ),
    "light": dict(
        bg="#F7F6FC", panel="#FFFFFF", head="#F3F1FB", grid="#1A1440", grid_a=0.05,
        line="#E3E0F0", line2="#CDC8E4", text="#0E0B1F", muted="#55536E",
        dim="#8E8BA8", violet="#6A3DF0", violet2="#8F6CFF", cyan="#0A8BAF",
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


def grid_and_glow(s: Svg, w, h, glows, rx=18, pid="g"):
    T = s.T
    s.defs.append(
        f'<clipPath id="{pid}c"><rect width="{w}" height="{h}" rx="{rx}"/></clipPath>'
        f'<pattern id="{pid}p" width="24" height="24" patternUnits="userSpaceOnUse">'
        f'<path d="M24 0H0V24" fill="none" stroke="{T["grid"]}" stroke-opacity="{T["grid_a"]}"/></pattern>'
        f'<radialGradient id="{pid}f" cx="50%" cy="50%" r="60%"><stop offset="0" stop-color="#fff"/>'
        f'<stop offset="1" stop-color="#fff" stop-opacity="0"/></radialGradient>'
        f'<mask id="{pid}m"><rect width="{w}" height="{h}" fill="url(#{pid}f)"/></mask>'
    )
    for i, (cx, cy, r, color) in enumerate(glows):
        s.defs.append(
            f'<radialGradient id="{pid}r{i}" cx="{cx}" cy="{cy}" r="{r}" gradientUnits="userSpaceOnUse">'
            f'<stop offset="0" stop-color="{color}" stop-opacity="{T["glow"]}"/>'
            f'<stop offset="1" stop-color="{color}" stop-opacity="0"/></radialGradient>')
    s.add(f'<g clip-path="url(#{pid}c)"><rect width="{w}" height="{h}" fill="{T["bg"]}"/>')
    for i in range(len(glows)):
        s.add(f'<rect width="{w}" height="{h}" fill="url(#{pid}r{i})"/>')
    s.add(f'<rect width="{w}" height="{h}" fill="url(#{pid}p)" mask="url(#{pid}m)"/></g>')
    s.add(f'<rect x=".5" y=".5" width="{w - 1}" height="{h - 1}" rx="{rx}" fill="none" stroke="{T["line"]}"/>')


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
    "End-to-end product engineering: interfaces, APIs,",
    "data, containers and cloud. Now building with AI agents.",
]
CHAIN = ["UI", "API", "DATA", "CLOUD", "OBSERVE", "AI"]


def hero(T):
    W, H = 960, 420
    s = Svg(W, H, T, "Salman Shaikh, Full Stack Engineer",
            "Building products from interface to infrastructure. End-to-end product engineering "
            "across interfaces, APIs, data, containers and cloud, now building with AI agents.")
    grid_and_glow(s, W, H, [(800, 150, 380, T["violet"]), (80, 440, 340, T["cyan"])])
    s.css.append("""
.rise{animation:rise 1s cubic-bezier(.2,.7,.2,1) both}
.d1{animation-delay:.1s}.d2{animation-delay:.25s}.d3{animation-delay:.4s}.d4{animation-delay:.55s}
@keyframes rise{from{opacity:0;transform:translateY(10px)}}
.flow{stroke-dasharray:2 7;animation:flow 1.6s linear infinite}
@keyframes flow{to{stroke-dashoffset:-18}}
.spin{transform-box:view-box;transform-origin:770px 232px;animation:spin 60s linear infinite}
.spinr{transform-box:view-box;transform-origin:770px 232px;animation:spin 90s linear infinite reverse}
@keyframes spin{to{transform:rotate(360deg)}}
.pulse{transform-box:fill-box;transform-origin:center;animation:pulse 4.8s ease-out infinite;opacity:0}
@keyframes pulse{0%{opacity:.7;transform:scale(1)}40%,100%{opacity:0;transform:scale(3.2)}}
""")
    # top bar
    s.add(f'<path d="M0 44.5H{W}" stroke="{T["line"]}"/>')
    s.add(f'<rect x="28" y="19" width="8" height="8" fill="{T["violet"]}"/>')
    s.text(46, 27.5, "SS-18 / ENGINEERING PROFILE", "mono", 500, 11, T["muted"], ls=1.6)
    s.text(W - 28, 27.5, "MUMBAI, IN   19.07°N  72.87°E", "mono", 400, 11, T["dim"],
           anchor="end", ls=1.4)
    corner_marks(s, 20, 58, W - 20, H - 16)

    # left column
    x = 52
    s.add(f'<g class="rise">')
    s.add(f'<rect x="{x}" y="101" width="3" height="14" fill="{T["violet"]}"/>')
    s.text(x + 13, 112.5, "FULL STACK ENGINEER", "mono", 700, 12, T["violet"], ls=3)
    s.text(x + 13 + text_width("FULL STACK ENGINEER", "mono", 700, 12, 3) + 14, 112.5,
           "2+ YRS IN PRODUCTION", "mono", 400, 12, T["dim"], ls=2)
    s.add("</g>")
    name_w = text_width(NAME, "sans", 700, 74, -2.5)
    assert x + name_w < 600, name_w
    s.add('<g class="rise d1">')
    s.text(x - 3, 192, NAME, "sans", 700, 74, T["text"], ls=-2.5)
    s.add("</g>")
    s.add('<g class="rise d2">')
    s.rich(x, 238, [(t, T[c]) for t, c in TAGLINE], "sans", 500, 23, ls=-0.3)
    for i, line in enumerate(HERO_DESC):
        s.text(x, 280 + i * 22, line, "mono", 400, 13, T["muted"])
    s.add("</g>")

    # chain of layers -> previews the system map
    s.add('<g class="rise d3">')
    cx = x
    y = 352
    for i, label in enumerate(CHAIN):
        tw = text_width(label, "mono", 500, 11, 1.4)
        w = tw + 18
        dashed = label == "AI"
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

    # right: architecture constellation
    ox, oy = 770, 232
    labels = ["UI", "API", "DATA", "CLOUD", "OBS", "AI"]
    r = 108
    s.add(f'<g class="spinr"><circle cx="{ox}" cy="{oy}" r="164" fill="none" stroke="{T["line2"]}" '
          f'stroke-dasharray="1 7"/></g>')
    s.add(f'<g class="spin"><circle cx="{ox}" cy="{oy}" r="146" fill="none" stroke="{T["line"]}" '
          f'stroke-dasharray="40 12 4 12"/></g>')
    s.add(f'<circle cx="{ox}" cy="{oy}" r="62" fill="none" stroke="{T["line"]}"/>')
    pts = []
    for i in range(6):
        a = math.radians(-90 + 60 * i)
        pts.append((ox + r * math.cos(a), oy + r * math.sin(a)))
    hexpath = "M" + " L".join(f"{px:.1f} {py:.1f}" for px, py in pts) + "Z"
    s.add(f'<path d="{hexpath}" fill="none" stroke="{T["line2"]}"/>')
    for i, (px, py) in enumerate(pts):
        col = T["violet"] if i % 2 == 0 else T["cyan"]
        s.add(f'<path d="M{ox} {oy} L{px:.1f} {py:.1f}" stroke="{col}" stroke-opacity=".75" '
              f'stroke-width="1.2" class="flow" style="animation-delay:-{i * .27:.2f}s"/>')
    for i, (px, py) in enumerate(pts):
        ai = labels[i] == "AI"
        col = T["cyan"] if ai else (T["violet"] if i % 2 == 0 else T["cyan"])
        s.add(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="5" fill="none" stroke="{col}" class="pulse" '
              f'style="animation-delay:{i * .8:.1f}s"/>')
        dash = ' stroke-dasharray="2 2"' if ai else ""
        s.add(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="6" fill="{T["bg"]}" stroke="{col}" '
              f'stroke-width="1.6"{dash}/>')
        s.add(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="2" fill="{col}"/>')
        a = math.radians(-90 + 60 * i)
        lx, ly = ox + (r + 24) * math.cos(a), oy + (r + 24) * math.sin(a) + 4
        anchor = "middle" if abs(math.cos(a)) < .2 else ("start" if math.cos(a) > 0 else "end")
        s.text(lx, ly, labels[i], "mono", 500, 10, T["muted"], anchor=anchor, ls=1.4)
    # core
    core = [(ox + 30 * math.cos(math.radians(-90 + 60 * k)),
             oy + 30 * math.sin(math.radians(-90 + 60 * k))) for k in range(6)]
    s.add(f'<circle cx="{ox}" cy="{oy}" r="46" fill="{T["violet"]}" fill-opacity=".10"/>')
    s.add(f'<path d="M{" L".join(f"{a:.1f} {b:.1f}" for a, b in core)}Z" fill="{T["panel"]}" '
          f'stroke="{T["violet"]}" stroke-width="1.6"/>')
    s.text(ox, oy + 7, "SS", "sans", 700, 20, T["text"], anchor="middle", ls=0.5)
    return s


# --------------------------------------------------------------------------
# 2. Section headers
# --------------------------------------------------------------------------
SECTIONS = [
    ("01", "IDENTITY", "how I build"),
    ("02", "SYSTEM MAP", "interface to infrastructure"),
    ("03", "TELEMETRY", "github activity"),
    ("04", "CHANNELS", "open a connection"),
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
    ("TypeScript", "types"), ("React", "ui"), ("Next.js", "ssr, routing"),
    ("Tailwind CSS", "styling"), ("React Native", "mobile")])
M2 = ("M2", "BACKEND SYSTEMS", "CORE", [
    ("Node.js, Express", "services"), ("FastAPI, Python", "python apis"),
    ("REST APIs", "contracts"), ("WebSockets", "realtime"), ("Socket.IO", "events")])
M3 = ("M3", "DATA LAYER", "CORE", [
    ("MongoDB", "documents"), ("PostgreSQL", "relational"), ("Redis", "cache"),
    ("Prisma", "orm")])
M4_STACK = ["AWS", "Docker", "Linux", "Nginx", "GitHub Actions"]
M4_PIPE = ["commit", "build", "test", "image", "deploy"]
M5 = ("M5", "OBSERVABILITY", "OPS", [
    ("Prometheus", "metrics"), ("Grafana", "dashboards"), ("Loki", "logs")])
M6 = ("M6", "AI ENGINEERING", "R&D", [
    ("Python", "language"), ("LangChain, LangGraph", "orchestration"),
    ("RAG", "retrieval"), ("MCP, AI agents", "tool use"),
    ("Qdrant, Pinecone", "vectors"), ("Neo4j", "graph")])


def module(s: Svg, x, y, w, h, spec, rows=True, dashed=False):
    T = s.T
    idx, title, tag, items = spec
    dash = ' stroke-dasharray="5 4"' if dashed else ""
    border = T["cyan"] if dashed else T["line2"]
    cid = f"c{idx}"
    s.defs.append(f'<clipPath id="{cid}"><rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10"/></clipPath>')
    s.add(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" fill="{T["panel"]}"/>')
    s.add(f'<rect x="{x}" y="{y}" width="{w}" height="34" fill="{T["head"]}" clip-path="url(#{cid})"/>')
    s.add(f'<path d="M{x} {y + 34.5}H{x + w}" stroke="{T["line"]}"/>')
    s.add(f'<rect x="{x + .5}" y="{y + .5}" width="{w - 1}" height="{h - 1}" rx="10" fill="none" '
          f'stroke="{border}"{dash}/>')
    s.text(x + 16, y + 22, idx, "mono", 700, 12, T["violet"])
    s.text(x + 44, y + 22, title, "mono", 500, 11, T["text"], ls=1.6)
    tw = text_width(tag, "mono", 500, 9.5, 1.4) + 14
    tcol = T["cyan"] if dashed else T["dim"]
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
    W, H = 960, 826
    s = Svg(W, H, T, "System map: interface to infrastructure",
            "Six engineering modules. M1 Product engineering: TypeScript, React, Next.js, Tailwind CSS, "
            "React Native. M2 Backend systems: Node.js, Express, FastAPI, REST APIs, WebSockets, "
            "Socket.IO. M3 Data layer: MongoDB, PostgreSQL, Redis, Prisma. M4 Cloud and DevOps: AWS, "
            "Docker, Linux, Nginx, GitHub Actions pipeline from commit to deploy. M5 Observability: "
            "Prometheus, Grafana, Loki. M6 AI engineering, marked as active exploration: Python, "
            "LangChain, LangGraph, RAG, MCP, AI agents, Qdrant, Pinecone, Neo4j.")
    grid_and_glow(s, W, H, [(480, 380, 520, T["violet"])], rx=18, pid="b")
    s.css.append("""
.flow{stroke-dasharray:3 6;animation:flow 1.4s linear infinite}
.back{stroke-dasharray:3 6;animation:flow 1.4s linear infinite reverse}
@keyframes flow{to{stroke-dashoffset:-18}}
.stage{animation:stage 6s ease-in-out infinite;opacity:0}
@keyframes stage{0%{opacity:0}6%,16%{opacity:1}26%,100%{opacity:0}}
""")
    # header
    s.text(28, 34, "FIG. 02", "mono", 700, 11, T["violet"], ls=1.6)
    s.text(28 + text_width("FIG. 02", "mono", 700, 11, 1.6) + 14, 34, "INTERFACE TO INFRASTRUCTURE  /  HOW THE PIECES I WORK WITH CONNECT", "mono", 400, 11,
           T["muted"], ls=1.2)
    lx = W - 28
    s.text(lx, 34, "exploring", "mono", 400, 10.5, T["muted"], anchor="end")
    lx -= text_width("exploring", "mono", 400, 10.5) + 8
    s.add(f'<path d="M{lx - 22:.1f} 30.5H{lx:.1f}" stroke="{T["cyan"]}" stroke-width="1.6" stroke-dasharray="4 3"/>')
    lx -= 40
    s.text(lx, 34, "core stack", "mono", 400, 10.5, T["muted"], anchor="end")
    lx -= text_width("core stack", "mono", 400, 10.5) + 8
    s.add(f'<path d="M{lx - 22:.1f} 30.5H{lx:.1f}" stroke="{T["violet"]}" stroke-width="1.6"/>')
    s.add(f'<path d="M0 54.5H{W}" stroke="{T["line"]}"/>')

    # row 1
    y1, h1 = 82, 214
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
        s.add(f'<rect x="{cx}" y="{y2 + 52}" width="{w:.1f}" height="28" rx="6" fill="{T["bg"]}" stroke="{T["line2"]}"/>')
        s.text(cx + 11, y2 + 70.5, tech, "mono", 500, 12, T["text"])
        cx += w + 10
    s.text(44, y2 + 118, "PIPELINE", "mono", 500, 10, T["dim"], ls=1.6)
    px = 128
    stage_w = 92
    for i, st in enumerate(M4_PIPE):
        s.add(f'<rect x="{px}" y="{y2 + 100}" width="{stage_w}" height="28" rx="6" fill="{T["bg"]}" stroke="{T["line2"]}"/>')
        s.add(f'<rect x="{px}" y="{y2 + 100}" width="{stage_w}" height="28" rx="6" fill="{T["violet"]}" '
              f'fill-opacity=".14" stroke="{T["violet"]}" class="stage" style="animation-delay:{i * .9:.1f}s"/>')
        s.text(px + 12, y2 + 118.5, f"{i + 1:02d}", "mono", 700, 10, T["violet"])
        s.text(px + 34, y2 + 118.5, st, "mono", 500, 12, T["text"])
        px += stage_w
        if i < len(M4_PIPE) - 1:
            s.add(f'<path d="M{px + 5} {y2 + 114}H{px + 20}" stroke="{T["violet"]}" stroke-width="1.3"/>')
            s.add(chevron(px + 21, y2 + 114, 3, T["violet"], 1.3))
            px += 28
    s.text(px + 16, y2 + 118.5, "via GitHub Actions", "mono", 400, 10.5, T["dim"])

    # row 3
    y3, h3 = y2 + h2 + 50, 230
    w3 = (W - 48 - 32) / 2
    x5, x6 = 24, 24 + w3 + 32
    s.add(f'<path d="M{x5 + w3 / 2} {y2 + h2 + 3}V{y3 - 3}" stroke="{T["line2"]}" stroke-width="1.2" class="back"/>')
    s.add(f'<circle cx="{x5 + w3 / 2}" cy="{y3}" r="3" fill="{T["violet"]}"/>')
    s.text(x5 + w3 / 2 + 10, y2 + h2 + 29, "metrics + logs", "mono", 400, 10, T["dim"])
    s.add(f'<path d="M{x6 + w3 / 2} {y2 + h2 + 3}V{y3 - 3}" stroke="{T["cyan"]}" stroke-width="1.4" stroke-dasharray="4 4"/>')
    s.add(f'<circle cx="{x6 + w3 / 2}" cy="{y3}" r="3" fill="{T["bg"]}" stroke="{T["cyan"]}" stroke-width="1.4"/>')
    s.text(x6 + w3 / 2 - 10, y2 + h2 + 29, "agents call services via APIs and MCP", "mono", 400, 10, T["dim"],
           anchor="end")
    module(s, x5, y3, w3, h3, M5)
    # M5 signal paths
    fy = y3 + 62 + 3 * 27 + 18
    s.add(f'<path d="M{x5 + 16} {fy - 12}H{x5 + w3 - 16}" stroke="{T["line"]}"/>')
    for k, chain in enumerate([["service", "/metrics", "Prometheus", "Grafana"],
                               ["containers", "stdout", "Loki", "Grafana"]]):
        yy = fy + 14 + k * 30
        cx = x5 + 18
        for j, node in enumerate(chain):
            w = text_width(node, "mono", 400, 10.5) + 14
            last = j == len(chain) - 1
            s.add(f'<rect x="{cx:.1f}" y="{yy - 13}" width="{w:.1f}" height="20" rx="4" fill="{T["bg"]}" '
                  f'stroke="{T["violet"] if last else T["line2"]}"/>')
            s.text(cx + 7, yy + 1, node, "mono", 400, 10.5, T["text"] if last else T["muted"])
            cx += w
            if not last:
                s.add(f'<path d="M{cx + 3:.1f} {yy - 3}H{cx + 13:.1f}" stroke="{T["dim"]}"/>')
                s.add(chevron(cx + 14, yy - 3, 2.6, T["dim"], 1.1))
                cx += 18
    module(s, x6, y3, w3, h3, M6, dashed=True)
    s.text(W - 28, H - 18, "solid = what I build and run   dashed = what I am actively exploring", "mono", 400,
           9.5, T["dim"], anchor="end")
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
    s.add(f'<rect x=".5" y=".5" width="{W - 1}" height="{H - 1}" rx="10" fill="{T["panel"]}" stroke="{T["line2"]}"/>')
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
    s = Svg(W, H, T, "Build it. Ship it. Run it. Then make it smarter.",
            "Building useful products, reliable systems and AI-powered tools.")
    grid_and_glow(s, W, H, [(480, 260, 360, T["violet"])], pid="f")
    s.css.append(".blink{animation:blink 1.1s steps(1) infinite}@keyframes blink{50%{opacity:0}}")
    parts = [("Build it. ", T["text"]), ("Ship it. ", T["text"]), ("Run it. ", T["text"]),
             ("Then make it smarter.", T["violet"])]
    full = "".join(p for p, _ in parts)
    tw = text_width(full, "sans", 600, 30, -0.6)
    x0 = (W - tw) / 2
    s.rich(round(x0, 1), 88, parts, "sans", 600, 30, ls=-0.6)
    s.add(f'<rect x="{x0 + tw + 6:.1f}" y="64" width="12" height="28" fill="{T["cyan"]}" class="blink"/>')
    s.text(W / 2, 122, "useful products  /  reliable systems  /  AI-powered tools", "mono", 400, 12.5,
           T["muted"], anchor="middle", ls=0.4)
    s.add(f'<path d="M40 150.5H{W - 40}" stroke="{T["line"]}"/>')
    s.text(40, 172, "EOF", "mono", 700, 10, T["violet"], ls=1.8)
    s.text(W / 2, 172, "SALMAN SHAIKH  /  SALMANSHAIKH18", "mono", 400, 10, T["dim"], anchor="middle", ls=1.8)
    s.text(W - 40, 172, "MUMBAI, IN", "mono", 400, 10, T["dim"], anchor="end", ls=1.8)
    return s


# --------------------------------------------------------------------------
def main():
    OUT.mkdir(exist_ok=True)
    jobs = [("hero", hero), ("system-map", blueprint), ("footer", footer)]
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
