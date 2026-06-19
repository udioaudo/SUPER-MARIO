"""6502 CPU emulator for NES (FC).

Implements the full MOS 6502 instruction set used by the NES 2A03 CPU,
including all 13 addressing modes, 56 official instructions (151 opcodes),
interrupt handling, cycle-accurate timing, and optional instruction logging.

Reference: https://www.nesdev.org/wiki/CPU
"""

from __future__ import annotations

from typing import Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from bus import Bus

# ─── Type aliases for dispatch table ───────────────────────────────────────────

#: Signature of an instruction handler: takes effective address, returns extra cycles.
InstrFn = Callable[[int], int]
#: Signature of an addressing mode function: returns effective address.
AddrFn = Callable[[], int]


class CPU:
    """Complete 6502 CPU emulator for the NES.

    The CPU executes one instruction per ``step()`` call, returning the
    number of master clock cycles consumed (including DMA and page-cross
    penalties).  Registers are exposed as read-only properties and can be
    inspected via the public API.
    """

    # ── Flag constants ─────────────────────────────────────────────────────

    FLAG_C: int = 0x01  # Carry
    FLAG_Z: int = 0x02  # Zero
    FLAG_I: int = 0x04  # Interrupt Disable
    FLAG_D: int = 0x08  # Decimal (unused on NES, always 0)
    FLAG_B: int = 0x10  # Break
    FLAG_U: int = 0x20  # Unused (always 1 on NES)
    FLAG_V: int = 0x40  # Overflow
    FLAG_N: int = 0x80  # Negative

    # ── Initialisation ─────────────────────────────────────────────────────

    def __init__(self, bus: Bus) -> None:
        """Create a CPU attached to *bus*.

        The CPU starts in a reset-like state:
        SP = 0xFD, P = 0x24 (U | I), all other registers zero.
        Call ``reset()`` to properly initialise from the reset vector.
        """
        self._bus: Bus = bus

        # Internal register storage
        self._a: int = 0
        self._x: int = 0
        self._y: int = 0
        self._pc: int = 0
        self._sp: int = 0xFD
        self._p: int = 0x24  # U | I  (0x20 | 0x04)

        # Cycle tracking
        self._cycles: int = 0
        self._page_crossed: bool = False
        self._acc_mode: bool = False

        # Logging
        self._logging_enabled: bool = False
        self._log_lines: list[str] = []

        # Built once at construction time
        self._opcodes: dict[int, tuple[InstrFn, AddrFn, int]] = {}
        self._build_opcode_table()

    # ── Public read-only register properties ───────────────────────────────

    @property
    def a(self) -> int:
        """Accumulator (8-bit)."""
        return self._a

    @property
    def x(self) -> int:
        """X index register (8-bit)."""
        return self._x

    @property
    def y(self) -> int:
        """Y index register (8-bit)."""
        return self._y

    @property
    def pc(self) -> int:
        """Program counter (16-bit)."""
        return self._pc

    @property
    def sp(self) -> int:
        """Stack pointer (8-bit, offset into page 0x01)."""
        return self._sp

    @property
    def p(self) -> int:
        """Status register (8-bit: NV_BDIZC)."""
        return self._p

    @property
    def cycles(self) -> int:
        """Total elapsed master-clock cycles since creation / last reset."""
        return self._cycles

    # ── Flag helpers ───────────────────────────────────────────────────────

    def _get_flag(self, flag: int) -> bool:
        """Return ``True`` if *flag* is set in the status register."""
        return (self._p & flag) != 0

    def _set_flag(self, flag: int, value: bool) -> None:
        """Set or clear *flag* in the status register."""
        if value:
            self._p |= flag
        else:
            self._p &= ~flag & 0xFF

    def _update_zn(self, value: int) -> None:
        """Update the Zero and Negative flags based on an 8-bit *value*."""
        self._set_flag(self.FLAG_Z, (value & 0xFF) == 0)
        self._set_flag(self.FLAG_N, (value & 0x80) != 0)

    # ── Memory helpers ─────────────────────────────────────────────────────

    def _consume_dma(self) -> None:
        """Consume any pending OAM DMA cycles from the bus."""
        self._cycles += self._bus.dma_cycles

    def _read(self, addr: int) -> int:
        """Read 1 byte from *addr* via the bus, consuming any DMA cycles."""
        result = self._bus.read(addr)
        self._consume_dma()
        return result

    def _write(self, addr: int, value: int) -> None:
        """Write 1 byte to *addr* via the bus."""
        self._bus.write(addr, value)

    def _read_word(self, addr: int) -> int:
        """Read a little-endian 16-bit word from *addr*."""
        low = self._read(addr)
        high = self._read((addr + 1) & 0xFFFF)
        return low | (high << 8)

    def _read_word_bug(self, addr: int) -> int:
        """Simulate the 6502 indirect-JMP page-boundary hardware bug.

        The high byte is read from ``(addr & 0xFF00) | ((addr + 1) & 0x00FF)``
        instead of ``addr + 1``.
        """
        low = self._read(addr)
        high_addr = (addr & 0xFF00) | ((addr + 1) & 0x00FF)
        high = self._read(high_addr)
        return low | (high << 8)

    # ── Stack ──────────────────────────────────────────────────────────────

    def _push(self, value: int) -> None:
        """Push an 8-bit *value* onto the stack (page 0x01)."""
        self._write(0x0100 | self._sp, value & 0xFF)
        self._sp = (self._sp - 1) & 0xFF

    def _pull(self) -> int:
        """Pull an 8-bit value from the stack."""
        self._sp = (self._sp + 1) & 0xFF
        return self._read(0x0100 | self._sp)

    def _push_word(self, value: int) -> None:
        """Push a 16-bit word (high byte first)."""
        self._push((value >> 8) & 0xFF)
        self._push(value & 0xFF)

    def _pull_word(self) -> int:
        """Pull a 16-bit word (low byte first)."""
        low = self._pull()
        high = self._pull()
        return low | (high << 8)

    # ── Instruction fetch ──────────────────────────────────────────────────

    def _fetch(self) -> int:
        """Read the byte at PC, increment PC, return the byte."""
        data = self._read(self._pc)
        self._pc = (self._pc + 1) & 0xFFFF
        return data

    def _fetch_word(self) -> int:
        """Read a little-endian word at PC, PC += 2."""
        low = self._fetch()
        high = self._fetch()
        return low | (high << 8)

    # ═══════════════════════════════════════════════════════════════════════
    # ADDRESSING MODES
    # ═══════════════════════════════════════════════════════════════════════

    def _addr_imp(self) -> int:
        """Implied — no operand; return 0 (unused)."""
        return 0

    def _addr_acc(self) -> int:
        """Accumulator — operate on A directly."""
        self._acc_mode = True
        return 0

    def _addr_imm(self) -> int:
        """Immediate — operand is the next byte at PC."""
        addr = self._pc
        self._pc = (self._pc + 1) & 0xFFFF
        return addr

    def _addr_zp0(self) -> int:
        """Zero-page — operand is an 8-bit address in page 0."""
        return self._fetch() & 0xFF

    def _addr_zpx(self) -> int:
        """Zero-page X-indexed — (operand + X) & 0xFF."""
        return (self._fetch() + self._x) & 0xFF

    def _addr_zpy(self) -> int:
        """Zero-page Y-indexed — (operand + Y) & 0xFF."""
        return (self._fetch() + self._y) & 0xFF

    def _addr_abs(self) -> int:
        """Absolute — full 16-bit address from next two bytes."""
        return self._fetch_word()

    def _addr_abx(self) -> int:
        """Absolute X-indexed — 16-bit base + X, track page crossing."""
        base = self._fetch_word()
        effective = (base + self._x) & 0xFFFF
        self._page_crossed = (base & 0xFF00) != (effective & 0xFF00)
        return effective

    def _addr_aby(self) -> int:
        """Absolute Y-indexed — 16-bit base + Y, track page crossing."""
        base = self._fetch_word()
        effective = (base + self._y) & 0xFFFF
        self._page_crossed = (base & 0xFF00) != (effective & 0xFF00)
        return effective

    def _addr_ind(self) -> int:
        """Indirect — used by JMP; reads a 16-bit pointer (with JMP bug)."""
        ptr = self._fetch_word()
        return self._read_word_bug(ptr)

    def _addr_izx(self) -> int:
        """Indexed indirect X — (zp + X) yields a 16-bit pointer."""
        zp = (self._fetch() + self._x) & 0xFF
        low = self._read(zp)
        high = self._read((zp + 1) & 0xFF)
        return low | (high << 8)

    def _addr_izy(self) -> int:
        """Indirect indexed Y — zp yields base; base + Y, track page crossing."""
        zp = self._fetch() & 0xFF
        low = self._read(zp)
        high = self._read((zp + 1) & 0xFF)
        base = low | (high << 8)
        effective = (base + self._y) & 0xFFFF
        self._page_crossed = (base & 0xFF00) != (effective & 0xFF00)
        return effective

    def _addr_rel(self) -> int:
        """Relative — signed 8-bit offset from PC (used by branches)."""
        offset = self._fetch()
        # Convert signed 8-bit to 16-bit signed addition
        return (self._pc + (offset ^ 0x80) - 0x80) & 0xFFFF

    # ═══════════════════════════════════════════════════════════════════════
    # INSTRUCTIONS
    # ═══════════════════════════════════════════════════════════════════════
    #
    # Every instruction handler receives the *effective address* computed by
    # the addressing mode and returns *extra* cycles (beyond base + page-cross).
    # Most instructions return 0; branches return 1 (taken) or 2 (taken + page).

    # ── Load / Store ──────────────────────────────────────────────────────

    def _lda(self, addr: int) -> int:
        """LDA — load accumulator from memory."""
        self._a = self._read(addr)
        self._update_zn(self._a)
        return 0

    def _ldx(self, addr: int) -> int:
        """LDX — load X from memory."""
        self._x = self._read(addr)
        self._update_zn(self._x)
        return 0

    def _ldy(self, addr: int) -> int:
        """LDY — load Y from memory."""
        self._y = self._read(addr)
        self._update_zn(self._y)
        return 0

    def _sta(self, addr: int) -> int:
        """STA — store accumulator to memory."""
        self._write(addr, self._a)
        return 0

    def _stx(self, addr: int) -> int:
        """STX — store X to memory."""
        self._write(addr, self._x)
        return 0

    def _sty(self, addr: int) -> int:
        """STY — store Y to memory."""
        self._write(addr, self._y)
        return 0

    # ── Register transfers ────────────────────────────────────────────────

    def _tax(self, addr: int) -> int:
        """TAX — transfer A to X."""
        self._x = self._a
        self._update_zn(self._x)
        return 0

    def _txa(self, addr: int) -> int:
        """TXA — transfer X to A."""
        self._a = self._x
        self._update_zn(self._a)
        return 0

    def _tay(self, addr: int) -> int:
        """TAY — transfer A to Y."""
        self._y = self._a
        self._update_zn(self._y)
        return 0

    def _tya(self, addr: int) -> int:
        """TYA — transfer Y to A."""
        self._a = self._y
        self._update_zn(self._a)
        return 0

    def _tsx(self, addr: int) -> int:
        """TSX — transfer SP to X."""
        self._x = self._sp
        self._update_zn(self._x)
        return 0

    def _txs(self, addr: int) -> int:
        """TXS — transfer X to SP (no flag update)."""
        self._sp = self._x
        return 0

    # ── Stack operations ──────────────────────────────────────────────────

    def _pha(self, addr: int) -> int:
        """PHA — push A onto stack."""
        self._push(self._a)
        return 0

    def _php(self, addr: int) -> int:
        """PHP — push status (with B and U set)."""
        self._push(self._p | self.FLAG_B | self.FLAG_U)
        return 0

    def _pla(self, addr: int) -> int:
        """PLA — pull A from stack."""
        self._a = self._pull()
        self._update_zn(self._a)
        return 0

    def _plp(self, addr: int) -> int:
        """PLP — pull status from stack.  B is cleared, U is always set."""
        self._p = self._pull() & ~self.FLAG_B
        self._set_flag(self.FLAG_U, True)
        return 0

    # ── Arithmetic ────────────────────────────────────────────────────────

    def _adc(self, addr: int) -> int:
        """ADC — add memory to A with carry."""
        val = self._read(addr)
        a = self._a
        carry = 1 if self._get_flag(self.FLAG_C) else 0
        result = a + val + carry

        self._set_flag(self.FLAG_C, result > 0xFF)
        # V: overflow if (A^M has bit7 clear) and (A^result has bit7 set)
        self._set_flag(self.FLAG_V, bool((~(a ^ val) & (a ^ result)) & 0x80))

        self._a = result & 0xFF
        self._update_zn(self._a)
        return 0

    def _sbc(self, addr: int) -> int:
        """SBC — subtract memory from A with carry (borrow)."""
        val = self._read(addr)
        a = self._a
        carry = 1 if self._get_flag(self.FLAG_C) else 0
        # A - M - (1 - C)  ==  A + ~M + C
        result = a + (val ^ 0xFF) + carry

        self._set_flag(self.FLAG_C, result > 0xFF)
        # V: overflow if (A^M has bit7 set) and (A^result has bit7 set)
        self._set_flag(self.FLAG_V, bool(((a ^ val) & (a ^ result)) & 0x80))

        self._a = result & 0xFF
        self._update_zn(self._a)
        return 0

    def _inc(self, addr: int) -> int:
        """INC — increment memory by 1."""
        val = (self._read(addr) + 1) & 0xFF
        self._write(addr, val)
        self._update_zn(val)
        return 0

    def _inx(self, addr: int) -> int:
        """INX — increment X by 1."""
        self._x = (self._x + 1) & 0xFF
        self._update_zn(self._x)
        return 0

    def _iny(self, addr: int) -> int:
        """INY — increment Y by 1."""
        self._y = (self._y + 1) & 0xFF
        self._update_zn(self._y)
        return 0

    def _dec(self, addr: int) -> int:
        """DEC — decrement memory by 1."""
        val = (self._read(addr) - 1) & 0xFF
        self._write(addr, val)
        self._update_zn(val)
        return 0

    def _dex(self, addr: int) -> int:
        """DEX — decrement X by 1."""
        self._x = (self._x - 1) & 0xFF
        self._update_zn(self._x)
        return 0

    def _dey(self, addr: int) -> int:
        """DEY — decrement Y by 1."""
        self._y = (self._y - 1) & 0xFF
        self._update_zn(self._y)
        return 0

    # ── Logic ─────────────────────────────────────────────────────────────

    def _and(self, addr: int) -> int:
        """AND — bitwise AND memory with A."""
        self._a &= self._read(addr)
        self._update_zn(self._a)
        return 0

    def _ora(self, addr: int) -> int:
        """ORA — bitwise OR memory with A."""
        self._a |= self._read(addr)
        self._update_zn(self._a)
        return 0

    def _eor(self, addr: int) -> int:
        """EOR — bitwise XOR memory with A."""
        self._a ^= self._read(addr)
        self._update_zn(self._a)
        return 0

    def _asl(self, addr: int) -> int:
        """ASL — arithmetic shift left (memory or accumulator)."""
        if self._acc_mode:
            val = self._a
            self._set_flag(self.FLAG_C, bool((val >> 7) & 1))
            val = (val << 1) & 0xFF
            self._a = val
        else:
            val = self._read(addr)
            self._set_flag(self.FLAG_C, bool((val >> 7) & 1))
            val = (val << 1) & 0xFF
            self._write(addr, val)
        self._update_zn(val)
        return 0

    def _lsr(self, addr: int) -> int:
        """LSR — logical shift right (memory or accumulator)."""
        if self._acc_mode:
            val = self._a
            self._set_flag(self.FLAG_C, bool(val & 1))
            val = (val >> 1) & 0xFF
            self._a = val
        else:
            val = self._read(addr)
            self._set_flag(self.FLAG_C, bool(val & 1))
            val = (val >> 1) & 0xFF
            self._write(addr, val)
        self._update_zn(val)
        return 0

    def _rol(self, addr: int) -> int:
        """ROL — rotate left through carry (memory or accumulator)."""
        carry_in = 1 if self._get_flag(self.FLAG_C) else 0
        if self._acc_mode:
            val = self._a
            self._set_flag(self.FLAG_C, bool((val >> 7) & 1))
            val = ((val << 1) | carry_in) & 0xFF
            self._a = val
        else:
            val = self._read(addr)
            self._set_flag(self.FLAG_C, bool((val >> 7) & 1))
            val = ((val << 1) | carry_in) & 0xFF
            self._write(addr, val)
        self._update_zn(val)
        return 0

    def _ror(self, addr: int) -> int:
        """ROR — rotate right through carry (memory or accumulator)."""
        carry_in = 1 if self._get_flag(self.FLAG_C) else 0
        if self._acc_mode:
            val = self._a
            self._set_flag(self.FLAG_C, bool(val & 1))
            val = ((val >> 1) | (carry_in << 7)) & 0xFF
            self._a = val
        else:
            val = self._read(addr)
            self._set_flag(self.FLAG_C, bool(val & 1))
            val = ((val >> 1) | (carry_in << 7)) & 0xFF
            self._write(addr, val)
        self._update_zn(val)
        return 0

    def _bit(self, addr: int) -> int:
        """BIT — test bits in memory against A."""
        val = self._read(addr)
        self._set_flag(self.FLAG_Z, (self._a & val) == 0)
        self._set_flag(self.FLAG_V, bool((val >> 6) & 1))
        self._set_flag(self.FLAG_N, bool((val >> 7) & 1))
        return 0

    # ── Compare ───────────────────────────────────────────────────────────

    def _cmp(self, addr: int) -> int:
        """CMP — compare A with memory."""
        val = self._read(addr)
        result = (self._a - val) & 0xFFFF
        self._set_flag(self.FLAG_C, self._a >= val)
        self._update_zn(result)
        return 0

    def _cpx(self, addr: int) -> int:
        """CPX — compare X with memory."""
        val = self._read(addr)
        result = (self._x - val) & 0xFFFF
        self._set_flag(self.FLAG_C, self._x >= val)
        self._update_zn(result)
        return 0

    def _cpy(self, addr: int) -> int:
        """CPY — compare Y with memory."""
        val = self._read(addr)
        result = (self._y - val) & 0xFFFF
        self._set_flag(self.FLAG_C, self._y >= val)
        self._update_zn(result)
        return 0

    # ── Branches ──────────────────────────────────────────────────────────

    def _branch(self, condition: bool, addr: int) -> int:
        """Shared branch logic.  Returns 0 (not taken), 1 (taken), or 2 (cross page)."""
        if not condition:
            return 0
        old_pc = self._pc
        self._pc = addr
        if (old_pc & 0xFF00) != (addr & 0xFF00):
            return 2
        return 1

    def _bcc(self, addr: int) -> int:
        """BCC — branch if carry clear."""
        return self._branch(not self._get_flag(self.FLAG_C), addr)

    def _bcs(self, addr: int) -> int:
        """BCS — branch if carry set."""
        return self._branch(self._get_flag(self.FLAG_C), addr)

    def _beq(self, addr: int) -> int:
        """BEQ — branch if equal (zero set)."""
        return self._branch(self._get_flag(self.FLAG_Z), addr)

    def _bmi(self, addr: int) -> int:
        """BMI — branch if minus (negative set)."""
        return self._branch(self._get_flag(self.FLAG_N), addr)

    def _bne(self, addr: int) -> int:
        """BNE — branch if not equal (zero clear)."""
        return self._branch(not self._get_flag(self.FLAG_Z), addr)

    def _bpl(self, addr: int) -> int:
        """BPL — branch if plus (negative clear)."""
        return self._branch(not self._get_flag(self.FLAG_N), addr)

    def _bvc(self, addr: int) -> int:
        """BVC — branch if overflow clear."""
        return self._branch(not self._get_flag(self.FLAG_V), addr)

    def _bvs(self, addr: int) -> int:
        """BVS — branch if overflow set."""
        return self._branch(self._get_flag(self.FLAG_V), addr)

    # ── Jumps / Subroutines ───────────────────────────────────────────────

    def _jmp(self, addr: int) -> int:
        """JMP — jump to address."""
        self._pc = addr
        return 0

    def _jsr(self, addr: int) -> int:
        """JSR — jump to subroutine (push return address - 1)."""
        self._push_word((self._pc - 1) & 0xFFFF)
        self._pc = addr
        return 0

    def _rts(self, addr: int) -> int:
        """RTS — return from subroutine."""
        self._pc = (self._pull_word() + 1) & 0xFFFF
        return 0

    def _rti(self, addr: int) -> int:
        """RTI — return from interrupt."""
        self._p = self._pull() & ~self.FLAG_B
        self._set_flag(self.FLAG_U, True)
        self._pc = self._pull_word()
        return 0

    # ── Flag operations ───────────────────────────────────────────────────

    def _clc(self, addr: int) -> int:
        """CLC — clear carry flag."""
        self._set_flag(self.FLAG_C, False)
        return 0

    def _sec(self, addr: int) -> int:
        """SEC — set carry flag."""
        self._set_flag(self.FLAG_C, True)
        return 0

    def _cld(self, addr: int) -> int:
        """CLD — clear decimal flag."""
        self._set_flag(self.FLAG_D, False)
        return 0

    def _sed(self, addr: int) -> int:
        """SED — set decimal flag."""
        self._set_flag(self.FLAG_D, True)
        return 0

    def _cli(self, addr: int) -> int:
        """CLI — clear interrupt-disable flag."""
        self._set_flag(self.FLAG_I, False)
        return 0

    def _sei(self, addr: int) -> int:
        """SEI — set interrupt-disable flag."""
        self._set_flag(self.FLAG_I, True)
        return 0

    def _clv(self, addr: int) -> int:
        """CLV — clear overflow flag."""
        self._set_flag(self.FLAG_V, False)
        return 0

    # ── Other ─────────────────────────────────────────────────────────────

    def _brk(self, addr: int) -> int:
        """BRK — software interrupt."""
        self._pc = (self._pc + 1) & 0xFFFF  # skip padding byte
        self._push_word(self._pc)
        self._push(self._p | self.FLAG_B | self.FLAG_U)
        self._set_flag(self.FLAG_I, True)
        self._pc = self._read_word(0xFFFE)
        return 0

    def _nop(self, addr: int) -> int:
        """NOP — no operation (official and unofficial)."""
        return 0

    # ═══════════════════════════════════════════════════════════════════════
    # DISPATCH TABLE
    # ═══════════════════════════════════════════════════════════════════════

    def _build_opcode_table(self) -> None:
        """Populate ``self._opcodes`` with all 256 opcode entries."""
        # Bind methods locally for brevity
        # --- instructions ---
        _adc = self._adc
        _and = self._and
        _asl = self._asl
        _bcc = self._bcc
        _bcs = self._bcs
        _beq = self._beq
        _bit = self._bit
        _bmi = self._bmi
        _bne = self._bne
        _bpl = self._bpl
        _brk = self._brk
        _bvc = self._bvc
        _bvs = self._bvs
        _clc = self._clc
        _cld = self._cld
        _cli = self._cli
        _clv = self._clv
        _cmp = self._cmp
        _cpx = self._cpx
        _cpy = self._cpy
        _dec = self._dec
        _dex = self._dex
        _dey = self._dey
        _eor = self._eor
        _inc = self._inc
        _inx = self._inx
        _iny = self._iny
        _jmp = self._jmp
        _jsr = self._jsr
        _lda = self._lda
        _ldx = self._ldx
        _ldy = self._ldy
        _lsr = self._lsr
        _nop = self._nop
        _ora = self._ora
        _pha = self._pha
        _php = self._php
        _pla = self._pla
        _plp = self._plp
        _rol = self._rol
        _ror = self._ror
        _rti = self._rti
        _rts = self._rts
        _sbc = self._sbc
        _sec = self._sec
        _sed = self._sed
        _sei = self._sei
        _sta = self._sta
        _stx = self._stx
        _sty = self._sty
        _tax = self._tax
        _tay = self._tay
        _tsx = self._tsx
        _txa = self._txa
        _txs = self._txs
        _tya = self._tya

        # --- addressing modes ---
        IMP = self._addr_imp
        ACC = self._addr_acc
        IMM = self._addr_imm
        ZP0 = self._addr_zp0
        ZPX = self._addr_zpx
        ZPY = self._addr_zpy
        ABS = self._addr_abs
        ABX = self._addr_abx
        ABY = self._addr_aby
        IND = self._addr_ind
        IZX = self._addr_izx
        IZY = self._addr_izy
        REL = self._addr_rel

        # Tables in groups for readability -----------------------------------
        ops: list[tuple[int, InstrFn, AddrFn, int]] = [
            # 0x00–0x0F
            (0x00, _brk, IMP, 7),
            (0x01, _ora, IZX, 6),
            (0x02, _nop, IMP, 2),
            (0x03, _nop, IMP, 2),
            (0x04, _nop, ZP0, 3),
            (0x05, _ora, ZP0, 3),
            (0x06, _asl, ZP0, 5),
            (0x07, _nop, IMP, 2),
            (0x08, _php, IMP, 3),
            (0x09, _ora, IMM, 2),
            (0x0A, _asl, ACC, 2),
            (0x0B, _nop, IMP, 2),
            (0x0C, _nop, ABS, 4),
            (0x0D, _ora, ABS, 4),
            (0x0E, _asl, ABS, 6),
            (0x0F, _nop, IMP, 2),
            # 0x10–0x1F
            (0x10, _bpl, REL, 2),
            (0x11, _ora, IZY, 5),
            (0x12, _nop, IMP, 2),
            (0x13, _nop, IMP, 2),
            (0x14, _nop, ZP0, 3),
            (0x15, _ora, ZPX, 4),
            (0x16, _asl, ZPX, 6),
            (0x17, _nop, IMP, 2),
            (0x18, _clc, IMP, 2),
            (0x19, _ora, ABY, 4),
            (0x1A, _nop, IMP, 2),
            (0x1B, _nop, IMP, 2),
            (0x1C, _nop, ABX, 4),
            (0x1D, _ora, ABX, 4),
            (0x1E, _asl, ABX, 7),
            (0x1F, _nop, IMP, 2),
            # 0x20–0x2F
            (0x20, _jsr, ABS, 6),
            (0x21, _and, IZX, 6),
            (0x22, _nop, IMP, 2),
            (0x23, _nop, IMP, 2),
            (0x24, _bit, ZP0, 3),
            (0x25, _and, ZP0, 3),
            (0x26, _rol, ZP0, 5),
            (0x27, _nop, IMP, 2),
            (0x28, _plp, IMP, 4),
            (0x29, _and, IMM, 2),
            (0x2A, _rol, ACC, 2),
            (0x2B, _nop, IMP, 2),
            (0x2C, _bit, ABS, 4),
            (0x2D, _and, ABS, 4),
            (0x2E, _rol, ABS, 6),
            (0x2F, _nop, IMP, 2),
            # 0x30–0x3F
            (0x30, _bmi, REL, 2),
            (0x31, _and, IZY, 5),
            (0x32, _nop, IMP, 2),
            (0x33, _nop, IMP, 2),
            (0x34, _nop, ZP0, 3),
            (0x35, _and, ZPX, 4),
            (0x36, _rol, ZPX, 6),
            (0x37, _nop, IMP, 2),
            (0x38, _sec, IMP, 2),
            (0x39, _and, ABY, 4),
            (0x3A, _nop, IMP, 2),
            (0x3B, _nop, IMP, 2),
            (0x3C, _nop, ABX, 4),
            (0x3D, _and, ABX, 4),
            (0x3E, _rol, ABX, 7),
            (0x3F, _nop, IMP, 2),
            # 0x40–0x4F
            (0x40, _rti, IMP, 6),
            (0x41, _eor, IZX, 6),
            (0x42, _nop, IMP, 2),
            (0x43, _nop, IMP, 2),
            (0x44, _nop, ZP0, 3),
            (0x45, _eor, ZP0, 3),
            (0x46, _lsr, ZP0, 5),
            (0x47, _nop, IMP, 2),
            (0x48, _pha, IMP, 3),
            (0x49, _eor, IMM, 2),
            (0x4A, _lsr, ACC, 2),
            (0x4B, _nop, IMP, 2),
            (0x4C, _jmp, ABS, 3),
            (0x4D, _eor, ABS, 4),
            (0x4E, _lsr, ABS, 6),
            (0x4F, _nop, IMP, 2),
            # 0x50–0x5F
            (0x50, _bvc, REL, 2),
            (0x51, _eor, IZY, 5),
            (0x52, _nop, IMP, 2),
            (0x53, _nop, IMP, 2),
            (0x54, _nop, ZP0, 3),
            (0x55, _eor, ZPX, 4),
            (0x56, _lsr, ZPX, 6),
            (0x57, _nop, IMP, 2),
            (0x58, _cli, IMP, 2),
            (0x59, _eor, ABY, 4),
            (0x5A, _nop, IMP, 2),
            (0x5B, _nop, IMP, 2),
            (0x5C, _nop, ABX, 4),
            (0x5D, _eor, ABX, 4),
            (0x5E, _lsr, ABX, 7),
            (0x5F, _nop, IMP, 2),
            # 0x60–0x6F
            (0x60, _rts, IMP, 6),
            (0x61, _adc, IZX, 6),
            (0x62, _nop, IMP, 2),
            (0x63, _nop, IMP, 2),
            (0x64, _nop, ZP0, 3),
            (0x65, _adc, ZP0, 3),
            (0x66, _ror, ZP0, 5),
            (0x67, _nop, IMP, 2),
            (0x68, _pla, IMP, 4),
            (0x69, _adc, IMM, 2),
            (0x6A, _ror, ACC, 2),
            (0x6B, _nop, IMP, 2),
            (0x6C, _jmp, IND, 5),
            (0x6D, _adc, ABS, 4),
            (0x6E, _ror, ABS, 6),
            (0x6F, _nop, IMP, 2),
            # 0x70–0x7F
            (0x70, _bvs, REL, 2),
            (0x71, _adc, IZY, 5),
            (0x72, _nop, IMP, 2),
            (0x73, _nop, IMP, 2),
            (0x74, _nop, ZP0, 3),
            (0x75, _adc, ZPX, 4),
            (0x76, _ror, ZPX, 6),
            (0x77, _nop, IMP, 2),
            (0x78, _sei, IMP, 2),
            (0x79, _adc, ABY, 4),
            (0x7A, _nop, IMP, 2),
            (0x7B, _nop, IMP, 2),
            (0x7C, _nop, ABX, 4),
            (0x7D, _adc, ABX, 4),
            (0x7E, _ror, ABX, 7),
            (0x7F, _nop, IMP, 2),
            # 0x80–0x8F
            (0x80, _nop, IMM, 2),
            (0x81, _sta, IZX, 6),
            (0x82, _nop, IMM, 2),
            (0x83, _nop, IMP, 2),
            (0x84, _sty, ZP0, 3),
            (0x85, _sta, ZP0, 3),
            (0x86, _stx, ZP0, 3),
            (0x87, _nop, IMP, 2),
            (0x88, _dey, IMP, 2),
            (0x89, _nop, IMM, 2),
            (0x8A, _txa, IMP, 2),
            (0x8B, _nop, IMP, 2),
            (0x8C, _sty, ABS, 4),
            (0x8D, _sta, ABS, 4),
            (0x8E, _stx, ABS, 4),
            (0x8F, _nop, IMP, 2),
            # 0x90–0x9F
            (0x90, _bcc, REL, 2),
            (0x91, _sta, IZY, 6),
            (0x92, _nop, IMP, 2),
            (0x93, _nop, IMP, 2),
            (0x94, _sty, ZPX, 4),
            (0x95, _sta, ZPX, 4),
            (0x96, _stx, ZPY, 4),
            (0x97, _nop, IMP, 2),
            (0x98, _tya, IMP, 2),
            (0x99, _sta, ABY, 5),
            (0x9A, _txs, IMP, 2),
            (0x9B, _nop, IMP, 2),
            (0x9C, _nop, IMP, 2),
            (0x9D, _sta, ABX, 5),
            (0x9E, _nop, IMP, 2),
            (0x9F, _nop, IMP, 2),
            # 0xA0–0xAF
            (0xA0, _ldy, IMM, 2),
            (0xA1, _lda, IZX, 6),
            (0xA2, _ldx, IMM, 2),
            (0xA3, _nop, IMP, 2),
            (0xA4, _ldy, ZP0, 3),
            (0xA5, _lda, ZP0, 3),
            (0xA6, _ldx, ZP0, 3),
            (0xA7, _nop, IMP, 2),
            (0xA8, _tay, IMP, 2),
            (0xA9, _lda, IMM, 2),
            (0xAA, _tax, IMP, 2),
            (0xAB, _nop, IMP, 2),
            (0xAC, _ldy, ABS, 4),
            (0xAD, _lda, ABS, 4),
            (0xAE, _ldx, ABS, 4),
            (0xAF, _nop, IMP, 2),
            # 0xB0–0xBF
            (0xB0, _bcs, REL, 2),
            (0xB1, _lda, IZY, 5),
            (0xB2, _nop, IMP, 2),
            (0xB3, _nop, IMP, 2),
            (0xB4, _ldy, ZPX, 4),
            (0xB5, _lda, ZPX, 4),
            (0xB6, _ldx, ZPY, 4),
            (0xB7, _nop, IMP, 2),
            (0xB8, _clv, IMP, 2),
            (0xB9, _lda, ABY, 4),
            (0xBA, _tsx, IMP, 2),
            (0xBB, _nop, IMP, 2),
            (0xBC, _ldy, ABX, 4),
            (0xBD, _lda, ABX, 4),
            (0xBE, _ldx, ABY, 4),
            (0xBF, _nop, IMP, 2),
            # 0xC0–0xCF
            (0xC0, _cpy, IMM, 2),
            (0xC1, _cmp, IZX, 6),
            (0xC2, _nop, IMM, 2),
            (0xC3, _nop, IMP, 2),
            (0xC4, _cpy, ZP0, 3),
            (0xC5, _cmp, ZP0, 3),
            (0xC6, _dec, ZP0, 5),
            (0xC7, _nop, IMP, 2),
            (0xC8, _iny, IMP, 2),
            (0xC9, _cmp, IMM, 2),
            (0xCA, _dex, IMP, 2),
            (0xCB, _nop, IMP, 2),
            (0xCC, _cpy, ABS, 4),
            (0xCD, _cmp, ABS, 4),
            (0xCE, _dec, ABS, 6),
            (0xCF, _nop, IMP, 2),
            # 0xD0–0xDF
            (0xD0, _bne, REL, 2),
            (0xD1, _cmp, IZY, 5),
            (0xD2, _nop, IMP, 2),
            (0xD3, _nop, IMP, 2),
            (0xD4, _nop, ZP0, 3),
            (0xD5, _cmp, ZPX, 4),
            (0xD6, _dec, ZPX, 6),
            (0xD7, _nop, IMP, 2),
            (0xD8, _cld, IMP, 2),
            (0xD9, _cmp, ABY, 4),
            (0xDA, _nop, IMP, 2),
            (0xDB, _nop, IMP, 2),
            (0xDC, _nop, ABX, 4),
            (0xDD, _cmp, ABX, 4),
            (0xDE, _dec, ABX, 7),
            (0xDF, _nop, IMP, 2),
            # 0xE0–0xEF
            (0xE0, _cpx, IMM, 2),
            (0xE1, _sbc, IZX, 6),
            (0xE2, _nop, IMM, 2),
            (0xE3, _nop, IMP, 2),
            (0xE4, _cpx, ZP0, 3),
            (0xE5, _sbc, ZP0, 3),
            (0xE6, _inc, ZP0, 5),
            (0xE7, _nop, IMP, 2),
            (0xE8, _inx, IMP, 2),
            (0xE9, _sbc, IMM, 2),
            (0xEA, _nop, IMP, 2),
            (0xEB, _nop, IMP, 2),
            (0xEC, _cpx, ABS, 4),
            (0xED, _sbc, ABS, 4),
            (0xEE, _inc, ABS, 6),
            (0xEF, _nop, IMP, 2),
            # 0xF0–0xFF
            (0xF0, _beq, REL, 2),
            (0xF1, _sbc, IZY, 5),
            (0xF2, _nop, IMP, 2),
            (0xF3, _nop, IMP, 2),
            (0xF4, _nop, ZP0, 3),
            (0xF5, _sbc, ZPX, 4),
            (0xF6, _inc, ZPX, 6),
            (0xF7, _nop, IMP, 2),
            (0xF8, _sed, IMP, 2),
            (0xF9, _sbc, ABY, 4),
            (0xFA, _nop, IMP, 2),
            (0xFB, _nop, IMP, 2),
            (0xFC, _nop, ABX, 4),
            (0xFD, _sbc, ABX, 4),
            (0xFE, _inc, ABX, 7),
            (0xFF, _nop, IMP, 2),
        ]

        for opc, instr, addr, cycles in ops:
            self._opcodes[opc] = (instr, addr, cycles)

    # ═══════════════════════════════════════════════════════════════════════
    # INTERRUPTS
    # ═══════════════════════════════════════════════════════════════════════

    def reset(self) -> int:
        """Assert the reset signal.

        Sets SP to 0xFD, P to 0x34 (I=1, U=1), loads PC from 0xFFFC,
        and returns 7 cycles.
        """
        self._sp = 0xFD
        self._p = 0x34
        self._pc = self._read_word(0xFFFC)
        self._cycles += 7
        return 7

    def nmi(self) -> int:
        """Non-maskable interrupt.

        Pushes PC, pushes P (with B=0), sets I=1, loads PC from 0xFFFA,
        and returns 7 cycles.
        """
        self._push_word(self._pc)
        self._push(self._p & ~self.FLAG_B)
        self._set_flag(self.FLAG_I, True)
        self._pc = self._read_word(0xFFFA)
        self._cycles += 7
        return 7

    def irq(self) -> int:
        """Maskable interrupt request.

        If I=1 the interrupt is ignored and returns 0 cycles.
        Otherwise pushes PC, pushes P (B=0), sets I=1, loads PC from 0xFFFE,
        and returns 7 cycles.
        """
        if self._get_flag(self.FLAG_I):
            return 0
        self._push_word(self._pc)
        self._push(self._p & ~self.FLAG_B)
        self._set_flag(self.FLAG_I, True)
        self._pc = self._read_word(0xFFFE)
        self._cycles += 7
        return 7

    # ═══════════════════════════════════════════════════════════════════════
    # STEP
    # ═══════════════════════════════════════════════════════════════════════

    def step(self) -> int:
        """Execute a single instruction and return the number of cycles consumed.

        Cycle counting includes:
        * base cycles from the opcode table
        * +1 if the addressing mode crossed a page boundary
        * +extra cycles returned by the instruction handler (branches)
        * +DMA cycles consumed before, during, and after the instruction
        """
        cycles_before = self._cycles

        # 1. Pre-existing DMA cycles from previous steps
        self._consume_dma()

        # 2. Fetch opcode
        pc_before = self._pc
        opcode = self._fetch()

        # 3. Look up dispatch table
        instr_fn, addr_fn, base_cycles = self._opcodes[opcode]

        # 4–5. Determine effective address
        self._page_crossed = False
        self._acc_mode = False
        addr = addr_fn()

        # 6. Execute the instruction
        instr_extra = instr_fn(addr)

        # 7. Compute base cycle count
        total = base_cycles + (1 if self._page_crossed else 0) + instr_extra

        # 8. DMA cycles triggered during the instruction
        self._consume_dma()

        # 9. Log the instruction if enabled
        if self._logging_enabled:
            self._log_instruction(pc_before, opcode)

        # 10. Update total cycle counter
        self._cycles += total

        return self._cycles - cycles_before

    # ═══════════════════════════════════════════════════════════════════════
    # LOGGING
    # ═══════════════════════════════════════════════════════════════════════

    def enable_logging(self) -> None:
        """Enable per-instruction logging (appends to ``_log_lines``)."""
        self._logging_enabled = True

    def disable_logging(self) -> None:
        """Disable per-instruction logging."""
        self._logging_enabled = False

    def _log_instruction(self, pc: int, opcode: int) -> None:
        """Append a formatted instruction-trace line to the log."""
        line = (
            f"{pc:04X}  {opcode:02X}  "
            f"{self._a:02X} {self._x:02X} {self._y:02X} "
            f"{self._sp:02X} {self._p:02X}  "
            f"{self._cycles}"
        )
        self._log_lines.append(line)
