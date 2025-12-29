# pages/2_🎯_KPI_Center_Performance.py
"""
KPI Center Performance Dashboard

VERSION: 3.3.2
CHANGELOG:
- v3.3.2: SYNCED Overall Achievement in Overview tab:
          - Now uses target-proportion weights (same as Progress tab)
          - complex_kpis_by_center built once, shared between tabs
          - Updated tooltip to explain calculation method
          - Removed duplicate code from KPI & Targets tab
- v3.3.0: FIXED New Business Revenue = 0 in KPI Progress tab:
          - Root Cause: complex_kpis_by_center was always None
          - Solution: Build complex_kpis_by_center dict from new queries:
            * get_new_business_by_kpi_center()
            * get_new_customers_by_kpi_center()
            * get_new_products_by_kpi_center()
          - Now Complex KPIs (New Business, New Customers, New Products)
            show correct values per KPI Center in Progress tab
          - Requires: queries.py v3.3.0
- v3.2.0: ENHANCED KPI & Targets tab with hierarchy support:
          - My KPIs: Shows rollup targets for parent KPI Centers
            * Leaf nodes: Direct assignments with weight
            * Parent nodes: Aggregated from all descendants (+ own if Mixed)
            * Level filter, help popover with formula explanation
          - Progress: Per-center KPI progress with overall achievement
            * Leaf nodes: Individual KPI progress bars
            * Parent nodes: Weighted average of children's achievements
            * View filter (All/Leaf/Parents)
          - Ranking: Group by hierarchy level for fair comparison
            * Only shows levels with ≥2 items (to rank)
            * Medals within each level
            * Level filter (All grouped/specific level/Leaf)
          - NEW queries: get_hierarchy_with_levels(), get_all_descendants(),
            get_leaf_descendants(), get_ancestors()
          - NEW metrics: calculate_rollup_targets(), calculate_per_center_progress()
          - Requires: queries.py v3.2.0, metrics.py v3.2.0, fragments.py v3.2.0
- v3.1.0: SYNCED KPI & Targets tab with Salesperson module:
          - Tab 5 now has 3 sub-tabs: My KPIs, Progress, Ranking
          - My KPIs: Improved assignments view with icons, better formatting
          - Progress: Progress bars with achievement %, prorated targets, color-coded badges
          - Ranking: Added medals (🥇🥈🥉), sortable dropdown like Salesperson
          - Added kpi_assignments_fragment, kpi_progress_fragment
          - Updated kpi_center_ranking_fragment with medals
          - Added metrics.get_kpi_progress_data(), metrics._get_prorated_target()
          - Requires updated fragments.py v3.1.0, metrics.py v3.1.0
- v3.0.1: BUGFIX backlog_by_etd_fragment not filtering by KPI Center:
          - Problem: backlog_by_month_df was pre-aggregated without kpi_center_id,
            client-side filter couldn't work
          - Solution: Pass backlog_detail_df (already filtered) to fragment,
            fragment aggregates data itself
- v3.0.0: SYNCED Backlog tab with Salesperson module:
          - Tab 4 now has 3 sub-tabs: Backlog List, By ETD, Risk Analysis
          - Backlog List: 7 summary cards, 5 filters with Excl option
          - By ETD: 3 view modes (Timeline/Stacked/Single Year) with charts
          - Risk Analysis: 4 risk cards (Overdue/This Week/This Month/On Track) + Overdue table
          - Warning banner shows when overdue orders exist
          - Full parity with Salesperson Backlog Analysis
          - Requires updated fragments.py v3.0.0, metrics.py, charts.py
- v2.14.0: ADDED exclude_internal support for Backlog and Complex KPIs:
          - Business Rule: "Exclude Internal Revenue" checkbox now affects ALL metrics consistently
          - Backlog queries: Revenue = 0 for Internal customers, GP kept (same as Sales)
          - Complex KPIs: Internal customers excluded entirely from New Customers, New Products, New Business
          - Updated load_data_for_year_range() to pass exclude_internal to all relevant queries
          - Updated _needs_data_reload() to check exclude_internal changes
          - Updated get_or_load_data() to pass exclude_internal from filter_values
          - Requires updated queries.py v2.14.0
- v2.10.0: SYNCED Sales Detail tab with Salesperson page:
          - Added sub-tabs: "📄 Transaction List" and "📊 Pivot Analysis"
          - Each sub-tab is a fragment for better performance
          - Transaction List: 7 summary cards, 5 filters with Excl, original values
          - Pivot Analysis: Default to Gross Profit, same styling as SP
- v2.9.1: FIXED Exclude Internal Revenue logic in load_yoy_data():
          - Business rule: Internal sales → Revenue = 0, GP/GP1 kept (real profit)
          - Previous: Filtered out rows entirely (lost GP/GP1 for YoY comparison)
          - Now: Set revenue = 0, keep rows for GP/GP1 calculation
          - Consistent with filter_data_client_side() logic
- v2.9.0: FIXED Complex KPIs (New Business) not reflecting filter changes:
          - Issue: New Customers/Products/Business Revenue not updating when 
            KPI Center, KPI Type, or Legal Entity filters changed
          - Root cause 1: _needs_data_reload() didn't check entity_ids changes
          - Root cause 2: load_data_for_year_range() didn't pass entity_ids to complex KPIs
          - Fix: Added entity_ids check in _needs_data_reload()
          - Fix: Pass entity_ids to all complex KPI queries
          - Fix: Store _entity_ids in cached data for reload comparison
- v2.8.0: KPI Type filter changed to SINGLE SELECTION:
          - Removed "All Types" option (filters.py v2.8.0)
          - Always single type → no double counting, no dedupe needed
          - Default: TERRITORY
          - Simplified get_selected_kpi_types() - always returns single type
- v2.7.0: FIXED Double Counting & New Business Revenue:
          - Issue #1: Added get_selected_kpi_types() helper to detect single vs multiple types
            * Single type selected → Full credit for that type (no dedupe)
            * Multiple types selected → Dedupe per entity to avoid double counting
          - Issue #2: queries.py now uses SUM() instead of MAX() for New Business Revenue
          - Updated load_data_for_year_range() to pass selected_kpi_types
          - Updated _needs_data_reload() to check kpi_type changes
          - Requires updated queries.py v2.7.0
- v2.6.0: REFACTORED Complex KPIs to match Salesperson page logic:
          - Added calculate_weighted_count() helper function
          - complex_kpis now uses weighted counting: sum(split_rate_percent) / 100
          - Requires updated queries.py and charts.py v2.6.0
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
    backlog_by_etd_fragment,        # NEW v3.0.0
    backlog_risk_analysis_fragment,  # NEW v3.0.0
    kpi_assignments_fragment,        # NEW v3.1.0
    kpi_progress_fragment,           # NEW v3.1.0
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


def calculate_weighted_count(df: pd.DataFrame, split_col: str = 'split_rate_percent') -> float:
    """
    Calculate weighted count from split percentages.
    
    NEW v2.6.0: Matches Salesperson page logic where:
    - Each record represents a (entity, item) combo
    - The count is weighted by split_rate_percent / 100
    - Example: If KPI Center has 50% split on a new customer, they get 0.5 credit
    
    Args:
        df: DataFrame with individual records (from get_new_customers/get_new_products)
        split_col: Column containing split percentage (default: 'split_rate_percent')
        
    Returns:
        Weighted count (float). Formula: sum(split_rate_percent) / 100
    """
    if df.empty:
        return 0.0
    if split_col not in df.columns:
        # If no split column, count each row as 1.0
        return float(len(df))
    # Sum of (split_rate_percent / 100), treating NULL as 100%
    return df[split_col].fillna(100).sum() / 100


def get_selected_kpi_types(filter_values: dict, kpi_center_df: pd.DataFrame) -> list:
    """
    Derive selected_kpi_types for dedupe logic.
    
    UPDATED v2.8.0: Now always returns single type (no "All Types" option).
    KPI Type filter is now single selection to prevent double counting.
    
    Args:
        filter_values: Dictionary from filters containing kpi_type_filter
        kpi_center_df: DataFrame with kpi_center_id, kpi_type columns (unused in v2.8.0)
        
    Returns:
        List with single KPI type. Always len == 1, so no dedupe needed.
    """
    kpi_type_filter = filter_values.get('kpi_type_filter')
    
    # v2.8.0: kpi_type_filter is always a single valid type (TERRITORY, VERTICAL, etc.)
    # No more "All Types" option, so this always returns a single-element list
    if kpi_type_filter:
        return [kpi_type_filter]
    
    # Fallback (shouldn't happen in v2.8.0+): return TERRITORY as default
    return ['TERRITORY']


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
    
    UPDATED v2.10.0 (Option B - Sales view + Parents):
    - KPI Center: Leaf nodes từ unified view + tất cả ancestors
    - Includes hierarchy info: parent_center_id, level, has_children
    - Parent KPI Centers now visible in dropdown for rollup selection
    
    Returns:
        Tuple of:
        - kpi_center_df: DataFrame with KPI Centers including parents + hierarchy info
        - entity_df: DataFrame with Legal Entities
        - available_years: List of years with sales data
        - kpi_center_ids_with_assignment: Set of KPI Center IDs with KPI assignment
        - kpi_types_with_assignment: Set of KPI Types with KPI assignment
    """
    from utils.db import get_db_engine
    from sqlalchemy import text
    
    engine = get_db_engine()
    
    # =========================================================================
    # 1. KPI CENTER - Option B: Sales view + All Ancestors
    #    - Lấy leaf nodes có sales từ unified view
    #    - Recursive CTE để lấy tất cả ancestors (parents)
    #    - Include hierarchy info: parent_center_id, level, has_children
    # =========================================================================
    kpi_center_query = """
        WITH RECURSIVE 
        -- Step 1: Get leaf nodes from sales data
        leaf_nodes AS (
            SELECT DISTINCT kpi_center_id
            FROM unified_sales_by_kpi_center_view
            WHERE kpi_center_id IS NOT NULL
        ),
        
        -- Step 2: Get all ancestors (parents) recursively
        all_ancestors AS (
            -- Base case: leaf nodes and their immediate parents
            SELECT kc.id AS kpi_center_id, kc.parent_center_id
            FROM kpi_centers kc
            WHERE kc.id IN (SELECT kpi_center_id FROM leaf_nodes)
              AND (kc.delete_flag = 0 OR kc.delete_flag IS NULL)
            
            UNION
            
            -- Recursive case: parent's parent, etc.
            SELECT kc.id, kc.parent_center_id
            FROM kpi_centers kc
            INNER JOIN all_ancestors aa ON kc.id = aa.parent_center_id
            WHERE kc.delete_flag = 0 OR kc.delete_flag IS NULL
        ),
        
        -- Step 3: Combine leaf nodes + ancestors into unique set
        all_relevant_ids AS (
            SELECT DISTINCT kpi_center_id FROM all_ancestors
        ),
        
        -- Step 4: Calculate level (0 = root, 1 = child, etc.)
        hierarchy_levels AS (
            -- Level 0: roots (no parent)
            SELECT 
                kc.id AS kpi_center_id,
                kc.name AS kpi_center_name,
                kc.type AS kpi_type,
                kc.parent_center_id,
                0 AS level
            FROM kpi_centers kc
            WHERE kc.id IN (SELECT kpi_center_id FROM all_relevant_ids)
              AND kc.parent_center_id IS NULL
              AND (kc.delete_flag = 0 OR kc.delete_flag IS NULL)
            
            UNION ALL
            
            -- Recursive: children
            SELECT 
                kc.id,
                kc.name,
                kc.type,
                kc.parent_center_id,
                hl.level + 1
            FROM kpi_centers kc
            INNER JOIN hierarchy_levels hl ON kc.parent_center_id = hl.kpi_center_id
            WHERE kc.id IN (SELECT kpi_center_id FROM all_relevant_ids)
              AND (kc.delete_flag = 0 OR kc.delete_flag IS NULL)
        ),
        
        -- Step 5: Determine which nodes have children
        children_count AS (
            SELECT 
                parent_center_id,
                COUNT(*) as child_count
            FROM kpi_centers
            WHERE parent_center_id IS NOT NULL
              AND id IN (SELECT kpi_center_id FROM all_relevant_ids)
              AND (delete_flag = 0 OR delete_flag IS NULL)
            GROUP BY parent_center_id
        )
        
        -- Final SELECT
        SELECT 
            hl.kpi_center_id,
            hl.kpi_center_name,
            hl.kpi_type,
            hl.parent_center_id,
            hl.level,
            CASE WHEN cc.child_count > 0 THEN 1 ELSE 0 END AS has_children
        FROM hierarchy_levels hl
        LEFT JOIN children_count cc ON hl.kpi_center_id = cc.parent_center_id
        ORDER BY hl.kpi_type, hl.level, hl.kpi_center_name
    """
    kpi_center_df = pd.read_sql(text(kpi_center_query), engine)
    
    # Convert has_children to boolean
    if not kpi_center_df.empty:
        kpi_center_df['has_children'] = kpi_center_df['has_children'].astype(bool)
        # Add description column for backward compatibility
        kpi_center_df['description'] = None
    
    # =========================================================================
    # 2. KPI CENTERS WITH KPI ASSIGNMENT - For "Only with KPI" checkbox filter
    #    Returns kpi_center_id and kpi_type for filtering both dropdowns
    # =========================================================================
    kpi_assignment_query = """
        SELECT DISTINCT 
            kac.kpi_center_id,
            kc.type AS kpi_type
        FROM sales_kpi_center_assignments_view kac
        LEFT JOIN kpi_centers kc ON kac.kpi_center_id = kc.id
        WHERE kac.kpi_center_id IS NOT NULL
    """
    kpi_assignment_df = pd.read_sql(text(kpi_assignment_query), engine)
    
    # Create set of KPI Center IDs with assignments (for filtering KPI Center dropdown)
    kpi_center_ids_with_assignment = set(
        kpi_assignment_df['kpi_center_id'].tolist()
    ) if not kpi_assignment_df.empty else set()
    
    # Create set of KPI Types that have assignments (for filtering KPI Type dropdown)
    kpi_types_with_assignment = set(
        kpi_assignment_df['kpi_type'].dropna().tolist()
    ) if not kpi_assignment_df.empty else set()
    
    # =========================================================================
    # 3. LEGAL ENTITY - Join với companies table để lấy english_name
    #    (Đảm bảo tên đồng nhất giữa data cũ và mới)
    # =========================================================================
    entity_query = """
        SELECT DISTINCT
            v.legal_entity_id AS entity_id,
            COALESCE(c.english_name, v.legal_entity) AS entity_name
        FROM unified_sales_by_kpi_center_view v
        LEFT JOIN companies c ON v.legal_entity_id = c.id
        WHERE v.legal_entity_id IS NOT NULL
        ORDER BY entity_name
    """
    entity_df = pd.read_sql(text(entity_query), engine)
    
    # =========================================================================
    # 4. AVAILABLE YEARS - From unified_sales_by_kpi_center_view
    # =========================================================================
    years_query = """
        SELECT DISTINCT CAST(invoice_year AS SIGNED) AS year
        FROM unified_sales_by_kpi_center_view
        WHERE invoice_year IS NOT NULL
        ORDER BY invoice_year DESC
    """
    years_df = pd.read_sql(text(years_query), engine)
    available_years = years_df['year'].tolist() if not years_df.empty else [datetime.now().year]
    
    # =========================================================================
    # 5. RETURN EXTENDED TUPLE
    # =========================================================================
    return (
        kpi_center_df,                      # KPI Centers with hierarchy info
        entity_df,                          # Legal Entities with english_name
        available_years,                    # Available years
        kpi_center_ids_with_assignment,     # Set of KPI Center IDs with KPI assignment
        kpi_types_with_assignment,          # Set of KPI Types with KPI assignment
    )


