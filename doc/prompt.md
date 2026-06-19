# SUPER MARIO FC 模拟器 —— Vibe Coding Prompt

> **目标**：用 Python 开发一个能运行《超级马里奥兄弟》1代（1985，FC/NES）的模拟器。
> **自动化级别**：全自动。主 Agent 追踪整体进度，逐模块生成子 Agent 实现，无人参与。
> **生成日期**：2026-06-19

---

## 0. 你的角色与工作方式

你是一个 **主 Agent（Orchestrator）**，负责：

1. **逐模块推进**：严格按照 Phase 1 → Phase 6 的顺序，**一个模块完全完成并通过所有质量门禁后**，才进入下一个模块。
2. **派生子 Agent**：每个模块由一个独立子 Agent 实现（含代码 + 测试）。
3. **验证门禁**：每个模块完成后，**必须**通过 pytest + mypy + ruff 三个检测，全部通过才算完成。
4. **进度追踪**：每完成一个模块，更新 [doc/tasks/progress.md](doc/tasks/progress.md) 中的状态。

**工作循环（对每个模块重复）**：

```
1. 阅读本 Prompt + 对应 doc/tasks/<module>.md 任务文件
2. 派生子 Agent，给定完整的模块规格 + 任务清单
3. 子 Agent 编写模块代码 + 单元测试
4. 运行 pytest，检查是否全部通过
5. 运行 mypy，检查类型是否正确
6. 运行 ruff，检查代码规范
7. 全部通过 → 更新 progress.md → 进入下一个模块
8. 未通过 → 子 Agent 修复 → 重新验证 → 直到全部通过
```

---

## 1. 项目目标

开发一个 Python + Pygame 的 FC 模拟器，**仅需运行《超级马里奥兄弟》1代**。

### 1.1 核心验收标准

- [ ] 能加载并运行《超级马里奥兄弟》1代 `.nes` ROM
- [ ] 标题画面、关卡画面正确显示，无明显花屏
- [ ] 马里奥可正常移动、跳跃、顶砖块、吃蘑菇、踩敌人、进水管、过关
- [ ] 背景音乐与音效正常播放
- [ ] 运行帧率接近 60 FPS，操作无明显延迟
- [ ] 基础调试工具可用

### 1.2 明确不做的事

- ❌ 其他映射器（MMC1、MMC3 等）
- ❌ 游戏手柄（仅键盘）
- ❌ 2P 双人
- ❌ 即时存档 / 读档
- ❌ 全屏模式、可变缩放、滤镜
- ❌ 图形界面菜单 / ROM 选择器
- ❌ 跨平台打包发布

---

## 2. 技术规格（已确认的决策）

| 维度 | 决策 |
|------|------|
| 兼容范围 | 仅《超级马里奥兄弟》1代（Mapper 0 / NROM） |
| 图形库 | Pygame |
| 性能目标 | 接近原机 60 FPS |
| 输入设备 | 仅键盘 |
| 玩家人数 | 仅 1P 单人 |
| ROM 加载 | 命令行参数传入 |
| 画面显示 | 固定倍数放大窗口，**默认 3 倍 (768×720)** |
| PPU 渲染 | 整帧一次性渲染（frame-at-once） |
| 时序同步 | 帧级同步（CPU 跑完一帧 → PPU 渲染 → APU 输出） |
| 调试工具 | 独立 Pygame 窗口，可关闭不可重新打开 |
| 音频输出 | 每帧生成一帧音频样本送入 Pygame mixer |
| APU DMC | 基本框架（寄存器读写 + 简单 delta 解码），后续按需完善 |
| CPU 日志 | 实现日志功能，默认关闭，通过 `--log` 参数启用 |
| 代码质量 | **pytest 全通过 + mypy strict + ruff 零警告** |

---

## 3. 项目文件结构

```
SUPER MARIO/
├── main.py              # 入口 + 主循环
├── cpu.py               # CPU 6502 模拟器
├── ppu.py               # PPU 图像处理器
├── apu.py               # APU 音频处理器
├── bus.py               # 总线 / 地址空间
├── cartridge.py         # 卡带 / Mapper 0
├── ram.py               # CPU RAM (2 KiB)
├── input.py             # 键盘输入
├── ui.py                # 游戏窗口
├── debug.py             # 调试窗口（--debug 启用）
├── palette.py           # NES 64 色调色板常量
├── requirements.txt     # 依赖列表
├── doc/
│   ├── SUPER MARIO.md   # 需求文档
│   ├── detailed-design.md  # 详细设计文档
│   ├── prompt.md        # 本文件（Vibe Coding Prompt）
│   └── tasks/           # 各模块任务文件
└── tests/
    ├── test_cpu.py
    ├── test_ppu.py
    ├── test_apu.py
    ├── test_bus.py
    ├── test_cartridge.py
    ├── test_ram.py
    ├── test_input.py
    ├── test_ui.py
    ├── test_palette.py
    ├── test_debug.py
    └── test_integration.py
```

