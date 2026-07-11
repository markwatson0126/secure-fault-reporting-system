import pytest

from app import create_app

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
    assert b'Login' in response.data


def test_admin_can_add_user(client):
    login_response = client.post('/login', data={
        'username': 'admin',
        'password': 'admin-test-password',
    })
    assert login_response.status_code == 302

    response = client.post('/add_user', data={
        'username': 'new-user',
        'password': 'new-user-password',
        'first_name': 'New',
        'last_name': 'User',
        'role': 'user',
    })
    assert response.status_code == 302
