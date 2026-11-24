from datetime import datetime, timedelta
from io import BytesIO
from flask import Blueprint, render_template, request, redirect, url_for, flash, abort, send_file
from flask_login import current_user
from .. import db
from ..models import Sale, Customer, Return, SalePayment
from ..utils.perms import permission_required
from ..services.sales import cancel_sale, create_return
from ..services.stock import BusinessError

bp = Blueprint("sales", __name__, url_prefix="/sales")


@bp.route("/")
@permission_required("sales")
def list_view():
    q = Sale.query
    s = request.args.get("q", "").strip()
    if s:
        q = q.outerjoin(Customer).filter(db.or_(Sale.invoice_no.ilike(f"%{s}%"), Customer.full_name.ilike(f"%{s}%")))
    for arg, op in (("from", ">="), ("to", "<")):
        v = request.args.get(arg)
        if v:
            d = datetime.strptime(v, "%Y-%m-%d") + (timedelta(days=1) if arg == "to" else timedelta())
            q = q.filter(Sale.sale_date >= d) if op == ">=" else q.filter(Sale.sale_date < d)
    if request.args.get("status"):
        q = q.filter(Sale.status == request.args["status"])
    if request.args.get("customer"):
        q = q.filter(Sale.customer_id == int(request.args["customer"]))
    if request.args.get("payment"):
        q = q.filter(Sale.payments.any(SalePayment.method == request.args["payment"]))
    p = q.order_by(Sale.sale_id.desc()).paginate(page=request.args.get("page", 1, type=int), per_page=15, error_out=False)
    return render_template("sales/list.html", p=p, customers=Customer.query.order_by(Customer.full_name).all(), s=s)


@bp.route("/<int:sale_id>")
@permission_required("sales")
def invoice(sale_id):
    sale = db.session.get(Sale, sale_id) or abort(404)
    return render_template("sales/invoice.html", sale=sale, thermal=request.args.get("fmt") == "thermal")


@bp.route("/<int:sale_id>/pdf")
@permission_required("sales")
def invoice_pdf(sale_id):
    from ..utils.pdf import invoice_pdf as build
    from ..utils.settings import get_settings
    sale = db.session.get(Sale, sale_id) or abort(404)
    return send_file(BytesIO(build(sale, get_settings())), mimetype="application/pdf",
                     download_name=f"{sale.invoice_no}.pdf", as_attachment=True)


@bp.route("/<int:sale_id>/cancel", methods=["POST"])
@permission_required("sales")
def cancel(sale_id):
    try:
        cancel_sale(current_user.user_id, sale_id)
        flash("Invoice cancelled and stock restored.", "success")
    except BusinessError as e:
        db.session.rollback()
        flash(str(e), "danger")
    return redirect(url_for("sales.invoice", sale_id=sale_id))


@bp.route("/<int:sale_id>/return", methods=["GET", "POST"])
@permission_required("returns")
def return_form(sale_id):
    sale = db.session.get(Sale, sale_id) or abort(404)
    if request.method == "POST":
        lines = [dict(sale_item_id=i.sale_item_id, quantity=request.form.get(f"qty_{i.sale_item_id}") or 0,
                      condition=request.form.get(f"cond_{i.sale_item_id}", "Resalable")) for i in sale.items]
        try:
            r = create_return(current_user.user_id, sale_id, lines, request.form.get("reason", ""),
                              request.form.get("refund_method", "Cash"))
            flash(f"Return {r.return_no} saved. Refund {r.refund_amount}.", "success")
            return redirect(url_for("sales.returns_list"))
        except (BusinessError, ValueError) as e:
            db.session.rollback()
            flash(str(e), "danger")
    return render_template("returns/form.html", sale=sale)


@bp.route("/returns")
@permission_required("returns")
def returns_list():
    p = Return.query.order_by(Return.return_id.desc()).paginate(page=request.args.get("page", 1, type=int), per_page=15, error_out=False)
    return render_template("returns/list.html", p=p)
