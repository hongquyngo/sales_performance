# utils/kpi_center_performance/backlog/charts.py
"""
Backlog Tab Charts for KPI Center Performance

VERSION: 4.3.0
EXTRACTED FROM: charts.py v3.3.2

Contains:
- build_forecast_waterfall_chart: Invoiced + Backlog = Forecast vs Target
- build_gap_analysis_chart: Bullet/progress chart for target comparison
- build_backlog_by_month_chart: Simple backlog by month (single year)
- build_backlog_by_month_chart_multiyear: Timeline across multiple years
- build_backlog_by_month_stacked: Stacked bars comparing same months across years
"""

import logging
from typing import Dict, List
import pandas as pd
import altair as alt

from ..constants import COLORS, MONTH_ORDER
from ..common.charts import empty_chart

logger = logging.getLogger(__name__)


# =============================================================================
# BACKLOG & FORECAST CHARTS - v2.4.0
# =============================================================================

def build_forecast_waterfall_chart(
    backlog_metrics: Dict,
    metric: str = 'revenue',
    title: str = ""
) -> alt.Chart:
    """
    Build a waterfall-style chart showing Invoiced + Backlog = Forecast vs Target.
    SYNCED with Salesperson page.
    
    Args:
        backlog_metrics: Dict with invoiced, backlog, target, forecast values
        metric: 'revenue', 'gp', or 'gp1'
        title: Optional chart title
        
    Returns:
        Altair stacked bar chart
    """
    if not backlog_metrics:
        return alt.Chart().mark_text().encode(text=alt.value("No backlog data"))
    
    # Map metric to keys
    metric_keys = {
        'revenue': {
            'invoiced': 'invoiced_revenue',
            'backlog': 'in_period_backlog_revenue',
            'target': 'target_revenue',
            'forecast': 'forecast_revenue',
            'label': 'Revenue'
        },
        'gp': {
            'invoiced': 'invoiced_gp',
            'backlog': 'in_period_backlog_gp',
            'target': 'target_gp',
            'forecast': 'forecast_gp',
            'label': 'Gross Profit'
        },
        'gp1': {
            'invoiced': 'invoiced_gp1',
            'backlog': 'in_period_backlog_gp1',
            'target': 'target_gp1',
            'forecast': 'forecast_gp1',
            'label': 'GP1'
        }
    }
    
    keys = metric_keys.get(metric, metric_keys['revenue'])
    
    # Get values with fallback
    invoiced = backlog_metrics.get(keys['invoiced'], 0) or 0
    backlog = backlog_metrics.get(keys['backlog'], 0) or 0
    target = backlog_metrics.get(keys['target'], 0) or 0
    forecast = backlog_metrics.get(keys['forecast'], invoiced + backlog) or (invoiced + backlog)
    
    chart_title = title if title else None
    
    # Prepare data for stacked bar
    data = pd.DataFrame([
        {
            'category': 'Performance',
            'component': '✅ Invoiced',
            'value': invoiced,
            'order': 1
        },
        {
            'category': 'Performance',
            'component': '📅 In-Period Backlog',
            'value': backlog,
            'order': 2
        },
        {
            'category': 'Target',
            'component': '🎯 Target',
            'value': target,
            'order': 1
        }
    ])
    
    # Color scale
    color_scale = alt.Scale(
        domain=['✅ Invoiced', '📅 In-Period Backlog', '🎯 Target'],
        range=[COLORS.get('gross_profit', '#1f77b4'), COLORS.get('new_customer', '#17becf'), COLORS.get('target', '#d62728')]
    )
    
    # Stacked bar chart
    bars = alt.Chart(data).mark_bar(size=60).encode(
        x=alt.X('category:N', title='', axis=alt.Axis(labelAngle=0)),
        y=alt.Y('value:Q', title='Amount (USD)', axis=alt.Axis(format='~s'), stack='zero'),
        color=alt.Color('component:N', scale=color_scale, legend=alt.Legend(orient='bottom')),
        order=alt.Order('order:Q'),
        tooltip=[
            alt.Tooltip('category:N', title='Category'),
            alt.Tooltip('component:N', title='Component'),
            alt.Tooltip('value:Q', title='Amount', format='$,.0f')
        ]
    )
    
    # Add forecast line
    forecast_line = alt.Chart(pd.DataFrame({'y': [forecast]})).mark_rule(
        color=COLORS.get('gross_profit_percent', '#800080'),
        strokeWidth=2,
        strokeDash=[5, 5]
    ).encode(
        y='y:Q'
    )
    
    # Add forecast label
    forecast_text = alt.Chart(pd.DataFrame({
        'x': ['Target'],
        'y': [forecast],
        'label': [f'Forecast: ${forecast:,.0f}']
    })).mark_text(
        align='left',
        dx=35,
        fontSize=12,
        fontWeight='bold',
        color=COLORS.get('gross_profit_percent', '#800080')
    ).encode(
        x='x:N',
        y='y:Q',
        text='label:N'
    )
    
    # Build final chart
    chart_props = {
        'width': 400,
        'height': 350
    }
    if chart_title:
        chart_props['title'] = chart_title
    
    chart = alt.layer(bars, forecast_line, forecast_text).properties(**chart_props)
    
    return chart


