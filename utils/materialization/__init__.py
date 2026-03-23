# utils/materialization/__init__.py
"""
Materialization Management Package

Manages materialized views/tables in MySQL:
- Registry of all materialized tables
- Refresh procedures (scheduled + on-demand)
- Freshness monitoring
- Refresh history & health metrics

Usage:
    from utils.materialization import MatManager, get_mat_manager
    
    mgr = get_mat_manager()
    mgr.refresh("mat_sales_invoice_full_looker")
    info = mgr.get_freshness("mat_sales_invoice_full_looker")
"""

from .manager import (
    MatManager,
    get_mat_manager,
    MatTableInfo,
)

__all__ = [
    'MatManager',
    'get_mat_manager',
    'MatTableInfo',
]
