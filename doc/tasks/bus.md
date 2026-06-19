# Bus 模块 — 任务列表

> 模块文件：`bus.py`
> 依赖：RAM、PPU（接口）、APU（接口）、Cartridge、Input（接口）
> 可独立测试：✅ 是（使用 Mock 对象）

---

## 任务清单

- [ ] **1. 创建 Bus 类骨架与设备注入**
  - 文件：`bus.py`
  - `__init__(cpu_ram, ppu, apu, cartridge, input_dev)`：持有所有设备引用
  - 预计代码量：~10 行

- [ ] **2. 实现写路由 `write(addr, value)`**
  - 地址 0x0000–0x1FFF → `cpu_ram.write(addr, value)`（自动镜像，在 RAM 内部处理）
  - 地址 0x2000–0x3FFF → `ppu.write_register(0x2000 + (addr % 8), value)`（8 字节镜像）
  - 地址 0x4000–0x4013, 0x4015 → `apu.write_register(addr, value)`
  - 地址 0x4014 → **OAM DMA**（见任务 4）
  - 地址 0x4016 → `input_dev.write(value)`
  - 地址 0x4017 → `apu.write_register(addr, value)`
  - 地址 0x4020–0xFFFF → `cartridge.cpu_write(addr, value)`
  - 预计代码量：~25 行

- [ ] **3. 实现读路由 `read(addr, from_ppu=False)`**
  - 地址 0x0000–0x1FFF → `cpu_ram.read(addr)`
  - 地址 0x2000–0x3FFF → `ppu.read_register(0x2000 + (addr % 8))`
  - 地址 0x4000–0x4015 → `apu.read_register(addr)`
  - 地址 0x4016 → `input_dev.read()`
  - 地址 0x4017 → `apu.read_register(addr)` 或返回 0
  - 地址 0x4020–0xFFFF → `cartridge.cpu_read(addr)`
  - 预计代码量：~20 行

- [ ] **4. 实现 OAM DMA（0x4014 写入处理）**
  - 从 CPU 内存 `(value << 8)` 起复制 256 字节到 PPU OAM
  - 每字节调用 `bus.read(dma_addr + i)` → `ppu.oam_write(i, data)`
  - 返回消耗的周期数：513（需要通知 CPU 模块）
  - **注意**：DMA 的周期成本需要在 Bus 层面追踪，因为 `write()` 本身是同步调用
  - 方案：Bus 增加 `dma_cycles` 属性，`cpu.step()` 每次读 Bus 后检查并累加
  - 预计代码量：~15 行

- [ ] **5. 编写单元测试**
  - 文件：`tests/test_bus.py`
  - 需构造 Mock 对象（MockRAM, MockPPU, MockAPU, MockCartridge, MockInput）
  - 测试用例：
    - 写 0x0000 → MockRAM 收到调用
    - 写 0x2000 → MockPPU 收到 write_register(0x2000, val)
    - 写 0x2008 → MockPPU 收到 write_register(0x2000, val)（镜像）
    - 写 0x4000 → MockAPU 收到 write_register(0x4000, val)
    - 写 0x4014 → OAM DMA 触发（验证 256 字节从 RAM 复制到 PPU OAM）
    - 写 0x4016 → MockInput 收到 write(val)
    - 读 0x4016 → MockInput.read() 被调用
    - 写 0x8000 → MockCartridge 收到 cpu_write(0x8000, val)
    - 读 0x8000 → MockCartridge.cpu_read(0x8000) 被调用
  - 预计代码量：~60 行

- [ ] **6. 跑通测试**
  - `python -m pytest tests/test_bus.py -v`

---

## 验收标准
- [x] （未开始）所有地址范围读写正确路由，OAM DMA 正确
