# PPU 模块 — 任务列表

> 模块文件：`ppu.py`
> 依赖：Cartridge（CHR ROM）、palette.py（系统调色板）
> 可独立测试：✅ 是（构造 VRAM/OAM 状态后测试 render_frame）

---

## 任务清单

### Phase 1 — 数据区与寄存器

- [ ] **1.1 创建 PPU 类骨架 + 内部存储**
  - 文件：`ppu.py`
  - `__init__(cartridge)`：
    - 分配 VRAM：`bytearray(2048)`（Nametable，实际只用到 2 个 1 KiB 表）
    - 分配 Palette RAM：`bytearray(32)`
    - 分配 OAM：`bytearray(256)`（64 条目 × 4 字节）
    - 辅助内部分配：`bytearray(256)` 用于 OAM 二次数据（sprite evaluation）
    - 保存 cartridge 引用（访问 CHR ROM / mirroring）
  - 预计代码量：~25 行

- [ ] **1.2 定义 PPU 内部跟踪变量**
  - `_cycle` → 当前帧内周期计数（0–340）
  - `_scanline` → 当前扫描线（0–261，共 262 行）
  - `_frame` → 累计帧号
  - `_nmi_occurred`, `_nmi_enabled` → NMI 相关
  - 预计代码量：~10 行

- [ ] **1.3 实现 VRAM 读写**
  - `read(addr)` → 0x2000–0x2FFF 范围内的地址映射到 VRAM（含镜像）
  - `write(addr, value)` → 同上
  - Nametable 镜像由 Cartridge.mirroring 决定
  - 预计代码量：~30 行

- [ ] **1.4 实现 PPU 寄存器**
  - PPUCTRL (0x2000 只写)：NMI 使能、PPU 主/从选择、精灵大小、背景/精灵 Pattern Table 选择、名称表基址、VRAM 地址增量
  - PPUMASK (0x2001 只写)：灰度、显示背景左 8 列、显示精灵左 8 列、显示背景、显示精灵、强调色
  - PPUSTATUS (0x2002 只读)：VBlank、Sprite 0 Hit、Sprite Overflow；读后清 VBlank 且复位写锁存器
  - 预计代码量：~25 行

- [ ] **1.5 实现 PPU 地址与滚动寄存器**
  - PPUSCROLL (0x2005 只写×2)：
    - 写锁存器（w 触发器）：第 1 次写 = hori scroll，第 2 次写 = vert scroll
    - 存储 `_scroll_x`（0–511）、`_scroll_y`（0–479，含 fine Y）
  - PPUADDR (0x2006 只写×2)：
    - 写锁存器：第 1 次写 = 高字节（bit 6–7 为 0，地址空间 0x0000–0x3FFF），第 2 次写 = 低字节
    - 存储 `_vram_addr`（15 bit 有效，0x0000–0x3FFF）
  - PPUDATA (0x2007 读写)：
    - 读：返回 VRAM[_vram_addr] 的缓冲值（读 buffer 延迟 1 次）
    - 写：写入 VRAM[_vram_addr]
    - 读/写后 `_vram_addr += increment`（PPUCTRL bit2：1 或 32）
  - 预计代码量：~40 行

- [ ] **1.6 实现 OAM 相关寄存器**
  - OAMADDR (0x2003 只写)：设置 OAM 地址指针 `_oam_addr`
  - OAMDATA (0x2004 读写)：
    - 读：`OAM[_oam_addr]`
    - 写：`OAM[_oam_addr] = value; _oam_addr = (_oam_addr + 1) & 0xFF`
  - `oam_write(index, value)` → 供 Bus 的 OAM DMA 调用
  - 预计代码量：~15 行

### Phase 2 — 时序与帧驱动

- [ ] **2.1 实现 `step(cpu_cycles)`**
  - PPU 每 CPU 周期跑 3 PPU 周期
  - 追踪 `_cycle` 和 `_scanline`
  - VBlank 标志管理：
    - 扫描线 241-261 → VBlank 期间（PPUSTATUS bit7 = 1）
    - 扫描线 261 结束时 → 清除 VBlank, Sprite 0 Hit, Sprite Overflow
    - 扫描线 0 开始新帧
  - NMI 触发：扫描线 241 周期 1 时，若 PPUCTRL bit7 (NMI enable) = 1，返回 True
  - 预计代码量：~35 行

- [ ] **2.2 扫描线与周期范围常量**
  - `VISIBLE_SCANLINES = (0, 239)` → 可见行
  - `POST_RENDER = 240` → 后渲染行
  - `VBLANK_START = 241` → VBlank 开始行
  - `VBLANK_END = 260` → VBlank 结束行
  - `PRE_RENDER = 261` → 预渲染行
  - `CYCLES_PER_SCANLINE = 341`
  - `TOTAL_SCANLINES = 262`
  - 预计代码量：~8 行

