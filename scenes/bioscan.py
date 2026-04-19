"""BioScan — layered biosphere cross-section scanner.

A top-to-bottom biosphere cross-section (exosphere → atmosphere → clouds →
canopy → understory → soil → bedrock → ocean → reef → abyss) scrolls past
inside a wireframe grid, flanked by cyberpunk HUD data panels.

Performance: bg_plane is persistent — only rows whose depth-quantised band
changes are redrawn, keeping per-frame cost proportional to descent speed
rather than screen area.

When the HUD is hidden (g), content expands to fill the full terminal width.

Scene-specific controls:
  o / p   cycle palette   (SCAN / NIGHT / THERMAL / DEEP)
  [ / ]   descent speed
  - / =   zoom level      (depth units per screen row)
  g       toggle HUD panels
  x       toggle fossil scan mode (popup specimen windows)
"""

from __future__ import annotations

import math
import random
from typing import Optional

from renderer import Plane, Color, BLACK
from scene_base import Scene


# ── Layout ────────────────────────────────────────────────────────────────────

_HUD_W      = 13   # target HUD margin per side (chars)
_MIN_CONT_W = 12   # minimum content columns between borders

# ── Motion limits ─────────────────────────────────────────────────────────────

_SPD_MIN,  _SPD_MAX,  _SPD_STEP  = 0.03, 2.5, 0.05
_ZOOM_MIN, _ZOOM_MAX, _ZOOM_STEP = 0.1,  5.0, 0.1
_TOTAL_DEPTH = 100.0


# ── Band definitions ──────────────────────────────────────────────────────────

_BANDS = [
    {"name": "EXOSPHERE",  "end":  8.0, "anim": False, "density": 0.07,
     "chars": list("·  .   *  ·  .  "),
     "bold_p": 0.05, "dim_p": 0.85},

    {"name": "ATMOSPHERE", "end": 18.0, "anim": False, "density": 0.15,
     "chars": list("░·∙  .   ·"),
     "bold_p": 0.00, "dim_p": 0.65},

    {"name": "CLOUDS",     "end": 28.0, "anim": True,  "density": 0.55,
     "chars": list("░▒▓~≈ "),
     "bold_p": 0.05, "dim_p": 0.25},

    {"name": "CANOPY",     "end": 40.0, "anim": False, "density": 0.72,
     "chars": list("▲△╫╪┬╦ψ╥"),
     "bold_p": 0.22, "dim_p": 0.08},

    {"name": "UNDERSTORY", "end": 50.0, "anim": False, "density": 0.58,
     "chars": list("├┤╫│┼┬╬╪"),
     "bold_p": 0.10, "dim_p": 0.18},

    {"name": "SOIL",       "end": 58.0, "anim": False, "density": 0.48,
     "chars": list("·∙░▒ .∙"),
     "bold_p": 0.00, "dim_p": 0.55},

    {"name": "BEDROCK",    "end": 68.0, "anim": False, "density": 0.88,
     "chars": list("▄▀▌▐■▪▬"),
     "bold_p": 0.05, "dim_p": 0.18},

    {"name": "OCEAN",      "end": 80.0, "anim": True,  "density": 0.60,
     "chars": list("~≈∽ ≀"),
     "bold_p": 0.05, "dim_p": 0.30},

    {"name": "REEF",       "end": 92.0, "anim": False, "density": 0.52,
     "chars": list("*ψ◆◇❖"),
     "bold_p": 0.30, "dim_p": 0.00},

    {"name": "ABYSS",      "end":100.0, "anim": False, "density": 0.05,
     "chars": list("·  .   ·"),
     "bold_p": 0.00, "dim_p": 0.92},
]

_N_BANDS    = len(_BANDS)
_ANIM_BANDS = {i for i, b in enumerate(_BANDS) if b["anim"]}

_BAND_TEMPS = ["-75°C", "-35°C", "-20°C",  "28°C",  "22°C",
               " 18°C",  "12°C",   "4°C",   "8°C",   "2°C"]
_BAND_PRESS = ["0.000", "0.010", "0.250", "1.020", "1.060",
               "1.100", "1.150", "1.200", "1.220", "1.240"]
