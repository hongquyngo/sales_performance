# utils/salesperson_performance/setup/fragments.py
"""
UI Fragments for Setup Tab - Salesperson Performance

3 Sub-tabs:
1. Split Rules - CRUD for sales_split_by_customer_product
2. KPI Assignments - CRUD for sales_employee_kpi_assignments
3. Salespeople - List/manage salespeople

"""

import streamlit as st
import pandas as pd
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Any

from .queries import SalespersonSetupQueries


# =============================================================================
# CONSTANTS
# =============================================================================

KPI_ICONS = {
    'revenue': '💰',
    'gross_profit': '📈',
    'gross_profit_1': '📊',
    'gp1': '📊',
    'num_new_customers': '👥',
    'num_new_products': '📦',
    'new_business_revenue': '💼',
    'num_new_projects': '🎯',
}

STATUS_ICONS = {
    'ACTIVE': '🟢',
    'INACTIVE': '🟡',
    'TERMINATED': '🔴',
    'ON_LEAVE': '🟠',
}


# =============================================================================
# AUTHORIZATION HELPERS (v1.2.0)
# =============================================================================

def can_modify_record(
    record_owner_id: int,
    access_level: str,
    accessible_employee_ids: List[int] = None
) -> bool:
    """
    Check if current user can modify a specific record.
    
    Authorization rules (Option C: Hybrid):
    - admin (full): Can modify ALL records
    - sales_manager (team): Can modify records owned by team members
    - sales (self): Can only modify own records
    
    Args:
        record_owner_id: Employee ID who owns the record (sale_person_id)
        access_level: 'full', 'team', or 'self'
        accessible_employee_ids: List of employee IDs user can access
        
    Returns:
        True if user can modify this record
    """
    if access_level == 'full':
        return True  # Admin can modify all
    
    if accessible_employee_ids is None:
        return True  # Full access (shouldn't happen but safety check)
    
    return record_owner_id in accessible_employee_ids


def get_editable_employee_ids(
    access_level: str,
    accessible_employee_ids: List[int] = None,
    user_employee_id: int = None
) -> List[int]:
    """
    Get list of employee IDs that user can CREATE/EDIT records FOR.
    
    This determines which salespeople appear in dropdown when creating new rules.
    
    Args:
        access_level: 'full', 'team', or 'self'
        accessible_employee_ids: List of employee IDs user can access
        user_employee_id: Current user's employee ID
        
    Returns:
        List of employee IDs user can create/edit records for
    """
    if access_level == 'full':
        return None  # None means all (no filter)
    
    if access_level == 'team':
        return accessible_employee_ids  # Can create for team members
    
    # 'self' access - can only create for themselves
    return [user_employee_id] if user_employee_id else []


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _render_authorization_info(current_role: str):
    """
    Render authorization matrix info in popover.
    
    v1.4.2: Shows role-based permissions with current user highlighted.
    """
    st.markdown("#### 🔐 Authorization Matrix")
    st.caption("Your current role is highlighted")
    
    # Define authorization matrix
    auth_matrix = {
        'admin': {
            'label': '👑 Admin',
            'scope': 'All Records',
            'view': '✅', 'create': '✅', 'edit': '✅', 'delete': '✅', 'approve': '✅',
            'notes': 'Full access to all records and approval'
        },
        'sales_manager': {
            'label': '👔 Sales Manager',
            'scope': 'Team Members',
            'view': '✅', 'create': '✅', 'edit': '✅', 'delete': '✅', 'approve': '✅',
            'notes': 'CRUD + Approve for team members only'
        },
        'gm': {
            'label': '🏢 GM',
            'scope': 'All Records',
            'view': '✅', 'create': '✅', 'edit': '✅', 'delete': '✅', 'approve': '❌',
            'notes': 'Full CRUD but cannot approve'
        },
        'md': {
            'label': '🏢 MD',
            'scope': 'All Records',
            'view': '✅', 'create': '✅', 'edit': '✅', 'delete': '✅', 'approve': '❌',
            'notes': 'Full CRUD but cannot approve'
        },
        'director': {
            'label': '🏢 Director',
            'scope': 'All Records',
            'view': '✅', 'create': '✅', 'edit': '✅', 'delete': '✅', 'approve': '❌',
            'notes': 'Full CRUD but cannot approve'
        },
        'sales': {
            'label': '💼 Sales',
            'scope': 'Own Records',
            'view': '✅', 'create': '✅*', 'edit': '✅*', 'delete': '✅', 'approve': '❌',
            'notes': '* Created/edited records are Pending approval'
        },
        'viewer': {
            'label': '👁️ Viewer',
            'scope': 'View Only',
            'view': '✅', 'create': '❌', 'edit': '❌', 'delete': '❌', 'approve': '❌',
            'notes': 'Read-only access'
        },
    }
    
    # Show current user's permissions first
    current_role_lower = current_role.lower()
    if current_role_lower in auth_matrix:
        info = auth_matrix[current_role_lower]
        st.success(f"**Your Role: {info['label']}**")
        st.markdown(f"**Scope:** {info['scope']}")
        
        col1, col2, col3, col4, col5 = st.columns(5)
        col1.metric("View", info['view'])
        col2.metric("Create", info['create'])
        col3.metric("Edit", info['edit'])
        col4.metric("Delete", info['delete'])
        col5.metric("Approve", info['approve'])
        
        if info.get('notes'):
            st.caption(f"📝 {info['notes']}")
    else:
        st.warning(f"Unknown role: {current_role}")
    
    st.divider()
    
    # Show full matrix
    with st.expander("📋 View All Roles", expanded=False):
        # Build table data
        table_data = []
        for role_key, info in auth_matrix.items():
            is_current = (role_key == current_role_lower)
            row = {
                'Role': f"**{info['label']}**" if is_current else info['label'],
                'Scope': info['scope'],
                'View': info['view'],
                'Create': info['create'],
                'Edit': info['edit'],
                'Delete': info['delete'],
                'Approve': info['approve'],
            }
            table_data.append(row)
        
        st.dataframe(
            table_data,
            hide_index=True,
            use_container_width=True,
            column_config={
                'Role': st.column_config.TextColumn('Role', width='medium'),
                'Scope': st.column_config.TextColumn('Scope', width='medium'),
                'View': st.column_config.TextColumn('View', width='small'),
                'Create': st.column_config.TextColumn('Create', width='small'),
                'Edit': st.column_config.TextColumn('Edit', width='small'),
                'Delete': st.column_config.TextColumn('Delete', width='small'),
                'Approve': st.column_config.TextColumn('Approve', width='small'),
            }
        )
        
        st.caption("""
        **Legend:**
        - ✅ = Allowed
        - ✅* = Allowed but record stays Pending
        - ❌ = Not allowed
        """)


def format_currency(value: float, decimals: int = 0) -> str:
    """Format value as USD currency."""
    if pd.isna(value) or value == 0:
        return "$0"
    if decimals > 0:
        return f"${value:,.{decimals}f}"
    return f"${value:,.0f}"


def format_percentage(value: float, decimals: int = 0) -> str:
    """Format as percentage."""
    if pd.isna(value):
        return "0%"
    return f"{value:.{decimals}f}%"


def get_status_display(status: str) -> tuple:
    """Get status badge with icon and color."""
    status_map = {
        'ok': ('✅ OK', 'green'),
        'incomplete_split': ('⚠️ Under 100%', 'orange'),
        'over_100_split': ('🔴 Over 100%', 'red')
    }
    return status_map.get(status, (status, 'gray'))


def get_period_warning(valid_to) -> tuple:
    """Get period status: (icon, text, delta_color for st.metric)."""
    if pd.isna(valid_to):
        return ("🟢", "No End Date", "off")
    
    try:
        valid_to_dt = pd.to_datetime(valid_to)
        days_until = (valid_to_dt - pd.Timestamp.now()).days
        
        if days_until < 0:
            return ("⚫", "EXPIRED", "inverse")
        elif days_until <= 7:
            return ("🔴", f"{days_until}d left", "inverse")
        elif days_until <= 30:
            return ("🟠", f"{days_until}d left", "off")
        else:
            return ("🟢", "Active", "normal")
    except:
        return ("❓", "Unknown", "off")


# =============================================================================
# MAIN SETUP TAB FRAGMENT
# =============================================================================

