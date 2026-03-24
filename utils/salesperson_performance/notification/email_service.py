# utils/salesperson_performance/notification/email_service.py
"""
Email Service for Salesperson Performance Notifications.

Uses shared config credentials (utils.config) — NOT .env directly.
Supports both local (.env) and Streamlit Cloud (st.secrets).

Usage:
    from utils.salesperson_performance.notification.email_service import EmailService

    svc = EmailService()
    if not svc.is_configured:
        st.warning("Email not configured")
    else:
        result = svc.send(
            to=["sales@company.com"],
            subject="Weekly Alert",
            html="<h1>Hello</h1>",
            cc=["manager@company.com"],
        )

VERSION: 1.0.0
"""

import logging
import smtplib
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path
from typing import List, Optional, Dict, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class EmailResult:
    """Result of an email send attempt."""
    success: bool
    message: str
    recipients: List[str]
    elapsed_seconds: float = 0.0


class EmailService:
    """
    SMTP email sender for salesperson notifications.

    Reads credentials from utils.config (outbound email config).
    Thread-safe: each send() opens and closes its own SMTP connection.
    """

    def __init__(self):
        """Initialize from shared config — no constructor args needed."""
        from utils.config import config

        email_cfg = config.get_email_config("outbound")
        self._sender = email_cfg.get("sender")
        self._password = email_cfg.get("password")
        self._smtp_host = email_cfg.get("host", "smtp.gmail.com")
        self._smtp_port = int(email_cfg.get("port", 587))

        if self.is_configured:
            logger.info(f"EmailService initialized: sender={self._sender}, "
                        f"smtp={self._smtp_host}:{self._smtp_port}")
        else:
            logger.warning("EmailService: email credentials not configured")

    # =========================================================================
    # PUBLIC API
    # =========================================================================

    @property
    def is_configured(self) -> bool:
        """Check if email sending is possible."""
        return bool(self._sender and self._password)

    @property
    def sender_address(self) -> Optional[str]:
        return self._sender

    def send(
        self,
        to: List[str],
        subject: str,
        html: str,
        plain_text: str = "",
        cc: Optional[List[str]] = None,
        bcc: Optional[List[str]] = None,
        reply_to: Optional[str] = None,
        attachments: Optional[List[str]] = None,
    ) -> EmailResult:
        """
        Send an email.

        Args:
            to:          Recipient email addresses
            subject:     Email subject line
            html:        HTML body (primary)
            plain_text:  Plain text fallback (auto-generated from subject if empty)
            cc:          CC recipients
            bcc:         BCC recipients (not shown in headers)
            reply_to:    Reply-To address
            attachments: List of file paths to attach

        Returns:
            EmailResult with success status and message
        """
        if not self.is_configured:
            return EmailResult(
                success=False,
                message="Email not configured. Check EMAIL_SENDER and EMAIL_PASSWORD.",
                recipients=to,
            )

        # Normalize
        cc = cc or []
        bcc = bcc or []
        all_recipients = to + cc + bcc

        if not all_recipients:
            return EmailResult(
                success=False,
                message="No recipients specified.",
                recipients=[],
            )

        # Build message
        msg = MIMEMultipart("mixed")
        msg["From"] = self._sender
        msg["To"] = ", ".join(to)
        msg["Subject"] = subject

        if cc:
            msg["Cc"] = ", ".join(cc)
        if reply_to:
            msg["Reply-To"] = reply_to

        # Body: HTML + plain text fallback
        alt = MIMEMultipart("alternative")
        alt.attach(MIMEText(plain_text or subject, "plain", "utf-8"))
        alt.attach(MIMEText(html, "html", "utf-8"))
        msg.attach(alt)

        # Attachments
        for filepath in (attachments or []):
            path = Path(filepath)
            if not path.exists():
                return EmailResult(
                    success=False,
                    message=f"Attachment not found: {filepath}",
                    recipients=all_recipients,
                )
            part = MIMEBase("application", "octet-stream")
            part.set_payload(path.read_bytes())
            encoders.encode_base64(part)
            part.add_header(
                "Content-Disposition",
                f'attachment; filename="{path.name}"',
            )
            msg.attach(part)

        # Send
        start = time.perf_counter()
        try:
            with smtplib.SMTP(self._smtp_host, self._smtp_port, timeout=30) as server:
                server.starttls()
                server.login(self._sender, self._password)
                server.sendmail(self._sender, all_recipients, msg.as_string())

            elapsed = time.perf_counter() - start
            logger.info(
                f"Email sent: to={to}, cc={cc}, subject='{subject}' ({elapsed:.2f}s)"
            )
            return EmailResult(
                success=True,
                message=f"Email sent to {', '.join(to)}",
                recipients=all_recipients,
                elapsed_seconds=round(elapsed, 2),
            )

        except smtplib.SMTPAuthenticationError:
            elapsed = time.perf_counter() - start
            msg_text = (
                "SMTP authentication failed. "
                "Check EMAIL_PASSWORD (use App Password for Gmail)."
            )
            logger.error(msg_text)
            return EmailResult(
                success=False, message=msg_text,
                recipients=all_recipients, elapsed_seconds=round(elapsed, 2),
            )
        except smtplib.SMTPException as e:
            elapsed = time.perf_counter() - start
            msg_text = f"SMTP error: {e}"
            logger.error(msg_text)
            return EmailResult(
                success=False, message=msg_text,
                recipients=all_recipients, elapsed_seconds=round(elapsed, 2),
            )
        except Exception as e:
            elapsed = time.perf_counter() - start
            msg_text = f"Email send failed: {e}"
            logger.error(msg_text)
            return EmailResult(
                success=False, message=msg_text,
                recipients=all_recipients, elapsed_seconds=round(elapsed, 2),
            )
