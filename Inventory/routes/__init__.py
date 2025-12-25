# inventory/__init__.py
import os
from flask import Blueprint, render_template

inventory_bp = Blueprint(
    'inventory',
    __name__,
    template_folder='../templates',
    static_folder='../static'
)

# Your existing imports
from . import GRV
from . import IBT
from . import stock_count
from . import stock_issue
from . import Barcode
from . import notifications
from . import offline
from . import stock_adjustment
from flask_login import login_required

@inventory_bp.route('/dashboard', methods=['GET'])
@login_required
def dashboard():
    return render_template('inventory_dashboard.html')