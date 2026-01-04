# utils/kpi_center_performance/analysis/fragments.py
"""
Streamlit Fragments for KPI Center Performance - Analysis Tab.

VERSION: 5.0.0
AUTHOR: Refactored for clean integration

USAGE IN MAIN PAGE:
    from utils.kpi_center_performance import analysis_tab_fragment
    
    with tab3:
        analysis_tab_fragment(
            sales_df=sales_df,
            prev_sales_df=prev_sales_df,
            filter_values=active_filters,
            metrics_calculator=metrics_calc
        )

Contains:
- analysis_tab_fragment: Main entry point (wrapper for all analysis)
- _top_performers_section: Top performers analysis
- _concentration_section: Pareto/concentration analysis  
- _mix_analysis_section: Brand and product breakdown
- _growth_analysis_section: YoY growth comparison
"""

import logging
from typing import Dict, Optional
import pandas as pd
import streamlit as st

from .charts import (
    build_top_performers_chart,
    build_pareto_chart,
    build_mix_pie_chart,
    build_growth_comparison_chart,
)

logger = logging.getLogger(__name__)


# =============================================================================
# MAIN ENTRY POINT - Called from main page
# =============================================================================

@st.fragment
def analysis_tab_fragment(
    sales_df: pd.DataFrame,
    prev_sales_df: pd.DataFrame = None,
    filter_values: Dict = None,
    metrics_calculator = None,
    fragment_key: str = "analysis"
):
    """
    Main Analysis Tab Fragment.
    
    This is the single entry point for Tab 3: Analysis.
    All analysis logic is encapsulated here.
    
    Args:
        sales_df: Current period sales data
        prev_sales_df: Previous period sales data (for YoY)
        filter_values: Active filters from sidebar
        metrics_calculator: KPICenterMetrics instance
        fragment_key: Unique key prefix for widgets
    """
    if sales_df.empty:
        st.info("📊 No data available for analysis. Please adjust your filters.")
        return
    
    # Header with help
    _render_header()
    
    # Sub-tabs for different analyses
    tab1, tab2, tab3, tab4 = st.tabs([
        "🏆 Top Performers",
        "📊 Concentration", 
        "🎨 Mix Analysis",
        "📈 Growth (YoY)"
    ])
    
    with tab1:
        _top_performers_section(
            sales_df=sales_df,
            filter_values=filter_values,
            metrics_calculator=metrics_calculator,
            key_prefix=f"{fragment_key}_top"
        )
    
    with tab2:
        _concentration_section(
            sales_df=sales_df,
            filter_values=filter_values,
            key_prefix=f"{fragment_key}_conc"
        )
    
    with tab3:
        _mix_analysis_section(
            sales_df=sales_df,
            filter_values=filter_values,
            key_prefix=f"{fragment_key}_mix"
        )
    
    with tab4:
        _growth_analysis_section(
            sales_df=sales_df,
            prev_sales_df=prev_sales_df,
            filter_values=filter_values,
            key_prefix=f"{fragment_key}_growth"
        )


def _render_header():
    """Render analysis tab header with help popover."""
    col_header, col_help = st.columns([6, 1])
    
    with col_header:
        st.subheader("📈 Performance Analysis")
    
    with col_help:
        with st.popover("ℹ️ Help"):
            st.markdown("""
**📈 Analysis Tools**

| Analysis | Description |
|----------|-------------|
| **Top Performers** | Rank by revenue, GP, or GP1 |
| **Concentration** | Pareto - who drives 80% |
| **Mix Analysis** | Brand & Product breakdown |
| **Growth (YoY)** | Compare vs previous year |

**Key Metrics:**
- **CR10**: % revenue from top 10%
- **HHI**: Concentration index (0-10000)
- **GP Margin**: Gross profit / Revenue
            """)


# =============================================================================
# SECTION 1: TOP PERFORMERS
# =============================================================================

