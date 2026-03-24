"""
dashboard/views.py
"""
from __future__ import annotations

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.mail import send_mail
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, ListView, TemplateView, UpdateView, View

from decimal import Decimal

from apps.core.models import CompanySettings, Role, RoleHourlyRate, User
from apps.crm.models import Account, ProductCatalog, Project, RevenueTarget
from apps.worktrack.models import TimeEntry

from .forms import CompanySettingsForm, UserCreateForm, UserEditForm


# ---------------------------------------------------------------------------
# Mixins
# ---------------------------------------------------------------------------

class AdminRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    login_url = "/auth/login/"

    def test_func(self) -> bool:
        return self.request.user.is_authenticated and self.request.user.is_admin


# ---------------------------------------------------------------------------
# Dashboard Home
# ---------------------------------------------------------------------------

class DashboardHomeView(LoginRequiredMixin, TemplateView):
    template_name = "dashboard/home.html"
    login_url = "/auth/login/"

    def get_context_data(self, **kwargs):
        ctx  = super().get_context_data(**kwargs)
        user = self.request.user
        now  = timezone.now()

        ctx["now"] = now

        week_start = now.date() - timezone.timedelta(days=now.weekday())

        # ── Projekt-Stats ──────────────────────────────────────────────────
        project_qs = (
            Project.objects.all()
            if user.is_admin
            else user.assigned_projects.all()
        )
        ctx["project_stats"] = {
            "active":    project_qs.filter(status=Project.Status.ACTIVE).count(),
            "on_hold":   project_qs.filter(status=Project.Status.ON_HOLD).count(),
            "completed": project_qs.filter(status=Project.Status.COMPLETED).count(),
            "total":     project_qs.count(),
        }

        # ── Stunden zur Genehmigung ────────────────────────────────────────
        if user.can_approve_time_entries():
            approvable_users = user.get_approvable_users()
            pending_qs = TimeEntry.objects.filter(
                status=TimeEntry.Status.SUBMITTED,
                user__in=approvable_users,
            ).select_related("user", "project").order_by("-date")
            ctx["pending_entries"]       = pending_qs[:10]
            ctx["pending_entries_count"] = pending_qs.count()
        else:
            ctx["pending_entries"] = TimeEntry.objects.filter(
                user=user, status=TimeEntry.Status.SUBMITTED,
            ).select_related("project")[:5]
            ctx["pending_entries_count"] = ctx["pending_entries"].count()

        # ── Eigene Stunden diese Woche ─────────────────────────────────────
        ctx["hours_this_week"] = (
            TimeEntry.objects.filter(
                user=user,
                date__gte=week_start,
                status__in=[TimeEntry.Status.APPROVED, TimeEntry.Status.SUBMITTED],
            ).aggregate(total=Sum("duration_hours"))["total"] or 0
        )

        # ── Letzte Projekt-Updates ─────────────────────────────────────────
        ctx["recent_projects"] = (
            Project.objects.select_related("account", "team_lead")
            .order_by("-updated_at")[:6]
        )

        # ── Account-Übersicht (Admin) ──────────────────────────────────────
        if user.is_admin:
            ctx["account_stats"] = {
                "total":    Account.objects.filter(is_active=True).count(),
                "customer": Account.objects.filter(
                    account_type=Account.AccountType.COMPANY, is_active=True
                ).count(),
            }
            ctx["user_count"] = User.objects.filter(is_active=True).count()

        # ── Team-Übersicht (Projektleiter) ────────────────────────────────────
        if user.is_project_manager:
            ctx["team_members"] = user.direct_reports.filter(is_active=True)
            ctx["team_hours_this_week"] = (
                TimeEntry.objects.filter(
                    user__in=ctx["team_members"],
                    date__gte=week_start,
                ).aggregate(total=Sum("duration_hours"))["total"] or 0
            )

        ctx["show_finance_kpis"] = False

        return ctx


# ---------------------------------------------------------------------------
# Administration — Benutzerverwaltung
# ---------------------------------------------------------------------------

