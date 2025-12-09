# utils/config.py
"""
Centralized Configuration Management

Version: 2.0.0
Features:
- Support both local (.env) and Streamlit Cloud (secrets.toml)
- Singleton pattern for efficiency
- Type-safe getters with defaults
- Environment detection
"""

import os
import json
import logging
from pathlib import Path
from dotenv import load_dotenv
from typing import Dict, Any, Optional, Union
from dataclasses import dataclass, field

# Initialize logger
logger = logging.getLogger(__name__)


def is_running_on_streamlit_cloud() -> bool:
    """Detect if running on Streamlit Cloud"""
    try:
        import streamlit as st
        return hasattr(st, 'secrets') and len(st.secrets) > 0
    except Exception:
        return False


@dataclass
class DatabaseConfig:
    """Database configuration container"""
    host: str
    port: int
    user: str
    password: str
    database: str
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'host': self.host,
            'port': self.port,
            'user': self.user,
            'password': self.password,
            'database': self.database
        }


@dataclass
class AWSConfig:
    """AWS configuration container"""
    access_key_id: Optional[str] = None
    secret_access_key: Optional[str] = None
    region: str = "ap-southeast-1"
    bucket_name: str = "prostech-erp-dev"
    app_prefix: str = "streamlit-app"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'access_key_id': self.access_key_id,
            'secret_access_key': self.secret_access_key,
            'region': self.region,
            'bucket_name': self.bucket_name,
            'app_prefix': self.app_prefix
        }
    
    def is_configured(self) -> bool:
        return bool(self.access_key_id and self.secret_access_key)


@dataclass
class EmailConfig:
    """Email configuration container"""
    sender: Optional[str] = None
    password: Optional[str] = None
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    
    def is_configured(self) -> bool:
        return bool(self.sender and self.password)


