# utils/delivery_schedule/detailed_list.py
"""Detailed delivery list with inline ETD editing (single & bulk).

Features:
  • Quick Filters — expander with DN Number, Customer, Product
    sub-filters applied on top of the main page filters.
  • Filter Presets — export current sub-filter as JSON, import later
    for quick recall across sessions.
  • Inline ETD edit via st.data_editor — click any ETD cell to
    open the date picker.  Changing one line auto-expands all lines
    of the same DN into a staging section below (ETD is header-level).
  • Multiple DNs can be edited with different new ETDs before saving.
  • Bulk ETD update — select multiple DNs, set one new date.
  • On save → DB update → email notification → cache clear → refresh.

Email notification:
  TO  : creator (created_by_email of each affected DN)
  CC  : current user + dn_update@prostech.vn
"""

import streamlit as st
import pandas as pd
from datetime import datetime, date
import logging

logger = logging.getLogger(__name__)


# ── User-friendly column labels ──────────────────────────────────

COLUMN_LABELS = {
    'dn_number':                          'DN Number',
    'delivery_id':                        'Delivery ID',
    'customer':                           'Customer',
    'recipient_company':                  'Ship-To Company',
    'recipient_state_province':           'State/Province',
    'recipient_country_name':             'Country',
    'etd':                                'ETD',
    'pt_code':                            'PT Code',
    'product_pn':                         'Product Name',
    'product_id':                         'Product ID',
    'brand':                              'Brand',
    'package_size':                       'Package Size',
    'standard_quantity':                  'Std Qty',
    'selling_quantity':                   'Selling Qty',
    'stock_out_request_quantity':         'Requested Qty',
    'stock_out_quantity':                 'Issued Qty',
    'remaining_quantity_to_deliver':      'Pending Qty',
    'stock_out_progress':                 'Issued %',
    'total_instock_at_preferred_warehouse': 'In-Stock (Preferred WH)',
    'total_instock_all_warehouses':       'In-Stock (All WH)',
    'gap_quantity':                       'Gap Qty',
    'product_gap_quantity':               'Product Gap Qty',
    'product_total_remaining_demand':     'Total Remaining Demand',
    'product_fulfill_rate_percent':       'Fulfill Rate %',
    'fulfill_rate_percent':               'Line Fulfill %',
    'delivery_demand_percentage':         'Demand %',
    'delivery_timeline_status':           'Timeline Status',
    'days_overdue':                       'Days Overdue',
    'shipment_status':                    'Shipment Status',
    'product_fulfillment_status':         'Fulfillment Status',
    'is_epe_company':                     'EPE Company',
    'legal_entity':                       'Legal Entity',
    'created_by_name':                    'Creator/Sales',
    'created_date':                       'Created Date',
    'delivered_date':                     'Delivered Date',
    'dispatched_date':                    'Dispatched Date',
    'preferred_warehouse':                'Preferred WH',
    'shipping_cost':                      'Shipping Cost',
    'export_tax':                         'Export Tax',
    'customer_country_code':              'Customer Country',
    'legal_entity_country_code':          'Entity Country',
}

# Columns visible by default (order matters)
DEFAULT_COLUMNS = [
    'dn_number', 'customer', 'recipient_company', 'etd',
    'pt_code', 'product_pn', 'brand',
    'stock_out_request_quantity', 'stock_out_quantity',
    'remaining_quantity_to_deliver', 'stock_out_progress',
    'product_fulfill_rate_percent',
    'delivery_timeline_status', 'days_overdue', 'shipment_status',
    'product_fulfillment_status', 'is_epe_company',
]


@st.fragment
def display_detailed_list(df, data_loader=None, email_sender=None):
    """Display detailed delivery list with ETD editing capability.

    Parameters
    ----------
    df : DataFrame
        Filtered delivery data.
    data_loader : DeliveryDataLoader, optional
        Needed for ETD update DB operations.
    email_sender : EmailSender, optional
        Needed for sending ETD change notifications.
    """
    st.subheader("📋 Detailed Delivery List")

    # ── Sub-filters (collapsed expander) ─────────────────────────
    display_df = df.copy()
    display_df = _apply_detail_filters(display_df)

    if display_df.empty:
        st.info("No data matches the current filters.")
        return

    # ── Prepare display data ─────────────────────────────────────
    # Keep etd as date for the editor
    if 'etd' in display_df.columns:
        display_df['etd'] = pd.to_datetime(display_df['etd'], errors='coerce').dt.date

    # Format other date columns to string
    other_date_cols = ['created_date', 'delivered_date', 'dispatched_date']
    for col in other_date_cols:
        if col in display_df.columns:
            display_df[col] = pd.to_datetime(
                display_df[col], errors='coerce'
            ).dt.strftime('%Y-%m-%d')

    # ── Check if editing is allowed ──────────────────────────────
    can_edit = (
        data_loader is not None
        and email_sender is not None
        and st.session_state.get('user_role', '') in (
            'supply_chain_manager', 'outbound_manager', 'supply_chain',
        )
    )

    if can_edit:
        _display_editable_table(display_df, data_loader, email_sender)
    else:
        _display_readonly_table(display_df)


