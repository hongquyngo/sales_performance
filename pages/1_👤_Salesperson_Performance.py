# pages/1_👤_Salesperson_Performance.py
"""
👤 Salesperson Performance Dashboard (Tabbed Version)

5 Tabs:
1. Overview - KPI summary, charts, trends
2. Sales Detail - Transaction list, pivot analysis
3. Backlog - Backlog detail, ETD analysis, risk
4. KPI & Targets - KPI assignments, progress, ranking
5. Setup - Sales split, customer/product portfolio

CHANGELOG:
- v2.4.0: ADDED Comprehensive Excel Export (Fragment-based)
          - Export button in Overview tab (no page reload!)
          - Uses @st.fragment to run independently
          - Includes: Summary, Pipeline & Forecast, By Salesperson, Monthly, 
            Sales Detail, Backlog Summary, Backlog Detail, Backlog by ETD
          - Professional formatting with conditional colors
- v2.3.0: IMPROVED naming convention and Help text
          - Renamed "In-Period Backlog" → "In-Period (KPI)" in Overview
          - Renamed "Forecast" → "Forecast (KPI)" in Overview
          - Renamed "Target (Prorated)" → "Target" in Overview
          - Updated all Help popovers with consistent English text
          - Added clear distinction between Overview (KPI-filtered) vs Backlog Tab (all employees)
          - Improved help text explaining KPI filtering logic
- v2.2.0: FIXED Backlog data mismatch between Overview and Backlog Tab
          - Removed LIMIT from get_backlog_detail() call (was limit=2000)
          - Fixed Overview Total Backlog orders count source
            (was using in-period orders, now uses summary backlog_orders)
          - Pass total_backlog_df to backlog_list_fragment for accurate totals
          - Backlog Tab now uses aggregated totals instead of sum from detail
- v2.1.0: REFACTORED - Smart data caching and deferred filter execution
          - All sidebar filters inside st.form (no rerun until "Apply Filters" clicked)
          - Smart year range caching: only reload when date range expands
          - Session state management for applied filters vs form values
          - Significant performance improvement for filter changes

Version: 2.4.0
"""

import streamlit as st
from datetime import datetime, date
import logging
import pandas as pd
import time

# Shared utilities
from utils.auth import AuthManager
from utils.db import check_db_connection

# Page-specific module
from utils.salesperson_performance import (
    AccessControl,
    SalespersonQueries,
    SalespersonMetrics,
    SalespersonFilters,
    SalespersonCharts,
    MONTH_ORDER
)

