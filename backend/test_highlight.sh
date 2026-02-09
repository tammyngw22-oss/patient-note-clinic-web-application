#!/bin/bash
API="http://127.0.0.1:5000/api"

# 1. Create Note
echo "Creating note..."
curl -s -X POST "/notes"   -H "Content-Type: application/json"   -d '{"content": "Test note for highlight removal", "author_role": "clinician", "type": "clinician_note"}' > note.json
NOTE_ID=
echo "Note ID: "

# 2. Add Highlight
echo "Adding highlight..."
curl -s -X POST "/notes//highlight"   -H "Content-Type: application/json"   -d '{"text": "highlight", "start": 0, "end": 9}' > highlight_res.json
# Extract highlight ID (it's inside the highlights array)
HIGHLIGHT_ID=
echo "Highlight ID: "

# 3. Verify Highlight exists
echo "Verifying highlight exists..."
curl -s "/timeline?role=clinician" | grep "" > /dev/null && echo "Highlight found." || echo "Highlight NOT found."

# 4. Remove Highlight
echo "Removing highlight  from note ..."
curl -s -X DELETE "/notes//highlight/" > delete_res.json
echo "Delete response:"
cat delete_res.json

# 5. Verify Highlight is gone
echo "Verifying highlight is gone..."
curl -s "/timeline?role=clinician" | grep "" > /dev/null && echo "Highlight STILL found (Fail)." || echo "Highlight gone (Success)."
