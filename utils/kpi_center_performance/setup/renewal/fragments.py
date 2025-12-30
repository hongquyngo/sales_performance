# utils/kpi_center_performance/setup/renewal/fragments.py
"""
UI Fragments for KPI Center Split Rules Renewal

Provides:
1. Trigger button to open renewal dialog
2. Renewal dialog with suggestions, selection, and execution
3. Proper fragment handling to avoid full page reruns

Usage in split_rules_section:
    from .renewal import renewal_section
    
    # In toolbar area - single component handles both button and dialog
    renewal_section(
        user_id=setup_queries.user_id,
        can_approve=can_approve,
        threshold_days=30
    )
"""

import streamlit as st
import pandas as pd
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

from .queries import RenewalQueries


# =============================================================================
# CONSTANTS
# =============================================================================

DEFAULT_THRESHOLD_DAYS = 30

THRESHOLD_OPTIONS = {
    7: '7 days (Urgent)',
    30: '30 days (Default)',
    60: '60 days (Proactive)',
    90: '90 days (Planning)'
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


def get_urgency_badge(urgency: str, days: int) -> str:
    """Get urgency badge with icon."""
    if urgency == 'critical':
        return f"🔴 {days}d"
    elif urgency == 'warning':
        return f"🟠 {days}d"
    else:
        return f"🟢 {days}d"


def get_default_new_valid_to() -> date:
    """Get default new valid_to date (end of next year)."""
    today = date.today()
    # If we're in Q4, extend to end of next year
    # Otherwise, extend to end of current year
    if today.month >= 10:
        return date(today.year + 1, 12, 31)
    else:
        return date(today.year, 12, 31)


# =============================================================================
# RENEWAL DIALOG - Using @st.dialog decorator
# =============================================================================

@st.dialog("🔄 Renew Expiring Split Rules", width="large")
def _renewal_dialog_impl(
    user_id: int,
    can_approve: bool,
    initial_threshold: int = DEFAULT_THRESHOLD_DAYS
):
    """
    Internal dialog implementation.
    Called directly from button click - no session state needed.
    """
    # Initialize
    renewal_queries = RenewalQueries(user_id=user_id)
    
    # -------------------------------------------------------------------------
    # CONFIGURATION BAR
    # -------------------------------------------------------------------------
    config_col1, config_col2, config_col3 = st.columns([2, 2, 2])
    
    with config_col1:
        threshold_days = st.selectbox(
            "Expiring within",
            options=list(THRESHOLD_OPTIONS.keys()),
            index=list(THRESHOLD_OPTIONS.keys()).index(initial_threshold) if initial_threshold in THRESHOLD_OPTIONS else 1,
            format_func=lambda x: THRESHOLD_OPTIONS[x],
            key="renewal_threshold_select"
        )
    
    with config_col2:
        min_sales = st.number_input(
            "Min sales (12m)",
            min_value=0,
            value=0,
            step=1000,
            format="%d",
            help="Minimum sales amount in last 12 months",
            key="renewal_min_sales"
        )
    
    with config_col3:
        kpi_type_filter = st.selectbox(
            "KPI Type",
            options=['All'] + list(KPI_TYPE_ICONS.keys()),
            format_func=lambda x: f"{KPI_TYPE_ICONS.get(x, '📁')} {x}" if x != 'All' else 'All Types',
            key="renewal_kpi_type_filter"
        )
    
    st.divider()
    
    # -------------------------------------------------------------------------
    # FETCH SUGGESTIONS
    # -------------------------------------------------------------------------
    suggestions_df = renewal_queries.get_renewal_suggestions(
        threshold_days=threshold_days,
        min_sales_amount=min_sales,
        kpi_type=kpi_type_filter if kpi_type_filter != 'All' else None
    )
    
    if suggestions_df.empty:
        st.info(
            f"✅ No rules expiring within {threshold_days} days with sales activity.\n\n"
            "All your active split rules are good!"
        )
        
        if st.button("Close", key="renewal_close_empty", use_container_width=True):
            st.rerun()
        return
    
    # -------------------------------------------------------------------------
    # SUMMARY METRICS
    # -------------------------------------------------------------------------
    stats = renewal_queries.get_renewal_summary_stats(threshold_days)
    
    metric_cols = st.columns(5)
    
    with metric_cols[0]:
        st.metric("Total", f"{stats['total_count']}")
    
    with metric_cols[1]:
        st.metric("🔴 Critical", f"{stats['critical_count']}", 
                  help="Expiring within 7 days")
    
    with metric_cols[2]:
        st.metric("🟠 Warning", f"{stats['warning_count']}",
                  help="Expiring within 30 days")
    
    with metric_cols[3]:
        st.metric("🟢 Normal", f"{stats['normal_count']}",
                  help="Expiring within threshold")
    
    with metric_cols[4]:
        st.metric("💰 Sales at Risk", format_currency(stats['total_sales_at_risk']),
                  help="Total 12-month sales for expiring rules")
    
    st.divider()
    
    # -------------------------------------------------------------------------
    # SELECTION TABLE
    # -------------------------------------------------------------------------
    st.markdown("### Select Rules to Renew")
    
    # Initialize selection in session state (for this dialog session)
    if 'renewal_selected_ids' not in st.session_state:
        # Default: select all critical and warning
        default_selected = suggestions_df[
            suggestions_df['expiry_urgency'].isin(['critical', 'warning'])
        ]['kpi_center_split_id'].tolist()
        st.session_state['renewal_selected_ids'] = default_selected
    
    # Select all / Deselect all buttons
    sel_col1, sel_col2, sel_col3 = st.columns([1, 1, 4])
    
    with sel_col1:
        if st.button("☑️ Select All", key="renewal_select_all", use_container_width=True):
            st.session_state['renewal_selected_ids'] = suggestions_df['kpi_center_split_id'].tolist()
            st.rerun()
    
    with sel_col2:
        if st.button("☐ Deselect All", key="renewal_deselect_all", use_container_width=True):
            st.session_state['renewal_selected_ids'] = []
            st.rerun()
    
    with sel_col3:
        selected_count = len(st.session_state.get('renewal_selected_ids', []))
        st.caption(f"Selected: {selected_count} / {len(suggestions_df)} rules")
    
    # Prepare display DataFrame
    display_df = suggestions_df.copy()
    
    # Add selection column
    display_df['Select'] = display_df['kpi_center_split_id'].isin(
        st.session_state.get('renewal_selected_ids', [])
    )
    
    # Format columns for display
    display_df['Urgency'] = display_df.apply(
        lambda r: get_urgency_badge(r['expiry_urgency'], r['days_until_expiry']),
        axis=1
    )
    
    display_df['Type'] = display_df['kpi_type'].apply(
        lambda x: f"{KPI_TYPE_ICONS.get(x, '📁')} {x}" if pd.notna(x) else ''
    )
    
    display_df['Sales 12m'] = display_df['total_sales_12m'].apply(format_currency)
    display_df['GP 12m'] = display_df['total_gp_12m'].apply(format_currency)
    display_df['Split'] = display_df['split_percentage'].apply(lambda x: f"{x:.0f}%")
    display_df['Expires'] = pd.to_datetime(display_df['effective_to']).dt.strftime('%Y-%m-%d')
    
    # Use data_editor for selection
    edited_df = st.data_editor(
        display_df[[
            'Select', 'kpi_center_split_id', 'Urgency', 'Type', 'kpi_center_name',
            'customer_display', 'product_display', 'Split', 'Expires', 'Sales 12m', 'GP 12m'
        ]],
        column_config={
            'Select': st.column_config.CheckboxColumn('☑️', width='small'),
            'kpi_center_split_id': st.column_config.NumberColumn('ID', width='small'),
            'Urgency': st.column_config.TextColumn('⏰', width='small'),
            'Type': st.column_config.TextColumn('Type', width='small'),
            'kpi_center_name': st.column_config.TextColumn('KPI Center', width='medium'),
            'customer_display': st.column_config.TextColumn('Customer', width='medium'),
            'product_display': st.column_config.TextColumn('Product', width='medium'),
            'Split': st.column_config.TextColumn('Split', width='small'),
            'Expires': st.column_config.TextColumn('Expires', width='small'),
            'Sales 12m': st.column_config.TextColumn('Sales 12m', width='small'),
            'GP 12m': st.column_config.TextColumn('GP 12m', width='small'),
        },
        hide_index=True,
        use_container_width=True,
        key="renewal_data_editor"
    )
    
    # Update selection from data_editor
    if edited_df is not None:
        selected_ids = edited_df[edited_df['Select'] == True]['kpi_center_split_id'].tolist()
        st.session_state['renewal_selected_ids'] = selected_ids
    
    st.divider()
    
    # -------------------------------------------------------------------------
    # RENEWAL CONFIGURATION
    # -------------------------------------------------------------------------
    st.markdown("### Renewal Settings")
    
    settings_col1, settings_col2 = st.columns(2)
    
    with settings_col1:
        strategy = st.radio(
            "Strategy",
            options=list(RENEWAL_STRATEGIES.keys()),
            format_func=lambda x: f"{RENEWAL_STRATEGIES[x]['icon']} {RENEWAL_STRATEGIES[x]['name']}",
            horizontal=True,
            key="renewal_strategy",
            help="**Extend**: Update end date of existing rules\n\n**Copy**: Create new rules with new period"
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
            # For copy strategy, need both dates
            date_col1, date_col2 = st.columns(2)
            with date_col1:
                new_valid_from = st.date_input(
                    "New Start Date",
                    value=date.today(),
                    min_value=date.today(),
                    key="renewal_new_valid_from"
                )
            with date_col2:
                new_valid_to = st.date_input(
                    "New End Date",
                    value=get_default_new_valid_to(),
                    min_value=date.today(),
                    key="renewal_new_valid_to_copy"
                )
    
    # Auto-approve option (only if user has permission)
    if can_approve:
        auto_approve = st.checkbox(
            "✅ Auto-approve renewed rules",
            value=True,
            key="renewal_auto_approve",
            help="If checked, renewed rules will be automatically approved"
        )
    else:
        auto_approve = False
        st.caption("⚠️ Renewed rules will require approval")
    
    st.divider()
    
    # -------------------------------------------------------------------------
    # ACTION BUTTONS
    # -------------------------------------------------------------------------
    selected_ids = st.session_state.get('renewal_selected_ids', [])
    
    action_col1, action_col2 = st.columns([3, 1])
    
    with action_col1:
        # Execute renewal button
        if st.button(
            f"🔄 Renew {len(selected_ids)} Rules",
            type="primary",
            disabled=len(selected_ids) == 0,
            use_container_width=True,
            key="renewal_execute_btn"
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
                # Clear selection
                st.session_state['renewal_selected_ids'] = []
                st.session_state['renewal_just_completed'] = True
                st.rerun()
            else:
                st.error(f"❌ Error: {result['message']}")
    
    with action_col2:
        # Cancel button - just close dialog
        if st.button(
            "❌ Cancel",
            use_container_width=True,
            key="renewal_cancel_btn"
        ):
            st.session_state['renewal_selected_ids'] = []
            st.rerun()


# =============================================================================
# MAIN ENTRY POINT - Combined button and dialog in one fragment
# =============================================================================

@st.fragment
def renewal_section(
    user_id: int = None,
    can_approve: bool = False,
    threshold_days: int = DEFAULT_THRESHOLD_DAYS
):
    """
    Combined renewal trigger button and dialog handler.
    
    This is a fragment that:
    1. Shows the renewal button with badge
    2. When clicked, opens the dialog directly (no page rerun)
    
    Args:
        user_id: Current user ID for queries and audit
        can_approve: Whether user can auto-approve renewals
        threshold_days: Days threshold for expiring rules
    """
    # Initialize renewal queries
    renewal_queries = RenewalQueries(user_id=user_id)
    
    # Get summary stats for button badge
    stats = renewal_queries.get_renewal_summary_stats(threshold_days)
    total_count = stats['total_count']
    critical_count = stats['critical_count']
    
    # Build button label with badge
    if total_count > 0:
        if critical_count > 0:
            label = f"🔄 Renew Expiring ({total_count}) 🔴"
        else:
            label = f"🔄 Renew Expiring ({total_count})"
        button_type = "primary" if critical_count > 0 else "secondary"
    else:
        label = "🔄 Renew Expiring"
        button_type = "secondary"
    
    # Show success toast if just completed renewal
    if st.session_state.get('renewal_just_completed', False):
        st.toast("✅ Rules renewed successfully!", icon="🎉")
        st.session_state['renewal_just_completed'] = False
    
    # Render button - when clicked, directly open dialog (no st.rerun needed)
    if st.button(
        label,
        type=button_type,
        help=f"{total_count} rules expiring within {threshold_days} days with recent sales",
        key="renewal_trigger_btn"
    ):
        # Open dialog directly - this is the key fix!
        # No session state manipulation, no st.rerun()
        _renewal_dialog_impl(
            user_id=user_id,
            can_approve=can_approve,
            initial_threshold=threshold_days
        )