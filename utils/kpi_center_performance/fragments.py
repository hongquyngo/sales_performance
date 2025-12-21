# utils/kpi_center_performance/fragments.py
"""
Fragment Components for KPI Center Performance

Uses @st.fragment decorator for partial reruns without full page refresh.
Each fragment manages its own state and interactions.

Fragments:
- monthly_trend_fragment: Monthly trend charts with drill-down
- yoy_comparison_fragment: Year-over-Year comparison
- sales_detail_fragment: Transaction list with filters
- pivot_analysis_fragment: Pivot table configuration
- backlog_list_fragment: Backlog detail with filters
- export_report_fragment: Two-step export (Generate → Download)
- kpi_center_ranking_fragment: KPI Center ranking table

VERSION: 1.0.0
"""

import logging
from datetime import date
from typing import Dict, List, Optional
import pandas as pd
import streamlit as st

from .constants import COLORS, MONTH_ORDER
from .charts import KPICenterCharts

logger = logging.getLogger(__name__)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _clean_dataframe_for_display(df: pd.DataFrame) -> pd.DataFrame:
    """
    Clean DataFrame for Streamlit display to avoid Arrow serialization errors.
    Converts mixed-type columns to strings.
    """
    if df.empty:
        return df
    
    df = df.copy()
    
    for col in df.columns:
        # Check for mixed types
        try:
            types = df[col].apply(type).unique()
            if len(types) > 1:
                df[col] = df[col].astype(str)
        except:
            df[col] = df[col].astype(str)
    
    return df


def _format_currency(value) -> str:
    """Format value as currency."""
    try:
        return f"${value:,.0f}"
    except:
        return str(value)


def _format_percent(value) -> str:
    """Format value as percentage."""
    try:
        return f"{value:.1f}%"
    except:
        return str(value)


# =============================================================================
# MONTHLY TREND FRAGMENT
# =============================================================================

