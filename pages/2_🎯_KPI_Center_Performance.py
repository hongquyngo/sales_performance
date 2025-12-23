# pages/2_🎯_KPI_Center_Performance.py
"""
KPI Center Performance Dashboard

A comprehensive dashboard for tracking KPI Center performance metrics.
Features:
- Revenue, GP, GP1 tracking with targets
- Complex KPIs (New Customers, Products, Business Revenue) with popup drill-down
- Pipeline & Forecast with gap analysis
- YoY comparison
- Parent-Child KPI Center rollup
- Backlog risk analysis
- Top Performers / Pareto Analysis
- Excel export

Access: admin, GM, MD, sales_manager only

VERSION: 2.3.1
CHANGELOG:
- v2.3.1: BUGFIX - KPI Center filter not working
          - filter_data_client_side now filters by kpi_center_ids
          - filter_data_client_side now filters by entity_ids
          - Added _calculate_backlog_risk_from_df for client-side recalculation
          - Targets now filtered by both year AND kpi_center_ids
- v2.3.0: Phase 3 - Added Analysis tab with Pareto analysis
          - top_performers_fragment for Customer/Brand/Product analysis
          - 80/20 concentration insights
          - Interactive charts with recommendations
- v2.2.0: Phase 2 enhancements:
          - monthly_trend_fragment now shows target overlay
          - backlog_list_fragment now shows overall vs filtered totals
          - sales_detail_fragment now shows summary cards at top
- v2.0.0: Added complex KPIs popup drill-down (New Customers/Products/Business detail)
          Added backlog risk analysis section
          Added smart data caching (year range expansion)
          Improved refresh button and cache management
          Enhanced help popovers throughout
"""

import logging
from datetime import date, datetime
import time
import pandas as pd
import streamlit as st

# Page config
st.set_page_config(
    page_title="KPI Center Performance",
    page_icon="🎯",
    layout="wide"
)

# Imports
from utils.auth import AuthManager
from utils.db import check_db_connection
from utils.kpi_center_performance import (
    AccessControl,
    KPICenterQueries,
    KPICenterMetrics,
    KPICenterFilters,
    KPICenterCharts,
    KPICenterExport,
    analyze_period,
    ALLOWED_ROLES,
    # Fragments
    monthly_trend_fragment,
    yoy_comparison_fragment,
    sales_detail_fragment,
    pivot_analysis_fragment,
    backlog_list_fragment,
    kpi_center_ranking_fragment,
    top_performers_fragment,  # NEW v2.3.0
    export_report_fragment,
)

from utils.kpi_center_performance.filters import (
    _get_cached_year_range,
    _set_cached_year_range,
    _get_applied_filters,
    _set_applied_filters,
    clear_data_cache,
)

logger = logging.getLogger(__name__)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _clean_dataframe_for_display(df: pd.DataFrame) -> pd.DataFrame:
    """
    Clean dataframe to avoid Arrow serialization errors.
    Fixes mixed type columns.
    """
    if df.empty:
        return df
    
    df_clean = df.copy()
    
    # Columns that should be numeric
    year_columns = ['etd_year', 'oc_year', 'invoice_year', 'year']
    numeric_columns = ['days_until_etd', 'days_since_order', 'split_rate_percent']
    
    for col in year_columns:
        if col in df_clean.columns:
            df_clean[col] = pd.to_numeric(df_clean[col], errors='coerce').fillna(0).astype(int)
    
    for col in numeric_columns:
        if col in df_clean.columns:
            df_clean[col] = pd.to_numeric(df_clean[col], errors='coerce')
    
    return df_clean


# =============================================================================
# AUTHENTICATION & ACCESS CONTROL
# =============================================================================

def check_access():
    """Check authentication and page access."""
    auth = AuthManager()
    
    if not auth.check_session():
        st.warning("⚠️ Please login to access this page")
        st.info("Go to the main page to login")
        st.stop()
    
    # Check database connection
    db_connected, db_error = check_db_connection()
    if not db_connected:
        st.error(f"❌ Database connection failed: {db_error}")
        st.info("Please check your network connection or VPN")
        st.stop()
    
    user_role = st.session_state.get('user_role', '')
    access = AccessControl(user_role)
    
    if not access.can_access_page():
        st.error(access.get_denied_message())
        st.stop()
    
    return access


# =============================================================================
# DATA LOADING WITH SMART CACHING
# =============================================================================

