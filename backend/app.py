import os
import google.generativeai as genai
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import datetime
import uuid
import copy
import json
import re
from cryptography.fernet import Fernet

app = Flask(__name__, static_folder='../frontend')
CORS(app)

# --- Gemini Configuration ---
# WARNING: In a real app, use environment variables!
# You can set it via `export GEMINI_API_KEY=...` before running.
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    print("Gemini configured.")
else:
    print("WARNING: GEMINI_API_KEY not set. AI features will fallback to basic simulation.")

@app.route('/')
def index():
    return send_from_directory('../frontend', 'index.html')

# --- In-Memory Data Store ---

# Notes/Entries in the timeline
# Structure:
# {
#   "id": "uuid",
#   "content": "text",
#   "author_role": "patient" | "staff" | "clinician" | "system" | "ai",
#   "type": "staff_note" | "clinician_note" | "ai_doctor_consult_summary" | ...,
#   "timestamp": "ISO string",
#   "version": 1,
#   "history": [], # List of previous versions
#   "conflicts": [],
#   "highlights": [], # List of key signals/highlights
#   "actions": [] # List of associated actions/assignments
# }
notes = []

# Load synthetic data if available
DATA_FILE = os.path.join(os.path.dirname(__file__), 'note.json')
KEY_FILE = os.path.join(os.path.dirname(__file__), 'secret.key')

cipher = None
if os.path.exists(KEY_FILE):
    try:
        with open(KEY_FILE, 'rb') as kf:
            key = kf.read()
            cipher = Fernet(key)
            print("Encryption key loaded.")
    except Exception as e:
        print(f"Error loading encryption key: {e}")

if os.path.exists(DATA_FILE):
    try:
        with open(DATA_FILE, 'rb') as f:
            file_content = f.read()
            
        # Try to decrypt if key exists
        notes_data = file_content
        if cipher:
            try:
                notes_data = cipher.decrypt(file_content)
                print("Decrypted notes successfully.")
            except Exception:
                # Fallback: maybe it's plain text
                print("Decryption failed or file not encrypted. Assuming plain text.")
                pass
                
        notes = json.loads(notes_data)
        print(f"Loaded {len(notes)} notes from {DATA_FILE}")
    except Exception as e:
        print(f"Error loading notes: {e}")

# Mock assignments/actions for Glance View (Global/System level)
# We will mix these with note-level actions
system_actions = []

# --- Helpers ---

def get_current_time():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

def generate_id():
    return str(uuid.uuid4())

def calculate_decay_weight(timestamp_str):
    """
    Calculates a weight (0.0 to 1.0) based on how old the item is.
    Simple linear decay: 100% at 0 days, 50% at 7 days, 0% at 14 days.
    """
    try:
        item_time = datetime.datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M")
        now = datetime.datetime.now()
        delta = now - item_time
        days = delta.days
        
        # Formula: weight = 1 / (1 + 0.5 * days)
        # Day 0: 1.0
        # Day 2: 0.5
        # Day 10: 0.16
        weight = 1.0 / (1.0 + 0.5 * days)
        return max(0.0, min(1.0, weight))
    except:
        return 1.0

def redact_phi(text):
    """
    Redacts sensitive PHI (ID, Phone, Names) from text.
    Privacy and Security: Synthetic Data Only.
    """
    if not isinstance(text, str):
        return text
        
    # Redact ID (6-18 digits)
    text = re.sub(r'\b\d{6,18}\b', '<REDACTED_ID>', text)
    # Redact Phone (Simple pattern: 3-4-4 or similar)
    text = re.sub(r'\b\d{3}[-\s]?\d{4}[-\s]?\d{4}\b', '<REDACTED_PHONE>', text)
    
    # Redact specific names (Simulation)
    # In production, use NER (Named Entity Recognition)
    names_to_redact = ["John Doe", "Jane Smith", "Alice", "Bob"]
    for name in names_to_redact:
        text = text.replace(name, "<REDACTED_NAME>")
        
    return text

