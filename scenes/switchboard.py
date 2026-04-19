"""Switchboard — Shadytel Metropolitan Telephone Exchange.

Full-screen interactive telephone switchboard: animated jack grid with
patch-cord visualizations, live call routing, operator log, trunk lines,
and a system PANIC mode with the Shadytel yellow crash screen.

Scene-specific controls:
  W / A / S / D  move cursor across jack grid
  Enter / Space  select jack (second select on different jack = connect pair)
  r              manually ring selected jack
  x              disconnect call / cancel ring at selected jack
  t              spawn an incoming trunk call
  [ / ]          auto-spawn rate  (slower / faster)
  g              toggle jack number labels
  c              trigger PANIC crash
  z              recover from crash
"""

from __future__ import annotations

import random
from typing import Optional

from renderer import Plane, Color, BLACK, WHITE
from scene_base import Scene


# ── Palette ───────────────────────────────────────────────────────────────────

_DARK_BG       = Color(0,   5,  15)
_HDR_BG        = Color(0,   8,  30)
_HDR_FG        = Color(100, 150, 220)
_HDR_HL        = Color(180, 210, 255)
_BORDER_FG     = Color(30,  60, 120)

_IDLE_FG       = Color(40,  60,  90)
_IDLE_BOX      = Color(25,  40,  65)
_RING_FG       = Color(220, 180,   0)
_RING_BOX      = Color(140, 100,   0)
_CONN_A_FG     = Color(  0, 210,  80)
_CONN_A_BOX    = Color(  0, 120,  45)
_CONN_B_FG     = Color(  0, 180, 220)
_CONN_B_BOX    = Color(  0,  90, 120)
_TRUNK_FG      = Color(210,  70, 220)
_TRUNK_BOX     = Color(110,  30, 120)
_CURSOR_FG     = Color(  0, 230, 230)
_CURSOR_BOX    = Color(  0, 120, 120)
_SELECTED_FG   = Color(255, 220,  50)
_SELECTED_BOX  = Color(140, 110,  20)

_WIRE_FG       = Color(  0, 160,  70)
_WIRE_RING_FG  = Color(200, 140,   0)
_WIRE_TRUNK_FG = Color(180,  50, 200)

_PANEL_FG      = Color( 80, 120, 170)
_PANEL_HL      = Color(160, 200, 255)
_PANEL_DIM     = Color( 40,  60,  90)
_PANEL_SEP     = Color( 20,  40,  70)

_CALL_A_FG     = Color(  0, 210,  80)
_CALL_B_FG     = Color(  0, 180, 220)
_CALL_TIME_FG  = Color( 80, 130, 170)

_CRASH_BG      = Color(210, 160,   0)   # amber-yellow
_CRASH_DARK    = Color( 10,  35,  90)   # dark blue for logo/text
_CRASH_MID     = Color( 20,  55, 130)
_CRASH_ERR     = Color(180,  20,   0)   # red for error lines
_CRASH_BLACK   = Color(  0,   0,   0)


# ── Jack grid constants ───────────────────────────────────────────────────────

_JACK_W   = 5    # cols per jack slot (box=4 + 1 gap)
_JACK_H   = 4    # rows per jack slot (box=3 + 1 wire-channel)
_BOX_W    = 4    # ┌──┐ width
_BOX_H    = 3    # top/mid/bot rows
_WIRE_ROW = 3    # offset from jack_top to wire channel

_INFO_W   = 26   # right panel width
_HDR_H    = 3    # header rows
_LOG_MAX  = 80   # operator log scroll buffer


# ── Shadytel crash screen logo ────────────────────────────────────────────────

# Pentagon outline + phone handset inside — rendered centered on yellow bg
_LOGO = [
    r"          ╭──────────────────────╮          ",
    r"        ╭─╯                      ╰─╮        ",
    r"       ╱    ╔═══╗          ╔═══╗    ╲       ",
    r"      │     ║ ○ ║          ║ ○ ║     │      ",
    r"      │     ╚═══╩══════════╩═══╝     │      ",
    r"      │     ╔═══╦══════════╦═══╗     │      ",
    r"      │     ║ ○ ║          ║ ○ ║     │      ",
    r"       ╲    ╚═══╝          ╚═══╝    ╱       ",
    r"        ╰─╮                      ╭─╯        ",
    r"          ╰──────────────────────╯          ",
]

