# Music Organizer v2

> 🌐 [English](README.md) · **中文**

自动扫描本地音乐文件，读取 metadata，整理文件结构并生成 M3U 播放列表。

兼容设备：Sony HAP-Z1ES、Sony Walkman（NW-WM1Z / WM1A / NW-WM1ZM2）、Chord Mojo+Poly / Hugo、Lotoo PAW Gold 2017。

> 📂 **查看 [`examples/`](examples/)** 目录——里面有手工构造的输入/输出结构演示（0 字节占位音频 + 真实可读的 `.m3u` / `.json` 内容）。

---

## 依赖

- Python 3.8+
- [ffmpeg](https://ffmpeg.org/)（含 ffprobe）

```bash
# macOS
brew install ffmpeg
```

---

## 目录结构

```
<project-dir>/
├── in/                        ← 原始音乐文件（输入）
│   ├── Jazz/                  ← 普通专辑（直接按流派/艺术家存放）
│   │   └── Miles Davis/
│   └── Test/                  ← 特殊目录：测试子集（见下方说明）
│       ├── Beyerdynamic T1/   ← 分类标签（可自定义）
│       └── Audio Format/      ← 分类标签（可自定义）
└── out/                       ← 整理后输出（可整盘拷到 SD 卡根目录）
    ├── MUSIC/                 ← 注意大写！Sony WM1A 只扫描 /MUSIC/
    │   ├── Jazz/              ← 普通文件按流派整理
    │   │   └── Miles Davis/
    │   │       └── (1959) Kind of Blue/
    │   ├── Classical/
    │   ├── Cantopop/
    │   ├── Mandopop/
    │   ├── Various/
    │   ├── Test/              ← Test 文件单独隔离
    │   │   ├── Beyerdynamic T1/
    │   │   │   └── Jazz/Miles Davis/...
    │   │   └── Audio Format/
    │   │       └── Mandopop/陳慧嫻/...
    │   └── Playlists/         ← Sony WM1A 专用播放列表目录（内容同 playlists/）
    │       ├── All.m3u
    │       ├── Album_*.m3u
    │       └── ...
    └── playlists/             ← Lotoo PAW Gold 2017 / Chord Poly / 通用
        ├── All.m3u                     ← 含所有曲目（含 Test）
        ├── Album_<Artist> - <Album>.m3u   ← 每张专辑
        ├── Artist_<Artist>.m3u            ← 每位艺术家
        ├── Format_<FMT>.m3u               ← 按格式分组（FLAC/DSD/WAV/…）
        ├── Test_<Category>.m3u            ← Test 子集每个分类一个
        └── music_index.json               ← --no-json 时不生成
```

> **扁平目录 + `<Category>_<Name>` 统一命名**：Lotoo PAW Gold 2017 的播放列表扫描器**不会递归子目录**，所以所有播放列表都在 `playlists/` 根目录。`Album_` / `Artist_` / `Format_` / `Test_` 前缀让同类播放列表在播放器界面里自动聚在一起。扩展名用 `.m3u` 而不是 `.m3u8`，因为 Chord Poly GoFigure 对 `.m3u8` 不可靠。

### Test/ 目录说明

`in/Test/` 是一个**保留名称**，用于隔离测试或专项对比用的音乐文件。

**命名规则：**
- `in/Test/` 下的**第一级子目录名**作为分类标签（category），例如 `Beyerdynamic T1`、`Audio Format`
- 分类标签可以是耳机型号、测试场景、音频格式对比等任意名称
- 分类下可继续按任意方式存放音乐（支持普通文件和 CUE+整轨）

**输出行为（与普通文件的区别）：**

| 项目 | 普通文件 | Test 文件 |
|------|----------|-----------|
| 输出路径 | `out/MUSIC/{Genre}/{Artist}/...` | `out/MUSIC/Test/{Category}/{Genre}/{Artist}/...` |
| All.m3u | 包含 | **包含** |
| Album_* / Artist_* / Format_* | 包含 | **不包含** |
| 专属播放列表 | 无 | `playlists/Test_{Category}.m3u` |

> 同一个 `Test/{Category}/` 下的所有文件会合并到同一个 `Test_{Category}.m3u`，文件名中的冒号、问号、单引号等 FAT32/exFAT 敏感字符会被清理。

---

## 用法

```bash
cd <project-dir>

# 默认：强制覆盖所有文件 + 生成 music_index.json
python3 music_organizer.py

# 增量模式：跳过大小相同的已有文件
python3 music_organizer.py --no-force

# 不生成 music_index.json
python3 music_organizer.py --no-json

# 增量模式 + 不生成 JSON
python3 music_organizer.py --no-force --no-json
```

### 参数说明

| 参数 | 说明 |
|------|------|
| `--no-force` | 跳过大小相同的已有文件（默认：强制覆盖） |
| `--no-json` | 不生成 `music_index.json`（默认：生成） |

---

## 支持格式

| 格式 | 类型 |
|------|------|
| FLAC | 无损压缩 |
| MP3 | 有损压缩 |
| M4A / AAC | Apple 格式 |
| WAV / AIFF | 无损非压缩 |
| DSF / DFF | DSD（适合 HAP-Z1ES） |
| OGG / Opus | 开源格式 |
| WMA / APE | 其他格式 |

CUE+整轨文件（`.cue` + `.flac` / `.wav`）会通过 ffmpeg 自动拆分为单曲。

---

## 流程说明

```
in/ 原始文件
   ↓
① 扫描所有音频文件 & CUE+整轨专辑
   ↓
② CUE 整轨拆分（ffmpeg，写入临时目录）
   ↓
③ 读取 metadata（ffprobe）
     → 应用 ALBUM_META 专辑级覆盖
     → 应用 ARTIST_GENRE / GENRE_MAP 流派映射
     → 从文件名/路径补全缺失字段
   ↓
④ 按 流派/艺术家/(年份) 专辑/ 复制到 out/MUSIC/（大写，Sony WM1A 要求）
     → 同时写入正确的 metadata 标签（ffmpeg -metadata）
     → 复制封面图 → folder.jpg
   ↓
⑤ 孤儿文件清理（删除旧路径残留文件及空目录）
   ↓
⑥ 生成 M3U 播放列表（全量重建，扁平 `<Category>_<Name>.m3u` 命名）
     → All.m3u、Album_*、Artist_*、Format_*
     → Test/ 子集生成 Test_<Category>.m3u
     → 同时写到 playlists/ 和 MUSIC/Playlists/ 两处
     → UTF-8 + BOM + CRLF；路径相对播放列表文件自身所在目录
   ↓
⑦ 生成 music_index.json（--no-json 时跳过）
```

---

## 流派自动识别规则

脚本通过以下优先级判断流派：

1. **ALBUM_META 专辑级覆盖**（`music_organizer.py` 顶部 `ALBUM_META` 字典）
2. **ARTIST_GENRE 艺术家映射**（例：`王菲 → Cantopop`）
3. **GENRE_MAP 标签规范化**（例：`vocal jazz → Jazz`）
4. **JAZZ_TITLES 曲名关键词**（匹配常见爵士标准曲）
5. **含中文字符** → `Mandopop`（兜底）
6. **`Various`**（最终兜底）

---

## 特殊文件名解析器

对于 metadata 缺失或错误的已知专辑，`ALBUM_META` 中可指定 `parse` 字段启用对应解析器：

| 解析器 | 适用场景 | 规则 |
|--------|----------|------|
| `bav` | Best Audiophile Voices | `艺术家_曲名.flac` |
| `violin_wav` | 古典小提琴名盘 | `NN.英文曲名  中文曲名.wav` |
| `mozart_flac` | 莫扎特第21/24协奏曲 | `N.曲名.flac` |
| `levine_wav` | 舒伯特/莱文 WAV | `NN.曲名.wav` |

---

## 缺失 tag 的处理

脚本运行结束后会列出 metadata 不完整的文件。推荐用以下工具补全后重跑：

- **[MusicBrainz Picard](https://picard.musicbrainz.org/)** — GUI，自动识别并嵌入标准 tag 和封面
- **[beets](https://beets.io/)** — 命令行，批量处理能力更强

补全 tag 后执行：

```bash
python3 music_organizer.py
```

---

## 自定义配置

所有配置均在 `music_organizer.py` 顶部：

| 变量 | 说明 |
|------|------|
| `SOURCE` | 原始文件目录（`<project-dir>/in`） |
| `DEST` | 输出目录（`<project-dir>/out`） |
| `ARTIST_GENRE` | 艺术家 → 流派 映射 |
| `GENRE_MAP` | tag 流派字符串规范化 |
| `ALBUM_META` | 专辑级 metadata 覆盖与解析器指定 |

---

## SD 卡 DAP 兼容性说明

把 `out/` 整盘拷到 SD 卡根目录即可在下列播放器上直接使用。脚本在播放列表生成时针对各家固件做了以下兼容性处理：

| 固件/设备 | 已处理的坑 | 对应实现 |
|-----------|-----------|---------|
| **Sony WM1A / WM1ZM2** | 只索引 `/MUSIC/`（大写），只扫描 `MUSIC/Playlists/` 下的播放列表 | 音乐目录命名 `MUSIC/`；播放列表同时写到 `MUSIC/Playlists/` |
| **Lotoo PAW Gold 2017** | 播放列表扫描器**不递归子目录**；需要 UTF-8 BOM 才能正确显示中文 | 扁平目录 + `<Category>_<Name>.m3u` 前缀；文件写入带 BOM |
| **Chord Poly (GoFigure)** | 对 `.m3u8` 扩展名不可靠；路径解析遵循标准 M3U（相对播放列表文件自身） | 扩展名用 `.m3u`；路径用 `os.path.relpath(track, pl_file.parent)` |
| **FAT32 / exFAT 文件系统** | 半角冒号、问号、单引号（包括中文弯引号 `‘ ’`）、感叹号会让扫描器出错 | `sanitize()` 清理 `: ： ' ‘ ’ ! * ? \| " < >` 及其他非法字符 |

**播放列表相对路径规范（重要）：**

```
#EXTM3U
#EXTENC:UTF-8

#EXTINF:243,Miles Davis - So What
../MUSIC/Jazz/Miles Davis/(1959) Kind of Blue/01 - So What.flac
```

- 路径相对**播放列表文件自身所在目录**（标准 M3U 语义），不是"相对 SD 卡根"
- 文件编码：UTF-8 + BOM（`EF BB BF`），行尾 CRLF
- 扩展名：`.m3u`（不用 `.m3u8`）

**Chord Poly MPD 模式的例外：** 如果用的是 Poly 的 MPD 服务器模式（而不是 SD 卡本地播放），MPD 是按 `music_directory` 配置项解析路径而非播放列表自身目录——这种场景需要自行调整 MPD 配置 `music_directory = /path/to/out/MUSIC/`。