class Config:
    """
    Centralized configuration management
    
    Usage:
        from utils.config import config
        
        # Get database config
        db_config = config.get_db_config()
        
        # Get AWS config
        aws_config = config.get_aws_config()
        
        # Get app settings
        timeout = config.get_app_setting("SESSION_TIMEOUT_HOURS", 8)
        
        # Check feature flags
        if config.is_feature_enabled("ANALYTICS"):
            ...
    """
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self.is_cloud = is_running_on_streamlit_cloud()
        self._load_config()
        self._initialized = True
    
    def _load_config(self):
        """Load configuration based on environment"""
        if self.is_cloud:
            self._load_cloud_config()
        else:
            self._load_local_config()
        
        self._load_app_config()
        self._log_config_status()
    
    def _load_cloud_config(self):
        """Load configuration from Streamlit Cloud secrets"""
        import streamlit as st
        
        # Database
        db_secrets = st.secrets.get("DB_CONFIG", {})
        self._db_config = DatabaseConfig(
            host=db_secrets.get("host", ""),
            port=int(db_secrets.get("port", 3306)),
            user=db_secrets.get("user", ""),
            password=db_secrets.get("password", ""),
            database=db_secrets.get("database", "prostechvn")
        )
        
        # AWS
        aws_secrets = st.secrets.get("AWS", {})
        self._aws_config = AWSConfig(
            access_key_id=aws_secrets.get("ACCESS_KEY_ID"),
            secret_access_key=aws_secrets.get("SECRET_ACCESS_KEY"),
            region=aws_secrets.get("REGION", "ap-southeast-1"),
            bucket_name=aws_secrets.get("BUCKET_NAME", "prostech-erp-dev"),
            app_prefix=aws_secrets.get("APP_PREFIX", "streamlit-app")
        )
        
        # API Keys
        api_secrets = st.secrets.get("API", {})
        self._api_keys = {
            "exchange_rate": api_secrets.get("EXCHANGE_RATE_API_KEY")
        }
        
        # Email - Support multiple accounts
        email_secrets = st.secrets.get("EMAIL", {})
        self._email_config = {
            "inbound": EmailConfig(
                sender=email_secrets.get("INBOUND_EMAIL_SENDER"),
                password=email_secrets.get("INBOUND_EMAIL_PASSWORD"),
                smtp_host=email_secrets.get("SMTP_HOST", "smtp.gmail.com"),
                smtp_port=int(email_secrets.get("SMTP_PORT", 587))
            ),
            "outbound": EmailConfig(
                sender=email_secrets.get("OUTBOUND_EMAIL_SENDER"),
                password=email_secrets.get("OUTBOUND_EMAIL_PASSWORD"),
                smtp_host=email_secrets.get("SMTP_HOST", "smtp.gmail.com"),
                smtp_port=int(email_secrets.get("SMTP_PORT", 587))
            )
        }
        
        # Google Cloud
        self._google_service_account = dict(st.secrets.get("gcp_service_account", {}))
        
        logger.info("☁️ Running in STREAMLIT CLOUD")
    
    def _load_local_config(self):
        """Load configuration from local .env file"""
        # Find and load .env file
        env_paths = [
            Path.cwd() / ".env",
            Path(__file__).parent.parent / ".env",
        ]
        
        for env_path in env_paths:
            if env_path.exists():
                load_dotenv(env_path)
                logger.info(f"Loaded .env from: {env_path}")
                break
        
        # Database
        self._db_config = DatabaseConfig(
            host=os.getenv("DB_HOST", ""),
            port=int(os.getenv("DB_PORT", "3306")),
            user=os.getenv("DB_USER", ""),
            password=os.getenv("DB_PASSWORD", ""),
            database=os.getenv("DB_NAME", os.getenv("DB_DATABASE", "prostechvn"))
        )
        
        # Validate required DB config
        if not all([self._db_config.host, self._db_config.user, self._db_config.password]):
            logger.error("Missing required database configuration")
            raise ValueError("Missing required database configuration. Please check .env file.")
        
        # AWS
        self._aws_config = AWSConfig(
            access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
            secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
            region=os.getenv("AWS_REGION", "ap-southeast-1"),
            bucket_name=os.getenv("S3_BUCKET_NAME", "prostech-erp-dev"),
            app_prefix=os.getenv("S3_APP_PREFIX", "streamlit-app")
        )
        
        # API Keys
        self._api_keys = {
            "exchange_rate": os.getenv("EXCHANGE_RATE_API_KEY")
        }
        
        # Email
        self._email_config = {
            "inbound": EmailConfig(
                sender=os.getenv("INBOUND_EMAIL_SENDER"),
                password=os.getenv("INBOUND_EMAIL_PASSWORD"),
                smtp_host=os.getenv("SMTP_HOST", "smtp.gmail.com"),
                smtp_port=int(os.getenv("SMTP_PORT", "587"))
            ),
            "outbound": EmailConfig(
                sender=os.getenv("OUTBOUND_EMAIL_SENDER"),
                password=os.getenv("OUTBOUND_EMAIL_PASSWORD"),
                smtp_host=os.getenv("SMTP_HOST", "smtp.gmail.com"),
                smtp_port=int(os.getenv("SMTP_PORT", "587"))
            )
        }
        
        # Google Cloud
        self._google_service_account = {}
        credentials_path = os.getenv("GOOGLE_CREDENTIALS_PATH", "credentials.json")
        if os.path.exists(credentials_path):
            try:
                with open(credentials_path, "r") as f:
                    self._google_service_account = json.load(f)
            except Exception as e:
                logger.warning(f"Could not load Google credentials: {e}")
        
        logger.info("💻 Running in LOCAL environment")
    
    def _load_app_config(self):
        """Load application-specific settings"""
        self._app_config = {
            # Session
            "SESSION_TIMEOUT_HOURS": int(os.getenv("SESSION_TIMEOUT_HOURS", "8")),
            
            # Business logic
            "MAX_EMAIL_RECIPIENTS": int(os.getenv("MAX_EMAIL_RECIPIENTS", "50")),
            "DELIVERY_WEEKS_AHEAD": int(os.getenv("DELIVERY_WEEKS_AHEAD", "4")),
            "PO_WEEKS_AHEAD": int(os.getenv("PO_WEEKS_AHEAD", "8")),
            
            # Database pool
            "DB_POOL_SIZE": int(os.getenv("DB_POOL_SIZE", "5")),
            "DB_POOL_RECYCLE": int(os.getenv("DB_POOL_RECYCLE", "3600")),
            
            # Cache
            "CACHE_TTL_SECONDS": int(os.getenv("CACHE_TTL_SECONDS", "300")),
            
            # Localization
            "TIMEZONE": os.getenv("TIMEZONE", "Asia/Ho_Chi_Minh"),
            
            # Feature flags
            "ENABLE_ANALYTICS": os.getenv("ENABLE_ANALYTICS", "true").lower() == "true",
            "ENABLE_EMAIL_NOTIFICATIONS": os.getenv("ENABLE_EMAIL_NOTIFICATIONS", "true").lower() == "true",
            "ENABLE_CALENDAR_INTEGRATION": os.getenv("ENABLE_CALENDAR_INTEGRATION", "true").lower() == "true",
            "ENABLE_DEBUG_MODE": os.getenv("ENABLE_DEBUG_MODE", "false").lower() == "true",
        }
    
    def _log_config_status(self):
        """Log configuration status"""
        logger.info(f"✅ Database: {self._db_config.host}/{self._db_config.database}")
        logger.info(f"✅ AWS S3: {'Configured' if self._aws_config.is_configured() else 'Not configured'}")
        logger.info(f"✅ Exchange API: {'Configured' if self._api_keys.get('exchange_rate') else 'Missing'}")
        logger.info(f"✅ Google: {'Loaded' if self._google_service_account else 'Not configured'}")
    
    # ==================== PUBLIC GETTERS ====================
    
    def get_db_config(self) -> Dict[str, Any]:
        """Get database configuration as dictionary"""
        return self._db_config.to_dict()
    
    def get_aws_config(self) -> Dict[str, Any]:
        """Get AWS configuration as dictionary"""
        return self._aws_config.to_dict()
    
    def get_email_config(self, module: str = "outbound") -> Dict[str, Any]:
        """Get email configuration for specific module"""
        email = self._email_config.get(module, self._email_config["outbound"])
        return {
            "sender": email.sender,
            "password": email.password,
            "host": email.smtp_host,
            "port": email.smtp_port
        }
    
    def get_api_key(self, service: str) -> Optional[str]:
        """Get API key for specific service"""
        return self._api_keys.get(service)
    
    def get_google_service_account(self) -> Dict[str, Any]:
        """Get Google service account configuration"""
        return self._google_service_account.copy()
    
    def get_app_setting(self, key: str, default: Any = None) -> Any:
        """Get application setting with default"""
        return self._app_config.get(key, default)
    
    def is_feature_enabled(self, feature: str) -> bool:
        """Check if feature is enabled"""
        key = f"ENABLE_{feature.upper()}"
        return self._app_config.get(key, True)
    
    # ==================== PROPERTIES ====================
    
    @property
    def db_config(self) -> Dict[str, Any]:
        """Backward compatible property"""
        return self.get_db_config()
    
    @property
    def aws_config(self) -> Dict[str, Any]:
        """Backward compatible property"""
        return self.get_aws_config()
    
    @property
    def app_config(self) -> Dict[str, Any]:
        """Backward compatible property"""
        return self._app_config.copy()


