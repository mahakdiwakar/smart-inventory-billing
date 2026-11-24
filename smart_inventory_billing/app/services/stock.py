"""Stock ledger: the ONLY place that changes Products.stock_quantity."""
from sqlalchemy import select, func
from .. import db
from ..models import Product, StockTransaction


class BusinessError(Exception):
    pass


def post_txn(product_id, txn_type, qty_in=0, qty_out=0, ref_type=None, ref_no=None, remarks=None, user_id=None):
    p = db.session.execute(
        select(Product).where(Product.product_id == product_id).with_for_update()
    ).scalar_one_or_none()
    if p is None:
        raise BusinessError(f"Product {product_id} not found")
    new_bal = (p.stock_quantity or 0) + qty_in - qty_out
    if new_bal < 0:
        raise BusinessError(f"Insufficient stock for {p.product_name} (available {p.stock_quantity}, needed {qty_out})")
    p.stock_quantity = new_bal
    db.session.add(StockTransaction(product_id=product_id, txn_type=txn_type, ref_type=ref_type, ref_no=ref_no,
                                    qty_in=qty_in, qty_out=qty_out, balance=new_bal, remarks=remarks,
                                    created_by=user_id))
    return new_bal


def ledger_balance(product_id):
    q = db.session.query(func.coalesce(func.sum(StockTransaction.qty_in - StockTransaction.qty_out), 0)) \
        .filter(StockTransaction.product_id == product_id).scalar()
    return int(q or 0)


def sync_opening_ledger():
    """For existing products whose ledger doesn't match stock_quantity, add an Opening entry for the gap."""
    n = 0
    for p in Product.query.all():
        gap = (p.stock_quantity or 0) - ledger_balance(p.product_id)
        if gap != 0:
            db.session.add(StockTransaction(
                product_id=p.product_id, txn_type="Opening", ref_type="Opening", ref_no="OPENING",
                qty_in=max(gap, 0), qty_out=max(-gap, 0), balance=p.stock_quantity or 0,
                remarks="Opening balance carried from master data"))
            n += 1
    db.session.commit()
    return n
