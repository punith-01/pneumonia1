"""
Database module for MongoDB operations
"""
import os
import certifi
from pymongo import MongoClient
from werkzeug.security import generate_password_hash, check_password_hash
from bson.objectid import ObjectId
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DatabaseManager:
    def __init__(self, mongodb_uri, database_name):
        """Initialize MongoDB connection"""
        try:
            # Configure MongoDB client with proper SSL/TLS settings using certifi
            self.client = MongoClient(
                mongodb_uri,
                tlsCAFile=certifi.where(),  # Use certifi for SSL certificates
                serverSelectionTimeoutMS=10000,
                connectTimeoutMS=10000,
                socketTimeoutMS=10000,
                retryWrites=True,
                w='majority'
            )
            self.db = self.client[database_name]
            self.users_collection = self.db.users
            
            # Test connection
            self.client.admin.command('ping')
            logger.info("✅ Successfully connected to MongoDB Atlas!")
            
            # Create indexes for better performance
            try:
                self.users_collection.create_index("username", unique=True)
                self.users_collection.create_index("email", unique=True)
                logger.info("Database indexes created successfully")
            except Exception as idx_error:
                logger.warning(f"Index creation warning (may already exist): {idx_error}")
            
        except Exception as e:
            logger.error(f"Failed to connect to MongoDB: {e}")
            raise e
    
    def create_user(self, username, email, password, auth_type='local', profile_pic=None):
        """Create a new user in the database"""
        try:
            # Check if user already exists
            if self.users_collection.find_one({"username": username}):
                return {"success": False, "message": "Username already exists"}
            
            if self.users_collection.find_one({"email": email}):
                return {"success": False, "message": "Email already registered"}
            
            # Create user document
            user_doc = {
                "username": username,
                "email": email,
                "auth_type": auth_type,
                "profile_pic": profile_pic,
                "created_at": None,  # Will be set by MongoDB
                "last_login": None
            }
            
            # Hash password for local auth
            if auth_type == 'local' and password:
                user_doc["password_hash"] = generate_password_hash(password)
            
            # Insert user
            result = self.users_collection.insert_one(user_doc)
            
            if result.inserted_id:
                logger.info(f"User {username} created successfully")
                return {"success": True, "user_id": str(result.inserted_id)}
            else:
                return {"success": False, "message": "Failed to create user"}
                
        except Exception as e:
            logger.error(f"Error creating user: {e}")
            return {"success": False, "message": str(e)}
    
    def authenticate_user(self, username, password):
        """Authenticate user with username and password"""
        try:
            user = self.users_collection.find_one({"username": username, "auth_type": "local"})
            
            if user:
                password_hash = user.get("password_hash", "")
                if password_hash and check_password_hash(password_hash, password):
                    # Update last login
                    self.users_collection.update_one(
                        {"_id": user["_id"]},
                        {"$currentDate": {"last_login": True}}
                    )
                    return {"success": True, "user": self._format_user(user)}
            
            return {"success": False, "message": "Invalid username or password"}
                
        except Exception as e:
            logger.error(f"Error authenticating user: {e}")
            return {"success": False, "message": str(e)}
    
    def get_user_by_id(self, user_id):
        """Get user by ID - handles both ObjectId and legacy string IDs"""
        try:
            # Try ObjectId first (new MongoDB format)
            try:
                user = self.users_collection.find_one({"_id": ObjectId(user_id)})
                if user:
                    return self._format_user(user)
            except:
                pass
            
            # Try legacy string ID format (for migration)
            user = self.users_collection.find_one({"legacy_id": user_id})
            if user:
                return self._format_user(user)
                
            return None
        except Exception as e:
            logger.error(f"Error getting user by ID: {e}")
            return None
    
    def get_or_create_oauth_user(self, user_info, auth_type='google'):
        """Get or create user from OAuth provider"""
        try:
            # Try to find existing user by email
            user = self.users_collection.find_one({"email": user_info.get("email")})
            
            if user:
                # Update last login
                self.users_collection.update_one(
                    {"_id": user["_id"]},
                    {"$currentDate": {"last_login": True}}
                )
                return {"success": True, "user": self._format_user(user)}
            else:
                # Create new OAuth user
                user_doc = {
                    "username": user_info.get("name", "").replace(" ", "_").lower(),
                    "email": user_info.get("email"),
                    "auth_type": auth_type,
                    "profile_pic": user_info.get("picture"),
                    "oauth_id": user_info.get("sub"),
                    "created_at": None,
                    "last_login": None
                }
                
                result = self.users_collection.insert_one(user_doc)
                
                if result.inserted_id:
                    user_doc["_id"] = result.inserted_id
                    return {"success": True, "user": self._format_user(user_doc)}
                else:
                    return {"success": False, "message": "Failed to create OAuth user"}
                    
        except Exception as e:
            logger.error(f"Error with OAuth user: {e}")
            return {"success": False, "message": str(e)}
    
    def _format_user(self, user_doc):
        """Format user document for application use"""
        if not user_doc:
            return None
            
        return {
            "id": str(user_doc["_id"]),
            "username": user_doc.get("username"),
            "email": user_doc.get("email"),
            "auth_type": user_doc.get("auth_type", "local"),
            "profile_pic": user_doc.get("profile_pic"),
            "created_at": user_doc.get("created_at"),
            "last_login": user_doc.get("last_login")
        }
    
    def migrate_users_from_json(self, json_file_path):
        """Migrate users from JSON file to MongoDB"""
        try:
            import json
            with open(json_file_path, 'r') as f:
                users_data = json.load(f)
            
            migrated_count = 0
            for user_data in users_data:
                # Check if user already exists
                existing_user = self.users_collection.find_one({
                    "$or": [
                        {"username": user_data.get("name")},
                        {"email": user_data.get("email")},
                        {"legacy_id": user_data.get("id")}
                    ]
                })
                
                if not existing_user:
                    # Create new user document
                    user_doc = {
                        "username": user_data.get("name"),
                        "email": user_data.get("email"),
                        "auth_type": user_data.get("auth_type", "local"),
                        "profile_pic": user_data.get("profile_pic"),
                        "password_hash": user_data.get("password_hash"),
                        "legacy_id": user_data.get("id"),  # Keep legacy ID for reference
                        "created_at": None,
                        "last_login": None
                    }
                    
                    result = self.users_collection.insert_one(user_doc)
                    if result.inserted_id:
                        migrated_count += 1
                        logger.info(f"Migrated user: {user_data.get('name')}")
            
            logger.info(f"Migration completed. {migrated_count} users migrated.")
            return {"success": True, "migrated_count": migrated_count}
            
        except Exception as e:
            logger.error(f"Error migrating users: {e}")
            return {"success": False, "message": str(e)}
    
    def close_connection(self):
        """Close MongoDB connection"""
        if self.client:
            self.client.close()
            logger.info("MongoDB connection closed")

# Global database manager instance
db_manager = None

def init_database():
    """Initialize database connection"""
    global db_manager
    mongodb_uri = os.getenv('MONGODB_URI')
    database_name = os.getenv('DATABASE_NAME', 'pneumonia_detection')
    
    if not mongodb_uri:
        raise ValueError("MONGODB_URI environment variable is required")
    
    db_manager = DatabaseManager(mongodb_uri, database_name)
    return db_manager

def get_db():
    """Get database manager instance"""
    global db_manager
    if db_manager is None:
        db_manager = init_database()
    return db_manager
