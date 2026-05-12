from flask import Flask, render_template, request, redirect, session, send_file
import pandas as pd
from sklearn.preprocessing import StandardScaler
from datetime import datetime
import sqlite3
import pickle
from tensorflow.keras.models import load_model

# SECURITY
from werkzeug.security import generate_password_hash, check_password_hash

# PDF
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import letter
import subprocess

app = Flask(__name__)
app.secret_key = "secret123"


# =========================
# HOME
# =========================
@app.route('/')
def home():
    return render_template("home.html")

@app.route('/admin_notifications')
def admin_notifications():
    if 'admin' not in session:
        return redirect('/admin_login')

    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    # Users
    c.execute("SELECT username FROM users")
    users_list = c.fetchall()

    # ✅ Add this (recent notifications)
    c.execute("""
        SELECT username, message, priority, time
        FROM notifications
        ORDER BY time DESC
        LIMIT 10
    """)
    notifications = c.fetchall()

    conn.close()

    return render_template(
        "admin_notifications.html",
        users_list=users_list,
        notifications=notifications
    )  



# =========================
# REGISTER
# =========================
@app.route('/register', methods=['GET','POST'])
def register():
    if request.method == 'POST':
        user = request.form['username']
        pwd = request.form['password']

        conn = sqlite3.connect("database.db")
        c = conn.cursor()

        try:
            hashed = generate_password_hash(pwd)
            c.execute("INSERT INTO users VALUES (?,?,?)", (user, hashed, "active"))
            c.execute("INSERT INTO profiles VALUES (?,?,?,?)", (user, user, "", ""))
            conn.commit()
        except:
            return "User already exists"

        conn.close()
        return redirect('/login')

    return render_template("register.html")

# =========================
# LOGIN
# =========================
@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        user = request.form['username']
        pwd = request.form['password']

        conn = sqlite3.connect("database.db")
        c = conn.cursor()

        c.execute("SELECT * FROM users WHERE username=?", (user,))
        data = c.fetchone()
        conn.close()

        if data and check_password_hash(data[1], pwd):
            # ✅ CHECK STATUS
            if len(data) > 2 and data[2] == "inactive":
                return "Account deactivated by admin"

            session['user'] = user
            return redirect('/dashboard')

        return "Invalid Credentials"

    return render_template("login.html")

# =========================
# FORGOT PASSWORD
# =========================
@app.route('/forgot', methods=['GET','POST'])
def forgot():
    if request.method == 'POST':
        user = request.form['username']
        new_pwd = request.form['password']

        conn = sqlite3.connect("database.db")
        c = conn.cursor()

        hashed = generate_password_hash(new_pwd)
        c.execute("UPDATE users SET password=? WHERE username=?", (hashed, user))

        conn.commit()
        conn.close()

        return redirect('/login')

    return render_template("forgot.html")
# =========================
# DASHBOARD
# =========================
@app.route('/dashboard')
def dashboard():
    if 'user' not in session:
        return redirect('/login')

    user = session['user']

    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    # TOTAL REPORTS
    c.execute("SELECT COUNT(*) FROM history WHERE username=?", (user,))
    reports = c.fetchone()[0] or 0

    # HIGH RISK
    c.execute("""
        SELECT COUNT(*) FROM history
        WHERE username=? AND result LIKE '%Detected%'
    """, (user,))
    risk = c.fetchone()[0] or 0

    # HISTORY
    c.execute("""
        SELECT disease, result, probability, time
        FROM history
        WHERE username=?
        ORDER BY time DESC
    """, (user,))
    history = c.fetchall()

    # PROFILE
    c.execute("""
        SELECT name, email, contact
        FROM profiles
        WHERE username=?
    """, (user,))
    profile = c.fetchone() or ("", "", "")

    # REMINDERS
    c.execute("""
        SELECT message, remind_date
        FROM reminders
        WHERE username=?
    """, (user,))
    reminders = c.fetchall()

    conn.close()

    return render_template(
        "dashboard.html",
        username=user,
        reports=reports,
        risk=risk,
        history=history,
        profile=profile,
        reminders=reminders
    )