@st.fragment
def setup_tab_fragment(
    sales_split_df: pd.DataFrame = None,
    sales_df: pd.DataFrame = None,
    active_filters: Dict = None,
    fragment_key: str = "setup"
):
    """
    Main fragment for Setup tab with 3 sub-tabs.
    
    v1.2.0: Setup tab now uses AccessControl for employee filtering instead of
            main page's active_filters. This prevents "Only with KPI assignment"
            filter from affecting Setup tab.
    
    Args:
        sales_split_df: Pre-loaded split data (optional, for backward compatibility)
        sales_df: Pre-loaded sales data (optional)
        active_filters: Dict of active filters from sidebar (year used, employee_ids ignored)
        fragment_key: Unique key for fragment
    """
    # Initialize queries with user context
    user_id = st.session_state.get('user_id') or st.session_state.get('user_uuid')
    setup_queries = SalespersonSetupQueries(user_id=user_id)
    
    # Get user role for permission check
    user_role = st.session_state.get('user_role', 'viewer')
    user_role_lower = str(user_role).lower() if user_role else ''
    
    # =========================================================================
    # HEADER WITH AUTHORIZATION INFO (v1.4.2)
    # =========================================================================
    header_col1, header_col2 = st.columns([6, 1])
    
    with header_col1:
        st.subheader("⚙️ Salesperson Configuration")
    
    with header_col2:
        # Authorization info popover
        with st.popover("🔐 Permissions", use_container_width=True):
            _render_authorization_info(user_role_lower)
    
    # =========================================================================
    # v1.3.0 (Phase 4): Get default year from MOST RECENT KPI data
    # Instead of using active_filters year, default to year with actual KPI data
    # =========================================================================
    def _get_most_recent_kpi_year() -> int:
        """Get year with most recent KPI assignments, or current year if none."""
        try:
            result = setup_queries.execute_query("""
                SELECT MAX(year) as max_year
                FROM sales_employee_kpi_assignments
                WHERE delete_flag = 0 OR delete_flag IS NULL
            """)
            if result and len(result) > 0 and result[0].get('max_year'):
                return int(result[0]['max_year'])
        except Exception:
            pass
        return date.today().year
    
    # Use session state to cache default year for Setup tab
    if 'setup_default_year' not in st.session_state:
        st.session_state['setup_default_year'] = _get_most_recent_kpi_year()
    
    # Setup tab uses its own year (independent from sidebar filters)
    current_year = st.session_state.get('setup_default_year', date.today().year)
    
    # =========================================================================
    # v1.2.0: Get accessible employees from AccessControl (NOT from active_filters)
    # This prevents "Only with KPI assignment" from affecting Setup tab
    # =========================================================================
    from utils.salesperson_performance import AccessControl
    
    # Get user info from session state
    user_role = st.session_state.get('user_role', 'viewer')
    employee_id = st.session_state.get('employee_id')
    
    access = AccessControl(user_role=user_role, employee_id=employee_id)
    access_level = access.get_access_level()
    
    if access_level == 'full':
        # Admin/GM/MD can see all salespeople
        accessible_employee_ids = None  # None means no filter (all)
    else:
        # Team or Self access - restricted to accessible employees
        accessible_employee_ids = access.get_accessible_employee_ids()
    
    # =========================================================================
    # v1.2.0: Determine EDITABLE scope (who can user CREATE/EDIT records for)
    # - admin (full): All salespeople
    # - sales_manager (team): Team members only
    # - sales (self): View only (no edit permission)
    # =========================================================================
    editable_employee_ids = get_editable_employee_ids(
        access_level=access_level,
        accessible_employee_ids=accessible_employee_ids,
        user_employee_id=employee_id
    )
    
    # =========================================================================
    # v1.3.0 (Phase 3): Store quick stats for sidebar display
    # =========================================================================
    accessible_count = len(accessible_employee_ids) if accessible_employee_ids else None
    editable_count = len(editable_employee_ids) if editable_employee_ids else None
    
    # Store for sidebar to access
    st.session_state['setup_access_info'] = {
        'access_level': access_level,
        'accessible_count': accessible_count,
        'editable_count': editable_count,
    }
    
    # Determine base edit permission by role
    # v1.4.1: sales role can now CRUD their own records (but cannot approve)
    can_edit_base = user_role_lower in ['admin', 'gm', 'md', 'director', 'sales_manager', 'sales']
    
    # v1.4.0: Approve permission
    # - admin: can approve ALL records
    # - sales_manager: can approve for team members only (checked per-record)
    # - sales: CANNOT approve (their records stay pending)
    can_approve = user_role_lower in ['admin', 'sales_manager']
    
    # Get issue counts for tab badges (using accessible scope)
    split_stats = setup_queries.get_split_summary_stats(
        employee_ids=accessible_employee_ids
    )
    split_critical = split_stats.get('over_100_count', 0)
    
    # FIX v1.3.1: Pass accessible_employee_ids to filter by team scope
    assignment_issues = setup_queries.get_assignment_issues_summary(
        current_year,
        employee_ids=accessible_employee_ids
    )
    assign_critical = assignment_issues.get('no_assignment_count', 0) + assignment_issues.get('weight_issues_count', 0)
    
    # =========================================================================
    # v1.3.0 (Phase 3): Store quick stats in session_state for sidebar
    # =========================================================================
    st.session_state['setup_quick_stats'] = {
        'split_rules_count': split_stats.get('total_rules', 0),
        'kpi_year': current_year,
        'kpi_current_year_count': assignment_issues.get('total_assignments', 0),
        'split_critical': split_critical,
        'assign_critical': assign_critical,
    }
    
    # Dynamic tab names with badges
    split_tab_name = f"📋 Split Rules{' 🔴' if split_critical > 0 else ''}"
    assign_tab_name = f"🎯 KPI Assignments{' ⚠️' if assign_critical > 0 else ''}"
    
    # Create 3 sub-tabs
    tab1, tab2, tab3 = st.tabs([
        split_tab_name,
        assign_tab_name, 
        "👥 Salespeople"
    ])
    
    with tab1:
        split_rules_section(
            setup_queries=setup_queries,
            accessible_employee_ids=accessible_employee_ids,
            editable_employee_ids=editable_employee_ids,  # v1.2.0: For record-level auth
            can_edit_base=can_edit_base,  # v1.2.0: Renamed
            can_approve=can_approve,
            access_level=access_level,
            user_employee_id=employee_id  # v1.2.0: For ownership check
        )
    
    with tab2:
        kpi_assignments_section(
            setup_queries=setup_queries,
            employee_ids=accessible_employee_ids,
            editable_employee_ids=editable_employee_ids,  # v1.2.0
            can_edit_base=can_edit_base,  # v1.2.0
            current_year=current_year,
            access_level=access_level,  # v1.2.0
            user_employee_id=employee_id  # v1.2.0
        )
    
    with tab3:
        # FIX v1.3.1: Pass accessible_employee_ids to filter salespeople list
        salespeople_section(
            setup_queries=setup_queries,
            employee_ids=accessible_employee_ids,  # NEW: Filter by team scope
            can_edit=can_edit_base and access_level == 'full'  # Only admin can edit salespeople
        )


# =============================================================================
# SPLIT RULES SECTION (v1.1.0 - Added Audit Trail Filters)
# =============================================================================