def _top_performers_section(
    sales_df: pd.DataFrame,
    filter_values: Dict = None,
    metrics_calculator = None,
    key_prefix: str = "top"
):
    """Top performers / Pareto analysis section."""
    
    st.markdown("#### 🏆 Top Performers Analysis")
    
    # Controls
    col1, col2, col3, col4 = st.columns([2, 2, 2, 1])
    
    with col1:
        group_by = st.selectbox(
            "Analyze by",
            ["Customer", "Brand", "Product"],
            key=f"{key_prefix}_group"
        )
    
    with col2:
        metric = st.selectbox(
            "Metric",
            ["Revenue", "Gross Profit", "GP1"],
            key=f"{key_prefix}_metric"
        )
    
    with col3:
        top_percent = st.slider(
            "Show top %",
            min_value=50, max_value=100, value=80, step=5,
            key=f"{key_prefix}_pct"
        )
    
    with col4:
        show_margin = st.checkbox("GP %", value=True, key=f"{key_prefix}_margin")
    
    # Map selections to columns
    group_col = {"Customer": "customer", "Brand": "brand", "Product": "product_pn"}.get(group_by, "customer")
    metric_col = {"Revenue": "revenue", "Gross Profit": "gross_profit", "GP1": "gp1"}.get(metric, "revenue")
    
    # Aggregate data
    agg_df = _aggregate_sales_data(sales_df, group_col)
    
    if agg_df.empty or agg_df[metric_col].sum() == 0:
        st.warning("No data to analyze")
        return
    
    # Sort and calculate cumulative
    agg_df = agg_df.sort_values(metric_col, ascending=False)
    total = agg_df[metric_col].sum()
    agg_df['cumulative'] = agg_df[metric_col].cumsum()
    agg_df['cumulative_percent'] = (agg_df['cumulative'] / total * 100).round(1)
    agg_df['percent'] = (agg_df[metric_col] / total * 100).round(1)
    
    # Filter to top percent
    top_data = agg_df[agg_df['cumulative_percent'] <= top_percent].copy()
    if top_data.empty:
        top_data = agg_df.head(1).copy()
    
    # Summary metrics
    _render_top_performers_metrics(top_data, agg_df, group_by, metric, metric_col, top_percent)
    
    # Chart and table
    _render_top_performers_content(top_data, group_col, group_by, metric, metric_col, show_margin)
    
    # Insights
    _render_top_performers_insights(top_data, agg_df, group_by, metric, metric_col)


def _aggregate_sales_data(sales_df: pd.DataFrame, group_col: str) -> pd.DataFrame:
    """Aggregate sales data by group column."""
    agg_dict = {
        'sales_by_kpi_center_usd': 'sum',
        'gross_profit_by_kpi_center_usd': 'sum',
        'inv_number': pd.Series.nunique
    }
    
    if 'gp1_by_kpi_center_usd' in sales_df.columns:
        agg_dict['gp1_by_kpi_center_usd'] = 'sum'
    
    agg_df = sales_df.groupby(group_col).agg(agg_dict).reset_index()
    
    # Rename columns
    agg_df = agg_df.rename(columns={
        'sales_by_kpi_center_usd': 'revenue',
        'gross_profit_by_kpi_center_usd': 'gross_profit',
        'gp1_by_kpi_center_usd': 'gp1',
        'inv_number': 'orders'
    })
    
    # Ensure gp1 exists
    if 'gp1' not in agg_df.columns:
        agg_df['gp1'] = 0
    
    # Calculate GP Margin
    agg_df['gp_margin'] = (agg_df['gross_profit'] / agg_df['revenue'] * 100).fillna(0).round(1)
    
    return agg_df


def _render_top_performers_metrics(top_data, agg_df, group_by, metric, metric_col, top_percent):
    """Render summary metrics for top performers."""
    st.divider()
    
    col1, col2, col3, col4 = st.columns(4)
    
    top_count = len(top_data)
    total_count = len(agg_df)
    top_value = top_data[metric_col].sum()
    total_value = agg_df[metric_col].sum()
    concentration = (top_count / total_count * 100) if total_count > 0 else 0
    
    with col1:
        st.metric(f"Top {group_by}s", f"{top_count:,}", f"of {total_count:,} total")
    
    with col2:
        st.metric(
            f"Top {top_percent}% {metric}",
            f"${top_value:,.0f}",
            f"{(top_value/total_value*100):.1f}% of total"
        )
    
    with col3:
        st.metric("Concentration", f"{concentration:.1f}%")
    
    with col4:
        avg_per = top_value / top_count if top_count > 0 else 0
        st.metric(f"Avg per {group_by}", f"${avg_per:,.0f}")


