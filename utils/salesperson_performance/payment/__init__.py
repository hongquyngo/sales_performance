# utils/salesperson_performance/payment/__init__.py
"""
Payment & Collection Detail tab for Salesperson Performance.

Architecture (v2.0 — no proxy calculations):

  Data source: customer_ar_by_salesperson_view (for BOTH modes)
    - Pre-calculated outstanding, collected, aging in SQL
    - Based on actual payment records (customer_payment_details)
    - Sales split joined by CURDATE() → CURRENT salesperson
    - Direct from sales_invoice_full_looker_view (1-layer, no UNION)

  AR Mode ("All Outstanding AR"):
    - Query: WHERE payment_status IN ('Unpaid', 'Partially Paid')
    - Method: SalespersonQueries.get_ar_outstanding_data()

  Period Mode ("Period Invoices"):
    - Query: WHERE inv_date BETWEEN :start AND :end
    - Method: SalespersonQueries.get_payment_period_data()

  All amounts are accurate — no proxy/estimated values anywhere.

VERSION: 2.0.0
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