def build_gap_analysis_chart(
    backlog_metrics: Dict,
    metrics_to_show: List[str] = ['revenue'],
    title: str = ""
) -> alt.Chart:
    """
    Build a bullet/progress chart showing current progress, forecast, and target.
    SYNCED with Salesperson page.
    
    Args:
        backlog_metrics: Dict with invoiced, target, forecast values
        metrics_to_show: List of metrics to display ['revenue', 'gp', 'gp1']
        title: Optional chart title
        
    Returns:
        Altair layered bullet chart
    """
    if not backlog_metrics:
        return alt.Chart().mark_text().encode(text=alt.value("No data available"))
    
    # Define metric configurations
    metric_configs = {
        'revenue': {
            'invoiced_key': 'invoiced_revenue',
            'target_key': 'target_revenue',
            'forecast_key': 'forecast_revenue',
            'label': 'Revenue'
        },
        'gp': {
            'invoiced_key': 'invoiced_gp',
            'target_key': 'target_gp',
            'forecast_key': 'forecast_gp',
            'label': 'Gross Profit'
        },
        'gp1': {
            'invoiced_key': 'invoiced_gp1',
            'target_key': 'target_gp1',
            'forecast_key': 'forecast_gp1',
            'label': 'GP1'
        }
    }
    
    # Build data for all metrics
    all_data = []
    for metric_name in metrics_to_show:
        if metric_name not in metric_configs:
            continue
        
        config = metric_configs[metric_name]
        target = backlog_metrics.get(config['target_key'], 0) or 0
        invoiced = backlog_metrics.get(config['invoiced_key'], 0) or 0
        forecast = backlog_metrics.get(config['forecast_key'], invoiced) or invoiced
        
        if target == 0:
            continue
        
        invoiced_pct = (invoiced / target) * 100
        forecast_pct = (forecast / target) * 100
        
        all_data.extend([
            {'metric': config['label'], 'type': 'Invoiced', 'value': invoiced, 'percent': invoiced_pct},
            {'metric': config['label'], 'type': 'Forecast', 'value': forecast, 'percent': forecast_pct},
            {'metric': config['label'], 'type': 'Target', 'value': target, 'percent': 100},
        ])
    
    if not all_data:
        return alt.Chart().mark_text().encode(text=alt.value("No target set"))
    
    data = pd.DataFrame(all_data)
    
    chart_title = title if title else None
    
    # Base bar (target as background)
    base = alt.Chart(data[data['type'] == 'Target']).mark_bar(
        color='#e0e0e0',
        size=40
    ).encode(
        x=alt.X('value:Q', title='Amount (USD)', axis=alt.Axis(format='~s')),
        y=alt.Y('metric:N', title='', sort=['Revenue', 'Gross Profit', 'GP1'])
    )
    
    # Forecast bar
    forecast_bar = alt.Chart(data[data['type'] == 'Forecast']).mark_bar(
        color=COLORS.get('new_customer', '#17becf'),
        size=25
    ).encode(
        x=alt.X('value:Q'),
        y=alt.Y('metric:N', sort=['Revenue', 'Gross Profit', 'GP1']),
        tooltip=[
            alt.Tooltip('metric:N', title='Metric'),
            alt.Tooltip('type:N', title='Type'),
            alt.Tooltip('value:Q', title='Amount', format='$,.0f'),
            alt.Tooltip('percent:Q', title='% of Target', format='.1f')
        ]
    )
    
    # Invoiced bar (innermost)
    invoiced_bar = alt.Chart(data[data['type'] == 'Invoiced']).mark_bar(
        color=COLORS.get('gross_profit', '#1f77b4'),
        size=15
    ).encode(
        x=alt.X('value:Q'),
        y=alt.Y('metric:N', sort=['Revenue', 'Gross Profit', 'GP1']),
        tooltip=[
            alt.Tooltip('metric:N', title='Metric'),
            alt.Tooltip('type:N', title='Type'),
            alt.Tooltip('value:Q', title='Amount', format='$,.0f'),
            alt.Tooltip('percent:Q', title='% of Target', format='.1f')
        ]
    )
    
    # Target line/tick
    target_rule = alt.Chart(data[data['type'] == 'Target']).mark_tick(
        color=COLORS.get('target', '#d62728'),
        thickness=3,
        size=50
    ).encode(
        x=alt.X('value:Q'),
        y=alt.Y('metric:N', sort=['Revenue', 'Gross Profit', 'GP1'])
    )
    
    # Achievement % text at end
    forecast_data = data[data['type'] == 'Forecast'].copy()
    text = alt.Chart(forecast_data).mark_text(
        align='left',
        dx=5,
        fontSize=11,
        fontWeight='bold'
    ).encode(
        x=alt.X('value:Q'),
        y=alt.Y('metric:N', sort=['Revenue', 'Gross Profit', 'GP1']),
        text=alt.Text('percent:Q', format='.0f'),
        color=alt.condition(
            alt.datum.percent >= 100,
            alt.value(COLORS.get('achievement_good', '#28a745')),
            alt.value(COLORS.get('achievement_bad', '#dc3545'))
        )
    )
    
    # Build final chart
    chart_props = {
        'width': 'container',
        'height': 80 + len(metrics_to_show) * 50
    }
    if chart_title:
        chart_props['title'] = chart_title
    
    chart = alt.layer(base, forecast_bar, invoiced_bar, target_rule, text).properties(**chart_props)
    
    return chart