class AdminIndexView(AdminRequiredMixin, TemplateView):
    template_name = "dashboard/admin/index.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["user_count"]              = User.objects.filter(is_active=True).count()
        ctx["admin_count"]             = User.objects.filter(role=Role.ADMIN, is_active=True).count()
        ctx["project_manager_count"]   = User.objects.filter(role=Role.PROJECT_MANAGER, is_active=True).count()
        ctx["employee_count"]          = User.objects.filter(role=Role.EMPLOYEE, is_active=True).count()
        ctx["project_assistant_count"] = User.objects.filter(role=Role.PROJECT_ASSISTANT, is_active=True).count()
        ctx["inactive_user_count"]     = User.objects.filter(is_active=False).count()
        ctx["recent_users"]            = User.objects.order_by("-date_joined")[:5]
        return ctx


class UserListView(AdminRequiredMixin, ListView):
    model = User
    template_name = "dashboard/admin/user_list.html"
    context_object_name = "users"

    def get_queryset(self):
        qs   = User.objects.select_related("reporting_to").order_by("last_name", "first_name")
        q    = self.request.GET.get("q", "").strip()
        role = self.request.GET.get("role", "")
        if q:
            qs = qs.filter(
                Q(first_name__icontains=q) |
                Q(last_name__icontains=q) |
                Q(email__icontains=q)
            )
        if role:
            qs = qs.filter(role=role)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["q"]           = self.request.GET.get("q", "")
        ctx["role_filter"] = self.request.GET.get("role", "")
        ctx["roles"]       = Role.choices
        return ctx


class UserCreateView(AdminRequiredMixin, CreateView):
    model = User
    form_class = UserCreateForm
    template_name = "dashboard/admin/user_form.html"
    success_url = reverse_lazy("dashboard:user_list")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"]   = "Neuer Benutzer einladen"
        ctx["submit_label"] = "Einladung senden"
        return ctx

    def form_valid(self, form):
        response = super().form_valid(form)
        user = self.object

        # Einladungs-Token generieren
        token = user.generate_invitation_token()

        # Einladungs-URL aufbauen
        invitation_path = reverse("core:invitation_accept", kwargs={"token": token})
        invitation_url  = self.request.build_absolute_uri(invitation_path)

        # E-Mail senden
        subject = "Du wurdest zu Donna Business OS eingeladen"
        body = (
            f"Hallo {user.first_name or user.email},\n\n"
            f"Du wurdest von {self.request.user.get_full_name()} zu Donna Business OS eingeladen.\n\n"
            f"Klicke auf den folgenden Link, um dein Passwort zu setzen und deinen Account zu aktivieren:\n\n"
            f"{invitation_url}\n\n"
            f"Der Link ist 7 Tage gültig.\n\n"
            f"Falls du diese Einladung nicht erwartet hast, ignoriere diese E-Mail.\n\n"
            f"Donna Business OS"
        )
        send_mail(
            subject=subject,
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=True,
        )

        messages.success(
            self.request,
            f"Einladung an {user.email} wurde gesendet.",
        )
        return response


class UserUpdateView(AdminRequiredMixin, UpdateView):
    model = User
    form_class = UserEditForm
    template_name = "dashboard/admin/user_form.html"
    success_url = reverse_lazy("dashboard:user_list")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"]   = f"{self.object.get_full_name()} bearbeiten"
        ctx["submit_label"] = "Änderungen speichern"
        ctx["edit_user"]    = self.object
        return ctx

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(
            self.request,
            f"Benutzer {self.object.get_full_name()} wurde aktualisiert.",
        )
        return response


class UserToggleActiveView(AdminRequiredMixin, View):
    """POST-only: aktiviert oder deaktiviert einen Benutzer."""

    def post(self, request, pk):
        target = get_object_or_404(User, pk=pk)
        if target == request.user:
            messages.error(request, "Du kannst dein eigenes Konto nicht deaktivieren.")
            return redirect("dashboard:user_list")
        target.is_active = not target.is_active
        target.save(update_fields=["is_active"])
        status = "aktiviert" if target.is_active else "deaktiviert"
        messages.success(request, f"{target.get_full_name()} wurde {status}.")
        return redirect("dashboard:user_list")


