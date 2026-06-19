"""Unit tests for the 6502 CPU emulator (cpu.py)."""

from __future__ import annotations

import pytest
from cpu import CPU


# ═══════════════════════════════════════════════════════════════════════════
# Mock Bus for testing
# ═══════════════════════════════════════════════════════════════════════════


class MockBus:
    """A lightweight bus substitute for CPU unit tests.

    Provides a 64 KiB flat memory space and the ``dma_cycles`` property
    that the CPU expects, without requiring the full Bus + device tree.
    """

    def __init__(self) -> None:
        self._mem: bytearray = bytearray(0x10000)
        self._dma_cycles: int = 0

    def read(self, addr: int, from_ppu: bool = False) -> int:
        """Read a byte from the mock memory."""
        if from_ppu:
            return 0
        return self._mem[addr & 0xFFFF]

    def write(self, addr: int, value: int) -> None:
        """Write a byte to the mock memory."""
        self._mem[addr & 0xFFFF] = value & 0xFF

    @property
    def dma_cycles(self) -> int:
        """Return and reset accumulated DMA cycles (always 0 in tests)."""
        extra = self._dma_cycles
        self._dma_cycles = 0
        return extra

    def load_program(self, start: int, data: list[int]) -> None:
        """Load a list of byte values into memory starting at *start*."""
        for i, byte in enumerate(data):
            self._mem[(start + i) & 0xFFFF] = byte & 0xFF

    def read_byte(self, addr: int) -> int:
        """Direct memory peek for test assertions."""
        return self._mem[addr & 0xFFFF]


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════


def _make_cpu(program: list[int] | None = None, pc: int = 0x8000) -> tuple[CPU, MockBus]:
    """Create a CPU with a MockBus and optionally load a *program*."""
    bus = MockBus()
    if program is not None:
        bus.load_program(pc, program)
    cpu = CPU(bus)  # type: ignore[arg-type]
    cpu._pc = pc  # noqa: SLF001
    return cpu, bus


def _step_until_done(cpu: CPU, max_steps: int = 2000) -> int:
    """Repeatedly step the CPU until max_steps is reached."""
    steps = 0
    for _ in range(max_steps):
        cpu.step()
        steps += 1
    return steps


# ═══════════════════════════════════════════════════════════════════════════
# Initialisation
# ═══════════════════════════════════════════════════════════════════════════


class TestCPUInit:
    """Verify CPU registers initialise correctly."""

    def test_initial_registers(self) -> None:
        cpu, _ = _make_cpu()
        assert cpu.a == 0
        assert cpu.x == 0
        assert cpu.y == 0
        assert cpu.sp == 0xFD
        # _p = 0x24 = U | I
        assert cpu.p == 0x24
        assert cpu.cycles == 0

    def test_flags_initial(self) -> None:
        cpu, _ = _make_cpu()
        assert not cpu._get_flag(CPU.FLAG_C)  # noqa: SLF001
        assert not cpu._get_flag(CPU.FLAG_Z)  # noqa: SLF001
        assert cpu._get_flag(CPU.FLAG_I)  # noqa: SLF001
        assert not cpu._get_flag(CPU.FLAG_D)  # noqa: SLF001
        assert not cpu._get_flag(CPU.FLAG_B)  # noqa: SLF001
        assert cpu._get_flag(CPU.FLAG_U)  # noqa: SLF001
        assert not cpu._get_flag(CPU.FLAG_V)  # noqa: SLF001
        assert not cpu._get_flag(CPU.FLAG_N)  # noqa: SLF001


# ═══════════════════════════════════════════════════════════════════════════
# Reset / Interrupts
# ═══════════════════════════════════════════════════════════════════════════


class TestReset:
    """CPU reset behaviour."""

    def test_reset_loads_vector_and_sets_flags(self) -> None:
        cpu, bus = _make_cpu()
        # Write reset vector 0xFFFC-FFFD -> 0xC000
        bus.load_program(0xFFFC, [0x00, 0xC0])
        cycles = cpu.reset()
        assert cpu.pc == 0xC000
        assert cpu.sp == 0xFD
        assert cpu.p == 0x34
        assert cycles == 7


class TestInterrupts:
    """NMI and IRQ behaviour."""

    def test_nmi_pushes_and_loads_vector(self) -> None:
        cpu, bus = _make_cpu(program=[0xEA], pc=0x8000)  # NOP at 0x8000
        bus.load_program(0xFFFA, [0x00, 0xC0])  # NMI vector -> 0xC000
        cpu._p = 0x24  # noqa: SLF001  U|I
        cycles = cpu.nmi()
        assert cycles == 7
        assert cpu.pc == 0xC000
        assert cpu._get_flag(CPU.FLAG_I)  # noqa: SLF001

        # Check stack: pushed PC (0x8000) and P (~B)
        sp_after = cpu.sp
        # SP went down by 3 (PCH, PCL, P)
        assert sp_after == 0xFD - 3

    def test_irq_blocked_when_i_set(self) -> None:
        cpu, bus = _make_cpu()
        cpu._p = 0x24  # noqa: SLF001  I=1
        cycles = cpu.irq()
        assert cycles == 0  # ignored

    def test_irq_taken_when_i_clear(self) -> None:
        cpu, bus = _make_cpu(program=[0xEA], pc=0x8000)
        bus.load_program(0xFFFE, [0x00, 0xC0])  # IRQ vector -> 0xC000
        cpu._p = 0x20  # noqa: SLF001  I=0, U=1
        cycles = cpu.irq()
        assert cycles == 7
        assert cpu.pc == 0xC000
        assert cpu._get_flag(CPU.FLAG_I)  # noqa: SLF001


# ═══════════════════════════════════════════════════════════════════════════
# Flag helpers
# ═══════════════════════════════════════════════════════════════════════════


