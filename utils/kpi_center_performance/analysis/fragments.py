# utils/kpi_center_performance/analysis/fragments.py
"""
Streamlit Fragments for KPI Center Performance - Analysis Tab.

Contains:
- top_performers_fragment: Top performers / Pareto analysis
"""

import logging
from typing import Dict, Optional
import pandas as pd
import streamlit as st

from ..charts import KPICenterCharts

logger = logging.getLogger(__name__)


# =============================================================================
# TOP PERFORMERS FRAGMENT - kept from v2.3.0
# =============================================================================

@st.fragment
def top_performers_fragment(
    sales_df: pd.DataFrame,
    filter_values: Dict = None,
    metrics_calculator = None,
    fragment_key: str = "kpc_top"
):
    """Top performers / Pareto analysis."""
    if sales_df.empty:
        st.info("No data for analysis")
        return
    
    st.subheader("🏆 Top Performers Analysis")
    
    # Controls
    col1, col2, col3 = st.columns(3)
    
    with col1:
        group_by = st.selectbox(
            "Analyze by",
            ["Customer", "Brand", "Product"],
            key=f"{fragment_key}_group"
        )
    
    with col2:
        metric = st.selectbox(
            "Metric",
            ["Revenue", "Gross Profit", "GP1"],
            key=f"{fragment_key}_metric"
        )
    
    with col3:
        top_percent = st.slider(
            "Show top %",
            min_value=50,
            max_value=100,
            value=80,
            step=5,
            key=f"{fragment_key}_pct"
        )
    
    # Map selections
    group_col_map = {
        "Customer": "customer",
        "Brand": "brand",
        "Product": "product_pn"
    }
    group_col = group_col_map.get(group_by, "customer")
    
    metric_col_map = {
        "Revenue": "sales_by_kpi_center_usd",
        "Gross Profit": "gross_profit_by_kpi_center_usd",
        "GP1": "gp1_by_kpi_center_usd"
    }
    value_col = metric_col_map.get(metric, "sales_by_kpi_center_usd")
    
    # Aggregate
    agg_df = sales_df.groupby(group_col).agg({
        'sales_by_kpi_center_usd': 'sum',
        'gross_profit_by_kpi_center_usd': 'sum',
        'gp1_by_kpi_center_usd': 'sum' if 'gp1_by_kpi_center_usd' in sales_df.columns else 'first',
        'inv_number': pd.Series.nunique
    }).reset_index()
    
    agg_df.columns = [group_col, 'revenue', 'gross_profit', 'gp1', 'orders']
    
    # Sort and calculate cumulative
    metric_lower = metric.lower().replace(' ', '_')
    agg_df = agg_df.sort_values(metric_lower, ascending=False)
    
    total = agg_df[metric_lower].sum()
    if total == 0:
        st.warning("No data to analyze")
        return
    
    agg_df['cumulative'] = agg_df[metric_lower].cumsum()
    agg_df['cumulative_percent'] = (agg_df['cumulative'] / total * 100).round(1)
    agg_df['percent'] = (agg_df[metric_lower] / total * 100).round(1)
    
    # Filter to top percent
    top_data = agg_df[agg_df['cumulative_percent'] <= top_percent].copy()
    if top_data.empty:
        top_data = agg_df.head(1).copy()
    
    # Summary metrics
    st.divider()
    
    col_s1, col_s2, col_s3, col_s4 = st.columns(4)
    
    top_count = len(top_data)
    total_count = len(agg_df)
    top_value = top_data[metric_lower].sum()
    concentration = (top_count / total_count * 100) if total_count > 0 else 0
    
    with col_s1:
        st.metric(f"Top {group_by}s", f"{top_count:,}", f"of {total_count:,} total")
    
    with col_s2:
        st.metric(f"Top {top_percent}% {metric}", f"${top_value:,.0f}",
                 f"{(top_value/total*100):.1f}% of total")
    
    with col_s3:
        st.metric("Concentration", f"{concentration:.1f}%")
    
    with col_s4:
        avg_per = top_value / top_count if top_count > 0 else 0
        st.metric(f"Avg per {group_by}", f"${avg_per:,.0f}")
    
    # Chart and table
    chart_col, table_col = st.columns([1.2, 1])
    
    with chart_col:
        chart = KPICenterCharts.build_top_performers_chart(
            data_df=top_data,
            value_col=metric_lower,
            label_col=group_col,
            top_n=min(15, len(top_data)),
            title=f"Top {group_by}s by {metric}"
        )
        st.altair_chart(chart, use_container_width=True)
    
    with table_col:
        display_df = top_data[[group_col, 'revenue', 'gross_profit', 'gp1', 'orders', 'percent', 'cumulative_percent']].copy()
        display_df.insert(0, 'Rank', range(1, len(display_df) + 1))
        
        st.dataframe(
            display_df.head(20),
            hide_index=True,
            column_config={
                'Rank': st.column_config.NumberColumn('🏆', width='small'),
                group_col: group_by,
                'revenue': st.column_config.NumberColumn('Revenue', format='$%,.0f'),
                'gross_profit': st.column_config.NumberColumn('GP', format='$%,.0f'),
                'gp1': st.column_config.NumberColumn('GP1', format='$%,.0f'),
                'orders': 'Orders',
                'percent': st.column_config.NumberColumn('% Share', format='%.1f%%'),
                'cumulative_percent': st.column_config.NumberColumn('Cum %', format='%.1f%%'),
            },
            use_container_width=True
        )
