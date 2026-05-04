#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Music Organizer v2 — Sony HAP-Z1ES / Walkman / Chord Poly
==========================================================
用法：
  python3 music_organizer.py               # 默认：强制覆盖
  python3 music_organizer.py --no-force    # 跳过大小相同的已有文件

功能：
• CUE+image 整轨拆分（Beethoven FLAC、黄教堂 WAV）via ffmpeg
• 专辑级 metadata 覆盖（ALBUM_META）修正错误/缺失 tag
• 多格式文件名解析器（BAV 合辑、古典 WAV 等）
• 通过 ffmpeg -metadata 将正确 tag 写入目标文件副本
• 封面图搜索（Artwork/ 子目录、.JPG 大写扩展名）
• 孤儿文件清理（metadata 变更后自动删除旧路径文件及空目录）
• 播放列表全量重建（每次运行清除旧 .m3u8 再重新生成）
"""

from __future__ import annotations
import os, json, shutil, re, subprocess, sys, tempfile, time
import urllib.request, urllib.parse
from pathlib import Path
from collections import defaultdict


# ── Dependency bootstrap ───────────────────────────────────────────────────────
def _ensure_deps() -> None:
    """Auto-install missing Python packages and system tools (ffmpeg/ffprobe)."""
    # --- Python: mutagen ---
    try:
        import mutagen  # noqa: F401
    except ImportError:
        print("📦  Installing mutagen …")
        subprocess.run([sys.executable, '-m', 'pip', 'install', '--quiet', 'mutagen'],
                       check=True)
        print("    ✅  mutagen installed")

    # --- System tools ---
    # ffmpeg/ffprobe are required; fpcalc is optional (enables AcoustID lookup).
    def _have(tool: str) -> bool:
        return subprocess.run(['which', tool], capture_output=True).returncode == 0

    def _install(brew_pkg: str, apt_pkg: str, label: str, required: bool = True) -> None:
        if _have('brew'):
            print(f"📦  Installing {label} via Homebrew …")
            subprocess.run(['brew', 'install', brew_pkg], check=required)
            print(f"    ✅  {label} installed")
        elif _have('apt-get'):
            print(f"📦  Installing {label} via apt …")
            subprocess.run(['sudo', 'apt-get', 'install', '-y', apt_pkg], check=required)
            print(f"    ✅  {label} installed")
        else:
            msg = f"⚠️   {label} not found. Install manually."
            if required:
                print(msg)
                sys.exit(1)
            else:
                print(f"{msg} (optional — AcoustID lookup will be disabled)")

    if not (_have('ffmpeg') and _have('ffprobe')):
        _install('ffmpeg', 'ffmpeg', 'ffmpeg', required=True)

    if not _have('fpcalc'):
        _install('chromaprint', 'libchromaprint-tools', 'fpcalc (chromaprint)', required=False)

_ensure_deps()

try:
    from mutagen.wave import WAVE as _MutagenWAVE
    _MUTAGEN_OK = True
except ImportError:
    _MUTAGEN_OK = False

# ── Paths ─────────────────────────────────────────────────────────────────────
_HERE      = Path(__file__).parent
SOURCE     = _HERE / "in"
TEST_ROOT  = SOURCE / 'Test'    # fixed folder; sub-dirs become category names
DEST         = _HERE / "out"
MUSIC_DEST   = DEST / "MUSIC"              # CAPITAL — Sony WM1A only indexes /MUSIC/
PL_DEST      = DEST                        # .m3u files live at SD root (Sony + Poly common ground)
STAGING      = Path(tempfile.gettempdir()) / "music_organizer_staging"  # temp for CUE splits

AUDIO_EXT = {'.flac','.mp3','.m4a','.aac','.wav','.aiff','.aif',
             '.dsf','.dff','.ogg','.opus','.wma','.ape'}
IMG_EXT   = {'.jpg','.jpeg','.png','.JPG','.JPEG','.PNG'}

# ── Genre rules ────────────────────────────────────────────────────────────────
ARTIST_GENRE = {
    # MusicBrainz cannot find these → must keep as local overrides
    'mari nakamoto': 'Jazz',
    '唐朝':          'Chinese Rock',
    'adele':         'Pop',
    'junkie xl':     'Soundtrack',
    'carlo maria giulini': 'Classical',
    'wiener philharmoniker': 'Classical',
    'james levine':  'Classical',
    'schubert':      'Classical',
    'brahms':        'Classical',
    'dvorák':        'Classical',    # MB only finds 'dvorak' (no accent)
    'bach':          'Classical',
    '群星':           'Choral',
    # MusicBrainz returns 'Folk' for these — local Jazz override is intentional
    'alison krauss': 'Jazz',
    'eva cassidy':   'Jazz',
    # CUE album default-genre bug fix (2025-05-04): keep until MB covers these reliably
    '陈慧娴':         'Mandopop',
    '陳慧嫻':         'Mandopop',
}

GENRE_MAP = {
    'jazz':'Jazz','jazz vocal':'Jazz','vocal jazz':'Jazz','bossa nova':'Jazz',
    'swing':'Jazz','blues':'Jazz',
    'classical':'Classical','classic':'Classical','chamber':'Classical',
    'choral':'Choral','choir':'Choral','sacred':'Choral',
    'pop':'Pop','adult contemporary':'Pop',
    'soul':'Pop','r&b':'R&B','funk':'R&B',
    'rock':'Rock','hard rock':'Rock','metal':'Rock','heavy metal':'Rock',
    'chinese rock':'Chinese Rock',
    'cantopop':'Cantopop','cantonese':'Cantopop',
    'mandopop':'Mandopop','mandarin':'Mandopop',
    'electronic':'Electronic','edm':'Electronic',
    'soundtrack':'Soundtrack','soundtracks':'Soundtrack','film score':'Soundtrack',
    'folk':'Folk','acoustic':'Folk','country':'Folk',
    'hip hop':'Hip Hop','rap':'Hip Hop',
}

_GENERIC_FOLDER_RE = re.compile(r'^(?:DISC|CD|Disk|Disc)\s*(\d+)?$', re.I)

JAZZ_TITLES = {
    'time after time','cheek to cheek','unforgettable','but beautiful',
    'blue prelude',"i've got you under my skin","after you've gone",
    "please send me someone to love","sneakin' up on you",
    "ain't no sunshine",'what a wonderful world','over the rainbow',
    'the look of love','perhaps love','skylark','so nice',
    'you light up my life','overjoyed','too young to go steady',
}

# ── MusicBrainz genre lookup ──────────────────────────────────────────────────
_MB_CACHE_PATH = _HERE / '.mb_cache.json'
_MB_CACHE: dict = {}
_MB_LAST_REQ   = 0.0

# MusicBrainz tag → our genre label
_MB_TAG_MAP = {
    'cantopop':      'Cantopop',
    'cantonese pop': 'Cantopop',
    'cantonese':     'Cantopop',
    'mandopop':      'Mandopop',
    'mandarin pop':  'Mandopop',
    'chinese pop':   'Mandopop',
    'c-pop':         'Mandopop',
    'chinese rock':  'Chinese Rock',
    'jazz':          'Jazz',
    'vocal jazz':    'Jazz',
    'jazz vocal':    'Jazz',
    'bossa nova':    'Jazz',
    'classical':     'Classical',
    'orchestra':     'Classical',
    'chamber music': 'Classical',
    'choral':        'Choral',
    'rock':          'Rock',
    'hard rock':     'Rock',
    'metal':         'Metal',
    'heavy metal':   'Metal',
    'soundtrack':    'Soundtrack',
    'film score':    'Soundtrack',
    'pop':           'Pop',
    'hip hop':       'Hip Hop',
    'r&b':           'R&B',
    'electronic':    'Electronic',
    'folk':          'Folk',
}


def _mb_load_cache() -> None:
    global _MB_CACHE
    if _MB_CACHE_PATH.exists():
        try:
            _MB_CACHE = json.loads(_MB_CACHE_PATH.read_text(encoding='utf-8'))
        except Exception:
            _MB_CACHE = {}


def _mb_save_cache() -> None:
    try:
        _MB_CACHE_PATH.write_text(
            json.dumps(_MB_CACHE, ensure_ascii=False, indent=2), encoding='utf-8')
    except Exception:
        pass


def _mb_get(url: str) -> dict:
    global _MB_LAST_REQ
    elapsed = time.time() - _MB_LAST_REQ
    if elapsed < 1.1:
        time.sleep(1.1 - elapsed)
    req = urllib.request.Request(url, headers={
        'User-Agent': 'MusicOrganizer/2.0 (outmyth@gmail.com)',
        'Accept':     'application/json',
    })
    try:
        with urllib.request.urlopen(req, timeout=6) as resp:
            _MB_LAST_REQ = time.time()
            return json.loads(resp.read().decode('utf-8'))
    except Exception:
        _MB_LAST_REQ = time.time()
        return {}


def mb_lookup_genre(artist: str) -> str:
    """Return genre for artist by querying MusicBrainz. Results cached locally."""
    artist = (artist or '').strip()
    if not artist:
        return ''
    key = artist.lower()
    if key in _MB_CACHE:
        return _MB_CACHE[key]

    q    = urllib.parse.quote(f'artist:"{artist}"')
    data = _mb_get(f'https://musicbrainz.org/ws/2/artist?query={q}&limit=1&fmt=json')
    hits = data.get('artists', [])
    if not hits:
        _MB_CACHE[key] = ''
        _mb_save_cache()
        return ''

    mbid   = hits[0].get('id', '')
    detail = _mb_get(f'https://musicbrainz.org/ws/2/artist/{mbid}?inc=tags&fmt=json') if mbid else {}
    tags   = sorted(detail.get('tags', []), key=lambda t: -t.get('count', 0))

    genre = ''
    for tag in tags:
        mapped = _MB_TAG_MAP.get(tag.get('name', '').lower(), '')
        if mapped:
            genre = mapped
            break

    _MB_CACHE[key] = genre
    _mb_save_cache()
    if genre:
        print(f"   🌐  MusicBrainz: {artist!r} → {genre}")
    return genre


_mb_load_cache()


# ── AcoustID acoustic fingerprint lookup ──────────────────────────────────────
# Identifies tracks by audio content alone — no embedded tags or filenames needed.
# Requires fpcalc (chromaprint) + an API key from https://acoustid.org/new-application
_AID_CACHE_PATH  = _HERE / '.acoustid_cache.json'
_AID_KEY_PATH    = _HERE / '.acoustid_key'
_AID_CACHE: dict = {}
_AID_KEY: str    = (os.environ.get('ACOUSTID_API_KEY', '')
                    or (_AID_KEY_PATH.read_text().strip() if _AID_KEY_PATH.exists() else ''))
_AID_LAST_REQ    = 0.0
_AID_WARNED      = False


def _aid_load_cache() -> None:
    global _AID_CACHE
    if _AID_CACHE_PATH.exists():
        try:
            _AID_CACHE = json.loads(_AID_CACHE_PATH.read_text(encoding='utf-8'))
        except Exception:
            _AID_CACHE = {}


def _aid_save_cache() -> None:
    try:
        _AID_CACHE_PATH.write_text(
            json.dumps(_AID_CACHE, ensure_ascii=False, indent=2), encoding='utf-8')
    except Exception:
        pass


def _fpcalc(fp: Path) -> tuple:
    """Run fpcalc to get (duration_seconds, fingerprint). Returns (0, '') on failure."""
    try:
        r = subprocess.run(['fpcalc', '-json', str(fp)],
                           capture_output=True, text=True, timeout=30)
        if r.returncode != 0:
            return (0, '')
        d = json.loads(r.stdout)
        return (int(d.get('duration', 0)), d.get('fingerprint', ''))
    except Exception:
        return (0, '')


def acoustid_lookup(fp: Path) -> dict:
    """Identify a file via AcoustID + MusicBrainz. Returns metadata dict or {}.

    Cached by file path + size so duplicate paths don't refetch.
    Silently no-op if API key isn't configured or fpcalc not installed.
    """
    global _AID_LAST_REQ, _AID_WARNED

    if not _AID_KEY:
        if not _AID_WARNED:
            print("   ℹ️   AcoustID skipped (no API key) — set ACOUSTID_API_KEY env var or .acoustid_key file")
            print("       Get a free key at https://acoustid.org/new-application")
            _AID_WARNED = True
        return {}

    try:
        size = fp.stat().st_size
    except Exception:
        return {}
    cache_key = f"{fp}::{size}"
    if cache_key in _AID_CACHE:
        return _AID_CACHE[cache_key]

    duration, fingerprint = _fpcalc(fp)
    if not fingerprint:
        _AID_CACHE[cache_key] = {}
        _aid_save_cache()
        return {}

    # Rate limit: AcoustID allows 3 req/sec; we use 1 req/sec to be polite.
    elapsed = time.time() - _AID_LAST_REQ
    if elapsed < 0.4:
        time.sleep(0.4 - elapsed)

    url  = 'https://api.acoustid.org/v2/lookup'
    # NOTE: meta MUST stay as 'recordings+releases+…' (single param, '+' separator).
    # AcoustID does NOT accept repeated meta= params, AND urlencode escapes '+' to
    # %2B which breaks the separator. So we urlencode the other fields and append
    # the meta string verbatim.
    body = urllib.parse.urlencode({
        'client':      _AID_KEY,
        'duration':    duration,
        'fingerprint': fingerprint,
    }) + '&meta=recordings+releases+compress'  # NB: adding 'releasegroups' suppresses 'releases'
    body = body.encode('utf-8')
    req = urllib.request.Request(url, data=body, headers={
        'User-Agent':   'MusicOrganizer/2.0 (outmyth@gmail.com)',
        'Content-Type': 'application/x-www-form-urlencoded',
    })

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            _AID_LAST_REQ = time.time()
            data = json.loads(resp.read().decode('utf-8'))
    except Exception:
        _AID_LAST_REQ = time.time()
        _AID_CACHE[cache_key] = {}
        _aid_save_cache()
        return {}

    result = {}
    for hit in data.get('results', []):
        if hit.get('score', 0) < 0.7:
            continue
        for rec in hit.get('recordings', []):
            title    = rec.get('title', '')
            artists  = rec.get('artists', [])
            artist   = ' / '.join(a.get('name', '') for a in artists if a.get('name'))
            releases = rec.get('releases', [])
            album, year = '', ''
            if releases:
                rel   = releases[0]
                album = rel.get('title', '')
                year  = str(rel.get('date', {}).get('year', '')) if rel.get('date') else ''
            if title and artist:
                result = {'title': title, 'artist': artist,
                          'album': album, 'date': year}
                break
        if result:
            break

    _AID_CACHE[cache_key] = result
    _aid_save_cache()
    if result:
        print(f"   🎼  AcoustID: {fp.name} → {result['artist']} - {result['title']}")
    return result


_aid_load_cache()


# ── Album-level overrides (keyed by substring of folder name) ─────────────────
# When embedded tags are incomplete/wrong, these values take precedence.
ALBUM_META = {
    'Best.Audiophile.Voices1': {
        'album': 'Best Audiophile Voices Vol.1',
        'album_artist': 'Various',
        'genre': 'Jazz',
        'year': '2004',
        'parse': 'bav',          # special filename parser
    },
    '古典小提琴名盘': {
        'album': 'Songs My Mother Taught Me',
        'album_artist': 'Various Classical',
        'genre': 'Classical',
        'year': '',
        'parse': 'violin_wav',
    },
    '莫扎特第21': {
        'album': 'Piano Concertos Nos. 21 & 24',
        'album_artist': 'Mozart / Various',
        'artist': 'Mozart / Various',
        'genre': 'Classical',
        'year': '',
        'parse': 'mozart_flac',
    },
    '詹姆斯.莱文': {
        'album': 'Schubert: Trout Quintet & Arpeggione Sonata',
        'album_artist': 'James Levine',
        'artist': 'James Levine',
        'genre': 'Classical',
        'year': '',
        'parse': 'levine_wav',
    },
}

# ── Helpers ────────────────────────────────────────────────────────────────────

def sanitize(name: str, max_len: int = 120) -> str:
    """Strip chars that trip up FAT32/exFAT scanners on Sony WM1A, Lotoo PAW
    Gold 2017, and Chord Poly: half + full-width colon, straight + curly
    apostrophes, exclamation, and the reserved invalid path chars.
    """
    for ch, rep in [('/', '-'), ('\\', '-'),
                    (':', ' - '), ('：', ' - '),             # : and ：
                    ('*', ''), ('?', ''), ('|', '-'),
                    ('"', ''), ('<', ''), ('>', ''),
                    ("'", ''), ('‘', ''), ('’', ''),  # ' ‘ ’
                    ('!', '')]:
        name = name.replace(ch, rep)
    return name.strip('. ')[:max_len]


def run(cmd, check=True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True)


def _probe_wav_mutagen(path: Path) -> dict:
    """Read ID3 chunk from WAV via mutagen (fallback when ffprobe returns garbled tags)."""
    try:
        f = _MutagenWAVE(str(path))
        if not f.tags:
            return {}
        def _t(key):
            frame = f.tags.get(key)
            return str(frame.text[0]) if frame and frame.text else ''
        return {
            'title':        _t('TIT2'),
            'artist':       _t('TPE1') or _t('TPE2'),
            'album_artist': _t('TPE2') or _t('TPE1'),
            'album':        _t('TALB'),
            'genre':        _t('TCON'),
            'date':         _t('TDRC') or _t('TYER'),
            'track':        _t('TRCK'),
            'disc':         _t('TPOS'),
        }
    except Exception:
        return {}


def _has_garbled(tags: dict) -> bool:
    """Return True if any text tag is all question-marks (ffprobe failed to decode)."""
    text_fields = ('title', 'artist', 'album', 'genre')
    for f in text_fields:
        v = tags.get(f, '')
        if v and all(c == '?' for c in v):
            return True
    return False


def probe(path: Path) -> dict:
    r = run(['ffprobe','-v','quiet','-print_format','json',
             '-show_format','-show_streams', str(path)])
    try:
        data = json.loads(r.stdout)
    except Exception:
        return {}
    fmt    = data.get('format', {})
    tags   = {k.lower(): v for k, v in fmt.get('tags', {}).items()}
    audio  = next((s for s in data.get('streams',[])
                   if s.get('codec_type') == 'audio'), {})
    result = {
        'title':        tags.get('title', ''),
        'artist':       tags.get('artist', tags.get('album_artist', '')),
        'album_artist': tags.get('album_artist', tags.get('artist', '')),
        'album':        tags.get('album', ''),
        'genre':        tags.get('genre', ''),
        'date':         tags.get('date', ''),
        'track':        tags.get('track', ''),
        'disc':         tags.get('disc', ''),
        'codec':        audio.get('codec_name', ''),
        'duration':     float(fmt.get('duration', 0)),
        'bitrate':      int(fmt.get('bit_rate', 0) or 0),
    }
    # WAV files may store tags in an ID3 chunk that ffprobe can't decode.
    # Fall back to mutagen when ffprobe returns garbled (all-'?') values.
    if _MUTAGEN_OK and path.suffix.lower() == '.wav' and _has_garbled(result):
        mu = _probe_wav_mutagen(path)
        for key in ('title', 'artist', 'album_artist', 'album', 'genre', 'date', 'track', 'disc'):
            if mu.get(key):
                result[key] = mu[key]
    return result


def year(s: str) -> str:
    m = re.search(r'\b(\d{4})\b', s or '')
    return m.group(1) if m else ''


def track_num(s: str) -> str:
    if not s:
        return ''
    try:
        return f'{int(str(s).split("/")[0]):02d}'
    except Exception:
        return str(s)


def fmt_label(ext: str) -> str:
    return {
        'dsf':'DSD','dff':'DSD',
        'flac':'FLAC','ape':'FLAC',
        'wav':'WAV','aiff':'WAV','aif':'WAV',
        'mp3':'MP3','m4a':'AAC','aac':'AAC',
        'ogg':'OGG','opus':'OGG','wma':'WMA',
    }.get(ext.lower().lstrip('.'), ext.upper().lstrip('.'))


def get_test_category(path: Path) -> str:
    """Return the test category name if path is under SOURCE/Test/, else ''."""
    try:
        return path.relative_to(TEST_ROOT).parts[0]
    except (ValueError, IndexError):
        return ''


# ── Filename parsers ───────────────────────────────────────────────────────────

def parse_bav(fp: Path) -> dict:
    """Best Audiophile Voices: 'Artist_Title.flac' → {artist, title}"""
    stem = fp.stem
    # Some files have Artist_Title, some have different patterns
    # Special case: "Jeanette Lindstrom and Steve Dobrogosz_The Look of Love"
    # Also: "Sylvia Hotel_Cheryl Wheeler" (artist=Sylvia Hotel, title=Cheryl Wheeler?)
    # Actually Sylvia Hotel IS the artist and "Cheryl Wheeler" is perhaps a song name
    # Let's use _ as separator: left=artist, right=title
    if '_' in stem:
        artist, title = stem.split('_', 1)
        return {'artist': artist.strip(), 'title': title.strip()}
    return {'title': stem}


def parse_violin_wav(fp: Path) -> dict:
    """古典小提琴: 'NN.English Title (Composer)  Chinese Title.wav'"""
    stem = fp.stem
    # Pattern: "01.Tempo Di Menuetto in the Style of Pugnani (Kreisler)  小步舞曲(克莱斯勒)"
    m = re.match(r'^(\d+)\.\s*(.+?)(?:\s{2,}|\s*$)', stem)
    if m:
        track_n = m.group(1)
        rest    = m.group(2).strip()
        # Strip trailing Chinese
        eng_part = re.split(r'\s{2,}', rest)[0].strip()
        return {'track': track_n, 'title': eng_part}
    return {}


def parse_mozart_flac(fp: Path) -> dict:
    """莫扎特: '1.Concerto No.21 in C major, K.467 , Allegro maestoso.flac'"""
    stem = fp.stem
    m = re.match(r'^(\d+)\.\s*(.+)$', stem)
    if m:
        return {'track': m.group(1), 'title': m.group(2).strip().rstrip(' ,')}
    return {}


def parse_levine_wav(fp: Path) -> dict:
    """Schubert/Levine WAV: '01.Quintet for Piano...'"""
    stem = fp.stem
    m = re.match(r'^(\d+)\.\s*(.+?)(?:\.{3})?$', stem)
    if m:
        t = m.group(2).strip()
        # Clean truncated title
        t = t.rstrip('.')
        # Shorten extremely long titles
        if 'Quintet for Piano' in t:
            mv_map = {
                'Allegro vivace': 'I. Allegro vivace',
                'Andante': 'II. Andante',
                'Scherzo': 'III. Scherzo: Presto',
                'Andantino': 'IV. Andantino',
                'Finale: Allegro giusto': 'V. Finale: Allegro giusto',
            }
            for k, v in mv_map.items():
                if k in t:
                    return {'track': m.group(1), 'title': v,
                            'album': 'Schubert: Trout Quintet & Arpeggione Sonata'}
        if 'Arpeggione' in t:
            mv_arp = {
                'Allegro moderato': 'Arpeggione Sonata - I. Allegro moderato',
                'Adagio': 'Arpeggione Sonata - II. Adagio',
                'Allegretto': 'Arpeggione Sonata - III. Allegretto',
            }
            for k, v in mv_arp.items():
                if k in t:
                    return {'track': m.group(1), 'title': v,
                            'album': 'Schubert: Trout Quintet & Arpeggione Sonata'}
        if 'Die Forelle' in t or 'The Trout' in t:
            return {'track': m.group(1), 'title': 'Die Forelle (The Trout) D.550',
                    'album': 'Schubert: Trout Quintet & Arpeggione Sonata'}
        return {'track': m.group(1), 'title': t}
    return {}


def infer_from_path(fp: Path) -> dict:
    """Generic fallback: parse from folder name + filename stem."""
    folder       = fp.parent.name
    stem         = fp.stem
    inferred_disc = ''

    # If immediate parent is a generic disc/cd folder, step up to grandparent.
    gm = _GENERIC_FOLDER_RE.match(folder)
    if gm and fp.parent.parent.name:
        inferred_disc = gm.group(1) or ''
        folder = fp.parent.parent.name

    fm = re.match(r'^(.+?)\s*-\s*(.+?)\s*\((\d{4})\)\s*$', folder)
    if fm:
        fa, falb, fy = fm.group(1).strip(), fm.group(2).strip(), fm.group(3)
    else:
        fm2 = re.match(r'^(.+?)\s*-\s*(.+)$', folder)
        fa, falb, fy = (fm2.group(1).strip(), fm2.group(2).strip(), '') if fm2 else (folder, folder, '')

    # Collect all ancestor folder names (lowercase) for artist disambiguation
    ancestors_lower = {p.name.lower() for p in fp.parents}

    track_n, artist, title = '', fa, stem
    m = re.match(r'^(\d+)\.\s+(.+?)\s*[-–]\s*(.+)$', stem)
    if m:
        track_n, g2, g3 = m.group(1), m.group(2).strip(), m.group(3).strip()
        # If g3 matches an ancestor folder or known artist, filename is "{title} - {artist}"
        g3_known = g3.lower() in ancestors_lower or g3.lower() in ARTIST_GENRE or g3.lower() in _MB_CACHE
        g2_known = g2.lower() in ancestors_lower or g2.lower() in ARTIST_GENRE or g2.lower() in _MB_CACHE
        if g3_known and not g2_known:
            artist, title = g3, g2
        else:
            artist, title = g2, g3
    else:
        m2 = re.match(r'^(\d+)\s*[-–]\s*(.+)$', stem)
        if m2:
            track_n, title = m2.group(1), m2.group(2).strip()
        else:
            m3 = re.match(r'^(\d+)\s+(.+)$', stem)
            if m3:
                track_n, title = m3.group(1), m3.group(2).strip()
    return {'title': title, 'artist': artist, 'album_artist': fa,
            'album': falb, 'date': fy, 'track': track_n, 'genre': '', 'disc': inferred_disc}


def classify_genre(meta: dict) -> str:
    artist = (meta.get('artist', '') or '').lower()
    album  = (meta.get('album',  '') or '').lower()
    title  = (meta.get('title',  '') or '').lower()
    genre  = (meta.get('genre',  '') or '').strip()

    for key, g in ARTIST_GENRE.items():
        if key.lower() in artist or key.lower() in album:
            return g

    if genre and genre.lower() not in ('other', 'unknown', ''):
        for key, g in GENRE_MAP.items():
            if key in genre.lower():
                return g
        return genre.title()

    if title.lower() in JAZZ_TITLES:
        return 'Jazz'

    if any('\u4e00' <= c <= '\u9fff' for c in artist + album + title):
        return 'Mandopop'

    mb = mb_lookup_genre(meta.get('artist', ''))
    if mb:
        return mb

    return 'Various'


# ── CUE parsing & splitting ────────────────────────────────────────────────────

def cue_time_to_sec(ts: str) -> float:
    """'MM:SS:FF' → float seconds (FF = 1/75 frames)"""
    parts = ts.strip().split(':')
    if len(parts) == 3:
        return int(parts[0])*60 + int(parts[1]) + int(parts[2])/75.0
    return 0.0


def parse_cue(cue_path: Path) -> list[dict]:
    """Parse CUE sheet → list of track dicts with start_sec."""
    content = None
    for enc in ('utf-8-sig', 'utf-8', 'gb18030', 'gbk', 'big5', 'latin-1'):
        try:
            content = cue_path.read_text(encoding=enc)
            break
        except Exception:
            continue
    if not content:
        return []

    tracks = []
    cur_track = {}
    album_title = ''
    album_artist = ''
    audio_file = cue_path.parent / ''  # default: same dir

    for line in content.splitlines():
        line = line.strip()
        m_file = re.match(r'^FILE\s+"?(.+?)"?\s+\w+$', line, re.IGNORECASE)
        if m_file:
            audio_file = cue_path.parent / m_file.group(1)
            continue

        m_title = re.match(r'^TITLE\s+"?(.+?)"?\s*$', line, re.IGNORECASE)
        if m_title:
            if cur_track:
                cur_track['title'] = m_title.group(1)
            else:
                album_title = m_title.group(1)
            continue

        m_perf = re.match(r'^PERFORMER\s+"?(.+?)"?\s*$', line, re.IGNORECASE)
        if m_perf:
            if cur_track:
                cur_track['performer'] = m_perf.group(1)
            else:
                album_artist = m_perf.group(1)
            continue

        m_date = re.match(r'^REM\s+DATE\s+(\d+)', line, re.IGNORECASE)
        if m_date and not cur_track:
            tracks.append({'__album_date': m_date.group(1)})
            continue

        m_track = re.match(r'^TRACK\s+(\d+)\s+AUDIO', line, re.IGNORECASE)
        if m_track:
            if cur_track and 'number' in cur_track:
                tracks.append(cur_track)
            cur_track = {'number': int(m_track.group(1)), 'audio_file': audio_file,
                         'album_title': album_title, 'album_artist': album_artist}
            continue

        # Use INDEX 01 as the authoritative start time
        m_idx = re.match(r'^INDEX\s+(\d+)\s+(\d+:\d+:\d+)', line, re.IGNORECASE)
        if m_idx and cur_track:
            if m_idx.group(1) == '01':
                cur_track['start_sec'] = cue_time_to_sec(m_idx.group(2))
            continue

    if cur_track and 'number' in cur_track:
        tracks.append(cur_track)

    # Filter out __album_date sentinel
    result = [t for t in tracks if 'number' in t]
    # Compute end times
    for i, t in enumerate(result):
        t['end_sec'] = result[i+1]['start_sec'] if i+1 < len(result) else None
    return result


def split_cue_album(cue_path: Path, album_meta_override: dict,
                    staging_dir: Path, disc_num: str = '', force: bool = False) -> list[dict]:
    """Split a CUE+image into individual files in staging_dir. Returns list of track dicts."""
    print(f"\n   🔪  Splitting CUE: {cue_path.name}")
    tracks_cue = parse_cue(cue_path)
    if not tracks_cue:
        print(f"      ⚠️  Could not parse CUE file")
        return []

    staging_dir.mkdir(parents=True, exist_ok=True)
    results = []

    for t in tracks_cue:
        audio_src = t.get('audio_file')
        if not audio_src or not Path(audio_src).exists():
            print(f"      ⚠️  Audio file not found: {audio_src}")
            continue

        track_n  = t['number']
        title    = t.get('title', f'Track {track_n:02d}')
        artist   = t.get('performer', t.get('album_artist', ''))
        alb_ttl  = t.get('album_title', '')
        start    = t.get('start_sec', 0)
        end      = t.get('end_sec')
        ext      = Path(audio_src).suffix

        # Apply album overrides
        final_artist = album_meta_override.get('artist', artist)
        final_album  = album_meta_override.get('album', alb_ttl)
        final_genre  = album_meta_override.get('genre', '')
        if not final_genre:
            final_genre = classify_genre({'artist': final_artist, 'album': final_album})
        final_year   = album_meta_override.get('year', '')

        dest_fn = f"{track_n:02d} - {sanitize(title, 100)}{ext}"
        dest_fp = staging_dir / dest_fn

        if dest_fp.exists() and not force:
            print(f"      ⏭  Exists: {dest_fn}")
        else:
            dur_arg = []
            if end:
                dur_arg = ['-t', str(end - start)]

            cmd = ['ffmpeg', '-y',
                   '-ss', str(start),
                   '-i', str(audio_src)] + dur_arg + [
                '-c', 'copy',
                '-metadata', f'title={title}',
                '-metadata', f'artist={final_artist}',
                '-metadata', f'album_artist={album_meta_override.get("album_artist", final_artist)}',
                '-metadata', f'album={final_album}',
                '-metadata', f'genre={final_genre}',
                '-metadata', f'date={final_year}',
                '-metadata', f'track={track_n}',
            ]
            if disc_num:
                cmd += ['-metadata', f'disc={disc_num}']
            cmd.append(str(dest_fp))

            r = run(cmd)
            if r.returncode == 0:
                print(f"      ✅  {dest_fn}")
            else:
                print(f"      ❌  Failed: {dest_fn}\n         {r.stderr[-200:]}")
                continue

        # Probe duration
        pr = probe(dest_fp)
        results.append({
            'src':          dest_fp,  # staged split file as "source"
            'title':        title,
            'artist':       final_artist,
            'album_artist': album_meta_override.get('album_artist', final_artist),
            'album':        final_album,
            'genre':        classify_genre({'artist': final_artist, 'album': final_album,
                                            'genre': final_genre, 'title': title}),
            'year':         final_year,
            'track':        f'{track_n:02d}',
            'disc':         disc_num or '',
            'format':       fmt_label(ext),
            'duration':     pr.get('duration', 0),
            'codec':        pr.get('codec', ''),
        })

    return results


def copy_with_meta(src: Path, dest: Path, meta: dict):
    """Copy audio file to dest, writing metadata tags via ffmpeg."""
    dest.parent.mkdir(parents=True, exist_ok=True)

    # If tags are already good and file is same format, just copy
    meta_args = []
    for k in ('title','artist','album_artist','album','genre','date','track','disc'):
        v = meta.get(k, '')
        if v:
            ffmpeg_key = 'album_artist' if k == 'album_artist' else k
            meta_args += ['-metadata', f'{ffmpeg_key}={v}']

    if meta_args:
        cmd = ['ffmpeg', '-y', '-i', str(src),
               '-c', 'copy'] + meta_args + [str(dest)]
        r = run(cmd)
        if r.returncode != 0:
            # Fallback: plain copy
            shutil.copy2(src, dest)
    else:
        shutil.copy2(src, dest)


# ── Cover art search ───────────────────────────────────────────────────────────

def find_cover(folder: Path) -> Path | None:
    """Search a folder (and Artwork/ subdir) for cover art."""
    candidates = ['folder.jpg','cover.jpg','front.jpg','albumart.jpg',
                  'folder.JPG','cover.JPG','Cover.jpg','Cover.JPG',
                  'folder.png','cover.png','0-2.jpg']
    # Artwork subfolder names
    for img in candidates:
        p = folder / img
        if p.exists():
            return p
    # Search Artwork/ or artwork/
    for sub in ('Artwork', 'artwork', 'scans', 'Scans'):
        art_dir = folder / sub
        if art_dir.is_dir():
            for f in art_dir.iterdir():
                if f.suffix.lower() in ('.jpg','.jpeg','.png') and \
                        re.search(r'(cover|front|folder|1\.)', f.name, re.I):
                    return f
            # Just take first jpg
            for f in sorted(art_dir.iterdir()):
                if f.suffix.lower() in ('.jpg','.jpeg','.png'):
                    return f
    # Last resort: any jpg in folder
    for f in folder.iterdir():
        if f.suffix.lower() in ('.jpg','.jpeg','.png') and \
                not f.name.startswith('.'):
            return f
    return None


# ── Main ──────────────────────────────────────────────────────────────────────

def main(force: bool = False):
    print("=" * 65)
    print("  Music Organizer v2  —  Sony / Chord Poly Edition")
    if force:
        print("  [--force] Overwriting existing files")
    print("=" * 65)

    # Pre-warm MB cache for any ARTIST_GENRE entry not yet looked up.
    # This runs silently; 🌐 lines only appear for new lookups.
    uncached = [a for a in ARTIST_GENRE if a.lower() not in _MB_CACHE]
    if uncached:
        print(f"\n🌐  Pre-warming MusicBrainz cache for {len(uncached)} artist(s) …")
        for artist in uncached:
            mb_lookup_genre(artist)

    STAGING.mkdir(parents=True, exist_ok=True)

    # ── Step 1: Discover all audio files + CUE albums ─────────────────────────
    audio_files = []
    cue_albums  = []  # list of (cue_path, disc_label)

    for root, dirs, fnames in os.walk(SOURCE):
        dirs[:] = sorted(d for d in dirs if not d.startswith('.'))
        fp_list  = [Path(root) / fn for fn in sorted(fnames)]

        # Detect CUE+image pattern
        cue_files  = [f for f in fp_list if f.suffix.lower() == '.cue']
        flac_files = [f for f in fp_list if f.suffix.lower() in ('.flac','.wav')]
        # If there's a CUE alongside a single large audio file → split mode
        for cue in cue_files:
            # Find the audio file it references (CUE may be UTF-8, GB18030, etc.)
            raw = cue.read_bytes()[:4000]
            m = re.search(rb'FILE\s+"?(.+?\.(?:flac|wav))"?', raw, re.I)
            if not m:
                continue
            raw_fn = m.group(1)
            ref_audio = None
            for enc in ('utf-8', 'gb18030', 'gbk', 'big5', 'latin-1'):
                try:
                    candidate = Path(root) / raw_fn.decode(enc)
                    if candidate.exists():
                        ref_audio = candidate
                        break
                except Exception:
                    continue
            if ref_audio:
                cue_albums.append((cue, ref_audio))
                if ref_audio in audio_files:
                    audio_files.remove(ref_audio)

        for f in fp_list:
            ext = f.suffix.lower()
            if ext in AUDIO_EXT:
                # Skip files that are CUE image sources (handled separately)
                already_cue = any(ref == f for _, ref in cue_albums)
                if not already_cue:
                    audio_files.append(f)

    # Deduplicate CUE albums (same ref_audio with multiple CUE → keep all)
    print(f"\n🔍  Found {len(audio_files)} individual audio files")
    print(f"    Found {len(cue_albums)} CUE+image album(s) to split")

    all_tracks = []  # final track list for playlists & index

    # ── Step 2: Split CUE+image albums ────────────────────────────────────────
    print("\n📀  Processing CUE+image albums …")
    for cue_path, ref_audio in cue_albums:
        folder_name = cue_path.parent.name
        # Determine disc number from CUE filename (CD1, CD2, Disc1, …)
        disc_m = re.search(r'(?:CD|Disc|D)(\d+)', cue_path.stem, re.I)
        disc_n = disc_m.group(1) if disc_m else ''

        # Find album override
        override = {}
        for key, vals in ALBUM_META.items():
            if key.lower() in folder_name.lower() or key.lower() in str(cue_path).lower():
                override = vals.copy()
                break

        # Defaults from CUE + known mappings
        if 'Beethoven' in folder_name or 'Giulini' in folder_name:
            override.setdefault('album',        'Beethoven: Symphonies Nos. 3 & 4')
            override.setdefault('album_artist', 'Carlo Maria Giulini')
            override.setdefault('artist',       'Carlo Maria Giulini / Wiener Philharmoniker')
            override.setdefault('genre',        'Classical')
            override.setdefault('year',         '2011')
        elif '黄教堂' in folder_name or '麦田' in folder_name:
            override.setdefault('album',        'Now the Green Blade Riseth')
            override.setdefault('album_artist', '群星')
            override.setdefault('artist',       '群星')
            override.setdefault('genre',        'Choral')
            override.setdefault('year',         '2008')

        stage_sub = STAGING / sanitize(folder_name, 60) / (f"CD{disc_n}" if disc_n else "CD")
        tracks = split_cue_album(cue_path, override, stage_sub, disc_n, force=force)
        cat = get_test_category(cue_path)
        for t in tracks:
            t['test_category'] = cat
        all_tracks.extend(tracks)

    # ── Step 2.5: Detect compilation folders ──────────────────────────────────
    # If multiple files in the same source folder lack embedded album tags AND
    # AcoustID would assign them to different albums, treat the folder as a
    # compilation and keep the folder name as the album. Prevents scattering
    # files like 'DISC 4/01.wav, 02.wav, 03.wav' across 3 unrelated MB releases.
    compilation_folders = set()
    if _AID_KEY:
        def _has_album_meta_override(folder: Path) -> bool:
            fname = folder.name.lower()
            full  = str(folder).lower()
            return any(k.lower() in fname or k.lower() in full for k in ALBUM_META)

        by_src_folder = defaultdict(list)
        for fp in audio_files:
            by_src_folder[fp.parent].append(fp)
        for folder, files in by_src_folder.items():
            if len(files) < 2:
                continue
            # Skip folders already covered by ALBUM_META — AcoustID won't run there.
            if _has_album_meta_override(folder):
                continue
            # Only check folders where ≥1 file lacks embedded album tag
            needs_check = any(not probe(f).get('album') for f in files)
            if not needs_check:
                continue
            albums = set()
            for f in files:
                aid = acoustid_lookup(f)
                if aid.get('album'):
                    albums.add(aid['album'])
            if len(albums) > 1:
                compilation_folders.add(folder)
        if compilation_folders:
            print(f"\n📚  Compilation folders detected ({len(compilation_folders)}) "
                  f"— keeping folder name as album:")
            for folder in sorted(compilation_folders):
                print(f"    {folder.relative_to(SOURCE)}")

    # ── Step 3: Process individual audio files ─────────────────────────────────
    print(f"\n📁  Processing {len(audio_files)} individual files …")
    missing_tags = []

    for fp in audio_files:
        meta = probe(fp)
        folder_name = fp.parent.name

        # Check for album-level override
        override = {}
        special_parse = None
        for key, vals in ALBUM_META.items():
            if key.lower() in folder_name.lower() or key.lower() in str(fp).lower():
                override = vals.copy()
                special_parse = override.pop('parse', None)
                break

        # Apply special parsers first (they override embedded tags for known-bad files)
        parsed = {}
        if special_parse == 'bav':
            parsed = parse_bav(fp)
        elif special_parse == 'violin_wav':
            parsed = parse_violin_wav(fp)
        elif special_parse == 'mozart_flac':
            parsed = parse_mozart_flac(fp)
        elif special_parse == 'levine_wav':
            parsed = parse_levine_wav(fp)

        # For Best Audiophile Voices: tags are wrong, use filename parse
        if special_parse == 'bav':
            meta['artist'] = parsed.get('artist', meta.get('artist', ''))
            meta['title']  = parsed.get('title',  meta.get('title', ''))
            # Fix album_artist tag which is stored as "album artist" (space)
            if not meta.get('album_artist'):
                meta['album_artist'] = meta.get('album artist', 'Various')

        # Fallback to inferred data — track which fields came from path inference
        # so AcoustID can later override placeholder values (e.g. album = folder name)
        # without clobbering high-confidence values from embedded tags or parsers.
        inf            = infer_from_path(fp)
        inferred_only  = set()
        for field in ('title','artist','album_artist','album','date','track','genre','disc'):
            if not meta.get(field):
                if parsed.get(field):
                    meta[field] = parsed[field]
                elif inf.get(field):
                    meta[field] = inf[field]
                    inferred_only.add(field)

        # AcoustID fingerprint lookup. Conservative override policy:
        #   • title / artist : only filled if completely MISSING. Filename-parsed
        #     values are kept as-is — avoids simp↔trad churn (e.g. 红日 → 紅日).
        #   • album          : filled if missing OR if value came from path
        #     inference (folder-name placeholder like '李克勤' for the album).
        #   • date           : filled if missing.
        if not override and (
            not meta.get('title')
            or not meta.get('artist')
            or not meta.get('album') or 'album' in inferred_only
        ):
            aid = acoustid_lookup(fp)
            # Only fill missing title/artist; never overwrite filename-parsed text
            for field in ('title', 'artist'):
                if not meta.get(field) and aid.get(field):
                    meta[field] = aid[field]
            # Album + date: replace path-inferred placeholder, or fill if missing.
            # Skip both if folder was flagged as a compilation — different songs
            # in the folder map to different MB releases, so per-track albums &
            # years would scatter them. Keep folder name + no-year to group them.
            is_compilation = fp.parent in compilation_folders
            if (aid.get('album') and not is_compilation
                    and (not meta.get('album') or 'album' in inferred_only)):
                meta['album'] = aid['album']
            if aid.get('date') and not meta.get('date') and not is_compilation:
                meta['date'] = aid['date']
            # album_artist: fill if missing only
            if aid.get('artist') and not meta.get('album_artist'):
                meta['album_artist'] = aid['artist']

        # Apply album overrides (highest priority for album/genre/year)
        for k in ('album','album_artist','artist','genre','year'):
            if k in override:
                if k == 'year':
                    meta['date'] = override[k]
                else:
                    meta[k] = override[k]
        # Parsed track/title takes priority over override for those fields
        for k in ('track','title'):
            if parsed.get(k):
                meta[k] = parsed[k]

        genre  = classify_genre(meta)
        yr     = year(meta.get('date',''))
        tn     = track_num(meta.get('track',''))
        disc   = track_num(meta.get('disc',''))
        artist  = sanitize(meta.get('album_artist') or meta.get('artist') or 'Unknown Artist')
        album   = sanitize(meta.get('album') or 'Unknown Album')
        title   = sanitize(meta.get('title') or fp.stem, max_len=200)
        ext     = fp.suffix
        fmt     = fmt_label(ext)

        # Folder: Music/[Category/]Genre/Artist/(Year) Album/
        alb_folder = f"({yr}) {album}" if yr else album
        # Add disc subfolder if multi-disc
        disc_folder = f"CD{disc}" if disc and disc not in ('01','1') else ''
        cat = get_test_category(fp)
        if cat:
            dest_dir = MUSIC_DEST / 'Test' / sanitize(cat) / sanitize(genre) / artist / sanitize(alb_folder)
        else:
            dest_dir = MUSIC_DEST / sanitize(genre) / artist / sanitize(alb_folder)
        if disc_folder:
            dest_dir = dest_dir / disc_folder

        dest_fn = f"{tn} - {title}{ext}" if tn else f"{title}{ext}"
        dest_fp = dest_dir / dest_fn

        # Decide whether metadata needs rewriting
        needs_tag_write = bool(override or special_parse)
        meta_to_write = {
            'title':        meta.get('title') or fp.stem,
            'artist':       meta.get('artist') or 'Unknown',
            'album_artist': meta.get('album_artist') or meta.get('artist') or 'Unknown',
            'album':        meta.get('album') or 'Unknown Album',
            'genre':        genre,
            'date':         yr,
            'track':        tn,
            'disc':         disc,
        }

        dest_dir.mkdir(parents=True, exist_ok=True)
        if force or not dest_fp.exists() or dest_fp.stat().st_size != fp.stat().st_size:
            if needs_tag_write:
                copy_with_meta(fp, dest_fp, meta_to_write)
            else:
                shutil.copy2(fp, dest_fp)
            status = "📝" if needs_tag_write else "✅"
            print(f"   {status}  {genre}/{artist}/{alb_folder}/{dest_fn}")
        else:
            print(f"   ⏭  {dest_fn}")

        # Flag missing tags
        missing = [f for f in ('title','artist','album') if not meta.get(f)]
        if missing:
            missing_tags.append((fp.name, missing))

        all_tracks.append({
            'src':           fp,
            'dest':          dest_fp,
            'dest_dir':      dest_dir,
            'title':         meta_to_write['title'],
            'artist':        meta_to_write['artist'],
            'album':         meta_to_write['album'],
            'album_artist':  meta_to_write['album_artist'],
            'genre':         genre,
            'year':          yr,
            'track':         tn,
            'disc':          disc,
            'format':        fmt,
            'duration':      meta.get('duration', 0),
            'codec':         meta.get('codec', ''),
            'test_category': cat,
        })

    # ── Step 4: CUE tracks → finalize dest paths ──────────────────────────────
    print(f"\n📁  Organizing {len([t for t in all_tracks if 'dest_dir' not in t])} CUE tracks …")
    for t in all_tracks:
        if 'dest_dir' in t:
            continue  # already handled above

        src = t['src']  # staged file
        genre  = t['genre']
        yr     = t['year']
        artist = sanitize(t['album_artist'] or t['artist'])
        album  = sanitize(t['album'])
        title  = sanitize(t['title'])
        disc   = t.get('disc', '')
        ext    = src.suffix

        alb_folder = f"({yr}) {album}" if yr else album
        disc_folder = f"CD{disc}" if disc and disc.lstrip('0') else ''
        cat = t.get('test_category', '')
        if cat:
            dest_dir = MUSIC_DEST / 'Test' / sanitize(cat) / sanitize(genre) / artist / sanitize(alb_folder)
        else:
            dest_dir = MUSIC_DEST / sanitize(genre) / artist / sanitize(alb_folder)
        if disc_folder:
            dest_dir = dest_dir / disc_folder

        tn = t['track']
        title_s = sanitize(t['title'], 120)
        dest_fn = f"{tn} - {title_s}{ext}"
        dest_fp = dest_dir / dest_fn
        dest_dir.mkdir(parents=True, exist_ok=True)

        if force or not dest_fp.exists():
            shutil.copy2(src, dest_fp)
            prefix = f"Test/{cat}/" if cat else ""
            print(f"   ✅  {prefix}{genre}/{artist}/{alb_folder}/{dest_fn}")
        else:
            print(f"   ⏭  {dest_fn}")

        t['dest']     = dest_fp
        t['dest_dir'] = dest_dir

    # ── Step 5: Cover art ─────────────────────────────────────────────────────
    print("\n🖼   Copying cover art …")
    art_done = set()
    art_copied = 0
    for t in all_tracks:
        dest_dir = t.get('dest_dir')
        if not dest_dir or dest_dir in art_done:
            continue
        art_done.add(dest_dir)

        # Find cover from source
        src = t['src']
        # Look in original source folder (for staged CUE splits, go up to source album)
        search_dirs = [src.parent]
        # For staged files, also check the original CUE folder
        if str(STAGING) in str(src):
            # Try to find the original folder in SOURCE
            folder_key = src.parent.parent.name  # e.g. "Carlo Maria Giulini..."
            for root, dirs, _ in os.walk(SOURCE):
                if folder_key in root:
                    search_dirs.append(Path(root))
                    break
            # Also search for album title substring
            for root, dirs, _ in os.walk(SOURCE):
                alb_part = t.get('album', '')[:15].lower()
                if alb_part and alb_part in root.lower():
                    search_dirs.append(Path(root))

        cover_src = None
        for d in search_dirs:
            cover_src = find_cover(d)
            if cover_src:
                break

        dst_art = dest_dir / 'folder.jpg'
        if cover_src and not dst_art.exists():
            shutil.copy2(cover_src, dst_art)
            art_copied += 1
    print(f"   ✅  {art_copied} cover art file(s) copied.")

    # ── Step 6: Generate playlists ────────────────────────────────────────────
    # Single output location: SD card root (= DEST). Paths inside use the
    # "MUSIC/<genre>/..." form (no leading slash, no `..`) — the only format
    # that resolves correctly on BOTH targets:
    #   - Sony Walkman: standard M3U, paths relative to playlist file. With
    #                   .m3u at SD root, "MUSIC/..." → "/MUSIC/..." ✓
    #   - Chord Poly (MPD): paths relative to music_directory (= SD root),
    #                   "MUSIC/..." resolves correctly ✓
    #
    # Extension: .m3u (not .m3u8) — Chord Poly GoFigure is unreliable with
    # .m3u8; content is still UTF-8 + BOM. Line terminator: CRLF.
    print(f"\n🎵  Generating playlists …")
    PL_DEST.mkdir(parents=True, exist_ok=True)
    # Full rebuild: clear stale .m3u/.m3u8 from SD root, plus legacy
    # MUSIC/Playlists/ and playlists/ subdirs from prior runs.
    for old in list(PL_DEST.glob('*.m3u')) + list(PL_DEST.glob('*.m3u8')):
        old.unlink()
    for legacy in (MUSIC_DEST / 'Playlists', DEST / 'playlists'):
        if legacy.exists():
            shutil.rmtree(legacy)
    for sub in ('by_album', 'by_artist', 'by_format'):
        old = PL_DEST / sub
        if old.exists():
            shutil.rmtree(old)

    by_album  = defaultdict(list)
    by_artist = defaultdict(list)
    by_format = defaultdict(list)
    by_test   = defaultdict(list)

    hdr = '#EXTM3U\n#EXTENC:UTF-8\n\n'

    def entry(t):
        """Path relative to SD root (DEST) — works for Sony + Poly."""
        dur = int(t.get('duration', 0))
        rel = os.path.relpath(str(t['dest']), str(DEST)).replace(chr(92), '/')
        return f"#EXTINF:{dur},{t['artist']} - {t['title']}\n{rel}\n"

    def open_pl(pl_file: Path):
        """UTF-8 + BOM + CRLF — max SD-card DAP compatibility."""
        return pl_file.open('w', encoding='utf-8-sig', newline='\r\n')

    def write_playlists(name: str, tracks: list) -> int:
        valid = [t for t in tracks if 'dest' in t]
        pl_file = PL_DEST / name
        with open_pl(pl_file) as f:
            f.write(hdr)
            for t in valid:
                f.write(entry(t))
        return len(valid)

    # Sort: artist > album > disc > track > title
    sorted_tracks = sorted(all_tracks,
        key=lambda x: (x.get('artist',''), x.get('album',''),
                       x.get('disc',''), x.get('track',''), x.get('title','')))

    # Bucket tracks (test tracks excluded from album/artist/format cuts)
    for t in sorted_tracks:
        if 'dest' not in t:
            continue
        if t.get('test_category'):
            by_test[t['test_category']].append(t)
            continue
        alb_key = f"{sanitize(t['album_artist'],50)} - {sanitize(t['album'],60)}"
        art_key = sanitize(t['album_artist'] or t['artist'], 80)
        by_album[alb_key].append(t)
        by_artist[art_key].append(t)
        by_format[t['format']].append(t)

    # Naming convention: <Category>_<Name>.m3u
    #   Underscore separates category from name (two-level grouping signal),
    #   hyphen " - " separates fields within name (artist - album).
    #   All ASCII, unambiguous, DAP-friendly.

    # ── All.m3u ───────────────────────────────────────────────────────────────
    total_valid = write_playlists('All.m3u', sorted_tracks)

    # ── Album_<Artist> - <Album>.m3u ──────────────────────────────────────────
    for alb_key in sorted(by_album):
        write_playlists(
            f"Album_{sanitize(alb_key, 100)}.m3u",
            sorted(by_album[alb_key], key=lambda x: (x.get('disc',''), x.get('track',''))))

    # ── Artist_<Artist>.m3u ───────────────────────────────────────────────────
    for art_key in sorted(by_artist):
        write_playlists(
            f"Artist_{sanitize(art_key, 100)}.m3u",
            sorted(by_artist[art_key], key=lambda x: (x.get('album',''), x.get('disc',''), x.get('track',''))))

    # ── Format_<Fmt>.m3u ──────────────────────────────────────────────────────
    for fmt_key in sorted(by_format):
        write_playlists(
            f"Format_{fmt_key}.m3u",
            sorted(by_format[fmt_key], key=lambda x: (x.get('artist',''), x.get('title',''))))

    # ── Test_<Category>.m3u ───────────────────────────────────────────────────
    for cat, tlist in sorted(by_test.items()):
        name = f"Test_{sanitize(cat, 60)}.m3u"
        n = write_playlists(
            name,
            sorted(tlist, key=lambda x: (x.get('genre',''), x.get('artist',''),
                                          x.get('album',''), x.get('track',''))))
        print(f"   ✅  {name} ({n} tracks)")

    print(f"   ✅  All.m3u ({total_valid} tracks)")
    print(f"   ✅  Album_*.m3u  ({len(by_album)} playlists)")
    print(f"   ✅  Artist_*.m3u ({len(by_artist)} playlists)")
    print(f"   ✅  Format_*.m3u ({len(by_format)} playlists: {', '.join(sorted(by_format))})")
    print(f"   📁  All playlists written to SD root: {PL_DEST}")

    # ── Step 7: Orphan cleanup ────────────────────────────────────────────────
    # Collect every file this run intentionally wrote to Organized/Music/
    expected_files: set[Path] = set()
    for t in all_tracks:
        if 'dest' in t:
            expected_files.add(t['dest'])
        if 'dest_dir' in t:
            expected_files.add(t['dest_dir'] / 'folder.jpg')

    orphans: list[Path] = []
    if MUSIC_DEST.exists():
        for p in MUSIC_DEST.rglob('*'):
            if not p.is_file():
                continue
            if p.name == '.DS_Store':
                orphans.append(p)
            elif p.suffix.lower() in AUDIO_EXT or p.name.lower() == 'folder.jpg':
                if p not in expected_files:
                    orphans.append(p)

    def dir_is_empty(d: Path) -> bool:
        """True if directory has no files other than .DS_Store."""
        return not any(f for f in d.iterdir() if f.name != '.DS_Store')

    if orphans:
        print(f"\n🗑   Removing {len(orphans)} orphan file(s) …")
        for p in orphans:
            p.unlink()
            if p.name != '.DS_Store':
                print(f"   🗑  {p.relative_to(MUSIC_DEST)}")
        # Remove empty directories bottom-up (deepest first)
        for dirpath in sorted(MUSIC_DEST.rglob('*'), key=lambda x: len(x.parts), reverse=True):
            if dirpath.is_dir() and dir_is_empty(dirpath):
                # Remove any remaining .DS_Store before rmdir
                ds = dirpath / '.DS_Store'
                if ds.exists():
                    ds.unlink()
                dirpath.rmdir()
                print(f"   🗑  (empty dir) {dirpath.relative_to(MUSIC_DEST)}/")
    else:
        print("\n🗑   No orphan files found.")

    # ── Step 8: Summary report ────────────────────────────────────────────────
    print("\n" + "=" * 65)
    print("  SUMMARY REPORT")
    print("=" * 65)

    genre_c = defaultdict(int)
    fmt_c   = defaultdict(int)
    for t in all_tracks:
        if 'dest' in t:
            genre_c[t['genre']] += 1
            fmt_c[t['format']] += 1

    print(f"\n📊  Tracks by Genre:")
    for g, n in sorted(genre_c.items()):
        print(f"    {g:<22} {n:>4} tracks")

    print(f"\n📊  Tracks by Format:")
    for f, n in sorted(fmt_c.items()):
        print(f"    {f:<10} {n:>4} tracks")

    total_dur = sum(t.get('duration', 0) for t in all_tracks if 'dest' in t)
    print(f"\n⏱   Total: {total_valid} tracks, "
          f"{int(total_dur//3600)}h {int((total_dur%3600)//60)}m")

    if missing_tags:
        print(f"\n⚠️   Files still missing tags ({len(missing_tags)}):")
        for fn, fields in missing_tags[:10]:
            print(f"    {fn}  — missing: {', '.join(fields)}")
        if len(missing_tags) > 10:
            print(f"    … and {len(missing_tags)-10} more")

    # ── ARTIST_GENRE audit (uses cache only, no new network calls) ────────────
    removable = [
        (a, g) for a, g in ARTIST_GENRE.items()
        if _MB_CACHE.get(a.lower()) == g
    ]
    if removable:
        print(f"\n💡  ARTIST_GENRE entries MusicBrainz can now cover ({len(removable)}) — safe to remove:")
        for artist, genre in removable:
            print(f"    '{artist}': '{genre}'")

    print(f"\n✅  Done! Output: {DEST}")
    print("=" * 65)


def audit_artist_genre() -> None:
    """Query MusicBrainz for every entry in ARTIST_GENRE and report which are safe to remove."""
if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser(
        description='Music Organizer v2 — Sony HAP-Z1ES / Walkman / Chord Poly',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            '默认行为（无参数）等同于 --force：\n'
            '  强制覆盖已有文件。\n\n'
            '示例：\n'
            '  python3 music_organizer.py              # 全量处理\n'
            '  python3 music_organizer.py --no-force   # 跳过大小相同的已有文件\n'
        ),
    )
    ap.add_argument('--no-force', dest='force', action='store_false',
                    help='跳过大小相同的已有文件（默认：强制覆盖）')
    ap.set_defaults(force=True)
    args = ap.parse_args()
    main(force=args.force)
