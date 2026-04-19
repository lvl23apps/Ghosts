"""Ghost — signature terminal drift scene.

Captures terminal content before ghosts2 starts, drifts it across the screen
with five visually distinct ghost-trail modes inspired by the notcurses plane
and fade model (ncplane_gradient, ncfadectx, ncplane_fadeout_iteration).

Ghost modes (m) — each is structurally and visually different:
  SIMPLE    ncfadectx-style: uniform fast linear fade, no glow, sharp edge
  PHOSPHOR  CRT P39 phosphor: multi-phase decay, heated bg glow, thermal flicker
  SMEAR     Motion blur: 12-cell block-char density trail (█▓▒░) in drift dir
  WAVE      Accumulate-and-erase: ghosts freeze at full intensity until the
            luminous scan bar sweeps through; dramatic fill → wipe cycle
  COMPLEX   Electrical discharge: chromatic aberration (±5 col red/blue),
            noise-char corruption, arc sparks, phosphor + smear layered

Frame FX (f):
  NONE / SCANLINE / CHROMATIC / NOISE / GRID

Controls:
  ↑ ↓ ← →    drift direction (also wasd)
  [ / ]       drift speed
  - / =       scatter  (1 col → full width at once)
  m           cycle ghost mode
  f           cycle frame FX
  o / p       prev / next colour palette
"""

from __future__ import annotations

import os
import random
import subprocess
import time
from typing import Optional

from renderer import Plane, Color, BLACK, WHITE, ALPHA_TRANSPARENT
from scene_base import Scene


# ── Pre-launch content capture ─────────────────────────────────────────────────

def _try_tmux() -> list[str]:
    if not os.environ.get("TMUX"):
        return []
    try:
        r = subprocess.run(
            ["tmux", "capture-pane", "-p", "-J"],
            capture_output=True, text=True, timeout=2,
        )
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.splitlines()
    except Exception:
        pass
    return []


def _fake_content() -> list[str]:
    import sys as _sys
    user = os.environ.get("USER", "user")
    try:
        host = os.uname().nodename
    except Exception:
        host = os.environ.get("HOSTNAME", "localhost")
    cwd  = os.getcwd()
    now  = time.strftime("%a %b %d %H:%M:%S %Z %Y")
    pver = _sys.version.split()[0]
    p    = f"{user}@{host}:{cwd}$ "
    lines: list[str] = []

    def cmd(c: str, *out: str) -> None:
        lines.append(p + c)
        lines.extend(out)
        lines.append("")

    lines.append(f"Last login: {now}")
    lines.append("")
    cmd("uname -a", f"Linux {host} 6.1.0-1 #1 SMP x86_64 GNU/Linux")
    cmd("date", now)
    cmd("uptime",
        f" {time.strftime('%H:%M:%S')} up 3 days  7:22,  2 users,"
        "  load average: 0.12, 0.08, 0.06")
    cmd("ls -la",
        "total 128",
        f"drwxr-xr-x  8 {user} {user}  4096 {time.strftime('%b %d %H:%M')} .",
        f"-rw-r--r--  1 {user} {user}  1337 {time.strftime('%b %d %H:%M')} main.py",
        f"-rw-r--r--  1 {user} {user}  8192 {time.strftime('%b %d %H:%M')} renderer.py",
        f"drwxr-xr-x  2 {user} {user}  4096 {time.strftime('%b %d %H:%M')} scenes",
        f"-rw-r--r--  1 {user} {user}  2048 {time.strftime('%b %d %H:%M')} scene_base.py",
    )
    cmd(f"python3 --version", f"Python {pver}")
    cmd("git log --oneline -8",
        "a1b2c3d add Ghost scene with terminal capture and trails",
        "b2c3d4e add Switchboard: Shadytel interactive exchange",
        "c3d4e5f add ComputerSim: 10 classic systems",
        "d4e5f6a add BioScan with fossil windows",
        "e5f6a7b add GlitchScreen modifiers DISSOLUTION CRITICAL_ERROR SYMBOL_STORM",
        "f6a7b8c add TopoFlyover terrain scanner",
        "a7b8c9d add Plasma bilinear gradient waves",
        "b8c9d0e initial commit: MatrixRain RainDrops",
    )
    cmd("git status",
        "On branch main",
        "Changes not staged for commit:",
        f"\tmodified:   scenes/ghost.py",
        "no changes added to commit",
    )
    cmd("ps aux | head -8",
        "USER       PID %CPU %MEM    VSZ   RSS TTY      STAT TIME COMMAND",
        f"root         1  0.0  0.0 167512  9216 ?        Ss   0:02 /sbin/init",
        f"{user}     1337  0.8  0.1 246880 18432 pts/0   Ss   0:00 -bash",
        f"{user}     1338  5.2  0.3 412160 49152 pts/0   S+   0:00 python3 main.py",
    )

    for hf in (os.path.expanduser("~/.bash_history"),
               os.path.expanduser("~/.zsh_history")):
        try:
            with open(hf) as fh:
                raw = [l.strip() for l in fh.readlines()[-40:]]
            for c in [l for l in raw if l and not l.startswith(":")][-12:]:
                lines.append(p + c)
            break
        except Exception:
            pass

    lines.append(p + "python3 main.py")
    return lines


