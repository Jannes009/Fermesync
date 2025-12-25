from flask import Flask, render_template, request, redirect, session, url_for, make_response, send_from_directory
from flask_login import login_user, logout_user, current_user, login_required
from auth import login_manager, authenticate_user
import os
from datetime import timedelta

# -----------------------------
# Flask App
# -----------------------------
def create_app():
    app = Flask(__name__, template_folder='main_templates', static_folder='main_static')
    app.secret_key = "secret_key"

    app.config.update(
        SECRET_KEY="secret_key",
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=False,  # True if HTTPS
        PERMANENT_SESSION_LIFETIME=timedelta(days=30)
    )

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
        session.clear()
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
            return render_template('no_modules.html')
        
    # Serve manifest.json at root
    @app.route("/manifest.json")
    def manifest():
        return send_from_directory(app.static_folder, "manifest.json")

    # Serve service worker at root
    @app.route("/sw.js")
    def service_worker():
        return send_from_directory(app.static_folder, "sw.js")

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


# -----------------------------
# RUN APP
# -----------------------------
app = create_app()
if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5001, debug=True)
