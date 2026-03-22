# utils/salesperson_performance/perf_logger.py
"""
Unified Performance Logger for Salesperson Performance Module.

Replaces scattered DEBUG_TIMING / DEBUG_VERBOSE / DEBUG_QUERY_TIMING flags
across 6+ files with ONE centralized, structured performance tracking system.

=== BEFORE (scattered across files) ===
- 1___Salesperson_Performance.py : DEBUG_TIMING, DEBUG_VERBOSE, _timing_log, timer(), print_timing_summary()
- queries.py                    : DEBUG_QUERY_TIMING (separate flag)
- metrics.py                    : DEBUG_METRICS_TIMING (separate flag)
- complex_kpi_calculator.py     : DEBUG_TIMING (yet another flag)
- sidebar_options_extractor.py  : DEBUG_TIMING (yet another flag)
  → 5 independent flags, inconsistent print formats, no structured data

=== AFTER (this module) ===
- Single import: from .perf_logger import perf, PerfCategory
- Single config: PERF_ENABLED / PERF_VERBOSE in ONE place
- Structured collection: category, label, duration, rows, metadata
- Clean summary table sorted by duration
- SQL query ref tracking with row counts
- Export-friendly data for further analysis

Usage:
    from utils.salesperson_performance.perf_logger import perf, PerfCategory as PC

    # Context manager (most common)
    with perf.track("get_sales_raw", PC.SQL, rows=len(df)):
        df = queries.get_sales_raw(...)

    # Manual start/stop (for conditional paths)
    token = perf.start("filter_data", PC.PANDAS)
    ...
    perf.stop(token, rows=len(result))

    # SQL query ref (automatic in _execute_query)
    perf.log_sql("sales_data", elapsed=1.23, rows=15000, query_hint="unified_sales_by_salesperson_view")

    # Cache events
    perf.log_cache_hit("sidebar_options")
    perf.log_cache_miss("raw_data", reason="year range expanded")

    # Print summary at end of page load
    perf.summary()

    # Get structured data for analysis
    records = perf.export()

VERSION: 1.0.0
"""

import time
import logging
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# =============================================================================
# CONFIGURATION — THE ONLY PLACE TO CHANGE
# =============================================================================

# Master switch: enable/disable all performance tracking
PERF_ENABLED = True

# Verbose mode: print each step as it happens (noisy but useful for debugging)
PERF_VERBOSE = False

# SQL detail: print SQL query hints and row counts
PERF_SQL_DETAIL = True

# Summary at page end: print the waterfall summary table
PERF_SUMMARY = True

# Slow threshold (seconds): highlight steps slower than this
SLOW_THRESHOLD = 1.0

# Very slow threshold (seconds): flag as critical
VERY_SLOW_THRESHOLD = 3.0


# =============================================================================
# CATEGORIES
# =============================================================================

class PerfCategory(str, Enum):
    """Categories for performance tracking entries."""
    INIT = "INIT"          # Initialization (auth, access control, DB check)
    SQL = "SQL"            # Database queries
    PANDAS = "PANDAS"      # In-memory Pandas operations
    CACHE = "CACHE"        # Cache operations (hit/miss/clear)
    METRICS = "METRICS"    # KPI & metrics calculations
    RENDER = "RENDER"      # UI rendering & fragment execution
    FILTER = "FILTER"      # Client-side filtering
    EXPORT = "EXPORT"      # Report generation
    OTHER = "OTHER"        # Anything else


# Short aliases for compact usage
PC = PerfCategory


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class PerfRecord:
    """Single performance measurement record."""
    label: str
    category: PerfCategory
    duration: float                    # seconds
    timestamp: float                   # time.perf_counter() at start
    wall_time: str                     # human-readable wall clock time
    rows: Optional[int] = None         # row count (for SQL/Pandas results)
    metadata: Dict[str, Any] = field(default_factory=dict)
    # For SQL tracking
    query_hint: Optional[str] = None   # table/view name for SQL queries

    @property
    def is_slow(self) -> bool:
        return self.duration >= SLOW_THRESHOLD

    @property
    def is_very_slow(self) -> bool:
        return self.duration >= VERY_SLOW_THRESHOLD

    @property
    def severity_icon(self) -> str:
        if self.is_very_slow:
            return "🔴"
        elif self.is_slow:
            return "🟡"
        return "🟢"


