# 超级玛丽 FC 模拟器 —— 详细设计文档

> 文档版本：v1.0
> 编写日期：2026-06-18
> 对应需求文档：doc/SUPER MARIO.md v1.0
>
> **设计决策摘要**（经与需求方确认）：
> - PPU 渲染：整帧一次性渲染（frame-at-once）
> - 时序同步：帧级同步（CPU 跑完一帧 → PPU 渲染 → APU 输出）
> - 调试工具：独立 Pygame 窗口
> - 音频输出：每帧生成一帧音频样本送入 Pygame

---

## 1. 架构概览

### 1.1 整体架构图

```
┌─────────────────────────────────────────────────────────────┐
│                         main.py                              │
│              （入口：初始化、主循环、调度）                      │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐         │
│  │   CPU   │  │   PPU   │  │   APU   │  │  Input  │         │
│  │ (6502)  │  │ (图像)   │  │ (音频)   │  │ (键盘)   │         │
│  └────┬────┘  └────┬────┘  └────┬────┘  └────┬────┘         │
│       │            │            │            │               │
│  ┌────┴────────────┴────────────┴────────────┴────┐         │
│  │                    Bus（总线）                   │         │
│  │  ┌──────────────────────────────────────────┐  │         │
│  │  │         统一地址空间 (0x0000–0xFFFF)       │  │         │
│  │  └──────────────────────────────────────────┘  │         │
│  └────────────────────────────────────────────────┘         │
│                                                               │
│  ┌─────────────┐  ┌──────────────┐                           │
│  │   Cartridge  │  │     RAM      │                           │
│  │  (卡带/Mapper)│  │  (CPU + PPU) │                           │
│  └─────────────┘  └──────────────┘                           │
│                                                               │
├─────────────────────────────────────────────────────────────┤
│                       UI / 显示层                              │
│  ┌────────────────┐  ┌────────────────┐                       │
│  │   Game Window  │  │  Debug Window  │                       │
│  │  (Pygame 主窗口)│  │  (Pygame 副窗口)│                       │
│  └────────────────┘  └────────────────┘                       │
└─────────────────────────────────────────────────────────────┘
```

### 1.2 模块职责一览

| 模块 | 文件 | 核心职责 | 对外接口 |
|------|------|----------|----------|
| **CPU** | `cpu.py` | 执行 6502 指令，管理寄存器与状态标志 | `step()`, `reset()`, `read_memory()`, `write_memory()` |
| **PPU** | `ppu.py` | 管理 VRAM、OAM、调色板，渲染每帧画面 | `step(cycles)`, `render_frame()`, `read_register()`, `write_register()` |
| **APU** | `apu.py` | 模拟 5 个声音通道，生成音频样本 | `step(cycles)`, `get_audio_samples()`, `read_register()`, `write_register()` |
| **Bus** | `bus.py` | 统一地址空间，路由读写请求到各设备 | `read(addr)`, `write(addr, value)` |
| **Cartridge** | `cartridge.py` | 解析 `.nes` 文件，提供 PRG ROM / CHR ROM 数据 | `load(filepath)`, `cpu_read(addr)`, `cpu_write(addr, value)`, `ppu_read(addr)`, `ppu_write(addr, value)` |
| **RAM** | `ram.py` | CPU 内存 (0x0000–0x07FF) + PPU 内存映射 | `read(addr)`, `write(addr, value)` |
| **Input** | `input.py` | 读取键盘，映射到 FC 手柄按钮状态 | `poll()`, `get_state()` |
| **UI** | `ui.py` | Pygame 窗口管理，画面放大显示，FPS 控制 | `init()`, `render(pixels)`, `handle_events()` |
| **Debug** | `debug.py` | 独立调试窗口：CPU 寄存器、内存查看、单步/帧步进 | `update()`, `render()`, `handle_input()` |
| **Main** | `main.py` | 串联所有模块，执行帧循环，命令行参数解析 | — |

### 1.3 数据流（一帧的处理过程）

```
[键盘输入] → Input.poll()                    # 1. 读取按键
    ↓
[CPU 执行 29781 周期]                          # 2. 运行游戏逻辑
    ↓  读写内存经过 Bus 路由
[Bus 路由] → RAM / Cartridge / PPU寄存器 / APU寄存器
    ↓
[PPU.render_frame()] → 256×240 像素数组        # 3. 生成画面
    ↓
[APU.get_audio_samples()] → PCM 样本数组       # 4. 生成音频
    ↓
[UI.render(pixels)] → 放大显示                  # 5. 显示画面
[pygame.mixer 播放音频样本]                      # 6. 播放声音
[Debug.update() → Debug.render()]              # 7. 更新调试窗口
    ↓
[UI 控制帧率] → 回到步骤 1                       # 8. 帧率控制
```

---

## 2. 模块详细设计

### 2.1 CPU（6502 模拟器） — `cpu.py`

#### 2.1.1 概述

模拟 Ricoh 2A03（6502 派生）CPU，仅实现《超级马里奥兄弟》1 代实际使用的指令与寻址方式。

#### 2.1.2 寄存器

| 寄存器 | 大小 | 说明 |
|--------|------|------|
| A (Accumulator) | 8 bit | 累加器，算术/逻辑运算主寄存器 |
| X | 8 bit | 索引寄存器，用于变址寻址与循环 |
| Y | 8 bit | 索引寄存器，用于变址寻址与循环 |
| PC (Program Counter) | 16 bit | 程序计数器，指向下一条要执行的指令地址 |
| SP (Stack Pointer) | 8 bit | 栈指针，指向栈页 (0x0100–0x01FF) 的偏移 |
| P (Status Flags) | 8 bit | 状态标志寄存器（7 个有效位） |

**状态标志位 (P 寄存器):**

| 位 | 标志 | 名称 | 说明 |
|----|------|------|------|
| 0 | C | Carry | 进位/借位标志 |
| 1 | Z | Zero | 结果为零 = 1 |
| 2 | I | Interrupt Disable | 中断禁止（始终设为 1，马里奥不用 IRQ） |
| 3 | D | Decimal | 十进制模式（6502 特有，NES 的 2A03 无此功能，始终为 0） |
| 4 | B | Break | BRK 指令标志 |
| 5 | — | (unused) | 未使用，始终为 1 |
| 6 | V | Overflow | 溢出标志 |
| 7 | N | Negative | 结果为负（bit 7 = 1）= 1 |

#### 2.1.3 寻址方式（需实现的）

马里奥 1 代实际使用的寻址方式。**重要**：不实现游戏未用到的寻址方式，避免无效工作量。

以下列表为 6502 全部寻址方式，标注"★"表示马里奥 1 代必定用到、必须实现：

