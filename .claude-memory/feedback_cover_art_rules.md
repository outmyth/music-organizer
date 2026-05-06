---
name: Cover Art 规则和 bug 模式
description: 封面补全的已知问题和正确流程：source 搜索路径、CAA、iTunes 三层 fallback
type: feedback
originSessionId: 9208d9a1-fa25-4144-b86c-48882cbc051d
---
## 规则 1：source 搜索路径要向上遍历到 SOURCE 根

**反例**：`search_dirs = [src.parent]` 只搜即时父目录。`in/李克勤/DISC 4/` 里的文件找不到 `in/李克勤/cover.jpg`。

**修复**：从 `src.parent` 向上遍历直到 SOURCE，把每一级都加入 `search_dirs`。

**How to apply**：新增文件搜索逻辑时，记住多碟专辑文件在 `DISC X/` 子目录，封面通常在父目录。

---

## 规则 2：三层封面 fallback 顺序

1. **source 本地文件**：`find_cover()` 搜索所有 ancestor 目录
2. **CAA (Cover Art Archive)**：MusicBrainz + coverartarchive.org，适合西方艺人
3. **iTunes Store album search**：`entity=album` 查询，适合华语/日韩流行，CAA 通常没有

**注意**：iTunes 用 `'albumart::{artist}::{album}'` 作 cache key（与 track 元数据 cache key 分开），避免混淆。

---

## 规则 3：ALBUM_META override 的专辑需手动确认封面

ALBUM_META override 跳过 AcoustID，MB Recording 等服务。这些专辑的 artist/album 名字可能与 MusicBrainz / iTunes 不匹配（如 Qobuz 专属合辑名），导致 CAA 和 iTunes 都返回 not_found。这种情况下需要手动放置 `folder.jpg` 到 source 目录。

**常见 not_found 原因**：
- Qobuz/流媒体平台专属合辑名（"Hi-Res Masters Metal Essentials" 等）→ 已通过 _normalize_album_for_search() 自动重试
- 极小众艺人 / 极稀有专辑
- 中文艺名无法与 MB 英文数据库匹配

---

## 规则 5：iTunes albumart cache 的 'not_found' 是粘性的

cache 一旦写入 `'not_found'`，下次运行直接 short-circuit 返回 False（不会触发 normalize 重试逻辑）。**当改进搜索逻辑后**（如新增 normalize、新增 fallback），需要清理旧的 not_found 条目：

```python
cache = {k:v for k,v in cache.items() if not (k.startswith('albumart::') and v=='not_found')}
```

**How to apply**：每次修改 `fetch_cover_itunes_album` 或 `_normalize_album_for_search` 后，清理 not_found cache 重跑一次。

---

## 规则 4：itunes_lookup 的 cache 包含 artwork 字段

`itunes_lookup()` 返回的 dict 包含 `'artwork'` 字段（artworkUrl600）。如果某条 cache 里没有该字段（旧版本缓存），重新运行不会自动补全（cache hit 直接返回旧数据）。如需刷新，删除对应 cache entry。