class UserDeleteView(AdminRequiredMixin, View):
    """POST-only: löscht einen Benutzer endgültig."""

    def post(self, request, pk):
        target = get_object_or_404(User, pk=pk)
        if target == request.user:
            messages.error(request, "Du kannst dein eigenes Konto nicht löschen.")
            return redirect("dashboard:user_list")
        name = target.get_full_name() or target.email
        target.delete()
        messages.success(request, f"Benutzer {name} wurde gelöscht.")
        return redirect("dashboard:user_list")


class UserResendInvitationView(AdminRequiredMixin, View):
    """POST-only: generiert neuen Einladungslink und sendet ihn erneut."""

    def post(self, request, pk):
        target = get_object_or_404(User, pk=pk)
        token = target.generate_invitation_token()
        invitation_path = reverse("core:invitation_accept", kwargs={"token": token})
        invitation_url  = request.build_absolute_uri(invitation_path)
        subject = "Deine Einladung zu Donna Business OS"
        body = (
            f"Hallo {target.first_name or target.email},\n\n"
            f"Du wurdest von {request.user.get_full_name()} zu Donna Business OS eingeladen.\n\n"
            f"Klicke auf den folgenden Link, um dein Passwort zu setzen und deinen Account zu aktivieren:\n\n"
            f"{invitation_url}\n\n"
            f"Der Link ist 7 Tage gültig.\n\n"
            f"Falls du diese Einladung nicht erwartet hast, ignoriere diese E-Mail.\n\n"
            f"Donna Business OS"
        )
        send_mail(
            subject=subject,
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[target.email],
            fail_silently=True,
        )
        messages.success(request, f"Einladung wurde erneut an {target.email} gesendet.")
        return redirect("dashboard:user_edit", pk=pk)


# ---------------------------------------------------------------------------
# 2FA-Verwaltung (Admin)
# ---------------------------------------------------------------------------

def _build_totp_qr(user: User, secret: str) -> str:
    """Generiert Base64-QR-Code als Data-URI für das gegebene Secret."""
    import base64
    import io

    import pyotp
    import qrcode

    totp    = pyotp.TOTP(secret)
    otp_uri = totp.provisioning_uri(name=user.email, issuer_name="Donna Business OS")
    img     = qrcode.make(otp_uri)
    buf     = io.BytesIO()
    img.save(buf, format="PNG")
    b64     = base64.b64encode(buf.getvalue()).decode()
    return f"data:image/png;base64,{b64}"


class UserTOTPSetupView(AdminRequiredMixin, View):
    """
    Admin richtet 2FA für einen anderen Benutzer ein.
    GET:  Secret generieren → QR-Code anzeigen.
    POST: Code prüfen → 2FA aktivieren.
    """
    template_name = "dashboard/admin/user_totp_setup.html"

    def _session_key(self, pk) -> str:
        return f"_donna_admin_totp_{pk}"

    def get(self, request, pk):
        import pyotp
        target = get_object_or_404(User, pk=pk)
        key    = self._session_key(pk)
        secret = request.session.get(key) or pyotp.random_base32()
        request.session[key] = secret
        return self._render(request, target, secret)

    def post(self, request, pk):
        import pyotp
        target = get_object_or_404(User, pk=pk)
        key    = self._session_key(pk)
        secret = request.session.get(key)
        if not secret:
            return redirect("dashboard:user_totp_setup", pk=pk)

        code = request.POST.get("code", "").strip()
        if pyotp.TOTP(secret).verify(code, valid_window=1):
            target.totp_secret  = secret
            target.totp_enabled = True
            target.save(update_fields=["totp_secret", "totp_enabled"])
            del request.session[key]
            messages.success(
                request,
                f"2FA für {target.get_full_name()} wurde erfolgreich aktiviert.",
            )
            return redirect("dashboard:user_edit", pk=pk)

        messages.error(request, "Der Code ist ungültig. Bitte erneut versuchen.")
        return self._render(request, target, secret, code_error=True)

    def _render(self, request, target, secret, code_error=False):
        from apps.core.forms import TOTPVerifyForm
        return __import__("django.shortcuts", fromlist=["render"]).render(
            request,
            self.template_name,
            {
                "target":     target,
                "secret":     secret,
                "qr_uri":     _build_totp_qr(target, secret),
                "code_error": code_error,
            },
        )


