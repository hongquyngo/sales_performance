# utils/salesperson_performance/setup/__init__.py
"""
Setup Tab Module for Salesperson Performance


VERSION: 1.0.0
"""

from .fragments import setup_tab_fragment
from .sales_split import render_sales_split_tab, SalesSplitFilter
from .customer_portfolio import render_customer_portfolio_tab, prepare_customer_portfolio
from .product_portfolio import render_product_portfolio_tab, prepare_product_portfolio
from .helpers import is_period_active, is_period_expired

__all__ = [
    # Main fragment
    'setup_tab_fragment',
    
    # Sales Split
    'render_sales_split_tab',
    'SalesSplitFilter',
    
    # Customer Portfolio
    'render_customer_portfolio_tab',
    'prepare_customer_portfolio',
    
    # Product Portfolio
    'render_product_portfolio_tab',
    'prepare_product_portfolio',
    
    # Helpers
    'is_period_active',
    'is_period_expired',
]

__version__ = '1.0.0'
