# CPU 模块 — 任务列表

> 模块文件：`cpu.py`
> 依赖：Bus（读/写内存）
> 可独立测试：✅ 是（nestest ROM）

---

## 任务清单

### Phase 1 — CPU 骨架与基础设施

- [ ] **1.1 创建 CPU 类骨架 + 寄存器**
  - 文件：`cpu.py`
  - 定义寄存器属性：A, X, Y, PC, SP, P（均为 `@property` 只读）
  - 内部状态变量：`_a, _x, _y, _pc, _sp, _p`
  - 状态标志位常量：`FLAG_C=0x01, FLAG_Z=0x02, FLAG_I=0x04, FLAG_D=0x08, FLAG_B=0x10, FLAG_U=0x20, FLAG_V=0x40, FLAG_N=0x80`
  - `__init__(bus)`：接受 Bus 实例
  - 预计代码量：~40 行

- [ ] **1.2 实现标志位辅助方法**
  - `_get_flag(flag)` → 返回 bool
  - `_set_flag(flag, value: bool)`
  - `_update_zn(val)` → 根据 val 设置 Z 和 N 标志
  - 预计代码量：~15 行

- [ ] **1.3 实现内存读写辅助方法**
  - `_read(addr)` → `self.bus.read(addr)`
  - `_write(addr, value)` → `self.bus.write(addr, value & 0xFF)`
  - `_read_word(addr)` → `self._read(addr) | (self._read(addr + 1) << 8)` （小端序）
  - `_read_word_bug(addr)` → 模拟 6502 的跨页 bug（低字节 + 0xFF 不回卷到同页高位）
  - `_push(val)` → `self._write(0x0100 + self._sp, val); self._sp = (self._sp - 1) & 0xFF`
  - `_pull()` → `self._sp = (self._sp + 1) & 0xFF; return self._read(0x0100 + self._sp)`
  - `_push_word(val)` → push 高字节再 push 低字节
  - `_pull_word()` → pull 低字节再 pull 高字节
  - 预计代码量：~35 行

- [ ] **1.4 实现 PC 递增辅助方法**
  - `_fetch()` → 读 `self._pc` 处的 1 字节，PC += 1
  - `_fetch_word()` → 读 `self._pc` 处的 2 字节（小端），PC += 2
  - 预计代码量：~10 行

### Phase 2 — 寻址方式

- [ ] **2.1 实现非索引寻址方式**
  - `_addr_imp()` → 返回 0（Implied：无地址，操作数隐含在寄存器中）
  - `_addr_acc()` → 返回 0（Accumulator：操作 A 寄存器）
  - `_addr_imm()` → 返回 `self._pc`，且 `self._pc += 1`
  - `_addr_zp0()` → `self._fetch()` 返回的零页地址
  - `_addr_abs()` → `self._fetch_word()` 返回的绝对地址
  - `_addr_rel()` → 返回有符号 8 位偏移（用于分支），需要特殊处理
  - 预计代码量：~30 行

- [ ] **2.2 实现索引寻址方式**
  - `_addr_zpx()` → `(self._fetch() + self._x) & 0xFF`（零页回卷）
  - `_addr_zpy()` → `(self._fetch() + self._y) & 0xFF`（零页回卷）
  - `_addr_abx()` → `self._fetch_word() + self._x`，记录是否跨页
  - `_addr_aby()` → `self._fetch_word() + self._y`，记录是否跨页
  - 预计代码量：~25 行

- [ ] **2.3 实现间接寻址方式**
  - `_addr_ind()` → 读 `_fetch_word()` 处的 2 字节指针（JMP 间接，含 6502 的指针不回卷 bug）
  - `_addr_izx()` → `(self._fetch() + self._x) & 0xFF` 指向的零页 2 字节指针
  - `_addr_izy()` → `self._fetch()` 指向的零页 2 字节指针 + Y，记录是否跨页
  - 预计代码量：~25 行

- [ ] **2.4 跨页周期惩罚跟踪**
  - 在 ABX/ABY/IZY 寻址中记录 `_page_crossed` 标志
  - 分支指令跨页时也记录
  - 供指令实现中追加 1 个额外周期
  - 预计代码量：~5 行

### Phase 3 — 指令实现（按类别分批）

- [ ] **3.1 加载/存储指令** — LDA, LDX, LDY, STA, STX, STY (共 6 条 × 多种寻址)
  - LDA (IMM, ZP0, ZPX, ABS, ABX, ABY, IZX, IZY) — 9 个操作码
  - LDX (IMM, ZP0, ZPY, ABS, ABY) — 5 个操作码
  - LDY (IMM, ZP0, ZPX, ABS, ABX) — 5 个操作码
  - STA (ZP0, ZPX, ABS, ABX, ABY, IZX, IZY) — 7 个操作码
  - STX (ZP0, ZPY, ABS) — 3 个操作码
  - STY (ZP0, ZPX, ABS) — 3 个操作码
  - **总计 32 个操作码**
  - 预计代码量：~80 行

- [ ] **3.2 寄存器传输指令** — TAX, TXA, TAY, TYA, TSX, TXS (共 6 条, IMP)
  - **总计 6 个操作码**
  - 预计代码量：~25 行

- [ ] **3.3 栈操作指令** — PHA, PHP, PLA, PLP (共 4 条, IMP)
  - **总计 4 个操作码**
  - 预计代码量：~25 行

