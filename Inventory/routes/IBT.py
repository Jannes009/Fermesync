from flask import request, jsonify, render_template, abort
from . import inventory_bp
from Core.auth import create_db_connection, close_db_connection
from flask_login import login_required, current_user
from Instance.local_settings import DEFAULT_TRANSFER_PROJECT_ID
from System import DateTime

from Core.sdk_connection import EvolutionConnection, EvolutionAgentNotFoundError, EvolutionConnectionError
import Pastel.Evolution as Evo

@inventory_bp.route('/SDK/IBT_issue', methods=['GET'])
@login_required
def IBT_issue():
    _require_requisition_access()
    return render_template('EvolutionSDK/IBT_create.html')


@inventory_bp.route("/SDK/fetch_all_warehouses") 
@login_required
def fetch_all_warehouses():
    _require_ibt_visibility()
    try:
        conn = create_db_connection() 
        cursor = conn.cursor() 
        query = f""" 
        Select WhseLink, WhseCode, WhseDescription
        from cmn.[_uvWarehouses] 
        """ 
        cursor.execute(query) 
        warehouses = [ 
            {"id": row[0], "code": row[1], "name": row[2]} 
            for row in cursor.fetchall() ] 
        conn.close() 
        return jsonify({"success": True, "warehouses": warehouses})
    except Exception as e:
        print("Error fetching warehouses:", str(e))
        return jsonify({"success": False, "message": str(e)}), 500

@inventory_bp.route("/fetch_whses_with_same_type", methods=["GET"])
@login_required
def fetch_whses_with_same_type():
    _require_requisition_access()
    whse_id = request.args.get("whse_id")
    try:
        conn = create_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
        SELECT WhseLink, WhseCode, WhseDescription
        FROM cmn.[_uvWarehouses] WHSE
        JOIN [agr].[WarehouseAttributes] 
            ATTR on ATTR.WhAttrWhseId = WHSE.WhseLink
            AND ATTR.WhAttrWhseType = (Select TOP 1 WhAttrWhseType from [agr].[WarehouseAttributes] where WhAttrWhseId = ?)
        """, (whse_id,))

        warehouses = [
            {"id": row.WhseLink, "code": row.WhseCode, "name": row.WhseDescription}
            for row in cursor.fetchall()
        ]
        conn.close()

        return jsonify({"success": True, "warehouses": warehouses})
    except Exception as e:
        print("Error fetching warehouses with same type:", str(e))
        return jsonify({"success": False, "message": str(e)}), 500

@inventory_bp.route("/fetch_products_in_both_whses", methods=["POST"])
@login_required
def fetch_products_in_both_whses():
    _require_requisition_access()
    whse_from_id = request.json.get("whse_from_id")
    whse_to_id = request.json.get("whse_to_id")
    try:
        print(whse_from_id, whse_to_id)
        conn = create_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
        SELECT FROMQTY.StockLink FromStockLink,
            FROMQTY.StockDescription,
            FROMQTY.QtyOnHand / CONV.ConversionFactor PurchaseQtyOnHand,
            FROMQTY.PurchaseUnitId,
            FROMQTY.PurchaseUnitCode,
            CONV.iUOMStockingUnitID,
            CONV.StockingUnitCode,
            CONV.ConversionFactor
        FROM [stk]._uvInventoryQty FROMQTY
        JOIN [cmn].[_uvStockUnitConversion] CONV on CONV.StockLink = FROMQTY.StockLink
        WHERE EXISTS(
            SELECT StockLink ToStockLink
            FROM [stk]._uvInventoryQty TOQTY
            WHERE TOQTY.WhseLink = ? AND TOQTY.StockLink = FROMQTY.StockLink
        )
        AND FROMQTY.WhseLink = ? AND FROMQTY.ItemActive = 1
        Order by FROMQTY.StockDescription
        """, (whse_to_id, whse_from_id,))

        rows = cursor.fetchall()
        conn.close()

        products_list = [
            {
                "product_id": row.FromStockLink,
                "product_desc": row.StockDescription,
                "qty_in_whse": row.PurchaseQtyOnHand,
                "purchasing_unit_id": row.PurchaseUnitId,
                "purchasing_unit_code": row.PurchaseUnitCode,
                "stocking_unit_id": row.iUOMStockingUnitID,
                "stocking_unit_code": row.StockingUnitCode,
                "conversion_factor": row.ConversionFactor
            }
            for row in rows
        ]
        return jsonify({"success": True, "products": products_list})
    except Exception as e:
        print("Error fetching products in both warehouses:", str(e))
        return jsonify({"success": False, "message": str(e)}), 500

