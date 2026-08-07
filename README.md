# Baker Street Assessment Platform - Backend

Django REST Framework backend for the Baker Street Assessment Platform, a professional clinical assessment solution for therapists and psychologists.

## Overview

This is the backend API powering Baker Street Assessment Platform. It handles user authentication, client management, assessment delivery, automated scoring, and secure token-based respondent invitations.

## Features

### Core Functionality
- **JWT Authentication** - Secure token-based auth with refresh tokens
- **Multi-Tenant Architecture** - Complete data isolation per clinician account
- **Respondent Link System** - Cryptographically signed tokens with usage limits and expiration
- **Automated Scoring Engine** - Real-time calculation for clinical frameworks (ABA, EFA, etc.)
- **Email Delivery** - Scheduled and immediate assessment invitations
- **QR Code Generation** - Visual respondent link sharing

### Security
- **Cloudflare Turnstile Integration** - Bot protection on signup/login
- **Admin Access Middleware** - IP-based and token-based admin route protection
- **CORS Configuration** - Secure cross-origin resource sharing
- **Environment-based Secrets** - No hardcoded credentials

### Monitoring & Error Tracking
- **Sentry Integration** - Real-time error reporting and performance monitoring
- **Structured Logging** - Comprehensive request/response logging

## Tech Stack

- **Python 3.10+**
- **Django 5.2**
- **Django REST Framework** with SimpleJWT
- **PostgreSQL** (production database; SQLite for local development)
- **Resend** (transactional email)
- **Gunicorn** (WSGI server)
- **WhiteNoise** (static files)

Scheduled invites are sent by handing Resend a `scheduled_at` timestamp, so there
is no Celery or Redis in this project.

## Project Structure

```
bakerbackend/
├── accounts/          # User authentication, 2FA, password reset, admin approval
├── clients/           # Client records and client groups
├── assessments/       # Assessment models, scoring, and respondent links
├── notifications/     # In-app notification feed
├── status/            # Health check endpoints
├── bakerapi/          # Project settings, middleware, admin site
├── manage.py          # Django management script
└── requirements.txt   # Python dependencies
```

## Getting Started

### Prerequisites
- Python 3.10+
- PostgreSQL (production only; local development defaults to SQLite)

### Installation

1. Create and activate virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Set up environment variables (create `.env` file):
```bash
SECRET_KEY=your-secret-key
DATABASE_URL=postgresql://user:password@localhost:5432/bakerstreet
ALLOWED_HOSTS=localhost,127.0.0.1
CORS_ALLOWED_ORIGINS=http://localhost:5173
TURNSTILE_SECRET_KEY=your-turnstile-secret
SENTRY_DSN=your-sentry-dsn
```

4. Run migrations:
```bash
python manage.py migrate
```

5. Create superuser:
```bash
python manage.py createsuperuser
```

6. Start development server:
```bash
python manage.py runserver
```

## API Endpoints

### Authentication (`/api/auth/`)
- `POST /api/auth/signup/` - Start registration (sends an email verification code)
- `POST /api/auth/signup/verify/` - Confirm the code and create the account
- `POST /api/auth/login/` - User login (returns tokens, or a 2FA challenge)
- `POST /api/auth/2fa/verify/` - Complete a two-factor challenge
- `POST /api/auth/token/refresh/` - Refresh JWT token
- `POST /api/auth/logout/` - Revoke a refresh token
- `GET|PATCH /api/auth/profile/` - Read or update the signed-in profile
- `POST /api/auth/password/reset/request|validate|complete/` - Password reset

Superuser only: `pending-users/`, `approve-user/`, `reject-user/`, `all-users/`,
`toggle-user-active/`, `delete-user/`.

### Assessments
- `GET|POST /api/assessments/` - List or create assessments
- `GET|PUT /api/assessments/{slug}/` - Retrieve or update an assessment
- `GET /api/assessments/published/` - Published assessments only
- `GET|POST /api/assessment-responses/` - List or record responses
- `GET /api/assessment-categories/`, `GET /api/assessment-tags/` - Taxonomy

Creating and updating assessments requires a staff or superuser account.

### Respondent Links
- `POST /api/respondent-links/issue/` - Generate a respondent link token
- `POST /api/respondent-links/email/` - Issue a link and email it to the client
- `POST /api/respondent-links/schedule/` - Schedule recurring invitations
- `GET /api/respondent-links/schedule/runs/` - List scheduled or sent runs
- `DELETE /api/respondent-links/schedule/{reference}/` - Cancel a schedule

