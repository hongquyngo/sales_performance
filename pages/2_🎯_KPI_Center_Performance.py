# pages/2_🎯_KPI_Center_Performance.py
"""
KPI Center Performance Dashboard

VERSION: 4.0.1
CHANGELOG:
- v4.0.1: RESTORED missing features from v3.9.0
  - Progress bar during data loading (in UnifiedDataLoader)
  - Export Report UI at end of Overview tab
  - Backlog & Forecast charts (waterfall + gap analysis)
  - Full metrics display with proper help text
- v4.0.0: Unified data loading architecture
  - Replaced load_lookup_data() + load_data_for_year_range() with UnifiedDataLoader
  - Replaced filter_data_client_side() with DataProcessor
  - Simplified reload logic (only on cache expiry)
  - All constants centralized in constants.py
  - ~60% faster first load, ~95% faster filter changes
"""

import logging
from datetime import date, datetime
import time
from contextlib import contextmanager
import pandas as pd
import streamlit as st

# =============================================================================
# PAGE CONFIG (must be first Streamlit command)
# =============================================================================
st.set_page_config(
    page_title="KPI Center Performance",
    page_icon="🎯",
    layout="wide"
)

# =============================================================================
# IMPORTS
# =============================================================================
from utils.auth import AuthManager
from utils.db import check_db_connection

# Import from refactored module
from utils.kpi_center_performance import (
    # NEW v4.0.0 - Core classes
    UnifiedDataLoader,
    DataProcessor,
    
    # Existing classes
    AccessControl,
    KPICenterQueries,
    KPICenterMetrics,
    KPICenterFilters,
    KPICenterCharts,
    KPICenterExport,
    
    # Filter helpers
    analyze_period,
    
    # Fragments
    monthly_trend_fragment,
    yoy_comparison_fragment,
    sales_detail_fragment,
    pivot_analysis_fragment,
    backlog_list_fragment,
    backlog_by_etd_fragment,
    backlog_risk_analysis_fragment,
    kpi_assignments_fragment,
    kpi_progress_fragment,
    kpi_center_ranking_fragment,
    top_performers_fragment,
    export_report_fragment,
    
    # Setup
    setup_tab_fragment,
    
    # Constants
    ALLOWED_ROLES,
    DEBUG_TIMING,
    CACHE_KEY_UNIFIED,
    CACHE_KEY_TIMING,
    CACHE_KEY_FILTERS,
)

logger = logging.getLogger(__name__)

# =============================================================================
# TIMING UTILITIES
# =============================================================================

def _init_timing():
    """Initialize timing storage in session state."""
    if CACHE_KEY_TIMING not in st.session_state:
        st.session_state[CACHE_KEY_TIMING] = []


def _reset_timing():
    """Reset timing data for new page load."""
    st.session_state[CACHE_KEY_TIMING] = []


@contextmanager
def timer(name: str):
    """
    Context manager to time code blocks.
    
    Usage:
        with timer("DB: get_sales_data"):
            data = queries.get_sales_data(...)
    """
    _init_timing()
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed = time.perf_counter() - start
        if DEBUG_TIMING:
            print(f"⏱️ [{name}] {elapsed:.3f}s")
        st.session_state[CACHE_KEY_TIMING].append({
            'name': name,
            'time': elapsed
        })


def _print_timing_summary():
    """Print formatted timing summary at end of page load."""
    if not DEBUG_TIMING:
        return
    
    timing_data = st.session_state.get(CACHE_KEY_TIMING, [])
    if not timing_data:
        return
    
    total_time = sum(t['time'] for t in timing_data)
    
    print(f"\n{'='*60}")
    print(f"📊 TIMING SUMMARY")
    print(f"{'='*60}")
    
    sorted_data = sorted(timing_data, key=lambda x: x['time'], reverse=True)
    
    for item in sorted_data:
        pct = (item['time'] / total_time * 100) if total_time > 0 else 0
        bar = '█' * int(pct / 5) + '░' * (20 - int(pct / 5))
        print(f"{item['name']:<45} {item['time']:>6.3f}s ({pct:>5.1f}%) {bar}")
    
    print(f"{'-'*60}")
    print(f"{'TOTAL':<45} {total_time:>6.3f}s")
    print(f"{'='*60}\n")


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _clean_dataframe_for_display(df: pd.DataFrame) -> pd.DataFrame:
    """Clean dataframe to avoid Arrow serialization errors."""
    if df.empty:
        return df
    
    df_clean = df.copy()
    
    # Year columns should be int
    year_columns = ['etd_year', 'oc_year', 'invoice_year', 'year']
    for col in year_columns:
        if col in df_clean.columns:
            df_clean[col] = pd.to_numeric(df_clean[col], errors='coerce').fillna(0).astype(int)
    
    # Numeric columns
    numeric_columns = ['days_until_etd', 'days_since_order', 'split_rate_percent']
    for col in numeric_columns:
        if col in df_clean.columns:
            df_clean[col] = pd.to_numeric(df_clean[col], errors='coerce')
    
    return df_clean


