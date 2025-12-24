# pages/2_🎯_KPI_Center_Performance.py
"""
KPI Center Performance Dashboard

VERSION: 2.5.1
CHANGELOG:
- v2.5.1: BUGFIX - kpi_type_filter now works in filter_data_client_side()
          - Removed debug print statements from fragments.py
- v2.4.0: SYNCED UI with Salesperson Performance page:
          - Overview tab now matches SP page layout exactly
          - Monthly Trend & Cumulative: 2 charts side-by-side with Customer/Brand/Product Excl filters
          - Year-over-Year Comparison: Tabs (Revenue/GP/GP1), summary metrics, 2 charts
          - Backlog & Forecast: Inline section with 3 tabs (Revenue/GP/GP1), 
            5 metrics each + 2 charts per tab (waterfall + gap analysis)
          - Removed separate PIPELINE & FORECAST and BACKLOG RISK ANALYSIS sections
          - New Business popover widened to match SP page
- v2.3.1: BUGFIX - KPI Center filter not working
- v2.3.0: Phase 3 - Added Analysis tab with Pareto analysis
- v2.2.0: Phase 2 enhancements
- v2.0.0: Complex KPIs popup, backlog risk, smart caching
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
    top_performers_fragment,
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
    """Clean dataframe to avoid Arrow serialization errors."""
    if df.empty:
        return df
    
    df_clean = df.copy()
    
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
    """
    Load lookup data for filters (cached).
    
    UPDATED v2.5.0: KPI Center and KPI Type loaded dynamically from 
    unified_sales_by_kpi_center_view instead of kpi_centers table.
    This ensures dropdown only shows KPI Centers with actual sales data.
    """
    from utils.db import get_db_engine
    from sqlalchemy import text
    
    engine = get_db_engine()
    
    # =========================================================================
    # KPI CENTER & KPI TYPE - From unified_sales_by_kpi_center_view (UPDATED)
    # =========================================================================
    kpi_center_query = """
        SELECT DISTINCT
            kpi_center_id,
            kpi_center AS kpi_center_name,
            kpi_type
        FROM unified_sales_by_kpi_center_view
        WHERE kpi_center_id IS NOT NULL
        ORDER BY kpi_type, kpi_center
    """
    kpi_center_df = pd.read_sql(text(kpi_center_query), engine)
    
    # Add placeholder columns for backward compatibility
    if not kpi_center_df.empty:
        kpi_center_df['parent_center_id'] = None
        kpi_center_df['description'] = None
    
    # =========================================================================
    # LEGAL ENTITY - From unified_sales_by_kpi_center_view (no change)
    # =========================================================================
    entity_query = """
        SELECT DISTINCT
            legal_entity_id AS entity_id,
            legal_entity AS entity_name
        FROM unified_sales_by_kpi_center_view
        WHERE legal_entity_id IS NOT NULL
        ORDER BY legal_entity
    """
    entity_df = pd.read_sql(text(entity_query), engine)
    
    # =========================================================================
    # AVAILABLE YEARS - From unified_sales_by_kpi_center_view (no change)
    # =========================================================================
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
    """Load data for specified year range."""
    start_date = date(start_year, 1, 1)
    end_date = date(end_year, 12, 31)
    
    progress_bar = st.progress(0, text=f"🔄 Loading data ({start_year}-{end_year})...")
    
    data = {}
    
    try:
        progress_bar.progress(10, text="📊 Loading sales data...")
        data['sales_df'] = queries.get_sales_data(
            start_date=start_date,
            end_date=end_date,
            kpi_center_ids=kpi_center_ids,
            entity_ids=entity_ids
        )
        
        progress_bar.progress(25, text="🎯 Loading KPI targets...")
        targets_list = []
        for yr in range(start_year, end_year + 1):
            t = queries.get_kpi_targets(year=yr, kpi_center_ids=kpi_center_ids)
            if not t.empty:
                targets_list.append(t)
        data['targets_df'] = pd.concat(targets_list, ignore_index=True) if targets_list else pd.DataFrame()
        
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
        
        data['backlog_by_month_df'] = queries.get_backlog_by_month(
            kpi_center_ids=kpi_center_ids,
            entity_ids=entity_ids
        )
        
        progress_bar.progress(55, text="📋 Loading backlog details...")
        data['backlog_detail_df'] = queries.get_backlog_detail(
            kpi_center_ids=kpi_center_ids,
            entity_ids=entity_ids
        )
        
        progress_bar.progress(70, text="🆕 Loading complex KPIs...")
        data['new_customers_df'] = queries.get_new_customers(start_date, end_date, kpi_center_ids)
        data['new_customers_detail_df'] = queries.get_new_customers_detail(start_date, end_date, kpi_center_ids)
        data['new_products_df'] = queries.get_new_products(start_date, end_date, kpi_center_ids)
        data['new_products_detail_df'] = data['new_products_df']
        data['new_business_df'] = queries.get_new_business_revenue(start_date, end_date, kpi_center_ids)
        data['new_business_detail_df'] = queries.get_new_business_detail(start_date, end_date, kpi_center_ids)
        
        progress_bar.progress(85, text="⚠️ Analyzing backlog risk...")
        data['backlog_risk'] = queries.get_backlog_risk_analysis(
            kpi_center_ids=kpi_center_ids,
            entity_ids=entity_ids
        )
        
        for key in data:
            if isinstance(data[key], pd.DataFrame) and not data[key].empty:
                data[key] = _clean_dataframe_for_display(data[key])
        
        data['_loaded_at'] = datetime.now()
        data['_year_range'] = (start_year, end_year)
        
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


def _needs_data_reload(filter_values: dict) -> bool:
    """Check if data needs to be reloaded."""
    if '_kpc_raw_cached_data' not in st.session_state or st.session_state._kpc_raw_cached_data is None:
        return True
    
    cached_start, cached_end = _get_cached_year_range()
    if cached_start is None or cached_end is None:
        return True
    
    required_start = filter_values['start_date'].year
    required_end = filter_values['end_date'].year
    
    return required_start < cached_start or required_end > cached_end


def get_or_load_data(queries: KPICenterQueries, filter_values: dict) -> dict:
    """Smart data loading with session-based caching."""
    required_start = filter_values['start_date'].year
    required_end = filter_values['end_date'].year
    
    kpi_center_ids = filter_values.get('kpi_center_ids', [])
    entity_ids = filter_values.get('entity_ids', [])
    
    cached_start, cached_end = _get_cached_year_range()
    
    if _needs_data_reload(filter_values):
        if cached_start is not None and cached_end is not None:
            new_start = min(required_start, cached_start)
            new_end = max(required_end, cached_end)
        else:
            current_year = date.today().year
            new_start = min(required_start, current_year - 2)
            new_end = max(required_end, current_year)
        
        data = load_data_for_year_range(
            queries=queries,
            start_year=new_start,
            end_year=new_end,
            kpi_center_ids=kpi_center_ids,
            entity_ids=entity_ids
        )
        
        st.session_state._kpc_raw_cached_data = data
        _set_cached_year_range(new_start, new_end)
        
        return data
    
    return st.session_state._kpc_raw_cached_data


def filter_data_client_side(raw_data: dict, filter_values: dict) -> dict:
    """
    Filter cached data client-side based on ALL filters.
    
    UPDATED v2.5.0: Uses kpi_center_ids_expanded to include children data
    when a parent KPI Center is selected.
    """
    start_date = filter_values['start_date']
    end_date = filter_values['end_date']
    
    # =========================================================================
    # UPDATED v2.5.0: Use expanded IDs (includes children)
    # =========================================================================
    # Fallback to 'kpi_center_ids' for backward compatibility
    kpi_center_ids = filter_values.get('kpi_center_ids_expanded', 
                                        filter_values.get('kpi_center_ids', []))
    
    entity_ids = filter_values.get('entity_ids', [])
    year = filter_values['year']
    exclude_internal_revenue = filter_values.get('exclude_internal_revenue', True)
    
    # =========================================================================
    # NEW v2.5.1: KPI Type filter
    # =========================================================================
    kpi_type_filter = filter_values.get('kpi_type_filter', None)
    
    filtered = {}
    
    for key, df in raw_data.items():
        if key.startswith('_'):
            continue
            
        if not isinstance(df, pd.DataFrame) or df.empty:
            filtered[key] = df
            continue
        
        df_filtered = df.copy()
        
        # Filter by date range
        date_cols = ['inv_date', 'oc_date', 'invoiced_date', 'first_invoice_date', 'first_sale_date']
        for date_col in date_cols:
            if date_col in df_filtered.columns:
                df_filtered[date_col] = pd.to_datetime(df_filtered[date_col], errors='coerce')
                df_filtered = df_filtered[
                    (df_filtered[date_col] >= pd.Timestamp(start_date)) & 
                    (df_filtered[date_col] <= pd.Timestamp(end_date))
                ]
                break
        
        # Filter by kpi_center_ids (now uses expanded IDs with children)
        if kpi_center_ids:
            kpc_ids_set = set(kpi_center_ids)
            if 'kpi_center_id' in df_filtered.columns:
                df_filtered = df_filtered[df_filtered['kpi_center_id'].isin(kpc_ids_set)]
        
        # Filter by entity_ids
        if entity_ids:
            entity_ids_set = set(entity_ids)
            if 'legal_entity_id' in df_filtered.columns:
                df_filtered = df_filtered[df_filtered['legal_entity_id'].isin(entity_ids_set)]
        
        # Exclude internal revenue
        if exclude_internal_revenue and 'customer_type' in df_filtered.columns:
            if 'sales_by_kpi_center_usd' in df_filtered.columns:
                internal_mask = df_filtered['customer_type'] == 'Internal'
                df_filtered.loc[internal_mask, 'sales_by_kpi_center_usd'] = 0
        
        # =====================================================================
        # NEW v2.5.1: Filter by kpi_type
        # =====================================================================
        if kpi_type_filter and 'kpi_type' in df_filtered.columns:
            df_filtered = df_filtered[df_filtered['kpi_type'] == kpi_type_filter]
        
        filtered[key] = df_filtered
    
    # Filter targets by year AND kpi_center_ids (using expanded IDs)
    if 'targets_df' in filtered and not filtered['targets_df'].empty:
        targets = filtered['targets_df']
        if 'year' in targets.columns:
            targets = targets[targets['year'] == year]
        if kpi_center_ids and 'kpi_center_id' in targets.columns:
            targets = targets[targets['kpi_center_id'].isin(kpi_center_ids)]
        # NEW v2.5.1: Filter targets by kpi_type
        if kpi_type_filter and 'kpi_type' in targets.columns:
            targets = targets[targets['kpi_type'] == kpi_type_filter]
        filtered['targets_df'] = targets
    
    # Recalculate backlog risk from filtered data
    if 'backlog_detail_df' in filtered and not filtered['backlog_detail_df'].empty:
        filtered['backlog_risk'] = _calculate_backlog_risk_from_df(filtered['backlog_detail_df'])
    
    return filtered


def _calculate_backlog_risk_from_df(backlog_df: pd.DataFrame) -> dict:
    """Calculate backlog risk metrics from filtered dataframe."""
    if backlog_df.empty:
        return {}
    
    today = date.today()
    
    if 'etd' in backlog_df.columns:
        backlog_df['etd'] = pd.to_datetime(backlog_df['etd'], errors='coerce')
        backlog_df['days_until_etd'] = (backlog_df['etd'] - pd.Timestamp(today)).dt.days
    
    revenue_col = 'backlog_by_kpi_center_usd' if 'backlog_by_kpi_center_usd' in backlog_df.columns else 'backlog_usd'
    
    if 'days_until_etd' not in backlog_df.columns:
        return {}
    
    overdue = backlog_df[backlog_df['days_until_etd'] < 0]
    at_risk = backlog_df[(backlog_df['days_until_etd'] >= 0) & (backlog_df['days_until_etd'] <= 7)]
    
    total_backlog = backlog_df[revenue_col].sum() if revenue_col in backlog_df.columns else 0
    overdue_revenue = overdue[revenue_col].sum() if revenue_col in overdue.columns else 0
    
    return {
        'overdue_orders': len(overdue),
        'overdue_revenue': overdue_revenue,
        'at_risk_orders': len(at_risk),
        'at_risk_revenue': at_risk[revenue_col].sum() if revenue_col in at_risk.columns else 0,
        'total_backlog': total_backlog,
        'overdue_percent': (overdue_revenue / total_backlog * 100) if total_backlog > 0 else 0,
    }


def load_yoy_data(queries: KPICenterQueries, filter_values: dict):
    """Load previous year data for YoY comparison."""
    start_date = filter_values['start_date']
    end_date = filter_values['end_date']
    kpi_center_ids = filter_values.get('kpi_center_ids', [])
    entity_ids = filter_values.get('entity_ids', [])
    
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
    
    if filter_values.get('exclude_internal_revenue', True) and not prev_sales_df.empty:
        if 'customer_type' in prev_sales_df.columns:
            prev_sales_df = prev_sales_df[prev_sales_df['customer_type'] != 'Internal']
    
    return prev_sales_df


# =============================================================================
# MAIN PAGE
# =============================================================================

def main():
    """Main page function."""
    
    access = check_access()
    
    st.title("🎯 KPI Center Performance")
    st.caption(f"Logged in as: {st.session_state.get('user_fullname', 'User')} ({st.session_state.get('user_role', '')})")
    
    try:
        kpi_center_df, entity_df, available_years = load_lookup_data()
    except Exception as e:
        st.error(f"Failed to load lookup data: {e}")
        logger.error(f"Lookup data error: {e}")
        st.stop()
    
    queries = KPICenterQueries(access)
    filters = KPICenterFilters(access)
    
    filter_values = filters.render_sidebar_filters(
        kpi_center_df=kpi_center_df,
        entity_df=entity_df,
        available_years=available_years
    )
    
    is_valid, error_msg = filters.validate_filters(filter_values)
    if not is_valid:
        st.error(f"⚠️ Filter error: {error_msg}")
        st.stop()
    
    # =========================================================================
    # LOAD DATA WITH SMART CACHING
    # =========================================================================
    
    if _get_applied_filters() is None:
        _set_applied_filters(filter_values)
    
    if filter_values.get('submitted', False):
        _set_applied_filters(filter_values)
    
    active_filters = _get_applied_filters()
    raw_data = get_or_load_data(queries, active_filters)
    data = filter_data_client_side(raw_data, active_filters)
    
    sales_df = data.get('sales_df', pd.DataFrame())
    targets_df = data.get('targets_df', pd.DataFrame())
    
    if sales_df.empty:
        st.warning("No data found for the selected filters. Try adjusting your selection.")
        st.stop()
    
    # =========================================================================
    # CALCULATE METRICS
    # =========================================================================
    
    metrics_calc = KPICenterMetrics(sales_df, targets_df)
    
    overview_metrics = metrics_calc.calculate_overview_metrics(
        period_type=active_filters['period_type'],
        year=active_filters['year'],
        start_date=active_filters['start_date'],
        end_date=active_filters['end_date']
    )
    
    complex_kpis = {
        'num_new_customers': data['new_customers_df']['num_new_customers'].sum() if not data.get('new_customers_df', pd.DataFrame()).empty else 0,
        'num_new_products': data['new_products_df']['num_new_products'].sum() if not data.get('new_products_df', pd.DataFrame()).empty else 0,
        'new_business_revenue': data['new_business_df']['new_business_revenue'].sum() if not data.get('new_business_df', pd.DataFrame()).empty else 0,
    }
    
    pipeline_metrics = metrics_calc.calculate_pipeline_forecast_metrics(
        total_backlog_df=data.get('backlog_summary_df', pd.DataFrame()),
        in_period_backlog_df=data.get('backlog_in_period_df', pd.DataFrame()),
        period_type=active_filters['period_type'],
        year=active_filters['year'],
        start_date=active_filters['start_date'],
        end_date=active_filters['end_date']
    )
    
    overall_achievement = metrics_calc.calculate_overall_kpi_achievement(
        period_type=active_filters['period_type'],
        year=active_filters['year'],
        start_date=active_filters['start_date'],
        end_date=active_filters['end_date']
    )
    
    yoy_metrics = None
    if active_filters.get('show_yoy', True):
        prev_sales_df = load_yoy_data(queries, active_filters)
        yoy_metrics = metrics_calc.calculate_yoy_metrics(sales_df, prev_sales_df)
    
    monthly_df = metrics_calc.prepare_monthly_summary()
    kpi_center_summary_df = metrics_calc.aggregate_by_kpi_center()
    period_info = analyze_period(active_filters)
    
    filter_summary = filters.get_filter_summary(active_filters)
    st.caption(f"📊 {filter_summary}")
    
    # ==========================================================================
    # TABS
    # ==========================================================================
    
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "📊 Overview",
        "📋 Sales Detail",
        "📈 Analysis",
        "📦 Backlog",
        "🎯 KPI & Targets",
        "⚙️ Setup"
    ])
    
    # ==========================================================================
    # TAB 1: OVERVIEW - SYNCED with Salesperson page v2.4.0
    # ==========================================================================
    
    with tab1:
        # =====================================================================
        # KPI CARDS (Performance + New Business)
        # =====================================================================
        KPICenterCharts.render_kpi_cards(
            metrics=overview_metrics,
            yoy_metrics=yoy_metrics,
            complex_kpis=complex_kpis,
            overall_achievement=overall_achievement,
            new_customers_df=data.get('new_customers_detail_df'),
            new_products_df=data.get('new_products_detail_df'),
            new_business_df=data.get('new_business_df'),
            new_business_detail_df=data.get('new_business_detail_df')
        )
        
        st.divider()
        
        # =====================================================================
        # MONTHLY TREND & CUMULATIVE - SYNCED with SP page
        # =====================================================================
        monthly_trend_fragment(
            sales_df=sales_df,
            filter_values=active_filters,
            targets_df=targets_df,
            fragment_key="kpc_trend"
        )
        
        st.divider()
        
        # =====================================================================
        # YEAR-OVER-YEAR COMPARISON - SYNCED with SP page
        # =====================================================================
        if active_filters.get('show_yoy', True):
            yoy_comparison_fragment(
                queries=queries,
                filter_values=active_filters,
                current_year=active_filters['year'],
                sales_df=sales_df,
                raw_cached_data=st.session_state.get('_kpc_raw_cached_data'),  # NEW
                fragment_key="kpc_yoy"
            )
            
            st.divider()
        
        # =====================================================================
        # BACKLOG & FORECAST - SYNCED with SP page (Image 4)
        # =====================================================================
        if period_info.get('show_backlog', True):
            col_bf_header, col_bf_help = st.columns([6, 1])
            with col_bf_header:
                st.subheader("📦 Backlog & Forecast")
            with col_bf_help:
                with st.popover("ℹ️ Help"):
                    st.markdown("""
