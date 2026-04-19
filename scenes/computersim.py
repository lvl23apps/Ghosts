"""ComputerSim — retro terminal system simulator.

Simulates ten historical computer systems, each with authentic banner text,
a session of commands and output, crash/recovery states, and colour themes.

Scene-specific controls:
  n / b        next / previous system
  o / p        colour theme: AUTHENTIC / PHOSPHOR / PAPER / NIGHT
  [ / ]        typing speed ×0.25 – ×4.0, step 0.25
  c            crash / recover current system
  r            toggle random mode (extra timing/content randomness)
"""

from __future__ import annotations

import random
from typing import Optional

from renderer import Plane, Color, BLACK, WHITE
from scene_base import Scene


# ── Speed / theme limits ──────────────────────────────────────────────────────

_SPD_MIN  = 0.25
_SPD_MAX  = 4.0
_SPD_STEP = 0.25

_THEMES = ["AUTHENTIC", "PHOSPHOR", "PAPER", "NIGHT"]


def _apply_theme(theme: str, system_colors: dict) -> dict:
    if theme == "PHOSPHOR":
        def g(v): return Color(0, v, 0)
        return {
            "prompt": g(220), "output": g(160), "banner": g(200),
            "header": g(255), "dim": g(80), "crash": Color(255, 80, 0),
        }
    elif theme == "PAPER":
        def a(v): return Color(v, int(v * 0.65), 0)
        return {
            "prompt": a(255), "output": a(200), "banner": a(230),
            "header": a(255), "dim": a(140), "crash": Color(255, 50, 0),
        }
    elif theme == "NIGHT":
        return {
            "prompt": Color(200, 220, 255), "output": Color(160, 180, 220),
            "banner": Color(180, 200, 240), "header": Color(220, 240, 255),
            "dim": Color(80, 100, 140), "crash": Color(255, 100, 100),
        }
    else:
        return system_colors


def _line_color(line: str, data: dict, colors: dict):
    """Return (Color, bold) for a rendered line."""
    prompt = data.get("prompt", "")
    if prompt and line.startswith(prompt):
        return colors["prompt"], True
    if line.startswith(("%", "!", "?", "panic", "PANIC", "Error", "ERROR",
                         "Abort", "BUGCHECK", "SYSTEM-", "UNICOS",
                         "Stack overflow", "Segmentation", "Bus error",
                         "Memory fault", "cpu0:", "cpu halted")):
        return colors["crash"], True
    if any(kw in line for kw in (
        "Copyright", "Version", "Welcome", "CRAY", "VAX", "UNIX",
        "Windows", "Plan 9", "MacsBug", "Sun ", "TOPS-20", "Floodgap",
        "MS-DOS", "MacsBug", "UNICOS", "SunOS", "Gopher",
    )):
        return colors["banner"], False
    if ("---" in line or "===" in line or "┌" in line or "└" in line
            or "╔" in line or "╚" in line or "════" in line or "────" in line):
        return colors["header"], False
    return colors["output"], False


# ── State machine constants ───────────────────────────────────────────────────

_ST_BIOS    = "bios"     # MSDOS-only: rapid BIOS text before banner
_ST_BANNER  = "banner"
_ST_PROMPT  = "prompt"
_ST_TYPING  = "typing"
_ST_OUTPUT  = "output"
_ST_CRASH   = "crash"
_ST_DONE    = "done"

# Ticks (at speed 1.0 = 2 ticks/frame = ~60 ticks/sec)
_PROMPT_PAUSE  = 45   # ticks before starting to type
_CHAR_TICKS    = 3    # ticks per character typed
_LINE_PAUSE    = 30   # ticks between output lines
_BANNER_PAUSE  = 4    # ticks per banner line
_CURSOR_BLINK  = 20   # ticks per cursor blink cycle


