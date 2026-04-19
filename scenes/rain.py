"""Rain Drops — falling raindrops with splash animations.

Scene-specific controls:
  o / p        cycle colour theme  (BLUE GREEN RED AMBER PURPLE CYAN WHITE RAINBOW)
  l            toggle λ mode — uses lambda-calculus characters as drops
  0-5          character pool  (0=random 1=drops 2=lines 3=ascii 4=unicode 5=mixed)
  [ / ]        wind angle — shear ±45°, step ≈ 7°
  - / =        density  (×0.25 – ×4.0)
  g            toggle grid mode — every cell is a character
  x            toggle burst mode — ASCII starburst explosions
  { / }        burst size — arm length 3 → 5 → 7 → 10 → 14 → 20
"""

from __future__ import annotations

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

_DROP_HEADS = list("○◎⊙◦•·∘⋅")     # head glyph for each drop (rendered white)

_DROPS   = list("·•○◦⊙◎∘⋅∙˙")
_LINES   = list("|:‖⌇⋮∥")
_ASCII   = list(".'`,;:!")
_UNICODE = list("⌇≈∿⌁⋯∼∽〜")
_MIXED   = _DROPS + _LINES + _ASCII[:3]
_LAMBDA  = (
    ['λ'] * 12
    + list("Λαβγδεζηθικμνξπρστυφχψω")
    + list("ΑΒΓΔΕΖΗΘΙΚΜΝΞΠΡΣΤΥΦΧΨΩ")
    + list("∀∃∂∇∈∏∑∞∫∴∵≡≤≥⊢⊥")
)

_POOLS = {
    "drops":   _DROPS,
    "lines":   _LINES,
    "ascii":   _ASCII,
    "unicode": _UNICODE,
    "mixed":   _MIXED,
    "lambda":  _LAMBDA,
}
_POOL_NAMES  = list(_POOLS.keys())
_POOL_LABELS = {
    None:      "RANDOM",
    "drops":   "DROPS",
    "lines":   "LINES",
    "ascii":   "ASCII",
    "unicode": "UNICODE",
    "mixed":   "MIXED",
    "lambda":  "λ MODE",
}

# Splash spread characters by ring distance
_SPLASH_NEAR = list("○◎∘~≈")
_SPLASH_MID  = list("~≈∿—˗")
_SPLASH_FAR  = list("·˙ . ")

_SHEAR_STEP      = 0.15
_SHEAR_MIN       = -1.0
_SHEAR_MAX       =  1.0
_CHAR_SCALE_STEP = 0.25
_CHAR_SCALE_MIN  = 0.25
_CHAR_SCALE_MAX  = 4.0


# ── Splash animation ──────────────────────────────────────────────────────────

class _Splash:
    """Horizontal spread from a raindrop impact.

    Expands outward for `radius` steps then fades, outer rings vanishing first.
    x positions are doubled to compensate for terminal cell aspect ratio.
    """

    def __init__(self, y: int, x: int, radius: int):
        self.y      = y
        self.x      = x
        self.radius = radius
        self.age    = 0
        self.hold   = 3
        self.total  = radius + self.hold + radius

    def update(self) -> None:
        self.age += 1

    def is_done(self) -> bool:
        return self.age >= self.total

    def render(self, plane: Plane, grad: list[Color]) -> None:
        n          = len(grad)
        peak       = self.radius + self.hold
        shrink_age = max(0, self.age - peak)
        visible_r  = min(self.age, max(0, self.radius - shrink_age))

        for r in range(1, visible_r + 1):
            for side in (-1, 1):
                x = self.x + r * 2 * side    # doubled for aspect ratio
                y = self.y
                if y < 0 or y >= plane.h - 1 or x < 0 or x >= plane.w:
                    continue
                spatial  = r / self.radius
                temporal = shrink_age / max(1, self.radius)
                fade     = min(1.0, spatial * 0.55 + temporal * 0.65)
                grad_i   = min(n - 1, int(fade * (n - 1)))
                if r <= 2:
                    char = random.choice(_SPLASH_NEAR)
                elif r <= 4:
                    char = random.choice(_SPLASH_MID)
                else:
                    char = random.choice(_SPLASH_FAR)
                plane.put_char(y, x, char, fg=grad[grad_i], bg=BLACK)

        # Impact glyph at centre
        if shrink_age < self.hold \
                and 0 <= self.y < plane.h - 1 \
                and 0 <= self.x < plane.w:
            plane.put_char(self.y, self.x, '○',
                           fg=grad[min(n - 1, shrink_age)],
                           bg=BLACK, bold=True)


# ── Drop ─────────────────────────────────────────────────────────────────────

