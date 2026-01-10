# utils/kpi_center_performance/setup/renewal/queries.py
"""
SQL Queries for KPI Center Split Rules Renewal (v2.0)

v2.0 Changes:
- Comprehensive filters: Brand, Customer, Product search
- Include EXPIRED rules (not just expiring)
- Expiry status categories: expired, critical, warning, normal
- Better sales activity filtering

Handles:
1. Fetching expired/expiring rules with sales activity
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


# =============================================================================
# CONSTANTS
# =============================================================================

EXPIRY_STATUS = {
    'expired': 'Already Expired',
    'critical': 'Critical (<7 days)',
    'warning': 'Warning (<30 days)',
    'normal': 'Expiring Soon',
    'all': 'All'
}


class RenewalQueries:
    """
    Database queries for Split Rules renewal functionality.
    
    v2.0: Enhanced with comprehensive filtering.
    
    Usage:
        from utils.kpi_center_performance.setup.renewal import RenewalQueries
        
        queries = RenewalQueries(user_id=123)
        
        # Get suggestions with filters
        suggestions = queries.get_renewal_suggestions(
            threshold_days=90,
            include_expired=True,
            brand_ids=[1, 2, 3],
            customer_search="foxconn"
        )
        
        # Execute renewal
        result = queries.renew_rules_extend(
            rule_ids=[1, 2, 3],
            new_valid_to=date(2026, 12, 31)
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
    # RENEWAL SUGGESTIONS (v2.0 - Enhanced filters)
    # =========================================================================
    
    def get_renewal_suggestions(
        self,
        # Expiry filters
        threshold_days: int = 90,
        include_expired: bool = True,
        expired_from_date: date = None,  # Date to look back for expired rules
        
        # Entity filters
        kpi_center_ids: List[int] = None,
        kpi_type: str = None,
        brand_ids: List[int] = None,
        
        # Search filters
        customer_search: str = None,
        product_search: str = None,
        
        # Sales filters
        min_sales_amount: float = 0,
        require_sales_activity: bool = True,
        sales_from_date: date = None,  # Date to look back for sales activity
    ) -> pd.DataFrame:
        """
        Get split rules that are expired/expiring AND have recent sales activity.
        
        v2.0 Changes:
        - Include EXPIRED rules (not just expiring soon)
        - Comprehensive entity filters (brand, customer, product search)
        
        v2.1 Changes:
        - expired_from_date: User-selectable date instead of fixed 365 days
        - sales_from_date: User-selectable date instead of fixed 12 months
        - Removed expiry_status filter (always show all)
        
        Args:
            threshold_days: Show rules expiring within N days (default: 90)
            include_expired: Include already expired rules (default: True)
            expired_from_date: Include rules expired since this date (default: first day of previous year)
            
            kpi_center_ids: Filter by KPI Center IDs
            kpi_type: Filter by KPI type (TERRITORY, VERTICAL, etc.)
            brand_ids: Filter by Brand IDs
            
            customer_search: Search customer name/code (partial match)
            product_search: Search product name/code (partial match)
            
            min_sales_amount: Minimum sales in the period
            require_sales_activity: If False, show rules without sales too
            sales_from_date: Include sales since this date (default: first day of previous year)
            
        Returns:
            DataFrame with columns:
            - All split rule fields
            - total_sales, total_gp, last_invoice_date, invoice_count
            - days_until_expiry (negative = already expired)
            - expiry_status: 'expired', 'critical', 'warning', 'normal'
        """
        # Build CTE for sales data
        sales_join = "INNER JOIN" if require_sales_activity else "LEFT JOIN"
        
        # Default sales_from_date to first day of previous year if not provided
        if sales_from_date is None:
            today = date.today()
            sales_from_date = date(today.year - 1, 1, 1)
        
        # HAVING clause logic:
        # - require_sales_activity=True + min_sales=0: HAVING SUM > 0 (có sales dương)
        # - require_sales_activity=True + min_sales>0: HAVING SUM >= min_sales (min_sales>0 ngầm định có sales)
        # - require_sales_activity=False + min_sales>0: HAVING SUM >= min_sales
        # - require_sales_activity=False + min_sales=0: không cần HAVING
        if require_sales_activity:
            if min_sales_amount > 0:
                having_clause = "HAVING SUM(sales_by_kpi_center_usd) >= :min_sales"
            else:
                having_clause = "HAVING SUM(sales_by_kpi_center_usd) > 0"
        else:
            if min_sales_amount > 0:
                having_clause = "HAVING SUM(sales_by_kpi_center_usd) >= :min_sales"
            else:
                having_clause = ""
        
        query = f"""
            WITH recent_sales AS (
                SELECT 
                    customer_id,
                    product_id,
                    kpi_center_id,
                    SUM(sales_by_kpi_center_usd) as total_sales,
                    SUM(gross_profit_by_kpi_center_usd) as total_gp,
                    SUM(gp1_by_kpi_center_usd) as total_gp1,
                    MAX(inv_date) as last_invoice_date,
                    COUNT(DISTINCT inv_number) as invoice_count
                FROM sales_report_by_kpi_center_flat_looker_view
                WHERE inv_date >= :sales_from_date
                  AND inv_date <= CURDATE()
                GROUP BY customer_id, product_id, kpi_center_id
                {having_clause}
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
                kcsfv.effective_period,
                kcsfv.is_approved,
                kcsfv.approval_status,
                kcsfv.created_by_name,
                kcsfv.approved_by_name,
                
                -- Sales metrics
                COALESCE(rs.total_sales, 0) as total_sales,
                COALESCE(rs.total_gp, 0) as total_gp,
                COALESCE(rs.total_gp1, 0) as total_gp1,
                rs.last_invoice_date,
                COALESCE(rs.invoice_count, 0) as invoice_count,
                
                -- Expiry info (negative = already expired)
                DATEDIFF(kcsfv.effective_to, CURDATE()) as days_until_expiry,
                
                -- Expiry status
                CASE 
                    WHEN kcsfv.effective_to < CURDATE() THEN 'expired'
                    WHEN DATEDIFF(kcsfv.effective_to, CURDATE()) <= 7 THEN 'critical'
                    WHEN DATEDIFF(kcsfv.effective_to, CURDATE()) <= 30 THEN 'warning'
                    ELSE 'normal'
                END as expiry_status
                
            FROM kpi_center_split_looker_view kcsfv
            {sales_join} recent_sales rs 
                ON kcsfv.customer_id = rs.customer_id 
                AND kcsfv.product_id = rs.product_id
                AND kcsfv.kpi_center_id = rs.kpi_center_id
            WHERE 
                -- Active (not deleted) and approved
                kcsfv.is_approved = 1
                AND (kcsfv.delete_flag = 0 OR kcsfv.delete_flag IS NULL)
        """
        
        params = {
            'min_sales': min_sales_amount,
            'sales_from_date': sales_from_date
        }
        
        # =====================================================================
        # EXPIRY DATE FILTER
        # =====================================================================
        if include_expired:
            # Include expired rules (from expired_from_date) AND expiring soon
            # Default expired_from_date to first day of previous year if not provided
            if expired_from_date is None:
                today = date.today()
                expired_from_date = date(today.year - 1, 1, 1)
            
            query += """
                AND (
                    kcsfv.effective_to >= :expired_from_date
                    AND kcsfv.effective_to <= DATE_ADD(CURDATE(), INTERVAL :threshold_days DAY)
                )
            """
            params['expired_from_date'] = expired_from_date
            params['threshold_days'] = threshold_days
        else:
            # Only expiring soon (not yet expired)
            query += """
                AND kcsfv.effective_to >= CURDATE()
                AND kcsfv.effective_to <= DATE_ADD(CURDATE(), INTERVAL :threshold_days DAY)
            """
            params['threshold_days'] = threshold_days
        
        # =====================================================================
        # ENTITY FILTERS
        # =====================================================================
        if kpi_center_ids:
            query += " AND kcsfv.kpi_center_id IN :kpi_center_ids"
            params['kpi_center_ids'] = tuple(kpi_center_ids)
        
        if kpi_type:
            query += " AND kcsfv.kpi_type = :kpi_type"
            params['kpi_type'] = kpi_type
        
        if brand_ids:
            query += " AND kcsfv.brand_id IN :brand_ids"
            params['brand_ids'] = tuple(brand_ids)
        
        # =====================================================================
        # SEARCH FILTERS (partial match)
        # =====================================================================
        if customer_search:
            query += """
                AND (
                    kcsfv.customer_name LIKE :customer_search
                    OR kcsfv.company_code LIKE :customer_search
                )
            """
            params['customer_search'] = f"%{customer_search}%"
        
        if product_search:
            query += """
                AND (
                    kcsfv.product_name LIKE :product_search
                    OR kcsfv.pt_code LIKE :product_search
                )
            """
            params['product_search'] = f"%{product_search}%"
        
        # =====================================================================
        # ORDER
        # =====================================================================
        query += """
            ORDER BY 
                -- Expired first, then by urgency
                CASE 
                    WHEN kcsfv.effective_to < CURDATE() THEN 0
                    ELSE 1
                END,
                days_until_expiry ASC,
                total_sales DESC
        """
        
        return self._execute_query(query, params, "renewal_suggestions")
    
    def get_renewal_summary_stats(
        self,
        threshold_days: int = 90,
        include_expired: bool = True,
        expired_from_date: date = None,
        sales_from_date: date = None,
        min_sales_amount: float = 0,
        require_sales_activity: bool = True
    ) -> Dict:
        """
        Get summary statistics for renewal suggestions.
        
        v2.0: Include expired rules in stats.
        v2.1: Use expired_from_date and sales_from_date instead of fixed values.
        v2.2: Add min_sales_amount and require_sales_activity for consistency.
        
        Returns:
            Dict with counts by status and total sales at risk
        """
        # Default sales_from_date to first day of previous year if not provided
        if sales_from_date is None:
            today = date.today()
            sales_from_date = date(today.year - 1, 1, 1)
        
        # HAVING clause logic (same as get_renewal_suggestions)
        if require_sales_activity:
            if min_sales_amount > 0:
                having_clause = "HAVING SUM(sales_by_kpi_center_usd) >= :min_sales"
            else:
                having_clause = "HAVING SUM(sales_by_kpi_center_usd) > 0"
        else:
            if min_sales_amount > 0:
                having_clause = "HAVING SUM(sales_by_kpi_center_usd) >= :min_sales"
            else:
                having_clause = ""
        
        sales_join = "INNER JOIN" if require_sales_activity else "LEFT JOIN"
        
        query = f"""
            WITH recent_sales AS (
                SELECT 
                    customer_id,
                    product_id,
                    kpi_center_id,
                    SUM(sales_by_kpi_center_usd) as total_sales
                FROM sales_report_by_kpi_center_flat_looker_view
                WHERE inv_date >= :sales_from_date
                  AND inv_date <= CURDATE()
                GROUP BY customer_id, product_id, kpi_center_id
                {having_clause}
            ),
            target_rules AS (
                SELECT 
                    kcsfv.kpi_center_split_id,
                    DATEDIFF(kcsfv.effective_to, CURDATE()) as days_until_expiry,
                    COALESCE(rs.total_sales, 0) as total_sales,
                    CASE 
                        WHEN kcsfv.effective_to < CURDATE() THEN 'expired'
                        WHEN DATEDIFF(kcsfv.effective_to, CURDATE()) <= 7 THEN 'critical'
                        WHEN DATEDIFF(kcsfv.effective_to, CURDATE()) <= 30 THEN 'warning'
                        ELSE 'normal'
                    END as expiry_status
                FROM kpi_center_split_looker_view kcsfv
                {sales_join} recent_sales rs 
                    ON kcsfv.customer_id = rs.customer_id 
                    AND kcsfv.product_id = rs.product_id
                    AND kcsfv.kpi_center_id = rs.kpi_center_id
                WHERE 
                    kcsfv.is_approved = 1
                    AND (kcsfv.delete_flag = 0 OR kcsfv.delete_flag IS NULL)
        """
        
        params = {
            'sales_from_date': sales_from_date,
            'min_sales': min_sales_amount
        }
        
        if include_expired:
            # Default expired_from_date to first day of previous year if not provided
            if expired_from_date is None:
                today = date.today()
                expired_from_date = date(today.year - 1, 1, 1)
            
            query += """
                    AND kcsfv.effective_to >= :expired_from_date
                    AND kcsfv.effective_to <= DATE_ADD(CURDATE(), INTERVAL :threshold_days DAY)
            """
            params['expired_from_date'] = expired_from_date
            params['threshold_days'] = threshold_days
        else:
            query += """
                    AND kcsfv.effective_to >= CURDATE()
                    AND kcsfv.effective_to <= DATE_ADD(CURDATE(), INTERVAL :threshold_days DAY)
            """
            params['threshold_days'] = threshold_days
        
        query += """
            )
            SELECT 
                COUNT(*) as total_count,
                SUM(CASE WHEN expiry_status = 'expired' THEN 1 ELSE 0 END) as expired_count,
                SUM(CASE WHEN expiry_status = 'critical' THEN 1 ELSE 0 END) as critical_count,
                SUM(CASE WHEN expiry_status = 'warning' THEN 1 ELSE 0 END) as warning_count,
                SUM(CASE WHEN expiry_status = 'normal' THEN 1 ELSE 0 END) as normal_count,
                COALESCE(SUM(total_sales), 0) as total_sales_at_risk
            FROM target_rules
        """
        
        df = self._execute_query(query, params, "renewal_summary_stats")
        
        if df.empty:
            return {
                'total_count': 0,
                'expired_count': 0,
                'critical_count': 0,
                'warning_count': 0,
                'normal_count': 0,
                'total_sales_at_risk': 0
            }
        
        row = df.iloc[0]
        return {
            'total_count': int(row.get('total_count', 0) or 0),
            'expired_count': int(row.get('expired_count', 0) or 0),
            'critical_count': int(row.get('critical_count', 0) or 0),
            'warning_count': int(row.get('warning_count', 0) or 0),
            'normal_count': int(row.get('normal_count', 0) or 0),
            'total_sales_at_risk': float(row.get('total_sales_at_risk', 0) or 0)
        }
    
    def get_brands_with_expiring_rules(
        self,
        threshold_days: int = 90,
        include_expired: bool = True,
        expired_from_date: date = None
    ) -> pd.DataFrame:
        """
        Get brands that have expiring rules for filter dropdown.
        
        v2.1: Use expired_from_date instead of fixed 365 days.
        """
        query = """
            SELECT DISTINCT 
                b.id as brand_id,
                b.brand_name,
                COUNT(kcsfv.kpi_center_split_id) as rule_count
            FROM kpi_center_split_looker_view kcsfv
            JOIN brands b ON kcsfv.brand_id = b.id
            WHERE kcsfv.is_approved = 1
              AND (kcsfv.delete_flag = 0 OR kcsfv.delete_flag IS NULL)
        """
        
        params = {}
        
        if include_expired:
            # Default expired_from_date to first day of previous year if not provided
            if expired_from_date is None:
                today = date.today()
                expired_from_date = date(today.year - 1, 1, 1)
            
            query += """
              AND kcsfv.effective_to >= :expired_from_date
              AND kcsfv.effective_to <= DATE_ADD(CURDATE(), INTERVAL :threshold_days DAY)
            """
            params['expired_from_date'] = expired_from_date
        else:
            query += """
              AND kcsfv.effective_to >= CURDATE()
              AND kcsfv.effective_to <= DATE_ADD(CURDATE(), INTERVAL :threshold_days DAY)
            """
        
        params['threshold_days'] = threshold_days
        
        query += """
            GROUP BY b.id, b.brand_name
            ORDER BY rule_count DESC, b.brand_name
        """
        
        return self._execute_query(query, params, "brands_with_expiring")
    
    # =========================================================================
    # RENEWAL OPERATIONS
    # =========================================================================
    
    def renew_rules_extend(
        self,
        rule_ids: List[int],
        new_valid_to: date,
        auto_approve: bool = False
    ) -> Dict:
        """
        Extend validity period of existing rules.
        
        This strategy:
        - Updates valid_to date
        - Keeps all other fields unchanged
        - Optionally auto-approves
        
        Args:
            rule_ids: List of rule IDs to extend
            new_valid_to: New end date
            auto_approve: If True, set isApproved = 1
            
        Returns:
            Dict with success, count, message
        """
        if not rule_ids:
            return {'success': False, 'count': 0, 'message': 'No rules selected'}
        
        query = """
            UPDATE kpi_center_split_by_customer_product
            SET 
                valid_to = :new_valid_to,
                -- Always reset approval status when extending (requires re-approval)
                -- If auto_approve is checked, approve immediately with current user
                isApproved = CASE WHEN :auto_approve = 1 THEN 1 ELSE 0 END,
                approved_by = CASE WHEN :auto_approve = 1 THEN :user_id ELSE NULL END,
                modified_date = NOW(),
                modified_by = :user_id,
                version = version + 1
            WHERE id IN :rule_ids
              AND (delete_flag = 0 OR delete_flag IS NULL)
        """
        
        params = {
            'rule_ids': tuple(rule_ids),
            'new_valid_to': new_valid_to,
            'auto_approve': 1 if auto_approve else 0,
            'user_id': self.user_id
        }
        
        return self._execute_update(query, params, "renew_extend")
    
    def renew_rules_copy(
        self,
        rule_ids: List[int],
        new_valid_from: date,
        new_valid_to: date,
        auto_approve: bool = False
    ) -> Dict:
        """
        Create new rules by copying existing ones with new validity period.
        
        This strategy:
        - Creates new rules with new validity period
        - Expires original rules (sets valid_to to day before new_valid_from)
        - Optionally auto-approves new rules
        
        Args:
            rule_ids: List of source rule IDs
            new_valid_from: Start date for new rules
            new_valid_to: End date for new rules
            auto_approve: If True, new rules are approved
            
        Returns:
            Dict with success, count, message
        """
        if not rule_ids:
            return {'success': False, 'count': 0, 'message': 'No rules selected'}
        
        try:
            with self.engine.connect() as conn:
                # Step 1: Insert new rules
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
                        CASE WHEN :auto_approve = 1 THEN 1 ELSE 0 END,
                        CASE WHEN :auto_approve = 1 THEN :user_id ELSE NULL END,
                        NOW(), NOW(), :user_id, :user_id,
                        0, 0
                    FROM kpi_center_split_by_customer_product
                    WHERE id IN :rule_ids
                      AND (delete_flag = 0 OR delete_flag IS NULL)
                """
                
                insert_params = {
                    'rule_ids': tuple(rule_ids),
                    'new_valid_from': new_valid_from,
                    'new_valid_to': new_valid_to,
                    'auto_approve': 1 if auto_approve else 0,
                    'user_id': self.user_id
                }
                
                result = conn.execute(text(insert_query), insert_params)
                rows_inserted = result.rowcount
                
                # Step 2: Expire original rules (set valid_to to day before new period)
                expire_query = """
                    UPDATE kpi_center_split_by_customer_product
                    SET 
                        valid_to = DATE_SUB(:new_valid_from, INTERVAL 1 DAY),
                        modified_date = NOW(),
                        modified_by = :user_id,
                        version = version + 1
                    WHERE id IN :rule_ids
                      AND (delete_flag = 0 OR delete_flag IS NULL)
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
        """
        query = """
            WITH rules_to_renew AS (
                SELECT 
                    id, customer_id, product_id, kpi_center_id, split_percentage
                FROM kpi_center_split_by_customer_product
                WHERE id IN :rule_ids AND (delete_flag = 0 OR delete_flag IS NULL)
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
                AND (existing.delete_flag = 0 OR existing.delete_flag IS NULL)
            INNER JOIN kpi_centers kc ON existing.kpi_center_id = kc.id
            WHERE 
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
        
        return {
            'has_conflicts': True,
            'conflicts': df.to_dict('records'),
            'message': f'Found {len(df)} potential overlapping rules'
        }
    
    def preview_renewal(
        self,
        rule_ids: List[int],
        new_valid_to: date = None,
        new_valid_from: date = None
    ) -> Dict:
        """
        Preview the renewal operation before executing.
        """
        if not rule_ids:
            return {'count': 0, 'rules': [], 'total_sales_covered': 0}
        
        query = """
            WITH recent_sales AS (
                SELECT 
                    customer_id,
                    product_id,
                    kpi_center_id,
                    SUM(sales_by_kpi_center_usd) as total_sales_12m
                FROM sales_report_by_kpi_center_flat_looker_view
                WHERE inv_date >= DATE_SUB(CURDATE(), INTERVAL 12 MONTH)
                GROUP BY customer_id, product_id, kpi_center_id
            )
            SELECT 
                kcsfv.kpi_center_split_id,
                kcsfv.kpi_center_name,
                kcsfv.customer_display,
                kcsfv.product_display,
                kcsfv.split_percentage,
                kcsfv.effective_to as current_valid_to,
                DATEDIFF(kcsfv.effective_to, CURDATE()) as days_until_expiry,
                COALESCE(rs.total_sales_12m, 0) as total_sales_12m
            FROM kpi_center_split_looker_view kcsfv
            LEFT JOIN recent_sales rs 
                ON kcsfv.customer_id = rs.customer_id 
                AND kcsfv.product_id = rs.product_id
                AND kcsfv.kpi_center_id = rs.kpi_center_id
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