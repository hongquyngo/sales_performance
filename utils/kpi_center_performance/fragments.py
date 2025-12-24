# utils/kpi_center_performance/fragments.py
"""
Streamlit Fragments for KPI Center Performance

VERSION: 2.4.0
CHANGELOG:
- v2.4.0: SYNCED UI with Salesperson Performance page:
          - monthly_trend_fragment: 2 charts side-by-side (Monthly Trend + Cumulative)
            with Customer/Brand/Product Excl filters
          - yoy_comparison_fragment: Tabs (Revenue/GP/GP1), summary metrics,
            2 charts (Monthly Comparison + Cumulative)
          - All filters now have Excl checkbox like SP page
- v2.3.0: Phase 3 - Pareto Analysis
- v2.2.0: Phase 2 enhancements
"""

import logging
from typing import Dict, Optional, List
import pandas as pd
import streamlit as st

from .charts import KPICenterCharts
from .constants import MONTH_ORDER

logger = logging.getLogger(__name__)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def _clean_dataframe_for_display(df: pd.DataFrame) -> pd.DataFrame:
    """Clean dataframe for display."""
    if df.empty:
        return df
    
    df = df.copy()
    
    date_cols = ['inv_date', 'oc_date', 'etd', 'first_sale_date']
    for col in date_cols:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors='coerce')
    
    str_cols = df.select_dtypes(include=['object']).columns
    df[str_cols] = df[str_cols].fillna('')
    
    return df


def _prepare_monthly_summary(sales_df: pd.DataFrame) -> pd.DataFrame:
    """Prepare monthly summary from sales data."""
    if sales_df.empty:
        return pd.DataFrame()
    
    df = sales_df.copy()
    
    # Ensure invoice_month column
    if 'invoice_month' not in df.columns:
        if 'inv_date' in df.columns:
            df['inv_date'] = pd.to_datetime(df['inv_date'], errors='coerce')
            df['invoice_month'] = df['inv_date'].dt.strftime('%b')
        else:
            return pd.DataFrame()
    
    # Aggregate by month
    monthly = df.groupby('invoice_month').agg({
        'sales_by_kpi_center_usd': 'sum',
        'gross_profit_by_kpi_center_usd': 'sum',
        'gp1_by_kpi_center_usd': 'sum' if 'gp1_by_kpi_center_usd' in df.columns else 'first',
        'inv_number': pd.Series.nunique,
        'customer_id': pd.Series.nunique
    }).reset_index()
    
    monthly.columns = ['month', 'revenue', 'gross_profit', 'gp1', 'orders', 'customers']
    
    # Add GP%
    monthly['gp_percent'] = (monthly['gross_profit'] / monthly['revenue'] * 100).fillna(0).round(1)
    
    # Sort by month order
    monthly['month_order'] = monthly['month'].map({m: i for i, m in enumerate(MONTH_ORDER)})
    monthly = monthly.sort_values('month_order')
    
    return monthly


# =============================================================================
# MONTHLY TREND FRAGMENT - UPDATED v2.4.0 to match SP page
# =============================================================================

