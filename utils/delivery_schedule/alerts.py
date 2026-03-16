# utils/delivery_schedule/alerts.py
"""Overdue delivery alert fragment"""

import streamlit as st


@st.fragment
def display_overdue_alert(df):
    """Display overdue deliveries alert"""
    overdue_df = df[df['delivery_timeline_status'] == 'Overdue']

    if overdue_df.empty:
        return

    with st.expander("⚠️ Overdue Deliveries Alert", expanded=True):
        st.warning(f"There are {overdue_df['delivery_id'].nunique()} overdue deliveries requiring attention!")

        overdue_summary = overdue_df.groupby(['customer', 'recipient_company']).agg({
            'delivery_id': 'nunique',
            'days_overdue': 'max',
            'remaining_quantity_to_deliver': 'sum'
        }).reset_index()
        overdue_summary.columns = ['Customer', 'Ship To', 'Deliveries', 'Max Days Overdue', 'Pending Qty']

        st.dataframe(
            overdue_summary.style.format({
                'Pending Qty': '{:,.0f}',
                'Max Days Overdue': '{:.0f} days',
                'Deliveries': '{:,.0f}'
            }, na_rep='-').background_gradient(
                subset=['Max Days Overdue'], cmap='Reds'
            ).bar(
                subset=['Pending Qty'], color='#ff6b6b'
            ),
            width="stretch"
        )