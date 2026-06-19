"""NES APU (Audio Processing Unit) emulator.

Implements all 5 NES audio channels:
  - Pulse 1 (square wave with envelope, sweep, duty cycle)
  - Pulse 2 (identical to Pulse 1)
  - Triangle (32-step waveform with linear counter)
  - Noise (LFSR-based pseudo-random noise with envelope)
  - DMC (delta modulation channel, basic framework)

Generates 44100 Hz PCM audio samples synchronised to the CPU master clock
(1.789773 MHz NTSC).  The frame counter drives envelope, sweep, and length
counter updates at the NES-native rates.

Reference: https://www.nesdev.org/wiki/APU
"""

from __future__ import annotations

from typing import Any, Callable

# ═══════════════════════════════════════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════════════════════════════════════

CPU_CLOCK: float = 1789773.0   # NTSC NES CPU frequency (Hz)
SAMPLE_RATE: int = 44100        # Output sample rate (Hz)
SAMPLES_PER_FRAME: int = SAMPLE_RATE // 60          # ≈ 735
CYCLES_PER_SAMPLE: float = CPU_CLOCK / SAMPLE_RATE  # ≈ 40.58

# Frame counter step boundaries in CPU cycles (approximate).
# In 4-step mode, steps fire at these boundaries within each frame.
_FC_STEP_BOUNDARIES_4: list[float] = [3728.5, 7457.0, 11185.5, 14914.0]
_FC_STEP_BOUNDARIES_5: list[float] = [3728.5, 7457.0, 11185.5, 14914.0, 18640.5]

# Length counter lookup table (index 0-31 maps to actual length value).
LENGTH_TABLE: list[int] = [
    10, 254, 20, 2, 40, 4, 80, 6, 160, 8, 60, 10, 14, 12, 26, 14,
    12, 16, 24, 18, 48, 20, 96, 22, 192, 24, 72, 26, 16, 28, 32, 30,
]

# Pulse duty cycle waveforms: a 1 means the output is high for that step.
# Each waveform is 8 steps; duty_index cycles 0→7 repeatedly.
_DUTY_WAVEFORMS: list[list[int]] = [
    [0, 1, 0, 0, 0, 0, 0, 0],  # 12.5%
    [0, 1, 1, 0, 0, 0, 0, 0],  # 25%
    [0, 1, 1, 1, 1, 0, 0, 0],  # 50%
    [1, 0, 0, 1, 1, 1, 1, 1],  # 75% (negated)
]

# Triangle waveform: 32-step repeating sequence.
_TRI_WAVE: list[int] = [
    15, 14, 13, 12, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1, 0,
    0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15,
]

# Noise channel period table (16 entries), indexed by period_index (bits 0-3).
_NOISE_PERIODS: list[int] = [
    4, 8, 16, 32, 64, 96, 128, 160,
    202, 254, 380, 508, 762, 1016, 2034, 4068,
]

# DMC rate table: CPU cycles per output-unit change, indexed by rate_index (bits 0-3).
_DMC_RATES: list[int] = [428, 380, 340, 320, 286, 254, 226, 214,
                          190, 160, 142, 128, 106, 84, 72, 54]


# ═══════════════════════════════════════════════════════════════════════════════
# Helper: envelope clock
# ═══════════════════════════════════════════════════════════════════════════════

def _clock_envelope(chan: dict[str, Any]) -> None:
    """Advance the envelope generator for a pulse or noise channel in-place."""
    if not chan["env_enabled"]:
        return
    if chan["env_counter"] > 0:
        chan["env_counter"] -= 1
    else:
        # Counter hit zero: reload the divider.
        chan["env_counter"] = chan["env_volume"]
        if chan["env_decay"] > 0:
            chan["env_decay"] -= 1
        elif chan["env_loop"]:
            # Loop: reset decay to 15.
            chan["env_decay"] = 15


# ═══════════════════════════════════════════════════════════════════════════════
# APU
# ═══════════════════════════════════════════════════════════════════════════════

