import json
import threading
from datetime import date, datetime, timedelta
from decimal import Decimal
from io import BytesIO
from types import SimpleNamespace
from urllib.parse import parse_qsl, urlencode

from flask import abort, current_app, jsonify, render_template, request, send_file, url_for
from flask_login import current_user, login_required
from openpyxl import Workbook
from openpyxl.styles import Font
from openpyxl.utils import get_column_letter
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright
from werkzeug.datastructures import MultiDict
from werkzeug.serving import make_server

from Core.auth import close_db_connection, create_db_connection
from . import report_bp


PERMISSION_CODES = {"REPORTS_VIEW", "REPORT_VIEW", "CHEMICAL_ANALYSIS_VIEW"}
ALL_ACCESS_CODES = {"REPORTS_ALL", "MANAGE_USERS"}

GROUP_COLUMNS = {
    "farm": "C.FarmName",
    "project": "P.ProjectName",
    "crop": "C.CropDescription",
    "variety": "C.VarietyDescription",
    "group": "C.GroupDescription",
    "product_type": "C.StkCrpType",
    "product": "COALESCE(C.ProductDescription, CONCAT('Stock ', C.AccountLink))",
    "active_ingredient": "COALESCE(C.ChemActIngredient, 'Not specified')",
}

GROUP_KEY_COLUMNS = {
    "farm": "COALESCE(C.FarmName, 'Not specified')",
    "project": "COALESCE(C.Project, -1)",
    "crop": "COALESCE(C.ProjAttrCropId, -1)",
    "variety": "COALESCE(C.VarietyDescription, 'Not specified')",
    "group": "COALESCE(C.GroupDescription, 'Not specified')",
    "product_type": "COALESCE(C.StkCrpType, 'Not specified')",
    "product": "COALESCE(C.AccountLink, -1)",
    "active_ingredient": "COALESCE(C.ChemActIngredient, 'Not specified')",
}
PLANT_WEEK_EXPRESSION = """
    CASE WHEN C.TxDate >= C.SprayPPlantDate
         THEN DATEDIFF(day, C.SprayPPlantDate, C.TxDate) / 7 + 1
         ELSE -((DATEDIFF(day, C.TxDate, C.SprayPPlantDate) + 6) / 7)
    END
"""

DRILLDOWN_GROUP_COLUMNS = {
    **GROUP_KEY_COLUMNS,
}

NUMERIC_GROUPS = {"project", "crop", "product"}
MAX_DOCUMENT_RECORDS = 50000


def _can_view():
    permissions = set(current_user.permissions or [])
    return bool(PERMISSION_CODES.intersection(permissions))


def _require_view():
    if not current_user.is_authenticated:
        abort(403)
    if not _can_view():
        abort(403)


def _multi_value(request_object, name):
    values = []
    for value in request_object.args.getlist(name):
        values.extend(part for part in value.split(",") if part)
    return list(dict.fromkeys(value for value in values if value not in ("", "null")))


def _safe_int_values(values):
    output = []
    for value in values:
        try:
            number = int(value)
        except (TypeError, ValueError):
            continue
        if number not in output:
            output.append(number)
    return output


def _parse_iso_date(value):
    if not value:
        return None
    try:
        parsed = date.fromisoformat(str(value))
        return parsed
    except ValueError:
        return None


def _period_bounds(value, interval):
    try:
        if interval == "daily":
            start = date.fromisoformat(value)
            if start.isoformat() != value:
                return None
            return start, start + timedelta(days=1)
        if interval == "monthly":
            start = datetime.strptime(value, "%Y-%m").date().replace(day=1)
            if start.strftime("%Y-%m") != value:
                return None
            end = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
            return start, end
        if interval == "weekly":
            year, week = value.split("-W") if "-W" in value else value.split("-")
            if len(year) != 4 or len(week) != 2:
                return None
            start = date.fromisocalendar(int(year), int(week), 1)
            if f"{start.isocalendar()[0]}-{start.isocalendar()[1]:02d}" != value:
                return None
            return start, start + timedelta(days=7)
    except (TypeError, ValueError):
        return None
    return None