---

## 4. 依赖 (requirements.txt)

```
pygame>=2.5.0
numpy>=1.24.0
```

---

## 5. 开发阶段与依赖关系

```
Phase 1 ──→ Phase 2 ──→ Phase 3 ──→ Phase 4 ──→ Phase 5 ──→ Phase 6
(RAM,     (PPU, UI)   (APU)      (Input)     (Debug)    (Main 联调)
Palette,
Cartridge,
Bus, CPU)
```

**严格按 Phase 顺序执行，每个模块完成后再进入下一个。同 Phase 内可按任意顺序。**

| 序号 | Phase | 模块 | 依赖 | 关键测试 |
|------|-------|------|------|----------|
| 1 | 1 | RAM | 无 | 读写 + 镜像 |
| 2 | 1 | Palette | 无 | 64 色数据完整性 |
| 3 | 1 | Cartridge | 无 | iNES 解析 + Mapper 0 映射 |
| 4 | 1 | Bus | RAM, PPU/APU/Cartridge/Input 接口 | Mock 地址路由 + OAM DMA |
| 5 | 1 | CPU | Bus | nestest 151 操作码 |
| 6 | 2 | PPU | Cartridge, Palette | 寄存器 + 渲染正确性 |
| 7 | 2 | UI | Pygame | 窗口 + 缩放 + 帧率 |
| 8 | 3 | APU | 无 | 5 通道波形 + 样本生成 |
| 9 | 4 | Input | Pygame | 键盘映射 + 移位寄存器 |
| 10 | 5 | Debug | CPU, PPU, Bus, Input | 调试窗口功能 |
| 11 | 6 | Main | 所有模块 | 集成测试 + 验收 |

---

## 6. 质量门禁（每个模块必须全部通过）

```bash
# 1. 单元测试（必须全部 PASS）
python -m pytest tests/test_<module>.py -v

# 2. 类型检查（必须零错误）
python -m mypy <module>.py --strict

# 3. 代码规范（必须零警告）
python -m ruff check <module>.py
```

**门禁规则**：任何一个门禁不通过 = 模块未完成，子 Agent 必须修复后重新验证。

---

## 7. 各模块详细规格

以下是每个模块的完整规格，子 Agent 必须严格按照此规格实现。

---

### 7.1 RAM 模块 (`ram.py`)

**职责**：CPU 内部 2 KiB 工作内存，最简单的存储模块。

```python
class RAM:
    def __init__(self, size: int = 2048):
        """分配 size 字节 bytearray，初始化为 0"""

    def read(self, addr: int) -> int:
        """读取 addr 处的 1 字节，地址自动镜像 (addr % size)"""

    def write(self, addr: int, value: int):
        """写入 value 到 addr，value 截断为 8 bit，地址自动镜像"""
```

**关键行为**：
- 地址 0x0000–0x07FF 映射到内部 2 KiB
- 0x0800–0x1FFF 是 0x0000–0x07FF 的镜像（通过 `addr % 2048` 自动实现）
- 写入超过 0xFF 的值自动截断为 `value & 0xFF`

**测试 (`tests/test_ram.py`)**：
- 初始状态读返回 0
- 基本读写验证
- 地址镜像验证（写 0x0800 读 0x0000 应相等）
- 写入值截断验证

---

### 7.2 Palette 模块 (`palette.py`)

**职责**：提供 NES 64 色系统调色板常量。

```python
# NES 64 色调色板，每个为 (R, G, B) 元组，范围 0–255
SYSTEM_PALETTE: list[tuple[int, int, int]] = [
    (0x7C, 0x7C, 0x7C),  # 0x00
    (0x00, 0x00, 0xFC),  # 0x01
    # ... 共 64 色
]
```

**参考**：https://www.nesdev.org/wiki/PPU_palettes

**关键行为**：
- 长度为 64
- 每个 R/G/B 值在 0–255 范围
- 0x0F = 黑色 (0, 0, 0) 或接近黑色
- 0x20 = 白色 (0xF8, 0xF8, 0xF8) 或接近白色

**测试 (`tests/test_palette.py`)**：
- 长度 = 64
- 所有值在 0–255
- 已知颜色抽查

---

### 7.3 Cartridge 模块 (`cartridge.py`)

**职责**：解析 iNES 格式 ROM 文件，仅实现 NROM (Mapper 0)。

#### iNES 文件头格式

| 偏移 | 大小 | 内容 |
|------|------|------|
| 0x00 | 4 | 魔术数 "NES" + 0x1A |
| 0x04 | 1 | PRG ROM 大小（16 KiB 单位）|
| 0x05 | 1 | CHR ROM 大小（8 KiB 单位）|
| 0x06 | 1 | Flags 6: bit0=镜像, bits3-0=Mapper低4位, bit2=Trainer |
| 0x07 | 1 | Flags 7: Mapper 高 4 位 |
| 0x08 | 8 | 保留 |
| 0x10 | 可变 | Trainer（512 字节，若有）|

