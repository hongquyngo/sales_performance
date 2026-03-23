# utils/credit_control/block_engine.py
"""Block/unblock customer credit via term_and_conditions.credit_status. VERSION: 1.0.0"""

import logging
from typing import Optional
from .models import CreditStatus
from . import queries

logger = logging.getLogger(__name__)


def execute_block(cs: CreditStatus, reason: str = 'overdue', scope: str = 'new_orders',
                  performed_by: str = 'system', user_id: int = None,
                  notification_id: int = None, notes: str = None) -> bool:
    if not cs.term_condition_id:
        return False
    if cs.credit_status == 'blocked':
        return True
    if cs.credit_status == 'vip_exempt':
        return False

    reason_text = notes or f"Auto-blocked: {reason} ({scope})"
    ok = queries.update_credit_status(cs.term_condition_id, 'blocked', user_id, reason_text)
    if not ok:
        return False

    queries.log_block_action(
        customer_id=cs.customer_id, legal_entity_id=cs.legal_entity_id,
        action='block', reason=reason, blocked_scope=scope,
        outstanding=cs.outstanding_usd, credit_limit=cs.credit_limit,
        overdue=cs.overdue_usd, max_days=cs.max_overdue_days,
        performed_by=performed_by, user_id=user_id,
        approval_history_id=None, notification_id=notification_id, notes=reason_text,
    )
    logger.warning(f"BLOCKED {cs.customer_name}: {reason}, scope={scope}, O/S=${cs.outstanding_usd:,.0f}")
    return True


def execute_unblock(cs: CreditStatus, reason: str = 'payment_received',
                    performed_by: str = 'user', user_id: int = None,
                    approval_history_id: int = None, notes: str = None) -> bool:
    if not cs.term_condition_id or cs.credit_status != 'blocked':
        return cs.credit_status != 'blocked'

    ok = queries.update_credit_status(cs.term_condition_id, 'normal')
    if not ok:
        return False

    queries.log_block_action(
        customer_id=cs.customer_id, legal_entity_id=cs.legal_entity_id,
        action='unblock', reason=reason, blocked_scope='both',
        outstanding=cs.outstanding_usd, credit_limit=cs.credit_limit,
        overdue=cs.overdue_usd, max_days=cs.max_overdue_days,
        performed_by=performed_by, user_id=user_id,
        approval_history_id=approval_history_id, notification_id=None,
        notes=notes or f"Unblocked: {reason}",
    )
    logger.info(f"UNBLOCKED {cs.customer_name}: {reason}")
    return True


def check_auto_unblock(customer_id: int) -> bool:
    """After payment received: check if block conditions resolved → auto-unblock."""
    from .credit_check import get_status
    for cs in get_status(customer_id):
        if cs.credit_status != 'blocked':
            continue
        if cs.max_overdue_days <= cs.block_threshold_days and not cs.is_over_limit:
            if execute_unblock(cs, reason='payment_received', performed_by='system'):
                return True
    return False
