from flask import Flask, render_template, request, redirect, session, url_for, make_response
from datetime import timedelta
from flask_session import Session
from flask_login import login_user, logout_user, current_user, login_required
import logging
import os
from auth import login_manager, UserLogin
from apscheduler.schedulers.background import BackgroundScheduler
from Market.routes.Import.scheduler import run_all_import_jobs


# Function to create and configure the Flask app
def create_app():
    # Set template folder to Market/templates and static folder to Market/static/
    app_root = os.path.dirname(os.path.abspath(__file__))
    template_dir = os.path.join(app_root, 'main_templates')
    static_dir = os.path.join(app_root, 'Market', 'static')

    app = Flask(__name__, template_folder=template_dir, static_folder=static_dir)

    @app.context_processor
    def utility_processor():
        def filemtime(bp_name, filename):
            bp = app.blueprints.get(bp_name)
            if bp and hasattr(bp, 'static_folder') and bp.static_folder:
                path = os.path.join(bp.static_folder, filename)
                if os.path.exists(path):
                    return int(os.path.getmtime(path))
            return "0"
        return dict(filemtime=filemtime)
        
    # Basic configuration
    app.secret_key = "secret_key"
    # app.config['EVOLUTION_SALES_ORDER_API'] = os.getenv(
    #     'EVOLUTION_SALES_ORDER_API',
    #     'http://localhost:5295/api/evolutiontest/create-sales-order'
    # )
    # app.config['EVOLUTION_WAREHOUSE_TRANSFER_API'] = os.getenv(
    #     'EVOLUTION_WAREHOUSE_TRANSFER_API',
    #     'http://localhost:5295/api/warehousetransfer/create'
    # )
    
    from sqlalchemy.pool import NullPool  # add this import at the top of main.py

    app.config.update(
        SESSION_PERMANENT=False,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SECURE=False,
        SESSION_COOKIE_SAMESITE='Lax',
        SQLALCHEMY_DATABASE_URI="sqlite:///user.db",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SQLALCHEMY_ENGINE_OPTIONS={"poolclass": NullPool}  # 👈 new line
    )


    # Initialize Flask-Login first
    login_manager.init_app(app)
    login_manager.login_view = 'login'
    login_manager.session_protection = "strong"

    from models import db, User
    db.init_app(app)
    login_manager.init_app(app)

    from Market.routes import market_bp
    from Inventory.routes import inventory_bp
    from view_account import account_bp

    app.register_blueprint(market_bp, url_prefix='/market')
    app.register_blueprint(inventory_bp, url_prefix='/inventory')
    app.register_blueprint(account_bp)

    # Create all tables
    with app.app_context():
        db.create_all()

    @app.route("/")
    def index():
        if current_user.is_authenticated:
            return redirect(url_for('dashboard'))
        error = request.args.get('error')
        return render_template('/index.html', error=error)

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if current_user.is_authenticated:
            return redirect(url_for('dashboard'))
            
        if request.method == "GET":
            print("rendering template")
            return render_template('/index.html', next=request.args.get('next'))

        
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            user_login = UserLogin(user.id, user.username, user.role)
            user_login.load_user_data()  # Load credentials from DB
            login_user(user_login)
            
            next_page = request.form.get('next')
            if next_page and next_page.startswith('/'):
                return redirect(next_page)
            return redirect(url_for('dashboard'))
        
        print("Invalid username or password", "error")
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
            return render_template('/index.html')

        username = request.form.get('username')
        password = request.form.get('password')
        role = request.form.get('role', 'user')

        if not all([username, password]):
            print("All fields are required", "error")
            return redirect(url_for('register'))

        if User.query.filter_by(username=username).first():
            print("Username already exists", "error")
            return redirect(url_for('register'))

        new_user = User(
            username=username,
            role=role
        )
        new_user.set_password(password)

        try:
            db.session.add(new_user)
            db.session.commit()

            user_login = UserLogin(new_user.id, new_user.username, new_user.role)
            user_login.load_user_data()
            login_user(user_login)

            print("Registration successful!", "success")
            return redirect(url_for('dashboard'))
        except Exception as e:
            db.session.rollback()
            print("Registration failed", e)
            return redirect(url_for('register'))


    @app.route("/dashboard")
    @login_required
    def dashboard():
        return render_template("/Home page/index.html",
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

    @app.teardown_appcontext
    def shutdown_session(exception=None):
        db.session.remove()

    return app

def set_last_module(name):
    session['last_module'] = name

app = create_app()

if __name__ == "__main__":
    # scheduler = BackgroundScheduler()
    # if not app.debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
    #     scheduler.add_job(run_all_import_jobs, 'interval', seconds=120)
    #     scheduler.start()
    app.run(host='0.0.0.0', port=5001, debug=True)

