"""
effects.py — Shared colour themes and visual effects for ghosts2 scenes.

Exports
───────
  _hsv(h, s, v) → Color
  _build_gradient(theme_dict) → list[Color]
  _hue_gradient(hue) → list[Color]
  _THEMES           — list of theme dicts (GREEN … WHITE)
  _RAINBOW_IDX      — sentinel index for the animated rainbow theme
  _RAINBOW_SPEED    — hue advance per frame
  _BURST_DIRS       — 8 direction vectors (aspect-corrected)
  _BURST_SIZES      — arm-length presets
  _BURST_CENTRE     — centre-glyph candidates
  _Burst            — starburst explosion class
"""

from __future__ import annotations

import colorsys
import random
from typing import TYPE_CHECKING

from renderer import Color, Plane, BLACK, WHITE, gradient

if TYPE_CHECKING:
    pass


# ── Colour helpers ────────────────────────────────────────────────────────────

def _hsv(h: float, s: float, v: float) -> Color:
    r, g, b = colorsys.hsv_to_rgb(h % 1.0, s, v)
    return Color(int(r * 255), int(g * 255), int(b * 255))


def _build_gradient(t: dict) -> list[Color]:
    b1, b2 = t["bright"]
    m1, m2 = t["mid"]
    d1, d2 = t["dark"]
    g = ([t["head"]]
         + gradient(b1, b2, 3)
         + gradient(m1, m2, 4)
         + gradient(d1, d2, 4))
    return (g + [d2] * 12)[:12]


def _hue_gradient(hue: float) -> list[Color]:
    t = {
        "head":   Color(255, 255, 255),
        "bright": (_hsv(hue, 0.25, 1.0),  _hsv(hue, 0.75, 0.95)),
        "mid":    (_hsv(hue, 0.90, 0.70),  _hsv(hue, 1.00, 0.40)),
        "dark":   (_hsv(hue, 1.00, 0.22),  _hsv(hue, 1.00, 0.07)),
    }
    return _build_gradient(t)


# ── Colour themes ─────────────────────────────────────────────────────────────

_THEMES = [
    {
        "name":   "GREEN",
        "head":   Color(255, 255, 255),
        "bright": (Color(180, 255, 180), Color(0, 200, 0)),
        "mid":    (Color(0, 180, 0),     Color(0, 80, 0)),
        "dark":   (Color(0, 50, 0),      Color(0, 12, 0)),
        "ghost":  Color(0, 10, 0),
        "spark":  Color(220, 255, 220),
        "bg":     (Color(0, 6, 0), Color(0, 3, 0), Color(0, 5, 0), Color(0, 2, 0)),
    },
    {
        "name":   "BLUE",
        "head":   Color(255, 255, 255),
        "bright": (Color(180, 200, 255), Color(50, 120, 255)),
        "mid":    (Color(30, 80, 220),   Color(10, 30, 120)),
        "dark":   (Color(5, 15, 70),     Color(0, 5, 25)),
        "ghost":  Color(0, 0, 12),
        "spark":  Color(200, 220, 255),
        "bg":     (Color(0, 0, 6), Color(0, 0, 3), Color(0, 0, 5), Color(0, 0, 2)),
    },
    {
        "name":   "RED",
        "head":   Color(255, 255, 255),
        "bright": (Color(255, 180, 180), Color(255, 50, 50)),
        "mid":    (Color(200, 30, 30),   Color(100, 10, 10)),
        "dark":   (Color(60, 5, 5),      Color(20, 0, 0)),
        "ghost":  Color(12, 0, 0),
        "spark":  Color(255, 220, 220),
        "bg":     (Color(6, 0, 0), Color(3, 0, 0), Color(5, 0, 0), Color(2, 0, 0)),
    },
    {
        "name":   "AMBER",
        "head":   Color(255, 255, 255),
        "bright": (Color(255, 240, 150), Color(255, 180, 0)),
        "mid":    (Color(200, 130, 0),   Color(120, 70, 0)),
        "dark":   (Color(70, 35, 0),     Color(25, 10, 0)),
        "ghost":  Color(12, 6, 0),
        "spark":  Color(255, 250, 200),
        "bg":     (Color(6, 3, 0), Color(3, 1, 0), Color(5, 2, 0), Color(2, 1, 0)),
    },
    {
        "name":   "PURPLE",
        "head":   Color(255, 255, 255),
        "bright": (Color(230, 180, 255), Color(170, 50, 255)),
        "mid":    (Color(130, 30, 200),  Color(70, 10, 130)),
        "dark":   (Color(40, 5, 80),     Color(15, 0, 30)),
        "ghost":  Color(8, 0, 15),
        "spark":  Color(240, 210, 255),
        "bg":     (Color(4, 0, 8), Color(2, 0, 4), Color(3, 0, 6), Color(1, 0, 3)),
    },
    {
        "name":   "CYAN",
        "head":   Color(255, 255, 255),
        "bright": (Color(180, 255, 255), Color(0, 220, 220)),
        "mid":    (Color(0, 170, 170),   Color(0, 80, 80)),
        "dark":   (Color(0, 45, 45),     Color(0, 12, 12)),
        "ghost":  Color(0, 8, 8),
        "spark":  Color(210, 255, 255),
        "bg":     (Color(0, 5, 5), Color(0, 2, 2), Color(0, 4, 4), Color(0, 1, 1)),
    },
    {
        "name":   "WHITE",
        "head":   Color(255, 255, 255),
        "bright": (Color(240, 240, 240), Color(180, 180, 180)),
        "mid":    (Color(140, 140, 140), Color(80, 80, 80)),
        "dark":   (Color(50, 50, 50),    Color(15, 15, 15)),
        "ghost":  Color(10, 10, 10),
        "spark":  Color(255, 255, 255),
        "bg":     (Color(5, 5, 5), Color(3, 3, 3), Color(4, 4, 4), Color(2, 2, 2)),
    },
]

