import os
import sqlite3
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_from_directory
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = "rov4love_secret_key_2026"
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "uploads")
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
DB_PATH = os.path.join(os.path.dirname(__file__), "rov4love.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS activities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_name TEXT,
            action TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            assignee TEXT,
            subsystem TEXT, -- Yazılım, Elektronik, Mekanik, Kaptan
            priority TEXT, -- Acil, Normal, Düşük
            status TEXT DEFAULT 'Yapılacak', -- Yapılacak, Devam Ediyor, Test/İnceleme, Tamamlandı
            deadline TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            channel TEXT DEFAULT 'genel', -- genel, yazilim, elektronik, mekanik
            user_name TEXT NOT NULL,
            content TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            category TEXT,
            description TEXT,
            file_path TEXT,
            link_url TEXT,
            author TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            details TEXT,
            decision_date TEXT,
            status TEXT DEFAULT 'Kabul Edildi',
            decision_maker TEXT
        );
        ''')
        
        # Populate demo initial data if tasks empty
        cur = db.cursor()
        cur.execute("SELECT count(*) as count FROM tasks")
        if cur.fetchone()["count"] == 0:
            sample_tasks = [
                ("O-Ring ve Basınç Tüpü Sızdırmazlık Testi", "10 bar basınca kadar sızdırmazlık simülasyonu ve test havuzu doğrulaması.", "Mekanik Ekip", "Mekanik", "Acil", "Devam Ediyor", "2026-08-25"),
                ("ArduSub SITL + MAVROS Otonom Yanaşma", "OpenCV ile pinger/ışık kaynağına kilitlenen visual servoing kontrolcüsü.", "Yazılım Ekip", "Yazılım", "Acil", "Yapılacak", "2026-08-22"),
                ("Güç Dağıtım Kartı (PDB) & ESC Bağlantıları", "Thruster güç hatlarının gürültü izolasyonu ve akım sensörü kalibrasyonu.", "Elektronik Ekip", "Elektronik", "Normal", "Test/İnceleme", "2026-08-28"),
                ("KTR (Kavramsal Tasarım Raporu) Revizyonu", "Şasi analizi ve ağırlık merkezi hesaplamalarının rapora eklenmesi.", "Kaptan", "Kaptan", "Düşük", "Tamamlandı", "2026-08-15")
            ]
            for t in sample_tasks:
                db.execute("INSERT INTO tasks (title, description, assignee, subsystem, priority, status, deadline) VALUES (?, ?, ?, ?, ?, ?, ?)", t)
            
            sample_messages = [
                ("genel", "Kaptan", "Beyler rov4love komuta portalı açıldı! Görevleri Kanban panosundan takip ediyoruz."),
                ("genel", "Gökalp", "Mekanik şasi güncellemelerini dosya deposuna yükledim."),
                ("yazilim", "Yazılımcı", "SITL üzerinde OpenCV pinger takip algoritmasını test etmeye başlıyorum."),
                ("elektronik", "Elektronikçi", "Pixhawk 2.4.8 telemetri bağlantıları hazır.")
            ]
            for m in sample_messages:
                db.execute("INSERT INTO messages (channel, user_name, content) VALUES (?, ?, ?)", m)

            sample_activities = [
                ("Kaptan", "rov4love komuta merkezini aktif hale getirdi."),
                ("Mekanik Ekip", "O-Ring sızdırmazlık görevini 'Devam Ediyor' durumuna aldı."),
                ("Yazılım Ekip", "Visual Servoing modülü için test ortamı hazırladı.")
            ]
            for a in sample_activities:
                db.execute("INSERT INTO activities (user_name, action) VALUES (?, ?)", a)
                
            sample_decisions = [
                ("Ana Şasi Malzeme Seçimi", "Ağırlık/dayanım optimizasyonu için şaside lazer kesim pleksi/delrin ve karbon fiber takviye kararlaştırıldı.", "2026-08-10", "Kabul Edildi", "Kaptan"),
                ("İtiş Sistemi Konfigürasyonu", "Vektörel 6 thruster düzenine geçildi (4 yatay açılı, 2 dikey).", "2026-08-12", "Kabul Edildi", "Takım Ortak")
            ]
            for d in sample_decisions:
                db.execute("INSERT INTO decisions (title, details, decision_date, status, decision_maker) VALUES (?, ?, ?, ?, ?)", d)

            db.commit()

init_db()

def log_activity(user_name, action):
    with get_db() as db:
        db.execute("INSERT INTO activities (user_name, action) VALUES (?, ?)", (user_name, action))
        db.commit()

@app.route("/")
def index():
    with get_db() as db:
        tasks = db.execute("SELECT * FROM tasks ORDER BY id DESC").fetchall()
        activities = db.execute("SELECT * FROM activities ORDER BY timestamp DESC LIMIT 8").fetchall()
        decisions = db.execute("SELECT * FROM decisions ORDER BY id DESC LIMIT 5").fetchall()
        docs = db.execute("SELECT * FROM documents ORDER BY id DESC LIMIT 5").fetchall()
        
        # Count stats
        total_tasks = len(tasks)
        completed_tasks = sum(1 for t in tasks if t["status"] == "Tamamlandı")
        in_progress = sum(1 for t in tasks if t["status"] == "Devam Ediyor")
        urgent_tasks = sum(1 for t in tasks if t["priority"] == "Acil" and t["status"] != "Tamamlandı")

    return render_template("index.html", 
                           tasks=tasks, 
                           activities=activities, 
                           decisions=decisions,
                           docs=docs,
                           stats={
                               "total": total_tasks,
                               "completed": completed_tasks,
                               "in_progress": in_progress,
                               "urgent": urgent_tasks
                           })

@app.route("/kanban")
def kanban():
    with get_db() as db:
        tasks = db.execute("SELECT * FROM tasks ORDER BY id DESC").fetchall()
    return render_template("kanban.html", tasks=tasks)

@app.route("/task/create", methods=["POST"])
def create_task():
    title = request.form.get("title")
    description = request.form.get("description")
    assignee = request.form.get("assignee")
    subsystem = request.form.get("subsystem")
    priority = request.form.get("priority")
    deadline = request.form.get("deadline")
    
    with get_db() as db:
        db.execute(
            "INSERT INTO tasks (title, description, assignee, subsystem, priority, deadline) VALUES (?, ?, ?, ?, ?, ?)",
            (title, description, assignee, subsystem, priority, deadline)
        )
        db.commit()
    log_activity(assignee or "Kaptan", f"'{title}' yeni görevini oluşturdu.")
    flash("Görev başarıyla oluşturuldu!", "success")
    return redirect(request.referrer or url_for("kanban"))

@app.route("/task/update_status/<int:task_id>/<string:new_status>")
def update_task_status(task_id, new_status):
    with get_db() as db:
        task = db.execute("SELECT title FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if task:
            db.execute("UPDATE tasks SET status = ? WHERE id = ?", (new_status, task_id))
            db.commit()
            log_activity("Kaptan/Üye", f"'{task['title']}' durumunu '{new_status}' olarak güncelledi.")
    return redirect(request.referrer or url_for("kanban"))

@app.route("/chat")
@app.route("/chat/<string:channel>")
def chat(channel="genel"):
    valid_channels = ["genel", "yazilim", "elektronik", "mekanik"]
    if channel not in valid_channels:
        channel = "genel"
    with get_db() as db:
        messages = db.execute("SELECT * FROM messages WHERE channel = ? ORDER BY timestamp ASC", (channel,)).fetchall()
    return render_template("chat.html", channel=channel, messages=messages)

@app.route("/chat/send", methods=["POST"])
def send_message():
    channel = request.form.get("channel", "genel")
    user_name = request.form.get("user_name", "Anonim")
    content = request.form.get("content", "").strip()
    
    if content:
        with get_db() as db:
            db.execute("INSERT INTO messages (channel, user_name, content) VALUES (?, ?, ?)", (channel, user_name, content))
            db.commit()
        log_activity(user_name, f"#{channel} odasına yeni mesaj gönderdi.")
    return redirect(url_for("chat", channel=channel))

@app.route("/wiki")
def wiki():
    with get_db() as db:
        docs = db.execute("SELECT * FROM documents ORDER BY created_at DESC").fetchall()
    return render_template("wiki.html", docs=docs)

@app.route("/wiki/upload", methods=["POST"])
def upload_wiki():
    title = request.form.get("title")
    category = request.form.get("category")
    description = request.form.get("description")
    link_url = request.form.get("link_url")
    author = request.form.get("author", "Kaptan")
    
    file = request.files.get("doc_file")
    file_path = None
    if file and file.filename != "":
        fname = secure_filename(file.filename)
        file.save(os.path.join(app.config["UPLOAD_FOLDER"], fname))
        file_path = fname
        
    with get_db() as db:
        db.execute(
            "INSERT INTO documents (title, category, description, file_path, link_url, author) VALUES (?, ?, ?, ?, ?, ?)",
            (title, category, description, file_path, link_url, author)
        )
        db.commit()
    log_activity(author, f"'{title}' başlıklı teknik dokümanı/kaynağı ekledi.")
    flash("Doküman/Link başarıyla eklendi!", "success")
    return redirect(url_for("wiki"))

@app.route("/uploads/<filename>")
def uploaded_file(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

@app.route("/decisions")
def decisions():
    with get_db() as db:
        decision_list = db.execute("SELECT * FROM decisions ORDER BY id DESC").fetchall()
    return render_template("decisions.html", decisions=decision_list)

@app.route("/decisions/create", methods=["POST"])
def create_decision():
    title = request.form.get("title")
    details = request.form.get("details")
    decision_date = request.form.get("decision_date", datetime.now().strftime("%Y-%m-%d"))
    decision_maker = request.form.get("decision_maker", "Kaptan")
    
    with get_db() as db:
        db.execute(
            "INSERT INTO decisions (title, details, decision_date, decision_maker) VALUES (?, ?, ?, ?)",
            (title, details, decision_date, decision_maker)
        )
        db.commit()
    log_activity(decision_maker, f"Yeni stratejik karar defterine işlendi: '{title}'")
    flash("Karar defterine başarıyla eklendi!", "success")
    return redirect(url_for("decisions"))

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
