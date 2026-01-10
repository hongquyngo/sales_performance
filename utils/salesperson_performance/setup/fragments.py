# utils/salesperson_performance/setup/fragments.py
"""
Streamlit Fragments for Setup Tab

Uses @st.fragment to enable partial reruns for filter-heavy sections.
Each fragment only reruns when its internal widgets change,
NOT when sidebar filters or other sections change.

Main Entry Point:
- setup_tab_fragment: Renders the complete Setup & Reference tab

VERSION: 1.0.0
"""

import streamlit as st
import pandas as pd
from typing import Dict, Optional, Any

from .sales_split import render_sales_split_tab
from .customer_portfolio import render_customer_portfolio_tab
from .product_portfolio import render_product_portfolio_tab


@st.fragment
def setup_tab_fragment(
    sales_split_df: pd.DataFrame,
    sales_df: pd.DataFrame,
    active_filters: Optional[Dict] = None,
    show_summary: bool = True,
    fragment_key: str = "setup"
):
    """
    
    This is the main entry point for the Setup tab. It uses @st.fragment
    to prevent unnecessary reruns when other parts of the page change.
    
            )
    """
    st.subheader("⚙️ Setup & Reference")
    
    # Create sub-tabs
    setup_tab1, setup_tab2, setup_tab3 = st.tabs([
        "👥 Sales Split",
        "📋 My Customers",
        "📦 My Products"
    ])
    
    # Tab 1: Sales Split
    with setup_tab1:
        render_sales_split_tab(
            sales_split_df=sales_split_df,
            key_prefix=f"{fragment_key}_split"
        )
    
    # Tab 2: My Customers
    with setup_tab2:
        render_customer_portfolio_tab(
            sales_df=sales_df,
            show_summary=show_summary,
            key_prefix=f"{fragment_key}_customer"
        )
    
    # Tab 3: My Products
    with setup_tab3:
        render_product_portfolio_tab(
            sales_df=sales_df,
            show_summary=show_summary,
            key_prefix=f"{fragment_key}_product"
        )


@st.fragment
def sales_split_fragment(
    sales_split_df: pd.DataFrame,
    fragment_key: str = "split"
):
    """
    Standalone fragment for Sales Split tab only.
    
    Use this when you need just the Sales Split functionality
    without the other portfolio tabs.
    
    Args:
        sales_split_df: Sales split DataFrame
        fragment_key: Unique key prefix for widgets
    """
    render_sales_split_tab(
        sales_split_df=sales_split_df,
        key_prefix=fragment_key
    )


@st.fragment
def customer_portfolio_fragment(
    sales_df: pd.DataFrame,
    show_summary: bool = True,
    fragment_key: str = "customer"
):
    """
    Standalone fragment for Customer Portfolio tab only.
    
    Args:
        sales_df: Sales DataFrame
        show_summary: Whether to show summary metrics
        fragment_key: Unique key prefix for widgets
    """
    render_customer_portfolio_tab(
        sales_df=sales_df,
        show_summary=show_summary,
        key_prefix=fragment_key
    )


@st.fragment
def product_portfolio_fragment(
    sales_df: pd.DataFrame,
    show_summary: bool = True,
    fragment_key: str = "product"
):
    """
    Standalone fragment for Product Portfolio tab only.
    
    Args:
        sales_df: Sales DataFrame
        show_summary: Whether to show summary metrics
        fragment_key: Unique key prefix for widgets
    """
    render_product_portfolio_tab(
        sales_df=sales_df,
        show_summary=show_summary,
        key_prefix=fragment_key
    )


# =============================================================================
# COMBINED PORTFOLIO FRAGMENT
# =============================================================================

@st.fragment
def portfolio_tabs_fragment(
    sales_df: pd.DataFrame,
    show_summary: bool = True,
    fragment_key: str = "portfolio"
):
    """
    Fragment combining Customer and Product portfolio tabs.
    
    Useful when you want portfolio analysis without Sales Split.
    
    Args:
        sales_df: Sales DataFrame
        show_summary: Whether to show summary metrics
        fragment_key: Unique key prefix for widgets
    """
    tab1, tab2 = st.tabs(["📋 Customers", "📦 Products"])
    
    with tab1:
        render_customer_portfolio_tab(
            sales_df=sales_df,
            show_summary=show_summary,
            key_prefix=f"{fragment_key}_customer"
        )
    
    with tab2:
        render_product_portfolio_tab(
            sales_df=sales_df,
            show_summary=show_summary,
            key_prefix=f"{fragment_key}_product"
        )


# =============================================================================
# EXPORT
# =============================================================================

__all__ = [
    'setup_tab_fragment',
    'sales_split_fragment',
    'customer_portfolio_fragment',
    'product_portfolio_fragment',
    'portfolio_tabs_fragment',
]