| 寻址方式 | 缩写 | 说明 | 必须？ |
|----------|------|------|--------|
| Implied | IMP | 无操作数（如 TAX、INX、RTS） | ★ |
| Accumulator | ACC | 操作 A 寄存器（如 LSR A） | ★ |
| Immediate | IMM | 操作数为紧跟的 1 字节立即数 | ★ |
| Zero Page | ZP0 | 操作数地址在零页 (0x00–0xFF) | ★ |
| Zero Page,X | ZPX | 零页地址 + X 索引 | ★ |
| Zero Page,Y | ZPY | 零页地址 + Y 索引 | ★ |
| Absolute | ABS | 操作数地址为 2 字节绝对地址 | ★ |
| Absolute,X | ABX | 绝对地址 + X 索引 | ★ |
| Absolute,Y | ABY | 绝对地址 + Y 索引 | ★ |
| Indirect | IND | JMP 间接跳转 (仅 JMP) | ★ |
| Indirect,X | IZX | (零页地址 + X) 作为指针，读目标地址 | ★ |
| Indirect,Y | IZY | 零页地址作为指针 + Y 索引 | ★ |
| Relative | REL | 分支指令的 8 位有符号偏移 | ★ |

**确认策略**：实现所有 13 种寻址方式。逐一列出是为了明确"实现全部"这一决定——马里奥 1 代作为典型的 NROM 游戏，几乎使用全部寻址方式。若某寻址方式确实未被使用，实现也无妨（代码量很小）。

#### 2.1.4 指令集（需实现的）

**确认策略**：实现全部 56 条"官方"指令（含非法指令的则仅实现官方指令）。马里奥 1 代不使用非法/未文档化指令（NROM 游戏通常不依赖），因此仅需实现标准 6502 指令集。

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

**总计：56 条指令**，每条指令需实现对应所有寻址方式的操作码。6502 共有 151 个官方操作码。

#### 2.1.5 中断

| 中断类型 | 向量地址 | 说明 | 实现？ |
|----------|----------|------|--------|
| NMI (Non-Maskable Interrupt) | 0xFFFA–0xFFFB | PPU 每帧 VBlank 开始时触发 | ★ 必须 |
| RESET | 0xFFFC–0xFFFD | 开机/重置时触发 | ★ 必须 |
| IRQ/BRK | 0xFFFE–0xFFFF | 可屏蔽中断（马里奥 1 代不使用 IRQ） | ★ 必须（BRK 指令需要） |

#### 2.1.6 CPU 核心接口

```python
class CPU:
    def __init__(self, bus: Bus):
        """初始化 CPU，通过 bus 访问所有内存和设备"""

    def reset(self):
        """
        硬件复位：
        - SP = 0xFD
        - P = 0x34 (I=1, unused=1)
        - PC = 从 0xFFFC-0xFFFD 读取复位向量
        - 消耗 7 个周期
        """

    def step(self) -> int:
        """
        执行 1 条指令。
        返回：消耗的 CPU 周期数（用于驱动 PPU/APU）
        """

    def nmi(self):
        """
        触发 NMI 中断：
        - 压栈 PC、P（B=0）
        - I = 1
        - PC = 从 0xFFFA-0xFFFB 读取 NMI 向量
        - 消耗 7 个周期
        """

    # 寄存器属性（只读，供调试用）
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

#### 2.1.7 CPU 测试方案

- **单元测试**：使用 nestest ROM（6502 功能测试 ROM）验证每条指令的正确性。nestest 会测试全部官方操作码并输出预期结果，与模拟器的日志对比即可发现错误。
- **测试方式**：`cpu.py` 可独立加载 nestest ROM，无需 PPU/APU 参与。与 nestest 的参考日志逐条比对 PC、A、X、Y、SP、P、周期数。

---

### 2.2 PPU（图像处理器） — `ppu.py`

#### 2.2.1 概述

模拟 Ricoh 2C02 PPU，采用**整帧一次性渲染**方式：CPU 执行完一帧的 29781 个周期后，PPU 一次性生成整帧 256×240 像素画面。

> **设计决策**（已与需求方确认）：不实现逐扫描线渲染（scanline-by-scanline），简化 PPU 设计与时序复杂度。代价：极少数依赖行级精确时序的边缘效果可能不正确，但对马里奥 1 代无实质影响。

#### 2.2.2 内存与数据区

| 存储区 | 大小 | 地址范围 | 说明 |
|--------|------|----------|------|
| VRAM (Nametable) | 2 KiB (2048 字节) | 0x2000–0x2FFF | 两个名称表（每表 960 字节 tile 索引 + 64 字节属性），镜像填充 |
| Palette RAM | 32 字节 | 0x3F00–0x3FFF | 8 组 4 字节调色板（背景 4 组 + 精灵 4 组） |
| OAM (Object Attribute Memory) | 256 字节 | 内部 | 64 个精灵条目（每条目 4 字节：Y, Tile, Attr, X） |
| Pattern Tables | 2 × 4096 字节 | 来自卡带 CHR ROM | 8×8 tile 的位图数据（每 tile 16 字节，2 个 bit-plane） |

#### 2.2.3 PPU 寄存器

PPU 通过 CPU 地址空间的 8 个映射地址访问：

| CPU 地址 | 名称 | 方向 | 说明 |
|----------|------|------|------|
| 0x2000 | PPUCTRL | 只写 | 控制寄存器（NMI 使能、名称表选择、VRAM 地址增量等） |
| 0x2001 | PPUMASK | 只写 | 掩码寄存器（显示背景、显示精灵、灰度模式等） |
| 0x2002 | PPUSTATUS | 只读 | 状态寄存器（VBlank 标志、Sprite 0 Hit、Sprite Overflow） |
| 0x2003 | OAMADDR | 只写 | OAM 地址指针（向 OAM 写数据前设置） |
| 0x2004 | OAMDATA | 读写 | OAM 数据端口（写入/读取精灵属性） |
| 0x2005 | PPUSCROLL | 只写×2 | 滚动寄存器（连续写 2 次：水平滚动 → 垂直滚动） |
| 0x2006 | PPUADDR | 只写×2 | VRAM 地址寄存器（连续写 2 次：高字节 → 低字节） |
| 0x2007 | PPUDATA | 读写 | VRAM 数据端口（读/写后地址自动递增） |

**写入机制实现要点**：
- PPUSCROLL 和 PPUADDR 使用内部**写锁存器（write latch / w 触发器）**，第 1 次写写入高字节，第 2 次写写入低字节。读取 PPUSTATUS 复位此锁存器。
- PPUSCROLL 的两字节设计细节：第一写 = 水平滚动细粒度 X (低 3 位 = fine X scroll) + 粗粒度 X（高 5 位），第二写 = 垂直滚动。

#### 2.2.4 画面渲染算法

由于采用**整帧一次性渲染**，PPU 不模拟逐扫描线的像素输出，而是在 `render_frame()` 被调用时根据当前 VRAM/OAM/寄存器状态一次性计算 256×240 像素：

```
render_frame():
    1. 从 PPUCTRL 和 PPUSCROLL 寄存器读出滚动的名称表基址和滚动偏移
    2. 按 Nametable → Pattern Table → Attribute Table → Palette 的层次
       绘制背景层（Background）：
       - 遍历屏幕 32×30 个 tile (每个 8×8 像素)
       - 根据滚动值确定起始 Tile 位置（考虑跨名称表边界）
       - 查名称表获取 tile 索引
       - 查属性表获取调色板组
       - 查 Pattern Table 获取 2 个 bit-plane 合成 2-bit 颜色索引
       - 查 Palette RAM 获取最终 RGB 颜色
    3. 绘制精灵层（Sprites）：
       - 遍历 OAM 64 个条目（4 字节/条）
       - 对每个活跃精灵，从 Pattern Table 取 tile 像素
       - 精灵优先级、水平/垂直翻转、背景遮挡逻辑
       - 精灵 0 Hit 检测：第 0 号精灵的非透明像素与背景非透明像素重叠时
         置 PPUSTATUS bit 6
    4. 合成：背景层 + 精灵层 → 256×240 像素数组
    5. 返回像素数组
