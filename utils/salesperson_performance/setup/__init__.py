# utils/salesperson_performance/setup/__init__.py
"""
Setup Tab Module for Salesperson Performance

Full management console with 3 sub-tabs:
1. Split Rules - CRUD for sales_split_by_customer_product
2. KPI Assignments - CRUD for sales_employee_kpi_assignments  
3. Salespeople - List/manage salespeople

v2.1.0: UX IMPROVEMENT - Add KPI Assignment dialog flow:
        - Removed "Add & Save All" button to prevent accidental saves
        - Reordered sections: "Add New Assignment" at TOP, "Pending Assignments" at BOTTOM
        - Natural UX flow: fill form → add to queue → review queue below → save
        - Added confirmation popover for "Save All Assignments" 
        - Shows summary by employee with weight totals before save
        - Clear visual separation with borders and section headers
        - Improved button placement to reduce mis-clicks
v2.0.3: FIX - Add KPI Assignment dialog batch queue:
        - "Add to Queue" now uses callback pattern (on_click)
        - No full page rerun, dialog stays open smoothly
        - Batch queue updates immediately after adding
v2.0.2: (Deprecated) Used reopen flag pattern with full page rerun
v2.0.1: FIX - KPI Type selector moved outside form for immediate UI update
v2.0.0: KPI Assignments refactored with Modal/Dialog pattern
        - Batch Add support (add multiple assignments before saving)
        - Improved notifications with row highlighting
        - Delete confirmation dialog
v1.9.0: Added version-based caching for data refresh after CRUD
"""

# Queries
from .queries import SalespersonSetupQueries

# Fragments
from .fragments import (
    # Main entry point
    setup_tab_fragment,
    
    # Sub-tab sections (can be used independently)
    split_rules_section,
    kpi_assignments_section,
    salespeople_section,
    
    # Helper functions
    format_currency,
    format_percentage,
    get_status_display,
    get_period_warning,
    
    # Authorization helpers (v1.2.0)
    can_modify_record,
    get_editable_employee_ids,
    
    # Data caching helpers (v1.9.0)
    _get_data_version,
    _bump_data_version,
    _get_cached_split_data,
    _get_cached_kpi_data,
    _clear_all_setup_cache,
    
    # Notification helpers (v1.8.0)
    _set_notification,
    _show_notification,
    
    # Constants
    KPI_ICONS,
    STATUS_ICONS,
)

__all__ = [
    # Queries
    'SalespersonSetupQueries',
    
    # Main Fragment
    'setup_tab_fragment',
    
    # Sub-tab Fragments
    'split_rules_section',
    'kpi_assignments_section',
    'salespeople_section',
    
    # Helpers
    'format_currency',
    'format_percentage',
    'get_status_display',
    'get_period_warning',
    
    # Authorization helpers (v1.2.0)
    'can_modify_record',
    'get_editable_employee_ids',
    
    # Data caching helpers (v1.9.0)
    '_get_data_version',
    '_bump_data_version',
    '_get_cached_split_data',
    '_get_cached_kpi_data',
    '_clear_all_setup_cache',
    
    # Notification helpers (v1.8.0)
    '_set_notification',
    '_show_notification',
    
    # Constants
    'KPI_ICONS',
    'STATUS_ICONS',
]

__version__ = '2.1.0'