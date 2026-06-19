"""NES controller input handler — keyboard-to-controller mapping.

Simulates the standard NES controller (FC 手柄) read protocol via 0x4016:
  1. Write 1 to 0x4016 → latch current button states into a shift register.
  2. Write 0 to 0x4016 → end latch.
  3. Repeatedly read 0x4016 → returns button states in order A→B→Sel→Start→↑→↓→←→→.
  4. Read #9+ returns 1 (controller connected).

Keyboard mapping (Pygame keycodes):
  ↑ = K_UP    ↓ = K_DOWN   ← = K_LEFT   → = K_RIGHT
  A = K_k     B = K_j       Start = K_RETURN   Select = K_RSHIFT
"""

from __future__ import annotations

import pygame

# Pygame key → NES controller button index (0–7)
KEY_MAPPING: dict[int, int] = {
    pygame.K_UP: 0,
    pygame.K_DOWN: 1,
    pygame.K_LEFT: 2,
    pygame.K_RIGHT: 3,
    pygame.K_k: 4,  # A button
    pygame.K_j: 5,  # B button
    pygame.K_RETURN: 6,  # Start
    pygame.K_RSHIFT: 7,  # Select
}

# FC button names in the order they are read from the shift register
_BUTTON_NAMES: list[str] = ["A", "B", "Select", "Start", "Up", "Down", "Left", "Right"]


class Input:
    """Keyboard-based NES controller emulation.

    Maps Pygame key events to the standard NES controller shift-register protocol.
    """

    def __init__(self) -> None:
        """Initialise with all buttons released and read index reset."""
        self._buttons: list[int] = [0] * 8  # current live button states
        self._latch: list[int] = [0] * 8  # latched snapshot for sequential read
        self._read_index: int = 0

    # ─── Event polling ──────────────────────────────────────────────────────

    def poll(self) -> None:
        """Read all pending Pygame events and update button states.

        Mapped KEYDOWN events set the button to 1 (pressed).
        Mapped KEYUP events set the button to 0 (released).
        Non-mapped events are reposted to the queue.
        """
        for event in pygame.event.get():
            if event.type == pygame.KEYDOWN:
                idx = KEY_MAPPING.get(event.key)
                if idx is not None:
                    self._buttons[idx] = 1
                else:
                    pygame.event.post(event)
            elif event.type == pygame.KEYUP:
                idx = KEY_MAPPING.get(event.key)
                if idx is not None:
                    self._buttons[idx] = 0
                else:
                    pygame.event.post(event)
            else:
                # QUIT and other events: put back
                pygame.event.post(event)

    # ─── Controller-port I/O (accessed via Bus → 0x4016) ────────────────────

    def write(self, value: int) -> None:
        """Handle a write to 0x4016.

        bit 0 = 1 → latch current button states into shift register, reset index.
        bit 0 = 0 → end latch (no action needed on transition to 0).

        Args:
            value: 8-bit value written by CPU to 0x4016.
        """
        if value & 0x01:
            self._latch = list(self._buttons)
            self._read_index = 0

    def read(self) -> int:
        """Handle a read from 0x4016.

        Returns the next button state from the latched shift register,
        in FC order: A(4) → B(5) → Select(7) → Start(6) → ↑(0) → ↓(1) → ←(2) → →(3).

        Bit 1 (0x40) is always set to indicate a standard controller is connected.
        Reads beyond the 8th return 1 (with 0x40 bit set → 0x41).

        Returns:
            8-bit value (0x41 = button pressed, 0x40 = released).
        """
        if self._read_index < 8:
            # Map from FC read order to button index
            fc_order = [4, 5, 7, 6, 0, 1, 2, 3]
            btn = self._latch[fc_order[self._read_index]]
            self._read_index += 1
            return btn | 0x40
        # All 8 buttons exhausted — return 1 (controller-connected marker)
        return 0x41

    # ─── Debug helper ──────────────────────────────────────────────────────

    def get_state(self) -> list[int]:
        """Return a copy of the current 8-button state for the debug window.

        Returns:
            List of 8 integers (0 = released, 1 = pressed).
        """
        return list(self._buttons)