```

**背景渲染细节**：

| 层级 | 说明 |
|------|------|
| Nametable | 32×30 字节，每字节为 tile 索引（指向 Pattern Table） |
| Attribute Table | 每字节覆盖 4×4 tile 区域（32×32 像素），指定该区域使用 4 组调色板中的哪一组 |
| Pattern Table | 每个 tile = 16 字节 = 2 planes × 8 字节，产生 8×8 像素的 2-bit 颜色索引 |
| 颜色索引合成 | `color_idx = (plane0 >> (7-x)) & 1 | ((plane1 >> (7-x)) & 1) << 1` |
| 通用背景色 | 颜色索引 0 → 调色板[0]（所有调色板组的 [0] 相同，为通用背景色） |

**精灵渲染细节**：

| 项 | 说明 |
|----|------|
| 条目数 | 64 个（马里奥 1 代实际使用远少于此数） |
| 每条目 | Y 坐标(1) + Tile 索引(1) + 属性(1) + X 坐标(1) = 4 字节 |
| 属性字节 | bit7=VFlip, bit6=HFlip, bit5=Behind BG, bits1-0=调色板组 |
| 精灵 0 Hit | 第 0 号精灵的非透明像素与背景非透明像素首次重叠时置 PPUSTATUS.6 |
| 精灵尺寸 | 由 PPUCTRL bit5 控制：8×8 或 8×16（马里奥 1 代使用 8×8） |

#### 2.2.5 调色板 → RGB 映射

FC 使用 64 色预设调色板（NES 系统调色板）。需内嵌完整 64 色的 RGB 值表。

```python
# NES 64 色调色板（部分举例）
SYSTEM_PALETTE = [
    (0x7C, 0x7C, 0x7C),  # 0x00 灰色
    (0x00, 0x00, 0xFC),  # 0x01 蓝色
    (0x00, 0x00, 0xBC),  # 0x02
    # ... 共 64 色
]
```

#### 2.2.6 PPU 核心接口

```python
class PPU:
    def __init__(self, cartridge: Cartridge):
        """初始化 PPU，从卡带获取 CHR ROM 数据"""

    def step(self, cpu_cycles: int):
        """
        推进 PPU 时间（帧级同步模式下仅用于追踪扫描线/周期计数，
        不实际逐行渲染）。主要用途：
        - 跟踪当前帧的周期数
        - 在 VBlank 起始时（第 241 条扫描线开始）触发 NMI
        - 在帧结束时（第 262 条扫描线结束）复位
        返回值：是否触发了 NMI（布尔），main.py 据此调用 cpu.nmi()
        """

    def render_frame(self) -> list[list[tuple[int,int,int]]]:
        """
        一次性渲染整帧。
        返回：256×240 像素的二维数组，每像素为 (R, G, B) 元组 (0-255)
        """

    # 寄存器读写（供 Bus 调用）
    def read_register(self, addr: int) -> int: ...
    def write_register(self, addr: int, value: int): ...

    # 存储器读写（供 Bus 调用，处理 0x2000–0x3FFF 地址）
    def read(self, addr: int) -> int: ...
    def write(self, addr: int, value: int): ...
