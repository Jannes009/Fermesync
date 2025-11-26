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

def decrypt_password(encrypted_password):
    """Decrypts an encrypted password from VARBINARY storage."""
    # pyodbc can return memoryview for VARBINARY
    if isinstance(encrypted_password, memoryview):
        encrypted_password = encrypted_password.tobytes()
    elif isinstance(encrypted_password, str):
        # This only works if somehow it was stored as a string (not ideal)
        encrypted_password = encrypted_password.encode()

    return fernet.decrypt(encrypted_password).decode()
