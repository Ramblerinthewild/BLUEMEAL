# app.py
import os
from datetime import datetime, time
import csv
import json
from pathlib import Path
from flask import request, jsonify
from models import db, User, MenuItemTemplate, MenuItem, StudentSelection

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

db.init_app(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# -----------------------
# Database models
# -----------------------

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

def redirect_by_role(user):
    if user.role == "organisation":
        return redirect(url_for("org_members"))
    elif user.role == "member":
        return redirect(url_for("member_dashboard"))   # student flow (existing)
    elif user.role == "individual":
        return redirect(url_for("individual_dashboard"))
    else:
        return redirect(url_for("index"))

# -----------------------
# Menu database model
# -----------------------
class Menu(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    meal_type = db.Column(db.String(20), nullable=False)  # breakfast/lunch/dinner
    items = db.Column(db.Text, nullable=True)  # store as JSON string
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

with app.app_context():
    db.create_all()


# -----------------------
# Routes
# -----------------------
@app.route("/")
def index():
    if current_user.is_authenticated:
        return redirect_by_role(current_user)
    return render_template("base.html")


@app.route("/signup", methods=["GET","POST"])
def signup():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        pw = request.form["password"]
        role = request.form["role"]  # NEW

        if role not in ["organisation", "member", "individual"]:
            flash("Invalid account type.", "danger")
            return redirect(url_for("signup"))

        if User.query.filter_by(email=email).first():
            flash("Email already registered.", "warning")
            return redirect(url_for("login"))

        user = User(
            email=email,
            pw_hash=generate_password_hash(pw),
            role=role
        )

        db.session.add(user)
        db.session.commit()
        login_user(user)

        # redirect based on role
        if role == "organisation":
            return redirect(url_for("org_members"))
        elif role == "member":
            return redirect(url_for("member_dashboard"))
        else:
            return redirect(url_for("individual_dashboard"))

    return render_template("signup.html")

# Add menu item template (the master list)
@app.route("/organisation/add-menu-template", methods=["POST"])
@login_required
def add_menu_template():
    if current_user.role != "organisation":
        return jsonify({"error": "Unauthorized"}), 403
    
    data = request.json
    
    # Validate required fields
    required = ["name", "calories", "protein", "carbs", "fats", "sugar", "fibre", "sodium"]
    for field in required:
        if field not in data or data[field] is None:
            return jsonify({"error": f"{field} is required"}), 400
    
    # Check if exists
    existing = MenuItemTemplate.query.filter_by(name=data["name"]).first()
    if existing:
        return jsonify({"error": "Item already exists"}), 400
    
    item = MenuItemTemplate(
        name=data["name"],
        calories=float(data["calories"]),
        protein=float(data["protein"]),
        carbs=float(data["carbs"]),
        fats=float(data["fats"]),
        sugar=float(data["sugar"]),
        fibre=float(data["fibre"]),
        sodium=float(data["sodium"])
    )
    
    db.session.add(item)
    db.session.commit()
    
    return jsonify({"success": True, "id": item.id})

# Get all menu templates for autocomplete
@app.route("/organisation/get-menu-templates")
@login_required
def get_menu_templates():
    if current_user.role != "organisation":
        return jsonify({"error": "Unauthorized"}), 403
    
    items = MenuItemTemplate.query.all()
    return jsonify([{
        "id": i.id,
        "name": i.name,
        "calories": i.calories,
        "protein": i.protein,
        "carbs": i.carbs,
        "fats": i.fats,
        "sugar": i.sugar,
        "fibre": i.fibre,
        "sodium": i.sodium
    } for i in items])

# Save daily menu (links templates to specific date)
@app.route("/organisation/save-menu", methods=["POST"])
@login_required
def save_menu():
    if current_user.role != "organisation":
        return jsonify({"error": "Unauthorized"}), 403

    data = request.json
    date = datetime.strptime(data["date"], "%Y-%m-%d").date()
    meals = data["meals"]  # { breakfast: ["Eggs", "Toast"], lunch: [...], dinner: [...] }

    # Delete old menu for that date
    MenuItem.query.filter_by(date=date).delete()

    # Add new items by looking up template IDs
    for meal_type, item_names in meals.items():
        for item_name in item_names:
            template = MenuItemTemplate.query.filter_by(name=item_name).first()
            if template:
                db.session.add(MenuItem(
                    date=date,
                    meal_type=meal_type,
                    template_id=template.id
                ))

    db.session.commit()
    return jsonify({"status": "saved"})

# Get menu for a specific date
@app.route("/organisation/get-menu/<date_str>")
@login_required
def get_menu(date_str):
    if current_user.role != "organisation":
        return jsonify({"error": "Unauthorized"}), 403

    try:
        date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"error": "Invalid date"}), 400

    items = MenuItem.query.filter_by(date=date).all()

    result = {"breakfast": [], "lunch": [], "dinner": []}
    for item in items:
        result[item.meal_type].append(item.template.name)
    
    return jsonify(result)


@app.route("/student/menu")
@login_required
def get_student_menu():
    date = request.args.get("date")
    date = datetime.strptime(date, "%Y-%m-%d").date()

    items = MenuItem.query.filter_by(date=date).all()

    meals = {"breakfast": [], "lunch": [], "dinner": []}
    for item in items:
        meals[item.meal_type].append(item.template.name)

    return jsonify(meals)

