import sys, os, clr

# Ensure DLL path exists once
sys.path.append(r"C:\Program Files (x86)\Sage Evolution")

clr.AddReference("Pastel.Evolution.Common")
clr.AddReference("Pastel.Evolution")
import Pastel.Evolution as Evo
from Core.key_manager import decrypt_password
from Instance.config import COMMON_DB, COMPANY_DB

class EvolutionConnection:
    def __init__(
        self,
        server_common=os.getenv("DB_SERVER_COMMON"),
        server_company=os.getenv("DB_SERVER_COMPANY"),
        common_db=COMMON_DB,
        company_db=COMPANY_DB,
        username_common=os.getenv("DB_USERNAME_COMMON"),
        password_common=decrypt_password(os.getenv("DB_PASSWORD_COMMON")),
        username_company=os.getenv("DB_USERNAME_COMPANY"),
        password_company=decrypt_password(os.getenv("DB_PASSWORD_COMPANY")),
        license_key=os.getenv("DB_LICENCE_KEY"),
        license_serial=os.getenv("DB_LICENCE_SERIAL"),
        trusted=False
    ):
        self.server_common = server_common
        self.server_company = server_company
        self.common_db = common_db
        self.company_db = company_db
        self.username_common = username_common
        self.password_common = password_common
        self.username_company = username_company
        self.password_company = password_company
        self.trusted = trusted
        self.license_key = license_key
        self.license_serial = license_serial

    def __enter__(self):
        Evo.DatabaseContext.CreateCommonDBConnection(
            self.server_common,
            self.common_db,
            self.username_common,
            self.password_common,
            self.trusted
        )

        Evo.DatabaseContext.SetLicense(self.license_key, self.license_serial)

        Evo.DatabaseContext.CreateConnection(
            self.server_company,
            self.company_db,
            self.username_company,
            self.password_company,
            self.trusted
        )
        return self

    def __exit__(self, exc_type, exc, tb):
        try:
            Evo.DatabaseContext.CloseConnection()
        except Exception:
            pass