IBT_STATUSES = {"REQUESTED", "APPROVED", "ISSUED", "RECEIVED", "REJECTED"}


def _has_permission(permission):
    return permission in (current_user.permissions or [])


def _require_permission(permission):
    if not _has_permission(permission):
        abort(403)


def _require_ibt_visibility():
    if not any(_has_permission(permission) for permission in ('IBT_VIEW', 'IBT_REQUEST', 'IBT_APPROVE', 'IBT_REJECT', 'IBT_ISSUE', 'IBT_RECEIVE')):
        abort(403)


def _require_requisition_access():
    if not any(_has_permission(permission) for permission in ('IBT_REQUEST', 'IBT_APPROVE', 'IBT_ISSUE')):
        abort(403)


def _user_warehouse_ids():
    return tuple(current_user.warehouses or [])


def _require_user_source_warehouse(warehouse_id):
    if warehouse_id not in _user_warehouse_ids():
        abort(403)


def _require_user_ibt_access(ibt_no, destination_only=False):
    warehouse_ids = _user_warehouse_ids()
    if not warehouse_ids:
        abort(403)

    placeholders = ','.join('?' for _ in warehouse_ids)
    endpoint_column = 'ToWhseLink' if destination_only else 'FromWhseLink OR ToWhseLink'
    conn = create_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(f"""
            SELECT TOP 1 1
            FROM stk._uvIBTSummary
            WHERE cIBTNumber = ?
              AND ({endpoint_column}) IN ({placeholders})
        """, (ibt_no, *warehouse_ids))
        if not cursor.fetchone():
            abort(403)
    finally:
        close_db_connection(conn, cursor)


def _evolution_workflow_status(status_id):
    return 'ISSUED' if int(status_id or 0) == 1 else 'APPROVED'


def _ensure_local_ibt(cursor, ibt_no):
    cursor.execute("SELECT IdIBT FROM stk.IBT WHERE IBTNo = ?", (ibt_no,))
    existing = cursor.fetchone()
    evolution_status = {0: 'REQUESTED', 1: 'ISSUED',2: 'RECEIVED'}
    if existing:
        return existing.IdIBT
    cursor.execute("SELECT TOP 1 StatusID FROM stk._uvIBTSummary WHERE cIBTNumber = ?", (ibt_no,))
    evolution_row = cursor.fetchone()
    status = evolution_status.get(int(evolution_row.StatusID or 0))
    cursor.execute("""
        INSERT INTO stk.IBT (IBTNo, IBTWorkflowStatus)
        OUTPUT INSERTED.IdIBT
        VALUES (?, ?)
    """, (ibt_no, status))
    print(ibt_no, status)
    return cursor.fetchone()[0]


@inventory_bp.route('/SDK/IBT', methods=['GET'])
@login_required
def ibt_summary():
    _require_ibt_visibility()
    return render_template('EvolutionSDK/IBT_summary.html', permissions=current_user.permissions)


@inventory_bp.route('/SDK/IBT_detail', methods=['GET'])
@login_required
def ibt_detail_page():
    _require_ibt_visibility()
    return render_template('EvolutionSDK/IBT_detail.html', permissions=current_user.permissions)

