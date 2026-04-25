# 示例目录

> 🌐 [English](README.md) · **中文**

这个目录展示脚本运行前后输入和输出的目录结构长什么样，方便你在 GitHub 上浏览仓库时直接看到布局，不用真的跑脚本。

**所有音频文件（`.flac`、`.dsf`、`folder.jpg`）都是 0 字节占位文件**——只为了展示目录树。`.m3u`、`.cue` 和 `.json` 文件包含真实可读的内容，演示脚本输出的精确格式。

> ⚠️ 仓库根目录下的 `in/` 和 `out/` 是给**你自己真实数据**用的（被 gitignore 忽略）。你在本地跑脚本时，把音乐放到 `in/`，脚本输出到 `out/`。当前的 `examples/` 目录纯粹是文档用途。

---

## `examples/in/` — 输入布局

```
examples/in/
├── Jazz/Miles Davis/Kind of Blue/                ← 普通专辑，3 首
│   ├── 01 - So What.flac
│   ├── 02 - Freddie Freeloader.flac
│   ├── 03 - Blue in Green.flac
│   └── folder.jpg
├── Classical/Beethoven/Symphony No. 5/           ← CUE+整轨专辑
│   ├── Symphony No. 5.cue                        (真实 CUE 内容)
│   ├── Symphony No. 5.flac                       (单个整轨文件)
│   └── folder.jpg
├── Cantopop/陳百強/一見鍾情/                      ← 中文标题专辑
│   ├── 01 - 一見鍾情.flac
│   ├── 02 - 偏偏喜歡你.flac
│   └── folder.jpg
└── Test/Beyerdynamic T1/                         ← 保留的 Test/ 分类
    ├── 01 - Time After Time.dsf
    └── 02 - Cheek to Cheek.dsf
```

**演示要点：**
- 普通专辑带封面图（`folder.jpg`）
- CUE+整轨专辑——脚本会用 ffmpeg 自动拆分成多首
- 中文标题专辑——脚本会自动归类（`陳百強` 匹配 `Cantopop` 规则；其他无规则的中文专辑自动归 `Mandopop`）
- `Test/{Category}/` 子目录用于耳机试音 / 格式对比

---

## `examples/out/` — 输出布局（脚本运行后）

```
examples/out/
├── MUSIC/                                      ← 大写，给 Sony WM1A 用
│   ├── Jazz/Miles Davis/(1959) Kind of Blue/    ← 年份前缀来自 metadata
│   │   ├── 01 - So What.flac
│   │   ├── 02 - Freddie Freeloader.flac
│   │   ├── 03 - Blue in Green.flac
│   │   └── folder.jpg
│   ├── Classical/Beethoven/(1808) Symphony No. 5/  ← CUE 拆分后的 4 个乐章
│   │   ├── 01 - I. Allegro con brio.flac
│   │   ├── 02 - II. Andante con moto.flac
│   │   ├── 03 - III. Scherzo. Allegro.flac
│   │   ├── 04 - IV. Allegro.flac
│   │   └── folder.jpg
│   ├── Cantopop/陳百強/(1985) 一見鍾情/
│   │   ├── 01 - 一見鍾情.flac
│   │   ├── 02 - 偏偏喜歡你.flac
│   │   └── folder.jpg
│   ├── Test/Beyerdynamic T1/Jazz/Various/      ← Test 按分类隔离，再按流派/艺术家
│   │   ├── 01 - Time After Time.dsf
│   │   └── 02 - Cheek to Cheek.dsf
│   └── Playlists/                              ← Sony WM1A 扫描路径（路径前缀 ../）
│       ├── All.m3u
│       ├── Album_Beethoven - Symphony No. 5.m3u
│       ├── Album_Miles Davis - Kind of Blue.m3u
│       ├── Album_陳百強 - 一見鍾情.m3u
│       ├── Artist_Beethoven.m3u
│       ├── Artist_Miles Davis.m3u
│       ├── Artist_陳百強.m3u
│       ├── Format_DSD.m3u
│       ├── Format_FLAC.m3u
│       └── Test_Beyerdynamic T1.m3u
└── playlists/                                  ← Lotoo / Chord Poly / 通用（路径前缀 ../MUSIC/）
    ├── All.m3u
    ├── Album_*.m3u
    ├── Artist_*.m3u
    ├── Format_*.m3u
    ├── Test_Beyerdynamic T1.m3u
    └── music_index.json                        ← 完整 metadata 目录
```

---

## 对比两套播放列表的相对路径

同一张播放列表写到两处，路径前缀不同——因为相对的是各自所在目录：

**`playlists/All.m3u`**（从仓库根算起，音乐在上一级再进 `MUSIC/`）：
```
#EXTINF:545,Miles Davis - So What
../MUSIC/Jazz/Miles Davis/(1959) Kind of Blue/01 - So What.flac
```

**`MUSIC/Playlists/All.m3u`**（已经在 `MUSIC/` 内部，只需往上一级）：
```
#EXTINF:545,Miles Davis - So What
../Jazz/Miles Davis/(1959) Kind of Blue/01 - So What.flac
```

这是**标准 M3U / RFC 8216 路径解析**——每个播放列表都自包含、相对自身位置。

---

## 这些 demo 文件怎么来的

这些文件是手工构造的，**不是**脚本实际跑出来的（音频文件是 0 字节，`ffprobe` 没法处理）。它们的内容严格遵循 `music_organizer.py` 的输出规范：

- **`in/` 目录树**镜像脚本期望的输入形态
- **`out/MUSIC/`** 结构遵循 `{Genre}/{Artist}/({Year}) {Album}/` 公式
- **`.m3u` 文件**使用 `music_organizer.py` 第 896-906 行的精确格式（header + EXTINF + 相对路径）
- **`music_index.json`** 匹配 Step 7 生成的 schema

要在自己机器上从真实输入跑出真实输出，参考 [主 README](../README.md)。
