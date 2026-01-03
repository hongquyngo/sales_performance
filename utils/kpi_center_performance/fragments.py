# utils/kpi_center_performance/fragments.py
"""
Streamlit Fragments for KPI Center Performance

v4.3.0 - Refactored into separate modules per tab:
- overview/fragments.py: Monthly trend, YoY comparison, export
- sales_detail/fragments.py: Sales list, pivot analysis
- analysis/fragments.py: Top performers
- backlog/fragments.py: Backlog list, by ETD, risk analysis
- kpi_targets/fragments.py: KPI assignments, progress, ranking
- common/fragments.py: Shared helper functions

This file re-exports all fragments for backward compatibility.
"""

import logging
from typing import Dict, Optional, List
from datetime import datetime
import pandas as pd
import streamlit as st

logger = logging.getLogger(__name__)

# =============================================================================
# OVERVIEW TAB FRAGMENTS
# =============================================================================
from .overview.fragments import (
    monthly_trend_fragment,
    yoy_comparison_fragment,
    export_report_fragment,
)

# =============================================================================
# SALES DETAIL TAB FRAGMENTS
# =============================================================================
from .sales_detail.fragments import (
    sales_detail_tab_fragment,
    sales_detail_fragment,
    pivot_analysis_fragment,
)

# =============================================================================
# ANALYSIS TAB FRAGMENTS
# =============================================================================
from .analysis.fragments import (
    top_performers_fragment,
)

# =============================================================================
# BACKLOG TAB FRAGMENTS
# =============================================================================
from .backlog.fragments import (
    backlog_tab_fragment,
    backlog_list_fragment,
    backlog_by_etd_fragment,
    backlog_risk_analysis_fragment,
)

# =============================================================================
# KPI & TARGETS TAB FRAGMENTS
# =============================================================================
from .kpi_targets.fragments import (
    kpi_assignments_fragment,
    kpi_progress_fragment,
    kpi_center_ranking_fragment,
)

# =============================================================================
# COMMON HELPER FUNCTIONS (for backward compatibility)
# =============================================================================
from .common.fragments import (
    clean_dataframe_for_display as _clean_dataframe_for_display,
    prepare_monthly_summary as _prepare_monthly_summary,
    format_product_display,
    format_oc_po,
    format_currency,
    get_rank_display,
)

# Backward compatibility aliases (private functions)
def _clean_dataframe_for_display(df: pd.DataFrame) -> pd.DataFrame:
    """Deprecated: Use common.fragments.clean_dataframe_for_display()"""
    from .common.fragments import clean_dataframe_for_display
    return clean_dataframe_for_display(df)

def _prepare_monthly_summary(sales_df: pd.DataFrame, debug_label: str = "") -> pd.DataFrame:
    """Deprecated: Use common.fragments.prepare_monthly_summary()"""
    from .common.fragments import prepare_monthly_summary
    return prepare_monthly_summary(sales_df, debug_label)


# =============================================================================
# __all__ - Public API
# =============================================================================
__all__ = [
    # Overview tab
    'monthly_trend_fragment',
    'yoy_comparison_fragment',
    'export_report_fragment',
    
    # Sales Detail tab
    'sales_detail_tab_fragment',
    'sales_detail_fragment',
    'pivot_analysis_fragment',
    
    # Analysis tab
    'top_performers_fragment',
    
    # Backlog tab
    'backlog_tab_fragment',
    'backlog_list_fragment',
    'backlog_by_etd_fragment',
    'backlog_risk_analysis_fragment',
    
    # KPI & Targets tab
    'kpi_assignments_fragment',
    'kpi_progress_fragment',
    'kpi_center_ranking_fragment',
    
    # Common utilities
    'format_product_display',
    'format_oc_po',
    'format_currency',
    'get_rank_display',
]
