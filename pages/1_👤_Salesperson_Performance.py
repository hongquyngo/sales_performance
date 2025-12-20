# pages/1_👤_Salesperson_Performance.py
"""
👤 Salesperson Performance Dashboard (Tabbed Version)

5 Tabs:
1. Overview - KPI summary, charts, trends
2. Sales Detail - Transaction list, pivot analysis
3. Backlog - Backlog detail, ETD analysis, risk
4. KPI & Targets - KPI assignments, progress, ranking
5. Setup - Sales split, customer/product portfolio

Version: 2.5.0

CHANGELOG:
- v2.5.0: ENHANCED Pipeline & Forecast section
          - Added 3 tabs: Revenue, Gross Profit, GP1
          - Added Target column (prorated) with employee count
          - Each metric filters by employees with that specific KPI target
          - GP1 backlog estimated using GP1/GP ratio from invoiced data
          - Added detailed Help tooltip explaining calculation for multiple salespeople
          - Uses calculate_pipeline_forecast_metrics() for accurate KPI-filtered logic
- v2.4.0: FIXED KPI Progress calculation inconsistency
          - Bug: Achievement % used annual target while Overall used prorated target
          - Fix: KPI Progress now uses prorated target (consistent with Overall Achievement)
          - Fix: Complex KPIs (New Customers, New Products, New Business Revenue) now
                 correctly filter actuals by employees who have that specific KPI target
          - Added explanatory note about KPI Progress calculation method
          - Caption now shows prorated target instead of annual target
- v2.3.0: FIXED KPI Progress logic when multiple salespeople selected
          - Each KPI now only counts actual from employees who have that specific KPI target
          - Example: GP Achievement only includes GP from employees with GP target assigned
          - Added employee count display in KPI progress caption
          - Team Ranking now supports multiple sort criteria:
            Revenue / GP / GP1 / GP% / KPI Achievement %
          - Default ranking changed to KPI Achievement %
          - Added GP1 and GP1% columns to ranking table
          - Highlight sort column with yellow background
- v2.2.0: Added Period Type radio buttons in sidebar
          - YTD/QTD/MTD: Auto-calculate dates for current year
          - Custom: Manual date selection
          - KPI targets prorate based on period type
- v2.1.0: Improved filters with MultiSelect + Excluded option
          - All filters now support multi-selection
          - Added "Excl" checkbox to exclude selected values instead of include
          - Added filter summary display showing active filters
          - Consistent filter UI across Sales Detail and Backlog tabs
- v2.0.0: Initial tabbed version
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
    SalespersonExport,
    PERIOD_TYPES,
    MONTH_ORDER,
)
from utils.salesperson_performance.filters import (
    analyze_period,
    render_multiselect_filter,
    apply_multiselect_filter,
    render_text_search_filter,
    apply_text_search_filter,
    render_number_filter,
    apply_number_filter,
    FilterResult,
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

def load_all_data_once() -> dict:
    """
    Load data based on user's access control.
    
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
    
    # Load data for reasonable date range (last 3 years + current year)
    current_year = date.today().year
    start_date = date(current_year - 2, 1, 1)  # 3 years of data
    end_date = date(current_year, 12, 31)
    
    # Progress bar with status
    progress_bar = st.progress(0, text=f"🔄 Loading {load_msg}...")
    
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
        for yr in range(current_year - 2, current_year + 1):
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
        progress_bar.progress(80, text="📋 Loading backlog details...")
        data['backlog_detail'] = q.get_backlog_detail(
            employee_ids=filter_employee_ids,
            entity_ids=None,
            limit=2000
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
        
        # Complete
        progress_bar.progress(100, text="✅ Data loaded successfully!")
        
    except Exception as e:
        progress_bar.empty()
        st.error(f"❌ Error loading data: {str(e)}")
        st.stop()
    
    # Clear progress bar after short delay
    time.sleep(0.5)
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
# CACHING LOGIC - Load once, filter client-side
# =============================================================================

# Initialize session state
if 'raw_cached_data' not in st.session_state:
    st.session_state.raw_cached_data = None

# Add Refresh button in sidebar
with st.sidebar:
    st.divider()
    col_r1, col_r2 = st.columns([1, 1])
    with col_r1:
        if st.button("🔄 Refresh Data", use_container_width=True, help="Reload data from database"):
            st.session_state.raw_cached_data = None
            st.rerun()
    with col_r2:
        if st.session_state.raw_cached_data and '_loaded_at' in st.session_state.raw_cached_data:
            loaded_at = st.session_state.raw_cached_data['_loaded_at']
            st.caption(f"📅 {loaded_at.strftime('%H:%M')}")

# Load data if not cached
if st.session_state.raw_cached_data is None:
    raw_data = load_all_data_once()
    st.session_state.raw_cached_data = raw_data
else:
    raw_data = st.session_state.raw_cached_data

# =============================================================================
# APPLY CLIENT-SIDE FILTERING (Instant - no DB query)
# =============================================================================

data = filter_data_client_side(
    raw_data=raw_data,
    filter_values=filter_values
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
    period_type=filter_values['period_type'],
    year=filter_values['year']
)

# FIXED v1.3.0: Query new_business fresh with correct date range
# new_business is aggregated data without date column, cannot filter client-side
fresh_new_business_df = queries.get_new_business_revenue(
    start_date=filter_values['start_date'],
    end_date=filter_values['end_date'],
    employee_ids=filter_values['employee_ids']
)

# NEW v1.5.0: Query new_business detail for combo-level display in popover
fresh_new_business_detail_df = queries.get_new_business_detail(
    start_date=filter_values['start_date'],
    end_date=filter_values['end_date'],
    employee_ids=filter_values['employee_ids']
)

complex_kpis = metrics_calc.calculate_complex_kpis(
    new_customers_df=data['new_customers'],
    new_products_df=data['new_products'],
    new_business_df=fresh_new_business_df  # Use fresh data instead of cached
)

backlog_metrics = metrics_calc.calculate_backlog_metrics(
    total_backlog_df=data['total_backlog'],
    in_period_backlog_df=data['in_period_backlog'],
    period_type=filter_values['period_type'],
    year=filter_values['year'],
    start_date=filter_values['start_date'],
    end_date=filter_values['end_date']
)

# NEW v2.5.0: Calculate Pipeline & Forecast with KPI-filtered logic
# This ensures each metric (Revenue/GP/GP1) only includes data from
# employees who have that specific KPI target assigned
pipeline_forecast_metrics = metrics_calc.calculate_pipeline_forecast_metrics(
    total_backlog_df=data['total_backlog'],
    in_period_backlog_df=data['in_period_backlog'],
    backlog_detail_df=data['backlog_detail'],  # Needed for employee filtering
    period_type=filter_values['period_type'],
    year=filter_values['year'],
    start_date=filter_values['start_date'],
    end_date=filter_values['end_date']
)

# Analyze in-period backlog for overdue detection
in_period_backlog_analysis = metrics_calc.analyze_in_period_backlog(
    backlog_detail_df=data['backlog_detail'],
    start_date=filter_values['start_date'],
    end_date=filter_values['end_date']
)

# Get period context for display logic
period_context = backlog_metrics.get('period_context', {})

# =============================================================================
# ANALYZE PERIOD TYPE
# =============================================================================

period_info = analyze_period(filter_values)

# YoY comparison (only for single-year periods)
yoy_metrics = None
if filter_values['compare_yoy'] and not period_info['is_multi_year']:
    previous_sales_df = queries.get_previous_year_data(
        start_date=filter_values['start_date'],
        end_date=filter_values['end_date'],
        employee_ids=filter_values['employee_ids'],
        entity_ids=filter_values['entity_ids'] if filter_values['entity_ids'] else None
    )
    
    if not previous_sales_df.empty:
        prev_metrics_calc = SalespersonMetrics(previous_sales_df, None)
        prev_overview = prev_metrics_calc.calculate_overview_metrics(
            period_type=filter_values['period_type'],
            year=filter_values['year'] - 1
        )
        yoy_metrics = metrics_calc.calculate_yoy_comparison(overview_metrics, prev_overview)

# Overall KPI Achievement (weighted average)
overall_achievement = metrics_calc.calculate_overall_kpi_achievement(
    overview_metrics=overview_metrics,
    complex_kpis=complex_kpis,
    period_type=filter_values['period_type'],
    year=filter_values['year']
)

# =============================================================================
# PAGE HEADER
# =============================================================================

st.title("👤 Salesperson Performance")
filter_summary = filters_ui.get_filter_summary(filter_values)
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
    # NOTE: show_backlog=False because we render Pipeline & Forecast separately below
    SalespersonCharts.render_kpi_cards(
        metrics=overview_metrics,
        yoy_metrics=yoy_metrics,
        complex_kpis=complex_kpis,
        backlog_metrics=None,  # v2.5.0: Don't show old backlog section
        overall_achievement=overall_achievement,
        show_complex=True,
        show_backlog=False,  # v2.5.0: Disable old backlog in KPI cards
        # NEW v1.2.0: Pass detail dataframes for popup buttons
        new_customers_df=data['new_customers'],
        new_products_df=data['new_products'],
        new_business_df=fresh_new_business_df,
        # NEW v1.5.0: Pass combo detail for New Business popup
        new_business_detail_df=fresh_new_business_detail_df
    )
    
    # NEW v2.5.0: Render Pipeline & Forecast section with tabs (Revenue/GP/GP1)
    # This uses calculate_pipeline_forecast_metrics() which filters data
    # by employees with corresponding KPI target
    if period_info['show_backlog'] and pipeline_forecast_metrics:
        SalespersonCharts.render_pipeline_forecast_section(
            pipeline_metrics=pipeline_forecast_metrics,
            show_forecast=period_context.get('show_forecast', True)
        )
    
    st.divider()
    
    # ==========================================================================
    # MONTHLY TREND + CUMULATIVE - WITH DRILL-DOWN FILTERS
    # ==========================================================================
    col_trend_header, col_trend_help = st.columns([6, 1])
    with col_trend_header:
        st.subheader("📊 Monthly Trend & Cumulative")
    with col_trend_help:
        with st.popover("ℹ️"):
            st.markdown("""
            **Filter by Customer/Brand/Product** to drill-down into specific segments.
            
            Use **Excl** checkbox to exclude selected items instead of filtering to them.
            """)
    
    # --- Drill-down filters ---
    col_tf1, col_tf2, col_tf3 = st.columns(3)
    
    with col_tf1:
        trend_customer_options = sorted(data['sales']['customer'].dropna().unique().tolist()) if not data['sales'].empty else []
        trend_customer_filter = render_multiselect_filter(
            label="Customer",
            options=trend_customer_options,
            key="trend_customer",
            placeholder="All customers..."
        )
    
    with col_tf2:
        trend_brand_options = sorted(data['sales']['brand'].dropna().unique().tolist()) if not data['sales'].empty else []
        trend_brand_filter = render_multiselect_filter(
            label="Brand",
            options=trend_brand_options,
            key="trend_brand",
            placeholder="All brands..."
        )
    
    with col_tf3:
        trend_product_options = sorted(data['sales']['product_pn'].dropna().unique().tolist())[:100] if not data['sales'].empty else []
        trend_product_filter = render_multiselect_filter(
            label="Product",
            options=trend_product_options,
            key="trend_product",
            placeholder="All products..."
        )
    
    # Apply filters to sales data for this section
    trend_sales_df = data['sales'].copy() if not data['sales'].empty else pd.DataFrame()
    trend_sales_df = apply_multiselect_filter(trend_sales_df, 'customer', trend_customer_filter)
    trend_sales_df = apply_multiselect_filter(trend_sales_df, 'brand', trend_brand_filter)
    trend_sales_df = apply_multiselect_filter(trend_sales_df, 'product_pn', trend_product_filter)
    
    # Show filter summary
    trend_active_filters = []
    if trend_customer_filter.is_active:
        mode = "excl" if trend_customer_filter.excluded else "incl"
        trend_active_filters.append(f"Customer: {len(trend_customer_filter.selected)} ({mode})")
    if trend_brand_filter.is_active:
        mode = "excl" if trend_brand_filter.excluded else "incl"
        trend_active_filters.append(f"Brand: {len(trend_brand_filter.selected)} ({mode})")
    if trend_product_filter.is_active:
        mode = "excl" if trend_product_filter.excluded else "incl"
        trend_active_filters.append(f"Product: {len(trend_product_filter.selected)} ({mode})")
    
    if trend_active_filters:
        st.caption(f"🔍 Filters: {' | '.join(trend_active_filters)}")
    
    # Calculate monthly summary with filtered data
    trend_metrics_calc = SalespersonMetrics(trend_sales_df, data['targets'])
    monthly_summary = trend_metrics_calc.prepare_monthly_summary()
    
    # Monthly charts
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("##### 📊 Monthly Trend")
        monthly_chart = SalespersonCharts.build_monthly_trend_chart(
            monthly_df=monthly_summary,
            show_gp1=False,
            title=""
        )
        st.altair_chart(monthly_chart, use_container_width=True)
    
    with col2:
        st.markdown("##### 📈 Cumulative Performance")
        cumulative_chart = SalespersonCharts.build_cumulative_chart(
            monthly_df=monthly_summary,
            title=""
        )
        st.altair_chart(cumulative_chart, use_container_width=True)
    
    # ==========================================================================
    # YEAR COMPARISON SECTION
    # Single-year: YoY Comparison (current vs previous year)
    # Multi-year: Multi-Year Comparison (all years in period)
    # ==========================================================================
    
    st.divider()
    
    # --- Header with help ---
    col_yc_header, col_yc_help = st.columns([6, 1])
    with col_yc_header:
        st.subheader("📊 Year-over-Year Comparison")
    with col_yc_help:
        with st.popover("ℹ️"):
            st.markdown("""
            **Filter by Customer/Brand/Product** to compare YoY performance for specific segments.
            
            Use **Excl** checkbox to exclude selected items instead of filtering to them.
            """)
    
    # --- Drill-down filters for YoY section ---
    col_yf1, col_yf2, col_yf3 = st.columns(3)
    
    with col_yf1:
        yoy_customer_options = sorted(data['sales']['customer'].dropna().unique().tolist()) if not data['sales'].empty else []
        yoy_customer_filter = render_multiselect_filter(
            label="Customer",
            options=yoy_customer_options,
            key="yoy_customer",
            placeholder="All customers..."
        )
    
    with col_yf2:
        yoy_brand_options = sorted(data['sales']['brand'].dropna().unique().tolist()) if not data['sales'].empty else []
        yoy_brand_filter = render_multiselect_filter(
            label="Brand",
            options=yoy_brand_options,
            key="yoy_brand",
            placeholder="All brands..."
        )
    
    with col_yf3:
        yoy_product_options = sorted(data['sales']['product_pn'].dropna().unique().tolist())[:100] if not data['sales'].empty else []
        yoy_product_filter = render_multiselect_filter(
            label="Product",
            options=yoy_product_options,
            key="yoy_product",
            placeholder="All products..."
        )
    
    # Apply filters to sales data for YoY section
    yoy_sales_df = data['sales'].copy() if not data['sales'].empty else pd.DataFrame()
    yoy_sales_df = apply_multiselect_filter(yoy_sales_df, 'customer', yoy_customer_filter)
    yoy_sales_df = apply_multiselect_filter(yoy_sales_df, 'brand', yoy_brand_filter)
    yoy_sales_df = apply_multiselect_filter(yoy_sales_df, 'product_pn', yoy_product_filter)
    
    # Show filter summary
    yoy_active_filters = []
    if yoy_customer_filter.is_active:
        mode = "excl" if yoy_customer_filter.excluded else "incl"
        yoy_active_filters.append(f"Customer: {len(yoy_customer_filter.selected)} ({mode})")
    if yoy_brand_filter.is_active:
        mode = "excl" if yoy_brand_filter.excluded else "incl"
        yoy_active_filters.append(f"Brand: {len(yoy_brand_filter.selected)} ({mode})")
    if yoy_product_filter.is_active:
        mode = "excl" if yoy_product_filter.excluded else "incl"
        yoy_active_filters.append(f"Product: {len(yoy_product_filter.selected)} ({mode})")
    
    if yoy_active_filters:
        st.caption(f"🔍 Filters: {' | '.join(yoy_active_filters)}")
    
    # Get years that actually have sales data (not just from date range)
    if not yoy_sales_df.empty and 'invoice_year' in yoy_sales_df.columns:
        actual_years = sorted(yoy_sales_df['invoice_year'].dropna().unique().astype(int).tolist())
    else:
        actual_years = []
    
    # Decide comparison type based on ACTUAL DATA, not date range
    if len(actual_years) >= 2:
        # =====================================================================
        # MULTI-YEAR COMPARISON (2+ years of actual data)
        # =====================================================================
        years_str = ', '.join(map(str, actual_years))
        st.subheader(f"📊 Multi-Year Comparison ({years_str})")
        st.caption(f"ℹ️ Comparing performance across years with actual data in selected date range.")
        
        # Create 3 tabs for each metric
        my_tab1, my_tab2, my_tab3 = st.tabs(["💰 Revenue", "📈 Gross Profit", "📊 GP1"])
        
        # Tab 1: Revenue
        with my_tab1:
            # Summary table
            summary_df = SalespersonCharts.build_multi_year_summary_table(
                sales_df=yoy_sales_df,
                years=actual_years,
                metric='revenue'
            )
            
            if not summary_df.empty:
                # Display yearly totals
                cols = st.columns(len(actual_years) + 1)
                for idx, (_, row) in enumerate(summary_df.iterrows()):
                    with cols[idx]:
                        st.metric(
                            label=f"{int(row['Year'])} Revenue",
                            value=f"${row['Total']:,.0f}",
                            delta=row['YoY Growth'] if row['YoY Growth'] != '-' else None,
                            delta_color="normal" if row['YoY Growth'] != '-' and '+' in str(row['YoY Growth']) else "inverse" if row['YoY Growth'] != '-' else "off"
                        )
            
            st.divider()
            
            # Charts side by side
            col_c1, col_c2 = st.columns(2)
            with col_c1:
                st.markdown("##### 📊 Monthly Revenue by Year")
                monthly_chart = SalespersonCharts.build_multi_year_monthly_chart(
                    sales_df=yoy_sales_df,
                    years=actual_years,
                    metric='revenue',
                    title=""
                )
                st.altair_chart(monthly_chart, use_container_width=True)
            
            with col_c2:
                st.markdown("##### 📈 Cumulative Revenue by Year")
                cum_chart = SalespersonCharts.build_multi_year_cumulative_chart(
                    sales_df=yoy_sales_df,
                    years=actual_years,
                    metric='revenue',
                    title=""
                )
                st.altair_chart(cum_chart, use_container_width=True)
        
        # Tab 2: Gross Profit
        with my_tab2:
            summary_df = SalespersonCharts.build_multi_year_summary_table(
                sales_df=yoy_sales_df,
                years=actual_years,
                metric='gross_profit'
            )
            
            if not summary_df.empty:
                cols = st.columns(len(actual_years) + 1)
                for idx, (_, row) in enumerate(summary_df.iterrows()):
                    with cols[idx]:
                        st.metric(
                            label=f"{int(row['Year'])} GP",
                            value=f"${row['Total']:,.0f}",
                            delta=row['YoY Growth'] if row['YoY Growth'] != '-' else None,
                            delta_color="normal" if row['YoY Growth'] != '-' and '+' in str(row['YoY Growth']) else "inverse" if row['YoY Growth'] != '-' else "off"
                        )
            
            st.divider()
            
            col_c1, col_c2 = st.columns(2)
            with col_c1:
                st.markdown("##### 📊 Monthly Gross Profit by Year")
                monthly_chart = SalespersonCharts.build_multi_year_monthly_chart(
                    sales_df=yoy_sales_df,
                    years=actual_years,
                    metric='gross_profit',
                    title=""
                )
                st.altair_chart(monthly_chart, use_container_width=True)
            
            with col_c2:
                st.markdown("##### 📈 Cumulative Gross Profit by Year")
                cum_chart = SalespersonCharts.build_multi_year_cumulative_chart(
                    sales_df=yoy_sales_df,
                    years=actual_years,
                    metric='gross_profit',
                    title=""
                )
                st.altair_chart(cum_chart, use_container_width=True)
        
        # Tab 3: GP1
        with my_tab3:
            summary_df = SalespersonCharts.build_multi_year_summary_table(
                sales_df=yoy_sales_df,
                years=actual_years,
                metric='gp1'
            )
            
            if not summary_df.empty:
                cols = st.columns(len(actual_years) + 1)
                for idx, (_, row) in enumerate(summary_df.iterrows()):
                    with cols[idx]:
                        st.metric(
                            label=f"{int(row['Year'])} GP1",
                            value=f"${row['Total']:,.0f}",
                            delta=row['YoY Growth'] if row['YoY Growth'] != '-' else None,
                            delta_color="normal" if row['YoY Growth'] != '-' and '+' in str(row['YoY Growth']) else "inverse" if row['YoY Growth'] != '-' else "off"
                        )
            
            st.divider()
            
            col_c1, col_c2 = st.columns(2)
            with col_c1:
                st.markdown("##### 📊 Monthly GP1 by Year")
                monthly_chart = SalespersonCharts.build_multi_year_monthly_chart(
                    sales_df=yoy_sales_df,
                    years=actual_years,
                    metric='gp1',
                    title=""
                )
                st.altair_chart(monthly_chart, use_container_width=True)
            
            with col_c2:
                st.markdown("##### 📈 Cumulative GP1 by Year")
                cum_chart = SalespersonCharts.build_multi_year_cumulative_chart(
                    sales_df=yoy_sales_df,
                    years=actual_years,
                    metric='gp1',
                    title=""
                )
                st.altair_chart(cum_chart, use_container_width=True)
    
    else:
        # =====================================================================
        # YOY COMPARISON (0 or 1 year of actual data)
        # =====================================================================
        
        # Determine primary year for comparison
        if len(actual_years) == 1:
            primary_year = actual_years[0]
        else:
            primary_year = filter_values['end_date'].year
        
        st.markdown(f"##### 📅 {primary_year} vs {primary_year - 1}")
        
        # Load previous year data
        previous_sales_df = queries.get_previous_year_data(
            start_date=filter_values['start_date'],
            end_date=filter_values['end_date'],
            employee_ids=filter_values['employee_ids'],
            entity_ids=filter_values['entity_ids'] if filter_values['entity_ids'] else None
        )
        
        # Apply same filters to previous year data
        if not previous_sales_df.empty:
            previous_sales_df = apply_multiselect_filter(previous_sales_df, 'customer', yoy_customer_filter)
            previous_sales_df = apply_multiselect_filter(previous_sales_df, 'brand', yoy_brand_filter)
            previous_sales_df = apply_multiselect_filter(previous_sales_df, 'product_pn', yoy_product_filter)
        
        if not previous_sales_df.empty:
            # Create 3 tabs for each metric
            yoy_tab1, yoy_tab2, yoy_tab3 = st.tabs(["💰 Revenue", "📈 Gross Profit", "📊 GP1"])
            
            # Tab 1: Revenue
            with yoy_tab1:
                current_total = yoy_sales_df['sales_by_split_usd'].sum() if not yoy_sales_df.empty else 0
                previous_total = previous_sales_df['sales_by_split_usd'].sum() if not previous_sales_df.empty else 0
                yoy_change = ((current_total - previous_total) / previous_total * 100) if previous_total > 0 else 0
                yoy_abs = current_total - previous_total
                
                col_s1, col_s2, col_s3 = st.columns([2, 2, 1])
                with col_s1:
                    st.metric(
                        label=f"{primary_year} Revenue",
                        value=f"${current_total:,.0f}",
                        delta=f"{yoy_change:+.1f}% YoY",
                        delta_color="normal" if yoy_change >= 0 else "inverse"
                    )
                with col_s2:
                    st.metric(
                        label=f"{primary_year - 1} Revenue",
                        value=f"${previous_total:,.0f}",
                        delta=f"${yoy_abs:+,.0f} difference",
                        delta_color="off"
                    )
                
                st.divider()
                
                col_c1, col_c2 = st.columns(2)
                with col_c1:
                    st.markdown("##### 📊 Monthly Revenue Comparison")
                    yoy_chart = SalespersonCharts.build_yoy_comparison_chart(
                        current_df=yoy_sales_df,
                        previous_df=previous_sales_df,
                        metric='revenue',
                        title=""
                    )
                    st.altair_chart(yoy_chart, use_container_width=True)
                
                with col_c2:
                    st.markdown("##### 📈 Cumulative Revenue")
                    cum_chart = SalespersonCharts.build_cumulative_yoy_chart(
                        current_df=yoy_sales_df,
                        previous_df=previous_sales_df,
                        metric='revenue',
                        title=""
                    )
                    st.altair_chart(cum_chart, use_container_width=True)
            
            # Tab 2: Gross Profit
            with yoy_tab2:
                current_total = yoy_sales_df['gross_profit_by_split_usd'].sum() if not yoy_sales_df.empty else 0
                previous_total = previous_sales_df['gross_profit_by_split_usd'].sum() if not previous_sales_df.empty else 0
                yoy_change = ((current_total - previous_total) / previous_total * 100) if previous_total > 0 else 0
                yoy_abs = current_total - previous_total
                
                col_s1, col_s2, col_s3 = st.columns([2, 2, 1])
                with col_s1:
                    st.metric(
                        label=f"{primary_year} Gross Profit",
                        value=f"${current_total:,.0f}",
                        delta=f"{yoy_change:+.1f}% YoY",
                        delta_color="normal" if yoy_change >= 0 else "inverse"
                    )
                with col_s2:
                    st.metric(
                        label=f"{primary_year - 1} Gross Profit",
                        value=f"${previous_total:,.0f}",
                        delta=f"${yoy_abs:+,.0f} difference",
                        delta_color="off"
                    )
                
                st.divider()
                
                col_c1, col_c2 = st.columns(2)
                with col_c1:
                    st.markdown("##### 📊 Monthly Gross Profit Comparison")
                    yoy_chart = SalespersonCharts.build_yoy_comparison_chart(
                        current_df=yoy_sales_df,
                        previous_df=previous_sales_df,
                        metric='gross_profit',
                        title=""
                    )
                    st.altair_chart(yoy_chart, use_container_width=True)
                
                with col_c2:
                    st.markdown("##### 📈 Cumulative Gross Profit")
                    cum_chart = SalespersonCharts.build_cumulative_yoy_chart(
                        current_df=yoy_sales_df,
                        previous_df=previous_sales_df,
                        metric='gross_profit',
                        title=""
                    )
                    st.altair_chart(cum_chart, use_container_width=True)
            
            # Tab 3: GP1
            with yoy_tab3:
                current_total = yoy_sales_df['gp1_by_split_usd'].sum() if not yoy_sales_df.empty else 0
                previous_total = previous_sales_df['gp1_by_split_usd'].sum() if not previous_sales_df.empty else 0
                yoy_change = ((current_total - previous_total) / previous_total * 100) if previous_total > 0 else 0
                yoy_abs = current_total - previous_total
                
                col_s1, col_s2, col_s3 = st.columns([2, 2, 1])
                with col_s1:
                    st.metric(
                        label=f"{primary_year} GP1",
                        value=f"${current_total:,.0f}",
                        delta=f"{yoy_change:+.1f}% YoY",
                        delta_color="normal" if yoy_change >= 0 else "inverse"
                    )
                with col_s2:
                    st.metric(
                        label=f"{primary_year - 1} GP1",
                        value=f"${previous_total:,.0f}",
                        delta=f"${yoy_abs:+,.0f} difference",
                        delta_color="off"
                    )
                
                st.divider()
                
                col_c1, col_c2 = st.columns(2)
                with col_c1:
                    st.markdown("##### 📊 Monthly GP1 Comparison")
                    yoy_chart = SalespersonCharts.build_yoy_comparison_chart(
                        current_df=yoy_sales_df,
                        previous_df=previous_sales_df,
                        metric='gp1',
                        title=""
                    )
                    st.altair_chart(yoy_chart, use_container_width=True)
                
                with col_c2:
                    st.markdown("##### 📈 Cumulative GP1")
                    cum_chart = SalespersonCharts.build_cumulative_yoy_chart(
                        current_df=yoy_sales_df,
                        previous_df=previous_sales_df,
                        metric='gp1',
                        title=""
                    )
                    st.altair_chart(cum_chart, use_container_width=True)
        else:
            st.info(f"No data available for {primary_year - 1} comparison")
    
    st.divider()
    
    # Forecast section - only show for current/future periods
    if period_context.get('show_forecast', True):
        col_bf_header, col_bf_help = st.columns([6, 1])
        with col_bf_header:
            st.subheader("📦 Backlog & Forecast")
        with col_bf_help:
            with st.popover("ℹ️ Help"):
                st.markdown("""
                **📦 Backlog & Forecast Charts**
                
                **Waterfall Chart (Left):**
                Shows how forecast is built from invoiced + backlog.
                
                ```
                Forecast = Invoiced + In-Period Backlog
                ```
                
                | Component | Description |
                |-----------|-------------|
                | Invoiced | Already shipped & invoiced |
                | In-Period Backlog | Expected to ship in period |
                | Forecast | Total projected |
                | Target | Prorated annual target |
                
                **Bullet Chart (Right):**
                Visual comparison of performance vs target.
                
                | Element | Meaning |
                |---------|---------|
                | Gray bar | Target (prorated) |
                | Cyan bar | Forecast |
                | Blue bar | Already invoiced |
                
                **⚠️ Data Filtered by KPI Assignment:**
                Each tab only shows data from employees who have that specific KPI target assigned.
                This ensures accurate achievement calculations.
                
                **GP1 Estimation:**
                When backlog doesn't have GP1, it's estimated using:
                ```
                Backlog GP1 = Backlog GP × (Sales GP1 / Sales GP)
                ```
                
                **Note:** Forecast only available for current or future periods.
                If end date is in the past, Forecast is not available.
                """)
        
        # Show overdue warning if applicable
        if in_period_backlog_analysis.get('overdue_warning'):
            st.warning(in_period_backlog_analysis['overdue_warning'])
        
        # NEW v2.5.0: Convert pipeline_forecast_metrics to legacy format for chart methods
        # This uses KPI-filtered data (only employees with specific KPI targets)
        chart_backlog_metrics = SalespersonCharts.convert_pipeline_to_backlog_metrics(
            pipeline_forecast_metrics
        )
        
        # Tabs for different metrics
        bf_tab1, bf_tab2, bf_tab3 = st.tabs(["💰 Revenue", "📈 Gross Profit", "📊 GP1"])
        
        with bf_tab1:
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
        
        with bf_tab2:
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
        
        with bf_tab3:
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
        
        End date ({filter_values['end_date'].strftime('%Y-%m-%d')}) is in the past.
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
# =============================================================================
# TAB 2: SALES DETAIL
# =============================================================================

with tab2:
    st.subheader("📋 Sales Transaction Detail")
    
    sales_df = data['sales']
    
    if sales_df.empty:
        st.info("No sales data for selected period")
    else:
        # Sub-tabs for detail views
        detail_tab1, detail_tab2 = st.tabs(["📄 Transaction List", "📊 Pivot Analysis"])
        
        with detail_tab1:
            # =================================================================
            # IMPROVED FILTERS - MultiSelect with Excluded option
            # =================================================================
            col_f1, col_f2, col_f3, col_f4, col_f5 = st.columns(5)
            
            # Customer filter
            with col_f1:
                customer_options = sorted(sales_df['customer'].dropna().unique().tolist())
                customer_filter = render_multiselect_filter(
                    label="Customer",
                    options=customer_options,
                    key="detail_customer",
                    placeholder="All customers..."
                )
            
            # Brand filter
            with col_f2:
                brand_options = sorted(sales_df['brand'].dropna().unique().tolist())
                brand_filter = render_multiselect_filter(
                    label="Brand",
                    options=brand_options,
                    key="detail_brand",
                    placeholder="All brands..."
                )
            
            # Product filter
            with col_f3:
                product_options = sorted(sales_df['product_pn'].dropna().unique().tolist())[:100]
                product_filter = render_multiselect_filter(
                    label="Product",
                    options=product_options,
                    key="detail_product",
                    placeholder="All products..."
                )
            
            # OC# / Customer PO search
            with col_f4:
                oc_po_filter = render_text_search_filter(
                    label="OC# / Customer PO",
                    key="detail_oc_po",
                    placeholder="Search..."
                )
            
            # Min Amount filter
            with col_f5:
                amount_filter = render_number_filter(
                    label="Min Amount ($)",
                    key="detail_min_amount",
                    default_min=0,
                    step=1000
                )
            
            # =================================================================
            # APPLY ALL FILTERS
            # =================================================================
            filtered_df = sales_df.copy()
            
            # Apply multiselect filters
            filtered_df = apply_multiselect_filter(filtered_df, 'customer', customer_filter)
            filtered_df = apply_multiselect_filter(filtered_df, 'brand', brand_filter)
            filtered_df = apply_multiselect_filter(filtered_df, 'product_pn', product_filter)
            
            # Apply text search on multiple columns
            filtered_df = apply_text_search_filter(
                filtered_df, 
                columns=['oc_number', 'customer_po_number'],
                search_result=oc_po_filter
            )
            
            # Apply number filter
            filtered_df = apply_number_filter(filtered_df, 'sales_by_split_usd', amount_filter)
            
            # =================================================================
            # Show filter summary
            # =================================================================
            active_filters = []
            if customer_filter.is_active:
                mode = "excl" if customer_filter.excluded else "incl"
                active_filters.append(f"Customer: {len(customer_filter.selected)} ({mode})")
            if brand_filter.is_active:
                mode = "excl" if brand_filter.excluded else "incl"
                active_filters.append(f"Brand: {len(brand_filter.selected)} ({mode})")
            if product_filter.is_active:
                mode = "excl" if product_filter.excluded else "incl"
                active_filters.append(f"Product: {len(product_filter.selected)} ({mode})")
            if oc_po_filter.is_active:
                mode = "excl" if oc_po_filter.excluded else "incl"
                active_filters.append(f"OC/PO: '{oc_po_filter.query}' ({mode})")
            if amount_filter.is_active:
                mode = "excl" if amount_filter.excluded else "incl"
                active_filters.append(f"Amount: ≥${amount_filter.min_value:,.0f} ({mode})")
            
            if active_filters:
                st.caption(f"🔍 Active filters: {' | '.join(active_filters)}")
            
            # =================================================================
            # Calculate Original (pre-split) values
            # Formula: Original = Split Value / (Split % / 100)
            # Note: GP1 is calculated field, no "original" value exists
            # =================================================================
            filtered_df = filtered_df.copy()
            
            # Avoid division by zero
            split_pct = filtered_df['split_rate_percent'].replace(0, 100) / 100
            
            # Calculate original values (before split) - only Revenue and GP
            filtered_df['total_revenue_usd'] = filtered_df['sales_by_split_usd'] / split_pct
            filtered_df['total_gp_usd'] = filtered_df['gross_profit_by_split_usd'] / split_pct
            
            # =================================================================
            # NEW: Format Product as "pt_code | Name | Package size"
            # =================================================================
            def format_product_display(row):
                parts = []
                if pd.notna(row.get('pt_code')) and row.get('pt_code'):
                    parts.append(str(row['pt_code']))
                if pd.notna(row.get('product_pn')) and row.get('product_pn'):
                    parts.append(str(row['product_pn']))
                if pd.notna(row.get('package_size')) and row.get('package_size'):
                    parts.append(str(row['package_size']))
                return ' | '.join(parts) if parts else str(row.get('product_pn', 'N/A'))
            
            filtered_df['product_display'] = filtered_df.apply(format_product_display, axis=1)
            
            # =================================================================
            # NEW: Format OC with Customer PO
            # Format: OC#\n(PO: xxx)
            # =================================================================
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
            
            filtered_df['oc_po_display'] = filtered_df.apply(format_oc_po, axis=1)
            
            # Display columns - reordered with new formatted columns
            display_columns = [
                'inv_date', 'inv_number', 'oc_po_display', 'customer', 'product_display', 'brand',
                'total_revenue_usd', 'total_gp_usd',  # Original values (Revenue, GP only)
                'split_rate_percent',
                'sales_by_split_usd', 'gross_profit_by_split_usd', 'gp1_by_split_usd',  # Split values
                'sales_name'
            ]
            available_cols = [c for c in display_columns if c in filtered_df.columns]
            
            st.markdown(f"**Showing {len(filtered_df):,} transactions** (of {len(sales_df):,} total)")
            
            # Prepare display dataframe
            display_detail = filtered_df[available_cols].head(500).copy()
            
            # =================================================================
            # Configure columns with tooltips using st.column_config
            # =================================================================
            column_config = {
                'inv_date': st.column_config.DateColumn(
                    "Date",
                    help="Invoice date"
                ),
                'inv_number': st.column_config.TextColumn(
                    "Invoice#",
                    help="Invoice number"
                ),
                'oc_po_display': st.column_config.TextColumn(
                    "OC / PO",
                    help="Order Confirmation number and Customer PO",
                    width="medium"
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
                # Original values (before split)
                'total_revenue_usd': st.column_config.NumberColumn(
                    "Total Revenue",
                    help="💰 ORIGINAL invoice revenue (100% of line item)\n\nThis is the full value BEFORE applying sales split.",
                    format="$%.0f"
                ),
                'total_gp_usd': st.column_config.NumberColumn(
                    "Total GP",
                    help="📈 ORIGINAL gross profit (100% of line item)\n\nFormula: Revenue - COGS\n\nThis is the full GP BEFORE applying sales split.",
                    format="$%.0f"
                ),
                # Split percentage
                'split_rate_percent': st.column_config.NumberColumn(
                    "Split %",
                    help="👥 Sales credit split percentage\n\nThis salesperson receives this % of the total revenue/GP/GP1.\n\n100% = Full credit\n50% = Shared equally with another salesperson",
                    format="%.0f%%"
                ),
                # Split values (after split)
                'sales_by_split_usd': st.column_config.NumberColumn(
                    "Revenue",
                    help="💰 CREDITED revenue for this salesperson\n\n📐 Formula: Total Revenue × Split %\n\nThis is the revenue credited to this salesperson after applying their split percentage.",
                    format="$%.0f"
                ),
                'gross_profit_by_split_usd': st.column_config.NumberColumn(
                    "GP",
                    help="📈 CREDITED gross profit for this salesperson\n\n📐 Formula: Total GP × Split %\n\nThis is the GP credited to this salesperson after applying their split percentage.",
                    format="$%.0f"
                ),
                'gp1_by_split_usd': st.column_config.NumberColumn(
                    "GP1",
                    help="📊 CREDITED GP1 for this salesperson\n\n📐 Formula: (GP - Broker Commission × 1.2) × Split %\n\nGP1 is calculated from GP after deducting commission, then split.",
                    format="$%.0f"
                ),
                'sales_name': st.column_config.TextColumn(
                    "Salesperson",
                    help="Salesperson receiving credit for this transaction"
                ),
            }
            
            # Display table with column configuration
            st.dataframe(
                display_detail,
                column_config=column_config,
                use_container_width=True,
                hide_index=True,
                height=500
            )
            
            # Legend for quick reference
            with st.expander("📖 Column Legend", expanded=False):
                st.markdown("""
                | Column | Description | Formula |
                |--------|-------------|---------|
                | **OC / PO** | Order Confirmation & Customer PO | Combined display |
                | **Product** | PT Code \| Name \| Package Size | Formatted product info |
                | **Total Revenue** | Original invoice amount (100%) | Full line item value |
                | **Total GP** | Original gross profit (100%) | Revenue - COGS |
                | **Split %** | Credit allocation to salesperson | Assigned by sales split rules |
                | **Revenue** | Credited revenue | Total Revenue × Split % |
                | **GP** | Credited gross profit | Total GP × Split % |
                | **GP1** | Credited GP1 | (GP - Broker Commission × 1.2) × Split % |
                
                > 💡 **Note:** GP1 is a calculated field (GP minus commission), so there's no "original" GP1 value.
                
                > 💡 **Tip:** Hover over column headers to see detailed tooltips.
                """)
            
            # Export button
            if st.button("📥 Export to Excel", key="export_detail"):
                exporter = SalespersonExport()
                excel_bytes = exporter.create_report(
                    summary_df=salesperson_summary if 'salesperson_summary' in dir() else pd.DataFrame(),
                    monthly_df=monthly_summary if 'monthly_summary' in dir() else pd.DataFrame(),
                    metrics=overview_metrics,
                    filters=filter_values,
                    detail_df=filtered_df
                )
                st.download_button(
                    label="⬇️ Download",
                    data=excel_bytes,
                    file_name=f"sales_detail_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )
        
        with detail_tab2:
            st.markdown("#### 📊 Pivot Analysis")
            
            # Pivot configuration
            col_p1, col_p2, col_p3 = st.columns(3)
            
            with col_p1:
                row_options = ['customer', 'brand', 'sales_name', 'product_pn', 'legal_entity']
                pivot_rows = st.selectbox("Rows", row_options, index=0, key="pivot_rows")
            
            with col_p2:
                col_options = ['invoice_month', 'brand', 'customer', 'sales_name']
                pivot_cols = st.selectbox("Columns", col_options, index=0, key="pivot_cols")
            
            with col_p3:
                value_options = ['sales_by_split_usd', 'gross_profit_by_split_usd', 'gp1_by_split_usd']
                pivot_values = st.selectbox("Values", value_options, index=1, key="pivot_values",
                                           format_func=lambda x: x.replace('_by_split_usd', '').replace('_', ' ').title())
            
            # Create pivot
            if pivot_rows in sales_df.columns and pivot_cols in sales_df.columns:
                pivot_df = sales_df.pivot_table(
                    values=pivot_values,
                    index=pivot_rows,
                    columns=pivot_cols,
                    aggfunc='sum',
                    fill_value=0
                )
                
                # Add totals
                pivot_df['Total'] = pivot_df.sum(axis=1)
                pivot_df = pivot_df.sort_values('Total', ascending=False)
                
                # Reorder columns (months)
                if pivot_cols == 'invoice_month':
                    month_cols = [m for m in MONTH_ORDER if m in pivot_df.columns]
                    other_cols = [c for c in pivot_df.columns if c not in MONTH_ORDER and c != 'Total']
                    pivot_df = pivot_df[month_cols + other_cols + ['Total']]
                
                st.dataframe(
                    pivot_df.style.format("${:,.0f}").background_gradient(cmap='Blues', subset=['Total']),
                    use_container_width=True,
                    height=500
                )
            else:
                st.warning("Selected columns not available in data")

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
            
            Backlog là snapshot của tất cả orders đang pending **tại thời điểm hiện tại**.
            
            | Metric | Description |
            |--------|-------------|
            | Total Backlog | All pending orders |
            | In-Period | Orders with ETD in date range |
            | Overdue | Orders with ETD already passed |
            
            **⚠️ Note:**
            - Backlog is not historical data
            - Always shows current status
            - Date range only filters In-Period Backlog
            """)
    
    backlog_df = data['backlog_detail']
    
    if backlog_df.empty:
        st.info("📦 No backlog data available")
    else:
        # Show overdue warning at top if applicable
        if in_period_backlog_analysis.get('overdue_warning'):
            st.warning(in_period_backlog_analysis['overdue_warning'])
        
        # In-period summary card - UPDATED: Added GP metric
        if in_period_backlog_analysis['total_count'] > 0:
            col_ip1, col_ip2, col_ip3, col_ip4, col_ip5 = st.columns(5)
            with col_ip1:
                st.metric(
                    "📅 In-Period Backlog",
                    f"${in_period_backlog_analysis['total_value']:,.0f}",
                    help="Orders with ETD in selected date range"
                )
            with col_ip2:
                st.metric(
                    "📈 In-Period GP",
                    f"${in_period_backlog_analysis.get('total_gp', 0):,.0f}",
                    help="Gross profit from in-period backlog"
                )
            with col_ip3:
                st.metric(
                    "✅ On Track",
                    f"${in_period_backlog_analysis['on_track_value']:,.0f}",
                    f"{in_period_backlog_analysis['on_track_count']} orders"
                )
            with col_ip4:
                st.metric(
                    "⚠️ Overdue",
                    f"${in_period_backlog_analysis['overdue_value']:,.0f}",
                    f"{in_period_backlog_analysis['overdue_count']} orders",
                    delta_color="inverse" if in_period_backlog_analysis['overdue_count'] > 0 else "off"
                )
            with col_ip5:
                st.metric(
                    "📊 Status",
                    in_period_backlog_analysis['status'].upper(),
                    help="healthy: no overdue, has_overdue: some orders past due"
                )
            
            st.divider()
        
        # Sub-tabs
        backlog_tab1, backlog_tab2, backlog_tab3 = st.tabs(["📋 Backlog List", "📅 By ETD", "⚠️ Risk Analysis"])
        
        with backlog_tab1:
            # Summary cards - Total backlog (not filtered by date)
            col_s1, col_s2, col_s3, col_s4 = st.columns(4)
            
            total_backlog_value = backlog_df['backlog_sales_by_split_usd'].sum()
            total_backlog_gp = backlog_df['backlog_gp_by_split_usd'].sum()
            total_orders = backlog_df['oc_number'].nunique()
            total_customers = backlog_df['customer_id'].nunique()
            
            with col_s1:
                st.metric("💰 Total Backlog", f"${total_backlog_value:,.0f}", help="All pending orders, not filtered by date")
            with col_s2:
                st.metric("📈 Backlog GP", f"${total_backlog_gp:,.0f}")
            with col_s3:
                st.metric("📦 Orders", f"{total_orders:,}")
            with col_s4:
                st.metric("👥 Customers", f"{total_customers:,}")
            
            st.divider()
            
            # =================================================================
            # IMPROVED FILTERS - MultiSelect with Excluded option
            # =================================================================
            col_bf1, col_bf2, col_bf3, col_bf4, col_bf5 = st.columns(5)
            
            # Customer filter
            with col_bf1:
                bl_customer_options = sorted(backlog_df['customer'].dropna().unique().tolist())
                bl_customer_filter = render_multiselect_filter(
                    label="Customer",
                    options=bl_customer_options,
                    key="bl_customer",
                    placeholder="All customers..."
                )
            
            # Brand filter
            with col_bf2:
                bl_brand_options = sorted(backlog_df['brand'].dropna().unique().tolist())
                bl_brand_filter = render_multiselect_filter(
                    label="Brand",
                    options=bl_brand_options,
                    key="bl_brand",
                    placeholder="All brands..."
                )
            
            # Product filter
            with col_bf3:
                bl_product_options = sorted(backlog_df['product_pn'].dropna().unique().tolist())[:100]
                bl_product_filter = render_multiselect_filter(
                    label="Product",
                    options=bl_product_options,
                    key="bl_product",
                    placeholder="All products..."
                )
            
            # OC# / Customer PO search
            with col_bf4:
                bl_oc_po_filter = render_text_search_filter(
                    label="OC# / Customer PO",
                    key="bl_oc_po",
                    placeholder="Search..."
                )
            
            # Status filter
            with col_bf5:
                bl_status_options = backlog_df['pending_type'].dropna().unique().tolist()
                bl_status_filter = render_multiselect_filter(
                    label="Status",
                    options=bl_status_options,
                    key="bl_status",
                    placeholder="All statuses..."
                )
            
            # =================================================================
            # APPLY ALL FILTERS
            # =================================================================
            filtered_backlog = backlog_df.copy()
            
            # Apply multiselect filters
            filtered_backlog = apply_multiselect_filter(filtered_backlog, 'customer', bl_customer_filter)
            filtered_backlog = apply_multiselect_filter(filtered_backlog, 'brand', bl_brand_filter)
            filtered_backlog = apply_multiselect_filter(filtered_backlog, 'product_pn', bl_product_filter)
            filtered_backlog = apply_multiselect_filter(filtered_backlog, 'pending_type', bl_status_filter)
            
            # Apply text search on multiple columns
            filtered_backlog = apply_text_search_filter(
                filtered_backlog, 
                columns=['oc_number', 'customer_po_number'] if 'customer_po_number' in backlog_df.columns else ['oc_number'],
                search_result=bl_oc_po_filter
            )
            
            # =================================================================
            # Show filter summary
            # =================================================================
            active_bl_filters = []
            if bl_customer_filter.is_active:
                mode = "excl" if bl_customer_filter.excluded else "incl"
                active_bl_filters.append(f"Customer: {len(bl_customer_filter.selected)} ({mode})")
            if bl_brand_filter.is_active:
                mode = "excl" if bl_brand_filter.excluded else "incl"
                active_bl_filters.append(f"Brand: {len(bl_brand_filter.selected)} ({mode})")
            if bl_product_filter.is_active:
                mode = "excl" if bl_product_filter.excluded else "incl"
                active_bl_filters.append(f"Product: {len(bl_product_filter.selected)} ({mode})")
            if bl_oc_po_filter.is_active:
                mode = "excl" if bl_oc_po_filter.excluded else "incl"
                active_bl_filters.append(f"OC/PO: '{bl_oc_po_filter.query}' ({mode})")
            if bl_status_filter.is_active:
                mode = "excl" if bl_status_filter.excluded else "incl"
                active_bl_filters.append(f"Status: {len(bl_status_filter.selected)} ({mode})")
            
            if active_bl_filters:
                st.caption(f"🔍 Active filters: {' | '.join(active_bl_filters)}")
            
            # =================================================================
            # NEW: Format Product as "pt_code | Name | Package size"
            # =================================================================
            def format_product_display(row):
                parts = []
                if pd.notna(row.get('pt_code')) and row.get('pt_code'):
                    parts.append(str(row['pt_code']))
                if pd.notna(row.get('product_pn')) and row.get('product_pn'):
                    parts.append(str(row['product_pn']))
                if pd.notna(row.get('package_size')) and row.get('package_size'):
                    parts.append(str(row['package_size']))
                return ' | '.join(parts) if parts else str(row.get('product_pn', 'N/A'))
            
            filtered_backlog = filtered_backlog.copy()
            filtered_backlog['product_display'] = filtered_backlog.apply(format_product_display, axis=1)
            
            # =================================================================
            # NEW: Format OC with Customer PO
            # =================================================================
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
            
            filtered_backlog['oc_po_display'] = filtered_backlog.apply(format_oc_po, axis=1)
            
            st.markdown(f"**Showing {len(filtered_backlog):,} backlog items** (of {len(backlog_df):,} total)")
            
            # Display with column configuration
            backlog_display_cols = ['oc_po_display', 'oc_date', 'etd', 'customer', 'product_display', 'brand',
                                   'backlog_sales_by_split_usd', 'backlog_gp_by_split_usd', 
                                   'days_until_etd', 'pending_type', 'sales_name']
            available_bl_cols = [c for c in backlog_display_cols if c in filtered_backlog.columns]
            
            display_bl = filtered_backlog[available_bl_cols].head(200).copy()
            
            # Column configuration
            column_config = {
                'oc_po_display': st.column_config.TextColumn(
                    "OC / PO",
                    help="Order Confirmation and Customer PO",
                    width="medium"
                ),
                'oc_date': st.column_config.DateColumn(
                    "OC Date",
                    help="Order confirmation date"
                ),
                'etd': st.column_config.DateColumn(
                    "ETD",
                    help="Estimated time of departure"
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
                'days_until_etd': st.column_config.NumberColumn(
                    "Days to ETD",
                    help="Days until ETD (negative = overdue)"
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
                display_bl,
                column_config=column_config,
                use_container_width=True,
                hide_index=True,
                height=400
            )
        
        with backlog_tab2:
            st.markdown("#### 📅 Backlog by ETD Month")
            
            # Prepare monthly backlog
            backlog_monthly = metrics_calc.prepare_backlog_by_month(
                backlog_by_month_df=data['backlog_by_month'],
                year=filter_values['year']
            )
            
            if not backlog_monthly.empty and backlog_monthly['backlog_revenue'].sum() > 0:
                chart = SalespersonCharts.build_backlog_by_month_chart(
                    monthly_df=backlog_monthly,
                    title=""
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
                st.info("No backlog data by month")
        
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
                
                **Current Settings:** {filter_values['period_type']} for {filter_values['year']}
                
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
                        start_date=filter_values['start_date'],
                        end_date=filter_values['end_date'],
                        employee_ids=employees_with_target
                    )
                else:
                    actual = 0
                
                # Get display name
                display_name = kpi_display_names.get(kpi_name, kpi_name.replace('_', ' ').title())
                
                # Get prorated target
                prorated_target = metrics_calc._get_prorated_target(kpi_name, filter_values['period_type'], filter_values['year'])
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