@inventory_bp.route('/ibt/list', methods=['GET'])
@login_required
def list_ibts():
    _require_ibt_visibility()
    conn = create_db_connection()
    cursor = conn.cursor()
    try:
        conn.commit()
        cursor.execute("""
            SELECT H.IdIBT, S.cIBTNumber IBTNo,
                   COALESCE(H.IBTWorkflowStatus,
                       CASE WHEN MAX(S.StatusID) = 1 THEN 'ISSUED' ELSE 'APPROVED' END) IBTWorkflowStatus,
                     MIN(S.FromWhseName) FromWhseName,
                     MIN(S.ToWhseName) ToWhseName,
                     COUNT(DISTINCT S.IDWhseIBTLines) LineCount,
                     H.IBTRequestTimeStamp
              FROM stk._uvIBTSummary S
                  LEFT JOIN stk.IBT H on H.IBTNo = S.cIBTNumber
              GROUP BY H.IdIBT, S.cIBTNumber, H.IBTWorkflowStatus, H.IBTRequestTimeStamp
            ORDER BY H.IBTRequestTimeStamp DESC, S.cIBTNumber DESC
        """)
        rows = [{"id": row.IdIBT, "number": row.IBTNo, "status": row.IBTWorkflowStatus,
                "warehouse_from": row.FromWhseName, "warehouse_to": row.ToWhseName,
                "line_count": row.LineCount,
                "request_timestamp": row.IBTRequestTimeStamp}
                for row in cursor.fetchall()]
        for row in rows:
            row["id"] = _ensure_local_ibt(cursor, row["number"])
        conn.commit()
        return jsonify({"success": True, "ibts": rows})
    finally:
        close_db_connection(conn, cursor)