@st.fragment
def monthly_trend_fragment(
    sales_df: pd.DataFrame,
    filter_values: Dict = None,
    targets_df: pd.DataFrame = None,
    fragment_key: str = "kpc_trend"
):
    """
    Monthly trend chart with Customer/Brand/Product Excl filters.
    SYNCED with Salesperson page (Image 1 & 2).
    
    Shows:
    - Monthly Trend: Revenue + GP bars with GP% line
    - Cumulative Performance: Cumulative Revenue + GP lines
    """
    if sales_df.empty:
        st.info("No sales data for trend analysis")
        return
    
    # Header with Help button
    col_header, col_help = st.columns([6, 1])
    with col_header:
        st.subheader("📊 Monthly Trend & Cumulative")
    with col_help:
        with st.popover("ℹ️"):
            st.markdown("""
**📊 Monthly Trend & Cumulative**

**Charts:**
- **Monthly Trend**: Revenue (orange) and Gross Profit (blue) bars with GP% line overlay
- **Cumulative Performance**: Running total of Revenue and GP over the year

**Filters:**
- **Customer/Brand/Product**: Filter data by specific selections
- **Excl**: Exclude selected items instead of including them
            """)
    
    # =========================================================================
    # FILTERS ROW - SYNCED with SP page
    # =========================================================================
    
    # Customer filter with Excl checkbox
    col_cust, col_brand, col_prod = st.columns(3)
    
    with col_cust:
        subcol1, subcol2 = st.columns([3, 1])
        with subcol1:
            st.markdown("**Customer**")
        with subcol2:
            excl_customer = st.checkbox("Excl", key=f"{fragment_key}_excl_customer", 
                                       help="Exclude selected customers")
        
        customers = ['All customers...'] + sorted(sales_df['customer'].dropna().unique().tolist())
        selected_customer = st.selectbox(
            "Customer", 
            customers, 
            key=f"{fragment_key}_customer",
            label_visibility="collapsed"
        )
    
    with col_brand:
        subcol1, subcol2 = st.columns([3, 1])
        with subcol1:
            st.markdown("**Brand**")
        with subcol2:
            excl_brand = st.checkbox("Excl", key=f"{fragment_key}_excl_brand",
                                    help="Exclude selected brands")
        
        brands = ['All brands...'] + sorted(sales_df['brand'].dropna().unique().tolist())
        selected_brand = st.selectbox(
            "Brand", 
            brands, 
            key=f"{fragment_key}_brand",
            label_visibility="collapsed"
        )
    
    with col_prod:
        subcol1, subcol2 = st.columns([3, 1])
        with subcol1:
            st.markdown("**Product**")
        with subcol2:
            excl_product = st.checkbox("Excl", key=f"{fragment_key}_excl_product",
                                      help="Exclude selected products")
        
        products = ['All products...'] + sorted(sales_df['product_pn'].dropna().unique().tolist()[:100])
        selected_product = st.selectbox(
            "Product", 
            products, 
            key=f"{fragment_key}_product",
            label_visibility="collapsed"
        )
    
    # =========================================================================
    # APPLY FILTERS
    # =========================================================================
    
    filtered_df = sales_df.copy()
    
    # Customer filter
    if selected_customer != 'All customers...':
        if excl_customer:
            filtered_df = filtered_df[filtered_df['customer'] != selected_customer]
        else:
            filtered_df = filtered_df[filtered_df['customer'] == selected_customer]
    
    # Brand filter
    if selected_brand != 'All brands...':
        if excl_brand:
            filtered_df = filtered_df[filtered_df['brand'] != selected_brand]
        else:
            filtered_df = filtered_df[filtered_df['brand'] == selected_brand]
    
    # Product filter
    if selected_product != 'All products...':
        if excl_product:
            filtered_df = filtered_df[filtered_df['product_pn'] != selected_product]
        else:
            filtered_df = filtered_df[filtered_df['product_pn'] == selected_product]
    
    if filtered_df.empty:
        st.warning("No data matches the selected filters")
        return
    
    # =========================================================================
    # PREPARE MONTHLY DATA
    # =========================================================================
    
    monthly_df = _prepare_monthly_summary(filtered_df)
    
    if monthly_df.empty:
        st.warning("Could not prepare monthly summary")
        return
    
    # =========================================================================
    # CHARTS - 2 columns like SP page
    # =========================================================================
    
    chart_col1, chart_col2 = st.columns(2)
    
    with chart_col1:
        st.markdown("**📊 Monthly Trend**")
        trend_chart = KPICenterCharts.build_monthly_trend_dual_chart(
            monthly_df=monthly_df,
            show_gp_percent_line=True
        )
        st.altair_chart(trend_chart, use_container_width=True)
    
    with chart_col2:
        st.markdown("**📈 Cumulative Performance**")
        cumulative_chart = KPICenterCharts.build_cumulative_dual_chart(
            monthly_df=monthly_df
        )
        st.altair_chart(cumulative_chart, use_container_width=True)


# =============================================================================
# YOY COMPARISON FRAGMENT - UPDATED v2.4.0 to match SP page
# =============================================================================

