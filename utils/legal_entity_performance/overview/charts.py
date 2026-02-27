# utils/legal_entity_performance/overview/charts.py
"""
Overview Tab Charts for Legal Entity Performance
Adapted from kpi_center_performance/overview/charts.py

VERSION: 2.0.0
Charts:
- render_kpi_cards: Metric cards with YoY deltas
- build_monthly_trend_dual_chart: Revenue + GP bars with GP% line
- build_cumulative_dual_chart: Cumulative Revenue + GP lines
- build_yoy_comparison_chart: YoY grouped bars
- build_yoy_cumulative_chart: YoY cumulative lines
"""

import logging
from typing import Dict, List, Optional
import pandas as pd
import numpy as np
import altair as alt
import streamlit as st

from ..constants import COLORS, MONTH_ORDER, CHART_WIDTH, CHART_HEIGHT
from ..common.charts import empty_chart

logger = logging.getLogger(__name__)


# =============================================================================
# KPI CARDS - Adapted from KPI center (simplified: no complex KPIs, no targets)
# =============================================================================

def render_kpi_cards(
    metrics: Dict,
    yoy_metrics: Dict = None,
    backlog_metrics: Dict = None,
):
    """
    Render KPI summary cards using Streamlit metrics.
    Adapted from KPI center render_kpi_cards.
    """
    # =========================================================================
    # PERFORMANCE SECTION
    # =========================================================================
    with st.container(border=True):
        st.markdown("**💰 PERFORMANCE**")
        
        # Row 1: Revenue | GP | GP1 | Commission
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            delta = None
            if yoy_metrics and yoy_metrics.get('revenue_delta_pct') is not None:
                delta = f"{yoy_metrics['revenue_delta_pct']:+.1f}% YoY"
            st.metric(
                label="Revenue",
                value=f"${metrics['total_revenue']:,.0f}",
                delta=delta,
                help="Total invoiced revenue. Formula: Σ calculated_invoiced_amount_usd"
            )
        
        with col2:
            delta = None
            if yoy_metrics and yoy_metrics.get('gp_delta_pct') is not None:
                delta = f"{yoy_metrics['gp_delta_pct']:+.1f}% YoY"
            st.metric(
                label="Gross Profit",
                value=f"${metrics['total_gp']:,.0f}",
                delta=delta,
                help="Revenue minus COGS. Formula: Σ invoiced_gross_profit_usd"
            )
        
        with col3:
            delta = None
            if yoy_metrics and yoy_metrics.get('gp1_delta_pct') is not None:
                delta = f"{yoy_metrics['gp1_delta_pct']:+.1f}% YoY"
            st.metric(
                label="GP1",
                value=f"${metrics['total_gp1']:,.0f}",
                delta=delta,
                help="Gross Profit after deducting broker commission"
            )
        
        with col4:
            st.metric(
                label="Commission",
                value=f"${metrics['total_commission']:,.0f}",
                help="Broker commission. Formula: Σ broker_commission_usd"
            )
        
        # Row 2: Customers | GP% | GP1% | Orders
        col5, col6, col7, col8 = st.columns(4)
        
        with col5:
            st.metric(
                label="Customers",
                value=f"{metrics['total_customers']:,}",
                help="Unique customers served in period"
            )
        
        with col6:
            gp_pct = metrics.get('gp_percent', 0)
            st.metric(
                label="GP %",
                value=f"{gp_pct:.1f}%",
                delta="↑ margin" if gp_pct > 30 else None,
                delta_color="off",
                help="Gross Profit Margin. Formula: GP / Revenue × 100%"
            )
        
        with col7:
            gp1_pct = metrics.get('gp1_percent', 0)
            st.metric(
                label="GP1 %",
                value=f"{gp1_pct:.1f}%",
                delta="↑ margin" if gp1_pct > 25 else None,
                delta_color="off",
                help="GP1 Margin. Formula: GP1 / Revenue × 100%"
            )
        
        with col8:
            st.metric(
                label="Invoices",
                value=f"{metrics['total_orders']:,}",
                help="Unique invoices in period"
            )
    
    # =========================================================================
    # BACKLOG SECTION
    # =========================================================================
    if backlog_metrics and backlog_metrics.get('total_backlog_usd', 0) > 0:
        with st.container(border=True):
            st.markdown("**📦 BACKLOG**")
            
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric(
                    label="Total Backlog",
                    value=f"${backlog_metrics['total_backlog_usd']:,.0f}",
                    help="Total outstanding order value"
                )
            with col2:
                st.metric(
                    label="In-Period Backlog",
                    value=f"${backlog_metrics.get('in_period_backlog_usd', 0):,.0f}",
                    help="Backlog with ETD within current period"
                )
            with col3:
                overdue = backlog_metrics.get('overdue_count', 0)
                st.metric(
                    label="Overdue Orders",
                    value=f"{overdue}",
                    delta=f"${backlog_metrics.get('overdue_amount_usd', 0):,.0f}" if overdue > 0 else None,
                    delta_color="inverse" if overdue > 0 else "off",
                    help="Orders past ETD date"
                )
            with col4:
                st.metric(
                    label="Backlog GP",
                    value=f"${backlog_metrics.get('total_backlog_gp_usd', 0):,.0f}",
                    help="Gross Profit from outstanding orders"
                )