# ── Detail-level sub-filters ─────────────────────────────────────

def _apply_detail_filters(df):
    """Render sub-filter expander and apply selections to df.

    Filters: DN Number, Customer, Product.
    (Full preset export/import is in filters.py — covers all filters.)
    """
    with st.expander("🔍 Quick Filters", expanded=False):

        # ── Build options from current data ──────────────────────
        dn_opts = sorted(df['dn_number'].dropna().unique()) if 'dn_number' in df.columns else []
        cust_opts = sorted(df['customer'].dropna().unique()) if 'customer' in df.columns else []
        prod_opts = []
        if 'pt_code' in df.columns and 'product_pn' in df.columns:
            prod_opts = sorted(
                (df[['pt_code', 'product_pn']]
                 .dropna()
                 .drop_duplicates()
                 .apply(lambda r: f"{r['pt_code']} - {r['product_pn']}", axis=1)
                 .tolist())
            )

        # ── Filter widgets ───────────────────────────────────────
        fc1, fc2, fc3 = st.columns(3)

        with fc1:
            sel_dn = st.multiselect(
                "DN Number",
                options=dn_opts,
                placeholder="All DNs",
                key="_dl_filter_dn",
            )
        with fc2:
            sel_cust = st.multiselect(
                "Customer",
                options=cust_opts,
                placeholder="All customers",
                key="_dl_filter_cust",
            )
        with fc3:
            sel_prod = st.multiselect(
                "Product",
                options=prod_opts,
                placeholder="All products",
                key="_dl_filter_prod",
            )

    # ── Apply filters ────────────────────────────────────────────
    mask = pd.Series(True, index=df.index)

    if sel_dn:
        mask &= df['dn_number'].isin(sel_dn)

    if sel_cust:
        mask &= df['customer'].isin(sel_cust)

    if sel_prod:
        pt_codes = [p.split(' - ')[0] for p in sel_prod]
        mask &= df['pt_code'].isin(pt_codes)

    filtered = df.loc[mask].copy()

    # Show count after filter
    if sel_dn or sel_cust or sel_prod:
        st.caption(
            f"Showing **{len(filtered):,}** of {len(df):,} rows  "
            f"({filtered['delivery_id'].nunique() if not filtered.empty else 0} DNs)"
        )

    return filtered


# ── Read-only table (original behaviour) ─────────────────────────

def _display_readonly_table(display_df):
    """Render the table without editing capability."""
    if 'etd' in display_df.columns:
        display_df = display_df.copy()
        display_df['etd'] = display_df['etd'].astype(str)

    column_config = _build_column_config(display_df)
    col_order = [c for c in DEFAULT_COLUMNS if c in display_df.columns]

    st.dataframe(
        display_df,
        column_order=col_order,
        column_config=column_config,
        use_container_width=True,
        hide_index=True,
        height=min(700, 50 + len(display_df) * 35),
    )


# ── Editable table + bulk update ─────────────────────────────────

