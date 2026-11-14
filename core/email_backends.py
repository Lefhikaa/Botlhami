"""Django email backend for Azure Communication Services Email.

Set EMAIL_BACKEND=core.email_backends.AzureCommunicationEmailBackend and
ACS_CONNECTION_STRING in the App Service settings. DEFAULT_FROM_EMAIL must be
a sender address on the ACS-verified domain (e.g. DoNotReply@xxxx.azurecomm.net).
"""
import logging

from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend

log = logging.getLogger(__name__)


class AzureCommunicationEmailBackend(BaseEmailBackend):
    def __init__(self, fail_silently=False, **kwargs):
        super().__init__(fail_silently=fail_silently, **kwargs)
        self._client = None

    @property
    def client(self):
        if self._client is None:
            from azure.communication.email import EmailClient

            self._client = EmailClient.from_connection_string(settings.ACS_CONNECTION_STRING)
        return self._client

    def send_messages(self, email_messages):
        sent = 0
        for msg in email_messages:
            html = next((body for body, mime in getattr(msg, "alternatives", []) if mime == "text/html"), None)
            content = {"subject": msg.subject, "plainText": msg.body}
            if html:
                content["html"] = html
            payload = {
                "senderAddress": settings.ACS_SENDER_ADDRESS,
                "recipients": {"to": [{"address": a} for a in msg.to], "cc": [{"address": a} for a in msg.cc], "bcc": [{"address": a} for a in msg.bcc]},
                "content": content,
            }
            try:
                self.client.begin_send(payload)  # queued by Azure; don't block the request waiting for delivery
                sent += 1
            except Exception:
                log.exception("Azure email send failed")
                if not self.fail_silently:
                    raise
        return sent