_BAND_HUMID = [5,   12,  80,  93,  88,  68,  30, 100, 100, 100]
_BAND_CO2   = [392, 400, 405, 412, 415, 418, 420, 425, 428, 430]
_BAND_O2    = [max(0.0, round(20.9 - i * 1.8, 1)) for i in range(_N_BANDS)]
_BIOTA_OPTS = ["NIL", "LOW", "MED", "HIGH", "DENSE"]


def _get_band(depth: float) -> int:
    d = depth % _TOTAL_DEPTH
    for i, b in enumerate(_BANDS):
        if d < b["end"]:
            return i
    return _N_BANDS - 1


# ── Palettes ──────────────────────────────────────────────────────────────────

def _c(r: int, g: int, b: int) -> Color:
    return Color(r, g, b)


_PALETTES = [
    {
        "name":  "SCAN",
        "hud_l": _c(0, 210, 60),   "hud_r": _c(255, 150, 20),
        "scan":  _c(160, 255, 160),
        "grid":  _c(45,  65,  45), "label": _c(0, 240, 95),
        "bands": [
            _c(10, 12, 48),    # EXOSPHERE
            _c(25, 38, 115),   # ATMOSPHERE
            _c(148, 160, 170), # CLOUDS
            _c(28, 182, 52),   # CANOPY
            _c(18, 112, 32),   # UNDERSTORY
            _c(122, 82, 40),   # SOIL
            _c(70,  55,  55),  # BEDROCK
            _c(15,  45, 155),  # OCEAN
            _c(0,  192, 172),  # REEF
            _c(5,   8,  28),   # ABYSS
        ],
    },
    {
        "name":  "NIGHT",
        "hud_l": _c(40,  80, 200), "hud_r": _c(80,  40, 200),
        "scan":  _c(140, 175, 255),
        "grid":  _c(25,  35,  85), "label": _c(95, 135, 255),
        "bands": [
            _c(5,   5,  20), _c(12,  18,  60), _c(78,  88, 122),
            _c(18,  75,  38), _c(12,  50,  24), _c(60,  45,  35),
            _c(40,  35,  42), _c(8,   25, 102), _c(25, 102, 122),
            _c(3,   5,  20),
        ],
    },
    {
        "name":  "THERMAL",
        "hud_l": _c(255, 80,   0), "hud_r": _c(255, 205,  0),
        "scan":  _c(255, 255, 195),
        "grid":  _c(78,  35,   0), "label": _c(255, 172,  0),
        "bands": [
            _c(5,  0,  22), _c(22,  0,  70), _c(62,  40,  85),
            _c(182, 80,  0), _c(142, 58,  0), _c(202,  98,  0),
            _c(222, 38,  0), _c(0,  18, 202), _c(0,  178, 202),
            _c(0,   5,  82),
        ],
    },
    {
        "name":  "DEEP",
        "hud_l": _c(0,  222, 222), "hud_r": _c(218,  0, 202),
        "scan":  _c(255, 255, 255),
        "grid":  _c(52,  52,  52), "label": _c(222, 222,  0),
        "bands": [
            _c(12,  0,  35), _c(30,   0,  88), _c(182, 182, 202),
            _c(0,  222,  80), _c(0,  152,  60), _c(152,  88,  30),
            _c(90,  90,  90), _c(0,   80, 202), _c(202,  0,  202),
            _c(5,   0,  32),
        ],
    },
]

_PAL_NAMES = [p["name"] for p in _PALETTES]


# ── Deterministic cell hash ───────────────────────────────────────────────────

def _dhash(a: int, b: int, c: int = 0) -> int:
    v = (a * 7919 + b * 6271 + c * 4999) & 0xFFFFFFFF
    v ^= v >> 16
    v  = (v * 0x45d9f3b) & 0xFFFFFFFF
    v ^= v >> 15
    return v


# ── Fossil specimens ──────────────────────────────────────────────────────────

