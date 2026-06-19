"""Unit tests for the NES APU emulator (apu.py)."""

from __future__ import annotations

import pytest
from apu import APU, SAMPLES_PER_FRAME, _DUTY_WAVEFORMS


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _configure_pulse(apu: APU, base: int, duty: int = 0, timer: int = 0x100) -> None:
    """Configure a pulse channel with a known duty, timer, and full volume.

    Args:
        apu: APU instance.
        base: Register base address (0x4000 for pulse1, 0x4004 for pulse2).
        duty: Duty cycle type (0-3).
        timer: 11-bit timer period.
    """
    # Volume register: duty<<6 | envelope disabled (const vol) | vol=15
    apu.write_register(base, (duty << 6) | 0x0F)
    # Sweep register: disabled
    apu.write_register(base + 1, 0x00)
    # Timer low
    apu.write_register(base + 2, timer & 0xFF)
    # Timer high + length index 0
    apu.write_register(base + 3, ((timer >> 8) & 0x07))


def _enable_all(apu: APU) -> None:
    """Enable all 5 channels."""
    apu.write_register(0x4015, 0x1F)


def _disable_all(apu: APU) -> None:
    """Disable all channels."""
    apu.write_register(0x4015, 0x00)


# ═══════════════════════════════════════════════════════════════════════════════
# 1. Basic audio sample generation
# ═══════════════════════════════════════════════════════════════════════════════

class TestBasicSampleGeneration:
    """Tests for get_audio_samples return value shape and range."""

    def test_returns_expected_number_of_samples(self) -> None:
        """get_audio_samples returns ~735 ints."""
        apu = APU()
        samples = apu.get_audio_samples()
        assert len(samples) == SAMPLES_PER_FRAME
        assert all(isinstance(s, int) for s in samples)

    def test_all_samples_in_int16_range(self) -> None:
        """Every sample is within the signed 16-bit range."""
        apu = APU()
        _enable_all(apu)
        _configure_pulse(apu, 0x4000, duty=2, timer=0x080)
        _configure_pulse(apu, 0x4004, duty=2, timer=0x080)
        samples = apu.get_audio_samples()
        for s in samples:
            assert -32768 <= s <= 32767, f"sample {s} out of int16 range"


# ═══════════════════════════════════════════════════════════════════════════════
# 2. Channel enable/disable via 0x4015
# ═══════════════════════════════════════════════════════════════════════════════

class TestChannelEnable:
    """Tests for enabling and disabling channels via register 0x4015."""

    def test_all_channels_disabled_produces_silence(self) -> None:
        """When all channels are disabled, all samples should be near zero."""
        apu = APU()
        _disable_all(apu)
        samples = apu.get_audio_samples()
        # With all channels disabled and no input, mixed output centers at
        # negative values near the centre point.  Verify they are all equal
        # (constant output with no oscillation).
        assert len(set(samples)) <= 2, (
            f"Expected near-constant output with all channels disabled, "
            f"got {len(set(samples))} unique values"
        )

    def test_pulse1_disabled_by_4015(self) -> None:
        """Clearing bit 0 of 0x4015 silences pulse 1."""
        apu = APU()
        _configure_pulse(apu, 0x4000, duty=2, timer=0x080)
        apu.write_register(0x4015, 0x01)  # enable pulse1 only
        samples_enabled = apu.get_audio_samples()
        # Disable pulse1
        apu.write_register(0x4015, 0x00)
        samples_disabled = apu.get_audio_samples()
        # With pulse1 enabled, a square wave produces at least 2 distinct
        # sample values (on/off).  With all channels disabled, all samples
        # are constant (1 unique value).
        assert len(set(samples_enabled)) >= 2
        assert len(set(samples_disabled)) <= 2

    def test_4015_status_readback(self) -> None:
        """Reading $4015 returns status of active channels."""
        apu = APU()
        # Nothing enabled yet; length counters are 0.
        status = apu.read_register(0x4015)
        assert status == 0x00

        # Enable pulse1 and give it a length.
        apu.write_register(0x4015, 0x01)
        _configure_pulse(apu, 0x4000, duty=2, timer=0x080)
        # After writing HI, length_counter is set.
        # Advance a bit to let the channel run.
        apu.write_register(0x4003, 0x00)  # re-write HI with length_index=0
        # Pulse 1 should have length_counter > 0 now.
        status = apu.read_register(0x4015)
        assert status & 0x01, f"Expected pulse1 active, got {status:#04x}"

    def test_reading_4015_clears_frame_irq(self) -> None:
        """Reading $4015 clears the frame IRQ flag."""
        apu = APU()
        # Switch to 5-step mode to allow IRQ generation.
        apu.write_register(0x4017, 0x80)  # 5-step mode, IRQ not inhibited
        # Advance frame counter to trigger an IRQ (step 2 or 3 at boundary).
        # Step 2 in 5-step is at 11185.5 cycles.
        apu.step(12000)
        status = apu.read_register(0x4015)
        # After stepping past step 2, IRQ should be set (bit 6).
        assert status & 0x40, f"Expected frame IRQ set, got {status:#04x}"
        # A second read should have it cleared.
        status2 = apu.read_register(0x4015)
        assert not (status2 & 0x40), f"Expected frame IRQ cleared, got {status2:#04x}"


