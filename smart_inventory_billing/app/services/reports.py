"""Report definitions. PROFIT = net sales (taxable, after discount, minus returns)
 - COGS (cost snapshot x qty sold, minus cost of RESALABLE returns) - expenses. GST is never part of revenue."""
from datetime import datetime, timedelta, date
from decimal import Decimal
from sqlalchemy import func
from .. import db
from ..models import (Sale, SaleItem, Purchase, PurchaseItem, Product, Category, Customer, Supplier, Expense,
                      StockTransaction, ReturnItem, Return)

REPORTS = {
    "daily_sales": "Daily Sales", "monthly_sales": "Monthly Sales", "annual_sales": "Annual Sales",
    "purchases": "Purchases", "profit": "Profit", "valuation": "Inventory Valuation", "low_stock": "Low Stock",
    "customers": "Customers", "suppliers": "Suppliers", "gst": "GST Summary", "product_perf": "Product Performance",
    "expenses": "Expenses", "stock_movement": "Stock Movement",
}


def _range(a):
    s = datetime.strptime(a.get("from") or "2000-01-01", "%Y-%m-%d")
    e = datetime.strptime(a.get("to") or "2999-12-31", "%Y-%m-%d") + timedelta(days=1)
    return s, e


def _bucket(fmt, s, e, a):
    rows = {}
    q = Sale.query.filter(Sale.status != "Cancelled", Sale.sale_date >= s, Sale.sale_date < e)
    if a.get("customer"):
        q = q.filter(Sale.customer_id == int(a["customer"]))
    for x in q:
        r = rows.setdefault(x.sale_date.strftime(fmt), [0, Decimal(0), Decimal(0), Decimal(0)])
        r[0] += 1; r[1] += x.taxable_value; r[2] += x.gst_amount; r[3] += x.total
    return [[k, v[0], float(v[1]), float(v[2]), float(v[3])] for k, v in sorted(rows.items())]