@inventory_bp.route('/ibt/detail/<path:ibt_no>', methods=['GET'])
@login_required
def get_ibt_detail(ibt_no):
    _require_ibt_visibility()
    conn = create_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT H.IdIBT, S.cIBTNumber IBTNo,
                COALESCE(H.IBTWorkflowStatus,
                    CASE WHEN S.StatusID = 1 THEN 'ISSUED' ELSE 'APPROVED' END) IBTWorkflowStatus,
                FromWhseLink, FromWhseName,ToWhseLink, ToWhseName,
                H.IBTRequestTimeStamp, H.IBTRequestUserId, RequestUser.username IBTRequestUser,
                H.IBTApprovalTimeStamp, H.IBTApprovalUserId, ApprovalUser.username IBTApprovalUser,
                H.IBTDispatchTimeStamp, H.IBTDispatchUserId, DispatchUser.username IBTDispatchUser,
                H.IBTRejectionTimeStamp, H.IBTRejectionUserId, RejectionUser.username IBTRejectionUser,
                H.IBTRejectionReason, H.IBTReceiveTimeStamp, H.IBTReceiveUserId,
                ReceiveUser.username IBTReceiveUser, S.StockLink, StockDesc,
                fQtyIssued, fQtyReceived, fQtyVariance,
                CONV.iUOMStockingUnitID, CONV.StockingUnitCode,
                CONV.PurchasingUnitCode, CONV.ConversionFactor
            FROM stk.IBT H
            LEFT JOIN stk._uvIBTSummary S on S.cIBTNumber = H.IBTNo
            JOIN [cmn].[_uvStockUnitConversion] CONV on CONV.StockLink = S.StockLink
            LEFT JOIN users.Users RequestUser on RequestUser.id = H.IBTRequestUserId
            LEFT JOIN users.Users ApprovalUser on ApprovalUser.id = H.IBTApprovalUserId
            LEFT JOIN users.Users DispatchUser on DispatchUser.id = H.IBTDispatchUserId
            LEFT JOIN users.Users RejectionUser on RejectionUser.id = H.IBTRejectionUserId
            LEFT JOIN users.Users ReceiveUser on ReceiveUser.id = H.IBTReceiveUserId
            Where H.IBTNo = ?
            """, ibt_no)
        rows = cursor.fetchall()
        if not rows:
            return jsonify({"success": False, "message": "IBT not found."}), 404
        ibt = {
            "id": rows[0].IdIBT,
            "number": rows[0].IBTNo,
            "status": rows[0].IBTWorkflowStatus,
            "warehouse_from": {"id": rows[0].FromWhseLink, "name": rows[0].FromWhseName},
            "warehouse_to": {"id": rows[0].ToWhseLink, "name": rows[0].ToWhseName},
            "request_timestamp": rows[0].IBTRequestTimeStamp,
            "request_user": rows[0].IBTRequestUser,
            "approval_timestamp": rows[0].IBTApprovalTimeStamp,
            "approval_user": rows[0].IBTApprovalUser,
            "dispatch_timestamp": rows[0].IBTDispatchTimeStamp,
            "dispatch_user": rows[0].IBTDispatchUser,
            "rejection_timestamp": rows[0].IBTRejectionTimeStamp,
            "rejection_user": rows[0].IBTRejectionUser,
            "rejection_reason": rows[0].IBTRejectionReason,
            "receive_timestamp": rows[0].IBTReceiveTimeStamp,
            "receive_user": rows[0].IBTReceiveUser
        }
        local_id = _ensure_local_ibt(cursor, rows[0].IBTNo)
        conn.commit()
        ibt["id"] = local_id
        lines = [{
            "product_id": row.StockLink,
            "product_desc": row.StockDesc,
            "qty": row.fQtyIssued,
            "qty_received": row.fQtyReceived,
            "qty_variance": row.fQtyVariance,
            "stocking_unit_id": row.iUOMStockingUnitID,
            "stocking_unit_code": row.StockingUnitCode,
            "purchasing_unit_code": row.PurchasingUnitCode,
            "conversion_factor": row.ConversionFactor
        } for row in rows]
        return jsonify({"success": True, "ibt": ibt,
                        "lines": lines})
    finally:
        close_db_connection(conn, cursor)


@inventory_bp.route('/ibt/approved', methods=['GET'])
@login_required
def approved_ibts():
    _require_permission('IBT_ISSUE')
    conn = create_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            SELECT H.IdIBT, H.IBTNo, H.IBTWorkflowStatus,
                   H.IBTRequestUserId, H.IBTRequestTimeStamp,
                   H.IBTApprovalUserId, H.IBTApprovalTimeStamp,
                   H.IBTRejectionUserId, H.IBTRejectionTimeStamp,
                   H.IBTRejectionReason, H.IBTDispatchUserId,
                   H.IBTDispatchTimeStamp, H.IBTReceiveUserId,
                   H.IBTReceiveTimeStamp,
                     MIN(S.FromWhseName) FromWhseName,
                     MIN(S.ToWhseName) ToWhseName,
                     COUNT(DISTINCT S.IDWhseIBTLines) + COUNT(DISTINCT S.IDWhseIBTLines) LineCount
            FROM stk.IBT H
                 LEFT JOIN stk._uvIBTSummary S on S.cIBTNumber = H.IBTNo
            GROUP BY H.IdIBT, H.IBTNo, H.IBTWorkflowStatus,
                     H.IBTRequestUserId, H.IBTRequestTimeStamp,
                     H.IBTApprovalUserId, H.IBTApprovalTimeStamp,
                     H.IBTRejectionUserId, H.IBTRejectionTimeStamp,
                     H.IBTRejectionReason, H.IBTDispatchUserId,
                     H.IBTDispatchTimeStamp, H.IBTReceiveUserId,
                     H.IBTReceiveTimeStamp
            ORDER BY H.IBTRequestTimeStamp DESC
        """)
        return jsonify({"success": True, "ibts": [
            {"id": row.IdIBT, "number": row.IBTNo, "warehouse_from": row.FromWhseName,
             "warehouse_to": row.ToWhseName, "line_count": row.LineCount}
            for row in cursor.fetchall()
        ]})
    finally:
        close_db_connection(conn, cursor)