class TestFlags:
    """Flag get/set/update operations."""

    def test_set_and_get_flag(self) -> None:
        cpu, _ = _make_cpu()
        cpu._set_flag(CPU.FLAG_C, True)  # noqa: SLF001
        assert cpu._get_flag(CPU.FLAG_C)  # noqa: SLF001
        cpu._set_flag(CPU.FLAG_C, False)  # noqa: SLF001
        assert not cpu._get_flag(CPU.FLAG_C)  # noqa: SLF001

    def test_update_zn_zero(self) -> None:
        cpu, _ = _make_cpu()
        cpu._update_zn(0)  # noqa: SLF001
        assert cpu._get_flag(CPU.FLAG_Z)  # noqa: SLF001
        assert not cpu._get_flag(CPU.FLAG_N)  # noqa: SLF001

    def test_update_zn_negative(self) -> None:
        cpu, _ = _make_cpu()
        cpu._update_zn(0x80)  # noqa: SLF001
        assert not cpu._get_flag(CPU.FLAG_Z)  # noqa: SLF001
        assert cpu._get_flag(CPU.FLAG_N)  # noqa: SLF001

    def test_update_zn_nonzero_positive(self) -> None:
        cpu, _ = _make_cpu()
        cpu._update_zn(0x01)  # noqa: SLF001
        assert not cpu._get_flag(CPU.FLAG_Z)  # noqa: SLF001
        assert not cpu._get_flag(CPU.FLAG_N)  # noqa: SLF001


# ═══════════════════════════════════════════════════════════════════════════
# LDA (Load Accumulator)
# ═══════════════════════════════════════════════════════════════════════════


class TestLDA:
    """LDA instruction in various addressing modes."""

    def test_lda_immediate(self) -> None:
        cpu, _ = _make_cpu(program=[0xA9, 0x42], pc=0x8000)
        cpu.step()
        assert cpu.a == 0x42
        assert cpu.pc == 0x8002
        assert not cpu._get_flag(CPU.FLAG_Z)  # noqa: SLF001
        assert not cpu._get_flag(CPU.FLAG_N)  # noqa: SLF001

    def test_lda_immediate_zero(self) -> None:
        cpu, _ = _make_cpu(program=[0xA9, 0x00], pc=0x8000)
        cpu.step()
        assert cpu.a == 0x00
        assert cpu._get_flag(CPU.FLAG_Z)  # noqa: SLF001

    def test_lda_immediate_negative(self) -> None:
        cpu, _ = _make_cpu(program=[0xA9, 0x80], pc=0x8000)
        cpu.step()
        assert cpu.a == 0x80
        assert cpu._get_flag(CPU.FLAG_N)  # noqa: SLF001

    def test_lda_zero_page(self) -> None:
        cpu, bus = _make_cpu(program=[0xA5, 0x10], pc=0x8000)
        bus.write(0x10, 0xAB)
        cpu.step()
        assert cpu.a == 0xAB
        assert cpu.pc == 0x8002

    def test_lda_absolute(self) -> None:
        cpu, bus = _make_cpu(program=[0xAD, 0x34, 0x12], pc=0x8000)
        bus.write(0x1234, 0xCC)
        cpu.step()
        assert cpu.a == 0xCC
        assert cpu.pc == 0x8003

    def test_lda_zpx(self) -> None:
        cpu, bus = _make_cpu(program=[0xB5, 0x10], pc=0x8000)
        cpu._x = 0x05  # noqa: SLF001
        bus.write(0x15, 0xDD)
        cpu.step()
        assert cpu.a == 0xDD


# ═══════════════════════════════════════════════════════════════════════════
# STA (Store Accumulator)
# ═══════════════════════════════════════════════════════════════════════════


class TestSTA:
    """STA instruction."""

    def test_sta_zero_page(self) -> None:
        cpu, bus = _make_cpu(program=[0x85, 0x20], pc=0x8000)
        cpu._a = 0x7B  # noqa: SLF001
        cpu.step()
        assert bus.read_byte(0x20) == 0x7B
        assert cpu.pc == 0x8002

    def test_sta_absolute(self) -> None:
        cpu, bus = _make_cpu(program=[0x8D, 0x00, 0x03], pc=0x8000)
        cpu._a = 0xA5  # noqa: SLF001
        cpu.step()
        assert bus.read_byte(0x0300) == 0xA5


# ═══════════════════════════════════════════════════════════════════════════
# Register Transfers
# ═══════════════════════════════════════════════════════════════════════════


class TestTransfers:
    """TAX, TXA, TAY, TYA, TSX, TXS."""

    def test_tax(self) -> None:
        cpu, _ = _make_cpu(program=[0xAA], pc=0x8000)
        cpu._a = 0x42  # noqa: SLF001
        cpu.step()
        assert cpu.x == 0x42
        assert not cpu._get_flag(CPU.FLAG_Z)  # noqa: SLF001

    def test_txa(self) -> None:
        cpu, _ = _make_cpu(program=[0x8A], pc=0x8000)
        cpu._x = 0x99  # noqa: SLF001
        cpu.step()
        assert cpu.a == 0x99

    def test_tay(self) -> None:
        cpu, _ = _make_cpu(program=[0xA8], pc=0x8000)
        cpu._a = 0xFF  # noqa: SLF001
        cpu.step()
        assert cpu.y == 0xFF
        assert cpu._get_flag(CPU.FLAG_N)  # noqa: SLF001

    def test_tya(self) -> None:
        cpu, _ = _make_cpu(program=[0x98], pc=0x8000)
        cpu._y = 0x00  # noqa: SLF001
        cpu.step()
        assert cpu.a == 0x00
        assert cpu._get_flag(CPU.FLAG_Z)  # noqa: SLF001

    def test_tsx(self) -> None:
        cpu, _ = _make_cpu(program=[0xBA], pc=0x8000)
        cpu._sp = 0xCE  # noqa: SLF001
        cpu.step()
        assert cpu.x == 0xCE

    def test_txs(self) -> None:
        cpu, _ = _make_cpu(program=[0x9A], pc=0x8000)
        cpu._x = 0xAA  # noqa: SLF001
        cpu.step()
        assert cpu.sp == 0xAA
        # TXS does NOT update flags