def calculate_weighted_count(df: pd.DataFrame, split_col: str = 'split_rate_percent') -> float:
    """
    Calculate weighted count from split percentages.
    
    Each record represents a (entity, item) combo.
    The count is weighted by split_rate_percent / 100.
    Example: If KPI Center has 50% split on a new customer, they get 0.5 credit.
    
    Args:
        df: DataFrame with individual records
        split_col: Column containing split percentage
        
    Returns:
        Weighted count (float)
    """
    if df.empty:
        return 0.0
    if split_col not in df.columns:
        return float(len(df))
    return df[split_col].fillna(100).sum() / 100


def get_selected_kpi_types(filter_values: dict, kpi_center_df: pd.DataFrame) -> list:
    """
    Derive selected_kpi_types for dedupe logic.
    
    KPI Type filter is single selection to prevent double counting.
    """
    kpi_type_filter = filter_values.get('kpi_type_filter')
    if kpi_type_filter:
        return [kpi_type_filter]
    return ['TERRITORY']  # Default


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
# FILTER STATE MANAGEMENT
# =============================================================================

def _get_applied_filters() -> dict:
    """Get currently applied filters from session state."""
    return st.session_state.get(CACHE_KEY_FILTERS)


def _set_applied_filters(filter_values: dict):
    """Store applied filters in session state."""
    st.session_state[CACHE_KEY_FILTERS] = filter_values


# =============================================================================
# MAIN PAGE
# =============================================================================