```

#### 2.2.7 PPU 测试方案

- **单元测试**：构造已知的 VRAM/OAM/调色板状态，调用 `render_frame()`，检查输出像素数组的特定位置颜色是否与预期一致。
- **集成测试**：加载完整 ROM 后，截取标题画面、关卡开始画面，与参考截图进行视觉对比。
- **调试工具辅助**：通过 PPU 调试视图检查 Pattern Table 和调色板是否正确渲染，逐层排查花屏原因。

---

### 2.3 APU（音频处理器） — `apu.py`

#### 2.3.1 概述

模拟 FC 的音频子系统（2A03 芯片内置），包含 5 个声音通道。每帧结束时生成一帧时长的 PCM 音频样本，送入 Pygame mixer 播放。

> **设计决策**（已与需求方确认）：每帧生成一帧音频样本（约 735 样本 @ 44100Hz），而非大缓冲异步模式。延迟最小，对马里奥 1 代的简单音频场景足够。

#### 2.3.2 声音通道

| 编号 | 通道名称 | 产生的声音 | 说明 |
|------|----------|-----------|------|
| 1 | Pulse 1 (矩形波 1) | 旋律线 1 | 占空比可调 (12.5%/25%/50%/75%)，音量包络，频率扫描 |
| 2 | Pulse 2 (矩形波 2) | 旋律线 2 | 同 Pulse 1，无频率扫描 |
| 3 | Triangle (三角波) | 低音线 | 固定音量，无包络，无频率扫描 |
| 4 | Noise (噪声) | 鼓点、爆炸等打击音效 | 伪随机噪声生成器，音量包络 |
| 5 | DMC (Delta Modulation Channel) | 低质量采样播放 | 播放 delta 编码的 PCM 采样（马里奥 1 代可能轻度使用） |

> 马里奥 1 代的音频使用情况：Pulse 1 和 Pulse 2 承载主要旋律，Triangle 承载低音线，Noise 承载打击/音效噪声。DMC 在 1 代中使用极少（若使用则主要音效采样），需要实现基本功能。

#### 2.3.3 各通道参数

**Pulse 通道 (×2):**

| 参数 | 大小 | 说明 |
|------|------|------|
| 占空比 (Duty Cycle) | 2 bit | 00=12.5%, 01=25%, 10=50%, 11=75% |
| 包络 (Envelope) | 4 bit volume + envelope loop/constant 标志 | 控制音量衰减 |
| 频率 (Timer) | 11 bit | 控制音高 |
| 波长计数器 (Length Counter) | 5 bit | 音符持续时长 |
| 频率扫描 (Sweep) | 仅 Pulse 1 | 自动升高/降低频率 |

**Triangle 通道:**

| 参数 | 大小 | 说明 |
|------|------|------|
| 线性计数器 (Linear Counter) | 7 bit | 控制音量线性衰减 |
| 频率 (Timer) | 11 bit | 控制音高 |
| 波长计数器 (Length Counter) | 5 bit | 音符持续时长 |

**Noise 通道:**

| 参数 | 大小 | 说明 |
|------|------|------|
| 包络 (Envelope) | 4 bit | 同 Pulse 的包络 |
| 噪声周期 (Noise Period) | 4 bit | 控制噪声频率 |
| 模式 (Mode) | 1 bit | 0=长模式(32767 bit LFSR), 1=短模式(93 bit LFSR) |
| 波长计数器 (Length Counter) | 5 bit | 音符持续时长 |

**DMC 通道:**

| 参数 | 说明 |
|------|------|
| 采样速率 (Rate) | 控制回放频率 |
| 直接加载 (Direct Load) | 7 bit 直接音量值 |
| 采样地址/长度 | 指定要播放的 PCM 数据区域 |
| 输出单元 (Output Unit) | 7 bit 计数器，delta 解码 |

#### 2.3.4 APU 寄存器

APU 寄存器映射在 CPU 地址空间 0x4000–0x4017（部分地址与手柄共用）：

| 地址 | 寄存器 | 所属通道 |
|------|--------|----------|
| 0x4000 | SQ1_VOL | Pulse 1 — 占空比/包络 |
| 0x4001 | SQ1_SWEEP | Pulse 1 — 频率扫描 |
| 0x4002 | SQ1_LO | Pulse 1 — 频率低 8 位 |
| 0x4003 | SQ1_HI | Pulse 1 — 频率高 3 位 + 波长计数 |
| 0x4004 | SQ2_VOL | Pulse 2 — 占空比/包络 |
| 0x4005 | SQ2_SWEEP | Pulse 2 — 频率扫描 |
| 0x4006 | SQ2_LO | Pulse 2 — 频率低 8 位 |
| 0x4007 | SQ2_HI | Pulse 2 — 频率高 3 位 + 波长计数 |
| 0x4008 | TRI_LINEAR | Triangle — 线性计数器 |
| 0x400A | TRI_LO | Triangle — 频率低 8 位 |
| 0x400B | TRI_HI | Triangle — 频率高 3 位 + 波长计数 |
| 0x400C | NOISE_VOL | Noise — 包络 |
| 0x400E | NOISE_LO | Noise — 噪声周期/模式 |
| 0x400F | NOISE_HI | Noise — 波长计数 |
| 0x4010 | DMC_FREQ | DMC — 速率 |
| 0x4011 | DMC_RAW | DMC — 直接加载 |
| 0x4012 | DMC_START | DMC — 采样地址 |
| 0x4013 | DMC_LEN | DMC — 采样长度 |
| 0x4015 | SND_CHN | APU 状态/通道使能 |
| 0x4017 | FRAME_COUNTER | 帧计数器模式 |

#### 2.3.5 帧计数器（Frame Counter）

APU 内部有一个帧计数器（Frame Counter），以 CPU 周期为单位产生"APU 帧"（不是视频帧）：

| 模式 | 序列 | 周期 | 说明 |
|------|------|------|------|
| 4-step（默认） | 3728.5 → 7457 → 11185.5 → 14914 CPU 周期 | 约 240 Hz | 驱动包络、波长计数器、频率扫描 |
| 5-step | 同 4-step 前 4 步 + 18640.5 | 由 0x4017 bit7=1 启用 |

每次帧计数器步进时：更新包络、更新频率扫描、递减波长计数器。

#### 2.3.6 音频样本生成

```python
def get_audio_samples(self) -> list[int]:
    """
    生成一帧时长的音频样本。

    计算：
    - 一帧视频 = 1/60 秒 ≈ 16.67 ms
    - 采样率 = 44100 Hz
    - 每帧样本数 = 44100 / 60 ≈ 735 样本（精确值：取整处理）

    对每一帧内的每个采样点：
    1. 将 APU 推进 sample_step = CPU_CLOCK / 44100 个 CPU 周期
       (CPU_CLOCK ≈ 1789773 Hz)
    2. 更新各通道状态（包络、频率扫描、波长计数）
    3. 混合 5 个通道的输出值
       - Pulse: 根据占空比查当前波形位置的值 (0 或 1)，乘以当前音量
       - Triangle: 三角波查表（32 步），乘以固定音量
       - Noise: LFSR bit 0，乘以当前音量
       - DMC: 输出单元 bit 6（若 DMC 激活）
    4. 混合公式（简单平均）:
       output = (pulse1 + pulse2) * pulse_ratio
              + triangle * tri_ratio
              + noise * noise_ratio
              + dmc * dmc_ratio
       推荐权重：pulse_ratio=0.3, tri_ratio=0.3, noise_ratio=0.2, dmc_ratio=0.2
    5. 缩放为 16 bit PCM（-32768 ~ 32767）

    返回：PCM 16-bit 有符号整数列表，长度为 735（约）
    """
```

#### 2.3.7 APU 核心接口

```python
class APU:
    def __init__(self):
        """初始化 5 个声音通道的默认状态"""

    def step(self, cpu_cycles: int):
        """
        推进 APU 时间（帧级同步模式下，主要用于驱动帧计数器）。
        """

    def get_audio_samples(self) -> list[int]:
        """
        生成当前帧的音频样本。
        应在 CPU 执行完一整帧后调用。
        返回：PCM 16-bit 有符号整数列表。
        """

    # 寄存器读写（供 Bus 调用）
    def read_register(self, addr: int) -> int: ...
    def write_register(self, addr: int, value: int): ...