@st.fragment
def yoy_comparison_fragment(
    queries,
    filter_values: Dict,
    current_year: int = None,
    sales_df: pd.DataFrame = None,
    fragment_key: str = "kpc_yoy"
):
    """
    Year-over-Year comparison with tabs and filters.
    SYNCED with Salesperson page (Image 3).
    
    Shows:
    - Tabs: Revenue / Gross Profit / GP1
    - Summary metrics (Current Year vs Previous Year)
    - Monthly Revenue Comparison (grouped bars)
    - Cumulative Revenue (lines)
    """
    from datetime import date
    
    # Header with anchor link
    st.subheader("📊 Year-over-Year Comparison ↔")
    
    if current_year is None:
        current_year = filter_values.get('year', date.today().year)
    
    previous_year = current_year - 1
    
    # =========================================================================
    # FILTERS ROW - SYNCED with SP page
    # =========================================================================
    
    col_cust, col_brand, col_prod = st.columns(3)
    
    with col_cust:
        subcol1, subcol2 = st.columns([3, 1])
        with subcol1:
            st.markdown("**Customer**")
        with subcol2:
            excl_customer = st.checkbox("Excl", key=f"{fragment_key}_excl_customer",
                                       help="Exclude selected customers")
        
        # Get customer options from current data or query
        if sales_df is not None and not sales_df.empty:
            customers = ['All customers...'] + sorted(sales_df['customer'].dropna().unique().tolist())
        else:
            customers = ['All customers...']
        
        selected_customer = st.selectbox(
            "Customer",
            customers,
            key=f"{fragment_key}_customer",
            label_visibility="collapsed"
        )
    
    with col_brand:
        subcol1, subcol2 = st.columns([3, 1])
        with subcol1:
            st.markdown("**Brand**")
        with subcol2:
            excl_brand = st.checkbox("Excl", key=f"{fragment_key}_excl_brand",
                                    help="Exclude selected brands")
        
        if sales_df is not None and not sales_df.empty:
            brands = ['All brands...'] + sorted(sales_df['brand'].dropna().unique().tolist())
        else:
            brands = ['All brands...']
        
        selected_brand = st.selectbox(
            "Brand",
            brands,
            key=f"{fragment_key}_brand",
            label_visibility="collapsed"
        )
    
    with col_prod:
        subcol1, subcol2 = st.columns([3, 1])
        with subcol1:
            st.markdown("**Product**")
        with subcol2:
            excl_product = st.checkbox("Excl", key=f"{fragment_key}_excl_product",
                                      help="Exclude selected products")
        
        if sales_df is not None and not sales_df.empty:
            products = ['All products...'] + sorted(sales_df['product_pn'].dropna().unique().tolist()[:100])
        else:
            products = ['All products...']
        
        selected_product = st.selectbox(
            "Product",
            products,
            key=f"{fragment_key}_product",
            label_visibility="collapsed"
        )
    
    # =========================================================================
    # LOAD DATA
    # =========================================================================
    
    @st.cache_data(ttl=1800, show_spinner=False)
    def load_yoy_data_cached(start_date, end_date, kpi_center_ids, entity_ids, exclude_internal):
        """Load current and previous year data."""
        # Current year
        current_df = queries.get_sales_data(
            start_date=start_date,
            end_date=end_date,
            kpi_center_ids=kpi_center_ids,
            entity_ids=entity_ids
        )
        
        # Previous year
        try:
            prev_start = date(start_date.year - 1, start_date.month, start_date.day)
            prev_end = date(end_date.year - 1, end_date.month, end_date.day)
        except ValueError:
            prev_start = date(start_date.year - 1, start_date.month, 28)
            prev_end = date(end_date.year - 1, end_date.month, 28)
        
        previous_df = queries.get_sales_data(
            start_date=prev_start,
            end_date=prev_end,
            kpi_center_ids=kpi_center_ids,
            entity_ids=entity_ids
        )
        
        # Exclude internal if requested
        if exclude_internal:
            if 'customer_type' in current_df.columns:
                current_df = current_df[current_df['customer_type'] != 'Internal']
            if 'customer_type' in previous_df.columns:
                previous_df = previous_df[previous_df['customer_type'] != 'Internal']
        
        return current_df, previous_df
    
    start_date = filter_values.get('start_date', date(current_year, 1, 1))
    end_date = filter_values.get('end_date', date.today())
    kpi_center_ids = filter_values.get('kpi_center_ids', [])
    entity_ids = filter_values.get('entity_ids', [])
    exclude_internal = filter_values.get('exclude_internal_revenue', True)
    
    try:
        current_df, previous_df = load_yoy_data_cached(
            start_date, end_date, tuple(kpi_center_ids) if kpi_center_ids else None,
            tuple(entity_ids) if entity_ids else None, exclude_internal
        )
    except Exception as e:
        logger.error(f"Error loading YoY data: {e}")
        st.error(f"Failed to load comparison data: {e}")
        return
    
    # =========================================================================
    # APPLY LOCAL FILTERS
    # =========================================================================
    
    def apply_filters(df):
        if df.empty:
            return df
        
        result = df.copy()
        
        if selected_customer != 'All customers...':
            if excl_customer:
                result = result[result['customer'] != selected_customer]
            else:
                result = result[result['customer'] == selected_customer]
        
        if selected_brand != 'All brands...':
            if excl_brand:
                result = result[result['brand'] != selected_brand]
            else:
                result = result[result['brand'] == selected_brand]
        
        if selected_product != 'All products...':
            if excl_product:
                result = result[result['product_pn'] != selected_product]
            else:
                result = result[result['product_pn'] == selected_product]
        
        return result
    
    current_filtered = apply_filters(current_df)
    previous_filtered = apply_filters(previous_df)
    
    # =========================================================================
    # PREPARE MONTHLY SUMMARIES
    # =========================================================================
    
    current_monthly = _prepare_monthly_summary(current_filtered)
    previous_monthly = _prepare_monthly_summary(previous_filtered)
    
    # =========================================================================
    # YEAR COMPARISON HEADER
    # =========================================================================
    
    st.markdown(f"**📅 {current_year} vs {previous_year}**")
    
    # =========================================================================
    # TABS: Revenue / Gross Profit / GP1
    # =========================================================================
    
    tab_rev, tab_gp, tab_gp1 = st.tabs(["💰 Revenue", "📈 Gross Profit", "📊 GP1"])
    
    for tab, metric_name, metric_col in [
        (tab_rev, "Revenue", "revenue"),
        (tab_gp, "Gross Profit", "gross_profit"),
        (tab_gp1, "GP1", "gp1")
    ]:
        with tab:
            # Calculate totals
            current_total = current_monthly[metric_col].sum() if not current_monthly.empty and metric_col in current_monthly.columns else 0
            previous_total = previous_monthly[metric_col].sum() if not previous_monthly.empty and metric_col in previous_monthly.columns else 0
            
            # YoY change
            if previous_total > 0:
                yoy_change = ((current_total - previous_total) / previous_total * 100)
                yoy_diff = current_total - previous_total
            else:
                yoy_change = 0
                yoy_diff = current_total
            
            # Summary metrics row
            col_curr, col_prev = st.columns(2)
            
            with col_curr:
                st.markdown(f"**{current_year} {metric_name}**")
                st.markdown(f"### ${current_total:,.0f}")
                if yoy_change != 0:
                    color = "green" if yoy_change > 0 else "red"
                    arrow = "↑" if yoy_change > 0 else "↓"
                    st.markdown(f":{color}[{arrow} {yoy_change:+.1f}% YoY]")
            
            with col_prev:
                st.markdown(f"**{previous_year} {metric_name}**")
                st.markdown(f"### ${previous_total:,.0f}")
                st.markdown(f"↑ ${yoy_diff:+,.0f} difference" if yoy_diff != 0 else "")
            
            st.markdown("")
            
            # Charts row
            chart_col1, chart_col2 = st.columns(2)
            
            with chart_col1:
                st.markdown(f"**📊 Monthly {metric_name} Comparison**")
                comparison_chart = KPICenterCharts.build_yoy_comparison_chart(
                    current_df=current_monthly,
                    previous_df=previous_monthly,
                    metric=metric_name,
                    current_year=current_year,
                    previous_year=previous_year
                )
                st.altair_chart(comparison_chart, use_container_width=True)
            
            with chart_col2:
                st.markdown(f"**📈 Cumulative {metric_name}**")
                cumulative_chart = KPICenterCharts.build_yoy_cumulative_chart(
                    current_df=current_monthly,
                    previous_df=previous_monthly,
                    metric=metric_name,
                    current_year=current_year,
                    previous_year=previous_year
                )
                st.altair_chart(cumulative_chart, use_container_width=True)


