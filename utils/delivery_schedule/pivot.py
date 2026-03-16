# utils/delivery_schedule/pivot.py
"""Smart pivot table — user picks rows, columns, values, and aggregation."""

import streamlit as st
import pandas as pd
from datetime import datetime

# ── Column registry ──────────────────────────────────────────────
# Maps user-friendly names → actual DataFrame column names.

ROW_COLUMN_OPTIONS = {
    "Customer":              "customer",
    "Ship-To Company":       "recipient_company",
    "PT Code":               "pt_code",
    "Product Name":          "product_pn",
    "Brand":                 "brand",
    "Package Size":          "package_size",
    "State/Province":        "recipient_state_province",
    "Country":               "recipient_country_name",
    "Legal Entity":          "legal_entity",
    "Creator/Sales":         "created_by_name",
    "Shipment Status":       "shipment_status",
    "Timeline Status":       "delivery_timeline_status",
    "Fulfillment Status":    "product_fulfillment_status",
    "EPE Company":           "is_epe_company",
    "Preferred Warehouse":   "preferred_warehouse",
}

VALUE_OPTIONS = {
    "Requested Qty":          ("stock_out_request_quantity",         "sum"),
    "Issued Qty":             ("stock_out_quantity",                 "sum"),
    "Pending Qty":            ("remaining_quantity_to_deliver",      "sum"),
    "Std Quantity":           ("standard_quantity",                  "sum"),
    "Selling Qty":            ("selling_quantity",                   "sum"),
    "Gap Qty":                ("gap_quantity",                       "sum"),
    "Product Gap Qty":        ("product_gap_quantity",               "sum"),
    "Delivery Count":         ("delivery_id",                       "nunique"),
    "Avg Fulfill %":          ("product_fulfill_rate_percent",      "mean"),
    "Avg Issued %":           ("stock_out_progress",                "mean"),
}

AGG_OPTIONS = ["sum", "mean", "count", "nunique", "min", "max"]

TIME_PERIOD_OPTIONS = {
    "Daily":   "D",
    "Weekly":  "W",
    "Monthly": "M",
}


@st.fragment
def display_pivot_table(df, data_loader):
    """Display smart pivot table with flexible row/column/value selectors."""
    st.subheader("📊 Pivot Table")

    # ── Available columns (only show options that exist in df) ────
    avail_row_opts = {k: v for k, v in ROW_COLUMN_OPTIONS.items() if v in df.columns}
    avail_val_opts = {k: v for k, v in VALUE_OPTIONS.items() if v[0] in df.columns}

    if not avail_row_opts or not avail_val_opts:
        st.warning("Not enough columns in the data to build a pivot table.")
        return

    # ── Configuration row ────────────────────────────────────────
    cfg1, cfg2, cfg3, cfg4, cfg5 = st.columns([2, 1.5, 1.5, 1, 1])

    with cfg1:
        row_labels = st.multiselect(
            "Rows",
            options=list(avail_row_opts.keys()),
            default=["State/Province", "Ship-To Company"],
            help="Group data by these fields (left side of pivot)",
        )

    with cfg2:
        col_mode = st.radio(
            "Columns",
            options=["Time Period", "Category"],
            horizontal=True,
            help="What appears across the top of the pivot",
        )

    with cfg3:
        if col_mode == "Time Period":
            time_period_label = st.selectbox(
                "Period", options=list(TIME_PERIOD_OPTIONS.keys()), index=0,
            )
            col_field = None
        else:
            # Pick a categorical column for cross-tab
            remaining = {k: v for k, v in avail_row_opts.items() if k not in row_labels}
            if not remaining:
                st.warning("No category left for columns — change row selection.")
                col_field = None
                time_period_label = None
            else:
                col_label = st.selectbox("Category", options=list(remaining.keys()))
                col_field = remaining[col_label]
                time_period_label = None

    with cfg4:
        val_label = st.selectbox("Value", options=list(avail_val_opts.keys()), index=0)
        val_col, default_agg = avail_val_opts[val_label]

    with cfg5:
        agg_func = st.selectbox(
            "Aggregation",
            options=AGG_OPTIONS,
            index=AGG_OPTIONS.index(default_agg) if default_agg in AGG_OPTIONS else 0,
            help="How to aggregate values in each cell",
        )

    if not row_labels:
        st.info("Select at least one row field.")
        return

    # ── Build pivot ──────────────────────────────────────────────
    row_cols = [avail_row_opts[lbl] for lbl in row_labels]
    work = df.copy()

    # Ensure etd is datetime when using time period columns
    if 'etd' in work.columns:
        work['etd'] = pd.to_datetime(work['etd'], errors='coerce')

    if col_mode == "Time Period" and time_period_label:
        freq = TIME_PERIOD_OPTIONS[time_period_label]
        pivot_table = _build_time_pivot(work, row_cols, freq, val_col, agg_func, time_period_label)
    elif col_field:
        pivot_table = _build_category_pivot(work, row_cols, col_field, val_col, agg_func)
    else:
        pivot_table = _build_flat_pivot(work, row_cols, val_col, agg_func)

    if pivot_table is None or pivot_table.empty:
        st.info("No data for this pivot configuration.")
        return

    # ── Display ──────────────────────────────────────────────────
    _render_pivot(pivot_table, row_labels)

    # ── Download ─────────────────────────────────────────────────
    csv = pivot_table.to_csv(index=False).encode('utf-8')
    st.download_button(
        "📥 Download CSV", data=csv,
        file_name=f"pivot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        mime="text/csv",
    )


