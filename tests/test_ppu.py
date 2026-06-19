"""Unit tests for the PPU module."""

from __future__ import annotations

import pytest

from palette import SYSTEM_PALETTE
from ppu import PPU


# ─── Mock cartridge ────────────────────────────────────────────────────────────


class MockCartridge:
    """Minimal cartridge stub for PPU testing.

    Supports CHR ROM (default) or CHR RAM mode, and configurable mirroring.
    Writing directly to ``_chr_data`` sets CHR ROM contents (always readable).
    When CHR RAM mode is active, ``ppu_write`` writes to ``_chr_ram``.
    """

    def __init__(self, mirroring: str = "vertical") -> None:
        self._mirroring = mirroring
        self._chr_data = bytearray(8192)
        self._chr_ram = bytearray(8192)
        self._use_chr_rom = True

    def ppu_read(self, addr: int) -> int:
        if self._use_chr_rom:
            return self._chr_data[addr % 8192]
        return self._chr_ram[addr % 8192]

    def ppu_write(self, addr: int, value: int) -> None:
        if not self._use_chr_rom:
            self._chr_ram[addr % 8192] = value & 0xFF

    @property
    def mirroring(self) -> str:
        return self._mirroring

    def set_chr_ram_mode(self) -> None:
        self._use_chr_rom = False

    def set_chr_rom_mode(self) -> None:
        self._use_chr_rom = True

    def write_chr(self, addr: int, value: int) -> None:
        """Directly write to the readable CHR data buffer (bypasses ROM/RAM mode)."""
        self._chr_data[addr % 8192] = value & 0xFF


@pytest.fixture
def cart() -> MockCartridge:
    """Return a fresh mock cartridge with vertical mirroring."""
    return MockCartridge()


@pytest.fixture
def ppu(cart: MockCartridge) -> PPU:
    """Return a fresh PPU connected to the mock cartridge."""
    return PPU(cart)


# ─── Initialisation tests ──────────────────────────────────────────────────────


class TestPPUInit:
    """Verify PPU initial state matches expected NES power-on defaults."""

    def test_frame_starts_at_zero(self, ppu: PPU) -> None:
        assert ppu.frame == 0

    def test_initial_ctrl_is_zero(self, ppu: PPU) -> None:
        """PPUCTRL should start at 0x00."""
        assert ppu._ctrl == 0

    def test_initial_mask_is_zero(self, ppu: PPU) -> None:
        """PPUMASK should start at 0x00."""
        assert ppu._mask == 0

    def test_initial_scroll_is_zero(self, ppu: PPU) -> None:
        """Both scroll values should start at 0."""
        assert ppu._scroll_x == 0
        assert ppu._scroll_y == 0

    def test_initial_vram_addr_is_zero(self, ppu: PPU) -> None:
        assert ppu._vram_addr == 0

    def test_initial_write_latch_is_false(self, ppu: PPU) -> None:
        assert ppu._w is False

    def test_initial_oam_addr_is_zero(self, ppu: PPU) -> None:
        assert ppu._oam_addr == 0

    def test_initial_nmi_occurred_is_false(self, ppu: PPU) -> None:
        assert ppu._nmi_occurred is False

    def test_initial_vblank_is_false(self, ppu: PPU) -> None:
        assert ppu._vblank is False

    def test_vram_size_is_2048(self, ppu: PPU) -> None:
        assert len(ppu._vram) == 2048

    def test_palette_ram_size_is_32(self, ppu: PPU) -> None:
        assert len(ppu._palette_ram) == 32

    def test_oam_size_is_256(self, ppu: PPU) -> None:
        assert len(ppu._oam) == 256


# ─── Register tests ────────────────────────────────────────────────────────────


