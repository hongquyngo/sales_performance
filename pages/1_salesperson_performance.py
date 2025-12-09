# pages/1_salesperson_performance.py
"""
Salesperson Performance Dashboard

Track sales performance by salesperson with:
- Role-based access control (sales see self, managers see team, admin sees all)
- KPI summary cards (Revenue, GP, GP1, Achievement)
- Complex KPIs (New Customers, New Products, New Business Revenue)
- Monthly trend visualization
- Target comparison
- YoY analysis
- Formatted Excel export

Version: 1.0.0
"""

import streamlit as st
from datetime import datetime, date
import logging

# Shared utilities
from utils.auth import AuthManager
from utils.db import check_db_connection

# Page-specific module
from utils.salesperson_performance import (
    AccessControl,
    SalespersonQueries,
    SalespersonMetrics,
    SalespersonFilters,
    SalespersonCharts,
    SalespersonExport,
    PERIOD_TYPES,
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# =============================================================================
# PAGE CONFIGURATION
# =============================================================================

st.set_page_config(
    page_title="Salesperson Performance",
    page_icon="👤",
    layout="wide",
    initial_sidebar_state="expanded"
)

# =============================================================================
# AUTHENTICATION CHECK
# =============================================================================

auth = AuthManager()

if not auth.check_session():
    st.warning("⚠️ Please login to access this page")
    st.info("Go to the main page to login")
    st.stop()

# =============================================================================
# DATABASE CONNECTION CHECK
# =============================================================================

db_connected, db_error = check_db_connection()

if not db_connected:
    st.error(f"❌ Database connection failed: {db_error}")
    st.info("Please check your network connection or VPN")
    st.stop()

# =============================================================================
# INITIALIZE COMPONENTS
# =============================================================================

# Access Control
access = AccessControl(
    user_role=st.session_state.get('user_role', 'viewer'),
    employee_id=st.session_state.get('employee_id')
)

# Data queries
queries = SalespersonQueries(access)

# Filters UI
filters_ui = SalespersonFilters(access)

# =============================================================================
# SIDEBAR FILTERS
# =============================================================================

# Get lookup data for filters
salesperson_options = queries.get_salesperson_options()
entity_options = queries.get_entity_options()
available_years = queries.get_available_years()

# Render filters and get selected values
filter_values = filters_ui.render_all_filters(
    salesperson_df=salesperson_options,
    entity_df=entity_options,
    available_years=available_years
)

# Validate filters
is_valid, error_msg = filters_ui.validate_filters(filter_values)
if not is_valid:
    st.error(f"⚠️ {error_msg}")
    st.stop()

# =============================================================================
# LOAD DATA
# =============================================================================

@st.cache_data(ttl=1800, show_spinner="Loading sales data...")
def load_all_data(start_date, end_date, employee_ids, entity_ids, year):
    """Load all required data with caching."""
    q = SalespersonQueries(AccessControl(
        st.session_state.get('user_role', 'viewer'),
        st.session_state.get('employee_id')
    ))
    
    # Main sales data
    sales_df = q.get_sales_data(
        start_date=start_date,
        end_date=end_date,
        employee_ids=employee_ids,
        entity_ids=entity_ids if entity_ids else None
    )
    
    # KPI targets
    targets_df = q.get_kpi_targets(year=year, employee_ids=employee_ids)
    
    # Complex KPIs
    new_customers_df = q.get_new_customers(start_date, end_date, employee_ids)
    new_products_df = q.get_new_products(start_date, end_date, employee_ids)
    new_business_df = q.get_new_business_revenue(start_date, end_date, employee_ids)
    
    return sales_df, targets_df, new_customers_df, new_products_df, new_business_df


# Load data based on filters
sales_df, targets_df, new_customers_df, new_products_df, new_business_df = load_all_data(
    start_date=filter_values['start_date'],
    end_date=filter_values['end_date'],
    employee_ids=tuple(filter_values['employee_ids']),
    entity_ids=tuple(filter_values['entity_ids']) if filter_values['entity_ids'] else None,
    year=filter_values['year']
)

# Check if we have data
if sales_df.empty:
    st.warning("📭 No data found for the selected filters")
    st.info("Try adjusting your filter criteria")
    st.stop()

# =============================================================================
# CALCULATE METRICS
# =============================================================================

metrics_calc = SalespersonMetrics(sales_df, targets_df)

# Overview metrics
overview_metrics = metrics_calc.calculate_overview_metrics(
    period_type=filter_values['period_type'],
    year=filter_values['year']
)

# Complex KPIs
complex_kpis = metrics_calc.calculate_complex_kpis(
    new_customers_df=new_customers_df,
    new_products_df=new_products_df,
    new_business_df=new_business_df
)

# YoY comparison (if enabled)
yoy_metrics = None
previous_sales_df = None

if filter_values['compare_yoy']:
    previous_sales_df = queries.get_previous_year_data(
        start_date=filter_values['start_date'],
        end_date=filter_values['end_date'],
        employee_ids=filter_values['employee_ids'],
        entity_ids=filter_values['entity_ids'] if filter_values['entity_ids'] else None
    )
    
    if not previous_sales_df.empty:
        prev_metrics_calc = SalespersonMetrics(previous_sales_df, None)
        prev_overview = prev_metrics_calc.calculate_overview_metrics(
            period_type=filter_values['period_type'],
            year=filter_values['year'] - 1
        )
        yoy_metrics = metrics_calc.calculate_yoy_comparison(overview_metrics, prev_overview)

# =============================================================================
# PAGE HEADER
# =============================================================================

st.title("👤 Salesperson Performance")

# Filter summary
filter_summary = filters_ui.get_filter_summary(filter_values)
st.caption(f"📊 {filter_summary}")

st.divider()

# =============================================================================
# KPI CARDS
# =============================================================================

SalespersonCharts.render_kpi_cards(
    metrics=overview_metrics,
    yoy_metrics=yoy_metrics,
    complex_kpis=complex_kpis,
    show_complex=True
)

st.divider()

# =============================================================================
# CHARTS SECTION
# =============================================================================

# Prepare monthly data
monthly_summary = metrics_calc.prepare_monthly_summary()

# Two-column layout for charts
col1, col2 = st.columns(2)

with col1:
    st.subheader("📊 Monthly Trend")
    monthly_chart = SalespersonCharts.build_monthly_trend_chart(
        monthly_df=monthly_summary,
        show_gp1=False,
        title=""
    )
    st.altair_chart(monthly_chart, use_container_width=True)

with col2:
    st.subheader("📈 Cumulative Performance")
    cumulative_chart = SalespersonCharts.build_cumulative_chart(
        monthly_df=monthly_summary,
        title=""
    )
    st.altair_chart(cumulative_chart, use_container_width=True)

st.divider()

# =============================================================================
# YoY COMPARISON (if enabled)
# =============================================================================

if filter_values['compare_yoy'] and previous_sales_df is not None and not previous_sales_df.empty:
    st.subheader("📊 Year-over-Year Comparison")
    
    metric_col_map = {
        'Revenue': 'revenue',
        'Gross Profit': 'gross_profit',
        'GP1': 'gp1'
    }
    selected_metric = metric_col_map.get(filter_values['metric_view'], 'revenue')
    
    yoy_chart = SalespersonCharts.build_yoy_comparison_chart(
        current_df=sales_df,
        previous_df=previous_sales_df,
        metric=selected_metric,
        title=f"{filter_values['metric_view']} - Current Year vs Previous Year"
    )
    st.altair_chart(yoy_chart, use_container_width=True)
    
    st.divider()

# =============================================================================
# ACHIEVEMENT BY SALESPERSON
# =============================================================================

st.subheader("🎯 Achievement by Salesperson")

# Get salesperson summary
salesperson_summary = metrics_calc.aggregate_by_salesperson()

if not salesperson_summary.empty and len(salesperson_summary) > 1:
    # Show achievement chart only if multiple salespeople
    achievement_chart = SalespersonCharts.build_achievement_chart(
        summary_df=salesperson_summary,
        metric='revenue',
        title=""
    )
    st.altair_chart(achievement_chart, use_container_width=True)

st.divider()

# =============================================================================
# TOP CUSTOMERS & BRANDS
# =============================================================================

col3, col4 = st.columns(2)

with col3:
    st.subheader("🏆 Top Customers by GP")
    top_customers = metrics_calc.prepare_top_customers_by_gp(top_percent=0.8)
    
    if not top_customers.empty:
        top_customers_chart = SalespersonCharts.build_top_customers_chart(
            top_df=top_customers,
            title=""
        )
        st.altair_chart(top_customers_chart, use_container_width=True)
    else:
        st.info("No customer data available")

with col4:
    st.subheader("🏆 Top Brands by GP")
    top_brands = metrics_calc.prepare_top_brands_by_gp(top_percent=0.8)
    
    if not top_brands.empty:
        top_brands_chart = SalespersonCharts.build_top_brands_chart(
            top_df=top_brands,
            title=""
        )
        st.altair_chart(top_brands_chart, use_container_width=True)
    else:
        st.info("No brand data available")

st.divider()

# =============================================================================
# DETAIL TABLE
# =============================================================================

st.subheader("📋 Performance Details")

if not salesperson_summary.empty:
    # Format for display
    display_df = salesperson_summary.copy()
    
    # Select and rename columns
    display_columns = {
        'sales_name': 'Salesperson',
        'revenue': 'Revenue',
        'gross_profit': 'Gross Profit',
        'gp1': 'GP1',
        'gp_percent': 'GP %',
        'customers': 'Customers',
        'invoices': 'Invoices',
    }
    
    if 'revenue_achievement' in display_df.columns:
        display_columns['revenue_achievement'] = 'Achievement %'
    
    # Filter to available columns
    available_display_cols = [c for c in display_columns.keys() if c in display_df.columns]
    display_df = display_df[available_display_cols].rename(columns=display_columns)
    
    # Format numeric columns
    st.dataframe(
        display_df.style.format({
            'Revenue': '${:,.0f}',
            'Gross Profit': '${:,.0f}',
            'GP1': '${:,.0f}',
            'GP %': '{:.1f}%',
            'Achievement %': '{:.1f}%' if 'Achievement %' in display_df.columns else None,
        }),
        use_container_width=True,
        hide_index=True
    )
else:
    st.info("No detail data available")

# =============================================================================
# EXPORT SECTION
# =============================================================================

st.divider()

col_export, col_spacer = st.columns([1, 3])

with col_export:
    if st.button("📥 Export to Excel", use_container_width=True):
        with st.spinner("Generating report..."):
            exporter = SalespersonExport()
            excel_bytes = exporter.create_report(
                summary_df=salesperson_summary,
                monthly_df=monthly_summary,
                metrics=overview_metrics,
                filters=filter_values,
                complex_kpis=complex_kpis,
                yoy_metrics=yoy_metrics,
                detail_df=sales_df
            )
            
            st.download_button(
                label="⬇️ Download Report",
                data=excel_bytes,
                file_name=f"salesperson_performance_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )

# =============================================================================
# FOOTER
# =============================================================================

st.divider()
st.caption(
    f"Generated by Prostech BI Dashboard | "
    f"User: {st.session_state.get('user_fullname', 'Unknown')} | "
    f"Access: {access.get_access_level().title()}"
)
