# Music Organizer — AI Assistant Prompt

> 把这段内容作为 system prompt 或首条消息发给任意 AI 模型，即可获得针对本项目的精准协助。

---

## 项目概述

这是一个本地音乐文件整理脚本（`music_organizer.py`），运行在 macOS，可放置在任意目录下运行。

**功能：**
- 扫描 `in/` 目录下的音频文件，用 ffprobe 读取 metadata
- 按 `流派/艺术家/(年份) 专辑/` 结构整理复制到 `out/` 目录
- 自动拆分 CUE+整轨文件（via ffmpeg）
- 生成 M3U 播放列表（Sony HAP-Z1ES / Walkman / Chord Poly 兼容）
- 每次运行后清理孤儿文件（metadata 变更导致路径变化时自动删除旧文件）

**目标设备：** Sony HAP-Z1ES、Sony Walkman NW-WM1Z/WM1A/NW-WM1ZM2、Chord Mojo+Poly / Hugo
（**不支持** Lotoo PAW Gold 2017 — 路径要求与 Chord Poly 互斥）

---

## 目录结构

```
<project-dir>/
├── music_organizer.py   ← 主脚本
├── in/                  ← 输入：原始音乐文件
│   ├── {普通专辑}/
│   └── Test/            ← 保留名称：测试子集（见下方说明）
│       └── {Category}/  ← 第一级子目录名即为分类标签
└── out/                                    ← 输出（整盘拷到 SD 卡根目录）
    ├── MUSIC/                              ← 大写！Sony WM1A 只扫描 /MUSIC/
    │   ├── {Genre}/
    │   │   └── {Artist}/
    │   │       └── ({Year}) {Album}/
    │   │           ├── {NN} - {Title}.{ext}
    │   │           └── folder.jpg
    │   └── Test/                           ← Test 文件隔离在此
    │       └── {Category}/
    │           └── {Genre}/{Artist}/({Year}) {Album}/
    ├── All.m3u                             ← 含所有曲目（含 Test）
    ├── Album_{Artist} - {Album}.m3u        ← 每张专辑
    ├── Artist_{Artist}.m3u                 ← 每位艺术家
    ├── Format_{FORMAT}.m3u                 ← 每种格式
    └── Test_{Category}.m3u                 ← 每个 Test 分类
```

**命名规范**：`<Category>_<Name>.m3u`——下划线分隔类别和名称，连字符 ` - ` 分隔名称内部字段（如 `Album_Miles Davis - Kind of Blue.m3u`）。所有 .m3u 都直接放在 SD 卡根（`out/`），是 Sony Walkman 与 Chord Poly 唯一都能正确解析路径的位置。

### Test/ 目录规则

`in/Test/` 是脚本识别的**保留目录名**，其直接子目录名作为分类标签（category）。

- **输出路径**：`out/MUSIC/Test/{Category}/{Genre}/{Artist}/...`（与普通文件隔离）
- **All.m3u**：包含所有曲目（含 Test）
- **排除分类播放列表**：Test 曲目不出现在 `Album_*`、`Artist_*`、`Format_*` 中
- **独立播放列表**：每个 category 生成一个 `Test_{Category}.m3u`
- **category 命名示例**：耳机型号（`Beyerdynamic T1`）、测试场景（`Audio Format`）等任意名称

---

## 运行方式

```bash
cd <project-dir>
python3 music_organizer.py              # 默认：强制覆盖
python3 music_organizer.py --no-force   # 增量：跳过大小相同的已有文件
```

**依赖：** Python 3.8+，ffmpeg（含 ffprobe）

---

## 脚本核心配置

### 1. ARTIST_GENRE（艺术家→流派映射）
```python
ARTIST_GENRE = {
    'adele':   'Pop',
    '王菲':    'Cantopop',
    'bach':    'Classical',
    'mozart':  'Classical',
    # key 必须小写，支持中英文
}
```

### 2. GENRE_MAP（genre tag 规范化）
```python
GENRE_MAP = {
    'vocal jazz': 'Jazz',
    'cantopop':   'Cantopop',
    'mandarin':   'Mandopop',
    # 将嵌入 tag 中的各种写法统一为标准流派名
}
```

### 3. ALBUM_META（专辑级覆盖，修正错误/缺失 tag）
```python
ALBUM_META = {
    '源文件夹名中的子串': {
        'album':        '正确专辑名',
        'album_artist': '正确艺术家',
        'artist':       '正确艺术家',
        'genre':        'Classical',
        'year':         '1999',
        'parse':        'bav',  # 可选：指定特殊文件名解析器
    },
}
```
`parse` 可选值：`bav`（Best Audiophile Voices）、`violin_wav`、`mozart_flac`、`levine_wav`

---

## 流派判断优先级（高→低）

1. `ALBUM_META` 中该专辑的 `genre` 覆盖
2. `ARTIST_GENRE`：artist 或 album 名包含 key
3. `GENRE_MAP`：对嵌入的 genre tag 规范化
4. `JAZZ_TITLES`：曲名匹配已知爵士标准曲
5. 含中文字符 → `Mandopop`（兜底）
6. `Various`（最终兜底）

