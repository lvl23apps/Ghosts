"""Slideshow — crossfades through images rendered as Braille block art.

Image source directories (checked in order):
  $GHOSTS_SLIDES env var
  ~/.config/ghosts/slides/
  ~/Pictures/randoms/
  ~/Pictures/
  <app>/slides/

Requires Pillow for image loading (pip install Pillow / apt install python3-pil).
Falls back to .txt Braille art files if Pillow is unavailable.

Color modes (c):
  ORIGINAL     actual colours sampled from the photo per Braille cell
  NEGATIVE     inverted RGB
  PSYCHEDELIC  hue rotates with time and position, saturation boosted
  VINTAGE      sepia tone via luminance matrix
  SVGA         quantised to 216-colour web-safe cube (6×6×6)
  VGA          quantised to 16-colour CGA/VGA palette

Controls:
  n / b        next / prev image
  c            cycle colour mode
  [ / ]        slide hold time (shorter / longer)
"""

from __future__ import annotations

import math
import os
import random
from typing import Optional

from renderer import Plane, Color, BLACK, WHITE
from scene_base import Scene


# ── Colour mode constants ─────────────────────────────────────────────────────

_CM_ORIGINAL    = 0
_CM_NEGATIVE    = 1
_CM_PSYCHEDELIC = 2
_CM_VINTAGE     = 3
_CM_SVGA        = 4
_CM_VGA         = 5
_CM_NAMES = ["ORIGINAL", "NEGATIVE", "PSYCHEDELIC", "VINTAGE", "SVGA", "VGA"]

# Classic 16-colour CGA/VGA palette
_VGA_COLOURS: list[Color] = [
    Color(  0,   0,   0), Color(  0,   0, 170), Color(  0, 170,   0),
    Color(  0, 170, 170), Color(170,   0,   0), Color(170,   0, 170),
    Color(170,  85,   0), Color(170, 170, 170), Color( 85,  85,  85),
    Color( 85,  85, 255), Color( 85, 255,  85), Color( 85, 255, 255),
    Color(255,  85,  85), Color(255,  85, 255), Color(255, 255,  85),
    Color(255, 255, 255),
]

# Web-safe 6×6×6 cube channel values for SVGA quantisation
_SVGA_STEPS = (0, 51, 102, 153, 204, 255)

# Braille dot layout for a 2-wide × 4-tall pixel block:
# col-offset, row-offset → Unicode bit position
_DOTS = (
    (0, 0, 0), (0, 1, 1), (0, 2, 2), (0, 3, 6),
    (1, 0, 3), (1, 1, 4), (1, 2, 5), (1, 3, 7),
)

_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".webp"}


# ── Colour helpers ────────────────────────────────────────────────────────────

def _nearest_vga(c: Color) -> Color:
    best, best_d = _VGA_COLOURS[0], float("inf")
    for vc in _VGA_COLOURS:
        d = (c.r - vc.r) ** 2 + (c.g - vc.g) ** 2 + (c.b - vc.b) ** 2
        if d < best_d:
            best_d, best = d, vc
    return best


def _nearest_svga(c: Color) -> Color:
    def snap(v: int) -> int:
        return min(_SVGA_STEPS, key=lambda s: abs(s - v))
    return Color(snap(c.r), snap(c.g), snap(c.b))


def _rgb_to_hsv(r: int, g: int, b: int) -> tuple[float, float, float]:
    r, g, b = r / 255.0, g / 255.0, b / 255.0
    mx, mn = max(r, g, b), min(r, g, b)
    diff = mx - mn
    v = mx
    s = 0.0 if mx == 0 else diff / mx
    if diff == 0:
        h = 0.0
    elif mx == r:
        h = ((g - b) / diff) % 6.0 / 6.0
    elif mx == g:
        h = ((b - r) / diff + 2.0) / 6.0
    else:
        h = ((r - g) / diff + 4.0) / 6.0
    return h, s, v


def _hsv_to_color(h: float, s: float, v: float) -> Color:
    h6 = (h % 1.0) * 6.0
    i  = int(h6)
    f  = h6 - i
    p, q, t = v * (1 - s), v * (1 - s * f), v * (1 - s * (1 - f))
    if   i == 0: r, g, b = v, t, p
    elif i == 1: r, g, b = q, v, p
    elif i == 2: r, g, b = p, v, t
    elif i == 3: r, g, b = p, q, v
    elif i == 4: r, g, b = t, p, v
    else:        r, g, b = v, p, q
    return Color(int(r * 255), int(g * 255), int(b * 255))