def call_llm_analysis(content, context_notes=[]):
    """
    Uses Gemini to analyze the note content and extract:
    1. Highlights (Risks/Important Info)
    2. Actions (Tasks)
    3. Suggested Type (if not provided)
    """
    if not GEMINI_API_KEY:
        # Fallback if no API key
        return {"highlights": [], "actions": []}

    # Extract user-highlighted examples for Few-Shot Learning
    user_examples = []
    for n in context_notes:
        for h in n.get('highlights', []):
            if h.get('type') == 'user-highlight':
                user_examples.append(f"Text: '{h['text']}' -> Highlight (Important Signal)")
    
    # Limit to last 5 examples
    user_examples = user_examples[:5]
    examples_str = "\n".join(user_examples)

    # Redact Content and Context
    safe_content = redact_phi(content)
    context_str = "\n".join([f"[{n['timestamp']}] {redact_phi(n['content'])}" for n in context_notes[-3:]])

    # Construct prompt
    prompt = f"""
    You are an AI medical assistant. Analyze the following clinical note.
    
    Context (Recent History):
    {context_str}
    
    User's Past Highlighting Habits (Self-Learning):
    {examples_str}
    
    Current Note:
    {safe_content}
    
    Task:
    1. Identify key medical highlights (risks, vital changes, important symptoms).
    2. Identify actionable tasks for the clinician or staff.
    3. Suggest a 'type' for this note if ambiguous (e.g., 'consult', 'prescription', 'triage').
    
    Output JSON format:
    {{
      "highlights": [
        {{ "text": "string", "type": "risk" | "vital" | "symptom", "reason": "short explanation" }}
      ],
      "actions": [
        {{ "description": "string", "assignee": "clinician" | "staff" | "system", "priority": "high" | "medium" | "low", "tags": ["tag1", "tag2"] }}
      ],
      "suggested_type": "string"
    }}
    """
    
    try:
        model = genai.GenerativeModel('gemini-flash-latest')
        response = model.generate_content(prompt, generation_config={"response_mime_type": "application/json"})
        text = response.text
        return json.loads(text)
    except Exception as e:
        print(f"LLM Error (Gemini): {e}")
        return {"highlights": [], "actions": []}

# --- RBAC Logic ---

# Standard Visibility Scopes (Templates)
# True = Visible, False = Hidden
SCOPE_TEMPLATES = {
    "clinician_only": {
        "patient": False,
        "staff": False, 
        "clinician": True, 
        "admin": True
    },
    "staff_visible": {
        "patient": False,
        "staff": True,
        "clinician": True,
        "admin": True
    },
    "patient_visible": {
        "patient": True,
        "staff": True,
        "clinician": True,
        "admin": True
    }
}

def get_standardized_scope(note):
    """
    Adapter function to ensure note['visibility_scope'] is always a valid dictionary.
    Handles legacy data (missing field or string value) by converting it to the new dict format.
    """
    raw_scope = note.get('visibility_scope')

    # Case 1: Already a dictionary (New format)
    if isinstance(raw_scope, dict):
        return raw_scope

    # Case 2: String (Legacy format from old code)
    if isinstance(raw_scope, str):
        if raw_scope == 'patient':
            return SCOPE_TEMPLATES['patient_visible']
        elif raw_scope == 'staff':
            return SCOPE_TEMPLATES['staff_visible']
        elif raw_scope == 'clinician':
            return SCOPE_TEMPLATES['clinician_only']
        else:
            return SCOPE_TEMPLATES['staff_visible'] # Default fallback

    # Case 3: Missing field (Legacy data) -> Infer from note type
    note_type = note.get('type')
    
    if note_type == 'ai_doctor_consult_summary':
        return SCOPE_TEMPLATES['clinician_only']
    
    if note_type == 'clinician_note':
        return SCOPE_TEMPLATES['clinician_only']
        
    if note_type == 'ai_nurse_consult_summary':
        return SCOPE_TEMPLATES['staff_visible']
        
    if note_type == 'staff_note':
        return SCOPE_TEMPLATES['staff_visible']
        
    if note_type in ['ai_patient_session_summary', 'patient_input']:
        return SCOPE_TEMPLATES['patient_visible']

    # Default fallback for unknown types
    return SCOPE_TEMPLATES['staff_visible']

