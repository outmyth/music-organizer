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
   - Skips generic parents (DISC N, CD N) → uses grandparent for artist
   - For "{track}. {X} - {Y}" filenames, checks ancestors / ARTIST_GENRE /
     MB cache to determine which token is artist vs title
        ↓
④ Merge: parsed > inferred (fills missing fields only).
   Track which fields came from inference (`inferred_only` set) — needed
   so AcoustID can later replace path-inferred placeholders.
        ↓
④.5 acoustid_lookup(fp) — fingerprint via fpcalc + AcoustID API
     Conservative override policy:
       • title / artist : only fills if MISSING (never overwrites
         filename-parsed text — avoids 红日 → 紅日 simp↔trad churn).
       • album          : fills if missing OR if value was path-inferred
         (e.g. '李克勤' as the album for files inside '李克勤/DISC 4/').
       • date           : fills if missing.
     Skipped entirely when ALBUM_META override applies, when folder
     was flagged as a compilation (see Step 2.5), or when API key not set.
        ↓
⑤ ALBUM_META override applied (highest priority for album/artist/genre/year)
   parsed track/title overrides album-level override for those fields
        ↓
⑤.5 normalize_multi_artist(canonicalize(meta['artist'])) — and same for album_artist
     • canonicalize: trad → simp Chinese (陳慧嫻 → 陈慧娴) via OpenCC
     • normalize_multi_artist: '/', '&', ',', 'feat.' → ', ' so '卢冠廷 / 莫文蔚'
       and '卢冠廷&莫文蔚' both become '卢冠廷, 莫文蔚'
     Title/album NOT touched — authored form preserved.
        ↓
⑥ classify_genre() → final genre string
   priority: ALBUM_META → ARTIST_GENRE (canonicalized keys) → GENRE_MAP →
             JAZZ_TITLES → Chinese chars → MusicBrainz API → 'Various'
