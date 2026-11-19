# Reports/__init__.py
import os
from flask import Blueprint, render_template

report_bp = Blueprint(
    'reports',
    __name__,
    template_folder='../templates',
    static_folder='../static'
)

from . import reports
from . import chemical_analysis


