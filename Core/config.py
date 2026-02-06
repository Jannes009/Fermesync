# config.py
import os
from datetime import timedelta

COMMON_DB_CONFIG = {
    "driver": "SQL Server",
    "server": r"SIGMAFIN-RDS\EVOLUTION",
    "database": "UB_FERMESYNC_COMMON",
    "uid": os.getenv("DB_USERNAME"),
    "pwd": os.getenv("DB_PASSWORD"),
    "trust_connection": "no"
}

def build_connection_string(cfg=None):
    cfg = cfg or COMMON_DB_CONFIG
    return (
        f"DRIVER={{{cfg['driver']}}};"
        f"SERVER={cfg['server']};"
        f"DATABASE={cfg['database']};"
        f"UID={cfg['uid']};"
        f"PWD={cfg['pwd']};"
        f"Trust_Connection={cfg['trust_connection']};"
    )

class BaseConfig:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-unsafe-key")

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = False
    PERMANENT_SESSION_LIFETIME = timedelta(days=30)

    # Push / VAPID
    VAPID_PUBLIC_KEY = os.getenv("VAPID_PUBLIC_KEY")
    VAPID_PRIVATE_KEY = os.getenv("VAPID_PRIVATE_KEY")
    VAPID_CLAIMS = {
        "sub": os.getenv("VAPID_SUBJECT", "mailto:jannes.fermsync@gmail.com")
    }


class DevelopmentConfig(BaseConfig):
    DEBUG = True
    TESTING = False


class TestingConfig(BaseConfig):
    DEBUG = False
    TESTING = True


class ProductionConfig(BaseConfig):
    DEBUG = False
    TESTING = False
    SESSION_COOKIE_SECURE = True
