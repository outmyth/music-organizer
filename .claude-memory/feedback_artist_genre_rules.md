---
name: ARTIST_GENRE 维护规则
description: 添加、删除、修改 ARTIST_GENRE 条目时必须遵守的规则，防止误分类
type: feedback
originSessionId: 9208d9a1-fa25-4144-b86c-48882cbc051d
---
## 规则 1：删除前必须检查子串依赖

审计报告输出「safe to remove」时不能直接删除，还需验证：该 key 是否作为子串覆盖了其他艺人名。

**反例**：`'唐朝': 'Metal'` 被审计标记为可删除（MB 能覆盖 `唐朝`），删除后导致 `唐朝乐队`（文件夹推断的 artist）的无 tag WAV 落到 Pop，因为 MB 对 `唐朝乐队` 返回空。

**How to apply**：删除某条目前，在 `.mb_cache.json` 里搜索是否有包含该 key 的其他 artist 且其 MB 值为空。脚本的 `_has_substring_dependents()` 函数现在自动做这个检查。

---

## 规则 2：ARTIST_GENRE 只匹配 artist / album_artist，不匹配 album

ARTIST_GENRE 的本意是「这个艺人属于这个流派」，不能用专辑标题来匹配，album 标题词汇过于宽泛。

**反例**：Pathfinder 专辑名「Beyond the Space, Beyond the Time」触发 `'beyond': 'Rock'`，整张专辑被错分为 Rock。

**How to apply**：`classify_genre` Step 1 只检查 `artist` 和 `album_artist`（已修复）。新增 ARTIST_GENRE 条目时无需担心这个问题，但如果发现某专辑被莫名分到错误流派，先检查专辑名是否含 ARTIST_GENRE 的某个 key。

---

## 规则 3：ARTIST_GENRE 两类用途要区分

| 用途 | 示例 | 能删吗 |
|------|------|--------|
| MB 找不到 / 返回空 | Pathfinder、信乐团、唐朝（覆盖 唐朝乐队） | 不能，除非 MB 能覆盖所有变体 |
| 故意纠正 MB 错误 | beyond (MB 说 Cantopop)、alison krauss (MB 说 Folk) | 永远不能删 |

审计冲突警告（`⚠️ ARTIST_GENRE conflicts with MusicBrainz`）里的条目通常是第二类，属于正常、故意的覆盖，每次运行都会出现，不需要处理。

---

## 规则 4：GENRE_MAP 中 metal 系全部映射到 Metal，不是 Rock

已修复的映射（music_organizer.py ~line 180）：
- power metal, symphonic metal, death metal, black metal, thrash metal, speed metal, progressive metal, gothic metal, doom metal → **Metal**
- metal, heavy metal → **Metal**

中文同样：金属、重金属 → **Metal**

如果将来新增 GENRE_MAP 条目，metal 相关一律归 Metal，不要归 Rock。