```

#### 2.3.8 APU 测试方案

- **单元测试**：逐通道测试。向 Pulse 1 寄存器写入已知值，检查输出波形是否符合预期频率和占空比。
- **集成测试**：运行游戏，人工聆听标题画面背景音乐与跳跃/吃金币音效是否正常。
- **已知参考**：马里奥 1 代标题画面 BGM 的旋律广为人知，听感对比即可确认 APU 正确性。

---

### 2.4 Bus（总线 / 地址空间） — `bus.py`

#### 2.4.1 概述

模拟 FC 的 16 位地址总线，接收 CPU 的读写请求，根据地址范围路由到对应设备。

#### 2.4.2 内存映射（完整地址空间）

| 地址范围 | 大小 | 映射到 | 说明 |
|----------|------|--------|------|
| 0x0000–0x07FF | 2 KiB | CPU RAM | 内部工作内存（含零页 0x0000–0x00FF 和栈 0x0100–0x01FF） |
| 0x0800–0x1FFF | — | CPU RAM 镜像 | 0x0000–0x07FF 的镜像（每 2 KiB 重复一次） |
| 0x2000–0x2007 | 8 字节 | PPU 寄存器 | PPUCTRL 等 8 个寄存器 |
| 0x2008–0x3FFF | — | PPU 寄存器镜像 | 0x2000–0x2007 每 8 字节重复 |
| 0x4000–0x4017 | 24 字节 | APU/OAMDMA/手柄 | APU 寄存器 + OAM DMA (0x4014) + 手柄端口 (0x4016, 0x4017) |
| 0x4018–0x401F | — | (禁用/测试) | CPU 测试模式，通常不实现 |
| 0x4020–0xFFFF | — | 卡带 (Mapper 0) | 由 Cartridge 模块处理：PRG ROM (0x8000–0xFFFF 或 0xC000–0xFFFF) + 可选 PRG RAM |

#### 2.4.3 OAM DMA

向 0x4014 写入值时触发 OAM DMA：将 CPU 内存中 `value << 8` 地址起的 256 字节复制到 PPU 的 OAM。该操作消耗 513 个 CPU 周期（等待 1 周期 + 256 次读写 × 2 周期）。

```python
# Bus.write() 中的处理：
if addr == 0x4014:
    dma_page = value
    dma_addr = dma_page << 8
    for i in range(256):
        ppu.oam_write(i, self.read(dma_addr + i))
    # 返回 513 CPU 周期（奇数周期对齐：514 或 513 取决于 CPU 周期奇偶性）
```

#### 2.4.4 Bus 核心接口

```python
class Bus:
    def __init__(self, cpu_ram: RAM, ppu: PPU, apu: APU,
                 cartridge: Cartridge, input: Input):
        """持有所有设备的引用，负责路由读写"""

    def read(self, addr: int, from_ppu: bool = False) -> int:
        """
        从地址 addr 读取 1 字节。
        from_ppu: 是否来自 PPU 的读请求（影响 cartridge.ppu_read 路由）
        返回：0–255
        """

    def write(self, addr: int, value: int):
        """向地址 addr 写入 1 字节"""
```

#### 2.4.5 Bus 测试方案

- **单元测试**：构造 mock 设备注入 Bus，验证地址路由正确性（如 0x0000 写到 RAM、0x2000 路由到 PPU 寄存器等）。
- **集成测试**：与 CPU 一起用 nestest ROM 测试。

---

### 2.5 Cartridge（卡带 / Mapper 0） — `cartridge.py`

#### 2.5.1 概述

解析 iNES 格式 (.nes) ROM 文件，仅实现 **NROM (Mapper 0)**。提供卡带侧的内存读写接口。

#### 2.5.2 iNES 文件格式

| 偏移 | 大小 | 内容 |
|------|------|------|
| 0x00 | 4 字节 | 魔术数 "NES" + 0x1A |
| 0x04 | 1 字节 | PRG ROM 大小（16 KiB 为单位） |
| 0x05 | 1 字节 | CHR ROM 大小（8 KiB 为单位） |
| 0x06 | 1 字节 | Flags 6（Mapper 号低 4 位、镜像模式等） |
| 0x07 | 1 字节 | Flags 7（Mapper 号高 4 位） |
| 0x08 | 8 字节 | 保留 / PRG RAM 大小等 |
| 0x10 | 可变 | 训练器 (Trainer)（若 Flags 6 bit2=1，512 字节，NROM 通常没有） |
| ... | PRG_ROM_SIZE × 16384 | PRG ROM 数据 |
| ... | CHR_ROM_SIZE × 8192 | CHR ROM 数据（若为 0 则使用 CHR RAM） |

#### 2.5.3 NROM (Mapper 0) 行为

**CPU 地址空间 (0x4020–0xFFFF):**

| PRG ROM 大小 | 映射行为 |
|-------------|----------|
| 16 KiB (PRG_ROM_SIZE = 1) | 0x8000–0xBFFF = PRG ROM；0xC000–0xFFFF = 镜像（重复映射） |
| 32 KiB (PRG_ROM_SIZE = 2) | 0x8000–0xFFFF = 连续 32 KiB PRG ROM |

> 马里奥 1 代的 PRG ROM 为 32 KiB，直接映射 0x8000–0xFFFF。

**PPU 地址空间 (0x0000–0x1FFF):**

| CHR ROM 大小 | 映射行为 |
|-------------|----------|
| 8 KiB (CHR_ROM_SIZE = 1) | 直接映射到 Pattern Table 0 (0x0000–0x0FFF) 和 Table 1 (0x1000–0x1FFF) |
| 0 KiB (CHR_ROM_SIZE = 0) | 使用 CHR RAM（8 KiB 可写 RAM，模拟器需分配） |

> 马里奥 1 代使用 8 KiB CHR ROM。

**镜像模式 (Nametable Mirroring):**

| 模式 | 说明 | 行为 |
|------|------|------|
| Horizontal | 水平镜像（iNES flags 6 bit0=0） | NT0=NT0, NT1=NT0, NT2=NT1, NT3=NT1 |
| Vertical | 垂直镜像（iNES flags 6 bit0=1） | NT0=NT0, NT1=NT1, NT2=NT0, NT3=NT1 |

> 马里奥 1 代使用**垂直镜像 (Vertical Mirroring)**。

#### 2.5.4 Cartridge 核心接口

```python
class Cartridge:
    def __init__(self):
        """创建空卡带对象"""

    @staticmethod
    def load(filepath: str) -> Cartridge:
        """
        从 .nes 文件加载。
        步骤：
        1. 读取文件头 16 字节，验证魔术数
        2. 检查 Mapper 号 = 0，否则抛出异常
        3. 读取 PRG ROM 和 CHR ROM 数据
        4. 根据 Flags 6 确定镜像模式
        5. 返回 Cartridge 实例
        """

    def cpu_read(self, addr: int) -> int:
        """
        CPU 侧读卡带（addr: 0x4020–0xFFFF）。
        - PRG ROM 区域：映射返回 ROM 数据
        - 未映射区域：返回 0
        """

    def cpu_write(self, addr: int, value: int):
        """
        CPU 侧写卡带。
        NROM 的 PRG ROM 是只读的 → 忽略写入。
        （若有 PRG RAM [少见]，在此处理）
        """

    def ppu_read(self, addr: int) -> int:
        """
        PPU 侧读卡带（addr: 0x0000–0x1FFF）。
        - CHR ROM → 返回 ROM 数据
        - CHR RAM → 返回 RAM 数据
        """

    def ppu_write(self, addr: int, value: int):
        """
        PPU 侧写卡带。
        - CHR RAM 模式 → 写入 RAM
        - CHR ROM 模式 → 忽略
        """

    @property
    def mirroring(self) -> str:
        """返回 'horizontal' 或 'vertical'"""

    @property
    def prg_rom(self) -> bytes: ...

    @property
    def chr_rom(self) -> bytes | None: ...
