import importlib.util
import os
import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path

import pytest
from werkzeug.security import check_password_hash


PROJECT_ROOT = Path(__file__).resolve().parents[1]
GENERATOR_PATH = PROJECT_ROOT / "scripts" / "create_assessment_db.py"
ASSESSMENT_PASSWORD = "AssessmentDemo!2026"
EXPECTED_EMAILS = {
    "alex.morgan@glasgow.example.com",
    "priya.shah@glasgow.example.com",
    "jamie.brown@glasgow.example.com",
    "taylor.reid@edinburgh.example.com",
    "morgan.lee@edinburgh.example.com",
    "sam.patel@edinburgh.example.com",
}
EXPECTED_DOMAINS = {
    ("Edinburgh", "edinburgh.example.com"),
    ("Glasgow", "glasgow.example.com"),
}
EXPECTED_CREATED_DATES = {
    "2026-02-03 09:15:00",
    "2026-02-05 11:30:00",
    "2026-02-10 08:45:00",
    "2026-02-12 15:10:00",
    "2026-03-02 10:25:00",
    "2026-03-04 13:40:00",
    "2026-03-09 09:05:00",
    "2026-03-11 14:35:00",
}
EXPECTED_CLOSED_DATES = {
    "2026-02-06 14:20:00",
    "2026-02-14 10:05:00",
    "2026-03-05 16:15:00",
    "2026-03-12 11:50:00",
}


