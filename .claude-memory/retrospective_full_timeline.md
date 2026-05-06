---
name: 全部历史问题完整复盘
description: 61 个 commit 涉及的所有 bug 类别 + 反复踩坑的元教训汇总
type: feedback
---

## 元教训：反复出现的失败模式

下表是从 61 个 commit 总结出的**重复犯错的元 pattern**。每次踩坑后续修复都是因为**没在第一次就做全维度审计**：

| 元 pattern | 第一次表现 | 反复表现 | 根因 |
|-----------|-----------|---------|-----|
| **只修 symptom 不修 root** | WAV ID3 garble (`??`) → 加 mutagen fallback | INFO chunk + GBK 又 mojibake | 没列全 "WAV tag 存储位置 × 编码"矩阵 |
| **embedded tag 无条件信任** | `_clean_junk` 只滤 URL/Unknown | Qobuz "Hi-Res Masters" 被当成真 album | 没区分"语法非空"和"语义合法" |
| **ALBUM_META 单点缺字段** | 唐朝乐队 override 没 year | 后续每次新加 override 都可能漏 | 没有 schema/必填字段检查 |
| **cache key 不规范** | `_HERE` 相对/绝对路径混用 → AcoustID miss | 后来又出现 mb_rec cache key 类似问题 | 路径处理没有单一统一规则 |
| **fallback 链条互相覆盖** | iTunes 覆盖正确的 AcoustID album | inferred_only 没 discard 让后续服务再次覆盖 | 改一处但忘了同步 inferred_only 状态 |
| **集中 fix 一类 bug 没扫表** | 修 WAV mutagen 时只看 ID3 | INFO chunk 同样问题被忽略 | 缺乏"全表检查清单" |

**核心规则**：每次 fix bug 必须问：
1. 这个症状的所有可能触发路径都列出来了吗？
2. 同类 bug 还可能从哪个维度进来？
3. 我有没有把判断逻辑加进代码自动化？还是只手动 patch 了一次？

---

## Timeline：61 个 commit 按主题分组

### 1. 流派分类（11 处修复）

| commit | 问题 | 教训 |
|--------|------|-----|
| 4cd7473 | 中文艺人 MB 不命中 → 全归 Classical | classify_genre 顺序：local → MB → embedded → 中文兜底 |
| 40d588e | CUE album 默认归 Classical | CUE 也要走 classify_genre，不能跳过 |
| e69c61a | Pathfinder/Megadeth 等被分到 Rock | metal 子流派全归 Metal（power/symphonic/death/black/thrash 等） |
| 41460b5 | 唐朝乐队硬编码 Chinese Rock | ARTIST_GENRE 直接写最终值，避免中间映射 |
| 498b6c3 | Pathfinder CUE 流派错（album 含 "beyond"） | classify_genre 只查 artist/album_artist，**不**查 album（album 名歧义） |
| 9ad902b | 唐朝无 tag WAV 全归 Pop | 删 ARTIST_GENRE 条目前要查子串依赖（'唐朝' 覆盖 '唐朝乐队'） |
| d7cf70a | 陈慧娴 错分 Mandopop | 港粤艺人即使 MB 标为 Mandopop 也要本地 override |
| 1bc6106 | Cantopop/Mandopop/Chinese Rock/J-Pop/K-Pop 太碎 | 用户偏好简洁：全归 Pop/Rock |
| Choral 合并（本次） | Choral 类只有 2 张专辑无意义 | 同上：小众流派归大类 |
| BAV 合辑被拆（本次） | BAV Vol.1 被按曲目艺人拆成 Folk+Pop+Jazz | ALBUM_META override 的 genre 强制覆盖 per-track |
| 8ab1e4e/ad7a444 | 缺乏审计 | 自动 audit ARTIST_GENRE/ALBUM_META 与 MB 的冲突 |

**记忆**：[ARTIST_GENRE 维护规则](feedback_artist_genre_rules.md)

---

### 2. AcoustID + 合辑检测（7 处修复）

