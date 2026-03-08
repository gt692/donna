from django.apps import AppConfig


class CoreConfig(AppConfig):
    name = "apps.core"
    verbose_name = "Core"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        """Handler beim Django-Start registrieren."""
        from apps.core.services.notifications import (
            notification_service,
            EmailHandler,
            InAppHandler,
        )
        notification_service.register(EmailHandler())
        notification_service.register(InAppHandler())
