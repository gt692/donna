"""
core/backends.py

Authentication-Backend das Login per E-Mail statt Username ermöglicht.
In settings/base.py registrieren:
    AUTHENTICATION_BACKENDS = ["apps.core.backends.EmailBackend"]
"""
from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend

UserModel = get_user_model()


class EmailBackend(ModelBackend):
    """Authentifiziert User über E-Mail-Adresse statt Username."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None or password is None:
            return None

        try:
            # username-Parameter enthält hier die E-Mail (aus LoginForm)
            user = UserModel.objects.get(email__iexact=username)
        except UserModel.DoesNotExist:
            # Timing-Angriff verhindern
            UserModel().set_password(password)
            return None

        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
