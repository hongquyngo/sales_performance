# utils/kpi_center_performance/setup/__init__.py
"""
Setup Tab Module for KPI Center Performance

Full management console with 3 sub-tabs:
1. Split Rules - CRUD for kpi_center_split_by_customer_product (with integrated validation)
2. KPI Assignments - CRUD for sales_kpi_center_assignments (with integrated validation)
3. Hierarchy - Tree view of kpi_centers

Note: Validation has been merged into Split Rules and KPI Assignments tabs for better UX.
      validation_section is kept for backward compatibility but deprecated.

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
    validation_section,  # Deprecated: kept for backward compatibility
    
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
    'validation_section',  # Deprecated
    
    # Constants
    'KPI_TYPES',
    'KPI_TYPE_ICONS',
    'KPI_ICONS',
]

__version__ = '2.4.1'