---

## 支持格式

| 格式 | 类型 |
|------|------|
| FLAC / APE | 无损压缩 |
| MP3 | 有损压缩 |
| M4A / AAC | Apple 格式 |
| WAV / AIFF | 无损非压缩 |
| DSF / DFF | DSD（HAP-Z1ES 原生支持） |
| OGG / Opus / WMA | 其他格式 |

CUE+整轨（`.cue` + `.flac`/`.wav`）自动检测并用 ffmpeg 拆分。

---

## 常见问题诊断

### 文件没有出现在预期位置
1. 用 ffprobe 读取源文件 tag：
   ```bash
   ffprobe -v quiet -print_format json -show_format "文件路径" \
     | python3 -c "import sys,json; d=json.load(sys.stdin); \
       print(json.dumps(d['format'].get('tags',{}), ensure_ascii=False, indent=2))"
   ```
2. 检查 `album_artist` tag（决定艺术家文件夹名）
3. 检查 `genre` tag（缺失时走兜底逻辑）
4. 确认 `ARTIST_GENRE` / `ALBUM_META` 是否有匹配条目

### 常见症状对照
| 症状 | 原因 |
|------|------|
| 文件在 `Various Artists/` 下 | `album_artist` tag 为 "Various Artists"，需在 Picard 修正 |
| 文件在 `Mandopop/WAV/WAV/` 下 | 上次运行时 tag 缺失，脚本用文件夹名填充了 artist/album |
| 文件在 `Various/` 流派下 | 无 genre tag、artist 不在 ARTIST_GENRE、无中文字符 |
| 旧路径文件未删除 | 孤儿清理在下次运行时自动处理 |

---

## 修改脚本的常见任务

### 新增艺术家→流派映射
```python
# 在 ARTIST_GENRE 中添加，key 必须小写
'artist name': 'Genre',
```

### 新增专辑 metadata 覆盖
```python
# 在 ALBUM_META 中添加，key 为源文件夹名的唯一子串
'FolderSubstring': {
    'album': '专辑名',
    'album_artist': '艺术家',
    'genre': 'Jazz',
    'year': '2001',
},
```

### 新增自定义文件名解析器
在脚本中添加 `def parse_xxx(fp: Path) -> dict:` 函数，返回包含 `title`、`artist`、`track` 等键的字典，然后在 `ALBUM_META` 对应条目中指定 `'parse': 'xxx'`，并在 `main()` 的 `special_parse` 分支中添加 `elif special_parse == 'xxx': parsed = parse_xxx(fp)`。

---

## 孤儿清理机制

每次运行结束时，脚本：
1. 收集本次所有写入目标路径
2. 扫描 `out/MUSIC/` 下所有音频文件和 `folder.jpg`
3. 删除不在目标集合中的孤儿文件（含 `.DS_Store`）
4. 自底向上删除空目录

**实际效果：** 在 MusicBrainz Picard 修正 metadata 后重新运行脚本，旧路径文件会被自动清除。

---

## 播放列表规范

所有 `.m3u` 每次全量重建（先删除旧文件），**统一写到 SD 卡根（`out/`）单一位置** — 这是 Sony Walkman 与 Chord Poly 唯一都能识别的位置。

**路径语义**：`os.path.relpath(track, DEST)`——相对于 SD 卡根（不是播放列表自身、也不是绝对路径）。这是 Sony 与 Poly 的唯一交集格式。

```
#EXTM3U
#EXTENC:UTF-8

#EXTINF:243,Miles Davis - So What
MUSIC/Jazz/Miles Davis/(1959) Kind of Blue/01 - So What.flac
```

**文件格式**：
- 扩展名：`.m3u`（不用 `.m3u8`——Chord Poly GoFigure 对 `.m3u8` 不可靠）
- 编码：UTF-8 + BOM（老版 Chord Poly 需要 BOM 才能正确识别中文）
- 行尾：CRLF

**兼容性说明**：

| 设备 | 固件坑 | 脚本的处理 |
|------|--------|-----------|
| Sony WM1A / WM1ZM2 | 只索引 `/MUSIC/` 大写目录；标准 M3U 路径解析（相对播放列表自身） | 音乐目录用 `MUSIC/`；.m3u 写在 SD 根，路径 `MUSIC/...` 可正确解析 |
| Chord Poly (GoFigure / MPD) | `.m3u8` 不稳；MPD 按 `music_directory` 解析路径 | 扩展名 `.m3u`；路径用 `MUSIC/...`（无前导 `/`、无 `..`）；MPD 配置 `music_directory = /SD 根/` |
| FAT32 / exFAT | 半/全角冒号、单引号、感叹号等会让扫描器出错 | `sanitize()` 清理非法字符 |

**为什么不支持 Lotoo PAW Gold 2017**：Lotoo 扫描器不解析 `..`，要求绝对路径 `/MUSIC/...`，但绝对路径会让 Chord Poly MPD 失败。三家设备没有共通格式，本项目专门优化 Sony + Poly。
