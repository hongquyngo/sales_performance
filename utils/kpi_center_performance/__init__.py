# utils/kpi_center_performance/__init__.py
"""
KPI Center Performance Module

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

# Setup Module - NEW v3.4.0
from .setup import (
    SetupQueries,
    setup_tab_fragment,
    split_rules_section,
    hierarchy_section,
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
    
    # Setup Module - NEW v3.4.0
    'SetupQueries',
    
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
    
    # Setup Fragments - NEW v3.4.0
    'setup_tab_fragment',
    'split_rules_section',
    'hierarchy_section',
    
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

__version__ = '3.4.0'