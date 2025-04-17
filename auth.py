from functools import wraps
from flask import redirect, url_for, flash, request
from flask_login import LoginManager, UserMixin, current_user
from models import db, User

login_manager = LoginManager()
login_manager.login_view = 'login'  # Ensure this matches your login route

class UserLogin(UserMixin):
    def __init__(self, id, username, role):
        self.id = id
        self.username = username
        self.role = role
        self.server_name = None
        self.database_name = None
        self.db_password = None

    def load_user_data(self):
        """Fetch user credentials from the database and store them."""
        user = db.session.get(User, self.id)
        if user:
            self.server_name = user.server_name
            self.database_name = user.database_name
            self.db_password = user.get_db_password()  # Decrypt password

    def get_db_password(self):
        return self.db_password if self.db_password else None

@login_manager.user_loader
def load_user(user_id):
    user = User.query.get(int(user_id))
    if user:
        user_login = UserLogin(user.id, user.username, user.role)
        user_login.load_user_data()  # Load DB credentials from database
        return user_login
    return None

def role_required(role=None):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                flash('Please log in to access this page.', 'warning')
                return redirect(url_for('login', next=request.path))

            if role and current_user.role != role:
                flash('You do not have permission to access this page.', 'danger')
                return redirect(url_for('dashboard'))

            return f(*args, **kwargs)
        return decorated_function
    return decorator
