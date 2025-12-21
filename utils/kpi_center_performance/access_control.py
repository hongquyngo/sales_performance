# utils/kpi_center_performance/access_control.py
"""
Access Control for KPI Center Performance

Simplified access control - page-level only:
- Only admin, GM, MD, sales_manager can access this page
- All allowed users can view all KPI Centers

No complex hierarchy like salesperson module.

VERSION: 1.0.0
"""

import logging
from typing import List, Optional
import pandas as pd

from .constants import ALLOWED_ROLES

logger = logging.getLogger(__name__)


class AccessControl:
    """
    Simplified access control for KPI Center Performance page.
    
    Unlike salesperson module which has full/team/self access levels,
    this module only checks if user's role is in ALLOWED_ROLES.
    All allowed users can see all KPI Centers.
    
    Usage:
        access = AccessControl(user_role=st.session_state.user_role)
        
        # Check if user can access page
        if not access.can_access_page():
            st.error("Access denied")
            st.stop()
        
        # All allowed users have full access to all KPI Centers
        kpi_center_ids = access.get_accessible_kpi_center_ids()
    """
    
    def __init__(self, user_role: str):
        """
        Initialize access control.
        
        Args:
            user_role: User's role from session (e.g., 'admin', 'sales_manager')
        """
        self.user_role = user_role.lower() if user_role else ''
        self._accessible_ids: Optional[List[int]] = None
        
        logger.info(f"KPICenterAccessControl initialized: role={self.user_role}")
    
    # =========================================================================
    # PAGE ACCESS CHECK
    # =========================================================================
    
    def can_access_page(self) -> bool:
        """
        Check if user can access KPI Center Performance page.
        
        Returns:
            True if user's role is in ALLOWED_ROLES
        """
        allowed_roles_lower = [r.lower() for r in ALLOWED_ROLES]
        can_access = self.user_role in allowed_roles_lower
        
        if not can_access:
            logger.warning(
                f"Access denied for role '{self.user_role}'. "
                f"Allowed roles: {ALLOWED_ROLES}"
            )
        
        return can_access
    
    def get_access_level(self) -> str:
        """
        Get access level - always 'full' for allowed users.
        
        This method exists for compatibility with salesperson module patterns.
        All allowed users have full access to all KPI Centers.
        
        Returns:
            'full' if user can access, 'none' otherwise
        """
        return 'full' if self.can_access_page() else 'none'
    
    # =========================================================================
    # KPI CENTER ACCESS
    # =========================================================================
    
    def get_accessible_kpi_center_ids(self) -> List[int]:
        """
        Get list of KPI Center IDs that user can access.
        
        For allowed users, returns all KPI Centers with data.
        Results are cached after first call.
        
        Returns:
            List of KPI Center IDs (empty if no access)
        """
        if not self.can_access_page():
            return []
        
        if self._accessible_ids is not None:
            return self._accessible_ids
        
        self._accessible_ids = self._get_all_kpi_center_ids()
        logger.info(f"Accessible KPI Centers: {len(self._accessible_ids)}")
        
        return self._accessible_ids
    
    def _get_all_kpi_center_ids(self) -> List[int]:
        """
        Get all KPI Center IDs that have sales data.
        """
        from sqlalchemy import text
        from utils.db import get_db_engine
        
        query = """
            SELECT DISTINCT kpi_center_id 
            FROM unified_sales_by_kpi_center_view
            WHERE kpi_center_id IS NOT NULL
            ORDER BY kpi_center_id
        """
        
        try:
            engine = get_db_engine()
            with engine.connect() as conn:
                result = conn.execute(text(query))
                ids = [row[0] for row in result]
                logger.debug(f"Found {len(ids)} KPI Centers with data")
                return ids
        except Exception as e:
            logger.error(f"Error fetching KPI Center IDs: {e}")
            return []
    
    # =========================================================================
    # DATA FILTERING
    # =========================================================================
    
    def filter_dataframe(
        self, 
        df: pd.DataFrame, 
        kpi_center_id_col: str = 'kpi_center_id'
    ) -> pd.DataFrame:
        """
        Filter DataFrame to only include accessible KPI Centers.
        
        For this simplified module, this essentially does nothing for
        allowed users (they can see all), but returns empty for denied users.
        
        Args:
            df: DataFrame to filter
            kpi_center_id_col: Column name containing KPI Center IDs
            
        Returns:
            Filtered DataFrame
        """
        if df.empty:
            return df
        
        if not self.can_access_page():
            logger.warning("Access denied, returning empty DataFrame")
            return df.head(0)
        
        # For allowed users, return all data
        return df
    
    def validate_selected_kpi_centers(
        self, 
        selected_ids: List[int]
    ) -> List[int]:
        """
        Validate and filter selected KPI Center IDs against access rights.
        
        For allowed users, all selections are valid.
        
        Args:
            selected_ids: List of KPI Center IDs user selected
            
        Returns:
            List of valid KPI Center IDs
        """
        if not self.can_access_page():
            return []
        
        accessible_ids = set(self.get_accessible_kpi_center_ids())
        valid_ids = [id for id in selected_ids if id in accessible_ids]
        
        if len(valid_ids) < len(selected_ids):
            logger.warning(
                f"Some selected KPI Centers not found in accessible list: "
                f"selected={len(selected_ids)}, valid={len(valid_ids)}"
            )
        
        return valid_ids
    
    # =========================================================================
    # HELPER METHODS
    # =========================================================================
    
    def can_select_kpi_center(self) -> bool:
        """Check if user can select different KPI Centers."""
        return self.can_access_page()
    
    def get_denied_message(self) -> str:
        """Get access denied message for display."""
        return (
            f"🚫 Access Denied\n\n"
            f"Your role '{self.user_role}' does not have permission to access "
            f"the KPI Center Performance page.\n\n"
            f"Allowed roles: {', '.join(ALLOWED_ROLES)}"
        )
    
    def __repr__(self) -> str:
        return (
            f"KPICenterAccessControl(role='{self.user_role}', "
            f"can_access={self.can_access_page()})"
        )
