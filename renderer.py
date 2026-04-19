"""
Renderer abstraction inspired by notcurses.

Core concepts borrowed:
  - Cell: per-cell 24-bit RGB fg + bg color, independent of any global pair table
  - Plane: a sparse 2D framebuffer with (y, x, z) position; planes composite
  - Renderer: composites planes back-to-front and outputs to the terminal

On 256-color terminals the CursesRenderer maps RGB → xterm-256 cube and
caches color pairs dynamically.  On truecolor terminals it can optionally emit
ANSI SGR 38;2 / 48;2 sequences directly through a thin escape-sequence layer
that sits beneath curses (curses handles input/cursor; we own foreground output
via sys.stdout when in "direct" mode).

This file deliberately has no scene logic — only the rendering primitive layer.
"""

from __future__ import annotations

import curses
import sys
from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple


# ── Color ────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Color:
    r: int
    g: int
    b: int

    def lerp(self, other: "Color", t: float) -> "Color":
        """Linear interpolate towards other by t ∈ [0, 1]."""
        return Color(
            int(self.r + (other.r - self.r) * t),
            int(self.g + (other.g - self.g) * t),
            int(self.b + (other.b - self.b) * t),
        )

    def to_256(self) -> int:
        """Map to nearest xterm-256 colour index.

        Uses the 6×6×6 colour cube (indices 16-231).
        For near-grey colours the 24-step greyscale ramp (232-255) is used
        when it produces a closer match.
        """
        r6 = round(self.r / 255 * 5)
        g6 = round(self.g / 255 * 5)
        b6 = round(self.b / 255 * 5)
        cube = 16 + 36 * r6 + 6 * g6 + b6

        # Greyscale ramp check: use it when r≈g≈b and not at pure extremes
        rng = max(self.r, self.g, self.b) - min(self.r, self.g, self.b)
        if rng < 20 and 0 < r6 < 5:
            gray_idx = round(self.r / 255 * 23)
            return 232 + gray_idx

        return cube

    def __repr__(self) -> str:
        return f"Color(#{self.r:02x}{self.g:02x}{self.b:02x})"


# Sentinel colours ─────────────────────────────────────────────────────────
BLACK   = Color(0,   0,   0)
WHITE   = Color(255, 255, 255)
GREEN   = Color(0,   255, 0)
DGGREEN = Color(0,   30,  0)   # deep ghost green


def gradient(start: Color, end: Color, steps: int) -> list[Color]:
    """Return a list of 'steps' colours linearly interpolated start→end."""
    if steps <= 1:
        return [start]
    return [start.lerp(end, i / (steps - 1)) for i in range(steps)]


# ── Cell ─────────────────────────────────────────────────────────────────────

ALPHA_OPAQUE      = 0   # cell fully covers planes below (notcurses: NCALPHA_OPAQUE)
ALPHA_TRANSPARENT = 1   # cell is invisible; lower planes show through
ALPHA_BLEND       = 2   # fg/bg blended with cell below (approximated)


@dataclass
class Cell:
    """A single terminal cell — character + per-cell 24-bit colours + attrs.

    Mirrors the notcurses nccell model:
      gcluster  → char
      channels  → fg / bg  (full 24-bit RGB, not a pair index)
      stylemask → bold, dim, blink
      alpha     → ALPHA_* constant
    """
    char:  str   = " "
    fg:    Color = field(default_factory=lambda: WHITE)
    bg:    Color = field(default_factory=lambda: BLACK)
    bold:  bool  = False
    dim:   bool  = False
    blink: bool  = False
    alpha: int   = ALPHA_OPAQUE

    @classmethod
    def transparent(cls) -> "Cell":
        c = cls()
        c.alpha = ALPHA_TRANSPARENT
        return c


# ── Plane ─────────────────────────────────────────────────────────────────────

class Plane:
    """A Z-ordered 2D framebuffer — sparse dict of (row, col) → Cell.

    Inspired by the notcurses ncplane:
      - Planes live at (y, x) on screen and at z in the pile order.
      - Transparent cells let lower planes show through (ALPHA_TRANSPARENT).
      - fill_gradient() implements ncplane_gradient() bilinear interpolation.
      - Planes are composited by the Renderer, not rendered directly.
    """

    def __init__(self, h: int, w: int, y: int = 0, x: int = 0, z: int = 0):
        self.h = h
        self.w = w
        self.y = y
        self.x = x
        self.z = z
        self._cells: Dict[Tuple[int, int], Cell] = {}

    # ── Primitive put/get ────────────────────────────────────────────────────

    def put(self, row: int, col: int, cell: Cell) -> None:
        if 0 <= row < self.h and 0 <= col < self.w:
            self._cells[(row, col)] = cell

    def put_char(self, row: int, col: int, char: str,
                 fg: Color = WHITE, bg: Color = BLACK,
                 bold: bool = False, dim: bool = False,
                 alpha: int = ALPHA_OPAQUE) -> None:
        self.put(row, col, Cell(char=char, fg=fg, bg=bg,
                                bold=bold, dim=dim, alpha=alpha))

    def get(self, row: int, col: int) -> Optional[Cell]:
        return self._cells.get((row, col))

    def clear(self) -> None:
        self._cells.clear()

    # ── High-level fills ─────────────────────────────────────────────────────

    def fill_gradient(self,
                      tl: Color, tr: Color, bl: Color, br: Color,
                      char: str = " ",
                      row0: int = 0, col0: int = 0,
                      row1: Optional[int] = None, col1: Optional[int] = None,
                      alpha: int = ALPHA_OPAQUE) -> None:
        """Bilinear gradient fill — mirrors ncplane_gradient().

        Each cell's colour is bilinearly interpolated between the four
        corner colours (top-left, top-right, bottom-left, bottom-right).
        """
        row1 = row1 if row1 is not None else self.h
        col1 = col1 if col1 is not None else self.w
        rows = max(1, row1 - row0)
        cols = max(1, col1 - col0)
        for r in range(row0, row1):
            ty = (r - row0) / (rows - 1) if rows > 1 else 0.0
            for c in range(col0, col1):
                tx = (c - col0) / (cols - 1) if cols > 1 else 0.0
                top   = tl.lerp(tr, tx)
                bot   = bl.lerp(br, tx)
                color = top.lerp(bot, ty)
                self.put(r, c, Cell(char=char, fg=color, bg=BLACK, alpha=alpha))

    def fill_column_gradient(self, col: int,
                              colors: list[Color], chars: list[str],
                              row0: int = 0) -> None:
        """Fill a single column with a per-row colour list (trail gradient)."""
        for i, (color, char) in enumerate(zip(colors, chars)):
            r = row0 + i
            bold = (i <= 2)
            dim  = (i >= len(colors) - 3)
            self.put(r, col, Cell(char=char, fg=color, bg=BLACK,
                                  bold=bold, dim=dim))

    # ── Fade (step-based, mirrors ncplane_fadeout_iteration) ─────────────────

    def fade_out_step(self, step: int, total_steps: int) -> None:
        """Darken every cell's fg by one step towards black (simulates ncplane_fadeout)."""
        t = step / total_steps
        for key, cell in self._cells.items():
            if cell.alpha == ALPHA_TRANSPARENT:
                continue
            new_fg = cell.fg.lerp(BLACK, t)
            self._cells[key] = Cell(char=cell.char, fg=new_fg, bg=cell.bg,
                                    bold=cell.bold, dim=cell.dim, alpha=cell.alpha)


