from app.config import settings

STYLE_INSTRUCTIONS = {
    "gentle": "Use a gentle, non-judgmental tone. Reflect feelings without assuming causes.",
    "practical": "Offer one or two small, optional next steps. Do not overwhelm the user.",
    "reflective": "Offer thoughtful questions that help the user name feelings and needs.",
}

async def generate_reflection(text: str, style: str) -> str:
    """Uses OpenAI when configured; otherwise returns a transparent deterministic fallback."""
    if not settings.openai_api_key:
        return (
            "A possible reframe: what you're feeling is information about what matters to you, "
            "not proof that you have failed. You do not have to solve everything at once. "
            "Try naming the feeling, the need underneath it, and one small thing within your control."
        )
    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=settings.openai_api_key)
        response = await client.chat.completions.create(
            model=settings.openai_model,
            temperature=0.5,
            max_tokens=350,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are AirSpace, a supportive emotional reflection assistant, not a therapist. "
                        "Be concise, validating, non-diagnostic, and do not claim certainty about the user's "
                        "feelings. Never shame, pressure, or tell the user what they must do. Do not provide "
                        "medical diagnoses. If imminent danger is mentioned, prioritize immediate human support. "
                        + STYLE_INSTRUCTIONS[style]
                    ),
                },
                {"role": "user", "content": text},
            ],
        )
        return (response.choices[0].message.content or "").strip() or (
            "Take a moment to identify what feels most important in what you shared."
        )
    except Exception:
        # Avoid exposing provider errors or user content in logs/responses.
        return (
            "I couldn't generate a personalized reflection just now. You could ask yourself: "
            "What am I feeling? What do I need right now? What is one manageable next step?"
        )