# =============================================================================
# MONTHLY TREND DUAL CHART - Adapted from KPI center
# =============================================================================

def build_monthly_trend_dual_chart(
    monthly_df: pd.DataFrame,
    show_gp_percent_line: bool = True
) -> alt.Chart:
    """
    Build monthly trend chart with Revenue + GP bars and GP% line.
    Adapted from kpi_center_performance/overview/charts.py
    """
    if monthly_df.empty:
        return empty_chart("No monthly data")
    
    chart_df = monthly_df.copy()
    chart_df['month_order'] = chart_df['month'].map(
        {m: i for i, m in enumerate(MONTH_ORDER)}
    )
    chart_df = chart_df.sort_values('month_order')
    
    if 'gp_percent' not in chart_df.columns:
        chart_df['gp_percent'] = (chart_df['gross_profit'] / chart_df['revenue'] * 100).fillna(0)
    
    # Prepare grouped bar data
    bar_data = []
    for _, row in chart_df.iterrows():
        bar_data.append({
            'month': row['month'], 'month_order': row['month_order'],
            'metric': 'Revenue', 'value': row.get('revenue', 0),
            'gp_percent': row.get('gp_percent', 0)
        })
        bar_data.append({
            'month': row['month'], 'month_order': row['month_order'],
            'metric': 'Gross Profit', 'value': row.get('gross_profit', 0),
            'gp_percent': row.get('gp_percent', 0)
        })
    
    bar_df = pd.DataFrame(bar_data)
    
    color_scale = alt.Scale(
        domain=['Revenue', 'Gross Profit'],
        range=[COLORS['revenue'], COLORS['gross_profit']]
    )
    
    bars = alt.Chart(bar_df).mark_bar(
        cornerRadiusTopLeft=2, cornerRadiusTopRight=2
    ).encode(
        x=alt.X('month:N', sort=MONTH_ORDER, title='Month', axis=alt.Axis(labelAngle=0)),
        y=alt.Y('value:Q', title='Amount (USD)', axis=alt.Axis(format='~s')),
        color=alt.Color('metric:N', scale=color_scale, legend=alt.Legend(title='Metric', orient='bottom')),
        xOffset='metric:N',
        tooltip=[
            alt.Tooltip('month:N', title='Month'),
            alt.Tooltip('metric:N', title='Metric'),
            alt.Tooltip('value:Q', title='Amount', format='$,.0f'),
        ]
    )
    
    bar_labels = alt.Chart(bar_df).mark_text(
        align='center', baseline='bottom', dy=-5, fontSize=9
    ).encode(
        x=alt.X('month:N', sort=MONTH_ORDER),
        y=alt.Y('value:Q'),
        xOffset='metric:N',
        text=alt.Text('value:Q', format=',.0f'),
        color=alt.value(COLORS['text_dark'])
    )
    
    chart = bars + bar_labels
    
    if show_gp_percent_line:
        line_df = chart_df[['month', 'month_order', 'gp_percent']].copy()
        
        line = alt.Chart(line_df).mark_line(
            color=COLORS['gross_profit_percent'],
            strokeWidth=2,
            point=alt.OverlayMarkDef(color=COLORS['gross_profit_percent'], size=40)
        ).encode(
            x=alt.X('month:N', sort=MONTH_ORDER),
            y=alt.Y('gp_percent:Q', title='GP %', axis=alt.Axis(format='.0f')),
            tooltip=[
                alt.Tooltip('month:N', title='Month'),
                alt.Tooltip('gp_percent:Q', title='GP %', format='.1f'),
            ]
        )
        
        line_labels = alt.Chart(line_df).mark_text(
            align='center', baseline='bottom', dy=-8, fontSize=9,
            color=COLORS['gross_profit_percent']
        ).encode(
            x=alt.X('month:N', sort=MONTH_ORDER),
            y=alt.Y('gp_percent:Q'),
            text=alt.Text('gp_percent:Q', format='.1f')
        )
        
        chart = alt.layer(bars + bar_labels, line + line_labels).resolve_scale(y='independent')
    
    return chart.properties(width=CHART_WIDTH, height=CHART_HEIGHT)


