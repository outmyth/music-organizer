# Music Organizer — Claude Code Skill

## Trigger
Use this skill when the user asks about music organization, the music_organizer.py script, or any task related to:
- Running / debugging the organizer
- Adding new artists, genres, or album overrides
- Diagnosing why a file ended up in the wrong place
- Extending the script with new features

## Project Context

**Location:** `<project-dir>/`  
**Script:** `music_organizer.py`  
**Input:** `in/` (source music files, including `in/Test/` for test subsets)  
**Output:** `out/` (organized output)

### Output structure
```
out/                                           ← copy whole folder to SD-card root
├── MUSIC/                                     ← CAPITAL — Sony WM1A only indexes /MUSIC/
│   ├── {Genre}/{Artist}/({Year}) {Album}/    ← normal files
│   │   ├── {NN} - {Title}.{ext}
│   │   └── folder.jpg
│   ├── Test/{Category}/{Genre}/{Artist}/     ← Test files (isolated)
│   └── Playlists/                            ← Sony WM1A exclusive playlist dir
│       └── (same flat .m3u files as below)
└── playlists/                                 ← Lotoo / Chord Poly / generic
    ├── All.m3u                                ← includes ALL tracks (incl. Test)
    ├── Album_{Artist} - {Album}.m3u           ← per album
    ├── Artist_{Artist}.m3u                    ← per artist
    ├── Format_{FORMAT}.m3u                    ← per format
    ├── Test_{Category}.m3u                    ← one per test category
    └── music_index.json
```

**Naming convention**: `<Category>_<Name>.m3u` — underscore separates category from name (two-level grouping signal visible in DAP UI); hyphen `" - "` separates fields within the name (e.g. `Album_Miles Davis - Kind of Blue.m3u`). All ASCII, unambiguous, DAP-friendly.

**Why flat + dual-write**: Lotoo PAW Gold 2017's playlist scanner does NOT recurse into subdirectories; Sony WM1A only indexes `MUSIC/Playlists/`. One flat directory + writing to both locations covers Lotoo, Chord Poly, Sony, and generic MPD players.

### Test/ — reserved directory name

`in/Test/` is a **reserved folder name** handled specially by the script.

**Rule:** the **first-level subdirectory** under `in/Test/` becomes the *category label*.

```
in/Test/
├── Beyerdynamic T1/   ← category = "Beyerdynamic T1"
│   └── (any music)
└── Audio Format/      ← category = "Audio Format"
    └── (any music)
```

**Behaviour vs normal files:**

| | Normal files | Test files |
|---|---|---|
| Output path | `out/MUSIC/{Genre}/...` | `out/MUSIC/Test/{Category}/{Genre}/...` |
| All.m3u | included | **included** |
| Album_* / Artist_* / Format_* | included | **excluded** |
| Dedicated playlist | — | `Test_{Category}.m3u` |

All files under the same `Test/{Category}/` merge into one playlist regardless of subfolder depth. CUE+image albums inside Test/ are also supported.

---

## Organization Workflow

Every run executes the following steps in order:

### Step 1 — Discovery（扫描 `in/`）

`os.walk(SOURCE)` recursively scans all files.

- **CUE+image detection**: any folder containing a `.cue` file with a referenced `.flac`/`.wav` is flagged as a CUE album. The CUE file is decoded with multiple encodings tried in order: UTF-8 → GB18030 → GBK → Big5 → latin-1.
- **Individual files**: all remaining audio files (`AUDIO_EXT`) that are NOT the image source of a CUE album.
- The two lists are kept separate for different processing paths.

---

### Step 2 — CUE+image splitting（整轨拆分）

For each CUE album:

1. Disc number detected from CUE filename (`CD1`, `CD2`, `Disc1` …).
2. Lookup `ALBUM_META` by source folder name substring → apply metadata override.
3. Hardcoded album-specific overrides applied (e.g. Beethoven/Giulini, 黄教堂).
4. `split_cue_album()` calls ffmpeg to extract each track into a temp staging directory (`/tmp/music_organizer_staging/`), writing correct metadata tags (`-metadata`) during the split.
5. `get_test_category()` tags each track with its Test category (if under `in/Test/`).

---

### Step 3 — Individual file processing（单曲文件处理）

For each audio file, metadata is resolved through a layered pipeline:

```
① ffprobe reads embedded tags
        ↓
② ALBUM_META substring match on folder name
   → special filename parser if 'parse' key set
     (bav / violin_wav / mozart_flac / levine_wav)
        ↓
③ infer_from_path() — fallback from filename & parent folder name
        ↓
④ Merge: parsed > inferred (fills missing fields only)
        ↓
⑤ ALBUM_META override applied (highest priority for album/artist/genre/year)
   parsed track/title overrides album-level override for those fields
        ↓
⑥ classify_genre() → final genre string
   priority: ALBUM_META → ARTIST_GENRE → GENRE_MAP → JAZZ_TITLES → Chinese chars → 'Various'
```

