# UI 模块 — 任务列表

> 模块文件：`ui.py`
> 依赖：Pygame（display, transform, time）
> 可独立测试：✅ 是（渲染测试图案 + 人工验证）

---

## 任务清单

- [ ] **1. 创建 UI 类骨架**
  - 文件：`ui.py`
  - 常量：
    - `NATIVE_WIDTH = 256`
    - `NATIVE_HEIGHT = 240`
    - `FPS_TARGET = 60.0988`（NTSC 实际帧率）
  - `__init__(scale=2)`：
    - `self._scale = max(1, min(5, scale))`（限制 1–5）
    - `WINDOW_WIDTH = 256 * scale`
    - `WINDOW_HEIGHT = 240 * scale`
    - `pygame.display.set_mode(WINDOW_WIDTH, WINDOW_HEIGHT)`
    - `pygame.display.set_caption("SUPER MARIO - NES Emulator")`
    - 创建内部 `pygame.Surface((256, 240))` 用于逐像素写入
    - 创建 `pygame.time.Clock()` 用于帧率控制
  - 预计代码量：~25 行

- [ ] **2. 实现 `render(pixels)` — 画面渲染**
  - 参数：`pixels` — 256×240 的二维像素数组，每像素为 `(R, G, B)` 元组
  - 步骤：
    1. 用 `pygame.PixelArray` 或 `pygame.surfarray.pixels3d` 直接写内部 Surface
    2. `pygame.transform.scale(internal_surface, (WINDOW_WIDTH, WINDOW_HEIGHT))` 放大
    3. 或使用 `pygame.transform.scale_by(internal_surface, scale)`（Pygame 2.3+）
    4. `pygame.display.flip()` 刷新
  - 性能提示：
    - 优先用 `pygame.surfarray.blit_array()`（NumPy 数组直接写入 Surface，最快）
    - 若使用 PixelArray，注意及时释放（`del` 或 `with` 语句）
  - 预计代码量：~15 行

- [ ] **3. 实现 `handle_events()` — 事件处理**
  - 处理窗口层级事件：
    - `pygame.QUIT` → 返回 True（主循环退出）
    - `pygame.KEYDOWN`/`pygame.KEYUP` → 放回队列供 Input 模块处理（`pygame.event.post(event)`）
    - 其他事件 → 放回队列
  - 返回：是否应退出程序
  - 预计代码量：~15 行

- [ ] **4. 实现 `tick()` — 帧率控制**
  - `self._clock.tick(FPS_TARGET)`
  - 返回上一帧的实际耗时（ms）
  - 预计代码量：~5 行

- [ ] **5. 实现 `get_fps()` — 获取实际 FPS（供调试）**
  - `return self._clock.get_fps()`
  - 预计代码量：~3 行

- [ ] **6. 编写单元测试**
  - 文件：`tests/test_ui.py`
  - 由于 Pygame 窗口测试需要图形环境，单元测试重点为：
    - 构造测试图案（如纯色 + 色条），传入 `render()`，人工确认
    - 构造 Pygame QUIT 事件，验证 `handle_events()` 返回 True
    - `tick()` 返回值类型验证
  - 单元测试可侧重非渲染部分；渲染部分用集成测试
  - 预计代码量：~30 行

- [ ] **7. 跑通测试 + 人工验证**
  - `python -m pytest tests/test_ui.py -v`
  - 写临时测试脚本：生成 256×240 随机颜色/测试图案画面，确认窗口正常显示

---

## 验收标准
- [x] （未开始）窗口正常创建与关闭，画面正确放大显示，帧率接近 60 FPS