@st.fragment
def split_rules_section(
    setup_queries: SalespersonSetupQueries,
    accessible_employee_ids: List[int] = None,
    editable_employee_ids: List[int] = None,  # v1.2.0: Who can user CREATE/EDIT for
    can_edit_base: bool = False,  # v1.2.0: Base permission (role allows editing)
    can_approve: bool = False,
    access_level: str = 'self',
    user_employee_id: int = None  # v1.2.0: For ownership check
):
    """
    Split Rules sub-tab with CRUD operations and comprehensive filters.
    
    v1.1.0: Added Audit Trail filter group (Created By, Approved By, Date Ranges)
    v1.2.0: Hybrid authorization (Option C):
            - admin (full): CRUD all records
            - sales_manager (team): CRUD for team members only
            - sales (self): CRUD only own records
    
    Args:
        setup_queries: Query handler
        accessible_employee_ids: List of employee IDs user can VIEW (None = all)
        editable_employee_ids: List of employee IDs user can CREATE/EDIT FOR (None = all)
        can_edit_base: Whether user's role allows editing at all
        can_approve: Whether user can approve rules
        access_level: 'full', 'team', or 'self'
        user_employee_id: Current user's employee ID
    """
    
    # Helper to check if user can modify a specific record
    def can_modify_this_record(record_owner_id: int) -> bool:
        """Check if current user can edit/delete this specific record."""
        if not can_edit_base:
            return False
        return can_modify_record(record_owner_id, access_level, editable_employee_ids)
    
    # =========================================================================
    # HELPER: Build query params from filter state
    # =========================================================================
    def get_current_filter_params():
        """
        Build query params from current filter state.
        
        v1.2.0: Changed to use Setup tab's own salesperson filter instead of
                main page's employee_ids. Applies accessible_employee_ids constraint.
        """
        params = {}
        
        # Period filters
        period_type = st.session_state.get('sp_split_period_type', 'full_year')
        period_year = st.session_state.get('sp_split_period_year', date.today().year)
        
        if period_type == 'ytd':
            params['period_start'] = date(period_year, 1, 1)
            params['period_end'] = date.today()
        elif period_type == 'full_year':
            params['period_year'] = period_year
        elif period_type == 'custom':
            custom_start = st.session_state.get('sp_split_period_start')
            custom_end = st.session_state.get('sp_split_period_end')
            if custom_start:
                params['period_start'] = custom_start
            if custom_end:
                params['period_end'] = custom_end
        
        # =====================================================================
        # v1.2.0: Salesperson filter - Setup tab's own filter
        # Note: selectbox returns single value (-1 = All, or specific employee_id)
        # =====================================================================
        sp_filter = st.session_state.get('sp_split_salesperson_filter', -1)
        
        if sp_filter and sp_filter != -1:
            # User selected a specific salesperson
            # Apply accessible constraint if not full access
            if accessible_employee_ids is not None:
                # Verify selected person is in accessible scope
                if sp_filter in accessible_employee_ids:
                    params['employee_ids'] = [sp_filter]
                else:
                    # Fallback to all accessible (shouldn't happen with proper UI)
                    params['employee_ids'] = accessible_employee_ids
            else:
                params['employee_ids'] = [sp_filter]
        elif accessible_employee_ids is not None:
            # "All" selected but user has restricted access
            params['employee_ids'] = accessible_employee_ids
        # else: Full access, "All" selected = show all (no filter)
        
        # Entity filters - Brand
        brand_filter = st.session_state.get('sp_split_brand_filter', [])
        if brand_filter:
            params['brand_ids'] = brand_filter
        
        # v1.5.2: Entity filters - Customer (multiselect)
        customer_filter = st.session_state.get('sp_split_customer_filter', [])
        if customer_filter:
            params['customer_ids'] = customer_filter
        
        # v1.5.2: Entity filters - Product (multiselect)
        product_filter = st.session_state.get('sp_split_product_filter', [])
        if product_filter:
            params['product_ids'] = product_filter
        
        # Rule attribute filters
        status_filter = st.session_state.get('sp_split_status_filter')
        if status_filter and status_filter != 'all':
            params['status_filter'] = status_filter
        
        approval_filter = st.session_state.get('sp_split_approval_filter')
        if approval_filter and approval_filter != 'all':
            params['approval_filter'] = approval_filter
        
        split_min = st.session_state.get('sp_split_pct_min')
        split_max = st.session_state.get('sp_split_pct_max')
        if split_min is not None and split_min > 0:
            params['split_min'] = split_min
        if split_max is not None and split_max < 100:
            params['split_max'] = split_max
        
        # Audit trail filters (v1.1.0 - NEW, v1.4.2 - FIXED)
        created_by = st.session_state.get('sp_split_created_by_filter')
        if created_by and created_by > 0:
            params['created_by_employee_id'] = created_by
        
        approved_by = st.session_state.get('sp_split_approved_by_filter')
        if approved_by and approved_by > 0:
            params['approved_by_employee_id'] = approved_by
        
        created_from = st.session_state.get('sp_split_created_date_from')
        if created_from:
            params['created_date_from'] = created_from
        
        created_to = st.session_state.get('sp_split_created_date_to')
        if created_to:
            params['created_date_to'] = created_to
        
        modified_from = st.session_state.get('sp_split_modified_date_from')
        if modified_from:
            params['modified_date_from'] = modified_from
        
        modified_to = st.session_state.get('sp_split_modified_date_to')
        if modified_to:
            params['modified_date_to'] = modified_to
        
        # System filters
        include_deleted = st.session_state.get('sp_split_show_deleted', False)
        params['include_deleted'] = include_deleted
        
        return params
    
    # =========================================================================
    # FILTERS (v1.1.0 - 5 Filter Groups like KPI Center)
    # =========================================================================
    with st.expander("🔍 Filters", expanded=True):
        
        # ROW 1: Period Filters
        st.markdown("##### 📅 Validity Period")
        
        p_col1, p_col2, p_col3, p_col4 = st.columns([1, 1, 1, 1])
        
        with p_col1:
            available_years = setup_queries.get_split_rule_years()
            current_year = date.today().year
            
            period_year = st.selectbox(
                "Year",
                options=available_years,
                index=available_years.index(current_year) if current_year in available_years else 0,
                key="sp_split_period_year"
            )
        
        with p_col2:
            period_type_options = {
                'ytd': f'📊 YTD {period_year}',
                'full_year': f'📅 Full Year {period_year}',
                'custom': '🔧 Custom Range',
                'all': '📋 All Periods'
            }
            period_type = st.selectbox(
                "Period Type",
                options=list(period_type_options.keys()),
                format_func=lambda x: period_type_options[x],
                index=1,
                key="sp_split_period_type"
            )
        
        with p_col3:
            default_start = date(period_year, 1, 1)
            period_start = st.date_input(
                "From",
                value=default_start,
                disabled=(period_type != 'custom'),
                key="sp_split_period_start"
            )
        
        with p_col4:
            default_end = date(period_year, 12, 31)
            period_end = st.date_input(
                "To",
                value=default_end,
                disabled=(period_type != 'custom'),
                key="sp_split_period_end"
            )
        
        st.divider()
        
        # ROW 2: Entity Filters
        st.markdown("##### 🏢 Entity Filters")
        
        e_col1, e_col2, e_col3, e_col4 = st.columns(4)
        
        # v1.2.0: Salesperson filter - Setup tab's own filter
        with e_col1:
            # Get salespeople within accessible scope
            salespeople_df = setup_queries.get_salespeople_for_dropdown(include_inactive=True)
            
            # Filter to accessible scope if restricted
            if accessible_employee_ids is not None:
                salespeople_df = salespeople_df[
                    salespeople_df['employee_id'].isin(accessible_employee_ids)
                ]
            
            if not salespeople_df.empty:
                sp_options = [(-1, "👥 All Salespeople")] + [
                    (row['employee_id'], f"👤 {row['employee_name']}") 
                    for _, row in salespeople_df.iterrows()
                ]
                
                # Determine label based on access level
                if access_level == 'full':
                    filter_label = "Salesperson"
                elif access_level == 'team':
                    filter_label = f"Team Member ({len(salespeople_df)})"
                else:
                    filter_label = "Your Data"
                
                st.selectbox(
                    filter_label,
                    options=[s[0] for s in sp_options],
                    format_func=lambda x: next((s[1] for s in sp_options if s[0] == x), "All"),
                    key="sp_split_salesperson_filter",
                    help="Filter rules by salesperson (within your access scope)"
                )
            else:
                st.info("No salespeople available")
        
        with e_col2:
            brands_df = setup_queries.get_brands_for_dropdown()
            brand_options = brands_df['brand_id'].tolist() if not brands_df.empty else []
            
            brand_filter = st.multiselect(
                "Brand",
                options=brand_options,
                format_func=lambda x: brands_df[brands_df['brand_id'] == x]['brand_name'].iloc[0] if not brands_df.empty else str(x),
                placeholder="All Brands",
                key="sp_split_brand_filter"
            )
        
        # v1.5.2: Customer multiselect (only customers with split rules)
        with e_col3:
            customers_df = setup_queries.get_customers_with_splits(
                employee_ids=accessible_employee_ids
            )
            
            if not customers_df.empty:
                customer_options = customers_df['customer_id'].tolist()
                st.multiselect(
                    "Customer",
                    options=customer_options,
                    format_func=lambda x: customers_df[customers_df['customer_id'] == x]['display_name'].iloc[0] if x in customer_options else str(x),
                    placeholder="All Customers",
                    key="sp_split_customer_filter",
                    help=f"{len(customer_options)} customers with split rules"
                )
            else:
                st.multiselect("Customer", options=[], placeholder="No customers", disabled=True)
        
        # v1.5.2: Product multiselect (only products with split rules)
        with e_col4:
            products_df = setup_queries.get_products_with_splits(
                employee_ids=accessible_employee_ids
            )
            
            if not products_df.empty:
                product_options = products_df['product_id'].tolist()
                st.multiselect(
                    "Product",
                    options=product_options,
                    format_func=lambda x: products_df[products_df['product_id'] == x]['display_name'].iloc[0] if x in product_options else str(x),
                    placeholder="All Products",
                    key="sp_split_product_filter",
                    help=f"{len(product_options)} products with split rules"
                )
            else:
                st.multiselect("Product", options=[], placeholder="No products", disabled=True)
        
        st.divider()
        
        # ROW 3: Rule Attributes
        st.markdown("##### 📊 Rule Attributes")
        
        r_col1, r_col2, r_col3, r_col4 = st.columns(4)
        
        with r_col1:
            split_min = st.number_input(
                "Split % Min",
                min_value=0,
                max_value=100,
                value=0,
                step=10,
                key="sp_split_pct_min"
            )
        
        with r_col2:
            split_max = st.number_input(
                "Split % Max",
                min_value=0,
                max_value=100,
                value=100,
                step=10,
                key="sp_split_pct_max"
            )
        
        with r_col3:
            status_options = {
                'all': '📋 All Status',
                'ok': '✅ OK (=100%)',
                'incomplete_split': '⚠️ Under 100%',
                'over_100_split': '🔴 Over 100%'
            }
            status_filter = st.selectbox(
                "Split Status",
                options=list(status_options.keys()),
                format_func=lambda x: status_options[x],
                key="sp_split_status_filter"
            )
        
        with r_col4:
            approval_options = {
                'all': '📋 All',
                'approved': '✅ Approved',
                'pending': '⏳ Pending'
            }
            approval_filter = st.selectbox(
                "Approval Status",
                options=list(approval_options.keys()),
                format_func=lambda x: approval_options[x],
                key="sp_split_approval_filter"
            )
        
        st.divider()
        
        # ROW 4: Audit Trail Filters (v1.1.0 - NEW)
        st.markdown("##### 👤 Audit Trail")
        
        a_col1, a_col2, a_col3, a_col4 = st.columns(4)
        
        with a_col1:
            # Created By dropdown (v1.4.2: Fixed - uses employees via keycloak_id)
            creators_df = setup_queries.get_creators_for_dropdown()
            creator_options = [(-1, "All Creators")] + [
                (row['employee_id'], row['employee_name']) 
                for _, row in creators_df.iterrows()
            ] if not creators_df.empty else [(-1, "All Creators")]
            
            created_by_filter = st.selectbox(
                "Created By",
                options=[c[0] for c in creator_options],
                format_func=lambda x: next((c[1] for c in creator_options if c[0] == x), "All Creators"),
                key="sp_split_created_by_filter"
            )
        
        with a_col2:
            # Approved By dropdown
            approvers_df = setup_queries.get_approvers_for_dropdown()
            approver_options = [(-1, "All Approvers")] + [
                (row['employee_id'], row['employee_name']) 
                for _, row in approvers_df.iterrows()
            ] if not approvers_df.empty else [(-1, "All Approvers")]
            
            approved_by_filter = st.selectbox(
                "Approved By",
                options=[a[0] for a in approver_options],
                format_func=lambda x: next((a[1] for a in approver_options if a[0] == x), "All Approvers"),
                key="sp_split_approved_by_filter"
            )
        
        with a_col3:
            # Created Date Range
            created_date_from = st.date_input(
                "Created From",
                value=None,
                key="sp_split_created_date_from"
            )
        
        with a_col4:
            created_date_to = st.date_input(
                "Created To",
                value=None,
                key="sp_split_created_date_to"
            )
        
        # Modified date row
        m_col1, m_col2, m_col3, m_col4 = st.columns(4)
        
        with m_col1:
            modified_date_from = st.date_input(
                "Modified From",
                value=None,
                key="sp_split_modified_date_from"
            )
        
        with m_col2:
            modified_date_to = st.date_input(
                "Modified To",
                value=None,
                key="sp_split_modified_date_to"
            )
        
        st.divider()
        
        # ROW 5: System Filters
        st.markdown("##### ⚙️ System")
        
        sys_col1, sys_col2, sys_col3 = st.columns([2, 1, 1])
        
        with sys_col1:
            # NOTE: View has built-in WHERE delete_flag=0, so this checkbox
            # cannot actually show deleted records. Kept disabled for UI consistency.
            show_deleted = st.checkbox(
                "🗑️ Show deleted rules",
                value=False,
                key="sp_split_show_deleted",
                help="⚠️ Not available: View filters out deleted records",
                disabled=True  # Cannot show deleted with current view
            )
        
        with sys_col2:
            if st.button("🔄 Reset Filters", use_container_width=True):
                keys_to_reset = [
                    'sp_split_period_year', 'sp_split_period_type', 'sp_split_period_start', 'sp_split_period_end',
                    'sp_split_salesperson_filter',
                    'sp_split_brand_filter', 'sp_split_customer_filter', 'sp_split_product_filter',  # v1.5.2: Updated
                    'sp_split_pct_min', 'sp_split_pct_max', 'sp_split_status_filter', 'sp_split_approval_filter',
                    'sp_split_created_by_filter', 'sp_split_approved_by_filter',
                    'sp_split_created_date_from', 'sp_split_created_date_to',
                    'sp_split_modified_date_from', 'sp_split_modified_date_to',
                    'sp_split_show_deleted'
                ]
                for key in keys_to_reset:
                    if key in st.session_state:
                        del st.session_state[key]
                st.rerun(scope="fragment")
        
        with sys_col3:
            # Count active filters
            sp_filter_val = st.session_state.get('sp_split_salesperson_filter', -1)
            customer_filter_val = st.session_state.get('sp_split_customer_filter', [])
            product_filter_val = st.session_state.get('sp_split_product_filter', [])
            active_filter_count = sum([
                period_type != 'all',
                sp_filter_val != -1 if sp_filter_val else False,
                len(brand_filter) > 0,
                len(customer_filter_val) > 0,  # v1.5.2: Updated
                len(product_filter_val) > 0,   # v1.5.2: Updated
                split_min > 0,
                split_max < 100,
                status_filter != 'all',
                approval_filter != 'all',
                created_by_filter > 0 if created_by_filter else False,
                approved_by_filter > 0 if approved_by_filter else False,
                created_date_from is not None,
                created_date_to is not None,
                modified_date_from is not None if 'modified_date_from' in dir() else False,
                modified_date_to is not None if 'modified_date_to' in dir() else False,
                show_deleted
            ])
            st.metric("Active Filters", active_filter_count)
    
    # =========================================================================
    # GET FILTER PARAMS
    # =========================================================================
    query_params = get_current_filter_params()
    
    # =========================================================================
    # SUMMARY METRICS (v1.2.0: Now synced with data table via employee_ids)
    # =========================================================================
    stats = setup_queries.get_split_summary_stats(
        period_year=query_params.get('period_year'),
        period_start=query_params.get('period_start'),
        period_end=query_params.get('period_end'),
        include_deleted=query_params.get('include_deleted', False),
        employee_ids=query_params.get('employee_ids')  # v1.2.0: Sync with data table
    )
    
    col1, col2, col3, col4, col5, col6 = st.columns(6)
    
    with col1:
        st.metric(
            label="Total Rules",
            value=f"{stats['total_rules']:,}",
            help="Total split rules matching current filters"
        )
    with col2:
        st.metric(
            label="✅ OK",
            value=f"{stats['ok_count']:,}",
            delta=f"{stats['ok_count']/max(stats['total_rules'],1)*100:.0f}%" if stats['total_rules'] > 0 else None,
            delta_color="off",
            help="Rules where total split = 100%"
        )
    with col3:
        st.metric(
            label="⚠️ Under 100%",
            value=f"{stats['incomplete_count']:,}",
            delta_color="off",
            help="Rules where total split < 100%"
        )
    with col4:
        st.metric(
            label="🔴 Over 100%",
            value=f"{stats['over_100_count']:,}",
            delta_color="off",
            help="Rules where total split > 100% - needs fix!"
        )
    with col5:
        st.metric(
            label="⏳ Pending",
            value=f"{stats['pending_count']:,}",
            help="Rules awaiting approval"
        )
    with col6:
        st.metric(
            label="⏰ Expiring",
            value=f"{stats['expiring_soon_count']:,}",
            help="Rules expiring within 30 days"
        )
    
    st.divider()
    
    # =========================================================================
    # TOOLBAR
    # =========================================================================
    if can_edit_base:
        if st.button("➕ Add Split Rule", type="primary"):
            st.session_state['sp_show_add_split_form'] = True
    
    # =========================================================================
    # ADD/EDIT FORMS
    # =========================================================================
    if st.session_state.get('sp_show_add_split_form', False):
        _render_split_form(
            setup_queries, 
            can_approve, 
            mode='add',
            editable_employee_ids=editable_employee_ids,  # v1.2.0
            access_level=access_level
        )
    
    if st.session_state.get('sp_edit_split_id'):
        _render_split_form(
            setup_queries, 
            can_approve, 
            mode='edit', 
            rule_id=st.session_state['sp_edit_split_id'],
            editable_employee_ids=editable_employee_ids,  # v1.2.0
            access_level=access_level
        )
    
    # =========================================================================
    # GET DATA WITH FILTERS
    # =========================================================================
    split_df = setup_queries.get_sales_split_data(**query_params)
    
    # v1.5.2: Removed client-side text search - now using server-side multiselect filters
    
    if split_df.empty:
        st.info("No split rules found matching the filters")
        return
    
    # =========================================================================
    # RESULTS SUMMARY
    # =========================================================================
    period_desc = ""
    if period_type == 'ytd':
        period_desc = f"YTD {period_year} (Jan 1 - Today)"
    elif period_type == 'full_year':
        period_desc = f"Full Year {period_year}"
    elif period_type == 'custom':
        period_desc = f"{period_start} to {period_end}"
    else:
        period_desc = "All Periods"
    
    st.caption(f"📊 Showing **{len(split_df):,}** rules | Period: {period_desc}")
    
    # =========================================================================
    # v1.5.2: Call nested fragment for data table
    # This prevents full page rerun when selecting/deselecting rows
    # =========================================================================
    _render_split_data_table(
        split_df=split_df,
        setup_queries=setup_queries,
        can_edit_base=can_edit_base,
        can_approve=can_approve,
        editable_employee_ids=editable_employee_ids,
        access_level=access_level
    )


