from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer


def _table(data, widths=None, head=True):
    t = Table(data, colWidths=widths, repeatRows=1 if head else 0)
    st = [("FONTSIZE", (0, 0), (-1, -1), 8), ("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
          ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]
    if head:
        st += [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f1b3d")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white)]
    t.setStyle(TableStyle(st))
    return t


def invoice_pdf(sale, st):
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=36)
    ss = getSampleStyleSheet()
    el = [Paragraph(f"<b>{st['store_name']}</b>", ss["Title"]),
          Paragraph(f"{st['store_address']} | GSTIN {st['store_gstin']}", ss["Normal"]), Spacer(1, 10),
          Paragraph(f"<b>Tax Invoice {sale.invoice_no}</b> &nbsp; Date: {sale.sale_date:%d-%b-%Y %H:%M}", ss["Heading3"])]
    c = sale.customer
    el.append(Paragraph(f"Customer: {c.full_name + ' (' + c.phone + ')' if c else 'Walk-in'}" + (f" | GSTIN {c.gstin}" if c and c.gstin else ""), ss["Normal"]))
    el.append(Spacer(1, 8))
    rows = [["#", "Item", "HSN", "Qty", "Rate", "Disc", "GST %", "GST", "Total"]]
    for i, it in enumerate(sale.items, 1):
        rows.append([i, it.product.product_name[:34], it.product.hsn_code, it.quantity, f"{it.unit_price:.2f}",
                     f"{it.discount:.2f}", f"{it.gst_rate:.1f}", f"{it.gst_amount:.2f}", f"{it.line_total:.2f}"])
    el += [_table(rows), Spacer(1, 8)]
    tax = [["Taxable value", f"{sale.taxable_value:.2f}"]]
    if sale.igst:
        tax.append(["IGST", f"{sale.igst:.2f}"])
    else:
        tax += [["CGST", f"{sale.cgst:.2f}"], ["SGST", f"{sale.sgst:.2f}"]]
    tax += [["Round off", f"{sale.round_off:.2f}"], ["Grand total", f"{sale.total:.2f}"],
            ["Paid (" + ", ".join(p.method for p in sale.payments) + ")", f"{sale.amount_paid:.2f}"],
            ["Balance due", f"{sale.balance_due:.2f}"]]
    el += [_table(tax, [150, 90], head=False), Spacer(1, 12), Paragraph(st["invoice_footer"], ss["Italic"])]
    doc.build(el)
    return buf.getvalue()
