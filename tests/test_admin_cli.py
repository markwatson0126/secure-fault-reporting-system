from app import create_app
from app.db import get_db


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