@st.fragment
def _render_split_data_table(
    split_df: pd.DataFrame,
    setup_queries: SalespersonSetupQueries,
    can_edit_base: bool,
    can_approve: bool,
    editable_employee_ids: List[int],
    access_level: str
):
    """
    v1.5.2: Nested fragment for data table and action bar.
    This allows row selection to only rerun this section, not the entire filters.
    """
    if split_df.empty:
        st.info("No split rules found matching the filters")
        return
    
    # Helper to check if user can modify a specific record
    def can_modify_this_record(record_owner_id: int) -> bool:
        if not can_edit_base:
            return False
        return can_modify_record(record_owner_id, access_level, editable_employee_ids)
    
    # Prepare display dataframe
    display_df = split_df.copy()
    
    display_df['ID'] = display_df['split_id'].apply(lambda x: f"#{x}")
    display_df['Salesperson'] = display_df['salesperson_name']
    display_df['Customer'] = display_df['customer_display']
    display_df['Product'] = display_df['product_display']
    display_df['Split'] = display_df['split_percentage'].apply(lambda x: f"{x:.0f}%")
    display_df['Status'] = display_df['split_status'].apply(lambda x: get_status_display(x)[0])
    display_df['Approved'] = display_df.apply(
        lambda r: f"✅ {r.get('approved_by_name', '').strip() if pd.notna(r.get('approved_by_name')) else ''}" if r.get('is_approved') else '⏳ Pending',
        axis=1
    )
    display_df['Created By'] = display_df['created_by_name'].fillna('')
    
    show_deleted_flag = st.session_state.get('sp_split_show_deleted', False)
    
    if show_deleted_flag and 'delete_flag' in display_df.columns:
        display_df['Deleted'] = display_df['delete_flag'].apply(lambda x: '🗑️' if x else '')
    
    # Get user's employee_id for approver tracking
    approver_employee_id = st.session_state.get('employee_id')
    
    # Count pending and approved
    pending_mask = display_df['is_approved'] != 1
    approved_mask = display_df['is_approved'] == 1
    pending_count = pending_mask.sum()
    approved_count = approved_mask.sum()
    
    # Initialize selection state
    if 'sp_split_selected_ids' not in st.session_state:
        st.session_state['sp_split_selected_ids'] = set()
    
    selected_ids = st.session_state.get('sp_split_selected_ids', set())
    valid_selected = set(display_df['split_id'].tolist()) & selected_ids if selected_ids else set()
    selected_count = len(valid_selected)
    
    # =========================================================================
    # UNIFIED ACTION BAR
    # =========================================================================
    with st.container(border=True):
        row1_col1, row1_col2, row1_col3, row1_col4 = st.columns([2, 1, 1, 1])
        
        with row1_col1:
            st.markdown(f"**📋 {pending_count}** pending · **✅ {approved_count}** approved")
        
        with row1_col2:
            if st.button("☑️ Select All Pending", use_container_width=True, 
                        help="Select all pending rules", key="sp_dt_select_pending"):
                pending_ids = display_df[pending_mask]['split_id'].tolist()
                st.session_state['sp_split_selected_ids'] = set(pending_ids)
                st.rerun(scope="fragment")
        
        with row1_col3:
            if st.button("☑️ Select All Approved", use_container_width=True,
                        help="Select all approved rules", key="sp_dt_select_approved"):
                approved_ids = display_df[approved_mask]['split_id'].tolist()
                st.session_state['sp_split_selected_ids'] = set(approved_ids)
                st.rerun(scope="fragment")
        
        with row1_col4:
            if st.button("✖️ Clear", use_container_width=True, 
                        disabled=selected_count == 0, key="sp_dt_clear"):
                st.session_state['sp_split_selected_ids'] = set()
                st.rerun(scope="fragment")
        
        # ROW 2: Action buttons (only show when items selected)
        if valid_selected:
            selected_df = display_df[display_df['split_id'].isin(valid_selected)]
            selected_pending = (selected_df['is_approved'] != 1).sum()
            selected_approved = (selected_df['is_approved'] == 1).sum()
            
            st.divider()
            
            # Single selection: Show Edit/Delete + Approve/Disapprove
            if selected_count == 1:
                selected_rule_id = list(valid_selected)[0]
                selected_row = selected_df.iloc[0]
                record_owner_id = selected_row['sale_person_id']
                is_rule_approved = selected_row.get('is_approved', 0) == 1
                
                can_modify = can_modify_this_record(record_owner_id)
                
                st.caption(f"📌 Selected: **#{selected_rule_id}** | {selected_row['salesperson_name']} | {selected_row['customer_display']}")
                
                if can_approve:
                    act_col1, act_col2, act_col3, act_col4 = st.columns(4)
                else:
                    act_col1, act_col2 = st.columns(2)
                    act_col3 = act_col4 = None
                
                with act_col1:
                    if can_modify:
                        if st.button("✏️ Edit", use_container_width=True, type="secondary", key="sp_dt_edit"):
                            st.session_state['sp_edit_split_id'] = selected_rule_id
                            st.rerun(scope="fragment")
                    else:
                        st.button("✏️ Edit", use_container_width=True, disabled=True,
                                 help="You can only edit records for your team members", key="sp_dt_edit_dis")
                
                with act_col2:
                    if can_modify:
                        with st.popover("🗑️ Delete", use_container_width=True):
                            st.warning(f"Delete rule **#{selected_rule_id}**?")
                            if st.button("🗑️ Yes, Delete", type="primary", 
                                        key="sp_dt_confirm_delete", use_container_width=True):
                                result = setup_queries.delete_split_rule(selected_rule_id)
                                if result['success']:
                                    st.session_state['sp_split_selected_ids'] = set()
                                    st.toast("Rule deleted", icon="🗑️")
                                    st.rerun(scope="fragment")
                                else:
                                    st.error(result['message'])
                    else:
                        st.button("🗑️ Delete", use_container_width=True, disabled=True,
                                 help="You can only delete records for your team members", key="sp_dt_del_dis")
                
                if can_approve:
                    with act_col3:
                        if not is_rule_approved:
                            if st.button("✅ Approve", use_container_width=True, type="primary", key="sp_dt_approve"):
                                result = setup_queries.bulk_approve_split_rules(
                                    rule_ids=[selected_rule_id],
                                    approver_employee_id=approver_employee_id
                                )
                                if result['success']:
                                    st.toast(f"Rule #{selected_rule_id} approved", icon="✅")
                                    st.rerun(scope="fragment")
                                else:
                                    st.error(result['message'])
                        else:
                            st.button("✅ Approve", use_container_width=True, disabled=True,
                                     help="Already approved", key="sp_dt_approve_dis")
                    
                    with act_col4:
                        if is_rule_approved:
                            if st.button("⏳ Disapprove", use_container_width=True, key="sp_dt_disapprove"):
                                result = setup_queries.bulk_disapprove_split_rules(
                                    rule_ids=[selected_rule_id]
                                )
                                if result['success']:
                                    st.toast(f"Rule #{selected_rule_id} reset to Pending", icon="⏳")
                                    st.rerun(scope="fragment")
                                else:
                                    st.error(result['message'])
                        else:
                            st.button("⏳ Disapprove", use_container_width=True, disabled=True,
                                     help="Not approved yet", key="sp_dt_disapprove_dis")
            
            # Multi selection: Show bulk actions only
            else:
                st.caption(f"📌 **{selected_count}** rules selected: {selected_pending} pending, {selected_approved} approved")
                
                # ROW 1: Approval actions (if user can approve)
                if can_approve:
                    bulk_col1, bulk_col2, bulk_col3 = st.columns([1, 1, 2])
                    
                    with bulk_col1:
                        if selected_pending > 0:
                            with st.popover(f"✅ Approve {selected_pending}", use_container_width=True):
                                st.warning(f"Approve **{selected_pending}** pending rules?")
                                if st.button("✅ Yes, Approve All", type="primary", 
                                            key="sp_dt_bulk_approve", use_container_width=True):
                                    pending_to_approve = selected_df[selected_df['is_approved'] != 1]['split_id'].tolist()
                                    result = setup_queries.bulk_approve_split_rules(
                                        rule_ids=pending_to_approve,
                                        approver_employee_id=approver_employee_id
                                    )
                                    if result['success']:
                                        st.session_state['sp_split_selected_ids'] = set()
                                        st.toast(f"✅ Approved {result['count']} rules", icon="✅")
                                        st.rerun(scope="fragment")
                                    else:
                                        st.error(result['message'])
                        else:
                            st.button("✅ Approve", disabled=True, use_container_width=True,
                                     help="No pending rules selected", key="sp_dt_bulk_approve_dis")
                    
                    with bulk_col2:
                        if selected_approved > 0:
                            with st.popover(f"⏳ Disapprove {selected_approved}", use_container_width=True):
                                st.warning(f"Reset **{selected_approved}** rules to Pending?")
                                if st.button("⏳ Yes, Reset to Pending", type="primary",
                                            key="sp_dt_bulk_disapprove", use_container_width=True):
                                    approved_to_reset = selected_df[selected_df['is_approved'] == 1]['split_id'].tolist()
                                    result = setup_queries.bulk_disapprove_split_rules(
                                        rule_ids=approved_to_reset
                                    )
                                    if result['success']:
                                        st.session_state['sp_split_selected_ids'] = set()
                                        st.toast(f"⏳ Reset {result['count']} rules to Pending", icon="⏳")
                                        st.rerun(scope="fragment")
                                    else:
                                        st.error(result['message'])
                        else:
                            st.button("⏳ Disapprove", disabled=True, use_container_width=True,
                                     help="No approved rules selected", key="sp_dt_bulk_disapprove_dis")
                
                # ROW 2: Bulk Update actions (v1.6.0 - Enhanced with validation)
                # Only show if user has edit permission
                if can_edit_base:
                    st.divider()
                    st.caption("📝 Bulk Update Actions")
                    
                    upd_col1, upd_col2, upd_col3 = st.columns([1, 1, 2])
                    
                    # Bulk Update Period (v1.6.0: With validation preview)
                    with upd_col1:
                        with st.popover(f"📅 Update Period ({selected_count})", use_container_width=True):
                            st.markdown(f"**Set validity period for {selected_count} rules**")
                            
                            bulk_valid_from = st.date_input(
                                "Valid From",
                                value=date.today(),
                                key="sp_bulk_valid_from"
                            )
                            bulk_valid_to = st.date_input(
                                "Valid To",
                                value=date(date.today().year, 12, 31),
                                key="sp_bulk_valid_to"
                            )
                            
                            st.caption(f"📌 Will update: {bulk_valid_from} → {bulk_valid_to}")
                            
                            # v1.6.0: Validation preview
                            selected_rule_ids = list(valid_selected)
                            period_impact = setup_queries.validate_bulk_period_impact(
                                rule_ids=selected_rule_ids,
                                valid_from=bulk_valid_from,
                                valid_to=bulk_valid_to
                            )
                            
                            # Show validation results
                            if period_impact['period_errors']:
                                for err in period_impact['period_errors']:
                                    st.error(f"❌ {err}")
                            
                            if period_impact.get('period_warnings'):
                                for warn in period_impact['period_warnings']:
                                    st.warning(f"⚠️ {warn}")
                            
                            if period_impact['overlap_count'] > 0:
                                st.error(f"❌ {period_impact['overlap_count']} rules will have overlapping periods - Not allowed")
                                with st.expander("View overlap details"):
                                    for ow in period_impact['overlap_warnings'][:5]:  # Show max 5
                                        st.caption(f"• #{ow['rule_id']}: {ow['salesperson_name']} - {ow['overlap_count']} overlaps")
                                    if period_impact['overlap_count'] > 5:
                                        st.caption(f"... and {period_impact['overlap_count'] - 5} more")
                            
                            # v1.6.2: Block if any overlaps OR period errors (pre-validation)
                            can_proceed_period = period_impact['can_proceed'] and period_impact['overlap_count'] == 0
                            
                            if can_proceed_period:
                                if st.button("📅 Apply Period", type="primary", 
                                            key="sp_dt_bulk_period", use_container_width=True):
                                    result = setup_queries.bulk_update_split_period(
                                        rule_ids=selected_rule_ids,
                                        valid_from=bulk_valid_from,
                                        valid_to=bulk_valid_to
                                    )
                                    if result['success']:
                                        st.session_state['sp_split_selected_ids'] = set()
                                        st.toast(f"📅 Updated period for {result['count']} rules", icon="📅")
                                        st.rerun(scope="fragment")
                                    else:
                                        st.error(result['message'])
                            else:
                                st.button("📅 Apply Period", type="primary", disabled=True,
                                         key="sp_dt_bulk_period_dis", use_container_width=True)
                                st.error("❌ Fix errors above before proceeding")
                    
                    # Bulk Update Split % (v1.6.0: With validation preview)
                    with upd_col2:
                        with st.popover(f"📊 Update Split % ({selected_count})", use_container_width=True):
                            st.markdown(f"**Set split % for {selected_count} rules**")
                            
                            bulk_split_pct = st.number_input(
                                "Split Percentage",
                                min_value=0,
                                max_value=100,
                                value=100,
                                step=5,
                                key="sp_bulk_split_pct"
                            )
                            
                            st.caption(f"📌 Will set: **{bulk_split_pct}%** for all selected rules")
                            
                            # v1.6.0: Validation preview with impact analysis
                            selected_rule_ids = list(valid_selected)
                            split_impact = setup_queries.validate_bulk_split_impact(
                                rule_ids=selected_rule_ids,
                                new_split_percentage=float(bulk_split_pct)
                            )
                            
                            # Show impact summary
                            imp_col1, imp_col2, imp_col3 = st.columns(3)
                            with imp_col1:
                                st.metric("✅ OK", split_impact['will_be_ok'], help="Will have total = 100%")
                            with imp_col2:
                                st.metric("⚠️ Under", split_impact['will_be_under'], help="Will have total < 100%")
                            with imp_col3:
                                delta_color = "inverse" if split_impact['will_be_over'] > 0 else "off"
                                st.metric("🔴 Over", split_impact['will_be_over'], 
                                         help="Will have total > 100%",
                                         delta="BLOCKED" if split_impact['will_be_over'] > 0 and access_level != 'full' else None,
                                         delta_color=delta_color)
                            
                            # Show detailed issues
                            if split_impact['will_be_over'] > 0:
                                over_rules = [d for d in split_impact['details'] if d['status'] == 'over']
                                with st.expander(f"🔴 View {len(over_rules)} over-allocated rules"):
                                    for r in over_rules[:5]:
                                        st.caption(f"• #{r['rule_id']}: {r['customer_name'][:20]}... → {r['new_total']:.0f}%")
                                    if len(over_rules) > 5:
                                        st.caption(f"... and {len(over_rules) - 5} more")
                            
                            # v1.6.0: Block if any over 100% - ALL users (business rule)
                            can_bulk_update = split_impact['can_proceed']
                            
                            if split_impact['will_be_over'] > 0:
                                st.error(f"❌ Cannot proceed: {split_impact['will_be_over']} rules would exceed 100%")
                            
                            if can_bulk_update:
                                if st.button("📊 Apply Split %", type="primary",
                                            key="sp_dt_bulk_split", use_container_width=True):
                                    result = setup_queries.bulk_update_split_percentage(
                                        rule_ids=selected_rule_ids,
                                        split_percentage=bulk_split_pct
                                    )
                                    if result['success']:
                                        st.session_state['sp_split_selected_ids'] = set()
                                        st.toast(f"📊 Updated split % for {result['count']} rules", icon="📊")
                                        st.rerun(scope="fragment")
                                    else:
                                        st.error(result['message'])
                            else:
                                st.button("📊 Apply Split %", type="primary", disabled=True,
                                         key="sp_dt_bulk_split_dis", use_container_width=True)
                
                if not can_approve and not can_edit_base:
                    st.info("💡 Select a single rule to view details")
    
    # =========================================================================
    # DATA TABLE WITH CHECKBOXES
    # =========================================================================
    display_df['Select'] = display_df['split_id'].apply(
        lambda x: x in st.session_state.get('sp_split_selected_ids', set())
    )
    
    columns_to_show = [
        'Select', 'ID', 'Salesperson', 'Customer', 'Product', 'brand',
        'Split', 'effective_period', 'Status', 'Approved', 'Created By'
    ]
    if show_deleted_flag and 'delete_flag' in display_df.columns:
        columns_to_show.append('Deleted')
    
    edited_df = st.data_editor(
        display_df[columns_to_show],
        hide_index=True,
        column_config={
            'Select': st.column_config.CheckboxColumn(
                '☑️',
                width='small',
                help="Select for actions"
            ),
            'ID': st.column_config.TextColumn('ID', width='small', disabled=True),
            'Salesperson': st.column_config.TextColumn('Salesperson', width='medium', disabled=True),
            'Customer': st.column_config.TextColumn('Customer', width='large', disabled=True),
            'Product': st.column_config.TextColumn('Product', width='large', disabled=True),
            'brand': st.column_config.TextColumn('Brand', width='small', disabled=True),
            'Split': st.column_config.TextColumn('Split %', width='small', disabled=True),
            'effective_period': st.column_config.TextColumn('Period', width='medium', disabled=True),
            'Status': st.column_config.TextColumn('Status', width='small', disabled=True),
            'Approved': st.column_config.TextColumn('Approved', width='medium', disabled=True),
            'Created By': st.column_config.TextColumn('Created By', width='medium', disabled=True),
        },
        use_container_width=True,
        key="sp_split_data_editor_v2"
    )
    
    if edited_df is not None and 'Select' in edited_df.columns:
        new_selected = set(display_df[edited_df['Select'] == True]['split_id'].tolist())
        if new_selected != st.session_state.get('sp_split_selected_ids', set()):
            st.session_state['sp_split_selected_ids'] = new_selected
            st.rerun(scope="fragment")