def _render_top_performers_content(top_data, group_col, group_by, metric, metric_col, show_margin):
    """Render chart and table for top performers."""
    chart_col, table_col = st.columns([1.2, 1])
    
    with chart_col:
        chart = build_top_performers_chart(
            data_df=top_data,
            value_col=metric_col,
            label_col=group_col,
            top_n=min(15, len(top_data)),
            title=f"Top {group_by}s by {metric}"
        )
        st.altair_chart(chart, use_container_width=True)
    
    with table_col:
        # Build display DataFrame with formatted values
        display_df = pd.DataFrame()
        display_df['Rank'] = range(1, len(top_data) + 1)
        display_df[group_by] = top_data[group_col].values
        
        # Format currency columns - handle NaN/inf
        display_df['Revenue'] = top_data['revenue'].fillna(0).apply(lambda x: f"${x:,.0f}")
        display_df['GP'] = top_data['gross_profit'].fillna(0).apply(lambda x: f"${x:,.0f}")
        
        if show_margin:
            display_df['GP %'] = top_data['gp_margin'].fillna(0).apply(lambda x: f"{x:.1f}%")
        
        display_df['GP1'] = top_data['gp1'].fillna(0).apply(lambda x: f"${x:,.0f}")
        display_df['Orders'] = top_data['orders'].fillna(0).astype(int)
        display_df['% Share'] = top_data['percent'].fillna(0).apply(lambda x: f"{x:.1f}%")
        display_df['Cum %'] = top_data['cumulative_percent'].fillna(0).apply(lambda x: f"{x:.1f}%")
        
        st.dataframe(
            display_df.head(20),
            hide_index=True,
            use_container_width=True,
            height=min(400, len(display_df) * 35 + 50)
        )


def _render_top_performers_insights(top_data, agg_df, group_by, metric, metric_col):
    """Render insights expander for top performers."""
    with st.expander("💡 Key Insights", expanded=False):
        if top_data.empty:
            st.info("No data for insights")
            return
        
        top_1 = top_data.iloc[0]
        group_col = top_data.columns[0]
        top_count = len(top_data)
        total_count = len(agg_df)
        concentration = (top_count / total_count * 100) if total_count > 0 else 0
        
        col1, col2 = st.columns(2)
        
        with col1:
            percent_val = top_1['percent'] if pd.notna(top_1['percent']) else 0
            total_percent = top_data['percent'].sum() if 'percent' in top_data.columns else 0
            st.markdown(f"""
**📊 Concentration:**
- Top 1: **{top_1[group_col]}** = {percent_val:.1f}% of {metric}
- Top {top_count} ({concentration:.1f}% of base) = {total_percent:.1f}% of {metric}
            """)
        
        with col2:
            avg_margin = top_data['gp_margin'].mean() if 'gp_margin' in top_data.columns else 0
            avg_margin = avg_margin if pd.notna(avg_margin) else 0
            high_margin = top_data[top_data['gp_margin'] > avg_margin] if 'gp_margin' in top_data.columns else pd.DataFrame()
            
            # Find highest margin row safely
            if 'gp_margin' in top_data.columns and not top_data['gp_margin'].isna().all():
                max_margin_idx = top_data['gp_margin'].idxmax()
                max_margin_name = top_data.loc[max_margin_idx, group_col]
                max_margin_val = top_data['gp_margin'].max()
            else:
                max_margin_name = "N/A"
                max_margin_val = 0
            
            st.markdown(f"""
**💰 Profitability:**
- Average GP Margin: **{avg_margin:.1f}%**
- Above average: {len(high_margin)} {group_by}s
- Highest margin: {max_margin_name} ({max_margin_val:.1f}%)
            """)


# =============================================================================
# SECTION 2: CONCENTRATION (PARETO)
# =============================================================================

