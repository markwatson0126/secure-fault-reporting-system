import sqlite3

from flask import render_template, request, redirect, url_for
from flask_login import UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash, generate_password_hash

from . import login_manager
from .db import get_db
from .validation import clean_text, is_blank


class User(UserMixin):
    def __init__(self, id, username, role):
        self.id = id
        self.username = username
        self.role = role

    def get_id(self):
        return str(self.id)


@login_manager.user_loader
def load_user(user_id):
    db = get_db()
    user = db.execute(
        "SELECT * FROM users WHERE id = ?",
        (user_id,)
    ).fetchone()

    if user:
        return User(
            id=user["id"],
            username=user["username"],
            role=user["role"]
        )

    return None


def init_app(app):
    @app.route("/login", methods=["GET", "POST"])
    def login():
        db = get_db()
        error = None

        if request.method == "POST":
            username = clean_text(request.form.get("username"))
            password = request.form["password"]

            user = db.execute(
                "SELECT * FROM users WHERE username = ?",
                (username,)
            ).fetchone()

            if user and check_password_hash(user["password_hash"], password):
                user_obj = User(
                    id=user["id"],
                    username=user["username"],
                    role=user["role"]
                )
                login_user(user_obj)
                return redirect(url_for("index"))

            error = "Invalid username or password"

        return render_template("login.html", error=error)

    @app.route("/logout")
    @login_required
    def logout():
        logout_user()
        return redirect(url_for("login"))

    @app.route("/add_user", methods=["POST"])
    @login_required
    def add_user():
        if current_user.role != "admin":
            return "Unauthorized", 403

        db = get_db()
        username = clean_text(request.form.get("username"))
        password = request.form.get("password", "")
        first_name = clean_text(request.form.get("first_name"))
        last_name = clean_text(request.form.get("last_name"))
        role = clean_text(request.form.get("role"))

        if (
            is_blank(username)
            or is_blank(password)
            or is_blank(first_name)
            or is_blank(last_name)
            or role not in {"user", "admin"}
        ):
            return "Invalid user details.", 400

        try:
            db.execute(
                """
                INSERT INTO users
                (username, password_hash, first_name, last_name, role)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    username,
                    generate_password_hash(password),
                    first_name,
                    last_name,
                    role,
                ),
            )
            db.commit()
            return redirect(url_for("index"))

        except sqlite3.IntegrityError:
            return "Username already exists.", 409