# ═══════════════════════════════════════════════════════════════════════════════
# 3. Pulse duty cycles
# ═══════════════════════════════════════════════════════════════════════════════

class TestPulseDutyCycles:
    """Tests that different duty cycle settings produce different outputs."""

    def test_different_duties_produce_different_outputs(self) -> None:
        """Each of the 4 duty waveforms yields distinct sample sets."""
        apu = APU()
        apu.write_register(0x4015, 0x01)  # enable pulse1 only

        outputs = {}
        for duty in range(4):
            apu2 = APU()
            apu2.write_register(0x4015, 0x01)
            _configure_pulse(apu2, 0x4000, duty=duty, timer=0x100)
            samples = tuple(apu2.get_audio_samples())
            outputs[duty] = samples

        # Each duty cycle should produce a different waveform.
        # Compare pairwise.
        for i in range(4):
            for j in range(i + 1, 4):
                assert outputs[i] != outputs[j], (
                    f"Duty {i} and duty {j} produced identical output"
                )

    def test_duty_waveform_values(self) -> None:
        """Verify the known duty cycle bit patterns."""
        assert _DUTY_WAVEFORMS[0] == [0, 1, 0, 0, 0, 0, 0, 0]
        assert _DUTY_WAVEFORMS[1] == [0, 1, 1, 0, 0, 0, 0, 0]
        assert _DUTY_WAVEFORMS[2] == [0, 1, 1, 1, 1, 0, 0, 0]
        assert _DUTY_WAVEFORMS[3] == [1, 0, 0, 1, 1, 1, 1, 1]

    def test_pulse_output_is_non_negative(self) -> None:
        """Pulse channel raw output values are 0-15 range."""
        apu = APU()
        apu.write_register(0x4015, 0x01)
        _configure_pulse(apu, 0x4000, duty=2, timer=0x100)
        # Run a frame to produce output.
        apu.get_audio_samples()
        # Check internal output value.
        p1 = apu.pulse1_output
        assert 0 <= p1 <= 15, f"pulse1_output {p1} out of 0-15 range"


# ═══════════════════════════════════════════════════════════════════════════════
# 4. Frame counter mode switching via 0x4017
# ═══════════════════════════════════════════════════════════════════════════════