@st.fragment
def monthly_trend_fragment(
    sales_df: pd.DataFrame,
    filter_values: Dict,
    show_cumulative: bool = True
):
    """
    Monthly trend charts with optional drill-down filters.
    
    Args:
        sales_df: Sales data with invoice_month column
        filter_values: Current filter values
        show_cumulative: Whether to show cumulative chart
    """
    if sales_df.empty:
        st.info("No sales data for trend analysis")
        return
    
    # Local filters for drill-down
    col1, col2, col3 = st.columns(3)
    
    with col1:
        # Customer filter
        customers = ['All'] + sorted(sales_df['customer'].dropna().unique().tolist())
        selected_customer = st.selectbox(
            "Customer",
            customers,
            key="trend_customer_filter"
        )
    
    with col2:
        # Brand filter
        brands = ['All'] + sorted(sales_df['brand'].dropna().unique().tolist())
        selected_brand = st.selectbox(
            "Brand",
            brands,
            key="trend_brand_filter"
        )
    
    with col3:
        # Metric selector
        metric = st.selectbox(
            "Metric",
            ["Revenue", "Gross Profit", "GP1"],
            key="trend_metric_selector"
        )
    
    # Apply local filters
    filtered_df = sales_df.copy()
    
    if selected_customer != 'All':
        filtered_df = filtered_df[filtered_df['customer'] == selected_customer]
    
    if selected_brand != 'All':
        filtered_df = filtered_df[filtered_df['brand'] == selected_brand]
    
    if filtered_df.empty:
        st.warning("No data matches the selected filters")
        return
    
    # Prepare monthly data
    if 'invoice_month' not in filtered_df.columns:
        if 'inv_date' in filtered_df.columns:
            filtered_df['inv_date'] = pd.to_datetime(filtered_df['inv_date'], errors='coerce')
            filtered_df['invoice_month'] = filtered_df['inv_date'].dt.strftime('%b')
        else:
            st.warning("Cannot determine month from data")
            return
    
    # Group by month
    monthly = filtered_df.groupby('invoice_month').agg({
        'sales_by_kpi_center_usd': 'sum',
        'gross_profit_by_kpi_center_usd': 'sum',
        'gp1_by_kpi_center_usd': 'sum' if 'gp1_by_kpi_center_usd' in filtered_df.columns else 'count',
        'customer_id': pd.Series.nunique
    }).reset_index()
    
    monthly.columns = ['invoice_month', 'revenue', 'gross_profit', 'gp1', 'customer_count']
    
    if 'gp1_by_kpi_center_usd' not in filtered_df.columns:
        monthly['gp1'] = 0
    
    # Calculate GP%
    monthly['gp_percent'] = (monthly['gross_profit'] / monthly['revenue'] * 100).round(2)
    
    # Ensure all months
    all_months = pd.DataFrame({'invoice_month': MONTH_ORDER})
    monthly = all_months.merge(monthly, on='invoice_month', how='left').fillna(0)
    
    # Add month order
    monthly['month_order'] = monthly['invoice_month'].apply(
        lambda x: MONTH_ORDER.index(x) if x in MONTH_ORDER else 12
    )
    monthly = monthly.sort_values('month_order')
    
    # Calculate cumulative
    monthly['cumulative_revenue'] = monthly['revenue'].cumsum()
    monthly['cumulative_gp'] = monthly['gross_profit'].cumsum()
    monthly['cumulative_gp1'] = monthly['gp1'].cumsum()
    
    # Display charts
    col_chart1, col_chart2 = st.columns(2)
    
    with col_chart1:
        chart = KPICenterCharts.build_monthly_trend_chart(
            monthly,
            title=f"Monthly {metric}"
        )
        st.altair_chart(chart, use_container_width=True)
    
    with col_chart2:
        if show_cumulative:
            cum_chart = KPICenterCharts.build_cumulative_chart(
                monthly,
                title="Cumulative Performance"
            )
            st.altair_chart(cum_chart, use_container_width=True)
    
    # Summary table
    with st.expander("📊 Monthly Data Table"):
        display_df = monthly[['invoice_month', 'revenue', 'gross_profit', 'gp1', 'gp_percent', 'customer_count']].copy()
        display_df.columns = ['Month', 'Revenue', 'GP', 'GP1', 'GP%', 'Customers']
        
        st.dataframe(
            display_df,
            hide_index=True,
            column_config={
                'Revenue': st.column_config.NumberColumn(format="$%,.0f"),
                'GP': st.column_config.NumberColumn(format="$%,.0f"),
                'GP1': st.column_config.NumberColumn(format="$%,.0f"),
                'GP%': st.column_config.NumberColumn(format="%.1f%%"),
            }
        )


# =============================================================================
# YOY COMPARISON FRAGMENT
# =============================================================================

