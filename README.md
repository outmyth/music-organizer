# Music Organizer v2

> 🌐 **English** · [中文](README.zh.md)

Automatically scans local music files, reads metadata, organizes them into a clean folder structure, and generates M3U playlists tuned for audiophile DAPs.

**Compatible devices:** Sony HAP-Z1ES · Sony Walkman (NW-WM1Z / WM1A / NW-WM1ZM2) · Chord Mojo+Poly / Hugo · Lotoo PAW Gold 2017.

---

## Requirements

- Python 3.8+
- [ffmpeg](https://ffmpeg.org/) (includes `ffprobe`)

```bash
# macOS
brew install ffmpeg
```

---

## Directory layout

```
<project-dir>/
├── in/                        ← raw music files (input)
│   ├── Jazz/                  ← normal albums (any structure under genre/artist)
│   │   └── Miles Davis/
│   └── Test/                  ← reserved name: test/comparison subset (see below)
│       ├── Beyerdynamic T1/   ← category label (any name)
│       └── Audio Format/      ← category label (any name)
└── out/                       ← organized output (copy whole folder to SD-card root)
    ├── MUSIC/                 ← UPPERCASE — Sony WM1A only indexes /MUSIC/
    │   ├── Jazz/              ← normal files grouped by genre
    │   │   └── Miles Davis/
    │   │       └── (1959) Kind of Blue/
    │   ├── Classical/
    │   ├── Cantopop/
    │   ├── Mandopop/
    │   ├── Various/
    │   ├── Test/              ← Test files isolated here
    │   │   ├── Beyerdynamic T1/
    │   │   │   └── Jazz/Miles Davis/...
    │   │   └── Audio Format/
    │   │       └── Mandopop/陳慧嫻/...
    │   └── Playlists/         ← Sony WM1A exclusive playlist directory
    │       ├── All.m3u
    │       ├── Album_*.m3u
    │       └── ...
    └── playlists/             ← Lotoo PAW Gold 2017 / Chord Poly / generic
        ├── All.m3u                       ← all tracks (incl. Test)
        ├── Album_<Artist> - <Album>.m3u  ← one per album
        ├── Artist_<Artist>.m3u           ← one per artist
        ├── Format_<FMT>.m3u              ← grouped by format (FLAC/DSD/WAV/…)
        ├── Test_<Category>.m3u           ← one per Test category
        └── music_index.json              ← skipped with --no-json
```

> **Flat layout + `<Category>_<Name>` naming**: Lotoo PAW Gold 2017's playlist scanner does **not** recurse into subdirectories, so all playlists live directly under `playlists/`. The `Album_` / `Artist_` / `Format_` / `Test_` prefixes group related playlists together in the DAP UI. The extension is `.m3u` (not `.m3u8`) because Chord Poly's GoFigure app is unreliable with `.m3u8`.

### The `Test/` directory

`in/Test/` is a **reserved folder name** for isolating test or comparison tracks (e.g. headphone audition tracks).

**Naming rule:**
- The **first-level subdirectory** under `in/Test/` becomes the category label, e.g. `Beyerdynamic T1`, `Audio Format`
- Category names can be anything: headphone models, audition scenarios, format comparisons
- Inside a category, music can be organized however you like (normal files and CUE+image albums both supported)

**How Test files differ from normal files:**

| Aspect | Normal files | Test files |
|--------|--------------|-----------|
| Output path | `out/MUSIC/{Genre}/{Artist}/...` | `out/MUSIC/Test/{Category}/{Genre}/{Artist}/...` |
| `All.m3u` | included | **included** |
| `Album_*` / `Artist_*` / `Format_*` | included | **excluded** |
| Dedicated playlist | — | `playlists/Test_{Category}.m3u` |

> All files under the same `Test/{Category}/` are merged into one `Test_{Category}.m3u`. Filenames containing FAT32/exFAT-sensitive characters (`:`, `?`, `'`, etc.) are sanitized.

---

## Usage

```bash
cd <project-dir>

# Default: force-overwrite all files + generate music_index.json
python3 music_organizer.py

# Incremental: skip existing files with matching size
python3 music_organizer.py --no-force

# Skip JSON index generation
python3 music_organizer.py --no-json

# Incremental + no JSON
python3 music_organizer.py --no-force --no-json
```

### Flags

| Flag | Description |
|------|-------------|
| `--no-force` | Skip existing files with matching size (default: force overwrite) |
| `--no-json` | Don't generate `music_index.json` (default: generate it) |

---

## Supported formats

| Format | Type |
|--------|------|
| FLAC | Lossless compressed |
| MP3 | Lossy compressed |
| M4A / AAC | Apple format |
| WAV / AIFF | Lossless uncompressed |
| DSF / DFF | DSD (native on HAP-Z1ES) |
| OGG / Opus | Open formats |
| WMA / APE | Other formats |

CUE+image albums (`.cue` + `.flac` / `.wav`) are auto-detected and split into individual tracks via ffmpeg.

---

## Pipeline

```
in/ raw files
   ↓
① Scan all audio files & CUE+image albums
   ↓
② Split CUE albums (ffmpeg → temp staging dir)
   ↓
③ Read metadata (ffprobe)
     → Apply ALBUM_META album-level overrides
     → Apply ARTIST_GENRE / GENRE_MAP genre mapping
     → Fall back to filename / path inference for missing fields
   ↓
④ Copy to out/MUSIC/ in Genre/Artist/(Year) Album/ structure
     (UPPERCASE MUSIC/ — required by Sony WM1A)
     → Write corrected metadata tags via ffmpeg -metadata
     → Copy cover art → folder.jpg
   ↓
⑤ Orphan cleanup (remove stale files / empty dirs from previous runs)
   ↓
⑥ Generate M3U playlists (full rebuild, flat <Category>_<Name>.m3u naming)
     → All.m3u, Album_*, Artist_*, Format_*
     → Test_<Category>.m3u for each Test subset
     → Written to both playlists/ and MUSIC/Playlists/
     → UTF-8 + BOM + CRLF; paths relative to each playlist file's own directory
   ↓
⑦ Generate music_index.json (skipped with --no-json)
```

---

## Genre classification (priority order)

1. **`ALBUM_META` album-level override** (top of `music_organizer.py`)
2. **`ARTIST_GENRE` artist mapping** (e.g. `Bach → Classical`)
3. **`GENRE_MAP` tag normalization** (e.g. `vocal jazz → Jazz`)
4. **`JAZZ_TITLES` track-name keywords** (matches well-known jazz standards)
5. **Contains CJK characters** → `Mandopop` (fallback)
6. **`Various`** (final fallback)

---

## Special filename parsers

For albums with broken or missing metadata, set `parse` in the corresponding `ALBUM_META` entry to enable a custom parser:

| Parser | Use case | Filename pattern |
|--------|----------|------------------|
| `bav` | Best Audiophile Voices | `Artist_Title.flac` |
| `violin_wav` | Classical violin compilations | `NN.English Title  Chinese Title.wav` |
| `mozart_flac` | Mozart Piano Concertos #21/24 | `N.Title.flac` |
| `levine_wav` | Schubert / Levine WAV rips | `NN.Title.wav` |

---

## Handling missing tags

The script lists files with incomplete metadata at the end of every run. To fill them in, use:

- **[MusicBrainz Picard](https://picard.musicbrainz.org/)** — GUI tool, auto-identifies tracks and embeds standard tags + cover art
- **[beets](https://beets.io/)** — CLI tool, better for batch workflows

After fixing tags, re-run:

```bash
python3 music_organizer.py
```

Orphan cleanup will remove the old wrong-path copies automatically.

---

## Configuration

All configuration lives at the top of `music_organizer.py`:

| Variable | Description |
|----------|-------------|
| `SOURCE` | Source directory (`<project-dir>/in`) |
| `DEST` | Output directory (`<project-dir>/out`) |
| `ARTIST_GENRE` | Artist → genre mapping |
| `GENRE_MAP` | Genre tag string normalization |
| `ALBUM_META` | Album-level metadata overrides + parser selection |

---

## SD-card DAP compatibility notes

Copy the entire `out/` folder to your SD card root and the playlists work directly on the supported devices. The script handles each firmware's quirks during playlist generation:

| Device / firmware | Quirk handled | How the script addresses it |
|-------------------|---------------|----------------------------|
| **Sony WM1A / WM1ZM2** | Only indexes `/MUSIC/` (uppercase); only reads playlists in `MUSIC/Playlists/` | Music dir named `MUSIC/`; playlists dual-written to `MUSIC/Playlists/` |
| **Lotoo PAW Gold 2017** | Playlist scanner does **not** recurse into subdirectories; needs UTF-8 BOM for Chinese | Flat layout with `<Category>_<Name>.m3u` prefixes; files written with BOM |
| **Chord Poly (GoFigure)** | Unreliable with `.m3u8` extension; standard M3U path resolution (relative to playlist file) | Extension is `.m3u`; paths use `os.path.relpath(track, pl_file.parent)` |
| **FAT32 / exFAT filesystems** | Half-width colon, question mark, straight + curly apostrophes (`‘ ’`), exclamation will trip up scanners | `sanitize()` strips/replaces `: ： ' ‘ ’ ! * ? \| " < >` and other invalid chars |

**Playlist relative-path format (important):**

```
#EXTM3U
#EXTENC:UTF-8

#EXTINF:243,Miles Davis - So What
../MUSIC/Jazz/Miles Davis/(1959) Kind of Blue/01 - So What.flac
```

- Paths are relative to **the playlist file's own directory** (standard M3U / RFC 8216 semantics) — not relative to the SD-card root.
- File encoding: UTF-8 + BOM (`EF BB BF`), CRLF line endings.
- Extension: `.m3u` (not `.m3u8`).

**Chord Poly MPD-mode exception:** If you're using Poly's MPD server mode (rather than local SD-card playback), MPD resolves paths relative to its `music_directory` setting, not the playlist file's location. In that case, set `music_directory = /path/to/out/MUSIC/` in your MPD config — this is external configuration, not handled by the script.

---

## License

[MIT](LICENSE)
