# Airspace - MVP backend

FastAPI backend for **AirSpace: Vent and Decompress**. Includes account registration/login, transient venting, optional AI-assisted reflection, emotional check-ins, and deletion controls

## Run locally (Windows PowerShell)

Requires Python 3.11+.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/docs` for interactive API documentation.

## Tests

```powershell
pytest -q
```

The API tests use an isolated in-memory SQLite database. They do not replace a deployment smoke test against the PostgreSQL database configured on Render.

## Environment variables

- `ENVIRONMENT`: `development` locally, `production` on Render.
- `DATABASE_URL`: SQLite locally; PostgreSQL in production.
- `JWT_SECRET`: a unique random value in production. Production settings reject the placeholder or a secret shorter than 32 characters.
- `CORS_ORIGINS`: comma-separated exact frontend origins.
- `DEEPSEEK_API_KEY`: optional. When configured, reframe, chat and voice replies require explicit consent before the text is sent to DeepSeek.
- `DEEPSEEK_MODEL`: default `deepseek-v4-flash` (`deepseek-chat`/`deepseek-reasoner` were retired 2026-07-24). Thinking mode is always disabled.
- `DEEPSEEK_BASE_URL`: default `https://api.deepseek.com`.
- `OPENAI_API_KEY`: optional, **speech-to-text only** (DeepSeek has no audio API). Without it, `/vent/voice` returns `unavailable` and the client falls back to on-device recognition.
- `OPENAI_TRANSCRIBE_MODEL`: speech-to-text model used by voice vent (default `gpt-4o-mini-transcribe`; `whisper-1` also works).
- `MAX_AUDIO_BYTES`: upload cap for voice vent (default 10 MB).
- `CRISIS_RESOURCES`: optional, reviewed local support contacts (JSON array of `CrisisResource` objects or plain text) included in safety notices and returned by `/api/v1/crisis-resources`.

`JWT_SECRET` has no default. In development an ephemeral one is generated (tokens reset on restart). Production refuses to start without a strong one.

## Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/health` | Health check |
| GET | `/api/v1/crisis-resources` | Public directory of crisis intervention and support hotlines |
| POST | `/api/v1/auth/register` | Create account |
| POST | `/api/v1/auth/login` | Obtain bearer token |
| GET | `/api/v1/me` | Current user profile (token validation) |
| POST | `/api/v1/vent` | Return acknowledgement/prompts; does not persist the submitted text |
| POST | `/api/v1/reframe` | Generic fallback or consent-based AI reflection |
| POST | `/api/v1/checkins` | Save emotional check-in |
| GET | `/api/v1/checkins` | List the authenticated user's check-ins |
| PATCH | `/api/v1/checkins/{id}` | Update after_score / emotion / note on owned check-in |
| DELETE | `/api/v1/checkins/{id}` | Delete an owned check-in |
| DELETE | `/api/v1/account` | Delete account and associated check-ins |

When the AI key is configured, the frontend must explain that the text will be processed by an external AI provider and set `consent_to_ai_processing` to `true` only after the user opts in. Without consent, the API does not send the text to the provider. Without an API key, the API returns a generic fallback that does not use the submitted text.

## Voice vent and chat

Both endpoints follow the same rules as `/reframe`: crisis phrases skip the AI entirely, the user must opt in (`consent_to_ai_processing`), and only paid calls are rate limited (voice 20/hour, chat 60/hour per user).

- **Voice:** `multipart/form-data` with `audio` (webm, ogg, mp4/m4a, mp3, wav, flac; max 10 MB), `consent_to_ai_processing`, optional `reflect` (also return an AI reply), `prompt_style`, and `language` (ISO-639-1 hint). The transcript is screened before any reply is generated. Audio is held in memory only.
- **Chat:** send `{"messages": [{"role": "user"|"assistant", "content": "..."}], "prompt_style", "consent_to_ai_processing"}`. The last message must be from the user. Every user turn is screened, so one flagged message ends AI replies until the client sends a fresh conversation. `system` messages are rejected.
- Without an API key, voice returns `ai_status: "unavailable"` (use on-device speech recognition and `POST /vent` instead) and chat returns the generic fallback prompt.

## Render

`render.yaml` defines the web service but does not create a PostgreSQL database. Create a managed PostgreSQL database and configure `DATABASE_URL` and `CORS_ORIGINS` in Render. The PostgreSQL driver is included and `postgres://` URLs are normalized to the psycopg SQLAlchemy dialect.

## Privacy and safety limitations

This is an MVP scaffold, not a clinical tool or a security audit. The phrase detector is a basic routing aid; it can miss risk or flag context incorrectly and cannot determine whether someone is safe. Establish a reviewed safety protocol and appropriate human-support guidance before inviting real users.

Raw vent text is not persisted by this API. If AI reflection is enabled and the user opts in, the submitted text is sent to DeepSeek for processing (and, for voice vent, the audio is sent to OpenAI for transcription). Check-in notes are stored and may contain sensitive personal information. Do not describe the service as guaranteed confidential, therapy, or an emergency service.

Rate limiting is in-memory and per-process (fine for one Render instance; move to Redis if you scale out). Before production, add account recovery, email verification where appropriate, Alembic migrations, backups, monitoring that does not log sensitive content, and a review of applicable privacy obligations.
