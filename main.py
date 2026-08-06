from flask import Flask, render_template, request, redirect, session, url_for, make_response, send_from_directory, jsonify
from flask_login import login_user, logout_user, current_user, login_required
from Core.auth import login_manager, authenticate_user, get_user_by_username, set_user_password
import os
from Core.config import DevelopmentConfig, ProductionConfig, TestingConfig
import subprocess
from Instance.local_settings import FLASK_ENV, ONESIGNAL_APP_ID

# -----------------------------
# Flask App
# -----------------------------
def create_app():
    app = Flask(
        __name__,
        template_folder='main_templates',
        static_folder='main_static'
    )

    env = FLASK_ENV

    if env == "production":
        app.config.from_object(ProductionConfig)
    elif env == "testing":
        app.config.from_object(TestingConfig)
    else:
        app.config.from_object(DevelopmentConfig)

    login_manager.init_app(app)
    login_manager.session_protection = "basic"

    from Core.admin import admin_bp
    from Market.routes import market_bp
    from Inventory.routes import inventory_bp
    from Core.view_account import account_bp
    from Agri.routes import agri_bp

    app.register_blueprint(market_bp, url_prefix='/market')
    app.register_blueprint(inventory_bp, url_prefix='/inventory')
    app.register_blueprint(agri_bp, url_prefix='/agri')
    app.register_blueprint(admin_bp)
    app.register_blueprint(account_bp)

    # -----------------------------
    # ROUTES
    # -----------------------------
    @app.context_processor 
    def utility_processor(): 
        def filemtime(bp_name, filename): 
            bp = app.blueprints.get(bp_name) 
            if bp and hasattr(bp, 'static_folder') and bp.static_folder: 
                path = os.path.join(bp.static_folder, filename) 
                if os.path.exists(path): 
                    return int(os.path.getmtime(path)) 
            return 0  # return 0 if file not found

        # ⚠️ Must return a dictionary
        return dict(filemtime=filemtime)
    
    @app.context_processor
    def inject_vapid_key():
        return {
            "vapid_public_key": app.config.get("VAPID_PUBLIC_KEY")
        }

    @app.context_processor
    def inject_onesignal():
        return {
            "onesignal_app_id": ONESIGNAL_APP_ID
        }

    @app.route("/")
    def index():
        if current_user.is_authenticated:
            return redirect(url_for('dashboard'))
        return render_template('index.html')

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if current_user.is_authenticated:
            return redirect(url_for('dashboard'))
        error_msg = None
        if request.method == "POST":
            username = request.form.get('username', '').strip()
            password = request.form.get('password', '')
            confirm_password = request.form.get('confirm_password', '')

            if not username:
                error_msg = "Username is required"
                return render_template('index.html', error=error_msg)

            user = get_user_by_username(username)
            if not user:
                error_msg = "Invalid username"
                return render_template('index.html', error=error_msg)

            if not user.password_hash:
                if not password:
                    error_msg = "Please create a password for first-time login"
                    return render_template('index.html', error=error_msg, first_time=True, username=username)
                if not confirm_password:
                    error_msg = "Please confirm your password"
                    return render_template('index.html', error=error_msg, first_time=True, username=username)
                if password != confirm_password:
                    error_msg = "Passwords do not match"
                    return render_template('index.html', error=error_msg, first_time=True, username=username)

                set_user_password(user.id, password)
                user = authenticate_user(username, password)
                if user:
                    login_user(user, remember=True)
                    session.permanent = True
                    return redirect(url_for('dashboard'))
                error_msg = "Unable to create password. Please try again."
                return render_template('index.html', error=error_msg, first_time=True, username=username)

            if not password:
                error_msg = "Password is required"
                return render_template('index.html', error=error_msg, username=username)

            user = authenticate_user(username, password)
            if user:
                login_user(user, remember=True)
                session.permanent = True
                return redirect(url_for('dashboard'))

            error_msg = "Invalid username or password"
        return render_template('index.html', error=error_msg)

    @app.route('/login/check_username', methods=['POST'])
    def check_username():
        data = request.get_json() or {}
        username = (data.get('username') or '').strip()
        if not username:
            return jsonify(success=False, message='Username is required'), 400
        user = get_user_by_username(username)
        if not user:
            return jsonify(success=False, message='Username not found'), 404
        return jsonify(success=True, has_password=bool(user.password_hash))

    @app.route("/logout")
    @login_required
    def logout():
        logout_user()
        return redirect(url_for('index'))

    @app.route("/install")
    def install():
        return render_template('install.html')

    @app.route("/dashboard")
    @login_required
    def dashboard():

        has_market = current_user.has_feature("MARKET")
        has_inventory = current_user.has_feature("INVENTORY")
        print(f"User {current_user.username} has_market: {has_market}, has_inventory: {has_inventory}")  # Debugging lin

        if has_market and has_inventory:
            return render_template('dashboard.html')

        elif has_market:
            return redirect(url_for('market.dashboard'))

        elif has_inventory:
            return redirect(url_for('inventory.dashboard'))

        else:
            return render_template('incomplete_account.html')

        
    # Serve manifest.json at root
    @app.route("/manifest.json")
    def manifest():
        return send_from_directory(app.static_folder, "manifest.json")

    # Serve service worker at root
    @app.route("/sw.js")
    def service_worker():
        return send_from_directory(app.static_folder, "sw.js")
    
    @app.route("/onesignal/OneSignalSDKWorker.js")
    def onesignal_worker():
        return send_from_directory("onesignal", "OneSignalSDKWorker.js")

    # -----------------------------
    # ERROR HANDLERS
    # -----------------------------
    # @app.errorhandler(401)
    # def unauthorized(error):
    #     return redirect(url_for('login', next=request.path))

    # @app.errorhandler(404)
    # def not_found(error):
    #     return render_template('error.html', error_message="Page not found"), 404

    # @app.errorhandler(500)
    # def internal_error(error):
    #     return render_template('error.html', error_message="Internal server error"), 500

    return app

def ensure_playwright_browsers_installed():
    try:
        subprocess.run(["playwright", "install"], check=True)
    except Exception as e:
        print(f"Failed to install Playwright browsers: {e}")

# -----------------------------
# RUN APP
# -----------------------------
app = create_app()

if __name__ == "__main__":
    ensure_playwright_browsers_installed()

    from waitress import serve

    env = FLASK_ENV
    print(env)
    if env == "production":
        serve(
            app,
            host="0.0.0.0",
            port=5001,
            threads=8
        )
    else:
        app.run(debug=True, host="0.0.0.0", port=5001)