def _render_split_form(
    setup_queries: SalespersonSetupQueries, 
    can_approve: bool, 
    mode: str = 'add', 
    rule_id: int = None,
    editable_employee_ids: List[int] = None,  # v1.2.0
    access_level: str = 'self'  # v1.2.0
):
    """
    Render Add/Edit split rule form.
    
    v1.2.0: Added editable_employee_ids to restrict salesperson dropdown
            based on user's authorization scope.
    """
    
    existing = None
    if mode == 'edit' and rule_id:
        df = setup_queries.get_sales_split_data(limit=5000)
        df = df[df['split_id'] == rule_id]
        if not df.empty:
            existing = df.iloc[0]
        else:
            st.error("Rule not found")
            st.session_state['sp_edit_split_id'] = None
            return
    
    title = "✏️ Edit Split Rule" if mode == 'edit' else "➕ Add Split Rule"
    
    with st.container(border=True):
        st.markdown(f"### {title}")
        
        if mode == 'edit' and existing is not None:
            st.caption(f"Rule ID: {rule_id}")
            col_info1, col_info2 = st.columns(2)
            with col_info1:
                st.markdown(f"**Customer:** {existing['customer_display']}")
            with col_info2:
                st.markdown(f"**Product:** {existing['product_display']}")
        
        with st.form(f"sp_{mode}_split_form", clear_on_submit=False):
            col1, col2 = st.columns(2)
            
            with col1:
                if mode == 'add':
                    # Customer search
                    customer_search = st.text_input("🔍 Search Customer", key=f"sp_{mode}_cust_search")
                    customers_df = setup_queries.get_customers_for_dropdown(
                        search=customer_search if customer_search else None, 
                        limit=50
                    )
                    
                    if not customers_df.empty:
                        customer_id = st.selectbox(
                            "Customer *",
                            options=customers_df['customer_id'].tolist(),
                            format_func=lambda x: customers_df[customers_df['customer_id'] == x]['display_name'].iloc[0],
                            key=f"sp_{mode}_customer_id"
                        )
                    else:
                        customer_id = None
                        st.caption("No customers found")
                else:
                    customer_id = existing['customer_id']
                
                # Salesperson selection (v1.2.0: Filter by editable scope)
                salespeople_df = setup_queries.get_salespeople_for_dropdown()
                
                # v1.2.0: Filter to only show editable employees
                if editable_employee_ids is not None and not salespeople_df.empty:
                    salespeople_df = salespeople_df[
                        salespeople_df['employee_id'].isin(editable_employee_ids)
                    ].reset_index(drop=True)
                
                if not salespeople_df.empty:
                    default_idx = 0
                    if existing is not None and 'sale_person_id' in existing:
                        matches = salespeople_df[salespeople_df['employee_id'] == existing['sale_person_id']]
                        if not matches.empty:
                            default_idx = salespeople_df.index.tolist().index(matches.index[0])
                    
                    # v1.2.0: Add label hint based on access level
                    sp_label = "Salesperson *"
                    if access_level == 'self':
                        sp_label = "Salesperson * (your account)"
                    elif access_level == 'team':
                        sp_label = "Salesperson * (team members)"
                    
                    sale_person_id = st.selectbox(
                        sp_label,
                        options=salespeople_df['employee_id'].tolist(),
                        index=default_idx,
                        format_func=lambda x: f"👤 {salespeople_df[salespeople_df['employee_id'] == x]['employee_name'].iloc[0]}",
                        key=f"sp_{mode}_sale_person_id"
                    )
                else:
                    sale_person_id = None
            
            with col2:
                if mode == 'add':
                    # Product search
                    product_search = st.text_input("🔍 Search Product", key=f"sp_{mode}_prod_search")
                    products_df = setup_queries.get_products_for_dropdown(
                        search=product_search if product_search else None,
                        limit=50
                    )
                    
                    if not products_df.empty:
                        product_id = st.selectbox(
                            "Product *",
                            options=products_df['product_id'].tolist(),
                            format_func=lambda x: products_df[products_df['product_id'] == x]['display_name'].iloc[0],
                            key=f"sp_{mode}_product_id"
                        )
                    else:
                        product_id = None
                        st.caption("No products found")
                else:
                    product_id = existing['product_id']
                
                # Split percentage
                default_split = float(existing['split_percentage']) if existing is not None else 100.0
                split_pct = st.number_input(
                    "Split % *",
                    min_value=0.0,
                    max_value=100.0,
                    value=default_split,
                    step=5.0,
                    key=f"sp_{mode}_split_pct"
                )
            
            # Period inputs (moved up for better UX)
            col3, col4 = st.columns(2)
            with col3:
                default_from = pd.to_datetime(existing['effective_from']).date() if existing is not None and pd.notna(existing.get('effective_from')) else date.today()
                valid_from = st.date_input("Valid From *", value=default_from, key=f"sp_{mode}_valid_from")
            
            with col4:
                default_to = pd.to_datetime(existing['effective_to']).date() if existing is not None and pd.notna(existing.get('effective_to')) else date(date.today().year, 12, 31)
                valid_to = st.date_input("Valid To *", value=default_to, key=f"sp_{mode}_valid_to")
            
            # =====================================================================
            # v1.6.0: ENHANCED VALIDATION SECTION
            # =====================================================================
            st.divider()
            st.markdown("##### 🔍 Validation")
            
            validation_errors = []
            validation_warnings = []
            can_save = True
            
            # 1. Period Validation
            if valid_from and valid_to:
                period_validation = setup_queries.validate_period(valid_from, valid_to)
                
                if not period_validation['is_valid']:
                    for err in period_validation['errors']:
                        validation_errors.append(f"📅 {err}")
                        can_save = False
                
                for warn in period_validation.get('warnings', []):
                    validation_warnings.append(f"📅 {warn}")
            
            # 2. Period Overlap Check (for same salesperson)
            # v1.6.2: BLOCK overlap (pre-validation business rule)
            if customer_id and product_id and sale_person_id and valid_from:
                overlap_check = setup_queries.check_period_overlap(
                    customer_id=customer_id,
                    product_id=product_id,
                    sale_person_id=sale_person_id,
                    valid_from=valid_from,
                    valid_to=valid_to,
                    exclude_rule_id=rule_id if mode == 'edit' else None
                )
                
                if overlap_check['has_overlap']:
                    # v1.6.2: BLOCK - not allowed to create overlapping rules
                    validation_errors.append(f"📅 Period overlaps with {overlap_check['overlap_count']} existing rule(s) for this salesperson")
                    can_save = False
                    
                    with st.expander(f"🔍 View {overlap_check['overlap_count']} overlapping rules"):
                        for r in overlap_check['overlapping_rules']:
                            st.caption(f"• Rule #{r['rule_id']}: {r['split_percentage']:.0f}% ({r['period_display']})")
            
            # 3. Split Percentage Validation (with period awareness)
            if customer_id and product_id:
                split_validation = setup_queries.validate_split_percentage(
                    customer_id=customer_id,
                    product_id=product_id,
                    new_percentage=split_pct,
                    exclude_rule_id=rule_id if mode == 'edit' else None,
                    valid_from=valid_from,
                    valid_to=valid_to
                )
                
                val_col1, val_col2, val_col3 = st.columns(3)
                with val_col1:
                    st.metric("Current Total", f"{split_validation['current_total']:.0f}%",
                             help=f"{split_validation['existing_count']} existing rule(s)")
                with val_col2:
                    delta_color = "off"
                    if split_validation['new_total'] > 100:
                        delta_color = "inverse"
                    st.metric("After Save", f"{split_validation['new_total']:.0f}%",
                             delta=f"+{split_pct:.0f}%", delta_color=delta_color)
                with val_col3:
                    if split_validation['new_total'] == 100:
                        st.success("✅ Perfect!")
                    elif split_validation['new_total'] > 100:
                        over_pct = split_validation['over_amount']
                        st.error(f"🔴 Over by {over_pct:.0f}%")
                        
                        # v1.6.0: Block save for over 100% - ALL users (business rule)
                        validation_errors.append(f"📊 Total split ({split_validation['new_total']:.0f}%) exceeds 100% - Not allowed")
                        can_save = False
                    else:
                        st.warning(f"⚠️ {split_validation['remaining']:.0f}% remaining")
                        validation_warnings.append(f"📊 Under-allocated: {split_validation['remaining']:.0f}% remaining")
            
            # Display validation summary
            if validation_errors:
                for err in validation_errors:
                    st.error(err)
            
            if validation_warnings and not validation_errors:
                for warn in validation_warnings:
                    st.warning(warn)
            
            # Approval checkbox (only for edit mode and users with approve permission)
            is_approved_value = False
            if mode == 'edit' and can_approve:
                st.divider()
                current_approval = bool(existing.get('is_approved', 0)) if existing is not None else False
                is_approved_value = st.checkbox(
                    "✅ Approve this rule",
                    value=current_approval,
                    key=f"sp_{mode}_is_approved",
                    help="Check to approve this split rule. Only admins/managers can approve."
                )
                if is_approved_value and not current_approval:
                    st.success("Rule will be marked as Approved after save")
                elif not is_approved_value and current_approval:
                    st.warning("Rule will be marked as Pending after save")
            elif mode == 'edit' and not can_approve:
                # v1.4.1: Sales role - show warning that edit resets approval
                current_approval = bool(existing.get('is_approved', 0)) if existing is not None else False
                st.divider()
                if current_approval:
                    st.warning("⚠️ This rule is currently **Approved**. After saving your changes, it will need to be re-approved by your manager.")
                else:
                    st.info("⏳ Status: **Pending approval** - Your manager will review after you save.")
            
            # Form buttons
            col_submit, col_cancel = st.columns(2)
            
            with col_submit:
                submitted = st.form_submit_button(
                    "💾 Save" if mode == 'add' else "💾 Update",
                    type="primary",
                    use_container_width=True
                )
            
            with col_cancel:
                cancelled = st.form_submit_button("❌ Cancel", use_container_width=True)
            
            if submitted:
                # v1.6.0: Check validation before proceeding
                if not can_save:
                    st.error("❌ Cannot save - Please fix validation errors above")
                elif mode == 'add' and not all([customer_id, product_id, sale_person_id]):
                    st.error("Please fill all required fields")
                else:
                    if mode == 'add':
                        result = setup_queries.create_split_rule(
                            customer_id=customer_id,
                            product_id=product_id,
                            sale_person_id=sale_person_id,
                            split_percentage=split_pct,
                            valid_from=valid_from,
                            valid_to=valid_to,
                            is_approved=can_approve
                        )
                    else:
                        # Build update params
                        update_kwargs = {
                            'rule_id': rule_id,
                            'split_percentage': split_pct,
                            'valid_from': valid_from,
                            'valid_to': valid_to,
                            'sale_person_id': sale_person_id
                        }
                        
                        # v1.4.1: Handle approval status on update
                        # - If user can approve: use checkbox value
                        # - If user cannot approve (sales): reset to pending (needs re-approval)
                        if can_approve:
                            update_kwargs['is_approved'] = is_approved_value
                        else:
                            # Sales role edits reset approval status to pending
                            update_kwargs['is_approved'] = False
                        
                        result = setup_queries.update_split_rule(**update_kwargs)
                    
                    if result['success']:
                        st.success(f"{'Created' if mode == 'add' else 'Updated'} successfully!")
                        st.session_state['sp_show_add_split_form'] = False
                        st.session_state['sp_edit_split_id'] = None
                        st.rerun(scope="fragment")
                    else:
                        st.error(result['message'])
            
            if cancelled:
                st.session_state['sp_show_add_split_form'] = False
                st.session_state['sp_edit_split_id'] = None
                st.rerun(scope="fragment")


