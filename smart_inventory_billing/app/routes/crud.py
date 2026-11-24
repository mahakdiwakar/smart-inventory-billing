import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, current_app
from sqlalchemy import or_, func
from sqlalchemy.exc import IntegrityError
from .. import db
from ..models import (Category, Supplier, Customer, Employee, Product, Expense, Sale, Purchase, ROLES)
from ..utils.perms import permission_required, can
from ..utils.audit import audit
from flask_login import login_required

bp = Blueprint("crud", __name__)

UOM = ["PCS", "KG", "GM", "LTR", "ML", "BOX", "PACK"]
PAY = ["Cash", "UPI", "Card", "Bank_Transfer"]
F = lambda name, label, type="text", req=False, **kw: dict(name=name, label=label, type=type, required=req, **kw)

ENTITIES = {
    "products": dict(model=Product, title="Products", pk="product_id", perm="products", active="is_active",
                     search=["product_name", "sku", "hsn_code"], order="product_name",
                     cols=[("sku", "SKU"), ("product_name", "Product"), ("category.category_name", "Category"),
                           ("selling_price", "Price|inr"), ("gst_rate", "GST %"), ("stock_quantity", "Stock"),
                           ("stock_status", "Status|badge")],
                     fields=[F("sku", "SKU (blank = auto-generate)"), F("hsn_code", "HSN code", req=True, maxlen=8),
                             F("product_name", "Product name", req=True),
                             F("category_id", "Category", "select", True, choices="categories"),
                             F("unit_of_measure", "Unit", "select", True, choices=UOM),
                             F("cost_price", "Cost price", "money", True), F("selling_price", "Selling price", "money", True),
                             F("gst_rate", "GST rate %", "money", True), F("reorder_level", "Reorder level", "int"),
                             F("is_active", "Active", "bool")],
                     note="Stock quantity can't be edited here. Use Purchases or Stock Adjustments so the ledger stays correct."),
    "categories": dict(model=Category, title="Categories", pk="category_id", perm="categories", active="is_active",
                       search=["category_name", "description"], order="category_name",
                       cols=[("category_name", "Name"), ("hsn_default_prefix", "HSN prefix"), ("description", "Description"),
                             ("is_active", "Active|yesno")],
                       fields=[F("category_name", "Category name", req=True), F("hsn_default_prefix", "HSN default prefix", maxlen=8),
                               F("description", "Description"), F("is_active", "Active", "bool")], deletable=True),
    "suppliers": dict(model=Supplier, title="Suppliers", pk="supplier_id", perm="suppliers", active="is_active",
                      search=["supplier_name", "phone", "gstin", "city"], order="supplier_name", detail=True,
                      cols=[("supplier_name", "Supplier"), ("contact_person", "Contact"), ("phone", "Phone"),
                            ("gstin", "GSTIN"), ("city", "City"), ("is_active", "Active|yesno")],
                      fields=[F("supplier_name", "Supplier name", req=True), F("contact_person", "Contact person"),
                              F("phone", "Phone", req=True, kind="phone"), F("email", "Email", kind="email"),
                              F("gstin", "GSTIN (15 characters)", req=True, kind="gstin"), F("address", "Address", "textarea"),
                              F("city", "City", req=True), F("state", "State", req=True), F("is_active", "Active", "bool")]),
    "customers": dict(model=Customer, title="Customers", pk="customer_id", perm="customers", active=None,
                      search=["full_name", "phone", "email", "gstin"], order="full_name", detail=True,
                      cols=[("full_name", "Name"), ("phone", "Phone"), ("gstin", "GSTIN (B2B)"), ("city", "City"),
                            ("loyalty_points", "Points")],
                      fields=[F("full_name", "Full name", req=True), F("phone", "Phone", req=True, kind="phone"),
                              F("email", "Email", kind="email"), F("gstin", "GSTIN (leave blank for B2C)", kind="gstin"),
                              F("address", "Address", "textarea"), F("city", "City"), F("state", "State"),
                              F("loyalty_points", "Loyalty points", "int")]),
    "employees": dict(model=Employee, title="Employees", pk="employee_id", perm="employees", active="is_active",
                      search=["full_name", "phone", "email"], order="full_name",
                      cols=[("full_name", "Name"), ("role", "Role"), ("phone", "Phone"), ("salary", "Salary|inr"),
                            ("hire_date", "Hired"), ("is_active", "Active|yesno")],
                      fields=[F("full_name", "Full name", req=True), F("role", "Role", "select", True, choices=list(ROLES)),
                              F("phone", "Phone", kind="phone"), F("email", "Email", kind="email"),
                              F("salary", "Salary", "money"), F("hire_date", "Hire date", "date"), F("is_active", "Active", "bool")]),
    "expenses": dict(model=Expense, title="Expenses", pk="expense_id", perm="expenses", active=None,
                     search=["category", "description"], order="-expense_date", deletable=True,
                     cols=[("expense_date", "Date"), ("category", "Category"), ("amount", "Amount|inr"),
                           ("payment_method", "Method"), ("description", "Description")],
                     fields=[F("category", "Expense category", req=True), F("amount", "Amount", "money", True),
                             F("expense_date", "Date", "date", True), F("payment_method", "Payment method", "select", True, choices=PAY),
                             F("description", "Description")]),
}


