# utils/kpi_center_performance/setup/fragments.py
"""
UI Fragments for Setup Tab - KPI Center Performance

Full management console with 4 sub-tabs:
1. Split Rules - CRUD for kpi_center_split_by_customer_product
2. KPI Assignments - CRUD for sales_kpi_center_assignments
3. Hierarchy - Tree view of kpi_centers
4. Validation - Health check dashboard

"""

import streamlit as st
import pandas as pd
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Any

from .queries import SetupQueries


# =============================================================================
# CONSTANTS - Synced with main KPI Center Performance page
# =============================================================================

KPI_TYPES = ['TERRITORY', 'VERTICAL', 'BRAND', 'INTERNAL']

KPI_TYPE_ICONS = {
    'TERRITORY': '🌍',
    'VERTICAL': '📊',
    'BRAND': '🏷️',
    'INTERNAL': '🏢'
}

KPI_ICONS = {
    'revenue': '💰',
    'gross_profit': '📈',
    'gross_profit_1': '📊',
    'gp1': '📊',
    'num_new_customers': '👥',
    'num_new_products': '📦',
    'new_business_revenue': '💼',
}


# =============================================================================
# HELPER FUNCTIONS - Consistent with main page formatting
# =============================================================================

def format_currency(value: float, decimals: int = 0) -> str:
    """Format value as USD currency - same pattern as main page."""
    if pd.isna(value) or value == 0:
        return "$0"
    if decimals > 0:
        return f"${value:,.{decimals}f}"
    return f"${value:,.0f}"


def format_product_display(product_name: str, pt_code: str = None, package_size: str = None, brand: str = None, include_brand: bool = False) -> str:
    """
    Format product for display.
    
    For DataTable fallback: "code | name (package_size)" - matches SQL view format
    For Form Header (include_brand=True): "code | name | package_size (brand)"
    
    Args:
        product_name: Product name
        pt_code: Product code
        package_size: Package size
        brand: Brand name
        include_brand: If True, append brand at end. Default False to match SQL view.
    """
    parts = []
    if pt_code and str(pt_code).strip() and str(pt_code).strip() != 'None':
        parts.append(str(pt_code).strip())
    if product_name and str(product_name).strip():
        parts.append(str(product_name).strip())
    
    # Package size format depends on include_brand
    pkg = str(package_size).strip() if package_size and str(package_size).strip() and str(package_size).strip() != 'None' else None
    
    if include_brand:
        # Form Header format: "code | name | package_size (brand)"
        if pkg:
            parts.append(pkg)
        result = " | ".join(parts) if parts else "N/A"
        if brand and str(brand).strip() and str(brand).strip() != 'None':
            result = f"{result} ({brand})"
    else:
        # SQL View format: "code | name (package_size)"
        result = " | ".join(parts) if parts else "N/A"
        if pkg:
            result = f"{result} ({pkg})"
    
    return result


def format_customer_display(customer_name: str, company_code: str = None) -> str:
    """
    Format customer for display: "code | english_name".
    """
    parts = []
    if company_code and str(company_code).strip() and str(company_code).strip() != 'None':
        parts.append(str(company_code).strip())
    if customer_name and str(customer_name).strip():
        parts.append(str(customer_name).strip())
    
    return " | ".join(parts) if parts else "N/A"


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
    """
    Get period status: (icon, text, delta_color for st.metric).
    Returns tuple for use with st.metric delta_color.
    """
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
    kpi_center_ids: List[int] = None,
    active_filters: Dict = None
):
    """
    Main fragment for Setup tab with 4 sub-tabs.
    
    Args:
        kpi_center_ids: List of selected KPI Center IDs from sidebar
        active_filters: Dict of active filters from sidebar
    """
    st.subheader("⚙️ KPI Center Configuration")
    
    # Initialize queries with user context
    # Note: user_id should be users.id (INT), not UUID
    # The auth system should store this in session_state
    user_id = st.session_state.get('user_id') or st.session_state.get('user_uuid')
    setup_queries = SetupQueries(user_id=user_id)
    
    # Get user role for permission check
    # FIX: Case-insensitive check to match auth.py which stores lowercase role from DB
    user_role = st.session_state.get('user_role', 'viewer')
    user_role_lower = str(user_role).lower() if user_role else ''
    can_edit = user_role_lower in ['admin', 'gm', 'md', 'director']
    can_approve = user_role_lower == 'admin'
    
    # Get year from filters
    current_year = active_filters.get('year', date.today().year) if active_filters else date.today().year
    
    # Create 4 sub-tabs
    tab1, tab2, tab3, tab4 = st.tabs([
        "📋 Split Rules",
        "🎯 KPI Assignments", 
        "🌳 Hierarchy",
        "📊 Validation"
    ])
    
    with tab1:
        split_rules_section(
            setup_queries=setup_queries,
            kpi_center_ids=kpi_center_ids,
            can_edit=can_edit,
            can_approve=can_approve
        )
    
    with tab2:
        kpi_assignments_section(
            setup_queries=setup_queries,
            kpi_center_ids=kpi_center_ids,
            can_edit=can_edit,
            current_year=current_year
        )
    
    with tab3:
        hierarchy_section(
            setup_queries=setup_queries,
            can_edit=can_edit
        )
    
    with tab4:
        validation_section(
            setup_queries=setup_queries,
            current_year=current_year
        )


# =============================================================================
# SPLIT RULES SECTION
# =============================================================================

