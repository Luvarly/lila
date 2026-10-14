from lila.textfilter import CODE_NOTICE, SpeechFilter


def run(*pieces: str, expressive: bool = False) -> list[str]:
    f = SpeechFilter(expressive)
    out = []
    for p in pieces:
        out += f.feed(p)
    return out + f.flush()


def test_releases_at_sentence_end_while_streaming():
    f = SpeechFilter()
    assert f.feed("Hello there") == []
    assert f.feed(". How are") == ["Hello there. "]
    assert f.feed(" you? I am") == ["How are you? "]
    assert f.flush() == ["I am "]


def test_inline_markdown():
    assert run("This is **bold**, *italic*, __strong__ and ~~gone~~ with `code`.\n") == [
        "This is bold, italic, strong and gone with code. "
    ]


def test_urls_links_and_snake_case():
    assert run("See https://example.com/a_b. Then [the docs](https://x.y) for my_var_name.\n") == [
        "See a link. Then the docs for my var name. "
    ]


def test_headings_lists_quotes_and_rules():
    text = "# Title\n- one\n* two\n+ three\n1. four\n2) five\n> quoted\n---\n***\n"
    assert run(text) == ["Title ", "one ", "two ", "three ", "four ", "five ", "quoted "]


def test_code_fence_split_across_chunks():
    out = run(
        "Here:\n``", "`python\nprint(1)\n", "x = 2. y = 3\n``", "`\nDone.", "\n```\nmore\n```\n"
    )
    assert out == ["Here: ", CODE_NOTICE, "Done. "]


def test_tables():
    assert run("| Name | Age |\n|---|:--:|\n| Ann | 30 |\n") == ["Name, Age ", "Ann, 30 "]


def test_long_text_without_sentence_end_is_cut_at_a_space():
    f = SpeechFilter()
    out = f.feed("word " * 40)
    assert len(out) == 1 and out[0].endswith("word ")
    assert len(out[0]) <= 200
    assert f.flush() == []


def test_emoji_removed():
    assert run("Great job 🎉✨ really, thanks 👍\n") == ["Great job really, thanks "]


def test_bracket_cues_removed_by_default():
    assert run("[laughing] That is funny. [soft tone] Okay.", "\n") == [
        "That is funny. ",
        "Okay. ",
    ]


def test_bracket_cues_kept_in_expressive_mode():
    assert run("[laughing] That is funny.\n", expressive=True) == ["[laughing] That is funny. "]


def test_links_become_text_even_in_expressive_mode():
    assert run("Read [the guide](https://x.y/guide) now.\n", expressive=True) == [
        "Read the guide now. "
    ]
