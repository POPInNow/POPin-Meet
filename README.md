# POPIN Meet

A lightweight meeting coordination app built with Flask. Create a poll of 2–3 time slots, share a link, collect availability, and confirm the best time. Includes optional Google/Outlook calendar availability checks, add-to-calendar deep links, and multi-channel organizer notifications (Email, SMS, WhatsApp, Slack).

## Features
- Create meeting with multiple time slots
- Shareable response link (`/s/<token>`)
- Live summary with best time slot and participant availability
- Add to Google/Outlook/Outlook 365 and `.ics` download
- Optional Google/Outlook calendar connect for availability pre-select
- Organizer notifications via Email/SMS/WhatsApp/Slack

## Tech Stack
- Python 3.11+
- Flask, SQLAlchemy
- Google Calendar API, Microsoft Graph (read-only availability)
- SMTP/SES for email, Twilio for SMS/WhatsApp

## Setup
1. Create a virtual environment and install deps
   ```bash
   python -m venv .venv
   .venv/Scripts/activate  # Windows
   # Or: source .venv/bin/activate (macOS/Linux)
   pip install -r requirements.txt  # or: uv pip install -r requirements.txt if using uv/pyproject
   ```

2. Copy environment template and fill in values
   ```bash
   cp .env.example .env
   ```
   - Do NOT commit `.env`.
   - Set `APP_DOMAIN` to your domain (used for OAuth callbacks and links).
   - Provide `DATABASE_URL` (SQLite for dev or Postgres for prod).
   - Provide Google and Microsoft OAuth creds; add redirect URIs:
     - Google: `https://<APP_DOMAIN>/oauth2callback`
     - Microsoft: `https://<APP_DOMAIN>/msgraph/callback`

3. Initialize the DB (dev)
   ```bash
   python -m flask --app POPIN-Meet/app.py shell -c "from db import db, init_app; from app import app; from models import Meeting, Response; from db import db; db.create_all(app=app)"
   ```

4. Run (dev)
   ```bash
   python POPIN-Meet/app.py
   # visit http://localhost:5000
   ```

## Slack setup

To receive organizer notifications in Slack using Incoming Webhooks:

1. Add Slack's Incoming Webhooks to your workspace and create a webhook for the target channel. See the official docs: https://api.slack.com/messaging/webhooks
2. Copy the generated webhook URL (it starts with `https://hooks.slack.com/services/...`).
3. In the app's Create Meeting page, select "Slack" under Notification Preferences and paste the webhook URL.

Notes:

- Treat webhook URLs as secrets. Do not commit or share them publicly.
- Outbound HTTPS access must be allowed from the server to Slack.

## Security & Operations
- Never commit secrets. `.env` is git ignored; rotate any credentials previously committed.
- Add CSRF protection and OAuth `state` validation before production launch.
- Prefer Postgres in production. Use Alembic/Flask-Migrate for schema changes.
- Run with Gunicorn behind Nginx; enable HTTPS and secure cookies.
- Configure environment variables on the host (systemd EnvironmentFile or secret store).
- Ensure OAuth apps are configured with correct redirect URLs.
- Create a systemd service to run Gunicorn pointing at `POPin-Meet/app:app`.

## License
Proprietary – © POPin Labs
