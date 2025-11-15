from flask import Blueprint

market_bp = Blueprint(
    'market',
    __name__,
    template_folder='../templates',  # relative to this file
    static_folder='../static'
)

# Import your routes here so they are registered with the blueprint
from . import entry, view, report, dashboard, BOM
from .Invoices import invoices  # noqa: F401
from .Maintanance import maintanance  # noqa: F401
from .Import import Import  # noqa: F401
from .Bill_Of_Lading import view_entry  # noqa: F401