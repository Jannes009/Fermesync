from flask import Flask, render_template, request, redirect, session, url_for, flash, make_response
from datetime import timedelta
from waitress import serve
from flask_session import Session
import logging

app = Flask(__name__)
# Function to create and configure the Flask app
def create_app():


    app.secret_key = "secret_key"

    from models import db, User
    
    # Configure SQLAlchemy
    app.config['SESSION_PERMANENT'] = False
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///user.db"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=1)  # Session timeout
    app.config['SESSION_COOKIE_HTTPONLY'] = True  # Prevent JavaScript access to cookies
    app.config['SESSION_COOKIE_SECURE'] = True  # Ensure cookies are sent over HTTPS
    db.init_app(app)

    # Register blueprints
    from routes.entry import entry_bp
    from routes.view import view_bp
    from routes.Invoices.invoices import invoice_bp
    from routes.Maintanance.product import maintanance_bp
    from routes.Import.Import import import_bp

    app.register_blueprint(entry_bp)
    app.register_blueprint(view_bp)
    app.register_blueprint(invoice_bp)
    app.register_blueprint(maintanance_bp)
    app.register_blueprint(import_bp)

    # Create all tables
    with app.app_context():
        db.create_all()

    # Define routes here
    @app.route("/")
    def index():
        error = request.args.get('error')  # Fetch the error message from query parameters
        if "username" in session:
            return redirect(url_for("dashboard"))
        return render_template('Login/index.html', error=error)

    # Login route
    @app.route("/login", methods=["POST"])
    def login():
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            session.clear()  # Clear previous session data
            session['username'] = username
            session['role'] = user.role
            session.permanent = True  # Apply session timeout
            return redirect(url_for('dashboard'))
        else:
            error = "Invalid username or password. Please try again."
            return redirect(url_for('index', error=error))

    # Logout route
    @app.route("/logout")
    def logout():
        session.clear()  # Clear session data
        resp = make_response(redirect(url_for('index')))
        resp.set_cookie('session', '', expires=0)  # Clear cookies if needed
        return resp

    # Register route
    @app.route("/register", methods=["POST"])
    def register():
        username = request.form['username']
        password = request.form['password']
        role = request.form.get('role', 'user')
        server_name = request.form['server_name']
        db_name = request.form['db_name']
        db_password = request.form['db_password']
        technofresh_username = request.form.get('technofresh_username', None)
        technofresh_password = request.form.get('technofresh_password', None)

        user = User.query.filter_by(username=username).first()
        if user:
            error = "User already exists. Please choose a different username."
            return render_template("Login/index.html", error=error)
        else:
            new_user = User(username=username, role=role, server_name=server_name, database_name=db_name)
            new_user.set_password(password)
            new_user.set_db_password(db_password)  # Encrypt DB password

            if technofresh_username and technofresh_password:
                new_user.technofresh_username = technofresh_username
                new_user.set_technofresh_password(technofresh_password)  # Encrypt Technofresh password

            db.session.add(new_user)
            db.session.commit()
            session.clear()
            session['username'] = username
            session['role'] = role
            session.permanent = True
            return redirect(url_for('dashboard'))


    # Dashboard route
    @app.route("/dashboard")
    def dashboard():
        if "username" not in session:
            return redirect(url_for("index"))
        username = session["username"]
        role = session.get('role')
        return render_template("Home page/index.html", username=username, role=role)
    
    @app.route("/get_username")
    def get_username():
        return {"username": session.get("username", "Guest")}


    # Create the database tables if they don't already exist (only run this once)
    with app.app_context():
        db.create_all()
        
    return app

# Global error handler
@app.errorhandler(Exception)
def handle_error(error):
    # Log the error details for debugging purposes
    logging.error(f"An error occurred: {error}")
    
    # Return the custom error page with the error message
    return render_template('error.html', error_message=str(error)), 500

# Error page template (templates/error.html)
@app.route("/error")
def error_page():
    return render_template('error.html')


if __name__ == "__main__":
    create_app().run(debug=True)