@inventory_bp.route('/ibt/create', methods=['POST'])
@login_required
def create_ibt_request():
    payload = request.get_json() or {}
    action = payload.get('action', 'request')
    required_permissions = {
        'request': ('IBT_REQUEST',),
        'approve': ('IBT_APPROVE',),
        'approve_issue': ('IBT_APPROVE', 'IBT_ISSUE')
    }
    if action not in required_permissions:
        return jsonify({"success": False, "message": "Unsupported IBT creation action."}), 400
    for permission in required_permissions[action]:
        _require_permission(permission)

    from_id = payload.get('from_warehouse_id')
    to_id = payload.get('to_warehouse_id')
    lines = payload.get('lines', [])
    if not from_id or not to_id:
        return jsonify({"success": False, "message": "Both source and destination warehouses must be specified."}), 400
    if not lines:
        return jsonify({"success": False, "message": "At least one product line must be specified."}), 400
    try:
        print(from_id, to_id, lines)
        with EvolutionConnection():
            ibt = Evo.WarehouseIBT()
            # ibt.Date = DateTime.Now
            ibt.WarehouseFrom = Evo.Warehouse(int(from_id))
            ibt.WarehouseTo = Evo.Warehouse(int(to_id))
            ibt.Description = current_user.username + " IBT request"
            ibt.Project = Evo.Project(DEFAULT_TRANSFER_PROJECT_ID)
            for item in lines:
                line = Evo.WarehouseIBTLine()
                line.InventoryItem = Evo.InventoryItem(int(item["product_id"]))
                line.QuantityIssued = item.get("qty", item.get("qty_stocking"))
                line.Description = "IBT request"
                line.Reference = current_user.username
                ibt.Detail.Add(line)
            ibt.Save()
            if action == 'approve_issue':
                ibt.IssueStock()

        conn = create_db_connection()
        cursor = conn.cursor()

        status = {'request': 'REQUESTED', 'approve': 'APPROVED', 'approve_issue': 'ISSUED'}[action]
        columns = ['IBTNo', 'IBTWorkflowStatus', 'IBTRequestUserId', 'IBTRequestTimeStamp']
        values = [ibt.Number, status, current_user.id, 'GETDATE()']
        if action in ('approve', 'approve_issue'):
            columns.extend(['IBTApprovalUserId', 'IBTApprovalTimeStamp'])
            values.extend([current_user.id, 'GETDATE()'])
        if action == 'approve_issue':
            columns.extend(['IBTDispatchUserId', 'IBTDispatchTimeStamp'])
            values.extend([current_user.id, 'GETDATE()'])
        value_sql = ', '.join('?' if value != 'GETDATE()' else 'GETDATE()' for value in values)
        parameters = [value for value in values if value != 'GETDATE()']
        cursor.execute(f"""
            INSERT INTO stk.IBT ({', '.join(columns)})
            OUTPUT INSERTED.IdIBT
            VALUES ({value_sql})
        """, parameters)
        ibt_id = cursor.fetchone()[0]
        conn.commit()
        close_db_connection(conn, cursor)
        return jsonify({"success": True, "ibt_id": ibt_id, "ibt_number": ibt.Number, "status": status})
    except ValueError as error:
        return jsonify({"success": False, "message": str(error)}), 400
    except Exception as error:
        return jsonify({"success": False, "message": str(error)}), 400


