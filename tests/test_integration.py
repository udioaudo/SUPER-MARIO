"""Integration and smoke tests for the complete NES emulator pipeline."""

from __future__ import annotations

import os
import tempfile

import pytest

# Import main module functions for testing
from main import parse_args, main as main_entry


# ─── Helpers ─────────────────────────────────────────────────────────────────

_BASE_ROM: bytes = (
    b"NES\x1A"  # magic
    b"\x01"  # PRG ROM: 1 page (16 KiB)
    b"\x01"  # CHR ROM: 1 page (8 KiB)
    b"\x01"  # flags6: vertical mirroring, mapper 0
    b"\x00"  # flags7: mapper 0 high nibble
    b"\x00" * 8  # padding
)


def _make_test_rom(path: str) -> None:
    """Write a minimal valid iNES ROM to *path*."""
    prg = bytes([0x4C, 0x00, 0xC0]) + b"\x00" * (16384 - 3)  # JMP $C000
    chr_data = b"\x00" * 8192
    with open(path, "wb") as f:
        f.write(_BASE_ROM)
        f.write(prg)
        f.write(chr_data)


# ─── CLI parsing tests ──────────────────────────────────────────────────────


class TestArgParsing:
    """Tests for command-line argument parsing."""

    def test_required_rom_file(self) -> None:
        """rom_file is a required positional argument."""
        with pytest.raises(SystemExit):
            parse_args([])

    def test_default_values(self) -> None:
        """Verify default values for optional arguments."""
        args = parse_args(["game.nes"])
        assert args.rom_file == "game.nes"
        assert args.scale == 2  # default changed to 2 for smaller window
        assert args.debug is False
        assert args.log is False

    def test_scale_short(self) -> None:
        """--scale with a valid value should parse correctly."""
        args = parse_args(["game.nes", "--scale", "2"])
        assert args.scale == 2

    def test_scale_max(self) -> None:
        args = parse_args(["game.nes", "--scale", "5"])
        assert args.scale == 5

    def test_debug_flag(self) -> None:
        """--debug should set debug to True."""
        args = parse_args(["game.nes", "--debug"])
        assert args.debug is True

    def test_log_flag(self) -> None:
        """--log should set log to True."""
        args = parse_args(["game.nes", "--log"])
        assert args.log is True

    def test_all_flags_combined(self) -> None:
        """All optional flags should work together."""
        args = parse_args(["game.nes", "--scale", "4", "--debug", "--log"])
        assert args.scale == 4
        assert args.debug is True
        assert args.log is True


# ─── Error handling tests ───────────────────────────────────────────────────


class TestErrorHandling:
    """Tests for graceful error handling in main()."""

    def test_nonexistent_file(self) -> None:
        """A nonexistent ROM path should print an error and exit."""
        with pytest.raises(SystemExit) as exc:
            main_entry(["/nonexistent/path/rom.nes"])
        assert exc.value.code == 1

    def test_invalid_magic(self) -> None:
        """A file without the NES magic number should cause an error."""
        fd, path = tempfile.mkstemp(suffix=".nes")
        os.close(fd)
        with open(path, "wb") as f:
            f.write(b"NOT A ROM FILE")
        try:
            with pytest.raises(SystemExit) as exc:
                main_entry([path])
            assert exc.value.code == 1
        finally:
            os.unlink(path)

    def test_non_mapper_0(self) -> None:
        """A ROM with mapper != 0 should be rejected."""
        fd, path = tempfile.mkstemp(suffix=".nes")
        os.close(fd)
        header = bytearray(_BASE_ROM)
        header[6] = 0x11  # mapper 1, vertical mirroring
        with open(path, "wb") as f:
            f.write(header)
            f.write(b"\x00" * 16384)  # PRG
            f.write(b"\x00" * 8192)  # CHR
        try:
            with pytest.raises(SystemExit) as exc:
                main_entry([path])
            assert exc.value.code == 1
        finally:
            os.unlink(path)


# ─── Pipeline smoke test ────────────────────────────────────────────────────


class TestPipelineSmoke:
    """Smoke test: run a few frames with a minimal ROM (headless, no Pygame display)."""

    @pytest.mark.skipif(
        os.environ.get("CI") == "true",
        reason="Headless smoke test requires a display or mock",
    )
    def test_rom_load_and_one_frame_no_crash(self) -> None:
        """Load a minimal ROM and simulate running a few CPU steps."""
        import pygame

        fd, path = tempfile.mkstemp(suffix=".nes")
        os.close(fd)
        _make_test_rom(path)

        try:
            from apu import APU
            from bus import Bus
            from cartridge import Cartridge
            from cpu import CPU
            from input import Input
            from ppu import PPU
            from ram import RAM

            pygame.init()
            cartridge = Cartridge.load(path)
            ram = RAM()
            ppu = PPU(cartridge)
            apu = APU()
            input_dev = Input()
            bus = Bus(ram, ppu, apu, cartridge, input_dev)
            cpu = CPU(bus)
            cpu.reset()

            # Run 1000 CPU steps — should not crash
            for _ in range(1000):
                cycles = cpu.step()
                ppu.step(cycles)
                apu.step(cycles)

            # Render one frame
            pixels = ppu.render_frame()
            assert len(pixels) == 240
            assert len(pixels[0]) == 256
            assert isinstance(pixels[0][0], tuple)
            assert len(pixels[0][0]) == 3

            # Generate audio samples
            samples = apu.get_audio_samples()
            assert len(samples) > 0

            pygame.quit()
        except Exception as exc:
            pygame.quit()
            raise exc
        finally:
            os.unlink(path)
