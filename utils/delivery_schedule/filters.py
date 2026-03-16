# utils/delivery_schedule/filters.py
"""Filter section — date preset lives OUTSIDE the form so it can
conditionally show/hide date pickers without waiting for submit."""

import streamlit as st
import json
from datetime import datetime, timedelta


def create_filter_section(filter_options):
    """Create the filter section with all filter controls.

    Date preset is rendered outside the form so that changing it
    immediately shows/hides the manual date pickers.  Everything
    else stays inside the form to prevent full-page reruns.
    """

    # ── Minimal styling ─────────────────────────────────────────
    st.markdown("""
    <style>
        /* Overdue popover: full width */
        [data-testid="stPopoverBody"] {
            width: calc(100vw - 6rem);
            max-width: calc(100vw - 6rem);
        }
    </style>
    """, unsafe_allow_html=True)

    # ── Pre-compute date bounds ──────────────────────────────────
    date_range_options = filter_options.get('date_range', {})
    today = datetime.now().date()
    data_min = date_range_options.get('min_date', today - timedelta(days=365))
    data_max = date_range_options.get('max_date', today + timedelta(days=365))
    if hasattr(data_min, 'date'):
        data_min = data_min.date()
    if hasattr(data_max, 'date'):
        data_max = data_max.date()
    if data_min > data_max:
        data_min, data_max = data_max, data_min
    extended_min = data_min.replace(month=1, day=1)
    extended_max = data_max.replace(month=12, day=31)

    # ── Date Preset (outside form — reruns immediately) ──────────
    preset_col, range_col = st.columns([1, 3])

    with preset_col:
        preset = st.selectbox(
            "📅 Date Range",
            options=["All Data", "This Week", "This Month",
                     "Next 30 Days", "Next 90 Days", "Custom"],
            index=1,
            key="date_preset",
        )

    # Compute the resolved range for non-Custom presets
    resolved_from, resolved_to = _resolve_date_preset(
        preset, None, None, today, data_min, data_max,
    )

    with range_col:
        if preset == "Custom":
            # Show editable date pickers
            dc1, dc2 = st.columns(2)
            with dc1:
                date_from = st.date_input(
                    "From", value=data_min,
                    min_value=extended_min, max_value=extended_max,
                    key="input_date_from",
                )
            with dc2:
                date_to = st.date_input(
                    "To", value=data_max,
                    min_value=extended_min, max_value=extended_max,
                    key="input_date_to",
                )
            if date_from > date_to:
                date_from, date_to = date_to, date_from
            resolved_from, resolved_to = date_from, date_to
        else:
            # Show read-only label with computed range
            st.markdown("")  # vertical spacer to align with selectbox
            st.info(
                f"📅  **{resolved_from.strftime('%Y/%m/%d')}**  →  "
                f"**{resolved_to.strftime('%Y/%m/%d')}**"
                f"{'  ·  Data range: ' + data_min.strftime('%Y/%m/%d') + ' → ' + data_max.strftime('%Y/%m/%d') if preset == 'All Data' else ''}"
            )

    # ── Main filter form ─────────────────────────────────────────
    with st.form("delivery_filters"):
        # ROW 1: Timeline + Legal Entity + Creator + Customer
        r1c1, r1c2, r1c3, r1c4 = st.columns(4)

        timeline_options = filter_options.get('timeline_statuses', [])
        default_timeline = ["Completed"] if "Completed" in timeline_options else None
        with r1c1:
            selected_timeline, exclude_timeline = _multiselect_excl(
                "Timeline Status", timeline_options, "timeline",
                default=default_timeline, excl_default=True,
            )
        with r1c2:
            selected_legal_entities, exclude_legal_entities = _multiselect_excl(
                "Legal Entity", filter_options.get('legal_entities', []),
                "legal_entities",
            )
        with r1c3:
            selected_creators, exclude_creators = _multiselect_excl(
                "Creator/Sales", filter_options.get('creators', []),
                "creators",
            )
        with r1c4:
            selected_customers, exclude_customers = _multiselect_excl(
                "Customer (Sold-To)", filter_options.get('customers', []),
                "customers",
            )

        # ROW 2: Ship-To, Product, Brand
        r3c1, r3c2, r3c3 = st.columns(3)
        with r3c1:
            selected_ship_to, exclude_ship_to = _multiselect_excl(
                "Ship-To Company", filter_options.get('ship_to_companies', []),
                "ship_to",
            )
        with r3c2:
            selected_products, exclude_products = _multiselect_excl(
                "Product", filter_options.get('products', []),
                "products",
            )
        with r3c3:
            selected_brands, exclude_brands = _multiselect_excl(
                "Brand", filter_options.get('brands', []),
                "brands",
            )

        # ROW 3: Location, Company Type & Inventory option
        r4c1, r4c2, r4c3, r4c4, r4c5 = st.columns([2, 2, 2, 2, 1.5])
        with r4c1:
            selected_states = st.multiselect(
                "State/Province",
                options=filter_options.get('states', []),
                placeholder="All states", key="filter_states",
            )
        with r4c2:
            cc, xc = st.columns([6, 1])
            with cc:
                selected_countries = st.multiselect(
                    "Country",
                    options=filter_options.get('countries', []),
                    placeholder="All countries", key="filter_countries",
                )
            with xc:
                st.markdown("<div style='margin-top:0.2rem'><small style='color:#999'>Excl</small></div>",
                             unsafe_allow_html=True)
                exclude_countries = st.checkbox(
                    "Excl", key="exclude_countries", value=False,
                    help="Exclude selected countries",
                    label_visibility="collapsed",
                )
        with r4c3:
            epe_filter = st.selectbox(
                "EPE Company",
                options=filter_options.get('epe_options', ["All"]),
                index=0, key="epe_filter",
            )
        with r4c4:
            foreign_filter = st.selectbox(
                "Customer Type",
                options=filter_options.get('foreign_options', ["All Customers"]),
                index=0, key="foreign_filter",
            )
        with r4c5:
            st.markdown("")  # vertical spacer
            include_expired = st.checkbox(
                "📦 Include expired stock",
                value=True,
                key="include_expired_inventory",
                help="Include expired inventory in fulfillment rate calculation",
            )

        # Submit
        st.form_submit_button(
            "🔄 Apply Filters", type="primary", use_container_width=True,
        )

    # ── Compile filters dict ─────────────────────────────────────
    filters = {
        'date_from': resolved_from,
        'date_to': resolved_to,
        'include_expired': include_expired,
        'creators': selected_creators or None,
        'exclude_creators': exclude_creators,
        'customers': selected_customers or None,
        'exclude_customers': exclude_customers,
        'products': selected_products or None,
        'exclude_products': exclude_products,
        'brands': selected_brands or None,
        'exclude_brands': exclude_brands,
        'ship_to_companies': selected_ship_to or None,
        'exclude_ship_to_companies': exclude_ship_to,
        'states': selected_states or None,
        'countries': selected_countries or None,
        'exclude_countries': exclude_countries,
        'epe_filter': epe_filter,
        'foreign_filter': foreign_filter,
        'timeline_status': selected_timeline or None,
        'exclude_timeline_status': exclude_timeline,
        'legal_entities': selected_legal_entities or None,
        'exclude_legal_entities': exclude_legal_entities,
        'statuses': None,
        'exclude_statuses': False,
    }

    # ── Filter Preset: Export / Import ──────────────────────────
    _filter_preset_section()

    return filters


