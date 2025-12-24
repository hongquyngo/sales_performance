# utils/kpi_center_performance/__init__.py
"""
KPI Center Performance Module

A comprehensive module for tracking KPI Center performance metrics.

VERSION: 2.5.0
CHANGELOG:
- v2.5.0: BUGFIX - YoY comparison showing $0 for previous year:
          - fragments.py: Fixed closure bug in yoy_comparison_fragment
          - fragments.py: Now uses raw_cached_data first before querying DB
          - Main page: Pass raw_cached_data to yoy_comparison_fragment
          - Main page: load_lookup_data() now queries from unified_sales_by_kpi_center_view
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
from .access_control import AccessControl, ALLOWED_ROLES

# Queries
from .queries import KPICenterQueries

# Metrics Calculator
from .metrics import KPICenterMetrics

# Filters
from .filters import (
    KPICenterFilters,
    analyze_period,
    render_multiselect_filter,
    apply_multiselect_filter,
    FilterResult,
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
    'FilterResult',
    
    # Functions
    'analyze_period',
    'render_multiselect_filter',
    'apply_multiselect_filter',
    'clear_data_cache',
    
    # Fragments
    'monthly_trend_fragment',
    'yoy_comparison_fragment',
    'sales_detail_fragment',
    'pivot_analysis_fragment',
    'backlog_list_fragment',
    'kpi_center_ranking_fragment',
    'top_performers_fragment',  # NEW v2.3.0
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

__version__ = '2.5.0'