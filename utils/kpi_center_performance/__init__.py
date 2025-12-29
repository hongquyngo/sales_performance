# utils/kpi_center_performance/__init__.py
"""
KPI Center Performance Module

A comprehensive module for tracking KPI Center performance metrics.

VERSION: 3.3.0
CHANGELOG:
- v3.3.0: FIXED New Business Revenue = 0 in KPI Progress tab:
          - Root Cause: complex_kpis_by_center was always None
          - queries.py: Added get_new_business_by_kpi_center(),
            get_new_customers_by_kpi_center(), get_new_products_by_kpi_center()
          - Main page: Build complex_kpis_by_center dict and pass to progress calc
          - Now Complex KPIs show correct values per KPI Center in Progress tab
          ENHANCED Parent KPI Center calculation:
          - metrics.py: Parents now aggregate KPIs with target-proportion weights
            * OLD: Weighted average of children's overall achievements
            * NEW: Aggregate targets & actuals by KPI, derive weights from proportion
            * Currency KPIs = 80% weight, Count KPIs = 20% weight
          - fragments.py: Parents now show per-KPI progress bars
            * Help popover with detailed calculation explanation
            * Children summary in expander for optional detail
- v3.2.0: ENHANCED KPI & Targets tab with hierarchy support:
          - queries.py: Added get_hierarchy_with_levels(), get_all_descendants(),
            get_leaf_descendants(), get_ancestors() for hierarchy traversal
          - metrics.py: Added calculate_rollup_targets(), calculate_per_center_progress()
          - fragments.py: Updated all 3 KPI & Targets fragments:
            * kpi_assignments_fragment: Rollup targets for parents
            * kpi_progress_fragment: Per-center progress with weighted overall
            * kpi_center_ranking_fragment: Group by level with ≥2 items filter
          - Leaf nodes: Direct calculation from targets/actuals
          - Parent nodes: Weighted average of children's achievements
          - Level auto-detection from hierarchy
- v3.1.0: SYNCED KPI & Targets tab with Salesperson module:
          - NEW kpi_assignments_fragment(): My KPIs sub-tab with improved UI
          - NEW kpi_progress_fragment(): Progress sub-tab with progress bars
          - UPDATED kpi_center_ranking_fragment(): Added medals (🥇🥈🥉), sortable dropdown
          - metrics.py: Added _get_prorated_target(), get_kpi_progress_data()
          - 3 sub-tabs: My KPIs, Progress, Ranking (same as Salesperson)
- v3.0.2: BUGFIX render_multiselect_filter doesn't have placeholder parameter
- v3.0.1: BUGFIX backlog_by_etd_fragment filter not working:
          - Problem: backlog_by_month_df was pre-aggregated without kpi_center_id
          - Solution: Use backlog_detail_df (already filtered) and aggregate in fragment
- v3.0.0: SYNCED Backlog tab with Salesperson module:
          - backlog_list_fragment(): 7 summary cards, 5 filters with Excl option
          - NEW backlog_by_etd_fragment(): 3 view modes (Timeline/Stacked/Single Year)
          - NEW backlog_risk_analysis_fragment(): Risk categorization + Overdue table
          - metrics.py: Added analyze_in_period_backlog()
          - charts.py: Added backlog chart methods
- v2.13.0: SYNCED sales_detail_fragment with Salesperson page:
          - filters.py: Added TextSearchResult, render_text_search_filter(),
                        apply_text_search_filter(), render_number_filter alias
          - fragments.py: Refactored sales_detail_fragment:
            * 7 summary metrics cards
            * 5 filter columns with Excl checkboxes
            * Original value calculation (pre-split)
            * Formatted Product and OC/PO display
            * Column tooltips and Legend expander
            * Export Filtered View button
          - Updated pivot_analysis_fragment: default to Gross Profit
- v2.5.0: ADDED Multi-Year Comparison (synced with Salesperson page):
          - charts.py: Added build_multi_year_monthly_chart(), 
                       build_multi_year_cumulative_chart(), 
                       build_multi_year_summary_table()
          - fragments.py: Updated yoy_comparison_fragment with multi-year support
          - Detects actual years in data: >= 2 years → Multi-Year, 0-1 years → YoY
          - Previous: BUGFIX - YoY comparison showing $0 for previous year
- v2.3.0: Phase 3 - Pareto Analysis:
          - charts.py: Added build_pareto_chart(), build_top_performers_chart(),
                       build_concentration_donut()
          - fragments.py: Added top_performers_fragment() with 80/20 insights
          - Main page: New Analysis tab with Pareto analysis
- v2.2.0: Phase 2 enhancements:
          - fragments.py: Added summary cards to sales_detail_fragment
          - fragments.py: Added total_backlog_df param to backlog_list_fragment  
          - fragments.py: Added targets overlay to monthly_trend_fragment
          - charts.py: Added build_achievement_bar_chart()
          - queries.py: Added calculate_complex_kpi_value() helper
          - queries.py: Added get_kpi_center_achievement_summary()
- v2.1.0: Fixed employee_count -> kpi_center_count consistency
          Fixed convert_pipeline_to_backlog_metrics key names

Components:
- AccessControl: Role-based access control
- KPICenterQueries: Database queries
- KPICenterMetrics: Metric calculations
- KPICenterFilters: Sidebar filter components
- KPICenterCharts: Visualization components
- KPICenterExport: Excel export functionality
- Fragments: Interactive UI components

Usage:
    from utils.kpi_center_performance import (
        AccessControl,
        KPICenterQueries,
        KPICenterMetrics,
        KPICenterFilters,
        KPICenterCharts,
        KPICenterExport,
        analyze_period,
        ALLOWED_ROLES,
    )
"""

