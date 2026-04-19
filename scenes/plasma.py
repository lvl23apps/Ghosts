"""Plasma — smooth flowing plasma field built from layered sine waves.

Scene-specific controls:
  o / p        cycle colour theme  (GREEN BLUE RED AMBER PURPLE CYAN WHITE RAINBOW)
  l            toggle λ mode — uses lambda-calculus characters
  0-5          character pool  (0=random 1=blocks 2=waves 3=dots 4=symbols 5=mixed)
  [ / ]        flow complexity  (SMOOTH → RIPPLE → VORTEX → RADIAL → WARP → CHAOS)
  - / =        animation speed  (×0.25 – ×4.0)
  g            toggle sparkle — bright flashes at plasma peaks
  x            toggle burst mode — ASCII starburst explosions
  { / }        burst size — arm length 3 → 5 → 7 → 10 → 14 → 20
"""

from __future__ import annotations

import math
import random
from typing import Optional

from renderer import Plane, Color, CursesRenderer, ALPHA_OPAQUE, BLACK, WHITE
from scene_base import Scene
from effects import (
    _hsv, _build_gradient, _hue_gradient,
    _THEMES, _RAINBOW_IDX, _RAINBOW_SPEED,
    _BURST_SIZES, _Burst,
)

# ── Character pools ───────────────────────────────────────────────────────────

_BLOCKS  = list("░▒▓▓▒░█▉▊▋▌▍")
_WAVES   = list("~≈∿〜∼∽⌁⋯∾")
_DOTS    = list("·•●○◦⊙◎∘⋅˙")
_SYMBOLS = list("★✦✧✺✹✸◉⊕⊗✼")
_MIXED   = _BLOCKS[:4] + _WAVES[:3] + _DOTS[:3]
_LAMBDA  = (
    ['λ'] * 12
    + list("Λαβγδεζηθικμνξπρστυφχψω")
    + list("ΑΒΓΔΕΖΗΘΙΚΜΝΞΠΡΣΤΥΦΧΨΩ")
    + list("∀∃∂∇∈∏∑∞∫∴∵≡≤≥⊢⊥")
)

_POOLS = {
    "blocks":  _BLOCKS,
    "waves":   _WAVES,
    "dots":    _DOTS,
    "symbols": _SYMBOLS,
    "mixed":   _MIXED,
    "lambda":  _LAMBDA,
}
_POOL_NAMES  = list(_POOLS.keys())
_POOL_LABELS = {
    None:      "RANDOM",
    "blocks":  "BLOCKS",
    "waves":   "WAVES",
    "dots":    "DOTS",
    "symbols": "SYMBOLS",
    "mixed":   "MIXED",
    "lambda":  "λ MODE",
}

# ── Complexity levels ─────────────────────────────────────────────────────────

_COMPLEXITY_MIN   = 1
_COMPLEXITY_MAX   = 6
_COMPLEXITY_NAMES = ["SMOOTH", "RIPPLE", "VORTEX", "RADIAL", "WARP", "CHAOS"]

# ── Speed ─────────────────────────────────────────────────────────────────────

_SPEED_STEP = 0.25
_SPEED_MIN  = 0.25
_SPEED_MAX  = 4.0


# ── Plasma field ──────────────────────────────────────────────────────────────

def _plasma_value(col: int, row: int, t: float, cx: float, cy: float,
                  complexity: int) -> float:
    """Return plasma field intensity in [0, 1] at character cell (col, row).

    col is halved to correct for the ~2:1 terminal cell aspect ratio so that
    radial terms appear circular rather than elliptical.
    """
    x       = col * 0.5   # aspect-correct x
    y       = float(row)
    v       = 0.0
    max_amp = 0.0

    # Level 1 — two orthogonal waves (always active)
    v       += math.sin(x * 0.30 + t)
    v       += math.sin(y * 0.45 + t * 0.75)
    max_amp += 2.0

    if complexity >= 2:          # diagonal ripple
        v       += math.sin((x + y) * 0.20 + t * 1.1)
        max_amp += 1.0

    if complexity >= 3:          # radial wave from field centre
        dx, dy  = x - cx * 0.5, y - cy
        v       += math.sin(math.sqrt(dx * dx + dy * dy + 1e-6) * 0.50 - t * 0.85)
        max_amp += 1.0

    if complexity >= 4:          # cross-amplitude modulation
        v       += math.sin(x * 0.18 + t * 0.45) * math.cos(y * 0.25 - t * 0.30)
        max_amp += 1.0

    if complexity >= 5:          # nonlinear product (warp)
        v       += math.sin(x * y * 0.012 + t * 0.60) * 0.75
        max_amp += 0.75

    if complexity >= 6:          # second radial from an offset centre (chaos)
        dx2, dy2 = x - cx * 0.25, y - cy * 1.5
        v        += math.sin(math.sqrt(dx2 * dx2 + dy2 * dy2 + 1e-6) * 0.38
                             - t * 1.20) * 0.85
        max_amp  += 0.85

    # Normalise to [0, 1]
    return max(0.0, min(1.0, v / (2.0 * max_amp) + 0.5))


