#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unified Playlist Generator — Sony HAP-Z1ES / Walkman  +  Chord Poly (MPD)
==========================================================================
Single path format: relative to Organized/ root  →  Music/Jazz/…
• Sony: reads M3U8 from Organized/ root; resolves Music/… relative to that
• Poly MPD: set music_directory = /path/to/Organized/
             set playlist_directory = /path/to/Organized/
             MPD resolves paths relative to music_directory → Music/… ✓

WHY "../Music/…" IS WRONG FOR POLY:
  MPD resolves M3U8 paths relative to music_directory, NOT the playlist file.
  (Documented in MPD GitHub Issue #200 and Chord Poly official examples.)
  Using "../Music/…" would make MPD look for "Organized/../Music/…" = wrong.

Output layout (placed directly in Organized/ root):
  Organized/
    All_Music.m3u8
    Jazz_Night.m3u8
    Classical_HiRes.m3u8
    DSD_Favorites.m3u8
    Audiophile_Voices.m3u8
    Soundtrack_Cinema.m3u8
    Chinese_Rock.m3u8
    HiRes_All.m3u8
    Test_Beyerdynamic_T1.m3u8
    by_album/  Artist/  Album.m3u8
    by_artist/ Artist.m3u8
    by_format/ FLAC.m3u8 / DSD.m3u8 / …
    playlists/music_index.json   ← index only, no playlist files here
"""

import json, os
from pathlib import Path
from collections import defaultdict

DEST       = Path("/sessions/great-modest-maxwell/mnt/Music/Organized")
MUSIC_ROOT = DEST / "Music"
PL_ROOT    = DEST          # playlists go in Organized/ root (not playlists/ subdir)
IDX_DIR    = DEST / "playlists"  # music_index.json stays here

# ── helpers ───────────────────────────────────────────────────────────────────

def hdr():
    return '#EXTM3U\n#EXTENC:UTF-8\n\n'

def rel(track_path: Path, from_dir: Path = None) -> str:
    """Path relative to Organized/ root (DEST) — works for both Sony and Poly/MPD.

    Sony reads playlists from Organized/ root, so 'Music/Jazz/…' resolves correctly.
    Poly MPD (music_directory = Organized/) resolves paths relative to music_directory,
    so 'Music/Jazz/…' also resolves correctly.

    The `from_dir` parameter is kept for API compatibility but is no longer used.
    """
    return str(track_path.relative_to(DEST)).replace('\\', '/')

def extinf(t: dict) -> str:
    dur = int(t.get('duration_sec', 0))
    return f"#EXTINF:{dur},{t['artist']} - {t['title']}"

def write_pl(pl_path: Path, tracks: list, comment: str = ''):
    pl_path.parent.mkdir(parents=True, exist_ok=True)
    with pl_path.open('w', encoding='utf-8') as f:
        f.write(hdr())
        if comment:
            f.write(f'# {comment}\n\n')
        for t in tracks:
            tp = DEST / t['path']
            f.write(extinf(t) + '\n')
            f.write(rel(tp) + '\n')
    return len(tracks)

def load_index():
    with (IDX_DIR / 'music_index.json').open(encoding='utf-8') as f:
        return json.load(f)['tracks']

def sort_key(t):
    return (t.get('genre',''), t.get('artist',''), t.get('album',''),
            t.get('disc',''), t.get('track',''), t.get('title',''))

# ── test track criteria (Beyerdynamic T1 试音碟) ─────────────────────────────
T1_PICKS = [
    ('01 - Time After Time.dsf',              'DSD 极低底噪·超高解析度'),
    ("05 - Cheek To Cheek.dsf",               'DSD 刷鼓+钢琴泛音 — 高频音色'),
    ("08 - I've Got You Under My Skin.dsf",   'DSD 爵士人声 — 声部分离·质感'),
    ('01 - Beethoven - Symphony No. 3',       '管弦乐动态范围 — 弱到强冲击'),
    ('01 - Beethoven - Symphony No. 4',       '交响曲4号 — 弦乐泛音·声场宽度'),
    ("11 - Ain't No Sunshine",                'Eva Cassidy — 吉他质感·人声透明度'),
    ('01 - Over The Rainbow',                 'Jane Monheit — 爵士人声·自然空间感'),
    ('16 - Someone Like You',                 'Adele 现场 — 钢琴+人声动态·厅堂感'),
    ('01 - Hometown Glory',                   'Adele 开场 — 低频重量·舞台规模'),
    ('01 - Concerto No.21 in C major',        'Mozart K.467 — 钢琴协奏曲·高频瞬态'),
    ('01 - Quintet for Piano, Violin',        'Schubert 鳟鱼五重奏 — 室内乐分离度'),
    ('06 - Arpeggione Sonata - I.',           '阿尔佩乔内奏鸣曲 — 大提琴中低频'),
    ('01 - Tempo Di Menuetto',                '古典小提琴 — 高频顺滑 vs 刺耳 测试'),
    ('15 - Songs My Mother Taught Me',        '德沃夏克·小提琴 — WAV 音色·余韵'),
    ('01 - Return to Croft Manor',            'Junkie XL — 电影音乐低频冲击'),
    ('13 - Becoming the Tomb Raider',         'Tomb Raider 高潮 — 铜管+打击乐爆发'),
    ('09 - SAID JUDAS TO MARY',               '黄教堂 K2HD 合唱 — 声场深度·层次'),
    ('01 - 夢回唐朝',                          '唐朝电吉他开场 — 摇滚能力·高频刺激性'),
]

def build_t1(all_tracks):
    used, result = set(), []
    for crit, reason in T1_PICKS:
        for t in all_tracks:
            p = t['path']
            if crit.lower() in p.lower() and p not in used:
                result.append({**t, '_reason': reason})
                used.add(p)
                break
    return result

# ── main ─────────────────────────────────────────────────────────────────────

def main():
    print('=' * 60)
    print('  Unified Playlist Generator  (Sony + Poly compatible)')
    print('=' * 60)

    all_tracks = load_index()
    tracks = sorted(all_tracks, key=sort_key)
    print(f'\n📋  {len(tracks)} tracks loaded\n')

    counts = {}

    # ── All Music ─────────────────────────────────────────────────────────────
    n = write_pl(PL_ROOT / 'All_Music.m3u8', tracks)
    counts['All_Music'] = n
    print(f'✅  All_Music.m3u8  ({n})')

    # ── Scene playlists ───────────────────────────────────────────────────────
    scenes = [
        ('Jazz_Night',       '🎷 Jazz Night — DSD + FLAC 爵士人声精选',
         lambda t: t['genre'] == 'Jazz'),

        ('Classical_HiRes',  '🎻 Classical Hi-Res — 古典 FLAC/WAV/DSD',
         lambda t: t['genre'] in ('Classical', 'Choral')
                   and t['format'] in ('FLAC', 'WAV', 'DSD')),

        ('DSD_Favorites',    '💿 DSD Favorites — 全部 DSD 曲目',
         lambda t: t['format'] == 'DSD'),

        ('Audiophile_Voices','🎤 Audiophile Voices — 人声精选 (Jazz + Pop)',
         lambda t: t['genre'] in ('Jazz', 'Pop')
                   and t['format'] in ('FLAC', 'WAV', 'DSD')),

        ('Soundtrack_Cinema','🎬 Soundtrack — 电影原声',
         lambda t: t['genre'] == 'Soundtrack'),

        ('Chinese_Rock',     '🎸 Chinese Rock — 唐朝',
         lambda t: t['genre'] == 'Chinese Rock'),

        ('HiRes_All',        '⭐ Hi-Res All — FLAC + WAV + DSD（排除 OGG）',
         lambda t: t['format'] in ('FLAC', 'WAV', 'DSD')),
    ]

    for name, comment, fn in scenes:
        sel = [t for t in tracks if fn(t)]
        n = write_pl(PL_ROOT / f'{name}.m3u8', sel, comment)
        counts[name] = n
        print(f'✅  {name}.m3u8  ({n})')

    # ── by_album ──────────────────────────────────────────────────────────────
    by_album = defaultdict(list)
    for t in tracks:
        by_album[(t.get('album_artist',''), t.get('album',''))].append(t)

    (PL_ROOT / 'by_album').mkdir(exist_ok=True)
    alb_count = 0
    for (aa, alb), tlist in sorted(by_album.items()):
        safe_aa  = aa[:60].replace('/', '-').replace(':', '-').strip('. ')
        safe_alb = alb[:80].replace('/', '-').replace(':', '-').strip('. ')
        sub = PL_ROOT / 'by_album' / safe_aa
        fn  = f'{safe_aa} - {safe_alb}.m3u8'
        sl  = sorted(tlist, key=lambda x: (x.get('disc',''), x.get('track','')))
        write_pl(sub / fn, sl)
        alb_count += 1
    print(f'✅  by_album/  ({alb_count} playlists)')

    # ── by_artist ─────────────────────────────────────────────────────────────
    by_artist = defaultdict(list)
    for t in tracks:
        by_artist[t.get('album_artist') or t.get('artist','')].append(t)

    (PL_ROOT / 'by_artist').mkdir(exist_ok=True)
    for aa, tlist in sorted(by_artist.items()):
        safe = aa[:100].replace('/', '-').replace(':', '-').strip('. ')
        sl = sorted(tlist, key=lambda x: (x.get('album',''), x.get('disc',''), x.get('track','')))
        write_pl(PL_ROOT / 'by_artist' / f'{safe}.m3u8', sl)
    print(f'✅  by_artist/  ({len(by_artist)} playlists)')

    # ── by_format ─────────────────────────────────────────────────────────────
    by_fmt = defaultdict(list)
    for t in tracks:
        by_fmt[t.get('format','?')].append(t)

    (PL_ROOT / 'by_format').mkdir(exist_ok=True)
    for fmt, tlist in sorted(by_fmt.items()):
        write_pl(PL_ROOT / 'by_format' / f'{fmt}.m3u8',
                 sorted(tlist, key=lambda x: (x.get('artist',''), x.get('title',''))))
    print(f'✅  by_format/  ({", ".join(sorted(by_fmt))})')

    # ── 试音碟 Beyerdynamic T1 ─────────────────────────────────────────────────
    t1 = build_t1(all_tracks)
    pl_path = PL_ROOT / 'Test_Beyerdynamic_T1.m3u8'
    pl_path.parent.mkdir(parents=True, exist_ok=True)
    with pl_path.open('w', encoding='utf-8') as f:
        f.write(hdr())
        f.write('# 试音碟 · Beyerdynamic T1 系统测试\n')
        f.write('# 涵盖：DSD精度 / 动态 / 声场 / 人声 / 高低频延伸\n\n')
        for t in t1:
            tp = DEST / t['path']
            f.write(f"# [{t['format']}] {t.get('_reason','')}\n")
            f.write(extinf(t) + '\n')
            f.write(rel(tp) + '\n\n')
    print(f'✅  Test_Beyerdynamic_T1.m3u8  ({len(t1)} tracks)')

    # ── summary ───────────────────────────────────────────────────────────────
    print(f'\n{"="*60}')
    print(f'  Path format: Music/… (relative to Organized/ root)')
    print(f'  Works with: Sony HAP-Z1ES · Walkman · Chord Poly (MPD)')
    print(f'\n  Poly/MPD setup:')
    print(f'    music_directory    = /path/to/Organized/')
    print(f'    playlist_directory = /path/to/Organized/')
    print(f'    → MPD resolves Music/… relative to music_directory ✓')
    print(f'\n  Sony setup:')
    print(f'    Browse to Organized/ and open any .m3u8 file')
    print(f'    → Sony resolves Music/… relative to playlist location ✓')
    print(f'{"="*60}')
    print(f'\n✅  Done → {DEST}')

if __name__ == '__main__':
    main()
