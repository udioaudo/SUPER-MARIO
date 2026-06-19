# Cartridge 模块 — 任务列表

> 模块文件：`cartridge.py`
> 依赖：无（仅文件 I/O）
> 可独立测试：✅ 是

---

## 任务清单

- [ ] **1. 实现 iNES 文件头解析**
  - 文件：`cartridge.py`
  - `Cartridge` 类数据属性
  - `load(filepath)` 静态方法：
    - 读文件前 16 字节
    - 验证魔术数 `NES` + `0x1A`（不是则抛异常）
    - 解析 PRG_ROM_SIZE（偏移 4）、CHR_ROM_SIZE（偏移 5）
    - 解析 Flags 6（偏移 6）：Mapper 号低 4 位、镜像模式 bit0
    - 解析 Flags 7（偏移 7）：Mapper 号高 4 位
    - 验证 Mapper 号 == 0（不是则抛异常）
    - 检查是否有 Trainer（Flags 6 bit2），有则跳过 512 字节
  - 预计代码量：~40 行

- [ ] **2. 实现 PRG ROM / CHR ROM 数据加载**
  - `load()` 方法续：
    - 读取 PRG ROM：`PRG_ROM_SIZE × 16384` 字节
    - 读取 CHR ROM：若 `CHR_ROM_SIZE > 0`，读 `CHR_ROM_SIZE × 8192` 字节
    - 若 `CHR_ROM_SIZE == 0`，分配 8 KiB CHR RAM (`bytearray(8192)`)
  - 预计代码量：~15 行

- [ ] **3. 实现 CPU 侧地址映射**
  - `cpu_read(addr)` — addr: 0x4020–0xFFFF：
    - 计算映射地址 `mapped = (addr - 0x8000) % len(prg_rom)`
    - 返回 `prg_rom[mapped]`
    - 地址 < 0x4020 返回 0（open bus）
  - `cpu_write(addr, value)` — PRG ROM 只读，忽略写入
  - 预计代码量：~15 行

- [ ] **4. 实现 PPU 侧地址映射**
  - `ppu_read(addr)` — addr: 0x0000–0x1FFF：
    - CHR ROM 模式：`chr_rom[addr % len(chr_rom)]`
    - CHR RAM 模式：`chr_ram[addr % 8192]`
  - `ppu_write(addr, value)` — 仅 CHR RAM 模式有效
  - 预计代码量：~15 行

- [ ] **5. 实现镜像模式属性**
  - `mirroring` 属性：根据 Flags 6 bit0 返回 `'vertical'` 或 `'horizontal'`
  - 预计代码量：~5 行

- [ ] **6. 编写单元测试**
  - 文件：`tests/test_cartridge.py`
  - 测试用例：
    - 构造合法 iNES 最小文件（Header 16 字节 + 1 页 PRG + 1 页 CHR），验证 load() 各字段
    - 非法魔术数 → 应抛异常
    - 非 Mapper 0 → 应抛异常
    - PRG ROM = 2 页（32 KiB → 马里奥 1 代场景）地址映射验证
    - PRG ROM = 1 页（16 KiB）镜像映射验证
    - CHR RAM 模式（CHR_ROM_SIZE=0）读写验证
    - 镜像模式 bit0=0 → horizontal，bit0=1 → vertical
  - 预计代码量：~50 行
  - 测试需 `tempfile` 或 `BytesIO` 构造 ROM 文件

- [ ] **7. 跑通测试**
  - `python -m pytest tests/test_cartridge.py -v`

---

## 验收标准
- [x] （未开始）iNES 文件正确解析，Mapper 0 地址映射正确，非法文件被拒绝
