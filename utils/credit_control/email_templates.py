# utils/credit_control/email_templates.py
"""HTML email templates for credit control notifications. VERSION: 1.0.0"""

import logging
from typing import Tuple
import pandas as pd
from .models import CreditStatus

logger = logging.getLogger(__name__)

_CSS = """
body{font-family:Arial,sans-serif;color:#333;line-height:1.6;max-width:700px;margin:0 auto}
.hdr{color:#fff;padding:16px 24px;border-radius:8px 8px 0 0}
.cnt{padding:24px;border:1px solid #ddd;border-top:none;border-radius:0 0 8px 8px}
.met{background:#f8f9fa;padding:12px 16px;border-radius:6px;display:inline-block;min-width:110px;margin:4px}
.met .lb{font-size:12px;color:#666;text-transform:uppercase}
.met .vl{font-size:20px;font-weight:bold}
.met .vl.red{color:#dc3545} .met .vl.org{color:#ff8c00}
table{border-collapse:collapse;width:100%;margin:16px 0}
th{background:#f0f0f0;padding:10px 12px;text-align:left;font-size:13px;border-bottom:2px solid #ddd}
td{padding:8px 12px;border-bottom:1px solid #eee;font-size:13px}
.alert{padding:12px 16px;margin:16px 0;border-radius:0 6px 6px 0}
.alert-w{background:#fff3cd;border-left:4px solid #ffc107}
.alert-d{background:#fce4e4;border-left:4px solid #dc3545}
.ftr{font-size:12px;color:#999;margin-top:24px;padding-top:16px;border-top:1px solid #eee}
"""

def _wrap(header_bg: str, body: str) -> str:
    return f"<html><head><style>{_CSS}</style></head><body><div class='hdr' style='background:{header_bg}'>{body.split('</div>',1)[0]}</div>{body.split('</div>',1)[1] if '</div>' in body else ''}</body></html>"

def _inv_rows(df: pd.DataFrame, max_n: int = 12) -> str:
    if df.empty:
        return "<tr><td colspan='5' style='text-align:center;color:#999'>No details</td></tr>"
    rows = []
    for i, (_, r) in enumerate(df.iterrows()):
        if i >= max_n:
            rows.append(f"<tr><td colspan='5' style='text-align:center;color:#666'>+{len(df)-max_n} more</td></tr>")
            break
        d = int(r.get('days_overdue', 0))
        sc = 'color:#dc3545;font-weight:bold' if d > 60 else 'color:#ff8c00' if d > 30 else ''
        rows.append(f"<tr><td>{r.get('inv_number','—')}</td><td>{_fd(r.get('inv_date'))}</td>"
                     f"<td>{_fd(r.get('due_date'))}</td><td style='{sc}'>{d}d</td>"
                     f"<td style='text-align:right'>${float(r.get('outstanding_usd',0)):,.2f}</td></tr>")
    return "\n".join(rows)

def _fd(v):
    if pd.isna(v): return '—'
    try: return pd.Timestamp(v).strftime('%Y-%m-%d')
    except: return str(v)[:10]

def _metrics_html(cs: CreditStatus) -> str:
    parts = [f"<span class='met'><span class='lb'>Overdue</span><br><span class='vl red'>${cs.overdue_usd:,.0f}</span></span>",
             f"<span class='met'><span class='lb'>Outstanding</span><br><span class='vl'>${cs.outstanding_usd:,.0f}</span></span>",
             f"<span class='met'><span class='lb'>Max Days</span><br><span class='vl org'>{cs.max_overdue_days}d</span></span>"]
    if cs.utilization_pct is not None:
        parts.append(f"<span class='met'><span class='lb'>Utilization</span><br><span class='vl'>{cs.utilization_pct:.0f}%</span></span>")
    return "<div>" + "".join(parts) + "</div>"


# ═══════════════════════════════════════════════════════════════
# TEMPLATES
# ═══════════════════════════════════════════════════════════════

def render_overdue_reminder(cs: CreditStatus, inv_df: pd.DataFrame, sales_contact: str = '') -> Tuple[str, str, str]:
    subj = f"[Payment Reminder] Overdue invoices — {cs.customer_name}"
    total = inv_df['outstanding_usd'].sum() if not inv_df.empty else cs.overdue_usd
    html = f"""<div class='hdr' style='background:#ff8c00'><h2>📋 Payment Reminder</h2></div>
<div class='cnt'>
<p>Dear Valued Customer,</p>
<p>The following invoices from <b>{cs.legal_entity_name or 'Prostech'}</b> are past due:</p>
<table><thead><tr><th>Invoice#</th><th>Date</th><th>Due</th><th>Days</th><th>Outstanding</th></tr></thead>
<tbody>{_inv_rows(inv_df)}</tbody>
<tfoot><tr><td colspan='4' style='text-align:right;font-weight:bold'>Total Overdue:</td><td style='font-weight:bold;color:#dc3545'>${total:,.2f}</td></tr></tfoot></table>
<p><b>Outstanding:</b> ${cs.outstanding_usd:,.2f}{f" · <b>Limit:</b> ${cs.credit_limit:,.2f} ({cs.utilization_pct:.0f}%)" if cs.credit_limit else ""}</p>
<div class='alert alert-w'>⚠️ Please arrange payment to avoid order restrictions.</div>
{f"<p>Account manager: <b>{sales_contact}</b></p>" if sales_contact else ""}
<div class='ftr'>Automated reminder · Prostech Credit Control</div></div>"""
    plain = f"Overdue: ${total:,.0f} | Outstanding: ${cs.outstanding_usd:,.0f} | Max: {cs.max_overdue_days}d"
    return subj, f"<html><head><style>{_CSS}</style></head><body>{html}</body></html>", plain

