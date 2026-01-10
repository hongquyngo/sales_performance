# utils/salesperson_performance/setup/customer_portfolio.py
"""
Customer Portfolio Tab Component

Displays customer portfolio analysis:
- Aggregates sales by customer
- Shows Revenue, GP, GP%, Invoice count, Last Invoice date
- Sorted by Revenue (descending)

VERSION: 1.0.0
"""

import logging
from typing import Dict, List, Optional

import pandas as pd
import streamlit as st

logger = logging.getLogger(__name__)


def prepare_customer_portfolio(sales_df: pd.DataFrame) -> pd.DataFrame:
    """
    Prepare customer portfolio summary from sales data.
    
    Aggregates sales data by customer with metrics:
    - Total Revenue (sales_by_split_usd)
    - Total GP (gross_profit_by_split_usd)
    - Invoice count
    - Last invoice date
    - GP percentage
    
    Args:
        sales_df: Sales DataFrame from unified_sales_by_salesperson_view
        
    Returns:
        DataFrame with columns: ID, Customer, Revenue, GP, Invoices, Last Invoice, GP %
        Sorted by Revenue descending
    """
    if sales_df.empty:
        return pd.DataFrame(columns=['ID', 'Customer', 'Revenue', 'GP', 'Invoices', 'Last Invoice', 'GP %'])
    
    # Check required columns
    required_cols = ['customer_id', 'customer', 'sales_by_split_usd', 'gross_profit_by_split_usd']
    missing_cols = [col for col in required_cols if col not in sales_df.columns]
    
    if missing_cols:
        logger.warning(f"Missing columns for customer portfolio: {missing_cols}")
        return pd.DataFrame(columns=['ID', 'Customer', 'Revenue', 'GP', 'Invoices', 'Last Invoice', 'GP %'])
    
    # Aggregate by customer
    agg_dict = {
        'sales_by_split_usd': 'sum',
        'gross_profit_by_split_usd': 'sum',
    }
    
    # Add optional columns
    if 'inv_number' in sales_df.columns:
        agg_dict['inv_number'] = pd.Series.nunique
    if 'inv_date' in sales_df.columns:
        agg_dict['inv_date'] = 'max'
    
    customer_portfolio = sales_df.groupby(['customer_id', 'customer']).agg(agg_dict).reset_index()
    
    # Rename columns
    column_rename = {
        'customer_id': 'ID',
        'customer': 'Customer',
        'sales_by_split_usd': 'Revenue',
        'gross_profit_by_split_usd': 'GP',
        'inv_number': 'Invoices',
        'inv_date': 'Last Invoice'
    }
    customer_portfolio.rename(columns=column_rename, inplace=True)
    
    # Calculate GP %
    customer_portfolio['GP %'] = (
        customer_portfolio['GP'] / customer_portfolio['Revenue'] * 100
    ).round(1)
    
    # Handle division by zero
    customer_portfolio['GP %'] = customer_portfolio['GP %'].fillna(0)
    
    # Sort by Revenue descending
    customer_portfolio = customer_portfolio.sort_values('Revenue', ascending=False)
    
    return customer_portfolio.reset_index(drop=True)


def get_customer_portfolio_summary(portfolio_df: pd.DataFrame) -> Dict:
    """
    Calculate summary metrics for customer portfolio.
    
    Args:
        portfolio_df: Customer portfolio DataFrame
        
    Returns:
        Dict with total_customers, total_revenue, total_gp, avg_revenue_per_customer
    """
    if portfolio_df.empty:
        return {
            'total_customers': 0,
            'total_revenue': 0,
            'total_gp': 0,
            'avg_revenue_per_customer': 0,
            'avg_gp_per_customer': 0,
            'total_invoices': 0,
        }
    
    total_customers = len(portfolio_df)
    total_revenue = portfolio_df['Revenue'].sum() if 'Revenue' in portfolio_df.columns else 0
    total_gp = portfolio_df['GP'].sum() if 'GP' in portfolio_df.columns else 0
    total_invoices = portfolio_df['Invoices'].sum() if 'Invoices' in portfolio_df.columns else 0
    
    return {
        'total_customers': total_customers,
        'total_revenue': total_revenue,
        'total_gp': total_gp,
        'avg_revenue_per_customer': total_revenue / total_customers if total_customers > 0 else 0,
        'avg_gp_per_customer': total_gp / total_customers if total_customers > 0 else 0,
        'total_invoices': total_invoices,
    }


def render_customer_portfolio_summary(summary: Dict):
    """
    Render summary metrics for customer portfolio.
    
    Args:
        summary: Summary dict from get_customer_portfolio_summary()
    """
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            label="Total Customers",
            value=f"{summary['total_customers']:,}",
            help="Number of unique customers in the period"
        )
    
    with col2:
        st.metric(
            label="Total Revenue",
            value=f"${summary['total_revenue']:,.0f}",
            help="Sum of revenue across all customers"
        )
    
    with col3:
        st.metric(
            label="Total GP",
            value=f"${summary['total_gp']:,.0f}",
            help="Sum of gross profit across all customers"
        )
    
    with col4:
        st.metric(
            label="Avg Revenue/Customer",
            value=f"${summary['avg_revenue_per_customer']:,.0f}",
            help="Average revenue per customer"
        )