def main():
    """Main page function."""
    
    # Reset timing for new page load
    _reset_timing()
    
    # Check access
    access = check_access()
    
    # Page header
    st.title("🎯 KPI Center Performance")
    st.caption(f"Logged in as: {st.session_state.get('user_fullname', 'User')} ({st.session_state.get('user_role', '')})")
    
    # =========================================================================
    # STEP 1: LOAD UNIFIED RAW DATA (cached)
    # =========================================================================
    # This replaces both load_lookup_data() and load_data_for_year_range()
    # Single source of truth for all data
    
    with timer("Load unified raw data"):
        loader = UnifiedDataLoader(access)
        unified_cache = loader.get_unified_data()
    
    # Check if data loaded successfully
    if unified_cache.get('sales_raw_df') is None or unified_cache['sales_raw_df'].empty:
        st.error("Failed to load data. Please try refreshing the page.")
        if DEBUG_TIMING:
            _print_timing_summary()
        st.stop()
    
    # =========================================================================
    # STEP 2: EXTRACT FILTER OPTIONS (from cache - instant)
    # =========================================================================
    
    with timer("Extract filter options"):
        filter_options = loader.extract_filter_options(unified_cache)
    
    # =========================================================================
    # STEP 3: RENDER SIDEBAR FILTERS
    # =========================================================================
    
    # Initialize query helper (still needed for some operations)
    queries = KPICenterQueries(access)
    filters = KPICenterFilters(access)
    
    with timer("Render sidebar filters"):
        filter_values = filters.render_sidebar_filters(
            kpi_center_df=filter_options['kpi_centers'],
            entity_df=filter_options['entities'],
            available_years=filter_options['years'],
            kpi_types_with_assignment=filter_options['kpi_types_with_assignment'],
        )
    
    # Validate filters
    is_valid, error_msg = filters.validate_filters(filter_values)
    if not is_valid:
        st.error(f"⚠️ Filter error: {error_msg}")
        st.stop()
    
    if DEBUG_TIMING:
        print(f"\n🔍 Filters applied: {filter_values.get('period_type')} {filter_values.get('year')}")
    
    # =========================================================================
    # STEP 4: MANAGE FILTER STATE
    # =========================================================================
    
    # Initialize or update applied filters
    if _get_applied_filters() is None:
        _set_applied_filters(filter_values)
    
    if filter_values.get('submitted', False):
        _set_applied_filters(filter_values)
    
    active_filters = _get_applied_filters()
    
    # Expand KPI Center IDs with children
    if active_filters.get('kpi_center_ids'):
        expanded_ids = loader.expand_kpi_center_ids_with_children(
            active_filters['kpi_center_ids']
        )
        active_filters['kpi_center_ids_expanded'] = expanded_ids
    
    # =========================================================================
    # STEP 5: PROCESS DATA (Pandas - instant)
    # =========================================================================
    # This replaces filter_data_client_side()
    
    with timer("Process data (Pandas)"):
        processor = DataProcessor(unified_cache)
        data = processor.process(active_filters)
    
    # Log data sizes
    if DEBUG_TIMING:
        for key, val in data.items():
            if not key.startswith('_') and isinstance(val, pd.DataFrame):
                print(f"   → {key}: {len(val):,} rows")
    
    # Extract main DataFrames
    sales_df = data.get('sales_df', pd.DataFrame())
    targets_df = data.get('targets_df', pd.DataFrame())
    backlog_df = data.get('backlog_detail_df', pd.DataFrame())
    prev_sales_df = data.get('prev_sales_df', pd.DataFrame())
    
    # =========================================================================
    # STEP 6: CHECK DATA AVAILABILITY
    # =========================================================================
    
    if sales_df.empty and backlog_df.empty:
        st.warning("No data found for the selected filters. Try adjusting your selection.")
        if DEBUG_TIMING:
            _print_timing_summary()
        st.stop()
    
    # Info message if no sales but have backlog
    if sales_df.empty and not backlog_df.empty:
        st.info(f"📊 No sales data for the selected period, but showing {len(backlog_df):,} backlog records.")
    
    # =========================================================================
    # STEP 7: CALCULATE METRICS
    # =========================================================================
    
    if DEBUG_TIMING:
        print(f"\n📈 CALCULATING METRICS...")
    
    with timer("Metrics: KPICenterMetrics init"):
        metrics_calc = KPICenterMetrics(sales_df, targets_df)
    
    with timer("Metrics: calculate_overview_metrics"):
        overview_metrics = metrics_calc.calculate_overview_metrics(
            period_type=active_filters['period_type'],
            year=active_filters['year'],
            start_date=active_filters['start_date'],
            end_date=active_filters['end_date']
        )
    
    # =========================================================================
    # COMPLEX KPIs
    # =========================================================================
    
    new_customers_df = data.get('new_customers_df', pd.DataFrame())
    new_products_df = data.get('new_products_df', pd.DataFrame())
    new_business_df = data.get('new_business_df', pd.DataFrame())
    
    complex_kpis = {
        'num_new_customers': calculate_weighted_count(new_customers_df),
        'num_new_products': calculate_weighted_count(new_products_df),
        'new_business_revenue': new_business_df['new_business_revenue'].sum() if not new_business_df.empty and 'new_business_revenue' in new_business_df.columns else 0,
    }
    
    # Build complex_kpis_by_center for Overall Achievement
    complex_kpis_by_center = {}
    calculator = data.get('_complex_kpi_calculator')
    
    if calculator:
        with timer("Pandas: get_complex_kpis_by_center"):
            new_business_by_center_df = calculator.calculate_new_business_by_kpi_center(
                start_date=active_filters['start_date'],
                end_date=active_filters['end_date'],
                kpi_center_ids=active_filters.get('kpi_center_ids', []),
                entity_ids=active_filters.get('entity_ids', [])
            )
            
            new_customers_by_center_df = calculator.calculate_new_customers_by_kpi_center(
                start_date=active_filters['start_date'],
                end_date=active_filters['end_date'],
                kpi_center_ids=active_filters.get('kpi_center_ids', []),
                entity_ids=active_filters.get('entity_ids', [])
            )
            
            new_products_by_center_df = calculator.calculate_new_products_by_kpi_center(
                start_date=active_filters['start_date'],
                end_date=active_filters['end_date'],
                kpi_center_ids=active_filters.get('kpi_center_ids', []),
                entity_ids=active_filters.get('entity_ids', [])
            )
            
            # Merge into complex_kpis_by_center
            for df, key in [
                (new_business_by_center_df, 'new_business_revenue'),
                (new_customers_by_center_df, 'num_new_customers'),
                (new_products_by_center_df, 'num_new_products'),
            ]:
                if not df.empty:
                    value_col = 'new_business_revenue' if 'new_business_revenue' in df.columns else 'weighted_count'
                    for _, row in df.iterrows():
                        kpc_id = row['kpi_center_id']
                        if kpc_id not in complex_kpis_by_center:
                            complex_kpis_by_center[kpc_id] = {}
                        complex_kpis_by_center[kpc_id][key] = row.get(value_col, 0)
    
    # =========================================================================
    # PIPELINE METRICS
    # =========================================================================
    
    with timer("Metrics: calculate_pipeline_forecast"):
        pipeline_metrics = metrics_calc.calculate_pipeline_forecast_metrics(
            total_backlog_df=data.get('backlog_summary_df', pd.DataFrame()),
            in_period_backlog_df=data.get('backlog_in_period_df', pd.DataFrame()),
            period_type=active_filters['period_type'],
            year=active_filters['year'],
            start_date=active_filters['start_date'],
            end_date=active_filters['end_date']
        )
    
    # =========================================================================
    # OVERALL ACHIEVEMENT
    # =========================================================================
    
    with timer("Metrics: calculate_overall_kpi_achievement"):
        overall_achievement = metrics_calc.calculate_overall_kpi_achievement(
            period_type=active_filters['period_type'],
            year=active_filters['year'],
            start_date=active_filters['start_date'],
            end_date=active_filters['end_date'],
            complex_kpis_by_center=complex_kpis_by_center
        )
    
    # =========================================================================
    # YOY METRICS (using pre-extracted previous year data)
    # =========================================================================
    
    yoy_metrics = None
    if active_filters.get('show_yoy', True):
        with timer("Metrics: calculate_yoy_metrics"):
            yoy_metrics = metrics_calc.calculate_yoy_metrics(sales_df, prev_sales_df)
    
    # =========================================================================
    # PREPARE SUMMARIES
    # =========================================================================
    
    with timer("Metrics: prepare_monthly_summary"):
        monthly_df = processor.prepare_monthly_summary(sales_df)
    
    with timer("Metrics: aggregate_by_kpi_center"):
        kpi_center_summary_df = processor.aggregate_by_kpi_center(sales_df)
    
    period_info = analyze_period(active_filters)
    
    # Filter summary
    filter_summary = filters.get_filter_summary(active_filters)
    st.caption(f"📊 {filter_summary}")
    
    if DEBUG_TIMING:
        print(f"\n🖼️ RENDERING UI...")
    
    # =========================================================================
    # TABS
    # =========================================================================
    
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "📊 Overview",
        "📋 Sales Detail",
        "📈 Analysis",
        "📦 Backlog",
        "🎯 KPI & Targets",
        "⚙️ Setup"
    ])
    
    # =========================================================================
    # TAB 1: OVERVIEW
    # =========================================================================
    
    with tab1:
        # KPI Cards
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
        
        # Monthly Trend
        monthly_trend_fragment(
            sales_df=sales_df,
            filter_values=active_filters,
            targets_df=targets_df,
            fragment_key="kpc_trend"
        )
        
        st.divider()
        
        # Year-over-Year Comparison
        if active_filters.get('show_yoy', True):
            yoy_comparison_fragment(
                queries=queries,
                filter_values=active_filters,
                current_year=active_filters['year'],
                sales_df=sales_df,
                raw_cached_data=unified_cache,  # Pass unified cache
                fragment_key="kpc_yoy"
            )
            
            st.divider()
        
        # Backlog & Forecast
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
| **In-Period (KPI)** | `Σ backlog WHERE ETD in period` | Backlog expected to ship in period |
| **Target** | `Σ prorated_target` | Sum of prorated annual targets |
| **Forecast (KPI)** | `Invoiced + In-Period` | Projected total |
| **GAP/Surplus** | `Forecast - Target` | Positive = ahead, Negative = behind |
                    """)
            
            # Overdue warning
            backlog_risk = data.get('backlog_risk', {})
            if backlog_risk and backlog_risk.get('overdue_orders', 0) > 0:
                overdue_orders = backlog_risk.get('overdue_orders', 0)
                overdue_revenue = backlog_risk.get('overdue_revenue', 0)
                st.warning(f"⚠️ {overdue_orders} orders are past ETD. Value: ${overdue_revenue:,.0f}")
            
            # Pipeline metrics display
            summary_metrics = pipeline_metrics.get('summary', {})
            gp1_gp_ratio = summary_metrics.get('gp1_gp_ratio', 1.0)
            if gp1_gp_ratio != 1.0:
                st.caption(f"📊 GP1 backlog estimated using GP1/GP ratio: {gp1_gp_ratio:.2%}")
            
            chart_backlog_metrics = KPICenterCharts.convert_pipeline_to_backlog_metrics(pipeline_metrics)
            
            revenue_metrics = pipeline_metrics.get('revenue', {})
            gp_metrics = pipeline_metrics.get('gross_profit', {})
            gp1_metrics = pipeline_metrics.get('gp1', {})
            
            bf_tab1, bf_tab2, bf_tab3 = st.tabs(["💰 Revenue", "📈 Gross Profit", "📊 GP1"])
            
            with bf_tab1:
                _render_backlog_forecast_tab(
                    summary_metrics, revenue_metrics, 'revenue',
                    chart_backlog_metrics=chart_backlog_metrics
                )
            
            with bf_tab2:
                _render_backlog_forecast_tab(
                    summary_metrics, gp_metrics, 'gp',
                    chart_backlog_metrics=chart_backlog_metrics
                )
            
            with bf_tab3:
                _render_backlog_forecast_tab(
                    summary_metrics, gp1_metrics, 'gp1',
                    chart_backlog_metrics=chart_backlog_metrics,
                    gp1_gp_ratio=gp1_gp_ratio
                )
        
        # =====================================================================
        # EXPORT SECTION - RESTORED from v3.9.0
        # =====================================================================
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
    
    # =========================================================================
    # TAB 2: SALES DETAIL
    # =========================================================================
    
    with tab2:
        if not sales_df.empty:
            sales_detail_fragment(
                sales_df=sales_df,
                fragment_key="kpc_detail"
            )
            
            st.divider()
            
            with st.expander("📊 Pivot Analysis", expanded=False):
                pivot_analysis_fragment(
                    sales_df=sales_df,
                    fragment_key="kpc_pivot"
                )
        else:
            st.info("No sales data for the selected period")
    
    # =========================================================================
    # TAB 3: ANALYSIS
    # =========================================================================
    
    with tab3:
        top_performers_fragment(
            sales_df=sales_df,
            filter_values=active_filters,
            metrics_calculator=metrics_calc
        )
    
    # =========================================================================
    # TAB 4: BACKLOG
    # =========================================================================
    
    with tab4:
        col_bl_header, col_bl_help = st.columns([6, 1])
        with col_bl_header:
            st.subheader("📦 Backlog Analysis")
        with col_bl_help:
            with st.popover("ℹ️ Help"):
                st.markdown("""
