from decimal import Decimal
import pytest
from app import db
from app.models import Product, Sale, Customer, Supplier, StockTransaction, Category, Return
from app.services.purchases import create_purchase, create_adjustment
from app.services.sales import create_sale, cancel_sale, create_return
from app.services.stock import BusinessError, ledger_balance
from conftest import login


def pid(sku): return Product.query.filter_by(sku=sku).first().product_id
def stock(sku): return Product.query.filter_by(sku=sku).first().stock_quantity


def stocked(uid, qty=20):
    s = Supplier.query.first()
    create_purchase(uid, s.supplier_id, [dict(product_id=pid("P1"), quantity=qty, unit_cost=40), dict(product_id=pid("P2"), quantity=qty, unit_cost=20)])


def test_login_and_roles(client):
    assert b"incorrect" in client.post("/login", data={"email": "admin@t.com", "password": "bad"}).data
    login(client, "Cashier")
    assert client.get("/pos/").status_code == 200
    assert client.get("/purchases/").status_code == 403
    assert client.get("/employees/").status_code == 403
    assert client.get("/settings/").status_code == 403


def test_inventory_clerk_cannot_pos(client):
    login(client, "Inventory_Clerk")
    assert client.get("/pos/").status_code == 403
    assert client.get("/purchases/").status_code == 200


def test_every_admin_page_loads(client, uid):
    login(client)
    for u in ["/", "/dashboard/data", "/pos/", "/pos/products", "/products/", "/categories/", "/suppliers/", "/customers/", "/employees/",
              "/expenses/", "/sales/", "/sales/returns", "/purchases/", "/purchases/new", "/inventory/", "/inventory/adjustments",
              "/reports/", "/settings/", "/profile", "/products/new", "/categories/new", "/customers/new"]:
        assert client.get(u).status_code == 200, u
    for r in ["daily_sales", "monthly_sales", "annual_sales", "purchases", "profit", "valuation", "low_stock", "customers",
              "suppliers", "gst", "product_perf", "expenses", "stock_movement"]:
        assert client.get(f"/reports/?r={r}").status_code == 200, r
        for f in ("csv", "xlsx", "pdf"):
            assert client.get(f"/reports/export/{f}?r={r}").status_code == 200, (r, f)


def test_crud_category_product_customer(client):
    login(client)
    client.post("/categories/new", data={"category_name": "Dairy", "is_active": "on"})
    assert Category.query.filter_by(category_name="Dairy").count() == 1
    r = client.post("/categories/new", data={"category_name": "Dairy"})
    assert b"already exists" in r.data
    cid = Category.query.filter_by(category_name="Dairy").first().category_id
    client.post("/products/new", data=dict(hsn_code="0401", product_name="Milk", category_id=cid, unit_of_measure="LTR",
                                           cost_price="50", selling_price="60", gst_rate="5", is_active="on"))
    p = Product.query.filter_by(product_name="Milk").first()
    assert p and p.sku.startswith("GRO") is False and p.stock_quantity == 0
    client.post(f"/categories/{cid}/delete")  # has product -> must stay
    assert db.session.get(Category, cid)
    assert b"15 characters" in client.post("/suppliers/new", data=dict(supplier_name="X", phone="9876543210", gstin="123", city="a", state="b")).data
    client.post("/customers/new", data=dict(full_name="Zed", phone="9111111111"))
    assert Customer.query.filter_by(full_name="Zed").first().state == "Maharashtra"


def test_purchase_adds_stock_and_ledger(uid):
    stocked(uid, 10)
    assert stock("P1") == 10 and ledger_balance(pid("P1")) == 10
    assert StockTransaction.query.filter_by(txn_type="Purchase").count() == 2


def test_purchase_duplicate_prevented(uid):
    s = Supplier.query.first()
    it = [dict(product_id=pid("P1"), quantity=5, unit_cost=40)]
    a, d1 = create_purchase(uid, s.supplier_id, it, idem_key="k1")
    b, d2 = create_purchase(uid, s.supplier_id, it, idem_key="k1")
    assert d2 and a.purchase_id == b.purchase_id and stock("P1") == 5


def test_sale_deducts_stock_and_gst_intrastate(uid):
    stocked(uid)
    c = Customer.query.filter_by(full_name="Local").first()
    sale, _ = create_sale(uid, [dict(product_id=pid("P1"), quantity=2), dict(product_id=pid("P2"), quantity=1)], c.customer_id,
                          0, [dict(method="Cash", amount=500)], "s1")
    assert stock("P1") == 18 and stock("P2") == 19
    assert sale.taxable_value == Decimal("130.00")
    assert sale.gst_amount == Decimal("10.40") and sale.cgst + sale.sgst == sale.gst_amount and sale.igst == 0
    assert sale.total == 140 and sale.balance_due == 0 and sale.amount_paid == 140
    assert ledger_balance(pid("P1")) == 18


def test_interstate_uses_igst(uid):
    stocked(uid)
    c = Customer.query.filter_by(full_name="Outstate").first()
    sale, _ = create_sale(uid, [dict(product_id=pid("P2"), quantity=1)], c.customer_id, 0, [dict(method="UPI", amount=35)], "s2")
    assert sale.igst == Decimal("5.40") and sale.cgst == 0 and sale.sgst == 0


