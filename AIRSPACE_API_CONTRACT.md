# AirSpace API: Frontend Contract (v0.3.0)

Verified against `Bethel-Kings/airspace_backend_mvp` with `airspace-handoff-fixes.patch` applied. Interactive docs: `{BASE_URL}/docs`. Machine-readable spec: `openapi.json` (attached alongside this file).

---

## 1. Basics

| Item | Value |
|---|---|
| Base URL | `{BASE_URL}` (Render URL once deployed; `http://127.0.0.1:8000` locally) |
| Prefix | `/api/v1` (except `/health`) |
| Format | JSON in, JSON out |
| Auth | `Authorization: Bearer <access_token>` |
| Token lifetime | 7 days (10080 min). **No refresh endpoint.** On `401`, send the user to login. |
| CORS | Exact origins only, set via `CORS_ORIGINS`. Headers allowed: `Authorization`, `Content-Type`. Methods: GET, POST, PATCH, DELETE. Native mobile apps are not affected by CORS. |

**Timestamps:** `created_at` is ISO 8601 in **UTC** and always carries an offset (`+00:00`), in dev and prod alike.

---

## 2. Error shapes (handle both)

**Business errors** (401, 404, 409):
```json
{ "detail": "Invalid email or password." }
```

**Validation errors** (422), where `detail` is an **array**:
```json
{ "detail": [ { "type": "value_error", "loc": ["body", "email"], "msg": "value is not a valid email address: ...", "input": "bad" } ] }
```

Use `loc[-1]` to map the error to a form field. Do not display `msg` raw to users; write your own copy.

| Status | Meaning |
|---|---|
| 401 | Missing, invalid, expired token, or user no longer exists. Has `WWW-Authenticate: Bearer`. |
| 404 | Check-in not found or not owned by the user |
| 409 | Email already registered |
| 422 | Validation failed |
| 429 | Rate limited. Read the `Retry-After` header (seconds) and disable the button until then. |
| 5xx | Unexpected; show a generic retry message |

---

## 3. Endpoints

### `GET /health`
No auth. `200 {"status":"ok","service":"airspace-api"}`. Does not check the database.

### `GET /api/v1/crisis-resources`
No auth. Returns a list of verified emergency helplines and mental health crisis intervention contacts:
```json
[
  {
    "name": "MANI (Mentally Aware Nigeria Initiative)",
    "phone": "08091116264",
    "alt_phone": "08111680686",
    "hours": "24/7",
    "description": "Free, confidential emotional support for anxiety, depression, and suicidal thoughts.",
    "url": "https://mentallyaware.org"
  },
  {
    "name": "SURPIN (Suicide Research & Prevention Initiative)",
    "phone": "08000787746",
    "alt_phone": "09034400009",
    "hours": "24/7",
    "description": "Nationwide crisis intervention; counsellors speak major Nigerian languages.",
    "url": "https://surpin.org"
  },
  {
    "name": "Safe Place Nigeria (She Writes Woman)",
    "phone": "08008002000",
    "alt_phone": null,
    "hours": "24/7",
    "description": "National toll-free crisis line with free tele-therapy referrals.",
    "url": "https://shewriteswoman.org"
  },
  {
    "name": "Lagos Lifeline",
    "phone": "07000006463",
    "alt_phone": null,
    "hours": "24/7",
    "description": "Lagos State line connecting callers to psychiatric professionals.",
    "url": "https://lagosstate.gov.ng"
  },
  {
    "name": "Emergency Services",
    "phone": "112",
    "alt_phone": null,
    "hours": "24/7",
    "description": "National emergency number. In Lagos, dial 767.",
    "url": ""
  }
]
```

### `POST /api/v1/auth/register`
```json
{ "email": "user@example.com", "password": "min 10, max 128 chars" }
```
`201 {"access_token": "...", "token_type": "bearer"}`. The user is logged in immediately. Errors: `409`, `422`, `429` (10 per hour per IP). Email is lowercased server-side.

### `POST /api/v1/auth/login`
Same body. `200` returns the same token shape. Errors: `401 "Invalid email or password."` (same message for wrong email or wrong password), `429` (10 attempts per 5 min per email, 20 per 5 min per IP).

### `GET /api/v1/me`  (auth)
`200 {"id": 1, "email": "user@example.com", "created_at": "..."}`. Call on app start to validate a stored token; on `401`, clear it and show login.

### `POST /api/v1/vent`  (auth)
```json
{ "text": "1 to 12000 chars" }
```
```json
{
  "acknowledgement": "string",
  "reflection_prompts": ["string", "string", "string"],
  "safety_notice": "string | null",
  "crisis_resources": [ ... ] | null,
  "stored": false
}
```
- Text is **not stored and not sent to AI**.
- Acknowledgement and prompts are currently **static** (identical every call).
- If `safety_notice` is non-null, crisis resources are also returned in `crisis_resources`. Show it prominently **before** anything else.

### `POST /api/v1/reframe`  (auth)
```json
{
  "text": "1 to 6000 chars",
  "prompt_style": "gentle | practical | reflective",
  "consent_to_ai_processing": false
}
```
```json
{
  "reflection": "string | null",
  "safety_notice": "string | null",
  "crisis_resources": [ ... ] | null,
  "needs_human_support": false,
  "ai_enabled": true,
  "ai_status": "see table",
  "consent_required": false
}
```