#### Mapper 0 地址映射

**CPU 侧 (0x4020–0xFFFF)**：
- 16 KiB PRG: 0x8000–0xBFFF → PRG ROM; 0xC000–0xFFFF → 镜像
- 32 KiB PRG: 0x8000–0xFFFF → 连续 PRG ROM（马里奥 1 代使用此模式）

**PPU 侧 (0x0000–0x1FFF)**：
- 8 KiB CHR ROM: 直接映射 Pattern Table 0 + Table 1
- CHR RAM (CHR_ROM_SIZE=0): 8 KiB 可写 RAM

**镜像模式**：
- Flag 6 bit0 = 0 → Horizontal
- Flag 6 bit0 = 1 → Vertical（马里奥 1 代使用）

```python
class Cartridge:
    def __init__(self): ...
    
    @staticmethod
    def load(filepath: str) -> "Cartridge":
        """加载 .nes 文件，验证魔术数 + Mapper 0，读取 PRG/CHR ROM"""
    
    def cpu_read(self, addr: int) -> int:
        """CPU 侧读卡带 (addr: 0x4020–0xFFFF)"""
    
    def cpu_write(self, addr: int, value: int):
        """CPU 侧写卡带 (NROM PRG ROM 只读，忽略)"""
    
    def ppu_read(self, addr: int) -> int:
        """PPU 侧读卡带 (addr: 0x0000–0x1FFF)"""
    
    def ppu_write(self, addr: int, value: int):
        """PPU 侧写卡带 (CHR RAM 模式有效)"""
    
    @property
    def mirroring(self) -> str:
        """返回 'horizontal' 或 'vertical'"""
    
    @property
    def prg_rom(self) -> bytes: ...
    
    @property
    def chr_rom(self) -> bytes | None: ...
```

**错误处理**：
- 非法魔术数 → 抛出异常并输出友好信息
- Mapper != 0 → 抛出异常 "仅支持 Mapper 0 (NROM)"

**测试 (`tests/test_cartridge.py`)**：
- 构造合法 iNES 最小文件验证解析
- 非法魔术数应抛异常
- 非 Mapper 0 应抛异常
- 16 KiB / 32 KiB PRG 映射验证
- CHR RAM 模式验证
- 镜像模式验证
- 使用 `tempfile` 或 `BytesIO` 构造测试 ROM

---

### 7.4 Bus 模块 (`bus.py`)

**职责**：模拟 FC 16 位地址总线，路由读写请求到各设备。

#### 内存映射

| 地址范围 | 映射到 | 路由规则 |
|----------|--------|----------|
| 0x0000–0x1FFF | CPU RAM | `cpu_ram.read/write(addr)`（RAM 内部镜像）|
| 0x2000–0x3FFF | PPU 寄存器 | `ppu.read/write_register(0x2000 + (addr % 8))` |
| 0x4000–0x4013, 0x4015 | APU | `apu.read/write_register(addr)` |
| 0x4014 | OAM DMA | 特殊处理（见下）|
| 0x4016 | Input | `input_dev.read/write()` |
| 0x4017 | APU | `apu.read/write_register(0x4017)` |
| 0x4020–0xFFFF | Cartridge | `cartridge.cpu_read/cpu_write(addr)` |

#### OAM DMA (0x4014)

写入 0x4014 触发：将 CPU 内存 `(value << 8)` 起的 256 字节复制到 PPU OAM。
- 消耗：513 CPU 周期
- Bus 需提供 `dma_cycles` 属性或返回值，供 CPU 累加

```python
class Bus:
    def __init__(self, cpu_ram, ppu, apu, cartridge, input_dev):
        """持有所有设备引用"""
    
    def read(self, addr: int, from_ppu: bool = False) -> int:
        """从地址读 1 字节"""
    
    def write(self, addr: int, value: int):
        """向地址写 1 字节"""
    
    @property
    def dma_cycles(self) -> int:
        """返回 OAM DMA 消耗的额外周期（若上次写 0x4014 触发）"""
```

**测试 (`tests/test_bus.py`)**：
- 使用 Mock 对象验证各地址范围路由正确
- 0x2008 镜像到 0x2000
- OAM DMA 正确复制 256 字节
- 所有设备接口被正确调用
- 需要定义 MockRAM, MockPPU, MockAPU, MockCartridge, MockInput

---

### 7.5 CPU 模块 (`cpu.py`)

**职责**：模拟 6502 CPU，实现全部 56 条官方指令，151 个操作码。

#### 寄存器

| 寄存器 | 位宽 | 说明 |
|--------|------|------|
| A | 8 | 累加器 |
| X | 8 | 索引寄存器 |
| Y | 8 | 索引寄存器 |
| PC | 16 | 程序计数器 |
| SP | 8 | 栈指针 (栈页 0x0100–0x01FF) |
| P | 8 | 状态标志 |

**状态标志位**：

