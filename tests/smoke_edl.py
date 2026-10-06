"""Tiny EDL for tests/smoke.sh: every cue type, out-of-order clips (two input runs), one contiguous merge,
screen-share blur window. Times are seconds of the 12 s synthetic source."""

CLIPS = [
    (8.0, 10.0, 'J', 'フックの字幕||二枚目のページ'),
    (1.0, 3.0, 'I', '質問の字幕\n二行目'),
    (3.05, 5.0, 'J', '連続クリップ（結合される）'),
]
SHARE_FROM = 4.0
SHARE_BLUR = (0, 86, 1440, 72)
SECTIONS = [(1.0, 'Q1', 'スモークテスト')]
POPS = [(8.3, 'ポップ!!', 'red', 1.0), (1.5, '金色テロップ', 'gold', 1.0), (3.3, '青テロップ', 'blue', 0.8)]
CHIPS = [(1.1, 'Chip A', '#D97757'), (1.4, 'Chip B', '#10A37F')]
CHIPS_END = 2.2
TIERS = [(2.3, 'ライト層', '1万', 1e4, False), (2.6, '本人', '1億', 1e8, True)]
TIERS_START, TIERS_END = 2.2, 3.0
TIERS_BADGE = 2.8
SITES = [(3.1, 'server'), (3.3, 'desktop'), (3.5, 'laptop'), (3.7, 'center')]
SITES_END = 3.9
REPOS = [(4.0, 'ふつう', '1本', 1, False), (4.2, '本人', '10本', 10, True)]
REPOS_END = 4.4
MONEY = [(9.0, 'api'), (9.2, 'api_yen'), (9.4, 'harness'), (9.6, 'subsc'), (9.8, 'actual')]
MONEY_END = 10.0
PLATES = [(1.0, 'I', 1.5), (3.1, 'J', 1.5)]
HOOK_TITLE_END = 10.0
END_CARD_FROM = 3.4
TAIL = 1.0

SPEAKERS = {'J': ('話者J', '#0A6CFF', '#0047B3'), 'I': ('話者I', '#FF3D7F', '#C2185B')}
PLATE_TEXT = {'J': ('サンプル株式会社 役職', '話者A'), 'I': ('聞き手', '話者B')}
TITLE = ('スモークテスト見出し', 'リボンのテキスト')
TIERS_TITLE = '棒グラフ（対数）'
TIERS_NOTE = '※注記'
TIERS_BADGE_TEXT = 'バッジ!!'
TIERS_LOG_RANGE = (4, 10.7)
SITES_CARDS = [('server', '場所A', 'サーバー'), ('desktop', '場所B', 'デスクトップ'), ('laptop', '場所C', 'ノート')]
SITES_CENTER_TEXT = '中央のポップ'
REPOS_TITLE = '棒グラフ（線形）'
REPOS_MAX = 10
MONEY_ROWS = [('api', '一行目', None), ('api_yen', '取り消し線の行', 'strike'), ('harness', '三行目', None)]
MONEY_ACTUAL_TEXT = '実際は'
END_CARD = ('エンドカード', '一行目', '二行目')