# =========================
# FEEDBACK PAGE  ✅ OUTSIDE
# =========================
@app.route('/feedback')
def feedback():
    if 'user' not in session:
        return redirect('/login')

    return render_template('feedback.html')


# =========================
# SUBMIT FEEDBACK  ✅ OUTSIDE
# =========================
@app.route('/submit_feedback', methods=['POST'])
def submit_feedback():
    if 'user' not in session:
        return redirect('/login')

    user = session['user']
    message = request.form['message']

    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    c.execute("""
        INSERT INTO feedback (username, message, time)
        VALUES (?, ?, datetime('now'))
    """, (user, message))

    conn.commit()
    conn.close()

    return render_template("feedback.html", message="Feedback submitted successfully!")

@app.route('/train_heart')
def train_heart():
    if 'admin' not in session:
        return redirect('/admin_login')

    subprocess.run(["python", "train.py"])

    return redirect('/admin_model')    


@app.route('/train_diabetes')
def train_diabetes():
    if 'admin' not in session:
        return redirect('/admin_login')

    subprocess.run(["python", "train.py"])

    return redirect('/admin_model')


# =========================
# USER NOTIFICATIONS
# =========================
@app.route('/notifications')
def user_notifications():
    if 'user' not in session:
        return redirect('/login')

    user = session['user']

    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    # GET GLOBAL + USER NOTIFICATIONS
    c.execute("""
        SELECT message 
        FROM notifications
        WHERE username='ALL' OR username=?
        ORDER BY id DESC
    """, (user,))

    notifications = c.fetchall()

    conn.close()

    return render_template("notifications.html", notifications=notifications)
# =========================
# PROFILE
# =========================
@app.route('/profile')
def profile():
    if 'user' not in session:
        return redirect('/login')
    user = session['user']

    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    c.execute("SELECT name, email, contact FROM profiles WHERE username=?", (user,))
    profile = c.fetchone()

    conn.close()

    return render_template("profile.html", profile=profile)

@app.route('/update_profile', methods=['POST'])
def update_profile():
    user = session['user']

    name = request.form['name']
    email = request.form['email']
    contact = request.form['contact']

    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    c.execute("UPDATE profiles SET name=?, email=?, contact=? WHERE username=?",
              (name, email, contact, user))

    conn.commit()
    conn.close()

    return redirect('/dashboard')
# =========================
# USER HISTORY (MEDICAL HISTORY)
# =========================
@app.route('/history')
def history_page():
    if 'user' not in session:
        return redirect('/login')

    user = session['user']

    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    c.execute("""
    SELECT rowid, disease, result, probability, time
    FROM history
    WHERE username=?
    ORDER BY time DESC
""", (user,))

    history = c.fetchall()
    conn.close()

    return render_template("history.html", history=history)
# =========================
# PAGES
# =========================
@app.route('/heart')
def heart():
    if 'user' not in session:
        return redirect('/login')
    return render_template("heart.html")

@app.route('/diabetes')
def diabetes():
    if 'user' not in session:
        return redirect('/login')
    return render_template("diabetes.html")
