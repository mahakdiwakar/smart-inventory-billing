from datetime import date, datetime, timedelta
from decimal import Decimal
from collections import defaultdict
from flask import Blueprint, render_template, jsonify
from sqlalchemy import func
from .. import db
from ..models import (Product, Category, Customer, Supplier, Sale, SaleItem, Purchase, AuditLog, Return)
from ..utils.perms import permission_required

bp = Blueprint("dashboard", __name__)


def _active_sales(q):
    return q.filter(Sale.status != "Cancelled")


@bp.route("/")
@permission_required("dashboard")
def index():
    today = date.today()
    month_start = datetime(today.year, today.month, 1)
    day_start = datetime(today.year, today.month, today.day)
    net = lambda q: (q.scalar() or 0)
    kpi = {
        "products": Product.query.filter_by(is_active=True).count(),
        "categories": Category.query.count(),
        "suppliers": Supplier.query.count(),
        "customers": Customer.query.count(),
        "today_sales": net(_active_sales(db.session.query(func.sum(Sale.total))).filter(Sale.sale_date >= day_start)),
        "month_sales": net(_active_sales(db.session.query(func.sum(Sale.total))).filter(Sale.sale_date >= month_start)),
        "month_purchases": net(db.session.query(func.sum(Purchase.total)).filter(
            Purchase.status == "Completed", Purchase.purchase_date >= month_start.date())),
        "low_stock": Product.query.filter(Product.is_active == True, Product.stock_quantity <= Product.reorder_level).count(),
        "stock_value": net(db.session.query(func.sum(Product.stock_quantity * Product.cost_price))),
    }
    low = Product.query.filter(Product.is_active == True, Product.stock_quantity <= Product.reorder_level) \
        .order_by(Product.stock_quantity).limit(8).all()
    recent_sales = Sale.query.order_by(Sale.sale_id.desc()).limit(6).all()
    recent_pur = Purchase.query.order_by(Purchase.purchase_id.desc()).limit(6).all()
    acts = AuditLog.query.order_by(AuditLog.log_id.desc()).limit(8).all()
    return render_template("dashboard/index.html", kpi=kpi, low=low, recent_sales=recent_sales,
                           recent_pur=recent_pur, acts=acts)


@bp.route("/dashboard/data")
@permission_required("dashboard")
def data():
    today = date.today()
    start12 = datetime(today.year - 1 if today.month < 12 else today.year, (today.month % 12) + 1, 1)
    sales = db.session.query(Sale.sale_date, Sale.total).filter(Sale.status != "Cancelled", Sale.sale_date >= start12).all()
    purs = db.session.query(Purchase.purchase_date, Purchase.total).filter(Purchase.status == "Completed",
                                                                         Purchase.purchase_date >= start12.date()).all()
    months, s_m, p_m = [], defaultdict(float), defaultdict(float)
    y, m = start12.year, start12.month
    for _ in range(12):
        months.append(f"{y}-{m:02d}")
        m += 1
        if m == 13:
            y, m = y + 1, 1
    for d, t in sales:
        s_m[d.strftime("%Y-%m")] += float(t)
    for d, t in purs:
        p_m[d.strftime("%Y-%m")] += float(t)
    d30 = datetime.combine(today - timedelta(days=29), datetime.min.time())
    daily = defaultdict(float)
    for d, t in db.session.query(Sale.sale_date, Sale.total).filter(Sale.status != "Cancelled", Sale.sale_date >= d30):
        daily[d.strftime("%Y-%m-%d")] += float(t)
    days = [(today - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(29, -1, -1)]
    cats = db.session.query(Category.category_name, func.count(Product.product_id)).join(
        Product, Product.category_id == Category.category_id).group_by(Category.category_name).all()
    top = db.session.query(Product.product_name, func.sum(SaleItem.quantity - SaleItem.returned_qty).label("q")) \
        .join(SaleItem, SaleItem.product_id == Product.product_id).join(Sale, Sale.sale_id == SaleItem.sale_id) \
        .filter(Sale.status != "Cancelled").group_by(Product.product_name).order_by(func.sum(SaleItem.quantity - SaleItem.returned_qty).desc()).limit(10).all()
    return jsonify(
        monthly={"labels": months, "sales": [s_m[x] for x in months], "purchases": [p_m[x] for x in months]},
        daily={"labels": days, "values": [daily[x] for x in days]},
        categories={"labels": [c[0] for c in cats], "values": [c[1] for c in cats]},
        top={"labels": [t[0] for t in top], "values": [int(t[1] or 0) for t in top]})
