---
name: dest 文件 metadata junk 传播链 + 反例
description: 为什么 source 修了但 dest 没修；为什么 ALBUM_META 硬编码值不会被网络服务覆盖
type: feedback
---

## 失败模式 1：source 干净 ≠ dest 干净

**症状**（2026-05-06 发现）：源文件 GBK fix 已修，源文件 metadata 解码正确；但 out/ 里 dest 文件还保留旧的 mojibake artist tag。同样 17 个王杰 SACD COLLECTION 文件 encoder 字段还有 SACD Ripper 水印，13 个 Tomb Raider 文件 comment 还有 `[www.PT80.net]`。

**根因链**：
1. `copy_with_meta` 用 ffmpeg `-c copy` → 默认**保留所有源 metadata**，包括 comment / encoded_by / general_remark / originator_reference 这些 junk-prone 字段
2. dest 写入条件：`force or 不存在 or 大小不匹配` → 旧 dest 大小匹配的话**永不重写**
3. probe() 只读 standard fields（title/artist/album 等），不检查 comment/encoded_by junk
4. writeback 只写空字段，不清 junk

**自动化修复**（已实现）：
1. `copy_with_meta` 主动 clear `comment / encoded_by / description / general_remark / originator_reference / TXXX` （这些字段写水印的概率远高于写有用信息）
2. `_has_junk_source_field()` 检测两类失败：
   - junk pattern: `_JUNK_TAG_RE` + `SACD Ripper` + `PT80` + `HiFi` + `[www.`
   - mojibake: `_is_mojibake()` round-trip 检测 GBK 误解码
3. 主循环：`src_has_junk` 强制触发 dest re-copy（即使大小匹配）
4. `writeback_to_source` 双触发：(a) field 为空被 enrichment 填上，(b) source 有 junk

---

## 失败模式 2：ALBUM_META 硬编码值绕过外部服务

**症状**（2026-05-06 发现）：`Songs My Mother Taught Me` 显示在 `Various Classical/` 文件夹下。`'Various Classical'` 是 ALBUM_META 里 hardcode 的 placeholder，实际上这是某位小提琴家的演奏专辑，AcoustID 完全可以查出真实 performer。

**根因**：
```python
# ALBUM_META override 触发后，整个 AcoustID block + text fallback 全跳过：
if not override and (...):
    aid = acoustid_lookup(fp)
```

`override` 一旦非空，所有后续 enrichment 全部 skip。结果 `'Various Classical'` 这种"我也不知道是谁"的 placeholder 就永远卡在那。

**架构缺陷**：ALBUM_META 没区分"硬约束"（用户精确知道的）和"软占位"（用户也不确定，需要外部服务补救）。

**应有的设计**（TODO，未实现）：

ALBUM_META 条目可以标注 `'soft'` 字段集合，列出哪些字段是软占位、可以被外部服务覆盖：

```python
'古典小提琴名盘': {
    'album': 'Songs My Mother Taught Me',     # 硬：用户确认
    'album_artist': 'Various',                # 软：实际不知道，可被 AcoustID 覆盖
    'genre': 'Classical',                     # 硬
    'soft': {'album_artist', 'date'},         # 这些字段允许 enrichment 覆盖
    'parse': 'violin_wav',
},
```

主循环逻辑改成：
- ALBUM_META 硬字段直接生效
- 软字段不阻断 AcoustID/MB/iTunes，由外部服务竞争填充
- 如果外部服务找不到，软字段保留 placeholder

**当前权宜**：把 `'Various Classical'` 改成 `'Various'`（与 BAV Vol.1 的 `Various` 一致）。仍然是 hardcoded placeholder，但至少不会出现"Various Classical"这种无意义的 derived 子目录。

---

## 教训：metadata 流向必须做"端到端"审计

每次修一个 metadata 处理 bug，必须问：
- source 是否干净？
- probe() 读取是否正确？
- enrichment 是否被 override 阻断？
- dest 写入是否正确传递？
- dest 是否被检测出问题并 re-copy？
- writeback 是否回灌？

任何一环卡住，就会出现 "我修了 source 但 dest 还是脏" 的现象。

---

## 通用规则：所有 ffmpeg 写文件命令都要 clear junk-prone 字段

`copy_with_meta` 和 `writeback_to_source` 都加了：
```python
for junk_field in ('comment','encoded_by','description',
                   'general_remark','originator_reference','TXXX'):
    meta_args += ['-metadata', f'{junk_field}=']
```

**Why**：这些字段被 watermark/ripper 滥用的概率 >> 用户主动写有用内容的概率。默认清掉对绝大多数用户都是正向。
