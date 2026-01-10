# utils/salesperson_performance/setup/sales_split.py
"""
Sales Split Tab Component

Displays sales split assignments with filtering capabilities:
- Filter by status (All/Active/Expired)
- Filter by salesperson
- Show split percentage, effective period, approval status

VERSION: 1.0.0
"""

import logging
from dataclasses import dataclass
from datetime import date
from typing import List, Optional, Tuple

import pandas as pd
import streamlit as st

from .helpers import is_period_active, is_period_expired, get_period_status

logger = logging.getLogger(__name__)


@dataclass
class SalesSplitFilter:
    """
    Filter configuration for Sales Split display.
    
    Attributes:
        status: Filter by period status ('All', 'Active', 'Expired')
        salesperson: Filter by salesperson name ('All' or specific name)
    """
    status: str = 'All'
    salesperson: str = 'All'
    
    def is_active(self) -> bool:
        """Check if any filter is applied."""
        return self.status != 'All' or self.salesperson != 'All'


def get_salesperson_options(sales_split_df: pd.DataFrame) -> List[str]:
    """
    Get unique salesperson names from sales split data.
    
    Args:
        sales_split_df: Sales split DataFrame
        
    Returns:
        Sorted list of salesperson names
    """
    if sales_split_df.empty or 'sales_name' not in sales_split_df.columns:
        return []
    
    return sorted(sales_split_df['sales_name'].dropna().unique().tolist())


def filter_sales_split(
    df: pd.DataFrame,
    filter_config: SalesSplitFilter,
    today_str: Optional[str] = None
) -> pd.DataFrame:
    """
    Apply filters to sales split DataFrame.
    
    Args:
        df: Sales split DataFrame
        filter_config: Filter configuration
        today_str: Today's date string (defaults to current date)
        
    Returns:
        Filtered DataFrame
    """
    if df.empty:
        return df
    
    if today_str is None:
        today_str = date.today().strftime('%Y-%m-%d')
    
    filtered = df.copy()
    
    # Filter by effective period status
    if filter_config.status == 'Active':
        if 'effective_period' in filtered.columns:
            filtered = filtered[
                filtered['effective_period'].apply(
                    lambda x: is_period_active(x, today_str)
                )
            ]
    elif filter_config.status == 'Expired':
        if 'effective_period' in filtered.columns:
            filtered = filtered[
                filtered['effective_period'].apply(
                    lambda x: is_period_expired(x, today_str)
                )
            ]
    
    # Filter by salesperson
    if filter_config.salesperson != 'All':
        if 'sales_name' in filtered.columns:
            filtered = filtered[filtered['sales_name'] == filter_config.salesperson]
    
    return filtered


def get_display_columns(df: pd.DataFrame) -> List[str]:
    """
    Get columns to display in sales split table.
    
    Args:
        df: Sales split DataFrame
        
    Returns:
        List of column names that exist in the DataFrame
    """
    preferred_columns = [
        'customer',
        'product_pn',
        'split_percentage',
        'effective_period',
        'approval_status',
        'sales_name'
    ]
    
    return [col for col in preferred_columns if col in df.columns]


def render_sales_split_filters(
    sales_split_df: pd.DataFrame,
    key_prefix: str = "split"
) -> SalesSplitFilter:
    """
    Render filter widgets for Sales Split tab.
    
    Args:
        sales_split_df: Sales split DataFrame for options
        key_prefix: Prefix for widget keys
        
    Returns:
        SalesSplitFilter with selected values
    """
    col1, col2 = st.columns(2)
    
    with col1:
        status = st.selectbox(
            "Status",
            options=['All', 'Active', 'Expired'],
            key=f"{key_prefix}_status",
            help="Filter by effective period status"
        )
    
    with col2:
        salesperson_options = ['All'] + get_salesperson_options(sales_split_df)
        salesperson = st.selectbox(
            "Salesperson",
            options=salesperson_options,
            key=f"{key_prefix}_salesperson",
            help="Filter by assigned salesperson"
        )
    
    return SalesSplitFilter(status=status, salesperson=salesperson)


