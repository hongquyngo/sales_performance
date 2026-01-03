# utils/kpi_center_performance/__init__.py
"""
KPI Center Performance Module

VERSION: 4.1.0
CHANGELOG:
- v4.1.0: Code cleanup and consolidation
  - Removed unused _get_entities_by_kpi_type() from filters.py
  - Removed unused KPI_CENTER_TYPES constant
  - Removed duplicate get_child_kpi_center_ids() (use get_all_descendants())
  - Consolidated DEBUG_TIMING definitions to constants.py
  - Fixed _complex_kpi_calculator caching bug (exclude_internal tracking)
  - Deprecated render_sidebar_filters() - use render_filter_form()
  - Consolidated analyze_period_context() into analyze_period()
  - Optimized _expand_kpi_center_ids_with_children() to use cached hierarchy
- v4.0.0: Unified data loading architecture
  - Added UnifiedDataLoader for single-source data loading
  - Added DataProcessor for Pandas-based filtering
  - Simplified reload logic (only on cache expiry)
  - ~60% faster first load, ~95% faster filter changes
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
    backlog_by_etd_fragment,
    backlog_risk_analysis_fragment,
    kpi_assignments_fragment,
    kpi_progress_fragment,
    kpi_center_ranking_fragment,
    top_performers_fragment,
    export_report_fragment,
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
    'KPICenterCharts',
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
    
    # Fragments
    'monthly_trend_fragment',
    'yoy_comparison_fragment',
    'sales_detail_fragment',
    'pivot_analysis_fragment',
    'backlog_list_fragment',
    'backlog_by_etd_fragment',
    'backlog_risk_analysis_fragment',
    'kpi_assignments_fragment',
    'kpi_progress_fragment',
    'kpi_center_ranking_fragment',
    'top_performers_fragment',
    'export_report_fragment',
    
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
    'KPI_CENTER_TYPES',
    'COLORS',
    'CHART_WIDTH',
    'CHART_HEIGHT',
    
    # Constants - Debug
    'DEBUG_TIMING',
    'DEBUG_QUERY_TIMING',
]

__version__ = '4.1.0'