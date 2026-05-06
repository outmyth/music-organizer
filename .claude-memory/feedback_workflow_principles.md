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

---

## 原则 6：整理新音乐文件时的自动复盘流程（用户 2026-05-05 明确要求）

每次整理新加入的音乐文件后，**主动**做以下复盘：

### 触发条件
新增 source 文件（in/ 下出现新的艺人/专辑/合辑），或运行脚本发现：
- 某 album 的 metadata 不正确（artist/title/year/album）
- 某 album 流派归类错误
- 某 album 没有封面
- 文件名约定/编码方式之前没见过
- 流媒体平台/下载源使用了新的 marketing 名

### 复盘动作（**自动执行，不要等提醒**）

1. **诊断根因**：不要只修当前症状。问"这个错误模式以前见过吗？同类文件以后还会出现吗？"
2. **修复代码**：把判断逻辑加进脚本（自动化），不要靠每次手动 patch 单个文件
3. **写入 memory**：
   - 如果是新 bug pattern → `feedback_<topic>_bugs.md`（或更新现有的）
   - 如果是新文件名/tag 约定 → `feedback_filename_conventions.md`
   - 如果是 embedded tag 反例 → `feedback_embedded_tag_skepticism.md`
   - 如果是用户偏好（流派合并、专辑名清理等）→ `feedback_workflow_principles.md`
4. **双写**：同时写到 `~/.claude/projects/<hash>/memory/` 和 `<repo>/.claude-memory/`
5. **更新 MEMORY.md 索引**（如果是新文件）
6. **`git add .claude-memory/ <相关代码文件> && git commit && git push`**
7. 同步 SD 卡（如果 out/ 内容变了）

### 反例：不要做的事

- ❌ 只修代码不写 memory（下次 session 又会犯）
- ❌ 只写 memory 不修代码（用户每次都要发现并提醒）
- ❌ 写了 memory 但只放 `~/.claude/`（换机器丢失）
- ❌ 等用户问"为什么之前没识别"才复盘（应主动复盘）

---

## 原则 7：autonomous mode — 不要反复请求权限（用户 2026-05-06 明确要求）

用户原话："能不能不要问我要权限了 直接做 我可以给你所需要的权限"

意味着：
- 直接执行 git commit / push、运行脚本、修改源文件、写 memory，**不要先问"要不要做"**
- 如果某操作权限被系统拦截，重试或换路径，但不要每次都问用户确认
- 用户已经在 session 开始时给了所有需要的访问权（repo / shell / SD card / memory）

例外（仍要确认）：
- 删除大量数据（rm -rf 大目录、git reset --hard 等不可逆动作）
- 修改 `~/.claude/` 之外的全局配置
- 涉及外部系统的不可逆动作（force push 到 main、删 GitHub branch）

### 模板：复盘文档至少包含

```
## 错误判断 vs 应有的警觉
| 当时的逻辑 | 应识别的信号 |
|----|----|
## 根本原因
（一句话说清，避免泛泛而谈）
## 自动化规则（已加入代码 / TODO）
## 教训
```
