from flask import render_template, request, redirect, url_for, flash, jsonify, send_file
from flask_login import login_required, current_user
from Core.auth import create_db_connection
from ... import agri_bp
import tempfile
import base64
from pathlib import Path
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


@agri_bp.route("/execution/<int:execution_id>/instruction_pdf", methods=["GET"])
@login_required
def execution_instruction_pdf(execution_id):
    """Generate execution instruction PDF with all sprays in the execution"""

    conn = create_db_connection()
    cur = conn.cursor()

    # Fetch batch details
    cur.execute("""
        SELECT EXE.IdSprExec, SprExecDate, EXE.SprExecResponsiblePerson, p.PersonName
        FROM agr.SprayExecution EXE
        LEFT JOIN agr.People p ON p.IdPerson = EXE.SprExecResponsiblePerson
        WHERE EXE.IdSprExec = ?
    """, execution_id)

    execution = cur.fetchone()
    if not execution:
        conn.close()
        return "Execution not found", 404

    # Fetch all spray headers in the execution
    cur.execute("""
        SELECT 
            SH.IdSprayH,
            SH.SprayHNo,
            SH.SprayHDescription,
            SH.SprayHDate,
            SH.SprayLineDoseBasis,
            SH.SprayHCreatedBy,
            SM.SprayMethodName,
            SM.SprayMethodTankSize,
            SM.SprayMethodWaterPerHa,
            F.FarmName
        FROM agr.SprayHeader SH
        LEFT JOIN agr.SprayMethod SM ON SM.IdSprayMethod = SH.SprayHMethodId
        LEFT JOIN agr.Farm F ON F.IdFarm = SM.SprayMethodFarmId
        WHERE SH.SprayHExecutionId = ?
        ORDER BY SH.SprayHDate
    """, execution_id)      
    
    sprays = cur.fetchall()

    execution_data = {
        "execution_id": execution.IdSprExec,
        "execution_date": str(execution.SprExecDate),
        "responsible_person": execution.PersonName,
        "sprays": []
    }

    all_projects = []
    all_mixes = {}
    stock_requirements = {}

    for spray in sprays:
        spray_id = spray.IdSprayH
        
        # Fetch projects for this spray
        cur.execute("""
            SELECT p.ProjectCode, sp.SprayPHa, sp.SprayPWaterPerHa, sp.SprayPPlantDate, sp.SprayPAgriculturist, sp.SprayPProjectManager, c.CropCode, v.VarietyCode, sp.SprayPBlockNo
            FROM agr.SprayProjects sp
            JOIN cmn._uvProject p ON p.ProjectLink = sp.SprayPProjectId
            LEFT JOIN agr.Crop c ON c.IdCrop = sp.SprayPCropId
            LEFT JOIN agr.Variety v ON v.IdVariety = sp.SprayPVarietyId
            WHERE sp.SprayPSprayId = ?
        """, spray_id)
        
        projects = cur.fetchall()
        project_list = [
            {"code": r.ProjectCode, "ha": float(r.SprayPHa or 0), "water_per_ha": float(r.SprayPWaterPerHa or 0), "plant_date": str(r.SprayPPlantDate) if r.SprayPPlantDate else None, "agriculturist": r.SprayPAgriculturist, "project_manager": r.SprayPProjectManager, "crop": r.CropCode, "variety": r.VarietyCode, "block_no": r.SprayPBlockNo}
            for r in projects
        ]
        all_projects.extend(project_list)

        # Fetch spray mix lines
        cur.execute("""
            SELECT 
                LIN.SprayMixLineStockId,
                EVOSTK.StockCode,
                STK.ChemStockActiveIngr,
                STK.ChemStockWitholdingPeriod,
                LIN.SprayMixLineQty,
                UOM.cUnitCode,
                SME.SprayMixNumber,
                SME.SprayMixWater,
                SME.SprayMixHa
            FROM agr.SprayMixLines LIN
            JOIN agr.SprayMix SME ON LIN.SprayMixLineMixId = SME.IdSprayMix
            JOIN cmn._uvStockItems EVOSTK ON EVOSTK.StockLink = LIN.SprayMixLineStockId
            LEFT JOIN agr.ChemStock STK ON STK.IdChemStock = LIN.SprayMixLineStockId
            LEFT JOIN cmn._uvUOM UOM ON UOM.idUnits = LIN.SprayMixLineUoMId
            WHERE SME.SprayMixHeaderId = ?
        """, spray_id)
        
        spray_lines = cur.fetchall()
        lines_list = [
            {
                "code": r.StockCode,
                "ingredient": r.ChemStockActiveIngr,
                "qty": float(r.SprayMixLineQty or 0),
                "uom": r.cUnitCode,
                "withholding_period": r.ChemStockWitholdingPeriod,
                "mix_number": r.SprayMixNumber,
                "water": float(r.SprayMixWater or 0),
                "mix_ha": float(r.SprayMixHa or 0),
                "spray_no": spray.SprayHNo
            }
            for r in spray_lines
        ]

        # Group lines by mix number, but prefix with spray_no
        for line in lines_list:
            mix_key = f"{line['spray_no']}-Mix{line['mix_number']}"
            if mix_key not in all_mixes:
                all_mixes[mix_key] = {"lines": [], "water": line["water"], "ha": line["mix_ha"], "spray_no": line["spray_no"]}
            all_mixes[mix_key]["lines"].append(line)

        spray_data = {
            "spray_id": spray.IdSprayH,
            "spray_no": spray.SprayHNo,
            "description": spray.SprayHDescription,
            "date": str(spray.SprayHDate),
            "dose": spray.SprayLineDoseBasis,
            "method_name": spray.SprayMethodName,
            "tank_size": spray.SprayMethodTankSize,
            "water_per_ha": spray.SprayMethodWaterPerHa,
            "farm_name": spray.FarmName,
            "projects": project_list,
            "lines": lines_list
        }
        execution_data["sprays"].append(spray_data)

    # Fetch stock requirements for all sprays in execution
    cur.execute("""
        SELECT 
            EVOSTK.StockCode,
            STK.ChemStockActiveIngr,
            SUM(REQ.TotalQty) as total_qty,
            UOM.cUnitCode
			--Select *
        FROM agr._uvSprayStockRequirements REQ
        JOIN cmn._uvStockItems EVOSTK ON EVOSTK.StockLink = REQ.StockId
        LEFT JOIN agr.ChemStock STK ON STK.IdChemStock = REQ.StockId
        LEFT JOIN cmn._uvUOM UOM ON UOM.idUnits = REQ.UoMId
        WHERE REQ.SprayId IN (SELECT IdSprayH FROM agr.SprayHeader WHERE SprayHExecutionId = ?)
        GROUP BY EVOSTK.StockCode, STK.ChemStockActiveIngr, UOM.cUnitCode
    """, execution_id)

    stock_reqs = cur.fetchall()
    stock_requirements = [
        {
            "code": r.StockCode,
            "ingredient": r.ChemStockActiveIngr,
            "min_qty": float(r.total_qty or 0),
            "uom": r.cUnitCode
        }
        for r in stock_reqs
    ]

    conn.close()

    # Aggregate unique values
    plant_dates = set()
    agriculturists = set()
    project_managers = set()
    crops = set()
    varieties = set()
    block_nos = set()
    for p in all_projects:
        if p["plant_date"]:
            plant_dates.add(p["plant_date"])
        if p["agriculturist"]:
            agriculturists.add(p["agriculturist"])
        if p["project_manager"]:
            project_managers.add(p["project_manager"])
        if p["crop"]:
            crops.add(p["crop"])
        if p["variety"]:
            varieties.add(p["variety"])
        if p["block_no"]:
            block_nos.add(p["block_no"])

    execution_data.update({
        "projects": all_projects,
        "total_ha": sum(p["ha"] for p in all_projects),
        "mixes": all_mixes,
        "stock_requirements": stock_requirements,
        "unique_plant_dates": sorted(list(plant_dates)),
        "unique_agriculturists": sorted(list(agriculturists)),
        "unique_project_managers": sorted(list(project_managers)),
        "unique_crops": sorted(list(crops)),
        "unique_varieties": sorted(list(varieties)),
        "unique_block_nos": sorted(list(block_nos)),
        "created_by": current_user.username if hasattr(current_user, 'username') else str(current_user.id)
    })

    assets_root = Path(__file__).resolve().parents[2] / "main_static" / "icons"
    logo_path = assets_root / "LogoIcon.svg"
    if logo_path.exists():
        raw = logo_path.read_bytes()
        logo_data = "data:image/svg+xml;base64," + base64.b64encode(raw).decode("ascii")
    else:
        logo_data = None

    execution_data["logo_data"] = logo_data

    template_css_path = Path(__file__).resolve().parents[3] / "static" / "color-template.css"
    color_css = template_css_path.read_text(encoding="utf-8")
    html = render_template(
        "global_gap/uitdraai/spray_execution_instruction.html",
        execution=execution_data,
        color_css=color_css
    )

    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        pdf_path = tmp.name
    
    html_to_pdf(html, pdf_path)
    
    return send_file(
        pdf_path,
        mimetype="application/pdf",
        as_attachment=False,
        download_name=f"Execution-{execution_id}-{execution_data['execution_date']}.pdf"
    )
