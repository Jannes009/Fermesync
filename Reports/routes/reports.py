from flask import abort, render_template
from flask_login import current_user, login_required

from . import report_bp


REPORT_PERMISSION_CODES = {"REPORTS_VIEW", "REPORT_VIEW", "CHEMICAL_ANALYSIS_VIEW"}


def can_view_reports():
    return bool(REPORT_PERMISSION_CODES.intersection(current_user.permissions or []))


@report_bp.route("/", methods=["GET"])
@login_required
def reports_index():
    if not can_view_reports():
        abort(403)
    return render_template("reports/reports_index.html")
