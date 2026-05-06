---
name: WAV tag 解码完整审计（多次踩坑教训）
description: WAV 有多种 tag 存储位置 + 多种字符编码，修复时必须全维度覆盖
type: feedback
---

## 元教训：修同类 bug 必须做"全维度审计"

**事故复盘（2026-05-05）**：
- 上一次修了 WAV ID3 chunk 的 `??` garble（mutagen fallback）→ 当时认为"WAV tag 解码问题搞定了"
- 这次又在 WAV 上栽了：HiFi3655 论坛的 GBK INFO chunk 整个目录全乱码
- 用户质问："这个之前曾经修复过，为啥没吸取教训"

**根本原因**：上次 fix 了**症状**（特定 garble pattern），没做**维度审计**：
- WAV tag 可以存在哪些位置？
- 每个位置可以用哪些字符编码？
- ffmpeg 默认按什么编码读？

如果当时把这张表填完整，会立刻发现 INFO chunk + GBK 这条路径同样会塌。

---

## WAV tag 存储 × 编码 完整矩阵

| 存储位置 | 编码可能 | ffmpeg 默认行为 | 已实现 fallback？ |
|---------|---------|----------------|------------------|
| RIFF INFO chunk | latin-1 / UTF-8 / **GBK** / Big5 | 按 latin-1 解（中文 → mojibake）| ✅ `_probe_wav_info_chunk()` GBK 优先 |
| ID3v2 chunk | UTF-16 / UTF-8 / latin-1 | 通常 OK，偶尔失败成 `??` | ✅ `_probe_wav_mutagen()` |
| BWF bext chunk | latin-1 强制 | 不读 | ⚪ 暂不处理 |
| iXML chunk | UTF-8 强制 | 不读 | ⚪ 暂不处理 |
| 没有 tag | — | 空 dict | ✅ `infer_from_path()` 兜底 |

---

## 什么时候要重读 INFO chunk

**触发条件**（已实现）：`_is_mojibake(result['artist'/'album'/'title'])`
- 检测方式：尝试 `s.encode('latin-1').decode('gbk')`，若得到合法 CJK 文本，原文必是 GBK mojibake
- 同时检查 `[¨©¬­®¯]` 等 latin-1 高位标点的连续出现（mojibake 特征）

**已知触发源**：HiFi3655、发烧友论坛、网盘 rip、淘宝/咸鱼出售的 WAV 包、国内"音响展"U盘内容

---

## 通用规则：发现编码问题时的"全表审计"清单

每次遇到 tag decoding 问题（不限 WAV），强制问一遍：

1. **存储**：这个文件格式有几种 tag 存放方式？（FLAC vorbis comment / ID3 / RIFF INFO / m4a atom / DSD ID3）
2. **编码**：每种存储用什么字符编码？工具对每种编码的默认处理？
3. **来源**：常见的 rip 工具/论坛会用哪种？（中文社区 = GBK 概率极高）
4. **检测**：能否从结果反推出原始字节是哪种编码（mojibake → 原始编码）
5. **fallback 链**：每条路径都有兜底吗？

不做这一步就等于"只修当前症状"，下次遇到同源问题又踩。

---

## 已知会写 GBK INFO chunk 的来源

- HiFi3655 / 发烧友论坛
- 国内"音响展"U盘内容（2024广州国际音响唱片展类）
- 国内 audiophile 网盘分享
- EAC + 中文 metadata 用户在 Windows 默认 codepage 936 时
- foobar2000 默认安装时（Windows 中文版）

文件名带 `下载公众号:`、`HiFi`、`★粤语精选`、`发烧友` 等关键词的 WAV，**默认假设是 GBK INFO chunk**。