| commit | 问题 | 教训 |
|--------|------|-----|
| a9d6236 | 无 tag 文件无 metadata | 接 AcoustID acoustic fingerprint |
| f88d6cc | AcoustID 返回空 | meta 参数 URL 编码 bug |
| 116d294 | placeholder album 没有被替换 | 用 inferred_only 标记 path-inferred 字段，AcoustID 可覆盖 |
| e4d7afe | 跨专辑合辑被强行套到 folder name | majority-vote：≥50% 同 album → 用之，否则保留 folder name |
| 4dd4167 | 唐朝乐队多专辑混合 | ALBUM_META 强制 override 跳过 majority-vote |
| 7407bd4 | `is_compilation` NameError 静默吞掉 date | 移除 stale guard |
| 574536e | AcoustID hit 但 cache miss | _HERE 必须 `.resolve()`，cache key 用绝对路径 |

**记忆**：[metadata pipeline 已知 bug 模式](feedback_metadata_pipeline_bugs.md)

---

### 3. CUE 拆轨（4 处修复）

| commit | 问题 | 教训 |
|--------|------|-----|
| ad380d2 | CUE track 1 无年份 | REM DATE 在 TRACK 块内时回填 track 1 |
| e0ee7ad | 多碟 CUE album 名带 "CDn" 后缀 | strip "CD1/CD2" 让两碟落到同一文件夹 |
| - | image WAV 重复处理 | already_cue 比较要 case-insensitive |
| - | CUE 无 PERFORMER → ARTIST_GENRE 不命中 | 从 "Artist - Album.cue" 文件名推断 artist |

**记忆**：[CUE 处理已知 bug 模式](feedback_cue_processing_bugs.md)

---

### 4. WAV tag 解码（3 处修复，本次新增）

| commit | 问题 | 教训 |
|--------|------|-----|
| 305d4b1 | WAV ID3 chunk 用 latin-1 → garble `??` | mutagen ID3 fallback |
| 574536e | `_has_garbled` 在 cleaned result 上调用 | 用 raw ffprobe tags 检测 |
| **本次** | INFO chunk + GBK → mojibake (`¬��͢`) | 直接读 RIFF INFO 字节，按 GBK/Big5/UTF-8/latin-1 顺序解码 |

**关键反省**：305d4b1 修 ID3 时应该已经把 INFO chunk 也看一遍。**全维度审计原则**就是从这里来的。

**记忆**：[WAV tag 解码完整审计](feedback_wav_decoding_full_audit.md)

---

### 5. 文件名 & embedded tag 反例（4 处）

| commit | 问题 | 教训 |
|--------|------|-----|
| 5cb9bba | URL/watermark 进 artist tag | `_clean_junk` + `_JUNK_TAG_RE` |
| 3addd43 | "Unknown Artist" / "Unknown Title" | `_PLACEHOLDER_TAGS` 集合 |
| 本次 Sally Yeh | 嵌入 album 是空但 iTunes 写错 album | inferred_only 必须 discard |
| 本次 Pink Floyd | embedded album = "Qobuz Hi-Res Masters" | _SAMPLER_ALBUM_RE 检测 + 用 filename `[…]` |

**记忆**：[embedded tag 可疑模式](feedback_embedded_tag_skepticism.md)、[文件名约定](feedback_filename_conventions.md)

---

### 6. Path inference & infer_from_path（3 处）

| commit | 问题 | 教训 |
|--------|------|-----|
| 503bf31 | DISC/CD 子目录被当 album | _GENERIC_FOLDER_RE 匹配，跳到 grandparent |
| 503bf31 | "title - artist" vs "artist - title" | g3 在 ancestors_lower / ARTIST_GENRE / MB cache 时反转 |
| 本次 Qobuz | 文件名 `[Album]` `「Artist」` 没解析 | 加正则提取 |

---

### 7. Cover art（4 处）

| commit | 问题 | 教训 |
|--------|------|-----|
| 72dc688 | 缺封面 | CAA 自动下载 |
| 本次 | 父目录有 cover 但 DISC X/ 子目录文件找不到 | search_dirs 从 src.parent 向上遍历到 SOURCE |
| 本次 | CAA 不覆盖华语艺人 | iTunes Store album search 兜底 |
| 本次 | Qobuz/SACD 平台合辑名查不到 | _normalize_album_for_search() 剥离平台后缀重试 |

