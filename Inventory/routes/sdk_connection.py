import sys, os, clr

# Ensure DLL path exists once
sys.path.append(r"C:\Program Files (x86)\Sage Evolution")

clr.AddReference("Pastel.Evolution.Common")
clr.AddReference("Pastel.Evolution")
import Pastel.Evolution as Evo
from Core.key_manager import decrypt_password

class EvolutionConnection:
    def __init__(
        self,
        server="SIGMAFIN-RDS\\EVOLUTION",
        common_db="SageCommon",
        company_db="UB_UITDRAAI_BDY",
        username=os.getenv("DB_USERNAME"),
        password=decrypt_password(os.getenv("DB_PASSWORD")),
        license_key=os.getenv("DB_LICENCE_KEY"),
        license_serial=os.getenv("DB_LICENCE_SERIAL"),
        trusted=False
    ):
        self.server = server
        self.common_db = common_db
        self.company_db = company_db
        self.username = username
        self.password = password
        self.trusted = trusted
        self.license_key = license_key
        self.license_serial = license_serial

    def __enter__(self):
        Evo.DatabaseContext.CreateCommonDBConnection(
            self.server,
            self.common_db,
            self.username,
            self.password,
            self.trusted
        )

        Evo.DatabaseContext.SetLicense(self.license_key, self.license_serial)

        Evo.DatabaseContext.CreateConnection(
            self.server,
            self.company_db,
            self.username,
            self.password,
            self.trusted
        )
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            Evo.DatabaseContext.CloseConnection()
        except Exception:
            pass