def _cfg(key):
    c = ENTITIES.get(key)
    if not c:
        abort(404)
    if not can(c["perm"]):
        abort(403)
    return c


def _choices(f):
    ch = f.get("choices")
    if ch == "categories":
        return [(c.category_id, c.category_name) for c in Category.query.filter_by(is_active=True).order_by(Category.category_name)]
    return [(x, x) for x in ch]


def _getattr_path(obj, path):
    for part in path.split("."):
        obj = getattr(obj, part, None) if obj is not None else None
    return obj


def parse_form(cfg, form, obj=None):
    vals, errors = {}, []
    for f in cfg["fields"]:
        n, raw = f["name"], (form.get(f["name"]) or "").strip()
        t = f["type"]
        if t == "bool":
            vals[n] = form.get(n) == "on"
            continue
        if not raw:
            if f["required"] and not (n == "sku"):
                errors.append(f"{f['label']} is required")
            vals[n] = None
            continue
        try:
            if t == "money":
                v = Decimal(raw)
                if v < 0:
                    raise InvalidOperation
                vals[n] = v
            elif t == "int":
                vals[n] = int(raw)
                if vals[n] < 0:
                    raise ValueError
            elif t == "date":
                vals[n] = datetime.strptime(raw, "%Y-%m-%d").date()
            elif t == "select" and n == "category_id":
                vals[n] = int(raw)
            else:
                vals[n] = raw
        except (InvalidOperation, ValueError):
            errors.append(f"{f['label']} is not valid")
            continue
        k = f.get("kind")
        if k == "gstin" and len(raw) != 15:
            errors.append("GSTIN must be exactly 15 characters")
        if k == "phone" and not re.fullmatch(r"\+?\d{10,14}", raw):
            errors.append("Phone must be 10 to 14 digits")
        if k == "email" and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", raw):
            errors.append("Email is not valid")
        if f.get("maxlen") and len(raw) > f["maxlen"]:
            errors.append(f"{f['label']} must be at most {f['maxlen']} characters")
    return vals, errors


@bp.route("/<key>/")
@login_required
def list_view(key):
    cfg = _cfg(key)
    M = cfg["model"]
    q = M.query
    s = request.args.get("q", "").strip()
    if s:
        q = q.filter(or_(*[getattr(M, c).ilike(f"%{s}%") for c in cfg["search"]]))
    extra = {}
    if key == "products":
        cat, stock = request.args.get("category", ""), request.args.get("stock", "")
        if cat:
            q = q.filter(Product.category_id == int(cat))
        if stock == "out":
            q = q.filter(Product.stock_quantity <= 0)
        elif stock == "low":
            q = q.filter(Product.stock_quantity > 0, Product.stock_quantity <= Product.reorder_level)
        elif stock == "in":
            q = q.filter(Product.stock_quantity > Product.reorder_level)
        extra = dict(categories=Category.query.order_by(Category.category_name).all(),
                     stats=dict(total=Product.query.count(),
                                low=Product.query.filter(Product.stock_quantity > 0, Product.stock_quantity <= Product.reorder_level).count(),
                                out=Product.query.filter(Product.stock_quantity <= 0).count(),
                                value=db.session.query(func.sum(Product.stock_quantity * Product.cost_price)).scalar() or 0))
    sort = request.args.get("sort") or cfg["order"]
    desc = sort.startswith("-")
    col = getattr(M, sort.lstrip("-"), None) or getattr(M, getattr(M, "__mapper__").primary_key[0].name)
    q = q.order_by(col.desc() if desc else col.asc())
    page = request.args.get("page", 1, type=int)
    p = q.paginate(page=page, per_page=current_app.config["PER_PAGE"], error_out=False)
    return render_template("crud/list.html", key=key, cfg=cfg, p=p, get=_getattr_path, s=s, sort=sort, **extra)


