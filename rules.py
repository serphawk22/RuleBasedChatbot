import re
import pandas as pd
import os
import time

# ───────────────────────────────────────────────
# Dynamic Rule Loader (from Excel)
# ───────────────────────────────────────────────
EXCEL_FILE = "chatbot_rules.xlsx"
_cached_rules = []
_last_mtime = 0

def load_dynamic_rules():
    """Load or reload rules from Excel if the file has changed."""
    global _cached_rules, _last_mtime
    
    if not os.path.exists(EXCEL_FILE):
        return []

    try:
        current_mtime = os.path.getmtime(EXCEL_FILE)
        if current_mtime > _last_mtime:
            # File has changed or initial load
            df = pd.read_excel(EXCEL_FILE)
            rules = []
            for _, row in df.iterrows():
                if pd.isna(row['Pattern']) or pd.isna(row['Response']):
                    continue
                rules.append({
                    "pattern": str(row['Pattern']),
                    "response": str(row['Response'])
                })
            _cached_rules = rules
            _last_mtime = current_mtime
    except Exception as e:
        print(f"❌ Error loading Excel rules: {e}")
    
    return _cached_rules

# ───────────────────────────────────────────────
# Registration flow  (Name → Contact → Education)
# ───────────────────────────────────────────────
REGISTER_TRIGGER = re.compile(r"\b(register|enroll|join|admit|sign\s*up|enquiry|inquiry)\b", re.I)

REGISTRATION_STEPS = [
    {"field": "name",      "ask": "Sure! Let's get you started. What is your full name?"},
    {"field": "contact",   "ask": "Thanks, {name}! Could you share your contact number?"},
    {"field": "education", "ask": "Great! What is your highest level of education? (e.g. 10th, 12th, Graduate, Post-Graduate)"},
]

REGISTRATION_DONE = "✅ Thank you, {name}! Your details have been saved.\n\n📋 Name: {name}\n📞 Contact: {contact}\n🎓 Education: {education}\n\nOur counselor will reach out to you shortly. Meanwhile, feel free to ask about courses, fees, or placements!"


# ───────────── session handler ─────────────
# sessions dict:  session_id → {"step": int, "data": {...}}
_sessions: dict = {}


def get_response(user_input: str, session_id: str = "default") -> str:
    """Return a reply. Handles both rule matching and the registration flow."""
    text = user_input.strip()

    # ---- active registration flow ----
    if session_id in _sessions:
        session = _sessions[session_id]
        step_info = REGISTRATION_STEPS[session["step"]]
        session["data"][step_info["field"]] = text  # save the answer

        next_step = session["step"] + 1
        if next_step < len(REGISTRATION_STEPS):
            session["step"] = next_step
            return REGISTRATION_STEPS[next_step]["ask"].format(**session["data"])
        else:
            # All fields collected — finish up
            reply = REGISTRATION_DONE.format(**session["data"])
            del _sessions[session_id]
            return reply

    # ---- check for registration trigger ----
    if REGISTER_TRIGGER.search(text.lower()):
        _sessions[session_id] = {"step": 0, "data": {}}
        return REGISTRATION_STEPS[0]["ask"]

    # ---- normal dynamic keyword rules ----
    dynamic_rules = load_dynamic_rules()
    for rule in dynamic_rules:
        if re.search(rule["pattern"], text, re.I):
            return rule["response"]

    return FALLBACK