def render_overdue_escalation(cs: CreditStatus, inv_df: pd.DataFrame) -> Tuple[str, str, str]:
    subj = f"[Escalation] Overdue {cs.max_overdue_days}d — {cs.customer_name} (${cs.overdue_usd:,.0f})"
    html = f"""<div class='hdr' style='background:#dc3545'><h2>⚠️ Overdue Escalation — {cs.customer_name}</h2></div>
<div class='cnt'>
<p><b>{cs.customer_name}</b> ({cs.customer_code or ''}) — overdue <b>{cs.max_overdue_days} days</b></p>
{_metrics_html(cs)}
<table><thead><tr><th>Invoice#</th><th>Date</th><th>Due</th><th>Days</th><th>O/S</th></tr></thead>
<tbody>{_inv_rows(inv_df)}</tbody></table>
<div class='alert alert-d'><b>Action Required:</b> Follow up immediately. Account may be blocked if unresolved within 15 days.</div>
<div class='ftr'>Prostech Credit Control · {cs.legal_entity_name or 'Prostech'}</div></div>"""
    plain = f"ESCALATION: {cs.customer_name} overdue {cs.max_overdue_days}d, ${cs.overdue_usd:,.0f}"
    return subj, f"<html><head><style>{_CSS}</style></head><body>{html}</body></html>", plain

def render_block_notice(cs: CreditStatus, inv_df: pd.DataFrame) -> Tuple[str, str, str]:
    subj = f"🔴 [BLOCKED] {cs.customer_name} — overdue {cs.max_overdue_days}d"
    html = f"""<div class='hdr' style='background:#8B0000'><h2>🚫 Credit Block — {cs.customer_name}</h2></div>
<div class='cnt'>
<div class='alert alert-d'><b>{cs.customer_name} BLOCKED.</b> Overdue exceeds {cs.block_threshold_days}d threshold ({cs.max_overdue_days}d actual).</div>
{_metrics_html(cs)}
<p><b>Impact:</b> ❌ New orders suspended · ❌ Deliveries on hold</p>
<table><thead><tr><th>Invoice#</th><th>Date</th><th>Due</th><th>Days</th><th>O/S</th></tr></thead>
<tbody>{_inv_rows(inv_df)}</tbody></table>
<p><b>Resolve:</b> 1) Pay overdue invoices, or 2) GM approval to override.</p>
<div class='ftr'>Prostech Credit Control · Automated Block Notice</div></div>"""
    plain = f"BLOCKED: {cs.customer_name}, overdue {cs.max_overdue_days}d, ${cs.overdue_usd:,.0f}"
    return subj, f"<html><head><style>{_CSS}</style></head><body>{html}</body></html>", plain

def render_credit_warning(cs: CreditStatus) -> Tuple[str, str, str]:
    subj = f"[Credit Warning] {cs.customer_name} — {cs.utilization_pct:.0f}%"
    html = f"""<div class='hdr' style='background:#ffc107;color:#333'><h2>⚠️ Credit Warning — {cs.customer_name}</h2></div>
<div class='cnt'>
<p><b>{cs.customer_name}</b> approaching credit limit:</p>
<div><span class='met'><span class='lb'>Outstanding</span><br><span class='vl org'>${cs.outstanding_usd:,.0f}</span></span>
<span class='met'><span class='lb'>Limit</span><br><span class='vl'>${cs.credit_limit:,.0f}</span></span>
<span class='met'><span class='lb'>Utilization</span><br><span class='vl org'>{cs.utilization_pct:.0f}%</span></span>
<span class='met'><span class='lb'>Available</span><br><span class='vl'>${cs.available_credit_usd:,.0f}</span></span></div>
<div class='alert alert-w'>Available: <b>${cs.available_credit_usd:,.0f}</b>. Orders above this may need approval.</div>
<div class='ftr'>Prostech Credit Control</div></div>"""
    plain = f"Credit Warning: {cs.customer_name}, {cs.utilization_pct:.0f}% (${cs.outstanding_usd:,.0f}/${cs.credit_limit:,.0f})"
    return subj, f"<html><head><style>{_CSS}</style></head><body>{html}</body></html>", plain

