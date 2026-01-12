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
         - Hybrid authorization (Option C):
           * admin (full): CRUD all records
           * sales_manager (team): CRUD for team members only
           * sales (self): VIEW ONLY - no edit permission
         - Record-level permission checks on Edit/Delete buttons
         - Salesperson dropdowns in forms filtered to editable scope
v1.3.0 - Phase 3 & 4 implementation:
         - Setup tab now defaults to MOST RECENT year with KPI data (Phase 4)
         - Stores quick stats in session_state for sidebar display (Phase 3)
         - Added _get_most_recent_kpi_year() helper function
         - Stores setup_access_info and setup_quick_stats for dynamic sidebar
v1.3.1 - FIX: Team scope not applied to KPI Assignments and Salespeople tabs
         - get_assignment_issues_summary() now accepts employee_ids parameter
         - salespeople_section() now accepts and filters by employee_ids  
         - Non-admin users now only see their team members in Setup tab
v1.4.0 - UX Improvements:
         - Select Rule dropdown shows full info without truncation
         - Edit Split Rule form includes Approve checkbox for admins
         - Shows approval status (read-only) for non-admin users

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

__version__ = '1.4.0'