@st.fragment
def yoy_comparison_fragment(
    queries,
    filter_values: Dict,
    current_year: int
):
    """
    Year-over-Year comparison with multi-year support.
    
    Args:
        queries: KPICenterQueries instance
        filter_values: Current filter values
        current_year: Current year from filters
    """
    # Year selection
    col1, col2 = st.columns([1, 3])
    
    with col1:
        compare_year = st.number_input(
            "Compare with Year",
            min_value=2014,
            max_value=current_year - 1,
            value=current_year - 1,
            key="yoy_compare_year"
        )
    
    # Load comparison data
    start_date = filter_values['start_date']
    end_date = filter_values['end_date']
    kpi_center_ids = filter_values.get('kpi_center_ids', [])
    entity_ids = filter_values.get('entity_ids', [])
    
    # Get current year data
    current_sales = queries.get_sales_data(
        start_date=start_date,
        end_date=end_date,
        kpi_center_ids=kpi_center_ids,
        entity_ids=entity_ids if entity_ids else None
    )
    
    # Get comparison year data (same period, different year)
    compare_start = date(compare_year, start_date.month, start_date.day)
    compare_end = date(compare_year, end_date.month, min(end_date.day, 28))  # Safe for Feb
    
    compare_sales = queries.get_sales_data(
        start_date=compare_start,
        end_date=compare_end,
        kpi_center_ids=kpi_center_ids,
        entity_ids=entity_ids if entity_ids else None
    )
    
    # Exclude internal if filter set
    if filter_values.get('exclude_internal_revenue', True):
        if not current_sales.empty and 'customer_type' in current_sales.columns:
            current_sales = current_sales[current_sales['customer_type'] != 'Internal']
        if not compare_sales.empty and 'customer_type' in compare_sales.columns:
            compare_sales = compare_sales[compare_sales['customer_type'] != 'Internal']
    
    # Metric selector
    with col2:
        metric = st.radio(
            "Metric",
            ["Revenue", "Gross Profit", "GP1"],
            horizontal=True,
            key="yoy_metric"
        )
    
    metric_map = {
        "Revenue": "revenue",
        "Gross Profit": "gross_profit",
        "GP1": "gp1"
    }
    
    # Build chart
    chart = KPICenterCharts.build_yoy_comparison_chart(
        current_df=current_sales,
        previous_df=compare_sales,
        metric=metric_map[metric],
        current_label=str(current_year),
        previous_label=str(compare_year)
    )
    
    st.altair_chart(chart, use_container_width=True)
    
    # Summary comparison
    col_curr, col_prev, col_change = st.columns(3)
    
    col_map = {
        "Revenue": "sales_by_kpi_center_usd",
        "Gross Profit": "gross_profit_by_kpi_center_usd",
        "GP1": "gp1_by_kpi_center_usd"
    }
    col_name = col_map[metric]
    
    current_total = current_sales[col_name].sum() if not current_sales.empty and col_name in current_sales.columns else 0
    compare_total = compare_sales[col_name].sum() if not compare_sales.empty and col_name in compare_sales.columns else 0
    
    with col_curr:
        st.metric(
            label=f"{current_year} {metric}",
            value=_format_currency(current_total)
        )
    
    with col_prev:
        st.metric(
            label=f"{compare_year} {metric}",
            value=_format_currency(compare_total)
        )
    
    with col_change:
        if compare_total > 0:
            change_pct = ((current_total - compare_total) / compare_total) * 100
            st.metric(
                label="YoY Change",
                value=f"{change_pct:+.1f}%",
                delta=_format_currency(current_total - compare_total)
            )
        else:
            st.metric(
                label="YoY Change",
                value="N/A",
                delta="No previous data"
            )


# =============================================================================
# SALES DETAIL FRAGMENT
# =============================================================================

