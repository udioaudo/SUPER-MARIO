"""Unit tests for the Debug module."""

from __future__ import annotations

import pygame
import pytest
from debug import DebugWindow


# ─── Mock objects ────────────────────────────────────────────────────────────


class MockCPU:
    """Minimal CPU mock for debug window testing."""

    def __init__(self) -> None:
        self.a: int = 0x42
        self.x: int = 0x01
        self.y: int = 0x02
        self.pc: int = 0xC000
        self.sp: int = 0xFD
        self.p: int = 0x34


class MockPPU:
    """Minimal PPU mock for debug window testing."""

    def __init__(self) -> None:
        self._frame: int = 123

    @property
    def frame(self) -> int:
        return self._frame

    def get_pattern_table(self, table_index: int) -> list[list[tuple[int, int, int]]]:
        """Return a simple 8×8 grey pattern for each tile."""
        size = 128
        return [[(0, 0, 0) for _ in range(size)] for _ in range(size)]

    def get_palette_data(self) -> tuple[bytes, list[tuple[int, int, int]]]:
        """Return minimal palette data."""
        return bytes(32), [(0, 0, 0)] * 64


class MockBus:
    """Minimal Bus mock for debug window testing."""

    def read(self, addr: int, from_ppu: bool = False) -> int:
        return (addr & 0xFF) ^ 0x55  # deterministic pattern


class MockInput:
    """Minimal Input mock for debug window testing."""

    def get_state(self) -> list[int]:
        return [0] * 8


# ─── Fixtures ────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _init_pygame() -> None:
    """Ensure pygame is initialised."""
    if not pygame.get_init():
        pygame.init()


@pytest.fixture
def debug() -> DebugWindow:
    """Create a DebugWindow with mock dependencies."""
    return DebugWindow(
        cpu=MockCPU(),
        ppu=MockPPU(),
        bus=MockBus(),
        input_dev=MockInput(),
    )


# ─── Tests ───────────────────────────────────────────────────────────────────


class TestDebugWindowInit:
    """Tests for basic construction and initial state."""

    def test_created_visible(self, debug: DebugWindow) -> None:
        """New debug windows should be visible."""
        assert debug.visible is True

    def test_has_surface(self, debug: DebugWindow) -> None:
        """Internal rendering surface should exist."""
        assert debug._surface is not None


class TestHandleInput:
    """Tests for debug keyboard shortcuts."""

    def test_f5_returns_pause(self, debug: DebugWindow) -> None:
        """F5 should return a pause action."""
        pygame.event.clear()
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F5))
        result = debug.handle_input()
        assert result == {"action": "pause"}

    def test_f6_returns_frame_step(self, debug: DebugWindow) -> None:
        """F6 should return a frame step action."""
        pygame.event.clear()
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F6))
        result = debug.handle_input()
        assert result == {"action": "step", "step": "frame"}

    def test_f7_returns_instruction_step(self, debug: DebugWindow) -> None:
        """F7 should return an instruction step action."""
        pygame.event.clear()
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F7))
        result = debug.handle_input()
        assert result == {"action": "step", "step": "instruction"}

    def test_f1_increments_mem_addr(self, debug: DebugWindow) -> None:
        """F1 should increase memory start address by 0x100."""
        pygame.event.clear()
        addr_before = debug._mem_start_addr
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F1))
        result = debug.handle_input()
        assert result == {}
        assert debug._mem_start_addr == (addr_before + 0x100) & 0xFFFF

    def test_f2_decrements_mem_addr(self, debug: DebugWindow) -> None:
        """F2 should decrease memory start address by 0x100."""
        debug._mem_start_addr = 0x0200
        pygame.event.clear()
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_F2))
        debug.handle_input()
        assert debug._mem_start_addr == 0x0100

    def test_up_scrolls_mem_forward(self, debug: DebugWindow) -> None:
        """UP arrow should increase memory start by 0x10."""
        pygame.event.clear()
        addr_before = debug._mem_start_addr
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_UP))
        debug.handle_input()
        assert debug._mem_start_addr == (addr_before + 0x10) & 0xFFFF

    def test_down_scrolls_mem_backward(self, debug: DebugWindow) -> None:
        """DOWN arrow should decrease memory start by 0x10."""
        debug._mem_start_addr = 0x0030
        pygame.event.clear()
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_DOWN))
        debug.handle_input()
        assert debug._mem_start_addr == 0x0020

    def test_pageup_scrolls_mem_forward_0x100(self, debug: DebugWindow) -> None:
        """PgUp should increase memory start by 0x100."""
        pygame.event.clear()
        addr_before = debug._mem_start_addr
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_PAGEUP))
        debug.handle_input()
        assert debug._mem_start_addr == (addr_before + 0x100) & 0xFFFF

    def test_pagedown_scrolls_mem_backward_0x100(self, debug: DebugWindow) -> None:
        """PgDn should decrease memory start by 0x100."""
        debug._mem_start_addr = 0x0200
        pygame.event.clear()
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_PAGEDOWN))
        debug.handle_input()
        assert debug._mem_start_addr == 0x0100

    def test_unmapped_key_reposted(self, debug: DebugWindow) -> None:
        """Non-debug keys should be reposted to the event queue."""
        pygame.event.clear()
        pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_a))
        debug.handle_input()
        # Should be reposted
        found = False
        for ev in pygame.event.get():
            if ev.type == pygame.KEYDOWN and ev.key == pygame.K_a:
                found = True
        assert found, "Unmapped KEYDOWN should be reposted"


class TestUpdateAndRender:
    """Tests for update() and render() not crashing."""

    def test_update_no_crash(self, debug: DebugWindow) -> None:
        """update() should complete without exception."""
        debug.update()  # should not raise

    def test_render_no_crash(self, debug: DebugWindow) -> None:
        """render() should complete without exception."""
        debug.render()  # should not raise

    def test_update_then_render_no_crash(self, debug: DebugWindow) -> None:
        """update() followed by render() should not crash."""
        debug.update()
        debug.render()


class TestVisibleProperty:
    """Tests for the visible property and window close behavior."""

    def test_window_close_sets_visible_false(self, debug: DebugWindow) -> None:
        """Closing the window should set visible to False."""
        pygame.event.clear()
        pygame.event.post(pygame.event.Event(pygame.QUIT))
        debug.handle_input()
        assert debug.visible is False
