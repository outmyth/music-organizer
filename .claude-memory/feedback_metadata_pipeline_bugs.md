---
name: metadata pipeline 已知 bug 模式
description: enrichment 流程中反复出现的六类 bug，包括 cache key 绝对路径、inferred_only 未清除、WAV garble 检测、iTunes 覆盖 AcoustID 等
type: feedback
originSessionId: 9208d9a1-fa25-4144-b86c-48882cbc051d
---
## Bug 1：_HERE 未 resolve() 导致 AcoustID cache key 不一致

**症状**：AcoustID cache 明明有该文件的数据，但 enrichment 时 cache miss，文件重新走 AcoustID 或用错数据。

**根因**：`_HERE = Path(__file__).parent` 不加 `.resolve()`。以相对路径运行脚本时 `__file__='music_organizer.py'`，`_HERE=Path('.')`，cache key 变成 `in/...` 而非 `/Users/.../in/...`，与之前绝对路径写入的 entry 不匹配。

**修复**：`_HERE = Path(__file__).resolve().parent`

**How to apply**：一旦发现 AcoustID cache 命中但 enrichment 结果不对，先检查 cache key 是相对还是绝对路径。

---

## Bug 2：AcoustID 设置 album 后未 discard inferred_only，iTunes 覆盖正确值

**症状**：AcoustID 返回正确 album（如 `瀟灑走一回`），但最终输出用了 iTunes 返回的错误 album（如 `90年代廣東得獎歌`）。

**根因**：AcoustID 把 album 写入 `meta['album']` 后，`inferred_only` 里的 `'album'` 没有被 `discard()`。`_still_needs()` 看到 `'album' in inf` 仍为 True，允许 iTunes 覆盖。

**修复**：赋值后立即 `inferred_only.discard('album')`（majority_album 和 per-track 两条分支都要加）。

**How to apply**：发现某专辑 album 被后续服务覆盖时，检查 `inferred_only` 在 AcoustID 赋值后是否正确清除。

---

## Bug 3：AcoustID 确认的 artist/title 仍在 inferred_only，_text_ok=False，文字服务不填 date

**症状**：AcoustID 返回了 album 和 artist，但 date 仍空，MB Recording/iTunes 没有被调用。

**根因**：infer_from_path 填的 artist 在 `inferred_only` 里，`_text_ok` 检查 `'artist' not in inferred_only` → False，文字服务全跳过。即使 AcoustID acoustic fingerprint 确认了 artist 名字一致，也无法触发。

**修复**：AcoustID 返回 artist/title 与 meta 中值相同时，从 `inferred_only` 中 discard。

**How to apply**：文件无嵌入 tag，artist 来自文件夹推断，AcoustID 确认 artist 正确但 date 仍空时，检查 `inferred_only` 是否阻断了文字服务。

---

## Bug 4：_has_garbled 在 cleaned result 上调用，WAV 混合乱码逃过 mutagen fallback

**症状**：WAV 文件有嵌入 tag，但 album 如 `2020???????????` 被当成有效值，最终专辑文件夹名截断。

**根因**：`_has_garbled(result)` 被调用在 `_clean_junk` 处理后的 result 上。`'??'` 被 clean 成 `''`（falsy），`_has_garbled` 返回 False，mutagen fallback 不触发。`'2020???????????'` 以数字开头，不被 `_ALL_JUNK_CHARS_RE` 匹配，直接当成正常 album 使用。

**修复**：改为 `_has_garbled(tags)` — 在 raw ffprobe tags 上检测（clean 之前）。

**How to apply**：WAV 文件 album/title 出现截断或乱码时，先 `ffprobe -show_format` 看 raw tags，确认是否有重复 key 且最后一个是乱码。

---

## Bug 5：source 文件 tag 永不写回，丢失 enrichment 结果

**症状**：enrichment 发现了 artist/album/date，out/ 目录正确，但 in/ source 文件 tag 仍空。删除 out/ 重跑时依赖 JSON cache，若 cache 丢失则需重查外部服务。

**根因**：所有 tag 写入只发生在 `copy_with_meta(fp, dest_fp, ...)` — 写到 dest 文件，source 从未被修改。

**修复**：加 `writeback_to_source(fp, meta, original_meta)` 函数：
- 只写原来为空的字段（不覆盖用户的 source tag）
- ffmpeg + `.__tmp__.ext` 临时文件 atomic replace
- `needs_tag_write` 为 True 时在 dest 写完后调用
- 幂等：第二次运行 delta 为空，不触发

**How to apply**：每次改动 enrichment 逻辑后，运行两次脚本，第二次应零 `🔖`。

---

## Bug 6：ALBUM_META override 使 AcoustID block 完全跳过，年份永远无法填入

**症状**：`ALBUM_META` 有该 folder 的 override（如 `'唐朝乐队'`），但 `year` 没填，最终专辑文件夹无年份前缀。

**根因**：`if not override and (...)` 保护整个 AcoustID block。一旦 override 非空，AcoustID、date 填充全部跳过。ALBUM_META 必须显式包含 `'year'` 才能有年份。

**修复**：在 ALBUM_META 条目里加 `'year': 'YYYY'`。

**How to apply**：新增 ALBUM_META 条目时，如果知道年份，**一定要加 `'year'` 字段**，否则该 album 永远没有年份前缀。
