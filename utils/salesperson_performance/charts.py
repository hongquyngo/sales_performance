# utils/salesperson_performance/charts.py
"""
Altair Chart Builders for Salesperson Performance

All visualization components using Altair:
- KPI summary cards (using st.metric)
- Monthly trend charts (bar + line)
- Cumulative charts
- Achievement comparison charts
- YoY comparison charts
- Top customers/brands Pareto charts
"""

import logging
from typing import Dict, Optional, List
import pandas as pd
import altair as alt
import streamlit as st

from .constants import COLORS, MONTH_ORDER, CHART_WIDTH, CHART_HEIGHT

logger = logging.getLogger(__name__)


class SalespersonCharts:
    """
    Chart builders for salesperson performance dashboard.
    
    All methods are static - can be called without instantiation.
    
    Usage:
        SalespersonCharts.render_kpi_cards(metrics, yoy_metrics, complex_kpis)
        chart = SalespersonCharts.build_monthly_trend_chart(monthly_df)
        st.altair_chart(chart, use_container_width=True)
    """
    
    # =========================================================================
    # KPI CARDS (Using st.metric)
    # =========================================================================
    
    @staticmethod
    def render_kpi_cards(
        metrics: Dict,
        yoy_metrics: Dict = None,
        complex_kpis: Dict = None,
        backlog_metrics: Dict = None,
        show_complex: bool = True,
        show_backlog: bool = True
    ):
        """
        Render KPI summary cards using Streamlit metrics.
        
        Args:
            metrics: Overview metrics dict
            yoy_metrics: YoY comparison metrics (optional)
            complex_kpis: Complex KPI metrics (optional)
            backlog_metrics: Backlog and forecast metrics (optional)
            show_complex: Whether to show complex KPI row
            show_backlog: Whether to show backlog/forecast row
        """
        # Row 1: Main Financial KPIs
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            delta = None
            if yoy_metrics and yoy_metrics.get('total_revenue_yoy') is not None:
                delta = f"{yoy_metrics['total_revenue_yoy']:+.1f}% YoY"
            
            st.metric(
                label="💰 Revenue",
                value=f"${metrics['total_revenue']:,.0f}",
                delta=delta
            )
        
        with col2:
            delta = None
            if yoy_metrics and yoy_metrics.get('total_gp_yoy') is not None:
                delta = f"{yoy_metrics['total_gp_yoy']:+.1f}% YoY"
            
            st.metric(
                label="📈 Gross Profit",
                value=f"${metrics['total_gp']:,.0f}",
                delta=delta
            )
        
        with col3:
            st.metric(
                label="🎯 GP1",
                value=f"${metrics['total_gp1']:,.0f}",
                delta=f"{metrics['gp1_percent']:.1f}% margin"
            )
        
        with col4:
            achievement = metrics.get('revenue_achievement')
            if achievement is not None:
                delta_color = "normal" if achievement >= 100 else "inverse"
                st.metric(
                    label="🏆 Achievement",
                    value=f"{achievement:.1f}%",
                    delta=f"vs ${metrics.get('revenue_target', 0):,.0f} target",
                    delta_color=delta_color
                )
            else:
                st.metric(
                    label="🏆 Achievement",
                    value="N/A",
                    delta="No target set"
                )
        
        # Row 2: Secondary metrics
        col5, col6, col7, col8 = st.columns(4)
        
        with col5:
            delta = None
            if yoy_metrics and yoy_metrics.get('total_customers_yoy') is not None:
                delta = f"{yoy_metrics['total_customers_yoy']:+.1f}% YoY"
            
            st.metric(
                label="👥 Customers",
                value=f"{metrics['total_customers']:,}",
                delta=delta
            )
        
        with col6:
            st.metric(
                label="🧾 Invoices",
                value=f"{metrics['total_invoices']:,}",
            )
        
        with col7:
            st.metric(
                label="📦 Orders",
                value=f"{metrics['total_orders']:,}",
            )
        
        with col8:
            st.metric(
                label="📊 GP %",
                value=f"{metrics['gp_percent']:.1f}%",
            )
        
        # Row 3: Backlog & Forecast (if provided and enabled)
        if show_backlog and backlog_metrics:
            st.divider()
            st.markdown("##### 📦 Backlog & Forecast")
            
            col_b1, col_b2, col_b3, col_b4, col_b5 = st.columns(5)
            
            with col_b1:
                st.metric(
                    label="📦 Total Backlog",
                    value=f"${backlog_metrics.get('total_backlog_revenue', 0):,.0f}",
                    delta=f"{backlog_metrics.get('backlog_orders', 0):,} orders",
                    delta_color="off"
                )
            
            with col_b2:
                coverage = backlog_metrics.get('backlog_coverage_percent')
                delta_str = f"{coverage:.0f}% of target" if coverage else None
                st.metric(
                    label="📅 In-Period Backlog",
                    value=f"${backlog_metrics.get('in_period_backlog_revenue', 0):,.0f}",
                    delta=delta_str,
                    delta_color="off"
                )
            
            with col_b3:
                st.metric(
                    label="✅ Current Invoiced",
                    value=f"${backlog_metrics.get('current_invoiced_revenue', 0):,.0f}",
                    help="Revenue already invoiced in period"
                )
            
            with col_b4:
                forecast_achievement = backlog_metrics.get('forecast_achievement_revenue')
                delta_str = f"{forecast_achievement:.0f}% of target" if forecast_achievement else None
                delta_color = "normal" if forecast_achievement and forecast_achievement >= 100 else "inverse"
                st.metric(
                    label="🔮 Forecast",
                    value=f"${backlog_metrics.get('forecast_revenue', 0):,.0f}",
                    delta=delta_str,
                    delta_color=delta_color if delta_str else "off",
                    help="Invoiced + In-Period Backlog"
                )
            
            with col_b5:
                gap = backlog_metrics.get('gap_revenue')
                gap_percent = backlog_metrics.get('gap_revenue_percent')
                
                if gap is not None:
                    # Positive gap = exceeding target, Negative = shortfall
                    if gap >= 0:
                        gap_label = "🟢 Surplus"
                        delta_color = "normal"
                    else:
                        gap_label = "🔴 GAP"
                        delta_color = "inverse"
                    
                    delta_str = f"{gap_percent:+.1f}%" if gap_percent else None
                    st.metric(
                        label=gap_label,
                        value=f"${gap:+,.0f}",
                        delta=delta_str,
                        delta_color=delta_color,
                        help="Forecast - Target"
                    )
                else:
                    st.metric(
                        label="⚠️ GAP",
                        value="N/A",
                        delta="No target",
                        delta_color="off"
                    )
        
        # Row 4: Complex KPIs (if provided and enabled)
        if show_complex and complex_kpis:
            st.divider()
            st.markdown("##### 🆕 New Business KPIs")
            
            col9, col10, col11 = st.columns(3)
            
            with col9:
                achievement = complex_kpis.get('new_customer_achievement')
                delta_str = f"{achievement:.0f}% of target" if achievement else None
                
                st.metric(
                    label="👥 New Customers",
                    value=f"{complex_kpis['new_customer_count']:.1f}",
                    delta=delta_str
                )
            
            with col10:
                achievement = complex_kpis.get('new_product_achievement')
                delta_str = f"{achievement:.0f}% of target" if achievement else None
                
                st.metric(
                    label="📦 New Products",
                    value=f"{complex_kpis['new_product_count']:.1f}",
                    delta=delta_str
                )
            
            with col11:
                achievement = complex_kpis.get('new_business_achievement')
                delta_str = f"{achievement:.0f}% of target" if achievement else None
                
                st.metric(
                    label="💼 New Business Revenue",
                    value=f"${complex_kpis['new_business_revenue']:,.0f}",
                    delta=delta_str
                )
    
    # =========================================================================
    # MONTHLY TREND CHART
    # =========================================================================
    
    @staticmethod
    def build_monthly_trend_chart(
        monthly_df: pd.DataFrame,
        show_gp1: bool = False,
        title: str = "📊 Monthly Revenue, Gross Profit & GP%"
    ) -> alt.Chart:
        """
        Build monthly trend chart with bars (Revenue, GP) and line (GP%).
        
        Args:
            monthly_df: Monthly summary data
            show_gp1: Whether to include GP1 in bars
            title: Chart title
            
        Returns:
            Altair chart
        """
        if monthly_df.empty:
            return SalespersonCharts._empty_chart("No data available")
        
        # Prepare data for bar chart
        value_vars = ['revenue', 'gross_profit']
        if show_gp1:
            value_vars.append('gp1')
        
        bar_data = monthly_df.melt(
            id_vars=['invoice_month'],
            value_vars=value_vars,
            var_name='Metric',
            value_name='Amount'
        )
        
        # Map metric names for display
        metric_map = {
            'revenue': 'Revenue',
            'gross_profit': 'Gross Profit',
            'gp1': 'GP1'
        }
        bar_data['Metric'] = bar_data['Metric'].map(metric_map)
        
        # Color scale
        domain = ['Revenue', 'Gross Profit']
        range_colors = [COLORS['revenue'], COLORS['gross_profit']]
        if show_gp1:
            domain.append('GP1')
            range_colors.append(COLORS['gp1'])
        
        color_scale = alt.Scale(domain=domain, range=range_colors)
        
        # Bar chart
        bars = alt.Chart(bar_data).mark_bar().encode(
            x=alt.X('invoice_month:N', sort=MONTH_ORDER, title='Month'),
            y=alt.Y('Amount:Q', title='Amount (USD)', axis=alt.Axis(format='~s')),
            color=alt.Color('Metric:N', scale=color_scale, legend=alt.Legend(orient='bottom')),
            xOffset='Metric:N',
            tooltip=[
                alt.Tooltip('invoice_month:N', title='Month'),
                alt.Tooltip('Metric:N', title='Metric'),
                alt.Tooltip('Amount:Q', title='Amount', format=',.0f')
            ]
        )
        
        # Value labels on bars
        bar_text = alt.Chart(bar_data).mark_text(
            align='center', baseline='bottom', dy=-5, fontSize=10
        ).encode(
            x=alt.X('invoice_month:N', sort=MONTH_ORDER),
            y=alt.Y('Amount:Q'),
            text=alt.Text('Amount:Q', format=',.0f'),
            xOffset='Metric:N',
            color=alt.value(COLORS['text_dark'])
        )
        
        # GP% line chart
        line = alt.Chart(monthly_df).mark_line(
            point=True,
            color=COLORS['gross_profit_percent'],
            strokeWidth=2
        ).encode(
            x=alt.X('invoice_month:N', sort=MONTH_ORDER),
            y=alt.Y('gp_percent:Q', title='GP %', axis=alt.Axis(format='.0f')),
            tooltip=[
                alt.Tooltip('invoice_month:N', title='Month'),
                alt.Tooltip('gp_percent:Q', title='GP %', format='.2f')
            ]
        )
        
        # GP% text labels
        line_text = alt.Chart(monthly_df).mark_text(
            align='center', baseline='bottom', dy=-8, fontSize=10,
            color=COLORS['gross_profit_percent']
        ).encode(
            x=alt.X('invoice_month:N', sort=MONTH_ORDER),
            y=alt.Y('gp_percent:Q'),
            text=alt.Text('gp_percent:Q', format='.1f')
        )
        
        # Combine with independent Y scales
        chart = alt.layer(bars, bar_text, line, line_text).resolve_scale(
            y='independent'
        ).properties(
            width=CHART_WIDTH,
            height=CHART_HEIGHT,
            title=title
        )
        
        return chart
    
    # =========================================================================
    # CUMULATIVE CHART
    # =========================================================================
    
    @staticmethod
    def build_cumulative_chart(
        monthly_df: pd.DataFrame,
        title: str = "📈 Cumulative Revenue & Gross Profit"
    ) -> alt.Chart:
        """
        Build cumulative revenue and GP chart.
        
        Args:
            monthly_df: Monthly summary with cumulative columns
            title: Chart title
            
        Returns:
            Altair chart
        """
        if monthly_df.empty:
            return SalespersonCharts._empty_chart("No data available")
        
        # Melt for line chart
        cumulative_data = monthly_df.melt(
            id_vars=['invoice_month'],
            value_vars=['cumulative_revenue', 'cumulative_gp'],
            var_name='Metric',
            value_name='Amount'
        )
        
        metric_map = {
            'cumulative_revenue': 'Cumulative Revenue',
            'cumulative_gp': 'Cumulative Gross Profit'
        }
        cumulative_data['Metric'] = cumulative_data['Metric'].map(metric_map)
        
        color_scale = alt.Scale(
            domain=['Cumulative Revenue', 'Cumulative Gross Profit'],
            range=[COLORS['revenue'], COLORS['gross_profit']]
        )
        
        # Line chart
        lines = alt.Chart(cumulative_data).mark_line(point=True, strokeWidth=2).encode(
            x=alt.X('invoice_month:N', sort=MONTH_ORDER, title='Month'),
            y=alt.Y('Amount:Q', title='Cumulative Amount (USD)', axis=alt.Axis(format='~s')),
            color=alt.Color('Metric:N', scale=color_scale, legend=alt.Legend(orient='bottom')),
            tooltip=[
                alt.Tooltip('invoice_month:N', title='Month'),
                alt.Tooltip('Metric:N', title='Metric'),
                alt.Tooltip('Amount:Q', title='Amount', format=',.0f')
            ]
        )
        
        # Value labels
        text = alt.Chart(cumulative_data).mark_text(
            align='center', baseline='bottom', dy=-8, fontSize=10
        ).encode(
            x=alt.X('invoice_month:N', sort=MONTH_ORDER),
            y=alt.Y('Amount:Q'),
            text=alt.Text('Amount:Q', format=',.0f'),
            color=alt.Color('Metric:N', scale=color_scale, legend=None)
        )
        
        chart = alt.layer(lines, text).properties(
            width=CHART_WIDTH,
            height=CHART_HEIGHT,
            title=title
        )
        
        return chart
    
    # =========================================================================
    # ACHIEVEMENT CHART (Actual vs Target)
    # =========================================================================
    
    @staticmethod
    def build_achievement_chart(
        summary_df: pd.DataFrame,
        metric: str = 'revenue',
        title: str = "🎯 Revenue Achievement by Salesperson"
    ) -> alt.Chart:
        """
        Build horizontal bar chart comparing actual vs target.
        
        Args:
            summary_df: Salesperson summary with achievement columns
            metric: 'revenue' or 'gross_profit'
            title: Chart title
            
        Returns:
            Altair chart
        """
        if summary_df.empty:
            return SalespersonCharts._empty_chart("No data available")
        
        # Prepare data
        df = summary_df.copy()
        
        if metric == 'revenue':
            actual_col = 'revenue'
            target_col = 'revenue_target'
            achievement_col = 'revenue_achievement'
        else:
            actual_col = 'gross_profit'
            target_col = 'gp_target'
            achievement_col = 'gp_achievement'
        
        # Ensure columns exist
        if actual_col not in df.columns:
            return SalespersonCharts._empty_chart("Data not available")
        
        df = df.sort_values(actual_col, ascending=True)
        
        # Determine color based on achievement
        if achievement_col in df.columns:
            df['color_flag'] = df[achievement_col] >= 100
        else:
            df['color_flag'] = True
        
        # Bar chart
        bars = alt.Chart(df).mark_bar().encode(
            y=alt.Y('sales_name:N', sort='-x', title=''),
            x=alt.X(f'{actual_col}:Q', title=f'{metric.replace("_", " ").title()} (USD)'),
            color=alt.condition(
                alt.datum.color_flag,
                alt.value(COLORS['achievement_good']),
                alt.value(COLORS['achievement_bad'])
            ),
            tooltip=[
                alt.Tooltip('sales_name:N', title='Salesperson'),
                alt.Tooltip(f'{actual_col}:Q', title='Actual', format=',.0f'),
                alt.Tooltip(f'{target_col}:Q', title='Target', format=',.0f') if target_col in df.columns else alt.value(''),
                alt.Tooltip(f'{achievement_col}:Q', title='Achievement %', format='.1f') if achievement_col in df.columns else alt.value('')
            ]
        )
        
        # Achievement % text
        if achievement_col in df.columns:
            text = alt.Chart(df).mark_text(
                align='left', dx=5, fontSize=11
            ).encode(
                y=alt.Y('sales_name:N', sort='-x'),
                x=alt.X(f'{actual_col}:Q'),
                text=alt.Text(f'{achievement_col}:Q', format='.0f'),
                color=alt.value(COLORS['text_dark'])
            )
            
            chart = alt.layer(bars, text)
        else:
            chart = bars
        
        chart = chart.properties(
            width=CHART_WIDTH,
            height=max(300, len(df) * 30),
            title=title
        )
        
        return chart
    
    # =========================================================================
    # YoY COMPARISON CHART
    # =========================================================================
    
    @staticmethod
    def build_yoy_comparison_chart(
        current_df: pd.DataFrame,
        previous_df: pd.DataFrame,
        metric: str = 'revenue',
        title: str = "📊 Year-over-Year Comparison"
    ) -> alt.Chart:
        """
        Build grouped bar chart comparing current vs previous year.
        
        Args:
            current_df: Current period monthly data
            previous_df: Previous year monthly data
            metric: Column name to compare
            title: Chart title
            
        Returns:
            Altair chart
        """
        metric_map = {
            'revenue': 'sales_by_split_usd',
            'gross_profit': 'gross_profit_by_split_usd',
            'gp1': 'gp1_by_split_usd'
        }
        
        col = metric_map.get(metric, metric)
        
        # Aggregate by month
        def agg_monthly(df, year_label):
            if df.empty:
                return pd.DataFrame()
            
            monthly = df.groupby('invoice_month')[col].sum().reset_index()
            monthly['Year'] = year_label
            monthly.columns = ['invoice_month', 'Amount', 'Year']
            return monthly
        
        current_monthly = agg_monthly(current_df, 'Current Year')
        previous_monthly = agg_monthly(previous_df, 'Previous Year')
        
        combined = pd.concat([current_monthly, previous_monthly], ignore_index=True)
        
        if combined.empty:
            return SalespersonCharts._empty_chart("No data available")
        
        # Chart
        chart = alt.Chart(combined).mark_bar().encode(
            x=alt.X('invoice_month:N', sort=MONTH_ORDER, title='Month'),
            y=alt.Y('Amount:Q', title='Amount (USD)', axis=alt.Axis(format='~s')),
            color=alt.Color('Year:N', scale=alt.Scale(
                domain=['Current Year', 'Previous Year'],
                range=[COLORS['current_year'], COLORS['previous_year']]
            ), legend=alt.Legend(orient='bottom')),
            xOffset='Year:N',
            tooltip=[
                alt.Tooltip('invoice_month:N', title='Month'),
                alt.Tooltip('Year:N', title='Year'),
                alt.Tooltip('Amount:Q', title='Amount', format=',.0f')
            ]
        ).properties(
            width=CHART_WIDTH,
            height=CHART_HEIGHT,
            title=title
        )
        
        return chart
    
    # =========================================================================
    # TOP CUSTOMERS/BRANDS PARETO CHART
    # =========================================================================
    
    @staticmethod
    def build_top_customers_chart(
        top_df: pd.DataFrame,
        title: str = "🏆 Top 80% Customers by Gross Profit"
    ) -> alt.Chart:
        """
        Build Pareto chart (bar + cumulative line) for top customers.
        
        Args:
            top_df: Top customers data with cumulative_percent
            title: Chart title
            
        Returns:
            Altair chart
        """
        if top_df.empty:
            return SalespersonCharts._empty_chart("No data available")
        
        df = top_df.copy()
        
        # Bar chart (Gross Profit)
        bars = alt.Chart(df).mark_bar().encode(
            x=alt.X('customer:N', sort='-y', title='Customer'),
            y=alt.Y('gross_profit:Q', title='Gross Profit (USD)', axis=alt.Axis(format='~s')),
            color=alt.value(COLORS['gross_profit']),
            tooltip=[
                alt.Tooltip('customer:N', title='Customer'),
                alt.Tooltip('gross_profit:Q', title='Gross Profit', format=',.0f'),
                alt.Tooltip('gp_percent_contribution:Q', title='% of Total', format='.2f')
            ]
        )
        
        # Bar text labels
        bar_text = alt.Chart(df).mark_text(
            align='center', baseline='bottom', dy=-5, fontSize=10
        ).encode(
            x=alt.X('customer:N', sort='-y'),
            y=alt.Y('gross_profit:Q'),
            text=alt.Text('gross_profit:Q', format=',.0f'),
            color=alt.value(COLORS['text_dark'])
        )
        
        # Cumulative % line
        line = alt.Chart(df).mark_line(
            point=True,
            color=COLORS['gross_profit_percent'],
            strokeWidth=2
        ).encode(
            x=alt.X('customer:N', sort='-y'),
            y=alt.Y('cumulative_percent:Q', title='Cumulative %', axis=alt.Axis(format='.0%')),
            tooltip=[
                alt.Tooltip('customer:N', title='Customer'),
                alt.Tooltip('cumulative_percent:Q', title='Cumulative %', format='.2%')
            ]
        )
        
        # Line text labels
        line_text = alt.Chart(df).mark_text(
            align='center', baseline='bottom', dy=-8, fontSize=10,
            color=COLORS['gross_profit_percent']
        ).encode(
            x=alt.X('customer:N', sort='-y'),
            y=alt.Y('cumulative_percent:Q'),
            text=alt.Text('cumulative_percent:Q', format='.1%')
        )
        
        # Combine with independent scales
        chart = alt.layer(bars, bar_text, line, line_text).resolve_scale(
            y='independent'
        ).properties(
            width=CHART_WIDTH,
            height=CHART_HEIGHT,
            title=title
        )
        
        return chart
    
    @staticmethod
    def build_top_brands_chart(
        top_df: pd.DataFrame,
        title: str = "🏆 Top 80% Brands by Gross Profit"
    ) -> alt.Chart:
        """
        Build Pareto chart for top brands.
        Same structure as top_customers_chart.
        """
        if top_df.empty:
            return SalespersonCharts._empty_chart("No data available")
        
        df = top_df.copy()
        
        # Bar chart
        bars = alt.Chart(df).mark_bar().encode(
            x=alt.X('brand:N', sort='-y', title='Brand'),
            y=alt.Y('gross_profit:Q', title='Gross Profit (USD)', axis=alt.Axis(format='~s')),
            color=alt.value(COLORS['gross_profit']),
            tooltip=[
                alt.Tooltip('brand:N', title='Brand'),
                alt.Tooltip('gross_profit:Q', title='Gross Profit', format=',.0f'),
                alt.Tooltip('gp_percent_contribution:Q', title='% of Total', format='.2f')
            ]
        )
        
        bar_text = alt.Chart(df).mark_text(
            align='center', baseline='bottom', dy=-5, fontSize=10
        ).encode(
            x=alt.X('brand:N', sort='-y'),
            y=alt.Y('gross_profit:Q'),
            text=alt.Text('gross_profit:Q', format=',.0f'),
            color=alt.value(COLORS['text_dark'])
        )
        
        # Cumulative line
        line = alt.Chart(df).mark_line(
            point=True,
            color=COLORS['gross_profit_percent'],
            strokeWidth=2
        ).encode(
            x=alt.X('brand:N', sort='-y'),
            y=alt.Y('cumulative_percent:Q', title='Cumulative %', axis=alt.Axis(format='.0%')),
            tooltip=[
                alt.Tooltip('brand:N', title='Brand'),
                alt.Tooltip('cumulative_percent:Q', title='Cumulative %', format='.2%')
            ]
        )
        
        line_text = alt.Chart(df).mark_text(
            align='center', baseline='bottom', dy=-8, fontSize=10,
            color=COLORS['gross_profit_percent']
        ).encode(
            x=alt.X('brand:N', sort='-y'),
            y=alt.Y('cumulative_percent:Q'),
            text=alt.Text('cumulative_percent:Q', format='.1%')
        )
        
        chart = alt.layer(bars, bar_text, line, line_text).resolve_scale(
            y='independent'
        ).properties(
            width=CHART_WIDTH,
            height=CHART_HEIGHT,
            title=title
        )
        
        return chart
    
    # =========================================================================
    # HELPER METHODS
    # =========================================================================
    
    @staticmethod
    def _empty_chart(message: str = "No data available") -> alt.Chart:
        """Create an empty chart with a message."""
        return alt.Chart(pd.DataFrame({'note': [message]})).mark_text(
            text=message,
            fontSize=16,
            color=COLORS['text_light']
        ).properties(
            width=CHART_WIDTH,
            height=200
        )
    
    # =========================================================================
    # BACKLOG & FORECAST CHARTS
    # =========================================================================
    
    @staticmethod
    def build_forecast_waterfall_chart(
        backlog_metrics: Dict,
        title: str = "🔮 Revenue Forecast vs Target"
    ) -> alt.Chart:
        """
        Build a waterfall-style chart showing Invoiced + Backlog = Forecast vs Target.
        
        Args:
            backlog_metrics: Dict with backlog metrics
            title: Chart title
            
        Returns:
            Altair chart
        """
        if not backlog_metrics:
            return SalespersonCharts._empty_chart("No backlog data")
        
        # Prepare data for stacked bar
        data = pd.DataFrame([
            {
                'category': 'Performance',
                'component': '✅ Invoiced',
                'value': backlog_metrics.get('current_invoiced_revenue', 0),
                'order': 1
            },
            {
                'category': 'Performance',
                'component': '📅 In-Period Backlog',
                'value': backlog_metrics.get('in_period_backlog_revenue', 0),
                'order': 2
            },
            {
                'category': 'Target',
                'component': '🎯 Target',
                'value': backlog_metrics.get('revenue_target', 0) or 0,
                'order': 1
            }
        ])
        
        # Color scale
        color_scale = alt.Scale(
            domain=['✅ Invoiced', '📅 In-Period Backlog', '🎯 Target'],
            range=[COLORS['gross_profit'], COLORS['new_customer'], COLORS['target']]
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
                alt.Tooltip('value:Q', title='Amount', format=',.0f')
            ]
        )
        
        # Add forecast line
        forecast_value = backlog_metrics.get('forecast_revenue', 0)
        forecast_line = alt.Chart(pd.DataFrame({'y': [forecast_value]})).mark_rule(
            color=COLORS['gross_profit_percent'],
            strokeWidth=2,
            strokeDash=[5, 5]
        ).encode(
            y='y:Q'
        )
        
        # Add forecast label
        forecast_text = alt.Chart(pd.DataFrame({
            'x': ['Target'],
            'y': [forecast_value],
            'label': [f'Forecast: ${forecast_value:,.0f}']
        })).mark_text(
            align='left',
            dx=35,
            fontSize=12,
            fontWeight='bold',
            color=COLORS['gross_profit_percent']
        ).encode(
            x='x:N',
            y='y:Q',
            text='label:N'
        )
        
        chart = alt.layer(bars, forecast_line, forecast_text).properties(
            width=400,
            height=350,
            title=title
        )
        
        return chart
    
    @staticmethod
    def build_backlog_by_month_chart(
        monthly_df: pd.DataFrame,
        invoiced_monthly_df: pd.DataFrame = None,
        title: str = "📅 Backlog by ETD Month"
    ) -> alt.Chart:
        """
        Build bar chart showing backlog distribution by ETD month.
        Optionally overlay with invoiced data for comparison.
        
        Args:
            monthly_df: Backlog by month data
            invoiced_monthly_df: Optional invoiced by month for comparison
            title: Chart title
            
        Returns:
            Altair chart
        """
        if monthly_df.empty:
            return SalespersonCharts._empty_chart("No backlog data")
        
        df = monthly_df.copy()
        
        # Ensure month column exists
        if 'month' not in df.columns and 'etd_month' in df.columns:
            df = df.rename(columns={'etd_month': 'month'})
        
        # Bar chart for backlog
        bars = alt.Chart(df).mark_bar(color=COLORS['new_customer']).encode(
            x=alt.X('month:N', sort=MONTH_ORDER, title='ETD Month'),
            y=alt.Y('backlog_revenue:Q', title='Backlog (USD)', axis=alt.Axis(format='~s')),
            tooltip=[
                alt.Tooltip('month:N', title='Month'),
                alt.Tooltip('backlog_revenue:Q', title='Backlog', format=',.0f'),
                alt.Tooltip('order_count:Q', title='Orders')
            ]
        )
        
        # Text labels
        text = alt.Chart(df).mark_text(
            align='center',
            baseline='bottom',
            dy=-5,
            fontSize=10,
            color=COLORS['text_dark']
        ).encode(
            x=alt.X('month:N', sort=MONTH_ORDER),
            y=alt.Y('backlog_revenue:Q'),
            text=alt.Text('backlog_revenue:Q', format=',.0f')
        )
        
        chart = alt.layer(bars, text).properties(
            width=CHART_WIDTH,
            height=300,
            title=title
        )
        
        return chart
    
    @staticmethod
    def build_gap_analysis_chart(
        backlog_metrics: Dict,
        title: str = "📊 Target vs Forecast Analysis"
    ) -> alt.Chart:
        """
        Build a bullet/progress chart showing current progress, forecast, and target.
        
        Args:
            backlog_metrics: Dict with backlog metrics
            title: Chart title
            
        Returns:
            Altair chart
        """
        if not backlog_metrics:
            return SalespersonCharts._empty_chart("No data available")
        
        target = backlog_metrics.get('revenue_target', 0) or 0
        invoiced = backlog_metrics.get('current_invoiced_revenue', 0)
        forecast = backlog_metrics.get('forecast_revenue', 0)
        
        if target == 0:
            return SalespersonCharts._empty_chart("No target set")
        
        # Calculate percentages
        invoiced_pct = (invoiced / target) * 100
        forecast_pct = (forecast / target) * 100
        
        data = pd.DataFrame([
            {'metric': 'Revenue', 'type': 'Invoiced', 'value': invoiced, 'percent': invoiced_pct},
            {'metric': 'Revenue', 'type': 'Forecast', 'value': forecast, 'percent': forecast_pct},
            {'metric': 'Revenue', 'type': 'Target', 'value': target, 'percent': 100},
        ])
        
        # Base bar (target as background)
        base = alt.Chart(data[data['type'] == 'Target']).mark_bar(
            color='#e0e0e0',
            size=40
        ).encode(
            x=alt.X('value:Q', title='Amount (USD)', axis=alt.Axis(format='~s')),
            y=alt.Y('metric:N', title='')
        )
        
        # Forecast bar
        forecast_bar = alt.Chart(data[data['type'] == 'Forecast']).mark_bar(
            color=COLORS['new_customer'],
            size=25
        ).encode(
            x=alt.X('value:Q'),
            y=alt.Y('metric:N'),
            tooltip=[
                alt.Tooltip('type:N', title='Type'),
                alt.Tooltip('value:Q', title='Amount', format=',.0f'),
                alt.Tooltip('percent:Q', title='% of Target', format='.1f')
            ]
        )
        
        # Invoiced bar (innermost)
        invoiced_bar = alt.Chart(data[data['type'] == 'Invoiced']).mark_bar(
            color=COLORS['gross_profit'],
            size=15
        ).encode(
            x=alt.X('value:Q'),
            y=alt.Y('metric:N'),
            tooltip=[
                alt.Tooltip('type:N', title='Type'),
                alt.Tooltip('value:Q', title='Amount', format=',.0f'),
                alt.Tooltip('percent:Q', title='% of Target', format='.1f')
            ]
        )
        
        # Target line
        target_rule = alt.Chart(data[data['type'] == 'Target']).mark_tick(
            color=COLORS['target'],
            thickness=3,
            size=50
        ).encode(
            x=alt.X('value:Q'),
            y=alt.Y('metric:N')
        )
        
        chart = alt.layer(base, forecast_bar, invoiced_bar, target_rule).properties(
            width=CHART_WIDTH,
            height=150,
            title=title
        )
        
        return chart