**📦 Backlog & Forecast**

| Metric | Formula | Description |
|--------|---------|-------------|
| **Total Backlog** | `Σ backlog_by_kpi_center_usd` | All outstanding orders |
| **In-Period (KPI)** | `Σ backlog WHERE ETD in period` | Backlog expected to ship in period. **Only from KPI Centers with this KPI assigned.** |
| **Target** | `Σ prorated_target` | Sum of prorated annual targets |
| **Forecast (KPI)** | `Invoiced + In-Period` | Projected total. **Only from KPI Centers with this KPI assigned.** |
| **GAP/Surplus** | `Forecast - Target` | Positive = ahead of target, Negative = behind |

---

**⚠️ Important: Data Filtered by KPI Assignment**

Each tab shows data ONLY from KPI Centers who have that specific KPI target:
- **Revenue tab**: KPI Centers with Revenue KPI
- **GP tab**: KPI Centers with Gross Profit KPI  
- **GP1 tab**: KPI Centers with GP1 KPI

This ensures accurate achievement calculation.
                    """)
            
            # Overdue warning
            backlog_risk = data.get('backlog_risk', {})
            if backlog_risk and backlog_risk.get('overdue_orders', 0) > 0:
                overdue_orders = backlog_risk.get('overdue_orders', 0)
                overdue_revenue = backlog_risk.get('overdue_revenue', 0)
                st.warning(f"⚠️ {overdue_orders} orders are past ETD. Value: ${overdue_revenue:,.0f}")
            
            # GP1/GP ratio note
            summary_metrics = pipeline_metrics.get('summary', {})
            gp1_gp_ratio = summary_metrics.get('gp1_gp_ratio', 1.0)
            if gp1_gp_ratio != 1.0:
                st.caption(f"📊 GP1 backlog estimated using GP1/GP ratio: {gp1_gp_ratio:.2%}")
            
            # Convert to backlog metrics format
            chart_backlog_metrics = KPICenterCharts.convert_pipeline_to_backlog_metrics(pipeline_metrics)
            
            # Extract metrics for each tab
            revenue_metrics = pipeline_metrics.get('revenue', {})
            gp_metrics = pipeline_metrics.get('gross_profit', {})
            gp1_metrics = pipeline_metrics.get('gp1', {})
            
            # Tabs for Revenue / GP / GP1
            bf_tab1, bf_tab2, bf_tab3 = st.tabs(["💰 Revenue", "📈 Gross Profit", "📊 GP1"])
            
            # =================================================================
            # REVENUE TAB
            # =================================================================
            with bf_tab1:
                col_m1, col_m2, col_m3, col_m4, col_m5 = st.columns(5)
                
                with col_m1:
                    st.metric(
                        label="Total Backlog",
                        value=f"${summary_metrics.get('total_backlog_revenue', 0):,.0f}",
                        delta=f"{int(summary_metrics.get('backlog_orders', 0)):,} orders" if summary_metrics.get('backlog_orders') else None,
                        delta_color="off",
                        help="All outstanding revenue from pending orders"
                    )
                
                with col_m2:
                    in_period = revenue_metrics.get('in_period_backlog', 0)
                    target = revenue_metrics.get('target')
                    pct = (in_period / target * 100) if target and target > 0 else None
                    kpc_count = revenue_metrics.get('kpi_center_count', 0)
                    st.metric(
                        label="In-Period (KPI)",
                        value=f"${in_period:,.0f}",
                        delta=f"{pct:.0f}% of target" if pct else None,
                        delta_color="off",
                        help=f"Backlog with ETD in period. Only from {kpc_count} KPI Centers with Revenue KPI."
                    )
                
                with col_m3:
                    target = revenue_metrics.get('target')
                    kpc_count = revenue_metrics.get('kpi_center_count', 0)
                    if target and target > 0:
                        st.metric(
                            label="Target",
                            value=f"${target:,.0f}",
                            delta=f"{kpc_count} KPI Centers",
                            delta_color="off",
                            help=f"Sum of prorated Revenue targets from {kpc_count} KPI Centers"
                        )
                    else:
                        st.metric(label="Target", value="N/A", delta="No KPI assigned", delta_color="off")
                
                with col_m4:
                    forecast = revenue_metrics.get('forecast')
                    achievement = revenue_metrics.get('forecast_achievement')
                    if forecast is not None:
                        delta_color = "normal" if achievement and achievement >= 100 else "inverse"
                        st.metric(
                            label="Forecast (KPI)",
                            value=f"${forecast:,.0f}",
                            delta=f"{achievement:.0f}% of target" if achievement else None,
                            delta_color=delta_color if achievement else "off",
                            help=f"Invoiced + In-Period Backlog"
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
                    st.markdown("**Revenue Forecast vs Target**")
                    forecast_chart = KPICenterCharts.build_forecast_waterfall_chart(
                        backlog_metrics=chart_backlog_metrics,
                        metric='revenue',
                        title=""
                    )
                    st.altair_chart(forecast_chart, use_container_width=True)
                with col_bf2:
                    st.markdown("**Revenue: Target vs Forecast**")
                    gap_chart = KPICenterCharts.build_gap_analysis_chart(
                        backlog_metrics=chart_backlog_metrics,
                        metrics_to_show=['revenue'],
                        title=""
                    )
                    st.altair_chart(gap_chart, use_container_width=True)
            
            # =================================================================
            # GROSS PROFIT TAB
            # =================================================================
            with bf_tab2:
                col_m1, col_m2, col_m3, col_m4, col_m5 = st.columns(5)
                
                with col_m1:
                    st.metric(
                        label="Total Backlog",
                        value=f"${summary_metrics.get('total_backlog_gp', 0):,.0f}",
                        delta=f"{int(summary_metrics.get('backlog_orders', 0)):,} orders" if summary_metrics.get('backlog_orders') else None,
                        delta_color="off",
                        help="All outstanding GP from pending orders"
                    )
                
                with col_m2:
                    in_period = gp_metrics.get('in_period_backlog', 0)
                    target = gp_metrics.get('target')
                    pct = (in_period / target * 100) if target and target > 0 else None
                    kpc_count = gp_metrics.get('kpi_center_count', 0)
                    st.metric(
                        label="In-Period (KPI)",
                        value=f"${in_period:,.0f}",
                        delta=f"{pct:.0f}% of target" if pct else None,
                        delta_color="off",
                        help=f"Backlog with ETD in period. Only from {kpc_count} KPI Centers with GP KPI."
                    )
                
                with col_m3:
                    target = gp_metrics.get('target')
                    kpc_count = gp_metrics.get('kpi_center_count', 0)
                    if target and target > 0:
                        st.metric(
                            label="Target",
                            value=f"${target:,.0f}",
                            delta=f"{kpc_count} KPI Centers",
                            delta_color="off",
                            help=f"Sum of prorated GP targets from {kpc_count} KPI Centers"
                        )
                    else:
                        st.metric(label="Target", value="N/A", delta="No KPI assigned", delta_color="off")
                
                with col_m4:
                    forecast = gp_metrics.get('forecast')
                    achievement = gp_metrics.get('forecast_achievement')
                    if forecast is not None:
                        delta_color = "normal" if achievement and achievement >= 100 else "inverse"
                        st.metric(
                            label="Forecast (KPI)",
                            value=f"${forecast:,.0f}",
                            delta=f"{achievement:.0f}% of target" if achievement else None,
                            delta_color=delta_color if achievement else "off",
                            help=f"Invoiced + In-Period Backlog"
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
                
                col_bf1, col_bf2 = st.columns(2)
                with col_bf1:
                    st.markdown("**GP Forecast vs Target**")
                    forecast_chart = KPICenterCharts.build_forecast_waterfall_chart(
                        backlog_metrics=chart_backlog_metrics,
                        metric='gp',
                        title=""
                    )
                    st.altair_chart(forecast_chart, use_container_width=True)
                with col_bf2:
                    st.markdown("**GP: Target vs Forecast**")
                    gap_chart = KPICenterCharts.build_gap_analysis_chart(
                        backlog_metrics=chart_backlog_metrics,
                        metrics_to_show=['gp'],
                        title=""
                    )
                    st.altair_chart(gap_chart, use_container_width=True)
            
            # =================================================================
            # GP1 TAB
            # =================================================================
            with bf_tab3:
                col_m1, col_m2, col_m3, col_m4, col_m5 = st.columns(5)
                
                with col_m1:
                    st.metric(
                        label="Total Backlog",
                        value=f"${summary_metrics.get('total_backlog_gp1', 0):,.0f}",
                        delta=f"{int(summary_metrics.get('backlog_orders', 0)):,} orders" if summary_metrics.get('backlog_orders') else None,
                        delta_color="off",
                        help=f"Estimated GP1 backlog (GP × {gp1_gp_ratio:.2%})"
                    )
                
                with col_m2:
                    in_period = gp1_metrics.get('in_period_backlog', 0)
                    target = gp1_metrics.get('target')
                    pct = (in_period / target * 100) if target and target > 0 else None
                    kpc_count = gp1_metrics.get('kpi_center_count', 0)
                    st.metric(
                        label="In-Period (KPI)",
                        value=f"${in_period:,.0f}",
                        delta=f"{pct:.0f}% of target" if pct else None,
                        delta_color="off",
                        help=f"Estimated GP1 backlog with ETD in period. Only from {kpc_count} KPI Centers with GP1 KPI."
                    )
                
                with col_m3:
                    target = gp1_metrics.get('target')
                    kpc_count = gp1_metrics.get('kpi_center_count', 0)
                    if target and target > 0:
                        st.metric(
                            label="Target",
                            value=f"${target:,.0f}",
                            delta=f"{kpc_count} KPI Centers",
                            delta_color="off",
                            help=f"Sum of prorated GP1 targets from {kpc_count} KPI Centers"
                        )
                    else:
                        st.metric(label="Target", value="N/A", delta="No KPI assigned", delta_color="off")
                
                with col_m4:
                    forecast = gp1_metrics.get('forecast')
                    achievement = gp1_metrics.get('forecast_achievement')
                    if forecast is not None:
                        delta_color = "normal" if achievement and achievement >= 100 else "inverse"
                        st.metric(
                            label="Forecast (KPI)",
                            value=f"${forecast:,.0f}",
                            delta=f"{achievement:.0f}% of target" if achievement else None,
                            delta_color=delta_color if achievement else "off",
                            help=f"Invoiced + In-Period Backlog (estimated)"
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
                
                col_bf1, col_bf2 = st.columns(2)
                with col_bf1:
                    st.markdown("**GP1 Forecast vs Target**")
                    forecast_chart = KPICenterCharts.build_forecast_waterfall_chart(
                        backlog_metrics=chart_backlog_metrics,
                        metric='gp1',
                        title=""
                    )
                    st.altair_chart(forecast_chart, use_container_width=True)
                with col_bf2:
                    st.markdown("**GP1: Target vs Forecast**")
                    gap_chart = KPICenterCharts.build_gap_analysis_chart(
                        backlog_metrics=chart_backlog_metrics,
                        metrics_to_show=['gp1'],
                        title=""
                    )
                    st.altair_chart(gap_chart, use_container_width=True)
            
            st.divider()
        else:
            st.info(f"""
            📅 **Forecast not available for historical periods**
            
            End date ({active_filters['end_date'].strftime('%Y-%m-%d')}) is in the past.
            Forecast is only meaningful when end date >= today.
            
            💡 **Tip:** To view Forecast, adjust End Date to today or a future date.
            """)
            st.divider()
        
        # =====================================================================
        # EXPORT SECTION
        # =====================================================================
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
    # TAB 3: ANALYSIS
    # ==========================================================================
    
    with tab3:
        top_performers_fragment(
            sales_df=sales_df,
            filter_values=active_filters,
            metrics_calculator=metrics_calc
        )
    
    # ==========================================================================
    # TAB 4: BACKLOG
    # ==========================================================================
    
    with tab4:
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
        
        st.divider()
        
        backlog_list_fragment(
            backlog_df=data.get('backlog_detail_df', pd.DataFrame()),
            filter_values=active_filters,
            total_backlog_df=data.get('backlog_summary_df', pd.DataFrame())
        )
        
        backlog_by_month = data.get('backlog_by_month_df', pd.DataFrame())
        if not backlog_by_month.empty:
            st.divider()
            st.subheader("📅 Backlog by ETD Month")
            
            st.dataframe(
                backlog_by_month,
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
    # TAB 5: KPI & TARGETS
    # ==========================================================================
    
    with tab5:
        st.subheader("🎯 KPI Assignments")
        
        if targets_df.empty:
            st.info("No KPI targets assigned for selected KPI Centers and year")
        else:
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
        
        st.subheader("🏆 KPI Center Ranking")
        kpi_center_ranking_fragment(
            ranking_df=kpi_center_summary_df,
            show_targets=not targets_df.empty
        )
    
    # ==========================================================================
    # TAB 6: SETUP
    # ==========================================================================
    
    with tab6:
        st.subheader("⚙️ KPI Center Configuration")
        
        st.markdown("### 📋 KPI Center Split Assignments")
        
        kpi_split_df = queries.get_kpi_split_data(
            kpi_center_ids=active_filters.get('kpi_center_ids', [])
        )
        
        if kpi_split_df.empty:
            st.info("No split assignments found for selected KPI Centers")
        else:
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