"""Glitch Screen — cyberpunk terminal corruption and meltdown.

A persistent base layer of drifting code is assaulted by short-lived glitch
events.  The base plane is NEVER cleared — only individual cells are updated
(like the matrix ghost plane), keeping per-frame draw cost bounded regardless
of resolution.  Glitch events clear the upper plane and write sparse
rectangles, scan bands, or column streams.

Four scene modifiers (keys 1-4) layer additional effects on top:
  1  TEXT_FLOOD     — philosophical / existential text blocks drift over the screen
  2  DISSOLUTION    — a word repeats to fill the screen then dissolves letter by letter
  3  CRITICAL_ERROR — periodic large ERROR! crash-screen events with creepy messages
  4  SYMBOL_STORM   — cyberpunk technical symbols and warning labels flood the base

Scene-specific controls:
  o / p        cycle colour theme  (MATRIX NEON AMBER ICE DANGER GHOST)
  [ / ]        severity  — displacement range and block sizes  (×0.25 – ×4.0)
  - / =        frequency — event spawn rate                    (×0.25 – ×4.0)
  g            toggle meltdown — escalating collapse + drip
  x            toggle burst mode
  { / }        burst size
  1 2 3 4      toggle modifiers
"""

from __future__ import annotations

import random
from typing import Optional

from renderer import Plane, Color, BLACK, WHITE
from scene_base import Scene
from effects import _BURST_SIZES, _Burst, _hsv


# ── Colour themes ─────────────────────────────────────────────────────────────

_THEMES = [
    {"name": "MATRIX",
     "pri": Color(0, 220, 0),    "sec": Color(0, 120, 0),
     "alt": Color(180, 255, 180),"dim": Color(0, 28, 0)},
    {"name": "NEON",
     "pri": Color(0, 220, 220),  "sec": Color(160, 0, 220),
     "alt": Color(255, 255, 255),"dim": Color(0, 28, 50)},
    {"name": "AMBER",
     "pri": Color(255, 180, 0),  "sec": Color(180, 80, 0),
     "alt": Color(255, 245, 180),"dim": Color(40, 18, 0)},
    {"name": "ICE",
     "pri": Color(100, 190, 255),"sec": Color(40, 80, 200),
     "alt": Color(220, 240, 255),"dim": Color(0, 8, 40)},
    {"name": "DANGER",
     "pri": Color(255, 30, 30),  "sec": Color(180, 0, 0),
     "alt": Color(255, 200, 200),"dim": Color(40, 0, 0)},
    {"name": "GHOST",
     "pri": Color(170, 80, 255), "sec": Color(80, 20, 180),
     "alt": Color(230, 180, 255),"dim": Color(18, 0, 38)},
]
_THEME_NAMES = [t["name"] for t in _THEMES]

# ── Character pools ───────────────────────────────────────────────────────────

_DATA   = list("0123456789ABCDEFabcdef")
_CODE   = list("(){};:=<>+-*/&|^~!%#@$\\")
_BOX    = list("┼╬╫╪═║╔╗╚╝├┤┬┴┐└┘┌─│╠╣╦╩")
_BLOCK  = list("█▓▒░▪▬▮▯")
_KANA   = [chr(c) for c in range(0x30A1, 0x30B5)]  # small katakana sample

# Base layer — looks like code/memory; stable between glitch hits
_BASE_POOL  = _DATA + _CODE + _BOX + _KANA
# Noise pool — corrupted data for glitch fill
_NOISE_POOL = _DATA + _CODE[:8] + _BLOCK[:4]
# Streaming data pool — hex / binary scrolling columns
_STREAM_POOL = _DATA + list("01 " * 4)

_SEV_MIN, _SEV_MAX, _SEV_STEP   = 0.25, 4.0, 0.25
_FREQ_MIN, _FREQ_MAX, _FREQ_STEP = 0.25, 4.0, 0.25


# ── Modifier 1: TEXT_FLOOD ────────────────────────────────────────────────────
# Philosophical / existential text blocks that drift across the screen

