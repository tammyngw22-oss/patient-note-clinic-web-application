def test_edit_increments_version(client):
    # Create note
    resp = client.post('/api/notes', json={
        "content": "Original Content",
        "author_role": "clinician",
        "type": "clinician_note"
    })
    note_id = resp.get_json()['id']
    
    # Edit note
    resp = client.put(f'/api/notes/{note_id}', json={
        "content": "Edited Content",
        "role": "clinician"
    })
    data = resp.get_json()
    
    assert data['version'] == 2
    assert data['content'] == "Edited Content"
    assert len(data['history']) == 1
    assert data['history'][0]['content'] == "Original Content"
    assert data['history'][0]['version'] == 1

def test_audit_log_metadata(client):
    # Create note
    resp = client.post('/api/notes', json={
        "content": "v1",
        "author_role": "clinician",
        "type": "clinician_note"
    })
    note_id = resp.get_json()['id']
    
    # Edit note
    client.put(f'/api/notes/{note_id}', json={
        "content": "v2",
        "role": "clinician"
    })
    
    resp = client.get('/api/timeline?role=clinician')
    note = [n for n in resp.get_json() if n['id'] == note_id][0]
    
    # Check history has metadata
    history_item = note['history'][0]
    assert 'timestamp' in history_item
    assert 'author_role' in history_item