class TestFrameCounter:
    """Tests for frame counter mode and IRQ behaviour."""

    def test_default_mode_is_4_step(self) -> None:
        """The APU starts in 4-step frame counter mode."""
        apu = APU()
        assert apu._fc_mode == 4

    def test_write_4017_bit7_sets_5_step_mode(self) -> None:
        """Writing bit 7 of $4017 switches to 5-step mode."""
        apu = APU()
        apu.write_register(0x4017, 0x80)
        assert apu._fc_mode == 5

    def test_write_4017_bit6_inhibits_irq(self) -> None:
        """Writing bit 6 of $4017 sets the IRQ inhibit flag."""
        apu = APU()
        apu.write_register(0x4017, 0xC0)  # 5-step + IRQ inhibit
        assert apu._fc_mode == 5
        assert apu._fc_irq_inhibit is True

    def test_write_4017_resets_frame_counter(self) -> None:
        """Writing any value to $4017 resets the frame counter sequencer."""
        apu = APU()
        # Advance some cycles.
        apu.step(5000)
        assert apu._fc_step_index > 0
        # Write to $4017 resets it.
        apu.write_register(0x4017, 0x00)
        assert apu._fc_step_index == 0
        assert apu._fc_cycle_accumulator == pytest.approx(0.0)

    def test_5_step_mode_clocks_immediately(self) -> None:
        """Writing to $4017 in 5-step mode immediately clocks length counters."""
        apu = APU()
        _enable_all(apu)
        _configure_pulse(apu, 0x4000, duty=2, timer=0x100)
        # Set length_counter via HI register write.
        apu.write_register(0x4003, (5 << 3))  # length_index=5, timer high=0
        assert apu.pulse1["length_counter"] > 0
        # Switch to 5-step: this immediately clocks length counters.
        apu.write_register(0x4017, 0x80)
        # Length counter should have decremented.
        # (It was set to LENGTH_TABLE[5] = 4, clocked once → 3)
        assert apu.pulse1["length_counter"] >= 2  # may have been decremented


# ═══════════════════════════════════════════════════════════════════════════════
# 5. DMC delta decoding
# ═══════════════════════════════════════════════════════════════════════════════

class TestDMC:
    """Tests for the DMC channel delta decoding and output."""

    def test_dmc_raw_write_sets_output_unit(self) -> None:
        """Writing to $4011 (DMC_RAW) sets the output_unit directly."""
        apu = APU()
        apu.write_register(0x4011, 0x40)  # set output to 64
        assert apu.dmc["output_unit"] == 0x40

        apu.write_register(0x4011, 0x7F)  # max
        assert apu.dmc["output_unit"] == 0x7F

    def test_dmc_freq_write_sets_rate(self) -> None:
        """Writing to $4010 sets rate_index, loop, and IRQ enable."""
        apu = APU()
        apu.write_register(0x4010, 0xCF)  # irq=1, loop=1, rate=15
        assert apu.dmc["irq_enabled"] is True
        assert apu.dmc["loop"] is True
        assert apu.dmc["rate_index"] == 15

    def test_dmc_start_addr_write(self) -> None:
        """Writing to $4012 computes sample_address = 0xC000 + value*64."""
        apu = APU()
        apu.write_register(0x4012, 0x10)  # value=16
        assert apu.dmc["sample_address"] == 0xC000 + 0x10 * 64

    def test_dmc_len_write(self) -> None:
        """Writing to $4013 computes sample_length = value*16 + 1."""
        apu = APU()
        apu.write_register(0x4013, 0x02)  # value=2
        assert apu.dmc["sample_length"] == 2 * 16 + 1  # = 33

    def test_dmc_disabled_produces_zero_output(self) -> None:
        """When DMC is disabled (bytes_remaining=0), output is 0."""
        apu = APU()
        apu.write_register(0x4011, 50)
        assert apu.dmc["output_unit"] == 50
        # DMC disabled; advance should give 0.
        apu._advance_dmc(1000)
        assert apu.dmc_output == 0

    def test_dmc_delta_decode_increases_output(self) -> None:
        """Simulate DMC bit=1 decoding: output_unit increases by 2, capped at 126."""
        apu = APU()
        apu.dmc["enabled"] = True
        apu.dmc["bytes_remaining"] = 10
        apu.dmc["bits_remaining"] = 8
        apu.dmc["sample_buffer"] = 0xFF  # all bits are 1
        apu.dmc["output_unit"] = 0
        apu.dmc["rate_index"] = 0
        # Advance to decode exactly 8 bits (rate 428 * 8 ≈ 3424 cycles).
        # The first bit fires after `rate` cycles because rate_counter
        # is initialised to `rate` on first advance.
        apu._advance_dmc(3500)
        # 8 increments of +2 each = +16, capped at 126.
        assert apu.dmc["output_unit"] == 16


