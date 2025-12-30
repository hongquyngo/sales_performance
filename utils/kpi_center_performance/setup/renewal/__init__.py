# utils/kpi_center_performance/setup/renewal/__init__.py
"""
Renewal Module for KPI Center Split Rules

Provides functionality to:
1. Detect expiring split rules with recent sales activity
2. Bulk renew selected rules with new validity period
3. Preview and confirm renewal operations

Usage:
    from utils.kpi_center_performance.setup.renewal import renewal_section
    
    # In toolbar - single component handles button + dialog
    renewal_section(
        user_id=setup_queries.user_id,
        can_approve=can_approve,
        threshold_days=30
    )
"""

from .queries import RenewalQueries
from .fragments import (
    # Main entry point (recommended)
    renewal_section,
    
    # Constants
    RENEWAL_STRATEGIES,
    DEFAULT_THRESHOLD_DAYS,
    
    # Deprecated - kept for backward compatibility
    renewal_trigger_button,
    check_and_show_renewal_dialog,
    renewal_dialog_fragment,
)

__all__ = [
    # Queries
    'RenewalQueries',
    
    # Main entry point (recommended)
    'renewal_section',
    
    # Constants
    'RENEWAL_STRATEGIES',
    'DEFAULT_THRESHOLD_DAYS',
    
    # Deprecated
    'renewal_trigger_button',
    'check_and_show_renewal_dialog',
    'renewal_dialog_fragment',
]

__version__ = '1.1.0'

__all__ = [
    # Queries
    'RenewalQueries',
    
    # Fragments
    'renewal_dialog_fragment',
    'renewal_trigger_button',
    
    # Constants
    'RENEWAL_STRATEGIES',
    'DEFAULT_THRESHOLD_DAYS',
]

__version__ = '1.0.0'