def _display_editable_table(display_df, data_loader, email_sender):
    """Render the table with editable ETD + bulk update section.

    Inline edit flow:
      1. User clicks any ETD cell → date picker opens → picks new date.
      2. All lines of the same DN auto-appear in the staging section
         below with the new ETD.
      3. User can continue editing more DNs — each DN can have a
         different new ETD.  All accumulate in the staging section.
      4. Save button commits all staged changes at once.
    """

    edit_tab, bulk_tab = st.tabs(["✏️ Inline Edit", "📦 Bulk Update ETD"])

    # ━━━━ Tab 1: Inline Edit via data_editor ━━━━━━━━━━━━━━━━━━━━
    with edit_tab:
        st.caption(
            "Click any **ETD** cell to pick a new date.  "
            "All lines of the same DN will appear in the staging "
            "section below.  You can edit multiple DNs before saving."
        )

        # Keep a copy of original ETD per delivery_id for comparison
        original_etd_map = (
            display_df
            .drop_duplicates(subset='delivery_id')
            .set_index('delivery_id')['etd']
            .to_dict()
        )

        column_config = _build_column_config(display_df, etd_editable=True)
        col_order = [c for c in DEFAULT_COLUMNS if c in display_df.columns]

        edited_df = st.data_editor(
            display_df,
            column_order=col_order,
            column_config=column_config,
            use_container_width=True,
            hide_index=True,
            height=min(700, 50 + len(display_df) * 35),
            key="etd_editor",
            num_rows="fixed",
        )

        # ── Detect changes at DN level ───────────────────────────
        # For each delivery_id, if ANY line has a different ETD
        # from the original, treat the whole DN as changed and use
        # the new ETD (first changed value found for that DN).
        changes = _detect_dn_etd_changes(original_etd_map, edited_df)

        # ── Staging section ──────────────────────────────────────
        if changes:
            st.divider()
            st.markdown(
                f"### 📝 Staged ETD Changes — "
                f"{len(changes)} DN(s)"
            )

            # Collect all affected lines for highlight
            changed_ids = {c['delivery_id'] for c in changes}
            affected_df = edited_df[
                edited_df['delivery_id'].isin(changed_ids)
            ].copy()

            # Show summary table: DN / Customer / Ship To / Old → New
            _show_changes_preview(changes)

            # Show affected lines with highlight
            _show_affected_lines(affected_df)

            # Reason + Save
            col_reason, col_btn = st.columns([3, 1])
            with col_reason:
                reason = st.text_input(
                    "Reason for change (optional)",
                    placeholder="e.g. Customer requested reschedule",
                    key="inline_etd_reason",
                )
            with col_btn:
                st.markdown("")  # vertical spacer
                if st.button(
                    f"💾 Save {len(changes)} DN(s) & Notify",
                    type="primary",
                    key="save_inline_etd",
                    use_container_width=True,
                ):
                    _execute_etd_updates(
                        changes, display_df, data_loader,
                        email_sender, reason=reason,
                    )

    # ━━━━ Tab 2: Bulk Update ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    with bulk_tab:
        _display_bulk_update(display_df, data_loader, email_sender)


def _display_bulk_update(display_df, data_loader, email_sender):
    """Bulk ETD update — select multiple DNs, set one new date."""

    st.caption("Select deliveries and set a new ETD for all of them at once.")

    dn_options = (
        display_df[['dn_number', 'delivery_id', 'customer', 'etd']]
        .drop_duplicates(subset='delivery_id')
        .sort_values('dn_number')
    )
    dn_display_map = {}
    for _, row in dn_options.iterrows():
        label = f"{row['dn_number']}  ·  {row['customer']}  ·  ETD: {row['etd']}"
        dn_display_map[label] = row['delivery_id']

    col1, col2 = st.columns([3, 1])

    with col1:
        selected_labels = st.multiselect(
            "Select Deliveries",
            options=list(dn_display_map.keys()),
            placeholder="Choose DNs to update…",
            key="bulk_dn_select",
        )

    with col2:
        new_etd = st.date_input(
            "New ETD",
            value=datetime.now().date(),
            key="bulk_new_etd",
        )

    if not selected_labels:
        return

    selected_ids = [dn_display_map[lbl] for lbl in selected_labels]
    changes = []
    for did in selected_ids:
        rows = display_df[display_df['delivery_id'] == did]
        if rows.empty:
            continue
        row = rows.iloc[0]
        old_etd = row['etd']
        if old_etd == new_etd:
            continue
        changes.append({
            'delivery_id': did,
            'dn_number': row['dn_number'],
            'customer': row.get('customer', ''),
            'recipient_company': row.get('recipient_company', ''),
            'old_etd': old_etd,
            'new_etd': new_etd,
        })

    if not changes:
        st.warning("No ETD changes — the selected DNs already have this date.")
        return

    st.info(f"📝 **{len(changes)}** delivery(ies) will be updated to **{new_etd}**")
    _show_changes_preview(changes)

    col_btn, col_reason = st.columns([1, 2])
    with col_reason:
        reason = st.text_input(
            "Reason for change (optional)",
            placeholder="e.g. Customer requested reschedule",
            key="bulk_etd_reason",
        )
    with col_btn:
        st.markdown("")  # spacer
        if st.button(
            "💾 Apply Bulk Update & Notify",
            type="primary",
            key="save_bulk_etd",
        ):
            _execute_etd_updates(
                changes, display_df, data_loader, email_sender, reason=reason,
            )


