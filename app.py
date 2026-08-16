import os
import sqlite3
from datetime import datetime
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from flask import Flask, render_template, request, redirect, url_for, flash, session, send_from_directory
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = "rov4love_kaptan_secret_key"
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "uploads")
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# Uploads klasörü yoksa oluştur
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

DB_PATH = os.path.join(os.path.dirname(__file__), "rov4love.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as db:
        # Kullanıcı Tablosu
        db.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT DEFAULT 'User', 
            status TEXT DEFAULT 'Pending', 
            tag TEXT DEFAULT 'Çaylak'
        )''')
        # Diğer Tablolar
        db.executescript('''
        CREATE TABLE IF NOT EXISTS activities (id INTEGER PRIMARY KEY AUTOINCREMENT, user_name TEXT, action TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS tasks (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, description TEXT, assignee TEXT, subsystem TEXT, priority TEXT, status TEXT DEFAULT 'Yapılacak', deadline TEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY AUTOINCREMENT, channel TEXT DEFAULT 'genel', user_name TEXT, tag TEXT, content TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS documents (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, category TEXT, description TEXT, file_path TEXT, link_url TEXT, author TEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS decisions (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, details TEXT, decision_date TEXT, status TEXT DEFAULT 'Kabul Edildi', decision_maker TEXT);
        ''')
        
        # --- MEHMET (KURUCU KAPTAN) HESABINI OTOMATİK OLUŞTUR ---
        user = db.execute("SELECT * FROM users WHERE username = 'mehmet'").fetchone()
        if not user:
            hashed_pw = generate_password_hash("ruhi 123")
            db.execute("INSERT INTO users (username, password, role, status, tag) VALUES (?, ?, ?, ?, ?)", 
                       ("mehmet", hashed_pw, "Admin", "Approved", "Kurucu Kaptan"))
            
        db.commit()

init_db()

# --- YETKİLENDİRME KONTROLLERİ ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        if session.get('status') != 'Approved':
            flash("Hesabınız Kaptan tarafından henüz onaylanmadı. Lütfen bekleyin.", "error")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get('role') != 'Admin':
            flash("Erişim Reddedildi. Sadece Kaptan girebilir.", "error")
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

def log_activity(user_name, action):
    with get_db() as db:
        db.execute("INSERT INTO activities (user_name, action) VALUES (?, ?)", (user_name, action))
        db.commit()

# --- GİRİŞ / KAYIT SİSTEMİ ---
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username").strip()
        password = request.form.get("password")
        
        with get_db() as db:
            user = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
            if user:
                flash("Bu isim zaten alınmış!", "error")
                return redirect(url_for('register'))
            
            # Artık herkes standart kullanıcı ve onay bekliyor olarak kayıt olur
            hashed_pw = generate_password_hash(password)
            db.execute("INSERT INTO users (username, password, role, status, tag) VALUES (?, ?, 'User', 'Pending', 'Çaylak')", 
                       (username, hashed_pw))
            db.commit()
            
        flash("Kayıt başarılı! Kaptan onayından sonra giriş yapabilirsiniz.", "success")
        return redirect(url_for('login'))
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username").strip()
        password = request.form.get("password")
        
        with get_db() as db:
            user = db.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
            
            if user and check_password_hash(user["password"], password):
                session["user_id"] = user["id"]
                session["username"] = user["username"]
                session["role"] = user["role"]
                session["status"] = user["status"]
                session["tag"] = user["tag"]
                
                if user["status"] == "Pending":
                    session.clear()
                    flash("Hesabınız Kaptan onayında bekliyor.", "error")
                    return redirect(url_for('login'))
                    
                log_activity(username, "Sisteme giriş yaptı.")
                return redirect(url_for('index'))
            else:
                flash("Hatalı kullanıcı adı veya şifre!", "error")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for('login'))

# --- ADMIN PANELİ ---
@app.route("/admin")
@login_required
@admin_required
def admin_panel():
    with get_db() as db:
        users = db.execute("SELECT * FROM users ORDER BY id DESC").fetchall()
    return render_template("admin.html", users=users)

@app.route("/admin/approve/<int:user_id>")
@login_required
@admin_required
def approve_user(user_id):
    with get_db() as db:
        db.execute("UPDATE users SET status = 'Approved' WHERE id = ?", (user_id,))
        db.commit()
    flash("Kullanıcı onaylandı!", "success")
    return redirect(url_for('admin_panel'))

@app.route("/admin/update_tag", methods=["POST"])
@login_required
@admin_required
def update_tag():
    user_id = request.form.get("user_id")
    new_tag = request.form.get("tag")
    new_role = request.form.get("role")
    
    with get_db() as db:
        target_user = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        
        # Sadece mehmet yetki (Admin/User) değiştirebilir
        if new_role and new_role != target_user['role']:
            if session.get('username') != 'mehmet':
                flash("Erişim Reddedildi: Sadece Kurucu Kaptan yetki seviyelerini değiştirebilir!", "error")
                new_role = target_user['role'] # Değişikliği iptal et
                
        # Mehmet'in kendi yetkisini yanlışlıkla düşürmesini engelle
        if target_user['username'] == 'mehmet' and new_role != 'Admin':
            new_role = 'Admin'

        db.execute("UPDATE users SET tag = ?, role = ? WHERE id = ?", (new_tag, new_role, user_id))
        db.commit()
        
    flash("Kullanıcı bilgileri güncellendi!", "success")
    return redirect(url_for('admin_panel'))

# --- ANA SAYFA VE KANBAN ---
@app.route("/")
@login_required
def index():
    with get_db() as db:
        tasks = db.execute("SELECT * FROM tasks ORDER BY id DESC").fetchall()
        activities = db.execute("SELECT * FROM activities ORDER BY timestamp DESC LIMIT 8").fetchall()
        stats = {
            "total": len(tasks),
            "completed": sum(1 for t in tasks if t["status"] == "Tamamlandı"),
            "in_progress": sum(1 for t in tasks if t["status"] == "Devam Ediyor"),
            "urgent": sum(1 for t in tasks if t["priority"] == "Acil" and t["status"] != "Tamamlandı")
        }
    return render_template("index.html", tasks=tasks, activities=activities, stats=stats)

@app.route("/kanban")
@login_required
def kanban():
    with get_db() as db:
        tasks = db.execute("SELECT * FROM tasks ORDER BY id DESC").fetchall()
    return render_template("kanban.html", tasks=tasks)

@app.route("/task/create", methods=["POST"])
@login_required
def create_task():
    title = request.form.get("title")
    description = request.form.get("description")
    assignee = request.form.get("assignee")
    subsystem = request.form.get("subsystem")
    priority = request.form.get("priority")
    deadline = request.form.get("deadline")
    
    with get_db() as db:
        db.execute("INSERT INTO tasks (title, description, assignee, subsystem, priority, deadline) VALUES (?, ?, ?, ?, ?, ?)",
            (title, description, assignee, subsystem, priority, deadline))
        db.commit()
    log_activity(session.get('username'), f"'{title}' görevini oluşturdu.")
    flash("Görev başarıyla oluşturuldu!", "success")
    return redirect(request.referrer or url_for("kanban"))

@app.route("/task/update_status/<int:task_id>/<string:new_status>")
@login_required
def update_task_status(task_id, new_status):
    with get_db() as db:
        task = db.execute("SELECT title FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if task:
            db.execute("UPDATE tasks SET status = ? WHERE id = ?", (new_status, task_id))
            db.commit()
            log_activity(session.get('username'), f"'{task['title']}' durumunu '{new_status}' olarak güncelledi.")
    return redirect(request.referrer or url_for("kanban"))

# --- SOHBET (CHAT) SİSTEMİ ---
@app.route("/chat", methods=["GET", "POST"])
@login_required
def chat():
    active_channel = request.args.get("channel", "genel")
    target_dm = request.args.get("dm", None)
    
    with get_db() as db:
        # Kişisel mesajlar için diğer kullanıcıları çek
        users = db.execute("SELECT username, tag FROM users WHERE username != ?", (session['username'],)).fetchall()
        
        if target_dm:
            # İki kullanıcı arasında alfabetik sıraya göre benzersiz bir oda adı oluştur
            u_list = sorted([session['username'], target_dm])
            room = f"dm_{u_list[0]}_{u_list[1]}"
            current_target = target_dm
        else:
            room = active_channel
            current_target = None
            
        messages = db.execute("SELECT * FROM messages WHERE channel = ? ORDER BY timestamp ASC", (room,)).fetchall()

    if request.method == "POST":
        content = request.form.get("content", "").strip()
        dest_room = request.form.get("room", room)
        if content:
            with get_db() as db:
                db.execute("INSERT INTO messages (channel, user_name, tag, content) VALUES (?, ?, ?, ?)", 
                           (dest_room, session['username'], session['tag'], content))
                db.commit()
            
            # Yönlendirmeyi doğru yere yap
            if dest_room.startswith("dm_"):
                parts = dest_room.split("_")
                other = parts[1] if parts[1] != session['username'] else parts[2]
                return redirect(url_for('chat', dm=other))
            else:
                return redirect(url_for('chat', channel=dest_room))
                
    return render_template("chat.html", 
                           messages=messages, 
                           active_channel=active_channel, 
                           target_dm=current_target, 
                           users=users,
                           current_room=room)

# --- DOKÜMAN / WIKI SİSTEMİ ---
@app.route("/wiki")
@login_required
def wiki():
    with get_db() as db:
        docs = db.execute("SELECT * FROM documents ORDER BY created_at DESC").fetchall()
    return render_template("wiki.html", docs=docs)

@app.route("/wiki/upload", methods=["POST"])
@login_required
def upload_wiki():
    title = request.form.get("title")
    category = request.form.get("category")
    description = request.form.get("description")
    link_url = request.form.get("link_url")
    
    file = request.files.get("doc_file")
    file_path = None
    if file and file.filename != "":
        fname = secure_filename(file.filename)
        file.save(os.path.join(app.config["UPLOAD_FOLDER"], fname))
        file_path = fname
        
    with get_db() as db:
        db.execute("INSERT INTO documents (title, category, description, file_path, link_url, author) VALUES (?, ?, ?, ?, ?, ?)",
            (title, category, description, file_path, link_url, session.get('username')))
        db.commit()
    log_activity(session.get('username'), f"'{title}' başlıklı teknik dokümanı ekledi.")
    flash("Doküman/Link başarıyla eklendi!", "success")
    return redirect(url_for("wiki"))

@app.route("/uploads/<filename>")
@login_required
def uploaded_file(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

# --- KARAR DEFTERİ ---
@app.route("/decisions")
@login_required
def decisions():
    with get_db() as db:
        decision_list = db.execute("SELECT * FROM decisions ORDER BY id DESC").fetchall()
    return render_template("decisions.html", decisions=decision_list)

@app.route("/decisions/create", methods=["POST"])
@login_required
@admin_required
def create_decision():
    title = request.form.get("title")
    details = request.form.get("details")
    decision_date = request.form.get("decision_date", datetime.now().strftime("%Y-%m-%d"))
    
    with get_db() as db:
        db.execute("INSERT INTO decisions (title, details, decision_date, decision_maker) VALUES (?, ?, ?, ?)",
            (title, details, decision_date, session.get('username')))
        db.commit()
    log_activity(session.get('username'), f"Karar defterine işlendi: '{title}'")
    flash("Karar defterine başarıyla eklendi!", "success")
    return redirect(url_for("decisions"))

if __name__ == "__main__":
    app.run(debug=True, host='0.0.0.0', port=5000)