def render_credit_exceeded(cs: CreditStatus) -> Tuple[str, str, str]:
    over = cs.outstanding_usd - (cs.credit_limit or 0)
    subj = f"🔴 [Credit Exceeded] {cs.customer_name} — {cs.utilization_pct:.0f}%"
    html = f"""<div class='hdr' style='background:#dc3545'><h2>🔴 Credit Exceeded — {cs.customer_name}</h2></div>
<div class='cnt'>
<div class='alert alert-d'><b>{cs.customer_name}</b> exceeded limit by <b>${over:,.0f}</b>. New orders blocked.</div>
<div><span class='met'><span class='lb'>Outstanding</span><br><span class='vl red'>${cs.outstanding_usd:,.0f}</span></span>
<span class='met'><span class='lb'>Limit</span><br><span class='vl'>${cs.credit_limit:,.0f}</span></span>
<span class='met'><span class='lb'>Over By</span><br><span class='vl red'>${over:,.0f}</span></span></div>
<div class='ftr'>Prostech Credit Control</div></div>"""
    plain = f"EXCEEDED: {cs.customer_name}, ${cs.outstanding_usd:,.0f}/${cs.credit_limit:,.0f}, over ${over:,.0f}"
    return subj, f"<html><head><style>{_CSS}</style></head><body>{html}</body></html>", plain


def render_weekly_summary(cs: CreditStatus, inv_df: pd.DataFrame) -> Tuple[str, str, str]:
    from datetime import datetime
    week = datetime.now().strftime('%Y-W%W')
    subj = f"[Weekly AR Summary] {cs.customer_name} — ${cs.outstanding_usd:,.0f} outstanding"
    html = f"""<div class='hdr' style='background:#17a2b8'><h2>📊 Weekly AR Summary — {cs.customer_name}</h2></div>
<div class='cnt'>
<p>Week {week} snapshot for <b>{cs.customer_name}</b> ({cs.customer_code or ''}):</p>
{_metrics_html(cs)}
{f"<table><thead><tr><th>Invoice#</th><th>Date</th><th>Due</th><th>Days</th><th>O/S</th></tr></thead><tbody>{_inv_rows(inv_df, 20)}</tbody></table>" if not inv_df.empty else ""}
<p>Payment term: <b>{cs.payment_term or '—'}</b> · Entity: <b>{cs.legal_entity_name or '—'}</b></p>
<div class='ftr'>Prostech Credit Control · Automated Weekly Summary</div></div>"""
    plain = f"Weekly: {cs.customer_name}, O/S ${cs.outstanding_usd:,.0f}, Overdue ${cs.overdue_usd:,.0f}, Max {cs.max_overdue_days}d"
    return subj, f"<html><head><style>{_CSS}</style></head><body>{html}</body></html>", plain

def render_monthly_summary(cs: CreditStatus, inv_df: pd.DataFrame) -> Tuple[str, str, str]:
    from datetime import datetime
    month = datetime.now().strftime('%B %Y')
    subj = f"[Monthly Credit Report] {cs.customer_name} — {month}"
    html = f"""<div class='hdr' style='background:#6f42c1'><h2>📋 Monthly Credit Report — {cs.customer_name}</h2></div>
<div class='cnt'>
<p><b>{month}</b> credit report for <b>{cs.customer_name}</b> ({cs.customer_code or ''}):</p>
{_metrics_html(cs)}
{f"<p>Credit limit: <b>${cs.credit_limit:,.0f}</b> · Utilization: <b>{cs.utilization_pct:.0f}%</b> · Available: <b>${cs.available_credit_usd:,.0f}</b></p>" if cs.credit_limit else ""}
{f"<table><thead><tr><th>Invoice#</th><th>Date</th><th>Due</th><th>Days</th><th>O/S</th></tr></thead><tbody>{_inv_rows(inv_df, 20)}</tbody></table>" if not inv_df.empty else ""}
<p>Status: <b>{cs.alert_level}</b> · Payment term: <b>{cs.payment_term or '—'}</b> · Entity: <b>{cs.legal_entity_name or '—'}</b></p>
<div class='ftr'>Prostech Credit Control · Automated Monthly Report</div></div>"""
    plain = f"Monthly: {cs.customer_name}, O/S ${cs.outstanding_usd:,.0f}, Overdue ${cs.overdue_usd:,.0f}, Limit ${cs.credit_limit or 0:,.0f}"
    return subj, f"<html><head><style>{_CSS}</style></head><body>{html}</body></html>", plain


# ═══════════════════════════════════════════════════════════════
# ROUTER
# ═══════════════════════════════════════════════════════════════

def render_template(key: str, cs: CreditStatus, inv_df: pd.DataFrame = None, sales_contact: str = '') -> Tuple[str, str, str]:
    if inv_df is None: inv_df = pd.DataFrame()
    t = {
        'overdue_reminder': lambda: render_overdue_reminder(cs, inv_df, sales_contact),
        'overdue_escalation': lambda: render_overdue_escalation(cs, inv_df),
        'overdue_critical': lambda: render_overdue_escalation(cs, inv_df),
        'block_notice': lambda: render_block_notice(cs, inv_df),
        'credit_warning': lambda: render_credit_warning(cs),
        'credit_exceeded': lambda: render_credit_exceeded(cs),
        'weekly_summary': lambda: render_weekly_summary(cs, inv_df),
        'monthly_summary': lambda: render_monthly_summary(cs, inv_df),
    }
    return t.get(key, lambda: render_overdue_reminder(cs, inv_df, sales_contact))()