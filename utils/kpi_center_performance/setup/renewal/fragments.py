# utils/kpi_center_performance/setup/renewal/fragments.py
"""
UI Fragments for KPI Center Split Rules Renewal

Provides:
1. Trigger button to open renewal dialog
2. Renewal dialog with suggestions, selection, and execution
3. Proper fragment handling to avoid full page reruns

Usage in split_rules_section:
    from .renewal import renewal_trigger_button, renewal_dialog_fragment
    
    # In toolbar area
    renewal_trigger_button(setup_queries, can_edit)
    
    # Dialog renders automatically when triggered
    if st.session_state.get('show_renewal_dialog'):
        renewal_dialog_fragment(setup_queries, can_approve)
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
# TRIGGER BUTTON - Call this from split_rules_section
# =============================================================================

@st.fragment
def renewal_trigger_button(
    user_id: int = None,
    threshold_days: int = DEFAULT_THRESHOLD_DAYS
):
    """
    Render the renewal trigger button with badge showing count.
    
    This is a fragment to avoid rerunning the whole page when
    checking for renewal suggestions.
    
    Args:
        user_id: Current user ID for queries
        threshold_days: Days threshold for expiring rules
    """
    # Initialize renewal queries
    renewal_queries = RenewalQueries(user_id=user_id)
    
    # Get summary stats
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
    
    # Render button
    if st.button(
        label,
        type=button_type,
        help=f"{total_count} rules expiring within {threshold_days} days with recent sales",
        key="renewal_trigger_btn"
    ):
        st.session_state['show_renewal_dialog'] = True
        st.session_state['renewal_threshold_days'] = threshold_days
        st.rerun()


# =============================================================================
# MAIN RENEWAL DIALOG
# =============================================================================

@st.dialog("🔄 Renew Expiring Split Rules", width="large")
def renewal_dialog_fragment(
    user_id: int = None,
    can_approve: bool = False
):
    """
    Main renewal dialog with suggestions, selection, and execution.
    
    Uses @st.dialog decorator for popup behavior.
    
    Args:
        user_id: Current user ID for queries and audit
        can_approve: Whether user can auto-approve renewals
    """
    # Initialize
    renewal_queries = RenewalQueries(user_id=user_id)
    
    # Get threshold from session or use default
    threshold_days = st.session_state.get('renewal_threshold_days', DEFAULT_THRESHOLD_DAYS)
    
    # -------------------------------------------------------------------------
    # CONFIGURATION BAR
    # -------------------------------------------------------------------------
    config_col1, config_col2, config_col3 = st.columns([2, 2, 2])
    
    with config_col1:
        threshold_days = st.selectbox(
            "Expiring within",
            options=list(THRESHOLD_OPTIONS.keys()),
            index=list(THRESHOLD_OPTIONS.keys()).index(threshold_days) if threshold_days in THRESHOLD_OPTIONS else 1,
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
        
        if st.button("Close", key="renewal_close_empty"):
            st.session_state['show_renewal_dialog'] = False
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
    
    # Initialize selection in session state
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
            st.rerun(scope="fragment")
    
    with sel_col2:
        if st.button("☐ Deselect All", key="renewal_deselect_all", use_container_width=True):
            st.session_state['renewal_selected_ids'] = []
            st.rerun(scope="fragment")
    
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
    action_col1, action_col2, action_col3 = st.columns([2, 2, 2])
    
    selected_ids = st.session_state.get('renewal_selected_ids', [])
    
    with action_col1:
        # Preview button
        if st.button(
            "👁️ Preview",
            disabled=len(selected_ids) == 0,
            use_container_width=True,
            key="renewal_preview_btn"
        ):
            preview = renewal_queries.preview_renewal(
                rule_ids=selected_ids,
                new_valid_to=new_valid_to,
                new_valid_from=new_valid_from
            )
            st.session_state['renewal_preview'] = preview
    
    with action_col2:
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
                # Clear selection and close dialog after short delay
                st.session_state['renewal_selected_ids'] = []
                st.session_state['show_renewal_dialog'] = False
                st.session_state['renewal_success'] = True
                st.rerun()
            else:
                st.error(f"❌ Error: {result['message']}")
    
    with action_col3:
        # Cancel button
        if st.button(
            "❌ Cancel",
            use_container_width=True,
            key="renewal_cancel_btn"
        ):
            # Clear state and close
            st.session_state['renewal_selected_ids'] = []
            st.session_state['show_renewal_dialog'] = False
            st.rerun()
    
    # -------------------------------------------------------------------------
    # PREVIEW PANEL (if requested)
    # -------------------------------------------------------------------------
    if 'renewal_preview' in st.session_state and st.session_state['renewal_preview']:
        preview = st.session_state['renewal_preview']
        
        with st.expander("📋 Preview Details", expanded=True):
            st.markdown(f"""
            **Summary:**
            - Rules to renew: **{preview['count']}**
            - Total sales coverage (12m): **{format_currency(preview['total_sales_covered'])}**
            - New end date: **{preview.get('new_valid_to', 'N/A')}**
            """)
            
            if preview.get('new_valid_from'):
                st.markdown(f"- New start date: **{preview['new_valid_from']}**")
            
            st.caption("Click 'Renew' to proceed or 'Cancel' to abort.")


# =============================================================================
# UTILITY: Check for pending dialog on page load
# =============================================================================

def check_and_show_renewal_dialog(user_id: int = None, can_approve: bool = False):
    """
    Check if renewal dialog should be shown and render it.
    
    Call this at the end of split_rules_section to handle dialog display.
    
    Args:
        user_id: Current user ID
        can_approve: Whether user can approve
    """
    if st.session_state.get('show_renewal_dialog', False):
        renewal_dialog_fragment(user_id=user_id, can_approve=can_approve)
    
    # Show success toast if just completed renewal
    if st.session_state.get('renewal_success', False):
        st.toast("✅ Rules renewed successfully!", icon="🎉")
        st.session_state['renewal_success'] = False
