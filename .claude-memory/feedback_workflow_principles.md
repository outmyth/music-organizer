---
name: 工作流原则（用户明确要求）
description: 用户反复强调的工作习惯，每次做完改动后必须遵守
type: feedback
originSessionId: 9208d9a1-fa25-4144-b86c-48882cbc051d
---
## 原则 1：每次改动后自动总结新发现的问题并写入 memory

用户不想每次都重新提醒，所有本次 session 发现的 bug、设计决策、新规则应在 session 结束前自动写入 memory 文件。

**Why**：以前反复在不同 session 犯同样的错误，因为没有持久化。

**How to apply**：每次 session 结束（或完成一个完整功能）时，检查是否有新的 bug pattern、设计决策、用户偏好需要记录。直接写，不要等用户提醒。

**双写规则**：memory 同时写到两个位置：
1. `~/.claude/projects/<hash>/memory/` — 本机 Claude Code auto-load 路径
2. `<repo>/.claude-memory/` — 提交到 git，跨机器/跨 session 持久化

写入新 memory 时，**两边都要更新**，然后 `git add .claude-memory/ && git commit && git push`。

---

## 原则 2：设计要自动化，不要依靠"下次提醒"

凡是需要每次手动检查/补救的步骤，都应该改成自动化逻辑。例如：
- source tag 写回 → 自动（writeback_to_source）
- cover art 补全 → 自动（三层 fallback）
- metadata 验证 → 自动（清理后用正确数据）

**Why**：用户的原话："这个应该自动做，而不是每次都要提醒你"。

---

## 原则 3：ALBUM_META 新增条目必须包含 year

每次新增 ALBUM_META 条目时，如果知道发行年份，必须加 `'year': 'YYYY'`。否则该专辑永远没有年份前缀（因为 override 非空时 AcoustID 被跳过）。

---

## 原则 4：流派归类偏好简洁

用户倾向于减少细分流派，用大类覆盖小类：
- Cantopop/Mandopop/J-Pop/K-Pop → **Pop**
- Choral/Choir → **Classical**

如果遇到类似场景（小众流派标签），优先考虑归入最接近的大类。

---

## 原则 5：完成后自动 git commit + push + 同步 SD 卡

每次功能完成后：
1. `git add` 相关文件 → `git commit` + `git push`
2. 重新运行 `python3 music_organizer.py`
3. 同步到 SD 卡：`python3 music_organizer.py --sync /Volumes/music_test --mirror`
4. 更新 memory

不要等用户提醒。
