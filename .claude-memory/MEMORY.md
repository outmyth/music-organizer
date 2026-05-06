# Memory Index

- [CUE 处理已知 bug 模式](feedback_cue_processing_bugs.md) — CUE+image 拆轨的四类已知 bug 和排查方法（大小写、年份回填、album 误匹配、无 PERFORMER）
- [ARTIST_GENRE 维护规则](feedback_artist_genre_rules.md) — 添加/删除 ARTIST_GENRE 条目时的规则，防止子串误删、album 误匹配、metal 归 Rock 等问题
- [metadata pipeline 已知 bug 模式](feedback_metadata_pipeline_bugs.md) — enrichment 流程六类 bug：cache key 绝对路径、inferred_only 未清除、WAV garble 检测、iTunes 覆盖 AcoustID、source 不写回、ALBUM_META 缺 year
- [Cover Art 规则和 bug 模式](feedback_cover_art_rules.md) — 封面三层 fallback（source→CAA→iTunes），source 搜索需向上遍历，Qobuz 合辑名无法匹配
- [工作流原则](feedback_workflow_principles.md) — 用户要求：改动后自动写 memory、自动化而非手动补救、ALBUM_META 必含 year、流派偏简洁、完成后自动 commit+push+sync
- [embedded tag 可疑模式](feedback_embedded_tag_skepticism.md) — 流媒体/下载源把营销名写进 album tag（Qobuz Hi-Res Masters 等），filename `[…]` `「…」` 才是真值
- [文件名约定](feedback_filename_conventions.md) — Qobuz `[Album]`+`「Artist」`、SACD COLLECTION、实体CD版/盒装版后缀的解析规则
- [WAV tag 解码完整审计](feedback_wav_decoding_full_audit.md) — 元教训：修同类 bug 必须做全维度审计，不只修 symptom（WAV 多种 tag 存储 × 多种编码，INFO chunk + GBK 是国内 rip 主路径）
- [全部历史问题完整复盘](retrospective_full_timeline.md) — 61 commit 按 12 主题分类，5 个反复犯错的元 pattern，自我审视清单（每次 fix 前必过）
