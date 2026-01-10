# utils/salesperson_performance/setup/product_portfolio.py
"""
Product Portfolio Tab Component

Displays product/brand portfolio analysis:
- Aggregates sales by brand
- Shows Revenue, GP, GP%, Product count, Customer count
- Sorted by Revenue (descending)

VERSION: 1.0.0
"""

import logging
from typing import Dict, List, Optional

import pandas as pd
import streamlit as st

logger = logging.getLogger(__name__)


def prepare_product_portfolio(
    sales_df: pd.DataFrame,
    group_by: str = 'brand'
) -> pd.DataFrame:
    """
    Prepare product/brand portfolio summary from sales data.
    
    Aggregates sales data by brand (or product) with metrics:
    - Total Revenue (sales_by_split_usd)
    - Total GP (gross_profit_by_split_usd)
    - Unique products count
    - Unique customers count
    - GP percentage
    
    Args:
        sales_df: Sales DataFrame from unified_sales_by_salesperson_view
        group_by: Column to group by ('brand' or 'product_pn')
        
    Returns:
        DataFrame with portfolio metrics, sorted by Revenue descending
    """
    if sales_df.empty:
        if group_by == 'brand':
            return pd.DataFrame(columns=['Brand', 'Revenue', 'GP', 'Products', 'Customers', 'GP %'])
        else:
            return pd.DataFrame(columns=['Product', 'Revenue', 'GP', 'Customers', 'Invoices', 'GP %'])
    
    # Check required columns
    required_cols = [group_by, 'sales_by_split_usd', 'gross_profit_by_split_usd']
    missing_cols = [col for col in required_cols if col not in sales_df.columns]
    
    if missing_cols:
        logger.warning(f"Missing columns for product portfolio: {missing_cols}")
        return pd.DataFrame()
    
    # Build aggregation dict based on group_by
    if group_by == 'brand':
        agg_dict = {
            'sales_by_split_usd': 'sum',
            'gross_profit_by_split_usd': 'sum',
            'product_pn': pd.Series.nunique,
            'customer_id': pd.Series.nunique
        }
        column_rename = {
            'brand': 'Brand',
            'sales_by_split_usd': 'Revenue',
            'gross_profit_by_split_usd': 'GP',
            'product_pn': 'Products',
            'customer_id': 'Customers'
        }
    else:  # group_by == 'product_pn'
        agg_dict = {
            'sales_by_split_usd': 'sum',
            'gross_profit_by_split_usd': 'sum',
            'customer_id': pd.Series.nunique,
            'inv_number': pd.Series.nunique
        }
        column_rename = {
            'product_pn': 'Product',
            'sales_by_split_usd': 'Revenue',
            'gross_profit_by_split_usd': 'GP',
            'customer_id': 'Customers',
            'inv_number': 'Invoices'
        }
    
    # Filter out None/missing columns from agg_dict
    agg_dict = {k: v for k, v in agg_dict.items() if k in sales_df.columns}
    
    # Aggregate
    portfolio = sales_df.groupby(group_by).agg(agg_dict).reset_index()
    
    # Rename columns
    portfolio.rename(columns=column_rename, inplace=True)
    
    # Calculate GP %
    if 'Revenue' in portfolio.columns and 'GP' in portfolio.columns:
        portfolio['GP %'] = (portfolio['GP'] / portfolio['Revenue'] * 100).round(1)
        portfolio['GP %'] = portfolio['GP %'].fillna(0)
    
    # Sort by Revenue descending
    if 'Revenue' in portfolio.columns:
        portfolio = portfolio.sort_values('Revenue', ascending=False)
    
    return portfolio.reset_index(drop=True)


