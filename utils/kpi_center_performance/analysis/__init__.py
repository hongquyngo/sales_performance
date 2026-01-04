# utils/kpi_center_performance/analysis/__init__.py
"""Analysis tab module for KPI Center Performance. VERSION: 6.2.0"""

from .fragments import analysis_tab_fragment
from .charts import build_pareto_chart, build_growth_comparison_chart

__all__ = ['analysis_tab_fragment', 'build_pareto_chart', 'build_growth_comparison_chart']