_PRE_LAUNCH: list[str] = _try_tmux() or _fake_content()


# ── Colour palettes ───────────────────────────────────────────────────────────
# (name, peak_fg, mid_fg, dim_fg, glow_bg, content_fg)

_PALETTES: list[tuple] = [
    ("GREEN",  Color(  0,255,110), Color(  0,170, 65), Color(  0, 60, 22),
               Color(  0, 28,  8), Color(140,195,158)),
    ("AMBER",  Color(240,165,  0), Color(168,108,  0), Color( 72, 42,  0),
               Color( 34, 16,  0), Color(198,180,132)),
    ("BLUE",   Color( 80,165,255), Color( 38, 95,210), Color( 10, 28, 98),
               Color(  0, 10, 44), Color(128,162,218)),
    ("RED",    Color(255, 72, 52), Color(198, 30, 18), Color( 84,  5,  4),
               Color( 42,  0,  0), Color(208,148,142)),
    ("CYAN",   Color(  0,235,235), Color(  0,148,148), Color(  0, 52, 52),
               Color(  0, 20, 20), Color(128,198,198)),
    ("WHITE",  Color(248,248,252), Color(168,168,175), Color( 60, 60, 65),
               Color( 22, 22, 24), Color(180,180,184)),
    ("VIOLET", Color(208, 82,255), Color(128, 32,192), Color( 50,  0, 76),
               Color( 28,  0, 44), Color(170,142,210)),
    ("RAINBOW",Color(255,255,255), Color(180,180,180), Color( 60, 60, 60),
               Color( 14, 14, 14), Color(178,178,178)),
]


def _rainbow(r: int, c: int, t: float, v: float) -> Color:
    h6 = ((c * 0.013 + r * 0.007 + t) % 1.0) * 6.0
    i  = int(h6); f = h6 - i
    p  = 0.0; q = 1.0 - f; tv = f
    if   i == 0: rv,gv,bv = 1.0, tv,  p
    elif i == 1: rv,gv,bv = q,  1.0,  p
    elif i == 2: rv,gv,bv = p,  1.0, tv
    elif i == 3: rv,gv,bv = p,   q,  1.0
    elif i == 4: rv,gv,bv = tv,  p,  1.0
    else:        rv,gv,bv = 1.0,  p,   q
    s = max(0.0, min(1.0, v))
    return Color(int(rv*255*s), int(gv*255*s), int(bv*255*s))


# ── Mode / FX / direction constants ──────────────────────────────────────────

_GM_SIMPLE   = 0
_GM_PHOSPHOR = 1
_GM_SMEAR    = 2
_GM_WAVE     = 3
_GM_COMPLEX  = 4
_GM_NAMES    = ["SIMPLE", "PHOSPHOR", "SMEAR", "WAVE", "COMPLEX"]

