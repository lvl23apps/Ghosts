#!/usr/bin/env python3
"""
ghosts2 — terminal scene viewer, v2.

Built on a notcurses-inspired rendering model:
  - Per-cell 24-bit RGB colour (mapped to xterm-256 dynamically)
  - Z-ordered planes composited by the renderer
  - Bilinear gradient fills  (ncplane_gradient equivalent)
  - Step-based fade support  (ncplane_fadeout_iteration equivalent)

Controls:
  ↑ / ↓        intensity 1–10
  ← / → Space  prev / next scene
  q / Esc      quit

Scene-specific controls are shown in the status bar.
"""

import curses
import time
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from renderer import CursesRenderer, Color, BLACK
from scenes import Ghost, MatrixRain, RainDrops, Plasma, TopoFlyover, GlitchScreen, BioScan, ComputerSim, Switchboard

SCENE_CLASSES = [Ghost, MatrixRain, RainDrops, Plasma, TopoFlyover, GlitchScreen, BioScan, ComputerSim, Switchboard]

_FPS   = 30
_FRAME = 1.0 / _FPS


def _status(renderer: CursesRenderer, stdscr, h: int, w: int,
            text: str, fg: Color) -> None:
    renderer.status(stdscr, h, w, text, fg=fg)


def _run(stdscr) -> None:
    curses.curs_set(0)
    stdscr.nodelay(True)

    renderer = CursesRenderer()
    renderer.setup(stdscr)

    intensity = 5
    idx       = 0
    scenes    = [S() for S in SCENE_CLASSES]
    for s in scenes:
        s.intensity = intensity

    h, w      = stdscr.getmaxyx()
    prev_size = (h, w)
    scenes[idx].init(renderer, h, w)

    while True:
        key = stdscr.getch()

        if key in (ord("q"), 27):
            break

        h, w = stdscr.getmaxyx()
        if (h, w) != prev_size:
            prev_size = (h, w)
            scenes[idx].on_resize(h, w)

        if key in (curses.KEY_RIGHT, ord("\t"), 9):
            scenes[idx].cleanup()
            idx = (idx + 1) % len(scenes)
            scenes[idx].init(renderer, h, w)

        elif key == curses.KEY_LEFT:
            scenes[idx].cleanup()
            idx = (idx - 1) % len(scenes)
            scenes[idx].init(renderer, h, w)

        elif key == curses.KEY_UP:
            intensity = min(10, intensity + 1)
            for s in scenes:
                s.intensity = intensity

        elif key == curses.KEY_DOWN:
            intensity = max(1, intensity - 1)
            for s in scenes:
                s.intensity = intensity

        elif key != -1:
            scenes[idx].on_key(key)

        t0 = time.monotonic()

        sc  = scenes[idx]
        sc.update(h, w)

        dots = "".join("●" if i == idx else "○" for i in range(len(scenes)))
        bar  = (f"  {dots}  {sc.name}"
                f"  ↑↓ {intensity}/10"
                f"{sc.status_extras}"
                f"  ← → switch  q quit  ")

        stdscr.erase()
        renderer.composite(sc.planes(), h, w)
        _status(renderer, stdscr, h, w, bar, sc.status_color)
        stdscr.refresh()

        elapsed = time.monotonic() - t0
        sleep   = _FRAME - elapsed
        if sleep > 0:
            time.sleep(sleep)


def main() -> None:
    try:
        curses.wrapper(_run)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
