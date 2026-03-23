# utils/credit_control/credit_check.py
"""Core credit check: view → CreditStatus → match rules. VERSION: 1.0.0"""

import logging
import json
from datetime import datetime, timedelta
from typing import List, Optional
import pandas as pd

from .models import CreditStatus, RuleMatch, BlockDecision
from . import queries

logger = logging.getLogger(__name__)


def get_all_statuses() -> List[CreditStatus]:
    return _df_to_statuses(queries.get_all_credit_statuses())

def get_status(customer_id: int) -> List[CreditStatus]:
    return _df_to_statuses(queries.get_credit_status_by_customer(customer_id))

def _df_to_statuses(df: pd.DataFrame) -> List[CreditStatus]:
    if df.empty:
        return []
    result = []
    for _, r in df.iterrows():
        result.append(CreditStatus(
            customer_id=int(r.get('customer_id', 0)),
            customer_name=str(r.get('customer_name', '')),
            customer_code=r.get('customer_code'),
            term_condition_id=r.get('term_condition_id'),
            legal_entity_id=r.get('legal_entity_id'),
            legal_entity_name=r.get('legal_entity_name'),
            credit_limit=float(r['credit_limit']) if pd.notna(r.get('credit_limit')) else None,
            credit_currency=r.get('credit_currency'),
            payment_term=r.get('payment_term'),
            credit_status=str(r.get('credit_status', 'normal')),
            auto_block_enabled=bool(r.get('auto_block_enabled', 0)),
            block_threshold_days=int(r.get('block_threshold_days', 60)),
            overdue_grace_days=int(r.get('overdue_grace_days', 7)),
            outstanding_usd=float(r.get('outstanding_usd', 0)),
            overdue_usd=float(r.get('overdue_usd', 0)),
            max_overdue_days=int(r.get('max_overdue_days', 0)),
            outstanding_invoices=int(r.get('outstanding_invoices', 0)),
            overdue_invoices=int(r.get('overdue_invoices', 0)),
            utilization_pct=float(r['utilization_pct']) if pd.notna(r.get('utilization_pct')) else None,
            available_credit_usd=float(r['available_credit_usd']) if pd.notna(r.get('available_credit_usd')) else None,
            alert_level=str(r.get('alert_level', 'CLEAR')),
            billing_contact_email=r.get('billing_contact_email'),
            billing_contact_name=r.get('billing_contact_name'),
            assigned_salespeople=r.get('assigned_salespeople'),
            assigned_sales_emails=r.get('assigned_sales_emails'),
        ))
    return result


def match_rules(cs: CreditStatus, rules_df: pd.DataFrame) -> List[RuleMatch]:
    matches = []
    for _, row in rules_df.iterrows():
        m = _check_rule(cs, row)
        if m:
            matches.append(m)
    return matches

def _check_rule(cs: CreditStatus, row: pd.Series) -> Optional[RuleMatch]:
    if cs.credit_status == 'vip_exempt':
        return None
    try:
        cond = json.loads(row['condition_json']) if isinstance(row['condition_json'], str) else row['condition_json']
    except (json.JSONDecodeError, TypeError):
        cond = {}

    rt = row['rule_type']
    if rt in ('weekly_summary', 'monthly_summary'):
        return _build_match(row, cs, 'info') if cs.outstanding_usd > 0 else None
    if not cond:
        return None

    if (v := cond.get('overdue_days_min')) is not None and cs.max_overdue_days < v: return None
    if (v := cond.get('overdue_days_max')) is not None and cs.max_overdue_days > v: return None
    if (v := cond.get('min_amount_usd')) is not None and cs.overdue_usd < v: return None
    if (v := cond.get('credit_utilization_pct_min')) is not None:
        if cs.utilization_pct is None or cs.utilization_pct < v: return None
    if (v := cond.get('credit_utilization_pct_max')) is not None:
        if cs.utilization_pct is None or cs.utilization_pct > v: return None

    sev = 'critical' if rt in ('escalation', 'credit_exceeded') else 'warning'
    return _build_match(row, cs, sev)

def _build_match(row, cs, sev):
    try: rr = json.loads(row['recipient_roles_json']) if isinstance(row['recipient_roles_json'], str) else row['recipient_roles_json']
    except: rr = ['assigned_sales']
    try: cc = json.loads(row['cc_roles_json']) if isinstance(row['cc_roles_json'], str) else (row['cc_roles_json'] or [])
    except: cc = []
    return RuleMatch(
        rule_id=int(row['id']), rule_name=str(row['rule_name']),
        rule_type=str(row['rule_type']), severity=sev,
        email_template_key=str(row['email_template_key']),
        auto_block_action=bool(row.get('auto_block_action', 0)),
        block_scope=row.get('block_scope'),
        recipient_roles=rr or [], cc_roles=cc or [], credit_status=cs,
    )

def check_cooldown(match: RuleMatch, cooldown_days: int = 7) -> RuleMatch:
    if not match.credit_status:
        return match
    last = queries.get_last_sent_at(match.credit_status.customer_id, match.rule_type)
    if last and datetime.now() < last + timedelta(days=cooldown_days):
        match.should_send = False
        match.skip_reason = f"cooldown (last {last.strftime('%Y-%m-%d')})"
    return match

def should_block_order(customer_id: int, entity_id: int = None) -> BlockDecision:
    statuses = get_status(customer_id)
    if not statuses:
        return BlockDecision(message="No credit terms found")
    for cs in statuses:
        if entity_id and cs.legal_entity_id != entity_id:
            continue
        if cs.credit_status == 'blocked':
            return BlockDecision(blocked=True, reason=cs.block_reason, blocked_scope='both',
                override_allowed=True, approver_role='gm', credit_status=cs,
                message=f"⛔ {cs.customer_name} BLOCKED. O/S: ${cs.outstanding_usd:,.0f}, Overdue: {cs.max_overdue_days}d. GM approval required.")
        if cs.credit_status == 'vip_exempt':
            continue
        if cs.is_over_limit:
            return BlockDecision(blocked=True, reason=f"Over limit ({cs.utilization_pct:.0f}%)",
                blocked_scope='new_orders', override_allowed=True, approver_role='sales_manager', credit_status=cs,
                message=f"⚠️ {cs.customer_name} over credit limit: ${cs.outstanding_usd:,.0f}/${cs.credit_limit:,.0f} ({cs.utilization_pct:.0f}%)")
        if cs.should_auto_block:
            return BlockDecision(blocked=True, reason=f"Overdue {cs.max_overdue_days}d",
                blocked_scope='new_orders', override_allowed=True, approver_role='sales_manager', credit_status=cs,
                message=f"⚠️ {cs.customer_name} overdue {cs.max_overdue_days}d (${cs.overdue_usd:,.0f})")
    return BlockDecision(message="Credit check passed")