# =============================================================================
# CUMULATIVE DUAL CHART - Adapted from KPI center
# =============================================================================

def build_cumulative_dual_chart(monthly_df: pd.DataFrame) -> alt.Chart:
    """Build cumulative chart with Revenue + GP lines."""
    if monthly_df.empty:
        return empty_chart("No data")
    
    chart_df = monthly_df.copy()
    chart_df['month_order'] = chart_df['month'].map(
        {m: i for i, m in enumerate(MONTH_ORDER)}
    )
    chart_df = chart_df.sort_values('month_order')
    chart_df['cumulative_revenue'] = chart_df['revenue'].cumsum()
    chart_df['cumulative_gp'] = chart_df['gross_profit'].cumsum()
    
    line_data = []
    for _, row in chart_df.iterrows():
        line_data.append({
            'month': row['month'], 'month_order': row['month_order'],
            'metric': 'Cumulative Revenue', 'value': row['cumulative_revenue']
        })
        line_data.append({
            'month': row['month'], 'month_order': row['month_order'],
            'metric': 'Cumulative Gross Profit', 'value': row['cumulative_gp']
        })
    
    line_df = pd.DataFrame(line_data)
    
    color_scale = alt.Scale(
        domain=['Cumulative Revenue', 'Cumulative Gross Profit'],
        range=[COLORS['revenue'], COLORS['gross_profit']]
    )
    
    lines = alt.Chart(line_df).mark_line(
        strokeWidth=2, point=alt.OverlayMarkDef(size=50)
    ).encode(
        x=alt.X('month:N', sort=MONTH_ORDER, title='Month', axis=alt.Axis(labelAngle=0)),
        y=alt.Y('value:Q', title='Cumulative Amount (USD)', axis=alt.Axis(format='~s')),
        color=alt.Color('metric:N', scale=color_scale, legend=alt.Legend(title='Metric', orient='bottom')),
        tooltip=[
            alt.Tooltip('month:N', title='Month'),
            alt.Tooltip('metric:N', title='Metric'),
            alt.Tooltip('value:Q', title='Amount', format='$,.0f'),
        ]
    )
    
    labels = alt.Chart(line_df).mark_text(
        align='left', baseline='middle', dx=5, fontSize=9
    ).encode(
        x=alt.X('month:N', sort=MONTH_ORDER),
        y=alt.Y('value:Q'),
        text=alt.Text('value:Q', format=',.0f'),
        color=alt.Color('metric:N', scale=color_scale, legend=None)
    )
    
    return (lines + labels).properties(width=CHART_WIDTH, height=CHART_HEIGHT)


# =============================================================================
# YOY COMPARISON CHARTS - Adapted from KPI center
# =============================================================================

def build_yoy_comparison_chart(
    current_df: pd.DataFrame,
    previous_df: pd.DataFrame,
    metric: str = "Revenue",
    current_year: int = None,
    previous_year: int = None
) -> alt.Chart:
    """Build Year-over-Year comparison chart with grouped bars."""
    if current_df.empty and previous_df.empty:
        return empty_chart("No data")
    
    metric_col_map = {'Revenue': 'revenue', 'Gross Profit': 'gross_profit', 'GP1': 'gp1'}
    value_col = metric_col_map.get(metric, 'revenue')
    
    combined_data = []
    
    if not current_df.empty and value_col in current_df.columns:
        curr = current_df[['month', value_col]].copy()
        curr['year'] = str(current_year) if current_year else 'Current'
        curr['year_type'] = 'Current Year'
        curr['value'] = curr[value_col]
        combined_data.append(curr[['month', 'year', 'year_type', 'value']])
    
    if not previous_df.empty and value_col in previous_df.columns:
        prev = previous_df[['month', value_col]].copy()
        prev['year'] = str(previous_year) if previous_year else 'Previous'
        prev['year_type'] = 'Previous Year'
        prev['value'] = prev[value_col]
        combined_data.append(prev[['month', 'year', 'year_type', 'value']])
    
    if not combined_data:
        return empty_chart("No data")
    
    chart_df = pd.concat(combined_data, ignore_index=True)
    
    color_scale = alt.Scale(
        domain=['Current Year', 'Previous Year'],
        range=[COLORS['current_year'], COLORS['previous_year']]
    )
    
    chart = alt.Chart(chart_df).mark_bar(
        cornerRadiusTopLeft=2, cornerRadiusTopRight=2
    ).encode(
        x=alt.X('month:N', sort=MONTH_ORDER, title='Month', axis=alt.Axis(labelAngle=0)),
        y=alt.Y('value:Q', title=metric, axis=alt.Axis(format='~s')),
        color=alt.Color('year_type:N', scale=color_scale, legend=alt.Legend(title='Year', orient='bottom')),
        xOffset='year_type:N',
        tooltip=[
            alt.Tooltip('month:N', title='Month'),
            alt.Tooltip('year:N', title='Year'),
            alt.Tooltip('value:Q', title=metric, format='$,.0f')
        ]
    )
    
    labels = alt.Chart(chart_df).mark_text(
        align='center', baseline='bottom', dy=-5, fontSize=9
    ).encode(
        x=alt.X('month:N', sort=MONTH_ORDER),
        y=alt.Y('value:Q'),
        xOffset='year_type:N',
        text=alt.Text('value:Q', format=',.0f'),
        color=alt.value(COLORS['text_dark'])
    )
    
    return (chart + labels).properties(width=CHART_WIDTH, height=CHART_HEIGHT)


