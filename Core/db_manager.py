from Core.auth import close_db_connection, create_db_connection
from Core.key_manager import decrypt_password

import logging
import pyodbc

logger = logging.getLogger(__name__)

def get_user_by_id(user_id):
    # Try connecting
    try:
        conn = create_db_connection()
        cursor = conn.cursor()
        print(f"[get_user_by_id] Connected to DB")
    except Exception as e:
        print(f"[get_user_by_id] DB connection failed: {e}")
        return None

    try:
        cursor.execute("SELECT id, username, PasswordHash FROM users.Users WHERE id = ?", (user_id,))
        row = cursor.fetchone()

        if not row:
            print(f"[get_user_by_id] No user found for ID: {user_id}")
            return None

        print(f"[get_user_by_id] Retrieved user {row[1]} (ID {row[0]})")

        return {
            "id": row[0],
            "username": row[1],
            "password_hash": row[2]
        }

    except Exception as e:
        print(f"[get_user_by_id] Error executing query: {e}")
        return None

    finally:
        close_db_connection(conn, cursor)
        print(f"[get_user_by_id] Connection closed")