@dataclass
class CacheEvent:
    """Cache hit/miss event."""
    key: str
    hit: bool
    timestamp: float
    wall_time: str
    reason: Optional[str] = None   # for misses: why


# =============================================================================
# MAIN PERFORMANCE LOGGER CLASS
# =============================================================================

class PerformanceLogger:
    """
    Centralized performance tracking for the Salesperson Performance module.

    Thread-safe for Streamlit's execution model (single-threaded per session).
    Call reset() at the start of each page load to clear previous data.
    """

    def __init__(self):
        self._records: List[PerfRecord] = []
        self._cache_events: List[CacheEvent] = []
        self._page_start: Optional[float] = None
        self._page_start_wall: Optional[str] = None
        self._active_tokens: Dict[int, float] = {}  # token_id → start_time
        self._next_token: int = 0

    # =========================================================================
    # LIFECYCLE
    # =========================================================================

    def reset(self):
        """Reset all records. Call at the start of each page load."""
        self._records.clear()
        self._cache_events.clear()
        self._page_start = time.perf_counter()
        self._page_start_wall = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        self._active_tokens.clear()
        self._next_token = 0
        if PERF_ENABLED and PERF_VERBOSE:
            print(f"\n{'='*70}")
            print(f"⏱️  PERF LOGGER RESET @ {self._page_start_wall}")
            print(f"{'='*70}")

    # =========================================================================
    # CONTEXT MANAGER — Primary API
    # =========================================================================

    @contextmanager
    def track(
        self,
        label: str,
        category: PerfCategory = PerfCategory.OTHER,
        rows: Optional[int] = None,
        query_hint: Optional[str] = None,
        **metadata
    ):
        """
        Context manager for timing a code block.

        Usage:
            with perf.track("get_sales_raw", PC.SQL) as t:
                df = queries.get_sales_raw(...)
            # optionally set rows after: t.rows = len(df)

        Or with rows known upfront:
            with perf.track("filter_sales", PC.PANDAS, rows=len(df)):
                ...
        """
        if not PERF_ENABLED:
            yield _TrackContext()
            return

        ctx = _TrackContext()
        start = time.perf_counter()
        wall = datetime.now().strftime("%H:%M:%S.%f")[:-3]

        try:
            yield ctx
        finally:
            elapsed = time.perf_counter() - start
            final_rows = ctx.rows if ctx.rows is not None else rows
            final_hint = ctx.query_hint or query_hint
            final_meta = {**metadata, **ctx.metadata}

            record = PerfRecord(
                label=label,
                category=category,
                duration=elapsed,
                timestamp=start,
                wall_time=wall,
                rows=final_rows,
                metadata=final_meta,
                query_hint=final_hint,
            )
            self._records.append(record)

            if PERF_VERBOSE:
                self._print_record(record)

    # =========================================================================
    # MANUAL START/STOP — For conditional paths
    # =========================================================================

    def start(self, label: str, category: PerfCategory = PerfCategory.OTHER) -> int:
        """Start timing. Returns a token to pass to stop()."""
        if not PERF_ENABLED:
            return -1
        token = self._next_token
        self._next_token += 1
        self._active_tokens[token] = (time.perf_counter(), label, category,
                                       datetime.now().strftime("%H:%M:%S.%f")[:-3])
        return token

    def stop(self, token: int, rows: Optional[int] = None, **metadata):
        """Stop timing for the given token."""
        if not PERF_ENABLED or token < 0 or token not in self._active_tokens:
            return
        start_time, label, category, wall = self._active_tokens.pop(token)
        elapsed = time.perf_counter() - start_time
        record = PerfRecord(
            label=label, category=category, duration=elapsed,
            timestamp=start_time, wall_time=wall, rows=rows, metadata=metadata,
        )
        self._records.append(record)
        if PERF_VERBOSE:
            self._print_record(record)

    # =========================================================================
    # SPECIALIZED LOGGERS
    # =========================================================================

    def log_sql(
        self,
        query_name: str,
        elapsed: float,
        rows: int = 0,
        query_hint: str = None,
    ):
        """
        Log a SQL query execution (called from _execute_query).

        Args:
            query_name: Identifier for the query (e.g., "sales_data", "backlog_detail")
            elapsed: Duration in seconds
            rows: Number of rows returned
            query_hint: Table/view name (e.g., "unified_sales_by_salesperson_view")
        """
        if not PERF_ENABLED:
            return
        record = PerfRecord(
            label=f"SQL: {query_name}",
            category=PerfCategory.SQL,
            duration=elapsed,
            timestamp=time.perf_counter() - elapsed,
            wall_time=datetime.now().strftime("%H:%M:%S.%f")[:-3],
            rows=rows,
            query_hint=query_hint,
        )
        self._records.append(record)
        if PERF_VERBOSE or PERF_SQL_DETAIL:
            self._print_record(record)

    def log_cache_hit(self, key: str):
        """Log a cache hit event."""
        if not PERF_ENABLED:
            return
        self._cache_events.append(CacheEvent(
            key=key, hit=True,
            timestamp=time.perf_counter(),
            wall_time=datetime.now().strftime("%H:%M:%S.%f")[:-3],
        ))
        if PERF_VERBOSE:
            print(f"   ♻️  CACHE HIT: {key}")

    def log_cache_miss(self, key: str, reason: str = None):
        """Log a cache miss event."""
        if not PERF_ENABLED:
            return
        self._cache_events.append(CacheEvent(
            key=key, hit=False,
            timestamp=time.perf_counter(),
            wall_time=datetime.now().strftime("%H:%M:%S.%f")[:-3],
            reason=reason,
        ))
        if PERF_VERBOSE:
            msg = f"   💾  CACHE MISS: {key}"
            if reason:
                msg += f" ({reason})"
            print(msg)

    def log_event(self, label: str, category: PerfCategory = PerfCategory.OTHER, **metadata):
        """Log a zero-duration event (milestone marker)."""
        if not PERF_ENABLED:
            return
        record = PerfRecord(
            label=label, category=category, duration=0.0,
            timestamp=time.perf_counter(),
            wall_time=datetime.now().strftime("%H:%M:%S.%f")[:-3],
            metadata=metadata,
        )
        self._records.append(record)
        if PERF_VERBOSE:
            print(f"   📌  {label}")

    # =========================================================================
    # SUMMARY OUTPUT
    # =========================================================================

    def summary(self):
        """Print formatted performance summary table."""
        if not PERF_ENABLED or not PERF_SUMMARY:
            return
        if not self._records:
            return

        total = sum(r.duration for r in self._records)
        page_elapsed = (time.perf_counter() - self._page_start) if self._page_start else total

        # Header
        print(f"\n{'='*90}")
        print(f"📊 PERFORMANCE SUMMARY  |  Page total: {page_elapsed:.2f}s  |  "
              f"Tracked: {total:.2f}s  |  Steps: {len(self._records)}")
        print(f"{'='*90}")

        # Column headers
        hdr = (f"{'':3} {'Category':<8} {'Label':<40} "
               f"{'Duration':>8} {'%':>6} {'Rows':>10} {'Note'}")
        print(hdr)
        print(f"{'─'*90}")

        # Sort by timestamp (execution order)
        for r in self._records:
            if r.duration == 0.0:
                continue  # skip event markers in summary
            pct = (r.duration / total * 100) if total > 0 else 0
            rows_str = f"{r.rows:>10,}" if r.rows is not None else f"{'':>10}"
            note = r.query_hint or ""
            if r.is_very_slow:
                note = f"🔴 SLOW  {note}"
            elif r.is_slow:
                note = f"🟡 slow  {note}"
            cat_str = r.category.value[:8].ljust(8)

            print(f"{r.severity_icon:3} {cat_str} {r.label:<40} "
                  f"{r.duration:>7.3f}s {pct:>5.1f}% {rows_str} {note}")

        # Totals by category
        print(f"{'─'*90}")

        cat_totals = {}
        for r in self._records:
            cat = r.category.value
            cat_totals[cat] = cat_totals.get(cat, 0.0) + r.duration

        for cat, dur in sorted(cat_totals.items(), key=lambda x: -x[1]):
            pct = (dur / total * 100) if total > 0 else 0
            bar = "█" * int(pct / 2.5) + "░" * (40 - int(pct / 2.5))
            print(f"    {cat:<8} {dur:>7.3f}s ({pct:>5.1f}%)  {bar}")

        print(f"{'─'*90}")
        print(f"    {'TOTAL':<8} {total:>7.3f}s")

        # Cache summary
        if self._cache_events:
            hits = sum(1 for e in self._cache_events if e.hit)
            misses = sum(1 for e in self._cache_events if not e.hit)
            print(f"\n    Cache: {hits} hits, {misses} misses")
            for e in self._cache_events:
                if not e.hit:
                    reason_str = f" — {e.reason}" if e.reason else ""
                    print(f"      💾 MISS: {e.key}{reason_str}")

        # SQL query reference
        sql_records = [r for r in self._records if r.category == PerfCategory.SQL]
        if sql_records:
            print(f"\n    SQL Queries ({len(sql_records)} total, "
                  f"{sum(r.duration for r in sql_records):.2f}s):")
            for r in sorted(sql_records, key=lambda x: -x.duration):
                rows_str = f"{r.rows:,}" if r.rows is not None else "?"
                hint = f"  [{r.query_hint}]" if r.query_hint else ""
                print(f"      {r.severity_icon} {r.duration:.3f}s  {rows_str:>10} rows  "
                      f"{r.label}{hint}")

        print(f"{'='*90}\n")

    # =========================================================================
    # EXPORT — Structured data for analysis
    # =========================================================================

    def export(self) -> List[Dict]:
        """
        Export all records as list of dicts for further analysis.

        Can be used to:
        - Store in session_state for UI display
        - Write to JSON file for trend analysis
        - Feed into a monitoring dashboard
        """
        return [
            {
                "label": r.label,
                "category": r.category.value,
                "duration": round(r.duration, 4),
                "wall_time": r.wall_time,
                "rows": r.rows,
                "query_hint": r.query_hint,
                "is_slow": r.is_slow,
                "is_very_slow": r.is_very_slow,
                **r.metadata,
            }
            for r in self._records
        ]

    def export_cache_events(self) -> List[Dict]:
        """Export cache events as list of dicts."""
        return [
            {
                "key": e.key,
                "hit": e.hit,
                "wall_time": e.wall_time,
                "reason": e.reason,
            }
            for e in self._cache_events
        ]

    @property
    def total_duration(self) -> float:
        """Total tracked duration in seconds."""
        return sum(r.duration for r in self._records)

    @property
    def sql_duration(self) -> float:
        """Total SQL query duration in seconds."""
        return sum(r.duration for r in self._records if r.category == PerfCategory.SQL)

    @property
    def record_count(self) -> int:
        return len(self._records)

    # =========================================================================
    # INTERNALS
    # =========================================================================

    def _print_record(self, r: PerfRecord):
        """Print a single record in verbose mode."""
        rows_str = f" → {r.rows:,} rows" if r.rows is not None else ""
        hint_str = f"  [{r.query_hint}]" if r.query_hint else ""
        print(f"   {r.severity_icon} [{r.category.value:<6}] {r.label:<40} "
              f"{r.duration:.3f}s{rows_str}{hint_str}")


class _TrackContext:
    """Mutable context returned by track() for post-hoc metadata."""
    def __init__(self):
        self.rows: Optional[int] = None
        self.query_hint: Optional[str] = None
        self.metadata: Dict[str, Any] = {}


# =============================================================================
# MODULE-LEVEL SINGLETON
# =============================================================================

perf = PerformanceLogger()
"""Module-level singleton. Import and use directly:
    from utils.salesperson_performance.perf_logger import perf, PerfCategory as PC
"""
