# APU 模块 — 任务列表

> 模块文件：`apu.py`
> 依赖：无（纯内部状态，通过 register 读写与外界交互）
> 可独立测试：✅ 是（写寄存器 → 推进 → 验证输出样本）

---

## 任务清单

### Phase 1 — 骨架与帧计数器

- [ ] **1.1 创建 APU 类骨架**
  - 文件：`apu.py`
  - `__init__()`：初始化 5 个通道
  - `CPU_CLOCK = 1789773`（NTSC NES CPU 频率）
  - `SAMPLE_RATE = 44100`
  - `SAMPLES_PER_FRAME = 44100 // 60`（约 735）
  - 预计代码量：~15 行

- [ ] **1.2 实现帧计数器 Frame Counter**
  - 内部计数器 `_fc_cycle`（以 CPU 周期计）
  - `_fc_mode`：0 = 4-step（默认），1 = 5-step（由 0x4017 bit7 控制）
  - `_fc_step`：当前步（0–4 或 0–5）
  - `_fc_irq_inhibit`：是否禁止 IRQ（0x4017 bit6）
  - 4-step 序列节拍：3728.5, 7457, 11185.5, 14914
  - 5-step 序列节拍：同 4-step + 18640.5
  - `step(cpu_cycles)` 中更新帧计数器
  - 每次步进时调用 `_clock_envelopes()`, `_clock_sweeps()`, `_clock_length_counters()`
  - 预计代码量：~40 行

### Phase 2 — Pulse 通道 (×2)

- [ ] **2.1 实现 Pulse 通道的基础状态**
  - 每个 Pulse 通道的状态变量：
    - `_duty` → 占空比（2 bit）
    - `_duty_table` → 4 种波形：[0b01000000, 0b01100000, 0b01111000, 0b10011111]
    - `_duty_index` → 当前在 duty table 中的位置 (0–7)
    - `_envelope_enabled` → 包络是否启用
    - `_envelope_volume` → 当前音量 (0–15)
    - `_envelope_decay` → 衰减率 (0–15)
    - `_envelope_loop` → 包络是否循环
    - `_envelope_counter` → 包络计数器
    - `_timer` → 频率定时器 (11 bit)
    - `_timer_counter` → 当前定时器倒数
    - `_length_counter` → 波长计数器 (5 bit, 查表 0/254/20/2/…)
    - `_length_halt` → 是否暂停波长计数
    - `_sweep_enabled` → 频率扫描是否启用
    - `_sweep_divider` → 扫描分频器
    - `_sweep_negate` → 扫描方向（加/减）
    - `_sweep_shift` → 扫描步长
    - `_sweep_reload` → 扫描重载标志
    - `_channel_enabled` → 通道是否启用
  - 预计代码量：~40 行（初始化 + 状态定义）

- [ ] **2.2 实现 Pulse 计时与波形输出**
  - `_clock_pulse(channel)`：
    - 递减 `_timer_counter`
    - 归零时：`_timer_counter = _timer`；`_duty_index = (_duty_index - 1) & 0x07`
    - 波形值 = `_duty_table[_duty] >> _duty_index) & 1`
    - 输出音量 = `_envelope_enabled ? _envelope_volume : 固定值`
    - 最终输出 = 波形值 × 输出音量（范围 0–15）
  - 预计代码量：~25 行

- [ ] **2.3 实现包络（Envelope）**
  - `_clock_envelope(channel)`：
    - 递减 `_envelope_counter`
    - 归零时：
      - 若 `_envelope_loop`：音量重置为 15
      - 否则：若 `_envelope_volume > 0`，减 1
    - `_envelope_counter` = `_envelope_decay`
  - 预计代码量：~20 行

- [ ] **2.4 实现频率扫描（Sweep，Pulse 1 独有）**
  - `_clock_sweep(channel)`：
    - 递减 `_sweep_divider`
    - 归零时：
      - 计算 `delta = _timer >> _sweep_shift`
      - 若 `_sweep_negate`：`new_timer = _timer - delta`（Pulse 1 减 1）
      - 否则：`new_timer = _timer + delta`
      - 若 `new_timer > 0x7FF`：禁用通道
      - 否则：`_timer = new_timer`
      - `_sweep_divider = sweep_period(3 bit) + 1`
    - 若 `_sweep_reload`：重置分频器和音量
  - 预计代码量：~30 行

- [ ] **2.5 实现波长计数器（Length Counter）**
  - 5 bit 查表：`[10, 254, 20, 2, 40, 4, 80, 6, 160, 8, 60, 10, 14, 12, 26, 14, 12, 16, 24, 18, 48, 20, 96, 22, 192, 24, 72, 26, 16, 28, 32, 30]`
  - `_clock_length_counter(channel)`：
    - 若 `_length_halt` 或 `_length_counter == 0`：不操作
    - 否则：`_length_counter -= 1`
    - 减到 0 时：通道静音
  - 预计代码量：~15 行

