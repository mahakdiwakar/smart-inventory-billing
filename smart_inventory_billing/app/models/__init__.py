from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from .. import db

D = lambda: db.Numeric(12, 2)
ROLES = ("Admin", "Manager", "Cashier", "Inventory_Clerk")


# ---------- Existing master tables (Phase 3 Part 1): mapped, never altered ----------
class Category(db.Model):
    __tablename__ = "Categories"
    category_id = db.Column(db.Integer, primary_key=True)
    category_name = db.Column(db.String(100), nullable=False, unique=True)
    hsn_default_prefix = db.Column(db.String(8))
    description = db.Column(db.String(255))
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Supplier(db.Model):
    __tablename__ = "Suppliers"
    supplier_id = db.Column(db.Integer, primary_key=True)
    supplier_name = db.Column(db.String(150), nullable=False)
    contact_person = db.Column(db.String(100))
    phone = db.Column(db.String(15), nullable=False, unique=True)
    email = db.Column(db.String(120), unique=True)
    gstin = db.Column(db.String(15), nullable=False, unique=True)
    address = db.Column(db.Text)
    city = db.Column(db.String(80), nullable=False)
    state = db.Column(db.String(80), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Customer(db.Model):
    __tablename__ = "Customers"
    customer_id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(15), nullable=False, unique=True)
    email = db.Column(db.String(120), unique=True)
    gstin = db.Column(db.String(15))
    address = db.Column(db.Text)
    city = db.Column(db.String(80), default="Mumbai")
    state = db.Column(db.String(80), default="Maharashtra")
    loyalty_points = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Employee(db.Model):
    __tablename__ = "Employees"
    employee_id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(120), nullable=False)
    role = db.Column(db.Enum(*ROLES))
    phone = db.Column(db.String(15), unique=True)
    email = db.Column(db.String(120), unique=True)
    salary = db.Column(D())
    hire_date = db.Column(db.Date)
    is_active = db.Column(db.Boolean, default=True)


class Product(db.Model):
    __tablename__ = "Products"
    product_id = db.Column(db.Integer, primary_key=True)
    sku = db.Column(db.String(30), nullable=False, unique=True)
    hsn_code = db.Column(db.String(8), nullable=False)
    product_name = db.Column(db.String(150), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey("Categories.category_id"), nullable=False)
    unit_of_measure = db.Column(db.Enum("PCS", "KG", "GM", "LTR", "ML", "BOX", "PACK"))
    cost_price = db.Column(D())
    selling_price = db.Column(D())
    gst_rate = db.Column(db.Numeric(5, 2))
    stock_quantity = db.Column(db.Integer, default=0)
    reorder_level = db.Column(db.Integer, default=10)
    is_active = db.Column(db.Boolean, default=True)
    category = db.relationship("Category")

    @property
    def stock_status(self):
        if (self.stock_quantity or 0) <= 0:
            return "Out of stock"
        return "Low stock" if self.stock_quantity <= (self.reorder_level or 0) else "In stock"


# ---------- New tables ----------
class User(UserMixin, db.Model):
    __tablename__ = "Users"
    user_id = db.Column(db.Integer, primary_key=True)
    employee_id = db.Column(db.Integer, db.ForeignKey("Employees.employee_id"))
    full_name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), nullable=False, unique=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.Enum(*ROLES), nullable=False, default="Cashier")
    is_active_user = db.Column(db.Boolean, default=True)
    last_login = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def get_id(self):
        return str(self.user_id)

    @property
    def is_active(self):
        return bool(self.is_active_user)

    def set_password(self, pw):
        self.password_hash = generate_password_hash(pw)

    def check_password(self, pw):
        return check_password_hash(self.password_hash, pw)


