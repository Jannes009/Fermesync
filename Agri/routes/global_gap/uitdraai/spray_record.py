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
            HEA.SprayHOperator,
			EXE.SprExecResponsiblePerson,
			PEA.PersonName,
            HEA.SprayHWeather,
            HEA.SprayHApplicationType,
            HEA.SprayHMethodId,
            SM.SprayMethodName,
            SM.SprayMethodTankSize
        FROM agr.SprayHeader HEA
        LEFT JOIN agr.SprayMethod SM ON SM.IdSprayMethod = HEA.SprayHMethodId
		JOIN agr.SprayExecution EXE on EXE.IdSprExec = Hea.SprayHExecutionId
		JOIN agr.People PEA on PEA.IdPerson = SprExecResponsiblePerson
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
            c.CropCode,
            c.CropGrowerCode,
            v.VarietyCode,
            sp.SprayPBlockNo
        FROM agr.SprayProjects sp
        JOIN cmn._uvProject p ON p.ProjectLink = sp.SprayPProjectId
        LEFT JOIN agr.Crop c ON c.IdCrop = sp.SprayPCropId
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
            "crop": row.CropCode,
            "grower_code": row.CropGrowerCode,
            "variety": row.VarietyCode,
            "block_no": row.SprayPBlockNo
        }
        for row in cur.fetchall()
    ]

    cur.execute("""
    Select 
        IssLinProjSprayId
        ,StockDescription
        
        ,ChemStockActiveIngr
		,ChemStockReason
		,ChemStockWitholdingPeriod
		,CLr.ChemColCode
        ,IssLineStockLink
        ,Sum(LIN.SprayLineTotalQty) QtyRecommended
        ,SUM(IssLinProjWeight*IssLineQtyFinalised) Finalised,
        cUnitCode
        --Select *
    from [agr].[SprayHeader] HEA
	JOIN [agr].[SprayLines] LIN on LIN.SprayLineHeaderId = HEA.IdSprayH
	LEFT JOIN stk.IssueLineProjects WT on Wt.IssLinProjSprayId = HEA.IdSprayH
    LEFT JOIN  stk.IssueLines ISSLIN on ISSLIN.IdIssLine = WT.IssLinProjLineId
    JOIN cmn._uvStockItems EVOSTK ON EVOSTK.StockLink = LIN.SprayLineStkId
    LEFT JOIN agr.ChemStock STK ON STK.IdChemStock = LIN.SprayLineStkId
	LEFT JOIN [agr].[ChemColour] CLR on CLR.IdChemCol = STK.ChemStockColourCodeId
    LEFT JOIN cmn._uvUOM UOM ON UOM.idUnits = ISSLIN.IssLineUoMId
    WHERE WT.IssLinProjSprayId = ?
    GROUP BY IssLinProjSprayId	,IssLineStockLink ,StockDescription,
    ChemStockActiveIngr, cUnitCode ,ChemStockReason
	,ChemStockWitholdingPeriod ,CLr.ChemColCode
    """, instruction_id)

    stock_requirements = [
        {
            "description": row.StockDescription,
            "ingredient": row.ChemStockActiveIngr,
            "reason": row.ChemStockReason,
            "withholding_period": row.ChemStockWitholdingPeriod,
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
        "instruction_description": header.SprayHDescription,
        "application_type": header.SprayHApplicationType,
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