_SHADYTEL_BIG = [
    r" ███████╗██╗  ██╗ █████╗ ██████╗ ██╗   ██╗████████╗███████╗██╗     ",
    r" ██╔════╝██║  ██║██╔══██╗██╔══██╗╚██╗ ██╔╝╚══██╔══╝██╔════╝██║     ",
    r" ███████╗███████║███████║██║  ██║ ╚████╔╝    ██║   █████╗  ██║     ",
    r" ╚════██║██╔══██║██╔══██║██║  ██║  ╚██╔╝     ██║   ██╔══╝  ██║     ",
    r" ███████║██║  ██║██║  ██║██████╔╝   ██║      ██║   ███████╗███████╗",
    r" ╚══════╝╚═╝  ╚═╝╚═╝  ╚═╝╚═════╝   ╚═╝      ╚═╝   ╚══════╝╚══════╝",
]

_SHADYTEL_SMALL = "  s h a d y t e l  —  metropolitan telephone exchange  "

_CRASH_MSGS = [
    "FATAL: Exchange crossbar matrix fault at 0x7F3A2B",
    "PANIC: Ring generator bus timeout — unit 4 silent",
    "ERROR: Supervisor loop overrun (50 ms deadline missed)",
    "ALERT: Memory corruption in call routing table",
    "FAULT: Tone generator phase-lock lost on TRK-3",
    "ERROR: Operator console bus arbitration failure",
    "PANIC: -48V central office battery undervoltage",
    "CRITICAL: DTMF decoder array stuck at 0xFF",
    "FATAL: Strowger selector motor controller silent",
    "ERROR: Billing register overflow — counter wrapped",
    "PANIC: Exchange heartbeat missed ×7 consecutive",
    "ALERT: Cross-connect fabric parity error CE:0x3B",
    "CRITICAL: Junctor group saturated — all busy",
    "FATAL: Routing table checksum mismatch",
    "ERROR: Ground-start supervision loss on POTS port 14",
    "PANIC: Loop-current detect false positive — jack 77",
    "CRITICAL: 2600 Hz trunk seizure detected on TRK-2",
    "FATAL: Software watchdog expired — resetting core…",
]

_CRASH_CODES = [
    "0x0000_DEAD", "EXCH_FAULT_03", "KERN_BUS_ERR",
    "0xC000_021A",  "STOP: 0x0050", "ERR_KERN_HALT",
]


# ── Strings ───────────────────────────────────────────────────────────────────

_TITLES = [
    "SHADYTEL  METROPOLITAN EXCHANGE  NO. 3",
    "SHADYTEL  CENTRAL OFFICE  MAIN BOARD",
    "SHADYTEL  AUTOMATIC SWITCHING CENTRE",
]

_OP_PHRASES = [
    "Number please.",
    "One moment, connecting you now.",
    "I'm sorry, that line is engaged.",
    "Please hold — ringing for you.",
    "Shadytel Exchange, good afternoon.",
    "Go ahead please, you're connected.",
    "Shall I try again in a moment?",
    "Extension forty-two, please hold.",
    "The number you require is ringing.",
    "Connecting trunk line to exchange seven.",
    "I have a call on the board for you.",
    "Your party is on the line now.",
    "I'm afraid there's no answer.",
    "Line engaged — may I take a message?",
    "Thank you for holding. Please go ahead.",
    "Good evening, Shadytel operator.",
    "I'll connect you directly.",
    "Ringing trunk three for you now.",
]

_TRUNK_NAMES = [
    "TRK-1  CENTRAL",
    "TRK-2  OPERATOR",
    "TRK-3  L.DISTANCE",
    "TRK-4  EMERGENCY",
]


# ── Call object ───────────────────────────────────────────────────────────────

class _Call:
    _LABEL_POOL = list("ABCDEFGHJKLMNPQRSTUVWXYZ")

    def __init__(self, a: int, b: int, trunk: bool = False, label: str = "?"):
        self.a       = a
        self.b       = b
        self.trunk   = trunk
        self.label   = label
        self.frames  = 0
        self.duration = random.randint(120, 600)
        self.done    = False

    def update(self) -> None:
        self.frames += 1
        if self.frames >= self.duration:
            self.done = True

    @property
    def elapsed_str(self) -> str:
        s = self.frames // 30
        return f"{s // 60:02d}:{s % 60:02d}"


# ── Scene ─────────────────────────────────────────────────────────────────────