| `ai_status` | Meaning | What the UI does |
|---|---|---|
| `skipped_for_safety` | Crisis phrase detected. `reflection` is null, `needs_human_support: true`. | Show `safety_notice` and structured `crisis_resources`. Do not show a reflection or "try again". |
| `unavailable` | No AI key on the server. `reflection` is a generic prompt that does not use the user's text. | Show the generic text. No consent needed. |
| `consent_required` | AI is on but the user has not opted in. `reflection` is null. | Show the consent dialog; on accept, resend with `consent_to_ai_processing: true`. |
| `success` | AI reflection generated. | Show `reflection`. |
| `fallback` | AI call failed or returned empty; generic text returned. | Show it; optionally label as "basic prompt". |

**Limits:** AI calls (consented requests only) are capped at 30/hour per user; over that, `429`. Crisis and consent responses are never rate limited.

**Consent flow:** the client cannot know in advance whether AI is on. First call with `consent_to_ai_processing: false`. If the response is `consent_required`, show a disclosure that the text is sent to an external provider (OpenAI), then resend only after the user opts in. Never default the flag to `true`.

### `POST /api/v1/checkins`  (auth)
```json
{ "before_score": 1-10, "after_score": 1-10 | null, "emotion": "max 80 | null", "note": "max 500 | null" }
```
`201` returns:
```json
{ "id": 1, "before_score": 3, "after_score": null, "emotion": null, "note": null, "created_at": "...", "safety_notice": null, "crisis_resources": null }
```
If `emotion` or `note` trips the crisis check, `safety_notice` and `crisis_resources` are populated: show them prominently (same rule as vent). The check-in is still saved. Notes are stored server-side; tell users that.

**Typical flow:** POST with `before_score` when the session starts, then PATCH `after_score` when it ends.

### `PATCH /api/v1/checkins/{id}`  (auth)
Send only the fields to change: `after_score` (1-10), `emotion`, `note`. An explicit `null` clears that field. `before_score` cannot be changed. Unknown fields and an empty body return `422`. Returns the full check-in (with `safety_notice` and `crisis_resources`). `404` if not found or not yours.

### `GET /api/v1/checkins`  (auth)
`200` returns an array of check-ins, newest first, **hard-capped at 100**. No pagination, filtering, or total count yet. `safety_notice` and `crisis_resources` are always `null` here.

### `DELETE /api/v1/checkins/{id}`  (auth)
`204` with an empty body. `404` if not found or not yours.

### `DELETE /api/v1/account`  (auth)
`204`. Deletes the user and all check-ins. **No password re-confirmation**, so add a confirmation dialog in the UI. Clear the stored token afterwards.

---

## 4. TypeScript types

```ts
type Token = { access_token: string; token_type: "bearer" };

type CrisisResource = {
  name: string;
  phone: string;
  alt_phone?: string | null;
  hours: string;
  description: string;
  url: string;
};

type CheckIn = {
  id: number;
  before_score: number;
  after_score: number | null;
  emotion: string | null;
  note: string | null;
  created_at: string;
  safety_notice: string | null;
  crisis_resources?: CrisisResource[] | null;
};

type AiStatus = "skipped_for_safety" | "unavailable" | "consent_required" | "success" | "fallback";

type Reframe = {
  reflection: string | null;
  safety_notice: string | null;
  crisis_resources?: CrisisResource[] | null;
  needs_human_support: boolean;
  ai_enabled: boolean;
  ai_status: AiStatus;
  consent_required: boolean;
};

type User = { id: number; email: string; created_at: string };

type CheckInPatch = { after_score?: number | null; emotion?: string | null; note?: string | null };

type Vent = {
  acknowledgement: string;
  reflection_prompts: string[];
  safety_notice: string | null;
  crisis_resources?: CrisisResource[] | null;
  stored: false;
};

type ApiError = { detail: string | { loc: (string | number)[]; msg: string; type: string }[] };
```

---

## 5. Product and safety rules for the UI

- Never describe AirSpace as therapy, confidential, or an emergency service.
- If `safety_notice` appears (vent or reframe), it takes over the screen. No upsell, no reflection, no cheerful copy. Use `crisis_resources` to render direct tap-to-call buttons (`tel:<phone>`) or website links.
- The crisis detector is a basic phrase match. **It will miss real risk.** The UI must not imply that "no warning" means "the user is safe."
- Do not log request bodies for `/vent`, `/reframe`, or check-in notes in analytics or error trackers (Sentry, LogRocket, etc.).
- Store the token in the most secure option your platform offers (Keychain/Keystore on mobile; avoid `localStorage` on web if you can).

---

## 6. Known gaps (still open)

| Gap | Frontend impact |
|---|---|
| No token refresh / logout | 7-day hard expiry; logout is client-side only (delete the token) |
| No capabilities endpoint | Cannot know `ai_enabled` before the first `/reframe` call |
| No password reset / email verification | Forgotten password means a lost account |
| `DELETE /account` needs no password | Add a confirmation dialog in the UI |
| Check-in list capped at 100, unpaginated | History screens will truncate |
| Rate limits are per-server-process | Fine on one Render instance; not shared across instances |
| `/vent` text is static | Do not market it as personalized |
| Crisis detector is a phrase match | Misses real risk; UI must never imply "no warning = safe" |