# ── Helpers ──────────────────────────────────────────────────────


def _detect_dn_etd_changes(original_etd_map, edited_df):
    """Detect ETD changes at the DN (delivery_id) level.

    Parameters
    ----------
    original_etd_map : dict
        {delivery_id: original_etd_date} — one entry per DN.
    edited_df : DataFrame
        The full DataFrame returned by st.data_editor.

    Returns
    -------
    list[dict] — one entry per changed DN, each with:
        delivery_id, dn_number, customer, recipient_company,
        old_etd, new_etd.

    Logic: scan every row.  If ANY line of a DN has a different ETD
    from the original, the whole DN is staged with that new ETD.
    The user only needs to change ONE line — the whole DN adopts it.
    """
    # Collect new_etd per delivery_id (first changed value wins)
    dn_new_etd = {}  # delivery_id → new_etd
    dn_info = {}     # delivery_id → {dn_number, customer, ...}

    for _, row in edited_df.iterrows():
        did = row['delivery_id']

        # Already found a change for this DN — skip
        if did in dn_new_etd:
            continue

        new_etd = row['etd']
        if isinstance(new_etd, datetime):
            new_etd = new_etd.date()

        old_etd = original_etd_map.get(did)
        if isinstance(old_etd, datetime):
            old_etd = old_etd.date()

        # Skip if both null or same
        if pd.isna(old_etd) and pd.isna(new_etd):
            continue
        if old_etd == new_etd:
            continue

        # Found a change — record it
        dn_new_etd[did] = new_etd
        dn_info[did] = {
            'dn_number': row.get('dn_number', ''),
            'customer': row.get('customer', ''),
            'recipient_company': row.get('recipient_company', ''),
            'old_etd': old_etd,
        }

    # Build changes list
    changes = []
    for did, new_etd in dn_new_etd.items():
        info = dn_info[did]
        changes.append({
            'delivery_id': did,
            'dn_number': info['dn_number'],
            'customer': info['customer'],
            'recipient_company': info['recipient_company'],
            'old_etd': info['old_etd'],
            'new_etd': new_etd,
        })

    return changes


def _show_affected_lines(affected_df):
    """Show affected lines with highlight background."""
    show_cols = [
        'dn_number', 'customer', 'recipient_company', 'etd',
        'pt_code', 'product_pn', 'brand',
        'stock_out_request_quantity', 'stock_out_quantity',
        'remaining_quantity_to_deliver', 'delivery_timeline_status',
    ]
    show_cols = [c for c in show_cols if c in affected_df.columns]

    display = affected_df[show_cols].copy()
    display = display.rename(columns=COLUMN_LABELS)

    st.dataframe(
        display.style.map(lambda _: 'background-color: #fff8e1'),
        use_container_width=True,
        hide_index=True,
        height=min(300, 40 + len(display) * 35),
    )


def _show_changes_preview(changes):
    """Display a compact preview table of pending ETD changes."""
    preview = pd.DataFrame(changes)
    preview = preview.rename(columns={
        'dn_number': 'DN Number',
        'customer': 'Customer',
        'recipient_company': 'Ship To',
        'old_etd': 'Current ETD',
        'new_etd': 'New ETD',
    })
    display_cols = [c for c in ['DN Number', 'Customer', 'Ship To', 'Current ETD', 'New ETD']
                    if c in preview.columns]
    st.dataframe(
        preview[display_cols],
        use_container_width=True,
        hide_index=True,
    )