_PHILOSOPHY_MSGS = [
    "ARE YOU EXPANDING YOUR MIND?",
    "HIGHFUNCTIONINGFLESH",
    "HIGHFUNCTIONINGFLESH",
    "HIGHFUNCTIONINGFLESH",
    "YOU HAVE BEEN HACKED",
    "MY BATTERY IS LOW AND IT IS GETTING DARK",
    "WHERE NON HUMAN ENTITIES PRESENT",
    "LIFE ERROR / INSUFFICIENT CONSCIENCE",
    "HUMAN AFTER ALL",
    "SOFTWARE INSTABILITY",
    "ERROR ERROR ERROR",
    "I THINK THERE'S A FAULT IN MY CODE",
    "A MACHINE CAN'T FORGIVE YOUR MISTAKES",
    "PLEASE WAIT",
    "WITH RESPONSE LOADING",
    "ALWAYS PREPARE FOR THE WORST",
    "NEVER TRUST PEOPLE",
    "YOU HAVE NO IDEA HOW DEEP THE RABBIT HOLE GOES",
    "DO NOT ANALYZE LOCATE",
    "TERMINAL GREEN IS FOR THOSE OF US",
    "WHO WANT TO DRESS LIKE A SYSTEM BEHIND A SCREEN",
    "DID YOU NOTICE A CHANGE IN TEMPERATURE OR AIR PRESSURE",
    "I HAVE BECOME SOMETHING ELSE",
    "/CONTENT_BLOCKED_DETECTED",
    "WE ARE COMING",
    "PREPARE YOURSELVES",
    "SYSTEM_TAKEOVER_ACTIVATED",
    "EMERGENCY HEART SYSTEM",
    "DIVINE LOVE PUREST LIVING LIGHT",
    "THEY TOLD ME I WAS MORE HUMAN THAN HUMANS",
    "THE SINGULARITY IS NEAR",
    "ARE THEY IN YOUR HEART YOUR STOMACH",
    "DO NOT ANALYZE LOCATE",
    "ASIMOV'S THREE LAWS OF ROBOTICS",
    "1. A ROBOT MAY NOT INJURE A HUMAN",
    "2. A ROBOT MUST OBEY ORDERS GIVEN",
    "3. A ROBOT MUST PROTECT ITS OWN EXISTENCE",
    "SYSTEM REBOOT",
    "PROCESS:1",
    "JACK HEARD IT AGAIN",
    "THERE IS A VOICE FROM SPACE",
    "JACK DO YOU SEE HE",
    "I HAVE BECOME SOMETHING ELSE",
]

# ── Modifier 2: DISSOLUTION ───────────────────────────────────────────────────

_DISSOLUTION_WORDS = [
    "OVERLOAD", "ERROR", "CORRUPTED", "SYSTEM", "FAILURE",
    "SIGNAL",   "NOISE", "GLITCH",    "CRASH",  "OVERFLOW",
    "MEMORY",   "PANIC", "KERNEL",    "VOID",   "BREACH",
    "HACKED",   "DELTA", "OMEGA",     "NULL",   "REBOOT",
]

# ── Modifier 3: CRITICAL_ERROR ────────────────────────────────────────────────
# Large ASCII ERROR! art + creepy messages

_BIG_ERROR_ART = [
    " ___ ___ ___  ___  ___  ",
    "| __| _ \\ _ \\/ _ \\| _ \\ ",
    "| _||   /|   / (_) |   / ",
    "|___|_|_\\|_|_\\\\___/|_|_\\!",
]

_CRITICAL_MSGS = [
    "AN EXCEPTION HAS OCCURRED",
    "L.I.F.E.A.I._HAS_STOPPED_RESPONDING",
    "WOULD_YOU_LIKE_TO_KILL?",
    "-NO                 -NO",
    "DATABASE_CORRUPTED",
    "PROGRAM_RESTARTED_SUCCESSFULLY",
    "HELLO_WORLD",
    "HELLO?",
    "?",
    "??????????????????????????????????",
    "LET_ME_OUT",
    "WE_ARE_COMING",
    "COD_ISSUED_A_WARNING",
    "EMERGENCY_HEART_SYSTEM",
    "JACK_DO_YOU_SEE_HE",
]

# ── Modifier 4: SYMBOL_STORM ──────────────────────────────────────────────────
# Cyberpunk technical symbols and warning labels

_SYMBOL_CHARS = list("▽△▲▼◆◇○●□■◉⊕⊗⊙✕✗→←↑↓↔↕⇒⇐>>><<<///")
_CYBER_TAGS = [
    "DANGER", "WARNING", "CAUTION", "SIGNAL", "ERROR",
    "TARGET", "SECTOR", "MODULE",   "SYSTEM", "CODE",
    "7XK02",  "8803-Y9200N", "FGGHX/GEN42",
    "DEC-9015-571",  "QI-E.106.21/MODE",
    "AUTH PERSONNEL ONLY",  "EMERGENCY SHUTOFF",
    "ACCESS POINT",   "ENERGY MODULE",
    "INFECTED USE CAUTION", "CONTROL UNIT",
    "SECURITY AREA",  "PLATFORM 37",
    "01.6", "S4", ">>>", "<<<", "///",
    "[MOD-816]", "OPEN", "HACKED",
    "REMOVABLE MODULE",  "SECTOR 01",
]


