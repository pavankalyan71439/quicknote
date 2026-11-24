
import os
import re
import sqlite3
from datetime import datetime, timezone
from functools import wraps

from flask import (Flask, g, jsonify, redirect, request,
                   send_from_directory, session)
from werkzeug.security import check_password_hash, generate_password_hash

DB_PATH = "quicknotes.db"   # new file, so your old notes.db is left untouched
MAX_NOTE_LENGTH = 2000

app = Flask(__name__, static_folder="static", static_url_path="/static")
# The secret key signs the login cookie. Set a real one before going online:
#   set SECRET_KEY=some-long-random-text      (Windows)
app.secret_key = os.environ.get("SECRET_KEY", "dev-only-change-me")
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"


# ---------- Database helpers ----------

def get_db():
    """Open one database connection per request and reuse it."""
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_error):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    """Create the tables the first time the app runs."""
    with sqlite3.connect(DB_PATH) as db:
        db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            )""")
        db.execute("""
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id),
                text TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT
            )""")


def now():
    return datetime.now(timezone.utc).isoformat()


def login_required(view):
    
    @wraps(view)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return jsonify(error="Please log in first."), 401
        return view(*args, **kwargs)
    return wrapper


# ---------- Pages ----------

@app.get("/")
def home():
    if "user_id" not in session:
        return redirect("/login")
    return send_from_directory("static", "index.html")


@app.get("/login")
def login_page():
    if "user_id" in session:
        return redirect("/")
    return send_from_directory("static", "login.html")


@app.get("/signup")
def signup_page():
    if "user_id" in session:
        return redirect("/")
    return send_from_directory("static", "signup.html")


# ---------- Accounts ----------

@app.post("/api/signup")
def signup():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""

    if not re.fullmatch(r"[A-Za-z0-9_]{3,30}", username):
        return jsonify(error="Username must be 3-30 letters, numbers or underscores."), 400
    if len(password) < 6:
        return jsonify(error="Password must be at least 6 characters."), 400

    db = get_db()
    try:
        cur = db.execute(
            "INSERT INTO users (username, password_hash, created_at) VALUES (?, ?, ?)",
            (username, generate_password_hash(password), now()),
        )
        db.commit()
    except sqlite3.IntegrityError:
        return jsonify(error="That username is already taken."), 409

    session.clear()
    session["user_id"] = cur.lastrowid      # log them in straight away
    session["username"] = username
    return jsonify(username=username), 201


@app.post("/api/login")
def login():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""

    user = get_db().execute(
        "SELECT id, username, password_hash FROM users WHERE username = ?",
        (username,),
    ).fetchone()

    # Same message for "no such user" and "wrong password" on purpose
    if user is None or not check_password_hash(user["password_hash"], password):
        return jsonify(error="Wrong username or password."), 401

    session.clear()
    session["user_id"] = user["id"]
    session["username"] = user["username"]
    return jsonify(username=user["username"])


@app.post("/api/logout")
def logout():
    session.clear()
    return "", 204


@app.get("/api/me")
@login_required
def me():
    return jsonify(username=session["username"])


# ---------- Notes (always limited to the logged-in user) ----------

def clean_text():
    
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    if not text:
        return None, "Write something before saving."
    if len(text) > MAX_NOTE_LENGTH:
        return None, f"Notes can be up to {MAX_NOTE_LENGTH} characters."
    return text, None


@app.get("/api/notes")
@login_required
def list_notes():
    rows = get_db().execute(
        "SELECT id, text, created_at, updated_at FROM notes "
        "WHERE user_id = ? ORDER BY id DESC",
        (session["user_id"],),
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.post("/api/notes")
@login_required
def create_note():
    text, error = clean_text()
    if error:
        return jsonify(error=error), 400

    db = get_db()
    created = now()
    cur = db.execute(
        "INSERT INTO notes (user_id, text, created_at) VALUES (?, ?, ?)",
        (session["user_id"], text, created),
    )
    db.commit()
    return jsonify(id=cur.lastrowid, text=text,
                   created_at=created, updated_at=None), 201


@app.put("/api/notes/<int:note_id>")
@login_required
def edit_note(note_id):
    text, error = clean_text()
    if error:
        return jsonify(error=error), 400

    db = get_db()
    updated = now()
    # "AND user_id = ?" stops anyone from editing somebody else's note
    cur = db.execute(
        "UPDATE notes SET text = ?, updated_at = ? WHERE id = ? AND user_id = ?",
        (text, updated, note_id, session["user_id"]),
    )
    db.commit()
    if cur.rowcount == 0:
        return jsonify(error="Note not found."), 404

    row = db.execute(
        "SELECT id, text, created_at, updated_at FROM notes WHERE id = ?",
        (note_id,),
    ).fetchone()
    return jsonify(dict(row))


@app.delete("/api/notes/<int:note_id>")
@login_required
def delete_note(note_id):
    db = get_db()
    cur = db.execute(
        "DELETE FROM notes WHERE id = ? AND user_id = ?",
        (note_id, session["user_id"]),
    )
    db.commit()
    if cur.rowcount == 0:
        return jsonify(error="Note not found."), 404
    return "", 204


init_db()

if __name__ == "__main__":
    app.run(debug=True)
