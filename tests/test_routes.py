from html.parser import HTMLParser

import pytest

from app import create_app


class CSRFTokenParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.token = None

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == 'input' and attributes.get('name') == 'csrf_token':
            self.token = attributes.get('value')


def get_csrf_token(client, path):
    response = client.get(path)
    assert response.status_code == 200

    parser = CSRFTokenParser()
    parser.feed(response.get_data(as_text=True))
    assert parser.token is not None
    return parser.token


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("INITIAL_ADMIN_PASSWORD", "admin-test-password")

    app = create_app({
        "TESTING": True,
        "SECRET_KEY": "test-only-secret",
        "DATABASE": str(tmp_path / "test.db"),
    })

    with app.test_client() as client:
        yield client

def test_home_redirects_to_login(client):
    response = client.get('/')
    assert response.status_code == 302
    assert '/login' in response.headers['Location']

def test_login_page_loads(client):
    response = client.get('/login')
    assert response.status_code == 200
    assert b'Sign in' in response.data
    assert b'govuk-template' in response.data
    assert b'<input type="hidden" name="csrf_token"' in response.data


def test_login_without_csrf_token_is_rejected(client):
    response = client.post('/login', data={
        'username': 'admin',
        'password': 'admin-test-password',
    })
    assert response.status_code == 400


def test_admin_can_add_user(client):
    login_csrf_token = get_csrf_token(client, '/login')
    login_response = client.post('/login', data={
        'username': 'admin',
        'password': 'admin-test-password',
        'csrf_token': login_csrf_token,
    })
    assert login_response.status_code == 302

    add_user_csrf_token = get_csrf_token(client, '/')
    response = client.post('/add_user', data={
        'username': 'new-user',
        'password': 'new-user-password',
        'first_name': 'New',
        'last_name': 'User',
        'role': 'user',
        'csrf_token': add_user_csrf_token,
    })
    assert response.status_code == 302

    home_response = client.get('/')
    assert home_response.status_code == 200
    assert b'Reported faults' in home_response.data


def test_govuk_assets_load(client):
    css_response = client.get('/static/css/application.css')
    js_response = client.get('/static/js/govuk-frontend.min.js')

    assert css_response.status_code == 200
    assert js_response.status_code == 200