from utils.salesperson_performance.fragments import (
    monthly_trend_fragment,
    yoy_comparison_fragment,
    sales_detail_fragment,
    pivot_analysis_fragment,
    backlog_list_fragment,
    export_report_fragment,
)
from utils.salesperson_performance.filters import (
    analyze_period,
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _clean_dataframe_for_display(df: pd.DataFrame) -> pd.DataFrame:
    """
    Clean dataframe to avoid Arrow serialization errors.
    Fixes mixed type columns (especially year columns from SQL DATE_FORMAT).
    """
    if df.empty:
        return df
    
    df_clean = df.copy()
    
    # Columns that should be numeric but might be strings from SQL DATE_FORMAT
    year_columns = ['etd_year', 'oc_year', 'invoice_year', 'year']
    numeric_columns = ['days_until_etd', 'days_since_order', 'split_rate_percent', 'split_percentage']
    
    for col in year_columns:
        if col in df_clean.columns:
            df_clean[col] = pd.to_numeric(df_clean[col], errors='coerce').fillna(0).astype(int)
    
    for col in numeric_columns:
        if col in df_clean.columns:
            df_clean[col] = pd.to_numeric(df_clean[col], errors='coerce')
    
    # Fix object columns with mixed types (but preserve dates)
    for col in df_clean.columns:
        if df_clean[col].dtype == 'object':
            # Skip date-like columns
            if any(x in col.lower() for x in ['date', '_at', 'etd', 'due']):
                continue
            
            # Check if this column has truly mixed types
            unique_types = set(type(x).__name__ for x in df_clean[col].dropna().head(100))
            if len(unique_types) > 1 and 'str' in unique_types:
                try:
                    df_clean[col] = df_clean[col].astype(str).replace('nan', '').replace('None', '')
                except:
                    pass
    
    return df_clean


def _is_period_active(period_str: str, today_str: str) -> bool:
    """
    Check if today falls within the effective period.
    
    Args:
        period_str: Period string in format "YYYY-MM-DD -> YYYY-MM-DD"
        today_str: Today's date in format "YYYY-MM-DD"
    
    Returns:
        True if period is active (today is within range)
    """
    if not period_str or ' -> ' not in str(period_str):
        return True  # No period defined = always active
    try:
        start, end = str(period_str).split(' -> ')
        return start.strip() <= today_str <= end.strip()
    except:
        return True


def _is_period_expired(period_str: str, today_str: str) -> bool:
    """
    Check if the effective period has ended.
    
    Args:
        period_str: Period string in format "YYYY-MM-DD -> YYYY-MM-DD"
        today_str: Today's date in format "YYYY-MM-DD"
    
    Returns:
        True if period has expired (end date < today)
    """
    if not period_str or ' -> ' not in str(period_str):
        return False  # No period defined = never expired
    try:
        _, end = str(period_str).split(' -> ')
        return end.strip() < today_str
    except:
        return False

# =============================================================================
# PAGE CONFIGURATION
# =============================================================================

st.set_page_config(
    page_title="Salesperson Performance",
    page_icon="👤",
    layout="wide",
    initial_sidebar_state="expanded"
)

# =============================================================================
# AUTHENTICATION CHECK
# =============================================================================

auth = AuthManager()

if not auth.check_session():
    st.warning("⚠️ Please login to access this page")
    st.info("Go to the main page to login")
    st.stop()

# =============================================================================
# DATABASE CONNECTION CHECK
# =============================================================================

db_connected, db_error = check_db_connection()

if not db_connected:
    st.error(f"❌ Database connection failed: {db_error}")
    st.info("Please check your network connection or VPN")
    st.stop()

# =============================================================================
# INITIALIZE COMPONENTS
# =============================================================================

access = AccessControl(
    user_role=st.session_state.get('user_role', 'viewer'),
    employee_id=st.session_state.get('employee_id')
)

queries = SalespersonQueries(access)
filters_ui = SalespersonFilters(access)

# =============================================================================
# SIDEBAR FILTERS (Form-based - only applies on click)
# =============================================================================

salesperson_options = queries.get_salesperson_options()
entity_options = queries.get_entity_options()

# Get default date range from database
default_start, default_end = queries.get_default_date_range()

# Use form-based filters to prevent rerun on every change
filter_values, filters_submitted = filters_ui.render_filter_form(
    salesperson_df=salesperson_options,
    entity_df=entity_options,
    default_start_date=default_start,
    default_end_date=default_end
)

is_valid, error_msg = filters_ui.validate_filters(filter_values)
if not is_valid:
    st.error(f"⚠️ {error_msg}")
    st.stop()

# =============================================================================
# LOAD ALL DATA WITH SMART CACHING (Client-Side Filtering)
# =============================================================================

def load_data_for_year_range(start_year: int, end_year: int) -> dict:
    """
    Load data for specified year range based on user's access control.
    
    REFACTORED v2.1.0:
    - Accepts start_year and end_year parameters instead of hardcoded 3 years
    - Supports smart caching: only reload when year range expands
    
    OPTIMIZED v2.0:
    - Full access (admin/GM/MD): Load all data
    - Team access (sales_manager): Load only team members' data
    - Self access (sales): Load only own data
    
    This significantly reduces load time for non-admin users.
    """
    # Initialize AccessControl
    access_control = AccessControl(
        st.session_state.get('user_role', 'viewer'),
        st.session_state.get('employee_id')
    )
    
    # Get accessible employee IDs based on role
    access_level = access_control.get_access_level()
    accessible_ids = access_control.get_accessible_employee_ids()
    
    # For full access, pass None to load all (more efficient than huge IN clause)
    # For restricted access, pass the specific IDs
    if access_level == 'full':
        filter_employee_ids = None  # Load all
        load_msg = "all salespeople"
    else:
        filter_employee_ids = accessible_ids if accessible_ids else None
        if access_level == 'team':
            load_msg = f"team ({len(accessible_ids)} members)"
        else:
            load_msg = "your data only"
    
    q = SalespersonQueries(access_control)
    
    # Use provided year range
    start_date = date(start_year, 1, 1)
    end_date = date(end_year, 12, 31)
    
    # Progress bar with status
    progress_bar = st.progress(0, text=f"🔄 Loading {load_msg} ({start_year}-{end_year})...")
    
    data = {}
    
    try:
        # Step 1: Sales data - FILTERED by access control
        progress_bar.progress(10, text=f"📊 Loading sales data ({load_msg})...")
        data['sales'] = q.get_sales_data(
            start_date=start_date,
            end_date=end_date,
            employee_ids=filter_employee_ids,
            entity_ids=None
        )
        
        # Step 2: KPI targets - FILTERED by access control
        progress_bar.progress(25, text="🎯 Loading KPI targets...")
        targets_list = []
        for yr in range(start_year, end_year + 1):
            t = q.get_kpi_targets(year=yr, employee_ids=filter_employee_ids)
            if not t.empty:
                targets_list.append(t)
        data['targets'] = pd.concat(targets_list, ignore_index=True) if targets_list else pd.DataFrame()
        
        # Step 3: Complex KPIs - FILTERED by access control
        progress_bar.progress(40, text="🆕 Loading new business metrics...")
        data['new_customers'] = q.get_new_customers(start_date, end_date, filter_employee_ids)
        data['new_products'] = q.get_new_products(start_date, end_date, filter_employee_ids)
        data['new_business'] = q.get_new_business_revenue(start_date, end_date, filter_employee_ids)
        
        # Step 4: Backlog data - FILTERED by access control
        progress_bar.progress(60, text="📦 Loading backlog data...")
        data['total_backlog'] = q.get_backlog_data(
            employee_ids=filter_employee_ids,
            entity_ids=None
        )
        data['in_period_backlog'] = q.get_backlog_in_period(
            start_date=start_date,
            end_date=end_date,
            employee_ids=filter_employee_ids,
            entity_ids=None
        )
        data['backlog_by_month'] = q.get_backlog_by_month(
            employee_ids=filter_employee_ids,
            entity_ids=None
        )
        
        # Step 5: Backlog detail - FILTERED by access control
        # UPDATED v2.2.0: Removed limit to get ALL backlog records for accurate totals
        progress_bar.progress(80, text="📋 Loading backlog details...")
        data['backlog_detail'] = q.get_backlog_detail(
            employee_ids=filter_employee_ids,
            entity_ids=None
            # limit removed - now returns all records (default: None)
        )
        
        # Step 6: Sales split data - FILTERED by access control
        progress_bar.progress(95, text="👥 Loading sales split data...")
        data['sales_split'] = q.get_sales_split_data(employee_ids=filter_employee_ids)
        
        # Step 7: Clean all dataframes
        for key in data:
            if isinstance(data[key], pd.DataFrame) and not data[key].empty:
                data[key] = _clean_dataframe_for_display(data[key])
        
        # Store metadata
        data['_loaded_at'] = datetime.now()
        data['_access_level'] = access_level
        data['_accessible_ids'] = accessible_ids
        data['_year_range'] = (start_year, end_year)
        
        # Complete
        progress_bar.progress(100, text="✅ Data loaded successfully!")
        
    except Exception as e:
        progress_bar.empty()
        st.error(f"❌ Error loading data: {str(e)}")
        logger.exception("Error loading data")
        st.stop()
    
    finally:
        # Clear progress bar after short delay
        time.sleep(0.3)
        progress_bar.empty()
    
    return data


def filter_data_client_side(raw_data: dict, filter_values: dict) -> dict:
    """
    Filter cached data client-side based on ALL filters.
    This is instant - no DB query needed.
    
    UPDATED v1.1.0: Added exclude_internal_revenue handling
    - Uses customer_type column from unified_sales_by_salesperson_view
    - When True: Sets revenue to 0 for Internal customers, keeps GP intact
    - Purpose: Evaluate sales performance with real (external) customers only
    """
    start_date = filter_values['start_date']
    end_date = filter_values['end_date']
    employee_ids = filter_values['employee_ids']
    entity_ids = filter_values['entity_ids']
    year = filter_values['year']
    exclude_internal_revenue = filter_values.get('exclude_internal_revenue', True)  # NEW
    
    filtered = {}
    
    for key, df in raw_data.items():
        # Skip metadata
        if key.startswith('_'):
            continue
            
        if not isinstance(df, pd.DataFrame) or df.empty:
            filtered[key] = df
            continue
        
        df_filtered = df.copy()
        
        # Filter by date range
        # FIXED v1.3.0: Added date columns for complex KPIs
        date_cols = [
            'inv_date',              # sales data
            'oc_date',               # order confirmation
            'invoiced_date',         # backlog
            'first_invoice_date',    # new_customers
            'first_sale_date',       # new_products
        ]
        for date_col in date_cols:
            if date_col in df_filtered.columns:
                df_filtered[date_col] = pd.to_datetime(df_filtered[date_col], errors='coerce')
                df_filtered = df_filtered[
                    (df_filtered[date_col] >= pd.Timestamp(start_date)) & 
                    (df_filtered[date_col] <= pd.Timestamp(end_date))
                ]
                break
        
        # Filter by employee_ids (salesperson)
        if employee_ids:
            emp_ids_set = set(employee_ids)
            if 'sales_id' in df_filtered.columns:
                df_filtered = df_filtered[df_filtered['sales_id'].isin(emp_ids_set)]
            elif 'employee_id' in df_filtered.columns:
                df_filtered = df_filtered[df_filtered['employee_id'].isin(emp_ids_set)]
        
        # Filter by entity_ids
        if entity_ids:
            entity_ids_set = set(entity_ids)
            if 'entity_id' in df_filtered.columns:
                df_filtered = df_filtered[df_filtered['entity_id'].isin(entity_ids_set)]
            elif 'legal_entity_id' in df_filtered.columns:
                df_filtered = df_filtered[df_filtered['legal_entity_id'].isin(entity_ids_set)]
        
        # Special handling for targets - filter by year
        if key == 'targets' and 'year' in df_filtered.columns:
            df_filtered = df_filtered[df_filtered['year'] == year]
        
        # =====================================================================
        # NEW: Exclude Internal Revenue (but keep GP)
        # Uses customer_type column from unified_sales_by_salesperson_view
        # customer_type = 'Internal' for internal companies
        # =====================================================================
        if exclude_internal_revenue and key == 'sales':
            if 'customer_type' in df_filtered.columns and 'sales_by_split_usd' in df_filtered.columns:
                # Create mask for internal customers
                is_internal = df_filtered['customer_type'].str.lower() == 'internal'
                
                # Log for debugging
                internal_count = is_internal.sum()
                if internal_count > 0:
                    internal_revenue = df_filtered.loc[is_internal, 'sales_by_split_usd'].sum()
                    logger.info(
                        f"Excluding internal revenue: {internal_count} rows, "
                        f"${internal_revenue:,.0f} revenue zeroed (GP kept intact)"
                    )
                
                # Zero out ONLY revenue for internal customers
                # GP columns (gross_profit_by_split_usd, gp1_by_split_usd) are kept intact
                # This allows evaluation of sales performance with real customers
                df_filtered.loc[is_internal, 'sales_by_split_usd'] = 0
        
        filtered[key] = df_filtered
    
    return filtered

# =============================================================================
# SMART CACHING LOGIC - Only reload when year range expands
# =============================================================================

def _get_applied_filters():
    """Get currently applied filters from session state."""
    return st.session_state.get('_applied_filters')


def _set_applied_filters(filters: dict):
    """Store applied filters in session state."""
    st.session_state['_applied_filters'] = filters.copy()


def _get_cached_year_range():
    """Get the year range of currently cached data."""
    return (
        st.session_state.get('_cached_start_year'),
        st.session_state.get('_cached_end_year')
    )


def _set_cached_year_range(start_year: int, end_year: int):
    """Store the year range of cached data."""
    st.session_state['_cached_start_year'] = start_year
    st.session_state['_cached_end_year'] = end_year


def _needs_data_reload(filter_values: dict) -> bool:
    """
    Check if we need to reload data from database.
    
    Returns True if:
    - No cached data exists
    - Requested year range expands beyond cached range
    """
    if 'raw_cached_data' not in st.session_state or st.session_state.raw_cached_data is None:
        return True
    
    cached_start, cached_end = _get_cached_year_range()
    if cached_start is None or cached_end is None:
        return True
    
    required_start = filter_values['start_date'].year
    required_end = filter_values['end_date'].year
    
    # Need reload if requested range expands beyond cached range
    return required_start < cached_start or required_end > cached_end


def get_or_load_data(filter_values: dict) -> dict:
    """
    Smart data loading with session-based caching.
    Only reloads if requested year range expands beyond cached range.
    
    Args:
        filter_values: Current filter values
        
    Returns:
        Raw data dict (not yet filtered by current filters)
    """
    required_start = filter_values['start_date'].year
    required_end = filter_values['end_date'].year
    
    cached_start, cached_end = _get_cached_year_range()
    
    # Check if we need to expand the cached range
    if _needs_data_reload(filter_values):
        # Calculate expanded range
        if cached_start is not None and cached_end is not None:
            # Expand existing range
            new_start = min(required_start, cached_start)
            new_end = max(required_end, cached_end)
        else:
            # First load - use default 3 years from current year
            current_year = date.today().year
            new_start = min(required_start, current_year - 2)
            new_end = max(required_end, current_year)
        
        # Load data for expanded range
        data = load_data_for_year_range(new_start, new_end)
        
        # Cache data and year range
        st.session_state.raw_cached_data = data
        _set_cached_year_range(new_start, new_end)
        
        return data
    
    return st.session_state.raw_cached_data


# Initialize applied filters on first load
if _get_applied_filters() is None:
    _set_applied_filters(filter_values)
    filters_submitted = True  # Force initial load

# Update applied filters when form is submitted
if filters_submitted:
    _set_applied_filters(filter_values)
    logger.info(f"Filters applied: {filter_values['period_type']} {filter_values['year']}")

# Always use applied filters (not current form values)
# This ensures data stays consistent even if form values change without submit
active_filters = _get_applied_filters()

# Add Refresh button in sidebar
with st.sidebar:
    st.divider()
    col_r1, col_r2 = st.columns([1, 1])
    with col_r1:
        if st.button("🔄 Refresh", use_container_width=True, help="Reload data from database"):
            # Clear all cached data
            st.session_state.raw_cached_data = None
            if '_cached_start_year' in st.session_state:
                del st.session_state['_cached_start_year']
            if '_cached_end_year' in st.session_state:
                del st.session_state['_cached_end_year']
            st.rerun()
    with col_r2:
        cached_start, cached_end = _get_cached_year_range()
        if cached_start and cached_end:
            st.caption(f"📦 {cached_start}-{cached_end}")
    
# Load data with smart caching
raw_data = get_or_load_data(active_filters)

# =============================================================================
# APPLY CLIENT-SIDE FILTERING (Instant - no DB query)
# =============================================================================

data = filter_data_client_side(
    raw_data=raw_data,
    filter_values=active_filters
)

# Check if we have any data
if data['sales'].empty and data['total_backlog'].empty:
    st.warning("📭 No data found for the selected filters")
    st.info("Try adjusting your filter criteria")
    st.stop()

# =============================================================================
# CALCULATE METRICS
# =============================================================================

metrics_calc = SalespersonMetrics(data['sales'], data['targets'])

overview_metrics = metrics_calc.calculate_overview_metrics(
    period_type=active_filters['period_type'],
    year=active_filters['year']
)

# FIXED v1.3.0: Query new_business fresh with correct date range
# new_business is aggregated data without date column, cannot filter client-side
fresh_new_business_df = queries.get_new_business_revenue(
    start_date=active_filters['start_date'],
    end_date=active_filters['end_date'],
    employee_ids=active_filters['employee_ids']
)

# NEW v1.5.0: Query new_business detail for combo-level display in popover
fresh_new_business_detail_df = queries.get_new_business_detail(
    start_date=active_filters['start_date'],
    end_date=active_filters['end_date'],
    employee_ids=active_filters['employee_ids']
)

complex_kpis = metrics_calc.calculate_complex_kpis(
    new_customers_df=data['new_customers'],
    new_products_df=data['new_products'],
    new_business_df=fresh_new_business_df  # Use fresh data instead of cached
)

backlog_metrics = metrics_calc.calculate_backlog_metrics(
    total_backlog_df=data['total_backlog'],
    in_period_backlog_df=data['in_period_backlog'],
    period_type=active_filters['period_type'],
    year=active_filters['year'],
    start_date=active_filters['start_date'],
    end_date=active_filters['end_date']
)

# NEW v2.5.0: Calculate Pipeline & Forecast with KPI-filtered logic
# This ensures each metric (Revenue/GP/GP1) only includes data from
# employees who have that specific KPI target assigned
pipeline_forecast_metrics = metrics_calc.calculate_pipeline_forecast_metrics(
    total_backlog_df=data['total_backlog'],
    in_period_backlog_df=data['in_period_backlog'],
    backlog_detail_df=data['backlog_detail'],  # Needed for employee filtering
    period_type=active_filters['period_type'],
    year=active_filters['year'],
    start_date=active_filters['start_date'],
    end_date=active_filters['end_date']
)

# Analyze in-period backlog for overdue detection
in_period_backlog_analysis = metrics_calc.analyze_in_period_backlog(
    backlog_detail_df=data['backlog_detail'],
    start_date=active_filters['start_date'],
    end_date=active_filters['end_date']
)

# Get period context for display logic
period_context = backlog_metrics.get('period_context', {})

# =============================================================================
# ANALYZE PERIOD TYPE
# =============================================================================

period_info = analyze_period(active_filters)

# YoY comparison (only for single-year periods)
yoy_metrics = None
if active_filters['compare_yoy'] and not period_info['is_multi_year']:
    previous_sales_df = queries.get_previous_year_data(
        start_date=active_filters['start_date'],
        end_date=active_filters['end_date'],
        employee_ids=active_filters['employee_ids'],
        entity_ids=active_filters['entity_ids'] if active_filters['entity_ids'] else None
    )
    
    if not previous_sales_df.empty:
        prev_metrics_calc = SalespersonMetrics(previous_sales_df, None)
        prev_overview = prev_metrics_calc.calculate_overview_metrics(
            period_type=active_filters['period_type'],
            year=active_filters['year'] - 1
        )
        yoy_metrics = metrics_calc.calculate_yoy_comparison(overview_metrics, prev_overview)

# Overall KPI Achievement (weighted average)
overall_achievement = metrics_calc.calculate_overall_kpi_achievement(
    overview_metrics=overview_metrics,
    complex_kpis=complex_kpis,
    period_type=active_filters['period_type'],
    year=active_filters['year']
)

# =============================================================================
# PAGE HEADER
# =============================================================================

st.title("👤 Salesperson Performance")
filter_summary = filters_ui.get_filter_summary(active_filters)
st.caption(f"📊 {filter_summary}")

# =============================================================================
# TABS
# =============================================================================

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📊 Overview",
    "📋 Sales Detail",
    "📦 Backlog",
    "🎯 KPI & Targets",
    "⚙️ Setup"
])