# =============================================================================
# KPI ASSIGNMENTS SECTION (v1.1.0 - Added Summary by Type)
# =============================================================================

@st.fragment
def kpi_assignments_section(
    setup_queries: SalespersonSetupQueries,
    employee_ids: List[int] = None,
    editable_employee_ids: List[int] = None,  # v1.2.0
    can_edit_base: bool = False,  # v1.2.0: Renamed from can_edit
    current_year: int = None,
    access_level: str = 'self',  # v1.2.0
    user_employee_id: int = None  # v1.2.0
):
    """
    KPI Assignments sub-tab.
    
    v1.1.0: Added KPI Summary by Type section (synced with KPI Center Performance)
    v1.2.0: Hybrid authorization - record-level permissions
    """
    
    # Helper to check if user can modify a specific record
    def can_modify_this_record(record_owner_id: int) -> bool:
        """Check if current user can edit/delete this specific record."""
        if not can_edit_base:
            return False
        return can_modify_record(record_owner_id, access_level, editable_employee_ids)
    
    current_year = current_year or date.today().year
    
    # -------------------------------------------------------------------------
    # FILTER BAR
    # -------------------------------------------------------------------------
    col1, col2, col3 = st.columns([1, 2, 1])
    
    with col1:
        available_years = setup_queries.get_available_years()
        if current_year not in available_years:
            available_years.append(current_year)
        available_years.sort(reverse=True)
        
        selected_year = st.selectbox(
            "Year",
            options=available_years,
            index=available_years.index(current_year) if current_year in available_years else 0,
            key="sp_assign_year_filter"
        )
    
    with col2:
        salespeople_df = setup_queries.get_salespeople_for_dropdown(include_inactive=True)
        
        # FIX v1.5.3: Filter by accessible employee scope (was missing)
        if employee_ids is not None:
            salespeople_df = salespeople_df[
                salespeople_df['employee_id'].isin(employee_ids)
            ]
        
        salesperson_options = [(-1, "All Salespeople")] + [
            (row['employee_id'], f"👤 {row['employee_name']}") 
            for _, row in salespeople_df.iterrows()
        ]
        selected_employee_id = st.selectbox(
            "Salesperson",
            options=[s[0] for s in salesperson_options],
            format_func=lambda x: next((s[1] for s in salesperson_options if s[0] == x), ""),
            key="sp_assign_employee_filter"
        )
    
    with col3:
        if can_edit_base:
            st.write("")
            if st.button("➕ Add Assignment", type="primary", use_container_width=True):
                st.session_state['sp_show_add_assignment_form'] = True
    
    # -------------------------------------------------------------------------
    # KPI SUMMARY BY TYPE (v1.1.0 - NEW - Synced with KPI Center Performance)
    # FIX v1.5.3: Filter by employee_ids for team scope
    # -------------------------------------------------------------------------
    summary_df = setup_queries.get_assignment_summary_by_type(selected_year, employee_ids=employee_ids)
    
    if not summary_df.empty:
        st.markdown(f"##### 📊 {selected_year} Targets Overview")
        
        # Create summary cards
        num_kpis = len(summary_df)
        cols = st.columns(min(num_kpis, 4))
        
        for idx, (_, row) in enumerate(summary_df.iterrows()):
            col_idx = idx % 4
            kpi_lower = row['kpi_name'].lower().replace(' ', '_')
            icon = KPI_ICONS.get(kpi_lower, '📋')
            
            with cols[col_idx]:
                # Format target based on UOM
                if row['unit_of_measure'] == 'USD':
                    target_display = format_currency(row['total_target'])
                else:
                    target_display = f"{row['total_target']:,.0f}"
                
                st.metric(
                    label=f"{icon} {row['kpi_name']}",
                    value=target_display,
                    delta=f"{row['employee_count']} salespeople",
                    delta_color="off",
                    help=f"Total {row['kpi_name']} target for {selected_year}"
                )
        
        st.divider()
    
    # -------------------------------------------------------------------------
    # ISSUES SECTION
    # FIX v1.5.3: Pass employee_ids to filter by team scope (was missing)
    # -------------------------------------------------------------------------
    issues = setup_queries.get_assignment_issues_summary(selected_year, employee_ids=employee_ids)
    
    critical_count = issues['no_assignment_count']
    warning_count = issues['weight_issues_count']
    
    has_issues = critical_count > 0 or warning_count > 0
    
    if has_issues:
        if critical_count > 0:
            expander_title = f"🔴 {critical_count} Missing Assignments"
        else:
            expander_title = f"⚠️ {warning_count} Weight Issues"
        
        with st.expander(expander_title, expanded=(critical_count > 0)):
            
            # Missing assignments
            if issues['no_assignment_count'] > 0:
                st.markdown("##### 🔴 Salespeople Without Assignments")
                st.caption(f"{issues['no_assignment_count']} active salespeople need {selected_year} KPI assignments")
                
                with st.container(border=True):
                    for emp in issues['no_assignment_details']:
                        col_info, col_action = st.columns([4, 1])
                        with col_info:
                            st.markdown(f"👤 **{emp['name']}**")
                            st.caption(emp.get('email', ''))
                        with col_action:
                            # v1.2.0: Check record-level permission for this employee
                            if can_edit_base and can_modify_this_record(emp['id']) and st.button(
                                "➕ Add", 
                                key=f"sp_add_assign_{emp['id']}", 
                                use_container_width=True
                            ):
                                st.session_state['sp_add_assignment_employee_id'] = emp['id']
                                st.session_state['sp_show_add_assignment_form'] = True
                                st.rerun(scope="fragment")
                
                st.divider()
            
            # Weight issues
            if issues['weight_issues_count'] > 0:
                st.markdown("##### ⚠️ Weight Sum ≠ 100%")
                st.caption(f"{issues['weight_issues_count']} salespeople have weights not summing to 100%")
                
                with st.container(border=True):
                    for emp in issues['weight_issues_details']:
                        col_info, col_weight, col_action = st.columns([3, 1, 1])
                        with col_info:
                            st.markdown(f"**{emp['employee_name']}**")
                        with col_weight:
                            weight = emp['total_weight']
                            if weight < 100:
                                st.warning(f"{weight:.0f}%")
                            else:
                                st.error(f"{weight:.0f}%")
                        with col_action:
                            gap = 100 - weight
                            if gap > 0:
                                st.caption(f"+{gap:.0f}% needed")
                            else:
                                st.caption(f"{abs(gap):.0f}% over")
    
    else:
        st.success(f"✅ All {selected_year} assignments are healthy!")
    
    st.divider()
    
    # -------------------------------------------------------------------------
    # ADD/EDIT FORMS
    # -------------------------------------------------------------------------
    if st.session_state.get('sp_show_add_assignment_form', False):
        _render_assignment_form(
            setup_queries, 
            selected_year, 
            mode='add',
            editable_employee_ids=editable_employee_ids,  # v1.2.0
            access_level=access_level
        )
    
    if st.session_state.get('sp_edit_assignment_id'):
        _render_assignment_form(
            setup_queries, 
            selected_year, 
            mode='edit',
            assignment_id=st.session_state['sp_edit_assignment_id'],
            editable_employee_ids=editable_employee_ids,  # v1.2.0
            access_level=access_level
        )
    
    # -------------------------------------------------------------------------
    # GET DATA
    # -------------------------------------------------------------------------
    query_params = {'year': selected_year}
    if selected_employee_id > 0:
        query_params['employee_ids'] = [selected_employee_id]
    elif employee_ids:
        query_params['employee_ids'] = employee_ids
    
    assignments_df = setup_queries.get_kpi_assignments(**query_params)
    weight_summary_df = setup_queries.get_assignment_weight_summary(selected_year)
    
    if assignments_df.empty:
        st.info(f"No KPI assignments found for {selected_year}")
        return
    
    # -------------------------------------------------------------------------
    # ASSIGNMENTS BY SALESPERSON - Card layout
    # -------------------------------------------------------------------------
    for emp_id in assignments_df['employee_id'].unique():
        emp_data = assignments_df[assignments_df['employee_id'] == emp_id]
        emp_name = emp_data.iloc[0]['employee_name']
        emp_email = emp_data.iloc[0]['employee_email']
        emp_status = emp_data.iloc[0]['employee_status']
        
        # Get weight sum
        weight_row = weight_summary_df[weight_summary_df['employee_id'] == emp_id]
        total_weight = int(weight_row['total_weight'].iloc[0]) if not weight_row.empty else 0
        kpi_count = len(emp_data)
        
        # Determine weight status
        if total_weight == 100:
            weight_badge = "✅"
            weight_color = "normal"
        elif total_weight < 100:
            weight_badge = "⚠️"
            weight_color = "off"
        else:
            weight_badge = "🔴"
            weight_color = "inverse"
        
        status_icon = STATUS_ICONS.get(emp_status, '❓')
        
        # v1.2.0: Check if user can modify records for this employee
        can_modify_for_emp = can_modify_this_record(emp_id)
        
        # Card container
        with st.container(border=True):
            # Header
            header_col1, header_col2 = st.columns([4, 1])
            
            with header_col1:
                st.markdown(f"### {status_icon} {emp_name}")
                st.caption(f"{emp_email} • {kpi_count} KPI{'s' if kpi_count > 1 else ''}")
            
            with header_col2:
                st.metric(
                    label="Weight Sum",
                    value=f"{total_weight}%",
                    delta=weight_badge,
                    delta_color=weight_color,
                    help="Total weight should equal 100%"
                )
            
            # KPI rows (v1.2.0: Pass per-employee edit permission)
            for _, kpi in emp_data.iterrows():
                _render_kpi_assignment_row(kpi, can_modify_for_emp, setup_queries)
            
            # Add KPI button (v1.2.0: Only show if user can add for this employee)
            if can_edit_base and can_modify_for_emp:
                if st.button(
                    f"➕ Add KPI to {emp_name}", 
                    key=f"sp_add_kpi_btn_{emp_id}",
                    use_container_width=True
                ):
                    st.session_state['sp_add_assignment_employee_id'] = emp_id
                    st.session_state['sp_show_add_assignment_form'] = True
                    st.rerun(scope="fragment")


