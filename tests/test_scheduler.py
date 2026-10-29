def test_schedule_status(admin_client):
    resp = admin_client.get('/api/schedule/status')
    assert resp.status_code == 200
    data = resp.get_json()
    assert data['status'] == 'success'
    assert 'can_calculate' in data
    assert 'eligible_machines' in data


def test_schedule_status_has_latest_draft_key(admin_client):
    resp = admin_client.get('/api/schedule/status')
    data = resp.get_json()
    assert 'latest_draft' in data
