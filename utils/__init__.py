# utils/__init__.py
"""
Shared Utilities Package for Streamlit Apps

This package contains common utilities shared across all pages:
- auth: Authentication and session management  
- config: Configuration management (local + Streamlit Cloud)
- db: Database connection management with pooling
- s3_utils: AWS S3 operations

Usage:
    # Import specific modules
    from utils.auth import AuthManager
    from utils.db import get_db_engine, execute_query
    from utils.config import config
    from utils.s3_utils import get_s3_manager
    
    # Or import commonly used items directly
    from utils import AuthManager, get_db_engine, config
"""

# Authentication
from .auth import (
    AuthManager,
    require_login,
    require_roles,
)

# Configuration  
from .config import (
    config,
    Config,
    IS_RUNNING_ON_CLOUD,
    DB_CONFIG,
    AWS_CONFIG,
    APP_CONFIG,
    EXCHANGE_RATE_API_KEY,
    EMAIL_SENDER,
    EMAIL_PASSWORD,
)

# Database
from .db import (
    get_db_engine,
    check_db_connection,
    reset_db_engine,
    get_connection,
    get_transaction,
    execute_query,
    execute_query_df,
    execute_update,
    execute_many,
    get_connection_pool_status,
)

# S3
from .s3_utils import (
    S3Manager,
    get_s3_manager,
    reset_s3_manager,
    upload_pdf,
    upload_image,
    get_company_logo,
    validate_s3_connection,
)

__all__ = [
    # Auth
    'AuthManager',
    'require_login',
    'require_roles',
    
    # Config
    'config',
    'Config',
    'IS_RUNNING_ON_CLOUD',
    'DB_CONFIG',
    'AWS_CONFIG',
    'APP_CONFIG',
    'EXCHANGE_RATE_API_KEY',
    'EMAIL_SENDER',
    'EMAIL_PASSWORD',
    
    # Database
    'get_db_engine',
    'check_db_connection',
    'reset_db_engine',
    'get_connection',
    'get_transaction',
    'execute_query',
    'execute_query_df',
    'execute_update',
    'execute_many',
    'get_connection_pool_status',
    
    # S3
    'S3Manager',
    'get_s3_manager',
    'reset_s3_manager',
    'upload_pdf',
    'upload_image',
    'get_company_logo',
    'validate_s3_connection',
]

__version__ = '2.0.0'
