import sys
from flask import request, jsonify, render_template, abort
import clr  # pythonnet
from Inventory.routes import inventory_bp
from Inventory.db import create_db_connection
from flask_login import login_required, current_user

# Add the path to your Evolution DLLs
sys.path.append(r"C:\Program Files (x86)\Sage Evolution")

# Load Evolution DLLs
clr.AddReference("Pastel.Evolution.Common")
clr.AddReference("Pastel.Evolution")
import Pastel.Evolution as evo

@inventory_bp.route("/SDK/stock_issue", methods=["GET"])
@login_required
def stock_issue():
    # permission check (optional)
    if "StockIssue" in current_user.permissions:
        return render_template('EvolutionSDK/stock_issue.html')
    else:
        abort(403)

# -------------------------
# Fetch warehouses (path matches frontend)
# -------------------------
@inventory_bp.route("/SDK/fetch_warehouses") 
def fetch_warehouses(): 
    conn = create_db_connection() 
    cursor = conn.cursor() 
    query = f""" 
    Select WhseLink, WhseCode, WhseDescription
    from [_uvWarehouses] 
    WHERE WhseLink IN ({','.join(['?'] * len(current_user.warehouses))}) 
    """ 
    cursor.execute(query, current_user.warehouses)
    warehouses = [ 
        {"id": row[0], "code": row[1], "name": row[2]} 
        for row in cursor.fetchall() ] 
    conn.close() 
    return jsonify({"warehouses": warehouses})

# -------------------------
# Fetch projects (match frontend path)
# -------------------------
@inventory_bp.route("/fetch_projects", methods=["POST"])
@login_required
def fetch_projects():
    conn = create_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT ProjectLink, ProjectName FROM _uvProject")
    rows = cursor.fetchall()
    conn.close()

    projects_list = [
        {"id": row[0], "name": row[1]}
        for row in rows
    ]
    return jsonify({"prod_projects": projects_list})

