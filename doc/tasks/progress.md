# 超级玛丽 FC 模拟器 — 总体进度

> 基于需求文档 v1.0 + 详细设计 v1.0
> 每个模块对应一个详细任务文件：`doc/tasks/<module-name>.md`

---

## 开发顺序与模块进度

| 序号 | 阶段 | 模块 | 任务文件 | 状态 | 备注 |
|------|------|------|----------|------|------|
| 1 | Phase 1 | RAM | [ram.md](ram.md) | [x] 已完成 | pytest 5/5 ✓ mypy strict ✓ ruff ✓ |
| 2 | Phase 1 | Palette | [palette.md](palette.md) | [x] 已完成 | pytest 4/4 ✓ mypy strict ✓ ruff ✓ |
| 3 | Phase 1 | Cartridge | [cartridge.md](cartridge.md) | [x] 已完成 | pytest 17/17 ✓ mypy strict ✓ ruff ✓ |
| 4 | Phase 1 | Bus | [bus.md](bus.md) | [x] 已完成 | pytest 19/19 ✓ mypy strict ✓ ruff ✓ |
| 5 | Phase 1 | CPU | [cpu.md](cpu.md) | [x] 已完成 | pytest 91✓/2skip ✓ mypy strict ✓ ruff ✓ |
| 6 | Phase 2 | PPU | [ppu.md](ppu.md) | [x] 已完成 | pytest 106✓ ✓ mypy strict ✓ ruff ✓ |
| 7 | Phase 2 | UI | [ui.md](ui.md) | [x] 已完成 | pytest 13✓ ✓ mypy strict ✓ ruff ✓ |
| 8 | Phase 3 | APU | [apu.md](apu.md) | [x] 已完成 | pytest 41✓ ✓ mypy strict ✓ ruff ✓ |
| 9 | Phase 4 | Input | [input.md](input.md) | [x] 已完成 | pytest 17✓ ✓ mypy strict ✓ ruff ✓ |
| 10 | Phase 5 | Debug | [debug.md](debug.md) | [x] 已完成 | pytest 16✓ ✓ mypy strict ✓ ruff ✓ |
| 11 | Phase 6 | Main | [main.md](main.md) | [x] 已完成 | pytest 11✓ ✓ mypy strict ✓ ruff ✓ |

---

## Phase 概览

| Phase | 内容 | 状态 | 验收标准 |
|-------|------|------|----------|
| **Phase 1** | RAM + Palette + Cartridge + Bus + CPU | [x] 已完成 | 136 tests ✓ mypy ✓ ruff ✓ (5/5 模块) |
| **Phase 2** | PPU + UI | [x] 已完成 | 119 tests ✓ both mypy ✓ both ruff ✓ |
| **Phase 3** | APU | [x] 已完成 | 41 tests, 5 channels ✓ |
| **Phase 4** | Input | [x] 已完成 | 17 tests, FC 手柄协议 ✓ |
| **Phase 5** | Debug | [x] 已完成 | 16 tests, 调试窗口 ✓ |
| **Phase 6** | Main 联调 + 验收 | [x] 已完成 | 340 total tests, all gates ✓ |

---

## 验收标准（对照需求文档 2.1 节）

- [ ] 能加载并运行《超级马里奥兄弟》1代 `.nes` ROM
- [ ] 标题画面、关卡画面正确显示，无明显花屏
- [ ] 马里奥可正常移动、跳跃、顶砖块、吃蘑菇、踩敌人、进水管、过关
- [ ] 背景音乐与音效正常播放
- [ ] 运行帧率接近 60 FPS，操作无明显延迟
- [ ] 基础调试工具可用

---

*最后更新：2026-06-19 — 全部 11 个模块已完成，340 个测试通过*