# =========================
# PREDICTION 
# =========================
@app.route('/predict', methods=['POST'])
def predict():
    if 'user' not in session:
        return redirect('/login')

    user = session['user']
    disease = request.form['disease']
    input_data = dict(request.form)

    try:

        # =========================
        # HEART MODEL
        # =========================
        if disease == "heart":

            features = [
                float(request.form.get('age')),
                float(request.form.get('sex')),
                float(request.form.get('cp')),
                float(request.form.get('trestbps')),
                float(request.form.get('chol')),
                float(request.form.get('fbs')),
                float(request.form.get('restecg')),
                float(request.form.get('thalach')),
                float(request.form.get('exang')),
                float(request.form.get('oldpeak')),
                float(request.form.get('slope')),
                float(request.form.get('ca')),
                float(request.form.get('thal'))
            ]

            # ✅ CLIP TO REALISTIC RANGES
            features[3] = min(features[3], 180)   # trestbps
            features[4] = min(features[4], 350)   # chol
            features[9] = min(features[9], 4)     # oldpeak

            scaler = pickle.load(open("heart_scaler.pkl", "rb"))
            model = pickle.load(open("heart_model.pkl", "rb"))

            data = scaler.transform([features])

            proba = model.predict_proba(data)[0][1]

            if proba >= 0.7:
                 result = "High Risk of Heart Disease"
            elif proba >= 0.4:
                result = "Medium Risk"
            else:
              result = "Low Risk"

            precaution = "Exercise & healthy diet"
            doctor = "Consult cardiologist"

        # =========================
        # DIABETES MODEL
        # =========================
        else:

            features = [
                float(request.form.get('pregnancies')),
                float(request.form.get('glucose')),
                float(request.form.get('bloodpressure')),
                float(request.form.get('skinthickness')),
                float(request.form.get('insulin')),
                float(request.form.get('bmi')),
                float(request.form.get('dpf')),
                float(request.form.get('age'))
            ]

        

            model = pickle.load(open("diabetes_model.pkl", "rb"))
            scaler = pickle.load(open("diabetes_scaler.pkl", "rb"))

            data = scaler.transform([features])

            proba = model.predict_proba(data)[0][1]

            if proba > 0.65:
                result = "High Risk of Diabetes"
            elif proba > 0.4:
                result = "Medium Risk"
            else:
                result = "Low Risk"

            precaution = "Control sugar & exercise"
            doctor = "Consult diabetologist"

        # =========================
        # COMMON
        # =========================
        prob = max(1, round(proba * 100, 2))  # avoid 0%
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        conn = sqlite3.connect("database.db")
        c = conn.cursor()

        c.execute("""
            INSERT INTO history (username, disease, result, probability, time)
            VALUES (?, ?, ?, ?, ?)
        """, (user, disease, result, prob, timestamp))

        conn.commit()
        conn.close()

        return render_template(
            "result.html",
            result=result,
            probability=prob,
            precaution=precaution,
            doctor=doctor,
            disease=disease,
            time=timestamp,
            inputs=input_data
        )

    except Exception as e:
        import traceback
        traceback.print_exc()
        return f"Error: {str(e)}"
# =========================
# DOWNLOAD PDF (IMPROVED)
# =========================
@app.route('/download/<disease>/<result>/<time>')
def download(disease, result, time):
    if 'user' not in session:
        return redirect('/login')

    user = session['user']
    filename = f"{user}_{time}.pdf".replace(":", "-")

    doc = SimpleDocTemplate(filename, pagesize=letter)
    styles = getSampleStyleSheet()
    content = []

    # 🔥 TITLE
    content.append(Paragraph(
        "<b><font size=18>AI Medical Diagnosis Report</font></b>",
        styles['Title']
    ))
    content.append(Spacer(1, 20))

    # 🔥 TABLE DATA
    data = [
        ["Field", "Details"],
        ["Patient Name", user],
        ["Disease", disease],
        ["Result", result],
        ["Date", time]
    ]

    table = Table(data, colWidths=[150, 250])

    # 🔥 STYLING
    table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.blue),
        ('TEXTCOLOR', (0,0), (-1,0), colors.white),

        ('BACKGROUND', (0,1), (-1,-1), colors.whitesmoke),
        ('GRID', (0,0), (-1,-1), 1, colors.black),

        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('PADDING', (0,0), (-1,-1), 10),
    ]))

    content.append(table)
    content.append(Spacer(1, 30))

    # 🔥 FOOTER
    content.append(Paragraph(
        "<i>This report is generated by an AI system. Please consult a doctor.</i>",
        styles['Normal']
    ))

    doc.build(content)

    return send_file(filename, as_attachment=True)


