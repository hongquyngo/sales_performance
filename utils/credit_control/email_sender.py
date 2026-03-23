# utils/credit_control/email_sender.py
"""
Email Sender for Credit Control — uses utils.config for SMTP credentials.

Follows same pattern as the standalone email_utils.py but reads credentials
from the centralized config system (utils.config.config.get_email_config).

Supports: HTML + plain text, CC/BCC, attachments.

VERSION: 1.0.0
"""

import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path
from typing import Dict, List, Optional, Union

from utils.config import config

logger = logging.getLogger(__name__)


def _get_smtp_config() -> Dict:
    """Get SMTP config from centralized config system."""
    cfg = config.get_email_config("outbound")
    return {
        'sender': cfg.get('sender'),
        'password': cfg.get('password'),
        'host': cfg.get('host', 'smtp.gmail.com'),
        'port': int(cfg.get('port', 587)),
    }


def send_email(
    to: Union[str, List[str]],
    subject: str,
    body: str,
    html: Optional[str] = None,
    cc: Union[str, List[str], None] = None,
    bcc: Union[str, List[str], None] = None,
    reply_to: Optional[str] = None,
    attachments: Optional[List[str]] = None,
) -> Dict:
    """
    Send email via SMTP using credentials from utils.config.

    Args:
        to: Recipient(s) — single email or list
        subject: Email subject
        body: Plain text body
        html: Optional HTML body (multipart/alternative)
        cc: CC recipient(s)
        bcc: BCC recipient(s)
        reply_to: Reply-To address
        attachments: List of file paths to attach

    Returns:
        {"success": bool, "message": str}
    """
    smtp = _get_smtp_config()

    if not smtp['sender'] or not smtp['password']:
        return {"success": False, "message": "Email not configured — check EMAIL_SENDER/EMAIL_PASSWORD in .env or Streamlit secrets"}

    # Normalize recipients
    to_list = [to] if isinstance(to, str) else list(to)
    cc_list = [cc] if isinstance(cc, str) else (list(cc) if cc else [])
    bcc_list = [bcc] if isinstance(bcc, str) else (list(bcc) if bcc else [])
    all_recipients = to_list + cc_list + bcc_list

    if not all_recipients:
        return {"success": False, "message": "No recipients specified"}

    # Build message
    msg = MIMEMultipart("mixed")
    msg["From"] = smtp['sender']
    msg["To"] = ", ".join(to_list)
    msg["Subject"] = subject
    if cc_list:
        msg["Cc"] = ", ".join(cc_list)
    if reply_to:
        msg["Reply-To"] = reply_to

    # Body
    if html:
        alt = MIMEMultipart("alternative")
        alt.attach(MIMEText(body, "plain", "utf-8"))
        alt.attach(MIMEText(html, "html", "utf-8"))
        msg.attach(alt)
    else:
        msg.attach(MIMEText(body, "plain", "utf-8"))

    # Attachments
    for filepath in (attachments or []):
        path = Path(filepath)
        if not path.exists():
            return {"success": False, "message": f"Attachment not found: {filepath}"}
        part = MIMEBase("application", "octet-stream")
        part.set_payload(path.read_bytes())
        encoders.encode_base64(part)
        part.add_header("Content-Disposition", f'attachment; filename="{path.name}"')
        msg.attach(part)

    # Send
    try:
        with smtplib.SMTP(smtp['host'], smtp['port']) as server:
            server.starttls()
            server.login(smtp['sender'], smtp['password'])
            server.sendmail(smtp['sender'], all_recipients, msg.as_string())

        logger.info(f"Email sent: '{subject}' → {', '.join(to_list)}")
        return {"success": True, "message": f"Sent to {', '.join(to_list)}"}

    except smtplib.SMTPAuthenticationError:
        msg = "SMTP auth failed — check EMAIL_PASSWORD (use App Password for Gmail)"
        logger.error(msg)
        return {"success": False, "message": msg}
    except Exception as e:
        logger.error(f"Email send failed: {e}")
        return {"success": False, "message": str(e)}
