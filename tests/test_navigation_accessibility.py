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
    parser = CSRFTokenParser()
    parser.feed(response.get_data(as_text=True))
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
        "SECRET_KEY": "navigation-test-secret",
        "DATABASE": str(tmp_path / "navigation.db"),
        "RATELIMIT_ENABLED": False,
    })
    with app.test_client() as client:
        client.get("/login")
    return app


@pytest.fixture
def client(app):
    return app.test_client()


def add_user(app, email, role):
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO users
                (email, password_hash, first_name, last_name, building_id, role)
            SELECT ?, ?, 'Navigation', 'Tester', id, ?
            FROM buildings WHERE name = 'Birmingham'
            """,
            (email, generate_password_hash("A distinct valid passphrase"), role),
        )
        db.commit()


def login(client, email):
    return client.post("/login", data={
        "email": email,
        "password": "A distinct valid passphrase",
        "csrf_token": csrf(client, "/login"),
    })


def test_standard_user_navigation_omits_redundant_faults_link(client):
    add_user(client.application, "user@hmrc.gov.uk", "user")
    login(client, "user@hmrc.gov.uk")

    page = client.get("/").get_data(as_text=True)
    account_bar = page.split('aria-label="Account and administration"', 1)[1].split("</nav>", 1)[0]

    assert ">Faults</a>" not in account_bar
    assert ">Users</a>" not in account_bar
    assert ">Email domains</a>" not in account_bar
    assert ">Sign out</a>" in account_bar


def test_admin_navigation_keeps_faults_and_admin_links(client):
    add_user(client.application, "admin@hmrc.gov.uk", "admin")
    login(client, "admin@hmrc.gov.uk")

    page = client.get("/").get_data(as_text=True)
    account_bar = page.split('aria-label="Account and administration"', 1)[1].split("</nav>", 1)[0]

    assert ">Faults</a>" in account_bar
    assert ">Users</a>" in account_bar
    assert ">Email domains</a>" in account_bar
    assert ">Sign out</a>" in account_bar
