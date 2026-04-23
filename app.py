from flask import Flask, render_template, request, jsonify, session, redirect, url_for, Response
from rules import get_response, load_dynamic_rules
import sqlite3
import pandas as pd
import os
import sys
import io
import requests

# Force UTF-8 for Windows console
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

app = Flask(__name__, static_folder="templates", static_url_path="/static")
app.secret_key = "7b2d9a4f6c1e3b5d8a0f9c2e4b7d1a5f6c8e0b2d4a9f3c1e5b7d8a0f2c4e6b9d"  # Auto-generated secure key

# --- Configuration ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# If running on Railway (or Render/Docker with a volume), save to the persistent volume mount point.
if os.environ.get("RAILWAY_ENVIRONMENT") or os.environ.get("RENDER"):
    DATABASE = "/app/data/allybot.db"
else:
    DATABASE = os.path.join(BASE_DIR, "allybot.db")
    
ADMIN_PASSWORD = "allybot1122"
GSCRIPT_URL = "https://script.google.com/macros/s/AKfycbzmnebKFLBtD1gJYXdGQo70-V0Qy4Ly3fLiBFkIkPwLP-Dzmvxj8suMuBYWzQucEBY5SQ/exec"

def init_db():
    """Create database table if it doesn't exist and ensure schema is up to date."""
    db_dir = os.path.dirname(DATABASE)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS registrations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            phone TEXT NOT NULL,
            course TEXT NOT NULL,
            registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("PRAGMA table_info(registrations)")
    columns = [row[1] for row in cursor.fetchall()]
    if "qualification" not in columns:
        cursor.execute("ALTER TABLE registrations ADD COLUMN qualification TEXT")
    conn.commit()
    conn.close()

# --- Routes ---

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/favicon.ico")
def favicon():
    return app.send_static_file("logo.jpg")  # Use logo as temporary favicon or point to actual ico

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        pw = request.form.get("password")
        if pw == ADMIN_PASSWORD:
            session["admin_logged_in"] = True
            return redirect(url_for("admin_dashboard"))
        return render_template("admin_login.html", error="Invalid Password")
    return render_template("admin_login.html")

@app.route("/admin")
def admin_dashboard():
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_login"))
    
    # Load rules from Google Sheets
    rules = load_dynamic_rules()
    
    # Load registrations
    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM registrations ORDER BY registered_at DESC")
    regs = cursor.fetchall()
    conn.close()
    
    return render_template("admin_dashboard.html", rules=rules, registrations=regs)

@app.route("/admin/save_rules", methods=["POST"])
def save_rules():
    if not session.get("admin_logged_in"):
        return jsonify({"success": False, "message": "Unauthorized"}), 403
    
    try:
        new_rules = request.json.get("rules", [])
        
        # Push ONLY to Google Sheets (via Apps Script)
        print("Pushing updates to Google Sheets...")
        resp = requests.post(GSCRIPT_URL, json={"rules": new_rules}, timeout=10)
        
        if resp.status_code == 200:
            print("Cloud sync successful.")
            return jsonify({"success": True, "message": "Rules synced to Google Sheets successfully!"})
        else:
            print(f"Cloud sync failed with status: {resp.status_code}")
            return jsonify({"success": False, "message": f"Cloud Sync Failed: {resp.status_code}"}), 500

    except Exception as e:
        return jsonify({"success": False, "message": f"Server Error: {str(e)}"}), 500

@app.route("/admin/download_csv")
def download_csv():
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_login"))
    
    date_from = request.args.get("date_from", "")
    date_to = request.args.get("date_to", "")

    conn = sqlite3.connect(DATABASE)
    cursor = conn.cursor()

    query = "SELECT id, name, email, phone, course, registered_at, qualification FROM registrations"
    params = []

    if date_from and date_to:
        query += " WHERE DATE(registered_at) BETWEEN ? AND ?"
        params = [date_from, date_to]
    elif date_from:
        query += " WHERE DATE(registered_at) >= ?"
        params = [date_from]
    elif date_to:
        query += " WHERE DATE(registered_at) <= ?"
        params = [date_to]

    query += " ORDER BY registered_at DESC"
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    # Build CSV content
    csv_output = io.StringIO()
    csv_output.write("ID,Name,Email,Phone,Course,Registered At,Qualification\n")
    for row in rows:
        fields = []
        for val in row:
            val_str = str(val) if val is not None else ""
            if "," in val_str or '"' in val_str or "\n" in val_str:
                val_str = '"' + val_str.replace('"', '""') + '"'
            fields.append(val_str)
        csv_output.write(",".join(fields) + "\n")

    # Dynamic filename
    fname = "registrations"
    if date_from:
        fname += f"_from_{date_from}"
    if date_to:
        fname += f"_to_{date_to}"
    fname += ".csv"

    return Response(
        csv_output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment;filename={fname}"}
    )


@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_logged_in", None)
    return redirect(url_for("admin_login"))

@app.route("/register", methods=["POST"])
def register():
    data = request.json
    name = data.get("name", "").strip()
    email = data.get("email", "").strip()
    phone = data.get("phone", "").strip()
    course = data.get("course", "").strip()
    qualification = data.get("qualification", "").strip()

    if not all([name, email, phone, course, qualification]):
        return jsonify({"success": False, "message": "All fields are required."}), 400

    try:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO registrations (name, email, phone, course, qualification) VALUES (?, ?, ?, ?, ?)",
            (name, email, phone, course, qualification)
        )
        conn.commit()
        conn.close()

        # Recommendation logic
        recommendation = ""
        q = qualification.lower()
        
        if q == "other" or not q:
            recommendation = "Could you please tell me which subjects you're interested in or what kind of career path you're looking for? I'd love to help you find the perfect course for your goals!"
        elif "ba" == q:
            recommendation = "Since you have a BA degree, we recommend starting with functional ERP module like **FICO** to kickstart your corporate career."
        elif any(x in q for x in ["bsc", "bca", "be", "btech", "science"]):
            recommendation = "With your technical background, we highly recommend **Data Analytics** (Advanced Excel, VBA, SQL), **ERP ABAP**, **Python**, or **SQL & Power BI** to leverage your analytical skills."
        elif any(x in q for x in ["bba", "bbm", "bcom", "business","graduate"]):
            recommendation = "For your business and commerce background, we suggest**ERP Modules**, **Data Analytics** (Advanced Excel, VBA, SQL), **Power BI** to enhance your management and financial reporting capabilities."
        elif any(x in q for x in ["post graduate"]):
            recommendation = "As a Post Graduate, we recommend exploring **Advanced ERP Modules**, or **Data Analytics** to transition into leadership or specialist roles."
        else:
            recommendation = "Based on your profile, we recommend starting with **Data Analytics** (Excel, VBA, SQL) or a functional ERP modules."

        return jsonify({
            "success": True, 
            "message": f"Welcome {name}! You're registered successfully.",
            "recommendation": recommendation
        })
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

@app.route("/chat", methods=["POST"])
def chat():
    user_message = request.json.get("message", "")
    reply = get_response(user_message)
    return jsonify({"reply": reply})

# Initialize database on startup (crucial for Gunicorn)
init_db()

if __name__ == "__main__":
    app.run(debug=True, port=5000)