def can_view_note(user_role, note):
    if user_role == 'admin':
        return True
    
    # HARD CONSTRAINT: Patient cannot see AI Nurse Consult Summary
    if user_role == 'patient' and note.get('type') == 'ai_nurse_consult_summary':
        return False
    
    # Get the standardized dictionary (handles all legacy cases safely)
    scope = get_standardized_scope(note)
    
    # Check if the specific role is allowed
    return scope.get(user_role, False)

def can_edit_note(user_role, note):
    if user_role == 'admin':
        return True
    if user_role == 'clinician':
        return note['author_role'] in ['clinician', 'ai', 'system'] # Can edit own and AI
    if user_role == 'staff':
        return note['author_role'] == 'staff'
    if user_role == 'patient':
        return note['author_role'] == 'patient'
    return False

# --- Routes ---

@app.route('/api/timeline', methods=['GET'])
def get_timeline():
    user_role = request.args.get('role', 'clinician')
    visible_notes = [n for n in notes if can_view_note(user_role, n)]
    # Sort by timestamp desc
    visible_notes.sort(key=lambda x: x['timestamp'], reverse=True)
    return jsonify(visible_notes)

@app.route('/api/notes', methods=['POST'])
def create_note():
    data = request.json
    user_role = data.get('author_role', 'staff') # trusted role from client for prototype
    
    # Simple permission check for creation
    if user_role == 'patient' and data.get('type') not in ['patient_input']:
        return jsonify({"error": "Unauthorized type for patient"}), 403
    
    content = data.get('content', '')
    
    # Handle "Simulate AI Scribe" auto-generation (Empty content + simulate_ai=True)
    if data.get('simulate_ai') and not content and user_role == 'ai':
        # Generate mock content
        import random
        scenarios = [
            "Patient presents with persistent cough for 2 weeks. Reports productive sputum, green in color. No fever, but mild fatigue. Chest clear on auscultation. Vitals: BP 120/80, HR 78, Temp 37.1C. Recommend chest X-ray and course of antibiotics.",
            "Patient complains of lower back pain radiating to right leg. Pain scale 7/10. History of heavy lifting 2 days ago. SLR positive on right at 45 degrees. Reflexes intact. Suspect lumbar disc herniation. Prescribed NSAIDs and muscle relaxants. Refer to PT.",
            "Follow-up for hypertension. BP 135/85 today. Patient reports adherence to medication. No headaches or visual changes. Labs show stable kidney function. Continue current management. Recheck in 3 months.",
            "Child, 5yo, brought in for rash on arms. Itchy, red papules. Started yesterday after playing in the park. Suspect contact dermatitis vs poison ivy. Hydrocortisone cream advised. Antihistamine for itching.",
            "Diabetic check-up. Fasting glucose 145 mg/dL. A1c 7.2%. Foot exam normal. Monofilament sensation intact. Discussed diet modifications. Increase Metformin dosage to 1000mg BID."
        ]
        content = random.choice(scenarios)
        
        # If we have the LLM, we could ask it to generate one too, but for consistency in a prototype, scenarios are safer and faster.
        # But let's try to make it feel "live" if LLM is there.
        if GEMINI_API_KEY:
             try:
                gen_prompt = "Generate a realistic, short (3-5 sentences) clinical note for a random patient visit. Include symptoms, vitals, and plan."
                model = genai.GenerativeModel('gemini-1.5-flash-latest')
                response = model.generate_content(gen_prompt)
                content = response.text.strip()
             except Exception as e:
                print(f"Gemini Generation Error: {e}")
                pass # Fallback to scenarios

    note_id = generate_id()
    new_note = {
        "id": note_id,
        "content": content,
        "author_role": user_role,
        "type": data.get('type', 'staff_note'),
        "timestamp": get_current_time(),
        "version": 1,
        "history": [],
        "highlights": data.get('highlights', []),
        "actions": []
    }
    
    # Calculate Visibility Scope
    new_note['visibility_scope'] = get_standardized_scope(new_note)

    # Auto-generate Actions & Highlights via LLM
    # We do this for ALL notes now to support "AI learning from user input"
    # But for performance in prototype, maybe only if simulate_ai=True OR explicit request?
    # User requirement: "AI dynamically learns from user input... does not use any fixed keyword list"
    # So we should call LLM for every input if key is present.
    
    llm_result = {"highlights": [], "actions": []}
    if GEMINI_API_KEY and user_role != 'patient':
        llm_result = call_llm_analysis(new_note['content'], notes)
    else:
        # Fallback dynamic logic (simple keyword matching removed as per request "no hardcoding", 
        # but kept minimal strictly for "offline" demo if key missing)
        pass 

    # Merge LLM results
    for h in llm_result.get('highlights', []):
        # Find start/end index
        start_idx = new_note['content'].find(h['text'])
        if start_idx != -1:
            new_note['highlights'].append({
                "id": generate_id(),
                "text": h['text'],
                "type": h.get('type', 'risk'),
                "reason": h.get('reason', 'AI detected'),
                "start": start_idx,
                "end": start_idx + len(h['text'])
            })
            
    for a in llm_result.get('actions', []):
        new_note['actions'].append({
            "id": generate_id(),
            "title": a.get('description', a.get('title', 'Untitled Action')),
            "status": "pending", # LLM suggested actions are pending
            "created_by_role": "ai",
            "assigned_to_role": a.get('assignee', 'clinician'), # Default AI actions to clinician for review
            "provenance_note_id": note_id,
            "created_at": get_current_time(),
            "tags": a.get('tags', [])
        })

    # Manual Actions from Frontend
    if 'manual_actions' in data:
        for action_title in data['manual_actions']:
            # Determine assignment based on creator role and action type
            assigned_to = 'staff' # Default
            if user_role == 'clinician':
                assigned_to = 'staff'
            elif user_role == 'staff':
                assigned_to = 'clinician'
            
            new_note['actions'].append({
                "id": generate_id(),
                "title": action_title,
                "status": "unresolved",
                "created_by_role": user_role,
                "assigned_to_role": assigned_to,
                "provenance_note_id": note_id,
                "created_at": get_current_time()
            })
            
    notes.insert(0, new_note) # Add to top
    return jsonify(new_note)

