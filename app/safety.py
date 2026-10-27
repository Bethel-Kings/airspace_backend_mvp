import json
import re
import unicodedata
from typing import Any

from app.config import settings
from app.schemas import CrisisResource

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

DEFAULT_CRISIS_RESOURCES: list[dict[str, Any]] = [
    {
        "name": "MANI (Mentally Aware Nigeria Initiative)",
        "phone": "08091116264",
        "alt_phone": "08111680686",
        "hours": "24/7",
        "description": "Free, confidential emotional support for anxiety, depression, and suicidal thoughts.",
        "url": "https://mentallyaware.org",
    },
    {
        "name": "SURPIN (Suicide Research & Prevention Initiative)",
        "phone": "08000787746",
        "alt_phone": "09034400009",
        "hours": "24/7",
        "description": "Nationwide crisis intervention; counsellors speak major Nigerian languages.",
        "url": "https://surpin.org",
    },
    {
        "name": "Safe Place Nigeria (She Writes Woman)",
        "phone": "08008002000",
        "hours": "24/7",
        "description": "National toll-free crisis line with free tele-therapy referrals.",
        "url": "https://shewriteswoman.org",
    },
    {
        "name": "Lagos Lifeline",
        "phone": "07000006463",
        "hours": "24/7",
        "description": "Lagos State line connecting callers to psychiatric professionals.",
        "url": "https://lagosstate.gov.ng",
    },
    {
        "name": "Emergency Services",
        "phone": "112",
        "hours": "24/7",
        "description": "National emergency number. In Lagos, dial 767.",
        "url": "",
    },
]


def get_crisis_resources() -> list[CrisisResource]:
    raw = settings.crisis_resources.strip()
    if raw:
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                return [CrisisResource.model_validate(item) for item in data]
        except Exception:
            pass
    return [CrisisResource.model_validate(item) for item in DEFAULT_CRISIS_RESOURCES]


def format_crisis_resources(resources: list[CrisisResource]) -> str:
    lines = []
    for r in resources:
        contact = r.phone
        if r.alt_phone:
            contact = f"{contact} / {r.alt_phone}"
        if r.hours:
            contact = f"{contact} ({r.hours})"

        details = [r.name, contact]
        if r.description:
            details.append(r.description)
        if r.url:
            details.append(r.url)
        lines.append("• " + " - ".join(d for d in details if d))
    return "\n".join(lines)


def get_crisis_message() -> str:
    raw = settings.crisis_resources.strip()
    if raw:
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                resources = [CrisisResource.model_validate(item) for item in data]
                resources_text = format_crisis_resources(resources)
                return f"{CRISIS_MESSAGE}\n\nCrisis support resources:\n{resources_text}"
        except Exception:
            return f"{CRISIS_MESSAGE} {raw}"

    resources = [CrisisResource.model_validate(item) for item in DEFAULT_CRISIS_RESOURCES]
    resources_text = format_crisis_resources(resources)
    return f"{CRISIS_MESSAGE}\n\nCrisis support resources:\n{resources_text}"


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).translate(_APOSTROPHES).lower()
    return re.sub(r"\s+", " ", text)


def may_need_immediate_support(text: str | None) -> bool:
    if not text:
        return False
    normalized = normalize(text)
    return any(p.search(normalized) for p in _COMPILED)
