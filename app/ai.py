from dataclasses import dataclass
from app.config import settings

STYLE_INSTRUCTIONS = {
    "gentle": "Use a gentle, non-judgmental tone. Reflect feelings without assuming causes.",
    "practical": "Offer one or two small, optional next steps. Do not overwhelm the user.",
    "reflective": "Offer thoughtful questions that help the user name feelings and needs.",
}
GENERIC_FALLBACK = "You could pause and ask yourself: What am I feeling right now? What do I need? What is one manageable next step?"


@dataclass
class ReflectionResult:
    text: str
    status: str  # success, fallback, or unavailable


async def generate_reflection(text: str, style: str) -> ReflectionResult:
    if not settings.openai_api_key:
        return ReflectionResult(GENERIC_FALLBACK, "unavailable")
    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=settings.openai_api_key, timeout=15.0, max_retries=1)
        response = await client.chat.completions.create(
            model=settings.openai_model,
            temperature=0.5,
            max_tokens=350,
            messages=[
                {"role": "system", "content": (
                    "You are AirSpace, a supportive emotional reflection assistant, not a therapist. "
                    "Be concise, validating, non-diagnostic, and do not claim certainty about the user's feelings. "
                    "Never shame, pressure, or tell the user what they must do. Do not provide medical diagnoses. "
                    "If imminent danger is mentioned, prioritize immediate human support. " + STYLE_INSTRUCTIONS[style]
                )},
                {"role": "user", "content": text},
            ],
        )
        content = (response.choices[0].message.content or "").strip()
        return ReflectionResult(content, "success") if content else ReflectionResult(GENERIC_FALLBACK, "fallback")
    except Exception:
        # Never log submitted emotional text or expose provider errors to the client.
        return ReflectionResult(GENERIC_FALLBACK, "fallback")