class APU:
    """Complete NES APU emulator with 5 audio channels and a frame counter.

    Usage::

        apu = APU()
        apu.write_register(0x4000, 0x9F)  # configure pulse 1
        apu.write_register(0x4015, 0x0F)  # enable all channels
        samples = apu.get_audio_samples()  # list[int] of ~735 s16 samples
    """

    def __init__(self) -> None:
        """Initialise all 5 channels and the frame counter."""
        # ── Pulse 1 ──────────────────────────────────────────────────────────
        self.pulse1: dict[str, Any] = _make_pulse()

        # ── Pulse 2 ──────────────────────────────────────────────────────────
        self.pulse2: dict[str, Any] = _make_pulse()

        # ── Triangle ─────────────────────────────────────────────────────────
        self.triangle: dict[str, Any] = {
            "enabled": False,
            "tri_step": 0,
            "timer": 0,
            "timer_counter": 0,
            "length_counter": 0,
            "length_halt": False,
            "linear_counter": 0,
            "linear_reload": 0,
            "linear_control": False,
            "linear_reload_flag": False,
        }

        # ── Noise ────────────────────────────────────────────────────────────
        self.noise: dict[str, Any] = {
            "enabled": False,
            "shift_register": 1,          # 15-bit LFSR
            "mode": 0,                    # 0 = long mode, 1 = short mode
            "timer": 0,
            "timer_counter": 0,
            "length_counter": 0,
            "length_halt": False,
            # Envelope
            "env_loop": False,
            "env_enabled": False,
            "env_volume": 0,
            "env_decay": 0,
            "env_counter": 0,
        }

        # ── DMC ──────────────────────────────────────────────────────────────
        self.dmc: dict[str, Any] = {
            "enabled": False,
            "rate_index": 0,
            "rate_counter": 0,
            "output_unit": 0,
            "sample_buffer": 0,
            "bits_remaining": 0,
            "bytes_remaining": 0,
            "sample_address": 0,
            "sample_length": 0,
            "loop": False,
            "irq_enabled": False,
            "silence": False,
        }

        # ── Frame counter ────────────────────────────────────────────────────
        self._fc_mode: int = 4               # 4-step (default) or 5-step
        self._fc_irq_inhibit: bool = False   # when True, suppress frame IRQ
        self._fc_irq: bool = False           # current IRQ flag
        self._fc_cycle_accumulator: float = 0.0
        self._fc_step_index: int = 0         # which step boundary is next

        # ── Per-sample output values (updated by advance_* helpers) ──────────
        self.pulse1_output: int = 0
        self.pulse2_output: int = 0
        self.triangle_output: int = 0
        self.noise_output: int = 0
        self.dmc_output: int = 0

    # ── Public API ───────────────────────────────────────────────────────────

    def step(self, cpu_cycles: int) -> None:
        """Advance internal cycle counter and drive the frame counter.

        Each CPU instruction should call this with the cycles it consumed.
        """
        self._fc_cycle_accumulator += float(cpu_cycles)
        self._tick_frame_counter()

    def get_audio_samples(self) -> list[int]:
        """Generate one frame of PCM 16-bit signed samples (~735 samples).

        For each sample, each channel is advanced by ``CYCLES_PER_SAMPLE``
        cycles, then all channel outputs are mixed and converted to a signed
        16-bit integer in the range [-32768, 32767].

        Returns:
            list[int]: ~735 signed 16-bit PCM samples.
        """
        samples: list[int] = []
        for _ in range(SAMPLES_PER_FRAME):
            # Advance each channel.
            self._advance_pulse(self.pulse1, CYCLES_PER_SAMPLE)
            self._advance_pulse(self.pulse2, CYCLES_PER_SAMPLE)
            self._advance_triangle(CYCLES_PER_SAMPLE)
            self._advance_noise(CYCLES_PER_SAMPLE)
            self._advance_dmc(CYCLES_PER_SAMPLE)

            # Record current outputs.
            p1 = self.pulse1_output
            p2 = self.pulse2_output
            tri = self.triangle_output
            noise = self.noise_output
            dmc = self.dmc_output

            # Mix: normalise each channel to roughly 0..1, weight, then
            # convert to signed 16-bit.
            pulse_out = float(p1 + p2) / 15.0 * 0.3
            tri_out = float(tri) / 15.0 * 0.3
            noise_out = float(noise) / 15.0 * 0.2
            dmc_out = float(dmc) / 127.0 * 0.2

            mixed = (pulse_out + tri_out + noise_out + dmc_out) / 4.0

            # Map 0..1-ish to signed 16-bit around a 0.5 centre, reduced volume.
            sample = int((mixed - 0.5) * 65535.0 * 0.5)
            sample = max(-32768, min(32767, sample))
            samples.append(sample)

        return samples

    def read_register(self, addr: int) -> int:
        """Read from an APU register.

        Currently only 0x4015 (channel status + frame IRQ) is implemented.

        Args:
            addr: Register address (0x4000-0x4017).

        Returns:
            8-bit register value.
        """
        if addr == 0x4015:
            return self._read_status()
        # Other reads return 0 (open bus behaviour is not emulated).
        return 0

    def write_register(self, addr: int, value: int) -> None:
        """Write to an APU register, routing to the correct channel.

        Args:
            addr: Register address (0x4000-0x4017).
            value: 8-bit value to write.
        """
        value &= 0xFF

        if addr == 0x4000:
            self._write_pulse_vol(self.pulse1, value)
        elif addr == 0x4001:
            self._write_pulse_sweep(self.pulse1, value)
        elif addr == 0x4002:
            self._write_pulse_lo(self.pulse1, value)
        elif addr == 0x4003:
            self._write_pulse_hi(self.pulse1, value)
        elif addr == 0x4004:
            self._write_pulse_vol(self.pulse2, value)
        elif addr == 0x4005:
            self._write_pulse_sweep(self.pulse2, value)
        elif addr == 0x4006:
            self._write_pulse_lo(self.pulse2, value)
        elif addr == 0x4007:
            self._write_pulse_hi(self.pulse2, value)
        elif addr == 0x4008:
            self._write_tri_linear(value)
        elif addr == 0x400A:
            self._write_tri_lo(value)
        elif addr == 0x400B:
            self._write_tri_hi(value)
        elif addr == 0x400C:
            self._write_noise_vol(value)
        elif addr == 0x400E:
            self._write_noise_lo(value)
        elif addr == 0x400F:
            self._write_noise_hi(value)
        elif addr == 0x4010:
            self._write_dmc_freq(value)
        elif addr == 0x4011:
            self._write_dmc_raw(value)
        elif addr == 0x4012:
            self._write_dmc_start(value)
        elif addr == 0x4013:
            self._write_dmc_len(value)
        elif addr == 0x4015:
            self._write_enable(value)
        elif addr == 0x4017:
            self._write_frame_counter(value)

    # ── Frame Counter ────────────────────────────────────────────────────────

    def _tick_frame_counter(self) -> None:
        """Execute frame-counter steps whose boundaries have been crossed."""
        mode = self._fc_mode
        boundaries = _FC_STEP_BOUNDARIES_5 if mode == 5 else _FC_STEP_BOUNDARIES_4
        total_steps = len(boundaries)

        ncalls: list[Callable[[], None]] = []
        while self._fc_step_index < total_steps:
            boundary = boundaries[self._fc_step_index]
            if self._fc_cycle_accumulator >= boundary:
                ncalls.append(self._make_step_fn(self._fc_step_index, mode))
                self._fc_step_index += 1
            else:
                break

        for fn in ncalls:
            fn()

        # Reset accumulator and step index when all steps have fired.
        if self._fc_step_index >= total_steps:
            self._fc_cycle_accumulator -= boundaries[-1]
            self._fc_step_index = 0

    def _make_step_fn(self, step: int, mode: int) -> Callable[[], None]:
        """Return a callable that executes the appropriate sub-step actions.

        Step 0: clock envelopes + (clock sweeps in 4-step, not in 5-step)
        Step 1: clock envelopes + clock sweeps + clock length counters
        Step 2: clock envelopes + clock sweeps + (set IRQ in 5-step)
        Step 3: clock envelopes + clock sweeps + clock length counters + set IRQ
        Step 4: (5-step only) — nothing (silent step)
        """

        def _step_fn() -> None:
            if step == 0:
                self._clock_envelopes()
                if mode == 4:
                    # In 4-step mode, sweeps clock on steps 0 and 1
                    # Actually: step 0 → envelopes; step 1 → envelopes + sweeps + lengths; etc.
                    # But the canonical behaviour is:
                    pass

            if step == 0:  # envelopes only (both modes)
                self._clock_envelopes()
            elif step == 1:
                self._clock_envelopes()
                self._clock_sweeps()
                self._clock_length_counters()
            elif step == 2:
                self._clock_envelopes()
                self._clock_sweeps()
                if mode == 5 and not self._fc_irq_inhibit:
                    self._fc_irq = True
            elif step == 3:
                self._clock_envelopes()
                self._clock_sweeps()
                self._clock_length_counters()
                if not self._fc_irq_inhibit:
                    self._fc_irq = True
            # Step 4 (5-step only): do nothing.

        return _step_fn

    def _clock_envelopes(self) -> None:
        """Clock envelopes on pulse 1/2 and noise channels."""
        _clock_envelope(self.pulse1)
        _clock_envelope(self.pulse2)
        _clock_envelope(self.noise)

    def _clock_sweeps(self) -> None:
        """Clock sweep units on pulse 1 and pulse 2."""
        self._clock_pulse_sweep(self.pulse1)
        self._clock_pulse_sweep(self.pulse2)

    def _clock_length_counters(self) -> None:
        """Clock length counters on all channels that have them."""
        self._clock_length(self.pulse1)
        self._clock_length(self.pulse2)
        self._clock_length(self.triangle)
        self._clock_length(self.noise)

    @staticmethod
    def _clock_length(chan: dict[str, Any]) -> None:
        """Decrement a channel's length counter if not halted."""
        if chan.get("length_halt", False):
            return
        if chan["length_counter"] > 0:
            chan["length_counter"] -= 1

    def _clock_pulse_sweep(self, chan: dict[str, Any]) -> None:
        """Advance the sweep unit of a pulse channel."""
        if not chan["sweep_enabled"]:
            return
        if chan["sweep_counter"] > 0:
            chan["sweep_counter"] -= 1
        else:
            # Reload sweep counter.
            period = chan["sweep_divider"]
            chan["sweep_counter"] = period if period > 0 else 1
            if chan["sweep_reload"]:
                chan["sweep_reload"] = False
                if chan["sweep_divider"] > 0:
                    self._sweep_calculate(chan)

    def _sweep_calculate(self, chan: dict[str, Any]) -> None:
        """Perform a sweep calculation on a pulse channel's timer."""
        shift = chan["sweep_shift"]
        if shift == 0:
            return
        delta = chan["timer"] >> shift
        if chan["sweep_negate"]:
            # Pulse 2 uses ones' complement negate; Pulse 1 uses the same logic
            # but with a -1 offset on some hardware. We use the common
            # implementation: negate means subtract (and for pulse 1, subtract
            # delta + 1, but we simplify to just subtract delta).
            new_timer = chan["timer"] - delta
            if new_timer < 0:
                new_timer = 0
        else:
            new_timer = chan["timer"] + delta
        if new_timer > 0x7FF:
            new_timer = 0x7FF
        chan["timer"] = new_timer

    # ── Pulse Channel ────────────────────────────────────────────────────────

    def _write_pulse_vol(self, chan: dict[str, Any], value: int) -> None:
        """Write to $4000/$4004: duty, loop/envelope, volume."""
        chan["duty"] = (value >> 6) & 0x03
        chan["env_loop"] = bool(value & 0x20)
        chan["env_enabled"] = not bool(value & 0x10)
        # When env_enabled is False, volume is constant.
        # When True, envelope generator uses the volume register as the period.
        chan["env_volume"] = value & 0x0F
        chan["env_decay"] = value & 0x0F
        chan["env_counter"] = value & 0x0F

    def _write_pulse_sweep(self, chan: dict[str, Any], value: int) -> None:
        """Write to $4001/$4005: sweep unit."""
        chan["sweep_enabled"] = bool(value & 0x80)
        chan["sweep_divider"] = (value >> 4) & 0x07
        chan["sweep_negate"] = bool(value & 0x08)
        chan["sweep_shift"] = value & 0x07
        chan["sweep_reload"] = True

    def _write_pulse_lo(self, chan: dict[str, Any], value: int) -> None:
        """Write to $4002/$4006: timer low 8 bits."""
        chan["timer"] = (chan["timer"] & 0x700) | value

    def _write_pulse_hi(self, chan: dict[str, Any], value: int) -> None:
        """Write to $4003/$4007: length index and timer high 3 bits."""
        length_index = (value >> 3) & 0x1F
        chan["timer"] = (chan["timer"] & 0xFF) | ((value & 0x07) << 8)
        chan["length_counter"] = LENGTH_TABLE[length_index]
        chan["duty_index"] = 0
        chan["env_counter"] = chan["env_volume"]

    def _advance_pulse(self, chan: dict[str, Any], cycles: float) -> None:
        """Advance a pulse channel by *cycles* CPU cycles and compute output."""
        if not chan["enabled"]:
            self.pulse1_output = 0 if chan is self.pulse1 else self.pulse1_output
            self.pulse2_output = 0 if chan is self.pulse2 else self.pulse2_output
            return

        # Calculate how many timer ticks elapsed.
        period = chan["timer"] + 1
        if period <= 0:
            period = 1
        # Advance the timer counter by the cycle count.
        chan["timer_counter"] += int(cycles)
        while chan["timer_counter"] >= 16 * period:
            chan["timer_counter"] -= 16 * period
            chan["duty_index"] = (chan["duty_index"] + 1) & 0x07

        # Check if channel should produce sound.
        if chan["length_counter"] == 0:
            value = 0
        else:
            # Check if timer is too low (ultrasonic → silence).
            if chan["timer"] < 8:
                value = 0
            else:
                waveform = _DUTY_WAVEFORMS[chan["duty"]]
                duty_bit = waveform[chan["duty_index"]]
                vol = chan["env_decay"] if chan["env_enabled"] else chan["env_volume"]
                value = duty_bit * vol

        if chan is self.pulse1:
            self.pulse1_output = value
        else:
            self.pulse2_output = value

    # ── Triangle Channel ─────────────────────────────────────────────────────

    def _write_tri_linear(self, value: int) -> None:
        """Write to $4008: linear counter control and reload."""
        self.triangle["linear_control"] = bool(value & 0x80)
        self.triangle["linear_reload"] = value & 0x7F

    def _write_tri_lo(self, value: int) -> None:
        """Write to $400A: timer low."""
        self.triangle["timer"] = (self.triangle["timer"] & 0x700) | value

    def _write_tri_hi(self, value: int) -> None:
        """Write to $400B: length index and timer high."""
        length_index = (value >> 3) & 0x1F
        self.triangle["timer"] = (self.triangle["timer"] & 0xFF) | ((value & 0x07) << 8)
        if self.triangle["enabled"]:
            self.triangle["length_counter"] = LENGTH_TABLE[length_index]
        self.triangle["linear_reload_flag"] = True

    def _advance_triangle(self, cycles: float) -> None:
        """Advance the triangle channel by *cycles* CPU cycles."""
        if not self.triangle["enabled"]:
            self.triangle_output = 0
            return

        period = self.triangle["timer"] + 1
        if period <= 0:
            period = 1

        # Advance timer counter.
        self.triangle["timer_counter"] += int(cycles)
        cycle_step = 32 * period
        while self.triangle["timer_counter"] >= cycle_step:
            self.triangle["timer_counter"] -= cycle_step
            if self.triangle["length_counter"] > 0 and self.triangle["linear_counter"] > 0:
                self.triangle["tri_step"] = (self.triangle["tri_step"] + 1) & 0x1F

        if self.triangle["length_counter"] == 0 or self.triangle["linear_counter"] == 0:
            self.triangle_output = 0
        elif self.triangle["timer"] < 2:
            self.triangle_output = 0
        else:
            self.triangle_output = _TRI_WAVE[self.triangle["tri_step"]]

    # ── Noise Channel ────────────────────────────────────────────────────────

    def _write_noise_vol(self, value: int) -> None:
        """Write to $400C: envelope / volume for noise channel."""
        self.noise["env_loop"] = bool(value & 0x20)
        self.noise["env_enabled"] = not bool(value & 0x10)
        self.noise["env_volume"] = value & 0x0F
        self.noise["env_decay"] = value & 0x0F
        self.noise["env_counter"] = value & 0x0F

    def _write_noise_lo(self, value: int) -> None:
        """Write to $400E: noise mode and period index."""
        self.noise["mode"] = (value >> 7) & 1
        period_index = value & 0x0F
        self.noise["timer"] = _NOISE_PERIODS[period_index]

    def _write_noise_hi(self, value: int) -> None:
        """Write to $400F: length index for noise channel."""
        length_index = (value >> 3) & 0x1F
        if self.noise["enabled"]:
            self.noise["length_counter"] = LENGTH_TABLE[length_index]
        self.noise["env_counter"] = self.noise["env_volume"]

    def _advance_noise(self, cycles: float) -> None:
        """Advance the noise channel by *cycles* CPU cycles."""
        if not self.noise["enabled"]:
            self.noise_output = 0
            return

        period = self.noise["timer"]
        if period <= 0:
            period = 1

        self.noise["timer_counter"] += int(cycles)
        while self.noise["timer_counter"] >= period:
            self.noise["timer_counter"] -= period
            # LFSR feedback
            shift_reg = self.noise["shift_register"]
            bit0 = shift_reg & 1
            if self.noise["mode"] == 0:
                # Long mode: feedback from bit 1
                other_bit = (shift_reg >> 1) & 1
            else:
                # Short mode: feedback from bit 6
                other_bit = (shift_reg >> 6) & 1
            feedback = bit0 ^ other_bit
            shift_reg = (shift_reg >> 1) | (feedback << 14)
            self.noise["shift_register"] = shift_reg & 0x7FFF

        if self.noise["length_counter"] == 0:
            self.noise_output = 0
        else:
            # Output is 0 if bit 0 is set (inverted).
            output_bit = (~self.noise["shift_register"]) & 1
            vol = self.noise["env_decay"] if self.noise["env_enabled"] else self.noise["env_volume"]
            self.noise_output = output_bit * vol

    # ── DMC Channel (basic framework) ────────────────────────────────────────

    def _write_dmc_freq(self, value: int) -> None:
        """Write to $4010: DMC IRQ enable, loop, and rate index."""
        self.dmc["irq_enabled"] = bool(value & 0x80)
        self.dmc["loop"] = bool(value & 0x40)
        self.dmc["rate_index"] = value & 0x0F
        self.dmc["rate_counter"] = _DMC_RATES[self.dmc["rate_index"]]

    def _write_dmc_raw(self, value: int) -> None:
        """Write to $4011: DMC raw output level (7-bit)."""
        self.dmc["output_unit"] = value & 0x7F

    def _write_dmc_start(self, value: int) -> None:
        """Write to $4012: DMC sample start address."""
        self.dmc["sample_address"] = 0xC000 + (value * 64)

    def _write_dmc_len(self, value: int) -> None:
        """Write to $4013: DMC sample length."""
        self.dmc["sample_length"] = (value * 16) + 1

    def _advance_dmc(self, cycles: float) -> None:
        """Advance the DMC channel by *cycles* CPU cycles."""
        dmc = self.dmc
        if not dmc["enabled"]:
            self.dmc_output = 0
            return

        if dmc["bytes_remaining"] == 0:
            self.dmc_output = 0
            return

        rate = _DMC_RATES[dmc["rate_index"]]
        # If the rate counter has not been initialised yet, prime it.
        if dmc["rate_counter"] <= 0:
            dmc["rate_counter"] = rate

        dmc["rate_counter"] -= int(cycles)
        while dmc["rate_counter"] <= 0:
            dmc["rate_counter"] += rate
            if dmc["bits_remaining"] == 0:
                # Fetch next byte (simplified: use 0, i.e. silence).
                # A full implementation would read from CPU memory.
                dmc["sample_buffer"] = 0
                dmc["bits_remaining"] = 8
                dmc["bytes_remaining"] -= 1
                if dmc["bytes_remaining"] == 0:
                    if dmc["loop"]:
                        dmc["bytes_remaining"] = dmc["sample_length"]
                    else:
                        dmc["output_unit"] = 0
                        break

            # Delta decode one bit.
            bit = dmc["sample_buffer"] & 1
            dmc["sample_buffer"] >>= 1
            dmc["bits_remaining"] -= 1

            if bit:
                dmc["output_unit"] = min(126, dmc["output_unit"] + 2)
            else:
                dmc["output_unit"] = max(0, dmc["output_unit"] - 2)

        if dmc["silence"]:
            self.dmc_output = 0
        else:
            self.dmc_output = dmc["output_unit"]

    # ── Enable / Status ──────────────────────────────────────────────────────

    def _write_enable(self, value: int) -> None:
        """Write to $4015: enable/disable channels."""
        self.pulse1["enabled"] = bool(value & 0x01)
        if not self.pulse1["enabled"]:
            self.pulse1["length_counter"] = 0

        self.pulse2["enabled"] = bool(value & 0x02)
        if not self.pulse2["enabled"]:
            self.pulse2["length_counter"] = 0

        self.triangle["enabled"] = bool(value & 0x04)
        if not self.triangle["enabled"]:
            self.triangle["length_counter"] = 0

        self.noise["enabled"] = bool(value & 0x08)
        if not self.noise["enabled"]:
            self.noise["length_counter"] = 0

        self.dmc["enabled"] = bool(value & 0x10)
        if not self.dmc["enabled"]:
            self.dmc["bytes_remaining"] = 0

    def _read_status(self) -> int:
        """Read $4015: channel status and frame IRQ flag."""
        result = 0
        if self.pulse1["length_counter"] > 0:
            result |= 0x01
        if self.pulse2["length_counter"] > 0:
            result |= 0x02
        if self.triangle["length_counter"] > 0:
            result |= 0x04
        if self.noise["length_counter"] > 0:
            result |= 0x08
        if self.dmc["bytes_remaining"] > 0:
            result |= 0x10
        if self._fc_irq:
            result |= 0x40
        # Reading $4015 clears the frame IRQ flag.
        self._fc_irq = False
        return result

    def _write_frame_counter(self, value: int) -> None:
        """Write to $4017: set frame counter mode and IRQ inhibit.

        Writing any value to $4017 resets the frame counter sequencer.
        """
        self._fc_mode = 5 if (value & 0x80) else 4
        self._fc_irq_inhibit = bool(value & 0x40)
        # Reset the frame counter.
        self._fc_cycle_accumulator = 0.0
        self._fc_step_index = 0
        # If mode is 5, immediately clock envelopes, sweeps, length counters.
        if self._fc_mode == 5:
            self._clock_envelopes()
            self._clock_sweeps()
            self._clock_length_counters()


# ═══════════════════════════════════════════════════════════════════════════════
# Channel factory
# ═══════════════════════════════════════════════════════════════════════════════

def _make_pulse() -> dict[str, Any]:
    """Create a fresh pulse-channel state dictionary."""
    return {
        "enabled": False,
        "duty": 0,
        "duty_index": 0,
        "env_loop": False,
        "env_enabled": False,
        "env_volume": 0,
        "env_decay": 0,
        "env_counter": 0,
        "timer": 0,
        "timer_counter": 0,
        "length_counter": 0,
        "length_halt": False,
        "sweep_enabled": False,
        "sweep_divider": 0,
        "sweep_negate": False,
        "sweep_shift": 0,
        "sweep_reload": False,
        "sweep_counter": 0,
    }