class UserTOTPDisableView(AdminRequiredMixin, View):
    """POST-only: deaktiviert 2FA für einen Benutzer."""

    def post(self, request, pk):
        target = get_object_or_404(User, pk=pk)
        target.totp_secret  = ""
        target.totp_enabled = False
        target.save(update_fields=["totp_secret", "totp_enabled"])
        messages.success(
            request,
            f"2FA für {target.get_full_name()} wurde deaktiviert.",
        )
        return redirect("dashboard:user_edit", pk=pk)


# ---------------------------------------------------------------------------
# RoleHourlyRate-Verwaltung
# ---------------------------------------------------------------------------

class HourlyRateListView(AdminRequiredMixin, TemplateView):
    template_name = "dashboard/admin/hourly_rate_list.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["rates"] = RoleHourlyRate.objects.order_by("role")
        return ctx


class HourlyRateUpdateView(AdminRequiredMixin, UpdateView):
    model = RoleHourlyRate
    fields = ["hourly_rate"]
    template_name = "dashboard/admin/hourly_rate_form.html"
    success_url = reverse_lazy("dashboard:hourly_rate_list")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"] = f"Stundensatz: {self.object.get_role_display()}"
        ctx["submit_label"] = "Speichern"
        return ctx

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(
            self.request,
            f"Stundensatz für {self.object.get_role_display()} wurde aktualisiert.",
        )
        return response


# ---------------------------------------------------------------------------
# Umsatzziele-Verwaltung
# ---------------------------------------------------------------------------

class RevenueTargetListView(AdminRequiredMixin, TemplateView):
    template_name = "dashboard/admin/revenue_target_list.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["targets"] = RevenueTarget.objects.order_by("-year", "company")
        return ctx


class RevenueTargetCreateView(AdminRequiredMixin, CreateView):
    model = RevenueTarget
    fields = ["company", "year", "target_amount"]
    template_name = "dashboard/admin/revenue_target_form.html"
    success_url = reverse_lazy("dashboard:revenue_target_list")

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields["year"].initial = __import__("datetime").date.today().year
        return form

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"] = "Neues Umsatzziel"
        ctx["submit_label"] = "Ziel anlegen"
        return ctx

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, "Umsatzziel wurde angelegt.")
        return response


class RevenueTargetUpdateView(AdminRequiredMixin, UpdateView):
    model = RevenueTarget
    fields = ["company", "year", "target_amount"]
    template_name = "dashboard/admin/revenue_target_form.html"
    success_url = reverse_lazy("dashboard:revenue_target_list")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"] = f"Umsatzziel bearbeiten"
        ctx["submit_label"] = "Speichern"
        return ctx

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, "Umsatzziel wurde aktualisiert.")
        return response


class RevenueTargetDeleteView(AdminRequiredMixin, View):
    def post(self, request, pk):
        target = get_object_or_404(RevenueTarget, pk=pk)
        target.delete()
        messages.success(request, "Umsatzziel wurde gelöscht.")
        return redirect("dashboard:revenue_target_list")


# ---------------------------------------------------------------------------
# Firmen-Zugangsdaten (Lexoffice API-Keys)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Projekttypen-Verwaltung
# ---------------------------------------------------------------------------

from apps.crm.models import ProjectType as ProjectTypeModel

class ProjectTypeListView(AdminRequiredMixin, TemplateView):
    template_name = "dashboard/admin/project_type_list.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["project_types"] = ProjectTypeModel.objects.all()
        return ctx


class ProjectTypeCreateView(AdminRequiredMixin, CreateView):
    model         = ProjectTypeModel
    fields        = ["name", "description", "color", "order", "is_active"]
    template_name = "dashboard/admin/project_type_form.html"
    success_url   = reverse_lazy("dashboard:project_type_list")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"]   = "Neuer Projekttyp"
        ctx["submit_label"] = "Projekttyp anlegen"
        return ctx

    def form_valid(self, form):
        messages.success(self.request, f"Projekttyp \"{form.instance.name}\" wurde angelegt.")
        return super().form_valid(form)