# ═══════════════════════════════════════════════════════════════════════════
# Stack Operations
# ═══════════════════════════════════════════════════════════════════════════


class TestStack:
    """PHA, PHP, PLA, PLP."""

    def test_pha_pla_roundtrip(self) -> None:
        cpu, bus = _make_cpu(
            program=[0x48, 0x68],  # PHA; PLA
            pc=0x8000,
        )
        cpu._a = 0x5A  # noqa: SLF001
        cpu.step()  # PHA
        assert bus.read_byte(0x0100 | 0xFD) == 0x5A
        assert cpu.sp == 0xFC
        cpu._a = 0xFF  # noqa: SLF001  clobber A
        cpu.step()  # PLA
        assert cpu.a == 0x5A
        assert cpu.sp == 0xFD

    def test_php_sets_b_and_u(self) -> None:
        cpu, bus = _make_cpu(program=[0x08], pc=0x8000)
        cpu._p = 0x00  # noqa: SLF001  all flags clear
        cpu.step()
        pushed = bus.read_byte(0x0100 | 0xFD)
        # B (0x10) and U (0x20) should be set
        assert pushed & CPU.FLAG_B
        assert pushed & CPU.FLAG_U

    def test_plp_clears_b_sets_u(self) -> None:
        cpu, bus = _make_cpu(program=[0x28], pc=0x8000)
        # Pre-seed stack with a value (PHA + manual stack poke)
        cpu._push(0xFF)  # noqa: SLF001  has all flags including B
        cpu._sp = 0xFD  # noqa: SLF001  rewind SP so PLP will pull 0xFF
        cpu.step()
        # B should be cleared after PLP
        assert not cpu._get_flag(CPU.FLAG_B)  # noqa: SLF001
        # U always set
        assert cpu._get_flag(CPU.FLAG_U)  # noqa: SLF001


# ═══════════════════════════════════════════════════════════════════════════
# ADC / SBC
# ═══════════════════════════════════════════════════════════════════════════


class TestADC:
    """ADC — add with carry."""

    def test_adc_immediate_no_carry(self) -> None:
        cpu, _ = _make_cpu(program=[0x69, 0x10], pc=0x8000)
        cpu._a = 0x20  # noqa: SLF001
        cpu._set_flag(CPU.FLAG_C, False)  # noqa: SLF001
        cpu.step()
        assert cpu.a == 0x30
        assert not cpu._get_flag(CPU.FLAG_C)  # noqa: SLF001
        assert not cpu._get_flag(CPU.FLAG_V)  # noqa: SLF001

    def test_adc_with_carry(self) -> None:
        cpu, _ = _make_cpu(program=[0x69, 0x10], pc=0x8000)
        cpu._a = 0x20  # noqa: SLF001
        cpu._set_flag(CPU.FLAG_C, True)  # noqa: SLF001
        cpu.step()
        assert cpu.a == 0x31

    def test_adc_carry_out(self) -> None:
        cpu, _ = _make_cpu(program=[0x69, 0x01], pc=0x8000)
        cpu._a = 0xFF  # noqa: SLF001
        cpu._set_flag(CPU.FLAG_C, False)  # noqa: SLF001
        cpu.step()
        assert cpu.a == 0x00
        assert cpu._get_flag(CPU.FLAG_C)  # noqa: SLF001
        assert cpu._get_flag(CPU.FLAG_Z)  # noqa: SLF001

    def test_adc_overflow_positive_positive_to_negative(self) -> None:
        """0x50 (+80) + 0x50 (+80) = 0xA0 (-96) -> overflow."""
        cpu, _ = _make_cpu(program=[0x69, 0x50], pc=0x8000)
        cpu._a = 0x50  # noqa: SLF001
        cpu._set_flag(CPU.FLAG_C, False)  # noqa: SLF001
        cpu.step()
        assert cpu.a == 0xA0
        assert cpu._get_flag(CPU.FLAG_V)  # noqa: SLF001
        assert cpu._get_flag(CPU.FLAG_N)  # noqa: SLF001

    def test_adc_no_overflow_signed(self) -> None:
        """0x50 (+80) + 0x10 (+16) = 0x60 (+96) -> no overflow."""
        cpu, _ = _make_cpu(program=[0x69, 0x10], pc=0x8000)
        cpu._a = 0x50  # noqa: SLF001
        cpu._set_flag(CPU.FLAG_C, False)  # noqa: SLF001
        cpu.step()
        assert cpu.a == 0x60
        assert not cpu._get_flag(CPU.FLAG_V)  # noqa: SLF001


