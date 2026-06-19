"""Unit tests for the Input module (keyboard mapping + shift register protocol)."""

from __future__ import annotations

import pygame
import pytest
from input import Input, KEY_MAPPING


@pytest.fixture(autouse=True)
def _init_pygame() -> None:
    """Ensure Pygame is initialised for each test."""
    if not pygame.get_init():
        pygame.init()


@pytest.fixture
def inp() -> Input:
    """Provide a fresh Input instance with a clear event queue."""
    pygame.event.clear()
    return Input()


# ─── Initialisation ─────────────────────────────────────────────────────────


class TestInitialState:
    def test_all_buttons_released(self, inp: Input) -> None:
        """All buttons should be 0 after construction."""
        assert inp.get_state() == [0] * 8

    def test_read_without_latch_returns_connected(self, inp: Input) -> None:
        """Reading before latching should still return 0x40 or 0x41."""
        result = inp.read()
        assert result in (0x40, 0x41)


# ─── Key mapping ────────────────────────────────────────────────────────────


class TestKeyMapping:
    def test_keydown_updates_button(self, inp: Input) -> None:
        """Pressing K (A button) should set button[4] to 1."""
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_k))
        inp.poll()
        assert inp.get_state()[4] == 1

    def test_keyup_releases_button(self, inp: Input) -> None:
        """Releasing K should set button[4] back to 0."""
        # Press first
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_k))
        inp.poll()
        # Then release
        pygame.event.post(pygame.event.Event(pygame.KEYUP, key=pygame.K_k))
        inp.poll()
        assert inp.get_state()[4] == 0

    def test_unmapped_key_reposted(self, inp: Input) -> None:
        """Non-mapped keys should be reposted to the event queue."""
        pygame.event.clear()
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_q))
        inp.poll()

        # The unmapped key should still be in the queue
        found = False
        for ev in pygame.event.get():
            if ev.type == pygame.KEYDOWN and ev.key == pygame.K_q:
                found = True
        assert found, "Unmapped key should be reposted"

    def test_multiple_buttons_pressed(self, inp: Input) -> None:
        """Multiple buttons can be pressed simultaneously."""
        keys = [pygame.K_UP, pygame.K_DOWN, pygame.K_j]
        for k in keys:
            pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=k))
        inp.poll()

        state = inp.get_state()
        assert state[0] == 1  # Up
        assert state[1] == 1  # Down
        assert state[5] == 1  # B


# ─── Write latch & read shift register ─────────────────────────────────────


class TestLatchAndRead:
    def test_latch_locks_current_state(self, inp: Input) -> None:
        """After pressing A and latching, read should return A's value."""
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_k))
        inp.poll()

        inp.write(1)  # latch
        # First read should be A (FC order: A=4)
        assert inp.read() == 0x41  # pressed + 0x40

    def test_read_order_is_fc_standard(self, inp: Input) -> None:
        """Verify reads return A→B→Sel→Start→↑→↓→←→→ order."""
        # Press all buttons
        all_keys = [
            pygame.K_k,  # A (index 4)
            pygame.K_j,  # B (index 5)
            pygame.K_RSHIFT,  # Select (index 7)
            pygame.K_RETURN,  # Start (index 6)
            pygame.K_UP,  # Up (index 0)
            pygame.K_DOWN,  # Down (index 1)
            pygame.K_LEFT,  # Left (index 2)
            pygame.K_RIGHT,  # Right (index 3)
        ]
        for k in all_keys:
            pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=k))
        inp.poll()

        inp.write(1)

        # Expected FC order: A, B, Select, Start, Up, Down, Left, Right
        expected = [1] * 8
        for i in range(8):
            assert inp.read() == (expected[i] | 0x40), f"Mismatch at read {i}"

    def test_ninth_read_returns_1(self, inp: Input) -> None:
        """Reads beyond the 8th should return 0x41 (1 | 0x40)."""
        inp.write(1)  # latch
        for _ in range(8):
            inp.read()
        # 9th and beyond
        assert inp.read() == 0x41
        assert inp.read() == 0x41

    def test_write_0_does_not_latch(self, inp: Input) -> None:
        """Writing 0 to 0x4016 should NOT reset the read index."""
        # Press A
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_k))
        inp.poll()

        inp.write(1)  # latch
        first = inp.read()
        assert first == 0x41  # A pressed

        # Write 0 — should NOT re-latch
        inp.write(0)
        second = inp.read()
        assert second == 0x40  # B (not pressed) — continues from index

    def test_relatch_mid_read(self, inp: Input) -> None:
        """Latching again should reset the read index."""
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_k))
        inp.poll()

        inp.write(1)
        _ = inp.read()  # A
        _ = inp.read()  # B

        # Re-latch
        inp.write(1)
        # Should be back at A
        assert inp.read() == 0x41

    def test_buttons_released_read_zero(self, inp: Input) -> None:
        """No buttons pressed → all reads should return 0x40."""
        inp.write(1)
        for _ in range(8):
            assert inp.read() == 0x40


# ─── Debug helper ──────────────────────────────────────────────────────────


class TestGetState:
    def test_get_state_returns_copy(self, inp: Input) -> None:
        """get_state should return a copy, not a reference."""
        state = inp.get_state()
        state[0] = 99
        assert inp.get_state()[0] == 0

    def test_get_state_reflects_current(self, inp: Input) -> None:
        """get_state should reflect current button states."""
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_j))
        inp.poll()
        assert inp.get_state()[5] == 1


# ─── Key mapping completeness ──────────────────────────────────────────────


class TestKeyMappingConstant:
    def test_mapping_has_8_entries(self) -> None:
        """KEY_MAPPING should have exactly 8 entries."""
        assert len(KEY_MAPPING) == 8

    def test_all_indices_covered(self) -> None:
        """All button indices 0–7 should be mapped."""
        indices = set(KEY_MAPPING.values())
        assert indices == set(range(8))

    def test_direction_keys_mapped(self) -> None:
        """Arrow keys should map to indices 0–3."""
        assert KEY_MAPPING[pygame.K_UP] == 0
        assert KEY_MAPPING[pygame.K_DOWN] == 1
        assert KEY_MAPPING[pygame.K_LEFT] == 2
        assert KEY_MAPPING[pygame.K_RIGHT] == 3
