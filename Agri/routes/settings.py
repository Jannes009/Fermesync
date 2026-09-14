from flask import render_template
from flask_login import login_required

from . import agri_bp


@agri_bp.route("/settings", methods=["GET"])
@login_required
def settings():
    return render_template("agri_settings.html")