@app.route('/api/actions/<action_id>/resolve', methods=['POST'])
def resolve_action(action_id):
    data = request.json
    user_role = data.get('role')
    resolution_type = data.get('resolution_type', 'resolve') # resolve | forward
    comment = data.get('comment', '')
    
    # Find the action across all notes
    target_action = None
    target_note = None
    
    for n in notes:
        for a in n.get('actions', []):
            if a['id'] == action_id:
                target_action = a
                target_note = n
                break
        if target_action:
            break
            
    if not target_action:
        return jsonify({"error": "Action not found"}), 404
        
    # Permission check: Only assignee can resolve (or admin)
    if user_role != 'admin' and target_action['assigned_to_role'] != user_role:
        return jsonify({"error": "Unauthorized: Action not assigned to you"}), 403
        
    # Update status
    target_action['status'] = 'resolved'
    target_action['resolved_at'] = get_current_time()
    target_action['resolution_comment'] = comment
    
    # Create System Note to log resolution in Timeline
    log_content = f"✅ Action Resolved: {target_action['title']}"
    if comment:
        log_content += f"\nNote: {comment}"
        
    # Handle Forwarding / New Action creation
    if resolution_type == 'forward':
        new_action_title = data.get('new_action_title')
        if new_action_title:
            # Determine new assignee (swap roles)
            new_assignee = 'staff' if user_role == 'clinician' else 'clinician'
            
            new_action = {
                "id": generate_id(),
                "title": new_action_title,
                "status": "unresolved",
                "created_by_role": user_role,
                "assigned_to_role": new_assignee,
                "provenance_note_id": target_action['provenance_note_id'], # Link to original source
                "created_at": get_current_time()
            }
            
            if 'actions' not in target_note:
                target_note['actions'] = []
            target_note['actions'].append(new_action)
            
            log_content += f"\n➡️ Forwarded to {new_assignee}: {new_action_title}"

    # Add log entry to timeline
    notes.insert(0, {
        "id": generate_id(),
        "content": log_content,
        "author_role": "system",
        "type": "system_log",
        "timestamp": get_current_time(),
        "version": 1,
        "history": [],
        "highlights": [],
        "actions": []
    })
    
    return jsonify({"status": "success", "action": target_action})

