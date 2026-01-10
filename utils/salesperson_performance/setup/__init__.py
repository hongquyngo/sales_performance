# utils/salesperson_performance/setup/__init__.py
"""
Setup Tab Module for Salesperson Performance

Full management console with 3 sub-tabs:
1. Split Rules - CRUD for sales_split_by_customer_product
2. KPI Assignments - CRUD for sales_employee_kpi_assignments  
3. Salespeople - List/manage salespeople

Features:
- Comprehensive Filters: Period, Entity, Attributes, Audit Trail filters
- Real-time Validation: Split percentage and weight validation
- Issue Detection: Missing assignments, weight issues
- CRUD Operations: Create, Read, Update, Delete for all entities
- KPI Summary: Overview by KPI type with total targets

v1.0.0 - Initial version based on KPI Center Performance setup pattern
v1.1.0 - Added audit trail filters, SQL View support, assignment summary by type
         Synced with KPI Center Performance v2.6.0 features:
         - 5 filter groups (Period, Entity, Attributes, Audit Trail, System)
         - Created By / Approved By / Date range filters
         - KPI summary by type in Assignments tab
         - Uses sales_split_looker_view for performance
v1.2.0 - FIX: Setup tab now independent from main page's "Only with KPI" filter
         - Setup tab uses AccessControl for employee filtering instead of active_filters
         - Added Salesperson dropdown filter in Entity Filters section
         - Fixed metrics/data table mismatch (metrics now use same employee_ids filter)
         - Access control: Users see only their own or team members' data based on hierarchy
         - Full access users (admin/GM/MD) can see all salespeople

Tables Managed:
- sales_split_by_customer_product: Sales territory assignments by customer-product
- sales_employee_kpi_assignments: KPI targets for each salesperson by year
- employees: Salesperson information (read-only)

Views Used:
- sales_split_full_looker_view: Pre-computed split data with validation status (enhanced)
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
    
    # Constants
    'KPI_ICONS',
    'STATUS_ICONS',
]

__version__ = '1.2.0'