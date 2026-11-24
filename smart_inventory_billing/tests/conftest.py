import pytest
from sqlalchemy.pool import StaticPool
from app import create_app, db
from app.config import Config
from app.models import User, Category, Product, Supplier, Customer


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite://"
    SQLALCHEMY_ENGINE_OPTIONS = {"poolclass": StaticPool, "connect_args": {"check_same_thread": False}}
    WTF_CSRF_ENABLED = False
    SECRET_KEY = "test"


@pytest.fixture
def app():
    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()
        c = Category(category_name="Grocery", hsn_default_prefix="GRO")
        db.session.add(c); db.session.flush()
        db.session.add_all([
            Product(sku="P1", hsn_code="1001", product_name="Rice 1kg", category_id=c.category_id, unit_of_measure="KG",
                    cost_price=40, selling_price=50, gst_rate=5, stock_quantity=0, reorder_level=5),
            Product(sku="P2", hsn_code="1002", product_name="Soap", category_id=c.category_id, unit_of_measure="PCS",
                    cost_price=20, selling_price=30, gst_rate=18, stock_quantity=0, reorder_level=5),
            Supplier(supplier_name="Sup", phone="9999999990", gstin="27AAAAA0000A1Z5", city="Pune", state="Maharashtra"),
            Customer(full_name="Local", phone="9000000001", state="Maharashtra"),
            Customer(full_name="Outstate", phone="9000000002", state="Gujarat"),
        ])
        for role in ("Admin", "Manager", "Cashier", "Inventory_Clerk"):
            u = User(full_name=role, email=f"{role.lower()}@t.com", role=role); u.set_password("pass1234"); db.session.add(u)
        db.session.commit()
        yield app


@pytest.fixture
def client(app):
    return app.test_client()


def login(client, role="Admin"):
    return client.post("/login", data={"email": f"{role.lower()}@t.com", "password": "pass1234"}, follow_redirects=True)


@pytest.fixture
def uid(app):
    return User.query.filter_by(role="Admin").first().user_id
