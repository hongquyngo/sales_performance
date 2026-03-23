# utils/credit_control/models.py
"""Data models for Credit Control. VERSION: 1.0.0"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional


@dataclass
class CreditStatus:
    """Credit snapshot for a customer-entity relationship. From customer_credit_status_view."""
    customer_id: int
    customer_name: str
    customer_code: Optional[str] = None
    term_condition_id: Optional[int] = None
    legal_entity_id: Optional[int] = None
    legal_entity_name: Optional[str] = None
    credit_limit: Optional[float] = None
    credit_currency: Optional[str] = None
    payment_term: Optional[str] = None
    credit_status: str = 'normal'
    auto_block_enabled: bool = False
    block_threshold_days: int = 60
    overdue_grace_days: int = 7
    outstanding_usd: float = 0.0
    overdue_usd: float = 0.0
    max_overdue_days: int = 0
    outstanding_invoices: int = 0
    overdue_invoices: int = 0
    utilization_pct: Optional[float] = None
    available_credit_usd: Optional[float] = None
    alert_level: str = 'CLEAR'
    billing_contact_email: Optional[str] = None
    billing_contact_name: Optional[str] = None
    assigned_salespeople: Optional[str] = None
    assigned_sales_emails: Optional[str] = None

    @property
    def is_blocked(self) -> bool:
        return self.credit_status == 'blocked'

    @property
    def is_over_limit(self) -> bool:
        return bool(self.credit_limit and self.credit_limit > 0 and self.outstanding_usd > self.credit_limit)

    @property
    def should_auto_block(self) -> bool:
        if not self.auto_block_enabled or self.credit_status in ('blocked', 'vip_exempt'):
            return False
        return self.max_overdue_days > self.block_threshold_days or self.is_over_limit


@dataclass
class BlockDecision:
    """Result of a credit check for order/delivery blocking."""
    blocked: bool = False
    reason: Optional[str] = None
    blocked_scope: Optional[str] = None
    override_allowed: bool = True
    approver_role: Optional[str] = None
    credit_status: Optional[CreditStatus] = None
    message: str = ''


@dataclass
class Recipient:
    """Single email recipient."""
    email: str
    name: str = ''
    role: str = ''
    def to_dict(self) -> Dict:
        return {'email': self.email, 'name': self.name, 'role': self.role}


@dataclass
class RuleMatch:
    """A notification rule that matched a customer's credit status."""
    rule_id: int
    rule_name: str
    rule_type: str
    severity: str
    email_template_key: str
    auto_block_action: bool = False
    block_scope: Optional[str] = None
    recipient_roles: List[str] = field(default_factory=list)
    cc_roles: List[str] = field(default_factory=list)
    credit_status: Optional[CreditStatus] = None
    should_send: bool = True
    skip_reason: Optional[str] = None
