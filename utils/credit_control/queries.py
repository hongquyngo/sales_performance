# utils/credit_control/queries.py
"""
SQL Queries — uses utils.db helpers exclusively.

Depends on: utils.db (execute_query_df, execute_query, execute_update)
No direct engine access.

VERSION: 1.0.0
"""

import logging
from datetime import datetime
from typing import Dict, List, Optional
import pandas as pd

from utils.db import execute_query_df, execute_query, execute_update, get_connection
from sqlalchemy import text as sa_text

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════
# CREDIT STATUS (read from view)
# ═══════════════════════════════════════════════════════════════

def get_all_credit_statuses() -> pd.DataFrame:
    try:
        return execute_query_df("SELECT * FROM customer_credit_status_view")
    except Exception as e:
        logger.error(f"get_all_credit_statuses: {e}")
        return pd.DataFrame()


def get_credit_status_by_customer(customer_id: int) -> pd.DataFrame:
    try:
        return execute_query_df(
            "SELECT * FROM customer_credit_status_view WHERE customer_id = :cid",
            {'cid': customer_id},
        )
    except Exception as e:
        logger.error(f"get_credit_status_by_customer({customer_id}): {e}")
        return pd.DataFrame()


# ═══════════════════════════════════════════════════════════════
# OVERDUE INVOICES (for email content)
# ═══════════════════════════════════════════════════════════════

def get_overdue_invoices(customer_id: int) -> pd.DataFrame:
    q = """
        SELECT DISTINCT inv_number, inv_date, due_date, days_overdue, aging_bucket,
            payment_status, payment_ratio,
            line_outstanding_usd_gross AS outstanding_usd,
            line_amount_usd_gross AS invoiced_usd,
            invoiced_currency,
            current_sales_name AS sales_name, current_sales_email AS sales_email,
            legal_entity
        FROM customer_ar_by_salesperson_view
        WHERE customer_id = :cid AND payment_status IN ('Unpaid','Partially Paid') AND days_overdue > 0
        ORDER BY days_overdue DESC
    """
    try:
        return execute_query_df(q, {'cid': customer_id})
    except Exception as e:
        logger.error(f"get_overdue_invoices({customer_id}): {e}")
        return pd.DataFrame()


# ═══════════════════════════════════════════════════════════════
# NOTIFICATION RULES
# ═══════════════════════════════════════════════════════════════

def get_active_rules() -> pd.DataFrame:
    try:
        return execute_query_df(
            "SELECT * FROM notification_rules WHERE is_active = 1 ORDER BY priority, id"
        )
    except Exception as e:
        logger.error(f"get_active_rules: {e}")
        return pd.DataFrame()


# ═══════════════════════════════════════════════════════════════
# NOTIFICATION LOG (cooldown check + history)
# ═══════════════════════════════════════════════════════════════

def get_last_sent_at(customer_id: int, notification_type: str) -> Optional[datetime]:
    try:
        rows = execute_query(
            "SELECT MAX(sent_at) AS last_sent FROM credit_notifications "
            "WHERE customer_id = :cid AND notification_type = :ntype AND delivery_status = 'sent'",
            {'cid': customer_id, 'ntype': notification_type},
        )
        return rows[0]['last_sent'] if rows and rows[0]['last_sent'] else None
    except Exception as e:
        logger.error(f"get_last_sent_at: {e}")
        return None


