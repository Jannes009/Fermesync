from datetime import date, datetime
from decimal import Decimal

from flask import abort, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from Agri.budgeting_utils import (
    budget_line_cost_per_ha,
    budget_line_total_cost,
    budget_week_periods,
    calculate_week_start,
    continuous_week_range,
    effective_budget_hectares,
    expense_value_from_transaction_sign,
    format_iso_week_label,
)
from Core.auth import create_db_connection
from . import agri_bp


def _format_timestamp(value):
    if not value:
        return "-"
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M")
    try:
        return datetime.fromisoformat(str(value)).strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return str(value)


def _format_date(value):
    if not value:
        return "-"
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    try:
        return datetime.fromisoformat(str(value)).strftime("%Y-%m-%d")
    except ValueError:
        return str(value)


def _sql_date_parameter(value):
    return value.isoformat() if isinstance(value, (date, datetime)) else value


def _template_description_exists(cursor, description, exclude_template_id=None):
    query = """
        SELECT TOP 1 IdBudgetTemplate
        FROM agr.BudgetTemplates
        WHERE LOWER(LTRIM(RTRIM(BTPDescription))) = LOWER(?)
    """
    params = [description]
    if exclude_template_id is not None:
        query += " AND IdBudgetTemplate <> ?"
        params.append(exclude_template_id)
    cursor.execute(query, params)
    return cursor.fetchone() is not None


def _has_budget_permission(*permissions):
    user_permissions = set(current_user.permissions or [])
    return any(permission in user_permissions for permission in permissions)


def _visible_crop_options(conn):
    cursor = conn.cursor()
    cursor.execute("SELECT IdCrop, CropCode, CropDescription FROM agr.Crop ORDER BY CropDescription")
    rows = cursor.fetchall()
    return [
        {"id": row.IdCrop, "code": row.CropCode, "description": row.CropDescription}
        for row in rows
    ]


def _fetch_stock_catalog(conn, crop_id):
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT DISTINCT SI.StockLink, SI.StockCode, SI.StockDescription,
               COALESCE(Cost.LastGRVCost, Cost.AverageCost, 0) AS UnitPrice
        FROM agr.ChemStockCrop CSC
        JOIN agr.ChemStock CS ON CS.IdChemStock = CSC.StkCrpChemStockId
        JOIN cmn._uvStockItems SI ON SI.StockLink = CS.ChemStockLink
        OUTER APPLY (
            SELECT TOP 1 AverageCost, LastGRVCost
            FROM cmn._uvStockCosts
            WHERE StockID = SI.StockLink
            ORDER BY StockID
        ) Cost
        WHERE CSC.StkCrpCropId = ?
          AND SI.ItemActive = 1
          AND SI.StockDescription IS NOT NULL
        ORDER BY SI.StockDescription
        """,
        (crop_id,),
    )
    return [
        {
            "id": row.StockLink,
            "code": row.StockCode,
            "description": row.StockDescription,
            "unit_price": float(row.UnitPrice or 0),
        }
        for row in cursor.fetchall()
    ]


def _fetch_template_lines(conn, template_id):
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT L.IdBTPLine, L.BTPLinStockId AS StockId, L.BTPLinRelationalWeek, L.BTPLinQuantityPerHa AS QuantityPerHa,
               I.StockCode, I.StockDescription
        FROM agr.BudgetTemplateLines L
        LEFT JOIN cmn._uvStockItems I ON I.StockLink = L.BTPLinStockId
        WHERE L.BTPLinBudgetTemplateId = ?
        ORDER BY L.IdBTPLine
        """,
        (template_id,),
    )
    return [
        {
            "id": row.IdBTPLine,
            "stock_id": row.StockId,
            "relational_week": row.BTPLinRelationalWeek,
            "quantity_per_ha": float(row.QuantityPerHa or 0),
            "stock_code": row.StockCode,
            "stock_description": row.StockDescription,
        }
        for row in cursor.fetchall()
    ]


def _budget_template_line_values(item):
    stock_id = item.get("stock_id")
    if stock_id in (None, ""):
        return None
    try:
        stock_id = int(stock_id)
        relational_week = int(item.get("relational_week"))
        quantity = float(item.get("quantity_per_ha"))
    except (TypeError, ValueError):
        raise ValueError("Each budget line must have a valid product, week, and quantity.")
    if quantity < 0:
        raise ValueError("Quantity per hectare cannot be negative.")
    return stock_id, relational_week, quantity


def _insert_budget_template_lines(cursor, template_id, lines):
    for item in lines:
        values = _budget_template_line_values(item)
        if values is None:
            continue
        cursor.execute(
            """
            INSERT INTO agr.BudgetTemplateLines
            (BTPLinBudgetTemplateId, BTPLinStockId, BTPLinRelationalWeek, BTPLinQuantityPerHa)
            VALUES (?, ?, ?, ?)
            """,
            (template_id, *values),
        )


def _save_budget_template_lines(cursor, template_id, lines):
    cursor.execute(
        "SELECT IdBTPLine FROM agr.BudgetTemplateLines WHERE BTPLinBudgetTemplateId = ?",
        (template_id,),
    )
    existing_ids = {int(row[0]) for row in cursor.fetchall()}
    retained_ids = set()

    for item in lines:
        values = _budget_template_line_values(item)
        if values is None:
            continue
        line_id = item.get("id")
        if line_id in (None, ""):
            cursor.execute(
                """
                INSERT INTO agr.BudgetTemplateLines
                (BTPLinBudgetTemplateId, BTPLinStockId, BTPLinRelationalWeek, BTPLinQuantityPerHa)
                VALUES (?, ?, ?, ?)
                """,
                (template_id, *values),
            )
            continue

        try:
            line_id = int(line_id)
        except (TypeError, ValueError):
            raise ValueError("Each saved budget line must have a valid line ID.")
        if line_id not in existing_ids:
            raise ValueError("A budget line does not belong to this template.")
        if line_id in retained_ids:
            raise ValueError("A budget line cannot be submitted more than once.")
        cursor.execute(
            """
            UPDATE agr.BudgetTemplateLines
            SET BTPLinStockId = ?, BTPLinRelationalWeek = ?, BTPLinQuantityPerHa = ?
            WHERE IdBTPLine = ? AND BTPLinBudgetTemplateId = ?
            """,
            (*values, line_id, template_id),
        )
        retained_ids.add(line_id)

    for line_id in existing_ids - retained_ids:
        cursor.execute(
            "DELETE FROM agr.BudgetTemplateLines WHERE IdBTPLine = ? AND BTPLinBudgetTemplateId = ?",
            (line_id, template_id),
        )


