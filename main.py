from flask import Flask, render_template, request, redirect, session, url_for, flash, make_response
from datetime import timedelta
from waitress import serve
from flask_session import Session
from flask_login import login_user, logout_user, current_user, login_required
import logging
from auth import login_manager, UserLogin

app = Flask(__name__)

# Function to create and configure the Flask app
def create_app():
    # Basic configuration
    app.secret_key = "secret_key"
    
    # Enhanced session configuration
    app.config.update(
        SESSION_PERMANENT=False,
        PERMANENT_SESSION_LIFETIME=timedelta(hours=1),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SECURE=True,
        SESSION_COOKIE_SAMESITE='Lax',
        SQLALCHEMY_DATABASE_URI="sqlite:///user.db",
        SQLALCHEMY_TRACK_MODIFICATIONS=False
    )

    # Initialize Flask-Login first
    login_manager.init_app(app)
    login_manager.login_view = 'login'
    login_manager.session_protection = "strong"

    from models import db, User
    db.init_app(app)

    # Register blueprints
    from routes.entry import entry_bp
    from routes.view import view_bp
    from routes.Invoices.invoices import invoice_bp
    from routes.Maintanance.product import maintanance_bp
    from routes.Import.Import import import_bp
    from routes.view_account import account_bp

    app.register_blueprint(entry_bp)
    app.register_blueprint(view_bp)
    app.register_blueprint(invoice_bp)
    app.register_blueprint(maintanance_bp)
    app.register_blueprint(import_bp, url_prefix='/import')
    app.register_blueprint(account_bp)

    # Create all tables
    with app.app_context():
        db.create_all()

    @app.route("/")
    def index():
        if current_user.is_authenticated:
            return redirect(url_for('dashboard'))
        error = request.args.get('error')
        return render_template('Login/index.html', error=error)

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if current_user.is_authenticated:
            return redirect(url_for('dashboard'))
            
        if request.method == "GET":
            return render_template('Login/index.html', next=request.args.get('next'))
        
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            user_login = UserLogin(user.id, user.username, user.role)
            user_login.load_user_data()  # Load credentials from DB
            login_user(user_login)
            
            next_page = request.args.get('next') or request.form.get('next')
            if next_page and next_page.startswith('/'):
                return redirect(next_page)
            return redirect(url_for('dashboard'))
        
        flash("Invalid username or password", "error")
        return redirect(url_for('login', next=request.form.get('next')))

    @app.route("/logout")
    @login_required
    def logout():
        logout_user()
        session.clear()
        resp = make_response(redirect(url_for('index')))
        resp.set_cookie('session', '', expires=0)
        resp.set_cookie('remember_token', '', expires=0)
        return resp

    @app.route("/register", methods=["GET", "POST"])
    def register():
        if current_user.is_authenticated:
            return redirect(url_for('dashboard'))
            
        if request.method == "GET":
            return render_template('register.html')
            
        username = request.form.get('username')
        password = request.form.get('password')
        role = request.form.get('role', 'user')
        server_name = request.form.get('server_name')
        db_name = request.form.get('db_name')
        db_password = request.form.get('db_password')

        if not all([username, password, server_name, db_name, db_password]):
            flash("All fields are required", "error")
            return redirect(url_for('register'))

        if User.query.filter_by(username=username).first():
            flash("Username already exists", "error")
            return redirect(url_for('register'))

        new_user = User(
            username=username,
            role=role,
            server_name=server_name,
            database_name=db_name
        )
        new_user.set_password(password)
        new_user.set_db_password(db_password)

        try:
            db.session.add(new_user)
            db.session.commit()
            
            user_login = UserLogin(new_user.id, new_user.username, new_user.role)
            login_user(user_login)
            flash("Registration successful!", "success")
            return redirect(url_for('dashboard'))
        except Exception as e:
            db.session.rollback()
            flash("Registration failed", "error")
            return redirect(url_for('register'))

    @app.route("/dashboard")
    @login_required
    def dashboard():
        return render_template("Home page/index.html",
                            username=current_user.username,
                            role=current_user.role)
    
    @app.route("/get_username")
    def get_username():
        return {"username": current_user.username if current_user.is_authenticated else "Guest"}

    # Error handlers
    @app.errorhandler(401)
    def unauthorized(error):
        return redirect(url_for('login', next=request.path))

    @app.errorhandler(404)
    def not_found(error):
        return render_template('error.html', error_message="Page not found"), 404

    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        return render_template('error.html', error_message="Internal server error"), 500

    @app.route("/error")
    def error_page():
        return render_template('error.html')

    return app

if __name__ == "__main__":
    app = create_app()
    app.run(debug=True)