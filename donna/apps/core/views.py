"""
core/views.py

Login-Flow (2 Schritte), TOTP-Setup und Logout.

Ablauf:
  GET/POST /auth/login/        → LoginView   (E-Mail + Passwort)
  GET/POST /auth/totp/         → TOTPView    (6-stelliger Code)
  GET/POST /auth/totp/setup/   → TOTPSetupView (erstmaliges Einrichten)
  POST     /auth/logout/       → LogoutView

Wenn 2FA noch nicht eingerichtet → nach erstem Login direkt zu /auth/totp/setup/
"""
from __future__ import annotations

import logging

import pyotp
from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.shortcuts import redirect, render
from django.views import View

from .forms import LoginForm, SetPasswordForm, TOTPSetupForm, TOTPVerifyForm

logger = logging.getLogger(__name__)

# Session-Key für den vorläufig authentifizierten User (noch ohne 2FA)
_SESSION_PRE_AUTH_USER = "_donna_pre_auth_user_id"


class LoginView(View):
    """
    Schritt 1: E-Mail + Passwort prüfen.
    Bei Erfolg → User-ID in Session speichern, weiter zu TOTP-Challenge.
    """
    template_name = "core/login.html"

    def get(self, request):
        if request.user.is_authenticated:
            return redirect("dashboard:home")
        return render(request, self.template_name, {"form": LoginForm()})

    def post(self, request):
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            # User-ID in Session hinterlegen — noch KEIN auth_login!
            request.session[_SESSION_PRE_AUTH_USER] = str(user.pk)
            logger.info("Login-Versuch Schritt 1 erfolgreich: %s", user.email)

            if not user.totp_enabled:
                # 2FA noch nicht eingerichtet → Setup erzwingen
                return redirect("core:totp_setup")
            return redirect("core:totp_verify")

        return render(request, self.template_name, {"form": form})


class TOTPVerifyView(View):
    """
    Schritt 2: TOTP-Code prüfen.
    Bei Erfolg → echtes auth_login() + Session sauber aufräumen.
    """
    template_name = "core/totp_verify.html"

    def _get_pre_auth_user(self, request):
        from django.contrib.auth import get_user_model
        user_id = request.session.get(_SESSION_PRE_AUTH_USER)
        if not user_id:
            return None
        try:
            return get_user_model().objects.get(pk=user_id)
        except get_user_model().DoesNotExist:
            return None

    def get(self, request):
        if not request.session.get(_SESSION_PRE_AUTH_USER):
            return redirect("core:login")
        return render(request, self.template_name, {"form": TOTPVerifyForm()})

    def post(self, request):
        user = self._get_pre_auth_user(request)
        if not user:
            messages.error(request, "Session abgelaufen. Bitte erneut einloggen.")
            return redirect("core:login")

        form = TOTPVerifyForm(request.POST)
        if form.is_valid():
            code   = form.cleaned_data["code"]
            totp   = pyotp.TOTP(user.totp_secret)

            # valid_window=1 erlaubt ±30 Sekunden Toleranz
            if totp.verify(code, valid_window=1):
                del request.session[_SESSION_PRE_AUTH_USER]
                auth_login(request, user, backend="apps.core.backends.EmailBackend")
                logger.info("2FA erfolgreich: %s", user.email)
                return redirect(request.GET.get("next", "dashboard:home"))

            messages.error(request, "Der Code ist ungültig oder abgelaufen.")
            logger.warning("Ungültiger TOTP-Code für: %s", user.email)

        return render(request, self.template_name, {"form": form})


