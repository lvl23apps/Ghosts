"""Matrix Rain — rebuilt on the ghosts2 plane/renderer model.

Scene-specific controls:
  o / p        cycle colour theme  (GREEN BLUE RED AMBER PURPLE CYAN WHITE RAINBOW)
  l            toggle λ mode — pool switches to Greek/lambda-calculus characters
  0-5          character pool  (0=random 1=katakana 2=kanji 3=math 4=mixed 5=latin)
  [ / ]        tilt angle  (shear ±45°, step ≈ 7°)
  - / =        fewer / more characters  (density ×0.25 – ×4.0)
  g            toggle grid mode — every screen cell is a character
  x            toggle burst mode — random ASCII starburst explosions
  { / }        burst size — arm length 3 → 5 → 7 → 10 → 14 → 20
"""

from __future__ import annotations

import colorsys
import random
from typing import Optional

from renderer import (
    Plane, Color, CursesRenderer,
    ALPHA_OPAQUE,
    BLACK, WHITE,
)
from scene_base import Scene
from effects import (
    _hsv, _build_gradient, _hue_gradient,
    _THEMES, _RAINBOW_IDX, _RAINBOW_SPEED,
    _BURST_DIRS, _BURST_SIZES, _BURST_CENTRE, _Burst,
)

# ── Character pools ──────────────────────────────────────────────────────────

_KATAKANA = [chr(c) for c in range(0x30A1, 0x30F7)]
_HIRAGANA = [chr(c) for c in range(0x3041, 0x3097)]
_KANJI    = list("一二三四五六七八九十百千万億兆日月火水木金土曜年時分秒")
_MATH     = list("∀∂∃∅∆∇∈∏∑−∓∔∗∘√∛∝∞∫∬∮∯∰∱∲∳∴∵∶∷∸∹")
_SYMBOLS  = list("☯☢☣✦✧★⊕⊗⊙⊚⊛⊜♦♠♣♥◆◇◈⌬⌭⌮⌯⏣⏢⏥⏦")
_BRAILLE  = [chr(c) for c in range(0x2840, 0x28C0)
             if bin(c - 0x2800).count("1") >= 4]
_LATIN    = list("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz")
_DIGITS   = list("0123456789!@#$%^&*()[]{}<>|/\\")
_LAMBDA   = (
    ['λ'] * 14                                  # dominant λ
    + list("Λαβγδεζηθικμνξπρστυφχψω")           # Greek lower
    + list("ΑΒΓΔΕΖΗΘΙΚΜΝΞΠΡΣΤΥΦΧΨΩ")            # Greek upper
    + list("∀∃∂∇∈∉∋∏∐∑∞∫∮∴∵≡≤≥≪≫⊢⊣⊥⊤")         # logic / lambda-calculus
)

_POOLS = {
    "katakana": _KATAKANA + _KATAKANA + _LATIN[:10],
    "kanji":    _KANJI + _HIRAGANA + _KATAKANA[:20],
    "math":     _MATH + _SYMBOLS + _BRAILLE[:20],
    "mixed":    _KATAKANA + _KANJI[:10] + _MATH[:10] + _SYMBOLS[:10],
    "latin":    _LATIN + _DIGITS + _SYMBOLS[:8],
    "lambda":   _LAMBDA,
}
_POOL_NAMES  = list(_POOLS.keys())

_SHEAR_MIN  = -1.5
_SHEAR_MAX  =  1.5
_SHEAR_STEP =  0.25

_POOL_LABELS = {
    None:       "RANDOM",
    "katakana": "KATAKANA",
    "kanji":    "KANJI",
    "math":     "MATH",
    "mixed":    "MIXED",
    "latin":    "LATIN",
    "lambda":   "λ MODE",
}

# ── Column ───────────────────────────────────────────────────────────────────