@st.cache_data(ttl=1800)
def load_lookup_data():
    """Load lookup data for filters (cached)."""
    from utils.db import get_db_engine
    from sqlalchemy import text
    
    engine = get_db_engine()
    
    # KPI Center list
    kpi_center_query = """
        SELECT DISTINCT
            kc.id AS kpi_center_id,
            kc.name AS kpi_center_name,
            kc.type AS kpi_type,
            kc.parent_center_id,
            kc.description
        FROM kpi_centers kc
        WHERE kc.delete_flag = 0
        ORDER BY kc.type, kc.name
    """
    kpi_center_df = pd.read_sql(text(kpi_center_query), engine)
    
    # Entity list
    entity_query = """
        SELECT DISTINCT
            legal_entity_id AS entity_id,
            legal_entity AS entity_name
        FROM unified_sales_by_kpi_center_view
        WHERE legal_entity_id IS NOT NULL
        ORDER BY legal_entity
    """
    entity_df = pd.read_sql(text(entity_query), engine)
    
    # Available years
    years_query = """
        SELECT DISTINCT CAST(invoice_year AS SIGNED) AS year
        FROM unified_sales_by_kpi_center_view
        WHERE invoice_year IS NOT NULL
        ORDER BY invoice_year DESC
    """
    years_df = pd.read_sql(text(years_query), engine)
    available_years = years_df['year'].tolist() if not years_df.empty else [datetime.now().year]
    
    return kpi_center_df, entity_df, available_years


def load_data_for_year_range(
    queries: KPICenterQueries,
    start_year: int,
    end_year: int,
    kpi_center_ids: list,
    entity_ids: list = None
) -> dict:
    """
    Load data for specified year range.
    
    SMART CACHING v2.0.0:
    - Only reload when year range expands
    - Caches raw data by year range
    """
    start_date = date(start_year, 1, 1)
    end_date = date(end_year, 12, 31)
    
    # Progress bar
    progress_bar = st.progress(0, text=f"🔄 Loading data ({start_year}-{end_year})...")
    
    data = {}
    
    try:
        # Step 1: Sales data
        progress_bar.progress(10, text="📊 Loading sales data...")
        data['sales_df'] = queries.get_sales_data(
            start_date=start_date,
            end_date=end_date,
            kpi_center_ids=kpi_center_ids,
            entity_ids=entity_ids
        )
        
        # Step 2: KPI Targets
        progress_bar.progress(25, text="🎯 Loading KPI targets...")
        targets_list = []
        for yr in range(start_year, end_year + 1):
            t = queries.get_kpi_targets(year=yr, kpi_center_ids=kpi_center_ids)
            if not t.empty:
                targets_list.append(t)
        data['targets_df'] = pd.concat(targets_list, ignore_index=True) if targets_list else pd.DataFrame()
        
        # Step 3: Backlog data
        progress_bar.progress(40, text="📦 Loading backlog data...")
        data['backlog_summary_df'] = queries.get_backlog_data(
            kpi_center_ids=kpi_center_ids,
            entity_ids=entity_ids
        )
        
        data['backlog_in_period_df'] = queries.get_backlog_in_period(
            start_date=start_date,
            end_date=end_date,
            kpi_center_ids=kpi_center_ids,
            entity_ids=entity_ids
        )
        
        data['backlog_detail_df'] = queries.get_backlog_detail(
            kpi_center_ids=kpi_center_ids,
            entity_ids=entity_ids
        )
        
        data['backlog_by_month_df'] = queries.get_backlog_by_month(
            kpi_center_ids=kpi_center_ids,
            entity_ids=entity_ids
        )
        
        # Step 4: Backlog risk analysis (NEW v2.0.0)
        progress_bar.progress(55, text="⚠️ Analyzing backlog risk...")
        data['backlog_risk'] = queries.get_backlog_risk_analysis(
            kpi_center_ids=kpi_center_ids,
            entity_ids=entity_ids,
            start_date=start_date,
            end_date=end_date
        )
        
        # Step 5: Complex KPIs
        progress_bar.progress(70, text="🆕 Loading new business metrics...")
        data['new_customers_df'] = queries.get_new_customers(
            start_date=start_date,
            end_date=end_date,
            kpi_center_ids=kpi_center_ids,
            entity_ids=entity_ids
        )
        
        data['new_products_df'] = queries.get_new_products(
            start_date=start_date,
            end_date=end_date,
            kpi_center_ids=kpi_center_ids,
            entity_ids=entity_ids
        )
        
        data['new_business_df'] = queries.get_new_business_revenue(
            start_date=start_date,
            end_date=end_date,
            kpi_center_ids=kpi_center_ids,
            entity_ids=entity_ids
        )
        
        # Step 6: Complex KPIs Detail (NEW v2.0.0 - for popup drill-down)
        progress_bar.progress(85, text="📋 Loading detail data...")
        data['new_customers_detail_df'] = queries.get_new_customers_detail(
            start_date=start_date,
            end_date=end_date,
            kpi_center_ids=kpi_center_ids,
            entity_ids=entity_ids
        )
        
        data['new_products_detail_df'] = queries.get_new_products_detail(
            start_date=start_date,
            end_date=end_date,
            kpi_center_ids=kpi_center_ids,
            entity_ids=entity_ids
        )
        
        data['new_business_detail_df'] = queries.get_new_business_detail(
            start_date=start_date,
            end_date=end_date,
            kpi_center_ids=kpi_center_ids,
            entity_ids=entity_ids
        )
        
        # Metadata
        data['_loaded_at'] = datetime.now()
        data['_year_range'] = (start_year, end_year)
        
        # Complete
        progress_bar.progress(100, text="✅ Data loaded successfully!")
        
    except Exception as e:
        progress_bar.empty()
        st.error(f"❌ Error loading data: {str(e)}")
        logger.exception("Error loading data")
        st.stop()
    
    finally:
        time.sleep(0.3)
        progress_bar.empty()
    
    return data


