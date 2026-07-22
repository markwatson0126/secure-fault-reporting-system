import sqlite3
from html.parser import HTMLParser

import pytest
from werkzeug.security import check_password_hash, generate_password_hash

from app import create_app
from app.db import BUILDINGS, FALLBACK_BUILDING, get_db


class CSRFTokenParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.token = None

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "input" and attributes.get("name") == "csrf_token" and self.token is None:
            self.token = attributes.get("value")


def csrf(client, path):
    response = client.get(path)
    assert response.status_code == 200
    parser = CSRFTokenParser()
    parser.feed(response.get_data(as_text=True))
    assert parser.token
    return parser.token


@pytest.fixture
def app(tmp_path, monkeypatch):
    for name in (
        "INITIAL_ADMIN_EMAIL", "INITIAL_ADMIN_PASSWORD", "INITIAL_ADMIN_FIRST_NAME",
        "INITIAL_ADMIN_LAST_NAME", "INITIAL_ADMIN_BUILDING",
    ):
        monkeypatch.delenv(name, raising=False)
    app = create_app({
        "TESTING": True,
        "SECRET_KEY": "test-only-secret",
        "DATABASE": str(tmp_path / "test.db"),
        "RATELIMIT_ENABLED": False,
    })
    with app.test_client() as client:
        client.get("/login")
    return app


@pytest.fixture
def client(app):
    return app.test_client()


def building_id(app, name="Birmingham"):
    with app.app_context():
        return get_db().execute(
            "SELECT id FROM buildings WHERE name = ?", (name,)
        ).fetchone()[0]


def add_user(app, email, role="user", building="Birmingham", password="A distinct valid passphrase"):
    with app.app_context():
        db = get_db()
        cursor = db.execute(
            """
            INSERT INTO users (email, password_hash, first_name, last_name, building_id, role)
            SELECT ?, ?, 'Test', 'Person', id, ? FROM buildings WHERE name = ?
            """,
            (email.lower(), generate_password_hash(password), role, building),
        )
        db.commit()
        return cursor.lastrowid


def login(client, email, password="A distinct valid passphrase"):
    return client.post("/login", data={
        "email": email, "password": password, "csrf_token": csrf(client, "/login"),
    })


def registration_data(app, **overrides):
    data = {
        "email": "new.person@hmrc.gov.uk",
        "first_name": "New",
        "last_name": "Person",
        "building_id": str(building_id(app)),
        "password": "correct horse battery staple",
    }
    data.update(overrides)
    return data


def register(client, **overrides):
    data = registration_data(client.application, **overrides)
    data["csrf_token"] = csrf(client, "/register")
    return client.post("/register", data=data)


def test_secret_key_is_required_outside_testing(tmp_path, monkeypatch):
    monkeypatch.delenv("SECRET_KEY", raising=False)
    with pytest.raises(RuntimeError, match="SECRET_KEY must be configured"):
        create_app({
            "TESTING": False,
            "DATABASE": str(tmp_path / "missing-secret.db"),
            "RATELIMIT_ENABLED": False,
        })


def test_secret_key_from_application_config_is_accepted(tmp_path, monkeypatch):
    monkeypatch.delenv("SECRET_KEY", raising=False)
    configured_app = create_app({
        "TESTING": False,
        "SECRET_KEY": "application-config-secret",
        "DATABASE": str(tmp_path / "configured-secret.db"),
        "RATELIMIT_ENABLED": False,
    })
    assert configured_app.config["SECRET_KEY"] == "application-config-secret"


def test_testing_app_does_not_require_environment_secret(tmp_path, monkeypatch):
    monkeypatch.delenv("SECRET_KEY", raising=False)
    testing_app = create_app({
        "TESTING": True,
        "DATABASE": str(tmp_path / "testing-without-secret.db"),
        "RATELIMIT_ENABLED": False,
    })
    assert testing_app.config["TESTING"] is True
    assert testing_app.config["SECRET_KEY"] is None


