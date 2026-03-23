# utils/salesperson_performance/payment/__init__.py
"""
Payment & Collection Detail tab for Salesperson Performance.

Architecture (v3.0 — unified layout, no data duplication):

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

  Layout (v4.0):
    - Unified metrics banner above tabs (no duplication)
    - 2 sub-tabs: Overview & Aging | Invoice Detail
    - Invoice Detail combines: AR summary + Top Customers chart
      + Invoice table with click-to-select → payment/doc detail panel
    - Top-level filters include "Exclude internal customers"
    - Salesperson drill-down selectbox removed (top-level filter suffices)

VERSION: 4.1.0
"""

from .fragments import (
    payment_tab_fragment,
    payment_list_fragment,
    payment_summary_fragment,
)
from .ar_drilldown import ar_by_salesperson_fragment, ar_summary_section

# MOVED v4.1.0: s3_utils now lives at parent level (salesperson_performance/)
# Re-export here for backward compatibility
from utils.salesperson_performance.s3_utils import get_s3_manager, generate_doc_url

__all__ = [
    'payment_tab_fragment',
    'payment_list_fragment',
    'payment_summary_fragment',
    'ar_by_salesperson_fragment',
    'ar_summary_section',
    'get_s3_manager',
    'generate_doc_url',
]