@app.route("/student/select", methods=["POST"])
@login_required
def student_select():
    if current_user.role != "member":
        return jsonify({"error": "Unauthorized"}), 403

    data = request.json
    try:
        date = datetime.strptime(data["date"], "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"error": "Invalid date"}), 400

    # Remove old selections for this student and date
    StudentSelection.query.filter_by(
        student_id=current_user.id,
        date=date
    ).delete()

    # Add new selections
    for meal, items in data["meals"].items():
        for item_name in items:
            # Look up the template by name
            template = MenuItemTemplate.query.filter_by(name=item_name).first()
            if not template:
                print(f"WARNING: Template not found for item '{item_name}'")
                continue
            
            db.session.add(StudentSelection(
                student_id=current_user.id,
                date=date,
                meal_type=meal,
                template_id=template.id
            ))

    db.session.commit()
    return jsonify({"status": "saved"})

@app.route("/organisation/analytics-data")
@login_required
def analytics_data():
    if current_user.role != "organisation":
        return jsonify({"error": "Unauthorized"}), 403
        
    date = request.args.get("date")
    date = datetime.strptime(date, "%Y-%m-%d").date()

    selections = StudentSelection.query.filter_by(date=date).all()

    result = {"breakfast": [], "lunch": [], "dinner": []}
    for s in selections:
        # Use template.name instead of item_name
        result[s.meal_type].append(s.template.name)

    return jsonify(result)


@app.route("/member")
@login_required
def member_dashboard():
    if current_user.role != "member":
        return redirect(url_for("index"))
    return render_template("member.html")


@app.route("/individual")
@login_required
def individual_dashboard():
    if current_user.role != "individual":
        return redirect(url_for("index"))
    return render_template("individual.html")


@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        pw = request.form["password"]
        user = User.query.filter_by(email=email).first()
        if user and user.check_password(pw):
            login_user(user)
            flash("Logged in!", "success")
            if user and user.check_password(pw):
                login_user(user)
                flash("Logged in!", "success")
                return redirect_by_role(user)

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

@app.route("/calender_day")
@login_required  # optional: require login
def calender_day():
    return render_template("calender_day.html")

@app.route("/Analytics")
@login_required  # optional: require login
def Analytics():
    return render_template("analytics.html")

latest_submission = ""  # TEMP storage (fine for now)

@app.route("/submit-menu", methods=["POST"])
@login_required
def submit_menu():
    global latest_submission
    data = request.json

    latest_submission = f"""
    Day: {data['day']}
    Meal: {data['meal']}
    Items: {data['items']}
    """

    return jsonify({"status": "ok"})

@app.route("/organisation/members")
@login_required
def org_members():
    if current_user.role != "organisation":
        return redirect(url_for("index"))
    return render_template("organisation/members.html")


@app.route("/organisation/analytics")
@login_required
def org_analytics():
    if current_user.role != "organisation":
        return redirect(url_for("index"))
    return render_template("organisation/analytics.html")


@app.route("/organisation/waste")
@login_required
def org_waste():
    if current_user.role != "organisation":
        return redirect(url_for("index"))
    return render_template("organisation/waste.html")


@app.route("/organisation/menu")
@login_required
def org_menu():
    if current_user.role != "organisation":
        return redirect(url_for("index"))
    return render_template("organisation/menu.html")


@app.route("/organisation/demand")
@login_required
def org_demand():
    if current_user.role != "organisation":
        return redirect(url_for("index"))
    return render_template("organisation/demand.html")

@app.route("/organisation/demand-data")
@login_required
def demand_data():
    if current_user.role != "organisation":
        return jsonify({"error": "Unauthorized"}), 403

    date_str = request.args.get("date")
    try:
        date = datetime.strptime(date_str, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid date"}), 400

    selections = StudentSelection.query.filter_by(date=date).all()

    result = {
        "breakfast": {},
        "lunch": {},
        "dinner": {}
    }

    # Group by meal and student to avoid double-counting
    from collections import defaultdict
    meal_to_students = defaultdict(lambda: defaultdict(set))  # meal -> item -> set(student_id)

    for s in selections:
        # Use template.name to get the item name
        meal_to_students[s.meal_type][s.template.name].add(s.student_id)

    # Calculate percentages
    for meal, item_dict in meal_to_students.items():
        # Total number of students who voted for this meal
        all_students = set()
        for students in item_dict.values():
            all_students.update(students)
        total_students = len(all_students)
        
        if total_students == 0:
            continue
            
        for item, students in item_dict.items():
            result[meal][item] = round((len(students) / total_students) * 100, 1)

    return jsonify(result)

@app.route("/debug-bad-selections")
@login_required
def debug_bad_selections():
    """Find all selections with missing templates"""
    if current_user.role != "organisation":
        return jsonify({"error": "Unauthorized"}), 403
    
    # Get all selections
    all_selections = StudentSelection.query.all()
    
    bad_ones = []
    for s in all_selections:
        if not s.template:
            bad_ones.append({
                "id": s.id,
                "student_id": s.student_id,
                "date": str(s.date),
                "meal_type": s.meal_type,
                "template_id": s.template_id,
                "problem": "Template doesn't exist"
            })
    
    return jsonify({
        "total_selections": len(all_selections),
        "bad_selections": len(bad_ones),
        "details": bad_ones
    })

@app.route("/clean-bad-selections")
@login_required
def clean_bad_selections():
    """Delete all selections with missing templates"""
    if current_user.role != "organisation":
        return jsonify({"error": "Unauthorized"}), 403
    
    deleted = 0
    all_selections = StudentSelection.query.all()
    
    for s in all_selections:
        if not s.template:
            db.session.delete(s)
            deleted += 1
    
    db.session.commit()
    
    return jsonify({
        "message": f"Deleted {deleted} bad selection records"
    })
# Add menu template



# -----------------------
# run
# -----------------------
if __name__ == "__main__":
    app.run(debug=True)
