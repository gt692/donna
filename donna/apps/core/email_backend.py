"""
Microsoft Graph API Email Backend für Django.
Ersetzt SMTP durch OAuth2-authentifizierte Graph API Aufrufe.
"""
import json
import msal
import requests
from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend


class GraphAPIEmailBackend(BaseEmailBackend):

    def _get_access_token(self):
        app = msal.ConfidentialClientApplication(
            client_id=settings.MS_CLIENT_ID,
            client_credential=settings.MS_CLIENT_SECRET,
            authority=f"https://login.microsoftonline.com/{settings.MS_TENANT_ID}",
        )
        result = app.acquire_token_for_client(
            scopes=["https://graph.microsoft.com/.default"]
        )
        if "access_token" not in result:
            raise RuntimeError(
                f"Token-Fehler: {result.get('error')}: {result.get('error_description')}"
            )
        return result["access_token"]

    def send_messages(self, email_messages):
        token = self._get_access_token()
        sender = settings.MS_SENDER_EMAIL
        sent = 0

        for message in email_messages:
            payload = {
                "message": {
                    "subject": message.subject,
                    "body": {
                        "contentType": "HTML" if message.content_subtype == "html" else "Text",
                        "content": message.body,
                    },
                    "toRecipients": [
                        {"emailAddress": {"address": addr}}
                        for addr in message.to
                    ],
                    "ccRecipients": [
                        {"emailAddress": {"address": addr}}
                        for addr in (message.cc or [])
                    ],
                    "from": {
                        "emailAddress": {"address": sender}
                    },
                },
                "saveToSentItems": "false",
            }

            response = requests.post(
                f"https://graph.microsoft.com/v1.0/users/{sender}/sendMail",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                },
                data=json.dumps(payload),
            )

            if response.status_code == 202:
                sent += 1
            else:
                if not self.fail_silently:
                    raise RuntimeError(
                        f"Graph API Fehler {response.status_code}: {response.text}"
                    )

        return sent