def log_notification(
    notification_type: str, severity: str,
    customer_id: Optional[int], legal_entity_id: Optional[int], employee_id: Optional[int],
    outstanding_usd: Optional[float], credit_limit_usd: Optional[float],
    overdue_amount_usd: Optional[float], max_overdue_days: Optional[int],
    utilization_pct: Optional[float],
    recipients_json: str, cc_json: Optional[str], email_subject: Optional[str],
    sent_at: Optional[datetime], delivery_status: str, error_message: Optional[str],
    triggered_by: str, triggered_by_user_id: Optional[int],
    rule_id: Optional[int], invoice_numbers_json: Optional[str],
) -> Optional[int]:
    q = """
        INSERT INTO credit_notifications (
            notification_type,severity,customer_id,legal_entity_id,employee_id,
            outstanding_usd,credit_limit_usd,overdue_amount_usd,max_overdue_days,utilization_pct,
            recipients_json,cc_json,email_subject,
            sent_at,delivery_status,error_message,
            triggered_by,triggered_by_user_id,rule_id,invoice_numbers_json,created_at
        ) VALUES (
            :notification_type,:severity,:customer_id,:legal_entity_id,:employee_id,
            :outstanding_usd,:credit_limit_usd,:overdue_amount_usd,:max_overdue_days,:utilization_pct,
            :recipients_json,:cc_json,:email_subject,
            :sent_at,:delivery_status,:error_message,
            :triggered_by,:triggered_by_user_id,:rule_id,:invoice_numbers_json,NOW()
        )
    """
    try:
        params = {
            'notification_type': notification_type, 'severity': severity,
            'customer_id': customer_id, 'legal_entity_id': legal_entity_id, 'employee_id': employee_id,
            'outstanding_usd': outstanding_usd, 'credit_limit_usd': credit_limit_usd,
            'overdue_amount_usd': overdue_amount_usd, 'max_overdue_days': max_overdue_days,
            'utilization_pct': utilization_pct,
            'recipients_json': recipients_json, 'cc_json': cc_json, 'email_subject': email_subject,
            'sent_at': sent_at, 'delivery_status': delivery_status, 'error_message': error_message,
            'triggered_by': triggered_by, 'triggered_by_user_id': triggered_by_user_id,
            'rule_id': rule_id, 'invoice_numbers_json': invoice_numbers_json,
        }
        # Use same connection for INSERT + LAST_INSERT_ID (session-specific)
        with get_connection() as conn:
            conn.execute(sa_text(q), params)
            row = conn.execute(sa_text("SELECT LAST_INSERT_ID() AS id")).fetchone()
            return row[0] if row else None
    except Exception as e:
        logger.error(f"log_notification: {e}")
        return None


def get_notification_history(customer_id: int = None, limit: int = 50) -> pd.DataFrame:
    q = """
        SELECT cn.*, c.english_name AS customer_name,
               CONCAT(e.first_name,' ',e.last_name) AS triggered_by_name
        FROM credit_notifications cn
        LEFT JOIN companies c ON cn.customer_id = c.id
        LEFT JOIN employees e ON cn.triggered_by_user_id = e.id
    """
    params = {}
    if customer_id:
        q += " WHERE cn.customer_id = :cid"
        params['cid'] = customer_id
    q += f" ORDER BY cn.created_at DESC LIMIT {limit}"
    try:
        return execute_query_df(q, params)
    except Exception as e:
        logger.error(f"get_notification_history: {e}")
        return pd.DataFrame()


# ═══════════════════════════════════════════════════════════════
# BLOCK MANAGEMENT
# ═══════════════════════════════════════════════════════════════

def update_credit_status(term_condition_id: int, new_status: str,
                         blocked_by: int = None, block_reason: str = None) -> bool:
    q = """
        UPDATE term_and_conditions
        SET credit_status = :status,
            blocked_at = CASE WHEN :status = 'blocked' THEN NOW() ELSE NULL END,
            blocked_by = CASE WHEN :status = 'blocked' THEN :blocked_by ELSE NULL END,
            block_reason = CASE WHEN :status = 'blocked' THEN :reason ELSE NULL END
        WHERE id = :tc_id
    """
    try:
        execute_update(q, {
            'tc_id': term_condition_id, 'status': new_status,
            'blocked_by': blocked_by, 'reason': block_reason,
        })
        return True
    except Exception as e:
        logger.error(f"update_credit_status: {e}")
        return False


def log_block_action(
    customer_id: int, legal_entity_id: Optional[int],
    action: str, reason: str, blocked_scope: str,
    outstanding: Optional[float], credit_limit: Optional[float],
    overdue: Optional[float], max_days: Optional[int],
    performed_by: str, user_id: Optional[int],
    approval_history_id: Optional[int], notification_id: Optional[int],
    notes: Optional[str],
) -> Optional[int]:
    q = """
        INSERT INTO customer_block_log (
            customer_id,legal_entity_id,action,reason,blocked_scope,
            outstanding_at_action,credit_limit_at_action,overdue_at_action,max_overdue_days,
            performed_by,user_id,approval_history_id,notification_id,notes,created_at
        ) VALUES (
            :cid,:eid,:action,:reason,:scope,
            :outstanding,:limit,:overdue,:max_days,
            :performed_by,:uid,:ahid,:nid,:notes,NOW()
        )
    """
    try:
        params = {
            'cid': customer_id, 'eid': legal_entity_id,
            'action': action, 'reason': reason, 'scope': blocked_scope,
            'outstanding': outstanding, 'limit': credit_limit,
            'overdue': overdue, 'max_days': max_days,
            'performed_by': performed_by, 'uid': user_id,
            'ahid': approval_history_id, 'nid': notification_id, 'notes': notes,
        }
        with get_connection() as conn:
            conn.execute(sa_text(q), params)
            row = conn.execute(sa_text("SELECT LAST_INSERT_ID() AS id")).fetchone()
            return row[0] if row else None
    except Exception as e:
        logger.error(f"log_block_action: {e}")
        return None