@st.fragment
def split_rules_section(
    setup_queries: SetupQueries,
    kpi_center_ids: List[int] = None,
    can_edit: bool = False,
    can_approve: bool = False
):
    """Split Rules sub-tab with CRUD operations."""
    
    # -------------------------------------------------------------------------
    # SUMMARY METRICS - Using st.metric like Overview tab
    # -------------------------------------------------------------------------
    stats = setup_queries.get_split_summary_stats()
    
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        st.metric(
            label="Total Rules",
            value=f"{stats['total_rules']:,}",
            help="Total active split rules in system"
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
    
    st.divider()
    
    # -------------------------------------------------------------------------
    # TOOLBAR
    # -------------------------------------------------------------------------
    if can_edit:
        if st.button("➕ Add Split Rule", type="primary"):
            st.session_state['show_add_split_form'] = True
    
    # -------------------------------------------------------------------------
    # ADD/EDIT FORMS
    # -------------------------------------------------------------------------
    if st.session_state.get('show_add_split_form', False):
        _render_split_form(setup_queries, can_approve, mode='add')
    
    if st.session_state.get('edit_split_id'):
        _render_split_form(setup_queries, can_approve, mode='edit', 
                          rule_id=st.session_state['edit_split_id'])
    
    # -------------------------------------------------------------------------
    # FILTERS
    # -------------------------------------------------------------------------
    with st.expander("🔍 Filters", expanded=False):
        f_col1, f_col2, f_col3, f_col4 = st.columns(4)
        
        with f_col1:
            kpi_type_filter = st.selectbox(
                "KPI Type",
                ['All'] + KPI_TYPES,
                key="split_kpi_type_filter"
            )
        
        with f_col2:
            status_options = {
                'All': 'All Status',
                'ok': '✅ OK',
                'incomplete_split': '⚠️ Under 100%',
                'over_100_split': '🔴 Over 100%'
            }
            status_filter = st.selectbox(
                "Status",
                list(status_options.keys()),
                format_func=lambda x: status_options[x],
                key="split_status_filter"
            )
        
        with f_col3:
            approval_options = {
                'all': 'All',
                'approved': '✅ Approved',
                'pending': '⏳ Pending'
            }
            approval_filter = st.selectbox(
                "Approval",
                list(approval_options.keys()),
                format_func=lambda x: approval_options[x],
                key="split_approval_filter"
            )
        
        with f_col4:
            product_search = st.text_input(
                "Search Product",
                placeholder="PT code or name...",
                key="split_product_search"
            )
    
    # -------------------------------------------------------------------------
    # GET DATA
    # -------------------------------------------------------------------------
    query_params = {'active_only': True, 'limit': 500}
    
    if kpi_center_ids:
        query_params['kpi_center_ids'] = kpi_center_ids
    if kpi_type_filter != 'All':
        query_params['kpi_type'] = kpi_type_filter
    if status_filter != 'All':
        query_params['status_filter'] = status_filter
    if approval_filter != 'all':
        query_params['approval_filter'] = approval_filter
    
    split_df = setup_queries.get_kpi_split_data(**query_params)
    
    # Client-side product search
    if product_search and not split_df.empty:
        search_lower = product_search.lower()
        mask = (
            split_df['product_name'].fillna('').str.lower().str.contains(search_lower) |
            split_df['pt_code'].fillna('').str.lower().str.contains(search_lower)
        )
        split_df = split_df[mask]
    
    if split_df.empty:
        st.info("No split rules found matching the filters")
        return
    
    st.caption(f"Showing {len(split_df):,} rules")
    
    # -------------------------------------------------------------------------
    # DATA TABLE - Updated with new view columns (v2.0)
    # -------------------------------------------------------------------------
    display_df = split_df.copy()
    
    # Format ID for display
    display_df['ID'] = display_df['kpi_center_split_id'].apply(lambda x: f"#{x}")
    
    # Format KPI Type with icon
    display_df['Type'] = display_df['kpi_type'].apply(
        lambda x: f"{KPI_TYPE_ICONS.get(x, '📁')} {x}" if pd.notna(x) else ''
    )
    
    # Use pre-formatted columns from view (or fallback to manual format)
    if 'customer_display' in display_df.columns:
        display_df['Customer'] = display_df['customer_display']
    else:
        display_df['Customer'] = display_df.apply(
            lambda r: format_customer_display(r.get('customer_name', ''), r.get('company_code', '')), 
            axis=1
        )
    
    if 'product_display' in display_df.columns:
        display_df['Product'] = display_df['product_display']
    else:
        display_df['Product'] = display_df.apply(
            lambda r: format_product_display(r['product_name'], r.get('pt_code'), r.get('package_size'), r.get('brand')), 
            axis=1
        )
    
    # Format split percentage
    display_df['Split'] = display_df['split_percentage'].apply(lambda x: f"{x:.0f}%")
    
    # Format status
    display_df['Status'] = display_df['kpi_split_status'].apply(
        lambda x: get_status_display(x)[0]
    )
    
    # Format approval with approver name
    display_df['Approved'] = display_df.apply(
        lambda r: f"✅ {r.get('approved_by_name', '').strip()}" if r.get('is_approved') else '⏳ Pending',
        axis=1
    )
    
    # Format creator name
    display_df['Created By'] = display_df['created_by_name'].fillna('').apply(lambda x: x.strip() if x else '-')
    
    # Display table with all columns
    st.dataframe(
        display_df[[
            'ID', 'kpi_center_name', 'Type', 'Customer', 'Product', 'brand',
            'Split', 'effective_period', 'Status', 'Approved', 'Created By'
        ]],
        hide_index=True,
        column_config={
            'ID': st.column_config.TextColumn('ID', width='small'),
            'kpi_center_name': st.column_config.TextColumn('KPI Center', width='medium'),
            'Type': st.column_config.TextColumn('Type', width='small'),
            'Customer': st.column_config.TextColumn('Customer', width='large'),
            'Product': st.column_config.TextColumn('Product', width='large'),
            'brand': st.column_config.TextColumn('Brand', width='small'),
            'Split': st.column_config.TextColumn('Split %', width='small'),
            'effective_period': st.column_config.TextColumn('Period', width='medium'),
            'Status': st.column_config.TextColumn('Status', width='small'),
            'Approved': st.column_config.TextColumn('Approved', width='medium'),
            'Created By': st.column_config.TextColumn('Created By', width='medium'),
        },
        use_container_width=True
    )
    
    # -------------------------------------------------------------------------
    # ROW ACTIONS - Updated with ID reference
    # -------------------------------------------------------------------------
    if can_edit and not split_df.empty:
        with st.expander("✏️ Edit / Delete Rule"):
            col1, col2, col3 = st.columns([3, 1, 1])
            
            with col1:
                # Build rule options with user-friendly display
                # Format: "#ID | customer english name (code) | product name (code | package size) (Split%) → KPI_TYPE"
                def format_rule_option(r):
                    rule_id = r['kpi_center_split_id']
                    
                    # Customer: english_name (code)
                    customer_name = r.get('customer_name', '')
                    company_code = r.get('company_code', '')
                    customer = f"{customer_name} ({company_code})" if company_code else customer_name
                    
                    # Product: name (code | package_size)
                    product_name = r.get('product_name', '')
                    pt_code = r.get('pt_code', '')
                    package_size = r.get('package_size', '')
                    product_detail = " | ".join(filter(None, [pt_code, package_size]))
                    product = f"{product_name} ({product_detail})" if product_detail else product_name
                    
                    split = r.get('split_percentage', 0)
                    kpi_type = r.get('kpi_type', '')
                    
                    return (
                        rule_id,
                        f"#{rule_id} | {customer} | {product} ({split:.0f}%) → {kpi_type}"
                    )
                
                rule_options = split_df.head(100).apply(format_rule_option, axis=1).tolist()
                rule_options = [(None, "Select a rule...")] + rule_options
                
                selected_rule = st.selectbox(
                    "Rule",
                    options=[r[0] for r in rule_options],
                    format_func=lambda x: next((r[1] for r in rule_options if r[0] == x), ""),
                    key="select_split_rule"
                )
            
            with col2:
                if selected_rule and st.button("✏️ Edit", use_container_width=True):
                    st.session_state['edit_split_id'] = selected_rule
                    st.rerun(scope="fragment")
            
            with col3:
                if selected_rule and st.button("🗑️ Delete", use_container_width=True):
                    result = setup_queries.delete_split_rule(selected_rule)
                    if result['success']:
                        st.success("Rule deleted")
                        st.rerun(scope="fragment")
                    else:
                        st.error(result['message'])


def _render_split_form(setup_queries: SetupQueries, can_approve: bool, 
                       mode: str = 'add', rule_id: int = None):
    """Render Add/Edit split rule form."""
    
    existing = None
    if mode == 'edit' and rule_id:
        df = setup_queries.get_kpi_split_data(limit=5000)
        df = df[df['kpi_center_split_id'] == rule_id]
        if not df.empty:
            existing = df.iloc[0]
        else:
            st.error("Rule not found")
            st.session_state['edit_split_id'] = None
            return
    
    title = "✏️ Edit Split Rule" if mode == 'edit' else "➕ Add Split Rule"
    
    with st.container(border=True):
        st.markdown(f"### {title}")
        
        if mode == 'edit' and existing is not None:
            st.caption(f"Rule ID: {rule_id}")
            col_info1, col_info2 = st.columns(2)
            with col_info1:
                st.markdown(f"**Customer:** {format_customer_display(existing['customer_name'], existing.get('company_code'))}")
            with col_info2:
                st.markdown(f"**Product:** {format_product_display(existing['product_name'], existing.get('pt_code'), existing.get('package_size'), existing.get('brand'), include_brand=True)}")
        
        with st.form(f"{mode}_split_form", clear_on_submit=False):
            col1, col2 = st.columns(2)
            
            with col1:
                if mode == 'add':
                    # Customer search
                    customer_search = st.text_input("🔍 Search Customer", key=f"{mode}_cust_search")
                    customers_df = setup_queries.get_customers_for_dropdown(
                        search=customer_search if customer_search else None, 
                        limit=50
                    )
                    
                    if not customers_df.empty:
                        customer_id = st.selectbox(
                            "Customer *",
                            options=customers_df['customer_id'].tolist(),
                            format_func=lambda x: f"{customers_df[customers_df['customer_id'] == x]['customer_name'].iloc[0]} ({customers_df[customers_df['customer_id'] == x]['company_code'].iloc[0]})",
                            key=f"{mode}_customer_id"
                        )
                    else:
                        customer_id = None
                        st.caption("No customers found")
                else:
                    customer_id = existing['customer_id']
                
                # KPI Center selection
                centers_df = setup_queries.get_kpi_centers_for_dropdown()
                if not centers_df.empty:
                    default_idx = 0
                    if existing is not None and 'kpi_center_id' in existing:
                        matches = centers_df[centers_df['kpi_center_id'] == existing['kpi_center_id']]
                        if not matches.empty:
                            default_idx = centers_df.index.tolist().index(matches.index[0])
                    
                    kpi_center_id = st.selectbox(
                        "KPI Center *",
                        options=centers_df['kpi_center_id'].tolist(),
                        index=default_idx,
                        format_func=lambda x: f"{KPI_TYPE_ICONS.get(centers_df[centers_df['kpi_center_id'] == x]['kpi_type'].iloc[0], '📁')} {centers_df[centers_df['kpi_center_id'] == x]['kpi_center_name'].iloc[0]}",
                        key=f"{mode}_kpi_center_id"
                    )
                else:
                    kpi_center_id = None
            
            with col2:
                if mode == 'add':
                    # Product search
                    product_search = st.text_input("🔍 Search Product", key=f"{mode}_prod_search")
                    products_df = setup_queries.get_products_for_dropdown(
                        search=product_search if product_search else None,
                        limit=50
                    )
                    
                    if not products_df.empty:
                        # Format: "name (code | package_size)" - consistent with customer dropdown
                        def format_product_option(row):
                            name = row['product_name'] or ''
                            code = row['pt_code'] or ''
                            pkg = row.get('package_size', '') or ''
                            detail = " | ".join(filter(None, [code, pkg]))
                            return f"{name} ({detail})" if detail else name
                        
                        product_id = st.selectbox(
                            "Product *",
                            options=products_df['product_id'].tolist(),
                            format_func=lambda x: format_product_option(products_df[products_df['product_id'] == x].iloc[0]),
                            key=f"{mode}_product_id"
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
                    key=f"{mode}_split_pct"
                )
            
            # Validation display
            if customer_id and product_id and kpi_center_id and not centers_df.empty:
                selected_type = centers_df[centers_df['kpi_center_id'] == kpi_center_id]['kpi_type'].iloc[0]
                validation = setup_queries.validate_split_percentage(
                    customer_id=customer_id,
                    product_id=product_id,
                    kpi_type=selected_type,
                    new_percentage=split_pct,
                    exclude_rule_id=rule_id if mode == 'edit' else None
                )
                
                # Show validation result like metric display
                if validation['current_total'] > 0 or mode == 'edit':
                    val_col1, val_col2, val_col3 = st.columns(3)
                    with val_col1:
                        st.metric("Current Total", f"{validation['current_total']:.0f}%")
                    with val_col2:
                        st.metric("After Save", f"{validation['new_total']:.0f}%",
                                 delta=f"+{split_pct:.0f}%", delta_color="off")
                    with val_col3:
                        if validation['new_total'] == 100:
                            st.success("✅ Perfect!")
                        elif validation['new_total'] > 100:
                            st.error(f"🔴 Over by {validation['new_total'] - 100:.0f}%")
                        else:
                            st.warning(f"⚠️ {validation['remaining']:.0f}% remaining")
            
            # Period inputs
            col3, col4 = st.columns(2)
            with col3:
                default_from = pd.to_datetime(existing['effective_from']).date() if existing is not None and pd.notna(existing.get('effective_from')) else date.today()
                valid_from = st.date_input("Valid From *", value=default_from, key=f"{mode}_valid_from")
            
            with col4:
                default_to = pd.to_datetime(existing['effective_to']).date() if existing is not None and pd.notna(existing.get('effective_to')) else date(date.today().year, 12, 31)
                valid_to = st.date_input("Valid To *", value=default_to, key=f"{mode}_valid_to")
            
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
                if mode == 'add' and not all([customer_id, product_id, kpi_center_id]):
                    st.error("Please fill all required fields")
                else:
                    if mode == 'add':
                        result = setup_queries.create_split_rule(
                            customer_id=customer_id,
                            product_id=product_id,
                            kpi_center_id=kpi_center_id,
                            split_percentage=split_pct,
                            valid_from=valid_from,
                            valid_to=valid_to,
                            is_approved=can_approve
                        )
                    else:
                        result = setup_queries.update_split_rule(
                            rule_id=rule_id,
                            split_percentage=split_pct,
                            valid_from=valid_from,
                            valid_to=valid_to,
                            kpi_center_id=kpi_center_id
                        )
                    
                    if result['success']:
                        st.success(f"{'Created' if mode == 'add' else 'Updated'} successfully!")
                        st.session_state['show_add_split_form'] = False
                        st.session_state['edit_split_id'] = None
                        st.rerun(scope="fragment")
                    else:
                        st.error(result['message'])
            
            if cancelled:
                st.session_state['show_add_split_form'] = False
                st.session_state['edit_split_id'] = None
                st.rerun(scope="fragment")


# =============================================================================
# KPI ASSIGNMENTS SECTION - Styled like KPI & Targets > Progress tab
# =============================================================================

@st.fragment
def kpi_assignments_section(
    setup_queries: SetupQueries,
    kpi_center_ids: List[int] = None,
    can_edit: bool = False,
    current_year: int = None
):
    """KPI Assignments sub-tab - styled like KPI & Targets tab."""
    
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
            key="assign_year_filter"
        )
    
    with col2:
        centers_df = setup_queries.get_kpi_centers_for_dropdown()
        center_options = [(-1, "All KPI Centers")] + [
            (row['kpi_center_id'], f"{KPI_TYPE_ICONS.get(row['kpi_type'], '📁')} {row['kpi_center_name']}") 
            for _, row in centers_df.iterrows()
        ]
        selected_center_id = st.selectbox(
            "KPI Center",
            options=[c[0] for c in center_options],
            format_func=lambda x: next((c[1] for c in center_options if c[0] == x), ""),
            key="assign_center_filter"
        )
    
    with col3:
        if can_edit:
            st.write("")  # Spacer
            if st.button("➕ Add Assignment", type="primary", use_container_width=True):
                st.session_state['show_add_assignment_form'] = True
    
    st.divider()
    
    # -------------------------------------------------------------------------
    # ADD/EDIT FORMS
    # -------------------------------------------------------------------------
    if st.session_state.get('show_add_assignment_form', False):
        _render_assignment_form(setup_queries, selected_year, mode='add')
    
    if st.session_state.get('edit_assignment_id'):
        _render_assignment_form(setup_queries, selected_year, mode='edit',
                               assignment_id=st.session_state['edit_assignment_id'])
    
    # -------------------------------------------------------------------------
    # KPI TYPE SUMMARY - Like Overview tab metrics
    # -------------------------------------------------------------------------
    summary_df = setup_queries.get_assignment_summary_by_type(selected_year)
    
    if not summary_df.empty:
        st.markdown(f"#### 📊 {selected_year} Targets Overview")
        
        num_cols = min(len(summary_df), 4)
        cols = st.columns(num_cols)
        
        for idx, (_, row) in enumerate(summary_df.iterrows()):
            with cols[idx % num_cols]:
                kpi_lower = row['kpi_name'].lower().replace(' ', '_')
                icon = KPI_ICONS.get(kpi_lower, '📋')
                
                if row['unit_of_measure'] == 'USD':
                    value = format_currency(row['total_target'])
                else:
                    value = f"{row['total_target']:,.0f}"
                
                st.metric(
                    label=f"{icon} {row['kpi_name']}",
                    value=value,
                    delta=f"{row['center_count']} centers",
                    delta_color="off",
                    help=f"Total {selected_year} target for {row['kpi_name']}"
                )
        
        st.divider()
    
    # -------------------------------------------------------------------------
    # ASSIGNMENTS BY KPI CENTER - Card layout like Progress tab
    # -------------------------------------------------------------------------
    query_params = {'year': selected_year}
    if selected_center_id > 0:
        query_params['kpi_center_ids'] = [selected_center_id]
    elif kpi_center_ids:
        query_params['kpi_center_ids'] = kpi_center_ids
    
    assignments_df = setup_queries.get_kpi_assignments(**query_params)
    weight_summary_df = setup_queries.get_assignment_weight_summary(selected_year)
    
    if assignments_df.empty:
        st.info(f"No KPI assignments found for {selected_year}")
        return
    
    # Group by KPI Center
    for center_id in assignments_df['kpi_center_id'].unique():
        center_data = assignments_df[assignments_df['kpi_center_id'] == center_id]
        center_name = center_data.iloc[0]['kpi_center_name']
        center_type = center_data.iloc[0]['kpi_center_type']
        
        # Get weight sum
        weight_row = weight_summary_df[weight_summary_df['kpi_center_id'] == center_id]
        total_weight = int(weight_row['total_weight'].iloc[0]) if not weight_row.empty else 0
        kpi_count = len(center_data)
        
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
        
        icon = KPI_TYPE_ICONS.get(center_type, '📁')
        
        # Card container - like Progress tab
        with st.container(border=True):
            # Header
            header_col1, header_col2 = st.columns([4, 1])
            
            with header_col1:
                st.markdown(f"### {icon} {center_name}")
                st.caption(f"{center_type} • {kpi_count} KPI{'s' if kpi_count > 1 else ''}")
            
            with header_col2:
                st.metric(
                    label="Weight Sum",
                    value=f"{total_weight}%",
                    delta=weight_badge,
                    delta_color=weight_color,
                    help="Total weight should equal 100%"
                )
            
            # KPI rows
            for _, kpi in center_data.iterrows():
                _render_kpi_assignment_row(kpi, can_edit, setup_queries)
            
            # Add KPI button
            if can_edit:
                if st.button(
                    f"➕ Add KPI to {center_name}", 
                    key=f"add_kpi_btn_{center_id}",
                    use_container_width=True
                ):
                    st.session_state['add_assignment_center_id'] = center_id
                    st.session_state['show_add_assignment_form'] = True
                    st.rerun(scope="fragment")


