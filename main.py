"""SUPER MARIO NES Emulator — main entry point and frame loop.

Usage:
    python main.py <rom_file> [--scale N] [--debug] [--log]

    rom_file    : Path to a .nes ROM file (required).
    --scale N   : Window scale factor 1–5 (default: 3).
    --debug     : Enable the debug window.
    --log       : Enable CPU instruction logging to stdout.
"""

from __future__ import annotations

import argparse
import sys
import traceback

import pygame

from apu import APU
from bus import Bus
from cartridge import Cartridge
from cpu import CPU
from debug import DebugWindow
from input import Input
from palette import SYSTEM_PALETTE  # noqa: F401 — available for debug
from ppu import PPU
from ram import RAM
from ui import UI

# ─── Constants ───────────────────────────────────────────────────────────────

FRAME_CPU_CYCLES: int = 29781  # NTSC: CPU cycles per frame (1789773 / 60)


# ─── CLI ─────────────────────────────────────────────────────────────────────


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments.

    Args:
        argv: Argument list (defaults to sys.argv[1:]).

    Returns:
        Parsed namespace with rom_file, scale, debug, log attributes.
    """
    parser = argparse.ArgumentParser(
        description="SUPER MARIO — NES (FC) Emulator",
    )
    parser.add_argument(
        "rom_file",
        type=str,
        help="Path to a .nes ROM file",
    )
    parser.add_argument(
        "--scale",
        type=int,
        default=2,
        choices=range(1, 6),
        metavar="N",
        help="Window scale factor 1–5 (default: 3 → 768×720)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable the debug window (F5=pause, F6=frame step, F7=instruction step)",
    )
    parser.add_argument(
        "--log",
        action="store_true",
        help="Enable CPU instruction logging to stdout",
    )
    return parser.parse_args(argv)


# ─── Main loop ───────────────────────────────────────────────────────────────


def run_loop(
    cpu: CPU,
    ppu: PPU,
    apu: APU,
    bus: Bus,
    input_dev: Input,
    ui: UI,
    debug: DebugWindow | None,
) -> None:
    """Execute the main emulation frame loop.

    Each frame:
      1. Poll UI events (quit?).
      2. Poll input (keyboard → controller).
      3. Handle debug commands (pause / step).
      4. Execute CPU instructions until one frame's worth of cycles.
      5. Render the PPU frame to the display.
      6. Generate and play APU audio samples.
      7. Update and render the debug window (if enabled).
      8. Cap frame rate via UI clock.

    Args:
        cpu: The CPU instance.
        ppu: The PPU instance.
        apu: The APU instance.
        bus: The Bus instance.
        input_dev: The Input (controller) instance.
        ui: The UI window.
        debug: Optional DebugWindow instance.
    """
    running: bool = True
    paused: bool = False
    step_mode: str | None = None  # 'frame' | 'instruction' | None

    while running:
        # 1. UI events
        if ui.handle_events():
            running = False
            break

        # 2. Input poll
        input_dev.poll()

        # 3. Debug commands
        if debug is not None and debug.visible:
            cmd = debug.handle_input()
            action = cmd.get("action")
            if action == "pause":
                paused = not paused
                step_mode = None
            elif action == "step":
                step_mode = cmd.get("step")
                if paused is False:
                    paused = True
                # Execute one step immediately
                if step_mode == "frame":
                    _run_frame(cpu, ppu, apu, step_one_frame=True)
                    step_mode = None
                elif step_mode == "instruction":
                    _run_instruction_step(cpu, ppu, apu)
                    step_mode = None

        # 4. CPU execution (when not paused)
        if not paused:
            _run_frame(cpu, ppu, apu, step_one_frame=False)
        elif step_mode is None:
            pass

        # 5. Render
        pixels = ppu.render_frame()
        ui.render(pixels)

        # 6. Debug window
        if debug is not None and debug.visible:
            debug.update()
            debug.render()

        # 7. Frame rate — let it run as fast as possible (no cap)
        #    The NES game logic is self-paced at 60 FPS internal timing.
        #    Removing the cap allows higher FPS if the host can keep up.


def _run_frame(
    cpu: CPU,
    ppu: PPU,
    apu: APU,
    *,
    step_one_frame: bool = False,
) -> None:
    """Execute CPU instructions for one frame (or until the current frame completes).

    Args:
        cpu: The CPU.
        ppu: The PPU.
        apu: The APU.
        step_one_frame: If True, execute exactly one full frame (29781 cycles).
                        If False, execute until cycles_this_frame >= FRAME_CPU_CYCLES
                        (accounts for partial frame carried over from previous call).
    """
    cycles_this_frame: int = 0
    target = FRAME_CPU_CYCLES

    while cycles_this_frame < target:
        cycles = cpu.step()
        cycles_this_frame += cycles

        # Advance PPU and check for NMI trigger
        nmi_triggered = ppu.step(cycles)
        apu.step(cycles)

        if nmi_triggered:
            cpu.nmi()

        if step_one_frame and cycles_this_frame >= FRAME_CPU_CYCLES:
            break


def _run_instruction_step(cpu: CPU, ppu: PPU, apu: APU) -> None:
    """Execute exactly one CPU instruction (for instruction stepping in debug)."""
    cycles = cpu.step()
    ppu.step(cycles)
    apu.step(cycles)


# ─── Entry point ─────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> None:
    """Program entry point. Parses args, initializes modules, runs the emulator.

    Args:
        argv: Command-line arguments (defaults to sys.argv[1:]).
    """
    args = parse_args(argv)

    # ── Initialise Pygame ──────────────────────────────────────────────────
    try:
        pygame.init()
    except pygame.error as exc:
        print(f"错误：无法初始化 Pygame — {exc}", file=sys.stderr)
        sys.exit(1)

    # ── Load cartridge ─────────────────────────────────────────────────────
    try:
        cartridge = Cartridge.load(args.rom_file)
    except FileNotFoundError:
        print(f"错误：找不到 ROM 文件 '{args.rom_file}'", file=sys.stderr)
        pygame.quit()
        sys.exit(1)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        pygame.quit()
        sys.exit(1)

    # ── Instantiate modules ────────────────────────────────────────────────
    ram = RAM(2048)
    ppu = PPU(cartridge)
    apu = APU()
    input_dev = Input()
    bus = Bus(cpu_ram=ram, ppu=ppu, apu=apu, cartridge=cartridge, input_dev=input_dev)
    cpu = CPU(bus)

    if args.log:
        cpu.enable_logging()

    ui = UI(scale=args.scale)

    # Debug window
    debug: DebugWindow | None = None
    if args.debug:
        debug = DebugWindow(cpu, ppu, bus, input_dev)

    # ── Reset CPU ──────────────────────────────────────────────────────────
    cpu.reset()

    # ── Run ────────────────────────────────────────────────────────────────
    try:
        run_loop(cpu, ppu, apu, bus, input_dev, ui, debug)
    except KeyboardInterrupt:
        pass
    except Exception:
        traceback.print_exc()
    finally:
        pygame.quit()


if __name__ == "__main__":
    main()
