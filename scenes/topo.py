"""Topo Flyover — procedural topographic map flyover.

Terrain is synthesised from layered sine-wave octaves.  The viewport scrolls
forward through the landscape, with new terrain entering at the top of the
screen and passing beneath you.

Scene-specific controls:
  o / p        cycle terrain palette  (NATURAL THERMAL NIGHT AMBER MONO)
  0-5          terrain preset  (ALPINE COASTAL PLAINS CANYON VOLCANIC MIXED)
  [ / ]        flyover speed  (slow → fast)
  - / =        altitude / zoom  (low=close detail, high=aerial overview)
  g            toggle contour-line mode
  x            toggle burst mode — ASCII starburst explosions
  { / }        burst size
"""

from __future__ import annotations

import math
import random
from typing import Optional

from renderer import Plane, Color, BLACK
from scene_base import Scene
from effects import _BURST_SIZES, _Burst


# ── Elevation character bands ─────────────────────────────────────────────────
# (upper_threshold, chars, animates)
# Water bands animate per-frame; land bands use a positional hash (stable).

_CHAR_BANDS = [
    (0.22, list("≋≋≈≈~~∼"),  True),   # deep ocean
    (0.33, list("≈≈~∼〜∽∼"),  True),   # ocean
    (0.40, list("·_.,`'"),    False),  # shore / beach
    (0.55, list("░·,∙∘·"),   False),  # lowland / grassland
    (0.68, list("▒░♦∆·,"),   False),  # hills / forest
    (0.82, list("▓▒▲△∧"),    False),  # mountain
    (0.92, list("█▓▲◆✦"),    False),  # high peak
    (1.01, list("✦*◈·◆"),    False),  # snow cap
]

_CONTOUR_CHARS = list("∘·○—~")


# ── Terrain colour palettes ───────────────────────────────────────────────────
# Each palette: list of (elevation_stop, Color) — linearly interpolated.

_TERRAIN_PALETTES = [
    # NATURAL — earth colours
    [
        (0.00, Color(  0,   8,  50)),
        (0.22, Color(  5,  50, 180)),
        (0.33, Color( 15, 100, 210)),
        (0.40, Color(195, 175, 105)),
        (0.55, Color( 70, 140,  50)),
        (0.68, Color( 90,  75,  50)),
        (0.82, Color(150, 130, 115)),
        (0.92, Color(210, 225, 235)),
        (1.00, Color(250, 255, 255)),
    ],
    # THERMAL — cold-deep to hot-peak
    [
        (0.00, Color(  0,   0,  80)),
        (0.22, Color(  0,  20, 200)),
        (0.35, Color(  0, 150, 200)),
        (0.50, Color(  0, 200, 100)),
        (0.65, Color(200, 200,   0)),
        (0.80, Color(255, 120,   0)),
        (0.92, Color(255,  40,   0)),
        (1.00, Color(255, 255, 200)),
    ],
    # NIGHT — dark atmospheric
    [
        (0.00, Color(  0,   2,  20)),
        (0.25, Color(  5,  20,  70)),
        (0.40, Color( 30,  25,  15)),
        (0.55, Color( 20,  50,  15)),
        (0.68, Color( 15,  40,  10)),
        (0.82, Color( 45,  40,  30)),
        (0.92, Color( 70,  65,  60)),
        (1.00, Color(130, 135, 140)),
    ],
    # AMBER — warm sepia tones
    [
        (0.00, Color( 10,   5,   0)),
        (0.25, Color( 50,  30,   5)),
        (0.40, Color(120,  80,  20)),
        (0.55, Color(180, 130,  40)),
        (0.68, Color(200, 160,  60)),
        (0.82, Color(220, 190, 100)),
        (0.92, Color(240, 220, 150)),
        (1.00, Color(255, 245, 200)),
    ],
    # MONO — greyscale
    [
        (0.00, Color(  0,   0,   0)),
        (0.25, Color( 15,  15,  15)),
        (0.40, Color( 35,  35,  35)),
        (0.55, Color( 65,  65,  65)),
        (0.68, Color(100, 100, 100)),
        (0.82, Color(150, 150, 150)),
        (0.92, Color(200, 200, 200)),
        (1.00, Color(255, 255, 255)),
    ],
]