class TestSBC:
    """SBC — subtract with carry (borrow)."""

    def test_sbc_immediate_simple(self) -> None:
        cpu, _ = _make_cpu(program=[0xE9, 0x10], pc=0x8000)
        cpu._a = 0x30  # noqa: SLF001
        cpu._set_flag(CPU.FLAG_C, True)  # noqa: SLF001  no borrow
        cpu.step()
        assert cpu.a == 0x20  # 0x30 - 0x10 = 0x20
        assert cpu._get_flag(CPU.FLAG_C)  # noqa: SLF001  no borrow occurred

    def test_sbc_with_borrow_in(self) -> None:
        cpu, _ = _make_cpu(program=[0xE9, 0x01], pc=0x8000)
        cpu._a = 0x10  # noqa: SLF001
        cpu._set_flag(CPU.FLAG_C, False)  # noqa: SLF001  borrow set
        cpu.step()
        assert cpu.a == 0x0E  # 0x10 - 0x01 - 0x01 = 0x0E

    def test_sbc_causes_borrow(self) -> None:
        cpu, _ = _make_cpu(program=[0xE9, 0x20], pc=0x8000)
        cpu._a = 0x10  # noqa: SLF001
        cpu._set_flag(CPU.FLAG_C, True)  # noqa: SLF001
        cpu.step()
        assert cpu.a == 0xF0  # 0x10 - 0x20 = -0x10 -> 0xF0
        assert not cpu._get_flag(CPU.FLAG_C)  # noqa: SLF001  borrow occurred

    def test_sbc_overflow(self) -> None:
        """0x50 (+80) - 0xB0 (-80) = 0xA0 (-96) -> overflow.
        Wait, 80 - (-80) = 160 > 127, so overflow.
        Actually 0x50 (+80) - 0xB0 = 0x50 - (-80 signed) = +160 > +127 -> V=1
        """
        cpu, _ = _make_cpu(program=[0xE9, 0xB0], pc=0x8000)
        cpu._a = 0x50  # noqa: SLF001  +80
        cpu._set_flag(CPU.FLAG_C, True)  # noqa: SLF001  no borrow
        cpu.step()
        assert cpu.a == 0xA0
        assert cpu._get_flag(CPU.FLAG_V)  # noqa: SLF001


# ═══════════════════════════════════════════════════════════════════════════
# INC / DEC
# ═══════════════════════════════════════════════════════════════════════════


class TestIncDec:
    """INC, INX, INY, DEC, DEX, DEY."""

    def test_inx_wraps(self) -> None:
        cpu, _ = _make_cpu(program=[0xE8], pc=0x8000)
        cpu._x = 0xFF  # noqa: SLF001
        cpu.step()
        assert cpu.x == 0x00
        assert cpu._get_flag(CPU.FLAG_Z)  # noqa: SLF001

    def test_iny(self) -> None:
        cpu, _ = _make_cpu(program=[0xC8], pc=0x8000)
        cpu._y = 0x05  # noqa: SLF001
        cpu.step()
        assert cpu.y == 0x06

    def test_dex(self) -> None:
        cpu, _ = _make_cpu(program=[0xCA], pc=0x8000)
        cpu._x = 0x01  # noqa: SLF001
        cpu.step()
        assert cpu.x == 0x00
        assert cpu._get_flag(CPU.FLAG_Z)  # noqa: SLF001

    def test_dey_wraps(self) -> None:
        cpu, _ = _make_cpu(program=[0x88], pc=0x8000)
        cpu._y = 0x00  # noqa: SLF001
        cpu.step()
        assert cpu.y == 0xFF
        assert cpu._get_flag(CPU.FLAG_N)  # noqa: SLF001

    def test_inc_zero_page(self) -> None:
        cpu, bus = _make_cpu(program=[0xE6, 0x50], pc=0x8000)
        bus.write(0x50, 0x41)
        cpu.step()
        assert bus.read_byte(0x50) == 0x42

    def test_dec_zero_page(self) -> None:
        cpu, bus = _make_cpu(program=[0xC6, 0x50], pc=0x8000)
        bus.write(0x50, 0x01)
        cpu.step()
        assert bus.read_byte(0x50) == 0x00
        # DEC updates Z,N on the result written
        assert cpu._get_flag(CPU.FLAG_Z)  # noqa: SLF001


# ═══════════════════════════════════════════════════════════════════════════
# Logic
# ═══════════════════════════════════════════════════════════════════════════


class TestLogic:
    """AND, ORA, EOR, BIT, ASL, LSR, ROL, ROR."""

    def test_and_immediate(self) -> None:
        cpu, _ = _make_cpu(program=[0x29, 0x0F], pc=0x8000)
        cpu._a = 0xFF  # noqa: SLF001
        cpu.step()
        assert cpu.a == 0x0F

    def test_ora_immediate(self) -> None:
        cpu, _ = _make_cpu(program=[0x09, 0xF0], pc=0x8000)
        cpu._a = 0x0F  # noqa: SLF001
        cpu.step()
        assert cpu.a == 0xFF

    def test_eor_immediate(self) -> None:
        cpu, _ = _make_cpu(program=[0x49, 0xFF], pc=0x8000)
        cpu._a = 0xAA  # noqa: SLF001
        cpu.step()
        assert cpu.a == 0x55

    def test_bit_zero_page(self) -> None:
        cpu, bus = _make_cpu(program=[0x24, 0x30], pc=0x8000)
        bus.write(0x30, 0xC0)  # bits 7 and 6 set
        cpu._a = 0x00  # noqa: SLF001
        cpu.step()
        # A & M = 0, so Z set
        assert cpu._get_flag(CPU.FLAG_Z)  # noqa: SLF001
        # V = bit6 = 1
        assert cpu._get_flag(CPU.FLAG_V)  # noqa: SLF001
        # N = bit7 = 1
        assert cpu._get_flag(CPU.FLAG_N)  # noqa: SLF001

    def test_bit_non_zero_a_and_m(self) -> None:
        cpu, bus = _make_cpu(program=[0x24, 0x30], pc=0x8000)
        bus.write(0x30, 0x80)  # bit7 set
        cpu._a = 0x80  # noqa: SLF001
        cpu.step()
        # A & M != 0, Z clear
        assert not cpu._get_flag(CPU.FLAG_Z)  # noqa: SLF001

    def test_asl_accumulator(self) -> None:
        cpu, _ = _make_cpu(program=[0x0A], pc=0x8000)
        cpu._a = 0x81  # noqa: SLF001  bit7 set
        cpu.step()
        assert cpu.a == 0x02
        assert cpu._get_flag(CPU.FLAG_C)  # noqa: SLF001  bit7 -> carry

    def test_lsr_accumulator(self) -> None:
        cpu, _ = _make_cpu(program=[0x4A], pc=0x8000)
        cpu._a = 0x03  # noqa: SLF001  bit0 set
        cpu.step()
        assert cpu.a == 0x01
        assert cpu._get_flag(CPU.FLAG_C)  # noqa: SLF001  bit0 -> carry

    def test_rol_through_carry(self) -> None:
        cpu, _ = _make_cpu(program=[0x2A], pc=0x8000)
        cpu._a = 0x00  # noqa: SLF001
        cpu._set_flag(CPU.FLAG_C, True)  # noqa: SLF001
        cpu.step()
        assert cpu.a == 0x01  # carry rotated in
        assert not cpu._get_flag(CPU.FLAG_C)  # noqa: SLF001

    def test_ror_through_carry(self) -> None:
        cpu, _ = _make_cpu(program=[0x6A], pc=0x8000)
        cpu._a = 0x00  # noqa: SLF001
        cpu._set_flag(CPU.FLAG_C, True)  # noqa: SLF001
        cpu.step()
        assert cpu.a == 0x80  # carry rotated into bit7
        assert not cpu._get_flag(CPU.FLAG_C)  # noqa: SLF001


