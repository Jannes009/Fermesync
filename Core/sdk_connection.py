import sys
import clr

from flask_login import current_user

# Ensure DLL path exists once
sys.path.append(r"C:\Program Files (x86)\Sage Evolution")

clr.AddReference("Pastel.Evolution.Common")
clr.AddReference("Pastel.Evolution")
import Pastel.Evolution as Evo
from Core.key_manager import decrypt_password
from Instance.local_settings import ( DB_SERVER_COMMON, DB_SERVER_COMPANY, COMMON_DB, COMPANY_DB, DB_USERNAME_COMMON,
                                        DB_PASSWORD_COMMON, DB_USERNAME_COMPANY, DB_PASSWORD_COMPANY, 
                                        DB_LICENCE_KEY, DB_LICENCE_SERIAL )
class EvolutionConnection:
    def __init__(
        self,
        server_common=DB_SERVER_COMMON,
        server_company=DB_SERVER_COMPANY,
        common_db=COMMON_DB,
        company_db=COMPANY_DB,
        username_common=DB_USERNAME_COMMON,
        password_common=decrypt_password(DB_PASSWORD_COMMON),
        username_company=DB_USERNAME_COMPANY,
        password_company=decrypt_password(DB_PASSWORD_COMPANY),
        license_key=DB_LICENCE_KEY,
        license_serial=DB_LICENCE_SERIAL,
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
        try:
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

            agent_name = getattr(current_user, 'username', None)
            Evo.DatabaseContext.CurrentAgent = Evo.Agent(agent_name)
            return self
        except Exception as ex:
            # Provide a clear, reusable exception for missing Evolution agent
            msg = str(ex) or "Unknown Evolution error"
            # Detect the Agent not found case and raise a specific error
            if 'Agent' in msg and 'not found' in msg:
                raise EvolutionAgentNotFoundError(
                    "Error: this user can't create transactions in Evolution because the user isn't set up in Evolution."
                )
            # For any other Evolution-related error, raise a generic connection error
            raise EvolutionConnectionError(f"Evolution connection error: {msg}")


class EvolutionAgentNotFoundError(Exception):
    """Raised when the current user is not configured as an agent in Evolution."""
    pass


class EvolutionConnectionError(Exception):
    """Raised for other Evolution connection or SDK errors."""
    pass

    def __exit__(self, exc_type, exc, tb):
        try:
            Evo.DatabaseContext.CloseConnection()
        except Exception:
            pass
