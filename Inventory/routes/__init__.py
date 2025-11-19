from flask import Blueprint

inventory_bp = Blueprint(
    'inventory',
    __name__,
    template_folder='../templates',
    static_folder='../static'
)

from . import EvolutionSDK
from . import IBT
from . import stock_count
from . import stock_issue
from . import Barcode