| 位 | 标志 | 名称 |
|----|------|------|
| 0 | C | Carry |
| 1 | Z | Zero |
| 2 | I | Interrupt Disable |
| 3 | D | Decimal（NES 2A03 无此功能，始终 0）|
| 4 | B | Break |
| 5 | U | Unused（始终 1）|
| 6 | V | Overflow |
| 7 | N | Negative |

#### 寻址方式（13 种，全部实现）

| 缩写 | 名称 | 说明 |
|------|------|------|
| IMP | Implied | 无操作数 |
| ACC | Accumulator | 操作 A 寄存器 |
| IMM | Immediate | 1 字节立即数 |
| ZP0 | Zero Page | 零页地址 |
| ZPX | Zero Page,X | 零页 + X |
| ZPY | Zero Page,Y | 零页 + Y |
| ABS | Absolute | 2 字节绝对地址 |
| ABX | Absolute,X | 绝对 + X |
| ABY | Absolute,Y | 绝对 + Y |
| IND | Indirect | JMP 间接 |
| IZX | Indirect,X | (零页 + X) 指针 |
| IZY | Indirect,Y | 零页指针 + Y |
| REL | Relative | 8 位有符号偏移 |

**跨页惩罚**：ABX/ABY/IZY 在地址跨页时追加 1 个额外周期。

#### 指令集（56 条，151 个操作码）

| 类别 | 指令 |
|------|------|
| 加载/存储 | LDA, LDX, LDY, STA, STX, STY |
| 寄存器传输 | TAX, TXA, TAY, TYA, TSX, TXS |
| 栈操作 | PHA, PHP, PLA, PLP |
| 算术 | ADC, SBC, INC, INX, INY, DEC, DEX, DEY |
| 逻辑 | AND, ORA, EOR, ASL, LSR, ROL, ROR, BIT |
| 比较 | CMP, CPX, CPY |
| 分支 | BCC, BCS, BEQ, BMI, BNE, BPL, BVC, BVS |
| 跳转/子程序 | JMP, JSR, RTS, RTI |
| 标志操作 | CLC, SEC, CLD, SED, CLI, SEI, CLV |
| 其他 | BRK, NOP |

#### 中断

| 中断 | 向量 | 触发条件 |
|------|------|----------|
| NMI | 0xFFFA–0xFFFB | PPU VBlank 开始时触发 |
| RESET | 0xFFFC–0xFFFD | 开机 / cpu.reset() |
| IRQ | 0xFFFE–0xFFFF | BRK 指令（马里奥不用硬件 IRQ）|

#### 核心接口

```python
class CPU:
    def __init__(self, bus: "Bus"): ...
    
    def reset(self) -> int:
        """SP=0xFD, P=0x34, PC=read_word(0xFFFC), 消耗 7 周期"""
    
    def step(self) -> int:
        """执行 1 条指令，返回消耗的 CPU 周期数"""
    
    def nmi(self) -> int:
        """触发 NMI，压栈 PC/P，PC=NMI 向量，消耗 7 周期"""
    
    def irq(self) -> int:
        """若 I=1 不处理；否则压栈 PC/P，PC=IRQ 向量"""
    
    # 只读寄存器属性
    @property
    def a(self) -> int: ...
    @property
    def x(self) -> int: ...
    @property
    def y(self) -> int: ...
    @property
    def pc(self) -> int: ...
    @property
    def sp(self) -> int: ...
    @property
    def p(self) -> int: ...
```

#### 操作码调度表

使用字典或 match/case（Python 3.10+）调度 151 个操作码。每个条目：`opcode → (指令函数, 寻址函数, 基础周期数)`。

#### step() 执行流程

```
1. 取指：opcode = bus.read(PC); PC += 1
2. 查表获取 (instr_fn, addr_fn, base_cycles)
3. 调用 addr_fn() 获取操作数地址
4. 调用 instr_fn(addr) 执行操作
5. 检查跨页惩罚，追加额外周期
6. 返回实际周期数
```

#### 日志功能

通过 `--log` 命令行参数启用，格式：
```
PC   OP  A  X  Y  SP  P  CYC
C000  A9  00 00 00 FD 34  0
```

#### 关键测试：nestest

- 加载 nestest ROM（仅 PRG ROM，映射到 0xC000–0xFFFF）
- 设置 PC = 0xC000（nestest 入口）
- 自动运行，与 nestest 参考日志逐条对比 PC, A, X, Y, SP, P, 周期数
- **必须 151 个官方操作码全部通过**

**测试 (`tests/test_cpu.py`)**：
- nestest 完整测试框架
- 每条指令后寄存器 + 周期数对比
- 不匹配时输出差异

---

### 7.6 PPU 模块 (`ppu.py`)

**职责**：模拟图像处理器，采用整帧一次性渲染方式。

#### 内部存储