@st.fragment
def sales_detail_fragment(
    sales_df: pd.DataFrame,
    filter_values: Dict
):
    """
    Sales detail list with filters and export.
    
    Args:
        sales_df: Sales data
        filter_values: Current filter values
    """
    if sales_df.empty:
        st.info("No sales data available")
        return
    
    st.subheader("📋 Sales Transactions")
    
    # Local filters
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        search = st.text_input(
            "Search",
            placeholder="Customer, Product, Invoice...",
            key="detail_search"
        )
    
    with col2:
        kpi_centers = ['All'] + sorted(sales_df['kpi_center'].dropna().unique().tolist())
        selected_kc = st.selectbox(
            "KPI Center",
            kpi_centers,
            key="detail_kpi_center"
        )
    
    with col3:
        brands = ['All'] + sorted(sales_df['brand'].dropna().unique().tolist())
        selected_brand = st.selectbox(
            "Brand",
            brands,
            key="detail_brand"
        )
    
    with col4:
        min_revenue = st.number_input(
            "Min Revenue",
            min_value=0,
            value=0,
            step=1000,
            key="detail_min_revenue"
        )
    
    # Apply filters
    filtered_df = sales_df.copy()
    
    if search:
        search_lower = search.lower()
        mask = (
            filtered_df['customer'].fillna('').str.lower().str.contains(search_lower) |
            filtered_df['product_pn'].fillna('').str.lower().str.contains(search_lower) |
            filtered_df['inv_number'].fillna('').astype(str).str.lower().str.contains(search_lower)
        )
        filtered_df = filtered_df[mask]
    
    if selected_kc != 'All':
        filtered_df = filtered_df[filtered_df['kpi_center'] == selected_kc]
    
    if selected_brand != 'All':
        filtered_df = filtered_df[filtered_df['brand'] == selected_brand]
    
    if min_revenue > 0:
        filtered_df = filtered_df[filtered_df['sales_by_kpi_center_usd'] >= min_revenue]
    
    # Stats
    st.caption(f"Showing {len(filtered_df):,} of {len(sales_df):,} transactions")
    
    if filtered_df.empty:
        st.warning("No transactions match the filters")
        return
    
    # Select columns for display
    display_cols = [
        'inv_date', 'inv_number', 'kpi_center', 'customer', 
        'product_pn', 'brand', 'sales_by_kpi_center_usd', 
        'gross_profit_by_kpi_center_usd', 'split_rate_percent'
    ]
    display_cols = [c for c in display_cols if c in filtered_df.columns]
    
    display_df = filtered_df[display_cols].head(500).copy()
    display_df = _clean_dataframe_for_display(display_df)
    
    # Column config
    column_config = {
        'inv_date': st.column_config.DateColumn('Date'),
        'inv_number': 'Invoice #',
        'kpi_center': 'KPI Center',
        'customer': 'Customer',
        'product_pn': 'Product',
        'brand': 'Brand',
        'sales_by_kpi_center_usd': st.column_config.NumberColumn('Revenue', format="$%,.0f"),
        'gross_profit_by_kpi_center_usd': st.column_config.NumberColumn('GP', format="$%,.0f"),
        'split_rate_percent': st.column_config.NumberColumn('Split %', format="%.0f%%"),
    }
    
    st.dataframe(
        display_df,
        hide_index=True,
        column_config=column_config,
        use_container_width=True
    )
    
    if len(filtered_df) > 500:
        st.caption("⚠️ Showing first 500 rows. Export for complete data.")


# =============================================================================
# PIVOT ANALYSIS FRAGMENT
# =============================================================================

@st.fragment
def pivot_analysis_fragment(
    sales_df: pd.DataFrame
):
    """
    Interactive pivot table configuration.
    """
    if sales_df.empty:
        st.info("No data for pivot analysis")
        return
    
    st.subheader("📊 Pivot Analysis")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        row_options = ['kpi_center', 'customer', 'brand', 'product_pn', 'invoice_month']
        row_options = [c for c in row_options if c in sales_df.columns]
        
        rows = st.selectbox(
            "Rows",
            row_options,
            key="pivot_rows"
        )
    
    with col2:
        col_options = ['None'] + [c for c in row_options if c != rows]
        columns = st.selectbox(
            "Columns",
            col_options,
            key="pivot_columns"
        )
    
    with col3:
        values = st.selectbox(
            "Values",
            ["Revenue", "Gross Profit", "GP1", "Count"],
            key="pivot_values"
        )
    
    # Build pivot
    value_map = {
        "Revenue": 'sales_by_kpi_center_usd',
        "Gross Profit": 'gross_profit_by_kpi_center_usd',
        "GP1": 'gp1_by_kpi_center_usd',
        "Count": 'inv_number'
    }
    
    value_col = value_map[values]
    aggfunc = 'sum' if values != 'Count' else 'nunique'
    
    if value_col not in sales_df.columns:
        st.warning(f"Column {value_col} not available")
        return
    
    if columns == 'None':
        pivot = sales_df.groupby(rows)[value_col].agg(aggfunc).reset_index()
        pivot.columns = [rows, values]
        pivot = pivot.sort_values(values, ascending=False)
    else:
        pivot = pd.pivot_table(
            sales_df,
            values=value_col,
            index=rows,
            columns=columns,
            aggfunc=aggfunc,
            fill_value=0
        ).reset_index()
    
    # Display
    st.dataframe(
        _clean_dataframe_for_display(pivot.head(100)),
        hide_index=True,
        use_container_width=True
    )


