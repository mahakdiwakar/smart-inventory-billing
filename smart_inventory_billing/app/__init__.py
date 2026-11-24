import click
from flask import Flask, render_template
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect

db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()


def create_app(config_object=None):
    app = Flask(__name__)
    from .config import Config
    app.config.from_object(config_object or Config)

    db.init_app(app)
    csrf.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message_category = "warning"

    from . import models  # noqa
    from .utils.perms import can, NAV

    @login_manager.user_loader
    def load_user(uid):
        return db.session.get(models.User, int(uid))

    from .routes import register_blueprints
    register_blueprints(app)

    @app.context_processor
    def inject():
        from .utils.settings import get_settings
        from flask_login import current_user
        s = get_settings() if current_user.is_authenticated else {}
        from datetime import datetime
        from flask import request, url_for
        page_url = lambda n: url_for(request.endpoint, **{**(request.view_args or {}), **request.args.to_dict(), "page": n})
        return {"can": can, "NAV": NAV, "store": s, "now": datetime.now, "page_url": page_url}

    @app.template_filter("inr")
    def inr(v):
        return f"₹{float(v or 0):,.2f}"

    for code, msg in ((403, "You don't have permission to open this page."),
                      (404, "That page doesn't exist."),
                      (500, "Something went wrong on our side.")):
        app.register_error_handler(code, lambda e, c=code, m=msg: (render_template("error.html", code=c, message=m), c))

    register_cli(app)
    return app


def register_cli(app):
    @app.cli.command("init-db")
    def init_db():
        """Create only the MISSING tables. Existing tables and data are never touched."""
        db.create_all()
        click.echo("Missing tables created (existing tables untouched).")

    @app.cli.command("seed-admin")
    def seed_admin():
        import os
        from .models import User
        email = os.getenv("ADMIN_EMAIL", "admin@smartstore.local")
        pw = os.getenv("ADMIN_PASSWORD", "ChangeMe@123")
        if User.query.filter_by(email=email).first():
            click.echo("Admin already exists - nothing changed.")
            return
        u = User(full_name="System Admin", email=email, role="Admin")
        u.set_password(pw)
        db.session.add(u)
        db.session.commit()
        click.echo(f"Admin created: {email}")

    @app.cli.command("sync-ledger")
    def sync_ledger():
        """Create Opening ledger entries so ledger == Products.stock_quantity for existing data."""
        from .services.stock import sync_opening_ledger
        n = sync_opening_ledger()
        click.echo(f"{n} product(s) reconciled.")
