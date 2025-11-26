from flask import Flask, render_template, request, redirect, session, url_for, make_response
from flask_login import login_user, logout_user, current_user, login_required
from auth import login_manager, UserLogin, authenticate_user
from cryptography.fernet import Fernet
import os
from werkzeug.security import check_password_hash

# -----------------------------
# Load Encryption Key
# -----------------------------
KEY_FILE = "encryption.key"

def load_encryption_key():
    if os.path.exists(KEY_FILE):
        with open(KEY_FILE, "rb") as f:
            return f.read()
    key = Fernet.generate_key()
    with open(KEY_FILE, "wb") as f:
        f.write(key)
    return key

SECRET_KEY = load_encryption_key()
cipher = Fernet(SECRET_KEY)


# -----------------------------
# Flask App
# -----------------------------
def create_app():
    app = Flask(__name__, template_folder='main_templates', static_folder='Market/static')
    app.secret_key = "secret_key"

    login_manager.init_app(app)
    login_manager.session_protection = "strong"

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
                login_user(user)
                return redirect(url_for('dashboard'))
        return render_template('index.html')

    @app.route("/logout")
    @login_required
    def logout():
        logout_user()
        session.clear()
        resp = make_response(redirect(url_for('index')))
        resp.set_cookie('session', '', expires=0)
        resp.set_cookie('remember_token', '', expires=0)
        return resp

    @app.route("/dashboard")
    @login_required
    def dashboard():
        return render_template('permissions.html', username=current_user.username)
    
    @app.route("/get_username")
    def get_username():
        if current_user.is_authenticated:
            return {"username": current_user.username}
        return {"username": None}

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