def get_product_portfolio_summary(portfolio_df: pd.DataFrame, is_brand: bool = True) -> Dict:
    """
    Calculate summary metrics for product portfolio.
    
    Args:
        portfolio_df: Product portfolio DataFrame
        is_brand: True if grouped by brand, False if by product
        
    Returns:
        Dict with summary metrics
    """
    if portfolio_df.empty:
        return {
            'total_items': 0,
            'total_revenue': 0,
            'total_gp': 0,
            'total_products': 0,
            'total_customers': 0,
        }
    
    total_items = len(portfolio_df)
    total_revenue = portfolio_df['Revenue'].sum() if 'Revenue' in portfolio_df.columns else 0
    total_gp = portfolio_df['GP'].sum() if 'GP' in portfolio_df.columns else 0
    
    if is_brand:
        total_products = portfolio_df['Products'].sum() if 'Products' in portfolio_df.columns else 0
        total_customers = portfolio_df['Customers'].max() if 'Customers' in portfolio_df.columns else 0
    else:
        total_products = total_items
        total_customers = portfolio_df['Customers'].sum() if 'Customers' in portfolio_df.columns else 0
    
    return {
        'total_items': total_items,
        'total_revenue': total_revenue,
        'total_gp': total_gp,
        'total_products': total_products,
        'total_customers': total_customers,
    }


def render_product_portfolio_summary(summary: Dict, is_brand: bool = True):
    """
    Render summary metrics for product portfolio.
    
    Args:
        summary: Summary dict from get_product_portfolio_summary()
        is_brand: True if grouped by brand
    """
    col1, col2, col3, col4 = st.columns(4)
    
    item_label = "Brands" if is_brand else "Products"
    
    with col1:
        st.metric(
            label=f"Total {item_label}",
            value=f"{summary['total_items']:,}",
            help=f"Number of unique {item_label.lower()} in the period"
        )
    
    with col2:
        st.metric(
            label="Total Revenue",
            value=f"${summary['total_revenue']:,.0f}",
            help=f"Sum of revenue across all {item_label.lower()}"
        )
    
    with col3:
        st.metric(
            label="Total GP",
            value=f"${summary['total_gp']:,.0f}",
            help=f"Sum of gross profit across all {item_label.lower()}"
        )
    
    with col4:
        if is_brand:
            st.metric(
                label="Total Products",
                value=f"{summary['total_products']:,}",
                help="Total unique products across all brands"
            )
        else:
            st.metric(
                label="Total Customers",
                value=f"{summary['total_customers']:,}",
                help="Total unique customers buying these products"
            )


def render_product_portfolio_table(
    portfolio_df: pd.DataFrame,
    height: int = 400,
    is_brand: bool = True
):
    """
    Render the product portfolio data table.
    
    Args:
        portfolio_df: Product portfolio DataFrame
        height: Table height in pixels
        is_brand: True if grouped by brand
    """
    if portfolio_df.empty:
        st.info("No product data to display")
        return
    
    # Select columns based on grouping
    if is_brand:
        display_cols = ['Brand', 'Revenue', 'GP', 'Products', 'Customers', 'GP %']
    else:
        display_cols = ['Product', 'Revenue', 'GP', 'Customers', 'Invoices', 'GP %']
    
    # Filter to available columns
    display_cols = [col for col in display_cols if col in portfolio_df.columns]
    
    # Apply styling
    styled_df = portfolio_df[display_cols].style.format({
        'Revenue': '${:,.0f}',
        'GP': '${:,.0f}',
        'GP %': '{:.1f}%'
    })
    
    st.dataframe(
        styled_df,
        use_container_width=True,
        hide_index=True,
        height=height,
    )