# ── Filter Preset Management ─────────────────────────────────────

# All session_state keys managed by the filter system.
# Master filters (form widgets):
_MASTER_FILTER_KEYS = {
    # Date
    'date_preset': 'selectbox',
    'input_date_from': 'date',
    'input_date_to': 'date',
    # Multiselect + Exclude pairs
    'filter_timeline': 'list',
    'exclude_timeline': 'bool',
    'filter_legal_entities': 'list',
    'exclude_legal_entities': 'bool',
    'filter_creators': 'list',
    'exclude_creators': 'bool',
    'filter_customers': 'list',
    'exclude_customers': 'bool',
    'filter_ship_to': 'list',
    'exclude_ship_to': 'bool',
    'filter_products': 'list',
    'exclude_products': 'bool',
    'filter_brands': 'list',
    'exclude_brands': 'bool',
    'filter_states': 'list',
    'filter_countries': 'list',
    'exclude_countries': 'bool',
    # Selectboxes
    'epe_filter': 'selectbox',
    'foreign_filter': 'selectbox',
    # Checkbox
    'include_expired_inventory': 'bool',
}

# Detail-level quick filters (detailed_list.py):
_DETAIL_FILTER_KEYS = {
    '_dl_filter_dn': 'list',
    '_dl_filter_cust': 'list',
    '_dl_filter_prod': 'list',
}