class ProjectTypeUpdateView(AdminRequiredMixin, UpdateView):
    model         = ProjectTypeModel
    fields        = ["name", "description", "color", "order", "is_active"]
    template_name = "dashboard/admin/project_type_form.html"
    success_url   = reverse_lazy("dashboard:project_type_list")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["page_title"]   = f"Projekttyp bearbeiten: {self.object.name}"
        ctx["submit_label"] = "Änderungen speichern"
        ctx["edit_obj"]     = self.object
        return ctx

    def form_valid(self, form):
        messages.success(self.request, f"Projekttyp \"{form.instance.name}\" wurde gespeichert.")
        return super().form_valid(form)


class ProjectTypeDeleteView(AdminRequiredMixin, View):
    def post(self, request, pk):
        pt = get_object_or_404(ProjectTypeModel, pk=pk)
        name = pt.name
        if pt.projects.exists():
            messages.error(request, f"\"{name}\" kann nicht gelöscht werden – es sind noch Projekte zugeordnet.")
        else:
            pt.delete()
            messages.success(request, f"Projekttyp \"{name}\" wurde gelöscht.")
        return redirect("dashboard:project_type_list")


# ---------------------------------------------------------------------------
# Firmeneinstellungen (Singleton)
# ---------------------------------------------------------------------------

class CompanySettingsView(AdminRequiredMixin, View):
    template_name = "dashboard/admin/company_settings.html"

    def get(self, request):
        from django.shortcuts import render as _render
        obj = CompanySettings.get()
        form = CompanySettingsForm(instance=obj)
        return _render(request, self.template_name, {"form": form, "settings_obj": obj})

    def post(self, request):
        from django.shortcuts import render as _render
        obj = CompanySettings.get()
        form = CompanySettingsForm(request.POST, request.FILES, instance=obj)
        if form.is_valid():
            form.save()
            messages.success(request, "Firmeneinstellungen gespeichert.")
            return redirect("dashboard:company_settings")
        return _render(request, self.template_name, {"form": form, "settings_obj": obj})


# ---------------------------------------------------------------------------
# Produktkatalog-Verwaltung
# ---------------------------------------------------------------------------

class ProductCatalogListView(AdminRequiredMixin, ListView):
    model = ProductCatalog
    template_name = "dashboard/admin/product_catalog_list.html"
    context_object_name = "products"
    queryset = ProductCatalog.objects.all().order_by("sort_order", "name")


class ProductCatalogCreateView(AdminRequiredMixin, View):
    template_name = "dashboard/admin/product_catalog_form.html"

    def get(self, request):
        from apps.dashboard.forms import ProductCatalogForm
        return render(request, self.template_name, {"form": ProductCatalogForm(), "title": "Neues Produkt"})

    def post(self, request):
        from apps.dashboard.forms import ProductCatalogForm
        form = ProductCatalogForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Produkt gespeichert.")
            return redirect("dashboard:product_catalog_list")
        return render(request, self.template_name, {"form": form, "title": "Neues Produkt"})


class ProductCatalogUpdateView(AdminRequiredMixin, View):
    template_name = "dashboard/admin/product_catalog_form.html"

    def get(self, request, pk):
        from apps.dashboard.forms import ProductCatalogForm
        obj = get_object_or_404(ProductCatalog, pk=pk)
        return render(request, self.template_name, {"form": ProductCatalogForm(instance=obj), "title": "Produkt bearbeiten", "object": obj})

    def post(self, request, pk):
        from apps.dashboard.forms import ProductCatalogForm
        obj = get_object_or_404(ProductCatalog, pk=pk)
        form = ProductCatalogForm(request.POST, instance=obj)
        if form.is_valid():
            form.save()
            messages.success(request, "Produkt gespeichert.")
            return redirect("dashboard:product_catalog_list")
        return render(request, self.template_name, {"form": form, "title": "Produkt bearbeiten", "object": obj})


class ProductCatalogDeleteView(AdminRequiredMixin, View):
    def post(self, request, pk):
        obj = get_object_or_404(ProductCatalog, pk=pk)
        obj.delete()
        messages.success(request, "Produkt gelöscht.")
        return redirect("dashboard:product_catalog_list")
