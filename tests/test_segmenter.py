from lila.audio import FRAME_MS, UtteranceSegmenter

QUIET = b"\x00" * 960
LOUD = b"\x01" * 960


def feed(seg, pattern):
    events = []
    for voiced in pattern:
        events += seg.process(LOUD if voiced else QUIET, voiced)
    return events


def test_normal_utterance_gives_speech_pause_then_utterance_with_preroll():
    seg = UtteranceSegmenter()
    events = feed(seg, [False] * 3 + [True] * 20 + [False] * 30)
    assert [e.kind for e in events] == ["speech", "pause", "utterance"]
    _, pause, utterance = events
    assert utterance.audio.startswith(QUIET * 3 + LOUD)
    # 3 pre-roll frames + 20 voiced + 700 ms of silence (24 frames of 30 ms)
    assert len(utterance.audio) == (3 + 20 + 24) * 960
    # The pause comes after 400 ms (14 frames) of silence; nothing was said after it.
    assert len(pause.audio) == (3 + 20 + 14) * 960
    assert utterance.early and utterance.audio.startswith(pause.audio)


def test_talking_again_after_a_pause_gives_a_new_pause():
    events = feed(UtteranceSegmenter(), [True] * 20 + [False] * 15 + [True] * 5 + [False] * 30)
    assert [e.kind for e in events] == ["speech", "pause", "pause", "utterance"]
    assert len(events[2].audio) > len(events[1].audio)


def test_one_short_word_is_an_utterance():
    # "yes": about 240 ms of voice, used to be thrown away as too short
    events = feed(UtteranceSegmenter(), [False] * 5 + [True] * 8 + [False] * 30)
    assert [e.kind for e in events] == ["speech", "pause", "utterance"]
    assert LOUD * 8 in events[2].audio


def test_a_click_never_starts():
    assert feed(UtteranceSegmenter(), [True] * 3 + [False] * 40) == []


def test_scattered_noise_never_starts():
    assert feed(UtteranceSegmenter(), [True, False] * 200) == []


def test_max_length_ends_at_30_seconds():
    seg = UtteranceSegmenter()
    events = feed(seg, [True] * (30_000 // FRAME_MS + 3))
    assert [e.kind for e in events] == ["speech", "utterance"]
    assert len(events[1].audio) == 30_000 // FRAME_MS * 960
    assert not events[1].early