def _concentration_section(
    sales_df: pd.DataFrame,
    filter_values: Dict = None,
    key_prefix: str = "conc"
):
    """Customer concentration / Pareto analysis section."""
    
    st.markdown("#### 📊 Concentration Analysis (Pareto)")
    
    # Controls
    col1, col2 = st.columns(2)
    
    with col1:
        dimension = st.selectbox(
            "Analyze",
            ["Customer", "Brand", "Product"],
            key=f"{key_prefix}_dim"
        )
    
    with col2:
        metric = st.selectbox(
            "By Metric",
            ["Revenue", "Gross Profit"],
            key=f"{key_prefix}_metric"
        )
    
    # Map
    dim_col = {"Customer": "customer", "Brand": "brand", "Product": "product_pn"}.get(dimension, "customer")
    value_col = {"Revenue": "sales_by_kpi_center_usd", "Gross Profit": "gross_profit_by_kpi_center_usd"}.get(metric)
    
    # Aggregate
    agg_df = sales_df.groupby(dim_col).agg({value_col: 'sum'}).reset_index()
    agg_df.columns = [dim_col, 'value']
    agg_df = agg_df.sort_values('value', ascending=False)
    
    total = agg_df['value'].sum()
    if total == 0:
        st.warning("No data for concentration analysis")
        return
    
    # Calculate cumulative
    agg_df['cumulative'] = agg_df['value'].cumsum()
    agg_df['cumulative_percent'] = (agg_df['cumulative'] / total * 100).round(1)
    agg_df['percent'] = (agg_df['value'] / total * 100).round(1)
    
    # Metrics
    _render_concentration_metrics(agg_df, dimension, total)
    
    # Pareto Chart
    chart = build_pareto_chart(
        data_df=agg_df.head(30),
        value_col='value',
        label_col=dim_col,
        title=f"{dimension} {metric} Distribution",
        show_cumulative_line=True,
        highlight_80_percent=True
    )
    st.altair_chart(chart, use_container_width=True)
    
    # Concentration bands table
    _render_concentration_bands(agg_df, dimension, metric, total)


def _render_concentration_metrics(agg_df, dimension, total):
    """Render concentration metrics."""
    # Find 80% threshold
    threshold_80 = agg_df[agg_df['cumulative_percent'] <= 80]
    count_80 = len(threshold_80) if not threshold_80.empty else 1
    pct_base_80 = (count_80 / len(agg_df) * 100)
    
    # CR10 (top 10%)
    top_10_count = max(1, int(len(agg_df) * 0.1))
    top_10_value = agg_df.head(top_10_count)['value'].sum()
    cr_10 = (top_10_value / total * 100)
    
    # HHI Index
    shares = agg_df['percent'] / 100
    hhi = (shares ** 2).sum() * 10000
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(f"Total {dimension}s", f"{len(agg_df):,}")
    
    with col2:
        st.metric("80% Threshold", f"{count_80:,}", f"{pct_base_80:.1f}% of base")
    
    with col3:
        st.metric("CR10 (Top 10%)", f"{cr_10:.1f}%")
    
    with col4:
        hhi_level = "Low" if hhi < 1500 else "Moderate" if hhi < 2500 else "High"
        st.metric("HHI Index", f"{hhi:.0f}", hhi_level)


def _render_concentration_bands(agg_df, dimension, metric, total):
    """Render concentration bands table."""
    st.markdown("##### 📈 Concentration Bands")
    
    bands = [("Top 5", 5), ("Top 10", 10), ("Top 20", 20), ("Top 50", 50), ("Top 100", 100)]
    
    band_data = []
    for label, n in bands:
        if n <= len(agg_df):
            band_value = agg_df.head(n)['value'].sum()
            band_pct = (band_value / total * 100) if total > 0 else 0
            band_data.append({
                'Band': label,
                'Count': n,
                'Value': f"${band_value:,.0f}",
                '% Total': f"{band_pct:.1f}%"
            })
    
    if band_data:
        band_df = pd.DataFrame(band_data)
        st.dataframe(band_df, hide_index=True, use_container_width=True)


# =============================================================================
# SECTION 3: MIX ANALYSIS
# =============================================================================

