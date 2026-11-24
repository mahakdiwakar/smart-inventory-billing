import csv
from io import StringIO, BytesIO
from flask import Blueprint, render_template, request, Response, send_file, abort
from ..models import Category, Product, Supplier, Customer
from ..utils.perms import permission_required
from ..services import reports as R

bp = Blueprint("reports", __name__, url_prefix="/reports")


@bp.route("/")
@permission_required("reports")
def index():
    name = request.args.get("r", "daily_sales")
    if name not in R.REPORTS:
        abort(404)
    try:
        headers, rows = R.run(name, request.args)
        err = None
    except ValueError:
        headers, rows, err = [], [], "Check the date format."
    return render_template("reports/index.html", reports=R.REPORTS, name=name, headers=headers, rows=rows, err=err,
                           categories=Category.query.all(), products=Product.query.order_by(Product.product_name).all(),
                           suppliers=Supplier.query.all(), customers=Customer.query.order_by(Customer.full_name).all())


@bp.route("/export/<fmt>")
@permission_required("reports")
def export(fmt):
    name = request.args.get("r", "daily_sales")
    if name not in R.REPORTS:
        abort(404)
    headers, rows = R.run(name, request.args)
    if fmt == "csv":
        buf = StringIO(); w = csv.writer(buf); w.writerow(headers); w.writerows(rows)
        return Response(buf.getvalue(), mimetype="text/csv", headers={"Content-Disposition": f"attachment; filename={name}.csv"})
    if fmt == "xlsx":
        from openpyxl import Workbook
        wb = Workbook(); ws = wb.active; ws.append(headers)
        for r in rows: ws.append(r)
        b = BytesIO(); wb.save(b); b.seek(0)
        return send_file(b, download_name=f"{name}.xlsx", as_attachment=True)
    if fmt == "pdf":
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.platypus import SimpleDocTemplate, Paragraph
        from reportlab.lib.styles import getSampleStyleSheet
        from ..utils.pdf import _table
        b = BytesIO()
        SimpleDocTemplate(b, pagesize=landscape(A4)).build([Paragraph(R.REPORTS[name], getSampleStyleSheet()["Title"]), _table([headers] + [[str(c) for c in r] for r in rows])])
        b.seek(0)
        return send_file(b, mimetype="application/pdf", download_name=f"{name}.pdf", as_attachment=True)
    abort(404)
