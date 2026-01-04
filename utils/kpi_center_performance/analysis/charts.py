# utils/kpi_center_performance/analysis/charts.py
"""
Analysis Tab Charts for KPI Center Performance.

VERSION: 6.1.0

Charts matching Salesperson Performance reference code style.
"""

import logging
import pandas as pd
import altair as alt

logger = logging.getLogger(__name__)

# =============================================================================
# COLOR CONFIGURATION - Match reference
# =============================================================================

METRIC_COLORS = {
    'revenue': '#FFA500',       # Orange
    'gross_profit': '#1f77b4',  # Blue
    'gp1': '#2ca02c',           # Green
}

LINE_COLOR = '#800080'  # Purple for cumulative line
TEXT_COLOR = '#333333'


# =============================================================================
# PARETO CHART - Match reference exactly
# =============================================================================

def build_pareto_chart(
    data_df: pd.DataFrame,
    value_col: str,
    label_col: str,
    title: str = "Pareto Analysis",
    metric_type: str = "revenue",
    **kwargs  # Accept extra args for compatibility
) -> alt.Chart:
    """
    Build Pareto chart: Bar (metric) + Line (cumulative %).
    
    Matches Salesperson Performance reference code exactly.
    
    Args:
        data_df: DataFrame with label, value, cumulative_percent, percent_contribution
        value_col: Column name for values (e.g., 'revenue')
        label_col: Column name for labels (e.g., 'customer')
        title: Chart title
        metric_type: 'revenue', 'gross_profit', or 'gp1' (for color)
        
    Returns:
        Altair layered chart with dual Y-axis
    """
    if data_df.empty:
        return _empty_chart("No data available")
    
    df = data_df.copy()
    
    # Verify required columns
    if value_col not in df.columns or label_col not in df.columns:
        return _empty_chart("Missing required columns")
    
    if df[value_col].sum() == 0:
        return _empty_chart("No data (total = 0)")
    
    # Config
    metric_label = {'revenue': 'Revenue', 'gross_profit': 'Gross Profit', 'gp1': 'GP1'}.get(metric_type, 'Value')
    bar_color = METRIC_COLORS.get(metric_type, '#FFA500')
    
    # === Layer 1: Bar Chart ===
    bars = alt.Chart(df).mark_bar().encode(
        x=alt.X(f'{label_col}:N', sort='-y', title=None, axis=alt.Axis(labelAngle=-45, labelLimit=100)),
        y=alt.Y(f'{value_col}:Q', title=f'{metric_label} (USD)', axis=alt.Axis(format='~s')),
        color=alt.value(bar_color),
        tooltip=[
            alt.Tooltip(f'{label_col}:N', title='Name'),
            alt.Tooltip(f'{value_col}:Q', title=metric_label, format='$,.0f'),
            alt.Tooltip('percent_contribution:Q', title='% of Total', format='.1f')
        ]
    )
    
    # === Layer 2: Bar Text Labels ===
    bar_text = alt.Chart(df).mark_text(
        align='center', baseline='bottom', dy=-5, fontSize=9
    ).encode(
        x=alt.X(f'{label_col}:N', sort='-y'),
        y=alt.Y(f'{value_col}:Q'),
        text=alt.Text(f'{value_col}:Q', format=',.0f'),
        color=alt.value(TEXT_COLOR)
    )
    
    # === Layer 3: Cumulative % Line ===
    line = alt.Chart(df).mark_line(
        point=True,
        color=LINE_COLOR,
        strokeWidth=2
    ).encode(
        x=alt.X(f'{label_col}:N', sort='-y'),
        y=alt.Y('cumulative_percent:Q', title='Cumulative %', axis=alt.Axis(format='.0%')),
        tooltip=[
            alt.Tooltip(f'{label_col}:N', title='Name'),
            alt.Tooltip('cumulative_percent:Q', title='Cumulative %', format='.1%')
        ]
    )
    
    # === Layer 4: Line Text Labels ===
    line_text = alt.Chart(df).mark_text(
        align='center', baseline='bottom', dy=-8, fontSize=9,
        color=LINE_COLOR
    ).encode(
        x=alt.X(f'{label_col}:N', sort='-y'),
        y=alt.Y('cumulative_percent:Q'),
        text=alt.Text('cumulative_percent:Q', format='.1%')
    )
    
    # === Combine with DUAL Y-AXIS ===
    chart = alt.layer(bars, bar_text, line, line_text).resolve_scale(
        y='independent'  # Important: separate Y scales
    ).properties(
        width='container',
        height=400,
        title=title
    )
    
    return chart


# =============================================================================
# GROWTH COMPARISON CHART
# =============================================================================

def build_growth_comparison_chart(
    data_df: pd.DataFrame,
    current_col: str,
    previous_col: str,
    label_col: str,
    title: str = "Growth Comparison",
    top_n: int = 15
) -> alt.Chart:
    """Build grouped bar chart for growth comparison."""
    if data_df.empty:
        return _empty_chart("No data available")
    
    chart_df = data_df.nlargest(top_n, current_col).copy()
    
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
                range=[METRIC_COLORS['revenue'], '#aec7e8']
            )
        ),
        xOffset='Period:N',
        tooltip=[
            alt.Tooltip(f'{label_col}:N', title='Name'),
            alt.Tooltip('Period:N', title='Period'),
            alt.Tooltip('Value:Q', title='Value', format='$,.0f'),
        ]
    ).properties(width='container', height=350, title=title)
    
    return chart


# =============================================================================
# HELPER
# =============================================================================

def _empty_chart(message: str = "No data available") -> alt.Chart:
    """Create placeholder chart when no data."""
    return alt.Chart(pd.DataFrame({'note': [message]})).mark_text(
        text=message, fontSize=16, color='#666666'
    ).properties(width=400, height=200)