```

**Compilation guard (Step 2.5)** — runs once before Step 3, only if AcoustID
API key is set. Groups `audio_files` by source folder, then for each folder
with ≥2 files lacking embedded album tags (and not covered by `ALBUM_META`):
looks up AcoustID for every file. If results disagree (≥2 distinct albums),
the folder is flagged as a *compilation* — Step ④.5 will skip the album +
date overrides for those files, keeping the path-derived placeholder so the
songs stay grouped on disk. Without this guard, a 9-song "Best of 唐朝乐队"
folder gets scattered to 4 different MB releases.

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

## External tools and libraries

The script uses the following dependencies. `_ensure_deps()` auto-installs each
on first run via `pip` (Python packages) or `brew` / `apt` (system tools).

### System binaries

| Tool | Used for | Required? | Auto-install |
|------|---------|-----------|---------------|
| `ffmpeg` | Re-encode + write metadata when `ALBUM_META` / parsers fix tags during copy; CUE-image splitting | **Yes** — script exits if missing | `brew install ffmpeg` / `apt install ffmpeg` |
| `ffprobe` (ships with ffmpeg) | Read embedded tags from every audio file (Step ① in pipeline) | **Yes** | bundled with ffmpeg |
| `fpcalc` (chromaprint) | Generate Chromaprint acoustic fingerprint for AcoustID lookup | Optional — AcoustID step skipped if missing | `brew install chromaprint` / `apt install libchromaprint-tools` |

### Python packages

| Package | Used for | Required? | Install |
|---------|---------|-----------|---------|
| `mutagen` | Fallback to read ID3 chunk in WAV files when `ffprobe` returns garbled `?` (INFO chunk encoding mismatch) | Yes | `pip install mutagen` |
| `opencc-python-reimplemented` | Traditional → Simplified Chinese for artist name canonicalization (so 陳慧嫻 and 陈慧娴 share one folder) | Yes | `pip install opencc-python-reimplemented` |

Standard library only: `os`, `json`, `shutil`, `re`, `subprocess`, `sys`,
`tempfile`, `time`, `urllib.request`, `urllib.parse`, `pathlib`, `collections`.
No third-party HTTP / JSON / web-scraping libraries.

### External web APIs

| API | Endpoint | Used for | Auth |
|-----|----------|---------|------|
| MusicBrainz | `musicbrainz.org/ws/2/artist` | Look up artist genre tags as last-resort genre fallback | None — public, rate-limited to 1 req/sec via User-Agent header |
| AcoustID | `api.acoustid.org/v2/lookup` | Identify track by Chromaprint fingerprint, return MusicBrainz recording IDs + release info | API key required; read from `ACOUSTID_API_KEY` env var or `.acoustid_key` file in project root (gitignored) |

### Local cache files

| File | Holds | Lifecycle |
|------|------|-----------|
| `.mb_cache.json` | Artist → genre, persisted after each MusicBrainz lookup | Committed to git so cache survives across machines |
| `.acoustid_cache.json` | `path::size` → AcoustID match dict, prevents repeat fingerprint lookups | Committed to git |
| `.acoustid_key` | AcoustID API key | **Gitignored** — never committed |

---

## Running the script

```bash
cd <project-dir>
python3 music_organizer.py               # default: force overwrite
python3 music_organizer.py --no-force    # skip same-size existing files (incremental)
```

Audit (which `ARTIST_GENRE` entries are now redundant) is automatic — printed
in the summary report at the end of every run.

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
6. **MusicBrainz API lookup** — queries `musicbrainz.org/ws/2/artist`, results cached in `.mb_cache.json`
7. `Various` (catch-all)

### ARTIST_GENRE maintenance — when to add a local override

Run `python3 music_organizer.py --audit-genres` to compare every entry against MusicBrainz and get three groups:

| Group | Action |
|---|---|
| ✅ MB agrees | Safe to delete — MB will cover it automatically |
| ⚠️ MB disagrees | Keep — local override is intentionally different |
| ❓ MB no result | Keep — MB can't find this artist |

**Current overrides that must stay** (as of 2025-05-04 audit):
- `alison krauss`, `eva cassidy` — MB says Folk, we classify as Jazz
- `bach`, `brahms`, `schubert`, `dvorák`, `bach`, `carlo maria giulini`, `wiener philharmoniker`, `james levine` — MB returned no result
- `mari nakamoto`, `唐朝`, `adele`, `junkie xl`, `群星` — MB returned no result
- `陈慧娴` / `陳慧嫻` — MB no result (keep until coverage improves)

---

## Known issues fixed (2025-05-04)

### 1. WAV files with ID3-only tags read as garbled `????`

**Root cause:** `probe()` uses `ffprobe`, which reads WAV metadata from the INFO chunk (Latin-1). Files whose tags were written only to the ID3 chunk (e.g. by MusicBrainz Picard or mutagen) come back as `????` garbage.

**Fix:** `probe()` now detects all-`?` values and falls back to `mutagen.wave.WAVE` (which reads the ID3 chunk natively). The fallback only fires for `.wav` files.

**Symptom:** File appears as `????///26 - .wav` in organizer output.

**Debug:**
```bash
ffprobe -v quiet -print_format json -show_format "file.wav" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['format'].get('tags',{}))"
# If all values are '????', tags are in ID3 chunk only
python3 -c "from mutagen.wave import WAVE; f=WAVE('file.wav'); print(f.tags.keys())"
```

**Permanent fix for the source file** (makes ffprobe readable without mutagen):
```bash
ffmpeg -i input.wav -metadata title="Title" -metadata artist="Artist" \
  -metadata genre="Cantopop" -c:a copy output.wav
```

---

### 2. CUE+WAV albums defaulted to Classical genre

**Root cause:** `split_cue_album()` had `album_meta_override.get('genre', 'Classical')` — any CUE album not in `ALBUM_META` silently became Classical.

**Fix:** Default changed to `''`; an empty genre then falls through to `classify_genre()` so Chinese-artist names resolve correctly to Mandopop/Cantopop.

**Symptom:** `陈慧娴/几时再见演唱会` appeared under `out/MUSIC/Classical/` instead of `Mandopop/`.

---

### 3. MusicBrainz automatic genre lookup

**Added:** `mb_lookup_genre(artist)` queries `musicbrainz.org/ws/2/artist` (1 req/sec rate limit, results cached in `.mb_cache.json`). Fires as penultimate fallback in `classify_genre()`.

