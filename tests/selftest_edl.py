"""EDL for scripts/selftest.sh (the 動作テスト / setup check): a ~10 s demo cut of a synthetic 14 s source
(colour bars + a sine tone). Two neutral speakers, a hook title, a Q header, a pop, name plates, an end card.
Times are seconds of the synthetic source. No real person is named anywhere."""

CLIPS = [
    (0.5, 3.5, 'A', '動作テストの動画です||テロップが出ていればOK'),
    (4.0, 7.0, 'B', '質問の字幕です\n二行目もあります'),
    (7.5, 10.5, 'A', '答えの字幕です||最後にエンドカード'),
]
SHARE_FROM = 1e9                  # never screen share
SHARE_BLUR = (0, 86, 1440, 72)
SECTIONS = [(4.0, 'Q1', '動作テストの質問')]
POPS = [(8.0, '動作テスト成功!!', 'gold', 1.8)]
PLATES = [(0.6, 'A', 2.0), (4.1, 'B', 2.0)]
HOOK_TITLE_END = 3.5              # title banner over the first clip
END_CARD_FROM = 9.4               # end card fades in here and holds on the tail
TAIL = 1.0

SPEAKERS = {'A': ('話者A', '#0A6CFF', '#0047B3'), 'B': ('話者B', '#FF3D7F', '#C2185B')}
PLATE_TEXT = {'A': ('サンプル株式会社', '話者A'), 'B': ('聞き手', '話者B')}
TITLE = ('動作テスト', 'この動画が見られたら準備完了')
END_CARD = ('準備完了！', '話者A（サンプル株式会社）', '聞き手  話者B')