class TOTPSetupView(View):
    """
    Erstmaliges TOTP-Setup: Secret generieren, QR-Code anzeigen,
    Code bestätigen und 2FA aktivieren.
    """
    template_name = "core/totp_setup.html"

    def _get_pre_auth_user(self, request):
        from django.contrib.auth import get_user_model
        user_id = request.session.get(_SESSION_PRE_AUTH_USER)
        if not user_id:
            return None
        try:
            return get_user_model().objects.get(pk=user_id)
        except get_user_model().DoesNotExist:
            return None

    def _get_or_create_secret(self, user, request) -> str:
        """Generiert einmalig ein Secret und speichert es in der Session."""
        secret = request.session.get("_donna_totp_setup_secret")
        if not secret:
            secret = pyotp.random_base32()
            request.session["_donna_totp_setup_secret"] = secret
        return secret

    def _build_qr_data_uri(self, user, secret: str) -> str:
        """Generiert einen Base64-kodierten QR-Code als Data-URI (kein externer Request)."""
        import base64
        import io
        import qrcode

        totp    = pyotp.TOTP(secret)
        otp_uri = totp.provisioning_uri(name=user.email, issuer_name="Donna Business OS")

        img     = qrcode.make(otp_uri)
        buffer  = io.BytesIO()
        img.save(buffer, format="PNG")
        b64     = base64.b64encode(buffer.getvalue()).decode()
        return f"data:image/png;base64,{b64}"

    def get(self, request):
        user = self._get_pre_auth_user(request)
        if not user:
            return redirect("core:login")

        secret  = self._get_or_create_secret(user, request)
        qr_uri  = self._build_qr_data_uri(user, secret)

        return render(request, self.template_name, {
            "form":   TOTPSetupForm(),
            "secret": secret,
            "qr_uri": qr_uri,
        })

    def post(self, request):
        user = self._get_pre_auth_user(request)
        if not user:
            return redirect("core:login")

        secret = request.session.get("_donna_totp_setup_secret")
        if not secret:
            return redirect("core:totp_setup")

        form = TOTPSetupForm(request.POST)
        if form.is_valid():
            code = form.cleaned_data["code"]
            totp = pyotp.TOTP(secret)

            if totp.verify(code, valid_window=1):
                user.totp_secret  = secret
                user.totp_enabled = True
                user.save(update_fields=["totp_secret", "totp_enabled"])

                # Setup-Secret aus Session entfernen
                del request.session["_donna_totp_setup_secret"]
                del request.session[_SESSION_PRE_AUTH_USER]

                auth_login(request, user, backend="apps.core.backends.EmailBackend")
                messages.success(request, "2FA erfolgreich eingerichtet. Willkommen bei Donna!")
                logger.info("TOTP-Setup abgeschlossen: %s", user.email)
                return redirect("dashboard:home")

            messages.error(request, "Der Code ist ungültig. Bitte versuche es erneut.")

        qr_uri = self._build_qr_data_uri(user, secret)
        return render(request, self.template_name, {
            "form":   form,
            "secret": secret,
            "qr_uri": qr_uri,
        })


class LogoutView(View):
    def post(self, request):
        auth_logout(request)
        return redirect("core:login")


class InvitationAcceptView(View):
    """
    Einladungs-Bestätigungsseite.
    GET:  Token prüfen → Passwort-Setzen-Formular anzeigen.
    POST: Passwort setzen, Account aktivieren, Token löschen → Login.
    """
    template_name         = "core/invitation_accept.html"
    template_invalid_name = "core/invitation_invalid.html"

    def _get_user(self, token: str):
        from django.contrib.auth import get_user_model
        try:
            return get_user_model().objects.get(invitation_token=token)
        except get_user_model().DoesNotExist:
            return None

    def get(self, request, token: str):
        user = self._get_user(token)
        if not user or not user.is_invitation_valid():
            return render(request, self.template_invalid_name)
        return render(request, self.template_name, {
            "form":       SetPasswordForm(),
            "token":      token,
            "user_email": user.email,
            "user_name":  user.first_name or user.email,
        })

    def post(self, request, token: str):
        user = self._get_user(token)
        if not user or not user.is_invitation_valid():
            return render(request, self.template_invalid_name)

        form = SetPasswordForm(request.POST)
        if form.is_valid():
            user.accept_invitation(form.cleaned_data["password1"])
            messages.success(
                request,
                "Passwort gesetzt! Du kannst dich jetzt anmelden.",
            )
            logger.info("Einladung akzeptiert: %s", user.email)
            return redirect("core:login")

        return render(request, self.template_name, {
            "form":       form,
            "token":      token,
            "user_email": user.email,
            "user_name":  user.first_name or user.email,
        })
