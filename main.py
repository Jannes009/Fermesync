from flask import Flask, render_template, request, redirect, session, url_for, make_response, send_from_directory
from flask_login import login_user, logout_user, current_user, login_required
from auth import login_manager, authenticate_user
import os
from config import DevelopmentConfig, ProductionConfig, TestingConfig
import subprocess

# -----------------------------
# Flask App
# -----------------------------
def create_app():
    app = Flask(
        __name__,
        template_folder='main_templates',
        static_folder='main_static'
    )

    env = os.getenv("FLASK_ENV", "development")

    if env == "production":
        app.config.from_object(ProductionConfig)
    elif env == "testing":
        app.config.from_object(TestingConfig)
    else:
        app.config.from_object(DevelopmentConfig)

    login_manager.init_app(app)
    login_manager.session_protection = "basic"

    from admin import admin_bp
    from Market.routes import market_bp
    from Inventory.routes import inventory_bp
    from view_account import account_bp

    app.register_blueprint(market_bp, url_prefix='/market')
    app.register_blueprint(inventory_bp, url_prefix='/inventory')
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

    @app.route("/")
    def index():
        if current_user.is_authenticated:
            return redirect(url_for('dashboard'))
        return render_template('index.html')

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if current_user.is_authenticated:
            return redirect(url_for('dashboard'))
        if request.method == "POST":
            username = request.form.get('username')
            password = request.form.get('password')
            user = authenticate_user(username, password)
            if user:
                login_user(user, remember=True)
                session.permanent = True
                return redirect(url_for('dashboard'))
        return render_template('index.html')

    @app.route("/logout")
    @login_required
    def logout():
        logout_user()
        return redirect(url_for('index'))


    @app.route("/dashboard")
    @login_required
    def dashboard():
        if current_user.market_module and current_user.inventory_module:
            return render_template('dashboard.html')
        elif current_user.market_module:
            return redirect(url_for('market.dashboard'))
        elif current_user.inventory_module:
            return redirect(url_for('inventory.dashboard'))
        else:
            return redirect(url_for('account.view_account'))
        
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
    app.run(host='0.0.0.0', port=5001, debug=True)