def _json_safe(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def _get_filters(request_object):
    start_date = _parse_iso_date(request_object.args.get("start_date"))
    end_date = _parse_iso_date(request_object.args.get("end_date"))
    raw_project = _multi_value(request_object, "project")
    return {
        "start_date": start_date,
        "end_date": end_date,
        "farm": _multi_value(request_object, "farm"),
        "project": _safe_int_values(raw_project),
        "crop": _safe_int_values(_multi_value(request_object, "crop")),
        "variety": _multi_value(request_object, "variety"),
        "group": _multi_value(request_object, "group"),
        "product_type": _multi_value(request_object, "product_type"),
        "product": _safe_int_values(_multi_value(request_object, "product")),
    }


def _build_filter_sql(filters, include_date=True):
    clauses = []
    params = []

    permissions = set(current_user.permissions or [])
    if not ALL_ACCESS_CODES.intersection(permissions):
        project_links = _safe_int_values(getattr(current_user, "projects", []) or [])
        if not project_links:
            clauses.append("1 = 0")
        else:
            placeholders = ",".join("?" for _ in project_links)
            clauses.append(f"P.MainProjectLink IN ({placeholders})")
            params.extend(project_links)

    if include_date and filters["start_date"]:
        clauses.append("C.TxDate >= CONVERT(date, ?, 23)")
        params.append(filters["start_date"].isoformat())
    if include_date and filters["end_date"]:
        clauses.append("C.TxDate < DATEADD(day, 1, CONVERT(date, ?, 23))")
        params.append(filters["end_date"].isoformat())

    multi_filters = (
        ("farm", "C.FarmName"),
        ("variety", "C.VarietyDescription"),
        ("group", "C.GroupDescription"),
        ("product_type", "C.StkCrpType"),
    )
    for name, column in multi_filters:
        values = filters[name]
        if values:
            placeholders = ",".join("?" for _ in values)
            clauses.append(f"{column} IN ({placeholders})")
            params.extend(values)

    if filters["project"]:
        placeholders = ",".join("?" for _ in filters["project"])
        clauses.append(f"C.Project IN ({placeholders})")
        params.extend(filters["project"])
    if filters["crop"]:
        placeholders = ",".join("?" for _ in filters["crop"])
        clauses.append(f"C.ProjAttrCropId IN ({placeholders})")
        params.extend(filters["crop"])
    if filters["product"]:
        placeholders = ",".join("?" for _ in filters["product"])
        clauses.append(f"C.AccountLink IN ({placeholders})")
        params.extend(filters["product"])

    return (" AND ".join(clauses) if clauses else "1 = 1"), params


BASE_FROM = """
FROM rpt.ChemicalCosts C
LEFT JOIN cmn._uvProject P ON P.ProjectLink = C.Project
"""


def _grouped_metrics(cursor, where, params, value_expression, key_expression,
                     label_expression, per_hectare=False, period_expression=None):
    period_select = f"{period_expression} AS Period," if period_expression else ""
    period_group = "Period," if period_expression else ""
    period_key_select = "Period," if period_expression else ""
    period_join = "A.Period=H.Period AND " if period_expression else ""
    output_period = "A.Period," if period_expression else ""
    value_order = (
        "CASE WHEN H.TotalHectares > 0 THEN A.TotalValue / H.TotalHectares END DESC"
        if per_hectare else "A.TotalValue DESC"
    )
    cursor.execute(
        f"""
        WITH Filtered AS (
            SELECT {period_select}
                   {key_expression} AS CategoryKey,
                   {label_expression} AS Category,
                   C.Project, C.IdSprayH, C.SprayPHa,
                   COALESCE({value_expression},0) AS Amount
            {BASE_FROM}
            WHERE {where}
        ),
        Amounts AS (
            SELECT {period_key_select}CategoryKey, MAX(Category) AS Category,
                   SUM(Amount) AS TotalValue
            FROM Filtered
            GROUP BY {period_group}CategoryKey
        ),
        HectareCombos AS (
            SELECT {period_key_select}CategoryKey, Project, IdSprayH,
                   MAX(SprayPHa) AS Hectares
            FROM Filtered
            WHERE Project IS NOT NULL AND IdSprayH IS NOT NULL
              AND SprayPHa IS NOT NULL AND SprayPHa > 0
            GROUP BY {period_group}CategoryKey, Project, IdSprayH
        ),
        Hectares AS (
            SELECT {period_key_select}CategoryKey, SUM(Hectares) AS TotalHectares
            FROM HectareCombos
            GROUP BY {period_group}CategoryKey
        )
        SELECT {output_period}A.CategoryKey,
               A.Category, A.TotalValue, H.TotalHectares
        FROM Amounts A
        LEFT JOIN Hectares H ON {period_join}A.CategoryKey=H.CategoryKey
        ORDER BY { "A.Period, " if period_expression else "" }{value_order}
        """,
        tuple(params),
    )
    results = []
    for row in cursor.fetchall():
        value = row.TotalValue or 0
        if per_hectare:
            value = (float(value) / float(row.TotalHectares)) if row.TotalHectares and row.TotalHectares > 0 else None
        results.append({
            "period": row.Period if period_expression else None,
            "key": row.CategoryKey,
            "label": row.Category if row.Category is not None else "Not specified",
            "value": float(value) if value is not None else None,
            "hectares": float(row.TotalHectares) if row.TotalHectares is not None else None,
        })
    return results


def _chart1_datasets(rows, periods, grouped, cumulative=False):
    if not grouped:
        values = [
            next((row["value"] for row in rows if row["period"] == period), None)
            for period in periods
        ]
        return [{
            "label": "Overall",
            "selection_value": None,
            "data": _cumulative_values(values) if cumulative else values,
        }]

    categories = {}
    totals = {}
    for row in rows:
        categories[row["key"]] = row["label"]
        totals[row["key"]] = totals.get(row["key"], 0) + (row["value"] or 0)
    selected_keys = sorted(totals, key=totals.get, reverse=True)[:12]
    datasets = []
    for key in selected_keys:
        values = [
            next((row["value"] for row in rows
                  if row["period"] == period and row["key"] == key), None)
            for period in periods
        ]
        datasets.append({
            "label": categories[key],
            "selection_value": str(key),
            "data": _cumulative_values(values) if cumulative else values,
        })
    return datasets


def _cumulative_values(values):
    running_total = 0
    has_value = False
    cumulative = []
    for value in values:
        if value is not None:
            running_total += value
            has_value = True
        cumulative.append(running_total if has_value else None)
    return cumulative


def _chart_period_label(period, interval):
    if interval == "plant_week":
        if period < 0:
            return f"Week {abs(period)} before planting"
        return f"Week {period} after planting"
    if interval == "weekly":
        year, week = period.split("-")
        return f"Week {int(week)}, {year}"
    if interval == "monthly":
        year, month = period.split("-")
        return f"{datetime(int(year), int(month), 1):%b %Y}"
    return period


def _chart_period_ranges(periods, interval):
    ranges = []
    for period in periods:
        bounds = _period_bounds(period, interval)
        ranges.append({
            "start": bounds[0].isoformat(),
            "end": (bounds[1] - timedelta(days=1)).isoformat(),
        } if bounds else None)
    return ranges


@report_bp.route("/chemical-analysis", methods=["GET"])
@login_required
def chemical_analysis_page():
    _require_view()
    return render_template("reports/chemical_analysis/index.html")


def _refresh_status(cursor):
    cursor.execute("""
        SELECT TOP 1 RefreshedAt, RowsInserted, RefreshedBy
        FROM rpt.ChemicalCostsRefreshLog
        ORDER BY RefreshedAt DESC, RefreshId DESC
    """)
    row = cursor.fetchone()
    cursor.execute("SELECT COUNT(*) AS RowCountValue FROM rpt.ChemicalCosts")
    row_count = int(cursor.fetchone().RowCountValue or 0)
    if not row:
        return None, row_count
    return {
        "refreshed_at": (row.RefreshedAt.isoformat() if hasattr(row.RefreshedAt, "isoformat") else str(row.RefreshedAt)) if row.RefreshedAt else None,
        "rows_inserted": int(row.RowsInserted or 0),
        "refreshed_by": row.RefreshedBy,
        "row_count": row_count,
    }, row_count


@report_bp.route("/api/chemical-analysis/status", methods=["GET"])
@login_required
def chemical_analysis_status():
    _require_view()
    conn = create_db_connection()
    cursor = conn.cursor()
    try:
        status, row_count = _refresh_status(cursor)
        if status is not None:
            status["row_count"] = row_count
        return jsonify({"success": True, "refresh": status, "row_count": row_count})
    except Exception as ex:
        print("Chemical analysis refresh status error:", ex)
        return jsonify({"success": False, "message": "Could not load refresh status"}), 500
    finally:
        close_db_connection(conn, cursor)


@report_bp.route("/api/chemical-analysis/refresh", methods=["POST"])
@login_required
def chemical_analysis_refresh():
    _require_view()
    permissions = set(current_user.permissions or [])
    if not permissions.intersection({"REPORTS_ALL", "MANAGE_USERS"}):
        return jsonify({"success": False, "message": "Permission denied"}), 403

    conn = create_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""EXEC rpt.sp_RefreshChemicalCosts
                        @AppUserName = ?;""", (current_user.username,))
        row = cursor.fetchone()
        conn.commit()
        status, row_count = _refresh_status(cursor)
        return jsonify({
            "success": True,
            "message": "Chemical costs data refreshed successfully.",
            "refresh": status,
            "row_count": row_count,
            "procedure_result": {
                "success": bool(row.Success) if row and hasattr(row, "Success") else True,
                "rows_inserted": int(row.RowsInserted or 0) if row and hasattr(row, "RowsInserted") else row_count,
                "refreshed_at": _json_safe(row.RefreshedAt) if row and hasattr(row, "RefreshedAt") else None,
            } if row else None,
        })
    except Exception as ex:
        conn.rollback()
        print("Chemical analysis refresh error:", ex)
        return jsonify({"success": False, "message": str(ex)}), 500
    finally:
        close_db_connection(conn, cursor)


@report_bp.route("/api/chemical-analysis/filters", methods=["GET"])
@login_required
def chemical_analysis_filters():
    _require_view()
    base_filters = _get_filters(request)
    where, params = _build_filter_sql(base_filters)
    conn = create_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT 1
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = 'agr'
              AND TABLE_NAME = 'Farm'
              AND COLUMN_NAME = 'FarmColour'
        """)
        farm_has_colour = cursor.fetchone() is not None
        farm_colour_expression = (
            """(SELECT TOP 1 F.FarmColour
               FROM agr.Farm F
               WHERE F.FarmName = C.FarmName
               ORDER BY F.IdFarm)"""
            if farm_has_colour else "CAST(NULL AS nvarchar(7))"
        )

        def distinct(column, order_column=None, extra_params=None):
            extra_params = extra_params or []
            cursor.execute(
                f"""
                SELECT DISTINCT {column} AS Value
                {BASE_FROM}
                WHERE {where}
                  AND {column} IS NOT NULL
                  AND LTRIM(RTRIM(CAST({column} AS varchar(255)))) <> ''
                ORDER BY {order_column or column}
                """,
                tuple(params + extra_params),
            )
            return [row.Value for row in cursor.fetchall()]

        cursor.execute(
            f"""
            SELECT MIN(C.TxDate) AS PeriodStart, MAX(C.TxDate) AS PeriodEnd
            {BASE_FROM}
            WHERE {where}
            """,
            tuple(params),
        )
        period = cursor.fetchone()

        cursor.execute(
            f"""
            SELECT DISTINCT C.FarmName AS Id, C.FarmName AS Label,
                   {farm_colour_expression} AS Colour
            {BASE_FROM}
            WHERE {where} AND C.FarmName IS NOT NULL
            ORDER BY C.FarmName
            """,
            tuple(params),
        )
        farms = [
            {"id": row.Id, "label": row.Label, "colour": row.Colour}
            for row in cursor.fetchall()
        ]

        cursor.execute(
            f"""
            SELECT DISTINCT C.Project AS Id, P.ProjectName AS Label
            {BASE_FROM}
            WHERE {where} AND C.Project IS NOT NULL
            ORDER BY P.ProjectName
            """,
            tuple(params),
        )
        projects = [{"id": int(row.Id), "label": row.Label} for row in cursor.fetchall()]

        cursor.execute(
            f"""
            SELECT DISTINCT C.ProjAttrCropId AS Id, C.CropDescription AS Label,
                   CRP.CropThemeColor AS Colour
            {BASE_FROM}
            LEFT JOIN agr.Crop CRP ON CRP.IdCrop = C.ProjAttrCropId
            WHERE {where} AND C.ProjAttrCropId IS NOT NULL
            ORDER BY C.CropDescription
            """,
            tuple(params),
        )
        crops = [
            {"id": int(row.Id), "label": row.Label, "colour": row.Colour}
            for row in cursor.fetchall()
        ]

        cursor.execute(
            f"""
            SELECT DISTINCT C.VarietyDescription AS Id, C.VarietyDescription AS Label
            {BASE_FROM}
            WHERE {where} AND C.VarietyDescription IS NOT NULL
            ORDER BY C.VarietyDescription
            """,
            tuple(params),
        )
        varieties = [{"id": row.Id, "label": row.Label} for row in cursor.fetchall()]

        cursor.execute(
            f"""
            SELECT DISTINCT C.AccountLink AS Id,
                   COALESCE(C.ProductDescription, CONCAT('Stock ', C.AccountLink)) AS Label
            {BASE_FROM}
            WHERE {where} AND C.AccountLink IS NOT NULL
            ORDER BY Label
            """,
            tuple(params),
        )
        products = [{"id": int(row.Id), "label": row.Label} for row in cursor.fetchall()]

        return jsonify({
            "success": True,
            "period": {
                "start": period.PeriodStart.strftime("%Y-%m-%d") if period.PeriodStart else None,
                "end": period.PeriodEnd.strftime("%Y-%m-%d") if period.PeriodEnd else None,
            },
            "farms": farms,
            "projects": projects,
            "crops": crops,
            "varieties": varieties,
            "groups": [{"id": "Fertilisers", "label": "Fertilisers"}, {"id": "Chemicals", "label": "Chemicals"}],
            "product_types": [
                {"id": value, "label": value}
                for value in distinct("C.StkCrpType")
            ],
            "products": products,
        })
    except Exception as ex:
        print("Chemical analysis filters error:", ex)
        return jsonify({"success": False, "message": "Could not load report filters"}), 500
    finally:
        close_db_connection(conn, cursor)