```

#### 2.5.5 Cartridge 测试方案

- **单元测试**：构造合法的 iNES 最小文件（16 字节头 + 任意 PRG/CHR 数据），测试 load() 的解析结果。
- **格式校验测试**：测试非法魔术数、非 Mapper 0 文件应抛出异常。
- **映射测试**：验证 PRG ROM 地址映射和镜像逻辑的 math 正确性。

---

### 2.6 RAM（内存） — `ram.py`

#### 2.6.1 概述

CPU 内部 RAM（2 KiB，地址 0x0000–0x07FF），为最简单的存储器模块。

#### 2.6.2 设计

```python
class RAM:
    def __init__(self, size: int = 2048):
        """分配 size 字节的内置数组，初始化为 0"""
        self._data = bytearray(size)

    def read(self, addr: int) -> int:
        """读取 addr 处的 1 字节。地址自动镜像（addr % size）"""
        return self._data[addr % len(self._data)]

    def write(self, addr: int, value: int):
        """写入 value 到 addr。地址自动镜像"""
        self._data[addr % len(self._data)] = value & 0xFF
```

> 此处 RAM 仅指 CPU 内部内存（0x0000–0x07FF）。PPU 的 VRAM 和 OAM 内嵌在 PPU 模块中，不由 RAM 模块管理。

#### 2.6.3 RAM 测试方案

- **单元测试**：基本的读写-验证循环 + 地址镜像验证。最简单，几乎不会出错。

---

### 2.7 Input（输入） — `input.py`

#### 2.7.1 概述

通过 Pygame 事件系统读取键盘状态，映射到 FC 手柄的 8 个按钮，模拟 FC 手柄端口的读取行为。

#### 2.7.2 键盘映射（硬编码默认值）

```python
KEY_MAPPING = {
    pygame.K_UP:     0,  # FC 方向 上
    pygame.K_DOWN:   1,  # FC 方向 下
    pygame.K_LEFT:   2,  # FC 方向 左
    pygame.K_RIGHT:  3,  # FC 方向 右
    pygame.K_k:      4,  # A 按钮（跳跃）
    pygame.K_j:      5,  # B 按钮（加速/火球）
    pygame.K_RETURN: 6,  # Start
    pygame.K_RSHIFT: 7,  # Select
}
```

#### 2.7.3 FC 手柄端口读取机制

FC 通过以下方式读取手柄状态：

1. 向 0x4016 写 1 再写 0 → **锁存**（latch）当前按钮状态到内部移位寄存器
2. 从 0x4016 反复读取 → 每次读返回一个按钮的当前状态（bit 0），按 A→B→Select→Start→↑→↓→←→→ 的顺序移出
3. 第 9 次及之后读取返回 1（表示手柄已读完）

```python
class Input:
    def __init__(self):
        self._buttons = [0] * 8  # 8 个按钮的当前状态 (0=松开, 1=按下)
        self._latch = 0
        self._read_index = 0

    def poll(self):
        """
        调用 pygame.event.get() 处理事件，
        根据 KEY_MAPPING 更新 self._buttons。
        不处理的事件重新放回队列。
        """

    def write(self, value: int):
        """
        模拟向 0x4016 写入。
        - value 的 bit 0 = 1 → 锁存当前按钮状态
        - value 的 bit 0 = 0 → 结束锁存，准备读取
        """

    def read(self) -> int:
        """
        模拟从 0x4016 读取。
        返回当前移位寄存器位 | 0x40（标准手柄额外位）
        bit0 = 按钮值, bit1-4 = 0, bit5-7 = 从高地址线来的开放总线值
        """

    def get_state(self) -> list[int]:
        """返回当前 8 个按钮的状态，供调试窗口使用"""
```

#### 2.7.4 Input 测试方案

- **单元测试**：模拟 Pygame 事件 → poll() → 检查 get_state() 与预期一致。
- **移位寄存器测试**：模拟锁存 → 多次读取 → 验证读出的按钮序列与 A/B/Select/Start/↑/↓/←/→ 顺序匹配。
- **集成测试**：运行游戏，按键操控马里奥移动/跳跃，确认响应正确。

---

### 2.8 UI（显示窗口） — `ui.py`

#### 2.8.1 概述

使用 Pygame 创建游戏窗口，接收 PPU 渲染的 256×240 像素数组，按固定整数倍放大显示。控制帧率接近 60 FPS。

#### 2.8.2 窗口配置

```python
SCALE_FACTOR = 2  # 默认 2 倍 -> 512×480 窗口
NATIVE_WIDTH = 256
NATIVE_HEIGHT = 240
WINDOW_WIDTH = NATIVE_WIDTH * SCALE_FACTOR   # 512
WINDOW_HEIGHT = NATIVE_HEIGHT * SCALE_FACTOR  # 480
FPS_TARGET = 60.0988  # FC NTSC 实际帧率：约 60.1 Hz
```

#### 2.8.3 渲染流程

```python
class UI:
    def __init__(self, scale: int = 3):
        """
        初始化 Pygame 显示窗口。
        - 创建窗口：pygame.display.set_mode(768, 720)
        - 设置窗口标题
        - 创建内部 Surface(256, 240) 用于绘制原始像素
        """

    def render(self, pixels: list[list[tuple[int,int,int]]]):
        """
        将 256×240 像素数组绘制到窗口：
        1. 逐像素写入内部 256×240 Surface
        2. pygame.transform.scale() 放大到窗口尺寸
        3. pygame.display.flip() 刷新显示
        """

    def handle_events(self) -> bool:
        """
        处理窗口事件。
        返回：是否应退出 (True = 退出)
        - QUIT 事件 → 返回 True
        - 按键事件 → 放回队列供 Input.poll() 处理
        """

    def tick(self):
        """限制帧率：pygame.time.Clock().tick(FPS_TARGET)"""
