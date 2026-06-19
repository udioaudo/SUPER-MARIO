"""NES PPU (Picture Processing Unit) emulation.

Implements the Ricoh 2C02 PPU including:
- VRAM (2 KiB nametable RAM)
- Palette RAM (32 bytes)
- OAM (256 bytes for 64 sprites)
- PPU registers (0x2000–0x2007)
- Frame-at-once rendering (background + sprites)
- Timing with VBlank / NMI generation
- Debug helpers (pattern table visualization, palette dump)

Reference: https://www.nesdev.org/wiki/PPU
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cartridge import Cartridge

from palette import SYSTEM_PALETTE


class PPU:
    """Emulates the NES PPU (2C02 Picture Processing Unit)."""

    # ── Timing constants ──────────────────────────────────────────────────────

    VISIBLE_SCANLINES: tuple[int, int] = (0, 239)
    POST_RENDER_SCANLINE: int = 240
    VBLANK_START_SCANLINE: int = 241
    VBLANK_END_SCANLINE: int = 260
    PRE_RENDER_SCANLINE: int = 261
    CYCLES_PER_SCANLINE: int = 341
    TOTAL_SCANLINES: int = 262

    # ── Memory map constants ──────────────────────────────────────────────────

    PATTERN_TABLE_SIZE: int = 0x1000  # 4 KiB per table, 2 tables = 8 KiB total
    NAMETABLE_SIZE: int = 0x0400      # 1 KiB per nametable
    VRAM_SIZE: int = 2048             # 2 KiB physical VRAM
    PALETTE_RAM_SIZE: int = 32
    OAM_SIZE: int = 256               # 64 sprites × 4 bytes

    def __init__(self, cartridge: Cartridge) -> None:
        """Initialise the PPU with a cartridge for CHR and mirroring data.

        Args:
            cartridge: The currently inserted Cartridge instance.
        """
        self._cartridge: Cartridge = cartridge

        # ── Memory ────────────────────────────────────────────────────────
        self._vram: bytearray = bytearray(self.VRAM_SIZE)          # 2 KiB nametable RAM
        self._palette_ram: bytearray = bytearray(self.PALETTE_RAM_SIZE)  # 32 bytes
        self._oam: bytearray = bytearray(self.OAM_SIZE)            # primary OAM
        self._oam_secondary: bytearray = bytearray(self.OAM_SIZE)  # secondary OAM (sprite eval)

        # ── Internal registers ────────────────────────────────────────────
        self._ctrl: int = 0       # PPUCTRL (0x2000)
        self._mask: int = 0       # PPUMASK (0x2001)
        self._status: int = 0     # PPUSTATUS (0x2002) — open-bus bits
        self._oam_addr: int = 0   # OAMADDR (0x2003)
        self._scroll_x: int = 0   # PPUSCROLL first-write X scroll (0–255)
        self._scroll_y: int = 0   # PPUSCROLL second-write Y scroll (0–255)
        self._vram_addr: int = 0  # Current VRAM address (14-bit, 0x0000–0x3FFF)
        self._ppu_data_buffer: int = 0  # PPUDATA read buffer (delayed by 1)

        # ── Internal latches ──────────────────────────────────────────────
        self._w: bool = False     # Write latch: False → first write, True → second
        self._t: int = 0          # Temporary VRAM address (for scroll updates)

        # Open-bus decay value (last value written to any PPU register)
        self._open_bus: int = 0

        # ── Timing state ──────────────────────────────────────────────────
        self._cycle: int = 0
        self._scanline: int = 0
        self._frame: int = 0

        # ── Flags ─────────────────────────────────────────────────────────
        self._nmi_occurred: bool = False
        self._nmi_pending: bool = False
        self._sprite_zero_hit: bool = False
        self._sprite_overflow: bool = False
        self._vblank: bool = False

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def frame(self) -> int:
        """Return total number of frames rendered."""
        return self._frame

    @property
    def _nmi_enabled(self) -> bool:
        """Return whether VBlank NMI is enabled (PPUCTRL bit 7)."""
        return bool(self._ctrl & 0x80)

    @property
    def _vram_increment(self) -> int:
        """VRAM address increment: 1 (across) or 32 (down), from PPUCTRL bit 2."""
        return 32 if (self._ctrl & 0x04) else 1

    @property
    def _sprite_pt_addr(self) -> int:
        """Sprite pattern table base address from PPUCTRL bit 3."""
        return 0x1000 if (self._ctrl & 0x08) else 0x0000

    @property
    def _bg_pt_addr(self) -> int:
        """Background pattern table base address from PPUCTRL bit 4."""
        return 0x1000 if (self._ctrl & 0x10) else 0x0000

    # ── Register I/O (called by Bus) ──────────────────────────────────────────

    def read_register(self, addr: int) -> int:
        """Read from a PPU register (addr is already mirrored to 0x2000–0x2007).

        Args:
            addr: Register address (0x2000–0x2007).

        Returns:
            Register value (0–255).
        """
        register = addr & 0x07

        if register == 0x00:
            # PPUCTRL is write-only; reads return open bus
            return self._open_bus

        elif register == 0x01:
            # PPUMASK is write-only; reads return open bus
            return self._open_bus

        elif register == 0x02:
            # PPUSTATUS
            return self._read_status()

        elif register == 0x03:
            # OAMADDR is write-only
            return self._open_bus

        elif register == 0x04:
            # OAMDATA read
            return self._oam[self._oam_addr]

        elif register == 0x05:
            # PPUSCROLL is write-only
            return self._open_bus

        elif register == 0x06:
            # PPUADDR is write-only
            return self._open_bus

        elif register == 0x07:
            # PPUDATA read
            return self._read_data()

        return self._open_bus

    def write_register(self, addr: int, value: int) -> None:
        """Write to a PPU register (addr is already mirrored to 0x2000–0x2007).

        Args:
            addr: Register address (0x2000–0x2007).
            value: Byte value to write (0–255).
        """
        value &= 0xFF
        self._open_bus = value
        register = addr & 0x07

        if register == 0x00:
            self._write_ctrl(value)
        elif register == 0x01:
            self._write_mask(value)
        elif register == 0x02:
            # PPUSTATUS is read-only
            pass
        elif register == 0x03:
            self._oam_addr = value
        elif register == 0x04:
            self._oam[self._oam_addr] = value
            self._oam_addr = (self._oam_addr + 1) & 0xFF
        elif register == 0x05:
            self._write_scroll(value)
        elif register == 0x06:
            self._write_addr(value)
        elif register == 0x07:
            self._write_data(value)

    def oam_write(self, index: int, value: int) -> None:
        """Write directly to OAM at the given byte index (used by OAM DMA).

        This bypasses OAMADDR and OAMDATA register logic.

        Args:
            index: Byte offset into OAM (0–255).
            value: Byte value to write.
        """
        self._oam[index & 0xFF] = value & 0xFF

    # ── Register write helpers ────────────────────────────────────────────────

    def _write_ctrl(self, value: int) -> None:
        """Handle write to PPUCTRL (0x2000).

        PPUCTRL bits:
            7: NMI enable (VBlank NMI)
            6: PPU master/slave (ignored)
            5: Sprite size (0=8×8, 1=8×16)
            4: Background pattern table select
            3: Sprite pattern table select
            2: VRAM address increment
            1-0: Base nametable address

        Also updates fine-scroll bits (10-11) in the temporary VRAM address (_t).
        """
        old_nmi = self._nmi_enabled
        self._ctrl = value
        # Update fine Y scroll bits in t register (bits 10-11 → nametable select)
        self._t = (self._t & 0xF3FF) | ((value & 0x03) << 10)

        # If NMI becomes enabled during VBlank, trigger immediately
        if (not old_nmi) and self._nmi_enabled and self._vblank:
            self._nmi_pending = True

    def _write_mask(self, value: int) -> None:
        """Handle write to PPUMASK (0x2001).

        PPUMASK bits:
            7: Emphasize blue
            6: Emphasize green
            5: Emphasize red
            4: Show sprites
            3: Show background
            2: Show sprites in leftmost 8 pixels
            1: Show background in leftmost 8 pixels
            0: Greyscale
        """
        self._mask = value

    def _read_status(self) -> int:
        """Handle read from PPUSTATUS (0x2002).

        PPUSTATUS bits:
            7: VBlank flag
            6: Sprite 0 Hit
            5: Sprite Overflow
            4-0: Open bus (lower 5 bits of last register write)

        Side effects:
            - Clears VBlank flag (bit 7).
            - Resets the write latch (_w → False).
        """
        result = (0x80 if self._vblank else 0x00)
        result |= (0x40 if self._sprite_zero_hit else 0x00)
        result |= (0x20 if self._sprite_overflow else 0x00)
        result |= (self._open_bus & 0x1F)

        # Reading PPUSTATUS clears VBlank and resets write latch
        self._vblank = False
        self._w = False

        return result

    def _write_scroll(self, value: int) -> None:
        """Handle write to PPUSCROLL (0x2005).

        First write (_w=False): coarse X scroll (high 5 bits) + fine X (low 3 bits).
        Second write (_w=True): coarse Y scroll (high 5 bits) + fine Y (low 3 bits).

        Simplified: store full X and Y scroll values (0–255).
        """
        if not self._w:
            self._scroll_x = value & 0xFF
        else:
            self._scroll_y = value & 0xFF
        self._w = not self._w

    def _write_addr(self, value: int) -> None:
        """Handle write to PPUADDR (0x2006).

        First write (_w=False): set high byte (bits 8-13) of VRAM address.
        Second write (_w=True): set low byte (bits 0-7) of VRAM address.
        """
        if not self._w:
            # High byte: value & 0x3F → bits 8-13; clear bits 14-15
            self._vram_addr = (value & 0x3F) << 8
        else:
            # Low byte
            self._vram_addr = (self._vram_addr & 0xFF00) | value
        self._w = not self._w

    def _read_data(self) -> int:
        """Handle read from PPUDATA (0x2007).

        Returns the buffered value from the previous read (1-byte delay),
        then reads the new value at the current VRAM address.
        Exception: palette reads (0x3F00–0x3FFF) return immediately.
        The VRAM address auto-increments after the read.
        """
        addr = self._vram_addr & 0x3FFF
        self._vram_addr = (self._vram_addr + self._vram_increment) & 0x3FFF

        if addr & 0x3F00 == 0x3F00:
            # Palette reads return immediately (no buffering)
            self._ppu_data_buffer = self._vram_read_internal(addr)
            return self._ppu_data_buffer

        # Non-palette: return buffered value, then read new
        result = self._ppu_data_buffer
        self._ppu_data_buffer = self._vram_read_internal(addr)
        return result

    def _write_data(self, value: int) -> None:
        """Handle write to PPUDATA (0x2007).

        Writes to VRAM at the current VRAM address, then auto-increments.
        Does NOT affect the write latch (_w).
        """
        addr = self._vram_addr & 0x3FFF
        self._vram_write_internal(addr, value)
        self._vram_addr = (self._vram_addr + self._vram_increment) & 0x3FFF

    # ── VRAM internal access ──────────────────────────────────────────────────

    def _vram_read_internal(self, addr: int) -> int:
        """Read a byte from VRAM or Palette RAM with address translation.

        Address map (14-bit addr, 0x0000–0x3FFF):
            0x0000–0x1FFF : CHR ROM / CHR RAM (via cartridge)
            0x2000–0x2FFF : Nametables (mirrored per cartridge mirroring)
            0x3000–0x3EFF : Mirror of 0x2000–0x2EFF
            0x3F00–0x3FFF : Palette RAM (mirrored every 32 bytes,
                            with 0x3F10/14/18/1C → 0x3F00/04/08/0C)

        Args:
            addr: 14-bit VRAM address (0x0000–0x3FFF).

        Returns:
            Byte value at the translated address.
        """
        addr &= 0x3FFF

        if addr < 0x2000:
            # CHR ROM / CHR RAM
            return self._cartridge.ppu_read(addr)

        elif addr < 0x3F00:
            # Nametable: 0x2000–0x2FFF, mirrored at 0x3000–0x3EFF
            nt_addr = addr & 0x2FFF
            vram_offset = self._nametable_mirror(nt_addr)
            return self._vram[vram_offset]

        else:
            # Palette RAM: 0x3F00–0x3FFF
            return self._read_palette(addr)

    def _vram_write_internal(self, addr: int, value: int) -> None:
        """Write a byte to VRAM or Palette RAM with address translation.

        Same address map as _vram_read_internal.  CHR ROM area (0x0000–0x1FFF)
        writes are forwarded to the cartridge (effective only in CHR RAM mode).

        Args:
            addr: 14-bit VRAM address (0x0000–0x3FFF).
            value: Byte to write.
        """
        addr &= 0x3FFF
        value &= 0xFF

        if addr < 0x2000:
            # CHR ROM / CHR RAM
            self._cartridge.ppu_write(addr, value)

        elif addr < 0x3F00:
            # Nametable
            nt_addr = addr & 0x2FFF
            vram_offset = self._nametable_mirror(nt_addr)
            self._vram[vram_offset] = value

        else:
            # Palette RAM
            self._write_palette(addr, value)

    def _nametable_mirror(self, addr: int) -> int:
        """Map a nametable address (0x2000–0x2FFF) to a physical VRAM offset.

        The NES has 2 KiB of physical VRAM.  Four logical nametables (NT0–NT3)
        are mapped onto these 2 KiB according to the cartridge mirroring mode:

            Horizontal mirroring (vertical arrangement):
                NT0 (0x2000) and NT1 (0x2400) share the first 1 KiB.
                NT2 (0x2800) and NT3 (0x2C00) share the second 1 KiB.

            Vertical mirroring (horizontal arrangement):
                NT0 (0x2000) and NT2 (0x2800) share the first 1 KiB.
                NT1 (0x2400) and NT3 (0x2C00) share the second 1 KiB.

        Args:
            addr: Nametable address (0x2000–0x2FFF).

        Returns:
            Physical VRAM offset (0–2047).
        """
        nt_select = (addr >> 10) & 3  # bits 10-11 identify the logical nametable
        offset = addr & 0x03FF        # offset within a 1 KiB nametable

        if self._cartridge.mirroring == "horizontal":
            # NT0 or NT1 → first 1 KiB, NT2 or NT3 → second 1 KiB
            if nt_select < 2:
                return offset
            else:
                return 0x0400 + offset
        else:
            # vertical: NT0 or NT2 → first 1 KiB, NT1 or NT3 → second 1 KiB
            if nt_select in (0, 2):
                return offset
            else:
                return 0x0400 + offset

    def _read_palette(self, addr: int) -> int:
        """Read a byte from palette RAM with mirroring.

        Palette addresses 0x3F10, 0x3F14, 0x3F18, 0x3F1C mirror
        0x3F00, 0x3F04, 0x3F08, 0x3F0C respectively.

        Args:
            addr: Address in range 0x3F00–0x3FFF.

        Returns:
            Palette entry value.
        """
        index = self._palette_index(addr)
        return self._palette_ram[index]

    def _write_palette(self, addr: int, value: int) -> None:
        """Write a byte to palette RAM with mirroring.

        Args:
            addr: Address in range 0x3F00–0x3FFF.
            value: Byte to write.
        """
        index = self._palette_index(addr)
        self._palette_ram[index] = value & 0x3F  # Only lower 6 bits used

    @staticmethod
    def _palette_index(addr: int) -> int:
        """Convert a palette address (0x3F00–0x3FFF) to a palette RAM index.

        Mirroring: 0x3F10 → 0x00, 0x3F14 → 0x04, 0x3F18 → 0x08, 0x3F1C → 0x0C.
        Addresses 0x3F20–0x3FFF mirror 0x3F00–0x3F1F (mod 32).

        Args:
            addr: Address in range 0x3F00–0x3FFF.

        Returns:
            Palette RAM index (0–31).
        """
        index = addr & 0x1F  # 0–31
        # Mirror 0x10/0x14/0x18/0x1C → 0x00/0x04/0x08/0x0C
        if index & 0x10 and index & 0x03 == 0:
            index -= 0x10
        return index

    # ── Timing ─────────────────────────────────────────────────────────────────

    def step(self, cpu_cycles: int) -> bool:
        """Advance the PPU by the given number of CPU cycles.

        The PPU runs at 3× the CPU clock rate, so each CPU cycle equals
        3 PPU cycles (dots).

        NMI fires (returns True) once per frame during VBlank if enabled.
        The NMI is latched on the VBlank entry edge and consumed on the
        first call to step() after that edge.

        Args:
            cpu_cycles: Number of CPU cycles to simulate.

        Returns:
            True if an NMI should be triggered this step.
        """
        ppu_cycles = cpu_cycles * 3

        for _ in range(ppu_cycles):
            old_scanline = self._scanline
            self._cycle += 1
            if self._cycle >= self.CYCLES_PER_SCANLINE:
                self._cycle = 0
                self._scanline += 1
                if self._scanline >= self.TOTAL_SCANLINES:
                    self._scanline = 0
                    self._frame += 1

            # VBlank entry: transition into scanline 241 (from any lower scanline)
            if (
                old_scanline < self.VBLANK_START_SCANLINE
                and self._scanline == self.VBLANK_START_SCANLINE
            ):
                self._vblank = True
                if self._nmi_enabled:
                    self._nmi_pending = True

            # Pre-render: transition into scanline 261 (from scanline 260)
            if (
                old_scanline != self.PRE_RENDER_SCANLINE
                and self._scanline == self.PRE_RENDER_SCANLINE
            ):
                self._vblank = False
                self._sprite_zero_hit = False
                self._sprite_overflow = False

        if self._nmi_pending:
            self._nmi_pending = False
            return True
        return False

    # ── Frame rendering ────────────────────────────────────────────────────────

    def render_frame(self) -> list[list[tuple[int, int, int]]]:
        """Render the entire visible frame at once.

        Returns:
            A 240×256 pixel grid of (R, G, B) tuples.
            pixels[y][x] where y=0 is top, x=0 is left.
        """
        # Initialise with universal background colour
        bg_color_idx = self._vram_read_internal(0x3F00) & 0x3F
        default_color = SYSTEM_PALETTE[bg_color_idx]
        pixels: list[list[tuple[int, int, int]]] = [
            [default_color for _ in range(256)] for _ in range(240)
        ]

        # Render background if enabled (PPUMASK bit 3)
        if self._mask & 0x08:
            self._render_background(pixels)

        # Render sprites if enabled (PPUMASK bit 4)
        if self._mask & 0x10:
            self._render_sprites(pixels)

        return pixels

    def _render_background(
        self, pixels: list[list[tuple[int, int, int]]]
    ) -> None:
        """Render the background layer into the pixel buffer.

        The NES nametable layout is 2×2 (4 screens of 256×240 pixels each),
        i.e. the full playfield is 512×480 pixels.  Scrolling moves a 256×240
        window across this space.  With vertical mirroring (SMB1 default),
        NT0=NT2 (left column) and NT1=NT3 (right column).

        Scroll offsets from PPUSCROLL determine the top-left corner of the
        visible window within the 512×480 playfield.
        """
        bg_pt_base = self._bg_pt_addr
        mask_leftmost = bool(self._mask & 0x02)

        for screen_y in range(240):
            for screen_x in range(256):
                # Clip leftmost 8 pixels if mask bit 1 is clear
                if screen_x < 8 and not mask_leftmost:
                    continue

                # Calculate virtual coordinate in the 512×480 playfield.
                # PPUCTRL bits 0-1 select the base nametable quadrant.
                nt_base_col = (self._ctrl & 0x01) * 256  # 0 or 256
                nt_base_row = ((self._ctrl >> 1) & 0x01) * 240  # 0 or 240
                virtual_x = screen_x + self._scroll_x + nt_base_col
                virtual_y = screen_y + self._scroll_y + nt_base_row

                # Determine which nametable quadrant (0–3) this pixel falls into
                nt_x = (virtual_x // 256) & 1  # 0=left, 1=right
                nt_y = (virtual_y // 240) & 1  # 0=top, 1=bottom
                nt_index = nt_y * 2 + nt_x  # 0=top-left, 1=top-right, 2=bottom-left, 3=bottom-right

                # Local pixel coordinates within the nametable
                local_x = virtual_x % 256
                local_y = virtual_y % 240

                tile_x = local_x // 8
                tile_y = local_y // 8

                # Nametable base address (0x2000, 0x2400, 0x2800, 0x2C00)
                nt_base = 0x2000 + nt_index * 0x0400

                # Read tile index from nametable
                nt_addr = nt_base + tile_y * 32 + tile_x
                tile_index = self._vram_read_internal(nt_addr)

                # Read attribute byte (every 4×4 tile block shares one byte)
                attr_addr = (
                    nt_base
                    + 0x03C0
                    + (tile_y // 4) * 8
                    + (tile_x // 4)
                )
                attr_byte = self._vram_read_internal(attr_addr)
                attr_shift = ((tile_x % 4) // 2) * 2 + ((tile_y % 4) // 2) * 4
                palette_group = (attr_byte >> attr_shift) & 0x03

                # Pixel within the 8×8 tile
                px = local_x % 8
                py = local_y % 8

                # Read two bit planes from pattern table
                plane0_addr = bg_pt_base + tile_index * 16 + py
                plane1_addr = plane0_addr + 8
                plane0 = self._vram_read_internal(plane0_addr)
                plane1 = self._vram_read_internal(plane1_addr)

                bit = 7 - px
                color_idx = ((plane0 >> bit) & 1) | (((plane1 >> bit) & 1) << 1)

                if color_idx == 0:
                    palette_idx = self._vram_read_internal(0x3F00)
                else:
                    palette_idx = self._vram_read_internal(
                        0x3F00 + palette_group * 4 + color_idx
                    )

                pixels[screen_y][screen_x] = SYSTEM_PALETTE[palette_idx & 0x3F]

    def _render_sprites(
        self, pixels: list[list[tuple[int, int, int]]]
    ) -> None:
        """Render sprites into the pixel buffer.

        Sprites are rendered in reverse OAM order: sprite 63 is drawn first
        (lowest priority), sprite 0 is drawn last (highest priority).

        Sprite 0 hit detection is performed when a non-transparent sprite-0
        pixel overlaps a non-background-colour pixel on screen.
        """
        sprite_height: int = 16 if (self._ctrl & 0x20) else 8
        sprite_pt_base = self._sprite_pt_addr
        mask_leftmost = bool(self._mask & 0x04)

        # Iterate in reverse: sprite 63 first (low priority), sprite 0 last (high)
        for sprite_idx in range(63, -1, -1):
            oam_addr = sprite_idx * 4
            oam_y = self._oam[oam_addr]
            tile_index = self._oam[oam_addr + 1]
            attr = self._oam[oam_addr + 2]
            oam_x = self._oam[oam_addr + 3]

            # Sprite Y on screen: OAM Y + 1 (NES quirk)
            sprite_y = oam_y + 1
            if sprite_y > 239 or sprite_y + sprite_height <= 1:
                continue

            # Sprite X
            sprite_x = oam_x
            if sprite_x >= 256:
                continue

            behind_bg = bool(attr & 0x20)
            flip_h = bool(attr & 0x40)
            flip_v = bool(attr & 0x80)
            palette_group = attr & 0x03

            # Background colour for comparison
            bg_color_idx = self._vram_read_internal(0x3F00) & 0x3F
            bg_color = SYSTEM_PALETTE[bg_color_idx]

            for py in range(sprite_height):
                pixel_y = sprite_y + py
                if pixel_y < 0 or pixel_y >= 240:
                    continue

                # Handle vertical flip: flip the row within the tile (and tile selection for 8×16)
                if sprite_height == 16:
                    # 8×16 sprites: two 8×8 tiles stacked vertically
                    actual_py = py
                    tile = tile_index & 0xFE  # Clear bit 0 for tile pair base
                    if flip_v:
                        actual_py = 15 - py
                    if actual_py >= 8:
                        tile += 1
                        actual_py -= 8
                    pt_base = 0x1000 if (tile_index & 0x01) else 0x0000
                else:
                    actual_py = py if not flip_v else (7 - py)
                    tile = tile_index
                    pt_base = sprite_pt_base

                plane0_addr = pt_base + tile * 16 + actual_py
                plane1_addr = plane0_addr + 8
                plane0 = self._vram_read_internal(plane0_addr)
                plane1 = self._vram_read_internal(plane1_addr)

                for px in range(8):
                    pixel_x = sprite_x + px
                    if pixel_x < 0 or pixel_x >= 256:
                        continue

                    # Clip leftmost 8 pixels if mask bit 2 is clear
                    if pixel_x < 8 and not mask_leftmost:
                        continue

                    # Handle horizontal flip
                    actual_px = px if not flip_h else (7 - px)
                    bit = 7 - actual_px
                    color_idx = ((plane0 >> bit) & 1) | (((plane1 >> bit) & 1) << 1)

                    if color_idx == 0:
                        continue  # Transparent pixel

                    # Sprite 0 hit detection
                    if (
                        sprite_idx == 0
                        and not self._sprite_zero_hit
                        and pixel_y < 240
                    ):
                        existing = pixels[pixel_y][pixel_x]
                        if existing != bg_color:
                            self._sprite_zero_hit = True

                    # Behind-background priority: skip if background is non-transparent
                    if behind_bg:
                        if pixels[pixel_y][pixel_x] != bg_color:
                            continue

                    # Read sprite palette colour
                    palette_idx = self._vram_read_internal(
                        0x3F10 + palette_group * 4 + color_idx
                    )
                    pixels[pixel_y][pixel_x] = SYSTEM_PALETTE[palette_idx & 0x3F]

    # ── Debug helpers ──────────────────────────────────────────────────────────

    def get_pattern_table(self, table_index: int) -> list[list[tuple[int, int, int]]]:
        """Return a 128×128 greyscale visualization of a pattern table.

        Each pattern table contains 256 tiles arranged as 16×16 tiles.
        Colour indices 0–3 are mapped to greyscale levels.

        Args:
            table_index: 0 for left pattern table ($0000), 1 for right ($1000).

        Returns:
            A 128×128 grid of (R, G, B) tuples.
        """
        if table_index not in (0, 1):
            raise ValueError("table_index must be 0 or 1")

        pt_base = table_index * 0x1000
        greyscale = [
            (0x00, 0x00, 0x00),   # 0 → black
            (0x55, 0x55, 0x55),   # 1 → dark grey
            (0xAA, 0xAA, 0xAA),   # 2 → light grey
            (0xFF, 0xFF, 0xFF),   # 3 → white
        ]

        pixels: list[list[tuple[int, int, int]]] = [
            [(0, 0, 0) for _ in range(128)] for _ in range(128)
        ]

        for tile_row in range(16):
            for tile_col in range(16):
                tile_index = tile_row * 16 + tile_col
                for py in range(8):
                    plane0 = self._vram_read_internal(
                        pt_base + tile_index * 16 + py
                    )
                    plane1 = self._vram_read_internal(
                        pt_base + tile_index * 16 + py + 8
                    )
                    for px in range(8):
                        bit = 7 - px
                        color_idx = ((plane0 >> bit) & 1) | (((plane1 >> bit) & 1) << 1)
                        y = tile_row * 8 + py
                        x = tile_col * 8 + px
                        pixels[y][x] = greyscale[color_idx]

        return pixels

    def get_palette_data(self) -> tuple[bytes, list[tuple[int, int, int]]]:
        """Return the current palette RAM and system palette for debugging.

        Returns:
            A tuple of (32-byte palette RAM as bytes, 64-colour system palette).
        """
        return bytes(self._palette_ram), SYSTEM_PALETTE
