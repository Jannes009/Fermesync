from flask import render_template, request, redirect, url_for, flash, jsonify, send_file
from flask_login import login_required, current_user
from Core.auth import create_db_connection
from ... import agri_bp
import tempfile
import base64
from pathlib import Path
from datetime import datetime
from playwright.sync_api import sync_playwright

def html_to_pdf(html: str, output_path: str):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        page.set_content(
            html,
            wait_until="networkidle"
        )

        page.pdf(
            path=output_path,
            format="A4",
            print_background=True,
            margin={
                "top": "5mm",
                "right": "5mm",
                "bottom": "20mm",
                "left": "5mm"
            }
        )

        browser.close()


def fetch_spray_record_data(instruction_id):
    conn = create_db_connection()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            HEA.SprayHNo,
            HEA.SprayHDescription,
            HEA.SprayHDate,
            HEA.SprayHStartDateTime, HEA.SprayHEndDateTime,
			EXE.SprExecResponsiblePerson,
            HEA.SprayHScouting,
			PEA.PersonName,
            HEA.SprayHWeather,
            HEA.SprayLineDoseBasis,
            HEA.SprayHMethodId,
            SM.SprayMethodName,
            SM.SprayMethodTankSize
            , HEA.SprayHCropId, HC.CropCode AS SprayHCropCode, HC.CropGrowerCode AS SprayHCropGrowerCode
        FROM agr.SprayHeader HEA
        LEFT JOIN agr.SprayMethod SM ON SM.IdSprayMethod = HEA.SprayHMethodId
        JOIN agr.SprayExecution EXE on EXE.IdSprExec = HEA.SprayHExecutionId
        JOIN agr.People PEA on PEA.IdPerson = EXE.SprExecResponsiblePerson

        LEFT JOIN agr.Crop HC on HC.IdCrop = HEA.SprayHCropId
        WHERE HEA.IdSprayH = ?
    """, instruction_id)

    header = cur.fetchone()
    if not header:
        conn.close()
        return None

    cur.execute("""
        SELECT
            p.ProjectCode,
            ISNULL(sp.SprayPHa, 0) AS SprayPHa,
            ISNULL(sp.SprayPWaterPerHa, 0) AS SprayPWaterPerHa,
            sp.SprayPPlantDate,
            sp.SprayPAgriculturist,
            sp.SprayPProjectManager,
            v.VarietyCode,
            sp.SprayPBlockNo
        FROM agr.SprayProjects sp
        JOIN cmn._uvProject p ON p.ProjectLink = sp.SprayPProjectId
        LEFT JOIN agr.Variety v ON v.IdVariety = sp.SprayPVarietyId
        WHERE sp.SprayPSprayId = ?
    """, instruction_id)

    projects = [
        {
            "code": row.ProjectCode,
            "ha": float(row.SprayPHa or 0),
            "water_per_ha": float(row.SprayPWaterPerHa or 0),
            "plant_date": row.SprayPPlantDate.date().isoformat() if isinstance(row.SprayPPlantDate, datetime) else str(row.SprayPPlantDate) if row.SprayPPlantDate else None,
            "agriculturist": row.SprayPAgriculturist,
            "project_manager": row.SprayPProjectManager,
            "variety": row.VarietyCode,
            "block_no": row.SprayPBlockNo
        }
        for row in cur.fetchall()
    ]

    cur.execute("""
    Select 
    IssLinProjSprayId
    ,StockDescription      
    ,ACT.ChemActIngredient
    ,LIN.SprayLineFunction
    ,Lin.SprayLineWitholdingPeriod
    ,CLr.ChemColCode
    ,IssLineStockLink
    ,Sum(LIN.SprayLineTotalQty) QtyRecommended
    ,ProjectQty Finalised,
    cUnitCode
    --Select *
    from [agr].[SprayHeader] HEA
    JOIN [agr].[SprayLines] LIN on LIN.SprayLineHeaderId = HEA.IdSprayH
    LEFT JOIN (
        Select 
        IssLinProjSprayId, IssLineStockLink--, IssLineQtyFinalised,IssLinProjWeight
        ,SUM(IssLineQtyFinalised*IssLinProjWeight) ProjectQty
        from  stk.IssueLineProjects WT 
        JOIN stk.IssueLines ISSLIN on ISSLIN.IdIssLine = WT.IssLinProjLineId
        GROUP BY IssLinProjSprayId, IssLineStockLink
	)ISSQTY on ISSQTY.IssLinProjSprayId = HEA.IdSprayH and ISSQTY.IssLineStockLink = LIN.SprayLineStkId
    JOIN cmn._uvStockItems EVOSTK ON EVOSTK.StockLink = LIN.SprayLineStkId
    LEFT JOIN agr.ChemStock STK ON STK.ChemStockLink = LIN.SprayLineStkId
    LEFT JOIN agr.ChemActiveIngredient ACT on ACT.IdChemAct = stk.ChemStockActiveIngrId
    LEFT JOIN [agr].[ChemColour] CLR on CLR.IdChemCol = STK.ChemStockColourCodeId
    LEFT JOIN cmn._uvUOM UOM ON UOM.idUnits = LIN.SprayLineUoMId
    WHERE HEA.IdSprayH = ?
    GROUP BY IssLinProjSprayId ,StockDescription ,ACT.ChemActIngredient
    ,LIN.SprayLineFunction ,Lin.SprayLineWitholdingPeriod ,CLr.ChemColCode
    ,IssLineStockLink ,cUnitCode, ProjectQty
    """, instruction_id)

    stock_requirements = [
        {
            "description": row.StockDescription,
            "ingredient": row.ChemActIngredient,
            "reason": row.SprayLineFunction,
            "withholding_period": row.SprayLineWitholdingPeriod,
            "colour_code": row.ChemColCode,
            "recommended_qty": float(row.QtyRecommended or 0),
            "finalised_qty": float(row.Finalised or 0),
            "uom": row.cUnitCode
        }
        for row in cur.fetchall()
    ]

    conn.close()

    total_ha = sum(item["ha"] for item in projects)

    assets_root = Path(__file__).resolve().parents[4] / "main_static" / "icons"
    logo_path = assets_root / "LogoIcon.svg"
    logo_data = None
    if logo_path.exists():
        raw = logo_path.read_bytes()
        logo_data = "data:image/svg+xml;base64," + base64.b64encode(raw).decode("ascii")

    return {
        "instruction_id": header.SprayHNo or instruction_id,
        "recommended_date": str(header.SprayHDate) if header.SprayHDate else None,
        "start_datetime": str(header.SprayHStartDateTime) if header.SprayHStartDateTime else None,
        "end_datetime": str(header.SprayHEndDateTime) if header.SprayHEndDateTime else None,
        "responsible_person": header.PersonName or "",
        "crop": header.SprayHCropCode if hasattr(header, 'SprayHCropCode') else None,
        "instruction_description": header.SprayHDescription,
        "dose_basis": header.SprayLineDoseBasis,
        "scouting": header.SprayHScouting or "",
        "method_name": header.SprayMethodName,
        "method_tank_size": header.SprayMethodTankSize,
        "weather": header.SprayHWeather,
        "projects": projects,
        "total_ha": total_ha,
        "stock_requirements": stock_requirements,
        "created_by": getattr(current_user, "username", str(getattr(current_user, "id", "unknown"))),
        "logo_data": logo_data
    }


@agri_bp.route("/instruction/<int:instruction_id>/instruction_pdf", methods=["GET"])
@login_required
def print_instruction(instruction_id):
    instruction = fetch_spray_record_data(instruction_id)
    if not instruction:
        return "Instruction not found", 404

    html = render_template(
        "global_gap/uitdraai/spray_record.html",
        instruction=instruction
    )

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        pdf_path = tmp.name

    html_to_pdf(html, pdf_path)

    return send_file(
        pdf_path,
        mimetype="application/pdf",
        as_attachment=False,
        download_name=f"SprayRecord-{instruction['instruction_id']}.pdf"
    )


