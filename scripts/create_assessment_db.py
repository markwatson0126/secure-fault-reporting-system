import argparse
import os
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

from werkzeug.security import generate_password_hash


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app import create_app
from app.db import get_db, initialise_database
from app.validation import validate_email_address


DEFAULT_OUTPUT = (
    PROJECT_ROOT
    / "assessment_artifacts"
    / "secure_fault_reporting_assessment.db"
)
PROTECTED_DATABASE = (PROJECT_ROOT / "instance" / "app.db").resolve()
ASSESSMENT_PASSWORD = "AssessmentDemo!2026"
INITIAL_ADMIN_PREFIX = "INITIAL_ADMIN_"
FIXED_DOMAIN_CREATED_AT = "2026-01-05 09:00:00"

USERS = (
    ("Alex", "Morgan", "alex.morgan@glasgow.example.com", "Glasgow", "admin"),
    ("Priya", "Shah", "priya.shah@glasgow.example.com", "Glasgow", "user"),
    ("Jamie", "Brown", "jamie.brown@glasgow.example.com", "Glasgow", "user"),
    ("Taylor", "Reid", "taylor.reid@edinburgh.example.com", "Edinburgh", "admin"),
    ("Morgan", "Lee", "morgan.lee@edinburgh.example.com", "Edinburgh", "user"),
    ("Sam", "Patel", "sam.patel@edinburgh.example.com", "Edinburgh", "user"),
)

ASSESSMENT_DOMAINS = (
    ("Glasgow", "glasgow.example.com", "alex.morgan@glasgow.example.com"),
    ("Edinburgh", "edinburgh.example.com", "taylor.reid@edinburgh.example.com"),
)

FAULTS = (
    (
        "Lift call button not responding",
        "The ground-floor lift call button does not illuminate when pressed.",
        "Glasgow",
        "Open",
        "priya.shah@glasgow.example.com",
        None,
        "2026-02-03 09:15:00",
        None,
    ),
    (
        "Meeting room light flickering",
        "The ceiling light in meeting room G-12 flickers during use.",
        "Glasgow",
        "Closed",
        "jamie.brown@glasgow.example.com",
        "alex.morgan@glasgow.example.com",
        "2026-02-05 11:30:00",
        "2026-02-06 14:20:00",
    ),
    (
        "Kitchen tap dripping",
        "The cold-water tap in the third-floor kitchen continues to drip.",
        "Glasgow",
        "Open",
        "jamie.brown@glasgow.example.com",
        None,
        "2026-02-10 08:45:00",
        None,
    ),
    (
        "Damaged floor tile near reception",
        "One floor tile beside the reception seating area is cracked.",
        "Glasgow",
        "Closed",
        "priya.shah@glasgow.example.com",
        "alex.morgan@glasgow.example.com",
        "2026-02-12 15:10:00",
        "2026-02-14 10:05:00",
    ),
    (
        "Ventilation noise in printer room",
        "The ventilation unit in the first-floor printer room is unusually loud.",
        "Edinburgh",
        "Open",
        "morgan.lee@edinburgh.example.com",
        None,
        "2026-03-02 10:25:00",
        None,
    ),
    (
        "Loose handrail on second floor",
        "The corridor handrail near the second-floor stairs is loose.",
        "Edinburgh",
        "Closed",
        "sam.patel@edinburgh.example.com",
        "taylor.reid@edinburgh.example.com",
        "2026-03-04 13:40:00",
        "2026-03-05 16:15:00",
    ),
    (
        "Water cooler not dispensing",
        "The water cooler beside the shared workspace is not dispensing water.",
        "Edinburgh",
        "Open",
        "sam.patel@edinburgh.example.com",
        None,
        "2026-03-09 09:05:00",
        None,
    ),
    (
        "Loose desk power-socket cover",
        "A power-socket cover on a shared desk is loose but still attached.",
        "Edinburgh",
        "Closed",
        "morgan.lee@edinburgh.example.com",
        "taylor.reid@edinburgh.example.com",
        "2026-03-11 14:35:00",
        "2026-03-12 11:50:00",
    ),
)

EXPECTED_COUNTS = {
    "buildings": 14,
    "users": 6,
    "allowed_email_domains": 16,
    "faults": 8,
}


@contextmanager
def _without_initial_admin_environment():
    original = {
        key: value
        for key, value in os.environ.items()
        if key.upper().startswith(INITIAL_ADMIN_PREFIX)
    }
    for key in list(os.environ):
        if key.upper().startswith(INITIAL_ADMIN_PREFIX):
            del os.environ[key]
    try:
        yield
    finally:
        for key in list(os.environ):
            if key.upper().startswith(INITIAL_ADMIN_PREFIX):
                del os.environ[key]
        os.environ.update(original)


