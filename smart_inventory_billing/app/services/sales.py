from decimal import Decimal
from datetime import datetime
from sqlalchemy.exc import IntegrityError
from .. import db
from ..models import (Sale, SaleItem, SalePayment, Product, Customer, Return, ReturnItem, Notification)
from ..utils.settings import get_settings
from ..utils.audit import audit
from .stock import post_txn, BusinessError
from .money import dec, q2

METHODS = ("Cash", "UPI", "Card", "Bank_Transfer")


def create_sale(user_id, items, customer_id=None, discount=0, payments=None, idem_key=None):
    """items: [{product_id, quantity}]. One DB transaction; any failure rolls everything back."""
    if idem_key:
        dup = Sale.query.filter_by(idempotency_key=idem_key).first()
        if dup:
            return dup, True  # duplicate submission -> return the original invoice
    if not items:
        raise BusinessError("Cart is empty")
    st = get_settings()
    customer = db.session.get(Customer, int(customer_id)) if customer_id else None
    intra = (not customer) or (customer.state or "").strip().lower() == st["store_state"].strip().lower()

    # merge duplicate product lines
    merged = {}
    for it in items:
        pid, qty = int(it["product_id"]), int(it["quantity"])
        if qty <= 0:
            raise BusinessError("Quantity must be at least 1")
        merged[pid] = merged.get(pid, 0) + qty

    lines = []
    for pid, qty in merged.items():
        p = db.session.get(Product, pid)
        if not p or not p.is_active:
            raise BusinessError(f"Product {pid} is not available")
        lines.append((p, qty, q2(dec(p.selling_price) * qty)))
    subtotal = sum((l[2] for l in lines), Decimal("0"))
    discount = q2(dec(discount))
    if discount < 0 or discount > subtotal:
        raise BusinessError("Discount must be between 0 and the bill subtotal")

    # allocate discount proportionally; last line takes the remainder
    allocated, remaining = [], discount
    for i, (p, qty, gross) in enumerate(lines):
        d = remaining if i == len(lines) - 1 else q2(discount * gross / subtotal) if subtotal else Decimal("0")
        d = min(d, gross)
        remaining -= d
        allocated.append(d)

    sale = Sale(invoice_no="TMP-" + (idem_key or datetime.utcnow().isoformat())[:24], idempotency_key=idem_key,
                customer_id=customer.customer_id if customer else None, subtotal=subtotal, discount=discount,
                taxable_value=subtotal - discount, total=0, created_by=user_id)
    db.session.add(sale)
    try:
        db.session.flush()
    except IntegrityError:
        db.session.rollback()
        dup = Sale.query.filter_by(idempotency_key=idem_key).first()
        if dup:
            return dup, True
        raise
    sale.invoice_no = f"{st['invoice_prefix']}{sale.sale_id:06d}"

    tax_total = Decimal("0")
    for (p, qty, gross), d in zip(lines, allocated):
        taxable = gross - d
        gst = q2(taxable * dec(p.gst_rate) / 100)
        tax_total += gst
        sale.items.append(SaleItem(product_id=p.product_id, quantity=qty, unit_price=dec(p.selling_price),
                                   cost_price=dec(p.cost_price), discount=d, taxable_value=taxable,
                                   gst_rate=dec(p.gst_rate), gst_amount=gst, line_total=taxable + gst))
        post_txn(p.product_id, "Sale", qty_out=qty, ref_type="Sale", ref_no=sale.invoice_no,
                 remarks="POS sale", user_id=user_id)
        if p.stock_quantity <= (p.reorder_level or 0):
            db.session.add(Notification(message=f"Low stock: {p.product_name} ({p.stock_quantity} left)", level="warning"))

    if intra:
        sale.cgst = q2(tax_total / 2)
        sale.sgst = tax_total - sale.cgst
    else:
        sale.igst = tax_total
    sale.gst_amount = tax_total
    exact = sale.taxable_value + tax_total
    sale.total = exact.quantize(Decimal("1"), rounding="ROUND_HALF_UP")
    sale.round_off = sale.total - exact

    paid = Decimal("0")
    for pay in payments or []:
        m, amt = pay.get("method"), q2(dec(pay.get("amount")))
        if m not in METHODS or amt <= 0:
            continue
        sale.payments.append(SalePayment(method=m, amount=amt, reference=(pay.get("reference") or None)))
        paid += amt
    if paid > sale.total:  # change returned to customer (only cash can give change)
        paid = sale.total
        sale.payments[-1].amount -= (sum(p.amount for p in sale.payments) - sale.total)
    sale.amount_paid = paid
    sale.balance_due = sale.total - paid
    if sale.balance_due > 0 and not customer:
        raise BusinessError("Walk-in customers must pay in full. Select a customer for credit sales.")

    if customer:
        customer.loyalty_points = (customer.loyalty_points or 0) + int(sale.total // int(st["loyalty_rate"] or 100))
    audit("SALE_CREATE", "Sale", sale.sale_id, f"{sale.invoice_no} total {sale.total}")
    db.session.commit()
    return sale, False


def cancel_sale(user_id, sale_id):
    sale = db.session.get(Sale, sale_id)
    if not sale:
        raise BusinessError("Invoice not found")
    if sale.status != "Completed":
        raise BusinessError(f"Only completed, unreturned invoices can be cancelled (status: {sale.status})")
    for it in sale.items:
        post_txn(it.product_id, "Sale_Cancel", qty_in=it.quantity, ref_type="Sale", ref_no=sale.invoice_no,
                 remarks="Invoice cancelled", user_id=user_id)
    if sale.customer:
        rate = int(get_settings()["loyalty_rate"] or 100)
        sale.customer.loyalty_points = max(0, (sale.customer.loyalty_points or 0) - int(sale.total // rate))
    sale.status = "Cancelled"
    audit("SALE_CANCEL", "Sale", sale.sale_id, sale.invoice_no)
    db.session.commit()
    return sale


def create_return(user_id, sale_id, lines, reason, refund_method):
    """lines: [{sale_item_id, quantity, condition}] — validated against sold minus already returned."""
    sale = db.session.get(Sale, sale_id)
    if not sale or sale.status in ("Cancelled", "Draft"):
        raise BusinessError("This invoice cannot accept returns")
    items = {i.sale_item_id: i for i in sale.items}
    ret = Return(return_no="TMP", sale_id=sale.sale_id, reason=reason, refund_method=refund_method,
                 refund_amount=0, created_by=user_id)
    db.session.add(ret)
    db.session.flush()
    ret.return_no = f"RET-{ret.return_id:06d}"
    total = Decimal("0")
    for ln in lines:
        qty = int(ln.get("quantity") or 0)
        if qty <= 0:
            continue
        si = items.get(int(ln["sale_item_id"]))
        if not si:
            raise BusinessError("Item does not belong to this invoice")
        if qty > si.quantity - si.returned_qty:
            raise BusinessError(f"Cannot return {qty} of {si.product.product_name}: only {si.quantity - si.returned_qty} returnable")
        cond = ln.get("condition", "Resalable")
        if cond not in ("Resalable", "Damaged"):
            raise BusinessError("Invalid condition")
        # refund = proportional share of what the customer actually paid (after discount, incl. GST)
        refund = q2(si.line_total * qty / si.quantity)
        gst = q2(si.gst_amount * qty / si.quantity)
        taxable = refund - gst
        si.returned_qty += qty
        ret.items.append(ReturnItem(sale_item_id=si.sale_item_id, product_id=si.product_id, quantity=qty,
                                    item_condition=cond, refund_amount=refund, taxable_refunded=taxable,
                                    gst_refunded=gst, cost_value=q2(dec(si.cost_price) * qty)))
        if cond == "Resalable":
            post_txn(si.product_id, "Sale_Return", qty_in=qty, ref_type="Return", ref_no=ret.return_no,
                     remarks=f"Return vs {sale.invoice_no}", user_id=user_id)
        else:  # recorded in the ledger with zero movement so damaged goods stay traceable but never re-enter stock
            post_txn(si.product_id, "Damaged_Return", ref_type="Return", ref_no=ret.return_no,
                     remarks=f"Damaged return vs {sale.invoice_no} (not restocked)", user_id=user_id)
        total += refund
    if total <= 0:
        raise BusinessError("Select at least one item and quantity to return")
    ret.refund_amount = total
    sale.status = "Returned" if all(i.returned_qty == i.quantity for i in sale.items) else "Partially_Returned"
    audit("RETURN_CREATE", "Return", ret.return_id, f"{ret.return_no} refund {total}")
    db.session.commit()
    return ret
