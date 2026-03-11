"""
dashboard/forms.py

Formulare für die Benutzerverwaltung im Admin-Bereich.
"""
from __future__ import annotations

from django import forms
from django.core.exceptions import ValidationError

from apps.core.models import Lookup, Role, User

_TW = (
    "w-full px-3 py-2 border border-slate-200 rounded-lg text-sm "
    "focus:outline-none focus:ring-2 focus:ring-indigo-500 transition"
)
_TW_SELECT = (
    "w-full px-3 py-2 border border-slate-200 rounded-lg text-sm bg-white "
    "focus:outline-none focus:ring-2 focus:ring-indigo-500 cursor-pointer transition"
)


class UserCreateForm(forms.ModelForm):
    """Einladungs-Formular — kein Passwort, wird per E-Mail vergeben."""

    class Meta:
        model = User
        fields = ["first_name", "last_name", "email", "role", "reporting_to", "notify_by_email"]
        widgets = {
            "first_name":   forms.TextInput(attrs={"class": _TW}),
            "last_name":    forms.TextInput(attrs={"class": _TW}),
            "email":        forms.EmailInput(attrs={"class": _TW}),
            "role":         forms.Select(attrs={"class": _TW_SELECT}),
            "reporting_to": forms.Select(attrs={"class": _TW_SELECT}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["first_name"].required = True
        self.fields["last_name"].required = True
        self.fields["reporting_to"].required = False
        self.fields["reporting_to"].empty_label = "— kein Vorgesetzter —"
        self.fields["reporting_to"].queryset = User.objects.filter(is_active=True).order_by(
            "last_name", "first_name"
        )
        self.fields["role"].widget.choices = [("", "— Rolle auswählen —")] + Lookup.choices_for("user_role")

    def clean_email(self):
        email = self.cleaned_data.get("email", "").lower().strip()
        if User.objects.filter(email__iexact=email).exists():
            raise ValidationError("Diese E-Mail-Adresse wird bereits verwendet.")
        return email

    def save(self, commit: bool = True) -> User:
        user = super().save(commit=False)
        user.username = self.cleaned_data["email"].lower()
        user.set_unusable_password()
        user.is_active = False
        if commit:
            user.save()
            self.save_m2m()
        return user


class UserEditForm(forms.ModelForm):
    class Meta:
        model = User
        fields = [
            "first_name", "last_name", "email",
            "role", "reporting_to",
            "is_active", "notify_by_email",
        ]
        widgets = {
            "first_name":   forms.TextInput(attrs={"class": _TW}),
            "last_name":    forms.TextInput(attrs={"class": _TW}),
            "email":        forms.EmailInput(attrs={"class": _TW}),
            "role":         forms.Select(attrs={"class": _TW_SELECT}),
            "reporting_to": forms.Select(attrs={"class": _TW_SELECT}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["reporting_to"].required = False
        self.fields["reporting_to"].empty_label = "— kein Vorgesetzter —"
        exclude_pk = self.instance.pk if self.instance and self.instance.pk else None
        qs = User.objects.filter(is_active=True).order_by("last_name", "first_name")
        if exclude_pk:
            qs = qs.exclude(pk=exclude_pk)
        self.fields["reporting_to"].queryset = qs
        self.fields["role"].widget.choices = [("", "— Rolle auswählen —")] + Lookup.choices_for("user_role")

    def clean_email(self):
        email = self.cleaned_data.get("email", "").lower().strip()
        qs = User.objects.filter(email__iexact=email)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError("Diese E-Mail-Adresse wird bereits verwendet.")
        return email

    def save(self, commit: bool = True) -> User:
        user = super().save(commit=False)
        user.username = self.cleaned_data["email"].lower()
        if commit:
            user.save()
        return user
