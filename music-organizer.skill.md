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
│   └── Test/{Category}/{Genre}/{Artist}/     ← Test files (isolated)
├── All.m3u                                    ← includes ALL tracks (incl. Test)
├── Album_{Artist} - {Album}.m3u               ← per album
├── Artist_{Artist}.m3u                        ← per artist
├── Format_{FORMAT}.m3u                        ← per format
└── Test_{Category}.m3u                        ← one per test category
```

**Naming convention**: `<Category>_<Name>.m3u` — underscore separates category from name (two-level grouping signal visible in DAP UI); hyphen `" - "` separates fields within the name (e.g. `Album_Miles Davis - Kind of Blue.m3u`). All ASCII, unambiguous, DAP-friendly.

**Why a single SD-root location**: Sony Walkman (standard M3U, paths relative to .m3u file) and Chord Poly MPD (paths relative to `music_directory` = SD root) both correctly resolve paths of the form `MUSIC/<genre>/...` only when the .m3u sits at the SD-card root. **Lotoo PAW Gold 2017 is not supported** — it requires absolute `/MUSIC/...` paths that conflict with Poly's MPD resolution.

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

All existing `.m3u` / `.m3u8` files (plus legacy `playlists/`, `MUSIC/Playlists/`, and `by_*/` subdirs from prior runs) deleted first — full rebuild every run.

Tracks sorted by: `artist → album → disc → track → title`.

Every playlist is written to **a single location: `out/` (the SD-card root)**. This is the only spot where one path format works for both Sony Walkman and Chord Poly.

| Playlist | Contents | Naming |
|---|---|---|
| All | All tracks including Test | `All.m3u` |
| Per album | Normal only | `Album_{Artist} - {Album}.m3u` |
| Per artist | Normal only | `Artist_{Artist}.m3u` |
| Per format | Normal only | `Format_{FORMAT}.m3u` |
| Per test category | Test only | `Test_{Category}.m3u` |

**Path format**: `os.path.relpath(track.dest, DEST)` — relative to the SD-card root, e.g. `MUSIC/Jazz/Miles Davis/(1959) Kind of Blue/01 - So What.flac`. **No leading `/`, no `..`** — this is the only format that resolves correctly on both Sony Walkman (standard M3U, paths relative to .m3u location at SD root) and Chord Poly MPD (paths relative to `music_directory` = SD root).

**File format**:
- Extension: `.m3u` (not `.m3u8` — Chord Poly GoFigure is unreliable with `.m3u8`)
- Encoding: **UTF-8 + BOM** (`encoding='utf-8-sig'`) — required by older Chord Poly firmware for Chinese characters
- Line terminator: **CRLF** (`newline='\r\n'`)
- Header: `#EXTM3U\n#EXTENC:UTF-8\n\n`
- Entry: `#EXTINF:{sec},{Artist} - {Title}\n{relpath}\n`

**Filesystem-safe naming (`sanitize()`)**: strips characters that trip up FAT32/exFAT scanners on Sony WM1A / Chord Poly — half + full-width colon (`:`, `：`), straight + curly apostrophes (`'`, `‘`, `’`), exclamation (`!`), plus the reserved invalid path chars (`* ? | " < >`). Colons replaced with ` - ` (space-hyphen-space).

---

### Step 7 — Orphan cleanup（孤儿文件清理）

1. Collect `expected_files` = all `dest` paths written this run + `dest_dir/folder.jpg` for every album.
2. Scan `out/MUSIC/` for all audio files, `folder.jpg`, and `.DS_Store`.
3. Delete any file not in `expected_files` (`.DS_Store` always deleted).
4. Remove empty directories bottom-up (a directory is "empty" if it contains only `.DS_Store`).

---

### Step 8 — Summary report

Prints track counts by genre and format, total duration, and lists up to 10 files with missing `title`/`artist`/`album` tags.

---

## Running the script

```bash
cd <project-dir>
python3 music_organizer.py            # default: force overwrite
python3 music_organizer.py --no-force # skip same-size existing files (incremental)
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
2. Scans `out/MUSIC/` for audio files + `folder.jpg` not in that set.
3. Deletes orphans (including `.DS_Store`).
4. Removes empty directories bottom-up.

This means: fix metadata in Picard → re-run script → old wrong-path copies auto-deleted.

---

## Playlist generation

All `.m3u` / `.m3u8` files (plus any legacy `playlists/`, `MUSIC/Playlists/`, `by_*/` subdirectories from prior runs) are deleted and fully regenerated each run.

**Path semantics**: relative to the SD-card root (`DEST`), no leading `/`, no `..`. Form: `MUSIC/<genre>/<artist>/.../<file>.{ext}`. Sony Walkman resolves this correctly because the .m3u sits at the SD root and Sony uses standard relative-to-playlist resolution. Chord Poly MPD resolves it correctly because MPD uses paths relative to `music_directory` (= SD root).

**DAP compatibility matrix** (all handled by Step 6):

| Device / firmware | Quirk | How the script handles it |
|---|---|---|
| Sony WM1A / WM1ZM2 | Only indexes `/MUSIC/` (uppercase); standard M3U path resolution (relative to playlist file) | Capital `MUSIC/` folder; .m3u at SD root, paths `MUSIC/...` resolve to `/MUSIC/...` |
| Chord Poly (GoFigure / MPD) | `.m3u8` unreliable; MPD paths relative to `music_directory`, not playlist file | `.m3u` extension; paths use `MUSIC/...` (no `/`, no `..`); set `music_directory = /SD root/` |
| FAT32 / exFAT | Breaks on `:`, `：`, `'`, `‘`, `’`, `!`, `*`, `?`, `|`, etc. | `sanitize()` strips or replaces all of these |

**Why Lotoo PAW Gold 2017 is not supported**: Lotoo's scanner does not parse `..` and requires absolute `/MUSIC/...` paths, but absolute paths break Chord Poly's MPD (which interprets `/` as filesystem root). There is no .m3u path format that satisfies both Lotoo and Poly — the project optimizes for Sony + Poly.
