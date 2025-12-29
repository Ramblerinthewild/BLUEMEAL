from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime

db = SQLAlchemy()

class User(UserMixin, db.Model):
    __tablename__ = "user"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(150), unique=True, nullable=False)
    pw_hash = db.Column(db.String(150), nullable=False)
    role = db.Column(db.String(50), nullable=False)
    school = db.Column(db.String(200))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class MenuItemTemplate(db.Model):
    __tablename__ = "menu_item_template"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), unique=True, nullable=False)

    calories = db.Column(db.Float, nullable=False)
    protein = db.Column(db.Float, nullable=False)
    carbs = db.Column(db.Float, nullable=False)
    fats = db.Column(db.Float, nullable=False)
    sugar = db.Column(db.Float, nullable=False)
    fibre = db.Column(db.Float, nullable=False)
    sodium = db.Column(db.Float, nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class MenuItem(db.Model):
    __tablename__ = "menu_item"

    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False)
    meal_type = db.Column(db.String(50), nullable=False)

    template_id = db.Column(
        db.Integer,
        db.ForeignKey("menu_item_template.id"),
        nullable=False
    )

    template = db.relationship("MenuItemTemplate")

class StudentSelection(db.Model):
    __tablename__ = "student_selection"

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    date = db.Column(db.Date, nullable=False)
    meal_type = db.Column(db.String(50), nullable=False)

    template_id = db.Column(
        db.Integer,
        db.ForeignKey("menu_item_template.id")
    )

    student = db.relationship("User")
    template = db.relationship("MenuItemTemplate")

class WellbeingFeedback(db.Model):
    __tablename__ = "wellbeing_feedback"
    
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    week_start = db.Column(db.Date, nullable=False)  # Monday of the week
    
    # Energy & Alertness (1-5 scale)
    morning_alertness = db.Column(db.Integer)  # How alert in morning classes
    afternoon_energy = db.Column(db.Integer)   # Energy after lunch
    overall_energy = db.Column(db.Integer)     # General energy through day
    
    # Focus & Performance
    concentration = db.Column(db.Integer)      # Ability to focus
    mental_clarity = db.Column(db.Integer)     # Clear thinking
    
    # Physical Wellbeing
    digestion = db.Column(db.Integer)          # Digestive comfort
    sleep_quality = db.Column(db.Integer)      # How well they slept
    
    # Open feedback
    comments = db.Column(db.Text)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    student = db.relationship("User")

class WasteRecord(db.Model):
    __tablename__ = "waste_record"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    date = db.Column(db.Date, nullable=False)
    time = db.Column(db.Time, nullable=False)

    record_type = db.Column(db.String(20), nullable=False)
    # "meal", "day", "week"

    kg = db.Column(db.Float, nullable=False)

    user = db.relationship("User")