def _render_kpi_assignment_row(kpi: pd.Series, can_edit: bool, setup_queries: SetupQueries):
    """Render a single KPI assignment row - Updated with creator/modifier info."""
    
    kpi_lower = kpi['kpi_name'].lower().replace(' ', '_')
    icon = KPI_ICONS.get(kpi_lower, '📋')
    
    col1, col2, col3, col4, col5 = st.columns([2, 3, 1, 2, 1])
    
    with col1:
        st.markdown(f"**{icon} {kpi['kpi_name']}**")
        # Show assignment ID for reference
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
        # Show creator and modifier info
        created_by = kpi.get('created_by_name', '').strip() if pd.notna(kpi.get('created_by_name')) else '-'
        modified_by = kpi.get('modified_by_name', '').strip() if pd.notna(kpi.get('modified_by_name')) else None
        
        if modified_by and modified_by != created_by:
            st.caption(f"👤 {created_by} • ✏️ {modified_by}")
        else:
            st.caption(f"👤 {created_by}")
    
    with col5:
        if can_edit:
            btn_col1, btn_col2 = st.columns(2)
            with btn_col1:
                if st.button("✏️", key=f"edit_assign_{kpi['assignment_id']}", help="Edit"):
                    st.session_state['edit_assignment_id'] = kpi['assignment_id']
                    st.rerun(scope="fragment")
            with btn_col2:
                if st.button("🗑️", key=f"del_assign_{kpi['assignment_id']}", help="Delete"):
                    result = setup_queries.delete_assignment(kpi['assignment_id'])
                    if result['success']:
                        st.rerun(scope="fragment")


