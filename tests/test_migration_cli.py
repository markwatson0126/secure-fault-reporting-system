import re
import sqlite3

from werkzeug.security import check_password_hash, generate_password_hash

from app import create_app
from app.db import FALLBACK_BUILDING, get_db
from app.validation import validate_email_address


def test_legacy_migration_preserves_users_hashes_roles_ids_and_faults(tmp_path):
    path = tmp_path / "legacy.db"
    db = sqlite3.connect(path)
    db.executescript("""
        CREATE TABLE users(id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL, first_name TEXT NOT NULL, last_name TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('user','admin')));
        CREATE TABLE faults(id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL, description TEXT NOT NULL, location TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('Open','Closed')), submitted_by INTEGER NOT NULL, closed_by INTEGER, date_created TEXT DEFAULT CURRENT_TIMESTAMP, date_closed TEXT, FOREIGN KEY(submitted_by) REFERENCES users(id), FOREIGN KEY(closed_by) REFERENCES users(id));
    """)
    password_hash = generate_password_hash("migration password")
    db.execute("INSERT INTO users VALUES(7,'Person@Example.COM',?,'First','Person','admin')", (password_hash,))
    db.execute("INSERT INTO users VALUES(8,'old-name',?,'Old','Name','user')", (password_hash,))
    db.execute("INSERT INTO faults(id,title,description,location,status,submitted_by) VALUES(3,'Leak','Pipe','Floor 1','Open',7)")
    db.commit(); db.close()
    app = create_app({"TESTING": True, "SECRET_KEY": "x", "DATABASE": str(path), "RATELIMIT_ENABLED": False})
    client = app.test_client()
    login_page = client.get("/login")
    with app.app_context():
        db = get_db()
        users = db.execute("SELECT users.*,buildings.name building FROM users JOIN buildings ON buildings.id=users.building_id ORDER BY users.id").fetchall()
        assert [(u["id"], u["email"], u["role"], u["building"]) for u in users] == [
            (7, "person@example.com", "admin", FALLBACK_BUILDING),
            (8, "legacy-8@migration-placeholder.internal", "user", FALLBACK_BUILDING),
        ]
        assert all(u["password_hash"] == password_hash for u in users)
        generated_email = users[1]["email"]
        normalised_email, error = validate_email_address(generated_email)
        assert error is None
        assert normalised_email == generated_email
        assert check_password_hash(users[1]["password_hash"], "migration password")
        assert tuple(db.execute("SELECT id,submitted_by FROM faults").fetchone()) == (3, 7)
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []

    csrf_match = re.search(
        rb'name="csrf_token" value="([^"]+)"', login_page.data
    )
    assert csrf_match is not None
    response = client.post("/login", data={
        "email": generated_email,
        "password": "migration password",
        "csrf_token": csrf_match.group(1).decode(),
    })
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/")


def test_create_admin_cli_success_and_validation(tmp_path):
    app = create_app({"TESTING": True, "SECRET_KEY": "x", "DATABASE": str(tmp_path / "cli.db"), "RATELIMIT_ENABLED": False})
    runner = app.test_cli_runner()
    result = runner.invoke(args=["create-admin", "--email", "ADMIN@HMRC.GOV.UK", "--first-name", "Estate", "--last-name", "Admin", "--building", "Birmingham"], input="A secure administrator passphrase\n")
    assert result.exit_code == 0
    assert "admin@hmrc.gov.uk" in result.output and "Birmingham" in result.output
    assert "A secure administrator passphrase" not in result.output
    with app.app_context():
        row = get_db().execute("SELECT email,role FROM users").fetchone()
        assert tuple(row) == ("admin@hmrc.gov.uk", "admin")
    duplicate = runner.invoke(args=["create-admin", "--email", "admin@hmrc.gov.uk", "--first-name", "E", "--last-name", "A", "--building", "Birmingham"], input="Another secure passphrase\n")
    assert duplicate.exit_code != 0
    unknown = runner.invoke(args=["create-admin", "--email", "other@hmrc.gov.uk", "--first-name", "E", "--last-name", "A", "--building", "Unknown"], input="Another secure passphrase\n")
    assert unknown.exit_code != 0


def test_initial_admin_environment_uses_email_and_exact_building(tmp_path, monkeypatch):
    monkeypatch.setenv("INITIAL_ADMIN_EMAIL", "initial@hmrc.gov.uk")
    monkeypatch.setenv("INITIAL_ADMIN_PASSWORD", "Initial administrator passphrase")
    monkeypatch.setenv("INITIAL_ADMIN_FIRST_NAME", "Initial")
    monkeypatch.setenv("INITIAL_ADMIN_LAST_NAME", "Admin")
    monkeypatch.setenv("INITIAL_ADMIN_BUILDING", "Leeds")
    app = create_app({"TESTING": True, "SECRET_KEY": "x", "DATABASE": str(tmp_path / "initial.db"), "RATELIMIT_ENABLED": False})
    app.test_client().get("/login")
    with app.app_context():
        row = get_db().execute("SELECT users.email,buildings.name FROM users JOIN buildings ON buildings.id=users.building_id").fetchone()
        assert tuple(row) == ("initial@hmrc.gov.uk", "Leeds")