def run_generator(output, *, force=False, environment=None):
    command = [
        sys.executable,
        str(GENERATOR_PATH),
        "--output",
        str(output),
    ]
    if force:
        command.append("--force")
    return subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def load_generator_module():
    specification = importlib.util.spec_from_file_location(
        "assessment_database_generator", GENERATOR_PATH
    )
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def test_generator_creates_sanitised_assessment_database(tmp_path):
    output = tmp_path / "assessment.db"
    environment = os.environ.copy()
    environment.update(
        {
            "INITIAL_ADMIN_EMAIL": "unexpected.initial.admin@hmrc.gov.uk",
            "INITIAL_ADMIN_PASSWORD": "Unexpected initial administrator password",
            "INITIAL_ADMIN_FIRST_NAME": "Unexpected",
            "INITIAL_ADMIN_LAST_NAME": "Administrator",
            "INITIAL_ADMIN_BUILDING": "Glasgow",
            "INITIAL_ADMIN_FUTURE_SETTING": "must also be ignored",
        }
    )

    result = run_generator(output, environment=environment)

    assert result.returncode == 0, result.stderr
    assert output.is_file()
    assert f"Assessment database created: {output.resolve()}" in result.stdout
    assert "Buildings: 14" in result.stdout
    assert "Users: 6" in result.stdout
    assert "Allowed email domains: 16" in result.stdout
    assert "Faults: 8" in result.stdout
    assert "FICTIONAL ASSESSMENT DATA ONLY" in result.stdout

    with closing(sqlite3.connect(output)) as database:
        tables = {
            row[0]
            for row in database.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert {
            "buildings",
            "users",
            "allowed_email_domains",
            "faults",
        }.issubset(tables)

        users = database.execute(
            "SELECT email, password_hash FROM users"
        ).fetchall()
        assert {row[0] for row in users} == EXPECTED_EMAILS
        assert len(users) == 6
        for _, password_hash in users:
            assert password_hash != ASSESSMENT_PASSWORD
            assert check_password_hash(password_hash, ASSESSMENT_PASSWORD)

        assert database.execute(
            "SELECT COUNT(*) FROM users WHERE email = ?",
            ("unexpected.initial.admin@hmrc.gov.uk",),
        ).fetchone()[0] == 0

        domains = {
            tuple(row)
            for row in database.execute(
                """
                SELECT buildings.name, allowed_email_domains.domain
                FROM allowed_email_domains
                JOIN buildings
                  ON buildings.id = allowed_email_domains.building_id
                WHERE allowed_email_domains.domain IN (?, ?)
                """,
                ("glasgow.example.com", "edinburgh.example.com"),
            )
        }
        assert domains == EXPECTED_DOMAINS

        assert database.execute(
            "SELECT COUNT(*) FROM faults"
        ).fetchone()[0] == 8
        faults_by_building = {
            tuple(row)
            for row in database.execute(
                """
                SELECT buildings.name, COUNT(*)
                FROM faults
                JOIN buildings ON buildings.id = faults.building_id
                GROUP BY buildings.name
                """
            )
        }
        assert faults_by_building == {("Edinburgh", 4), ("Glasgow", 4)}
        statuses = {
            tuple(row)
            for row in database.execute(
                "SELECT status, COUNT(*) FROM faults GROUP BY status"
            )
        }
        assert statuses == {("Closed", 4), ("Open", 4)}
        assert {
            row[0]
            for row in database.execute("SELECT date_created FROM faults")
        } == EXPECTED_CREATED_DATES
        assert {
            row[0]
            for row in database.execute(
                "SELECT date_closed FROM faults WHERE status = ?",
                ("Closed",),
            )
        } == EXPECTED_CLOSED_DATES
        assert database.execute(
            """
            SELECT COUNT(*) FROM faults
            WHERE status = ?
              AND (closed_by IS NULL OR date_closed IS NULL)
            """,
            ("Closed",),
        ).fetchone()[0] == 0
        assert database.execute(
            """
            SELECT COUNT(*) FROM faults
            WHERE status = ?
              AND (closed_by IS NOT NULL OR date_closed IS NOT NULL)
            """,
            ("Open",),
        ).fetchone()[0] == 0
        assert database.execute("PRAGMA foreign_key_check").fetchall() == []


def test_initial_admin_environment_is_restored_after_failure(monkeypatch):
    generator = load_generator_module()
    for key in list(os.environ):
        if key.upper().startswith("INITIAL_ADMIN_"):
            monkeypatch.delenv(key)
    original_values = {
        "INITIAL_ADMIN_EMAIL": "original@example.com",
        "INITIAL_ADMIN_PASSWORD": "original-password",
        "INITIAL_ADMIN_UNRECOGNISED": "original-future-value",
    }
    for key, value in original_values.items():
        monkeypatch.setenv(key, value)

    with pytest.raises(RuntimeError, match="deliberate test failure"):
        with generator._without_initial_admin_environment():
            assert not any(
                key.upper().startswith("INITIAL_ADMIN_")
                for key in os.environ
            )
            os.environ["INITIAL_ADMIN_ADDED_DURING_GENERATION"] = "temporary"
            raise RuntimeError("deliberate test failure")

    assert {
        key: value
        for key, value in os.environ.items()
        if key.upper().startswith("INITIAL_ADMIN_")
    } == original_values


def test_generator_refuses_to_overwrite_existing_database(tmp_path):
    output = tmp_path / "existing.db"
    with closing(sqlite3.connect(output)) as database:
        database.execute("CREATE TABLE sentinel (value TEXT)")
        database.execute(
            "INSERT INTO sentinel (value) VALUES (?)", ("preserve me",)
        )
        database.commit()
    original_content = output.read_bytes()

    result = run_generator(output)

    assert result.returncode != 0
    assert "already exists" in result.stderr
    assert output.read_bytes() == original_content


def test_generator_rejects_symbolic_link_output_path(tmp_path):
    target = tmp_path / "target.db"
    with closing(sqlite3.connect(target)) as database:
        database.execute("CREATE TABLE sentinel (value TEXT)")
        database.commit()
    output = tmp_path / "linked-output.db"
    try:
        output.symlink_to(target)
    except (NotImplementedError, OSError) as error:
        pytest.skip(f"Symbolic-link creation is unavailable: {error}")

    result = run_generator(output, force=True)

    assert result.returncode != 0
    assert "symbolic-link output path" in result.stderr
    assert output.is_symlink()
    with closing(sqlite3.connect(target)) as database:
        assert database.execute(
            """
            SELECT COUNT(*) FROM sqlite_master
            WHERE type = ? AND name = ?
            """,
            ("table", "sentinel"),
        ).fetchone()[0] == 1


def test_force_replaces_existing_generated_database(tmp_path):
    output = tmp_path / "replaceable.db"
    first_result = run_generator(output)
    assert first_result.returncode == 0, first_result.stderr

    with closing(sqlite3.connect(output)) as database:
        database.execute("CREATE TABLE sentinel (value TEXT)")
        database.execute(
            "INSERT INTO sentinel (value) VALUES (?)", ("remove me",)
        )
        database.commit()

    replacement_result = run_generator(output, force=True)

    assert replacement_result.returncode == 0, replacement_result.stderr
    assert "FICTIONAL ASSESSMENT DATA ONLY" in replacement_result.stdout
    with closing(sqlite3.connect(output)) as database:
        tables = {
            row[0]
            for row in database.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert "sentinel" not in tables
        assert database.execute(
            "SELECT COUNT(*) FROM users"
        ).fetchone()[0] == 6
        assert database.execute(
            "SELECT COUNT(*) FROM faults"
        ).fetchone()[0] == 8
        assert database.execute("PRAGMA foreign_key_check").fetchall() == []