# =============================================================================
# TAB 1: OVERVIEW
# =============================================================================

with tab1:
    # KPI Cards - Performance & New Business sections
    SalespersonCharts.render_kpi_cards(
        metrics=overview_metrics,
        yoy_metrics=yoy_metrics,
        complex_kpis=complex_kpis,
        backlog_metrics=None,  # Backlog shown in separate Backlog & Forecast section below
        overall_achievement=overall_achievement,
        show_complex=True,
        show_backlog=False,  # Backlog & Forecast section is rendered separately
        # NEW v1.2.0: Pass detail dataframes for popup buttons
        new_customers_df=data['new_customers'],
        new_products_df=data['new_products'],
        new_business_df=fresh_new_business_df,
        # NEW v1.5.0: Pass combo detail for New Business popup
        new_business_detail_df=fresh_new_business_detail_df
    )
    
    st.divider()
    
    # ==========================================================================
    # MONTHLY TREND + CUMULATIVE - FRAGMENT
    # Only reruns when filters in this section change (not entire page)
    # ==========================================================================
    monthly_trend_fragment(
        sales_df=data['sales'],
        targets_df=data['targets'],
        fragment_key="trend"
    )
    
    # ==========================================================================
    # YEAR COMPARISON SECTION
    # Single-year: YoY Comparison (current vs previous year)
    # Multi-year: Multi-Year Comparison (all years in period)
    # ==========================================================================
    
    st.divider()
    
    # ==========================================================================
    # YEAR-OVER-YEAR COMPARISON - FRAGMENT
    # Only reruns when filters in this section change (not entire page)
    # ==========================================================================
    yoy_comparison_fragment(
        sales_df=data['sales'],
        queries=queries,
        filter_values=active_filters,
        fragment_key="yoy"
    )
    
    st.divider()
    
    # Forecast section - only show for current/future periods
    if period_context.get('show_forecast', True):
        col_bf_header, col_bf_help = st.columns([6, 1])
        with col_bf_header:
            st.subheader("📦 Backlog & Forecast")
        with col_bf_help:
            with st.popover("ℹ️ Help"):
                st.markdown("""
**📦 Backlog & Forecast**

| Metric | Formula | Description |
|--------|---------|-------------|
| **Total Backlog** | `Σ backlog_by_split_usd` | All outstanding orders (all employees) |
| **In-Period (KPI)** | `Σ backlog WHERE ETD in period` | Backlog expected to ship in period. **Only from employees with this KPI assigned.** |
| **Target** | `Σ prorated_target` | Sum of prorated annual targets |
| **Forecast (KPI)** | `Invoiced + In-Period` | Projected total. **Only from employees with this KPI assigned.** |
| **GAP/Surplus** | `Forecast - Target` | Positive = ahead of target, Negative = behind |

---

**⚠️ Important: Data Filtered by KPI Assignment**

Each tab shows data ONLY from employees who have that specific KPI target:
- **Revenue tab**: Employees with Revenue KPI
- **GP tab**: Employees with Gross Profit KPI  
- **GP1 tab**: Employees with GP1 KPI

This ensures accurate achievement calculation.

---

**📐 Target Calculation:**
```
Target = Σ (Annual_Target × Proration_Factor)
```

Proration by Period Type:
- **YTD**: elapsed_months / 12
- **QTD**: 1/4
- **MTD**: 1/12

---

**📊 GP1 Backlog Estimation:**
```
Backlog GP1 = Backlog GP × (GP1/GP ratio from invoiced data)
```
                """)
        
        # Show overdue warning if applicable
        if in_period_backlog_analysis.get('overdue_warning'):
            st.warning(in_period_backlog_analysis['overdue_warning'])
        
        # Convert pipeline_forecast_metrics to legacy format for chart methods
        chart_backlog_metrics = SalespersonCharts.convert_pipeline_to_backlog_metrics(
            pipeline_forecast_metrics
        )
        
        # Extract metrics for cards
        revenue_metrics = pipeline_forecast_metrics.get('revenue', {})
        gp_metrics = pipeline_forecast_metrics.get('gross_profit', {})
        gp1_metrics = pipeline_forecast_metrics.get('gp1', {})
        summary_metrics = pipeline_forecast_metrics.get('summary', {})
        
        # Show GP1/GP ratio if available
        gp1_gp_ratio = summary_metrics.get('gp1_gp_ratio', 1.0)
        if gp1_gp_ratio != 1.0:
            st.caption(f"📊 GP1 backlog estimated using GP1/GP ratio: {gp1_gp_ratio:.2%}")
        
        # Tabs for different metrics
        bf_tab1, bf_tab2, bf_tab3 = st.tabs(["💰 Revenue", "📈 Gross Profit", "📊 GP1"])
        
        # =================================================================
        # TAB: REVENUE
        # =================================================================
        with bf_tab1:
            # Metrics cards row
            col_m1, col_m2, col_m3, col_m4, col_m5 = st.columns(5)
            
            with col_m1:
                # FIXED v2.2.0: Use summary_metrics for orders count to match total_backlog_revenue
                st.metric(
                    label="Total Backlog",
                    value=f"${summary_metrics.get('total_backlog_revenue', 0):,.0f}",
                    delta=f"{int(summary_metrics.get('backlog_orders', 0)):,} orders" if summary_metrics.get('backlog_orders') else None,
                    delta_color="off",
                    help="All outstanding revenue from pending orders (all employees)"
                )
            
            with col_m2:
                in_period = revenue_metrics.get('in_period_backlog', 0)
                target = revenue_metrics.get('target')
                pct = (in_period / target * 100) if target and target > 0 else None
                emp_count = revenue_metrics.get('employee_count', 0)
                st.metric(
                    label="In-Period (KPI)",
                    value=f"${in_period:,.0f}",
                    delta=f"{pct:.0f}% of target" if pct else None,
                    delta_color="off",
                    help=f"Backlog with ETD in period. Only from {emp_count} employees with Revenue KPI assigned."
                )
            
            with col_m3:
                target = revenue_metrics.get('target')
                emp_count = revenue_metrics.get('employee_count', 0)
                if target and target > 0:
                    st.metric(
                        label="Target",
                        value=f"${target:,.0f}",
                        delta=f"{emp_count} people",
                        delta_color="off",
                        help=f"Sum of prorated Revenue targets from {emp_count} employees with Revenue KPI"
                    )
                else:
                    st.metric(label="Target", value="N/A", delta="No KPI assigned", delta_color="off")
            
            with col_m4:
                forecast = revenue_metrics.get('forecast')
                achievement = revenue_metrics.get('forecast_achievement')
                emp_count = revenue_metrics.get('employee_count', 0)
                if forecast is not None:
                    delta_color = "normal" if achievement and achievement >= 100 else "inverse"
                    st.metric(
                        label="Forecast (KPI)",
                        value=f"${forecast:,.0f}",
                        delta=f"{achievement:.0f}% of target" if achievement else None,
                        delta_color=delta_color if achievement else "off",
                        help=f"Invoiced + In-Period Backlog. Only from {emp_count} employees with Revenue KPI."
                    )
                else:
                    st.metric(label="Forecast (KPI)", value="N/A", delta_color="off")
            
            with col_m5:
                gap = revenue_metrics.get('gap')
                gap_pct = revenue_metrics.get('gap_percent')
                if gap is not None:
                    label = "Surplus ✅" if gap >= 0 else "GAP ⚠️"
                    delta_color = "normal" if gap >= 0 else "inverse"
                    st.metric(
                        label=label,
                        value=f"${gap:+,.0f}",
                        delta=f"{gap_pct:+.1f}%" if gap_pct else None,
                        delta_color=delta_color,
                        help="Forecast - Target. Positive = ahead, Negative = behind."
                    )
                else:
                    st.metric(label="GAP", value="N/A", delta_color="off")
            
            # Charts row
            col_bf1, col_bf2 = st.columns(2)
            with col_bf1:
                forecast_chart = SalespersonCharts.build_forecast_waterfall_chart(
                    backlog_metrics=chart_backlog_metrics,
                    metric='revenue',
                    title="Revenue Forecast vs Target"
                )
                st.altair_chart(forecast_chart, use_container_width=True)
            with col_bf2:
                gap_chart = SalespersonCharts.build_gap_analysis_chart(
                    backlog_metrics=chart_backlog_metrics,
                    metrics_to_show=['revenue'],
                    title="Revenue: Target vs Forecast"
                )
                st.altair_chart(gap_chart, use_container_width=True)
        
        # =================================================================
        # TAB: GROSS PROFIT
        # =================================================================
        with bf_tab2:
            # Metrics cards row
            col_m1, col_m2, col_m3, col_m4, col_m5 = st.columns(5)
            
            with col_m1:
                # FIXED v2.2.0: Use summary_metrics for orders count to match total_backlog_gp
                st.metric(
                    label="Total Backlog",
                    value=f"${summary_metrics.get('total_backlog_gp', 0):,.0f}",
                    delta=f"{int(summary_metrics.get('backlog_orders', 0)):,} orders" if summary_metrics.get('backlog_orders') else None,
                    delta_color="off",
                    help="All outstanding GP from pending orders (all employees)"
                )
            
            with col_m2:
                in_period = gp_metrics.get('in_period_backlog', 0)
                target = gp_metrics.get('target')
                pct = (in_period / target * 100) if target and target > 0 else None
                emp_count = gp_metrics.get('employee_count', 0)
                st.metric(
                    label="In-Period (KPI)",
                    value=f"${in_period:,.0f}",
                    delta=f"{pct:.0f}% of target" if pct else None,
                    delta_color="off",
                    help=f"Backlog with ETD in period. Only from {emp_count} employees with GP KPI assigned."
                )
            
            with col_m3:
                target = gp_metrics.get('target')
                emp_count = gp_metrics.get('employee_count', 0)
                if target and target > 0:
                    st.metric(
                        label="Target",
                        value=f"${target:,.0f}",
                        delta=f"{emp_count} people",
                        delta_color="off",
                        help=f"Sum of prorated GP targets from {emp_count} employees with GP KPI"
                    )
                else:
                    st.metric(label="Target", value="N/A", delta="No KPI assigned", delta_color="off")
            
            with col_m4:
                forecast = gp_metrics.get('forecast')
                achievement = gp_metrics.get('forecast_achievement')
                emp_count = gp_metrics.get('employee_count', 0)
                if forecast is not None:
                    delta_color = "normal" if achievement and achievement >= 100 else "inverse"
                    st.metric(
                        label="Forecast (KPI)",
                        value=f"${forecast:,.0f}",
                        delta=f"{achievement:.0f}% of target" if achievement else None,
                        delta_color=delta_color if achievement else "off",
                        help=f"Invoiced + In-Period Backlog. Only from {emp_count} employees with GP KPI."
                    )
                else:
                    st.metric(label="Forecast (KPI)", value="N/A", delta_color="off")
            
            with col_m5:
                gap = gp_metrics.get('gap')
                gap_pct = gp_metrics.get('gap_percent')
                if gap is not None:
                    label = "Surplus ✅" if gap >= 0 else "GAP ⚠️"
                    delta_color = "normal" if gap >= 0 else "inverse"
                    st.metric(
                        label=label,
                        value=f"${gap:+,.0f}",
                        delta=f"{gap_pct:+.1f}%" if gap_pct else None,
                        delta_color=delta_color,
                        help="Forecast - Target. Positive = ahead, Negative = behind."
                    )
                else:
                    st.metric(label="GAP", value="N/A", delta_color="off")
            
            # Charts row
            col_bf1, col_bf2 = st.columns(2)
            with col_bf1:
                forecast_chart = SalespersonCharts.build_forecast_waterfall_chart(
                    backlog_metrics=chart_backlog_metrics,
                    metric='gp',
                    title="GP Forecast vs Target"
                )
                st.altair_chart(forecast_chart, use_container_width=True)
            with col_bf2:
                gap_chart = SalespersonCharts.build_gap_analysis_chart(
                    backlog_metrics=chart_backlog_metrics,
                    metrics_to_show=['gp'],
                    title="GP: Target vs Forecast"
                )
                st.altair_chart(gap_chart, use_container_width=True)
        
        # =================================================================
        # TAB: GP1
        # =================================================================
        with bf_tab3:
            # Metrics cards row
            col_m1, col_m2, col_m3, col_m4, col_m5 = st.columns(5)
            
            with col_m1:
                # FIXED v2.2.0: Use summary_metrics for orders count to match total_backlog_gp1
                st.metric(
                    label="Total Backlog",
                    value=f"${summary_metrics.get('total_backlog_gp1', 0):,.0f}",
                    delta=f"{int(summary_metrics.get('backlog_orders', 0)):,} orders" if summary_metrics.get('backlog_orders') else None,
                    delta_color="off",
                    help=f"Estimated GP1 backlog (GP × {gp1_gp_ratio:.2%}). All employees."
                )
            
            with col_m2:
                in_period = gp1_metrics.get('in_period_backlog', 0)
                target = gp1_metrics.get('target')
                pct = (in_period / target * 100) if target and target > 0 else None
                emp_count = gp1_metrics.get('employee_count', 0)
                st.metric(
                    label="In-Period (KPI)",
                    value=f"${in_period:,.0f}",
                    delta=f"{pct:.0f}% of target" if pct else None,
                    delta_color="off",
                    help=f"Estimated GP1 backlog with ETD in period. Only from {emp_count} employees with GP1 KPI assigned."
                )
            
            with col_m3:
                target = gp1_metrics.get('target')
                emp_count = gp1_metrics.get('employee_count', 0)
                if target and target > 0:
                    st.metric(
                        label="Target",
                        value=f"${target:,.0f}",
                        delta=f"{emp_count} people",
                        delta_color="off",
                        help=f"Sum of prorated GP1 targets from {emp_count} employees with GP1 KPI"
                    )
                else:
                    st.metric(label="Target", value="N/A", delta="No KPI assigned", delta_color="off")
            
            with col_m4:
                forecast = gp1_metrics.get('forecast')
                achievement = gp1_metrics.get('forecast_achievement')
                emp_count = gp1_metrics.get('employee_count', 0)
                if forecast is not None:
                    delta_color = "normal" if achievement and achievement >= 100 else "inverse"
                    st.metric(
                        label="Forecast (KPI)",
                        value=f"${forecast:,.0f}",
                        delta=f"{achievement:.0f}% of target" if achievement else None,
                        delta_color=delta_color if achievement else "off",
                        help=f"Invoiced + In-Period Backlog (estimated). Only from {emp_count} employees with GP1 KPI."
                    )
                else:
                    st.metric(label="Forecast (KPI)", value="N/A", delta_color="off")
            
            with col_m5:
                gap = gp1_metrics.get('gap')
                gap_pct = gp1_metrics.get('gap_percent')
                if gap is not None:
                    label = "Surplus ✅" if gap >= 0 else "GAP ⚠️"
                    delta_color = "normal" if gap >= 0 else "inverse"
                    st.metric(
                        label=label,
                        value=f"${gap:+,.0f}",
                        delta=f"{gap_pct:+.1f}%" if gap_pct else None,
                        delta_color=delta_color,
                        help="Forecast - Target. Positive = ahead, Negative = behind."
                    )
                else:
                    st.metric(label="GAP", value="N/A", delta_color="off")
            
            # Charts row
            col_bf1, col_bf2 = st.columns(2)
            with col_bf1:
                forecast_chart = SalespersonCharts.build_forecast_waterfall_chart(
                    backlog_metrics=chart_backlog_metrics,
                    metric='gp1',
                    title="GP1 Forecast vs Target"
                )
                st.altair_chart(forecast_chart, use_container_width=True)
            with col_bf2:
                gap_chart = SalespersonCharts.build_gap_analysis_chart(
                    backlog_metrics=chart_backlog_metrics,
                    metrics_to_show=['gp1'],
                    title="GP1: Target vs Forecast"
                )
                st.altair_chart(gap_chart, use_container_width=True)
        
        st.divider()
    else:
        # Historical period - show info message with detailed explanation
        st.info(f"""
        📅 **Forecast not available for historical periods**
        
        End date ({active_filters['end_date'].strftime('%Y-%m-%d')}) is in the past.
        Forecast is only meaningful when end date >= today.
        
        💡 **Tip:** To view Forecast, adjust End Date to today or a future date.
        """)
        st.divider()
    
    # Top customers/brands with metric tabs and help
    col_tc_header, col_tc_help = st.columns([6, 1])
    with col_tc_header:
        st.subheader("🏆 Top Customers & Brands Analysis")
    with col_tc_help:
        with st.popover("ℹ️ Help"):
            st.markdown("""
            **🏆 Pareto Analysis (80/20 Rule)**
            
            Shows customers/brands contributing to **80%** of the selected metric.
            
            **Chart Elements:**
            | Element | Description |
            |---------|-------------|
            | Bars | Individual contribution |
            | Line | Cumulative % |
            | 80% line | Pareto threshold |
            
            **Calculation:**
            1. Sort by metric (descending)
            2. Calculate cumulative sum
            3. Show items until 80% reached
            
            **Metrics Available:**
            - **Revenue**: Total sales by customer/brand
            - **Gross Profit**: GP contribution
            - **GP1**: GP1 contribution
            
            **Use Cases:**
            - Identify key accounts
            - Focus sales efforts
            - Risk assessment (concentration)
            """)
    
    ranking_tab1, ranking_tab2, ranking_tab3 = st.tabs(["💰 By Revenue", "📈 By Gross Profit", "📊 By GP1"])
    
    with ranking_tab1:
        col3, col4 = st.columns(2)
        with col3:
            top_customers = metrics_calc.prepare_top_customers_by_metric('revenue', top_percent=0.8)
            if not top_customers.empty:
                chart = SalespersonCharts.build_top_customers_chart(
                    top_df=top_customers, 
                    metric='revenue',
                    title="Top Customers by Revenue"
                )
                st.altair_chart(chart, use_container_width=True)
        with col4:
            top_brands = metrics_calc.prepare_top_brands_by_metric('revenue', top_percent=0.8)
            if not top_brands.empty:
                chart = SalespersonCharts.build_top_brands_chart(
                    top_df=top_brands,
                    metric='revenue',
                    title="Top Brands by Revenue"
                )
                st.altair_chart(chart, use_container_width=True)
    
    with ranking_tab2:
        col3, col4 = st.columns(2)
        with col3:
            top_customers = metrics_calc.prepare_top_customers_by_metric('gross_profit', top_percent=0.8)
            if not top_customers.empty:
                chart = SalespersonCharts.build_top_customers_chart(
                    top_df=top_customers,
                    metric='gross_profit',
                    title="Top Customers by Gross Profit"
                )
                st.altair_chart(chart, use_container_width=True)
        with col4:
            top_brands = metrics_calc.prepare_top_brands_by_metric('gross_profit', top_percent=0.8)
            if not top_brands.empty:
                chart = SalespersonCharts.build_top_brands_chart(
                    top_df=top_brands,
                    metric='gross_profit',
                    title="Top Brands by Gross Profit"
                )
                st.altair_chart(chart, use_container_width=True)
    
    with ranking_tab3:
        col3, col4 = st.columns(2)
        with col3:
            top_customers = metrics_calc.prepare_top_customers_by_metric('gp1', top_percent=0.8)
            if not top_customers.empty:
                chart = SalespersonCharts.build_top_customers_chart(
                    top_df=top_customers,
                    metric='gp1',
                    title="Top Customers by GP1"
                )
                st.altair_chart(chart, use_container_width=True)
        with col4:
            top_brands = metrics_calc.prepare_top_brands_by_metric('gp1', top_percent=0.8)
            if not top_brands.empty:
                chart = SalespersonCharts.build_top_brands_chart(
                    top_df=top_brands,
                    metric='gp1',
                    title="Top Brands by GP1"
                )
                st.altair_chart(chart, use_container_width=True)
    
    st.divider()
    
    # Summary table
    st.subheader("📋 Performance by Salesperson")
    salesperson_summary = metrics_calc.aggregate_by_salesperson()
    
    if not salesperson_summary.empty:
        display_cols = ['sales_name', 'revenue', 'gross_profit', 'gp1', 'gp_percent', 'customers', 'invoices']
        if 'revenue_achievement' in salesperson_summary.columns:
            display_cols.append('revenue_achievement')
        
        display_df = salesperson_summary[[c for c in display_cols if c in salesperson_summary.columns]].copy()
        display_df.columns = ['Salesperson', 'Revenue', 'Gross Profit', 'GP1', 'GP %', 'Customers', 'Invoices'] + \
                            (['Achievement %'] if 'revenue_achievement' in display_cols else [])
        
        st.dataframe(
            display_df.style.format({
                'Revenue': '${:,.0f}',
                'Gross Profit': '${:,.0f}',
                'GP1': '${:,.0f}',
                'GP %': '{:.1f}%',
                'Achievement %': '{:.1f}%'
            } if 'Achievement %' in display_df.columns else {
                'Revenue': '${:,.0f}',
                'Gross Profit': '${:,.0f}',
                'GP1': '${:,.0f}',
                'GP %': '{:.1f}%',
            }),
            use_container_width=True,
            hide_index=True
        )
    
    # ==========================================================================
    # EXPORT REPORT - FRAGMENT (NEW v2.4.0)
    # Runs independently - no page reload when generating
    # ==========================================================================
    st.divider()
    export_report_fragment(
        overview_metrics=overview_metrics,
        complex_kpis=complex_kpis,
        pipeline_forecast_metrics=pipeline_forecast_metrics,
        yoy_metrics=yoy_metrics,
        in_period_backlog_analysis=in_period_backlog_analysis,
        filter_values=active_filters,
        sales_df=data['sales'],
        total_backlog_df=data['total_backlog'],
        backlog_detail_df=data['backlog_detail'],
        backlog_by_month_df=data['backlog_by_month'],
        targets_df=data['targets'],
        metrics_calc=metrics_calc,
        fragment_key="export"
    )

