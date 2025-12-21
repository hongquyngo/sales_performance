# pages/2_🎯_KPI_Center_Performance.py
"""
KPI Center Performance Dashboard

A comprehensive dashboard for tracking KPI Center performance metrics.
Features:
- Revenue, GP, GP1 tracking with targets
- Complex KPIs (New Customers, Products, Business Revenue)
- Pipeline & Forecast with gap analysis
- YoY comparison
- Parent-Child KPI Center rollup
- Excel export

Access: admin, GM, MD, sales_manager only

VERSION: 1.0.0
"""

import logging
from datetime import date, datetime
import pandas as pd
import streamlit as st

# Page config
st.set_page_config(
    page_title="KPI Center Performance",
    page_icon="🎯",
    layout="wide"
)

# Imports
from utils.auth import AuthManager
from utils.kpi_center_performance import (
    AccessControl,
    KPICenterQueries,
    KPICenterMetrics,
    KPICenterFilters,
    KPICenterCharts,
    KPICenterExport,
    analyze_period,
    ALLOWED_ROLES,
    # Fragments
    monthly_trend_fragment,
    yoy_comparison_fragment,
    sales_detail_fragment,
    pivot_analysis_fragment,
    backlog_list_fragment,
    kpi_center_ranking_fragment,
    export_report_fragment,
)

logger = logging.getLogger(__name__)


# =============================================================================
# AUTHENTICATION & ACCESS CONTROL
# =============================================================================

def check_access():
    """Check authentication and page access."""
    auth = AuthManager()
    
    if not auth.check_session():
        st.warning("⚠️ Please login to access this page")
        st.stop()
    
    user_role = st.session_state.get('user_role', '')
    access = AccessControl(user_role)
    
    if not access.can_access_page():
        st.error(access.get_denied_message())
        st.stop()
    
    return access


# =============================================================================
# DATA LOADING
# =============================================================================

@st.cache_data(ttl=1800)
def load_lookup_data():
    """Load lookup data for filters."""
    from utils.db import get_db_engine
    from sqlalchemy import text
    
    engine = get_db_engine()
    
    # KPI Center list
    kpi_center_query = """
        SELECT DISTINCT
            kc.id AS kpi_center_id,
            kc.name AS kpi_center_name,
            kc.type AS kpi_type,
            kc.parent_center_id,
            kc.description
        FROM kpi_centers kc
        WHERE kc.delete_flag = 0
        ORDER BY kc.type, kc.name
    """
    kpi_center_df = pd.read_sql(text(kpi_center_query), engine)
    
    # Entity list
    entity_query = """
        SELECT DISTINCT
            legal_entity_id AS entity_id,
            legal_entity AS entity_name
        FROM unified_sales_by_kpi_center_view
        WHERE legal_entity_id IS NOT NULL
        ORDER BY legal_entity
    """
    entity_df = pd.read_sql(text(entity_query), engine)
    
    # Available years
    years_query = """
        SELECT DISTINCT CAST(invoice_year AS SIGNED) AS year
        FROM unified_sales_by_kpi_center_view
        WHERE invoice_year IS NOT NULL
        ORDER BY invoice_year DESC
    """
    years_df = pd.read_sql(text(years_query), engine)
    available_years = years_df['year'].tolist() if not years_df.empty else [datetime.now().year]
    
    return kpi_center_df, entity_df, available_years