```

#### 2.8.4 UI 测试方案

- 人工验证：画面是否正常显示、缩放是否像素级清晰、窗口关闭是否正常。
- FPS 验证：在调试窗口中查看实际帧率是否接近 60。

---

### 2.9 Debug（调试工具） — `debug.py`

#### 2.9.1 概述

独立的 Pygame 调试窗口，显示 CPU 状态、内存内容、PPU 调色板/Pattern Table 等调试信息。与游戏窗口并行运行。

> **设计决策**（已与需求方确认）：使用独立 Pygame 窗口，而非叠加层或纯控制台输出。

#### 2.9.2 调试功能清单

| 功能 | 显示区域 | 说明 | 优先级 |
|------|----------|------|--------|
| CPU 寄存器 | 窗口左上区 | A, X, Y, PC, SP, P (含各标志位展开) | 必须 |
| 运行信息 | 窗口右上区 | FPS、运行/暂停状态、当前帧号 | 必须 |
| 内存查看 | 窗口左中区 | 可滚动查看指定地址区间的内存 hex dump (16 字节/行) | 必须 |
| PPU Pattern Table | 窗口右区 | 两个 Pattern Table 的可视化缩略图 (128×128 像素各) | 可选（需求标注为可选，推荐实现） |
| PPU 调色板 | 窗口右区下方 | 32 个调色板色块展示 | 可选 |
| 单步/帧步进 | 键盘控制 | F5=暂停/继续, F6=帧步进(暂停时), F7=指令步进(暂停时) | 必须 |

#### 2.9.3 调试窗口布局（建议）

```
┌───────────────────── 调试窗口 (640×480) ─────────────────────┐
│ CPU Registers          │ FPS: 60.1  Frame: 12345  [PAUSED]   │
│ A: 0x05  X: 0x00      │                                     │
│ Y: 0x00  PC: 0xC123   │                                     │
│ SP: 0xFD               │                                     │
│ P: NV-BDIZC            │                                     │
│   10110001             │                                     │
├────────────────────────┼─────────────────────────────────────┤
│ Memory View [0x0000]   │ Pattern Table 0     Pattern Table 1 │
│ 0000: 00 01 02 03 ...  │ ░░▓▓░░▓▓  ...       ▓▓▓▓▓░░░  ...   │
│ 0010: FF EE DD CC ...  │                                     │
│ ...                    │                                     │
│ [↑/↓ 翻页] [PgUp/PgDn]│                                     │
├────────────────────────┴─────────────────────────────────────┤
│ Palette                                                  │
│ BG0: ■ ■ ■ ■  BG1: ■ ■ ■ ■  BG2: ■ ■ ■ ■  BG3: ■ ■ ■ ■ │
│ SP0: ■ ■ ■ ■  SP1: ■ ■ ■ ■  SP2: ■ ■ ■ ■  SP3: ■ ■ ■ ■ │
├──────────────────────────────────────────────────────────────┤
│ F5=Pause/Continue  F6=Frame Step  F7=Instruction Step       │
│ F1=Mem Start+0x100  F2=Mem Start-0x100                      │
└──────────────────────────────────────────────────────────────┘
```

#### 2.9.4 调试窗口核心接口

```python
class DebugWindow:
    def __init__(self, cpu: CPU, ppu: PPU, bus: Bus, input: Input):
        """
        创建 640×480 独立 Pygame 窗口。
        持有各模块引用以读取调试数据。
        """

    def update(self):
        """刷新调试窗口内部的 CPU/内存/PPU 数据缓存"""

    def render(self):
        """
        渲染调试窗口内容：
        - CPU 寄存器值
        - 运行状态信息
        - 内存 hex dump
        - Pattern Table 可视化
        - 调色板色块
        - 底部控制提示
        """

    def handle_input(self) -> dict:
        """
        处理调试窗口的键盘事件（仅处理调试快捷键）。
        返回：控制命令 dict，如 {'action': 'pause', 'step': 'frame'}
        不处理游戏按键（放回队列）。
        """
```

#### 2.9.5 调试控制键盘快捷键

| 按键 | 功能 |
|------|------|
| F5 | 暂停 / 继续运行 |
| F6 | 帧步进（仅在暂停状态下有效） |
| F7 | 指令步进（仅在暂停状态下有效） |
| F1 | 内存查看起始地址 +0x100 |
| F2 | 内存查看起始地址 -0x100 |
| ↑/↓ | 内存查看滚动（每次 ±0x10） |
| PgUp/PgDn | 内存查看翻页（每次 ±0x100） |

#### 2.9.6 调试窗口测试方案

- 人工验证：启动模拟器，按 F5 确认暂停/继续功能；暂停后按 F6 确认逐帧步进；检查寄存器值与预期一致。
- 内存查看测试：对比已知 ROM 数据区域，确认 hex dump 显示正确。
- Pattern Table 显示测试：对比马里奥 1 代的 Pattern Table 参考图。

---

### 2.10 Main（主程序） — `main.py`

#### 2.10.1 概述

程序入口，串联所有模块，实现主帧循环。解析命令行参数。

#### 2.10.2 命令行参数

```
python main.py <rom_file> [--scale N] [--debug]

参数：
  rom_file     : （必填）.nes ROM 文件路径
  --scale N    : （可选）画面放大倍数，默认 3，范围 1–5
  --debug      : （可选）启用调试窗口
```

#### 2.10.3 初始化流程

```python
def main():
    # 1. 解析命令行参数
    args = parse_args()

    # 2. 创建各模块实例
    cartridge = Cartridge.load(args.rom_file)
    ram = RAM(2048)
    ppu = PPU(cartridge)
    apu = APU()
    input_dev = Input()
    bus = Bus(ram, ppu, apu, cartridge, input_dev)
    cpu = CPU(bus)

    # 3. 初始化 UI
    ui = UI(scale=args.scale)
    debug = DebugWindow(cpu, ppu, bus, input_dev) if args.debug else None

    # 4. 初始化音频
    pygame.mixer.init(frequency=44100, size=-16, channels=1)

    # 5. 复位
    cpu.reset()

    # 6. 进入主循环
    run_loop(cpu, ppu, apu, bus, input_dev, ui, debug)
```

#### 2.10.4 主循环流程

```python
FRAME_CPU_CYCLES = 29781  # NTSC NES 一帧的 CPU 周期数