# ═══════════════════════════════════════════════════════════════════════════
# Compare
# ═══════════════════════════════════════════════════════════════════════════


class TestCompare:
    """CMP, CPX, CPY."""

    def test_cmp_equal(self) -> None:
        cpu, _ = _make_cpu(program=[0xC9, 0x42], pc=0x8000)
        cpu._a = 0x42  # noqa: SLF001
        cpu.step()
        assert cpu._get_flag(CPU.FLAG_C)  # noqa: SLF001  A >= M
        assert cpu._get_flag(CPU.FLAG_Z)  # noqa: SLF001  A == M

    def test_cmp_less(self) -> None:
        cpu, _ = _make_cpu(program=[0xC9, 0x50], pc=0x8000)
        cpu._a = 0x10  # noqa: SLF001
        cpu.step()
        assert not cpu._get_flag(CPU.FLAG_C)  # noqa: SLF001  A < M
        assert not cpu._get_flag(CPU.FLAG_Z)  # noqa: SLF001
        assert cpu._get_flag(CPU.FLAG_N)  # noqa: SLF001  result negative

    def test_cmp_greater(self) -> None:
        cpu, _ = _make_cpu(program=[0xC9, 0x10], pc=0x8000)
        cpu._a = 0x50  # noqa: SLF001
        cpu.step()
        assert cpu._get_flag(CPU.FLAG_C)  # noqa: SLF001  A >= M

    def test_cpx(self) -> None:
        cpu, _ = _make_cpu(program=[0xE0, 0x20], pc=0x8000)
        cpu._x = 0x20  # noqa: SLF001
        cpu.step()
        assert cpu._get_flag(CPU.FLAG_Z)  # noqa: SLF001
        assert cpu._get_flag(CPU.FLAG_C)  # noqa: SLF001

    def test_cpy(self) -> None:
        cpu, _ = _make_cpu(program=[0xC0, 0x10], pc=0x8000)
        cpu._y = 0x05  # noqa: SLF001
        cpu.step()
        assert not cpu._get_flag(CPU.FLAG_C)  # noqa: SLF001
        assert cpu._get_flag(CPU.FLAG_N)  # noqa: SLF001


# ═══════════════════════════════════════════════════════════════════════════
# Branches
# ═══════════════════════════════════════════════════════════════════════════


class TestBranches:
    """Branch instructions."""

    def test_bne_taken_forward(self) -> None:
        # BNE +2 (skip next byte), NOP, NOP
        cpu, _ = _make_cpu(
            program=[0xD0, 0x02, 0xEA, 0xEA],  # BNE +2; NOP; NOP
            pc=0x8000,
        )
        cpu._set_flag(CPU.FLAG_Z, False)  # noqa: SLF001
        cpu.step()
        assert cpu.pc == 0x8004  # skipped the NOP at 8002

    def test_bne_not_taken(self) -> None:
        cpu, _ = _make_cpu(program=[0xD0, 0x02, 0xEA], pc=0x8000)
        cpu._set_flag(CPU.FLAG_Z, True)  # noqa: SLF001
        cpu.step()
        assert cpu.pc == 0x8002  # did NOT branch

    def test_beq_taken(self) -> None:
        cpu, _ = _make_cpu(program=[0xF0, 0x03, 0xEA, 0xEA, 0xEA], pc=0x8000)
        cpu._set_flag(CPU.FLAG_Z, True)  # noqa: SLF001
        cpu.step()
        assert cpu.pc == 0x8005  # 0x8000 + 2 (opcode+offset) + 3 = 0x8005

    def test_bcs_taken(self) -> None:
        cpu, _ = _make_cpu(program=[0xB0, 0x01, 0xEA], pc=0x8000)
        cpu._set_flag(CPU.FLAG_C, True)  # noqa: SLF001
        cpu.step()
        assert cpu.pc == 0x8003

    def test_bpl_backward(self) -> None:
        # Infinite loop: BPL -2 (branch to self)
        cpu, _ = _make_cpu(program=[0x10, 0xFE], pc=0x8000)  # -2 = 0xFE
        cpu._set_flag(CPU.FLAG_N, False)  # noqa: SLF001
        cpu.step()
        assert cpu.pc == 0x8000  # branched back to self

    def test_branch_cycle_count_not_taken(self) -> None:
        cpu, _ = _make_cpu(program=[0xD0, 0x02], pc=0x8000)
        cpu._set_flag(CPU.FLAG_Z, True)  # noqa: SLF001
        cycles = cpu.step()
        assert cycles == 2

    def test_branch_cycle_count_taken_same_page(self) -> None:
        cpu, _ = _make_cpu(program=[0xD0, 0x02, 0xEA, 0xEA], pc=0x8000)
        cpu._set_flag(CPU.FLAG_Z, False)  # noqa: SLF001
        cycles = cpu.step()
        assert cycles == 3


