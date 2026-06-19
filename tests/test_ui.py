"""Unit tests for the UI module (non-rendering and event logic)."""

from __future__ import annotations

import pygame
import pytest
from ui import UI


@pytest.fixture(autouse=True)
def _init_pygame() -> None:
    """Ensure Pygame is initialized for each test."""
    if not pygame.get_init():
        pygame.init()


@pytest.fixture
def ui() -> UI:
    """Create a UI instance at minimum scale for fast testing."""
    return UI(scale=1)


def test_constants() -> None:
    """Verify the UI module's documented constants."""
    assert UI.NATIVE_WIDTH == 256
    assert UI.NATIVE_HEIGHT == 240
    assert abs(UI.FPS_TARGET - 60.0988) < 0.001


def test_scale_clamping_min() -> None:
    """Scale values below 1 should be clamped to 1."""
    ui_obj = UI(scale=0)
    assert ui_obj._scale == 1


def test_scale_clamping_max() -> None:
    """Scale values above 5 should be clamped to 5."""
    ui_obj = UI(scale=10)
    assert ui_obj._scale == 5


def test_scale_default() -> None:
    """Default scale should be 3 as per spec."""
    ui_obj = UI()
    assert ui_obj._scale == 3


def test_window_created(ui: UI) -> None:
    """The display surface should exist after construction."""
    assert ui._window is not None
    assert ui._window.get_width() == 256
    assert ui._window.get_height() == 240


def test_internal_surface(ui: UI) -> None:
    """The internal rendering surface should be 256×240."""
    assert ui._internal_surface.get_width() == 256
    assert ui._internal_surface.get_height() == 240


def test_handle_events_quit() -> None:
    """Post a QUIT event and verify handle_events returns True."""
    ui_obj = UI(scale=1)
    # Flush any pending events
    pygame.event.clear()
    pygame.event.post(pygame.event.Event(pygame.QUIT))
    assert ui_obj.handle_events() is True


def test_handle_events_keydown_reposted(ui: UI) -> None:
    """KEYDOWN events should be reposted for the Input module to consume."""
    pygame.event.clear()
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RIGHT))

    result = ui.handle_events()
    assert result is False  # No quit

    # The keydown should still be in the queue (reposted)
    found = False
    for event in pygame.event.get():
        if event.type == pygame.KEYDOWN and event.key == pygame.K_RIGHT:
            found = True
    assert found, "KEYDOWN event was not reposted to the queue"


def test_handle_events_no_events(ui: UI) -> None:
    """With no events in queue, handle_events should return False."""
    pygame.event.clear()
    assert ui.handle_events() is False


def test_tick_returns_int(ui: UI) -> None:
    """tick() should return an integer (elapsed ms)."""
    ms = ui.tick()
    assert isinstance(ms, int)
    assert ms >= 0


def test_get_fps_returns_float(ui: UI) -> None:
    """get_fps() should return a float."""
    fps = ui.get_fps()
    assert isinstance(fps, float)
    assert fps >= 0.0


def test_render_accepts_valid_array(ui: UI) -> None:
    """render() should accept a 256×240 RGB pixel grid without crashing."""
    pixels = [
        [(x * 64 % 256, y * 32 % 256, (x + y) * 16 % 256) for x in range(256)]
        for y in range(240)
    ]
    # Should not raise
    ui.render(pixels)


def test_window_scale_dimensions() -> None:
    """Verify window dimensions match scale factor."""
    ui_obj = UI(scale=4)
    assert ui_obj._window_width == 1024
    assert ui_obj._window_height == 960