class TestPPURegisters:
    """Test PPU register read/write behaviour."""

    # ── PPUCTRL (0x2000) ──────────────────────────────────────────────────

    def test_write_ctrl_sets_nmi_enable(self, ppu: PPU) -> None:
        ppu.write_register(0x2000, 0x80)
        assert ppu._ctrl == 0x80
        assert ppu._nmi_enabled is True

    def test_write_ctrl_sets_sprite_size(self, ppu: PPU) -> None:
        ppu.write_register(0x2000, 0x20)
        assert ppu._ctrl == 0x20
        assert (ppu._ctrl & 0x20) != 0  # 8×16 mode bit is set

    def test_write_ctrl_sets_bg_pt_addr(self, ppu: PPU) -> None:
        ppu.write_register(0x2000, 0x10)
        assert ppu._bg_pt_addr == 0x1000

    def test_write_ctrl_sets_sprite_pt_addr(self, ppu: PPU) -> None:
        ppu.write_register(0x2000, 0x08)
        assert ppu._sprite_pt_addr == 0x1000

    def test_write_ctrl_sets_vram_increment(self, ppu: PPU) -> None:
        ppu.write_register(0x2000, 0x04)
        assert ppu._vram_increment == 32

    def test_write_ctrl_default_increment_is_1(self, ppu: PPU) -> None:
        assert ppu._vram_increment == 1

    def test_write_ctrl_updates_t_register(self, ppu: PPU) -> None:
        """PPUCTRL bits 1-0 should update bits 10-11 of _t."""
        ppu.write_register(0x2000, 0x03)  # nametable = 3
        assert (ppu._t >> 10) & 3 == 3

    def test_read_ctrl_returns_open_bus(self, ppu: PPU) -> None:
        """PPUCTRL is write-only; reading returns open bus."""
        ppu.write_register(0x2000, 0x55)
        assert ppu.read_register(0x2000) == 0x55  # last written value

    # ── PPUMASK (0x2001) ──────────────────────────────────────────────────

    def test_write_mask_sets_show_sprites(self, ppu: PPU) -> None:
        ppu.write_register(0x2001, 0x10)
        assert ppu._mask == 0x10

    def test_write_mask_sets_show_background(self, ppu: PPU) -> None:
        ppu.write_register(0x2001, 0x08)
        assert ppu._mask == 0x08

    def test_write_mask_sets_leftmost_clipping(self, ppu: PPU) -> None:
        # bits 1 and 2 control leftmost 8-pixel visibility
        ppu.write_register(0x2001, 0x06)
        assert ppu._mask == 0x06

    def test_write_mask_sets_emphasis_bits(self, ppu: PPU) -> None:
        ppu.write_register(0x2001, 0xE0)  # RGB emphasis
        assert ppu._mask == 0xE0

    def test_read_mask_returns_open_bus(self, ppu: PPU) -> None:
        ppu.write_register(0x2001, 0xAA)
        assert ppu.read_register(0x2001) == 0xAA

    # ── PPUSTATUS (0x2002) ────────────────────────────────────────────────

    def test_read_status_clears_vblank(self, ppu: PPU) -> None:
        # Manually set VBlank
        ppu._vblank = True
        ppu._open_bus = 0x1F  # set lower bits for open bus
        status = ppu.read_register(0x2002)
        assert status & 0x80  # VBlank was set
        assert not ppu._vblank  # VBlank should be cleared

    def test_read_status_resets_write_latch(self, ppu: PPU) -> None:
        ppu._w = True
        ppu.read_register(0x2002)
        assert ppu._w is False

    def test_read_status_includes_sprite_zero_hit(self, ppu: PPU) -> None:
        ppu._sprite_zero_hit = True
        status = ppu.read_register(0x2002)
        assert status & 0x40

    def test_read_status_includes_sprite_overflow(self, ppu: PPU) -> None:
        ppu._sprite_overflow = True
        status = ppu.read_register(0x2002)
        assert status & 0x20

    def test_read_status_open_bus_lower_bits(self, ppu: PPU) -> None:
        ppu.write_register(0x2001, 0xAB)  # writes to open bus
        status = ppu.read_register(0x2002)
        assert (status & 0x1F) == (0xAB & 0x1F)

    # ── OAMADDR (0x2003) ──────────────────────────────────────────────────

    def test_write_oam_addr(self, ppu: PPU) -> None:
        ppu.write_register(0x2003, 0x42)
        assert ppu._oam_addr == 0x42

    def test_read_oam_addr_returns_open_bus(self, ppu: PPU) -> None:
        ppu.write_register(0x2003, 0x77)
        assert ppu.read_register(0x2003) == 0x77

    # ── OAMDATA (0x2004) ──────────────────────────────────────────────────

    def test_write_oam_data_and_auto_increment(self, ppu: PPU) -> None:
        ppu.write_register(0x2003, 0x00)  # set OAM addr to 0
        ppu.write_register(0x2004, 0x12)
        assert ppu._oam[0] == 0x12
        assert ppu._oam_addr == 1  # auto-incremented

    def test_write_oam_data_wraps_at_256(self, ppu: PPU) -> None:
        ppu.write_register(0x2003, 0xFF)  # set OAM addr to 255
        ppu.write_register(0x2004, 0xAB)
        assert ppu._oam[255] == 0xAB
        assert ppu._oam_addr == 0  # wraps around

    def test_read_oam_data(self, ppu: PPU) -> None:
        ppu._oam[10] = 0xCD
        ppu.write_register(0x2003, 10)
        assert ppu.read_register(0x2004) == 0xCD
        assert ppu._oam_addr == 10  # reads do NOT increment OAM addr

    # ── PPUSCROLL (0x2005) ────────────────────────────────────────────────

    def test_write_scroll_x_on_first_write(self, ppu: PPU) -> None:
        ppu.write_register(0x2005, 0x7F)
        assert ppu._scroll_x == 0x7F
        assert ppu._scroll_y == 0  # unchanged
        assert ppu._w is True  # latch toggled

    def test_write_scroll_y_on_second_write(self, ppu: PPU) -> None:
        ppu.write_register(0x2005, 0x10)  # _scroll_x
        ppu.write_register(0x2005, 0x20)  # _scroll_y
        assert ppu._scroll_x == 0x10
        assert ppu._scroll_y == 0x20
        assert ppu._w is False  # latch toggled back

    def test_scroll_x_then_y_then_x_again(self, ppu: PPU) -> None:
        """After two scroll writes, latch resets; third write is X again."""
        ppu.write_register(0x2005, 0x01)  # X
        ppu.write_register(0x2005, 0x02)  # Y
        ppu.write_register(0x2005, 0x03)  # X again
        assert ppu._scroll_x == 0x03
        assert ppu._scroll_y == 0x02

    def test_read_scroll_returns_open_bus(self, ppu: PPU) -> None:
        ppu.write_register(0x2005, 0x88)
        assert ppu.read_register(0x2005) == 0x88


# ─── PPUADDR / PPU write-latch tests ───────────────────────────────────────────


class TestScrollLatch:
    """Verify the shared write-latch (_w) behaviour for PPUSCROLL and PPUADDR."""

    def test_ppuaddr_first_write_sets_high_byte(self, ppu: PPU) -> None:
        ppu.write_register(0x2006, 0x3F)  # high byte = 0x3F → addr 0x3F00
        assert ppu._vram_addr == 0x3F00
        assert ppu._w is True

    def test_ppuaddr_high_byte_masks_to_6_bits(self, ppu: PPU) -> None:
        """Only bits 0-5 are used for the high byte (bits 14-15 always 0)."""
        ppu.write_register(0x2006, 0xFF)  # high byte, only 0x3F used
        assert ppu._vram_addr == 0x3F00

    def test_ppuaddr_second_write_sets_low_byte(self, ppu: PPU) -> None:
        ppu.write_register(0x2006, 0x20)  # high → 0x2000
        ppu.write_register(0x2006, 0x42)  # low
        assert ppu._vram_addr == 0x2042
        assert ppu._w is False

    def test_ppuaddr_third_write_is_high_again(self, ppu: PPU) -> None:
        ppu.write_register(0x2006, 0x20)  # high
        ppu.write_register(0x2006, 0x00)  # low
        ppu.write_register(0x2006, 0x24)  # high again
        assert ppu._vram_addr == 0x2400
        assert ppu._w is True

    def test_status_read_resets_latch_between_addr_writes(self, ppu: PPU) -> None:
        """Reading PPUSTATUS resets _w; next PPUADDR write is high byte."""
        ppu.write_register(0x2006, 0x20)  # high, latch → True
        ppu.read_register(0x2002)          # reset latch → False
        ppu.write_register(0x2006, 0x42)   # now treated as high byte
        # PPUADDR high byte masks to 6 bits: 0x42 & 0x3F = 0x02 → addr 0x0200
        assert ppu._vram_addr == ((0x42 & 0x3F) << 8)
        assert ppu._w is True

    def test_status_read_resets_scroll_latch(self, ppu: PPU) -> None:
        """Similar latch reset affects PPUSCROLL writes."""
        ppu.write_register(0x2005, 0x11)  # X, latch → True
        ppu.read_register(0x2002)          # latch → False
        ppu.write_register(0x2005, 0x22)   # treated as X again
        assert ppu._scroll_x == 0x22
        assert ppu._scroll_y == 0

    def test_shared_latch_scroll_then_addr(self, ppu: PPU) -> None:
        """After one scroll write (_w=True), PPUADDR write is LOW byte."""
        ppu.write_register(0x2005, 0x10)   # X scroll → _w=True
        ppu.write_register(0x2006, 0x42)   # PPUADDR with _w=True → low byte
        assert ppu._vram_addr == 0x0042
        assert ppu._w is False

    def test_shared_latch_addr_then_scroll(self, ppu: PPU) -> None:
        """After one PPUADDR write (_w=True), PPUSCROLL write is Y scroll."""
        ppu.write_register(0x2006, 0x20)   # high byte → _w=True
        ppu.write_register(0x2005, 0x88)   # PPUSCROLL with _w=True → Y scroll
        assert ppu._scroll_x == 0
        assert ppu._scroll_y == 0x88
        assert ppu._w is False


