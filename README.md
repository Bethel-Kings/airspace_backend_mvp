# AirSpace API — MVP backend

FastAPI backend for **AirSpace: Vent and Decompress**. Includes account registration/login, private emotional check-ins, a vent endpoint, an optional AI reflection endpoint, and basic safety routing.

## MVP scope

- Email/password authentication with JWT bearer tokens.
- Password hashing with Argon2 through `pwdlib`.
- Vent endpoint returns acknowledgement and reflection prompts; **raw vent text is not stored**.
- Reframe endpoint uses OpenAI only when `OPENAI_API_KEY` is configured; otherwise it returns a clearly generic fallback.
- Mood check-ins (1–10 before/after) can be listed and deleted by their owner.
- Account deletion cascades to saved check-ins.
- `/health` endpoint for deployment checks.
- Render deployment manifest.

## Important limitations before real users

This is an MVP scaffold, not a clinically validated product or a security audit. Do not market it as therapy, an emergency service, or guaranteed confidential care. The crisis phrase detector is deliberately simple and can miss risk or flag context incorrectly. It must not be the only safety mechanism.

Before production:
1. Use managed PostgreSQL on Render; do not rely on a local SQLite file for production persistence.
2. Set a long, unique `JWT_SECRET` and exact frontend origins in `CORS_ORIGINS`.
3. Use HTTPS, rate limiting, email verification, password reset, abuse controls, dependency scanning, backups, and monitoring that does not log vent content.
4. Review Nigerian privacy obligations and applicable data-protection requirements with a qualified professional.
5. Establish a reviewed crisis-response protocol and display locally appropriate support options. Do not rely on the simple keyword detector alone.
6. Decide retention, consent, deletion, and AI-provider data handling with users before launch. Avoid sending identifying details to an AI provider.
7. Add tests and security review before collecting sensitive real-world data.

## Run locally

Requires Python 3.11+.

```bash
python -m venv .venv
# Windows PowerShell:
.venv\\Scripts\\Activate.ps1
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt
copy .env.example .env   # Windows; on macOS/Linux use: cp .env.example .env
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/docs` for interactive API documentation.

## Environment variables

- `DATABASE_URL`: local default is SQLite; use a PostgreSQL connection string in deployment.
- `JWT_SECRET`: replace the example value before deployment.
- `CORS_ORIGINS`: comma-separated exact frontend origins.
- `OPENAI_API_KEY`: optional. Leave blank to use the generic fallback.
- `OPENAI_MODEL`: model name available to your API account.
- `PERSIST_VENT_TEXT`: currently not used to persist vents; raw vent content is never written by this MVP.

## API quick start

1. `POST /api/v1/auth/register` with `{"email":"you@example.com","password":"at-least-10-chars"}`.
2. Copy `access_token` from the response.
3. In Swagger, click **Authorize** and enter `Bearer YOUR_TOKEN` (or use the token as the bearer credential).
4. Try:
   - `POST /api/v1/vent` — `{"text":"I have had a difficult day."}`
   - `POST /api/v1/reframe` — `{"text":"I feel overwhelmed by everything.","prompt_style":"gentle"}`
   - `POST /api/v1/checkins` — `{"before_score":8,"after_score":5,"emotion":"overwhelmed","note":"Felt calmer after writing."}`
   - `GET /api/v1/checkins`
   - `DELETE /api/v1/checkins/{id}`
   - `DELETE /api/v1/account`

## Endpoint summary

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Health check |
| POST | `/api/v1/auth/register` | Create account |
| POST | `/api/v1/auth/login` | Get access token |
| POST | `/api/v1/vent` | Receive acknowledgement/prompts; does not save text |
| POST | `/api/v1/reframe` | Optional AI-assisted reflection |
| POST | `/api/v1/checkins` | Save emotional state check-in |
| GET | `/api/v1/checkins` | List own check-ins |
| DELETE | `/api/v1/checkins/{id}` | Delete own check-in |
| DELETE | `/api/v1/account` | Delete account and check-ins |

## Architecture

`FastAPI routes → schemas → SQLAlchemy models → database`

The MVP deliberately separates transient venting from persisted check-in tracking. This reduces stored sensitive content, but check-in notes are still sensitive personal data and should be treated accordingly.
