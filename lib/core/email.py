"""Thin SMTP email sender.

Sends via STARTTLS when SMTP_HOST is configured in the environment. If it is not
configured, the message is logged at WARNING level so local dev stays functional
without a mail server.

Emails are sent as multipart/alternative with both plain-text and HTML parts so
that all mail clients render them correctly and links are clickable.
"""

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from lib.core.environment import env

logger = logging.getLogger(__name__)


def send_email(to: str, subject: str, body: str, html: str | None = None) -> None:
    """Send an email.

    ``body`` is always required (plain-text fallback).  Pass ``html`` to also
    include an HTML part — mail clients will prefer it when present.
    """
    if not env.SMTP_HOST:
        logger.warning(
            'SMTP_HOST not configured — email not sent to %s: %s', to, subject
        )
        return

    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = env.SMTP_FROM
    msg['To'] = to
    msg.attach(MIMEText(body, 'plain'))
    if html:
        msg.attach(MIMEText(html, 'html'))

    with smtplib.SMTP(env.SMTP_HOST, env.SMTP_PORT) as smtp:
        smtp.starttls()
        if env.SMTP_USER and env.SMTP_PASSWORD:
            smtp.login(env.SMTP_USER, env.SMTP_PASSWORD)
        smtp.sendmail(env.SMTP_FROM, [to], msg.as_string())