@app.route('/api/consult/end', methods=['POST'])
def end_consult():
    data = request.json
    user_role = data.get('role')
    source_note_id = data.get('source_note_id')
    
    # Determine type based on role
    if user_role == 'clinician':
        note_type = 'ai_doctor_consult_summary'
        scope = SCOPE_TEMPLATES['clinician_only']
        prompt_role = "doctor"
    elif user_role == 'staff':
        note_type = 'ai_nurse_consult_summary'
        scope = SCOPE_TEMPLATES['staff_visible']
        prompt_role = "nurse"
    elif user_role == 'patient':
        note_type = 'ai_patient_session_summary'
        scope = SCOPE_TEMPLATES['patient_visible']
        prompt_role = "patient session"
    else:
        return jsonify({"error": "Invalid role for ending consult"}), 400
        
    # Gather context (e.g. all notes from today or last session)
    # For prototype, just take last 10 notes
    recent_notes = notes[:10]
    # Deep copy to avoid modifying original list in place during reverse
    recent_notes = copy.deepcopy(recent_notes)
    recent_notes.reverse() # Chronological
    
    # Redact context for summary
    context_text = "\n".join([f"[{n['author_role']}]: {redact_phi(n['content'])}" for n in recent_notes])
    
    content = ""
    if GEMINI_API_KEY:
        try:
            # Custom instructions based on role
            custom_instructions = ""
            if user_role == 'patient':
                custom_instructions = """
                STRICT RULES FOR PATIENT SUMMARY:
                1. Use simple, non-medical language (layperson terms).
                2. DO NOT include specific medication dosages (e.g., say 'steroids' not 'Solu-Medrol 125mg').
                3. DO NOT include raw vital signs (e.g., say 'fast heart rate' not 'HR 110').
                4. Focus on: What happened, What was done, and What to do next.
                5. NO medical jargon or complex diagnosis codes.
                """
            
            prompt = f"""
            Summarize the following medical consultation for a {prompt_role}'s record.
            {custom_instructions}
            
            Context:
            {context_text}
            
            Output a concise professional summary.
            """
            model = genai.GenerativeModel('gemini-flash-latest')
            response = model.generate_content(prompt)
            content = response.text.strip()
        except Exception as e:
            print(f"Gemini Error: {e}")
            content = f"AI Generated {prompt_role} summary (LLM Error)"
    else:
        # Mock content
        if note_type == 'ai_doctor_consult_summary':
            content = "Assessment: Acute Bronchitis. \nPlan: Azithromycin 500mg PO x 3 days. Albuterol inhaler PRN. \nFollow-up: If symptoms worsen or fever persists > 48hrs."
        elif note_type == 'ai_nurse_consult_summary':
            content = "Patient educated on medication adherence and hydration. Vitals stable. Patient expressed understanding of discharge instructions."
        else:
            content = "Session Summary: Patient reported symptoms of cough and fatigue. Vitals recorded. Doctor consultation completed with prescription provided."

    new_note = {
        "id": generate_id(),
        "content": content,
        "author_role": "system",
        "type": note_type,
        "timestamp": get_current_time(),
        "version": 1,
        "history": [],
        "highlights": [],
        "actions": [],
        "provenance_pointer": source_note_id,
        "visibility_scope": scope
    }

    # Auto-generate Actions & Highlights via LLM
    if GEMINI_API_KEY:
        # SKIP highlights/actions for Patient summaries to avoid leaking clinical reasoning
        if user_role == 'patient':
            llm_result = {"highlights": [], "actions": []}
        else:
            llm_result = call_llm_analysis(new_note['content'], notes)

        for h in llm_result.get('highlights', []):
            start_idx = new_note['content'].find(h['text'])
            if start_idx != -1:
                new_note['highlights'].append({
                    "id": generate_id(),
                    "text": h['text'],
                    "type": h.get('type', 'risk'),
                    "reason": h.get('reason', 'AI detected'),
                    "start": start_idx,
                    "end": start_idx + len(h['text'])
                })
        
        for a in llm_result.get('actions', []):
            new_note['actions'].append({
                "id": generate_id(),
                "title": a.get('description', a.get('title', 'Untitled Action')),
                "status": "pending",
                "created_by_role": "ai",
                "assigned_to_role": a.get('assignee', 'clinician'),
                "provenance_note_id": new_note['id'],
                "created_at": get_current_time(),
                "tags": a.get('tags', [])
            })
    
    notes.insert(0, new_note)
    return jsonify(new_note)

