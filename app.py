# app.py
import os
from datetime import datetime, time
import csv
import json
from pathlib import Path

import pandas as pd
from flask import (Flask, flash, jsonify, redirect, render_template, request,
                   send_file, url_for)
from flask_login import (LoginManager, UserMixin, current_user, login_required,
                         login_user, logout_user)
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
MENU_CSV = BASE_DIR / "menu_examples" / "la_impact_menu.csv"
NUTRITION_JSON = BASE_DIR / "nutrition" / "nutrition_lookup.json"
SELECTIONS_CSV = DATA_DIR / "selections.csv"

DATA_DIR.mkdir(exist_ok=True, parents=True)

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("FLASK_SECRET", "dev-secret-key")
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{DATA_DIR / 'users.db'}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"

# -----------------------
# Database models
# -----------------------
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(200), unique=True, nullable=False)
    pw_hash = db.Column(db.String(200), nullable=False)
    school = db.Column(db.String(200), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def check_password(self, pw):
        return check_password_hash(self.pw_hash, pw)

with app.app_context():
    db.create_all()

# -----------------------
# Auth
# -----------------------
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))



def is_school_email(email):
    # Simple check: school domain ends with .edu or contains 'school'
    return email.endswith(".org") or "students" in email or email.endswith(".com") or email.endswith("@school.edu")

# -----------------------
# Utilities: CSV + Nutrition
# -----------------------
def load_menu_df():
    # Use pandas for flexible parsing
    return pd.read_csv(MENU_CSV, parse_dates=["date"])

def parse_meal_cell(cell):
    # cell like "Rice+Chicken;Salad" or "Rice;Chicken"
    if pd.isna(cell):
        return []
    # allow comma or semicolon separators or + sign
    s = str(cell)
    items = []
    for sep in (";", "+", ","):
        if sep in s:
            items = [p.strip() for p in s.split(sep) if p.strip()]
            break
    if not items:
        items = [s.strip()]
    return items

def get_day_menu(target_date: datetime.date):
    df = load_menu_df()
    row = df[df["date"].dt.date == target_date]
    if row.empty:
        return None
    row = row.iloc[0]
    return {
        "breakfast": parse_meal_cell(row.get("breakfast", "")),
        "lunch": parse_meal_cell(row.get("lunch", "")),
        "snack1": parse_meal_cell(row.get("snack1", "")),
        "dinner": parse_meal_cell(row.get("dinner", "")),
        "snack2": parse_meal_cell(row.get("snack2", ""))
    }

# meal times (example school schedule) — adjust as needed
MEAL_TIMES = {
    "breakfast": (time(7,0), time(8,30)),
    "lunch": (time(12,0), time(14,0)),
    "snack1": (time(10,0), time(10,30)),
    "dinner": (time(17,30), time(19,0)),
    "snack2": (time(15,30), time(16,0))
}

def get_current_or_next_meal(now=None, day_menu=None):
    if now is None:
        now = datetime.now()
    today = now.date()
    if day_menu is None:
        day_menu = get_day_menu(today)
    # order of meals to check
    order = ["breakfast","snack1","lunch","snack2","dinner"]
    current_time = now.time()
    # check current
    for m in order:
        start, end = MEAL_TIMES[m]
        if start <= current_time <= end:
            return m, "current", day_menu.get(m, [])
    # not current: find next by start time
    future_meals = []
    for m in order:
        start, end = MEAL_TIMES[m]
        if current_time < start:
            future_meals.append((start, m))
    if future_meals:
        next_m = sorted(future_meals)[0][1]
        return next_m, "upcoming", day_menu.get(next_m, [])
    # if no more today, show breakfast for next day
    next_day_menu = get_day_menu(today + pd.Timedelta(days=1))
    return "breakfast", "tomorrow", (next_day_menu.get("breakfast", []) if next_day_menu else [])

# load nutrition database
with open(NUTRITION_JSON, "r", encoding="utf8") as f:
    NUTRI_DB = json.load(f)

REQUIRED_NUTRIENTS = {"Carbohydrates","Protein","Vitamins","Minerals","Salt","Water"}

def gather_nutrients_for_items(items):
    found = set()
    for it in items:
        # try exact match, fallback to partial match
        if it in NUTRI_DB:
            found.update(NUTRI_DB[it])
        else:
            # try matching words
            for key in NUTRI_DB:
                if key.lower() in it.lower() or it.lower() in key.lower():
                    found.update(NUTRI_DB[key])
    return found

