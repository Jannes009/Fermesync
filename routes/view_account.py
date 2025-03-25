from flask import Blueprint, render_template, request, flash, redirect, url_for
from flask_login import login_required, current_user
from werkzeug.security import check_password_hash
from models import db, User, ConnectedService  # Changed from relative import
from auth import UserLogin  # Changed from relative import

account_bp = Blueprint('account', __name__, url_prefix='/account')

# ... rest of your view_account.py code ...

@account_bp.route('/')
@login_required
def view_account():
    """Display the account information page."""
    user = User.query.get(current_user.id)
    connected_services = ConnectedService.query.filter_by(user_id=current_user.id).all()
    
    return render_template('Login/account.html',
                         user=user,
                         connected_services=connected_services)

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

# ... (keep the rest of your account routes) ...

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