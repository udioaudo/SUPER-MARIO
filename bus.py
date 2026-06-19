"""NES 16-bit address bus — routes CPU reads/writes to the correct device.

The NES memory map:

    Address           Device              Notes
    ────────────────────────────────────────────────
    0x0000–0x1FFF     CPU RAM             2 KiB mirrored
    0x2000–0x3FFF     PPU registers       8-byte register block mirrored
    0x4000–0x4013     APU registers
    0x4014            OAM DMA             Triggers 256-byte DMA to PPU OAM
    0x4015            APU register
    0x4016            Input (controller)
    0x4017            APU register
    0x4020–0xFFFF     Cartridge (PRG ROM) Mapper 0

The Bus tracks extra cycles consumed by OAM DMA via the ``dma_cycles`` property.
"""

from __future__ import annotations

from typing import Protocol

# ─── Device protocols (structural subtypes for duck typing) ──────────────────


class RAMProtocol(Protocol):
    """Protocol expected from RAM instances used by Bus."""

    def read(self, addr: int) -> int: ...
    def write(self, addr: int, value: int) -> None: ...


class PPUProtocol(Protocol):
    """Protocol expected from PPU instances used by Bus."""

    def read_register(self, addr: int) -> int: ...
    def write_register(self, addr: int, value: int) -> None: ...
    def oam_write(self, index: int, value: int) -> None: ...


class APUProtocol(Protocol):
    """Protocol expected from APU instances used by Bus."""

    def read_register(self, addr: int) -> int: ...
    def write_register(self, addr: int, value: int) -> None: ...


class InputProtocol(Protocol):
    """Protocol expected from Input instances used by Bus."""

    def read(self) -> int: ...
    def write(self, value: int) -> None: ...


class CartridgeProtocol(Protocol):
    """Protocol expected from Cartridge instances used by Bus."""

    def cpu_read(self, addr: int) -> int: ...
    def cpu_write(self, addr: int, value: int) -> None: ...
    def ppu_read(self, addr: int) -> int: ...
    def ppu_write(self, addr: int, value: int) -> None: ...


# ─── Bus ─────────────────────────────────────────────────────────────────────


class Bus:
    """The NES 16-bit address bus, connecting CPU to all memory-mapped devices."""

    # OAM DMA consumes 513 CPU cycles (1 dummy read + 256 alternating r/w = 512)
    OAM_DMA_CYCLES: int = 513

    def __init__(
        self,
        cpu_ram: RAMProtocol,
        ppu: PPUProtocol,
        apu: APUProtocol,
        cartridge: CartridgeProtocol,
        input_dev: InputProtocol,
    ) -> None:
        """Create a Bus connecting all devices.

        Args:
            cpu_ram: The 2 KiB CPU RAM instance.
            ppu: The PPU picture processing unit.
            apu: The APU audio processing unit.
            cartridge: The loaded Cartridge (with mapper 0).
            input_dev: The Input controller handler.
        """
        self._cpu_ram = cpu_ram
        self._ppu = ppu
        self._apu = apu
        self._cartridge = cartridge
        self._input = input_dev
        self._dma_cycles: int = 0

    # ─── Read ────────────────────────────────────────────────────────────────

    def read(self, addr: int, from_ppu: bool = False) -> int:
        """Read 1 byte from the given 16-bit address.

        Args:
            addr: 16-bit address to read from.
            from_ppu: If True, the PPU is the reader (routed to cartridge PPU bus).

        Returns:
            The byte read from the mapped device.
        """
        # PPU reads directly from cartridge CHR memory
        if from_ppu:
            return self._cartridge.ppu_read(addr)

        if addr <= 0x1FFF:
            return self._cpu_ram.read(addr)
        if addr <= 0x3FFF:
            return self._ppu.read_register(0x2000 + (addr % 8))
        if addr <= 0x4013 or addr == 0x4015:
            return self._apu.read_register(addr)
        if addr == 0x4016:
            return self._input.read()
        if addr == 0x4017:
            return self._apu.read_register(addr)
        return self._cartridge.cpu_read(addr)

    # ─── Write ───────────────────────────────────────────────────────────────

    def write(self, addr: int, value: int) -> None:
        """Write 1 byte to the given 16-bit address, routing to the correct device.

        Args:
            addr: 16-bit address to write to.
            value: 8-bit value to write.
        """
        value &= 0xFF

        if addr <= 0x1FFF:
            self._cpu_ram.write(addr, value)
        elif addr <= 0x3FFF:
            self._ppu.write_register(0x2000 + (addr % 8), value)
        elif addr <= 0x4013 or addr == 0x4015:
            self._apu.write_register(addr, value)
        elif addr == 0x4014:
            self._do_oam_dma(value)
        elif addr == 0x4016:
            self._input.write(value)
        elif addr == 0x4017:
            self._apu.write_register(addr, value)
        else:
            self._cartridge.cpu_write(addr, value)

    # ─── OAM DMA ─────────────────────────────────────────────────────────────

    def _do_oam_dma(self, value: int) -> None:
        """Execute OAM DMA: copy 256 bytes from CPU RAM page (value * 0x100) to PPU OAM.

        The DMA reads 256 bytes starting at address ``value << 8`` in CPU memory
        and writes each byte sequentially to PPU OAM (index 0–255).

        Args:
            value: High byte of the CPU RAM source address (page number).
        """
        base_addr = (value & 0xFF) << 8
        for i in range(256):
            data = self._cpu_ram.read(base_addr + i)
            self._ppu.oam_write(i, data)

        # Track the 513 CPU cycles consumed by the DMA
        self._dma_cycles += self.OAM_DMA_CYCLES

    # ─── Properties ──────────────────────────────────────────────────────────

    @property
    def dma_cycles(self) -> int:
        """Return and consume the accumulated OAM DMA cycle penalty.

        After reading, the counter is reset to 0 — the CPU should call this
        once per ``step()`` iteration and add the result to its cycle count.
        """
        extra = self._dma_cycles
        self._dma_cycles = 0
        return extra