**Cache file:** `.mb_cache.json` in project root — commit to git to persist across machines. Artists found to return wrong genre can be overridden in `ARTIST_GENRE`.

**Audit (now automatic):** every run prints suggestions in the summary report — entries where MusicBrainz now agrees with the local override. Pre-warming queries new ARTIST_GENRE entries at startup.

---

### 4. AcoustID acoustic fingerprinting

**Added:** `acoustid_lookup(fp)` identifies a file by its audio content alone — works on completely untagged files.

**Pipeline:** runs `fpcalc` (chromaprint) on the file → POSTs fingerprint + duration to `api.acoustid.org/v2/lookup` → picks the highest-scoring recording (≥0.7) → fills in title/artist/album/date.

**When triggered:** title/artist missing OR album missing OR album was only filled by path inference (placeholder like the artist name reused as album). Skipped when `ALBUM_META` override applies, or when the source folder was flagged as a compilation.

**Override policy (conservative):**
- `title` / `artist` — only filled if missing. Filename-parsed text is preserved verbatim (don't churn 红日 → 紅日).
- `album` — replaces path-inferred placeholder OR fills if missing.
- `date` — fills if missing.
- Real embedded-tag values are NEVER overridden.

**Setup:**
1. Register a free application at https://acoustid.org/new-application — get API key
2. Either: `export ACOUSTID_API_KEY=your_key`
   Or: write the key into `.acoustid_key` in the project root (gitignored)
3. `fpcalc` auto-installs via brew/apt on first run

**Cache:** `.acoustid_cache.json`, keyed by `path::size` so identical paths skip refetch. Commit to git to persist across machines.

**Without API key:** prints a one-time hint when an eligible file appears, then silently skips.

**API quirks discovered (2025-05-04 debugging session):**
- `urllib.parse.urlencode()` escapes `+` to `%2B`, but AcoustID uses literal `+` as the meta-type separator. Build the body with urlencode for normal fields, then append `&meta=recordings+releases+compress` verbatim.
- `meta=recordings+releasegroups+releases` returns recordings WITHOUT the releases field — adding `releasegroups` suppresses `releases`. Use `meta=recordings+releases+compress` only.
- AcoustID does NOT accept repeated `meta=` parameters; only the `+`-separated form works.

---

### 5. Compilation folder guard

**Added:** Step 2.5 — runs before individual file processing. Detects folders that should be treated as compilations to keep their songs grouped together.

**Why needed:** AcoustID returns the highest-scoring single MusicBrainz release per recording. A given song typically appears on 10–18 different releases (compilations, remasters, regional editions). When 9 songs from a "Best of" folder each match different releases, naive AcoustID-fills scatter the folder across 4–9 destination album folders.

**Detection rule:**
1. Group `audio_files` by `fp.parent`.
2. Skip folders covered by `ALBUM_META` overrides.
3. Skip single-file folders.
4. Skip folders where every file has an embedded album tag.
5. For surviving candidates, look up AcoustID album for each file.
6. If `len(distinct AcoustID albums) >= 2` → flag the folder as a compilation.

**Effect on flagged folders:**
- Step ④.5 skips both `album` and `date` overrides → keeps path-inferred album and leaves date empty.
- Result: all songs land in one shared `{Artist}/{folder-name}/` directory.

**Real-world examples:**
- `唐朝乐队/` — 9 songs across 4 MB albums (中國火 1992, 演义 1999, 梦回唐朝 2008, 美麗新世界 2020). With guard: all in `Chinese Rock/唐朝乐队/唐朝乐队/`.
- `李克勤/DISC 4/` — 3 songs across 3 MB albums (Custom Made 2003, 最好李克勤MD 2001, Purple Dream). With guard: all in `Mandopop/李克勤/李克勤/`.
- `Test/Audio Format/卢冠廷 - 一生所爱/` — 3 different format versions (DSF/FLAC/WAV) of the same song, but AcoustID maps each to a different release. With guard: kept together.

---

### 6a. URL/watermark junk in artist tags

**Symptom:** files from sites like `WWW.HIFI369.COM` had `album_artist=WWW.HIFI369.COM` (download-site URL) → file routed to `Mandopop/WWW.HIFI369.COM/` instead of the real artist's folder. AcoustID didn't help because the field had a value (just garbage), not "missing".

**Fix:** `_clean_junk(s)` in `probe()` clears values matching `_JUNK_TAG_RE` — patterns: `http(s)://`, `www.`, top-level domains (`.com .net .org .cn .io .tv`), Chinese download-site terms (`公众号`, `下载站`). Applied to `artist`, `album_artist`, `album` fields before any other processing.

**Effect:** real `artist=卢冠廷 / 莫文蔚` (which had been masked by the junk `album_artist`) now drives the destination.

---

### 6b. Multi-artist separator inconsistency

**Symptom:** the same duet appeared under three folders because the separator differed between source files:
- `卢冠廷  /  莫文蔚` (WAV, double-space slash)
- `卢冠廷&莫文蔚` (FLAC, ampersand no spaces)
- `卢冠廷 ,  莫文蔚` (some other rip, comma)

**Fix:** `normalize_multi_artist(s)` in `music_organizer.py` runs after canonicalize. Splits on `/`, `&`, `,`, `;`, `feat.`, `ft.`, `featuring`, `with`, `vs.` and rejoins with `, ` (canonical separator). Single-artist names get only whitespace collapse.

**Effect:** all three duet versions now land in `Mandopop/卢冠廷, 莫文蔚/`. Solo `卢冠廷` (no separator) stays as `卢冠廷/`.

**Note:** order of names is preserved — `Lou Kuan-Ting, 莫文蔚` ≠ `莫文蔚, Lou Kuan-Ting`. This is intentional (lead artist usually comes first in tags). If two files credit the duo in opposite order, they'll still split.

---

### 6c. Traditional ↔ Simplified Chinese artist split

**Symptom:** the same artist landed in two folders — `Mandopop/陳慧嫻/` (from embedded tags) AND `Mandopop/陈慧娴/` (from CUE-split files using folder name). Same person, same library, two homes.

**Root cause:** Cantopop / Mandopop CD rips often have artist tags written in traditional Chinese while the user's local folder/file names use simplified. There's no built-in normalization, so `sanitize()` produces two different folder names downstream.

**Fix:** use OpenCC to canonicalize all artist fields to simplified Chinese. `canonicalize(s)` is called on:
- `meta['artist']` and `meta['album_artist']` after all sources merged (individual file path)
- `final_artist` in `split_cue_album()` (CUE path)
- `ARTIST_GENRE` keys at module load time (so matching is script-agnostic)

**Library:** `opencc-python-reimplemented` — pure Python, auto-installed via pip on first run. Uses the `t2s` converter (traditional → simplified). Title and album are deliberately NOT canonicalized — those reflect the album's authored character form.

---

### 7. Filename `{track}. {X} - {Y}` order ambiguity

**Symptom:** files like `03. 红日 - 李克勤.wav` ended up under `Mandopop/红日/红日/` (artist↔title swapped) — the original regex assumed `{track}. {artist} - {title}`.

**Fix:** `infer_from_path()` now uses ancestor folder names + `ARTIST_GENRE` keys + `_MB_CACHE` to disambiguate which token is the artist. If `Y` matches a known artist (or appears in any ancestor folder name) and `X` doesn't, treat as `{track}. {title} - {artist}`.

**Related fix:** when the immediate parent folder matches `DISC|CD|Disk|Disc \s*\d*`, step up to the grandparent for artist/album inference. The disc number is captured into the `disc` field.

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
| Same artist in two folders (e.g. `陳慧嫻/` + `陈慧娴/`) | OpenCC not installed — re-run to auto-install, or check `import opencc` works |
| Songs from a compilation scattered across multiple albums | AcoustID picked different MB releases; verify the source folder has ≥2 files lacking embedded album tag (compilation guard's prerequisites) |
| Multi-disc set missing CDs (e.g. only CD1 in output) | Source folder only contains that disc — `find in/ -name "*.cue"` to confirm what's actually present. Compare CUE filenames (CD1/CD2/Disc1) against expected count |
| AcoustID returned wrong album for a single file | Incorrect MB match. Add an `ALBUM_META` override keyed by source folder name to force the correct values, or delete that entry from `.acoustid_cache.json` and verify the AcoustID score on next run |

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