# -------------------------
# Fetch products in warehouse (route name matches frontend)
# -------------------------
@inventory_bp.route("/fetch_products_in_whse", methods=["POST"])
@login_required
def fetch_products_in_whse():
    whse_link = request.json.get("whse_link")
    if not whse_link:
        return jsonify({"products": []})

    conn = create_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT StockLink, StockCode, StockDescription, QtyOnHand, StockingUnitId, StockingUnitCode
        FROM _uvInventoryQty 
        WHERE QtyOnHand > 0 AND WhseLink = ?
    """, (whse_link,))
    rows = cursor.fetchall()
    conn.close()

    products_list = [
        {
            "product_link": row[0],
            "product_code": row[1],
            "product_desc": row[2],
            "qty_in_whse": row[3],
            "uom_id": row[4],
            "uom_code": row[5],
        }
        for row in rows
    ]
    return jsonify({"products": products_list})

# -------------------------
# Fetch product by barcode (returns product_code + product_link if available in whse)
# -------------------------
@inventory_bp.route("/SDK/fetch_product_by_barcode", methods=["POST"])
@login_required
def fetch_product_by_barcode():
    barcode = request.json.get("barcode")
    whse_link = request.json.get("whse_link", None)  # optional

    if not barcode:
        return jsonify({}), 400

    conn = create_db_connection()
    cursor = conn.cursor()

    # First find the StockCode from barcodes table
    cursor.execute("SELECT StockCode, UOMID, cUnitCode FROM _uvProductBarcodes WHERE Barcode = ?", (barcode,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return jsonify({})  # not found

    stock_code = row[0]
    uom_id = row[1]
    uom_code = row[2]

    # Try to find StockLink for that StockCode in the requested warehouse (if provided),
    # otherwise return any stocklink for that code.
    if whse_link:
        cursor.execute("""
            SELECT TOP 1 StockLink
            FROM _uvInventoryQty
            WHERE StockCode = ? AND WhseLink = ?
        """, (stock_code, whse_link))
        inv_row = cursor.fetchone()
    else:
        cursor.execute("""
            SELECT TOP 1 StockLink
            FROM _uvInventoryQty
            WHERE StockCode = ?
        """, (stock_code,))
        inv_row = cursor.fetchone()

    product_link = inv_row[0] if inv_row else None
    conn.close()

    return jsonify({
        "product_code": stock_code,
        "product_link": product_link,
        "uom_id": uom_id,
        "uom_code": uom_code
    })

# -------------------------
# Create stock issue (fixed SQL inserts, SCOPE_IDENTITY usage)
# -------------------------
@inventory_bp.route("/SDK/create_stock_issue", methods=["POST"])
@login_required
def create_stock_issue():
    if "StockIssue" not in current_user.permissions:
        abort(403)  # Forbidden
    data = request.json
    if not data:
        return jsonify({"status": "error", "message": "No data provided"}), 400

    warehouse_code = data.get("warehouse")
    project_code = data.get("project")
    issued_to = data.get("issued_to")
    order_final = data.get("order_final", False)
    lines_payload = data.get("lines", [])
    submission_lines = []

    if not warehouse_code or not project_code or not issued_to or not lines_payload:
        return jsonify({"status": "error", "message": "Missing required data"}), 400

    conn = create_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
    INSERT INTO IssueHeader( 
    IssueWhseId, IssueProjectId, IssueByUserId, IssueToName, [IssueTimeStamp]) 
    VALUES (?, ?, ?, ?, GETDATE()) """, 
    (warehouse_code, project_code, current_user.id, issued_to))
            # Now get the SCOPE_IDENTITY() in a separate query
    cursor.execute("""
    Select MAX([IssueId]) [IssueId]
    from [dbo].[IssueHeader] HEA
    WHERE NOT EXISTS (Select * from IssueLines LIN where LIN.IssLineHeaderId = HEA.IssueId)
        """)
    stock_issue_id = cursor.fetchone()[0] 

    # If order is final, mark header final now
    if order_final:
        cursor.execute("""
            UPDATE IssueHeader
            SET IssueFinalised = 1, IssueFinalisedByUserId = ?, IssueFinalisedTimeStamp = GETDATE()
            WHERE IssueId = ?
        """, (current_user.id, stock_issue_id))

    # Insert each line (six columns -> six placeholders)
    for line in lines_payload:
        cursor.execute("""
            INSERT INTO IssueLines(
                IssLineHeaderId, IssLineStockLink, IssLineStockCode, IssLineQtyIssued, IssLineUOMId, IssLineUOMCode
            )
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            stock_issue_id,
            line.get("product_link"),
            line.get("product_code"),
            line.get("qty_to_issue"),
            line.get("uom_id"),
            line.get("uom_code"),
        ))
        # If final, set IssLineQtyFinalised for that newly-inserted line
        if order_final:
            cursor.execute("SELECT MAX(IssLineId) FROM IssueLines")
            last_line_id = cursor.fetchone()[0]
            cursor.execute("""
                UPDATE IssueLines
                SET IssLineQtyFinalised = ?
                WHERE IssLineId = ?
            """, (line.get("qty_to_issue"), last_line_id))
            submission_line = {
                "line_id": last_line_id,
                "product_link": line.get("product_link"),
                "finalised_qty": line.get("qty_to_issue")
            }
            submission_lines.append(submission_line)

    conn.commit()

    # If order_final we can attempt to submit to Evolution in the background call;
    # keep it synchronous here for simplicity. If submit_stock_issue raises, log it but do not fail DB insert.
    if order_final:
        try:
            order_number = submit_stock_issue(warehouse_code, project_code, submission_lines, issued_to)
            cursor.execute("""
                UPDATE IssueHeader
                SET IssueInvoiceNo = ?
                WHERE IssueId = ?
            """, (order_number, stock_issue_id))
            conn.commit()
        except Exception as ex:
            # Log and continue. The DB already has the header/lines and finalised flags.
            print("submit_stock_issue failed:", ex)

    return jsonify({"status": "success", "message": "Stock issue created.", "issue_id": stock_issue_id}), 200

    # except Exception as ex:
    #     conn.rollback()
    #     print("Stock Issue Error:", str(ex))
    #     return jsonify({"status": "error", "message": "Stock Issue Error: " + str(ex)}), 500
    # finally:
    #     conn.close()


def submit_stock_issue(warehouse_code, project_code, lines, issued_to, returned_to=None):
    """
    Submits the issue to Evolution as a SalesOrder. This function should
    raise exceptions on failure (caller handles logging).
    NOTE: we rely on product_link being the Evolution InventoryItem identifier (StockLink).
    """
    # -------------------------
    # Connect to Evolution
    # -------------------------
    conn = None
    cursor = None
    description = f"{issued_to}, {returned_to}" if returned_to else f"{issued_to}"
    try:
        evo.DatabaseContext.CreateCommonDBConnection(
            "SIGMAFIN-RDS\\EVOLUTION", "SageCommon", "sa", "@Evolution", False
        )
        evo.DatabaseContext.SetLicense("DE12111082", "9824607")
        evo.DatabaseContext.CreateConnection(
            "SIGMAFIN-RDS\\EVOLUTION", "UB_UITDRAAI_BDY", "sa", "@Evolution", False
        )

        # -------------------------
        # Create Sales Order (Stock Issue)
        # -------------------------
        SO = evo.SalesOrder()
        SO.Customer = evo.Customer("ZZZ001")  # Always the same customer
        SO.Project = evo.Project(project_code)  # From frontend
        SO.Description = description

        conn = create_db_connection()
        cursor = conn.cursor()

        # Add each line (use product_link as the inventory key)
        for line in lines:
            OD = evo.OrderDetail()
            SO.Detail.Add(OD)

            # fetch product code from product_link
            cursor.execute("""
                SELECT StockCode FROM _uvStockItems WHERE StockLink = ?
            """, (line.get("product_link"),))
            stock_code = cursor.fetchone()[0]
            # product_link expected to be usable by Evolution InventoryItem constructor
            OD.InventoryItem = evo.InventoryItem(stock_code)
            OD.Quantity = float(line.get("finalised_qty") or 0)
            OD.Warehouse = evo.Warehouse(warehouse_code)

        # Complete the Sales Order
        SO.Complete()
        order_number = SO.OrderNo


        return order_number
    except Exception as ex:
        print("Stock Issue Submission Error:", str(ex))
        raise ex
    finally:
        try:
            if cursor:
                cursor.close()
        except Exception:
            pass
        try:
            if conn:
                conn.close()
        except Exception:
            pass

@inventory_bp.route("/SDK/incomplete_issues", methods=["GET"])
def incomplete_issues():
    conn = create_db_connection()
    cur = conn.cursor()

    sql = """
        SELECT Distinct IssueId, IssueTimeStamp, ProjectName, IssueToName
        FROM [dbo].[_uvStockIssue]
        WHERE IssueFinalised = 0
        ORDER BY IssueId, IssueTimeStamp, ProjectName, IssueToName
    """

    cur.execute(sql)
    rows = cur.fetchall()

    # build grouped structure: one issue → many lines
    issues = [{
        "IssueId": r.IssueId,
        "IssueTimeStamp": r.IssueTimeStamp,
        "ProjectName": r.ProjectName,
        "IssueToName": r.IssueToName,
        "lines": []
    } for r in rows
    ]

    return jsonify({"issues": issues})


@inventory_bp.route("/fetch_products_for_return", methods=["POST"])
def fetch_products_for_return():
    if "StockIssue" not in current_user.permissions:
        abort(403)  # Forbidden
    data = request.json
    issue_id = data.get("issue_id")

    results = []
    conn = None
    cursor = None

    try:
        conn = create_db_connection()
        if conn is None:
            return jsonify([]), 500

        cursor = conn.cursor()
        cursor.execute("""  
            Select IssLineId, IssLineStockLink, StockDescription, 
                   IssLineUOMID, ISSLineUOMCode, ISSLineQtyIssued 
            from [_uvStockIssue]
            where IssueId = ?
        """, (issue_id,))

        rows = cursor.fetchall()
        results = [{
            "line_id": r.IssLineId,
            "stock_link": r.IssLineStockLink,
            "stock_description": r.StockDescription,
            "uom_id": r.IssLineUOMID,
            "uom_code": r.ISSLineUOMCode,
            "qty_issued": r.ISSLineQtyIssued
        } for r in rows]
    except Exception as e:
        print("fetch_products_for_return error:", e)
    finally:
        if cursor:
            try:
                cursor.close()
            except Exception:
                pass
        if conn:
            try:
                conn.close()
            except Exception:
                pass

    return jsonify(results)


@inventory_bp.route("/process_return", methods=["POST"])
@login_required
def process_return():
    data = request.json
    issue_id = data.get("issue_id")
    returned_to = data.get("returned_to")
    lines = data.get("returns") or []
    submission_lines = []

    conn = None
    cursor = None

    try:
        conn = create_db_connection()
        if conn is None:
            return jsonify({"success": False, "message": "Database connection could not be established."}), 500

        cursor = conn.cursor()

        cursor.execute("""
            Update IssueHeader
            SET IssueReturnedToName = ?, IssueFinalised = 1, 
                IssueFinalisedByUserId = ?, IssueFinalisedTimeStamp = GETDATE()
            WHERE IssueId = ?
        """, (returned_to, current_user.id, issue_id))
        for line in lines:
            qty_finalised = line.get("qty_issued") - line.get("qty_returned")
            # fetch stock link for submission
            cursor.execute("""
                Select IssLineStockLink
                from IssueLines
                where IssLineId = ?
            """, (line.get("line_id"),))
            stock_link_row = cursor.fetchone()
            if not stock_link_row:
                raise Exception(f"No stock link found for line {line.get('line_id')}")

            stock_link = stock_link_row[0]

            submission_lines.append({
                "line_id": line.get("line_id"),
                "product_link": stock_link,
                "finalised_qty": qty_finalised
            })

            cursor.execute("""
                UPDATE IssueLines
                SET IssLineQtyReceived = ?, IssLineQtyFinalised = ?
                WHERE IssLineId = ?
            """, (line.get("qty_returned"), qty_finalised, line.get("line_id")))
        # get Issue details
        cursor.execute("""
            Select IssueWhseId, IssueProjectId, IssueReturnedToName, IssueToName
            from IssueHeader
            where IssueId = ?
        """, (issue_id,))
        issue = cursor.fetchone()
        if not issue:
            raise Exception(f"Issue {issue_id} not found.")

        order_number = submit_stock_issue(issue.IssueWhseId, issue.IssueProjectId, submission_lines, issue.IssueToName, issue.IssueReturnedToName)
        cursor.execute("""
            UPDATE IssueHeader
            SET IssueInvoiceNo = ?
            WHERE IssueId = ?
        """, (order_number, issue_id))

        conn.commit()
        return jsonify({"success": True, "order_number": order_number})

    except Exception as e:
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
        return jsonify({"success": False, "message": str(e)})
    
    finally:
        if cursor:
            try:
                cursor.close()
            except Exception:
                pass
        if conn:
            try:
                conn.close()
            except Exception:
                pass

