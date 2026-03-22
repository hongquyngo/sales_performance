# utils/kpi_center_performance/queries.py
"""
KPI Center Performance Data Queries

"""

import logging
import time
from datetime import date, datetime
from typing import List, Optional, Tuple, Dict
import pandas as pd
import streamlit as st
from sqlalchemy import text

from utils.db import get_db_engine
from .constants import LOOKBACK_YEARS, CACHE_TTL_SECONDS, DEBUG_QUERY_TIMING
from .access_control import AccessControl

logger = logging.getLogger(__name__)


class KPICenterQueries:
    """
    Data loading class for KPI Center performance.
    
    Usage:
        access = AccessControl(user_role)
        queries = KPICenterQueries(access)
        
        sales_df = queries.get_sales_data(start_date, end_date)
        targets_df = queries.get_kpi_targets(year)
    """
    
    def __init__(self, access_control: AccessControl):
        """
        Initialize with access control.
        
        Args:
            access_control: AccessControl instance for filtering
        """
        self.access = access_control
        self._engine = None
    
    @property
    def engine(self):
        """Lazy load database engine."""
        if self._engine is None:
            self._engine = get_db_engine()
        return self._engine
    
    # =========================================================================
    # KPI CENTER HIERARCHY HELPERS
    # Note: get_kpi_center_hierarchy() moved to setup/queries.py (v3.4.0)
    # Note: get_child_kpi_center_ids() removed v4.1.0 - use get_all_descendants() instead
    # =========================================================================
    
    # =========================================================================
    # CORE SALES DATA
    # =========================================================================
    
    def get_sales_data(
        self,
        start_date: date,
        end_date: date,
        kpi_center_ids: List[int] = None,
        entity_ids: List[int] = None,
        include_children: bool = True
    ) -> pd.DataFrame:
        """
        Get sales data aggregated by KPI Center.
        
        Args:
            start_date: Start of period
            end_date: End of period
            kpi_center_ids: Optional list of KPI Centers to filter
            entity_ids: Optional list of entity IDs to filter
            include_children: Include child KPI Centers in totals
            
        Returns:
            DataFrame with sales transactions
        """
        if not self.access.can_access_page():
            return pd.DataFrame()
        
        # Expand to include children if requested
        if kpi_center_ids:
            kpi_center_ids = self.access.validate_selected_kpi_centers(kpi_center_ids)
            if include_children:
                expanded_ids = set(kpi_center_ids)
                for parent_id in kpi_center_ids:
                    child_ids = self.get_all_descendants(parent_id, include_self=False)
                    expanded_ids.update(child_ids)
                kpi_center_ids = list(expanded_ids)
        else:
            kpi_center_ids = self.access.get_accessible_kpi_center_ids()
        
        if not kpi_center_ids:
            return pd.DataFrame()
        
        query = """
            SELECT 
                data_source,
                unified_line_id,
                kpi_center_id,
                kpi_center,
                kpi_type,
                split_rate_percent,
                inv_date,
                inv_number,
                vat_number,
                legal_entity,
                legal_entity_id,
                customer,
                customer_id,
                customer_code,
                customer_type,
                customer_po_number,
                oc_number,
                oc_date,
                product_id,
                product_pn,
                pt_code,
                brand,
                sales_by_kpi_center_usd,
                gross_profit_by_kpi_center_usd,
                gp1_by_kpi_center_usd,
                broker_commission_by_kpi_center_usd,
                invoice_month,
                invoice_year
            FROM unified_sales_by_kpi_center_view
            WHERE inv_date BETWEEN :start_date AND :end_date
              AND kpi_center_id IN :kpi_center_ids
        """
        
        params = {
            'start_date': start_date,
            'end_date': end_date,
            'kpi_center_ids': tuple(kpi_center_ids)
        }
        
        if entity_ids:
            query += " AND legal_entity_id IN :entity_ids"
            params['entity_ids'] = tuple(entity_ids)
        
        query += " ORDER BY inv_date DESC"
        
        return self._execute_query(query, params, "sales_data")
    
    # =========================================================================
    # BACKLOG RAW DATA
    # NOTE: get_lookback_sales_data() REMOVED in v4.0.0 - replaced by UnifiedDataLoader
    # NOTE: get_all_backlog_raw() REMOVED in v4.0.0 - replaced by UnifiedDataLoader
    # =========================================================================
    
    # =========================================================================
    # KPI TARGETS MULTI-YEAR
    # NOTE: get_kpi_targets_multi_year() REMOVED in v4.0.0 - replaced by UnifiedDataLoader
    # NOTE: get_previous_year_data() REMOVED in v4.0.0 - replaced by DataProcessor._extract_previous_year()
    # NOTE: get_kpi_center_list() REMOVED in v4.0.0 - replaced by UnifiedDataLoader._load_hierarchy()
    # NOTE: get_kpi_center_achievement_summary() REMOVED in v4.0.0 - not used
    # =========================================================================

    # =========================================================================
    # HIERARCHY METHODS - NEW v3.2.0
    # =========================================================================
    def get_hierarchy_with_levels(
        self,
        kpi_type: str = None,
        include_all_types: bool = False
    ) -> pd.DataFrame:
        """
        Get KPI Center hierarchy with calculated levels.
        
        NEW v3.2.0: Dynamic level calculation using recursive CTE.
        
        Args:
            kpi_type: Filter by KPI type (TERRITORY, BRAND, etc.)
            include_all_types: If True, include all types
            
        Returns:
            DataFrame with columns:
            - kpi_center_id, kpi_center_name, kpi_type
            - parent_center_id, level, is_leaf
            - path (for sorting/display)
        """
        query = """
            WITH RECURSIVE hierarchy AS (
                -- Base case: root nodes (no parent)
                SELECT 
                    kc.id as kpi_center_id,
                    kc.name as kpi_center_name,
                    kc.type as kpi_type,
                    kc.parent_center_id,
                    0 as level,
                    CAST(kc.name AS CHAR(1000)) as path
                FROM prostechvn.kpi_centers kc
                WHERE kc.parent_center_id IS NULL
                  AND kc.delete_flag = 0
                
                UNION ALL
                
                -- Recursive case: children
                SELECT 
                    kc.id,
                    kc.name,
                    kc.type,
                    kc.parent_center_id,
                    h.level + 1,
                    CONCAT(h.path, ' > ', kc.name)
                FROM prostechvn.kpi_centers kc
                INNER JOIN hierarchy h ON kc.parent_center_id = h.kpi_center_id
                WHERE kc.delete_flag = 0
            ),
            children_count AS (
                SELECT 
                    parent_center_id,
                    COUNT(*) as child_count
                FROM prostechvn.kpi_centers
                WHERE delete_flag = 0 AND parent_center_id IS NOT NULL
                GROUP BY parent_center_id
            )
            SELECT 
                h.kpi_center_id,
                h.kpi_center_name,
                h.kpi_type,
                h.parent_center_id,
                h.level,
                h.path,
                CASE WHEN cc.child_count IS NULL OR cc.child_count = 0 THEN 1 ELSE 0 END as is_leaf,
                COALESCE(cc.child_count, 0) as direct_children_count
            FROM hierarchy h
            LEFT JOIN children_count cc ON h.kpi_center_id = cc.parent_center_id
            WHERE 1=1
        """
        
        if kpi_type and not include_all_types:
            query += " AND h.kpi_type = :kpi_type"
        
        query += " ORDER BY h.level, h.path"
        
        params = {'kpi_type': kpi_type} if kpi_type else {}
        
        return self._execute_query(query, params, "hierarchy_with_levels")
    def get_all_descendants(
        self,
        kpi_center_id: int,
        include_self: bool = False
    ) -> List[int]:
        """
        Get all descendant KPI Center IDs for a given parent.
        
        NEW v3.2.0: Recursive descendant lookup.
        
        Args:
            kpi_center_id: Parent KPI Center ID
            include_self: Whether to include the parent itself
            
        Returns:
            List of descendant KPI Center IDs
        """
        query = """
            WITH RECURSIVE descendants AS (
                -- Start with direct children
                SELECT id as kpi_center_id
                FROM prostechvn.kpi_centers
                WHERE parent_center_id = :parent_id
                  AND delete_flag = 0
                
                UNION ALL
                
                -- Recursive: get children of children
                SELECT kc.id
                FROM prostechvn.kpi_centers kc
                INNER JOIN descendants d ON kc.parent_center_id = d.kpi_center_id
                WHERE kc.delete_flag = 0
            )
            SELECT kpi_center_id FROM descendants
        """
        
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text(query), {'parent_id': kpi_center_id})
                descendants = [row[0] for row in result]
                
                if include_self:
                    descendants.insert(0, kpi_center_id)
                
                return descendants
        except Exception as e:
            logger.error(f"Error getting descendants for {kpi_center_id}: {e}")
            return [kpi_center_id] if include_self else []
    
    def get_leaf_descendants(
        self,
        kpi_center_id: int
    ) -> List[int]:
        """
        Get only leaf (no children) descendants for a KPI Center.
        
        Used for parent progress calculation in metrics.py.
        
        Args:
            kpi_center_id: Parent KPI Center ID
            
        Returns:
            List of leaf descendant KPI Center IDs
        """
        query = """
            WITH RECURSIVE descendants AS (
                -- Start with the center itself
                SELECT 
                    id as kpi_center_id,
                    id as original_id
                FROM prostechvn.kpi_centers
                WHERE id = :parent_id
                  AND delete_flag = 0
                
                UNION ALL
                
                -- Recursive: get all descendants
                SELECT kc.id, d.original_id
                FROM prostechvn.kpi_centers kc
                INNER JOIN descendants d ON kc.parent_center_id = d.kpi_center_id
                WHERE kc.delete_flag = 0
            ),
            leaf_nodes AS (
                SELECT d.kpi_center_id
                FROM descendants d
                WHERE NOT EXISTS (
                    SELECT 1 FROM prostechvn.kpi_centers kc
                    WHERE kc.parent_center_id = d.kpi_center_id
                      AND kc.delete_flag = 0
                )
                AND d.kpi_center_id != :parent_id  -- Exclude parent itself
            )
            SELECT kpi_center_id FROM leaf_nodes
        """
        
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text(query), {'parent_id': kpi_center_id})
                return [row[0] for row in result]
        except Exception as e:
            logger.error(f"Error getting leaf descendants for {kpi_center_id}: {e}")
            return []

    def get_ancestors(
        self,
        kpi_center_id: int,
        include_self: bool = False
    ) -> List[int]:
        """
        Get all ancestor KPI Center IDs for a given center.
        
        NEW v3.2.0: For hierarchy traversal.
        
        Args:
            kpi_center_id: KPI Center ID
            include_self: Whether to include the center itself
            
        Returns:
            List of ancestor KPI Center IDs (from immediate parent to root)
        """
        query = """
            WITH RECURSIVE ancestors AS (
                -- Start with immediate parent
                SELECT parent_center_id as kpi_center_id, 1 as depth
                FROM prostechvn.kpi_centers
                WHERE id = :center_id
                  AND parent_center_id IS NOT NULL
                  AND delete_flag = 0
                
                UNION ALL
                
                -- Recursive: get parent of parent
                SELECT kc.parent_center_id, a.depth + 1
                FROM prostechvn.kpi_centers kc
                INNER JOIN ancestors a ON kc.id = a.kpi_center_id
                WHERE kc.parent_center_id IS NOT NULL
                  AND kc.delete_flag = 0
            )
            SELECT kpi_center_id FROM ancestors ORDER BY depth
        """
        
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text(query), {'center_id': kpi_center_id})
                ancestors = [row[0] for row in result]
                
                if include_self:
                    ancestors.insert(0, kpi_center_id)
                
                return ancestors
        except Exception as e:
            logger.error(f"Error getting ancestors for {kpi_center_id}: {e}")
            return [kpi_center_id] if include_self else []
    # =========================================================================
    # PAYMENT & AR DATA — NEW v6.1.0
    # UPDATED v6.1.1: Added get_payment_data_unified() — single query
    # =========================================================================

    def get_payment_data_unified(
        self,
        kpi_center_ids: List[int] = None,
        entity_ids: List[int] = None,
    ) -> pd.DataFrame:
        """
        Load ALL payment/AR data in a SINGLE query.

        NEW v6.1.1: Replaces 2 separate queries (get_ar_outstanding_data +
        get_payment_period_data) which each materialized the full view (~90s each).

        Single query: ~5s total. Caller splits into AR vs Period using Pandas.

        Args:
            kpi_center_ids: KPI Center filter
            entity_ids: Optional entity filter

        Returns:
            DataFrame with ALL invoice rows (all statuses).
            Caller filters by payment_status / inv_date in Pandas.
        """
        if not self.access.can_access_page():
            return pd.DataFrame()

        if not kpi_center_ids:
            kpi_center_ids = self.access.get_accessible_kpi_center_ids()

        if not kpi_center_ids:
            return pd.DataFrame()

        query = """
            SELECT *
            FROM customer_ar_by_kpi_center_view
            WHERE kpi_center_id IN :kpi_center_ids
        """
        params = {'kpi_center_ids': tuple(kpi_center_ids)}

        if entity_ids:
            query += " AND legal_entity_id IN :entity_ids"
            params['entity_ids'] = tuple(entity_ids)

        return self._execute_query(query, params, "payment_unified_by_kpc")

    def get_ar_outstanding_data(
        self,
        kpi_center_ids: List[int] = None,
        entity_ids: List[int] = None,
    ) -> pd.DataFrame:
        """
        Get ALL outstanding AR data (unpaid + partially paid).

        Uses customer_ar_by_kpi_center_view which provides:
        - Pre-calculated outstanding, collected amounts (split by KPI Center)
        - Aging buckets, days overdue
        - Payment status, ratio

        Args:
            kpi_center_ids: Optional KPI Center filter
            entity_ids: Optional entity filter

        Returns:
            DataFrame with AR line items
        """
        if not self.access.can_access_page():
            return pd.DataFrame()

        if not kpi_center_ids:
            kpi_center_ids = self.access.get_accessible_kpi_center_ids()

        if not kpi_center_ids:
            return pd.DataFrame()

        query = """
            SELECT *
            FROM customer_ar_by_kpi_center_view
            WHERE payment_status IN ('Unpaid', 'Partially Paid')
              AND kpi_center_id IN :kpi_center_ids
        """
        params = {'kpi_center_ids': tuple(kpi_center_ids)}

        if entity_ids:
            query += " AND legal_entity_id IN :entity_ids"
            params['entity_ids'] = tuple(entity_ids)

        query += " ORDER BY outstanding_by_kpi_center_usd DESC"

        return self._execute_query(query, params, "ar_outstanding_by_kpc")

    def get_payment_period_data(
        self,
        start_date: date,
        end_date: date,
        kpi_center_ids: List[int] = None,
        entity_ids: List[int] = None,
    ) -> pd.DataFrame:
        """
        Get payment data for invoices within a specific period.

        Args:
            start_date: Period start
            end_date: Period end
            kpi_center_ids: Optional KPI Center filter
            entity_ids: Optional entity filter

        Returns:
            DataFrame with payment line items for the period
        """
        if not self.access.can_access_page():
            return pd.DataFrame()

        if not kpi_center_ids:
            kpi_center_ids = self.access.get_accessible_kpi_center_ids()

        if not kpi_center_ids:
            return pd.DataFrame()

        query = """
            SELECT *
            FROM customer_ar_by_kpi_center_view
            WHERE inv_date BETWEEN :start_date AND :end_date
              AND kpi_center_id IN :kpi_center_ids
        """
        params = {
            'start_date': start_date,
            'end_date': end_date,
            'kpi_center_ids': tuple(kpi_center_ids),
        }

        if entity_ids:
            query += " AND legal_entity_id IN :entity_ids"
            params['entity_ids'] = tuple(entity_ids)

        query += " ORDER BY inv_date DESC"

        return self._execute_query(query, params, "payment_period_by_kpc")

    def get_payment_transactions(
        self,
        invoice_numbers: List[str],
    ) -> pd.DataFrame:
        """
        Get payment transaction details for specific invoices.

        Schema: customer_payment_details → sale_invoices (for invoice_number)
                customer_payment_details → customer_payments (for payment header)

        Args:
            invoice_numbers: List of invoice numbers

        Returns:
            DataFrame with payment transactions
        """
        if not invoice_numbers:
            return pd.DataFrame()

        query = """
            SELECT
                si.invoice_number AS inv_number,
                cp.payment_number,
                cp.received_date AS payment_received_date,
                cpd.sub_payment_total AS amount_received,
                cpd.sub_payment_total AS amount_received_raw,
                si_cur.code AS currency_code,
                CASE
                    WHEN COALESCE(ipi.payment_ratio, 0) >= 1 THEN 'Fully Paid'
                    WHEN COALESCE(ipi.payment_ratio, 0) > 0 THEN 'Partially Paid'
                    ELSE 'Unpaid'
                END AS payment_status,
                COALESCE(ipi.payment_ratio, 0) AS payment_ratio
            FROM customer_payment_details cpd
            INNER JOIN customer_payments cp 
                ON cpd.customer_payment_id = cp.id
                AND cp.delete_flag = 0
            INNER JOIN sale_invoices si 
                ON cpd.sale_invoice_id = si.id
                AND si.delete_flag = 0
            LEFT JOIN currencies si_cur 
                ON si.currency_id = si_cur.id
            LEFT JOIN (
                SELECT 
                    cpd2.sale_invoice_id,
                    ROUND(
                        SUM(cpd2.sub_payment_total) / NULLIF(MAX(si2.total_invoiced_amount), 0), 
                        4
                    ) AS payment_ratio
                FROM customer_payment_details cpd2
                INNER JOIN customer_payments cp2 ON cpd2.customer_payment_id = cp2.id
                INNER JOIN sale_invoices si2 ON cpd2.sale_invoice_id = si2.id
                WHERE cp2.delete_flag = 0 AND cpd2.delete_flag = 0
                GROUP BY cpd2.sale_invoice_id
            ) ipi ON si.id = ipi.sale_invoice_id
            WHERE cpd.delete_flag = 0
              AND si.invoice_number IN :invoice_numbers
            ORDER BY cp.received_date DESC
        """
        params = {'invoice_numbers': tuple(invoice_numbers)}
        return self._execute_query(query, params, "payment_transactions")

    def get_invoice_documents(
        self,
        invoice_numbers: List[str],
    ) -> pd.DataFrame:
        """
        Get document metadata for specific invoices.

        Uses medias table joined through sale_invoice_details → sale_invoices.
        Returns empty DataFrame if media tables not configured.

        Args:
            invoice_numbers: List of invoice numbers

        Returns:
            DataFrame with document info (filename, s3_key, doc_type)
        """
        if not invoice_numbers:
            return pd.DataFrame()

        # Try to query media attached to sale invoices
        # This query is defensive — returns empty if tables don't exist
        query = """
            SELECT
                m.id AS media_id,
                m.filename,
                m.s3_key,
                'invoice' AS doc_type,
                si.invoice_number
            FROM medias m
            INNER JOIN sale_invoices si 
                ON m.sale_invoice_id = si.id
                AND si.delete_flag = 0
            WHERE si.invoice_number IN :invoice_numbers
              AND (m.delete_flag = 0 OR m.delete_flag IS NULL)
            ORDER BY m.created_date DESC
        """
        try:
            params = {'invoice_numbers': tuple(invoice_numbers)}
            return self._execute_query(query, params, "invoice_documents")
        except Exception as e:
            # Table structure may differ — handle gracefully
            logger.debug(f"Invoice documents query failed (expected if media tables differ): {e}")
            return pd.DataFrame()

    # =========================================================================
    # HELPER METHODS
    # =========================================================================
    
    def _execute_query(
        self, 
        query: str, 
        params: dict, 
        query_name: str = "query"
    ) -> pd.DataFrame:
        """
        Execute SQL query and return DataFrame.
        
        UPDATED v3.5.0: Added timing output to terminal.
        """
        start_time = time.perf_counter()
        
        try:
            logger.debug(f"Executing {query_name}")
            df = pd.read_sql(text(query), self.engine, params=params)
            
            elapsed = time.perf_counter() - start_time
            
            if DEBUG_QUERY_TIMING:
                print(f"   📊 SQL [{query_name}]: {elapsed:.3f}s → {len(df):,} rows")
            
            logger.debug(f"{query_name} returned {len(df)} rows")
            return df
        except Exception as e:
            elapsed = time.perf_counter() - start_time
            if DEBUG_QUERY_TIMING:
                print(f"   ❌ SQL [{query_name}]: {elapsed:.3f}s → ERROR: {e}")
            logger.error(f"Error executing {query_name}: {e}")
            return pd.DataFrame()