class _Col:
    """One falling column of rain."""

    def __init__(self, x: int, h: int, intensity: float,
                 pool_key: Optional[str] = None,
                 max_len: Optional[int] = None):
        self.x              = x
        self.h              = h
        if pool_key and pool_key in _POOLS:
            self.pool       = _POOLS[pool_key]
        else:
            self.pool       = _POOLS[random.choice(_POOL_NAMES)]
        self.speed          = random.uniform(0.3, 0.8 + intensity * 0.18)
        self.head_y         = float(random.randint(-h, 0))
        self.max_len        = max_len if max_len is not None else random.randint(6, min(30, h - 2))
        self.trail: list[list] = []
        self.mut_base       = random.randint(4, 18)
        self.ghost_cells: list[tuple[int, int, str]] = []
        self.ghost_captured = False

    def _rand_char(self) -> str:
        return random.choice(self.pool)

    def update(self, speed_mult: float, mutation_rate_mult: float,
               shear: float = 0.0) -> None:
        self.head_y += self.speed * speed_mult
        head_iy = int(self.head_y)

        while len(self.trail) < min(self.max_len, head_iy + 1):
            self.trail.append([self._rand_char(),
                                random.randint(2, self.mut_base), 0])

        for cell in self.trail:
            cell[1] -= mutation_rate_mult
            if cell[1] <= 0:
                cell[0] = self._rand_char()
                cell[1] = random.randint(2, self.mut_base)
            if cell[2] > 0:
                cell[2] -= 1

        if self.trail and random.random() < 0.01:
            i = random.randint(1, max(1, len(self.trail) - 2))
            if i < len(self.trail):
                self.trail[i][2] = random.randint(2, 6)

        if not self.ghost_captured and head_iy >= self.h:
            self.ghost_captured = True
            self.ghost_cells = [
                (head_iy - i, self.x + int(shear * i), cell[0])
                for i, cell in enumerate(self.trail)
                if 0 <= head_iy - i < self.h
            ]

    def is_done(self) -> bool:
        return self.head_y - len(self.trail) > self.h

    def render_to_planes(self, trail_plane: Plane, head_plane: Plane,
                         h: int, trail_gradient: list[Color],
                         spark_color: Color, shear: float) -> None:
        head_iy = int(self.head_y)
        n_grad  = len(trail_gradient)
        w       = trail_plane.w

        for i, cell_data in enumerate(self.trail):
            y = head_iy - i
            x = self.x + int(shear * i)
            if y < 0 or y >= h - 1 or x < 0 or x >= w:
                continue
            char, _, spark_t = cell_data
            if i == 0:
                head_plane.put_char(y, x, char, fg=WHITE, bg=BLACK, bold=True)
            else:
                grad_i = min(i, n_grad - 1)
                color  = trail_gradient[grad_i]
                if spark_t > 0:
                    color = spark_color
                    bold  = True
                    dim   = False
                else:
                    bold = (i <= 2)
                    dim  = (i >= n_grad - 2)
                trail_plane.put_char(y, x, char,
                                     fg=color, bg=BLACK, bold=bold, dim=dim)


# ── Scene ─────────────────────────────────────────────────────────────────────