# =============================================================================
# TAB 2: SALES DETAIL
# =============================================================================

with tab2:
    st.subheader("📋 Sales Transaction Detail")
    
    sales_df = data['sales']
    
    if sales_df.empty:
        st.info("No sales data for selected period")
    else:
        # Sub-tabs for detail views - EACH IS A FRAGMENT
        # Only reruns when filters in that sub-tab change
        detail_tab1, detail_tab2 = st.tabs(["📄 Transaction List", "📊 Pivot Analysis"])
        
        with detail_tab1:
            # =================================================================
            # TRANSACTION LIST - FRAGMENT
            # Only reruns when filters in this section change
            # =================================================================
            sales_detail_fragment(
                sales_df=sales_df,
                overview_metrics=overview_metrics,
                filter_values=active_filters,
                fragment_key="detail"
            )
        
        with detail_tab2:
            # =================================================================
            # PIVOT ANALYSIS - FRAGMENT  
            # Only reruns when pivot config changes
            # =================================================================
            pivot_analysis_fragment(
                sales_df=sales_df,
                fragment_key="pivot"
            )

# =============================================================================
# TAB 3: BACKLOG
# =============================================================================

with tab3:
    col_bl_header, col_bl_help = st.columns([6, 1])
    with col_bl_header:
        st.subheader("📦 Backlog Analysis")
    with col_bl_help:
        with st.popover("ℹ️ Help"):
            st.markdown("""
**📦 Backlog Analysis**

Backlog is a snapshot of ALL pending orders **at current time**.

| Metric | Description |
|--------|-------------|
| **Total Backlog** | All pending orders (not yet invoiced) |
| **Total GP** | Total gross profit from pending orders |
| **In-Period** | Orders with ETD within selected date range |
| **In-Period GP** | Gross profit from in-period orders |
| **On Track** | In-period orders with ETD ≥ today |
| **Overdue** | In-period orders with ETD < today (past due) |

---

**⚠️ Important Notes:**
- Backlog is NOT historical data - always shows current status
- Date range only filters In-Period calculation
- This section shows ALL selected employees (not KPI-filtered)
- Different from Overview's In-Period (KPI) which only includes employees with KPI assigned

---

**📊 Comparison with Overview:**

| Section | In-Period Scope |
|---------|-----------------|
| **Overview** → In-Period (KPI) | Only employees with KPI assigned |
| **Backlog Tab** → In-Period | All selected employees |
            """)
    
    backlog_df = data['backlog_detail']
    
    if backlog_df.empty:
        st.info("📦 No backlog data available")
    else:
        # Show overdue warning at top if applicable
        if in_period_backlog_analysis.get('overdue_warning'):
            st.warning(in_period_backlog_analysis['overdue_warning'])
        
        # Sub-tabs
        backlog_tab1, backlog_tab2, backlog_tab3 = st.tabs(["📋 Backlog List", "📅 By ETD", "⚠️ Risk Analysis"])
        
        with backlog_tab1:
            # =================================================================
            # BACKLOG LIST - FRAGMENT
            # Only reruns when filters in this section change
            # UPDATED v2.2.0: Pass total_backlog_df for accurate summary totals
            # =================================================================
            backlog_list_fragment(
                backlog_df=backlog_df,
                in_period_backlog_analysis=in_period_backlog_analysis,
                total_backlog_df=data['total_backlog'],  # NEW: for accurate totals
                fragment_key="backlog"
            )

        with backlog_tab2:
                    st.markdown("#### 📅 Backlog by ETD Month")
                    
                    # Check if we have backlog data
                    raw_backlog_by_month = data['backlog_by_month']
                    
                    if raw_backlog_by_month.empty:
                        st.info("No backlog data available")
                    else:
                        # Get year summary for info display
                        year_summary = metrics_calc.get_backlog_year_summary(raw_backlog_by_month)
                        unique_years = sorted(raw_backlog_by_month['etd_year'].astype(int).unique())
                        
                        # Show year info
                        if len(unique_years) > 1:
                            st.info(f"📆 Backlog spans {len(unique_years)} years: {', '.join(map(str, unique_years))}")
                        
                        # View mode selector
                        col_view, col_spacer = st.columns([2, 4])
                        with col_view:
                            view_mode = st.radio(
                                "View Mode",
                                options=["Timeline", "Stacked by Month", "Single Year"],
                                horizontal=True,
                                key="backlog_etd_view_mode",
                                help="Timeline: Chronological view | Stacked: Compare months across years | Single Year: One year only"
                            )
                        
                        if view_mode == "Timeline":
                            # =========================================================
                            # TIMELINE VIEW - Chronological across all years
                            # =========================================================
                            backlog_monthly = metrics_calc.prepare_backlog_by_month_multiyear(
                                backlog_by_month_df=raw_backlog_by_month,
                                include_empty_months=False
                            )
                            
                            if not backlog_monthly.empty and backlog_monthly['backlog_revenue'].sum() > 0:
                                chart = SalespersonCharts.build_backlog_by_month_chart_multiyear(
                                    monthly_df=backlog_monthly,
                                    title="",
                                    color_by_year=True,
                                    show_totals_by_year=True
                                )
                                st.altair_chart(chart, use_container_width=True)
                                
                                # Data table with year info
                                display_cols = ['year_month', 'etd_year', 'backlog_revenue', 'backlog_gp', 'order_count']
                                display_cols = [c for c in display_cols if c in backlog_monthly.columns]
                                
                                st.dataframe(
                                    backlog_monthly[display_cols].style.format({
                                        'backlog_revenue': '${:,.0f}',
                                        'backlog_gp': '${:,.0f}',
                                        'order_count': '{:,.0f}'
                                    }),
                                    use_container_width=True,
                                    hide_index=True,
                                    height=400
                                )
                            else:
                                st.info("No backlog data to display")
                        
                        elif view_mode == "Stacked by Month":
                            # =========================================================
                            # STACKED VIEW - Compare same months across years
                            # =========================================================
                            backlog_monthly = metrics_calc.prepare_backlog_by_month_multiyear(
                                backlog_by_month_df=raw_backlog_by_month,
                                include_empty_months=False
                            )
                            
                            if not backlog_monthly.empty and backlog_monthly['backlog_revenue'].sum() > 0:
                                chart = SalespersonCharts.build_backlog_by_month_stacked(
                                    monthly_df=backlog_monthly,
                                    title=""
                                )
                                st.altair_chart(chart, use_container_width=True)
                                
                                # Pivot table: months as rows, years as columns
                                pivot_df = backlog_monthly.pivot_table(
                                    index='etd_month',
                                    columns='etd_year',
                                    values='backlog_revenue',
                                    aggfunc='sum',
                                    fill_value=0
                                )
                                # Reorder months
                                pivot_df = pivot_df.reindex(MONTH_ORDER)
                                pivot_df = pivot_df.dropna(how='all')
                                
                                # Add total column
                                pivot_df['Total'] = pivot_df.sum(axis=1)
                                
                                st.dataframe(
                                    pivot_df.style.format('${:,.0f}'),
                                    use_container_width=True
                                )
                            else:
                                st.info("No backlog data to display")
                        
                        else:  # Single Year
                            # =========================================================
                            # SINGLE YEAR VIEW - Original behavior
                            # =========================================================
                            col_year, _ = st.columns([2, 4])
                            with col_year:
                                selected_year = st.selectbox(
                                    "Select Year",
                                    options=unique_years,
                                    index=unique_years.index(active_filters['year']) if active_filters['year'] in unique_years else 0,
                                    key="backlog_etd_year_select"
                                )
                            
                            backlog_monthly = metrics_calc.prepare_backlog_by_month(
                                backlog_by_month_df=raw_backlog_by_month,
                                year=selected_year
                            )
                            
                            if not backlog_monthly.empty and backlog_monthly['backlog_revenue'].sum() > 0:
                                chart = SalespersonCharts.build_backlog_by_month_chart(
                                    monthly_df=backlog_monthly,
                                    title=f"Backlog by ETD Month - {selected_year}"
                                )
                                st.altair_chart(chart, use_container_width=True)
                                
                                # Monthly table
                                st.dataframe(
                                    backlog_monthly[['month', 'backlog_revenue', 'backlog_gp', 'order_count']].style.format({
                                        'backlog_revenue': '${:,.0f}',
                                        'backlog_gp': '${:,.0f}',
                                    }),
                                    use_container_width=True,
                                    hide_index=True
                                )
                            else:
                                st.info(f"No backlog data for {selected_year}")


        with backlog_tab3:
            st.markdown("#### ⚠️ Backlog Risk Analysis")
            
            # Calculate risk categories
            today = date.today()
            
            backlog_risk = backlog_df.copy()
            backlog_risk['days_until_etd'] = pd.to_numeric(backlog_risk['days_until_etd'], errors='coerce')
            
            # Categorize
            overdue = backlog_risk[backlog_risk['days_until_etd'] < 0]
            this_week = backlog_risk[(backlog_risk['days_until_etd'] >= 0) & (backlog_risk['days_until_etd'] <= 7)]
            this_month = backlog_risk[(backlog_risk['days_until_etd'] > 7) & (backlog_risk['days_until_etd'] <= 30)]
            on_track = backlog_risk[backlog_risk['days_until_etd'] > 30]
            
            # Display risk summary
            col_r1, col_r2, col_r3, col_r4 = st.columns(4)
            
            with col_r1:
                overdue_value = overdue['backlog_sales_by_split_usd'].sum()
                st.metric(
                    "🔴 Overdue",
                    f"${overdue_value:,.0f}",
                    delta=f"{len(overdue)} orders",
                    delta_color="inverse"
                )
            
            with col_r2:
                week_value = this_week['backlog_sales_by_split_usd'].sum()
                st.metric(
                    "🟠 This Week",
                    f"${week_value:,.0f}",
                    delta=f"{len(this_week)} orders",
                    delta_color="off"
                )
            
            with col_r3:
                month_value = this_month['backlog_sales_by_split_usd'].sum()
                st.metric(
                    "🟡 This Month",
                    f"${month_value:,.0f}",
                    delta=f"{len(this_month)} orders",
                    delta_color="off"
                )
            
            with col_r4:
                track_value = on_track['backlog_sales_by_split_usd'].sum()
                st.metric(
                    "🟢 On Track",
                    f"${track_value:,.0f}",
                    delta=f"{len(on_track)} orders",
                    delta_color="normal"
                )
            
            st.divider()
            
            # Show overdue details - UPDATED: Synchronized format with Sales/Backlog list
            if not overdue.empty:
                st.markdown("##### 🔴 Overdue Orders (ETD Passed)")
                
                # Create formatted columns
                overdue_display = overdue.copy()
                
                # Format Product as "pt_code | Name | Package size"
                def format_product_display(row):
                    parts = []
                    if pd.notna(row.get('pt_code')) and row.get('pt_code'):
                        parts.append(str(row['pt_code']))
                    if pd.notna(row.get('product_pn')) and row.get('product_pn'):
                        parts.append(str(row['product_pn']))
                    if pd.notna(row.get('package_size')) and row.get('package_size'):
                        parts.append(str(row['package_size']))
                    return ' | '.join(parts) if parts else str(row.get('product_pn', 'N/A'))
                
                overdue_display['product_display'] = overdue_display.apply(format_product_display, axis=1)
                
                # Format OC with Customer PO
                def format_oc_po(row):
                    oc = str(row.get('oc_number', '')) if pd.notna(row.get('oc_number')) else ''
                    po = str(row.get('customer_po_number', '')) if pd.notna(row.get('customer_po_number')) else ''
                    if oc and po:
                        return f"{oc}\n(PO: {po})"
                    elif oc:
                        return oc
                    elif po:
                        return f"(PO: {po})"
                    return ''
                
                overdue_display['oc_po_display'] = overdue_display.apply(format_oc_po, axis=1)
                overdue_display['days_overdue'] = overdue_display['days_until_etd'].abs()
                
                # Select columns for display
                display_cols = ['oc_po_display', 'etd', 'customer', 'product_display', 'brand',
                               'backlog_sales_by_split_usd', 'backlog_gp_by_split_usd', 
                               'days_overdue', 'pending_type', 'sales_name']
                available_cols = [c for c in display_cols if c in overdue_display.columns]
                
                display_df = overdue_display[available_cols].sort_values(
                    'backlog_sales_by_split_usd', ascending=False
                ).head(50).copy()
                
                # Column configuration
                column_config = {
                    'oc_po_display': st.column_config.TextColumn(
                        "OC / PO",
                        help="Order Confirmation and Customer PO",
                        width="medium"
                    ),
                    'etd': st.column_config.DateColumn(
                        "ETD",
                        help="Estimated time of departure (PASSED)"
                    ),
                    'customer': st.column_config.TextColumn(
                        "Customer",
                        help="Customer name",
                        width="medium"
                    ),
                    'product_display': st.column_config.TextColumn(
                        "Product",
                        help="Product: PT Code | Name | Package Size",
                        width="large"
                    ),
                    'brand': st.column_config.TextColumn(
                        "Brand",
                        help="Product brand/manufacturer"
                    ),
                    'backlog_sales_by_split_usd': st.column_config.NumberColumn(
                        "Amount",
                        help="Backlog amount (split-adjusted)",
                        format="$%.0f"
                    ),
                    'backlog_gp_by_split_usd': st.column_config.NumberColumn(
                        "GP",
                        help="Backlog gross profit (split-adjusted)",
                        format="$%.0f"
                    ),
                    'days_overdue': st.column_config.NumberColumn(
                        "Days Overdue",
                        help="Number of days past ETD"
                    ),
                    'pending_type': st.column_config.TextColumn(
                        "Status",
                        help="Both Pending / Delivery Pending / Invoice Pending"
                    ),
                    'sales_name': st.column_config.TextColumn(
                        "Salesperson",
                        help="Salesperson receiving credit"
                    ),
                }
                
                st.dataframe(
                    display_df,
                    column_config=column_config,
                    use_container_width=True,
                    hide_index=True,
                    height=400
                )

