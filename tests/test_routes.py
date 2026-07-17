from html.parser import HTMLParser

import pytest
from werkzeug.security import check_password_hash

from app import create_app
from app.db import get_db


class CSRFTokenParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.token = None

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == 'input' and attributes.get('name') == 'csrf_token':
            self.token = attributes.get('value')


def extract_csrf_token(response):
    parser = CSRFTokenParser()
    parser.feed(response.get_data(as_text=True))
    assert parser.token is not None
    return parser.token


def get_csrf_token(client, path):
    response = client.get(path)
    assert response.status_code == 200
    return extract_csrf_token(response)


def registration_data(**overrides):
    data = {
        'username': 'new-user',
        'first_name': 'New',
        'last_name': 'User',
        'password': 'secure-password-123',
        'confirm_password': 'secure-password-123',
    }
    data.update(overrides)
    return data


def post_registration(client, **overrides):
    data = registration_data(**overrides)
    data['csrf_token'] = get_csrf_token(client, '/register')
    return client.post('/register', data=data)


def get_user(app, username):
    with app.app_context():
        return get_db().execute(
            "SELECT * FROM users WHERE username = ?",
            (username,),
        ).fetchone()


def count_users(app, username):
    with app.app_context():
        return get_db().execute(
            "SELECT COUNT(*) FROM users WHERE username = ?",
            (username,),
        ).fetchone()[0]


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


def test_registration_page_loads_with_csrf_token(client):
    response = client.get('/register')

    assert response.status_code == 200
    assert b'Create an account' in response.data
    assert b'<input type="hidden" name="csrf_token"' in response.data


def test_valid_registration_creates_regular_user(client):
    password = 'secure-password-123'
    response = post_registration(
        client,
        username='Case.Sensitive-User',
        password=password,
        confirm_password=password,
        role='admin',
    )

    assert response.status_code == 302
    assert response.headers['Location'].endswith('/login')

    unauthenticated_response = client.get('/')
    assert unauthenticated_response.status_code == 302
    assert '/login' in unauthenticated_response.headers['Location']

    user = get_user(client.application, 'Case.Sensitive-User')
    assert user is not None
    assert user['role'] == 'user'
    assert user['password_hash'] != password
    assert check_password_hash(user['password_hash'], password)

    login_page = client.get('/login')
    assert b'Account created. You can now sign in.' in login_page.data

    login_response = client.post('/login', data={
        'username': 'Case.Sensitive-User',
        'password': password,
        'csrf_token': extract_csrf_token(login_page),
    })
    assert login_response.status_code == 302
    assert login_response.headers['Location'].endswith('/')


def test_registration_without_csrf_token_is_rejected(client):
    response = client.post('/register', data=registration_data())
    assert response.status_code == 400


@pytest.mark.parametrize(
    ('field', 'value', 'error_message'),
    [
        ('username', '', b'Enter a username'),
        ('first_name', '', b'Enter your first name'),
        ('last_name', '', b'Enter your last name'),
        ('password', '', b'Enter a password'),
        ('confirm_password', '', b'Confirm your password'),
    ],
)
def test_registration_rejects_blank_values(
    client, field, value, error_message
):
    response = post_registration(client, **{field: value})

    assert response.status_code == 200
    assert error_message in response.data


@pytest.mark.parametrize(
    ('field', 'value', 'error_message'),
    [
        ('username', '   ', b'Enter a username'),
        ('first_name', '   ', b'Enter your first name'),
        ('last_name', '   ', b'Enter your last name'),
        ('password', '            ', b'Enter a password'),
        ('confirm_password', '            ', b'Passwords do not match'),
    ],
)
def test_registration_rejects_whitespace_only_values(
    client, field, value, error_message
):
    response = post_registration(client, **{field: value})

    assert response.status_code == 200
    assert error_message in response.data


@pytest.mark.parametrize(
    ('username', 'error_message'),
    [
        ('ab', b'Username must be at least 3 characters'),
        ('a' * 31, b'Username must be 30 characters or fewer'),
        ('invalid user!', b'Username can only contain letters, numbers'),
    ],
)
def test_registration_rejects_invalid_usernames(
    client, username, error_message
):
    response = post_registration(client, username=username)

    assert response.status_code == 200
    assert error_message in response.data


@pytest.mark.parametrize('field', ['first_name', 'last_name'])
def test_registration_rejects_names_over_50_characters(client, field):
    response = post_registration(client, **{field: 'a' * 51})

    assert response.status_code == 200
    assert b'must be 50 characters or fewer' in response.data


def test_registration_rejects_short_password(client):
    response = post_registration(
        client,
        password='short',
        confirm_password='short',
    )

    assert response.status_code == 200
    assert b'Password must be at least 12 characters' in response.data


def test_registration_rejects_password_mismatch(client):
    response = post_registration(
        client,
        password='secure-password-123',
        confirm_password='different-password-123',
    )

    assert response.status_code == 200
    assert b'Passwords do not match' in response.data


def test_registration_rejects_duplicate_username(client):
    first_response = post_registration(client, username='duplicate-user')
    second_response = post_registration(client, username='duplicate-user')

    assert first_response.status_code == 302
    assert second_response.status_code == 200
    assert b'An account with that username already exists' in second_response.data
    assert count_users(client.application, 'duplicate-user') == 1


def test_invalid_registration_preserves_only_non_password_values(client):
    response = post_registration(
        client,
        username='Preserved.User',
        first_name="Anne-Marie",
        last_name="O'Connor",
        password='password-that-must-not-return',
        confirm_password='different-secret-that-must-not-return',
    )

    assert response.status_code == 200
    assert b'value="Preserved.User"' in response.data
    assert b'value="Anne-Marie"' in response.data
    assert b'value="O&#39;Connor"' in response.data
    assert b'password-that-must-not-return' not in response.data
    assert b'different-secret-that-must-not-return' not in response.data


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
