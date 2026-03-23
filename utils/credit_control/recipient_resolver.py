# utils/credit_control/recipient_resolver.py
"""Role keys → email addresses. Uses existing DB tables via queries.py. VERSION: 1.0.0"""

import logging
from typing import Dict, List
import pandas as pd
from .models import CreditStatus, Recipient
from . import queries

logger = logging.getLogger(__name__)


def resolve(roles: List[str], cs: CreditStatus) -> List[Recipient]:
    """Resolve role keys → deduplicated Recipient list."""
    seen: Dict[str, Recipient] = {}
    for role in roles:
        for r in _resolve_role(role, cs):
            if r.email and r.email not in seen:
                seen[r.email] = r
    return list(seen.values())


def _resolve_role(role: str, cs: CreditStatus) -> List[Recipient]:
    if role == 'assigned_sales':
        return _from_sales(cs)
    elif role == 'sales_manager':
        return _from_managers(cs)
    elif role == 'customer_contact':
        return _from_contacts(cs)
    elif role == 'finance':
        return _from_email_group('Finance', role)
    elif role == 'gm':
        return _from_email_group('Management', role)
    return []


def _from_sales(cs: CreditStatus) -> List[Recipient]:
    # Fast path: cached on view
    if cs.assigned_sales_emails:
        emails = [e.strip() for e in cs.assigned_sales_emails.split(',') if e.strip()]
        names = [n.strip() for n in (cs.assigned_salespeople or '').split(',')]
        while len(names) < len(emails): names.append('')
        return [Recipient(email=e, name=n, role='assigned_sales') for e, n in zip(emails, names) if e]
    df = queries.get_assigned_sales(cs.customer_id)
    return [Recipient(email=str(r['email']), name=str(r.get('name','')), role='assigned_sales')
            for _, r in df.iterrows() if pd.notna(r.get('email'))]


def _from_managers(cs: CreditStatus) -> List[Recipient]:
    sales_df = queries.get_assigned_sales(cs.customer_id)
    if sales_df.empty: return []
    eids = sales_df['employee_id'].dropna().astype(int).tolist()
    if not eids: return []
    mgr_df = queries.get_managers_for(eids)
    return [Recipient(email=str(r['email']), name=str(r.get('name','')), role='sales_manager')
            for _, r in mgr_df.iterrows() if pd.notna(r.get('email'))]


def _from_contacts(cs: CreditStatus) -> List[Recipient]:
    if cs.billing_contact_email:
        return [Recipient(email=cs.billing_contact_email, name=cs.billing_contact_name or '', role='customer_contact')]
    df = queries.get_customer_contacts(cs.customer_id)
    if df.empty: return []
    r = df.iloc[0]
    return [Recipient(email=str(r['email']), name=f"{r.get('first_name','')} {r.get('last_name','')}".strip(), role='customer_contact')]


def _from_email_group(group_name: str, role: str) -> List[Recipient]:
    df = queries.get_email_group_members(group_name)
    return [Recipient(email=str(r['email']), name=str(r.get('name','')), role=role)
            for _, r in df.iterrows() if pd.notna(r.get('email'))]