def _mix_analysis_section(
    sales_df: pd.DataFrame,
    filter_values: Dict = None,
    key_prefix: str = "mix"
):
    """Brand and Product mix analysis section."""
    
    st.markdown("#### 🎨 Brand & Product Mix")
    
    # Tabs for brand vs product
    mix_tab1, mix_tab2 = st.tabs(["📊 Brand Mix", "📦 Product Mix"])
    
    with mix_tab1:
        _render_mix_view(
            sales_df, 
            dimension="brand",
            dimension_label="Brand",
            key_prefix=f"{key_prefix}_brand"
        )
    
    with mix_tab2:
        _render_mix_view(
            sales_df,
            dimension="product_pn",
            dimension_label="Product",
            key_prefix=f"{key_prefix}_product"
        )


def _render_mix_view(sales_df: pd.DataFrame, dimension: str, dimension_label: str, key_prefix: str):
    """Render mix analysis for a dimension."""
    
    # Aggregate
    agg_df = sales_df.groupby(dimension).agg({
        'sales_by_kpi_center_usd': 'sum',
        'gross_profit_by_kpi_center_usd': 'sum',
        'inv_number': pd.Series.nunique
    }).reset_index()
    
    agg_df.columns = [dimension, 'revenue', 'gross_profit', 'orders']
    agg_df['gp_margin'] = (agg_df['gross_profit'] / agg_df['revenue'] * 100).fillna(0).round(1)
    agg_df = agg_df.sort_values('revenue', ascending=False)
    
    total_revenue = agg_df['revenue'].sum()
    if total_revenue == 0:
        st.warning(f"No {dimension_label} data")
        return
    
    agg_df['percent'] = (agg_df['revenue'] / total_revenue * 100).round(1)
    
    # Layout: Chart + Table
    col_chart, col_table = st.columns([1, 1])
    
    with col_chart:
        # Prepare data for pie (top 10 + others)
        top_items = agg_df.head(10).copy()
        
        if len(agg_df) > 10:
            others = agg_df.iloc[10:]
            others_revenue = others['revenue'].sum()
            others_gp = others['gross_profit'].sum()
            others_row = pd.DataFrame([{
                dimension: 'Others',
                'revenue': others_revenue,
                'gross_profit': others_gp,
                'orders': others['orders'].sum(),
                'gp_margin': (others_gp / others_revenue * 100) if others_revenue > 0 else 0,
                'percent': (others_revenue / total_revenue * 100)
            }])
            top_items = pd.concat([top_items, others_row], ignore_index=True)
        
        chart = build_mix_pie_chart(
            data_df=top_items,
            value_col='revenue',
            label_col=dimension,
            title=f"{dimension_label} Revenue Mix"
        )
        st.altair_chart(chart, use_container_width=True)
    
    with col_table:
        # Build display DataFrame with formatted values
        source_df = agg_df.head(15)
        display_df = pd.DataFrame()
        display_df['#'] = range(1, len(source_df) + 1)
        display_df[dimension_label] = source_df[dimension].values
        display_df['Revenue'] = source_df['revenue'].fillna(0).apply(lambda x: f"${x:,.0f}")
        display_df['GP'] = source_df['gross_profit'].fillna(0).apply(lambda x: f"${x:,.0f}")
        display_df['GP %'] = source_df['gp_margin'].fillna(0).apply(lambda x: f"{x:.1f}%")
        display_df['Orders'] = source_df['orders'].fillna(0).astype(int)
        display_df['% Mix'] = source_df['percent'].fillna(0).apply(lambda x: f"{x:.1f}%")
        
        st.dataframe(display_df, hide_index=True, use_container_width=True, height=380)
    
    # Summary metrics
    st.markdown("---")
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(f"Total {dimension_label}s", f"{len(agg_df):,}")
    
    with col2:
        avg_revenue = total_revenue / len(agg_df) if len(agg_df) > 0 else 0
        st.metric(f"Avg Revenue", f"${avg_revenue:,.0f}")
    
    with col3:
        avg_margin = agg_df['gp_margin'].mean()
        st.metric("Avg GP Margin", f"{avg_margin:.1f}%" if pd.notna(avg_margin) else "N/A")
    
    with col4:
        top_3_pct = agg_df.head(3)['percent'].sum()
        st.metric("Top 3 Share", f"{top_3_pct:.1f}%")


# =============================================================================
# SECTION 4: GROWTH ANALYSIS (YOY)
# =============================================================================

