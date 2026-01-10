# utils/kpi_center_performance/setup/renewal/fragments.py
"""
UI Fragments for KPI Center Split Rules Renewal (v2.0)

v2.0 Changes:
- Comprehensive filters: Expiry status, Brand, Customer/Product search
- Include EXPIRED rules (not just expiring)
- Better @st.fragment handling to avoid page reruns
- Cleaner dialog flow

Provides:
1. Trigger button to open renewal dialog
2. Renewal dialog with filters, selection, and execution
3. Proper fragment handling
"""

import streamlit as st
import pandas as pd
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

from .queries import RenewalQueries, EXPIRY_STATUS


# =============================================================================
# CONSTANTS
# =============================================================================

DEFAULT_THRESHOLD_DAYS = 90

THRESHOLD_OPTIONS = {
    30: '30 days',
    60: '60 days',
    90: '90 days (Default)',
    180: '180 days',
    365: '1 year'
}

EXPIRY_STATUS_OPTIONS = {
    'all': '📋 All',
    'expired': '⚫ Expired',
    'critical': '🔴 Critical (<7d)',
    'warning': '🟠 Warning (<30d)',
    'normal': '🟢 Normal'
}

RENEWAL_STRATEGIES = {
    'extend': {
        'name': 'Extend Period',
        'description': 'Update the end date of existing rules',
        'icon': '📅'
    },
    'copy': {
        'name': 'Copy to New Period',
        'description': 'Create new rules, expire originals',
        'icon': '📋'
    }
}

KPI_TYPE_ICONS = {
    'TERRITORY': '🌍',
    'VERTICAL': '📊',
    'BRAND': '🏷️',
    'INTERNAL': '🏢'
}


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def format_currency(value: float) -> str:
    """Format value as USD currency."""
    if pd.isna(value) or value == 0:
        return "$0"
    if value >= 1000000:
        return f"${value/1000000:.1f}M"
    if value >= 1000:
        return f"${value/1000:.1f}K"
    return f"${value:,.0f}"


def get_expiry_badge(status: str, days: int) -> str:
    """Get expiry badge with icon."""
    if status == 'expired':
        return f"⚫ {abs(days)}d ago"
    elif status == 'critical':
        return f"🔴 {days}d"
    elif status == 'warning':
        return f"🟠 {days}d"
    else:
        return f"🟢 {days}d"


def get_default_new_valid_to() -> date:
    """Get default new valid_to date (end of current/next year)."""
    today = date.today()
    if today.month >= 10:
        return date(today.year + 1, 12, 31)
    else:
        return date(today.year, 12, 31)


def get_default_expired_from() -> date:
    """Get default expired_from date (first day of previous year)."""
    today = date.today()
    return date(today.year - 1, 1, 1)


# =============================================================================
# RENEWAL DIALOG (v2.0)
# =============================================================================

