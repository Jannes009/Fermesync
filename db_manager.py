from auth import connect, close_connection
from key_manager import decrypt_password

import logging
import pyodbc

logger = logging.getLogger(__name__)

def get_user_by_id(user_id):
    # Try connecting
    try:
        conn, cursor = connect()
        print(f"[get_user_by_id] Connected to DB")
    except Exception as e:
        print(f"[get_user_by_id] DB connection failed: {e}")
        return None

    try:
        cursor.execute("SELECT id, username, PasswordHash FROM Users WHERE id = ?", (user_id,))
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
        close_connection(conn, cursor)
        print(f"[get_user_by_id] Connection closed")



def get_services_for_user(user_id):
    try:
        conn, cursor = connect()
        print(f"[get_services_for_user] Connected to DB")
    except Exception as e:
        print(f"[get_services_for_user] DB connection failed: {e}")
        return []

    try:
        cursor.execute("""
            SELECT Id, ServiceType, Username
            FROM ConnectedServices
            WHERE UserId = ?
        """, (user_id,))
        rows = cursor.fetchall()

        print({"service_type": [r[1]for r in rows]})

        return [{"id": r[0], "service_type": r[1], "username": r[2]}for r in rows]

    except Exception as e:
        print(f"[get_services_for_user] Error executing query: {e}")
        return []

    finally:
        close_connection(conn, cursor)
        print(f"[get_services_for_user] Connection closed")



def get_service_details(user_id, service_type):
    print(f"[get_service_details] Fetching service '{service_type}' for user {user_id}")

    try:
        conn, cursor = connect()
        print("[get_service_details] Connected to DB")
    except Exception as e:
        print(f"[get_service_details] DB connection failed: {e}")
        return None

    try:
        cursor.execute("""
            SELECT Username, EncryptedPassword
            FROM ConnectedServices
            WHERE UserId = ? AND ServiceType = ?
        """, (user_id, service_type))

        row = cursor.fetchone()

        if not row:
            print(f"[get_service_details] Service '{service_type}' not found for user {user_id}")
            return None

        username = row[0]
        encrypted_password = row[1]

        # Try decrypt
        try:
            password = decrypt_password(encrypted_password)
            print(f"[get_service_details] Password decrypted successfully")
        except Exception as e:
            print(f"[get_service_details] Failed to decrypt password: {e}")
            return None

        print(f"[get_service_details] Service fetched: {service_type} ({username})")

        return {
            "service_type": service_type,
            "username": username,
            "password": password
        }

    except Exception as e:
        print(f"[get_service_details] Error executing query: {e}")
        return None

    finally:
        close_connection(conn, cursor)
        print("[get_service_details] Connection closed")



def get_databases_for_user(user_id):
    try:
        conn, cursor = connect()
        print(f"[get_databases_for_user] Connected to DB")
    except Exception as e:
        print(f"[get_databases_for_user] DB connection failed: {e}")
        return []

    try:
        cursor.execute("""
            SELECT UserId, DatabaseType, ServerName, DatabaseName, SqlUsername
            FROM UserDatabaseConfig
            WHERE UserId = ?
        """, (user_id,))
        rows = cursor.fetchall()

        print(f"[get_databases_for_user] Retrieved {len(rows)} database configs for user {user_id}")

        return [
            {
                "user_id": r[0],
                "db_type": r[1],
                "server_name": r[2],
                "database_name": r[3],
                "db_username": r[4],
            }
            for r in rows
        ]

    except Exception as e:
        print(f"[get_databases_for_user] Error executing query: {e}")
        return []

    finally:
        close_connection(conn, cursor)
        print("[get_databases_for_user] Connection closed")