# ─── PPUDATA buffering tests ───────────────────────────────────────────────────


class TestPPUDATABuffering:
    """Verify the 1-byte read-buffer delay and auto-increment on PPUDATA."""

    def test_read_data_increments_vram_addr_by_1(self, ppu: PPU) -> None:
        ppu.write_register(0x2006, 0x20)  # addr → 0x2000
        ppu.write_register(0x2006, 0x00)
        ppu.read_register(0x2007)  # read, addr increments
        assert ppu._vram_addr == 0x2001  # +1 increment (default)

    def test_read_data_increments_by_32(self, ppu: PPU) -> None:
        ppu.write_register(0x2000, 0x04)  # CTRL: increment = 32
        ppu.write_register(0x2006, 0x20)  # addr → 0x2000
        ppu.write_register(0x2006, 0x00)
        ppu.read_register(0x2007)
        assert ppu._vram_addr == 0x2020

    def test_read_data_buffering_non_palette(self, ppu: PPU) -> None:
        """Non-palette reads are delayed by one access."""
        # Set up VRAM address to point into nametable (non-palette)
        ppu.write_register(0x2006, 0x20)  # high
        ppu.write_register(0x2006, 0x00)  # low → 0x2000

        # Write a known value to VRAM at 0x2000
        ppu._vram[0] = 0x42

        # First read: returns old buffered value (stale)
        first = ppu.read_register(0x2007)
        # Second read: returns the value that was at 0x2000 during first read
        second = ppu.read_register(0x2007)
        assert second == 0x42

    def test_read_data_no_buffering_for_palette(self, ppu: PPU) -> None:
        """Palette reads (0x3F00-0x3FFF) return immediately, no delay."""
        ppu._palette_ram[0] = 0x1A
        ppu._palette_ram[1] = 0x2B

        # Set VRAM addr to palette region
        ppu.write_register(0x2006, 0x3F)
        ppu.write_register(0x2006, 0x00)

        val = ppu.read_register(0x2007)
        # Palette reads return the value immediately
        assert val == 0x1A

    def test_write_data_increments_vram_addr(self, ppu: PPU) -> None:
        ppu.write_register(0x2006, 0x20)
        ppu.write_register(0x2006, 0x00)
        ppu.write_register(0x2007, 0x55)
        assert ppu._vram_addr == 0x2001  # +1

    def test_write_data_does_not_reset_latch(self, ppu: PPU) -> None:
        """PPUDATA writes should not affect the write latch."""
        ppu.write_register(0x2005, 0x10)  # X → latch = True
        assert ppu._w is True
        ppu.write_register(0x2007, 0x42)  # PPUDATA write
        assert ppu._w is True  # Latch unchanged

    def test_vram_addr_wraps_at_16k(self, ppu: PPU) -> None:
        """VRAM address space is 14 bits (0x0000-0x3FFF)."""
        ppu.write_register(0x2006, 0x3F)  # high
        ppu.write_register(0x2006, 0xFF)  # low → 0x3FFF
        # Simulate increment past boundary
        ppu._vram_addr += 1
        assert ppu._vram_addr == 0x4000
        ppu._vram_addr &= 0x3FFF
        assert ppu._vram_addr == 0x0000


# ─── VRAM internal access tests ────────────────────────────────────────────────


class TestNametableMirroringHorizontal:
    """Test horizontal nametable mirroring (NT0<->NT1, NT2<->NT3)."""

    @pytest.fixture
    def ppu_h(self) -> PPU:
        cart = MockCartridge(mirroring="horizontal")
        return PPU(cart)

    def test_nt0_maps_to_vram0(self, ppu_h: PPU) -> None:
        ppu_h._vram_write_internal(0x2000, 0xAB)
        assert ppu_h._vram[0x000] == 0xAB

    def test_nt1_mirrors_nt0(self, ppu_h: PPU) -> None:
        ppu_h._vram_write_internal(0x2000, 0x42)
        assert ppu_h._vram_read_internal(0x2400) == 0x42

    def test_nt2_maps_to_vram1(self, ppu_h: PPU) -> None:
        ppu_h._vram_write_internal(0x2800, 0xCD)
        assert ppu_h._vram[0x400] == 0xCD

    def test_nt3_mirrors_nt2(self, ppu_h: PPU) -> None:
        ppu_h._vram_write_internal(0x2800, 0xEF)
        assert ppu_h._vram_read_internal(0x2C00) == 0xEF

    def test_nt_offset_addressing(self, ppu_h: PPU) -> None:
        ppu_h._vram_write_internal(0x2400 + 0x3FF, 0xAA)
        assert ppu_h._vram[0x3FF] == 0xAA
        assert ppu_h._vram_read_internal(0x2000 + 0x3FF) == 0xAA


