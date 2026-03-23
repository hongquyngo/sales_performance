# utils/credit_control/notification_engine.py
"""
Notification Engine — orchestrates credit check → send → log.
Uses email_sender.py (built on utils.config) for SMTP.

VERSION: 1.0.0
"""

import logging
import json
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass, field
import pandas as pd

from .models import CreditStatus, RuleMatch, Recipient
from .credit_check import get_all_statuses, get_status, match_rules, check_cooldown
from .recipient_resolver import resolve
from .email_templates import render_template
from .email_sender import send_email
from . import queries

logger = logging.getLogger(__name__)


@dataclass
class BatchResult:
    total_customers: int = 0
    total_matched: int = 0
    total_sent: int = 0
    total_skipped: int = 0
    total_failed: int = 0
    total_blocked: int = 0
    details: List[Dict] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None

    def summary(self) -> str:
        dur = (self.finished_at - self.started_at).total_seconds() if self.started_at and self.finished_at else 0
        return (f"{self.total_customers} customers, {self.total_matched} matches, "
                f"{self.total_sent} sent, {self.total_skipped} skipped, "
                f"{self.total_failed} failed, {self.total_blocked} blocked ({dur:.1f}s)")


def run_batch(dry_run: bool = False, triggered_by_user_id: int = None) -> BatchResult:
    """Run credit check for ALL customers. dry_run=True previews without sending."""
    result = BatchResult(started_at=datetime.now())

    all_cs = get_all_statuses()
    result.total_customers = len(all_cs)
    if not all_cs:
        result.finished_at = datetime.now()
        return result

    rules_df = queries.get_active_rules()
    if rules_df.empty:
        result.finished_at = datetime.now()
        return result

    for cs in all_cs:
        if cs.alert_level == 'CLEAR':
            continue
        for match in match_rules(cs, rules_df):
            result.total_matched += 1
            cd = int(rules_df.loc[rules_df['id'] == match.rule_id, 'cooldown_days'].iloc[0]) if match.rule_id else 7
            match = check_cooldown(match, cd)
            if not match.should_send:
                result.total_skipped += 1
                result.details.append({'customer': cs.customer_name, 'rule': match.rule_name,
                                       'action': 'skipped', 'reason': match.skip_reason})
                continue
            try:
                r = _process_match(match, dry_run, 'manual' if triggered_by_user_id else 'scheduler', triggered_by_user_id)
                if r['status'] in ('sent', 'dry_run'):
                    result.total_sent += 1
                elif r['status'] == 'failed':
                    result.total_failed += 1
                    result.errors.append(r.get('error', ''))
                if r.get('auto_blocked'):
                    result.total_blocked += 1
                result.details.append(r)
            except Exception as e:
                result.total_failed += 1
                result.errors.append(f"{cs.customer_name}: {e}")

    result.finished_at = datetime.now()
    logger.info(f"Batch: {result.summary()}")
    return result


def send_manual(customer_id: int, template_key: str = 'overdue_reminder',
                triggered_by_user_id: int = None, extra_emails: List[str] = None,
                dry_run: bool = False) -> Dict:
    """Send notification for a specific customer (bypasses cooldown)."""
    statuses = get_status(customer_id)
    if not statuses:
        return {'status': 'error', 'error': f'No credit terms for customer {customer_id}'}
    cs = statuses[0]
    match = RuleMatch(rule_id=0, rule_name=f'Manual: {template_key}', rule_type='overdue_reminder',
                      severity='warning', email_template_key=template_key,
                      recipient_roles=['assigned_sales', 'customer_contact'],
                      cc_roles=['sales_manager'], credit_status=cs)
    return _process_match(match, dry_run, 'manual', triggered_by_user_id, extra_emails)


def _process_match(match: RuleMatch, dry_run: bool, triggered_by: str,
                   user_id: int = None, extra_emails: List[str] = None) -> Dict:
    cs = match.credit_status
    if not cs:
        return {'status': 'error', 'error': 'No credit status'}

    # 1. Resolve recipients
    to_list = resolve(match.recipient_roles, cs)
    cc_list = resolve(match.cc_roles, cs) if match.cc_roles else []
    if extra_emails:
        for e in extra_emails:
            if e not in [r.email for r in to_list]:
                to_list.append(Recipient(email=e, role='manual'))
    if not to_list:
        return {'status': 'skipped', 'reason': 'no_recipients', 'customer': cs.customer_name, 'rule': match.rule_name}

    # 2. Get overdue invoices + render
    inv_df = queries.get_overdue_invoices(cs.customer_id) if cs.overdue_invoices > 0 else pd.DataFrame()
    sales_c = f"{cs.assigned_salespeople} ({cs.assigned_sales_emails})" if cs.assigned_salespeople else ''
    subject, html, plain = render_template(match.email_template_key, cs, inv_df, sales_c)

    result = {'customer': cs.customer_name, 'customer_id': cs.customer_id, 'rule': match.rule_name,
              'type': match.rule_type, 'severity': match.severity, 'subject': subject,
              'to': [r.email for r in to_list], 'cc': [r.email for r in cc_list],
              'outstanding': cs.outstanding_usd, 'overdue': cs.overdue_usd,
              'max_days': cs.max_overdue_days, 'auto_blocked': False}

    if dry_run:
        result['status'] = 'dry_run'
        result['action'] = f"WOULD send to {len(to_list)} recipients"
        return result

    # 3. Send (using our own email_sender built on utils.config)
    send_result = send_email(
        to=[r.email for r in to_list], subject=subject, body=plain, html=html,
        cc=[r.email for r in cc_list] if cc_list else None,
    )

    sent_at = datetime.now() if send_result['success'] else None
    status = 'sent' if send_result['success'] else 'failed'
    inv_nums = inv_df['inv_number'].tolist() if not inv_df.empty else []

    # 4. Log
    nid = queries.log_notification(
        notification_type=match.rule_type, severity=match.severity,
        customer_id=cs.customer_id, legal_entity_id=cs.legal_entity_id, employee_id=None,
        outstanding_usd=cs.outstanding_usd, credit_limit_usd=cs.credit_limit,
        overdue_amount_usd=cs.overdue_usd, max_overdue_days=cs.max_overdue_days,
        utilization_pct=cs.utilization_pct,
        recipients_json=json.dumps([r.to_dict() for r in to_list]),
        cc_json=json.dumps([r.to_dict() for r in cc_list]) if cc_list else None,
        email_subject=subject, sent_at=sent_at, delivery_status=status,
        error_message=send_result.get('message') if not send_result['success'] else None,
        triggered_by=triggered_by, triggered_by_user_id=user_id,
        rule_id=match.rule_id or None,
        invoice_numbers_json=json.dumps(inv_nums) if inv_nums else None,
    )

    result['status'] = status
    result['notification_id'] = nid
    if not send_result['success']:
        result['error'] = send_result.get('message', '')

    # 5. Auto-block
    if match.auto_block_action and send_result['success']:
        from .block_engine import execute_block
        result['auto_blocked'] = execute_block(cs, reason='overdue' if 'overdue' in match.rule_type else 'over_credit_limit',
                                                scope=match.block_scope or 'new_orders', performed_by='system', notification_id=nid)
    return result