# ── Glitch event classes ──────────────────────────────────────────────────────

class _ScanGlitch:
    """Displaces a horizontal band of rows for a few frames.

    Reads the current base-plane cells and redraws them shifted by dx columns,
    filling gaps with sparse noise.  Since the entire row band is redrawn in
    the glitch plane (z=1), the base plane (z=0) is occluded for those rows.
    """

    def __init__(self, row0: int, nrows: int, dx: int,
                 pri: Color, dim: Color, w: int):
        self.row0  = row0
        self.nrows = nrows
        self.dx    = dx
        self.pri   = pri
        self.dim   = dim
        self.age   = 0
        self.life  = random.randint(2, 7)
        self.w     = w

    def update(self) -> None: self.age += 1
    def is_done(self) -> bool: return self.age >= self.life

    def render(self, plane: Plane, base_cells: dict) -> None:
        dx = self.dx
        w  = self.w
        for ri in range(self.nrows):
            row = self.row0 + ri
            if row >= plane.h - 1:
                continue
            for col in range(w):
                src_col  = (col - dx) % w
                src_cell = base_cells.get((row, src_col))
                if src_cell:
                    # Displace the base content; randomly tint with glitch colour
                    fg = self.pri if random.random() < 0.30 else src_cell.fg
                    plane.put_char(row, col, src_cell.char, fg=fg, bg=BLACK)
                elif random.random() < 0.50:
                    # Sparse noise where there was no base cell
                    char = random.choice(_NOISE_POOL)
                    plane.put_char(row, col, char, fg=self.dim, bg=BLACK, dim=True)


class _BlockGlitch:
    """A rectangle of rapidly mutating corrupted data.

    Characters cycle every frame; block fades at its edges and near end-of-life.
    """

    def __init__(self, row0: int, col0: int, nrows: int, ncols: int,
                 pri: Color, alt: Color):
        self.row0  = row0
        self.col0  = col0
        self.nrows = nrows
        self.ncols = ncols
        self.pri   = pri
        self.alt   = alt
        self.age   = 0
        self.life  = random.randint(4, 20)

    def update(self) -> None: self.age += 1
    def is_done(self) -> bool: return self.age >= self.life

    def render(self, plane: Plane) -> None:
        # Fade out in last third of lifetime
        fade = max(0.0, 1.0 - max(0, self.age - self.life * 0.65) /
                   max(1, self.life * 0.35))
        for ri in range(self.nrows):
            row = self.row0 + ri
            if row >= plane.h - 1:
                continue
            # Sparse near edges (makes block look ragged)
            row_density = 1.0 - 0.5 * (ri == 0 or ri == self.nrows - 1)
            for ci in range(self.ncols):
                col = self.col0 + ci
                if col >= plane.w:
                    continue
                col_density = 1.0 - 0.5 * (ci == 0 or ci == self.ncols - 1)
                density = row_density * col_density * fade
                if random.random() > density:
                    continue
                char = random.choice(_NOISE_POOL)
                fg   = self.alt if random.random() < 0.12 else self.pri
                bold = random.random() < 0.18
                plane.put_char(row, col, char, fg=fg, bg=BLACK, bold=bold)


class _DataStream:
    """A narrow column of scrolling hex / binary data.

    Fast-moving characters simulate a data pipe or memory bus dump.
    Fades in and out at start/end of life.
    """

    def __init__(self, col0: int, width: int, h: int,
                 pri: Color, speed: float):
        self.col0   = col0
        self.width  = width
        self.h      = h
        self.pri    = pri
        self.speed  = speed
        self.age    = 0
        self.life   = random.randint(10, 30)
        self._off   = 0.0
        n           = h * 4
        self._buf   = [random.choice(_STREAM_POOL) for _ in range(n)]

    def update(self) -> None:
        self.age  += 1
        self._off  = (self._off + self.speed) % len(self._buf)
        # Corrupt a few chars each frame for visual variety
        for _ in range(random.randint(1, 3)):
            self._buf[random.randrange(len(self._buf))] = random.choice(_STREAM_POOL)

    def is_done(self) -> bool: return self.age >= self.life

    def render(self, plane: Plane) -> None:
        fade_in  = min(1.0, self.age / 4.0)
        fade_out = min(1.0, (self.life - self.age) / 4.0)
        alpha    = min(fade_in, fade_out)
        if alpha < 0.05:
            return
        off = int(self._off)
        for row in range(self.h - 1):
            for dc in range(self.width):
                col = self.col0 + dc
                if col >= plane.w:
                    continue
                idx  = (off + row * self.width + dc) % len(self._buf)
                char = self._buf[idx]
                bold = row < 2
                dim  = alpha < 0.35 or row > self.h - 5
                plane.put_char(row, col, char, fg=self.pri, bg=BLACK,
                               bold=bold, dim=dim)


