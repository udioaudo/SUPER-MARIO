"""Unit tests for the Bus module (address routing + OAM DMA)."""

from __future__ import annotations

from bus import Bus


# ─── Mock device classes ─────────────────────────────────────────────────────


class MockRAM:
    """Mock CPU RAM that records writes and returns programmed values."""

    def __init__(self) -> None:
        self._data: bytearray = bytearray(2048)
        self._last_write_addr: int | None = None
        self._last_write_value: int | None = None
        self._write_count: int = 0

    def read(self, addr: int) -> int:
        return self._data[addr % 2048]

    def write(self, addr: int, value: int) -> None:
        self._data[addr % 2048] = value & 0xFF
        self._last_write_addr = addr
        self._last_write_value = value & 0xFF
        self._write_count += 1


class MockPPU:
    """Mock PPU that records register reads/writes."""

    def __init__(self) -> None:
        self.registers: dict[int, int] = {}
        self.read_register_calls: list[int] = []
        self.write_register_calls: list[tuple[int, int]] = []
        self.oam_data: bytearray = bytearray(256)
        self.oam_write_calls: list[tuple[int, int]] = []

    def read_register(self, addr: int) -> int:
        self.read_register_calls.append(addr)
        return self.registers.get(addr, 0)

    def write_register(self, addr: int, value: int) -> None:
        self.write_register_calls.append((addr, value))
        self.registers[addr] = value & 0xFF

    def oam_write(self, index: int, value: int) -> None:
        self.oam_data[index] = value & 0xFF
        self.oam_write_calls.append((index, value & 0xFF))


class MockAPU:
    """Mock APU that records register reads/writes."""

    def __init__(self) -> None:
        self.registers: dict[int, int] = {}
        self.read_calls: list[int] = []
        self.write_calls: list[tuple[int, int]] = []

    def read_register(self, addr: int) -> int:
        self.read_calls.append(addr)
        return self.registers.get(addr, 0)

    def write_register(self, addr: int, value: int) -> None:
        self.write_calls.append((addr, value & 0xFF))
        self.registers[addr] = value & 0xFF


class MockCartridge:
    """Mock Cartridge for Bus routing tests."""

    def __init__(self) -> None:
        self.cpu_read_calls: list[int] = []
        self.cpu_write_calls: list[tuple[int, int]] = []
        self.ppu_read_calls: list[int] = []
        self.ppu_write_calls: list[tuple[int, int]] = []

    def cpu_read(self, addr: int) -> int:
        self.cpu_read_calls.append(addr)
        return 0xAA  # arbitrary

    def cpu_write(self, addr: int, value: int) -> None:
        self.cpu_write_calls.append((addr, value))

    def ppu_read(self, addr: int) -> int:
        self.ppu_read_calls.append(addr)
        return 0xBB

    def ppu_write(self, addr: int, value: int) -> None:
        self.ppu_write_calls.append((addr, value))


class MockInput:
    """Mock Input device for Bus routing tests."""

    def __init__(self) -> None:
        self.read_calls: int = 0
        self.write_calls: list[int] = []
        self._next_read: int = 0x40

    def read(self) -> int:
        self.read_calls += 1
        return self._next_read

    def write(self, value: int) -> None:
        self.write_calls.append(value)


# ─── Helper ──────────────────────────────────────────────────────────────────


def _make_bus() -> tuple[Bus, MockRAM, MockPPU, MockAPU, MockCartridge, MockInput]:
    """Create a Bus with all mock devices."""
    ram = MockRAM()
    ppu = MockPPU()
    apu = MockAPU()
    cartridge = MockCartridge()
    input_dev = MockInput()
    bus = Bus(cpu_ram=ram, ppu=ppu, apu=apu, cartridge=cartridge, input_dev=input_dev)
    return bus, ram, ppu, apu, cartridge, input_dev


# ─── Tests: RAM routing ──────────────────────────────────────────────────────


class TestRAMRouting:
    """Address range 0x0000–0x1FFF should route to CPU RAM."""

    def test_write_to_ram(self) -> None:
        bus, ram, _, _, _, _ = _make_bus()
        bus.write(0x0000, 0x42)
        assert ram.read(0x0000) == 0x42

    def test_read_from_ram(self) -> None:
        bus, ram, _, _, _, _ = _make_bus()
        ram.write(0x00FF, 0x77)
        assert bus.read(0x00FF) == 0x77

    def test_ram_mirroring_via_bus(self) -> None:
        """Writing to 0x0800 should be visible at 0x0000 (RAM internal mirroring)."""
        bus, ram, _, _, _, _ = _make_bus()
        bus.write(0x0800, 0x88)
        assert bus.read(0x0000) == 0x88


# ─── Tests: PPU routing ──────────────────────────────────────────────────────


