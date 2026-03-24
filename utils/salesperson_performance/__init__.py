# utils/salesperson_performance/__init__.py
"""
Salesperson Performance Module

Isolated utilities for salesperson performance tracking page.
All components are self-contained within this module.

Components:
- access_control: Role-based data access (sales/manager/admin)
- queries: SQL queries and data loading with caching
- metrics: KPI calculations and aggregations
- filters: Sidebar filter components
- charts: Altair visualizations
- export: Formatted Excel report generation
- s3_utils: S3 presigned URL generation for document viewing (MOVED v4.1.0)

Usage:
    from utils.salesperson_performance import (
        AccessControl,
        SalespersonQueries,
        SalespersonMetrics,
        SalespersonFilters,
        SalespersonCharts,
        SalespersonExport,
        CONSTANTS,
        generate_doc_url,
    )
"""

from .access_control import AccessControl
from .queries import SalespersonQueries
from .metrics import SalespersonMetrics
from .filters import SalespersonFilters
from .charts import SalespersonCharts
from .export import SalespersonExport

# Fragments
from .fragments import kpi_progress_fragment

# Performance Logger
from .perf_logger import perf, PerfCategory

# S3 Utilities (MOVED v4.1.0: from payment/s3_utils to module root)
from .s3_utils import get_s3_manager, generate_doc_url

# Notification (NEW v4.2.0: Phase 1 — ad-hoc bulletin email)
from .notification.ui import render_email_bulletin_button

# Constants
from .constants import (
    COLORS,
    MONTH_ORDER,
    PERIOD_TYPES,
    KPI_TYPES,
    FULL_ACCESS_ROLES,
    TEAM_ACCESS_ROLES,
    SELF_ACCESS_ROLES,
    LOOKBACK_YEARS,
    CHART_WIDTH,
    CHART_HEIGHT,
)

__all__ = [
    # Classes
    'AccessControl',
    'SalespersonQueries',
    'SalespersonMetrics',
    'SalespersonFilters',
    'SalespersonCharts',
    'SalespersonExport',
    
    # Fragments
    'kpi_progress_fragment',
    
    # Performance Logger
    'perf',
    'PerfCategory',
    
    # S3 Utilities
    'get_s3_manager',
    'generate_doc_url',
    
    # Notification
    'render_email_bulletin_button',
    
    # Constants
    'COLORS',
    'MONTH_ORDER',
    'PERIOD_TYPES',
    'KPI_TYPES',
    'FULL_ACCESS_ROLES',
    'TEAM_ACCESS_ROLES',
    'SELF_ACCESS_ROLES',
    'LOOKBACK_YEARS',
    'CHART_WIDTH',
    'CHART_HEIGHT',
]

__version__ = '4.2.0'