def _fetch_project_budget_lines(conn, budget_id):
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT L.IdProjectBudgetLine, L.PBLinProjectBudgetId, L.PBLinRelationalWeek, L.PBLinWeekStartDate,
               L.PBLinStockId, L.PBLinQuantityPerHa, L.PBLinBudgetUnitPrice,
               I.StockCode, I.StockDescription
        FROM agr.ProjectBudgetLines L
        LEFT JOIN cmn._uvStockItems I ON I.StockLink = L.PBLinStockId
        WHERE L.PBLinProjectBudgetId = ?
        ORDER BY L.PBLinRelationalWeek, I.StockDescription
        """,
        (budget_id,),
    )
    rows = cursor.fetchall()
    return [
        {
            "id": row.IdProjectBudgetLine,
            "stock_id": row.PBLinStockId,
            "relational_week": row.PBLinRelationalWeek,
            "week_start_date": row.PBLinWeekStartDate,
            "quantity_per_ha": float(row.PBLinQuantityPerHa or 0),
            "unit_price": float(row.PBLinBudgetUnitPrice or 0),
            "stock_code": row.StockCode,
            "stock_description": row.StockDescription,
            "calendar_week": format_iso_week_label(row.PBLinWeekStartDate) if row.PBLinWeekStartDate else "-",
        }
        for row in rows
    ]


def _project_budget_total(budget_ha, unit_price, quantity_per_ha):
    return budget_line_total_cost(quantity_per_ha, budget_ha, unit_price)


@agri_bp.route("/budget-templates")
@login_required
def budget_templates():
    return redirect(url_for("agri.budgets_overview", tab="templates"))


@agri_bp.route("/budgets")
@login_required
def budgets_overview():
    can_view_templates = _has_budget_permission("BUDGET_VIEW", "BUDGET_TEMPLATE_MANAGE")
    can_view_projects = _has_budget_permission("BUDGET_VIEW", "BUDGET_CREATE", "BUDGET_TEMPLATE_MANAGE")
    if not can_view_templates and not can_view_projects:
        abort(403)

    conn = create_db_connection()
    cursor = conn.cursor()
    templates = []
    budgets = []
    try:
        if can_view_templates:
            cursor.execute(
                """
        SELECT T.IdBudgetTemplate, T.BTPDescription, C.CropDescription,
               T.BTPIsActive, T.BTPCreatedAt, T.BTPModifiedAt,
               U1.UserName AS CreatedByName, U2.UserName AS ModifiedByName,
               COUNT(L.IdBTPLine) AS ProductCount,
               COUNT(DISTINCT L.BTPLinRelationalWeek) AS WeekCount
        FROM agr.BudgetTemplates T
        LEFT JOIN agr.Crop C ON C.IdCrop = T.BTPCropId
        LEFT JOIN users.Users U1 ON U1.id = T.BTPCreatedBy
        LEFT JOIN users.Users U2 ON U2.id = T.BTPModifiedBy
        LEFT JOIN agr.BudgetTemplateLines L ON L.BTPLinBudgetTemplateId = T.IdBudgetTemplate
        GROUP BY T.IdBudgetTemplate, T.BTPDescription, C.CropDescription,
                 T.BTPIsActive, T.BTPCreatedAt, T.BTPModifiedAt,
                 U1.UserName, U2.UserName
        ORDER BY T.BTPModifiedAt DESC, T.IdBudgetTemplate DESC
                """
            )
            templates = [
                {
                    "id": row.IdBudgetTemplate,
                    "description": row.BTPDescription,
                    "crop": row.CropDescription or "-",
                    "product_count": int(row.ProductCount or 0),
                    "week_count": int(row.WeekCount or 0),
                    "created_by": row.CreatedByName or "-",
                    "modified_at": _format_timestamp(row.BTPModifiedAt),
                    "is_active": bool(row.BTPIsActive),
                    "status": "Active" if row.BTPIsActive else "Inactive",
                }
                for row in cursor.fetchall()
            ]

        if can_view_projects:
            cursor.execute(
                """
                SELECT PRJ.ProjectLink, PRJ.ProjectName, PRJ.ProjectCode, C.CropDescription,
                       PA.ProjAttrPlantDate, PA.ProjAttrHa AS ProjectHa,
                       B.IdProjectBudget, B.PBPlantingDate, B.PBBudgetHa, B.PBStatus,
                       T.BTPDescription,
                       SUM(L.PBLinQuantityPerHa * L.PBLinBudgetUnitPrice * COALESCE(B.PBBudgetHa, PA.ProjAttrHa, 0)) AS TotalBudget
                FROM cmn._uvProject PRJ
                JOIN agr.ProjectAttributes PA ON PA.ProjAttrProjectId = PRJ.ProjectLink
                LEFT JOIN agr.Crop C ON C.IdCrop = PA.ProjAttrCropId
                LEFT JOIN agr.ProjectBudgets B ON B.PBProjectId = PRJ.ProjectLink
                LEFT JOIN agr.BudgetTemplates T ON T.IdBudgetTemplate = B.PBBudgetTemplateId
                LEFT JOIN agr.ProjectBudgetLines L ON L.PBLinProjectBudgetId = B.IdProjectBudget
                GROUP BY PRJ.ProjectLink, PRJ.ProjectName, PRJ.ProjectCode, C.CropDescription,
                         PA.ProjAttrPlantDate, PA.ProjAttrHa, B.IdProjectBudget, B.PBPlantingDate,
                         B.PBBudgetHa, B.PBStatus, T.BTPDescription
                ORDER BY PRJ.ProjectCode
                """
            )
            budgets = [
                {
                    "id": row.IdProjectBudget,
                    "project_id": row.ProjectLink,
                    "project_name": row.ProjectName or row.ProjectCode or "-",
                    "crop": row.CropDescription or "-",
                    "planting_date": _format_date(row.PBPlantingDate or row.ProjAttrPlantDate),
                    "project_ha": float(row.ProjectHa or 0),
                    "budget_ha": effective_budget_hectares(row.PBBudgetHa, row.ProjectHa) if row.IdProjectBudget else None,
                    "template": row.BTPDescription or "-",
                    "status": row.PBStatus or "Not budgeted",
                    "total_budget": float(row.TotalBudget or 0),
                }
                for row in cursor.fetchall()
            ]
    finally:
        conn.close()

    requested_tab = request.args.get("tab")
    if requested_tab == "projects" and can_view_projects:
        active_tab = "projects"
    elif requested_tab == "templates" and can_view_templates:
        active_tab = "templates"
    else:
        active_tab = "templates" if can_view_templates else "projects"
    permissions = set(current_user.permissions or [])
    return render_template(
        "budget_templates.html",
        templates=templates,
        budgets=budgets,
        active_tab=active_tab,
        can_create_template=bool(permissions.intersection({"AGR_MAIN", "BUDGET_CREATE", "BUDGET_TEMPLATE_MANAGE"})),
        can_edit_template=bool(permissions.intersection({"AGR_MAIN", "BUDGET_EDIT", "BUDGET_TEMPLATE_MANAGE"})),
        can_create_budget=bool(permissions.intersection({"AGR_MAIN", "BUDGET_CREATE", "BUDGET_TEMPLATE_MANAGE"})),
        can_edit_budget=bool(permissions.intersection({"AGR_MAIN", "BUDGET_EDIT", "BUDGET_TEMPLATE_MANAGE"})),
        can_view_templates=can_view_templates,
        can_view_projects=can_view_projects,
    )


@agri_bp.route("/budget-template/create", methods=["GET", "POST"])
@login_required
def create_budget_template():
    if not _has_budget_permission("BUDGET_CREATE", "BUDGET_TEMPLATE_MANAGE"):
        abort(403)

    payload = request.get_json(silent=True) if request.is_json else None
    if payload is not None:
        description = (payload.get("description") or "").strip() or "New budget template"
        crop_id = payload.get("crop_id")
        is_active = bool(payload.get("is_active", True))
        lines = payload.get("lines") or []
        conn = create_db_connection()
        cursor = conn.cursor()
        try:
            if _template_description_exists(cursor, description):
                return jsonify({"success": False, "message": "A budget template with this description already exists."}), 409
            cursor.execute(
                """
                INSERT INTO agr.BudgetTemplates
                (BTPDescription, BTPCropId, BTPIsActive, BTPCreatedBy, BTPCreatedAt, BTPModifiedBy, BTPModifiedAt)
                OUTPUT INSERTED.IdBudgetTemplate
                VALUES (?, ?, ?, ?, GETDATE(), ?, GETDATE())
                """,
                (description, int(crop_id) if crop_id not in (None, "") else None, int(is_active), current_user.id, current_user.id),
            )
            template_id = cursor.fetchone()[0]
            _insert_budget_template_lines(cursor, template_id, lines)
            conn.commit()
            return jsonify({"success": True, "template_id": template_id})
        except ValueError as exc:
            conn.rollback()
            return jsonify({"success": False, "message": str(exc)}), 400
        except Exception as exc:
            conn.rollback()
            return jsonify({"success": False, "message": str(exc)}), 400
        finally:
            conn.close()

    if request.method == "POST":
        description = (request.form.get("description") or "").strip() or "New budget template"
        crop_id = request.form.get("crop_id")
        is_active = request.form.get("is_active") in ("1", "true", "True", "on")
        conn = create_db_connection()
        cursor = conn.cursor()
        try:
            if _template_description_exists(cursor, description):
                abort(409, description="A budget template with this description already exists.")
            cursor.execute(
                """
                INSERT INTO agr.BudgetTemplates
                (BTPDescription, BTPCropId, BTPIsActive, BTPCreatedBy, BTPCreatedAt, BTPModifiedBy, BTPModifiedAt)
                OUTPUT INSERTED.IdBudgetTemplate
                VALUES (?, ?, ?, ?, GETDATE(), ?, GETDATE())
                """,
                (description, int(crop_id) if crop_id and crop_id.isdigit() else None, int(is_active), current_user.id, current_user.id),
            )
            template_id = cursor.fetchone()[0]
            conn.commit()
        finally:
            conn.close()
        return redirect(url_for("agri.edit_budget_template", template_id=template_id))

    conn = create_db_connection()
    template = {"id": None, "description": "", "crop_id": None, "is_active": True}
    try:
        crops = _visible_crop_options(conn)
    finally:
        conn.close()
    return render_template("budget_template_editor.html", template=template, crops=crops, lines=[])


@agri_bp.route("/budget-template/<int:template_id>", methods=["GET"])
@login_required
def edit_budget_template(template_id):
    if not _has_budget_permission("BUDGET_EDIT", "BUDGET_TEMPLATE_MANAGE"):
        abort(403)

    conn = create_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT T.IdBudgetTemplate, T.BTPDescription, T.BTPCropId, T.BTPIsActive,
                   C.CropDescription, C.CropCode
            FROM agr.BudgetTemplates T
            LEFT JOIN agr.Crop C ON C.IdCrop = T.BTPCropId
            WHERE T.IdBudgetTemplate = ?
            """,
            (template_id,),
        )
        row = cursor.fetchone()
        if not row:
            abort(404)
        crops = _visible_crop_options(conn)
        lines = _fetch_template_lines(conn, template_id)
        template = {
            "id": row.IdBudgetTemplate,
            "description": row.BTPDescription,
            "crop_id": row.BTPCropId,
            "crop_description": row.CropDescription,
            "crop_code": row.CropCode,
            "is_active": bool(row.BTPIsActive),
        }
        return render_template("budget_template_editor.html", template=template, crops=crops, lines=lines)
    finally:
        conn.close()