# =============================================================================
# BACKLOG BY MONTH CHARTS - v3.0.0
# =============================================================================

def build_backlog_by_month_chart(
    monthly_df: pd.DataFrame,
    revenue_col: str = 'backlog_revenue',
    gp_col: str = 'backlog_gp',
    month_col: str = 'etd_month',
    title: str = "Backlog by ETD Month"
) -> alt.Chart:
    """
    Build simple backlog by month bar chart for single year view.
    
    Args:
        monthly_df: DataFrame with month and backlog values
        revenue_col: Column name for revenue values
        gp_col: Column name for GP values
        month_col: Column name for month
        title: Chart title
        
    Returns:
        Altair layered chart with bars
    """
    if monthly_df.empty:
        return empty_chart("No backlog data")
    
    df = monthly_df.copy()
    
    # Ensure columns exist
    if revenue_col not in df.columns:
        return empty_chart(f"Missing column: {revenue_col}")
    
    # Revenue bars
    bars = alt.Chart(df).mark_bar(
        color=COLORS.get('revenue', '#FFA500'),
        opacity=0.8
    ).encode(
        x=alt.X(f'{month_col}:N', sort=MONTH_ORDER, title='Month'),
        y=alt.Y(f'{revenue_col}:Q', title='Backlog (USD)', axis=alt.Axis(format='~s')),
        tooltip=[
            alt.Tooltip(f'{month_col}:N', title='Month'),
            alt.Tooltip(f'{revenue_col}:Q', title='Revenue', format='$,.0f'),
        ]
    )
    
    # Add GP bars if available
    if gp_col and gp_col in df.columns:
        gp_bars = alt.Chart(df).mark_bar(
            color=COLORS.get('gross_profit', '#1f77b4'),
            opacity=0.6,
            xOffset=15
        ).encode(
            x=alt.X(f'{month_col}:N', sort=MONTH_ORDER),
            y=alt.Y(f'{gp_col}:Q'),
            tooltip=[
                alt.Tooltip(f'{month_col}:N', title='Month'),
                alt.Tooltip(f'{gp_col}:Q', title='GP', format='$,.0f'),
            ]
        )
        chart = alt.layer(bars, gp_bars)
    else:
        chart = bars
    
    # Add value labels
    labels = alt.Chart(df).mark_text(
        dy=-10,
        fontSize=10,
        color='#333'
    ).encode(
        x=alt.X(f'{month_col}:N', sort=MONTH_ORDER),
        y=alt.Y(f'{revenue_col}:Q'),
        text=alt.Text(f'{revenue_col}:Q', format=',.0f')
    )
    
    return alt.layer(chart, labels).properties(
        width='container',
        height=350,
        title=title
    )