class MatrixRain(Scene):
    name = "Matrix Rain"

    def __init__(self):
        self._ghost_plane: Optional[Plane] = None
        self._trail_plane: Optional[Plane] = None
        self._head_plane:  Optional[Plane] = None
        self._cols:        list[_Col]      = []
        self._h = self._w = 0
        self._t = 0
        self._ghost_decay_t = 0
        # Controllable state
        self._theme_idx  = 0
        self._pool_key: Optional[str] = None
        self._shear      = 0.0
        self._char_scale = 1.0
        self._rainbow_hue = 0.0
        self._grid_mode  = False
        self._burst_mode = False
        self._burst_size_idx = 2        # index into _BURST_SIZES (default 7)
        self._burst_t    = 0
        self._bursts: list[_Burst] = []
        self._burst_plane: Optional[Plane] = None
        # Derived from theme
        self._trail_gradient: list[Color] = []
        self._ghost_color: Color = Color(0, 10, 0)
        self._spark_color: Color = Color(220, 255, 220)
        self._bg_colors = (Color(0, 6, 0), Color(0, 3, 0),
                           Color(0, 5, 0), Color(0, 2, 0))
        self._apply_theme_values()

    # ── Theme helpers ─────────────────────────────────────────────────────────

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
        """Return a dim-but-visible background colour for grid mode cells."""
        if self._theme_idx == _RAINBOW_IDX:
            return _hsv(self._rainbow_hue, 0.9, 0.18)
        b = _THEMES[self._theme_idx]["bright"][1]
        return Color(max(1, b.r // 7), max(1, b.g // 7), max(1, b.b // 7))

    def _setup_ghost_plane(self, h: int, w: int) -> None:
        """Initialise the ghost plane — gradient fill or full character grid."""
        if self._grid_mode:
            self._fill_ghost_grid(h, w)
        elif self._theme_idx != _RAINBOW_IDX:
            tl, tr, bl, br = self._bg_colors
            self._ghost_plane.fill_gradient(
                tl=tl, tr=tr, bl=bl, br=br,
                char=" ", alpha=ALPHA_OPAQUE,
            )

    def _fill_ghost_grid(self, h: int, w: int) -> None:
        """Fill every ghost-plane cell with a dim background character."""
        pool = _POOLS.get(self._pool_key or "mixed", _POOLS["mixed"])
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

    # ── Scene-specific controls ───────────────────────────────────────────────

    def on_key(self, key: int) -> bool:
        # Colour theme
        if key == ord('p'):
            self._theme_idx = (self._theme_idx + 1) % (_RAINBOW_IDX + 1)
            self._apply_theme()
            return True
        if key == ord('o'):
            self._theme_idx = (self._theme_idx - 1) % (_RAINBOW_IDX + 1)
            self._apply_theme()
            return True
        # Burst mode
        if key == ord('x'):
            self._burst_mode = not self._burst_mode
            if not self._burst_mode:
                self._bursts.clear()
                if self._burst_plane:
                    self._burst_plane.clear()
            return True
        if key == ord('{'):
            self._burst_size_idx = max(0, self._burst_size_idx - 1)
            return True
        if key == ord('}'):
            self._burst_size_idx = min(len(_BURST_SIZES) - 1,
                                       self._burst_size_idx + 1)
            return True
        # λ mode — toggle the lambda-calculus/Greek character pool
        if key == ord('l'):
            if self._pool_key == "lambda":
                self._pool_key = None
            else:
                self._pool_key = "lambda"
            self._build_columns(self._h, self._w)
            return True
        # Grid mode — full-screen character background + all columns active
        if key == ord('g'):
            self._grid_mode = not self._grid_mode
            if self._grid_mode:
                self._fill_ghost_grid(self._h, self._w)
            else:
                self._ghost_plane.clear()
                self._setup_ghost_plane(self._h, self._w)
            self._build_columns(self._h, self._w)
            return True
        # Tilt / shear
        if key == ord(']'):
            self._shear = min(_SHEAR_MAX, round(self._shear + _SHEAR_STEP, 2))
            return True
        if key == ord('['):
            self._shear = max(_SHEAR_MIN, round(self._shear - _SHEAR_STEP, 2))
            return True
        # Character density
        if key == ord('='):
            self._char_scale = min(_CHAR_SCALE_MAX,
                                   round(self._char_scale + _CHAR_SCALE_STEP, 2))
            return True
        if key == ord('-'):
            self._char_scale = max(_CHAR_SCALE_MIN,
                                   round(self._char_scale - _CHAR_SCALE_STEP, 2))
            return True
        # Character pool (0-5; pressing these exits lambda mode naturally)
        pool_map = {
            ord('0'): None,
            ord('1'): 'katakana',
            ord('2'): 'kanji',
            ord('3'): 'math',
            ord('4'): 'mixed',
            ord('5'): 'latin',
        }
        if key in pool_map:
            self._pool_key = pool_map[key]
            self._build_columns(self._h, self._w)
            return True
        return False

    @property
    def status_extras(self) -> str:
        if self._theme_idx == _RAINBOW_IDX:
            theme = "RAINBOW"
        else:
            theme = _THEMES[self._theme_idx]["name"]
        pool  = _POOL_LABELS[self._pool_key]
        angle = int(self._shear * 45)
        scale = f"{self._char_scale:.2g}"
        grid  = "  g GRID:ON" if self._grid_mode else "  g GRID"
        arm   = _BURST_SIZES[self._burst_size_idx]
        burst = f"  x BURST:ON({arm})" if self._burst_mode else "  x BURST"
        return f"  o/p {theme}  l/0-5 {pool}  [/] {angle:+d}°  -/= ×{scale}{grid}{burst}"

    @property
    def status_color(self) -> Color:
        if self._theme_idx == _RAINBOW_IDX:
            return _hsv(self._rainbow_hue, 0.7, 0.65)
        c = _THEMES[self._theme_idx]["bright"][0]
        return Color(max(0, c.r // 2), max(0, c.g // 2), max(0, c.b // 2))

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def init(self, renderer: CursesRenderer, h: int, w: int) -> None:
        self._h, self._w = h, w
        self._t = 0
        self._ghost_decay_t = 0
        self._rebuild_planes(h, w)
        self._build_columns(h, w)
        self._setup_ghost_plane(h, w)

    def on_resize(self, h: int, w: int) -> None:
        self._h, self._w = h, w
        self._rebuild_planes(h, w)
        self._build_columns(h, w)
        self._setup_ghost_plane(h, w)

    def _rebuild_planes(self, h: int, w: int) -> None:
        self._ghost_plane = Plane(h, w, z=0)
        self._trail_plane = Plane(h, w, z=1)
        self._head_plane  = Plane(h, w, z=2)
        self._burst_plane = Plane(h, w, z=3)
        self._bursts.clear()

    def _build_columns(self, h: int, w: int) -> None:
        if h == 0 or w == 0:
            return
        pool = self._pool_key
        if self._grid_mode:
            # One column per x position, full-height trails
            self._cols = [
                _Col(x, h, self.imap(0.4, 2.0), pool_key=pool, max_len=h - 1)
                for x in range(w)
            ]
        else:
            target = max(1, min(
                int(self.imap(w * 0.3, w * 0.85) * self._char_scale), w))
            xs = random.sample(range(w), min(target, w))
            self._cols = [_Col(x, h, self.imap(0.4, 2.0), pool_key=pool) for x in xs]

    def update(self, h: int, w: int) -> None:
        self._h, self._w = h, w
        self._t += 1
        speed_mult    = self.imap(0.4, 2.5)
        mut_rate_mult = self.imap(0.3, 1.5)

        if self._theme_idx == _RAINBOW_IDX:
            self._rainbow_hue = (self._rainbow_hue + _RAINBOW_SPEED) % 1.0
            self._apply_theme_values()

        self._trail_plane.clear()
        self._head_plane.clear()

        pool = self._pool_key
        dead = []
        for col in self._cols:
            col.update(speed_mult, mut_rate_mult, shear=self._shear)
            if col.is_done():
                if not self._grid_mode:
                    # In grid mode, ghost chars come from _fill_ghost_grid
                    for gy, gx, gchar in col.ghost_cells:
                        if 0 <= gx < w and random.random() < 0.18:
                            self._ghost_plane.put_char(
                                gy, gx, gchar,
                                fg=self._ghost_color, bg=BLACK, dim=True,
                            )
                dead.append(col)

        for col in dead:
            self._cols.remove(col)
            if self._grid_mode:
                # Replace at the same x so every position stays covered
                self._cols.append(_Col(col.x, h, self.imap(0.4, 2.0),
                                       pool_key=pool, max_len=h - 1))
            else:
                x = random.randrange(w)
                stale = [k for k in self._ghost_plane._cells if k[1] == x]
                for k in stale:
                    del self._ghost_plane._cells[k]
                self._cols.append(_Col(x, h, self.imap(0.4, 2.0), pool_key=pool))

        # Ghost plane decay (skip in grid mode — background is managed separately)
        if not self._grid_mode:
            self._ghost_decay_t += 1
            decay_interval = max(2, int(self.imap(180, 40)))
            if self._ghost_decay_t >= decay_interval:
                self._ghost_decay_t = 0
                keys = list(self._ghost_plane._cells.keys())
                to_erase = random.sample(keys, max(0, len(keys) // 8))
                for k in to_erase:
                    del self._ghost_plane._cells[k]

        # Density control (not needed in grid mode — columns are pinned to positions)
        if not self._grid_mode:
            target = max(1, min(
                int(self.imap(w * 0.3, w * 0.85) * self._char_scale), w))
            while len(self._cols) < target:
                x = random.randrange(w)
                self._cols.append(_Col(x, h, self.imap(0.4, 2.0), pool_key=pool))
            while len(self._cols) > target + 5:
                self._cols.pop()

        # In grid mode, ensure all x positions are covered (gap-fill after resize etc.)
        if self._grid_mode:
            active_xs = {col.x for col in self._cols}
            for x in range(w):
                if x not in active_xs:
                    self._cols.append(_Col(x, h, self.imap(0.4, 2.0),
                                           pool_key=pool, max_len=h - 1))

        for col in self._cols:
            col.render_to_planes(
                self._trail_plane, self._head_plane,
                h, self._trail_gradient, self._spark_color, self._shear,
            )

        # ── Burst rendering ───────────────────────────────────────────────
        if self._burst_mode:
            self._burst_plane.clear()

            # Spawn new burst on interval (rate scales with intensity)
            self._burst_t += 1
            interval = max(8, int(self.imap(90, 10)))
            max_live  = max(2, int(self.imap(2, 10)))
            if self._burst_t >= interval and len(self._bursts) < max_live:
                self._burst_t = 0
                arm = _BURST_SIZES[self._burst_size_idx]
                margin = arm * 2 + 2
                cy = random.randint(1, max(1, h - 3))
                cx = random.randint(margin, max(margin, w - margin - 1))
                pool = _POOLS.get(self._pool_key or "mixed", _POOLS["mixed"])
                self._bursts.append(_Burst(cy, cx, arm, pool))

            # Tick and render
            alive = []
            for burst in self._bursts:
                burst.update()
                if not burst.is_done():
                    burst.render(self._burst_plane, self._trail_gradient)
                    alive.append(burst)
            self._bursts = alive

    def planes(self) -> list[Plane]:
        planes = [self._ghost_plane, self._trail_plane, self._head_plane]
        if self._burst_mode:
            planes.append(self._burst_plane)
        return planes
