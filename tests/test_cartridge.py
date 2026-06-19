"""Unit tests for the Cartridge module (iNES parsing + Mapper 0)."""

from __future__ import annotations

import os
import tempfile

import pytest
from cartridge import Cartridge


# ─── Helper: build an iNES ROM in a temp file ────────────────────────────────

def _make_ines(
    prg_pages: int = 1,
    chr_pages: int = 1,
    mapper: int = 0,
    mirroring: int = 0,
    trainer: bool = False,
    prg_data: bytes | None = None,
    chr_data: bytes | None = None,
) -> str:
    """Create a temporary .nes file and return its path.

    Args:
        prg_pages: Number of 16 KiB PRG ROM pages.
        chr_pages: Number of 8 KiB CHR ROM pages (0 = CHR RAM).
        mapper: Mapper number (default 0 = NROM).
        mirroring: 0=horizontal, 1=vertical.
        trainer: Whether to include a 512-byte trainer.
        prg_data: Raw PRG ROM bytes (padded/trimmed to page count).
        chr_data: Raw CHR ROM bytes (padded/trimmed to page count).

    Returns:
        Path to the temporary .nes file.
    """
    header = bytearray(16)
    header[0:4] = b"NES\x1A"
    header[4] = prg_pages & 0xFF
    header[5] = chr_pages & 0xFF
    # flags6: lower nibble = mapper low, bits 4-7 = mapper bits; bit 0 = mirroring; bit 2 = trainer
    flags6 = (mirroring & 0x01) | ((mapper & 0x0F) << 4)
    if trainer:
        flags6 |= 0x04
    # flags7: upper nibble = mapper high
    flags7 = mapper & 0xF0
    header[6] = flags6
    header[7] = flags7

    prg_chunk = bytearray(prg_pages * Cartridge.PRG_ROM_PAGE_SIZE)
    if prg_data:
        prg_chunk[: len(prg_data)] = prg_data

    chr_chunk = bytearray(chr_pages * Cartridge.CHR_ROM_PAGE_SIZE)
    if chr_data:
        chr_chunk[: len(chr_data)] = chr_data

    trainer_chunk = bytearray(Cartridge.TRAINER_SIZE) if trainer else bytearray()

    # Write to a temp file; we manage the path ourselves.
    fd, path = tempfile.mkstemp(suffix=".nes", prefix="test_")
    os.close(fd)
    with open(path, "wb") as f:
        f.write(header)
        if trainer_chunk:
            f.write(trainer_chunk)
        f.write(prg_chunk)
        f.write(chr_chunk)

    return path


# ─── Tests ───────────────────────────────────────────────────────────────────


class TestINESHeaderParsing:
    """Tests for iNES header validation and field extraction."""

    def test_valid_minimal_rom(self) -> None:
        """A minimal valid iNES file (1 PRG page, 1 CHR page) should load."""
        path = _make_ines(prg_pages=1, chr_pages=1)
        try:
            cart = Cartridge.load(path)
            assert cart is not None
            assert len(cart.prg_rom) == 16384
            assert cart.chr_rom is not None
            assert len(cart.chr_rom) == 8192
        finally:
            os.unlink(path)

    def test_invalid_magic_number(self) -> None:
        """A file without 'NES' + 0x1A magic should raise ValueError."""
        fd, path = tempfile.mkstemp(suffix=".nes", prefix="test_bad_")
        os.close(fd)
        with open(path, "wb") as f:
            f.write(b"NOT_A_NES_FILE\x00\x00\x00\x00")
        try:
            with pytest.raises(ValueError, match="不是有效的 iNES ROM"):
                Cartridge.load(path)
        finally:
            os.unlink(path)

    def test_file_not_found(self) -> None:
        """Loading a nonexistent file should raise FileNotFoundError."""
        with pytest.raises(FileNotFoundError, match="找不到 ROM 文件"):
            Cartridge.load("/nonexistent/path/rom.nes")

    def test_non_mapper_0_rejected(self) -> None:
        """Any mapper other than 0 must raise a ValueError."""
        for bad_mapper in (1, 3, 4, 7, 69):
            path = _make_ines(mapper=bad_mapper)
            try:
                with pytest.raises(ValueError, match="仅支持 Mapper 0"):
                    Cartridge.load(path)
            finally:
                os.unlink(path)

    def test_mirroring_horizontal(self) -> None:
        """Flags6 bit0=0 → horizontal mirroring."""
        path = _make_ines(mirroring=0)
        try:
            cart = Cartridge.load(path)
            assert cart.mirroring == "horizontal"
        finally:
            os.unlink(path)

    def test_mirroring_vertical(self) -> None:
        """Flags6 bit0=1 → vertical mirroring (Super Mario Bros default)."""
        path = _make_ines(mirroring=1)
        try:
            cart = Cartridge.load(path)
            assert cart.mirroring == "vertical"
        finally:
            os.unlink(path)

    def test_trainer_skipped(self) -> None:
        """When trainer bit is set, the 512-byte trainer should be skipped."""
        path = _make_ines(prg_pages=1, chr_pages=1, trainer=True)
        try:
            cart = Cartridge.load(path)
            assert len(cart.prg_rom) == 16384
            assert cart.chr_rom is not None
            assert len(cart.chr_rom) == 8192
        finally:
            os.unlink(path)


