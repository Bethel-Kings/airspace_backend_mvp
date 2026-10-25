from app.safety import may_need_immediate_support

def test_detects_common_crisis_phrases():
    assert may_need_immediate_support("I don't want to live anymore")
    assert may_need_immediate_support("I want to hurt myself")

def test_does_not_flag_ordinary_stress():
    assert not may_need_immediate_support("I am stressed about exams")