_FOSSILS = [
    {
        "name": "AMMONITE",
        "art": [
            r"     .-----.     ",
            r"    / .---. \    ",
            r"   / / .~. \ \   ",
            r"  | | ( o ) | |  ",
            r"   \ \ '~' / /   ",
            r"    \ '---' /    ",
            r"     '-----'     ",
        ],
    },
    {
        "name": "TRILOBITE",
        "art": [
            r"   ___________   ",
            r"  /  ___|___  \  ",
            r" / (o)     (o) \ ",
            r" |_____________| ",
            r" |=============| ",
            r" |=============| ",
            r"  \_______|___/  ",
            r"      |||||      ",
        ],
    },
    {
        "name": "NAUTILUS",
        "art": [
            r"    .--------.   ",
            r"   / .------. \  ",
            r"  | / .----. \ | ",
            r"  | | ( oo ) | | ",
            r"  | \ '----' / | ",
            r"   \ '------' /  ",
            r"    '--------'   ",
        ],
    },
    {
        "name": "SHARK TOOTH",
        "art": [
            r"        /\       ",
            r"       /  \      ",
            r"      /    \     ",
            r"     /  ~~  \    ",
            r"    /  ~~~~  \   ",
            r"   /__________\  ",
            r"   \          /  ",
            r"    '--.  .--'   ",
        ],
    },
    {
        "name": "FERN FROND",
        "art": [
            "          |      ",
            "         /|\\     ",
            "        / | \\    ",
            "       /  |  \\   ",
            "      /~~ | ~~\\  ",
            "     /    |    \\ ",
            "    /~~~~~|~~~~~\\",
            "~~~~~~~~~~~~~~~~~~~~",
        ],
    },
    {
        "name": "CRINOID",
        "art": [
            r"  ~\~~/~\~~/~\~  ",
            r"   \|/  \|/  \|/ ",
            r"    |    |    |   ",
            r"    |    |    |   ",
            r"     \   |   /    ",
            r"      \  |  /     ",
            r"       \ | /      ",
            r"        \|/       ",
            r"        ===       ",
        ],
    },
    {
        "name": "SEA URCHIN",
        "art": [
            r"    \ | | | /    ",
            r"   --\     /--   ",
            r"  -- ( ~~~ ) --  ",
            r"   --/     \--   ",
            r"    / | | | \    ",
        ],
    },
    {
        "name": "BIVALVE",
        "art": [
            r"      _____      ",
            r"    /       \    ",
            r"   / ~~~~~~~ \   ",
            r"  | ~~~ o ~~~ |  ",
            r"   \ ~~~~~~~ /   ",
            r"    \_______/    ",
        ],
    },
]


class _FossilWindow:
    """A popup specimen window: bordered box with title + ASCII fossil art.

    Lifecycle: fade_in → hold → fade_out, writing to the overlay plane.
    Colors dim smoothly toward BLACK outside the hold phase.
    """

    _FADE_IN  = 6
    _HOLD     = 45
    _FADE_OUT = 8

    def __init__(self, fossil: dict, r0: int, c0: int,
                 border_color: Color, art_color: Color):
        self.fossil      = fossil
        self.r0          = r0
        self.c0          = c0
        self.border_color = border_color
        self.art_color    = art_color
        self.age          = 0
        self.total        = self._FADE_IN + self._HOLD + self._FADE_OUT

        art           = fossil["art"]
        self.art_h    = len(art)
        self.art_w    = max(len(row) for row in art)
        title         = f"[ FOSSIL SCAN: {fossil['name']} ]"
        self.win_w    = max(self.art_w + 4, len(title) + 2)
        self.win_h    = self.art_h + 4   # top border + title + separator + art + bottom
        self._title   = title

    def update(self) -> None:
        self.age += 1

    def is_done(self) -> bool:
        return self.age >= self.total

    def _alpha(self) -> float:
        if self.age < self._FADE_IN:
            return self.age / self._FADE_IN
        if self.age < self._FADE_IN + self._HOLD:
            return 1.0
        return 1.0 - (self.age - self._FADE_IN - self._HOLD) / self._FADE_OUT

    def render(self, plane: Plane) -> None:
        alpha = self._alpha()
        if alpha < 0.04:
            return

        bc  = self.border_color.lerp(BLACK, 1.0 - alpha)
        tc  = self.art_color.lerp(BLACK, 1.0 - alpha)
        r0  = self.r0
        c0  = self.c0
        ww  = self.win_w
        art = self.fossil["art"]

        def _put(row: int, col: int, ch: str,
                 fg: Color, bold: bool = False, dim: bool = False) -> None:
            if 0 <= row < plane.h - 1 and 0 <= col < plane.w:
                plane.put_char(row, col, ch, fg=fg, bg=BLACK, bold=bold, dim=dim)

        # Top border
        _put(r0, c0, "┌", bc)
        for ci in range(1, ww - 1):
            _put(r0, c0 + ci, "─", bc)
        _put(r0, c0 + ww - 1, "┐", bc)

        # Title row
        _put(r0 + 1, c0, "│", bc)
        title_cell = self._title.center(ww - 2)[:ww - 2]
        for ci, ch in enumerate(title_cell):
            _put(r0 + 1, c0 + 1 + ci, ch, tc, bold=True)
        _put(r0 + 1, c0 + ww - 1, "│", bc)

        # Separator
        _put(r0 + 2, c0, "├", bc)
        for ci in range(1, ww - 1):
            _put(r0 + 2, c0 + ci, "─", bc, dim=True)
        _put(r0 + 2, c0 + ww - 1, "┤", bc)

        # Art rows
        for ri, art_row in enumerate(art):
            row = r0 + 3 + ri
            _put(row, c0, "│", bc)
            padded = art_row.ljust(ww - 2)[:ww - 2]
            for ci, ch in enumerate(padded):
                _put(row, c0 + 1 + ci, ch, tc)
            _put(row, c0 + ww - 1, "│", bc)

        # Bottom border
        bot = r0 + 3 + len(art)
        _put(bot, c0, "└", bc)
        for ci in range(1, ww - 1):
            _put(bot, c0 + ci, "─", bc)
        _put(bot, c0 + ww - 1, "┘", bc)