# ── Scene ─────────────────────────────────────────────────────────────────────

class Plasma(Scene):
    name = "Plasma"

    _DEFAULT_THEME = 4    # PURPLE

    def __init__(self):
        self._plasma_plane: Optional[Plane] = None
        self._burst_plane:  Optional[Plane] = None
        self._bursts: list[_Burst] = []
        self._h = self._w = 0
        self._t = 0.0
        self._burst_t = 0

        # Per-cell character & mutation timers  {(row,col): [char, ticks_left]}
        self._cell_chars: dict[tuple[int,int], list] = {}

        # Controls
        self._theme_idx   = self._DEFAULT_THEME
        self._pool_key: Optional[str] = None
        self._complexity  = 3           # default: VORTEX
        self._speed       = 1.0
        self._sparkle     = False
        self._burst_mode  = False
        self._burst_size_i = 2          # default arm=7
        self._rainbow_hue = 0.0

        # Derived colour state
        self._trail_gradient: list[Color] = []
        self._apply_theme_values()

    # ── Theme ─────────────────────────────────────────────────────────────────

    def _apply_theme_values(self) -> None:
        if self._theme_idx == _RAINBOW_IDX:
            self._trail_gradient = _hue_gradient(self._rainbow_hue)
        else:
            self._trail_gradient = _build_gradient(_THEMES[self._theme_idx])

    def _apply_theme(self) -> None:
        self._apply_theme_values()
        # Force full redraw of cell chars on next frame
        self._cell_chars.clear()

    # ── Controls ──────────────────────────────────────────────────────────────

    def on_key(self, key: int) -> bool:
        if key == ord('p'):
            self._theme_idx = (self._theme_idx + 1) % (_RAINBOW_IDX + 1)
            self._apply_theme()
            return True
        if key == ord('o'):
            self._theme_idx = (self._theme_idx - 1) % (_RAINBOW_IDX + 1)
            self._apply_theme()
            return True
        if key == ord('l'):
            self._pool_key = None if self._pool_key == "lambda" else "lambda"
            self._cell_chars.clear()
            return True
        if key == ord('['):
            self._complexity = max(_COMPLEXITY_MIN, self._complexity - 1)
            return True
        if key == ord(']'):
            self._complexity = min(_COMPLEXITY_MAX, self._complexity + 1)
            return True
        if key == ord('-'):
            self._speed = max(_SPEED_MIN, round(self._speed - _SPEED_STEP, 2))
            return True
        if key == ord('='):
            self._speed = min(_SPEED_MAX, round(self._speed + _SPEED_STEP, 2))
            return True
        if key == ord('g'):
            self._sparkle = not self._sparkle
            return True
        if key == ord('x'):
            self._burst_mode = not self._burst_mode
            if not self._burst_mode:
                self._bursts.clear()
                if self._burst_plane:
                    self._burst_plane.clear()
            return True
        if key == ord('{'):
            self._burst_size_i = max(0, self._burst_size_i - 1)
            return True
        if key == ord('}'):
            self._burst_size_i = min(len(_BURST_SIZES) - 1,
                                     self._burst_size_i + 1)
            return True
        pool_map = {
            ord('0'): None,      ord('1'): 'blocks',
            ord('2'): 'waves',   ord('3'): 'dots',
            ord('4'): 'symbols', ord('5'): 'mixed',
        }
        if key in pool_map:
            self._pool_key = pool_map[key]
            self._cell_chars.clear()
            return True
        return False

    @property
    def status_extras(self) -> str:
        theme    = ("RAINBOW" if self._theme_idx == _RAINBOW_IDX
                    else _THEMES[self._theme_idx]["name"])
        pool     = _POOL_LABELS[self._pool_key]
        cname    = _COMPLEXITY_NAMES[self._complexity - 1]
        speed    = f"{self._speed:.2g}"
        sparkle  = "  g SPARKLE:ON" if self._sparkle else "  g SPARKLE"
        arm      = _BURST_SIZES[self._burst_size_i]
        burst    = f"  x BURST:ON({arm})" if self._burst_mode else "  x BURST"
        return (f"  o/p {theme}  l/0-5 {pool}"
                f"  [/] {cname}  -/= ×{speed}{sparkle}{burst}")

    @property
    def status_color(self) -> Color:
        if self._theme_idx == _RAINBOW_IDX:
            return _hsv(self._rainbow_hue, 0.7, 0.65)
        c = _THEMES[self._theme_idx]["bright"][0]
        return Color(max(0, c.r // 2), max(0, c.g // 2), max(0, c.b // 2))

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def init(self, renderer: CursesRenderer, h: int, w: int) -> None:
        self._h, self._w = h, w
        self._t = 0.0
        self._burst_t = 0
        self._bursts.clear()
        self._cell_chars.clear()
        self._plasma_plane = Plane(h, w, z=0)
        self._burst_plane  = Plane(h, w, z=1)

    def on_resize(self, h: int, w: int) -> None:
        self._h, self._w = h, w
        self._cell_chars.clear()
        self._plasma_plane = Plane(h, w, z=0)
        self._burst_plane  = Plane(h, w, z=1)

    def cleanup(self) -> None:
        self._bursts.clear()
        self._cell_chars.clear()

    # ── Frame update ──────────────────────────────────────────────────────────

    def update(self, h: int, w: int) -> None:
        self._h, self._w = h, w
        base_speed = self.imap(0.008, 0.040)
        self._t   += base_speed * self._speed

        if self._theme_idx == _RAINBOW_IDX:
            self._rainbow_hue = (self._rainbow_hue + _RAINBOW_SPEED) % 1.0
            self._apply_theme_values()

        grad = self._trail_gradient
        n    = len(grad)
        pool = _POOLS.get(self._pool_key or "", None)

        cx   = (w - 1) * 0.5   # field centre (col)
        cy   = (h - 2) * 0.5   # field centre (row), exclude status bar row

        self._plasma_plane.clear()

        for row in range(h - 1):           # leave last row for status bar
            for col in range(w):
                pv = _plasma_value(col, row, self._t, cx, cy, self._complexity)

                # Character selection with lazy per-cell mutation
                key = (row, col)
                entry = self._cell_chars.get(key)
                if entry is None:
                    p = pool if pool is not None else _POOLS[random.choice(_POOL_NAMES)]
                    char  = random.choice(p)
                    timer = random.randint(3, 18)
                    self._cell_chars[key] = [char, timer, p]
                    entry = self._cell_chars[key]

                entry[1] -= 1
                if entry[1] <= 0:
                    # Mutation rate: faster at high plasma values
                    entry[0]  = random.choice(entry[2])
                    entry[1]  = max(2, int((1.0 - pv) * 20) + random.randint(1, 6))

                # If pool changed globally, refresh pool reference
                if pool is not None and entry[2] is not pool:
                    entry[2] = pool
                    entry[0] = random.choice(pool)

                char = entry[0]

                # Sparkle: rare bright flash at plasma peaks
                if self._sparkle and pv > 0.88 and random.random() < 0.08:
                    self._plasma_plane.put_char(
                        row, col, char, fg=WHITE, bg=BLACK, bold=True)
                    continue

                # Map plasma value to gradient
                # Use a sine-smoothed mapping so mid-values get more range
                grad_t = (math.sin(pv * math.pi - math.pi * 0.5) + 1.0) * 0.5
                grad_i = min(n - 1, int(grad_t * (n - 1)))

                bold = pv > 0.78
                dim  = pv < 0.22

                self._plasma_plane.put_char(
                    row, col, char, fg=grad[grad_i], bg=BLACK,
                    bold=bold, dim=dim,
                )

        # Bursts
        if self._burst_mode:
            self._burst_plane.clear()
            self._burst_t += 1
            interval = max(8, int(self.imap(90, 10)))
            max_live = max(2, int(self.imap(2, 10)))
            if self._burst_t >= interval and len(self._bursts) < max_live:
                self._burst_t = 0
                arm    = _BURST_SIZES[self._burst_size_i]
                margin = arm * 2 + 2
                cy_b   = random.randint(1, max(1, h - 3))
                cx_b   = random.randint(margin, max(margin, w - margin - 1))
                bpool  = _POOLS.get(self._pool_key or "mixed", _POOLS["mixed"])
                self._bursts.append(_Burst(cy_b, cx_b, arm, bpool))
            alive = []
            for burst in self._bursts:
                burst.update()
                if not burst.is_done():
                    burst.render(self._burst_plane, grad)
                    alive.append(burst)
            self._bursts = alive

    def planes(self) -> list[Plane]:
        ps = [self._plasma_plane]
        if self._burst_mode:
            ps.append(self._burst_plane)
        return ps
