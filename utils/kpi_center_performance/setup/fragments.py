# utils/kpi_center_performance/setup/fragments.py
"""
UI Fragments for Setup Tab - KPI Center Performance

Handles all Streamlit UI components for Setup tab:
- Split Rules section
- Hierarchy section  
- (Future) KPI Assignments section
- (Future) Validation Dashboard

VERSION: 1.0.0
CHANGELOG:
- v1.0.0: Initial extraction from main page
          - setup_tab_fragment() - Main entry point
          - split_rules_section() - KPI Split Rules display
          - hierarchy_section() - Hierarchy view
"""

import streamlit as st
import pandas as pd
from typing import Dict, List, Optional, Any

from .queries import SetupQueries


# =============================================================================
# MAIN SETUP TAB FRAGMENT
# =============================================================================

@st.fragment
def setup_tab_fragment(
    kpi_center_ids: List[int] = None,
    active_filters: Dict = None
):
    """
    Main fragment for Setup tab.
    
    Args:
        kpi_center_ids: List of selected KPI Center IDs
        active_filters: Dict of active filters from sidebar
    """
    st.subheader("⚙️ KPI Center Configuration")
    
    # Initialize queries
    setup_queries = SetupQueries()
    
    # Split Rules Section
    split_rules_section(
        setup_queries=setup_queries,
        kpi_center_ids=kpi_center_ids
    )
    
    st.divider()
    
    # Hierarchy Section
    hierarchy_section(
        setup_queries=setup_queries
    )


# =============================================================================
# SPLIT RULES SECTION
# =============================================================================

@st.fragment
def split_rules_section(
    setup_queries: SetupQueries,
    kpi_center_ids: List[int] = None
):
    """
    Display KPI Center Split Rules with filtering.
    
    Args:
        setup_queries: SetupQueries instance
        kpi_center_ids: List of KPI Center IDs to filter
    """
    st.markdown("### 📋 KPI Center Split Assignments")
    
    # Get split data
    kpi_split_df = setup_queries.get_kpi_split_data(
        kpi_center_ids=kpi_center_ids,
        approval_filter='approved'
    )
    
    if kpi_split_df.empty:
        st.info("No split assignments found for selected KPI Centers")
        return
    
    # Filters row
    col1, col2 = st.columns(2)
    
    with col1:
        customers = ['All'] + sorted(kpi_split_df['customer_name'].dropna().unique().tolist())
        selected_customer = st.selectbox(
            "Filter by Customer",
            customers,
            key="setup_customer_filter"
        )
    
    with col2:
        search = st.text_input(
            "Search Product",
            placeholder="Product name or code...",
            key="setup_product_search"
        )
    
    # Apply filters
    filtered_split = kpi_split_df.copy()
    
    if selected_customer != 'All':
        filtered_split = filtered_split[filtered_split['customer_name'] == selected_customer]
    
    if search:
        mask = (
            filtered_split['product_pn'].fillna('').str.lower().str.contains(search.lower()) |
            filtered_split['pt_code'].fillna('').str.lower().str.contains(search.lower())
        )
        filtered_split = filtered_split[mask]
    
    st.caption(f"Showing {len(filtered_split):,} split assignments")
    
    # Display columns
    display_cols = [
        'kpi_center_name', 'customer_name', 'product_pn', 'brand',
        'split_percentage', 'effective_period', 'kpi_split_status'
    ]
    display_cols = [c for c in display_cols if c in filtered_split.columns]
    
    # Data table
    st.dataframe(
        filtered_split[display_cols].head(500),
        hide_index=True,
        column_config={
            'kpi_center_name': 'KPI Center',
            'customer_name': 'Customer',
            'product_pn': 'Product',
            'brand': 'Brand',
            'split_percentage': st.column_config.NumberColumn('Split %'),
            'effective_period': 'Period',
            'kpi_split_status': 'Status',
        },
        use_container_width=True
    )


# =============================================================================
# HIERARCHY SECTION
# =============================================================================

@st.fragment  
def hierarchy_section(
    setup_queries: SetupQueries
):
    """
    Display KPI Center Hierarchy.
    
    Args:
        setup_queries: SetupQueries instance
    """
    st.markdown("### 🌳 KPI Center Hierarchy")
    
    # Get hierarchy data with stats
    hierarchy_df = setup_queries.get_kpi_center_hierarchy(include_stats=True)
    
    if hierarchy_df.empty:
        st.info("No hierarchy data available")
        return
    
    # Display columns based on what's available
    display_cols = ['kpi_center_id', 'kpi_center_name', 'kpi_type', 'parent_center_id', 'level']
    
    # Add stat columns if available
    if 'children_count' in hierarchy_df.columns:
        display_cols.append('children_count')
    if 'split_count' in hierarchy_df.columns:
        display_cols.append('split_count')
    if 'assignment_count' in hierarchy_df.columns:
        display_cols.append('assignment_count')
    
    display_cols = [c for c in display_cols if c in hierarchy_df.columns]
    
    st.dataframe(
        hierarchy_df[display_cols],
        hide_index=True,
        column_config={
            'kpi_center_id': 'ID',
            'kpi_center_name': 'KPI Center',
            'kpi_type': 'Type',
            'parent_center_id': 'Parent ID',
            'level': 'Level',
            'children_count': st.column_config.NumberColumn('Children'),
            'split_count': st.column_config.NumberColumn('Split Rules'),
            'assignment_count': st.column_config.NumberColumn('Assignments'),
        },
        use_container_width=True
    )


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def format_status_badge(status: str) -> str:
    """Format status as colored badge."""
    status_map = {
        'ok': '✅ OK',
        'incomplete_split': '⚠️ Incomplete',
        'over_100_split': '🔴 Over 100%'
    }
    return status_map.get(status, status)