# =============================================================================
# SALES DETAIL FRAGMENT - kept from v2.2.0
# =============================================================================

@st.fragment
def sales_detail_fragment(
    sales_df: pd.DataFrame,
    filter_values: Dict = None,
    fragment_key: str = "kpc_sales"
):
    """Sales detail list with filters and summary cards."""
    if sales_df.empty:
        st.info("No sales data available")
        return
    
    # Summary cards at top
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total Revenue", f"${sales_df['sales_by_kpi_center_usd'].sum():,.0f}")
    with col2:
        st.metric("Total GP", f"${sales_df['gross_profit_by_kpi_center_usd'].sum():,.0f}")
    with col3:
        st.metric("Invoices", f"{sales_df['inv_number'].nunique():,}")
    with col4:
        st.metric("Customers", f"{sales_df['customer_id'].nunique():,}")
    
    st.divider()
    
    # Filters
    col1, col2, col3 = st.columns(3)
    
    with col1:
        customers = ['All'] + sorted(sales_df['customer'].dropna().unique().tolist())
        selected_customer = st.selectbox("Customer", customers, key=f"{fragment_key}_cust")
    
    with col2:
        brands = ['All'] + sorted(sales_df['brand'].dropna().unique().tolist())
        selected_brand = st.selectbox("Brand", brands, key=f"{fragment_key}_brand")
    
    with col3:
        search = st.text_input("Search Product", placeholder="Part number...", key=f"{fragment_key}_search")
    
    # Apply filters
    filtered = sales_df.copy()
    
    if selected_customer != 'All':
        filtered = filtered[filtered['customer'] == selected_customer]
    if selected_brand != 'All':
        filtered = filtered[filtered['brand'] == selected_brand]
    if search:
        filtered = filtered[filtered['product_pn'].fillna('').str.lower().str.contains(search.lower())]
    
    st.caption(f"Showing {len(filtered):,} transactions")
    
    # Display columns
    display_cols = ['inv_date', 'inv_number', 'customer', 'brand', 'product_pn',
                   'sales_by_kpi_center_usd', 'gross_profit_by_kpi_center_usd', 'kpi_center']
    display_cols = [c for c in display_cols if c in filtered.columns]
    
    st.dataframe(
        filtered[display_cols].head(500),
        hide_index=True,
        column_config={
            'inv_date': st.column_config.DateColumn('Date'),
            'inv_number': 'Invoice',
            'customer': 'Customer',
            'brand': 'Brand',
            'product_pn': 'Product',
            'sales_by_kpi_center_usd': st.column_config.NumberColumn('Revenue', format="$%,.0f"),
            'gross_profit_by_kpi_center_usd': st.column_config.NumberColumn('GP', format="$%,.0f"),
            'kpi_center': 'KPI Center',
        },
        use_container_width=True
    )


