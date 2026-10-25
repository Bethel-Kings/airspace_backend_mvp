import re

# Lightweight routing only—not a diagnosis or a substitute for professional assessment.
CRISIS_PATTERNS = [
    r"\b(kill myself|suicide|suicidal|end my life|don't want to live|do not want to live)\b",
    r"\b(hurt myself|harm myself|self[- ]harm|cut myself|overdose)\b",
]

def may_need_immediate_support(text: str) -> bool:
    normalized = re.sub(r"\s+", " ", text.lower())
    return any(re.search(pattern, normalized) for pattern in CRISIS_PATTERNS)

CRISIS_MESSAGE = (
    "Your safety matters. AirSpace is not an emergency or crisis service. "
    "If you may act on thoughts of harming yourself, contact local emergency services now "
    "or go to the nearest emergency department. If possible, tell a trusted person nearby "
    "and ask them to stay with you while you get support."
)