def render_product_portfolio_tab(
    sales_df: pd.DataFrame,
    group_by: str = 'brand',
    show_summary: bool = True,
    key_prefix: str = "product"
):
    """
    Render complete Product Portfolio tab content.
    
    This is the main entry point for the My Products sub-tab.
    
    Args:
        sales_df: Sales DataFrame
        group_by: Column to group by ('brand' or 'product_pn')
        show_summary: Whether to show summary metrics
        key_prefix: Prefix for widget keys
        
    Example:
        with setup_tab3:
            render_product_portfolio_tab(
                sales_df=data['sales'],
                group_by='brand',
                show_summary=True
            )
    """
    is_brand = group_by == 'brand'
    title = "#### 📦 Product Portfolio" if is_brand else "#### 📦 Product List"
    st.markdown(title)
    
    if sales_df.empty:
        st.info("No product data available")
        return
    
    # Option to switch view (brand vs product)
    view_options = st.radio(
        "View by",
        options=['Brand', 'Product'],
        horizontal=True,
        key=f"{key_prefix}_view",
        label_visibility="collapsed"
    )
    
    actual_group_by = 'brand' if view_options == 'Brand' else 'product_pn'
    is_brand = actual_group_by == 'brand'
    
    # Prepare portfolio data
    portfolio_df = prepare_product_portfolio(sales_df, group_by=actual_group_by)
    
    if portfolio_df.empty:
        st.info("No product data available")
        return
    
    # Show summary metrics (optional)
    if show_summary:
        summary = get_product_portfolio_summary(portfolio_df, is_brand=is_brand)
        render_product_portfolio_summary(summary, is_brand=is_brand)
        st.divider()
    
    # Show record count
    item_label = "brands" if is_brand else "products"
    st.caption(f"📊 {len(portfolio_df):,} {item_label}")
    
    # Render table
    render_product_portfolio_table(portfolio_df, is_brand=is_brand)


# =============================================================================
# ADVANCED ANALYSIS (Optional enhancements)
# =============================================================================

def get_top_brands(
    portfolio_df: pd.DataFrame,
    top_n: int = 10,
    metric: str = 'Revenue'
) -> pd.DataFrame:
    """
    Get top N brands by specified metric.
    
    Args:
        portfolio_df: Brand portfolio DataFrame
        top_n: Number of top brands to return
        metric: Metric to sort by ('Revenue', 'GP', 'Products')
        
    Returns:
        Top N brands DataFrame
    """
    if portfolio_df.empty or metric not in portfolio_df.columns:
        return pd.DataFrame()
    
    return portfolio_df.nlargest(top_n, metric)


def calculate_brand_concentration(
    portfolio_df: pd.DataFrame,
    top_percent: float = 0.8
) -> Dict:
    """
    Calculate brand concentration metrics (Pareto analysis).
    
    Args:
        portfolio_df: Brand portfolio DataFrame
        top_percent: Threshold for concentration analysis (default 80%)
        
    Returns:
        Dict with concentration metrics
    """
    if portfolio_df.empty or 'Revenue' not in portfolio_df.columns:
        return {
            'top_brand_count': 0,
            'top_brand_revenue': 0,
            'top_brand_percent': 0,
            'concentration_ratio': 0,
        }
    
    total_revenue = portfolio_df['Revenue'].sum()
    if total_revenue == 0:
        return {
            'top_brand_count': 0,
            'top_brand_revenue': 0,
            'top_brand_percent': 0,
            'concentration_ratio': 0,
        }
    
    # Sort by revenue and calculate cumulative
    sorted_df = portfolio_df.sort_values('Revenue', ascending=False).copy()
    sorted_df['cumulative_revenue'] = sorted_df['Revenue'].cumsum()
    sorted_df['cumulative_percent'] = sorted_df['cumulative_revenue'] / total_revenue
    
    # Find number of brands making up top_percent of revenue
    top_brands = sorted_df[sorted_df['cumulative_percent'] <= top_percent]
    
    # Include one more if we haven't reached the threshold
    if len(top_brands) < len(sorted_df):
        top_brands = sorted_df.head(len(top_brands) + 1)
    
    top_count = len(top_brands)
    top_revenue = top_brands['Revenue'].sum()
    
    return {
        'top_brand_count': top_count,
        'top_brand_revenue': top_revenue,
        'top_brand_percent': (top_revenue / total_revenue * 100) if total_revenue > 0 else 0,
        'concentration_ratio': (top_count / len(portfolio_df) * 100) if len(portfolio_df) > 0 else 0,
    }