SOURCE_SORT_COLUMNS = {
    "tx_date": "C.TxDate",
    "dt_stamp": "C.DTStamp",
    "user_name": "C.UserName",
    "farm": "C.FarmName",
    "project": "P.ProjectName",
    "crop": "C.CropDescription",
    "variety": "C.VarietyDescription",
    "group": "C.GroupDescription",
    "product_type": "C.StkCrpType",
    "product": "C.ProductDescription",
    "ingredient": "C.ChemActIngredient",
    "quantity": "C.Qty",
    "cost": "C.TotalCost",
    "account_link": "C.AccountLink",
}


SOURCE_SELECT = """
    C.TxDate, C.DTStamp, C.UserName, C.FarmName,
    P.ProjectName, C.CropDescription, C.VarietyDescription,
    C.GroupDescription, C.StkCrpType,
    C.ProductCode, C.ProductDescription,
    C.ChemActIngredient, C.Qty,
    COALESCE(C.UnitCode, 'Unknown') AS UnitCode,
    C.UnitCost, C.TotalCost,
    C.WarehouseID, C.WeekNo, C.IdSprayH, C.SprayHNo,
    C.AccountLink, C.SprayPHa
"""


@report_bp.route("/api/chemical-analysis/source-data", methods=["GET"])
@login_required
def chemical_analysis_source_data():
    _require_view()
    filters = _get_filters(request)
    where, params = _build_filter_sql(filters)

    try:
        page = max(1, int(request.args.get("page", 1)))
    except (TypeError, ValueError):
        page = 1
    all_records = request.args.get("all") == "1"
    if all_records:
        page = 1
        page_size = MAX_DOCUMENT_RECORDS
    else:
        try:
            page_size = min(200, max(10, int(request.args.get("page_size", 50))))
        except (TypeError, ValueError):
            page_size = 50

    search = (request.args.get("search") or "").strip()
    search_clause = ""
    if search:
        if len(search) > 100:
            search = search[:100]
        search_clause = """
          AND (
            C.FarmName LIKE ? OR P.ProjectName LIKE ? OR C.CropDescription LIKE ?
            OR C.VarietyDescription LIKE ? OR C.StkCrpType LIKE ?
            OR C.ProductCode LIKE ? OR C.ProductDescription LIKE ?
            OR C.ChemActIngredient LIKE ? OR C.UserName LIKE ?
          )
        """
        params.extend([f"%{search}%"] * 9)

    sort_key = request.args.get("sort", "tx_date")
    sort_column = SOURCE_SORT_COLUMNS.get(sort_key, "C.TxDate")
    sort_direction = "ASC" if request.args.get("direction", "desc").lower() == "asc" else "DESC"
    combined_where = f"{where}{search_clause}"

    conn = create_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            f"""
            SELECT COUNT(*) AS RecordCount
            {BASE_FROM}
            WHERE {combined_where}
            """,
            tuple(params),
        )
        record_count = int(cursor.fetchone().RecordCount or 0)
        if all_records and record_count > MAX_DOCUMENT_RECORDS:
            return jsonify({
                "success": False,
                "message": "Print exceeds the 50,000-record limit. Narrow the filters or search and try again.",
            }), 413

        offset = (page - 1) * page_size
        cursor.execute(
            f"""
            SELECT {SOURCE_SELECT}
            {BASE_FROM}
            WHERE {combined_where}
            ORDER BY {sort_column} {sort_direction}
            OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
            """,
            tuple(params + [offset, page_size]),
        )
        rows = []
        for row in cursor.fetchall():
            spray_hectares = None
            if row.SprayPHa is not None:
                spray_hectares = float(row.SprayPHa)
            spray_id = int(row.IdSprayH) if row.IdSprayH is not None else None
            spray_link = (
                url_for("agri.spray_execution_page", spray_id=spray_id)
                if spray_id is not None and "SPRAY_REC_VIEW" in (current_user.permissions or [])
                else None
            )
            rows.append({
                "tx_date": _json_safe(row.TxDate),
                "dt_stamp": _json_safe(row.DTStamp),
                "user_name": row.UserName,
                "farm": row.FarmName,
                "project": row.ProjectName,
                "crop": row.CropDescription,
                "variety": row.VarietyDescription,
                "group": row.GroupDescription,
                "product_type": row.StkCrpType,
                "stock_code": row.ProductCode,
                "product": row.ProductDescription,
                "ingredient": row.ChemActIngredient,
                "quantity": -float(row.Qty or 0),
                "unit": row.UnitCode,
                "unit_cost": float(row.UnitCost or 0),
                "cost": -float(row.TotalCost or 0),
                "warehouse_id": row.WarehouseID,
                "spray_week": row.WeekNo,
                "spray_header_id": spray_id,
                "spray_header_no": row.SprayHNo,
                "spray_link": spray_link,
                "account_link": row.AccountLink,
                "spray_hectares": spray_hectares,
            })

        return jsonify({
            "success": True,
            "rows": rows,
            "page": page,
            "page_size": page_size,
            "total": record_count,
            "pages": max(1, (record_count + page_size - 1) // page_size),
        })
    except Exception as ex:
        print("Chemical analysis source data error:", ex)
        return jsonify({"success": False, "message": "Could not load source data"}), 500
    finally:
        close_db_connection(conn, cursor)


@report_bp.route("/api/chemical-analysis/export", methods=["GET"])
@login_required
def chemical_analysis_export():
    _require_view()
    filters = _get_filters(request)
    where, params = _build_filter_sql(filters)
    search = (request.args.get("search") or "").strip()
    search_clause = ""
    if search:
        if len(search) > 100:
            search = search[:100]
        search_clause = """
          AND (
            C.FarmName LIKE ? OR P.ProjectName LIKE ? OR C.CropDescription LIKE ?
            OR C.VarietyDescription LIKE ? OR C.StkCrpType LIKE ?
            OR C.ProductCode LIKE ? OR C.ProductDescription LIKE ?
            OR C.ChemActIngredient LIKE ? OR C.UserName LIKE ?
          )
        """
        params.extend([f"%{search}%"] * 9)

    conn = create_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            f"""
            SELECT COUNT(*) AS RecordCount
            {BASE_FROM}
            WHERE {where}{search_clause}
            """,
            tuple(params),
        )
        record_count = int(cursor.fetchone().RecordCount or 0)
        if record_count > 50000:
            return jsonify({
                "success": False,
                "message": "Export exceeds the 50,000-record limit. Narrow the filters and try again.",
            }), 413

        cursor.execute(
            f"""
            SELECT TOP 50000 {SOURCE_SELECT}
            {BASE_FROM}
            WHERE {where}{search_clause}
            ORDER BY C.TxDate DESC
            """,
            tuple(params),
        )

        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Chemical Analysis"
        headings = [
            "Transaction Date", "Timestamp", "User", "Farm", "Project", "Crop", "Variety",
            "Group", "Product Type", "Stock Code", "Product", "Active Ingredient",
            "Quantity", "Unit", "Unit Cost", "Total Cost", "Warehouse ID", "Spray Week",
            "Spray Header ID", "Spray Header No", "Account Link", "Spray Hectares",
        ]
        sheet.append(headings)
        for cell in sheet[1]:
            cell.font = Font(bold=True)

        for row in cursor.fetchall():
            sheet.append([
                row.TxDate, row.DTStamp, row.UserName, row.FarmName, row.ProjectName,
                row.CropDescription, row.VarietyDescription, row.GroupDescription,
                row.StkCrpType, row.ProductCode, row.ProductDescription, row.ChemActIngredient,
                -float(row.Qty or 0), row.UnitCode, float(row.UnitCost or 0),
                -float(row.TotalCost or 0), row.WarehouseID, row.WeekNo,
                row.IdSprayH, row.SprayHNo, row.AccountLink,
                float(row.SprayPHa) if row.SprayPHa is not None else None,
            ])

        for index, width in enumerate([14, 20, 16, 18, 24, 16, 18, 16, 16, 16, 28, 32,
                                       12, 10, 12, 14, 12, 12, 14, 16, 12, 14], start=1):
            sheet.column_dimensions[get_column_letter(index)].width = width

        output = BytesIO()
        workbook.save(output)
        output.seek(0)
        return send_file(
            output,
            as_attachment=True,
            download_name=f"chemical_fertiliser_analysis_{date.today().isoformat()}.xlsx",
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    except Exception as ex:
        print("Chemical analysis export error:", ex)
        return jsonify({"success": False, "message": "Could not export report"}), 500
    finally:
        close_db_connection(conn, cursor)


@report_bp.route("/api/chemical-analysis/dashboard", methods=["GET"])
@login_required
def chemical_analysis_dashboard():
    _require_view()
    filters = _get_filters(request)
    where, params = _build_filter_sql(filters)

    chart1_measure = request.args.get("chart1_measure", "cost")
    chart1_calculation = request.args.get("chart1_calculation", "total")
    chart1_group = request.args.get("chart1_group", "none")
    chart1_interval = request.args.get("chart1_interval", "weekly")
    chart1_cumulative = request.args.get("chart1_cumulative", "false").lower() in ("true", "1")
    chart2_measure = request.args.get("chart2_measure", "cost")
    chart2_calculation = request.args.get("chart2_calculation", "total")
    chart2_group = request.args.get("chart2_group", "crop")
    chart3_measure = request.args.get("chart3_measure", "cost")
    chart3_calculation = request.args.get("chart3_calculation", "total")
    chart3_group = request.args.get("chart3_group", "product")

    conn = create_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            f"""
            SELECT -SUM(COALESCE(C.TotalCost,0)) AS TotalCost,
                   COUNT(DISTINCT C.AccountLink) AS ProductCount
            {BASE_FROM} WHERE {where}
            """,
            tuple(params),
        )
        totals = cursor.fetchone()

        cursor.execute(
            f"""
            WITH Hectares AS (
                SELECT DISTINCT C.IdSprayH,C.Project,C.SprayPHa
                {BASE_FROM}
                WHERE {where} AND C.IdSprayH IS NOT NULL
                  AND C.SprayPHa IS NOT NULL AND C.SprayPHa>0
            )
            SELECT SUM(SprayPHa) AS Hectares FROM Hectares
            """,
            tuple(params),
        )
        hectares_row = cursor.fetchone()
        hectares = float(hectares_row.Hectares) if hectares_row and hectares_row.Hectares is not None else None
        total_cost = float(totals.TotalCost or 0)

        cursor.execute(
            f"""
            SELECT COALESCE(C.UnitCode,'Unknown') AS Unit,
                   -SUM(COALESCE(C.Qty,0)) AS Quantity
            {BASE_FROM} WHERE {where}
            GROUP BY COALESCE(C.UnitCode,'Unknown') ORDER BY Quantity DESC
            """,
            tuple(params),
        )
        quantity_breakdown = [{"unit": row.Unit, "quantity": float(row.Quantity or 0)} for row in cursor.fetchall()]

        chart1 = {"labels": [], "datasets": []}
        if chart1_measure not in ("cost", "quantity") or chart1_calculation not in ("total", "per_hectare"):
            abort(400, "Invalid graph 1 setting")
        if chart1_group != "none" and chart1_group not in GROUP_COLUMNS:
            abort(400, "Invalid graph 1 grouping")
        chart1_where = where
        chart1_params = list(params)
        time_expression = "CONVERT(varchar(10),C.TxDate,23)"
        if chart1_interval == "monthly":
            time_expression = "CONVERT(varchar(7),C.TxDate,23)"
        elif chart1_interval == "weekly":
            time_expression = "C.WeekNo"
        elif chart1_interval == "plant_week":
            time_expression = PLANT_WEEK_EXPRESSION
            chart1_where += " AND C.SprayPPlantDate IS NOT NULL"
        elif chart1_interval != "daily":
            abort(400, "Invalid graph 1 interval")
        chart1_column = GROUP_COLUMNS.get(chart1_group) if chart1_group != "none" else None
        chart1_key = "CAST(1 AS int)" if chart1_column is None else GROUP_KEY_COLUMNS[chart1_group]
        chart1_label = "'Overall'" if chart1_column is None else (
            f"COALESCE({chart1_column},'Not specified')"
        )
        chart1_value = "-C.TotalCost" if chart1_measure == "cost" else "-C.Qty"
        chart1_rows = _grouped_metrics(
            cursor, chart1_where, chart1_params, chart1_value, chart1_key, chart1_label,
            chart1_calculation == "per_hectare", time_expression,
        )
        raw_periods = sorted(
            {row["period"] for row in chart1_rows if row["period"] is not None},
            key=int if chart1_interval == "plant_week" else None,
        )
        chart_labels = [_chart_period_label(period, chart1_interval) for period in raw_periods]
        chart1 = {
            "labels": chart_labels,
            "period_values": raw_periods,
            "period_ranges": _chart_period_ranges(raw_periods, chart1_interval),
            "datasets": _chart1_datasets(
                chart1_rows, raw_periods, chart1_column is not None, chart1_cumulative
            ),
            "non_additive": chart1_group == "active_ingredient",
            "cumulative": chart1_cumulative,
        }

        def breakdown(chart_group, measure, calculation):
            if measure not in ("cost", "quantity") or calculation not in ("total", "per_hectare"):
                abort(400, "Invalid graph setting")
            if chart_group not in GROUP_COLUMNS:
                abort(400, "Invalid graph grouping")
            column = GROUP_COLUMNS[chart_group]
            key_expression = GROUP_KEY_COLUMNS[chart_group]
            label_expression = f"COALESCE({column},'Not specified')"
            value_expression = "-C.TotalCost" if measure == "cost" else "-C.Qty"
            rows = _grouped_metrics(
                cursor, where, params, value_expression, key_expression, label_expression,
                calculation == "per_hectare",
            )
            items = [{
                "label": row["label"],
                "value": row["value"],
                "selection_id": int(row["key"]) if chart_group == "product" and row["key"] is not None else None,
                "selection_value": str(row["key"]),
            } for row in rows]
            return {"items": items[:20], "non_additive": chart_group == "active_ingredient"}

        chart2 = breakdown(chart2_group, chart2_measure, chart2_calculation)
        chart3 = breakdown(chart3_group, chart3_measure, chart3_calculation)

        return jsonify({
            "success": True,
            "kpis": {
                "total_cost": total_cost,
                "cost_per_hectare": (total_cost / hectares) if hectares and hectares > 0 else None,
                "hectares": hectares,
                "quantity_breakdown": quantity_breakdown,
                "products_used": int(totals.ProductCount or 0),
                "hectares_available": hectares is not None,
            },
            "chart1": chart1,
            "chart2": chart2,
            "chart3": chart3,
        })
    except Exception as ex:
        print("Chemical analysis dashboard error:", ex)
        return jsonify({"success": False, "message": "Could not load dashboard data"}), 500
    finally:
        close_db_connection(conn, cursor)


