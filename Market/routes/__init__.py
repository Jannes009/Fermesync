from flask import Blueprint, abort, redirect, url_for, render_template
from flask_login import current_user, login_required

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

@market_bp.route("/dashboard")
@login_required
def market_dashboard():
    if not current_user.has_feature("MARKET"):
        abort(403)
    return render_template('Home Page/index.html')
