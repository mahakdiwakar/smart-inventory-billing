"""Idempotent demo data: runs only if there are no sales/purchases yet. Uses the real services, so the ledger stays correct.
Usage:  python database/seed_demo_data.py"""
import os, sys, random
from datetime import date, timedelta
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import create_app, db
from app.models import Product, Supplier, Customer, Sale, Purchase, Expense, User
from app.services.purchases import create_purchase
from app.services.sales import create_sale
from app.services.stock import sync_opening_ledger, BusinessError

random.seed(7)
app = create_app()
with app.app_context():
    db.create_all()
    admin = User.query.filter_by(role="Admin").first()
    if not admin:
        sys.exit("Run `flask seed-admin` first.")
    if Sale.query.count() or Purchase.query.count():
        sys.exit("Transactional data already exists - nothing changed.")
    sync_opening_ledger()
    products, suppliers, customers = Product.query.all(), Supplier.query.all(), Customer.query.all()
    if not (products and suppliers and customers):
        sys.exit("Load the 105 master records first (see README step 7).")
    for i in range(8):
        picks = random.sample(products, 6)
        pur, _ = create_purchase(admin.user_id, random.choice(suppliers).supplier_id,
                                 [dict(product_id=p.product_id, quantity=random.randint(20, 60), unit_cost=p.cost_price) for p in picks],
                                 date.today() - timedelta(days=random.randint(5, 80)), f"DEMO-{i+1}", f"demo-pur-{i}")
    made = 0
    for i in range(40):
        picks = random.sample(products, random.randint(1, 4))
        cust = random.choice(customers + [None] * 10)
        try:
            create_sale(admin.user_id, [dict(product_id=p.product_id, quantity=random.randint(1, 3)) for p in picks],
                        cust.customer_id if cust else None, random.choice([0, 0, 10, 25]), [dict(method=random.choice(["Cash", "UPI", "Card"]), amount=100000)], f"demo-sale-{i}")
            made += 1
        except BusinessError:
            db.session.rollback()
    for cat, amt in (("Rent", 25000), ("Electricity", 4200), ("Packaging", 1800), ("Transport", 2600)):
        db.session.add(Expense(category=cat, amount=amt, expense_date=date.today() - timedelta(days=random.randint(0, 30)), payment_method="Bank_Transfer", description="Demo expense"))
    db.session.commit()
    print(f"Demo data added: 8 purchases, {made} sales, 4 expenses.")