def _growth_analysis_section(
    sales_df: pd.DataFrame,
    prev_sales_df: pd.DataFrame = None,
    filter_values: Dict = None,
    key_prefix: str = "growth"
):
    """Year-over-Year growth analysis section."""
    
    st.markdown("#### 📈 Growth Analysis (YoY)")
    
    if prev_sales_df is None or prev_sales_df.empty:
        st.info("📊 No previous period data available for YoY comparison.")
        st.caption("Enable 'Show YoY' in sidebar filters to load comparison data.")
        return
    
    # Controls
    col1, col2 = st.columns(2)
    
    with col1:
        dimension = st.selectbox(
            "Compare by",
            ["Customer", "Brand", "Product"],
            key=f"{key_prefix}_dim"
        )
    
    with col2:
        metric = st.selectbox(
            "Metric",
            ["Revenue", "Gross Profit"],
            key=f"{key_prefix}_metric"
        )
    
    # Map
    dim_col = {"Customer": "customer", "Brand": "brand", "Product": "product_pn"}.get(dimension, "customer")
    value_col = {"Revenue": "sales_by_kpi_center_usd", "Gross Profit": "gross_profit_by_kpi_center_usd"}.get(metric)
    
    # Aggregate and compare
    compare_df = _build_comparison_data(sales_df, prev_sales_df, dim_col, value_col)
    
    if compare_df.empty:
        st.warning("No comparison data available")
        return
    
    # Summary metrics
    _render_growth_metrics(compare_df, dimension, metric)
    
    # Views
    view_tab1, view_tab2, view_tab3 = st.tabs(["📊 Top Movers", "🆕 New & Lost", "📋 Full List"])
    
    with view_tab1:
        _render_top_movers(compare_df, dim_col, dimension, metric)
    
    with view_tab2:
        _render_new_and_lost(compare_df, dim_col, dimension, metric)
    
    with view_tab3:
        _render_full_comparison(compare_df, dim_col, dimension)


def _build_comparison_data(sales_df, prev_sales_df, dim_col, value_col) -> pd.DataFrame:
    """Build comparison DataFrame between current and previous period."""
    # Aggregate current
    current = sales_df.groupby(dim_col).agg({value_col: 'sum'}).reset_index()
    current.columns = [dim_col, 'current']
    
    # Aggregate previous
    prev = prev_sales_df.groupby(dim_col).agg({value_col: 'sum'}).reset_index()
    prev.columns = [dim_col, 'previous']
    
    # Merge
    compare = current.merge(prev, on=dim_col, how='outer').fillna(0)
    compare['change'] = compare['current'] - compare['previous']
    compare['growth_pct'] = (
        (compare['current'] - compare['previous']) / compare['previous'] * 100
    ).replace([float('inf'), -float('inf')], 0).fillna(0).round(1)
    
    # Categorize
    compare['status'] = compare.apply(
        lambda r: '🆕 New' if r['previous'] == 0 and r['current'] > 0
        else '❌ Lost' if r['current'] == 0 and r['previous'] > 0
        else '📈 Growing' if r['growth_pct'] > 10
        else '📉 Declining' if r['growth_pct'] < -10
        else '➡️ Stable',
        axis=1
    )
    
    return compare.sort_values('current', ascending=False)


def _render_growth_metrics(compare_df, dimension, metric):
    """Render growth summary metrics."""
    total_current = compare_df['current'].sum()
    total_previous = compare_df['previous'].sum()
    total_growth = ((total_current - total_previous) / total_previous * 100) if total_previous > 0 else 0
    
    new_count = len(compare_df[compare_df['status'] == '🆕 New'])
    lost_count = len(compare_df[compare_df['status'] == '❌ Lost'])
    growing_count = len(compare_df[compare_df['status'] == '📈 Growing'])
    declining_count = len(compare_df[compare_df['status'] == '📉 Declining'])
    
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        st.metric(f"Total {metric}", f"${total_current:,.0f}", f"{total_growth:+.1f}%")
    
    with col2:
        st.metric(f"🆕 New", f"{new_count:,}")
    
    with col3:
        st.metric(f"❌ Lost", f"{lost_count:,}")
    
    with col4:
        st.metric(f"📈 Growing", f"{growing_count:,}")
    
    with col5:
        st.metric(f"📉 Declining", f"{declining_count:,}")