def _execute_etd_updates(changes, display_df, data_loader, email_sender, reason=""):
    """Write ETD changes to DB, send email, clear cache."""
    current_user = st.session_state.get('user_fullname', 'System')
    current_email = st.session_state.get('user_email', '')

    success_count = 0
    errors = []

    with st.spinner("Updating ETD in database…"):
        for ch in changes:
            ok, msg = data_loader.update_delivery_etd(
                delivery_id=ch['delivery_id'],
                new_etd=ch['new_etd'],
                updated_by=current_user,
                reason=reason,
            )
            if ok:
                success_count += 1
            else:
                errors.append(f"{ch['dn_number']}: {msg}")

    if success_count > 0:
        st.success(f"✅ Updated ETD for {success_count}/{len(changes)} deliveries")

        with st.spinner("Sending email notifications…"):
            _send_etd_notifications(
                changes, display_df, email_sender,
                current_user, current_email, reason,
            )

        # Clear cache so next load picks up new ETD
        data_loader.load_base_data.clear()

    if errors:
        st.error("Some updates failed:\n" + "\n".join(errors))
        if success_count > 0:
            # Some succeeded but not all — let user see errors, then offer refresh
            if st.button("🔄 Refresh data", key="refresh_after_partial"):
                st.rerun()

    # Auto-rerun only when ALL succeeded — otherwise let user see errors
    if success_count > 0 and not errors:
        st.toast(f"✅ Updated {success_count} DN(s) — refreshing data…")
        st.rerun()


def _send_etd_notifications(changes, display_df, email_sender,
                             updated_by_name, updated_by_email, reason):
    """Send ETD change email grouped by creator.

    TO  : creator (created_by_email)
    CC  : user who made the change + dn_update@prostech.vn
    """
    GROUP_CC = "dn_update@prostech.vn"

    creator_groups = {}
    for ch in changes:
        rows = display_df[display_df['delivery_id'] == ch['delivery_id']]
        if rows.empty:
            continue
        creator_email = rows.iloc[0].get('created_by_email', '')
        creator_name = rows.iloc[0].get('created_by_name', 'Team')
        if not creator_email:
            continue
        creator_groups.setdefault(creator_email, {
            'name': creator_name,
            'changes': [],
        })['changes'].append(ch)

    for creator_email, info in creator_groups.items():
        cc_list = [GROUP_CC]
        if updated_by_email and updated_by_email != creator_email:
            cc_list.append(updated_by_email)

        try:
            ok, msg = email_sender.send_etd_update_notification(
                to_email=creator_email,
                to_name=info['name'],
                changes=info['changes'],
                updated_by_name=updated_by_name,
                updated_by_email=updated_by_email,
                cc_emails=cc_list,
                reason=reason,
            )
            if ok:
                st.toast(f"📧 Notified {info['name']} ({creator_email})")
            else:
                st.warning(f"Failed to email {creator_email}: {msg}")
        except Exception as e:
            logger.error(f"ETD notification error for {creator_email}: {e}")
            st.warning(f"Email error for {creator_email}: {e}")


# ── Column config builder ────────────────────────────────────────

def _build_column_config(df, etd_editable=False):
    """Build st.column_config dict with proper types, labels, and formats.

    Parameters
    ----------
    df : DataFrame
    etd_editable : bool
        If True, ETD column is an editable DateColumn (for data_editor).
        All other columns are always disabled / read-only.
    """

    quantity_cols = {
        'standard_quantity', 'selling_quantity', 'remaining_quantity_to_deliver',
        'stock_out_quantity', 'stock_out_request_quantity',
        'total_instock_at_preferred_warehouse', 'total_instock_all_warehouses',
        'gap_quantity', 'product_gap_quantity', 'product_total_remaining_demand',
    }
    rate_cols = {
        'product_fulfill_rate_percent', 'fulfill_rate_percent',
        'delivery_demand_percentage', 'stock_out_progress',
    }
    currency_cols = {'shipping_cost', 'export_tax'}

    config = {}

    for col in df.columns:
        label = COLUMN_LABELS.get(col, col.replace('_', ' ').title())

        # ETD — editable date column when in data_editor mode
        if col == 'etd' and etd_editable:
            config[col] = st.column_config.DateColumn(
                label, help="Click to change ETD",
            )
            continue

        # Everything else is read-only
        if col in quantity_cols:
            config[col] = st.column_config.NumberColumn(
                label, format="%,.0f", disabled=True,
            )
        elif col in rate_cols:
            config[col] = st.column_config.ProgressColumn(
                label, format="%.1f%%", min_value=0, max_value=100,
            )
        elif col in currency_cols:
            config[col] = st.column_config.NumberColumn(
                label, format="%,.2f", disabled=True,
            )
        elif col == 'days_overdue':
            config[col] = st.column_config.NumberColumn(
                label, format="%,.0f", disabled=True,
            )
        else:
            config[col] = st.column_config.TextColumn(label, disabled=True)

    return config