@app.route('/api/notes/<note_id>', methods=['PUT'])
def update_note(note_id):
    data = request.json
    user_role = data.get('role', 'clinician')
    
    note = next((n for n in notes if n['id'] == note_id), None)
    if not note:
        return jsonify({"error": "Note not found"}), 404
        
    if not can_edit_note(user_role, note):
        return jsonify({"error": "Unauthorized"}), 403
        
    # Versioning
    prev_version = copy.deepcopy(note)
    # Remove history from the copy to avoid recursion/bloat
    prev_version['history'] = [] 
    
    note['history'].append(prev_version)
    note['version'] += 1
    note['content'] = data.get('content', note['content'])
    note['timestamp'] = get_current_time() # Update timestamp on edit? Or keep original? Usually edit time.
    
    # Conflict Resolution Logic (Simulation)
    # If clinician edits AI note, it overrides.
    if user_role == 'clinician' and note['author_role'] == 'ai':
        note['author_role'] = 'clinician' # Take ownership or keep as AI but 'confirmed'?
        # Let's keep original author but maybe add 'last_editor'
        note['last_editor'] = 'clinician'

    return jsonify(note)

@app.route('/api/notes/<note_id>/revert', methods=['POST'])
def revert_note(note_id):
    """
    Reverts a note to its previous version.
    Designed for the 'Undo' functionality for clinicians modifying AI notes.
    """
    data = request.json
    user_role = data.get('role', 'clinician')
    
    note = next((n for n in notes if n['id'] == note_id), None)
    if not note:
        return jsonify({"error": "Note not found"}), 404
        
    if not can_edit_note(user_role, note):
        return jsonify({"error": "Unauthorized"}), 403
        
    if not note.get('history'):
        return jsonify({"error": "No history to revert to"}), 400
        
    # Get the last version from history
    prev_version = note['history'].pop()
    
    # Save current state as a 'reverted_from' version? 
    # Or just discard current state and go back?
    # Usually 'undo' implies discarding current, BUT for auditability, we should probably record that a revert happened.
    # However, standard 'undo' just pops.
    # Let's check requirements: "modification record and revert record will be displayed in the sidepanel"
    # This implies we need to KEEP the record of the revert action.
    
    # So:
    # 1. Create a copy of current state (to be saved in history as the state that was reverted)
    # 2. BUT actually, if we want to RESTORE the previous content, we should just overwrite current fields with prev_version fields.
    # 3. And we should add a log entry or some metadata indicating a revert happened.
    
    # Let's treat 'revert' as a new edit that restores old content.
    # 1. Archive current state to history.
    current_state_to_archive = copy.deepcopy(note)
    current_state_to_archive['history'] = [] # Don't nest history
    
    # 2. Restore content/author from prev_version
    # Ideally we find the target version. If we just pop, we lose the 'current' bad state if we don't save it.
    # If we save 'current' to history, then 'pop' isn't quite right because 'history' grows.
    
    # Let's say:
    # v1 (AI)
    # v2 (Clinician Edit) -> stored in note. history=[v1]
    # REVERT:
    # v3 (Revert to v1) -> stored in note. history=[v1, v2]
    # Content of v3 == Content of v1.
    
    # Implementation:
    # Target version is the LAST item in history (which is the state before current edit).
    target_version = prev_version # This was popped, so it's the one we want to go back to?
    # Wait, if history=[v1], and current is v2.
    # We want to go back to v1.
    # So we take v1.
    # We create v3 which looks like v1.
    # We append v2 to history.
    
    # Re-insert the popped version because we aren't 'removing' history, we are appending a new 'revert' event?
    # Actually, if I just pop, I lose the record of v2?
    # "modification record and revert record will be displayed"
    # So we must NOT destroy history.
    
    # Put it back
    note['history'].append(prev_version)
    
    # Create new version
    note['version'] += 1
    
    # Restore fields from target_version
    note['content'] = target_version['content']
    note['author_role'] = target_version['author_role']
    # note['type'] = target_version['type'] # Type usually doesn't change
    
    # Add metadata about revert
    note['reverted_at'] = get_current_time()
    note['reverted_by'] = user_role
    
    # Save the state BEFORE revert (the bad edit) to history?
    # The 'prev_version' we appended back is v1.
    # We need to append v2 (the current state before revert) to history.
    # So:
    # 1. note['history'] currently has [v1]. note is v2.
    # 2. We want note to be v3 (copy of v1). history to be [v1, v2].
    
    note['history'].append(current_state_to_archive)
    
    # Now note is updated.
    
    return jsonify(note)