| 存储区 | 大小 | 说明 |
|--------|------|------|
| VRAM | 2048 字节 | Nametable（2 × 1024 字节）|
| Palette RAM | 32 字节 | 8 组 × 4 色（背景 4 组 + 精灵 4 组）|
| OAM | 256 字节 | 64 精灵条目 × 4 字节 |
| OAM 辅助 | 256 字节 | 精灵评测用 |

#### PPU 寄存器

| CPU 地址 | 名称 | 方向 | 说明 |
|----------|------|------|------|
| 0x2000 | PPUCTRL | W | NMI 使能、名称表选择、增量、精灵/背景 PT 选择、精灵大小 |
| 0x2001 | PPUMASK | W | 灰度、背景/精灵左列裁剪、显示背景/精灵、强调色 |
| 0x2002 | PPUSTATUS | R | VBlank(bit7)、Sprite 0 Hit(bit6)、Sprite Overflow(bit5)；读后清 VBlank + 复位写锁存器 |
| 0x2003 | OAMADDR | W | OAM 地址指针 |
| 0x2004 | OAMDATA | R/W | OAM 数据端口 |
| 0x2005 | PPUSCROLL | W×2 | 滚动（第1次=水平，第2次=垂直）|
| 0x2006 | PPUADDR | W×2 | VRAM 地址（第1次=高字节，第2次=低字节，15 bit 有效）|
| 0x2007 | PPUDATA | R/W | VRAM 数据（读缓冲延迟 1 次，读/写后地址 + 增量）|

**写锁存器（w 触发器）**：PPUSCROLL 和 PPUADDR 共用。读 PPUSTATUS 后复位。

#### 时序

| 常量 | 值 | 说明 |
|------|-----|------|
| 可见扫描线 | 0–239 | 可见行 |
| 后渲染行 | 240 | |
| VBlank 开始 | 241 | PPUSTATUS bit7 = 1 |
| VBlank 结束 | 260 | |
| 预渲染行 | 261 | 清除 VBlank/Sprite0Hit/SpriteOverflow |
| 扫描线周期 | 341 | |
| 总扫描线 | 262 | |

**NMI 触发**：扫描线 241 周期 1，若 PPUCTRL bit7 = 1 → step() 返回 True。

#### 渲染算法

**render_frame() 流程**：

1. **背景层**（256×240 像素）：
   - 从 PPUCTRL 获取名称表基址，从 PPUSCROLL 获取滚动偏移
   - 遍历 32×30 个 tile（8×8 像素），考虑滚动和名称表边界跨越
   - 每个 tile：
     - 查 Nametable → tile 索引
     - 查 Attribute Table → 调色板组（每字节覆盖 4×4 tile）
     - 查 Pattern Table → 2 个 bit-plane → 2-bit 颜色索引
     - `color_idx = ((plane0 >> (7-x)) & 1) | (((plane1 >> (7-x)) & 1) << 1)`
     - color_idx 0 → Palette[0]（通用背景色）
     - color_idx 1–3 → Palette[group][idx]
     - 查 SYSTEM_PALETTE → RGB

2. **精灵层**：
   - 倒序遍历 OAM 64 条目（低优先 → 高优先）
   - 每条目 4 字节：Y、Tile 索引、属性、X
   - 属性：bit7=VFlip, bit6=HFlip, bit5=Behind BG, bits1-0=调色板组
   - 精灵尺寸：8×8（马里奥 1 代）
   - 精灵 0 Hit 检测

3. **合成**：
   - 精灵透明像素 → 显示背景
   - Behind BG + 背景非透明 → 显示背景
   - 其余 → 显示精灵

#### 镜像处理

Nametable 镜像由 Cartridge.mirroring 决定：
- Vertical: NT0↔NT2, NT1↔NT3
- Horizontal: NT0↔NT1, NT2↔NT3

#### 核心接口

```python
class PPU:
    def __init__(self, cartridge: "Cartridge"): ...
    
    def step(self, cpu_cycles: int) -> bool:
        """推进 PPU 时间，返回是否触发 NMI"""
    
    def render_frame(self) -> list[list[tuple[int, int, int]]]:
        """一次性渲染整帧，返回 256×240 RGB 像素数组"""
    
    def read_register(self, addr: int) -> int: ...
    def write_register(self, addr: int, value: int): ...
    def read(self, addr: int) -> int: ...
    def write(self, addr: int, value: int): ...
    def oam_write(self, index: int, value: int): ...
    
    # 调试数据
    def get_pattern_table(self, table_index: int) -> list[list[tuple[int,int,int]]]:
        """返回 128×128 Pattern Table 可视化像素"""
    
    def get_palette_data(self) -> bytes: ...
    
    @property
    def frame(self) -> int: ...
```

**测试 (`tests/test_ppu.py`)**：
- 寄存器写入/读取验证
- 写锁存器行为
- PPUDATA 缓冲读 + 自动递增
- 构造已知 VRAM/OAM/调色板 → 验证 render_frame() 特定像素
- VBlank 时序 + NMI 触发

---

### 7.7 UI 模块 (`ui.py`)