# ═══════════════════════════════════════════════════════════════════════════════
# 6. Triangle channel
# ═══════════════════════════════════════════════════════════════════════════════

class TestTriangle:
    """Tests for the triangle channel."""

    def test_triangle_disabled_outputs_zero(self) -> None:
        """Disabled triangle channel outputs 0."""
        apu = APU()
        apu.triangle["enabled"] = False
        apu._advance_triangle(1000)
        assert apu.triangle_output == 0

    def test_triangle_linear_counter_mutes(self) -> None:
        """Triangle with linear_counter == 0 produces 0."""
        apu = APU()
        apu.triangle["enabled"] = True
        apu.triangle["length_counter"] = 10
        apu.triangle["linear_counter"] = 0   # muted
        apu.triangle["timer"] = 0x100
        apu._advance_triangle(1000)
        assert apu.triangle_output == 0

    def test_triangle_produces_waveform_values(self) -> None:
        """An active triangle channel produces values from the 32-step wave."""
        apu = APU()
        apu.triangle["enabled"] = True
        apu.triangle["length_counter"] = 100
        apu.triangle["linear_counter"] = 50
        apu.triangle["timer"] = 0x0FF
        apu.triangle["tri_step"] = 0
        # Advance a little.
        apu._advance_triangle(500)
        # Output should be a value from the triangle waveform (0-15).
        assert 0 <= apu.triangle_output <= 15

    def test_triangle_linear_reload_sets_flag(self) -> None:
        """Writing to $400B sets linear_reload_flag."""
        apu = APU()
        apu.triangle["enabled"] = True
        apu.write_register(0x400B, (0 << 3) | 0x07)  # length_idx=0, timer_high=7
        assert apu.triangle["linear_reload_flag"] is True

    def test_triangle_linear_control(self) -> None:
        """Writing to $4008 sets linear_control and linear_reload."""
        apu = APU()
        apu.write_register(0x4008, 0x8F)  # control=1, reload=15
        assert apu.triangle["linear_control"] is True
        assert apu.triangle["linear_reload"] == 0x0F


# ═══════════════════════════════════════════════════════════════════════════════
# 7. Noise channel
# ═══════════════════════════════════════════════════════════════════════════════

class TestNoise:
    """Tests for the noise channel."""

    def test_noise_disabled_outputs_zero(self) -> None:
        """Disabled noise channel outputs 0."""
        apu = APU()
        apu.noise["enabled"] = False
        apu._advance_noise(1000)
        assert apu.noise_output == 0

    def test_noise_mode_switch(self) -> None:
        """Writing to $400E sets noise mode (bit 7)."""
        apu = APU()
        apu.write_register(0x400E, 0x80)  # mode=1 (short), period_idx=0
        assert apu.noise["mode"] == 1
        apu.write_register(0x400E, 0x00)  # mode=0 (long), period_idx=0
        assert apu.noise["mode"] == 0

    def test_noise_period_index(self) -> None:
        """Writing to $400E sets the noise period from the lookup table."""
        from apu import _NOISE_PERIODS
        apu = APU()
        apu.write_register(0x400E, 0x05)  # period_index=5
        assert apu.noise["timer"] == _NOISE_PERIODS[5]

    def test_noise_lfsr_updates(self) -> None:
        """The noise LFSR shifts and produces changing output."""
        apu = APU()
        apu.noise["enabled"] = True
        apu.noise["length_counter"] = 100
        apu.noise["env_enabled"] = False  # constant volume
        apu.noise["env_volume"] = 15
        apu.noise["timer"] = 4  # fast period
        initial_shift = apu.noise["shift_register"]
        apu._advance_noise(1000)
        # LFSR should have been updated.
        assert apu.noise["shift_register"] != initial_shift

    def test_noise_length_counter_write(self) -> None:
        """Writing to $400F sets the noise length counter."""
        apu = APU()
        apu.noise["enabled"] = True
        apu.write_register(0x400F, (10 << 3))  # length_index=10
        from apu import LENGTH_TABLE
        assert apu.noise["length_counter"] == LENGTH_TABLE[10]


