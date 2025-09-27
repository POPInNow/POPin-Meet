# POPin Meet — TODO and Roadmap

This document captures prioritized improvements, security hardening, and feature roadmap for the POPin Meet app. It references specific files and symbols to make each task easy to implement.

## Immediate Priorities (Critical)
- [ ] CSRF protection for all forms and mutating routes
  - Add Flask-WTF and enable CSRF globally.
  - Inject `{{ form.csrf_token }}` in templates for forms in `POPin-Meet/templates/` (e.g., `create_meeting.html`, `respond_meeting.html`).
  - File refs: `POPin-Meet/routes.py`, templates.

- [ ] Validate OAuth `state` parameter
  - Google: In `POPin-Meet/routes.py::oauth2callback()`, verify `state == session['oauth_state']`, then clear it.
  - Microsoft: In `POPin-Meet/routes.py::msgraph_callback()`, verify `state == session['msgraph_state']`, then clear it.
  - File refs: `POPin-Meet/google_calendar.py`, `POPin-Meet/microsoft_calendar.py`, `POPin-Meet/routes.py`.

- [ ] Move OAuth credentials off client-side session
  - Do NOT store full credential dicts in Flask cookie sessions.
  - Use server-side session (Flask-Session with Redis) or a DB table (e.g., `oauth_tokens`) and store only an opaque key in session per meeting token.
  - Encrypt at rest for DB storage (e.g., Fernet).
  - File refs: `POPin-Meet/routes.py`.

- [ ] Convert disconnect endpoints to POST with CSRF
  - Change `/disconnect_calendar/<token>` and `/disconnect_outlook/<token>` to POST endpoints.
  - Use CSRF tokens and form buttons/links.
  - File refs: `POPin-Meet/routes.py`, `POPin-Meet/templates/respond_meeting.html`.

- [ ] Logging controls and redaction
  - Replace global `logging.basicConfig(level=logging.DEBUG)` with env-driven levels.
  - Use per-module loggers: `logger = logging.getLogger(__name__)`.
  - Redact tokens, emails, and identifiers in logs.
  - File refs: `POPin-Meet/app.py`, `POPin-Meet/routes.py`, `POPin-Meet/microsoft_calendar.py`, others.

- [ ] Sanitize ICS filename
  - In `POPin-Meet/routes.py::download_ics()`, use `werkzeug.utils.secure_filename` for `Content-Disposition` filename derived from `meeting_title`.

- [ ] Basic rate limiting
  - Add `Flask-Limiter` with sensible defaults for public GET endpoints and OAuth callbacks.

## High Priority
- [ ] Use exact slot durations for Google free/busy
  - Parity with Outlook path: accept `slot_ranges_utc` based on `meeting['slots_meta']` and query exact ranges instead of assuming 1 hour.
  - File refs: `POPin-Meet/google_calendar.py`, `POPin-Meet/routes.py`.

- [ ] Security headers and HTTPS enforcement
  - Add `Flask-Talisman` (or manual headers) for HSTS, CSP (report-only initially), Referrer-Policy, X-Content-Type-Options, X-Frame-Options.

- [ ] Database migrations
  - Introduce `Flask-Migrate`/Alembic, remove production `db.create_all()` from `POPin-Meet/app.py`.
  - Add deploy step: `flask db upgrade`.

- [ ] Provider selection when both calendars connected
  - Let respondent choose Google vs Outlook if both are connected.
  - Persist choice in `session[f'av_source_{token}']` and reflect in `POPin-Meet/templates/respond_meeting.html`.

- [ ] OAuth redirect domain configuration
  - Ensure `APP_DOMAIN` is HTTPS in prod and validated. Fail fast on invalid/missing config.
  - File refs: `POPin-Meet/google_calendar.py`, `POPin-Meet/microsoft_calendar.py`.

## Medium Priority
- [ ] Standardize availability function return shapes
  - Always return index-aligned dict `{i: bool}` (False on failure) instead of `{}`.
  - File refs: `POPin-Meet/google_calendar.py`, `POPin-Meet/microsoft_calendar.py`.

- [ ] Time formatting portability
  - Replace `strftime('%-I:%M %p')` with `%I:%M %p` and strip leading zero for Windows compatibility.
  - File refs: `POPin-Meet/routes.py`.

- [ ] Session and cookie security
  - Add `SESSION_COOKIE_SECURE=True`, `SESSION_COOKIE_HTTPONLY=True`, `SESSION_COOKIE_SAMESITE='Lax'`, and `PERMANENT_SESSION_LIFETIME` in config.
  - File refs: `POPin-Meet/app.py`.

- [ ] README/setup alignment
  - Either provide `requirements.txt` or update README to `uv pip sync` / PEP 621 workflow.

- [ ] Fix .gitignore quoted paths
  - Remove quotes around filenames so they are actually ignored.
  - File ref: `.gitignore`.

- [ ] Replace summary page auto-refresh with SSE
  - Replace 30-second reload in `POPin-Meet/templates/meeting_summary.html` with Server-Sent Events (SSE) or websockets for live updates.

## Low Priority
- [ ] App factory + blueprints
  - Migrate from `from routes import *` to an app factory pattern and blueprint modules for cleaner structure.
  - File refs: `POPin-Meet/app.py`, `POPin-Meet/routes.py`.

- [ ] Remove unused imports and tidy
  - E.g., remove `from sqlalchemy import func` in `POPin-Meet/models.py` if unused.

- [ ] Consolidate entry points
  - Decide between `POPin-Meet/app.py` and `POPin-Meet/main.py` and keep one canonical dev entrypoint.

- [ ] Unit tests for time parsing and availability
  - Add tests for Outlook timestamp edge cases (7-digit fractions, Z vs offset) and Google free/busy.

## Feature Roadmap
- **Finalize time action (organizer)**
  - POST endpoint to confirm a slot; freeze poll; send final notifications; mark UI as Confirmed.

- **Participant reminders**
  - Optional email/SMS reminders to non-responders; throttle to avoid spam.

- **Export responses**
  - `GET /meeting/<token>/export.csv` including all respondents and their availability.

- **Organizer invite workflow**
  - Allow organizer to list participants (emails/phones), send invites with unique response links, and track who has responded.

- **Direct calendar event creation**
  - With organizer consent and OAuth, create the event in Google/Outlook on confirmation.

- **Slack slash command integration**
  - `/popin-meet` to create a poll from Slack and post results to a channel.

- **Poll editing and closing**
  - Add/remove time slots until poll is closed; keep an audit trail.

- **Time zone intelligence**
  - Suggest time options that maximize overlap across participants’ locales; show local times for each participant.

- **Admin dashboard**
  - View polls, usage analytics, and error logs; retry failed notifications.

## Ops & Deployment Notes
- Prefer Gunicorn behind Nginx with systemd service (`popin-meet`).
- Configure all secrets via environment variables or a secret manager; do not commit `.env`.
- Add `/healthz` (simple 200 OK) and `/readiness` (checks DB connectivity) for monitoring.
- Log rotation and env-driven log levels; avoid verbose debug in production.
- Add database migration step to deployment pipeline.

## Quick Implementation Order
1) CSRF + POST-only disconnect routes + OAuth `state` validation.
2) Logging controls and redaction.
3) ICS filename sanitization.
4) Standardize availability return shapes and improve Google free/busy to use exact ranges.
5) Session/cookie security flags and server-side token storage.
6) Migrations, rate limiting, security headers.

---
Keep this file updated as tasks are completed. If you want, we can create GitHub issues from each checkbox to track progress. 
