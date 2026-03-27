import logging
import os

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
        from django.conf import settings as dj_settings
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"] = "Neue Baubeschreibung"
        ctx["submit_label"] = "Erstellen"
        ctx["google_maps_api_key"] = dj_settings.GOOGLE_MAPS_API_KEY
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
            "photo":          report.files.filter(file_type="photo"),
            "plan":           report.files.filter(file_type="plan"),
            "bauakte":        report.files.filter(file_type="bauakte"),
            "energieausweis": report.files.filter(file_type="energieausweis"),
            "misc":           report.files.filter(file_type="misc"),
        }
        ctx["upload_tabs"] = [
            ("photo",          "Fotos",         "violet"),
            ("plan",           "Pläne",          "blue"),
            ("bauakte",        "Bauakte",        "amber"),
            ("energieausweis", "Energieausweis", "emerald"),
            ("misc",           "Sonstiges",      "slate"),
        ]
        ctx["upload_form"] = PropertyReportFileForm()
        ctx["pending_files_count"] = report.files.filter(markdown_content="").count()
        ctx["failed_files_count"] = report.files.filter(markdown_content__startswith="[").count()
        return ctx


class PropertyReportUpdateView(PropTechMixin, UpdateView):
    model = PropertyReport
    form_class = PropertyReportForm
    template_name = "proptech/report_form.html"

    def get_context_data(self, **kwargs):
        from django.conf import settings as dj_settings
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"] = "Baubeschreibung bearbeiten"
        ctx["submit_label"] = "Speichern"
        ctx["google_maps_api_key"] = dj_settings.GOOGLE_MAPS_API_KEY
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


class PropertyReportRefineView(PropTechMixin, View):
    """Überarbeitet den generierten Text anhand von Nutzer-Feedback via Claude."""
    def post(self, request, pk):
        import json
        from django.http import JsonResponse
        report = get_object_or_404(PropertyReport, pk=pk)
        feedback = request.POST.get("feedback", "").strip()
        current_text = request.POST.get("current_text", report.generated_text).strip()

        if not feedback:
            return JsonResponse({"error": "Kein Feedback angegeben."}, status=400)
        if not current_text:
            return JsonResponse({"error": "Noch kein generierter Text vorhanden."}, status=400)

        from django.conf import settings as dj_settings
        if not getattr(dj_settings, "ANTHROPIC_API_KEY", ""):
            return JsonResponse({"error": "Kein Anthropic API-Key konfiguriert."}, status=500)

        try:
            import anthropic
            client = anthropic.Anthropic(api_key=dj_settings.ANTHROPIC_API_KEY)
            response = client.messages.create(
                model="claude-opus-4-6",
                max_tokens=4096,
                system=(
                    "Du bist ein erfahrener Immobilien-Texter. Du erhältst eine bestehende "
                    "Objektbeschreibung und konkrete Überarbeitungshinweise. "
                    "Überarbeite den Text präzise gemäß dem Feedback. "
                    "Behalte alles bei was nicht kritisiert wird. "
                    "Gib nur den überarbeiteten Text zurück, keine Erklärungen."
                ),
                messages=[{
                    "role": "user",
                    "content": (
                        f"## Bestehende Beschreibung:\n\n{current_text}\n\n"
                        f"## Mein Feedback / was überarbeitet werden soll:\n\n{feedback}\n\n"
                        "Bitte überarbeite die Beschreibung entsprechend."
                    ),
                }],
            )
            refined_text = response.content[0].text
            report.generated_text = refined_text
            report.save(update_fields=["generated_text"])
            return JsonResponse({"text": refined_text})
        except Exception as exc:
            logger.exception("Überarbeitung fehlgeschlagen für %s", pk)
            return JsonResponse({"error": str(exc)}, status=500)


# ── Dateien ────────────────────────────────────────────────────────────────────

HEIC_EXTENSIONS = {".heic", ".heif"}
BLOCKED_EXTENSIONS = {".tiff", ".tif", ".bmp"}


