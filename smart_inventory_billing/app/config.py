import os
from pathlib import Path
from urllib.parse import quote_plus
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent


def _db_uri():
    db_url = os.getenv("DATABASE_URL")
    if db_url:
        if db_url.startswith("mysql://"):
            db_url = db_url.replace("mysql://", "mysql+pymysql://", 1)
        return db_url

    u = os.getenv("DB_USER", "root")
    p = quote_plus(os.getenv("DB_PASSWORD", ""))
    h = os.getenv("DB_HOST", "127.0.0.1")
    port = os.getenv("DB_PORT", "3306")
    n = os.getenv("DB_NAME", "smart_inventory_billing")

    return (
        f"mysql+pymysql://{u}:{p}@{h}:{port}/{n}"
        "?charset=utf8mb4"
    )


def _get_ssl_ca():
    # 1. Custom env var if specified
    custom_ca = os.getenv("DB_SSL_CA")
    if custom_ca and os.path.exists(custom_ca):
        return custom_ca

    # 2. Local bundled isrgrootx1.pem (in app base dir or repo root)
    local_pem = BASE_DIR / "isrgrootx1.pem"
    if local_pem.exists():
        return str(local_pem)
    parent_pem = BASE_DIR.parent / "isrgrootx1.pem"
    if parent_pem.exists():
        return str(parent_pem)

    # 3. System Linux cert bundle (Render / Debian / Ubuntu standard path)
    system_ca = "/etc/ssl/certs/ca-certificates.crt"
    if os.path.exists(system_ca):
        return system_ca

    # 4. certifi if installed
    try:
        import certifi
        return certifi.where()
    except Exception:
        pass

    return None


def _get_engine_options():
    options = {"pool_pre_ping": True}

    ssl_req = os.getenv("DB_SSL_REQUIRED", "").strip().lower()
    host = os.getenv("DB_HOST", "")
    db_url = os.getenv("DATABASE_URL", "")

    # Auto-detect remote TiDB / Cloud MySQL or explicit SSL flag
    is_cloud_or_remote = (
        ssl_req in ("true", "1", "yes")
        or "tidbcloud.com" in host
        or "tidbcloud.com" in db_url
        or (host and host not in ("127.0.0.1", "localhost", "::1"))
    )

    if is_cloud_or_remote and ssl_req not in ("false", "0", "no"):
        ca_path = _get_ssl_ca()
        if ca_path:
            options["connect_args"] = {"ssl": {"ca": ca_path}}
        else:
            options["connect_args"] = {"ssl": {}}

    return options


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-change-me")

    SQLALCHEMY_DATABASE_URI = _db_uri()
    SQLALCHEMY_ENGINE_OPTIONS = _get_engine_options()

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.getenv("FLASK_ENV") == "production" or os.getenv("RENDER") == "true"
    PERMANENT_SESSION_LIFETIME = 60 * 60 * 8
    WTF_CSRF_TIME_LIMIT = None
    PER_PAGE = 15
