import sqlite3
from functools import wraps
from urllib.parse import urlsplit

from flask import abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import UserMixin, current_user, login_required, login_user, logout_user
from werkzeug.security import check_password_hash, generate_password_hash

from . import login_manager
from .db import active_buildings, find_active_building, get_db
from .validation import (
    clean_text, email_domain, validate_domain, validate_email_address,
    validate_name, validate_password,
)

USER_SEARCH_MAX_LENGTH = 100


class User(UserMixin):
    def __init__(self, id, email, role, building_id, first_name, last_name, building_name):
        self.id = id
        self.email = email
        self.role = role
        self.building_id = building_id
        self.first_name = first_name
        self.last_name = last_name
        self.building_name = building_name

    def get_id(self):
        return str(self.id)


def _user_from_row(row):
    return User(
        row["id"], row["email"], row["role"], row["building_id"],
        row["first_name"], row["last_name"], row["building_name"],
    )


@login_manager.user_loader
def load_user(user_id):
    row = get_db().execute(
        """
        SELECT users.*, buildings.name AS building_name FROM users
        JOIN buildings ON buildings.id = users.building_id WHERE users.id = ?
        """,
        (user_id,),
    ).fetchone()
    return _user_from_row(row) if row else None


def admin_required(view):
    @wraps(view)
    @login_required
    def wrapped(*args, **kwargs):
        if current_user.role != "admin":
            abort(403)
        return view(*args, **kwargs)
    return wrapped


def _safe_next_url(value):
    if not value:
        return None
    target = urlsplit(value)
    return value if (
        not target.scheme and not target.netloc and value.startswith("/")
        and not value.startswith("//") and "\\" not in value
    ) else None


def _escape_like(value):
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _account_values(form=None, building_id=None):
    supplied_form = form is not None
    form = form or {}
    return {
        "email": clean_text(form.get("email")),
        "first_name": clean_text(form.get("first_name")),
        "last_name": clean_text(form.get("last_name")),
        "building_id": clean_text(form.get("building_id")) if building_id is None else str(building_id),
        "role": clean_text(form.get("role")) if supplied_form else "user",
    }


def _validate_account(values, password, db, require_role=False, fixed_building_id=None):
    errors = {}
    email, errors_email = validate_email_address(values["email"])
    if errors_email:
        errors["email"] = errors_email
    else:
        values["email"] = email
    values["first_name"], first_error = validate_name(values["first_name"], "First name")
    values["last_name"], last_error = validate_name(values["last_name"], "Last name")
    if first_error:
        errors["first_name"] = first_error
    if last_error:
        errors["last_name"] = last_error
    password_error = validate_password(password)
    if password_error:
        errors["password"] = password_error

    building = find_active_building(values["building_id"], db)
    if not values["building_id"]:
        errors["building_id"] = "Select a building or work location"
    elif building is None:
        errors["building_id"] = "Select a valid building or work location"
    elif fixed_building_id is not None and building["id"] != fixed_building_id:
        errors["building_id"] = "Select a valid building or work location"

    if require_role and values["role"] not in {"user", "admin"}:
        errors["role"] = "Select a valid role"
    if email and db.execute(
        "SELECT id FROM users WHERE email = ? COLLATE NOCASE", (email,)
    ).fetchone():
        errors["email"] = "An account already exists for this email address"
    return building, errors


def _domain_is_allowed(db, building_id, email):
    return db.execute(
        """
        SELECT 1 FROM allowed_email_domains
        WHERE building_id = ? AND domain = ? COLLATE NOCASE AND active = 1
        """,
        (building_id, email_domain(email)),
    ).fetchone() is not None


