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
from django.db.models import Count, Sum
from django.shortcuts import get_object_or_404, redirect
from django.views.generic import CreateView, DetailView, ListView, TemplateView, UpdateView, View

from .forms import AccountForm, ProjectForm
from .models import Account, Document, Project, ProjectBudgetExtension, ProjectMemberRate


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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
        messages.success(self.request, f'Account „{account.name}" wurde erstellt.')
        return redirect("crm:account_detail", pk=account.pk)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"]   = "Neuer Account"
        ctx["submit_label"] = "Account erstellen"
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
        messages.success(self.request, f'Account „{account.name}" wurde aktualisiert.')
        return redirect("crm:account_detail", pk=account.pk)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"]   = f"{self.object.name} bearbeiten"
        ctx["submit_label"] = "Speichern"
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
        project.save()
        form.save_m2m()  # team_members ManyToMany
        _save_member_rates(self.request, project, form.cleaned_data["team_members"])
        messages.success(self.request, f'Projekt „{project.name}" wurde erstellt.')
        return redirect("crm:project_detail", pk=project.pk)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"]   = "Neues Projekt"
        ctx["submit_label"] = "Projekt erstellen"
        form = kwargs.get("form") or ctx.get("form")
        if form:
            ctx["member_rates_data"] = _member_rates_data(form, project=None)
        ctx["project_types_by_company"] = Project.PROJECT_TYPES_BY_COMPANY
        return ctx


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

    # Spalten-Reihenfolge (keine archivierten Status)
    COLUMNS = [
        (Project.Status.LEAD,       "Lead"),
        (Project.Status.OFFER_SENT, "Angebot versendet"),
        (Project.Status.ACTIVE,     "Aktiv"),
        (Project.Status.ON_HOLD,    "Pausiert"),
        (Project.Status.INVOICED,   "Rechnung"),
    ]

    def get_context_data(self, **kwargs):
        ctx  = super().get_context_data(**kwargs)
        user = self.request.user

        projects = list(
            Project.objects
            .exclude(status__in=Project.ARCHIVED_STATUSES)
            .select_related("account", "team_lead")
            .order_by("team_lead__last_name", "team_lead__first_name", "name")
        )

        columns = []
        for status_value, status_label in self.COLUMNS:
            col_projects = [p for p in projects if p.status == status_value]

            # Innerhalb der Spalte nach Projektleiter gruppieren
            by_lead: dict = {}
            no_lead: list = []
            for project in col_projects:
                if project.team_lead:
                    key = project.team_lead.pk
                    if key not in by_lead:
                        by_lead[key] = {"lead": project.team_lead, "projects": []}
                    by_lead[key]["projects"].append(project)
                else:
                    no_lead.append(project)

            groups = list(by_lead.values())
            if no_lead:
                groups.append({"lead": None, "projects": no_lead})

            columns.append({
                "status": status_value,
                "label":  status_label,
                "groups": groups,
                "count":  len(col_projects),
            })

        ctx["columns"] = columns
        return ctx
