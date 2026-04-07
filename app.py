from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from rules import get_response, load_dynamic_rules
import sqlite3
import pandas as pd
import os

app = Flask(__name__, static_folder="templates", static_url_path="/static")
app.secret_key = "ally_tech_secret_key"  # Change this in production

# ─── Configuration ───
DATABASE = "allybot.db"
EXCEL_FILE = "chatbot_rules.xlsx"
ADMIN_PASSWORD = "allybot1122"  # Password to protect the data

def init_db():
    """Create database table if it doesn't exist and ensure schema is up to date."""
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

# ─── Routes ───

@app.route("/")
def home():
    return render_template("index.html")

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
    
    # Load rules for the dashboard
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
        df = pd.DataFrame(new_rules)
        df.to_excel(EXCEL_FILE, index=False)
        return jsonify({"success": True, "message": "Rules updated successfully!"})
    except PermissionError:
        return jsonify({"success": False, "message": "Error: Please close the 'chatbot_rules.xlsx' file in Excel before saving changes."}), 500
    except Exception as e:
        return jsonify({"success": False, "message": f"Server Error: {str(e)}"}), 500

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
        if "ba" == q:
            recommendation = "Since you have a BA degree, we recommend ERP FICO, Advanced Excel, VBA, and SQL."
        elif any(x in q for x in ["bsc", "bca", "be", "btech", "science"]):
            recommendation = "With your technical background, we recommend ERP ABAP, ERP MM, Python, SQL, and Power BI."
        elif any(x in q for x in ["bba", "bbm", "business"]):
            recommendation = "For your business background, we suggest ERP FICO, ERP MM, Power BI, and Advanced Excel."
        else:
            recommendation = "We recommend starting with Data Analytics (Excel, VBA, SQL) or a functional ERP module like MM."

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

if __name__ == "__main__":
    init_db()
    app.run(debug=True, port=5000)