def build_yoy_cumulative_chart(
    current_df: pd.DataFrame,
    previous_df: pd.DataFrame,
    metric: str = "Revenue",
    current_year: int = None,
    previous_year: int = None
) -> alt.Chart:
    """Build YoY cumulative comparison chart."""
    if current_df.empty and previous_df.empty:
        return empty_chart("No data")
    
    metric_col_map = {'Revenue': 'revenue', 'Gross Profit': 'gross_profit', 'GP1': 'gp1'}
    value_col = metric_col_map.get(metric, 'revenue')
    
    line_data = []
    
    if not current_df.empty and value_col in current_df.columns:
        curr = current_df.copy()
        curr['month_order'] = curr['month'].map({m: i for i, m in enumerate(MONTH_ORDER)})
        curr = curr.sort_values('month_order')
        curr['cumulative'] = curr[value_col].cumsum()
        for _, row in curr.iterrows():
            line_data.append({
                'month': row['month'], 'month_order': row['month_order'],
                'year': 'Current Year', 'value': row['cumulative']
            })
    
    if not previous_df.empty and value_col in previous_df.columns:
        prev = previous_df.copy()
        prev['month_order'] = prev['month'].map({m: i for i, m in enumerate(MONTH_ORDER)})
        prev = prev.sort_values('month_order')
        prev['cumulative'] = prev[value_col].cumsum()
        for _, row in prev.iterrows():
            line_data.append({
                'month': row['month'], 'month_order': row['month_order'],
                'year': 'Previous Year', 'value': row['cumulative']
            })
    
    if not line_data:
        return empty_chart("No data")
    
    chart_df = pd.DataFrame(line_data)
    
    color_scale = alt.Scale(
        domain=['Current Year', 'Previous Year'],
        range=[COLORS['current_year'], COLORS['previous_year']]
    )
    
    chart = alt.Chart(chart_df).mark_line(
        strokeWidth=2, point=alt.OverlayMarkDef(size=50)
    ).encode(
        x=alt.X('month:N', sort=MONTH_ORDER, title='Month', axis=alt.Axis(labelAngle=0)),
        y=alt.Y('value:Q', title=f'Cumulative {metric}', axis=alt.Axis(format='~s')),
        color=alt.Color('year:N', scale=color_scale, legend=alt.Legend(title='Year', orient='bottom')),
        strokeDash=alt.condition(
            alt.datum.year == 'Previous Year',
            alt.value([5, 5]),
            alt.value([0])
        ),
        tooltip=[
            alt.Tooltip('month:N', title='Month'),
            alt.Tooltip('year:N', title='Year'),
            alt.Tooltip('value:Q', title=f'Cumulative {metric}', format='$,.0f')
        ]
    )
    
    labels = alt.Chart(chart_df).mark_text(
        align='left', baseline='middle', dx=5, fontSize=9
    ).encode(
        x=alt.X('month:N', sort=MONTH_ORDER),
        y=alt.Y('value:Q'),
        text=alt.Text('value:Q', format=',.0f'),
        color=alt.Color('year:N', scale=color_scale, legend=None)
    )
    
    return (chart + labels).properties(width=CHART_WIDTH, height=CHART_HEIGHT)
