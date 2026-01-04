# utils/kpi_center_performance/__init__.py
"""
KPI Center Performance Module

VERSION: 5.0.0
CHANGELOG:
- v5.0.0: New single-selection KPI Center tree selector
  - Prevents parent-child double counting
  - "Include sub-centers" toggle
  - Search filter for large trees
- v4.6.0: Added overview_tab_fragment as main Overview tab entry point
"""

# =============================================================================
# CORE CLASSES - NEW v4.0.0
# =============================================================================

# Unified Data Loading (NEW)
from .data_loader import UnifiedDataLoader

# Data Processing (NEW)
from .data_processor import DataProcessor

# =============================================================================
# EXISTING CLASSES
# =============================================================================

# Access Control
from .access_control import AccessControl

# Queries (still needed for some operations)
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
    # Text search filter
    TextSearchResult,
    render_text_search_filter,
    apply_text_search_filter,
    # Number filter
    NumberRangeResult,
    render_number_filter,
    apply_number_filter,
    # Cache helpers (updated to use new architecture)
    clear_data_cache,
)

# KPI Center Selector - NEW v5.0.0
from .kpi_center_selector import (
    KPICenterNode,
    KPICenterSelection,
    KPICenterTreeBuilder,
    render_kpi_center_selector,
    get_kpi_center_selection_ids,
)

# =============================================================================
# CHARTS - Direct imports from submodules (v4.3.0)
# =============================================================================

# Common chart utilities
from .common.charts import (
    empty_chart,
    convert_pipeline_to_backlog_metrics,
)

# Overview charts
from .overview.charts import (
    render_kpi_cards,
    build_monthly_trend_dual_chart,
    build_cumulative_dual_chart,
    build_yoy_comparison_chart,
    build_yoy_cumulative_chart,
    build_multi_year_monthly_chart,
    build_multi_year_cumulative_chart,
    build_forecast_waterfall_chart,
    build_gap_analysis_chart,
)

# Analysis charts
from .analysis.charts import (
    build_pareto_chart,
    build_top_performers_chart,
)

# Backlog charts
from .backlog.charts import (
    build_backlog_by_month_chart,
    build_backlog_by_month_chart_multiyear,
    build_backlog_by_month_stacked,
)


# Backward compatibility wrapper class
class KPICenterCharts:
    """
    Backward compatibility wrapper for chart functions.
    
    Delegates to functions in submodules.
    Prefer direct imports for new code.
    """
    # Common
    empty_chart = staticmethod(empty_chart)
    convert_pipeline_to_backlog_metrics = staticmethod(convert_pipeline_to_backlog_metrics)
    
    # Overview
    render_kpi_cards = staticmethod(render_kpi_cards)
    build_monthly_trend_dual_chart = staticmethod(build_monthly_trend_dual_chart)
    build_cumulative_dual_chart = staticmethod(build_cumulative_dual_chart)
    build_yoy_comparison_chart = staticmethod(build_yoy_comparison_chart)
    build_yoy_cumulative_chart = staticmethod(build_yoy_cumulative_chart)
    build_multi_year_monthly_chart = staticmethod(build_multi_year_monthly_chart)
    build_multi_year_cumulative_chart = staticmethod(build_multi_year_cumulative_chart)
    
    # Analysis
    build_pareto_chart = staticmethod(build_pareto_chart)
    build_top_performers_chart = staticmethod(build_top_performers_chart)
    
    # Backlog
    build_forecast_waterfall_chart = staticmethod(build_forecast_waterfall_chart)
    build_gap_analysis_chart = staticmethod(build_gap_analysis_chart)
    build_backlog_by_month_chart = staticmethod(build_backlog_by_month_chart)
    build_backlog_by_month_chart_multiyear = staticmethod(build_backlog_by_month_chart_multiyear)
    build_backlog_by_month_stacked = staticmethod(build_backlog_by_month_stacked)

# Export
from .export import KPICenterExport

# =============================================================================
# FRAGMENTS - Direct imports from submodules (v4.3.0)
# =============================================================================

# Common fragments
from .common.fragments import prepare_monthly_summary

# Overview fragments - UPDATED v4.6.0
from .overview.fragments import (
    overview_tab_fragment,  # NEW v4.6.0 - Main tab entry point
    monthly_trend_fragment,
    yoy_comparison_fragment,
    export_report_fragment,
)

# Sales detail fragments
from .sales_detail.fragments import (
    sales_detail_fragment,
    pivot_analysis_fragment,
    sales_detail_tab_fragment,
)

# Analysis fragments
from .analysis.fragments import top_performers_fragment

