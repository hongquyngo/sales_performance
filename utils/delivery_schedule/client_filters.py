# utils/delivery_schedule/client_filters.py
"""Client-side filtering on cached DataFrame.

The DB only ever returns two possible datasets:
  • active  — delivery_timeline_status != 'Completed'
  • full    — all rows (active + completed)

Every other filter (customer, product, date range, brand, …)
is applied here in pure pandas — instant, no DB round-trip.
"""

import pandas as pd
from datetime import datetime


# ── Public API ───────────────────────────────────────────────────

def needs_completed_data(filters: dict) -> bool:
    """Determine whether the current filter set requires completed rows.

    Returns True when the user explicitly *wants* to see completed data:
      • Timeline filter is empty (= show all) and exclude is OFF
      • Timeline filter includes "Completed" and exclude is OFF
      • Timeline filter excludes something else but NOT "Completed"

    Returns False (= active-only is sufficient) when:
      • "Completed" is selected AND exclude is ON   ← the default
      • Timeline filter selects specific non-completed statuses
    """
    selected = filters.get('timeline_status')  # list or None
    exclude = filters.get('exclude_timeline_status', False)

    if not selected:
        # Nothing selected → means "All" → need completed too
        return True

    has_completed = 'Completed' in selected

    if exclude:
        # Excluding the selected items
        # If "Completed" is in the exclude list → don't need completed data
        return not has_completed
    else:
        # Including only selected items
        # Need completed data only if "Completed" is among them
        return has_completed


def apply_client_filters(df: pd.DataFrame, filters: dict) -> pd.DataFrame:
    """Apply all user-selected filters on a cached DataFrame.

    Handles every filter that `load_delivery_data` previously pushed to SQL,
    but operates entirely in memory — sub-second even for 100k+ rows.
    """
    if df is None or df.empty:
        return df

    mask = pd.Series(True, index=df.index)

    # ── Date range ───────────────────────────────────────────────
    if 'etd' in df.columns:
        etd = pd.to_datetime(df['etd'], errors='coerce')
        if filters.get('date_from'):
            mask &= etd >= pd.Timestamp(filters['date_from'])
        if filters.get('date_to'):
            mask &= etd <= pd.Timestamp(filters['date_to'])

    # ── Include / Exclude helpers ────────────────────────────────
    def _apply_list_filter(col, values, exclude):
        nonlocal mask
        if not values or col not in df.columns:
            return
        if exclude:
            mask &= ~df[col].isin(values)
        else:
            mask &= df[col].isin(values)

    # ── Timeline status ──────────────────────────────────────────
    _apply_list_filter(
        'delivery_timeline_status',
        filters.get('timeline_status'),
        filters.get('exclude_timeline_status', False),
    )

    # ── Products (need to extract pt_code from "PT001 - Name") ──
    products = filters.get('products')
    if products:
        pt_codes = [p.split(' - ')[0] for p in products]
        _apply_list_filter(
            'pt_code', pt_codes,
            filters.get('exclude_products', False),
        )

    # ── Brands ───────────────────────────────────────────────────
    _apply_list_filter(
        'brand',
        filters.get('brands'),
        filters.get('exclude_brands', False),
    )

    # ── Creators ─────────────────────────────────────────────────
    _apply_list_filter(
        'created_by_name',
        filters.get('creators'),
        filters.get('exclude_creators', False),
    )

    # ── Customers ────────────────────────────────────────────────
    _apply_list_filter(
        'customer',
        filters.get('customers'),
        filters.get('exclude_customers', False),
    )

    # ── Ship-to companies ────────────────────────────────────────
    _apply_list_filter(
        'recipient_company',
        filters.get('ship_to_companies'),
        filters.get('exclude_ship_to_companies', False),
    )

    # ── Legal entities ───────────────────────────────────────────
    _apply_list_filter(
        'legal_entity',
        filters.get('legal_entities'),
        filters.get('exclude_legal_entities', False),
    )

    # ── States ───────────────────────────────────────────────────
    _apply_list_filter(
        'recipient_state_province',
        filters.get('states'),
        filters.get('exclude_states', False),
    )

    # ── Countries ────────────────────────────────────────────────
    _apply_list_filter(
        'recipient_country_name',
        filters.get('countries'),
        filters.get('exclude_countries', False),
    )

    # ── Shipment statuses ────────────────────────────────────────
    _apply_list_filter(
        'shipment_status',
        filters.get('statuses'),
        filters.get('exclude_statuses', False),
    )

    # ── EPE Company (radio: All / EPE Only / Non-EPE Only) ──────
    epe = filters.get('epe_filter')
    if epe == 'EPE Companies Only' and 'is_epe_company' in df.columns:
        mask &= df['is_epe_company'] == 'Yes'
    elif epe == 'Non-EPE Companies Only' and 'is_epe_company' in df.columns:
        mask &= df['is_epe_company'] == 'No'

    # ── Foreign / Domestic (radio) ───────────────────────────────
    foreign = filters.get('foreign_filter')
    if foreign == 'Foreign Only' and 'customer_country_code' in df.columns:
        mask &= df['customer_country_code'] != df['legal_entity_country_code']
    elif foreign == 'Domestic Only' and 'customer_country_code' in df.columns:
        mask &= df['customer_country_code'] == df['legal_entity_country_code']

    return df.loc[mask].copy()