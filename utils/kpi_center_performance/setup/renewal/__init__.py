# utils/kpi_center_performance/setup/renewal/__init__.py
"""
Renewal Module for KPI Center Split Rules (v2.1)

v2.1 Changes:
- User-selectable date pickers for expired_from and sales_from
- Removed Expiry Status filter (always shows all)
- No more hardcoded 365 days or 12 months

v2.0 Changes:
- Comprehensive filters: Expiry status, Brand, Customer/Product search
- Include EXPIRED rules (not just expiring)
- Better @st.fragment/@st.dialog handling

Provides functionality to:
1. Detect expired/expiring split rules with sales activity
2. Filter by brand, customer, product, date ranges
3. Bulk renew selected rules with new validity period
4. Preview and confirm renewal operations

Usage:
    from utils.kpi_center_performance.setup.renewal import renewal_section
    
    # In toolbar - single component handles button + dialog
    renewal_section(
        user_id=setup_queries.user_id,
        can_approve=can_approve,
        threshold_days=90
    )
"""

from .queries import RenewalQueries, EXPIRY_STATUS
from .fragments import (
    renewal_section,
    RENEWAL_STRATEGIES,
    DEFAULT_THRESHOLD_DAYS,
)

__all__ = [
    # Queries
    'RenewalQueries',
    'EXPIRY_STATUS',
    
    # Fragments
    'renewal_section',
    
    # Constants
    'RENEWAL_STRATEGIES',
    'DEFAULT_THRESHOLD_DAYS',
]

__version__ = '2.1.0'