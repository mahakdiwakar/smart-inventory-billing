from flask import Blueprint, render_template, request, jsonify, url_for
from sqlalchemy import or_
from ..models import Product, Category, Customer
from ..utils.perms import permission_required
from ..services.sales import create_sale
from ..services.stock import BusinessError

bp = Blueprint("pos", __name__, url_prefix="/pos")


@bp.route("/")
@permission_required("pos")
def index():
    return render_template("pos/index.html",
                           categories=Category.query.filter_by(is_active=True).order_by(Category.category_name).all(),
                           customers=Customer.query.order_by(Customer.full_name).all())


@bp.route("/products")
@permission_required("pos")
def products():
    q, cat = request.args.get("q", "").strip(), request.args.get("category", "")
    qs = Product.query.filter_by(is_active=True)
    if q:
        qs = qs.filter(or_(Product.product_name.ilike(f"%{q}%"), Product.sku.ilike(f"%{q}%")))
    if cat:
        qs = qs.filter(Product.category_id == int(cat))
    return jsonify([dict(id=p.product_id, sku=p.sku, name=p.product_name, price=float(p.selling_price or 0),
                         gst=float(p.gst_rate or 0), stock=p.stock_quantity) for p in qs.order_by(Product.product_name).limit(60)])


@bp.route("/checkout", methods=["POST"])
@permission_required("pos")
def checkout():
    from flask_login import current_user
    d = request.get_json(silent=True) or {}
    try:
        sale, dup = create_sale(current_user.user_id, d.get("items", []), d.get("customer_id") or None,
                                d.get("discount") or 0, d.get("payments", []), d.get("idempotency_key"))
    except (BusinessError, ValueError, KeyError, TypeError) as e:
        from .. import db
        db.session.rollback()
        return jsonify(ok=False, error=str(e)), 400
    return jsonify(ok=True, duplicate=dup, invoice=sale.invoice_no, url=url_for("sales.invoice", sale_id=sale.sale_id))
