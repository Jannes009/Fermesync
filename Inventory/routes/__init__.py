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
from .import purchase_order
from . import IBT
from .stock_count import stock_count
from .stock_count import stock_count_summary
from .stock_issue import stock_issue_summary
from .stock_issue import create_stock_issue
from . import Barcode
from . import offline
from . import stock_adjustment
from . import warehouse_transfer
from . import qty
from . import product_detail
from . import edit_product
from flask_login import login_required

@inventory_bp.route('/dashboard', methods=['GET'])
@login_required
def dashboard():
    return render_template('inventory_dashboard.html')