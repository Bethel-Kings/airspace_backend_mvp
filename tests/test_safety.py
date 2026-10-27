from app.safety import may_need_immediate_support


def test_detects_common_crisis_phrases():
    assert may_need_immediate_support("I don't want to live anymore")
    assert may_need_immediate_support("I want to hurt myself")


def test_does_not_flag_ordinary_stress():
    assert not may_need_immediate_support("I am stressed about exams")


def test_detector_normalizes_case_and_whitespace():
    assert may_need_immediate_support("I DO NOT WANT TO LIVE")


def test_detects_curly_apostrophe_from_phone_keyboards():
    assert may_need_immediate_support("I don\u2019t want to live")
    assert may_need_immediate_support("i dont want to live")


def test_detects_wider_phrasing():
    for text in [
        "I want to die", "I keep cutting myself", "I am killing myself",
        "I wish I was dead", "everyone would be better off dead", "life isn\u2019t worth living",
        "I'm thinking about suicide",
    ]:
        assert may_need_immediate_support(text), text


def test_common_idioms_are_not_flagged():
    for text in ["This deadline is killing me", "I could die of embarrassment", "I want to live abroad"]:
        assert not may_need_immediate_support(text), text


def test_none_or_empty_is_safe():
    assert not may_need_immediate_support(None)
    assert not may_need_immediate_support("")