# ── Renderer ─────────────────────────────────────────────────────────────────

class CursesRenderer:
    """Composite planes and output to curses screen.

    Rendering model:
      1. Sort planes by z (lowest = back).
      2. For each plane cell, if ALPHA_TRANSPARENT skip; else write to the
         screen framebuffer (overwriting whatever lower plane wrote).
      3. Map RGB → 256-colour index → curses colour pair (cached).

    The pair cache starts at pair 32 to leave 1-31 free for any scene that
    uses legacy 8-colour pairs.  The cache evicts all entries if it fills
    (keeps the last-used pairs valid; stale pairs may briefly show wrong
    colour on the eviction frame).
    """

    _PAIR_BASE = 32
    _PAIR_MAX  = 4096   # curses supports up to COLOR_PAIRS-1

    def __init__(self):
        self._pair_cache: Dict[Tuple[int, int], int] = {}
        self._next_pair  = self._PAIR_BASE
        self._can_256    = False
        self._stdscr     = None

    def setup(self, stdscr) -> None:
        self._stdscr = stdscr
        curses.start_color()
        curses.use_default_colors()
        self._can_256 = curses.COLORS >= 256
        # Eagerly define the standard green gradient pairs used by Matrix
        if self._can_256:
            _MATRIX_GREENS = [
                (231, -1),  # white fg, default bg
                (46,  -1),  # #00ff00
                (40,  -1),  # #00d700
                (34,  -1),  # #00af00
                (28,  -1),  # #008700
                (22,  -1),  # #005f00
                (234, -1),  # #1c1c1c  (ghost)
                (236, -1),  # #303030  (faint ghost)
            ]
            for i, (fg, bg) in enumerate(_MATRIX_GREENS):
                pair = self._PAIR_BASE + i
                curses.init_pair(pair, fg, bg)
            self._next_pair = self._PAIR_BASE + len(_MATRIX_GREENS)

    def _get_pair(self, fg: Color, bg: Color) -> int:
        """Return a curses pair number for this fg/bg combination."""
        if not self._can_256:
            return 0
        fg_idx = fg.to_256()
        bg_idx = bg.to_256() if bg != BLACK else -1
        key    = (fg_idx, bg_idx)
        if key in self._pair_cache:
            return self._pair_cache[key]
        # Evict if full
        if self._next_pair >= min(self._PAIR_MAX, curses.COLOR_PAIRS - 1):
            self._pair_cache.clear()
            self._next_pair = self._PAIR_BASE + 8  # keep the eager greens
        pair = self._next_pair
        self._next_pair += 1
        curses.init_pair(pair, fg_idx, bg_idx)
        self._pair_cache[key] = pair
        return pair

    def composite(self, planes: list[Plane], h: int, w: int) -> None:
        """Composite all planes z-back-to-front onto the curses screen."""
        stdscr = self._stdscr
        for plane in sorted(planes, key=lambda p: p.z):
            py, px = plane.y, plane.x
            for (row, col), cell in plane._cells.items():
                sy = py + row
                sx = px + col
                if sy < 0 or sy >= h - 1 or sx < 0 or sx >= w:
                    continue
                if cell.alpha == ALPHA_TRANSPARENT:
                    continue
                pair = self._get_pair(cell.fg, cell.bg)
                attr = curses.color_pair(pair)
                if cell.bold:
                    attr |= curses.A_BOLD
                if cell.dim:
                    attr |= curses.A_DIM
                if cell.blink:
                    attr |= curses.A_BLINK
                try:
                    stdscr.addstr(sy, sx, cell.char, attr)
                except curses.error:
                    pass

    def status(self, stdscr, h: int, w: int, text: str,
               fg: Color = Color(0, 180, 0)) -> None:
        """Write a status bar at the bottom of the screen."""
        pair = self._get_pair(fg, BLACK)
        attr = curses.color_pair(pair) | curses.A_DIM
        try:
            stdscr.addstr(h - 1, 0, text[:w - 1].ljust(w - 1), attr)
        except curses.error:
            pass
