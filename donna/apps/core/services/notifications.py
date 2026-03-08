"""
core/services/notifications.py

NotificationService nach Observer-Pattern.

Architektur:
    - NotificationService  → zentraler Dispatcher (Subject)
    - NotificationHandler  → abstrakte Basis für Kanäle (Observer)
    - EmailHandler         → konkreter E-Mail-Kanal (via Django-Mail)
    - InAppHandler         → Platzhalter für In-App-Notifications

Verwendung:
    from core.services.notifications import notification_service
    from core.models import NotificationEvent

    notification_service.dispatch(
        event=NotificationEvent.INVOICE_CREATED,
        context={"project": project, "invoice_number": "RE-2024-042"},
        project=project,          # optional: für projektspezifische Abos
    )
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

from django.template import Context, Template
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Abstrakte Handler-Basis (Observer)
# ---------------------------------------------------------------------------

class NotificationHandler(ABC):
    """
    Abstrakte Basis für alle Benachrichtigungs-Kanäle.
    Neue Kanäle (Slack, SMS, Webhook …) erben von dieser Klasse
    und werden via `notification_service.register()` angemeldet.
    """

    @abstractmethod
    def send(
        self,
        recipient,          # core.User
        event: str,
        subject: str,
        body: str,
        context: dict[str, Any],
    ) -> None:
        """Versendet eine Benachrichtigung über diesen Kanal."""
        ...

    @property
    @abstractmethod
    def channel_name(self) -> str:
        """Eindeutiger Name des Kanals, z.B. 'email'."""
        ...


# ---------------------------------------------------------------------------
# Konkrete Handler
# ---------------------------------------------------------------------------

class EmailHandler(NotificationHandler):
    """Versendet Benachrichtigungen per E-Mail (Django send_mail)."""

    channel_name = "email"

    def send(self, recipient, event: str, subject: str, body: str, context: dict) -> None:
        from django.core.mail import send_mail
        from django.conf import settings

        if not recipient.notify_by_email or not recipient.email:
            return

        try:
            send_mail(
                subject=subject,
                message=body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[recipient.email],
                fail_silently=False,
            )
            self._log(recipient, event, subject, body, context, success=True)
        except Exception as exc:
            logger.error("EmailHandler: Fehler beim Senden an %s: %s", recipient.email, exc)
            self._log(recipient, event, subject, body, context, success=False, error=str(exc))

    def _log(self, recipient, event, subject, body, context, *, success: bool, error: str = "") -> None:
        from core.models import NotificationLog
        import json

        status = NotificationLog.DeliveryStatus.SENT if success else NotificationLog.DeliveryStatus.FAILED

        # Kontext serialisierbar machen
        safe_context = {}
        for k, v in context.items():
            try:
                safe_context[k] = str(v)
            except Exception:
                safe_context[k] = repr(v)

        NotificationLog.objects.create(
            recipient=recipient,
            event=event,
            subject=subject,
            body=body,
            status=status,
            error_message=error,
            sent_at=timezone.now() if success else None,
            context_payload=safe_context,
        )


class InAppHandler(NotificationHandler):
    """
    Platzhalter für In-App-Benachrichtigungen.
    Implementierung folgt, wenn das Frontend-Modul steht.
    """
    channel_name = "in_app"

    def send(self, recipient, event: str, subject: str, body: str, context: dict) -> None:
        # TODO: In-App-Notification in DB oder WebSocket pushen
        logger.debug("InAppHandler: [%s] → %s: %s", event, recipient, subject)


# ---------------------------------------------------------------------------
# NotificationService — zentraler Dispatcher (Subject)
# ---------------------------------------------------------------------------

class NotificationService:
    """
    Zentraler Service zum Auslösen von Benachrichtigungen.

    Ablauf bei `dispatch()`:
    1. Lade alle aktiven NotificationSubscriptions für dieses Ereignis
    2. Lade das zugehörige NotificationTemplate
    3. Rendere den Template-Body mit dem übergebenen Kontext
    4. Übergib an alle registrierten Handler

    Handler können zur Laufzeit über `register()` hinzugefügt /
    über `unregister()` entfernt werden.
    """

    def __init__(self) -> None:
        self._handlers: dict[str, NotificationHandler] = {}

    def register(self, handler: NotificationHandler) -> None:
        self._handlers[handler.channel_name] = handler
        logger.info("NotificationService: Handler '%s' registriert.", handler.channel_name)

    def unregister(self, channel_name: str) -> None:
        self._handlers.pop(channel_name, None)

    def dispatch(
        self,
        event: str,
        context: dict[str, Any],
        project=None,   # crm.Project | None
    ) -> None:
        """
        Löst ein Ereignis aus und benachrichtigt alle Abonnenten.

        Args:
            event:   Eine der NotificationEvent-Konstanten.
            context: Template-Variablen für Subject/Body.
            project: Optionales Projekt (für projektspezifische Abos).
        """
        from core.models import NotificationSubscription, NotificationTemplate

        try:
            template = NotificationTemplate.objects.get(event=event, is_active=True)
        except NotificationTemplate.DoesNotExist:
            logger.warning("NotificationService: Kein aktives Template für Ereignis '%s'.", event)
            return

        # Subscribers ermitteln: projektspezifisch + globale Abos
        subscriptions = NotificationSubscription.objects.filter(
            event=event,
        ).filter(
            models.Q(project=project) | models.Q(project__isnull=True)
        ).select_related("user").distinct()

        if not subscriptions.exists():
            logger.debug("NotificationService: Keine Abonnenten für '%s'.", event)
            return

        rendered_subject = self._render(template.subject, context)
        rendered_body    = self._render(template.body_template, context)

        for subscription in subscriptions:
            recipient = subscription.user
            for handler in self._handlers.values():
                try:
                    handler.send(
                        recipient=recipient,
                        event=event,
                        subject=rendered_subject,
                        body=rendered_body,
                        context=context,
                    )
                except Exception as exc:
                    logger.error(
                        "NotificationService: Handler '%s' fehlgeschlagen für %s: %s",
                        handler.channel_name, recipient, exc,
                    )

    @staticmethod
    def _render(template_string: str, context: dict) -> str:
        """Rendert einen Django-Template-String mit dem gegebenen Kontext."""
        try:
            t = Template(template_string)
            return t.render(Context(context))
        except Exception as exc:
            logger.error("NotificationService: Template-Rendering-Fehler: %s", exc)
            return template_string


# ---------------------------------------------------------------------------
# Singleton-Instanz — in apps/core/apps.py mit Handlern bestücken
# ---------------------------------------------------------------------------

notification_service = NotificationService()