def _convert_heic_to_jpeg(uploaded_file):
    """Konvertiert eine HEIC/HEIF-Datei in JPEG. Gibt ein neues File-Objekt zurück."""
    from io import BytesIO
    from django.core.files.uploadedfile import InMemoryUploadedFile
    from PIL import Image
    try:
        from pillow_heif import register_heif_opener
        register_heif_opener()
    except ImportError:
        return None
    try:
        img = Image.open(uploaded_file)
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        output = BytesIO()
        img.save(output, format="JPEG", quality=92)
        output.seek(0)
        new_name = os.path.splitext(uploaded_file.name)[0] + ".jpg"
        return InMemoryUploadedFile(
            output, "file", new_name, "image/jpeg", output.getbuffer().nbytes, None
        )
    except Exception as exc:
        logger.warning("HEIC-Konvertierung fehlgeschlagen (%s): %s", uploaded_file.name, exc)
        return None


class PropertyReportFileUploadView(PropTechMixin, View):
    def post(self, request, pk):
        report = get_object_or_404(PropertyReport, pk=pk)
        file_type = request.POST.get("file_type", "")
        label = request.POST.get("label", "")
        files = request.FILES.getlist("file")
        if not files or not file_type:
            messages.error(request, "Bitte Dateityp wählen und mindestens eine Datei auswählen.")
            return redirect("proptech:report_detail", pk=pk)
        converted = skipped = 0
        for uploaded in files:
            ext = os.path.splitext(uploaded.name)[1].lower()
            if ext in BLOCKED_EXTENSIONS:
                skipped += 1
                continue
            if ext in HEIC_EXTENSIONS:
                jpeg = _convert_heic_to_jpeg(uploaded)
                if jpeg:
                    uploaded = jpeg
                    converted += 1
                else:
                    skipped += 1
                    continue
            PropertyReportFile.objects.create(
                report=report,
                file_type=file_type,
                file=uploaded,
                label=label,
            )
        if converted:
            messages.info(request, f"{converted} HEIC-Foto{'s' if converted != 1 else ''} automatisch zu JPEG konvertiert.")
        if skipped:
            messages.warning(request, f"{skipped} Datei(en) übersprungen (nicht unterstütztes Format).")
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


class PropertyReportFileReprocessView(PropTechMixin, View):
    """Setzt markdown_content aller fehlgeschlagenen Dateien zurück → werden beim nächsten Generieren neu verarbeitet."""
    def post(self, request, pk):
        report = get_object_or_404(PropertyReport, pk=pk)
        reset_count = report.files.filter(markdown_content__startswith="[").update(markdown_content="")
        if reset_count:
            messages.success(request, f"{reset_count} Datei(en) zum Neuverarbeiten vorgemerkt — bitte jetzt generieren.")
        else:
            messages.info(request, "Keine fehlgeschlagenen Dateien gefunden.")
        return redirect("proptech:report_detail", pk=pk)


class PropertyReportFileBulkDeleteView(PropTechMixin, View):
    def post(self, request, pk):
        file_ids = request.POST.getlist("file_ids")
        if file_ids:
            files = PropertyReportFile.objects.filter(pk__in=file_ids, report__pk=pk)
            for f in files:
                try:
                    f.file.delete(save=False)
                except Exception:
                    pass
            deleted_count = files.count()
            files.delete()
            messages.success(request, f"{deleted_count} Datei(en) gelöscht.")
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

    def get_context_data(self, **kwargs):
        from django.conf import settings as dj_settings
        ctx = super().get_context_data(**kwargs)
        ctx["google_maps_api_key"] = dj_settings.GOOGLE_MAPS_API_KEY
        return ctx

    def form_valid(self, form):
        response = super().form_valid(form)
        obj = self.object
        if obj.file:
            import os
            from .services import _extract_pdf_text
            ext = os.path.splitext(obj.file.name)[1].lower()
            if ext == ".pdf":
                text = _extract_pdf_text(obj.file)
                if text:
                    obj.extracted_text = f"# Vorlage: {obj.name}\n\n{text}"
                    obj.save(update_fields=["extracted_text"])
            elif ext in (".txt", ".md"):
                try:
                    with obj.file.open("r") as f:
                        text = f.read()
                    if text:
                        obj.extracted_text = f"# Vorlage: {obj.name}\n\n{text}"
                        obj.save(update_fields=["extracted_text"])
                except Exception:
                    pass
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
