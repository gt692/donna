from django import forms

from .models import DescriptionTemplate, PropertyReport, PropertyReportFile

_TW = (
    "w-full px-3 py-2 border border-slate-200 rounded-lg text-sm "
    "focus:outline-none focus:ring-2 focus:ring-[#2F6FB3] transition"
)
_TW_SELECT = (
    "w-full px-3 py-2 border border-slate-200 rounded-lg text-sm bg-white "
    "focus:outline-none focus:ring-2 focus:ring-[#2F6FB3] transition"
)


class PropertyReportForm(forms.ModelForm):
    class Meta:
        model = PropertyReport
        fields = [
            "title", "role", "project",
            "street", "postal_code", "city",
            "building_type", "year_of_construction",
            "living_area", "plot_area",
            "number_of_rooms", "number_of_floors",
            "condition", "additional_notes",
        ]
        widgets = {
            "title": forms.TextInput(attrs={"class": _TW, "placeholder": "z.B. EFH Musterstraße 1, Berlin"}),
            "role": forms.Select(attrs={"class": _TW_SELECT}),
            "project": forms.Select(attrs={"class": _TW_SELECT}),
            "street": forms.TextInput(attrs={"class": _TW, "placeholder": "Musterstraße 1"}),
            "postal_code": forms.TextInput(attrs={"class": _TW, "placeholder": "12345"}),
            "city": forms.TextInput(attrs={"class": _TW, "placeholder": "Berlin"}),
            "building_type": forms.Select(attrs={"class": _TW_SELECT}),
            "year_of_construction": forms.NumberInput(attrs={"class": _TW, "placeholder": "z.B. 1985"}),
            "living_area": forms.NumberInput(attrs={"class": _TW, "step": "0.01", "placeholder": "m²"}),
            "plot_area": forms.NumberInput(attrs={"class": _TW, "step": "0.01", "placeholder": "m²"}),
            "number_of_rooms": forms.NumberInput(attrs={"class": _TW, "step": "0.5", "placeholder": "z.B. 4.5"}),
            "number_of_floors": forms.NumberInput(attrs={"class": _TW, "placeholder": "z.B. 2"}),
            "condition": forms.TextInput(attrs={"class": _TW, "placeholder": "z.B. Neubau, saniert, renovierungsbedürftig…"}),
            "additional_notes": forms.Textarea(attrs={
                "class": _TW, "rows": 4,
                "placeholder": "Besonderheiten, Ausstattungsdetails, Hinweise für die KI…",
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["project"].required = False
        self.fields["project"].empty_label = "— Kein Projekt zugeordnet —"
        from apps.crm.models import Project
        self.fields["project"].queryset = Project.objects.filter(
            deleted_at__isnull=True
        ).order_by("name")


class PropertyReportFileForm(forms.ModelForm):
    class Meta:
        model = PropertyReportFile
        fields = ["file_type", "file", "label"]
        widgets = {
            "file_type": forms.Select(attrs={"class": _TW_SELECT}),
            "label": forms.TextInput(attrs={"class": _TW, "placeholder": "Optionale Bezeichnung"}),
        }


class DescriptionTemplateForm(forms.ModelForm):
    class Meta:
        model = DescriptionTemplate
        fields = ["name", "role", "building_type", "street", "postal_code", "city", "file", "is_active"]
        widgets = {
            "name": forms.TextInput(attrs={"class": _TW, "placeholder": "z.B. Exposé EFH München Schwabing"}),
            "role": forms.Select(attrs={"class": _TW_SELECT}),
            "building_type": forms.Select(attrs={"class": _TW_SELECT}),
            "street": forms.TextInput(attrs={"class": _TW, "placeholder": "Musterstraße 1", "autocomplete": "off"}),
            "postal_code": forms.TextInput(attrs={"class": _TW, "placeholder": "12345"}),
            "city": forms.TextInput(attrs={"class": _TW, "placeholder": "München"}),
        }