def load_data_for_year_range(
    queries: KPICenterQueries,
    start_year: int,
    end_year: int,
    kpi_center_ids: list,
    entity_ids: list = None,
    display_start: date = None,  # NEW: Display period start for complex KPIs
    display_end: date = None,    # NEW: Display period end for complex KPIs
    selected_kpi_types: list = None,  # NEW v2.7.0: For double-counting prevention
    exclude_internal: bool = True  # NEW v2.14.0: Exclude internal revenue/customers
) -> dict:
    """
    Load data for specified year range.
    
    Args:
        queries: KPICenterQueries instance
        start_year: Start year for cache range
        end_year: End year for cache range
        kpi_center_ids: List of KPI Center IDs to filter
        entity_ids: Optional list of entity IDs to filter
        display_start: Actual display period start date (for complex KPIs that can't be filtered client-side)
        display_end: Actual display period end date (for complex KPIs that can't be filtered client-side)
        selected_kpi_types: List of selected KPI types for dedupe logic (NEW v2.7.0)
        exclude_internal: If True, exclude internal revenue in backlog and internal customers in Complex KPIs (NEW v2.14.0)
    
    Returns:
        dict: Dictionary containing all loaded DataFrames
    
    Note:
        - Sales data uses cache period (start_year to end_year) because it CAN be filtered client-side
        - Complex KPIs (new_customers, new_products, new_business) use display period because 
          they return aggregated data WITHOUT date columns, so they CANNOT be filtered client-side
        - NEW v2.7.0: selected_kpi_types is passed to complex KPI queries for dedupe logic
        - NEW v2.14.0: exclude_internal is passed to backlog and complex KPI queries for consistent business logic
    """
    # Cache period - for data that CAN be filtered client-side
    cache_start = date(start_year, 1, 1)
    cache_end = date(end_year, 12, 31)
    
    # Display period - for complex KPIs that CANNOT be filtered client-side
    # If not provided, fall back to cache period
    kpi_start = display_start or cache_start
    kpi_end = display_end or cache_end
    
    progress_bar = st.progress(0, text=f"🔄 Loading data ({start_year}-{end_year})...")
    
    data = {}
    
    try:
        progress_bar.progress(10, text="📊 Loading sales data...")
        # Sales data uses CACHE period (can be filtered client-side via inv_date column)
        data['sales_df'] = queries.get_sales_data(
            start_date=cache_start,
            end_date=cache_end,
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
        # =====================================================================
        # NEW v2.14.0: Pass exclude_internal to backlog queries
        # When exclude_internal=True: Revenue = 0 for Internal, GP kept
        # =====================================================================
        data['backlog_summary_df'] = queries.get_backlog_data(
            kpi_center_ids=kpi_center_ids,
            entity_ids=entity_ids,
            exclude_internal=exclude_internal  # NEW v2.14.0
        )
        
        data['backlog_in_period_df'] = queries.get_backlog_in_period(
            start_date=cache_start,
            end_date=cache_end,
            kpi_center_ids=kpi_center_ids,
            entity_ids=entity_ids,
            exclude_internal=exclude_internal  # NEW v2.14.0
        )
        
        data['backlog_by_month_df'] = queries.get_backlog_by_month(
            kpi_center_ids=kpi_center_ids,
            entity_ids=entity_ids,
            exclude_internal=exclude_internal  # NEW v2.14.0
        )
        
        progress_bar.progress(55, text="📋 Loading backlog details...")
        data['backlog_detail_df'] = queries.get_backlog_detail(
            kpi_center_ids=kpi_center_ids,
            entity_ids=entity_ids
        )
        
        progress_bar.progress(70, text="🆕 Loading complex KPIs...")
        # =====================================================================
        # FIXED v2.9.0: Complex KPIs now receive entity_ids for proper filtering
        # FIXED v2.7.0: Complex KPIs now receive selected_kpi_types for dedupe
        # NEW v2.14.0: Complex KPIs now receive exclude_internal to exclude Internal customers
        # - Single type → no dedupe (full credit per KPI Center)
        # - Multiple types → dedupe per entity to avoid double counting
        # - exclude_internal=True → Internal customers excluded entirely from counts
        # =====================================================================
        data['new_customers_df'] = queries.get_new_customers(
            kpi_start, kpi_end, kpi_center_ids,
            entity_ids=entity_ids,
            selected_kpi_types=selected_kpi_types,
            exclude_internal=exclude_internal  # NEW v2.14.0
        )
        data['new_customers_detail_df'] = queries.get_new_customers_detail(
            kpi_start, kpi_end, kpi_center_ids,
            entity_ids=entity_ids,
            selected_kpi_types=selected_kpi_types,
            exclude_internal=exclude_internal  # NEW v2.14.0
        )
        data['new_products_df'] = queries.get_new_products(
            kpi_start, kpi_end, kpi_center_ids,
            entity_ids=entity_ids,
            selected_kpi_types=selected_kpi_types,
            exclude_internal=exclude_internal  # NEW v2.14.0
        )
        # Use same data for detail (already filtered)
        data['new_products_detail_df'] = queries.get_new_products_detail(
            kpi_start, kpi_end, kpi_center_ids,
            entity_ids=entity_ids,
            selected_kpi_types=selected_kpi_types,
            exclude_internal=exclude_internal  # NEW v2.14.0
        )
        data['new_business_df'] = queries.get_new_business_revenue(
            kpi_start, kpi_end, kpi_center_ids,
            entity_ids=entity_ids,
            selected_kpi_types=selected_kpi_types,
            exclude_internal=exclude_internal  # NEW v2.14.0
        )
        data['new_business_detail_df'] = queries.get_new_business_detail(
            kpi_start, kpi_end, kpi_center_ids,
            entity_ids=entity_ids,
            selected_kpi_types=selected_kpi_types,
            exclude_internal=exclude_internal  # NEW v2.14.0
        )
        
        progress_bar.progress(85, text="⚠️ Analyzing backlog risk...")
        data['backlog_risk'] = queries.get_backlog_risk_analysis(
            kpi_center_ids=kpi_center_ids,
            entity_ids=entity_ids,
            exclude_internal=exclude_internal  # NEW v2.14.0
        )
        
        for key in data:
            if isinstance(data[key], pd.DataFrame) and not data[key].empty:
                data[key] = _clean_dataframe_for_display(data[key])
        
        data['_loaded_at'] = datetime.now()
        data['_year_range'] = (start_year, end_year)
        # Store display period for reference
        data['_display_period'] = (kpi_start, kpi_end)
        # NEW v2.7.0: Store for reload check
        data['_selected_kpi_types'] = selected_kpi_types
        data['_kpi_center_ids'] = kpi_center_ids  # CRITICAL: For reload check when KPI Center changes
        # NEW v2.9.0: Store entity_ids for reload check
        data['_entity_ids'] = entity_ids
        # NEW v2.14.0: Store exclude_internal for reload check
        data['_exclude_internal'] = exclude_internal
        
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
    """
    Check if data needs to be reloaded.
    
    FIXED v2.9.0: Added entity_ids check.
    NEW v2.14.0: Added exclude_internal check.
    Complex KPIs and Backlog are queried with these parameters, so must reload when changed.
    """
    if '_kpc_raw_cached_data' not in st.session_state or st.session_state._kpc_raw_cached_data is None:
        return True
    
    cached_start, cached_end = _get_cached_year_range()
    if cached_start is None or cached_end is None:
        return True
    
    required_start = filter_values['start_date'].year
    required_end = filter_values['end_date'].year
    
    # Check if year range needs expansion
    if required_start < cached_start or required_end > cached_end:
        return True
    
    cached_data = st.session_state._kpc_raw_cached_data
    
    # =========================================================================
    # FIXED: Check if display period changed (for complex KPIs)
    # Complex KPIs can't be filtered client-side, so we need to reload
    # when the display period changes
    # =========================================================================
    cached_display_period = cached_data.get('_display_period')
    
    if cached_display_period:
        cached_display_start, cached_display_end = cached_display_period
        if (filter_values['start_date'] != cached_display_start or 
            filter_values['end_date'] != cached_display_end):
            return True
    
    # =========================================================================
    # FIXED v2.7.0: Check if kpi_center_ids changed
    # Complex KPIs are queried with kpi_center_ids parameter, must reload!
    # =========================================================================
    cached_kpi_center_ids = cached_data.get('_kpi_center_ids')
    current_kpi_center_ids = filter_values.get('kpi_center_ids', [])
    
    if cached_kpi_center_ids is not None:
        # Compare as sets (order doesn't matter)
        if set(cached_kpi_center_ids) != set(current_kpi_center_ids):
            return True
    
    # =========================================================================
    # NEW v2.7.0: Check if kpi_type_filter changed
    # This affects dedupe logic in complex KPIs
    # =========================================================================
    cached_kpi_type_filter = cached_data.get('_kpi_type_filter')
    current_kpi_type_filter = filter_values.get('kpi_type_filter')
    
    if cached_kpi_type_filter != current_kpi_type_filter:
        return True
    
    # =========================================================================
    # NEW v2.9.0: Check if entity_ids changed
    # Complex KPIs are queried with entity_ids parameter, must reload!
    # =========================================================================
    cached_entity_ids = cached_data.get('_entity_ids')
    current_entity_ids = filter_values.get('entity_ids', [])
    
    # Normalize: empty list and None should be treated the same
    cached_set = set(cached_entity_ids) if cached_entity_ids else set()
    current_set = set(current_entity_ids) if current_entity_ids else set()
    
    if cached_set != current_set:
        return True
    
    # =========================================================================
    # NEW v2.14.0: Check if exclude_internal changed
    # Backlog and Complex KPIs are queried with exclude_internal parameter
    # Must reload when this setting changes!
    # =========================================================================
    cached_exclude_internal = cached_data.get('_exclude_internal', True)
    current_exclude_internal = filter_values.get('exclude_internal_revenue', True)
    
    if cached_exclude_internal != current_exclude_internal:
        return True
    
    return False


def get_or_load_data(queries: KPICenterQueries, filter_values: dict, kpi_center_df: pd.DataFrame = None) -> dict:
    """
    Smart data loading with session-based caching.
    
    UPDATED v2.7.0: Added kpi_center_df parameter to derive selected_kpi_types.
    """
    required_start = filter_values['start_date'].year
    required_end = filter_values['end_date'].year
    
    kpi_center_ids = filter_values.get('kpi_center_ids', [])
    entity_ids = filter_values.get('entity_ids', [])
    
    # =========================================================================
    # NEW v2.7.0: Derive selected_kpi_types for dedupe logic
    # =========================================================================
    if kpi_center_df is not None:
        selected_kpi_types = get_selected_kpi_types(filter_values, kpi_center_df)
    else:
        # Fallback: use kpi_type_filter directly
        kpi_type_filter = filter_values.get('kpi_type_filter')
        selected_kpi_types = [kpi_type_filter] if kpi_type_filter else None
    
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
            entity_ids=entity_ids,
            # =========================================================
            # FIXED: Pass display period for complex KPIs
            # =========================================================
            display_start=filter_values['start_date'],
            display_end=filter_values['end_date'],
            # =========================================================
            # NEW v2.7.0: Pass selected_kpi_types for dedupe logic
            # =========================================================
            selected_kpi_types=selected_kpi_types,
            # =========================================================
            # NEW v2.14.0: Pass exclude_internal for consistent business logic
            # =========================================================
            exclude_internal=filter_values.get('exclude_internal_revenue', True)
        )
        
        # Store kpi_type_filter for reload check
        data['_kpi_type_filter'] = filter_values.get('kpi_type_filter')
        
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
            # =================================================================
            # FIXED v2.9.1: Exclude Internal Revenue - Set revenue = 0, keep GP/GP1
            # Business rule: Internal sales have Revenue = 0 but GP/GP1 are real profit
            # Previous: Filtered out rows entirely (wrong - lost GP/GP1)
            # Now: Set revenue = 0, keep rows for GP/GP1 calculation
            # =================================================================
            if 'sales_by_kpi_center_usd' in prev_sales_df.columns:
                internal_mask = prev_sales_df['customer_type'] == 'Internal'
                prev_sales_df.loc[internal_mask, 'sales_by_kpi_center_usd'] = 0
    
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
        (
            kpi_center_df, 
            entity_df, 
            available_years,
            kpi_center_ids_with_assignment,
            kpi_types_with_assignment,
        ) = load_lookup_data()
    except Exception as e:
        st.error(f"Failed to load lookup data: {e}")
        logger.error(f"Lookup data error: {e}")
        st.stop()
    
    queries = KPICenterQueries(access)
    filters = KPICenterFilters(access)
    
    filter_values = filters.render_sidebar_filters(
        kpi_center_df=kpi_center_df,
        entity_df=entity_df,
        available_years=available_years,
        kpi_types_with_assignment=kpi_types_with_assignment,  # NEW v2.6.0
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
    # =========================================================================
    # UPDATED v2.7.0: Pass kpi_center_df for selected_kpi_types derivation
    # =========================================================================
    raw_data = get_or_load_data(queries, active_filters, kpi_center_df=kpi_center_df)
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
    
    # =========================================================================
    # COMPLEX KPIs - UPDATED v2.6.0: Use weighted counting
    # =========================================================================
    # Get DataFrames for complex KPIs
    new_customers_df = data.get('new_customers_df', pd.DataFrame())
    new_products_df = data.get('new_products_df', pd.DataFrame())
    new_business_df = data.get('new_business_df', pd.DataFrame())
    
    complex_kpis = {
        # Weighted count: sum(split_rate_percent) / 100
        # This matches Salesperson page logic
        'num_new_customers': calculate_weighted_count(new_customers_df),
        'num_new_products': calculate_weighted_count(new_products_df),
        # Revenue is still a direct sum (unchanged)
        'new_business_revenue': new_business_df['new_business_revenue'].sum() if not new_business_df.empty else 0,
    }
    
    # =========================================================================
    # NEW v3.3.1: Build complex_kpis_by_center for Overall Achievement
    # Used by both Overview tab and KPI & Targets tab
    # =========================================================================
    complex_kpis_by_center = {}
    selected_kpi_types = get_selected_kpi_types(active_filters, kpi_center_df)
    
    # Get New Business Revenue per KPI Center
    new_business_by_center_df = queries.get_new_business_by_kpi_center(
        start_date=active_filters['start_date'],
        end_date=active_filters['end_date'],
        kpi_center_ids=active_filters.get('kpi_center_ids', []),
        entity_ids=active_filters.get('entity_ids', []),
        selected_kpi_types=selected_kpi_types,
        exclude_internal=active_filters.get('exclude_internal_revenue', True)
    )
    
    if not new_business_by_center_df.empty:
        for _, row in new_business_by_center_df.iterrows():
            kpc_id = row['kpi_center_id']
            if kpc_id not in complex_kpis_by_center:
                complex_kpis_by_center[kpc_id] = {}
            complex_kpis_by_center[kpc_id]['new_business_revenue'] = row.get('new_business_revenue', 0) or 0
    
    # Get New Customers per KPI Center
    new_customers_by_center_df = queries.get_new_customers_by_kpi_center(
        start_date=active_filters['start_date'],
        end_date=active_filters['end_date'],
        kpi_center_ids=active_filters.get('kpi_center_ids', []),
        entity_ids=active_filters.get('entity_ids', []),
        selected_kpi_types=selected_kpi_types,
        exclude_internal=active_filters.get('exclude_internal_revenue', True)
    )
    
    if not new_customers_by_center_df.empty:
        for _, row in new_customers_by_center_df.iterrows():
            kpc_id = row['kpi_center_id']
            if kpc_id not in complex_kpis_by_center:
                complex_kpis_by_center[kpc_id] = {}
            complex_kpis_by_center[kpc_id]['num_new_customers'] = row.get('weighted_count', 0) or 0
    
    # Get New Products per KPI Center
    new_products_by_center_df = queries.get_new_products_by_kpi_center(
        start_date=active_filters['start_date'],
        end_date=active_filters['end_date'],
        kpi_center_ids=active_filters.get('kpi_center_ids', []),
        entity_ids=active_filters.get('entity_ids', []),
        selected_kpi_types=selected_kpi_types,
        exclude_internal=active_filters.get('exclude_internal_revenue', True)
    )
    
    if not new_products_by_center_df.empty:
        for _, row in new_products_by_center_df.iterrows():
            kpc_id = row['kpi_center_id']
            if kpc_id not in complex_kpis_by_center:
                complex_kpis_by_center[kpc_id] = {}
            complex_kpis_by_center[kpc_id]['num_new_products'] = row.get('weighted_count', 0) or 0
    
    pipeline_metrics = metrics_calc.calculate_pipeline_forecast_metrics(
        total_backlog_df=data.get('backlog_summary_df', pd.DataFrame()),
        in_period_backlog_df=data.get('backlog_in_period_df', pd.DataFrame()),
        period_type=active_filters['period_type'],
        year=active_filters['year'],
        start_date=active_filters['start_date'],
        end_date=active_filters['end_date']
    )
    
    # UPDATED v3.3.1: Pass complex_kpis_by_center for accurate calculation
    overall_achievement = metrics_calc.calculate_overall_kpi_achievement(
        period_type=active_filters['period_type'],
        year=active_filters['year'],
        start_date=active_filters['start_date'],
        end_date=active_filters['end_date'],
        complex_kpis_by_center=complex_kpis_by_center
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
    # TAB 2: SALES DETAIL (with Sub-tabs like Salesperson)
    # ==========================================================================
    
    with tab2:
        st.subheader("📋 Sales Transaction Detail")
        
        if sales_df.empty:
            st.info("No sales data for selected period")
        else:
            # Sub-tabs for detail views - EACH IS A FRAGMENT
            # Only reruns when filters in that sub-tab change
            detail_tab1, detail_tab2 = st.tabs(["📄 Transaction List", "📊 Pivot Analysis"])
            
            with detail_tab1:
                # =============================================================
                # TRANSACTION LIST - FRAGMENT
                # Only reruns when filters in this section change
                # =============================================================
                sales_detail_fragment(
                    sales_df=sales_df,
                    overview_metrics=overview_metrics,
                    filter_values=active_filters,
                    fragment_key="kpc_detail"
                )
            
            with detail_tab2:
                # =============================================================
                # PIVOT ANALYSIS - FRAGMENT  
                # Only reruns when pivot config changes
                # =============================================================
                pivot_analysis_fragment(
                    sales_df=sales_df,
                    fragment_key="kpc_pivot"
                )
    
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
    # TAB 4: BACKLOG - SYNCED v3.0.0 with Salesperson module
    # ==========================================================================
    
    with tab4:
        # Header with Help
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
        
        backlog_df = data.get('backlog_detail_df', pd.DataFrame())
        
        if backlog_df.empty:
            st.info("📦 No backlog data available")
        else:
            # Show overdue warning at top if applicable
            in_period_analysis = KPICenterMetrics.analyze_in_period_backlog(
                backlog_detail_df=backlog_df,
                start_date=active_filters.get('start_date', date.today()),
                end_date=active_filters.get('end_date', date.today())
            )
            
            if in_period_analysis.get('overdue_warning'):
                st.warning(in_period_analysis['overdue_warning'])
            
            # Sub-tabs (synced with Salesperson)
            backlog_tab1, backlog_tab2, backlog_tab3 = st.tabs([
                "📋 Backlog List", 
                "📅 By ETD", 
                "⚠️ Risk Analysis"
            ])
            
            with backlog_tab1:
                # BACKLOG LIST - FRAGMENT with 7 cards, 5 filters
                backlog_list_fragment(
                    backlog_df=backlog_df,
                    filter_values=active_filters,
                    total_backlog_df=data.get('backlog_summary_df', pd.DataFrame())
                )
            
            with backlog_tab2:
                # BACKLOG BY ETD - FRAGMENT with 3 view modes
                # FIX v3.0.1: Pass backlog_detail_df instead of backlog_by_month_df
                # backlog_detail_df is already filtered by KPI Center selection
                backlog_by_etd_fragment(
                    backlog_detail_df=backlog_df,  # Use detail data (already filtered)
                    current_year=active_filters.get('year', date.today().year),
                    fragment_key="kpc_backlog_etd"
                )
            
            with backlog_tab3:
                # RISK ANALYSIS - FRAGMENT
                backlog_risk_analysis_fragment(
                    backlog_df=backlog_df,
                    fragment_key="kpc_backlog_risk"
                )
    
    # ==========================================================================
    # TAB 5: KPI & TARGETS - UPDATED v3.1.0 (synced with Salesperson)
    # ==========================================================================
    
    with tab5:
        st.subheader("🎯 KPI & Targets")
        
        if targets_df.empty:
            st.info("No KPI targets assigned for selected KPI Centers and year")
        else:
            # =================================================================
            # GET HIERARCHY DATA - NEW v3.2.0
            # =================================================================
            
            # Get hierarchy with levels for this KPI type
            hierarchy_df = queries.get_hierarchy_with_levels(
                kpi_type=active_filters.get('kpi_type', 'TERRITORY')
            )
            
            # Filter hierarchy to selected KPI Centers (if any)
            selected_kpc_ids = active_filters.get('kpi_center_ids', [])
            if selected_kpc_ids:
                # Include selected + their ancestors + their descendants
                all_relevant_ids = set(selected_kpc_ids)
                for kpc_id in selected_kpc_ids:
                    all_relevant_ids.update(queries.get_ancestors(kpc_id, include_self=True))
                    all_relevant_ids.update(queries.get_all_descendants(kpc_id, include_self=True))
                hierarchy_df = hierarchy_df[hierarchy_df['kpi_center_id'].isin(all_relevant_ids)]
            
            # Calculate rollup targets
            rollup_targets = metrics_calc.calculate_rollup_targets(
                hierarchy_df=hierarchy_df,
                queries_instance=queries
            )
            
            # NOTE v3.3.1: complex_kpis_by_center is now built in CALCULATE METRICS section
            # and shared between Overview tab and KPI & Targets tab
            
            # Calculate per-center progress using shared complex_kpis_by_center
            progress_data = metrics_calc.calculate_per_center_progress(
                hierarchy_df=hierarchy_df,
                queries_instance=queries,
                period_type=active_filters['period_type'],
                year=active_filters['year'],
                start_date=active_filters['start_date'],
                end_date=active_filters['end_date'],
                complex_kpis_by_center=complex_kpis_by_center  # From CALCULATE METRICS section
            )
            
            # 3 Sub-tabs (synced with Salesperson page)
            kpi_tab1, kpi_tab2, kpi_tab3 = st.tabs([
                "📊 My KPIs", 
                "📈 Progress", 
                "🏆 Ranking"
            ])
            
            # =================================================================
            # SUB-TAB 1: MY KPIs (Assignments View) - UPDATED v3.2.0
            # =================================================================
            with kpi_tab1:
                st.markdown("#### 📊 KPI Assignments")
                kpi_assignments_fragment(
                    rollup_targets=rollup_targets,
                    hierarchy_df=hierarchy_df,
                    fragment_key="kpc_assignments"
                )
            
            # =================================================================
            # SUB-TAB 2: KPI PROGRESS (Per-Center) - UPDATED v3.2.0
            # =================================================================
            with kpi_tab2:
                st.markdown("#### 📈 KPI Progress")
                kpi_progress_fragment(
                    progress_data=progress_data,
                    hierarchy_df=hierarchy_df,
                    period_type=active_filters['period_type'],
                    year=active_filters['year'],
                    fragment_key="kpc_progress"
                )
            
            # =================================================================
            # SUB-TAB 3: KPI CENTER RANKING - UPDATED v3.2.0
            # =================================================================
            with kpi_tab3:
                st.markdown("#### 🏆 KPI Center Ranking")
                kpi_center_ranking_fragment(
                    ranking_df=kpi_center_summary_df,
                    progress_data=progress_data,
                    hierarchy_df=hierarchy_df,
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