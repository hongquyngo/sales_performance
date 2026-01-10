# utils/kpi_center_performance/setup/renewal/fragments.py
"""
UI Fragments for KPI Center Split Rules Renewal (v3.0)

v3.0 Changes:
- Multi-step confirmation flow: Select → Preview → Processing → Result
- Impact summary with detailed breakdown before execution
- Progress indicator during bulk operations
- Detailed result summary with download option
- Confirmation checkbox for safety on bulk operations

v2.0 Changes:
- Comprehensive filters: Expiry status, Brand, Customer/Product search
- Include EXPIRED rules (not just expiring)
- Better @st.fragment handling to avoid page reruns

Provides:
1. Trigger button to open renewal dialog
2. Multi-step renewal dialog with filters, preview, and execution
3. Proper fragment handling with step navigation
"""

import streamlit as st
import pandas as pd
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional
from io import BytesIO
import time

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

# Dialog step constants
STEP_SELECT = 'select'
STEP_PREVIEW = 'preview'
STEP_PROCESSING = 'processing'
STEP_RESULT = 'result'

# Threshold for requiring confirmation (number of rules)
BULK_CONFIRMATION_THRESHOLD = 50


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


def init_renewal_state():
    """Initialize all renewal-related session state variables."""
    defaults = {
        'renewal_step': STEP_SELECT,
        # Note: 'renewal_selected_ids' is NOT initialized here
        # It will be set by default selection logic in _render_step_select()
        'renewal_selected_df': None,
        'renewal_settings': {},
        'renewal_result': None,
        'renewal_start_time': None,
        'renewal_completed': False,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def reset_renewal_state():
    """Reset renewal state when closing dialog."""
    keys_to_reset = [
        'renewal_step', 'renewal_selected_ids', 'renewal_selected_df',
        'renewal_settings', 'renewal_result', 'renewal_start_time',
        'renewal_dialog_open'  # Track dialog open state for rerun persistence
    ]
    for key in keys_to_reset:
        if key in st.session_state:
            del st.session_state[key]


def get_preview_stats(df: pd.DataFrame) -> Dict:
    """
    Calculate detailed statistics for preview step.
    
    Args:
        df: DataFrame of selected rules
        
    Returns:
        Dict with counts, affected entities, and totals
    """
    if df.empty:
        return {
            'total_rules': 0,
            'expired_count': 0,
            'critical_count': 0,
            'warning_count': 0,
            'normal_count': 0,
            'total_sales': 0,
            'total_gp': 0,
            'unique_customers': 0,
            'unique_products': 0,
            'unique_centers': 0,
            'unique_brands': 0,
        }
    
    return {
        'total_rules': len(df),
        'expired_count': len(df[df['expiry_status'] == 'expired']),
        'critical_count': len(df[df['expiry_status'] == 'critical']),
        'warning_count': len(df[df['expiry_status'] == 'warning']),
        'normal_count': len(df[df['expiry_status'] == 'normal']),
        'total_sales': df['total_sales'].sum() if 'total_sales' in df.columns else 0,
        'total_gp': df['total_gp'].sum() if 'total_gp' in df.columns else 0,
        'unique_customers': df['customer_id'].nunique() if 'customer_id' in df.columns else 0,
        'unique_products': df['product_id'].nunique() if 'product_id' in df.columns else 0,
        'unique_centers': df['kpi_center_id'].nunique() if 'kpi_center_id' in df.columns else 0,
        'unique_brands': df['brand_id'].nunique() if 'brand_id' in df.columns else 0,
    }


def generate_renewal_report(
    selected_df: pd.DataFrame,
    settings: Dict,
    result: Dict
) -> BytesIO:
    """
    Generate Excel report of renewal operation.
    
    Args:
        selected_df: DataFrame of renewed rules
        settings: Renewal settings used
        result: Result of renewal operation
        
    Returns:
        BytesIO buffer containing Excel file
    """
    buffer = BytesIO()
    
    with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
        # Summary sheet
        summary_data = {
            'Item': [
                'Renewal Date',
                'Strategy',
                'New End Date',
                'New Start Date',
                'Auto-approved',
                'Total Rules',
                'Success Count',
                'Failed Count',
                'Duration (seconds)',
            ],
            'Value': [
                datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                settings.get('strategy', 'N/A'),
                str(settings.get('new_valid_to', 'N/A')),
                str(settings.get('new_valid_from', 'N/A')),
                'Yes' if settings.get('auto_approve', False) else 'No',
                result.get('count', 0),
                result.get('count', 0) if result.get('success') else 0,
                0 if result.get('success') else result.get('count', 0),
                f"{result.get('duration', 0):.2f}",
            ]
        }
        summary_df = pd.DataFrame(summary_data)
        summary_df.to_excel(writer, sheet_name='Summary', index=False)
        
        # Details sheet
        if selected_df is not None and not selected_df.empty:
            export_cols = [
                'kpi_center_split_id', 'kpi_center_name', 'kpi_type',
                'customer_display', 'product_display', 'brand',
                'split_percentage', 'effective_from', 'effective_to',
                'expiry_status', 'total_sales', 'total_gp'
            ]
            available_cols = [c for c in export_cols if c in selected_df.columns]
            selected_df[available_cols].to_excel(
                writer, sheet_name='Renewed Rules', index=False
            )
    
    buffer.seek(0)
    return buffer


# =============================================================================
# RENEWAL DIALOG (v3.0) - Multi-step Confirmation Flow
# =============================================================================

@st.dialog("🔄 Renew Split Rules", width="large")
def _renewal_dialog_impl(
    user_id: int,
    can_approve: bool,
    initial_threshold: int = DEFAULT_THRESHOLD_DAYS
):
    """
    Renewal dialog with multi-step confirmation flow.
    
    v3.0: Multi-step flow with preview, progress, and result summary.
    
    Steps:
        1. SELECT: Filter and select rules to renew
        2. PREVIEW: Review impact summary and confirm
        3. PROCESSING: Execute with progress indicator
        4. RESULT: Show summary and download option
    """
    # Initialize state
    init_renewal_state()
    renewal_queries = RenewalQueries(user_id=user_id)
    
    # Get current step
    current_step = st.session_state.get('renewal_step', STEP_SELECT)
    
    # Step indicator
    _render_step_indicator(current_step)
    
    st.divider()
    
    # Route to appropriate step
    if current_step == STEP_SELECT:
        _render_step_select(renewal_queries, can_approve, initial_threshold)
    elif current_step == STEP_PREVIEW:
        _render_step_preview(renewal_queries, can_approve)
    elif current_step == STEP_PROCESSING:
        _render_step_processing(renewal_queries)
    elif current_step == STEP_RESULT:
        _render_step_result()


def _render_step_indicator(current_step: str):
    """Render step progress indicator."""
    steps = [
        (STEP_SELECT, "1️⃣ Select", "Choose rules to renew"),
        (STEP_PREVIEW, "2️⃣ Preview", "Review changes"),
        (STEP_PROCESSING, "3️⃣ Process", "Executing..."),
        (STEP_RESULT, "4️⃣ Done", "View results"),
    ]
    
    cols = st.columns(4)
    for i, (step_id, step_name, step_desc) in enumerate(steps):
        with cols[i]:
            if step_id == current_step:
                st.markdown(f"**{step_name}**")
                st.caption(step_desc)
            elif steps.index((step_id, step_name, step_desc)) < [s[0] for s in steps].index(current_step):
                st.markdown(f"~~{step_name}~~ ✓")
            else:
                st.markdown(f"<span style='color: gray'>{step_name}</span>", unsafe_allow_html=True)


# =============================================================================
# STEP 1: SELECT - Filter and Selection
# =============================================================================

def _render_step_select(
    renewal_queries: RenewalQueries,
    can_approve: bool,
    initial_threshold: int
):
    """Render Step 1: Filter and rule selection."""
    
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
        # Disable all columns except 'Select' to prevent accidental edits
        disabled=[
            'kpi_center_split_id', 'Status', 'Type', 'kpi_center_name',
            'customer_display', 'product_display', 'brand', 'Split', 'Expires', 'Sales', 'GP'
        ],
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
    # ACTION BUTTONS - Navigate to Preview
    # =========================================================================
    selected_ids = st.session_state.get('renewal_selected_ids', [])
    
    # Store settings in session state for preview step
    strategy = st.session_state.get('renewal_strategy', 'extend')
    if strategy == 'extend':
        new_valid_to = st.session_state.get('renewal_new_valid_to', get_default_new_valid_to())
        new_valid_from = None
    else:
        new_valid_from = st.session_state.get('renewal_new_valid_from', date.today())
        new_valid_to = st.session_state.get('renewal_new_valid_to_copy', get_default_new_valid_to())
    
    auto_approve = st.session_state.get('renewal_auto_approve', False) if can_approve else False
    
    action_col1, action_col2 = st.columns([3, 1])
    
    with action_col1:
        if st.button(
            f"👁️ Preview Changes ({len(selected_ids)} rules)",
            type="primary",
            disabled=len(selected_ids) == 0,
            use_container_width=True,
            key="renewal_to_preview"
        ):
            # Save settings and selected data for preview
            st.session_state['renewal_settings'] = {
                'strategy': strategy,
                'new_valid_from': new_valid_from,
                'new_valid_to': new_valid_to,
                'auto_approve': auto_approve,
            }
            # Store selected DataFrame for preview stats
            st.session_state['renewal_selected_df'] = suggestions_df[
                suggestions_df['kpi_center_split_id'].isin(selected_ids)
            ].copy()
            # Navigate to preview
            st.session_state['renewal_step'] = STEP_PREVIEW
            st.rerun()
    
    with action_col2:
        if st.button("❌ Close", use_container_width=True, key="renewal_cancel"):
            reset_renewal_state()
            st.rerun()


# =============================================================================
# STEP 2: PREVIEW - Review and Confirm
# =============================================================================

def _render_step_preview(renewal_queries: RenewalQueries, can_approve: bool):
    """Render Step 2: Preview impact summary and confirm."""
    
    selected_ids = st.session_state.get('renewal_selected_ids', [])
    selected_df = st.session_state.get('renewal_selected_df', pd.DataFrame())
    settings = st.session_state.get('renewal_settings', {})
    
    if not selected_ids or selected_df.empty:
        st.error("No rules selected. Please go back and select rules.")
        if st.button("◀️ Back to Selection", key="preview_back_error"):
            st.session_state['renewal_step'] = STEP_SELECT
            st.rerun()
        return
    
    # =========================================================================
    # RENEWAL SUMMARY
    # =========================================================================
    st.markdown("### 📋 Renewal Summary")
    
    # Settings display
    settings_col1, settings_col2, settings_col3 = st.columns(3)
    
    with settings_col1:
        strategy_info = RENEWAL_STRATEGIES.get(settings.get('strategy', 'extend'), {})
        st.markdown(f"**Strategy:** {strategy_info.get('icon', '📅')} {strategy_info.get('name', 'Extend')}")
    
    with settings_col2:
        st.markdown(f"**New End Date:** `{settings.get('new_valid_to', 'N/A')}`")
        if settings.get('new_valid_from'):
            st.markdown(f"**New Start Date:** `{settings.get('new_valid_from', 'N/A')}`")
    
    with settings_col3:
        if settings.get('auto_approve'):
            st.markdown("**Auto-approve:** ✅ Yes")
        else:
            st.markdown("**Auto-approve:** ❌ No (requires approval)")
    
    st.divider()
    
    # =========================================================================
    # IMPACT SUMMARY
    # =========================================================================
    st.markdown("### 📊 Impact Summary")
    
    stats = get_preview_stats(selected_df)
    
    # Status breakdown
    st.markdown("##### Rules by Status")
    status_cols = st.columns(5)
    
    with status_cols[0]:
        st.metric("📋 Total", f"{stats['total_rules']:,}")
    with status_cols[1]:
        st.metric("⚫ Expired", f"{stats['expired_count']:,}")
    with status_cols[2]:
        st.metric("🔴 Critical", f"{stats['critical_count']:,}")
    with status_cols[3]:
        st.metric("🟠 Warning", f"{stats['warning_count']:,}")
    with status_cols[4]:
        st.metric("🟢 Normal", f"{stats['normal_count']:,}")
    
    # Affected entities
    st.markdown("##### Affected Entities")
    entity_cols = st.columns(4)
    
    with entity_cols[0]:
        st.metric("👥 Customers", f"{stats['unique_customers']:,}")
    with entity_cols[1]:
        st.metric("📦 Products", f"{stats['unique_products']:,}")
    with entity_cols[2]:
        st.metric("🎯 KPI Centers", f"{stats['unique_centers']:,}")
    with entity_cols[3]:
        st.metric("🏷️ Brands", f"{stats['unique_brands']:,}")
    
    # Financial impact
    st.markdown("##### Financial Coverage")
    fin_cols = st.columns(2)
    
    with fin_cols[0]:
        st.metric("💰 Total Sales", format_currency(stats['total_sales']))
    with fin_cols[1]:
        st.metric("📈 Total GP", format_currency(stats['total_gp']))
    
    st.divider()
    
    # =========================================================================
    # CONFIRMATION
    # =========================================================================
    # Warning for bulk operations
    if stats['total_rules'] >= BULK_CONFIRMATION_THRESHOLD:
        st.warning(
            f"⚠️ **Bulk Operation Warning**\n\n"
            f"You are about to renew **{stats['total_rules']:,}** rules. "
            f"This action cannot be undone. Please review the summary above carefully."
        )
        
        confirm_checked = st.checkbox(
            "I have reviewed the changes and want to proceed",
            key="renewal_confirm_checkbox"
        )
    else:
        confirm_checked = True  # No confirmation needed for small batches
    
    st.divider()
    
    # =========================================================================
    # ACTION BUTTONS
    # =========================================================================
    btn_col1, btn_col2, btn_col3 = st.columns([1, 2, 1])
    
    with btn_col1:
        if st.button("◀️ Back", use_container_width=True, key="preview_back"):
            st.session_state['renewal_step'] = STEP_SELECT
            st.rerun()
    
    with btn_col2:
        if st.button(
            f"🔄 Confirm & Renew {stats['total_rules']:,} Rules",
            type="primary",
            disabled=not confirm_checked,
            use_container_width=True,
            key="preview_confirm"
        ):
            # Record start time and move to processing
            st.session_state['renewal_start_time'] = time.time()
            st.session_state['renewal_step'] = STEP_PROCESSING
            st.rerun()
    
    with btn_col3:
        if st.button("❌ Cancel", use_container_width=True, key="preview_cancel"):
            reset_renewal_state()
            st.rerun()


# =============================================================================
# STEP 3: PROCESSING - Execute with Progress
# =============================================================================

def _render_step_processing(renewal_queries: RenewalQueries):
    """Render Step 3: Execute renewal with progress indicator."""
    
    selected_ids = st.session_state.get('renewal_selected_ids', [])
    settings = st.session_state.get('renewal_settings', {})
    start_time = st.session_state.get('renewal_start_time', time.time())
    
    st.markdown("### 🔄 Processing Renewal")
    st.markdown(f"Renewing **{len(selected_ids):,}** rules...")
    
    # Progress placeholder
    progress_bar = st.progress(0, text="Initializing...")
    status_text = st.empty()
    
    # Simulate progress stages (actual execution is atomic)
    stages = [
        (0.1, "Validating rules..."),
        (0.3, "Preparing updates..."),
        (0.5, "Executing renewal..."),
        (0.8, "Finalizing changes..."),
    ]
    
    for progress, status in stages:
        progress_bar.progress(progress, text=status)
        status_text.caption(f"⏳ {status}")
        time.sleep(0.3)  # Brief pause for visual feedback
    
    # Execute the actual renewal
    strategy = settings.get('strategy', 'extend')
    new_valid_to = settings.get('new_valid_to')
    new_valid_from = settings.get('new_valid_from')
    auto_approve = settings.get('auto_approve', False)
    
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
    
    # Calculate duration
    duration = time.time() - start_time
    result['duration'] = duration
    
    # Complete progress
    progress_bar.progress(1.0, text="Complete!")
    
    # Store result and move to result step
    st.session_state['renewal_result'] = result
    st.session_state['renewal_step'] = STEP_RESULT
    time.sleep(0.5)  # Brief pause before showing result
    st.rerun()


# =============================================================================
# STEP 4: RESULT - Summary and Download
# =============================================================================

def _render_step_result():
    """Render Step 4: Show result summary and download option."""
    
    result = st.session_state.get('renewal_result', {})
    settings = st.session_state.get('renewal_settings', {})
    selected_df = st.session_state.get('renewal_selected_df', pd.DataFrame())
    
    # =========================================================================
    # RESULT STATUS
    # =========================================================================
    if result.get('success', False):
        st.success("### ✅ Renewal Completed Successfully!")
    else:
        st.error("### ❌ Renewal Failed")
        st.error(f"Error: {result.get('message', 'Unknown error')}")
    
    st.divider()
    
    # =========================================================================
    # RESULT DETAILS
    # =========================================================================
    st.markdown("### 📊 Results")
    
    result_cols = st.columns(4)
    
    with result_cols[0]:
        if result.get('success'):
            st.metric("✅ Rules Renewed", f"{result.get('count', 0):,}")
        else:
            st.metric("❌ Failed", f"{result.get('count', 0):,}")
    
    with result_cols[1]:
        st.metric("⏱️ Duration", f"{result.get('duration', 0):.1f}s")
    
    with result_cols[2]:
        strategy_info = RENEWAL_STRATEGIES.get(settings.get('strategy', 'extend'), {})
        st.metric("📅 Strategy", strategy_info.get('name', 'Extend'))
    
    with result_cols[3]:
        st.metric("📆 New End Date", str(settings.get('new_valid_to', 'N/A')))
    
    # Additional info
    info_cols = st.columns(2)
    
    with info_cols[0]:
        if settings.get('new_valid_from'):
            st.info(f"**New Start Date:** {settings.get('new_valid_from')}")
    
    with info_cols[1]:
        if settings.get('auto_approve'):
            st.success("**Status:** Auto-approved ✅")
        else:
            st.warning("**Status:** Pending approval ⏳")
    
    st.divider()
    
    # =========================================================================
    # DOWNLOAD REPORT
    # =========================================================================
    if result.get('success') and not selected_df.empty:
        st.markdown("### 📥 Download Report")
        st.caption("Download a detailed report of the renewed rules for your records.")
        
        # Generate report
        report_buffer = generate_renewal_report(selected_df, settings, result)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"renewal_report_{timestamp}.xlsx"
        
        st.download_button(
            label="📥 Download Excel Report",
            data=report_buffer,
            file_name=filename,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="renewal_download_report"
        )
    
    st.divider()
    
    # =========================================================================
    # TIPS AND NEXT STEPS
    # =========================================================================
    if result.get('success'):
        with st.expander("💡 Tips & Next Steps", expanded=False):
            st.markdown("""
            - **Rules are now active** with updated validity periods
            - **Check the main table** to verify the changes
            - **If auto-approve was disabled**, rules will need manual approval
            - **Download the report** above for your records or audit purposes
            """)
    
    # =========================================================================
    # ACTION BUTTONS
    # =========================================================================
    btn_col1, btn_col2 = st.columns(2)
    
    with btn_col1:
        if st.button(
            "🔄 Renew More Rules",
            use_container_width=True,
            key="result_renew_more"
        ):
            reset_renewal_state()
            st.session_state['renewal_step'] = STEP_SELECT
            st.rerun()
    
    with btn_col2:
        if st.button(
            "✅ Done - Close Dialog",
            type="primary",
            use_container_width=True,
            key="result_done"
        ):
            st.session_state['renewal_completed'] = result.get('success', False)
            reset_renewal_state()
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
    
    v3.0: Multi-step dialog with preview and confirmation.
    v3.1: Fixed dialog closing on rerun by tracking open state.
    """
    # Show success toast if just completed
    if st.session_state.get('renewal_completed', False):
        st.toast("✅ Rules renewed successfully!", icon="🎉")
        st.session_state['renewal_completed'] = False
    
    # Button to open dialog
    if st.button(
        "🔄 Renew Expiring",
        help="Open renewal dialog to manage expiring/expired split rules with preview confirmation",
        key="renewal_trigger"
    ):
        # Reset state to start fresh
        reset_renewal_state()
        st.session_state['renewal_dialog_open'] = True
    
    # Open dialog if flag is set (persists across reruns)
    if st.session_state.get('renewal_dialog_open', False):
        _renewal_dialog_impl(
            user_id=user_id,
            can_approve=can_approve,
            initial_threshold=threshold_days
        )