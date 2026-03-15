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
import random
import string

import pyotp
from django.conf import settings as django_settings
from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.views import View

from .forms import (
    EmailMFAVerifyForm,
    LoginForm,
    PasswordResetRequestForm,
    SecuritySettingsForm,
    SetNewPasswordForm,
    SetPasswordForm,
    TOTPSetupForm,
    TOTPVerifyForm,
)

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
                # Kein 2FA eingerichtet → direkt einloggen
                from django.contrib.auth import login as auth_login
                del request.session[_SESSION_PRE_AUTH_USER]
                auth_login(request, user, backend="apps.core.backends.EmailBackend")
                next_url = request.GET.get("next") or "dashboard:home"
                return redirect(next_url)
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
        user = self._get_pre_auth_user(request)
        return render(request, self.template_name, {
            "form": TOTPVerifyForm(),
            "email_mfa_available": user and user.email_mfa_enabled,
        })

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

        return render(request, self.template_name, {
            "form": form,
            "email_mfa_available": user.email_mfa_enabled,
        })


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


# ---------------------------------------------------------------------------
# Password Reset
# ---------------------------------------------------------------------------

def _get_site_base_url(request) -> str:
    scheme = "https" if request.is_secure() else "http"
    return f"{scheme}://{request.get_host()}"


class PasswordResetRequestView(View):
    """
    GET/POST /auth/password-reset/
    User gibt E-Mail ein → Reset-Link wird versendet (falls Account existiert).
    """
    template_name = "core/password_reset_request.html"

    def get(self, request):
        return render(request, self.template_name, {"form": PasswordResetRequestForm()})

    def post(self, request):
        form = PasswordResetRequestForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data["email"].lower().strip()
            from django.contrib.auth import get_user_model
            User = get_user_model()
            try:
                user = User.objects.get(email__iexact=email, is_active=True)
            except User.DoesNotExist:
                user = None

            if user:
                uid   = urlsafe_base64_encode(force_bytes(user.pk))
                token = default_token_generator.make_token(user)
                reset_url = (
                    f"{_get_site_base_url(request)}"
                    f"/auth/password-reset/{uid}/{token}/"
                )
                try:
                    from django.template.loader import render_to_string
                    body = render_to_string("email/password_reset.txt", {
                        "user":      user,
                        "reset_url": reset_url,
                    })
                except Exception:
                    body = (
                        f"Hallo {user.first_name or user.email},\n\n"
                        f"klicke auf den folgenden Link um dein Passwort zurückzusetzen:\n\n"
                        f"{reset_url}\n\n"
                        f"Der Link ist 24 Stunden gültig.\n\n"
                        f"Falls du kein Passwort-Reset angefordert hast, ignoriere diese E-Mail.\n\n"
                        f"Donna Business OS"
                    )
                send_mail(
                    subject="Passwort zurücksetzen — Donna",
                    message=body,
                    from_email=getattr(django_settings, "DEFAULT_FROM_EMAIL", "noreply@donna.local"),
                    recipient_list=[user.email],
                    fail_silently=True,
                )
                logger.info("Passwort-Reset-Link gesendet an: %s", user.email)

            # Immer weiterleiten, um User-Enumeration zu verhindern
            return redirect("core:password_reset_sent")

        return render(request, self.template_name, {"form": form})


class PasswordResetSentView(View):
    """GET /auth/password-reset/sent/ — Bestätigungsseite."""
    template_name = "core/password_reset_sent.html"

    def get(self, request):
        return render(request, self.template_name)