# ── Scene ─────────────────────────────────────────────────────────────────────

class BioScan(Scene):
    name = "BioScan"

    def __init__(self):
        self._bg_plane:      Optional[Plane] = None
        self._grid_plane:    Optional[Plane] = None
        self._hud_plane:     Optional[Plane] = None
        self._fossil_plane:  Optional[Plane] = None

        self._h = self._w = 0
        self._t = 0

        # Motion
        self._depth  = 0.0
        self._speed  = 0.30
        self._zoom   = 1.0

        # Scan beam — fractional row position
        self._scan_y = 0.0

        # Persistent row state: row → band_idx last drawn
        self._row_band: dict[int, int] = {}

        # HUD / palette
        self._hud_on      = True
        self._palette_idx = 0

        # Fossil scan mode
        self._fossil_mode  = False
        self._fossils:     list = []   # active _FossilWindow instances
        self._fossil_t     = 0
        self._fossil_queue = list(range(len(_FOSSILS)))
        random.shuffle(self._fossil_queue)

    # ── Layout ────────────────────────────────────────────────────────────────

    def _layout(self, w: int) -> tuple[int, int, int, int]:
        """Return (grid_l, c_start, c_end, grid_r).

        When the HUD is off, content expands to fill the full terminal width.
        grid_l / grid_r : vertical wireframe border columns
        c_start / c_end : content columns [c_start, c_end)
        """
        if not self._hud_on:
            return 0, 1, w - 1, w - 1
        hud_w   = min(_HUD_W, max(0, (w - _MIN_CONT_W - 2) // 2))
        grid_l  = hud_w
        c_start = hud_w + 1
        c_end   = w - hud_w - 1
        grid_r  = w - hud_w - 1
        return grid_l, c_start, c_end, grid_r

    # ── Palette helpers ───────────────────────────────────────────────────────

    def _pal(self) -> dict:
        return _PALETTES[self._palette_idx]

    def _band_color(self, band_idx: int, seed: int) -> Color:
        base = self._pal()["bands"][band_idx]
        j    = ((seed & 0xFF) / 255.0 - 0.5) * 0.24
        return Color(
            max(0, min(255, int(base.r * (1.0 + j)))),
            max(0, min(255, int(base.g * (1.0 + j)))),
            max(0, min(255, int(base.b * (1.0 + j)))),
        )

    # ── Background (persistent) ───────────────────────────────────────────────

    def _draw_bg_row(self, row: int, band_idx: int,
                     c_start: int, c_end: int) -> None:
        band  = _BANDS[band_idx]
        chars = band["chars"]
        den   = band["density"]
        bp    = int(band["bold_p"] * 255)
        dp    = int(band["dim_p"]  * 255)

        for col in range(c_start, c_end):
            h = _dhash(row, col, band_idx)
            if (h & 0xFFFF) / 65535.0 > den:
                self._bg_plane._cells.pop((row, col), None)
                continue
            char = chars[h % len(chars)]
            fg   = self._band_color(band_idx, h >> 8)
            bold = ((h >> 16) & 0xFF) < bp
            dim  = ((h >> 24) & 0xFF) < dp
            self._bg_plane.put_char(row, col, char, fg=fg, bg=BLACK,
                                    bold=bold, dim=dim)

    def _anim_bg_row(self, row: int, band_idx: int,
                     c_start: int, c_end: int) -> None:
        band  = _BANDS[band_idx]
        chars = band["chars"]
        fg    = self._pal()["bands"][band_idx]
        n     = max(1, (c_end - c_start) // 8)
        for _ in range(n):
            col  = random.randint(c_start, max(c_start, c_end - 1))
            char = random.choice(chars)
            dim  = random.random() < 0.30
            self._bg_plane.put_char(row, col, char, fg=fg, bg=BLACK, dim=dim)

    def _update_bg(self, h: int, c_start: int, c_end: int) -> None:
        for row in range(h - 1):
            band_idx = _get_band(self._depth + row * self._zoom)
            prev     = self._row_band.get(row, -1)
            if band_idx != prev:
                self._row_band[row] = band_idx
                self._draw_bg_row(row, band_idx, c_start, c_end)
            elif band_idx in _ANIM_BANDS:
                self._anim_bg_row(row, band_idx, c_start, c_end)

    # ── Wireframe grid ────────────────────────────────────────────────────────

    def _draw_grid(self, h: int, w: int,
                   grid_l: int, c_start: int, c_end: int, grid_r: int) -> None:
        pal    = self._pal()
        gc     = pal["grid"]
        lc     = pal["label"]
        cont_w = c_end - c_start

        for row in range(h - 1):
            if 0 <= grid_l < w:
                self._grid_plane.put_char(row, grid_l, "║", fg=gc, bg=BLACK)
            if 0 <= grid_r < w and grid_r != grid_l:
                self._grid_plane.put_char(row, grid_r, "║", fg=gc, bg=BLACK)

        for i in range(1, _N_BANDS):
            boundary_d = _BANDS[i - 1]["end"]
            row_f      = (boundary_d - self._depth) / max(0.001, self._zoom)
            row        = int(row_f)
            if not (0 <= row < h - 1):
                continue

            label = _BANDS[i]["name"]
            if len(label) + 6 <= cont_w:
                side = (cont_w - len(label) - 4) // 2
                line = ("─" * side
                        + "╢ " + label + " ╟"
                        + "─" * (cont_w - side - len(label) - 4))
            else:
                line = "─" * cont_w

            for ci, ch in enumerate(line[:cont_w]):
                self._grid_plane.put_char(row, c_start + ci, ch, fg=lc, bg=BLACK)
            if 0 <= grid_l < w:
                self._grid_plane.put_char(row, grid_l, "╠", fg=lc, bg=BLACK)
            if 0 <= grid_r < w and grid_r != grid_l:
                self._grid_plane.put_char(row, grid_r, "╣", fg=lc, bg=BLACK)

    # ── HUD panels ───────────────────────────────────────────────────────────

    def _draw_hud(self, h: int, w: int,
                  grid_l: int, c_start: int, c_end: int, grid_r: int) -> None:
        pal      = self._pal()
        lc       = pal["hud_l"]
        rc       = pal["hud_r"]
        sc       = pal["scan"]
        t        = self._t
        depth    = self._depth % _TOTAL_DEPTH
        band_idx = _get_band(self._depth)
        bname    = _BANDS[band_idx]["name"]

        if grid_l > 1:
            col_w = grid_l
            sig   = int(50 + 40 * math.sin(t * 0.04))
            bars  = "█" * (sig // 10) + "░" * (10 - sig // 10)
            lines = [
                "BIOSCAN v2.1",
                "────────────",
                f"DEP {depth:6.1f}m",
                f"LYR {bname[:8]}",
                f"TMP {_BAND_TEMPS[band_idx]}",
                f"PRS {_BAND_PRESS[band_idx]}atm",
                "────────────",
                f"O2  {_BAND_O2[band_idx]:.1f}%",
                f"H2O {_BAND_HUMID[band_idx]}%",
                f"CO2 {_BAND_CO2[band_idx]}ppm",
                "────────────",
                f"BIO {_BIOTA_OPTS[band_idx % len(_BIOTA_OPTS)]}",
                f"SIG {bars[:max(1, col_w - 4)]}",
                "────────────",
            ]
            for ri, line in enumerate(lines):
                if ri >= h - 1:
                    break
                for ci, ch in enumerate(line[:col_w]):
                    self._hud_plane.put_char(
                        ri, ci, ch, fg=lc, bg=BLACK,
                        bold=(ri == 0), dim=(ch == "─"))

        r_start = grid_r + 1
        if r_start < w:
            col_w = w - r_start
            hz    = 2400 + (t % 200)
            lat   = 3.2  + math.sin(t * 0.012) * 0.5
            lon   = 122.4 + math.cos(t * 0.009) * 0.3
            err   = 0.001 + (t % 31) * 0.0001
            up_h  = t // 1800
            up_m  = (t // 30) % 60
            sats  = 12 + (t // 240) % 5
            lines = [
                "SCAN:ACTIVE",
                "────────────",
                "MODE PASSIVE",
                f"FRQ {hz}MHz",
                "────────────",
                f"LAT {lat:+.2f}N",
                f"LON {lon:.2f}E",
                "────────────",
                f"SAT {sats}/16",
                f"ERR {err:.4f}%",
                "────────────",
                f"SPD {self._speed:.2f}",
                f"UP  {up_h}h{up_m:02d}m",
                "────────────",
            ]
            for ri, line in enumerate(lines):
                if ri >= h - 1:
                    break
                for ci, ch in enumerate(line[:col_w]):
                    self._hud_plane.put_char(
                        ri, r_start + ci, ch, fg=rc, bg=BLACK,
                        bold=(ri == 0), dim=(ch == "─"))

        # Scan beam (always drawn, even in HUD-off path via update())
        scan_row = int(self._scan_y) % max(1, h - 1)
        for col in range(c_start, c_end):
            self._hud_plane.put_char(scan_row, col, "░", fg=sc, bg=BLACK, bold=True)

    # ── Fossil window management ──────────────────────────────────────────────

    def _spawn_fossil(self, h: int, c_start: int, c_end: int) -> None:
        if not self._fossil_queue:
            self._fossil_queue = list(range(len(_FOSSILS)))
            random.shuffle(self._fossil_queue)

        fossil = _FOSSILS[self._fossil_queue.pop()]
        pal    = self._pal()
        win_w  = max(len(fossil["art"][0]) + 4 if fossil["art"] else 20,
                     len(f"[ FOSSIL SCAN: {fossil['name']} ]") + 2)
        win_h  = len(fossil["art"]) + 4

        # Center horizontally in content area; random vertical placement
        cx = (c_start + c_end - win_w) // 2
        cx = max(c_start, min(cx, c_end - win_w))
        cy = random.randint(1, max(1, h - win_h - 3))

        self._fossils.append(
            _FossilWindow(fossil, cy, cx,
                          border_color=pal["scan"],
                          art_color=pal["label"])
        )

    # ── Controls ──────────────────────────────────────────────────────────────

    def on_key(self, key: int) -> bool:
        if key == ord('p'):
            self._palette_idx = (self._palette_idx + 1) % len(_PALETTES)
            self._row_band.clear()
            return True
        if key == ord('o'):
            self._palette_idx = (self._palette_idx - 1) % len(_PALETTES)
            self._row_band.clear()
            return True
        if key == ord('['):
            self._speed = max(_SPD_MIN, round(self._speed - _SPD_STEP, 3))
            return True
        if key == ord(']'):
            self._speed = min(_SPD_MAX, round(self._speed + _SPD_STEP, 3))
            return True
        if key == ord('-'):
            self._zoom = max(_ZOOM_MIN, round(self._zoom - _ZOOM_STEP, 2))
            self._row_band.clear()
            return True
        if key == ord('='):
            self._zoom = min(_ZOOM_MAX, round(self._zoom + _ZOOM_STEP, 2))
            self._row_band.clear()
            return True
        if key == ord('g'):
            self._hud_on = not self._hud_on
            # Layout change — force full background redraw at new content width
            self._row_band.clear()
            if self._bg_plane:
                self._bg_plane.clear()
            return True
        if key == ord('x'):
            self._fossil_mode = not self._fossil_mode
            if not self._fossil_mode:
                self._fossils.clear()
                if self._fossil_plane:
                    self._fossil_plane.clear()
            return True
        return False

    @property
    def status_extras(self) -> str:
        pal    = _PAL_NAMES[self._palette_idx]
        spd    = f"{self._speed:.2f}"
        zm     = f"{self._zoom:.1f}"
        hud    = "ON" if self._hud_on else "OFF"
        fossil = "  x FOSSIL:ON" if self._fossil_mode else "  x FOSSIL"
        return (f"  o/p {pal}  [/] SPD×{spd}"
                f"  -/= ZOOM×{zm}  g HUD:{hud}{fossil}")

    @property
    def status_color(self) -> Color:
        return _PALETTES[self._palette_idx]["hud_l"]

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def init(self, renderer, h: int, w: int) -> None:
        self._h, self._w = h, w
        self._t = self._fossil_t = 0
        self._depth  = 0.0
        self._scan_y = 0.0
        self._row_band.clear()
        self._fossils.clear()
        self._fossil_queue = list(range(len(_FOSSILS)))
        random.shuffle(self._fossil_queue)
        self._bg_plane     = Plane(h, w, z=0)
        self._grid_plane   = Plane(h, w, z=1)
        self._hud_plane    = Plane(h, w, z=2)
        self._fossil_plane = Plane(h, w, z=3)

    def on_resize(self, h: int, w: int) -> None:
        self._h, self._w = h, w
        self._row_band.clear()
        self._fossils.clear()
        self._bg_plane     = Plane(h, w, z=0)
        self._grid_plane   = Plane(h, w, z=1)
        self._hud_plane    = Plane(h, w, z=2)
        self._fossil_plane = Plane(h, w, z=3)

    def cleanup(self) -> None:
        self._fossils.clear()

    # ── Frame update ──────────────────────────────────────────────────────────

    def update(self, h: int, w: int) -> None:
        self._h, self._w = h, w
        self._t += 1

        grid_l, c_start, c_end, grid_r = self._layout(w)

        self._depth  = (self._depth + self._speed) % _TOTAL_DEPTH
        scan_spd     = max(0.5, self._speed * 2.5)
        self._scan_y = (self._scan_y + scan_spd) % max(1, h - 1)

        # 1. Persistent background
        self._update_bg(h, c_start, c_end)

        # 2. Grid
        self._grid_plane.clear()
        self._draw_grid(h, w, grid_l, c_start, c_end, grid_r)

        # 3. HUD + scan beam
        self._hud_plane.clear()
        if self._hud_on:
            self._draw_hud(h, w, grid_l, c_start, c_end, grid_r)
        else:
            scan_row = int(self._scan_y) % max(1, h - 1)
            sc = self._pal()["scan"]
            for col in range(c_start, c_end):
                self._hud_plane.put_char(scan_row, col, "░",
                                         fg=sc, bg=BLACK, bold=True)

        # 4. Fossil scan windows
        if self._fossil_mode:
            self._fossil_plane.clear()
            self._fossil_t += 1
            # Spawn interval: ~5 s at 30 fps = 150 frames; shorter at high intensity
            interval = max(60, int(self.imap(180, 60)))
            if self._fossil_t >= interval and len(self._fossils) < 2:
                self._fossil_t = 0
                self._spawn_fossil(h, c_start, c_end)

            alive = []
            for fw in self._fossils:
                fw.update()
                if not fw.is_done():
                    fw.render(self._fossil_plane)
                    alive.append(fw)
            self._fossils = alive

    def planes(self) -> list[Plane]:
        ps = [self._bg_plane, self._grid_plane, self._hud_plane]
        if self._fossil_mode:
            ps.append(self._fossil_plane)
        return ps
