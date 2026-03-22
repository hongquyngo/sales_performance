# pages/2_🎯_KPI_Center_Performance.py
"""
KPI Center Performance Dashboard

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
    KPICenterExport,
    
    # NEW v4.6.0 - Tab-level fragment for Overview
    overview_tab_fragment,
    
    # Fragments - Analysis tab
    analysis_tab_fragment,
    
    # Fragments - KPI & Targets tab
    kpi_assignments_fragment,
    kpi_progress_fragment,
    kpi_center_ranking_fragment,
    
    # Tab-level fragment wrappers
    sales_detail_tab_fragment,
    backlog_tab_fragment,
    
    # Setup
    setup_tab_fragment,
    
    # Payment & Collection — NEW v6.1.0
    _PAYMENT_AVAILABLE,
    payment_tab_fragment,
    generate_doc_url,
    
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
    return df[split_col].fillna(0).sum() / 100  # Fix: NULL split_rate should not get credit


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
    # STEP 1: LOAD UNIFIED RAW DATA (cached) - Initial load
    # =========================================================================
    # This replaces both load_lookup_data() and load_data_for_year_range()
    # Single source of truth for all data
    # 
    # NEW v4.1.0: Dynamic Loading support
    # - Initial load uses default range
    # - After filters rendered, check if extended range needed and reload
    
    with timer("Load unified raw data (initial)"):
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
    # STEP 4.1: DYNAMIC RELOAD IF CUSTOM PERIOD REQUIRES EXTENDED DATA
    # =========================================================================
    # Check if current filter requires data beyond cached range
    # This handles the case where user selects Custom period before default range
    
    custom_start_date = active_filters.get('custom_start_date')
    if custom_start_date:
        # Check if reload needed
        cache_range = loader.get_cached_data_range()
        if cache_range:
            cached_start = cache_range.get('lookback_start')
            if cached_start and custom_start_date < cached_start:
                with timer("Load unified raw data (extended range)"):
                    unified_cache = loader.get_unified_data(custom_start_date=custom_start_date)
                
                if DEBUG_TIMING:
                    print(f"📅 Extended data loaded: {custom_start_date} → {cached_start} (was cached)")
    
    # Show info if extended data was loaded
    cache_range = loader.get_cached_data_range()
    if cache_range and custom_start_date:
        from utils.kpi_center_performance.constants import LOOKBACK_YEARS, MIN_DATA_YEAR
        default_start = date(max(date.today().year - LOOKBACK_YEARS, MIN_DATA_YEAR), 1, 1)
        actual_start = cache_range.get('lookback_start')
        if actual_start and actual_start < default_start:
            st.info(
                f"📅 Extended data loaded from **{actual_start.strftime('%Y-%m-%d')}** "
                f"(default: {default_start.strftime('%Y-%m-%d')})"
            )
    
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
        # v5.0.0: Pass default_weights from DB for parent rollup calculations
        # v5.2.0: Pass hierarchy_df for recursive rollup with stop condition
        default_weights = loader.get_default_weights()
        hierarchy_df = unified_cache.get('hierarchy_df', pd.DataFrame())
        metrics_calc = KPICenterMetrics(
            sales_df, 
            targets_df, 
            default_weights=default_weights,
            hierarchy_df=hierarchy_df
        )
    
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
        # v4.6.1: Use pre-calculated values from data_processor (single source of truth)
        'num_new_customers': data.get('num_new_customers', 0) or calculate_weighted_count(new_customers_df),
        'num_new_products': data.get('num_new_products', 0) or calculate_weighted_count(new_products_df),
        'num_new_combos': data.get('num_new_combos', 0),  # NEW v4.7.0
        'new_business_revenue': data.get('new_business_revenue', 0) or (new_business_df['new_business_revenue'].sum() if not new_business_df.empty and 'new_business_revenue' in new_business_df.columns else 0),
    }
    
    # DEBUG v4.6.1: Track what's being used
    print(f"   🔍 [DEBUG main_page] data.get('num_new_customers') = {data.get('num_new_customers', 'NOT_FOUND')}")
    print(f"   🔍 [DEBUG main_page] data.get('num_new_products') = {data.get('num_new_products', 'NOT_FOUND')}")
    print(f"   🔍 [DEBUG main_page] data.get('num_new_combos') = {data.get('num_new_combos', 'NOT_FOUND')}")
    print(f"   🔍 [DEBUG main_page] complex_kpis['num_new_customers'] = {complex_kpis['num_new_customers']}")
    print(f"   🔍 [DEBUG main_page] complex_kpis['num_new_products'] = {complex_kpis['num_new_products']}")
    print(f"   🔍 [DEBUG main_page] complex_kpis['num_new_combos'] = {complex_kpis['num_new_combos']}")
    
    # Build complex_kpis_by_center for Overall Achievement
    complex_kpis_by_center = {}
    # v4.5.0: Get pre-calculated *_by_center DataFrames (no duplicate calculation)
    with timer("Build: complex_kpis_by_center dict"):
        new_business_by_center_df = data.get('new_business_by_center_df', pd.DataFrame())
        new_customers_by_center_df = data.get('new_customers_by_center_df', pd.DataFrame())
        new_products_by_center_df = data.get('new_products_by_center_df', pd.DataFrame())
        new_combos_by_center_df = data.get('new_combos_by_center_df', pd.DataFrame())  # FIX v6.0.1: Add combos
        
        # Merge into complex_kpis_by_center
        for df, key in [
            (new_business_by_center_df, 'new_business_revenue'),
            (new_customers_by_center_df, 'num_new_customers'),
            (new_products_by_center_df, 'num_new_products'),
            (new_combos_by_center_df, 'num_new_combos'),  # FIX v6.0.1: Add combos to progress
        ]:
            if not df.empty:
                # Detect value column: each df uses different column name
                if 'new_business_revenue' in df.columns:
                    value_col = 'new_business_revenue'
                elif 'combo_count' in df.columns:
                    value_col = 'combo_count'
                else:
                    value_col = 'weighted_count'
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
        # v5.0.0: Pass selected_kpi_center_ids for scenario detection (assigned vs default weight)
        overall_achievement = metrics_calc.calculate_overall_kpi_achievement(
            period_type=active_filters['period_type'],
            year=active_filters['year'],
            start_date=active_filters['start_date'],
            end_date=active_filters['end_date'],
            complex_kpis_by_center=complex_kpis_by_center,
            selected_kpi_center_ids=active_filters.get('kpi_center_ids', [])
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
    
    # Filter summary
    filter_summary = filters.get_filter_summary(active_filters)
    st.caption(f"📊 {filter_summary}")
    
    if DEBUG_TIMING:
        print(f"\n🖼️ RENDERING UI...")
    
    # =========================================================================
    # TABS
    # =========================================================================
    
    if _PAYMENT_AVAILABLE:
        tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
            "📊 Overview",
            "📋 Sales Detail",
            "📈 Analysis",
            "📦 Backlog",
            "💰 Payment",
            "🎯 KPI & Targets",
            "⚙️ Setup"
        ])
    else:
        tab1, tab2, tab3, tab4, tab6, tab7 = st.tabs([
            "📊 Overview",
            "📋 Sales Detail",
            "📈 Analysis",
            "📦 Backlog",
            "🎯 KPI & Targets",
            "⚙️ Setup"
        ])
        tab5 = None  # Payment tab not available
    
    # =========================================================================
    # TAB 1: OVERVIEW
    # =========================================================================
    
    with tab1:
        overview_tab_fragment(
            # Data
            sales_df=sales_df,
            targets_df=targets_df,
            data=data,
            # Metrics
            overview_metrics=overview_metrics,
            yoy_metrics=yoy_metrics,
            complex_kpis=complex_kpis,
            pipeline_metrics=pipeline_metrics,
            overall_achievement=overall_achievement,
            # Filters & Config
            active_filters=active_filters,
            queries=queries,
            unified_cache=unified_cache,
            # Summaries
            monthly_df=monthly_df,
            kpi_center_summary_df=kpi_center_summary_df,
        )
    
    # =========================================================================
    # TAB 2: SALES DETAIL
    # =========================================================================
    
    with tab2:
        sales_detail_tab_fragment(
            sales_df=sales_df,
            filter_values=active_filters,
            key_prefix="sales_tab"
        )
    
    # =========================================================================
    # TAB 3: ANALYSIS
    # =========================================================================
    
    with tab3:
        analysis_tab_fragment(
            sales_df=sales_df,
            prev_sales_df=prev_sales_df,
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
        
        backlog_tab_fragment(
            backlog_df=backlog_df,
            filter_values=active_filters,
            key_prefix="backlog_tab"
        )
    
    # =========================================================================
    # TAB 5: PAYMENT & COLLECTION — NEW v6.1.0
    # =========================================================================
    
    if _PAYMENT_AVAILABLE and tab5 is not None:
      with tab5:
        st.subheader("💰 Payment & Collection")
        
        ar_outstanding_df = pd.DataFrame()
        period_payment_df = pd.DataFrame()
        
        try:
            kpc_ids = active_filters.get('kpi_center_ids_expanded',
                                         active_filters.get('kpi_center_ids', []))
            entity_ids = active_filters.get('entity_ids', [])
            
            with timer("Load: AR outstanding data"):
                ar_outstanding_df = queries.get_ar_outstanding_data(
                    kpi_center_ids=kpc_ids,
                    entity_ids=entity_ids,
                )
            
            with timer("Load: Period payment data"):
                period_payment_df = queries.get_payment_period_data(
                    start_date=active_filters['start_date'],
                    end_date=active_filters['end_date'],
                    kpi_center_ids=kpc_ids,
                    entity_ids=entity_ids,
                )
        except Exception as e:
            logger.warning(f"Payment data not available: {e}")
            st.info(
                "💰 Payment data requires `customer_ar_by_kpi_center_view` "
                "to be configured in the database."
            )
        
        if not ar_outstanding_df.empty or not period_payment_df.empty:
            def _load_payment_txns(inv_numbers):
                return queries.get_payment_transactions(inv_numbers)
            
            def _load_invoice_docs(inv_numbers):
                return queries.get_invoice_documents(inv_numbers)
            
            s3_url_gen = None
            try:
                s3_url_gen = generate_doc_url
            except Exception:
                pass
            
            payment_tab_fragment(
                sales_df=sales_df,
                filter_values=active_filters,
                key_prefix="kpc_payment",
                ar_outstanding_df=ar_outstanding_df,
                period_payment_df=period_payment_df,
                payment_txn_loader=_load_payment_txns,
                doc_loader=_load_invoice_docs,
                s3_url_generator=s3_url_gen,
            )
        elif ar_outstanding_df.empty and period_payment_df.empty:
            # Only show this if the try block didn't already show an error
            pass
    
    # =========================================================================
    # TAB 6: KPI & TARGETS
    # =========================================================================
    
    with tab6:
        st.subheader("🎯 KPI & Targets")
        
        if targets_df.empty:
            st.info("No KPI targets assigned for selected KPI Centers and year")
        else:
            hierarchy_df = queries.get_hierarchy_with_levels(
                kpi_type=active_filters.get('kpi_type_filter', 'TERRITORY')
            )
            
            # v5.3.0: Only show selected center + descendants (not ancestors)
            # - Leaf node: show only itself
            # - Parent node: show itself + all children
            selected_kpc_ids = active_filters.get('kpi_center_ids', [])
            if selected_kpc_ids:
                all_relevant_ids = set(selected_kpc_ids)
                for kpc_id in selected_kpc_ids:
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
    # TAB 7: SETUP
    # =========================================================================
    
    with tab7:
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
# RUN
# =============================================================================

if __name__ == "__main__":
    main()
else:
    main()