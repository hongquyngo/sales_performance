# utils/kpi_center_performance/setup/renewal/__init__.py
"""
Renewal Module for KPI Center Split Rules (v3.0)

v3.0 Changes:
- Multi-step confirmation flow: Select → Preview → Processing → Result
- Impact summary with detailed breakdown before execution
- Progress indicator during bulk operations
- Detailed result summary with download option
- Confirmation checkbox for safety on bulk operations (>50 rules)

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
3. Preview impact before bulk renewal operations
4. Bulk renew selected rules with new validity period
5. Download detailed Excel report of renewed rules

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
    BULK_CONFIRMATION_THRESHOLD,
    # Step constants (for testing/customization)
    STEP_SELECT,
    STEP_PREVIEW,
    STEP_PROCESSING,
    STEP_RESULT,
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
    'BULK_CONFIRMATION_THRESHOLD',
    
    # Step constants
    'STEP_SELECT',
    'STEP_PREVIEW',
    'STEP_PROCESSING',
    'STEP_RESULT',
]

__version__ = '3.0.0'