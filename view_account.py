from flask import render_template, request, flash, redirect, url_for, jsonify, Blueprint
from flask_login import login_required, current_user
from werkzeug.security import check_password_hash
from models import db, User, ConnectedService, UserDatabaseConfig  # Changed from relative import
from auth import UserLogin  # Changed from relative import
from Market.db import create_db_connection, close_db_connection

account_bp = Blueprint('account', __name__, url_prefix='/account')

@account_bp.route('/account/')
@login_required
def view_account():
    user = User.query.get(current_user.id)
    # no need to query ConnectedService separately
    # connected_services = ConnectedService.query.filter_by(user_id=current_user.id).all()

    return render_template(
        'account.html',
        user=user,
        # connected_services=user.connected_services  # optional
    )


@account_bp.route('/account/add_service', methods=['POST'])
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
    

@account_bp.route('/account/add_database_config', methods=['POST'])
@login_required
def add_database_config():
    """Add a new connected service."""
    try:
        db_type = request.form.get('db_type')
        server_name = request.form.get('server_name')
        db_name = request.form.get('db_name')
        db_username = request.form.get('db_username')
        db_password = request.form.get('db_password')

        if not all([db_type, server_name, db_name, db_username, db_password]):
            flash("All fields are required", "error")
            return redirect(url_for('account.view_account'))

        # Create new service
        new_database_config = UserDatabaseConfig(
            user_id=current_user.id,
            server_name=server_name,
            database_type=db_type,
            database_name=db_name,
            db_username=db_username
        )
        new_database_config.set_db_password(db_password)
        db.session.add(new_database_config)
        db.session.commit()
        
        flash(f"{db_type} database added successfully", "success")
        return redirect(url_for('account.view_account'))

    except Exception as e:
        db.session.rollback()
        flash(f"Error adding service: {str(e)}", "error")
        return redirect(url_for('account.view_account'))
    
@account_bp.route('/account/remove_database/<int:db_id>', methods=['POST'])
@login_required
def remove_database(db_id):
    """Remove a user database configuration."""
    try:
        db_config = UserDatabaseConfig.query.filter_by(
            id=db_id,
            user_id=current_user.id
        ).first()

        if not db_config:
            flash("Database configuration not found", "error")
            return redirect(url_for('account.view_account'))

        db.session.delete(db_config)
        db.session.commit()

        flash("Database configuration removed successfully", "success")
        return redirect(url_for('account.view_account'))

    except Exception as e:
        db.session.rollback()
        flash(f"Error removing database configuration: {str(e)}", "error")
        return redirect(url_for('account.view_account'))


@account_bp.route('/account/remove_service/<int:service_id>', methods=['POST'])
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

@account_bp.route('/account/update_agent', methods=['POST'])
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