---
name: embedded tag 可疑模式（不要无条件信任）
description: 流媒体/下载站把营销名写进 album tag，filename brackets 才是真值
type: feedback
originSessionId: 9208d9a1-fa25-4144-b86c-48882cbc051d
---
## 复盘：为什么 Pink Floyd 4 首歌曾被堆到 "Qobuz Hi-Res Masters" 文件夹

**错误判断**：embedded album tag 非空 ≠ tag 正确。

**当时的逻辑漏洞**：
- `_clean_junk` 只过滤 URL/Unknown 类**结构性垃圾**，不识别**语义垃圾**（合法字符串但内容是平台 marketing 名）
- trust 层级是：embedded tag > path inference，没有反例检测层

**应该立刻警觉的信号**：
1. 同一艺人下出现 N 张**同名**专辑只靠年份区分 → 必然是 sampler 拆分
2. embedded album 含平台/营销词：`Qobuz`, `Tidal`, `Hi-Res Masters`, `Essentials`, `SACD COLLECTION`, `实体CD版`, `盒装版`, `豪华版`
3. 文件名末尾有 `[…]` 或全角 `「…」` → 通常是真值的编码（流媒体下载惯例）

---

## 规则：embedded tag 反例检测层

加在 `probe()` 之后、enrichment 之前：

1. **album 含 sampler 关键词** → 用 filename brackets 替换（已实现 `_SAMPLER_ALBUM_RE`）
2. **filename 有 `[Album]`** → 与 embedded album 比对，如果 embedded 是已知 sampler 名，用 bracket
3. **filename 有 `「Artist」`** → 全角直角引号包艺人名，比 folder/embedded 优先

---

## 教训：何时怀疑 embedded tag

| 情况 | embedded 信任度 |
|------|----------------|
| 普通 CD rip / Picard tagged | 高 |
| 流媒体下载（Qobuz/Tidal/Apple Music） | **低** — 大概率写营销名 |
| 群文件 / 网盘下载 | 低 — tag 可能被人为改过 |
| 无 tag (空) | 中 — 需要 path inference + AcoustID 兜底 |

---

## 规则：4 张同名专辑应自动检测

如果某艺人下有 ≥ 2 张专辑名相同（即使年份不同），脚本应警告并尝试用 filename bracket 拆分。这是 sampler split 的明确信号。

（暂未自动化，发现时人工触发 normalize 即可）