def _insert_user(db, values, password, building_id, role):
    db.execute(
        """
        INSERT INTO users (email, password_hash, first_name, last_name, building_id, role)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (values["email"], generate_password_hash(password), values["first_name"],
         values["last_name"], building_id, role),
    )


def init_app(app, app_limiter):
    @app.route("/login", methods=["GET", "POST"])
    @app_limiter.limit(lambda: current_app.config["LOGIN_RATE_LIMIT"], exempt_when=lambda: request.method != "POST")
    def login():
        error = None
        email = ""
        if request.method == "POST":
            email = clean_text(request.form.get("email"))
            password = request.form.get("password", "")
            normalised_email, validation_error = validate_email_address(email)
            row = None
            if validation_error is None:
                row = get_db().execute(
                    """
                    SELECT users.*, buildings.name AS building_name FROM users
                    JOIN buildings ON buildings.id = users.building_id
                    WHERE users.email = ? COLLATE NOCASE
                    """,
                    (normalised_email,),
                ).fetchone()
            if row and check_password_hash(row["password_hash"], password):
                login_user(_user_from_row(row))
                return redirect(_safe_next_url(request.args.get("next")) or url_for("index"))
            error = "Enter the correct email address and password"
        return render_template("login.html", error=error, email=email)

    @app.route("/register", methods=["GET", "POST"])
    def register():
        db = get_db()
        values = _account_values()
        errors = {}
        if request.method == "POST":
            values = _account_values(request.form)
            password = request.form.get("password", "")
            building, errors = _validate_account(values, password, db)
            if not errors and not _domain_is_allowed(db, building["id"], values["email"]):
                return render_template("registration_ineligible.html", values=values), 422
            if not errors:
                try:
                    _insert_user(db, values, password, building["id"], "user")
                    db.commit()
                except sqlite3.IntegrityError:
                    db.rollback()
                    errors["email"] = "An account already exists for this email address"
                else:
                    flash("Account created. You can now sign in.", "success")
                    return redirect(url_for("login"))
        return render_template("register.html", errors=errors, values=values, buildings=active_buildings(db))

    @app.route("/logout")
    @login_required
    def logout():
        logout_user()
        return redirect(url_for("login"))

    @app.route("/admin/users")
    @admin_required
    def admin_users():
        filters = {
            "first_name": clean_text(request.args.get("first_name")),
            "last_name": clean_text(request.args.get("last_name")),
            "email": clean_text(request.args.get("email")),
            "role": clean_text(request.args.get("role")),
        }
        for field in ("first_name", "last_name", "email"):
            if len(filters[field]) > USER_SEARCH_MAX_LENGTH:
                abort(400)
        if filters["role"] not in {"", "user", "admin"}:
            abort(400)

        conditions = []
        parameters = []
        text_columns = {
            "first_name": "users.first_name",
            "last_name": "users.last_name",
            "email": "users.email",
        }
        for field, column in text_columns.items():
            if filters[field]:
                conditions.append(
                    f"{column} COLLATE NOCASE LIKE ? ESCAPE '\\'"
                )
                parameters.append(f"%{_escape_like(filters[field])}%")
        if filters["role"]:
            conditions.append("users.role = ?")
            parameters.append(filters["role"])

        where_clause = (
            f'WHERE {" AND ".join(conditions)}' if conditions else ""
        )
        query = f"""
            SELECT users.first_name, users.last_name, users.email, users.role,
                   buildings.name AS building_name
            FROM users JOIN buildings ON buildings.id = users.building_id
            {where_clause}
            ORDER BY users.last_name COLLATE NOCASE,
                     users.first_name COLLATE NOCASE,
                     users.id
        """
        users = get_db().execute(query, parameters).fetchall()
        return render_template("admin/users.html", users=users, filters=filters)

    @app.route("/add_user", methods=["GET", "POST"])
    @admin_required
    def add_user():
        db = get_db()
        values = _account_values(building_id=current_user.building_id)
        errors = {}
        if request.method == "POST":
            values = _account_values(request.form)
            password = request.form.get("password", "")
            building, errors = _validate_account(
                values, password, db, require_role=True,
                fixed_building_id=current_user.building_id,
            )
            if not errors and not _domain_is_allowed(db, current_user.building_id, values["email"]):
                errors["email"] = "Email domain is not accepted for this building"
            if not errors:
                try:
                    _insert_user(db, values, password, current_user.building_id, values["role"])
                    db.commit()
                except sqlite3.IntegrityError:
                    db.rollback()
                    errors["email"] = "An account already exists for this email address"
                else:
                    flash("Account created.", "success")
                    return redirect(url_for("admin_users"))
        return render_template(
            "admin/add_user.html", errors=errors, values=values,
            buildings=[{"id": current_user.building_id, "name": current_user.building_name}],
        )

    @app.route("/admin/domains")
    @admin_required
    def admin_domains():
        domains = get_db().execute(
            """
            SELECT * FROM allowed_email_domains WHERE building_id = ?
            ORDER BY domain COLLATE NOCASE
            """,
            (current_user.building_id,),
        ).fetchall()
        return render_template("admin/domains.html", domains=domains)

    @app.route("/admin/domains/add", methods=["GET", "POST"])
    @admin_required
    def add_domain():
        db = get_db()
        value = ""
        error = None
        if request.method == "POST":
            value = clean_text(request.form.get("domain"))
            domain, error = validate_domain(value)
            if not error and db.execute(
                "SELECT id FROM allowed_email_domains WHERE building_id = ? AND domain = ? COLLATE NOCASE",
                (current_user.building_id, domain),
            ).fetchone():
                error = "This email domain already exists for this building"
            if not error:
                try:
                    db.execute(
                        """
                        INSERT INTO allowed_email_domains
                            (building_id, domain, active, created_by_user_id)
                        VALUES (?, ?, 1, ?)
                        """,
                        (current_user.building_id, domain, current_user.id),
                    )
                    db.commit()
                except sqlite3.IntegrityError:
                    db.rollback()
                    error = "This email domain already exists for this building"
                else:
                    flash("Email domain added.", "success")
                    return redirect(url_for("admin_domains"))
        return render_template("admin/add_domain.html", error=error, value=value)

    def scoped_domain(domain_id):
        row = get_db().execute(
            "SELECT * FROM allowed_email_domains WHERE id = ?", (domain_id,)
        ).fetchone()
        if row is None:
            abort(404)
        if row["building_id"] != current_user.building_id:
            abort(403)
        return row

    @app.post("/admin/domains/<int:domain_id>/deactivate")
    @admin_required
    def deactivate_domain(domain_id):
        row = scoped_domain(domain_id)
        if row["active"]:
            db = get_db()
            db.execute(
                """
                UPDATE allowed_email_domains SET active = 0,
                    deactivated_by_user_id = ?, deactivated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND building_id = ?
                """,
                (current_user.id, domain_id, current_user.building_id),
            )
            db.commit()
        return redirect(url_for("admin_domains"))

    @app.post("/admin/domains/<int:domain_id>/activate")
    @admin_required
    def activate_domain(domain_id):
        row = scoped_domain(domain_id)
        if not row["active"]:
            db = get_db()
            db.execute(
                """
                UPDATE allowed_email_domains SET active = 1,
                    deactivated_by_user_id = NULL, deactivated_at = NULL
                WHERE id = ? AND building_id = ?
                """,
                (domain_id, current_user.building_id),
            )
            db.commit()
        return redirect(url_for("admin_domains"))