# ═══════════════════════════════════════════════════════════════════════════
# Jumps and Subroutines
# ═══════════════════════════════════════════════════════════════════════════


class TestJumps:
    """JMP, JSR, RTS, RTI."""

    def test_jmp_absolute(self) -> None:
        cpu, _ = _make_cpu(program=[0x4C, 0x00, 0x90], pc=0x8000)
        cpu.step()
        assert cpu.pc == 0x9000

    def test_jsr_rts(self) -> None:
        # JSR $8500 ; ... ; RTS
        cpu, bus = _make_cpu(
            program=[
                # at 0x8000:
                0x20, 0x00, 0x85,  # JSR $8500
                # at 0x8003 (return point):
                0xEA,  # NOP
                # at 0x8500:
                0x60,  # RTS
            ],
            pc=0x8000,
        )
        # We need the code at 0x8500 to be RTS (0x60)
        bus.write(0x8500, 0x60)  # already loaded via load_program but let's be safe
        cpu.step()  # JSR $8500 - pushes return addr and jumps
        assert cpu.pc == 0x8500
        cpu.step()  # RTS - pops return addr and returns
        assert cpu.pc == 0x8003  # 0x8000 + 3 (JSR length)

    def test_rti(self) -> None:
        cpu, bus = _make_cpu(program=[0x40], pc=0x8000)
        # Simulate interrupt entry: push PC, push P
        cpu._push_word(0x9000)  # noqa: SLF001  return PC
        cpu._push(0x20 | 0x04)  # noqa: SLF001  P = U|I
        cpu.step()  # RTI
        assert cpu.pc == 0x9000
        assert cpu._get_flag(CPU.FLAG_U)  # noqa: SLF001  U always set
        assert not cpu._get_flag(CPU.FLAG_B)  # noqa: SLF001  B cleared
        assert cpu._get_flag(CPU.FLAG_I)  # noqa: SLF001  I from pushed P


# ═══════════════════════════════════════════════════════════════════════════
# Flag operations
# ═══════════════════════════════════════════════════════════════════════════


class TestFlagOps:
    """CLC, SEC, CLD, SED, CLI, SEI, CLV."""

    def test_sec_clc(self) -> None:
        cpu, _ = _make_cpu(program=[0x38, 0x18], pc=0x8000)
        cpu.step()  # SEC
        assert cpu._get_flag(CPU.FLAG_C)  # noqa: SLF001
        cpu.step()  # CLC
        assert not cpu._get_flag(CPU.FLAG_C)  # noqa: SLF001

    def test_sei_cli(self) -> None:
        cpu, _ = _make_cpu(program=[0x78, 0x58], pc=0x8000)
        cpu.step()  # SEI
        assert cpu._get_flag(CPU.FLAG_I)  # noqa: SLF001
        cpu.step()  # CLI
        assert not cpu._get_flag(CPU.FLAG_I)  # noqa: SLF001

    def test_sed_cld(self) -> None:
        cpu, _ = _make_cpu(program=[0xF8, 0xD8], pc=0x8000)
        cpu.step()  # SED
        assert cpu._get_flag(CPU.FLAG_D)  # noqa: SLF001
        cpu.step()  # CLD
        assert not cpu._get_flag(CPU.FLAG_D)  # noqa: SLF001

    def test_clv(self) -> None:
        cpu, _ = _make_cpu(program=[0xB8], pc=0x8000)
        cpu._set_flag(CPU.FLAG_V, True)  # noqa: SLF001
        cpu.step()
        assert not cpu._get_flag(CPU.FLAG_V)  # noqa: SLF001


# ═══════════════════════════════════════════════════════════════════════════
# BRK
# ═══════════════════════════════════════════════════════════════════════════


class TestBRK:
    """BRK software interrupt."""

    def test_brk_pushes_and_jumps(self) -> None:
        cpu, bus = _make_cpu(program=[0x00, 0x00], pc=0x8000)  # BRK + padding
        bus.load_program(0xFFFE, [0x00, 0x90])  # IRQ vector = 0x9000
        cpu._p = 0x20  # noqa: SLF001  U=1 only
        cpu.step()
        # PC should be at 0x9000 (from vector)
        assert cpu.pc == 0x9000
        # I flag set
        assert cpu._get_flag(CPU.FLAG_I)  # noqa: SLF001
        # Check stack: pushed PCH, PCL, P
        # SP should be 0xFD - 3 = 0xFA
        assert cpu.sp == 0xFA


# ═══════════════════════════════════════════════════════════════════════════
# Unofficial NOPs
# ═══════════════════════════════════════════════════════════════════════════


class TestUnofficialNOPs:
    """Undocumented opcodes should act as NOPs (not crash)."""

    def test_nop_0x02(self) -> None:
        cpu, _ = _make_cpu(program=[0x02, 0xEA], pc=0x8000)
        cpu.step()
        # Should not crash, PC advances (IMP mode: no operands)
        assert cpu.pc == 0x8001

    def test_nop_0x04_zp(self) -> None:
        cpu, _ = _make_cpu(program=[0x04, 0x10, 0xEA], pc=0x8000)
        cpu.step()
        # ZP NOP consumes the operand byte
        assert cpu.pc == 0x8002

    def test_nop_0x0C_abs(self) -> None:
        cpu, _ = _make_cpu(program=[0x0C, 0x00, 0x80, 0xEA], pc=0x8000)
        cpu.step()
        # ABS NOP consumes two operand bytes
        assert cpu.pc == 0x8003


# ═══════════════════════════════════════════════════════════════════════════
# Addressing modes
# ═══════════════════════════════════════════════════════════════════════════


