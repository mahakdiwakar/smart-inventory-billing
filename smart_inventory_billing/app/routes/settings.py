from flask import Blueprint, render_template, request, flash, redirect, url_for
from .. import db
from ..utils.perms import permission_required
from ..utils.settings import get_settings, save_settings, DEFAULTS
from ..utils.audit import audit

bp = Blueprint("settings", __name__, url_prefix="/settings")


@bp.route("/", methods=["GET", "POST"])
@permission_required("settings")
def index():
    if request.method == "POST":
        data = {k: request.form.get(k, "").strip() for k in DEFAULTS}
        if data["store_gstin"] and len(data["store_gstin"]) != 15:
            flash("GSTIN must be 15 characters.", "danger")
        else:
            save_settings(data); audit("SETTINGS", "Store_Settings"); db.session.commit()
            flash("Settings saved.", "success")
            return redirect(url_for("settings.index"))
    return render_template("settings/index.html", s=get_settings(), keys=list(DEFAULTS))