# =============================================================================
# PIVOT ANALYSIS FRAGMENT
# =============================================================================

@st.fragment
def pivot_analysis_fragment(
    sales_df: pd.DataFrame,
    fragment_key: str = "kpc_pivot"
):
    """Configurable pivot table analysis."""
    if sales_df.empty:
        st.info("No data for pivot analysis")
        return
    
    st.subheader("📊 Pivot Analysis")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        row_options = ['customer', 'brand', 'kpi_center', 'invoice_month']
        row_by = st.selectbox("Rows", row_options, key=f"{fragment_key}_rows")
    
    with col2:
        col_options = ['None', 'invoice_month', 'brand', 'kpi_center']
        col_by = st.selectbox("Columns", col_options, key=f"{fragment_key}_cols")
    
    with col3:
        value_options = ['Revenue', 'Gross Profit', 'GP1', 'Orders']
        value_metric = st.selectbox("Values", value_options, key=f"{fragment_key}_values")
    
    # Map value selection
    value_col_map = {
        'Revenue': 'sales_by_kpi_center_usd',
        'Gross Profit': 'gross_profit_by_kpi_center_usd',
        'GP1': 'gp1_by_kpi_center_usd',
        'Orders': 'inv_number'
    }
    value_col = value_col_map.get(value_metric, 'sales_by_kpi_center_usd')
    
    # Ensure month column exists
    df = sales_df.copy()
    if 'invoice_month' not in df.columns and 'inv_date' in df.columns:
        df['inv_date'] = pd.to_datetime(df['inv_date'], errors='coerce')
        df['invoice_month'] = df['inv_date'].dt.strftime('%b')
    
    # Aggregate
    if value_metric == 'Orders':
        agg_func = pd.Series.nunique
    else:
        agg_func = 'sum'
    
    if col_by == 'None':
        pivot = df.groupby(row_by).agg({value_col: agg_func}).reset_index()
        pivot.columns = [row_by, value_metric]
        pivot = pivot.sort_values(value_metric, ascending=False)
    else:
        pivot = df.pivot_table(
            index=row_by,
            columns=col_by,
            values=value_col,
            aggfunc=agg_func,
            fill_value=0
        ).reset_index()
    
    # Format
    format_dict = {}
    if value_metric in ['Revenue', 'Gross Profit', 'GP1']:
        for col in pivot.columns:
            if col != row_by:
                format_dict[col] = st.column_config.NumberColumn(format="$%,.0f")
    
    st.dataframe(
        pivot.head(50),
        hide_index=True,
        column_config=format_dict,
        use_container_width=True
    )