def get_block_history(customer_id: int = None, limit: int = 50) -> pd.DataFrame:
    q = """
        SELECT bl.*, c.english_name AS customer_name,
               CONCAT(e.first_name,' ',e.last_name) AS user_name,
               le.english_name AS entity_name
        FROM customer_block_log bl
        LEFT JOIN companies c ON bl.customer_id = c.id
        LEFT JOIN employees e ON bl.user_id = e.id
        LEFT JOIN companies le ON bl.legal_entity_id = le.id
    """
    params = {}
    if customer_id:
        q += " WHERE bl.customer_id = :cid"
        params['cid'] = customer_id
    q += f" ORDER BY bl.created_at DESC LIMIT {limit}"
    try:
        return execute_query_df(q, params)
    except Exception as e:
        logger.error(f"get_block_history: {e}")
        return pd.DataFrame()


# ═══════════════════════════════════════════════════════════════
# RECIPIENT RESOLUTION (from existing tables)
# ═══════════════════════════════════════════════════════════════

def get_assigned_sales(customer_id: int) -> pd.DataFrame:
    return execute_query_df("""
        SELECT DISTINCT current_sales_id AS employee_id, current_sales_name AS name, current_sales_email AS email
        FROM customer_ar_by_salesperson_view
        WHERE customer_id = :cid AND current_sales_id IS NOT NULL AND current_sales_status = 'ACTIVE'
    """, {'cid': customer_id})


def get_managers_for(employee_ids: List[int]) -> pd.DataFrame:
    if not employee_ids:
        return pd.DataFrame()
    # Build IN clause dynamically — SQLAlchemy text() doesn't expand tuples
    placeholders = ','.join(f':eid{i}' for i in range(len(employee_ids)))
    params = {f'eid{i}': eid for i, eid in enumerate(employee_ids)}
    return execute_query_df(f"""
        SELECT DISTINCT mgr.id AS employee_id, CONCAT(mgr.first_name,' ',mgr.last_name) AS name, mgr.email
        FROM employees e INNER JOIN employees mgr ON e.manager_id = mgr.id
        WHERE e.id IN ({placeholders}) AND mgr.status = 'ACTIVE' AND mgr.email IS NOT NULL AND mgr.delete_flag = 0
    """, params)


def get_customer_contacts(customer_id: int) -> pd.DataFrame:
    return execute_query_df("""
        SELECT ct.id, ct.first_name, ct.last_name, ct.email, ct.phone,
               p.name AS position_name, d.name AS department_name
        FROM contacts ct
        LEFT JOIN positions p ON ct.position_id = p.id
        LEFT JOIN departments d ON ct.department_id = d.id
        WHERE ct.company_id = :cid AND ct.delete_flag = 0 AND ct.email IS NOT NULL AND ct.email != ''
        ORDER BY CASE WHEN LOWER(COALESCE(d.name,'')) LIKE '%financ%' THEN 0
                      WHEN LOWER(COALESCE(d.name,'')) LIKE '%account%' THEN 1 ELSE 10 END, ct.id
    """, {'cid': customer_id})


def get_email_group_members(group_name: str) -> pd.DataFrame:
    return execute_query_df("""
        SELECT DISTINCT e.id AS employee_id, CONCAT(e.first_name,' ',e.last_name) AS name, e.email
        FROM email_group eg
        INNER JOIN employee_email_group eeg ON eg.id = eeg.email_group_id
        INNER JOIN employees e ON eeg.employee_id = e.id
        WHERE eg.group_name = :gn AND eg.delete_flag = 0 AND e.status = 'ACTIVE' AND e.email IS NOT NULL AND e.delete_flag = 0
    """, {'gn': group_name})