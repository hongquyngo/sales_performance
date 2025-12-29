# utils/kpi_center_performance/setup/fragments.py
"""
UI Fragments for Setup Tab - KPI Center Performance

Full management console with 4 sub-tabs:
1. Split Rules - CRUD for kpi_center_split_by_customer_product
2. KPI Assignments - CRUD for sales_kpi_center_assignments
3. Hierarchy - Tree view of kpi_centers
4. Validation - Health check dashboard

VERSION: 2.0.0
CHANGELOG:
- v2.0.0: Full implementation per proposal v3.4.0
          - 4 sub-tabs with complete CRUD functionality
          - Enhanced filters and bulk operations
          - Interactive tree view for hierarchy
          - Validation dashboard with issue tracking
- v1.0.0: Initial read-only version
"""

import streamlit as st
import pandas as pd
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Any

from .queries import SetupQueries


# =============================================================================
# CONSTANTS
# =============================================================================

KPI_TYPES = ['TERRITORY', 'VERTICAL', 'BRAND', 'INTERNAL']

KPI_TYPE_COLORS = {
    'TERRITORY': '#3498db',  # Blue
    'VERTICAL': '#2ecc71',   # Green
    'BRAND': '#e74c3c',      # Red
    'INTERNAL': '#9b59b6'    # Purple
}

KPI_TYPE_ICONS = {
    'TERRITORY': '🌍',
    'VERTICAL': '📊',
    'BRAND': '🏷️',
    'INTERNAL': '🏢'
}