- [ ] **2.6 实现 Pulse 寄存器写入**
  - 0x4000/0x4004 → SQ1_VOL / SQ2_VOL：占空比 + 包络
  - 0x4001/0x4005 → SQ1_SWEEP / SQ2_SWEEP：频率扫描
  - 0x4002/0x4006 → SQ1_LO / SQ2_LO：频率低 8 位
  - 0x4003/0x4007 → SQ1_HI / SQ2_HI：频率高 3 位 + 波长计数重载
  - 预计代码量：~30 行

### Phase 3 — Triangle 通道

- [ ] **3.1 实现 Triangle 通道状态**
  - 状态变量：
    - `_timer` → 频率定时器 (11 bit)
    - `_timer_counter`
    - `_linear_counter` → 线性计数器 (7 bit)
    - `_linear_reload` → 线性计数器重载值
    - `_linear_control` → 是否由 0x4008 bit7 控制
    - `_length_counter` → 波长计数器
    - `_length_halt`
    - `_tri_step` → 当前三角波步骤 (0–31)
    - `_channel_enabled`
  - 三角波波形表（32 步）：
    - [15,14,13,12,11,10,9,8,7,6,5,4,3,2,1,0,0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15]
  - 预计代码量：~25 行

- [ ] **3.2 实现 Triangle 计时与波形输出**
  - `_clock_triangle()`：
    - 递减 `_timer_counter`
    - 归零时：`_timer_counter = _timer`；`_tri_step = (_tri_step + 1) & 0x1F`
    - 输出 = `tri_wave[_tri_step]` × 线性计数器活跃状态（0 或波形值）
    - Triangle 无音量包络 → 固定"音量"（由线性计数器充当）
  - 预计代码量：~15 行

- [ ] **3.3 实现线性计数器（Linear Counter）**
  - 受 0x4008 bit7 (`_linear_control`) 控制
  - `_clock_linear_counter()`：
    - 若 `_linear_reload`：`_linear_counter = _linear_reload`
    - 否则若 `_linear_counter > 0`：`_linear_counter -= 1`
    - 若 `_linear_control == 0`：清除 reload 标志
  - 预计代码量：~15 行

- [ ] **3.4 实现 Triangle 寄存器写入**
  - 0x4008 → TRI_LINEAR：线性计数器
  - 0x400A → TRI_LO：频率低 8 位
  - 0x400B → TRI_HI：频率高 3 位 + 波长计数重载
  - 预计代码量：~20 行

### Phase 4 — Noise 通道

- [ ] **4.1 实现 Noise 通道状态**
  - 状态变量：
    - `_shift_register` → 15 bit LFSR（初始值 = 1）
    - `_mode` → 0=长模式(32767 bit), 1=短模式(93 bit)
    - `_timer` → 噪声周期定时器 (4 bit → 查表)
    - `_timer_counter`
    - `_envelope_enabled`, `_envelope_volume`, `_envelope_decay`, `_envelope_loop`, `_envelope_counter`
    - `_length_counter`, `_length_halt`
    - `_channel_enabled`
  - 噪声周期查表（16 项）：`[4, 8, 16, 32, 64, 96, 128, 160, 202, 254, 380, 508, 762, 1016, 2034, 4068]`
  - 预计代码量：~25 行

- [ ] **4.2 实现 Noise 计时与波形输出**
  - `_clock_noise()`：
    - 递减 `_timer_counter`
    - 归零时：
      - `_timer_counter = noise_period_table[_noise_period]`
      - 更新 LFSR：
        - `feedback = (shift_reg & 1) ^ ((shift_reg >> (_mode ? 6 : 1)) & 1)`
        - `shift_reg = (shift_reg >> 1) | (feedback << 14)`
    - 输出 = `~shift_reg & 1`（取反后的 bit 0）× 包络音量
  - 预计代码量：~20 行

- [ ] **4.3 实现 Noise 寄存器写入**
  - 0x400C → NOISE_VOL：包络
  - 0x400E → NOISE_LO：噪声周期 + 模式
  - 0x400F → NOISE_HI：波长计数
  - 预计代码量：~15 行

### Phase 5 — DMC 通道（基本框架）

- [ ] **5.1 实现 DMC 通道状态**
  - 状态变量：
    - `_rate` → 采样速率 (4 bit → 查表)
    - `_rate_counter`
    - `_sample_addr` → PCM 数据起始地址 (0xC000 + addr*64)
    - `_sample_length` → PCM 数据长度 (length*16 + 1)
    - `_bytes_remaining` → 剩余字节
    - `_output_unit` → 7 bit 输出计数器（delta 解码）
    - `_sample_buffer` → 当前播放的 1 字节采样
    - `_bits_remaining` → 当前字节剩余 bit 数
    - `_silence` → 静音标志
    - `_irq_enabled` → IRQ 使能
    - `_loop` → 循环播放
  - DMC 速率查表（16 项）：`[428, 380, 340, 320, 286, 254, 226, 214, 190, 160, 142, 128, 106, 84, 72, 54]`
  - 预计代码量：~30 行