# =============================================================================
# BACKLOG LIST FRAGMENT
# =============================================================================

@st.fragment
def backlog_list_fragment(
    backlog_df: pd.DataFrame,
    filter_values: Dict = None,
    total_backlog_df: pd.DataFrame = None,
    fragment_key: str = "kpc_backlog"
):
    """Backlog detail list with risk indicators."""
    if backlog_df.empty:
        st.info("No backlog data available")
        return
    
    st.subheader("📋 Backlog Detail")
    
    # Show overall totals if available
    if total_backlog_df is not None and not total_backlog_df.empty:
        col1, col2, col3 = st.columns(3)
        with col1:
            total_rev = total_backlog_df['backlog_revenue'].sum() if 'backlog_revenue' in total_backlog_df.columns else 0
            st.metric("Total Backlog", f"${total_rev:,.0f}")
        with col2:
            total_gp = total_backlog_df['backlog_gp'].sum() if 'backlog_gp' in total_backlog_df.columns else 0
            st.metric("Total GP", f"${total_gp:,.0f}")
        with col3:
            total_orders = len(backlog_df)
            st.metric("Orders", f"{total_orders:,}")
        
        st.divider()
    
    # Filters
    col1, col2 = st.columns(2)
    
    with col1:
        customers = ['All'] + sorted(backlog_df['customer'].dropna().unique().tolist())
        selected_customer = st.selectbox("Customer", customers, key=f"{fragment_key}_cust")
    
    with col2:
        risk_filter = st.selectbox("Risk Level", ['All', '🔴 Overdue', '🟡 At Risk', '🟢 OK'],
                                   key=f"{fragment_key}_risk")
    
    # Apply filters
    filtered = backlog_df.copy()
    
    if selected_customer != 'All':
        filtered = filtered[filtered['customer'] == selected_customer]
    
    # Add risk indicator
    def get_risk_indicator(days):
        try:
            d = float(days)
            if pd.isna(d):
                return "⚪"
            if d < 0:
                return "🔴"
            elif d <= 7:
                return "🟡"
            elif d <= 30:
                return "🟢"
            else:
                return "⚪"
        except:
            return "⚪"
    
    if 'days_until_etd' in filtered.columns:
        filtered['risk'] = filtered['days_until_etd'].apply(get_risk_indicator)
        
        if risk_filter != 'All':
            risk_map = {
                '🔴 Overdue': '🔴',
                '🟡 At Risk': '🟡',
                '🟢 OK': '🟢'
            }
            filtered = filtered[filtered['risk'] == risk_map.get(risk_filter, '')]
    
    st.caption(f"Showing {len(filtered):,} orders")
    
    # Display
    display_cols = ['risk', 'etd', 'customer', 'product_pn', 'backlog_by_kpi_center_usd',
                   'backlog_gp_by_kpi_center_usd', 'kpi_center', 'days_until_etd']
    display_cols = [c for c in display_cols if c in filtered.columns]
    
    st.dataframe(
        filtered[display_cols].head(500),
        hide_index=True,
        column_config={
            'risk': st.column_config.TextColumn('Risk', width='small'),
            'etd': st.column_config.DateColumn('ETD'),
            'customer': 'Customer',
            'product_pn': 'Product',
            'backlog_by_kpi_center_usd': st.column_config.NumberColumn('Backlog', format="$%,.0f"),
            'backlog_gp_by_kpi_center_usd': st.column_config.NumberColumn('GP', format="$%,.0f"),
            'kpi_center': 'KPI Center',
            'days_until_etd': st.column_config.NumberColumn('Days', format="%d"),
        },
        use_container_width=True
    )


# =============================================================================
# KPI CENTER RANKING FRAGMENT
# =============================================================================

