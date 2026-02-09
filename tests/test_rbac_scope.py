def test_staff_cannot_edit_clinician_note(client):
    # Create a clinician note
    resp = client.post('/api/notes', json={
        "content": "Clinician Note",
        "author_role": "clinician",
        "type": "clinician_note"
    })
    note_id = resp.get_json()['id']
    
    # Staff tries to edit it
    resp = client.put(f'/api/notes/{note_id}', json={
        "content": "Staff Hacked",
        "role": "staff"
    })
    assert resp.status_code == 403

def test_clinician_cannot_edit_staff_note(client):
    # Create a staff note
    resp = client.post('/api/notes', json={
        "content": "Staff Note",
        "author_role": "staff",
        "type": "staff_note"
    })
    note_id = resp.get_json()['id']
    
    # Clinician tries to edit it (Requirement: Clinician can view staff notes, but edit clinician_sections)
    # The requirement says "Clinician: ... can view staff_notes ... access range limited to clinic patients"
    # It doesn't explicitly say they can *edit* staff notes. Usually they can't edit other people's notes.
    # My implementation says: if note['author_role'] in ['clinician', 'ai', 'system'] they can edit.
    # So they shouldn't be able to edit staff notes.
    resp = client.put(f'/api/notes/{note_id}', json={
        "content": "Clinician Override",
        "role": "clinician"
    })
    assert resp.status_code == 403

def test_patient_access_scope(client):
    # Create internal note
    client.post('/api/notes', json={
        "content": "Internal AI raw thought",
        "author_role": "ai",
        "type": "ai_internal_thought"
    })
    
    # Create public note
    client.post('/api/notes', json={
        "content": "Public Summary",
        "author_role": "clinician",
        "type": "clinician_note"
    })
    
    resp = client.get('/api/timeline?role=patient')
    data = resp.get_json()
    
    # Should only see public note
    assert len(data) == 1
    assert "Public Summary" in data[0]['content']
