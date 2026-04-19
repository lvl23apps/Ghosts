# ghosts2 — Scene Building Guide

Hand this file to a Claude model along with the source files listed under **Required Reading**. It contains everything needed to build a new scene from scratch with no additional context.

---

## Required Reading

Before writing any code, read these files in order:

1. `renderer.py` — Color, Cell, Plane, CursesRenderer APIs
2. `scene_base.py` — Scene base class and lifecycle contract
3. `effects.py` — shared themes, gradients, _Burst class
4. `scenes/rain.py` — reference implementation (clean, fully-featured)
5. `scenes/plasma.py` — reference for full-screen field scenes
6. `scenes/__init__.py` — registration list
7. `main.py` — SCENE_CLASSES list and global key routing

---

## Architecture in One Page

```
main.py
  └─ curses loop → scenes[idx].update(h, w)
                 → renderer.composite(sc.planes(), h, w)
                 → renderer.status(stdscr, h, w, bar, sc.status_color)

A scene owns 1–N Plane objects.
Each Plane is a sparse dict of (row, col) → Cell.
Cells have: char, fg Color, bg Color, bold, dim, alpha.
Planes are z-sorted and composited back-to-front.
Row h-1 is the status bar — NEVER write there.
```

### Coordinate system

```
(0,0) ─────────────── (0, w-1)
  │                        │
  │   content area         │   rows 0 .. h-2
  │                        │
(h-2, 0) ─────── (h-2, w-1)
(h-1, 0) ─────── (h-1, w-1)   ← status bar (renderer owns this)
```

---

## Key APIs

### Color

```python
from renderer import Color, BLACK, WHITE, gradient

c = Color(r, g, b)           # 24-bit RGB, ints 0-255
c2 = c.lerp(other, t)        # linear interpolate, t ∈ [0,1]
idx = c.to_256()             # map to nearest xterm-256 index

gradient(start, end, steps)  # returns list[Color], length=steps
BLACK = Color(0, 0, 0)
WHITE = Color(255, 255, 255)
```

### Plane

```python
from renderer import Plane, ALPHA_OPAQUE, ALPHA_TRANSPARENT

p = Plane(h, w, z=0)         # z controls composite order (lower = behind)

p.put_char(row, col, char,
           fg=WHITE, bg=BLACK,
           bold=False, dim=False,
           alpha=ALPHA_OPAQUE)

p.fill_gradient(tl, tr, bl, br,   # four corner Colors
                char=" ",
                alpha=ALPHA_OPAQUE)

p.clear()                    # wipe all cells
p.fade_out_step(step, total) # darken all cells by one step
p._cells                     # dict[(row,col)] → Cell  (read/write directly if needed)
```

Alpha constants:
- `ALPHA_OPAQUE = 0` — cell fully covers lower planes (default)
- `ALPHA_TRANSPARENT = 1` — cell is invisible, lower planes show through
- `ALPHA_BLEND = 2` — blend with plane below (approximate)

### Scene base class

```python
from scene_base import Scene

class MyScene(Scene):
    name = "My Scene"          # shown in status bar

    # intensity: int 1–10, set externally by main loop
    # imap(lo, hi) → float    maps intensity 1→lo, 10→hi

    def init(self, renderer, h: int, w: int) -> None:
        """Called once when scene becomes active. Build planes here."""

    def on_resize(self, h: int, w: int) -> None:
        """Terminal was resized. Rebuild planes."""

    def update(self, h: int, w: int) -> None:
        """Advance simulation one frame. Clear and redraw planes here."""

    def planes(self) -> list[Plane]:
        """Return planes for the renderer to composite this frame."""
        return [self._plane]

    def cleanup(self) -> None:
        """Called when switching away. Release heavy state if needed."""

    def on_key(self, key: int) -> bool:
        """Handle scene-specific key. Return True if consumed."""
        return False

    @property
    def status_extras(self) -> str:
        """Appended to the main status bar. Start with two spaces."""
        return "  key LABEL"

    @property
    def status_color(self) -> Color:
        """Color for the status bar text."""
        return Color(0, 150, 0)
```

---

## effects.py — Shared Utilities

```python
from effects import (
    _hsv,                      # _hsv(h,s,v) → Color  (h,s,v all 0.0–1.0)
    _build_gradient,           # _build_gradient(theme_dict) → list[Color] (12 steps)
    _hue_gradient,             # _hue_gradient(hue) → list[Color]  (rainbow)
    _THEMES,                   # list of 7 theme dicts (indices 0–6)
    _RAINBOW_IDX,              # = 7, sentinel for animated rainbow
    _RAINBOW_SPEED,            # = 0.0025, hue advance per frame
    _BURST_SIZES,              # [3, 5, 7, 10, 14, 20]
    _Burst,                    # starburst explosion class
)
```