**记忆**：[Cover Art 规则和 bug 模式](feedback_cover_art_rules.md)

---

### 8. Source 文件 metadata 写回（本次新增）

| 问题 | 教训 |
|-----|-----|
| enrichment 发现的 metadata 只写 dest，source 永远空 | 加 `writeback_to_source()` 幂等回写。原因：用户问"没写回不就丢失了吗" |
| ffmpeg 不识别 `.wav.tmp` | temp 后缀应保留真扩展名：`.__tmp__.wav` |

---

### 9. Various Artists / 合辑路由（2 处）

| commit | 问题 | 教训 |
|--------|------|-----|
| 5729ecd | tribute album 全归到 Various 失去艺人 | 当 album_artist 是 Various marker 且非来自 ALBUM_META override 时，按真 artist 路由 |
| 本次 BAV | 合辑被按曲目艺人拆开 | ALBUM_META genre 强制覆盖 per-track classify |

---

### 10. 编码统一（2 处）

| commit | 问题 | 教训 |
|-----|-----|-----|
| ef5e403 | 陳慧嫻 vs 陈慧娴 分两个文件夹 | OpenCC trad→simp canonicalize artist |
| 857c56d | "卢冠廷&莫文蔚" / "卢冠廷, 莫文蔚" 分两组 | normalize_multi_artist 统一为 ", " |

---

### 11. SD 卡同步（4 处）

| commit | 问题 | 教训 |
|--------|------|-----|
| 57d4124 | 缺 sync 命令 | --sync 调 rsync |
| 22847ac | rsync 删除 Sony Walkman 系统目录 | --exclude 保护 `MUSIC_DB`、`Capability_*` |
| 76befcd | source 里 .DS_Store / ._* 污染 SD | sync 前 pre-clean source |

---

### 12. 外部 API 集成（4 处）

| commit | 服务 | 用途 |
|--------|-----|-----|
| a9d6236 | AcoustID | acoustic fingerprint 主路径 |
| 4cd7473 | MusicBrainz Artist | genre 查询 |
| 622eba8 | MB Recording | album/date 二级查询 |
| 8852276 | iTunes Search | album/date/genre + 封面（华语强项）|
| 57cef4d | Last.fm + Discogs | 元数据补充（Last.fm 注册被 firewall 拒，已停用）|

---

## 重复问题主题汇总（出现 >1 次的"惯犯"）

### 主题 A：流派分类被 album 误判

出现过：beyond、iron、giant 等 ARTIST_GENRE key 被 album 名包含 → 整张专辑流派错。

**已封堵**：classify_genre 只查 artist/album_artist。

### 主题 B：AcoustID 设置 album 后没清 inferred_only

出现过 2 次（Sally Yeh + 后续修复中）。每条 album 赋值分支都要 `inferred_only.discard('album')`。

### 主题 C：ALBUM_META 添加新条目缺关键字段

唐朝乐队漏 year（修复 b45c4cf），可能下次新增其他 override 时再忘其它字段。

**TODO**：加自动审计：`ALBUM_META` 条目缺 year/genre 时启动时打印 warning。

### 主题 D：cache 路径/key 不一致

`_HERE` 没 resolve、cache 里出现绝对+相对两种 key 共存。**全脚本 path handling 应该统一约定**：所有持久化 key 用绝对路径。

### 主题 E：embedded tag 被流媒体平台污染

Qobuz、SACD COLLECTION、实体CD版、盒装版 等平台后缀。每次新发现一个就加规则。

**TODO**：建立"已知 sampler/edition keyword 黑名单"，遇到含此关键词的 album 自动尝试 filename `[…]` 替换。

---

## 自我审视清单（每次 fix 前必过）

1. ☐ 我的 fix 解决的是 symptom 还是 root cause？
2. ☐ 同类 bug 还能从哪个维度进来？（编码、平台、文件类型、cache 状态、enrichment 顺序）
3. ☐ 已有 memory 文件里有类似 pattern 吗？
4. ☐ 修完代码 → 写 memory（双写）→ commit + push 都做了？
5. ☐ 跑两遍脚本验证幂等？
6. ☐ 同步 SD 卡？