def test_environment_secret_key_is_still_supported(tmp_path, monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "environment-secret")
    configured_app = create_app({
        "TESTING": False,
        "DATABASE": str(tmp_path / "environment-secret.db"),
        "RATELIMIT_ENABLED": False,
    })
    assert configured_app.config["SECRET_KEY"] == "environment-secret"


def test_schema_and_seed_are_idempotent(app):
    with app.app_context():
        from app.db import initialise_database
        initialise_database()
        initialise_database()
        db = get_db()
        assert [row[0] for row in db.execute("SELECT name FROM buildings ORDER BY name")] == sorted(BUILDINGS)
        assert db.execute("SELECT COUNT(*) FROM buildings").fetchone()[0] == 15
        assert db.execute("SELECT COUNT(*) FROM allowed_email_domains").fetchone()[0] == 14
        assert db.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert db.execute(
            "SELECT COUNT(*) FROM allowed_email_domains d JOIN buildings b ON b.id=d.building_id WHERE b.name=?",
            (FALLBACK_BUILDING,),
        ).fetchone()[0] == 0


def test_database_case_insensitive_uniqueness_and_constraints(app):
    add_user(app, "case@hmrc.gov.uk")
    with app.app_context():
        db = get_db()
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO users(email,password_hash,first_name,last_name,building_id,role) VALUES(?,?,?,?,?,?)",
                ("CASE@HMRC.GOV.UK", "hash", "A", "B", building_id(app), "user"),
            )
        db.rollback()
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("INSERT INTO buildings(name,active) VALUES('birmingham',1)")
        db.rollback()


def test_valid_registration_normalises_email_and_hard_codes_user_role(client):
    password = "lowercase words only are accepted"
    response = register(client, email="  New.Person@HMRC.GOV.UK  ", password=password, role="admin")
    assert response.status_code == 302
    with client.application.app_context():
        user = get_db().execute("SELECT * FROM users WHERE email=?", ("new.person@hmrc.gov.uk",)).fetchone()
        assert user["role"] == "user"
        assert user["building_id"] == building_id(client.application)
        assert user["password_hash"] != password
        assert check_password_hash(user["password_hash"], password)
    assert b"Account created. You can now sign in." in client.get("/login").data


@pytest.mark.parametrize("email,message", [
    ("", b"Enter an email address"),
    ("   ", b"Enter an email address"),
    ("not-an-email", b"Enter an email address in the correct format, like name@example.com"),
    ("a" * 244 + "@hmrc.gov.uk", b"Email address must be 254 characters or fewer"),
])
def test_registration_email_validation(client, email, message):
    response = register(client, email=email)
    assert response.status_code == 200
    assert message in response.data
    assert b"<title>Error:" in response.data


def test_mixed_case_duplicate_is_rejected(client):
    assert register(client, email="duplicate@hmrc.gov.uk").status_code == 302
    response = register(client, email="DUPLICATE@HMRC.GOV.UK")
    assert b"An account already exists for this email address" in response.data


@pytest.mark.parametrize("email", [
    "person@hmrc.gov.uk.example.com", "person@fakehmrc.gov.uk", "person@digital.hmrc.gov.uk",
    "person@unlisted.example",
])
def test_domain_matching_is_exact(client, email):
    response = register(client, email=email)
    assert response.status_code == 422
    assert b"You cannot create an account" in response.data
    assert b"accepted domains" not in response.data


def test_domain_comparison_is_case_insensitive(client):
    assert register(client, email="PERSON@HMRC.GOV.UK").status_code == 302


