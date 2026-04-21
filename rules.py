import re
import pandas as pd
import os
import time

# ===============================================
# Constants
# ===============================================
FALLBACK = "I'm sorry, I don't understand that. Could you please rephrase? Or type 'register' to enroll!"

# ===============================================
# Rule Sources (Google Sheets Only)
# ===============================================
SHEET_ID = "1BLG8o_11SNQYIA31ghc-4TrgGFWqZs5vFUhK6WuX1q4"
GOOGLE_SHEET_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv"

_cached_rules = []
_last_fetch_time = 0
CACHE_DURATION = 60  # Cache rules for 60 seconds

def load_dynamic_rules():
    """Load rules ONLY from Google Sheets."""
    global _cached_rules, _last_fetch_time
    
    current_time = time.time()
    
    # Fetch from Google Sheets if cache expired
    if current_time - _last_fetch_time > CACHE_DURATION:
        try:
            print("Fetching rules from Google Sheets...")
            df = pd.read_csv(GOOGLE_SHEET_URL)
            rules = []
            for _, row in df.iterrows():
                pattern = row.get('Pattern') or row.get('pattern')
                response = row.get('Response') or row.get('response')
                if not pd.isna(pattern) and not pd.isna(response):
                    rules.append({"pattern": str(pattern), "response": str(response)})
            
            if rules:
                _cached_rules = rules
                _last_fetch_time = current_time
                print(f"Loaded {len(_cached_rules)} rules from Google Sheets.")
        except Exception as e:
            print("Google Sheets fetch failed (check connectivity or sheet permissions).")

    return _cached_rules

# ===============================================
# Registration flow
# ===============================================
REGISTER_TRIGGER = re.compile(r"\b(register|enroll|join|admit|sign\s*up|enquiry|inquiry)\b", re.I)

REGISTRATION_STEPS = [
    {"field": "name",      "ask": "Sure! Let's get you started. What is your full name?"},
    {"field": "contact",   "ask": "Thanks, {name}! Could you share your contact number?"},
    {"field": "education", "ask": "Great! What is your highest level of education? (e.g. 10th, 12th, Graduate, Post-Graduate)"},
]

REGISTRATION_DONE = "Success! Thank you, {name}! Your details have been saved.\n\nName: {name}\nContact: {contact}\nEducation: {education}\n\nOur counselor will reach out to you shortly."

# ===============================================
# Session Handler
# ===============================================
_sessions = {}

def get_response(user_input, session_id="default"):
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