@agri_bp.route("/budget-template/stocks/<int:crop_id>")
@login_required
def budget_template_stocks(crop_id):
    if not _has_budget_permission("BUDGET_CREATE", "BUDGET_EDIT", "BUDGET_TEMPLATE_MANAGE"):
        abort(403)

    conn = create_db_connection()
    try:
        return jsonify(_fetch_stock_catalog(conn, crop_id))
    finally:
        conn.close()


@agri_bp.route("/budget-template/<int:template_id>/save", methods=["POST"])
@login_required
def save_budget_template(template_id):
    if not _has_budget_permission("BUDGET_EDIT", "BUDGET_TEMPLATE_MANAGE"):
        return jsonify({"success": False, "message": "Permission denied"}), 403

    payload = request.get_json(silent=True) or {}
    description = (payload.get("description") or "").strip() or "New budget template"
    crop_id = payload.get("crop_id")
    is_active = bool(payload.get("is_active", True))
    lines = payload.get("lines") or []
    
    conn = create_db_connection()
    cursor = conn.cursor()
    try:
        if _template_description_exists(cursor, description, template_id):
            return jsonify({"success": False, "message": "A budget template with this description already exists."}), 409
        cursor.execute(
            """
            UPDATE agr.BudgetTemplates
            SET BTPDescription = ?, BTPCropId = ?, BTPIsActive = ?, BTPModifiedBy = ?, BTPModifiedAt = GETDATE()
            WHERE IdBudgetTemplate = ?
            """,
            (description, int(crop_id) if crop_id not in (None, "") else None, int(is_active), current_user.id, template_id),
        )
        _save_budget_template_lines(cursor, template_id, lines)
        conn.commit()
        return jsonify({"success": True, "message": "Template saved"})
    except ValueError as exc:
        conn.rollback()
        return jsonify({"success": False, "message": str(exc)}), 400
    except Exception as exc:
        conn.rollback()
        return jsonify({"success": False, "message": str(exc)}), 400
    finally:
        conn.close()