# =============================================================================
# TAB 4: KPI & TARGETS
# =============================================================================

with tab4:
    st.subheader("🎯 KPI & Targets")
    
    targets_df = data['targets']
    
    if targets_df.empty:
        st.info("No KPI assignments found for selected salespeople")
    else:
        # Sub-tabs
        kpi_tab1, kpi_tab2, kpi_tab3 = st.tabs(["📊 My KPIs", "📈 Progress", "🏆 Ranking"])
        
        with kpi_tab1:
            st.markdown("#### 📊 KPI Assignments")
            
            # Group by salesperson
            for sales_id in targets_df['employee_id'].unique():
                sales_targets = targets_df[targets_df['employee_id'] == sales_id]
                sales_name = sales_targets['employee_name'].iloc[0]
                
                with st.expander(f"👤 {sales_name}", expanded=True):
                    kpi_display = sales_targets[['kpi_name', 'annual_target_value', 
                                                 'monthly_target_value', 'quarterly_target_value',
                                                 'unit_of_measure', 'weight_numeric']].copy()
                    kpi_display.columns = ['KPI', 'Annual Target', 'Monthly', 'Quarterly', 'Unit', 'Weight %']
                    
                    st.dataframe(kpi_display, use_container_width=True, hide_index=True)
        
        with kpi_tab2:
            st.markdown("#### 📈 KPI Progress")
            
            # =================================================================
            # EXPLANATORY NOTE - NEW v2.4.0
            # =================================================================
            with st.expander("ℹ️ How KPI Progress is calculated", expanded=False):
                st.markdown(f"""
                **📐 Calculation Method**
                
                Achievement % is calculated using **Prorated Target** based on the selected period type:
                
                | Period Type | Target Proration |
                |-------------|------------------|
                | **YTD** | Annual Target × (Elapsed Months / 12) |
                | **QTD** | Annual Target / 4 |
                | **MTD** | Annual Target / 12 |
                | **Custom** | Annual Target (full year) |
                
                **Current Settings:** {active_filters['period_type']} for {active_filters['year']}
                
                **📊 Why Prorated?**
                
                Using prorated targets allows fair comparison:
                - In June (YTD), achieving 50% of annual target = 100% achievement
                - This is consistent with how **Overall Achievement** is calculated
                
                **👥 Employee Filtering**
                
                Each KPI only counts actuals from employees who have that specific KPI target assigned.
                This ensures accurate achievement measurement when viewing multiple salespeople.
                """)
            
            # =================================================================
            # DYNAMIC KPI Progress - Show ALL assigned KPIs
            # FIXED v2.4.0: 
            # 1. Use prorated target instead of annual target for achievement
            # 2. Complex KPIs now filter by employees with target
            # =================================================================
            
            # Map KPI names to column names in sales_df
            kpi_column_map = {
                'revenue': 'sales_by_split_usd',
                'gross_profit': 'gross_profit_by_split_usd',
                'gross_profit_1': 'gp1_by_split_usd',
            }
            
            # Complex KPIs that need special handling (query fresh for each)
            complex_kpi_names = ['num_new_customers', 'num_new_products', 'new_business_revenue']
            
            # Display name mapping for better UI
            kpi_display_names = {
                'revenue': 'Revenue',
                'gross_profit': 'Gross Profit',
                'gross_profit_1': 'GP1',
                'num_new_customers': 'New Customers',
                'num_new_products': 'New Products',
                'new_business_revenue': 'New Business Revenue',
                'num_new_projects': 'New Projects',
            }
            
            # KPIs that should show currency format
            currency_kpis = ['revenue', 'gross_profit', 'gross_profit_1', 'new_business_revenue']
            
            # Get unique KPI types from targets
            kpi_progress = []
            sales_df = data['sales']
            
            for kpi_name in targets_df['kpi_name'].str.lower().unique():
                # Get employees who have this specific KPI target
                employees_with_target = targets_df[
                    targets_df['kpi_name'].str.lower() == kpi_name
                ]['employee_id'].unique().tolist()
                
                # Get target for this KPI (sum of all employees with this target)
                kpi_target = targets_df[
                    targets_df['kpi_name'].str.lower() == kpi_name
                ]['annual_target_value_numeric'].sum()
                
                if kpi_target <= 0:
                    continue
                
                # Calculate actual value - ONLY from employees who have this KPI target
                if kpi_name in kpi_column_map:
                    # For sales-based KPIs: filter sales_df by employees with target
                    col_name = kpi_column_map[kpi_name]
                    if not sales_df.empty and col_name in sales_df.columns:
                        filtered_sales = sales_df[sales_df['sales_id'].isin(employees_with_target)]
                        actual = filtered_sales[col_name].sum() if not filtered_sales.empty else 0
                    else:
                        actual = 0
                elif kpi_name in complex_kpi_names:
                    # =============================================================
                    # FIXED v2.4.0: Query complex KPIs filtered by employees with target
                    # Instead of using pre-calculated values from all selected employees,
                    # we now query fresh with only the employees who have this KPI target
                    # =============================================================
                    actual = queries.calculate_complex_kpi_value(
                        kpi_name=kpi_name,
                        start_date=active_filters['start_date'],
                        end_date=active_filters['end_date'],
                        employee_ids=employees_with_target
                    )
                else:
                    actual = 0
                
                # Get display name
                display_name = kpi_display_names.get(kpi_name, kpi_name.replace('_', ' ').title())
                
                # Get prorated target
                prorated_target = metrics_calc._get_prorated_target(kpi_name, active_filters['period_type'], active_filters['year'])
                if prorated_target is None:
                    prorated_target = kpi_target  # Fallback to annual
                
                # =============================================================
                # FIXED v2.4.0: Use prorated_target instead of kpi_target
                # This makes Achievement % consistent with Overall Achievement
                # =============================================================
                achievement = (actual / prorated_target * 100) if prorated_target and prorated_target > 0 else 0
                
                kpi_progress.append({
                    'kpi_name': kpi_name,
                    'KPI': display_name,
                    'Actual': actual,
                    'Target (Annual)': kpi_target,
                    'Target (Prorated)': prorated_target,
                    'Achievement %': achievement,
                    'is_currency': kpi_name in currency_kpis,
                    'employee_count': len(employees_with_target)
                })
            
            if kpi_progress:
                # Sort by KPI name for consistent ordering
                kpi_progress.sort(key=lambda x: x['KPI'])
                
                # Display with progress bars
                for row in kpi_progress:
                    col_k1, col_k2 = st.columns([1, 3])
                    
                    with col_k1:
                        st.markdown(f"**{row['KPI']}**")
                        achievement = row['Achievement %']
                        if achievement >= 100:
                            st.success(f"✅ {achievement:.1f}%")
                        elif achievement >= 80:
                            st.warning(f"🟡 {achievement:.1f}%")
                        else:
                            st.error(f"🔴 {achievement:.1f}%")
                    
                    with col_k2:
                        st.progress(min(achievement / 100, 1.0))
                        
                        # =============================================================
                        # FIXED v2.4.0: Show prorated target in caption (not annual)
                        # =============================================================
                        if row['is_currency']:
                            st.caption(
                                f"${row['Actual']:,.0f} / ${row['Target (Prorated)']:,.0f} prorated "
                                f"(${row['Target (Annual)']:,.0f} annual) • {row['employee_count']} people"
                            )
                        else:
                            st.caption(
                                f"{row['Actual']:.1f} / {row['Target (Prorated)']:,.0f} prorated "
                                f"({row['Target (Annual)']:,.0f} annual) • {row['employee_count']} people"
                            )
            else:
                st.info("No KPI targets assigned for selected salespeople")
        
        with kpi_tab3:
            st.markdown("#### 🏆 Team Ranking")
            
            # Only show if multiple salespeople
            salesperson_summary = metrics_calc.aggregate_by_salesperson()
            
            if len(salesperson_summary) > 1:
                # --- Ranking Criteria Selector ---
                ranking_options = {
                    'Revenue': 'revenue',
                    'Gross Profit': 'gross_profit',
                    'GP1': 'gp1',
                    'GP %': 'gp_percent',
                    'KPI Achievement %': 'kpi_achievement'
                }
                
                selected_ranking = st.selectbox(
                    "📊 Rank by",
                    options=list(ranking_options.keys()),
                    index=4,  # Default: KPI Achievement %
                    key="ranking_criteria"
                )
                
                sort_col = ranking_options[selected_ranking]
                
                # --- Prepare data with GP1% ---
                ranking_df = salesperson_summary.copy()
                
                # Calculate GP1%
                ranking_df['gp1_percent'] = (
                    ranking_df['gp1'] / ranking_df['revenue'] * 100
                ).round(2).fillna(0)
                
                # Calculate KPI Achievement (weighted average of revenue & GP achievement)
                if 'revenue_achievement' in ranking_df.columns and 'gp_achievement' in ranking_df.columns:
                    ranking_df['kpi_achievement'] = ranking_df.apply(
                        lambda row: (
                            (row['revenue_achievement'] + row['gp_achievement']) / 2
                            if row['revenue_achievement'] > 0 and row['gp_achievement'] > 0
                            else row['revenue_achievement'] if row['revenue_achievement'] > 0
                            else row['gp_achievement'] if row['gp_achievement'] > 0
                            else 0
                        ),
                        axis=1
                    ).round(1)
                elif 'revenue_achievement' in ranking_df.columns:
                    ranking_df['kpi_achievement'] = ranking_df['revenue_achievement']
                elif 'gp_achievement' in ranking_df.columns:
                    ranking_df['kpi_achievement'] = ranking_df['gp_achievement']
                else:
                    ranking_df['kpi_achievement'] = 0
                
                # --- Sort by selected criteria ---
                ranking_df = ranking_df.sort_values(sort_col, ascending=False).reset_index(drop=True)
                ranking_df.index = ranking_df.index + 1  # Start from 1
                
                # Add rank emoji
                def get_rank_emoji(rank):
                    if rank == 1: return "🥇"
                    elif rank == 2: return "🥈"
                    elif rank == 3: return "🥉"
                    else: return f"#{rank}"
                
                ranking_df.insert(0, 'Rank', ranking_df.index.map(get_rank_emoji))
                
                # --- Select display columns ---
                display_cols = ['Rank', 'sales_name', 'revenue', 'gross_profit', 'gp1', 'gp_percent', 'gp1_percent', 'customers']
                
                # Add KPI Achievement if available
                if 'kpi_achievement' in ranking_df.columns and ranking_df['kpi_achievement'].sum() > 0:
                    display_cols.append('kpi_achievement')
                
                # Filter to available columns only
                display_cols = [c for c in display_cols if c in ranking_df.columns]
                ranking_df = ranking_df[display_cols]
                
                # Rename columns for display
                column_rename = {
                    'sales_name': 'Salesperson',
                    'revenue': 'Revenue',
                    'gross_profit': 'Gross Profit',
                    'gp1': 'GP1',
                    'gp_percent': 'GP %',
                    'gp1_percent': 'GP1 %',
                    'customers': 'Customers',
                    'kpi_achievement': 'Achievement %'
                }
                ranking_df = ranking_df.rename(columns=column_rename)
                
                # --- Format & Display ---
                format_dict = {
                    'Revenue': '${:,.0f}',
                    'Gross Profit': '${:,.0f}',
                    'GP1': '${:,.0f}',
                    'GP %': '{:.1f}%',
                    'GP1 %': '{:.1f}%',
                }
                
                if 'Achievement %' in ranking_df.columns:
                    format_dict['Achievement %'] = '{:.1f}%'
                
                # Highlight the sort column
                sort_col_display = selected_ranking if selected_ranking != 'KPI Achievement %' else 'Achievement %'
                
                def highlight_sort_column(col):
                    if col.name == sort_col_display:
                        return ['background-color: #fff3cd'] * len(col)
                    return [''] * len(col)
                
                st.dataframe(
                    ranking_df.style
                        .format(format_dict)
                        .apply(highlight_sort_column),
                    use_container_width=True,
                    hide_index=True
                )
                
                # Show ranking info
                st.caption(f"📌 Ranked by **{selected_ranking}** (highest first)")
                
            else:
                st.info("Need multiple salespeople to show ranking")

