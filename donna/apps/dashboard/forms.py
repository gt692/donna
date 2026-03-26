"""
dashboard/forms.py

Formulare für die Benutzerverwaltung im Admin-Bereich.
"""
from __future__ import annotations

from django import forms
from django.core.exceptions import ValidationError

from apps.core.models import CompanySettings, Role, User, UserRole
from apps.crm.models import ProductCatalog

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
        role_choices = list(UserRole.objects.order_by("order").values_list("slug", "name"))
        self.fields["role"].widget.choices = [("", "— Rolle auswählen —")] + role_choices

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
            "is_active", "notify_by_email", "show_in_kanban",
            "perm_edit_leads", "perm_delete_leads",
            "perm_edit_projects", "perm_delete_projects",
            "perm_edit_offers", "perm_delete_offers", "perm_send_offers",
            "perm_edit_invoices", "perm_delete_invoices", "perm_send_invoices",
            "perm_edit_accounts", "perm_delete_accounts",
            "perm_approve_time",
            "perm_edit_templates",
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
        role_choices = list(UserRole.objects.order_by("order").values_list("slug", "name"))
        self.fields["role"].widget.choices = [("", "— Rolle auswählen —")] + role_choices

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


_TW_CS = (
    "w-full px-3 py-2 text-sm rounded-lg border border-slate-200 "
    "focus:outline-none focus:ring-2 focus:ring-[#1666b0]"
)


class CompanySettingsForm(forms.ModelForm):
    class Meta:
        model = CompanySettings
        exclude = ["updated_at"]
        widgets = {
            "company_name":    forms.TextInput(attrs={"class": _TW_CS}),
            "legal_form":      forms.TextInput(attrs={"class": _TW_CS}),
            "slogan":          forms.TextInput(attrs={"class": _TW_CS}),
            "street":          forms.TextInput(attrs={"class": _TW_CS}),
            "postal_code":     forms.TextInput(attrs={"class": _TW_CS}),
            "city":            forms.TextInput(attrs={"class": _TW_CS}),
            "country":         forms.TextInput(attrs={"class": _TW_CS}),
            "hrb_number":        forms.TextInput(attrs={"class": _TW_CS}),
            "registry_court":    forms.TextInput(attrs={"class": _TW_CS}),
            "geschaeftsfuehrer": forms.TextInput(attrs={"class": _TW_CS}),
            "vat_id":            forms.TextInput(attrs={"class": _TW_CS}),
            "tax_number":        forms.TextInput(attrs={"class": _TW_CS}),
            "bank_name":         forms.TextInput(attrs={"class": _TW_CS}),
            "iban":              forms.TextInput(attrs={"class": _TW_CS}),
            "bic":               forms.TextInput(attrs={"class": _TW_CS}),
            "bank2_name":        forms.TextInput(attrs={"class": _TW_CS}),
            "bank2_iban":        forms.TextInput(attrs={"class": _TW_CS}),
            "bank2_bic":         forms.TextInput(attrs={"class": _TW_CS}),
            "email":           forms.EmailInput(attrs={"class": _TW_CS}),
            "phone":           forms.TextInput(attrs={"class": _TW_CS}),
            "website":         forms.URLInput(attrs={"class": _TW_CS}),
            "pdf_footer_text": forms.Textarea(attrs={"class": _TW_CS, "rows": 4}),
            "payment_days":    forms.NumberInput(attrs={"class": _TW_CS}),
            "primary_color":   forms.TextInput(attrs={"class": _TW_CS, "type": "color"}),
        }


_INPUT = "w-full px-3 py-2 text-sm rounded-lg border border-slate-200 focus:outline-none focus:ring-2 focus:ring-[#1666b0]"


class ProductCatalogForm(forms.ModelForm):
    class Meta:
        model = ProductCatalog
        fields = ["name", "description", "category", "unit", "quantity", "unit_price", "sort_order", "is_active"]
        widgets = {
            "name":        forms.TextInput(attrs={"class": _INPUT}),
            "description": forms.Textarea(attrs={"class": _INPUT, "rows": 3}),
            "category":    forms.TextInput(attrs={"class": _INPUT}),
            "unit":        forms.TextInput(attrs={"class": _INPUT}),
            "quantity":    forms.NumberInput(attrs={"class": _INPUT, "step": "0.01"}),
            "unit_price":  forms.NumberInput(attrs={"class": _INPUT, "step": "0.01"}),
            "sort_order":  forms.NumberInput(attrs={"class": _INPUT}),
        }
