from conftest import login, csrf_token


def test_login_success_admin(client):
    resp = login(client, 'admin', 'Admin@123456', 'admin')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['user']['role'] == 'admin'
    assert csrf_token(client) != ''


def test_login_wrong_password(client):
    resp = login(client, 'admin', 'wrong-password', 'admin')
    assert resp.status_code == 401


def test_login_missing_fields(client):
    resp = client.post('/api/auth/login', json={'username': 'admin'})
    assert resp.status_code == 400


def test_login_role_mismatch(client):
    resp = login(client, 'admin', 'Admin@123456', 'worker')
    assert resp.status_code == 403


def test_me_requires_login(client):
    resp = client.get('/api/auth/me')
    assert resp.status_code == 200
    assert resp.get_json()['authenticated'] is False


def test_csrf_missing_header(admin_client):
    resp = admin_client.post('/api/tasks/add', json={'machine_id': 'R-001', 'farmland_id': 'F-001'})
    assert resp.status_code == 403


def test_csrf_wrong_token(admin_client):
    resp = admin_client.post(
        '/api/tasks/add',
        json={'machine_id': 'R-001', 'farmland_id': 'F-001'},
        headers={'X-CSRF-Token': 'not-a-real-token'},
    )
    assert resp.status_code == 403


def test_csrf_valid_token(admin_client, csrf):
    resp = admin_client.post(
        '/api/tasks/add',
        json={'machine_id': 'R-001', 'farmland_id': 'F-001'},
        headers={'X-CSRF-Token': csrf},
    )
    assert resp.status_code in (200, 201)


def test_logout_clears_session(admin_client, csrf):
    resp = admin_client.post('/api/auth/logout', headers={'X-CSRF-Token': csrf})
    assert resp.status_code == 200
    assert admin_client.get('/api/auth/me').get_json()['authenticated'] is False
