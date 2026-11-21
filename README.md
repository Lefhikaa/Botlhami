# Botlhami

Botlhami is an innovation platform for CEDA. Saxum Advisory & Solutions (Pty) Ltd built it for the CEDA Innovation Portal Hackathon (13–23 November 2026).

It takes ideas from submission through screening, blind expert evaluation and adjudication to an award with an implementation plan, or a development report for applicants who are not awarded. Everything is tracked live, protected by role-based access and recorded in an append-only audit trail.

**Live site:** https://botlhami-saxum-dcbngscjene6gqef.southafricanorth-01.azurewebsites.net

## What's built

| Area | What it does |
| --- | --- |
| Accounts | Self-registration with email verification and Omang (format check, stored only as a keyed hash plus the last 4 digits, card upload and staff ID checks); password or one-time-code sign-in; password change and reset; lockout after 5 failed attempts |
| Roles and security | Six roles (applicant, evaluator, adjudicator, CEDA consultant, committee observer, administrator), server-side permission checks, append-only audit trail, Content Security Policy, HSTS |
| Ideas | Submission with mandatory-field checks, implementation capacity, drafts and documents; screening; blind evaluation on CEDA's six weighted categories with per-category comments; adjudication; revision rounds; further assessment; pipeline board; notifications and email alerts |
| Evaluation engine | Radar chart of every evaluator, strengths and weaknesses, disagreement and near-pass flags, and an explained recommendation (approve, further assessment or decline) |
| After a decision | Awards with a CEDA officer and an implementation plan of milestones; development reports, certificates and improve-and-resubmit for applicants not awarded |
| Help and support | Searchable FAQs, regulator contacts, forms and documents; support tickets with severity-based service levels; administrators manage all content without code |
| Chat | Live chat with CEDA consultants, plus the Botlhami Assistant, which answers from the help content (optionally grounded with Azure OpenAI) and hands over to a person |
| Reports | Participation, outcomes by sector and town, stage times against targets, evaluator workload, support performance, after-award progress, chat and assistant reports, CSV export without names |
| Design | CEDA colours, light and dark mode, sidebar navigation with search (Ctrl/⌘+K), page loading feedback, works on phones |
| Operations | Azure App Service and PostgreSQL in South Africa North, Azure Communication Services email, Application Insights availability test, tests and deployment on every push |

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

To load demo accounts for every role, plus sample ideas, documents and support tickets:

```bash
python manage.py seed_demo --password "choose-a-demo-password"
```

Open http://127.0.0.1:8000. Locally, emails such as one-time codes are printed in the terminal instead of being sent.

## Tests

```bash
python manage.py test
```

## Stack

- Python 3.12, Django 5.2
- PostgreSQL in production, SQLite locally
- Hosting: Azure App Service, South Africa North region
- Email: Azure Communication Services
- Monitoring: Application Insights availability test on `/health/`
- Password hashing: Argon2

All configuration comes from environment variables. See `.env.example`. In production, set at least `SECRET_KEY`, `DATABASE_URL`, `ALLOWED_HOSTS`, `ACS_CONNECTION_STRING`, `ACS_SENDER_ADDRESS` and `OMANG_PEPPER` (a long random value that must never change once set, or stored Omang numbers stop matching).

## Deployment

The app is hosted on Azure App Service in South Africa North, and is deployed automatically from `main` by GitHub Actions. See [DEPLOYMENT.md](DEPLOYMENT.md) for the one-time setup.

## Security notes

- Passwords are hashed with Argon2. One-time codes are stored hashed, expire after 10 minutes, and allow 5 attempts.
- Sign-in locks for 15 minutes after 5 failed attempts from the same email and IP address.
- Every sign-in, failed attempt, denied access and account change is written to an append-only audit trail.
- Omang numbers are stored only as an HMAC-SHA256 hash (keyed with `OMANG_PEPPER`) plus the last 4 digits. Omang copies are visible only to ID-check staff, and every view is logged.
- Evaluators never see who the applicant is.
- A Content Security Policy allows only the site's own scripts. In production, cookies are secure and HSTS is on.

© 2026 Saxum Advisory & Solutions (Pty) Ltd