def load_data(queries: KPICenterQueries, filter_values: dict):
    """Load all required data based on filters."""
    start_date = filter_values['start_date']
    end_date = filter_values['end_date']
    kpi_center_ids = filter_values.get('kpi_center_ids', [])
    entity_ids = filter_values.get('entity_ids', [])
    year = filter_values['year']
    
    # Sales data
    sales_df = queries.get_sales_data(
        start_date=start_date,
        end_date=end_date,
        kpi_center_ids=kpi_center_ids,
        entity_ids=entity_ids if entity_ids else None
    )
    
    # Exclude internal if requested
    if filter_values.get('exclude_internal_revenue', True) and not sales_df.empty:
        if 'customer_type' in sales_df.columns:
            sales_df = sales_df[sales_df['customer_type'] != 'Internal']
    
    # KPI Targets
    targets_df = queries.get_kpi_targets(year=year, kpi_center_ids=kpi_center_ids)
    
    # Backlog data
    backlog_summary_df = queries.get_backlog_data(
        kpi_center_ids=kpi_center_ids,
        entity_ids=entity_ids if entity_ids else None
    )
    
    backlog_in_period_df = queries.get_backlog_in_period(
        start_date=start_date,
        end_date=end_date,
        kpi_center_ids=kpi_center_ids,
        entity_ids=entity_ids if entity_ids else None
    )
    
    backlog_detail_df = queries.get_backlog_detail(
        kpi_center_ids=kpi_center_ids,
        entity_ids=entity_ids if entity_ids else None
    )
    
    backlog_by_month_df = queries.get_backlog_by_month(
        kpi_center_ids=kpi_center_ids,
        entity_ids=entity_ids if entity_ids else None
    )
    
    # Complex KPIs
    new_customers_df = queries.get_new_customers(
        start_date=start_date,
        end_date=end_date,
        kpi_center_ids=kpi_center_ids,
        entity_ids=entity_ids if entity_ids else None
    )
    
    new_products_df = queries.get_new_products(
        start_date=start_date,
        end_date=end_date,
        kpi_center_ids=kpi_center_ids,
        entity_ids=entity_ids if entity_ids else None
    )
    
    new_business_df = queries.get_new_business_revenue(
        start_date=start_date,
        end_date=end_date,
        kpi_center_ids=kpi_center_ids,
        entity_ids=entity_ids if entity_ids else None
    )
    
    return {
        'sales_df': sales_df,
        'targets_df': targets_df,
        'backlog_summary_df': backlog_summary_df,
        'backlog_in_period_df': backlog_in_period_df,
        'backlog_detail_df': backlog_detail_df,
        'backlog_by_month_df': backlog_by_month_df,
        'new_customers_df': new_customers_df,
        'new_products_df': new_products_df,
        'new_business_df': new_business_df,
    }


def load_yoy_data(queries: KPICenterQueries, filter_values: dict):
    """Load previous year data for YoY comparison."""
    start_date = filter_values['start_date']
    end_date = filter_values['end_date']
    kpi_center_ids = filter_values.get('kpi_center_ids', [])
    entity_ids = filter_values.get('entity_ids', [])
    
    # Previous year same period
    prev_start = date(start_date.year - 1, start_date.month, start_date.day)
    prev_end = date(end_date.year - 1, end_date.month, min(end_date.day, 28))
    
    prev_sales_df = queries.get_sales_data(
        start_date=prev_start,
        end_date=prev_end,
        kpi_center_ids=kpi_center_ids,
        entity_ids=entity_ids if entity_ids else None
    )
    
    # Exclude internal if requested
    if filter_values.get('exclude_internal_revenue', True) and not prev_sales_df.empty:
        if 'customer_type' in prev_sales_df.columns:
            prev_sales_df = prev_sales_df[prev_sales_df['customer_type'] != 'Internal']
    
    return prev_sales_df


# =============================================================================
# MAIN PAGE
# =============================================================================

