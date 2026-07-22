import os
import sqlite3

import click
from flask import current_app, g
from flask.cli import with_appcontext
from werkzeug.security import generate_password_hash

from .validation import validate_email_address, validate_name, validate_password


BUILDINGS = (
    "Belfast", "Birmingham", "Bristol", "Cardiff", "Croydon", "Edinburgh",
    "Glasgow", "Leeds", "Liverpool", "Manchester", "Newcastle", "Nottingham",
    "Portsmouth", "Stratford", "Other government or partner location",
)
HMRC_BUILDINGS = BUILDINGS[:-1]
FALLBACK_BUILDING = BUILDINGS[-1]


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def _schema_sql():
    project_root = os.path.abspath(os.path.join(current_app.root_path, ".."))
    with open(os.path.join(project_root, "schema.sql"), "r", encoding="utf-8") as file:
        return file.read()


def _apply_schema(db):
    for statement in _schema_sql().split(";"):
        if statement.strip():
            db.execute(statement)


def seed_buildings(db):
    db.executemany(
        "INSERT OR IGNORE INTO buildings (name, active) VALUES (?, 1)",
        ((name,) for name in BUILDINGS),
    )


def seed_reference_data(db):
    seed_buildings(db)
    db.executemany(
        """
        INSERT OR IGNORE INTO allowed_email_domains
            (building_id, domain, active, created_by_user_id)
        SELECT id, 'hmrc.gov.uk', 1, NULL FROM buildings WHERE name = ? COLLATE NOCASE
        """,
        ((name,) for name in HMRC_BUILDINGS),
    )


def _legacy_email(user_id, username, used):
    email, error = validate_email_address(username)
    if error or email in used:
        email = f"legacy-{user_id}@migration-placeholder.internal"
        suffix = 1
        while email in used:
            suffix += 1
            email = f"legacy-{user_id}-{suffix}@migration-placeholder.internal"
    used.add(email)
    return email


def migrate_legacy_database(db):
    columns = {row["name"] for row in db.execute("PRAGMA table_info(users)")}
    if not columns or "username" not in columns:
        return

    fallback_id = db.execute(
        "SELECT id FROM buildings WHERE name = ? COLLATE NOCASE", (FALLBACK_BUILDING,)
    ).fetchone()["id"]
    users = db.execute("SELECT * FROM users ORDER BY id").fetchall()
    faults = db.execute("SELECT * FROM faults ORDER BY id").fetchall()

    db.commit()
    db.execute("PRAGMA foreign_keys = OFF")
    try:
        db.execute("BEGIN IMMEDIATE")
        db.execute("ALTER TABLE users RENAME TO users_legacy")
        db.execute("ALTER TABLE faults RENAME TO faults_legacy")
        _apply_schema(db)
        used = set()
        for user in users:
            db.execute(
                """
                INSERT INTO users
                    (id, email, password_hash, first_name, last_name, building_id, role)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user["id"], _legacy_email(user["id"], user["username"], used),
                    user["password_hash"], user["first_name"], user["last_name"],
                    fallback_id, user["role"],
                ),
            )
        for fault in faults:
            db.execute(
                """
                INSERT INTO faults
                    (id, title, description, location, status, submitted_by,
                     closed_by, date_created, date_closed)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                tuple(fault),
            )
        db.execute("DROP TABLE faults_legacy")
        db.execute("DROP TABLE users_legacy")
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.execute("PRAGMA foreign_keys = ON")


def initialise_database():
    db = get_db()
    db.execute("CREATE TABLE IF NOT EXISTS buildings (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL COLLATE NOCASE UNIQUE, active INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)))")
    seed_buildings(db)
    db.commit()
    # Domains depend on users, so legacy users must be migrated before seeding domains.
    migrate_legacy_database(db)
    _apply_schema(db)
    seed_reference_data(db)
    _create_initial_admin(db)
    violations = db.execute("PRAGMA foreign_key_check").fetchall()
    if violations:
        db.rollback()
        raise RuntimeError("Database migration failed foreign-key validation")
    db.commit()


