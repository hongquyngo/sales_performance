# utils/kpi_center_performance/charts.py
"""
Altair Chart Builders for KPI Center Performance

VERSION: 4.3.0 (Modular Refactor)
CHANGELOG:
- v4.3.0: REFACTORED to modular structure by tab folders
          - Imports re-exported from submodules for backward compatibility
          - Original file split into:
            - common/charts.py: empty_chart, convert_pipeline_to_backlog_metrics
            - overview/charts.py: render_kpi_cards, trend charts, YoY charts
            - analysis/charts.py: Pareto, top performers
            - backlog/charts.py: Forecast waterfall, gap analysis, backlog charts
- v3.3.2: UPDATED Overall Achievement tooltip in render_kpi_cards()
- v2.7.0: UPDATED Popovers to merge rows with same entity
- v2.6.0: REFACTORED NEW BUSINESS section
- v2.5.0: ADDED Multi-Year Comparison charts
- v2.4.0: SYNCED UI with Salesperson Performance page

BACKWARD COMPATIBILITY:
Old import still works:
    from .charts import KPICenterCharts
    KPICenterCharts.render_kpi_cards(...)
    
New import (recommended):
    from .overview.charts import render_kpi_cards
    render_kpi_cards(...)
"""

import logging
from typing import Dict, Optional, List
import pandas as pd
import altair as alt
import streamlit as st

# Re-export from submodules for backward compatibility
from .common.charts import (
    empty_chart,
    convert_pipeline_to_backlog_metrics,
)

from .overview.charts import (
    render_kpi_cards,
    build_monthly_trend_dual_chart,
    build_cumulative_dual_chart,
    build_yoy_comparison_chart,
    build_yoy_cumulative_chart,
    build_monthly_trend_chart,
    build_multi_year_monthly_chart,
    build_multi_year_cumulative_chart,
    build_multi_year_summary_table,
)

from .analysis.charts import (
    build_pareto_chart,
    build_top_performers_chart,
)

from .backlog.charts import (
    build_forecast_waterfall_chart,
    build_gap_analysis_chart,
    build_backlog_by_month_chart,
    build_backlog_by_month_chart_multiyear,
    build_backlog_by_month_stacked,
)

logger = logging.getLogger(__name__)