@st.dialog("🔄 Renew Split Rules", width="large")
def _renewal_dialog_impl(
    user_id: int,
    can_approve: bool,
    initial_threshold: int = DEFAULT_THRESHOLD_DAYS
):
    """
    Renewal dialog with comprehensive filters.
    
    v2.0: Include expired rules, enhanced filters.
    """
    renewal_queries = RenewalQueries(user_id=user_id)
    
    # =========================================================================
    # FILTERS SECTION
    # =========================================================================
    with st.expander("🔍 Filters", expanded=True):
        
        # Row 1: Expiry filters
        st.markdown("##### 📅 Expiry Filters")
        exp_col1, exp_col2, exp_col3, exp_col4, exp_col5 = st.columns([1.2, 1, 1, 1, 1])
        
        with exp_col1:
            threshold_days = st.selectbox(
                "Look ahead",
                options=list(THRESHOLD_OPTIONS.keys()),
                index=2,  # 90 days default
                format_func=lambda x: THRESHOLD_OPTIONS[x],
                key="renewal_threshold"
            )
        
        with exp_col2:
            include_expired = st.checkbox(
                "Include expired",
                value=True,
                key="renewal_include_expired",
                help="Show rules that have already expired"
            )
        
        with exp_col3:
            # Date picker for expired_from - only enabled when include_expired is checked
            expired_from_date = st.date_input(
                "Expired from",
                value=get_default_expired_from(),
                max_value=date.today(),
                disabled=not include_expired,
                key="renewal_expired_from",
                help="Include rules expired since this date"
            )
        
        with exp_col4:
            require_sales = st.checkbox(
                "With sales activity",
                value=True,
                key="renewal_require_sales",
                help="Only show rules with sales activity"
            )
        
        with exp_col5:
            # Date picker for sales_from - only enabled when require_sales is checked
            sales_from_date = st.date_input(
                "Sales from",
                value=get_default_expired_from(),  # Same default: first day of previous year
                max_value=date.today(),
                disabled=not require_sales,
                key="renewal_sales_from",
                help="Include rules with sales since this date"
            )
        
        st.divider()
        
        # Row 2: Entity filters
        st.markdown("##### 🏢 Entity Filters")
        ent_col1, ent_col2, ent_col3 = st.columns(3)
        
        with ent_col1:
            kpi_type_filter = st.selectbox(
                "KPI Type",
                options=['All'] + list(KPI_TYPE_ICONS.keys()),
                format_func=lambda x: f"{KPI_TYPE_ICONS.get(x, '📁')} {x}" if x != 'All' else '📁 All Types',
                key="renewal_kpi_type"
            )
        
        with ent_col2:
            # Get brands with expiring rules
            brands_df = renewal_queries.get_brands_with_expiring_rules(
                threshold_days=threshold_days,
                include_expired=include_expired,
                expired_from_date=expired_from_date if include_expired else None
            )
            brand_options = brands_df['brand_id'].tolist() if not brands_df.empty else []
            
            brand_filter = st.multiselect(
                "Brand",
                options=brand_options,
                format_func=lambda x: brands_df[brands_df['brand_id'] == x]['brand_name'].iloc[0] if not brands_df.empty else str(x),
                placeholder="All Brands",
                key="renewal_brand_filter"
            )
        
        with ent_col3:
            min_sales = st.number_input(
                "Min sales",
                min_value=0,
                value=0,
                step=1000,
                format="%d",
                key="renewal_min_sales",
                help="Minimum total sales in selected period"
            )
        
        # Row 3: Search
        search_col1, search_col2 = st.columns(2)
        
        with search_col1:
            customer_search = st.text_input(
                "🔍 Search Customer",
                placeholder="Name or code...",
                key="renewal_customer_search"
            )
        
        with search_col2:
            product_search = st.text_input(
                "🔍 Search Product",
                placeholder="Name or PT code...",
                key="renewal_product_search"
            )
    
    # =========================================================================
    # FETCH DATA
    # =========================================================================
    suggestions_df = renewal_queries.get_renewal_suggestions(
        threshold_days=threshold_days,
        include_expired=include_expired,
        expired_from_date=expired_from_date if include_expired else None,
        kpi_type=kpi_type_filter if kpi_type_filter != 'All' else None,
        brand_ids=brand_filter if brand_filter else None,
        customer_search=customer_search if customer_search else None,
        product_search=product_search if product_search else None,
        min_sales_amount=min_sales,
        require_sales_activity=require_sales,
        sales_from_date=sales_from_date if require_sales else None
    )
    
    if suggestions_df.empty:
        st.info("✅ No rules found matching the filters.")
        if st.button("Close", key="renewal_close_empty", use_container_width=True):
            st.rerun()
        return
    
    # =========================================================================
    # SUMMARY METRICS
    # =========================================================================
    stats = renewal_queries.get_renewal_summary_stats(
        threshold_days=threshold_days,
        include_expired=include_expired,
        expired_from_date=expired_from_date if include_expired else None,
        sales_from_date=sales_from_date if require_sales else None,
        min_sales_amount=min_sales,
        require_sales_activity=require_sales
    )
    
    metric_cols = st.columns(6)
    
    with metric_cols[0]:
        st.metric("Total", f"{stats['total_count']}")
    
    with metric_cols[1]:
        st.metric("⚫ Expired", f"{stats['expired_count']}")
    
    with metric_cols[2]:
        st.metric("🔴 Critical", f"{stats['critical_count']}")
    
    with metric_cols[3]:
        st.metric("🟠 Warning", f"{stats['warning_count']}")
    
    with metric_cols[4]:
        st.metric("🟢 Normal", f"{stats['normal_count']}")
    
    with metric_cols[5]:
        st.metric("💰 Sales", format_currency(stats['total_sales_at_risk']))
    
    st.divider()
    
    # =========================================================================
    # SELECTION TABLE
    # =========================================================================
    st.markdown(f"### Select Rules ({len(suggestions_df)} found)")
    
    # Initialize selection
    if 'renewal_selected_ids' not in st.session_state:
        # Default: select expired and critical
        default_selected = suggestions_df[
            suggestions_df['expiry_status'].isin(['expired', 'critical'])
        ]['kpi_center_split_id'].tolist()
        st.session_state['renewal_selected_ids'] = default_selected
    
    # Quick selection buttons
    sel_col1, sel_col2, sel_col3, sel_col4 = st.columns(4)
    
    with sel_col1:
        if st.button("☑️ All", key="renewal_select_all", use_container_width=True):
            st.session_state['renewal_selected_ids'] = suggestions_df['kpi_center_split_id'].tolist()
            st.rerun()
    
    with sel_col2:
        if st.button("☐ None", key="renewal_deselect_all", use_container_width=True):
            st.session_state['renewal_selected_ids'] = []
            st.rerun()
    
    with sel_col3:
        if st.button("⚫🔴 Urgent", key="renewal_select_urgent", use_container_width=True):
            urgent = suggestions_df[
                suggestions_df['expiry_status'].isin(['expired', 'critical'])
            ]['kpi_center_split_id'].tolist()
            st.session_state['renewal_selected_ids'] = urgent
            st.rerun()
    
    with sel_col4:
        selected_count = len(st.session_state.get('renewal_selected_ids', []))
        st.metric("Selected", selected_count, label_visibility="collapsed")
    
    # Prepare display data
    display_df = suggestions_df.copy()
    
    display_df['Select'] = display_df['kpi_center_split_id'].isin(
        st.session_state.get('renewal_selected_ids', [])
    )
    
    display_df['Status'] = display_df.apply(
        lambda r: get_expiry_badge(r['expiry_status'], r['days_until_expiry']),
        axis=1
    )
    
    display_df['Type'] = display_df['kpi_type'].apply(
        lambda x: f"{KPI_TYPE_ICONS.get(x, '📁')} {x}" if pd.notna(x) else ''
    )
    
    display_df['Sales'] = display_df['total_sales'].apply(format_currency)
    display_df['GP'] = display_df['total_gp'].apply(format_currency)
    display_df['Split'] = display_df['split_percentage'].apply(lambda x: f"{x:.0f}%")
    display_df['Expires'] = pd.to_datetime(display_df['effective_to']).dt.strftime('%Y-%m-%d')
    
    # Data editor for selection
    edited_df = st.data_editor(
        display_df[[
            'Select', 'kpi_center_split_id', 'Status', 'Type', 'kpi_center_name',
            'customer_display', 'product_display', 'brand', 'Split', 'Expires', 'Sales', 'GP'
        ]],
        column_config={
            'Select': st.column_config.CheckboxColumn('☑️', width='small'),
            'kpi_center_split_id': st.column_config.NumberColumn('ID', width='small'),
            'Status': st.column_config.TextColumn('Status', width='small'),
            'Type': st.column_config.TextColumn('Type', width='small'),
            'kpi_center_name': st.column_config.TextColumn('Center', width='medium'),
            'customer_display': st.column_config.TextColumn('Customer', width='medium'),
            'product_display': st.column_config.TextColumn('Product', width='medium'),
            'brand': st.column_config.TextColumn('Brand', width='small'),
            'Split': st.column_config.TextColumn('Split', width='small'),
            'Expires': st.column_config.TextColumn('Expires', width='small'),
            'Sales': st.column_config.TextColumn('Sales', width='small'),
            'GP': st.column_config.TextColumn('GP', width='small'),
        },
        hide_index=True,
        use_container_width=True,
        height=300,
        key="renewal_data_editor"
    )
    
    # Update selection from editor
    if edited_df is not None:
        selected_ids = edited_df[edited_df['Select'] == True]['kpi_center_split_id'].tolist()
        st.session_state['renewal_selected_ids'] = selected_ids
    
    st.divider()
    
    # =========================================================================
    # RENEWAL SETTINGS
    # =========================================================================
    st.markdown("### Renewal Settings")
    
    settings_col1, settings_col2 = st.columns(2)
    
    with settings_col1:
        strategy = st.radio(
            "Strategy",
            options=list(RENEWAL_STRATEGIES.keys()),
            format_func=lambda x: f"{RENEWAL_STRATEGIES[x]['icon']} {RENEWAL_STRATEGIES[x]['name']}",
            horizontal=True,
            key="renewal_strategy"
        )
        st.caption(RENEWAL_STRATEGIES[strategy]['description'])
    
    with settings_col2:
        if strategy == 'extend':
            new_valid_to = st.date_input(
                "New End Date",
                value=get_default_new_valid_to(),
                min_value=date.today(),
                key="renewal_new_valid_to"
            )
            new_valid_from = None
        else:
            date_col1, date_col2 = st.columns(2)
            with date_col1:
                new_valid_from = st.date_input(
                    "New Start",
                    value=date.today(),
                    min_value=date.today() - timedelta(days=365),
                    key="renewal_new_valid_from"
                )
            with date_col2:
                new_valid_to = st.date_input(
                    "New End",
                    value=get_default_new_valid_to(),
                    key="renewal_new_valid_to_copy"
                )
    
    # Auto-approve option
    if can_approve:
        auto_approve = st.checkbox(
            "✅ Auto-approve renewed rules",
            value=True,
            key="renewal_auto_approve"
        )
    else:
        auto_approve = False
        st.caption("⚠️ Renewed rules will require approval")
    
    st.divider()
    
    # =========================================================================
    # ACTION BUTTONS
    # =========================================================================
    selected_ids = st.session_state.get('renewal_selected_ids', [])
    
    action_col1, action_col2 = st.columns([3, 1])
    
    with action_col1:
        if st.button(
            f"🔄 Renew {len(selected_ids)} Rules",
            type="primary",
            disabled=len(selected_ids) == 0,
            use_container_width=True,
            key="renewal_execute"
        ):
            # Execute renewal
            if strategy == 'extend':
                result = renewal_queries.renew_rules_extend(
                    rule_ids=selected_ids,
                    new_valid_to=new_valid_to,
                    auto_approve=auto_approve
                )
            else:
                result = renewal_queries.renew_rules_copy(
                    rule_ids=selected_ids,
                    new_valid_from=new_valid_from,
                    new_valid_to=new_valid_to,
                    auto_approve=auto_approve
                )
            
            if result['success']:
                st.success(f"✅ {result['message']}")
                st.session_state['renewal_selected_ids'] = []
                st.session_state['renewal_completed'] = True
                st.rerun()
            else:
                st.error(f"❌ {result['message']}")
    
    with action_col2:
        if st.button("❌ Close", use_container_width=True, key="renewal_cancel"):
            st.session_state['renewal_selected_ids'] = []
            st.rerun()


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

@st.fragment
def renewal_section(
    user_id: int = None,
    can_approve: bool = False,
    threshold_days: int = DEFAULT_THRESHOLD_DAYS
):
    """
    Renewal button that opens dialog.
    
    Uses @st.fragment to avoid page rerun when button is clicked.
    """
    # Show success toast if just completed
    if st.session_state.get('renewal_completed', False):
        st.toast("✅ Rules renewed successfully!", icon="🎉")
        st.session_state['renewal_completed'] = False
    
    # Simple button - opens dialog directly
    if st.button(
        "🔄 Renew Expiring",
        help="Open renewal dialog to manage expiring/expired split rules",
        key="renewal_trigger"
    ):
        _renewal_dialog_impl(
            user_id=user_id,
            can_approve=can_approve,
            initial_threshold=threshold_days
        )