# =============================================================================
# BACKLOG LIST FRAGMENT
# =============================================================================

@st.fragment
def backlog_list_fragment(
    backlog_df: pd.DataFrame,
    filter_values: Dict
):
    """
    Backlog detail list with filters.
    """
    if backlog_df.empty:
        st.info("No backlog data available")
        return
    
    st.subheader("📦 Backlog Detail")
    
    # Local filters
    col1, col2, col3 = st.columns(3)
    
    with col1:
        search = st.text_input(
            "Search",
            placeholder="Customer, Product, OC#...",
            key="backlog_search"
        )
    
    with col2:
        kpi_centers = ['All'] + sorted(backlog_df['kpi_center'].dropna().unique().tolist())
        selected_kc = st.selectbox(
            "KPI Center",
            kpi_centers,
            key="backlog_kpi_center"
        )
    
    with col3:
        status_options = ['All']
        if 'pending_type' in backlog_df.columns:
            status_options += backlog_df['pending_type'].dropna().unique().tolist()
        selected_status = st.selectbox(
            "Status",
            status_options,
            key="backlog_status"
        )
    
    # Apply filters
    filtered_df = backlog_df.copy()
    
    if search:
        search_lower = search.lower()
        mask = pd.Series([False] * len(filtered_df), index=filtered_df.index)
        for col in ['customer', 'product_pn', 'oc_number']:
            if col in filtered_df.columns:
                mask |= filtered_df[col].fillna('').astype(str).str.lower().str.contains(search_lower)
        filtered_df = filtered_df[mask]
    
    if selected_kc != 'All':
        filtered_df = filtered_df[filtered_df['kpi_center'] == selected_kc]
    
    if selected_status != 'All' and 'pending_type' in filtered_df.columns:
        filtered_df = filtered_df[filtered_df['pending_type'] == selected_status]
    
    # Stats
    total_backlog = filtered_df['backlog_by_kpi_center_usd'].sum() if 'backlog_by_kpi_center_usd' in filtered_df.columns else 0
    st.caption(f"Showing {len(filtered_df):,} items • Total: ${total_backlog:,.0f}")
    
    if filtered_df.empty:
        st.warning("No backlog matches the filters")
        return
    
    # Select columns
    display_cols = [
        'oc_number', 'etd', 'customer', 'product_pn', 'kpi_center',
        'backlog_by_kpi_center_usd', 'backlog_gp_by_kpi_center_usd',
        'days_until_etd', 'pending_type'
    ]
    display_cols = [c for c in display_cols if c in filtered_df.columns]
    
    display_df = filtered_df[display_cols].head(500).copy()
    display_df = _clean_dataframe_for_display(display_df)
    
    column_config = {
        'oc_number': 'OC #',
        'etd': st.column_config.DateColumn('ETD'),
        'customer': 'Customer',
        'product_pn': 'Product',
        'kpi_center': 'KPI Center',
        'backlog_by_kpi_center_usd': st.column_config.NumberColumn('Amount', format="$%,.0f"),
        'backlog_gp_by_kpi_center_usd': st.column_config.NumberColumn('GP', format="$%,.0f"),
        'days_until_etd': 'Days to ETD',
        'pending_type': 'Status',
    }
    
    st.dataframe(
        display_df,
        hide_index=True,
        column_config=column_config,
        use_container_width=True
    )


# =============================================================================
# KPI CENTER RANKING FRAGMENT
# =============================================================================

