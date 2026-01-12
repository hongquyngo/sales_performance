# utils/salesperson_performance/setup/__init__.py
"""
Setup Tab Module for Salesperson Performance

Full management console with 3 sub-tabs:
1. Split Rules - CRUD for sales_split_by_customer_product
2. KPI Assignments - CRUD for sales_employee_kpi_assignments  
3. Salespeople - List/manage salespeople


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
    
    # Constants
    'KPI_ICONS',
    'STATUS_ICONS',
]

__version__ = '1.5.4'