# ==================== SINGLETON INSTANCE ====================

config = Config()

# ==================== BACKWARD COMPATIBILITY EXPORTS ====================

IS_RUNNING_ON_CLOUD = config.is_cloud
DB_CONFIG = config.db_config
AWS_CONFIG = config.aws_config
APP_CONFIG = config.app_config
EXCHANGE_RATE_API_KEY = config.get_api_key("exchange_rate")
GOOGLE_SERVICE_ACCOUNT_JSON = config.get_google_service_account()

# Email exports
INBOUND_EMAIL_CONFIG = config.get_email_config("inbound")
OUTBOUND_EMAIL_CONFIG = config.get_email_config("outbound")
EMAIL_SENDER = config.get_email_config("outbound").get("sender")
EMAIL_PASSWORD = config.get_email_config("outbound").get("password")

__all__ = [
    'config',
    'Config',
    'IS_RUNNING_ON_CLOUD',
    'DB_CONFIG',
    'AWS_CONFIG',
    'APP_CONFIG',
    'EXCHANGE_RATE_API_KEY',
    'GOOGLE_SERVICE_ACCOUNT_JSON',
    'EMAIL_SENDER',
    'EMAIL_PASSWORD',
    'INBOUND_EMAIL_CONFIG',
    'OUTBOUND_EMAIL_CONFIG',
]