@st.fragment
def kpi_center_ranking_fragment(
    ranking_df: pd.DataFrame,
    show_targets: bool = True
):
    """
    KPI Center ranking table with chart.
    """
    if ranking_df.empty:
        st.info("No ranking data available")
        return
    
    # Metric selector
    metric = st.radio(
        "Rank by",
        ["Revenue", "Gross Profit", "GP1", "Customers"],
        horizontal=True,
        key="ranking_metric"
    )
    
    metric_col_map = {
        "Revenue": "revenue",
        "Gross Profit": "gross_profit",
        "GP1": "gp1",
        "Customers": "customers"
    }
    
    sort_col = metric_col_map[metric]
    if sort_col not in ranking_df.columns:
        st.warning(f"Column {sort_col} not available")
        return
    
    sorted_df = ranking_df.sort_values(sort_col, ascending=False).copy()
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        # Chart
        chart = KPICenterCharts.build_kpi_center_ranking_chart(
            sorted_df,
            metric=sort_col,
            top_n=10
        )
        st.altair_chart(chart, use_container_width=True)
    
    with col2:
        # Table
        display_cols = ['kpi_center', 'revenue', 'gross_profit', 'customers']
        if show_targets and 'revenue_achievement' in sorted_df.columns:
            display_cols.append('revenue_achievement')
        
        display_cols = [c for c in display_cols if c in sorted_df.columns]
        display_df = sorted_df[display_cols].head(15).copy()
        
        column_config = {
            'kpi_center': 'KPI Center',
            'revenue': st.column_config.NumberColumn('Revenue', format="$%,.0f"),
            'gross_profit': st.column_config.NumberColumn('GP', format="$%,.0f"),
            'customers': 'Customers',
            'revenue_achievement': st.column_config.NumberColumn('Achievement', format="%.0f%%"),
        }
        
        st.dataframe(
            display_df,
            hide_index=True,
            column_config=column_config,
            use_container_width=True
        )


# =============================================================================
# EXPORT REPORT FRAGMENT
# =============================================================================

@st.fragment
def export_report_fragment(
    metrics: Dict,
    complex_kpis: Dict,
    pipeline_metrics: Dict,
    filter_values: Dict,
    yoy_metrics: Dict = None,
    kpi_center_summary_df: pd.DataFrame = None,
    monthly_df: pd.DataFrame = None,
    sales_detail_df: pd.DataFrame = None,
    backlog_summary_df: pd.DataFrame = None,
    backlog_detail_df: pd.DataFrame = None,
    backlog_by_month_df: pd.DataFrame = None
):
    """
    Two-step export: Generate → Download.
    Uses fragment to avoid full page reload.
    """
    from .export import KPICenterExport
    
    st.subheader("📥 Export Report")
    
    # Generate button
    if st.button("🔄 Generate Excel Report", key="generate_report_btn"):
        with st.spinner("Generating report..."):
            try:
                exporter = KPICenterExport()
                excel_bytes = exporter.create_comprehensive_report(
                    metrics=metrics,
                    complex_kpis=complex_kpis,
                    pipeline_metrics=pipeline_metrics,
                    filters=filter_values,
                    yoy_metrics=yoy_metrics,
                    kpi_center_summary_df=kpi_center_summary_df,
                    monthly_df=monthly_df,
                    sales_detail_df=sales_detail_df,
                    backlog_summary_df=backlog_summary_df,
                    backlog_detail_df=backlog_detail_df,
                    backlog_by_month_df=backlog_by_month_df,
                )
                
                st.session_state['kpi_center_export_data'] = excel_bytes
                st.success("✅ Report generated! Click download below.")
                
            except Exception as e:
                logger.error(f"Export error: {e}")
                st.error(f"Failed to generate report: {e}")
    
    # Download button (only if report generated)
    if 'kpi_center_export_data' in st.session_state:
        year = filter_values.get('year', 2025)
        period = filter_values.get('period_type', 'YTD')
        filename = f"kpi_center_performance_{year}_{period}.xlsx"
        
        st.download_button(
            label="⬇️ Download Excel Report",
            data=st.session_state['kpi_center_export_data'],
            file_name=filename,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="download_report_btn"
        )