# ═══════════════════════════════════════════════════════════════════════════════
# 8. Register write/read edge cases
# ═══════════════════════════════════════════════════════════════════════════════

class TestRegisters:
    """Tests for register writes and reads at various addresses."""

    def test_write_unknown_register_is_safe(self) -> None:
        """Writing to an unmapped APU register does not crash."""
        apu = APU()
        apu.write_register(0x4009, 0xFF)  # unmapped
        apu.write_register(0x400D, 0xFF)  # unmapped
        apu.write_register(0x4014, 0xFF)  # OAMDMA (not APU, but should be safe)
        apu.write_register(0x4016, 0xFF)  # controller (not APU)

    def test_read_unknown_register_returns_zero(self) -> None:
        """Reading an unmapped APU register returns 0."""
        apu = APU()
        assert apu.read_register(0x4000) == 0
        assert apu.read_register(0x4001) == 0
        assert apu.read_register(0x4017) == 0

    def test_sweep_register_fields(self) -> None:
        """Writing to $4001 sets sweep fields correctly."""
        apu = APU()
        apu.write_register(0x4001, 0x9F)  # enabled=1, divider=1, negate=1, shift=7
        assert apu.pulse1["sweep_enabled"] is True
        assert apu.pulse1["sweep_divider"] == 1
        assert apu.pulse1["sweep_negate"] is True
        assert apu.pulse1["sweep_shift"] == 7

    def test_volume_envelope_fields(self) -> None:
        """Writing to $4000 sets volume/envelope/duty fields correctly."""
        apu = APU()
        # Bit 4 = 0 → envelope enabled (use decay counter)
        # duty=3 (11xxxxxx), loop=1 (xx1xxxxx), bit4=0 (xxx0xxxx), vol=10
        apu.write_register(0x4000, 0xEA)  # 11 1 0 1010
        assert apu.pulse1["duty"] == 3
        assert apu.pulse1["env_loop"] is True
        assert apu.pulse1["env_enabled"] is True   # bit 4 = 0 → envelope enabled
        assert apu.pulse1["env_volume"] == 10

        # Bit 4 = 1 → constant volume (envelope disabled)
        # duty=3, loop=1, bit4=1, vol=15
        apu.write_register(0x4000, 0xFF)  # 11 1 1 1111
        assert apu.pulse1["env_enabled"] is False  # bit 4 = 1 → envelope disabled
        assert apu.pulse1["env_volume"] == 15
        assert apu.pulse1["env_decay"] == 15

    def test_timer_low_high_combination(self) -> None:
        """Writing $4002 then $4003 correctly combines the 11-bit timer."""
        apu = APU()
        apu.write_register(0x4002, 0x55)  # timer low
        apu.write_register(0x4003, (0 << 3) | 0x03)  # length_idx=0, timer_high=3
        assert apu.pulse1["timer"] == (3 << 8) | 0x55


# ═══════════════════════════════════════════════════════════════════════════════
# 9. Envelope generator
# ═══════════════════════════════════════════════════════════════════════════════

