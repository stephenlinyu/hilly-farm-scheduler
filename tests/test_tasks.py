def test_list_tasks(admin_client):
    resp = admin_client.get('/api/tasks')
    assert resp.status_code == 200
    assert isinstance(resp.get_json(), list)


def test_add_task_unknown_machine(admin_client, csrf):
    resp = admin_client.post(
        '/api/tasks/add',
        json={'machine_id': 'NOT-EXIST', 'farmland_id': 'F-001'},
        headers={'X-CSRF-Token': csrf},
    )
    assert resp.status_code == 404


def test_add_task_unknown_field(admin_client, csrf):
    resp = admin_client.post(
        '/api/tasks/add',
        json={'machine_id': 'R-001', 'farmland_id': 'NOT-EXIST'},
        headers={'X-CSRF-Token': csrf},
    )
    assert resp.status_code == 404


def test_add_task_missing_fields(admin_client, csrf):
    resp = admin_client.post('/api/tasks/add', json={}, headers={'X-CSRF-Token': csrf})
    assert resp.status_code == 400
