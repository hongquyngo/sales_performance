# utils/kpi_center_performance/payment/__init__.py
"""
Payment & Collection Detail tab for KPI Center Performance.

Adapted from salesperson_performance/payment for KPI Center context.

Architecture:
  Data source: customer_ar_by_kpi_center_view
    - Pre-calculated outstanding, collected, aging in SQL
    - Based on actual payment records (customer_payment_details)
    - Sales split by KPI Center (split_rate_percent)

  AR Mode ("All Outstanding AR"):
    - Query: WHERE payment_status IN ('Unpaid', 'Partially Paid')

  Period Mode ("Period Invoices"):
    - Query: WHERE inv_date BETWEEN :start AND :end

  Layout:
    - Unified metrics banner above tabs
    - 2 sub-tabs: Overview & Aging | Invoice Detail
    - Invoice Detail: AR by KPI Center summary + Invoice table
      with click-to-select → payment/doc detail panel

VERSION: 1.0.0
"""

from .fragments import (
    payment_tab_fragment,
    payment_list_fragment,
    payment_summary_fragment,
)
from .ar_drilldown import (
    ar_by_kpi_center_fragment,
    ar_summary_section,
)
from .s3_utils import get_s3_manager, generate_doc_url

__all__ = [
    'payment_tab_fragment',
    'payment_list_fragment',
    'payment_summary_fragment',
    'ar_by_kpi_center_fragment',
    'ar_summary_section',
    'get_s3_manager',
    'generate_doc_url',
]