- [ ] **5.2 实现 DMC 计时与输出**
  - `_clock_dmc()`：
    - 递减 `_rate_counter`
    - 归零时：
      - `_rate_counter = rate_table[_rate]`
      - 若 `_silence`：不操作
      - 否则若 `_bits_remaining > 0`：
        - 若 `_sample_buffer & 1`：`_output_unit += 2`（上限 126）
        - 否则：`_output_unit -= 2`（下限 0）
        - `_sample_buffer >>= 1; _bits_remaining -= 1`
      - 若 `_bits_remaining == 0`：需要新字节
    - 输出 = `_output_unit`（0–127）
  - 预计代码量：~25 行

- [ ] **5.3 实现 DMC 内存读取器**
  - `_dmc_reader_active` → 是否需要从内存读取采样字节
  - 当 `_bits_remaining == 0` 且 `_bytes_remaining > 0` 时：
    - 从 `_sample_addr` 读 1 字节（通过 Bus）
    - `_sample_addr = (_sample_addr + 1) | 0x8000`（自动回卷）
    - `_bytes_remaining -= 1`
    - `_sample_buffer = byte; _bits_remaining = 8`
  - 当 `_bytes_remaining == 0`：
    - 若 `_loop`：重载地址和长度
    - 否则若 `_irq_enabled`：触发 IRQ
  - 预计代码量：~25 行

- [ ] **5.4 实现 DMC 寄存器写入**
  - 0x4010 → DMC_FREQ：速率 + IRQ + 循环
  - 0x4011 → DMC_RAW：直接加载输出单元（7 bit）
  - 0x4012 → DMC_START：采样地址 = 0xC000 + value*64
  - 0x4013 → DMC_LEN：采样长度 = value*16 + 1
  - 预计代码量：~20 行

### Phase 6 — 音频样本生成与混合

- [ ] **6.1 实现音频样本生成**
  - `get_audio_samples()`：
    - 帧时长 = 1/60 秒
    - 每样本推进 `CPU_CLOCK / SAMPLE_RATE ≈ 40.58` CPU 周期
    - 生成 ~735 个样本
    - 每个样本：推进各通道、混合、缩放为 int16
  - 预计代码量：~35 行

- [ ] **6.2 实现通道混合**
  - 混合公式：
    - `pulse_out = (pulse1 * pulse_ratio + pulse2 * pulse_ratio) / 15`（归一化到 0–1）
    - `tri_out = triangle / 15`
    - `noise_out = noise / 15`
    - `dmc_out = dmc / 127`（DMC 输出范围 0–127）
  - 总输出 = `(pulse_out + tri_out + noise_out + dmc_out) / 4`（简单平均）
  - 缩放为 int16: `int((output - 0.5) * 65535)`（范围 -32768 ~ 32767）
  - 或使用设计文档中的加权混合
  - 预计代码量：~20 行

### Phase 7 — 寄存器总接口

- [ ] **7.1 实现 `read_register(addr)`**
  - 0x4015 → SND_CHN：读取各通道状态（活跃/非活跃）
  - 其他寄存器：通常返回 0（或最后写入值）
  - 预计代码量：~15 行

- [ ] **7.2 实现 `write_register(addr, value)`**
  - 按地址分发到各通道的寄存器处理函数
  - 0x4015 → 各通道 enable/disable
  - 0x4017 → 帧计数器模式设置
  - 预计代码量：~30 行

### Phase 8 — 测试

- [ ] **8.1 编写 Pulse 通道单元测试**
  - 文件：`tests/test_apu.py`
  - 构造 APU，写 Pulse 寄存器，推进时钟，验证波形输出
  - 测试用例：
    - 占空比正确性
    - 频率正确性
    - 包络衰减
    - 频率扫描
    - 波长计数器归零后静音
  - 预计代码量：~60 行

- [ ] **8.2 编写其他通道单元测试**
  - Triangle 三角波形状验证
  - Noise LFSR 输出
  - DMC delta 解码
  - 帧计数器步进
  - 预计代码量：~60 行

- [ ] **8.3 编写音频样本测试**
  - 写已知寄存器 → 调用 `get_audio_samples()` → 验证样本数组长度和非零值
  - 预计代码量：~20 行

- [ ] **8.4 跑通全部测试**
  - `python -m pytest tests/test_apu.py -v`

---

## 验收标准
- [x] （未开始）5 个通道正确运行，帧计数器正常，`get_audio_samples()` 返回合法 PCM 样本