_ALL_FILTER_KEYS = {**_MASTER_FILTER_KEYS, **_DETAIL_FILTER_KEYS}


def _filter_preset_section():
    """Render filter preset Export / Import controls."""
    with st.expander("💾 Filter Presets", expanded=False):
        col_imp, col_exp = st.columns(2)

        with col_imp:
            _import_preset()

        with col_exp:
            _export_preset()


def _export_preset():
    """Serialize current filter state to downloadable JSON."""
    preset = {}
    for key, dtype in _ALL_FILTER_KEYS.items():
        val = st.session_state.get(key)
        if val is None:
            continue
        # Skip empty lists and default values
        if dtype == 'list' and not val:
            continue
        if dtype == 'date':
            val = val.isoformat() if hasattr(val, 'isoformat') else str(val)
        preset[key] = val

    if not preset:
        st.caption("No active filters to export.")
        return

    preset_json = json.dumps(preset, indent=2, ensure_ascii=False, default=str)

    st.download_button(
        "📥 Export current filters",
        data=preset_json,
        file_name=f"filter_preset_{datetime.now().strftime('%Y%m%d_%H%M')}.json",
        mime="application/json",
        key="_preset_export_btn",
        use_container_width=True,
    )
    st.caption(f"{len(preset)} filter(s) active")


def _import_preset():
    """Upload a previously exported filter preset JSON."""
    uploaded = st.file_uploader(
        "📤 Import preset (.json)",
        type=["json"],
        key="_preset_import_uploader",
    )

    if uploaded is None:
        return

    # Avoid re-processing same file after rerun
    file_id = f"{uploaded.name}_{uploaded.size}"
    if st.session_state.get('_preset_last_import') == file_id:
        return

    try:
        preset = json.loads(uploaded.read().decode('utf-8'))
        applied = 0

        for key, val in preset.items():
            if key not in _ALL_FILTER_KEYS:
                continue

            dtype = _ALL_FILTER_KEYS[key]

            # Type coercion
            if dtype == 'date' and isinstance(val, str):
                from datetime import date as _date
                try:
                    val = _date.fromisoformat(val)
                except ValueError:
                    continue
            elif dtype == 'bool' and not isinstance(val, bool):
                val = bool(val)
            elif dtype == 'list' and not isinstance(val, list):
                val = [val]

            st.session_state[key] = val
            applied += 1

        st.session_state['_preset_last_import'] = file_id
        st.toast(f"✅ Loaded preset — {applied} filter(s) applied")
        st.rerun()

    except Exception as e:
        st.error(f"Invalid preset file: {e}")


# ── Helpers ──────────────────────────────────────────────────────

def _resolve_date_preset(preset, date_from, date_to, today, data_min, data_max):
    """Compute actual date range from a preset name."""
    if preset == "This Week":
        ws = today - timedelta(days=today.weekday())
        return max(ws, data_min), min(ws + timedelta(days=6), data_max)
    elif preset == "This Month":
        ms = today.replace(day=1)
        nm = today.replace(day=28) + timedelta(days=4)
        return max(ms, data_min), min(nm - timedelta(days=nm.day), data_max)
    elif preset == "Next 30 Days":
        return max(today, data_min), min(today + timedelta(days=30), data_max)
    elif preset == "Next 90 Days":
        return max(today, data_min), min(today + timedelta(days=90), data_max)
    elif preset == "Custom":
        if date_from and date_to:
            if date_from > date_to:
                date_from, date_to = date_to, date_from
            return date_from, date_to
        return data_min, data_max
    else:  # All Data
        return data_min, data_max


def _multiselect_excl(label, options, key_prefix, default=None, excl_default=False):
    """Multiselect (full label) + icon-only exclude checkbox beside it.

    Layout:  [ ──── multiselect with label ──── ] [☑]
    The checkbox column is just wide enough for the tick box.
    """
    mc, xc = st.columns([6, 1])
    with mc:
        selected = st.multiselect(
            label, options=options, default=default,
            placeholder=f"All {label.lower()}", key=f"filter_{key_prefix}",
        )
    with xc:
        st.markdown("<div style='margin-top:0.2rem'><small style='color:#999'>Excl</small></div>",
                     unsafe_allow_html=True)
        exclude = st.checkbox(
            "Excl", key=f"exclude_{key_prefix}", value=excl_default,
            help=f"Exclude selected {label.lower()}",
            label_visibility="collapsed",
        )
    return selected, exclude