"""Base scene class for ghosts2.

Scenes receive a list of Plane objects (one per logical layer) and a
CursesRenderer.  They write to their planes; the renderer composites.

Intensity (1–10) maps via imap() exactly as in ghosts v1.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from renderer import CursesRenderer, Color, Plane


class Scene:
    name      = "Scene"
    intensity = 5   # 1–10, set externally

    def imap(self, lo: float, hi: float) -> float:
        """Map intensity 1–10 linearly to [lo, hi]."""
        return lo + (self.intensity - 1) * (hi - lo) / 9.0

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def init(self, renderer: "CursesRenderer", h: int, w: int) -> None:
        """Called once when the scene becomes active.  Build planes here."""

    def on_resize(self, h: int, w: int) -> None:
        """Called when the terminal is resized."""

    def update(self, h: int, w: int) -> None:
        """Advance simulation state by one frame.  Do not render here."""

    def planes(self) -> list["Plane"]:
        """Return the current list of planes for the renderer to composite."""
        return []

    def cleanup(self) -> None:
        """Called when switching away from this scene."""

    # ── Scene-specific key handling ───────────────────────────────────────────

    def on_key(self, key: int) -> bool:
        """Handle a scene-specific key press.  Return True if consumed."""
        return False

    @property
    def status_extras(self) -> str:
        """Extra text appended to the status bar for this scene."""
        return ""

    @property
    def status_color(self) -> "Color":
        """Colour used for the status bar text."""
        from renderer import Color
        return Color(0, 150, 0)