# =========================
# LOGOUT
# =========================
@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect('/login')


# =========================
# ADMIN SECTION 
# =========================


ADMIN_USER = "admin"
ADMIN_PASS = "admin123"

# =========================
# ADMIN LOGIN
# =========================
@app.route('/admin_login', methods=['GET','POST'])
def admin_login():
    if request.method == 'POST':
        if request.form['username'] == ADMIN_USER and request.form['password'] == ADMIN_PASS:
            session['admin'] = True
            return redirect('/admin_dashboard')
    return render_template("admin_login.html")


# =========================
# ADMIN DASHBOARD + RECENT ACTIVITY
# =========================
@app.route('/admin_dashboard')
def admin_dashboard():
    if 'admin' not in session:
        return redirect('/admin_login')

    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    c.execute("SELECT COUNT(*) FROM users")
    total_users = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM history")
    total_reports = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM feedback")
    total_feedback = c.fetchone()[0]

    c.execute("SELECT DISTINCT disease FROM history")
    diseases = c.fetchall()

    # RECENT ACTIVITY
    c.execute("""
        SELECT username, disease, result, time
        FROM history
        ORDER BY time DESC LIMIT 5
    """)
    recent = c.fetchall()

    conn.close()

    return render_template("admin_dashboard.html",
                           users=total_users,
                           reports=total_reports,
                           feedback=total_feedback,
                           diseases=len(diseases),
                           recent=recent)


# =========================
# VIEW USERS
# =========================
@app.route('/admin_users')
def admin_users():
    # 🔴 ADD THIS (IMPORTANT)
    if 'admin' not in session:
        return redirect('/admin_login')

    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    c.execute("SELECT * FROM users")
    users = c.fetchall()

    conn.close()
    return render_template("admin_users.html", users=users)
# =========================
# ADD USER
# =========================
@app.route('/add_user', methods=['POST'])
def add_user():

    # 🔴 ADD THIS (IMPORTANT)
    if 'admin' not in session:
        return redirect('/admin_login')

    username = request.form['username']
    password = generate_password_hash(request.form['password'])

    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    c.execute("""
    INSERT INTO users (username, password, status)
    VALUES (?, ?, ?)
    """, (username, password, "active"))

    conn.commit()
    conn.close()

    return redirect('/admin_users')

# =========================
# EDIT USER
# =========================
@app.route('/edit_user/<username>', methods=['GET','POST'])
def edit_user(username):
    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    if request.method == 'POST':
        new_username = request.form['username']
        new_password = generate_password_hash(request.form['password'])

        c.execute("UPDATE users SET username=?, password=? WHERE username=?",
                  (new_username, new_password, username))

        conn.commit()
        conn.close()
        return redirect('/admin_users')

    c.execute("SELECT * FROM users WHERE username=?", (username,))
    user = c.fetchone()
    conn.close()

    return render_template("edit_user.html", user=user)


# =========================
# TOGGLE USER STATUS
# =========================
@app.route('/toggle_user/<username>')
def toggle_user(username):
    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    c.execute("SELECT status FROM users WHERE username=?", (username,))
    status = c.fetchone()[0]

    new_status = "inactive" if status == "active" else "active"

    c.execute("UPDATE users SET status=? WHERE username=?", (new_status, username))

    conn.commit()
    conn.close()

    return redirect('/admin_users')


# =========================
# DELETE USER
# =========================
@app.route('/delete_user/<username>')
def delete_user(username):
    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    c.execute("DELETE FROM users WHERE username=?", (username,))
    c.execute("DELETE FROM profiles WHERE username=?", (username,))
    c.execute("DELETE FROM history WHERE username=?", (username,))

    conn.commit()
    conn.close()

    return redirect('/admin_users')


