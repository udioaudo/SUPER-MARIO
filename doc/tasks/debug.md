# Debug 模块 — 任务列表

> 模块文件：`debug.py`
> 依赖：Pygame、CPU（只读）、PPU（只读）、Bus（只读）、Input（只读）
> 可独立测试：⚠️ 需 Mock 所有依赖模块（建议最后实现）

---

## 任务清单

### Phase 1 — 窗口基础

- [ ] **1.1 创建 DebugWindow 类骨架**
  - 文件：`debug.py`
  - `__init__(cpu, ppu, bus, input_dev)`：
    - 持有各模块引用（只读访问）
    - 创建 640×480 Pygame 窗口：`pygame.display.set_mode(640, 480)`
    - `pygame.display.set_caption("SUPER MARIO - Debug")`
    - 初始化 Pygame 字体：`pygame.font.SysFont('Consolas', 14)`（等宽字体）
    - 内部状态：
      - `_mem_start_addr = 0x0000` — 内存查看起始地址
      - `_fps_history = []` — FPS 滑动窗口
  - 预计代码量：~25 行

- [ ] **1.2 实现窗口关闭处理**
  - 关闭调试窗口不影响主游戏窗口
  - 策略：`_visible = True` 属性；
    - 初始 `_visible = True`
    - 用户关闭调试窗口 → `_visible = False`
    - main.py 中：`if debug._visible: debug.update(); debug.render()`
    - main.py 中：`if debug._visible: cmd = debug.handle_input()`
  - 预计代码量：~10 行

### Phase 2 — 调试功能

- [ ] **2.1 实现 CPU 寄存器显示**
  - `_render_cpu_registers(surface, x, y)`：
    - `A: 0x{self._cpu.a:02X}`
    - `X: 0x{self._cpu.x:02X}`
    - `Y: 0x{self._cpu.y:02X}`
    - `PC: 0x{self._cpu.pc:04X}`
    - `SP: 0x{self._cpu.sp:02X}`
    - `P: NV-BDIZC`（展开 8 个标志位：大写 = 1，小写 = 0）
    - 二进制值 `{self._cpu.p:08b}`
  - 预计代码量：~30 行

- [ ] **2.2 实现运行信息显示**
  - `_render_runtime_info(surface, x, y)`：
    - 当前 FPS（从 UI 获取或自行计算均值）
    - 帧号（从 PPU 获取 `_frame` 属性）
    - 运行状态：`[RUNNING]` 或 `[PAUSED]`
  - 预计代码量：~20 行

- [ ] **2.3 实现内存查看器**
  - `_render_memory_view(surface, x, y)`：
    - 从 `self._mem_start_addr` 开始，显示 16 行 × 16 字节
    - 格式：`XXXX: XX XX XX XX XX XX XX XX  XX XX XX XX XX XX XX XX`
    - 每行 = 地址 + 16 个十六进制字节
    - 数据来源：`self._bus.read(addr)`
    - 当前查看地址范围标题：`Memory View [0x{start:04X}]`
  - 预计代码量：~30 行

- [ ] **2.4 实现 Pattern Table 可视化**
  - `_render_pattern_table(surface, x, y, table_index)`：
    - 从 PPU 获取 `get_pattern_table(table_index)`（128×128 RGB 数组）
    - 每个 tile = 8×8 像素，16×16 tile 排列
    - 缩放到 128×128 显示
    - 标题：`Pattern Table 0` / `Pattern Table 1`
    - **可选优先级**（需求标注为可选，Phase 5 最后实现）
  - 预计代码量：~25 行

- [ ] **2.5 实现调色板显示**
  - `_render_palette(surface, x, y)`：
    - 从 PPU 获取 `get_palette_data()`（32 字节 Palette RAM）
    - 显示 8 组 × 4 色块（背景 4 组 + 精灵 4 组）
    - 每个色块 = 16×16 像素填充对应 RGB 颜色
    - 标签：`BG0: ■ ■ ■ ■  BG1: ■ ■ ■ ■  BG2: ■ ■ ■ ■  BG3: ■ ■ ■ ■`
    - 标签：`SP0: ■ ■ ■ ■  SP1: ■ ■ ■ ■  SP2: ■ ■ ■ ■  SP3: ■ ■ ■ ■`
    - **可选优先级**
  - 预计代码量：~25 行

### Phase 3 — 键盘控制

- [ ] **3.1 实现 `handle_input()`**
  - 从调试窗口的 Pygame 事件队列读取事件
  - 仅处理调试快捷键，非调试事件放回队列
  - 快捷键：
    - `F5` → `{'action': 'pause'}`
    - `F6` → `{'action': 'step', 'step': 'frame'}`
    - `F7` → `{'action': 'step', 'step': 'instruction'}`
    - `F1` → `self._mem_start_addr = (self._mem_start_addr + 0x100) & 0xFFFF`
    - `F2` → `self._mem_start_addr = (self._mem_start_addr - 0x100) & 0xFFFF`
    - `UP` → `self._mem_start_addr = (self._mem_start_addr + 0x10) & 0xFFFF`
    - `DOWN` → `self._mem_start_addr = max(0, self._mem_start_addr - 0x10)`
    - `PAGEUP` → `self._mem_start_addr = (self._mem_start_addr + 0x100) & 0xFFFF`
    - `PAGEDOWN` → `self._mem_start_addr = max(0, self._mem_start_addr - 0x100)`
    - 窗口关闭 → `_visible = False`
  - 预计代码量：~35 行

### Phase 4 — 渲染循环

- [ ] **4.1 实现 `update()`**
  - 刷新内部缓存（目前主要是为未来扩展预留）
  - 如：缓存 Pattern Table 渲染结果（避免每帧重算）
  - 预计代码量：~5 行

- [ ] **4.2 实现 `render()`**
  - 清屏（黑色背景）
  - 依次调用各渲染函数：
    1. `_render_cpu_registers(0, 0)`
    2. `_render_runtime_info(320, 0)`
    3. `_render_memory_view(0, 100)`
    4. `_render_pattern_table(320, 100, 0)` — Pattern Table 0（可选）
    5. `_render_pattern_table(460, 100, 1)` — Pattern Table 1（可选）
    6. `_render_palette(320, 240)` — 调色板（可选）
    7. `_render_controls_hint(0, 460)` — 底部快捷键提示
  - `pygame.display.flip()`（仅刷新调试窗口）
  - 预计代码量：~25 行

- [ ] **4.3 实现快捷键提示条**
  - `_render_controls_hint(surface, x, y)`：
    - `F5=Pause/Continue  F6=Frame Step  F7=Instruction Step`
    - `F1/F2=Mem±0x100  ↑↓=Mem±0x10  PgUp/PgDn=Mem±0x100`
  - 预计代码量：~10 行

### Phase 5 — 测试

- [ ] **5.1 编写单元测试**
  - 文件：`tests/test_debug.py`
  - Mock CPU/PPU/Bus/Input，注入 DebugWindow
  - 测试用例：
    - 窗口创建成功
    - `handle_input()` 对 F5 返回 `{'action': 'pause'}`
    - `handle_input()` 对 F1 修改 `_mem_start_addr`
    - 关闭窗口 → `_visible = False`
    - `update()` 不崩溃
    - `render()` 不崩溃
  - 预计代码量：~50 行

- [ ] **5.2 跑通测试**
  - `python -m pytest tests/test_debug.py -v`

---

## 验收标准
- [x] （未开始）CPU 寄存器、内存查看正确显示；暂停/帧步进/指令步进可用；Pattern Table 和调色板可选功能正常