_PALETTE_NAMES = ["NATURAL", "THERMAL", "NIGHT", "AMBER", "MONO"]


# ── Terrain presets ───────────────────────────────────────────────────────────
# waves: list of (wx_freq, wy_freq, phase, amplitude)
# bias:  elevation centre shift — positive → more land, negative → more ocean

_PI = math.pi

# ── Terrain presets ───────────────────────────────────────────────────────────
#
# Each wave is a DIRECTIONAL plane wave: (angle_rad, freq, phase, amp)
#   contribution = amp * sin(dot(direction, (wx,wy)) * freq + phase)
#   direction    = (cos(angle), sin(angle))
#
# angle near π/2 (90°) → ridges run left-right (fly head-on into them).
# angle near 0 or π    → ridges run top-to-bottom (fly along them).
#
# warp:     (amplitude, frequency) — bends coords before wave eval.
#           Breaks straight-line regularity into organic curves.
# sharpen:  tanh steepness (1.0 = natural, >2 = cliff-like mesa/canyon).
# bias:     shifts the normalised elevation centre (+= more land, -= more ocean).
# contrast: multiplier on the normalised deviation before bias is applied.
#           < 1.0 compresses terrain into a narrow elevation band (plains effect).

_PRESETS = {
    # Long parallel ridges running left-right; warp curves them.
    # High bias + moderate contrast → mostly highlands, no ocean.
    "ALPINE": {
        "waves": [
            (_PI * 0.50, 0.20, 0.00, 1.00),   # primary E-W ridge
            (_PI * 0.47, 0.20, _PI,  0.80),   # offset phase → twin-peak profile
            (_PI * 0.54, 0.42, 1.10, 0.45),   # diagonal secondary
            (_PI * 0.28, 0.85, 2.50, 0.18),   # NE texture
            (_PI * 0.72, 1.70, 0.60, 0.09),   # SW fine detail
        ],
        "warp":     (2.2, 0.13),
        "sharpen":  1.0,
        "bias":    +0.13,
        "contrast": 0.92,
    },
    # Mostly deep ocean (very low contrast + strong negative bias).
    # Two wave axes at 60° and 120° create a triangular interference lattice —
    # islands only appear at the handful of constructive-peak nodes.
    "COASTAL": {
        "waves": [
            (_PI * 0.50, 0.04, 0.00, 0.40),   # vast continental shelf swell
            (_PI * 0.33, 0.40, 0.00, 1.00),   # island axis A (60°)
            (_PI * 0.67, 0.40, _PI,  0.95),   # island axis B (120°, anti-phase)
            (_PI * 0.50, 1.10, 1.80, 0.22),   # breaking-wave texture
        ],
        "warp":     (0.5, 0.25),
        "sharpen":  1.3,
        "bias":    -0.22,
        "contrast": 1.00,
    },
    # Low contrast compresses everything into the 0.42–0.64 grassland band.
    # Very low-freq primary wave creates broad continental undulation.
    "PLAINS": {
        "waves": [
            (_PI * 0.50, 0.05, 0.00, 1.00),   # continental swell (long wavelength)
            (_PI * 0.49, 0.11, 1.80, 0.35),   # gentle secondary roll
            (_PI * 0.51, 0.22, 0.90, 0.10),   # slight ripple
            (_PI * 0.42, 0.44, 2.80, 0.04),   # barely-there texture
        ],
        "warp":     (0.2, 0.06),
        "sharpen":  1.0,
        "bias":    +0.05,
        "contrast": 0.28,              # squashes range to ~±0.14 around bias centre
    },
    # High-amplitude waves at very different angles cut across each other.
    # Strong tanh sharpening → flat-topped mesas + sudden narrow canyon slots.
    "CANYON": {
        "waves": [
            (_PI * 0.50, 0.26, 0.00, 1.00),   # primary E-W slots
            (_PI * 0.35, 0.34, 0.70, 0.95),   # angled secondary
            (_PI * 0.65, 0.56, 1.90, 0.75),   # opposing diagonal
            (_PI * 0.50, 1.10, 2.50, 0.28),   # fine slot detail
        ],
        "warp":     (1.0, 0.22),
        "sharpen":  2.8,
        "bias":    +0.04,
        "contrast": 1.00,
    },
    # Abyssal ocean floor.  Two high-freq wave axes at ±35° from N create an
    # interference pattern of isolated spikes — the volcanic islands.
    # Sharpening makes the peaks spike violently from a flat ocean.
    "VOLCANIC": {
        "waves": [
            (_PI * 0.50, 0.04, 0.00, 0.45),   # flat ocean floor
            (_PI * 0.40, 0.52, 0.00, 1.00),   # peak axis A
            (_PI * 0.60, 0.52, _PI * 0.6, 0.90),  # peak axis B
            (_PI * 0.50, 1.30, 1.80, 0.30),   # caldera rim
            (_PI * 0.50, 2.60, 0.50, 0.12),   # lava roughness
        ],
        "warp":     (0.6, 0.18),
        "sharpen":  2.0,
        "bias":    -0.17,
        "contrast": 1.00,
    },
    # Four directions active (N, NE, NW, E-W) at different scales.
    # No dominant axis → rumpled, varied landscape without obvious pattern.
    "MIXED": {
        "waves": [
            (_PI * 0.50, 0.12, 0.00, 1.00),   # N primary
            (_PI * 0.25, 0.20, 1.80, 0.65),   # NE
            (_PI * 0.75, 0.24, 3.10, 0.55),   # NW
            (_PI * 0.00, 0.32, 0.90, 0.38),   # E-W
            (_PI * 0.50, 0.70, 2.20, 0.18),   # fine N texture
        ],
        "warp":     (1.3, 0.12),
        "sharpen":  1.0,
        "bias":     0.00,
        "contrast": 0.80,
    },
}