@report_bp.route("/api/chemical-analysis/kpis", methods=["GET"])
@login_required
def chemical_analysis_kpis():
    _require_view()
    filters = _get_filters(request)
    where, params = _build_filter_sql(filters)
    conn = create_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            f"""
            SELECT
                -SUM(COALESCE(C.TotalCost, 0)) AS TotalCost,
                -SUM(COALESCE(C.Qty, 0)) AS TotalQty,
                COUNT(DISTINCT C.AccountLink) AS ProductCount
            {BASE_FROM}
            WHERE {where}
            """,
            tuple(params),
        )
        totals = cursor.fetchone()

        cursor.execute(
            f"""
            WITH Hectares AS (
                SELECT DISTINCT C.IdSprayH, C.Project, C.SprayPHa
                {BASE_FROM}
                WHERE {where}
                  AND C.IdSprayH IS NOT NULL
                  AND C.SprayPHa IS NOT NULL
                  AND C.SprayPHa > 0
            )
            SELECT SUM(SprayPHa) AS Hectares
            FROM Hectares
            """,
            tuple(params),
        )
        hectares_row = cursor.fetchone()
        hectares = float(hectares_row.Hectares) if hectares_row and hectares_row.Hectares is not None else None
        total_cost = float(totals.TotalCost or 0)

        cursor.execute(
            f"""
            SELECT COALESCE(C.UnitCode, 'Unknown') AS Unit,
                   -SUM(COALESCE(C.Qty, 0)) AS Quantity
            {BASE_FROM}
            WHERE {where}
            GROUP BY COALESCE(C.UnitCode, 'Unknown')
            ORDER BY Quantity DESC
            """,
            tuple(params),
        )
        quantity_breakdown = [
            {"unit": row.Unit, "quantity": float(row.Quantity or 0)}
            for row in cursor.fetchall()
        ]

        return jsonify({
            "success": True,
            "total_cost": total_cost,
            "cost_per_hectare": (total_cost / hectares) if hectares and hectares > 0 else None,
            "hectares": hectares,
            "quantity_breakdown": quantity_breakdown,
            "products_used": int(totals.ProductCount or 0),
            "hectares_available": hectares is not None,
        })
    except Exception as ex:
        print("Chemical analysis KPI error:", ex)
        return jsonify({"success": False, "message": "Could not calculate KPIs"}), 500
    finally:
        close_db_connection(conn, cursor)