@st.fragment
def kpi_center_ranking_fragment(
    ranking_df: pd.DataFrame,
    show_targets: bool = True,
    fragment_key: str = "kpc_ranking"
):
    """KPI Center performance ranking table."""
    if ranking_df.empty:
        st.info("No ranking data available")
        return
    
    # Sort options
    sort_options = ['Revenue', 'Gross Profit', 'GP1', 'GP %']
    if show_targets:
        sort_options.append('Achievement %')
    
    sort_by = st.selectbox("Sort by", sort_options, key=f"{fragment_key}_sort")
    
    # Map sort selection - use actual column names from aggregate_by_kpi_center()
    sort_col_map = {
        'Revenue': 'revenue',
        'Gross Profit': 'gross_profit',
        'GP1': 'gp1',
        'GP %': 'gp_percent',
        'Achievement %': 'revenue_achievement'
    }
    sort_col = sort_col_map.get(sort_by, 'revenue')
    
    if sort_col not in ranking_df.columns:
        sort_col = 'revenue'
    
    # Sort and add rank
    sorted_df = ranking_df.sort_values(sort_col, ascending=False).copy()
    sorted_df.insert(0, 'Rank', range(1, len(sorted_df) + 1))
    
    # Format - use actual column names from aggregate_by_kpi_center()
    column_config = {
        'Rank': st.column_config.NumberColumn('Rank', width='small'),
        'kpi_center': 'KPI Center',
        'revenue': st.column_config.NumberColumn('Revenue', format='$%,.0f'),
        'gross_profit': st.column_config.NumberColumn('GP', format='$%,.0f'),
        'gp1': st.column_config.NumberColumn('GP1', format='$%,.0f'),
        'gp_percent': st.column_config.NumberColumn('GP %', format='%.1f%%'),
        'customers': 'Customers',
        'invoices': 'Orders',
    }
    
    if show_targets and 'revenue_achievement' in sorted_df.columns:
        column_config['revenue_achievement'] = st.column_config.ProgressColumn(
            'Achievement',
            min_value=0,
            max_value=150,
            format='%.1f%%'
        )
    
    st.dataframe(
        sorted_df,
        hide_index=True,
        column_config=column_config,
        use_container_width=True
    )


# =============================================================================
# TOP PERFORMERS FRAGMENT - kept from v2.3.0
# =============================================================================

@st.fragment
def top_performers_fragment(
    sales_df: pd.DataFrame,
    filter_values: Dict = None,
    metrics_calculator = None,
    fragment_key: str = "kpc_top"
):
    """Top performers / Pareto analysis."""
    if sales_df.empty:
        st.info("No data for analysis")
        return
    
    st.subheader("🏆 Top Performers Analysis")
    
    # Controls
    col1, col2, col3 = st.columns(3)
    
    with col1:
        group_by = st.selectbox(
            "Analyze by",
            ["Customer", "Brand", "Product"],
            key=f"{fragment_key}_group"
        )
    
    with col2:
        metric = st.selectbox(
            "Metric",
            ["Revenue", "Gross Profit", "GP1"],
            key=f"{fragment_key}_metric"
        )
    
    with col3:
        top_percent = st.slider(
            "Show top %",
            min_value=50,
            max_value=100,
            value=80,
            step=5,
            key=f"{fragment_key}_pct"
        )
    
    # Map selections
    group_col_map = {
        "Customer": "customer",
        "Brand": "brand",
        "Product": "product_pn"
    }
    group_col = group_col_map.get(group_by, "customer")
    
    metric_col_map = {
        "Revenue": "sales_by_kpi_center_usd",
        "Gross Profit": "gross_profit_by_kpi_center_usd",
        "GP1": "gp1_by_kpi_center_usd"
    }
    value_col = metric_col_map.get(metric, "sales_by_kpi_center_usd")
    
    # Aggregate
    agg_df = sales_df.groupby(group_col).agg({
        'sales_by_kpi_center_usd': 'sum',
        'gross_profit_by_kpi_center_usd': 'sum',
        'gp1_by_kpi_center_usd': 'sum' if 'gp1_by_kpi_center_usd' in sales_df.columns else 'first',
        'inv_number': pd.Series.nunique
    }).reset_index()
    
    agg_df.columns = [group_col, 'revenue', 'gross_profit', 'gp1', 'orders']
    
    # Sort and calculate cumulative
    metric_lower = metric.lower().replace(' ', '_')
    agg_df = agg_df.sort_values(metric_lower, ascending=False)
    
    total = agg_df[metric_lower].sum()
    if total == 0:
        st.warning("No data to analyze")
        return
    
    agg_df['cumulative'] = agg_df[metric_lower].cumsum()
    agg_df['cumulative_percent'] = (agg_df['cumulative'] / total * 100).round(1)
    agg_df['percent'] = (agg_df[metric_lower] / total * 100).round(1)
    
    # Filter to top percent
    top_data = agg_df[agg_df['cumulative_percent'] <= top_percent].copy()
    if top_data.empty:
        top_data = agg_df.head(1).copy()
    
    # Summary metrics
    st.divider()
    
    col_s1, col_s2, col_s3, col_s4 = st.columns(4)
    
    top_count = len(top_data)
    total_count = len(agg_df)
    top_value = top_data[metric_lower].sum()
    concentration = (top_count / total_count * 100) if total_count > 0 else 0
    
    with col_s1:
        st.metric(f"Top {group_by}s", f"{top_count:,}", f"of {total_count:,} total")
    
    with col_s2:
        st.metric(f"Top {top_percent}% {metric}", f"${top_value:,.0f}",
                 f"{(top_value/total*100):.1f}% of total")
    
    with col_s3:
        st.metric("Concentration", f"{concentration:.1f}%")
    
    with col_s4:
        avg_per = top_value / top_count if top_count > 0 else 0
        st.metric(f"Avg per {group_by}", f"${avg_per:,.0f}")
    
    # Chart and table
    chart_col, table_col = st.columns([1.2, 1])
    
    with chart_col:
        chart = KPICenterCharts.build_top_performers_chart(
            data_df=top_data,
            value_col=metric_lower,
            label_col=group_col,
            top_n=min(15, len(top_data)),
            title=f"Top {group_by}s by {metric}"
        )
        st.altair_chart(chart, use_container_width=True)
    
    with table_col:
        display_df = top_data[[group_col, 'revenue', 'gross_profit', 'gp1', 'orders', 'percent', 'cumulative_percent']].copy()
        display_df.insert(0, 'Rank', range(1, len(display_df) + 1))
        
        st.dataframe(
            display_df.head(20),
            hide_index=True,
            column_config={
                'Rank': st.column_config.NumberColumn('🏆', width='small'),
                group_col: group_by,
                'revenue': st.column_config.NumberColumn('Revenue', format='$%,.0f'),
                'gross_profit': st.column_config.NumberColumn('GP', format='$%,.0f'),
                'gp1': st.column_config.NumberColumn('GP1', format='$%,.0f'),
                'orders': 'Orders',
                'percent': st.column_config.NumberColumn('% Share', format='%.1f%%'),
                'cumulative_percent': st.column_config.NumberColumn('Cum %', format='%.1f%%'),
            },
            use_container_width=True
        )


