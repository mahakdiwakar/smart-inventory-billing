import os
from urllib.parse import quote_plus
from dotenv import load_dotenv

load_dotenv()


def _db_uri():
    if os.getenv("DATABASE_URL"):
        return os.getenv("DATABASE_URL")
    u, p = os.getenv("DB_USER", "root"), quote_plus(os.getenv("DB_PASSWORD", ""))
    h, port = os.getenv("DB_HOST", "127.0.0.1"), os.getenv("DB_PORT", "3306")
    n = os.getenv("DB_NAME", "smart_inventory_billing")
    return f"mysql+pymysql://{u}:{p}@{h}:{port}/{n}?charset=utf8mb4"


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-change-me")
    SQLALCHEMY_DATABASE_URI = _db_uri()
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    PERMANENT_SESSION_LIFETIME = 60 * 60 * 8
    WTF_CSRF_TIME_LIMIT = None
    PER_PAGE = 15
