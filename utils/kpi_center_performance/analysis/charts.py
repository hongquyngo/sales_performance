# utils/kpi_center_performance/analysis/charts.py
"""
Analysis Tab Charts for KPI Center Performance

VERSION: 4.3.0
EXTRACTED FROM: charts.py v3.3.2

Contains:
- build_pareto_chart: Pareto analysis with bar + cumulative line
- build_top_performers_chart: Horizontal bar chart for top N
"""

import logging
import pandas as pd
import altair as alt

from ..constants import COLORS

logger = logging.getLogger(__name__)


def build_pareto_chart(
    data_df: pd.DataFrame,
    value_col: str,
    label_col: str,
    title: str = "Pareto Analysis",
    show_cumulative_line: bool = True,
    highlight_80_percent: bool = True
) -> alt.Chart:
    """
    Build Pareto chart with bar + cumulative line.
    
    Args:
        data_df: DataFrame with label and value columns
        value_col: Column name for values (e.g., 'revenue')
        label_col: Column name for labels (e.g., 'customer_name')
        title: Chart title
        show_cumulative_line: Whether to show cumulative % line
        highlight_80_percent: Whether to highlight 80% threshold
        
    Returns:
        Altair layered chart with bars and optional line
    """
    if data_df.empty:
        return alt.Chart().mark_text().encode(text=alt.value("No data"))
    
    chart_df = data_df.sort_values(value_col, ascending=False).head(20).copy()
    
    total = chart_df[value_col].sum()
    if total == 0:
        return alt.Chart().mark_text().encode(text=alt.value("No data"))
    
    chart_df['cumulative'] = chart_df[value_col].cumsum()
    chart_df['cumulative_percent'] = (chart_df['cumulative'] / total * 100).round(1)
    chart_df['percent'] = (chart_df[value_col] / total * 100).round(1)
    chart_df['order'] = range(len(chart_df))
    
    bars = alt.Chart(chart_df).mark_bar(
        color=COLORS.get('primary', '#1f77b4'),
        cornerRadiusTopLeft=3,
        cornerRadiusTopRight=3
    ).encode(
        x=alt.X(f'{label_col}:N', 
               sort=alt.EncodingSortField(field='order', order='ascending'),
               title=None,
               axis=alt.Axis(labelAngle=-45, labelLimit=100)),
        y=alt.Y(f'{value_col}:Q', title='Value'),
        tooltip=[
            alt.Tooltip(f'{label_col}:N', title='Name'),
            alt.Tooltip(f'{value_col}:Q', title='Value', format='$,.0f'),
            alt.Tooltip('percent:Q', title='% of Total', format='.1f'),
            alt.Tooltip('cumulative_percent:Q', title='Cumulative %', format='.1f'),
        ]
    )
    
    chart = bars
    
    if show_cumulative_line:
        line = alt.Chart(chart_df).mark_line(
            color=COLORS.get('secondary', '#aec7e8'),
            strokeWidth=2,
            point=alt.OverlayMarkDef(color=COLORS.get('secondary', '#aec7e8'), size=50)
        ).encode(
            x=alt.X(f'{label_col}:N', sort=alt.EncodingSortField(field='order', order='ascending')),
            y=alt.Y('cumulative_percent:Q', title='Cumulative %', scale=alt.Scale(domain=[0, 105])),
        )
        
        chart = alt.layer(bars, line).resolve_scale(y='independent')
    
    return chart.properties(width='container', height=350, title=title)


def build_top_performers_chart(
    data_df: pd.DataFrame,
    value_col: str,
    label_col: str,
    top_n: int = 10,
    title: str = "Top Performers",
    show_percent: bool = True
) -> alt.Chart:
    """
    Build horizontal bar chart for top performers.
    
    Args:
        data_df: DataFrame with label and value columns
        value_col: Column name for values (e.g., 'revenue')
        label_col: Column name for labels (e.g., 'customer_name')
        top_n: Number of top items to show
        title: Chart title
        show_percent: Whether to show percentage labels
        
    Returns:
        Altair horizontal bar chart
    """
    if data_df.empty:
        return alt.Chart().mark_text().encode(text=alt.value("No data"))
    
    chart_df = data_df.nlargest(top_n, value_col).copy()
    
    total = data_df[value_col].sum()
    if total > 0:
        chart_df['percent'] = (chart_df[value_col] / total * 100).round(1)
    else:
        chart_df['percent'] = 0
    
    bars = alt.Chart(chart_df).mark_bar(
        color=COLORS.get('primary', '#1f77b4'),
        cornerRadiusTopRight=4,
        cornerRadiusBottomRight=4
    ).encode(
        x=alt.X(f'{value_col}:Q', title='Value'),
        y=alt.Y(f'{label_col}:N', sort='-x', title=None),
        tooltip=[
            alt.Tooltip(f'{label_col}:N', title='Name'),
            alt.Tooltip(f'{value_col}:Q', title='Value', format='$,.0f'),
            alt.Tooltip('percent:Q', title='% of Total', format='.1f'),
        ]
    )
    
    chart = bars
    
    if show_percent:
        text = alt.Chart(chart_df).mark_text(
            align='left',
            baseline='middle',
            dx=5,
            fontSize=11
        ).encode(
            x=alt.X(f'{value_col}:Q'),
            y=alt.Y(f'{label_col}:N', sort='-x'),
            text=alt.Text('percent:Q', format='.1f'),
        )
        chart = bars + text
    
    return chart.properties(width='container', height=min(400, top_n * 35), title=title)