class _Drop:
    """One falling raindrop — short trail, distinct droplet head, splash on landing."""

    def __init__(self, x: int, h: int, intensity: float,
                 pool_key: Optional[str] = None,
                 max_len: Optional[int] = None):
        self.x          = x
        self.h          = h
        if pool_key and pool_key in _POOLS:
            self.pool   = _POOLS[pool_key]
        else:
            self.pool   = _POOLS[random.choice(_POOL_NAMES)]
        self.head_char  = random.choice(_DROP_HEADS)
        self.speed      = random.uniform(0.7, 1.4 + intensity * 0.10)
        self.head_y     = float(random.randint(-h, 0))
        self.trail_len  = (max_len if max_len is not None
                           else random.randint(1, min(6, h - 2)))
        self.trail: list[str] = []
        self.mut_t: list[int] = []
        self.ghost_captured = False
        self.splash_pos: Optional[tuple[int, int]] = None   # (y, x)

    def _rand_char(self) -> str:
        return random.choice(self.pool)

    def update(self, speed_mult: float, shear: float = 0.0) -> None:
        self.head_y += self.speed * speed_mult
        head_iy = int(self.head_y)

        # Grow trail
        while len(self.trail) < min(self.trail_len, head_iy + 1):
            self.trail.append(self._rand_char())
            self.mut_t.append(random.randint(4, 14))

        # Slow character mutation
        for i in range(len(self.trail)):
            self.mut_t[i] -= 1
            if self.mut_t[i] <= 0:
                self.trail[i] = self._rand_char()
                self.mut_t[i] = random.randint(4, 14)

        # Capture splash position once the head reaches the floor
        if not self.ghost_captured and head_iy >= self.h - 2:
            self.ghost_captured = True
            sx = self.x + int(shear * len(self.trail))
            self.splash_pos = (self.h - 2, max(0, min(self.h - 1, sx)))

    def is_done(self) -> bool:
        return self.head_y - self.trail_len > self.h

    def render(self, plane: Plane, h: int, grad: list[Color],
               shear: float) -> None:
        head_iy = int(self.head_y)
        n       = len(grad)
        w       = plane.w

        # Head character (white, bold)
        hx = self.x
        hy = head_iy
        if 0 <= hy < h - 1 and 0 <= hx < w:
            plane.put_char(hy, hx, self.head_char, fg=WHITE, bg=BLACK, bold=True)

        # Trail characters (gradient from head back)
        for i, char in enumerate(self.trail):
            y = head_iy - 1 - i
            x = self.x + int(shear * (i + 1))
            if y < 0 or y >= h - 1 or x < 0 or x >= w:
                continue
            grad_i = min(n - 1, int((i + 1) / max(1, self.trail_len) * (n - 1) * 0.8))
            plane.put_char(y, x, char,
                           fg=grad[grad_i], bg=BLACK,
                           bold=False, dim=(i >= self.trail_len - 2))


# ── Scene ─────────────────────────────────────────────────────────────────────

