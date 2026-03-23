# utils/materialization/manager.py
"""
Materialization Manager

Core logic for managing materialized tables in MySQL.
No Streamlit dependency — can be used from CLI, cron, or Streamlit.

Adding a new materialized table:
    1. Create the mat table + refresh procedure in SQL
    2. Add entry to MAT_REGISTRY below
    3. That's it — the manager page will pick it up automatically
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any
from sqlalchemy import text

from utils.db import get_db_engine

logger = logging.getLogger(__name__)


# =====================================================================
# Data Classes
# =====================================================================

@dataclass
class MatTableInfo:
    """Definition of a materialized table"""
    table_name: str
    display_name: str
    source_view: str
    refresh_procedure: str
    description: str
    schedule: str = "Every 1 hour"
    category: str = "General"
    owner: str = ""
    tags: List[str] = field(default_factory=list)


# =====================================================================
# Registry — ADD NEW MATERIALIZED TABLES HERE
# =====================================================================

MAT_REGISTRY: Dict[str, MatTableInfo] = {
    "mat_sales_invoice_full_looker": MatTableInfo(
        table_name="mat_sales_invoice_full_looker",
        display_name="Sales Invoice Full (Looker)",
        source_view="sales_invoice_full_looker_view",
        refresh_procedure="sp_refresh_mat_sales_invoice_looker",
        description=(
            "Full sales invoice details with GP calculation including "
            "landed cost, financing cost (cost-based), outbound logistics, "
            "commission, and adjusted GP1. Used by Looker dashboards and "
            "credit control apps."
        ),
        schedule="Every 1 hour",
        category="Sales & Finance",
        tags=["sales", "invoice", "GP", "COGS", "looker", "credit-control"],
    ),
    # ─────────────────────────────────────────────────────────────────
    # ADD MORE MATERIALIZED TABLES BELOW:
    # ─────────────────────────────────────────────────────────────────
    # "mat_purchase_invoice_summary": MatTableInfo(
    #     table_name="mat_purchase_invoice_summary",
    #     display_name="Purchase Invoice Summary",
    #     source_view="purchase_invoice_summary_view",
    #     refresh_procedure="sp_refresh_mat_purchase_invoice_summary",
    #     description="...",
    #     category="Procurement",
    #     tags=["purchase", "invoice"],
    # ),
}


# =====================================================================
# Manager Class
# =====================================================================

class MatManager:
    """
    Manager for all materialized tables.
    
    Usage:
        mgr = MatManager()
        
        # List all registered tables
        for info in mgr.list_tables():
            print(info.display_name)
        
        # Refresh a specific table
        result = mgr.refresh("mat_sales_invoice_full_looker")
        
        # Check freshness
        freshness = mgr.get_freshness("mat_sales_invoice_full_looker")
    """

    def __init__(self):
        self.registry = MAT_REGISTRY

    # ─────────────────────────────────────────────────────────
    # Registry
    # ─────────────────────────────────────────────────────────

    def list_tables(self) -> List[MatTableInfo]:
        """List all registered materialized tables"""
        return list(self.registry.values())

    def get_table_info(self, table_name: str) -> Optional[MatTableInfo]:
        """Get info for a specific materialized table"""
        return self.registry.get(table_name)

    # ─────────────────────────────────────────────────────────
    # Freshness
    # ─────────────────────────────────────────────────────────

    def get_freshness(self, table_name: str) -> Dict[str, Any]:
        """
        Get data freshness for a materialized table.
        
        Returns:
            Dict with keys: last_refreshed, minutes_ago, total_rows, exists
        """
        engine = get_db_engine()
        try:
            with engine.connect() as conn:
                # First check if table exists
                check = conn.execute(text("""
                    SELECT COUNT(*) AS cnt 
                    FROM information_schema.TABLES 
                    WHERE TABLE_SCHEMA = DATABASE() 
                      AND TABLE_NAME = :tbl
                """), {"tbl": table_name}).fetchone()

                if not check or check.cnt == 0:
                    return {
                        "exists": False,
                        "last_refreshed": None,
                        "minutes_ago": None,
                        "total_rows": 0,
                    }

                row = conn.execute(text(f"""
                    SELECT 
                        MAX(_mat_refreshed_at) AS last_refreshed,
                        TIMESTAMPDIFF(MINUTE, MAX(_mat_refreshed_at), NOW()) AS minutes_ago,
                        COUNT(*) AS total_rows
                    FROM `{table_name}`
                """)).fetchone()

                return {
                    "exists": True,
                    "last_refreshed": row.last_refreshed if row else None,
                    "minutes_ago": row.minutes_ago if row else None,
                    "total_rows": row.total_rows if row else 0,
                }
        except Exception as e:
            logger.error(f"Error checking freshness for {table_name}: {e}")
            return {
                "exists": False,
                "last_refreshed": None,
                "minutes_ago": None,
                "total_rows": 0,
                "error": str(e),
            }

    def get_all_freshness(self) -> Dict[str, Dict[str, Any]]:
        """Get freshness for all registered tables"""
        result = {}
        for table_name in self.registry:
            result[table_name] = self.get_freshness(table_name)
        return result

    # ─────────────────────────────────────────────────────────
    # Refresh
    # ─────────────────────────────────────────────────────────

    def refresh(self, table_name: str) -> Dict[str, Any]:
        """
        Trigger on-demand refresh for a materialized table.
        
        Returns:
            Dict with refresh_status, row_count, duration_sec
        """
        info = self.registry.get(table_name)
        if not info:
            return {"refresh_status": "ERROR", "message": f"Unknown table: {table_name}"}

        engine = get_db_engine()
        try:
            with engine.connect() as conn:
                # Call the stored procedure
                conn.execute(text(f"CALL `{info.refresh_procedure}`('ON_DEMAND')"))
                conn.commit()

                # Fetch result (the SP returns a result set)
                # Since we already committed, read from log
                log = conn.execute(text("""
                    SELECT status, row_count, duration_sec, error_message
                    FROM mat_refresh_log
                    WHERE table_name = :tbl
                    ORDER BY id DESC
                    LIMIT 1
                """), {"tbl": table_name}).fetchone()

                if log:
                    return {
                        "refresh_status": log.status,
                        "row_count": log.row_count,
                        "duration_sec": float(log.duration_sec) if log.duration_sec else None,
                        "error_message": log.error_message,
                    }
                return {"refresh_status": "UNKNOWN"}

        except Exception as e:
            logger.error(f"Refresh failed for {table_name}: {e}")
            return {"refresh_status": "ERROR", "message": str(e)}

    def is_refreshing(self, table_name: str) -> bool:
        """Check if a refresh is currently running"""
        engine = get_db_engine()
        try:
            with engine.connect() as conn:
                row = conn.execute(text("""
                    SELECT COUNT(*) AS cnt
                    FROM mat_refresh_log
                    WHERE table_name = :tbl
                      AND status = 'RUNNING'
                      AND started_at > DATE_SUB(NOW(), INTERVAL 30 MINUTE)
                """), {"tbl": table_name}).fetchone()
                return row and row.cnt > 0
        except Exception:
            return False

    # ─────────────────────────────────────────────────────────
    # Logs & History
    # ─────────────────────────────────────────────────────────

    def get_refresh_logs(
        self, 
        table_name: str = None, 
        limit: int = 50,
        status_filter: str = None,
    ) -> List[Dict[str, Any]]:
        """
        Get refresh log entries.
        
        Args:
            table_name: Filter by table (None = all)
            limit: Max rows to return
            status_filter: Filter by status (SUCCESS, FAILED, SKIPPED, RUNNING)
        """
        engine = get_db_engine()
        try:
            conditions = ["1=1"]
            params = {"limit_val": limit}

            if table_name:
                conditions.append("table_name = :tbl")
                params["tbl"] = table_name
            if status_filter:
                conditions.append("status = :status")
                params["status"] = status_filter

            where = " AND ".join(conditions)

            with engine.connect() as conn:
                rows = conn.execute(text(f"""
                    SELECT 
                        id, table_name, trigger_type, status,
                        started_at, completed_at, duration_sec,
                        row_count, error_message
                    FROM mat_refresh_log
                    WHERE {where}
                    ORDER BY id DESC
                    LIMIT :limit_val
                """), params).fetchall()

                return [dict(r._mapping) for r in rows]

        except Exception as e:
            logger.error(f"Error fetching refresh logs: {e}")
            return []

    def get_health_summary(
        self, 
        table_name: str = None, 
        hours: int = 24
    ) -> Dict[str, Any]:
        """
        Get refresh health summary for last N hours.
        
        Returns:
            Dict with success_count, fail_count, avg_duration, etc.
        """
        engine = get_db_engine()
        try:
            conditions = ["started_at > DATE_SUB(NOW(), INTERVAL :hours HOUR)"]
            params = {"hours": hours}

            if table_name:
                conditions.append("table_name = :tbl")
                params["tbl"] = table_name

            where = " AND ".join(conditions)

            with engine.connect() as conn:
                rows = conn.execute(text(f"""
                    SELECT 
                        status,
                        COUNT(*) AS cnt,
                        ROUND(AVG(duration_sec), 2) AS avg_duration,
                        ROUND(MAX(duration_sec), 2) AS max_duration,
                        ROUND(MIN(duration_sec), 2) AS min_duration,
                        MIN(row_count) AS min_rows,
                        MAX(row_count) AS max_rows
                    FROM mat_refresh_log
                    WHERE {where}
                    GROUP BY status
                """), params).fetchall()

                summary = {
                    "period_hours": hours,
                    "statuses": {},
                    "total_refreshes": 0,
                }
                for r in rows:
                    d = dict(r._mapping)
                    summary["statuses"][d["status"]] = d
                    summary["total_refreshes"] += d["cnt"]

                return summary

        except Exception as e:
            logger.error(f"Error fetching health summary: {e}")
            return {"period_hours": hours, "statuses": {}, "total_refreshes": 0, "error": str(e)}

    # ─────────────────────────────────────────────────────────
    # Schema / Table Info
    # ─────────────────────────────────────────────────────────

    def get_table_columns(self, table_name: str) -> List[Dict[str, Any]]:
        """Get column definitions for a materialized table"""
        engine = get_db_engine()
        try:
            with engine.connect() as conn:
                rows = conn.execute(text("""
                    SELECT 
                        COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, 
                        COLUMN_KEY, COLUMN_COMMENT
                    FROM information_schema.COLUMNS
                    WHERE TABLE_SCHEMA = DATABASE()
                      AND TABLE_NAME = :tbl
                    ORDER BY ORDINAL_POSITION
                """), {"tbl": table_name}).fetchall()
                return [dict(r._mapping) for r in rows]
        except Exception as e:
            logger.error(f"Error fetching columns for {table_name}: {e}")
            return []

    def get_table_indexes(self, table_name: str) -> List[Dict[str, Any]]:
        """Get index definitions for a materialized table"""
        engine = get_db_engine()
        try:
            with engine.connect() as conn:
                rows = conn.execute(text("""
                    SELECT 
                        INDEX_NAME, 
                        GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX) AS columns,
                        NON_UNIQUE,
                        INDEX_TYPE
                    FROM information_schema.STATISTICS
                    WHERE TABLE_SCHEMA = DATABASE()
                      AND TABLE_NAME = :tbl
                    GROUP BY INDEX_NAME, NON_UNIQUE, INDEX_TYPE
                    ORDER BY INDEX_NAME
                """), {"tbl": table_name}).fetchall()
                return [dict(r._mapping) for r in rows]
        except Exception as e:
            logger.error(f"Error fetching indexes for {table_name}: {e}")
            return []

    def get_table_size(self, table_name: str) -> Dict[str, Any]:
        """Get table storage size"""
        engine = get_db_engine()
        try:
            with engine.connect() as conn:
                row = conn.execute(text("""
                    SELECT 
                        ROUND(DATA_LENGTH / 1024 / 1024, 2) AS data_mb,
                        ROUND(INDEX_LENGTH / 1024 / 1024, 2) AS index_mb,
                        ROUND((DATA_LENGTH + INDEX_LENGTH) / 1024 / 1024, 2) AS total_mb,
                        TABLE_ROWS AS est_rows
                    FROM information_schema.TABLES
                    WHERE TABLE_SCHEMA = DATABASE()
                      AND TABLE_NAME = :tbl
                """), {"tbl": table_name}).fetchone()

                if row:
                    return dict(row._mapping)
                return {"data_mb": 0, "index_mb": 0, "total_mb": 0, "est_rows": 0}
        except Exception as e:
            return {"data_mb": 0, "index_mb": 0, "total_mb": 0, "est_rows": 0, "error": str(e)}

    # ─────────────────────────────────────────────────────────
    # Dependency Analysis
    # ─────────────────────────────────────────────────────────

    def get_dependencies(self, table_name: str) -> List[Dict[str, Any]]:
        """
        Find all database objects that reference the SOURCE VIEW
        of a materialized table.
        
        Searches: views, stored procedures, functions, events, triggers.
        
        Returns:
            List of dicts with object_type, object_name, and migration_status
        """
        info = self.registry.get(table_name)
        if not info:
            return []

        source_view = info.source_view
        mat_table = info.table_name
        engine = get_db_engine()

        try:
            with engine.connect() as conn:
                rows = conn.execute(text("""
                    SELECT 'VIEW' AS object_type, v.TABLE_NAME AS object_name,
                           v.VIEW_DEFINITION AS definition
                    FROM information_schema.VIEWS v
                    WHERE v.TABLE_SCHEMA = DATABASE()
                      AND v.VIEW_DEFINITION LIKE CONCAT('%%', :source_view, '%%')
                      AND v.TABLE_NAME <> :source_view

                    UNION ALL

                    SELECT r.ROUTINE_TYPE, r.ROUTINE_NAME, r.ROUTINE_DEFINITION
                    FROM information_schema.ROUTINES r
                    WHERE r.ROUTINE_SCHEMA = DATABASE()
                      AND r.ROUTINE_DEFINITION LIKE CONCAT('%%', :source_view, '%%')

                    UNION ALL

                    SELECT 'EVENT', e.EVENT_NAME, e.EVENT_DEFINITION
                    FROM information_schema.EVENTS e
                    WHERE e.EVENT_SCHEMA = DATABASE()
                      AND e.EVENT_DEFINITION LIKE CONCAT('%%', :source_view, '%%')

                    UNION ALL

                    SELECT 'TRIGGER', t.TRIGGER_NAME, t.ACTION_STATEMENT
                    FROM information_schema.TRIGGERS t
                    WHERE t.TRIGGER_SCHEMA = DATABASE()
                      AND t.ACTION_STATEMENT LIKE CONCAT('%%', :source_view, '%%')

                    ORDER BY object_type, object_name
                """), {"source_view": source_view}).fetchall()

                results = []
                for r in rows:
                    d = dict(r._mapping)
                    definition = d.pop("definition", "") or ""
                    
                    # Check if this object ALSO references the mat table
                    # → already migrated (or uses both)
                    uses_mat = mat_table in definition
                    uses_source = source_view in definition

                    if uses_mat and not uses_source:
                        status = "migrated"
                    elif uses_mat and uses_source:
                        status = "partial"
                    else:
                        status = "not_migrated"

                    d["migration_status"] = status
                    results.append(d)

                return results

        except Exception as e:
            logger.error(f"Error checking dependencies for {table_name}: {e}")
            return []

    def get_app_references(self, table_name: str, search_dir: str = None) -> List[Dict[str, str]]:
        """
        Scan Python files for references to the source view name.
        Helps find app-level queries that need migration.
        
        Args:
            table_name: Materialized table name
            search_dir: Directory to scan (default: project root)
            
        Returns:
            List of dicts with file_path, line_number, line_content
        """
        import os

        info = self.registry.get(table_name)
        if not info:
            return []

        source_view = info.source_view
        
        if search_dir is None:
            # Default: go up from utils/materialization/ to project root
            search_dir = os.path.abspath(
                os.path.join(os.path.dirname(__file__), "..", "..")
            )

        results = []
        try:
            for root, dirs, files in os.walk(search_dir):
                # Skip common non-relevant dirs
                dirs[:] = [d for d in dirs if d not in {
                    "__pycache__", ".git", "node_modules", ".venv", "venv", ".mypy_cache"
                }]
                for fname in files:
                    if not fname.endswith(".py"):
                        continue
                    fpath = os.path.join(root, fname)
                    try:
                        with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                            for i, line in enumerate(f, 1):
                                if source_view in line:
                                    results.append({
                                        "file_path": os.path.relpath(fpath, search_dir),
                                        "line_number": i,
                                        "line_content": line.strip()[:200],
                                    })
                    except Exception:
                        continue
        except Exception as e:
            logger.error(f"Error scanning app references: {e}")

        return results

    # ─────────────────────────────────────────────────────────
    # Log Management
    # ─────────────────────────────────────────────────────────

    def cleanup_old_logs(self, days: int = 30) -> int:
        """Delete refresh logs older than N days"""
        engine = get_db_engine()
        try:
            with engine.connect() as conn:
                result = conn.execute(text("""
                    DELETE FROM mat_refresh_log 
                    WHERE started_at < DATE_SUB(NOW(), INTERVAL :days DAY)
                """), {"days": days})
                conn.commit()
                deleted = result.rowcount
                logger.info(f"Cleaned up {deleted} old log entries (older than {days} days)")
                return deleted
        except Exception as e:
            logger.error(f"Error cleaning up logs: {e}")
            return 0

    def check_log_table_exists(self) -> bool:
        """Check if mat_refresh_log table exists"""
        engine = get_db_engine()
        try:
            with engine.connect() as conn:
                row = conn.execute(text("""
                    SELECT COUNT(*) AS cnt
                    FROM information_schema.TABLES
                    WHERE TABLE_SCHEMA = DATABASE()
                      AND TABLE_NAME = 'mat_refresh_log'
                """)).fetchone()
                return row and row.cnt > 0
        except Exception:
            return False


# =====================================================================
# Singleton Access
# =====================================================================

_manager: Optional[MatManager] = None


def get_mat_manager() -> MatManager:
    """Get MatManager singleton"""
    global _manager
    if _manager is None:
        _manager = MatManager()
    return _manager