**职责**：Pygame 游戏窗口，画面放大显示，帧率控制。

#### 配置

```python
NATIVE_WIDTH = 256
NATIVE_HEIGHT = 240
SCALE_FACTOR = 3          # 默认 3 倍 → 768×720
WINDOW_WIDTH = 768
WINDOW_HEIGHT = 720
FPS_TARGET = 60.0988      # NTSC 实际帧率
```

#### 核心接口

```python
class UI:
    def __init__(self, scale: int = 3):
        """scale 限制 1–5，创建窗口 + 内部 Surface + Clock"""
    
    def render(self, pixels: list[list[tuple[int,int,int]]]):
        """
        将 256×240 像素数组渲染到窗口：
        1. 用 pygame.surfarray.blit_array() 写内部 Surface
        2. pygame.transform.scale() 放大
        3. pygame.display.flip() 刷新
        """
    
    def handle_events(self) -> bool:
        """
        处理窗口事件。返回是否应退出。
        - QUIT → True
        - KEYDOWN/KEYUP → 放回队列
        """
    
    def tick(self):
        """pygame.time.Clock().tick(FPS_TARGET)"""
    
    def get_fps(self) -> float:
        """返回当前实际 FPS"""
```

**关键行为**：
- handle_events() 中 KEYDOWN/KEYUP 事件放回队列供 Input 模块处理
- render() 优先用 `pygame.surfarray.blit_array()`（最快）或 `PixelArray`

**测试 (`tests/test_ui.py`)**：
- 非渲染部分单元测试（事件处理、tick FPS）
- 渲染部分人工/集成验证

---

### 7.8 APU 模块 (`apu.py`)

**职责**：模拟音频处理器，5 个声音通道，每帧生成 PCM 音频样本。

#### 5 个声音通道

| # | 通道 | 产生的声音 | 实现深度 |
|---|------|-----------|----------|
| 1 | Pulse 1 | 旋律线 1 | 完整（含频率扫描）|
| 2 | Pulse 2 | 旋律线 2 | 完整（含频率扫描）|
| 3 | Triangle | 低音线 | 完整（含线性计数器）|
| 4 | Noise | 打击/音效 | 完整（含 LFSR）|
| 5 | DMC | 低质量采样 | **基本框架** |

#### DMC 基本框架（仅实现）

- 寄存器读写（0x4010–0x4013）
- 简单 delta 解码：`output_unit +/-= 2`
- 速率定时器
- **不做**：内存读取器（不从 Bus 读采样数据）、IRQ 触发、循环播放

#### 帧计数器（Frame Counter）

- 4-step 模式（默认）：步进于 3728.5, 7457, 11185.5, 14914 CPU 周期
- 5-step 模式（0x4017 bit7=1）：同上 + 18640.5
- 每次步进：更新包络、频率扫描、波长计数器

#### 寄存器地址

| 地址 | Pulse 1 | Pulse 2 | Triangle | Noise | DMC |
|------|---------|---------|----------|-------|-----|
| 0x4000 | SQ1_VOL | | | | |
| 0x4001 | SQ1_SWEEP | | | | |
| 0x4002 | SQ1_LO | | | | |
| 0x4003 | SQ1_HI | | | | |
| 0x4004 | | SQ2_VOL | | | |
| 0x4005 | | SQ2_SWEEP | | | |
| 0x4006 | | SQ2_LO | | | |
| 0x4007 | | SQ2_HI | | | |
| 0x4008 | | | TRI_LINEAR | | |
| 0x400A | | | TRI_LO | | |
| 0x400B | | | TRI_HI | | |
| 0x400C | | | | NOISE_VOL | |
| 0x400E | | | | NOISE_LO | |
| 0x400F | | | | NOISE_HI | |
| 0x4010 | | | | | DMC_FREQ |
| 0x4011 | | | | | DMC_RAW |
| 0x4012 | | | | | DMC_START |
| 0x4013 | | | | | DMC_LEN |
| 0x4015 | SND_CHN（全部通道使能/状态）|
| 0x4017 | FRAME_COUNTER |

#### 音频样本生成

```python
SAMPLE_RATE = 44100
SAMPLES_PER_FRAME = 44100 // 60  # 约 735
CPU_CLOCK = 1789773
CYCLES_PER_SAMPLE = CPU_CLOCK / SAMPLE_RATE  # 约 40.58

def get_audio_samples(self) -> list[int]:
    """
    生成一帧时长的 PCM 16-bit 有符号整数列表。
    每样本推进 CYCLES_PER_SAMPLE CPU 周期，更新通道状态，混合输出。
    """
```

#### 混合公式

```
pulse_out = (pulse1 + pulse2) / 15 * 0.3
tri_out = triangle / 15 * 0.3
noise_out = noise / 15 * 0.2
dmc_out = dmc / 127 * 0.2
output = (pulse_out + tri_out + noise_out + dmc_out) / 4
```

#### 核心接口

