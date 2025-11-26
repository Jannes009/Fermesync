# config.py

COMMON_DB_CONFIG = {
    "driver": "SQL Server",
    "server": r"SIGMAFIN-RDS\EVOLUTION",
    "database": "UB_FERMESYNC_COMMON",
    "uid": "sa",
    "pwd": "@Evolution",
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
