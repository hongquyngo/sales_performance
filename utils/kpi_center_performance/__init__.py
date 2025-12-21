# utils/kpi_center_performance/__init__.py
"""
KPI Center Performance Module

A comprehensive dashboard module for tracking KPI Center performance.
Similar to salesperson_performance module but with:
- Simplified access control (page-level only)
- Parent-Child KPI Center rollup
- KPI Type filtering (TERRITORY, INTERNAL)

Components:
- AccessControl: Role-based page access (admin, GM, MD, sales_manager)
- KPICenterQueries: SQL queries and data loading
- KPICenterMetrics: KPI calculations and aggregations
- KPICenterFilters: Sidebar filter components
- KPICenterCharts: Altair visualizations
- KPICenterExport: Excel report generation

VERSION: 1.0.0
"""

from .constants import (
    ALLOWED_ROLES,
    COLORS,
    MONTH_ORDER,
    PERIOD_TYPES,
    KPI_TYPES,
    KPI_CENTER_TYPES,
    LOOKBACK_YEARS,
    CACHE_TTL_SECONDS,
    CHART_WIDTH,
    CHART_HEIGHT,
)

from .access_control import AccessControl

from .queries import KPICenterQueries

from .metrics import KPICenterMetrics

from .filters import (
    KPICenterFilters,
    analyze_period,
    FilterResult,
    render_multiselect_filter,
    apply_multiselect_filter,
)

from .charts import KPICenterCharts

from .export import KPICenterExport

from .fragments import (
    monthly_trend_fragment,
    yoy_comparison_fragment,
    sales_detail_fragment,
    pivot_analysis_fragment,
    backlog_list_fragment,
    kpi_center_ranking_fragment,
    export_report_fragment,
)


__all__ = [
    # Constants
    'ALLOWED_ROLES',
    'COLORS',
    'MONTH_ORDER',
    'PERIOD_TYPES',
    'KPI_TYPES',
    'KPI_CENTER_TYPES',
    'LOOKBACK_YEARS',
    'CACHE_TTL_SECONDS',
    
    # Classes
    'AccessControl',
    'KPICenterQueries',
    'KPICenterMetrics',
    'KPICenterFilters',
    'KPICenterCharts',
    'KPICenterExport',
    
    # Filter helpers
    'analyze_period',
    'FilterResult',
    'render_multiselect_filter',
    'apply_multiselect_filter',
    
    # Fragments
    'monthly_trend_fragment',
    'yoy_comparison_fragment',
    'sales_detail_fragment',
    'pivot_analysis_fragment',
    'backlog_list_fragment',
    'kpi_center_ranking_fragment',
    'export_report_fragment',
]

__version__ = '1.0.0'
