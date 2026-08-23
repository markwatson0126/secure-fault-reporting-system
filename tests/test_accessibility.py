from html.parser import HTMLParser

import pytest
from werkzeug.security import generate_password_hash

from app import create_app
from app.db import get_db


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
        "SECRET_KEY": "accessibility-test-secret",
        "DATABASE": str(tmp_path / "accessibility.db"),
        "RATELIMIT_ENABLED": False,
    })
    with app.test_client() as test_client:
        test_client.get("/login")
    return app


@pytest.fixture
def client(app):
    return app.test_client()


def building_id(app, name="Birmingham"):
    with app.app_context():
        return get_db().execute(
            "SELECT id FROM buildings WHERE name = ?", (name,)
        ).fetchone()[0]


def add_user(app, email, role="user", building="Birmingham"):
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO users
                (email, password_hash, first_name, last_name, building_id, role)
            SELECT ?, ?, 'Accessibility', 'Tester', id, ?
            FROM buildings WHERE name = ?
            """,
            (
                email,
                generate_password_hash("A distinct valid passphrase"),
                role,
                building,
            ),
        )
        db.commit()


def login(client, email):
    return client.post("/login", data={
        "email": email,
        "password": "A distinct valid passphrase",
        "csrf_token": csrf(client, "/login"),
    })


def add_fault(app, title="Broken light"):
    with app.app_context():
        db = get_db()
        user = db.execute(
            "SELECT id, building_id FROM users ORDER BY id LIMIT 1"
        ).fetchone()
        cursor = db.execute(
            """
            INSERT INTO faults
                (title, description, building_id, status, submitted_by)
            VALUES (?, 'The light is not working', ?, 'Open', ?)
            """,
            (title, user["building_id"], user["id"]),
        )
        db.commit()
        return cursor.lastrowid


def test_primary_fault_form_is_visible_and_not_hidden_in_details(client):
    add_user(client.application, "reporter@hmrc.gov.uk")
    login(client, "reporter@hmrc.gov.uk")

    page = client.get("/").get_data(as_text=True)

    assert "<details" not in page
    assert "Report a fault" in page
    assert 'action="/submit"' in page
    assert 'id="title-hint"' in page
    assert 'id="description-hint"' in page


def test_fault_validation_has_error_summary_associations_and_preserves_input(client):
    add_user(client.application, "reporter@hmrc.gov.uk")
    login(client, "reporter@hmrc.gov.uk")

    response = client.post("/submit", data={
        "title": "  Broken lift  ",
        "description": "  Doors will not open  ",
        "building_id": "999999",
        "csrf_token": csrf(client, "/"),
    })
    page = response.get_data(as_text=True)

    assert response.status_code == 400
    assert "<title>Error:" in page
    assert "govuk-error-summary" in page
    assert 'href="#building_id"' in page
    assert 'id="building_id-error"' in page
    assert 'aria-describedby="building_id-error"' in page
    assert 'value="Broken lift"' in page
    assert "Doors will not open" in page


def test_successful_fault_report_displays_confirmation(client):
    add_user(client.application, "reporter@hmrc.gov.uk")
    login(client, "reporter@hmrc.gov.uk")

    response = client.post("/submit", data={
        "title": "Broken light",
        "description": "The light is not working",
        "building_id": str(building_id(client.application)),
        "csrf_token": csrf(client, "/"),
    }, follow_redirects=True)

    assert response.status_code == 200
    assert b"Fault reported." in response.data
    assert b"govuk-notification-banner--success" in response.data


def test_fault_actions_have_context_and_confirmation_pages(client):
    add_user(client.application, "admin@hmrc.gov.uk", role="admin")
    login(client, "admin@hmrc.gov.uk")
    fault_id = add_fault(client.application)

    page = client.get("/").get_data(as_text=True)
    assert "Mark as closed<span class=\"govuk-visually-hidden\">: Broken light</span>" in page
    assert "Delete fault<span class=\"govuk-visually-hidden\">: Broken light</span>" in page

    close_page = client.get(f"/close/{fault_id}/confirm").get_data(as_text=True)
    assert "Mark this fault as closed?" in close_page
    assert "Yes, mark as closed" in close_page
    assert "Cancel" in close_page

    delete_page = client.get(f"/delete/{fault_id}/confirm").get_data(as_text=True)
    assert "Delete this fault?" in delete_page
    assert "cannot be undone" in delete_page
    assert "Yes, delete fault" in delete_page


def test_close_confirmation_posts_and_announces_success(client):
    add_user(client.application, "reporter@hmrc.gov.uk")
    login(client, "reporter@hmrc.gov.uk")
    fault_id = add_fault(client.application)

    response = client.post(
        f"/close/{fault_id}",
        data={"csrf_token": csrf(client, f"/close/{fault_id}/confirm")},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Fault marked as closed." in response.data
    assert b"Closed" in response.data


def test_generic_header_and_navigation_landmark_are_present(client):
    add_user(client.application, "reporter@hmrc.gov.uk")
    login(client, "reporter@hmrc.gov.uk")

    page = client.get("/").get_data(as_text=True)

    assert 'class="govuk-generic-header"' in page
    assert 'class="govuk-generic-header__homepage-link"' in page
    assert 'aria-label="Account and administration"' in page
    assert 'href="#main-content" class="govuk-skip-link"' in page


def test_domain_table_has_caption_scoped_headers_and_contextual_actions(client):
    add_user(client.application, "admin@hmrc.gov.uk", role="admin")
    login(client, "admin@hmrc.gov.uk")

    page = client.get("/admin/domains").get_data(as_text=True)

    assert "Accepted email domains for Birmingham" in page
    assert page.count('scope="col"') == 4
    assert "Deactivate<span class=\"govuk-visually-hidden\"> hmrc.gov.uk</span>" in page


def test_accessibility_page_is_transparent_about_limits(client):
    response = client.get("/accessibility")

    assert response.status_code == 200
    assert b"does not claim full Web Content Accessibility Guidelines" in response.data
    assert b"has not yet had a formal accessibility audit" in response.data
    assert b"usability testing with disabled users" in response.data