STATUS_BADGES = {
    'ok': ('✅', 'green'),
    'incomplete_split': ('⚠️', 'orange'),
    'over_100_split': ('🔴', 'red'),
    'approved': ('✅', 'green'),
    'pending': ('⏳', 'gray')
}


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
        kpi_center_ids: List of selected KPI Center IDs
        active_filters: Dict of active filters from sidebar
    """
    st.subheader("⚙️ KPI Center Configuration")
    
    # Initialize queries with user context
    user_id = st.session_state.get('user_uuid')
    setup_queries = SetupQueries(user_id=user_id)
    
    # Get user role for permission check
    user_role = st.session_state.get('user_role', 'Manager')
    can_edit = user_role in ['Admin', 'GM', 'MD']
    can_approve = user_role == 'Admin'
    
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
            can_edit=can_edit
        )
    
    with tab3:
        hierarchy_section(
            setup_queries=setup_queries,
            can_edit=can_edit
        )
    
    with tab4:
        validation_section(
            setup_queries=setup_queries
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
    """
    Split Rules sub-tab with CRUD operations.
    """
    # =========================================================================
    # SUMMARY CARDS
    # =========================================================================
    stats = setup_queries.get_split_summary_stats()
    
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        st.metric("Total Rules", f"{stats['total_rules']:,}")
    with col2:
        st.metric("✅ OK", f"{stats['ok_count']:,}", 
                  delta=None, delta_color="off")
    with col3:
        st.metric("⚠️ Under 100%", f"{stats['incomplete_count']:,}",
                  delta=None, delta_color="off")
    with col4:
        st.metric("🔴 Over 100%", f"{stats['over_100_count']:,}",
                  delta=None, delta_color="off")
    with col5:
        st.metric("⏳ Pending", f"{stats['pending_count']:,}",
                  delta=None, delta_color="off")
    
    st.divider()
    
    # =========================================================================
    # ADD BUTTON & FILTERS
    # =========================================================================
    col_add, col_filter = st.columns([1, 5])
    
    with col_add:
        if can_edit:
            if st.button("➕ Add Split Rule", type="primary", key="add_split_btn"):
                st.session_state['show_add_split_form'] = True
    
    # Show Add Form Dialog
    if st.session_state.get('show_add_split_form', False):
        _render_add_split_form(setup_queries, can_approve)
    
    # Show Edit Form Dialog
    if st.session_state.get('edit_split_id'):
        _render_edit_split_form(setup_queries, st.session_state['edit_split_id'])
    
    # =========================================================================
    # FILTERS
    # =========================================================================
    with st.expander("🔍 Filters", expanded=True):
        filter_col1, filter_col2, filter_col3, filter_col4 = st.columns(4)
        
        with filter_col1:
            # Customer filter
            customers_df = setup_queries.get_customers_for_dropdown(limit=500)
            customer_options = ['All'] + customers_df['customer_name'].tolist() if not customers_df.empty else ['All']
            selected_customer = st.selectbox(
                "Customer",
                customer_options,
                key="split_customer_filter"
            )
        
        with filter_col2:
            # KPI Type filter
            kpi_type_filter = st.selectbox(
                "KPI Type",
                ['All'] + KPI_TYPES,
                key="split_kpi_type_filter"
            )
        
        with filter_col3:
            # Status filter
            status_filter = st.selectbox(
                "Status",
                ['All', 'ok', 'incomplete_split', 'over_100_split'],
                format_func=lambda x: {
                    'All': 'All Status',
                    'ok': '✅ OK',
                    'incomplete_split': '⚠️ Under 100%',
                    'over_100_split': '🔴 Over 100%'
                }.get(x, x),
                key="split_status_filter"
            )
        
        with filter_col4:
            # Approval filter
            approval_filter = st.selectbox(
                "Approval",
                ['all', 'approved', 'pending'],
                format_func=lambda x: {
                    'all': 'All',
                    'approved': '✅ Approved',
                    'pending': '⏳ Pending'
                }.get(x, x),
                key="split_approval_filter"
            )
        
        # Second row of filters
        filter_col5, filter_col6, filter_col7, filter_col8 = st.columns(4)
        
        with filter_col5:
            product_search = st.text_input(
                "Search Product",
                placeholder="Product name or code...",
                key="split_product_search"
            )
        
        with filter_col6:
            # Brand filter
            brands_df = setup_queries.get_brands_for_dropdown()
            brand_options = ['All'] + brands_df['brand_name'].tolist() if not brands_df.empty else ['All']
            selected_brand = st.selectbox(
                "Brand",
                brand_options,
                key="split_brand_filter"
            )
        
        with filter_col7:
            active_only = st.checkbox("Active Only", value=True, key="split_active_only")
        
        with filter_col8:
            expiring_soon = st.checkbox("Expiring in 30 days", value=False, key="split_expiring")
    
    # =========================================================================
    # BUILD QUERY PARAMETERS
    # =========================================================================
    query_params = {
        'active_only': active_only,
        'limit': 1000
    }
    
    if kpi_center_ids:
        query_params['kpi_center_ids'] = kpi_center_ids
    
    if selected_customer != 'All':
        customer_id = customers_df[customers_df['customer_name'] == selected_customer]['customer_id'].iloc[0]
        query_params['customer_ids'] = [customer_id]
    
    if kpi_type_filter != 'All':
        query_params['kpi_type'] = kpi_type_filter
    
    if status_filter != 'All':
        query_params['status_filter'] = status_filter
    
    if approval_filter != 'all':
        query_params['approval_filter'] = approval_filter
    
    if selected_brand != 'All':
        brand_id = brands_df[brands_df['brand_name'] == selected_brand]['brand_id'].iloc[0]
        query_params['brand_ids'] = [brand_id]
    
    if expiring_soon:
        query_params['expiring_days'] = 30
    
    # =========================================================================
    # GET DATA
    # =========================================================================
    split_df = setup_queries.get_kpi_split_data(**query_params)
    
    # Apply product search client-side
    if product_search and not split_df.empty:
        mask = (
            split_df['product_pn'].fillna('').str.lower().str.contains(product_search.lower()) |
            split_df['pt_code'].fillna('').str.lower().str.contains(product_search.lower())
        )
        split_df = split_df[mask]
    
    if split_df.empty:
        st.info("No split rules found matching the filters")
        return
    
    st.caption(f"Showing {len(split_df):,} split rules")
    
    # =========================================================================
    # BULK ACTIONS
    # =========================================================================
    if can_edit:
        with st.expander("📦 Bulk Actions"):
            bulk_col1, bulk_col2, bulk_col3 = st.columns(3)
            
            with bulk_col1:
                if can_approve:
                    if st.button("✅ Approve Selected", key="bulk_approve"):
                        selected_ids = st.session_state.get('selected_split_ids', [])
                        if selected_ids:
                            result = setup_queries.approve_split_rules(
                                selected_ids, 
                                approved_by=st.session_state.get('user_employee_id')
                            )
                            if result['success']:
                                st.success(f"Approved {result['count']} rules")
                                st.rerun()
                            else:
                                st.error(result['message'])
                        else:
                            st.warning("No rules selected")
            
            with bulk_col2:
                if st.button("📋 Copy to New Period", key="bulk_copy"):
                    st.session_state['show_copy_period_form'] = True
            
            with bulk_col3:
                if st.button("🗑️ Delete Selected", key="bulk_delete"):
                    selected_ids = st.session_state.get('selected_split_ids', [])
                    if selected_ids:
                        result = setup_queries.delete_split_rules_bulk(selected_ids)
                        if result['success']:
                            st.success(f"Deleted {result['count']} rules")
                            st.rerun()
                        else:
                            st.error(result['message'])
                    else:
                        st.warning("No rules selected")
    
    # Copy to Period Form
    if st.session_state.get('show_copy_period_form', False):
        _render_copy_period_form(setup_queries)
    
    # =========================================================================
    # DATA TABLE
    # =========================================================================
    display_df = split_df.copy()
    
    # Add status badge column
    display_df['status_display'] = display_df['kpi_split_status'].apply(
        lambda x: STATUS_BADGES.get(x, ('❓', 'gray'))[0] + ' ' + x.replace('_', ' ').title()
    )
    
    # Add approval badge
    display_df['approval_display'] = display_df['approval_status'].apply(
        lambda x: '✅ Approved' if x == 'approved' else '⏳ Pending'
    )
    
    # Add expiring warning
    display_df['period_display'] = display_df.apply(
        lambda row: _format_period_with_warning(row['effective_from'], row['effective_to']),
        axis=1
    )
    
    # Display columns
    display_cols = [
        'kpi_center_name', 'customer_name', 'product_pn', 'brand',
        'split_percentage', 'period_display', 'status_display', 'approval_display'
    ]
    
    # Configure column display
    column_config = {
        'kpi_center_name': st.column_config.TextColumn('KPI Center', width='medium'),
        'customer_name': st.column_config.TextColumn('Customer', width='medium'),
        'product_pn': st.column_config.TextColumn('Product', width='medium'),
        'brand': st.column_config.TextColumn('Brand', width='small'),
        'split_percentage': st.column_config.NumberColumn('Split %', format="%.1f%%"),
        'period_display': st.column_config.TextColumn('Period', width='medium'),
        'status_display': st.column_config.TextColumn('Status', width='small'),
        'approval_display': st.column_config.TextColumn('Approval', width='small'),
    }
    
    # Add selection column if can edit
    if can_edit:
        display_df['select'] = False
        display_cols = ['select'] + display_cols
        column_config['select'] = st.column_config.CheckboxColumn('Select', default=False)
    
    # Show data editor
    edited_df = st.data_editor(
        display_df[display_cols].head(500),
        hide_index=True,
        column_config=column_config,
        use_container_width=True,
        disabled=[c for c in display_cols if c != 'select'],
        key="split_data_editor"
    )
    
    # Track selected IDs
    if can_edit and 'select' in edited_df.columns:
        selected_mask = edited_df['select'] == True
        selected_ids = display_df.loc[selected_mask.index[selected_mask], 'kpi_center_split_id'].tolist()
        st.session_state['selected_split_ids'] = selected_ids
    
    # =========================================================================
    # ROW ACTIONS
    # =========================================================================
    if can_edit:
        st.caption("Click on a row to edit or delete")
        
        action_col1, action_col2, action_col3 = st.columns([2, 1, 1])
        
        with action_col1:
            selected_row_id = st.selectbox(
                "Select Rule to Edit/Delete",
                options=[None] + split_df['kpi_center_split_id'].tolist(),
                format_func=lambda x: "Select a rule..." if x is None else f"Rule #{x}",
                key="select_rule_action"
            )
        
        with action_col2:
            if selected_row_id and st.button("✏️ Edit", key="edit_single"):
                st.session_state['edit_split_id'] = selected_row_id
                st.rerun()
        
        with action_col3:
            if selected_row_id and st.button("🗑️ Delete", key="delete_single"):
                result = setup_queries.delete_split_rule(selected_row_id)
                if result['success']:
                    st.success("Rule deleted")
                    st.rerun()
                else:
                    st.error(result['message'])


def _format_period_with_warning(valid_from, valid_to) -> str:
    """Format period with expiring warning."""
    if pd.isna(valid_to):
        return f"{valid_from} → No End"
    
    days_until = (pd.to_datetime(valid_to) - pd.Timestamp.now()).days
    
    if days_until < 0:
        return f"⚫ EXPIRED"
    elif days_until <= 30:
        return f"⚠️ {valid_from} → {valid_to}"
    else:
        return f"{valid_from} → {valid_to}"


def _render_add_split_form(setup_queries: SetupQueries, can_approve: bool):
    """Render the Add Split Rule form."""
    with st.expander("➕ Add New Split Rule", expanded=True):
        with st.form("add_split_form"):
            st.markdown("### Add Split Rule")
            
            col1, col2 = st.columns(2)
            
            with col1:
                # Customer search
                customer_search = st.text_input("Search Customer", key="add_customer_search")
                customers_df = setup_queries.get_customers_for_dropdown(search=customer_search, limit=50)
                
                if not customers_df.empty:
                    customer_id = st.selectbox(
                        "Customer *",
                        options=customers_df['customer_id'].tolist(),
                        format_func=lambda x: customers_df[customers_df['customer_id'] == x]['customer_name'].iloc[0],
                        key="add_customer_id"
                    )
                else:
                    st.warning("No customers found")
                    customer_id = None
            
            with col2:
                # Product search
                product_search = st.text_input("Search Product", key="add_product_search")
                products_df = setup_queries.get_products_for_dropdown(search=product_search, limit=50)
                
                if not products_df.empty:
                    product_id = st.selectbox(
                        "Product *",
                        options=products_df['product_id'].tolist(),
                        format_func=lambda x: products_df[products_df['product_id'] == x]['product_name'].iloc[0],
                        key="add_product_id"
                    )
                else:
                    st.warning("No products found")
                    product_id = None
            
            col3, col4 = st.columns(2)
            
            with col3:
                # KPI Center
                centers_df = setup_queries.get_kpi_centers_for_dropdown()
                if not centers_df.empty:
                    kpi_center_id = st.selectbox(
                        "KPI Center *",
                        options=centers_df['kpi_center_id'].tolist(),
                        format_func=lambda x: f"{centers_df[centers_df['kpi_center_id'] == x]['kpi_center_name'].iloc[0]} ({centers_df[centers_df['kpi_center_id'] == x]['kpi_type'].iloc[0]})",
                        key="add_kpi_center_id"
                    )
                else:
                    kpi_center_id = None
            
            with col4:
                split_percentage = st.number_input(
                    "Split % *",
                    min_value=0.0,
                    max_value=100.0,
                    value=100.0,
                    step=5.0,
                    key="add_split_pct"
                )
            
            # Show current splits if customer and product selected
            if customer_id and product_id:
                # Get selected center's type
                selected_type = centers_df[centers_df['kpi_center_id'] == kpi_center_id]['kpi_type'].iloc[0] if kpi_center_id else None
                
                existing_df = setup_queries.get_split_by_customer_product(
                    customer_id=customer_id,
                    product_id=product_id,
                    kpi_type=selected_type
                )
                
                if not existing_df.empty:
                    current_total = existing_df['split_percentage'].sum()
                    st.info(f"📊 Current splits for this combo ({selected_type}): {current_total}%")
                    
                    for _, row in existing_df.iterrows():
                        st.caption(f"  • {row['kpi_center_name']}: {row['split_percentage']}%")
                    
                    new_total = current_total + split_percentage
                    if new_total > 100:
                        st.error(f"⚠️ Adding {split_percentage}% will result in {new_total}% (over limit)")
                    elif new_total == 100:
                        st.success(f"✅ Total will be exactly 100%")
                    else:
                        st.warning(f"Total will be {new_total}% ({100 - new_total}% remaining)")
            
            col5, col6 = st.columns(2)
            
            with col5:
                valid_from = st.date_input(
                    "Valid From *",
                    value=date.today(),
                    key="add_valid_from"
                )
            
            with col6:
                valid_to = st.date_input(
                    "Valid To *",
                    value=date(date.today().year, 12, 31),
                    key="add_valid_to"
                )
            
            col_submit, col_cancel = st.columns(2)
            
            with col_submit:
                submitted = st.form_submit_button("Save", type="primary")
            
            with col_cancel:
                if st.form_submit_button("Cancel"):
                    st.session_state['show_add_split_form'] = False
                    st.rerun()
            
            if submitted:
                if not all([customer_id, product_id, kpi_center_id]):
                    st.error("Please fill all required fields")
                else:
                    result = setup_queries.create_split_rule(
                        customer_id=customer_id,
                        product_id=product_id,
                        kpi_center_id=kpi_center_id,
                        split_percentage=split_percentage,
                        valid_from=valid_from,
                        valid_to=valid_to,
                        is_approved=can_approve
                    )
                    
                    if result['success']:
                        st.success(f"Split rule created (ID: {result['id']})")
                        st.session_state['show_add_split_form'] = False
                        st.rerun()
                    else:
                        st.error(result['message'])


def _render_edit_split_form(setup_queries: SetupQueries, rule_id: int):
    """Render the Edit Split Rule form."""
    # Get current rule data
    rule_df = setup_queries.get_kpi_split_data(limit=1)
    rule_df = rule_df[rule_df['kpi_center_split_id'] == rule_id]
    
    if rule_df.empty:
        st.error("Rule not found")
        st.session_state['edit_split_id'] = None
        return
    
    rule = rule_df.iloc[0]
    
    with st.expander(f"✏️ Edit Split Rule #{rule_id}", expanded=True):
        with st.form("edit_split_form"):
            st.markdown(f"**Customer:** {rule['customer_name']}")
            st.markdown(f"**Product:** {rule['product_pn']}")
            st.markdown(f"**KPI Center:** {rule['kpi_center_name']}")
            
            col1, col2 = st.columns(2)
            
            with col1:
                new_split_pct = st.number_input(
                    "Split %",
                    min_value=0.0,
                    max_value=100.0,
                    value=float(rule['split_percentage']),
                    step=5.0,
                    key="edit_split_pct"
                )
            
            with col2:
                # Validate new percentage
                validation = setup_queries.validate_split_percentage(
                    customer_id=rule['customer_id'],
                    product_id=rule['product_id'],
                    kpi_type=rule['kpi_type'],
                    new_percentage=new_split_pct,
                    exclude_rule_id=rule_id
                )
                
                if validation['valid']:
                    st.success(validation['message'])
                else:
                    st.error(validation['message'])
            
            col3, col4 = st.columns(2)
            
            with col3:
                new_valid_from = st.date_input(
                    "Valid From",
                    value=pd.to_datetime(rule['effective_from']).date() if pd.notna(rule['effective_from']) else date.today(),
                    key="edit_valid_from"
                )
            
            with col4:
                new_valid_to = st.date_input(
                    "Valid To",
                    value=pd.to_datetime(rule['effective_to']).date() if pd.notna(rule['effective_to']) else date(date.today().year, 12, 31),
                    key="edit_valid_to"
                )
            
            col_submit, col_cancel = st.columns(2)
            
            with col_submit:
                if st.form_submit_button("Save Changes", type="primary"):
                    result = setup_queries.update_split_rule(
                        rule_id=rule_id,
                        split_percentage=new_split_pct,
                        valid_from=new_valid_from,
                        valid_to=new_valid_to
                    )
                    
                    if result['success']:
                        st.success("Rule updated")
                        st.session_state['edit_split_id'] = None
                        st.rerun()
                    else:
                        st.error(result['message'])
            
            with col_cancel:
                if st.form_submit_button("Cancel"):
                    st.session_state['edit_split_id'] = None
                    st.rerun()


def _render_copy_period_form(setup_queries: SetupQueries):
    """Render the Copy to Period form."""
    with st.expander("📋 Copy Rules to New Period", expanded=True):
        with st.form("copy_period_form"):
            st.markdown("Copy selected rules to a new validity period")
            
            selected_ids = st.session_state.get('selected_split_ids', [])
            st.info(f"{len(selected_ids)} rules selected")
            
            col1, col2 = st.columns(2)
            
            with col1:
                new_valid_from = st.date_input(
                    "New Valid From",
                    value=date(date.today().year + 1, 1, 1),
                    key="copy_valid_from"
                )
            
            with col2:
                new_valid_to = st.date_input(
                    "New Valid To",
                    value=date(date.today().year + 1, 12, 31),
                    key="copy_valid_to"
                )
            
            col_submit, col_cancel = st.columns(2)
            
            with col_submit:
                if st.form_submit_button("Copy Rules", type="primary"):
                    if not selected_ids:
                        st.error("No rules selected")
                    else:
                        result = setup_queries.copy_splits_to_period(
                            rule_ids=selected_ids,
                            new_valid_from=new_valid_from,
                            new_valid_to=new_valid_to
                        )
                        
                        if result['success']:
                            st.success(f"Copied {len(selected_ids)} rules to new period")
                            st.session_state['show_copy_period_form'] = False
                            st.rerun()
                        else:
                            st.error(result['message'])
            
            with col_cancel:
                if st.form_submit_button("Cancel"):
                    st.session_state['show_copy_period_form'] = False
                    st.rerun()


# =============================================================================
# KPI ASSIGNMENTS SECTION
# =============================================================================

@st.fragment
def kpi_assignments_section(
    setup_queries: SetupQueries,
    kpi_center_ids: List[int] = None,
    can_edit: bool = False
):
    """
    KPI Assignments sub-tab with CRUD operations.
    """
    # =========================================================================
    # FILTER BAR
    # =========================================================================
    col1, col2, col3, col4 = st.columns([1, 1, 1, 1])
    
    with col1:
        available_years = setup_queries.get_available_years()
        current_year = date.today().year
        if current_year not in available_years:
            available_years.append(current_year)
        available_years.sort(reverse=True)
        
        selected_year = st.selectbox(
            "Year",
            options=available_years,
            index=0,
            key="assignment_year"
        )
    
    with col2:
        centers_df = setup_queries.get_kpi_centers_for_dropdown()
        center_options = [('All', None)] + [(row['kpi_center_name'], row['kpi_center_id']) 
                                             for _, row in centers_df.iterrows()]
        selected_center = st.selectbox(
            "KPI Center",
            options=center_options,
            format_func=lambda x: x[0],
            key="assignment_center"
        )
    
    with col3:
        kpi_types_df = setup_queries.get_kpi_types()
        kpi_type_options = [('All', None)] + [(row['kpi_name'], row['kpi_type_id']) 
                                               for _, row in kpi_types_df.iterrows()]
        selected_kpi_type = st.selectbox(
            "KPI Type",
            options=kpi_type_options,
            format_func=lambda x: x[0],
            key="assignment_kpi_type"
        )
    
    with col4:
        if can_edit:
            st.write("")  # Spacer
            st.write("")
            if st.button("➕ Add Assignment", type="primary", key="add_assignment_btn"):
                st.session_state['show_add_assignment_form'] = True
    
    st.divider()
    
    # =========================================================================
    # SUMMARY BY KPI TYPE
    # =========================================================================
    summary_df = setup_queries.get_assignment_summary_by_type(selected_year)
    
    if not summary_df.empty:
        st.markdown(f"### {selected_year} KPI Targets Overview")
        
        summary_cols = st.columns(len(summary_df) if len(summary_df) <= 4 else 4)
        
        for idx, (_, row) in enumerate(summary_df.iterrows()):
            with summary_cols[idx % 4]:
                icon = '💰' if 'revenue' in row['kpi_name'].lower() else (
                    '📈' if 'profit' in row['kpi_name'].lower() else (
                        '👥' if 'customer' in row['kpi_name'].lower() else '📊'
                    )
                )
                
                if row['unit_of_measure'] == 'USD':
                    value_display = f"${row['total_target']:,.0f}"
                else:
                    value_display = f"{row['total_target']:,.0f}"
                
                st.metric(
                    f"{icon} {row['kpi_name']}",
                    value_display,
                    delta=f"{row['center_count']} centers",
                    delta_color="off"
                )
    
    st.divider()
    
    # Show Add Form
    if st.session_state.get('show_add_assignment_form', False):
        _render_add_assignment_form(setup_queries, selected_year)
    
    # Show Edit Form
    if st.session_state.get('edit_assignment_id'):
        _render_edit_assignment_form(setup_queries, st.session_state['edit_assignment_id'])
    
    # =========================================================================
    # ASSIGNMENTS BY KPI CENTER
    # =========================================================================
    query_params = {'year': selected_year}
    
    if selected_center[1]:
        query_params['kpi_center_ids'] = [selected_center[1]]
    elif kpi_center_ids:
        query_params['kpi_center_ids'] = kpi_center_ids
    
    if selected_kpi_type[1]:
        query_params['kpi_type_id'] = selected_kpi_type[1]
    
    assignments_df = setup_queries.get_kpi_assignments(**query_params)
    weight_summary_df = setup_queries.get_assignment_weight_summary(selected_year)
    
    if assignments_df.empty:
        st.info(f"No KPI assignments found for {selected_year}")
        return
    
    # Group by KPI Center
    for center_id in assignments_df['kpi_center_id'].unique():
        center_assignments = assignments_df[assignments_df['kpi_center_id'] == center_id]
        center_name = center_assignments.iloc[0]['kpi_center_name']
        center_type = center_assignments.iloc[0]['kpi_center_type']
        
        # Get weight sum
        weight_row = weight_summary_df[weight_summary_df['kpi_center_id'] == center_id]
        total_weight = int(weight_row['total_weight'].iloc[0]) if not weight_row.empty else 0
        
        weight_status = "✅" if total_weight == 100 else "⚠️"
        
        with st.expander(f"📁 {center_name} ({center_type}) - Weight: {total_weight}% {weight_status}", expanded=True):
            # Table header
            cols = st.columns([3, 2, 1.5, 1, 1, 1])
            with cols[0]:
                st.markdown("**KPI Type**")
            with cols[1]:
                st.markdown("**Annual Target**")
            with cols[2]:
                st.markdown("**Monthly**")
            with cols[3]:
                st.markdown("**Weight**")
            with cols[4]:
                st.markdown("**Actions**")
            
            # Assignment rows
            for _, assignment in center_assignments.iterrows():
                cols = st.columns([3, 2, 1.5, 1, 1, 1])
                
                with cols[0]:
                    st.text(assignment['kpi_name'])
                
                with cols[1]:
                    if assignment['unit_of_measure'] == 'USD':
                        st.text(f"${assignment['annual_target_value_numeric']:,.0f}")
                    else:
                        st.text(f"{assignment['annual_target_value_numeric']:,.0f}")
                
                with cols[2]:
                    if assignment['unit_of_measure'] == 'USD':
                        st.text(f"${assignment['monthly_target_value']:,.0f}")
                    else:
                        st.text(f"{assignment['monthly_target_value']:,.1f}")
                
                with cols[3]:
                    st.text(f"{assignment['weight_numeric']}%")
                
                with cols[4]:
                    if can_edit:
                        col_edit, col_delete = st.columns(2)
                        with col_edit:
                            if st.button("✏️", key=f"edit_assign_{assignment['assignment_id']}"):
                                st.session_state['edit_assignment_id'] = assignment['assignment_id']
                                st.rerun()
                        with col_delete:
                            if st.button("🗑️", key=f"del_assign_{assignment['assignment_id']}"):
                                result = setup_queries.delete_assignment(assignment['assignment_id'])
                                if result['success']:
                                    st.rerun()
            
            # Add KPI button
            if can_edit:
                if st.button(f"➕ Add KPI to {center_name}", key=f"add_kpi_{center_id}"):
                    st.session_state['add_assignment_center_id'] = center_id
                    st.session_state['show_add_assignment_form'] = True
                    st.rerun()


def _render_add_assignment_form(setup_queries: SetupQueries, year: int):
    """Render the Add Assignment form."""
    with st.expander("➕ Add KPI Assignment", expanded=True):
        with st.form("add_assignment_form"):
            st.markdown("### Add KPI Assignment")
            
            col1, col2 = st.columns(2)
            
            with col1:
                # KPI Center
                centers_df = setup_queries.get_kpi_centers_for_dropdown()
                
                # Pre-select if coming from center card
                default_center = st.session_state.get('add_assignment_center_id')
                default_idx = 0
                if default_center and default_center in centers_df['kpi_center_id'].values:
                    default_idx = centers_df[centers_df['kpi_center_id'] == default_center].index[0]
                
                kpi_center_id = st.selectbox(
                    "KPI Center *",
                    options=centers_df['kpi_center_id'].tolist(),
                    index=default_idx,
                    format_func=lambda x: f"{centers_df[centers_df['kpi_center_id'] == x]['kpi_center_name'].iloc[0]} ({centers_df[centers_df['kpi_center_id'] == x]['kpi_type'].iloc[0]})",
                    key="add_assign_center"
                )
            
            with col2:
                # KPI Type
                kpi_types_df = setup_queries.get_kpi_types()
                kpi_type_id = st.selectbox(
                    "KPI Type *",
                    options=kpi_types_df['kpi_type_id'].tolist(),
                    format_func=lambda x: kpi_types_df[kpi_types_df['kpi_type_id'] == x]['kpi_name'].iloc[0],
                    key="add_assign_type"
                )
            
            # Get unit of measure for display
            selected_uom = kpi_types_df[kpi_types_df['kpi_type_id'] == kpi_type_id]['unit_of_measure'].iloc[0]
            
            col3, col4 = st.columns(2)
            
            with col3:
                annual_target = st.number_input(
                    f"Annual Target ({selected_uom}) *",
                    min_value=0,
                    value=0,
                    step=1000 if selected_uom == 'USD' else 1,
                    key="add_assign_target"
                )
                
                if selected_uom == 'USD':
                    st.caption(f"Monthly: ${annual_target / 12:,.0f}")
            
            with col4:
                weight = st.number_input(
                    "Weight % *",
                    min_value=0,
                    max_value=100,
                    value=0,
                    step=5,
                    key="add_assign_weight"
                )
                
                # Validate weight
                validation = setup_queries.validate_assignment_weight(
                    kpi_center_id=kpi_center_id,
                    year=year,
                    new_weight=weight
                )
                
                if validation['valid']:
                    st.success(validation['message'])
                else:
                    st.error(validation['message'])
            
            notes = st.text_input("Notes (optional)", key="add_assign_notes")
            
            col_submit, col_cancel = st.columns(2)
            
            with col_submit:
                if st.form_submit_button("Save Assignment", type="primary"):
                    if annual_target <= 0:
                        st.error("Annual target must be greater than 0")
                    elif weight <= 0:
                        st.error("Weight must be greater than 0")
                    else:
                        result = setup_queries.create_assignment(
                            kpi_center_id=kpi_center_id,
                            kpi_type_id=kpi_type_id,
                            year=year,
                            annual_target_value=annual_target,
                            weight=weight,
                            notes=notes if notes else None
                        )
                        
                        if result['success']:
                            st.success(f"Assignment created (ID: {result['id']})")
                            st.session_state['show_add_assignment_form'] = False
                            st.session_state['add_assignment_center_id'] = None
                            st.rerun()
                        else:
                            st.error(result['message'])
            
            with col_cancel:
                if st.form_submit_button("Cancel"):
                    st.session_state['show_add_assignment_form'] = False
                    st.session_state['add_assignment_center_id'] = None
                    st.rerun()


def _render_edit_assignment_form(setup_queries: SetupQueries, assignment_id: int):
    """Render the Edit Assignment form."""
    # Get current assignment data
    assignments_df = setup_queries.get_kpi_assignments()
    assignment_df = assignments_df[assignments_df['assignment_id'] == assignment_id]
    
    if assignment_df.empty:
        st.error("Assignment not found")
        st.session_state['edit_assignment_id'] = None
        return
    
    assignment = assignment_df.iloc[0]
    
    with st.expander(f"✏️ Edit Assignment #{assignment_id}", expanded=True):
        with st.form("edit_assignment_form"):
            st.markdown(f"**KPI Center:** {assignment['kpi_center_name']}")
            st.markdown(f"**KPI Type:** {assignment['kpi_name']}")
            st.markdown(f"**Year:** {assignment['year']}")
            
            col1, col2 = st.columns(2)
            
            with col1:
                new_target = st.number_input(
                    f"Annual Target ({assignment['unit_of_measure']})",
                    min_value=0,
                    value=int(assignment['annual_target_value_numeric']),
                    step=1000 if assignment['unit_of_measure'] == 'USD' else 1,
                    key="edit_assign_target"
                )
            
            with col2:
                new_weight = st.number_input(
                    "Weight %",
                    min_value=0,
                    max_value=100,
                    value=int(assignment['weight_numeric']),
                    step=5,
                    key="edit_assign_weight"
                )
                
                # Validate weight
                validation = setup_queries.validate_assignment_weight(
                    kpi_center_id=assignment['kpi_center_id'],
                    year=assignment['year'],
                    new_weight=new_weight,
                    exclude_assignment_id=assignment_id
                )
                
                if validation['valid']:
                    st.success(validation['message'])
                else:
                    st.error(validation['message'])
            
            new_notes = st.text_input(
                "Notes",
                value=assignment['notes'] if pd.notna(assignment['notes']) else "",
                key="edit_assign_notes"
            )
            
            col_submit, col_cancel = st.columns(2)
            
            with col_submit:
                if st.form_submit_button("Save Changes", type="primary"):
                    result = setup_queries.update_assignment(
                        assignment_id=assignment_id,
                        annual_target_value=new_target,
                        weight=new_weight,
                        notes=new_notes if new_notes else None
                    )
                    
                    if result['success']:
                        st.success("Assignment updated")
                        st.session_state['edit_assignment_id'] = None
                        st.rerun()
                    else:
                        st.error(result['message'])
            
            with col_cancel:
                if st.form_submit_button("Cancel"):
                    st.session_state['edit_assignment_id'] = None
                    st.rerun()


# =============================================================================
# HIERARCHY SECTION
# =============================================================================

@st.fragment  
def hierarchy_section(
    setup_queries: SetupQueries,
    can_edit: bool = False
):
    """
    Hierarchy sub-tab with tree view.
    """
    # =========================================================================
    # TOOLBAR
    # =========================================================================
    col1, col2, col3, col4 = st.columns([1, 1, 1, 3])
    
    with col1:
        if can_edit:
            if st.button("➕ Add Center", type="primary", key="add_center_btn"):
                st.session_state['show_add_center_form'] = True
    
    with col2:
        if st.button("📂 Expand All", key="expand_all"):
            st.session_state['hierarchy_expanded'] = True
    
    with col3:
        if st.button("📁 Collapse All", key="collapse_all"):
            st.session_state['hierarchy_expanded'] = False
    
    # Show Add Form
    if st.session_state.get('show_add_center_form', False):
        _render_add_center_form(setup_queries)
    
    # Show Edit Form
    if st.session_state.get('edit_center_id'):
        _render_edit_center_form(setup_queries, st.session_state['edit_center_id'])
    
    # Show Detail Panel
    if st.session_state.get('view_center_id'):
        _render_center_detail_panel(setup_queries, st.session_state['view_center_id'])
    
    st.divider()
    
    # =========================================================================
    # TREE VIEW
    # =========================================================================
    hierarchy_df = setup_queries.get_kpi_center_hierarchy(include_stats=True)
    
    if hierarchy_df.empty:
        st.info("No KPI Centers found")
        return
    
    expanded = st.session_state.get('hierarchy_expanded', True)
    
    # Group by KPI Type
    for kpi_type in hierarchy_df['kpi_type'].unique():
        type_df = hierarchy_df[hierarchy_df['kpi_type'] == kpi_type]
        icon = KPI_TYPE_ICONS.get(kpi_type, '📁')
        
        with st.expander(f"{icon} {kpi_type}", expanded=expanded):
            # Build tree structure
            _render_tree_level(
                df=type_df,
                parent_id=None,
                level=0,
                setup_queries=setup_queries,
                can_edit=can_edit
            )


def _render_tree_level(
    df: pd.DataFrame,
    parent_id: int,
    level: int,
    setup_queries: SetupQueries,
    can_edit: bool
):
    """Recursively render tree levels."""
    # Get nodes at this level with this parent
    if parent_id is None:
        level_nodes = df[(df['parent_center_id'].isna()) & (df['level'] == level)]
    else:
        level_nodes = df[df['parent_center_id'] == parent_id]
    
    for _, node in level_nodes.iterrows():
        indent = "│   " * level
        
        # Determine icon based on whether it has children
        has_children = node['children_count'] > 0
        node_icon = "📁" if has_children else "📄"
        
        # Build stats string
        stats = []
        if node.get('assignment_count', 0) > 0:
            stats.append(f"{node['assignment_count']} KPIs")
        if node.get('split_count', 0) > 0:
            stats.append(f"{node['split_count']} splits")
        stats_str = " | ".join(stats) if stats else ""
        
        # Render node
        col1, col2, col3 = st.columns([4, 2, 1])
        
        with col1:
            if has_children:
                label = f"{indent}├── {node_icon} **{node['kpi_center_name']}** ({node['children_count']} children)"
            else:
                label = f"{indent}├── {node_icon} {node['kpi_center_name']}"
            
            # Make clickable
            if st.button(label, key=f"node_{node['kpi_center_id']}", use_container_width=True):
                st.session_state['view_center_id'] = node['kpi_center_id']
                st.rerun()
        
        with col2:
            if stats_str:
                st.caption(stats_str)
        
        with col3:
            if can_edit:
                btn_col1, btn_col2 = st.columns(2)
                with btn_col1:
                    if st.button("✏️", key=f"edit_node_{node['kpi_center_id']}"):
                        st.session_state['edit_center_id'] = node['kpi_center_id']
                        st.rerun()
                with btn_col2:
                    if node['children_count'] == 0:  # Only show delete for leaf nodes
                        if st.button("🗑️", key=f"del_node_{node['kpi_center_id']}"):
                            deps = setup_queries.check_kpi_center_dependencies(node['kpi_center_id'])
                            if deps['can_delete']:
                                result = setup_queries.delete_kpi_center(node['kpi_center_id'])
                                if result['success']:
                                    st.rerun()
                            else:
                                st.error(deps['message'])
        
        # Render children recursively
        if has_children:
            _render_tree_level(
                df=df,
                parent_id=node['kpi_center_id'],
                level=level + 1,
                setup_queries=setup_queries,
                can_edit=can_edit
            )


def _render_add_center_form(setup_queries: SetupQueries):
    """Render the Add KPI Center form."""
    with st.expander("➕ Add KPI Center", expanded=True):
        with st.form("add_center_form"):
            col1, col2 = st.columns(2)
            
            with col1:
                name = st.text_input("Name *", key="add_center_name")
            
            with col2:
                kpi_type = st.selectbox(
                    "Type *",
                    options=KPI_TYPES,
                    key="add_center_type"
                )
            
            description = st.text_input("Description", key="add_center_desc")
            
            # Parent selection - filter by same type
            centers_df = setup_queries.get_kpi_centers_for_dropdown(kpi_type=kpi_type)
            parent_options = [(None, "No Parent (Root)")] + [
                (row['kpi_center_id'], row['kpi_center_name']) 
                for _, row in centers_df.iterrows()
            ]
            
            parent_id = st.selectbox(
                "Parent Center",
                options=[p[0] for p in parent_options],
                format_func=lambda x: next(p[1] for p in parent_options if p[0] == x),
                key="add_center_parent"
            )
            
            col_submit, col_cancel = st.columns(2)
            
            with col_submit:
                if st.form_submit_button("Create Center", type="primary"):
                    if not name:
                        st.error("Name is required")
                    else:
                        result = setup_queries.create_kpi_center(
                            name=name,
                            kpi_type=kpi_type,
                            description=description if description else None,
                            parent_center_id=parent_id
                        )
                        
                        if result['success']:
                            st.success(f"KPI Center created (ID: {result['id']})")
                            st.session_state['show_add_center_form'] = False
                            st.rerun()
                        else:
                            st.error(result['message'])
            
            with col_cancel:
                if st.form_submit_button("Cancel"):
                    st.session_state['show_add_center_form'] = False
                    st.rerun()


def _render_edit_center_form(setup_queries: SetupQueries, center_id: int):
    """Render the Edit KPI Center form."""
    detail = setup_queries.get_kpi_center_detail(center_id)
    
    if not detail:
        st.error("Center not found")
        st.session_state['edit_center_id'] = None
        return
    
    with st.expander(f"✏️ Edit KPI Center: {detail['kpi_center_name']}", expanded=True):
        with st.form("edit_center_form"):
            col1, col2 = st.columns(2)
            
            with col1:
                new_name = st.text_input(
                    "Name",
                    value=detail['kpi_center_name'],
                    key="edit_center_name"
                )
            
            with col2:
                st.text_input(
                    "Type",
                    value=detail['kpi_type'],
                    disabled=True,
                    key="edit_center_type"
                )
            
            new_description = st.text_input(
                "Description",
                value=detail['description'] if detail['description'] else "",
                key="edit_center_desc"
            )
            
            # Parent selection
            centers_df = setup_queries.get_kpi_centers_for_dropdown(
                kpi_type=detail['kpi_type'],
                exclude_ids=[center_id]  # Exclude self
            )
            parent_options = [(0, "No Parent (Root)")] + [
                (row['kpi_center_id'], row['kpi_center_name']) 
                for _, row in centers_df.iterrows()
            ]
            
            current_parent = detail['parent_center_id'] if detail['parent_center_id'] else 0
            
            new_parent_id = st.selectbox(
                "Parent Center",
                options=[p[0] for p in parent_options],
                index=next((i for i, p in enumerate(parent_options) if p[0] == current_parent), 0),
                format_func=lambda x: next(p[1] for p in parent_options if p[0] == x),
                key="edit_center_parent"
            )
            
            col_submit, col_cancel = st.columns(2)
            
            with col_submit:
                if st.form_submit_button("Save Changes", type="primary"):
                    result = setup_queries.update_kpi_center(
                        kpi_center_id=center_id,
                        name=new_name,
                        description=new_description if new_description else None,
                        parent_center_id=new_parent_id if new_parent_id > 0 else 0
                    )
                    
                    if result['success']:
                        st.success("Center updated")
                        st.session_state['edit_center_id'] = None
                        st.rerun()
                    else:
                        st.error(result['message'])
            
            with col_cancel:
                if st.form_submit_button("Cancel"):
                    st.session_state['edit_center_id'] = None
                    st.rerun()


def _render_center_detail_panel(setup_queries: SetupQueries, center_id: int):
    """Render the center detail panel."""
    detail = setup_queries.get_kpi_center_detail(center_id)
    
    if not detail:
        st.session_state['view_center_id'] = None
        return
    
    with st.expander(f"📄 {detail['kpi_center_name']}", expanded=True):
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown(f"**Type:** {detail['kpi_type']}")
            st.markdown(f"**Parent:** {detail.get('parent_name', 'None')}")
            st.markdown(f"**Created:** {detail['created_date']}")
        
        with col2:
            st.markdown(f"**Active Splits:** {detail.get('active_splits', 0)}")
            st.markdown(f"**{date.today().year} Assignments:** {detail.get('current_year_assignments', 0)}")
            st.markdown(f"**Children:** {detail.get('children_count', 0)}")
        
        if detail.get('description'):
            st.markdown(f"**Description:** {detail['description']}")
        
        col_btn1, col_btn2, col_btn3, col_btn4 = st.columns(4)
        
        with col_btn1:
            if st.button("View Splits", key="detail_view_splits"):
                # Navigate to splits tab with filter
                st.session_state['split_center_filter'] = center_id
        
        with col_btn2:
            if st.button("View Assignments", key="detail_view_assign"):
                st.session_state['assignment_center'] = (detail['kpi_center_name'], center_id)
        
        with col_btn3:
            if st.button("View Performance", key="detail_view_perf"):
                # Could navigate to Overview tab
                pass
        
        with col_btn4:
            if st.button("Close", key="close_detail"):
                st.session_state['view_center_id'] = None
                st.rerun()


# =============================================================================
# VALIDATION SECTION
# =============================================================================

@st.fragment
def validation_section(setup_queries: SetupQueries):
    """
    Validation sub-tab with health dashboard.
    """
    current_year = date.today().year
    
    col_header, col_refresh = st.columns([5, 1])
    
    with col_header:
        st.markdown("### 🏥 Configuration Health Check")
    
    with col_refresh:
        if st.button("🔄 Refresh", key="refresh_validation"):
            st.rerun()
    
    # Get all validation issues
    issues = setup_queries.get_all_validation_issues(year=current_year)
    
    # =========================================================================
    # HEALTH SCORE CARDS
    # =========================================================================
    col1, col2, col3 = st.columns(3)
    
    with col1:
        split_summary = issues['summary'].get('split', {})
        split_issues = split_summary.get('over_100_count', 0) + split_summary.get('incomplete_count', 0)
        
        if split_issues == 0:
            st.success("### ✅ Split Rules\n\nNo issues found")
        else:
            st.warning(f"### ⚠️ Split Rules\n\n{split_issues} issues")
    
    with col2:
        assign_summary = issues['summary'].get('assignment', {})
        assign_issues = assign_summary.get('weight_issues', 0) + assign_summary.get('no_assignment', 0)
        
        if assign_issues == 0:
            st.success("### ✅ Assignments\n\nNo issues found")
        else:
            st.warning(f"### ⚠️ Assignments\n\n{assign_issues} issues")
    
    with col3:
        hierarchy_summary = issues['summary'].get('hierarchy', {})
        hierarchy_issues = hierarchy_summary.get('issues', 0)
        
        if hierarchy_issues == 0:
            st.success(f"### ✅ Hierarchy\n\n{hierarchy_summary.get('total_centers', 0)} centers")
        else:
            st.warning(f"### ⚠️ Hierarchy\n\n{hierarchy_issues} issues")
    
    st.divider()
    
    # =========================================================================
    # ISSUE TABLES
    # =========================================================================
    
    # Split Rule Issues
    if issues['split_issues']:
        st.markdown("### 📋 Split Rule Issues")
        
        for issue in issues['split_issues']:
            severity_icon = {
                'critical': '🔴',
                'warning': '⚠️',
                'info': 'ℹ️'
            }.get(issue['severity'], '❓')
            
            col_issue, col_count, col_action = st.columns([4, 1, 1])
            
            with col_issue:
                st.markdown(f"{severity_icon} **{issue['type'].replace('_', ' ').title()}**: {issue['message']}")
            
            with col_count:
                st.metric("Count", issue['count'])
            
            with col_action:
                if issue['type'] == 'over_100_split':
                    if st.button("View & Fix", key=f"fix_{issue['type']}"):
                        st.session_state['split_status_filter'] = 'over_100_split'
                elif issue['type'] == 'incomplete_split':
                    if st.button("View & Fix", key=f"fix_{issue['type']}"):
                        st.session_state['split_status_filter'] = 'incomplete_split'
                elif issue['type'] == 'pending_approval':
                    if st.button("Review", key=f"fix_{issue['type']}"):
                        st.session_state['split_approval_filter'] = 'pending'
                elif issue['type'] == 'expiring_soon':
                    if st.button("Extend", key=f"fix_{issue['type']}"):
                        st.session_state['split_expiring'] = True
    
    # Assignment Issues
    if issues['assignment_issues']:
        st.markdown("### 🎯 Assignment Issues")
        
        for issue in issues['assignment_issues']:
            severity_icon = {
                'critical': '🔴',
                'warning': '⚠️',
                'info': 'ℹ️'
            }.get(issue['severity'], '❓')
            
            col_issue, col_count, col_action = st.columns([4, 1, 1])
            
            with col_issue:
                st.markdown(f"{severity_icon} **{issue['type'].replace('_', ' ').title()}**: {issue['message']}")
            
            with col_count:
                st.metric("Count", issue['count'])
            
            with col_action:
                if st.button("View & Fix", key=f"fix_assign_{issue['type']}"):
                    # Navigate to assignments tab
                    pass
            
            # Show details if available
            if issue.get('details'):
                with st.expander("View Details"):
                    details_df = pd.DataFrame(issue['details'])
                    st.dataframe(details_df, hide_index=True, use_container_width=True)
    
    # No issues message
    if not issues['split_issues'] and not issues['assignment_issues']:
        st.success("🎉 No configuration issues found! All systems healthy.")
    
    st.divider()
    
    # =========================================================================
    # QUICK STATS
    # =========================================================================
    st.markdown("### 📊 Quick Statistics")
    
    col_stat1, col_stat2, col_stat3, col_stat4 = st.columns(4)
    
    split_stats = issues['summary'].get('split', {})
    
    with col_stat1:
        st.metric("Total Split Rules", f"{split_stats.get('total_rules', 0):,}")
    
    with col_stat2:
        ok_pct = (split_stats.get('ok_count', 0) / split_stats.get('total_rules', 1)) * 100
        st.metric("OK Rules", f"{ok_pct:.1f}%")
    
    with col_stat3:
        st.metric("Pending Approval", f"{split_stats.get('pending_count', 0):,}")
    
    with col_stat4:
        st.metric("Expiring Soon", f"{split_stats.get('expiring_soon_count', 0):,}")