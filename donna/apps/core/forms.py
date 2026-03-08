"""
core/forms.py

Login-Formular und TOTP-Challenge-Formular.
"""
from django import forms
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

_TW_INPUT = (
    "w-full px-4 py-3 rounded-lg border border-slate-200 "
    "bg-slate-50 focus:outline-none focus:ring-2 focus:ring-indigo-500 "
    "focus:border-transparent text-sm transition"
)


class LoginForm(forms.Form):
    """
    Schritt 1 des 2FA-Flows: E-Mail + Passwort.
    Validiert die Credentials, gibt aber noch keine Session heraus —
    die Session wird erst nach TOTP-Bestätigung geöffnet.
    """
    email = forms.EmailField(
        label=_("E-Mail"),
        widget=forms.EmailInput(
            attrs={
                "autocomplete": "email",
                "placeholder":  "name@firma.de",
                "class": (
                    "w-full px-4 py-3 rounded-lg border border-slate-200 "
                    "bg-slate-50 focus:outline-none focus:ring-2 focus:ring-indigo-500 "
                    "focus:border-transparent text-sm transition"
                ),
            }
        ),
    )
    password = forms.CharField(
        label=_("Passwort"),
        widget=forms.PasswordInput(
            attrs={
                "autocomplete": "current-password",
                "placeholder":  "••••••••••••",
                "class": (
                    "w-full px-4 py-3 rounded-lg border border-slate-200 "
                    "bg-slate-50 focus:outline-none focus:ring-2 focus:ring-indigo-500 "
                    "focus:border-transparent text-sm transition"
                ),
            }
        ),
    )

    def __init__(self, request=None, *args, **kwargs):
        self.request        = request
        self._user_cache    = None
        super().__init__(*args, **kwargs)

    def clean(self):
        email    = self.cleaned_data.get("email", "").lower().strip()
        password = self.cleaned_data.get("password", "")

        if email and password:
            # Django-Auth arbeitet standardmäßig mit username.
            # Wir mappen E-Mail → username über ein Custom Backend (siehe unten).
            self._user_cache = authenticate(
                self.request, username=email, password=password
            )
            if self._user_cache is None:
                raise forms.ValidationError(
                    _("E-Mail oder Passwort ist nicht korrekt."),
                    code="invalid_credentials",
                )
            if not self._user_cache.is_active:
                raise forms.ValidationError(
                    _("Dieses Konto ist deaktiviert."),
                    code="inactive",
                )
        return self.cleaned_data

    def get_user(self):
        return self._user_cache


class TOTPVerifyForm(forms.Form):
    """
    Schritt 2 des 2FA-Flows: 6-stelliger TOTP-Code.
    """
    code = forms.CharField(
        label=_("Authenticator-Code"),
        min_length=6,
        max_length=6,
        widget=forms.TextInput(
            attrs={
                "autocomplete":   "one-time-code",
                "inputmode":      "numeric",
                "pattern":        "[0-9]{6}",
                "placeholder":    "000000",
                "autofocus":      True,
                "class": (
                    "w-full px-4 py-3 rounded-lg border border-slate-200 "
                    "bg-slate-50 focus:outline-none focus:ring-2 focus:ring-indigo-500 "
                    "focus:border-transparent text-sm tracking-widest text-center "
                    "font-mono transition"
                ),
            }
        ),
    )

    def clean_code(self) -> str:
        return self.cleaned_data["code"].strip().replace(" ", "")


class TOTPSetupForm(forms.Form):
    """Bestätigt den ersten TOTP-Code beim Einrichten der 2FA."""
    code = forms.CharField(
        label=_("Code zur Bestätigung"),
        min_length=6,
        max_length=6,
        widget=forms.TextInput(
            attrs={
                "autocomplete": "one-time-code",
                "inputmode":    "numeric",
                "pattern":      "[0-9]{6}",
                "placeholder":  "000000",
                "autofocus":    True,
                "class": (
                    "w-full px-4 py-3 rounded-lg border border-slate-200 "
                    "bg-slate-50 focus:outline-none focus:ring-2 focus:ring-indigo-500 "
                    "focus:border-transparent text-sm tracking-widest text-center "
                    "font-mono transition"
                ),
            }
        ),
    )


class SetPasswordForm(forms.Form):
    """Wird beim Akzeptieren einer Einladung verwendet."""
    password1 = forms.CharField(
        label=_("Passwort wählen"),
        widget=forms.PasswordInput(
            attrs={
                "autocomplete": "new-password",
                "placeholder":  "Mindestens 12 Zeichen",
                "autofocus":    True,
                "class":        _TW_INPUT,
            }
        ),
    )
    password2 = forms.CharField(
        label=_("Passwort bestätigen"),
        widget=forms.PasswordInput(
            attrs={
                "autocomplete": "new-password",
                "placeholder":  "Passwort wiederholen",
                "class":        _TW_INPUT,
            }
        ),
    )

    def clean(self):
        cd = super().clean()
        p1 = cd.get("password1")
        p2 = cd.get("password2")
        if p1 and p2 and p1 != p2:
            self.add_error("password2", _("Die Passwörter stimmen nicht überein."))
        if p1:
            try:
                validate_password(p1)
            except ValidationError as e:
                self.add_error("password1", e)
        return cd