def build_backlog_by_month_chart_multiyear(
    monthly_df: pd.DataFrame,
    revenue_col: str = 'backlog_revenue',
    title: str = "Backlog Timeline"
) -> alt.Chart:
    """
    Build timeline backlog chart across multiple years.
    X-axis shows "Jan'25, Feb'25, ..., Jan'26" format.
    
    Args:
        monthly_df: DataFrame with year_month, etd_year, and backlog values
        revenue_col: Column name for revenue values
        title: Chart title
        
    Returns:
        Altair bar chart with color by year
    """
    if monthly_df.empty:
        return empty_chart("No backlog data")
    
    df = monthly_df.copy()
    
    if revenue_col not in df.columns:
        return empty_chart(f"Missing column: {revenue_col}")
    
    # Ensure year_month column exists
    if 'year_month' not in df.columns:
        df['year_month'] = df['etd_month'] + "'" + df['etd_year'].astype(str).str[-2:]
    
    # Convert etd_year to string for color encoding
    df['year_str'] = df['etd_year'].astype(str)
    
    # Get unique years for color scale
    unique_years = sorted(df['etd_year'].unique())
    year_colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd']
    color_scale = alt.Scale(
        domain=[str(y) for y in unique_years],
        range=year_colors[:len(unique_years)]
    )
    
    # Build chart
    bars = alt.Chart(df).mark_bar().encode(
        x=alt.X('year_month:N', title='ETD Month', sort=None),
        y=alt.Y(f'{revenue_col}:Q', title='Backlog (USD)', axis=alt.Axis(format='~s')),
        color=alt.Color('year_str:N', scale=color_scale, title='Year'),
        tooltip=[
            alt.Tooltip('year_month:N', title='Month'),
            alt.Tooltip('etd_year:O', title='Year'),
            alt.Tooltip(f'{revenue_col}:Q', title='Revenue', format='$,.0f'),
        ]
    )
    
    # Add value labels on top
    labels = alt.Chart(df).mark_text(
        dy=-8,
        fontSize=9,
        color='#333'
    ).encode(
        x=alt.X('year_month:N', sort=None),
        y=alt.Y(f'{revenue_col}:Q'),
        text=alt.Text(f'{revenue_col}:Q', format=',.0f')
    )
    
    return alt.layer(bars, labels).properties(
        width='container',
        height=350,
        title=title
    )


def build_backlog_by_month_stacked(
    monthly_df: pd.DataFrame,
    revenue_col: str = 'backlog_revenue',
    title: str = "Backlog by Month (Stacked)"
) -> alt.Chart:
    """
    Build stacked bar chart comparing same months across years.
    
    Args:
        monthly_df: DataFrame with etd_month, etd_year, and backlog values
        revenue_col: Column name for revenue values
        title: Chart title
        
    Returns:
        Altair stacked bar chart
    """
    if monthly_df.empty:
        return empty_chart("No backlog data")
    
    df = monthly_df.copy()
    
    if revenue_col not in df.columns:
        return empty_chart(f"Missing column: {revenue_col}")
    
    # Convert etd_year to string for color encoding
    df['year_str'] = df['etd_year'].astype(str)
    
    # Get unique years for color scale
    unique_years = sorted(df['etd_year'].unique())
    year_colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd']
    color_scale = alt.Scale(
        domain=[str(y) for y in unique_years],
        range=year_colors[:len(unique_years)]
    )
    
    # Build stacked bar chart
    chart = alt.Chart(df).mark_bar().encode(
        x=alt.X('etd_month:N', sort=MONTH_ORDER, title='Month'),
        y=alt.Y(f'{revenue_col}:Q', title='Backlog (USD)', axis=alt.Axis(format='~s')),
        color=alt.Color('year_str:N', scale=color_scale, title='Year', 
                      legend=alt.Legend(orient='bottom')),
        tooltip=[
            alt.Tooltip('etd_month:N', title='Month'),
            alt.Tooltip('etd_year:O', title='Year'),
            alt.Tooltip(f'{revenue_col}:Q', title='Revenue', format='$,.0f'),
        ]
    )
    
    return chart.properties(
        width='container',
        height=350,
        title=title
    )