class StockTransaction(db.Model):
    __tablename__ = "Stock_Transactions"
    txn_id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("Products.product_id"), nullable=False, index=True)
    txn_type = db.Column(db.String(30), nullable=False)
    ref_type = db.Column(db.String(30))
    ref_no = db.Column(db.String(40), index=True)
    qty_in = db.Column(db.Integer, nullable=False, default=0)
    qty_out = db.Column(db.Integer, nullable=False, default=0)
    balance = db.Column(db.Integer, nullable=False)
    remarks = db.Column(db.String(255))
    created_by = db.Column(db.Integer, db.ForeignKey("Users.user_id"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    product = db.relationship("Product")


class StockAdjustment(db.Model):
    __tablename__ = "Stock_Adjustments"
    adjustment_id = db.Column(db.Integer, primary_key=True)
    adjustment_no = db.Column(db.String(30), unique=True, nullable=False)
    adjustment_type = db.Column(db.String(30), nullable=False)
    remarks = db.Column(db.String(255))
    created_by = db.Column(db.Integer, db.ForeignKey("Users.user_id"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    items = db.relationship("StockAdjustmentItem", backref="adjustment", cascade="all, delete-orphan")


class StockAdjustmentItem(db.Model):
    __tablename__ = "Stock_Adjustment_Items"
    item_id = db.Column(db.Integer, primary_key=True)
    adjustment_id = db.Column(db.Integer, db.ForeignKey("Stock_Adjustments.adjustment_id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("Products.product_id"), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)  # signed effect on stock
    product = db.relationship("Product")


class Purchase(db.Model):
    __tablename__ = "Purchases"
    purchase_id = db.Column(db.Integer, primary_key=True)
    purchase_no = db.Column(db.String(30), unique=True, nullable=False)
    supplier_invoice_no = db.Column(db.String(50))
    supplier_id = db.Column(db.Integer, db.ForeignKey("Suppliers.supplier_id"), nullable=False)
    purchase_date = db.Column(db.Date, nullable=False)
    subtotal = db.Column(D(), nullable=False)
    gst_amount = db.Column(D(), nullable=False)
    total = db.Column(D(), nullable=False)
    status = db.Column(db.Enum("Draft", "Completed", "Cancelled"), default="Completed")
    idempotency_key = db.Column(db.String(64), unique=True)
    created_by = db.Column(db.Integer, db.ForeignKey("Users.user_id"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    supplier = db.relationship("Supplier")
    items = db.relationship("PurchaseItem", backref="purchase", cascade="all, delete-orphan")


class PurchaseItem(db.Model):
    __tablename__ = "Purchase_Items"
    item_id = db.Column(db.Integer, primary_key=True)
    purchase_id = db.Column(db.Integer, db.ForeignKey("Purchases.purchase_id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("Products.product_id"), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    unit_cost = db.Column(D(), nullable=False)
    gst_rate = db.Column(db.Numeric(5, 2), nullable=False)
    gst_amount = db.Column(D(), nullable=False)
    line_total = db.Column(D(), nullable=False)
    product = db.relationship("Product")


class Sale(db.Model):
    __tablename__ = "Sales"
    sale_id = db.Column(db.Integer, primary_key=True)
    invoice_no = db.Column(db.String(30), unique=True, nullable=False)
    idempotency_key = db.Column(db.String(64), unique=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("Customers.customer_id"))
    sale_date = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    subtotal = db.Column(D(), nullable=False)        # taxable value before discount
    discount = db.Column(D(), nullable=False, default=0)
    taxable_value = db.Column(D(), nullable=False)   # after discount
    cgst = db.Column(D(), nullable=False, default=0)
    sgst = db.Column(D(), nullable=False, default=0)
    igst = db.Column(D(), nullable=False, default=0)
    gst_amount = db.Column(D(), nullable=False, default=0)
    round_off = db.Column(D(), nullable=False, default=0)
    total = db.Column(D(), nullable=False)
    amount_paid = db.Column(D(), nullable=False, default=0)
    balance_due = db.Column(D(), nullable=False, default=0)
    status = db.Column(db.Enum("Draft", "Completed", "Cancelled", "Partially_Returned", "Returned"), default="Completed")
    created_by = db.Column(db.Integer, db.ForeignKey("Users.user_id"))
    customer = db.relationship("Customer")
    items = db.relationship("SaleItem", backref="sale", cascade="all, delete-orphan")
    payments = db.relationship("SalePayment", backref="sale", cascade="all, delete-orphan")
    cashier = db.relationship("User")


class SaleItem(db.Model):
    __tablename__ = "Sale_Items"
    sale_item_id = db.Column(db.Integer, primary_key=True)
    sale_id = db.Column(db.Integer, db.ForeignKey("Sales.sale_id"), nullable=False, index=True)
    product_id = db.Column(db.Integer, db.ForeignKey("Products.product_id"), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    unit_price = db.Column(D(), nullable=False)
    cost_price = db.Column(D(), nullable=False)  # snapshot used for profit
    discount = db.Column(D(), nullable=False, default=0)
    taxable_value = db.Column(D(), nullable=False)
    gst_rate = db.Column(db.Numeric(5, 2), nullable=False)
    gst_amount = db.Column(D(), nullable=False)
    line_total = db.Column(D(), nullable=False)
    returned_qty = db.Column(db.Integer, nullable=False, default=0)
    product = db.relationship("Product")


class SalePayment(db.Model):
    __tablename__ = "Sale_Payments"
    payment_id = db.Column(db.Integer, primary_key=True)
    sale_id = db.Column(db.Integer, db.ForeignKey("Sales.sale_id"), nullable=False)
    method = db.Column(db.Enum("Cash", "UPI", "Card", "Bank_Transfer"), nullable=False)
    amount = db.Column(D(), nullable=False)
    reference = db.Column(db.String(60))
    paid_at = db.Column(db.DateTime, default=datetime.utcnow)


class Return(db.Model):
    __tablename__ = "Returns"
    return_id = db.Column(db.Integer, primary_key=True)
    return_no = db.Column(db.String(30), unique=True, nullable=False)
    sale_id = db.Column(db.Integer, db.ForeignKey("Sales.sale_id"), nullable=False)
    reason = db.Column(db.String(255))
    refund_method = db.Column(db.Enum("Cash", "UPI", "Card", "Bank_Transfer", "Store_Credit"), nullable=False)
    refund_amount = db.Column(D(), nullable=False)
    status = db.Column(db.Enum("Pending", "Approved", "Rejected"), default="Approved")
    created_by = db.Column(db.Integer, db.ForeignKey("Users.user_id"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    sale = db.relationship("Sale")
    items = db.relationship("ReturnItem", backref="ret", cascade="all, delete-orphan")


class ReturnItem(db.Model):
    __tablename__ = "Return_Items"
    return_item_id = db.Column(db.Integer, primary_key=True)
    return_id = db.Column(db.Integer, db.ForeignKey("Returns.return_id"), nullable=False)
    sale_item_id = db.Column(db.Integer, db.ForeignKey("Sale_Items.sale_item_id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("Products.product_id"), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    item_condition = db.Column(db.Enum("Resalable", "Damaged"), nullable=False)
    refund_amount = db.Column(D(), nullable=False)
    taxable_refunded = db.Column(D(), nullable=False, default=0)
    gst_refunded = db.Column(D(), nullable=False, default=0)
    cost_value = db.Column(D(), nullable=False, default=0)
    product = db.relationship("Product")


class Expense(db.Model):
    __tablename__ = "Expenses"
    expense_id = db.Column(db.Integer, primary_key=True)
    category = db.Column(db.String(60), nullable=False)
    amount = db.Column(D(), nullable=False)
    expense_date = db.Column(db.Date, nullable=False)
    payment_method = db.Column(db.Enum("Cash", "UPI", "Card", "Bank_Transfer"), default="Cash")
    description = db.Column(db.String(255))
    created_by = db.Column(db.Integer, db.ForeignKey("Users.user_id"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Notification(db.Model):
    __tablename__ = "Notifications"
    notification_id = db.Column(db.Integer, primary_key=True)
    message = db.Column(db.String(255), nullable=False)
    level = db.Column(db.String(10), default="info")
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class AuditLog(db.Model):
    __tablename__ = "Audit_Logs"
    log_id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("Users.user_id"))
    action = db.Column(db.String(40), nullable=False)
    entity = db.Column(db.String(40))
    entity_id = db.Column(db.String(40))
    details = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    user = db.relationship("User")


class StoreSetting(db.Model):
    __tablename__ = "Store_Settings"
    setting_key = db.Column(db.String(50), primary_key=True)
    setting_value = db.Column(db.String(500))