### Theme dict structure

```python
_THEMES[i] = {
    "name":   "GREEN",
    "head":   Color(...),      # bright head colour
    "bright": (Color, Color),  # bright gradient endpoints
    "mid":    (Color, Color),
    "dark":   (Color, Color),
    "ghost":  Color(...),      # haze / residue colour
    "spark":  Color(...),      # sparkle colour
    "bg":     (Color, Color, Color, Color),  # background corners tl,tr,bl,br
}
```

Theme indices: 0=GREEN 1=BLUE 2=RED 3=AMBER 4=PURPLE 5=CYAN 6=WHITE; 7=RAINBOW sentinel.

### _Burst

```python
burst = _Burst(cy, cx, arm_len, pool)
# cy, cx     — centre row/col
# arm_len    — arm length in cells (from _BURST_SIZES)
# pool       — list[str] of characters to use in arms

burst.update()               # call every frame
burst.is_done() → bool
burst.render(plane, grad)    # grad = list[Color], at least 12 entries
```

Lifecycle: grow → hold (4 frames) → shrink. Total frames = arm_len + 4 + arm_len.

---

## Standard Control Conventions

All existing scenes follow this key assignment. New scenes should match it:

| Key | Behaviour |
|-----|-----------|
| `o` / `p` | Cycle theme/palette backward / forward |
| `l` | Toggle λ (lambda) character pool |
| `0`–`5` | Select character pool or preset |
| `[` / `]` | Scene-specific continuous control (angle, speed, complexity…) |
| `-` / `=` | Density or speed (scale factor) |
| `g` | Toggle a secondary visual mode |
| `x` | Toggle burst mode |
| `{` / `}` | Burst size (cycles through _BURST_SIZES) |

Global keys handled by `main.py` (do **not** intercept these):
`q` Esc `↑` `↓` `←` `→` `Space` `Tab`

### Status bar format

```python
@property
def status_extras(self) -> str:
    # Each control shown as "  key CURRENT_VALUE"
    # Keys that toggle show ":ON" suffix when active
    return (f"  o/p {theme_name}"
            f"  [/] LABEL"
            f"  g MODE:ON" if active else "  g MODE")
```

The main loop prepends: `  ●○○  Scene Name  ↑↓ 5/10`

---

## Rainbow Theme Pattern

Copy this boilerplate for rainbow support:

```python
from effects import _THEMES, _RAINBOW_IDX, _RAINBOW_SPEED, _hue_gradient, _build_gradient

# In __init__:
self._theme_idx   = 0          # default theme
self._rainbow_hue = 0.0

# In _apply_theme_values():
def _apply_theme_values(self):
    if self._theme_idx == _RAINBOW_IDX:
        self._gradient = _hue_gradient(self._rainbow_hue)
        return
    self._gradient = _build_gradient(_THEMES[self._theme_idx])

# In update(), at the top:
if self._theme_idx == _RAINBOW_IDX:
    self._rainbow_hue = (self._rainbow_hue + _RAINBOW_SPEED) % 1.0
    self._apply_theme_values()

# In on_key():
if key == ord('p'):
    self._theme_idx = (self._theme_idx + 1) % (_RAINBOW_IDX + 1)
    self._apply_theme_values()
    return True
if key == ord('o'):
    self._theme_idx = (self._theme_idx - 1) % (_RAINBOW_IDX + 1)
    self._apply_theme_values()
    return True

# Status colour helper:
@property
def status_color(self):
    if self._theme_idx == _RAINBOW_IDX:
        return _hsv(self._rainbow_hue, 0.7, 0.65)
    c = _THEMES[self._theme_idx]["bright"][0]
    return Color(max(0, c.r // 2), max(0, c.g // 2), max(0, c.b // 2))
```

---

## Burst Mode Pattern

Copy this boilerplate for burst support:

```python
# In __init__:
self._burst_plane:  Optional[Plane] = None
self._bursts:       list[_Burst]    = []
self._burst_mode   = False
self._burst_size_i = 2          # index into _BURST_SIZES, default arm=7
self._burst_t      = 0

# In init() / on_resize():
self._burst_plane = Plane(h, w, z=3)   # highest z

# In update():
if self._burst_mode:
    self._burst_plane.clear()
    self._burst_t += 1
    interval = max(8, int(self.imap(90, 10)))
    max_live  = max(2, int(self.imap(2, 10)))
    if self._burst_t >= interval and len(self._bursts) < max_live:
        self._burst_t = 0
        arm    = _BURST_SIZES[self._burst_size_i]
        margin = arm * 2 + 2
        cy = random.randint(1, max(1, h - 3))
        cx = random.randint(margin, max(margin, w - margin - 1))
        self._bursts.append(_Burst(cy, cx, arm, pool))
    alive = []
    for burst in self._bursts:
        burst.update()
        if not burst.is_done():
            burst.render(self._burst_plane, self._gradient)
            alive.append(burst)
    self._bursts = alive

# In planes():
def planes(self):
    ps = [self._main_plane]
    if self._burst_mode:
        ps.append(self._burst_plane)
    return ps

# In on_key():
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
    self._burst_size_i = min(len(_BURST_SIZES) - 1, self._burst_size_i + 1)
    return True
```

---

## Plane Z-ordering Convention

| z | Purpose |
|---|---------|
| 0 | Background / ghost / residue plane |
| 1 | Main content plane |
| 2 | Foreground effects (splashes, sparks) |
| 3 | Burst plane (always on top) |

---

## imap — Intensity Mapping

```python
# Maps self.intensity (1–10) linearly to [lo, hi]
speed = self.imap(0.5, 3.0)   # slow at intensity 1, fast at intensity 10
count = self.imap(5, 50)      # few at low intensity, many at high
```

intensity is set externally by main.py. Never modify it from a scene.

---

## Rules and Hard Constraints

1. **Never write to row `h-1`**. That row belongs to the status bar renderer.
2. **Never intercept global keys** (`q`, Esc, arrow keys, Space, Tab). Return `False` from `on_key` for those.
3. **`update()` must clear planes at the start** (or selectively clear changed regions). Stale cell data causes visual artifacts.
4. **`init()` must be idempotent** — it may be called multiple times if the user switches scenes and back.
5. **`on_resize()` must rebuild all planes** with the new h/w. The old planes are the wrong size.
6. **No external dependencies**. Only stdlib + the project's own modules (`renderer`, `scene_base`, `effects`).
7. **Status extras must start with two spaces** to pad against the fixed prefix.
8. **Character mutation** for animated text: use per-cell timer counts (int), decrement each frame, refresh char when it hits 0. Do not pick random chars every frame (causes visual noise).
9. **Aspect ratio**: terminal cells are approximately 2:1 (height:width). For circular or directional effects, multiply horizontal distances by 0.5 (or double vertical distances) to compensate.
10. **Ghost / residue plane**: for scenes that leave fading trail on a persistent plane, decay it periodically by randomly removing a fraction of cells (not clearing the whole plane). Typical decay: remove `len(cells) // 8` random cells every `imap(200, 50)` frames.

---

## Registration Checklist

After writing `scenes/myscene.py`:

**`scenes/__init__.py`** — add:
```python
from .myscene import MyScene
__all__ = [..., "MyScene"]
```

**`main.py`** — add to import and list:
```python
from scenes import ..., MyScene
SCENE_CLASSES = [..., MyScene]
```

**Smoke test** before handing back:
```python
python3 -c "
from scenes import MyScene
s = MyScene()
print(s.name, s.status_extras, s.status_color)
s.init(None, 24, 80)
s.update(24, 80)
s.update(24, 80)
print('planes:', [p.z for p in s.planes()])
print('cells:', sum(len(p._cells) for p in s.planes()))
print('OK')
"
```

---

## Minimal Scene Template