def _render_kpi_assignment_row(kpi: pd.Series, can_edit: bool, setup_queries: SalespersonSetupQueries):
    """Render a single KPI assignment row."""
    
    kpi_lower = kpi['kpi_name'].lower().replace(' ', '_')
    icon = KPI_ICONS.get(kpi_lower, '📋')
    
    col1, col2, col3, col4 = st.columns([2, 3, 1, 1])
    
    with col1:
        st.markdown(f"**{icon} {kpi['kpi_name']}**")
        st.caption(f"ID: {kpi['assignment_id']}")
    
    with col2:
        if kpi['unit_of_measure'] == 'USD':
            annual = format_currency(kpi['annual_target_value_numeric'])
            monthly = format_currency(kpi['monthly_target_value'])
        else:
            annual = f"{kpi['annual_target_value_numeric']:,.0f}"
            monthly = f"{kpi['monthly_target_value']:,.1f}"
        
        st.caption(f"Annual: {annual} • Monthly: {monthly}")
    
    with col3:
        st.markdown(f"**{kpi['weight_numeric']:.0f}%** weight")
    
    with col4:
        if can_edit:
            btn_col1, btn_col2 = st.columns(2)
            with btn_col1:
                if st.button("✏️", key=f"sp_edit_assign_{kpi['assignment_id']}", help="Edit"):
                    st.session_state['sp_edit_assignment_id'] = kpi['assignment_id']
                    st.rerun(scope="fragment")
            with btn_col2:
                if st.button("🗑️", key=f"sp_del_assign_{kpi['assignment_id']}", help="Delete"):
                    result = setup_queries.delete_assignment(kpi['assignment_id'])
                    if result['success']:
                        st.rerun(scope="fragment")