@inventory_bp.route('/ibt/<path:ibt_no>/update', methods=['POST'])
@login_required
def update_ibt_request(ibt_no):
    payload = request.get_json() or {}
    from_id = payload.get('from_warehouse_id')
    to_id = payload.get('to_warehouse_id')
    lines = payload.get('lines', [])
    if not from_id or not to_id:
        return jsonify({"success": False, "message": "Both source and destination warehouses are required."}), 400
    if str(from_id) == str(to_id):
        return jsonify({"success": False, "message": "Source and destination warehouses must be different."}), 400
    try:
        conn = create_db_connection()
        cursor = conn.cursor()
        print(ibt_no)
        cursor.execute("Select IBTNo, IBTWorkflowStatus from stk.IBT where IBTNo=?", (ibt_no,))
        row = cursor.fetchone()
        if not row:
            cursor.execute("SELECT TOP 1 StatusID FROM stk._uvIBTSummary WHERE cIBTNumber = ?", (ibt_no,))
            evolution_row = cursor.fetchone()
            if not evolution_row:
                return jsonify({"success": False, "message": "IBT not found."}), 404
            _ensure_local_ibt(cursor, ibt_no)
            cursor.execute("Select IBTNo, IBTWorkflowStatus from stk.IBT where IBTNo=?", (ibt_no,))
            row = cursor.fetchone()
        if row.IBTWorkflowStatus in ("REQUESTED", "REJECTED"):
            _require_permission('IBT_REQUEST')
            next_status = 'REQUESTED'
            cursor.execute("UPDATE [stk].[IBT] SET IBTWorkflowStatus=?, IBTRejectionReason=NULL, IBTRequestUserId=?, IBTRequestTimeStamp=GETDATE() WHERE IBTNo=?", (next_status, current_user.id, ibt_no))
        elif row.IBTWorkflowStatus == "APPROVED":
            _require_permission('IBT_APPROVE')
            next_status = 'APPROVED'
        else:
            return jsonify({"success": False, "message": "Only requested, rejected, or approved IBTs can be edited."}), 409
        if any(item.get("qty") is None and item.get("qty_stocking") is None for item in lines):
            return jsonify({"success": False, "message": "Each IBT line must include a quantity."}), 400
        print(from_id, to_id, lines)
        with EvolutionConnection():
            ibt = Evo.WarehouseIBT(ibt_no)
            ibt.WarehouseFrom = Evo.Warehouse(int(from_id))
            ibt.WarehouseTo = Evo.Warehouse(int(to_id))
            ibt.Description = current_user.username + " IBT request"
            ibt.Project = Evo.Project(DEFAULT_TRANSFER_PROJECT_ID)
            for existing_line in list(ibt.Detail):
                ibt.Detail.Remove(existing_line)
            for item in lines:
                print(item)
                line = Evo.WarehouseIBTLine()
                line.InventoryItem = Evo.InventoryItem(int(item["product_id"]))
                line.QuantityIssued = item.get("qty", item.get("qty_stocking"))
                line.Description = "IBT request"
                line.Reference = current_user.username
                ibt.Detail.Add(line)
            ibt.Save()
            conn.commit()
        return jsonify({"success": True, "ibt_number": ibt.Number, "status": next_status})
    except ValueError as error:
        return jsonify({"success": False, "message": str(error)}), 400
    finally:
        if 'conn' in locals():
            close_db_connection(conn, cursor)