**Destination path formula:**
```
Normal:  out/MUSIC/{Genre}/{Artist}/({Year}) {Album}/[CD{N}/]{NN} - {Title}.{ext}
Test:    out/MUSIC/Test/{Category}/{Genre}/{Artist}/({Year}) {Album}/[CD{N}/]{NN} - {Title}.{ext}
```

- `{NN}` = zero-padded track number; omitted if no track tag.
- `CD{N}` subfolder added only when disc number > 1.
- If `ALBUM_META` or special parser was used → `copy_with_meta()` rewrites tags via ffmpeg during copy. Otherwise → plain `shutil.copy2()`.

---

### Step 4 — CUE tracks → finalize（CUE 轨道归档）

Staged CUE split files (from temp dir) are copied to the same dest path formula as Step 3 using `shutil.copy2()`.

---

### Step 5 — Cover art（封面图复制）

For each unique destination album folder:

1. Search source folder for cover: `folder.jpg`, `cover.jpg`, `front.jpg`, `.JPG` variants, then `Artwork/` subdir, then any `.jpg`/`.png` in folder.
2. For CUE-staged files: also searches the original source album folder by folder name key.
3. Copies first match to `dest_dir/folder.jpg` (skips if already exists).

---

### Step 6 — Playlist generation（播放列表生成）

All existing `.m3u` / `.m3u8` files (plus legacy `by_*/` subdirs) deleted first — full rebuild every run.

Tracks sorted by: `artist → album → disc → track → title`.

Every playlist is written **twice** — once to `out/playlists/` (Lotoo / Chord Poly / generic) and once to `out/MUSIC/Playlists/` (Sony WM1A only indexes this path). Each copy computes paths relative to its own location.

| Playlist | Contents | Naming |
|---|---|---|
| All | All tracks including Test | `All.m3u` |
| Per album | Normal only | `Album_{Artist} - {Album}.m3u` |
| Per artist | Normal only | `Artist_{Artist}.m3u` |
| Per format | Normal only | `Format_{FORMAT}.m3u` |
| Per test category | Test only | `Test_{Category}.m3u` |

**Path format**: `os.path.relpath(track.dest, pl_file.parent)` — relative to the **playlist file's own directory** (standard M3U semantics, required by Chord Poly / Lotoo / Sony in SD-card mode). NOT relative to a library root.

**File format**:
- Extension: `.m3u` (not `.m3u8` — Chord Poly GoFigure is unreliable with `.m3u8`)
- Encoding: **UTF-8 + BOM** (`encoding='utf-8-sig'`) — required by Lotoo and older Chord Poly firmware for Chinese characters
- Line terminator: **CRLF** (`newline='\r\n'`) — Sony / Lotoo firmware preference
- Header: `#EXTM3U\n#EXTENC:UTF-8\n\n`
- Entry: `#EXTINF:{sec},{Artist} - {Title}\n{relpath}\n`

**Filesystem-safe naming (`sanitize()`)**: strips characters that trip up FAT32/exFAT scanners on Sony WM1A / Lotoo / Chord Poly — half + full-width colon (`:`, `：`), straight + curly apostrophes (`'`, `‘`, `’`), exclamation (`!`), plus the reserved invalid path chars (`* ? | " < >`). Colons replaced with ` - ` (space-hyphen-space).

---

### Step 7 — JSON index（索引生成，可选）

Generates `playlists/music_index.json` with full metadata for every track. Skipped with `--no-json`.

---

### Step 8 — Orphan cleanup（孤儿文件清理）

1. Collect `expected_files` = all `dest` paths written this run + `dest_dir/folder.jpg` for every album.
2. Scan `out/MUSIC/` for all audio files, `folder.jpg`, and `.DS_Store` — **skipping `MUSIC/Playlists/`** (its `.m3u` files are written by Step 6 and must not be cleaned up here).
3. Delete any file not in `expected_files` (`.DS_Store` always deleted).
4. Remove empty directories bottom-up (a directory is "empty" if it contains only `.DS_Store`).

---

### Step 9 — Summary report

Prints track counts by genre and format, total duration, and lists up to 10 files with missing `title`/`artist`/`album` tags.

---

## Running the script

```bash
cd <project-dir>
python3 music_organizer.py            # default: force overwrite + generate JSON
python3 music_organizer.py --no-force # skip same-size existing files (incremental)
python3 music_organizer.py --no-json  # skip music_index.json generation
```

---

## Key configuration (top of script)

### ARTIST_GENRE
Maps artist name substrings (lowercase) → canonical genre string.
```python
ARTIST_GENRE = {
    'adele': 'Pop',
    '王菲':  'Cantopop',
    'bach':  'Classical',
    ...
}
```

### GENRE_MAP
Normalizes embedded genre tags to canonical names.
```python
GENRE_MAP = {
    'vocal jazz': 'Jazz',
    'cantopop':   'Cantopop',
    ...
}
```