class _TermSim:
    """State-machine terminal simulator for one historical system."""

    def __init__(self, data: dict):
        self.data = data
        self._scrollback: list[str] = []
        self._state     = _ST_BANNER
        self._banner_idx = 0
        self._banner_tick = 0
        self._session_idx = 0
        self._cmd_char    = 0
        self._out_idx     = 0
        self._out_tick    = 0
        self._prompt_tick = 0
        self._type_tick   = 0
        self._tick_count  = 0
        self._bios_idx    = 0
        self._bios_tick   = 0
        self._crashed     = False

        if data.get("bios_lines"):
            self._state = _ST_BIOS

    def reset(self):
        self._scrollback.clear()
        self._state       = _ST_BIOS if self.data.get("bios_lines") else _ST_BANNER
        self._banner_idx  = 0
        self._banner_tick = 0
        self._session_idx = 0
        self._cmd_char    = 0
        self._out_idx     = 0
        self._out_tick    = 0
        self._prompt_tick = 0
        self._type_tick   = 0
        self._tick_count  = 0
        self._bios_idx    = 0
        self._bios_tick   = 0
        self._crashed     = False

    def crash(self):
        self._crashed = True
        self._state   = _ST_CRASH
        self._scrollback.clear()

    def recover(self):
        self._crashed = False
        self.reset()

    def tick(self, speed_mult: float = 1.0, random_mode: bool = False):
        """Advance one tick. Called ticks_per_frame times per frame."""
        self._tick_count += 1
        spd = max(1, speed_mult)

        if self._crashed or self._state == _ST_CRASH:
            return

        # ── BIOS phase (MSDOS) ────────────────────────────────────────────────
        if self._state == _ST_BIOS:
            bios = self.data.get("bios_lines", [])
            self._bios_tick += 1
            delay = max(1, int(2 / spd))
            if self._bios_tick >= delay:
                self._bios_tick = 0
                if self._bios_idx < len(bios):
                    line = bios[self._bios_idx]
                    if random_mode and self._bios_idx > 5:
                        # occasionally double a hex count line
                        line = line
                    self._scrollback.append(line)
                    self._bios_idx += 1
                else:
                    self._state     = _ST_BANNER
                    self._banner_idx = 0
            return

        # ── BANNER phase ──────────────────────────────────────────────────────
        if self._state == _ST_BANNER:
            banner = self.data.get("banner", [])
            self._banner_tick += 1
            pause = self.data.get("banner_pause", _BANNER_PAUSE)
            delay = max(1, int(pause / spd))
            if self._banner_tick >= delay:
                self._banner_tick = 0
                if self._banner_idx < len(banner):
                    self._scrollback.append(banner[self._banner_idx])
                    self._banner_idx += 1
                else:
                    self._state       = _ST_PROMPT
                    self._prompt_tick = 0
                    self._session_idx = 0
                    self._cmd_char    = 0
            return

        # ── PROMPT pause ──────────────────────────────────────────────────────
        if self._state == _ST_PROMPT:
            self._prompt_tick += 1
            delay = max(1, int(_PROMPT_PAUSE / spd))
            if random_mode:
                delay += random.randint(-10, 10)
            if self._prompt_tick >= delay:
                self._state     = _ST_TYPING
                self._type_tick = 0
                self._cmd_char  = 0
            return

        # ── TYPING phase ──────────────────────────────────────────────────────
        if self._state == _ST_TYPING:
            session = self.data.get("session", [])
            if self._session_idx >= len(session):
                # Loop back
                self._scrollback.append("")
                self._state       = _ST_BANNER
                self._banner_idx  = 0
                self._banner_tick = 0
                return

            cmd, _out = session[self._session_idx]
            self._type_tick += 1
            delay = max(1, int(_CHAR_TICKS / spd))
            if random_mode:
                delay = max(1, delay + random.randint(-1, 1))
            if self._type_tick >= delay:
                self._type_tick = 0
                self._cmd_char += 1
                if self._cmd_char > len(cmd):
                    # Command fully typed — emit it as a scrollback line
                    prompt = self.data.get("prompt", "")
                    self._scrollback.append(prompt + cmd)
                    self._state   = _ST_OUTPUT
                    self._out_idx = 0
                    self._out_tick = 0
            return

        # ── OUTPUT phase ──────────────────────────────────────────────────────
        if self._state == _ST_OUTPUT:
            session = self.data.get("session", [])
            _cmd, out_lines = session[self._session_idx]
            self._out_tick += 1
            delay = max(1, int(_LINE_PAUSE / spd))
            if random_mode:
                delay = max(1, delay + random.randint(-5, 5))
            if self._out_tick >= delay:
                self._out_tick = 0
                if self._out_idx < len(out_lines):
                    self._scrollback.append(out_lines[self._out_idx])
                    self._out_idx += 1
                    if random_mode and self._out_idx < len(out_lines):
                        # occasionally skip a blank
                        pass
                else:
                    self._session_idx += 1
                    self._cmd_char    = 0
                    self._state       = _ST_PROMPT
                    self._prompt_tick = 0
            return

    def _current_typing_line(self) -> str:
        """Return the partially typed command line (for display)."""
        if self._state != _ST_TYPING:
            return ""
        session = self.data.get("session", [])
        if self._session_idx >= len(session):
            return ""
        cmd, _ = session[self._session_idx]
        prompt  = self.data.get("prompt", "")
        partial = cmd[:self._cmd_char]
        return prompt + partial

    def render(self, plane: Plane, h: int, w: int, theme: str):
        data   = self.data
        colors = _apply_theme(theme, data["colors"])

        if self._state == _ST_CRASH or self._crashed:
            crash_bg   = data.get("crash_bg", BLACK)
            crash_lines = data.get("crash_lines", [])
            crash_color = colors["crash"]

            # Fill background for BSOD-style crashes
            if crash_bg != BLACK:
                for row in range(h - 1):
                    for col in range(w):
                        plane.put_char(row, col, " ", fg=WHITE, bg=crash_bg)

            # Render crash lines centered vertically
            start_row = max(0, (h - len(crash_lines)) // 2 - 1)
            for i, line in enumerate(crash_lines):
                row = start_row + i
                if row >= h - 1:
                    break
                fg = WHITE if crash_bg != BLACK else crash_color
                bg = crash_bg
                col = 0
                for ci, ch in enumerate(line[:w]):
                    plane.put_char(row, col + ci, ch, fg=fg, bg=bg, bold=(crash_bg != BLACK))
            return

        # Normal rendering — scrollback + typing line
        scrollback = list(self._scrollback)
        typing_line = self._current_typing_line()
        if typing_line or self._state in (_ST_PROMPT, _ST_TYPING):
            display_lines = scrollback + [typing_line]
        else:
            display_lines = scrollback

        # Show at most h-2 lines, bottom-aligned
        visible = display_lines[-(h - 2):]

        for i, line in enumerate(visible):
            row = i
            if row >= h - 1:
                break
            fg, bold = _line_color(line, data, colors)
            for ci, ch in enumerate(line[:w]):
                plane.put_char(row, ci, ch, fg=fg, bg=BLACK, bold=bold)

        # Blinking cursor on typing line
        if self._state in (_ST_PROMPT, _ST_TYPING):
            cursor_on = (self._tick_count // _CURSOR_BLINK) % 2 == 0
            if cursor_on:
                typing_row = len(visible) - 1
                if typing_row < h - 1:
                    cursor_col = len(typing_line)
                    if cursor_col < w:
                        plane.put_char(typing_row, cursor_col, "_",
                                       fg=colors["prompt"], bg=BLACK, bold=True)


# ── System data ───────────────────────────────────────────────────────────────

_MAC_OS = _TermSim({
    "name": "Mac OS 7.6",
    "prompt": "MacsBug> ",
    "banner": [
        "",
        "MacsBug 6.6.3  \u00a9 Apple Computer, Inc.  1995",
        "System 7.6 on Macintosh Quadra 840AV",
        "",
        "Bus Error at 0006FBC4",
        "",
        "    PC  0006FBC4  SR 2700        A7 4082FBC0",
        "    D0 00000040  D1 00000000  D2 12345678  D3 00000000",
        "    D4 0006FBD0  D5 0006FC00  D6 00000000  D7 0006FB00",
        "    A0 0000C000  A1 00003F10  A2 0006FBD4  A3 0000C020",
        "    A4 FFFFFFFF  A5 00280000  A6 4082FEFC",
        "",
        "  0006FBC4  2C00   move.l  D0,D6",
        "  0006FBC6  6658   bne.s   $0006FC20",
        "",
    ],
    "session": [
        ("ip", [
            "  PC: 0006FBC4  _BlockMove+$001C",
            "  SP: 4082FBC0  (main task stack)",
            "",
        ]),
        ("il", [
            "  0006FBB0  41EE FFD4   lea    -$002C(A6),A0",
            "  0006FBB4  2F08        move.l A0,-(A7)",
            "  0006FBB6  A02E        _BlockMove",
            "  0006FBB8  2C00        move.l D0,D6",
            "=> 0006FBC4  2C00        move.l D0,D6",
            "  0006FBC6  6658        bne.s  $0006FC20",
            "",
        ]),
        ("dm 0x4082FBC0", [
            "  4082FBC0: 0006 FC00 0000 0040 0000 0000 1234 5678",
            "  4082FBD0: 0006 FBD0 0006 FC00 0000 0000 0006 FB00",
            "  4082FBE0: 0000 C000 0000 3F10 0006 FBD4 0000 C020",
            "",
        ]),
        ("wh 0x0000C000", [
            "  0x0000C000 is a handle.",
            "  Master pointer at 0x0000C000",
            "  Locked: No    Purgeable: Yes    Resource: Yes",
            "  Size: 1024 bytes   Type: 'CODE'  ID: 1",
            "",
        ]),
        ("es", [
            "  Stack frame at A6=4082FEFC",
            "  Return addr: 00289A44 in 'Main':DoEvent+$0098",
            "  Local vars:  24 bytes",
            "  4082FECC: 00289A44 00000001 00000000 0006FBC4",
            "",
        ]),
        ("g", [
            "",
            "  Continuing execution from 0006FBC4...",
            "",
        ]),
    ],
    "crash_lines": [
        "",
        "  Sorry, a system error occurred.",
        "",
        "  ID=11 (Hardware Exception)",
        "",
        "  To continue, click Restart.",
        "  To see the technical information, use MacsBug.",
        "",
        "  \u250c\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2510",
        "  \u2502  \u261b  Sorry, a system error occurred. \u2502",
        "  \u2502     ID = 11   Hardware Exception    \u2502",
        "  \u2502                                     \u2502",
        "  \u2502  [  Resume  ]    [  Restart  ]      \u2502",
        "  \u2514\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2518",
    ],
    "crash_bg": BLACK,
    "colors": {
        "prompt": Color(200, 200, 200),
        "output": Color(180, 180, 180),
        "banner": Color(220, 220, 220),
        "header": Color(255, 255, 255),
        "dim":    Color(120, 120, 120),
        "crash":  Color(220, 220, 220),
    },
})

_CRAY = _TermSim({
    "name": "Cray UNICOS",
    "prompt": "% ",
    "banner": [
        "",
        "  \u2554\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2557",
        "  \u2551  CRAY X-MP/416  UNICOS 9.0.2.3                       \u2551",
        "  \u2551  National Center for Atmospheric Research             \u2551",
        "  \u2551  Hostname: cray-xmp.ncar.edu    Uptime: 112 days      \u2551",
        "  \u255a\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u255d",
        "",
        "  WARNING: Authorised users only. All activity is logged.",
        "",
    ],
    "session": [
        ("uname -a", [
            "UNICOS 9.0.2.3 cray-xmp cray CRAY X-MP/416 09/30/93",
            "",
        ]),
        ("qstat -a", [
            "",
            "Job ID   Name             User       Nodes CPUs  Walltime  Status",
            "-------- ---------------- ---------- ----- ----- --------- ------",
            "5823     climate_v3       johnson        4    64  48:00:00  R",
            "5891     md_protein       chen           2    32  12:00:00  R",
            "5924     fft_benchmark    system         1    16  00:10:00  R",
            "5931     atmosphere_sim   matsuda        4    64  72:00:00  Q",
            "5934     ocean_model_v7   rodriguez      4    64  48:00:00  Q",
            "5940     plasma_dynamics  volkov         2    32  24:00:00  Q",
            "",
        ]),
        ("showflops", [
            "",
            "CRAY X-MP/416 Performance Monitor",
            "----------------------------------",
            "Peak theoretical:   8192.0 Mflops/s",
            "Current aggregate:  7841.3 Mflops/s  (95.7%)",
            "",
            "  CPU 0:   1972.4 Mflops/s  [ climate_v3    ]",
            "  CPU 1:   1965.1 Mflops/s  [ climate_v3    ]",
            "  CPU 2:   1958.8 Mflops/s  [ md_protein    ]",
            "  CPU 3:   1945.0 Mflops/s  [ fft_benchmark ]",
            "",
        ]),
        ("cf77 -O3 -Wf'-dp' ocean_model.f90 -o ocean.x", [
            "cf77: CRAY Fortran 5.0.3.3",
            "ocean_model.f90:",
            "   PROGRAM OCEAN_MODEL  -- vectorising...",
            "   SUBROUTINE ADVECT    -- vectorising...",
            "   SUBROUTINE DIFFUSE   -- vectorising...",
            "   SUBROUTINE PRESSURE  -- vectorising...",
            "Vectorisation complete. 847/852 loops vectorised (99.4%)",
            "Link complete. ocean.x: 4,194,304 bytes",
            "",
        ]),
        ("qsub ocean_run.job", [
            "Job 5950 submitted to queue 'batch'.",
            "Estimated start: within 2 hours.",
            "",
        ]),
    ],
    "crash_lines": [
        "",
        "UNICOS kernel panic: machine check",
        "",
        "CPU 2: double-bit ECC error",
        "Address: 0x0000000048A3FC00",
        "Fatal memory error -- system cannot continue",
        "",
        "%SYSTEM-PANIC: Hardware memory fault",
        "Initiating emergency shutdown...",
        "Core dump written to /var/adm/crash/vmcore.0",
        "",
        "System halted. Contact system administrator.",
    ],
    "crash_bg": BLACK,
    "colors": {
        "prompt": Color(0, 200, 255),
        "output": Color(160, 220, 255),
        "banner": Color(100, 200, 255),
        "header": Color(0, 255, 255),
        "dim":    Color(40, 100, 150),
        "crash":  Color(255, 80, 80),
    },
})

_MSDOS_BIOS = [
    "Award Modular BIOS v4.51PG, An Energy Star Ally",
    "Copyright (C) 1984-96, Award Software, Inc.",
    "",
    "ASUS P/I-P55T2P4 ACPI BIOS Revision 0105",
    "",
    "Testing memory... ",
    "  640K OK",
    "  1024K OK",
    "  2048K OK",
    "  4096K OK",
    "  8192K OK",
    " 16384K OK",
    " 32768K OK",
    "Memory test OK: 32768K",
    "",
    "Detecting primary master IDE... WDC AC31600H (1.6 GB)",
    "Detecting primary slave  IDE... ATAPI CDROM 24X",
    "Detecting secondary master... None",
    "Detecting secondary slave ... None",
    "",
    "Award Plug and Play BIOS Extension v1.0A",
    "Initialising PnP cards...",
    "  IRQ 5: Sound Blaster 16",
    "  IRQ 10: 3Com EtherLink III",
    "",
    "Starting MS-DOS...",
    "",
    "HIMEM is testing extended memory...",
    "HIMEM: DOS XMS driver, version 3.09 - 11/01/94",
    "        Extended Memory Specification (XMS) Version 3.0",
    "        Copyright 1988-1993 Microsoft Corp.",
    "SmartDrive Cache version 5.1 installed.",
    "Mouse Systems Mouse driver version 8.20",
    "",
    "C:\\>",
]

_MSDOS = _TermSim({
    "name": "MS-DOS 6.22",
    "prompt": "C:\\>",
    "bios_lines": _MSDOS_BIOS,
    "banner": [],
    "banner_pause": 5,
    "session": [
        ("VER", [
            "",
            "MS-DOS Version 6.22",
            "",
        ]),
        ("DIR /W", [
            " Volume in drive C is MS-DOS_622",
            " Volume Serial Number is 1A2B-3C4D",
            " Directory of C:\\",
            "",
            "[WINDOWS]  [GAMES]    [DOS]      [TEMP]",
            "AUTOEXEC BAT   CONFIG   SYS   COMMAND  COM",
            "IO       SYS   MSDOS    SYS   HIMEM    SYS",
            "       8 file(s)        174,211 bytes",
            "               1,047,552 bytes free",
            "",
        ]),
        ("TYPE AUTOEXEC.BAT", [
            "@ECHO OFF",
            "PROMPT $P$G",
            "PATH C:\\DOS;C:\\WINDOWS;C:\\GAMES",
            "SET TEMP=C:\\TEMP",
            "SET BLASTER=A220 I5 D1 H5 P330 T6",
            "LH C:\\DOS\\SMARTDRV.EXE 2048",
            "LH C:\\DOS\\MOUSE.COM /Y",
            "",
        ]),
        ("MEM", [
            "",
            "Memory Type    Total  =  Used  +  Free",
            "-----------  -------   -------   -------",
            "Conventional   640K  =   91K  +   549K",
            "Upper          155K  =   47K  +   108K",
            "Extended (XMS) 31,744K = 2,048K + 29,696K",
            "Total memory 32,539K = 2,186K + 30,353K",
            "",
            "Largest executable program size  549K",
            "",
        ]),
        ("SCANDISK C: /AUTOFIX", [
            "",
            "Microsoft ScanDisk",
            "",
            "ScanDisk is now checking the following areas of drive C:",
            "  Media descriptor               OK",
            "  File allocation tables         OK",
            "  Directory structure            OK",
            "  File system                    OK",
            "  Surface scan ...",
            "  Cluster 1024 of 2048 ...",
            "",
        ]),
        ("DEFRAG C: /F", [
            "",
            "Microsoft Defrag",
            "Optimising drive C...",
            "[\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2591\u2591\u2591\u2591\u2591\u2591\u2591\u2591\u2591\u2591\u2591\u2591\u2591] 45%",
            "",
            "Method: Full Optimisation",
            "Clusters processed: 462 of 1024",
            "",
        ]),
    ],
    "crash_lines": [
        "",
        "General failure reading drive C",
        "Abort, Retry, Fail?",
        "",
        "Not ready reading drive C",
        "Abort, Retry, Fail?",
        "",
        "General failure error reading drive C",
        "Abort, Retry, Fail?",
        "",
        "Stack overflow - System halted",
        "Press Ctrl-Alt-Del to restart",
    ],
    "crash_bg": BLACK,
    "colors": {
        "prompt": Color(160, 160, 160),
        "output": Color(180, 180, 180),
        "banner": Color(0, 200, 200),
        "header": Color(220, 220, 220),
        "dim":    Color(100, 100, 100),
        "crash":  Color(255, 200, 0),
    },
})

_WINDOWS = _TermSim({
    "name": "Windows 95",
    "prompt": "C:\\WINDOWS>",
    "banner": [
        "",
        "Microsoft Windows 95",
        "Copyright Microsoft Corporation 1981-1995",
        "",
        "C:\\WINDOWS>",
    ],
    "session": [
        ("ver", [
            "",
            "Windows 95 [Version 4.00.950]",
            "",
        ]),
        ("dir /w c:\\", [
            " Volume in drive C is WIN95",
            " Volume Serial Number is 2C3D-4E5F",
            " Directory of C:\\",
            "",
            "[WINDOWS]  [PROGRA~1]  [GAMES]   [TEMP]    [DOS]",
            "AUTOEXEC BAT   CONFIG   SYS   COMMAND  COM",
            "IO       SYS   MSDOS    SYS   WIN      COM",
            "       9 file(s)        312,441 bytes",
            "               2,097,152 bytes free",
            "",
        ]),
        ("mem /c /p", [
            "",
            "Modules using memory below 1 MB:",
            "",
            "  Name         Total    Conventional  Upper Memory",
            "  --------  --------   ------------  ------------",
            "  SYSTEM      16,400         16,400            0",
            "  HIMEM        1,120          1,120            0",
            "  IFSHLP        2,864          2,864            0",
            "  COMMAND       7,616          7,616            0",
            "  Free        611,744        611,744            0",
            "",
            "Total FREE:   611,744",
            "",
        ]),
        ("scandisk c: /autofix /nosummary", [
            "",
            "Microsoft ScanDisk",
            "",
            "ScanDisk is now checking drive C.",
            "  Media descriptor           OK",
            "  File allocation tables     OK",
            "  Directory structure        OK",
            "  File system                OK",
            "  Surface scan ...",
            "  [\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2588\u2591\u2591\u2591\u2591\u2591\u2591\u2591\u2591\u2591\u2591\u2591\u2591\u2591\u2591\u2591] 60%",
            "  ScanDisk found no problems on drive C.",
            "",
        ]),
        ("msconfig", [
            "  Microsoft System Configuration Utility",
            "  Checking startup items...",
            "  WIN.INI   - 4 entries",
            "  SYSTEM.INI - 6 entries",
            "  Autoexec.bat - 7 entries",
            "  Config.sys   - 5 entries",
            "  Startup group: 3 programs",
            "",
        ]),
    ],
    "crash_lines": [
        "",
        "Windows",
        "",
        "     A fatal exception 0E has occurred at 0028:C0011E36 in VxD VMM(01) +",
        "     00010E36. The current application will be terminated.",
        "",
        "  *  Press any key to terminate the current application.",
        "  *  Press CTRL+ALT+DEL again to restart your computer. You will",
        "     lose any unsaved information in all applications.",
        "",
        "                          Press any key to continue _",
    ],
    "crash_bg": Color(0, 0, 170),
    "colors": {
        "prompt": Color(200, 200, 200),
        "output": Color(180, 180, 180),
        "banner": Color(120, 180, 255),
        "header": Color(220, 220, 220),
        "dim":    Color(100, 100, 100),
        "crash":  Color(255, 255, 255),
    },
})

_SOLARIS = _TermSim({
    "name": "Solaris 2.6",
    "prompt": "root@sunfire# ",
    "banner": [
        "",
        "Sun Microsystems Inc.   SunOS 5.6       Generic August 1997",
        "",
        "Sun Ultra 2 -- 2 x UltraSPARC-II @ 300MHz -- 512 MB RAM",
        "",
    ],
    "session": [
        ("uname -a", [
            "SunOS sunfire 5.6 Generic_105181-05 sun4u sparc SUNW,Ultra-2",
            "",
        ]),
        ("prstat 1 3", [
            "   PID USERNAME  SIZE   RSS STATE  PRI NICE      TIME  CPU PROCESS/NLWP",
            "   283 root     7984K 5680K sleep   58    0   0:00:02 0.4% sendmail/1",
            "   112 root     3520K 2144K sleep   58    0   0:00:00 0.2% syslogd/1",
            "     1 root     1040K  640K sleep   58    0   0:00:00 0.0% init/1",
            " Total: 42 processes, 58 lwps, load averages: 0.04, 0.02, 0.01",
            "",
        ]),
        ("prtconf | head -20", [
            "System Configuration:  Sun Microsystems  sun4u",
            "Memory size: 512 Megabytes",
            "System Peripherals (Software Nodes):",
            "",
            "SUNW,Ultra-2",
            "    packages (driver not attached)",
            "    chosen (driver not attached)",
            "    openprom (driver not attached)",
            "    options, instance #0",
            "    aliases (driver not attached)",
            "    memory (driver not attached)",
            "    virtual-memory (driver not attached)",
            "    SUNW,UltraSPARC-II, instance #0",
            "    SUNW,UltraSPARC-II, instance #1",
            "",
        ]),
        ("df -k", [
            "Filesystem            kbytes    used   avail capacity  Mounted on",
            "/dev/dsk/c0t0d0s0    1023398  408112  564053    42%    /",
            "/dev/dsk/c0t0d0s6    2046784  987220 1059564    49%    /usr",
            "/dev/dsk/c0t1d0s7    4093270 1843024 2291050    45%    /export/home",
            "swap                  524288   12448  511840     3%    /tmp",
            "",
        ]),
        ("showrev -p | head -10", [
            "Patch: 105181-05 Obsoletes:  Requires:  Incompatibles:  Packages: SUNWcsr",
            "Patch: 105210-12 Obsoletes:  Requires:  Incompatibles:  Packages: SUNWcsr",
            "Patch: 105568-07 Obsoletes:  Requires:  Incompatibles:  Packages: SUNWcsr",
            "Patch: 106040-09 Obsoletes:  Requires:  Incompatibles:  Packages: SUNWcsr",
            "Patch: 106285-02 Obsoletes:  Requires:  Incompatibles:  Packages: SUNWcsr",
            "",
        ]),
        ("truss -c ls /usr/bin 2>&1 | tail -8", [
            "syscall               seconds   calls  errors",
            "open                    0.000      12       0",
            "read                    0.000       6       0",
            "write                   0.001       1       0",
            "stat64                  0.003     214       0",
            "getdents64              0.000       8       0",
            "",
            "sys totals:             0.006     267       0",
            "",
        ]),
    ],
    "crash_lines": [
        "",
        "panic: kernel trap (unexpected level 15 interrupt)",
        "syncing file systems... done",
        "",
        "{0} ok",
        "",
        "Type  'boot'  and press Return to start up the system.",
        "Type  'go'    and press Return to resume (may not work).",
        "",
        "ok _",
    ],
    "crash_bg": BLACK,
    "colors": {
        "prompt": Color(255, 165, 0),
        "output": Color(220, 220, 180),
        "banner": Color(255, 200, 100),
        "header": Color(255, 220, 0),
        "dim":    Color(150, 100, 0),
        "crash":  Color(255, 100, 0),
    },
})

_VAX = _TermSim({
    "name": "VAX/VMS 5.4",
    "prompt": "$ ",
    "banner": [
        "",
        "        VAX/VMS Version V5.4  on node VAXSRV",
        "",
        "  Welcome to Digital Equipment Corporation VAX/VMS",
        "  Copyright (c) 1988 Digital Equipment Corporation",
        "",
        "  Username: SMITH",
        "  Password:",
        "",
        "   Last interactive login on Friday, 03-AUG-1990 14:12:44.53",
        "   Last non-interactive login on Thursday, 02-AUG-1990 09:03:17.26",
        "",
        "  You have 3 new mail messages.",
        "",
        "$ ",
    ],
    "session": [
        ("SHOW SYSTEM", [
            "VAX/VMS V5.4  on node VAXSRV  3-AUG-1990 14:20:17.34",
            "Uptime  3 17:24:36",
            " Pid    Process Name    State  Pri      I/O       CPU       Page flts  Pages",
            "000000A4 SWAPPER          HIB   16          0   0 00:00:00.00         0      0",
            "000000AC ERRFMT           HIB    8         13   0 00:00:00.05         0     82",
            "000000AE CACHE_SERVER      HIB   16         18   0 00:00:00.08         0    120",
            "000000B2 NETACP           HIB   10        482   0 00:00:00.52         0    306",
            "000000C0 SMITH            CUR    4       1234   0 00:00:02.34        45    128",
            "",
        ]),
        ("DIR SYS$LOGIN:", [
            "",
            "Directory SYS$SYSROOT:[SMITH]",
            "",
            "LOGIN.COM;1         MAIL.MAI;1          REPORT.TXT;3",
            "PROGRAM.FOR;1       RUNFILE.COM;2        OUTPUT.LIS;4",
            "",
            "Total of 6 files.",
            "",
        ]),
        ("TYPE REPORT.TXT", [
            "",
            "Monthly Performance Report - August 1990",
            "=========================================",
            "System: VAXSRV   Node: VAXCLUSTER",
            "CPU Utilisation: 34.2%",
            "Memory: 32 MB total, 24 MB in use",
            "Active processes: 14",
            "Disk I/O: 14,233 ops/sec",
            "",
        ]),
        ("SHOW QUOTA", [
            "",
            "Process quota name       Used          Quota         Remaining",
            "Buffered I/O count          2             30               28",
            "Direct I/O count            1             28               27",
            "Paging file                37          20480            20443",
            "Timer queue entries         1             10                9",
            "Open file count             3             50               47",
            "Subprocess count            0             10               10",
            "",
        ]),
        ("BACKUP SYS$LOGIN:*.* MTA0:SMITH_BACKUP/SAVE_SET", [
            "%BACKUP-I-STARTJNL, starting journal file SYS$COMMON:[SYSEXE]BACKUP.LOG",
            "%BACKUP-I-PROCESS,  processing SYS$SYSROOT:[SMITH]LOGIN.COM;1",
            "%BACKUP-I-PROCESS,  processing SYS$SYSROOT:[SMITH]REPORT.TXT;3",
            "%BACKUP-I-PROCESS,  processing SYS$SYSROOT:[SMITH]PROGRAM.FOR;1",
            "%BACKUP-I-PROCESS,  processing SYS$SYSROOT:[SMITH]RUNFILE.COM;2",
            "%BACKUP-I-PROCESS,  processing SYS$SYSROOT:[SMITH]OUTPUT.LIS;4",
            "%BACKUP-I-ENDJNL,   ending journal",
            "",
        ]),
        ("MOUNT /FOREIGN MTA1: SCRATCH", [
            "%MOUNT-I-MOUNTED, SCRATCH mounted on _MTA1:",
            "",
        ]),
        ("LOGOUT", [
            "",
            "  SMITH logged out at  3-AUG-1990 14:35:22.18",
            "  Elapsed:    0 00:15:09.84  CPU:        0 00:00:02.34  I/O:      1342",
            "",
        ]),
    ],
    "crash_lines": [
        "",
        "%BUGCHECK-F-INCONSTATE, inconsistent state detected",
        "%SYSTEM-F-ACCVIO, access violation",
        "",
        "VAX/VMS crash dump initiated",
        "Writing SYS$SYSTEM:SYSAPERDUMP.DMP",
        "...",
        "Crash dump complete. System halted.",
        "",
        ">>> HALT",
        ">>> ",
    ],
    "crash_bg": BLACK,
    "colors": {
        "prompt": Color(0, 220, 180),
        "output": Color(180, 220, 200),
        "banner": Color(0, 200, 200),
        "header": Color(0, 255, 220),
        "dim":    Color(0, 100, 100),
        "crash":  Color(255, 100, 50),
    },
})

_GOPHER = _TermSim({
    "name": "Gopher 1436",
    "prompt": "gopher> ",
    "banner": [
        "",
        "Gopher Client v2.3  (RFC 1436)",
        "Type 'open <host>' to connect, 'quit' to exit",
        "",
    ],
    "session": [
        ("open gopher.floodgap.com", [
            "Trying 69.90.127.50...",
            "Connected to gopher.floodgap.com (port 70).",
            "",
            "    Floodgap Systems Gopher Server",
            "    ================================",
            "",
            " 1  About Floodgap and our Gopher server",
            " 1  Software for Gopherspace",
            " 0  Gopherspace News",
            " 7  Search Gopherspace with Veronica-2",
            " 1  Fun and games",
            " 0  Welcome message (25+ years in Gopherspace!)",
            " 1  Archived items",
            "",
        ]),
        ("1", [
            "Opening menu: About Floodgap...",
            "",
            " 0  About this server",
            " 0  Our history (since 1994)",
            " 0  Contact information",
            " 0  Server statistics",
            " 1  Back to main menu",
            "",
        ]),
        ("7", [
            "Enter search terms: unix history",
            "Connecting to Veronica-2 at gopher.floodgap.com...",
            "Results for: unix history",
            "",
            " 0  A Brief History of Unix",
            " 0  The Unix Heritage Society archives",
            " 1  Dennis Ritchie Memorial Archive",
            " 0  Ken Thompson interview transcript (1999)",
            " 0  The Original Bell Labs Unix manpages",
            " 1  TUHS - The Unix Heritage Society",
            "",
        ]),
        ("0", [
            "Fetching text document...",
            "================================================",
            "",
            "A BRIEF HISTORY OF UNIX",
            "",
            "Unix was conceived in 1969 by Ken Thompson at Bell Labs",
            "as a single-user operating system. Dennis Ritchie created",
            "the C programming language to rewrite it in 1973.",
            "",
            "Version 7 (1979) was the last widely distributed research",
            "edition, notable for its portability and elegant design.",
            "It shipped with cc, sh, awk, sed, grep, and make.",
            "",
            "[end of document]",
            "",
        ]),
        ("quit", [
            "Connection closed.",
            "",
        ]),
    ],
    "crash_lines": [
        "Connection refused to gopher.floodgap.com:70",
        "Gopher protocol error: unexpected EOF",
        "Server returned invalid menu format",
        "gopher: Network unreachable",
    ],
    "crash_bg": BLACK,
    "colors": {
        "prompt": Color(0, 200, 0),
        "output": Color(0, 160, 0),
        "banner": Color(0, 220, 50),
        "header": Color(0, 255, 0),
        "dim":    Color(0, 80, 0),
        "crash":  Color(255, 50, 0),
    },
})

_TOPS20 = _TermSim({
    "name": "TOPS-20 7.1",
    "prompt": "@",
    "banner": [
        "",
        " TOPS-20 Command Processor 7(21022)",
        " SIC-20 System -- PDP-10 KL-10B",
        " Copyright 1988 Digital Equipment Corporation",
        "",
        " Welcome to the Stanford Integrated Circuit Lab",
        " Type HELP for assistance",
        "",
        "@LOGIN SMITH",
        " Job 23  SIC-20 TOPS-20 7(21022)  TTY 14  2:13pm  Thursday",
        " Previous login: Monday, 3-Aug-87 14:12, from LOCAL",
        "",
    ],
    "session": [
        ("DIRECTORY", [
            " SMITH.DIR.1    REPORT.TXT.3    PROGRAM.FOR.1",
            " RUNFILE.SAV.1   OUTPUT.LST.2",
            " 5 Files, 1247 pages",
            "",
        ]),
        ("TYPE REPORT.TXT", [
            "",
            "Stanford IC Lab - Quarterly Report Q3 1987",
            "============================================",
            "Project: 32-bit RISC processor simulation",
            "Team: Smith, Chen, Nakamura, Volkov",
            "CPU simulation cycles completed: 1,048,576",
            "Timing violations: 0",
            "Status: ON SCHEDULE",
            "",
        ]),
        ("COMPILE PROGRAM.FOR", [
            "FORTRAN-10: PROGRAM.FOR",
            "   0 Errors detected",
            "LINK: Loading",
            "   LINK: Execution begins",
            "",
        ]),
        ("RUN PROGRAM", [
            "PROGRAM Version 1.3",
            "Enter matrix size: 64",
            "Computation complete: 0.347 seconds",
            "",
        ]),
        ("INFORMATION JOB", [
            " Job 23, User SMITH, assigned to TTY14",
            " Connected at  3-Aug-87 2:13pm",
            " CPU time used:   0:02:14",
            " Runtime limit:   5:00:00",
            " Core limit:    256K words",
            "",
        ]),
        ("LOGOUT", [
            " Saved all files",
            " CPU Time: 0:02:47  Connect Time: 0:18:33",
            " Logged out Job 23, User SMITH at 2:31pm",
            "",
        ]),
    ],
    "crash_lines": [
        "?TOPS20 Fatal trap at address 254321",
        "?Memory parity error -- job 23 killed",
        "?Return to EXEC",
        "@",
    ],
    "crash_bg": BLACK,
    "colors": {
        "prompt": Color(0, 220, 220),
        "output": Color(180, 220, 220),
        "banner": Color(100, 220, 220),
        "header": Color(0, 255, 255),
        "dim":    Color(0, 100, 100),
        "crash":  Color(255, 200, 0),
    },
})

_BELLUNIX = _TermSim({
    "name": "UNIX V7 1979",
    "prompt": "$ ",
    "banner": [
        "",
        "UNIX  (Version 7)",
        "login: dmr",
        "Password:",
        "",
        "You have mail.",
        "",
    ],
    "session": [
        ("ls -l", [
            "total 242",
            "-rwxr-xr-x 1 root     13948 Aug  1 1979 cc",
            "-rwxr-xr-x 1 root      4096 Aug  1 1979 sh",
            "-rw-r--r-- 1 dmr       8192 Aug  2 1979 ken.c",
            "-rw-r--r-- 1 dmr        512 Aug  2 1979 a.out",
            "-rw-r--r-- 1 dmr        128 Aug  3 1979 Makefile",
            "",
        ]),
        ("cat Makefile", [
            "CC=cc",
            "CFLAGS=-O",
            "ken: ken.o",
            "\t$(CC) $(CFLAGS) -o ken ken.o",
            "ken.o: ken.c",
            "\t$(CC) $(CFLAGS) -c ken.c",
            "",
        ]),
        ("cc -O ken.c", [
            "",
        ]),
        ("./a.out", [
            "hello, world",
            "",
        ]),
        ("grep -n main ken.c", [
            "1:main(argc, argv)",
            "42:/* main loop */",
            "",
        ]),
        ("who", [
            "dmr      tty0   Aug  3 14:09",
            "ken      tty1   Aug  3 14:02",
            "bwk      tty2   Aug  3 09:34",
            "mab      tty3   Aug  3 11:22",
            "",
        ]),
        ("mail", [
            "From ken Fri Aug  3 13:41:07 1979",
            "dmr -",
            "changed the interrupt handler again - see ken.c rev 3.",
            "pipe semantics still broken on 11/70. -ken",
            "",
            "?",
        ]),
    ],
    "crash_lines": [
        "Segmentation fault -- core dumped",
        "Memory fault",
        "Bus error",
        "$ ",
    ],
    "crash_bg": BLACK,
    "colors": {
        "prompt": Color(200, 200, 200),
        "output": Color(180, 180, 180),
        "banner": Color(220, 220, 220),
        "header": Color(255, 255, 255),
        "dim":    Color(120, 120, 120),
        "crash":  Color(200, 100, 0),
    },
})

_PLAN9 = _TermSim({
    "name": "Plan 9 (4th Ed)",
    "prompt": "; ",
    "banner": [
        "",
        "Plan 9 from Bell Labs",
        "4th Edition",
        "",
        "cpu% factotum -D",
        "cpu% aux/listen1 -t tcp!*!rcmd /bin/cpu",
        "",
    ],
    "session": [
        ("ls /bin", [
            "1",
            "2",
            "acid",
            "auth/factotum",
            "auth/secstore",
            "awk",
            "bc",
            "cat",
            "cp",
            "dd",
            "diff",
            "echo",
            "ed",
            "grep",
            "ls",
            "mk",
            "rc",
            "sed",
            "",
        ]),
        ("cat /dev/sysname", [
            "gnot",
            "",
        ]),
        ("bind -a '#S' /dev", [
            "",
        ]),
        ("cat /proc/1/status", [
            "rc             0   Sleeping     0:00:01.234   0:00:00.012   15M",
            "",
        ]),
        ("9fs sources", [
            "post...sources",
            "9fs sources: connected",
            "",
        ]),
        ("mk", [
            "mk: '/sys/src/cmd/rc/rc.c' is up to date",
            "",
        ]),
        ("cat /net/tcp/clone", [
            "3",
            "",
        ]),
        ("ls -l /dev", [
            "--rw-rw---- M 1 glenda glenda    0 Apr  1 14:23 cons",
            "--rw-rw---- M 1 glenda glenda    0 Apr  1 14:23 consctl",
            "-r--r--r-- M 1 glenda glenda   12 Apr  1 14:23 sysname",
            "-r--r--r-- M 1 glenda glenda   32 Apr  1 14:23 time",
            "",
        ]),
    ],
    "crash_lines": [
        "panic: trap: gs segment",
        "cpu0: syscall pc=0x80104e77",
        "cpu halted",
        "; ",
    ],
    "crash_bg": BLACK,
    "colors": {
        "prompt": Color(180, 180, 220),
        "output": Color(160, 160, 200),
        "banner": Color(200, 200, 240),
        "header": Color(220, 220, 255),
        "dim":    Color(80, 80, 120),
        "crash":  Color(200, 100, 200),
    },
})

_SYSTEMS = [
    _MAC_OS,
    _CRAY,
    _MSDOS,
    _WINDOWS,
    _SOLARIS,
    _VAX,
    _GOPHER,
    _TOPS20,
    _BELLUNIX,
    _PLAN9,
]


# ── Scene ─────────────────────────────────────────────────────────────────────

class ComputerSim(Scene):
    name = "CompSim"

    def __init__(self):
        self._sys_idx    = 0
        self._theme_idx  = 0
        self._speed      = 1.0
        self._random     = False
        self._crashed    = False

        self._text_plane: Optional[Plane] = None
        self._bg_plane:   Optional[Plane] = None
        self._h = self._w = 0

        # Reset all sims to clean state
        for sim in _SYSTEMS:
            sim.reset()

    def _current_sim(self) -> _TermSim:
        return _SYSTEMS[self._sys_idx]

    def _current_theme(self) -> str:
        return _THEMES[self._theme_idx]

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def init(self, renderer, h: int, w: int) -> None:
        self._h, self._w = h, w
        self._bg_plane   = Plane(h, w, z=-1)
        self._text_plane = Plane(h, w, z=0)
        for sim in _SYSTEMS:
            sim.reset()

    def on_resize(self, h: int, w: int) -> None:
        self._h, self._w = h, w
        self._bg_plane   = Plane(h, w, z=-1)
        self._text_plane = Plane(h, w, z=0)

    def cleanup(self) -> None:
        pass

    # ── Controls ──────────────────────────────────────────────────────────────

    def on_key(self, key: int) -> bool:
        if key == ord('n'):
            self._sys_idx = (self._sys_idx + 1) % len(_SYSTEMS)
            _SYSTEMS[self._sys_idx].reset()
            self._crashed = False
            return True
        if key == ord('b'):
            self._sys_idx = (self._sys_idx - 1) % len(_SYSTEMS)
            _SYSTEMS[self._sys_idx].reset()
            self._crashed = False
            return True
        if key == ord('o'):
            self._theme_idx = (self._theme_idx - 1) % len(_THEMES)
            return True
        if key == ord('p'):
            self._theme_idx = (self._theme_idx + 1) % len(_THEMES)
            return True
        if key == ord('['):
            self._speed = max(_SPD_MIN, round(self._speed - _SPD_STEP, 2))
            return True
        if key == ord(']'):
            self._speed = min(_SPD_MAX, round(self._speed + _SPD_STEP, 2))
            return True
        if key == ord('c'):
            sim = self._current_sim()
            if self._crashed:
                sim.recover()
                self._crashed = False
            else:
                sim.crash()
                self._crashed = True
            return True
        if key == ord('r'):
            self._random = not self._random
            return True
        return False

    # ── Frame update ──────────────────────────────────────────────────────────

    def update(self, h: int, w: int) -> None:
        self._h, self._w = h, w

        # Recreate planes if size changed
        if (self._text_plane is None or
                self._text_plane.h != h or self._text_plane.w != w):
            self._bg_plane   = Plane(h, w, z=-1)
            self._text_plane = Plane(h, w, z=0)

        self._bg_plane.clear()
        self._text_plane.clear()

        sim = self._current_sim()
        ticks_per_frame = max(1, int(self._speed * 2))

        if not self._crashed:
            for _ in range(ticks_per_frame):
                sim.tick(self._speed, self._random)

        theme = self._current_theme()
        data  = sim.data

        # Windows BSOD: fill bg_plane blue
        if self._crashed and data.get("crash_bg", BLACK) != BLACK:
            crash_bg = data["crash_bg"]
            for row in range(h - 1):
                for col in range(w):
                    self._bg_plane.put_char(row, col, " ",
                                            fg=WHITE, bg=crash_bg)

        sim.render(self._text_plane, h, w, theme)

    def planes(self) -> list[Plane]:
        result = []
        if self._bg_plane is not None:
            result.append(self._bg_plane)
        if self._text_plane is not None:
            result.append(self._text_plane)
        return result

    # ── Status bar ────────────────────────────────────────────────────────────

    @property
    def status_extras(self) -> str:
        sim_name  = _SYSTEMS[self._sys_idx].data["name"]
        theme     = _THEMES[self._theme_idx]
        rand_flag = "ON" if self._random else "OFF"
        return (f"  n/b {sim_name}"
                f"  o/p {theme}"
                f"  [/] x{self._speed:.2f}"
                f"  c CRASH"
                f"  r RAND:{rand_flag}")

    @property
    def status_color(self) -> Color:
        sim    = self._current_sim()
        colors = _apply_theme(self._current_theme(), sim.data["colors"])
        return colors["prompt"]