@inventory_bp.route('/ibt/<path:ibt_no>/<action>', methods=['POST'])
@login_required
def transition_ibt(ibt_no, action):
    permission_by_action = {"approve": "IBT_APPROVE", "reject": "IBT_REJECT", "issue": "IBT_ISSUE", "receive": "IBT_RECEIVE"}
    if action not in permission_by_action:
        return jsonify({"success": False, "message": "Unsupported IBT action."}), 404
    _require_permission(permission_by_action[action])
    conn = create_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT IBTNo, IBTWorkflowStatus FROM [stk].[IBT] WHERE IBTNo=?", (ibt_no,))
        row = cursor.fetchone()
        if not row:
            cursor.execute("SELECT TOP 1 StatusID FROM stk._uvIBTSummary WHERE cIBTNumber = ?", (ibt_no,))
            evolution_row = cursor.fetchone()
            if not evolution_row:
                return jsonify({"success": False, "message": "IBT not found."}), 404
            _ensure_local_ibt(cursor, ibt_no)
            cursor.execute("SELECT IBTNo, IBTWorkflowStatus FROM [stk].[IBT] WHERE IBTNo=?", (ibt_no,))
            row = cursor.fetchone()
        expected = {"approve": "REQUESTED", "reject": "REQUESTED", "issue": "APPROVED", "receive": "ISSUED"}[action]
        target = {"approve": "APPROVED", "reject": "REJECTED", "issue": "ISSUED", "receive": "RECEIVED"}[action]
        if row.IBTWorkflowStatus != expected:
            return jsonify({"success": False, "message": f"IBT is {row.IBTWorkflowStatus}; expected {expected}."}), 409
        if action == "approve":
            cursor.execute("UPDATE [stk].[IBT] SET IBTWorkflowStatus=?, IBTApprovalUserId=?, IBTApprovalTimeStamp=GETDATE() WHERE IBTNo=?", (target, current_user.id, ibt_no))
        elif action == "reject":
            reason = (request.get_json() or {}).get("reason", "")
            cursor.execute("UPDATE [stk].[IBT] SET IBTWorkflowStatus=?, IBTRejectionUserId=?, IBTRejectionTimeStamp=GETDATE(), IBTRejectionReason=? WHERE IBTNo=?", (target, current_user.id, reason, ibt_no))
        elif action == "issue":
            with EvolutionConnection():
                ibt = Evo.WarehouseIBT(ibt_no)
                ibt.IssueStock()
            cursor.execute("UPDATE [stk].[IBT] SET IBTWorkflowStatus=?, IBTDispatchTimeStamp=GETDATE(), IBTDispatchUserId=? WHERE IBTNo=?", (target, current_user.id, ibt_no))
        else:
            with EvolutionConnection():
                ibt = Evo.WarehouseIBT(ibt_no)
                ibt.ReceiveStock()
            cursor.execute("UPDATE [stk].[IBT] SET IBTWorkflowStatus=?, IBTReceiveUserId=?, IBTReceiveTimeStamp=GETDATE() WHERE IBTNo=?", (target, current_user.id, ibt_no))
        conn.commit()
        return jsonify({"success": True, "status": target})
    except ValueError as error:
        return jsonify({"success": False, "message": str(error)}), 400
    except Exception as error:
        conn.rollback()
        return jsonify({"success": False, "message": str(error)}), 400
    finally:
        close_db_connection(conn, cursor)

@inventory_bp.route("/submit_ibt", methods=["POST"])
@login_required
def submit_ibt():
    _require_permission('IBT_REQUEST')
    return create_ibt_request()


# -------------------------
# IBT ISSUE END
# -------------------------

# IBT RECEIVE START
@inventory_bp.route("/SDK/IBT_receive", methods=["GET"])
def IBT_receive():
    _require_permission('IBT_RECEIVE')
    return render_template('EvolutionSDK/IBT_receive.html')

@inventory_bp.route("/fetch_issued_ibts", methods=["GET"])
def fetch_issued_ibts():
    _require_permission('IBT_RECEIVE')
    try:
        conn = create_db_connection()
        cursor = conn.cursor()

        warehouses = current_user.warehouses
        if len(warehouses) == 0:
            return jsonify({"ibts": []})
        placeholders = ",".join(["?"] * len(warehouses))
        cursor.execute(f"""
        Select Distinct IDWhseIBT, cIBTNumber, cIBTDescription, FromWhseName, ToWhseName
        from [stk].[_uvIBTSummary]
        Where StatusID = 1 AND ToWhseLink IN ({placeholders})
        """, warehouses)
        ibts = [
            {
                "ibt_number": row.cIBTNumber,
                "description": row.cIBTDescription,
                "warehouse_from": row.FromWhseName,
                "warehouse_to": row.ToWhseName
            }
            for row in cursor.fetchall()
        ]

        conn.close()

        return jsonify({"success": True, "ibts": ibts})
    except Exception as e:
        print("Error fetching issued IBTs:", str(e))
        return jsonify({"success": False, "message": str(e)}), 500

