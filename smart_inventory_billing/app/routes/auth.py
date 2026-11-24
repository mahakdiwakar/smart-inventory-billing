from datetime import datetime
from urllib.parse import urlparse
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from .. import db
from ..models import User
from ..utils.audit import audit

bp = Blueprint("auth", __name__)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))
    if request.method == "POST":
        u = User.query.filter_by(email=request.form.get("email", "").strip().lower()).first()
        if u and u.is_active and u.check_password(request.form.get("password", "")):
            login_user(u)
            u.last_login = datetime.utcnow()
            audit("LOGIN", "User", u.user_id)
            db.session.commit()
            nxt = request.args.get("next", "")
            return redirect(nxt if nxt and not urlparse(nxt).netloc else url_for("dashboard.index"))
        flash("Email or password is incorrect.", "danger")
    return render_template("auth/login.html")


@bp.route("/logout", methods=["POST", "GET"])
@login_required
def logout():
    audit("LOGOUT", "User", current_user.user_id)
    db.session.commit()
    logout_user()
    return redirect(url_for("auth.login"))


@bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    if request.method == "POST":
        cur, new, conf = (request.form.get(k, "") for k in ("current", "new", "confirm"))
        if not current_user.check_password(cur):
            flash("Current password is incorrect.", "danger")
        elif len(new) < 8 or new != conf:
            flash("New password must be at least 8 characters and match the confirmation.", "danger")
        else:
            current_user.set_password(new)
            audit("PASSWORD_CHANGE", "User", current_user.user_id)
            db.session.commit()
            flash("Password changed.", "success")
    return render_template("auth/profile.html")