def main():
    """Main page function."""
    
    # Check access
    access = check_access()
    
    # Page header
    st.title("🎯 KPI Center Performance")
    st.caption(f"Logged in as: {st.session_state.get('user_fullname', 'User')} ({st.session_state.get('user_role', '')})")
    
    # Load lookup data
    try:
        kpi_center_df, entity_df, available_years = load_lookup_data()
    except Exception as e:
        st.error(f"Failed to load lookup data: {e}")
        logger.error(f"Lookup data error: {e}")
        st.stop()
    
    # Initialize queries and filters
    queries = KPICenterQueries(access)
    filters = KPICenterFilters(access)
    
    # Render sidebar filters
    filter_values = filters.render_sidebar_filters(
        kpi_center_df=kpi_center_df,
        entity_df=entity_df,
        available_years=available_years
    )
    
    # Validate filters
    is_valid, error_msg = filters.validate_filters(filter_values)
    if not is_valid:
        st.error(f"⚠️ Filter error: {error_msg}")
        st.stop()
    
    # Load data
    with st.spinner("Loading data..."):
        try:
            data = load_data(queries, filter_values)
        except Exception as e:
            st.error(f"Failed to load data: {e}")
            logger.error(f"Data loading error: {e}")
            st.stop()
    
    sales_df = data['sales_df']
    targets_df = data['targets_df']
    
    if sales_df.empty:
        st.warning("No data found for the selected filters. Try adjusting your selection.")
        st.stop()
    
    # Initialize metrics calculator
    metrics_calc = KPICenterMetrics(sales_df, targets_df)
    
    # Calculate metrics
    overview_metrics = metrics_calc.calculate_overview_metrics(
        period_type=filter_values['period_type'],
        year=filter_values['year'],
        start_date=filter_values['start_date'],
        end_date=filter_values['end_date']
    )
    
    # Complex KPIs summary
    complex_kpis = {
        'num_new_customers': data['new_customers_df']['num_new_customers'].sum() if not data['new_customers_df'].empty else 0,
        'num_new_products': data['new_products_df']['num_new_products'].sum() if not data['new_products_df'].empty else 0,
        'new_business_revenue': data['new_business_df']['new_business_revenue'].sum() if not data['new_business_df'].empty else 0,
    }
    
    # Pipeline & Forecast
    pipeline_metrics = metrics_calc.calculate_pipeline_forecast_metrics(
        total_backlog_df=data['backlog_summary_df'],
        in_period_backlog_df=data['backlog_in_period_df'],
        period_type=filter_values['period_type'],
        year=filter_values['year'],
        start_date=filter_values['start_date'],
        end_date=filter_values['end_date']
    )
    
    # Overall KPI Achievement
    overall_achievement = metrics_calc.calculate_overall_kpi_achievement(
        period_type=filter_values['period_type'],
        year=filter_values['year'],
        start_date=filter_values['start_date'],
        end_date=filter_values['end_date']
    )
    
    # YoY metrics (if enabled)
    yoy_metrics = None
    if filter_values.get('show_yoy', True):
        prev_sales_df = load_yoy_data(queries, filter_values)
        yoy_metrics = metrics_calc.calculate_yoy_metrics(sales_df, prev_sales_df)
    
    # Monthly summary
    monthly_df = metrics_calc.prepare_monthly_summary()
    
    # KPI Center summary
    kpi_center_summary_df = metrics_calc.aggregate_by_kpi_center()
    
    # Period analysis
    period_info = analyze_period(filter_values)
    
    # ==========================================================================
    # TABS
    # ==========================================================================
    
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📊 Overview",
        "📋 Sales Detail",
        "📦 Backlog",
        "🎯 KPI & Targets",
        "⚙️ Setup"
    ])
    
    # ==========================================================================
    # TAB 1: OVERVIEW
    # ==========================================================================
    
    with tab1:
        # KPI Cards
        KPICenterCharts.render_kpi_cards(
            metrics=overview_metrics,
            yoy_metrics=yoy_metrics,
            complex_kpis=complex_kpis,
            overall_achievement=overall_achievement
        )
        
        # Pipeline & Forecast
        KPICenterCharts.render_pipeline_forecast_section(
            pipeline_metrics=pipeline_metrics,
            show_forecast=period_info.get('show_backlog', True)
        )
        
        st.divider()
        
        # Monthly Trend (Fragment)
        st.subheader("📈 Monthly Trend")
        monthly_trend_fragment(
            sales_df=sales_df,
            filter_values=filter_values
        )
        
        # YoY Comparison (if enabled)
        if filter_values.get('show_yoy', True):
            st.divider()
            st.subheader("📊 Year-over-Year Comparison")
            yoy_comparison_fragment(
                queries=queries,
                filter_values=filter_values,
                current_year=filter_values['year']
            )
        
        # Export section
        st.divider()
        export_report_fragment(
            metrics=overview_metrics,
            complex_kpis=complex_kpis,
            pipeline_metrics=pipeline_metrics,
            filter_values=filter_values,
            yoy_metrics=yoy_metrics,
            kpi_center_summary_df=kpi_center_summary_df,
            monthly_df=monthly_df,
            sales_detail_df=sales_df,
            backlog_summary_df=data['backlog_summary_df'],
            backlog_detail_df=data['backlog_detail_df'],
            backlog_by_month_df=data['backlog_by_month_df']
        )
    
    # ==========================================================================
    # TAB 2: SALES DETAIL
    # ==========================================================================
    
    with tab2:
        sales_detail_fragment(
            sales_df=sales_df,
            filter_values=filter_values
        )
        
        st.divider()
        
        pivot_analysis_fragment(sales_df=sales_df)
    
    # ==========================================================================
    # TAB 3: BACKLOG
    # ==========================================================================
    
    with tab3:
        # Backlog summary cards
        backlog_metrics = KPICenterCharts.convert_pipeline_to_backlog_metrics(pipeline_metrics)
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric(
                label="Total Backlog",
                value=f"${backlog_metrics.get('total_backlog_revenue', 0):,.0f}",
                help="All uninvoiced orders"
            )
        
        with col2:
            st.metric(
                label="Total Backlog GP",
                value=f"${backlog_metrics.get('total_backlog_gp', 0):,.0f}"
            )
        
        with col3:
            st.metric(
                label="In-Period Backlog",
                value=f"${backlog_metrics.get('in_period_backlog_revenue', 0):,.0f}",
                help="Backlog with ETD in selected period"
            )
        
        with col4:
            st.metric(
                label="Backlog Orders",
                value=f"{backlog_metrics.get('backlog_orders', 0):,}"
            )
        
        st.divider()
        
        # Backlog detail list
        backlog_list_fragment(
            backlog_df=data['backlog_detail_df'],
            filter_values=filter_values
        )
        
        # Backlog by ETD month
        if not data['backlog_by_month_df'].empty:
            st.divider()
            st.subheader("📅 Backlog by ETD Month")
            
            display_df = data['backlog_by_month_df'].copy()
            st.dataframe(
                display_df,
                hide_index=True,
                column_config={
                    'etd_year': 'Year',
                    'etd_month': 'Month',
                    'backlog_orders': 'Orders',
                    'backlog_usd': st.column_config.NumberColumn('Backlog', format="$%,.0f"),
                    'backlog_gp_usd': st.column_config.NumberColumn('Backlog GP', format="$%,.0f"),
                },
                use_container_width=True
            )
    
    # ==========================================================================
    # TAB 4: KPI & TARGETS
    # ==========================================================================
    
    with tab4:
        st.subheader("🎯 KPI Assignments")
        
        if targets_df.empty:
            st.info("No KPI targets assigned for selected KPI Centers and year")
        else:
            # Group by KPI Center
            for kpi_center_id in targets_df['kpi_center_id'].unique():
                kc_targets = targets_df[targets_df['kpi_center_id'] == kpi_center_id]
                kc_name = kc_targets['kpi_center_name'].iloc[0]
                
                with st.expander(f"📊 {kc_name}", expanded=True):
                    display_cols = ['kpi_name', 'annual_target_value', 'weight_numeric', 'unit_of_measure']
                    display_cols = [c for c in display_cols if c in kc_targets.columns]
                    
                    st.dataframe(
                        kc_targets[display_cols],
                        hide_index=True,
                        column_config={
                            'kpi_name': 'KPI',
                            'annual_target_value': 'Annual Target',
                            'weight_numeric': st.column_config.NumberColumn('Weight %'),
                            'unit_of_measure': 'Unit',
                        }
                    )
        
        st.divider()
        
        # KPI Center Ranking
        st.subheader("🏆 KPI Center Ranking")
        kpi_center_ranking_fragment(
            ranking_df=kpi_center_summary_df,
            show_targets=not targets_df.empty
        )
    
    # ==========================================================================
    # TAB 5: SETUP
    # ==========================================================================
    
    with tab5:
        st.subheader("⚙️ KPI Center Configuration")
        
        # KPI Split assignments
        st.markdown("### 📋 KPI Center Split Assignments")
        
        kpi_split_df = queries.get_kpi_split_data(
            kpi_center_ids=filter_values.get('kpi_center_ids', [])
        )
        
        if kpi_split_df.empty:
            st.info("No split assignments found for selected KPI Centers")
        else:
            # Filter options
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
            
            display_cols = ['kpi_center_name', 'customer_name', 'product_pn', 'brand', 
                          'split_percentage', 'effective_period', 'kpi_split_status']
            display_cols = [c for c in display_cols if c in filtered_split.columns]
            
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
        
        # KPI Center Hierarchy
        st.divider()
        st.markdown("### 🌳 KPI Center Hierarchy")
        
        hierarchy_df = queries.get_kpi_center_hierarchy()
        
        if hierarchy_df.empty:
            st.info("No hierarchy data available")
        else:
            st.dataframe(
                hierarchy_df,
                hide_index=True,
                column_config={
                    'kpi_center_id': 'ID',
                    'kpi_center_name': 'KPI Center',
                    'kpi_type': 'Type',
                    'parent_center_id': 'Parent ID',
                    'level': 'Level',
                }
            )


# =============================================================================
# RUN
# =============================================================================

if __name__ == "__main__":
    main()
else:
    main()
