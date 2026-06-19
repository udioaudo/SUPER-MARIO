"""iNES ROM file parser and NROM (Mapper 0) cartridge emulation.

Supports only Mapper 0 (NROM) as used by Super Mario Bros.
Reference: https://www.nesdev.org/wiki/INES
"""

from __future__ import annotations

import os


class Cartridge:
    """Represents an NROM (Mapper 0) NES cartridge loaded from a .nes ROM file."""

    # iNES file header constants
    HEADER_SIZE: int = 16
    PRG_ROM_PAGE_SIZE: int = 16384  # 16 KiB
    CHR_ROM_PAGE_SIZE: int = 8192  # 8 KiB
    TRAINER_SIZE: int = 512

    def __init__(self) -> None:
        """Create an empty cartridge. Use `Cartridge.load(filepath)` to populate."""
        self._prg_rom: bytes = b""
        self._chr_rom: bytes | None = None
        self._chr_ram: bytearray | None = None
        self._mirroring: str = "horizontal"
        self._prg_rom_size: int = 0
        self._chr_rom_size: int = 0

    @staticmethod
    def load(filepath: str) -> "Cartridge":
        """Parse a .nes iNES ROM file and return a Cartridge instance.

        Raises:
            FileNotFoundError: If the file does not exist.
            ValueError: If the file has an invalid magic number.
            ValueError: If the mapper is not 0 (NROM).

        Returns:
            A new Cartridge with PRG/CHR ROM loaded.
        """
        if not os.path.isfile(filepath):
            raise FileNotFoundError(f"错误：找不到 ROM 文件 '{filepath}'")

        with open(filepath, "rb") as f:
            header = f.read(Cartridge.HEADER_SIZE)

        if len(header) < Cartridge.HEADER_SIZE:
            raise ValueError(
                f"错误：'{filepath}' 不是有效的 iNES ROM 文件（文件头不足 16 字节）"
            )

        # Validate magic number: "NES" + 0x1A
        if header[0:4] != b"NES\x1A":
            raise ValueError(
                f"错误：'{filepath}' 不是有效的 iNES ROM 文件"
            )

        cart = Cartridge()

        cart._prg_rom_size = header[4]
        cart._chr_rom_size = header[5]

        flags6 = header[6]
        flags7 = header[7]

        # Determine mirroring from flags6 bit 0
        cart._mirroring = "vertical" if (flags6 & 0x01) else "horizontal"

        # Compute mapper number: flags6 bits 3–0 (lower nibble) + flags7 bits 7–4 (upper nibble)
        mapper = (flags7 & 0xF0) | ((flags6 & 0xF0) >> 4)

        if mapper != 0:
            raise ValueError(
                f"错误：仅支持 Mapper 0 (NROM)，当前 ROM Mapper 号为 {mapper}"
            )

        # Skip trainer if present (flags6 bit 2)
        trainer_present = bool(flags6 & 0x04)

        with open(filepath, "rb") as f:
            offset = Cartridge.HEADER_SIZE
            if trainer_present:
                offset += Cartridge.TRAINER_SIZE
            f.seek(offset)

            prg_size = cart._prg_rom_size * Cartridge.PRG_ROM_PAGE_SIZE
            cart._prg_rom = f.read(prg_size)

            chr_size = cart._chr_rom_size * Cartridge.CHR_ROM_PAGE_SIZE
            if cart._chr_rom_size > 0:
                cart._chr_rom = f.read(chr_size)
            else:
                # CHR RAM mode: allocate writable 8 KiB
                cart._chr_ram = bytearray(Cartridge.CHR_ROM_PAGE_SIZE)

        return cart

    # ─── CPU memory bus (0x4020–0xFFFF) ──────────────────────────────────────

    def cpu_read(self, addr: int) -> int:
        """Read 1 byte from the CPU-side cartridge address space.

        Args:
            addr: Address in range 0x4020–0xFFFF. For NROM, PRG ROM sits at
                  0x8000–0xFFFF (or 0xC000–0xFFFF for 16 KiB with mirroring).
                  Reads below 0x4020 return 0 (open bus).

        Returns:
            Byte value at the mapped address.
        """
        if addr < 0x4020:
            return 0

        # Only map addresses >= 0x4020, but NROM PRG ROM is 0x8000+
        prg_len = len(self._prg_rom)
        if prg_len == 0:
            return 0
        mapped = (addr - 0x8000) % prg_len
        return self._prg_rom[mapped]

    def cpu_write(self, addr: int, value: int) -> None:
        """Write to CPU-side cartridge space. NROM PRG ROM is read-only — ignored.

        Args:
            addr: Write address.
            value: Value to write (discarded for NROM).
        """
        # NROM PRG ROM is read-only; writes are silently ignored.

    # ─── PPU memory bus (0x0000–0x1FFF) ──────────────────────────────────────

    def ppu_read(self, addr: int) -> int:
        """Read 1 byte from the PPU-side cartridge address space (pattern tables).

        Args:
            addr: Address in range 0x0000–0x1FFF. Maps to CHR ROM or CHR RAM.

        Returns:
            Byte value at the mapped address.
        """
        if self._chr_rom is not None:
            return self._chr_rom[addr % len(self._chr_rom)]
        if self._chr_ram is not None:
            return self._chr_ram[addr % len(self._chr_ram)]
        return 0

    def ppu_write(self, addr: int, value: int) -> None:
        """Write to PPU-side cartridge space. Only effective in CHR RAM mode.

        Args:
            addr: Write address in range 0x0000–0x1FFF.
            value: Byte value to write (0–255).
        """
        if self._chr_ram is not None:
            self._chr_ram[addr % len(self._chr_ram)] = value & 0xFF
        # CHR ROM is read-only; writes are silently ignored.

    # ─── Properties ──────────────────────────────────────────────────────────

    @property
    def mirroring(self) -> str:
        """Return the nametable mirroring mode: 'horizontal' or 'vertical'.

        - Horizontal: NT0↔NT1, NT2↔NT3 (vertical arrangement).
        - Vertical: NT0↔NT2, NT1↔NT3 (horizontal arrangement).

        Super Mario Bros uses vertical mirroring.
        """
        return self._mirroring

    @property
    def prg_rom(self) -> bytes:
        """Return the raw PRG ROM data."""
        return self._prg_rom

    @property
    def chr_rom(self) -> bytes | None:
        """Return the raw CHR ROM data, or None if using CHR RAM."""
        return self._chr_rom

    @property
    def chr_ram(self) -> bytearray | None:
        """Return the CHR RAM, or None if using CHR ROM."""
        return self._chr_ram
