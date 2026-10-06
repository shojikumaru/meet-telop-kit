"""EDL template (edit decision list + telop cues) for one ad cut. Copy it to work/edl.py and replace EVERYTHING.

    cp templates/edl_template.py work/edl.py

All times are SECONDS IN THE SEGMENT you transcribed (= the times in work/seg.json, i.e. recording time minus the
--from you gave transcribe.sh; render with build_base.py --source-offset <that FROM>). The times below are made up
(a 50 s segment) so the file renders as-is against a synthetic test source; none of them mean anything.

Names, titles, companies and the end card text come from the user's request. Never invent them and never reuse
names from another job: if they are missing, ask the user. The placeholders 話者A / 話者B are only placeholders.

Speaker keys ('A', 'B', ...) are free-form short strings; use the same key in CLIPS, SPEAKERS, PLATE_TEXT, PLATES.
A '||' inside a subtitle splits it into consecutive pages (time shared by character count); '\n' is a line break.
Keep each page <= 2 lines of ~20 full-width characters. Subtitles are hand-edited readable Japanese, not raw ASR.
"""

# ---------------------------------------------------------------- cut list (required)
# (start, end, speaker key, subtitle) in OUTPUT order. Pick start/end from studio/phrases.py so cuts land in silences.
CLIPS = [
    # --- hook: the most surprising 10-15 s of the talk, placed first ---
    (40.00, 44.00, 'B', 'フックになる一言をここに||二枚目のページ'),
    # --- Q1 ---
    (2.00, 5.00, 'A', '一つ目の質問をここに\n二行まで'),
    (5.50, 12.00, 'B', '答えの字幕をここに||続きのページ'),
    # --- Q2 ---
    (14.00, 17.00, 'A', '二つ目の質問をここに'),
    (17.50, 26.00, 'B', '数字が出てくる答え||比べる話が続く'),
    # --- Q3 ---
    (28.00, 30.00, 'A', '三つ目の質問をここに'),
    (30.50, 38.00, 'B', '場所やお金の話||最後のまとめ'),
    # --- closing (the end card fades in over it) ---
    (46.00, 50.00, 'B', 'しめくくりの一言'),
]

# ---------------------------------------------------------------- layout (required)
# From SHARE_FROM on the recording shows a screen share: content on the left 1440 px, the browser bar at SHARE_BLUR
# (x, y, w, h in 1920x1080) is blurred, telops centre on x=720. 1e9 = never.
SHARE_FROM = 1e9
SHARE_BLUR = (0, 86, 1440, 72)
# A recording that switches between face view and screen share: list the share spans instead (overrides SHARE_FROM).
# SHARE_RANGES = [(28.0, 38.0)]
TAIL = 2.0              # seconds of freeze after the last clip (the end card holds on it)
# TIMING: leave it out (= 'anchored': telops follow the measured cut starts).

# ---------------------------------------------------------------- people (required; from the user, never invented)
# speaker key -> (subtitle chip name, colour, dark colour)
SPEAKERS = {
    'A': ('話者A', '#FF3D7F', '#C2185B'),   # e.g. the interviewer
    'B': ('話者B', '#0A6CFF', '#0047B3'),   # e.g. the guest
}
# name plate: speaker key -> (affiliation / title line, full name)
PLATE_TEXT = {
    'A': ('聞き手の所属・肩書き', '話者A'),
    'B': ('ゲストの会社名 役職', '話者B'),
}
# (time, speaker key, seconds on screen): when each person first speaks
PLATES = [(2.2, 'A', 3.0), (5.7, 'B', 3.0)]

# ---------------------------------------------------------------- hook title + end card
TITLE = ('金色の大見出し', 'リボンの一行（動画の売り文句）')
HOOK_TITLE_END = 44.0   # the title banner is shown from the start until this time (end of the hook clip)
END_CARD = ('続きは 本編で！', 'ゲストの会社名 役職  話者B', '聞き手  話者A')   # (pop line, line 1, line 2)
END_CARD_FROM = 48.0    # the end card fades in here (inside the last clip) and holds on the tail

# ---------------------------------------------------------------- section headers + pops
# (time, label, short question title) at each question start
SECTIONS = [(2.0, 'Q1', '質問1の短いタイトル'), (14.0, 'Q2', '質問2の短いタイトル'), (28.0, 'Q3', '質問3の短いタイトル')]
# (time, text, 'gold' | 'red' | 'blue', seconds) for numbers / punchlines, about one per 20-30 s
POPS = [(41.0, '驚きの数字!!', 'red', 2.4), (9.0, 'ポイント', 'gold', 2.0), (15.5, '補足', 'blue', 1.5)]

# ---------------------------------------------------------------- optional panels
# Delete a whole block to skip that panel. A panel you keep needs ALL its keys (a missing *_END makes it never
# appear; a missing key or text crashes the render). Reveal times = when the speaker says the item.

# logo chips: (time, label, colour); all fade out at CHIPS_END
CHIPS = [(6.0, '項目A', '#D97757'), (7.5, '項目B', '#10A37F'), (9.5, '項目C', '#4285F4')]
CHIPS_END = 11.5

# log-scale bars: (time, label, value text, value, highlight); TIERS_LOG_RANGE = log10 of the left / right edge
TIERS = [(18.5, '少ない人', '1万', 1e4, False), (19.5, 'ふつう', '100万', 1e6, False), (20.5, 'ゲスト', '1億', 1e8, True)]
TIERS_START, TIERS_END = 18.0, 21.5
TIERS_BADGE = 21.0                      # red badge pop time (leave out for no badge)
TIERS_TITLE = '対数の棒グラフのタイトル'
TIERS_NOTE = '※横軸は対数スケール（1目盛り＝10倍）'
TIERS_BADGE_TEXT = 'バッジの文字!!'
TIERS_LOG_RANGE = (3, 9)

# linear bars: same row shape as TIERS; REPOS_MAX = the value that fills a whole bar
REPOS = [(22.5, 'ふつう', '2本', 2, False), (24.0, 'ゲスト', '10本', 10, True)]
REPOS_END = 25.5
REPOS_TITLE = '線形の棒グラフのタイトル'
REPOS_MAX = 10

# three cards: SITES = (time, key) for key 'server' (panel start), every SITES_CARDS key, and 'center' (pop)
# SITES_CARDS = (key, line 1, line 2); the key also picks the icon: server / desktop / anything else = laptop
SITES = [(31.0, 'server'), (31.8, 'desktop'), (32.6, 'laptop'), (33.3, 'center')]
SITES_END = 34.0
SITES_CARDS = [('server', '場所1', 'サーバー'), ('desktop', '場所2', 'デスクトップ'), ('laptop', '場所3', 'ノートPC')]
SITES_CENTER_TEXT = '真ん中のポップ'

# money panel: MONEY = (time, key) for key 'api' (panel start), every MONEY_ROWS key, and 'actual' (pop)
# MONEY_ROWS = (key, text, kind); kind 'strike' is struck through at the 'actual' cue, None = plain row
MONEY = [(34.5, 'api'), (35.3, 'price'), (36.0, 'trick'), (37.0, 'actual')]
MONEY_END = 37.8
MONEY_ROWS = [('api', 'ふつうに払うと', None), ('price', '月 ○○万円', 'strike'), ('trick', '工夫すると', None)]
MONEY_ACTUAL_TEXT = '実際は 月 △△万円'

# ---------------------------------------------------------------- preview stills
# segment times worth checking as stills (preview.py also adds 1.5 s and the last second of the output)
PREVIEW_AT = [42.0, 9.5, 20.8, 24.2, 33.5, 37.2, 49.0]