def _vintage(c: Color) -> Color:
    """Sepia tone transform."""
    r = min(255, int(c.r * 0.393 + c.g * 0.769 + c.b * 0.189))
    g = min(255, int(c.r * 0.349 + c.g * 0.686 + c.b * 0.168))
    b = min(255, int(c.r * 0.272 + c.g * 0.534 + c.b * 0.131))
    return Color(r, g, b)


# ── Image discovery ───────────────────────────────────────────────────────────

def _image_dirs() -> list[str]:
    dirs = []
    env = os.environ.get("GHOSTS_SLIDES")
    if env:
        dirs.append(env)
    dirs.append(os.path.expanduser("~/.config/ghosts/slides"))
    dirs.append(os.path.expanduser("~/Pictures/randoms"))
    dirs.append(os.path.expanduser("~/Pictures"))
    here = os.path.dirname(os.path.abspath(__file__))
    dirs.append(os.path.join(os.path.dirname(here), "slides"))
    return dirs


def _find_images() -> list[str]:
    seen: set[str] = set()
    paths: list[str] = []
    for d in _image_dirs():
        if not os.path.isdir(d):
            continue
        for fn in sorted(os.listdir(d)):
            if os.path.splitext(fn)[1].lower() in _IMAGE_EXTS:
                fp = os.path.join(d, fn)
                if fp not in seen:
                    seen.add(fp)
                    paths.append(fp)
    return paths


def _find_txt_slides() -> list[str]:
    paths: list[str] = []
    for d in _image_dirs():
        if os.path.isdir(d):
            for fn in sorted(os.listdir(d)):
                if fn.endswith(".txt"):
                    paths.append(os.path.join(d, fn))
    return paths


# ── Slide conversion ──────────────────────────────────────────────────────────

# Type: slide = list[list[tuple[str, Color]]]   (rows × cols → (char, colour))