def active_buildings(db=None):
    database = db or get_db()
    return database.execute(
        "SELECT id, name FROM buildings WHERE active = 1 ORDER BY name COLLATE NOCASE"
    ).fetchall()


def find_active_building(value, db=None):
    database = db or get_db()
    try:
        building_id = int(value)
    except (TypeError, ValueError):
        return None
    return database.execute(
        "SELECT id, name FROM buildings WHERE id = ? AND active = 1", (building_id,)
    ).fetchone()


def _create_initial_admin(db):
    password = os.environ.get("INITIAL_ADMIN_PASSWORD")
    if not password:
        return
    email, email_error = validate_email_address(os.environ.get("INITIAL_ADMIN_EMAIL"))
    first_name, first_error = validate_name(os.environ.get("INITIAL_ADMIN_FIRST_NAME"), "First name")
    last_name, last_error = validate_name(os.environ.get("INITIAL_ADMIN_LAST_NAME"), "Last name")
    password_error = validate_password(password)
    building_name = os.environ.get("INITIAL_ADMIN_BUILDING")
    building = db.execute(
        "SELECT id FROM buildings WHERE name = ? COLLATE NOCASE AND active = 1",
        (building_name,),
    ).fetchone() if building_name else None
    if email_error or first_error or last_error or password_error or building is None:
        raise RuntimeError("Initial administrator configuration is invalid")
    existing = db.execute(
        "SELECT role, building_id FROM users WHERE email = ? COLLATE NOCASE", (email,)
    ).fetchone()
    if existing is not None:
        if existing["role"] == "admin" and existing["building_id"] == building["id"]:
            return
        raise RuntimeError("Initial administrator conflicts with an existing account")
    db.execute(
        """
        INSERT INTO users
            (email, password_hash, first_name, last_name, building_id, role)
        VALUES (?, ?, ?, ?, ?, 'admin')
        """,
        (email, generate_password_hash(password), first_name, last_name, building["id"]),
    )


def init_db_once():
    if not current_app.config.get("DB_INITIALISED"):
        initialise_database()
        current_app.config["DB_INITIALISED"] = True


@click.command("create-admin")
@click.option("--email", prompt=True)
@click.option("--first-name", prompt=True)
@click.option("--last-name", prompt=True)
@click.option("--building", prompt=True)
@with_appcontext
def create_admin_command(email, first_name, last_name, building):
    """Create an administrator without exposing the password in shell history."""
    password = click.prompt("Password", hide_input=True, confirmation_prompt=False)
    initialise_database()
    db = get_db()
    normalised_email, email_error = validate_email_address(email)
    first_name, first_error = validate_name(first_name, "First name")
    last_name, last_error = validate_name(last_name, "Last name")
    password_error = validate_password(password)
    building_row = db.execute(
        "SELECT id, name FROM buildings WHERE name = ? COLLATE NOCASE AND active = 1",
        (building.strip(),),
    ).fetchone()
    errors = [error for error in (email_error, first_error, last_error, password_error) if error]
    if building_row is None:
        errors.append("Select a valid building or work location")
    if normalised_email and db.execute(
        "SELECT 1 FROM users WHERE email = ? COLLATE NOCASE", (normalised_email,)
    ).fetchone():
        errors.append("An account already exists for this email address")
    if errors:
        raise click.ClickException(errors[0])
    try:
        db.execute(
            """
            INSERT INTO users (email, password_hash, first_name, last_name, building_id, role)
            VALUES (?, ?, ?, ?, ?, 'admin')
            """,
            (normalised_email, generate_password_hash(password), first_name, last_name, building_row["id"]),
        )
        db.commit()
    except sqlite3.IntegrityError:
        db.rollback()
        raise click.ClickException("An account already exists for this email address")
    click.echo(f"Administrator created for {normalised_email} at {building_row['name']}.")


def init_app(app):
    app.before_request(init_db_once)
    app.teardown_appcontext(close_db)
    app.cli.add_command(create_admin_command)
