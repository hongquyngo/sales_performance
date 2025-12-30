# utils/kpi_center_performance/setup/renewal/__init__.py
"""
Renewal Module for KPI Center Split Rules

Provides functionality to:
1. Detect expiring split rules with recent sales activity
2. Bulk renew selected rules with new validity period
3. Preview and confirm renewal operations

Usage:
    from utils.kpi_center_performance.setup.renewal import (
        RenewalQueries,
        renewal_dialog_fragment,
        renewal_trigger_button,
    )
    
    # Or from parent setup module:
    from .renewal import renewal_trigger_button, check_and_show_renewal_dialog
"""

from .queries import RenewalQueries
from .fragments import (
    renewal_dialog_fragment,
    renewal_trigger_button,
    check_and_show_renewal_dialog,
    RENEWAL_STRATEGIES,
    DEFAULT_THRESHOLD_DAYS,
)

__all__ = [
    # Queries
    'RenewalQueries',
    
    # Fragments
    'renewal_dialog_fragment',
    'renewal_trigger_button',
    'check_and_show_renewal_dialog',
    
    # Constants
    'RENEWAL_STRATEGIES',
    'DEFAULT_THRESHOLD_DAYS',
]

__version__ = '1.0.0'

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