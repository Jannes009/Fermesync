# key_manager.py
from cryptography.fernet import Fernet
import os

KEY_FILE = "db_encryption.key"

def load_encryption_key():
    if os.path.exists(KEY_FILE):
        with open(KEY_FILE, "rb") as f:
            return f.read()
    key = Fernet.generate_key()
    with open(KEY_FILE, "wb") as f:
        f.write(key)
    return key

FERNET_KEY = load_encryption_key()
fernet = Fernet(FERNET_KEY)

def encrypt_password(password):
    """Encrypts a password string."""
    return fernet.encrypt(password.encode())

def decrypt_password(encrypted_password) -> str:
    """
    Decrypt Fernet-encrypted password.
    Works for:
    - env var strings
    - varbinary(max) bytes from SQL
    """
    if not encrypted_password:
        raise ValueError("Encrypted password not set")

    # If value comes from env var (string), convert to bytes
    if isinstance(encrypted_password, str):
        encrypted_password = encrypted_password.encode("utf-8")

    # If already bytes (from varbinary), leave it
    return fernet.decrypt(encrypted_password).decode("utf-8")

