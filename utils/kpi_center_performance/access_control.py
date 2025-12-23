# utils/kpi_center_performance/access_control.py
"""
Access Control for KPI Center Performance Module

Handles role-based access control for KPI Center data.

VERSION: 2.0.0
"""

import logging
from typing import List, Optional
import streamlit as st

from .constants import ALLOWED_ROLES

logger = logging.getLogger(__name__)


class AccessControl:
    """
    Access control for KPI Center Performance page.
    
    KPI Center uses a simpler access model than Salesperson:
    - ALLOWED_ROLES can access all KPI Centers
    - No hierarchy-based restrictions (parent-child access is for rollup, not restriction)
    
    Usage:
        access = AccessControl(user_role)
        if access.can_access_page():
            kpi_centers = access.get_accessible_kpi_center_ids()
    """
    
    def __init__(self, user_role: str):
        """
        Initialize access control.
        
        Args:
            user_role: Current user's role
        """
        self.user_role = user_role
        self._kpi_center_ids = None
    
    def can_access_page(self) -> bool:
        """Check if user can access KPI Center Performance page."""
        return self.user_role in ALLOWED_ROLES
    
    def get_access_level(self) -> str:
        """
        Get access level for current user.
        
        Returns:
            'full' for allowed roles, 'none' otherwise
        """
        if self.user_role in ALLOWED_ROLES:
            return 'full'
        return 'none'
    
    def get_accessible_kpi_center_ids(self) -> List[int]:
        """
        Get list of KPI Center IDs accessible to user.
        
        For allowed roles, returns all KPI Centers.
        
        Returns:
            List of kpi_center_id values
        """
        if not self.can_access_page():
            return []
        
        if self._kpi_center_ids is not None:
            return self._kpi_center_ids
        
        # Get all KPI Centers
        try:
            from utils.db import get_db_engine
            from sqlalchemy import text
            
            engine = get_db_engine()
            query = """
                SELECT DISTINCT id 
                FROM kpi_centers 
                WHERE delete_flag = 0
                ORDER BY id
            """
            
            with engine.connect() as conn:
                result = conn.execute(text(query))
                self._kpi_center_ids = [row[0] for row in result]
            
            return self._kpi_center_ids
            
        except Exception as e:
            logger.error(f"Error fetching KPI Center IDs: {e}")
            return []
    
    def validate_selected_kpi_centers(self, selected_ids: List[int]) -> List[int]:
        """
        Validate that selected KPI Centers are accessible.
        
        Args:
            selected_ids: List of selected KPI Center IDs
            
        Returns:
            List of valid KPI Center IDs
        """
        if not self.can_access_page():
            return []
        
        # For full access, all selections are valid
        return selected_ids
    
    def get_denied_message(self) -> str:
        """Get message to show when access is denied."""
        return f"⚠️ Access Denied. Your role ({self.user_role}) does not have permission to view KPI Center Performance. Required roles: {', '.join(ALLOWED_ROLES)}"
    
    def __repr__(self) -> str:
        return f"AccessControl(role={self.user_role}, level={self.get_access_level()})"