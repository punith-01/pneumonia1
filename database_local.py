"""
Local SQLite Database module for MongoDB fallback
Uses SQLite for local development/demo when MongoDB is not available
"""
import os
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
import logging
import json
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class LocalDatabaseManager:
    def __init__(self, db_path='local_users.db'):
        """Initialize SQLite connection"""
        self.db_path = db_path
        self._init_db()
        logger.info(f"✅ Local SQLite database initialized at {db_path}")
    
    def _get_connection(self):
        """Get database connection"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def _init_db(self):
        """Initialize database tables"""
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT,
                auth_type TEXT DEFAULT 'local',
                profile_pic TEXT,
                oauth_id TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login TIMESTAMP
            )
        ''')
        
        conn.commit()
        conn.close()
        logger.info("Database tables initialized")
    
    def create_user(self, username, email, password, auth_type='local', profile_pic=None):
        """Create a new user in the database"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            # Check if user already exists
            cursor.execute("SELECT id FROM users WHERE username = ?", (username,))
            if cursor.fetchone():
                conn.close()
                return {"success": False, "message": "Username already exists"}
            
            cursor.execute("SELECT id FROM users WHERE email = ?", (email,))
            if cursor.fetchone():
                conn.close()
                return {"success": False, "message": "Email already registered"}
            
            # Hash password for local auth
            password_hash = None
            if auth_type == 'local' and password:
                password_hash = generate_password_hash(password)
            
            # Insert user
            cursor.execute('''
                INSERT INTO users (username, email, password_hash, auth_type, profile_pic, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (username, email, password_hash, auth_type, profile_pic, datetime.now()))
            
            conn.commit()
            user_id = cursor.lastrowid
            conn.close()
            
            logger.info(f"User {username} created successfully with ID {user_id}")
            return {"success": True, "user_id": str(user_id)}
                
        except Exception as e:
            logger.error(f"Error creating user: {e}")
            return {"success": False, "message": str(e)}
    
    def authenticate_user(self, username, password):
        """Authenticate user with username and password"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            cursor.execute(
                "SELECT * FROM users WHERE username = ? AND auth_type = 'local'",
                (username,)
            )
            row = cursor.fetchone()
            
            if row:
                user = dict(row)
                password_hash = user.get("password_hash", "")
                if password_hash and check_password_hash(password_hash, password):
                    # Update last login
                    cursor.execute(
                        "UPDATE users SET last_login = ? WHERE id = ?",
                        (datetime.now(), user["id"])
                    )
                    conn.commit()
                    conn.close()
                    return {"success": True, "user": self._format_user(user)}
            
            conn.close()
            return {"success": False, "message": "Invalid username or password"}
                
        except Exception as e:
            logger.error(f"Error authenticating user: {e}")
            return {"success": False, "message": str(e)}
    
    def get_user_by_id(self, user_id):
        """Get user by ID"""
        try:
            conn = self._get_connection()
            cursor = conn.cursor()
            
            cursor.execute("SELECT * FROM users WHERE id = ?", (int(user_id),))
            row = cursor.fetchone()
            conn.close()
            
            if row:
                return self._format_user(dict(row))
            return None
            
        except Exception as e:
            logger.error(f"Error getting user by ID: {e}")
            return None
    
    def get_or_create_oauth_user(self, user_info, auth_type='google'):
        """Get or create user from OAuth provider"""
        try:
            email = user_info.get("email")
            
            conn = self._get_connection()
            cursor = conn.cursor()
            
            # Try to find existing user by email
            cursor.execute("SELECT * FROM users WHERE email = ?", (email,))
            row = cursor.fetchone()
            
            if row:
                user = dict(row)
                # Update last login
                cursor.execute(
                    "UPDATE users SET last_login = ? WHERE id = ?",
                    (datetime.now(), user["id"])
                )
                conn.commit()
                conn.close()
                return {"success": True, "user": self._format_user(user)}
            else:
                # Create new OAuth user
                username = user_info.get("name", "").replace(" ", "_").lower()
                profile_pic = user_info.get("picture")
                oauth_id = user_info.get("sub")
                
                cursor.execute('''
                    INSERT INTO users (username, email, auth_type, profile_pic, oauth_id, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (username, email, auth_type, profile_pic, oauth_id, datetime.now()))
                
                conn.commit()
                user_id = cursor.lastrowid
                
                # Fetch the created user
                cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
                row = cursor.fetchone()
                conn.close()
                
                if row:
                    return {"success": True, "user": self._format_user(dict(row))}
                else:
                    return {"success": False, "message": "Failed to create OAuth user"}
                    
        except Exception as e:
            logger.error(f"Error with OAuth user: {e}")
            return {"success": False, "message": str(e)}
    
    def _format_user(self, user_dict):
        """Format user dict for application use"""
        if not user_dict:
            return None
            
        return {
            "id": str(user_dict["id"]),
            "username": user_dict.get("username"),
            "email": user_dict.get("email"),
            "auth_type": user_dict.get("auth_type", "local"),
            "profile_pic": user_dict.get("profile_pic"),
            "created_at": user_dict.get("created_at"),
            "last_login": user_dict.get("last_login")
        }
    
    def migrate_users_from_json(self, json_file_path):
        """Migrate users from JSON file to SQLite"""
        try:
            with open(json_file_path, 'r') as f:
                users_data = json.load(f)
            
            migrated_count = 0
            for user_data in users_data:
                # Check if user already exists
                conn = self._get_connection()
                cursor = conn.cursor()
                
                cursor.execute(
                    "SELECT id FROM users WHERE username = ? OR email = ?",
                    (user_data.get("name"), user_data.get("email"))
                )
                
                if not cursor.fetchone():
                    cursor.execute('''
                        INSERT INTO users (username, email, password_hash, auth_type, profile_pic, created_at)
                        VALUES (?, ?, ?, ?, ?, ?)
                    ''', (
                        user_data.get("name"),
                        user_data.get("email"),
                        user_data.get("password_hash"),
                        user_data.get("auth_type", "local"),
                        user_data.get("profile_pic"),
                        datetime.now()
                    ))
                    conn.commit()
                    migrated_count += 1
                    logger.info(f"Migrated user: {user_data.get('name')}")
                
                conn.close()
            
            logger.info(f"Migration completed. {migrated_count} users migrated.")
            return {"success": True, "migrated_count": migrated_count}
            
        except Exception as e:
            logger.error(f"Error migrating users: {e}")
            return {"success": False, "message": str(e)}
    
    def close_connection(self):
        """Close connection (no-op for SQLite as we open/close per operation)"""
        logger.info("SQLite database manager closed")


# Global database manager instance
db_manager = None

def init_local_database(db_path='local_users.db'):
    """Initialize local database connection"""
    global db_manager
    db_manager = LocalDatabaseManager(db_path)
    return db_manager

def get_local_db():
    """Get local database manager instance"""
    global db_manager
    if db_manager is None:
        db_manager = init_local_database()
    return db_manager
