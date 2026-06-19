"""NES emulator debug window — CPU state, memory viewer, pattern tables, palettes.

Provides an independent on-screen debugging panel (640×480) activated via ``--debug``.
The window can be closed independently without affecting the main game window.

Keyboard shortcuts:
  F5          Pause / Continue
  F6          Frame step (when paused)
  F7          Instruction step (when paused)
  F1 / F2     Memory start addr ±0x100
  ↑ / ↓       Memory scroll ±0x10
  PgUp / PgDn Memory scroll ±0x100
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pygame

if TYPE_CHECKING:
    from bus import Bus
    from cpu import CPU
    from input import Input
    from ppu import PPU

# ─── Constants ───────────────────────────────────────────────────────────────

DEBUG_WIDTH: int = 640
DEBUG_HEIGHT: int = 480
FONT_SIZE: int = 13
LINE_HEIGHT: int = 16
COLOR_BG: tuple[int, int, int] = (20, 20, 30)
COLOR_TEXT: tuple[int, int, int] = (200, 200, 200)
COLOR_HEADING: tuple[int, int, int] = (255, 220, 60)
COLOR_VALUE: tuple[int, int, int] = (120, 220, 120)
COLOR_HINT: tuple[int, int, int] = (140, 140, 160)


class DebugWindow:
    """Standalone debug window for inspecting NES emulator state at runtime."""

    def __init__(
        self,
        cpu: "CPU",
        ppu: "PPU",
        bus: "Bus",
        input_dev: "Input",
    ) -> None:
        """Create a 640×480 debug window.

        Args:
            cpu: Reference to the CPU (read-only access).
            ppu: Reference to the PPU (read-only access).
            bus: Reference to the Bus (for memory reads).
            input_dev: Reference to the Input module (for controller state).
        """
        self._cpu = cpu
        self._ppu = ppu
        self._bus = bus
        self._input = input_dev

        self._visible: bool = True
        self._mem_start_addr: int = 0x0000

        # Rendering surface (blitted to display by caller or self-contained)
        self._surface: pygame.Surface = pygame.Surface((DEBUG_WIDTH, DEBUG_HEIGHT))

        try:
            self._font: pygame.font.Font = pygame.font.SysFont("Consolas", FONT_SIZE)
        except Exception:
            self._font = pygame.font.Font(None, FONT_SIZE)

        # FPS tracking
        self._fps_history: list[float] = []

        # Cached pattern table surfaces (updated in update())
        self._pt_cache: tuple[pygame.Surface | None, pygame.Surface | None] = (
            None,
            None,
        )

    # ─── Properties ─────────────────────────────────────────────────────────

    @property
    def visible(self) -> bool:
        """Whether the debug window is still open."""
        return self._visible

    # ─── Update & Render ────────────────────────────────────────────────────

    def update(self) -> None:
        """Refresh cached data (pattern tables, etc.). Called once per frame."""
        # Cache pattern table visualisations
        try:
            pt0 = self._ppu.get_pattern_table(0)
            pt1 = self._ppu.get_pattern_table(1)
            self._pt_cache = (
                _make_surface_from_pixels(pt0, 128, 128),
                _make_surface_from_pixels(pt1, 128, 128),
            )
        except Exception:
            self._pt_cache = (None, None)

    def render(self) -> None:
        """Render all debug information to the internal surface."""
        self._surface.fill(COLOR_BG)

        y = 5
        self._render_cpu_registers(5, y)
        self._render_runtime_info(290, y)
        y += 95
        self._render_memory_view(5, y)
        self._render_pattern_tables(300, y)
        self._render_palette(300, y + 145)
        self._render_controls_hint(5, DEBUG_HEIGHT - 20)

    # ─── Input handling ────────────────────────────────────────────────────

    def handle_input(self) -> dict[str, Any]:
        """Process keyboard shortcuts for the debug window.

        Returns a command dict consumed by the main loop, e.g.:
        ``{'action': 'pause'}`` or ``{'action': 'step', 'step': 'frame'}``.
        Returns an empty dict when no debug action was triggered.

        Non-debug events are reposted to the global Pygame event queue.
        """
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self._visible = False
                return {}

            if event.type == pygame.KEYDOWN:
                cmd = self._handle_keydown(event)
                if cmd:
                    return cmd

            # Repost unhandled events
            pygame.event.post(event)

        return {}

    def _handle_keydown(self, event: pygame.event.Event) -> dict[str, Any] | None:
        """Map a single KEYDOWN event to a debug command, or None."""
        key = event.key

        if key == pygame.K_F5:
            return {"action": "pause"}
        if key == pygame.K_F6:
            return {"action": "step", "step": "frame"}
        if key == pygame.K_F7:
            return {"action": "step", "step": "instruction"}

        if key == pygame.K_F1:
            self._mem_start_addr = (self._mem_start_addr + 0x100) & 0xFFFF
            return {}
        if key == pygame.K_F2:
            self._mem_start_addr = (self._mem_start_addr - 0x100) & 0xFFFF
            return {}

        if key == pygame.K_UP:
            self._mem_start_addr = (self._mem_start_addr + 0x10) & 0xFFFF
            return {}
        if key == pygame.K_DOWN:
            self._mem_start_addr = max(0, self._mem_start_addr - 0x10)
            return {}

        if key == pygame.K_PAGEUP:
            self._mem_start_addr = (self._mem_start_addr + 0x100) & 0xFFFF
            return {}
        if key == pygame.K_PAGEDOWN:
            self._mem_start_addr = max(0, self._mem_start_addr - 0x100)
            return {}

        return None  # repost

    # ─── Rendering helpers ──────────────────────────────────────────────────

    def _draw_text(
        self,
        x: int,
        y: int,
        text: str,
        color: tuple[int, int, int] = COLOR_TEXT,
    ) -> None:
        """Draw a single line of text at (x, y)."""
        img = self._font.render(text, True, color)
        self._surface.blit(img, (x, y))

    def _render_cpu_registers(self, x: int, y: int) -> None:
        """Display CPU register values with expanded status flags."""
        cpu = self._cpu
        self._draw_text(x, y, "── CPU Registers ──", COLOR_HEADING)
        y += LINE_HEIGHT
        self._draw_text(x, y, f"A:  0x{cpu.a:02X}  ({cpu.a})", COLOR_VALUE)
        y += LINE_HEIGHT
        self._draw_text(x, y, f"X:  0x{cpu.x:02X}  ({cpu.x})", COLOR_VALUE)
        y += LINE_HEIGHT
        self._draw_text(x, y, f"Y:  0x{cpu.y:02X}  ({cpu.y})", COLOR_VALUE)
        y += LINE_HEIGHT
        self._draw_text(x, y, f"PC: 0x{cpu.pc:04X}", COLOR_VALUE)
        y += LINE_HEIGHT
        self._draw_text(x, y, f"SP: 0x{cpu.sp:02X}", COLOR_VALUE)
        y += LINE_HEIGHT

        # Expand status flags: uppercase = set, lowercase = clear
        p = cpu.p
        flags = ""
        flags += "N" if p & 0x80 else "n"
        flags += "V" if p & 0x40 else "v"
        flags += "-"
        flags += "B" if p & 0x10 else "b"
        flags += "D" if p & 0x08 else "d"
        flags += "I" if p & 0x04 else "i"
        flags += "Z" if p & 0x02 else "z"
        flags += "C" if p & 0x01 else "c"
        self._draw_text(x, y, f"P:  {flags}  (0x{p:02X})", COLOR_VALUE)

    def _render_runtime_info(self, x: int, y: int) -> None:
        """Display FPS, frame count, and run state."""
        self._draw_text(x, y, "── Runtime ──", COLOR_HEADING)
        y += LINE_HEIGHT

        # Average FPS from recent history
        self._fps_history.append(pygame.time.Clock().get_fps())
        if len(self._fps_history) > 60:
            self._fps_history.pop(0)
        avg_fps = (
            sum(self._fps_history) / len(self._fps_history)
            if self._fps_history
            else 0.0
        )
        self._draw_text(x, y, f"FPS:     {avg_fps:.1f}", COLOR_TEXT)
        y += LINE_HEIGHT

        try:
            frame = self._ppu.frame
        except Exception:
            frame = 0
        self._draw_text(x, y, f"Frame:   {frame}", COLOR_TEXT)

    def _render_memory_view(self, x: int, y: int) -> None:
        """Display a hex dump of 16 rows × 16 bytes starting at _mem_start_addr."""
        self._draw_text(
            x, y, f"── Memory [0x{self._mem_start_addr:04X}] ──", COLOR_HEADING
        )
        y += LINE_HEIGHT

        for row in range(16):
            addr = (self._mem_start_addr + row * 16) & 0xFFFF
            line = f"{addr:04X}: "
            chars = ""
            for col in range(16):
                try:
                    b = self._bus.read((addr + col) & 0xFFFF) & 0xFF
                except Exception:
                    b = 0
                line += f"{b:02X} "
                chars += chr(b) if 32 <= b < 127 else "."
            line += f" {chars}"
            self._draw_text(x, y + row * LINE_HEIGHT, line, COLOR_TEXT)

    def _render_pattern_tables(self, x: int, y: int) -> None:
        """Display Pattern Table 0 and 1 (128×128 each, scaled 2×)."""
        pt0_surf, pt1_surf = self._pt_cache

        self._draw_text(x, y, "── Pattern Tables ──", COLOR_HEADING)
        y += LINE_HEIGHT

        if pt0_surf is not None:
            scaled = pygame.transform.scale(pt0_surf, (128, 128))
            self._surface.blit(scaled, (x, y))
            self._draw_text(x, y + 130, "PT0", COLOR_HINT)

        if pt1_surf is not None:
            scaled = pygame.transform.scale(pt1_surf, (128, 128))
            self._surface.blit(scaled, (x + 135, y))
            self._draw_text(x + 135, y + 130, "PT1", COLOR_HINT)

    def _render_palette(self, x: int, y: int) -> None:
        """Display 8 palette groups × 4 colours each."""
        self._draw_text(x, y, "── Palettes ──", COLOR_HEADING)
        y += LINE_HEIGHT

        try:
            palette_ram, _ = self._ppu.get_palette_data()
        except Exception:
            palette_ram = bytes(32)

        from palette import SYSTEM_PALETTE

        labels = ["BG0", "BG1", "BG2", "BG3", "SP0", "SP1", "SP2", "SP3"]
        for group in range(8):
            self._draw_text(x, y + group * 18, f"{labels[group]}:", COLOR_TEXT)
            for color in range(4):
                idx = palette_ram[group * 4 + color] & 0x3F
                rgb = SYSTEM_PALETTE[idx]
                rect = pygame.Rect(x + 40 + color * 18, y + group * 18, 16, 16)
                pygame.draw.rect(self._surface, rgb, rect)
                pygame.draw.rect(self._surface, (60, 60, 60), rect, 1)

    def _render_controls_hint(self, x: int, y: int) -> None:
        """Display keyboard shortcut hints at the bottom."""
        hint = (
            "F5=Pause  F6=Frame Step  F7=Instruction Step  "
            "F1/F2=Mem±0x100  ↑↓=Mem±0x10  PgUp/PgDn=Mem±0x100"
        )
        self._draw_text(x, y, hint, COLOR_HINT)


# ─── Utility ─────────────────────────────────────────────────────────────────


def _make_surface_from_pixels(
    pixels: list[list[tuple[int, int, int]]],
    width: int,
    height: int,
) -> pygame.Surface:
    """Convert a 2-D pixel grid to a Pygame Surface."""
    surf = pygame.Surface((width, height))
    for py in range(min(height, len(pixels))):
        row = pixels[py]
        for px in range(min(width, len(row))):
            surf.set_at((px, py), row[px])
    return surf