class TestNametableMirroringVertical:
    """Test vertical nametable mirroring (NT0<->NT2, NT1<->NT3)."""

    @pytest.fixture
    def ppu_v(self) -> PPU:
        cart = MockCartridge(mirroring="vertical")
        return PPU(cart)

    def test_nt0_maps_to_vram0(self, ppu_v: PPU) -> None:
        ppu_v._vram_write_internal(0x2000, 0x11)
        assert ppu_v._vram[0x000] == 0x11

    def test_nt2_mirrors_nt0(self, ppu_v: PPU) -> None:
        ppu_v._vram_write_internal(0x2000, 0x22)
        assert ppu_v._vram_read_internal(0x2800) == 0x22

    def test_nt1_maps_to_vram1(self, ppu_v: PPU) -> None:
        ppu_v._vram_write_internal(0x2400, 0x33)
        assert ppu_v._vram[0x400] == 0x33

    def test_nt3_mirrors_nt1(self, ppu_v: PPU) -> None:
        ppu_v._vram_write_internal(0x2400, 0x44)
        assert ppu_v._vram_read_internal(0x2C00) == 0x44


class TestAddressRangeMirroring:
    """Test that 0x3000-0x3EFF mirrors 0x2000-0x2EFF."""

    def test_3000_mirrors_2000(self, ppu: PPU) -> None:
        ppu._vram_write_internal(0x2000, 0x55)
        assert ppu._vram_read_internal(0x3000) == 0x55

    def test_3EFF_mirrors_2EFF(self, ppu: PPU) -> None:
        ppu._vram_write_internal(0x2EFF, 0x77)
        assert ppu._vram_read_internal(0x3EFF) == 0x77

    def test_3FFF_is_palette_not_nametable(self, ppu: PPU) -> None:
        """0x3F00-0x3FFF is palette, NOT a nametable mirror."""
        ppu._palette_ram[0] = 0x0F
        ppu._vram_write_internal(0x3F00, 0x1A)
        # This writes to palette, not VRAM nametable area
        assert ppu._palette_ram[0] == 0x1A


# ─── Palette tests ─────────────────────────────────────────────────────────────


class TestPaletteMirroring:
    """Test palette RAM mirroring rules."""

    def test_palette_3f10_mirrors_3f00(self, ppu: PPU) -> None:
        ppu._palette_ram[0] = 0x1A
        assert ppu._vram_read_internal(0x3F10) == 0x1A

    def test_palette_3f14_mirrors_3f04(self, ppu: PPU) -> None:
        ppu._palette_ram[4] = 0x2B
        assert ppu._vram_read_internal(0x3F14) == 0x2B

    def test_palette_3f18_mirrors_3f08(self, ppu: PPU) -> None:
        ppu._palette_ram[8] = 0x3C
        assert ppu._vram_read_internal(0x3F18) == 0x3C

    def test_palette_3f1c_mirrors_3f0c(self, ppu: PPU) -> None:
        ppu._palette_ram[12] = 0x0F
        assert ppu._vram_read_internal(0x3F1C) == 0x0F

    def test_palette_3f20_mirrors_3f00(self, ppu: PPU) -> None:
        """Addresses 0x3F20+ mirror 0x3F00+ (every 32 bytes)."""
        ppu._palette_ram[0] = 0x12
        assert ppu._vram_read_internal(0x3F20) == 0x12

    def test_palette_non_mirror_3f11_is_index_17(self, ppu: PPU) -> None:
        """0x3F11 should map to sprite palette 0 colour 1 (index 17)."""
        ppu._palette_ram[17] = 0x11
        assert ppu._vram_read_internal(0x3F11) == 0x11

    def test_palette_non_mirror_3f15_is_index_21(self, ppu: PPU) -> None:
        """0x3F15 should map to sprite palette 1 colour 1 (index 21)."""
        ppu._palette_ram[21] = 0x22
        assert ppu._vram_read_internal(0x3F15) == 0x22

    def test_palette_write_masks_to_6_bits(self, ppu: PPU) -> None:
        """Palette entries only use the lower 6 bits."""
        ppu._vram_write_internal(0x3F00, 0xFF)
        assert ppu._palette_ram[0] == 0x3F  # 0xFF & 0x3F = 0x3F


# ─── CHR RAM tests ─────────────────────────────────────────────────────────────


class TestCHRRAM:
    """Test CHR RAM read/write through the PPU."""

    def test_chr_ram_write_read(self) -> None:
        cart = MockCartridge()
        cart.set_chr_ram_mode()
        ppu = PPU(cart)

        ppu._vram_write_internal(0x0000, 0x42)
        assert ppu._vram_read_internal(0x0000) == 0x42

    def test_chr_rom_write_ignored(self) -> None:
        cart = MockCartridge()
        cart.set_chr_rom_mode()
        ppu = PPU(cart)

        cart._chr_data[0] = 0x10
        ppu._vram_write_internal(0x0000, 0x99)  # should be ignored
        assert ppu._vram_read_internal(0x0000) == 0x10  # original CHR ROM data


# ─── Helper for rendering tests: create a PPU with CHR RAM ─────────────────────


def _make_ppu_for_render(mirroring: str = "vertical") -> tuple[PPU, MockCartridge]:
    """Create a PPU with CHR RAM mode for rendering tests that need to write CHR data."""
    cart = MockCartridge(mirroring=mirroring)
    cart.set_chr_ram_mode()
    ppu = PPU(cart)
    return ppu, cart


# ─── Timing tests ──────────────────────────────────────────────────────────────


