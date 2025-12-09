# utils/auth.py
"""
Authentication Manager for Streamlit Apps

Version: 2.0.0
Features:
- SHA256 password hashing (compatible with existing database)
- Role-based access control
- Session management with timeout
- Backward compatible with existing apps
"""

import streamlit as st
import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple, List
from functools import wraps
import logging
from sqlalchemy import text
from .db import get_db_engine
from .config import config

logger = logging.getLogger(__name__)


class AuthManager:
    """Authentication manager for Streamlit apps"""
    
    def __init__(self):
        self.session_timeout = timedelta(
            hours=config.get_app_setting("SESSION_TIMEOUT_HOURS", 8)
        )
    
    # ==================== PASSWORD HASHING ====================
    
    def hash_password(self, password: str, salt: str = None) -> Tuple[str, str]:
        """
        Hash password with SHA256 + salt
        
        Args:
            password: Plain text password
            salt: Optional salt (generated if not provided)
            
        Returns:
            Tuple of (hash, salt)
        """
        if not salt:
            salt = secrets.token_hex(32)
        
        pwd_hash = hashlib.sha256((password + salt).encode()).hexdigest()
        return pwd_hash, salt
    
    def verify_password(self, password: str, stored_hash: str, salt: str) -> bool:
        """
        Verify password against stored hash
        
        Args:
            password: Plain text password
            stored_hash: Stored password hash
            salt: Password salt
            
        Returns:
            True if password matches
        """
        pwd_hash, _ = self.hash_password(password, salt)
        return pwd_hash == stored_hash
    
    # ==================== AUTHENTICATION ====================
    
    def authenticate(self, username: str, password: str) -> Tuple[bool, Optional[Dict]]:
        """
        Authenticate user against database
        
        Args:
            username: User's username
            password: Plain text password
            
        Returns:
            Tuple of (success: bool, user_info: dict or error: dict)
        """
        try:
            engine = get_db_engine()
            
            query = text("""
                SELECT 
                    u.id,
                    u.username,
                    u.password_hash,
                    u.password_salt,
                    u.email,
                    u.role,
                    u.is_active,
                    u.last_login,
                    u.employee_id,
                    e.id as emp_id,
                    e.keycloak_id,
                    CONCAT(e.first_name, ' ', e.last_name) as full_name
                FROM users u
                LEFT JOIN employees e ON u.employee_id = e.id
                WHERE u.username = :username
                AND u.delete_flag = 0
            """)
            
            with engine.connect() as conn:
                result = conn.execute(query, {'username': username}).fetchone()
            
            if not result:
                logger.warning(f"Login attempt for non-existent user: {username}")
                return False, {"error": "Invalid username or password"}
            
            user = dict(result._mapping)
            
            # Check if account is active
            if not user['is_active']:
                logger.warning(f"Login attempt for inactive user: {username}")
                return False, {"error": "Account is inactive. Please contact administrator."}
            
            # Verify password
            if not self.verify_password(password, user['password_hash'], user['password_salt']):
                logger.warning(f"Invalid password for user: {username}")
                return False, {"error": "Invalid username or password"}
            
            # Update last login
            self._update_last_login(user['id'])
            
            logger.info(f"User {username} authenticated successfully")
            
            return True, {
                'id': user['id'],
                'username': user['username'],
                'email': user['email'],
                'role': user['role'],
                'employee_id': user['employee_id'],
                'keycloak_id': user.get('keycloak_id'),
                'full_name': user['full_name'] or user['username'],
                'login_time': datetime.now()
            }
            
        except Exception as e:
            logger.error(f"Authentication error: {e}")
            return False, {"error": "Authentication failed. Please try again."}
    
    def _update_last_login(self, user_id: int):
        """Update user's last login timestamp"""
        try:
            engine = get_db_engine()
            query = text("UPDATE users SET last_login = NOW() WHERE id = :user_id")
            
            with engine.connect() as conn:
                conn.execute(query, {'user_id': user_id})
                conn.commit()
        except Exception as e:
            logger.warning(f"Could not update last_login: {e}")
    
    # ==================== SESSION MANAGEMENT ====================
    
    def check_session(self) -> bool:
        """Check if user session is valid and not expired"""
        if 'authenticated' not in st.session_state:
            return False
        
        if not st.session_state.authenticated:
            return False
        
        # Check session timeout
        login_time = st.session_state.get('login_time')
        if login_time:
            elapsed = datetime.now() - login_time
            if elapsed > self.session_timeout:
                logger.info(f"Session expired for user: {st.session_state.get('username')}")
                self.logout()
                return False
        
        return True
    
    def login(self, user_info: Dict):
        """Initialize user session after successful authentication"""
        st.session_state.authenticated = True
        st.session_state.user_id = user_info['id']
        st.session_state.username = user_info['username']
        st.session_state.user_email = user_info['email']
        st.session_state.user_keycloak_id = user_info.get('keycloak_id')
        st.session_state.user_role = user_info['role']
        st.session_state.user_fullname = user_info['full_name']
        st.session_state.employee_id = user_info['employee_id']
        st.session_state.login_time = user_info['login_time']
        
        # Initialize app-specific session vars
        st.session_state.debug_mode = False
        
        logger.info(f"User {user_info['username']} (keycloak_id: {user_info.get('keycloak_id')}) logged in successfully")
    
    def logout(self):
        """Clear user session and cache"""
        username = st.session_state.get('username', 'Unknown')
        
        # Keys to clear
        auth_keys = [
            'authenticated', 'user_id', 'username', 'user_email',
            'user_keycloak_id', 'user_role', 'user_fullname',
            'employee_id', 'login_time', 'debug_mode'
        ]
        
        for key in auth_keys:
            if key in st.session_state:
                del st.session_state[key]
        
        # Clear cache
        st.cache_data.clear()
        
        logger.info(f"User {username} logged out")
    
    # ==================== ACCESS CONTROL ====================
    
    def require_auth(self) -> bool:
        """
        Require authentication to access a page
        Use at the beginning of each protected page
        """
        if not self.check_session():
            st.warning("⚠️ Please login to access this page")
            st.stop()
            return False
        return True
    
    def require_role(self, allowed_roles: List[str]) -> bool:
        """
        Require specific role(s) to access a page
        
        Args:
            allowed_roles: List of role names that can access
            
        Usage:
            auth.require_role(['admin', 'manager'])
        """
        if not self.require_auth():
            return False
        
        current_role = st.session_state.get('user_role', '')
        
        if current_role not in allowed_roles:
            st.error(f"🚫 Access denied. Required role: {', '.join(allowed_roles)}")
            st.stop()
            return False
        
        return True
    
    def has_role(self, role: str) -> bool:
        """Check if current user has specific role"""
        return st.session_state.get('user_role', '') == role
    
    def is_admin(self) -> bool:
        """Check if current user is admin"""
        return self.has_role('admin')
    
    # ==================== USER INFO HELPERS ====================
    
    def get_user_display_name(self) -> str:
        """Get user's display name for UI"""
        if 'user_fullname' in st.session_state and st.session_state.user_fullname:
            return st.session_state.user_fullname
        return st.session_state.get('username', 'User')
    
    def get_user_keycloak_id(self) -> Optional[str]:
        """Get user's keycloak_id for database operations"""
        return st.session_state.get('user_keycloak_id')
    
    def get_user_id(self) -> Optional[int]:
        """Get current user's ID"""
        return st.session_state.get('user_id')
    
    def get_current_user(self) -> Dict:
        """Get all current user info as dictionary"""
        return {
            'id': st.session_state.get('user_id'),
            'username': st.session_state.get('username'),
            'email': st.session_state.get('user_email'),
            'role': st.session_state.get('user_role'),
            'fullname': st.session_state.get('user_fullname'),
            'employee_id': st.session_state.get('employee_id'),
            'keycloak_id': st.session_state.get('user_keycloak_id'),
        }
    
    def update_session_activity(self):
        """Update session activity to prevent timeout (placeholder for future use)"""
        pass


# ==================== DECORATORS ====================

def require_login(func):
    """Decorator to require login for a function"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        auth = AuthManager()
        if auth.require_auth():
            return func(*args, **kwargs)
    return wrapper


def require_roles(*roles):
    """Decorator to require specific roles"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            auth = AuthManager()
            if auth.require_role(list(roles)):
                return func(*args, **kwargs)
        return wrapper
    return decorator


# ==================== MODULE EXPORTS ====================

__all__ = [
    'AuthManager',
    'require_login',
    'require_roles',
]