# Access Control
from .access_control import AccessControl

# Queries
from .queries import KPICenterQueries

# Metrics Calculator
from .metrics import KPICenterMetrics

# Filters
from .filters import (
    KPICenterFilters,
    analyze_period,
    # Multiselect filter
    FilterResult,
    render_multiselect_filter,
    apply_multiselect_filter,
    # Text search filter (NEW v2.13.0)
    TextSearchResult,
    render_text_search_filter,
    apply_text_search_filter,
    # Number filter
    NumberRangeResult,
    render_number_filter,
    apply_number_filter,
    # Cache helpers
    clear_data_cache,
)

# Charts
from .charts import KPICenterCharts

# Export
from .export import KPICenterExport

# Fragments
from .fragments import (
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
    top_performers_fragment,  # NEW v2.3.0
    export_report_fragment,
)

# Constants
from .constants import (
    ALLOWED_ROLES,
    LOOKBACK_YEARS,
    CACHE_TTL_SECONDS,
    PERIOD_TYPES,
    MONTH_ORDER,
    KPI_CENTER_TYPES,
    COLORS,
    CHART_WIDTH,
    CHART_HEIGHT,
)

__all__ = [
    # Classes
    'AccessControl',
    'KPICenterQueries',
    'KPICenterMetrics',
    'KPICenterFilters',
    'KPICenterCharts',
    'KPICenterExport',
    
    # Filter Result Classes
    'FilterResult',
    'TextSearchResult',
    'NumberRangeResult',
    
    # Filter Functions
    'analyze_period',
    'render_multiselect_filter',
    'apply_multiselect_filter',
    'render_text_search_filter',
    'apply_text_search_filter',
    'render_number_filter',
    'apply_number_filter',
    'clear_data_cache',
    
    # Fragments
    'monthly_trend_fragment',
    'yoy_comparison_fragment',
    'sales_detail_fragment',
    'pivot_analysis_fragment',
    'backlog_list_fragment',
    'backlog_by_etd_fragment',        # NEW v3.0.0
    'backlog_risk_analysis_fragment',  # NEW v3.0.0
    'kpi_assignments_fragment',        # NEW v3.1.0
    'kpi_progress_fragment',           # NEW v3.1.0
    'kpi_center_ranking_fragment',
    'top_performers_fragment',
    'export_report_fragment',
    
    # Constants
    'ALLOWED_ROLES',
    'LOOKBACK_YEARS',
    'CACHE_TTL_SECONDS',
    'PERIOD_TYPES',
    'MONTH_ORDER',
    'KPI_CENTER_TYPES',
    'COLORS',
    'CHART_WIDTH',
    'CHART_HEIGHT',
]

__version__ = '3.3.0'