_PRESET_NAMES = ["ALPINE", "COASTAL", "PLAINS", "CANYON", "VOLCANIC", "MIXED"]

_SPEED_STEP = 0.05
_SPEED_MIN  = 0.02
_SPEED_MAX  = 1.50

_ALT_STEP   = 0.25
_ALT_MIN    = 0.25
_ALT_MAX    = 4.00

_CONTOUR_LEVELS = 8      # number of contour bands
_CONTOUR_WIDTH  = 0.14   # fraction of each band that draws as a contour line


# ── Field helpers ─────────────────────────────────────────────────────────────

def _elevation(wx: float, wy: float, preset: dict) -> float:
    """Terrain elevation at world (wx, wy) → [0, 1].

    Directional plane waves + domain warp + optional tanh sharpening +
    contrast compression.  Each preset produces a radically different
    elevation distribution.
    """
    # Domain warp — compute displacements from ORIGINAL coordinates
    warp_amp, warp_freq = preset.get("warp", (0.0, 0.0))
    if warp_amp:
        dx = warp_amp * math.sin(wy * warp_freq + 1.3)
        dy = warp_amp * math.cos(wx * warp_freq + 0.7)   # original wx
        wx += dx
        wy += dy

    v = total_amp = 0.0
    for angle, freq, phase, amp in preset["waves"]:
        proj   = wx * math.cos(angle) + wy * math.sin(angle)
        v         += amp * math.sin(proj * freq + phase)
        total_amp += amp

    # Tanh sharpening: exaggerates peaks/troughs → cliff-like transitions
    steepness = preset.get("sharpen", 1.0)
    if steepness != 1.0:
        v = math.tanh((v / total_amp) * steepness) * total_amp

    # Contrast compression then bias shift
    contrast = preset.get("contrast", 1.0)
    bias     = preset.get("bias", 0.0)
    return max(0.0, min(1.0, (v / (2.0 * total_amp)) * contrast + 0.5 + bias))


