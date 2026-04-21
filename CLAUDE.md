扫描本地音乐文件夹 （～/data/Music/Source/）的音乐文件，读取 具体文件的metadata，自动整理这些文件和生成 M3U 播放列表用于以下音乐播放器，并且存储到目标目录（～/data/Music/Organized/）。

**兼容设备：**
- Sony HAP-Z1ES 
- Sony Walkman 金砖（NW-WM1Z / WM1A / NW-WM1ZM2）
- Chord Mojo + Poly/ Hugo（通过手机 USB DAC app）

整体流程图（推荐）
本地文件夹原始文件
   ↓
【AI 预清洗 & 去重】
   ↓
【MusicBrainz Picard 自动识别】
   ↓
【人工校正关键字段】
   ↓
【统一文件结构（Sony 友好）】
   ↓
【生成播放列表（Poly & Sony 各一套）】

## 🎵 支持格式

| 格式 | 说明 |
|------|------|
| FLAC | 无损压缩，最常用 |
| MP3  | 有损压缩 |
| M4A / AAC | Apple 格式 |
| WAV / AIFF | 无损非压缩 |
| DSF / DFF | DSD 格式（适合 HAP-Z1ES） |
| OGG / Opus | 开源格式 |

## 📁 输出结构

输出目录 `out/` 整盘拷贝到 SD 卡根目录即可直接使用。

```
out/
├── MUSIC/                  ← 大写！Sony WM1A 只扫描 /MUSIC/
│   ├── Jazz/Miles Davis/(1959) Kind of Blue/
│   ├── Classical/Bach/(1982) Goldberg Variations - Gould/
│   ├── Cantopop/陈百强/
│   ├── Mandopop/王菲/
│   ├── Various/
│   ├── Test/{Category}/...   ← Test 曲目隔离
│   └── Playlists/           ← Sony WM1A 专用播放列表（与下方 playlists/ 内容相同）
│       ├── All.m3u
│       ├── Album_*.m3u
│       └── ...
└── playlists/              ← Lotoo / Chord Poly / 通用
    ├── All.m3u                          ← 含所有曲目（含 Test）
    ├── Album_<Artist> - <Album>.m3u     ← 每张专辑
    ├── Artist_<Artist>.m3u              ← 每位艺术家
    ├── Format_<FMT>.m3u                 ← 每种格式（FLAC / DSD / WAV / …）
    ├── Test_<Category>.m3u              ← Test 每个分类一个
    └── music_index.json                 ← 加 --json 才生成
```

**播放列表设计要点**：
- 扁平目录：Lotoo PAW Gold 2017 的扫描器不递归子目录
- `<Category>_<Name>.m3u` 统一命名：同类播放列表在 DAP 界面自动聚拢
- 扩展名 `.m3u`（不用 `.m3u8`）：Chord Poly GoFigure 对 `.m3u8` 不可靠
- 编码 UTF-8 + BOM + CRLF：Lotoo / 老版 Poly 需要 BOM 识别中文
- 路径相对播放列表文件自身所在目录（标准 M3U，不是"相对 SD 卡根"）
- 同时写到 `playlists/` 和 `MUSIC/Playlists/` 两处，覆盖所有目标设备

## 🔧 tag 缺失怎么办？

程序会在最后报告缺失 tag 的文件数。推荐用以下工具补全：

- **[MusicBrainz Picard](https://picard.musicbrainz.org/)** — 免费，自动识别并补全 tag（macOS 可直接下载）
- **[beets](https://beets.io/)** — 命令行工具，功能强大
  ```bash
  pip3 install beets
  beet import ~/Music
Cover Art（Poly 最大隐形杀手）
🔧 Options → Cover Art

✔️ Download cover art
✔️ Use Cover Art Archive
✔️ Embed cover images in tags

，
```