# =========================
# REPORTS + FILTER (UPDATED)
# =========================
@app.route('/admin_reports')
def admin_reports():
    disease = request.args.get('disease')

    conn = sqlite3.connect("database.db")

    # 🔥 IMPORTANT: use dictionary rows (no more index confusion)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    if disease:
        c.execute("""
            SELECT rowid, username, disease, result, probability, time
            FROM history
            WHERE disease=?
        """, (disease,))
    else:
        c.execute("""
            SELECT rowid, username, disease, result, probability, time
            FROM history
        """)

    reports = c.fetchall()
    conn.close()

    return render_template("admin_reports.html", reports=reports)

# =========================
# SEARCH RECORDS
# =========================
@app.route('/search_records', methods=['POST'])
def search_records():
    keyword = request.form['keyword']

    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    c.execute("""
        SELECT rowid, * FROM history
        WHERE username LIKE ? OR disease LIKE ?
    """, (f"%{keyword}%", f"%{keyword}%"))

    reports = c.fetchall()
    conn.close()

    return render_template("admin_reports.html", reports=reports)


# =========================
# DELETE REPORT
# =========================
@app.route('/delete_report/<int:id>')
def delete_report(id):
    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    c.execute("DELETE FROM history WHERE rowid=?", (id,))
    conn.commit()
    conn.close()

    return redirect('/history')


# =========================
# ADMIN DOWNLOAD REPORT
# =========================
@app.route('/admin_download/<int:id>')
def admin_download(id):
    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    c.execute("SELECT username, disease, result, time FROM history WHERE rowid=?", (id,))
    data = c.fetchone()
    conn.close()

    filename = f"report_{id}.pdf"

    doc = SimpleDocTemplate(filename)
    styles = getSampleStyleSheet()
    content = []

    content.append(Paragraph("Admin Report", styles['Title']))
    content.append(Spacer(1, 20))

    table = Table([
        ["User", data[0]],
        ["Disease", data[1]],
        ["Result", data[2]],
        ["Time", data[3]]
    ])

    content.append(table)
    doc.build(content)

    return send_file(filename, as_attachment=True)

@app.route('/admin_analytics')
def admin_analytics():

    if 'admin' not in session:
        return redirect('/admin_login')

    return render_template("admin_analytics.html")

@app.route('/api/admin_analytics')
def api_admin_analytics():

    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    # BAR
    c.execute("SELECT disease, COUNT(*) FROM history GROUP BY disease")
    data = c.fetchall()
    labels = [row[0] for row in data]
    values = [row[1] for row in data]

    # PIE
    c.execute("SELECT result, COUNT(*) FROM history GROUP BY result")
    result_data = c.fetchall()
    pie_labels = [row[0] for row in result_data]
    pie_values = [row[1] for row in result_data]

    # LINE
    c.execute("""
        SELECT substr(time,1,10), COUNT(*)
        FROM history
        GROUP BY substr(time,1,10)
        ORDER BY substr(time,1,10)
    """)
    trend_data = c.fetchall()
    trend_labels = [row[0] for row in trend_data]
    trend_values = [row[1] for row in trend_data]

    conn.close()

    return {
        "labels": labels,
        "values": values,
        "pie_labels": pie_labels,
        "pie_values": pie_values,
        "trend_labels": trend_labels,
        "trend_values": trend_values
    }


# =========================
# MODEL CONTROL PANEL
# =========================
@app.route('/admin_model')
def admin_model():
    if 'admin' not in session:
        return redirect('/admin_login')

    try:
        conn = sqlite3.connect("database.db")
        c = conn.cursor()

        # ✅ Create table if not exists
        c.execute("""
            CREATE TABLE IF NOT EXISTS model_info (
                model_name TEXT,
                accuracy REAL,
                last_trained TEXT
            )
        """)

        # ✅ Fetch data
        c.execute("""
            SELECT model_name, accuracy, last_trained
            FROM model_info
            ORDER BY last_trained DESC
        """)

        models = c.fetchall()

        # ✅ If empty → show default values
        if not models:
            models = [
                ("Heart Model", 0.92, "Not Trained"),
                ("Diabetes Model", 0.75, "Not Trained")
            ]

        conn.close()

        return render_template("admin_model.html", models=models)

    except Exception as e:
        return f"Error loading model panel: {str(e)}"


