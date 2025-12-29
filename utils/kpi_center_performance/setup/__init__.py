# utils/kpi_center_performance/setup/__init__.py
"""
Setup Tab Module for KPI Center Performance

Full management console with 4 sub-tabs:
1. Split Rules - CRUD for kpi_center_split_by_customer_product
2. KPI Assignments - CRUD for sales_kpi_center_assignments
3. Hierarchy - Tree view of kpi_centers
4. Validation - Health check dashboard

VERSION: 2.0.0
CHANGELOG:
- v2.0.0: Full CRUD implementation per proposal v3.4.0
          - Complete CRUD operations for Split Rules
          - Complete CRUD operations for KPI Assignments
          - Interactive hierarchy tree with CRUD
          - Validation dashboard with issue tracking
          - Bulk operations support
          - Permission-based access control
- v1.0.0: Initial read-only version
"""

# Queries
from .queries import SetupQueries

# Fragments
from .fragments import (
    # Main entry point
    setup_tab_fragment,
    
    # Sub-tab sections (can be used independently)
    split_rules_section,
    kpi_assignments_section,
    hierarchy_section,
    validation_section,
    
    # Constants
    KPI_TYPES,
    KPI_TYPE_ICONS,
    KPI_ICONS,
)

__all__ = [
    # Queries
    'SetupQueries',
    
    # Main Fragment
    'setup_tab_fragment',
    
    # Sub-tab Fragments
    'split_rules_section',
    'kpi_assignments_section',
    'hierarchy_section',
    'validation_section',
    
    # Constants
    'KPI_TYPES',
    'KPI_TYPE_ICONS',
    'KPI_ICONS',
]

__version__ = '2.0.0'