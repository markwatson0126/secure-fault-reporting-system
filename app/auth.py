import sqlite3

from flask import flash, render_template, request, redirect, url_for
from flask_login import UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import check_password_hash, generate_password_hash

from . import login_manager
from .db import get_db
from .validation import (
    NAME_MAX_LENGTH,
    PASSWORD_MIN_LENGTH,
    USERNAME_MAX_LENGTH,
    USERNAME_MIN_LENGTH,
    clean_text,
    is_blank,
    is_valid_username,
)


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

    @app.route("/register", methods=["GET", "POST"])
    def register():
        values = {
            "username": "",
            "first_name": "",
            "last_name": "",
        }
        errors = {}

        if request.method == "POST":
            values = {
                "username": clean_text(request.form.get("username")),
                "first_name": clean_text(request.form.get("first_name")),
                "last_name": clean_text(request.form.get("last_name")),
            }
            password = request.form.get("password", "")
            confirm_password = request.form.get("confirm_password", "")

            if is_blank(values["username"]):
                errors["username"] = "Enter a username"
            elif len(values["username"]) < USERNAME_MIN_LENGTH:
                errors["username"] = "Username must be at least 3 characters"
            elif len(values["username"]) > USERNAME_MAX_LENGTH:
                errors["username"] = "Username must be 30 characters or fewer"
            elif not is_valid_username(values["username"]):
                errors["username"] = (
                    "Username can only contain letters, numbers, full stops, "
                    "underscores and hyphens"
                )

            if is_blank(values["first_name"]):
                errors["first_name"] = "Enter your first name"
            elif len(values["first_name"]) > NAME_MAX_LENGTH:
                errors["first_name"] = "First name must be 50 characters or fewer"

            if is_blank(values["last_name"]):
                errors["last_name"] = "Enter your last name"
            elif len(values["last_name"]) > NAME_MAX_LENGTH:
                errors["last_name"] = "Last name must be 50 characters or fewer"

            if password == "" or password.isspace():
                errors["password"] = "Enter a password"
            elif len(password) < PASSWORD_MIN_LENGTH:
                errors["password"] = "Password must be at least 12 characters"

            if confirm_password == "":
                errors["confirm_password"] = "Confirm your password"
            elif password != confirm_password:
                errors["confirm_password"] = "Passwords do not match"

            db = get_db()

            if "username" not in errors:
                existing_user = db.execute(
                    "SELECT id FROM users WHERE username = ?",
                    (values["username"],),
                ).fetchone()
                if existing_user is not None:
                    errors["username"] = "An account with that username already exists"

            if not errors:
                try:
                    db.execute(
                        """
                        INSERT INTO users
                        (username, password_hash, first_name, last_name, role)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        (
                            values["username"],
                            generate_password_hash(password),
                            values["first_name"],
                            values["last_name"],
                            "user",
                        ),
                    )
                    db.commit()
                except sqlite3.IntegrityError:
                    db.rollback()
                    errors["username"] = (
                        "An account with that username already exists"
                    )
                else:
                    flash("Account created. You can now sign in.", "success")
                    return redirect(url_for("login"))

        return render_template("register.html", errors=errors, values=values)

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
