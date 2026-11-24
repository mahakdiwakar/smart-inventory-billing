from .. import db
from ..models import StoreSetting

DEFAULTS = {
    "store_name": "Smart Retail Store", "store_address": "Mumbai, Maharashtra", "store_phone": "",
    "store_email": "", "store_gstin": "27ABCDE1234F1Z5", "store_state": "Maharashtra",
    "invoice_prefix": "INV-", "currency": "INR", "invoice_footer": "Thank you for shopping with us!",
    "loyalty_rate": "100",  # 1 point per ₹100
}


def get_settings():
    s = dict(DEFAULTS)
    try:
        for r in StoreSetting.query.all():
            s[r.setting_key] = r.setting_value
    except Exception:
        db.session.rollback()
    return s


def save_settings(data):
    for k, v in data.items():
        if k in DEFAULTS:
            row = db.session.get(StoreSetting, k)
            if row:
                row.setting_value = v
            else:
                db.session.add(StoreSetting(setting_key=k, setting_value=v))
