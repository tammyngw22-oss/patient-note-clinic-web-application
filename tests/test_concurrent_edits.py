def test_concurrent_edits_resolution(client):
    # Setup: Create an AI note
    resp = client.post('/api/notes', json={
        "content": "AI generated content",
        "author_role": "ai",
        "type": "ai_consult_summary"
    })
    note_id = resp.get_json()['id']
    
    # Simulate concurrent edits
    # 1. Clinician edits
    client.put(f'/api/notes/{note_id}', json={
        "content": "Clinician corrected content",
        "role": "clinician"
    })
    
    # 2. Another update (e.g. late arriving AI refinement) - but clinician already touched it
    # Ideally, if clinician touched it, AI shouldn't overwrite it, or it should be a new version.
    # In my simple implementation, every PUT is a new version.
    
    client.put(f'/api/notes/{note_id}', json={
        "content": "AI Refinement",
        "role": "staff" # Simulate staff trying to edit
    })
    
    resp = client.get('/api/timeline')
    note = [n for n in resp.get_json() if n['id'] == note_id][0]
    
    # Verify latest version is the last write (Staff in this case, unless we block it)
    # But wait, earlier I wrote a test that staff cannot edit clinician note.
    # If the first edit changed author to clinician, the second edit by staff should fail!
    
    # Let's verify that logic.
    # 1. AI creates (author=ai)
    # 2. Clinician edits (author becomes clinician)
    # 3. Staff edits (should fail because author is clinician)
    
    assert note['author_role'] == 'clinician' # From the first edit
    assert note['content'] == "Clinician corrected content" # Staff edit should have failed