@app.route('/api/notes/<note_id>/highlight', methods=['POST'])
def add_highlight(note_id):
    data = request.json
    text = data.get('text')
    start = data.get('start')
    end = data.get('end')
    
    note = next((n for n in notes if n['id'] == note_id), None)
    if not note:
        return jsonify({"error": "Note not found"}), 404
        
    new_highlight = {
        "id": generate_id(),
        "text": text,
        "type": "user-highlight", # Distinguish from AI risk
        "start": start,
        "end": end
    }
    
    if 'highlights' not in note:
        note['highlights'] = []
        
    note['highlights'].append(new_highlight)
    
    return jsonify(note)

@app.route('/api/notes/<note_id>/highlight/<highlight_id>', methods=['DELETE'])
def remove_highlight(note_id, highlight_id):
    note = next((n for n in notes if n['id'] == note_id), None)
    if not note:
        return jsonify({"error": "Note not found"}), 404
        
    if 'highlights' in note:
        note['highlights'] = [h for h in note['highlights'] if h['id'] != highlight_id]
        
    return jsonify(note)

@app.route('/api/glance', methods=['GET'])
def get_glance():
    user_role = request.args.get('role', 'clinician')
    
    if user_role == 'patient':
        return jsonify({"key_signals": [], "actions": [], "clinician_confirmed": []})
    
    # Gather highlights and actions from all notes
    all_highlights = []
    all_actions = copy.deepcopy(system_actions)
    confirmed_items = []
    ai_scribed_notes = []

    for n in notes:
        can_view = can_view_note(user_role, n)

        # AI Scribed Notes
        # Check if note is AI-generated (type starts with ai_)
        # Even if edited by clinician (author_role changed), it remains an AI-scribed note in essence.
        if can_view and n.get('type', '').startswith('ai_'):
            ai_scribed_notes.append({
                "id": n['id'],
                "type": n['type'].replace('ai_', '').replace('_', ' ').title(),
                "summary": n['content'][:100] + "..." if len(n['content']) > 100 else n['content'],
                "timestamp": n['timestamp'],
                "author_role": n['author_role']
            })

        # Highlights with Decay
        if can_view:
            decay_weight = calculate_decay_weight(n['timestamp'])

            for h in n.get('highlights', []):
                h['source_note_id'] = n['id']
                h['weight'] = decay_weight
                h['timestamp'] = n['timestamp'] # For sorting
                
                # Decay Filtering: Skip old non-critical items
                if decay_weight < 0.2 and h.get('type') != 'critical':
                    continue
                    
                all_highlights.append(h)
        
        # Actions
        # Allow viewing actions assigned to the user even if the note itself is hidden (Task Assignment)
        for a in n.get('actions', []):
            # Filtering Rule:
            # 1. Show only derived actions (assigned to me)
            # 2. Show only unresolved
            
            # Special case for Admin: see everything? Or adhere to strict flow?
            # Let's adhere to flow, but Admin can see all unresolved.
            
            is_visible = False
            if user_role == 'admin':
                is_visible = True
            elif a.get('assigned_to_role') == user_role and a.get('status') in ['unresolved', 'pending']:
                is_visible = True
                
            if is_visible:
                all_actions.append(a)

        # Clinician Confirmed Logic
        # 1. Decisions/Plans (explicit types or keywords)
        if can_view and n['author_role'] == 'clinician':
            is_plan = 'plan' in n['content'].lower() or 'decision' in n['content'].lower()
            if is_plan or n['type'] == 'clinician_note':
                confirmed_items.append({
                    "id": n['id'],
                    "text": f"Decision: {n['content'][:50]}...",
                    "source_note_id": n['id'],
                    "type": "decision"
                })
            
            # 2. Modified AI Content
            # If clinician is author but history has AI versions, or we flag it
            if n.get('history'):
                # Check if original was AI
                first_ver = n['history'][0]
                if first_ver.get('author_role') == 'ai':
                    confirmed_items.append({
                        "id": n['id'] + "_mod",
                        "text": "Modified AI Consult",
                        "source_note_id": n['id'],
                        "type": "modification"
                    })
            
    # Filter for "Only Clinician Visible" requirement
    if user_role not in ['clinician', 'admin']:
        confirmed_items = []
        
    # Sort highlights: High weight first, then recent first
    all_highlights.sort(key=lambda x: (x.get('weight', 0), x.get('timestamp', '')), reverse=True)

    return jsonify({
        "actions": all_actions,
        "key_signals": all_highlights,
        "clinician_confirmed": confirmed_items,
        "ai_scribed_notes": ai_scribed_notes
    })

@app.route('/api/reset', methods=['POST'])
def reset():
    global notes, system_actions
    notes = []
    system_actions = []
    return jsonify({"status": "reset"})

if __name__ == '__main__':
    # TLS Configuration (Optional for Local Demo)
    # To enable HTTPS, uncomment the lines below and ensure cert.pem/key.pem exist.
    # ssl_files = ('cert.pem', 'key.pem')
    # if os.path.exists(ssl_files[0]) and os.path.exists(ssl_files[1]):
    #     print("Starting with TLS (HTTPS)...")
    #     app.run(debug=True, port=5000, ssl_context=ssl_files)
    # else:
    #     print("WARNING: SSL certs not found. Starting in HTTP mode.")
    #     app.run(debug=True, port=5000)
    
    # Default to HTTP for local ease of use (avoiding self-signed cert warnings)
    print("Starting in HTTP mode (TLS disabled for local demo)...")
    app.run(debug=True, port=5001)