def _render_top_movers(compare_df, dim_col, dimension, metric):
    """Render top gainers and decliners."""
    col_gain, col_lose = st.columns(2)
    
    with col_gain:
        st.markdown("##### 📈 Top Gainers")
        gainers = compare_df[compare_df['change'] > 0].nlargest(10, 'change')
        if not gainers.empty:
            display_df = pd.DataFrame()
            display_df[dimension] = gainers[dim_col].values
            display_df['Previous'] = gainers['previous'].fillna(0).apply(lambda x: f"${x:,.0f}")
            display_df['Current'] = gainers['current'].fillna(0).apply(lambda x: f"${x:,.0f}")
            display_df['Change'] = gainers['change'].fillna(0).apply(lambda x: f"${x:+,.0f}")
            display_df['Growth %'] = gainers['growth_pct'].fillna(0).apply(lambda x: f"{x:+.1f}%")
            st.dataframe(display_df, hide_index=True, use_container_width=True)
        else:
            st.info("No gainers in this period")
    
    with col_lose:
        st.markdown("##### 📉 Top Decliners")
        losers = compare_df[compare_df['change'] < 0].nsmallest(10, 'change')
        if not losers.empty:
            display_df = pd.DataFrame()
            display_df[dimension] = losers[dim_col].values
            display_df['Previous'] = losers['previous'].fillna(0).apply(lambda x: f"${x:,.0f}")
            display_df['Current'] = losers['current'].fillna(0).apply(lambda x: f"${x:,.0f}")
            display_df['Change'] = losers['change'].fillna(0).apply(lambda x: f"${x:+,.0f}")
            display_df['Growth %'] = losers['growth_pct'].fillna(0).apply(lambda x: f"{x:+.1f}%")
            st.dataframe(display_df, hide_index=True, use_container_width=True)
        else:
            st.info("No decliners in this period")


def _render_new_and_lost(compare_df, dim_col, dimension, metric):
    """Render new and lost items."""
    col_new, col_lost = st.columns(2)
    
    with col_new:
        st.markdown("##### 🆕 New (not in previous period)")
        new_items = compare_df[compare_df['status'] == '🆕 New'].nlargest(15, 'current')
        if not new_items.empty:
            display_df = pd.DataFrame()
            display_df[dimension] = new_items[dim_col].values
            display_df[f'Current {metric}'] = new_items['current'].fillna(0).apply(lambda x: f"${x:,.0f}")
            st.dataframe(display_df, hide_index=True, use_container_width=True)
        else:
            st.info(f"No new {dimension}s")
    
    with col_lost:
        st.markdown("##### ❌ Lost (no sales this period)")
        lost_items = compare_df[compare_df['status'] == '❌ Lost'].nlargest(15, 'previous')
        if not lost_items.empty:
            display_df = pd.DataFrame()
            display_df[dimension] = lost_items[dim_col].values
            display_df[f'Previous {metric}'] = lost_items['previous'].fillna(0).apply(lambda x: f"${x:,.0f}")
            st.dataframe(display_df, hide_index=True, use_container_width=True)
        else:
            st.info(f"No lost {dimension}s")


def _render_full_comparison(compare_df, dim_col, dimension):
    """Render full comparison table."""
    source_df = compare_df.head(50)
    display_df = pd.DataFrame()
    display_df[dimension] = source_df[dim_col].values
    display_df['Previous'] = source_df['previous'].fillna(0).apply(lambda x: f"${x:,.0f}")
    display_df['Current'] = source_df['current'].fillna(0).apply(lambda x: f"${x:,.0f}")
    display_df['Change'] = source_df['change'].fillna(0).apply(lambda x: f"${x:+,.0f}")
    display_df['Growth %'] = source_df['growth_pct'].fillna(0).apply(lambda x: f"{x:+.1f}%")
    display_df['Status'] = source_df['status'].values
    
    st.dataframe(display_df, hide_index=True, use_container_width=True, height=500)


# =============================================================================
# LEGACY EXPORT (for backward compatibility)
# =============================================================================

# Keep old function name for backward compatibility if needed
top_performers_fragment = _top_performers_section