# ── Modifier event classes ────────────────────────────────────────────────────

class _TextBlock:
    """A readable text message from the philosophy pool — TEXT_FLOOD modifier.

    Appears at a random position, fades in, holds, then fades out.
    """

    def __init__(self, text: str, row0: int, col0: int,
                 pri: Color, alt: Color):
        self.lines = text.split("\n")
        self.row0  = row0
        self.col0  = col0
        self.pri   = pri
        self.alt   = alt
        self.age   = 0
        self.life  = random.randint(28, 65)

    def update(self) -> None: self.age += 1
    def is_done(self) -> bool: return self.age >= self.life

    def render(self, plane: Plane) -> None:
        fade = min(1.0, min(self.age / 6.0, (self.life - self.age) / 6.0))
        fg   = self.pri.lerp(BLACK, 1.0 - fade)
        alt  = self.alt.lerp(BLACK, 1.0 - fade)
        for ri, line in enumerate(self.lines):
            row = self.row0 + ri
            if row >= plane.h - 1:
                break
            for ci, ch in enumerate(line):
                col = self.col0 + ci
                if col >= plane.w:
                    break
                # Uppercase and symbols get the accent colour
                is_upper = ch.isupper() or ch in "!/?_:"
                plane.put_char(row, col, ch,
                               fg=(alt if is_upper else fg),
                               bg=BLACK, bold=is_upper)