### ALBUM_META
Per-album overrides for broken/missing tags. Key = substring of source folder name.
```python
ALBUM_META = {
    'FolderNameSubstring': {
        'album':        'Correct Album Title',
        'album_artist': 'Correct Artist',
        'artist':       'Correct Artist',
        'genre':        'Jazz',
        'year':         '1999',
        'parse':        'bav',   # optional: special filename parser
    },
}
```
Available `parse` values: `bav`, `violin_wav`, `mozart_flac`, `levine_wav`.

---

## Genre classification priority (highest → lowest)

1. `ALBUM_META` override for the album's source folder
2. `ARTIST_GENRE` — artist or album name contains the key
3. `GENRE_MAP` — embedded genre tag normalization
4. `JAZZ_TITLES` — title matches known jazz standards
5. Chinese characters detected → `Mandopop` (fallback)
6. `Various` (catch-all)

---

## Diagnosing a misplaced file

When a file ends up in the wrong folder, check in this order:

1. **Read embedded tags:**
   ```bash
   ffprobe -v quiet -print_format json -show_format "path/to/file.ext" \
     | python3 -c "import sys,json; d=json.load(sys.stdin); print(json.dumps(d['format'].get('tags',{}), ensure_ascii=False, indent=2))"
   ```
2. **Check `album_artist` tag** — this drives the artist folder name.
3. **Check `genre` tag** — fed into `GENRE_MAP`; missing genre triggers fallback rules.
4. **Check `ARTIST_GENRE`** — does the artist name match any key?
5. **Check `ALBUM_META`** — does the source folder name contain any key?

Common causes:
| Symptom | Likely cause |
|---------|-------------|
| File under `Various Artists/` | `album_artist` tag is "Various Artists" — fix in Picard |
| File under `Mandopop/WAV/WAV/` | Tags were missing; script used folder name as artist/album |
| File under `Various/` genre | No genre tag, artist not in `ARTIST_GENRE`, no Chinese chars |
| Old copy not deleted | Script ran before metadata fix; re-run will trigger orphan cleanup |

---

## Adding a new artist → genre mapping

Edit `ARTIST_GENRE` in the script:
```python
'new artist name': 'Genre',   # key must be lowercase
```

## Adding an album override

Edit `ALBUM_META`:
```python
'UniquePartOfFolderName': {
    'album':        'Correct Title',
    'album_artist': 'Artist Name',
    'genre':        'Jazz',
    'year':         '2001',
},
```

## CUE+image albums

Automatically detected: any folder containing a `.cue` file alongside a single large `.flac` or `.wav`. The script splits tracks via ffmpeg into a temp staging directory, then organizes them normally. Multi-disc albums (CD1.cue + CD2.cue) produce `CD1/` and `CD2/` subfolders.

---

## Orphan cleanup

After every run, the script:
1. Collects all destination paths written this run.
2. Scans `out/MUSIC/` for audio files + `folder.jpg` not in that set (skipping `MUSIC/Playlists/`).
3. Deletes orphans (including `.DS_Store`).
4. Removes empty directories bottom-up.

This means: fix metadata in Picard → re-run script → old wrong-path copies auto-deleted.

---

## Playlist generation

All `.m3u` / `.m3u8` files (plus any legacy `by_*/` subdirectories) are deleted and fully regenerated each run.

**Path semantics**: relative to each playlist file's own directory (standard M3U, per RFC 8216). The same playlist written to `playlists/` and `MUSIC/Playlists/` gets different `../` prefixes so both resolve correctly.

**DAP compatibility matrix** (all handled by Step 6):

| Device / firmware | Quirk | How the script handles it |
|---|---|---|
| Sony WM1A / WM1ZM2 | Only indexes `/MUSIC/`; only reads playlists in `MUSIC/Playlists/` | Capital `MUSIC/` folder; dual-write to `MUSIC/Playlists/` |
| Lotoo PAW Gold 2017 | Playlist scanner does not recurse into subdirectories; needs UTF-8 BOM for Chinese | Flat directory with `<Category>_<Name>.m3u` prefixes; BOM-prefixed files |
| Chord Poly (GoFigure) | `.m3u8` unreliable; follows standard M3U path resolution | `.m3u` extension; paths relative to playlist file's own dir |
| Chord Poly (MPD mode) | Resolves paths relative to `music_directory` setting | Set `music_directory = /path/to/out/MUSIC/` (external MPD config, not script) |
| FAT32 / exFAT | Breaks on `:`, `：`, `'`, `‘`, `’`, `!`, `*`, `?`, `|`, etc. | `sanitize()` strips or replaces all of these |

**Why not relative to SD-card root?** An earlier version wrote paths as `Music/Jazz/...` assuming a library root. But a playlist at `playlists/by_album/Artist/X.m3u8` looking for `Music/Jazz/...` makes DAPs search `playlists/by_album/Artist/Music/Jazz/...` — which doesn't exist → empty playlist. Only Chord Poly in MPD mode uses library-root semantics, and that's an external configuration concern, not a playlist-file concern.
