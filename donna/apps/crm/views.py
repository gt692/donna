"""
crm/views.py

Account- und Projekt-Verwaltung.

URLs:
  /crm/accounts/               → AccountListView
  /crm/accounts/new/           → AccountCreateView
  /crm/accounts/<pk>/          → AccountDetailView
  /crm/accounts/<pk>/edit/     → AccountUpdateView

  /crm/projects/               → ProjectListView
  /crm/projects/new/           → ProjectCreateView
  /crm/projects/<pk>/          → ProjectDetailView
  /crm/projects/<pk>/edit/     → ProjectUpdateView
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

import datetime

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404, redirect
from django.http import HttpResponse, JsonResponse
from django.views.generic import CreateView, DetailView, ListView, TemplateView, UpdateView, View

from .forms import AccountForm, ContactForm, ProjectForm
from .models import Account, Contact, Document, Project, ProjectBudgetExtension, ProjectMemberRate


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _all_projects_list(exclude_pk=None) -> list:
    qs = Project.objects.order_by("name")
    if exclude_pk:
        qs = qs.exclude(pk=exclude_pk)
    return [{"id": str(p.pk), "label": str(p)} for p in qs]


def _member_rates_data(form, project=None) -> dict:
    """Baut ein Dict {user_pk: {name, role, default_rate, current_rate}} für das Template."""
    data = {}
    for user in form.fields["team_members"].queryset:
        data[str(user.pk)] = {
            "name": user.get_full_name() or user.username,
            "role": user.get_role_display(),
            "default_rate": float(user.default_hourly_rate) if user.default_hourly_rate is not None else None,
            "current_rate": None,
        }
    if project and project.pk:
        for mr in project.member_rates.select_related("user"):
            key = str(mr.user_id)
            if key in data:
                data[key]["current_rate"] = float(mr.hourly_rate)
    return data


def _save_member_rates(request, project, team_members) -> None:
    """Speichert/aktualisiert projektspezifische Stundensätze der Teammitglieder."""
    team_pks = [u.pk for u in team_members]
    project.member_rates.exclude(user_id__in=team_pks).delete()
    for user in team_members:
        raw = request.POST.get(f"member_rate_{user.pk}", "").strip()
        try:
            rate = Decimal(raw)
        except InvalidOperation:
            default = user.default_hourly_rate
            if default is None:
                continue
            rate = Decimal(str(default))
        ProjectMemberRate.objects.update_or_create(
            project=project, user=user, defaults={"hourly_rate": rate}
        )


# ---------------------------------------------------------------------------
# Mixins
# ---------------------------------------------------------------------------

class CRMMixin(LoginRequiredMixin):
    login_url = "/auth/login/"


class AdminOrLeadMixin(CRMMixin, UserPassesTestMixin):
    """Nur Admins und Teamleiter dürfen CRM-Objekte anlegen/bearbeiten."""
    def test_func(self):
        return self.request.user.can_approve_time_entries()


# ---------------------------------------------------------------------------
# Account-Views
# ---------------------------------------------------------------------------

def _save_inline_contact(request, account):
    """Legt einen neuen Kontakt an und setzt ihn als primary_contact, wenn
    new_contact_first_name oder new_contact_last_name im POST vorhanden sind."""
    fn = request.POST.get("new_contact_first_name", "").strip()
    ln = request.POST.get("new_contact_last_name", "").strip()
    if not (fn or ln):
        return
    contact = Contact.objects.create(
        first_name=fn,
        last_name=ln,
        email=request.POST.get("new_contact_email", "").strip(),
        phone=request.POST.get("new_contact_phone", "").strip(),
        mobile=request.POST.get("new_contact_mobile", "").strip(),
        role=request.POST.get("new_contact_role", "") or "",
    )
    contact.accounts.add(account)
    account.primary_contact = contact
    account.save(update_fields=["primary_contact"])


class AccountListView(CRMMixin, ListView):
    model               = Account
    template_name       = "crm/account_list.html"
    context_object_name = "accounts"
    paginate_by         = 25

    def get_queryset(self):
        qs = (
            Account.objects
            .filter(is_active=True)
            .annotate(project_count=Count("projects"))
            .select_related("account_manager")
            .order_by("name")
        )
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(name__icontains=q)
        t = self.request.GET.get("type", "")
        if t:
            qs = qs.filter(account_type=t)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["q"]            = self.request.GET.get("q", "")
        ctx["type_filter"]  = self.request.GET.get("type", "")
        ctx["account_types"] = Account.AccountType.choices
        return ctx


class AccountCreateView(AdminOrLeadMixin, CreateView):
    model         = Account
    form_class    = AccountForm
    template_name = "crm/account_form.html"

    def form_valid(self, form):
        account = form.save()
        _save_inline_contact(self.request, account)
        messages.success(self.request, f'Account „{account.name}" wurde erstellt.')
        return redirect("crm:account_detail", pk=account.pk)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"]           = "Neuer Account"
        ctx["submit_label"]         = "Account erstellen"
        ctx["contact_role_choices"] = Contact.Role.choices
        ctx["contact_emails"]       = {str(k): v for k, v in Contact.objects.values_list("id", "email")}
        return ctx


class AccountDetailView(CRMMixin, DetailView):
    model         = Account
    template_name = "crm/account_detail.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["projects"] = (
            self.object.projects
            .select_related("team_lead")
            .order_by("-created_at")
        )
        return ctx


class AccountUpdateView(AdminOrLeadMixin, UpdateView):
    model         = Account
    form_class    = AccountForm
    template_name = "crm/account_form.html"

    def form_valid(self, form):
        account = form.save()
        _save_inline_contact(self.request, account)
        messages.success(self.request, f'Account „{account.name}" wurde aktualisiert.')
        return redirect("crm:account_detail", pk=account.pk)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"]           = f"{self.object.name} bearbeiten"
        ctx["submit_label"]         = "Speichern"
        ctx["contact_role_choices"] = Contact.Role.choices
        ctx["contact_emails"]       = {str(k): v for k, v in Contact.objects.values_list("id", "email")}
        return ctx


# ---------------------------------------------------------------------------
# Projekt-Views
# ---------------------------------------------------------------------------

class ProjectListView(CRMMixin, ListView):
    model               = Project
    template_name       = "crm/project_list.html"
    context_object_name = "projects"
    paginate_by         = 25

    def _base_qs(self):
        user = self.request.user
        if user.is_admin:
            qs = Project.objects.all()
        else:
            qs = (Project.objects.filter(team_lead=user) | user.assigned_projects.all()).distinct()
        return qs.select_related("account", "team_lead")

    def get_queryset(self):
        qs = self._base_qs().exclude(status__in=Project.ARCHIVED_STATUSES).order_by("-created_at")

        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(name__icontains=q) | qs.filter(account__name__icontains=q)

        status = self.request.GET.get("status", "")
        if status:
            qs = qs.filter(status=status)

        return qs.distinct()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["q"]             = self.request.GET.get("q", "")
        ctx["status_filter"] = self.request.GET.get("status", "")
        # Nur aktive Status im Filter anbieten
        ctx["status_choices"] = [
            (v, l) for v, l in Project.Status.choices
            if v not in Project.ARCHIVED_STATUSES
        ]
        ctx["archive_count"] = self._base_qs().filter(
            status__in=Project.ARCHIVED_STATUSES
        ).count()
        return ctx


class ProjectArchiveView(CRMMixin, TemplateView):
    template_name = "crm/project_archive.html"

    def _base_qs(self):
        user = self.request.user
        if user.is_admin:
            qs = Project.objects.all()
        else:
            qs = (Project.objects.filter(team_lead=user) | user.assigned_projects.all()).distinct()
        return qs.select_related("account", "team_lead")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        base = self._base_qs()
        ctx["completed_projects"] = base.filter(
            status=Project.Status.COMPLETED
        ).order_by("-updated_at")
        ctx["cancelled_projects"] = base.filter(
            status=Project.Status.CANCELLED
        ).order_by("-updated_at")
        ctx["offer_lost_projects"] = base.filter(
            status=Project.Status.OFFER_LOST
        ).order_by("-updated_at")
        return ctx


class ProjectCreateView(AdminOrLeadMixin, CreateView):
    model         = Project
    form_class    = ProjectForm
    template_name = "crm/project_form.html"

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw["user"] = self.request.user
        return kw

    def form_valid(self, form):
        project = form.save(commit=False)
        project.created_by = self.request.user
        project.status = Project.Status.LEAD  # neue Projekte immer als Lead

        # Inline-Account anlegen falls kein bestehender ausgewählt
        if not project.account_id:
            new_name = self.request.POST.get("new_account_name", "").strip()
            new_type = self.request.POST.get("new_account_type", Account.AccountType.COMPANY)
            if new_name:
                project.account = Account.objects.create(
                    name=new_name,
                    account_type=new_type,
                )
            else:
                form.add_error(None, "Bitte einen Account auswählen oder einen neuen Namen eingeben.")
                return self.form_invalid(form)

        project.save()
        form.save_m2m()
        _save_member_rates(self.request, project, form.cleaned_data["team_members"])
        messages.success(self.request, f'Projekt „{project.name}" wurde erstellt.')
        return redirect("crm:project_detail", pk=project.pk)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"]      = "Neues Projekt"
        ctx["submit_label"]    = "Projekt erstellen"
        ctx["is_create"]       = True
        ctx["account_types"]   = Account.AccountType.choices
        form = kwargs.get("form") or ctx.get("form")
        if form:
            ctx["member_rates_data"] = _member_rates_data(form, project=None)
        ctx["project_types_by_company"] = Project.PROJECT_TYPES_BY_COMPANY
        ctx["all_projects_json"] = _all_projects_list()
        ctx["selected_predecessors_json"] = []
        return ctx


class AccountSearchView(CRMMixin, View):
    """AJAX: Accounts per Name suchen (für Projekt-Anlage-Widget)."""

    def get(self, request):
        q = request.GET.get("q", "").strip()
        qs = Account.objects.filter(is_active=True)
        if q:
            qs = qs.filter(name__icontains=q)
        results = [{"id": str(a.pk), "name": a.name, "type": a.get_account_type_display()}
                   for a in qs.order_by("name")[:10]]
        return JsonResponse({"results": results})


class ProjectDetailView(CRMMixin, DetailView):
    model         = Project
    template_name = "crm/project_detail.html"

    def get_context_data(self, **kwargs):
        ctx     = super().get_context_data(**kwargs)
        project = self.object

        from apps.worktrack.models import TimeEntry
        entries = (
            TimeEntry.objects
            .filter(project=project)
            .select_related("user")
            .order_by("-date")[:20]
        )

        # Stunden-Statistik
        stats = TimeEntry.objects.filter(project=project).aggregate(
            total=Sum("duration_hours"),
            approved=Sum("duration_hours", filter=__import__("django.db.models", fromlist=["Q"]).Q(status="approved")),
        )
        hours_total    = float(stats["total"] or 0)
        hours_approved = float(stats["approved"] or 0)

        # Kosten: freigegebene Stunden × projektspezifischer Stundensatz je Mitglied
        rates_map = {str(mr.user_id): float(mr.hourly_rate) for mr in project.member_rates.all()}
        approved_entries = (
            TimeEntry.objects
            .filter(project=project, status="approved")
            .values("user_id", "duration_hours")
        )
        cost_approved = sum(
            float(e["duration_hours"]) * rates_map.get(str(e["user_id"]), 0)
            for e in approved_entries
        )

        extensions = list(project.budget_extensions.all())
        base_budget      = float(project.budget_amount) if project.budget_amount else None
        extra_budget     = sum(float(e.amount) for e in extensions)
        budget_amount    = (base_budget + extra_budget) if base_budget is not None else None
        budget_cost_pct  = min(int(cost_approved / budget_amount * 100), 100) if budget_amount else None
        budget_remaining = budget_amount - cost_approved if budget_amount is not None else None

        # Team-Mitglieder mit Stundensatz für Template aufbereiten
        team_members_with_rates = [
            {
                "member": m,
                "rate": rates_map.get(str(m.pk)),
            }
            for m in project.team_members.all()
        ]

        # Provisions-Berechnung (nur Projekttyp "sale")
        commission_net   = None
        commission_gross = None
        if project.project_type == "sale" and project.purchase_price:
            inner = float(project.commission_inner or 0)
            outer = float(project.commission_outer or 0)
            commission_net   = float(project.purchase_price) * (inner + outer) / 100
            commission_gross = commission_net * 1.19

        ctx["commission_net"]          = commission_net
        ctx["commission_gross"]        = commission_gross
        ctx["time_entries"]            = entries
        ctx["hours_total"]             = hours_total
        ctx["hours_approved"]          = hours_approved
        ctx["cost_approved"]           = cost_approved
        ctx["has_rates"]               = bool(rates_map)
        ctx["budget_amount_total"]     = budget_amount
        ctx["budget_cost_pct"]         = budget_cost_pct
        ctx["budget_remaining"]        = budget_remaining
        ctx["budget_extensions"]       = extensions
        ctx["documents"]               = project.documents.order_by("-document_date")
        ctx["team_members"]            = project.team_members.all()
        ctx["team_members_with_rates"] = team_members_with_rates
        ctx["budget_pct"]              = (
            min(int(hours_approved / float(project.budget_hours) * 100), 100)
            if project.budget_hours else None
        )
        ctx["today"]                   = datetime.date.today().isoformat()
        return ctx


class ProjectUpdateView(AdminOrLeadMixin, UpdateView):
    model         = Project
    form_class    = ProjectForm
    template_name = "crm/project_form.html"

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw["user"] = self.request.user
        return kw

    def form_valid(self, form):
        project = form.save()
        _save_member_rates(self.request, project, form.cleaned_data["team_members"])
        messages.success(self.request, f'Projekt „{project.name}" wurde aktualisiert.')
        return redirect("crm:project_detail", pk=project.pk)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"]   = f"{self.object.name} bearbeiten"
        ctx["submit_label"] = "Speichern"
        form = kwargs.get("form") or ctx.get("form")
        if form:
            ctx["member_rates_data"] = _member_rates_data(form, project=self.object)
        ctx["project_types_by_company"] = Project.PROJECT_TYPES_BY_COMPANY
        ctx["all_projects_json"] = _all_projects_list(exclude_pk=self.object.pk)
        ctx["selected_predecessors_json"] = [
            {"id": str(p.pk), "label": str(p)}
            for p in self.object.predecessor_projects.all()
        ]
        return ctx


# ---------------------------------------------------------------------------
# Budget-Erweiterung hinzufügen (POST-only)
# ---------------------------------------------------------------------------

class ProjectBudgetExtensionCreateView(AdminOrLeadMixin, View):
    def post(self, request, pk):
        project = get_object_or_404(Project, pk=pk)
        amount_raw = request.POST.get("amount", "").strip()
        date_raw   = request.POST.get("approved_at", "").strip()
        note       = request.POST.get("note", "").strip()
        try:
            amount      = Decimal(amount_raw)
            approved_at = datetime.date.fromisoformat(date_raw)
            ProjectBudgetExtension.objects.create(
                project=project, amount=amount, approved_at=approved_at, note=note
            )
            messages.success(request, f"Budget-Erweiterung von {amount:,.0f} € hinzugefügt.")
        except (InvalidOperation, ValueError):
            messages.error(request, "Ungültiger Betrag oder Datum.")
        return redirect("crm:project_detail", pk=pk)


class ProjectBudgetExtensionDeleteView(AdminOrLeadMixin, View):
    def post(self, request, pk, ext_pk):
        ext = get_object_or_404(ProjectBudgetExtension, pk=ext_pk, project_id=pk)
        ext.delete()
        messages.success(request, "Budget-Erweiterung entfernt.")
        return redirect("crm:project_detail", pk=pk)


# ---------------------------------------------------------------------------
# Kanban-Board
# ---------------------------------------------------------------------------

class KanbanView(CRMMixin, TemplateView):
    template_name = "crm/kanban.html"

    # status, label, company filter ("" = alle), css-Klassen direkt
    COLUMNS = [
        {"status": "lead",       "label": "Lead",       "company": "",
         "hdr_bg": "bg-slate-100",    "hdr_border": "border-slate-200",
         "dot": "bg-slate-400",       "badge_bg": "bg-slate-200",    "badge_text": "text-slate-600"},
        {"status": "offer_sent", "label": "Angebot",    "company": "",
         "hdr_bg": "bg-amber-50",     "hdr_border": "border-amber-200",
         "dot": "bg-amber-400",       "badge_bg": "bg-amber-100",    "badge_text": "text-amber-700"},
        {"status": "active",     "label": "GT Immo",    "company": "gt_immo",
         "hdr_bg": "bg-green-50",     "hdr_border": "border-green-200",
         "dot": "bg-green-500",       "badge_bg": "bg-green-100",    "badge_text": "text-green-700"},
        {"status": "active",     "label": "GT Projekt", "company": "gt_projekt",
         "hdr_bg": "bg-[#f0f9fe]",    "hdr_border": "border-[#bde8f7]",
         "dot": "bg-[#1666b0]",       "badge_bg": "bg-[#ddf1fb]",    "badge_text": "text-[#1255a0]"},
        {"status": "active",     "label": "DIRESO",     "company": "direso",
         "hdr_bg": "bg-teal-50",      "hdr_border": "border-teal-200",
         "dot": "bg-teal-400",        "badge_bg": "bg-teal-100",     "badge_text": "text-teal-700"},
        {"status": "on_hold",    "label": "Pausiert",   "company": "",
         "hdr_bg": "bg-purple-50",    "hdr_border": "border-purple-200",
         "dot": "bg-purple-400",      "badge_bg": "bg-purple-100",   "badge_text": "text-purple-700"},
        {"status": "invoiced",   "label": "Rechnung",   "company": "",
         "hdr_bg": "bg-orange-50",    "hdr_border": "border-orange-200",
         "dot": "bg-orange-400",      "badge_bg": "bg-orange-100",   "badge_text": "text-orange-700"},
    ]

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        projects = list(
            Project.objects
            .exclude(status__in=Project.ARCHIVED_STATUSES)
            .select_related("account", "team_lead")
            .order_by("name")
        )

        columns = []
        for col_def in self.COLUMNS:
            col_projects = [
                p for p in projects
                if p.status == col_def["status"]
                and (not col_def["company"] or p.company == col_def["company"])
            ]
            columns.append({
                **col_def,
                "projects": col_projects,
                "count":    len(col_projects),
            })

        ctx["columns"] = columns
        return ctx


class ProjectKanbanMoveView(CRMMixin, View):
    """AJAX-Endpunkt: Projektstatus per Drag & Drop aktualisieren."""

    VALID_STATUSES = {s for s in Project.Status.values if s not in Project.ARCHIVED_STATUSES}

    def post(self, request):
        import json
        try:
            data       = json.loads(request.body)
            project_id = data["project_id"]
            new_status = data["new_status"]
        except (KeyError, ValueError, json.JSONDecodeError):
            return JsonResponse({"ok": False, "error": "Invalid request"}, status=400)

        if new_status not in self.VALID_STATUSES:
            return JsonResponse({"ok": False, "error": "Invalid status"}, status=400)

        try:
            project = Project.objects.get(pk=project_id)
        except Project.DoesNotExist:
            return JsonResponse({"ok": False, "error": "Not found"}, status=404)

        project.status = new_status
        project.save(update_fields=["status"])
        return JsonResponse({"ok": True})


# ---------------------------------------------------------------------------
# Dokument-Upload / Viewer / Löschen
# ---------------------------------------------------------------------------

class DocumentUploadView(AdminOrLeadMixin, View):
    """PDF-Upload für ein Projekt-Dokument."""

    # Automatische Status-Übergänge beim Hochladen eines Dokuments
    STATUS_TRANSITIONS = {
        Document.DocumentType.OFFER:      ("lead",       "offer_sent"),
        Document.DocumentType.COMMISSION: ("offer_sent", "active"),
    }

    def post(self, request, pk):
        project = get_object_or_404(Project, pk=pk)
        doc_type = request.POST.get("document_type", "").strip()
        uploaded = request.FILES.get("file")

        if not uploaded or doc_type not in Document.DocumentType.values:
            messages.error(request, "Ungültiger Upload.")
            return redirect("crm:project_detail", pk=pk)

        title = request.POST.get("title", "").strip() or uploaded.name

        doc = Document.objects.create(
            project=project,
            document_type=doc_type,
            title=title,
            file=uploaded,
            uploaded_by=request.user,
        )

        # Automatischer Status-Übergang
        transition = self.STATUS_TRANSITIONS.get(doc_type)
        if transition:
            from_status, to_status = transition
            if project.status == from_status:
                project.status = to_status
                project.save(update_fields=["status"])
                messages.success(
                    request,
                    f'Dokument gespeichert. Status geändert zu „{project.get_status_display()}".'
                )
            else:
                messages.success(request, "Dokument gespeichert.")
        else:
            messages.success(request, "Dokument gespeichert.")

        return redirect("crm:project_detail", pk=pk)


class DocumentDeleteView(AdminOrLeadMixin, View):
    """Löscht ein Dokument und seine Datei."""

    def post(self, request, pk, doc_pk):
        doc = get_object_or_404(Document, pk=doc_pk, project_id=pk)
        if doc.file:
            doc.file.delete(save=False)
        doc.delete()
        messages.success(request, "Dokument gelöscht.")
        return redirect("crm:project_detail", pk=pk)


class DocumentServeView(CRMMixin, View):
    """Sendet eine Dokument-Datei als Inline-PDF oder Download."""

    def get(self, request, pk, doc_pk):
        doc = get_object_or_404(Document, pk=doc_pk, project_id=pk)
        if not doc.file:
            from django.http import Http404
            raise Http404
        download = request.GET.get("download") == "1"
        disposition = "attachment" if download else "inline"
        response = HttpResponse(doc.file, content_type="application/pdf")
        filename = doc.file.name.split("/")[-1]
        response["Content-Disposition"] = f'{disposition}; filename="{filename}"'
        return response


# ---------------------------------------------------------------------------
# vCard-Hilfsfunktionen
# ---------------------------------------------------------------------------

def _vcard_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace(",", "\\,").replace(";", "\\;").replace("\n", "\\n")


def _contact_to_vcard(contact: Contact) -> str:
    lines = [
        "BEGIN:VCARD",
        "VERSION:3.0",
        f"N:{_vcard_escape(contact.last_name)};{_vcard_escape(contact.first_name)};;;",
        f"FN:{_vcard_escape(contact.get_full_name())}",
    ]
    if contact.company_name:
        lines.append(f"ORG:{_vcard_escape(contact.company_name)}")
    if contact.role:
        lines.append(f"TITLE:{_vcard_escape(contact.get_role_display())}")
    if contact.email:
        lines.append(f"EMAIL;TYPE=INTERNET:{_vcard_escape(contact.email)}")
    if contact.phone:
        lines.append(f"TEL;TYPE=WORK:{_vcard_escape(contact.phone)}")
    if contact.mobile:
        lines.append(f"TEL;TYPE=CELL:{_vcard_escape(contact.mobile)}")
    addr_parts = [
        "", "",
        contact.address_line1,
        contact.city, "",
        contact.postal_code,
        contact.country,
    ]
    if any(addr_parts):
        lines.append("ADR;TYPE=WORK:" + ";".join(_vcard_escape(p) for p in addr_parts))
    if contact.notes:
        lines.append(f"NOTE:{_vcard_escape(contact.notes)}")
    lines.append("END:VCARD")
    return "\r\n".join(lines) + "\r\n"


def _parse_vcard(text: str) -> list[dict]:
    """Parst einen vCard-Text (3.0/4.0) und gibt eine Liste von Dicts zurück."""
    contacts = []
    current: dict | None = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.upper() == "BEGIN:VCARD":
            current = {}
            continue
        if line.upper() == "END:VCARD":
            if current is not None:
                contacts.append(current)
            current = None
            continue
        if current is None:
            continue

        if ":" not in line:
            continue
        prop, _, value = line.partition(":")
        prop_name = prop.split(";")[0].upper()
        value = value.replace("\\n", "\n").replace("\\,", ",").replace("\\;", ";")

        if prop_name == "N":
            parts = value.split(";")
            current["last_name"]  = parts[0] if len(parts) > 0 else ""
            current["first_name"] = parts[1] if len(parts) > 1 else ""
        elif prop_name == "FN" and "first_name" not in current:
            parts = value.split(" ", 1)
            current["first_name"] = parts[0]
            current["last_name"]  = parts[1] if len(parts) > 1 else ""
        elif prop_name == "ORG":
            current["company_name"] = value.split(";")[0]
        elif prop_name == "EMAIL":
            current.setdefault("email", value)
        elif prop_name == "TEL":
            prop_upper = prop.upper()
            if "CELL" in prop_upper or "MOBILE" in prop_upper:
                current.setdefault("mobile", value)
            else:
                current.setdefault("phone", value)
        elif prop_name == "ADR":
            parts = value.split(";")
            current["address_line1"] = parts[2] if len(parts) > 2 else ""
            current["city"]          = parts[3] if len(parts) > 3 else ""
            current["postal_code"]   = parts[5] if len(parts) > 5 else ""
            current["country"]       = parts[6] if len(parts) > 6 else ""
        elif prop_name == "NOTE":
            current["notes"] = value

    return contacts


# ---------------------------------------------------------------------------
# Kontakt-Views
# ---------------------------------------------------------------------------

class ContactListView(CRMMixin, ListView):
    model               = Contact
    template_name       = "crm/contact_list.html"
    context_object_name = "contacts"
    paginate_by         = 50

    def get_queryset(self):
        qs = Contact.objects.prefetch_related("projects")
        q = self.request.GET.get("q", "").strip()
        if q:
            qs = qs.filter(
                Q(first_name__icontains=q) |
                Q(last_name__icontains=q) |
                Q(company_name__icontains=q) |
                Q(email__icontains=q)
            )
        role = self.request.GET.get("role", "")
        if role:
            qs = qs.filter(role=role)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["q"]            = self.request.GET.get("q", "")
        ctx["role_filter"]  = self.request.GET.get("role", "")
        ctx["role_choices"] = Contact.Role.choices
        return ctx


class ContactDetailView(CRMMixin, DetailView):
    model         = Contact
    template_name = "crm/contact_detail.html"


class ContactCreateView(CRMMixin, CreateView):
    model         = Contact
    form_class    = ContactForm
    template_name = "crm/contact_form.html"

    def form_valid(self, form):
        contact = form.save()
        messages.success(self.request, f'Kontakt „{contact}" wurde erstellt.')
        return redirect("crm:contact_detail", pk=contact.pk)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"]   = "Neuer Kontakt"
        ctx["submit_label"] = "Kontakt erstellen"
        return ctx


class ContactUpdateView(CRMMixin, UpdateView):
    model         = Contact
    form_class    = ContactForm
    template_name = "crm/contact_form.html"

    def form_valid(self, form):
        contact = form.save()
        messages.success(self.request, f'Kontakt „{contact}" wurde aktualisiert.')
        return redirect("crm:contact_detail", pk=contact.pk)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"]   = f"{self.object} bearbeiten"
        ctx["submit_label"] = "Speichern"
        return ctx


class ContactVCardExportView(CRMMixin, View):
    def get(self, request, pk):
        contact = get_object_or_404(Contact, pk=pk)
        vcf = _contact_to_vcard(contact)
        filename = f"{contact.last_name}_{contact.first_name}.vcf".replace(" ", "_")
        response = HttpResponse(vcf, content_type="text/vcard; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response


class ContactVCardImportView(CRMMixin, View):
    def post(self, request):
        vcf_file = request.FILES.get("vcf_file")
        if not vcf_file:
            messages.error(request, "Keine Datei ausgewählt.")
            return redirect("crm:contact_list")

        text = vcf_file.read().decode("utf-8", errors="replace")
        parsed = _parse_vcard(text)
        created = 0
        for data in parsed:
            first = data.get("first_name", "").strip()
            last  = data.get("last_name", "").strip()
            if not first and not last:
                continue
            Contact.objects.create(
                first_name   = first,
                last_name    = last,
                company_name = data.get("company_name", ""),
                email        = data.get("email", ""),
                phone        = data.get("phone", ""),
                mobile       = data.get("mobile", ""),
                address_line1= data.get("address_line1", ""),
                postal_code  = data.get("postal_code", ""),
                city         = data.get("city", ""),
                country      = data.get("country", "") or "Deutschland",
                notes        = data.get("notes", ""),
            )
            created += 1

        messages.success(request, f"{created} Kontakt(e) importiert.")
        return redirect("crm:contact_list")
