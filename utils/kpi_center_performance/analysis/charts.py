# utils/kpi_center_performance/analysis/charts.py
"""
Analysis Tab Charts for KPI Center Performance.

VERSION: 5.0.0

Contains:
- build_pareto_chart: Pareto analysis with bar + cumulative line
- build_top_performers_chart: Horizontal bar chart for top N
- build_mix_pie_chart: Pie/donut chart for mix analysis
- build_growth_comparison_chart: Bar chart for growth comparison
"""

import logging
import pandas as pd
import altair as alt

from ..constants import COLORS

logger = logging.getLogger(__name__)

# Extended color palette for charts
CHART_COLORS = [
    '#1f77b4',  # blue
    '#ff7f0e',  # orange
    '#2ca02c',  # green
    '#d62728',  # red
    '#9467bd',  # purple
    '#8c564b',  # brown
    '#e377c2',  # pink
    '#7f7f7f',  # gray
    '#bcbd22',  # olive
    '#17becf',  # cyan
]


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
        value_col: Column name for values (e.g., 'value')
        label_col: Column name for labels (e.g., 'customer')
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
    
    # Determine if item is within 80% threshold
    if highlight_80_percent:
        chart_df['within_80'] = chart_df['cumulative_percent'] <= 80
    
    # Bar chart
    bars = alt.Chart(chart_df).mark_bar(
        cornerRadiusTopLeft=3,
        cornerRadiusTopRight=3
    ).encode(
        x=alt.X(f'{label_col}:N', 
               sort=alt.EncodingSortField(field='order', order='ascending'),
               title=None,
               axis=alt.Axis(labelAngle=-45, labelLimit=100)),
        y=alt.Y(f'{value_col}:Q', title='Value'),
        color=alt.condition(
            alt.datum.within_80 if highlight_80_percent else alt.value(True),
            alt.value(COLORS.get('primary', '#1f77b4')),
            alt.value('#aec7e8')
        ) if highlight_80_percent else alt.value(COLORS.get('primary', '#1f77b4')),
        tooltip=[
            alt.Tooltip(f'{label_col}:N', title='Name'),
            alt.Tooltip(f'{value_col}:Q', title='Value', format='$,.0f'),
            alt.Tooltip('percent:Q', title='% of Total', format='.1f'),
            alt.Tooltip('cumulative_percent:Q', title='Cumulative %', format='.1f'),
        ]
    )
    
    chart = bars
    
    if show_cumulative_line:
        # Cumulative line
        line = alt.Chart(chart_df).mark_line(
            color='#ff7f0e',
            strokeWidth=2,
            point=alt.OverlayMarkDef(color='#ff7f0e', size=50)
        ).encode(
            x=alt.X(f'{label_col}:N', sort=alt.EncodingSortField(field='order', order='ascending')),
            y=alt.Y('cumulative_percent:Q', title='Cumulative %', scale=alt.Scale(domain=[0, 105])),
        )
        
        # Add 80% threshold line
        if highlight_80_percent:
            threshold = alt.Chart(pd.DataFrame({'y': [80]})).mark_rule(
                color='red',
                strokeDash=[5, 5],
                strokeWidth=1.5
            ).encode(y='y:Q')
            
            chart = alt.layer(bars, line, threshold).resolve_scale(y='independent')
        else:
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
        label_col: Column name for labels (e.g., 'customer')
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


def build_mix_pie_chart(
    data_df: pd.DataFrame,
    value_col: str,
    label_col: str,
    title: str = "Mix Analysis",
    inner_radius: int = 50
) -> alt.Chart:
    """
    Build pie/donut chart for mix analysis.
    
    Args:
        data_df: DataFrame with label and value columns
        value_col: Column name for values
        label_col: Column name for labels
        title: Chart title
        inner_radius: Inner radius (0 for pie, >0 for donut)
        
    Returns:
        Altair pie/donut chart
    """
    if data_df.empty:
        return alt.Chart().mark_text().encode(text=alt.value("No data"))
    
    chart_df = data_df.copy()
    total = chart_df[value_col].sum()
    
    if total == 0:
        return alt.Chart().mark_text().encode(text=alt.value("No data"))
    
    chart_df['percent'] = (chart_df[value_col] / total * 100).round(1)
    
    chart = alt.Chart(chart_df).mark_arc(innerRadius=inner_radius).encode(
        theta=alt.Theta(f'{value_col}:Q', stack=True),
        color=alt.Color(
            f'{label_col}:N',
            scale=alt.Scale(range=CHART_COLORS),
            legend=alt.Legend(
                title=None,
                orient='right',
                labelLimit=150
            )
        ),
        tooltip=[
            alt.Tooltip(f'{label_col}:N', title='Name'),
            alt.Tooltip(f'{value_col}:Q', title='Value', format='$,.0f'),
            alt.Tooltip('percent:Q', title='% of Total', format='.1f'),
        ]
    ).properties(
        width=300,
        height=300,
        title=title
    )
    
    return chart


def build_growth_comparison_chart(
    data_df: pd.DataFrame,
    current_col: str,
    previous_col: str,
    label_col: str,
    title: str = "Growth Comparison",
    top_n: int = 15
) -> alt.Chart:
    """
    Build grouped bar chart for growth comparison.
    
    Args:
        data_df: DataFrame with current, previous, and label columns
        current_col: Column name for current period values
        previous_col: Column name for previous period values
        label_col: Column name for labels
        title: Chart title
        top_n: Number of items to show
        
    Returns:
        Altair grouped bar chart
    """
    if data_df.empty:
        return alt.Chart().mark_text().encode(text=alt.value("No data"))
    
    chart_df = data_df.nlargest(top_n, current_col).copy()
    
    # Melt for grouped bars
    melted = chart_df.melt(
        id_vars=[label_col],
        value_vars=[current_col, previous_col],
        var_name='Period',
        value_name='Value'
    )
    
    melted['Period'] = melted['Period'].map({
        current_col: 'Current',
        previous_col: 'Previous'
    })
    
    chart = alt.Chart(melted).mark_bar().encode(
        x=alt.X(f'{label_col}:N', sort='-y', title=None, axis=alt.Axis(labelAngle=-45)),
        y=alt.Y('Value:Q', title='Value'),
        color=alt.Color(
            'Period:N',
            scale=alt.Scale(
                domain=['Current', 'Previous'],
                range=[COLORS.get('primary', '#1f77b4'), '#aec7e8']
            )
        ),
        xOffset='Period:N',
        tooltip=[
            alt.Tooltip(f'{label_col}:N', title='Name'),
            alt.Tooltip('Period:N', title='Period'),
            alt.Tooltip('Value:Q', title='Value', format='$,.0f'),
        ]
    ).properties(
        width='container',
        height=350,
        title=title
    )
    
    return chart