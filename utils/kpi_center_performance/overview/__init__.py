# utils/kpi_center_performance/overview/__init__.py
"""
Overview tab fragments and charts for KPI Center Performance.

VERSION: 4.4.0
CHANGELOG:
- v4.4.0: Removed dead code exports (build_monthly_trend_chart, build_multi_year_summary_table)
"""

from .fragments import (
    monthly_trend_fragment,
    yoy_comparison_fragment,
    export_report_fragment,
)

from .charts import (
    render_kpi_cards,
    build_monthly_trend_dual_chart,
    build_cumulative_dual_chart,
    build_yoy_comparison_chart,
    build_yoy_cumulative_chart,
    build_multi_year_monthly_chart,
    build_multi_year_cumulative_chart,
)

__all__ = [
    # Fragments
    'monthly_trend_fragment',
    'yoy_comparison_fragment',
    'export_report_fragment',
    # Charts
    'render_kpi_cards',
    'build_monthly_trend_dual_chart',
    'build_cumulative_dual_chart',
    'build_yoy_comparison_chart',
    'build_yoy_cumulative_chart',
    'build_multi_year_monthly_chart',
    'build_multi_year_cumulative_chart',
]