def _image_to_slide(path: str, h: int, w: int):
    """Convert image to Braille art slide at terminal dimensions.

    Each terminal cell covers a 2×4 pixel block.  Bright pixels light dots;
    the average RGB of all 8 pixels in the block becomes the cell colour.
    Returns None on failure.
    """
    try:
        from PIL import Image as _Image
        img = _Image.open(path)

        src_w, src_h = img.size
        tgt_w, tgt_h = w * 2, (h - 1) * 4

        # For JPEGs, use draft() to decode at reduced resolution in the JPEG
        # decoder itself — 4–8× faster than decoding then downsampling.
        if hasattr(img, "draft"):
            img.draft("RGB", (tgt_w * 2, tgt_h * 2))
            src_w, src_h = img.size

        img = img.convert("RGB")

        scale = min(tgt_w / src_w, tgt_h / src_h)
        fit_w = max(1, int(src_w * scale))
        fit_h = max(1, int(src_h * scale))
        img   = img.resize((fit_w, fit_h), _Image.BILINEAR)

        # Pad to target with black
        canvas = _Image.new("RGB", (tgt_w, tgt_h), (0, 0, 0))
        off_x  = (tgt_w - fit_w) // 2
        off_y  = (tgt_h - fit_h) // 2
        canvas.paste(img, (off_x, off_y))
        pixels = canvas.load()

        slide = []
        for row in range(h - 1):
            cells = []
            for col in range(w):
                px, py = col * 2, row * 4
                bits = 0
                rs = gs = bs = 0
                for dx, dy, bit in _DOTS:
                    x, y = px + dx, py + dy
                    r, g, b = pixels[x, y]
                    luma = 0.299 * r + 0.587 * g + 0.114 * b
                    if luma >= 90:       # bright pixel → dot lit
                        bits |= (1 << bit)
                    rs += r; gs += g; bs += b
                char  = chr(0x2800 + bits)
                color = Color(rs // 8, gs // 8, bs // 8)
                cells.append((char, color))
            slide.append(cells)
        return slide
    except Exception:
        return None


def _txt_to_slide(path: str, h: int, w: int):
    """Load a pre-converted .txt Braille art file, scaled to terminal size."""
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
        if not lines:
            return None
        src_h = len(lines)
        src_w = max(len(ln) for ln in lines)
        slide = []
        for row in range(h - 1):
            sy   = int(row * src_h / max(1, h - 1))
            line = list(lines[min(sy, src_h - 1)])
            cells = []
            for col in range(w):
                sx = int(col * src_w / max(1, w))
                ch = line[sx] if sx < len(line) else " "
                # Generate a soft gradient colour — overridden by colour mode
                t  = col / max(1, w - 1)
                v  = int(100 + 80 * abs(math.sin(row * 0.07 + t * math.pi)))
                cells.append((ch, Color(v, v, v)))
            slide.append(cells)
        return slide
    except Exception:
        return None


# ── Scene ─────────────────────────────────────────────────────────────────────

_GLITCH_POOL = "░▒▓▄▀▌▐│─┼╬◆○●□■×÷±≈∞§@#$%&!?~^"

def _glitch_name(name: str, frame: int) -> str:
    """Return a partially corrupted version of name, flickering with frame."""
    rng = random.Random(frame // 4)   # changes every 4 frames
    out = []
    for ch in name:
        r = rng.random()
        if ch in (".", "/", "_", "-"):
            out.append(ch)            # punctuation always legible
        elif r < 0.40:
            out.append(rng.choice(_GLITCH_POOL))   # corrupted
        elif r < 0.55:
            out.append(ch.swapcase())              # case-flipped
        else:
            out.append(ch)                         # legible
    return "".join(out)


_HOLD_DEFAULT  = 300   # frames before starting next crossfade (~10 s at 30fps)
_FADE_FRAMES   = 90    # crossfade duration in frames (~3 s)
_HOLD_STEP     = 60    # hold time adjustment per keypress


class Slideshow(Scene):
    name = "Slideshow"

    def init(self, renderer, h: int, w: int) -> None:
        self._h, self._w = h, w
        self._frame = 0

        self._color_mode  = _CM_ORIGINAL
        self._hold_frames = _HOLD_DEFAULT

        # Discover sources
        self._img_paths  = _find_images()
        self._txt_paths  = _find_txt_slides()
        self._all_paths  = self._img_paths + self._txt_paths
        if not self._all_paths:
            self._all_paths = ["__empty__"]

        self._idx  = 0
        self._cache: dict[tuple, list] = {}   # (path, h, w) → slide

        # Slide state
        self._cur_slide: Optional[list] = None
        self._nxt_slide: Optional[list] = None
        self._hold_t  = 0        # frames spent displaying current slide
        self._fade_t  = 0        # frames into crossfade (0 = not fading)
        self._fading  = False

        self._plane = Plane(h, w, z=0)
        self._load_current()

    def _load_slide(self, path: str) -> Optional[list]:
        key = (path, self._h, self._w)
        if key in self._cache:
            return self._cache[key]
        if path == "__empty__":
            slide = self._empty_slide()
        elif path.endswith(".txt"):
            slide = _txt_to_slide(path, self._h, self._w)
        else:
            slide = _image_to_slide(path, self._h, self._w)
            if slide is None:
                slide = _txt_to_slide(path, self._h, self._w)
        if slide is None:
            slide = self._empty_slide()
        self._cache[key] = slide
        return slide

    def _empty_slide(self) -> list:
        msg = "  no slides found — set GHOSTS_SLIDES or add images to ~/Pictures/randoms/  "
        mid = (self._h - 1) // 2
        slide = []
        for r in range(self._h - 1):
            cells = []
            for c in range(self._w):
                if r == mid and c < len(msg):
                    cells.append((msg[c], Color(180, 180, 180)))
                else:
                    cells.append((" ", BLACK))
            slide.append(cells)
        return slide

    def _load_current(self) -> None:
        self._cur_slide = self._load_slide(self._all_paths[self._idx])
        self._hold_t    = 0
        self._fading    = False
        self._fade_t    = 0

    def _start_fade(self, direction: int) -> None:
        n = (self._idx + direction) % len(self._all_paths)
        self._nxt_slide = self._load_slide(self._all_paths[n])
        self._fading    = True
        self._fade_t    = 0
        self._next_idx  = n

    def _finish_fade(self) -> None:
        self._idx       = self._next_idx
        self._cur_slide = self._nxt_slide
        self._nxt_slide = None
        self._hold_t    = 0
        self._fading    = False
        self._fade_t    = 0

    def on_resize(self, h: int, w: int) -> None:
        self._h, self._w = h, w
        self._cache.clear()
        self._plane = Plane(h, w, z=0)
        self._load_current()

    def cleanup(self) -> None:
        pass

    # ── colour mode transform ─────────────────────────────────────────────────

    def _apply_mode(self, c: Color, row: int, col: int) -> Color:
        mode = self._color_mode

        if mode == _CM_NEGATIVE:
            return Color(255 - c.r, 255 - c.g, 255 - c.b)

        if mode == _CM_PSYCHEDELIC:
            h, s, v = _rgb_to_hsv(c.r, c.g, c.b)
            t = self._frame * 0.008
            h = (h + t + row * 0.004 + col * 0.002) % 1.0
            s = min(1.0, s * 1.4 + 0.45)
            v = max(0.35, v)
            return _hsv_to_color(h, s, v)

        if mode == _CM_VINTAGE:
            return _vintage(c)

        if mode == _CM_SVGA:
            return _nearest_svga(c)

        if mode == _CM_VGA:
            return _nearest_vga(c)

        return c   # ORIGINAL

    # ── key handling ──────────────────────────────────────────────────────────

    def on_key(self, key: int) -> bool:
        if key in (ord("n"), ord("N")):
            self._start_fade(+1); return True
        if key in (ord("b"), ord("B")):
            self._start_fade(-1); return True
        if key in (ord("c"), ord("C")):
            self._color_mode = (self._color_mode + 1) % len(_CM_NAMES)
            return True
        if key == ord("["):
            self._hold_frames = max(_HOLD_STEP, self._hold_frames - _HOLD_STEP)
            return True
        if key == ord("]"):
            self._hold_frames = min(1800, self._hold_frames + _HOLD_STEP)
            return True
        return False

    # ── update ────────────────────────────────────────────────────────────────

    def update(self, h: int, w: int) -> None:
        if h != self._h or w != self._w:
            self.on_resize(h, w)

        self._frame += 1

        if self._fading:
            self._fade_t += 1
            if self._fade_t >= _FADE_FRAMES:
                self._finish_fade()
        else:
            self._hold_t += 1
            # Pre-load next slide 60 frames before transition so any slow
            # image decode (large JPEGs) happens during the static hold phase.
            if self._hold_t == max(1, self._hold_frames - 60):
                nxt_idx = (self._idx + 1) % len(self._all_paths)
                self._load_slide(self._all_paths[nxt_idx])
            if self._hold_t >= self._hold_frames:
                self._start_fade(+1)

        self._render(h, w)

    # ── rendering ─────────────────────────────────────────────────────────────

    def _render(self, h: int, w: int) -> None:
        p = self._plane
        p.clear()

        cur = self._cur_slide
        nxt = self._nxt_slide if self._fading else None
        t   = (self._fade_t / _FADE_FRAMES) if self._fading else 0.0

        if cur is None:
            return

        for row, cells in enumerate(cur):
            if row >= h - 1:
                break
            for col, (char, color) in enumerate(cells):
                if col >= w:
                    break

                if nxt is not None and row < len(nxt) and col < len(nxt[row]):
                    nchar, ncolor = nxt[row][col]
                    # Blend: crossfade both char and colour
                    color = color.lerp(ncolor, t)
                    char  = nchar if t >= 0.5 else char

                # Skip empty Braille — no need to render invisible cells
                if char == "\u2800" and color.r < 12 and color.g < 12 and color.b < 12:
                    continue

                fg = self._apply_mode(color, row, col)

                # Minimum brightness so dark images still show structure
                if fg.r < 30 and fg.g < 30 and fg.b < 30:
                    fg = Color(30, 30, 30)

                p.put_char(row, col, char, fg=fg, bg=BLACK)

    def planes(self) -> list[Plane]:
        return [self._plane]

    @property
    def status_extras(self) -> str:
        if not self._all_paths or self._all_paths[0] == "__empty__":
            label = "no images"
        else:
            raw   = os.path.basename(self._all_paths[self._idx])
            if len(raw) > 28:
                raw = raw[-28:]
            label = _glitch_name(raw, self._frame)
        secs  = max(1, self._hold_frames // 30)
        phase = f"FADE {int(self._fade_t//_FADE_FRAMES*100)}%" if self._fading else f"hold {self._hold_t}/{self._hold_frames}"
        return (
            f"  c:{_CM_NAMES[self._color_mode]}"
            f"  [/]:{secs}s"
            f"  {phase}"
            f"  {self._idx+1}/{len(self._all_paths)} {label}"
            f"  n/b nav"
        )

    @property
    def status_color(self) -> Color:
        return Color(180, 140, 255)