# ── Pivot builders ───────────────────────────────────────────────

def _build_time_pivot(df, row_cols, freq, val_col, agg_func, period_label):
    """Pivot with time-period columns (daily / weekly / monthly)."""
    try:
        pt = df.pivot_table(
            index=row_cols,
            columns=pd.Grouper(key='etd', freq=freq),
            values=val_col,
            aggfunc=agg_func,
            fill_value=0,
        )

        # Format column headers
        fmt = {
            'Daily':   '%Y-%m-%d',
            'Weekly':  'W %Y-%m-%d',
            'Monthly': '%b %Y',
        }.get(period_label, '%Y-%m-%d')
        pt.columns = pt.columns.strftime(fmt)

        # Add row total
        pt['Total'] = pt.sum(axis=1)

        # Sort by total descending, then drop helper
        pt = pt.sort_values('Total', ascending=False)

        return pt.reset_index()
    except Exception as e:
        st.error(f"Pivot error: {e}")
        return pd.DataFrame()


def _build_category_pivot(df, row_cols, col_field, val_col, agg_func):
    """Pivot with a categorical column across the top."""
    try:
        pt = df.pivot_table(
            index=row_cols,
            columns=col_field,
            values=val_col,
            aggfunc=agg_func,
            fill_value=0,
        )

        pt['Total'] = pt.sum(axis=1)
        pt = pt.sort_values('Total', ascending=False)

        return pt.reset_index()
    except Exception as e:
        st.error(f"Pivot error: {e}")
        return pd.DataFrame()


def _build_flat_pivot(df, row_cols, val_col, agg_func):
    """Simple group-by without cross-tab columns (fallback)."""
    try:
        pt = df.groupby(row_cols).agg(**{val_col: (val_col, agg_func)}).reset_index()
        pt = pt.sort_values(val_col, ascending=False)
        return pt
    except Exception as e:
        st.error(f"Pivot error: {e}")
        return pd.DataFrame()


# ── Rendering ────────────────────────────────────────────────────

def _render_pivot(table, row_labels):
    """Render pivot table with formatting and frozen row columns."""
    # Identify numeric columns (everything except row labels)
    row_display = set(row_labels)
    num_cols = [c for c in table.columns
                if c not in [ROW_COLUMN_OPTIONS.get(r, r) for r in row_labels]]

    # Build format dict — numbers only
    fmt = {}
    for c in num_cols:
        if table[c].dtype in ('float64', 'float32'):
            fmt[c] = '{:,.1f}'
        else:
            fmt[c] = '{:,.0f}'

    styled = table.style.format(fmt, na_rep='-')

    # Gradient on numeric columns (skip Total column for cleaner look)
    gradient_cols = [c for c in num_cols if c != 'Total']
    if gradient_cols:
        styled = styled.background_gradient(subset=gradient_cols, cmap='Blues')

    # Highlight Total column
    if 'Total' in table.columns:
        styled = styled.background_gradient(subset=['Total'], cmap='YlOrRd')

    # Column config for Streamlit
    column_config = {}
    for c in table.columns:
        if c in [ROW_COLUMN_OPTIONS.get(r, r) for r in row_labels]:
            column_config[c] = st.column_config.TextColumn(c, width="medium")
        elif c == 'Total':
            column_config[c] = st.column_config.NumberColumn(c, width="small")
        else:
            column_config[c] = st.column_config.NumberColumn(c, width="small")

    st.dataframe(
        styled,
        width="stretch",
        height=min(600, 50 + len(table) * 35),
        column_config=column_config,
    )

    st.caption(f"{len(table):,} rows  ·  {len(num_cols)} data columns")