class KPICenterCharts:
    """
    Chart builders for KPI Center performance dashboard.
    
    DEPRECATED: This class is provided for backward compatibility only.
    Please use the modular imports instead:
    
        from .overview.charts import render_kpi_cards, build_monthly_trend_dual_chart
        from .analysis.charts import build_pareto_chart
        from .backlog.charts import build_forecast_waterfall_chart
    """
    
    # =========================================================================
    # KPI CARDS - Delegated to overview/charts.py
    # =========================================================================
    
    @staticmethod
    def render_kpi_cards(
        metrics: Dict,
        yoy_metrics: Dict = None,
        complex_kpis: Dict = None,
        backlog_metrics: Dict = None,
        overall_achievement: Dict = None,
        show_complex: bool = True,
        show_backlog: bool = True,
        new_customers_df: pd.DataFrame = None,
        new_products_df: pd.DataFrame = None,
        new_business_df: pd.DataFrame = None,
        new_business_detail_df: pd.DataFrame = None
    ):
        """Render KPI summary cards. Delegated to overview.charts.render_kpi_cards()"""
        return render_kpi_cards(
            metrics=metrics,
            yoy_metrics=yoy_metrics,
            complex_kpis=complex_kpis,
            backlog_metrics=backlog_metrics,
            overall_achievement=overall_achievement,
            show_complex=show_complex,
            show_backlog=show_backlog,
            new_customers_df=new_customers_df,
            new_products_df=new_products_df,
            new_business_df=new_business_df,
            new_business_detail_df=new_business_detail_df
        )
    
    # =========================================================================
    # BACKLOG & FORECAST CHARTS - Delegated to backlog/charts.py
    # =========================================================================
    
    @staticmethod
    def build_forecast_waterfall_chart(
        backlog_metrics: Dict,
        metric: str = 'revenue',
        title: str = ""
    ) -> alt.Chart:
        """Build forecast waterfall chart. Delegated to backlog.charts.build_forecast_waterfall_chart()"""
        return build_forecast_waterfall_chart(backlog_metrics, metric, title)
    
    @staticmethod
    def build_gap_analysis_chart(
        backlog_metrics: Dict,
        metrics_to_show: List[str] = ['revenue'],
        title: str = ""
    ) -> alt.Chart:
        """Build gap analysis chart. Delegated to backlog.charts.build_gap_analysis_chart()"""
        return build_gap_analysis_chart(backlog_metrics, metrics_to_show, title)
    
    # =========================================================================
    # MONTHLY TREND CHARTS - Delegated to overview/charts.py
    # =========================================================================
    
    @staticmethod
    def build_monthly_trend_dual_chart(
        monthly_df: pd.DataFrame,
        show_gp_percent_line: bool = True
    ) -> alt.Chart:
        """Build monthly trend dual chart. Delegated to overview.charts.build_monthly_trend_dual_chart()"""
        return build_monthly_trend_dual_chart(monthly_df, show_gp_percent_line)
    
    @staticmethod
    def build_cumulative_dual_chart(
        monthly_df: pd.DataFrame
    ) -> alt.Chart:
        """Build cumulative dual chart. Delegated to overview.charts.build_cumulative_dual_chart()"""
        return build_cumulative_dual_chart(monthly_df)
    
    # =========================================================================
    # YOY COMPARISON CHARTS - Delegated to overview/charts.py
    # =========================================================================
    
    @staticmethod
    def build_yoy_comparison_chart(
        current_df: pd.DataFrame,
        previous_df: pd.DataFrame,
        metric: str = "Revenue",
        current_year: int = None,
        previous_year: int = None
    ) -> alt.Chart:
        """Build YoY comparison chart. Delegated to overview.charts.build_yoy_comparison_chart()"""
        return build_yoy_comparison_chart(current_df, previous_df, metric, current_year, previous_year)
    
    @staticmethod
    def build_yoy_cumulative_chart(
        current_df: pd.DataFrame,
        previous_df: pd.DataFrame,
        metric: str = "Revenue",
        current_year: int = None,
        previous_year: int = None
    ) -> alt.Chart:
        """Build YoY cumulative chart. Delegated to overview.charts.build_yoy_cumulative_chart()"""
        return build_yoy_cumulative_chart(current_df, previous_df, metric, current_year, previous_year)
    
    # =========================================================================
    # MONTHLY TREND CHART (Simple version)
    # =========================================================================
    
    @staticmethod
    def build_monthly_trend_chart(
        monthly_df: pd.DataFrame,
        metric: str = "Revenue",
        show_target: bool = True,
        target_value: float = None
    ) -> alt.Chart:
        """Build simple monthly trend chart. Delegated to overview.charts.build_monthly_trend_chart()"""
        return build_monthly_trend_chart(monthly_df, metric, show_target, target_value)
    
    # =========================================================================
    # UTILITY METHODS - Delegated to common/charts.py
    # =========================================================================
    
    @staticmethod
    def convert_pipeline_to_backlog_metrics(pipeline_metrics: Dict) -> Dict:
        """Convert pipeline metrics format. Delegated to common.charts.convert_pipeline_to_backlog_metrics()"""
        return convert_pipeline_to_backlog_metrics(pipeline_metrics)
    
    # =========================================================================
    # PARETO / TOP PERFORMERS CHARTS - Delegated to analysis/charts.py
    # =========================================================================
    
    @staticmethod
    def build_pareto_chart(
        data_df: pd.DataFrame,
        value_col: str,
        label_col: str,
        title: str = "Pareto Analysis",
        show_cumulative_line: bool = True,
        highlight_80_percent: bool = True
    ) -> alt.Chart:
        """Build Pareto chart. Delegated to analysis.charts.build_pareto_chart()"""
        return build_pareto_chart(data_df, value_col, label_col, title, show_cumulative_line, highlight_80_percent)
    
    @staticmethod
    def build_top_performers_chart(
        data_df: pd.DataFrame,
        value_col: str,
        label_col: str,
        top_n: int = 10,
        title: str = "Top Performers",
        show_percent: bool = True
    ) -> alt.Chart:
        """Build top performers chart. Delegated to analysis.charts.build_top_performers_chart()"""
        return build_top_performers_chart(data_df, value_col, label_col, top_n, title, show_percent)
    
    # =========================================================================
    # MULTI-YEAR COMPARISON CHARTS - Delegated to overview/charts.py
    # =========================================================================
    
    @staticmethod
    def build_multi_year_monthly_chart(
        sales_df: pd.DataFrame,
        years: List[int],
        metric: str = 'revenue',
        title: str = ""
    ) -> alt.Chart:
        """Build multi-year monthly chart. Delegated to overview.charts.build_multi_year_monthly_chart()"""
        return build_multi_year_monthly_chart(sales_df, years, metric, title)
    
    @staticmethod
    def build_multi_year_cumulative_chart(
        sales_df: pd.DataFrame,
        years: List[int],
        metric: str = 'revenue',
        title: str = ""
    ) -> alt.Chart:
        """Build multi-year cumulative chart. Delegated to overview.charts.build_multi_year_cumulative_chart()"""
        return build_multi_year_cumulative_chart(sales_df, years, metric, title)
    
    @staticmethod
    def build_multi_year_summary_table(
        sales_df: pd.DataFrame,
        years: List[int],
        metric: str = 'revenue'
    ) -> pd.DataFrame:
        """Build multi-year summary table. Delegated to overview.charts.build_multi_year_summary_table()"""
        return build_multi_year_summary_table(sales_df, years, metric)
    
    @staticmethod
    def _empty_chart(message: str = "No data") -> alt.Chart:
        """Return empty chart. Delegated to common.charts.empty_chart()"""
        return empty_chart(message)
    
    # =========================================================================
    # BACKLOG CHARTS - Delegated to backlog/charts.py
    # =========================================================================
    
    @staticmethod
    def build_backlog_by_month_chart(
        monthly_df: pd.DataFrame,
        revenue_col: str = 'backlog_revenue',
        gp_col: str = 'backlog_gp',
        month_col: str = 'etd_month',
        title: str = "Backlog by ETD Month"
    ) -> alt.Chart:
        """Build backlog by month chart. Delegated to backlog.charts.build_backlog_by_month_chart()"""
        return build_backlog_by_month_chart(monthly_df, revenue_col, gp_col, month_col, title)
    
    @staticmethod
    def build_backlog_by_month_chart_multiyear(
        monthly_df: pd.DataFrame,
        revenue_col: str = 'backlog_revenue',
        title: str = "Backlog Timeline"
    ) -> alt.Chart:
        """Build multi-year backlog chart. Delegated to backlog.charts.build_backlog_by_month_chart_multiyear()"""
        return build_backlog_by_month_chart_multiyear(monthly_df, revenue_col, title)
    
    @staticmethod
    def build_backlog_by_month_stacked(
        monthly_df: pd.DataFrame,
        revenue_col: str = 'backlog_revenue',
        title: str = "Backlog by Month (Stacked)"
    ) -> alt.Chart:
        """Build stacked backlog chart. Delegated to backlog.charts.build_backlog_by_month_stacked()"""
        return build_backlog_by_month_stacked(monthly_df, revenue_col, title)


# Export all for "from .charts import *"
__all__ = [
    'KPICenterCharts',
    # Common
    'empty_chart',
    'convert_pipeline_to_backlog_metrics',
    # Overview
    'render_kpi_cards',
    'build_monthly_trend_dual_chart',
    'build_cumulative_dual_chart',
    'build_yoy_comparison_chart',
    'build_yoy_cumulative_chart',
    'build_monthly_trend_chart',
    'build_multi_year_monthly_chart',
    'build_multi_year_cumulative_chart',
    'build_multi_year_summary_table',
    # Analysis
    'build_pareto_chart',
    'build_top_performers_chart',
    # Backlog
    'build_forecast_waterfall_chart',
    'build_gap_analysis_chart',
    'build_backlog_by_month_chart',
    'build_backlog_by_month_chart_multiyear',
    'build_backlog_by_month_stacked',
]
