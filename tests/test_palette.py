"""Unit tests for the Palette module."""

import pytest
from palette import SYSTEM_PALETTE


def test_palette_length() -> None:
    """The system palette must contain exactly 64 entries."""
    assert len(SYSTEM_PALETTE) == 64, f"Expected 64 colors, got {len(SYSTEM_PALETTE)}"


def test_all_entries_are_rgb_tuples() -> None:
    """Every entry must be a 3-element tuple of ints."""
    for i, entry in enumerate(SYSTEM_PALETTE):
        assert isinstance(entry, tuple), f"Entry {i} is not a tuple"
        assert len(entry) == 3, f"Entry {i} does not have 3 values"
        assert all(isinstance(v, int) for v in entry), (
            f"Entry {i} has non-integer value"
        )


def test_all_values_in_range() -> None:
    """All R, G, B values must be in 0–255 range."""
    for i, (r, g, b) in enumerate(SYSTEM_PALETTE):
        assert 0 <= r <= 255, f"Entry 0x{i:02X}: R={r} out of range"
        assert 0 <= g <= 255, f"Entry 0x{i:02X}: G={g} out of range"
        assert 0 <= b <= 255, f"Entry 0x{i:02X}: B={b} out of range"


def test_known_colors() -> None:
    """Spot-check several well-known NES palette entries."""
    # 0x0F should be black (mirror of 1D which is the "black emphasis" entry)
    # Note: 0x0D, 0x1D, 0x0F etc. are black in standard palette
    assert SYSTEM_PALETTE[0x0F] in [
        (0x00, 0x00, 0x00),
    ], f"0x0F should be black, got {SYSTEM_PALETTE[0x0F]}"

    # 0x20 should be light gray / near white
    r, g, b = SYSTEM_PALETTE[0x20]
    assert r >= 0xF0 and g >= 0xF0 and b >= 0xF0, (
        f"0x20 should be near white, got {SYSTEM_PALETTE[0x20]}"
    )

    # 0x30 should be pure white
    assert SYSTEM_PALETTE[0x30] == (0xFC, 0xFC, 0xFC), (
        f"0x30 expected pure white, got {SYSTEM_PALETTE[0x30]}"
    )

    # 0x16 is the classic Mario red/orange
    r, g, b = SYSTEM_PALETTE[0x16]
    assert r > 0xE0 and g < 0x80 and b == 0, (
        f"0x16 should be reddish-orange, got {SYSTEM_PALETTE[0x16]}"
    )
