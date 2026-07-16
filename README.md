# Secure Fault Reporting and Resolution System

A Flask and SQLite web application for reporting and resolving building maintenance faults. This project is being developed for a Level 6 Software Engineering and DevOps assignment.

## Current functionality

- User authentication and session management with Flask-Login
- Submission and tracking of building faults
- Recording when and by whom a fault is closed
- Administrator-only user creation and fault deletion
- Role-based access for standard users and administrators
- SQLite persistence using the Python `sqlite3` module
- GOV.UK Design System components with non-GOV.UK branding

## Technology

- Python 3
- Flask
- Flask-Login
- SQLite
- Jinja2
- GOV.UK Frontend
- Node.js and npm for frontend assets
- pytest
- Gunicorn

## Project structure

```text
secure-fault-reporting-system/
|-- app/
|   |-- static/
|   |   |-- css/
|   |   |   `-- application.css
|   |   |-- js/
|   |   |   `-- govuk-frontend.min.js
|   |   `-- src/
|   |       `-- application.scss
|   |-- templates/
|   |   |-- base.html
|   |   |-- index.html
|   |   `-- login.html
|   |-- __init__.py
|   |-- auth.py
|   |-- db.py
|   |-- routes.py
|   `-- validation.py
|-- diagrams/
|   `-- FaultReporterERD.png
|-- scripts/
|   `-- copy-govuk-assets.mjs
|-- tests/
|   `-- test_routes.py
|-- .gitattributes
|-- .gitignore
|-- package-lock.json
|-- package.json
|-- Procfile
|-- README.md
|-- requirements.txt
|-- run.py
`-- schema.sql
```

## Local setup

### 1. Create a virtual environment

Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
```

macOS or Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 2. Install dependencies

```bash
python -m pip install -r requirements.txt
npm install
npm run build
```

### 3. Run the application

```bash
python run.py
```

Then open `http://127.0.0.1:5000`.

## Database

The application creates `instance/app.db` from `schema.sql` when it is first accessed. The local database is ignored by Git and must not be committed.

No database file is included in the repository. To create the first administrator on a new database, set `INITIAL_ADMIN_PASSWORD` before the application's first request. You may also set `INITIAL_ADMIN_USERNAME`; it defaults to `admin`.

Set `SECRET_KEY` to a strong random value in deployed environments. Local database files and environment files must remain uncommitted.

## Testing

Tests are stored in `tests/` and use pytest:

```bash
pytest
```

The tests use the Flask application factory and an isolated temporary database.

## Entity relationship diagram

The database design is documented in [the entity relationship diagram](diagrams/FaultReporterERD.png). It shows the relationships between the `users` and `faults` tables.

## Development status

This repository is in early development. Security hardening, validation, test isolation, and deployment configuration are still being reviewed. No production deployment URL is currently documented.
