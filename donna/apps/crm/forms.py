"""
crm/forms.py
"""
from django import forms
from django.utils.translation import gettext_lazy as _

from .models import Account, Project

_INPUT = (
    "w-full px-3 py-2 rounded-lg border border-slate-200 bg-white "
    "focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent "
    "text-sm transition"
)
_SELECT = _INPUT + " cursor-pointer"


class AccountForm(forms.ModelForm):
    class Meta:
        model  = Account
        fields = [
            "name", "account_type", "is_active",
            "email", "phone", "website",
            "address_line1", "address_line2", "postal_code", "city", "country",
            "account_manager", "lexoffice_id", "notes",
        ]
        widgets = {
            "name":          forms.TextInput(attrs={"class": _INPUT, "placeholder": "Firmenname"}),
            "account_type":  forms.Select(attrs={"class": _SELECT}),
            "email":         forms.EmailInput(attrs={"class": _INPUT}),
            "phone":         forms.TextInput(attrs={"class": _INPUT}),
            "website":       forms.URLInput(attrs={"class": _INPUT, "placeholder": "https://"}),
            "address_line1": forms.TextInput(attrs={"class": _INPUT}),
            "address_line2": forms.TextInput(attrs={"class": _INPUT}),
            "postal_code":   forms.TextInput(attrs={"class": _INPUT, "placeholder": "12345"}),
            "city":          forms.TextInput(attrs={"class": _INPUT}),
            "country":       forms.TextInput(attrs={"class": _INPUT}),
            "account_manager": forms.Select(attrs={"class": _SELECT}),
            "lexoffice_id":  forms.TextInput(attrs={"class": _INPUT, "placeholder": "UUID aus Lexoffice"}),
            "notes":         forms.Textarea(attrs={"class": _INPUT, "rows": 3}),
            "is_active":     forms.CheckboxInput(
                attrs={"class": "w-4 h-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.core.models import User, Role
        self.fields["account_manager"].queryset = User.objects.filter(
            is_active=True
        ).order_by("last_name", "first_name")
        self.fields["account_manager"].required = False
        self.fields["account_manager"].empty_label = "— kein Account-Manager —"


class ProjectForm(forms.ModelForm):
    class Meta:
        model  = Project
        fields = [
            "name", "account", "status", "description",
            "team_lead", "team_members",
            "start_date", "end_date",
            "budget_hours", "budget_amount", "hourly_rate",
            "storage_path", "lexoffice_id", "internal_reference",
        ]
        widgets = {
            "name":        forms.TextInput(attrs={"class": _INPUT, "placeholder": "Projektname"}),
            "account":     forms.Select(attrs={"class": _SELECT}),
            "status":      forms.Select(attrs={"class": _SELECT}),
            "description": forms.Textarea(attrs={"class": _INPUT, "rows": 3,
                                                  "placeholder": "Kurze Projektbeschreibung …"}),
            "team_lead":   forms.Select(attrs={"class": _SELECT}),
            "team_members": forms.CheckboxSelectMultiple(),
            "start_date":  forms.DateInput(attrs={"class": _INPUT, "type": "date"}, format="%Y-%m-%d"),
            "end_date":    forms.DateInput(attrs={"class": _INPUT, "type": "date"}, format="%Y-%m-%d"),
            "budget_hours":  forms.NumberInput(attrs={"class": _INPUT, "step": "0.5", "placeholder": "z.B. 80"}),
            "budget_amount": forms.NumberInput(attrs={"class": _INPUT, "step": "0.01", "placeholder": "z.B. 9600.00"}),
            "hourly_rate":   forms.NumberInput(attrs={"class": _INPUT, "step": "0.01", "placeholder": "z.B. 120.00"}),
            "storage_path":  forms.TextInput(attrs={"class": _INPUT,
                                                     "placeholder": r"\\srv01\projekte\2024\Kunde-X"}),
            "lexoffice_id":  forms.TextInput(attrs={"class": _INPUT, "placeholder": "UUID aus Lexoffice"}),
            "internal_reference": forms.TextInput(attrs={"class": _INPUT, "placeholder": "z.B. P-2024-042"}),
        }

    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.core.models import User, Role

        self.fields["account"].queryset = Account.objects.filter(
            is_active=True
        ).order_by("name")
        self.fields["account"].empty_label = "Account auswählen …"

        leads_qs = User.objects.filter(
            role__in=[Role.PROJECT_MANAGER, Role.ADMIN], is_active=True
        ).order_by("last_name")
        self.fields["team_lead"].queryset = leads_qs
        self.fields["team_lead"].required = False
        self.fields["team_lead"].empty_label = "— kein Projektleiter —"

        self.fields["team_members"].queryset = User.objects.filter(
            is_active=True
        ).order_by("last_name", "first_name")
        self.fields["team_members"].required = False

        # Optionale Felder
        for f in ("budget_hours", "budget_amount", "hourly_rate",
                  "storage_path", "lexoffice_id", "internal_reference",
                  "start_date", "end_date", "description"):
            self.fields[f].required = False
