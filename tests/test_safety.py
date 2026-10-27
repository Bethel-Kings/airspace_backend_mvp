import json
from app.safety import (
    DEFAULT_CRISIS_RESOURCES,
    get_crisis_message,
    get_crisis_resources,
    may_need_immediate_support,
)
from app.config import settings


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


def test_default_crisis_resources():
    resources = get_crisis_resources()
    assert len(resources) == 5
    names = [r.name for r in resources]
    assert "MANI (Mentally Aware Nigeria Initiative)" in names
    assert "SURPIN (Suicide Research & Prevention Initiative)" in names
    assert "Safe Place Nigeria (She Writes Woman)" in names
    assert "Lagos Lifeline" in names
    assert "Emergency Services" in names


def test_crisis_message_contains_support_contacts():
    msg = get_crisis_message()
    assert "Your safety matters" in msg
    assert "MANI" in msg
    assert "08091116264" in msg
    assert "SURPIN" in msg
    assert "112" in msg


def test_crisis_resources_custom_json(monkeypatch):
    custom = [
        {"name": "Custom Helpline", "phone": "12345", "hours": "24/7", "description": "Help"}
    ]
    monkeypatch.setattr(settings, "crisis_resources", json.dumps(custom))
    resources = get_crisis_resources()
    assert len(resources) == 1
    assert resources[0].name == "Custom Helpline"
    assert resources[0].phone == "12345"
    assert "Custom Helpline" in get_crisis_message()


def test_crisis_resources_plain_text_fallback(monkeypatch):
    monkeypatch.setattr(settings, "crisis_resources", "Emergency hotline: 999")
    msg = get_crisis_message()
    assert "Emergency hotline: 999" in msg
