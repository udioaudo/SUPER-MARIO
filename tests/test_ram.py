"""Unit tests for the RAM module."""

import pytest
from ram import RAM


@pytest.fixture
def ram() -> RAM:
    """Provide a fresh RAM instance for each test."""
    return RAM()


def test_initial_state_read_zero(ram: RAM) -> None:
    """All bytes should read as 0 immediately after initialization."""
    assert ram.read(0x0000) == 0
    assert ram.read(0x07FF) == 0
    assert ram.read(0x0005) == 0


def test_basic_read_write(ram: RAM) -> None:
    """Writing a value to an address and reading it back should return the same value."""
    ram.write(0x0000, 0x42)
    assert ram.read(0x0000) == 0x42

    ram.write(0x0001, 0xFF)
    assert ram.read(0x0001) == 0xFF

    ram.write(0x07FF, 0xAB)
    assert ram.read(0x07FF) == 0xAB


def test_address_mirroring(ram: RAM) -> None:
    """Writing to a mirrored address should be visible at the base address."""
    ram.write(0x0800, 0x99)
    assert ram.read(0x0000) == 0x99

    ram.write(0x1000, 0x77)
    assert ram.read(0x0000) == 0x77

    ram.write(0x1FFF, 0x55)
    assert ram.read(0x07FF) == 0x55

    # Writing at base should be visible at mirrored addresses too
    ram.write(0x0005, 0xEE)
    assert ram.read(0x0805) == 0xEE
    assert ram.read(0x1005) == 0xEE


def test_value_truncation(ram: RAM) -> None:
    """Values above 0xFF should be truncated to 8 bits."""
    ram.write(0x0000, 0x1FF)  # 0x1FF & 0xFF = 0xFF
    assert ram.read(0x0000) == 0xFF

    ram.write(0x0000, 0x342)  # 0x342 & 0xFF = 0x42
    assert ram.read(0x0000) == 0x42

    ram.write(0x0000, 0x100)  # 0x100 & 0xFF = 0x00
    assert ram.read(0x0000) == 0x00


def test_multiple_addresses_independent(ram: RAM) -> None:
    """Writing to different addresses should not interfere with each other."""
    ram.write(0x0000, 0x11)
    ram.write(0x0001, 0x22)
    ram.write(0x0002, 0x33)
    assert ram.read(0x0000) == 0x11
    assert ram.read(0x0001) == 0x22
    assert ram.read(0x0002) == 0x33
