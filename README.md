# Ghosts

Terminal scene viewer — 9 animated scenes rendered in 24-bit colour via xterm-256 mapping.

Built on a notcurses-inspired rendering model: z-ordered planes, per-cell 24-bit RGB, bilinear gradient fills, and step-based fade support.

## Installation

### APT (Debian / Ubuntu)

```bash
curl -sL https://github.com/lvl23apps/Ghosts/releases/latest/download/ghosts.deb -o ghosts.deb
sudo apt install ./ghosts.deb
ghosts
```

### macOS

Python 3.9+ is required. Install it via Homebrew if needed:

```bash
brew install python tmux
```

Then install Ghosts from source:

```bash
git clone https://github.com/lvl23apps/Ghosts.git
cd Ghosts
python3 main.py
```

[iTerm2](https://iterm2.com) or the built-in Terminal app on macOS 12+ both work. `tmux` is recommended for the Ghost scene.

> **Note:** Do not use `brew install ghosts` — Homebrew will resolve this to [Ghostty](https://ghostty.org), a different application.

### Windows

Windows is supported via **WSL** (Windows Subsystem for Linux) or natively with `windows-curses`.

**WSL (recommended):**
```powershell
# From PowerShell — install WSL if you haven't already
wsl --install
```
Then inside the WSL terminal follow the APT instructions above.

**Native (Windows Terminal + Python):**
```powershell
pip install windows-curses
git clone https://github.com/lvl23apps/Ghosts.git
cd Ghosts
python main.py
```

Use [Windows Terminal](https://aka.ms/terminal) for best colour support. Set your profile to `xterm-256color` under Settings → Profiles → Advanced → Environment variables.

### From source

```bash
git clone https://github.com/lvl23apps/Ghosts.git
cd Ghosts
python3 main.py
```

**Requirements:** Python 3.9+, a 256-colour terminal (`TERM=xterm-256color`). No external Python packages — pure stdlib (Windows requires `pip install windows-curses`). `tmux` is optional but recommended: the Ghost scene captures your live pane content when running inside a tmux session.

## Scenes

| Scene | Description |
|---|---|
| Ghost | Captures terminal content before launch; drifts it with five trail modes |
| Matrix Rain | Cascading glyphs with palette and angle control |
| Rain Drops | Rainfall simulation with scatter and wind |
| Plasma | Bilinear gradient wave field |
| Topo Flyover | Terrain scanner with contour rendering |
| Glitch Screen | Display corruption — dissolution, critical error, symbol storm |
| Bio Scan | Biological scan with fossil windows |
| Computer Sim | 10 classic computer systems simulated |
| Switchboard | Shadytel Metropolitan Exchange — interactive patch bay with PANIC mode |

## Controls

| Key | Action |
|---|---|
| `← →` or `Tab` | Previous / next scene |
| `↑ ↓` | Intensity 1–10 |
| `q` / `Esc` | Quit |

Scene-specific controls are shown in the status bar at the bottom.

### Ghost scene

| Key | Action |
|---|---|
| `↑ ↓ ← →` / `wasd` | Drift direction |
| `[ ]` | Speed |
| `- =` | Scatter (column spread) |
| `m` | Trail mode: SIMPLE / PHOSPHOR / SMEAR / WAVE / COMPLEX |
| `f` | Frame FX: NONE / SCANLINE / CHROMATIC / NOISE / GRID |
| `o p` | Colour palette |

### Switchboard scene

| Key | Action |
|---|---|
| `wasd` | Move cursor |
| `Enter` | Select / connect jack |
| `x` | Drop connection |
| `r` | Ring selected jack |
| `t` | Trunk call |
| `[ ]` | Spawn rate |
| `g` | Toggle labels |
| `c` | Trigger PANIC crash mode |
| `z` | Recover from PANIC |

## Building your own scene

See [SCENE_BUILDING.md](SCENE_BUILDING.md) for the full guide — APIs, lifecycle, examples, and step-by-step instructions for registering a new scene.

Short version:

1. Create `scenes/myscene.py` subclassing `Scene` from `scene_base.py`
2. Implement `init`, `update`, `planes`, and optionally `on_key` / `status_extras`
3. Add the import to `scenes/__init__.py`
4. Add the class to `SCENE_CLASSES` in `main.py`

## Architecture

```
main.py          — event loop, scene switching, status bar
renderer.py      — CursesRenderer, Plane, Color, compositor
scene_base.py    — Scene base class and lifecycle contract
effects.py       — shared gradient, burst, and HSV utilities
scenes/
  ghost.py       — terminal drift with ghost trails
  matrix.py      — matrix rain
  rain.py        — rainfall
  plasma.py      — plasma waves
  topo.py        — topo flyover
  glitch.py      — glitch effects
  bioscan.py     — bio scan
  computersim.py — classic computer sim
  switchboard.py — telephone switchboard
```

## License

MIT
