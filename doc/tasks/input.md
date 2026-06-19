# Input 模块 — 任务列表

> 模块文件：`input.py`
> 依赖：Pygame（事件系统）
> 可独立测试：✅ 是（模拟 Pygame 事件）

---

## 任务清单

- [ ] **1. 创建 Input 类骨架**
  - 文件：`input.py`
  - `__init__()`：
    - `_buttons = [0] * 8` — 8 个按钮当前状态（0=松开, 1=按下）
    - `_latch = 0` — 锁存状态
    - `_read_index = 0` — 移位寄存器读取索引
    - `_shift = [0] * 8` — 当前锁存的按钮移位寄存器
  - 预计代码量：~10 行

- [ ] **2. 定义键盘映射**
  - `KEY_MAPPING` 字典：Pygame 键码 → FC 按钮索引 (0–7)
  - 方向键: ↑=0, ↓=1, ←=2, →=3
  - A=4 (K), B=5 (J), Start=6 (Enter), Select=7 (右 Shift)
  - 预计代码量：~12 行

- [ ] **3. 实现 `poll()` — 键盘事件读取**
  - 调用 `pygame.event.get()` 获取所有事件
  - 处理 KEYDOWN/KEYUP 事件：
    - 若按键在 KEY_MAPPING 中 → 更新 `_buttons[mapping] = 1` (按下) / 0 (松开)
    - 不在映射中的事件 → `pygame.event.post(event)` 放回队列
  - 不吞掉 QUIT 等其他事件（放回）
  - 预计代码量：~15 行

- [ ] **4. 实现 `write(value)` — 锁存/写入**
  - 模拟向 FC 的 0x4016 写入（仅关注 bit 0）
  - `value & 1 == 1`：
    - 锁存当前 `_buttons` 到 `_shift`（深拷贝）
    - `_read_index = 0`
  - `value & 1 == 0`：锁存结束，读取准备就绪
  - 预计代码量：~10 行

- [ ] **5. 实现 `read()` — 读取按钮状态**
  - 模拟从 FC 的 0x4016 读取
  - 读取顺序：A→B→Select→Start→↑→↓→←→→
  - 若 `_read_index < 8`：返回 `_shift[_read_index] & 1`；`_read_index += 1`
  - 若 `_read_index >= 8`：返回 1（表示已读完，真实硬件返回 1）
  - 返回格式：`bit0 = 按钮值 | 0x40`（模拟标准手柄 bit 1=1 表示手柄已连接）
  - 预计代码量：~15 行

- [ ] **6. 实现 `get_state()` — 供调试窗口**
  - 返回当前 8 个按钮状态的副本
  - 预计代码量：~3 行

- [ ] **7. 编写单元测试**
  - 文件：`tests/test_input.py`
  - 需 Mock pyGame 事件队列（`pygame.event.get()` 和 `pygame.event.post()`）
  - 测试用例：
    - 初始状态所有按钮为 0
    - 模拟 KEYDOWN K → `_buttons[4]` = 1
    - 模拟 KEYUP K → `_buttons[4]` = 0
    - 非映射按键（如字母 Q）→ 事件放回队列
    - 锁存 → 读 8 次 → 验证读取顺序 A/B/Sel/Start/↑/↓/←/→
    - 第 9 次读取返回 1
    - 写 bit0=0 → 不复位读取索引（仅锁存时复位）
  - 预计代码量：~60 行

- [ ] **8. 跑通测试**
  - `python -m pytest tests/test_input.py -v`

---

## 验收标准
- [x] （未开始）键盘映射正确，锁存/移位读取逻辑正确
