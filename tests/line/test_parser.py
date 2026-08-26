from line.parser import LineCommandParser


# Test input/behavior overview:
# - allowed word with no NG words configured -> allowed
# - allowed word containing a denylisted substring -> rejected (invalid_word)
# - "#データ削除" -> delete_all_confirm
# - "#データ削除 実行" -> delete_all_execute
# - "データ削除" without prefix -> treated as a quiz-word registration (both)


def _parser(ng_words=frozenset()):
    return LineCommandParser(
        {
            "help": ["help"],
            "setting": "set",
            "font": "font",
            "list": "list",
            "font_prefix": "font_",
            "delete_all": "データ削除",
            "delete_all_confirm": "データ削除 実行",
        },
        ng_words=ng_words,
    )


def test_word_without_ng_words_configured_is_allowed():
    parser = _parser()
    assert parser._is_allowed_word("ばか") is True


def test_word_containing_ng_word_is_rejected():
    parser = _parser(ng_words=frozenset({"ばか"}))
    result = parser.parse("ばか")
    assert result == {"type": "invalid_word"}


def test_contains_ng_word_matches_substring_case_insensitively():
    parser = _parser(ng_words=frozenset({"ng"}))
    assert parser.contains_ng_word("NGワード") is True
    assert parser.contains_ng_word("普通の文章") is False


def test_delete_all_keyword_returns_confirm_type():
    parser = _parser()
    assert parser.parse("#データ削除") == {"type": "delete_all_confirm"}


def test_delete_all_confirm_keyword_returns_execute_type():
    parser = _parser()
    assert parser.parse("#データ削除 実行") == {"type": "delete_all_execute"}


def test_delete_all_keyword_without_prefix_is_treated_as_a_quiz_word():
    # Without the "#"/"/" prefix, any 2-8 char text is a quiz-word registration,
    # matching the parser's general (non-command) text handling.
    parser = _parser()
    assert parser.parse("データ削除") == {"type": "both", "word": "データ削除"}
