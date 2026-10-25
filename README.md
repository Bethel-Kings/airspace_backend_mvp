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
- `OPENAI_API_KEY`: optional. When configured, the reframe endpoint requires explicit consent before sending the text to OpenAI.
- `OPENAI_MODEL`: a model available to your API account.

## Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/health` | Health check |
| POST | `/api/v1/auth/register` | Create account |
| POST | `/api/v1/auth/login` | Obtain bearer token |
| POST | `/api/v1/vent` | Return acknowledgement/prompts; does not persist the submitted text |
| POST | `/api/v1/reframe` | Generic fallback or consent-based AI reflection |
| POST | `/api/v1/checkins` | Save emotional check-in |
| GET | `/api/v1/checkins` | List the authenticated user's check-ins |
| DELETE | `/api/v1/checkins/{id}` | Delete an owned check-in |
| DELETE | `/api/v1/account` | Delete account and associated check-ins |

When the AI key is configured, the frontend must explain that the text will be processed by an external AI provider and set `consent_to_ai_processing` to `true` only after the user opts in. Without consent, the API does not send the text to the provider. Without an API key, the API returns a generic fallback that does not use the submitted text.

## Render

`render.yaml` defines the web service but does not create a PostgreSQL database. Create a managed PostgreSQL database and configure `DATABASE_URL` and `CORS_ORIGINS` in Render. The PostgreSQL driver is included and `postgres://` URLs are normalized to the psycopg SQLAlchemy dialect.

## Privacy and safety limitations

This is an MVP scaffold, not a clinical tool or a security audit. The phrase detector is a basic routing aid; it can miss risk or flag context incorrectly and cannot determine whether someone is safe. Establish a reviewed safety protocol and appropriate human-support guidance before inviting real users.

Raw vent text is not persisted by this API. If AI reflection is enabled and the user opts in, the submitted text is sent to OpenAI for processing. Check-in notes are stored and may contain sensitive personal information. Do not describe the service as guaranteed confidential, therapy, or an emergency service.

Before production, add rate limiting, account recovery, email verification where appropriate, Alembic migrations, backups, monitoring that does not log sensitive content, and a review of applicable privacy obligations.