def run_loop(cpu, ppu, apu, bus, input_dev, ui, debug):
    running = True
    paused = False
    step_mode = None  # None | 'frame' | 'instruction'

    while running:
        # 1. 处理事件
        quit_requested = ui.handle_events()
        if quit_requested:
            running = False
            break
        input_dev.poll()

        # 2. 处理调试命令
        if debug:
            cmd = debug.handle_input()
            if cmd.get('action') == 'pause':
                paused = not paused
            elif cmd.get('action') == 'step':
                if cmd['step'] == 'frame':
                    step_mode = 'frame'
                    paused = False  # 临时解冻跑一帧
                elif cmd['step'] == 'instruction':
                    step_mode = 'instruction'
                    paused = False  # 临时解冻跑一条指令

        # 3. CPU 执行
        if not paused:
            cycles_this_frame = 0
            nmi_triggered = False

            while cycles_this_frame < FRAME_CPU_CYCLES:
                cycles = cpu.step()
                cycles_this_frame += cycles

                # 驱动 PPU
                nmi = ppu.step(cycles)
                if nmi:
                    cpu.nmi()

                # 驱动 APU
                apu.step(cycles)

                # 指令步进处理
                if step_mode == 'instruction':
                    step_mode = None
                    paused = True
                    break

            # 帧步进处理
            if step_mode == 'frame':
                step_mode = None
                paused = True

        # 4. 渲染画面
        pixels = ppu.render_frame()
        ui.render(pixels)

        # 5. 播放音频
        audio_samples = apu.get_audio_samples()
        sound = pygame.sndarray.make_sound(np.array(audio_samples, dtype=np.int16))
        sound.play()

        # 6. 更新调试窗口
        if debug:
            debug.update()
            debug.render()

        # 7. 帧率控制
        ui.tick()

    pygame.quit()
```

#### 2.10.5 帧级同步的时序说明

由于采用帧级同步策略，主循环的每个迭代就是完整的一帧：

1. CPU 连续执行 29781 个周期（约 29,781 × 3 ≈ 89,343 PPU 周期）
2. PPU 在 CPU 执行期间被驱动（主要是 VBlank 检测 → 触发 NMI）
3. 整帧 CPU 指令执行完毕后，PPU 一次性渲染整帧画面
4. APU 一次性生成整帧音频样本

**优点**：实现简单，逻辑清晰，不需要复杂的 cycle-stepping 同步机制。
**缺点**：无法模拟行级精度效果，但马里奥 1 代不受影响。

#### 2.10.6 Main 测试方案

- **冒烟测试**：加载 ROM → 启动 → 确认窗口出现、画面显示、无崩溃。
- **验收测试**：逐一对照需求文档 2.1 节验收标准。
- **性能测试**：在调试窗口中观察 FPS，确保接近 60。

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
├── debug.py             # 调试窗口（可选启用）
├── palette.py           # NES 64 色调色板常量
├── requirements.txt     # 依赖列表
├── doc/
│   ├── SUPER MARIO.md   # 需求文档
│   └── detailed-design.md  # 本详细设计文档
└── tests/
    ├── test_cpu.py      # CPU 测试（含 nestest）
    ├── test_ppu.py      # PPU 测试
    ├── test_apu.py      # APU 测试
    ├── test_bus.py      # Bus 测试
    ├── test_cartridge.py   # 卡带测试
    ├── test_ram.py      # RAM 测试
    ├── test_input.py    # Input 测试
    └── test_integration.py  # 集成测试
```

---

## 4. 依赖

`requirements.txt`:
```
pygame>=2.5.0
numpy>=1.24.0
```

| 依赖 | 用途 |
|------|------|
| pygame | 图形窗口、事件处理、音频输出 (mixer/sndarray) |
| numpy | `pygame.sndarray.make_sound()` 需要 numpy 数组作为输入 |

---

## 5. 模块间接口总结

### 5.1 CPU ← → 其他模块（通过 Bus）

```
CPU ──read(addr)──→ Bus ──→ RAM / PPU / APU / Cartridge / Input
CPU ──write(addr, val)──→ Bus ──→ RAM / PPU / APU / Cartridge / Input
CPU ←──NMI 信号──── PPU (通过 main.py 中转: ppu.step() 返回 True → cpu.nmi())
```

### 5.2 PPU ← → 其他模块

```
PPU ──read(addr)──→ Bus ──→ Cartridge (CHR ROM / VRAM)
PPU ←──写入数据──── Bus (CPU 通过 PPU 寄存器写入)
PPU → render_frame() → 256×240 像素数组 → UI
PPU.step(cycles) → bool(触发 NMI?) → main.py → cpu.nmi()
```

### 5.3 APU ← → 其他模块

```
APU ←──寄存器写入── Bus (CPU 通过 APU 寄存器写入)
APU.step(cycles) → 内部状态更新
APU → get_audio_samples() → PCM 样本列表 → main.py → pygame.mixer
```

### 5.4 数据流方向

```
输入: Input (键盘) → Bus.read(0x4016) → CPU → 影响游戏逻辑
输出:
  ├─ 视频: PPU.render_frame() → UI.render() → Pygame 窗口
  ├─ 音频: APU.get_audio_samples() → pygame.mixer 播放
  └─ 调试: Debug.update() → Debug.render() → 独立调试窗口
```

---

## 6. 开发阶段建议

依据需求文档第 7 章建议，结合模块间的依赖关系：

| 阶段 | 模块 | 原因 | 可独立测试？ |
|------|------|------|-------------|
| **Phase 1** | RAM + Cartridge + Bus + CPU | CPU 是最核心部件，Cartridge/Bus/RAM 是其必需依赖 | CPU 可用 nestest ROM 独立测试，无需 PPU/APU |
| **Phase 2** | PPU + UI + palette | 画面显示，依赖 Cartridge (CHR ROM) 和 Bus (寄存器读写) | 可通过写测试脚本验证渲染输出 |
| **Phase 3** | APU | 音频，相对独立（仅依赖 Bus 的寄存器读写） | 可单独写寄存器 → 生成样本 → 播放验证 |
| **Phase 4** | Input | 键盘输入，依赖 Pygame 事件 + Bus | 可在 Phase 2 之后与 PPU/UI 联调 |
| **Phase 5** | Debug | 调试工具，依赖所有模块的只读访问 | 最后实现，此时其他模块已稳定 |
| **Phase 6** | main.py 联调 + 集成测试 | 全部模块串联 + 性能调优 + 验收 | 运行完整游戏验证 |

---

## 7. 关键未决项（需进一步确认）

以下事项在本详细设计中仍存在不确定性，请在开发前确认：

| # | 问题 | 影响模块 | 建议方案 |
|---|------|----------|----------|
| 1 | 缩放倍率默认值（2 倍 vs 3 倍）？ | UI | 建议 3 倍 (768×720)，适合 1080p 屏幕 |
| 2 | DMC 通道实现到什么程度？（马里奥 1 代 DMC 使用极少） | APU | 建议实现基本框架（寄存器读写 + 简单输出），若调试发现 BGM/音效缺失再完善 |
| 3 | 调试窗口是否需要始终显示，还是可关闭/重新打开？ | Debug | 建议默认开启时始终显示，关闭可通过关闭窗口实现 |
| 4 | 是否需要日志功能（将 CPU 指令执行记录到文件）？ | CPU/Debug | nestest 验证阶段肯定需要；运行游戏阶段非必须但有助于排错 |

---

*（本文档基于需求文档 doc/SUPER MARIO.md v1.0 与 2026-06-18 的需求方确认编写。后续需求变更请同步更新本文档的版本号与对应章节。）*