def test_discount_allocated_and_total(uid):
    stocked(uid)
    sale, _ = create_sale(uid, [dict(product_id=pid("P1"), quantity=2), dict(product_id=pid("P2"), quantity=1)], None,
                          "13", [dict(method="Cash", amount=500)], "s3")
    assert sum(i.discount for i in sale.items) == Decimal("13.00")
    assert sum(i.taxable_value for i in sale.items) == sale.taxable_value == Decimal("117.00")


def test_negative_stock_blocked_and_rolled_back(uid):
    stocked(uid, 3)
    with pytest.raises(BusinessError):
        create_sale(uid, [dict(product_id=pid("P2"), quantity=1), dict(product_id=pid("P1"), quantity=4)], None, 0, [dict(method="Cash", amount=999)], "s4")
    db.session.rollback()
    assert stock("P1") == 3 and stock("P2") == 3 and Sale.query.count() == 0


def test_duplicate_invoice_submission(uid):
    stocked(uid)
    a, _ = create_sale(uid, [dict(product_id=pid("P1"), quantity=1)], None, 0, [dict(method="Cash", amount=60)], "same")
    b, dup = create_sale(uid, [dict(product_id=pid("P1"), quantity=1)], None, 0, [dict(method="Cash", amount=60)], "same")
    assert dup and a.invoice_no == b.invoice_no and stock("P1") == 19


def test_walkin_cannot_owe(uid):
    stocked(uid)
    with pytest.raises(BusinessError):
        create_sale(uid, [dict(product_id=pid("P1"), quantity=1)], None, 0, [dict(method="Cash", amount=10)], "s5")


def test_cancel_restores_stock_once(uid):
    stocked(uid)
    s, _ = create_sale(uid, [dict(product_id=pid("P1"), quantity=5)], None, 0, [dict(method="Cash", amount=999)], "s6")
    assert stock("P1") == 15
    cancel_sale(uid, s.sale_id)
    assert stock("P1") == 20 and s.status == "Cancelled"
    with pytest.raises(BusinessError):
        cancel_sale(uid, s.sale_id)


def test_returns_resalable_vs_damaged_and_limits(uid):
    stocked(uid)
    s, _ = create_sale(uid, [dict(product_id=pid("P1"), quantity=4)], None, 0, [dict(method="Cash", amount=999)], "s7")
    item = s.items[0]
    r = create_return(uid, s.sale_id, [dict(sale_item_id=item.sale_item_id, quantity=1, condition="Resalable")], "x", "Cash")
    assert stock("P1") == 17 and r.refund_amount == s.items[0].line_total / 4 and s.status == "Partially_Returned"
    create_return(uid, s.sale_id, [dict(sale_item_id=item.sale_item_id, quantity=1, condition="Damaged")], "dmg", "Cash")
    assert stock("P1") == 17  # damaged is not restocked
    assert StockTransaction.query.filter_by(txn_type="Damaged_Return").count() == 1
    with pytest.raises(BusinessError):
        create_return(uid, s.sale_id, [dict(sale_item_id=item.sale_item_id, quantity=3, condition="Resalable")], "x", "Cash")
    db.session.rollback()
    create_return(uid, s.sale_id, [dict(sale_item_id=item.sale_item_id, quantity=2, condition="Resalable")], "x", "Cash")
    assert s.status == "Returned" and ledger_balance(pid("P1")) == stock("P1") == 19


def test_adjustments(uid):
    stocked(uid, 10)
    create_adjustment(uid, "Damaged Goods", [dict(product_id=pid("P1"), quantity=3)], "broken")
    assert stock("P1") == 7
    create_adjustment(uid, "Correction", [dict(product_id=pid("P1"), quantity=-2)], "recount")
    assert stock("P1") == 5
    with pytest.raises(BusinessError):
        create_adjustment(uid, "Stock Decrease", [dict(product_id=pid("P1"), quantity=99)])
    db.session.rollback()
    assert ledger_balance(pid("P1")) == stock("P1") == 5


def test_pos_checkout_endpoint_and_invoice(client, uid):
    stocked(uid)
    login(client, "Cashier")
    body = dict(idempotency_key="web1", items=[dict(product_id=pid("P1"), quantity=2)], payments=[dict(method="Cash", amount=200)])
    r = client.post("/pos/checkout", json=body).get_json()
    assert r["ok"]
    assert client.post("/pos/checkout", json=body).get_json()["duplicate"] is True
    assert stock("P1") == 18
    assert client.get(r["url"]).status_code == 200
    assert client.get(r["url"] + "?fmt=thermal").status_code == 200
    pdf = client.get(r["url"] + "/pdf")
    assert pdf.status_code == 200 and pdf.data[:4] == b"%PDF"
    bad = client.post("/pos/checkout", json=dict(idempotency_key="web2", items=[dict(product_id=pid("P1"), quantity=999)], payments=[])).get_json()
    assert bad["ok"] is False


def test_sync_ledger_for_existing_data(app):
    from app.services.stock import sync_opening_ledger
    Product.query.filter_by(sku="P1").first().stock_quantity = 12
    db.session.commit()
    assert sync_opening_ledger() == 1 and ledger_balance(pid("P1")) == 12
    assert sync_opening_ledger() == 0  # idempotent