**📦 Backlog Analysis**

| Metric | Description |
|--------|-------------|
| **Total Backlog** | All pending orders (not yet invoiced) |
| **In-Period** | Orders with ETD within selected date range |
| **On Track** | In-period orders with ETD ≥ today |
| **Overdue** | In-period orders with ETD < today |

**Risk Categories:**
- 🔴 **Overdue**: ETD has passed
- 🟠 **This Week**: ETD within 7 days
- 🟡 **This Month**: ETD within 30 days
- 🟢 **On Track**: ETD > 30 days
                """)
        
        if backlog_df.empty:
            st.info("📦 No backlog data available")
        else:
            in_period_analysis = KPICenterMetrics.analyze_in_period_backlog(
                backlog_detail_df=backlog_df,
                start_date=active_filters.get('start_date', date.today()),
                end_date=active_filters.get('end_date', date.today())
            )
            
            if in_period_analysis.get('overdue_warning'):
                st.warning(in_period_analysis['overdue_warning'])
            
            backlog_tab1, backlog_tab2, backlog_tab3 = st.tabs([
                "📋 Backlog List",
                "📅 By ETD",
                "⚠️ Risk Analysis"
            ])
            
            with backlog_tab1:
                backlog_list_fragment(
                    backlog_df=backlog_df,
                    filter_values=active_filters,
                    total_backlog_df=data.get('backlog_summary_df', pd.DataFrame())
                )
            
            with backlog_tab2:
                backlog_by_etd_fragment(
                    backlog_detail_df=backlog_df,
                    current_year=active_filters.get('year', date.today().year),
                    fragment_key="kpc_backlog_etd"
                )
            
            with backlog_tab3:
                backlog_risk_analysis_fragment(
                    backlog_df=backlog_df,
                    fragment_key="kpc_backlog_risk"
                )
    
    # =========================================================================
    # TAB 5: KPI & TARGETS
    # =========================================================================
    
    with tab5:
        st.subheader("🎯 KPI & Targets")
        
        if targets_df.empty:
            st.info("No KPI targets assigned for selected KPI Centers and year")
        else:
            hierarchy_df = queries.get_hierarchy_with_levels(
                kpi_type=active_filters.get('kpi_type', 'TERRITORY')
            )
            
            selected_kpc_ids = active_filters.get('kpi_center_ids', [])
            if selected_kpc_ids:
                all_relevant_ids = set(selected_kpc_ids)
                for kpc_id in selected_kpc_ids:
                    all_relevant_ids.update(queries.get_ancestors(kpc_id, include_self=True))
                    all_relevant_ids.update(queries.get_all_descendants(kpc_id, include_self=True))
                hierarchy_df = hierarchy_df[hierarchy_df['kpi_center_id'].isin(all_relevant_ids)]
            
            rollup_targets = metrics_calc.calculate_rollup_targets(
                hierarchy_df=hierarchy_df,
                queries_instance=queries
            )
            
            progress_data = metrics_calc.calculate_per_center_progress(
                hierarchy_df=hierarchy_df,
                queries_instance=queries,
                period_type=active_filters['period_type'],
                year=active_filters['year'],
                start_date=active_filters['start_date'],
                end_date=active_filters['end_date'],
                complex_kpis_by_center=complex_kpis_by_center
            )
            
            kpi_tab1, kpi_tab2, kpi_tab3 = st.tabs([
                "📊 My KPIs",
                "📈 Progress",
                "🏆 Ranking"
            ])
            
            with kpi_tab1:
                st.markdown("#### 📊 KPI Assignments")
                kpi_assignments_fragment(
                    rollup_targets=rollup_targets,
                    hierarchy_df=hierarchy_df,
                    fragment_key="kpc_assignments"
                )
            
            with kpi_tab2:
                st.markdown("#### 📈 KPI Progress")
                kpi_progress_fragment(
                    progress_data=progress_data,
                    hierarchy_df=hierarchy_df,
                    period_type=active_filters['period_type'],
                    year=active_filters['year'],
                    fragment_key="kpc_progress"
                )
            
            with kpi_tab3:
                st.markdown("#### 🏆 KPI Center Ranking")
                kpi_center_ranking_fragment(
                    ranking_df=kpi_center_summary_df,
                    progress_data=progress_data,
                    hierarchy_df=hierarchy_df,
                    show_targets=not targets_df.empty
                )
    
    # =========================================================================
    # TAB 6: SETUP
    # =========================================================================
    
    with tab6:
        setup_tab_fragment(
            kpi_center_ids=active_filters.get('kpi_center_ids', []),
            active_filters=active_filters
        )
    
    # =========================================================================
    # TIMING SUMMARY
    # =========================================================================
    
    if DEBUG_TIMING:
        print(f"✅ PAGE RENDER COMPLETE")
        print(f"{'='*60}")
    _print_timing_summary()


# =============================================================================
# HELPER: BACKLOG FORECAST TAB RENDERING
# RESTORED v4.0.1: Added charts (waterfall + gap analysis) from v3.9.0
# =============================================================================

def _render_backlog_forecast_tab(
    summary_metrics: dict, 
    kpi_metrics: dict, 
    metric_type: str,
    chart_backlog_metrics: dict = None,
    gp1_gp_ratio: float = 1.0
):
    """
    Render backlog forecast metrics AND charts for a specific tab (revenue/gp/gp1).
    
    RESTORED from v3.9.0: Now includes both metrics row AND charts row.
    
    Args:
        summary_metrics: Overall summary metrics (total_backlog_revenue, etc.)
        kpi_metrics: KPI-specific metrics (in_period_backlog, target, forecast, gap)
        metric_type: 'revenue', 'gp', or 'gp1'
        chart_backlog_metrics: Dict for chart rendering (optional)
        gp1_gp_ratio: Ratio for GP1 estimation (default 1.0)
    """
    col_m1, col_m2, col_m3, col_m4, col_m5 = st.columns(5)
    
    # Labels and keys based on type
    if metric_type == 'revenue':
        total_key = 'total_backlog_revenue'
        label_total = "Total Backlog"
        help_suffix = "revenue"
        kpi_name = "Revenue"
    elif metric_type == 'gp':
        total_key = 'total_backlog_gp'
        label_total = "Total GP Backlog"
        help_suffix = "GP"
        kpi_name = "GP"
    else:  # gp1
        total_key = 'total_backlog_gp1'
        label_total = "Total GP1 Backlog"
        help_suffix = "GP1"
        kpi_name = "GP1"
    
    with col_m1:
        help_text = f"All outstanding {help_suffix} from pending orders"
        if metric_type == 'gp1' and gp1_gp_ratio != 1.0:
            help_text = f"Estimated GP1 backlog (GP × {gp1_gp_ratio:.2%})"
        st.metric(
            label=label_total,
            value=f"${summary_metrics.get(total_key, 0):,.0f}",
            delta=f"{int(summary_metrics.get('backlog_orders', 0)):,} orders" if summary_metrics.get('backlog_orders') else None,
            delta_color="off",
            help=help_text
        )
    
    with col_m2:
        in_period = kpi_metrics.get('in_period_backlog', 0)
        target = kpi_metrics.get('target')
        pct = (in_period / target * 100) if target and target > 0 else None
        kpc_count = kpi_metrics.get('kpi_center_count', 0)
        st.metric(
            label="In-Period (KPI)",
            value=f"${in_period:,.0f}",
            delta=f"{pct:.0f}% of target" if pct else None,
            delta_color="off",
            help=f"Backlog with ETD in period. Only from {kpc_count} KPI Centers with {kpi_name} KPI."
        )
    
    with col_m3:
        target = kpi_metrics.get('target')
        kpc_count = kpi_metrics.get('kpi_center_count', 0)
        if target and target > 0:
            st.metric(
                label="Target",
                value=f"${target:,.0f}",
                delta=f"{kpc_count} KPI Centers",
                delta_color="off",
                help=f"Sum of prorated {kpi_name} targets from {kpc_count} KPI Centers"
            )
        else:
            st.metric(
                label="Target",
                value="N/A",
                delta="No KPI assigned",
                delta_color="off",
                help="No KPI target assigned"
            )
    
    with col_m4:
        forecast = kpi_metrics.get('forecast')
        achievement = kpi_metrics.get('forecast_achievement')
        if forecast is not None:
            delta_color = "normal" if achievement and achievement >= 100 else "inverse"
            st.metric(
                label="Forecast (KPI)",
                value=f"${forecast:,.0f}",
                delta=f"{achievement:.0f}% of target" if achievement else None,
                delta_color=delta_color if achievement else "off",
                help="Invoiced + In-Period Backlog"
            )
        else:
            st.metric(
                label="Forecast (KPI)",
                value="N/A",
                delta="No target",
                delta_color="off",
                help="No KPI target assigned"
            )
    
    with col_m5:
        gap = kpi_metrics.get('gap')
        gap_pct = kpi_metrics.get('gap_percent')
        if gap is not None:
            gap_label = "Surplus ✅" if gap >= 0 else "GAP ⚠️"
            delta_color = "normal" if gap >= 0 else "inverse"
            st.metric(
                label=gap_label,
                value=f"${gap:+,.0f}",
                delta=f"{gap_pct:+.1f}%" if gap_pct else None,
                delta_color=delta_color,
                help="Forecast - Target. Positive = ahead, Negative = behind."
            )
        else:
            st.metric(
                label="GAP",
                value="N/A",
                delta="No target",
                delta_color="off",
                help="No KPI target assigned"
            )
    
    # =========================================================================
    # CHARTS ROW - RESTORED from v3.9.0
    # =========================================================================
    if chart_backlog_metrics:
        col_bf1, col_bf2 = st.columns(2)
        with col_bf1:
            st.markdown(f"**{kpi_name} Forecast vs Target**")
            forecast_chart = KPICenterCharts.build_forecast_waterfall_chart(
                backlog_metrics=chart_backlog_metrics,
                metric=metric_type,
                title=""
            )
            st.altair_chart(forecast_chart, use_container_width=True)
        with col_bf2:
            st.markdown(f"**{kpi_name}: Target vs Forecast**")
            gap_chart = KPICenterCharts.build_gap_analysis_chart(
                backlog_metrics=chart_backlog_metrics,
                metrics_to_show=[metric_type],
                title=""
            )
            st.altair_chart(gap_chart, use_container_width=True)


# =============================================================================
# RUN
# =============================================================================

if __name__ == "__main__":
    main()
else:
    main()