def suggest_for_balance(selected_items):
    present = gather_nutrients_for_items(selected_items)
    missing = REQUIRED_NUTRIENTS - present
    suggestions = []
    if not missing:
        return [], present
    # naive suggestion: find items in NUTRI_DB that supply missing nutrients
    for need in missing:
        # search for a food that contains this nutrient
        found = [food for food, nutrients in NUTRI_DB.items() if need in nutrients]
        suggestion = found[:3] if found else []
        suggestions.append({"need": need, "options": suggestion})
    return suggestions, present

# -----------------------
# Save selection
# -----------------------
def init_selections_csv():
    if not SELECTIONS_CSV.exists():
        with open(SELECTIONS_CSV, "w", newline="", encoding="utf8") as f:
            writer = csv.writer(f)
            writer.writerow(["timestamp","user_email","date","meal","selected_items","portion"])

init_selections_csv()

def save_selection(user_email, date_str, meal, items, portion):
    timestamp = datetime.utcnow().isoformat()
    with open(SELECTIONS_CSV, "a", newline="", encoding="utf8") as f:
        writer = csv.writer(f)
        writer.writerow([timestamp, user_email, date_str, meal, "|".join(items), portion])

# -----------------------
# Routes
# -----------------------
@app.route("/")
def index():
    if current_user.is_authenticated:
        return redirect(url_for("menu"))
    return render_template("base.html")

@app.route("/signup", methods=["GET","POST"])
def signup():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        pw = request.form["password"]
        if not is_school_email(email):
            flash("Please use a valid school email address.", "danger")
            return redirect(url_for("signup"))
        if User.query.filter_by(email=email).first():
            flash("Email already registered. Please log in.", "warning")
            return redirect(url_for("login"))
        user = User(email=email, pw_hash=generate_password_hash(pw))
        db.session.add(user)
        db.session.commit()
        login_user(user)
        flash("Signed up successfully!", "success")
        return redirect(url_for("menu"))
    return render_template("signup.html")

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        pw = request.form["password"]
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(pw):
            login_user(user)
            flash("Logged in!", "success")
            return redirect(url_for("menu"))
        flash("Invalid login", "danger")
        return redirect(url_for("login"))
    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Logged out", "info")
    return redirect(url_for("index"))

@app.route("/menu")
@login_required
def menu():
    # read menus
    today = datetime.now().date()
    day_menu = get_day_menu(today) or {}
    meal, status, items = get_current_or_next_meal(datetime.now(), day_menu)
    # For display: provide a nice time range
    start, end = MEAL_TIMES.get(meal, (time(0,0),time(23,59)))
    time_range = f"{start.strftime('%H:%M')} - {end.strftime('%H:%M')}"
    return render_template("menu.html",
                           meal=meal.title(),
                           status=status,
                           items=items,
                           time_range=time_range,
                           date=today.isoformat())

@app.route("/suggest", methods=["POST"])
@login_required
def suggest():
    payload = request.json
    items = payload.get("items", [])
    portion = payload.get("portion", "regular")
    suggestions, present = suggest_for_balance(items)
    # save user selection
    save_selection(current_user.email, payload.get("date", datetime.now().date().isoformat()), payload.get("meal","unknown"), items, portion)
    return jsonify({"suggestions": suggestions, "present": list(present)})

@app.route("/admin")
@login_required
def admin():
    # for demo only: allow any logged in user to view admin (in real life, add role check)
    # read selections CSV into pandas
    df = pd.read_csv(SELECTIONS_CSV, parse_dates=["timestamp"])
    # quick stats:
    top_items = {}
    for row in df["selected_items"].dropna():
        for it in str(row).split("|"):
            top_items[it] = top_items.get(it,0) + 1
    top_list = sorted(top_items.items(), key=lambda x: -x[1])[:10]
    # export file path
    return render_template("admin.html", top_list=top_list, total=len(df))

@app.route("/export-selections")
@login_required
def export_selections():
    return send_file(SELECTIONS_CSV, as_attachment=True)

# -----------------------
# run
# -----------------------
if __name__ == "__main__":
    app.run(debug=True)
