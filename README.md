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

- **Python 3.11+**
- **Django 4.2+**
- **Django REST Framework**
- **PostgreSQL** (production database)
- **Celery** (async task processing)
- **Redis** (caching and task queue)
- **Gunicorn** (WSGI server)

## Project Structure

```
bakerbackend/
├── accounts/          # User authentication and profiles
├── assessments/       # Assessment models, scoring, and respondent links
├── bakerapi/          # Project settings and middleware
├── manage.py          # Django management script
└── requirements.txt   # Python dependencies
```

## Getting Started

### Prerequisites
- Python 3.11+
- PostgreSQL
- Redis (for Celery)

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

### Authentication
- `POST /api/accounts/signup/` - User registration
- `POST /api/accounts/login/` - User login
- `POST /api/accounts/token/refresh/` - Refresh JWT token

### Assessments
- `GET /api/assessments/` - List all assessments
- `POST /api/assessments/` - Create new assessment
- `GET /api/assessments/{slug}/` - Get assessment details
- `PUT /api/assessments/{slug}/` - Update assessment

### Respondent Links
- `POST /api/assessments/respondent-links/issue/` - Generate respondent link token
- `POST /api/assessments/respondent-links/resolve/` - Resolve token and get assessment
- `POST /api/assessments/respondent-links/submit/` - Submit assessment response

### Clients
- `GET /api/assessments/clients/` - List clients
- `POST /api/assessments/clients/` - Create client
- `GET /api/assessments/clients/{slug}/` - Get client details

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
| `DATABASE_URL` | PostgreSQL connection string | Yes |
| `ALLOWED_HOSTS` | Comma-separated allowed hosts | Yes |
| `CORS_ALLOWED_ORIGINS` | Comma-separated CORS origins | Yes |
| `TURNSTILE_SECRET_KEY` | Cloudflare Turnstile secret | Yes |
| `SENTRY_DSN` | Sentry error tracking DSN | No |
| `DEBUG` | Enable debug mode (development only) | No |

## Development

### Running Tests
```bash
python manage.py test
```

### Code Quality
```bash
# Run linting
pylint bakerapi accounts assessments

# Run type checking
mypy .
```

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

**Live API:** https://bakerbackend.onrender.com  
**Frontend:** https://www.bakerstreetassessment.com  
**Repository:** https://github.com/soulhacker010/bakerbackend