```python
"""My Scene — one-line description.

Scene-specific controls:
  o / p        cycle colour theme
  [ / ]        <what this does>
  - / =        density / speed
  g            toggle <mode>
  x            toggle burst mode
  { / }        burst size
"""

from __future__ import annotations

import random
from typing import Optional

from renderer import Plane, Color, BLACK, WHITE
from scene_base import Scene
from effects import (
    _hsv, _build_gradient, _hue_gradient,
    _THEMES, _RAINBOW_IDX, _RAINBOW_SPEED,
    _BURST_SIZES, _Burst,
)


class MyScene(Scene):
    name = "My Scene"

    def __init__(self):
        self._plane:       Optional[Plane] = None
        self._burst_plane: Optional[Plane] = None
        self._bursts:      list[_Burst]    = []
        self._h = self._w = 0
        self._t        = 0
        self._burst_t  = 0

        # Controls
        self._theme_idx   = 0
        self._rainbow_hue = 0.0
        self._burst_mode  = False
        self._burst_size_i = 2

        # Derived
        self._gradient: list[Color] = []
        self._apply_theme_values()

    def _apply_theme_values(self) -> None:
        if self._theme_idx == _RAINBOW_IDX:
            self._gradient = _hue_gradient(self._rainbow_hue)
        else:
            self._gradient = _build_gradient(_THEMES[self._theme_idx])

    def on_key(self, key: int) -> bool:
        if key == ord('p'):
            self._theme_idx = (self._theme_idx + 1) % (_RAINBOW_IDX + 1)
            self._apply_theme_values()
            return True
        if key == ord('o'):
            self._theme_idx = (self._theme_idx - 1) % (_RAINBOW_IDX + 1)
            self._apply_theme_values()
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
        return False

    @property
    def status_extras(self) -> str:
        theme = ("RAINBOW" if self._theme_idx == _RAINBOW_IDX
                 else _THEMES[self._theme_idx]["name"])
        arm   = _BURST_SIZES[self._burst_size_i]
        burst = f"  x BURST:ON({arm})" if self._burst_mode else "  x BURST"
        return f"  o/p {theme}{burst}"

    @property
    def status_color(self) -> Color:
        if self._theme_idx == _RAINBOW_IDX:
            return _hsv(self._rainbow_hue, 0.7, 0.65)
        c = _THEMES[self._theme_idx]["bright"][0]
        return Color(max(0, c.r // 2), max(0, c.g // 2), max(0, c.b // 2))

    def init(self, renderer, h: int, w: int) -> None:
        self._h, self._w = h, w
        self._t = self._burst_t = 0
        self._bursts.clear()
        self._plane       = Plane(h, w, z=0)
        self._burst_plane = Plane(h, w, z=1)

    def on_resize(self, h: int, w: int) -> None:
        self._h, self._w = h, w
        self._plane       = Plane(h, w, z=0)
        self._burst_plane = Plane(h, w, z=1)

    def cleanup(self) -> None:
        self._bursts.clear()

    def update(self, h: int, w: int) -> None:
        self._h, self._w = h, w
        self._t += 1

        if self._theme_idx == _RAINBOW_IDX:
            self._rainbow_hue = (self._rainbow_hue + _RAINBOW_SPEED) % 1.0
            self._apply_theme_values()

        self._plane.clear()

        # ── YOUR RENDERING LOGIC HERE ──────────────────────────────────────
        grad = self._gradient
        for row in range(h - 1):              # never touch row h-1
            for col in range(w):
                char    = "·"
                grad_i  = (row + col + self._t) % len(grad)
                self._plane.put_char(row, col, char, fg=grad[grad_i], bg=BLACK)
        # ──────────────────────────────────────────────────────────────────

        # Burst mode (copy verbatim)
        if self._burst_mode:
            self._burst_plane.clear()
            self._burst_t += 1
            interval = max(8, int(self.imap(90, 10)))
            max_live  = max(2, int(self.imap(2, 10)))
            if self._burst_t >= interval and len(self._bursts) < max_live:
                self._burst_t = 0
                arm    = _BURST_SIZES[self._burst_size_i]
                margin = arm * 2 + 2
                cy = random.randint(1, max(1, h - 3))
                cx = random.randint(margin, max(margin, w - margin - 1))
                self._bursts.append(_Burst(cy, cx, arm, list("·•○◦")))
            alive = []
            for burst in self._bursts:
                burst.update()
                if not burst.is_done():
                    burst.render(self._burst_plane, grad)
                    alive.append(burst)
            self._bursts = alive

    def planes(self) -> list[Plane]:
        ps = [self._plane]
        if self._burst_mode:
            ps.append(self._burst_plane)
        return ps
```

---

## Existing Scenes — Quick Reference

| File | Class | Style | Planes | Notable |
|------|-------|-------|--------|---------|
| `scenes/matrix.py` | `MatrixRain` | Falling columns | ghost z=0, cols z=1, burst z=2 | Ghost residue, shear/tilt, grid mode |
| `scenes/rain.py` | `RainDrops` | Falling drops + splashes | ghost z=0, drops z=1, splash z=2, burst z=3 | Splash animation, puddle deposits |
| `scenes/plasma.py` | `Plasma` | Full-screen field | plasma z=0, burst z=1 | Per-cell mutation timers, sine field |
| `scenes/topo.py` | `TopoFlyover` | Scrolling terrain map | topo z=0, burst z=1 | Directional waves, domain warp, contour mode |

---

## Running the Application

```bash
cd /home/ph0tik/Documents/projects/ghosts2
python3 main.py
```

No external dependencies. Requires Python 3.10+ and a 256-colour terminal.

Global controls: `↑`/`↓` intensity, `←`/`→` or `Space` switch scenes, `q` quit.
