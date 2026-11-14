# Botlhami

Botlhami is an innovation platform for CEDA. Saxum Advisory & Solutions (Pty) Ltd is building it for the CEDA Innovation Portal Hackathon (13–23 November 2026).

It takes ideas from submission through review, feedback and approval to award, with live tracking, role-based access and a full audit trail.

## Status

| Area | Status |
| --- | --- |
| Accounts: self-registration, email verification, password and one-time-code sign-in, password change and reset | Done |
| Roles, permission checks, append-only audit trail, security headers, login lockout | Done |
| Idea submission, evaluation workflow, adjudication, awards | In progress |
| Live chat, admin content, FAQs, alerts, reports | Planned |

## Run it locally

You need Python 3.12 or later.

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Open http://127.0.0.1:8000. Locally, emails such as one-time codes are printed in the terminal instead of being sent.

## Tests

```bash
python manage.py test
```

## Stack

- Python 3, Django 5.2
- PostgreSQL in production, SQLite locally
- Hosting: Azure App Service, South Africa North region
- Email: Azure Communication Services
- Password hashing: Argon2

All configuration comes from environment variables. See `.env.example`.

## Security notes

- Passwords are hashed with Argon2. One-time codes are stored hashed, expire after 10 minutes, and allow 5 attempts.
- Sign-in locks for 15 minutes after 5 failed attempts from the same email and IP address.
- Every sign-in, failed attempt, denied access and account change is written to an append-only audit trail.
- A Content Security Policy is set. In production, cookies are secure and HSTS is on.

© 2026 Saxum Advisory & Solutions (Pty) Ltd
