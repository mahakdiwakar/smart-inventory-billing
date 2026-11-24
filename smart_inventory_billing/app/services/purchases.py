from decimal import Decimal
from datetime import date
from sqlalchemy.exc import IntegrityError
from .. import db
from ..models import Purchase, PurchaseItem, Product, Supplier, StockAdjustment, StockAdjustmentItem
from ..utils.audit import audit
from .stock import post_txn, BusinessError
from .money import dec, q2


def create_purchase(user_id, supplier_id, items, purchase_date=None, supplier_invoice_no=None, idem_key=None):
    if idem_key:
        dup = Purchase.query.filter_by(idempotency_key=idem_key).first()
        if dup:
            return dup, True
    if not db.session.get(Supplier, int(supplier_id)):
        raise BusinessError("Select a valid supplier")
    if not items:
        raise BusinessError("Add at least one product")
    pur = Purchase(purchase_no="TMP-" + (idem_key or "x")[:24], supplier_id=int(supplier_id),
                   purchase_date=purchase_date or date.today(), supplier_invoice_no=supplier_invoice_no,
                   subtotal=0, gst_amount=0, total=0, idempotency_key=idem_key, created_by=user_id)
    db.session.add(pur)
    try:
        db.session.flush()
    except IntegrityError:
        db.session.rollback()
        dup = Purchase.query.filter_by(idempotency_key=idem_key).first()
        if dup:
            return dup, True
        raise
    pur.purchase_no = f"PUR-{pur.purchase_id:06d}"
    sub = gst_t = Decimal("0")
    for it in items:
        p = db.session.get(Product, int(it["product_id"]))
        qty, cost = int(it["quantity"]), q2(dec(it["unit_cost"]))
        if not p or qty <= 0 or cost < 0:
            raise BusinessError("Invalid purchase line")
        rate = dec(it.get("gst_rate", p.gst_rate))
        base = q2(cost * qty)
        gst = q2(base * rate / 100)
        sub += base
        gst_t += gst
        pur.items.append(PurchaseItem(product_id=p.product_id, quantity=qty, unit_cost=cost, gst_rate=rate,
                                      gst_amount=gst, line_total=base + gst))
        post_txn(p.product_id, "Purchase", qty_in=qty, ref_type="Purchase", ref_no=pur.purchase_no,
                 remarks=f"Purchase from supplier #{pur.supplier_id}", user_id=user_id)
    pur.subtotal, pur.gst_amount, pur.total = sub, gst_t, sub + gst_t
    audit("PURCHASE_CREATE", "Purchase", pur.purchase_id, f"{pur.purchase_no} total {pur.total}")
    db.session.commit()
    return pur, False


ADJ_SIGN = {"Opening Stock": 1, "Stock Increase": 1, "Stock Decrease": -1,
            "Damaged Goods": -1, "Expired Goods": -1, "Correction": 0}


def create_adjustment(user_id, adj_type, lines, remarks=None):
    """Correction takes a signed quantity; every other type takes a positive quantity."""
    if adj_type not in ADJ_SIGN:
        raise BusinessError("Invalid adjustment type")
    adj = StockAdjustment(adjustment_no="TMP", adjustment_type=adj_type, remarks=remarks, created_by=user_id)
    db.session.add(adj)
    db.session.flush()
    adj.adjustment_no = f"ADJ-{adj.adjustment_id:06d}"
    done = 0
    for ln in lines:
        qty = int(ln["quantity"])
        if qty == 0:
            continue
        sign = ADJ_SIGN[adj_type]
        if sign != 0 and qty < 0:
            raise BusinessError("Enter a positive quantity for this adjustment type")
        eff = qty * sign if sign else qty
        pid = int(ln["product_id"])
        adj.items.append(StockAdjustmentItem(product_id=pid, quantity=eff))
        post_txn(pid, "Adjustment", qty_in=max(eff, 0), qty_out=max(-eff, 0), ref_type="Adjustment",
                 ref_no=adj.adjustment_no, remarks=f"{adj_type}: {remarks or ''}"[:255], user_id=user_id)
        done += 1
    if not done:
        raise BusinessError("Enter a non-zero quantity for at least one product")
    audit("ADJUSTMENT", "Stock_Adjustment", adj.adjustment_id, f"{adj.adjustment_no} {adj_type}")
    db.session.commit()
    return adj
