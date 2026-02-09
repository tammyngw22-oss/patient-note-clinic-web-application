import json
import uuid
import datetime
import random
from cryptography.fernet import Fernet
import os

# --- Configuration ---
OUTPUT_FILE = 'backend/note.json'
KEY_FILE = 'backend/secret.key'

# --- Helpers ---
def generate_id():
    return str(uuid.uuid4())

def get_time_offset(minutes_ago):
    now = datetime.datetime.now()
    delta = datetime.timedelta(minutes=minutes_ago)
    return (now - delta).strftime("%Y-%m-%d %H:%M")

# --- Scenarios ---
# We will create a rich timeline for a single patient visit (e.g., "Acute Asthma Attack")
# encompassing multiple roles to demonstrate RBAC and features.

scenarios = [
    # 1. Patient Input (Triage/Registration) - Visible to Patient, Staff, Clinician
    {
        "type": "patient_input",
        "author_role": "patient",
        "content": "I'm having trouble breathing since this morning. It feels like my chest is tight. I used my inhaler twice but it didn't help much. Pain score: 4/10.",
        "minutes_ago": 60,
        "visibility_scope": {"patient": True, "staff": True, "clinician": True, "admin": True},
        "history": [
            {
                "version": 1,
                "timestamp": get_time_offset(65),
                "content": "I'm having trouble breathing. Pain score: 8/10."
            }
        ],
        "version": 2
    },
    # 2. Staff Triage Note - Visible to Staff, Clinician (NOT Patient)
    {
        "type": "staff_note",
        "author_role": "staff",
        "content": "Triage Assessment: Patient appears in mild respiratory distress. Speaking in short sentences. \nVitals: \nBP: 130/85 \nHR: 110 (Tachycardic) \nRR: 28/min \nSpO2: 92% on room air. \nAllocated to Bed 4.",
        "minutes_ago": 50,
        "highlights": [
            {"text": "HR: 110 (Tachycardic)", "type": "vital", "reason": "Abnormal heart rate"},
            {"text": "SpO2: 92% on room air", "type": "vital", "reason": "Hypoxia risk"}
        ],
        "actions": [
            {"title": "Review Triage Vitals", "status": "pending", "assigned_to_role": "clinician", "created_by_role": "staff"}
        ],
        "visibility_scope": {"patient": False, "staff": True, "clinician": True, "admin": True},
        "history": [
            {
                "version": 1,
                "timestamp": get_time_offset(55),
                "content": "Triage Assessment: Patient appears in mild respiratory distress. Speaking in short sentences. \nVitals: \nBP: 130/85 \nHR: 110 (Tachycardic) \nRR: 28/min \nSpO2: 92% on room air. \nAllocated to Bed 2."
            }
        ],
        "version": 2
    },
    # 2b. Nurse Request for Doctor Review (Explicit Example)
    {
        "type": "staff_note",
        "author_role": "staff",
        "content": "Nurse Note: Patient requesting stronger pain medication (Morphine) due to persistent 8/10 pain. Please assess.",
        "minutes_ago": 45,
        "actions": [
            {"title": "Assess Pain Meds Request", "status": "pending", "assigned_to_role": "clinician", "created_by_role": "staff"}
        ],
        "visibility_scope": {"patient": False, "staff": True, "clinician": True, "admin": True}
    },
    # 3. Clinician Note (Examination) - Visible to Clinician (NOT Staff, NOT Patient) - "Private/Draft"
    {
        "type": "clinician_note",
        "author_role": "clinician",
        "content": "Examination: \nGeneral: Alert, anxious. \nLungs: Diffuse expiratory wheezes bilaterally. Reduced air entry at bases. No crackles. \nHeart: Tachycardic, regular rhythm. \nImpression: Acute Asthma Exacerbation. \nPlan: \n1. Nebulized Albuterol/Ipratropium x3 \n2. IV Solu-Medrol 125mg \n3. Reassess in 20 mins.",
        "minutes_ago": 30,
        "highlights": [
            {"text": "Acute Asthma Exacerbation", "type": "risk", "reason": "Primary diagnosis"},
            {"text": "Reduced air entry", "type": "symptom", "reason": "Severity indicator"}
        ],
        "actions": [
            {"title": "Administer Nebulizers", "status": "pending", "assigned_to_role": "staff", "created_by_role": "clinician"},
            {"title": "Start IV Steroids", "status": "pending", "assigned_to_role": "staff", "created_by_role": "clinician"}
        ],
        "visibility_scope": {"patient": False, "staff": False, "clinician": True, "admin": True}, # Strict privacy for draft
        "history": [
            {
                "version": 1,
                "timestamp": get_time_offset(35),
                "content": "Examination: \nGeneral: Alert, anxious. \nLungs: Diffuse expiratory wheezes bilaterally. Reduced air entry at bases. No crackles. \nHeart: Tachycardic, regular rhythm. \nImpression: Acute Asthma Exacerbation. \nPlan: \n1. Nebulized Albuterol/Ipratropium x3 \n2. IV Solu-Medrol 40mg \n3. Reassess in 20 mins."
            }
        ],
        "version": 2
    },
    # 4. Staff Action Log (Treatment) - Visible to Staff, Clinician
    {
        "type": "staff_note",
        "author_role": "staff",
        "content": "Treatment Administered: \n1st Nebulizer started at 10:15. \nIV access established in R forearm. Solu-Medrol 125mg given IV push.",
        "minutes_ago": 20,
        "actions": [ # Resolved actions
             {"title": "Administer Nebulizers", "status": "resolved", "assigned_to_role": "staff", "created_by_role": "clinician", "resolution_comment": "Started 1st dose"},
             {"title": "Start IV Steroids", "status": "resolved", "assigned_to_role": "staff", "created_by_role": "clinician", "resolution_comment": "Given IV"}
        ],
        "visibility_scope": {"patient": False, "staff": True, "clinician": True, "admin": True}
    },
    # 5. AI Scribe Summary (Doctor Consult) - Visible to Clinician Only
    {
        "type": "ai_doctor_consult_summary",
        "author_role": "ai",
        "content": "## Consult Summary\n**History**: 45yo Male presenting with acute dyspnea. History of asthma. Failed home inhaler therapy.\n**Exam**: Wheezing +, SpO2 92%.\n**Assessment**: Moderate Asthma Exacerbation.\n**Plan**: \n- Continue nebs q20min.\n- Discharge if SpO2 > 95% and wheeze resolves.\n- Prescribe Prednisone burst (40mg x 5 days).",
        "minutes_ago": 10,
        "actions": [
            {"title": "Schedule Spirometry Test", "status": "pending", "assigned_to_role": "staff", "created_by_role": "ai"},
            {"title": "Verify Inhaler Technique", "status": "pending", "assigned_to_role": "staff", "created_by_role": "ai"}
        ],
        "visibility_scope": {"patient": False, "staff": False, "clinician": True, "admin": True}
    },
    # 6. Patient Discharge Instructions (AI Nurse) - Visible to Everyone (inc Patient)
    {
        "type": "ai_nurse_consult_summary",
        "author_role": "ai",
        "content": "## Discharge Instructions\n1. **Medications**: Take Prednisone (steroid pills) for 5 days with food. Continue inhaler every 4 hours.\n2. **Warning Signs**: Return to ER if lips turn blue, can't speak in full sentences, or inhaler stops working.\n3. **Follow-up**: See Dr. Smith in 3 days.",
        "minutes_ago": 5,
        "visibility_scope": {"patient": False, "staff": True, "clinician": True, "admin": True}
    },
    # 7. Patient Session Summary (AI) - Visible to Patient, Staff, Clinician
    {
        "type": "ai_patient_session_summary",
        "author_role": "ai",
        "content": "## Your Visit Summary\n**Reason for Visit**: Breathing difficulty.\n**Care Provided**: Nebulizer therapy and medication to improve lung function.\n**Plan**: \n1. Continue prescribed medication.\n2. Monitor breathing at home.\n3. Follow up in 3 days.",
        "minutes_ago": 2,
        "visibility_scope": {"patient": True, "staff": True, "clinician": True, "admin": True},
        "highlights": []
    }
]

