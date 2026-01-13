# utils/kpi_center_performance/setup/__init__.py
"""
Setup Tab Module for KPI Center Performance

Full management console with 3 sub-tabs:
1. Split Rules - CRUD for kpi_center_split_by_customer_product (with integrated validation)
2. KPI Assignments - CRUD for sales_kpi_center_assignments (with integrated validation)
3. Hierarchy - Tree view of kpi_centers

Features:
- Renewal: Bulk renew expiring split rules with sales activity (v2.5.0)
- Validation: Integrated into Split Rules and KPI Assignments tabs for better UX
- Comprehensive Filters: Full filtering by period, entity, attributes, audit trail (v2.6.0)
- Bulk Operations: Multi-selection with bulk approve/disapprove/update (v2.7.0)

v2.7.0 Changes (Sync with Salesperson Performance):
- DataTable with multi-selection (checkbox column)
- Bulk Approve: Approve multiple pending rules at once
- Bulk Disapprove: Reset multiple approved rules to pending
- Bulk Update Period: Update valid_from/valid_to for multiple rules
- Bulk Delete: Delete multiple rules at once
- Single selection: Edit/Delete + Approve/Disapprove actions

v2.6.0 Changes:
- Split Rules now has 5 filter groups: Period, Entity, Attributes, Audit, System
- Period filter uses overlapping logic (not active_only)
- Added: Split % range filter, Created By/Approved By filters, Date range filters
- Removed: active_only logic (confusing with delete_flag)
"""

# Queries
from .queries import SetupQueries

# Fragments
from .fragments import (
    # Main entry point
    setup_tab_fragment,
    
    # Sub-tab sections (can be used independently)
    split_rules_section,
    kpi_assignments_section,
    hierarchy_section,
    
    # Constants
    KPI_TYPES,
    KPI_TYPE_ICONS,
    KPI_ICONS,
)

# Renewal sub-module
from .renewal import (
    RenewalQueries,
    renewal_section,
    RENEWAL_STRATEGIES,
    DEFAULT_THRESHOLD_DAYS,
)

__all__ = [
    # Queries
    'SetupQueries',
    
    # Main Fragment
    'setup_tab_fragment',
    
    # Sub-tab Fragments
    'split_rules_section',
    'kpi_assignments_section',
    'hierarchy_section',
    
    # Renewal
    'RenewalQueries',
    'renewal_section',
    'RENEWAL_STRATEGIES',
    'DEFAULT_THRESHOLD_DAYS',
    
    # Constants
    'KPI_TYPES',
    'KPI_TYPE_ICONS',
    'KPI_ICONS',
]

__version__ = '2.7.2'