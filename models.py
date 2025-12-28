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
