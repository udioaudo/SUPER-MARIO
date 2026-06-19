"""Pygame-based game window for the NES emulator.

Handles:
  - Window creation with pixel-accurate scaling (1×–5×)
  - Frame rendering (256×240 → scaled window)
  - Event loop (delegates KEYDOWN/KEYUP back to queue for Input module)
  - Frame rate control (target: NTSC 60.0988 FPS)
"""

from __future__ import annotations

import numpy as np
import pygame


class UI:
    """Manages the Pygame display window and frame rendering."""

    NATIVE_WIDTH: int = 256
    NATIVE_HEIGHT: int = 240
    FPS_TARGET: float = 60.0988  # NTSC actual frame rate

    def __init__(self, scale: int = 3) -> None:
        """Create a Pygame window scaled from the NES native resolution.

        Args:
            scale: Integer scale factor, clamped to 1–5.
        """
        self._scale: int = max(1, min(5, scale))
        self._window_width: int = self.NATIVE_WIDTH * self._scale
        self._window_height: int = self.NATIVE_HEIGHT * self._scale

        self._window: pygame.Surface = pygame.display.set_mode(
            (self._window_width, self._window_height)
        )
        pygame.display.set_caption("SUPER MARIO - NES Emulator")

        # Internal 256×240 surface for pixel-level rendering
        self._internal_surface: pygame.Surface = pygame.Surface(
            (self.NATIVE_WIDTH, self.NATIVE_HEIGHT)
        )
        self._clock: pygame.time.Clock = pygame.time.Clock()

    def render(self, pixels: list[list[tuple[int, int, int]]]) -> None:
        """Render a 256×240 pixel grid to the scaled window.

        Uses ``pygame.surfarray.blit_array`` for fast NumPy-based pixel transfer.

        Args:
            pixels: 256×240 grid of (R, G, B) tuples (each 0–255).
        """
        # Convert 2-D list to 3-D NumPy array (height, width, 3) of uint8.
        arr = np.array(pixels, dtype=np.uint8)

        # make_surface expects (width, height, 3) — transpose from H×W×3 to W×H×3.
        pixel_surface = pygame.surfarray.make_surface(arr.transpose(1, 0, 2))

        # Scale up to window size
        scaled = pygame.transform.scale(
            pixel_surface, (self._window_width, self._window_height)
        )
        self._window.blit(scaled, (0, 0))
        pygame.display.flip()

    def handle_events(self) -> bool:
        """Process Pygame events for the window layer.

        QUIT events are consumed and signal program exit.
        KEYDOWN / KEYUP events are reposted so the Input module can pick them up.

        Returns:
            True if the application should quit, False otherwise.
        """
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return True
            if event.type in (pygame.KEYDOWN, pygame.KEYUP):
                # Repost so Input.poll() can read it
                pygame.event.post(event)
        return False

    def tick(self) -> int:
        """Cap the frame rate and return the elapsed time in milliseconds.

        Returns:
            Milliseconds elapsed since the last tick.
        """
        return self._clock.tick(int(self.FPS_TARGET))

    def get_fps(self) -> float:
        """Return the current actual frame rate for debug display.

        Returns:
            Approximate FPS averaged over recent frames.
        """
        return self._clock.get_fps()