@report_bp.route("/api/chemical-analysis/chart-data", methods=["GET"])
@login_required
def chemical_analysis_chart_data():
    _require_view()
    chart = request.args.get("chart", "")
    measure = request.args.get("measure", "cost")
    calculation = request.args.get("calculation", "total")
    group_by = request.args.get("group_by", "none")
    interval = request.args.get("interval", "weekly")
    cumulative = request.args.get("cumulative", "false").lower() in ("true", "1")

    if measure not in ("cost", "quantity"):
        return jsonify({"success": False, "message": "Invalid measure"}), 400
    if calculation not in ("total", "per_hectare"):
        return jsonify({"success": False, "message": "Invalid calculation"}), 400

    filters = _get_filters(request)
    where, params = _build_filter_sql(filters)
    conn = create_db_connection()
    cursor = conn.cursor()
    try:
        if chart == "1":
            time_expression = "CONVERT(varchar(10), C.TxDate, 23)"
            chart_where = where
            if interval == "monthly":
                time_expression = "CONVERT(varchar(7), C.TxDate, 23)"
            elif interval == "weekly":
                time_expression = "C.WeekNo"
            elif interval == "plant_week":
                time_expression = PLANT_WEEK_EXPRESSION
                chart_where += " AND C.SprayPPlantDate IS NOT NULL"
            elif interval != "daily":
                return jsonify({"success": False, "message": "Invalid interval"}), 400
            group_expression = GROUP_COLUMNS.get(group_by) if group_by != "none" else None
            if group_by != "none" and group_expression is None:
                return jsonify({"success": False, "message": "Invalid group"}), 400
            key_expression = "CAST(1 AS int)" if group_expression is None else GROUP_KEY_COLUMNS[group_by]
            label_expression = "'Overall'" if group_expression is None else f"COALESCE({group_expression},'Not specified')"
            value_expression = "-C.TotalCost" if measure == "cost" else "-C.Qty"
            rows = _grouped_metrics(
                cursor, chart_where, params, value_expression, key_expression, label_expression,
                calculation == "per_hectare", time_expression,
            )
            periods = sorted(
                {row["period"] for row in rows if row["period"] is not None},
                key=int if interval == "plant_week" else None,
            )
            labels = [_chart_period_label(period, interval) for period in periods]
            datasets = _chart1_datasets(rows, periods, group_expression is not None, cumulative)
            return jsonify({
                "success": True, "labels": labels, "datasets": datasets,
                "period_values": periods,
                "period_ranges": _chart_period_ranges(periods, interval),
                "non_additive": group_by == "active_ingredient",
                "cumulative": cumulative,
            })

        if chart in ("2", "3"):
            allowed = {
                "farm", "project", "crop", "variety", "group", "product_type",
                "product", "active_ingredient",
            }
            if group_by not in allowed:
                return jsonify({"success": False, "message": "Invalid group"}), 400
            column = GROUP_COLUMNS[group_by]
            key_expression = GROUP_KEY_COLUMNS[group_by]
            label_expression = f"COALESCE({column},'Not specified')"
            value_expression = "-C.TotalCost" if measure == "cost" else "-C.Qty"
            rows = _grouped_metrics(
                cursor, where, params, value_expression, key_expression, label_expression,
                calculation == "per_hectare",
            )
            items = [{
                "label": row["label"], "value": row["value"],
                "selection_id": int(row["key"]) if group_by == "product" and row["key"] is not None else None,
                "selection_value": str(row["key"]),
            } for row in rows]
            return jsonify({
                "success": True,
                "items": items[:15 if chart == "3" and group_by == "active_ingredient" else 20],
                "non_additive": chart == "3" and group_by == "active_ingredient",
            })

        return jsonify({"success": False, "message": "Invalid chart"}), 400
    except Exception as ex:
        print("Chemical analysis chart error:", ex)
        return jsonify({"success": False, "message": "Could not load chart data"}), 500
    finally:
        close_db_connection(conn, cursor)


