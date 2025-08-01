from flask import Blueprint, render_template, request, flash, redirect, url_for, jsonify
from flask_login import login_required, current_user
from werkzeug.security import check_password_hash
from models import db, User, ConnectedService  # Changed from relative import
from auth import UserLogin  # Changed from relative import
from db import create_db_connection, close_db_connection
from routes.db_functions import (
    get_production_unit_codes, get_market_codes,
    get_transporter_codes
)

account_bp = Blueprint('account', __name__, url_prefix='/account')

@account_bp.route('/')
@login_required
def view_account():
    user = User.query.get(current_user.id)
    connected_services = ConnectedService.query.filter_by(user_id=current_user.id).all()

    conn = create_db_connection()
    cursor = conn.cursor()
    production_units = get_production_unit_codes(cursor)
    packhouses = get_market_codes(cursor)
    agents = get_agents_full()
    transporters = get_transporter_codes(cursor)
    close_db_connection(cursor, conn)

    return render_template(
        'Login/account.html',
        user=user,
        connected_services=connected_services
)

@account_bp.route('/add_service', methods=['POST'])
@login_required
def add_service():
    """Add a new connected service."""
    try:
        account_password = request.form.get('account_password')
        service_type = request.form.get('service_type')
        username = request.form.get('service_username')
        password = request.form.get('service_password')

        # Verify account password first
        user = User.query.get(current_user.id)
        if not user.check_password(account_password):
            flash("Account password is incorrect", "error")
            return redirect(url_for('account.view_account'))

        if not all([service_type, password]):
            flash("Service type and password are required", "error")
            return redirect(url_for('account.view_account'))

        # Create new service
        new_service = ConnectedService(
            user_id=current_user.id,
            service_type=service_type,
            username=username
        )
        new_service.set_password(password)
        
        db.session.add(new_service)
        db.session.commit()
        
        flash(f"{service_type} service added successfully", "success")
        return redirect(url_for('account.view_account'))

    except Exception as e:
        db.session.rollback()
        flash(f"Error adding service: {str(e)}", "error")
        return redirect(url_for('account.view_account'))

@account_bp.route('/remove_service/<int:service_id>', methods=['POST'])
@login_required
def remove_service(service_id):
    """Remove a connected service."""
    try:
        service = ConnectedService.query.filter_by(
            id=service_id,
            user_id=current_user.id
        ).first()

        if not service:
            flash("Service not found", "error")
            return redirect(url_for('account.view_account'))

        db.session.delete(service)
        db.session.commit()
        
        flash("Service removed successfully", "success")
        return redirect(url_for('account.view_account'))

    except Exception as e:
        db.session.rollback()
        flash(f"Error removing service: {str(e)}", "error")
        return redirect(url_for('account.view_account'))

@account_bp.route('/get_agents_full', methods=['GET'])
@login_required
def get_agents_full():
    conn = create_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT 
            DCLink, Account, Name, GroupCode, MarketComm, AgentComm, 
            DiscountPercent 
        FROM 
            _uvMarketAgent
    """)
    agents = cursor.fetchall()
    close_db_connection(cursor, conn)
    # Return as list of dicts for JS
    result = [
        {
            "DCLink": row[0],
            "Account": row[1],
            "Name": row[2],
            "GroupCode": row[3],
            "MarketComm": row[4],
            "AgentComm": row[5],
            "DiscountPercent": row[6]
        }
        for row in agents
    ]
    return jsonify(result)

@account_bp.route('/get_production_units', methods=['GET'])
@login_required
def get_production_units():
    conn = create_db_connection()
    cursor = conn.cursor()
    units = get_production_unit_codes(cursor)
    close_db_connection(cursor, conn)
    # Return as list of dicts
    result = [
        {"Code": row[0], "Name": row[1]} for row in units
    ]
    return jsonify(result)

@account_bp.route('/get_packhouses', methods=['GET'])
@login_required
def get_packhouses():
    conn = create_db_connection()
    cursor = conn.cursor()
    packhouses = get_market_codes(cursor)
    close_db_connection(cursor, conn)
    result = [
        {"Code": row[0], "Name": row[1]} for row in packhouses
    ]
    return jsonify(result)

@account_bp.route('/get_transporters', methods=['GET'])
@login_required
def get_transporters():
    conn = create_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
                   SELECT [TransporterAccount], [TransporterName], GroupCode
                   FROM [_uvMarketTransporter]
                    ORDER BY [TransporterName]
                   """)
    transporters = cursor.fetchall()
    close_db_connection(cursor, conn)
    result = [
        {"Code": row[0], "Name": row[1], "Group": row[2]} for row in transporters
    ]
    return jsonify(result)

@account_bp.route('/update_agent', methods=['POST'])
@login_required
def update_agent():
    data = request.get_json()
    dclink = data.get('DCLink')
    agent_comm = data.get('AgentComm')
    market_comm = data.get('MarketComm')
    discount = data.get('DiscountPercent')
    try:
        conn = create_db_connection()
        cursor = conn.cursor()
        cursor.execute("EXEC SIGUpdateClient @DCLink = ?, @AgentComm = ?, @MarketComm = ?, @DiscountPercent = ?", (dclink, agent_comm, market_comm, discount))
        conn.commit()
        close_db_connection(cursor, conn)
        return jsonify(success=True, message="Agent updated successfully")
    except Exception as e:
        if 'conn' in locals():
            close_db_connection(cursor, conn)
        return jsonify(success=False, error=str(e)), 500