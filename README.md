# Secure Fault Reporting and Resolution System

A Flask and SQLite demonstration application for reporting and resolving building maintenance faults. The account journey follows applicable GOV.UK Design System patterns within the scope of this demonstration application. This is not a claim of full GOV.UK compliance or production readiness.

## Features

- Email addresses are the case-insensitive account and sign-in identifier.
- Every account belongs to one building or work location.
- Public account creation is available only when the exact email domain is active for the selected building.
- Estates administrators can see users and manage accepted domains only for their own building.
- Fault lists display submitters' full names, never their email addresses.
- Flask-Login, global CSRF protection, Werkzeug password hashing and throttled login POSTs protect account journeys.
- GOV.UK Frontend 6.3.0 provides form, error-summary, notification, table, select and password-input components with non-GOV.UK service branding.

## Local setup

Use Python 3.11 or later and a current Node.js release.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
npm install
npm run build
$env:SECRET_KEY = "replace-with-a-long-random-value"
python run.py
```

On macOS or Linux, activate with `source .venv/bin/activate` and export `SECRET_KEY`. Open `http://127.0.0.1:5000` after startup. `SECRET_KEY` is required outside tests. Set `SESSION_COOKIE_SECURE=true` for HTTPS deployments; it remains off for local HTTP development. Cookies are HTTP-only and use SameSite=Lax.

## Accounts, buildings and email eligibility

The public **Create an account** journey asks for email address, first name, last name, building or work location, and password. Email addresses are trimmed, validated without DNS queries, normalised to lowercase and stored with case-insensitive uniqueness. Registration does not sign the user in.

The selected active building must contain an active allowed-domain record matching the part after the final `@` exactly. Wildcards, substring matching and subdomain inheritance are not supported: `digital.hmrc.gov.uk` does not match `hmrc.gov.uk`. There is no public bypass.

The database seeds these buildings idempotently: Belfast, Birmingham, Bristol, Cardiff, Croydon, Edinburgh, Glasgow, Leeds, Liverpool, Manchester, Newcastle, Nottingham, Portsmouth, Stratford, and Other government or partner location. `hmrc.gov.uk` is seeded for each named HMRC regional centre, but not for Other government or partner location.

## Estates administration

After signing in, an administrator can open **Users** to see accounts in their building and create users or administrators assigned to that same building. **Email domains** lists active and inactive entries for their building. Administrators can add, deactivate and reactivate entries. Entries are retained rather than deleted and can be reactivated. Deactivation metadata represents the current inactive state and is cleared when an entry is reactivated. Deactivation affects new registrations only. Python permission checks and building-scoped SQL enforce this scope, including crafted requests.

### Create an administrator securely

Deployment operators can create an administrator for any active building. The password is hidden and cannot be supplied as a command-line option:

```powershell
$env:FLASK_APP = "run.py"
flask create-admin
```

The command prompts for email, first name, last name, building and password. For architectures that require environment bootstrap before the first request, set all five values; an invalid or unknown building fails rather than being substituted:

```text
INITIAL_ADMIN_EMAIL
INITIAL_ADMIN_PASSWORD
INITIAL_ADMIN_FIRST_NAME
INITIAL_ADMIN_LAST_NAME
INITIAL_ADMIN_BUILDING
```

`INITIAL_ADMIN_USERNAME` is not supported.

### Tutor demonstration

1. Sign in as the selected building's Estates administrator.
2. Open **Email domains** and add the domain after the `@` in the tutor's email address.
3. The tutor opens **Create an account** and selects that same building.
4. The tutor registers with their own email address.
5. Open **Users** as the administrator to demonstrate building-scoped visibility.

## Password policy

Passwords must contain at least 12 characters. Spaces and ordinary Unicode characters are accepted; there are no uppercase, lowercase, number, symbol or artificial maximum-length rules. A small explicit list of common passwords, including `password`, `qwerty`, `welcome`, `admin`, `government` and `hmrc`, is rejected after case-folding and removing non-alphanumeric characters. The application also rejects simple repetition and a small set of obvious sequences; it does not attempt to detect every possible variation of a listed password. Passwords are never redisplayed or logged and are stored only as Werkzeug hashes.

## Login throttling

Only POST login attempts are limited. `LOGIN_RATE_LIMIT` defaults to `5 per minute`; GET requests remain available. Flask-Limiter uses `RATELIMIT_STORAGE_URI`, which defaults to `memory://` for local use and deterministic isolated tests. In-memory storage is not suitable for multi-process production deployment. Configure shared storage such as Redis in production.

## Database and migration

The application creates or upgrades `instance/app.db` automatically and idempotently on the first application request. The `flask create-admin` command also initialises or migrates the database before creating the administrator. Do not delete the database. The migration creates buildings before foreign-keyed account data, changes legacy `username` accounts to `email`, retains IDs, password hashes, names, roles and fault relationships, and assigns migrated users to **Other government or partner location**.

Legacy usernames that are valid emails are lowercased. Other values become deterministic `legacy-<user-id>@migration-placeholder.internal` internal migration placeholders, with a suffix only if required for uniqueness. These placeholders are syntactically valid account identifiers but are not intended for email delivery. SQLite foreign keys are enabled on every application connection and checked after migration. `schema.sql` is non-destructive and can initialise a new database.

### Current entity relationship diagram

```mermaid
erDiagram
    BUILDINGS ||--o{ USERS : has
    BUILDINGS ||--o{ ALLOWED_EMAIL_DOMAINS : allows
    USERS o|--o{ ALLOWED_EMAIL_DOMAINS : creates
    USERS o|--o{ ALLOWED_EMAIL_DOMAINS : deactivates
    USERS ||--o{ FAULTS : submits
    USERS o|--o{ FAULTS : closes

    BUILDINGS {
        INTEGER id PK
        TEXT name
        INTEGER active
    }

    USERS {
        INTEGER id PK
        TEXT email
        TEXT password_hash
        TEXT first_name
        TEXT last_name
        INTEGER building_id FK
        TEXT role
    }

    ALLOWED_EMAIL_DOMAINS {
        INTEGER id PK
        INTEGER building_id FK
        TEXT domain
        INTEGER active
        INTEGER created_by_user_id FK
        TEXT created_at
        INTEGER deactivated_by_user_id FK
        TEXT deactivated_at
    }

    FAULTS {
        INTEGER id PK
        TEXT title
        TEXT description
        TEXT location
        TEXT status
        INTEGER submitted_by FK
        INTEGER closed_by FK
        TEXT date_created
        TEXT date_closed
    }
```

Back up the database before deploying any schema change, install the updated requirements, deploy the code, and start one application instance to perform the migration before scaling out.

## Development and verification

```powershell
python -m pytest
npm run build
git diff --check
```

Frontend source is in `app/static/src/application.scss`. `npm run build` compiles CSS and copies GOV.UK Frontend JavaScript from `node_modules`.

## Privacy and security decisions

Email addresses are personal data. They are not placed in URLs or shown in general fault listings. Only an administrator for the same building can browse an account email. Password hashes are never rendered. SQL values are parameterised, CSRF remains globally enabled, unsafe post-login redirect targets are rejected, and login errors do not disclose whether an account exists.

## Security limitations

Before production use, consider organisational single sign-on, multi-factor authentication, email ownership confirmation, account recovery, account deactivation, central audit logging, shared rate-limit storage, penetration testing, formal accessibility testing, user research and a service assessment.
