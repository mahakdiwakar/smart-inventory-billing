from datetime import date, datetime
from flask import Blueprint, render_template, request, jsonify, url_for, abort
from flask_login import current_user
from .. import db
from ..models import Purchase, Supplier, Product
from ..utils.perms import permission_required
from ..services.purchases import create_purchase
from ..services.stock import BusinessError

bp = Blueprint("purchases", __name__, url_prefix="/purchases")


@bp.route("/")
@permission_required("purchases")
def list_view():
    q = Purchase.query
    if request.args.get("supplier"):
        q = q.filter(Purchase.supplier_id == int(request.args["supplier"]))
    p = q.order_by(Purchase.purchase_id.desc()).paginate(page=request.args.get("page", 1, type=int), per_page=15, error_out=False)
    return render_template("purchases/list.html", p=p, suppliers=Supplier.query.order_by(Supplier.supplier_name).all())


@bp.route("/new")
@permission_required("purchases")
def new():
    products = [dict(id=p.product_id, name=f"{p.sku} - {p.product_name}", cost=float(p.cost_price or 0), gst=float(p.gst_rate or 0))
                for p in Product.query.filter_by(is_active=True).order_by(Product.product_name)]
    return render_template("purchases/new.html", suppliers=Supplier.query.filter_by(is_active=True).order_by(Supplier.supplier_name).all(),
                           products=products, today=date.today().isoformat())


@bp.route("/save", methods=["POST"])
@permission_required("purchases")
def save():
    d = request.get_json(silent=True) or {}
    try:
        pur, dup = create_purchase(current_user.user_id, d.get("supplier_id"), d.get("items", []),
                                   datetime.strptime(d["date"], "%Y-%m-%d").date() if d.get("date") else None,
                                   d.get("supplier_invoice_no"), d.get("idempotency_key"))
    except (BusinessError, ValueError, KeyError, TypeError) as e:
        db.session.rollback()
        return jsonify(ok=False, error=str(e)), 400
    return jsonify(ok=True, duplicate=dup, url=url_for("purchases.detail", pid=pur.purchase_id))


@bp.route("/<int:pid>")
@permission_required("purchases")
def detail(pid):
    return render_template("purchases/detail.html", pur=db.session.get(Purchase, pid) or abort(404))