def _table_counts(db):
    return {
        "buildings": db.execute(
            "SELECT COUNT(*) FROM buildings"
        ).fetchone()[0],
        "users": db.execute(
            "SELECT COUNT(*) FROM users"
        ).fetchone()[0],
        "allowed_email_domains": db.execute(
            "SELECT COUNT(*) FROM allowed_email_domains"
        ).fetchone()[0],
        "faults": db.execute(
            "SELECT COUNT(*) FROM faults"
        ).fetchone()[0],
    }


def _insert_assessment_data(db):
    building_rows = db.execute(
        "SELECT id, name FROM buildings WHERE name IN (?, ?)",
        ("Glasgow", "Edinburgh"),
    ).fetchall()
    building_ids = {row["name"]: row["id"] for row in building_rows}
    if set(building_ids) != {"Glasgow", "Edinburgh"}:
        raise RuntimeError("Required assessment buildings were not seeded")

    user_ids = {}
    for first_name, last_name, email, building, role in USERS:
        normalised_email, validation_error = validate_email_address(email)
        if validation_error or normalised_email != email:
            raise RuntimeError(f"Assessment email is not valid: {email}")
        cursor = db.execute(
            """
            INSERT INTO users
                (email, password_hash, first_name, last_name, building_id, role)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                email,
                generate_password_hash(ASSESSMENT_PASSWORD),
                first_name,
                last_name,
                building_ids[building],
                role,
            ),
        )
        user_ids[email] = cursor.lastrowid

    for building, domain, created_by_email in ASSESSMENT_DOMAINS:
        db.execute(
            """
            INSERT INTO allowed_email_domains
                (building_id, domain, active, created_by_user_id, created_at)
            VALUES (?, ?, 1, ?, ?)
            """,
            (
                building_ids[building],
                domain,
                user_ids[created_by_email],
                FIXED_DOMAIN_CREATED_AT,
            ),
        )

    for (
        title,
        description,
        building,
        status,
        submitted_by_email,
        closed_by_email,
        date_created,
        date_closed,
    ) in FAULTS:
        db.execute(
            """
            INSERT INTO faults
                (title, description, building_id, status, submitted_by,
                 closed_by, date_created, date_closed)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                title,
                description,
                building_ids[building],
                status,
                user_ids[submitted_by_email],
                user_ids[closed_by_email] if closed_by_email else None,
                date_created,
                date_closed,
            ),
        )


def _build_temporary_database(database_path):
    with _without_initial_admin_environment():
        app = create_app(
            {
                "TESTING": True,
                "SECRET_KEY": "assessment-generator-only",
                "DATABASE": str(database_path),
                "RATELIMIT_ENABLED": False,
            }
        )
        with app.app_context():
            initialise_database()
            db = get_db()
            try:
                db.execute("BEGIN")
                _insert_assessment_data(db)
                violations = db.execute("PRAGMA foreign_key_check").fetchall()
                if violations:
                    raise RuntimeError(
                        "Assessment database failed foreign-key validation"
                    )
                counts = _table_counts(db)
                if counts != EXPECTED_COUNTS:
                    raise RuntimeError(
                        f"Assessment database record counts are incorrect: {counts}"
                    )
                db.commit()
            except Exception:
                db.rollback()
                raise
    return counts


def _remove_temporary_database(database_path):
    for suffix in ("", "-journal", "-wal", "-shm"):
        Path(f"{database_path}{suffix}").unlink(missing_ok=True)


def generate_assessment_database(output=DEFAULT_OUTPUT, force=False):
    supplied_output_path = Path(output).expanduser()
    if supplied_output_path.is_symlink():
        raise RuntimeError("Refusing to replace a symbolic-link output path")
    output_path = supplied_output_path.resolve()
    if output_path == PROTECTED_DATABASE:
        raise RuntimeError("Refusing to replace instance/app.db")
    if output_path.exists() and output_path.is_dir():
        raise RuntimeError(f"Output path is a directory: {output_path}")
    if output_path.exists() and not force:
        raise RuntimeError(
            f"Output database already exists: {output_path}. Use --force to replace it."
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=".adb-", suffix=".db", dir=output_path.parent
    )
    os.close(descriptor)
    temporary_database = Path(temporary_name)
    try:
        counts = _build_temporary_database(temporary_database)
        os.replace(temporary_database, output_path)
    finally:
        _remove_temporary_database(temporary_database)
    return output_path, counts


def _argument_parser():
    parser = argparse.ArgumentParser(
        description="Create a sanitised fictional assessment SQLite database."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"Output database path (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace an existing output database.",
    )
    return parser


def main(argv=None):
    arguments = _argument_parser().parse_args(argv)
    try:
        output_path, counts = generate_assessment_database(
            arguments.output, arguments.force
        )
    except Exception as error:
        print(f"Assessment database generation failed: {error}", file=sys.stderr)
        return 1

    print(f"Assessment database created: {output_path}")
    print(f"Buildings: {counts['buildings']}")
    print(f"Users: {counts['users']}")
    print(f"Allowed email domains: {counts['allowed_email_domains']}")
    print(f"Faults: {counts['faults']}")
    print("WARNING: FICTIONAL ASSESSMENT DATA ONLY. NO PRODUCTION DATA.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