class PasswordResetConfirmView(View):
    """
    GET/POST /auth/password-reset/<uidb64>/<token>/
    Token validieren und neues Passwort setzen.
    """
    template_name = "core/password_reset_confirm.html"

    def _get_user(self, uidb64: str):
        from django.contrib.auth import get_user_model
        try:
            uid  = force_str(urlsafe_base64_decode(uidb64))
            return get_user_model().objects.get(pk=uid)
        except Exception:
            return None

    def get(self, request, uidb64: str, token: str):
        user = self._get_user(uidb64)
        if not user or not default_token_generator.check_token(user, token):
            messages.error(request, "Der Reset-Link ist ungültig oder abgelaufen.")
            return redirect("core:password_reset_request")
        return render(request, self.template_name, {
            "form":    SetNewPasswordForm(),
            "uidb64":  uidb64,
            "token":   token,
            "validlink": True,
        })

    def post(self, request, uidb64: str, token: str):
        user = self._get_user(uidb64)
        if not user or not default_token_generator.check_token(user, token):
            messages.error(request, "Der Reset-Link ist ungültig oder abgelaufen.")
            return redirect("core:password_reset_request")

        form = SetNewPasswordForm(request.POST)
        if form.is_valid():
            user.set_password(form.cleaned_data["password1"])
            user.save(update_fields=["password"])
            logger.info("Passwort zurückgesetzt für: %s", user.email)
            return redirect("core:password_reset_complete")

        return render(request, self.template_name, {
            "form":    form,
            "uidb64":  uidb64,
            "token":   token,
            "validlink": True,
        })


class PasswordResetCompleteView(View):
    """GET /auth/password-reset/complete/ — Erfolgsseite."""
    template_name = "core/password_reset_complete.html"

    def get(self, request):
        return render(request, self.template_name)


# ---------------------------------------------------------------------------
# E-Mail-MFA
# ---------------------------------------------------------------------------

def _generate_email_otp(user) -> str:
    """
    Löscht alte, unverbrauchte Codes und erstellt einen neuen 6-stelligen Code.
    Gibt den erzeugten Code zurück.
    """
    from .models import EmailOTPCode
    from datetime import timedelta

    # Alte unverbrauchte Codes löschen
    EmailOTPCode.objects.filter(user=user, used=False).delete()

    code = "".join(random.choices(string.digits, k=6))
    EmailOTPCode.objects.create(
        user=user,
        code=code,
        expires_at=timezone.now() + timedelta(minutes=10),
    )
    return code


class EmailMFASendView(View):
    """
    POST /auth/email-mfa/send/
    Generiert OTP, sendet E-Mail, leitet zur Verify-Seite weiter.
    """

    def post(self, request):
        user_id = request.session.get(_SESSION_PRE_AUTH_USER)
        if not user_id:
            return redirect("core:login")

        from django.contrib.auth import get_user_model
        try:
            user = get_user_model().objects.get(pk=user_id)
        except get_user_model().DoesNotExist:
            return redirect("core:login")

        if not user.email_mfa_enabled:
            messages.error(request, "E-Mail-MFA ist für diesen Account nicht aktiviert.")
            return redirect("core:totp_verify")

        code = _generate_email_otp(user)

        try:
            from django.template.loader import render_to_string
            body = render_to_string("email/email_otp.txt", {"user": user, "code": code})
        except Exception:
            body = (
                f"Hallo {user.first_name or user.email},\n\n"
                f"dein Einmal-Code lautet: {code}\n\n"
                f"Der Code ist 10 Minuten gültig.\n\n"
                f"Donna Business OS"
            )

        send_mail(
            subject=f"Dein Anmeldecode: {code} — Donna",
            message=body,
            from_email=getattr(django_settings, "DEFAULT_FROM_EMAIL", "noreply@donna.local"),
            recipient_list=[user.email],
            fail_silently=True,
        )
        logger.info("E-Mail-OTP gesendet an: %s", user.email)
        return redirect("core:email_mfa_verify")


class EmailMFAVerifyView(View):
    """
    GET/POST /auth/email-mfa/verify/
    Code aus E-Mail eingeben und verifizieren.
    """
    template_name = "core/email_mfa_verify.html"

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
        return render(request, self.template_name, {"form": EmailMFAVerifyForm()})

    def post(self, request):
        user = self._get_pre_auth_user(request)
        if not user:
            messages.error(request, "Session abgelaufen. Bitte erneut einloggen.")
            return redirect("core:login")

        form = EmailMFAVerifyForm(request.POST)
        if form.is_valid():
            from .models import EmailOTPCode
            code = form.cleaned_data["code"]
            otp_obj = (
                EmailOTPCode.objects
                .filter(user=user, used=False)
                .order_by("-created_at")
                .first()
            )
            if otp_obj and otp_obj.code == code and otp_obj.is_valid():
                otp_obj.used = True
                otp_obj.save(update_fields=["used"])
                del request.session[_SESSION_PRE_AUTH_USER]
                auth_login(request, user, backend="apps.core.backends.EmailBackend")
                logger.info("E-Mail-MFA erfolgreich: %s", user.email)
                return redirect(request.GET.get("next", "dashboard:home"))

            messages.error(request, "Der Code ist ungültig oder abgelaufen.")
            logger.warning("Ungültiger E-Mail-OTP für: %s", user.email)

        return render(request, self.template_name, {"form": form})