def _render_assignment_form(
    setup_queries: SalespersonSetupQueries, 
    year: int,
    mode: str = 'add', 
    assignment_id: int = None,
    editable_employee_ids: List[int] = None,  # v1.2.0
    access_level: str = 'self'  # v1.2.0
):
    """
    Render Add/Edit assignment form.
    
    v1.2.0: Added editable_employee_ids to restrict salesperson dropdown.
    """
    
    existing = None
    if mode == 'edit' and assignment_id:
        df = setup_queries.get_kpi_assignments()
        df = df[df['assignment_id'] == assignment_id]
        if not df.empty:
            existing = df.iloc[0]
        else:
            st.error("Assignment not found")
            st.session_state['sp_edit_assignment_id'] = None
            return
    
    title = "✏️ Edit KPI Assignment" if mode == 'edit' else "➕ Add KPI Assignment"
    
    with st.container(border=True):
        st.markdown(f"### {title}")
        
        with st.form(f"sp_{mode}_assignment_form"):
            col1, col2 = st.columns(2)
            
            with col1:
                # Salesperson (v1.2.0: Filter by editable scope)
                salespeople_df = setup_queries.get_salespeople_for_dropdown()
                
                # v1.2.0: Filter to only show editable employees
                if editable_employee_ids is not None and not salespeople_df.empty:
                    salespeople_df = salespeople_df[
                        salespeople_df['employee_id'].isin(editable_employee_ids)
                    ].reset_index(drop=True)
                
                default_employee = st.session_state.get('sp_add_assignment_employee_id')
                if existing is not None:
                    default_employee = existing['employee_id']
                
                default_idx = 0
                if default_employee and not salespeople_df.empty:
                    matches = salespeople_df[salespeople_df['employee_id'] == default_employee]
                    if not matches.empty:
                        default_idx = salespeople_df.index.tolist().index(matches.index[0])
                
                # v1.2.0: Add label hint based on access level
                sp_label = "Salesperson *"
                if access_level == 'self':
                    sp_label = "Salesperson * (your account)"
                elif access_level == 'team':
                    sp_label = "Salesperson * (team members)"
                
                employee_id = st.selectbox(
                    sp_label,
                    options=salespeople_df['employee_id'].tolist(),
                    index=default_idx,
                    format_func=lambda x: f"👤 {salespeople_df[salespeople_df['employee_id'] == x]['employee_name'].iloc[0]}",
                    key=f"sp_{mode}_assign_employee",
                    disabled=(mode == 'edit')
                )
                
                # KPI Type
                kpi_types_df = setup_queries.get_kpi_types()
                
                default_type_idx = 0
                if existing is not None:
                    matches = kpi_types_df[kpi_types_df['kpi_type_id'] == existing['kpi_type_id']]
                    if not matches.empty:
                        default_type_idx = kpi_types_df.index.tolist().index(matches.index[0])
                
                kpi_type_id = st.selectbox(
                    "KPI Type *",
                    options=kpi_types_df['kpi_type_id'].tolist(),
                    index=default_type_idx,
                    format_func=lambda x: f"{KPI_ICONS.get(kpi_types_df[kpi_types_df['kpi_type_id'] == x]['kpi_name'].iloc[0].lower().replace(' ', '_'), '📋')} {kpi_types_df[kpi_types_df['kpi_type_id'] == x]['kpi_name'].iloc[0]}",
                    key=f"sp_{mode}_assign_type",
                    disabled=(mode == 'edit')
                )
            
            with col2:
                # Get UOM
                selected_kpi = kpi_types_df[kpi_types_df['kpi_type_id'] == kpi_type_id].iloc[0]
                selected_uom = selected_kpi['unit_of_measure']
                
                # Annual target
                default_target = int(existing['annual_target_value_numeric']) if existing is not None else 0
                annual_target = st.number_input(
                    f"Annual Target ({selected_uom}) *",
                    min_value=0,
                    value=default_target,
                    step=10000 if selected_uom == 'USD' else 1,
                    key=f"sp_{mode}_assign_target"
                )
                
                if selected_uom == 'USD' and annual_target > 0:
                    st.caption(f"= {format_currency(annual_target / 12)}/month • {format_currency(annual_target / 4)}/quarter")
                
                # Weight
                default_weight = int(existing['weight_numeric']) if existing is not None else 0
                weight = st.number_input(
                    "Weight % *",
                    min_value=0,
                    max_value=100,
                    value=default_weight,
                    step=5,
                    key=f"sp_{mode}_assign_weight"
                )
            
            # Weight validation
            validation = setup_queries.validate_assignment_weight(
                employee_id=employee_id,
                year=year,
                new_weight=weight,
                exclude_assignment_id=assignment_id if mode == 'edit' else None
            )
            
            val_col1, val_col2 = st.columns(2)
            with val_col1:
                st.metric("Current Weight Sum", f"{validation['current_total']}%")
            with val_col2:
                if validation['new_total'] == 100:
                    st.success(f"✅ After save: {validation['new_total']}%")
                elif validation['new_total'] > 100:
                    st.error(f"🔴 After save: {validation['new_total']}% (over limit!)")
                else:
                    st.warning(f"⚠️ After save: {validation['new_total']}% ({100 - validation['new_total']}% remaining)")
            
            notes = st.text_input(
                "Notes (optional)",
                value=existing['notes'] if existing is not None and pd.notna(existing.get('notes')) else "",
                key=f"sp_{mode}_assign_notes"
            )
            
            # Buttons
            col_submit, col_cancel = st.columns(2)
            
            with col_submit:
                submitted = st.form_submit_button(
                    "💾 Save" if mode == 'add' else "💾 Update",
                    type="primary",
                    use_container_width=True
                )
            
            with col_cancel:
                cancelled = st.form_submit_button("❌ Cancel", use_container_width=True)
            
            if submitted:
                if annual_target <= 0:
                    st.error("Annual target must be > 0")
                elif weight <= 0:
                    st.error("Weight must be > 0")
                else:
                    if mode == 'add':
                        result = setup_queries.create_assignment(
                            employee_id=employee_id,
                            kpi_type_id=kpi_type_id,
                            year=year,
                            annual_target_value=annual_target,
                            weight=weight,
                            notes=notes if notes else None
                        )
                    else:
                        result = setup_queries.update_assignment(
                            assignment_id=assignment_id,
                            annual_target_value=annual_target,
                            weight=weight,
                            notes=notes if notes else None
                        )
                    
                    if result['success']:
                        st.success("Saved!")
                        st.session_state['sp_show_add_assignment_form'] = False
                        st.session_state['sp_edit_assignment_id'] = None
                        st.session_state['sp_add_assignment_employee_id'] = None
                        st.rerun(scope="fragment")
                    else:
                        st.error(result['message'])
            
            if cancelled:
                st.session_state['sp_show_add_assignment_form'] = False
                st.session_state['sp_edit_assignment_id'] = None
                st.session_state['sp_add_assignment_employee_id'] = None
                st.rerun(scope="fragment")


# =============================================================================
# SALESPEOPLE SECTION
# =============================================================================

@st.fragment  
def salespeople_section(
    setup_queries: SalespersonSetupQueries,
    employee_ids: List[int] = None,  # FIX v1.3.1: Filter by team scope
    can_edit: bool = False
):
    """
    Salespeople sub-tab with list view.
    
    FIX v1.3.1: Added employee_ids parameter to filter by team scope.
    Non-admin users should only see their team members.
    """
    
    # Toolbar
    col1, col2 = st.columns([1, 5])
    
    with col1:
        status_options = {
            'ACTIVE': '🟢 Active',
            'all': '📋 All Status',
            'INACTIVE': '🟡 Inactive',
            'TERMINATED': '🔴 Terminated',
            'ON_LEAVE': '🟠 On Leave'
        }
        status_filter = st.selectbox(
            "Status",
            options=list(status_options.keys()),
            format_func=lambda x: status_options[x],
            key="sp_salespeople_status"
        )
    
    with col2:
        search = st.text_input("🔍 Search", placeholder="Name or email...", key="sp_salespeople_search")
    
    st.divider()
    
    # Get salespeople
    include_inactive = (status_filter == 'all')
    status_param = status_filter if status_filter != 'all' else None
    
    salespeople_df = setup_queries.get_salespeople(
        status_filter=status_param,
        include_inactive=include_inactive
    )
    
    # FIX v1.3.1: Filter by employee_ids (team scope)
    if not salespeople_df.empty and employee_ids is not None:
        salespeople_df = salespeople_df[salespeople_df['employee_id'].isin(employee_ids)]
    
    # Client-side search
    if not salespeople_df.empty and search:
        search_lower = search.lower()
        mask = (
            salespeople_df['employee_name'].fillna('').str.lower().str.contains(search_lower, regex=False) |
            salespeople_df['email'].fillna('').str.lower().str.contains(search_lower, regex=False)
        )
        salespeople_df = salespeople_df[mask]
    
    if salespeople_df.empty:
        st.info("No salespeople found")
        return
    
    st.caption(f"📊 Showing **{len(salespeople_df)}** salespeople")
    
    # Render cards
    for _, row in salespeople_df.iterrows():
        status_icon = STATUS_ICONS.get(row['status'], '❓')
        
        with st.container(border=True):
            col1, col2, col3 = st.columns([3, 2, 1])
            
            with col1:
                st.markdown(f"### {status_icon} {row['employee_name']}")
                st.caption(row['email'] or '')
                
                # Position info
                info_parts = []
                if row.get('title_name') and pd.notna(row['title_name']):
                    info_parts.append(row['title_name'])
                if row.get('department_name') and pd.notna(row['department_name']):
                    info_parts.append(row['department_name'])
                if info_parts:
                    st.caption(" • ".join(info_parts))
            
            with col2:
                # Stats
                st.metric(
                    label="Active Splits",
                    value=row['active_split_count'],
                    help="Number of active split rules"
                )
            
            with col3:
                st.metric(
                    label=f"{date.today().year} KPIs",
                    value=row['current_year_kpi_count'],
                    help=f"Number of KPI assignments for {date.today().year}"
                )
            
            # Manager info
            if row.get('manager_name') and pd.notna(row['manager_name']):
                st.caption(f"👔 Manager: {row['manager_name']}")