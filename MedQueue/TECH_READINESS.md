# MedQueue Technical Readiness (PK)

## 1) CI/CD
- Status: PK
- Implemented:
  - Tests pipeline: .github/workflows/tests.yml
  - Auto deploy pipeline (staging -> production): .github/workflows/deploy.yml
- How to show:
  - Open GitHub Actions tab
  - Show successful runs for Tests and Deploy workflows
  - Show commit history linked to deployments

## 2) Testing
- Status: PK
- Implemented:
  - Unit/feature/regression style tests: startup/backend/appointments/tests.py
  - Automated report generator: startup/backend/run_tests_with_report.py
  - Load tests: startup/backend/load_tests/locustfile.py
- How to show:
  - Run unit/feature/regression:
    - python startup/backend/run_tests_with_report.py --target appointments.tests
  - Run load test:
    - locust -f startup/backend/load_tests/locustfile.py --host http://127.0.0.1:8000

## 3) Hosting (Cloud-ready)
- Status: PK
- Implemented:
  - Containerization: startup/backend/Dockerfile
  - Compose runtime: startup/docker-compose.yml
  - Deploy jobs for staging/prod via SSH in deploy workflow
- How to show:
  - docker compose -f startup/docker-compose.yml up -d --build
  - Open app on localhost and explain same image is used on cloud VM

## 4) Database + Backups
- Status: PK
- Implemented:
  - Stable migrations: startup/backend/appointments/migrations/
  - Backup command: startup/backend/appointments/management/commands/backup_db.py
  - Windows daily task scripts:
    - startup/backend/scripts/backup_db.ps1
    - startup/backend/scripts/setup_daily_backup_task.ps1
- How to show:
  - python startup/backend/manage.py showmigrations
  - python startup/backend/manage.py backup_db
  - Run setup_daily_backup_task.ps1 and show Task Scheduler entry

## 5) Monitoring
- Status: PK
- Implemented:
  - PostHog middleware tracking API requests/errors: startup/backend/appointments/monitoring.py
  - Settings/env hooks in startup/backend/medqueue_project/settings.py
- Required env:
  - POSTHOG_API_KEY
  - POSTHOG_HOST (optional, default us.i.posthog.com)
- How to show:
  - Trigger API calls from frontend/backend
  - Show events in PostHog dashboard

## 6) API Documentation
- Status: PK
- Implemented:
  - OpenAPI schema: /api/schema/
  - Swagger UI: /api/docs/swagger/
  - Redoc UI: /api/docs/redoc/
- How to show:
  - Open Swagger and execute 2-3 endpoints live

## Demo Script (3-5 minutes)
1. Open Swagger -> run hospitals/doctors endpoint.
2. Run tests -> show report artifact in test_reports.
3. Run backup command -> show generated .gz backup file.
4. Show GitHub Actions tests + deploy workflows.
5. Show PostHog incoming events after API calls.