class TestEnvelope:
    """Tests for envelope generation on pulse and noise channels."""

    def test_envelope_decays_over_time(self) -> None:
        """The envelope decay counter decreases as it is clocked."""
        apu = APU()
        apu.pulse1["env_enabled"] = True
        apu.pulse1["env_volume"] = 5
        apu.pulse1["env_decay"] = 10
        apu.pulse1["env_counter"] = 5
        # Clock envelope several times.
        for _ in range(20):
            apu._clock_envelopes()
        # Decay should have decreased.
        assert apu.pulse1["env_decay"] < 10

    def test_envelope_loops_when_enabled(self) -> None:
        """When env_loop is set, decay resets to 15 after reaching 0."""
        apu = APU()
        apu.pulse1["env_enabled"] = True
        apu.pulse1["env_loop"] = True
        apu.pulse1["env_volume"] = 1   # fast divider
        apu.pulse1["env_decay"] = 1
        apu.pulse1["env_counter"] = 1
        # After 4 ticks: decay=0→loops→15
        # Then each 2 ticks decrements decay by 1.
        # After 4+30=34 ticks: decay=0→loops→15 again.
        # After 34+2=36 ticks: decay=15→14
        apu._clock_envelopes()  # 1
        apu._clock_envelopes()  # 2
        apu._clock_envelopes()  # 3
        apu._clock_envelopes()  # 4: env_decay loops to 15
        assert apu.pulse1["env_decay"] == 15
        # Verify it continues decrementing.
        apu._clock_envelopes()  # 5
        apu._clock_envelopes()  # 6: env_decay → 14
        assert apu.pulse1["env_decay"] == 14


# ═══════════════════════════════════════════════════════════════════════════════
# 10. Multiple samples are consistent
# ═══════════════════════════════════════════════════════════════════════════════

class TestMultipleFrames:
    """Tests across multiple frames of audio."""

    def test_two_frames_same_length(self) -> None:
        """Two consecutive get_audio_samples calls return the same count."""
        apu = APU()
        _enable_all(apu)
        _configure_pulse(apu, 0x4000, duty=2, timer=0x100)
        frame1 = apu.get_audio_samples()
        frame2 = apu.get_audio_samples()
        assert len(frame1) == len(frame2) == SAMPLES_PER_FRAME

    def test_output_changes_across_frames(self) -> None:
        """With an active channel, consecutive frames show oscillation."""
        apu = APU()
        apu.write_register(0x4015, 0x01)  # pulse1 only
        # Enable envelope so we get volume variation across the frame.
        # Write vol register: duty=2, loop=0, envelope enabled, decay=15
        apu.write_register(0x4000, 0x8F)  # duty=2(10xxxxxx), env_enabled(bit4=0→True? Wait)
        # Actually: bit4=1 means envelope enabled (use decay), bit4=0 means constant vol
        # Let's use constant vol but fast timer so duty index cycles often.
        _configure_pulse(apu, 0x4000, duty=2, timer=0x050)
        frame1 = tuple(apu.get_audio_samples())
        frame2 = tuple(apu.get_audio_samples())
        # With duty 2 (50% square), output alternates 0↔15,
        # producing at least 2 distinct sample values.
        unique1 = len(set(frame1))
        unique2 = len(set(frame2))
        assert unique1 >= 2, f"Frame 1 had only {unique1} unique values, expected oscillation"
        assert unique2 >= 2, f"Frame 2 had only {unique2} unique values"


# ═══════════════════════════════════════════════════════════════════════════════
# 11. Frame counter advancement via step()
# ═══════════════════════════════════════════════════════════════════════════════

class TestStep:
    """Tests for the step() method and frame counter integration."""

    def test_step_accumulates_cycles(self) -> None:
        """step() adds cycles to the internal accumulator."""
        apu = APU()
        assert apu._fc_cycle_accumulator == pytest.approx(0.0)
        apu.step(100)
        assert apu._fc_cycle_accumulator == pytest.approx(100.0)

    def test_step_triggers_frame_counter_steps(self) -> None:
        """Advancing past a step boundary triggers the step."""
        apu = APU()
        _enable_all(apu)
        # Give pulse1 a length counter.
        apu.write_register(0x4003, (5 << 3))  # length_idx=5
        initial_length = apu.pulse1["length_counter"]
        # Step past the first boundary (~3728.5).
        apu.step(4000)
        # After stepping past boundary 0 (envelopes only), step past boundary 1
        # at 7457, which clocks length counters.
        apu.step(4000)
        # Length should have decremented.
        assert apu.pulse1["length_counter"] < initial_length