def test_registration_and_login_share_international_domain_normalisation(client):
    password = "A valid international domain passphrase"
    with client.application.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO allowed_email_domains (building_id, domain, active)
            VALUES (?, 'bücher.de', 1)
            """,
            (building_id(client.application),),
        )
        db.commit()

    assert register(
        client, email="Person@xn--bcher-kva.de", password=password
    ).status_code == 302
    with client.application.app_context():
        stored = get_db().execute(
            "SELECT email FROM users WHERE email = ?",
            ("person@bücher.de",),
        ).fetchone()
        assert stored["email"] == "person@bücher.de"

    assert login(
        client, "PERSON@XN--BCHER-KVA.DE", password
    ).status_code == 302


def test_inactive_domain_and_fallback_building_are_ineligible(client):
    with client.application.app_context():
        db = get_db()
        db.execute("UPDATE allowed_email_domains SET active=0 WHERE domain='hmrc.gov.uk' AND building_id=?", (building_id(client.application),))
        fallback = db.execute("SELECT id FROM buildings WHERE name=?", (FALLBACK_BUILDING,)).fetchone()[0]
        db.commit()
    assert register(client).status_code == 422
    assert register(client, email="other@example.com", building_id=str(fallback)).status_code == 422


def test_active_admin_added_domain_allows_registration(client):
    with client.application.app_context():
        db = get_db()
        db.execute("INSERT INTO allowed_email_domains(building_id,domain,active) VALUES(?, 'college.ac.uk', 1)", (building_id(client.application),))
        db.commit()
    assert register(client, email="tutor@COLLEGE.AC.UK").status_code == 302


@pytest.mark.parametrize("value,message", [
    ("", b"Select a building or work location"),
    ("999999", b"Select a valid building or work location"),
])
def test_building_is_validated(client, value, message):
    response = register(client, building_id=value)
    assert response.status_code == 200
    assert message in response.data


def test_inactive_building_is_rejected(client):
    with client.application.app_context():
        db = get_db(); db.execute("UPDATE buildings SET active=0 WHERE name='Birmingham'"); db.commit()
    assert b"Select a valid building or work location" in register(client).data


@pytest.mark.parametrize("password,message", [
    ("", b"Enter a password"), ("short words", b"Password must be at least 12 characters"),
    ("PASSWORD123", b"Choose a password that is not commonly used"),
    ("abcabcabcabc", b"Choose a password that is not commonly used"),
])
def test_shared_password_policy(client, password, message):
    response = register(client, password=password)
    assert message in response.data
    assert password.encode() not in response.data if password else True


def test_names_support_unicode_and_are_limited_to_100(client):
    assert register(client, first_name="Łukasz 李", last_name="O’Connor-Silva").status_code == 302
    response = register(client, email="second@hmrc.gov.uk", first_name="x" * 101)
    assert b"First name must be 100 characters or fewer" in response.data


def test_account_markup_and_secret_preservation(client):
    page = client.get("/register").data
    login_page = client.get("/login").data
    assert b'type="email"' in page and b'autocomplete="email"' in page and b'maxlength="254"' in page
    for rendered_page in (page, login_page):
        assert b'class="govuk-form-group govuk-password-input"' in rendered_page
        assert b'data-module="govuk-password-input"' in rendered_page
        assert b'class="govuk-input__wrapper govuk-password-input__wrapper"' in rendered_page
        assert b'aria-controls="password" aria-label="Show password"' in rendered_page
    assert b'autocomplete="new-password"' in page and b'autocapitalize="none"' in page
    assert b"confirm_password" not in page
    assert b'<option value="">Select a building or work location</option>' in page
    secret = "This secret must never return"
    response = register(client, email="bad", first_name="Anne-Marie", password=secret)
    assert b"Anne-Marie" in response.data and secret.encode() not in response.data
    assert response.data.index(b"govuk-error-summary") < response.data.index(b"<h1")
    password_error = register(client, password="short")
    assert b'aria-describedby="password-hint password-error"' in password_error.data


def test_role_error_is_associated_with_role_select(client):
    add_user(client.application, "admin@hmrc.gov.uk", "admin")
    login(client, "admin@hmrc.gov.uk")
    data = registration_data(
        client.application,
        email="role-error@hmrc.gov.uk",
        role="invalid-role",
        csrf_token=csrf(client, "/add_user"),
    )
    response = client.post("/add_user", data=data)
    assert b'id="role-error"' in response.data
    assert b'id="role" name="role" aria-describedby="role-error"' in response.data


def test_csrf_is_required(client):
    assert client.post("/register", data=registration_data(client.application)).status_code == 400
    assert client.post("/login", data={"email": "x", "password": "y"}).status_code == 400


def test_login_is_case_insensitive_generic_and_preserves_only_email(client):
    add_user(client.application, "person@hmrc.gov.uk")
    assert login(client, " PERSON@HMRC.GOV.UK ").status_code == 302
    client.get("/logout")
    unknown = login(client, "unknown@hmrc.gov.uk")
    malformed = login(client, "not-an-email")
    wrong = login(client, "person@hmrc.gov.uk", "Wrong secret phrase")
    message = b"Enter the correct email address and password"
    assert message in unknown.data and message in malformed.data and message in wrong.data
    assert b'value="unknown@hmrc.gov.uk"' in unknown.data
    assert b'value="not-an-email"' in malformed.data
    assert b'value="person@hmrc.gov.uk"' in wrong.data
    assert b"Wrong secret phrase" not in wrong.data


def test_login_rejects_unsafe_next(client):
    add_user(client.application, "person@hmrc.gov.uk")
    response = client.post("/login?next=https://evil.example", data={
        "email": "person@hmrc.gov.uk", "password": "A distinct valid passphrase",
        "csrf_token": csrf(client, "/login?next=https://evil.example"),
    })
    assert response.headers["Location"].endswith("/")


def test_login_post_is_throttled_but_get_is_not(tmp_path, monkeypatch):
    app = create_app({"TESTING": True, "SECRET_KEY": "x", "DATABASE": str(tmp_path / "rate.db"), "LOGIN_RATE_LIMIT": "2 per minute", "RATELIMIT_ENABLED": True, "RATELIMIT_KEY_PREFIX": "isolated-rate-test", "RATELIMIT_HEADERS_ENABLED": True})
    client = app.test_client(); token = csrf(client, "/login")
    responses = [client.post("/login", data={"email": "x@example.com", "password": "wrong", "csrf_token": token}) for _ in range(4)]
    assert responses[0].status_code == 200
    response = next(item for item in responses if item.status_code == 429)
    assert response.status_code == 429 and b"Too many sign-in attempts" in response.data
    assert response.headers.get("Retry-After")
    assert client.get("/login").status_code == 200


def test_admin_user_list_is_building_scoped(client):
    add_user(client.application, "admin@hmrc.gov.uk", "admin")
    add_user(client.application, "local@hmrc.gov.uk")
    add_user(client.application, "remote@hmrc.gov.uk", building="Leeds")
    login(client, "admin@hmrc.gov.uk")
    response = client.get("/admin/users")
    assert b"local@hmrc.gov.uk" in response.data
    assert b"remote@hmrc.gov.uk" not in response.data
    assert b"password_hash" not in response.data


def test_regular_user_cannot_access_admin_routes(client):
    add_user(client.application, "user@hmrc.gov.uk")
    login(client, "user@hmrc.gov.uk")
    for path in ("/admin/users", "/admin/domains", "/add_user"):
        assert client.get(path).status_code == 403


def test_admin_can_create_scoped_user_but_not_cross_building(client):
    add_user(client.application, "admin@hmrc.gov.uk", "admin")
    login(client, "admin@hmrc.gov.uk")
    token = csrf(client, "/add_user")
    leeds = building_id(client.application, "Leeds")
    data = registration_data(client.application, email="created@hmrc.gov.uk", role="admin", csrf_token=token)
    data["building_id"] = str(leeds)
    response = client.post("/add_user", data=data)
    assert b"Select a valid building or work location" in response.data
    data.update(email="created@hmrc.gov.uk", building_id=str(building_id(client.application)), csrf_token=csrf(client, "/add_user"))
    assert client.post("/add_user", data=data).status_code == 302
    with client.application.app_context():
        row = get_db().execute("SELECT role,building_id FROM users WHERE email='created@hmrc.gov.uk'").fetchone()
        assert tuple(row) == ("admin", building_id(client.application))


@pytest.mark.parametrize("domain", ["@hmrc.gov.uk", "user@hmrc.gov.uk", "https://hmrc.gov.uk", "hmrc.gov.uk/path", "*.hmrc.gov.uk", "hmrc.gov.uk:443", "   "])
def test_domain_admin_rejects_invalid_values(client, domain):
    add_user(client.application, "admin@hmrc.gov.uk", "admin"); login(client, "admin@hmrc.gov.uk")
    response = client.post("/admin/domains/add", data={"domain": domain, "csrf_token": csrf(client, "/admin/domains/add")})
    expected = b"Enter an email domain" if not domain.strip() else b"Enter an email domain in the correct format, like hmrc.gov.uk"
    assert expected in response.data


def test_admin_domain_lifecycle_audit_and_cross_scope(client):
    admin_id = add_user(client.application, "admin@hmrc.gov.uk", "admin"); login(client, "admin@hmrc.gov.uk")
    response = client.post("/admin/domains/add", data={"domain": "College.AC.UK", "csrf_token": csrf(client, "/admin/domains/add")})
    assert response.status_code == 302
    with client.application.app_context():
        db = get_db(); row = db.execute("SELECT * FROM allowed_email_domains WHERE domain='college.ac.uk'").fetchone(); domain_id = row["id"]
        assert row["created_by_user_id"] == admin_id and row["created_at"]
        other = db.execute("INSERT INTO allowed_email_domains(building_id,domain,active) VALUES(?, 'other.example', 1)", (building_id(client.application, "Leeds"),)).lastrowid; db.commit()
    duplicate = client.post("/admin/domains/add", data={"domain": "COLLEGE.ac.uk", "csrf_token": csrf(client, "/admin/domains/add")})
    assert b"This email domain already exists for this building" in duplicate.data
    token = csrf(client, "/admin/domains")
    assert client.post(f"/admin/domains/{domain_id}/deactivate", data={"csrf_token": token}).status_code == 302
    with client.application.app_context():
        row = get_db().execute("SELECT * FROM allowed_email_domains WHERE id=?", (domain_id,)).fetchone()
        assert row["active"] == 0 and row["deactivated_by_user_id"] == admin_id and row["deactivated_at"]
    assert client.post(f"/admin/domains/{domain_id}/activate", data={"csrf_token": token}).status_code == 302
    with client.application.app_context():
        row = get_db().execute(
            "SELECT * FROM allowed_email_domains WHERE id=?", (domain_id,)
        ).fetchone()
        assert row["active"] == 1
        assert row["deactivated_by_user_id"] is None
        assert row["deactivated_at"] is None
    assert client.post(f"/admin/domains/{other}/deactivate", data={"csrf_token": token}).status_code == 403
    assert client.post("/admin/domains/999999/deactivate", data={"csrf_token": token}).status_code == 404


def test_deactivating_domain_does_not_disable_existing_user(client):
    add_user(client.application, "person@hmrc.gov.uk")
    with client.application.app_context():
        db=get_db(); db.execute("UPDATE allowed_email_domains SET active=0 WHERE building_id=?", (building_id(client.application),)); db.commit()
    assert login(client, "person@hmrc.gov.uk").status_code == 302


def test_fault_list_displays_name_not_email(client):
    user_id = add_user(client.application, "private@hmrc.gov.uk")
    with client.application.app_context():
        db=get_db(); db.execute("INSERT INTO faults(title,description,location,status,submitted_by) VALUES('Leak','Pipe','Floor 1','Open',?)", (user_id,)); db.commit()
    login(client, "private@hmrc.gov.uk")
    response = client.get("/")
    assert b"Test Person" in response.data and b"private@hmrc.gov.uk" not in response.data


def test_fault_form_uses_required_browser_validation(client):
    add_user(client.application, "reporter@hmrc.gov.uk")
    login(client, "reporter@hmrc.gov.uk")
    response = client.get("/")
    fault_form = response.data.split(b'action="/submit"', 1)[1].split(
        b"</form>", 1
    )[0]
    assert b"novalidate" not in fault_form
    assert b'id="title" name="title" type="text" required' in fault_form
    assert b'id="description" name="description" rows="5" required' in fault_form
    assert b'id="location" name="location" type="text" required' in fault_form


def test_govuk_assets_load(client):
    assert client.get("/static/css/application.css").status_code == 200
    assert client.get("/static/js/govuk-frontend.min.js").status_code == 200