def _render_assignment_form(setup_queries: SetupQueries, year: int,
                           mode: str = 'add', assignment_id: int = None):
    """Render Add/Edit assignment form."""
    
    existing = None
    if mode == 'edit' and assignment_id:
        df = setup_queries.get_kpi_assignments()
        df = df[df['assignment_id'] == assignment_id]
        if not df.empty:
            existing = df.iloc[0]
        else:
            st.error("Assignment not found")
            st.session_state['edit_assignment_id'] = None
            return
    
    title = "✏️ Edit KPI Assignment" if mode == 'edit' else "➕ Add KPI Assignment"
    
    with st.container(border=True):
        st.markdown(f"### {title}")
        
        with st.form(f"{mode}_assignment_form"):
            col1, col2 = st.columns(2)
            
            with col1:
                # KPI Center
                centers_df = setup_queries.get_kpi_centers_for_dropdown()
                
                default_center = st.session_state.get('add_assignment_center_id')
                if existing is not None:
                    default_center = existing['kpi_center_id']
                
                default_idx = 0
                if default_center and not centers_df.empty:
                    matches = centers_df[centers_df['kpi_center_id'] == default_center]
                    if not matches.empty:
                        default_idx = centers_df.index.tolist().index(matches.index[0])
                
                kpi_center_id = st.selectbox(
                    "KPI Center *",
                    options=centers_df['kpi_center_id'].tolist(),
                    index=default_idx,
                    format_func=lambda x: f"{KPI_TYPE_ICONS.get(centers_df[centers_df['kpi_center_id'] == x]['kpi_type'].iloc[0], '📁')} {centers_df[centers_df['kpi_center_id'] == x]['kpi_center_name'].iloc[0]}",
                    key=f"{mode}_assign_center",
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
                    key=f"{mode}_assign_type",
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
                    key=f"{mode}_assign_target"
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
                    key=f"{mode}_assign_weight"
                )
            
            # Weight validation
            validation = setup_queries.validate_assignment_weight(
                kpi_center_id=kpi_center_id,
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
                key=f"{mode}_assign_notes"
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
                            kpi_center_id=kpi_center_id,
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
                        st.session_state['show_add_assignment_form'] = False
                        st.session_state['edit_assignment_id'] = None
                        st.session_state['add_assignment_center_id'] = None
                        st.rerun(scope="fragment")
                    else:
                        st.error(result['message'])
            
            if cancelled:
                st.session_state['show_add_assignment_form'] = False
                st.session_state['edit_assignment_id'] = None
                st.session_state['add_assignment_center_id'] = None
                st.rerun(scope="fragment")


# =============================================================================
# HIERARCHY SECTION
# =============================================================================

@st.fragment  
def hierarchy_section(
    setup_queries: SetupQueries,
    can_edit: bool = False
):
    """Hierarchy sub-tab with tree view."""
    
    # Toolbar
    col1, col2 = st.columns([1, 5])
    
    with col1:
        if can_edit:
            if st.button("➕ Add Center", type="primary"):
                st.session_state['show_add_center_form'] = True
    
    with col2:
        expand_all = st.checkbox("Expand All", value=True, key="hier_expand_all")
    
    # Forms
    if st.session_state.get('show_add_center_form', False):
        _render_center_form(setup_queries, mode='add')
    
    if st.session_state.get('edit_center_id'):
        _render_center_form(setup_queries, mode='edit',
                           center_id=st.session_state['edit_center_id'])
    
    st.divider()
    
    # Get hierarchy
    hierarchy_df = setup_queries.get_kpi_center_hierarchy(include_stats=True)
    
    if hierarchy_df.empty:
        st.info("No KPI Centers found")
        return
    
    # Group by KPI Type
    for kpi_type in hierarchy_df['kpi_type'].dropna().unique():
        type_df = hierarchy_df[hierarchy_df['kpi_type'] == kpi_type].copy()
        icon = KPI_TYPE_ICONS.get(kpi_type, '📁')
        
        with st.expander(f"{icon} {kpi_type} ({len(type_df)} centers)", expanded=expand_all):
            # Build tree structure: render parents first, then their children
            _render_hierarchy_tree(type_df, can_edit, setup_queries, parent_id=None, level=0)


def _render_hierarchy_tree(df: pd.DataFrame, can_edit: bool, setup_queries: SetupQueries, 
                           parent_id: int = None, level: int = 0):
    """
    Recursively render hierarchy tree with proper parent-child grouping.
    
    Args:
        df: DataFrame containing all centers for this KPI type
        can_edit: Whether user can edit
        setup_queries: Query handler
        parent_id: Current parent ID (None for root level)
        level: Current indentation level
    """
    # Get nodes at this level (matching parent_id)
    if parent_id is None:
        # Root level: get nodes with no parent or parent_center_id is NULL
        current_level = df[df['parent_center_id'].isna() | (df['parent_center_id'] == 0)]
    else:
        current_level = df[df['parent_center_id'] == parent_id]
    
    # Sort by name
    current_level = current_level.sort_values('kpi_center_name')
    
    for _, row in current_level.iterrows():
        # Render this node
        _render_hierarchy_node(row, can_edit, setup_queries, level)
        
        # Recursively render children
        children = df[df['parent_center_id'] == row['kpi_center_id']]
        if not children.empty:
            _render_hierarchy_tree(df, can_edit, setup_queries, 
                                  parent_id=row['kpi_center_id'], level=level + 1)


def _render_hierarchy_node(row: pd.Series, can_edit: bool, setup_queries: SetupQueries, level: int = 0):
    """Render a single hierarchy node with proper indentation."""
    
    # Visual indent using CSS margin
    indent_px = level * 24
    has_children = row['children_count'] > 0
    
    # Icons based on level and children
    if level == 0:
        node_icon = "📁" if has_children else "📄"
    else:
        node_icon = "┗━ 📁" if has_children else "┗━ 📄"
    
    # Container with indent
    with st.container():
        col1, col2, col3 = st.columns([4, 2, 1])
        
        with col1:
            # Apply indentation
            name_display = row['kpi_center_name']
            if has_children:
                name_display = f"**{name_display}** ({row['children_count']} children)"
            
            if level > 0:
                st.markdown(
                    f"<div style='margin-left: {indent_px}px;'>{node_icon} {name_display}</div>",
                    unsafe_allow_html=True
                )
            else:
                st.markdown(f"{node_icon} {name_display}")
        
        with col2:
            stats_parts = []
            if row.get('assignment_count', 0) > 0:
                stats_parts.append(f"{int(row['assignment_count'])} KPIs")
            if row.get('split_count', 0) > 0:
                stats_parts.append(f"{int(row['split_count'])} splits")
            
            if stats_parts:
                st.caption(" | ".join(stats_parts))
            else:
                st.caption("No data")
        
        with col3:
            if can_edit:
                if st.button("✏️", key=f"edit_hier_{row['kpi_center_id']}", help="Edit"):
                    st.session_state['edit_center_id'] = row['kpi_center_id']
                    st.rerun(scope="fragment")


def _render_center_form(setup_queries: SetupQueries, mode: str = 'add', center_id: int = None):
    """Render Add/Edit KPI Center form."""
    
    existing = None
    if mode == 'edit' and center_id:
        existing = setup_queries.get_kpi_center_detail(center_id)
        if not existing:
            st.error("Center not found")
            st.session_state['edit_center_id'] = None
            return
    
    title = "✏️ Edit KPI Center" if mode == 'edit' else "➕ Add KPI Center"
    
    with st.container(border=True):
        st.markdown(f"### {title}")
        
        with st.form(f"{mode}_center_form"):
            col1, col2 = st.columns(2)
            
            with col1:
                name = st.text_input(
                    "Name *",
                    value=existing['kpi_center_name'] if existing else "",
                    key=f"{mode}_center_name"
                )
            
            with col2:
                if mode == 'add':
                    kpi_type = st.selectbox(
                        "Type *",
                        options=KPI_TYPES,
                        format_func=lambda x: f"{KPI_TYPE_ICONS.get(x, '📁')} {x}",
                        key=f"{mode}_center_type"
                    )
                else:
                    kpi_type = existing['kpi_type']
                    st.text_input("Type", value=f"{KPI_TYPE_ICONS.get(kpi_type, '📁')} {kpi_type}", disabled=True)
            
            description = st.text_input(
                "Description",
                value=existing.get('description', '') if existing else "",
                key=f"{mode}_center_desc"
            )
            
            # Parent selection
            current_type = kpi_type if mode == 'add' else existing['kpi_type']
            centers_df = setup_queries.get_kpi_centers_for_dropdown(
                kpi_type=current_type,
                exclude_ids=[center_id] if center_id else None
            )
            
            parent_options = [(0, "No Parent (Root)")] + [
                (row['kpi_center_id'], f"└ {row['kpi_center_name']}")
                for _, row in centers_df.iterrows()
            ]
            
            current_parent = existing.get('parent_center_id', 0) if existing else 0
            current_parent = current_parent if current_parent else 0
            default_idx = next((i for i, p in enumerate(parent_options) if p[0] == current_parent), 0)
            
            parent_id = st.selectbox(
                "Parent Center",
                options=[p[0] for p in parent_options],
                index=default_idx,
                format_func=lambda x: next((p[1] for p in parent_options if p[0] == x), ""),
                key=f"{mode}_center_parent"
            )
            
            # Buttons
            col_submit, col_cancel = st.columns(2)
            
            with col_submit:
                submitted = st.form_submit_button("💾 Save", type="primary", use_container_width=True)
            
            with col_cancel:
                cancelled = st.form_submit_button("❌ Cancel", use_container_width=True)
            
            if submitted:
                if not name:
                    st.error("Name is required")
                else:
                    if mode == 'add':
                        result = setup_queries.create_kpi_center(
                            name=name,
                            kpi_type=kpi_type,
                            description=description if description else None,
                            parent_center_id=parent_id if parent_id > 0 else None
                        )
                    else:
                        result = setup_queries.update_kpi_center(
                            kpi_center_id=center_id,
                            name=name,
                            description=description if description else None,
                            parent_center_id=parent_id
                        )
                    
                    if result['success']:
                        st.success("Saved!")
                        st.session_state['show_add_center_form'] = False
                        st.session_state['edit_center_id'] = None
                        st.rerun(scope="fragment")
                    else:
                        st.error(result['message'])
            
            if cancelled:
                st.session_state['show_add_center_form'] = False
                st.session_state['edit_center_id'] = None
                st.rerun(scope="fragment")


# =============================================================================
# VALIDATION SECTION
# =============================================================================

@st.fragment
def validation_section(setup_queries: SetupQueries, current_year: int = None):
    """Validation dashboard - health check for configurations."""
    
    current_year = current_year or date.today().year
    
    # Header
    col_title, col_refresh = st.columns([5, 1])
    with col_title:
        st.markdown("### 🏥 Configuration Health Check")
    with col_refresh:
        if st.button("🔄 Refresh"):
            st.rerun(scope="fragment")
    
    # Get issues
    issues = setup_queries.get_all_validation_issues(year=current_year)
    
    # -------------------------------------------------------------------------
    # HEALTH SUMMARY CARDS
    # -------------------------------------------------------------------------
    col1, col2, col3 = st.columns(3)
    
    split_summary = issues['summary'].get('split', {})
    split_critical = split_summary.get('over_100_count', 0)
    split_warning = split_summary.get('incomplete_count', 0)
    
    assign_summary = issues['summary'].get('assignment', {})
    assign_issues = assign_summary.get('weight_issues', 0) + assign_summary.get('no_assignment', 0)
    
    hier_summary = issues['summary'].get('hierarchy', {})
    
    with col1:
        if split_critical == 0 and split_warning == 0:
            st.success(f"### ✅ Split Rules\n\n{split_summary.get('total_rules', 0):,} rules OK")
        elif split_critical > 0:
            st.error(f"### 🔴 Split Rules\n\n{split_critical} critical issues")
        else:
            st.warning(f"### ⚠️ Split Rules\n\n{split_warning} warnings")
    
    with col2:
        if assign_issues == 0:
            st.success(f"### ✅ Assignments\n\n{current_year} configured")
        else:
            st.warning(f"### ⚠️ Assignments\n\n{assign_issues} issues")
    
    with col3:
        hier_count = hier_summary.get('total_centers', 0)
        st.info(f"### 🌳 Hierarchy\n\n{hier_count} centers")
    
    st.divider()
    
    # -------------------------------------------------------------------------
    # ISSUE DETAILS
    # -------------------------------------------------------------------------
    if issues['split_issues']:
        st.markdown("#### 📋 Split Rule Issues")
        
        for issue in issues['split_issues']:
            severity_icons = {'critical': '🔴', 'warning': '⚠️', 'info': 'ℹ️'}
            icon = severity_icons.get(issue['severity'], '❓')
            
            with st.container(border=True):
                col_desc, col_count = st.columns([4, 1])
                with col_desc:
                    st.markdown(f"{icon} **{issue['type'].replace('_', ' ').title()}**")
                    st.caption(issue['message'])
                with col_count:
                    st.metric("Count", issue['count'])
    
    if issues['assignment_issues']:
        st.markdown("#### 🎯 Assignment Issues")
        
        for issue in issues['assignment_issues']:
            severity_icons = {'critical': '🔴', 'warning': '⚠️', 'info': 'ℹ️'}
            icon = severity_icons.get(issue['severity'], '❓')
            
            with st.container(border=True):
                col_desc, col_count = st.columns([4, 1])
                with col_desc:
                    st.markdown(f"{icon} **{issue['type'].replace('_', ' ').title()}**")
                    st.caption(issue['message'])
                with col_count:
                    st.metric("Count", issue['count'])
                
                if issue.get('details'):
                    with st.expander("View Details"):
                        st.dataframe(
                            pd.DataFrame(issue['details']),
                            hide_index=True,
                            use_container_width=True
                        )
    
    if not issues['split_issues'] and not issues['assignment_issues']:
        st.success("🎉 All configurations are healthy! No issues found.")
    
    # -------------------------------------------------------------------------
    # QUICK STATS
    # -------------------------------------------------------------------------
    st.divider()
    st.markdown("#### 📊 Quick Statistics")
    
    stat_col1, stat_col2, stat_col3, stat_col4 = st.columns(4)
    
    with stat_col1:
        st.metric(
            "Total Split Rules",
            f"{split_summary.get('total_rules', 0):,}",
            help="Total active split rules"
        )
    
    with stat_col2:
        total = split_summary.get('total_rules', 0)
        ok = split_summary.get('ok_count', 0)
        pct = (ok / total * 100) if total > 0 else 0
        st.metric(
            "OK Rate",
            f"{pct:.0f}%",
            help="Percentage of rules with exactly 100% split"
        )
    
    with stat_col3:
        st.metric(
            "Pending Approval",
            f"{split_summary.get('pending_count', 0):,}",
            help="Rules awaiting approval"
        )
    
    with stat_col4:
        st.metric(
            "Expiring Soon",
            f"{split_summary.get('expiring_soon_count', 0):,}",
            help="Rules expiring within 30 days"
        )