# pages/1_👤_Salesperson_Performance.py
"""
👤 Salesperson Performance Dashboard (Tabbed Version)

5 Tabs:
1. Overview - KPI summary, charts, trends
2. Sales Detail - Transaction list, pivot analysis
3. Backlog - Backlog detail, ETD analysis, risk
4. KPI & Targets - KPI assignments, progress, ranking
5. Setup - Sales split, customer/product portfolio

Version: 2.0.0
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
from utils.salesperson_performance.filters import analyze_period

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
    Load ALL data without any filters.
    This data will be cached and ALL filtering done client-side.
    Only reloads when user clicks Refresh button.
    """
    q = SalespersonQueries(AccessControl(
        st.session_state.get('user_role', 'viewer'),
        st.session_state.get('employee_id')
    ))
    
    # Load data for reasonable date range (last 3 years + current year)
    current_year = date.today().year
    start_date = date(current_year - 2, 1, 1)  # 3 years of data
    end_date = date(current_year, 12, 31)
    
    # Progress bar with status
    progress_bar = st.progress(0, text="🔄 Initializing...")
    
    data = {}
    
    try:
        # Step 1: Sales data - NO filters
        progress_bar.progress(10, text="📊 Loading all sales data...")
        data['sales'] = q.get_sales_data(
            start_date=start_date,
            end_date=end_date,
            employee_ids=None,
            entity_ids=None
        )
        
        # Step 2: KPI targets - ALL years, ALL employees
        progress_bar.progress(25, text="🎯 Loading all KPI targets...")
        # Load targets for multiple years
        targets_list = []
        for yr in range(current_year - 2, current_year + 1):
            t = q.get_kpi_targets(year=yr, employee_ids=None)
            if not t.empty:
                targets_list.append(t)
        data['targets'] = pd.concat(targets_list, ignore_index=True) if targets_list else pd.DataFrame()
        
        # Step 3: Complex KPIs - NO filters
        progress_bar.progress(40, text="🆕 Loading new business metrics...")
        data['new_customers'] = q.get_new_customers(start_date, end_date, None)
        data['new_products'] = q.get_new_products(start_date, end_date, None)
        data['new_business'] = q.get_new_business_revenue(start_date, end_date, None)
        
        # Step 4: Backlog data - NO filters
        progress_bar.progress(60, text="📦 Loading all backlog data...")
        data['total_backlog'] = q.get_backlog_data(
            employee_ids=None,
            entity_ids=None
        )
        data['in_period_backlog'] = q.get_backlog_in_period(
            start_date=start_date,
            end_date=end_date,
            employee_ids=None,
            entity_ids=None
        )
        data['backlog_by_month'] = q.get_backlog_by_month(
            employee_ids=None,
            entity_ids=None
        )
        
        # Step 5: Backlog detail - NO filters
        progress_bar.progress(80, text="📋 Loading backlog details...")
        data['backlog_detail'] = q.get_backlog_detail(
            employee_ids=None,
            entity_ids=None,
            limit=2000
        )
        
        # Step 6: Sales split data - NO filter
        progress_bar.progress(95, text="👥 Loading sales split data...")
        data['sales_split'] = q.get_sales_split_data(employee_ids=None)
        
        # Step 7: Clean all dataframes
        for key in data:
            if isinstance(data[key], pd.DataFrame) and not data[key].empty:
                data[key] = _clean_dataframe_for_display(data[key])
        
        # Store load timestamp
        data['_loaded_at'] = datetime.now()
        
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
    # KPI Cards
    SalespersonCharts.render_kpi_cards(
        metrics=overview_metrics,
        yoy_metrics=yoy_metrics,
        complex_kpis=complex_kpis,
        backlog_metrics=backlog_metrics if period_info['show_backlog'] else None,
        overall_achievement=overall_achievement,
        show_complex=True,
        show_backlog=period_info['show_backlog']
    )
    
    st.divider()
    
    # Monthly charts
    monthly_summary = metrics_calc.prepare_monthly_summary()
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("📊 Monthly Trend")
        monthly_chart = SalespersonCharts.build_monthly_trend_chart(
            monthly_df=monthly_summary,
            show_gp1=False,
            title=""
        )
        st.altair_chart(monthly_chart, use_container_width=True)
    
    with col2:
        st.subheader("📈 Cumulative Performance")
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
    
    # Get years that actually have sales data (not just from date range)
    if not data['sales'].empty and 'invoice_year' in data['sales'].columns:
        actual_years = sorted(data['sales']['invoice_year'].dropna().unique().astype(int).tolist())
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
                sales_df=data['sales'],
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
                    sales_df=data['sales'],
                    years=actual_years,
                    metric='revenue',
                    title=""
                )
                st.altair_chart(monthly_chart, use_container_width=True)
            
            with col_c2:
                st.markdown("##### 📈 Cumulative Revenue by Year")
                cum_chart = SalespersonCharts.build_multi_year_cumulative_chart(
                    sales_df=data['sales'],
                    years=actual_years,
                    metric='revenue',
                    title=""
                )
                st.altair_chart(cum_chart, use_container_width=True)
        
        # Tab 2: Gross Profit
        with my_tab2:
            summary_df = SalespersonCharts.build_multi_year_summary_table(
                sales_df=data['sales'],
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
                    sales_df=data['sales'],
                    years=actual_years,
                    metric='gross_profit',
                    title=""
                )
                st.altair_chart(monthly_chart, use_container_width=True)
            
            with col_c2:
                st.markdown("##### 📈 Cumulative Gross Profit by Year")
                cum_chart = SalespersonCharts.build_multi_year_cumulative_chart(
                    sales_df=data['sales'],
                    years=actual_years,
                    metric='gross_profit',
                    title=""
                )
                st.altair_chart(cum_chart, use_container_width=True)
        
        # Tab 3: GP1
        with my_tab3:
            summary_df = SalespersonCharts.build_multi_year_summary_table(
                sales_df=data['sales'],
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
                    sales_df=data['sales'],
                    years=actual_years,
                    metric='gp1',
                    title=""
                )
                st.altair_chart(monthly_chart, use_container_width=True)
            
            with col_c2:
                st.markdown("##### 📈 Cumulative GP1 by Year")
                cum_chart = SalespersonCharts.build_multi_year_cumulative_chart(
                    sales_df=data['sales'],
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
        
        col_yoy_header, col_yoy_help = st.columns([6, 1])
        with col_yoy_header:
            st.subheader(f"📊 Year-over-Year Comparison ({primary_year} vs {primary_year - 1})")
        with col_yoy_help:
            with st.popover("ℹ️"):
                st.markdown("""
                **Period Matching:**
                - Compares same date range: e.g., YTD 2025 vs YTD 2024
                - Leap year handled: Feb 29 → Feb 28
                """)
        
        # Load previous year data
        previous_sales_df = queries.get_previous_year_data(
            start_date=filter_values['start_date'],
            end_date=filter_values['end_date'],
            employee_ids=filter_values['employee_ids'],
            entity_ids=filter_values['entity_ids'] if filter_values['entity_ids'] else None
        )
        
        if not previous_sales_df.empty:
            # Create 3 tabs for each metric
            yoy_tab1, yoy_tab2, yoy_tab3 = st.tabs(["💰 Revenue", "📈 Gross Profit", "📊 GP1"])
            
            # Tab 1: Revenue
            with yoy_tab1:
                current_total = data['sales']['sales_by_split_usd'].sum() if not data['sales'].empty else 0
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
                        current_df=data['sales'],
                        previous_df=previous_sales_df,
                        metric='revenue',
                        title=""
                    )
                    st.altair_chart(yoy_chart, use_container_width=True)
                
                with col_c2:
                    st.markdown("##### 📈 Cumulative Revenue")
                    cum_chart = SalespersonCharts.build_cumulative_yoy_chart(
                        current_df=data['sales'],
                        previous_df=previous_sales_df,
                        metric='revenue',
                        title=""
                    )
                    st.altair_chart(cum_chart, use_container_width=True)
            
            # Tab 2: Gross Profit
            with yoy_tab2:
                current_total = data['sales']['gross_profit_by_split_usd'].sum() if not data['sales'].empty else 0
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
                        current_df=data['sales'],
                        previous_df=previous_sales_df,
                        metric='gross_profit',
                        title=""
                    )
                    st.altair_chart(yoy_chart, use_container_width=True)
                
                with col_c2:
                    st.markdown("##### 📈 Cumulative Gross Profit")
                    cum_chart = SalespersonCharts.build_cumulative_yoy_chart(
                        current_df=data['sales'],
                        previous_df=previous_sales_df,
                        metric='gross_profit',
                        title=""
                    )
                    st.altair_chart(cum_chart, use_container_width=True)
            
            # Tab 3: GP1
            with yoy_tab3:
                current_total = data['sales']['gp1_by_split_usd'].sum() if not data['sales'].empty else 0
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
                        current_df=data['sales'],
                        previous_df=previous_sales_df,
                        metric='gp1',
                        title=""
                    )
                    st.altair_chart(yoy_chart, use_container_width=True)
                
                with col_c2:
                    st.markdown("##### 📈 Cumulative GP1")
                    cum_chart = SalespersonCharts.build_cumulative_yoy_chart(
                        current_df=data['sales'],
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
        
        # Tabs for different metrics
        bf_tab1, bf_tab2, bf_tab3 = st.tabs(["💰 Revenue", "📈 Gross Profit", "📊 GP1"])
        
        with bf_tab1:
            col_bf1, col_bf2 = st.columns(2)
            with col_bf1:
                forecast_chart = SalespersonCharts.build_forecast_waterfall_chart(
                    backlog_metrics=backlog_metrics,
                    metric='revenue',
                    title="Revenue Forecast vs Target"
                )
                st.altair_chart(forecast_chart, use_container_width=True)
            with col_bf2:
                gap_chart = SalespersonCharts.build_gap_analysis_chart(
                    backlog_metrics=backlog_metrics,
                    metrics_to_show=['revenue'],
                    title="Revenue: Target vs Forecast"
                )
                st.altair_chart(gap_chart, use_container_width=True)
        
        with bf_tab2:
            col_bf1, col_bf2 = st.columns(2)
            with col_bf1:
                forecast_chart = SalespersonCharts.build_forecast_waterfall_chart(
                    backlog_metrics=backlog_metrics,
                    metric='gp',
                    title="GP Forecast vs Target"
                )
                st.altair_chart(forecast_chart, use_container_width=True)
            with col_bf2:
                gap_chart = SalespersonCharts.build_gap_analysis_chart(
                    backlog_metrics=backlog_metrics,
                    metrics_to_show=['gp'],
                    title="GP: Target vs Forecast"
                )
                st.altair_chart(gap_chart, use_container_width=True)
        
        with bf_tab3:
            col_bf1, col_bf2 = st.columns(2)
            with col_bf1:
                forecast_chart = SalespersonCharts.build_forecast_waterfall_chart(
                    backlog_metrics=backlog_metrics,
                    metric='gp1',
                    title="GP1 Forecast vs Target"
                )
                st.altair_chart(forecast_chart, use_container_width=True)
            with col_bf2:
                gap_chart = SalespersonCharts.build_gap_analysis_chart(
                    backlog_metrics=backlog_metrics,
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
            # Filters row
            col_f1, col_f2, col_f3, col_f4 = st.columns(4)
            
            with col_f1:
                customers = ['All'] + sorted(sales_df['customer'].dropna().unique().tolist())
                selected_customer = st.selectbox("Customer", customers, key="detail_customer")
            
            with col_f2:
                brands = ['All'] + sorted(sales_df['brand'].dropna().unique().tolist())
                selected_brand = st.selectbox("Brand", brands, key="detail_brand")
            
            with col_f3:
                products = ['All'] + sorted(sales_df['product_pn'].dropna().unique().tolist())[:100]
                selected_product = st.selectbox("Product", products, key="detail_product")
            
            with col_f4:
                min_amount = st.number_input("Min Amount ($)", value=0, step=1000, key="detail_min_amount")
            
            # Filter data
            filtered_df = sales_df.copy()
            if selected_customer != 'All':
                filtered_df = filtered_df[filtered_df['customer'] == selected_customer]
            if selected_brand != 'All':
                filtered_df = filtered_df[filtered_df['brand'] == selected_brand]
            if selected_product != 'All':
                filtered_df = filtered_df[filtered_df['product_pn'] == selected_product]
            if min_amount > 0:
                filtered_df = filtered_df[filtered_df['sales_by_split_usd'] >= min_amount]
            
            # Display columns
            display_columns = [
                'inv_date', 'inv_number', 'customer', 'product_pn', 'brand',
                'sales_by_split_usd', 'gross_profit_by_split_usd', 'gp1_by_split_usd',
                'split_rate_percent', 'sales_name'
            ]
            available_cols = [c for c in display_columns if c in filtered_df.columns]
            
            st.markdown(f"**Showing {len(filtered_df):,} transactions**")
            
            # Display table
            display_detail = filtered_df[available_cols].copy()
            display_detail.columns = ['Date', 'Invoice#', 'Customer', 'Product', 'Brand',
                                      'Revenue', 'GP', 'GP1', 'Split %', 'Salesperson'][:len(available_cols)]
            
            st.dataframe(
                display_detail.head(500).style.format({
                    'Revenue': '${:,.0f}',
                    'GP': '${:,.0f}',
                    'GP1': '${:,.0f}',
                    'Split %': '{:.0f}%'
                }),
                use_container_width=True,
                hide_index=True,
                height=500
            )
            
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
        
        # In-period summary card
        if in_period_backlog_analysis['total_count'] > 0:
            col_ip1, col_ip2, col_ip3, col_ip4 = st.columns(4)
            with col_ip1:
                st.metric(
                    "📅 In-Period Backlog",
                    f"${in_period_backlog_analysis['total_value']:,.0f}",
                    help="Orders with ETD in selected date range"
                )
            with col_ip2:
                st.metric(
                    "✅ On Track",
                    f"${in_period_backlog_analysis['on_track_value']:,.0f}",
                    f"{in_period_backlog_analysis['on_track_count']} orders"
                )
            with col_ip3:
                st.metric(
                    "⚠️ Overdue",
                    f"${in_period_backlog_analysis['overdue_value']:,.0f}",
                    f"{in_period_backlog_analysis['overdue_count']} orders",
                    delta_color="inverse" if in_period_backlog_analysis['overdue_count'] > 0 else "off"
                )
            with col_ip4:
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
            
            # Filters
            col_bf1, col_bf2 = st.columns(2)
            with col_bf1:
                backlog_customers = ['All'] + sorted(backlog_df['customer'].dropna().unique().tolist())
                bl_selected_customer = st.selectbox("Customer", backlog_customers, key="bl_customer")
            with col_bf2:
                pending_types = ['All'] + backlog_df['pending_type'].dropna().unique().tolist()
                bl_selected_type = st.selectbox("Status", pending_types, key="bl_type")
            
            # Filter
            filtered_backlog = backlog_df.copy()
            if bl_selected_customer != 'All':
                filtered_backlog = filtered_backlog[filtered_backlog['customer'] == bl_selected_customer]
            if bl_selected_type != 'All':
                filtered_backlog = filtered_backlog[filtered_backlog['pending_type'] == bl_selected_type]
            
            # Display
            backlog_display_cols = ['oc_number', 'oc_date', 'etd', 'customer', 'product_pn', 'brand',
                                   'backlog_sales_by_split_usd', 'backlog_gp_by_split_usd', 
                                   'days_until_etd', 'pending_type', 'sales_name']
            available_bl_cols = [c for c in backlog_display_cols if c in filtered_backlog.columns]
            
            display_bl = filtered_backlog[available_bl_cols].copy()
            display_bl.columns = ['OC#', 'OC Date', 'ETD', 'Customer', 'Product', 'Brand',
                                 'Amount', 'GP', 'Days to ETD', 'Status', 'Salesperson'][:len(available_bl_cols)]
            
            st.dataframe(
                display_bl.head(200).style.format({
                    'Amount': '${:,.0f}',
                    'GP': '${:,.0f}',
                }),
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
            
            # Show overdue details
            if not overdue.empty:
                st.markdown("##### 🔴 Overdue Orders (ETD Passed)")
                overdue_display = overdue[['oc_number', 'etd', 'customer', 'product_pn', 
                                          'backlog_sales_by_split_usd', 'days_until_etd', 'sales_name']].copy()
                overdue_display.columns = ['OC#', 'ETD', 'Customer', 'Product', 'Amount', 'Days Overdue', 'Salesperson']
                overdue_display['Days Overdue'] = overdue_display['Days Overdue'].abs()
                
                st.dataframe(
                    overdue_display.sort_values('Amount', ascending=False).head(20).style.format({
                        'Amount': '${:,.0f}'
                    }),
                    use_container_width=True,
                    hide_index=True
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
            
            # Calculate progress for each KPI type
            kpi_progress = []
            
            # Revenue
            revenue_target = targets_df[targets_df['kpi_name'].str.lower() == 'revenue']['annual_target_value_numeric'].sum()
            revenue_actual = overview_metrics.get('total_revenue', 0)
            if revenue_target > 0:
                kpi_progress.append({
                    'KPI': 'Revenue',
                    'Actual': revenue_actual,
                    'Target (Annual)': revenue_target,
                    'Target (Prorated)': metrics_calc._get_prorated_target('revenue', filter_values['period_type'], filter_values['year']) or 0,
                    'Achievement %': (revenue_actual / revenue_target * 100) if revenue_target else 0
                })
            
            # Gross Profit
            gp_target = targets_df[targets_df['kpi_name'].str.lower() == 'gross_profit']['annual_target_value_numeric'].sum()
            gp_actual = overview_metrics.get('total_gp', 0)
            if gp_target > 0:
                kpi_progress.append({
                    'KPI': 'Gross Profit',
                    'Actual': gp_actual,
                    'Target (Annual)': gp_target,
                    'Target (Prorated)': metrics_calc._get_prorated_target('gross_profit', filter_values['period_type'], filter_values['year']) or 0,
                    'Achievement %': (gp_actual / gp_target * 100) if gp_target else 0
                })
            
            # New Customers
            nc_target = targets_df[targets_df['kpi_name'].str.lower() == 'num_new_customers']['annual_target_value_numeric'].sum()
            nc_actual = complex_kpis.get('new_customer_count', 0)
            if nc_target > 0:
                kpi_progress.append({
                    'KPI': 'New Customers',
                    'Actual': nc_actual,
                    'Target (Annual)': nc_target,
                    'Target (Prorated)': nc_target,
                    'Achievement %': (nc_actual / nc_target * 100) if nc_target else 0
                })
            
            if kpi_progress:
                progress_df = pd.DataFrame(kpi_progress)
                
                # Display with progress bars
                for _, row in progress_df.iterrows():
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
                        if 'Revenue' in row['KPI'] or 'Profit' in row['KPI']:
                            st.caption(f"${row['Actual']:,.0f} / ${row['Target (Prorated)']:,.0f}")
                        else:
                            st.caption(f"{row['Actual']:.1f} / {row['Target (Annual)']:.0f}")
        
        with kpi_tab3:
            st.markdown("#### 🏆 Team Ranking")
            
            # Only show if multiple salespeople
            salesperson_summary = metrics_calc.aggregate_by_salesperson()
            
            if len(salesperson_summary) > 1:
                ranking_df = salesperson_summary[['sales_name', 'revenue', 'gross_profit', 'gp_percent', 'customers']].copy()
                ranking_df = ranking_df.sort_values('gross_profit', ascending=False).reset_index(drop=True)
                ranking_df.index = ranking_df.index + 1  # Start from 1
                
                # Add rank emoji
                def get_rank_emoji(rank):
                    if rank == 1: return "🥇"
                    elif rank == 2: return "🥈"
                    elif rank == 3: return "🥉"
                    else: return f"#{rank}"
                
                ranking_df.insert(0, 'Rank', ranking_df.index.map(get_rank_emoji))
                ranking_df.columns = ['Rank', 'Salesperson', 'Revenue', 'Gross Profit', 'GP %', 'Customers']
                
                st.dataframe(
                    ranking_df.style.format({
                        'Revenue': '${:,.0f}',
                        'Gross Profit': '${:,.0f}',
                        'GP %': '{:.1f}%'
                    }),
                    use_container_width=True,
                    hide_index=True
                )
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