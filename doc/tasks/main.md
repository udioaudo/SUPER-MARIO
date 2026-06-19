# Main 模块 — 任务列表

> 模块文件：`main.py`
> 依赖：所有其他模块
> 可独立测试：⚠️ 需集成测试（不可单元测试）

---

## 任务清单

- [ ] **1. 实现命令行参数解析**
  - 文件：`main.py`
  - `parse_args()`：
    - 使用 `argparse`
    - 必填参数：`rom_file`（ROM 文件路径，string）
    - 可选参数：`--scale N`（默认 2，范围 1–5，int）
    - 可选参数：`--debug`（启用调试窗口，store_true）
  - 预计代码量：~15 行

- [ ] **2. 实现初始化流程**
  - `main()` 函数：
    1. 调用 `parse_args()`
    2. 初始化 Pygame：`pygame.init()`
    3. 加载卡带：`cartridge = Cartridge.load(args.rom_file)`
    4. 创建模块实例（顺序：RAM → PPU → APU → Input → Bus → CPU）
    5. 创建 UI：`ui = UI(scale=args.scale)`
    6. 创建 Debug（若 `--debug`）：`debug = DebugWindow(cpu, ppu, bus, input_dev)`
    7. 初始化音频：`pygame.mixer.init(frequency=44100, size=-16, channels=1)`
    8. CPU 复位：`cpu.reset()`
  - 预计代码量：~30 行

- [ ] **3. 实现主循环 `run_loop()`**
  - 常量：`FRAME_CPU_CYCLES = 29781`
  - 变量：`running`, `paused`, `step_mode` (None | 'frame' | 'instruction')
  - 每帧：
    1. 处理 UI 事件（退出？）
    2. 处理 Input 事件（按键轮询）
    3. 处理 Debug 命令（若有）
    4. CPU 执行：循环 `cpu.step()` 直到累积 ≥ FRAME_CPU_CYCLES
       - 每次 step 后驱动 `ppu.step(cycles)`, `apu.step(cycles)`
       - 若 `ppu.step()` 返回 True → `cpu.nmi()`
       - 指令步进处理
    5. 渲染画面：`ppu.render_frame()` → `ui.render(pixels)`
    6. 播放音频：`apu.get_audio_samples()` → `pygame.sndarray.make_sound()` → `sound.play()`
    7. 更新调试窗口：`debug.update()` → `debug.render()`（若启用且可见）
    8. 帧率控制：`ui.tick()`
  - 预计代码量：~55 行

- [ ] **4. 实现音频播放逻辑**
  - `apu.get_audio_samples()` 返回 int16 列表
  - 转换为 NumPy 数组：`np.array(samples, dtype=np.int16)`
  - 创建 Pygame Sound：`pygame.sndarray.make_sound(arr)`
  - 播放：`sound.play()`
  - 注意：避免累积过多 Sound 对象（每帧创建新 Sound，garbage collection）
  - 可选优化：使用 Stream 方式（如 `pygame.mixer.Sound(buffer=...)`）
  - 预计代码量：~10 行

- [ ] **5. 实现异常处理**
  - 文件不存在 → 输出友好错误信息
  - Mapper 非 0 → 输出"仅支持 Mapper 0 (NROM)"
  - 魔术数非法 → 输出"不是有效的 iNES ROM 文件"
  - 确保退出时调用 `pygame.quit()`（即使异常）
  - 预计代码量：~15 行

- [ ] **6. 实现 `requirements.txt`**
  - 文件：`requirements.txt`
  - 内容：
    ```
    pygame>=2.5.0
    numpy>=1.24.0
    ```
  - 预计代码量：2 行

- [ ] **7. 集成测试**
  - 文件：`tests/test_integration.py`
  - 测试用例：
    - 加载马里奥 ROM → 模拟运行 1 帧 → 无崩溃
    - 加载马里奥 ROM → 模拟运行 10 帧 → 无崩溃
    - 非法文件路径 → 友好报错
    - `--scale 1` / `--scale 5` 参数解析正确
    - `--debug` 参数解析正确
  - 预计代码量：~40 行

- [ ] **8. 冒烟测试**
  - `python main.py mario.nes` → 窗口正常打开，有关卡画面
  - `python main.py mario.nes --debug` → 游戏窗口 + 调试窗口同时显示
  - `python main.py mario.nes --scale 4` → 1024×960 窗口
  - 关闭游戏窗口 → 程序正常退出

- [ ] **9. 跑通测试**
  - `python -m pytest tests/test_integration.py -v`

---

## 验收标准
- [x] （未开始）命令行解析正确，主循环正常运行，游戏画面与音频同步输出