# =============================================================================
# TAB 5: SETUP
# =============================================================================

with tab5:
    st.subheader("⚙️ Setup & Reference")
    
    # Sub-tabs
    setup_tab1, setup_tab2, setup_tab3 = st.tabs(["👥 Sales Split", "📋 My Customers", "📦 My Products"])
    
    with setup_tab1:
        st.markdown("#### 👥 Sales Split Assignments")
        
        sales_split_df = data['sales_split']
        
        if sales_split_df.empty:
            st.info("No sales split data available")
        else:
            # Filter options
            col_sp1, col_sp2 = st.columns(2)
            with col_sp1:
                split_status = st.selectbox("Status", ['All', 'Active', 'Expired'], key="split_status")
            with col_sp2:
                split_sales = st.selectbox("Salesperson", 
                                          ['All'] + sorted(sales_split_df['sales_name'].dropna().unique().tolist()),
                                          key="split_sales")
            
            filtered_split = sales_split_df.copy()
            
            # Filter by effective period status
            if split_status in ['Active', 'Expired']:
                today_str = date.today().strftime('%Y-%m-%d')
                if split_status == 'Active':
                    filtered_split = filtered_split[
                        filtered_split['effective_period'].apply(
                            lambda x: _is_period_active(x, today_str)
                        )
                    ]
                elif split_status == 'Expired':
                    filtered_split = filtered_split[
                        filtered_split['effective_period'].apply(
                            lambda x: _is_period_expired(x, today_str)
                        )
                    ]
            
            # Filter by salesperson
            if split_sales != 'All':
                filtered_split = filtered_split[filtered_split['sales_name'] == split_sales]
            
            # Show record count
            st.caption(f"📊 Showing {len(filtered_split):,} split assignments")
            
            # Display
            split_display_cols = [c for c in ['customer', 'product_pn', 'split_percentage', 
                                              'effective_period', 'approval_status', 'sales_name'] 
                                 if c in filtered_split.columns]
            
            if split_display_cols:
                st.dataframe(
                    filtered_split[split_display_cols].head(200),
                    use_container_width=True,
                    hide_index=True,
                    height=400
                )
    
    with setup_tab2:
        st.markdown("#### 📋 Customer Portfolio")
        
        sales_df = data['sales']
        
        if not sales_df.empty:
            # Aggregate by customer
            customer_portfolio = sales_df.groupby(['customer_id', 'customer']).agg({
                'sales_by_split_usd': 'sum',
                'gross_profit_by_split_usd': 'sum',
                'inv_number': pd.Series.nunique,
                'inv_date': 'max'
            }).reset_index()
            
            customer_portfolio.columns = ['ID', 'Customer', 'Revenue', 'GP', 'Invoices', 'Last Invoice']
            customer_portfolio['GP %'] = (customer_portfolio['GP'] / customer_portfolio['Revenue'] * 100).round(1)
            customer_portfolio = customer_portfolio.sort_values('Revenue', ascending=False)
            
            st.dataframe(
                customer_portfolio.style.format({
                    'Revenue': '${:,.0f}',
                    'GP': '${:,.0f}',
                    'GP %': '{:.1f}%'
                }),
                use_container_width=True,
                hide_index=True,
                height=400
            )
        else:
            st.info("No customer data available")
    
    with setup_tab3:
        st.markdown("#### 📦 Product Portfolio")
        
        sales_df = data['sales']
        
        if not sales_df.empty:
            # Aggregate by brand
            brand_portfolio = sales_df.groupby('brand').agg({
                'sales_by_split_usd': 'sum',
                'gross_profit_by_split_usd': 'sum',
                'product_pn': pd.Series.nunique,
                'customer_id': pd.Series.nunique
            }).reset_index()
            
            brand_portfolio.columns = ['Brand', 'Revenue', 'GP', 'Products', 'Customers']
            brand_portfolio['GP %'] = (brand_portfolio['GP'] / brand_portfolio['Revenue'] * 100).round(1)
            brand_portfolio = brand_portfolio.sort_values('Revenue', ascending=False)
            
            st.dataframe(
                brand_portfolio.style.format({
                    'Revenue': '${:,.0f}',
                    'GP': '${:,.0f}',
                    'GP %': '{:.1f}%'
                }),
                use_container_width=True,
                hide_index=True,
                height=400
            )
        else:
            st.info("No product data available")

# =============================================================================
# FOOTER
# =============================================================================

st.divider()
st.caption(
    f"Generated by Prostech BI Dashboard | "
    f"User: {st.session_state.get('user_fullname', 'Unknown')} | "
    f"Access: {access.get_access_level().title()}"
)