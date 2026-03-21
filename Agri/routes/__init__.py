# Agri/__init__.py
import os
from flask import Blueprint, render_template

agri_bp = Blueprint(
    'agri',
    __name__,
    template_folder='../templates',
    static_folder='../static'
)

from . import spray_recommendation
from . import setup
from . import spray_instruction
from . import spray_stock_issue
from . import pdf_generator
from flask_login import login_required