class TestPPURouting:
    """Address range 0x2000–0x3FFF should route to PPU registers."""

    def test_write_to_ppu_register(self) -> None:
        bus, _, ppu, _, _, _ = _make_bus()
        bus.write(0x2000, 0x81)
        assert ppu.write_register_calls == [(0x2000, 0x81)]

    def test_read_from_ppu_register(self) -> None:
        bus, _, ppu, _, _, _ = _make_bus()
        ppu.registers[0x2002] = 0x80
        result = bus.read(0x2002)
        assert result == 0x80
        assert 0x2002 in ppu.read_register_calls

    def test_ppu_register_mirror_0x2008_to_0x2000(self) -> None:
        """Address 0x2008 should mirror to PPU register 0x2000."""
        bus, _, ppu, _, _, _ = _make_bus()
        bus.write(0x2008, 0xFF)
        assert ppu.write_register_calls[0] == (0x2000, 0xFF)

    def test_ppu_register_mirror_0x3FFF_to_0x2007(self) -> None:
        """Address 0x3FFF should mirror to PPU register 0x2007."""
        bus, _, ppu, _, _, _ = _make_bus()
        bus.write(0x3FFF, 0xAB)
        assert ppu.write_register_calls[0] == (0x2007, 0xAB)


# ─── Tests: APU routing ──────────────────────────────────────────────────────


class TestAPURouting:
    """Addresses 0x4000–0x4013, 0x4015, 0x4017 should route to APU."""

    def test_write_to_apu(self) -> None:
        bus, _, _, apu, _, _ = _make_bus()
        bus.write(0x4000, 0x9F)
        assert apu.write_calls == [(0x4000, 0x9F)]

    def test_read_from_apu(self) -> None:
        bus, _, _, apu, _, _ = _make_bus()
        apu.registers[0x4015] = 0x0F
        result = bus.read(0x4015)
        assert result == 0x0F

    def test_write_0x4017_to_apu(self) -> None:
        bus, _, _, apu, _, _ = _make_bus()
        bus.write(0x4017, 0xC0)
        assert apu.write_calls == [(0x4017, 0xC0)]


# ─── Tests: Input routing ────────────────────────────────────────────────────


class TestInputRouting:
    """Address 0x4016 should route to Input device."""

    def test_write_to_input(self) -> None:
        bus, _, _, _, _, inp = _make_bus()
        bus.write(0x4016, 1)
        assert inp.write_calls == [1]

    def test_read_from_input(self) -> None:
        bus, _, _, _, _, inp = _make_bus()
        result = bus.read(0x4016)
        assert inp.read_calls == 1
        assert result == 0x40  # default from mock


# ─── Tests: Cartridge routing ────────────────────────────────────────────────


class TestCartridgeRouting:
    """Addresses 0x4020–0xFFFF should route to Cartridge."""

    def test_write_to_cartridge(self) -> None:
        bus, _, _, _, cart, _ = _make_bus()
        bus.write(0x8000, 0x12)
        assert cart.cpu_write_calls == [(0x8000, 0x12)]

    def test_read_from_cartridge(self) -> None:
        bus, _, _, _, cart, _ = _make_bus()
        result = bus.read(0x8000)
        assert cart.cpu_read_calls == [0x8000]
        assert result == 0xAA

    def test_read_from_ppu_perspective(self) -> None:
        """When from_ppu=True, routes to cartridge.ppu_read()."""
        bus, _, _, _, cart, _ = _make_bus()
        result = bus.read(0x1000, from_ppu=True)
        assert cart.ppu_read_calls == [0x1000]
        assert result == 0xBB


# ─── Tests: OAM DMA ──────────────────────────────────────────────────────────


class TestOAMDMA:
    """Writing 0x4014 triggers OAM DMA (256 bytes from RAM page to PPU OAM)."""

    def test_oam_dma_transfers_256_bytes(self) -> None:
        bus, ram, ppu, _, _, _ = _make_bus()
        # Fill RAM with ascending values starting at page 0x02
        for i in range(256):
            ram.write(0x0200 + i, i + 1)

        bus.write(0x4014, 0x02)

        # Verify 256 bytes were copied to PPU OAM
        assert len(ppu.oam_write_calls) == 256
        for i in range(256):
            assert ppu.oam_data[i] == (i + 1) & 0xFF

    def test_oam_dma_returns_correct_cycles(self) -> None:
        bus, ram, _, _, _, _ = _make_bus()

        # Trigger DMA
        bus.write(0x4014, 0x00)

        # dma_cycles should be 513
        assert bus.dma_cycles == 513
        # Reading dma_cycles should reset it
        assert bus.dma_cycles == 0

    def test_oam_dma_cycles_accumulate_over_multiple_dmas(self) -> None:
        bus, _, _, _, _, _ = _make_bus()

        bus.write(0x4014, 0x00)
        bus.write(0x4014, 0x01)

        # Two DMAs = 1026 cycles
        assert bus.dma_cycles == 1026


# ─── Tests: value clamping ───────────────────────────────────────────────────


class TestValueClamping:
    """Values written via bus.write should be clamped to 8 bits."""

    def test_write_clamps_to_8bit(self) -> None:
        bus, ram, _, _, _, _ = _make_bus()
        bus.write(0x0000, 0x1FF)
        assert ram.read(0x0000) == 0xFF
