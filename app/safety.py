import re
import unicodedata

from app.config import settings

# Prototype-only routing. This is not a clinical risk assessment and cannot establish safety.
# It is a phrase match: it WILL miss real risk and may flag harmless context.
CRISIS_PATTERNS = [
    r"\b(kill(?:ing)? myself|suicid(?:e|al)|end(?:ing)? my (?:own )?life|take my own life)\b",
    r"\b(?:i )?do(?:n't| not|nt) want to (?:live|be alive|be here)\b",
    r"\b(want to die|wanna die|wish i (?:was|were) dead|better off dead|no reason to live)\b",
    r"\b(?:life )?(?:is not|isn't|isnt) worth living\b",
    r"\b(?:hurt|harm)(?:ing)? myself\b",
    r"\b(?:self[- ]?harm|cut(?:ting)? myself|overdos(?:e|ing))\b",
]
_COMPILED = [re.compile(p) for p in CRISIS_PATTERNS]
_APOSTROPHES = str.maketrans({"\u2019": "'", "\u2018": "'", "\u02bc": "'", "\u00b4": "'", "`": "'"})

CRISIS_MESSAGE = (
    "Your safety matters. AirSpace is not an emergency or crisis service. "
    "If you may act on thoughts of harming yourself, contact local emergency services "
    "or go to the nearest emergency department now. If possible, tell a trusted person "
    "nearby and ask them to stay with you while you get support."
)


def get_crisis_message() -> str:
    extra = settings.crisis_resources.strip()
    return f"{CRISIS_MESSAGE} {extra}" if extra else CRISIS_MESSAGE


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).translate(_APOSTROPHES).lower()
    return re.sub(r"\s+", " ", text)


def may_need_immediate_support(text: str | None) -> bool:
    if not text:
        return False
    normalized = normalize(text)
    return any(p.search(normalized) for p in _COMPILED)
