"""
worktrack/forms.py
"""
from django import forms
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from .models import TimeEntry

_INPUT = (
    "w-full px-3 py-2 rounded-lg border border-slate-200 bg-white "
    "focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent "
    "text-sm transition"
)
_SELECT = _INPUT + " cursor-pointer"


class TimeEntryForm(forms.ModelForm):
    """Formular zum Erstellen und Bearbeiten einer Zeitbuchung."""

    class Meta:
        model  = TimeEntry
        fields = [
            "project", "date", "duration_hours",
            "start_time", "end_time",
            "activity_type", "description", "is_billable",
        ]
        widgets = {
            "project": forms.Select(attrs={"class": _SELECT}),
            "date": forms.DateInput(
                attrs={"class": _INPUT, "type": "date"},
                format="%Y-%m-%d",
            ),
            "duration_hours": forms.NumberInput(
                attrs={
                    "class": _INPUT,
                    "step": "0.25", "min": "0.25", "max": "24",
                    "placeholder": "1.50",
                }
            ),
            "start_time": forms.TimeInput(
                attrs={"class": _INPUT, "type": "time"}, format="%H:%M"
            ),
            "end_time": forms.TimeInput(
                attrs={"class": _INPUT, "type": "time"}, format="%H:%M"
            ),
            "activity_type": forms.Select(attrs={"class": _SELECT, "required": False}),
            "description": forms.Textarea(
                attrs={
                    "class": _INPUT,
                    "rows": 3,
                    "placeholder": "Was wurde gemacht? (z.B. Feature X implementiert, Kundencall)",
                }
            ),
            "is_billable": forms.CheckboxInput(
                attrs={"class": "w-4 h-4 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"}
            ),
        }

    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.crm.models import Project
        if user.is_admin:
            qs = Project.objects.filter(
                status__in=["active", "on_hold"]
            ).select_related("account").order_by("account__name", "name")
        else:
            qs = user.assigned_projects.filter(
                status__in=["active", "on_hold"]
            ).select_related("account").order_by("account__name", "name")

        self.fields["project"].queryset = qs
        self.fields["project"].label_from_instance = lambda p: f"{p.account.name} — {p.name}"
        self.fields["project"].empty_label = "Projekt auswählen …"

        self.fields["activity_type"].required = False
        self.fields["activity_type"].choices = [("", "Tätigkeitsart (optional)")] + list(
            TimeEntry.ActivityCategory.choices
        )

        # duration_hours optional wenn Von/Bis gesetzt
        self.fields["duration_hours"].required = False

        if not self.initial.get("date") and not self.data.get("date"):
            self.initial["date"] = timezone.now().date()

    def clean(self):
        from decimal import Decimal, ROUND_HALF_UP
        import datetime
        cleaned = super().clean()
        start = cleaned.get("start_time")
        end   = cleaned.get("end_time")

        if start and end:
            if end <= start:
                raise forms.ValidationError(
                    _("Die Endzeit muss nach der Startzeit liegen."), code="invalid_times"
                )
            # Dauer automatisch berechnen (auf 0.25 runden)
            delta = datetime.datetime.combine(datetime.date.today(), end) \
                  - datetime.datetime.combine(datetime.date.today(), start)
            hours = Decimal(str(delta.seconds / 3600)).quantize(Decimal("0.01"))
            cleaned["duration_hours"] = hours

        if not cleaned.get("duration_hours"):
            raise forms.ValidationError(
                _("Bitte entweder Von/Bis-Zeiten oder die Dauer in Stunden angeben."),
                code="missing_duration",
            )
        return cleaned


class ApprovalRejectForm(forms.Form):
    """Ablehnungs-Formular mit Pflicht-Begründung."""
    review_note = forms.CharField(
        label=_("Begründung (Pflichtfeld)"),
        widget=forms.Textarea(
            attrs={
                "class": _INPUT,
                "rows": 3,
                "placeholder": "Bitte gib an, warum die Buchung abgelehnt wird …",
            }
        ),
        min_length=10,
    )