def get_or_load_data(queries: KPICenterQueries, filter_values: dict) -> dict:
    """
    Get data from cache or load if needed.
    Implements smart caching - only reload when year range expands.
    """
    required_start_year = filter_values['start_date'].year
    required_end_year = filter_values['end_date'].year
    
    # Check existing cache
    cached_start, cached_end = _get_cached_year_range()
    
    # Get cached data if exists
    cached_data = st.session_state.get('_kpc_raw_cached_data')
    
    # Determine if reload needed
    need_reload = False
    
    if cached_data is None:
        need_reload = True
        logger.info("No cached data - loading fresh")
    elif cached_start is None or cached_end is None:
        need_reload = True
        logger.info("No cached year range - loading fresh")
    elif required_start_year < cached_start or required_end_year > cached_end:
        need_reload = True
        logger.info(f"Year range expanded: {cached_start}-{cached_end} → {required_start_year}-{required_end_year}")
    
    if need_reload:
        # Load data for required year range (expand to include buffer)
        load_start_year = min(required_start_year, cached_start or required_start_year)
        load_end_year = max(required_end_year, cached_end or required_end_year)
        
        data = load_data_for_year_range(
            queries=queries,
            start_year=load_start_year,
            end_year=load_end_year,
            kpi_center_ids=filter_values.get('kpi_center_ids', []),
            entity_ids=filter_values.get('entity_ids', [])
        )
        
        # Update cache
        st.session_state['_kpc_raw_cached_data'] = data
        _set_cached_year_range(load_start_year, load_end_year)
        
        return data
    
    return cached_data


