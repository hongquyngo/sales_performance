# utils/salesperson_performance/payment/__init__.py
"""
Payment & Collection Detail tab for Salesperson Performance.

Adapted from legal_entity_performance/payment module.
Uses unified_sales_by_salesperson_view with payment columns
(payment_status, payment_ratio, due_date).

USD calculation per line:
  collected_usd   = sales_by_split_usd × payment_ratio
  outstanding_usd = sales_by_split_usd × (1 - payment_ratio)

VERSION: 1.0.0
"""

from .fragments import (
    payment_tab_fragment,
    payment_list_fragment,
    payment_summary_fragment,
)

__all__ = [
    'payment_tab_fragment',
    'payment_list_fragment',
    'payment_summary_fragment',
]