class TestPRGMapping:
    """Tests for CPU-side PRG ROM address mapping."""

    def test_32kib_prg_linear(self) -> None:
        """32 KiB PRG (2 pages) maps linearly to 0x8000–0xFFFF."""
        prg = bytearray(32768)
        # Fill with pattern: each byte = its offset within PRG
        for i in range(len(prg)):
            prg[i] = i & 0xFF

        path = _make_ines(prg_pages=2, prg_data=bytes(prg))
        try:
            cart = Cartridge.load(path)

            # 0x8000 → PRG[0]
            assert cart.cpu_read(0x8000) == prg[0]
            # 0x8001 → PRG[1]
            assert cart.cpu_read(0x8001) == prg[1]
            # 0xFFFF → PRG[32767]
            assert cart.cpu_read(0xFFFF) == prg[32767]
        finally:
            os.unlink(path)

    def test_16kib_prg_mirrored(self) -> None:
        """16 KiB PRG (1 page): 0x8000–0xBFFF → PRG, 0xC000–0xFFFF → mirrored."""
        prg = bytearray(16384)
        for i in range(len(prg)):
            prg[i] = i & 0xFF

        path = _make_ines(prg_pages=1, prg_data=bytes(prg))
        try:
            cart = Cartridge.load(path)

            # 0x8000 → PRG[0]
            assert cart.cpu_read(0x8000) == prg[0]
            # 0xBFFF → PRG[0x3FFF] (last byte)
            assert cart.cpu_read(0xBFFF) == prg[0x3FFF]
            # 0xC000 → mirrored PRG[0]
            assert cart.cpu_read(0xC000) == prg[0]
            # 0xFFFF → mirrored PRG[0x3FFF]
            assert cart.cpu_read(0xFFFF) == prg[0x3FFF]
        finally:
            os.unlink(path)

    def test_cpu_read_below_4020_returns_0(self) -> None:
        """Addresses below 0x4020 are not cartridge space and return 0 (open bus)."""
        path = _make_ines(prg_pages=1)
        try:
            cart = Cartridge.load(path)
            assert cart.cpu_read(0x0000) == 0
            assert cart.cpu_read(0x2000) == 0
            assert cart.cpu_read(0x4019) == 0
        finally:
            os.unlink(path)

    def test_cpu_write_ignored(self) -> None:
        """PRG ROM is read-only; cpu_write should not raise or change anything."""
        path = _make_ines(prg_pages=1)
        try:
            cart = Cartridge.load(path)
            before = cart.cpu_read(0x8000)
            cart.cpu_write(0x8000, 0x42)
            assert cart.cpu_read(0x8000) == before
        finally:
            os.unlink(path)


class TestCHRMapping:
    """Tests for PPU-side CHR ROM / CHR RAM mapping."""

    def test_chr_rom_read(self) -> None:
        """CHR ROM should return pattern table data."""
        chr_data = bytes(range(256)) * 32  # 8192 bytes total
        path = _make_ines(chr_pages=1, chr_data=chr_data)
        try:
            cart = Cartridge.load(path)

            assert cart.cpu_read(0x4020) == 0  # open bus below PRG
            # CPU reads outside cartridge space return 0
            assert cart.cpu_read(0x0000) == 0
            # PPU reads
            assert cart.ppu_read(0x0000) == chr_data[0]
            assert cart.ppu_read(0x0001) == chr_data[1]
            assert cart.ppu_read(0x1FFF) == chr_data[8191]
            # Mirroring: 0x0000 mirrors to 0x0000 of 8 KiB
            assert cart.ppu_read(0x2000) == chr_data[0]  # mirror
        finally:
            os.unlink(path)

    def test_chr_ram_read_write(self) -> None:
        """CHR RAM mode (chr_pages=0) allows reading and writing."""
        path = _make_ines(chr_pages=0)
        try:
            cart = Cartridge.load(path)
            assert cart.chr_rom is None

            # Initially should be 0
            assert cart.ppu_read(0x0000) == 0

            # Write and read back
            cart.ppu_write(0x0000, 0xAB)
            assert cart.ppu_read(0x0000) == 0xAB

            # Mirroring
            cart.ppu_write(0x0008, 0xCD)
            assert cart.ppu_read(0x2008) == 0xCD
        finally:
            os.unlink(path)

    def test_chr_rom_write_ignored(self) -> None:
        """Writing to CHR ROM should be silently ignored."""
        path = _make_ines(chr_pages=1)
        try:
            cart = Cartridge.load(path)
            before = cart.ppu_read(0x0000)
            cart.ppu_write(0x0000, 0xFF)
            assert cart.ppu_read(0x0000) == before
        finally:
            os.unlink(path)


class TestProperties:
    """Tests for cartridge properties."""

    def test_prg_rom_property(self) -> None:
        """prg_rom should return the raw bytes."""
        prg = b"HELLO" + b"\x00" * 16379
        path = _make_ines(prg_pages=1, prg_data=prg)
        try:
            cart = Cartridge.load(path)
            assert cart.prg_rom[:5] == b"HELLO"
        finally:
            os.unlink(path)

    def test_chr_rom_property(self) -> None:
        """chr_rom returns raw CHR ROM bytes."""
        chr_data = b"CHRDATA" + b"\x00" * 8185
        path = _make_ines(chr_pages=1, chr_data=chr_data)
        try:
            cart = Cartridge.load(path)
            assert cart.chr_rom is not None
            assert cart.chr_rom[:7] == b"CHRDATA"
        finally:
            os.unlink(path)

    def test_chr_ram_property(self) -> None:
        """chr_ram returns writable bytearray when CHR_RAM mode."""
        path = _make_ines(chr_pages=0)
        try:
            cart = Cartridge.load(path)
            assert cart.chr_rom is None
            assert cart.chr_ram is not None
            assert len(cart.chr_ram) == 8192
        finally:
            os.unlink(path)
