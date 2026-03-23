# utils/credit_control/__init__.py
"""
Credit Control Module — Email notifications, credit checking, order blocking.

Depends on: utils.config, utils.db, utils.auth (existing)
New tables: notification_rules, credit_notifications, customer_block_log
Extends: term_and_conditions (credit_status columns)

VERSION: 1.0.0
"""

from .credit_check import get_all_statuses, get_status, should_block_order
from .notification_engine import run_batch, send_manual, BatchResult
from .block_engine import execute_block, execute_unblock, check_auto_unblock
from .models import CreditStatus, BlockDecision
from .constants import ALERT_LEVELS

__all__ = [
    'get_all_statuses', 'get_status', 'should_block_order',
    'run_batch', 'send_manual', 'BatchResult',
    'execute_block', 'execute_unblock', 'check_auto_unblock',
    'CreditStatus', 'BlockDecision', 'ALERT_LEVELS',
]
__version__ = '1.0.0'