def run(name, a):
    s, e = _range(a)
    H = ["Period", "Invoices", "Taxable", "GST", "Total"]
    if name == "daily_sales": return H, _bucket("%Y-%m-%d", s, e, a)
    if name == "monthly_sales": return H, _bucket("%Y-%m", s, e, a)
    if name == "annual_sales": return H, _bucket("%Y", s, e, a)
    if name == "purchases":
        q = Purchase.query.filter(Purchase.status == "Completed", Purchase.purchase_date >= s.date(), Purchase.purchase_date < e.date())
        if a.get("supplier"): q = q.filter(Purchase.supplier_id == int(a["supplier"]))
        return ["Purchase no", "Date", "Supplier", "Subtotal", "GST", "Total"], \
            [[p.purchase_no, str(p.purchase_date), p.supplier.supplier_name, float(p.subtotal), float(p.gst_amount), float(p.total)] for p in q.order_by(Purchase.purchase_id)]
    if name == "profit":
        items = db.session.query(SaleItem).join(Sale).filter(Sale.status != "Cancelled", Sale.sale_date >= s, Sale.sale_date < e).all()
        rev = sum((i.taxable_value for i in items), Decimal(0))
        cogs = sum((i.cost_price * i.quantity for i in items), Decimal(0))
        rets = db.session.query(ReturnItem).join(Return).join(Sale, Sale.sale_id == Return.sale_id).filter(
            Sale.status != "Cancelled", Return.created_at >= s, Return.created_at < e).all()
        ret_rev = sum((r.taxable_refunded for r in rets), Decimal(0))
        ret_cogs = sum((r.cost_value for r in rets if r.item_condition == "Resalable"), Decimal(0))
        exp = db.session.query(func.coalesce(func.sum(Expense.amount), 0)).filter(Expense.expense_date >= s.date(), Expense.expense_date < e.date()).scalar()
        net_rev, net_cogs = rev - ret_rev, cogs - ret_cogs
        gross = net_rev - net_cogs
        return ["Line", "Amount"], [["Net sales (taxable, after discount & returns)", float(net_rev)],
            ["Cost of goods sold (net of resalable returns)", float(net_cogs)], ["Gross profit", float(gross)],
            ["Expenses", float(exp)], ["Net profit", float(gross - Decimal(exp))]]
    if name == "valuation":
        q = Product.query
        if a.get("category"): q = q.filter(Product.category_id == int(a["category"]))
        return ["SKU", "Product", "Stock", "Cost", "Value"], [[p.sku, p.product_name, p.stock_quantity, float(p.cost_price or 0), float((p.cost_price or 0) * (p.stock_quantity or 0))] for p in q.order_by(Product.product_name)]
    if name == "low_stock":
        return ["SKU", "Product", "Stock", "Reorder level"], [[p.sku, p.product_name, p.stock_quantity, p.reorder_level] for p in Product.query.filter(Product.stock_quantity <= Product.reorder_level).order_by(Product.stock_quantity)]
    if name == "customers":
        rows = db.session.query(Customer.full_name, Customer.phone, func.count(Sale.sale_id), func.coalesce(func.sum(Sale.total), 0)) \
            .outerjoin(Sale, (Sale.customer_id == Customer.customer_id) & (Sale.status != "Cancelled")).group_by(Customer.customer_id, Customer.full_name, Customer.phone).all()
        return ["Customer", "Phone", "Invoices", "Spent"], [[r[0], r[1], r[2], float(r[3])] for r in rows]
    if name == "suppliers":
        rows = db.session.query(Supplier.supplier_name, Supplier.gstin, func.count(Purchase.purchase_id), func.coalesce(func.sum(Purchase.total), 0)) \
            .outerjoin(Purchase, Purchase.supplier_id == Supplier.supplier_id).group_by(Supplier.supplier_id, Supplier.supplier_name, Supplier.gstin).all()
        return ["Supplier", "GSTIN", "Purchases", "Value"], [[r[0], r[1], r[2], float(r[3])] for r in rows]
    if name == "gst":
        q = Sale.query.filter(Sale.status != "Cancelled", Sale.sale_date >= s, Sale.sale_date < e)
        o = [sum((getattr(x, f) for x in q), Decimal(0)) for f in ("taxable_value", "cgst", "sgst", "igst")]
        pin = db.session.query(func.coalesce(func.sum(Purchase.gst_amount), 0)).filter(Purchase.status == "Completed", Purchase.purchase_date >= s.date(), Purchase.purchase_date < e.date()).scalar()
        ret = db.session.query(func.coalesce(func.sum(ReturnItem.gst_refunded), 0)).join(Return).filter(Return.created_at >= s, Return.created_at < e).scalar()
        out = o[1] + o[2] + o[3] - Decimal(ret)
        return ["Component", "Amount"], [["Taxable sales", float(o[0])], ["CGST collected", float(o[1])], ["SGST collected", float(o[2])],
            ["IGST collected", float(o[3])], ["Less: GST on returns", float(ret)], ["Net output GST", float(out)],
            ["Input GST (purchases)", float(pin)], ["Net GST payable", float(out - Decimal(pin))]]
    if name == "product_perf":
        rows = db.session.query(Product.sku, Product.product_name, func.sum(SaleItem.quantity - SaleItem.returned_qty), func.sum(SaleItem.taxable_value)) \
            .join(SaleItem, SaleItem.product_id == Product.product_id).join(Sale, Sale.sale_id == SaleItem.sale_id) \
            .filter(Sale.status != "Cancelled", Sale.sale_date >= s, Sale.sale_date < e).group_by(Product.product_id, Product.sku, Product.product_name).order_by(func.sum(SaleItem.taxable_value).desc()).all()
        return ["SKU", "Product", "Net units sold", "Taxable sales"], [[r[0], r[1], int(r[2] or 0), float(r[3] or 0)] for r in rows]
    if name == "expenses":
        return ["Date", "Category", "Amount", "Method", "Description"], [[str(x.expense_date), x.category, float(x.amount), x.payment_method, x.description] for x in Expense.query.filter(Expense.expense_date >= s.date(), Expense.expense_date < e.date()).order_by(Expense.expense_date)]
    if name == "stock_movement":
        q = StockTransaction.query.filter(StockTransaction.created_at >= s, StockTransaction.created_at < e)
        if a.get("product"): q = q.filter(StockTransaction.product_id == int(a["product"]))
        return ["Date", "Product", "Type", "Ref", "In", "Out", "Balance"], [[x.created_at.strftime("%Y-%m-%d %H:%M"), x.product.product_name, x.txn_type, x.ref_no, x.qty_in, x.qty_out, x.balance] for x in q.order_by(StockTransaction.txn_id)]
    raise KeyError(name)