# Backlog fragments
from .backlog.fragments import (
    backlog_list_fragment,
    backlog_by_etd_fragment,
    backlog_risk_analysis_fragment,
    backlog_tab_fragment,
)

# KPI Targets fragments
from .kpi_targets.fragments import (
    kpi_assignments_fragment,
    kpi_progress_fragment,
    kpi_center_ranking_fragment,
)

# Setup Module
from .setup import (
    SetupQueries,
    setup_tab_fragment,
    split_rules_section,
    hierarchy_section,
)

# Calculators
from .backlog_calculator import BacklogCalculator
from .complex_kpi_calculator import ComplexKPICalculator

# Constants
from .constants import (
    # Role definitions
    ALLOWED_ROLES,
    # Data loading settings
    LOOKBACK_YEARS,
    MIN_DATA_YEAR,
    MAX_FUTURE_YEARS,
    # Cache settings
    CACHE_TTL_SECONDS,
    CACHE_KEY_UNIFIED,
    CACHE_KEY_PROCESSED,
    CACHE_KEY_FILTERS,
    CACHE_KEY_TIMING,
    # UI settings
    PERIOD_TYPES,
    MONTH_ORDER,
    # KPI_CENTER_TYPES removed v4.1.0 (unused)
    COLORS,
    CHART_WIDTH,
    CHART_HEIGHT,
    # Debug settings
    DEBUG_TIMING,
    DEBUG_QUERY_TIMING,
)

# =============================================================================
# ALL EXPORTS
# =============================================================================

__all__ = [
    # NEW v4.0.0 - Core classes
    'UnifiedDataLoader',
    'DataProcessor',
    
    # Existing classes
    'AccessControl',
    'KPICenterQueries',
    'KPICenterMetrics',
    'KPICenterFilters',
    'KPICenterCharts',  # Backward compat wrapper
    'KPICenterExport',
    
    # Setup Module
    'SetupQueries',
    
    # Calculators
    'BacklogCalculator',
    'ComplexKPICalculator',
    
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
    
    # KPI Center Selector - NEW v5.0.0
    'KPICenterNode',
    'KPICenterSelection',
    'KPICenterTreeBuilder',
    'render_kpi_center_selector',
    'get_kpi_center_selection_ids',
    
    # Chart Functions (v4.3.0 - direct exports)
    'empty_chart',
    'convert_pipeline_to_backlog_metrics',
    'render_kpi_cards',
    'build_monthly_trend_dual_chart',
    'build_cumulative_dual_chart',
    'build_yoy_comparison_chart',
    'build_yoy_cumulative_chart',
    'build_multi_year_monthly_chart',
    'build_multi_year_cumulative_chart',
    'build_pareto_chart',
    'build_top_performers_chart',
    'build_forecast_waterfall_chart',
    'build_gap_analysis_chart',
    'build_backlog_by_month_chart',
    'build_backlog_by_month_chart_multiyear',
    'build_backlog_by_month_stacked',
    
    # Fragments - Overview (UPDATED v4.6.0)
    'overview_tab_fragment',  # NEW v4.6.0
    'prepare_monthly_summary',
    'monthly_trend_fragment',
    'yoy_comparison_fragment',
    'export_report_fragment',
    
    # Fragments - Sales Detail
    'sales_detail_fragment',
    'pivot_analysis_fragment',
    'sales_detail_tab_fragment',
    
    # Fragments - Analysis
    'top_performers_fragment',
    
    # Fragments - Backlog
    'backlog_list_fragment',
    'backlog_by_etd_fragment',
    'backlog_risk_analysis_fragment',
    'backlog_tab_fragment',
    
    # Fragments - KPI Targets
    'kpi_assignments_fragment',
    'kpi_progress_fragment',
    'kpi_center_ranking_fragment',
    
    # Setup Fragments
    'setup_tab_fragment',
    'split_rules_section',
    'hierarchy_section',
    
    # Constants - Data Loading
    'LOOKBACK_YEARS',
    'MIN_DATA_YEAR',
    'MAX_FUTURE_YEARS',
    
    # Constants - Cache
    'CACHE_TTL_SECONDS',
    'CACHE_KEY_UNIFIED',
    'CACHE_KEY_PROCESSED',
    'CACHE_KEY_FILTERS',
    'CACHE_KEY_TIMING',
    
    # Constants - Roles
    'ALLOWED_ROLES',
    
    # Constants - UI
    'PERIOD_TYPES',
    'MONTH_ORDER',
    'COLORS',
    'CHART_WIDTH',
    'CHART_HEIGHT',
    
    # Constants - Debug
    'DEBUG_TIMING',
    'DEBUG_QUERY_TIMING',
]

__version__ = '5.0.0'