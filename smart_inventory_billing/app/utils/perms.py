from functools import wraps
from flask import abort
from flask_login import current_user, login_required

# module -> allowed roles (Admin always allowed)
PERMS = {
    "dashboard": ["Manager", "Cashier", "Inventory_Clerk"],
    "pos": ["Manager", "Cashier"],
    "sales": ["Manager", "Cashier"],
    "returns": ["Manager", "Cashier"],
    "customers": ["Manager", "Cashier"],
    "products": ["Manager", "Inventory_Clerk"],
    "categories": ["Manager", "Inventory_Clerk"],
    "inventory": ["Manager", "Inventory_Clerk"],
    "adjustments": ["Manager", "Inventory_Clerk"],
    "suppliers": ["Manager", "Inventory_Clerk"],
    "purchases": ["Manager", "Inventory_Clerk"],
    "expenses": ["Manager"],
    "reports": ["Manager"],
    "employees": [],
    "settings": [],
    "audit": [],
}

NAV = [
    ("Dashboard", "dashboard.index", "dashboard", "bi-speedometer2"),
    ("POS / Billing", "pos.index", "pos", "bi-receipt"),
    ("Products", "crud.list_view", "products", "bi-box-seam"),
    ("Categories", "crud.list_view", "categories", "bi-tags"),
    ("Inventory", "inventory.ledger", "inventory", "bi-boxes"),
    ("Stock Adjustments", "inventory.adjustments", "adjustments", "bi-sliders"),
    ("Suppliers", "crud.list_view", "suppliers", "bi-truck"),
    ("Purchases", "purchases.list_view", "purchases", "bi-bag-plus"),
    ("Customers", "crud.list_view", "customers", "bi-people"),
    ("Sales", "sales.list_view", "sales", "bi-cash-stack"),
    ("Returns", "sales.returns_list", "returns", "bi-arrow-return-left"),
    ("Expenses", "crud.list_view", "expenses", "bi-wallet2"),
    ("Employees", "crud.list_view", "employees", "bi-person-badge"),
    ("Reports", "reports.index", "reports", "bi-graph-up"),
    ("Settings", "settings.index", "settings", "bi-gear"),
]


def can(module):
    if not current_user.is_authenticated:
        return False
    return current_user.role == "Admin" or current_user.role in PERMS.get(module, [])


def permission_required(module):
    def deco(fn):
        @wraps(fn)
        @login_required
        def wrapper(*a, **kw):
            if not can(module):
                abort(403)
            return fn(*a, **kw)
        return wrapper
    return deco
