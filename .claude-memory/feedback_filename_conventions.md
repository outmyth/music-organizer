---
name: 已识别的文件名约定（Qobuz, SACD COLLECTION 等）
description: 第三方音乐源使用的文件名/tag 编码方式，需要特殊解析
type: feedback
originSessionId: 9208d9a1-fa25-4144-b86c-48882cbc051d
---
## Qobuz 命名约定

Qobuz 流媒体下载会把真专辑信息编码到文件名里，但 **embedded album tag 写的是 sampler 名字**：

| 字段 | Qobuz 写入的值 | 真值（在文件名里） |
|------|---------------|------------------|
| filename | `02 - Comfortably Numb [The Wall].flac` | album = `The Wall` |
| filename | `10 - Peace Sells「Megadeth」[Peace Sells... But Who's Buying？].flac` | artist = `Megadeth`, album = `Peace Sells...` |
| filename | `12 - Autumn Leaves (2012 Remastered)「Cannonball Adderley」.flac` | artist = `Cannonball Adderley` |
| ID3 album | `Qobuz Hi-Res Masters of Pink Floyd` | sampler 名（要替换） |
| ID3 album | `Hi-Res Masters Metal Essentials` | sampler 名（要替换） |

**编码规则**：
- `[Album]` 末尾方括号 = 真专辑名
- `「Artist」` 全角直角引号 = 真艺人名
- ID3 album tag 写的是 Qobuz 流派 sampler 名，**不可信**

**处理逻辑**（已实现）：
1. `infer_from_path()` 解析 `[…]` 和 `「…」`
2. 主循环检查 embedded album 是否匹配 `_SAMPLER_ALBUM_RE` (`Qobuz Hi-Res Masters` / `Hi-Res Masters X Essentials` / `SACD COLLECTION`)，如果匹配且文件名有 `[…]`，强制用 bracket 替换 album

**反例**：单独依赖 embedded tag 会导致 4 首不同专辑的 Pink Floyd 单曲被堆到同一个 "Qobuz Hi-Res Masters of Pink Floyd" 文件夹里。

---

## SACD COLLECTION 约定

SACD rip 工具会把多张专辑统一打成 "Artist - SACD COLLECTION"。这种 album 通常无法在 iTunes/CAA 找到，需要单独处理或人工放封面。

---

## 中文 "实体CD版" / "盒装版" 后缀

国内压制 CD rip 经常加 `实体CD版`、`SACD版`、`盒装` 等后缀。`_normalize_album_for_search()` 已自动剥离这些后缀用于 iTunes 重试。
