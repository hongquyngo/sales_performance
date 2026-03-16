# pages/1_📊_Delivery_Schedule.py

import streamlit as st
from datetime import datetime
from utils.auth import AuthManager
from utils.delivery_schedule import (
    DeliveryDataLoader,
    EmailSender,
    create_filter_section,
    display_metrics,
    display_pivot_table,
    display_detailed_list,
    display_email_notifications,
    needs_completed_data,
    apply_client_filters,
    calculate_fulfillment,
    render_user_guide,
)

# ── Page config & auth ───────────────────────────────────────────

st.set_page_config(page_title="Delivery Schedule", page_icon="📊", layout="wide")

auth_manager = AuthManager()
if not auth_manager.check_session():
    st.warning("⚠️ Please login to access this page")
    st.stop()

data_loader = DeliveryDataLoader()
email_sender = EmailSender()


# ── Smart data loading with progress ─────────────────────────────

def _load_smart(data_loader, filters, progress, status):
    """Two-tier cache + dynamic fulfillment with progress feedback.

    Tier 1 — st.cache_data inside load_base_data (TTL 5 min, keyed by
             include_completed bool).  Two possible cached DataFrames.
    Tier 2 — client-side pandas filtering on the cached DataFrame.
    Tier 3 — fulfillment recalculation on filtered result.
    """
    include_completed = needs_completed_data(filters)

    # Step 1 — Load from cache (already loaded during filter options)
    status.markdown(
        "⏳ **Loading data** — "
        + ("all deliveries (incl. completed)..." if include_completed else "active deliveries...")
    )
    progress.progress(20, text="Loading from cache...")
    df_base = data_loader.load_base_data(include_completed)

    if df_base is None or df_base.empty:
        return None

    # Step 2 — Apply filters
    status.markdown("🔍 **Applying filters...**")
    progress.progress(50, text="Applying filters...")
    df = apply_client_filters(df_base, filters)

    if df is None or df.empty:
        return None

    # Step 3 — Recalculate fulfillment
    status.markdown("📊 **Calculating fulfillment...**")
    progress.progress(75, text="Calculating fulfillment...")
    include_expired = filters.get('include_expired', True)
    df = calculate_fulfillment(df, include_expired=include_expired)

    progress.progress(100, text="Done!")
    return df


# ── Main ─────────────────────────────────────────────────────────

def main():
    st.title("📊 Delivery Schedule")
    render_user_guide()

    # Step 0 — Load filter options (triggers initial data cache)
    progress = st.progress(0, text="Initializing...")
    status = st.empty()

    status.markdown("📦 **Loading delivery data & filter options...**")
    progress.progress(15, text="Loading data...")
    filter_options = data_loader.get_filter_options()

    # Clear progress while user interacts with filters
    progress.empty()
    status.empty()

    # Filters (form — no rerun until submit)
    filters = create_filter_section(filter_options)

    # Re-create progress bar for data loading phase
    progress = st.progress(0, text="Loading data...")
    status = st.empty()

    # Load data — smart 2-tier cache + dynamic fulfillment
    df = _load_smart(data_loader, filters, progress, status)

    if df is None or df.empty:
        progress.empty()
        status.empty()
        st.info("No delivery data found for the selected filters")
        return

    # Step 4 — Load overdue data (cache hit — no extra DB query)
    status.markdown("⚠️ **Loading overdue data...**")
    progress.progress(85, text="Loading overdue data...")
    include_expired = filters.get('include_expired', True)
    df_all_active = data_loader.load_base_data(include_completed=False)
    df_all_active = calculate_fulfillment(df_all_active, include_expired=include_expired)

    # Step 5 — Rendering
    status.markdown("🎨 **Rendering UI...**")
    progress.progress(95, text="Rendering UI...")

    # Track selected PT codes for cross-page use
    if filters.get('products'):
        st.session_state.selected_pt_codes = [
            p.split(' - ')[0] for p in filters['products']
        ]
    else:
        st.session_state.selected_pt_codes = None

    # Done — clear progress
    progress.progress(100, text="✅ Done!")
    import time; time.sleep(0.3)  # brief flash so user sees "Done"
    progress.empty()
    status.empty()

    # KPI cards — overdue/OOS from full active data, rest from filtered
    display_metrics(df, df_all_active)

    # Tabs — each @st.fragment runs independently
    tab1, tab2, tab3 = st.tabs([
        "📊 Pivot Table",
        "📋 Detailed List",
        "📧 Email Notifications",
    ])

    with tab1:
        display_pivot_table(df, data_loader)
    with tab2:
        display_detailed_list(df, data_loader, email_sender)
    with tab3:
        display_email_notifications(data_loader, email_sender)

    # Footer
    st.markdown("---")
    st.caption(f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    main()