@agri_bp.route("/budget-template/<int:template_id>/duplicate", methods=["POST"])
@login_required
def duplicate_budget_template(template_id):
    if not _has_budget_permission("BUDGET_CREATE", "BUDGET_TEMPLATE_MANAGE"):
        return jsonify({"success": False, "message": "Permission denied"}), 403

    conn = create_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT BTPDescription, BTPCropId, BTPIsActive
            FROM agr.BudgetTemplates
            WHERE IdBudgetTemplate = ?
            """,
            (template_id,),
        )
        row = cursor.fetchone()
        if not row:
            return jsonify({"success": False, "message": "Template not found"}), 404

        description_base = f"Copy of {row.BTPDescription}".strip()
        description = description_base
        copy_number = 2
        while _template_description_exists(cursor, description):
            description = f"{description_base} ({copy_number})"
            copy_number += 1
        cursor.execute(
            """
            INSERT INTO agr.BudgetTemplates
            (BTPDescription, BTPCropId, BTPIsActive, BTPCreatedBy, BTPCreatedAt, BTPModifiedBy, BTPModifiedAt)
            VALUES (?, ?, ?, ?, GETDATE(), ?, GETDATE())
            """,
            (description, row.BTPCropId, bool(row.BTPIsActive), current_user.id, current_user.id),
        )
        new_template_id = cursor.execute("SELECT CAST(SCOPE_IDENTITY() AS int)").fetchone()[0]
        cursor.execute(
            """
            INSERT INTO agr.BudgetTemplateLines
            (BTPLinBudgetTemplateId, BTPLinStockId, BTPLinRelationalWeek, BTPLinQuantityPerHa)
            SELECT ?, BTPLinStockId, BTPLinRelationalWeek, BTPLinQuantityPerHa
            FROM agr.BudgetTemplateLines
            WHERE BTPLinBudgetTemplateId = ?
            """,
            (new_template_id, template_id),
        )
        conn.commit()
        return jsonify({"success": True, "template_id": new_template_id})
    except Exception as exc:
        conn.rollback()
        return jsonify({"success": False, "message": str(exc)}), 400
    finally:
        conn.close()


@agri_bp.route("/budget-template/<int:template_id>/toggle-status", methods=["POST"])
@login_required
def toggle_budget_template_status(template_id):
    if not _has_budget_permission("BUDGET_EDIT", "BUDGET_TEMPLATE_MANAGE"):
        return jsonify({"success": False, "message": "Permission denied"}), 403

    conn = create_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            UPDATE agr.BudgetTemplates
            SET BTPIsActive = CASE WHEN BTPIsActive = 1 THEN 0 ELSE 1 END,
                BTPModifiedBy = ?,
                BTPModifiedAt = GETDATE()
            WHERE IdBudgetTemplate = ?
            """,
            (current_user.id, template_id),
        )
        conn.commit()
        return jsonify({"success": True})
    finally:
        conn.close()


@agri_bp.route("/project-budgets")
@login_required
def project_budgets():
    return redirect(url_for("agri.budgets_overview", tab="projects"))


@agri_bp.route("/project-budget/create/<int:project_id>", methods=["GET", "POST"])
@login_required
def create_project_budget(project_id):
    if not _has_budget_permission("BUDGET_CREATE", "BUDGET_TEMPLATE_MANAGE"):
        abort(403)

    projects = list(current_user.projects or [])
    if not projects:
        abort(404)

    conn = create_db_connection()
    cursor = conn.cursor()
    try:
        placeholders = ",".join("?" for _ in projects)
        cursor.execute(
            f"""
            SELECT PRJ.ProjectName, PRJ.ProjectCode, PA.ProjAttrCropId, C.CropDescription,
                   PA.ProjAttrPlantDate, PA.ProjAttrHa, PA.ProjAttrFarmId
            FROM cmn._uvProject PRJ
            LEFT JOIN agr.ProjectAttributes PA ON PA.ProjAttrProjectId = PRJ.ProjectLink
            LEFT JOIN agr.Crop C ON C.IdCrop = PA.ProjAttrCropId
            WHERE PRJ.ProjectLink = ? AND PRJ.MainProjectLink IN ({placeholders})
            """,
            [project_id, *projects],
        )
        project = cursor.fetchone()
        if not project:
            abort(404)
        active_templates = cursor.execute(
            """
            SELECT IdBudgetTemplate, BTPDescription
            FROM agr.BudgetTemplates
            WHERE BTPIsActive = 1 AND BTPCropId = ?
            ORDER BY BTPDescription
            """,
            (project.ProjAttrCropId,),
        ).fetchall()
        existing_budget = cursor.execute(
            "SELECT IdProjectBudget FROM agr.ProjectBudgets WHERE PBProjectId = ?",
            (project_id,),
        ).fetchone()
        if existing_budget:
            return redirect(url_for("agri.edit_project_budget", budget_id=existing_budget.IdProjectBudget))
        if request.method == "POST":
            template_id = request.form.get("template_id")
            if not template_id or not template_id.isdigit():
                abort(400, description="Select an active budget template for this project's crop.")
            selected_template = cursor.execute(
                """
                SELECT IdBudgetTemplate
                FROM agr.BudgetTemplates
                WHERE IdBudgetTemplate = ? AND BTPCropId = ? AND BTPIsActive = 1
                """,
                (int(template_id), project.ProjAttrCropId),
            ).fetchone()
            if not selected_template:
                abort(400, description="The selected template is not active for this project's crop.")
            status = "Active" if request.form.get("is_active", "on") == "on" else "Inactive"
            return _create_project_budget_from_template(
                project_id,
                int(template_id),
                status,
            )

        return render_template(
            "project_budget_create.html",
            project={
                "id": project_id,
                "name": project.ProjectName,
                "code": project.ProjectCode,
                "crop": project.CropDescription or "-",
                "planting_date": _format_date(project.ProjAttrPlantDate),
                "hectares": float(project.ProjAttrHa or 0),
            },
            templates=[{"id": row.IdBudgetTemplate, "description": row.BTPDescription} for row in active_templates],
        )
    finally:
        conn.close()