@app.route('/train_model/<model>')
def train_model(model):
    if 'admin' not in session:
        return redirect('/admin_login')

    try:
        # run training script
        subprocess.run(["python", "train.py"])

        return redirect('/admin_model')

    except Exception as e:
        return f"Training failed: {str(e)}"
 
# =========================
# SAVE MODEL
# =========================
@app.route('/save_model/<model>')
def save_model_admin(model):
    if 'admin' not in session:
        return redirect('/admin_login')

    return render_template("model_status.html", model=model, action="save", status=True)
# =========================
# FEEDBACK
# =========================
@app.route('/admin_feedback')
def admin_feedback():
    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    c.execute("SELECT * FROM feedback")
    feedback = c.fetchall()

    conn.close()
    return render_template("admin_feedback.html", feedback=feedback)


# =========================
# SEND NOTIFICATION
# =========================
@app.route('/send_notification', methods=['POST'])
def send_notification():
    if 'admin' not in session:
        return redirect('/admin_login')

    user = request.form['user']
    message = request.form['message']
    priority = request.form['priority']

    # Handle ALL users
    if user == "ALL":
        username = "ALL"
    else:
        username = user

    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    c.execute("""
        INSERT INTO notifications (username, message, priority, time)
        VALUES (?, ?, ?, datetime('now'))
    """, (username, message, priority))

    conn.commit()
    conn.close()

    # ✅ Stay on same page
    return redirect('/admin_notifications?success=1' )

# =========================
# ADMIN SETTINGS
# =========================
@app.route('/admin_settings', methods=['GET','POST'])
def admin_settings():
    global ADMIN_PASS

    if request.method == 'POST':
        ADMIN_PASS = request.form['password']
        return "Password updated"

    return render_template("admin_settings.html")
# =========================
# DISEASE MANAGEMENT
# =========================
@app.route('/admin_diseases')
def admin_diseases():
    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    c.execute("SELECT * FROM diseases")
    diseases = c.fetchall()

    conn.close()
    return render_template("admin_diseases.html", diseases=diseases)


@app.route('/add_disease', methods=['POST'])
def add_disease():
    name = request.form['name']
    desc = request.form['description']

    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    c.execute("INSERT INTO diseases VALUES (?,?)", (name, desc))

    conn.commit()
    conn.close()

    return redirect('/admin_diseases')


@app.route('/delete_disease/<name>')
def delete_disease(name):
    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    c.execute("DELETE FROM diseases WHERE name=?", (name,))

    conn.commit()
    conn.close()

    return redirect('/admin_diseases')
# =========================
# EDIT PATIENT RECORD
# =========================
@app.route('/edit_record/<int:id>', methods=['GET','POST'])
def edit_record(id):
    conn = sqlite3.connect("database.db")
    c = conn.cursor()

    if request.method == 'POST':
        disease = request.form['disease']
        result = request.form['result']

        c.execute("""
            UPDATE history
            SET disease=?, result=?
            WHERE rowid=?
        """, (disease, result, id))

        conn.commit()
        conn.close()

        return redirect('/admin_reports')

    c.execute("SELECT rowid, * FROM history WHERE rowid=?", (id,))
    record = c.fetchone()

    conn.close()

    return render_template("edit_record.html", record=record)
# =========================
# ADMIN LOGOUT
# =========================
@app.route('/admin_logout')
def admin_logout():
    session.pop('admin', None)
    return redirect('/admin_login')
# =========================
# RUN
# =========================
if __name__ == "__main__":
    app.run(debug=True)