def _lerp_color(c0: Color, c1: Color, t: float) -> Color:
    return Color(
        int(c0.r + (c1.r - c0.r) * t),
        int(c0.g + (c1.g - c0.g) * t),
        int(c0.b + (c1.b - c0.b) * t),
    )


def _terrain_color(elev: float, palette_idx: int) -> Color:
    stops = _TERRAIN_PALETTES[palette_idx]
    if elev <= stops[0][0]:
        return stops[0][1]
    for i in range(len(stops) - 1):
        e0, c0 = stops[i]
        e1, c1 = stops[i + 1]
        if elev <= e1:
            t = (elev - e0) / (e1 - e0)
            return _lerp_color(c0, c1, t)
    return stops[-1][1]


def _terrain_char(elev: float, wx_i: int, wy_i: int,
                  frame: int) -> tuple[str, bool, bool]:
    """Return (char, bold, dim) for a terrain cell.

    Water bands animate using frame + position; land bands are stable via hash.
    """
    for upper, chars, animates in _CHAR_BANDS:
        if elev <= upper:
            if animates:
                idx  = (wx_i * 3 + wy_i * 5 + frame // 4) % len(chars)
                return chars[idx], False, elev < 0.12
            else:
                h    = ((wx_i * 2654435761) ^ (wy_i * 2246822519)) & 0x7FFFFFFF
                bold = elev > 0.82
                dim  = elev < 0.42
                return chars[h % len(chars)], bold, dim
    return "·", False, False


def _on_contour(elev: float) -> bool:
    frac = (elev * _CONTOUR_LEVELS) % 1.0
    return frac < _CONTOUR_WIDTH or frac > (1.0 - _CONTOUR_WIDTH)


# ── Scene ─────────────────────────────────────────────────────────────────────

class TopoFlyover(Scene):
    name = "Topo Flyover"

    def __init__(self):
        self._topo_plane:  Optional[Plane] = None
        self._burst_plane: Optional[Plane] = None
        self._bursts: list[_Burst] = []
        self._h = self._w = 0
        self._scroll  = 0.0    # world-y position of the top-of-screen
        self._frame   = 0
        self._burst_t = 0

        # Controls
        self._palette_idx  = 0           # NATURAL
        self._preset_key   = "ALPINE"
        self._speed        = 0.25        # world-y units per frame
        self._altitude     = 1.0         # world-units per screen-row
        self._contour      = False
        self._burst_mode   = False
        self._burst_size_i = 2

    # ── Controls ─────────────────────────────────────────────────────────────

    def on_key(self, key: int) -> bool:
        if key == ord('p'):
            self._palette_idx = (self._palette_idx + 1) % len(_PALETTE_NAMES)
            return True
        if key == ord('o'):
            self._palette_idx = (self._palette_idx - 1) % len(_PALETTE_NAMES)
            return True
        if key == ord('['):
            self._speed = max(_SPEED_MIN, round(self._speed - _SPEED_STEP, 3))
            return True
        if key == ord(']'):
            self._speed = min(_SPEED_MAX, round(self._speed + _SPEED_STEP, 3))
            return True
        if key == ord('-'):
            self._altitude = max(_ALT_MIN, round(self._altitude - _ALT_STEP, 2))
            return True
        if key == ord('='):
            self._altitude = min(_ALT_MAX, round(self._altitude + _ALT_STEP, 2))
            return True
        if key == ord('g'):
            self._contour = not self._contour
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
        preset_map = {
            ord('0'): "ALPINE",   ord('1'): "COASTAL",
            ord('2'): "PLAINS",   ord('3'): "CANYON",
            ord('4'): "VOLCANIC", ord('5'): "MIXED",
        }
        if key in preset_map:
            self._preset_key = preset_map[key]
            return True
        return False

    @property
    def status_extras(self) -> str:
        palette = _PALETTE_NAMES[self._palette_idx]
        preset  = self._preset_key
        spd     = f"{self._speed:.2g}"
        alt     = f"{self._altitude:.2g}"
        contour = "  g CONTOUR:ON" if self._contour else "  g CONTOUR"
        arm     = _BURST_SIZES[self._burst_size_i]
        burst   = f"  x BURST:ON({arm})" if self._burst_mode else "  x BURST"
        return (f"  o/p {palette}  0-5 {preset}"
                f"  [/] SPD×{spd}  -/= ALT×{alt}{contour}{burst}")

    @property
    def status_color(self) -> Color:
        return _terrain_color(0.58, self._palette_idx)

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def init(self, renderer, h: int, w: int) -> None:
        self._h, self._w = h, w
        self._frame = self._burst_t = 0
        self._bursts.clear()
        self._topo_plane  = Plane(h, w, z=0)
        self._burst_plane = Plane(h, w, z=1)

    def on_resize(self, h: int, w: int) -> None:
        self._h, self._w = h, w
        self._topo_plane  = Plane(h, w, z=0)
        self._burst_plane = Plane(h, w, z=1)

    def cleanup(self) -> None:
        self._bursts.clear()

    # ── Frame update ──────────────────────────────────────────────────────────

    def update(self, h: int, w: int) -> None:
        self._h, self._w = h, w
        self._frame  += 1
        self._scroll += self._speed

        preset  = _PRESETS[self._preset_key]
        alt     = self._altitude
        cx      = w * 0.5
        frame   = self._frame
        pal     = self._palette_idx

        self._topo_plane.clear()

        for row in range(h - 1):
            for col in range(w):
                # World coordinates.
                # x is aspect-corrected (×0.5) so radial features look circular.
                # y counts forward from the top; scroll advances the entire field.
                wx   = (col - cx) * alt * 0.5
                wy   = self._scroll - row * alt

                elev  = _elevation(wx, wy, preset)
                color = _terrain_color(elev, pal)

                if self._contour:
                    if _on_contour(elev):
                        wx_i = int(wx * 10) & 0xFF
                        wy_i = int(wy * 10) & 0xFF
                        ci   = ((wx_i * 17 + wy_i * 31) ^ frame) % len(_CONTOUR_CHARS)
                        self._topo_plane.put_char(
                            row, col, _CONTOUR_CHARS[ci],
                            fg=color, bg=BLACK, bold=True)
                    else:
                        # Dim terrain char between contour lines
                        dim_col = _lerp_color(color, Color(0, 0, 0), 0.72)
                        self._topo_plane.put_char(
                            row, col, "·", fg=dim_col, bg=BLACK, dim=True)
                else:
                    wx_i = int(wx * 10) & 0xFFFF
                    wy_i = int(wy * 10) & 0xFFFF
                    char, bold, dim = _terrain_char(elev, wx_i, wy_i, frame)
                    self._topo_plane.put_char(
                        row, col, char, fg=color, bg=BLACK, bold=bold, dim=dim)

        # Burst mode
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
                pool   = list("▲△▓▒░✦◆*")
                self._bursts.append(_Burst(cy_b, cx_b, arm, pool))
            # Build a gradient from the terrain palette for burst colouring
            burst_grad = [_terrain_color(i / 11.0, pal) for i in range(12)]
            alive = []
            for burst in self._bursts:
                burst.update()
                if not burst.is_done():
                    burst.render(self._burst_plane, burst_grad)
                    alive.append(burst)
            self._bursts = alive

    def planes(self) -> list[Plane]:
        ps = [self._topo_plane]
        if self._burst_mode:
            ps.append(self._burst_plane)
        return ps
