"""EDL for the anchored-timing check in tests/smoke.sh (build_base only): seven short NON-contiguous cuts whose
lengths are not whole frames, so every segment ends a little after its nominal end (max(video, audio)) and the
drift adds up. Screen share from the 4th clip on. Times are seconds of the 12 s synthetic source."""

CLIPS = [
    (0.50, 1.237, 'J', 'a'),
    (2.00, 2.737, 'I', 'b'),
    (3.50, 4.237, 'J', 'c'),
    (5.00, 5.737, 'I', 'd'),
    (6.50, 7.237, 'J', 'e'),
    (8.00, 8.737, 'I', 'f'),
    (9.50, 10.237, 'J', 'g'),
]
SHARE_FROM = 6.0
SHARE_BLUR = (0, 86, 1440, 72)
TAIL = 0.5
