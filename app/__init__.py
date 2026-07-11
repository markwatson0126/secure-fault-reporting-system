import os
import secrets
from datetime import datetime

from flask import Flask
from flask_login import LoginManager

login_manager = LoginManager()


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)

    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY") or secrets.token_hex(32),
        DATABASE=os.path.join(app.instance_path, "app.db"),
    )

    if test_config is not None:
        app.config.update(test_config)

    os.makedirs(app.instance_path, exist_ok=True)

    login_manager.init_app(app)
    login_manager.login_view = "login"

    @app.template_filter("datetimeformat")
    def format_datetime(value):
        try:
            return datetime.strptime(value, "%Y-%m-%d %H:%M:%S").strftime("%d/%m/%Y")
        except Exception:
            try:
                return datetime.strptime(value, "%Y-%m-%d").strftime("%d/%m/%Y")
            except Exception:
                return value

    from . import db
    db.init_app(app)

    from . import auth
    auth.init_app(app)

    from . import routes
    routes.init_app(app)

    return app