def filter_data_client_side(raw_data: dict, filter_values: dict) -> dict:
    """
    Filter cached data client-side based on filters.
    Instant - no DB query needed.
    
    FIXED v2.3.1: Added KPI Center and Entity filtering
    """
    start_date = filter_values['start_date']
    end_date = filter_values['end_date']
    exclude_internal = filter_values.get('exclude_internal_revenue', True)
    
    # ═══════════════════════════════════════════════════════════════
    # FIX: Get KPI Center and Entity IDs for filtering
    # ═══════════════════════════════════════════════════════════════
    selected_kpi_center_ids = filter_values.get('kpi_center_ids', [])
    selected_entity_ids = filter_values.get('entity_ids', [])
    
    filtered = {}
    
    for key, value in raw_data.items():
        # Skip metadata
        if key.startswith('_'):
            continue
        
        # Skip non-dataframe values
        if not isinstance(value, pd.DataFrame):
            filtered[key] = value
            continue
        
        if value.empty:
            filtered[key] = value
            continue
        
        df = value.copy()
        
        # ═══════════════════════════════════════════════════════════════
        # FIX: Filter by KPI Center IDs (CRITICAL)
        # ═══════════════════════════════════════════════════════════════
        if selected_kpi_center_ids and 'kpi_center_id' in df.columns:
            df = df[df['kpi_center_id'].isin(selected_kpi_center_ids)]
        
        # ═══════════════════════════════════════════════════════════════
        # FIX: Filter by Entity IDs
        # ═══════════════════════════════════════════════════════════════
        if selected_entity_ids:
            entity_col = None
            if 'legal_entity_id' in df.columns:
                entity_col = 'legal_entity_id'
            elif 'entity_id' in df.columns:
                entity_col = 'entity_id'
            
            if entity_col:
                df = df[df[entity_col].isin(selected_entity_ids)]
        
        # Filter by date range
        date_cols = ['inv_date', 'oc_date', 'first_sale_date']
        for date_col in date_cols:
            if date_col in df.columns:
                df[date_col] = pd.to_datetime(df[date_col], errors='coerce')
                df = df[
                    (df[date_col] >= pd.Timestamp(start_date)) & 
                    (df[date_col] <= pd.Timestamp(end_date))
                ]
                break
        
        # Exclude internal revenue for sales data
        if exclude_internal and key == 'sales_df':
            if 'customer_type' in df.columns:
                df = df[df['customer_type'] != 'Internal']
        
        # Filter targets by year AND kpi_center_ids
        if key == 'targets_df':
            if 'year' in df.columns:
                df = df[df['year'] == filter_values['year']]
            # Also filter targets by selected KPI Centers
            if selected_kpi_center_ids and 'kpi_center_id' in df.columns:
                df = df[df['kpi_center_id'].isin(selected_kpi_center_ids)]
        
        filtered[key] = df
    
    # ═══════════════════════════════════════════════════════════════
    # FIX: Recalculate backlog_risk from filtered backlog data
    # ═══════════════════════════════════════════════════════════════
    backlog_detail_df = filtered.get('backlog_detail_df', pd.DataFrame())
    if not backlog_detail_df.empty:
        filtered['backlog_risk'] = _calculate_backlog_risk_from_df(backlog_detail_df)
    elif 'backlog_risk' in raw_data:
        filtered['backlog_risk'] = raw_data['backlog_risk']
    
    return filtered


def _calculate_backlog_risk_from_df(backlog_df: pd.DataFrame) -> dict:
    """
    Calculate backlog risk metrics from filtered backlog DataFrame.
    NEW v2.3.1: Helper for client-side backlog risk calculation.
    """
    if backlog_df.empty:
        return {
            'overdue_orders': 0, 'overdue_revenue': 0, 'overdue_gp': 0,
            'at_risk_orders': 0, 'at_risk_revenue': 0,
            'total_orders': 0, 'total_backlog': 0,
            'in_period_overdue': 0, 'in_period_overdue_revenue': 0,
            'overdue_percent': 0
        }
    
    df = backlog_df.copy()
    
    # Ensure days_until_etd is numeric
    if 'days_until_etd' in df.columns:
        df['days_until_etd'] = pd.to_numeric(df['days_until_etd'], errors='coerce').fillna(0)
    else:
        df['days_until_etd'] = 0
    
    # Identify revenue column
    rev_col = 'backlog_by_kpi_center_usd' if 'backlog_by_kpi_center_usd' in df.columns else 'total_backlog_usd'
    gp_col = 'backlog_gp_by_kpi_center_usd' if 'backlog_gp_by_kpi_center_usd' in df.columns else 'total_backlog_gp_usd'
    
    if rev_col not in df.columns:
        return {'overdue_orders': 0, 'overdue_revenue': 0, 'total_backlog': 0, 'overdue_percent': 0}
    
    total_backlog = df[rev_col].sum()
    
    # Overdue (days_until_etd < 0)
    overdue_mask = df['days_until_etd'] < 0
    overdue_orders = df[overdue_mask]['oc_number'].nunique() if 'oc_number' in df.columns else overdue_mask.sum()
    overdue_revenue = df.loc[overdue_mask, rev_col].sum()
    overdue_gp = df.loc[overdue_mask, gp_col].sum() if gp_col in df.columns else 0
    
    # At risk (0-7 days)
    at_risk_mask = (df['days_until_etd'] >= 0) & (df['days_until_etd'] <= 7)
    at_risk_orders = df[at_risk_mask]['oc_number'].nunique() if 'oc_number' in df.columns else at_risk_mask.sum()
    at_risk_revenue = df.loc[at_risk_mask, rev_col].sum()
    
    # Totals
    total_orders = df['oc_number'].nunique() if 'oc_number' in df.columns else len(df)
    overdue_percent = (overdue_revenue / total_backlog * 100) if total_backlog > 0 else 0
    
    return {
        'overdue_orders': int(overdue_orders),
        'overdue_revenue': float(overdue_revenue),
        'overdue_gp': float(overdue_gp),
        'at_risk_orders': int(at_risk_orders),
        'at_risk_revenue': float(at_risk_revenue),
        'total_orders': int(total_orders),
        'total_backlog': float(total_backlog),
        'in_period_overdue': int(overdue_orders),
        'in_period_overdue_revenue': float(overdue_revenue),
        'overdue_percent': float(overdue_percent)
    }


