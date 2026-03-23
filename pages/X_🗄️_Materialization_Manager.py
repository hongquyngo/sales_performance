# pages/materialization_manager.py
"""
Materialization Manager

Admin dashboard for monitoring and managing materialized tables.
- Overview of all registered materialized tables
- Data freshness monitoring
- Manual refresh trigger
- Refresh history & health metrics
- Table schema explorer
"""

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import logging

from utils.auth import AuthManager
from utils.materialization import get_mat_manager

logger = logging.getLogger(__name__)

# =====================================================================
# Page Config
# =====================================================================

st.set_page_config(
    page_title="Materialization Manager",
    page_icon="🗄️",
    layout="wide",
)

# Auth
auth = AuthManager()
auth.require_role(["admin"])

# Manager
mgr = get_mat_manager()


# =====================================================================
# Helpers
# =====================================================================

def freshness_badge(minutes_ago, total_rows: int = 0):
    """Return (emoji, color, label) tuple for freshness status"""
    if minutes_ago is None:
        return "⚪", "gray", "No data"
    if minutes_ago <= 30:
        return "🟢", "#22c55e", f"{minutes_ago}m ago"
    if minutes_ago <= 60:
        return "🟢", "#22c55e", f"{minutes_ago}m ago"
    if minutes_ago <= 120:
        return "🟡", "#eab308", f"{minutes_ago}m ago"
    hours = minutes_ago // 60
    return "🔴", "#ef4444", f"{hours}h {minutes_ago % 60}m ago"


def status_icon(status: str) -> str:
    icons = {
        "SUCCESS": "✅",
        "FAILED": "❌",
        "RUNNING": "⏳",
        "SKIPPED": "⏭️",
    }
    return icons.get(status, "❓")


def format_duration(sec) -> str:
    if sec is None:
        return "—"
    sec = float(sec)
    if sec < 1:
        return f"{sec*1000:.0f}ms"
    if sec < 60:
        return f"{sec:.1f}s"
    return f"{sec/60:.1f}m"


def format_rows(n) -> str:
    if n is None:
        return "—"
    n = int(n)
    if n >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n/1_000:.1f}K"
    return str(n)


# =====================================================================
# Check Prerequisites
# =====================================================================

if not mgr.check_log_table_exists():
    st.error(
        "⚠️ **`mat_refresh_log` table not found.** "
        "Please run the materialization setup SQL script first."
    )
    st.code(
        "-- Run this SQL to create required infrastructure:\n"
        "-- See: materialized_sales_invoice_looker.sql (STEP 1)",
        language="sql",
    )
    st.stop()


# =====================================================================
# Page Header
# =====================================================================

st.title("🗄️ Materialization Manager")
st.caption("Monitor & manage materialized tables for analytics performance")

st.divider()

# =====================================================================
# Overview Cards
# =====================================================================

tables = mgr.list_tables()
all_freshness = mgr.get_all_freshness()

# Summary metrics row
col_m1, col_m2, col_m3, col_m4 = st.columns(4)

total_tables = len(tables)
healthy = sum(1 for f in all_freshness.values() if f.get("minutes_ago") is not None and f["minutes_ago"] <= 120)
stale = sum(1 for f in all_freshness.values() if f.get("minutes_ago") is not None and f["minutes_ago"] > 120)
missing = sum(1 for f in all_freshness.values() if not f.get("exists"))

col_m1.metric("Registered Tables", total_tables)
col_m2.metric("Healthy (≤2h)", healthy, delta=None)
col_m3.metric("Stale (>2h)", stale, delta=f"-{stale}" if stale > 0 else None, delta_color="inverse")
col_m4.metric("Missing/Empty", missing, delta=f"-{missing}" if missing > 0 else None, delta_color="inverse")

st.divider()

# =====================================================================
# Table Status Cards
# =====================================================================

