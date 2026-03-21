from flask import render_template, request, redirect, url_for, flash, jsonify, send_file
from flask_login import login_required, current_user
from Core.auth import create_db_connection
from . import agri_bp
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


@agri_bp.route("/spray/<int:spray_id>/instruction_pdf", methods=["GET"])
@login_required
def spray_instruction_pdf(spray_id):
    """Generate spray instruction PDF with operator signature space"""
    
    conn = create_db_connection()
    cur = conn.cursor()

    # Fetch spray header (including user who created the spray instruction)
    cur.execute("""
        SELECT 
            SH.IdSprayH,
            SH.SprayHNo,
            SH.SprayHDescription,
            SH.SprayHDate,
            SH.SprayHApplicationType,
            SH.SprayHRecUserId,
            SM.SprayMethodName,
            SM.SprayMethodTankSize,
            SM.SprayMethodWaterPerHa,
            F.FarmName
        FROM agr.SprayHeader SH
        LEFT JOIN agr.SprayMethod SM ON SM.IdSprayMethod = SH.SprayHMethodId
        LEFT JOIN agr.Farm F ON F.IdFarm = SM.SprayMethodFarmId
        WHERE SH.IdSprayH = ?
    """, spray_id)
    
    header = cur.fetchone()

    if not header:
        conn.close()
        return "Spray instruction not found", 404

    rec_user = None
    rec_user_id = getattr(header, "SprayHRecUserId", None)
    if rec_user_id:
        # adjust user table/name field to your schema
        cur.execute("""
            SELECT UserName
            FROM users.Users
            WHERE Id = ?
        """, rec_user_id)
        row = cur.fetchone()
        rec_user = row.UserName if row else str(rec_user_id)

    # Fetch projects with additional fields
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
    total_ha = sum([p["ha"] for p in project_list])

    # Collect unique values
    plant_dates = set()
    agriculturists = set()
    project_managers = set()
    crops = set()
    varieties = set()
    block_nos = set()
    for p in project_list:
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
            "mix_ha": float(r.SprayMixHa or 0)
        }
        for r in spray_lines
    ]

    # Group lines by mix number
    mixes = {}
    for line in lines_list:
        mix_no = line["mix_number"]
        if mix_no not in mixes:
            mixes[mix_no] = {"lines": [], "water": line["water"], "ha": line["mix_ha"]}
        mixes[mix_no]["lines"].append(line)

    conn.close()

    spray_data = {
        "spray_id": header.IdSprayH,
        "spray_no": header.SprayHNo,
        "description": header.SprayHDescription,
        "date": str(header.SprayHDate),
        "application_type": header.SprayHApplicationType,
        "method_name": header.SprayMethodName,
        "tank_size": header.SprayMethodTankSize,
        "water_per_ha": header.SprayMethodWaterPerHa,
        "farm_name": header.FarmName,
        "projects": project_list,
        "total_ha": total_ha,
        "lines": lines_list,
        "mixes": mixes,
        "unique_plant_dates": sorted(list(plant_dates)),
        "unique_agriculturists": sorted(list(agriculturists)),
        "unique_project_managers": sorted(list(project_managers)),
        "unique_crops": sorted(list(crops)),
        "unique_varieties": sorted(list(varieties)),
        "unique_block_nos": sorted(list(block_nos)),
        "created_by": rec_user or "Unknown"
    }

    assets_root = Path(__file__).resolve().parents[2] / "main_static" / "icons"
    logo_path = assets_root / "LogoIcon.svg"
    print(f"Looking for logo at: {logo_path}")
    if logo_path.exists():
        raw = logo_path.read_bytes()
        logo_data = "data:image/svg+xml;base64," + base64.b64encode(raw).decode("ascii")
        print("Logo found and encoded")
    else:
        logo_data = None

    spray_data["logo_data"] = logo_data

    html = render_template("global_gap/uitdraai.html", spray=spray_data)
    
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        pdf_path = tmp.name
    
    html_to_pdf(html, pdf_path)
    
    return send_file(
        pdf_path,
        mimetype="application/pdf",
        as_attachment=False,
        download_name=f"Spray-{spray_data['spray_no']}-{spray_data['date']}.pdf"
    )