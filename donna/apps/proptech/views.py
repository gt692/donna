import logging

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, DetailView, ListView, UpdateView, View

from .forms import DescriptionTemplateForm, PropertyReportFileForm, PropertyReportForm
from .models import DescriptionTemplate, PropertyReport, PropertyReportFile

logger = logging.getLogger(__name__)


class PropTechMixin(LoginRequiredMixin):
    pass


# ── Reports ────────────────────────────────────────────────────────────────────

class PropertyReportListView(PropTechMixin, ListView):
    model = PropertyReport
    template_name = "proptech/report_list.html"
    context_object_name = "reports"

    def get_queryset(self):
        qs = PropertyReport.objects.select_related("project", "created_by")
        if not self.request.user.is_admin:
            qs = qs.filter(created_by=self.request.user)
        return qs


class PropertyReportCreateView(PropTechMixin, CreateView):
    model = PropertyReport
    form_class = PropertyReportForm
    template_name = "proptech/report_form.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"] = "Neue Baubeschreibung"
        ctx["submit_label"] = "Erstellen"
        return ctx

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        return super().form_valid(form)

    def get_success_url(self):
        return reverse("proptech:report_detail", kwargs={"pk": self.object.pk})


class PropertyReportDetailView(PropTechMixin, DetailView):
    model = PropertyReport
    template_name = "proptech/report_detail.html"
    context_object_name = "report"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        report = self.object
        ctx["files_by_type"] = {
            "photo":   report.files.filter(file_type="photo"),
            "plan":    report.files.filter(file_type="plan"),
            "bauakte": report.files.filter(file_type="bauakte"),
            "misc":    report.files.filter(file_type="misc"),
        }
        ctx["upload_form"] = PropertyReportFileForm()
        return ctx


class PropertyReportUpdateView(PropTechMixin, UpdateView):
    model = PropertyReport
    form_class = PropertyReportForm
    template_name = "proptech/report_form.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"] = "Baubeschreibung bearbeiten"
        ctx["submit_label"] = "Speichern"
        return ctx

    def get_success_url(self):
        return reverse("proptech:report_detail", kwargs={"pk": self.object.pk})


class PropertyReportDeleteView(PropTechMixin, View):
    def post(self, request, pk):
        report = get_object_or_404(PropertyReport, pk=pk)
        title = report.title
        report.delete()
        messages.success(request, f'Baubeschreibung "{title}" gelöscht.')
        return redirect("proptech:report_list")


class PropertyReportGenerateView(PropTechMixin, View):
    def post(self, request, pk):
        report = get_object_or_404(PropertyReport, pk=pk)
        from django.conf import settings as django_settings
        if not getattr(django_settings, "ANTHROPIC_API_KEY", ""):
            messages.error(request, "Kein Anthropic API-Key konfiguriert (ANTHROPIC_API_KEY in .env).")
            return redirect("proptech:report_detail", pk=pk)
        try:
            from .services import PropertyDescriptionService
            text = PropertyDescriptionService().generate(report)
            report.generated_text = text
            report.generated_at = timezone.now()
            report.save(update_fields=["generated_text", "generated_at"])
            messages.success(request, "Baubeschreibung erfolgreich generiert.")
        except Exception as exc:
            logger.exception("Generierung fehlgeschlagen für %s", pk)
            messages.error(request, f"Fehler bei der Generierung: {exc}")
        return redirect("proptech:report_detail", pk=pk)


class PropertyReportSaveTextView(PropTechMixin, View):
    """Speichert den manuell bearbeiteten generierten Text."""
    def post(self, request, pk):
        report = get_object_or_404(PropertyReport, pk=pk)
        report.generated_text = request.POST.get("generated_text", "")
        report.save(update_fields=["generated_text"])
        messages.success(request, "Text gespeichert.")
        return redirect("proptech:report_detail", pk=pk)


# ── Dateien ────────────────────────────────────────────────────────────────────

class PropertyReportFileUploadView(PropTechMixin, View):
    def post(self, request, pk):
        report = get_object_or_404(PropertyReport, pk=pk)
        form = PropertyReportFileForm(request.POST, request.FILES)
        if form.is_valid():
            f = form.save(commit=False)
            f.report = report
            f.save()
        else:
            messages.error(request, "Fehler beim Hochladen. Bitte Datei und Typ prüfen.")
        return redirect("proptech:report_detail", pk=pk)


class PropertyReportFileDeleteView(PropTechMixin, View):
    def post(self, request, pk, fid):
        f = get_object_or_404(PropertyReportFile, pk=fid, report__pk=pk)
        try:
            f.file.delete(save=False)
        except Exception:
            pass
        f.delete()
        return redirect("proptech:report_detail", pk=pk)


# ── Vorlagen ───────────────────────────────────────────────────────────────────

class DescriptionTemplateListView(PropTechMixin, ListView):
    model = DescriptionTemplate
    template_name = "proptech/template_list.html"
    context_object_name = "templates"


class DescriptionTemplateCreateView(PropTechMixin, CreateView):
    model = DescriptionTemplate
    form_class = DescriptionTemplateForm
    template_name = "proptech/template_form.html"
    success_url = reverse_lazy("proptech:template_list")

    def form_valid(self, form):
        response = super().form_valid(form)
        obj = self.object
        if obj.file:
            import os
            if os.path.splitext(obj.file.name)[1].lower() == ".pdf":
                from .services import _extract_pdf_text
                text = _extract_pdf_text(obj.file)
                if text:
                    obj.extracted_text = text
                    obj.save(update_fields=["extracted_text"])
        messages.success(self.request, f'Vorlage "{obj.name}" hochgeladen.')
        return response


class DescriptionTemplateDeleteView(PropTechMixin, View):
    def post(self, request, pk):
        tpl = get_object_or_404(DescriptionTemplate, pk=pk)
        name = tpl.name
        try:
            tpl.file.delete(save=False)
        except Exception:
            pass
        tpl.delete()
        messages.success(request, f'Vorlage "{name}" gelöscht.')
        return redirect("proptech:template_list")