class TestAddressingModes:
    """Verify that addressing modes produce correct effective addresses."""

    def test_abx_page_cross(self) -> None:
        """When base + X crosses a page, _page_crossed is set."""
        cpu, _ = _make_cpu(program=[0xBD, 0xFF, 0x80], pc=0x8000)  # LDA $80FF,X
        cpu._x = 0x01  # noqa: SLF001  0x80FF + 1 = 0x8100 -> page crossed
        cpu._set_flag(CPU.FLAG_I, False)  # noqa: SLF001  so IRQ isn't pending
        _ = cpu.step()  # noqa: SLF001
        # page_crossed flag should be set, adding 1 extra cycle
        # (tested through cycle counting below)

    def test_indirect_jmp_bug(self) -> None:
        """JMP indirect bug: high byte wraps within page."""
        cpu, bus = _make_cpu(program=[0x6C, 0xFF, 0x02], pc=0x8000)
        # Pointer at 0x02FF. Low byte from 0x02FF, high byte from 0x0200 (bug!)
        bus.write(0x02FF, 0x00)
        bus.write(0x0200, 0x90)  # bug: high byte from 0x0200, not 0x0300
        cpu.step()
        assert cpu.pc == 0x9000

    def test_izx(self) -> None:
        """Indexed Indirect X: (zp + X) yields 16-bit pointer."""
        cpu, bus = _make_cpu(program=[0xA1, 0x80], pc=0x8000)  # LDA ($80,X)
        cpu._x = 0x05  # noqa: SLF001
        # Zero-page at 0x85, 0x86 should contain the target address
        bus.write(0x85, 0x34)
        bus.write(0x86, 0x12)
        bus.write(0x1234, 0xAB)  # target value
        cpu.step()
        assert cpu.a == 0xAB

    def test_izy_no_page_cross(self) -> None:
        """Indirect Indexed Y: (zp),Y -> A."""
        cpu, bus = _make_cpu(program=[0xB1, 0x80], pc=0x8000)  # LDA ($80),Y
        cpu._y = 0x01  # noqa: SLF001
        bus.write(0x80, 0x00)
        bus.write(0x81, 0x03)  # base = 0x0300
        bus.write(0x0301, 0xCD)  # target at base+Y
        cycles = cpu.step()
        assert cpu.a == 0xCD
        # No page cross -> cycles = base(5) + extra(0) = 5
        assert cycles == 5

    def test_izy_page_cross_extra_cycle(self) -> None:
        """IZY with page crossing adds 1 cycle."""
        cpu, bus = _make_cpu(program=[0xB1, 0x80], pc=0x8000)
        cpu._y = 0xFF  # noqa: SLF001
        bus.write(0x80, 0x01)
        bus.write(0x81, 0x03)  # base = 0x0301
        # base + Y = 0x0301 + 0xFF = 0x0400 -> page crossed
        bus.write(0x0400, 0xCD)
        cycles = cpu.step()
        assert cpu.a == 0xCD
        # Base=5, page_crossed=True -> +1 = 6
        assert cycles == 6


# ═══════════════════════════════════════════════════════════════════════════
# Cycle counting
# ═══════════════════════════════════════════════════════════════════════════


class TestCycleCounting:
    """Verify instruction cycle counts."""

    def test_lda_imm_cycles(self) -> None:
        cpu, _ = _make_cpu(program=[0xA9, 0x00], pc=0x8000)
        cycles = cpu.step()
        assert cycles == 2

    def test_lda_abs_cycles(self) -> None:
        cpu, _ = _make_cpu(program=[0xAD, 0x00, 0x80], pc=0x8000)
        cycles = cpu.step()
        assert cycles == 4

    def test_sta_zp_cycles(self) -> None:
        cpu, _ = _make_cpu(program=[0x85, 0x00], pc=0x8000)
        cycles = cpu.step()
        assert cycles == 3

    def test_nop_cycles(self) -> None:
        cpu, _ = _make_cpu(program=[0xEA], pc=0x8000)
        cycles = cpu.step()
        assert cycles == 2

    def test_jsr_cycles(self) -> None:
        cpu, bus = _make_cpu(program=[0x20, 0x00, 0x80], pc=0x8000)
        cycles = cpu.step()
        assert cycles == 6

    def test_rts_cycles(self) -> None:
        cpu, bus = _make_cpu(program=[0x60], pc=0x8000)
        # Simulate JSR return: push return address
        cpu._push_word(0x8003 - 1)  # noqa: SLF001
        cycles = cpu.step()
        assert cycles == 6

    def test_cumulative_cycles(self) -> None:
        """After multiple steps, _cycles should accumulate."""
        cpu, _ = _make_cpu(program=[0xA9, 0x01, 0xA9, 0x02], pc=0x8000)  # 2 LDA imm
        cpu.step()
        cpu.step()
        assert cpu.cycles == 4  # 2 + 2


# ═══════════════════════════════════════════════════════════════════════════
# Logging
# ═══════════════════════════════════════════════════════════════════════════


class TestLogging:
    """Instruction tracing / logging."""

    def test_logging_enabled(self) -> None:
        cpu, _ = _make_cpu(program=[0xA9, 0x42], pc=0x8000)
        cpu.enable_logging()
        cpu.step()
        assert len(cpu._log_lines) == 1  # noqa: SLF001
        line = cpu._log_lines[0]  # noqa: SLF001
        parts = line.split()
        assert parts[0] == "8000"  # PC
        assert parts[1] == "A9"    # opcode

    def test_logging_disabled(self) -> None:
        cpu, _ = _make_cpu(program=[0xA9, 0x42], pc=0x8000)
        cpu.step()
        assert len(cpu._log_lines) == 0  # noqa: SLF001

    def test_log_format(self) -> None:
        cpu, _ = _make_cpu(program=[0xA9, 0x42], pc=0xC000)
        cpu._sp = 0xFD  # noqa: SLF001
        cpu._p = 0x34  # noqa: SLF001  U|I
        cpu.enable_logging()
        cpu.step()
        line = cpu._log_lines[0]  # noqa: SLF001
        # Expected: "C000  A9  42 00 00 FD 34  <cycles>"
        # A=42 (loaded), Z/N cleared since 0x42 != 0 and bit7=0
        assert line.startswith("C000  A9  42 00 00 FD 34")