def render_customer_portfolio_table(
    portfolio_df: pd.DataFrame,
    height: int = 400,
    show_id: bool = False
):
    """
    Render the customer portfolio data table.
    
    Args:
        portfolio_df: Customer portfolio DataFrame
        height: Table height in pixels
        show_id: Whether to show customer ID column
    """
    if portfolio_df.empty:
        st.info("No customer data to display")
        return
    
    # Select columns to display
    display_cols = ['Customer', 'Revenue', 'GP', 'Invoices', 'Last Invoice', 'GP %']
    if show_id:
        display_cols = ['ID'] + display_cols
    
    # Filter to available columns
    display_cols = [col for col in display_cols if col in portfolio_df.columns]
    
    # Column configuration
    column_config = {
        'ID': st.column_config.NumberColumn('ID', width='small'),
        'Customer': st.column_config.TextColumn('Customer', width='large'),
        'Revenue': st.column_config.NumberColumn(
            'Revenue',
            format='$%,.0f',
            width='medium'
        ),
        'GP': st.column_config.NumberColumn(
            'GP',
            format='$%,.0f',
            width='medium'
        ),
        'Invoices': st.column_config.NumberColumn('Invoices', width='small'),
        'Last Invoice': st.column_config.DateColumn(
            'Last Invoice',
            format='YYYY-MM-DD',
            width='medium'
        ),
        'GP %': st.column_config.NumberColumn(
            'GP %',
            format='%.1f%%',
            width='small'
        ),
    }
    
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


def render_customer_portfolio_tab(
    sales_df: pd.DataFrame,
    show_summary: bool = True,
    show_id: bool = False,
    key_prefix: str = "customer"
):
    """
    Render complete Customer Portfolio tab content.
    
    This is the main entry point for the My Customers sub-tab.
    
    Args:
        sales_df: Sales DataFrame
        show_summary: Whether to show summary metrics
        show_id: Whether to show customer ID column
        key_prefix: Prefix for widget keys
        
    Example:
        with setup_tab2:
            render_customer_portfolio_tab(
                sales_df=data['sales'],
                show_summary=True
            )
    """
    st.markdown("#### 📋 Customer Portfolio")
    
    if sales_df.empty:
        st.info("No customer data available")
        return
    
    # Prepare portfolio data
    portfolio_df = prepare_customer_portfolio(sales_df)
    
    if portfolio_df.empty:
        st.info("No customer data available")
        return
    
    # Show summary metrics (optional)
    if show_summary:
        summary = get_customer_portfolio_summary(portfolio_df)
        render_customer_portfolio_summary(summary)
        st.divider()
    
    # Show record count
    st.caption(f"📊 {len(portfolio_df):,} customers")
    
    # Render table
    render_customer_portfolio_table(portfolio_df, show_id=show_id)


# =============================================================================
# ADVANCED ANALYSIS (Optional enhancements)
# =============================================================================

def get_top_customers(
    portfolio_df: pd.DataFrame,
    top_n: int = 10,
    metric: str = 'Revenue'
) -> pd.DataFrame:
    """
    Get top N customers by specified metric.
    
    Args:
        portfolio_df: Customer portfolio DataFrame
        top_n: Number of top customers to return
        metric: Metric to sort by ('Revenue', 'GP', 'Invoices')
        
    Returns:
        Top N customers DataFrame
    """
    if portfolio_df.empty or metric not in portfolio_df.columns:
        return pd.DataFrame()
    
    return portfolio_df.nlargest(top_n, metric)


def calculate_customer_concentration(
    portfolio_df: pd.DataFrame,
    top_percent: float = 0.8
) -> Dict:
    """
    Calculate customer concentration metrics.
    
    Args:
        portfolio_df: Customer portfolio DataFrame
        top_percent: Threshold for concentration analysis (default 80%)
        
    Returns:
        Dict with concentration metrics
    """
    if portfolio_df.empty or 'Revenue' not in portfolio_df.columns:
        return {
            'top_customer_count': 0,
            'top_customer_revenue': 0,
            'top_customer_percent': 0,
            'concentration_ratio': 0,
        }
    
    total_revenue = portfolio_df['Revenue'].sum()
    if total_revenue == 0:
        return {
            'top_customer_count': 0,
            'top_customer_revenue': 0,
            'top_customer_percent': 0,
            'concentration_ratio': 0,
        }
    
    # Sort by revenue and calculate cumulative
    sorted_df = portfolio_df.sort_values('Revenue', ascending=False)
    sorted_df['cumulative_revenue'] = sorted_df['Revenue'].cumsum()
    sorted_df['cumulative_percent'] = sorted_df['cumulative_revenue'] / total_revenue
    
    # Find number of customers making up top_percent of revenue
    top_customers = sorted_df[sorted_df['cumulative_percent'] <= top_percent]
    
    # Include one more if we haven't reached the threshold
    if len(top_customers) < len(sorted_df):
        top_customers = sorted_df.head(len(top_customers) + 1)
    
    top_count = len(top_customers)
    top_revenue = top_customers['Revenue'].sum()
    
    return {
        'top_customer_count': top_count,
        'top_customer_revenue': top_revenue,
        'top_customer_percent': (top_revenue / total_revenue * 100) if total_revenue > 0 else 0,
        'concentration_ratio': (top_count / len(portfolio_df) * 100) if len(portfolio_df) > 0 else 0,
    }