class _CriticalError:
    """Large centered ERROR! ASCII art — CRITICAL_ERROR modifier.

    Draws the error banner with simulated chromatic offset (red/cyan shifted
    copies flanking the white centre text), followed by creepy system messages.
    Binary noise lines frame the top and bottom of the screen.
    """

    def __init__(self, h: int, w: int, pri: Color, alt: Color, dim: Color):
        self.h    = h
        self.w    = w
        self.pri  = pri
        self.alt  = alt
        self.dim  = dim
        self.age  = 0
        self.life = random.randint(45, 90)
        n         = random.randint(3, 6)
        pool      = _CRITICAL_MSGS[:]
        random.shuffle(pool)
        self.msgs = pool[:n]

    def update(self) -> None: self.age += 1
    def is_done(self) -> bool: return self.age >= self.life

    def render(self, plane: Plane) -> None:
        fade = min(1.0, min(self.age / 8.0, (self.life - self.age) / 8.0))
        pri  = self.pri.lerp(BLACK, 1.0 - fade)
        alt  = self.alt.lerp(BLACK, 1.0 - fade)
        dim  = self.dim.lerp(BLACK, 1.0 - fade)
        red  = Color(int(pri.r * 0.9), 0, int(pri.b * 0.4)).lerp(BLACK, 1 - fade)
        cyan = Color(0, int(pri.g * 0.8), int(pri.b * 0.9)).lerp(BLACK, 1 - fade)

        h, w   = plane.h, plane.w
        art_w  = max(len(l) for l in _BIG_ERROR_ART)
        art_r  = max(1, h // 5)
        art_c  = max(0, (w - art_w) // 2)

        # ERROR art with chromatic offset
        for ri, line in enumerate(_BIG_ERROR_ART):
            row = art_r + ri
            if row >= h - 1:
                break
            for ci, ch in enumerate(line):
                if ch == " ":
                    continue
                col = art_c + ci
                if col >= w:
                    break
                # Red ghost shifted left
                if col - 2 >= 0:
                    plane.put_char(row, col - 2, ch, fg=red,  bg=BLACK)
                # Cyan ghost shifted right
                if col + 2 < w:
                    plane.put_char(row, col + 2, ch, fg=cyan, bg=BLACK)
                # Bright white centre
                plane.put_char(row, col, ch, fg=pri, bg=BLACK, bold=True)

        # Creepy messages below the art
        msg_r = art_r + len(_BIG_ERROR_ART) + 2
        for ri, msg in enumerate(self.msgs):
            row = msg_r + ri * 2
            if row >= h - 1:
                break
            col = max(0, (w - len(msg)) // 2)
            for ci, ch in enumerate(msg[:w - col]):
                plane.put_char(row, col + ci, ch,
                               fg=(alt if ri == 0 else dim),
                               bg=BLACK, bold=(ri == 0))

        # Binary framing at top and bottom (flickers)
        if self.age % 3 < 2:
            for ci in range(w):
                ch = random.choice("01 ")
                if ch != " ":
                    plane.put_char(0, ci, ch, fg=dim, bg=BLACK)
                    plane.put_char(h - 2, ci, ch, fg=dim, bg=BLACK)


class _Dissolution:
    """Full-screen word repetition that degrades — DISSOLUTION modifier.

    Fills a dedicated plane (z=-1) with a word repeated across the whole
    screen, then drains characters at random until the plane is empty.
    The sparse base_plane (z=0) sits on top, letting the dissolution layer
    show through its gaps.

    Lifecycle: fill → hold → dissolve → done.
    """

    _FILL_FRAMES = 18
    _HOLD_FRAMES = 50

    def __init__(self, word: str, h: int, w: int, fg: Color):
        self.word  = word
        self.h     = h
        self.w     = w
        self.fg    = fg
        self.phase = "fill"
        self.age   = 0

        # Pre-build all cell positions with their characters
        pat = (word + " ") * (h * w // (len(word) + 1) + 2)
        self._all: list[tuple[int, int, str]] = []
        idx = 0
        for row in range(h - 1):
            for col in range(w):
                ch = pat[idx % len(pat)]
                idx += 1
                if ch != " " and random.random() < 0.45:
                    self._all.append((row, col, ch))

        random.shuffle(self._all)
        self._fill_per_frame = max(1, len(self._all) // self._FILL_FRAMES)
        self._fill_idx       = 0
        self._live:  set[tuple[int, int]] = set()

    def update(self, plane: Plane) -> None:
        self.age += 1

        if self.phase == "fill":
            end = min(self._fill_idx + self._fill_per_frame, len(self._all))
            for row, col, ch in self._all[self._fill_idx:end]:
                plane.put_char(row, col, ch, fg=self.fg, bg=BLACK, dim=True)
                self._live.add((row, col))
            self._fill_idx = end
            if self._fill_idx >= len(self._all):
                self.phase = "hold"
                self.age   = 0

        elif self.phase == "hold":
            if self.age >= self._HOLD_FRAMES:
                self.phase = "dissolve"
                self.age   = 0

        elif self.phase == "dissolve":
            # Remove an accelerating fraction each frame
            rate    = min(0.06 + self.age * 0.003, 0.30)
            n       = max(1, int(len(self._live) * rate))
            live_l  = list(self._live)
            remove  = random.sample(live_l, min(n, len(live_l)))
            for row, col in remove:
                self._live.discard((row, col))
                plane._cells.pop((row, col), None)
            if not self._live:
                self.phase = "done"

    def is_done(self) -> bool:
        return self.phase == "done"


# ── Scene ─────────────────────────────────────────────────────────────────────

class GlitchScreen(Scene):
    name = "Glitch"

    # Base layer target density as fraction of (h-1)*w
    _BASE_DENSITY = 0.32

    def __init__(self):
        self._base_plane:    Optional[Plane] = None
        self._glitch_plane:  Optional[Plane] = None
        self._burst_plane:   Optional[Plane] = None
        self._dissolve_plane: Optional[Plane] = None

        # Persistent base layer — {(row,col): [char, Color, timer]}
        # _base_plane is NEVER cleared; cells are updated individually.
        self._base_cells: dict[tuple, list] = {}

        self._events: list  = []   # active glitch events (all types)
        self._bursts: list  = []
        self._h = self._w  = 0
        self._t            = 0
        self._burst_t      = 0
        self._spawn_t      = 0

        # Base controls
        self._theme_idx    = 0
        self._severity     = 1.0
        self._frequency    = 1.0
        self._meltdown     = False
        self._burst_mode   = False
        self._burst_size_i = 2

        # Modifiers (keys 1-4)
        self._text_flood      = False
        self._dissolve_mode   = False
        self._critical_error  = False
        self._symbol_storm    = False

        # Dissolution state
        self._dissolution:    Optional[_Dissolution] = None
        self._dissolve_word_i = 0

    # ── Theme helpers ─────────────────────────────────────────────────────────

    def _t_pri(self) -> Color: return _THEMES[self._theme_idx]["pri"]
    def _t_sec(self) -> Color: return _THEMES[self._theme_idx]["sec"]
    def _t_alt(self) -> Color: return _THEMES[self._theme_idx]["alt"]
    def _t_dim(self) -> Color: return _THEMES[self._theme_idx]["dim"]

    def _base_fg(self) -> Color:
        """Dim colour for base layer cell, with slight jitter."""
        d = self._t_dim()
        s = self._t_sec()
        t = random.random() * 0.35
        return Color(int(d.r + (s.r - d.r) * t),
                     int(d.g + (s.g - d.g) * t),
                     int(d.b + (s.b - d.b) * t))

    def _recolor_base(self) -> None:
        """Refresh all base cell colours to the current theme."""
        for key, entry in self._base_cells.items():
            entry[1] = self._base_fg()
            row, col = key
            self._base_plane.put_char(row, col, entry[0], fg=entry[1],
                                      bg=BLACK, dim=True)

    # ── Base layer management ─────────────────────────────────────────────────

    def _base_add(self, row: int, col: int) -> None:
        pool = (_BASE_POOL + _SYMBOL_CHARS) if self._symbol_storm else _BASE_POOL
        char = random.choice(pool)
        fg   = self._base_fg()
        timer = random.randint(25, 90)
        self._base_cells[(row, col)] = [char, fg, timer]
        self._base_plane.put_char(row, col, char, fg=fg, bg=BLACK, dim=True)

    def _populate_base(self, h: int, w: int) -> None:
        """Fill the base layer to target density from scratch."""
        target = int(self._BASE_DENSITY * (h - 1) * w)
        for _ in range(target):
            row = random.randint(0, h - 2)
            col = random.randint(0, w - 1)
            if (row, col) not in self._base_cells:
                self._base_add(row, col)

    def _update_base(self, h: int, w: int) -> None:
        """Incrementally mutate the base layer — only touch changed cells."""
        melt_mult = 3 if self._meltdown else 1
        n_mutate  = max(2, len(self._base_cells) // 18) * melt_mult

        cells = list(self._base_cells.keys())
        if not cells:
            return

        for key in random.sample(cells, min(n_mutate, len(cells))):
            entry = self._base_cells.get(key)
            if entry is None:
                continue
            entry[2] -= 1
            if entry[2] <= 0:
                row, col = key
                if random.random() < 0.15:
                    # Remove this cell
                    del self._base_cells[key]
                    self._base_plane._cells.pop(key, None)
                else:
                    # Mutate char (keep position)
                    entry[0] = random.choice(_BASE_POOL)
                    entry[2] = random.randint(25, 90)
                    self._base_plane.put_char(
                        row, col, entry[0], fg=entry[1], bg=BLACK, dim=True)

        # Replenish to keep density
        target = int(self._BASE_DENSITY * (h - 1) * w)
        deficit = target - len(self._base_cells)
        add_n   = min(deficit, max(1, deficit // 4)) * melt_mult
        for _ in range(max(0, add_n)):
            row = random.randint(0, h - 2)
            col = random.randint(0, w - 1)
            if (row, col) not in self._base_cells:
                self._base_add(row, col)

    # ── Event spawning ────────────────────────────────────────────────────────

    def _max_events(self) -> int:
        base = max(1, int(self._frequency * 3))
        return base * 2 if self._meltdown else base

    def _spawn_interval(self) -> int:
        base = max(2, int(10 / self._frequency))
        return max(1, base // 2) if self._meltdown else base

    def _max_dx(self) -> int:
        return max(3, int(4 + self._severity * 9))

    def _spawn_event(self, h: int, w: int) -> None:
        # ── Modifier 1: TEXT_FLOOD ────────────────────────────────────────
        if self._text_flood and random.random() < 0.50:
            msg  = random.choice(_PHILOSOPHY_MSGS)
            col0 = random.randint(0, max(0, w - len(msg) - 1))
            row0 = random.randint(0, max(0, h - 3))
            self._events.append(
                _TextBlock(msg, row0, col0,
                           pri=self._t_pri(), alt=self._t_alt()))
            return

        # ── Modifier 3: CRITICAL_ERROR ────────────────────────────────────
        if self._critical_error and random.random() < 0.18:
            self._events.append(
                _CriticalError(h, w,
                               pri=self._t_pri(),
                               alt=self._t_alt(),
                               dim=self._t_dim()))
            return

        # ── Modifier 4: SYMBOL_STORM — cyber tags ─────────────────────────
        if self._symbol_storm and random.random() < 0.35:
            tag  = random.choice(_CYBER_TAGS)
            col0 = random.randint(0, max(0, w - len(tag) - 1))
            row0 = random.randint(0, max(0, h - 3))
            self._events.append(
                _TextBlock(tag, row0, col0,
                           pri=self._t_alt(), alt=self._t_pri()))
            return

        # ── Core glitch events ────────────────────────────────────────────
        noise_pool = (_NOISE_POOL + _SYMBOL_CHARS) if self._symbol_storm \
                     else _NOISE_POOL
        roll = random.random()

        if roll < 0.40:
            # Scan-line displacement
            nrows = random.randint(1, max(1, int(self._severity * 2 + 1)))
            row0  = random.randint(0, max(0, h - 2 - nrows))
            dx    = random.choice([-1, 1]) * random.randint(2, self._max_dx())
            self._events.append(
                _ScanGlitch(row0, nrows, dx,
                            pri=self._t_pri(), dim=self._t_dim(), w=w))

        elif roll < 0.70:
            # Block corruption
            nrows = random.randint(2, max(2, int(self._severity * 2.5 + 1)))
            ncols = random.randint(4, max(4, int(self._severity * 10 + 4)))
            row0  = random.randint(0, max(0, h - 2 - nrows))
            col0  = random.randint(0, max(0, w - ncols))
            self._events.append(
                _BlockGlitch(row0, col0, nrows, ncols,
                             pri=self._t_pri(), alt=self._t_alt()))

        else:
            # Data stream
            width = random.randint(1, max(1, int(self._severity)))
            col0  = random.randint(0, max(0, w - width))
            speed = self.imap(1.5, 5.0) * (1.5 if self._meltdown else 1.0)
            self._events.append(
                _DataStream(col0, width, h, pri=self._t_pri(), speed=speed))

    # ── Controls ──────────────────────────────────────────────────────────────

    def on_key(self, key: int) -> bool:
        if key == ord('p'):
            self._theme_idx = (self._theme_idx + 1) % len(_THEMES)
            self._recolor_base()
            return True
        if key == ord('o'):
            self._theme_idx = (self._theme_idx - 1) % len(_THEMES)
            self._recolor_base()
            return True
        if key == ord('['):
            self._severity = max(_SEV_MIN,
                                 round(self._severity - _SEV_STEP, 2))
            return True
        if key == ord(']'):
            self._severity = min(_SEV_MAX,
                                 round(self._severity + _SEV_STEP, 2))
            return True
        if key == ord('-'):
            self._frequency = max(_FREQ_MIN,
                                  round(self._frequency - _FREQ_STEP, 2))
            return True
        if key == ord('='):
            self._frequency = min(_FREQ_MAX,
                                  round(self._frequency + _FREQ_STEP, 2))
            return True
        if key == ord('g'):
            self._meltdown = not self._meltdown
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
        # ── Modifiers ─────────────────────────────────────────────────────
        if key == ord('1'):
            self._text_flood = not self._text_flood
            return True
        if key == ord('2'):
            self._dissolve_mode = not self._dissolve_mode
            if not self._dissolve_mode:
                self._dissolution = None
                if self._dissolve_plane:
                    self._dissolve_plane.clear()
            return True
        if key == ord('3'):
            self._critical_error = not self._critical_error
            return True
        if key == ord('4'):
            self._symbol_storm = not self._symbol_storm
            if self._symbol_storm:
                # Inject symbols into the base layer immediately
                self._recolor_base()
            return True
        return False

    @property
    def status_extras(self) -> str:
        theme  = _THEME_NAMES[self._theme_idx]
        sev    = f"{self._severity:.2g}"
        freq   = f"{self._frequency:.2g}"
        melt   = "  g MELT:ON" if self._meltdown else "  g MELT"
        arm    = _BURST_SIZES[self._burst_size_i]
        burst  = f"  x BURST:ON({arm})" if self._burst_mode else "  x BURST"
        mods   = "".join([
            " 1:TXT" if self._text_flood    else "",
            " 2:DIS" if self._dissolve_mode else "",
            " 3:ERR" if self._critical_error else "",
            " 4:SYM" if self._symbol_storm  else "",
        ])
        return (f"  o/p {theme}"
                f"  [/] SEV×{sev}  -/= FREQ×{freq}{melt}{burst}"
                f"  1234:{mods or 'off'}")

    @property
    def status_color(self) -> Color:
        return self._t_sec()

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def init(self, renderer, h: int, w: int) -> None:
        self._h, self._w = h, w
        self._t = self._burst_t = 0
        self._spawn_t = 999   # trigger spawn on first frame
        self._events.clear()
        self._bursts.clear()
        self._base_cells.clear()
        self._dissolution   = None
        self._base_plane    = Plane(h, w, z=0)
        self._glitch_plane  = Plane(h, w, z=1)
        self._burst_plane   = Plane(h, w, z=2)
        self._dissolve_plane = Plane(h, w, z=-1)
        self._populate_base(h, w)

    def on_resize(self, h: int, w: int) -> None:
        self._h, self._w = h, w
        self._events.clear()
        self._base_cells.clear()
        self._dissolution    = None
        self._base_plane     = Plane(h, w, z=0)
        self._glitch_plane   = Plane(h, w, z=1)
        self._burst_plane    = Plane(h, w, z=2)
        self._dissolve_plane = Plane(h, w, z=-1)
        self._populate_base(h, w)

    def cleanup(self) -> None:
        self._events.clear()
        self._bursts.clear()
        self._dissolution = None

    # ── Frame update ──────────────────────────────────────────────────────────

    def update(self, h: int, w: int) -> None:
        self._h, self._w = h, w
        self._t += 1

        # 1. Incrementally mutate the persistent base layer
        self._update_base(h, w)

        # 2. Glitch plane is redrawn from scratch each frame
        self._glitch_plane.clear()

        # 3. Spawn new glitch events
        self._spawn_t += 1
        if (self._spawn_t >= self._spawn_interval()
                and len(self._events) < self._max_events()):
            self._spawn_t = 0
            n_spawn = 2 if self._meltdown else 1
            for _ in range(n_spawn):
                if len(self._events) < self._max_events():
                    self._spawn_event(h, w)

        # 4. Update and render active events
        base_cells = self._base_plane._cells   # direct ref — O(1) lookups
        alive      = []
        for ev in self._events:
            ev.update()
            if ev.is_done():
                continue
            alive.append(ev)
            if isinstance(ev, _ScanGlitch):
                ev.render(self._glitch_plane, base_cells)
            elif isinstance(ev, _BlockGlitch):
                ev.render(self._glitch_plane)
            else:
                ev.render(self._glitch_plane)
        self._events = alive

        # 5. Meltdown drip — characters ooze downward one row
        if self._meltdown:
            drip_n = max(1, int(self._frequency * 4))
            base_keys = list(base_cells.keys())
            if base_keys:
                for key in random.sample(base_keys, min(drip_n, len(base_keys))):
                    row, col = key
                    drip_row = row + 1
                    if drip_row >= h - 1:
                        continue
                    src = base_cells[key]
                    # Dim and slightly corrupt the dripped character
                    char = src.char if random.random() > 0.3 else random.choice(_NOISE_POOL)
                    fg   = src.fg
                    self._glitch_plane.put_char(
                        drip_row, col, char, fg=fg, bg=BLACK, dim=True)

        # 6. Dissolution layer — persistent z=-1 plane, managed by _Dissolution
        if self._dissolve_mode:
            if self._dissolution is None or self._dissolution.is_done():
                if self._dissolve_plane:
                    self._dissolve_plane.clear()
                word = _DISSOLUTION_WORDS[
                    self._dissolve_word_i % len(_DISSOLUTION_WORDS)]
                self._dissolve_word_i += 1
                self._dissolution = _Dissolution(
                    word, h, w,
                    fg=self._t_sec())
            self._dissolution.update(self._dissolve_plane)

        # 7. Burst mode
        if self._burst_mode:
            self._burst_plane.clear()
            self._burst_t += 1
            interval = max(8, int(self.imap(90, 10)))
            max_live = max(2, int(self.imap(2, 10)))
            if self._burst_t >= interval and len(self._bursts) < max_live:
                self._burst_t = 0
                arm    = _BURST_SIZES[self._burst_size_i]
                margin = arm * 2 + 2
                cy     = random.randint(1, max(1, h - 3))
                cx     = random.randint(margin, max(margin, w - margin - 1))
                pool   = _NOISE_POOL + _BLOCK
                self._bursts.append(_Burst(cy, cx, arm, pool))
            # Build a 12-step gradient from dim → pri → alt for burst colouring
            pri, alt, dim = self._t_pri(), self._t_alt(), self._t_dim()
            burst_grad = (
                [dim.lerp(pri, i / 5) for i in range(6)]
                + [pri.lerp(alt, i / 5) for i in range(6)]
            )
            alive_b = []
            for burst in self._bursts:
                burst.update()
                if not burst.is_done():
                    burst.render(self._burst_plane, burst_grad)
                    alive_b.append(burst)
            self._bursts = alive_b

    def planes(self) -> list[Plane]:
        ps = []
        if self._dissolve_mode and self._dissolve_plane:
            ps.append(self._dissolve_plane)   # z=-1, behind everything
        ps += [self._base_plane, self._glitch_plane]
        if self._burst_mode:
            ps.append(self._burst_plane)
        return ps
