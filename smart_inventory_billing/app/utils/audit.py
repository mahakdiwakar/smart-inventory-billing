from flask_login import current_user
from .. import db
from ..models import AuditLog


def audit(action, entity=None, entity_id=None, details=None):
    uid = current_user.user_id if current_user and current_user.is_authenticated else None
    db.session.add(AuditLog(user_id=uid, action=action, entity=entity,
                            entity_id=str(entity_id) if entity_id is not None else None,
                            details=(details or "")[:255]))