for info in tables:
    tn = info.table_name
    fresh = all_freshness.get(tn, {})
    emoji, color, label = freshness_badge(fresh.get("minutes_ago"), fresh.get("total_rows", 0))
    size = mgr.get_table_size(tn)
    is_running = mgr.is_refreshing(tn)

    with st.container(border=True):
        # Header row
        hdr_col1, hdr_col2 = st.columns([3, 1])
        with hdr_col1:
            st.markdown(f"### {emoji} {info.display_name}")
            st.caption(f"`{tn}` — {info.category}")
        with hdr_col2:
            st.markdown(
                f"<div style='text-align:right; padding-top:8px;'>"
                f"<span style='font-size:0.8em; color:gray;'>Freshness</span><br>"
                f"<span style='font-size:1.3em; font-weight:600; color:{color};'>{label}</span>"
                f"</div>",
                unsafe_allow_html=True,
            )

        # Metrics row
        mc1, mc2, mc3, mc4, mc5, mc6 = st.columns(6)
        mc1.metric("Rows", format_rows(fresh.get("total_rows")))
        mc2.metric("Data Size", f"{size.get('data_mb', 0)} MB")
        mc3.metric("Index Size", f"{size.get('index_mb', 0)} MB")
        mc4.metric("Schedule", info.schedule)

        last_refresh = fresh.get("last_refreshed")
        mc5.metric(
            "Last Refresh",
            last_refresh.strftime("%H:%M:%S") if isinstance(last_refresh, datetime) else "—",
            help=str(last_refresh) if last_refresh else "Never refreshed",
        )

        # Refresh button
        with mc6:
            st.write("")  # spacer
            if is_running:
                st.button("⏳ Refreshing...", key=f"btn_{tn}", disabled=True)
            else:
                if st.button("🔄 Refresh Now", key=f"btn_{tn}", type="primary", use_container_width=True):
                    with st.spinner(f"Refreshing {info.display_name}..."):
                        result = mgr.refresh(tn)
                    if result.get("refresh_status") == "SUCCESS":
                        st.success(
                            f"✅ Refreshed! {format_rows(result.get('row_count'))} rows "
                            f"in {format_duration(result.get('duration_sec'))}"
                        )
                        st.rerun()
                    elif result.get("refresh_status") == "SKIPPED":
                        st.info("⏭️ Skipped — another refresh is already running.")
                    else:
                        st.error(f"❌ Failed: {result.get('message') or result.get('error_message', 'Unknown error')}")

        # Description
        with st.expander("ℹ️ Details", expanded=False):
            st.markdown(f"**Description:** {info.description}")
            st.markdown(f"**Source View:** `{info.source_view}`")
            st.markdown(f"**Refresh Procedure:** `{info.refresh_procedure}`")
            if info.tags:
                st.markdown(f"**Tags:** {', '.join(f'`{t}`' for t in info.tags)}")

st.divider()

# =====================================================================
# Refresh History & Health
# =====================================================================

st.subheader("📋 Refresh History")

# Filters
fil_col1, fil_col2, fil_col3, fil_col4 = st.columns([2, 2, 2, 1])

with fil_col1:
    table_options = ["All Tables"] + [t.table_name for t in tables]
    selected_table = st.selectbox(
        "Table",
        table_options,
        key="log_table_filter",
        label_visibility="collapsed",
    )

with fil_col2:
    status_options = ["All Status", "SUCCESS", "FAILED", "SKIPPED", "RUNNING"]
    selected_status = st.selectbox(
        "Status",
        status_options,
        key="log_status_filter",
        label_visibility="collapsed",
    )

with fil_col3:
    limit = st.selectbox(
        "Show",
        [25, 50, 100, 200],
        index=1,
        key="log_limit",
        label_visibility="collapsed",
    )

with fil_col4:
    if st.button("🔍 Load", use_container_width=True):
        pass  # triggers rerun

# Fetch logs
logs = mgr.get_refresh_logs(
    table_name=None if selected_table == "All Tables" else selected_table,
    limit=limit,
    status_filter=None if selected_status == "All Status" else selected_status,
)

if logs:
    df_logs = pd.DataFrame(logs)

    # Format columns
    df_logs["status"] = df_logs["status"].apply(lambda s: f"{status_icon(s)} {s}")
    df_logs["duration"] = df_logs["duration_sec"].apply(format_duration)
    df_logs["rows"] = df_logs["row_count"].apply(format_rows)
    df_logs["started_at"] = pd.to_datetime(df_logs["started_at"]).dt.strftime("%Y-%m-%d %H:%M:%S")
    df_logs["completed_at"] = pd.to_datetime(df_logs["completed_at"]).dt.strftime("%Y-%m-%d %H:%M:%S")

    display_cols = [
        "id", "table_name", "trigger_type", "status",
        "started_at", "completed_at", "duration", "rows", "error_message",
    ]
    existing_cols = [c for c in display_cols if c in df_logs.columns]

    st.dataframe(
        df_logs[existing_cols],
        use_container_width=True,
        hide_index=True,
        column_config={
            "id": st.column_config.NumberColumn("ID", width="small"),
            "table_name": st.column_config.TextColumn("Table", width="medium"),
            "trigger_type": st.column_config.TextColumn("Trigger", width="small"),
            "status": st.column_config.TextColumn("Status", width="small"),
            "started_at": st.column_config.TextColumn("Started", width="medium"),
            "completed_at": st.column_config.TextColumn("Completed", width="medium"),
            "duration": st.column_config.TextColumn("Duration", width="small"),
            "rows": st.column_config.TextColumn("Rows", width="small"),
            "error_message": st.column_config.TextColumn("Error", width="large"),
        },
    )

    # Health summary
    st.divider()
    st.subheader("📊 Health Summary (Last 24h)")

    health_col1, health_col2 = st.columns(2)

    for idx, tinfo in enumerate(tables):
        col = health_col1 if idx % 2 == 0 else health_col2
        with col:
            summary = mgr.get_health_summary(tinfo.table_name, hours=24)
            with st.container(border=True):
                st.markdown(f"**{tinfo.display_name}**")
                st.caption(f"Total refreshes: {summary['total_refreshes']}")

                scol1, scol2, scol3, scol4 = st.columns(4)

                success = summary["statuses"].get("SUCCESS", {})
                failed = summary["statuses"].get("FAILED", {})
                skipped = summary["statuses"].get("SKIPPED", {})

                scol1.metric("✅ Success", success.get("cnt", 0))
                scol2.metric("❌ Failed", failed.get("cnt", 0))
                scol3.metric("⏭️ Skipped", skipped.get("cnt", 0))
                scol4.metric(
                    "⏱️ Avg Duration",
                    format_duration(success.get("avg_duration")),
                )
