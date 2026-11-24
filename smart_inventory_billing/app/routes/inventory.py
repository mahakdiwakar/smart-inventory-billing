from datetime import datetime, timedelta
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import current_user
from sqlalchemy import func
from .. import db
from ..models import Product, StockTransaction, Category, StockAdjustment
from ..utils.perms import permission_required
from ..services.purchases import create_adjustment, ADJ_SIGN
from ..services.stock import BusinessError, ledger_balance

bp = Blueprint("inventory", __name__, url_prefix="/inventory")


@bp.route("/")
@permission_required("inventory")
def ledger():
    q = StockTransaction.query
    if request.args.get("product"):
        q = q.filter(StockTransaction.product_id == int(request.args["product"]))
    if request.args.get("type"):
        q = q.filter(StockTransaction.txn_type == request.args["type"])
    if request.args.get("from"):
        q = q.filter(StockTransaction.created_at >= datetime.strptime(request.args["from"], "%Y-%m-%d"))
    if request.args.get("to"):
        q = q.filter(StockTransaction.created_at < datetime.strptime(request.args["to"], "%Y-%m-%d") + timedelta(days=1))
    p = q.order_by(StockTransaction.txn_id.desc()).paginate(page=request.args.get("page", 1, type=int), per_page=20, error_out=False)
    by_cat = db.session.query(Category.category_name, func.sum(Product.stock_quantity), func.sum(Product.stock_quantity * Product.cost_price)) \
        .join(Product, Product.category_id == Category.category_id).group_by(Category.category_name).all()
    mismatches = [x for x in Product.query.all() if ledger_balance(x.product_id) != (x.stock_quantity or 0)]
    return render_template("inventory/ledger.html", p=p, products=Product.query.order_by(Product.product_name).all(),
                           by_cat=by_cat, mismatches=mismatches)


@bp.route("/adjustments", methods=["GET", "POST"])
@permission_required("adjustments")
def adjustments():
    if request.method == "POST":
        pids, qtys = request.form.getlist("product_id"), request.form.getlist("quantity")
        lines = [dict(product_id=a, quantity=b) for a, b in zip(pids, qtys) if a and b not in ("", None)]
        try:
            adj = create_adjustment(current_user.user_id, request.form.get("adjustment_type"), lines, request.form.get("remarks"))
            flash(f"{adj.adjustment_no} posted to the stock ledger.", "success")
            return redirect(url_for("inventory.adjustments"))
        except (BusinessError, ValueError) as e:
            db.session.rollback()
            flash(str(e), "danger")
    return render_template("inventory/adjustments.html", types=list(ADJ_SIGN), products=Product.query.order_by(Product.product_name).all(),
                           recent=StockAdjustment.query.order_by(StockAdjustment.adjustment_id.desc()).limit(15).all())