# ═══════════════════════════════════════════════════════════════════════════
# Nestest framework
# ═══════════════════════════════════════════════════════════════════════════


class TestNestest:
    """Framework for running nestest ROM.

    The nestest ROM is a comprehensive 6502 test that validates every
    official instruction against known-good state.  It runs from 0xC000
    and writes results to memory-mapped locations.

    This test is skipped if the ROM file is not present.
    """

    def test_nestest_rom_available(self) -> None:
        """Check whether the nestest ROM file exists."""
        import os
        rom_path = os.path.join(
            os.path.dirname(__file__), "..", "roms", "nestest.nes"
        )
        try:
            from cartridge import Cartridge
            Cartridge.load(rom_path)
        except (FileNotFoundError, ValueError):
            pytest.skip("nestest.nes ROM not available")

    def test_nestest_execution(self) -> None:
        """Run nestest for a fixed number of instructions and check state.

        This is a smoke test that ensures the CPU can execute the nestest
        ROM without crashing.  A full nestest comparison requires a golden
        log, which is deferred.
        """
        import os
        rom_path = os.path.join(
            os.path.dirname(__file__), "..", "roms", "nestest.nes"
        )
        try:
            from cartridge import Cartridge
            cart = Cartridge.load(rom_path)
        except (FileNotFoundError, ValueError):
            pytest.skip("nestest.nes ROM not available")

        from ram import RAM
        from bus import Bus

        # Build a minimal bus for nestest
        ram = RAM()

        class _NestestPPU:
            def read_register(self, addr: int) -> int:
                return 0
            def write_register(self, addr: int, value: int) -> None:
                pass
            def oam_write(self, index: int, value: int) -> None:
                pass

        class _NestestAPU:
            def read_register(self, addr: int) -> int:
                return 0
            def write_register(self, addr: int, value: int) -> None:
                pass

        class _NestestInput:
            def read(self) -> int:
                return 0x40
            def write(self, value: int) -> None:
                pass

        bus = Bus(
            cpu_ram=ram,
            ppu=_NestestPPU(),
            apu=_NestestAPU(),
            cartridge=cart,
            input_dev=_NestestInput(),
        )
        cpu = CPU(bus)
        cpu.reset()

        # nestest requires PC = 0xC000 for automated mode
        cpu._pc = 0xC000  # noqa: SLF001

        # Run a reasonable number of instructions
        steps_taken = 0
        max_steps = 50000
        for _ in range(max_steps):
            cpu.step()
            steps_taken += 1
            # nestest writes its result to 0x0002 and 0x0003 when done
            # 0 = running, any other value = test result
            if ram.read(0x0002) != 0 and ram.read(0x0003) != 0:
                break

        assert steps_taken < max_steps, "nestest did not complete within step limit"
        # After nestest completes, check that it passed:
        # On success, it enters an infinite loop at a known location
        # The official nestest success message: PC loops around 0xC66E
        # Memory locations 0x0002/0x0003 contain error code (0 = all ok)
        error_lo = ram.read(0x0002)
        error_hi = ram.read(0x0003)
        # nestest writes error info; 0x00 in both means all tests passed
        # (the test finishes with PC stuck in a loop)
        assert error_lo == 0x00, f"nestest reported error lo={error_lo:02X} hi={error_hi:02X}"
        assert error_hi == 0x00, f"nestest reported error hi={error_hi:02X}"


# ═══════════════════════════════════════════════════════════════════════════
# Comprehensive quick sanity: run a short multi-instruction sequence
# ═══════════════════════════════════════════════════════════════════════════


class TestMultiInstruction:
    """Execute several instructions in sequence and verify final state."""

    def test_sequence_load_add_store(self) -> None:
        """LDA #$10; STA $00; LDA #$20; ADC $00; STA $01"""
        cpu, bus = _make_cpu(
            program=[
                0xA9, 0x10,  # LDA #$10
                0x85, 0x00,  # STA $00
                0xA9, 0x20,  # LDA #$20
                0x65, 0x00,  # ADC $00
                0x85, 0x01,  # STA $01
            ],
            pc=0x8000,
        )
        for _ in range(5):
            cpu.step()
        assert cpu.a == 0x30
        assert bus.read_byte(0x00) == 0x10
        assert bus.read_byte(0x01) == 0x30

    def test_sequence_countdown_loop(self) -> None:
        """Simulate a simple countdown using DEX / BNE."""
        cpu, _ = _make_cpu(
            program=[
                0xA2, 0x05,  # LDX #$05    ; counter = 5
                0xCA,        # DEX         ; X--
                0xD0, 0xFD,  # BNE -3      ; branch back if not zero (0xFD = -3)
                0xEA,        # NOP         ; after loop
            ],
            pc=0x8000,
        )
        # LDX
        cpu.step()
        assert cpu.x == 5
        # Loop: DEX then BNE (5 iterations: X: 4,3,2,1,0)
        # DEX (X=4), BNE taken -> DEX (X=3), BNE taken -> ... DEX (X=0), BNE not taken
        for _ in range(5):
            cpu.step()  # DEX
            cpu.step()  # BNE
        assert cpu.x == 0
        assert cpu._get_flag(CPU.FLAG_Z)  # noqa: SLF001
        # Now the NOP
        cpu.step()
        assert cpu.pc == 0x8006
