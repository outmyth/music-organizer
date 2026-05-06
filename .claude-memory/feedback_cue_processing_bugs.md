---
name: CUE 处理已知 bug 模式
description: CUE+image 拆轨时已发现并修复的四类 bug，以及排查方法
type: feedback
originSessionId: 9208d9a1-fa25-4144-b86c-48882cbc051d
---
以下 bug 均已修复（2026-05-05），记录在此以防同类问题复发。

## Bug 1：CUE image 被当成普通音频文件重复处理

**症状**：CUE image WAV 出现在 out/ 的错误流派目录（通常是 Pop），artist 来自文件夹名而非 CUE 内容。

**根因**：`already_cue` 检查用了大小写敏感的 Path 比较。CUE 文件里写 `FILE "artist.WAV" WAVE`，实际文件是 `artist.wav`，导致比较失败，image 被再次处理为个人文件。

**修复**：`str(ref).lower() == str(f).lower()` 做大小写不敏感比较（music_organizer.py ~line 1197）。

**How to apply**：遇到 CUE 专辑的 WAV image 出现在 out/ 某流派目录时，先检查 CUE FILE 行的扩展名大小写。

---

## Bug 2：Track 01 年份丢失（REM DATE 在 TRACK 块内部）

**症状**：同一 CUE 专辑的 track 01 输出到 `artist/album/`（无年份），其余曲目输出到 `artist/(1997) album/`，产生两个目录。

**根因**：CUE 里 `REM DATE` 写在 `TRACK 01 AUDIO` 内部而非文件头。parse_cue 创建 track 01 dict 时 `album_date=''`，后来解析到日期才更新全局变量，但 track 01 已创建完毕。

**修复**：解析到 `REM DATE` 时，如果 `cur_track['album_date']` 为空则回填（~line 956）。

**How to apply**：发现同一专辑出现「有年份」和「无年份」两个目录时，用 `cat` 看 CUE 文件头，确认 REM DATE 是否在 TRACK 块内。

---

## Bug 3：ARTIST_GENRE 用 album 字段匹配导致误分类

**症状**：专辑名含乐队名子串（如 "Beyond the Space, Beyond the Time"）触发 BEYOND 乐队的 Rock 规则，整张专辑被错分到 Rock。

**根因**：`classify_genre` 对 ARTIST_GENRE 的匹配同时检查 `artist` 和 `album`，album 标题中的普通词汇很容易误命中乐队名。

**修复**：ARTIST_GENRE 只对比 `artist` 和 `album_artist` 字段，不对比 `album`（~line 861）。

**How to apply**：发现某专辑流派明显错误、且专辑标题含常见词（beyond、iron、giant 等），检查是否触发了同名 ARTIST_GENRE key。

---

## Bug 4：CUE 无 PERFORMER 时 artist 为空，导致 ARTIST_GENRE 无法匹配

**症状**：ARTIST_GENRE 已有正确 key，但 CUE 拆轨结果仍归到错误流派。

**根因**：CUE 文件没有顶层 `PERFORMER` 行，parse_cue 返回 `album_artist=''`，`classify_genre` 用空字符串查找，ARTIST_GENRE 自然不匹配。

**修复**：`parse_cue` 在 PERFORMER 缺失时从 CUE 文件名推断 artist（`"Artist - Album.cue"` 格式）（~line 921）。

**How to apply**：CUE 专辑流派错误时，先 `head -5 xxx.cue` 检查是否有 `PERFORMER` 行。若无，确认文件名是否符合 `Artist - Album.cue` 格式。