class RainDrops(Scene):
    name = "Rain Drops"

    # Default theme: BLUE (index 1 in shared _THEMES)
    _DEFAULT_THEME = 1

    def __init__(self):
        self._ghost_plane:  Optional[Plane] = None
        self._drop_plane:   Optional[Plane] = None
        self._splash_plane: Optional[Plane] = None
        self._burst_plane:  Optional[Plane] = None
        self._drops:   list[_Drop]   = []
        self._splashes: list[_Splash] = []
        self._bursts:  list[_Burst]  = []
        self._h = self._w = 0
        self._t = 0
        self._ghost_decay_t = 0
        # Controls
        self._theme_idx    = self._DEFAULT_THEME
        self._pool_key: Optional[str] = None
        self._shear        = 0.0
        self._char_scale   = 1.0
        self._rainbow_hue  = 0.0
        self._grid_mode    = False
        self._burst_mode   = False
        self._burst_size_i = 2       # index into _BURST_SIZES (default 7)
        self._burst_t      = 0
        # Derived
        self._trail_gradient: list[Color] = []
        self._ghost_color: Color = Color(0, 0, 12)
        self._spark_color: Color = Color(200, 220, 255)
        self._bg_colors = (Color(0, 0, 6), Color(0, 0, 3),
                           Color(0, 0, 5), Color(0, 0, 2))
        self._apply_theme_values()

    # ── Theme ─────────────────────────────────────────────────────────────────

    def _apply_theme_values(self) -> None:
        if self._theme_idx == _RAINBOW_IDX:
            self._trail_gradient = _hue_gradient(self._rainbow_hue)
            self._ghost_color    = _hsv(self._rainbow_hue, 0.8, 0.08)
            self._spark_color    = _hsv(self._rainbow_hue, 0.15, 1.0)
            return
        t = _THEMES[self._theme_idx]
        self._trail_gradient = _build_gradient(t)
        self._ghost_color    = t["ghost"]
        self._spark_color    = t["spark"]
        self._bg_colors      = t["bg"]

    def _grid_char_color(self) -> Color:
        if self._theme_idx == _RAINBOW_IDX:
            return _hsv(self._rainbow_hue, 0.9, 0.18)
        b = _THEMES[self._theme_idx]["bright"][1]
        return Color(max(1, b.r // 7), max(1, b.g // 7), max(1, b.b // 7))

    def _setup_ghost_plane(self, h: int, w: int) -> None:
        if self._grid_mode:
            self._fill_ghost_grid(h, w)
        elif self._theme_idx != _RAINBOW_IDX:
            tl, tr, bl, br = self._bg_colors
            self._ghost_plane.fill_gradient(
                tl=tl, tr=tr, bl=bl, br=br,
                char=" ", alpha=ALPHA_OPAQUE,
            )

    def _fill_ghost_grid(self, h: int, w: int) -> None:
        pool  = _POOLS.get(self._pool_key or "mixed", _POOLS["mixed"])
        color = self._grid_char_color()
        for row in range(h - 1):
            for col in range(w):
                self._ghost_plane.put_char(
                    row, col, random.choice(pool),
                    fg=color, bg=BLACK, dim=True,
                )

    def _apply_theme(self) -> None:
        self._apply_theme_values()
        if self._ghost_plane is None:
            return
        self._ghost_plane.clear()
        self._setup_ghost_plane(self._h, self._w)

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
            self._build_drops(self._h, self._w)
            return True
        if key == ord('g'):
            self._grid_mode = not self._grid_mode
            if self._grid_mode:
                self._fill_ghost_grid(self._h, self._w)
            else:
                self._ghost_plane.clear()
                self._setup_ghost_plane(self._h, self._w)
            self._build_drops(self._h, self._w)
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
        if key == ord('['):
            self._shear = max(_SHEAR_MIN,
                              round(self._shear - _SHEAR_STEP, 2))
            return True
        if key == ord(']'):
            self._shear = min(_SHEAR_MAX,
                              round(self._shear + _SHEAR_STEP, 2))
            return True
        if key == ord('-'):
            self._char_scale = max(_CHAR_SCALE_MIN,
                                   round(self._char_scale - _CHAR_SCALE_STEP, 2))
            return True
        if key == ord('='):
            self._char_scale = min(_CHAR_SCALE_MAX,
                                   round(self._char_scale + _CHAR_SCALE_STEP, 2))
            return True
        pool_map = {
            ord('0'): None,    ord('1'): 'drops',
            ord('2'): 'lines', ord('3'): 'ascii',
            ord('4'): 'unicode', ord('5'): 'mixed',
        }
        if key in pool_map:
            self._pool_key = pool_map[key]
            self._build_drops(self._h, self._w)
            return True
        return False

    @property
    def status_extras(self) -> str:
        theme = ("RAINBOW" if self._theme_idx == _RAINBOW_IDX
                 else _THEMES[self._theme_idx]["name"])
        pool  = _POOL_LABELS[self._pool_key]
        angle = int(self._shear * 45)
        scale = f"{self._char_scale:.2g}"
        grid  = "  g GRID:ON" if self._grid_mode else "  g GRID"
        arm   = _BURST_SIZES[self._burst_size_i]
        burst = f"  x BURST:ON({arm})" if self._burst_mode else "  x BURST"
        return (f"  o/p {theme}  l/0-5 {pool}"
                f"  [/] {angle:+d}°  -/= ×{scale}{grid}{burst}")

    @property
    def status_color(self) -> Color:
        if self._theme_idx == _RAINBOW_IDX:
            return _hsv(self._rainbow_hue, 0.7, 0.65)
        c = _THEMES[self._theme_idx]["bright"][0]
        return Color(max(0, c.r // 2), max(0, c.g // 2), max(0, c.b // 2))

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def init(self, renderer: CursesRenderer, h: int, w: int) -> None:
        self._h, self._w = h, w
        self._t = self._ghost_decay_t = 0
        self._splashes.clear()
        self._bursts.clear()
        self._rebuild_planes(h, w)
        self._build_drops(h, w)
        self._setup_ghost_plane(h, w)

    def on_resize(self, h: int, w: int) -> None:
        self._h, self._w = h, w
        self._splashes.clear()
        self._rebuild_planes(h, w)
        self._build_drops(h, w)
        self._setup_ghost_plane(h, w)

    def _rebuild_planes(self, h: int, w: int) -> None:
        self._ghost_plane  = Plane(h, w, z=0)
        self._drop_plane   = Plane(h, w, z=1)
        self._splash_plane = Plane(h, w, z=2)
        self._burst_plane  = Plane(h, w, z=3)

    def _build_drops(self, h: int, w: int) -> None:
        if h == 0 or w == 0:
            return
        pool = self._pool_key
        if self._grid_mode:
            self._drops = [
                _Drop(x, h, self.imap(0.4, 1.8), pool_key=pool, max_len=4)
                for x in range(w)
            ]
        else:
            target = max(1, min(
                int(self.imap(w * 0.15, w * 0.55) * self._char_scale), w))
            xs = random.sample(range(w), min(target, w))
            self._drops = [_Drop(x, h, self.imap(0.4, 1.8), pool_key=pool)
                           for x in xs]

    def update(self, h: int, w: int) -> None:
        self._h, self._w = h, w
        self._t += 1
        speed_mult = self.imap(0.5, 2.8)

        if self._theme_idx == _RAINBOW_IDX:
            self._rainbow_hue = (self._rainbow_hue + _RAINBOW_SPEED) % 1.0
            self._apply_theme_values()

        self._drop_plane.clear()
        self._splash_plane.clear()

        pool = self._pool_key
        splash_r = max(2, int(self.imap(3, 10)))

        dead = []
        for drop in self._drops:
            drop.update(speed_mult, shear=self._shear)

            # Spawn splash when drop lands
            if drop.splash_pos and not getattr(drop, '_splash_spawned', False):
                drop._splash_spawned = True
                sy, sx = drop.splash_pos
                self._splashes.append(_Splash(sy, sx, splash_r))
                # Leave a tiny puddle residue on ghost plane
                if random.random() < 0.45 and 0 <= sy < h - 1 and 0 <= sx < w:
                    self._ghost_plane.put_char(
                        sy, sx, random.choice(_SPLASH_FAR),
                        fg=self._ghost_color, bg=BLACK, dim=True,
                    )

            if drop.is_done():
                dead.append(drop)

        for drop in dead:
            self._drops.remove(drop)
            if self._grid_mode:
                self._drops.append(
                    _Drop(drop.x, h, self.imap(0.4, 1.8),
                          pool_key=pool, max_len=4))
            else:
                x = random.randrange(w)
                self._drops.append(_Drop(x, h, self.imap(0.4, 1.8), pool_key=pool))

        # Density control
        if not self._grid_mode:
            target = max(1, min(
                int(self.imap(w * 0.15, w * 0.55) * self._char_scale), w))
            while len(self._drops) < target:
                self._drops.append(
                    _Drop(random.randrange(w), h,
                          self.imap(0.4, 1.8), pool_key=pool))
            while len(self._drops) > target + 5:
                self._drops.pop()
        else:
            active_xs = {d.x for d in self._drops}
            for x in range(w):
                if x not in active_xs:
                    self._drops.append(
                        _Drop(x, h, self.imap(0.4, 1.8),
                              pool_key=pool, max_len=4))

        # Render drops
        for drop in self._drops:
            drop.render(self._drop_plane, h, self._trail_gradient, self._shear)

        # Splash animations
        alive_splashes = []
        for splash in self._splashes:
            splash.update()
            if not splash.is_done():
                splash.render(self._splash_plane, self._trail_gradient)
                alive_splashes.append(splash)
        self._splashes = alive_splashes

        # Ghost plane decay
        if not self._grid_mode:
            self._ghost_decay_t += 1
            decay_interval = max(2, int(self.imap(200, 50)))
            if self._ghost_decay_t >= decay_interval:
                self._ghost_decay_t = 0
                keys = list(self._ghost_plane._cells.keys())
                to_erase = random.sample(keys, max(0, len(keys) // 10))
                for k in to_erase:
                    del self._ghost_plane._cells[k]

        # Burst mode
        if self._burst_mode:
            self._burst_plane.clear()
            self._burst_t += 1
            interval  = max(8, int(self.imap(90, 10)))
            max_live  = max(2, int(self.imap(2, 10)))
            if self._burst_t >= interval and len(self._bursts) < max_live:
                self._burst_t = 0
                arm    = _BURST_SIZES[self._burst_size_i]
                margin = arm * 2 + 2
                cy = random.randint(1, max(1, h - 3))
                cx = random.randint(margin, max(margin, w - margin - 1))
                bpool = _POOLS.get(self._pool_key or "mixed", _POOLS["mixed"])
                self._bursts.append(_Burst(cy, cx, arm, bpool))
            alive = []
            for burst in self._bursts:
                burst.update()
                if not burst.is_done():
                    burst.render(self._burst_plane, self._trail_gradient)
                    alive.append(burst)
            self._bursts = alive

    def planes(self) -> list[Plane]:
        ps = [self._ghost_plane, self._drop_plane, self._splash_plane]
        if self._burst_mode:
            ps.append(self._burst_plane)
        return ps