@agri_bp.route("/project-budget/<int:budget_id>", methods=["GET"])
@login_required
def edit_project_budget(budget_id):
    if not _has_budget_permission("BUDGET_EDIT", "BUDGET_TEMPLATE_MANAGE"):
        abort(403)

    conn = create_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
                 SELECT B.IdProjectBudget, B.PBProjectId, B.PBPlantingDate, B.PBBudgetHa, B.PBStatus,
                     B.PBBudgetTemplateId, T.BTPDescription,
                     PRJ.ProjectName, PRJ.ProjectCode, PA.ProjAttrCropId, PA.ProjAttrPlantDate,
                     PA.ProjAttrHa, C.CropDescription
            FROM agr.ProjectBudgets B
            LEFT JOIN cmn._uvProject PRJ ON PRJ.ProjectLink = B.PBProjectId
            LEFT JOIN agr.ProjectAttributes PA ON PA.ProjAttrProjectId = B.PBProjectId
            LEFT JOIN agr.Crop C ON C.IdCrop = PA.ProjAttrCropId
            LEFT JOIN agr.BudgetTemplates T ON T.IdBudgetTemplate = B.PBBudgetTemplateId
            WHERE B.IdProjectBudget = ?
            """,
            (budget_id,),
        )
        budget = cursor.fetchone()
        if not budget:
            abort(404)
        lines = _fetch_project_budget_lines(conn, budget_id)
        catalog = _fetch_stock_catalog(conn, budget.ProjAttrCropId) if budget.ProjAttrCropId else []
        lines_by_stock = {}
        weeks = continuous_week_range(line["relational_week"] for line in lines)
        for line in lines:
            stock_key = str(line["stock_id"])
            product = lines_by_stock.setdefault(stock_key, {"values": {}, "unit_price": line["unit_price"]})
            product["values"][line["relational_week"]] = line["quantity_per_ha"]
            product["unit_price"] = line["unit_price"]
        products = [
            {
                "stock_id": item["id"],
                "stock_code": item["code"],
                "stock_description": item["description"],
                "unit_price": lines_by_stock.get(str(item["id"]), {}).get("unit_price", item["unit_price"]),
                "values": lines_by_stock.get(str(item["id"]), {}).get("values", {}),
            }
            for item in catalog
        ]
        budget_ha = effective_budget_hectares(budget.PBBudgetHa, budget.ProjAttrHa)
        project_ha = float(budget.ProjAttrHa or 0)
        total_per_ha = sum(
            sum(float(quantity or 0) for quantity in product["values"].values()) * float(product["unit_price"] or 0)
            for product in products
        )
        is_active = str(budget.PBStatus or "Active").strip().lower() not in {"inactive", "0", "false"}
        return render_template(
            "project_budget_editor.html",
            budget={
                "id": budget.IdProjectBudget,
                "project_id": budget.PBProjectId,
                "project_name": budget.ProjectName or budget.ProjectCode or "-",
                "crop": budget.CropDescription or "-",
                "planting_date": _format_date(budget.ProjAttrPlantDate or budget.PBPlantingDate),
                "project_ha": project_ha,
                "budget_ha": budget_ha,
                "is_active": is_active,
                "template": budget.BTPDescription or "-",
            },
            products=products,
            weeks=weeks,
            total_per_ha=total_per_ha,
            total_budget=total_per_ha * budget_ha,
        )
    finally:
        conn.close()


@agri_bp.route("/project-budget/<int:budget_id>/performance")
@login_required
def project_budget_performance(budget_id):
    if not _has_budget_permission("BUDGET_VIEW", "BUDGET_CREATE", "BUDGET_EDIT", "BUDGET_TEMPLATE_MANAGE"):
        abort(403)

    project_groups = list(current_user.projects or [])
    if not project_groups:
        abort(404)

    conn = create_db_connection()
    cursor = conn.cursor()
    try:
        group_placeholders = ",".join("?" for _ in project_groups)
        cursor.execute(
            f"""
            SELECT B.IdProjectBudget, B.PBProjectId, B.PBPlantingDate, B.PBBudgetHa,
                   PRJ.ProjectName, PRJ.ProjectCode,
                     PA.ProjAttrPlantDate, PA.ProjAttrHa, PA.ProjAttrCropId, C.CropDescription
            FROM agr.ProjectBudgets B
            JOIN cmn._uvProject PRJ ON PRJ.ProjectLink = B.PBProjectId
            LEFT JOIN agr.ProjectAttributes PA ON PA.ProjAttrProjectId = B.PBProjectId
            LEFT JOIN agr.Crop C ON C.IdCrop = PA.ProjAttrCropId
            WHERE B.IdProjectBudget = ?
              AND PRJ.MainProjectLink IN ({group_placeholders})
            """,
            [budget_id, *project_groups],
        )
        budget = cursor.fetchone()
        if not budget:
            abort(404)

        budget_ha = effective_budget_hectares(budget.PBBudgetHa, budget.ProjAttrHa)
        project_ha = float(budget.ProjAttrHa or 0)
        cursor.execute(
            """
            SELECT CS.ChemStockLink AS StockLink, CSC.StkCrpType, UOM.cUnitCode AS StockingUnitCode
            FROM agr.ChemStockCrop CSC
            JOIN agr.ChemStock CS ON CS.IdChemStock = CSC.StkCrpChemStockId
            LEFT JOIN cmn._uvUOM UOM ON UOM.idUnits = CS.ChemStockStockingUnitId
            WHERE CSC.StkCrpCropId = ?
            """,
            (budget.ProjAttrCropId,),
        )
        crop_products = cursor.fetchall()
        product_types = {
            row.StockLink: row.StkCrpType or "Unclassified"
            for row in crop_products
        }
        product_units = {
            row.StockLink: row.StockingUnitCode or ""
            for row in crop_products
        }
        cursor.execute(
            """
            SELECT L.PBLinRelationalWeek, L.PBLinWeekStartDate, L.PBLinStockId,
                   L.PBLinQuantityPerHa, L.PBLinBudgetUnitPrice,
                   SI.StockCode, SI.StockDescription
            FROM agr.ProjectBudgetLines L
            LEFT JOIN cmn._uvStockItems SI ON SI.StockLink = L.PBLinStockId
            WHERE L.PBLinProjectBudgetId = ?
            ORDER BY L.PBLinRelationalWeek, SI.StockDescription
            """,
            (budget_id,),
        )
        budget_lines = cursor.fetchall()
        undated_budget_line_count = sum(1 for line in budget_lines if line.PBLinWeekStartDate is None)

        stored_week_starts = {}
        for line in budget_lines:
            if line.PBLinRelationalWeek is not None and line.PBLinWeekStartDate is not None:
                stored_week_starts.setdefault(line.PBLinRelationalWeek, line.PBLinWeekStartDate)
        week_periods = budget_week_periods(stored_week_starts)

        budget_products = {}
        budget_cost_by_week = {period["relational_week"]: 0.0 for period in week_periods}
        weekly_product_data = {period["relational_week"]: {} for period in week_periods}
        budget_total = 0.0
        for line in budget_lines:
            stock_id = line.PBLinStockId
            if stock_id is None:
                continue
            product = budget_products.setdefault(
                stock_id,
                {
                    "stock_id": stock_id,
                    "product_code": line.StockCode or "",
                    "product_description": line.StockDescription or f"Stock {stock_id}",
                    "product_type": product_types.get(stock_id, "Unclassified"),
                    "budget_quantity": 0.0,
                    "budget_cost": 0.0,
                    "weighted_price_total": 0.0,
                    "weighted_price_quantity": 0.0,
                    "fallback_prices": [],
                },
            )
            quantity_per_ha = float(line.PBLinQuantityPerHa or 0)
            unit_price = float(line.PBLinBudgetUnitPrice or 0)
            line_quantity = quantity_per_ha * budget_ha
            line_cost = budget_line_total_cost(quantity_per_ha, budget_ha, unit_price)
            product["budget_quantity"] += line_quantity
            product["budget_cost"] += line_cost
            product["weighted_price_total"] += quantity_per_ha * unit_price
            product["weighted_price_quantity"] += quantity_per_ha
            product["fallback_prices"].append(unit_price)
            budget_total += line_cost
            if line.PBLinRelationalWeek in budget_cost_by_week:
                budget_cost_by_week[line.PBLinRelationalWeek] += line_cost
                weekly_product = weekly_product_data[line.PBLinRelationalWeek].setdefault(
                    stock_id,
                    {
                        "stock_id": stock_id,
                        "product_code": line.StockCode or "",
                        "product_description": line.StockDescription or f"Stock {stock_id}",
                        "stocking_unit_code": product_units.get(stock_id, ""),
                        "budget_quantity": 0.0,
                        "actual_quantity": 0.0,
                        "budget_cost": 0.0,
                        "actual_cost": 0.0,
                    },
                )
                weekly_product["budget_quantity"] += line_quantity
                weekly_product["budget_cost"] += line_cost

        actual_by_product = {}
        actual_by_week = {period["relational_week"]: 0.0 for period in week_periods}
        actual_row_count = 0
        if week_periods:
            values_sql = ", ".join("(CAST(? AS int), CAST(? AS date), CAST(? AS date))" for _ in week_periods)
            week_params = []
            for period in week_periods:
                week_params.extend((
                    period["relational_week"],
                    period["week_start"].isoformat(),
                    period["next_week_start"].isoformat(),
                ))
            cursor.execute(
                f"""
                WITH BudgetWeeks (RelationalWeek, WeekStartDate, NextWeekStartDate) AS (
                    SELECT WeekData.RelationalWeek, WeekData.WeekStartDate, WeekData.NextWeekStartDate
                    FROM (VALUES {values_sql}) AS WeekData(RelationalWeek, WeekStartDate, NextWeekStartDate)
                )
                SELECT BW.RelationalWeek, TX.StockLink,
                       MAX(TX.StockCode) AS StockCode,
                       MAX(TX.Description_1) AS StockDescription,
                       MAX(UOM.cUnitCode) AS StockingUnitCode,
                       SUM(TX.Qty) AS ActualQuantity,
                       SUM(TX.TotalCost) AS ActualCost
                FROM BudgetWeeks BW
                JOIN cmn._uvStockTransactions TX
                  ON TX.TxDate >= BW.WeekStartDate
                 AND TX.TxDate < BW.NextWeekStartDate
                LEFT JOIN agr.ChemStock CS ON CS.ChemStockLink = TX.StockLink
                LEFT JOIN cmn._uvUOM UOM ON UOM.idUnits = CS.ChemStockStockingUnitId
                WHERE TX.ProjectLink = ?
                  AND TX.GroupName IN (?, ?)
                GROUP BY BW.RelationalWeek, TX.StockLink
                """,
                [*week_params, budget.PBProjectId, "Chemicals", "Fertiliser"],
            )
            actual_rows = cursor.fetchall()
            actual_row_count = len(actual_rows)
            for row in actual_rows:
                product = actual_by_product.setdefault(
                    row.StockLink,
                    {
                        "stock_id": row.StockLink,
                        "product_code": row.StockCode or "",
                        "product_description": row.StockDescription or f"Stock {row.StockLink}",
                        "product_type": product_types.get(row.StockLink, "Unclassified"),
                        "actual_quantity": 0.0,
                        "actual_cost": 0.0,
                    },
                )
                actual_quantity = expense_value_from_transaction_sign(row.ActualQuantity)
                actual_cost = expense_value_from_transaction_sign(row.ActualCost)
                product["actual_quantity"] += actual_quantity
                product["actual_cost"] += actual_cost
                actual_by_week[row.RelationalWeek] += actual_cost
                weekly_product = weekly_product_data[row.RelationalWeek].setdefault(
                    row.StockLink,
                    {
                        "stock_id": row.StockLink,
                        "product_code": row.StockCode or "",
                        "product_description": row.StockDescription or f"Stock {row.StockLink}",
                        "stocking_unit_code": row.StockingUnitCode or product_units.get(row.StockLink, ""),
                        "budget_quantity": 0.0,
                        "actual_quantity": 0.0,
                        "budget_cost": 0.0,
                        "actual_cost": 0.0,
                    },
                )
                weekly_product["actual_quantity"] += actual_quantity
                weekly_product["actual_cost"] += actual_cost

        product_ids = set(budget_products) | set(actual_by_product)
        product_comparison = []
        actual_total = 0.0
        for stock_id in product_ids:
            budget_product = budget_products.get(stock_id, {})
            actual_product = actual_by_product.get(stock_id, {})
            budget_quantity = float(budget_product.get("budget_quantity", 0))
            budget_cost = float(budget_product.get("budget_cost", 0))
            actual_quantity = float(actual_product.get("actual_quantity", 0))
            actual_cost = float(actual_product.get("actual_cost", 0))
            weighted_quantity = float(budget_product.get("weighted_price_quantity", 0))
            weighted_price = (
                float(budget_product["weighted_price_total"]) / weighted_quantity
                if weighted_quantity
                else (sum(budget_product.get("fallback_prices", [])) / len(budget_product["fallback_prices"]) if budget_product.get("fallback_prices") else 0.0)
            )
            product_comparison.append(
                {
                    "product_code": budget_product.get("product_code") or actual_product.get("product_code") or "",
                    "product_description": budget_product.get("product_description") or actual_product.get("product_description") or f"Stock {stock_id}",
                    "product_type": budget_product.get("product_type") or actual_product.get("product_type") or "Unclassified",
                    "budget_quantity": budget_quantity,
                    "actual_quantity": actual_quantity,
                    "quantity_difference": budget_quantity - actual_quantity,
                    "budget_unit_price": weighted_price,
                    "budget_cost": budget_cost,
                    "actual_cost": actual_cost,
                    "cost_difference": budget_cost - actual_cost,
                }
            )
            actual_total += actual_cost
        product_comparison.sort(key=lambda product: product["product_description"].lower())
        category_summary_by_type = {}
        for product in product_comparison:
            product_type = product["product_type"]
            summary = category_summary_by_type.setdefault(
                product_type,
                {
                    "product_type": product_type,
                    "product_count": 0,
                    "budget_quantity": 0.0,
                    "actual_quantity": 0.0,
                    "budget_cost": 0.0,
                    "actual_cost": 0.0,
                },
            )
            summary["product_count"] += 1
            summary["budget_quantity"] += product["budget_quantity"]
            summary["actual_quantity"] += product["actual_quantity"]
            summary["budget_cost"] += product["budget_cost"]
            summary["actual_cost"] += product["actual_cost"]
        category_summary = [
            {
                **summary,
                "quantity_difference": summary["budget_quantity"] - summary["actual_quantity"],
                "difference": summary["budget_cost"] - summary["actual_cost"],
            }
            for summary in sorted(category_summary_by_type.values(), key=lambda item: item["product_type"].lower())
        ]

        chart_weeks = [
            {
                "label": f"R{period['relational_week']} · {format_iso_week_label(period['week_start'])}",
                "budget_cost": budget_cost_by_week.get(period["relational_week"], 0.0),
                "actual_cost": actual_by_week.get(period["relational_week"], 0.0),
                "products": [
                    {
                        **product,
                        "quantity_difference": product["budget_quantity"] - product["actual_quantity"],
                    }
                    for product in sorted(
                        weekly_product_data[period["relational_week"]].values(),
                        key=lambda item: item["product_description"].lower(),
                    )
                ],
            }
            for period in week_periods
        ]
        actual_cost_present = actual_row_count > 0
        budget_cost_per_ha = budget_total / budget_ha if budget_ha else 0.0
        return render_template(
            "budget_performance.html",
            project={
                "id": budget.PBProjectId,
                "name": budget.ProjectName or budget.ProjectCode or "-",
                "crop": budget.CropDescription or "-",
                "planting_date": _format_date(budget.ProjAttrPlantDate or budget.PBPlantingDate),
                "project_hectares": project_ha,
                "budget_hectares": budget_ha,
            },
            budget_total=budget_total,
            actual_total=actual_total,
            difference=budget_total - actual_total,
            budget_cost_per_ha=budget_cost_per_ha,
            chart_weeks=chart_weeks,
            category_summary=category_summary,
            products=product_comparison,
            has_actual_costs=actual_cost_present,
            has_budget_periods=bool(week_periods),
            undated_budget_line_count=undated_budget_line_count,
        )
    finally:
        conn.close()


@agri_bp.route("/project-budget/<int:budget_id>/save", methods=["POST"])
@login_required
def save_project_budget(budget_id):
    if not _has_budget_permission("BUDGET_EDIT", "BUDGET_TEMPLATE_MANAGE"):
        return jsonify({"success": False, "message": "Permission denied"}), 403

    payload = request.get_json(silent=True) or {}
    status = "Active" if payload.get("is_active", True) else "Inactive"
    lines = payload.get("lines") or []

    conn = create_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            """
            SELECT B.PBBudgetHa, B.PBPlantingDate, PA.ProjAttrPlantDate, PA.ProjAttrCropId, PA.ProjAttrHa
            FROM agr.ProjectBudgets B
            LEFT JOIN agr.ProjectAttributes PA ON PA.ProjAttrProjectId = B.PBProjectId
            WHERE B.IdProjectBudget = ?
            """,
            (budget_id,),
        )
        budget = cursor.fetchone()
        if not budget:
            abort(404)
        planting_date = budget.ProjAttrPlantDate or budget.PBPlantingDate
        budget_ha = effective_budget_hectares(budget.PBBudgetHa, budget.ProjAttrHa)
        allowed_stock_ids = {
            str(item["id"])
            for item in _fetch_stock_catalog(conn, budget.ProjAttrCropId)
        } if budget.ProjAttrCropId else set()
        validated_lines = []
        for item in lines:
            try:
                stock_id = int(item.get("stock_id"))
                relational_week = int(item.get("relational_week") or 0)
                quantity_value = float(item.get("quantity_per_ha") or 0)
                price_value = float(item.get("unit_price") or 0)
            except (TypeError, ValueError, AttributeError):
                conn.rollback()
                return jsonify({"success": False, "message": "Budget lines contain invalid values."}), 400
            if str(stock_id) not in allowed_stock_ids:
                conn.rollback()
                return jsonify({"success": False, "message": "A product is not linked to this project's crop."}), 400
            if quantity_value < 0 or price_value < 0:
                conn.rollback()
                return jsonify({"success": False, "message": "Quantities and prices cannot be negative."}), 400
            validated_lines.append((stock_id, relational_week, quantity_value, price_value))

        cursor.execute(
            """
            UPDATE agr.ProjectBudgets
            SET PBBudgetHa = ?, PBStatus = ?, PBModifiedBy = ?, PBModifiedAt = GETDATE()
            WHERE IdProjectBudget = ?
            """,
            (budget_ha, status, current_user.id, budget_id),
        )
        cursor.execute("DELETE FROM agr.ProjectBudgetLines WHERE PBLinProjectBudgetId = ?", (budget_id,))
        for stock_id, relational_week, quantity_value, price_value in validated_lines:
            week_start_date = _sql_date_parameter(calculate_week_start(planting_date, relational_week))
            cursor.execute(
                """
                INSERT INTO agr.ProjectBudgetLines
                (PBLinProjectBudgetId, PBLinRelationalWeek, PBLinWeekStartDate, PBLinStockId, PBLinQuantityPerHa, PBLinBudgetUnitPrice)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (budget_id, relational_week, week_start_date, stock_id, quantity_value, price_value),
            )
        conn.commit()
        return jsonify({"success": True, "message": "Budget saved"})
    except Exception as exc:
        conn.rollback()
        return jsonify({"success": False, "message": str(exc)}), 400
    finally:
        conn.close()