Public (no authentication, token-gated):
- `POST /api/respondent-links/resolve/` - Resolve a token
- `POST /api/respondent-links/client/` - Capture client details for a new respondent
- `POST /api/respondent-links/assessment/` - Fetch an invited assessment
- `POST /api/respondent-links/assessment-response/` - Submit answers

### Clients
- `GET|POST /api/clients/` - List or create clients
- `GET|PATCH|DELETE /api/clients/{slug}/` - Retrieve, update or delete a client
- `POST /api/clients/import/` - Bulk import from CSV rows
- `GET|POST /api/client-groups/` - List or create client groups

### Other
- `GET /api/notifications/` - Notification feed for the signed-in user
- `GET /api/health/` - Public uptime check
- `GET /api/health/full/` - Detailed service checks (staff or admin IP/token)

## Deployment

### Render Deployment

1. Connect GitHub repository to Render
2. Set environment variables in Render dashboard
3. Deploy using Render's auto-deploy or manual deploy

### Manual Deployment (Render CLI)

```bash
# Install Render CLI
npm install -g @render/cli

# Login to Render
render login

# Deploy
render deploys create --service-id your-service-id
```

### Database Migrations on Production

```bash
# Using Render shell
render shell your-service-id
python manage.py migrate
```

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `SECRET_KEY` | Django secret key | Yes |
| `DATABASE_URL` | Database connection string. The app refuses to start without it when `DEBUG` is false | Yes in production |
| `ALLOWED_HOSTS` | Comma-separated allowed hosts | Yes |
| `FRONTEND_BASE_URL` | Comma-separated frontend origins. The first is used to build invite and reset links, and all are added to CORS | Yes |
| `RESEND_API_KEY` | Resend API key for transactional email | Yes |
| `RESEND_FROM_EMAIL` | Verified sender address | Yes |
| `CORS_ALLOWED_ORIGINS` | Extra CORS origins beyond `FRONTEND_BASE_URL` | No |
| `RESEND_REPLY_TO` | Default reply-to address | No |
| `FEEDBACK_TO_EMAIL` | Where in-app feedback is delivered | No |
| `TURNSTILE_ENABLED` | Turn Cloudflare Turnstile on for signup and login | No |
| `TURNSTILE_SECRET` | Cloudflare Turnstile secret (required when enabled) | No |
| `SIGNUP_ENABLED` | Allow self-service registration. Defaults to false | No |
| `DJANGO_ADMIN_URL` | Path for the Django admin. Defaults to `admin` | No |
| `ADMIN_ALLOWED_IPS` | Comma-separated IPs or CIDRs allowed to reach the admin | No |
| `ADMIN_ACCESS_TOKEN` | Value for the `X-Admin-Token` header, an alternative to the IP allowlist | No |
| `SENTRY_DSN` | Sentry error tracking DSN | No |
| `JWT_ACCESS_MINUTES` / `JWT_REFRESH_DAYS` | Token lifetimes. Default 15 minutes and 7 days | No |
| `DEBUG` | Enable debug mode (development only) | No |

If neither `ADMIN_ALLOWED_IPS` nor `ADMIN_ACCESS_TOKEN` is set in production, the
Django admin is reachable from any address at whatever `DJANGO_ADMIN_URL` is set
to. Set at least one.

## Development

### Running Tests
```bash
python manage.py test
```

Tests run against a throwaway database, so they never touch the configured one.
Email sending is mocked; a test must never call Resend for real. Test cases that
hit rate-limited endpoints should extend `bakerapi.test_utils.ThrottledAPITestCase`
so throttle counters reset between tests.

### Database Operations
```bash
# Create migrations
python manage.py makemigrations

# Apply migrations
python manage.py migrate

# Create database backup
pg_dump $DATABASE_URL > backup.sql
```

## Contributing

This is a private project. For access or collaboration inquiries, contact the repository owner.

## License

Proprietary - All rights reserved

## Support

For issues or questions, open a GitHub issue or contact the maintainer.

---

**Live API:** https://bakerbackend-enjy.onrender.com  
**Frontend:** https://www.bakerstreetassessment.com (Vercel project `bakers-street`)  
**Repository:** https://github.com/soulhacker010/bakerbackend