- [ ] **3.4 算术指令** — ADC, SBC, INC, INX, INY, DEC, DEX, DEY (共 8 条)
  - ADC (IMM, ZP0, ZPX, ABS, ABX, ABY, IZX, IZY) — 8 个操作码
  - SBC (IMM, ZP0, ZPX, ABS, ABX, ABY, IZX, IZY) — 8 个操作码
  - INC (ZP0, ZPX, ABS, ABX) — 4 个操作码
  - INX (IMP) — 1 个操作码
  - INY (IMP) — 1 个操作码
  - DEC (ZP0, ZPX, ABS, ABX) — 4 个操作码
  - DEX (IMP) — 1 个操作码
  - DEY (IMP) — 1 个操作码
  - **总计 28 个操作码**
  - 预计代码量：~100 行

- [ ] **3.5 逻辑指令** — AND, ORA, EOR, ASL, LSR, ROL, ROR, BIT (共 8 条)
  - AND (IMM, ZP0, ZPX, ABS, ABX, ABY, IZX, IZY) — 8 个操作码
  - ORA (IMM, ZP0, ZPX, ABS, ABX, ABY, IZX, IZY) — 8 个操作码
  - EOR (IMM, ZP0, ZPX, ABS, ABX, ABY, IZX, IZY) — 8 个操作码
  - ASL (ACC, ZP0, ZPX, ABS, ABX) — 5 个操作码
  - LSR (ACC, ZP0, ZPX, ABS, ABX) — 5 个操作码
  - ROL (ACC, ZP0, ZPX, ABS, ABX) — 5 个操作码
  - ROR (ACC, ZP0, ZPX, ABS, ABX) — 5 个操作码
  - BIT (ZP0, ABS) — 2 个操作码
  - **总计 46 个操作码**
  - 预计代码量：~120 行

- [ ] **3.6 比较指令** — CMP, CPX, CPY (共 3 条)
  - CMP (IMM, ZP0, ZPX, ABS, ABX, ABY, IZX, IZY) — 8 个操作码
  - CPX (IMM, ZP0, ABS) — 3 个操作码
  - CPY (IMM, ZP0, ABS) — 3 个操作码
  - **总计 14 个操作码**
  - 预计代码量：~40 行

- [ ] **3.7 分支指令** — BCC, BCS, BEQ, BMI, BNE, BPL, BVC, BVS (共 8 条, REL)
  - **总计 8 个操作码**
  - 预计代码量：~20 行

- [ ] **3.8 跳转/子程序指令** — JMP, JSR, RTS, RTI (共 4 条)
  - JMP (ABS, IND) — 2 个操作码
  - JSR (ABS) — 1 个操作码
  - RTS (IMP) — 1 个操作码
  - RTI (IMP) — 1 个操作码
  - **总计 5 个操作码**
  - 预计代码量：~35 行

- [ ] **3.9 标志操作指令** — CLC, SEC, CLD, SED, CLI, SEI, CLV (共 7 条, IMP)
  - **总计 7 个操作码**
  - 预计代码量：~20 行

- [ ] **3.10 其他指令** — BRK, NOP (共 2 条)
  - BRK (IMP) — 1 个操作码
  - NOP (IMP) — 1 个操作码
  - **总计 2 个操作码**
  - 预计代码量：~20 行

### Phase 4 — 中断与主循环

- [ ] **4.1 实现 `reset()`**
  - SP = 0xFD
  - P = 0x34（I=1, unused=1）
  - PC = `_read_word(0xFFFC)`（复位向量）
  - 返回消耗周期数：7
  - 预计代码量：~10 行

- [ ] **4.2 实现 `nmi()`**
  - 压栈 PC 高字节 → PC 低字节
  - 压栈 P（B 标志 = 0，bit4 清 0 后压入）
  - I = 1
  - PC = `_read_word(0xFFFA)`（NMI 向量）
  - 返回消耗周期数：7
  - 预计代码量：~15 行

- [ ] **4.3 实现 `irq()`**
  - 若 I = 1，不处理（返回 0 周期）
  - 压栈 PC 高字节 → PC 低字节
  - 压栈 P（B = 0）
  - I = 1
  - PC = `_read_word(0xFFFE)`（IRQ 向量）
  - 返回消耗周期数：7
  - 预计代码量：~15 行

- [ ] **4.4 构建操作码调度表**
  - 151 个条目的 dict/list：`opcode → (指令函数, 寻址函数, 基础周期数)`
  - 或使用大号 `match/case`（Python 3.10+）
  - 未实现的操作码 → 抛出 `NotImplementedError`（或当作 NOP）
  - 预计代码量：~160 行（151 个条目）

- [ ] **4.5 实现 `step()`**
  - 取指：`opcode = self._fetch()`
  - 查表获取寻址函数、指令函数、基础周期数
  - 调用寻址函数获取操作数地址
  - 调用指令函数执行操作
  - 返回实际周期数 = 基础周期 + 跨页惩罚
  - 预计代码量：~20 行

### Phase 5 — 验证

- [ ] **5.1 编写 nestest 测试框架**
  - 文件：`tests/test_cpu.py`
  - 加载 nestest ROM（仅 PRG ROM，映射到 0xC000–0xFFFF）
  - 构造最小 Bus（仅含 RAM 和简易 Cartridge）
  - 设置 PC = 0xC000（nestest 入口）
  - 自动运行直到遇到特定停止条件
  - 预计代码量：~50 行

- [ ] **5.2 与 nestest 参考日志对比**
  - nestest 参考日志：每行包含 PC, A, X, Y, SP, P, 周期数
  - 测试对比：每执行一条指令后的寄存器状态
  - 任何不匹配 → 测试失败并报告差异
  - 跑通全部 151 个官方操作码
  - 预计代码量：~40 行

- [ ] **5.3 跑通全部单元测试**
  - `python -m pytest tests/test_cpu.py -v`

---

## 验收标准
- [x] （未开始）nestest 全部 151 个官方操作码通过，所有寄存器与周期数匹配