@agri_bp.route("/project-budget/<int:budget_id>/delete", methods=["POST"])
@login_required
def delete_project_budget(budget_id):
    if not _has_budget_permission("BUDGET_DELETE", "BUDGET_TEMPLATE_MANAGE"):
        return jsonify({"success": False, "message": "Permission denied"}), 403

    conn = create_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM agr.ProjectBudgetLines WHERE PBLinProjectBudgetId = ?", (budget_id,))
        cursor.execute("DELETE FROM agr.ProjectBudgets WHERE IdProjectBudget = ?", (budget_id,))
        conn.commit()
        return jsonify({"success": True})
    finally:
        conn.close()


def _create_project_budget_from_template(project_id, template_id, status):
    conn = create_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT PBProjectId FROM agr.ProjectBudgets WHERE PBProjectId = ?",
            (project_id,),
        )
        if cursor.fetchone():
            return redirect(url_for("agri.project_budgets"))

        cursor.execute(
            """
            SELECT PRJ.ProjectName, PRJ.ProjectCode, PA.ProjAttrPlantDate, PA.ProjAttrHa
            FROM cmn._uvProject PRJ
            LEFT JOIN agr.ProjectAttributes PA ON PA.ProjAttrProjectId = PRJ.ProjectLink
            WHERE PRJ.ProjectLink = ?
            """,
            (project_id,),
        )
        project = cursor.fetchone()
        planting_date = project.ProjAttrPlantDate or datetime.now().date().isoformat()
        cursor.execute(
            """
            INSERT INTO agr.ProjectBudgets
            (PBProjectId, PBPlantingDate, PBBudgetHa, PBStatus, PBBudgetTemplateId, PBCreatedBy, PBCreatedAt, PBModifiedBy, PBModifiedAt)
            OUTPUT INSERTED.IdProjectBudget
            VALUES (?, ?, ?, ?, ?, ?, GETDATE(), ?, GETDATE())
            """,
            (project_id, planting_date, float(project.ProjAttrHa or 0), status, template_id, current_user.id, current_user.id),
        )
        budget_id = cursor.fetchone()[0]
        template_lines = _fetch_template_lines(conn, template_id)
        for line in template_lines:
            stock_id = line["stock_id"]
            if stock_id in (None, ""):
                continue
            unit_price = _lookup_stock_unit_price(conn, stock_id)
            cursor.execute(
                """
                INSERT INTO agr.ProjectBudgetLines
                (PBLinProjectBudgetId, PBLinRelationalWeek, PBLinWeekStartDate, PBLinStockId, PBLinQuantityPerHa, PBLinBudgetUnitPrice)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    budget_id,
                    line["relational_week"],
                    _sql_date_parameter(calculate_week_start(planting_date, line["relational_week"])),
                    stock_id,
                    line["quantity_per_ha"],
                    unit_price,
                ),
            )
        conn.commit()
        return redirect(url_for("agri.edit_project_budget", budget_id=budget_id))
    except Exception as exc:
        conn.rollback()
        return redirect(url_for("agri.project_budgets"))
    finally:
        conn.close()


def _lookup_stock_unit_price(conn, stock_id):
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT TOP 1 AverageCost, LastGRVCost
        FROM cmn._uvStockCosts
        WHERE StockID = ?
        ORDER BY StockID
        """,
        (stock_id,),
    )
    row = cursor.fetchone()
    if row:
        if row.LastGRVCost is not None:
            return float(row.LastGRVCost)
        if row.AverageCost is not None:
            return float(row.AverageCost)
    return 0.0


@agri_bp.route("/budget-template/<int:template_id>/delete", methods=["POST"])
@login_required
def delete_budget_template(template_id):
    if not _has_budget_permission("BUDGET_DELETE", "BUDGET_TEMPLATE_MANAGE"):
        return jsonify({"success": False, "message": "Permission denied"}), 403

    conn = create_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM agr.BudgetTemplateLines WHERE BTPLinBudgetTemplateId = ?", (template_id,))
        cursor.execute("DELETE FROM agr.BudgetTemplates WHERE IdBudgetTemplate = ?", (template_id,))
        conn.commit()
        return jsonify({"success": True})
    finally:
        conn.close()
