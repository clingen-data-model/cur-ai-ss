"""Thin SMTP email sender.

Sends via STARTTLS when SMTP_HOST is configured in the environment. If it is not
configured, the message is logged at WARNING level so local dev stays functional
without a mail server.
"""

import logging
import smtplib
from email.mime.text import MIMEText

from lib.core.environment import env

logger = logging.getLogger(__name__)


def send_email(to: str, subject: str, body: str) -> None:
    if not env.SMTP_HOST:
        logger.warning(
            'SMTP_HOST not configured — email not sent to %s: %s', to, subject
        )
        return

    msg = MIMEText(body)
    msg['Subject'] = subject
    msg['From'] = env.SMTP_FROM
    msg['To'] = to

    with smtplib.SMTP(env.SMTP_HOST, env.SMTP_PORT) as smtp:
        smtp.starttls()
        if env.SMTP_USER and env.SMTP_PASSWORD:
            smtp.login(env.SMTP_USER, env.SMTP_PASSWORD)
        smtp.sendmail(env.SMTP_FROM, [to], msg.as_string())
