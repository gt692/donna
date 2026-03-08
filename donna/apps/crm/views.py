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

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db.models import Count, Sum
from django.shortcuts import redirect
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from .forms import AccountForm, ProjectForm
from .models import Account, Document, Project


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

    def get_queryset(self):
        user = self.request.user
        if user.is_admin:
            qs = Project.objects.all()
        else:
            # Teamleiter sehen ihre Projekte + zugewiesene
            qs = Project.objects.filter(
                team_lead=user
            ) | user.assigned_projects.all()
            qs = qs.distinct()

        qs = qs.select_related("account", "team_lead").order_by("-created_at")

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
        ctx["status_choices"] = Project.Status.choices
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
        messages.success(self.request, f'Projekt „{project.name}" wurde erstellt.')
        return redirect("crm:project_detail", pk=project.pk)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"]   = "Neues Projekt"
        ctx["submit_label"] = "Projekt erstellen"
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
            .select_related("user", "activity_type")
            .order_by("-date")[:20]
        )

        # Stunden-Statistik
        stats = TimeEntry.objects.filter(project=project).aggregate(
            total=Sum("duration_hours"),
            approved=Sum("duration_hours", filter=__import__("django.db.models", fromlist=["Q"]).Q(status="approved")),
        )

        ctx["time_entries"]     = entries
        ctx["hours_total"]      = float(stats["total"] or 0)
        ctx["hours_approved"]   = float(stats["approved"] or 0)
        ctx["documents"]        = project.documents.order_by("-document_date")
        ctx["team_members"]     = project.team_members.all()
        ctx["budget_pct"]       = (
            min(int(ctx["hours_approved"] / float(project.budget_hours) * 100), 100)
            if project.budget_hours else None
        )
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
        messages.success(self.request, f'Projekt „{project.name}" wurde aktualisiert.')
        return redirect("crm:project_detail", pk=project.pk)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"]   = f"{self.object.name} bearbeiten"
        ctx["submit_label"] = "Speichern"
        return ctx