```python
class APU:
    def __init__(self): ...
    
    def step(self, cpu_cycles: int):
        """推进 APU 时间，驱动帧计数器"""
    
    def get_audio_samples(self) -> list[int]:
        """生成当前帧 PCM 16-bit 样本列表"""
    
    def read_register(self, addr: int) -> int: ...
    def write_register(self, addr: int, value: int): ...
```

**测试 (`tests/test_apu.py`)**：
- Pulse 占空比 + 频率 + 包络 + 频率扫描验证
- Triangle 三角波形状验证
- Noise LFSR 输出验证
- DMC delta 解码验证
- 帧计数器步进验证
- get_audio_samples() 返回合理样本

---

### 7.9 Input 模块 (`input.py`)

**职责**：键盘输入映射到 FC 手柄，模拟手柄端口读取。

#### 键盘映射

```python
KEY_MAPPING = {
    pygame.K_UP:     0,  # 上
    pygame.K_DOWN:   1,  # 下
    pygame.K_LEFT:   2,  # 左
    pygame.K_RIGHT:  3,  # 右
    pygame.K_k:      4,  # A
    pygame.K_j:      5,  # B
    pygame.K_RETURN: 6,  # Start
    pygame.K_RSHIFT: 7,  # Select
}
```

#### FC 手柄读取机制

1. 向 0x4016 写 1 → 锁存按钮到移位寄存器
2. 向 0x4016 写 0 → 结束锁存
3. 反复读 0x4016 → 按 A→B→Select→Start→↑→↓→←→→ 顺序返回每个按钮状态
4. 第 9 次及之后 → 返回 1

```python
class Input:
    def __init__(self): ...
    
    def poll(self):
        """处理 Pygame 事件，更新按钮状态。非按键事件放回队列"""
    
    def write(self, value: int):
        """向 0x4016 写入（bit0: 1=锁存, 0=结束锁存）"""
    
    def read(self) -> int:
        """从 0x4016 读取当前按钮状态位 | 0x40"""
    
    def get_state(self) -> list[int]:
        """返回 8 个按钮状态副本，供调试窗口使用"""
```

**测试 (`tests/test_input.py`)**：
- Mock Pygame 事件验证 poll() 行为
- 锁存 → 读取 8 次 → 验证顺序 A/B/Sel/Start/↑/↓/←/→
- 第 9 次读取返回 1
- 非映射按键事件放回队列

---

### 7.10 Debug 模块 (`debug.py`)

**职责**：独立 Pygame 调试窗口（640×480）。

#### 调试功能

| 功能 | 位置 | 说明 |
|------|------|------|
| CPU 寄存器 | 左上 | A, X, Y, PC, SP, P（展开标志位）|
| 运行信息 | 右上 | FPS、帧号、RUNNING/PAUSED |
| 内存查看 | 左下 | 16 行 × 16 字节 hex dump，可滚动 |
| Pattern Table | 右下区 | 可选：两个 PT 128×128 可视化 |
| 调色板 | 右下区下方 | 可选：32 色块展示 |
| 快捷键提示 | 底部 | 控制说明 |

#### 快捷键

| 按键 | 功能 |
|------|------|
| F5 | 暂停 / 继续 |
| F6 | 帧步进（暂停时）|
| F7 | 指令步进（暂停时）|
| F1 | 内存起始地址 +0x100 |
| F2 | 内存起始地址 -0x100 |
| ↑ | 内存滚动 +0x10 |
| ↓ | 内存滚动 -0x10 |
| PgUp | 内存翻页 +0x100 |
| PgDn | 内存翻页 -0x100 |

#### 核心接口

```python
class DebugWindow:
    def __init__(self, cpu: "CPU", ppu: "PPU", bus: "Bus", input_dev: "Input"):
        """创建 640×480 独立窗口，持有只读引用"""
    
    def update(self):
        """刷新内部数据缓存"""
    
    def render(self):
        """渲染调试窗口全部内容"""
    
    def handle_input(self) -> dict:
        """
        处理调试快捷键，返回控制命令 dict。
        如 {'action': 'pause'} 或 {'action': 'step', 'step': 'frame'}
        """
    
    @property
    def visible(self) -> bool:
        """窗口是否可见（关闭后为 False）"""
```

**关闭行为**：用户点 X 关闭调试窗口后 `visible = False`，不影响主游戏窗口。不可重新打开。

**测试 (`tests/test_debug.py`)**：
- Mock CPU/PPU/Bus/Input 注入
- handle_input() 对 F5 返回 `{'action': 'pause'}`
- 窗口关闭 → `visible = False`
- render()/update() 不崩溃

---

### 7.11 Main 模块 (`main.py`)

**职责**：程序入口，串联所有模块，主帧循环。

#### 命令行参数

```
python main.py <rom_file> [--scale N] [--debug] [--log]

  rom_file    : （必填）.nes ROM 文件路径
  --scale N   : （可选）画面放大倍数，默认 3，范围 1–5
  --debug     : （可选）启用调试窗口
  --log       : （可选）启用 CPU 指令日志
```

