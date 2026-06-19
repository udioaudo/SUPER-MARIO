# RAM 模块 — 任务列表

> 模块文件：`ram.py`
> 依赖：无（纯数据存储，无外部依赖）
> 可独立测试：✅ 是

---

## 任务清单

- [x] **1. 创建 RAM 类骨架**
  - 文件：`ram.py`
  - `__init__(size=2048)`: 分配 `bytearray(size)`，初始化为 0
  - `read(addr)`: 读 1 字节，地址自动镜像 (`addr % size`)
  - `write(addr, value)`: 写 1 字节 (`value & 0xFF`)，地址自动镜像
  - 预计代码量：~15 行

- [x] **2. 编写单元测试**
  - 文件：`tests/test_ram.py`
  - 测试用例：
    - 初始状态读返回 0
    - 基本读写：写 0x00→读→验证；写 0xFF→读→验证
    - 地址镜像：写 0x0800 再读 0x0000，验证相等
    - 写入超 0xFF 的值被截断
  - 预计代码量：~20 行

- [x] **3. 跑通测试**
  - `python -m pytest tests/test_ram.py -v`

---

## 验收标准
- [x] 读写正确，地址镜像正确，pytest/mypy/ruff 全部通过