_RAINBOW_IDX   = len(_THEMES)    # sentinel; not in _THEMES list
_RAINBOW_SPEED = 0.0025


# ── Starburst explosion ───────────────────────────────────────────────────────
#
# 8 directions: x is doubled to compensate for ~2:1 terminal cell aspect ratio.

_BURST_DIRS = [
    (-1,  0),   # N
    (-1,  1),   # NE
    ( 0,  2),   # E
    ( 1,  1),   # SE
    ( 1,  0),   # S
    ( 1, -1),   # SW
    ( 0, -2),   # W
    (-1, -1),   # NW
]

_BURST_SIZES  = [3, 5, 7, 10, 14, 20]
_BURST_CENTRE = list("✦✧✺✹✸★◉⊕⊗")


class _Burst:
    """Starburst explosion — characters radiate in 8 arms from a centre point.

    Lifecycle (frames):
      grow   0 … arm_len      one new step per frame
      hold   arm_len … +hold  full burst visible
      shrink … total          outer steps vanish first; centre glyph fades last
    """

    def __init__(self, cy: int, cx: int, arm_len: int, pool: list[str]):
        self.cy      = cy
        self.cx      = cx
        self.arm_len = arm_len
        self.pool    = pool
        self.age     = 0
        self.hold    = 4
        self.total   = arm_len + self.hold + arm_len
        self._centre = random.choice(_BURST_CENTRE)
        self._chars  = [
            [random.choice(pool) for _ in range(arm_len)]
            for _ in _BURST_DIRS
        ]

    def update(self) -> None:
        self.age += 1
        for arm in self._chars:
            for i in range(len(arm)):
                if random.random() < 0.07:
                    arm[i] = random.choice(self.pool)

    def is_done(self) -> bool:
        return self.age >= self.total

    def render(self, plane: Plane, grad: list[Color]) -> None:
        n          = len(grad)
        peak       = self.arm_len + self.hold
        shrink_age = max(0, self.age - peak)

        for arm_i, (dy, dx) in enumerate(_BURST_DIRS):
            for step in range(self.arm_len):
                if step >= self.age:
                    break
                visible_len = self.arm_len - shrink_age
                if step >= visible_len:
                    continue
                y = self.cy + dy * (step + 1)
                x = self.cx + dx * (step + 1)
                if y < 0 or y >= plane.h - 1 or x < 0 or x >= plane.w:
                    continue
                spatial  = step / max(1, self.arm_len - 1)
                temporal = shrink_age / max(1, self.arm_len)
                fade     = min(1.0, spatial * 0.65 + temporal * 0.55)
                grad_i   = min(n - 1, int(fade * (n - 1)))
                plane.put_char(
                    y, x, self._chars[arm_i][step],
                    fg=grad[grad_i], bg=BLACK,
                    bold=(step == 0),
                )

        if shrink_age < self.hold \
                and 0 <= self.cy < plane.h - 1 \
                and 0 <= self.cx < plane.w:
            plane.put_char(self.cy, self.cx, self._centre,
                           fg=grad[min(n - 1, shrink_age)],
                           bg=BLACK, bold=True)