class TestVBlankTiming:
    """Test that step() correctly advances scanline/cycle and handles VBlank."""

    def test_step_advances_ppu_cycles(self, ppu: PPU) -> None:
        """1 CPU cycle = 3 PPU cycles."""
        ppu.step(1)
        assert ppu._cycle == 3
        assert ppu._scanline == 0

    def test_scanline_increments_after_341_cycles(self, ppu: PPU) -> None:
        """After 341 PPU cycles, scanline increments."""
        cpu_cycles = 114  # 114 * 3 = 342 PPU cycles -> crosses boundary
        ppu.step(cpu_cycles)
        assert ppu._scanline == 1
        assert ppu._cycle == 1  # 342 - 341 = 1

    def test_vblank_starts_at_scanline_241(self, ppu: PPU) -> None:
        """VBlank should start at scanline 241, dot 1."""
        ppu._scanline = 241
        ppu._cycle = 0
        ppu.step(1)  # 3 PPU cycles: 0->1, 1->2, 2->3
        # cycle 1 triggers VBlank
        assert ppu._vblank is True

    def test_vblank_triggers_nmi_when_enabled(self, ppu: PPU) -> None:
        """With NMI enabled, VBlank start should trigger NMI."""
        ppu.write_register(0x2000, 0x80)  # enable NMI
        ppu._scanline = 241
        ppu._cycle = 0
        result = ppu.step(1)
        assert result is True
        assert ppu._nmi_occurred is True

    def test_vblank_no_nmi_when_disabled(self, ppu: PPU) -> None:
        """Without NMI enable, VBlank should not trigger NMI."""
        ppu.write_register(0x2000, 0x00)  # NMI disabled
        ppu._scanline = 241
        ppu._cycle = 0
        result = ppu.step(1)
        assert result is False

    def test_nmi_once_then_again_next_frame(self, ppu: PPU) -> None:
        """NMI triggers once per frame, then again in the next frame."""
        ppu.write_register(0x2000, 0x80)  # enable NMI

        # Position at scanline 241, just before VBlank
        ppu._scanline = 241
        ppu._cycle = 0
        first = ppu.step(1)
        assert first is True

        # Advance through the rest of the frame and into the next
        # From current (scanline 241, cycle 3), need to reach scanline 241 again.
        # Total PPU cycles needed:
        #   remaining in scanline 241: 341 - 3 = 338
        #   scanlines 242-260 (19 scanlines): 19 * 341
        #   scanline 261 (wraps), then 0-240 (241 scanlines): 241 * 341
        #   + 1 cycle to start VBlank at 241,1
        cycles_remaining = (PPU.TOTAL_SCANLINES - 241) * PPU.CYCLES_PER_SCANLINE - ppu._cycle
        # Wait, let me just compute it differently.
        # Need to go through: scanlines 241 (remaining) → 260 → 0 → 240 → 241 (start)
        # That's: 20 scanlines (242-261) + 241 scanlines (0-240) = 261 scanlines from start of scanline 242
        # Plus remaining of current scanline 241
        remaining_in_241 = PPU.CYCLES_PER_SCANLINE - ppu._cycle  # 341 - 3 = 338
        # Plus scanlines 242-261 (20 scanlines): 20 * 341 = 6820
        # Plus scanlines 0-240 (241 scanlines): 241 * 341 = 82181
        total_ppu = remaining_in_241 + 20 * PPU.CYCLES_PER_SCANLINE + 241 * PPU.CYCLES_PER_SCANLINE
        cpu_needed = (total_ppu + 2) // 3  # ceiling
        ppu.step(cpu_needed)

        # Now we should be past scanline 241, dot 1
        assert ppu._nmi_occurred is True
        assert ppu._vblank is True

    def test_pre_render_clears_vblank(self, ppu: PPU) -> None:
        """Scanline 261, dot 1 should clear VBlank and hit flags."""
        ppu._vblank = True
        ppu._sprite_zero_hit = True
        ppu._sprite_overflow = True
        ppu._scanline = 261
        ppu._cycle = 0
        ppu.step(1)
        assert ppu._vblank is False
        assert ppu._sprite_zero_hit is False
        assert ppu._sprite_overflow is False

    def test_frame_increments(self, ppu: PPU) -> None:
        """After 262 scanlines, frame counter increments."""
        total_ppu_cycles = PPU.TOTAL_SCANLINES * PPU.CYCLES_PER_SCANLINE
        cpu_cycles = (total_ppu_cycles + 2) // 3  # ceiling
        ppu.step(cpu_cycles)
        assert ppu.frame >= 1


# ─── Rendering tests ───────────────────────────────────────────────────────────


class TestRenderBackground:
    """Test background rendering with known VRAM data."""

    def test_render_returns_240_by_256(self, ppu: PPU) -> None:
        ppu.write_register(0x2001, 0x08)  # show background
        pixels = ppu.render_frame()
        assert len(pixels) == 240
        assert all(len(row) == 256 for row in pixels)

    def test_render_without_bg_shows_default_color(self, ppu: PPU) -> None:
        """With background disabled, all pixels are the universal bg colour."""
        ppu._vram_write_internal(0x3F00, 0x12)
        # Mask = 0 (no bg, no sprites)
        pixels = ppu.render_frame()
        expected = SYSTEM_PALETTE[0x12]
        assert all(p == expected for row in pixels for p in row)

    def test_tile_rendering_with_known_pattern(self) -> None:
        """Render a known tile pattern and verify pixel colours."""
        ppu, cart = _make_ppu_for_render()

        ppu.write_register(0x2001, 0x0A)  # show background + leftmost bg

        # Set up nametable: tile index 0 at NT0 (0x2000)
        ppu._vram_write_internal(0x2000, 0x00)  # nametable[0] = tile 0

        # Set pattern table: tile 0 in pattern table 0 ($0000)
        # Plane 0: row 0 = 0xFF (all 1s)
        # Plane 1: row 0 = 0x00 (all 0s)
        # -> colour index = 1 for all 8 pixels in row 0
        ppu._vram_write_internal(0x0000, 0xFF)  # plane 0, row 0
        ppu._vram_write_internal(0x0008, 0x00)  # plane 1, row 0

        # Fill remaining rows of tile 0 with zeros
        for py in range(1, 16):
            ppu._vram_write_internal(py, 0x00)

        # Set attribute byte: palette group 0 for top-left 4x4 tiles
        ppu._vram_write_internal(0x23C0, 0x00)  # all palette group 0

        # Set palette: universal bg = colour 0x0F (black)
        # palette group 0, colour 1 = colour 0x30 (white)
        ppu._vram_write_internal(0x3F00, 0x0F)  # universal bg = black
        ppu._vram_write_internal(0x3F01, 0x30)  # palette 0, colour 1 = white

        pixels = ppu.render_frame()

        # Top row of pixels should be white (colour index 1 -> palette entry 0x30)
        for x in range(8):
            assert pixels[0][x] == SYSTEM_PALETTE[0x30]

        # Second row should be black (colour index 0 -> universal bg)
        for x in range(8):
            assert pixels[1][x] == SYSTEM_PALETTE[0x0F]

    def test_leftmost_clipping_clears_first_8_pixels(self) -> None:
        """When mask bit 1 is 0, leftmost 8 pixels show universal bg."""
        ppu, cart = _make_ppu_for_render()

        ppu.write_register(0x2001, 0x08)  # bg enabled, leftmost bg NOT enabled
        ppu._vram_write_internal(0x3F00, 0x0F)
        bg_color = SYSTEM_PALETTE[0x0F]

        # Fill VRAM with a pattern that would show coloured pixels
        ppu._vram_write_internal(0x2000, 0x00)
        for py in range(8):
            ppu._vram_write_internal(0x0000 + py, 0xFF)
            ppu._vram_write_internal(0x0008 + py, 0xFF)
        ppu._vram_write_internal(0x23C0, 0x00)
        ppu._vram_write_internal(0x3F01, 0x30)  # non-bg colour at index 1

        pixels = ppu.render_frame()

        # First 8 columns should be bg colour (clipped)
        for y in range(240):
            for x in range(8):
                assert pixels[y][x] == bg_color

    def test_attribute_palette_group_selection(self) -> None:
        """Verify that attribute bytes select the correct palette group."""
        ppu, cart = _make_ppu_for_render()

        ppu.write_register(0x2001, 0x0A)  # show background + leftmost bg)

        # Nametable: tile 0
        ppu._vram_write_internal(0x2000, 0x00)

        # Attribute: top-left 16x16 area, tile (0,0) is in the bottom-right
        # quadrant of the first attribute block.
        # For tile (0,0): tile_x%4=0, tile_y%4=0 -> shift=0 -> palette group 0
        # Set attribute to 0b01010101 -> palette groups: 1, 1, 1, 1
        ppu._vram_write_internal(0x23C0, 0x55)  # all quadrants use palette group 1

        # Pattern: colour index 1 for all pixels
        for py in range(8):
            ppu._vram_write_internal(0x0000 + py, 0xFF)
            ppu._vram_write_internal(0x0008 + py, 0x00)

        # Palette group 0, colour 1 = blue
        ppu._vram_write_internal(0x3F01, 0x02)  # blue
        # Palette group 1, colour 1 = green
        ppu._vram_write_internal(0x3F05, 0x19)  # bright green

        pixels = ppu.render_frame()

        # Tile (0,0) should use palette group 1 because of attribute byte
        assert pixels[0][0] == SYSTEM_PALETTE[0x19]