@report_bp.route("/api/chemical-analysis/drilldown", methods=["GET"])
@login_required
def chemical_analysis_drilldown():
    _require_view()
    selection, error = _build_drilldown_selection(request)
    if error:
        return error

    chart = selection["chart"]
    group_by = selection["group_by"]
    measure = selection["measure"]
    calculation = selection["calculation"]
    interval = selection["interval"]
    cumulative = selection["cumulative"]
    period_value = selection["period_value"]
    period_bounds = selection["period_bounds"]
    combined_where = selection["combined_where"]
    query_params = selection["query_params"]
    selection_where = selection["selection_where"]
    selection_params = selection["selection_params"]

    try:
        page = max(1, int(request.args.get("page", 1)))
    except (TypeError, ValueError):
        page = 1
    all_records = request.args.get("all") == "1"
    if all_records:
        page = 1
        page_size = MAX_DOCUMENT_RECORDS
    else:
        try:
            page_size = min(100, max(10, int(request.args.get("page_size", 25))))
        except (TypeError, ValueError):
            page_size = 25
    offset = (page - 1) * page_size

    conn = create_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            f"""
            SELECT COUNT(*) AS RecordCount,
                   -SUM(COALESCE(C.TotalCost, 0)) AS TotalCost,
                   -SUM(COALESCE(C.Qty, 0)) AS TotalQuantity
            {BASE_FROM}
            WHERE {combined_where}
            """,
            tuple(query_params),
        )
        summary_row = cursor.fetchone()
        record_count = int(summary_row.RecordCount or 0)
        if all_records and record_count > MAX_DOCUMENT_RECORDS:
            return jsonify({
                "success": False,
                "message": "Print exceeds the 50,000-record limit. Narrow the chart selection and try again.",
            }), 413
        total_cost = float(summary_row.TotalCost or 0)
        total_quantity = float(summary_row.TotalQuantity or 0)

        cursor.execute(
            f"""
            WITH HectareCombos AS (
                SELECT C.IdSprayH, C.Project, MAX(C.SprayPHa) AS Hectares
                {BASE_FROM}
                WHERE {combined_where}
                  AND C.IdSprayH IS NOT NULL AND C.Project IS NOT NULL
                  AND C.SprayPHa IS NOT NULL AND C.SprayPHa > 0
                GROUP BY C.IdSprayH, C.Project
            )
            SELECT SUM(Hectares) AS TotalHectares FROM HectareCombos
            """,
            tuple(query_params),
        )
        hectares_row = cursor.fetchone()
        hectares = (
            float(hectares_row.TotalHectares)
            if hectares_row and hectares_row.TotalHectares is not None
            else None
        )

        cursor.execute(
            f"""
            SELECT COALESCE(C.UnitCode, 'Unknown') AS Unit,
                   -SUM(COALESCE(C.Qty, 0)) AS Quantity
            {BASE_FROM}
            WHERE {combined_where}
            GROUP BY COALESCE(C.UnitCode, 'Unknown')
            ORDER BY Quantity DESC
            """,
            tuple(query_params),
        )
        quantity_breakdown = [
            {"unit": row.Unit, "quantity": float(row.Quantity or 0)}
            for row in cursor.fetchall()
        ]

        cursor.execute(
            f"""
            SELECT C.CacheRowId, C.TxDate, C.Id, C.UserName, C.FarmName,
                   P.ProjectName, C.CropDescription, C.VarietyDescription,
                   C.GroupDescription, C.StkCrpType, C.ProductCode,
                   C.ProductDescription, C.ChemActIngredient, C.Qty,
                   COALESCE(C.UnitCode, 'Unknown') AS UnitCode, C.UnitCost,
                   C.TotalCost, C.IdSprayH, C.SprayHNo, C.SprayPHa
            {BASE_FROM}
            WHERE {combined_where}
            ORDER BY C.TxDate DESC, C.CacheRowId DESC
            OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
            """,
            tuple(query_params + [offset, page_size]),
        )
        can_view_spray = "SPRAY_REC_VIEW" in (current_user.permissions or [])
        rows = []
        for row in cursor.fetchall():
            spray_id = int(row.IdSprayH) if row.IdSprayH is not None else None
            rows.append({
                "tx_date": _json_safe(row.TxDate),
                "transaction_type": row.Id,
                "user_name": row.UserName,
                "farm": row.FarmName,
                "project": row.ProjectName,
                "crop": row.CropDescription,
                "variety": row.VarietyDescription,
                "group": row.GroupDescription,
                "product_type": row.StkCrpType,
                "stock_code": row.ProductCode,
                "product": row.ProductDescription,
                "ingredient": row.ChemActIngredient,
                "quantity": -float(row.Qty or 0),
                "unit": row.UnitCode,
                "unit_cost": float(row.UnitCost or 0),
                "cost": -float(row.TotalCost or 0),
                "spray_header_id": spray_id,
                "spray_header_no": row.SprayHNo,
                "spray_hectares": float(row.SprayPHa) if row.SprayPHa is not None else None,
                "spray_link": (
                    url_for("agri.spray_execution_page", spray_id=spray_id)
                    if spray_id is not None and can_view_spray
                    else None
                ),
            })

        metric_value = total_cost if measure == "cost" else total_quantity
        chart_value = (
            metric_value / hectares
            if calculation == "per_hectare" and hectares and hectares > 0
            else (metric_value if calculation == "total" else None)
        )
        if chart == "1" and cumulative and calculation == "per_hectare":
            time_expression = (
                PLANT_WEEK_EXPRESSION if interval == "plant_week"
                else "C.WeekNo" if interval == "weekly"
                else "CONVERT(varchar(7), C.TxDate, 23)" if interval == "monthly"
                else "CONVERT(varchar(10), C.TxDate, 23)"
            )
            group_expression = GROUP_COLUMNS.get(group_by) if group_by != "none" else None
            key_expression = GROUP_KEY_COLUMNS[group_by] if group_expression else "CAST(1 AS int)"
            label_expression = (
                f"COALESCE({group_expression},'Not specified')"
                if group_expression else "'Overall'"
            )
            value_expression = "-C.TotalCost" if measure == "cost" else "-C.Qty"
            period_rows = _grouped_metrics(
                cursor, selection_where, selection_params, value_expression,
                key_expression, label_expression, True, time_expression,
            )
            chart_value = sum(
                row["value"] or 0
                for row in period_rows
                if row["period"] <= period_value
            )

        period_range = None
        if period_bounds:
            period_range = {
                "start": period_bounds[0].isoformat(),
                "end": (period_bounds[1] - timedelta(days=1)).isoformat(),
            }
        return jsonify({
            "success": True,
            "label": request.args.get("selection_label", "Overall"),
            "group_by": group_by,
            "period_label": _chart_period_label(period_value, interval) if chart == "1" else None,
            "period_range": period_range,
            "cumulative": cumulative,
            "non_additive": group_by == "active_ingredient",
            "measure": measure,
            "calculation": calculation,
            "summary": {
                "total_cost": total_cost,
                "total_quantity": total_quantity,
                "quantity_breakdown": quantity_breakdown,
                "hectares": hectares,
                "chart_value": chart_value,
                "record_count": record_count,
            },
            "rows": rows,
            "page": page,
            "page_size": page_size,
            "total": record_count,
            "pages": max(1, (record_count + page_size - 1) // page_size),
        })
    except Exception as ex:
        print("Chemical analysis drilldown error:", ex)
        return jsonify({"success": False, "message": "Could not load transaction details"}), 500
    finally:
        close_db_connection(conn, cursor)


def _build_drilldown_selection(request_object):
    chart = request_object.args.get("chart")
    group_by = request_object.args.get("group_by", "none")
    measure = request_object.args.get("measure", "cost")
    calculation = request_object.args.get("calculation", "total")
    if chart not in ("1", "2", "3"):
        return None, (jsonify({"success": False, "message": "Invalid chart"}), 400)
    if measure not in ("cost", "quantity") or calculation not in ("total", "per_hectare"):
        return None, (jsonify({"success": False, "message": "Invalid chart calculation"}), 400)

    available_groups = {
        "farm", "project", "crop", "variety", "group", "product_type",
        "product", "active_ingredient",
    }
    if (chart == "1" and group_by != "none" and group_by not in GROUP_KEY_COLUMNS) or (
        chart != "1" and group_by not in available_groups
    ):
        return None, (jsonify({"success": False, "message": "Invalid chart grouping"}), 400)

    filters = _get_filters(request_object)
    where, params = _build_filter_sql(filters)
    selection_clauses = [where]
    selection_params = list(params)
    if chart == "1" and request_object.args.get("interval") == "plant_week":
        selection_clauses.append("C.SprayPPlantDate IS NOT NULL")

    if group_by != "none":
        group_value = request_object.args.get("group_value")
        if group_value is None or group_value == "":
            return None, (jsonify({"success": False, "message": "Missing chart category"}), 400)
        if group_by in NUMERIC_GROUPS:
            try:
                group_value = int(group_value)
            except (TypeError, ValueError):
                return None, (jsonify({"success": False, "message": "Invalid chart category"}), 400)
        group_clause = f"{DRILLDOWN_GROUP_COLUMNS[group_by]} = ?"
        selection_clauses.append(group_clause)
        selection_params.append(group_value)

    interval = request_object.args.get("interval", "weekly") if chart == "1" else None
    cumulative = request_object.args.get("cumulative", "false").lower() in ("true", "1")
    period_value = request_object.args.get("period")
    period_bounds = None
    clauses = list(selection_clauses)
    query_params = list(selection_params)
    if chart == "1":
        if interval == "plant_week":
            try:
                period_value = int(period_value)
                if str(period_value) != request_object.args.get("period"):
                    raise ValueError
            except (TypeError, ValueError):
                return None, (jsonify({"success": False, "message": "Invalid chart period"}), 400)
            clauses.append(f"{PLANT_WEEK_EXPRESSION} {'<=' if cumulative else '='} ?")
            query_params.append(period_value)
        else:
            period_bounds = _period_bounds(period_value or "", interval)
            if period_bounds is None:
                return None, (jsonify({"success": False, "message": "Invalid chart period"}), 400)
            expected_start = period_bounds[0].isoformat()
            expected_end = (period_bounds[1] - timedelta(days=1)).isoformat()
            if (
                request_object.args.get("period_start") not in (None, expected_start)
                or request_object.args.get("period_end") not in (None, expected_end)
            ):
                return None, (jsonify({"success": False, "message": "Chart period bounds do not match"}), 400)
            if cumulative:
                clauses.append("C.TxDate < CONVERT(date, ?, 23)")
                query_params.append(period_bounds[1].isoformat())
            else:
                clauses.append("C.TxDate >= CONVERT(date, ?, 23) AND C.TxDate < CONVERT(date, ?, 23)")
                query_params.extend([period_bounds[0].isoformat(), period_bounds[1].isoformat()])

    return {
        "chart": chart,
        "group_by": group_by,
        "measure": measure,
        "calculation": calculation,
        "interval": interval,
        "cumulative": cumulative,
        "period_value": period_value,
        "period_bounds": period_bounds,
        "filters": filters,
        "combined_where": " AND ".join(f"({clause})" for clause in clauses),
        "query_params": query_params,
        "selection_where": " AND ".join(f"({clause})" for clause in selection_clauses),
        "selection_params": selection_params,
    }, None


@report_bp.route("/api/chemical-analysis/drilldown/export", methods=["GET"])
@login_required
def chemical_analysis_drilldown_export():
    _require_view()
    selection, error = _build_drilldown_selection(request)
    if error:
        return error

    conn = create_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            f"SELECT COUNT(*) AS RecordCount {BASE_FROM} WHERE {selection['combined_where']}",
            tuple(selection["query_params"]),
        )
        record_count = int(cursor.fetchone().RecordCount or 0)
        if record_count > 50000:
            return jsonify({
                "success": False,
                "message": "Export exceeds the 50,000-record limit. Narrow the filters and try again.",
            }), 413

        cursor.execute(
            f"""
            SELECT TOP 50000 {SOURCE_SELECT}
            {BASE_FROM}
            WHERE {selection['combined_where']}
            ORDER BY C.TxDate DESC, C.CacheRowId DESC
            """,
            tuple(selection["query_params"]),
        )
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Chart Transactions"
        sheet.append([
            "Transaction Date", "Timestamp", "User", "Farm", "Project", "Crop",
            "Variety", "Group", "Product Type", "Stock Code", "Product",
            "Active Ingredient", "Quantity", "Unit", "Unit Cost", "Total Cost",
            "Spray Number", "Spray Instruction", "Account Link", "Spray Hectares",
        ])
        for cell in sheet[1]:
            cell.font = Font(bold=True)

        can_view_spray = "SPRAY_REC_VIEW" in (current_user.permissions or [])
        for row in cursor.fetchall():
            sheet.append([
                row.TxDate, row.DTStamp, row.UserName, row.FarmName, row.ProjectName,
                row.CropDescription, row.VarietyDescription, row.GroupDescription,
                row.StkCrpType, row.ProductCode, row.ProductDescription,
                row.ChemActIngredient, -float(row.Qty or 0), row.UnitCode,
                float(row.UnitCost or 0), -float(row.TotalCost or 0),
                row.SprayHNo,
                url_for("agri.spray_execution_page", spray_id=row.IdSprayH)
                if row.IdSprayH is not None and can_view_spray else None,
                row.AccountLink, float(row.SprayPHa) if row.SprayPHa is not None else None,
            ])

        output = BytesIO()
        workbook.save(output)
        output.seek(0)
        return send_file(
            output,
            as_attachment=True,
            download_name=f"chemical_analysis_chart_{date.today().isoformat()}.xlsx",
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    except Exception as ex:
        print("Chemical analysis drilldown export error:", ex)
        return jsonify({"success": False, "message": "Could not export chart transactions"}), 500
    finally:
        close_db_connection(conn, cursor)


DOCUMENT_FILTER_KEYS = {
    "start_date", "end_date", "farm", "project", "crop", "variety",
    "group", "product_type", "product",
}
DOCUMENT_REPORT_KEYS = {
    "chart1_measure", "chart1_calculation", "chart1_group", "chart1_interval",
    "chart1_cumulative", "chart2_measure", "chart2_calculation", "chart2_group",
    "chart3_measure", "chart3_calculation", "chart3_group",
}
DOCUMENT_DRILLDOWN_KEYS = DOCUMENT_FILTER_KEYS | {
    "chart", "group_by", "measure", "calculation", "interval", "cumulative",
    "period", "period_start", "period_end", "period_label", "group_value",
    "selection_label", "page", "page_size",
}


def _validate_document_query(raw_query, context):
    if not isinstance(raw_query, str) or len(raw_query) > 50000:
        return None, (jsonify({"success": False, "message": "Invalid document request"}), 400)
    try:
        pairs = parse_qsl(raw_query, keep_blank_values=False, max_num_fields=1000)
    except ValueError:
        return None, (jsonify({"success": False, "message": "Too many document parameters"}), 400)

    allowed = DOCUMENT_DRILLDOWN_KEYS if context == "drilldown" else (
        DOCUMENT_FILTER_KEYS | ({"search", "sort", "direction"} if context == "source" else DOCUMENT_REPORT_KEYS)
    )
    if any(key not in allowed or len(value) > 500 for key, value in pairs):
        return None, (jsonify({"success": False, "message": "Invalid document parameters"}), 400)

    values = MultiDict(pairs)
    for field in ("start_date", "end_date"):
        for value in values.getlist(field):
            if _parse_iso_date(value) is None:
                return None, (jsonify({"success": False, "message": "Invalid reporting date"}), 400)
    for field in ("project", "crop", "product"):
        for value in values.getlist(field):
            try:
                int(value)
            except ValueError:
                return None, (jsonify({"success": False, "message": "Invalid document filter"}), 400)

    if context == "source":
        if values.get("sort", "tx_date") not in SOURCE_SORT_COLUMNS:
            return None, (jsonify({"success": False, "message": "Invalid source-data sort"}), 400)
        if values.get("direction", "desc").lower() not in ("asc", "desc"):
            return None, (jsonify({"success": False, "message": "Invalid source-data sort direction"}), 400)
    elif context == "report":
        if values.get("chart1_measure", "cost") not in ("cost", "quantity"):
            return None, (jsonify({"success": False, "message": "Invalid chart measure"}), 400)
        if values.get("chart1_calculation", "total") not in ("total", "per_hectare"):
            return None, (jsonify({"success": False, "message": "Invalid chart calculation"}), 400)
        if values.get("chart1_group", "none") not in ({"none"} | set(GROUP_COLUMNS)):
            return None, (jsonify({"success": False, "message": "Invalid chart grouping"}), 400)
        if values.get("chart1_interval", "weekly") not in ("daily", "weekly", "monthly", "plant_week"):
            return None, (jsonify({"success": False, "message": "Invalid chart interval"}), 400)
        if values.get("chart1_cumulative", "false").lower() not in ("false", "true", "0", "1"):
            return None, (jsonify({"success": False, "message": "Invalid cumulative setting"}), 400)
        for chart in ("chart2", "chart3"):
            if values.get(f"{chart}_measure", "cost") not in ("cost", "quantity"):
                return None, (jsonify({"success": False, "message": "Invalid chart measure"}), 400)
            if values.get(f"{chart}_calculation", "total") not in ("total", "per_hectare"):
                return None, (jsonify({"success": False, "message": "Invalid chart calculation"}), 400)
            if values.get(f"{chart}_group", "crop" if chart == "chart2" else "product") not in GROUP_COLUMNS:
                return None, (jsonify({"success": False, "message": "Invalid chart grouping"}), 400)
    else:
        selection, error = _build_drilldown_selection(SimpleNamespace(args=values))
        if error:
            return None, error

    return pairs, None


@report_bp.route("/api/chemical-analysis/document.pdf", methods=["POST"])
@login_required
def chemical_analysis_document_pdf():
    _require_view()
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"success": False, "message": "Invalid PDF request"}), 400
    context = payload.get("context")
    if context not in ("report", "source", "drilldown"):
        return jsonify({"success": False, "message": "Invalid PDF context"}), 400
    pairs, error = _validate_document_query(payload.get("query"), context)
    if error:
        return error

    page_parameters = [("print_context", context)]
    if context == "drilldown":
        page_parameters.append(("drilldown_query", urlencode(pairs, doseq=True)))
    else:
        page_parameters.extend(pairs)

    application = current_app._get_current_object()
    internal_server = make_server("127.0.0.1", 0, application, threaded=True)
    server_thread = threading.Thread(target=internal_server.serve_forever, daemon=True)
    server_thread.start()
    try:
        internal_origin = f"http://127.0.0.1:{internal_server.server_port}"
        page_path = url_for("reports.chemical_analysis_page")
        page_url = f"{internal_origin}{page_path}?{urlencode(page_parameters, doseq=True)}"
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                browser_context = browser.new_context(
                    viewport={"width": 1440, "height": 1000},
                    accept_downloads=False,
                )
                cookie_names = {
                    application.config.get("SESSION_COOKIE_NAME", "session"),
                    application.config.get("REMEMBER_COOKIE_NAME", "remember_token"),
                }
                cookies = [
                    {
                        "name": name,
                        "value": value,
                        "url": internal_origin,
                        "httpOnly": True,
                        "secure": False,
                        "sameSite": "Lax",
                    }
                    for name, value in request.cookies.items()
                    if name in cookie_names
                ]
                if not cookies:
                    return jsonify({"success": False, "message": "Your login session could not be used to generate the PDF"}), 401
                browser_context.add_cookies(cookies)
                page = browser_context.new_page()
                page.route("https://cdn.onesignal.com/**", lambda route: route.abort())
                response = page.goto(page_url, wait_until="domcontentloaded", timeout=30000)
                if response is None or response.status >= 400 or url_for("reports.chemical_analysis_page") not in page.url:
                    return jsonify({"success": False, "message": "Could not open the authorized report for PDF generation"}), 502
                page.wait_for_function(
                    "window.__fermeDocumentReady === true || Boolean(window.__fermeDocumentError)",
                    timeout=120000,
                )
                document_error = page.evaluate("window.__fermeDocumentError || null")
                if document_error:
                    return jsonify({"success": False, "message": document_error}), 500
                page.emulate_media(media="print")
                page.evaluate("window.__fermePrepareForPdf()")
                pdf_data = page.pdf(
                    format="A4",
                    landscape=True,
                    print_background=True,
                    prefer_css_page_size=True,
                    display_header_footer=True,
                    header_template="<div></div>",
                    footer_template=(
                        "<div style='width:100%;margin:0 10mm;color:#666;font:8px Arial,sans-serif;"
                        "text-align:right'><span class='pageNumber'></span> / <span class='totalPages'></span></div>"
                    ),
                    margin={"top": "12mm", "right": "10mm", "bottom": "16mm", "left": "10mm"},
                )
            finally:
                browser.close()

        response = send_file(
            BytesIO(pdf_data),
            as_attachment=True,
            download_name=f"Chemical_Analysis_{date.today().isoformat()}.pdf",
            mimetype="application/pdf",
        )
        response.headers["Cache-Control"] = "private, no-store"
        return response
    except PlaywrightError:
        current_app.logger.exception("Chemical analysis PDF rendering failed")
        return jsonify({
            "success": False,
            "message": "PDF generation failed. Please try again.",
        }), 503
    except Exception:
        current_app.logger.exception("Chemical analysis PDF request failed")
        return jsonify({"success": False, "message": "Could not generate the report PDF"}), 500
    finally:
        internal_server.shutdown()
        internal_server.server_close()
        server_thread.join(timeout=5)
