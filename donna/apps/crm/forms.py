"""
crm/forms.py
"""
from django import forms
from django.forms import inlineformset_factory
from django.utils.translation import gettext_lazy as _

from apps.core.models import Lookup
from .models import Account, Contact, Invoice, InvoiceItem, Offer, OfferItem, Project

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
            "account_manager", "primary_contact", "billing_email", "lexoffice_id", "notes",
        ]
        widgets = {
            "name":            forms.TextInput(attrs={"class": _INPUT}),
            "account_type":    forms.Select(attrs={"class": _SELECT}),
            "email":           forms.EmailInput(attrs={"class": _INPUT, "placeholder": "Zentrale"}),
            "phone":           forms.TextInput(attrs={"class": _INPUT, "placeholder": "Zentrale"}),
            "website":         forms.URLInput(attrs={"class": _INPUT, "placeholder": "https://"}),
            "address_line1":   forms.TextInput(attrs={"class": _INPUT}),
            "address_line2":   forms.TextInput(attrs={"class": _INPUT}),
            "postal_code":     forms.TextInput(attrs={"class": _INPUT, "placeholder": "12345"}),
            "city":            forms.TextInput(attrs={"class": _INPUT}),
            "country":         forms.TextInput(attrs={"class": _INPUT}),
            "account_manager": forms.Select(attrs={"class": _SELECT}),
            "primary_contact": forms.Select(attrs={"class": _SELECT}),
            "billing_email":   forms.EmailInput(attrs={"class": _INPUT, "id": "id_billing_email", "placeholder": "rechnung@beispiel.de"}),
            "lexoffice_id":    forms.TextInput(attrs={"class": _INPUT, "placeholder": "UUID aus Lexoffice"}),
            "notes":           forms.Textarea(attrs={"class": _INPUT, "rows": 3}),
            "is_active":       forms.CheckboxInput(
                attrs={"class": "w-4 h-4 rounded border-slate-300 text-[#1666b0] focus:ring-[#1666b0]"}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.core.models import User
        self.fields["account_manager"].queryset = User.objects.filter(
            is_active=True
        ).order_by("last_name", "first_name")
        self.fields["account_manager"].required = False
        self.fields["account_manager"].empty_label = "— kein Account-Manager —"
        self.fields["primary_contact"].queryset = Contact.objects.all()
        self.fields["primary_contact"].required = False
        self.fields["primary_contact"].empty_label = "— kein Ansprechpartner —"


class ContactForm(forms.ModelForm):
    class Meta:
        model  = Contact
        fields = [
            "first_name", "last_name", "company_name", "role",
            "email", "phone", "mobile",
            "address_line1", "postal_code", "city", "country",
            "projects", "accounts",
            "notes",
        ]
        widgets = {
            "first_name":   forms.TextInput(attrs={"class": _INPUT, "placeholder": "Vorname"}),
            "last_name":    forms.TextInput(attrs={"class": _INPUT, "placeholder": "Nachname"}),
            "company_name": forms.TextInput(attrs={"class": _INPUT, "placeholder": "Firmenname (optional)"}),
            "role":         forms.Select(attrs={"class": _SELECT}),
            "email":        forms.EmailInput(attrs={"class": _INPUT}),
            "phone":        forms.TextInput(attrs={"class": _INPUT, "placeholder": "+49 30 …"}),
            "mobile":       forms.TextInput(attrs={"class": _INPUT, "placeholder": "+49 170 …"}),
            "address_line1": forms.TextInput(attrs={"class": _INPUT, "placeholder": "Straße, Nr."}),
            "postal_code":  forms.TextInput(attrs={"class": _INPUT, "placeholder": "12345"}),
            "city":         forms.TextInput(attrs={"class": _INPUT}),
            "country":      forms.TextInput(attrs={"class": _INPUT}),
            "projects":     forms.CheckboxSelectMultiple(),
            "accounts":     forms.CheckboxSelectMultiple(),
            "notes":        forms.Textarea(attrs={"class": _INPUT, "rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["role"].choices = [("", "— Rolle auswählen —")] + Lookup.choices_for("contact_role")
        self.fields["role"].required = False
        self.fields["company_name"].required = False
        self.fields["email"].required = False
        self.fields["phone"].required = False
        self.fields["mobile"].required = False
        self.fields["address_line1"].required = False
        self.fields["postal_code"].required = False
        self.fields["city"].required = False
        self.fields["notes"].required = False
        self.fields["projects"].queryset = Project.objects.exclude(
            status__in=Project.ARCHIVED_STATUSES
        ).order_by("name")
        self.fields["projects"].required = False
        self.fields["accounts"].queryset = Account.objects.filter(
            is_active=True
        ).order_by("name")
        self.fields["accounts"].required = False


class ProjectForm(forms.ModelForm):
    class Meta:
        model  = Project
        fields = [
            "company", "name", "project_type", "account", "status", "description",
            "team_lead", "team_members", "predecessor_projects",
            "start_date", "end_date",
            "budget_hours", "budget_amount",
            "purchase_price", "commission_inner", "commission_outer",
            "storage_path", "lexoffice_id",
        ]
        widgets = {
            "company":      forms.Select(attrs={"class": _SELECT, "id": "id_company"}),
            "name":         forms.TextInput(attrs={"class": _INPUT, "placeholder": "Projektname"}),
            "project_type": forms.Select(attrs={"class": _SELECT, "id": "id_project_type"}),
            "account":      forms.Select(attrs={"class": _SELECT}),
            "status":       forms.Select(attrs={"class": _SELECT}),
            "description": forms.Textarea(attrs={"class": _INPUT, "rows": 3,
                                                  "placeholder": "Kurze Projektbeschreibung …"}),
            "team_lead":   forms.Select(attrs={"class": _SELECT}),
            "team_members": forms.CheckboxSelectMultiple(),
            "start_date":  forms.DateInput(attrs={"class": _INPUT, "type": "date"}, format="%Y-%m-%d"),
            "end_date":    forms.DateInput(attrs={"class": _INPUT, "type": "date"}, format="%Y-%m-%d"),
            "budget_hours":  forms.NumberInput(attrs={"class": _INPUT, "step": "0.5", "placeholder": "z.B. 80"}),
            "budget_amount": forms.NumberInput(attrs={"class": _INPUT, "step": "1", "placeholder": "z.B. 9600"}),
            "purchase_price":    forms.NumberInput(attrs={"class": _INPUT, "step": "1", "placeholder": "z.B. 450000"}),
            "commission_inner":  forms.NumberInput(attrs={"class": _INPUT, "step": "0.01", "placeholder": "z.B. 3.57"}),
            "commission_outer":  forms.NumberInput(attrs={"class": _INPUT, "step": "0.01", "placeholder": "z.B. 3.57"}),
            "storage_path":  forms.TextInput(attrs={"class": _INPUT,
                                                     "placeholder": r"\\srv01\projekte\2024\Kunde-X"}),
            "lexoffice_id":  forms.TextInput(attrs={"class": _INPUT, "placeholder": "UUID aus Lexoffice"}),
        }

    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.core.models import User, Role

        self.fields["account"].queryset = Account.objects.filter(
            is_active=True
        ).order_by("name")
        self.fields["account"].required = False
        self.fields["account"].empty_label = "— kein Account —"

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

        # Vorgängerprojekte: alle außer sich selbst (beim Bearbeiten)
        predecessors_qs = Project.objects.order_by("name")
        if self.instance and self.instance.pk:
            predecessors_qs = predecessors_qs.exclude(pk=self.instance.pk)
        self.fields["predecessor_projects"].queryset = predecessors_qs
        self.fields["predecessor_projects"].required = False

        company_choices = [("", "Unternehmen auswählen …")] + Lookup.choices_for("company")
        self.fields["company"].choices = company_choices
        self.fields["company"].widget.choices = company_choices
        self.fields["company"].required = True
        project_type_choices = Lookup.choices_for("project_type")
        self.fields["project_type"].choices = project_type_choices
        self.fields["project_type"].widget.choices = project_type_choices

        # primary_contact ist optional im AccountForm


        # Optionale Felder
        for f in ("budget_hours", "budget_amount",
                  "purchase_price", "commission_inner", "commission_outer",
                  "storage_path", "lexoffice_id",
                  "start_date", "end_date", "description"):
            self.fields[f].required = False


# ---------------------------------------------------------------------------
# Offer Forms
# ---------------------------------------------------------------------------

class OfferForm(forms.ModelForm):
    class Meta:
        model  = Offer
        fields = [
            "title", "offer_date", "valid_until", "tax_rate",
            "intro_text", "closing_text", "payment_terms",
            "recipient_name", "recipient_email", "recipient_address",
        ]
        widgets = {
            "title":             forms.TextInput(attrs={"class": _INPUT, "placeholder": "Angebotstitel"}),
            "offer_date":        forms.DateInput(attrs={"class": _INPUT, "type": "date"}, format="%Y-%m-%d"),
            "valid_until":       forms.DateInput(attrs={"class": _INPUT, "type": "date"}, format="%Y-%m-%d"),
            "tax_rate":          forms.NumberInput(attrs={"class": _INPUT, "step": "0.01"}),
            "intro_text":        forms.Textarea(attrs={"class": _INPUT, "rows": 3, "placeholder": "Einleitungstext …"}),
            "closing_text":      forms.Textarea(attrs={"class": _INPUT, "rows": 3, "placeholder": "Nachbemerkung …"}),
            "payment_terms":     forms.Textarea(attrs={"class": _INPUT, "rows": 2, "placeholder": "z.B. Zahlbar innerhalb von 14 Tagen ohne Abzug."}),
            "recipient_name":    forms.TextInput(attrs={"class": _INPUT, "placeholder": "Empfänger Name"}),
            "recipient_email":   forms.EmailInput(attrs={"class": _INPUT, "placeholder": "empfaenger@beispiel.de"}),
            "recipient_address": forms.Textarea(attrs={"class": _INPUT, "rows": 3, "placeholder": "Straße, Nr.\nPLZ Ort"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["valid_until"].required = False
        self.fields["intro_text"].required = False
        self.fields["closing_text"].required = False
        self.fields["payment_terms"].required = False
        self.fields["recipient_name"].required = False
        self.fields["recipient_email"].required = False
        self.fields["recipient_address"].required = False


class OfferItemForm(forms.ModelForm):
    class Meta:
        model  = OfferItem
        fields = ["position", "description", "quantity", "unit", "unit_price"]
        widgets = {
            "position":    forms.NumberInput(attrs={
                "class": "w-16 px-2 py-1.5 text-sm rounded border border-slate-200 text-center",
                "min": "1",
            }),
            "description": forms.Textarea(attrs={
                "class": "w-full px-2 py-1.5 text-sm rounded border border-slate-200 resize-none",
                "rows": 2,
                "placeholder": "Leistungsbeschreibung …",
            }),
            "quantity":    forms.NumberInput(attrs={
                "class": "w-24 px-2 py-1.5 text-sm rounded border border-slate-200 text-right item-qty",
                "step": "0.01", "min": "0",
            }),
            "unit":        forms.TextInput(attrs={
                "class": "w-28 px-2 py-1.5 text-sm rounded border border-slate-200",
                "placeholder": "pauschal",
            }),
            "unit_price":  forms.NumberInput(attrs={
                "class": "w-32 px-2 py-1.5 text-sm rounded border border-slate-200 text-right item-price",
                "step": "0.01", "min": "0",
            }),
        }


OfferItemFormSet = inlineformset_factory(
    Offer,
    OfferItem,
    form=OfferItemForm,
    extra=1,
    can_delete=True,
)


# ---------------------------------------------------------------------------
# Invoice Forms
# ---------------------------------------------------------------------------

class InvoiceForm(forms.ModelForm):
    class Meta:
        model = Invoice
        fields = [
            "title", "invoice_type", "invoice_date", "due_date", "tax_rate",
            "intro_text", "closing_text", "payment_info",
            "recipient_name", "recipient_email", "recipient_address",
        ]
        widgets = {
            "title":            forms.TextInput(attrs={"class": _INPUT}),
            "invoice_type":     forms.Select(attrs={"class": _SELECT}),
            "invoice_date":     forms.DateInput(attrs={"class": _INPUT, "type": "date"}),
            "due_date":         forms.DateInput(attrs={"class": _INPUT, "type": "date"}),
            "tax_rate":         forms.NumberInput(attrs={"class": _INPUT, "step": "0.01"}),
            "intro_text":       forms.Textarea(attrs={"class": _INPUT, "rows": 3}),
            "closing_text":     forms.Textarea(attrs={"class": _INPUT, "rows": 3}),
            "payment_info":     forms.Textarea(attrs={"class": _INPUT, "rows": 3}),
            "recipient_name":   forms.TextInput(attrs={"class": _INPUT}),
            "recipient_email":  forms.EmailInput(attrs={"class": _INPUT}),
            "recipient_address": forms.Textarea(attrs={"class": _INPUT, "rows": 3}),
        }


class InvoiceItemForm(forms.ModelForm):
    class Meta:
        model = InvoiceItem
        fields = ["position", "description", "quantity", "unit", "unit_price"]
        widgets = {
            "position":    forms.NumberInput(attrs={"class": _INPUT + " w-16"}),
            "description": forms.Textarea(attrs={"class": _INPUT, "rows": 2}),
            "quantity":    forms.NumberInput(attrs={"class": _INPUT + " w-24", "step": "0.01"}),
            "unit":        forms.TextInput(attrs={"class": _INPUT + " w-28"}),
            "unit_price":  forms.NumberInput(attrs={"class": _INPUT + " w-32", "step": "0.01"}),
        }


InvoiceItemFormSet = forms.inlineformset_factory(
    Invoice, InvoiceItem, form=InvoiceItemForm, extra=1, can_delete=True
)
