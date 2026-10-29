"""测试夹具：临时 SQLite 数据库 + Flask test_client + 登录会话。

在导入 app 之前设置 FARM_SQLITE_DB，避免污染仓库目录下的真实数据库。
"""
import os
import tempfile

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_TMP = os.path.join(_REPO_ROOT, 'test_tmp')
os.makedirs(_TMP, exist_ok=True)
_DB_PATH = os.path.join(_TMP, 'test_farm.sqlite')
if os.path.exists(_DB_PATH):
    os.remove(_DB_PATH)
os.environ['FARM_SQLITE_DB'] = _DB_PATH
os.environ['FARM_SYSTEM_SECRET_KEY'] = 'test-secret-key-0123456789abcdef0123456789abcdef'
os.environ['FARM_DB_DRIVER'] = 'sqlite'
os.environ['FARM_LOGIN_FAILURE_LIMIT'] = '1000'

import pytest  # noqa: E402

from init_local_db import init_db  # noqa: E402

init_db()

from app import app as flask_app  # noqa: E402

ADMIN = {'username': 'admin', 'password': 'Admin@123456', 'role': 'admin'}


@pytest.fixture
def client():
    flask_app.config['TESTING'] = True
    with flask_app.test_client() as c:
        yield c


def login(client, username, password, role):
    return client.post('/api/auth/login', json={
        'username': username, 'password': password, 'role': role,
    })


def csrf_token(client):
    cookie = client.get_cookie('farm_csrf_token')
    return cookie.value if cookie else ''


@pytest.fixture
def admin_client(client):
    resp = login(client, ADMIN['username'], ADMIN['password'], ADMIN['role'])
    assert resp.status_code == 200, resp.get_data(as_text=True)
    return client


@pytest.fixture
def csrf(admin_client):
    return csrf_token(admin_client)
