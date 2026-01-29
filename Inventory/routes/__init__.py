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
from .OrderEntry import edit_po
from .OrderEntry import PurchaseOrder
from .OrderEntry import PO_summary
from .OrderEntry import PO_requisition
from .OrderEntry import pdf_generator
from . import IBT
from .stock_count import stock_count
from .stock_count import stock_count_summary
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