class Switchboard(Scene):
    name = "Switchboard"

    # ── lifecycle ─────────────────────────────────────────────────────────────

    def init(self, renderer, h: int, w: int) -> None:
        self._h = h
        self._w = w
        self._title       = random.choice(_TITLES)
        self._calls:  list[_Call] = []
        self._ringing:  set[int]  = set()
        self._ring_t:   dict[int, int] = {}
        self._used_labels: set[str]   = set()

        self._cursor_gr   = 0
        self._cursor_gc   = 0
        self._selected:   Optional[int] = None   # jack index pending connection

        self._spawn_t     = 0
        self._spawn_rate  = 5    # 1=slow … 10=fast (maps to interval)
        self._blink_t     = 0
        self._blink_on    = True
        self._total_calls = 0

        self._phrase_t    = 0
        self._phrase_int  = random.randint(90, 240)
        self._phrase      = random.choice(_OP_PHRASES)
        self._op_log:     list[str] = []

        self._trunk_busy  = [False] * 4
        self._trunk_t     = [0] * 4

        self._show_labels = True
        self._crashed     = False
        self._crash_t     = 0
        self._crash_log:  list[str] = []
        self._crash_msg_t = 0

        self._bg_plane    : Optional[Plane] = None
        self._grid_plane  : Optional[Plane] = None
        self._wire_plane  : Optional[Plane] = None
        self._hud_plane   : Optional[Plane] = None
        self._crash_plane : Optional[Plane] = None

        self._compute_layout(h, w)
        self._build_planes(h, w)

    def on_resize(self, h: int, w: int) -> None:
        self._h = h
        self._w = w
        self._compute_layout(h, w)
        self._build_planes(h, w)
        # Clamp cursor
        self._cursor_gr = min(self._cursor_gr, self._jrows - 1)
        self._cursor_gc = min(self._cursor_gc, self._jcols - 1)

    def cleanup(self) -> None:
        pass

    # ── layout ────────────────────────────────────────────────────────────────

    def _compute_layout(self, h: int, w: int) -> None:
        """Calculate jack grid dimensions from terminal size."""
        usable_w = w - _INFO_W - 1
        usable_h = h - _HDR_H - 1   # leave 1 for status bar

        self._jcols = max(2, usable_w // _JACK_W)
        self._jrows = max(1, usable_h // _JACK_H)
        self._total = self._jcols * self._jrows

        self._grid_x = 1
        self._grid_y = _HDR_H
        self._info_x = self._grid_x + self._jcols * _JACK_W + 1

    def _build_planes(self, h: int, w: int) -> None:
        self._bg_plane    = Plane(h, w, z=-1)
        self._grid_plane  = Plane(h, w, z=0)
        self._wire_plane  = Plane(h, w, z=1)
        self._hud_plane   = Plane(h, w, z=2)
        self._crash_plane = Plane(h, w, z=5)

    def _jack_screen(self, gr: int, gc: int) -> tuple[int, int]:
        """Top-left (y, x) of jack box at grid position (gr, gc)."""
        return self._grid_y + gr * _JACK_H, self._grid_x + gc * _JACK_W

    def _jack_index(self, gr: int, gc: int) -> int:
        return gr * self._jcols + gc

    def _jack_grid(self, idx: int) -> tuple[int, int]:
        return divmod(idx, self._jcols)

    def _free_label(self) -> str:
        for c in _Call._LABEL_POOL:
            if c not in self._used_labels:
                self._used_labels.add(c)
                return c
        return "?"

    def _release_label(self, lbl: str) -> None:
        self._used_labels.discard(lbl)

    def _occupied(self) -> set[int]:
        occ: set[int] = set()
        for c in self._calls:
            occ.add(c.a)
            occ.add(c.b)
        occ |= self._ringing
        return occ

    # ── update ────────────────────────────────────────────────────────────────

    def update(self, h: int, w: int) -> None:
        if h != self._h or w != self._w:
            self.on_resize(h, w)

        self._blink_t += 1
        if self._blink_t >= 15:
            self._blink_t = 0
            self._blink_on = not self._blink_on

        # Crash tick
        if self._crashed:
            self._crash_t   += 1
            self._crash_msg_t += 1
            interval = max(8, 45 - self._crash_t // 20)
            if self._crash_msg_t >= interval:
                self._crash_msg_t = 0
                msg = random.choice(_CRASH_MSGS)
                self._crash_log.append(msg)
                if len(self._crash_log) > 40:
                    self._crash_log.pop(0)
            self._render_crash(h, w)
            return

        # Phrase rotation
        self._phrase_t += 1
        if self._phrase_t >= self._phrase_int:
            self._phrase_t   = 0
            self._phrase_int = random.randint(90, 240)
            self._phrase     = random.choice(_OP_PHRASES)

        # Trunk timers
        for i in range(4):
            if self._trunk_busy[i]:
                self._trunk_t[i] += 1
                if self._trunk_t[i] > random.randint(180, 600):
                    self._trunk_busy[i] = False
                    self._trunk_t[i]    = 0

        # Update calls
        for c in self._calls[:]:
            c.update()
            if c.done:
                self._calls.remove(c)
                self._release_label(c.label)

        # Ring timers
        for j in list(self._ringing):
            self._ring_t[j] = self._ring_t.get(j, 0) + 1
            if self._ring_t[j] > random.randint(30, 90):
                self._ringing.discard(j)
                self._ring_t.pop(j, None)
                # Sometimes auto-answer a ringing jack
                if random.random() < 0.6:
                    self._try_connect(j)

        # Auto-spawn
        max_calls = max(2, int(self.imap(2, min(14, self._total // 4))))
        interval  = max(4, 50 - self._spawn_rate * 4)
        self._spawn_t += 1
        if self._spawn_t >= interval:
            self._spawn_t = 0
            occ  = self._occupied()
            free = [i for i in range(self._total) if i not in occ]
            if len(free) >= 2 and len(self._calls) < max_calls:
                if random.random() < 0.35:
                    j = random.choice(free)
                    self._ringing.add(j)
                    self._ring_t[j] = 0
                elif random.random() < 0.15 and any(not b for b in self._trunk_busy):
                    # trunk call
                    self._spawn_trunk(random.choice(free))
                else:
                    a, b = random.sample(free, 2)
                    self._connect(a, b)

        # Render
        self._render_bg(h, w)
        self._render_grid(h, w)
        self._render_wires(h, w)
        self._render_hud(h, w)
        self._crash_plane.clear()

    # ── call management ───────────────────────────────────────────────────────

    def _connect(self, a: int, b: int, trunk: bool = False) -> None:
        lbl = self._free_label()
        self._calls.append(_Call(a, b, trunk=trunk, label=lbl))
        self._ringing.discard(a)
        self._ringing.discard(b)
        self._ring_t.pop(a, None)
        self._ring_t.pop(b, None)
        self._total_calls += 1
        gr_a, gc_a = self._jack_grid(a)
        gr_b, gc_b = self._jack_grid(b)
        self._op_log.append(
            f"CONNECT {a+1:03d}↔{b+1:03d}  [{lbl}]"
            + ("  TRUNK" if trunk else "")
        )
        if len(self._op_log) > _LOG_MAX:
            self._op_log.pop(0)

    def _try_connect(self, j: int) -> None:
        occ  = self._occupied()
        free = [i for i in range(self._total) if i not in occ and i != j]
        if free:
            self._connect(j, random.choice(free))

    def _spawn_trunk(self, jack: int) -> None:
        for i in range(4):
            if not self._trunk_busy[i]:
                self._trunk_busy[i] = True
                self._trunk_t[i]    = 0
                self._connect(jack, self._total - 1 - i, trunk=True)
                self._op_log.append(f"TRUNK IN  {_TRUNK_NAMES[i]}")
                return

    def _disconnect_jack(self, idx: int) -> None:
        for c in self._calls[:]:
            if c.a == idx or c.b == idx:
                self._calls.remove(c)
                self._release_label(c.label)
                self._op_log.append(f"DROP      {c.a+1:03d}↔{c.b+1:03d}  [{c.label}]")
        self._ringing.discard(idx)
        self._ring_t.pop(idx, None)

    # ── key handling ──────────────────────────────────────────────────────────

    def on_key(self, key: int) -> bool:
        import curses

        if self._crashed:
            if key in (ord("z"), ord("Z")):
                self._crashed     = False
                self._crash_t     = 0
                self._crash_log.clear()
                self._crash_plane.clear()
            return True

        if key in (ord("w"), ord("W"), curses.KEY_UP):
            self._cursor_gr = max(0, self._cursor_gr - 1)
            return True
        if key in (ord("s"), ord("S"), curses.KEY_DOWN):
            self._cursor_gr = min(self._jrows - 1, self._cursor_gr + 1)
            return True
        if key in (ord("a"), ord("A"), curses.KEY_LEFT):
            self._cursor_gc = max(0, self._cursor_gc - 1)
            return True
        if key in (ord("d"), ord("D"), curses.KEY_RIGHT):
            self._cursor_gc = min(self._jcols - 1, self._cursor_gc + 1)
            return True

        if key in (ord("\n"), ord("\r"), 10, 13):
            idx = self._jack_index(self._cursor_gr, self._cursor_gc)
            if self._selected is None:
                self._selected = idx
            elif self._selected == idx:
                self._selected = None
            else:
                occ = self._occupied()
                if self._selected not in occ and idx not in occ:
                    self._connect(self._selected, idx)
                self._selected = None
            return True

        if key in (ord("r"), ord("R")):
            idx = self._jack_index(self._cursor_gr, self._cursor_gc)
            occ = self._occupied()
            if idx not in occ:
                self._ringing.add(idx)
                self._ring_t[idx] = 0
                self._op_log.append(f"RING      {idx+1:03d}")
            return True

        if key in (ord("x"), ord("X")):
            idx = self._jack_index(self._cursor_gr, self._cursor_gc)
            self._disconnect_jack(idx)
            if self._selected == idx:
                self._selected = None
            return True

        if key in (ord("t"), ord("T")):
            occ  = self._occupied()
            free = [i for i in range(self._total) if i not in occ]
            if free:
                self._spawn_trunk(random.choice(free))
            return True

        if key == ord("["):
            self._spawn_rate = max(1, self._spawn_rate - 1)
            return True
        if key == ord("]"):
            self._spawn_rate = min(10, self._spawn_rate + 1)
            return True

        if key in (ord("g"), ord("G")):
            self._show_labels = not self._show_labels
            return True

        if key in (ord("c"), ord("C")):
            self._crashed     = True
            self._crash_t     = 0
            self._crash_msg_t = 0
            self._crash_log.clear()
            self._crash_log.append(random.choice(_CRASH_MSGS))
            self._op_log.append("*** SYSTEM PANIC ***")
            return True

        return False

    # ── rendering helpers ─────────────────────────────────────────────────────

    def _put_str(self, plane: Plane, y: int, x: int, s: str,
                 fg: Color, bg: Color = BLACK, bold: bool = False,
                 dim: bool = False) -> None:
        for i, ch in enumerate(s):
            if 0 <= y < plane.h and 0 <= x + i < plane.w:
                plane.put_char(y, x + i, ch, fg=fg, bg=bg, bold=bold, dim=dim)

    # ── background ────────────────────────────────────────────────────────────

    def _render_bg(self, h: int, w: int) -> None:
        p = self._bg_plane
        p.clear()
        for r in range(h):
            bg = _HDR_BG if r < _HDR_H else _DARK_BG
            for c in range(w):
                p.put_char(r, c, " ", fg=BLACK, bg=bg)

    # ── header ────────────────────────────────────────────────────────────────

    def _render_header(self, plane: Plane, h: int, w: int) -> None:
        # Top bar
        self._put_str(plane, 0, 0, "▌", fg=_HDR_HL, bg=_HDR_BG, bold=True)
        self._put_str(plane, 0, 1, " SHADYTEL ", fg=_HDR_HL, bg=_HDR_BG, bold=True)
        self._put_str(plane, 0, 11, "metropolitan telephone exchange ",
                      fg=_HDR_FG, bg=_HDR_BG)
        # Divider line
        sep = "─" * (w - 2)
        self._put_str(plane, 1, 1, sep, fg=_BORDER_FG, bg=_HDR_BG)
        # Sub-header: title + stats
        active = len(self._calls)
        ringing = len(self._ringing)
        stat = f"  calls: {active}  ringing: {ringing}  total: {self._total_calls}"
        title_col = max(0, (w // 2 - len(self._title) // 2))
        self._put_str(plane, 2, 2, self._title, fg=_HDR_FG, bg=_HDR_BG)
        self._put_str(plane, 2, 2 + len(self._title), stat,
                      fg=_PANEL_DIM, bg=_HDR_BG)

    # ── jack grid ─────────────────────────────────────────────────────────────

    def _render_grid(self, h: int, w: int) -> None:
        p = self._grid_plane
        p.clear()

        self._render_header(p, h, w)

        active_a = {c.a: c for c in self._calls}
        active_b = {c.b: c for c in self._calls}
        cursor_idx = self._jack_index(self._cursor_gr, self._cursor_gc)

        for gr in range(self._jrows):
            for gc in range(self._jcols):
                idx = self._jack_index(gr, gc)
                ty, tx = self._jack_screen(gr, gc)
                if ty + _BOX_H >= h or tx + _BOX_W >= w:
                    continue

                # Classify jack state
                is_cursor   = (idx == cursor_idx)
                is_selected = (idx == self._selected)
                is_ring     = (idx in self._ringing)
                is_a        = (idx in active_a)
                is_b        = (idx in active_b)
                call        = active_a.get(idx) or active_b.get(idx)
                is_trunk    = call.trunk if call else False

                # Pick colours
                if is_selected:
                    sym, fg, bx = "★", _SELECTED_FG, _SELECTED_BOX
                elif is_cursor and not is_ring and not is_a and not is_b:
                    sym, fg, bx = "◎", _CURSOR_FG, _CURSOR_BOX
                elif is_ring:
                    sym = "◉" if self._blink_on else "○"
                    fg, bx = _RING_FG, _RING_BOX
                elif is_a:
                    sym, fg, bx = ("T" if is_trunk else "●"), _TRUNK_FG if is_trunk else _CONN_A_FG, _TRUNK_BOX if is_trunk else _CONN_A_BOX
                elif is_b:
                    sym, fg, bx = ("T" if is_trunk else "●"), _TRUNK_FG if is_trunk else _CONN_B_FG, _TRUNK_BOX if is_trunk else _CONN_B_BOX
                else:
                    sym, fg, bx = "○", _IDLE_FG, _IDLE_BOX
                    if is_cursor:
                        sym, fg, bx = "◎", _CURSOR_FG, _CURSOR_BOX

                bold = is_selected or is_a or is_b or is_ring

                # Draw box: ┌──┐ / │○ │ / └42┘
                self._put_str(p, ty,   tx, "┌──┐", fg=bx, bg=BLACK)
                self._put_str(p, ty+1, tx, "│", fg=bx, bg=BLACK)
                p.put_char(ty+1, tx+1, sym, fg=fg, bg=BLACK, bold=bold)
                self._put_str(p, ty+1, tx+2, " │", fg=bx, bg=BLACK)

                # Bottom row: label or number
                if call and (is_a or is_b):
                    lbl = call.label
                    self._put_str(p, ty+2, tx, f"└{lbl}─┘", fg=bx, bg=BLACK, bold=True)
                elif self._show_labels:
                    num = f"{idx+1:02d}"[:2]
                    self._put_str(p, ty+2, tx, f"└{num}─┘", fg=_IDLE_BOX, bg=BLACK)
                else:
                    self._put_str(p, ty+2, tx, "└──┘", fg=_IDLE_BOX, bg=BLACK)

    # ── wire / patch-cord rendering ───────────────────────────────────────────

    def _render_wires(self, h: int, w: int) -> None:
        p = self._wire_plane
        p.clear()

        for call in self._calls:
            ra, ca = self._jack_grid(call.a)
            rb, cb = self._jack_grid(call.b)
            ay, ax = self._jack_screen(ra, ca)
            by_, bx = self._jack_screen(rb, cb)

            # Centre x of each jack (1 col from left edge, inside box)
            ax_c = ax + 1
            bx_c = bx + 1

            color = _WIRE_TRUNK_FG if call.trunk else _WIRE_FG

            if ra == rb:
                # Same row: horizontal cord in wire channel below box
                ch_y = ay + _WIRE_ROW
                if ch_y >= h:
                    continue
                xlo, xhi = (ax_c, bx_c) if ax_c < bx_c else (bx_c, ax_c)
                p.put_char(ch_y, xlo, "╰", fg=color, bg=BLACK, bold=True)
                for x in range(xlo + 1, xhi):
                    p.put_char(ch_y, x, "─", fg=color, bg=BLACK)
                p.put_char(ch_y, xhi, "╯", fg=color, bg=BLACK, bold=True)
            else:
                # Different rows: L-route
                # Determine which jack is "upper" (smaller row)
                if ra < rb:
                    uy, ux_c = ay, ax_c   # upper jack
                    ly, lx_c = by_, bx_c  # lower jack
                else:
                    uy, ux_c = by_, bx_c
                    ly, lx_c = ay, ax_c

                ch_y = ly + _WIRE_ROW   # wire channel of lower jack

                # Vertical from upper jack bottom down to lower wire channel
                for y in range(uy + _BOX_H, ch_y + 1):
                    if 0 <= y < h:
                        existing = p.get(y, ux_c)
                        ch = "┼" if existing and existing.char in "─╴╶" else "│"
                        p.put_char(y, ux_c, ch, fg=color, bg=BLACK)

                # Horizontal in lower wire channel
                xlo = min(ux_c, lx_c)
                xhi = max(ux_c, lx_c)
                for x in range(xlo, xhi + 1):
                    if 0 <= ch_y < h and 0 <= x < w:
                        existing = p.get(ch_y, x)
                        if existing and existing.char == "│":
                            p.put_char(ch_y, x, "┼", fg=color, bg=BLACK)
                        else:
                            p.put_char(ch_y, x, "─", fg=color, bg=BLACK)

                # Corner decorations
                if 0 <= ch_y < h:
                    p.put_char(ch_y, ux_c,
                               "╰" if ux_c < lx_c else "╯",
                               fg=color, bg=BLACK, bold=True)
                    p.put_char(ch_y, lx_c,
                               "╯" if ux_c < lx_c else "╰",
                               fg=color, bg=BLACK, bold=True)

        # Ringing jacks get a small shimmer on wire channel
        if self._blink_on:
            for j in self._ringing:
                gr, gc = self._jack_grid(j)
                ty, tx = self._jack_screen(gr, gc)
                ch_y   = ty + _WIRE_ROW
                if 0 <= ch_y < h and 0 <= tx + 1 < w:
                    p.put_char(ch_y, tx + 1, "~", fg=_WIRE_RING_FG, bg=BLACK)

    # ── info panel ────────────────────────────────────────────────────────────

    def _render_hud(self, h: int, w: int) -> None:
        p  = self._hud_plane
        p.clear()
        ix = self._info_x
        if ix >= w - 2:
            return

        def line(y, txt, fg=_PANEL_FG, bold=False, dim=False):
            if 0 <= y < h:
                self._put_str(p, y, ix, txt[:w - ix - 1], fg=fg, bold=bold, dim=dim)

        # Separator column
        for r in range(_HDR_H, h - 1):
            p.put_char(r, ix - 1, "│", fg=_BORDER_FG, bg=BLACK)

        # ── Active calls ──────────────────────────────────────────────────────
        y = _HDR_H
        line(y, "─── ACTIVE CALLS ─────────", fg=_PANEL_SEP)
        y += 1
        if not self._calls:
            line(y, "  (none)", fg=_PANEL_DIM, dim=True)
            y += 1
        else:
            for c in self._calls[:10]:
                fc = _TRUNK_FG if c.trunk else _CALL_A_FG
                bc = _TRUNK_FG if c.trunk else _CALL_B_FG
                tag = "T" if c.trunk else c.label
                elapsed = c.elapsed_str
                txt = f"  [{tag}] {c.a+1:03d}"
                self._put_str(p, y, ix, txt[:w - ix - 1], fg=fc, bold=True)
                mid = f"↔{c.b+1:03d}"
                self._put_str(p, y, ix + len(txt), mid, fg=bc, bold=True)
                tim = f" {elapsed}"
                self._put_str(p, y, ix + len(txt) + len(mid), tim,
                              fg=_CALL_TIME_FG, dim=True)
                y += 1
            if len(self._calls) > 10:
                line(y, f"  … +{len(self._calls)-10} more", fg=_PANEL_DIM, dim=True)
                y += 1

        # ── Ringing ───────────────────────────────────────────────────────────
        y += 1
        line(y, "─── RINGING ──────────────", fg=_PANEL_SEP)
        y += 1
        ring_list = sorted(self._ringing)
        if not ring_list:
            line(y, "  (none)", fg=_PANEL_DIM, dim=True)
            y += 1
        else:
            chunk = ring_list[:6]
            bright = _RING_FG if self._blink_on else _RING_BOX
            nums = "  " + "  ".join(f"{j+1:03d}" for j in chunk)
            line(y, nums, fg=bright, bold=self._blink_on)
            y += 1
            if len(ring_list) > 6:
                line(y, f"  +{len(ring_list)-6} more ringing", fg=_RING_BOX, dim=True)
                y += 1

        # ── Trunk lines ───────────────────────────────────────────────────────
        y += 1
        line(y, "─── TRUNK LINES ──────────", fg=_PANEL_SEP)
        y += 1
        for i, name in enumerate(_TRUNK_NAMES):
            busy   = self._trunk_busy[i]
            status = "BUSY" if busy else "FREE"
            sc     = _TRUNK_FG if busy else _PANEL_DIM
            line(y, f"  {name}  {status}", fg=sc, bold=busy)
            y += 1

        # ── Operator ──────────────────────────────────────────────────────────
        y += 1
        line(y, "─── OPERATOR ─────────────", fg=_PANEL_SEP)
        y += 1
        line(y, f'  "{self._phrase}"', fg=_PANEL_HL, dim=True)
        y += 1

        # ── Activity log ──────────────────────────────────────────────────────
        y += 1
        line(y, "─── ACTIVITY LOG ─────────", fg=_PANEL_SEP)
        y += 1
        log_lines = self._op_log[-(h - y - 2):]
        for entry in log_lines:
            if y >= h - 1:
                break
            fc = _PANEL_DIM if "DROP" in entry else _PANEL_FG
            if "TRUNK" in entry:
                fc = _TRUNK_FG
            if "PANIC" in entry:
                fc = _CRASH_ERR
            line(y, f"  {entry}", fg=fc, dim=("DROP" in entry))
            y += 1

    # ── crash screen ──────────────────────────────────────────────────────────

    def _render_crash(self, h: int, w: int) -> None:
        # Yellow background on bg_plane
        p = self._bg_plane
        p.clear()
        for r in range(h):
            for c in range(w):
                p.put_char(r, c, " ", fg=BLACK, bg=_CRASH_BG)

        # Clear other planes
        self._grid_plane.clear()
        self._wire_plane.clear()
        self._hud_plane.clear()

        # Draw crash content on crash_plane
        cp = self._crash_plane
        cp.clear()

        def cstr(y, x, s, fg=_CRASH_DARK, bold=False):
            self._put_str(cp, y, x, s, fg=fg, bg=_CRASH_BG, bold=bold)

        # Scanline flicker at top based on crash age
        for r in range(min(3, h)):
            flicker = _CRASH_BG.lerp(_CRASH_DARK, 0.05 * (self._crash_t % 8))
            for c in range(w):
                cp.put_char(r, c, " ", fg=BLACK, bg=flicker)

        # ── Logo block ────────────────────────────────────────────────────────
        logo_h   = len(_LOGO) + len(_SHADYTEL_BIG) + 4
        logo_w   = max(len(ln) for ln in _LOGO + _SHADYTEL_BIG)
        logo_y   = max(1, (h // 2 - logo_h // 2) - 2)
        logo_x   = max(1, w // 2 - logo_w // 2 - 10)

        for i, ln in enumerate(_LOGO):
            cstr(logo_y + i, logo_x, ln, fg=_CRASH_DARK, bold=True)

        ty = logo_y + len(_LOGO) + 1
        for i, ln in enumerate(_SHADYTEL_BIG):
            if ty + i < h:
                cstr(ty + i, logo_x, ln, fg=_CRASH_DARK, bold=True)

        sub_y = ty + len(_SHADYTEL_BIG) + 1
        if sub_y < h:
            sx = max(0, w // 2 - len(_SHADYTEL_SMALL) // 2 - 10)
            cstr(sub_y, sx, _SHADYTEL_SMALL, fg=_CRASH_MID)

        # ── Error log (right column) ──────────────────────────────────────────
        log_x  = min(w - 44, logo_x + logo_w + 4)
        log_y0 = 2
        cstr(log_y0, log_x, "! SHADYTEL EXCHANGE PANIC REPORT",
             fg=_CRASH_ERR, bold=True)
        cstr(log_y0 + 1, log_x, "  " + "─" * 30, fg=_CRASH_DARK)

        visible = self._crash_log[-(h - log_y0 - 8):]
        for i, msg in enumerate(visible):
            ry = log_y0 + 2 + i
            if ry >= h - 4:
                break
            fc = _CRASH_ERR if any(w in msg for w in ("FATAL", "PANIC", "CRITICAL")) \
                 else _CRASH_DARK
            cstr(ry, log_x, f"  {msg}", fg=fc)

        # Blinking error code at bottom
        if self._blink_on:
            code = _CRASH_CODES[self._crash_t // 30 % len(_CRASH_CODES)]
            bottom_msg = f"  STOP: {code}  —  press Z to recover  "
            bx = max(0, w // 2 - len(bottom_msg) // 2)
            for c in range(w):
                cp.put_char(h - 2, c, " ", fg=BLACK, bg=_CRASH_DARK)
            cstr(h - 2, bx, bottom_msg, fg=_CRASH_BG, bold=True)

    # ── planes / status ───────────────────────────────────────────────────────

    def planes(self) -> list[Plane]:
        out = [self._bg_plane, self._grid_plane,
               self._wire_plane, self._hud_plane]
        if self._crashed:
            out.append(self._crash_plane)
        return out

    @property
    def status_extras(self) -> str:
        if self._crashed:
            return "  !! SYSTEM PANIC !!  z:recover"
        sel = f"  sel:{self._selected+1:03d}" if self._selected is not None else ""
        return (f"  wasd move  Enter select{sel}"
                f"  r:ring  x:drop  t:trunk"
                f"  [/] rate:{self._spawn_rate}"
                f"  g:labels  c:PANIC")

    @property
    def status_color(self) -> Color:
        return _CRASH_ERR if self._crashed else Color(60, 100, 160)