# ---------------------------------------------------------------------------
# Sicherheitseinstellungen (Profil)
# ---------------------------------------------------------------------------

@method_decorator(login_required, name="dispatch")
class SecuritySettingsView(View):
    """
    GET/POST /auth/profile/security/
    E-Mail-MFA ein-/ausschalten; erfordert aktuellen TOTP-Code.
    """
    template_name = "core/security_settings.html"

    def get(self, request):
        form = SecuritySettingsForm(
            user=request.user,
            initial={"enable_email_mfa": request.user.email_mfa_enabled},
        )
        return render(request, self.template_name, {
            "form": form,
            "user": request.user,
        })

    def post(self, request):
        form = SecuritySettingsForm(user=request.user, data=request.POST)
        if form.is_valid():
            new_state = form.cleaned_data["enable_email_mfa"]
            request.user.email_mfa_enabled = new_state
            request.user.save(update_fields=["email_mfa_enabled"])
            status = "aktiviert" if new_state else "deaktiviert"
            messages.success(request, f"E-Mail-MFA wurde {status}.")
            logger.info(
                "E-Mail-MFA %s für: %s", status, request.user.email
            )
            return redirect("core:security_settings")

        return render(request, self.template_name, {
            "form": form,
            "user": request.user,
        })


@method_decorator(login_required, name="dispatch")
class TOTPReconfigureView(View):
    """
    GET/POST /auth/profile/totp/reconfigure/
    Eingeloggte User können ihren TOTP-Secret neu einrichten (z.B. neues Gerät).
    Kein Pre-Auth-Session-Slot nötig — User ist bereits vollständig eingeloggt.
    """
    template_name = "core/totp_reconfigure.html"
    _SESSION_KEY = "_donna_totp_reconfig_secret"

    def _build_qr_data_uri(self, user, secret: str) -> str:
        import base64, io, qrcode
        otp_uri = pyotp.TOTP(secret).provisioning_uri(
            name=user.email, issuer_name="Donna Business OS"
        )
        img = qrcode.make(otp_uri)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return f"data:image/png;base64,{base64.b64encode(buf.getvalue()).decode()}"

    def get(self, request):
        secret = request.session.get(self._SESSION_KEY) or pyotp.random_base32()
        request.session[self._SESSION_KEY] = secret
        return render(request, self.template_name, {
            "qr_uri": self._build_qr_data_uri(request.user, secret),
            "secret": secret,
            "form":   TOTPSetupForm(),
        })

    def post(self, request):
        secret = request.session.get(self._SESSION_KEY)
        if not secret:
            return redirect("core:totp_reconfigure")

        form = TOTPSetupForm(request.POST)
        if form.is_valid():
            code = form.cleaned_data["code"]
            if pyotp.TOTP(secret).verify(code, valid_window=1):
                request.user.totp_secret  = secret
                request.user.totp_enabled = True
                request.user.save(update_fields=["totp_secret", "totp_enabled"])
                request.session.pop(self._SESSION_KEY, None)
                messages.success(request, "Authenticator-App erfolgreich neu eingerichtet.")
                logger.info("TOTP neu konfiguriert: %s", request.user.email)
                return redirect("core:security_settings")
            form.add_error("code", "Ungültiger Code. Bitte versuche es erneut.")

        return render(request, self.template_name, {
            "qr_uri": self._build_qr_data_uri(request.user, secret),
            "secret": secret,
            "form":   form,
        })
