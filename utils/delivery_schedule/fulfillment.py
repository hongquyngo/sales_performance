# utils/delivery_schedule/fulfillment.py
"""Dynamic fulfillment calculation — responsive to filtered data.

The SQL view (`delivery_full_view`) provides GLOBAL fulfillment columns
computed across all active deliveries.  Those values are fine for email
notifications and other non-filtered contexts.

For the Delivery Schedule UI, we OVERWRITE those columns with values
recomputed from the *filtered* DataFrame so that:
  1. Product-level demand reflects only the deliveries the user sees.
  2. The "include expired inventory" toggle controls which stock column
     is used as the supply source.

Column contract — these columns are overwritten in-place so that
downstream UI code (metrics, pivot, detailed list) requires NO changes:
  • product_total_remaining_demand
  • product_active_delivery_count
  • product_gap_quantity
  • product_fulfill_rate_percent
  • delivery_demand_percentage
  • product_fulfillment_status
  • gap_quantity              (line-level)
  • fulfill_rate_percent      (line-level)
  • fulfillment_status        (line-level)
"""

import numpy as np
import pandas as pd
import logging

logger = logging.getLogger(__name__)

# ── Columns that get overwritten ─────────────────────────────────

_PRODUCT_LEVEL_COLS = [
    'product_total_remaining_demand',
    'product_active_delivery_count',
    'product_gap_quantity',
    'product_fulfill_rate_percent',
    'product_fulfillment_status',
]

_LINE_LEVEL_COLS = [
    'gap_quantity',
    'fulfill_rate_percent',
    'fulfillment_status',
    'delivery_demand_percentage',
    'stock_out_progress',
]


# ── Public API ───────────────────────────────────────────────────

