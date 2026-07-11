import os
import sqlite3

from flask import current_app, g
from werkzeug.security import generate_password_hash


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")

    return g.db


def close_db(exception=None):
    db = g.pop("db", None)

    if db is not None:
        db.close()


def init_db():
    db = get_db()

    project_root = os.path.abspath(os.path.join(current_app.root_path, ".."))
    schema_path = os.path.join(project_root, "schema.sql")

    with open(schema_path, "r", encoding="utf-8") as f:
        db.executescript(f.read())

    initial_admin_password = os.environ.get("INITIAL_ADMIN_PASSWORD")

    if initial_admin_password:
        db.execute(
            """
            INSERT INTO users
            (username, password_hash, first_name, last_name, role)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                os.environ.get("INITIAL_ADMIN_USERNAME", "admin"),
                generate_password_hash(initial_admin_password),
                "System",
                "Administrator",
                "admin",
            ),
        )

    db.commit()


def init_db_once():
    if current_app.config.get("DB_INITIALISED"):
        return

    db_path = current_app.config["DATABASE"]

    if not os.path.exists(db_path):
        init_db()

    current_app.config["DB_INITIALISED"] = True


def init_app(app):
    app.before_request(init_db_once)
    app.teardown_appcontext(close_db)
