# utils/kpi_center_performance/setup/__init__.py
"""
Setup Tab Module for KPI Center Performance

Handles all Setup tab functionality:
- KPI Center Split Rules (CRUD)
- KPI Assignments (CRUD)
- Hierarchy View & Management
- Validation Dashboard

VERSION: 1.0.0
CHANGELOG:
- v1.0.0: Initial extraction from main module
          - Moved setup-related queries from queries.py
          - Created setup_tab_fragment for UI
          - Maintains backward compatibility with main page
"""

# Queries
from .queries import SetupQueries

# Fragments
from .fragments import (
    setup_tab_fragment,
    split_rules_section,
    hierarchy_section,
)

__all__ = [
    # Queries
    'SetupQueries',
    
    # Fragments
    'setup_tab_fragment',
    'split_rules_section',
    'hierarchy_section',
]

__version__ = '1.0.0'