@bp.route("/<key>/new", methods=["GET", "POST"])
@bp.route("/<key>/<int:id>/edit", methods=["GET", "POST"])
@login_required
def form_view(key, id=None):
    cfg = _cfg(key)
    M = cfg["model"]
    obj = db.session.get(M, id) if id else None
    if id and not obj:
        abort(404)
    errors = []
    if request.method == "POST":
        vals, errors = parse_form(cfg, request.form, obj)
        if not errors:
            try:
                if key == "products" and not vals.get("sku"):
                    cat = db.session.get(Category, vals["category_id"])
                    base = (cat.hsn_default_prefix or cat.category_name[:3]).upper().replace(" ", "")[:4]
                    vals["sku"] = f"{base}-{(db.session.query(func.max(Product.product_id)).scalar() or 0) + 1:05d}"
                if key == "customers":
                    vals["city"] = vals.get("city") or "Mumbai"
                    vals["state"] = vals.get("state") or "Maharashtra"
                    vals["loyalty_points"] = vals.get("loyalty_points") or 0
                if key == "products":
                    vals["reorder_level"] = 10 if vals.get("reorder_level") is None else vals["reorder_level"]
                if obj is None:
                    obj = M(**{k: v for k, v in vals.items() if v is not None or k in ("is_active",)})
                    db.session.add(obj)
                else:
                    for k, v in vals.items():
                        setattr(obj, k, v)
                db.session.flush()
                audit("CREATE" if not id else "UPDATE", cfg["title"], getattr(obj, cfg["pk"]), "")
                db.session.commit()
                flash(f"{cfg['title'][:-1] if cfg['title'].endswith('s') else cfg['title']} saved.", "success")
                return redirect(url_for("crud.list_view", key=key))
            except IntegrityError as e:
                db.session.rollback()
                errors = ["A record with the same unique value (name, SKU, phone, email or GSTIN) already exists."]
    fields = [dict(f, options=_choices(f) if f["type"] == "select" else None) for f in cfg["fields"]]
    return render_template("crud/form.html", key=key, cfg=cfg, obj=obj, fields=fields, errors=errors,
                           form=request.form if request.method == "POST" else None)


@bp.route("/<key>/<int:id>/toggle", methods=["POST"])
@login_required
def toggle(key, id):
    cfg = _cfg(key)
    obj = db.session.get(cfg["model"], id) or abort(404)
    if not cfg.get("active"):
        abort(404)
    setattr(obj, cfg["active"], not getattr(obj, cfg["active"]))
    audit("TOGGLE", cfg["title"], id)
    db.session.commit()
    return redirect(request.referrer or url_for("crud.list_view", key=key))


@bp.route("/<key>/<int:id>/delete", methods=["POST"])
@login_required
def delete(key, id):
    cfg = _cfg(key)
    if not cfg.get("deletable"):
        abort(404)
    obj = db.session.get(cfg["model"], id) or abort(404)
    if key == "categories" and Product.query.filter_by(category_id=id).count():
        flash("This category has products. Deactivate it instead of deleting.", "warning")
        return redirect(url_for("crud.list_view", key=key))
    db.session.delete(obj)
    audit("DELETE", cfg["title"], id)
    db.session.commit()
    flash("Deleted.", "success")
    return redirect(url_for("crud.list_view", key=key))


@bp.route("/<key>/<int:id>")
@login_required
def detail(key, id):
    cfg = _cfg(key)
    if not cfg.get("detail"):
        abort(404)
    obj = db.session.get(cfg["model"], id) or abort(404)
    if key == "customers":
        hist = Sale.query.filter_by(customer_id=id).order_by(Sale.sale_id.desc()).limit(50).all()
        spent = sum((s.total for s in hist if s.status != "Cancelled"), Decimal("0"))
        extra = dict(history=hist, total=spent, kind="sales")
    else:
        hist = Purchase.query.filter_by(supplier_id=id).order_by(Purchase.purchase_id.desc()).limit(50).all()
        extra = dict(history=hist, total=sum((p.total for p in hist), Decimal("0")), kind="purchases")
    return render_template("crud/detail.html", key=key, cfg=cfg, obj=obj, **extra)
