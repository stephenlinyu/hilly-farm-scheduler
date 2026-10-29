def test_track_for_demo_machine(admin_client):
    resp = admin_client.get('/api/tracks/R-001')
    assert resp.status_code == 200


def test_track_history(admin_client):
    resp = admin_client.get('/api/tracks/R-001/history')
    assert resp.status_code in (200, 400, 404)


def test_machines_list(admin_client):
    resp = admin_client.get('/api/machines')
    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data, list)
    assert len(data) >= 50


def test_fields_list(admin_client):
    resp = admin_client.get('/api/fields')
    assert resp.status_code == 200
    data = resp.get_json()
    assert isinstance(data, list)
    assert len(data) >= 100