_FX_NONE      = 0
_FX_SCANLINE  = 1
_FX_CHROMATIC = 2
_FX_NOISE     = 3
_FX_GRID      = 4
_FX_NAMES     = ["NONE", "SCANLINE", "CHROMATIC", "NOISE", "GRID"]

_DIR_UP    = 0
_DIR_DOWN  = 1
_DIR_LEFT  = 2
_DIR_RIGHT = 3
_DIR_NAMES = ["↑ UP", "↓ DOWN", "← LEFT", "→ RIGHT"]

# Smear block chars: density from full to sparse
_SMEAR_CHARS = "█▓▒░"
_NOISE_CHARS  = list("▓▒░█▄▀▌▐│─┼╬◆◇○●□■×÷±≈∞§")


# ── Scene ─────────────────────────────────────────────────────────────────────

class Ghost(Scene):
    name = "Ghost"

    def init(self, renderer, h: int, w: int) -> None:
        self._h, self._w = h, w
        src = list(_PRE_LAUNCH) if _PRE_LAUNCH else [""]
        self._source: list[str] = src or [""]
        self._src_ptr = 0

        self._canvas: list[list[str]] = []
        self._reset_canvas(h, w)

        # Ghost trail: (r,c) → [char, intensity]
        self._ghosts: dict[tuple, list] = {}

        # Wave state — used by WAVE and COMPLEX
        self._wave_pos:  float = -1.0
        self._wave_t:    int   = 0
        self._wave_int:  int   = random.randint(40, 70)

        self._frame: int = 0

        # Scroll
        self._dir     = _DIR_UP
        self._speed   = 0.15
        self._acc     = 0.0
        self._scatter = w

        self._col_done:  list[int] = [0] * w
        self._row_done:  list[int] = [0] * h
        self._src_round: int = 0

        # Modes
        self._ghost_mode  = _GM_PHOSPHOR
        self._fx_mode     = _FX_NONE
        self._palette_idx = 0

        # Planes
        self._bg_plane   : Optional[Plane] = None
        self._ghost_plane: Optional[Plane] = None
        self._live_plane : Optional[Plane] = None
        self._wave_plane : Optional[Plane] = None   # z=3 — WAVE sweep bar
        self._build_planes(h, w)

    def _reset_canvas(self, h: int, w: int) -> None:
        self._canvas = []
        for r in range(h):
            ln = self._source[r % len(self._source)]
            self._canvas.append(list(ln[:w].ljust(w)))

    def _build_planes(self, h: int, w: int) -> None:
        self._bg_plane    = Plane(h, w, z=-1)
        self._ghost_plane = Plane(h, w, z=0)
        self._live_plane  = Plane(h, w, z=1)
        self._wave_plane  = Plane(h, w, z=3)

    def on_resize(self, h: int, w: int) -> None:
        self._h, self._w = h, w
        self._reset_canvas(h, w)
        self._ghosts.clear()
        self._col_done  = [0] * w
        self._row_done  = [0] * h
        self._src_round = 0
        self._scatter   = min(self._scatter, w)
        self._build_planes(h, w)

    def cleanup(self) -> None:
        pass

    # ── palette helpers ───────────────────────────────────────────────────────

    def _pal(self) -> tuple:
        return _PALETTES[self._palette_idx]

    def _peak(self) -> Color:
        p = self._pal()
        return p[1]

    def _mid(self)  -> Color:  return self._pal()[2]
    def _dim(self)  -> Color:  return self._pal()[3]
    def _glow(self) -> Color:  return self._pal()[4]
    def _cont(self) -> Color:  return self._pal()[5]

    def _pal_fg(self, r: int, c: int, intensity: float) -> Color:
        """Compute fg colour for a ghost at (r,c) at given intensity."""
        name = self._pal()[0]
        if name == "RAINBOW":
            return _rainbow(r, c, self._frame * 0.003, intensity)
        mode = self._ghost_mode

        if mode == _GM_SIMPLE:
            # Straight linear fade: peak colour → black
            return self._peak().lerp(BLACK, 1.0 - intensity)

        if mode in (_GM_PHOSPHOR, _GM_COMPLEX):
            # Three-phase CRT phosphor curve
            if intensity > 0.68:
                t = (intensity - 0.68) / 0.32
                return WHITE.lerp(self._peak(), 1.0 - t * 0.55)
            elif intensity > 0.30:
                t = (intensity - 0.30) / 0.38
                return self._peak().lerp(self._mid(), 1.0 - t)
            else:
                t = intensity / 0.30
                return self._mid().lerp(self._dim(), 1.0 - t * 0.7).lerp(BLACK, 1.0 - t)

        if mode == _GM_SMEAR:
            # Stays saturated at peak colour throughout — density shown via char
            return self._peak().lerp(self._dim(), 1.0 - intensity)

        if mode == _GM_WAVE:
            # Flat full colour — no gradient; ghosts don't decay so intensity is ~1.0
            return self._peak()

        return self._peak().lerp(BLACK, 1.0 - intensity)

    def _pal_bg(self, r: int, c: int, intensity: float) -> Color:
        """Per-cell background glow (PHOSPHOR/COMPLEX only)."""
        if self._ghost_mode not in (_GM_PHOSPHOR, _GM_COMPLEX):
            return BLACK
        if intensity < 0.30:
            return BLACK
        name = self._pal()[0]
        # Use _mid() as the glow colour — much more visible than _glow()
        if name == "RAINBOW":
            base = _rainbow(r, c, self._frame * 0.003, 0.22)
        else:
            base = self._mid()
        # Scale: at intensity=0.30 → subtle; at intensity=1.0 → half-bright mid
        t = (intensity - 0.30) / 0.70
        return base.lerp(BLACK, 1.0 - t * 0.55)

    def _smear_char(self, intensity: float, original: str) -> str:
        """Return block character representing ghost density for SMEAR mode."""
        if intensity > 0.83:  return "█"
        if intensity > 0.63:  return "▓"
        if intensity > 0.43:  return "▒"
        if intensity > 0.23:  return "░"
        return original

    # ── scroll mechanics ──────────────────────────────────────────────────────

    def _src_char(self, row_idx: int, col: int) -> str:
        if not self._source:
            return " "
        ln = self._source[row_idx % len(self._source)]
        return ln[col] if col < len(ln) else " "

    def _add_ghost(self, r: int, c: int, char: str) -> None:
        """Add a ghost at (r,c). For SMEAR/COMPLEX: immediately trail behind."""
        if char == " ":
            return
        self._ghosts[(r, c)] = [char, 1.0]

        # Directional smear trail — 12-cell density wake opposite to drift
        if self._ghost_mode in (_GM_SMEAR, _GM_COMPLEX):
            dr, dc = {
                _DIR_UP:    ( 1,  0),
                _DIR_DOWN:  (-1,  0),
                _DIR_LEFT:  ( 0,  1),
                _DIR_RIGHT: ( 0, -1),
            }[self._dir]
            trail = (
                (1, 0.96), (2, 0.90), (3, 0.82), (4, 0.72),
                (5, 0.60), (6, 0.48), (7, 0.36), (8, 0.24),
                (9, 0.15), (10, 0.09), (11, 0.05), (12, 0.02),
            )
            for step, frac in trail:
                nr, nc = r + dr * step, c + dc * step
                if 0 <= nr < self._h and 0 <= nc < self._w:
                    existing = self._ghosts.get((nr, nc))
                    if existing is None or existing[1] < frac:
                        self._ghosts[(nr, nc)] = [char, frac]

    def _shift_up(self, cols: list[int]) -> None:
        h = self._h
        for c in cols:
            self._add_ghost(0, c, self._canvas[0][c])
            for r in range(h - 1):
                self._canvas[r][c] = self._canvas[r+1][c]
            self._canvas[h-1][c] = self._src_char(h - 1 + self._col_done[c], c)
            self._col_done[c] += 1
        self._advance_src(self._col_done, self._w)

    def _shift_down(self, cols: list[int]) -> None:
        h = self._h
        for c in cols:
            self._add_ghost(h-1, c, self._canvas[h-1][c])
            for r in range(h-1, 0, -1):
                self._canvas[r][c] = self._canvas[r-1][c]
            self._canvas[0][c] = self._src_char(-(self._col_done[c]+1), c)
            self._col_done[c] += 1
        self._advance_src(self._col_done, self._w)

    def _shift_left(self, rows: list[int]) -> None:
        w = self._w
        for r in rows:
            self._add_ghost(r, 0, self._canvas[r][0])
            self._canvas[r] = self._canvas[r][1:] + [" "]
            ln = self._source[(r + self._row_done[r]) % len(self._source)]
            ci = (w - 1 + self._row_done[r]) % max(1, len(ln)) if ln else 0
            self._canvas[r][w-1] = ln[ci] if ln and ci < len(ln) else " "
            self._row_done[r] += 1
        self._advance_src(self._row_done, self._h)

    def _shift_right(self, rows: list[int]) -> None:
        w = self._w
        for r in rows:
            self._add_ghost(r, w-1, self._canvas[r][w-1])
            self._canvas[r] = [" "] + self._canvas[r][:-1]
            ln = self._source[r % len(self._source)]
            ci = (-(self._row_done[r]+1)) % max(1, len(ln)) if ln else 0
            self._canvas[r][0] = ln[ci] if ln and ci < len(ln) else " "
            self._row_done[r] += 1
        self._advance_src(self._row_done, self._h)

    def _advance_src(self, done: list[int], total: int) -> None:
        mn = min(done) if done else 0
        if mn > self._src_round:
            self._src_round = mn
            self._src_ptr = (self._src_ptr + 1) % max(1, len(self._source))

    def _pick_cols(self) -> list[int]:
        n = min(self._scatter, self._w)
        return list(range(self._w)) if n >= self._w else random.sample(range(self._w), n)

    def _pick_rows(self) -> list[int]:
        n = min(self._scatter, self._h)
        return list(range(self._h)) if n >= self._h else random.sample(range(self._h), n)

    def _do_step(self) -> None:
        if   self._dir == _DIR_UP:    self._shift_up(self._pick_cols())
        elif self._dir == _DIR_DOWN:  self._shift_down(self._pick_cols())
        elif self._dir == _DIR_LEFT:  self._shift_left(self._pick_rows())
        else:                          self._shift_right(self._pick_rows())

    # ── ghost decay — each mode is structurally distinct ─────────────────────

    def _decay_ghosts(self) -> None:
        mode = self._ghost_mode
        h, w = self._h, self._w
        dead = []

        for (r, c), ghost in self._ghosts.items():
            char, intensity = ghost

            if mode == _GM_SIMPLE:
                # ncfadectx-style: uniform, fast, sharp — ~6 frames to gone
                intensity *= 0.80

            elif mode == _GM_PHOSPHOR:
                # CRT P39: three phases with very different time constants
                # Phase 1 (>0.65): phosphor fully energised — extremely slow (~165 frames)
                # Phase 2 (0.25-0.65): colour shifts as phosphor cools (~21 frames)
                # Phase 3 (<0.25): exponential dark drop
                if intensity > 0.65:
                    intensity -= 0.002 + random.uniform(0.0, 0.001)
                elif intensity > 0.25:
                    intensity -= 0.019
                else:
                    intensity *= 0.74

            elif mode == _GM_SMEAR:
                # Slower per-cell decay so the 12-cell trail stays dense
                intensity *= 0.91

            elif mode == _GM_WAVE:
                # NO decay between sweeps — ghosts are frozen at full intensity
                # Only the wave sweep erases them
                pass  # intensity unchanged

            elif mode == _GM_COMPLEX:
                # Phosphor-rate base decay
                if intensity > 0.65:
                    intensity -= 0.002 + random.uniform(0.0, 0.001)
                elif intensity > 0.25:
                    intensity -= 0.019
                else:
                    intensity *= 0.74
                # Corruption: randomly replace char with noise at medium intensity
                if 0.25 < intensity < 0.75 and random.random() < 0.04:
                    ghost[0] = random.choice(_NOISE_CHARS)

            if mode != _GM_WAVE and intensity < 0.016:
                dead.append((r, c))
                continue
            elif mode == _GM_WAVE and intensity <= 0.0:
                dead.append((r, c))
                continue
            ghost[1] = intensity

        for k in dead:
            del self._ghosts[k]

        # ── PHOSPHOR: thermal flicker — bright cells spike toward white ──────
        if mode == _GM_PHOSPHOR and self._ghosts:
            bright = [(k, g) for k, g in self._ghosts.items() if g[1] > 0.65]
            if bright and random.random() < 0.25:
                # Affect 1-3 cells per frame
                for _ in range(random.randint(1, 3)):
                    k, g = random.choice(bright)
                    g[1] = min(1.0, g[1] + random.uniform(0.10, 0.30))

        # ── COMPLEX: arc sparks — neighbours discharge ───────────────────────
        if mode == _GM_COMPLEX and self._ghosts:
            # Higher spark rate: 18% per frame, up to 4 sparks
            if random.random() < 0.18:
                keys = list(self._ghosts)
                for _ in range(random.randint(1, 4)):
                    src_k = random.choice(keys)
                    r0, c0 = src_k
                    # Arcs jump further than neighbours — up to 3 cells away
                    sr = r0 + random.randint(-3, 3)
                    sc = c0 + random.randint(-3, 3)
                    if 0 <= sr < h and 0 <= sc < w and (sr, sc) not in self._ghosts:
                        self._ghosts[(sr, sc)] = [
                            random.choice(_NOISE_CHARS),
                            random.uniform(0.55, 1.0)
                        ]

        # ── WAVE / COMPLEX: scanning sweep ───────────────────────────────────
        if mode in (_GM_WAVE, _GM_COMPLEX):
            self._wave_t += 1
            if self._wave_t >= self._wave_int:
                self._wave_t   = 0
                self._wave_int = random.randint(40, 70)
                self._wave_pos = 0.0

            if 0.0 <= self._wave_pos >= 0:
                axis = w if self._dir in (_DIR_UP, _DIR_DOWN) else h
                if self._wave_pos < axis:
                    advance = 5.0
                    old = int(self._wave_pos)
                    self._wave_pos += advance
                    new = int(self._wave_pos)

                    # Erase ghosts behind the sweep front
                    for pos in range(old, min(new, axis)):
                        if self._dir in (_DIR_UP, _DIR_DOWN):
                            for rr in range(h):
                                self._ghosts.pop((rr, pos), None)
                        else:
                            for cc in range(w):
                                self._ghosts.pop((pos, cc), None)
                else:
                    self._wave_pos = -1.0

    # ── key handling ──────────────────────────────────────────────────────────

    def on_key(self, key: int) -> bool:
        import curses

        if key in (curses.KEY_UP,    ord("w"), ord("W")):
            self._dir = _DIR_UP;    return True
        if key in (curses.KEY_DOWN,  ord("s"), ord("S")):
            self._dir = _DIR_DOWN;  return True
        if key in (curses.KEY_LEFT,  ord("a"), ord("A")):
            self._dir = _DIR_LEFT;  return True
        if key in (curses.KEY_RIGHT, ord("d"), ord("D")):
            self._dir = _DIR_RIGHT; return True

        if key == ord("["):
            self._speed = max(0.02, self._speed - 0.03);  return True
        if key == ord("]"):
            self._speed = min(2.0,  self._speed + 0.03);  return True

        if key == ord("-"):
            md = self._w if self._dir in (_DIR_UP, _DIR_DOWN) else self._h
            self._scatter = max(1, self._scatter - max(1, md // 16)); return True
        if key == ord("="):
            md = self._w if self._dir in (_DIR_UP, _DIR_DOWN) else self._h
            self._scatter = min(md, self._scatter + max(1, md // 16)); return True

        if key in (ord("m"), ord("M")):
            self._ghost_mode = (self._ghost_mode + 1) % len(_GM_NAMES)
            self._wave_pos   = -1.0
            self._wave_t     = 0
            self._ghosts.clear()
            return True

        if key in (ord("f"), ord("F")):
            self._fx_mode = (self._fx_mode + 1) % len(_FX_NAMES); return True

        if key in (ord("o"), ord("O")):
            self._palette_idx = (self._palette_idx - 1) % len(_PALETTES); return True
        if key in (ord("p"), ord("P")):
            self._palette_idx = (self._palette_idx + 1) % len(_PALETTES); return True

        return False

    # ── update ────────────────────────────────────────────────────────────────

    def update(self, h: int, w: int) -> None:
        if h != self._h or w != self._w:
            self.on_resize(h, w)

        self._frame += 1
        self._acc   += self._speed
        while self._acc >= 1.0:
            self._acc -= 1.0
            self._do_step()

        self._decay_ghosts()
        self._render(h, w)

    # ── rendering ─────────────────────────────────────────────────────────────

    def _fx_live(self, r: int, c: int, col: Color) -> Color:
        fx = self._fx_mode
        if fx == _FX_SCANLINE  and r % 2 == 1:
            return col.lerp(BLACK, 0.55)
        if fx == _FX_CHROMATIC:
            t = c / max(1, self._w - 1)
            return Color(int(col.r*(1-t*0.25)), col.g, int(col.b*(0.72+t*0.28)))
        if fx == _FX_GRID and (r % 6 == 0 or c % 12 == 0):
            return col.lerp(BLACK, 0.45)
        return col

    def _fx_ghost(self, r: int, c: int, fg: Color, char: str) -> tuple:
        fx = self._fx_mode
        if fx == _FX_SCANLINE  and r % 2 == 1:
            fg = fg.lerp(BLACK, 0.60)
        if fx == _FX_CHROMATIC:
            t  = c / max(1, self._w - 1)
            fg = Color(int(fg.r*(1-t*0.4)+200*t*0.4),
                       int(fg.g * 0.55),
                       int(fg.b*(t*0.85+0.15)))
        if fx == _FX_NOISE and random.random() < 0.03:
            char = random.choice(_NOISE_CHARS)
        if fx == _FX_GRID and (r % 6 == 0 or c % 12 == 0):
            fg = fg.lerp(BLACK, 0.35)
        return fg, char

    def _render_bg(self) -> None:
        p = self._bg_plane
        p.clear()
        for r in range(self._h):
            for c in range(self._w):
                p.put_char(r, c, " ", fg=BLACK, bg=BLACK)

    def _render_ghosts(self) -> None:
        p    = self._ghost_plane
        p.clear()
        mode = self._ghost_mode

        for (r, c), (char, intensity) in self._ghosts.items():
            if intensity < 0.016:
                continue

            # Char — SMEAR replaces with block density chars
            display = self._smear_char(intensity, char) if mode in (_GM_SMEAR, _GM_COMPLEX) else char

            fg = self._pal_fg(r, c, intensity)
            bg = self._pal_bg(r, c, intensity)

            fg, display = self._fx_ghost(r, c, fg, display)

            bold = intensity > 0.60
            dim  = intensity < 0.25

            p.put_char(r, c, display, fg=fg, bg=bg, bold=bold, dim=dim)

            # COMPLEX: chromatic aberration — ±5 col red/blue shadows
            if mode == _GM_COMPLEX and intensity > 0.45:
                ca = intensity * 0.70
                red_str  = int(220 * ca)
                blue_str = int(220 * ca)
                # Near shadow (±2) — stronger
                if c > 1 and (r, c-2) not in self._ghosts:
                    p.put_char(r, c-2, display,
                               fg=Color(red_str, 0, 0), bg=BLACK)
                if c < self._w-2 and (r, c+2) not in self._ghosts:
                    p.put_char(r, c+2, display,
                               fg=Color(0, 0, blue_str), bg=BLACK)
                # Far shadow (±5) — dimmer
                if intensity > 0.65:
                    ds = int(red_str * 0.45)
                    if c > 4 and (r, c-5) not in self._ghosts:
                        p.put_char(r, c-5, display,
                                   fg=Color(ds, 0, int(ds*0.3)), bg=BLACK, dim=True)
                    if c < self._w-5 and (r, c+5) not in self._ghosts:
                        p.put_char(r, c+5, display,
                                   fg=Color(int(ds*0.3), 0, ds), bg=BLACK, dim=True)

    def _render_wave(self) -> None:
        """Render the luminous scanning bar for WAVE and COMPLEX modes."""
        p = self._wave_plane
        p.clear()
        mode = self._ghost_mode
        if mode not in (_GM_WAVE, _GM_COMPLEX):
            return
        if self._wave_pos < 0:
            return

        h, w   = self._h, self._w
        pos    = int(self._wave_pos)
        peak   = self._peak()
        bright = peak.lerp(WHITE, 0.55)
        soft   = peak.lerp(BLACK, 0.4)

        axis = w if self._dir in (_DIR_UP, _DIR_DOWN) else h

        # Draw 9-cell-wide sweep bar: fade → peak → white-hot centre → peak → fade
        for offset, col, bld in ((-4, soft,           False),
                                  (-3, peak,           False),
                                  (-2, peak,           True),
                                  (-1, bright,         True),
                                  ( 0, WHITE,          True),
                                  ( 1, bright,         True),
                                  ( 2, peak,           True),
                                  ( 3, peak,           False),
                                  ( 4, soft,           False)):
            pp = pos + offset
            if pp < 0 or pp >= axis:
                continue
            if self._dir in (_DIR_UP, _DIR_DOWN):
                bar_char = "│"
                for rr in range(h):
                    p.put_char(rr, pp, bar_char, fg=col, bg=BLACK, bold=bld)
            else:
                bar_char = "─"
                for cc in range(w):
                    p.put_char(pp, cc, bar_char, fg=col, bg=BLACK, bold=bld)

    def _render_live(self) -> None:
        p = self._live_plane
        p.clear()
        name = self._pal()[0]
        for r in range(self._h):
            for c in range(self._w):
                ch = self._canvas[r][c]
                if ch == " ":
                    continue
                if name == "RAINBOW":
                    col = _rainbow(r, c, self._frame * 0.003, 0.78)
                else:
                    col = self._cont()
                col = self._fx_live(r, c, col)
                p.put_char(r, c, ch, fg=col, bg=BLACK)

    def _render(self, h: int, w: int) -> None:
        self._render_bg()
        self._render_ghosts()
        self._render_wave()
        self._render_live()

    # ── planes / status ───────────────────────────────────────────────────────

    def planes(self) -> list[Plane]:
        return [self._bg_plane, self._ghost_plane,
                self._live_plane, self._wave_plane]

    @property
    def status_extras(self) -> str:
        md  = self._w if self._dir in (_DIR_UP, _DIR_DOWN) else self._h
        pct = int(100 * self._scatter / max(1, md))
        return (
            f"  {_DIR_NAMES[self._dir]}"
            f"  [/]{self._speed:.2f}"
            f"  -/={pct}%"
            f"  m:{_GM_NAMES[self._ghost_mode]}"
            f"  f:{_FX_NAMES[self._fx_mode]}"
            f"  o/p:{self._pal()[0]}"
        )

    @property
    def status_color(self) -> Color:
        return self._peak()