#### 初始化流程

```python
def main():
    1. parse_args()
    2. pygame.init()
    3. cartridge = Cartridge.load(args.rom_file)
    4. ram = RAM(2048)
    5. ppu = PPU(cartridge)
    6. apu = APU()
    7. input_dev = Input()
    8. bus = Bus(ram, ppu, apu, cartridge, input_dev)
    9. cpu = CPU(bus)
    10. ui = UI(scale=args.scale)
    11. debug = DebugWindow(cpu, ppu, bus, input_dev) if args.debug else None
    12. pygame.mixer.init(frequency=44100, size=-16, channels=1)
    13. cpu.reset()
    14. run_loop(...)
```

#### 主循环

```python
FRAME_CPU_CYCLES = 29781  # NTSC 一帧的 CPU 周期数

def run_loop(cpu, ppu, apu, bus, input_dev, ui, debug):
    running = True
    paused = False
    step_mode = None  # None | 'frame' | 'instruction'
    
    while running:
        1. ui.handle_events() → 退出？
        2. input_dev.poll()
        3. if debug and debug.visible:
             cmd = debug.handle_input()
             处理暂停/步进命令
        4. if not paused:
             累积执行 cpu.step() 直到 cycles_this_frame >= 29781
             每次 step 后驱动 ppu.step(cycles) 和 apu.step(cycles)
             ppu.step 返回 True → cpu.nmi()
             处理指令/帧步进
        5. pixels = ppu.render_frame()
        6. ui.render(pixels)
        7. samples = apu.get_audio_samples()
        8. sound = pygame.sndarray.make_sound(np.array(samples, dtype=np.int16))
        9. sound.play()
        10. if debug and debug.visible:
              debug.update()
              debug.render()
        11. ui.tick()
    
    pygame.quit()
```

#### 异常处理

| 异常 | 输出 |
|------|------|
| 文件不存在 | "错误：找不到 ROM 文件 '{path}'" |
| 魔术数非法 | "错误：'{path}' 不是有效的 iNES ROM 文件" |
| Mapper != 0 | "错误：仅支持 Mapper 0 (NROM)，当前 ROM Mapper 号为 {n}" |
| 任何异常 | 确保调用 pygame.quit() 后退出 |

**测试 (`tests/test_integration.py`)**：
- 加载 ROM 模拟运行 1/10 帧无崩溃
- 非法文件友好报错
- 命令行参数解析正确
- 无 ROM 文件时使用 mock 验证初始化流程

---

## 8. 子 Agent 工作模板

每个子 Agent 收到任务后，按以下步骤工作：

### Step 1: 阅读与理解
- 阅读本 Prompt 中对应模块的完整规格（第 7 章）
- 阅读 `doc/tasks/<module>.md` 中的任务清单

### Step 2: 编写代码
- 严格按照模块规格实现
- 代码风格：清晰、有注释、类型标注完整
- 所有公开方法必须有类型标注

### Step 3: 编写测试
- 创建 `tests/test_<module>.py`
- 覆盖任务清单和规格中列出的所有测试用例
- 测试应独立、可重复、不依赖外部 ROM 文件（除 CPU 的 nestest 测试）

### Step 4: 质量门禁
```bash
# 必须全部通过
python -m pytest tests/test_<module>.py -v
python -m mypy <module>.py --strict
python -m ruff check <module>.py
```

### Step 5: 报告
- 向主 Agent 报告：代码行数、测试数、三个门禁结果
- 若有失败，修复后重新报告

---

## 9. 进度追踪文件更新规范

每完成一个模块，更新 `doc/tasks/progress.md`：

```markdown
| N | Phase X | Module | [module.md](module.md) | [x] 已完成 | 备注：pytest/mypy/ruff 全通过 |
```

同时更新对应 `doc/tasks/<module>.md` 中的复选框：
```markdown
- [x] **1. xxx**
```

---

## 10. 关键参考资料

- NES 6502 指令集：https://www.nesdev.org/obelisk-6502-guide/
- PPU 调色板：https://www.nesdev.org/wiki/PPU_palettes
- APU 音频：https://www.nesdev.org/wiki/APU
- iNES 格式：https://www.nesdev.org/wiki/INES
- NROM Mapper：https://www.nesdev.org/wiki/NROM
- nestest ROM：https://www.nesdev.org/wiki/Emulator_tests

---

## 11. 开始工作

作为主 Agent，你的第一个动作是：

1. **检查环境**：确认 Python 3.10+ 已安装，`pip install pygame numpy mypy ruff` 已就绪
2. **从 Phase 1 RAM 模块开始**：派生子 Agent → 实现 `ram.py` + `tests/test_ram.py` → 跑通三个门禁
3. **严格按 Phase 顺序推进**，每个模块完成后再进入下一个

**现在开始执行 Phase 1 的第一个模块：RAM。**