# =============================================================================
# EXPORT REPORT FRAGMENT
# =============================================================================

@st.fragment
def export_report_fragment(
    metrics: Dict,
    complex_kpis: Dict,
    pipeline_metrics: Dict,
    filter_values: Dict,
    yoy_metrics: Dict = None,
    kpi_center_summary_df: pd.DataFrame = None,
    monthly_df: pd.DataFrame = None,
    sales_detail_df: pd.DataFrame = None,
    backlog_summary_df: pd.DataFrame = None,
    backlog_detail_df: pd.DataFrame = None,
    backlog_by_month_df: pd.DataFrame = None
):
    """Excel report generation fragment."""
    from .export import KPICenterExport
    
    st.subheader("📥 Export Report")
    
    with st.expander("ℹ️ Export Options"):
        st.markdown("""
**Excel Report includes:**
- Summary sheet with all KPI metrics
- KPI Center breakdown
- Monthly trend data
- Sales transaction details (up to 10,000 rows)
- Backlog summary and details
        """)
    
    if st.button("🔄 Generate Excel Report", key="generate_report_btn", type="primary"):
        with st.spinner("Generating report..."):
            try:
                exporter = KPICenterExport()
                excel_bytes = exporter.create_comprehensive_report(
                    metrics=metrics,
                    complex_kpis=complex_kpis,
                    pipeline_metrics=pipeline_metrics,
                    filters=filter_values,
                    yoy_metrics=yoy_metrics,
                    kpi_center_summary_df=kpi_center_summary_df,
                    monthly_df=monthly_df,
                    sales_detail_df=sales_detail_df,
                    backlog_summary_df=backlog_summary_df,
                    backlog_detail_df=backlog_detail_df,
                    backlog_by_month_df=backlog_by_month_df,
                )
                st.session_state['kpi_center_export_data'] = excel_bytes
                st.success("✅ Report generated! Click download below.")
            except Exception as e:
                logger.error(f"Export error: {e}")
                st.error(f"Failed to generate report: {e}")
    
    if 'kpi_center_export_data' in st.session_state:
        year = filter_values.get('year', 2025)
        period = filter_values.get('period_type', 'YTD')
        filename = f"kpi_center_performance_{year}_{period}.xlsx"
        st.download_button(
            label="⬇️ Download Excel Report",
            data=st.session_state['kpi_center_export_data'],
            file_name=filename,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="download_report_btn"
        )