else:
    st.info("No refresh logs found. Trigger a refresh to see history.")


# =====================================================================
# Schema Explorer
# =====================================================================

st.divider()

with st.expander("🔍 Schema Explorer", expanded=False):
    schema_table = st.selectbox(
        "Select table to explore",
        [t.table_name for t in tables],
        key="schema_table",
    )

    if schema_table:
        tab_cols, tab_idx = st.tabs(["📋 Columns", "🔑 Indexes"])

        with tab_cols:
            columns = mgr.get_table_columns(schema_table)
            if columns:
                df_cols = pd.DataFrame(columns)
                st.dataframe(df_cols, use_container_width=True, hide_index=True)
            else:
                st.warning("Table not found or no columns.")

        with tab_idx:
            indexes = mgr.get_table_indexes(schema_table)
            if indexes:
                df_idx = pd.DataFrame(indexes)
                st.dataframe(df_idx, use_container_width=True, hide_index=True)
            else:
                st.warning("No indexes found.")


# =====================================================================
# Dependency Analysis
# =====================================================================

st.divider()

with st.expander("🔗 Dependency Analysis", expanded=False):
    st.markdown(
        "Find all **database objects** (views, procedures, events, triggers) "
        "and **Python files** that still reference the **source view** — "
        "these need to be migrated to the materialized table."
    )

    dep_table = st.selectbox(
        "Select materialized table",
        [t.table_name for t in tables],
        key="dep_table",
    )

    if dep_table:
        dep_info = mgr.get_table_info(dep_table)

        st.markdown(
            f"Scanning for references to **`{dep_info.source_view}`** → "
            f"should be migrated to **`{dep_info.table_name}`**"
        )

        # ── DB Dependencies ──
        st.markdown("#### 🗃️ Database Objects")

        deps = mgr.get_dependencies(dep_table)

        if deps:
            def migration_badge(status):
                badges = {
                    "migrated": "✅ Migrated",
                    "partial": "⚠️ Partial (uses both)",
                    "not_migrated": "🔴 Not migrated",
                }
                return badges.get(status, status)

            df_deps = pd.DataFrame(deps)
            df_deps["migration_status"] = df_deps["migration_status"].apply(migration_badge)

            # Summary counts
            dep_c1, dep_c2, dep_c3 = st.columns(3)
            not_migrated = sum(1 for d in deps if d["migration_status"] == "not_migrated")
            partial = sum(1 for d in deps if d["migration_status"] == "partial")
            migrated = sum(1 for d in deps if d["migration_status"] == "migrated")

            dep_c1.metric("🔴 Not Migrated", not_migrated)
            dep_c2.metric("⚠️ Partial", partial)
            dep_c3.metric("✅ Migrated", migrated)

            st.dataframe(
                df_deps[["object_type", "object_name", "migration_status"]],
                use_container_width=True,
                hide_index=True,
                column_config={
                    "object_type": st.column_config.TextColumn("Type", width="small"),
                    "object_name": st.column_config.TextColumn("Object Name", width="medium"),
                    "migration_status": st.column_config.TextColumn("Migration Status", width="medium"),
                },
            )
        else:
            st.success("✅ No database objects reference the source view — all clear!")

        # ── Python File References ──
        st.markdown("#### 🐍 Python File References")

        app_refs = mgr.get_app_references(dep_table)

        if app_refs:
            st.warning(f"Found **{len(app_refs)}** reference(s) to `{dep_info.source_view}` in Python files:")
            df_refs = pd.DataFrame(app_refs)
            st.dataframe(
                df_refs,
                use_container_width=True,
                hide_index=True,
                column_config={
                    "file_path": st.column_config.TextColumn("File", width="medium"),
                    "line_number": st.column_config.NumberColumn("Line", width="small"),
                    "line_content": st.column_config.TextColumn("Content", width="large"),
                },
            )
        else:
            st.success("✅ No Python files reference the source view — all migrated!")


# =====================================================================
# Maintenance
# =====================================================================

st.divider()

with st.expander("🧹 Maintenance", expanded=False):
    st.markdown("**Clean up old refresh logs**")
    maint_col1, maint_col2 = st.columns([2, 1])

    with maint_col1:
        cleanup_days = st.number_input(
            "Delete logs older than (days)",
            min_value=7,
            max_value=365,
            value=30,
            key="cleanup_days",
        )

    with maint_col2:
        st.write("")  # spacer
        st.write("")
        if st.button("🗑️ Clean Up", key="btn_cleanup"):
            deleted = mgr.cleanup_old_logs(days=cleanup_days)
            if deleted > 0:
                st.success(f"Deleted {deleted} old log entries.")
            else:
                st.info("No old logs to clean up.")