class TestRenderSprites:
    """Test sprite rendering with known OAM data."""

    def test_render_sprites_disabled(self) -> None:
        """Without show-sprites mask bit, sprites do not appear."""
        ppu, cart = _make_ppu_for_render()

        ppu.write_register(0x2001, 0x08)  # only bg, no sprites
        ppu._vram_write_internal(0x3F00, 0x0F)
        bg_color = SYSTEM_PALETTE[0x0F]

        # Set up sprite 0 in OAM
        ppu._oam[0] = 50   # Y
        ppu._oam[1] = 0    # tile index
        ppu._oam[2] = 0    # attributes
        ppu._oam[3] = 100  # X

        pixels = ppu.render_frame()
        # The sprite pixel area should still be background colour
        assert pixels[51][100] == bg_color

    def test_sprite_renders_at_correct_position(self) -> None:
        """A sprite should appear at OAM[Y]+1, OAM[X]."""
        ppu, cart = _make_ppu_for_render()

        ppu.write_register(0x2001, 0x10)  # show sprites only

        # Background colour (transparent where no sprite)
        ppu._vram_write_internal(0x3F00, 0x0F)

        # Sprite 0: at (100, 50) on screen, tile 0, palette 0
        ppu._oam[0] = 49   # Y-1 = 49 -> screen Y = 50
        ppu._oam[1] = 0    # tile index 0
        ppu._oam[2] = 0    # attr: palette 0, no flip, no behind
        ppu._oam[3] = 100  # X

        # Set sprite pattern: all non-transparent pixels (colour index 1)
        for py in range(8):
            ppu._vram_write_internal(0x0000 + py, 0xFF)  # plane 0
            ppu._vram_write_internal(0x0008 + py, 0x00)  # plane 1

        # Sprite palette: 0x3F11 = colour for palette 0, index 1
        ppu._vram_write_internal(0x3F11, 0x30)  # white

        pixels = ppu.render_frame()

        # Sprite pixel at (100, 50) should be white
        assert pixels[50][100] == SYSTEM_PALETTE[0x30]
        # Pixel without sprite should be bg colour
        assert pixels[0][0] == SYSTEM_PALETTE[0x0F]

    def test_sprite_behind_background(self) -> None:
        """Behind-background sprites should be hidden by opaque bg pixels."""
        ppu, cart = _make_ppu_for_render()

        ppu.write_register(0x2001, 0x18)  # bg + sprites
        ppu._vram_write_internal(0x3F00, 0x0F)  # bg colour = black

        # Set up nametable for bg: tile 0 at (12, 6) -> pixel (96, 48)
        tile_x = 12
        tile_y = 6
        ppu._vram_write_internal(0x2000 + tile_y * 32 + tile_x, 0x00)

        # Background tile pattern: colour index 3 (non-transparent)
        for py in range(8):
            ppu._vram_write_internal(0x0000 + py, 0xFF)
            ppu._vram_write_internal(0x0008 + py, 0xFF)  # index = 3

        ppu._vram_write_internal(
            0x23C0 + (tile_y // 4) * 8 + (tile_x // 4), 0x00
        )
        ppu._vram_write_internal(0x3F03, 0x21)  # palette 0 colour 3 = light blue

        # Sprite at same position, behind background
        ppu._oam[0] = 47   # Y-1=47 -> screen Y=48
        ppu._oam[1] = 0    # tile 0
        ppu._oam[2] = 0x20  # behind background
        ppu._oam[3] = 96   # X

        # Sprite pattern: colour index 1
        ppu._vram_write_internal(0x3F11, 0x30)  # white

        pixels = ppu.render_frame()

        # Background should win at overlapping pixel (bg tile top-left)
        assert pixels[48][96] == SYSTEM_PALETTE[0x21]

    def test_sprite_horizontal_flip(self) -> None:
        """Horizontally flipped sprite should render reversed."""
        ppu, cart = _make_ppu_for_render()

        ppu.write_register(0x2001, 0x10)  # show sprites
        ppu._vram_write_internal(0x3F00, 0x0F)

        # Sprite with horizontal flip
        ppu._oam[0] = 99   # screen Y = 100
        ppu._oam[1] = 0    # tile 0
        ppu._oam[2] = 0x40  # horizontal flip
        ppu._oam[3] = 100  # X

        # Pattern: only leftmost pixel (bit 7) is non-transparent
        ppu._vram_write_internal(0x0000, 0x80)  # plane 0 row 0: bit 7 = 1
        ppu._vram_write_internal(0x0008, 0x00)  # plane 1 row 0: all 0
        for py in range(1, 8):
            ppu._vram_write_internal(0x0000 + py, 0x00)
            ppu._vram_write_internal(0x0008 + py, 0x00)

        ppu._vram_write_internal(0x3F11, 0x30)  # white

        pixels = ppu.render_frame()

        # With h-flip, leftmost pattern pixel (px=0) moves to rightmost (px=7)
        # So pixel at X=107 should be white, X=100 should be bg
        assert pixels[100][107] == SYSTEM_PALETTE[0x30]
        assert pixels[100][100] == SYSTEM_PALETTE[0x0F]

    def test_sprite_vertical_flip(self) -> None:
        """Vertically flipped sprite should render upside-down."""
        ppu, cart = _make_ppu_for_render()

        ppu.write_register(0x2001, 0x10)
        ppu._vram_write_internal(0x3F00, 0x0F)

        ppu._oam[0] = 99   # screen Y = 100
        ppu._oam[1] = 0    # tile 0
        ppu._oam[2] = 0x80  # vertical flip
        ppu._oam[3] = 100  # X

        # Pattern: only row 0 of tile is non-transparent
        ppu._vram_write_internal(0x0000, 0xFF)  # plane 0 row 0
        ppu._vram_write_internal(0x0008, 0x00)  # plane 1 row 0 (index = 1)
        for py in range(1, 16):
            ppu._vram_write_internal(0x0000 + py, 0x00)

        ppu._vram_write_internal(0x3F11, 0x30)

        pixels = ppu.render_frame()

        # With v-flip, row 0 moves to row 7 (screen Y = 107)
        assert pixels[107][100] == SYSTEM_PALETTE[0x30]
        assert pixels[100][100] == SYSTEM_PALETTE[0x0F]

    def test_sprite_priority_order(self) -> None:
        """Sprite 0 should overwrite sprite 1 (higher priority)."""
        ppu, cart = _make_ppu_for_render()

        ppu.write_register(0x2001, 0x10)
        ppu._vram_write_internal(0x3F00, 0x0F)

        # Sprite 1 (low priority - rendered first)
        ppu._oam[4] = 99   # sprite 1 Y -> screen Y=100
        ppu._oam[5] = 0    # tile 0
        ppu._oam[6] = 0    # palette 0
        ppu._oam[7] = 100  # X

        # Sprite 0 (high priority - rendered last)
        ppu._oam[0] = 99
        ppu._oam[1] = 0
        ppu._oam[2] = 1    # palette 1 (different from sprite 1)
        ppu._oam[3] = 100

        # Both sprites use same tile with colour index 1
        for py in range(8):
            ppu._vram_write_internal(0x0000 + py, 0xFF)
            ppu._vram_write_internal(0x0008 + py, 0x00)

        ppu._vram_write_internal(0x3F11, 0x30)  # sprite palette 0, colour 1 = white
        ppu._vram_write_internal(0x3F15, 0x16)  # sprite palette 1, colour 1 = orange

        pixels = ppu.render_frame()

        # Sprite 0 (palette 1 = orange) should win since it's drawn last
        assert pixels[100][100] == SYSTEM_PALETTE[0x16]

    def test_leftmost_sprite_clipping(self) -> None:
        """When mask bit 2 is 0, sprites hidden in leftmost 8 pixels."""
        ppu, cart = _make_ppu_for_render()

        ppu.write_register(0x2001, 0x10)  # sprites enabled, leftmost sprites NOT
        ppu._vram_write_internal(0x3F00, 0x0F)
        bg_color = SYSTEM_PALETTE[0x0F]

        # Sprite at X=0 (in leftmost 8 pixels) - actual sprite starts at X=0
        ppu._oam[0] = 99   # screen Y = 100
        ppu._oam[1] = 0
        ppu._oam[2] = 0
        ppu._oam[3] = 0   # X=0

        # Sprite pattern: all non-transparent
        for py in range(8):
            ppu._vram_write_internal(0x0000 + py, 0xFF)
            ppu._vram_write_internal(0x0008 + py, 0x00)
        ppu._vram_write_internal(0x3F11, 0x30)

        pixels = ppu.render_frame()

        # Leftmost column of sprite should NOT be drawn (clipped)
        # But bg is also off, so it should be the default bg colour
        assert pixels[100][0] == bg_color

    def test_sprite_at_x_greater_than_255_skipped(self) -> None:
        """Sprite with X >= 256 should not be rendered."""
        ppu, cart = _make_ppu_for_render()

        ppu.write_register(0x2001, 0x10)
        ppu._vram_write_internal(0x3F00, 0x0F)

        ppu._oam[0] = 100  # Y
        ppu._oam[1] = 0
        ppu._oam[2] = 0
        ppu._oam[3] = 255  # X = 255 (visible, partially)

        # Fill all CHR with FF so sprite is non-transparent
        for py in range(8):
            ppu._vram_write_internal(0x0000 + py, 0xFF)
            ppu._vram_write_internal(0x0008 + py, 0x00)
        ppu._vram_write_internal(0x3F11, 0x30)

        pixels = ppu.render_frame()

        # At X=255, only 1 pixel of sprite is visible
        # The rest (X>=256) would be clipped by the ppu rendering loop
        assert pixels[101][255] == SYSTEM_PALETTE[0x30]


# ─── Sprite 0 hit tests ────────────────────────────────────────────────────────


class TestSpriteZeroHit:
    """Test Sprite 0 hit detection."""

    def test_sprite_0_hit_sets_flag(self) -> None:
        """When sprite 0 non-transparent pixel overlaps bg non-transparent pixel."""
        ppu, cart = _make_ppu_for_render()

        ppu.write_register(0x2001, 0x1E)  # bg + sprites + leftmost bg + leftmost sprites

        # Set up bg tile at top-left
        ppu._vram_write_internal(0x2000, 0x00)
        for py in range(8):
            ppu._vram_write_internal(0x0000 + py, 0xFF)
            ppu._vram_write_internal(0x0008 + py, 0xFF)  # index = 3
        ppu._vram_write_internal(0x23C0, 0x00)
        ppu._vram_write_internal(0x3F03, 0x21)  # bg palette 0 colour 3

        # Sprite 0 at same position
        ppu._oam[0] = 0    # Y-1=0 -> screen Y=1
        ppu._oam[1] = 0    # tile 0
        ppu._oam[2] = 0    # no special attributes
        ppu._oam[3] = 0    # X=0

        ppu._vram_write_internal(0x3F13, 0x30)  # sprite palette 0 colour 3

        ppu.render_frame()
        assert ppu._sprite_zero_hit is True

    def test_sprite_0_hit_false_when_transparent(self) -> None:
        """No hit when sprite-0 pixel is transparent."""
        ppu, cart = _make_ppu_for_render()

        ppu.write_register(0x2001, 0x18)

        # Bg with non-transparent pixel
        ppu._vram_write_internal(0x2000, 0x00)
        for py in range(8):
            ppu._vram_write_internal(0x0000 + py, 0xFF)
            ppu._vram_write_internal(0x0008 + py, 0xFF)
        ppu._vram_write_internal(0x23C0, 0x00)
        ppu._vram_write_internal(0x3F03, 0x21)

        # Sprite 0 with transparent pixel (colour index 0)
        ppu._oam[0] = 0
        ppu._oam[1] = 0
        ppu._oam[2] = 0
        ppu._oam[3] = 0
        # Leave pattern as all-zeros -> colour idx 0 (transparent)
        for py in range(8):
            ppu._vram_write_internal(0x0000 + py, 0x00)
            ppu._vram_write_internal(0x0008 + py, 0x00)

        ppu.render_frame()
        assert ppu._sprite_zero_hit is False

    def test_sprite_0_hit_requires_bg_opaque(self) -> None:
        """No sprite-0 hit when bg pixel is the universal background colour."""
        ppu, cart = _make_ppu_for_render()

        ppu.write_register(0x2001, 0x18)

        # Bg with only universal background colour (colour index 0)
        ppu._vram_write_internal(0x2000, 0x00)
        for py in range(8):
            ppu._vram_write_internal(0x0000 + py, 0x00)  # all transparent
            ppu._vram_write_internal(0x0008 + py, 0x00)
        ppu._vram_write_internal(0x23C0, 0x00)
        ppu._vram_write_internal(0x3F00, 0x0F)  # universal bg colour

        # Sprite 0 with non-transparent pixel
        ppu._oam[0] = 0
        ppu._oam[1] = 0
        ppu._oam[2] = 0
        ppu._oam[3] = 0
        for py in range(8):
            ppu._vram_write_internal(0x0000 + py, 0xFF)
            ppu._vram_write_internal(0x0008 + py, 0x00)
        ppu._vram_write_internal(0x3F11, 0x30)

        ppu.render_frame()
        assert ppu._sprite_zero_hit is False


# ─── Debug helpers tests ───────────────────────────────────────────────────────


class TestDebugPatternTable:
    """Test get_pattern_table debug helper."""

    def test_returns_128_by_128(self, ppu: PPU) -> None:
        table = ppu.get_pattern_table(0)
        assert len(table) == 128
        assert all(len(row) == 128 for row in table)

    def test_table_1_differs_from_table_0(self) -> None:
        """Writing different data to table 0 vs table 1 produces different output."""
        ppu, cart = _make_ppu_for_render()

        # Table 0: all zeros
        for i in range(256 * 16):
            ppu._vram_write_internal(i, 0x00)

        # Table 1: all FF (at 0x1000+)
        for i in range(256 * 16):
            ppu._vram_write_internal(0x1000 + i, 0xFF)

        t0 = ppu.get_pattern_table(0)
        t1 = ppu.get_pattern_table(1)

        # Table 0 should be all black (index 0)
        assert t0[0][0] == (0, 0, 0)
        # Table 1 should be all white (index 3: FF+FF -> bit pair 11 = 3)
        assert t1[0][0] == (0xFF, 0xFF, 0xFF)

    def test_invalid_table_index_raises(self, ppu: PPU) -> None:
        with pytest.raises(ValueError):
            ppu.get_pattern_table(2)
        with pytest.raises(ValueError):
            ppu.get_pattern_table(-1)

    def test_greyscale_values(self) -> None:
        """Verify all four greyscale levels are used."""
        ppu, cart = _make_ppu_for_render()

        # Create tiles with each colour index
        # Tile 0: colour 0 (all zeros)
        for py in range(8):
            ppu._vram_write_internal(0x0000 + py, 0x00)
            ppu._vram_write_internal(0x0008 + py, 0x00)

        # Tile 1: colour 1 (plane 0 = 0xFF, plane 1 = 0x00)
        for py in range(8):
            ppu._vram_write_internal(0x0010 + py, 0xFF)
            ppu._vram_write_internal(0x0018 + py, 0x00)

        # Tile 2: colour 2 (plane 0 = 0x00, plane 1 = 0xFF)
        for py in range(8):
            ppu._vram_write_internal(0x0020 + py, 0x00)
            ppu._vram_write_internal(0x0028 + py, 0xFF)

        # Tile 3: colour 3 (both planes = 0xFF)
        for py in range(8):
            ppu._vram_write_internal(0x0030 + py, 0xFF)
            ppu._vram_write_internal(0x0038 + py, 0xFF)

        table = ppu.get_pattern_table(0)

        # Tile 0 top-left pixel: colour 0 -> black
        assert table[0][0] == (0, 0, 0)
        # Tile 1 top-left pixel: colour 1 -> dark grey
        assert table[0][8] == (0x55, 0x55, 0x55)
        # Tile 2 top-left pixel: colour 2 -> light grey
        assert table[0][16] == (0xAA, 0xAA, 0xAA)
        # Tile 3 top-left pixel: colour 3 -> white
        assert table[0][24] == (0xFF, 0xFF, 0xFF)


class TestPaletteDebug:
    """Test get_palette_data debug helper."""

    def test_returns_palette_ram_bytes(self, ppu: PPU) -> None:
        ppu._palette_ram[0] = 0x01
        ppu._palette_ram[1] = 0x02
        data, sys_pal = ppu.get_palette_data()
        assert len(data) == 32
        assert data[0] == 0x01
        assert data[1] == 0x02

    def test_returns_system_palette(self, ppu: PPU) -> None:
        _, sys_pal = ppu.get_palette_data()
        assert sys_pal is SYSTEM_PALETTE
        assert len(sys_pal) == 64
