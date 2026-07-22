import os
from datetime import datetime

from flask import Flask, render_template
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect

login_manager = LoginManager()
csrf = CSRFProtect()


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)

    app.config.from_mapping(
        SECRET_KEY=os.environ.get("SECRET_KEY"),
        DATABASE=os.path.join(app.instance_path, "app.db"),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("SESSION_COOKIE_SECURE", "").lower()
        in {"1", "true", "yes"},
        RATELIMIT_STORAGE_URI=os.environ.get("RATELIMIT_STORAGE_URI", "memory://"),
        RATELIMIT_KEY_PREFIX=os.environ.get("RATELIMIT_KEY_PREFIX", "secure-fault-reporting"),
        RATELIMIT_ENABLED=os.environ.get("RATELIMIT_ENABLED", "true").lower()
        not in {"0", "false", "no"},
        LOGIN_RATE_LIMIT=os.environ.get("LOGIN_RATE_LIMIT", "5 per minute"),
    )

    if test_config is not None:
        app.config.update(test_config)

    if not app.config.get("TESTING") and not app.config.get("SECRET_KEY"):
        raise RuntimeError("SECRET_KEY must be configured")

    os.makedirs(app.instance_path, exist_ok=True)

    login_manager.init_app(app)
    login_manager.login_view = "login"
    csrf.init_app(app)
    app_limiter = Limiter(key_func=get_remote_address)
    app_limiter.init_app(app)
    # Flask-Limiter's route wrapper holds a weak reference; retain one per app.
    app.extensions["app_limiter"] = app_limiter

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
    auth.init_app(app, app_limiter)

    from . import routes
    routes.init_app(app)

    @app.errorhandler(429)
    def rate_limit_exceeded(error):
        response = error.get_response()
        response.set_data(render_template("429.html"))
        response.content_type = "text/html; charset=utf-8"
        return response

    return app