def load_yoy_data(queries: KPICenterQueries, filter_values: dict):
    """Load previous year data for YoY comparison."""
    start_date = filter_values['start_date']
    end_date = filter_values['end_date']
    kpi_center_ids = filter_values.get('kpi_center_ids', [])
    entity_ids = filter_values.get('entity_ids', [])
    
    # Previous year same period
    prev_start = date(start_date.year - 1, start_date.month, start_date.day)
    try:
        prev_end = date(end_date.year - 1, end_date.month, end_date.day)
    except ValueError:
        prev_end = date(end_date.year - 1, end_date.month, 28)
    
    prev_sales_df = queries.get_sales_data(
        start_date=prev_start,
        end_date=prev_end,
        kpi_center_ids=kpi_center_ids,
        entity_ids=entity_ids if entity_ids else None
    )
    
    # Exclude internal if requested
    if filter_values.get('exclude_internal_revenue', True) and not prev_sales_df.empty:
        if 'customer_type' in prev_sales_df.columns:
            prev_sales_df = prev_sales_df[prev_sales_df['customer_type'] != 'Internal']
    
    return prev_sales_df


# =============================================================================
# MAIN PAGE
# =============================================================================

def main():
    """Main page function."""
    
    # Check access
    access = check_access()
    
    # Page header
    st.title("🎯 KPI Center Performance")
    st.caption(f"Logged in as: {st.session_state.get('user_fullname', 'User')} ({st.session_state.get('user_role', '')})")
    
    # Load lookup data
    try:
        kpi_center_df, entity_df, available_years = load_lookup_data()
    except Exception as e:
        st.error(f"Failed to load lookup data: {e}")
        logger.error(f"Lookup data error: {e}")
        st.stop()
    
    # Initialize queries and filters
    queries = KPICenterQueries(access)
    filters = KPICenterFilters(access)
    
    # Render sidebar filters
    filter_values = filters.render_sidebar_filters(
        kpi_center_df=kpi_center_df,
        entity_df=entity_df,
        available_years=available_years
    )
    
    # Validate filters
    is_valid, error_msg = filters.validate_filters(filter_values)
    if not is_valid:
        st.error(f"⚠️ Filter error: {error_msg}")
        st.stop()
    
    # =========================================================================
    # LOAD DATA WITH SMART CACHING
    # =========================================================================
    
    # Handle initial load vs form submit
    if _get_applied_filters() is None:
        _set_applied_filters(filter_values)
    
    if filter_values.get('submitted', False):
        _set_applied_filters(filter_values)
    
    # Use applied filters
    active_filters = _get_applied_filters()
    
    # Load data
    raw_data = get_or_load_data(queries, active_filters)
    
    # Apply client-side filtering
    data = filter_data_client_side(raw_data, active_filters)
    
    sales_df = data.get('sales_df', pd.DataFrame())
    targets_df = data.get('targets_df', pd.DataFrame())
    
    if sales_df.empty:
        st.warning("No data found for the selected filters. Try adjusting your selection.")
        st.stop()
    
    # =========================================================================
    # CALCULATE METRICS
    # =========================================================================
    
    # Initialize metrics calculator
    metrics_calc = KPICenterMetrics(sales_df, targets_df)
    
    # Calculate metrics
    overview_metrics = metrics_calc.calculate_overview_metrics(
        period_type=active_filters['period_type'],
        year=active_filters['year'],
        start_date=active_filters['start_date'],
        end_date=active_filters['end_date']
    )
    
    # Complex KPIs summary
    complex_kpis = {
        'num_new_customers': data['new_customers_df']['num_new_customers'].sum() if not data.get('new_customers_df', pd.DataFrame()).empty else 0,
        'num_new_products': data['new_products_df']['num_new_products'].sum() if not data.get('new_products_df', pd.DataFrame()).empty else 0,
        'new_business_revenue': data['new_business_df']['new_business_revenue'].sum() if not data.get('new_business_df', pd.DataFrame()).empty else 0,
    }
    
    # Pipeline & Forecast
    pipeline_metrics = metrics_calc.calculate_pipeline_forecast_metrics(
        total_backlog_df=data.get('backlog_summary_df', pd.DataFrame()),
        in_period_backlog_df=data.get('backlog_in_period_df', pd.DataFrame()),
        period_type=active_filters['period_type'],
        year=active_filters['year'],
        start_date=active_filters['start_date'],
        end_date=active_filters['end_date']
    )
    
    # Overall KPI Achievement
    overall_achievement = metrics_calc.calculate_overall_kpi_achievement(
        period_type=active_filters['period_type'],
        year=active_filters['year'],
        start_date=active_filters['start_date'],
        end_date=active_filters['end_date']
    )
    
    # YoY metrics (if enabled)
    yoy_metrics = None
    if active_filters.get('show_yoy', True):
        prev_sales_df = load_yoy_data(queries, active_filters)
        yoy_metrics = metrics_calc.calculate_yoy_metrics(sales_df, prev_sales_df)
    
    # Monthly summary
    monthly_df = metrics_calc.prepare_monthly_summary()
    
    # KPI Center summary
    kpi_center_summary_df = metrics_calc.aggregate_by_kpi_center()
    
    # Period analysis
    period_info = analyze_period(active_filters)
    
    # Filter summary in header
    filter_summary = filters.get_filter_summary(active_filters)
    st.caption(f"📊 {filter_summary}")
    
    # ==========================================================================
    # TABS - UPDATED v2.3.0: Added Analysis tab
    # ==========================================================================
    
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "📊 Overview",
        "📋 Sales Detail",
        "📈 Analysis",  # NEW v2.3.0
        "📦 Backlog",
        "🎯 KPI & Targets",
        "⚙️ Setup"
    ])
    
    # ==========================================================================
    # TAB 1: OVERVIEW
    # ==========================================================================
    
    with tab1:
        # KPI Cards with popup drill-down (NEW v2.0.0)
        KPICenterCharts.render_kpi_cards(
            metrics=overview_metrics,
            yoy_metrics=yoy_metrics,
            complex_kpis=complex_kpis,
            overall_achievement=overall_achievement,
            # NEW: Pass detail dataframes for popup buttons
            new_customers_df=data.get('new_customers_detail_df'),
            new_products_df=data.get('new_products_detail_df'),
            new_business_df=data.get('new_business_df'),
            new_business_detail_df=data.get('new_business_detail_df')
        )
        
        # Backlog Risk Analysis (NEW v2.0.0)
        backlog_risk = data.get('backlog_risk', {})
        if backlog_risk:
            KPICenterCharts.render_backlog_risk_section(backlog_risk)
        
        # Pipeline & Forecast
        KPICenterCharts.render_pipeline_forecast_section(
            pipeline_metrics=pipeline_metrics,
            show_forecast=period_info.get('show_backlog', True)
        )
        
        st.divider()
        
        # Monthly Trend (Fragment) - UPDATED v2.2.0: Added targets_df
        st.subheader("📈 Monthly Trend")
        monthly_trend_fragment(
            sales_df=sales_df,
            filter_values=active_filters,
            targets_df=targets_df  # NEW v2.2.0: For target overlay
        )
        
        # YoY Comparison (if enabled)
        if active_filters.get('show_yoy', True):
            st.divider()
            st.subheader("📊 Year-over-Year Comparison")
            yoy_comparison_fragment(
                queries=queries,
                filter_values=active_filters,
                current_year=active_filters['year']
            )
        
        # Export section
        st.divider()
        export_report_fragment(
            metrics=overview_metrics,
            complex_kpis=complex_kpis,
            pipeline_metrics=pipeline_metrics,
            filter_values=active_filters,
            yoy_metrics=yoy_metrics,
            kpi_center_summary_df=kpi_center_summary_df,
            monthly_df=monthly_df,
            sales_detail_df=sales_df,
            backlog_summary_df=data.get('backlog_summary_df', pd.DataFrame()),
            backlog_detail_df=data.get('backlog_detail_df', pd.DataFrame()),
            backlog_by_month_df=data.get('backlog_by_month_df', pd.DataFrame())
        )
    
    # ==========================================================================
    # TAB 2: SALES DETAIL
    # ==========================================================================
    
    with tab2:
        sales_detail_fragment(
            sales_df=sales_df,
            filter_values=active_filters
        )
        
        st.divider()
        
        pivot_analysis_fragment(sales_df=sales_df)
    
    # ==========================================================================
    # TAB 3: ANALYSIS (NEW v2.3.0)
    # ==========================================================================
    
    with tab3:
        # Top Performers / Pareto Analysis
        top_performers_fragment(
            sales_df=sales_df,
            filter_values=active_filters,
            metrics_calculator=metrics_calc  # Use metrics_calc defined earlier
        )
    
    # ==========================================================================
    # TAB 4: BACKLOG (was TAB 3)
    # ==========================================================================
    
    with tab4:
        # Backlog summary cards
        backlog_metrics = KPICenterCharts.convert_pipeline_to_backlog_metrics(pipeline_metrics)
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric(
                label="Total Backlog",
                value=f"${backlog_metrics.get('total_backlog_revenue', 0):,.0f}",
                help="All uninvoiced orders"
            )
        
        with col2:
            st.metric(
                label="Total Backlog GP",
                value=f"${backlog_metrics.get('total_backlog_gp', 0):,.0f}"
            )
        
        with col3:
            st.metric(
                label="In-Period Backlog",
                value=f"${backlog_metrics.get('in_period_backlog_revenue', 0):,.0f}",
                help="Backlog with ETD in selected period"
            )
        
        with col4:
            st.metric(
                label="Backlog Orders",
                value=f"{backlog_metrics.get('backlog_orders', 0):,}"
            )
        
        # Backlog Risk Summary (NEW v2.0.0)
        backlog_risk = data.get('backlog_risk', {})
        if backlog_risk and backlog_risk.get('overdue_orders', 0) > 0:
            st.divider()
            st.subheader("⚠️ Risk Analysis")
            
            risk_col1, risk_col2, risk_col3 = st.columns(3)
            
            with risk_col1:
                st.metric(
                    label="🔴 Overdue Orders",
                    value=f"{backlog_risk.get('overdue_orders', 0):,}",
                    delta=f"${backlog_risk.get('overdue_revenue', 0):,.0f}",
                    delta_color="inverse",
                    help="Orders with ETD in the past"
                )
            
            with risk_col2:
                st.metric(
                    label="🟡 At Risk (7 days)",
                    value=f"{backlog_risk.get('at_risk_orders', 0):,}",
                    delta=f"${backlog_risk.get('at_risk_revenue', 0):,.0f}",
                    delta_color="off",
                    help="Orders with ETD within next 7 days"
                )
            
            with risk_col3:
                overdue_pct = backlog_risk.get('overdue_percent', 0)
                st.metric(
                    label="Overdue %",
                    value=f"{overdue_pct:.1f}%",
                    help="Percentage of total backlog that is overdue"
                )
        
        st.divider()
        
        # Backlog detail list - UPDATED v2.2.0: Added total_backlog_df
        backlog_list_fragment(
            backlog_df=data.get('backlog_detail_df', pd.DataFrame()),
            filter_values=active_filters,
            total_backlog_df=data.get('backlog_summary_df', pd.DataFrame())  # NEW v2.2.0
        )
        
        # Backlog by ETD month
        backlog_by_month = data.get('backlog_by_month_df', pd.DataFrame())
        if not backlog_by_month.empty:
            st.divider()
            st.subheader("📅 Backlog by ETD Month")
            
            display_df = backlog_by_month.copy()
            st.dataframe(
                display_df,
                hide_index=True,
                column_config={
                    'etd_year': 'Year',
                    'etd_month': 'Month',
                    'backlog_orders': 'Orders',
                    'backlog_usd': st.column_config.NumberColumn('Backlog', format="$%,.0f"),
                    'backlog_gp_usd': st.column_config.NumberColumn('Backlog GP', format="$%,.0f"),
                },
                use_container_width=True
            )
    
    # ==========================================================================
    # TAB 5: KPI & TARGETS (was TAB 4)
    # ==========================================================================
    
    with tab5:
        st.subheader("🎯 KPI Assignments")
        
        if targets_df.empty:
            st.info("No KPI targets assigned for selected KPI Centers and year")
        else:
            # Group by KPI Center
            for kpi_center_id in targets_df['kpi_center_id'].unique():
                kc_targets = targets_df[targets_df['kpi_center_id'] == kpi_center_id]
                kc_name = kc_targets['kpi_center_name'].iloc[0]
                
                with st.expander(f"📊 {kc_name}", expanded=True):
                    display_cols = ['kpi_name', 'annual_target_value', 'weight_numeric', 'unit_of_measure']
                    display_cols = [c for c in display_cols if c in kc_targets.columns]
                    
                    st.dataframe(
                        kc_targets[display_cols],
                        hide_index=True,
                        column_config={
                            'kpi_name': 'KPI',
                            'annual_target_value': 'Annual Target',
                            'weight_numeric': st.column_config.NumberColumn('Weight %'),
                            'unit_of_measure': 'Unit',
                        }
                    )
        
        st.divider()
        
        # KPI Center Ranking
        st.subheader("🏆 KPI Center Ranking")
        kpi_center_ranking_fragment(
            ranking_df=kpi_center_summary_df,
            show_targets=not targets_df.empty
        )
    
    # ==========================================================================
    # TAB 6: SETUP (was TAB 5)
    # ==========================================================================
    
    with tab6:
        st.subheader("⚙️ KPI Center Configuration")
        
        # KPI Split assignments
        st.markdown("### 📋 KPI Center Split Assignments")
        
        kpi_split_df = queries.get_kpi_split_data(
            kpi_center_ids=active_filters.get('kpi_center_ids', [])
        )
        
        if kpi_split_df.empty:
            st.info("No split assignments found for selected KPI Centers")
        else:
            # Filter options
            col1, col2 = st.columns(2)
            
            with col1:
                customers = ['All'] + sorted(kpi_split_df['customer_name'].dropna().unique().tolist())
                selected_customer = st.selectbox(
                    "Filter by Customer",
                    customers,
                    key="setup_customer_filter"
                )
            
            with col2:
                search = st.text_input(
                    "Search Product",
                    placeholder="Product name or code...",
                    key="setup_product_search"
                )
            
            filtered_split = kpi_split_df.copy()
            
            if selected_customer != 'All':
                filtered_split = filtered_split[filtered_split['customer_name'] == selected_customer]
            
            if search:
                mask = (
                    filtered_split['product_pn'].fillna('').str.lower().str.contains(search.lower()) |
                    filtered_split['pt_code'].fillna('').str.lower().str.contains(search.lower())
                )
                filtered_split = filtered_split[mask]
            
            st.caption(f"Showing {len(filtered_split):,} split assignments")
            
            display_cols = ['kpi_center_name', 'customer_name', 'product_pn', 'brand', 
                          'split_percentage', 'effective_period', 'kpi_split_status']
            display_cols = [c for c in display_cols if c in filtered_split.columns]
            
            st.dataframe(
                filtered_split[display_cols].head(500),
                hide_index=True,
                column_config={
                    'kpi_center_name': 'KPI Center',
                    'customer_name': 'Customer',
                    'product_pn': 'Product',
                    'brand': 'Brand',
                    'split_percentage': st.column_config.NumberColumn('Split %'),
                    'effective_period': 'Period',
                    'kpi_split_status': 'Status',
                },
                use_container_width=True
            )
        
        # KPI Center Hierarchy
        st.divider()
        st.markdown("### 🌳 KPI Center Hierarchy")
        
        hierarchy_df = queries.get_kpi_center_hierarchy()
        
        if hierarchy_df.empty:
            st.info("No hierarchy data available")
        else:
            st.dataframe(
                hierarchy_df,
                hide_index=True,
                column_config={
                    'kpi_center_id': 'ID',
                    'kpi_center_name': 'KPI Center',
                    'kpi_type': 'Type',
                    'parent_center_id': 'Parent ID',
                    'level': 'Level',
                }
            )


# =============================================================================
# RUN
# =============================================================================

if __name__ == "__main__":
    main()
else:
    main()