def render_sales_split_table(
    df: pd.DataFrame,
    height: int = 400,
    max_rows: int = 200
):
    """
    Render the sales split data table.
    
    Args:
        df: Filtered sales split DataFrame
        height: Table height in pixels
        max_rows: Maximum rows to display
    """
    display_cols = get_display_columns(df)
    
    if not display_cols:
        st.warning("No displayable columns in sales split data")
        return
    
    # Column configuration for better display
    column_config = {
        'customer': st.column_config.TextColumn('Customer', width='medium'),
        'product_pn': st.column_config.TextColumn('Product', width='medium'),
        'split_percentage': st.column_config.NumberColumn(
            'Split %',
            format='%.1f%%',
            width='small'
        ),
        'effective_period': st.column_config.TextColumn('Period', width='medium'),
        'approval_status': st.column_config.TextColumn('Status', width='small'),
        'sales_name': st.column_config.TextColumn('Salesperson', width='medium'),
    }
    
    st.dataframe(
        df[display_cols].head(max_rows),
        use_container_width=True,
        hide_index=True,
        height=height,
        column_config={k: v for k, v in column_config.items() if k in display_cols}
    )


def render_sales_split_tab(
    sales_split_df: pd.DataFrame,
    key_prefix: str = "split"
):
    """
    Render complete Sales Split tab content.
    
    This is the main entry point for the Sales Split sub-tab.
    
    Args:
        sales_split_df: Sales split DataFrame
        key_prefix: Prefix for widget keys to avoid conflicts
        
    Example:
        with setup_tab1:
            render_sales_split_tab(
                sales_split_df=data['sales_split'],
                key_prefix="setup_split"
            )
    """
    st.markdown("#### 👥 Sales Split Assignments")
    
    if sales_split_df.empty:
        st.info("No sales split data available")
        return
    
    # Render filters
    filter_config = render_sales_split_filters(sales_split_df, key_prefix)
    
    # Apply filters
    filtered_df = filter_sales_split(sales_split_df, filter_config)
    
    # Show record count
    total_count = len(sales_split_df)
    filtered_count = len(filtered_df)
    
    if filter_config.is_active():
        st.caption(f"📊 Showing {filtered_count:,} of {total_count:,} split assignments")
    else:
        st.caption(f"📊 Showing {filtered_count:,} split assignments")
    
    # Render table
    if filtered_df.empty:
        st.info("No records match the selected filters")
    else:
        render_sales_split_table(filtered_df)


# =============================================================================
# SUMMARY METRICS (Optional enhancement)
# =============================================================================

def calculate_split_summary(df: pd.DataFrame) -> dict:
    """
    Calculate summary metrics for sales split data.
    
    Args:
        df: Sales split DataFrame
        
    Returns:
        Dict with summary metrics
    """
    if df.empty:
        return {
            'total_assignments': 0,
            'unique_customers': 0,
            'unique_products': 0,
            'unique_salespeople': 0,
            'active_count': 0,
            'expired_count': 0,
        }
    
    today_str = date.today().strftime('%Y-%m-%d')
    
    active_count = 0
    expired_count = 0
    
    if 'effective_period' in df.columns:
        for period in df['effective_period']:
            status = get_period_status(period, today_str)
            if status == 'active':
                active_count += 1
            elif status == 'expired':
                expired_count += 1
    
    return {
        'total_assignments': len(df),
        'unique_customers': df['customer'].nunique() if 'customer' in df.columns else 0,
        'unique_products': df['product_pn'].nunique() if 'product_pn' in df.columns else 0,
        'unique_salespeople': df['sales_name'].nunique() if 'sales_name' in df.columns else 0,
        'active_count': active_count,
        'expired_count': expired_count,
    }
