# utils/kpi_center_performance/setup/renewal/queries.py
"""
SQL Queries for KPI Center Split Rules Renewal

Handles:
1. Fetching expiring rules with sales activity
2. Bulk renewal operations (EXTEND / COPY strategies)
3. Validation and conflict detection
"""

import logging
from datetime import date, datetime
from typing import List, Optional, Dict, Any
import pandas as pd
from sqlalchemy import text

from utils.db import get_db_engine

logger = logging.getLogger(__name__)


class RenewalQueries:
    """
    Database queries for Split Rules renewal functionality.
    
    Usage:
        from utils.kpi_center_performance.setup.renewal import RenewalQueries
        
        queries = RenewalQueries(user_id=123)
        
        # Get suggestions
        suggestions = queries.get_renewal_suggestions(threshold_days=30)
        
        # Execute renewal
        result = queries.renew_rules_extend(
            rule_ids=[1, 2, 3],
            new_valid_to=date(2025, 12, 31)
        )
    """
    
    def __init__(self, user_id: int = None):
        """
        Initialize with database engine.
        
        Args:
            user_id: Current user ID (users.id) for audit trail
        """
        self._engine = None
        self.user_id = user_id
    
    @property
    def engine(self):
        """Lazy load database engine."""
        if self._engine is None:
            self._engine = get_db_engine()
        return self._engine
    
    # =========================================================================
    # RENEWAL SUGGESTIONS
    # =========================================================================
    
    def get_renewal_suggestions(
        self,
        threshold_days: int = 30,
        min_sales_amount: float = 0,
        kpi_center_ids: List[int] = None,
        kpi_type: str = None,
        limit: int = 200
    ) -> pd.DataFrame:
        """
        Get split rules that are expiring soon AND have recent sales activity.
        
        Criteria:
        1. Rule is still active (valid_to >= today)
        2. Rule expires within threshold_days
        3. Rule is approved
        4. Customer-Product combo has invoiced sales in last 12 months
        
        Args:
            threshold_days: Show rules expiring within N days (default: 30)
            min_sales_amount: Minimum sales amount in last 12 months (default: 0)
            kpi_center_ids: Filter by KPI Center IDs
            kpi_type: Filter by KPI type (TERRITORY, VERTICAL, etc.)
            limit: Maximum number of results
            
        Returns:
            DataFrame with columns:
            - All split rule fields
            - total_sales_12m: Total sales in last 12 months
            - total_gp_12m: Total gross profit in last 12 months
            - last_invoice_date: Most recent invoice date
            - invoice_count: Number of invoices in last 12 months
            - days_until_expiry: Days until rule expires
            - expiry_urgency: 'critical' (<7d), 'warning' (<30d), 'normal'
        """
        query = """
            WITH recent_sales AS (
                -- Aggregate sales by customer-product in last 12 months
                SELECT 
                    customer_id,
                    product_id,
                    SUM(sales_by_kpi_center_usd) as total_sales_12m,
                    SUM(gross_profit_by_kpi_center_usd) as total_gp_12m,
                    SUM(gp1_by_kpi_center_usd) as total_gp1_12m,
                    MAX(inv_date) as last_invoice_date,
                    COUNT(DISTINCT inv_number) as invoice_count
                FROM sales_report_by_kpi_center_flat_looker_view
                WHERE inv_date >= DATE_SUB(CURDATE(), INTERVAL 12 MONTH)
                  AND inv_date <= CURDATE()
                GROUP BY customer_id, product_id
                HAVING SUM(sales_by_kpi_center_usd) >= :min_sales
            )
            SELECT 
                -- Split rule fields
                kcsfv.kpi_center_split_id,
                kcsfv.kpi_center_id,
                kcsfv.kpi_center_name,
                kcsfv.kpi_type,
                kcsfv.customer_id,
                kcsfv.company_code,
                kcsfv.customer_name,
                kcsfv.customer_display,
                kcsfv.product_id,
                kcsfv.pt_code,
                kcsfv.product_name,
                kcsfv.package_size,
                kcsfv.product_display,
                kcsfv.brand_id,
                kcsfv.brand,
                kcsfv.split_percentage,
                kcsfv.effective_from,
                kcsfv.effective_to,
                kcsfv.is_approved,
                kcsfv.created_by_name,
                kcsfv.approved_by_name,
                
                -- Sales metrics
                COALESCE(rs.total_sales_12m, 0) as total_sales_12m,
                COALESCE(rs.total_gp_12m, 0) as total_gp_12m,
                COALESCE(rs.total_gp1_12m, 0) as total_gp1_12m,
                rs.last_invoice_date,
                COALESCE(rs.invoice_count, 0) as invoice_count,
                
                -- Expiry info
                DATEDIFF(kcsfv.effective_to, CURDATE()) as days_until_expiry,
                CASE 
                    WHEN DATEDIFF(kcsfv.effective_to, CURDATE()) <= 7 THEN 'critical'
                    WHEN DATEDIFF(kcsfv.effective_to, CURDATE()) <= 30 THEN 'warning'
                    ELSE 'normal'
                END as expiry_urgency
                
            FROM kpi_center_split_looker_view kcsfv
            INNER JOIN recent_sales rs 
                ON kcsfv.customer_id = rs.customer_id 
                AND kcsfv.product_id = rs.product_id
            WHERE 
                -- Still active
                kcsfv.effective_to >= CURDATE()
                -- Expiring within threshold
                AND kcsfv.effective_to <= DATE_ADD(CURDATE(), INTERVAL :threshold_days DAY)
                -- Approved only
                AND kcsfv.is_approved = 1
        """
        
        params = {
            'threshold_days': threshold_days,
            'min_sales': min_sales_amount
        }
        
        # Optional filters
        if kpi_center_ids:
            query += " AND kcsfv.kpi_center_id IN :kpi_center_ids"
            params['kpi_center_ids'] = tuple(kpi_center_ids)
        
        if kpi_type:
            query += " AND kcsfv.kpi_type = :kpi_type"
            params['kpi_type'] = kpi_type
        
        # Order by urgency then sales value
        query += """
            ORDER BY 
                days_until_expiry ASC,
                total_sales_12m DESC
            LIMIT :limit
        """
        params['limit'] = limit
        
        return self._execute_query(query, params, "renewal_suggestions")
    
    def get_renewal_summary_stats(self, threshold_days: int = 30) -> Dict:
        """
        Get summary statistics for renewal suggestions.
        
        Returns:
            Dict with counts by urgency level and total sales at risk
        """
        query = """
            WITH recent_sales AS (
                SELECT 
                    customer_id,
                    product_id,
                    SUM(sales_by_kpi_center_usd) as total_sales_12m
                FROM sales_report_by_kpi_center_flat_looker_view
                WHERE inv_date >= DATE_SUB(CURDATE(), INTERVAL 12 MONTH)
                  AND inv_date <= CURDATE()
                GROUP BY customer_id, product_id
                HAVING SUM(sales_by_kpi_center_usd) > 0
            ),
            expiring_rules AS (
                SELECT 
                    kcsfv.kpi_center_split_id,
                    DATEDIFF(kcsfv.effective_to, CURDATE()) as days_until_expiry,
                    COALESCE(rs.total_sales_12m, 0) as total_sales_12m
                FROM kpi_center_split_looker_view kcsfv
                INNER JOIN recent_sales rs 
                    ON kcsfv.customer_id = rs.customer_id 
                    AND kcsfv.product_id = rs.product_id
                WHERE kcsfv.effective_to >= CURDATE()
                  AND kcsfv.effective_to <= DATE_ADD(CURDATE(), INTERVAL :threshold_days DAY)
                  AND kcsfv.is_approved = 1
            )
            SELECT 
                COUNT(*) as total_count,
                SUM(CASE WHEN days_until_expiry <= 7 THEN 1 ELSE 0 END) as critical_count,
                SUM(CASE WHEN days_until_expiry > 7 AND days_until_expiry <= 30 THEN 1 ELSE 0 END) as warning_count,
                SUM(CASE WHEN days_until_expiry > 30 THEN 1 ELSE 0 END) as normal_count,
                SUM(total_sales_12m) as total_sales_at_risk
            FROM expiring_rules
        """
        
        df = self._execute_query(query, {'threshold_days': threshold_days}, "renewal_summary")
        
        if df.empty:
            return {
                'total_count': 0,
                'critical_count': 0,
                'warning_count': 0,
                'normal_count': 0,
                'total_sales_at_risk': 0
            }
        
        row = df.iloc[0]
        return {
            'total_count': int(row.get('total_count', 0) or 0),
            'critical_count': int(row.get('critical_count', 0) or 0),
            'warning_count': int(row.get('warning_count', 0) or 0),
            'normal_count': int(row.get('normal_count', 0) or 0),
            'total_sales_at_risk': float(row.get('total_sales_at_risk', 0) or 0)
        }
    
    # =========================================================================
    # RENEWAL OPERATIONS
    # =========================================================================
    
    def renew_rules_extend(
        self,
        rule_ids: List[int],
        new_valid_to: date,
        auto_approve: bool = True
    ) -> Dict:
        """
        Renew rules by EXTENDING the validity period (update valid_to).
        
        This is the simpler approach that modifies existing rules.
        
        Args:
            rule_ids: List of rule IDs to renew
            new_valid_to: New end date for all selected rules
            auto_approve: Whether to keep approved status (default: True)
            
        Returns:
            Dict with 'success': bool, 'count': int, 'message': str
        """
        if not rule_ids:
            return {'success': False, 'count': 0, 'message': 'No rules selected'}
        
        query = """
            UPDATE kpi_center_split_by_customer_product
            SET 
                valid_to = :new_valid_to,
                modified_date = NOW(),
                modified_by = :user_id,
                version = version + 1
            WHERE id IN :rule_ids
              AND delete_flag = 0
        """
        
        params = {
            'rule_ids': tuple(rule_ids),
            'new_valid_to': new_valid_to,
            'user_id': self.user_id
        }
        
        # If not auto-approve, reset approval status
        if not auto_approve:
            query = query.replace(
                "version = version + 1",
                "version = version + 1, isApproved = 0, approved_by = NULL"
            )
        
        return self._execute_update(query, params, "renew_extend")
    
    def renew_rules_copy(
        self,
        rule_ids: List[int],
        new_valid_from: date,
        new_valid_to: date,
        auto_approve: bool = False
    ) -> Dict:
        """
        Renew rules by COPYING to new records with new validity period.
        
        This approach preserves history by creating new records.
        Original rules are optionally expired (valid_to = new_valid_from - 1).
        
        Args:
            rule_ids: List of source rule IDs
            new_valid_from: Start date for new rules
            new_valid_to: End date for new rules
            auto_approve: Whether to auto-approve new rules (default: False)
            
        Returns:
            Dict with 'success': bool, 'count': int, 'new_ids': list, 'message': str
        """
        if not rule_ids:
            return {'success': False, 'count': 0, 'new_ids': [], 'message': 'No rules selected'}
        
        try:
            with self.engine.connect() as conn:
                # Step 1: Insert new rules copied from originals
                insert_query = """
                    INSERT INTO kpi_center_split_by_customer_product (
                        customer_id, product_id, kpi_center_id, split_percentage,
                        valid_from, valid_to, isApproved, approved_by,
                        created_date, modified_date, created_by, modified_by,
                        delete_flag, version
                    )
                    SELECT 
                        customer_id, product_id, kpi_center_id, split_percentage,
                        :new_valid_from, :new_valid_to, 
                        :is_approved, :approved_by,
                        NOW(), NOW(), :created_by, :created_by,
                        0, 0
                    FROM kpi_center_split_by_customer_product
                    WHERE id IN :rule_ids AND delete_flag = 0
                """
                
                params = {
                    'rule_ids': tuple(rule_ids),
                    'new_valid_from': new_valid_from,
                    'new_valid_to': new_valid_to,
                    'is_approved': 1 if auto_approve else 0,
                    'approved_by': self.user_id if auto_approve else None,
                    'created_by': self.user_id
                }
                
                result = conn.execute(text(insert_query), params)
                rows_inserted = result.rowcount
                
                # Step 2: Expire original rules (set valid_to = new_valid_from - 1)
                expire_query = """
                    UPDATE kpi_center_split_by_customer_product
                    SET 
                        valid_to = DATE_SUB(:new_valid_from, INTERVAL 1 DAY),
                        modified_date = NOW(),
                        modified_by = :user_id,
                        version = version + 1
                    WHERE id IN :rule_ids
                      AND delete_flag = 0
                      AND valid_to >= :new_valid_from
                """
                
                expire_params = {
                    'rule_ids': tuple(rule_ids),
                    'new_valid_from': new_valid_from,
                    'user_id': self.user_id
                }
                
                conn.execute(text(expire_query), expire_params)
                conn.commit()
                
                logger.info(f"renew_copy: Created {rows_inserted} new rules")
                return {
                    'success': True,
                    'count': rows_inserted,
                    'message': f'Created {rows_inserted} renewed rules'
                }
                
        except Exception as e:
            logger.error(f"Error in renew_copy: {e}")
            return {
                'success': False,
                'count': 0,
                'message': str(e)
            }
    
    # =========================================================================
    # VALIDATION
    # =========================================================================
    
    def check_renewal_conflicts(
        self,
        rule_ids: List[int],
        new_valid_from: date,
        new_valid_to: date
    ) -> Dict:
        """
        Check for potential conflicts when renewing rules.
        
        Conflicts include:
        - Overlapping periods with other rules for same customer-product-center
        - Over 100% split after renewal
        
        Args:
            rule_ids: Rules to be renewed
            new_valid_from: Proposed new start date
            new_valid_to: Proposed new end date
            
        Returns:
            Dict with 'has_conflicts': bool, 'conflicts': list
        """
        # Check for overlapping rules
        query = """
            WITH rules_to_renew AS (
                SELECT 
                    id, customer_id, product_id, kpi_center_id, split_percentage
                FROM kpi_center_split_by_customer_product
                WHERE id IN :rule_ids AND delete_flag = 0
            )
            SELECT 
                rtr.id as renewing_rule_id,
                existing.id as conflicting_rule_id,
                existing.kpi_center_id,
                kc.name as kpi_center_name,
                existing.split_percentage as existing_split,
                rtr.split_percentage as renewing_split,
                existing.valid_from as existing_from,
                existing.valid_to as existing_to
            FROM rules_to_renew rtr
            INNER JOIN kpi_center_split_by_customer_product existing
                ON rtr.customer_id = existing.customer_id
                AND rtr.product_id = existing.product_id
                AND rtr.kpi_center_id = existing.kpi_center_id
                AND existing.id != rtr.id
                AND existing.delete_flag = 0
            INNER JOIN kpi_centers kc ON existing.kpi_center_id = kc.id
            WHERE 
                -- Check for period overlap
                existing.valid_from <= :new_valid_to
                AND existing.valid_to >= :new_valid_from
        """
        
        params = {
            'rule_ids': tuple(rule_ids) if rule_ids else (0,),
            'new_valid_from': new_valid_from,
            'new_valid_to': new_valid_to
        }
        
        df = self._execute_query(query, params, "check_conflicts")
        
        if df.empty:
            return {'has_conflicts': False, 'conflicts': []}
        
        conflicts = df.to_dict('records')
        return {
            'has_conflicts': True,
            'conflicts': conflicts,
            'message': f'Found {len(conflicts)} potential overlapping rules'
        }
    
    def preview_renewal(
        self,
        rule_ids: List[int],
        new_valid_to: date = None,
        new_valid_from: date = None
    ) -> Dict:
        """
        Preview the renewal operation before executing.
        
        Args:
            rule_ids: Rules to be renewed
            new_valid_to: New end date
            new_valid_from: New start date (for COPY strategy)
            
        Returns:
            Dict with summary of what will happen
        """
        if not rule_ids:
            return {
                'count': 0,
                'rules': [],
                'total_sales_covered': 0
            }
        
        query = """
            WITH recent_sales AS (
                SELECT 
                    customer_id,
                    product_id,
                    SUM(sales_by_kpi_center_usd) as total_sales_12m
                FROM sales_report_by_kpi_center_flat_looker_view
                WHERE inv_date >= DATE_SUB(CURDATE(), INTERVAL 12 MONTH)
                GROUP BY customer_id, product_id
            )
            SELECT 
                kcsfv.kpi_center_split_id,
                kcsfv.kpi_center_name,
                kcsfv.customer_display,
                kcsfv.product_display,
                kcsfv.split_percentage,
                kcsfv.effective_to as current_valid_to,
                COALESCE(rs.total_sales_12m, 0) as total_sales_12m
            FROM kpi_center_split_looker_view kcsfv
            LEFT JOIN recent_sales rs 
                ON kcsfv.customer_id = rs.customer_id 
                AND kcsfv.product_id = rs.product_id
            WHERE kcsfv.kpi_center_split_id IN :rule_ids
        """
        
        df = self._execute_query(query, {'rule_ids': tuple(rule_ids)}, "preview_renewal")
        
        if df.empty:
            return {'count': 0, 'rules': [], 'total_sales_covered': 0}
        
        return {
            'count': len(df),
            'rules': df.to_dict('records'),
            'total_sales_covered': float(df['total_sales_12m'].sum()),
            'new_valid_to': new_valid_to.isoformat() if new_valid_to else None,
            'new_valid_from': new_valid_from.isoformat() if new_valid_from else None
        }
    
    # =========================================================================
    # HELPER METHODS
    # =========================================================================
    
    def _execute_query(
        self, 
        query: str, 
        params: dict, 
        query_name: str = "query"
    ) -> pd.DataFrame:
        """Execute SQL query and return DataFrame."""
        try:
            logger.debug(f"Executing {query_name}")
            df = pd.read_sql(text(query), self.engine, params=params)
            logger.debug(f"{query_name} returned {len(df)} rows")
            return df
        except Exception as e:
            logger.error(f"Error executing {query_name}: {e}")
            return pd.DataFrame()
    
    def _execute_update(
        self,
        query: str,
        params: dict,
        operation_name: str = "update"
    ) -> Dict:
        """Execute UPDATE and return result."""
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text(query), params)
                conn.commit()
                
                rows_affected = result.rowcount
                logger.info(f"{operation_name} successful, {rows_affected} rows affected")
                return {
                    'success': True,
                    'count': rows_affected,
                    'message': f'{operation_name}: {rows_affected} rules updated'
                }
        except Exception as e:
            logger.error(f"Error in {operation_name}: {e}")
            return {
                'success': False,
                'count': 0,
                'message': str(e)
            }