### Phase 3 — 整帧渲染

- [ ] **3.1 实现背景层渲染**
  - `render_frame()` 中：
    - 确定当前滚动偏移 `_scroll_x`, `_scroll_y`
    - 确定名称表索引 `nt_base = PPUCTRL bits 0-1` 决定的基址（0x2000/0x2400/0x2800/0x2C00）
    - 遍历屏幕 256×240 像素，每 8×8 tile：
      - 计算该 tile 在 Nametable 中的坐标（考虑滚动）
      - 处理水平跨名称表边界
      - 处理垂直跨名称表边界
    - 对每个 tile：
      - 查 Nametable → tile 索引
      - 查 Attribute Table → 调色板组（2 bit）
      - 查 Pattern Table → 2 bit-plane → 2-bit 颜色索引
      - 颜色索引 0 → 通用背景色（Palette[0]）
      - 颜色索引 1-3 → `palette_bg[group][color_idx]`
      - 映射到系统调色板 → RGB
  - 预计代码量：~80 行

- [ ] **3.2 实现精灵层渲染**
  - 遍历 OAM 64 条目（倒序：先画低优先级精灵）
  - 每条目：
    - Y 坐标（需 +1 偏移，精灵 Y 在屏幕坐标中 = Y_byte + 1）
    - Tile 索引（Pattern Table 由 PPUCTRL bit3 选择）
    - 属性（VFlip, HFlip, Behind BG, Palette Group）
    - X 坐标
  - 从 Pattern Table 取 tile 像素（8×8）
  - 应用翻转、优先级逻辑
  - 精灵 0 Hit 检测：第 0 号精灵的非透明像素与背景非透明像素重叠时置标志
  - 预计代码量：~60 行

- [ ] **3.3 实现背景+精灵合成**
  - 背景像素 + 精灵像素叠加规则：
    - 精灵颜色索引 0（透明）→ 显示背景
    - 精灵 Behind BG 属性 = 1 → 仅覆盖背景颜色索引 0 的位置
    - 精灵 Behind BG 属性 = 0 → 覆盖非 0 背景
  - 最终输出：256×240 的 RGB 像素数组
  - 预计代码量：~30 行

- [ ] **3.4 实现调色板读取辅助**
  - `_read_palette(index)` → Palette RAM 数据
  - 地址 0x3F10/0x3F14/0x3F18/0x3F1C 镜像到 0x3F00/0x3F04/0x3F08/0x3F0C
  - 返回的 palette 索引查 SYSTEM_PALETTE
  - 预计代码量：~15 行

### Phase 4 — 调试数据暴露

- [ ] **4.1 暴露 Pattern Table 供调试**
  - `get_pattern_table(table_index: int)` → 128×128 像素的 RGB 数组
  - 每个 tile 8×8，排列为 16×16 个 tile
  - 从 CHR ROM 读取 tile 数据，按调色板 0（灰度）或当前调色板着色
  - 预计代码量：~30 行

- [ ] **4.2 暴露调色板供调试**
  - `get_palette_data()` → 32 字节 Palette RAM + 64 色系统调色板
  - 供 Debug 窗口直接使用
  - 预计代码量：~8 行

### Phase 5 — 测试

- [ ] **5.1 编写寄存器单元测试**
  - 文件：`tests/test_ppu.py`
  - 测试用例：
    - PPUCTRL 写入 NMI 使能位
    - PPUSTATUS 读取 VBlank 标志
    - PPUSCROLL/PPUADDR 两次写入 → 写锁存器行为
    - PPUSTATUS 读取 → 复位写锁存器
    - PPUDATA 读写后地址自动递增
    - OAMDATA 读写
  - 预计代码量：~60 行

- [ ] **5.2 编写渲染单元测试**
  - 构造已知 VRAM 状态：
    - 写已知 tile 索引到 Nametable
    - 写已知调色板
    - 写已知 CHR ROM tile 数据（模拟）
  - 调用 `render_frame()`
  - 验证特定像素位置的 RGB 值
  - 预计代码量：~50 行

- [ ] **5.3 编写时序单元测试**
  - 模拟 CPU 周期推进
  - 验证 VBlank 标志在扫描线 241 设置
  - 验证 NMI 触发时机
  - 预计代码量：~30 行

- [ ] **5.4 跑通全部测试**
  - `python -m pytest tests/test_ppu.py -v`

---

## 验收标准
- [x] （未开始）背景、精灵、滚动正确渲染；VBlank/NMI 时序正确；调试数据可用