def calculate_fulfillment(
    df: pd.DataFrame,
    include_expired: bool = True,
) -> pd.DataFrame:
    """Recalculate all fulfillment columns on *df* in-place.

    Parameters
    ----------
    df : DataFrame
        Delivery data — typically the *filtered* result from
        ``apply_client_filters()``.
    include_expired : bool
        If True  → use ``total_instock_*`` columns  (all inventory).
        If False → use ``total_instock_*_valid`` columns (non-expired only).

    Returns
    -------
    DataFrame with fulfillment columns overwritten.
    """
    if df is None or df.empty:
        return df

    df = df.copy()

    # ── Pick the right inventory columns ─────────────────────────
    if include_expired:
        stock_all = 'total_instock_all_warehouses'
        stock_pref = 'total_instock_at_preferred_warehouse'
    else:
        stock_all = 'total_instock_all_warehouses_valid'
        stock_pref = 'total_instock_at_preferred_warehouse_valid'

    # Fallback: if _valid columns don't exist, use the regular ones
    if stock_all not in df.columns:
        logger.warning(
            f"Column {stock_all!r} not found — falling back to "
            f"'total_instock_all_warehouses'.  Run the updated SQL view."
        )
        stock_all = 'total_instock_all_warehouses'
        stock_pref = 'total_instock_at_preferred_warehouse'

    # ── 1. Product-level aggregation from filtered data ──────────
    active_mask = (
        (df['remaining_quantity_to_deliver'] > 0)
        & (df['shipment_status'] != 'DELIVERED')
    )

    product_stats = (
        df.loc[active_mask]
        .groupby('product_id', sort=False)
        .agg(
            _demand=('remaining_quantity_to_deliver', 'sum'),
            _dn_count=('delivery_id', 'nunique'),
        )
    )

    # Inventory per product (same value for every row of a product — take max)
    product_inv = (
        df.groupby('product_id', sort=False)[stock_all]
        .max()
        .rename('_stock')
    )

    product_stats = product_stats.join(product_inv, how='left')
    product_stats['_stock'] = product_stats['_stock'].fillna(0)

    # Calculate
    product_stats['product_total_remaining_demand'] = product_stats['_demand']
    product_stats['product_active_delivery_count'] = product_stats['_dn_count']
    product_stats['product_gap_quantity'] = (
        product_stats['_demand'] - product_stats['_stock']
    )
    product_stats['product_fulfill_rate_percent'] = np.where(
        product_stats['_demand'] > 0,
        (product_stats['_stock'] / product_stats['_demand'] * 100).round(2),
        np.where(product_stats['_stock'] > 0, 100.0, 0.0),
    )
    product_stats['product_fulfillment_status'] = _classify_product_status_vec(
        product_stats['_stock'], product_stats['_demand'],
    )

    # ── 2. Merge product stats back ──────────────────────────────
    merge_cols = [
        'product_total_remaining_demand',
        'product_active_delivery_count',
        'product_gap_quantity',
        'product_fulfill_rate_percent',
        'product_fulfillment_status',
    ]

    # Drop old columns, join new ones
    df = df.drop(columns=[c for c in merge_cols if c in df.columns])
    df = df.join(
        product_stats[merge_cols],
        on='product_id',
        how='left',
    )

    # Fill NaN for products with no active lines in current filter
    df['product_total_remaining_demand'] = df['product_total_remaining_demand'].fillna(0)
    df['product_active_delivery_count'] = df['product_active_delivery_count'].fillna(0)
    df['product_gap_quantity'] = df['product_gap_quantity'].fillna(0)
    df['product_fulfill_rate_percent'] = df['product_fulfill_rate_percent'].fillna(0)
    df['product_fulfillment_status'] = df['product_fulfillment_status'].fillna('Unknown')

    # ── 3. Line-level calculations ───────────────────────────────
    remaining = df['remaining_quantity_to_deliver'].fillna(0)
    stock = df[stock_all].fillna(0)

    df['gap_quantity'] = remaining - stock
    df['fulfill_rate_percent'] = np.where(
        remaining > 0,
        (stock / remaining * 100).round(2),
        np.where(stock > 0, 100.0, 0.0),
    )

    # Delivery demand percentage
    df['delivery_demand_percentage'] = np.where(
        df['product_total_remaining_demand'] > 0,
        (remaining / df['product_total_remaining_demand'] * 100).round(2),
        0.0,
    )

    # Stock-out progress: how much of the request has been issued
    req_qty = df['stock_out_request_quantity'].fillna(0)
    issued_qty = df['stock_out_quantity'].fillna(0)
    df['stock_out_progress'] = np.where(
        req_qty > 0,
        (issued_qty / req_qty * 100).round(1),
        0.0,
    )

    # Line-level fulfillment status
    df['fulfillment_status'] = _classify_line_status_vec(
        df['shipment_status'], remaining, stock,
    )

    logger.info(
        f"[fulfillment] Recalculated on {len(df)} rows, "
        f"include_expired={include_expired}, "
        f"stock_col={stock_all}"
    )
    return df


# ── Vectorized status classifiers ────────────────────────────────

def _classify_product_status_vec(stock: pd.Series, demand: pd.Series) -> pd.Series:
    """Vectorized product fulfillment status classification."""
    conditions = [
        stock.isna() | (stock == 0),          # No stock at all
        stock >= demand,                       # Enough for ALL demand
        stock > 0,                             # Some stock, not enough
    ]
    choices = ['Out of Stock', 'Can Fulfill All', 'Can Fulfill Partial']
    return pd.Series(
        np.select(conditions, choices, default='Unknown'),
        index=stock.index,
    )


def _classify_line_status_vec(
    shipment_status: pd.Series,
    remaining: pd.Series,
    stock: pd.Series,
) -> pd.Series:
    """Vectorized line-level fulfillment status."""
    conditions = [
        shipment_status == 'DELIVERED',
        (remaining == 0) & shipment_status.isin(['STOCKED_OUT', 'PARTIALLY_STOCKED_OUT']),
        remaining == 0,
        stock.isna() | (stock == 0),
        stock < remaining,
        stock >= remaining,
    ]
    choices = [
        'Delivered',
        'Stocked Out - Ready',
        'No Remaining',
        'Out of Stock',
        'Partial Fulfilled',
        'Fulfilled',
    ]
    return pd.Series(
        np.select(conditions, choices, default='Unknown'),
        index=shipment_status.index,
    )