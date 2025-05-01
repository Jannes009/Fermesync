from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from cryptography.fernet import Fernet
import base64
import os

db = SQLAlchemy()

# Securely load or generate an encryption key
KEY_FILE = "encryption.key"

def load_encryption_key():
    """Loads the encryption key from an environment variable or a secure file."""
    key = os.environ.get("ENCRYPTION_KEY")

    if key:
        return key.encode()  # Convert string to bytes for Fernet

    # If key file exists, load from there
    if os.path.exists(KEY_FILE):
        with open(KEY_FILE, "rb") as f:
            return f.read()

    # No key found: Generate a new one and save it
    key = Fernet.generate_key()
    with open(KEY_FILE, "wb") as f:
        f.write(key)

    print("⚠️ New encryption key generated and saved to", KEY_FILE)
    return key

SECRET_KEY = load_encryption_key()
cipher = Fernet(SECRET_KEY)

# models.py
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(25), unique=True, nullable=False)
    password_hash = db.Column(db.String(150), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="user")
    server_name = db.Column(db.String(100), nullable=False)
    database_name = db.Column(db.String(100), nullable=False)
    db_username = db.Column(db.String(100), nullable=False)  # NEW
    db_password = db.Column(db.String(250), nullable=False)  # Encrypted

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def encrypt_password(self, password):
        return cipher.encrypt(password.encode()).decode()

    def decrypt_password(self, encrypted_password):
        return cipher.decrypt(encrypted_password.encode()).decode()

    def set_db_password(self, password):
        self.db_password = self.encrypt_password(password)

    def get_db_password(self):
        return self.decrypt_password(self.db_password)

class ConnectedService(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    service_type = db.Column(db.String(50), nullable=False)  # e.g., 'technofresh', 'shopware', etc.
    username = db.Column(db.String(100), nullable=True)
    encrypted_password = db.Column(db.String(250), nullable=False)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())

    user = db.relationship('User', backref=db.backref('connected_services', lazy=True))

    def set_password(self, password):
        self.encrypted_password = cipher.encrypt(password.encode()).decode()

    def get_password(self):
        return cipher.decrypt(self.encrypted_password.encode()).decode()