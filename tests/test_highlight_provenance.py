def test_highlight_generation_and_provenance(client):
    # Create AI note with "pain" keyword to trigger auto-highlight
    resp = client.post('/api/notes', json={
        "content": "Patient reports severe chest pain.",
        "author_role": "ai",
        "type": "ai_consult_summary",
        "simulate_ai": True
    })
    note = resp.get_json()
    note_id = note['id']
    
    assert len(note['highlights']) > 0
    highlight = note['highlights'][0]
    assert highlight['text'] == "Pain reported"
    
    # Check Glance View
    resp = client.get('/api/glance')
    glance_data = resp.get_json()
    
    key_signals = glance_data['key_signals']
    assert len(key_signals) > 0
    signal = key_signals[0]
    
    # Assert provenance pointer resolves to the note
    assert signal['source_note_id'] == note_id
    assert signal['start'] >= 0
    assert signal['end'] > signal['start']