@inventory_bp.route("/display_ibt", methods=["GET"])
def display_ibt():
    _require_permission('IBT_RECEIVE')
    ibt_no = request.args.get("ibt_no") or request.args.get("ibt_id")
    try:

        conn = create_db_connection()
        cursor = conn.cursor()

        cursor.execute("""
        Select 
        IDWhseIBT, cIBTNumber, cIBTDescription, FromWhseName, ToWhseName
        ,IDWhseIBTLines
        ,s.StockLink, StockDesc ,cDescription, cReference, fQtyIssued,
        CONV.StockingUnitCode, CONV.PurchasingUnitCode, CONV.ConversionFactor
        from [stk].[_uvIBTSummary] S
        JOIN [cmn].[_uvStockUnitConversion] CONV on CONV.StockLink = s.StockLink
        Where StatusID = 1 and S.cIBTNumber = ?
        """, (ibt_no,))

        rows = cursor.fetchall()
        conn.close()

        ibt_details = [
            {
                "ibt_number": row.cIBTNumber,
                "description": row.cIBTDescription,
                "warehouse_from": row.FromWhseName,
                "warehouse_to": row.ToWhseName,
                "ibt_line_id": row.IDWhseIBTLines,
                "product_id": row.StockLink,
                "product_desc": row.StockDesc,
                "line_description": row.cDescription,
                "line_reference": row.cReference,
                "qty_issued": row.fQtyIssued,
                "stocking_unit_code": row.StockingUnitCode,
                "purchasing_unit_code": row.PurchasingUnitCode,
                "conversion_factor": row.ConversionFactor
            }
            for row in rows
        ]
        return jsonify({"success": True, "ibt_details": ibt_details})
    except Exception as e:
        print("Error displaying IBT:", str(e))
        return jsonify({"success": False, "message": str(e)}), 500

@inventory_bp.route("/submit_ibt_receive", methods=["POST"])
def submit_ibt_receive():
    _require_permission('IBT_RECEIVE')
    try:
        data = request.get_json()
        ibt_no = data.get("ibt_no") or data.get("ibt_number") or data.get("ibt_id")

        with EvolutionConnection():
            ibt = Evo.WarehouseIBT(str(ibt_no))
            ibt.ReceivedDate = DateTime.Now

            for line_data in data.get("lines", []):
                matched = False
                line_id = line_data.get("ibt_line_id")
                for ibt_line in ibt.Detail:
                    if ibt_line.ID == int(line_id):
                        print(line_data.get("QuantityReceived"), line_data.get("QuantityVariance"))
                        ibt_line.QuantityReceived = line_data.get("QuantityReceived")
                        ibt_line.QuantityVariance = line_data.get("QuantityVariance")
                        ibt_line.Description = line_data.get("Description", "")
                        ibt_line.Reference = line_data.get("Reference", "")
                        matched = True
                        break
                print(f"Evolution line IDs: {[(ibt_line.ID) for ibt_line in ibt.Detail]}")
                if not matched:
                    missing_id = line_id if line_id is not None else line_data.get("InventoryItemID")
                    return jsonify({"success": False, "message": f"IBT line not found for line id {missing_id}"}), 400

            ibt.ReceiveStock()
        conn = create_db_connection()
        cursor = conn.cursor()
        _ensure_local_ibt(cursor, ibt_no)
        cursor.execute("""
            UPDATE [stk].[IBT]
            SET IBTWorkflowStatus = 'RECEIVED',
                IBTReceiveUserId = ?,
                IBTReceiveTimeStamp = GETDATE()
            WHERE IBTNo = ?
        """, (current_user.id, ibt_no))
        conn.commit()
        conn.close()

        return jsonify({
            "success": True,
            "message": "IBT successfully received",
            "ibtNumber": ibt.Number
        })

    except Exception as e:
        print("Error submitting IBT receive:", str(e))
        return jsonify({"success": False, "message": f"Error: {str(e)}"}), 500