# --- Build Note Objects ---
final_notes = []
for s in scenarios:
    note_id = generate_id()
    
    # Process Actions
    processed_actions = []
    if 'actions' in s:
        for a in s['actions']:
            processed_actions.append({
                "id": generate_id(),
                "title": a['title'],
                "status": a['status'],
                "created_by_role": a.get('created_by_role', 'system'),
                "assigned_to_role": a.get('assigned_to_role', 'clinician'),
                "provenance_note_id": note_id,
                "created_at": get_time_offset(s['minutes_ago']),
                "resolution_comment": a.get('resolution_comment', '')
            })
            
    # Process Highlights
    processed_highlights = []
    if 'highlights' in s:
        for h in s['highlights']:
            start = s['content'].find(h['text'])
            if start != -1:
                processed_highlights.append({
                    "id": generate_id(),
                    "text": h['text'],
                    "type": h['type'],
                    "reason": h['reason'],
                    "start": start,
                    "end": start + len(h['text'])
                })

    note = {
        "id": note_id,
        "content": s['content'],
        "author_role": s['author_role'],
        "type": s['type'],
        "timestamp": get_time_offset(s['minutes_ago']),
        "version": s.get('version', 1),
        "history": s.get('history', []),
        "highlights": processed_highlights,
        "actions": processed_actions,
        "visibility_scope": s['visibility_scope']
    }
    final_notes.append(note)

# --- Save & Encrypt ---
json_data = json.dumps(final_notes, indent=2).encode('utf-8')

# Load or Generate Key
if os.path.exists(KEY_FILE):
    with open(KEY_FILE, 'rb') as kf:
        key = kf.read()
else:
    key = Fernet.generate_key()
    with open(KEY_FILE, 'wb') as kf:
        kf.write(key)

cipher = Fernet(key)
encrypted_data = cipher.encrypt(json_data)

with open(OUTPUT_FILE, 'wb') as f:
    f.write(encrypted_data)

print(f"Successfully generated {len(final_notes)} synthetic notes.")
print(f"Data saved to {OUTPUT_FILE} (Encrypted).")
